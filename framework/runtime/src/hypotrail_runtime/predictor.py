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

What the predictor id binds (review A1, 2026-10-24). The id is the digest of the manifest
(``predictor.json``), and every immutable byte of the bundle is reached from it: the
payload, wheel and lock digests it records are compared with the files themselves; the
recipe and the data contract by their content digests; the parity rows, their expected
outputs, their origin and the tolerance through the manifest extension
``hypotrail.parity`` (equal to the bundle document's ``parity``); the computation context
through ``hypotrail.computation_context`` (its path and digest, or null when the capture
had none). A listed file that none of these binds is refused, so the bundle document
(``predictor_bundle.json``) holds nothing that could change a prediction or a parity
verdict without changing the id. Outside the id, by design: the evidence binding
(``evidence/``, mutable and versioned) and the optional packages, which are made from the
verified native bundle after its id exists; each package is checked against its own
descriptor (present, listed, digests, ``predictor_id``, ``artifact_id``), never trusted
blindly, and a native bundle embedded in a package must be the predictor itself, byte for
byte (review A1, round 2).

Round 3 (review A, 2026-10-25). A package's ``artifact_id`` is the content id of its
descriptor (:func:`canonical.artifact_id` without ``artifact_id``: its files with their
digests, signature, environment and parity) and is recomputed; every listed file under
``packages/<format>/`` must be named by the descriptor, apart from the descriptor's own copy
inside the package (extension ``hypotrail.descriptor_copy``), which must be the descriptor
beside the package, canonically equal. A Python bytecode cache (``__pycache__``, ``*.pyc``,
``*.pyo``) anywhere in a bundle is refused, listed or not: it is code that no digest binds
(Python imports a cached module instead of its source), and loading a package in place
writes one. Trusted roots are absolute paths.
* :meth:`Predictor.predict` checks the raw features against the data contract and returns
  a :class:`PredictionBatch` in input order: the score of the named positive class, or a
  prediction in the target unit.
"""
from __future__ import annotations

import json
import os
import pickle
import platform
import re
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
                        ParityResult, ParitySpec, PredictorArtifact, PredictorBundle,
                        TrainingScope, Tolerance, parse, validate_data_contract,
                        validate_recipe)
from .errors import ContractError
from .preprocess import build_pipeline

NATIVE_FORMAT = 'sklearn_pickle/1'
PAYLOAD = 'payload/model.pkl'
RECIPE = 'recipe.json'
DATA_CONTRACT = 'data_contract.json'
MANIFEST = 'predictor.json'
BUNDLE = 'predictor_bundle.json'
CONTEXT = 'computation_context.json'
LOCK = 'environment/requirements.lock'
PARITY_FEATURES = 'parity/features.json'
PARITY_EXPECTED = 'parity/expected_outputs.json'
# Evidence bindings are versioned beside the hashed content: ``evidence/binding-<n>.json``;
# the bundle document's ``evidence_binding_path`` names the current one (CONTRAT §5).
EVIDENCE_DIR = 'evidence'
PACKAGES_DIR = 'packages'
# Spec L-10: proposed float64 tolerances; classes and selections must match exactly. They
# are never relaxed automatically.
DEFAULT_TOLERANCE = {'rtol': 1e-10, 'atol': 1e-12}
SEMANTIC_DISTRIBUTIONS = ('numpy', 'pandas', 'scikit-learn', 'scipy')
TRUSTED_ROOTS_ENV = 'HYPOTRAIL_RUNTIME_TRUSTED_ROOTS'
PARITY_FRAME = 'hypotrail.parity_frame/1'
# Manifest extensions that bind the parity and the computation context to the predictor id
# (and the ones the capture itself writes): a caller's extension never replaces them.
BOUND_PARITY = 'hypotrail.parity'
BOUND_CONTEXT = 'hypotrail.computation_context'
RESERVED_EXTENSIONS = ('hypotrail.learnt_state', 'hypotrail.n_train', BOUND_PARITY,
                       BOUND_CONTEXT)
# A packager's format names a folder of the bundle (``packages/<format>``).
PACKAGE_FORMAT = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')
# The descriptor extension naming the descriptor's own copy inside its package (round 3).
DESCRIPTOR_COPY = 'hypotrail.descriptor_copy'
# Python bytecode: never part of a bundle (round 3, R3-A1).
BYTECODE_DIR = '__pycache__'
BYTECODE_SUFFIXES = ('.pyc', '.pyo')


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


def runtime_closure(root: str = DISTRIBUTION) -> dict[str, str]:
    """``{distribution: version}`` of the installed distributions the runtime needs to load
    and run a predictor: the transitive closure of ``root``'s requirements (extras and
    unmet environment markers left out), including ``root``."""
    import re
    from importlib.metadata import PackageNotFoundError, distribution
    name_re = re.compile(r'^\s*([A-Za-z0-9][A-Za-z0-9._-]*)')
    seen: dict[str, str] = {}
    todo = [root]
    while todo:
        name = todo.pop()
        key = name.lower().replace('_', '-')
        if key in seen:
            continue
        try:
            dist = distribution(name)
        except PackageNotFoundError:
            continue
        seen[key] = dist.version
        for req in dist.requires or []:
            requirement, _, marker = req.partition(';')
            if 'extra' in marker:
                continue
            if marker.strip() and not _marker_holds(marker):
                continue
            m = name_re.match(requirement)
            if m:
                todo.append(m.group(1))
    return seen


def _marker_holds(marker: str) -> bool:
    try:
        from packaging.markers import Marker
    except ImportError:              # pragma: no cover - keep the requirement when unsure
        return True
    return Marker(marker.strip()).evaluate()


def environment_lock() -> bytes:
    """The pinned environment of the predictor (audit: the semantic dependencies, not this
    lock, enter a computation's identity): every distribution of the runtime's dependency
    closure, ``name==version``, sorted. Packages of the engine the predictor does not need
    (notebooks, browsers, diagnostics backends) are not part of it."""
    pins = runtime_closure()
    pins.pop(DISTRIBUTION, None)          # shipped as the bundle's own wheel
    lines = [f'{n}=={v}' for n, v in sorted(pins.items())]
    # The header names the platform as the manifest does (system and machine), not the
    # kernel build: the lock digest enters the predictor id.
    header = [f'# python {platform.python_version()} ({sys.implementation.name})',
              f'# platform {sys.platform}-{platform.machine()}',
              f'# closure of {DISTRIBUTION} {__version__} requirements']
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
    clash = sorted(set(extensions or {}) & set(RESERVED_EXTENSIONS))
    if clash:
        raise ContractError('contract_invalid', 'These manifest extensions are written by the '
                            'capture itself.', path='extensions',
                            remediation='Use another namespaced key.', details={'keys': clash})
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
             'columns': list(recipe.output_contract.columns),
             'values': [float(v) for v in expected]}) + b'\n')
        payload = _file_entry(tmp, PAYLOAD)
        parity_spec = {'features_path': PARITY_FEATURES, 'expected_outputs_path': PARITY_EXPECTED,
                       'sha256s': {PARITY_FEATURES: canonical.file_sha256(tmp / PARITY_FEATURES),
                                   PARITY_EXPECTED: canonical.file_sha256(tmp / PARITY_EXPECTED)},
                       'origin': parity_origin,
                       'tolerance': {'rtol': float(tol['rtol']), 'atol': float(tol['atol']),
                                     'exact': list(tol['exact'])},
                       'n_rows': int(len(parity_view))}
        bound_context = None if ctx is None else {'relative_path': CONTEXT,
                                                  'sha256': canonical.file_sha256(tmp / CONTEXT)}
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
            'extensions': {**dict(extensions or {}),
                           'hypotrail.learnt_state': fitted.learnt_state(),
                           'hypotrail.n_train': fitted.n_train,
                           BOUND_PARITY: parity_spec, BOUND_CONTEXT: bound_context}}
        manifest_doc['predictor_id'] = canonical.artifact_id(manifest_doc,
                                                             exclude=('predictor_id',))
        manifest = parse(PredictorArtifact, manifest_doc)
        canonical.write_json(_mk(tmp, MANIFEST), manifest)
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
            _verify_packages(tmp, packager, packages, parity_spec)
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
        if rel == BUNDLE or rel.startswith(EVIDENCE_DIR + '/'):
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


def _contract_doc(model, value):
    """A packager's answer as a contract model: the model itself, an object exposing
    ``to_contract()`` (its contract v1 document), or a mapping."""
    if isinstance(value, model):
        return value
    if hasattr(value, 'to_contract'):
        value = value.to_contract()
    return parse(model, value)


def _package(root: Path, packager, native: BundleDescriptor, parity_spec: Mapping) -> list:
    """Run the injected packager on the verified native bundle (workstream B implements
    it; the runtime imports no packaging library). Its descriptor is recorded beside the
    package (``packages/<format>.descriptor.json``), never inside it."""
    out = []
    fmt = getattr(packager, 'format', None)
    if not isinstance(fmt, str) or not PACKAGE_FORMAT.match(fmt):
        # Checked before the format becomes a path (``packages/<format>``).
        raise ContractError('contract_invalid', 'A packager names its format: letters, digits, '
                            '"_" or "-", 64 characters at most, no path separator or dot.',
                            path='packager.format', remediation='Set packager.format.',
                            details={'format': fmt if isinstance(fmt, str) else None})
    rel = f'{PACKAGES_DIR}/{fmt}'
    target = root / rel
    target.mkdir(parents=True)
    try:
        descriptor = _contract_doc(PackageDescriptor,
                                   packager.package(root, target, dict(parity_spec)))
    except ContractError:
        raise
    except Exception as exc:
        raise ContractError('backend_failed', f'The packager {fmt} failed: '
                            f'{type(exc).__name__}: {exc}',
                            remediation='Fix the packaging environment; the final test stays '
                                        'closed.', details=_error_details(exc)) from exc
    if descriptor.predictor_id != native.predictor_id:
        raise ContractError('artifact_integrity_failed', 'The package names another predictor.',
                            remediation='Package the bundle that was captured.')
    if descriptor.parity_result.status != 'ok':
        raise ContractError('artifact_integrity_failed', f'The {fmt} package does not '
                            'reproduce the native predictor.',
                            remediation='The capture is not usable; nothing is relaxed.',
                            details={'parity': descriptor.parity_result.model_dump(mode='json')})
    manifest_rel = f'{PACKAGES_DIR}/{fmt}.descriptor.json'
    manifest_sha = canonical.write_json(root / manifest_rel, descriptor)
    out.append((descriptor, {'format': fmt, 'artifact_id': descriptor.artifact_id,
                             'relative_path': rel, 'manifest_sha256': manifest_sha}))
    return out


def _error_details(exc) -> dict:
    to_dict = getattr(exc, 'to_dict', None)
    return dict(to_dict()) if callable(to_dict) else {}


def _verify_packages(root: Path, packager, packages: list, parity_spec: Mapping) -> None:
    """Ask the packager to verify its package against the final bundle document."""
    for _, entry in packages:
        try:
            check = _contract_doc(ParityResult, packager.verify(root, root / entry[
                'relative_path'], dict(parity_spec)))
        except ContractError:
            raise
        except Exception as exc:
            raise ContractError('backend_failed', f'Verifying the {entry["format"]} package '
                                f'failed: {type(exc).__name__}: {exc}',
                                remediation='Fix the packaging environment.',
                                details=_error_details(exc)) from exc
        if check.status != 'ok':
            raise ContractError('artifact_integrity_failed', f'The {entry["format"]} package '
                                'does not reproduce the native predictor.',
                                remediation='The capture is not usable; nothing is relaxed.',
                                details={'parity': check.model_dump(mode='json')})


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


def _refuse_integrity(message: str, *, path: str = '', **details) -> None:
    raise ContractError('artifact_integrity_failed', message, path=path,
                        remediation='Refuse this bundle; capture the predictor again.',
                        details=details or None)


def verify_bundle(bundle_dir: Path) -> BundleDescriptor:
    """Check the bundle before anything is unpickled; return its descriptor.

    Every listed file is compared with its bytes; every digest the manifest records (the
    payload, the runtime wheel, the environment lock, the parity files and the computation
    context) is compared with the bytes too; the bundle document's parity block must be the
    one the manifest binds; every listed file must be bound by the manifest or belong to a
    declared optional package (checked against its descriptor, and any native bundle it
    embeds against this one)."""
    root = Path(bundle_dir)
    if not (root / BUNDLE).is_file():
        raise ContractError('model_not_captured', f'{root} holds no {BUNDLE}.',
                            remediation='Capture the predictor first.')
    refuse_bytecode(root, what='bundle')
    bundle = parse(PredictorBundle, _inside(root, BUNDLE).read_bytes())
    for path in root.rglob('*'):
        if path.is_symlink() and not path.resolve().is_relative_to(root.resolve()):
            raise ContractError('artifact_integrity_failed', f'{path.name} links outside the '
                                'bundle.', remediation='Refuse this bundle.')
    listed = {f.relative_path for f in bundle.files}
    actual: dict[str, str] = {}
    for entry in bundle.files:
        path = _inside(root, entry.relative_path)
        digest = canonical.file_sha256(path)
        if path.stat().st_size != entry.size_bytes or digest != entry.sha256:
            raise ContractError('artifact_integrity_failed', f'{entry.relative_path} does not '
                                'match its recorded size and digest.',
                                path=entry.relative_path, remediation='Refuse this bundle.')
        actual[entry.relative_path] = digest
    present = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    extra = sorted(p for p in present - listed - {BUNDLE}
                   if not p.startswith(EVIDENCE_DIR + '/'))
    if extra:
        raise ContractError('artifact_integrity_failed', 'The bundle holds unlisted files.',
                            remediation='Refuse this bundle.', details={'files': extra})
    if bundle.evidence_binding_path is not None and (
            not bundle.evidence_binding_path.startswith(EVIDENCE_DIR + '/')
            or not (root / bundle.evidence_binding_path).is_file()):
        raise ContractError('artifact_integrity_failed', 'The evidence binding path is not a '
                            'recorded binding.', path='evidence_binding_path',
                            remediation='Refuse this bundle.')
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
    if manifest.runtime.api_version.split('.')[0] != RUNTIME_API_VERSION.split('.')[0]:
        raise ContractError('schema_version_unsupported', 'The bundle needs another runtime '
                            'API major version.', path='runtime/api_version',
                            remediation=f'Install the runtime {manifest.runtime.version}.')
    recipe = validate_recipe(_inside(root, bundle.recipe_path).read_bytes())
    contract = validate_data_contract(_inside(root, bundle.data_contract_path).read_bytes())
    if recipe.digest() != manifest.recipe_sha256 or contract.digest() != \
            manifest.data_contract_sha256:
        raise ContractError('artifact_integrity_failed', 'The recipe or the data contract does '
                            'not match the manifest.', remediation='Refuse this bundle.')
    bound = _check_manifest_bindings(bundle, manifest, actual)
    _check_packages(root, bundle, actual, bound)
    return BundleDescriptor(path=root, bundle=bundle, manifest=manifest, recipe=recipe,
                            data_contract=contract)


def bytecode_in(root: Path) -> tuple[list[str], list[str]]:
    """``(folders, files)``: the ``__pycache__`` folders and the stray ``*.pyc``/``*.pyo``
    files under ``root`` (relative POSIX paths, sorted; files inside a listed folder are not
    repeated)."""
    root = Path(root)
    folders, files = set(), set()
    for path in root.rglob('*'):
        parts = path.relative_to(root).parts
        if BYTECODE_DIR in parts:
            folders.add('/'.join(parts[:parts.index(BYTECODE_DIR) + 1]))
        elif path.suffix.lower() in BYTECODE_SUFFIXES:
            files.add('/'.join(parts))
    return sorted(folders), sorted(files)


def refuse_bytecode(root: Path, *, what: str = 'bundle') -> None:
    """Refuse a bundle (or a package) holding Python bytecode (round 3, R3-A1/A4). A
    ``__pycache__`` folder is what loading a package in place leaves behind (``mlflow.pyfunc.
    load_model`` on ``packages/<format>`` compiles its wrapper there), and a planted one
    replaces the wrapper the digests bind: it is refused whether it is listed or not, and
    the message says how to recover."""
    folders, files = bytecode_in(root)
    if not folders and not files:
        return
    named = folders + files
    shown = ', '.join(named[:5]) + (f' and {len(named) - 5} more' if len(named) > 5 else '')
    raise ContractError(
        'artifact_integrity_failed',
        f'A Python bytecode cache was written into the {what} ({shown}), typically by loading '
        f'its package in place (for example mlflow.pyfunc.load_model on '
        f'{PACKAGES_DIR}/<format> inside the bundle). Bytecode is code that no digest binds '
        f'(Python runs a cached module instead of its source), so the {what} is refused.',
        path=named[0],
        remediation=f'Delete {shown} (Python bytecode only; nothing the {what} needs), then '
                    f'load a package from a copy of its folder, never from inside the {what}.',
        details={'bytecode_folders': folders, 'bytecode_files': files})


def _bound_digest(actual: Mapping[str, str], rel: str | None, sha: str | None,
                  what: str) -> str | None:
    """The listed file ``rel`` whose bytes the manifest records as ``sha``."""
    if rel is None and sha is None:
        return None
    if rel is None or sha is None:
        _refuse_integrity(f'The manifest names the {what} without both its path and digest.',
                          path=what)
    if rel not in actual:
        _refuse_integrity(f'The {what} the manifest binds is not in the bundle.', path=rel)
    if actual[rel] != sha:
        _refuse_integrity(f'The {what} does not match the digest the predictor id binds.',
                          path=rel, recorded=sha, found=actual[rel])
    return rel


def _check_manifest_bindings(bundle: PredictorBundle, manifest: PredictorArtifact,
                             actual: Mapping[str, str]) -> set[str]:
    """Compare every digest the manifest records with the bytes; return the bound paths."""
    bound = {bundle.predictor_manifest_path, bundle.recipe_path, bundle.data_contract_path}
    for f in manifest.payload_files:
        if f.relative_path not in actual:
            _refuse_integrity('A payload the manifest binds is not in the bundle.',
                              path=f.relative_path)
        bound.add(_bound_digest(actual, f.relative_path, f.sha256, 'payload'))
    for rel, sha, what in ((manifest.runtime.wheel_relative_path, manifest.runtime.wheel_sha256,
                            'runtime wheel'),
                           (manifest.environment.lock_relative_path,
                            manifest.environment.lock_sha256, 'environment lock')):
        found = _bound_digest(actual, rel, sha, what)
        if found is not None:
            bound.add(found)
    ext = manifest.extensions
    if BOUND_PARITY not in ext or BOUND_CONTEXT not in ext:
        _refuse_integrity('The manifest does not bind the parity rows, the tolerance and the '
                          'computation context (a bundle captured before this runtime '
                          'version); its id does not cover them.', path='extensions',
                          missing=[k for k in (BOUND_PARITY, BOUND_CONTEXT) if k not in ext])
    try:
        spec = ParitySpec.model_validate(ext[BOUND_PARITY], strict=True)
    except Exception:
        _refuse_integrity('The parity binding of the manifest is malformed.',
                          path=f'extensions/{BOUND_PARITY}')
    if canonical.dumps(spec) != canonical.dumps(bundle.parity):
        _refuse_integrity('The parity rows, their outputs, their origin or the tolerance of '
                          'the bundle document differ from the ones the predictor id binds.',
                          path='parity')
    if set(spec.sha256s) != {spec.features_path, spec.expected_outputs_path}:
        _refuse_integrity('The parity digests name exactly the parity features and outputs.',
                          path='parity/sha256s')
    for rel, sha in spec.sha256s.items():
        bound.add(_bound_digest(actual, rel, sha, 'parity file'))
    context = ext[BOUND_CONTEXT]
    if context is not None:
        if not isinstance(context, Mapping) or set(context) != {'relative_path', 'sha256'} \
                or not all(isinstance(v, str) for v in context.values()):
            _refuse_integrity('The computation-context binding of the manifest is malformed.',
                              path=f'extensions/{BOUND_CONTEXT}')
        bound.add(_bound_digest(actual, context['relative_path'], context['sha256'],
                                'computation context'))
    return bound


def _check_packages(root: Path, bundle: PredictorBundle, actual: Mapping[str, str],
                    bound: set[str]) -> None:
    """Each optional package against its descriptor; no listed file left unbound."""
    owned: list[str] = []
    formats = set()
    for i, entry in enumerate(bundle.optional_packages):
        where = f'optional_packages/{i}'
        if not PACKAGE_FORMAT.match(entry.format) or entry.format in formats \
                or entry.relative_path != f'{PACKAGES_DIR}/{entry.format}':
            _refuse_integrity('An optional package is not declared as the capture writes it '
                              '(packages/<format>, one per format).', path=where)
        formats.add(entry.format)
        descriptor_rel = f'{PACKAGES_DIR}/{entry.format}.descriptor.json'
        if descriptor_rel not in actual or actual[descriptor_rel] != entry.manifest_sha256:
            _refuse_integrity(f'The {entry.format} package descriptor is missing or altered.',
                              path=descriptor_rel)
        descriptor = parse(PackageDescriptor, _inside(root, descriptor_rel).read_bytes())
        if (descriptor.format, descriptor.predictor_id, descriptor.artifact_id) != \
                (entry.format, bundle.predictor_id, entry.artifact_id):
            _refuse_integrity(f'The {entry.format} package descriptor names another format, '
                              'predictor or artefact.', path=descriptor_rel)
        if package_artifact_id(descriptor) != descriptor.artifact_id:
            _refuse_integrity(f'The artifact id of the {entry.format} package is not the '
                              'content id of its descriptor (its files, signature, '
                              'environment and parity).', path=descriptor_rel,
                              recorded=descriptor.artifact_id,
                              found=package_artifact_id(descriptor))
        if descriptor.parity_result.status != 'ok':
            _refuse_integrity(f'The {entry.format} package does not reproduce the native '
                              'predictor.', path=descriptor_rel)
        for f in descriptor.files:
            rel = f'{entry.relative_path}/{f.relative_path}'
            if actual.get(rel) != f.sha256:
                _refuse_integrity(f'A file of the {entry.format} package is missing or '
                                  'altered.', path=rel)
        _check_package_listing(root, entry, descriptor, actual)
        _check_embedded_bundles(root, bundle, entry, descriptor, actual, bound)
        owned += [descriptor_rel, entry.relative_path + '/']
    unbound = sorted(rel for rel in actual if rel not in bound
                     and not any(rel == o or (o.endswith('/') and rel.startswith(o))
                                 for o in owned))
    if unbound:
        _refuse_integrity('The bundle lists files that neither the predictor id nor a '
                          'declared package binds.', files=unbound)


def package_artifact_id(descriptor: PackageDescriptor) -> str:
    """The content id of a package (round 3, R3-A2): the canonical digest of its descriptor
    without ``artifact_id``. The descriptor lists every file of the package with its
    SHA-256, so the id changes with any byte of the package."""
    return canonical.artifact_id(descriptor, exclude=('artifact_id',))


def _check_package_listing(root: Path, entry, descriptor: PackageDescriptor,
                           actual: Mapping[str, str]) -> None:
    """Every listed file under ``packages/<format>/`` is named by the package descriptor;
    the only other one allowed is the descriptor's own copy (``hypotrail.descriptor_copy``),
    which must be the descriptor beside the package (round 3, R3-A1/A2)."""
    prefix = entry.relative_path + '/'
    named = {f.relative_path for f in descriptor.files}
    copy = descriptor.extensions.get(DESCRIPTOR_COPY)
    if copy is not None:
        copy_rel = f'{prefix}{copy}' if isinstance(copy, str) else None
        if copy_rel is None or copy in named or copy_rel not in actual:
            _refuse_integrity(f'The {entry.format} package descriptor names a copy of itself '
                              'that the package does not hold as an unlisted file.',
                              path=copy_rel or f'{entry.relative_path}.descriptor.json')
        try:
            inner = parse(PackageDescriptor, _inside(root, copy_rel).read_bytes())
        except ContractError as exc:
            _refuse_integrity(f'The descriptor inside the {entry.format} package is not a '
                              f'package descriptor: {exc.message}', path=copy_rel,
                              inner_code=exc.code)
        if canonical.dumps(inner) != canonical.dumps(descriptor):
            _refuse_integrity(f'The descriptor inside the {entry.format} package differs from '
                              'the one beside it.', path=copy_rel)
        named.add(copy)
    unnamed = sorted(rel for rel in actual
                     if rel.startswith(prefix) and rel[len(prefix):] not in named)
    if unnamed:
        _refuse_integrity(f'The {entry.format} package holds listed files its descriptor does '
                          'not name.', path=unnamed[0], files=unnamed)


def _check_embedded_bundles(root: Path, bundle: PredictorBundle, entry, descriptor,
                            actual: Mapping[str, str], bound: set[str]) -> None:
    """A native bundle carried inside a package is the outer predictor, byte for byte
    (review A1, round 2): the package is outside the predictor id, so a copy re-captured
    with another model that agrees on the parity rows would otherwise be served under the
    evaluated id. Every folder of the package holding a listed ``predictor_bundle.json``,
    and the folder the descriptor names (extension ``hypotrail.native_bundle``), is verified
    as a bundle of its own and must name the same predictor, recipe, data contract and payload,
    and list exactly the files the outer predictor id binds, with the same digests. It holds
    no package of its own."""
    prefix = entry.relative_path + '/'
    # Every listed file of the package, described or not (an unlisted one is refused before).
    inside_package = [rel[len(prefix):] for rel in actual if rel.startswith(prefix)]
    folders = {rel.rpartition('/')[0] for rel in inside_package
               if rel == BUNDLE or rel.endswith('/' + BUNDLE)}
    declared = descriptor.extensions.get('hypotrail.native_bundle')
    if declared is not None:
        if not isinstance(declared, str) or declared.strip('/') not in folders:
            _refuse_integrity(f'The {entry.format} package descriptor names an embedded native '
                              'bundle that the package does not hold.',
                              path=f'{prefix}{declared}' if isinstance(declared, str)
                              else f'{entry.relative_path}.descriptor.json')
    expected = {rel: actual[rel] for rel in bound}
    for folder in sorted(folders):
        rel = prefix + folder if folder else entry.relative_path
        try:
            inner = verify_bundle(_inside(root, rel))
        except ContractError as exc:
            _refuse_integrity(f'The native bundle embedded in the {entry.format} package does '
                              f'not verify: {exc.message}', path=rel, inner_code=exc.code)
        if inner.predictor_id != bundle.predictor_id:
            _refuse_integrity(f'The native bundle embedded in the {entry.format} package is '
                              'another predictor.', path=rel, recorded=bundle.predictor_id,
                              found=inner.predictor_id)
        if inner.bundle.optional_packages:
            _refuse_integrity(f'The native bundle embedded in the {entry.format} package holds '
                              'packages of its own.', path=rel)
        found = {f.relative_path: f.sha256 for f in inner.bundle.files}
        for what, path in (('predictor manifest', bundle.predictor_manifest_path),
                           ('recipe', bundle.recipe_path),
                           ('data contract', bundle.data_contract_path),
                           *(('payload', f.relative_path)
                             for f in inner.manifest.payload_files)):
            if found.get(path) != expected.get(path):
                _refuse_integrity(f'The {what} of the native bundle embedded in the '
                                  f'{entry.format} package differs from the predictor\'s.',
                                  path=f'{rel}/{path}')
        if found != expected:
            _refuse_integrity(f'The native bundle embedded in the {entry.format} package does '
                              'not hold exactly the files the predictor id binds.', path=rel,
                              files=sorted(set(found) ^ set(expected)
                                           | {k for k in found if found[k] != expected.get(k)}))


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


def _trusted_roots(trusted_roots) -> list[Path]:
    """``trusted_roots`` is None or a collection of paths. A string or a single path is
    refused: iterating it would trust each character (``'/'`` trusts every bundle)."""
    if trusted_roots is None:
        return []
    if isinstance(trusted_roots, (str, bytes, os.PathLike)) or \
            not hasattr(trusted_roots, '__iter__'):
        raise ContractError('contract_invalid', 'trusted_roots is a list of directories, not '
                            'one path or one string.', path='trusted_roots',
                            remediation='Pass trusted_roots=[directory, ...].',
                            details={'type': type(trusted_roots).__name__})
    roots = list(trusted_roots)
    for root in roots:
        if not isinstance(root, (str, os.PathLike)) or isinstance(root, bytes):
            raise ContractError('contract_invalid', 'Each trusted root is a path.',
                                path='trusted_roots',
                                remediation='Pass trusted_roots=[directory, ...].',
                                details={'type': type(root).__name__})
        # An empty or relative root would trust the working directory, whatever it is when
        # the call runs (round 3, R3-A5): ``Path('')`` is ``.``.
        if not os.fspath(root) or not Path(root).is_absolute():
            raise ContractError('contract_invalid', 'Each trusted root is an absolute '
                                'directory path; an empty or relative one would trust the '
                                'current working directory.', path='trusted_roots',
                                remediation='Pass absolute directories, for example '
                                            'trusted_roots=[Path(folder).resolve()].',
                                details={'root': os.fspath(root)})
    return [Path(r) for r in roots]


def _trusted(root: Path, trusted_roots: Sequence[Path] | None) -> bool:
    roots = _trusted_roots(trusted_roots)
    # Empty and relative entries of the variable are dropped (never the working directory).
    roots += [Path(p) for p in os.environ.get(TRUSTED_ROOTS_ENV, '').split(os.pathsep)
              if p and Path(p).is_absolute()]
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
    _trusted_roots(trusted_roots)            # a malformed argument is refused first
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
    for rel, sha in spec.sha256s.items():      # the files the predictor id binds, re-read
        if canonical.file_sha256(_inside(predictor.path, rel)) != sha:
            _refuse_integrity(f'{rel} changed after the bundle was verified.', path=rel)
    features = frame_from_document(_read_json(predictor.path, spec.features_path))
    expected = _read_json(predictor.path, spec.expected_outputs_path)['values']
    return compare(np.asarray(expected, dtype=float), predictor.predict(features).values,
                   spec.tolerance.model_dump(mode='json'))


def write_evidence_binding(bundle_dir: Path, binding: Mapping) -> Path:
    """Record a new version of the evidence binding (``evidence/binding-<n>.json``) and
    point the bundle document's ``evidence_binding_path`` at it. The hashed content (the
    predictor manifest and every listed file) is never modified; earlier bindings stay."""
    from .contracts import EvidenceBinding
    root = Path(bundle_dir)
    desc = verify_bundle(root)
    doc = parse(EvidenceBinding, binding)
    if doc.predictor_id != desc.predictor_id:
        raise ContractError('artifact_integrity_failed', 'A binding names its own predictor '
                            'only.', remediation='Bind the evaluated predictor id.')
    folder = root / EVIDENCE_DIR
    folder.mkdir(exist_ok=True)
    n = 1 + max([int(p.stem.split('-')[1]) for p in folder.glob('binding-*.json')
                 if p.stem.split('-')[1].isdigit()] or [0])
    rel = f'{EVIDENCE_DIR}/binding-{n}.json'
    canonical.write_json(root / rel, doc)
    bundle = desc.bundle.model_copy(update={'evidence_binding_path': rel})
    # The temporary document is written under evidence/ (outside the hashed content), so a
    # crash before the rename leaves nothing that makes the bundle unverifiable.
    tmp = folder / f'.{BUNDLE}.tmp'
    canonical.write_json(tmp, parse(PredictorBundle, bundle.model_dump(mode='json')))
    os.replace(tmp, root / BUNDLE)
    return root / rel


def read_evidence_binding(bundle_dir: Path):
    """The current evidence binding of a verified bundle, or None (``unassessed``)."""
    from .contracts import EvidenceBinding
    root = Path(bundle_dir)
    desc = verify_bundle(root)
    rel = desc.bundle.evidence_binding_path
    if rel is None:
        return None
    doc = parse(EvidenceBinding, _inside(root, rel).read_bytes())
    if doc.predictor_id != desc.predictor_id:
        raise ContractError('artifact_integrity_failed', 'The evidence binding names another '
                            'predictor.', path=rel, remediation='Refuse this binding.')
    return doc
