"""The MLflow packager (contract v1 §6, L-19, M-07; AC07, AC19).

The native bundles here come from the PRIVATE TEST DOUBLE of ``hypotrail_runtime``; the
same tests run against chantier A's runtime with ``HYPOTRAIL_EXPORT_REAL_RUNTIME=1``.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from export_env import needs_mlflow, project_env
from mlkit.integrations import mlflow_packaging as mp

import azureml_study as fx

pytestmark = needs_mlflow


@pytest.fixture
def native(material, tmp_path):
    target = tmp_path / 'native'
    shutil.copytree(material['native_bundle'], target)
    return target


def test_package_signature_and_parity(native, runtime, tmp_path):
    descriptor = mp.ArtifactPackager(runtime).package(native, tmp_path / 'package')
    assert descriptor.format == 'mlflow_pyfunc' and descriptor.parity_result['status'] == 'passed'
    inputs = {c['name']: (c['type'], c['required']) for c in descriptor.signature['inputs']}
    assert list(inputs) == fx.FEATURES
    assert inputs['origin'] == ('long', True) and inputs['horsepower'] == ('double', False)
    assert [c['name'] for c in descriptor.signature['outputs']] == ['prediction']
    assert descriptor.signature['unit'] == 'mpg'
    files = {f['relative_path'] for f in descriptor.files}
    assert {'MLmodel', 'hypotrail_pyfunc.py', 'requirements.txt'} <= files
    assert any(f.startswith('artifacts/native_bundle/') for f in files)
    assert not any('__pycache__' in f for f in files)
    written = json.loads((tmp_path / 'package' / mp.DESCRIPTOR_FILE).read_text())
    assert written['artifact_id'] == descriptor.artifact_id
    requirements = (tmp_path / 'package' / 'requirements.txt').read_text()
    assert 'scikit-learn==' in requirements and 'mlflow-skinny==' in requirements


def test_packaging_never_fits(native, runtime, tmp_path, monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError('the packager must not fit')
    monkeypatch.setattr(runtime, 'fit_predictor', refuse)
    mp.ArtifactPackager(runtime).package(native, tmp_path / 'package')


def test_the_package_holds_no_local_path(native, runtime, tmp_path):
    mp.ArtifactPackager(runtime).package(native, tmp_path / 'package')
    for path in (tmp_path / 'package').rglob('*'):
        if path.is_file():
            assert str(tmp_path).encode() not in path.read_bytes(), path


def test_verify_detects_a_changed_package(native, runtime, tmp_path):
    packager = mp.ArtifactPackager(runtime)
    packager.package(native, tmp_path / 'package')
    assert packager.verify(native, tmp_path / 'package').status == 'passed'
    assert packager.verify(native, tmp_path / 'package').status == 'passed'
    (tmp_path / 'package' / 'requirements.txt').write_text('changed\n')
    result = packager.verify(native, tmp_path / 'package')
    assert result.status == 'failed' and result.reason == 'package_files_changed'


def test_a_parity_failure_writes_no_package(native, runtime, tmp_path):
    class Drifting:
        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def load_predictor(self, bundle_dir):
            predictor = self._inner.load_predictor(bundle_dir)

            class Wrapped:
                def predict(self, frame):
                    batch = predictor.predict(frame)
                    batch.values = batch.values + 1e-6
                    return batch
            return Wrapped()
    with pytest.raises(mp.PackagingError) as error:
        mp.ArtifactPackager(Drifting(runtime)).package(native, tmp_path / 'package')
    assert error.value.code == 'artifact_integrity_failed'
    assert not (tmp_path / 'package').exists()
    assert not [p for p in tmp_path.iterdir() if p.name.startswith('.package.')]


def test_a_non_empty_destination_is_refused(native, runtime, tmp_path):
    (tmp_path / 'package').mkdir()
    (tmp_path / 'package' / 'x').write_text('keep')
    with pytest.raises(mp.PackagingError) as error:
        mp.ArtifactPackager(runtime).package(native, tmp_path / 'package')
    assert error.value.code == 'destination_not_empty'


def test_the_hook_inside_capture_packages_before_any_check(material):
    bundle = json.loads((material['bundle'] / 'predictor_bundle.json').read_text())
    assert bundle['optional_packages'][0]['format'] == 'mlflow_pyfunc'
    package = material['bundle'] / bundle['optional_packages'][0]['relative_path']
    copy = json.loads((package / 'artifacts' / 'native_bundle' / 'predictor_bundle.json').read_text())
    assert copy['optional_packages'] == [], 'a package never contains itself'


def test_pyfunc_loads_in_a_clean_process_after_a_move(native, runtime, tmp_path):
    """AC19/AC22: moved elsewhere, the package loads with mlflow.pyfunc in a fresh process
    (isolated mode, no repository on its path) and reproduces the native predictions."""
    mp.ArtifactPackager(runtime).package(native, tmp_path / 'package')
    moved = tmp_path / 'elsewhere' / 'model'
    moved.parent.mkdir()
    shutil.move(str(tmp_path / 'package'), moved)
    shutil.rmtree(native)
    script = (
        'import sys, json, pandas as pd, mlflow.pyfunc\n'
        f'sys.path.insert(0, {str(project_env().get("PYTHONPATH", ""))!r})\n'
        'model = mlflow.pyfunc.load_model(sys.argv[1])\n'
        'features = pd.read_csv(sys.argv[1] + "/artifacts/native_bundle/parity/features.csv")\n'
        'print(json.dumps(model.predict(features)["prediction"].tolist()))\n')
    result = subprocess.run([sys.executable, '-I', '-c', script, str(moved)], cwd=tmp_path,
                            capture_output=True, text=True, env=project_env(), check=False)
    assert result.returncode == 0, result.stderr[-2000:]
    predicted = json.loads(result.stdout.strip().splitlines()[-1])
    expected = mp.read_table(moved / 'artifacts/native_bundle/parity/expected_outputs.csv')
    assert mp.compare(__import__('pandas').DataFrame({'prediction': predicted}), expected,
                      1e-10, 1e-12)['equal']


def test_the_profile_hook(monkeypatch):
    assert mp.packager_for('base') is None
    assert isinstance(mp.packager_for('atelier'), mp.ArtifactPackager)
    with pytest.raises(mp.PackagingError) as error:
        mp.packager_for('everything')
    assert error.value.code == 'capability_not_supported'
    monkeypatch.setitem(sys.modules, 'mlflow', None)
    with pytest.raises(mp.PackagingError) as error:
        mp.packager_for('atelier')
    assert error.value.code == 'optional_dependency_missing'
