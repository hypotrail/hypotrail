"""Regression tests for the independent review of the implementation (one per finding)."""
from __future__ import annotations

import pytest

import ukit
from mlkit.study import cli
from mlkit.study.understanding import actions, canonical, export as ex


def code(p):
    return p['error']['code']


def started(u):
    plan, out = u.start()
    return out['result']['session_id'], plan['plan']['task_ids']


def task_of(u, tasks, dim):
    return next(t for t in tasks if u.bank_task(t)['dimension_ids'][0] == dim)


@pytest.fixture
def u(tmp_path):
    u = ukit.U(tmp_path)
    u.set_policy(ukit.policy(mode='required'))
    return u


def test_author_cannot_review_or_overrule_on_a_critical_dimension(u):
    """Finding 1: no self-review on a critical dimension; a decision of another reviewer is
    replaced only through arbitration; a reservation is cleared without new evidence only by
    its own reviewer."""
    sid, tasks = started(u)
    a = u.submit(sid, task_of(u, tasks, 'D2'))['result']['attempt_id']
    out = u.review(sid, [u.decision('D2', [a])], reviewer='alice', expect=2)
    assert code(out) == 'review_required'
    first = u.review(sid, [u.decision('D2', [a], status='to_consolidate')], reviewer='bob')
    old = first['result']['decisions'][0]['decision_id']
    rid = next(iter(u.ext()['reservations']))
    override = u.decision('D2', [a], supersedes_ids=[old], resolves_reservation_ids=[rid],
                          correction_of_review_error=True)
    out = u.review(sid, [override], reviewer='dave', expect=2)
    assert code(out) == 'review_required'                    # another reviewer: arbitrate
    clear = u.decision('D2', [a], resolves_reservation_ids=[rid],
                       correction_of_review_error=True)
    out = u.review(sid, [clear], reviewer='dave', expect=2)
    assert code(out) == 'evidence_invalid'
    ok = u.review(sid, [u.decision('D2', [a], supersedes_ids=[old],
                                   resolves_reservation_ids=[rid],
                                   correction_of_review_error=True)], reviewer='bob')
    assert ok['result']['decisions'][0]['status'] == 'demonstrated'


def test_arbitration_choice_is_binding_for_the_gate(tmp_path):
    """Finding 2: the choice is one of the conflicting decisions; selecting the decision that
    lost the arbitration blocks the milestone."""
    u = ukit.U(tmp_path)
    sid = ukit.full_flow(u)
    sel = next(iter(u.ext()['selections'].values()))
    # Re-open D3 in a linked session with a conflict.
    _, out = u.start()
    sid2 = out['result']['session_id']
    t3 = next(t for t in u.ext()['sessions'][sid2]['task_ids']
              if u.bank_task(t)['dimension_ids'][0] == 'D3')
    a = u.submit(sid2, t3, 'Second session answer on D3.')['result']['attempt_id']
    good = u.review(sid2, [u.decision('D3', [a])], reviewer='bob')['result']['decisions'][0]
    bad = u.review(sid2, [u.decision('D3', [a], status='to_consolidate')],
                   reviewer='dave')['result']['decisions'][0]
    arb = {'arbiter_declared_id': 'erin', 'declaration': ukit.SIM, 'simulated': True,
           'conflicting_decision_ids': [good['decision_id'], bad['decision_id']],
           'reservation_ids': [], 'chosen_decision_id': sel['dimension_decision_map']['D2'],
           'rationale': 'x', 'evidence_refs': []}
    out = u.m('arbitrate', '--session', sid2, '--file', u.file('a1.json', arb), expect=2)
    assert code(out) == 'evidence_invalid'                    # not among the conflict
    arb['chosen_decision_id'] = bad['decision_id']
    arb['reservation_ids'] = list(u.ext()['reservations'])
    u.m('arbitrate', '--session', sid2, '--file', u.file('a2.json', arb))
    u.m('close', '--session', sid2, '--to', 'completed', '--reason', 'done')
    dm = dict(sel['dimension_decision_map'], D3=good['decision_id'])
    u.m('select', '--file', u.file('s.json', {
        'milestone': 'handoff', 'actor_scope': sel['actor_scope'],
        'dimension_decision_map': dm, 'transfer_decision_map': sel['transfer_decision_map'],
        'reservation_resolution_refs': []}))
    gate = u.call('check', '--milestone', 'handoff')['gate']
    assert gate['decision'] == 'blocked'
    assert {'code': 'lost_arbitration', 'dimension': 'D3'} in gate['reasons']
    assert sid


def test_peer_coverage_needs_a_selected_current_transfer(tmp_path):
    """Finding 3: no search for an old transfer; a transfer whose context changed is stale."""
    u = ukit.U(tmp_path)
    ukit.full_flow(u)
    sel = next(iter(u.ext()['selections'].values()))
    u.m('select', '--file', u.file('s.json', {
        'milestone': 'handoff', 'actor_scope': sel['actor_scope'],
        'dimension_decision_map': sel['dimension_decision_map'], 'transfer_decision_map': {},
        'reservation_resolution_refs': []}))
    gate = u.call('check', '--milestone', 'handoff')['gate']
    assert gate['missing_peer_dimensions'] == ['D2']
    u.m('select', '--file', u.file('s2.json', {
        'milestone': 'handoff', 'actor_scope': sel['actor_scope'],
        'dimension_decision_map': sel['dimension_decision_map'],
        'transfer_decision_map': sel['transfer_decision_map'],
        'reservation_resolution_refs': []}))
    assert u.call('check', '--milestone', 'handoff')['gate']['decision'] == 'allowed'
    (u.repo / 'src/transforms.py').write_text('changed\n')         # the transfer's code
    gate = u.call('check', '--milestone', 'handoff')['gate']
    assert 'D2' in gate['missing_peer_dimensions']


def test_coaching_carries_over_to_a_linked_session(u):
    """Finding 4: help received in one session makes the same task aided in the next."""
    sid, tasks = started(u)
    t = task_of(u, tasks, 'D3')
    a = u.submit(sid, t, 'First.')['result']['attempt_id']
    u.m('coach', '--attempt', a)
    u.m('close', '--session', sid, '--to', 'abandoned', '--reason', 'restart')
    _, out = u.start()
    again = u.submit(out['result']['session_id'], t, 'Same task after the hints.')['result']
    assert again['aided'] and not again['first_attempt']


def test_explicit_policy_rejects_reviews_made_under_another_policy(tmp_path):
    """Finding 5: a candidate reviewed under a looser policy does not pass a stricter one.

    Expectation changed in review round 5: the standalone verifier mirrors the gate's policy
    digest rule instead of its own ``policy_differs`` (a comparison of review terms): a
    policy whose digest differs from the embedded one gives the gate's codes for decisions
    made under another policy."""
    u = ukit.U(tmp_path)
    sid = ukit.full_flow(u)
    ukit.approve_all(u, sid)
    u.m('export', 'write', '--session', sid, '--repo', u.repo)
    strict = ukit.policy(mode='required', context_requirement='public_only',
                         evidence_requirement='recorded_decisions',
                         assistance_rule={'critical': 'unaided_required',
                                          'other': 'unaided_required'}, version=2)
    out = cli.run(['understanding', 'verify-export', '--repo', str(u.repo), '--target',
                   'worktree', '--policy-file', str(u.file('strict.json', strict))]).payload
    reasons = {r['code'] for r in out['generations'][0]['gate_result']['reasons']}
    assert {'selection_policy_changed', 'decision_policy_changed',
            'peer_coverage_missing'} <= reasons
    assert out['generations'][0]['gate_result']['decision'] == 'blocked'


def test_receipt_checks_the_announced_bytes(tmp_path):
    """Finding 6: a receipt with other bytes than the intent announced is refused."""
    u = ukit.U(tmp_path)
    sid = ukit.full_flow(u)
    ukit.approve_all(u, sid)
    u.m('export', 'write', '--session', sid, '--repo', u.repo)
    intent = next(iter(u.ext()['exports'].values()))
    intent_id = intent['intent_id']
    # The intent is final once published; a forged receipt cannot change it.
    out = actions.apply(u.study, 'export_receipt', {
        'intent_id': intent_id, 'verified_files': {n: '0' * 64 for n in ex.FILES}},
        request_id='forged', expected_revision=u.rev())
    assert out['result']['final'] is True
    assert u.ext()['exports'][intent_id]['status'] == 'published'


def test_export_works_without_a_selection(tmp_path):
    """Finding 8: in coaching, without any milestone selection, the author can approve."""
    u = ukit.U(tmp_path)
    u.set_policy()
    _, out = u.start()
    sid = out['result']['session_id']
    task = u.call('task', '--session', sid)['task']
    a = u.submit(sid, task['task_id'])['result']['attempt_id']
    u.review(sid, [u.decision(task['dimension_ids'][0], [a])], reviewer='bob')
    prev = ukit.approve_all(u, sid)
    assert 'alice' in prev['required_contributors']
    w = u.m('export', 'write', '--session', sid, '--repo', u.repo)
    assert w['receipt']['status'] == 'published'


def test_git_receipt_and_plan_use_the_announced_bytes(tmp_path):
    """Finding 9: an artefact edited after the export gets neither a plan nor a receipt."""
    u = ukit.U(tmp_path)
    sid = ukit.full_flow(u)
    ukit.approve_all(u, sid)
    w = u.m('export', 'write', '--session', sid, '--repo', u.repo)
    md = u.repo / ex.EXPORT_DIR / w['review_id'] / ex.MD_FILE
    md.write_text(md.read_text() + 'edited\n')
    out = u.call('git-plan', '--session', sid, '--repo', u.repo, expect=2)
    assert code(out) == 'export_stale'
    ukit.git(u.repo, 'add', '--', ex.EXPORT_DIR)
    ukit.git(u.repo, 'commit', '-q', '-m', 'edited review')
    out = u.m('git-receipt', '--session', sid, '--repo', u.repo, '--commit', 'HEAD', expect=2)
    assert code(out) == 'git_index_conflict'


def test_verifier_answers_invalid_on_malformed_artefacts(tmp_path):
    """Finding 10: untrusted content gives invalid, never an internal error."""
    u = ukit.U(tmp_path)
    sid = ukit.full_flow(u)
    ukit.approve_all(u, sid)
    w = u.m('export', 'write', '--session', sid, '--repo', u.repo)
    d = u.repo / ex.EXPORT_DIR / w['review_id']
    (d / ex.MANIFEST_FILE).write_bytes(b'[1,2]')
    o = cli.run(['understanding', 'verify-export', '--repo', str(u.repo), '--target', 'worktree'])
    assert o.exit_code == 0 and o.payload['public_integrity'] == 'invalid'
    doc = canonical.loads((d / ex.JSON_FILE).read_bytes())
    doc['privacy_review']['approvals'] = [1]
    (d / ex.JSON_FILE).write_bytes(canonical.dumps(doc))
    o = cli.run(['understanding', 'verify-export', '--repo', str(u.repo), '--target', 'worktree'])
    assert o.exit_code == 0 and o.payload['generations'][0]['public_integrity'] == 'invalid'


def test_float_or_malformed_input_is_a_refusal(u):
    """Minor findings: a raw float, a wrong shape deep in a file, an edited plan source."""
    sid, tasks = started(u)
    bad = dict(ukit.ASSIST, resources_used=[1.5])
    out = u.submit(sid, task_of(u, tasks, 'D2'), assist=bad, expect=2)
    assert code(out) == 'evidence_invalid'
    weird = {'reviewer_declared_id': 'bob', 'declaration': ukit.SIM, 'simulated': True,
             'decisions': [{**u.decision('D2', ['x']), 'criterion_results': 'nope'}]}
    out = u.m('review', '--session', sid, '--file', u.file('w.json', weird), expect=2)
    assert code(out) == 'evidence_invalid'
    dup = u.decision('D2', ['x'])
    dup['criterion_results'] = dup['criterion_results'] + dup['criterion_results'][:1]
    a = u.submit(sid, task_of(u, tasks, 'D2'))['result']['attempt_id']
    dup['attempt_ids'] = [a]
    out = u.review(sid, [dup], expect=2)
    assert code(out) == 'evidence_invalid'
    out = u.call('policy', 'set', '--file', u.file('p.json', ukit.policy(
        critical_dimensions=[['D2']])), '--author', 'lead', '--reason', 'x', mutation=True,
        expect=2)
    assert code(out) == 'policy_invalid'
