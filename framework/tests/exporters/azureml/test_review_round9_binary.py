"""NR-19 (owner session 2026-10-26, §6.2 item 5): the R9AB-1 integrity checks on a binary
export.

``test_review_round9.py`` ports the reviewer's R9AB-1 probes on the synthetic regression
material. Here the same probes run on a **binary logistic** export of a temporary synthetic
study taken through the engine's real commands (logistic fit, rule ``capacity:40``, two
captures at two revisions, the opening, ``export azureml --out``):

* a plan given the final-test rows (digests and checksum rewritten) is refused by
  ``validate`` (``contract_identities``), by ``materialize`` and by the first step;
* relabelled roles differ from the snapshot's evaluation plan;
* an evaluated model copied from another bundle (the study's earlier capture of the same
  configuration, another predictor id) is refused by ``validate``, ``predict`` and the
  steps, and the snapshot rewritten to name it no longer hashes to ``hypotrail.snapshot_id``;
* identity overrides are refused (``scientific_config_changed``), and an evaluated model
  added to a recipe-only binary export is refused.

The probes are imported from ``test_review_round9`` (never weakened); studies live in
temporary folders.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from export_env import needs_hydra, needs_mlflow, project_env
from mlkit.exporters.azureml import canonical as cj

import test_review_round9 as r9

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'study'))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'study' / 'libraries'))

pytestmark = [needs_mlflow, needs_hydra]

PLAN, SNAPSHOT = r9.PLAN, r9.SNAPSHOT
RULE = 'capacity:40'


def _key(k: str) -> int:
    return int(k[1:])


def _bundle(flow, values: dict) -> Path:
    return Path(flow.study) / '.hypotrail' / values['bundle']


def _binary_study(base: Path, capture: bool):
    import libkit
    from mlkit.study import state as st
    from test_binary_logistic import _adopt_policy, _open_final_test
    flow = libkit.study_at_fits(base, task='binary', n_rows=400)
    flow.run('fit.baseline')
    flow.run('fit.logistic')
    flow.run('policy.evaluate', '--rule', RULE)
    if st.has_explicit_binary_model_choice(flow.state()):
        flow.decide('model_choice', 'fit.logistic')
    _adopt_policy(flow, RULE)
    captures = []
    if capture:
        # Two captures of the same configuration at two revisions: two predictor ids.
        captures.append(flow.run('predictor.capture', '--profile', 'base')['values'])
        captures.append(flow.run('predictor.capture', '--profile', 'workshop')['values'])
        assert captures[0]['predictor_id'] != captures[1]['predictor_id']
    assert _open_final_test(flow)['result']['opening']['status'] == 'promoted'
    return flow, captures


@pytest.fixture(scope='module')
def binary(tmp_path_factory):
    import azureml_study as fx
    import flowkit as fk
    base = tmp_path_factory.mktemp('r9-binary')
    flow, captures = _binary_study(base, capture=True)
    out = base / 'export'
    payload = flow.call('export', 'azureml', '--out', out, '--expected-revision', flow.rev(),
                        '--profile', fx.profile(base), '--study', flow.study)
    assert payload['artifact_status'] == 'packaged'
    return {'flow': flow, 'out': out, 'source': Path(flow.case_dir) / 'data.csv',
            'final_keys': sorted(fk.partition_keys(flow.study, 'final_test'), key=_key),
            'n_rows': len(fk.partition_keys(flow.study, 'final_test'))
            + len(fk.partition_keys(flow.study, 'development')),
            'other': _bundle(flow, captures[0]), 'captured': captures[1]}


@pytest.fixture
def exported(binary, tmp_path):
    """The binary export copied to a writable folder, its development rows materialised."""
    root = tmp_path / 'project'
    shutil.copytree(binary['out'], root)
    result = r9._run(root, 'materialize', '--source', binary['source'])
    assert result.returncode == 0, result.stderr[-2000:]
    return root


def _with_final_test_rows(root: Path, final_keys: list[str]) -> int:
    """The reviewer's probe on the binary plan: the final-test keys added to the first
    partition, every digest recomputed, the checksum line rewritten."""
    plan = r9._read(root, PLAN)
    part = plan['partitions'][0]
    part['row_keys'] = sorted(set(part['row_keys']) | set(final_keys), key=_key)
    part['keys_sha256'] = cj.canonical_sha256(part['row_keys'])
    development = sorted({k for p in plan['partitions'] for k in p['row_keys']}, key=_key)
    plan['development_keys_sha256'] = cj.canonical_sha256(development)
    plan['n_development_rows'] = len(development)
    plan['keys_sha256'] = cj.canonical_sha256({p['id']: p['row_keys']
                                               for p in plan['partitions']})
    r9._rewrite(root, PLAN, plan)
    return len(development)


def test_a_binary_plan_given_the_final_test_rows_is_refused_everywhere(exported, binary,
                                                                       tmp_path):
    root = exported
    before = (root / 'data/hypotrail/development/development.csv').read_bytes()
    assert _with_final_test_rows(root, binary['final_keys']) == binary['n_rows']
    validation = r9._run(root, 'validate', '--offline')
    assert validation.returncode == 1
    checks = r9._checks(validation)
    assert checks['data_checksums']['status'] == 'passed'
    assert checks['contract_identities']['status'] == 'failed'
    error = checks['contract_identities']['error']
    assert (error['code'], error['path']) == ('artifact_integrity_failed', PLAN)
    assert 'components.data_splitting.keys_sha256' in error['message']
    result = r9._run(root, 'materialize', '--source', binary['source'])
    assert result.returncode == 2
    refusal = r9._document(result)['error']
    assert (refusal['code'], refusal['path']) == ('artifact_integrity_failed', PLAN)
    assert (root / 'data/hypotrail/development/development.csv').read_bytes() == before
    run_dir = tmp_path / 'run'
    result = r9._run(root, 'run-local', '--mode', 'rebuild_final_candidate', '--run-dir',
                     run_dir)
    assert result.returncode == 2, result.stderr[-2000:]
    document = r9._document(result)
    assert document['failed_step'] == 'data_preparation'
    assert (document['error']['code'], document['error']['path']) == \
        ('artifact_integrity_failed', PLAN)
    assert not (run_dir / '04_model').exists()


def test_a_binary_plan_with_relabelled_roles_differs_from_the_snapshot(exported):
    plan = r9._read(exported, PLAN)
    plan['partitions'][0]['role'] = ('train' if plan['partitions'][0]['role'] != 'train'
                                     else 'validation')
    r9._rewrite(exported, PLAN, plan)
    error = r9._checks(r9._run(exported, 'validate', '--offline'))['contract_identities'][
        'error']
    assert error['code'] == 'artifact_integrity_failed' and error['path'] == PLAN
    assert error['details']['differing'] == ['roles']


def test_a_binary_evaluated_model_from_another_bundle_is_refused(exported, binary, tmp_path):
    root = exported
    snapshot_id = r9._read(root, SNAPSHOT)['predictor']['predictor_id']
    assert snapshot_id == binary['captured']['predictor_id']
    r9._swap_evaluated(root, binary['other'])
    checks = r9._checks(r9._run(root, 'validate', '--offline'))
    assert checks['data_checksums']['status'] == 'passed'
    for check in ('contract_identities', 'evaluated_model_parity'):
        error = checks[check]['error']
        assert (error['code'], error['path']) == ('artifact_integrity_failed',
                                                  'models/evaluated'), check
        assert error['details']['expected'] == snapshot_id
        assert error['message'] == 'The evaluated model is not the predictor the snapshot names.'
    out = tmp_path / 'predictions.json'
    result = r9._run(root, 'predict', '--parity', '--output', out)
    assert result.returncode == 2
    assert r9._document(result)['error']['code'] == 'artifact_integrity_failed'
    assert not out.exists()
    result = r9._run(root, 'run-local', '--mode', 'rebuild_final_candidate', '--run-dir',
                     tmp_path / 'run')
    assert result.returncode == 2
    document = r9._document(result)
    assert document['failed_step'] == 'data_preparation'
    assert document['error']['path'] == 'models/evaluated'


def test_a_binary_snapshot_rewritten_to_name_the_other_model_is_refused(exported, binary):
    import hypotrail_runtime as rt
    r9._swap_evaluated(exported, binary['other'])
    snapshot = r9._read(exported, SNAPSHOT)
    snapshot['predictor']['predictor_id'] = rt.verify_bundle(binary['other']).predictor_id
    r9._rewrite(exported, SNAPSHOT, snapshot)
    checks = r9._checks(r9._run(exported, 'validate', '--offline'))
    error = checks['contract_identities']['error']
    assert (error['code'], error['path']) == ('artifact_integrity_failed', SNAPSHOT)
    assert 'hypotrail.snapshot_id' in error['message']
    # The decision rule travels inside the snapshot: changing it breaks the binding too.
    assert 'decision_rule' in snapshot


def test_a_binary_decision_rule_rewritten_is_refused(exported):
    """The rule is metadata bound by ``hypotrail.snapshot_id``: a rewritten rule (with its
    checksum line) no longer matches the configuration."""
    snapshot = r9._read(exported, SNAPSHOT)
    snapshot['decision_rule']['rule'] = 'capacity:10'
    snapshot['decision_rule']['amount'] = '10'
    r9._rewrite(exported, SNAPSHOT, snapshot)
    error = r9._checks(r9._run(exported, 'validate', '--offline'))['contract_identities'][
        'error']
    assert (error['code'], error['path']) == ('artifact_integrity_failed', SNAPSHOT)
    assert 'hypotrail.snapshot_id' in error['message']


def test_binary_identity_overrides_and_an_added_evaluated_model_are_refused(binary,
                                                                           tmp_path):
    import azureml_study as fx
    flow, _ = _binary_study(tmp_path / 'recipe-only', capture=False)
    out = tmp_path / 'export'
    payload = flow.call('export', 'azureml', '--out', out, '--expected-revision', flow.rev(),
                        '--profile', fx.profile(tmp_path), '--study', flow.study)
    assert payload['artifact_status'] == 'missing'
    script = (
        'import json, sys\n'
        'from pathlib import Path\n'
        'from src.pipeline.utils.hypotrail import contracts\n'
        'from src.pipeline.utils.hypotrail.errors import ProjectError\n'
        'from src.pipeline.utils.project import _frozen_config\n'
        'frozen = _frozen_config()\n'
        'snapshot = contracts.load_json(Path("data/hypotrail") / contracts.FILES["snapshot"])\n'
        'out = []\n'
        'for overrides in (["hypotrail.snapshot_id=x"], ["+hypotrail.study_revision=8"], '
        '["models.path=elsewhere"]):\n'
        '    try:\n'
        '        contracts.check_snapshot(snapshot, frozen["config"], overrides)\n'
        '        out.append(None)\n'
        '    except ProjectError as error:\n'
        '        out.append([error.code, error.path])\n'
        'sys.stdout.write(json.dumps(out))\n')
    result = subprocess.run([sys.executable, '-c', script], cwd=out, capture_output=True,
                            text=True, env=project_env(), timeout=300)
    assert result.returncode == 0, result.stderr[-2000:]
    assert json.loads(result.stdout) == [
        ['scientific_config_changed', 'hypotrail.snapshot_id'],
        ['scientific_config_changed', 'hypotrail.study_revision'], None]
    root = tmp_path / 'with-model'
    shutil.copytree(out, root)
    shutil.copytree(binary['other'], root / 'data/hypotrail/models/evaluated')
    r9._resum(root)
    error = r9._checks(r9._run(root, 'validate', '--offline'))['contract_identities']['error']
    assert (error['code'], error['path']) == ('artifact_integrity_failed', 'models/evaluated')
    assert error['message'] == ('The export holds an evaluated model that its snapshot does '
                                'not name.')
