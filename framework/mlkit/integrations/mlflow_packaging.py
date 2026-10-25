"""MLflow packaging of a native Hypotrail predictor bundle (contract v1 §6, L-19, M-07).

``ArtifactPackager`` is the packaging extension of the shared interface: it consumes a
native bundle produced by ``hypotrail_runtime.capture_predictor`` (chantier A) and writes
an MLflow ``python_function`` package next to it, **without fitting anything and without
reading any study**. The package is a derived artefact with its own identity
(``artifact_id``), linked to the native predictor by ``predictor_id``; it is never new
scientific evidence.

* :meth:`ArtifactPackager.package` verifies the native bundle (``verify_bundle``), predicts
  the bundle's parity features with the native predictor and compares them with the
  bundle's expected outputs, saves the pyfunc package in a temporary sibling folder, loads
  it back with ``mlflow.pyfunc.load_model``, compares its predictions with the native ones,
  writes ``hypotrail-package.json`` (the package descriptor) and publishes the folder by a
  rename. Any failure leaves no package behind.
* :meth:`ArtifactPackager.verify` repeats the two comparisons on an existing package, after
  checking that the package serves the native bundle it was made from: its wrapper is this
  packager's, ``MLmodel`` loads it on ``artifacts/native_bundle`` with the signature of the
  bundle, and the bundle there verifies and is byte-identical to the native one (same
  predictor id, manifest, recipe, data contract, payload and bound files). ``package`` makes
  the same check before publishing. The package is outside the predictor id; parity on the
  bundle's rows alone would accept another model that agrees on them (review A1, round 2).

Round 3 (review A, 2026-10-25). Nothing from the package runs before its integrity is
established, and nothing is read from or written into it as bytecode:

* a ``__pycache__`` folder or a ``*.pyc``/``*.pyo`` file anywhere in a package is refused,
  never skipped (a planted cache replaces the wrapper the digests bind, and MLflow imports
  it); a package is loaded for parity only from a fresh temporary copy, with bytecode
  reading and writing disabled (``sys.pycache_prefix`` on an empty temporary folder,
  ``sys.dont_write_bytecode``);
* ``artifact_id`` is the content id of the descriptor (``hypotrail_runtime.canonical.
  artifact_id`` of the contract document without ``artifact_id``), recomputed by ``verify``
  and by the runtime; the descriptor inside the package (``hypotrail-package.json``, named
  by the extension ``hypotrail.descriptor_copy``) is the contract document itself, so the
  runtime compares it with the one beside the package;
* the environment files (``requirements.txt``, ``conda.yaml``, ``python_env.yaml``) are
  written by this packager from the bundle's pinned environment (its semantic dependencies,
  the runtime and the MLflow version recorded in the descriptor), not by the MLflow
  installation, and ``verify`` regenerates them and compares the bytes;
* ``verify`` turns every failure into a :class:`PackagingError` (a runtime refusal keeps its
  contract code; anything else is ``artifact_integrity_failed``) or a failed result.

Round 4 (review A, 2026-10-25). A package holds exactly the files this packager writes, and
its ``MLmodel`` is exactly the document it writes:

* ``MLmodel`` is written by this packager (:func:`mlmodel_bytes`, from the bundle's signature
  and the package's pinned environment: no clock, no random id, no local path, no key
  MLflow's loader would follow elsewhere such as ``data``, ``code`` or ``model_config``), in
  place of the one ``mlflow.pyfunc.save_model`` writes; ``verify`` regenerates it and
  compares the bytes, so an added, removed or changed key (top level or in the
  ``python_function`` block) is refused before anything from the package runs;
* the package's files are an allowlist (:data:`PACKAGE_FILES`): ``MLmodel``, the wrapper, the
  three environment files, the descriptor copy, and ``artifacts/native_bundle/**`` (the
  embedded bundle, checked against the native one); any other file or folder is refused, by
  :meth:`ArtifactPackager.package` and :meth:`ArtifactPackager.verify` here, and by the
  runtime's ``verify_bundle`` for a package of this format inside a bundle.

The wrapper inside the package (``hypotrail_pyfunc.py``, MLflow "models from code") imports
only ``hypotrail_runtime``, ``mlflow`` and ``pandas``: it keeps the whole preprocessing of the
native predictor and the meaning of its output (``regression_point`` or the score of the
named positive class), so serving needs neither this repository nor a study.

Tolerances are the ones the bundle declares (``parity.tolerance``), never relaxed here.
Tracking is not done here: packaging logs nothing to any MLflow server.

This module is **standalone** (stdlib, pandas, numpy, mlflow, hypotrail_runtime; all but
the stdlib imported lazily) because the Azure ML export copies it byte for byte into the
generated project (``src/pipeline/utils/hypotrail/mlflow_packaging.py``), where the
training step injects it into ``capture_predictor`` for a rebuilt candidate.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import math
import os
import re
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping

FORMAT = 'mlflow_pyfunc'
# 2 (round 3): the descriptor inside the package is the contract document, its artifact id
# is the descriptor's content id, and the environment files are the packager's own.
# 3 (round 4): ``MLmodel`` is the packager's own document and the files are an allowlist.
PACKAGER_VERSION = '3'
DESCRIPTOR_SCHEMA = 'hypotrail.package_descriptor/1'
PARITY_SCHEMA = 'hypotrail.parity_result/1'
DESCRIPTOR_FILE = 'hypotrail-package.json'
WRAPPER_FILE = 'hypotrail_pyfunc.py'
NATIVE_ARTIFACT = 'native_bundle'
# The bundle document of contract v1 §5 (``hypotrail.predictor_bundle/1``), at the bundle
# root; the name hypotrail_runtime writes (integration I1).
BUNDLE_DOCUMENT = 'predictor_bundle.json'
PARITY_FRAME = 'hypotrail.parity_frame/1'
PARITY_OUTPUTS = 'hypotrail.parity_outputs/1'
RUNTIME_MODULE = 'hypotrail_runtime'
# Physical types of a DataContract column and the MLflow ColSpec type they map to.
MLFLOW_TYPES = {'int64': 'long', 'int32': 'integer', 'float64': 'double', 'float32': 'float',
                'bool': 'boolean', 'boolean': 'boolean', 'string': 'string', 'str': 'string',
                'object': 'string', 'category': 'string', 'datetime64[ns]': 'datetime'}
OUTPUT_KINDS = ('regression_point', 'binary_score')
DESCRIPTOR_COPY = 'hypotrail.descriptor_copy'
ENVIRONMENT_FILES = ('requirements.txt', 'conda.yaml', 'python_env.yaml')
MLMODEL_ENV = {'conda': 'conda.yaml', 'virtualenv': 'python_env.yaml'}
MLMODEL_FILE = 'MLmodel'
CODE_LOADER = 'mlflow.pyfunc.loaders.code_model'
EMBEDDED_BUNDLE = f'artifacts/{NATIVE_ARTIFACT}'
# The files of a package (round 4, R4-A1): these names at the package root, and the embedded
# native bundle under ``EMBEDDED_BUNDLE``; nothing else. The runtime keeps the same list for
# the ``mlflow_pyfunc`` format (``hypotrail_runtime.predictor.MLFLOW_PYFUNC_FILES``).
PACKAGE_FILES = (MLMODEL_FILE, WRAPPER_FILE, *ENVIRONMENT_FILES, DESCRIPTOR_FILE)
PACKAGE_FOLDERS = ('artifacts', EMBEDDED_BUNDLE)
BYTECODE_DIR = '__pycache__'
BYTECODE_SUFFIXES = ('.pyc', '.pyo')
# What may enter a generated environment file: a distribution name, a version, a Python
# version (no URL, no space, no YAML syntax).
_NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$')
_VERSION = re.compile(r'^[0-9][A-Za-z0-9.+!_-]{0,63}$')
_PYTHON = re.compile(r'^[0-9]+\.[0-9]+\.[0-9]+[A-Za-z0-9+]{0,16}$')

WRAPPER_SOURCE = '''"""MLflow pyfunc wrapper of a Hypotrail native predictor (generated by the packager).

It loads the native bundle stored in the package artifacts with ``hypotrail_runtime`` and
returns its typed predictions in input order. It neither fits nor reads any other file.
"""
from pathlib import Path

import mlflow.pyfunc
import pandas as pd
from mlflow.models import set_model


class HypotrailPredictor(mlflow.pyfunc.PythonModel):
    """Native predictor behind the pyfunc interface."""

    def load_context(self, context):
        import hypotrail_runtime

        bundle = Path(context.artifacts["native_bundle"]).resolve()
        hypotrail_runtime.verify_bundle(bundle)
        # The bundle travels inside this package: it is the trusted source by construction.
        self._predictor = hypotrail_runtime.load_predictor(bundle, trusted_roots=[bundle])

    def predict(self, context, model_input, params=None):
        batch = self._predictor.predict(model_input)
        columns = list(batch.columns)
        values = batch.values
        rows = list(batch.row_order)
        frame = pd.DataFrame(values, columns=columns) if getattr(values, "ndim", 1) == 2 \\
            else pd.DataFrame({columns[0]: list(values)})
        frame.index = rows
        return frame.sort_index().reset_index(drop=True)


set_model(HypotrailPredictor())
'''


class PackagingError(RuntimeError):
    """A refusal of the packager: ``code`` is one of the contract v1 §8 codes."""

    def __init__(self, code: str, message: str, *, path: str | None = None,
                 remediation: str | None = None, details: Mapping | None = None):
        super().__init__(message)
        self.code, self.message, self.path = code, message, path
        self.remediation = remediation
        self.details = dict(details or {})

    def to_dict(self) -> dict:
        return {'code': self.code, 'path': self.path, 'message': self.message,
                'remediation': self.remediation, 'details': self.details}


@dataclass(frozen=True)
class ParitySpec:
    """Where the parity rows are, relative to the native bundle, and the declared
    tolerance. ``origin`` is ``synthetic`` or ``authorized_development``."""

    features_path: str
    expected_outputs_path: str
    rtol: float
    atol: float
    origin: str

    @classmethod
    def from_bundle(cls, bundle: Mapping) -> 'ParitySpec':
        parity = bundle.get('parity')
        if not isinstance(parity, Mapping):
            raise PackagingError('contract_invalid', 'The bundle has no parity section.',
                                 path='parity')
        tolerance = parity.get('tolerance')
        if not isinstance(tolerance, Mapping):
            raise PackagingError('contract_invalid', 'The bundle parity has no tolerance.',
                                 path='parity.tolerance')
        rtol, atol = tolerance.get('rtol'), tolerance.get('atol')
        for name, value in (('rtol', rtol), ('atol', atol)):
            if type(value) is not float or not math.isfinite(value) or value < 0:
                raise PackagingError('contract_invalid',
                                     f'parity.tolerance.{name} must be a finite float >= 0.',
                                     path=f'parity.tolerance.{name}')
        origin = parity.get('origin')
        if origin not in ('synthetic', 'authorized_development'):
            raise PackagingError('contract_invalid',
                                 'parity.origin must be synthetic or authorized_development.',
                                 path='parity.origin')
        return cls(_relative(parity.get('features_path'), 'parity.features_path'),
                   _relative(parity.get('expected_outputs_path'),
                             'parity.expected_outputs_path'), rtol, atol, origin)


@dataclass(frozen=True)
class ParityResult:
    """The comparisons of one parity check (``status`` passed, failed, or not_run)."""

    status: str
    n_rows: int | None
    columns: list
    rtol: float
    atol: float
    comparisons: list
    reason: str | None = None
    schema_version: str = PARITY_SCHEMA

    def to_dict(self) -> dict:
        return asdict(self)

    def to_contract(self) -> dict:
        """The ``hypotrail.parity_result/1`` document of contract v1 (status ``ok`` or
        ``failed``); the comparisons are kept under namespaced extensions."""
        worst = [c.get('max_abs_diff') for c in self.comparisons
                 if isinstance(c.get('max_abs_diff'), float)]
        return {'schema_version': PARITY_SCHEMA,
                'status': 'ok' if self.status == 'passed' else 'failed',
                'n_rows': int(self.n_rows or 0),
                'max_abs_diff': max(worst) if worst else None, 'max_rel_diff': None,
                'exact_mismatches': 0,
                'tolerance': {'rtol': float(self.rtol), 'atol': float(self.atol), 'exact': []},
                'reason': self.reason,
                'extensions': {'hypotrail.comparisons': list(self.comparisons),
                               'hypotrail.columns': list(self.columns)}}


@dataclass(frozen=True)
class PackageDescriptor:
    """The packaged artefact: its files and their sha256, its signature and environment,
    and the parity observed when it was written."""

    format: str
    artifact_id: str
    predictor_id: str
    files: list
    signature: dict
    environment: dict
    parity_result: dict
    schema_version: str = DESCRIPTOR_SCHEMA
    packager_version: str = PACKAGER_VERSION
    native_bundle: str = f'artifacts/{NATIVE_ARTIFACT}'
    extensions: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_contract(self) -> dict:
        """The ``hypotrail.package_descriptor/1`` document of contract v1."""
        parity = self.parity_result
        if isinstance(parity, Mapping) and parity.get('status') in ('passed', 'failed') \
                and 'comparisons' in parity:
            parity = ParityResult(parity['status'], parity.get('n_rows'), parity['columns'],
                                  parity['rtol'], parity['atol'], parity['comparisons'],
                                  parity.get('reason')).to_contract()
        return {'schema_version': DESCRIPTOR_SCHEMA, 'format': self.format,
                'artifact_id': self.artifact_id, 'predictor_id': self.predictor_id,
                'files': list(self.files), 'signature': dict(self.signature),
                'environment': dict(self.environment), 'parity_result': parity,
                'extensions': {'hypotrail.packager_version': self.packager_version,
                               'hypotrail.native_bundle': self.native_bundle,
                               **{k: v for k, v in self.extensions.items() if '.' in k}}}


# --- helpers ----------------------------------------------------------------------------

def canonical_bytes(value: Any) -> bytes:
    """Contract v1 §1 canonical JSON: sorted keys, compact, UTF-8, no NaN; -0.0 is 0.0."""
    return json.dumps(_normal(value), sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def _normal(value: Any) -> Any:
    if isinstance(value, Mapping):
        out = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise PackagingError('contract_invalid', 'A JSON object key is not a string.')
            out[key] = _normal(item)
        return out
    if isinstance(value, (list, tuple)):
        return [_normal(v) for v in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PackagingError('contract_invalid', 'A JSON number is not finite.')
        return 0.0 if value == 0 else value
    if value is None or isinstance(value, (str, bool, int)):
        return value
    raise PackagingError('contract_invalid', f'Not a JSON value: {type(value).__name__}.')


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def _relative(path, where: str) -> str:
    """A relative POSIX path inside a folder: no absolute path, no ``..``."""
    if not isinstance(path, str) or not path or path.startswith('/') or '\\' in path:
        raise PackagingError('artifact_integrity_failed', f'{where} is not a relative path.',
                             path=where)
    if any(part in ('', '.', '..') for part in path.split('/')):
        raise PackagingError('artifact_integrity_failed', f'{where} leaves its folder.',
                             path=where)
    return path


def inside(root: Path, relative: str, where: str) -> Path:
    target = root / _relative(relative, where)
    real_root = Path(os.path.realpath(root))
    real = Path(os.path.realpath(target))
    if real_root not in real.parents:
        raise PackagingError('artifact_integrity_failed', f'{where} resolves outside the bundle.',
                             path=where)
    return target


def bytecode_in(root: Path) -> tuple[list[str], list[str]]:
    """``(folders, files)``: the ``__pycache__`` folders and stray ``*.pyc``/``*.pyo`` files
    under ``root``, relative, sorted."""
    folders, files = set(), set()
    for path in Path(root).rglob('*'):
        parts = path.relative_to(root).parts
        if BYTECODE_DIR in parts:
            folders.add('/'.join(parts[:parts.index(BYTECODE_DIR) + 1]))
        elif path.suffix.lower() in BYTECODE_SUFFIXES:
            files.add('/'.join(parts))
    return sorted(folders), sorted(files)


def refuse_bytecode(root: Path, what: str = 'package') -> None:
    """``artifact_integrity_failed`` when ``root`` holds Python bytecode (round 3): MLflow
    imports a cached wrapper instead of the source the digests bind, and loading a package
    in place writes such a cache. The message names what to delete."""
    folders, files = bytecode_in(root)
    if not folders and not files:
        return
    named = folders + files
    shown = ', '.join(named[:5]) + (f' and {len(named) - 5} more' if len(named) > 5 else '')
    raise PackagingError(
        'artifact_integrity_failed',
        f'A Python bytecode cache was written into the {what} ({shown}), typically by loading '
        f'the package in place (mlflow.pyfunc.load_model on its folder). Bytecode is code no '
        f'digest binds (Python runs a cached module instead of its source), so the {what} is '
        f'refused.', path=named[0],
        remediation=f'Delete {shown} (Python bytecode only), then load the package from a copy '
                    f'of its folder, never in place.',
        details={'bytecode_folders': folders, 'bytecode_files': files})


def _inventory(root: Path) -> list[dict]:
    """``[{relative_path, size_bytes, sha256}]`` of every file under ``root``, sorted; a
    symlink is refused; Python bytecode (``__pycache__``, ``*.pyc``, ``*.pyo``) is refused,
    never skipped (round 3)."""
    refuse_bytecode(root)
    out = []
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise PackagingError('artifact_integrity_failed',
                                 'A package may not contain a symbolic link.',
                                 path=path.relative_to(root).as_posix())
        if path.is_file():
            out.append({'relative_path': path.relative_to(root).as_posix(),
                        'size_bytes': path.stat().st_size, 'sha256': sha256_file(path)})
    return out


def _read_json(path: Path, where: str) -> dict:
    try:
        with open(path, encoding='utf-8') as handle:
            data = json.load(handle, parse_constant=_no_constant)
    except (OSError, ValueError) as error:
        raise PackagingError('artifact_integrity_failed', f'{where} is not readable JSON.',
                             path=where, details={'error': str(error)}) from error
    if not isinstance(data, dict):
        raise PackagingError('contract_invalid', f'{where} is not a JSON object.', path=where)
    return data


def _no_constant(name: str):
    raise ValueError(f'non-finite JSON constant {name}')


def _import(name: str, extra: str):
    try:
        return importlib.import_module(name)
    except ImportError as error:
        raise PackagingError('optional_dependency_missing', f'{name} is not installed.',
                             remediation=f'Install {extra} in this environment.',
                             details={'module': name}) from error


def read_table(path: Path):
    """A parity table: the runtime's typed documents (``hypotrail.parity_frame/1`` features,
    ``hypotrail.parity_outputs/1`` expected outputs), ``.csv`` (header), ``.json`` (records),
    or ``.parquet``."""
    pd = _import('pandas', 'pandas')
    suffix = path.suffix.lower()
    if suffix == '.csv':
        return pd.read_csv(path, keep_default_na=False, na_values=[''])
    if suffix == '.json':
        data = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(data, Mapping) and data.get('schema_version') == PARITY_FRAME:
            # The runtime's own reader keeps the declared physical types (no inference).
            runtime = _import(RUNTIME_MODULE, 'the hypotrail_runtime wheel of the bundle')
            return runtime.predictor.frame_from_document(data)
        if isinstance(data, Mapping) and data.get('schema_version') == PARITY_OUTPUTS:
            columns = data.get('columns') or []
            if len(columns) != 1:
                raise PackagingError('contract_invalid', 'Parity outputs name one column.',
                                     path=path.name)
            return pd.DataFrame({columns[0]: [float(v) for v in data['values']]})
        return pd.DataFrame(data)
    if suffix == '.parquet':
        return pd.read_parquet(path)
    raise PackagingError('contract_invalid', f'Unsupported parity table format: {suffix}.',
                         path=path.name)


def batch_frame(batch):
    """A ``PredictionBatch`` (contract v1 §6) as a DataFrame in input order."""
    pd = _import('pandas', 'pandas')
    columns = list(batch.columns)
    values = batch.values
    if getattr(values, 'ndim', 1) == 2:
        frame = pd.DataFrame(values, columns=columns)
    else:
        if len(columns) != 1:
            raise PackagingError('contract_invalid',
                                 'A one-dimensional prediction batch names one column.')
        frame = pd.DataFrame({columns[0]: list(values)})
    frame.index = list(batch.row_order)
    return frame.sort_index().reset_index(drop=True)


def compare(left, right, rtol: float, atol: float) -> dict:
    """``{equal, max_abs_diff, reason}``: same columns and rows; floats within
    ``|l - r| <= atol + rtol * |r|`` with NaN, and infinities of the same sign, at the same
    places; other values equal."""
    np = _import('numpy', 'numpy')
    if list(left.columns) != list(right.columns):
        return {'equal': False, 'max_abs_diff': None, 'reason': 'columns_differ'}
    if len(left) != len(right):
        return {'equal': False, 'max_abs_diff': None, 'reason': 'row_count_differs'}
    worst = 0.0
    for column in left.columns:
        a, b = left[column].to_numpy(), right[column].to_numpy()
        if a.dtype.kind in 'fiu' and b.dtype.kind in 'fiu':
            a, b = a.astype('float64'), b.astype('float64')
            nan_a, nan_b = np.isnan(a), np.isnan(b)
            if not np.array_equal(nan_a, nan_b):
                return {'equal': False, 'max_abs_diff': None, 'reason': 'nan_positions_differ'}
            # Infinities must sit at the same rows with the same sign (swapped rows differ).
            inf_a, inf_b = np.isinf(a), np.isinf(b)
            if not np.array_equal(inf_a, inf_b) or not np.array_equal(a[inf_a], b[inf_b]):
                return {'equal': False, 'max_abs_diff': None, 'reason': 'infinities_differ'}
            mask = ~(nan_a | np.isinf(a))
            if mask.any():
                diff = np.abs(a[mask] - b[mask])
                worst = max(worst, float(diff.max()))
                if not bool(np.all(diff <= atol + rtol * np.abs(b[mask]))):
                    return {'equal': False, 'max_abs_diff': worst, 'reason': 'outside_tolerance'}
        elif not np.array_equal(a.astype(object), b.astype(object)):
            return {'equal': False, 'max_abs_diff': None, 'reason': 'values_differ'}
    return {'equal': True, 'max_abs_diff': worst, 'reason': None}


# --- the packager -----------------------------------------------------------------------

class ArtifactPackager:
    """Contract v1 §6 packaging extension; ``format`` is ``mlflow_pyfunc``.

    ``runtime`` is the ``hypotrail_runtime`` module (imported lazily by default). The
    packager never calls ``fit_predictor``."""

    format = FORMAT

    def __init__(self, runtime=None):
        self._runtime = runtime

    @property
    def runtime(self):
        if self._runtime is None:
            self._runtime = _import(RUNTIME_MODULE, 'the hypotrail_runtime wheel of the bundle')
        return self._runtime

    # The documents of a native bundle, read after ``verify_bundle`` accepted it.
    def _documents(self, bundle_dir: Path) -> tuple[dict, dict, dict]:
        bundle = _read_json(bundle_dir / BUNDLE_DOCUMENT, BUNDLE_DOCUMENT)
        if bundle.get('schema_version') != 'hypotrail.predictor_bundle/1':
            raise PackagingError('schema_version_unsupported',
                                 'The native bundle is not hypotrail.predictor_bundle/1.',
                                 path='schema_version',
                                 details={'found': bundle.get('schema_version')})
        manifest = _read_json(inside(bundle_dir, bundle.get('predictor_manifest_path'),
                                      'predictor_manifest_path'), 'predictor_manifest_path')
        contract = _read_json(inside(bundle_dir, bundle.get('data_contract_path'),
                                      'data_contract_path'), 'data_contract_path')
        return bundle, manifest, contract

    def _parity_frames(self, bundle_dir: Path, spec: ParitySpec):
        features = read_table(inside(bundle_dir, spec.features_path, 'parity.features_path'))
        expected = read_table(inside(bundle_dir, spec.expected_outputs_path,
                                      'parity.expected_outputs_path'))
        return features, expected

    def signature(self, manifest: Mapping, contract: Mapping) -> dict:
        """The explicit pyfunc signature: the inference columns of the data contract in its
        canonical order (target and keys excluded) and the output contract's columns."""
        columns = contract.get('columns')
        if not isinstance(columns, list):
            raise PackagingError('contract_invalid', 'The data contract has no columns.',
                                 path='data_contract.columns')
        by_name = {c.get('name'): c for c in columns if isinstance(c, Mapping)}
        policy = contract.get('inference_policy') or {}
        order = policy.get('canonical_order') or policy.get('required_columns') or \
            [c['name'] for c in columns if c.get('role') == 'feature']
        inputs = []
        for name in order:
            column = by_name.get(name)
            if column is None or column.get('role') in ('target', 'key'):
                raise PackagingError('contract_invalid',
                                     f'Inference column {name!r} is not a feature column.',
                                     path='data_contract.inference_policy')
            kind = MLFLOW_TYPES.get(str(column.get('physical_type')))
            if kind is None:
                raise PackagingError('capability_not_supported',
                                     f'No MLflow type for physical type '
                                     f'{column.get("physical_type")!r}.',
                                     path=f'data_contract.columns.{name}')
            inputs.append({'name': name, 'type': kind,
                           'required': not bool(column.get('nullable'))})
        output = manifest.get('output_contract') or {}
        if output.get('kind') not in OUTPUT_KINDS:
            raise PackagingError('capability_not_supported',
                                 f'Output kind {output.get("kind")!r} is not packaged in v1.',
                                 path='output_contract.kind')
        outputs = [{'name': name, 'type': 'double', 'required': True}
                   for name in output.get('columns') or []]
        if not outputs:
            raise PackagingError('contract_invalid', 'The output contract names no column.',
                                 path='output_contract.columns')
        return {'inputs': inputs, 'outputs': outputs, 'output_kind': output['kind'],
                'unit': output.get('unit'), 'positive_label': output.get('positive_label')}

    def _requirements(self, manifest: Mapping, mlflow_version: str | None = None) -> list[str]:
        """The pinned requirements of the package: the bundle's semantic dependencies, its
        runtime, and ``mlflow-skinny`` at ``mlflow_version`` (the installed MLflow when it is
        None). Every pin is a distribution name and a version, never a URL or an option."""
        runtime = manifest.get('runtime') or {}
        environment = manifest.get('environment') or {}
        pins = [(d.get('distribution'), d.get('version'))
                for d in environment.get('semantic_dependencies') or []
                if isinstance(d, Mapping)]
        if runtime.get('distribution') or runtime.get('version'):
            pins.append((runtime.get('distribution'), runtime.get('version')))
        if mlflow_version is None:
            mlflow_version = _import('mlflow', 'the azureml extra (mlflow-skinny)').__version__
        pins.append(('mlflow-skinny', mlflow_version))
        lines = set()
        for name, version in pins:
            if not (isinstance(name, str) and _NAME.match(name) and isinstance(version, str)
                    and _VERSION.match(version)):
                raise PackagingError('contract_invalid', 'A pinned dependency of the package is '
                                     'not a distribution name and a version.',
                                     path='environment.semantic_dependencies',
                                     details={'distribution': str(name)[:100],
                                              'version': str(version)[:64]})
            lines.add(f'{name}=={version}')
        return sorted(lines)

    def environment(self, manifest: Mapping, mlflow_version: str | None = None) -> dict:
        """The package's environment (``python``, ``pip_requirements``, ``mlflow``): the
        bundle's pinned environment and the MLflow version of the package."""
        python = (manifest.get('environment') or {}).get('python')
        if not isinstance(python, str) or not _PYTHON.match(python):
            raise PackagingError('contract_invalid', 'The bundle does not name its Python '
                                 'version as major.minor.micro.', path='environment.python',
                                 details={'python': str(python)[:40]})
        if mlflow_version is None:
            mlflow_version = _import('mlflow', 'the azureml extra (mlflow-skinny)').__version__
        return {'python': python, 'pip_requirements': self._requirements(manifest, mlflow_version),
                'mlflow': mlflow_version}

    def _native_parity(self, bundle_dir: Path, spec: ParitySpec):
        features, expected = self._parity_frames(bundle_dir, spec)
        root = Path(bundle_dir).resolve()
        predictor = self.runtime.load_predictor(root, trusted_roots=[root])
        native = batch_frame(predictor.predict(features.copy()))
        return features, expected, native

    # The contract document of a descriptor and its content id (round 3, R3-A2).
    def _contract(self, document: Mapping):
        runtime = self.runtime
        try:
            return runtime.parse(runtime.PackageDescriptor, document)
        except Exception as error:      # noqa: BLE001 - the runtime's refusal is the cause
            raise PackagingError('artifact_integrity_failed', 'The package descriptor is not a '
                                 'hypotrail.package_descriptor/1 document.',
                                 path=DESCRIPTOR_FILE,
                                 remediation='Capture the predictor again; never edit a '
                                             'package.',
                                 details={'error': f'{type(error).__name__}: {error}'[:300]}
                                 ) from error

    def content_id(self, document: Mapping) -> str:
        """The package's ``artifact_id``: the runtime's content id of its descriptor (the
        contract document without ``artifact_id``), the rule the runtime checks too."""
        return self.runtime.canonical.artifact_id(self._contract(document),
                                                  exclude=('artifact_id',))

    def _describe(self, predictor_id, files, signature, environment, parity
                  ) -> PackageDescriptor:
        draft = PackageDescriptor(FORMAT, '0' * 64, predictor_id, files, signature,
                                  environment, parity,
                                  extensions={DESCRIPTOR_COPY: DESCRIPTOR_FILE})
        return replace(draft, artifact_id=self.content_id(draft.to_contract()))

    def descriptor_bytes(self, descriptor: PackageDescriptor) -> bytes:
        """The canonical bytes of the contract document, as ``capture_predictor`` writes the
        descriptor beside the package: the copy inside the package is the same document."""
        return self.runtime.canonical.dumps(self._contract(descriptor.to_contract())) + b'\n'

    def package(self, native_bundle_dir, output_dir, parity_spec: ParitySpec | None = None
                ) -> PackageDescriptor:
        """Write the pyfunc package of ``native_bundle_dir`` at ``output_dir`` (a new or
        empty folder); refuse, writing nothing, when a parity comparison fails."""
        bundle_dir, out = Path(native_bundle_dir), Path(output_dir)
        self.runtime.verify_bundle(bundle_dir)
        bundle, manifest, contract = self._documents(bundle_dir)
        spec = _spec(parity_spec, bundle)
        signature = self.signature(manifest, contract)
        mlflow = _import('mlflow', 'the azureml extra (mlflow-skinny)')
        environment = self.environment(manifest, mlflow.__version__)
        features, expected, native = self._native_parity(bundle_dir, spec)
        first = compare(native, expected, spec.rtol, spec.atol)
        if not first['equal']:
            raise PackagingError('artifact_integrity_failed',
                                 'The native predictor does not reproduce the bundle parity '
                                 'outputs; nothing was packaged.',
                                 details={'comparison': 'native_vs_expected', **first})
        if out.exists() and (not out.is_dir() or any(out.iterdir())):
            raise PackagingError('destination_not_empty', 'The package folder is not empty.',
                                 path=str(out))
        out.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f'.{out.name}.', dir=out.parent))
        try:
            package_dir = staging / 'package'
            wrapper = staging / WRAPPER_FILE
            wrapper.write_text(WRAPPER_SOURCE, encoding='utf-8')
            bundle_copy = staging / NATIVE_ARTIFACT
            shutil.copytree(bundle_dir, bundle_copy,
                            ignore=_skip(bundle_dir, bundle, out, staging))
            mlflow.pyfunc.save_model(
                str(package_dir), python_model=str(wrapper),
                artifacts={NATIVE_ARTIFACT: str(bundle_copy)},
                signature=_mlflow_signature(signature),
                pip_requirements=environment['pip_requirements'])
            _write_mlmodel(package_dir, signature, environment)
            write_environment_files(package_dir, environment)
            refuse_layout(package_dir, with_descriptor=False)
            self._check_embedded(bundle_dir, bundle, package_dir, signature, environment)
            files = _inventory(package_dir)
            second = self._pyfunc_parity(package_dir, files, features, native, spec)
            if not second['equal']:
                raise PackagingError('artifact_integrity_failed',
                                     'The pyfunc package does not reproduce the native '
                                     'predictions; nothing was packaged.',
                                     details={'comparison': 'pyfunc_vs_native', **second})
            if _inventory(package_dir) != files:
                raise PackagingError('artifact_integrity_failed', 'The package changed while '
                                     'it was checked; nothing was packaged.')
            parity = ParityResult('passed', int(len(features)), list(native.columns),
                                  spec.rtol, spec.atol,
                                  [{'left': 'native', 'right': 'expected', **first},
                                   {'left': 'pyfunc', 'right': 'native', **second}]).to_dict()
            descriptor = self._describe(manifest.get('predictor_id'), files, signature,
                                        environment, parity)
            (package_dir / DESCRIPTOR_FILE).write_bytes(self.descriptor_bytes(descriptor))
            refuse_layout(package_dir)
            if out.exists():
                out.rmdir()
            os.rename(package_dir, out)
            return descriptor
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def _pyfunc_parity(self, package_dir: Path, listed: list, features, native,
                       spec: ParitySpec) -> dict:
        """Load the package with MLflow and compare its predictions with the native ones.

        Round 3 (R3-A1/A4): the package is loaded from a fresh temporary copy, checked
        against ``listed`` first, with bytecode neither read nor written
        (``sys.pycache_prefix`` on an empty temporary folder, ``sys.dont_write_bytecode``):
        nothing is read from, or written into, the package folder or the bundle."""
        mlflow = _import('mlflow', 'the azureml extra (mlflow-skinny)')
        # Imported before bytecode is disabled, so MLflow itself does not recompile.
        importlib.import_module('mlflow.pyfunc')
        importlib.import_module('mlflow.pyfunc.loaders.code_model')
        expected = [f for f in listed if f['relative_path'] != DESCRIPTOR_FILE]
        with tempfile.TemporaryDirectory(prefix='hypotrail-pyfunc-') as scratch:
            copy = Path(scratch) / 'package'
            shutil.copytree(package_dir, copy, symlinks=True)
            found = [f for f in _inventory(copy) if f['relative_path'] != DESCRIPTOR_FILE]
            if found != expected:
                raise PackagingError('artifact_integrity_failed', 'The package changed while '
                                     'it was verified.', path=str(Path(package_dir).name),
                                     remediation='Verify the package again; never edit it.')
            cache = Path(scratch) / 'no-bytecode'
            cache.mkdir()
            previous = (sys.dont_write_bytecode, sys.pycache_prefix)
            modules = set(sys.modules)
            sys.dont_write_bytecode, sys.pycache_prefix = True, str(cache)
            try:
                model = mlflow.pyfunc.load_model(str(copy))
                result = model.predict(features.copy())
            finally:
                sys.dont_write_bytecode, sys.pycache_prefix = previous
                for name in set(sys.modules) - modules:
                    if name.startswith('code_model_') or name == Path(WRAPPER_FILE).stem:
                        sys.modules.pop(name, None)
        pd = _import('pandas', 'pandas')
        if not isinstance(result, pd.DataFrame):
            result = pd.DataFrame({native.columns[0]: list(result)})
        return compare(result.reset_index(drop=True), native, spec.rtol, spec.atol)

    def _check_embedded(self, bundle_dir: Path, bundle: Mapping, package: Path,
                        signature: Mapping, environment: Mapping) -> None:
        """The package serves the native bundle it was made from (review A1, round 2): the
        wrapper is this packager's; ``MLmodel`` is, byte for byte, the document this packager
        writes for the bundle's signature and the package's pinned ``environment``
        (:func:`mlmodel_bytes`, round 4, R4-A1: every top-level key and the whole
        ``python_function`` block, so a ``data`` key or any key not generated is refused);
        and the bundle under ``artifacts/native_bundle`` verifies on its own and is
        byte-identical to the native one (same predictor id, manifest, recipe, data contract
        and payload; exactly the files the predictor id binds, with the same digests). The
        package is outside the predictor id, so parity on the bundle's rows alone would
        accept another model that agrees on them. ``artifact_integrity_failed`` otherwise."""
        def refuse(message, **details):
            raise PackagingError('artifact_integrity_failed', message, path=str(package.name),
                                 remediation='Capture the predictor again; never edit a '
                                             'package.', details=details)
        wrapper = inside(package, WRAPPER_FILE, 'package wrapper')
        if not wrapper.is_file() or wrapper.read_bytes() != WRAPPER_SOURCE.encode('utf-8'):
            refuse('The package wrapper is not the one this packager writes.',
                   file=WRAPPER_FILE)
        expected = mlmodel_bytes(signature, environment)
        path = inside(package, MLMODEL_FILE, MLMODEL_FILE)
        found = path.read_bytes() if path.is_file() else None
        if found != expected:
            import yaml
            try:
                parsed = yaml.safe_load(found.decode('utf-8')) if found is not None else None
            except (UnicodeDecodeError, yaml.YAMLError):
                parsed = None
            differences = _mlmodel_differences(parsed, mlmodel_document(signature,
                                                                        environment))
            shown = [k for name in ('unexpected', 'missing', 'changed')
                     for k in differences[name]]
            refuse('The package MLmodel is not the document this packager writes for the '
                   'native bundle' + (f' ({", ".join(shown[:5])} differ)' if shown else '')
                   + ': MLflow would load what it names instead of the checked wrapper and '
                   'embedded bundle.', file=MLMODEL_FILE, **differences)
        embedded = inside(package, f'artifacts/{NATIVE_ARTIFACT}', 'native bundle')
        try:
            self.runtime.verify_bundle(embedded)
        except Exception as error:      # noqa: BLE001 - the runtime's refusal is the cause
            refuse('The native bundle embedded in the package does not verify.',
                   error=f'{type(error).__name__}: {error}'[:300])
        inner, inner_manifest, _ = self._documents(embedded)
        _, manifest, _ = self._documents(bundle_dir)
        for key in ('predictor_id', 'recipe_sha256', 'data_contract_sha256', 'payload_files'):
            if inner_manifest.get(key) != manifest.get(key):
                refuse('The native bundle embedded in the package is another predictor '
                       f'({key} differs).', field=key)
        if inner.get('optional_packages'):
            refuse('The native bundle embedded in the package holds packages of its own.')
        if _files(inner) != _native_files(bundle):
            refuse('The native bundle embedded in the package does not hold exactly the '
                   'files of the native bundle.')

    def _check_descriptor(self, package: Path, descriptor: Mapping, manifest: Mapping,
                          signature: Mapping) -> dict:
        """The descriptor inside the package (round 3, R3-A2): a contract document of this
        packager's version, its ``artifact_id`` the content id of its files, signature,
        environment and parity, its signature the bundle's, and its environment the bundle's
        pinned environment, whose files the package holds byte for byte. Returns that
        environment."""
        def refuse(message, path=DESCRIPTOR_FILE, **details):
            raise PackagingError('artifact_integrity_failed', message, path=path,
                                 remediation='Capture the predictor again; never edit a '
                                             'package.', details=details)
        model = self._contract(descriptor)
        extensions = descriptor.get('extensions') or {}
        if extensions.get('hypotrail.packager_version') != PACKAGER_VERSION:
            raise PackagingError('schema_version_unsupported', 'The package was written by '
                                 'another version of the MLflow packager.',
                                 path=DESCRIPTOR_FILE,
                                 remediation='Capture the predictor again with this version '
                                             '(the package is derived from the bundle).',
                                 details={'found': str(extensions.get(
                                     'hypotrail.packager_version'))[:20],
                                     'expected': PACKAGER_VERSION})
        if descriptor.get('format') != FORMAT or extensions.get(DESCRIPTOR_COPY) != \
                DESCRIPTOR_FILE or extensions.get('hypotrail.native_bundle') != \
                f'artifacts/{NATIVE_ARTIFACT}':
            refuse('The package descriptor does not describe this packager\'s package.')
        content = self.runtime.canonical.artifact_id(model, exclude=('artifact_id',))
        if content != descriptor.get('artifact_id'):
            refuse('The package artifact id is not the content id of its descriptor.',
                   recorded=str(descriptor.get('artifact_id'))[:64], found=content)
        if descriptor.get('signature') != dict(signature):
            refuse('The package descriptor signature is not the signature of the native '
                   'bundle.')
        recorded = descriptor.get('environment') if isinstance(
            descriptor.get('environment'), Mapping) else {}
        version = recorded.get('mlflow')
        if not isinstance(version, str) or not _VERSION.match(version):
            refuse('The package descriptor does not name its MLflow version.')
        expected = self.environment(manifest, version)
        if dict(recorded) != expected:
            refuse('The package environment is not the pinned environment of the native '
                   'bundle.', expected=expected)
        for name, data in environment_files(expected).items():
            path = inside(package, name, name)
            if not path.is_file() or path.read_bytes() != data:
                refuse(f'{name} is not the environment file this packager writes for the '
                       'pinned environment of the native bundle.', path=name)
        return expected

    def verify(self, native_bundle_dir, package_dir, parity_spec: ParitySpec | None = None
               ) -> ParityResult:
        """Check an existing package against its native bundle: no bytecode, exactly the
        allowlisted files (:func:`refuse_layout`, round 4), file hashes of the descriptor, the
        descriptor itself (:meth:`_check_descriptor`), the wrapper, ``MLmodel`` regenerated
        and compared byte for byte, and the embedded native bundle (:meth:`_check_embedded`),
        native parity, then pyfunc parity on a fresh temporary copy. Nothing from the package
        runs before these checks pass.
        ``failed`` with a reason, never an exception, for a parity mismatch or a changed
        file list; every other failure is a :class:`PackagingError`: the runtime's refusals
        keep their contract code, anything else (an unreadable package, one that would
        serve another bundle, an MLflow error) is ``artifact_integrity_failed``."""
        try:
            return self._verify(Path(native_bundle_dir), Path(package_dir), parity_spec)
        except PackagingError:
            raise
        except Exception as error:      # noqa: BLE001 - converted, never swallowed
            code, to_dict = getattr(error, 'code', None), getattr(error, 'to_dict', None)
            if isinstance(code, str) and callable(to_dict):      # the runtime's ContractError
                found = dict(to_dict())
                raise PackagingError(code, str(found.get('message') or error),
                                     path=found.get('path'),
                                     remediation=found.get('remediation'),
                                     details={**dict(found.get('details') or {}),
                                              'contract_code': code}) from error
            raise PackagingError('artifact_integrity_failed', 'The package could not be '
                                 f'verified: {type(error).__name__}: {error}'[:600],
                                 path=Path(package_dir).name,
                                 remediation='Capture the predictor again; never edit a '
                                             'package.',
                                 details={'error_type': type(error).__name__}) from error

    def _verify(self, bundle_dir: Path, package: Path, parity_spec) -> ParityResult:
        self.runtime.verify_bundle(bundle_dir)
        bundle, manifest, contract = self._documents(bundle_dir)
        spec = _spec(parity_spec, bundle)
        refuse_bytecode(package)
        refuse_layout(package)
        descriptor = _read_json(package / DESCRIPTOR_FILE, DESCRIPTOR_FILE)
        listed = descriptor.get('files')
        if descriptor.get('predictor_id') != manifest.get('predictor_id'):
            return ParityResult('failed', None, [], spec.rtol, spec.atol, [],
                                'predictor_id_differs')
        actual = [f for f in _inventory(package) if f['relative_path'] != DESCRIPTOR_FILE]
        if actual != listed:
            return ParityResult('failed', None, [], spec.rtol, spec.atol, [],
                                'package_files_changed')
        signature = self.signature(manifest, contract)
        environment = self._check_descriptor(package, descriptor, manifest, signature)
        self._check_embedded(bundle_dir, bundle, package, signature, environment)
        features, expected, native = self._native_parity(bundle_dir, spec)
        first = compare(native, expected, spec.rtol, spec.atol)
        second = self._pyfunc_parity(package, actual, features, native, spec)
        status = 'passed' if first['equal'] and second['equal'] else 'failed'
        reason = None if status == 'passed' else (first['reason'] or second['reason'])
        return ParityResult(status, int(len(features)), list(native.columns), spec.rtol,
                            spec.atol, [{'left': 'native', 'right': 'expected', **first},
                                        {'left': 'pyfunc', 'right': 'native', **second}],
                            reason)


def environment_files(environment: Mapping) -> dict[str, bytes]:
    """The environment files of a package for its pinned ``environment`` (round 3, R3-A2):
    ``requirements.txt`` (one pin per line), ``conda.yaml`` and ``python_env.yaml`` in the
    layout MLflow reads. Written by the packager, not by the installed MLflow, so their
    bytes depend on the bundle only (MLflow would add the local pip and setuptools
    versions), and regenerated by :meth:`ArtifactPackager.verify`."""
    pins = list(environment['pip_requirements'])
    python = environment['python']
    requirements = ''.join(f'{pin}\n' for pin in pins)
    conda = ('channels:\n- conda-forge\ndependencies:\n'
             f'- python={python}\n- pip\n- pip:\n'
             + ''.join(f'  - {pin}\n' for pin in pins) + 'name: mlflow-env\n')
    python_env = (f'python: {python}\nbuild_dependencies:\n- pip\n- setuptools\n- wheel\n'
                  'dependencies:\n- -r requirements.txt\n')
    return {'requirements.txt': requirements.encode('utf-8'),
            'conda.yaml': conda.encode('utf-8'),
            'python_env.yaml': python_env.encode('utf-8')}


def write_environment_files(package_dir: Path, environment: Mapping) -> None:
    for name, data in environment_files(environment).items():
        (Path(package_dir) / name).write_bytes(data)


def _signature_json(columns) -> str:
    """One side of an MLmodel signature, as MLflow serialises a ``Schema`` of ``ColSpec``:
    a JSON list of ``{type, name, required}`` (ASCII, MLflow's separators)."""
    return json.dumps([{'type': c['type'], 'name': c['name'], 'required': bool(c['required'])}
                       for c in columns])


def mlmodel_document(signature: Mapping, environment: Mapping) -> dict:
    """The ``MLmodel`` document of a package (round 4, R4-A1): the ``python_function``
    flavor that loads this packager's wrapper (MLflow "models from code") on the embedded
    native bundle with the packager's environment files, the bundle's signature, the
    package's Python and MLflow versions. Nothing else: no ``data``, ``code``,
    ``model_config`` or other key MLflow's loader would follow, no clock, random id or local
    path, so the document depends on the bundle and the pinned environment only."""
    return {'flavors': {'python_function': {
                'artifacts': {NATIVE_ARTIFACT: {'path': EMBEDDED_BUNDLE, 'uri': NATIVE_ARTIFACT}},
                'code': None, 'env': dict(MLMODEL_ENV), 'loader_module': CODE_LOADER,
                'model_code_path': WRAPPER_FILE, 'python_version': environment['python'],
                'streamable': False}},
            'mlflow_version': environment['mlflow'],
            'signature': {'inputs': _signature_json(signature['inputs']),
                          'outputs': _signature_json(signature['outputs']), 'params': None}}


def mlmodel_bytes(signature: Mapping, environment: Mapping) -> bytes:
    """The bytes of ``MLmodel`` (round 4, R4-A1): :func:`mlmodel_document` as indented JSON
    with sorted keys, ASCII only, which is YAML that MLflow reads (``yaml.safe_load``).
    Written by :meth:`ArtifactPackager.package` and regenerated by ``verify``, which
    compares the bytes."""
    return (json.dumps(mlmodel_document(signature, environment), indent=2, sort_keys=True,
                       ensure_ascii=True, allow_nan=False) + '\n').encode('ascii')


def _mlmodel_differences(found, expected: Mapping, prefix: str = '') -> dict:
    """``{unexpected, missing, changed}``: dotted keys of ``found`` (a parsed ``MLmodel``)
    against the document the packager writes, for the refusal's details."""
    out = {'unexpected': [], 'missing': [], 'changed': []}
    if not isinstance(found, Mapping):
        out['changed'].append(prefix or '<document>')
        return out
    for key in sorted(set(found) | set(expected), key=str):
        where = f'{prefix}{key}'
        if key not in expected:
            out['unexpected'].append(where)
        elif key not in found:
            out['missing'].append(where)
        elif isinstance(expected[key], Mapping) and isinstance(found[key], Mapping):
            for name, items in _mlmodel_differences(found[key], expected[key],
                                                    where + '.').items():
                out[name] += items
        elif found[key] != expected[key]:
            out['changed'].append(where)
    return out


def layout_issues(root: Path, *, with_descriptor: bool = True) -> dict:
    """``{unexpected, missing}``: the paths under a package folder that the allowlist of round
    4 (R4-A1) does not admit (any file or folder but :data:`PACKAGE_FILES`, the folders of
    :data:`PACKAGE_FOLDERS` and what lies under ``artifacts/native_bundle/``), and the
    allowlisted files that are absent (the descriptor copy only when ``with_descriptor``;
    the embedded bundle by its ``predictor_bundle.json``)."""
    root = Path(root)
    unexpected = []
    for path in sorted(root.rglob('*')):
        rel = path.relative_to(root).as_posix()
        if rel.startswith(EMBEDDED_BUNDLE + '/'):
            continue
        if path.is_dir() and not path.is_symlink():
            if rel not in PACKAGE_FOLDERS:
                unexpected.append(rel + '/')
        elif rel not in PACKAGE_FILES:
            unexpected.append(rel)
    required = [*PACKAGE_FILES, f'{EMBEDDED_BUNDLE}/{BUNDLE_DOCUMENT}']
    missing = [rel for rel in required if (with_descriptor or rel != DESCRIPTOR_FILE)
               and not (root / rel).is_file()]
    return {'unexpected': unexpected, 'missing': missing}


def refuse_layout(root: Path, *, with_descriptor: bool = True) -> None:
    """``artifact_integrity_failed`` unless the package folder holds exactly the files of
    the allowlist (:func:`layout_issues`). MLflow's loader follows keys of ``MLmodel`` to
    other files of the package, so a file no check reads is never admitted."""
    issues = layout_issues(root, with_descriptor=with_descriptor)
    if not issues['unexpected'] and not issues['missing']:
        return
    named = issues['unexpected'] + issues['missing']
    shown = ', '.join(named[:5]) + (f' and {len(named) - 5} more' if len(named) > 5 else '')
    raise PackagingError(
        'artifact_integrity_failed',
        f'The package does not hold exactly the files this packager writes ({shown}): only '
        f'{", ".join(PACKAGE_FILES)} and the embedded native bundle under {EMBEDDED_BUNDLE}/ '
        'are allowed, since MLflow could load any other file of the package.',
        path=named[0],
        remediation='Capture the predictor again; never add, remove or edit a file of a '
                    'package.',
        details={'unexpected': issues['unexpected'], 'missing': issues['missing'],
                 'allowed': [*PACKAGE_FILES, EMBEDDED_BUNDLE + '/']})


def _signature_document(value) -> dict:
    """An MLmodel ``signature`` with its JSON strings decoded, for comparison."""
    if not isinstance(value, Mapping):
        return {'unreadable': str(value)[:200]}
    out = {}
    for key, item in value.items():
        if isinstance(item, str):
            try:
                item = json.loads(item)
            except ValueError:
                item = {'unreadable': item[:200]}
        out[str(key)] = item
    return out


def _spec(parity_spec, bundle: Mapping) -> ParitySpec:
    """The parity spec: a :class:`ParitySpec`, the runtime's mapping (the bundle's
    ``parity`` section, passed by ``capture_predictor``), or the bundle's own."""
    if isinstance(parity_spec, ParitySpec):
        return parity_spec
    if isinstance(parity_spec, Mapping):
        return ParitySpec.from_bundle({'parity': parity_spec})
    return ParitySpec.from_bundle(bundle)


def _files(bundle: Mapping) -> dict:
    """``{relative_path: sha256}`` of the files a bundle document lists."""
    return {f.get('relative_path'): f.get('sha256') for f in bundle.get('files') or []
            if isinstance(f, Mapping)}


def _native_files(bundle: Mapping) -> dict:
    """The listed files of a bundle that belong to the native predictor: every file but
    those of its optional packages (``packages/<format>/...`` and their descriptors)."""
    owned = [p['relative_path'] for p in bundle.get('optional_packages') or []
             if isinstance(p, Mapping) and isinstance(p.get('relative_path'), str)]
    return {rel: sha for rel, sha in _files(bundle).items()
            if not any(rel == f'{o}.descriptor.json' or rel.startswith(o + '/')
                       for o in owned)}


def _skip(bundle_dir: Path, bundle: Mapping, out: Path, staging: Path):
    """``copytree`` filter of the native bundle copied into a package: the package being
    written (``out``, when it lies inside the bundle), the packager's staging folder, and
    the bundle's existing optional packages are left out, so a package never contains
    itself or another package."""
    excluded = {Path(os.path.realpath(p)) for p in (out, staging)}
    for package in bundle.get('optional_packages') or []:
        if isinstance(package, Mapping) and isinstance(package.get('relative_path'), str):
            excluded.add(Path(os.path.realpath(bundle_dir / package['relative_path'])))

    def ignore(folder, names):
        base = Path(os.path.realpath(folder))
        return [n for n in names if base / n in excluded]
    return ignore


def _mlflow_signature(signature: Mapping):
    from mlflow.models import ModelSignature
    from mlflow.types import ColSpec, Schema
    return ModelSignature(
        inputs=Schema([ColSpec(c['type'], c['name'], required=c['required'])
                       for c in signature['inputs']]),
        outputs=Schema([ColSpec(c['type'], c['name'], required=c['required'])
                        for c in signature['outputs']]))


def _write_mlmodel(package_dir: Path, signature: Mapping, environment: Mapping) -> None:
    """Replace the ``MLmodel`` MLflow wrote with the packager's own (:func:`mlmodel_bytes`,
    round 4). MLflow's records the clock, a random model id, the local Python version and
    the absolute paths of the wrapper source and of each artifact's origin. Its loading keys
    are checked first, so an MLflow version that would load the package otherwise is
    refused rather than silently overwritten; loading the package for parity then proves
    the packager's document loads."""
    import yaml
    path = Path(package_dir) / MLMODEL_FILE
    try:
        written = yaml.safe_load(path.read_text(encoding='utf-8'))
        pyfunc = written['flavors']['python_function']
        located = (sorted(written['flavors']), pyfunc.get('loader_module'),
                   Path(str(pyfunc.get('model_code_path'))).name, sorted(pyfunc.get('artifacts')
                                                                     or {}),
                   (pyfunc.get('artifacts') or {}).get(NATIVE_ARTIFACT, {}).get('path'),
                   pyfunc.get('data'), pyfunc.get('code'))
        found_signature = _signature_document(written.get('signature'))
    except (OSError, yaml.YAMLError, KeyError, TypeError, AttributeError) as error:
        raise PackagingError('capability_not_supported', 'The MLmodel written by this MLflow '
                             'version is not readable.', path=MLMODEL_FILE,
                             remediation='Use the MLflow version the azureml extra pins.',
                             details={'error': str(error)[:200]}) from error
    if located != (['python_function'], CODE_LOADER, WRAPPER_FILE, [NATIVE_ARTIFACT],
                   EMBEDDED_BUNDLE, None, None) or found_signature != _signature_document(
                       mlmodel_document(signature, environment)['signature']):
        raise PackagingError('capability_not_supported', 'This MLflow version writes a model '
                             'that the packager does not know how to describe.',
                             path=MLMODEL_FILE,
                             remediation='Use the MLflow version the azureml extra pins.',
                             details={'found': [str(v) for v in located]})
    path.write_bytes(mlmodel_bytes(signature, environment))


# --- the hook of capture_predictor (contract v1 §6) ------------------------------------

# Export profiles of the capture: ``base`` captures the native bundle only; ``atelier``
# (the workshop) requires the MLflow package, written before the final test is opened.
PROFILES = {'base': None, 'atelier': FORMAT}


def packager_for(profile: str, runtime=None) -> 'ArtifactPackager | None':
    """The packager to inject into ``capture_predictor(..., packager=...)`` for an export
    profile: ``None`` for ``base``; for ``atelier``, an :class:`ArtifactPackager`, or
    ``optional_dependency_missing`` **before** anything is captured when MLflow is not
    installed. Chantier A calls this known adapter lazily; no code is discovered from YAML."""
    if profile not in PROFILES:
        raise PackagingError('capability_not_supported', f'Unknown export profile {profile!r}.',
                             path='profile', remediation=f'Use one of {", ".join(PROFILES)}.')
    if PROFILES[profile] is None:
        return None
    _import('mlflow', 'the azureml extra (mlflow-skinny)')
    return ArtifactPackager(runtime)
