"""PRIVATE TEST DOUBLE of chantier A's ``hypotrail_runtime`` (contract v1 §5, §6).

It exists only so chantier B can test the Azure ML export, the MLflow packager and the
exported project before chantier A's runtime is merged. It is never installed, never on a
production import path (tests prepend its folder to ``sys.path`` explicitly), and its fits
prove nothing about the engine: after the merge, the same suites must run against the real
runtime (``docs/handoff/AZUREML-EXPORT-V1.md``, deferred tests).

It implements the contract v1 boundary for one family, ``linear`` regression: median
imputation and standardisation of numeric features, most-frequent imputation and one-hot
encoding of categorical ones, all learnt on the training rows, then least squares. The
bundle layout (``predictor_bundle.json`` and its manifests) follows §5; its file names are
this double's choice where contract v1 leaves them open.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

__version__ = '0.0.0+testdouble'
API_VERSION = '1'
DISTRIBUTION = 'hypotrail-runtime-testdouble'
BUNDLE_DOCUMENT = 'predictor_bundle.json'
FAMILIES = ('linear',)
TOLERANCE = {'rtol': 1e-10, 'atol': 1e-12}


class RuntimeContractError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(f'{code}: {message}')
        self.code = code


def _canonical(value) -> bytes:
    def norm(v):
        if isinstance(v, dict):
            return {k: norm(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [norm(x) for x in v]
        if isinstance(v, float):
            if not math.isfinite(v):
                raise RuntimeContractError('contract_invalid', 'non-finite number')
            return 0.0 if v == 0 else v
        return v
    return json.dumps(norm(value), sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8')


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_file(path: Path) -> str:
    return _sha(path.read_bytes())


def validate_recipe(document):
    if document.get('schema_version') != 'hypotrail.model_recipe/1':
        raise RuntimeContractError('schema_version_unsupported', 'not hypotrail.model_recipe/1')
    if document.get('family') not in FAMILIES:
        raise RuntimeContractError('capability_not_supported', f'family {document.get("family")}')
    return dict(document)


def validate_data_contract(document):
    if document.get('schema_version') != 'hypotrail.data_contract/1':
        raise RuntimeContractError('schema_version_unsupported', 'not hypotrail.data_contract/1')
    return dict(document)


@dataclass
class PredictionBatch:
    row_order: list
    kind: str
    values: object
    columns: list
    unit: object
    positive_label: object


def _categorical(recipe) -> list:
    return [f for f in recipe['features'] if recipe['feature_types'][f]['semantic'] == 'categorical']


def _features(frame, recipe):
    import pandas as pd
    missing = [f for f in recipe['features'] if f not in frame.columns]
    if missing:
        raise RuntimeContractError('contract_invalid', f'missing feature columns {missing}')
    out = pd.DataFrame(index=range(len(frame)))
    for name in recipe['features']:
        column = frame[name].reset_index(drop=True)
        if recipe['feature_types'][name]['semantic'] == 'categorical':
            out[name] = column.astype('string').astype(object).where(column.notna(), None)
        else:
            out[name] = pd.to_numeric(column, errors='raise').astype('float64')
    return out


class Predictor:
    def __init__(self, pipeline, recipe):
        self._pipeline, self._recipe = pipeline, recipe

    def predict(self, raw_features):
        import numpy as np
        values = np.asarray(self._pipeline.predict(_features(raw_features, self._recipe)),
                            dtype='float64')
        output = self._recipe['output_contract']
        return PredictionBatch(list(range(len(values))), output['kind'], values,
                               list(output['columns']), output.get('unit'),
                               output.get('positive_label'))


@dataclass
class FittedPredictor:
    predictor: Predictor
    recipe: dict
    data_contract: dict
    training_scope: dict


def fit_predictor(recipe, data_contract, training_frame, training_scope):
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LinearRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler
    recipe = validate_recipe(recipe)
    categorical = _categorical(recipe)
    numeric = [f for f in recipe['features'] if f not in categorical]
    pipeline = Pipeline([
        ('prepare', ColumnTransformer([
            ('numeric', Pipeline([('impute', SimpleImputer(strategy='median')),
                                  ('scale', StandardScaler())]), numeric),
            ('categorical', Pipeline([('impute', SimpleImputer(strategy='most_frequent')),
                                      ('encode', OneHotEncoder(handle_unknown='ignore'))]),
             categorical)])),
        ('model', LinearRegression(**recipe['parameters']))])
    target = recipe['target']['name']
    pipeline.fit(_features(training_frame, recipe), training_frame[target].astype('float64'))
    return FittedPredictor(Predictor(pipeline, recipe), recipe, dict(data_contract),
                           dict(training_scope))


def _versions() -> list:
    from importlib.metadata import version
    return [{'distribution': d, 'version': version(d)}
            for d in ('joblib', 'numpy', 'pandas', 'scikit-learn', 'scipy')]


def _wheel(folder: Path) -> Path:
    """A minimal wheel of this double, so the export has a runtime wheel to copy."""
    import zipfile
    name = f'hypotrail_runtime_testdouble-{__version__.replace("+", "_")}-py3-none-any.whl'
    path = folder / name
    source = Path(__file__).read_bytes()
    info = 'hypotrail_runtime_testdouble-0.0.0.dist-info'
    with zipfile.ZipFile(path, 'w') as archive:
        for entry, data in (('hypotrail_runtime/__init__.py', source),
                            (f'{info}/METADATA', b'Metadata-Version: 2.1\nName: '
                             b'hypotrail-runtime-testdouble\nVersion: 0.0.0\n'),
                            (f'{info}/WHEEL', b'Wheel-Version: 1.0\nRoot-Is-Purelib: true\n'
                             b'Tag: py3-none-any\n'),
                            (f'{info}/RECORD', b'')):
            item = zipfile.ZipInfo(entry, date_time=(1980, 1, 1, 0, 0, 0))
            archive.writestr(item, data)
    return path


def capture_predictor(fitted, context, parity_features, destination, packager=None):
    import joblib
    import pandas as pd
    destination = Path(destination)
    if destination.exists() and any(destination.iterdir()):
        raise RuntimeContractError('destination_not_empty', str(destination))
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.capture-', dir=destination.parent))
    try:
        (staging / 'payload').mkdir()
        (staging / 'parity').mkdir()
        (staging / 'environment').mkdir()
        joblib.dump(fitted.predictor._pipeline, staging / 'payload' / 'pipeline.joblib')
        (staging / 'recipe.json').write_bytes(json.dumps(fitted.recipe, indent=2).encode())
        (staging / 'data_contract.json').write_bytes(
            json.dumps(fitted.data_contract, indent=2).encode())
        features = pd.DataFrame(parity_features).reset_index(drop=True)
        features.to_csv(staging / 'parity' / 'features.csv', index=False)
        batch = fitted.predictor.predict(features)
        pd.DataFrame({batch.columns[0]: batch.values}).to_csv(
            staging / 'parity' / 'expected_outputs.csv', index=False, float_format='%.17g')
        versions = _versions()
        lock = ''.join(f'{v["distribution"]}=={v["version"]}\n' for v in versions)
        (staging / 'environment' / 'requirements.lock').write_text(lock)
        wheel = _wheel(staging / 'environment')
        payload = staging / 'payload' / 'pipeline.joblib'
        manifest = {
            'schema_version': 'hypotrail.predictor_artifact/1',
            'recipe_sha256': _sha(_canonical(fitted.recipe)),
            'data_contract_sha256': _sha(_canonical(fitted.data_contract)),
            'input_contract_sha256': _sha(_canonical(fitted.data_contract.get(
                'inference_policy'))),
            'output_contract': fitted.recipe['output_contract'],
            'native_format': 'joblib_sklearn_pipeline',
            'payload_files': [{'relative_path': 'payload/pipeline.joblib',
                               'size_bytes': payload.stat().st_size,
                               'sha256': _sha_file(payload)}],
            'runtime': {'api_version': API_VERSION, 'distribution': DISTRIBUTION,
                        'version': '0.0.0', 'wheel_relative_path': f'environment/{wheel.name}',
                        'wheel_sha256': _sha_file(wheel)},
            'environment': {'python': platform.python_version(), 'platform': sys.platform,
                            'semantic_dependencies': versions,
                            'lock_relative_path': 'environment/requirements.lock',
                            'lock_sha256': _sha(lock.encode())},
            'training_scope': fitted.training_scope,
            'code_fingerprint': context.get('code_fingerprint') if isinstance(context, dict)
            else None,
        }
        manifest['predictor_id'] = _sha(_canonical(manifest))
        (staging / 'predictor.json').write_bytes(json.dumps(manifest, indent=2).encode())
        bundle = {
            'schema_version': 'hypotrail.predictor_bundle/1',
            'recipe_path': 'recipe.json', 'data_contract_path': 'data_contract.json',
            'predictor_manifest_path': 'predictor.json',
            'parity': {'features_path': 'parity/features.csv',
                       'expected_outputs_path': 'parity/expected_outputs.csv',
                       'sha256s': {'features': _sha_file(staging / 'parity' / 'features.csv'),
                                   'expected_outputs': _sha_file(
                                       staging / 'parity' / 'expected_outputs.csv')},
                       'origin': 'authorized_development', 'tolerance': dict(TOLERANCE)},
            'optional_packages': [], 'evidence_binding_path': None}
        (staging / BUNDLE_DOCUMENT).write_bytes(json.dumps(bundle, indent=2).encode())
        if packager is not None:
            package_dir = staging / 'packages' / 'mlflow_pyfunc'
            descriptor = packager.package(staging, package_dir)
            bundle['optional_packages'] = [{
                'format': descriptor.format, 'artifact_id': descriptor.artifact_id,
                'relative_path': 'packages/mlflow_pyfunc',
                'manifest_sha256': _sha_file(package_dir / 'hypotrail-package.json')}]
            (staging / BUNDLE_DOCUMENT).write_bytes(json.dumps(bundle, indent=2).encode())
        if destination.exists():
            destination.rmdir()
        os.rename(staging, destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return SimpleNamespace(bundle_dir=destination, predictor_id=manifest['predictor_id'],
                           document=bundle)


def _read(bundle_dir: Path, name: str) -> dict:
    return json.loads((bundle_dir / name).read_text())


def verify_bundle(bundle_dir):
    bundle_dir = Path(bundle_dir)
    for path in bundle_dir.rglob('*'):
        if path.is_symlink():
            raise RuntimeContractError('artifact_integrity_failed', f'symlink {path}')
    bundle = _read(bundle_dir, BUNDLE_DOCUMENT)
    if bundle.get('schema_version') != 'hypotrail.predictor_bundle/1':
        raise RuntimeContractError('schema_version_unsupported', 'bundle')
    manifest = _read(bundle_dir, bundle['predictor_manifest_path'])
    body = {k: v for k, v in manifest.items() if k != 'predictor_id'}
    if _sha(_canonical(body)) != manifest['predictor_id']:
        raise RuntimeContractError('artifact_integrity_failed', 'predictor_id')
    for item in manifest['payload_files']:
        path = bundle_dir / item['relative_path']
        if not path.is_file() or _sha_file(path) != item['sha256'] or \
                path.stat().st_size != item['size_bytes']:
            raise RuntimeContractError('artifact_integrity_failed', item['relative_path'])
    if _sha(_canonical(_read(bundle_dir, bundle['recipe_path']))) != manifest['recipe_sha256']:
        raise RuntimeContractError('artifact_integrity_failed', 'recipe')
    for key, rel in (('features', bundle['parity']['features_path']),
                     ('expected_outputs', bundle['parity']['expected_outputs_path'])):
        if _sha_file(bundle_dir / rel) != bundle['parity']['sha256s'][key]:
            raise RuntimeContractError('artifact_integrity_failed', rel)
    return SimpleNamespace(bundle_dir=bundle_dir, predictor_id=manifest['predictor_id'],
                           document=bundle, predictor=manifest)


def load_predictor(bundle_dir):
    import joblib
    descriptor = verify_bundle(bundle_dir)
    recipe = _read(Path(bundle_dir), descriptor.document['recipe_path'])
    # A trusted local test artefact; a hash does not make a third-party pickle safe.
    pipeline = joblib.load(Path(bundle_dir) / 'payload' / 'pipeline.joblib')
    return Predictor(pipeline, recipe)
