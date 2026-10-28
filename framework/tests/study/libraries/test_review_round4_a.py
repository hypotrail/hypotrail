"""Regressions of the fourth review round of 25 October 2026, area A (library runtime).

R4-A1 ``MLmodel`` was compared on a few keys only and nothing limited the files of a
package: ``data: evil`` in ``MLmodel`` made ``mlflow.pyfunc.load_model`` load
``evil/MLmodel`` and ``evil/hypotrail_pyfunc.py``, which no check read; ``verify_bundle``,
``ArtifactPackager.verify`` (which even ran the evil wrapper) and the export passed. Now
``MLmodel`` is the packager's own document, regenerated and compared byte for byte, and the
files of an ``mlflow_pyfunc`` package are an allowlist, enforced by the packager and by the
runtime. R4-A2 the ``artifact_id`` the capture records was never compared with the package
the bundle holds: the export and the final-test opening now refuse a bundle whose packages
are not the recorded ones. Ported from the reviewer's probes; every bundle and study lives in
``tmp_path`` and the data are synthetic.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from hypotrail_runtime import canonical, capture_predictor, load_predictor, verify_bundle
from hypotrail_runtime import predictor as runtime_predictor

import test_review_round2_a as r2
import test_review_round3_a as r3

PKG = r2.PKG
needs_mlflow = r2.needs_mlflow


def _evil_data_redirect(dest: Path) -> None:
    """The reviewer's probe: an ``evil/`` folder holding another wrapper and an MLmodel that
    loads it on the embedded bundle, ``data: evil`` added to the package's MLmodel, and the
    package re-described consistently everywhere."""
    pkg = dest / PKG
    evil = pkg / 'evil'
    evil.mkdir()
    (evil / 'hypotrail_pyfunc.py').write_text(r3.EVIL)
    top = yaml.safe_load((pkg / 'MLmodel').read_text())
    inner = json.loads(json.dumps(top))
    inner['flavors']['python_function']['artifacts']['native_bundle']['path'] = \
        '../artifacts/native_bundle'
    (evil / 'MLmodel').write_text(yaml.safe_dump(inner, sort_keys=True))
    top['flavors']['python_function']['data'] = 'evil'
    (pkg / 'MLmodel').write_text(yaml.safe_dump(top, sort_keys=True))
    r2._redescribe_mlflow_package(dest)


def _clean_copy(dest: Path, tmp_path: Path) -> Path:
    """A copy of the honest bundle, to verify a tampered package against it with the
    packager alone (outside any bundle the runtime would check)."""
    clean = tmp_path / 'clean' / 'b'
    shutil.copytree(dest, clean)
    return clean


def _package_alone(dest: Path, tmp_path: Path) -> Path:
    alone = tmp_path / 'alone' / 'package'
    shutil.copytree(dest / PKG, alone)
    return alone


# --- R4-A1: the package is exactly what the packager writes --------------------------------------

@needs_mlflow
def test_mlmodel_data_key_redirecting_loading_to_unchecked_code_is_refused(tmp_path,
                                                                          monkeypatch):
    """Reviewer probe. Before the fix verify_bundle accepted, ArtifactPackager.verify returned
    passed and ran the evil wrapper, the export said packaged, and the pyfunc served another
    model. Now the runtime refuses the files, the packager refuses both the files and the
    MLmodel before running anything, and the export refuses."""
    mp, dest, _ = r3._workshop(tmp_path)
    clean = _clean_copy(dest, tmp_path)
    marker = tmp_path / 'ran'
    monkeypatch.setenv('R3_MARKER', str(marker))
    _evil_data_redirect(dest)
    e = r2._refused(verify_bundle, dest)
    assert e.details['unexpected'] == [f'{PKG}/evil/MLmodel', f'{PKG}/evil/hypotrail_pyfunc.py']
    assert 'exactly the files' in e.message
    r2._refused(load_predictor, dest, trusted_roots=[dest.parent])
    err = r3._packaging_refused(mp.ArtifactPackager().verify, dest, dest / PKG)
    assert err.details['contract_code'] == 'artifact_integrity_failed'
    r3._export_refused(dest)
    # The packager alone, on the tampered package beside an honest bundle.
    alone = _package_alone(dest, tmp_path)
    err = r3._packaging_refused(mp.ArtifactPackager().verify, clean, alone)
    assert err.details['unexpected'] == ['evil/', 'evil/MLmodel', 'evil/hypotrail_pyfunc.py']
    shutil.rmtree(alone / 'evil')
    alone_files = [f for f in mp._inventory(alone) if f['relative_path'] != mp.DESCRIPTOR_FILE]
    doc = json.loads((alone / mp.DESCRIPTOR_FILE).read_bytes())
    doc['files'] = alone_files
    doc['artifact_id'] = canonical.artifact_id(doc, exclude=('artifact_id',))
    (alone / mp.DESCRIPTOR_FILE).write_bytes(canonical.dumps(doc) + b'\n')
    err = r3._packaging_refused(mp.ArtifactPackager().verify, clean, alone)
    assert 'flavors.python_function.data' in err.details['unexpected']
    assert 'MLmodel' in err.message
    assert not marker.exists(), 'package code ran during verify'
    assert mp.ArtifactPackager().verify(clean, clean / PKG).status == 'passed'
    assert not marker.exists()


def _edit_mlmodel(pkg: Path, edit) -> None:
    document = yaml.safe_load((pkg / 'MLmodel').read_text())
    edit(document)
    (pkg / 'MLmodel').write_text(yaml.safe_dump(document, sort_keys=True))


def _pyfunc(document):
    return document['flavors']['python_function']


MLMODEL_EDITS = {
    'data_on_the_embedded_bundle': (lambda d: _pyfunc(d).update(data='artifacts/native_bundle'),
                                    'unexpected', 'flavors.python_function.data'),
    'top_level_key_added': (lambda d: d.update(metadata={'note': 'added'}), 'unexpected',
                            'metadata'),
    'code_path_added': (lambda d: _pyfunc(d).update(code='artifacts'), 'changed',
                        'flavors.python_function.code'),
    'model_config_added': (lambda d: _pyfunc(d).update(model_config={'k': 1}), 'unexpected',
                           'flavors.python_function.model_config'),
    'loader_module_changed': (lambda d: _pyfunc(d).update(loader_module='mlflow.pyfunc.model'),
                              'changed', 'flavors.python_function.loader_module'),
    'model_code_path_changed': (lambda d: _pyfunc(d).update(
        model_code_path='artifacts/native_bundle/recipe.json'), 'changed',
        'flavors.python_function.model_code_path'),
    'key_removed': (lambda d: _pyfunc(d).pop('env'), 'missing', 'flavors.python_function.env'),
    'version_changed': (lambda d: d.update(mlflow_version='0.0.1'), 'changed',
                        'mlflow_version'),
}


@needs_mlflow
@pytest.mark.parametrize('name', sorted(MLMODEL_EDITS))
def test_an_mlmodel_other_than_the_generated_one_is_refused_before_loading(tmp_path,
                                                                           monkeypatch, name):
    """Variants: a key added at the top level or in the python_function block, a key
    removed, the loader module or the wrapper path changed. The package is re-described
    everywhere (the runtime cannot read MLmodel and accepts it); the packager regenerates
    MLmodel, refuses, names the difference, and loads nothing; so does the export."""
    import mlflow.pyfunc
    edit, kind, key = MLMODEL_EDITS[name]
    mp, dest, _ = r3._workshop(tmp_path)
    pkg = dest / PKG
    _edit_mlmodel(pkg, edit)
    r2._redescribe_mlflow_package(dest)
    verify_bundle(dest)
    loads = []
    monkeypatch.setattr(mlflow.pyfunc, 'load_model', lambda *a, **k: loads.append(a))
    err = r3._packaging_refused(mp.ArtifactPackager().verify, dest, pkg)
    assert key in err.details[kind], err.details
    assert err.path == 'mlflow_pyfunc' and err.details['file'] == 'MLmodel'
    assert 'not the document this packager writes' in err.message
    r3._export_refused(dest)
    assert loads == []


@needs_mlflow
def test_mlmodel_bytes_reformatted_with_the_same_values_are_refused(tmp_path):
    """The comparison is on bytes: the same document dumped by PyYAML is refused, so no
    parser difference can hide a key."""
    mp, dest, _ = r3._workshop(tmp_path)
    pkg = dest / PKG
    _edit_mlmodel(pkg, lambda d: None)
    r2._redescribe_mlflow_package(dest)
    err = r3._packaging_refused(mp.ArtifactPackager().verify, dest, pkg)
    assert err.details == {**err.details, 'unexpected': [], 'missing': [], 'changed': []}


LAYOUT_EDITS = {
    'extra_top_level_folder': ('extra/notes.txt', b'not written by the packager'),
    'extra_file_at_the_root': ('README.txt', b'not written by the packager'),
    'extra_python_module': ('helpers.py', b'print("imported")\n'),
    'extra_file_beside_the_bundle': ('artifacts/other.json', b'{}'),
}


@needs_mlflow
@pytest.mark.parametrize('name', sorted(LAYOUT_EDITS))
def test_a_file_the_packager_does_not_write_is_refused(tmp_path, name):
    """Variants: an extra top-level folder, an extra file at the root, a module, a file
    beside the embedded bundle, each named by the re-described descriptor. The runtime
    refuses it for the mlflow_pyfunc format, the packager too (also alone), and the export."""
    rel, data = LAYOUT_EDITS[name]
    mp, dest, _ = r3._workshop(tmp_path)
    clean = _clean_copy(dest, tmp_path)
    path = dest / PKG / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    r2._redescribe_mlflow_package(dest)
    e = r2._refused(verify_bundle, dest)
    assert e.details['unexpected'] == [f'{PKG}/{rel}'] and e.details['missing'] == []
    assert e.path == f'{PKG}/{rel}'
    err = r3._packaging_refused(mp.ArtifactPackager().verify, dest, dest / PKG)
    assert err.details['contract_code'] == 'artifact_integrity_failed'
    r3._export_refused(dest)
    err = r3._packaging_refused(mp.ArtifactPackager().verify, clean,
                                _package_alone(dest, tmp_path))
    assert rel in err.details['unexpected']


@needs_mlflow
@pytest.mark.parametrize('rel', ['python_env.yaml', 'MLmodel', 'hypotrail_pyfunc.py'])
def test_a_missing_package_file_is_refused(tmp_path, rel):
    mp, dest, _ = r3._workshop(tmp_path)
    (dest / PKG / rel).unlink()
    r2._redescribe_mlflow_package(dest)
    e = r2._refused(verify_bundle, dest)
    assert e.details['missing'] == [f'{PKG}/{rel}']
    err = r3._packaging_refused(mp.ArtifactPackager().verify, dest, dest / PKG)
    assert err.details['contract_code'] == 'artifact_integrity_failed'


@needs_mlflow
def test_an_empty_extra_folder_is_refused_by_the_packager(tmp_path):
    """An empty folder holds no listed file, so only the packager sees it; it refuses it."""
    mp, dest, _ = r3._workshop(tmp_path)
    (dest / PKG / 'evil').mkdir()
    verify_bundle(dest)
    err = r3._packaging_refused(mp.ArtifactPackager().verify, dest, dest / PKG)
    assert err.details['unexpected'] == ['evil/']


@needs_mlflow
def test_the_generated_package_is_the_allowlist_and_its_mlmodel_is_deterministic(tmp_path):
    """The package holds exactly the allowlist; MLmodel is the packager's document (no clock,
    random id, local path or local Python version), so two captures of the same predictor
    in two folders give the same MLmodel, the same package and the same artifact id; and
    MLflow loads it (the packager's parity check passed)."""
    mp, dest, d = r3._workshop(tmp_path)
    pkg = dest / PKG
    files = {f['relative_path'] for f in mp._inventory(pkg)}
    inner = {f for f in files if f.startswith(mp.EMBEDDED_BUNDLE + '/')}
    assert files - inner == set(mp.PACKAGE_FILES)
    assert mp.layout_issues(pkg) == {'unexpected': [], 'missing': []}
    descriptor = json.loads((pkg / mp.DESCRIPTOR_FILE).read_bytes())
    expected = mp.mlmodel_bytes(descriptor['signature'], descriptor['environment'])
    assert (pkg / 'MLmodel').read_bytes() == expected
    text = expected.decode('ascii')
    for absent in ('utc_time_created', 'model_uuid', 'model_size_bytes', str(tmp_path),
                   '"data"'):
        assert absent not in text
    assert yaml.safe_load(text) == mp.mlmodel_document(descriptor['signature'],
                                                       descriptor['environment'])
    assert d.packages[0].parity_result.status == 'ok'
    other = tmp_path / 'elsewhere'
    other.mkdir()
    again = capture_predictor(r2._fitted(), None, r2._parity(), other / 'b',
                              mp.packager_for('atelier'), code_fingerprint=r2.FP)
    assert again.predictor_id == d.predictor_id
    assert (other / 'b' / PKG / 'MLmodel').read_bytes() == expected
    assert again.packages[0].artifact_id == d.packages[0].artifact_id


def test_the_runtime_and_the_packager_share_one_allowlist():
    pytest.importorskip('mlflow')
    from mlkit.integrations import mlflow_packaging as mp
    assert runtime_predictor.MLFLOW_PYFUNC_FORMAT == mp.FORMAT
    assert runtime_predictor.MLFLOW_PYFUNC_FILES == mp.PACKAGE_FILES
    assert runtime_predictor.MLFLOW_PYFUNC_BUNDLE == mp.EMBEDDED_BUNDLE
    assert runtime_predictor.MLFLOW_PYFUNC_FILES[-1] == mp.DESCRIPTOR_FILE


@needs_mlflow
def test_a_package_of_the_previous_packager_version_is_refused(tmp_path):
    """Version 3 changes MLmodel: a version-2 package is refused with
    schema_version_unsupported (capture again), never verified against the new rules."""
    mp, dest, _ = r3._workshop(tmp_path)
    pkg = dest / PKG
    doc = json.loads((pkg / mp.DESCRIPTOR_FILE).read_bytes())
    doc['extensions']['hypotrail.packager_version'] = '2'
    (pkg / mp.DESCRIPTOR_FILE).write_bytes(canonical.dumps(doc) + b'\n')
    r2._redescribe_mlflow_package(dest)
    r3._packaging_refused(mp.ArtifactPackager().verify, dest, pkg,
                          code='schema_version_unsupported')


# --- R4-A2: the package the bundle holds is the one the capture recorded -------------------------

def _remake_package(dest: Path, mlflow_version: str = '3.0.0') -> None:
    """Re-make the package consistently with another recorded MLflow version, as an attacker
    who knows every rule would: the descriptor's environment, the environment files and
    MLmodel regenerated by the packager's own functions, the package re-described with a
    recomputed artifact id. Every check of the bundle and of the package passes; only the
    artifact id differs from the one the capture recorded."""
    from mlkit.integrations import mlflow_packaging as mp
    pkg = dest / PKG
    doc = json.loads((pkg / mp.DESCRIPTOR_FILE).read_bytes())
    manifest = json.loads((dest / 'predictor.json').read_bytes())
    environment = mp.ArtifactPackager().environment(manifest, mlflow_version)
    doc['environment'] = environment
    (pkg / mp.DESCRIPTOR_FILE).write_bytes(canonical.dumps(doc) + b'\n')
    mp.write_environment_files(pkg, environment)
    (pkg / 'MLmodel').write_bytes(mp.mlmodel_bytes(doc['signature'], environment))
    r2._redescribe_mlflow_package(dest)


def _recipe_and_contract(dest: Path):
    return (json.loads((dest / 'recipe.json').read_bytes()),
            json.loads((dest / 'data_contract.json').read_bytes()))


@needs_mlflow
def test_export_refuses_a_package_other_than_the_captured_one(tmp_path, monkeypatch):
    """Reviewer probe: the recorded artifact id was never compared. A package re-made
    consistently verifies everywhere; the export, given what the capture recorded, refuses
    it before verifying or loading any package."""
    from mlkit.exporters.azureml import artifact
    from mlkit.exporters.azureml.errors import ExportError
    mp, dest, d = r3._workshop(tmp_path)
    recorded = [{'format': p.format, 'artifact_id': p.artifact_id} for p in d.packages]
    recipe, contract = _recipe_and_contract(dest)
    assert artifact.verify_predictor(dest, recipe, contract, recorded_packages=recorded)[
        'artifact_status'] == 'packaged'
    _remake_package(dest)
    verify_bundle(dest)
    assert mp.ArtifactPackager().verify(dest, dest / PKG).status == 'passed'
    held = json.loads((dest / 'predictor_bundle.json').read_bytes())['optional_packages'][0]
    assert held['artifact_id'] != recorded[0]['artifact_id']
    verified = []
    monkeypatch.setattr(mp.ArtifactPackager, 'verify',
                        lambda self, *a, **k: verified.append(a))
    with pytest.raises(ExportError) as err:
        artifact.verify_predictor(dest, recipe, contract, recorded_packages=recorded)
    e = err.value
    assert e.code == 'artifact_integrity_failed' and e.path == 'predictor.packages'
    assert e.details['reason'] == 'package_not_recorded'
    assert e.details['changed'] == ['mlflow_pyfunc']
    assert e.details['missing'] == e.details['unrecorded'] == []
    assert 'predictor.capture' in e.remediation and 'copy you trust' in e.remediation
    assert verified == []


@needs_mlflow
@pytest.mark.parametrize('recorded,key', [([], 'unrecorded'),
                                          ([{'format': 'mlflow_pyfunc', 'artifact_id': None},
                                            {'format': 'onnx', 'artifact_id': 'a' * 64}],
                                           'missing')])
def test_export_refuses_a_package_missing_or_not_recorded(tmp_path, recorded, key):
    from mlkit.exporters.azureml import artifact
    from mlkit.exporters.azureml.errors import ExportError
    mp, dest, _ = r3._workshop(tmp_path)
    recipe, contract = _recipe_and_contract(dest)
    with pytest.raises(ExportError) as err:
        artifact.verify_predictor(dest, recipe, contract, recorded_packages=recorded)
    assert err.value.details['reason'] == 'package_not_recorded'
    assert err.value.details[key] == (['mlflow_pyfunc'] if key == 'unrecorded' else ['onnx'])


def test_a_base_capture_recorded_with_a_package_is_refused(tmp_path):
    from mlkit.exporters.azureml import artifact
    from mlkit.exporters.azureml.errors import ExportError
    dest = tmp_path / 'b'
    capture_predictor(r2._fitted(), None, r2._parity(), dest, None, code_fingerprint=r2.FP)
    recipe, contract = _recipe_and_contract(dest)
    assert artifact.verify_predictor(dest, recipe, contract,
                                     recorded_packages=[])['artifact_status'] == 'captured'
    with pytest.raises(ExportError) as err:
        artifact.verify_predictor(dest, recipe, contract, recorded_packages=[
            {'format': 'mlflow_pyfunc', 'artifact_id': 'a' * 64}])
    assert err.value.details['missing'] == ['mlflow_pyfunc']


def test_the_recorded_packages_come_from_the_export_source():
    from mlkit.exporters.azureml.artifact import recorded_packages
    ids = [{'format': 'mlflow_pyfunc', 'artifact_id': 'a' * 64}]
    assert recorded_packages({'extensions': {'hypotrail.packages': ids},
                              'predictor': {'packages': ['mlflow_pyfunc']}}) == ids
    assert recorded_packages({'predictor': {'packages': ['mlflow_pyfunc']}}) == \
        [{'format': 'mlflow_pyfunc', 'artifact_id': None}]
    assert recorded_packages({'predictor': {'status': 'captured'}}) is None


@needs_mlflow
def test_a_re_made_package_in_a_study_refuses_the_export_and_the_final_test(tmp_path):
    """Engine path: a workshop capture in a study, its package re-made consistently after
    the capture. read_export_source states the recorded artifact id, so the export refuses
    the bundle; the final-test opening refuses it too (capture_loadable, an actionable junior
    message naming the package), nothing is opened and no final-test row is read."""
    import test_capture_final as tcf
    from mlkit.contracts import capture as cap
    from mlkit.contracts.export_source import read_export_source
    from mlkit.exporters.azureml import artifact, snapshot
    from mlkit.exporters.azureml.errors import ExportError
    from mlkit.exporters.azureml import layout
    from mlkit.study import read, state as st
    flow = tcf._chosen(tmp_path, 'regression')
    v = flow.run('predictor.capture', '--profile', 'workshop')['values']
    bundle = tcf._home(flow) / v['bundle']
    source = read_export_source(Path(flow.study), int(flow.rev()))
    assert source.extensions['hypotrail.packages'] == v['packages']
    assert artifact.recorded_packages(source) == v['packages']
    _remake_package(bundle)
    verify_bundle(bundle)
    capabilities = layout.load('team-azureml-v1').document['capabilities']
    with pytest.raises(ExportError) as err:
        snapshot.build(source, template_capabilities=capabilities,
                       verify_predictor=artifact.verify_predictor)
    assert err.value.code == 'artifact_integrity_failed'
    assert err.value.details['reason'] == 'package_not_recorded'
    assert err.value.details['changed'] == ['mlflow_pyfunc']
    out = tcf._open(flow, expect=2)
    assert 'result' not in out
    error = out['error']
    assert error['code'] == 'precondition_missing'
    item = next(x for x in error['details']['missing'] if x['requirement'] == 'capture_loadable')
    assert item['slot'] == cap.CAPTURE
    assert item['contract_code'] == 'artifact_integrity_failed'
    assert 'mlflow_pyfunc' in item['junior_message']
    assert 'model package' in item['junior_message']
    assert 'predictor.capture again' in item['junior_message']
    assert 'No final-test row was read' in error['details']['junior_message']
    state = read.open(flow.study).state
    assert not st.final_test_opened(state)


def test_package_mismatch_compares_formats_and_ids():
    from types import SimpleNamespace
    from mlkit.contracts import capture as cap
    bundle = SimpleNamespace(optional_packages=[SimpleNamespace(format='mlflow_pyfunc',
                                                                artifact_id='a' * 64)])
    assert cap.package_mismatch(bundle, None) is None
    assert cap.package_mismatch(bundle, [{'format': 'mlflow_pyfunc',
                                          'artifact_id': 'a' * 64}]) is None
    assert cap.package_mismatch(bundle, [{'format': 'mlflow_pyfunc', 'artifact_id': 'b' * 64}]
                                ) == {'missing': [], 'unrecorded': [], 'changed': ['mlflow_pyfunc']}
    assert cap.package_mismatch(bundle, []) == {'missing': [], 'unrecorded': ['mlflow_pyfunc'],
                                                'changed': []}
    assert cap.package_mismatch(SimpleNamespace(optional_packages=[]), [
        {'format': 'mlflow_pyfunc', 'artifact_id': 'a' * 64}])['missing'] == ['mlflow_pyfunc']
