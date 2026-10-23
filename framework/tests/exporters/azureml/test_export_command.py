"""``hypotrail export azureml``: refusals, statuses, determinism and contents.

Criteria: A02 (stale revision), A03/AC21 (repeatable bytes), A04 (occupied or unsafe
target), A05 (no captured model), A12 (altered model, incompatible lock), A15/AC24 (no
final-test keys, secrets or local paths), A19 (unsupported family), the draft/configured
statuses, the MAPIE capability refusal, and the CLI when chantier A's reader is absent.
"""
from __future__ import annotations

import copy
import json
import shutil
import stat
import sys
from pathlib import Path

import pytest

from export_env import HAS_MLFLOW, needs_mlflow
from mlkit.exporters.azureml import snapshot as sn
from mlkit.exporters.azureml.errors import ExportError

import azureml_study as fx


def _files(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob('*'))
            if p.is_file()}


def _refused(run, code, **kwargs):
    with pytest.raises(ExportError) as error:
        run(**kwargs)
    assert error.value.code == code, error.value.to_dict()
    return error.value


def test_a_configured_export_with_the_evaluated_model(export):
    payload, code, out = export()
    assert code == 0
    assert payload['schema'] == 'hypotrail.azureml_export/1'
    assert payload['configuration_status'] == 'configured' and payload['missing_fields'] == []
    assert payload['artifact_status'] == ('packaged' if HAS_MLFLOW else 'captured')
    assert payload['out'] == str(out) and payload['study_revision'] == fx.REVISION
    readiness = json.loads((out / 'data/hypotrail/contracts/readiness.json').read_text())
    assert readiness['evidence_status'] == 'evaluated'
    assert readiness['azure_job'] == 'not_submitted' and readiness['registered_model'] == \
        'not_registered' and readiness['azure_qualification'] == 'not_qualified'
    scopes = {c['scope'] for c in payload['next_commands']}
    assert scopes == {'local', 'network_read', 'azure_write'}
    recipe = json.loads((out / 'data/hypotrail/contracts/model-recipe.json').read_text())
    assert recipe == fx.recipe()
    training = (out / 'src/conf/components/training/default.yaml').read_text()
    assert 'type: "linear"' in training and '"fit_intercept": true' in training


def test_two_exports_are_byte_identical(export, tmp_path):
    first, _, a = export(name='a')
    second, _, b = export(name='b')
    assert first['export_id'] == second['export_id']
    assert first['snapshot_id'] == second['snapshot_id']
    assert _files(a) == _files(b)
    text = b''.join(_files(a).values())
    assert str(tmp_path).encode() not in text


def test_another_revision_is_another_snapshot(export):
    first, _, _ = export(name='a')
    second, _, _ = export(name='b', source_changes={'revision': fx.REVISION + 1},
                          expected_revision=fx.REVISION + 1)
    assert first['snapshot_id'] != second['snapshot_id']
    assert first['export_id'] != second['export_id']


def test_a_stale_revision_is_refused_and_nothing_is_written(export, tmp_path):
    _refused(export, 'stale_revision', expected_revision=fx.REVISION - 1)
    assert not (tmp_path / 'export').exists()
    assert not [p for p in tmp_path.iterdir() if '.export-' in p.name]


def _source(material, **kwargs):
    return fx.export_source(material['folder'], contract=material['contract'],
                            source=material['source'], **kwargs)


def test_a_reader_that_returns_another_revision_is_refused(export, material):
    source = _source(material, bundle_dir=None)

    def reader(path, revision):
        return {**source, 'revision': revision + 1}
    _refused(export, 'stale_revision', reader=reader)


def test_plan_writes_nothing(export, tmp_path):
    payload, code, out = export(plan=True)
    assert code == 0 and payload['plan'] is True and payload['out'] is None
    assert payload['files'] and not out.exists()


def test_an_occupied_target_is_refused_untouched(export, tmp_path):
    target = tmp_path / 'busy'
    target.mkdir()
    (target / 'mine.txt').write_text('keep')
    error = _refused(export, 'export_target_exists', out=target)
    assert error.details['contract_code'] == 'destination_not_empty'
    assert _files(target) == {'mine.txt': b'keep'}


def test_a_symlink_target_is_refused(export, tmp_path):
    real = tmp_path / 'real'
    real.mkdir()
    link = tmp_path / 'link'
    link.symlink_to(real)
    _refused(export, 'invalid_arguments', out=link)
    assert not any(real.iterdir())


def test_a_target_inside_the_study_engine_folder_is_refused(export, tmp_path):
    _refused(export, 'invalid_arguments', out=tmp_path / 'study' / '.hypotrail' / 'x')


def test_an_empty_existing_target_is_used(export, tmp_path):
    target = tmp_path / 'empty'
    target.mkdir()
    payload, code, _ = export(out=target)
    assert code == 0 and (target / 'README.md').is_file()


def test_a_draft_without_profile(export):
    payload, code, out = export(profile=False)
    assert code == 0 and payload['configuration_status'] == 'draft'
    assert 'compute' in payload['missing_fields']
    assert 'draft_not_ready_to_submit' in payload['warnings']
    assert 'azure_write' not in {c['scope'] for c in payload['next_commands']}
    job = (out / 'aml/pipelines/training/pipeline-job.yml').read_text()
    assert 'azureml:MISSING-compute' in job
    assert '**draft**' in (out / 'README.md').read_text()


def test_require_configured_refuses_a_draft_and_writes_nothing(export, tmp_path):
    error = _refused(export, 'contract_invalid', profile_changes={'compute': None},
                     require_configured=True)
    assert error.details['missing_fields'] == ['compute']
    assert not (tmp_path / 'export').exists()


def test_a_configured_export_has_no_missing_marker(export):
    payload, _, out = export()
    rendered = {f['path'] for f in payload['files'] if f['kind'] in ('rendered', 'generated')}
    for path, data in _files(out).items():
        if path in rendered:
            assert b'MISSING-' not in data, path


def test_no_final_test_key_secret_or_local_path_in_the_export(export, material):
    _, _, out = export()
    final = [k for p in fx.plan()['partitions'] if p['role'] == 'final_test' for k in p['row_keys']]
    for path, data in _files(out).items():
        for key in final:
            assert f'"{key}"'.encode() not in data and f"'{key}'".encode() not in data, (path, key)
        assert str(material['folder']).encode() not in data, path
        assert b'AccountKey=' not in data and b'SharedAccessSignature=' not in data
    plan = json.loads((out / 'data/hypotrail/contracts/development-plan.json').read_text())
    assert plan['final_test'] == {'status': 'opened_once', 'n_rows': fx.N_FINAL,
                                  'labels_included': False, 'row_keys_included': False}
    assert [p['role'] for p in plan['partitions']] == [f'fold_{k}' for k in range(1, 6)]


def test_exported_files_are_readable(export):
    _, _, out = export()
    for path in out.rglob('*'):
        if path.is_file():
            assert path.stat().st_mode & stat.S_IRUSR and path.stat().st_mode & stat.S_IROTH


def test_shared_modules_are_byte_copies(export):
    import mlkit.exporters.azureml.canonical as canonical
    import mlkit.integrations.mlflow_packaging as packaging
    _, _, out = export()
    folder = out / 'src/pipeline/utils/hypotrail'
    assert (folder / 'canonical.py').read_bytes() == Path(canonical.__file__).read_bytes()
    assert (folder / 'mlflow_packaging.py').read_bytes() == Path(packaging.__file__).read_bytes()


def test_a_study_without_captured_model_exports_its_recipe(export):
    payload, code, out = export(bundle=None)
    assert code == 0 and payload['artifact_status'] == 'missing'
    assert 'artifact_missing' in payload['warnings']
    assert 'model_environment_missing' in payload['warnings']
    assert not (out / 'data/hypotrail/models/evaluated').exists() or \
        not any((out / 'data/hypotrail/models/evaluated').iterdir())
    assert (out / 'data/hypotrail/contracts/model-recipe.json').is_file()
    assert 'No runtime wheel' in (out / 'aml/pipelines/training/runtime/Dockerfile').read_text()
    readiness = json.loads((out / 'data/hypotrail/contracts/readiness.json').read_text())
    assert readiness['artifact'] == 'missing' and readiness['evidence_status'] == 'missing'


def test_an_unconfirmed_selection_is_refused(export, material):
    source = _source(material, bundle_dir=None, confirmed=False)
    error = _refused(export, 'contract_invalid', reader=fx.reader_of(source))
    assert error.details['reason'] == 'selection_not_confirmed'


def test_a_stale_selected_result_is_refused(export, material):
    source = _source(material, bundle_dir=None, current=False)
    error = _refused(export, 'contract_invalid', reader=fx.reader_of(source))
    assert error.details['reason'] == 'selected_result_not_current'


def test_an_unsupported_family_is_refused_not_replaced(export, material):
    source = _source(material, bundle_dir=None, the_recipe=fx.recipe('ebm'))
    error = _refused(export, 'capability_not_supported', reader=fx.reader_of(source))
    assert error.details['path'] == 'model_recipe.family'


def test_a_calibrated_capability_is_refused_not_removed(export, material):
    the_recipe = fx.recipe()
    the_recipe['extensions'] = {'hypotrail.calibration': {'method': 'split_conformal'}}
    source = _source(material, bundle_dir=None, the_recipe=the_recipe)
    error = _refused(export, 'capability_not_supported', reader=fx.reader_of(source))
    assert 'calibration' in error.details['path']


def test_an_unknown_recipe_version_is_refused(export, material):
    the_recipe = fx.recipe()
    the_recipe['schema_version'] = 'hypotrail.model_recipe/2'
    source = _source(material, bundle_dir=None, the_recipe=the_recipe)
    _refused(export, 'schema_version_unsupported', reader=fx.reader_of(source))


def test_a_final_test_key_listed_as_development_is_refused(export, material):
    source = _source(material, bundle_dir=None)
    source['development_plan']['partitions'][0]['row_keys'].append(f'L{fx.N_ROWS}')
    _refused(export, 'contract_invalid', reader=fx.reader_of(source))


def _copy_bundle(material, tmp_path) -> Path:
    target = tmp_path / 'bundle-copy'
    shutil.copytree(material['bundle'], target)
    return target


def _with_bundle(export, bundle_dir, material):
    source = _source(material, bundle_dir=bundle_dir)
    return lambda **kw: export(reader=fx.reader_of(source), **kw)


def test_an_altered_model_payload_is_refused(export, material, tmp_path):
    bundle = _copy_bundle(material, tmp_path)
    payload = bundle / 'payload' / 'pipeline.joblib'
    payload.write_bytes(payload.read_bytes() + b'x')
    _refused(_with_bundle(export, bundle, material), 'artifact_integrity_failed')


def test_a_bundle_of_another_recipe_is_refused(export, material, tmp_path):
    bundle = _copy_bundle(material, tmp_path)
    source = _source(material, bundle_dir=bundle)
    source['scientific_contracts']['model_recipe']['parameters'] = {'fit_intercept': False}
    _refused(export, 'artifact_integrity_failed', reader=fx.reader_of(source))


def test_a_rebuilt_candidate_cannot_carry_an_evaluated_binding(export, material, runtime, tmp_path):
    bundle = fx.capture(runtime, tmp_path / 'rebuilt', material['source'], material['contract'],
                        fx.recipe(), role='rebuilt_candidate')
    fx.bind_evidence(bundle)
    _refused(_with_bundle(export, bundle, material), 'artifact_integrity_failed')


def test_an_unqualified_python_is_refused(export, material, runtime, tmp_path, monkeypatch):
    monkeypatch.setattr(runtime.platform, 'python_version', lambda: '3.11.9')
    bundle = fx.capture(runtime, tmp_path / 'py311', material['source'], material['contract'],
                        fx.recipe())
    monkeypatch.undo()
    _refused(_with_bundle(export, bundle, material), 'environment_unqualified')


def test_a_conflicting_lock_is_refused(export, material, runtime, tmp_path, monkeypatch):
    original = runtime._versions
    monkeypatch.setattr(runtime, '_versions',
                        lambda: original() + [{'distribution': 'pyyaml', 'version': '5.4.1'}])
    bundle = fx.capture(runtime, tmp_path / 'conflict', material['source'], material['contract'],
                        fx.recipe())
    monkeypatch.undo()
    _refused(_with_bundle(export, bundle, material), 'environment_unqualified')


def test_a_native_only_bundle_is_captured_not_packaged(export):
    payload, code, out = export(bundle='native_bundle')
    assert code == 0 and payload['artifact_status'] == 'captured'
    assert 'mlflow_package_missing' in payload['warnings']
    readiness = json.loads((out / 'data/hypotrail/contracts/readiness.json').read_text())
    assert readiness['evidence_status'] == 'unassessed'


@needs_mlflow
def test_without_mlflow_the_package_is_not_verified(export, monkeypatch):
    import importlib.util
    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, 'find_spec',
                        lambda name, *a: None if name == 'mlflow' else real(name, *a))
    payload, code, _ = export()
    assert payload['artifact_status'] == 'captured'
    assert 'mlflow_package_not_verified' in payload['warnings']


def test_the_export_refuses_without_a_runtime_for_a_captured_model(export, monkeypatch):
    monkeypatch.setitem(sys.modules, 'hypotrail_runtime', None)
    _refused(export, 'optional_dependency_missing')


def test_without_chantier_a_reader_the_cli_refuses_cleanly(tmp_path):
    from mlkit.study import cli
    if _importable(sn.SOURCE_MODULE):
        pytest.skip('chantier A provides read_export_source in this checkout')
    outcome = cli.run(['export', 'azureml', '--study', str(tmp_path), '--expected-revision', '1',
                       '--out', str(tmp_path / 'out')])
    assert outcome.exit_code == 2
    error = outcome.payload['error']
    assert error['code'] == 'optional_dependency_missing'
    assert error['details']['remediation'] and error['details']['path']
    assert not (tmp_path / 'out').exists()


def test_handoff_refuses_azureml_options(tmp_path):
    from mlkit.study import cli
    outcome = cli.run(['export', 'handoff', '--study', str(tmp_path), '--plan'])
    assert outcome.exit_code == 2


def _importable(name: str) -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError:
        return False


def test_the_snapshot_is_independent_of_the_object_shape(material):
    """A Pydantic-like ExportSource (model_dump) is read the same as a mapping."""
    source = fx.export_source(material['folder'], bundle_dir=None)

    class Model:
        def __init__(self, data):
            self._data = data

        def model_dump(self, mode='python'):
            return copy.deepcopy(self._data)
    from mlkit.exporters.azureml import layout
    caps = layout.load('team-azureml-v1').document['capabilities']
    a = sn.build(source, template_capabilities=caps)
    b = sn.build(Model(source), template_capabilities=caps)
    assert a.snapshot_id == b.snapshot_id


def test_a_failure_while_writing_leaves_nothing(export, tmp_path, monkeypatch):
    """A16: the publication is atomic; a failure removes the temporary folder."""
    from mlkit.exporters.azureml import layout
    calls = {'n': 0}
    real = layout.check_tree

    def failing(root, template):
        calls['n'] += 1
        raise OSError('disk full (simulated)')
    monkeypatch.setattr(layout, 'check_tree', failing)
    with pytest.raises(OSError):
        export()
    monkeypatch.setattr(layout, 'check_tree', real)
    assert calls['n'] == 1
    assert not (tmp_path / 'export').exists()
    assert not [p for p in tmp_path.iterdir() if '.export-' in p.name]


def test_the_engine_imports_no_optional_library(tmp_path):
    """AC25: the CLI and the exporter import neither MLflow nor Hydra until they are used."""
    import subprocess
    code = ('import sys, mlkit.study.cli, mlkit.study.cmd_export, mlkit.exporters.azureml, '
            'mlkit.integrations.mlflow_packaging; '
            'print([m for m in ("mlflow", "hydra", "omegaconf") if m in sys.modules])')
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                            check=True)
    assert result.stdout.strip() == '[]'


def test_the_notebook_is_a_valid_walkthrough(export):
    _, _, out = export()
    notebook = json.loads((out / 'notebooks/01_first_draft.ipynb').read_text())
    assert notebook['nbformat'] == 4 and notebook['cells']
    text = ''.join(''.join(c['source']) for c in notebook['cells'])
    assert 'study-synthetic-cars' in text and 'predict' in text and 'outputs' in text


def test_an_interpolation_like_value_is_refused(export, material):
    """A scientific value that OmegaConf would interpolate never reaches the project."""
    the_recipe = fx.recipe()
    the_recipe['parameters'] = {'fit_intercept': True, 'note': '${oc.env:HOME}'}
    source = _source(material, bundle_dir=None, the_recipe=the_recipe)
    error = _refused(export, 'contract_invalid', reader=fx.reader_of(source))
    assert error.details['path'].startswith('scientific_projection')


def test_the_rendered_configuration_is_block_yaml(export):
    _, _, out = export()
    text = (out / 'src/conf/components/training/default.yaml').read_text()
    assert 'params:\n    fit_intercept: true\n' in text
    assert not [line for line in text.splitlines() if line != line.rstrip()]
