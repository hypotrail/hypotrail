"""Regressions of the ninth review round (R9AB-1, R9AB-5, R9AB-6) of the Azure ML export, on
synthetic material and temporary folders only. The reviewer's probes are ported here.

* R9AB-1: SHA256SUMS is written with the data folder, so a file changed together with its
  checksum line passed every check. The development plan, the deployment snapshot and the
  evaluated model are now bound to the configuration that travels with the code: a plan
  given the final-test rows (its digests and checksum rewritten) is refused by ``validate``
  (``contract_identities``), by ``materialize`` and by every step (``artifact_integrity_
  failed``), and an evaluated model copied from another bundle is refused by ``validate``,
  ``predict`` and the steps (its predictor id is not the snapshot's).
* R9AB-5: a step that meets a refusal of ``hypotrail_runtime`` (``ContractError``) or of the
  packager (``PackagingError``) prints it as a JSON refusal with exit code 2, so
  ``run-local`` relays it instead of ``step_failed``.
* R9AB-6: a column named ``_target_`` exported, then the project's own ``validate`` refused
  its configuration; the export refuses it as it refuses ``${``.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import azureml_study as fx
from export_env import needs_hydra, needs_mlflow, project_env
from mlkit.exporters.azureml import canonical as cj
from mlkit.exporters.azureml import export_azureml
from mlkit.exporters.azureml.errors import ExportError

MOD = 'src.pipeline.utils.project'
PLAN = 'contracts/development-plan.json'
SNAPSHOT = 'contracts/deployment-snapshot.json'
FINAL_KEYS = [f'L{i}' for i in range(fx.N_ROWS - fx.N_FINAL + 1, fx.N_ROWS + 1)]


def _run(root: Path, *args, env: dict | None = None):
    return subprocess.run([sys.executable, '-m', MOD, *map(str, args)], cwd=root,
                          capture_output=True, text=True, env=env or project_env(),
                          check=False, timeout=900)


def _document(result) -> dict:
    return json.loads(result.stdout[result.stdout.index('{'):])


def _writable(path: Path) -> None:
    for item in [path, *path.rglob('*')] if path.is_dir() else [path]:
        os.chmod(item, 0o755 if item.is_dir() else 0o644)


def _rewrite(root: Path, rel: str, document: dict) -> None:
    """Write a contract of the data folder and its SHA256SUMS line, as the reviewer did."""
    data = root / 'data/hypotrail'
    _writable(data / rel)
    (data / rel).write_bytes(cj.pretty_bytes(document))
    _resum(root)


def _resum(root: Path) -> None:
    """Rewrite SHA256SUMS: one line for each file it lists that still exists and for each
    file under ``models/`` (the reviewer's rewrite of the checksums)."""
    data = root / 'data/hypotrail'
    sums = data / 'SHA256SUMS'
    _writable(sums)
    listed = [line.split('  ', 1)[1] for line in sums.read_text().splitlines() if line.strip()]
    names = {n for n in listed if (data / n).is_file()}
    names |= {p.relative_to(data).as_posix() for p in (data / 'models').rglob('*') if p.is_file()}
    sums.write_text(''.join(f'{cj.sha256_hex((data / n).read_bytes())}  {n}\n'
                            for n in sorted(names)))


def _read(root: Path, rel: str) -> dict:
    return json.loads((root / 'data/hypotrail' / rel).read_text())


def _with_final_test_rows(root: Path) -> int:
    """The reviewer's probe: the final-test keys added to fold_1, every digest of the plan
    recomputed, its checksum line rewritten. Returns the new number of development rows."""
    plan = _read(root, PLAN)
    part = plan['partitions'][0]
    part['row_keys'] = sorted(part['row_keys'] + FINAL_KEYS, key=lambda k: int(k[1:]))
    part['keys_sha256'] = cj.canonical_sha256(part['row_keys'])
    development = sorted({k for p in plan['partitions'] for k in p['row_keys']},
                         key=lambda k: int(k[1:]))
    plan['development_keys_sha256'] = cj.canonical_sha256(development)
    plan['n_development_rows'] = len(development)
    plan['keys_sha256'] = cj.canonical_sha256({p['id']: p['row_keys'] for p in plan['partitions']})
    _rewrite(root, PLAN, plan)
    return len(development)


def _checks(result) -> dict:
    return {c['id']: c for c in _document(result)['checks']}


@pytest.fixture
def exported(export, material, tmp_path):
    """A captured export copied to a writable folder, its development rows materialised."""
    payload, code, out = export(name='e')
    assert code == 0, payload
    root = tmp_path / 'project'
    shutil.copytree(out, root)
    result = _run(root, 'materialize', '--source', material['source'])
    assert result.returncode == 0, result.stderr[-2000:]
    return root


# --- R9AB-1: the plan, the snapshot and the evaluated model are bound ---------------------

@needs_mlflow
@needs_hydra
def test_a_plan_given_the_final_test_rows_is_refused_everywhere(exported, material, tmp_path):
    root = exported
    before = (root / 'data/hypotrail/development/development.csv').read_bytes()
    assert _with_final_test_rows(root) == fx.N_ROWS
    validation = _run(root, 'validate', '--offline')
    assert validation.returncode == 1
    checks = _checks(validation)
    # The checksums agree (they were rewritten): they never were the binding.
    assert checks['data_checksums']['status'] == 'passed'
    assert checks['contract_identities']['status'] == 'failed'
    error = checks['contract_identities']['error']
    assert error['code'] == 'artifact_integrity_failed'
    assert error['path'] == PLAN
    assert 'components.data_splitting.keys_sha256' in error['message']
    # materialize extracts nothing from that plan.
    result = _run(root, 'materialize', '--source', material['source'])
    assert result.returncode == 2
    refusal = _document(result)['error']
    assert (refusal['code'], refusal['path']) == ('artifact_integrity_failed', PLAN)
    assert (root / 'data/hypotrail/development/development.csv').read_bytes() == before
    # No step trains on it: the first step refuses before reading a row.
    run_dir = tmp_path / 'run'
    result = _run(root, 'run-local', '--mode', 'rebuild_final_candidate', '--run-dir', run_dir)
    assert result.returncode == 2, result.stderr[-2000:]
    document = _document(result)
    assert document['failed_step'] == 'data_preparation'
    assert (document['error']['code'], document['error']['path']) == \
        ('artifact_integrity_failed', PLAN)
    assert not (run_dir / '04_model').exists()


@needs_mlflow
@needs_hydra
def test_a_plan_with_relabelled_roles_differs_from_the_snapshot(exported):
    """The roles are outside the key digest: they are compared with the snapshot's
    evaluation plan, itself bound to ``hypotrail.snapshot_id``."""
    plan = _read(exported, PLAN)
    plan['partitions'][0]['role'] = 'train'
    _rewrite(exported, PLAN, plan)
    error = _checks(_run(exported, 'validate', '--offline'))['contract_identities']['error']
    assert error['code'] == 'artifact_integrity_failed' and error['path'] == PLAN
    assert error['details']['differing'] == ['roles']


def _other_bundle(material, tmp_path) -> Path:
    """Another predictor of the same recipe on the same rows (another training scope): it
    predicts the evaluated model's parity outputs, under another predictor id."""
    import hypotrail_runtime as rt
    other = fx.capture(rt, tmp_path / 'other', material['source'], material['contract'],
                       fx.recipe(), role='development_fit')
    assert rt.verify_bundle(other).predictor_id != \
        rt.verify_bundle(material['bundle']).predictor_id
    return other


def _swap_evaluated(root: Path, other: Path) -> None:
    evaluated = root / 'data/hypotrail/models/evaluated'
    _writable(evaluated)
    shutil.rmtree(evaluated)
    shutil.copytree(other, evaluated)
    _resum(root)


@needs_mlflow
@needs_hydra
def test_an_evaluated_model_from_another_bundle_is_refused(exported, material, tmp_path):
    root = exported
    snapshot_id = _read(root, SNAPSHOT)['predictor']['predictor_id']
    _swap_evaluated(root, _other_bundle(material, tmp_path))
    checks = _checks(_run(root, 'validate', '--offline'))
    assert checks['data_checksums']['status'] == 'passed'
    for check in ('contract_identities', 'evaluated_model_parity'):
        error = checks[check]['error']
        assert (error['code'], error['path']) == ('artifact_integrity_failed',
                                                  'models/evaluated'), check
        assert error['details']['expected'] == snapshot_id
        assert error['message'] == 'The evaluated model is not the predictor the snapshot names.'
    out = tmp_path / 'predictions.json'
    result = _run(root, 'predict', '--parity', '--output', out)
    assert result.returncode == 2
    assert _document(result)['error']['code'] == 'artifact_integrity_failed'
    assert not out.exists()
    result = _run(root, 'run-local', '--mode', 'rebuild_final_candidate', '--run-dir',
                  tmp_path / 'run')
    assert result.returncode == 2
    document = _document(result)
    assert document['failed_step'] == 'data_preparation'
    assert document['error']['path'] == 'models/evaluated'


@needs_mlflow
@needs_hydra
def test_a_snapshot_rewritten_to_name_the_other_model_is_refused(exported, material, tmp_path):
    """The swap with the snapshot's predictor id rewritten too: the snapshot no longer
    hashes to the configuration's ``hypotrail.snapshot_id``."""
    import hypotrail_runtime as rt
    other = _other_bundle(material, tmp_path)
    _swap_evaluated(exported, other)
    snapshot = _read(exported, SNAPSHOT)
    snapshot['predictor']['predictor_id'] = rt.verify_bundle(other).predictor_id
    _rewrite(exported, SNAPSHOT, snapshot)
    checks = _checks(_run(exported, 'validate', '--offline'))
    error = checks['contract_identities']['error']
    assert (error['code'], error['path']) == ('artifact_integrity_failed', SNAPSHOT)
    assert 'hypotrail.snapshot_id' in error['message']
    assert checks['evaluated_model_parity']['status'] == 'passed'


@needs_hydra
def test_an_identity_override_and_an_added_evaluated_model_are_refused(export, material):
    """An override of ``hypotrail.snapshot_id`` (or the study's id or revision) would name
    another snapshot: refused as ``scientific_config_changed``. A recipe-only export holds
    no evaluated model; one added to its data folder is refused."""
    payload, code, out = export(name='e', bundle=None)
    assert code == 0, payload
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
    root = out.parent / 'with-model'
    shutil.copytree(out, root)
    shutil.copytree(material['bundle'], root / 'data/hypotrail/models/evaluated')
    _resum(root)
    error = _checks(_run(root, 'validate', '--offline'))['contract_identities']['error']
    assert (error['code'], error['path']) == ('artifact_integrity_failed', 'models/evaluated')
    assert error['message'] == 'The export holds an evaluated model that its snapshot does not name.'


# --- R9AB-5: a step relays the refusals of the runtime and of the packager ------------------

# Each step's main and the function of steps.py it runs.
STEPS = [('data_preparation', 'prepare'), ('data_splitting', 'split'), ('training', 'train'),
         ('evaluation', 'evaluate')]


@needs_hydra
@pytest.mark.parametrize(('step', 'function'), STEPS)
def test_a_step_prints_a_runtime_or_packager_refusal(export, tmp_path, step, function):
    payload, code, out = export(name='e', bundle=None)
    assert code == 0, payload
    found = {}
    for kind in ('contract', 'packaging', 'internal'):
        # The step's main runs as ``python -m`` runs it (Hydra finds its configuration from
        # the module's file), its step function replaced by one that raises.
        script = (
            'import runpy, sys\n'
            'from src.pipeline.utils.hypotrail import steps\n'
            'from hypotrail_runtime.errors import ContractError\n'
            'from src.pipeline.utils.hypotrail.mlflow_packaging import PackagingError\n'
            'def refuse(frozen):\n'
            f'    kind = {kind!r}\n'
            '    if kind == "contract":\n'
            '        raise ContractError("environment_unqualified", "not the bound runtime",\n'
            '                            path="runtime/w.whl", remediation="install it")\n'
            '    if kind == "packaging":\n'
            '        raise PackagingError("artifact_integrity_failed", "the package differs",\n'
            '                             path="packages/mlflow_pyfunc", remediation="again")\n'
            '    raise KeyError("not a refusal")\n'
            f'steps.{function} = refuse\n'
            f'sys.argv = ["main.py", "hydra.run.dir={tmp_path / kind}"]\n'
            f'runpy.run_module("src.pipeline.{step}.main", run_name="__main__", alter_sys=True)\n')
        result = subprocess.run([sys.executable, '-c', script], cwd=out, capture_output=True,
                                text=True, env=project_env(), timeout=300)
        relayed = subprocess.run(
            [sys.executable, '-c', 'import json, sys\n'
             'from src.pipeline.utils.project import _step_refusal\n'
             'data = json.load(sys.stdin)\n'
             f'sys.stdout.write(json.dumps(_step_refusal({step!r}, data[0], data[1], data[2])))'],
            cwd=out, input=json.dumps([result.returncode, result.stdout, result.stderr]),
            capture_output=True, text=True, env=project_env(), timeout=300)
        assert relayed.returncode == 0, relayed.stderr[-2000:]
        found[kind] = (result.returncode, json.loads(relayed.stdout))
    code, refusal = found['contract']
    assert code == 2
    assert (refusal['code'], refusal['path'], refusal['remediation']) == \
        ('environment_unqualified', 'runtime/w.whl', 'install it')
    assert refusal['details']['source'] == 'hypotrail_runtime'
    code, refusal = found['packaging']
    assert code == 2
    assert (refusal['code'], refusal['path']) == ('artifact_integrity_failed',
                                                  'packages/mlflow_pyfunc')
    code, refusal = found['internal']
    assert code == 1
    assert refusal['code'] == 'step_failed'
    assert any('KeyError' in line for line in refusal['details']['output_tail'])


# --- R9AB-6: a Hydra instantiation key is refused at export ---------------------------------

def _renamed(source: Path, name: str):
    contract = fx.data_contract(source)
    for column in contract['columns']:
        if column['name'] == 'weight':
            column['name'] = name
    policy = contract['inference_policy']
    policy['required_columns'] = [name if n == 'weight' else n for n in policy['required_columns']]
    policy['canonical_order'] = [name if n == 'weight' else n for n in policy['canonical_order']]
    recipe = fx.recipe()
    recipe['features'] = [name if n == 'weight' else n for n in recipe['features']]
    recipe['feature_types'] = {(name if k == 'weight' else k): v
                               for k, v in recipe['feature_types'].items()}
    return fx._validated('contract', contract), fx._validated('recipe', recipe)


def _export_named(tmp_path: Path, name: str):
    source = fx.write_source(tmp_path)
    contract, recipe = _renamed(source, name)
    doc = fx.export_source(tmp_path, bundle_dir=None, the_recipe=recipe, contract=contract,
                           source=source)
    out = tmp_path / 'export'
    return export_azureml(tmp_path / 'study', expected_revision=fx.REVISION, out=out,
                          profile_path=fx.profile(tmp_path), reader=fx.reader_of(doc)), out


def test_a_column_named_target_is_refused_at_export(tmp_path):
    """The reviewer's probe: ``_target_`` exported, then the project's ``validate`` failed
    at ``hydra_config_frozen``. It is refused like ``${``, and nothing is written."""
    with pytest.raises(ExportError) as caught:
        _export_named(tmp_path, '_target_')
    assert caught.value.code == 'contract_invalid'
    assert caught.value.path == 'scientific_projection.feature_types._target_'
    assert '"_target_"' in caught.value.message
    assert not (tmp_path / 'export').exists()


@needs_hydra
@pytest.mark.parametrize('name', ['_args_', '_partial_'])
def test_hydra_s_other_instantiation_keys_export_and_validate(tmp_path, name):
    """Without ``_target_`` they are plain keys: the project composes and freezes them."""
    (payload, code), out = _export_named(tmp_path, name)
    assert code == 0, payload
    check = _checks(_run(out, 'validate', '--offline'))['hydra_config_frozen']
    assert check['status'] == 'passed', check


def test_the_refusal_names_every_carried_value_as_before():
    """The interpolation refusal itself is unchanged (same code and remediation)."""
    from mlkit.exporters.azureml import render
    with pytest.raises(ExportError) as caught:
        render._no_interpolation({'features': ['a${b}']}, 'scientific_projection')
    assert caught.value.code == 'contract_invalid'
    assert caught.value.path == 'scientific_projection.features[0]'
    with pytest.raises(ExportError) as caught:
        render._no_interpolation({'feature_types': {'x': {'_target_': 1}}},
                                 'scientific_projection')
    assert caught.value.path == 'scientific_projection.feature_types.x._target_'
