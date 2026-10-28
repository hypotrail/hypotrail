"""Regressions of the review of 24 October 2026 through the real engine: temporary Auto MPG
studies go through the engine's commands, ``read_export_source`` and the real ``hypotrail
export azureml`` command (no reader double).

* B-M1: a capture of ``fit.linear`` followed by the confirmation of another model is not
  exported as the selected model, and ``read_export_source`` no longer calls it captured;
* B-M3: a study changed after its final test opened is exported recipe-only, without the
  earlier evidence, instead of being refused with an impossible remediation;
* E2: a stale ``--expected-revision`` is a refusal (exit code 2, ``details.contract_code``,
  ``details.path``, ``details.remediation``);
* the study identity does not depend on the folder the study is read from;
* a legacy study's refusal names a remediation the junior can follow.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

from export_env import needs_mlflow

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'study'))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'study' / 'libraries'))

pytestmark = [needs_mlflow]

WORDS = 'Yes, I choose that model because its error is smaller'
VARIANT_WORDS = 'Yes, I choose the variant because it is more stable'
OPEN = 'Yes, I open the final test now, because the model and the rule are fixed'


def _open_final(flow):
    from mlkit.study import state as st
    value = st.b1_default_value(flow.state(), 'final_test')
    proposal = flow.call('decide', 'propose', 'final_test', '--value-json', json.dumps(value),
                         '--restatement', 'You open the sealed final test once.',
                         '--rationale', 'The model is chosen.', '--request-id', flow.rid(),
                         '--expected-revision', flow.rev(), '--study', flow.study)
    flow.call('decide', 'confirm', proposal['result']['proposal_id'], '--user-words', OPEN,
              '--request-id', flow.rid(), '--expected-revision', flow.rev(),
              '--study', flow.study)


def _regression(base: Path, *, opened: bool):
    import libkit
    flow = libkit.study_at_fits(base, case_dir=libkit.AUTO)
    flow.run('fit.baseline')
    flow.run('fit.linear')
    flow.variant()
    flow.run('evaluate.regression')
    flow.decide('model_choice', 'fit.linear', words=WORDS)
    flow.run('predictor.capture', '--profile', 'workshop')
    if opened:
        _open_final(flow)
    return flow


def _copy(flow0, target: Path, prefix: str):
    from flowkit import Flow
    shutil.copytree(flow0.study, target)
    return Flow(target, flow0.case_dir, prefix=prefix)


def _export(flow, out: Path, profile: Path, expect=0):
    return flow.call('export', 'azureml', '--out', out, '--expected-revision', flow.rev(),
                     '--profile', profile, '--study', flow.study, expect=expect)


def _profile(folder: Path) -> Path:
    import azureml_study as fx
    return fx.profile(folder)


@pytest.fixture(scope='module')
def sealed(tmp_path_factory):
    return _regression(tmp_path_factory.mktemp('sealed'), opened=False)


@pytest.fixture(scope='module')
def opened(tmp_path_factory):
    return _regression(tmp_path_factory.mktemp('opened'), opened=True)


def test_another_confirmed_model_is_not_exported_with_the_old_capture(sealed, tmp_path):
    from mlkit.contracts.export_source import read_export_source
    flow = _copy(sealed, tmp_path / 'study', 'z')
    flow.decide('model_choice', 'fit.variant', words=VARIANT_WORDS)
    assert flow.state()['decisions']['model_choice']['value'] == 'fit.variant'
    source = read_export_source(flow.study, flow.rev())
    assert source.predictor.status == 'stale'
    assert source.predictor.evidence_status != 'evaluated'
    assert source.scientific_contracts.get('source') != 'captured_bundle'
    assert any('not the confirmed selection' in x for x in source.limitations)
    payload = _export(flow, tmp_path / 'out', _profile(tmp_path), expect=2)
    error = payload['error']
    assert error['code'] in ('model_not_captured', 'capability_not_supported'), error
    assert 'predictor.capture' in error['details']['remediation']
    assert not (tmp_path / 'out').exists()


def test_reconfirming_the_captured_model_keeps_the_capture_selected(sealed, tmp_path):
    from mlkit.contracts.export_source import read_export_source
    flow = _copy(sealed, tmp_path / 'study', 'r')
    source = read_export_source(flow.study, flow.rev())
    assert source.predictor.status == 'captured'
    assert source.scientific_contracts['source'] == 'captured_bundle'
    payload = _export(flow, tmp_path / 'out', _profile(tmp_path))
    assert payload['artifact_status'] == 'packaged'


def test_a_change_after_the_opening_is_exported_recipe_only(opened, tmp_path):
    from mlkit.contracts.export_source import read_export_source
    from mlkit.study import governance
    flow = _copy(opened, tmp_path / 'study', 'y')
    value = dict(governance.DEFAULT_PREPROCESSING)
    value['log_transform'] = ['weight']
    flow.decide('preprocessing', value)
    for activity in ('fit.baseline', 'fit.linear', 'fit.variant', 'evaluate.regression'):
        flow.run(activity)
    flow.decide('model_choice', 'fit.linear', words=WORDS)
    source = read_export_source(flow.study, flow.rev())
    assert source.predictor.status == 'stale'
    assert source.scientific_contracts['source'] == 'configuration'
    assert any('not inherited' in x for x in source.limitations)
    assert flow.run('predictor.capture', expect=2)['error']['code'] == 'precondition_missing'
    payload = _export(flow, tmp_path / 'out', _profile(tmp_path))
    assert payload['ok'] and payload['artifact_status'] == 'missing'
    out = tmp_path / 'out'
    assert not (out / 'data/hypotrail/models/evaluated').exists()
    ready = json.loads((out / 'data/hypotrail/contracts/readiness.json').read_text())
    assert ready['evidence_status'] == 'missing'
    snapshot = json.loads((out / 'data/hypotrail/contracts/deployment-snapshot.json')
                          .read_text())
    assert any('not inherited' in x for x in snapshot['limitations'])
    recipe = json.loads((out / 'data/hypotrail/contracts/model-recipe.json').read_text())
    ops = json.dumps(recipe['preprocessing'])
    assert 'weight' in ops                       # the recipe of the current preprocessing


def test_activity_after_the_opening_keeps_the_evaluated_export(opened, tmp_path):
    flow = _copy(opened, tmp_path / 'study', 'w')
    flow.run('eda.target_summary')
    payload = _export(flow, tmp_path / 'out', _profile(tmp_path))
    ready = json.loads((tmp_path / 'out/data/hypotrail/contracts/readiness.json').read_text())
    assert payload['artifact_status'] == 'packaged' and ready['evidence_status'] == 'evaluated'


def test_the_study_identity_does_not_depend_on_its_folder(opened, tmp_path):
    first = _copy(opened, tmp_path / 'a' / 'study', 'a')
    second = _copy(opened, tmp_path / 'participant-2' / 'study', 'b')
    one = _export(first, tmp_path / 'ea', _profile(tmp_path))
    two = _export(second, tmp_path / 'ec', _profile(tmp_path))
    assert one['snapshot_id'] == two['snapshot_id']
    assert one['export_id'] == two['export_id']


def test_a_stale_revision_is_a_refusal_with_the_contract_fields(opened, tmp_path):
    from mlkit.study import cli
    outcome = cli.run(['export', 'azureml', '--study', str(opened.study),
                       '--expected-revision', str(opened.rev() - 1), '--out',
                       str(tmp_path / 'o'), '--profile', str(_profile(tmp_path))])
    assert outcome.exit_code == 2, outcome.payload
    error = outcome.payload['error']
    assert error['code'] == 'stale_revision'
    assert error['details']['contract_code'] == 'stale_revision'
    assert error['details']['path'] == 'expected_revision'
    assert error['details']['remediation']
    assert not (tmp_path / 'o').exists()


def test_a_legacy_study_refusal_names_a_reachable_remediation(tmp_path):
    import flowkit as fk
    from flowkit import Flow
    from mlkit.study import case as c, state as st, store as sto
    case_dir = fk.make_case(tmp_path / 'case', n_rows=300)['case'].parent
    store = sto.StudyStore(tmp_path / 'study')
    store.create(st.initial_state(c.load_case(case_dir)))           # the v0.1 shape
    flow = Flow(tmp_path / 'study', case_dir)
    flow.pauses()
    flow.run('split')
    before = fk.tree_digest(flow.study)
    payload = _export(flow, tmp_path / 'out', _profile(tmp_path), expect=2)
    assert fk.tree_digest(flow.study) == before
    assert not (tmp_path / 'out').exists()
    error = payload['error']
    assert error['code'] == 'capability_not_supported'
    assert 'Update the engine' not in error['details']['remediation']
    # The study has no final test: its model choice is still open, and confirming it is
    # what lets the recipe be exported (never "update the engine").
    assert 'confirm the model choice' in error['details']['remediation']
