"""A changed case or dataset file is refused or flagged everywhere (review finding L1).

Plan §3.7 row 12: decisions and results refer to the bytes recorded at ``init``. The
case file is re-read by every activity, so it is verified against the recorded digest
when the computation loads it, when a decision is proposed, when the view is built
(flagged, since ``status`` must still answer), and when deliverables are rendered.
The case is copied into ``tmp_path`` before it is changed.
"""
from __future__ import annotations

import json
import shutil

import pytest

from mlkit.study import cmd_render, executions as ex, view
from mlkit.study.errors import StudyError

import flowkit as fk
from flowkit import Flow


@pytest.fixture
def flow(tmp_path, synthetic_case_dir):
    case_dir = tmp_path / 'case'
    shutil.copytree(synthetic_case_dir, case_dir)
    f = Flow(tmp_path / 'study', case_dir)
    f.init()
    f.pauses()
    f.run('split')
    return f


def _touch_case(flow):
    path = flow.case_dir / 'case.yaml'
    path.write_text(path.read_text(encoding='utf-8') + '\n# edited after init\n',
                    encoding='utf-8')


def test_a_proposal_on_a_changed_case_is_refused(flow):
    _touch_case(flow)
    rev = flow.rev()
    out = flow.call('decide', 'propose', 'prediction_time', '--value', 'At signup',
                    '--restatement', 'You predict at signup.', '--rationale', 'Earlier.',
                    '--request-id', flow.rid(), '--expected-revision', rev, '--study',
                    flow.study, expect=2)
    assert out['error']['code'] == 'dataset_changed'
    assert out['error']['details']['path'].endswith('case.yaml')
    assert flow.rev() == rev


def test_the_view_flags_a_changed_case_and_cites_nothing(flow):
    _touch_case(flow)
    v = view.build(flow.study)
    item = next(x for x in v['not_yet_defensible'] if x['id'] == 'sources_changed')
    assert [c['label'] for c in item['changes']] == ['case']
    assert v['results']['split']['current'] is False
    assert v['results']['split']['stale_reason']['sources_changed'] == ['case']


def test_render_refuses_a_changed_case(flow, tmp_path):
    before = (flow.study / 'reports' / 'study.html').read_bytes()
    _touch_case(flow)
    code, out = fk.hyp('render', '--study', flow.study, cwd=tmp_path)
    assert code == 2 and out['error']['code'] == 'dataset_changed'
    assert (flow.study / 'reports' / 'study.html').read_bytes() == before
    with pytest.raises(StudyError) as err:
        cmd_render.render_all(flow.study)
    assert err.value.code == 'dataset_changed'


def test_a_computation_refuses_a_case_changed_after_its_reservation(flow):
    rev = flow.rev()
    with pytest.raises(StudyError) as err:
        ex.run(flow.study, 'eda.target_rate', {}, request_id='edited', expected_revision=rev,
               hooks={'after_reserve': lambda plan: _touch_case(flow)})
    assert err.value.code == 'dataset_changed'
    assert err.value.details['path'].endswith('case.yaml')
    state = flow.state()
    assert 'eda.target_rate' not in state['current']
    record = json.loads((flow.study / '.hypotrail' / 'executions' /
                         f'{ex.execution_id("edited")}.json').read_text())
    assert record['status'] == 'failed' and record['error']['code'] == 'dataset_changed'
