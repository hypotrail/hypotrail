"""Area C probes: idempotency and stale revisions on the mutation verbs, out-of-order
sequences. A failure is a finding."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import advkit as rkit  # noqa: E402,F401
from advkit import U, ukit, code, gate, custom_flow, transfer  # noqa: E402

REQ = ukit.policy(mode='required')


def test_start_retry_with_same_request_is_a_replay(tmp_path):
    """SPEC 13 / A12: an identical idempotent request returns its initial result. A client
    that lost the answer of `understanding start` retries with the same request id and the
    same expected revision."""
    u = U(tmp_path)
    u.set_policy(REQ)
    plan_path = u.root / 'inputs' / 'plan.json'
    u.call('plan', '--profile', 'pipeline', '--milestone', 'handoff', '--actor', 'alice',
           '--repo', u.repo, '--sources-file', u.file('sources.json', ukit.SOURCES),
           '--write-plan', plan_path)
    rev = u.rev()
    first = u.m('start', '--plan-file', plan_path, request_id='st1', revision=rev)
    again = u.m('start', '--plan-file', plan_path, request_id='st1', revision=rev,
                expect=None)
    print(again.get('error') or again['result'])
    assert again.get('replayed') is True and again['result'] == first['result']
    assert len(u.ext()['sessions']) == 1


def test_mutations_with_a_stale_revision_change_nothing(tmp_path):
    u = U(tmp_path)
    u.set_policy(REQ)
    plan, out = u.start()
    sid = out['result']['session_id']
    t = next(t for t in plan['plan']['task_ids'] if u.bank_task(t)['dimension_ids'][0] == 'D3')
    a = u.submit(sid, t)['result']['attempt_id']
    before = u.state()
    stale = u.rev() - 1
    cases = [
        ('policy', 'set', '--file', u.file('pp.json', REQ), '--author', 'lead', '--reason', 'r'),
        ('submit', '--session', sid, '--task', t, '--response-file', u.file('x.txt', 'x'),
         '--assistance-file', u.file('xa.json', ukit.ASSIST)),
        ('coach', '--attempt', a),
        ('review', '--session', sid, '--file', u.file('rv.json', {
            'reviewer_declared_id': 'bob', 'declaration': ukit.SIM, 'simulated': True,
            'decisions': [u.decision('D3', [a])]})),
        ('handover', 'set', '--session', sid, '--file', u.file('h.json', ukit.HANDOVER)),
        ('close', '--session', sid, '--to', 'abandoned', '--reason', 'x'),
    ]
    for args in cases:
        o = u.m(*args, revision=stale, expect=2)
        assert code(o) == 'stale_revision', (args[0], o)
    after = u.state()
    assert after['understanding'] == before['understanding']
    assert after['revision'] == before['revision']


def test_out_of_order_sequences(tmp_path):
    u = U(tmp_path)
    u.set_policy(REQ)
    plan, out = u.start()
    sid = out['result']['session_id']
    tasks = plan['plan']['task_ids']
    t = next(t for t in tasks if u.bank_task(t)['dimension_ids'][0] == 'D3')
    a = u.submit(sid, t)['result']['attempt_id']
    # a selection from an active session is refused
    rv = u.review(sid, [u.decision('D3', [a])])
    did = rv['result']['decisions'][0]['decision_id']
    sel = {'milestone': 'handoff', 'actor_scope': {'actor_declared_id': 'alice',
                                                    'profile': 'pipeline'},
           'dimension_decision_map': {'D3': did}, 'transfer_decision_map': {},
           'reservation_resolution_refs': []}
    o = u.m('select', '--file', u.file('sel.json', sel), expect=2)
    assert code(o) == 'invalid_transition'
    # abandon, then submit / review / coach / select are refused
    u.m('close', '--session', sid, '--to', 'abandoned', '--reason', 'stop')
    o = u.submit(sid, t, expect=2)
    assert code(o) == 'invalid_transition'
    o = u.review(sid, [u.decision('D3', [a])], expect=2)
    assert code(o) == 'invalid_transition'
    o = u.m('coach', '--attempt', a, expect=2)
    assert code(o) == 'invalid_transition'
    o = u.m('select', '--file', u.file('sel2.json', sel), expect=2)
    assert code(o) == 'invalid_transition'
    o = u.m('close', '--session', sid, '--to', 'active', '--reason', 'reopen', expect=2)
    assert code(o) == 'invalid_transition'
    # proposals, arbitration and handover on an abandoned session (probe; print only)
    u.m('handover', 'set', '--session', sid, '--file', u.file('h.json', ukit.HANDOVER),
        expect=None)
    st = u.ext()['sessions'][sid]
    print('handovers on abandoned:', [h for h in u.ext()['handovers'].values()
                                      if h['session_id'] == sid])
    assert st['status'] == 'abandoned'


def test_policy_mode_toggle_does_not_allow_self_review_on_critical(tmp_path):
    """Policy changed mid-session to coaching, the author self-reviews a critical
    dimension, the required policy is restored byte for byte: the gate must block."""
    u = U(tmp_path)
    u.set_policy(REQ)
    plan, out = u.start()
    sid = out['result']['session_id']
    dims = out['result']['dimensions']
    tasks = plan['plan']['task_ids']
    decisions = []
    for dim in dims:
        t = next(x for x in tasks if u.bank_task(x)['dimension_ids'][0] == dim)
        aid = u.submit(sid, t)['result']['attempt_id']
        decisions.append(u.decision(dim, [aid]))
    u.set_policy(ukit.policy(mode='coaching'))
    u.review(sid, decisions, reviewer='alice')          # self review while coaching
    u.set_policy(REQ)
    u.m('handover', 'set', '--session', sid, '--file', u.file('h.json', ukit.HANDOVER))
    _, rv = transfer(u, sid)
    u.m('close', '--session', sid, '--to', 'completed', '--reason', 'done')
    dm = {d['dimension_id']: d['decision_id'] for d in u.ext()['decisions'].values()
          if d['kind'] == 'attempt'}
    u.m('select', '--file', u.file('sel.json', {
        'milestone': 'handoff', 'actor_scope': {'actor_declared_id': 'alice',
                                                'profile': 'pipeline'},
        'dimension_decision_map': dm, 'transfer_decision_map': {'D2': rv['result']['decision_id']},
        'reservation_resolution_refs': []}))
    g = gate(u)
    print(g['decision'], [r['code'] for r in g['reasons']])
    assert g['decision'] == 'blocked'
    assert any(r['code'] == 'reviewer_not_distinct' for r in g['reasons'])


def test_rectification_after_review_blocks_until_rereviewed(tmp_path):
    u = U(tmp_path)
    sid = custom_flow(u, REQ)
    assert gate(u)['decision'] == 'allowed'
    a = next(x['attempt_id'] for x in u.ext()['attempts'].values()
             if x['dimension_ids'] == ['D5'])
    u.m('rectify', '--attempt', a, '--assistance-file', u.file('r.json', dict(
        ukit.ASSIST, ai_assistance_declared=True)))
    g = gate(u)
    assert g['decision'] == 'blocked'
    assert any(r['code'] == 'assistance_rectified_after_review' for r in g['reasons'])
    # Rectify is accepted with the review OFF? (probe)
    u.set_policy(dict(ukit.POLICY, mode='off'))
    o = u.m('rectify', '--attempt', a, '--assistance-file', u.file('r2.json', ukit.ASSIST),
            expect=None)
    print('rectify while off:', o.get('error', {}).get('code') or 'accepted')


def test_taskset_edit_mid_session_blocks(tmp_path):
    u = U(tmp_path)
    custom_flow(u, REQ)
    assert gate(u)['decision'] == 'allowed'
    p = u.case_dir / 'understanding.yaml'
    orig = p.read_text()
    p.write_text(orig.replace('Test fixture: no person reviewed this bank.',
                              'Test fixture: edited.'))
    g = gate(u)
    print(g['decision'], sorted({r['code'] for r in g['reasons']}))
    assert g['decision'] == 'blocked'
    p.write_text(orig)
    assert gate(u)['decision'] == 'allowed'
