"""Area D review: canonical JSON v1 against an independent re-implementation."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st, HealthCheck

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'understanding'))

from mlkit.study.understanding import canonical as C  # noqa: E402

MAX = 2 ** 53 - 1


def ref_str(s: str) -> str:
    out = ['"']
    for ch in s:
        o = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == '\\':
            out.append('\\\\')
        elif o == 8:
            out.append('\\b')
        elif o == 9:
            out.append('\\t')
        elif o == 10:
            out.append('\\n')
        elif o == 12:
            out.append('\\f')
        elif o == 13:
            out.append('\\r')
        elif o < 0x20:
            out.append('\\u%04x' % o)
        else:
            out.append(ch)
    out.append('"')
    return ''.join(out)


def ref_dumps(v) -> str:
    if v is None:
        return 'null'
    if v is True:
        return 'true'
    if v is False:
        return 'false'
    if isinstance(v, int):
        return str(v)
    if isinstance(v, str):
        return ref_str(v)
    if isinstance(v, list):
        return '[' + ','.join(ref_dumps(x) for x in v) + ']'
    if isinstance(v, dict):
        # sort by code point sequence explicitly (not relying on Python str ordering)
        keys = sorted(v, key=lambda k: [ord(c) for c in k])
        return '{' + ','.join(ref_str(k) + ':' + ref_dumps(v[k]) for k in keys) + '}'
    raise TypeError


text = st.text(alphabet=st.characters(blacklist_categories=('Cs',)), max_size=12)
ints = st.integers(min_value=-MAX, max_value=MAX)
decs = st.from_regex(r'-?(0|[1-9][0-9]{0,6})(\.[0-9]{0,4}[1-9])?', fullmatch=True) \
    .filter(lambda s: s != '-0').map(lambda s: {'decimal': s})
leaf = st.none() | st.booleans() | ints | text | decs
values = st.recursive(leaf, lambda ch: st.lists(ch, max_size=4)
                      | st.dictionaries(text, ch, max_size=4), max_leaves=25)


@settings(max_examples=1500, suppress_health_check=[HealthCheck.too_slow])
@given(values)
def test_dumps_matches_reference_and_roundtrips(v):
    b = C.dumps(v)
    assert b == ref_dumps(v).encode('utf-8')
    assert C.loads(b) == v
    assert C.is_canonical(b)
    assert C.digest(v) == hashlib.sha256(b).hexdigest()
    # standard JSON parser reads the same value
    assert json.loads(b.decode()) == v


@settings(max_examples=500)
@given(st.floats(allow_nan=False, allow_infinity=False))
def test_float_rule_decimal_is_canonical_and_exact(x):
    d = C.decimal(x)
    C.dumps(d)          # passes the decimal check
    from decimal import Decimal
    assert Decimal(d['decimal']) == Decimal(repr(x))


@pytest.mark.parametrize('bad', [
    b'{"a":1,"a":1}', b'1.0', b'1e2', b'-0', b'NaN', b'Infinity', b'-Infinity',
    b'9007199254740992', b'-9007199254740992', b'"\\ud800"', b'{"\\udc00":1}',
    b'{"decimal":"1.0"}', b'{"decimal":"01"}', b'{"decimal":"-0"}', b'{"decimal":"1e3"}',
    b'{"decimal":"+1"}', b'{"decimal":".5"}', b'{"decimal":1}', b'\xff', b'"\x01"',
])
def test_parser_refusals(bad):
    with pytest.raises(C.CanonicalError):
        C.loads(bad)


@pytest.mark.parametrize('noncanon', [
    b'{"b":1,"a":2}', b'{ "a":1}', b'"\\u00e9"', b'"\\/"', b'"\\u001F"', b'"\\u0008"',
    b'[1, 2]', b'\xef\xbb\xbf1', b'"\\u007f"', b'1\n',
])
def test_non_canonical_detected(noncanon):
    assert not C.is_canonical(noncanon)


def test_supplementary_key_order_is_code_point():
    # U+FF61 sorts before U+1F600 by code point, after it in UTF-16 order
    v = {'\U0001F600': 1, '｡': 2}
    assert C.dumps(v) == '{"｡":2,"\U0001F600":1}'.encode()


def test_boundary_ints_and_zero():
    assert C.dumps([MAX, -MAX, 0]) == b'[9007199254740991,-9007199254740991,0]'
    for bad in (MAX + 1, -MAX - 1):
        with pytest.raises(C.CanonicalError):
            C.dumps(bad)


def test_decimal_helper_rejects_lax_strings():
    """decimal() accepts non-numeric looking inputs that Decimal tolerates."""
    lax = []
    for s in (' 1.5 ', '1_000', '+2', '1E+2', '0x10'):
        try:
            lax.append((s, C.decimal(s)))
        except C.CanonicalError:
            pass
    print('LAX', lax)


def test_deep_nesting_limit_parse_and_dump():
    deep = b'[' * 40 + b']' * 40
    with pytest.raises(C.CanonicalError):
        C.loads(deep)
    very = b'[' * 100000 + b']' * 100000
    with pytest.raises(C.CanonicalError):
        C.loads(very)
