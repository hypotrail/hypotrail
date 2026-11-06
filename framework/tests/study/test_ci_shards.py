"""The CI shards (ci_shards.py): every test file runs in exactly one shard, the spread is the
same on every machine, and no shard carries more than its share plus one file."""
from __future__ import annotations

from pathlib import Path

import pytest

import ci_shards as cs

HERE = Path(__file__).resolve().parent
FRAMEWORK = HERE.parents[1]


def _files():
    return sorted(p.relative_to(FRAMEWORK).as_posix()
                  for root in ('tests/study', 'tests/workshop')
                  for p in (FRAMEWORK / root).rglob('test_*.py'))


@pytest.mark.parametrize('n', [1, 3, 8])
def test_every_file_in_exactly_one_shard(n):
    files = _files()
    shards = cs.partition(files, n, cs.load_durations())
    flat = [f for s in shards for f in s]
    assert sorted(flat) == files and len(flat) == len(set(flat))
    assert cs.partition(list(reversed(files)), n, cs.load_durations()) == shards


def test_the_spread_is_balanced():
    durations = {f'f{i}.py': float(d) for i, d in enumerate([50, 40, 30, 20, 10, 10, 5, 5])}
    shards = cs.partition(durations, 3, durations)
    loads = [sum(durations[f] for f in s) for s in shards]
    assert max(loads) <= sum(durations.values()) / 3 + max(durations.values())
    assert sorted(loads) == [55.0, 55.0, 60.0]


def test_an_unknown_file_counts_as_the_median():
    durations = {'a.py': 1.0, 'b.py': 3.0, 'c.py': 100.0}
    shards = cs.partition(['a.py', 'b.py', 'c.py', 'new.py'], 2, durations)
    assert shards == [['c.py'], ['b.py', 'new.py', 'a.py']]


def test_the_environment_names_the_shard(monkeypatch):
    ids = ['tests/study/test_a.py::t1', 'tests/study/test_a.py::t2', 'tests/study/test_b.py::t']
    assert cs.selected(ids, '') is None
    one, two = cs.selected(ids, '1/2'), cs.selected(ids, '2/2')
    assert one | two == set(ids) and not one & two
    assert {cs.file_of(i) for i in one} != {cs.file_of(i) for i in two}
    for bad in ('0/2', '3/2', '1', 'a/b'):
        with pytest.raises(ValueError):
            cs.parse(bad)


def test_the_split_files_are_scheduled_test_by_test():
    assert cs.SPLIT <= set(_files())
    split, whole = sorted(cs.SPLIT)[0], 'tests/study/test_ci_shards.py'
    assert cs.scope(f'{split}::test_x[a]') == f'{split}::test_x[a]'
    assert cs.scope(split.replace('/', '\\') + '::t') == split.replace('/', '\\') + '::t'
    assert cs.scope(f'{whole}::test_x[a]') == cs.scope(f'{whole}::test_y') == whole
