"""``read_export_source`` and failures around the capture (AC05, AC09, AC23).

Read-only: the export source never writes, never reads data rows and invents nothing for a
study that has no capture. A process killed during the capture or the final evaluation never
makes rows unseen again and never yields an evaluated binding.
"""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

import flowkit as fk
from flowkit import Flow
from hypotrail_runtime.errors import ContractError
from mlkit.contracts.export_source import read_export_source
from mlkit.study import case as c, state as st, store as sto

from test_capture_final import _chosen, _open


def test_export_source_of_a_captured_and_evaluated_study(tmp_path):
    flow = _chosen(tmp_path)
    v = flow.run('predictor.capture')['values']
    src = read_export_source(flow.study, flow.rev())
    assert src.predictor.status == 'captured' and src.predictor.evidence_status == 'unassessed'
    assert src.final_test['status'] == 'sealed'
    _open(flow)
    before = fk.tree_digest(flow.study)
    src = read_export_source(flow.study, flow.rev())
    assert fk.tree_digest(flow.study) == before                      # read-only
    assert src.predictor.predictor_id == v['predictor_id']
    assert src.predictor.evidence_status == 'evaluated'
    assert src.final_test['status'] == 'opened'
    text = src.canonical().decode()
    final_keys = fk.partition_keys(flow.study, 'final_test')
    assert not any(f'"{k}"' in text for k in final_keys)            # no final-test row key
    assert {d.decision_id for d in src.decisions} >= {'split', 'policy', 'final_test'}
    with pytest.raises(ContractError) as e:
        read_export_source(flow.study, flow.rev() - 1)
    assert e.value.code == 'stale_revision'


def test_a_study_evaluated_without_capture_gets_no_invented_model(tmp_path):
    flow = _chosen(tmp_path)
    _open(flow)
    src = read_export_source(flow.study, flow.rev())
    assert src.predictor.status == 'not_captured'
    assert src.predictor.predictor_id is None and src.predictor.evidence_status == 'unassessed'
    assert any('rebuilt candidate' in x for x in src.limitations)
    # A capture after the opening is refused: no rebuilt model receives the verdict (AC23).
    assert flow.run('predictor.capture', expect=2)['error']['code'] == 'precondition_missing'


def test_a_legacy_study_reads_without_any_change(tmp_path):
    case_dir = fk.make_case(tmp_path / 'case', n_rows=300)['case'].parent
    store = sto.StudyStore(tmp_path / 'study')
    store.create(st.initial_state(c.load_case(case_dir)))           # the v0.1 shape
    flow = Flow(tmp_path / 'study', case_dir)
    flow.pauses()
    flow.run('split')
    before = fk.tree_digest(flow.study)
    src = read_export_source(flow.study, flow.rev())
    assert fk.tree_digest(flow.study) == before
    assert src.predictor.status in ('not_applicable', 'not_captured')
    assert src.final_test['status'] == 'absent'
    out = flow.run('predictor.capture', expect=2)
    assert out['error']['code'] in ('invalid_arguments', 'precondition_missing')


def test_a_process_killed_during_the_capture_keeps_its_reads(tmp_path):
    flow = _chosen(tmp_path)
    rev = flow.rev()
    proc = subprocess.run([sys.executable, '-m', 'mlkit.study.cli', 'run', 'predictor.capture',
                           '--request-id', 'cap-1', '--expected-revision', str(rev),
                           '--study', str(flow.study)], capture_output=True, text=True,
                          cwd=tmp_path, env=fk.env(HYPOTRAIL_TEST_HOOKS='1',
                                                   HYPOTRAIL_FAULT='run_before_promote'))
    assert proc.returncode != 0
    # The next run records the interruption with the reads it had planned.
    out = flow.call('run', 'predictor.capture', '--request-id', flow.rid(),
                    '--expected-revision', flow.rev(), '--study', flow.study, expect=None)
    assert out['error']['code'] == 'interrupted_execution_pending'
    state = flow.state()
    interrupted = list(state['executions']['interrupted'].values())
    assert interrupted and interrupted[0]['activity'] == 'predictor.capture'
    records = [r for r in fk.exposure_records(flow.study)
               if r.get('activity') == 'predictor.capture']
    assert records and all(r['result_id'] is None for r in records)
    assert all(r['purpose'] == 'train_fit' for r in records)
    assert 'predictor.capture' not in state['current']
    assert not st.final_test_opened(state)
    src = read_export_source(flow.study, flow.rev())
    assert src.predictor.status == 'not_captured'                   # nothing half-recorded


def test_a_final_evaluation_failing_after_its_reservation_consumes_the_test(tmp_path):
    from mlkit.study import executions
    from test_wp_b1_final_test import _confirm_without_opening, _propose_final
    flow = _chosen(tmp_path)
    flow.run('predictor.capture')
    p = _propose_final(flow)
    _confirm_without_opening(flow, p['result']['proposal_id'])

    def boom(_plan):
        raise RuntimeError('the process failed while scoring')
    with pytest.raises(RuntimeError):
        executions.run(flow.study, 'final_test.evaluation', {}, request_id='open-x',
                       expected_revision=flow.rev(), hooks={'before_promote': boom})
    state = flow.state()
    assert st.final_test_opened(state)                     # consumed: never reopened
    src = read_export_source(flow.study, flow.rev())
    assert src.predictor.evidence_status == 'unassessed'   # no evaluated binding
    assert src.final_test['final_result_id'] is None
    bundle = sto.StudyStore(flow.study).home / src.predictor.bundle_dir
    assert not (bundle / 'evidence').exists()
    assert flow.run('final_test.evaluation', expect=2)['error']['code'] \
        == 'final_test_already_opened'
