"""Canonical JSON serialisation ``hypotrail.canonical/1`` (CONTRAT-COMMUN-v1 §1, spec L-01).

Typed normalisation comes first (the Pydantic model dumps its fields in JSON mode, so a
``float`` field is a float and an ``int`` field an int); then:

* mappings sorted by Unicode code point of their keys, lists kept in order;
* UTF-8, compact separators ``(',', ':')``, ``ensure_ascii=False``, ``allow_nan=False``;
* ``-0.0`` becomes ``0.0``; NaN and infinities are refused (``contract_invalid``);
* only JSON types: str, int, float, bool, None, list, mapping with string keys;
* a string (value or key) holding a lone surrogate is refused (``contract_invalid``).

Three digests are distinguished: :func:`scientific_id` (a scientific document),
:func:`artifact_id` (a content manifest without its own id and its mutable binding) and
:func:`file_sha256` (the bytes of a file). Any change to these rules is a new serialiser
version (:data:`VERSION`), never an edit of this one.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

from .errors import ContractError

VERSION = 'hypotrail.canonical/1'


def normalize(value: Any, path: str = '') -> Any:
    """The JSON value with ``-0.0`` as ``0.0``; refuses non-finite numbers and non-JSON
    types (a tuple is read as a list)."""
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractError('contract_invalid', 'A non-finite number cannot be serialised; '
                                'an undefined value is null with its reason.', path=path,
                                remediation='Replace it with null and record the cause.')
        return 0.0 if value == 0 else float(value)
    if isinstance(value, Mapping):
        out = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ContractError('contract_invalid', 'Mapping keys are strings.',
                                    path=f'{path}/{key!r}', remediation='Use string keys.')
            out[key] = normalize(item, f'{path}/{key}')
        return out
    if isinstance(value, (list, tuple)):
        return [normalize(item, f'{path}/{i}') for i, item in enumerate(value)]
    raise ContractError('contract_invalid', f'{type(value).__name__} is not a JSON type.',
                        path=path, remediation='Serialise library objects explicitly; '
                                               'contracts hold JSON values only.')


def dumps(value: Any) -> bytes:
    """Canonical bytes of a JSON value (after :func:`normalize`)."""
    if hasattr(value, 'model_dump'):
        value = value.model_dump(mode='json')
    text = json.dumps(normalize(value), sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False)
    try:
        return text.encode('utf-8')
    except UnicodeEncodeError as exc:       # a lone surrogate is not a Unicode scalar value
        raise ContractError('contract_invalid', 'A string holds a lone surrogate, which UTF-8 '
                            'cannot encode.', path='',
                            remediation='Send valid Unicode text (decode the source with its '
                                        'declared encoding).',
                            details={'position': exc.start}) from None


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def scientific_id(document: Any) -> str:
    """SHA-256 of the canonical scientific document."""
    return sha256_hex(dumps(document))


def artifact_id(manifest: Any, *, exclude: Iterable[str] = ()) -> str:
    """SHA-256 of a content manifest without the named top-level keys (its own id and any
    mutable binding field): the manifest never signs its own digest."""
    if hasattr(manifest, 'model_dump'):
        manifest = manifest.model_dump(mode='json')
    content = {k: v for k, v in dict(manifest).items() if k not in set(exclude)}
    return sha256_hex(dumps(content))


def file_sha256(path: Path | str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for block in iter(lambda: fh.read(chunk), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, document: Any) -> str:
    """Write the canonical bytes (plus a newline) and return the file's SHA-256."""
    data = dumps(document) + b'\n'
    Path(path).write_bytes(data)
    return sha256_hex(data)
