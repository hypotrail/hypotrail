"""Area C probe: a mapped source missing from the start is a missing dependency (SPEC 12:
unknown, then blocked under context_requirement complete)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import advkit as rkit  # noqa: E402,F401
from advkit import U, ukit, gate, custom_flow  # noqa: E402

REQ = ukit.policy(mode='required')
SOURCES = ukit.SOURCES + [{'logical_key': 'repo:src/model.py', 'path': 'src/model.py',
                           'role': 'code'}]


def test_mapped_code_source_missing_since_start(tmp_path, monkeypatch):
    u = U(tmp_path)
    orig = U.start
    monkeypatch.setattr(U, 'start', lambda self, **kw: orig(self, sources=SOURCES, **kw))
    sid = custom_flow(u, REQ)
    snap_unreadable = None
    from mlkit.study.understanding import service as sv
    store = sv.open_store(u.study)
    s = u.ext()['sessions'][sid]
    snap_unreadable = sv.session_snapshot(store, s)['local']['unreadable_sources']
    print('unreadable at start:', snap_unreadable)
    g = gate(u)
    print(g['decision'], g['dimensions']['D6'])
    plan = u.call('plan', '--profile', 'pipeline', '--milestone', 'handoff', '--actor',
                  'alice', '--repo', u.repo, '--sources-file', u.file('sx.json', SOURCES))
    print('plan mentions the missing source:', 'src/model.py' in str(plan))
    assert g['dimensions']['D6']['freshness'] != 'current'
    assert g['decision'] == 'blocked'
