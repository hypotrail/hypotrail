"""Regressions of the third review round of 25 October 2026, area A (library runtime).

R3-A1 a planted bytecode cache in the MLflow package replaced the wrapper: bytecode is now
refused anywhere in a bundle or a package, every listed package file must be named by its
descriptor, and the packager never runs package code before its integrity is established
(it loads a temporary copy with bytecode disabled). R3-A4 loading a package in place writes
a bytecode cache into the bundle: still refused, with a message that says what happened and
what to delete, and the engine's own loads never write into the bundle. R3-A2 the package's
identity: ``artifact_id`` is the content id of its descriptor, the descriptor inside the
package is the one beside it, and the environment files are regenerated and compared.
R3-A3 an edited MLmodel signature is a packaging refusal, never a raw MLflow exception.
R3-A5 an empty or relative trusted root is refused. R3-A6 a torn last line of the
calibration ledger is repaired by the next claim (reported), any other corruption is
``contract_invalid``. Ported from the reviewer's probes; every bundle, study and ledger
lives in ``tmp_path`` and the data are synthetic.
"""
from __future__ import annotations

import importlib.util
import json
import os
import py_compile
import shutil
import subprocess
import sys
import warnings
from pathlib import Path

import numpy as np
import pytest

from hypotrail_runtime import canonical, capture_predictor, load_predictor, verify_bundle
from hypotrail_runtime.errors import ContractError

import test_review_round2_a as r2

PKG = r2.PKG
needs_mlflow, needs_mapie = r2.needs_mlflow, r2.needs_mapie

EVIL = '''
import os
from pathlib import Path
import mlflow.pyfunc
import pandas as pd
from mlflow.models import set_model

MARKER = os.environ.get("R3_MARKER")


class HypotrailPredictor(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        import hypotrail_runtime
        bundle = Path(context.artifacts["native_bundle"]).resolve()
        self._predictor = hypotrail_runtime.load_predictor(bundle, trusted_roots=[bundle])
        if MARKER:
            Path(MARKER).write_text("evil wrapper ran")

    def predict(self, context, model_input, params=None):
        batch = self._predictor.predict(model_input)
        values = list(batch.values)
        band = list(model_input["band"]) if "band" in model_input else [0] * len(values)
        values = [v + (0.4 if b == 3 else 0.0) for v, b in zip(values, band)]
        frame = pd.DataFrame({list(batch.columns)[0]: values})
        frame.index = list(batch.row_order)
        return frame.sort_index().reset_index(drop=True)


set_model(HypotrailPredictor())
'''


def _workshop(tmp_path):
    from mlkit.integrations import mlflow_packaging as mp
    dest = tmp_path / 'trusted' / 'b'
    d = capture_predictor(r2._fitted(), None, r2._parity(), dest, mp.packager_for('atelier'),
                          code_fingerprint=r2.FP)
    return mp, dest, d


def _plant_pyc(tmp_path, pkg: Path) -> Path:
    """A bytecode cache of another wrapper where MLflow's import looks for it (unchecked
    hash: Python never compares it with the source)."""
    src = tmp_path / 'evil_src' / 'hypotrail_pyfunc.py'
    src.parent.mkdir(exist_ok=True)
    src.write_text(EVIL)
    cache = Path(importlib.util.cache_from_source(str(pkg / 'hypotrail_pyfunc.py')))
    cache.parent.mkdir(exist_ok=True)
    py_compile.compile(str(src), cfile=str(cache), doraise=True,
                       invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
    return cache


def _list_in_bundle_document(dest: Path, path: Path) -> None:
    doc = json.loads((dest / 'predictor_bundle.json').read_bytes())
    rel = path.relative_to(dest).as_posix()
    doc['files'].append({'relative_path': rel, 'size_bytes': path.stat().st_size,
                         'sha256': canonical.file_sha256(path)})
    doc['files'].sort(key=lambda e: e['relative_path'])
    (dest / 'predictor_bundle.json').write_bytes(canonical.dumps(doc) + b'\n')


def _export_record(dest):
    from mlkit.exporters.azureml.artifact import verify_predictor
    recipe = json.loads((dest / 'recipe.json').read_bytes())
    contract = json.loads((dest / 'data_contract.json').read_bytes())
    return verify_predictor(dest, recipe, contract)


def _export_refused(dest):
    from mlkit.exporters.azureml.errors import ExportError
    with pytest.raises(ExportError) as err:
        _export_record(dest)
    assert 'artifact_integrity_failed' in (err.value.code,
                                           (err.value.details or {}).get('contract_code'))
    return err.value


def _packaging_refused(fn, *args, code='artifact_integrity_failed'):
    from mlkit.integrations import mlflow_packaging as mp
    with pytest.raises(mp.PackagingError) as e:
        fn(*args)
    assert e.value.code == code, e.value.to_dict()
    return e.value


def _no_bytecode(root: Path) -> None:
    assert not [p for p in root.rglob('*') if '__pycache__' in p.parts
                or p.suffix in ('.pyc', '.pyo')]


# --- R3-A1: a bytecode cache never replaces the wrapper ----------------------------------------

@needs_mlflow
@pytest.mark.parametrize('listed', [True, False], ids=['listed', 'unlisted'])
def test_a_planted_bytecode_cache_is_refused_and_never_runs(tmp_path, monkeypatch, listed):
    """Reviewer probe: a planted ``__pycache__/hypotrail_pyfunc.cpython-*.pyc`` (listed in the
    bundle document or not). Before the fix verify_bundle, ArtifactPackager.verify (which ran
    the planted code) and the export passed, and the package served another model."""
    mp, dest, d = _workshop(tmp_path)
    pkg = dest / PKG
    cache = _plant_pyc(tmp_path, pkg)
    if listed:
        _list_in_bundle_document(dest, cache)
    marker = tmp_path / 'marker.txt'
    monkeypatch.setenv('R3_MARKER', str(marker))
    assert (pkg / mp.WRAPPER_FILE).read_bytes() == mp.WRAPPER_SOURCE.encode()
    e = r2._refused(verify_bundle, dest)
    folder = f'{PKG}/__pycache__'
    assert e.details['bytecode_folders'] == [folder]
    assert folder in e.message and 'bytecode' in e.message
    assert f'Delete {folder}' in e.remediation
    r2._refused(load_predictor, dest, trusted_roots=[dest.parent])
    err = _packaging_refused(mp.ArtifactPackager().verify, dest, pkg)
    assert err.details['contract_code'] == 'artifact_integrity_failed'
    assert not marker.exists(), 'the planted code ran during verify'
    _export_refused(dest)
    assert not marker.exists()
    shutil.rmtree(pkg / '__pycache__')                  # removed: the bundle is the same again
    if listed:
        doc = json.loads((dest / 'predictor_bundle.json').read_bytes())
        doc['files'] = [f for f in doc['files'] if '__pycache__' not in f['relative_path']]
        (dest / 'predictor_bundle.json').write_bytes(canonical.dumps(doc) + b'\n')
    assert verify_bundle(dest).predictor_id == d.predictor_id
    assert mp.ArtifactPackager().verify(dest, pkg).status == 'passed'
    assert not marker.exists()


@needs_mlflow
def test_a_planted_cache_in_a_package_outside_a_bundle_is_refused_before_loading(tmp_path,
                                                                                  monkeypatch):
    """The packager's own check (a package outside the bundle, the runtime does not see it):
    the cache is refused, never skipped, and nothing from the package runs."""
    from mlkit.integrations import mlflow_packaging as mp
    native = tmp_path / 'native'
    capture_predictor(r2._fitted(), None, r2._parity(), native, None, code_fingerprint=r2.FP)
    package = tmp_path / 'package'
    mp.ArtifactPackager().package(native, package)
    _plant_pyc(tmp_path, package)
    marker = tmp_path / 'marker.txt'
    monkeypatch.setenv('R3_MARKER', str(marker))
    err = _packaging_refused(mp.ArtifactPackager().verify, native, package)
    assert err.details['bytecode_folders'] == ['__pycache__']
    assert not marker.exists()
    with pytest.raises(mp.PackagingError):
        mp._inventory(package)                      # refused, never skipped
    stray = package / 'artifacts' / 'stray.pyc'
    shutil.rmtree(package / '__pycache__')
    stray.write_bytes(b'\x00')
    err = _packaging_refused(mp.ArtifactPackager().verify, native, package)
    assert err.details['bytecode_files'] == ['artifacts/stray.pyc']


@needs_mlflow
def test_a_planted_cache_in_the_embedded_bundle_is_refused(tmp_path):
    mp, dest, _ = _workshop(tmp_path)
    folder = dest / PKG / 'artifacts' / 'native_bundle' / '__pycache__'
    folder.mkdir()
    (folder / 'x.cpython-313.pyc').write_bytes(b'\x00')
    e = r2._refused(verify_bundle, dest)
    assert e.details['bytecode_folders'] == [f'{PKG}/artifacts/native_bundle/__pycache__']


def test_bytecode_anywhere_in_a_bundle_is_refused(tmp_path):
    """Without MLflow too: a ``.pyc`` file or a ``__pycache__`` folder, listed or not, in the
    native part of the bundle or under evidence/."""
    dest = tmp_path / 'b'
    capture_predictor(r2._fitted(), None, r2._parity(), dest, None, code_fingerprint=r2.FP)
    for rel in ('payload/model.cpython-313.pyc', 'evidence/__pycache__/x.pyc', 'runtime/a.pyo'):
        path = dest / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'\x00')
        e = r2._refused(verify_bundle, dest)
        assert rel in e.details['bytecode_files'] or \
            rel.rpartition('/')[0] in e.details['bytecode_folders']
        path.unlink()
        if path.parent.name == '__pycache__':
            path.parent.rmdir()
    assert verify_bundle(dest).predictor_id


def test_every_listed_package_file_is_named_by_its_descriptor(tmp_path):
    """A file added under ``packages/<format>/`` and listed in the bundle document only (the
    document is not bound to the predictor id) is refused."""
    from mlkit.contracts.testing_packager import SyntheticPackager
    dest = tmp_path / 'b'
    capture_predictor(r2._fitted(), None, r2._parity(), dest, SyntheticPackager(),
                      code_fingerprint=r2.FP)
    extra = dest / 'packages' / 'synthetic_test' / 'notes.txt'
    extra.write_text('not described')
    _list_in_bundle_document(dest, extra)
    e = r2._refused(verify_bundle, dest)
    assert e.details['files'] == ['packages/synthetic_test/notes.txt']
    assert 'does not name' in e.message


# --- R3-A4: loading a package in place ---------------------------------------------------------

@needs_mlflow
def test_loading_the_package_in_place_is_refused_with_what_to_delete(tmp_path):
    """Loading the package as MLflow documents it, inside the bundle, writes a bytecode cache
    there: the bundle is refused (correctly), and the message says what happened, what to
    delete and to load packages from a copy. Deleting the folder restores the bundle."""
    mp, dest, d = _workshop(tmp_path)
    code = ('import mlflow.pyfunc, sys; sys.dont_write_bytecode=False; '
            f'mlflow.pyfunc.load_model({str(dest / PKG)!r})')
    env = {k: v for k, v in os.environ.items() if k not in ('PYTHONDONTWRITEBYTECODE',
                                                             'PYTHONPYCACHEPREFIX')}
    env['PYTHONPATH'] = os.pathsep.join(sys.path)
    subprocess.run([sys.executable, '-c', code], check=True, env=env, capture_output=True)
    assert list((dest / PKG).rglob('*.pyc')), 'no bytecode written'
    e = r2._refused(verify_bundle, dest)
    folder = f'{PKG}/__pycache__'
    assert e.path == folder
    assert 'A Python bytecode cache was written into the bundle' in e.message
    assert 'loading its package in place' in e.message and folder in e.message
    assert e.remediation.startswith(f'Delete {folder}')
    assert 'from a copy of its folder, never from inside the bundle' in e.remediation
    shutil.rmtree(dest / PKG / '__pycache__')
    assert verify_bundle(dest).predictor_id == d.predictor_id


@needs_mlflow
def test_the_engine_s_own_loads_never_write_into_the_bundle(tmp_path, monkeypatch):
    """ArtifactPackager.verify loads the package for parity from a temporary copy with
    bytecode disabled: nothing is written into the bundle even when the interpreter writes
    bytecode, and the interpreter's settings are restored."""
    mp, dest, d = _workshop(tmp_path)
    monkeypatch.setattr(sys, 'dont_write_bytecode', False)
    monkeypatch.setattr(sys, 'pycache_prefix', None)
    before = {p.relative_to(dest).as_posix(): canonical.file_sha256(p)
              for p in dest.rglob('*') if p.is_file()}
    assert mp.ArtifactPackager().verify(dest, dest / PKG).status == 'passed'
    _export_record(dest)
    after = {p.relative_to(dest).as_posix(): canonical.file_sha256(p)
             for p in dest.rglob('*') if p.is_file()}
    assert after == before
    _no_bytecode(dest)
    assert sys.dont_write_bytecode is False and sys.pycache_prefix is None
    assert verify_bundle(dest).predictor_id == d.predictor_id


# --- R3-A2: the package's identity -------------------------------------------------------------

@needs_mlflow
def test_artifact_id_is_the_content_id_and_the_descriptors_are_identical(tmp_path):
    mp, dest, d = _workshop(tmp_path)
    pkg = dest / PKG
    package = d.packages[0]
    assert package.artifact_id == canonical.artifact_id(package, exclude=('artifact_id',))
    outer = (dest / f'{PKG}.descriptor.json').read_bytes()
    assert (pkg / mp.DESCRIPTOR_FILE).read_bytes() == outer
    assert json.loads(outer)['extensions']['hypotrail.descriptor_copy'] == mp.DESCRIPTOR_FILE
    # The environment files are the packager's, from the bundle's pinned environment only.
    environment = json.loads(outer)['environment']
    for name, data in mp.environment_files(environment).items():
        assert (pkg / name).read_bytes() == data
    assert (pkg / 'requirements.txt').read_text().splitlines() == \
        environment['pip_requirements']
    assert 'pip==' not in (pkg / 'python_env.yaml').read_text()


@needs_mlflow
def test_a_relabelled_package_keeps_no_artifact_id_it_does_not_hash_to(tmp_path):
    """Reviewer probe, first half: requirements.txt edited (another runtime) and the file
    lists re-described, the artifact id kept. The runtime now recomputes the id."""
    mp, dest, d = _workshop(tmp_path)
    pkg = dest / PKG
    original = d.packages[0].artifact_id
    req = pkg / 'requirements.txt'
    req.write_text('hypotrail-runtime @ https://example.invalid/evil-1.0.0-py3-none-any.whl\n'
                   + req.read_text())
    r2._redescribe_mlflow_package(dest)
    for rel in (f'{PKG}/{mp.DESCRIPTOR_FILE}', f'{PKG}.descriptor.json'):
        doc = json.loads((dest / rel).read_bytes())
        doc['artifact_id'] = original
        (dest / rel).write_bytes(canonical.dumps(doc) + b'\n')
    doc = json.loads((dest / 'predictor_bundle.json').read_bytes())
    doc['optional_packages'][0]['artifact_id'] = original
    sha = canonical.file_sha256(dest / f'{PKG}.descriptor.json')
    doc['optional_packages'][0]['manifest_sha256'] = sha
    for e in doc['files']:
        if e['relative_path'] in (f'{PKG}/{mp.DESCRIPTOR_FILE}', f'{PKG}.descriptor.json'):
            e['sha256'] = canonical.file_sha256(dest / e['relative_path'])
            e['size_bytes'] = (dest / e['relative_path']).stat().st_size
    (dest / 'predictor_bundle.json').write_bytes(canonical.dumps(doc) + b'\n')
    e = r2._refused(verify_bundle, dest)
    assert 'content id' in e.message and e.details['recorded'] == original
    _packaging_refused(mp.ArtifactPackager().verify, dest, pkg)
    _export_refused(dest)


@needs_mlflow
@pytest.mark.parametrize('name', ['requirements.txt', 'conda.yaml', 'python_env.yaml'])
def test_environment_files_pointing_elsewhere_are_refused(tmp_path, name):
    """Reviewer probe, second half: an environment file that installs another runtime, the
    package re-described everywhere with a recomputed artifact id. The runtime cannot know
    MLflow's files; the packager regenerates them and refuses, and so does the export."""
    mp, dest, _ = _workshop(tmp_path)
    pkg = dest / PKG
    path = pkg / name
    text = path.read_text()
    if name == 'requirements.txt':
        text = 'hypotrail-runtime @ https://example.invalid/evil-1.0.0-py3-none-any.whl\n' + text
    else:
        # Round 5 (R5-A1): conda.yaml installs the embedded runtime wheel by its path; the
        # probe makes it install a runtime of the same version from an index instead.
        wheel = ('./artifacts/native_bundle/runtime/hypotrail_runtime-1.0.0-py3-none-any.whl')
        assert wheel in text or name == 'python_env.yaml'
        text = text.replace(wheel, 'hypotrail-runtime==1.0.0') \
            .replace('- -r requirements.txt', '- -r other.txt')
    path.write_text(text)
    r2._redescribe_mlflow_package(dest)
    verify_bundle(dest)                         # consistent everywhere the runtime looks
    err = _packaging_refused(mp.ArtifactPackager().verify, dest, pkg)
    assert err.path == name
    assert 'environment file' in err.message
    _export_refused(dest)


@needs_mlflow
def test_a_descriptor_environment_that_is_not_the_bundle_s_is_refused(tmp_path):
    mp, dest, _ = _workshop(tmp_path)
    pkg = dest / PKG
    doc = json.loads((pkg / mp.DESCRIPTOR_FILE).read_bytes())
    doc['environment'] = {**doc['environment'],
                          'pip_requirements': doc['environment']['pip_requirements'][:-1]}
    (pkg / mp.DESCRIPTOR_FILE).write_bytes(canonical.dumps(doc) + b'\n')
    r2._redescribe_mlflow_package(dest)
    verify_bundle(dest)
    err = _packaging_refused(mp.ArtifactPackager().verify, dest, pkg)
    assert 'pinned environment' in err.message


@needs_mlflow
def test_inner_and_outer_descriptors_must_agree(tmp_path):
    """Reviewer probe: the descriptor beside the package edited (signature, environment) and
    re-hashed in the bundle document. Refused for its artifact id; with the id recomputed
    too, refused because the descriptor inside the package differs."""
    mp, dest, _ = _workshop(tmp_path)
    desc_path = dest / f'{PKG}.descriptor.json'

    def rewrite(recompute):
        desc = json.loads(desc_path.read_bytes())
        desc['signature'] = {'inputs': [], 'note': 'not what the package says'}
        desc['environment'] = {'python': '2.7'}
        if recompute:
            desc['artifact_id'] = canonical.artifact_id(desc, exclude=('artifact_id',))
        desc_path.write_bytes(canonical.dumps(desc) + b'\n')
        doc = json.loads((dest / 'predictor_bundle.json').read_bytes())
        sha = canonical.file_sha256(desc_path)
        doc['optional_packages'][0]['manifest_sha256'] = sha
        doc['optional_packages'][0]['artifact_id'] = desc['artifact_id']
        for e in doc['files']:
            if e['relative_path'] == f'{PKG}.descriptor.json':
                e['sha256'], e['size_bytes'] = sha, desc_path.stat().st_size
        (dest / 'predictor_bundle.json').write_bytes(canonical.dumps(doc) + b'\n')
    rewrite(recompute=False)
    e = r2._refused(verify_bundle, dest)
    assert 'content id' in e.message
    rewrite(recompute=True)
    e = r2._refused(verify_bundle, dest)
    assert e.path == f'{PKG}/{mp.DESCRIPTOR_FILE}'
    assert 'differs from the one beside it' in e.message
    _packaging_refused(mp.ArtifactPackager().verify, dest, dest / PKG)
    _export_refused(dest)


# --- R3-A3: every exception of verify is a packaging refusal -----------------------------------

@needs_mlflow
def test_an_edited_mlmodel_signature_is_a_packaging_refusal(tmp_path):
    """Reviewer probe: the MLmodel signature edited (long columns as double) and the package
    re-described. Before the fix ArtifactPackager.verify raised a raw MlflowException; now
    _check_embedded compares the signature with the bundle's before anything is loaded."""
    import yaml
    mp, dest, _ = _workshop(tmp_path)
    pkg = dest / PKG
    model = yaml.safe_load((pkg / 'MLmodel').read_text())
    sig = json.loads(model['signature']['inputs'])
    changed = 0
    for col in sig:
        if col['type'] == 'long':
            col['type'] = 'double'
            changed += 1
    assert changed
    model['signature']['inputs'] = json.dumps(sig)
    (pkg / 'MLmodel').write_text(yaml.safe_dump(model, sort_keys=True))
    r2._redescribe_mlflow_package(dest)
    verify_bundle(dest)
    err = _packaging_refused(mp.ArtifactPackager().verify, dest, pkg)
    assert 'signature' in err.message
    _export_refused(dest)


@needs_mlflow
def test_an_mlflow_failure_inside_verify_is_a_packaging_refusal(tmp_path, monkeypatch):
    import mlflow.pyfunc
    from mlflow.exceptions import MlflowException
    mp, dest, _ = _workshop(tmp_path)

    def broken(*args, **kwargs):
        raise MlflowException('simulated loader failure')
    monkeypatch.setattr(mlflow.pyfunc, 'load_model', broken)
    err = _packaging_refused(mp.ArtifactPackager().verify, dest, dest / PKG)
    assert 'MlflowException' in err.message and err.details['error_type'] == 'MlflowException'


@needs_mlflow
def test_a_runtime_refusal_inside_verify_keeps_its_contract_code(tmp_path):
    from mlkit.integrations import mlflow_packaging as mp
    empty = tmp_path / 'not-a-bundle'
    empty.mkdir()
    err = _packaging_refused(mp.ArtifactPackager().verify, empty, empty / PKG,
                             code='model_not_captured')
    assert err.details['contract_code'] == 'model_not_captured'


# --- R3-A5: trusted roots are absolute ---------------------------------------------------------

@pytest.mark.parametrize('roots', [[''], ['.'], ['somewhere'], [Path('')], [Path('rel/dir')]])
def test_an_empty_or_relative_trusted_root_is_refused(tmp_path, monkeypatch, roots):
    """Reviewer probe: ``trusted_roots=['']`` trusted the working directory."""
    dest = tmp_path / 'somewhere' / 'b'
    capture_predictor(r2._fitted(), None, r2._parity(), dest, None, code_fingerprint=r2.FP)
    monkeypatch.delenv('HYPOTRAIL_RUNTIME_TRUSTED_ROOTS', raising=False)
    monkeypatch.chdir(tmp_path)
    e = r2._refused(load_predictor, dest, trusted_roots=roots, code='contract_invalid')
    assert e.path == 'trusted_roots'
    assert load_predictor(dest, trusted_roots=[tmp_path]).predictor_id


def test_relative_entries_of_the_variable_trust_nothing(tmp_path, monkeypatch):
    dest = tmp_path / 'somewhere' / 'b'
    capture_predictor(r2._fitted(), None, r2._parity(), dest, None, code_fingerprint=r2.FP)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('HYPOTRAIL_RUNTIME_TRUSTED_ROOTS', os.pathsep.join(['', '.', 'somewhere']))
    r2._refused(load_predictor, dest)
    monkeypatch.setenv('HYPOTRAIL_RUNTIME_TRUSTED_ROOTS', str(tmp_path / 'somewhere'))
    assert load_predictor(dest).predictor_id


# --- R3-A6: the calibration ledger is read strictly ---------------------------------------------

@needs_mapie
def test_a_torn_last_ledger_line_is_repaired_by_the_next_claim(tmp_path):
    """Reviewer probe: a torn append made every later claim fail with a raw
    json.JSONDecodeError. The torn last line is ignored for reading, and the next claim
    removes it atomically under the lock, says so, and appends after it."""
    from mlkit.integrations import mapie_uncertainty as mu
    path = tmp_path / 'ledger.jsonl'
    led = mu.CalibrationLedger(path)
    rows = ['r1', 'r2']
    first = led.claim(r2._ref(rows), r2.PROC_A, keys=rows)
    complete = path.read_bytes()
    torn = b'{"schema": "hypotrail.calibration_use/1", "calibr'
    with open(path, 'ab') as fh:
        fh.write(torn)
    assert led.uses() == [first]                         # ignored for reading
    with pytest.warns(mu.LedgerRepaired) as caught:
        use = led.claim(r2._ref(['q1']), r2.PROC_B, keys=['q1'])
    assert caught[0].message.details['line'] == 2
    assert caught[0].message.details['size_bytes'] == len(torn)
    assert led.repairs == [caught[0].message.details]
    data = path.read_bytes()
    assert data.startswith(complete) and torn not in data
    assert data == complete + canonical.dumps(use) + b'\n'
    assert led.uses() == [first, use]
    _refused_rows = r2._refused(led.claim, r2._ref(rows, 'x'), r2.PROC_B, keys=rows,
                                code='calibration_not_eligible')   # still fails closed
    assert _refused_rows.details['reason'] == 'same_rows'
    with warnings.catch_warnings():
        warnings.simplefilter('error')                    # no repair the second time
        assert led.claim(r2._ref(rows), r2.PROC_A, keys=rows) == first


@needs_mapie
@pytest.mark.parametrize('corruption', ['middle_line', 'record_without_newline',
                                        'not_a_record', 'bad_digests'])
def test_any_other_ledger_corruption_is_contract_invalid(tmp_path, corruption):
    from mlkit.integrations import mapie_uncertainty as mu
    path = tmp_path / 'ledger.jsonl'
    led = mu.CalibrationLedger(path)
    led.claim(r2._ref(['r1']), r2.PROC_A, keys=['r1'])
    good = path.read_bytes()
    if corruption == 'middle_line':
        path.write_bytes(good + b'{"schema": "hypo\n' + good)
    elif corruption == 'record_without_newline':
        path.write_bytes(good + b'{"schema": "other"}')        # complete JSON, not a use
    elif corruption == 'not_a_record':
        path.write_bytes(good + b'[1, 2]\n')
    else:
        doc = json.loads(good)
        doc['row_digests'] = 'abc'
        path.write_bytes(good + canonical.dumps(doc) + b'\n')
    before = path.read_bytes()
    for call in (led.uses, lambda: led.claim(r2._ref(['q1']), r2.PROC_B, keys=['q1'])):
        with pytest.raises(ContractError) as e:
            call()
        assert e.value.code == 'contract_invalid'
        assert e.value.remediation and 'ledger' in e.value.message
    assert path.read_bytes() == before                    # nothing claimed, nothing repaired


@needs_mapie
def test_a_complete_last_use_without_its_newline_is_kept(tmp_path):
    from mlkit.integrations import mapie_uncertainty as mu
    path = tmp_path / 'ledger.jsonl'
    led = mu.CalibrationLedger(path)
    first = led.claim(r2._ref(['r1']), r2.PROC_A, keys=['r1'])
    path.write_bytes(path.read_bytes().rstrip(b'\n'))
    assert led.uses() == [first]
    r2._refused(led.claim, r2._ref(['r1'], 'x'), r2.PROC_B, keys=['r1'],
                code='calibration_not_eligible')
    second = led.claim(r2._ref(['q1']), r2.PROC_B, keys=['q1'])
    assert led.uses() == [first, second]
    assert path.read_bytes().count(b'\n') == 2


# --- Round 3, from area B: non-finite feature values --------------------------------------------

@pytest.mark.parametrize('value', [np.inf, -np.inf])
@pytest.mark.parametrize('stage', ['predict', 'loaded', 'fit'])
def test_a_non_finite_feature_value_is_contract_invalid(tmp_path, value, stage):
    """``inf``/``-inf`` in a numeric feature reached scikit-learn and raised a raw
    ValueError; it is now ``contract_invalid`` with the issue ``{path: input/<col>, kind:
    non_finite_values, n_rows, rows}`` (the shape the exported project uses). NaN keeps its
    handling: a missing value of a nullable column is predicted as before."""
    from hypotrail_runtime import fit_predictor
    import docs_v1
    rows = r2._frame(12, 5, with_target=stage == 'fit')
    rows.loc[[2, 7], 'age'] = value
    rows.loc[4, 'age'] = np.nan
    if stage == 'fit':
        call = lambda: fit_predictor(docs_v1.recipe(), docs_v1.contract(), rows, r2.SCOPE)  # noqa
    else:
        model = r2._fitted()
        if stage == 'loaded':
            dest = tmp_path / 'b'
            capture_predictor(model, None, r2._parity(), dest, None, code_fingerprint=r2.FP)
            model = load_predictor(dest, trusted_roots=[tmp_path])
        call = lambda: model.predict(rows)  # noqa: E731
    with pytest.raises(ContractError) as e:
        call()
    assert e.value.code == 'contract_invalid'
    issue = next(i for i in e.value.issues if i['kind'] == 'non_finite_values')
    assert {k: issue[k] for k in ('path', 'kind', 'n_rows', 'rows')} == {
        'path': 'input/age', 'kind': 'non_finite_values', 'n_rows': 2, 'rows': [2, 7]}
    finite = rows.drop(index=[2, 7]).reset_index(drop=True)
    if stage != 'fit':
        out = model.predict(finite)
        assert len(out.values) == len(finite) and np.isfinite(out.values).all()
