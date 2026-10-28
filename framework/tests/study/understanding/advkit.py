"""Helpers of the adversarial review tests of 24 October 2026 (built on ukit)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'understanding'))

import ukit  # noqa: E402,F401
from ukit import U, ASSIST, HANDOVER, SIM  # noqa: E402,F401


def code(p):
    return p['error']['code']


def transfer(u, sid, peer='carol', reviewer='alice', status='demonstrated', dims=('D2',),
             expect_review=0):
    task = next(t['task_id'] for t in u.bank()['tasks'] if t['kind'] == 'transfer')
    t = u.m('transfer', 'start', '--session', sid, '--peer', peer, '--task', task)
    tid = t['result']['transfer_id']
    u.m('transfer', 'submit', '--transfer', tid, '--response-file',
        u.file(f'peer-{u.n}.txt', 'The imputer in src/transforms.py learns a mean.'),
        '--assistance-file', u.file(f'peer-assist-{u.n}.json', ASSIST), '--evidence-file',
        u.file(f'peer-evidence-{u.n}.json', {'evidence_refs': ['src/transforms.py'],
                                             'difficulty_or_blockers': []}))
    rv = u.m('transfer', 'review', '--transfer', tid, '--file', u.file(
        f'peer-review-{u.n}.json', {'reviewer_declared_id': reviewer, 'declaration': SIM,
                                    'simulated': True, 'dimension_ids': list(dims),
                                    'status': status, 'rationale': 'Simulated.'}),
        expect=expect_review)
    return tid, rv


def custom_flow(u, policy_doc, *, attempts_for=None, peer=True, close=True, select=True,
                transfer_map=None):
    """Like ukit.full_flow, but ``attempts_for(u, sid, dim, task_id) -> [attempt ids]``
    may replace the single unaided attempt of a dimension."""
    u.set_policy(policy_doc)
    plan, out = u.start()
    sid = out['result']['session_id']
    dims = out['result']['dimensions']
    tasks = {t: u.bank_task(t) for t in plan['plan']['task_ids']}
    decisions = []
    for dim in dims:
        tid = next(t for t, spec in tasks.items() if spec['dimension_ids'][0] == dim)
        if attempts_for is not None:
            ids = attempts_for(u, sid, dim, tid)
        else:
            ids = None
        if ids is None:
            ids = [u.submit(sid, tid, f'My own answer for {dim}.')['result']['attempt_id']]
        decisions.append(u.decision(dim, ids, evidence_refs=['src/pipeline.py']))
    u.review(sid, decisions)
    u.m('handover', 'set', '--session', sid, '--file', u.file('handover.json', HANDOVER))
    tmap = {}
    if peer:
        _, rv = transfer(u, sid)
        tmap = {'D2': rv['result']['decision_id']}
    if transfer_map is not None:
        tmap = transfer_map(u, sid, tmap)
    if close:
        u.m('close', '--session', sid, '--to', 'completed', '--reason', 'review done')
    if select:
        ext = u.ext()
        dm = {d['dimension_id']: d['decision_id'] for d in ext['decisions'].values()
              if d['kind'] == 'attempt' and d['session_id'] == sid}
        u.m('select', '--file', u.file('selection.json', {
            'milestone': 'handoff', 'actor_scope': {'actor_declared_id': 'alice',
                                                    'profile': 'pipeline'},
            'dimension_decision_map': dm, 'transfer_decision_map': tmap,
            'reservation_resolution_refs': []}))
    return sid


def gate(u, *extra):
    return u.call('check', '--milestone', 'handoff', *extra)['gate']
