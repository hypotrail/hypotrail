"""A04–A08, A12, A22, A27, A28: attempts, help, proposals, human reviews, conflicts,
reservations, handover, concurrency, limits. Every reviewer here is a simulated fixture."""
from __future__ import annotations

import json

import pytest

import ukit


@pytest.fixture
def u(tmp_path):
    u = ukit.U(tmp_path)
    u.set_policy(ukit.policy(mode='required'))
    return u


def code(p):
    return p['error']['code']


def started(u):
    plan, out = u.start()
    return out['result']['session_id'], plan['plan']['task_ids']


def task_of(u, tasks, dim):
    return next(t for t in tasks if u.bank_task(t)['dimension_ids'][0] == dim)


def test_first_attempt_is_immutable_and_coaching_marks_help(u):
    """A04: the first attempt stays; coaching is recorded before hints are given; the same
    question answered again after coaching is an aided answer; a re-demonstration needs a
    new variant."""
    sid, tasks = started(u)
    t2 = task_of(u, tasks, 'D2')
    first = u.submit(sid, t2, 'I am not sure.')['result']
    assert first['first_attempt'] and not first['aided']
    aid = first['attempt_id']
    stored = dict(u.ext()['attempts'][aid])
    coach = u.m('coach', '--attempt', aid)
    assert coach['hints'] and coach['result']['hint_count'] == len(coach['hints'])
    second = u.submit(sid, t2, 'Better answer after hints.')['result']
    assert not second['first_attempt'] and second['aided']
    assert u.ext()['attempts'][aid]['response_sha256'] == stored['response_sha256']
    # The difficulty is recorded; the same question again cannot resolve it.
    d = u.review(sid, [u.decision('D2', [aid], status='to_consolidate')])
    rid = next(iter(u.ext()['reservations']))
    retry = u.decision('D2', [second['attempt_id']], resolves_reservation_ids=[rid])
    out = u.review(sid, [retry], expect=2)
    assert code(out) == 'evidence_invalid' and 'new variant' in out['error']['message']
    # A new variant of the same family, answered without hints, resolves it.
    variant = next(t['task_id'] for t in u.bank()['tasks'] if t['variant_family']
                   == u.bank_task(t2)['variant_family'] and t['task_id'] != t2)
    assert variant not in tasks
    offered = [u.call('task', '--session', sid)['task']['task_id']]
    for t in tasks:                                  # answer the rest of the plan first
        if t != t2:
            u.submit(sid, t, f'Answer to {t}.')
    offered.append(u.call('task', '--session', sid)['task']['task_id'])
    assert offered[-1] == variant                     # the new variant, never t2 again
    new = u.submit(sid, variant, 'A new reasoning on another case.')['result']
    assert new['first_attempt'] and not new['aided']
    ok = u.review(sid, [u.decision('D2', [new['attempt_id']], resolves_reservation_ids=[rid])])
    assert ok['result']['decisions'][0]['status'] == 'demonstrated'
    assert u.ext()['reservations'][rid]['status'] == 'resolved'
    assert d['result']['decisions'][0]['status'] == 'to_consolidate'   # history kept
    assert u.ext()['attempts'][aid]['response_sha256'] == stored['response_sha256']


def test_proposal_never_creates_a_human_decision(u):
    """A05: a correct proposal stays a proposal: the dimension needs a human review and a
    required milestone stays blocked."""
    sid, tasks = started(u)
    a = u.submit(sid, task_of(u, tasks, 'D2'), 'The input known later must go, because the '
                 'desk acts before the outcome.')['result']['attempt_id']
    from mlkit.study.understanding import canonical
    rubric = u.rubric('D2')
    prop = {'attempt_id': a, 'rubric_digest': canonical.digest(rubric),
            'author': {'type': 'model', 'name': 'any', 'version': '1'},
            'criteria': [{'criterion_id': c['criterion_id'], 'proposed': 'met',
                          'excerpts': ['the desk acts before the outcome'], 'refs': [],
                          'justification': 'The answer links the input to the moment.'}
                         for c in rubric['criteria']],
            'uncertainties': ['critical: the location is not given']}
    out = u.m('propose-review', '--session', sid, '--file', u.file('prop.json', prop))
    assert out['result']['human_decision_created'] is False
    assert not [d for d in u.ext()['decisions'].values() if d['kind'] == 'attempt']
    view = u.call('status')['sessions'][0]
    assert {d['dimension_id']: d['status'] for d in view['dimensions']}['D2'] == 'needs_review'
    gate = u.call('check', '--milestone', 'handoff')['gate']
    assert gate['decision'] == 'blocked'


@pytest.mark.parametrize('bad, why', [
    ({'excerpts': ['words not in the answer']}, 'verbatim'),
    ({'justification': 'run `rm -rf /` first'}, 'command'),
    ({'justification': 'see file:///etc/passwd'}, 'command'),
    ({'refs': ['../../secret']}, 'outside'),
])
def test_proposal_inputs_are_data_not_instructions(u, bad, why):
    """A22: excerpts must match, commands and file links are refused, refs are allowlisted."""
    sid, tasks = started(u)
    a = u.submit(sid, task_of(u, tasks, 'D2'), 'An answer.')['result']['attempt_id']
    from mlkit.study.understanding import canonical
    rubric = u.rubric('D2')
    crit = {'criterion_id': rubric['criteria'][0]['criterion_id'], 'proposed': 'met',
            'excerpts': [], 'refs': [], 'justification': 'ok'}
    crit.update(bad)
    prop = {'attempt_id': a, 'rubric_digest': canonical.digest(rubric),
            'author': {'type': 'agent', 'name': 'x', 'version': '1'}, 'criteria': [crit],
            'uncertainties': []}
    out = u.m('propose-review', '--session', sid, '--file', u.file('p.json', prop), expect=2)
    assert code(out) == 'evidence_invalid'


def test_keyword_rubric_is_not_a_matcher(u):
    """A06: demonstrated needs every mandatory criterion met by a human result; a review
    that marks a criterion not met cannot be demonstrated, whatever words the answer has."""
    sid, tasks = started(u)
    a = u.submit(sid, task_of(u, tasks, 'D2'), 'leakage leakage availability prediction moment '
                 'validity — but the input stays because it improves the score')['result']
    d = u.decision('D2', [a['attempt_id']])
    d['criterion_results'][0]['result'] = 'not_met'
    out = u.review(sid, [d], expect=2)
    assert code(out) == 'evidence_invalid'
    d['status'] = 'to_consolidate'
    u.review(sid, [d])
    assert u.call('status')['sessions'][0]['dimensions'][0]['status'] in (
        'not_evaluated', 'to_consolidate')


def test_missing_mandatory_or_unevaluated_dimension_blocks(u):
    """A07: an unevaluated dimension blocks; no average compensates a gap."""
    sid, tasks = started(u)
    for t in tasks:
        dim = u.bank_task(t)['dimension_ids'][0]
        if dim == 'D6':
            continue                                      # D6 never answered
        a = u.submit(sid, t)['result']['attempt_id']
        u.review(sid, [u.decision(dim, [a])])
    u.m('close', '--session', sid, '--to', 'completed', '--reason', 'done')
    dm = {d['dimension_id']: d['decision_id'] for d in u.ext()['decisions'].values()}
    u.m('select', '--file', u.file('s.json', {
        'milestone': 'handoff', 'actor_scope': {'actor_declared_id': 'alice',
                                                'profile': 'pipeline'},
        'dimension_decision_map': dm, 'transfer_decision_map': {},
        'reservation_resolution_refs': []}))
    gate = u.call('check', '--milestone', 'handoff')['gate']
    assert gate['decision'] == 'blocked'
    assert 'D6' in gate['missing_dimensions'] and 'D2' in gate['missing_peer_dimensions']


def test_peer_with_author_id_and_note_approval_are_not_a_handover(u):
    """A08: same declared id refused; approving the note is not a handover task."""
    sid, _ = started(u)
    u.m('handover', 'set', '--session', sid, '--file', u.file('h.json', ukit.HANDOVER))
    task = next(t['task_id'] for t in u.bank()['tasks'] if t['kind'] == 'transfer')
    out = u.m('transfer', 'start', '--session', sid, '--peer', 'alice', '--task', task, expect=2)
    assert code(out) == 'evidence_invalid' and 'does not authenticate' in out['error']['message']
    t = u.m('transfer', 'start', '--session', sid, '--peer', 'carol', '--task', task)['result']
    out = u.m('transfer', 'submit', '--transfer', t['transfer_id'], '--response-file',
              u.file('r.txt', 'I read and approve the note.'), '--assistance-file',
              u.file('a.json', ukit.ASSIST), '--evidence-file',
              u.file('e.json', {'evidence_refs': [], 'difficulty_or_blockers': []}), expect=2)
    assert code(out) == 'evidence_invalid' and 'own references' in out['error']['message']
    cover = u.call('check', '--milestone', 'handoff')['gate']
    assert cover['decision'] == 'blocked'


def test_handover_change_stales_the_transfer_but_results_do_not(u):
    """A29 (handover): editing HandoverContent, even a removal, makes the transfer stale;
    adding review results does not."""
    sid = ukit.full_flow(u)
    gate = u.call('check', '--milestone', 'handoff')['gate']
    assert gate['decision'] == 'allowed'
    # Approvals and an export of the results change nothing for the transfer.
    ukit.approve_all(u, sid)
    assert u.call('check', '--milestone', 'handoff')['gate']['decision'] == 'allowed'
    shorter = dict(ukit.HANDOVER, safety_rules=[])
    out = u.m('handover', 'set', '--session', sid, '--file', u.file('h2.json', shorter))
    assert out['result']['transfers_now_stale']
    gate = u.call('check', '--milestone', 'handoff')['gate']
    assert gate['decision'] == 'blocked' and gate['missing_peer_dimensions'] == ['D2']


def test_concurrent_and_idempotent_submissions(u):
    """A12: two submits at the same revision give one transition; an identical retry
    replays; the same request id with other content is refused."""
    sid, tasks = started(u)
    rev = u.rev()
    t = task_of(u, tasks, 'D2')
    one = u.submit(sid, t, 'Answer one.', request_id='same', revision=rev)
    again = u.submit(sid, t, 'Answer one.', request_id='same', revision=rev)
    assert again['replayed'] and again['result'] == one['result']
    other = u.submit(sid, t, 'Answer two.', request_id='same', revision=rev, expect=2)
    assert code(other) == 'idempotency_conflict'
    late = u.submit(sid, t, 'Answer three.', request_id='other', revision=rev, expect=2)
    assert code(late) == 'stale_revision'
    assert len(u.ext()['attempts']) == 1


def test_late_review_against_a_changed_context_has_no_current_effect(u):
    """A12: a review recorded after the sources changed stays archived history; the gate
    sees the change (stale) instead of taking the review as current."""
    sid = ukit.full_flow(u)
    (u.repo / 'src/transforms.py').write_text('def fit_imputer(train):\n    return 0\n')
    gate = u.call('check', '--milestone', 'handoff')['gate']
    assert gate['decision'] == 'blocked' and 'D5' in gate['stale_dimensions']
    # A late review (the session is closed): refused, nothing current changes.
    a = next(x['attempt_id'] for x in u.ext()['attempts'].values()
             if 'D5' in x['dimension_ids'])
    late = u.review(sid, [u.decision('D5', [a])], expect=2)
    assert code(late) == 'invalid_transition'
    assert u.call('check', '--milestone', 'handoff')['gate']['decision'] == 'blocked'


def test_contradictory_decisions_need_arbitration_in_both_orders(tmp_path):
    """A27: demonstrated then to_consolidate, and the reverse, on the same evidence: no
    last-write-wins; an arbitration settles it; a positive unrelated review never hides an
    open reservation; an active session satisfies nothing."""
    for order in (('demonstrated', 'to_consolidate'), ('to_consolidate', 'demonstrated')):
        u = ukit.U(tmp_path / order[0])
        u.set_policy(ukit.policy(mode='required'))
        sid, tasks = started(u)
        a = u.submit(sid, task_of(u, tasks, 'D3'))['result']['attempt_id']
        first = u.review(sid, [u.decision('D3', [a], status=order[0])], reviewer='bob')
        second = u.review(sid, [u.decision('D3', [a], status=order[1])], reviewer='dave')
        status = u.call('status')['sessions'][0]
        d3 = next(d for d in status['dimensions'] if d['dimension_id'] == 'D3')
        assert d3['status'] in ('needs_review', 'to_consolidate')
        assert u.call('status')['conflicts']
        ids = [first['result']['decisions'][0]['decision_id'],
               second['result']['decisions'][0]['decision_id']]
        pos = ids[order.index('demonstrated')]
        reservations = list(u.ext()['reservations'])
        arb = {'arbiter_declared_id': 'erin', 'declaration': ukit.SIM, 'simulated': True,
               'conflicting_decision_ids': ids, 'reservation_ids': reservations,
               'chosen_decision_id': pos, 'rationale': 'Simulated: the second reading holds.',
               'evidence_refs': []}
        u.m('arbitrate', '--session', sid, '--file', u.file('arb.json', arb))
        assert not u.call('status')['conflicts']
        d3 = next(d for d in u.call('status')['sessions'][0]['dimensions']
                  if d['dimension_id'] == 'D3')
        assert d3['status'] == 'demonstrated'


def test_unrelated_positive_review_does_not_hide_a_reservation(u):
    sid, tasks = started(u)
    t = task_of(u, tasks, 'D3')
    a = u.submit(sid, t)['result']['attempt_id']
    u.review(sid, [u.decision('D3', [a], status='to_consolidate')])
    b = u.submit(sid, task_of(u, tasks, 'D2'))['result']['attempt_id']
    out = u.review(sid, [u.decision('D3', [b])], expect=2)        # D2 attempt for D3
    assert code(out) == 'evidence_invalid'
    status = u.call('status')
    assert status['open_reservations']
    # Selecting from an active session is refused (A27).
    did = next(iter(u.ext()['decisions']))
    out = u.m('select', '--file', u.file('s.json', {
        'milestone': 'handoff', 'actor_scope': {'actor_declared_id': 'alice',
                                                'profile': 'pipeline'},
        'dimension_decision_map': {'D3': did}, 'transfer_decision_map': {},
        'reservation_resolution_refs': []}), expect=2)
    assert code(out) == 'invalid_transition'


def test_new_rubric_needs_a_new_review(tmp_path):
    """A27: a changed rubric does not reuse an old human decision."""
    u = ukit.U(tmp_path)
    ukit.full_flow(u)
    path = u.case_dir / 'understanding.yaml'
    path.write_text(path.read_text().replace('Links the inclusion of an input',
                                             'Ties the inclusion of an input'))
    gate = u.call('check', '--milestone', 'handoff')['gate']
    assert gate['decision'] == 'blocked'
    assert {'rubric_changed', 'bank_changed'} <= {r['code'] for r in gate['reasons']}


def test_removed_answer_keeps_judgement_and_follows_evidence_requirement(tmp_path):
    """A28: an answer deleted outside the engine: judgement kept, availability unavailable,
    a new review on it refused, the milestone follows evidence_requirement."""
    u = ukit.U(tmp_path)
    sid = ukit.full_flow(u)
    attempt = next(iter(u.ext()['attempts'].values()))
    (u.study / '.hypotrail' / 'blobs' / attempt['response_sha256']).unlink()
    # A new review on the missing answer is impossible (a linked session would be needed,
    # and its review refuses an unavailable payload).
    assert u.ext()['sessions'][sid]['status'] == 'completed'
    status = u.call('status')['sessions'][0]
    assert status['unavailable_answers'] == 1
    dims = [d for d in status['dimensions'] if d['evidence_availability'] == 'unavailable']
    assert dims and all(d['status'] == 'demonstrated' for d in dims)
    gate = u.call('check', '--milestone', 'handoff')['gate']
    assert gate['decision'] == 'blocked'
    assert 'evidence_unavailable' in {r['code'] for r in gate['reasons']}
    relaxed = u.file('relaxed.json', ukit.policy(mode='required',
                                                 evidence_requirement='recorded_decisions'))
    gate = u.call('check', '--milestone', 'handoff', '--policy-file', relaxed)['gate']
    assert 'evidence_unavailable' not in {r['code'] for r in gate['reasons']}
    assert 'evidence_not_reauditable' in gate['limitations']


def test_answers_never_reach_logs_outputs_or_errors(u):
    """A22: the answer text appears in no revision record, event, status or error."""
    secret = 'UNIQUE-ANSWER-TEXT-7f3a'
    sid, tasks = started(u)
    out = u.submit(sid, task_of(u, tasks, 'D2'), f'{secret} my reasoning')
    assert secret not in json.dumps(out)
    assert secret not in json.dumps(u.call('status'))
    home = u.study / '.hypotrail'
    for name in ('revisions.jsonl', 'events.jsonl', 'state.json'):
        assert secret not in (home / name).read_text()
    big = u.submit(sid, task_of(u, tasks, 'D3'), 'x' * 70000, expect=2)
    assert code(big) == 'evidence_invalid' and 'x' * 50 not in json.dumps(big)


def test_input_limits_and_depth(u):
    sid, tasks = started(u)
    deep = {}
    cur = deep
    for _ in range(20):
        cur['k'] = {}
        cur = cur['k']
    out = u.m('review', '--session', sid, '--file', u.file('deep.json', deep), expect=2)
    assert code(out) == 'evidence_invalid'
    out = u.m('review', '--session', sid, '--file',
              u.file('dup.json', '{"a": 1, "a": 2}'), expect=2)
    assert code(out) == 'evidence_invalid'


def test_reviewer_must_be_distinct_for_critical_dimensions(u):
    """In required mode the author never reviews themself on a critical dimension; on another
    dimension a self-review is recorded and the policy decides."""
    sid, tasks = started(u)
    a = u.submit(sid, task_of(u, tasks, 'D2'))['result']['attempt_id']
    out = u.review(sid, [u.decision('D2', [a])], reviewer='alice', expect=2)
    assert code(out) == 'review_required'
    b = u.submit(sid, task_of(u, tasks, 'D6'))['result']['attempt_id']
    ok = u.review(sid, [u.decision('D6', [b])], reviewer='alice')
    assert ok['result']['decisions'][0]['status'] == 'demonstrated'


def test_new_review_on_a_removed_answer_is_refused(u):
    """A28: a review cannot rest on an answer that is no longer available."""
    sid, tasks = started(u)
    a = u.submit(sid, task_of(u, tasks, 'D3'), 'An answer to lose.')['result']['attempt_id']
    sha = u.ext()['attempts'][a]['response_sha256']
    (u.study / '.hypotrail' / 'blobs' / sha).unlink()
    out = u.review(sid, [u.decision('D3', [a])], expect=2)
    assert code(out) == 'evidence_unavailable'
    assert 'An answer to lose' not in json.dumps(out)
