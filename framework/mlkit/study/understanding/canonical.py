"""Canonical JSON v1 of the understanding review (SPEC-COMPREHENSION §12).

One byte form for every digest the producer writes and the verifier recomputes:

* UTF-8, object keys sorted by Unicode code point, compact separators (``,`` and ``:``);
* no implicit Unicode normalisation; strings written directly in UTF-8 except ``"`` and
  ``\\`` (short escapes), U+0008, U+0009, U+000A, U+000C, U+000D (``\\b \\t \\n \\f \\r``)
  and the other controls U+0000 to U+001F (``\\u`` with four lowercase hex digits); the
  slash is not escaped; a lone surrogate is refused;
* integers from ``-(2**53 - 1)`` to ``2**53 - 1``, base 10, no ``+``, no leading zero, no
  negative zero (an integer has none); booleans and null as JSON;
* no raw float: a scientific number is the typed object ``{"decimal": "..."}`` whose
  string has no exponent, no ``+``, no superfluous leading zero, no trailing zero after
  the point, and ``"0"`` for zero (``1.0`` is ``{"decimal": "1"}``);
* parsing refuses duplicate keys, ``NaN``, ``Infinity``, raw floats, out-of-range integers
  and malformed decimal objects.

Lists keep their order; a list declared as a set is sorted by its identifier by the
producer before it is serialised (:func:`sorted_set`).

This module imports nothing from the study engine, so the standalone verifier
(:mod:`mlkit.study.understanding.verify`) recomputes the same bytes.
"""
from __future__ import annotations

import decimal as _decimal
import hashlib
import json
import math
import re
from typing import Any, Iterable

VERSION = 'hypotrail.canonical-json/1'
# The rule that turns an engine float into a decimal object (versioned; it never changes a
# computation, only the form a number takes in a digest).
FLOAT_RULE = 'float-shortest-repr/1'
MAX_SAFE = 2 ** 53 - 1
MAX_DEPTH = 32
DECIMAL_RE = re.compile(r'-?(0|[1-9][0-9]*)(\.[0-9]*[1-9])?')
_SHORT = {'"': '\\"', '\\': '\\\\', '\b': '\\b', '\t': '\\t', '\n': '\\n', '\f': '\\f',
          '\r': '\\r'}


class CanonicalError(ValueError):
    """A value or a document outside canonical JSON v1. ``path`` locates it."""

    def __init__(self, message: str, path: str = ''):
        super().__init__(f'{message} at {path or "<root>"}')
        self.message = message
        self.path = path


def decimal(value) -> dict:
    """The decimal object of a finite number (int, float, Decimal or numeric text), under
    :data:`FLOAT_RULE`: a float is read through its shortest round-trip ``repr``."""
    if isinstance(value, bool):
        raise CanonicalError('a boolean is not a decimal')
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalError('a non-finite number has no decimal form')
        d = _decimal.Decimal(repr(value))
    elif isinstance(value, (int, _decimal.Decimal)):
        d = _decimal.Decimal(value)
    elif isinstance(value, str):
        try:
            d = _decimal.Decimal(value)
        except _decimal.InvalidOperation as exc:
            raise CanonicalError(f'not a number: {value!r}') from exc
    else:
        raise CanonicalError(f'not a number: {type(value).__name__}')
    if not d.is_finite():
        raise CanonicalError('a non-finite number has no decimal form')
    text = format(d, 'f')
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    if text in ('-0', ''):
        text = '0'
    return {'decimal': text}


def is_decimal(obj) -> bool:
    return isinstance(obj, dict) and set(obj) == {'decimal'}


def _check_decimal(obj: dict, path: str) -> None:
    text = obj['decimal']
    if not isinstance(text, str) or not DECIMAL_RE.fullmatch(text) or text == '-0':
        raise CanonicalError('malformed decimal object', path)


def _string(text: str, path: str) -> str:
    out = ['"']
    for ch in text:
        code = ord(ch)
        if 0xD800 <= code <= 0xDFFF:
            raise CanonicalError('lone surrogate in a string', path)
        if ch in _SHORT:
            out.append(_SHORT[ch])
        elif code < 0x20:
            out.append(f'\\u{code:04x}')
        else:
            out.append(ch)
    out.append('"')
    return ''.join(out)


def _write(value: Any, path: str, depth: int, out: list) -> None:
    if depth > MAX_DEPTH:
        raise CanonicalError('nesting deeper than the limit', path)
    if value is None:
        out.append('null')
    elif value is True:
        out.append('true')
    elif value is False:
        out.append('false')
    elif isinstance(value, int):
        if not -MAX_SAFE <= value <= MAX_SAFE:
            raise CanonicalError('integer outside the safe range', path)
        out.append(str(value))
    elif isinstance(value, float):
        raise CanonicalError('raw float (use a decimal object)', path)
    elif isinstance(value, str):
        out.append(_string(value, path))
    elif isinstance(value, dict):
        if is_decimal(value):
            _check_decimal(value, path)
        out.append('{')
        keys = list(value)
        for k in keys:
            if not isinstance(k, str):
                raise CanonicalError('object key is not a string', path)
        for i, k in enumerate(sorted(keys)):
            if i:
                out.append(',')
            out.append(_string(k, path))
            out.append(':')
            _write(value[k], f'{path}/{k}', depth + 1, out)
        out.append('}')
    elif isinstance(value, (list, tuple)):
        out.append('[')
        for i, item in enumerate(value):
            if i:
                out.append(',')
            _write(item, f'{path}/{i}', depth + 1, out)
        out.append(']')
    else:
        raise CanonicalError(f'unsupported type {type(value).__name__}', path)


def dumps(value: Any) -> bytes:
    """Canonical bytes of ``value``; :class:`CanonicalError` when it is not canonical."""
    out: list[str] = []
    _write(value, '', 0, out)
    return ''.join(out).encode('utf-8')


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest(value: Any) -> str:
    """SHA-256 (hex) of the canonical bytes of ``value``."""
    return sha256_hex(dumps(value))


def _pairs(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise CanonicalError(f'duplicate key {k!r}')
        out[k] = v
    return out


def _no_float(text):
    raise CanonicalError(f'raw float {text} (use a decimal object)')


def _no_constant(text):
    raise CanonicalError(f'{text} is not allowed')


def _int(text):
    value = int(text)
    if not -MAX_SAFE <= value <= MAX_SAFE:
        raise CanonicalError('integer outside the safe range')
    if text.startswith('-0'):
        raise CanonicalError('negative zero')
    return value


def loads(data: bytes | str) -> Any:
    """Parse JSON strictly (duplicates, floats, constants, range, depth refused) and check
    every decimal object. It does not require the input to be in canonical form; use
    :func:`is_canonical` for that."""
    if isinstance(data, bytes):
        try:
            data = data.decode('utf-8')
        except UnicodeDecodeError as exc:
            raise CanonicalError('not UTF-8') from exc
    try:
        value = json.loads(data, object_pairs_hook=_pairs, parse_float=_no_float,
                           parse_constant=_no_constant, parse_int=_int)
    except CanonicalError:
        raise
    except (ValueError, RecursionError) as exc:
        raise CanonicalError(f'not JSON: {exc}') from exc
    dumps(value)                     # depth, surrogates and decimal objects
    return value


def is_canonical(data: bytes) -> bool:
    try:
        return dumps(loads(data)) == data
    except CanonicalError:
        return False


def sorted_set(items: Iterable[dict], key: str) -> list:
    """A list declared as a set, sorted by its identifier ``key`` (duplicates refused)."""
    items = list(items)
    ids = [i[key] for i in items]
    if len(set(ids)) != len(ids):
        raise CanonicalError(f'duplicate {key} in a set')
    return sorted(items, key=lambda i: i[key])
