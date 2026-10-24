import json, random
import pytest
from mlkit.study.understanding import canonical as c

ALPH = ['a', 'Z', '"', '\\', '/', '\x00', '\x1f', '\x7f', '\x85', ' ', 'é', '￿',
        '\U0001F600', '\U00010000', '﻿', '​', '\b', '\t', '\n', '\f', '\r', ' ']


def rstr(r):
    return ''.join(r.choice(ALPH) for _ in range(r.randint(0, 6)))


def rval(r, d=0):
    k = r.randint(0, 6 if d < 4 else 3)
    if k == 0: return None
    if k == 1: return r.choice([True, False])
    if k == 2: return r.choice([0, -1, 2**53 - 1, -(2**53 - 1), r.randint(-10**6, 10**6)])
    if k == 3: return rstr(r)
    if k == 4: return [rval(r, d + 1) for _ in range(r.randint(0, 4))]
    return {rstr(r): rval(r, d + 1) for _ in range(r.randint(0, 4))}


def reference(v):
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


def test_against_stdlib_reference():
    r = random.Random(20261024)
    for _ in range(5000):
        v = rval(r)
        assert c.dumps(v) == reference(v), v
        assert c.loads(c.dumps(v)) == v
        assert c.is_canonical(c.dumps(v))


@pytest.mark.parametrize('raw', [b'"\\u00e9"', b'"\\/"', b'"\\u001F"', b'{"b":1,"a":2}',
                                 b'"\\ud83d\\ude00"', b' 1', b'1 ', b'"\\u007f"',
                                 b'{"a":1,"\\u0061":2}', b'-0', b'[1.0]', b'1e2',
                                 b'"\xed\xa0\x80"', b'\xef\xbb\xbf1', b'{"decimal":"01"}',
                                 b'{"decimal":"1.0"}', b'{"decimal":"-0"}'])
def test_non_canonical_or_refused(raw):
    assert not c.is_canonical(raw)
