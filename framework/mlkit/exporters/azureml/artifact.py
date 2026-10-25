"""The captured predictor of a study, as the export transports it (spec §07, contract §5).

The export copies the native bundle that chantier A captured before the final test was
opened, after ``hypotrail_runtime.verify_bundle`` accepted it; it never fits, rebuilds or
re-packages it. The bundle's MLflow package (written by the packager hook during the
capture, in the workshop profile) is verified again with
:meth:`mlkit.integrations.mlflow_packaging.ArtifactPackager.verify` when MLflow is
installed; without MLflow that check is ``not_run`` and the artifact is reported
``captured``, never ``packaged``.

Statuses (spec §14): ``missing`` (no predictor), ``captured`` (native bundle verified),
``packaged`` (native bundle and its MLflow package verified). The evidence status comes
from the bundle's evidence binding (``evaluated``, ``unassessed``, ``stale``); a bundle
without binding is ``unassessed``, never ``evaluated``.
"""
from __future__ import annotations

import importlib
import importlib.util
import os
from pathlib import Path
from typing import Mapping

from mlkit.integrations import mlflow_packaging as mp

from . import canonical as cj
from .errors import ExportError, from_packaging
from .snapshot import PREDICTOR_ROLES, runtime

QUALIFIED_PYTHON = '3.13'
MAX_BUNDLE_BYTES = 200 * 1024 * 1024


def _json(bundle_dir: Path, relative, where: str) -> dict:
    try:
        path = mp.inside(bundle_dir, relative, where)
        return mp._read_json(path, where)
    except mp.PackagingError as error:
        raise from_packaging(error) from error


def read_files(root: Path) -> dict[str, bytes]:
    """Every file under ``root`` by POSIX relative path; a symlink or a Python bytecode
    cache (``__pycache__``, ``*.pyc``) is refused, as the runtime refuses it in a bundle."""
    out, total = {}, 0
    for path in sorted(root.rglob('*')):
        rel = path.relative_to(root).as_posix()
        if '__pycache__' in path.relative_to(root).parts or path.suffix in ('.pyc', '.pyo'):
            raise ExportError('artifact_integrity_failed', 'The bundle holds a Python bytecode '
                              'cache, written by loading its package in place.', path=rel,
                              remediation='Delete the __pycache__ folder from the bundle and '
                                          'load packages from a copy.')
        if path.is_symlink():
            raise ExportError('artifact_integrity_failed', 'The bundle holds a symbolic link.',
                              path=rel, remediation='Capture the predictor again.')
        if path.is_file():
            data = path.read_bytes()
            total += len(data)
            if total > MAX_BUNDLE_BYTES:
                raise ExportError('capability_not_supported', 'The bundle is too large to copy '
                                  'into the project.', path=rel,
                                  remediation='Reference the model as an Azure asset instead.')
            out[rel] = data
    return out


def verify_predictor(bundle_dir: Path, recipe: Mapping, contract: Mapping) -> dict:
    """The predictor record of a captured bundle, or a refusal."""
    rt = runtime('verify the captured predictor')
    if not bundle_dir.is_dir() or bundle_dir.is_symlink():
        raise ExportError('model_not_captured', 'The predictor bundle folder is missing.',
                          path='predictor.bundle_dir',
                          remediation='Capture the predictor in a training activity first.')
    try:
        rt.verify_bundle(bundle_dir)
    except Exception as error:   # the runtime refuses a bundle it cannot verify
        # The runtime's own remediation (e.g. delete a bytecode cache) reaches the user.
        remediation = getattr(error, 'remediation', None) or \
            'Capture the predictor again; never edit a bundle.'
        details = {'error': f'{type(error).__name__}: {error}'[:300]}
        if isinstance(getattr(error, 'details', None), Mapping):
            details['runtime'] = dict(error.details)
        raise ExportError('artifact_integrity_failed', 'hypotrail_runtime refused the bundle.',
                          path='predictor.bundle_dir', remediation=remediation,
                          details=details) from error
    bundle = _json(bundle_dir, mp.BUNDLE_DOCUMENT, mp.BUNDLE_DOCUMENT)
    manifest = _json(bundle_dir, bundle.get('predictor_manifest_path'), 'predictor_manifest_path')
    bundled_recipe = _json(bundle_dir, bundle.get('recipe_path'), 'recipe_path')
    bundled_contract = _json(bundle_dir, bundle.get('data_contract_path'), 'data_contract_path')
    if cj.normalise(bundled_recipe) != cj.normalise(dict(recipe)):
        raise ExportError('artifact_integrity_failed', 'The bundle was fitted with another '
                          'recipe than the selected one.', path='predictor.recipe',
                          remediation='Capture the selected recipe again; the export does not '
                                      'substitute a model.')
    if cj.normalise(bundled_contract) != cj.normalise(dict(contract)):
        raise ExportError('data_identity_mismatch', 'The bundle data contract differs from the '
                          "study's.", path='predictor.data_contract',
                          remediation='Capture the predictor again on the current contract.')
    role = (manifest.get('training_scope') or {}).get('role')
    if role not in PREDICTOR_ROLES:
        raise ExportError('contract_invalid', 'The predictor has no known training role.',
                          path='predictor.training_scope.role', remediation='Fix the engine.')
    environment = manifest.get('environment') or {}
    python = str(environment.get('python') or '')
    if not (python == QUALIFIED_PYTHON or python.startswith(QUALIFIED_PYTHON + '.')):
        raise ExportError('environment_unqualified', f'The predictor was captured under Python '
                          f'{python or "unknown"}; this template qualifies {QUALIFIED_PYTHON}.',
                          path='predictor.environment.python',
                          remediation='Capture the predictor in the qualified environment.')
    binding_path = bundle.get('evidence_binding_path')
    evidence_status, binding = 'unassessed', None
    if binding_path:
        binding = _json(bundle_dir, binding_path, 'evidence_binding_path')
        if binding.get('predictor_id') != manifest.get('predictor_id'):
            raise ExportError('artifact_integrity_failed', 'The evidence binding names another '
                              'predictor.', path='predictor.evidence_binding',
                              remediation='Never move a binding between predictors.')
        evidence_status = binding.get('status') if binding.get('status') in (
            'evaluated', 'unassessed', 'stale') else 'unassessed'
    if role == 'rebuilt_candidate' and evidence_status == 'evaluated':
        raise ExportError('artifact_integrity_failed', 'A rebuilt candidate cannot carry the '
                          'verdict of an evaluated model.', path='predictor.evidence_binding',
                          remediation='Export the evaluated predictor, not a rebuilt one.')
    checks = [{'id': 'bundle_verified', 'status': 'passed'},
              {'id': 'bundle_recipe_matches', 'status': 'passed'}]
    warnings = []
    artifact_status, package = 'captured', None
    packages = [p for p in bundle.get('optional_packages') or []
                if isinstance(p, Mapping) and p.get('format') == mp.FORMAT]
    if packages:
        package = packages[0]
        package_dir = bundle_dir / mp._relative(package.get('relative_path'),
                                                'optional_packages.relative_path')
        if importlib.util.find_spec('mlflow') is None:
            checks.append({'id': 'mlflow_package_verified', 'status': 'not_run',
                           'detail': 'MLflow is not installed in this environment.'})
            warnings.append('mlflow_package_not_verified')
        else:
            try:
                result = mp.ArtifactPackager(rt).verify(bundle_dir, package_dir)
            except mp.PackagingError as error:
                raise from_packaging(error) from error
            if result.status != 'passed':
                raise ExportError('artifact_integrity_failed', 'The MLflow package does not '
                                  'reproduce the native predictor.', path='predictor.package',
                                  remediation='Capture the predictor again with the workshop '
                                              'profile.', details={'reason': result.reason})
            checks.append({'id': 'mlflow_package_verified', 'status': 'passed'})
            artifact_status = 'packaged'
    else:
        checks.append({'id': 'mlflow_package_present', 'status': 'missing',
                       'detail': 'The bundle has no MLflow package; the native predictor is '
                                 'transported, no MLflow model is announced.'})
        warnings.append('mlflow_package_missing')
    files = read_files(bundle_dir)
    runtime_info = manifest.get('runtime') or {}
    wheel = None
    if runtime_info.get('wheel_relative_path'):
        rel = mp._relative(runtime_info['wheel_relative_path'], 'runtime.wheel_relative_path')
        if rel not in files or cj.sha256_hex(files[rel]) != runtime_info.get('wheel_sha256'):
            raise ExportError('artifact_integrity_failed', 'The runtime wheel is missing or '
                              'altered.', path='predictor.runtime.wheel_relative_path',
                              remediation='Capture the predictor again.')
        wheel = (os.path.basename(rel), files[rel])
    lock = None
    if environment.get('lock_relative_path'):
        rel = mp._relative(environment['lock_relative_path'], 'environment.lock_relative_path')
        if rel not in files or cj.sha256_hex(files[rel]) != environment.get('lock_sha256'):
            raise ExportError('artifact_integrity_failed', 'The environment lock is missing or '
                              'altered.', path='predictor.environment.lock_relative_path',
                              remediation='Capture the predictor again.')
        lock = files[rel]
    return {'predictor_id': manifest.get('predictor_id'), 'role': role,
            'evidence_status': evidence_status, 'binding': binding,
            'artifact_status': artifact_status, 'bundle': bundle, 'manifest': manifest,
            'files': files, 'wheel': wheel, 'lock': lock, 'environment': environment,
            'runtime': runtime_info,
            'package': None if package is None else {
                'relative_path': package.get('relative_path'),
                'artifact_id': package.get('artifact_id')},
            'checks': checks, 'warnings': warnings}
