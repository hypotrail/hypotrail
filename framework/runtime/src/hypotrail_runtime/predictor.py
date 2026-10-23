"""Fit, capture, verify and load a complete predictor (CONTRAT-COMMUN-v1 §5–§6, spec L-08–L-10).

* :func:`fit_predictor` fits the recipe's complete pipeline on the rows it is given (the
  caller authorises them; this function decides no protocol and reads no file).
* :func:`capture_predictor` writes a bundle without refitting: the native payload, the
  recipe, the data contract, the predictor manifest (its id is its content digest), the
  runtime wheel, an environment lock, the parity rows and their expected outputs, and the
  optional packages of an injected packager. It is prepared in a temporary sibling
  directory, reloaded and checked for parity there, then renamed atomically into place.
* :func:`verify_bundle` checks paths, sizes, digests, ids, versions and the environment
  before anything is unpickled; :func:`load_predictor` loads only a verified bundle under
  an explicitly trusted root (a digest does not make a third-party pickle safe).
* :meth:`Predictor.predict` checks the raw features against the data contract and returns
  a :class:`PredictionBatch` in input order: the score of the named positive class, or a
  prediction in the target unit.
"""
from __future__ import annotations

import json
import os
import pickle
import platform
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from . import RUNTIME_API_VERSION, DISTRIBUTION, __version__, canonical, families, inference
from .contracts import (ComputationContext, DataContract, ModelRecipe, PackageDescriptor,
                        ParityResult, PredictorArtifact, PredictorBundle, TrainingScope,
                        Tolerance, parse, validate_data_contract, validate_recipe)
from .errors import ContractError
from .preprocess import build_pipeline

NATIVE_FORMAT = 'sklearn_pickle/1'
PAYLOAD = 'payload/model.pkl'
RECIPE = 'recipe.json'
DATA_CONTRACT = 'data_contract.json'
MANIFEST = 'predictor.json'
BUNDLE = 'bundle.json'
CONTEXT = 'computation_context.json'
LOCK = 'environment/requirements.lock'
PARITY_FEATURES = 'parity/features.json'
PARITY_EXPECTED = 'parity/expected_outputs.json'
EVIDENCE_BINDING = 'evidence_binding.json'
PACKAGES_DIR = 'packages'
# Spec L-10: proposed float64 tolerances; classes and selections must match exactly. They
# are never relaxed automatically.
DEFAULT_TOLERANCE = {'rtol': 1e-10, 'atol': 1e-12}
SEMANTIC_DISTRIBUTIONS = ('numpy', 'pandas', 'scikit-learn', 'scipy')
TRUSTED_ROOTS_ENV = 'HYPOTRAIL_RUNTIME_TRUSTED_ROOTS'
PARITY_FRAME = 'hypotrail.parity_frame/1'


# --- outputs ---------------------------------------------------------------------------------

@dataclass(frozen=True)
class PredictionBatch:
    """Outputs in input order. ``values`` is the positive-class score (``binary_score``) or
    the prediction (``regression_point``); a decision rule or an interval is a separate
    capability."""
    row_order: list[int]
    kind: str
    values: np.ndarray
    columns: list[str]
    unit: str | None
    positive_label: Any
    conversions: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {'row_order': list(self.row_order), 'kind': self.kind,
                'values': [float(v) for v in self.values], 'columns': list(self.columns),
                'unit': self.unit, 'positive_label': self.positive_label,
                'conversions': list(self.conversions)}


def positive_indicator(series: pd.Series, label: Any) -> np.ndarray:
    """1 where the target is the positive label (the engine's ``activities.positive``)."""
    from pandas.api.types import is_numeric_dtype
    if isinstance(label, (int, float)) and not isinstance(label, bool) \
            and is_numeric_dtype(series):
        return (series == label).astype(int).to_numpy()
    return (series.astype(str) == str(label)).astype(int).to_numpy()


class _Model:
    """Shared prediction logic of a fitted and of a loaded predictor."""

    recipe: ModelRecipe
    data_contract: DataContract
    pipeline: Any

    def predict(self, raw_features: pd.DataFrame) -> PredictionBatch:
        view, conversions = inference.check_frame(self.data_contract, raw_features,
                                                  features=list(self.recipe.features))
        out = self.recipe.output_contract
        n = len(view)
        if n == 0:
            values = np.zeros(0, dtype=float)
        elif self.recipe.task == 'binary':
            classes = list(self.pipeline.classes_)
            if 1 not in classes:
                raise ContractError('backend_failed', 'The fitted model has no positive class.',
                                    remediation='Refit on rows holding both classes.')
            values = np.asarray(self.pipeline.predict_proba(view)[:, classes.index(1)],
                                dtype=float)
        else:
            values = np.asarray(self.pipeline.predict(view), dtype=float)
        return PredictionBatch(row_order=list(range(n)), kind=out.kind, values=values,
                               columns=list(out.columns), unit=out.unit,
                               positive_label=out.positive_label, conversions=conversions)


@dataclass
class FittedPredictor(_Model):
    recipe: ModelRecipe
    data_contract: DataContract
    pipeline: Any
    training_scope: TrainingScope
    n_train: int

    def learnt_state(self) -> dict:
        return self.pipeline.named_steps['prepare'].learnt_state()


@dataclass
class Predictor(_Model):
    recipe: ModelRecipe
    data_contract: DataContract
    pipeline: Any
    manifest: PredictorArtifact
    bundle: PredictorBundle
    path: Path

    @property
    def predictor_id(self) -> str:
        return self.manifest.predictor_id


@dataclass(frozen=True)
class BundleDescriptor:
    path: Path
    bundle: PredictorBundle
    manifest: PredictorArtifact
    recipe: ModelRecipe
    data_contract: DataContract
    parity: ParityResult | None = None
    packages: tuple[PackageDescriptor, ...] = ()

    @property
    def predictor_id(self) -> str:
        return self.bundle.predictor_id


# --- fit -------------------------------------------------------------------------------------

def _as_recipe(recipe) -> ModelRecipe:
    if isinstance(recipe, ModelRecipe):
        return validate_recipe(recipe.model_dump(mode='json'))
    return validate_recipe(recipe)


def _as_contract(contract) -> DataContract:
    if isinstance(contract, DataContract):
        return validate_data_contract(contract.model_dump(mode='json'))
    return validate_data_contract(contract)


def fit_predictor(recipe, data_contract, training_frame: pd.DataFrame,
                  training_scope) -> FittedPredictor:
    """Fit the complete pipeline on ``training_frame`` (features and target) only."""
    recipe, contract = _as_recipe(recipe), _as_contract(data_contract)
    families.require_qualified(recipe.family)
    scope = training_scope if isinstance(training_scope, TrainingScope) \
        else TrainingScope.model_validate(dict(training_scope), strict=True)
    for name in recipe.features:
        if contract.column(name) is None or contract.column(name).role != 'feature':
            raise ContractError('contract_invalid', f'{name!r} is not a feature of the data '
                                'contract.', path=f'features/{name}',
                                remediation='Use the data contract of the recipe.')
    if not isinstance(training_frame, pd.DataFrame) or not len(training_frame):
        raise ContractError('contract_invalid', 'The training rows are an empty set.',
                            path='training_frame', remediation='Pass the authorised rows.')
    target = recipe.target.name
    if target not in training_frame.columns:
        raise ContractError('contract_invalid', f'The training rows have no target {target!r}.',
                            path='training_frame', remediation='Include the target column.')
    view, _ = inference.check_frame(contract, training_frame.drop(columns=[target]),
                                    features=list(recipe.features), purpose='training')
    if recipe.task == 'binary':
        y = positive_indicator(training_frame[target], recipe.target.positive_label)
        if y.min() == y.max():
            raise ContractError('contract_invalid', 'The training rows hold one class only.',
                                path='training_frame', remediation='Fit on both classes.')
    else:
        y_series = training_frame[target]
        if y_series.isna().any():
            raise ContractError('contract_invalid', 'Training rows without a target value are '
                                'neither dropped nor imputed.', path=f'training_frame/{target}',
                                remediation='Exclude them by a declared rule first.')
        y = y_series.to_numpy(dtype=float)
    pipeline = build_pipeline(recipe)
    try:
        pipeline.fit(view, y)
    except ContractError:
        raise
    except Exception as exc:     # a backend failure is named, never swallowed
        raise ContractError('backend_failed', f'scikit-learn failed to fit: '
                            f'{type(exc).__name__}: {exc}',
                            remediation='Check the recipe and the training rows.') from exc
    return FittedPredictor(recipe=recipe, data_contract=contract, pipeline=pipeline,
                           training_scope=scope, n_train=len(view))


# --- parity frames ---------------------------------------------------------------------------

def parity_frame_document(frame: pd.DataFrame, contract: DataContract,
                          features: Sequence[str]) -> dict:
    columns = []
    for name in features:
        spec = contract.column(name)
        values = [None if (v is None or (isinstance(v, float) and v != v)) else
                  (v.item() if hasattr(v, 'item') else v) for v in frame[name].tolist()]
        columns.append({'name': name, 'physical_type': spec.physical_type, 'values': values})
    return {'schema_version': PARITY_FRAME, 'n_rows': int(len(frame)), 'columns': columns}


def frame_from_document(doc: Mapping) -> pd.DataFrame:
    if doc.get('schema_version') != PARITY_FRAME:
        raise ContractError('contract_invalid', 'Not a parity frame.', path='schema_version',
                            remediation=f'Send a {PARITY_FRAME} document.')
    data = {}
    for col in doc['columns']:
        values, kind = col['values'], col['physical_type']
        if kind == 'float64':
            data[col['name']] = pd.Series([np.nan if v is None else v for v in values],
                                          dtype='float64')
        elif kind == 'int64':
            data[col['name']] = pd.Series(values, dtype='int64')
        elif kind == 'bool':
            data[col['name']] = pd.Series(values, dtype='bool')
        else:
            data[col['name']] = pd.Series(values, dtype=object)
    return pd.DataFrame(data)


def compare(expected: np.ndarray, actual: np.ndarray, tolerance: Mapping,
            exact: bool = False) -> ParityResult:
    expected, actual = np.asarray(expected, dtype=float), np.asarray(actual, dtype=float)
    tol = Tolerance(rtol=float(tolerance['rtol']), atol=float(tolerance['atol']),
                    exact=list(tolerance.get('exact') or []))
    if expected.shape != actual.shape:
        return ParityResult(schema_version='hypotrail.parity_result/1', status='failed',
                            n_rows=int(len(actual)), max_abs_diff=None, max_rel_diff=None,
                            exact_mismatches=0, tolerance=tol,
                            reason='the outputs do not have the same number of rows')
    if not len(expected):
        return ParityResult(schema_version='hypotrail.parity_result/1', status='ok', n_rows=0,
                            max_abs_diff=None, max_rel_diff=None, exact_mismatches=0,
                            tolerance=tol, reason=None)
    if not (np.isfinite(expected).all() and np.isfinite(actual).all()):
        return ParityResult(schema_version='hypotrail.parity_result/1', status='failed',
                            n_rows=int(len(actual)), max_abs_diff=None, max_rel_diff=None,
                            exact_mismatches=0, tolerance=tol, reason='non-finite output')
    diff = np.abs(expected - actual)
    rel = diff / np.maximum(np.abs(expected), np.finfo(float).tiny)
    mismatches = int((expected != actual).sum()) if exact else 0
    ok = bool(np.all(diff <= tol.atol + tol.rtol * np.abs(expected))) and mismatches == 0
    return ParityResult(schema_version='hypotrail.parity_result/1',
                        status='ok' if ok else 'failed', n_rows=int(len(actual)),
                        max_abs_diff=float(diff.max()), max_rel_diff=float(rel.max()),
                        exact_mismatches=mismatches, tolerance=tol,
                        reason=None if ok else 'outputs differ beyond the declared tolerance')


# --- environment -----------------------------------------------------------------------------

def semantic_dependencies() -> list[dict]:
    from importlib.metadata import PackageNotFoundError, version
    out = []
    for name in SEMANTIC_DISTRIBUTIONS:
        try:
            out.append({'distribution': name, 'version': version(name)})
        except PackageNotFoundError:
            continue
    out.append({'distribution': DISTRIBUTION, 'version': __version__})
    return out


def environment_lock() -> bytes:
    """Every installed distribution and version, sorted (audit only: the semantic
    dependencies, not this lock, enter a computation's identity)."""
    from importlib.metadata import distributions
    seen = {}
    for dist in distributions():
        name = (dist.metadata.get('Name') or '').strip()
        if name:
            seen[name.lower().replace('_', '-')] = dist.version
    lines = [f'{n}=={v}' for n, v in sorted(seen.items())]
    header = [f'# python {platform.python_version()} ({sys.implementation.name})',
              f'# platform {platform.platform()}']
    return ('\n'.join(header + lines) + '\n').encode('utf-8')


def input_contract(contract: DataContract, features: Sequence[str]) -> dict:
    """The inference projection of a data contract (the feature columns and the policy)."""
    columns = [contract.column(f).model_dump(mode='json') for f in features]
    return {'schema': 'hypotrail.input_contract/1', 'columns': columns,
            'inference_policy': contract.inference_policy.model_dump(mode='json')}


# --- capture ---------------------------------------------------------------------------------

def _file_entry(root: Path, rel: str) -> dict:
    path = root / rel
    return {'relative_path': rel, 'size_bytes': path.stat().st_size,
            'sha256': canonical.file_sha256(path)}


def _write(root: Path, rel: str, data: bytes) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def capture_predictor(fitted: FittedPredictor, context: ComputationContext | Mapping | None,
                      parity_features: pd.DataFrame, destination: Path, packager=None, *,
                      parity_origin: str = 'authorized_development',
                      tolerance: Mapping | None = None, code_fingerprint: str | None = None,
                      extensions: Mapping | None = None) -> BundleDescriptor:
    """Write the bundle of ``fitted`` into ``destination`` (absent or empty) without
    refitting. The bundle holds no target value and no row beyond ``parity_features``
    (feature columns only). ``packager`` (optional, injected) is called on the verified
    native bundle before it is moved into place; its failure fails the capture."""
    destination = Path(destination)
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ContractError('destination_not_empty', f'{destination} already holds files.',
                            path=str(destination.name), remediation='Capture into a new '
                            'directory; an existing bundle is never overwritten.')
    if parity_origin not in ('synthetic', 'authorized_development'):
        raise ContractError('contract_invalid', 'parity_origin is synthetic or '
                            'authorized_development.', path='parity_origin',
                            remediation='Declare where the parity rows come from.')
    recipe, contract = fitted.recipe, fitted.data_contract
    target = recipe.target.name
    if target in parity_features.columns:
        raise ContractError('partition_not_authorized', 'Parity rows never carry the target.',
                            path='parity_features', remediation='Pass the feature columns only.')
    features = list(recipe.features)
    parity_view, _ = inference.check_frame(contract, parity_features, features=features,
                                           purpose='parity')
    if not len(parity_view):
        raise ContractError('contract_invalid', 'The parity set is empty.',
                            path='parity_features', remediation='Pass at least one row.')
    tol = {**DEFAULT_TOLERANCE, **dict(tolerance or {})}
    tol.setdefault('exact', [])
    expected = fitted.predict(parity_view).values
    ctx = None
    if context is not None:
        ctx = context if isinstance(context, ComputationContext) \
            else parse(ComputationContext, context)
    fingerprint = code_fingerprint or (ctx.code_fingerprint if ctx else None)
    if fingerprint is None:
        raise ContractError('contract_invalid', 'A capture names its code fingerprint.',
                            path='code_fingerprint', remediation='Pass the computation context.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f'.{destination.name}.tmp-', dir=destination.parent))
    try:
        from . import wheel
        _write(tmp, PAYLOAD, pickle.dumps(fitted.pipeline, protocol=5))
        canonical.write_json(_mk(tmp, RECIPE), recipe)
        canonical.write_json(_mk(tmp, DATA_CONTRACT), contract)
        recipe_sha, contract_sha = recipe.digest(), contract.digest()
        if ctx is not None:
            canonical.write_json(_mk(tmp, CONTEXT), ctx)
        _write(tmp, LOCK, environment_lock())
        wheel_path = wheel.build(tmp / 'runtime')
        wheel_rel = f'runtime/{wheel_path.name}'
        _write(tmp, PARITY_FEATURES, canonical.dumps(
            parity_frame_document(parity_view, contract, features)) + b'\n')
        _write(tmp, PARITY_EXPECTED, canonical.dumps(
            {'schema_version': 'hypotrail.parity_outputs/1', 'kind': recipe.output_contract.kind,
             'values': [float(v) for v in expected]}) + b'\n')
        payload = _file_entry(tmp, PAYLOAD)
        manifest_doc = {
            'schema_version': 'hypotrail.predictor_artifact/1', 'predictor_id': '0' * 64,
            'recipe_sha256': recipe_sha, 'data_contract_sha256': contract_sha,
            'input_contract_sha256': canonical.scientific_id(input_contract(contract, features)),
            'output_contract': recipe.output_contract.model_dump(mode='json'),
            'native_format': NATIVE_FORMAT, 'payload_files': [payload],
            'runtime': {'api_version': RUNTIME_API_VERSION, 'distribution': DISTRIBUTION,
                        'version': __version__, 'wheel_relative_path': wheel_rel,
                        'wheel_sha256': canonical.file_sha256(wheel_path)},
            'environment': {'python': platform.python_version(),
                            'platform': f'{sys.platform}-{platform.machine()}',
                            'semantic_dependencies': semantic_dependencies(),
                            'lock_relative_path': LOCK,
                            'lock_sha256': canonical.file_sha256(tmp / LOCK)},
            'training_scope': fitted.training_scope.model_dump(mode='json'),
            'code_fingerprint': fingerprint,
            'extensions': {'hypotrail.learnt_state': fitted.learnt_state(),
                           'hypotrail.n_train': fitted.n_train, **dict(extensions or {})}}
        manifest_doc['predictor_id'] = canonical.artifact_id(manifest_doc,
                                                             exclude=('predictor_id',))
        manifest = parse(PredictorArtifact, manifest_doc)
        canonical.write_json(_mk(tmp, MANIFEST), manifest)
        parity_spec = {'features_path': PARITY_FEATURES, 'expected_outputs_path': PARITY_EXPECTED,
                       'sha256s': {PARITY_FEATURES: canonical.file_sha256(tmp / PARITY_FEATURES),
                                   PARITY_EXPECTED: canonical.file_sha256(tmp / PARITY_EXPECTED)},
                       'origin': parity_origin,
                       'tolerance': {'rtol': float(tol['rtol']), 'atol': float(tol['atol']),
                                     'exact': list(tol['exact'])},
                       'n_rows': int(len(parity_view))}
        _write_bundle(tmp, manifest.predictor_id, parity_spec, [])
        native = verify_bundle(tmp)
        reloaded = _load_verified(native)
        parity = compare(expected, reloaded.predict(parity_view).values, parity_spec['tolerance'])
        if parity.status != 'ok':
            raise ContractError('artifact_integrity_failed', 'The reloaded predictor does not '
                                'reproduce the outputs of the fitted one.',
                                remediation='Do not evaluate this capture; the tolerance is '
                                            'never relaxed automatically.',
                                details=parity.model_dump(mode='json'))
        packages = []
        if packager is not None:
            packages = _package(tmp, packager, native, parity_spec)
            _write_bundle(tmp, manifest.predictor_id, parity_spec, packages)
            native = verify_bundle(tmp)
        if destination.exists():
            destination.rmdir()
        os.replace(tmp, destination)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    final = verify_bundle(destination)
    return BundleDescriptor(path=destination, bundle=final.bundle, manifest=final.manifest,
                            recipe=final.recipe, data_contract=final.data_contract,
                            parity=parity, packages=tuple(p for p, _ in packages))


def _mk(root: Path, rel: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _write_bundle(root: Path, predictor_id: str, parity_spec: Mapping,
                  packages: list) -> PredictorBundle:
    files = []
    for path in sorted(p for p in root.rglob('*') if p.is_file()):
        rel = path.relative_to(root).as_posix()
        if rel in (BUNDLE, EVIDENCE_BINDING):
            continue
        files.append(_file_entry(root, rel))
    doc = {'schema_version': 'hypotrail.predictor_bundle/1', 'predictor_id': predictor_id,
           'recipe_path': RECIPE, 'data_contract_path': DATA_CONTRACT,
           'predictor_manifest_path': MANIFEST, 'parity': dict(parity_spec),
           'optional_packages': [entry for _, entry in packages],
           'evidence_binding_path': None, 'files': files}
    bundle = parse(PredictorBundle, doc)
    canonical.write_json(root / BUNDLE, bundle)
    return bundle


def _package(root: Path, packager, native: BundleDescriptor, parity_spec: Mapping) -> list:
    """Run the injected packager on the verified native bundle (workstream B implements
    it; the runtime imports no packaging library)."""
    out = []
    fmt = getattr(packager, 'format', None)
    if not isinstance(fmt, str) or not fmt:
        raise ContractError('contract_invalid', 'A packager names its format.',
                            path='packager.format', remediation='Set packager.format.')
    rel = f'{PACKAGES_DIR}/{fmt}'
    target = root / rel
    target.mkdir(parents=True)
    try:
        descriptor = packager.package(root, target, dict(parity_spec))
        descriptor = descriptor if isinstance(descriptor, PackageDescriptor) else \
            parse(PackageDescriptor, descriptor)
        check = packager.verify(root, target, dict(parity_spec))
        check = check if isinstance(check, ParityResult) else parse(ParityResult, check)
    except ContractError:
        raise
    except Exception as exc:
        raise ContractError('backend_failed', f'The packager {fmt} failed: '
                            f'{type(exc).__name__}: {exc}',
                            remediation='Fix the packaging environment; the final test stays '
                                        'closed.') from exc
    if descriptor.predictor_id != native.predictor_id:
        raise ContractError('artifact_integrity_failed', 'The package names another predictor.',
                            remediation='Package the bundle that was captured.')
    if descriptor.parity_result.status != 'ok' or check.status != 'ok':
        raise ContractError('artifact_integrity_failed', f'The {fmt} package does not '
                            'reproduce the native predictor.',
                            remediation='The capture is not usable; nothing is relaxed.',
                            details={'parity': check.model_dump(mode='json')})
    manifest_rel = f'{rel}/package_descriptor.json'
    manifest_sha = canonical.write_json(root / manifest_rel, descriptor)
    out.append((descriptor, {'format': fmt, 'artifact_id': descriptor.artifact_id,
                             'relative_path': rel, 'manifest_sha256': manifest_sha}))
    return out


# --- verify and load -------------------------------------------------------------------------

def _inside(root: Path, rel: str) -> Path:
    path = root / rel
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError:
        raise ContractError('artifact_integrity_failed', f'{rel} is missing from the bundle.',
                            path=rel, remediation='Capture the bundle again.') from None
    if not resolved.is_relative_to(root.resolve()):
        raise ContractError('artifact_integrity_failed', f'{rel} leaves the bundle directory.',
                            path=rel, remediation='Refuse this bundle.')
    return resolved


def _read_json(root: Path, rel: str) -> dict:
    return json.loads(_inside(root, rel).read_bytes())


def verify_bundle(bundle_dir: Path) -> BundleDescriptor:
    """Check the bundle before anything is unpickled; return its descriptor."""
    root = Path(bundle_dir)
    if not (root / BUNDLE).is_file():
        raise ContractError('model_not_captured', f'{root} holds no {BUNDLE}.',
                            remediation='Capture the predictor first.')
    bundle = parse(PredictorBundle, _inside(root, BUNDLE).read_bytes())
    for path in root.rglob('*'):
        if path.is_symlink() and not path.resolve().is_relative_to(root.resolve()):
            raise ContractError('artifact_integrity_failed', f'{path.name} links outside the '
                                'bundle.', remediation='Refuse this bundle.')
    listed = {f.relative_path for f in bundle.files}
    for entry in bundle.files:
        path = _inside(root, entry.relative_path)
        if path.stat().st_size != entry.size_bytes or \
                canonical.file_sha256(path) != entry.sha256:
            raise ContractError('artifact_integrity_failed', f'{entry.relative_path} does not '
                                'match its recorded size and digest.',
                                path=entry.relative_path, remediation='Refuse this bundle.')
    present = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    extra = sorted(present - listed - {BUNDLE, EVIDENCE_BINDING})
    if extra:
        raise ContractError('artifact_integrity_failed', 'The bundle holds unlisted files.',
                            remediation='Refuse this bundle.', details={'files': extra})
    for rel in (bundle.recipe_path, bundle.data_contract_path, bundle.predictor_manifest_path,
                bundle.parity.features_path, bundle.parity.expected_outputs_path):
        if rel not in listed:
            raise ContractError('artifact_integrity_failed', f'{rel} is not listed.',
                                path=rel, remediation='Refuse this bundle.')
    manifest = parse(PredictorArtifact, _inside(root, bundle.predictor_manifest_path).read_bytes())
    if canonical.artifact_id(manifest, exclude=('predictor_id',)) != manifest.predictor_id \
            or manifest.predictor_id != bundle.predictor_id:
        raise ContractError('artifact_integrity_failed', 'The predictor id does not match its '
                            'manifest.', remediation='Refuse this bundle.')
    recipe = validate_recipe(_inside(root, bundle.recipe_path).read_bytes())
    contract = validate_data_contract(_inside(root, bundle.data_contract_path).read_bytes())
    if recipe.digest() != manifest.recipe_sha256 or contract.digest() != \
            manifest.data_contract_sha256:
        raise ContractError('artifact_integrity_failed', 'The recipe or the data contract does '
                            'not match the manifest.', remediation='Refuse this bundle.')
    for f in manifest.payload_files:
        if f.relative_path not in listed:
            raise ContractError('artifact_integrity_failed', 'A payload is not listed.',
                                path=f.relative_path, remediation='Refuse this bundle.')
    for rel, sha in bundle.parity.sha256s.items():
        if canonical.file_sha256(_inside(root, rel)) != sha:
            raise ContractError('artifact_integrity_failed', f'{rel} does not match its digest.',
                                path=rel, remediation='Refuse this bundle.')
    if manifest.runtime.api_version.split('.')[0] != RUNTIME_API_VERSION.split('.')[0]:
        raise ContractError('schema_version_unsupported', 'The bundle needs another runtime '
                            'API major version.', path='runtime/api_version',
                            remediation=f'Install the runtime {manifest.runtime.version}.')
    return BundleDescriptor(path=root, bundle=bundle, manifest=manifest, recipe=recipe,
                            data_contract=contract)


def environment_issues(manifest: PredictorArtifact) -> list[dict]:
    """Installed versions that differ from the capture's semantic dependencies."""
    from importlib.metadata import PackageNotFoundError, version
    issues = []
    for dep in manifest.environment.semantic_dependencies:
        if dep.distribution == DISTRIBUTION:
            continue
        try:
            found = version(dep.distribution)
        except PackageNotFoundError:
            found = None
        if found != dep.version:
            issues.append({'distribution': dep.distribution, 'captured': dep.version,
                           'installed': found})
    return issues


def _trusted(root: Path, trusted_roots: Sequence[Path] | None) -> bool:
    roots = list(trusted_roots or [])
    roots += [Path(p) for p in os.environ.get(TRUSTED_ROOTS_ENV, '').split(os.pathsep) if p]
    resolved = root.resolve()
    return any(resolved.is_relative_to(Path(r).resolve()) for r in roots)


def _load_verified(desc: BundleDescriptor) -> Predictor:
    issues = environment_issues(desc.manifest)
    if issues:
        raise ContractError('environment_unqualified', 'This environment differs from the '
                            'capture on a dependency of the predictor.',
                            remediation='Install the captured versions (environment lock in '
                                        'the bundle) before loading.',
                            details={'differences': issues})
    with open(_inside(desc.path, desc.manifest.payload_files[0].relative_path), 'rb') as fh:
        pipeline = pickle.load(fh)
    return Predictor(recipe=desc.recipe, data_contract=desc.data_contract, pipeline=pipeline,
                     manifest=desc.manifest, bundle=desc.bundle, path=desc.path)


def load_predictor(bundle_dir: Path, *, trusted_roots: Sequence[Path] | None = None) -> Predictor:
    """Load a verified bundle. The bundle must lie under a root the caller trusts
    explicitly (``trusted_roots`` or ``HYPOTRAIL_RUNTIME_TRUSTED_ROOTS``): verification
    proves integrity, not that a pickle is safe to load."""
    root = Path(bundle_dir)
    desc = verify_bundle(root)
    if not _trusted(root, trusted_roots):
        raise ContractError('artifact_integrity_failed', 'The bundle is not under a trusted '
                            'root; a native payload from an unknown source is never loaded.',
                            remediation=f'Pass trusted_roots=[...] or set {TRUSTED_ROOTS_ENV} '
                                        'for a source you control.')
    return _load_verified(desc)


def check_parity(predictor: Predictor) -> ParityResult:
    """The bundle's own parity rows through ``predictor``."""
    spec = predictor.bundle.parity
    features = frame_from_document(_read_json(predictor.path, spec.features_path))
    expected = _read_json(predictor.path, spec.expected_outputs_path)['values']
    return compare(np.asarray(expected, dtype=float), predictor.predict(features).values,
                   spec.tolerance.model_dump(mode='json'))


def write_evidence_binding(bundle_dir: Path, binding: Mapping) -> Path:
    """Write (or replace by a new version) the mutable evidence binding beside the bundle;
    the hashed content is never modified."""
    from .contracts import EvidenceBinding
    root = Path(bundle_dir)
    desc = verify_bundle(root)
    doc = parse(EvidenceBinding, binding)
    if doc.predictor_id != desc.predictor_id:
        raise ContractError('artifact_integrity_failed', 'A binding names its own predictor '
                            'only.', remediation='Bind the evaluated predictor id.')
    path = root / EVIDENCE_BINDING
    tmp = root / f'.{EVIDENCE_BINDING}.tmp'
    canonical.write_json(tmp, doc)
    os.replace(tmp, path)
    return path
