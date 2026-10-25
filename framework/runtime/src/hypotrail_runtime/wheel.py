"""A reproducible wheel of this runtime, built from its own files (bundle ``runtime/``).

The bundle carries the exact runtime that loads it. The wheel is assembled from the
installed package files (``*.py`` and the generated schemas), with fixed timestamps and a
sorted member list, so the same runtime source always gives the same bytes and the same
``wheel_sha256``. It declares the same dependencies as ``framework/runtime/pyproject.toml``
(a test compares them).

Round 5 (review A, R5-A1). The version number does not identify the code: two runtimes of
version 1.0.0 may predict differently. What a bundle binds is its wheel (``runtime.
wheel_sha256`` in the predictor manifest), so the installed runtime is compared with the
wheel's members, file by file (:func:`installed_runtime_issues`), by SHA-256.
:func:`code_digest` summarises one side as one digest (for messages and records). The
comparison reads the installed files from the folder the import system resolves for
``hypotrail_runtime``, without importing anything from it.

Round 5 (review E, R5E-1). Both sides are selected by one rule, :func:`wheel_member`: the
files the wheel build takes (``*.py``, ``*.json``, ``*.typed``, outside ``__pycache__``), so
a Finder ``.DS_Store``, an editor swap file or a ``predictor.py.orig`` beside the sources is
ignored, as the wheel ignores it, while a stray ``*.py`` is code and counts. A compiled
extension module (:data:`importlib.machinery.EXTENSION_SUFFIXES`, ``.so``, ``.pyd``) is code
too: the import system loads it before a source of the same name, so it is counted on the
installed side although no wheel can carry it (:func:`installed_code`).

Round 9 (review AB, R9AB-2). Python bytecode the import system would run *instead of* a bound
source counts as code too (:func:`unvalidated_bytecode`):

* a ``*.pyc`` or ``*.pyo`` file outside ``__pycache__`` is sourceless code: the import system
  loads ``predictor/__init__.pyc`` (a package folder is tried before ``predictor.py``) or a
  ``name.pyc`` without any source, so it is always counted, and no wheel holds one;
* the cache file the import system reads for a bound source (:func:`importlib.util.
  cache_from_source`, in ``__pycache__`` or under ``sys.pycache_prefix``) counts when this
  interpreter would use it without comparing it with the source: a hash-based pyc that is
  not validated (``unchecked-hash``, or ``checked-hash`` under ``--check-hash-based-pycs
  never``). A timestamp-based pyc and a validated hash-based pyc are not counted: Python
  recompiles the source when they do not match it. The residual limit: a timestamp-based pyc
  is matched on the source's modification time and size only, so a cache file forged with
  the time and size of the bound source runs in its place; bytecode is never trusted beyond
  what the interpreter itself checks.
"""
from __future__ import annotations

import _imp
import base64
import hashlib
import importlib.machinery
import importlib.util
import io
import zipfile
from pathlib import Path

from . import DEPENDENCIES, DISTRIBUTION, REQUIRES_PYTHON, __version__

_EPOCH = (1980, 1, 1, 0, 0, 0)
PACKAGE = 'hypotrail_runtime'
BYTECODE_DIR = '__pycache__'
BYTECODE_SUFFIXES = ('.pyc', '.pyo')
# The files a wheel of this runtime holds (R5E-1: the one selection rule of both sides).
MEMBER_SUFFIXES = ('.py', '.json', '.typed')
# Compiled extension modules, on this platform and the usual ones elsewhere.
EXTENSION_SUFFIXES = tuple(sorted(set(importlib.machinery.EXTENSION_SUFFIXES)
                                  | {'.so', '.pyd'}))


def wheel_name() -> str:
    return f'{PACKAGE}-{__version__}-py3-none-any.whl'


def wheel_member(relative: Path | str) -> bool:
    """Whether the file ``relative`` (a path inside the package folder) is one the wheel
    build takes: a ``*.py``, ``*.json`` or ``*.typed`` file outside ``__pycache__``."""
    rel = Path(relative)
    return BYTECODE_DIR not in rel.parts and rel.suffix in MEMBER_SUFFIXES


def extension_module(relative: Path | str) -> bool:
    """Whether ``relative`` is a compiled extension module the import system would load
    (``.so``, ``.pyd``, ...): code, although no wheel of this pure runtime carries one."""
    rel = Path(relative)
    return BYTECODE_DIR not in rel.parts and any(
        rel.name.endswith(suffix) for suffix in EXTENSION_SUFFIXES)


# The header of a pyc (PEP 552): the magic number, then a 32-bit little-endian flags word whose
# bit 0 marks a hash-based pyc and bit 1 asks for the hash to be checked against the source.
PYC_HEADER_SIZE = 16
PYC_HASH_BASED = 0b01
PYC_CHECK_SOURCE = 0b10


def sourceless_bytecode(relative: Path | str) -> bool:
    """Whether ``relative`` is bytecode outside ``__pycache__``: the import system can load it
    without any source (``name.pyc``, or ``name/__init__.pyc`` before ``name.py``), so it is
    code although no wheel of this runtime carries one (round 9, R9AB-2)."""
    rel = Path(relative)
    return BYTECODE_DIR not in rel.parts and rel.suffix.lower() in BYTECODE_SUFFIXES


def _unvalidated_header(head: bytes) -> bool:
    """Whether a pyc with this header is one this interpreter runs without checking it
    against its source: the current magic number, hash-based, and not validated
    (``unchecked-hash``, or any hash-based pyc under ``--check-hash-based-pycs never``)."""
    if len(head) < PYC_HEADER_SIZE or head[:4] != importlib.util.MAGIC_NUMBER:
        return False                        # ignored by the import system (source compiled)
    flags = int.from_bytes(head[4:8], 'little')
    if flags & ~(PYC_HASH_BASED | PYC_CHECK_SOURCE) or not flags & PYC_HASH_BASED:
        return False                        # refused as invalid, or validated by timestamp
    mode = _imp.check_hash_based_pycs
    validated = mode != 'never' and (bool(flags & PYC_CHECK_SOURCE) or mode == 'always')
    return not validated


def unvalidated_bytecode(source: Path) -> Path | None:
    """The bytecode cache file the import system would run for ``source`` (a ``*.py`` file)
    without comparing it with that source, or None (round 9, R9AB-2). The cache file is the
    one :func:`importlib.util.cache_from_source` names for this interpreter (its cache tag,
    optimisation level and ``sys.pycache_prefix``)."""
    try:
        cache = Path(importlib.util.cache_from_source(str(source)))
    except (NotImplementedError, ValueError):
        return None
    try:
        with cache.open('rb') as handle:
            head = handle.read(PYC_HEADER_SIZE)
    except OSError:
        return None
    return cache if _unvalidated_header(head) else None


def _members() -> list[tuple[str, bytes]]:
    root = Path(__file__).resolve().parent
    out = []
    for path in sorted(root.rglob('*')):
        if not path.is_file() or not wheel_member(path.relative_to(root)):
            continue
        out.append((f'{PACKAGE}/{path.relative_to(root).as_posix()}', path.read_bytes()))
    return out


def _record_hash(data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()
    return f'sha256={digest}'


def build(destination: Path) -> Path:
    """Write the wheel into ``destination`` (a directory) and return its path."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    dist_info = f'{PACKAGE}-{__version__}.dist-info'
    metadata = '\n'.join(['Metadata-Version: 2.1', f'Name: {DISTRIBUTION}',
                          f'Version: {__version__}', f'Requires-Python: {REQUIRES_PYTHON}',
                          *[f'Requires-Dist: {d}' for d in DEPENDENCIES], '']).encode()
    wheel = ('Wheel-Version: 1.0\nGenerator: hypotrail_runtime.wheel\n'
             'Root-Is-Purelib: true\nTag: py3-none-any\n').encode()
    members = _members() + [(f'{dist_info}/METADATA', metadata),
                            (f'{dist_info}/WHEEL', wheel)]
    record = ''.join(f'{name},{_record_hash(data)},{len(data)}\n' for name, data in members)
    record += f'{dist_info}/RECORD,,\n'
    members.append((f'{dist_info}/RECORD', record.encode()))
    path = destination / wheel_name()
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in members:
            info = zipfile.ZipInfo(name, date_time=_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, data)
    return path


# --- the installed runtime against a bundle's wheel (round 5, R5-A1) ------------------------

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def installed_location() -> Path | None:
    """The folder the import system resolves for ``hypotrail_runtime`` (the module in use
    when it is already imported), without importing it; None when it is not a regular
    package of one folder."""
    spec = importlib.util.find_spec(PACKAGE)
    locations = list(spec.submodule_search_locations or []) if spec is not None else []
    if len(locations) != 1:
        return None
    return Path(locations[0]).resolve()


def installed_files(root: Path | None = None) -> dict[str, str]:
    """``{hypotrail_runtime/<relative path>: sha256}`` of the files of the installed package
    folder that a wheel built from it would hold (:func:`wheel_member`), plus the code that
    runs although no wheel carries it: a compiled extension module (:func:`extension_module`),
    sourceless bytecode (:func:`sourceless_bytecode`), and the cache file of a source that
    this interpreter would run without validating it (:func:`unvalidated_bytecode`; named
    ``<source> (bytecode cache <path>)`` when it lies outside the folder). Every other file
    (``.DS_Store``, ``*.swp``, ``*.orig``, a README, a bytecode cache Python validates) is
    ignored, exactly as the wheel build ignores it (round 5, R5E-1; round 9, R9AB-2)."""
    root = installed_location() if root is None else Path(root)
    if root is None:
        return {}
    out = {}
    for path in sorted(root.rglob('*')):
        rel = path.relative_to(root)
        if not path.is_file():
            continue
        if wheel_member(rel) or extension_module(rel) or sourceless_bytecode(rel):
            out[f'{PACKAGE}/{rel.as_posix()}'] = _sha256(path.read_bytes())
        if rel.suffix == '.py' and BYTECODE_DIR not in rel.parts:
            cache = unvalidated_bytecode(path)
            if cache is not None:
                inside = cache.resolve().is_relative_to(root.resolve())
                name = (cache.resolve().relative_to(root.resolve()).as_posix() if inside
                        else f'{rel.as_posix()} (bytecode cache {cache})')
                out[f'{PACKAGE}/{name}'] = _sha256(cache.read_bytes())
    return out


def wheel_files(data: bytes) -> dict[str, str]:
    """``{hypotrail_runtime/<relative path>: sha256}`` of the package members of a runtime
    wheel (its ``.dist-info`` left out)."""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return {name: _sha256(zf.read(name)) for name in sorted(zf.namelist())
                if name.startswith(PACKAGE + '/') and not name.endswith('/')}


def code_digest(files: dict[str, str]) -> str:
    """One digest of a runtime's code: SHA-256 of ``<path> <sha256>`` lines, sorted."""
    return _sha256(''.join(f'{name} {sha}\n' for name, sha in sorted(files.items())).encode())


def installed_runtime_issues(wheel_data: bytes) -> dict | None:
    """None when the installed ``hypotrail_runtime`` holds exactly the code of the wheel
    ``wheel_data`` (same files, same bytes); otherwise ``{location, missing, unexpected,
    changed, installed_digest, bound_digest}`` (paths relative to the package folder)."""
    location = installed_location()
    found = installed_files(location) if location is not None else {}
    bound = wheel_files(wheel_data)
    if found == bound:
        return None
    strip = len(PACKAGE) + 1
    return {'location': str(location) if location is not None else None,
            'missing': sorted(n[strip:] for n in set(bound) - set(found)),
            'unexpected': sorted(n[strip:] for n in set(found) - set(bound)),
            'changed': sorted(n[strip:] for n in set(found) & set(bound)
                              if found[n] != bound[n]),
            'installed_digest': code_digest(found), 'bound_digest': code_digest(bound)}
