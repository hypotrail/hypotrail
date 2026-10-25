"""A reproducible wheel of this runtime, built from its own files (bundle ``runtime/``).

The bundle carries the exact runtime that loads it. The wheel is assembled from the
installed package files (``*.py`` and the generated schemas), with fixed timestamps and a
sorted member list, so the same runtime source always gives the same bytes and the same
``wheel_sha256``. It declares the same dependencies as ``framework/runtime/pyproject.toml``
(a test compares them).

Round 5 (review A, R5-A1). The version number does not identify the code: two runtimes of
version 1.0.0 may predict differently. What a bundle binds is its wheel (``runtime.
wheel_sha256`` in the predictor manifest), so the installed runtime is compared with the
wheel's members, file by file (:func:`installed_runtime_issues`): every file of the installed
package folder but Python bytecode, against every ``hypotrail_runtime/`` member of the
wheel, by SHA-256. :func:`code_digest` summarises one side as one digest (for messages and
records). The comparison reads the installed files from the folder the import system
resolves for ``hypotrail_runtime``, without importing anything from it.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import io
import zipfile
from pathlib import Path

from . import DEPENDENCIES, DISTRIBUTION, REQUIRES_PYTHON, __version__

_EPOCH = (1980, 1, 1, 0, 0, 0)
PACKAGE = 'hypotrail_runtime'
BYTECODE_DIR = '__pycache__'
BYTECODE_SUFFIXES = ('.pyc', '.pyo')


def wheel_name() -> str:
    return f'{PACKAGE}-{__version__}-py3-none-any.whl'


def _members() -> list[tuple[str, bytes]]:
    root = Path(__file__).resolve().parent
    out = []
    for path in sorted(root.rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts:
            continue
        if path.suffix not in ('.py', '.json', '.typed'):
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
    """``{hypotrail_runtime/<relative path>: sha256}`` of every file of the installed package
    folder except Python bytecode (``__pycache__``, ``*.pyc``, ``*.pyo``): a stray file is
    kept, since an extension module or a data file beside the sources changes what runs."""
    root = installed_location() if root is None else Path(root)
    if root is None:
        return {}
    out = {}
    for path in sorted(root.rglob('*')):
        rel = path.relative_to(root)
        if BYTECODE_DIR in rel.parts or path.suffix.lower() in BYTECODE_SUFFIXES:
            continue
        if path.is_file():
            out[f'{PACKAGE}/{rel.as_posix()}'] = _sha256(path.read_bytes())
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
