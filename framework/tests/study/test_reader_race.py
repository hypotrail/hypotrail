"""A reader never sees a half-finished commit as an integrity error (review finding M3).

A writer process commits proposals in a loop while this process reads the state as
``status`` does (no lock), for a bounded time: the reviewer's ``race_w.py`` and
``race_r.py``. Before the fix, a read that fell between the commit point and the removal
of ``commit.pending.json`` raised ``integrity_error`` or ``FileNotFoundError``.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
import time

from mlkit.study import read
from mlkit.study.errors import StudyError
from mlkit.study.store import StudyStore

import flowkit as fk

WRITER = textwrap.dedent('''
    import sys, time, uuid
    from mlkit.study import commands as cmd
    from mlkit.study.store import StudyStore
    store, deadline = StudyStore(sys.argv[1]), time.monotonic() + float(sys.argv[2])
    n = 0
    while time.monotonic() < deadline:
        s = store.load_state()
        rid = uuid.uuid4().hex
        req = {'request_id': rid, 'expected_revision': s['revision'], 'action': 'decide.propose',
               'params': {'decision_id': 'prediction_time', 'value': 'At signup',
                          'restatement': 'At signup.', 'rationale': 'x'}}
        store.execute(req, cmd.handlers(cmd.Context(store, rid)))
        n += 1
    print(n)
''')
SECONDS = 4.0


def test_reads_during_commits_are_consistent(tmp_path, synthetic_case_dir):
    study = tmp_path / 'study'
    fk.Flow(study, synthetic_case_dir).init()
    writer = subprocess.Popen([sys.executable, '-c', WRITER, str(study), str(SECONDS)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                              env=fk.env())
    store, errors, reads = StudyStore(study), [], 0
    revisions = []
    deadline = time.monotonic() + SECONDS + 30
    while writer.poll() is None and time.monotonic() < deadline:
        for load in (store.load_state, lambda: read.load_state(study)):
            try:
                revisions.append(load()['revision'])
                reads += 1
            except (StudyError, OSError) as exc:
                errors.append(getattr(exc, 'code', type(exc).__name__))
    out, err = writer.communicate(timeout=60)
    assert writer.returncode == 0, err
    commits = int(out.strip())
    assert commits > 20 and reads > 100, (commits, reads)
    assert errors == [], {e: errors.count(e) for e in set(errors)}
    assert revisions == sorted(revisions)             # reads never go back in time
