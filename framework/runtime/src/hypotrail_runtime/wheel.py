"""A reproducible wheel of this runtime, built from its own files (bundle ``runtime/``).

The bundle carries the exact runtime that loads it. The wheel is assembled from the
installed package files (``*.py`` and the generated schemas), with fixed timestamps and a
sorted member list, so the same runtime source always gives the same bytes and the same
``wheel_sha256``. It declares the same dependencies as ``framework/runtime/pyproject.toml``
(a test compares them).
"""
from __future__ import annotations

import base64
import hashlib
import zipfile
from pathlib import Path

from . import DEPENDENCIES, DISTRIBUTION, REQUIRES_PYTHON, __version__

_EPOCH = (1980, 1, 1, 0, 0, 0)
PACKAGE = 'hypotrail_runtime'


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
