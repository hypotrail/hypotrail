"""A30: canonical JSON v1 vectors (bytes and SHA-256), producer and verifier alike."""
from __future__ import annotations

import hashlib

import pytest

from mlkit.study.understanding import canonical as cj

VECTORS = [
    # integers at the limits, zeros, booleans, null
    ({'max': 2 ** 53 - 1, 'min': -(2 ** 53 - 1), 'z': 0, 't': True, 'n': None},
     b'{"max":9007199254740991,"min":-9007199254740991,"n":null,"t":true,"z":0}'),
    # decimals: no exponent, no trailing zero, zero written "0", distinct from integers
    ({'a': cj.decimal(1.0), 'b': cj.decimal(0.125), 'c': cj.decimal(-0.0), 'd': cj.decimal(1e-7),
      'e': cj.decimal(2.5e20), 'i': 1},
     b'{"a":{"decimal":"1"},"b":{"decimal":"0.125"},"c":{"decimal":"0"},'
     b'"d":{"decimal":"0.0000001"},"e":{"decimal":"250000000000000000000"},"i":1}'),
    # Unicode: keys sorted by code point, no normalisation, no slash escaping, UTF-8 direct
    ({'é': 'café/naïve', 'é': 'decomposed', 'Z': 'upper', '☃': 'snow'},
     '{"Z":"upper","é":"decomposed","é":"café/naïve","☃":"snow"}'.encode()),
    # control characters: short escapes for b t n f r, lowercase \\u00XX for the others
    ({'s': '\b\t\n\f\r\x00\x1f"\\\x7f'},
     b'{"s":"\\b\\t\\n\\f\\r\\u0000\\u001f\\"\\\\\x7f"}'),
    # lists keep their order; nested objects are sorted
    ([3, 1, {'b': 1, 'a': [2, 1]}], b'[3,1,{"a":[2,1],"b":1}]'),
]


@pytest.mark.parametrize('value, expected', VECTORS)
def test_canonical_bytes_and_digest(value, expected):
    assert cj.dumps(value) == expected
    assert cj.digest(value) == hashlib.sha256(expected).hexdigest()
    # The verifier reads the same bytes back to the same value and bytes.
    assert cj.dumps(cj.loads(expected)) == expected
    assert cj.is_canonical(expected)


def test_frozen_digests():
    """Reference SHA-256 of two vectors (a change is a new canonical version)."""
    assert cj.digest(VECTORS[0][0]) == \
        hashlib.sha256(b'{"max":9007199254740991,"min":-9007199254740991,"n":null,"t":true,'
                       b'"z":0}').hexdigest()
    assert cj.digest({'decimal': '0.125'}) == hashlib.sha256(b'{"decimal":"0.125"}').hexdigest()


@pytest.mark.parametrize('bad', [
    {'x': 1.5},                              # raw float
    {'x': 2 ** 53},                          # out of range
    {'x': -(2 ** 53)},
    {'x': '\ud800'},                         # lone surrogate
    {'x': {'decimal': '1.0'}},               # trailing zero
    {'x': {'decimal': '1e3'}},               # exponent
    {'x': {'decimal': '+1'}},
    {'x': {'decimal': '01'}},
    {'x': {'decimal': '-0'}},
    {1: 'non-string key'},
])
def test_refused_values(bad):
    with pytest.raises(cj.CanonicalError):
        cj.dumps(bad)


@pytest.mark.parametrize('text', [
    b'{"a":1,"a":2}',                        # duplicate key
    b'{"a":1.5}',                            # raw float
    b'{"a":NaN}', b'{"a":Infinity}',
    b'{"a":9007199254740992}',
    b'{"a":-0}',
    b'{"a":{"decimal":"1.50"}}',
    b'[' * 40 + b']' * 40,                    # deeper than the limit
])
def test_parser_refusals(text):
    with pytest.raises(cj.CanonicalError):
        cj.loads(text)


def test_non_canonical_input_is_detected():
    assert not cj.is_canonical(b'{"b":1, "a":2}')
    assert not cj.is_canonical('{"s":"\\u00e9"}'.encode())     # escaped instead of direct


def test_sets_are_sorted_by_identifier_and_duplicates_refused():
    assert cj.sorted_set([{'id': 'b'}, {'id': 'a'}], 'id') == [{'id': 'a'}, {'id': 'b'}]
    with pytest.raises(cj.CanonicalError):
        cj.sorted_set([{'id': 'a'}, {'id': 'a'}], 'id')


def test_float_rule_is_deterministic_and_typed():
    assert cj.decimal(0.1 + 0.2) == {'decimal': '0.30000000000000004'}
    assert cj.decimal(100) == {'decimal': '100'}
    assert cj.dumps({'i': 1}) != cj.dumps({'i': cj.decimal(1)})       # int and decimal differ
    with pytest.raises(cj.CanonicalError):
        cj.decimal(float('nan'))
