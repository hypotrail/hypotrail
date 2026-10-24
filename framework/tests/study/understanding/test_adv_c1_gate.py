"""Area C probes: the gate. Each test asserts the SPEC behaviour; a failure is a finding."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import advkit as rkit  # noqa: E402,F401
from advkit import U, ukit, gate, custom_flow, transfer  # noqa: E402

REQ = ukit.policy(mode='required')


def test_baseline_full_flow_is_allowed(tmp_path):
    u = U(tmp_path)
    custom_flow(u, REQ)
    g = gate(u)
    assert g['decision'] == 'allowed', g['reasons']


def test_unaided_rule_cannot_be_laundered_by_adding_an_unaided_attempt(tmp_path):
    """Critical D2 needs an unaided demonstration. The person answers 'I do not know'
    (unaided), is coached, answers the SAME task again (aided). The reviewer marks D2
    demonstrated citing both attempts. The demonstration rests on the aided answer:
    the gate must not count it as unaided (SPEC 07.4-5, 09, A04)."""
    u = U(tmp_path)

    def attempts(u, sid, dim, tid):
        if dim != 'D2':
            return None
        a1 = u.submit(sid, tid, 'I do not know.')['result']
        u.m('coach', '--attempt', a1['attempt_id'])
        a2 = u.submit(sid, tid, 'Better answer after the hints.')['result']
        assert a2['aided']
        return [a1['attempt_id'], a2['attempt_id']]

    custom_flow(u, REQ, attempts_for=attempts)
    g = gate(u)
    assert g['dimensions']['D2']['assistance'] == 'aided', g['dimensions']['D2']
    assert g['decision'] == 'blocked'


def test_aided_attempt_alone_is_blocked_on_critical(tmp_path):
    """Control: the aided attempt alone is refused by the gate."""
    u = U(tmp_path)

    def attempts(u, sid, dim, tid):
        if dim != 'D2':
            return None
        a1 = u.submit(sid, tid, 'I do not know.')['result']
        u.m('coach', '--attempt', a1['attempt_id'])
        a2 = u.submit(sid, tid, 'Better answer after the hints.')['result']
        return [a2['attempt_id']]

    custom_flow(u, REQ, attempts_for=attempts)
    g = gate(u)
    assert g['decision'] == 'blocked'
    assert any(r['code'] == 'assistance_not_admissible' for r in g['reasons'])


def test_team_coverage_of_three_people_can_be_satisfied(tmp_path):
    """team_coverage.minimum_people accepts 2..10. With 3, two distinct peers must be
    selectable; otherwise the policy can never allow (blocks when it should allow)."""
    u = U(tmp_path)
    pol = ukit.policy(mode='required', team_coverage={'minimum_people': 3})
    ids = {}

    def tmap(u, sid, current):
        _, rv = transfer(u, sid, peer='dave', reviewer='alice')
        ids['dave'] = rv['result']['decision_id']
        return {'D2': [current['D2'], ids['dave']]}

    try:
        custom_flow(u, pol, transfer_map=tmap)
    except AssertionError as exc:            # the select was refused
        raise AssertionError(f'a list of two transfer reviews cannot be selected: {exc}')
    g = gate(u)
    assert g['decision'] == 'allowed', g['reasons']


def test_moved_repository_check_and_export_agree(tmp_path):
    """After the repository moves, `check` and the protected action agree (A16): both read
    the recorded repository (`check --repo` is a preview that says so); `relocate` records
    the new place and both then allow."""
    import shutil
    u = U(tmp_path)
    custom_flow(u, REQ)
    new = tmp_path / 'moved'
    shutil.move(str(u.repo), str(new))
    g_new = gate(u, '--repo', str(new))
    g_def = gate(u)
    from mlkit.study import cli
    o = cli.run(['export', 'handoff', '--study', str(u.study), '--out', str(tmp_path / 'h')])
    print('check --repo NEW:', g_new['decision'], '| check:', g_def['decision'],
          '| export:', o.exit_code, o.payload.get('error', {}).get('code'))
    assert g_new['decision'] == 'allowed'
    assert 'repo_note' in u.call('check', '--milestone', 'handoff', '--repo', str(new))
    assert g_def['decision'] != 'allowed' and o.exit_code not in (0, 3)
    for s in u.ext()['sessions']:
        u.m('relocate', '--session', s, '--repo', new)
    assert gate(u)['decision'] == 'allowed'
    o = cli.run(['export', 'handoff', '--study', str(u.study), '--out', str(tmp_path / 'h2')])
    assert o.exit_code in (0, 3), o.payload


def test_transfer_after_session_completed_is_refused(tmp_path):
    """A completed session is final (SPEC 10: a new attempt after closing creates a linked
    session, without rewriting the previous one). Handover and transfers should not be
    added to it after closing."""
    u = U(tmp_path)
    sid = custom_flow(u, REQ, peer=False, select=False)
    assert u.ext()['sessions'][sid]['status'] == 'completed'
    h = u.m('handover', 'set', '--session', sid, '--file',
            u.file('h2.json', dict(ukit.HANDOVER, limits=['x'])), expect=None)
    tid, rv = transfer(u, sid, peer='dave') if 'error' not in h else (None, None)
    print('handover on completed:', 'error' not in h, '| transfer reviewed:', rv and rv['ok'])
    assert 'error' in h, 'handover set accepted on a completed session'


def test_peer_negative_review_is_not_masked_by_a_later_positive_one(tmp_path):
    """SPEC 09/10: an unrelated positive opinion never hides a current reservation. A
    transfer reviewed to_consolidate, then another transfer demonstrated on the same note."""
    u = U(tmp_path)

    def tmap(u, sid, current):
        transfer(u, sid, peer='dave', status='to_consolidate')
        return current

    custom_flow(u, REQ, transfer_map=tmap)
    g = gate(u)
    print(g['decision'], g['reasons'])
    assert g['decision'] == 'blocked'


def test_arbiter_may_not_be_a_party_to_the_conflict(tmp_path):
    """SPEC 09: the arbiter is a declared human allowed by the role policy. Probe: the
    reviewer whose decision is in conflict arbitrates and chooses their own decision."""
    u = U(tmp_path)
    u.set_policy(REQ)
    plan, out = u.start()
    sid = out['result']['session_id']
    t = next(t for t in plan['plan']['task_ids'] if u.bank_task(t)['dimension_ids'][0] == 'D3')
    a = u.submit(sid, t)['result']['attempt_id']
    first = u.review(sid, [u.decision('D3', [a])], reviewer='bob')
    second = u.review(sid, [u.decision('D3', [a], status='to_consolidate')], reviewer='dave')
    ids = [first['result']['decisions'][0]['decision_id'],
           second['result']['decisions'][0]['decision_id']]
    res = list(u.ext()['reservations'])
    arb = u.m('arbitrate', '--session', sid, '--file', u.file('arb.json', {
        'arbiter_declared_id': 'bob', 'declaration': ukit.SIM, 'simulated': True,
        'conflicting_decision_ids': ids, 'reservation_ids': res, 'chosen_decision_id': ids[0],
        'rationale': 'I keep mine.', 'evidence_refs': []}), expect=None)
    print(arb)
    assert 'error' in arb, 'a party to the conflict arbitrated it in its own favour'


def test_arbitration_resolves_reservation_without_new_evidence(tmp_path):
    """SPEC 09: every resolution of a difficulty rests on new admissible evidence or a
    reasoned correction of a review error. Probe: an arbitration naming only the
    reservation, no evidence_refs, resolves it."""
    u = U(tmp_path)
    u.set_policy(REQ)
    plan, out = u.start()
    sid = out['result']['session_id']
    t = next(t for t in plan['plan']['task_ids'] if u.bank_task(t)['dimension_ids'][0] == 'D3')
    a = u.submit(sid, t)['result']['attempt_id']
    u.review(sid, [u.decision('D3', [a], status='to_consolidate')], reviewer='bob')
    res = list(u.ext()['reservations'])
    arb = u.m('arbitrate', '--session', sid, '--file', u.file('arb.json', {
        'arbiter_declared_id': 'eve', 'declaration': ukit.SIM, 'simulated': True,
        'conflicting_decision_ids': [], 'reservation_ids': res, 'chosen_decision_id': None,
        'rationale': 'ok', 'evidence_refs': ['../../etc/passwd']}), expect=None)
    print(arb, u.ext()['reservations'])
    assert 'error' in arb


def test_linked_session_must_be_of_the_same_person(tmp_path):
    u = U(tmp_path)
    u.set_policy(REQ)
    _, out = u.start(actor='alice')
    s1 = out['result']['session_id']
    args = ['plan', '--profile', 'pipeline', '--milestone', 'handoff', '--actor', 'bob',
            '--previous-session', s1, '--repo', u.repo, '--sources-file',
            u.file('s.json', ukit.SOURCES), '--write-plan', u.root / 'inputs' / 'p2.json']
    u.call(*args)
    o = u.m('start', '--plan-file', u.root / 'inputs' / 'p2.json', expect=None)
    print(o.get('error') or o['result'])
    assert 'error' in o, 'bob\'s session linked to alice\'s session'
