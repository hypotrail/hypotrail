"""CI shards: one CI job runs one part of the study suite (``HYPOTRAIL_SHARD=k/n``).

A whole test file goes to one shard, so its module fixtures are built once. The files are
spread by their measured duration (``ci-durations.json``, seconds per file on one machine;
only the proportions matter): the longest first, each to the shard with the least work so
far (longest processing time first). A file the table does not know counts as the median
file. The spread depends only on the file list and the table, so every job of a run
computes the same partition and every file runs in exactly one shard.

Within a shard, pytest-xdist runs a whole file on one worker (``--dist loadfile``, the
scheduler of ``scheduler()``), except the files of ``SPLIT``: their tests are independent
(each builds its study in its own ``tmp_path`` and uses no module fixture but a cheap one),
and one of them alone runs for most of an hour, so each of their tests is scheduled on its
own. A module fixture of a split file is built once per worker that runs its tests.

Refresh the table after adding a long test file (CONTRIBUTING.md, "Tests on every platform").
"""
from __future__ import annotations

import json
import os
from pathlib import Path

DURATIONS = Path(__file__).with_name('ci-durations.json')
ENV = 'HYPOTRAIL_SHARD'

# Files scheduled test by test within a shard (measured at over five minutes each, 2026-11-06).
SPLIT = frozenset({
    'tests/study/test_perturbations.py',
    'tests/study/test_review_round5_engine.py',
    'tests/study/test_review_round6_engine.py',
    'tests/study/test_review_round9_e.py',
    'tests/study/understanding/test_review_round3_c.py',
    'tests/study/understanding/test_review_round5_cd.py',
})


def parse(value: str | None) -> tuple[int, int] | None:
    """``(k, n)`` of ``"k/n"`` (1 <= k <= n), None when unset or empty; ValueError otherwise."""
    if not value:
        return None
    k, sep, n = value.partition('/')
    if not sep or not k.isdigit() or not n.isdigit() or not 1 <= int(k) <= int(n):
        raise ValueError(f'{ENV} is "k/n" with 1 <= k <= n, not {value!r}')
    return int(k), int(n)


def load_durations(path: Path = DURATIONS) -> dict[str, float]:
    if not path.is_file():
        return {}
    return {str(k): float(v) for k, v in json.loads(path.read_text(encoding='utf-8')).items()}


def partition(files, n: int, durations: dict[str, float]) -> list[list[str]]:
    """The files of each of the ``n`` shards (longest processing time first; ties broken by
    file name, so the result is the same on every machine)."""
    files = sorted(set(files))
    known = sorted(durations[f] for f in files if f in durations)
    default = known[len(known) // 2] if known else 1.0
    cost = {f: durations.get(f, default) for f in files}
    shards: list[list[str]] = [[] for _ in range(n)]
    load = [0.0] * n
    for f in sorted(files, key=lambda f: (-cost[f], f)):
        i = min(range(n), key=lambda j: (load[j], j))
        shards[i].append(f)
        load[i] += cost[f]
    return shards


def file_of(nodeid: str) -> str:
    return nodeid.split('::', 1)[0]


def selected(nodeids, value: str | None = None) -> set[str] | None:
    """The node ids the shard named by ``value`` (default: the environment) keeps, or None
    when no shard is named."""
    spec = parse(os.environ.get(ENV) if value is None else value)
    if spec is None:
        return None
    k, n = spec
    nodeids = list(nodeids)
    mine = set(partition({file_of(i) for i in nodeids}, n, load_durations())[k - 1])
    return {i for i in nodeids if file_of(i) in mine}


def scope(nodeid: str) -> str:
    """The unit xdist schedules on one worker: the file, or the test for a file of SPLIT."""
    path = file_of(nodeid.replace('\\', '/'))
    return nodeid if path in SPLIT else file_of(nodeid)


def scheduler(config, log):
    """The ``--dist loadfile`` scheduler with the files of SPLIT scheduled test by test."""
    from xdist.scheduler import LoadFileScheduling

    class Scheduling(LoadFileScheduling):
        def _split_scope(self, nodeid: str) -> str:
            return scope(nodeid)
    return Scheduling(config, log)
