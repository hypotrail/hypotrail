"""Regressions of the ninth review round of 25 October 2026, area AB (library runtime).

R9AB-2 the installed-runtime check compared the wheel's members and skipped every Python
bytecode file, so code that the import system runs instead of a bound source was never
compared: a sourceless ``hypotrail_runtime/predictor/__init__.pyc`` (a package folder is
tried before ``predictor.py``) or an unchecked-hash pyc in ``__pycache__`` served other
scores under the evaluated predictor id. Bytecode outside ``__pycache__`` is now counted as
an unexpected file, and so is a cache file this interpreter would run without validating it
against its source; a validated cache (timestamp, checked hash) is still ignored.
R9AB-3 MLflow 3.17 copies the working directory's uv project files into a package it saves,
which the package allowlist refuses: a capture from a uv project failed. The packager names
an empty folder as the uv project, and the package is byte-identical from any directory.
R9AB-4 the calibration eligibility checked overlap with four named partitions only and
ignored the engine's own names (``validation``, ``fold_k``, ``development``).
Ported from the reviewer's probes; every bundle and runtime copy lives in ``tmp_path``.
"""
from __future__ import annotations

import importlib.util
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

import hypotrail_runtime
from hypotrail_runtime import capture_predictor, check_parity, load_predictor
from hypotrail_runtime import wheel as runtime_wheel
from mlkit.integrations import mapie_uncertainty as mu

import test_review_round2_a as r2
import test_review_round5_a as r5

PKG = r2.PKG
needs_mlflow = r2.needs_mlflow
RUNTIME_SOURCE = Path(hypotrail_runtime.__file__).resolve().parent
SCORE_LINE = r5.SCORE_LINE
INVERTED = r5.INVERTED


def _runtime_copy(tmp_path: Path, name: str) -> Path:
    """A copy of the installed runtime (sources only) under ``tmp_path/name``; returns the
    folder to put on ``sys.path``."""
    root = tmp_path / name
    shutil.copytree(RUNTIME_SOURCE, root / 'hypotrail_runtime',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo'))
    return root


def _inverted_source(tmp_path: Path, *, absolute: bool) -> Path:
    """``predictor.py`` with the positive-class score inverted (written outside the copy);
    with ``absolute``, its relative imports made absolute so it can be a package's
    ``__init__``."""
    text = (RUNTIME_SOURCE / 'predictor.py').read_text()
    assert text.count(SCORE_LINE) == 1
    text = text.replace(SCORE_LINE, INVERTED)
    if absolute:
        text = re.sub(r'from \. import', 'from hypotrail_runtime import', text)
        text = re.sub(r'from \.(\w+) import', r'from hypotrail_runtime.\1 import', text)
    path = tmp_path / ('predictor_absolute.py' if absolute else 'predictor_inverted.py')
    path.write_text(text)
    return path


def _compile(source: Path, target: Path, mode) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    py_compile.compile(str(source), cfile=str(target), doraise=True, invalidation_mode=mode)


def _cache(root: Path, module: str = 'predictor') -> Path:
    """The cache file the import system reads for ``hypotrail_runtime/<module>.py``."""
    source = root / 'hypotrail_runtime' / f'{module}.py'
    environment_prefix = sys.pycache_prefix
    try:
        sys.pycache_prefix = None
        return Path(importlib.util.cache_from_source(str(source)))
    finally:
        sys.pycache_prefix = environment_prefix


PROBE = textwrap.dedent('''
    import json, sys
    from pathlib import Path
    import hypotrail_runtime as rt
    bundle = Path(sys.argv[1])
    out = {"predictor_module": rt.predictor.__file__}
    try:
        predictor = rt.load_predictor(bundle, trusted_roots=[bundle.resolve()])
        out["parity"] = rt.check_parity(predictor).status
    except rt.ContractError as error:
        out["refused"] = error.code
        out["details"] = error.details
    print(json.dumps(out))
''')


def _probe(tmp_path: Path, bundle: Path, runtime_root: Path, *flags: str) -> dict:
    """``load_predictor`` in a fresh process whose ``hypotrail_runtime`` is ``runtime_root``'s
    (no bytecode written, no cache prefix: the import system reads ``__pycache__``)."""
    script = tmp_path / 'probe.py'
    script.write_text(PROBE)
    environment = {k: v for k, v in os.environ.items()
                   if k not in ('PYTHONPATH', 'PYTHONPYCACHEPREFIX')}
    environment.update(PYTHONPATH=str(runtime_root), PYTHONDONTWRITEBYTECODE='1',
                       PYTHONWARNINGS='ignore', MLFLOW_DISABLE_AGENT_HINT='1')
    result = subprocess.run([sys.executable, *flags, str(script), str(bundle)],
                            capture_output=True, text=True, cwd=tmp_path, env=environment,
                            timeout=600)
    assert result.returncode == 0, result.stderr[-3000:]
    return json.loads(result.stdout.strip().splitlines()[-1])


@pytest.fixture
def bundle(tmp_path):
    dest = tmp_path / 'bundle'
    capture_predictor(r2._fitted(), None, r2._parity(), dest, None, code_fingerprint=r2.FP)
    return dest


# --- R9AB-2: bytecode that runs instead of a bound source is compared ------------------------

def test_a_sourceless_package_shadowing_a_bound_module_is_refused(tmp_path, bundle):
    """The reviewer's probe: ``predictor/__init__.pyc`` beside an untouched ``predictor.py``.
    The import system loads the bytecode package (the probe proves it), and the runtime
    refuses to score with it: ``predictor/__init__.pyc`` is an unexpected file."""
    root = _runtime_copy(tmp_path, 'sourceless')
    _compile(_inverted_source(tmp_path, absolute=True),
             root / 'hypotrail_runtime' / 'predictor' / '__init__.pyc',
             py_compile.PycInvalidationMode.UNCHECKED_HASH)
    out = _probe(tmp_path, bundle, root)
    assert out['predictor_module'].endswith('predictor/__init__.pyc')
    assert out['refused'] == 'environment_unqualified', out
    assert out['details']['reason'] == 'runtime_not_bound'
    assert out['details']['unexpected'] == ['predictor/__init__.pyc']
    assert out['details']['changed'] == out['details']['missing'] == []


@pytest.mark.parametrize('name', ['predictor.pyc', 'extra.pyc', 'extra.pyo',
                                  'schemas/stray.pyc'])
def test_bytecode_outside_the_cache_folder_is_an_unexpected_file(tmp_path, bundle,
                                                                 monkeypatch, name):
    """Any ``*.pyc``/``*.pyo`` outside ``__pycache__`` counts, whatever its content: a
    sourceless module can be imported by its name, and no wheel of the runtime holds one."""
    root = _runtime_copy(tmp_path, 'stray') / 'hypotrail_runtime'
    (root / name).parent.mkdir(parents=True, exist_ok=True)
    (root / name).write_bytes(b'not even bytecode')
    assert runtime_wheel.sourceless_bytecode(name)
    r5._point_at(monkeypatch, root)
    e = r2._refused(load_predictor, bundle, trusted_roots=[bundle],
                    code='environment_unqualified')
    assert e.details['unexpected'] == [name]
    assert name in e.message


def test_an_unchecked_hash_cache_of_a_bound_source_is_refused(tmp_path, bundle):
    """The reviewer's second probe: an unchecked-hash pyc in ``__pycache__`` is run whatever
    ``predictor.py`` holds (no invalidation applies); it is now an unexpected file."""
    root = _runtime_copy(tmp_path, 'unchecked')
    cache = _cache(root)
    _compile(_inverted_source(tmp_path, absolute=False), cache,
             py_compile.PycInvalidationMode.UNCHECKED_HASH)
    out = _probe(tmp_path, bundle, root)
    assert out['refused'] == 'environment_unqualified', out
    assert out['details']['unexpected'] == [f'__pycache__/{cache.name}']


def test_a_cache_python_validates_is_ignored(tmp_path, bundle):
    """A timestamp pyc and a checked-hash pyc are compared with their source by the import
    system itself: one of altered code is not run (the source is), one of the bound code is
    the bound code. Neither is counted, so the runtime loads and reproduces its parity rows."""
    root = _runtime_copy(tmp_path, 'validated')
    package = root / 'hypotrail_runtime'
    # Altered code: a checked-hash pyc, and a timestamp pyc of a source of another size.
    _compile(_inverted_source(tmp_path, absolute=False), _cache(root),
             py_compile.PycInvalidationMode.CHECKED_HASH)
    longer = tmp_path / 'preprocess_altered.py'
    longer.write_text((package / 'preprocess.py').read_text() + '\nraise SystemExit(3)\n')
    _compile(longer, _cache(root, 'preprocess'), py_compile.PycInvalidationMode.TIMESTAMP)
    # The bound code: valid caches the import system uses.
    _compile(package / 'canonical.py', _cache(root, 'canonical'),
             py_compile.PycInvalidationMode.CHECKED_HASH)
    _compile(package / 'inference.py', _cache(root, 'inference'),
             py_compile.PycInvalidationMode.TIMESTAMP)
    for module in ('predictor', 'preprocess', 'canonical', 'inference'):
        assert runtime_wheel.unvalidated_bytecode(package / f'{module}.py') is None or \
            sys.pycache_prefix is not None
    out = _probe(tmp_path, bundle, root)
    assert out.get('parity') == 'ok', out


def test_a_checked_hash_cache_counts_when_python_does_not_check_it(tmp_path, bundle):
    """Under ``--check-hash-based-pycs never`` a checked-hash pyc is run without its source:
    the check follows the interpreter's own mode, so that cache is an unexpected file."""
    root = _runtime_copy(tmp_path, 'never')
    cache = _cache(root)
    _compile(_inverted_source(tmp_path, absolute=False), cache,
             py_compile.PycInvalidationMode.CHECKED_HASH)
    out = _probe(tmp_path, bundle, root, '--check-hash-based-pycs', 'never')
    assert out['refused'] == 'environment_unqualified', out
    assert out['details']['unexpected'] == [f'__pycache__/{cache.name}']
    assert _probe(tmp_path, bundle, root).get('parity') == 'ok'


def test_an_unvalidated_cache_under_a_pycache_prefix_is_counted(tmp_path, bundle,
                                                                monkeypatch):
    """With ``sys.pycache_prefix`` the import system reads the cache outside the package
    folder; the check reads the same file (``importlib.util.cache_from_source``) and names it
    by its source."""
    root = _runtime_copy(tmp_path, 'prefixed') / 'hypotrail_runtime'
    prefix = tmp_path / 'prefix'
    monkeypatch.setattr(sys, 'pycache_prefix', str(prefix))
    cache = Path(importlib.util.cache_from_source(str(root / 'predictor.py')))
    assert cache.is_relative_to(prefix)
    _compile(_inverted_source(tmp_path, absolute=False), cache,
             py_compile.PycInvalidationMode.UNCHECKED_HASH)
    r5._point_at(monkeypatch, root)
    e = r2._refused(load_predictor, bundle, trusted_roots=[bundle],
                    code='environment_unqualified')
    assert e.details['unexpected'] == [f'predictor.py (bytecode cache {cache})']


def test_an_invalid_cache_file_is_still_ignored(tmp_path, bundle, monkeypatch):
    """A file the import system refuses as bytecode (another magic number, a short header,
    unknown flags) is never run: the source is compiled instead, so it is not counted."""
    monkeypatch.setattr(sys, 'pycache_prefix', None)
    root = _runtime_copy(tmp_path, 'invalid') / 'hypotrail_runtime'
    cache = _cache(root.parent)
    cache.parent.mkdir()
    magic = importlib.util.MAGIC_NUMBER
    for data in (b'cache', b'\x00' * 16 + b'code', magic + (0b101).to_bytes(4, 'little') +
                 b'\x00' * 8):
        cache.write_bytes(data)
        assert runtime_wheel.unvalidated_bytecode(root / 'predictor.py') is None
        r5._point_at(monkeypatch, root)
        assert check_parity(load_predictor(bundle, trusted_roots=[bundle])).status == 'ok'


@needs_mlflow
def test_the_mlflow_wrapper_refuses_a_sourceless_shadow_through_load_predictor(tmp_path):
    """The wrapper's own pre-import check still skips bytecode (its text is part of the
    packaged bytes, PACKAGER_VERSION 4, unchanged): the shadow is caught by the runtime check
    of ``load_predictor`` it then calls, when the shadow keeps that check (documented limit
    in LIBRARIES-V1, review round 9)."""
    from mlkit.integrations import mlflow_packaging as mp
    dest = tmp_path / 'bundle'
    capture_predictor(r2._fitted(), None, r2._parity(), dest, mp.ArtifactPackager(),
                      code_fingerprint=r2.FP)
    root = _runtime_copy(tmp_path, 'sourceless')
    _compile(_inverted_source(tmp_path, absolute=True),
             root / 'hypotrail_runtime' / 'predictor' / '__init__.pyc',
             py_compile.PycInvalidationMode.UNCHECKED_HASH)
    out = r5._serve(tmp_path, dest, root)
    assert out.get('refused') == 'ContractError', out
    assert 'predictor/__init__.pyc' in out['message']
    assert 'is not the runtime this bundle binds' in out['message']


# --- R9AB-3: the package is the same from any working directory ------------------------------

def _package_files(dest: Path) -> dict[str, bytes]:
    root = dest / PKG
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in sorted(root.rglob('*')) if p.is_file()}


@needs_mlflow
def test_a_capture_from_a_uv_project_packages_the_same_bytes(tmp_path, monkeypatch):
    """The reviewer's probe: from a folder holding ``pyproject.toml``, ``uv.lock`` and
    ``.python-version`` (MLflow's uv auto-detection on), packaging failed with
    ``backend_failed`` (the copied files are outside the allowlist). It now packages, from a
    uv project and from the directory the tests were started in (``framework/`` is one), the
    same bytes as from a neutral folder, and copies no uv file."""
    from mlkit.integrations import mlflow_packaging as mp
    monkeypatch.delenv('MLFLOW_UV_AUTO_DETECT', raising=False)
    monkeypatch.delenv('MLFLOW_LOG_UV_FILES', raising=False)
    fitted, parity = r2._fitted(), r2._parity()
    started_in = Path.cwd()
    uv_project = tmp_path / 'uv-project'
    uv_project.mkdir()
    (uv_project / 'pyproject.toml').write_text('[project]\nname = "team"\nversion = "0.1.0"\n')
    (uv_project / 'uv.lock').write_text('version = 1\n')
    (uv_project / '.python-version').write_text('3.13\n')
    neutral = tmp_path / 'neutral'
    neutral.mkdir()
    captured = {}
    for name, folder in (('neutral', neutral), ('uv_project', uv_project),
                         ('started_in', started_in)):
        monkeypatch.chdir(folder)
        dest = tmp_path / 'captures' / name
        capture_predictor(fitted, None, parity, dest, mp.ArtifactPackager(),
                          code_fingerprint=r2.FP)
        captured[name] = _package_files(dest)
    assert captured['neutral'], 'no package written'
    assert not {'pyproject.toml', 'uv.lock', '.python-version'} & set(captured['neutral'])
    assert captured['uv_project'] == captured['neutral']
    assert captured['started_in'] == captured['neutral']
    assert sorted(p.name for p in uv_project.iterdir()) == \
        ['.python-version', 'pyproject.toml', 'uv.lock']


# --- R9AB-4: a calibration is disjoint from every other partition ----------------------------

CALIBRATION = {'id': 'cal', 'role': 'calibration', 'keys': ['L1', 'L2', 'L3'],
               'reserved_revision': 1, 'frozen_revision': 2}


def test_calibration_overlap_is_checked_on_every_partition_name():
    """The reviewer's probe: the engine's own role names were ignored, so a calibration made
    of validation rows was eligible."""
    result = mu.eligibility(CALIBRATION, other_partitions={'validation': ['L1', 'L2', 'L3'],
                                                           'fold_1': ['L1']})
    assert result['eligible'] is False
    assert result['reasons'] == ['overlaps_fold_1', 'overlaps_validation']
    result = mu.eligibility(CALIBRATION, other_partitions={'development': ['L2'],
                                                           'final_test': ['L3'],
                                                           'train': ['L9']})
    assert result['reasons'] == ['overlaps_final_test', 'overlaps_development']
    assert mu.eligibility(CALIBRATION, other_partitions={'selection': ['L1']})['reasons'] == \
        ['overlaps_selection']


def test_a_calibration_disjoint_from_every_partition_stays_eligible():
    result = mu.eligibility(CALIBRATION, other_partitions={
        'train': ['L4'], 'validation': ['L5'], 'fold_2': ['L6'], 'development': ['L4', 'L5'],
        'final_test': ['L7'], 'empty': []})
    assert result['eligible'] is True and result['reasons'] == []
