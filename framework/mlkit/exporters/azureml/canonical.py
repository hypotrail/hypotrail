"""Canonical JSON and SHA-256 identities (contract v1 §1), standalone.

The normalisation precedes the serialisation: an object's keys must be strings, a list
keeps its order, ``True`` stays a boolean and never an integer, a float stays a float
(``-0.0`` becomes ``0.0``), NaN and infinities are refused. The bytes are UTF-8 JSON with
sorted keys, compact separators, ``ensure_ascii=False`` and ``allow_nan=False``.

This module has no dependency besides the standard library because the Azure ML export
copies it byte for byte into the generated project
(``src/pipeline/utils/hypotrail/canonical.py``), so the generator and the exported
project compute the same identities. The scientific documents of chantier A carry their
own ``scientific_id``; this serialiser identifies the export's own documents.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping

SERIALIZER_VERSION = 'hypotrail.canonical_json/1'


class CanonicalError(ValueError):
    """A value that has no canonical JSON form; ``path`` names where it is."""

    def __init__(self, message: str, path: str):
        super().__init__(f'{path}: {message}')
        self.path = path


def normalise(value: Any, path: str = '$') -> Any:
    """The typed JSON value of ``value`` (dicts, lists, str, int, float, bool, None)."""
    if isinstance(value, Mapping):
        out = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalError('an object key is not a string', path)
            out[key] = normalise(item, f'{path}.{key}')
        return out
    if isinstance(value, (list, tuple)):
        return [normalise(item, f'{path}[{i}]') for i, item in enumerate(value)]
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalError('a number is not finite', path)
        return 0.0 if value == 0 else float(value)
    raise CanonicalError(f'not a JSON value ({type(value).__name__})', path)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(normalise(value), sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_sha256(value: Any) -> str:
    return sha256_hex(canonical_bytes(value))


def pretty_bytes(value: Any) -> bytes:
    """The same value written for people (indented, sorted keys, final newline); the
    identity of a document is always computed on :func:`canonical_bytes`."""
    return (json.dumps(normalise(value), sort_keys=True, indent=2, ensure_ascii=False,
                       allow_nan=False) + '\n').encode('utf-8')


def loads_strict(text: str) -> Any:
    """JSON text read without NaN or Infinity constants."""
    def refuse(name):
        raise CanonicalError(f'non-finite constant {name}', '$')
    return json.loads(text, parse_constant=refuse)
