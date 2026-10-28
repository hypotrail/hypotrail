"""Area C probe: arbitration validated against the current policy, not the session's."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import advkit as rkit  # noqa: E402,F401
from advkit import U, ukit  # noqa: E402

REQ = ukit.policy(mode='required')
RELAXED = ukit.policy(mode='required', critical_dimensions=['D2'],
                      role_policy={'arbiters': 'any_declared'})


def test_author_arbitrates_own_critical_conflict_after_a_policy_toggle(tmp_path):
    u = U(tmp_path)
    u.set_policy(REQ)
    plan, out = u.start()
    sid = out['result']['session_id']
    dims = out['result']['dimensions']
    tasks = plan['plan']['task_ids']
    att = {}
    for dim in dims:
        t = next(x for x in tasks if u.bank_task(x)['dimension_ids'][0] == dim)
        att[dim] = u.submit(sid, t)['result']['attempt_id']
    u.review(sid, [u.decision(d, [att[d]]) for d in dims], reviewer='bob')
    neg = u.review(sid, [u.decision('D3', [att['D3']], status='to_consolidate')],
                   reviewer='dave')
    ext = u.ext()
    pos_id = next(d['decision_id'] for d in ext['decisions'].values()
                  if d['dimension_id'] == 'D3' and d['status'] == 'demonstrated')
    neg_id = neg['result']['decisions'][0]['decision_id']
    res = [r for r in ext['reservations']]
    arb_doc = {'arbiter_declared_id': 'alice', 'declaration': ukit.SIM, 'simulated': True,
               'conflicting_decision_ids': [pos_id, neg_id], 'reservation_ids': res,
               'chosen_decision_id': pos_id, 'rationale': 'I am right.', 'evidence_refs': []}
    refused = u.m('arbitrate', '--session', sid, '--file', u.file('a1.json', arb_doc),
                  expect=2)
    assert refused['error']['code'] == 'review_required'          # control
    u.set_policy(RELAXED)                                          # D3 no longer critical
    # The session's policy still makes D3 critical: the toggle does not let the author in.
    again = u.m('arbitrate', '--session', sid, '--file', u.file('a2.json', arb_doc), expect=2)
    assert again['error']['code'] == 'review_required'
