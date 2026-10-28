"""Round 2 of the understanding review, area C (C2-1 to C2-7): regression tests.

Every human here is a simulated declaration (``ukit.SIM``, ``simulated: true``); every study
and repository lives in a temporary directory. Several tests are ported from the reviewer's
reproducing tests of round 2.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import advkit  # noqa: E402,F401
from advkit import U, ukit, gate, custom_flow, transfer, code, SIM  # noqa: E402
from mlkit.study import cli, cmd_export as ce  # noqa: E402

REQ = ukit.policy(mode='required')


def _archive_copy(u, dst: Path, *, git_init=False) -> Path:
    """The committed tree of the project exported elsewhere (a frozen copy)."""
    dst.mkdir()
    tar = subprocess.run(['git', '-C', str(u.repo), 'archive', 'HEAD'], capture_output=True,
                         check=True).stdout
    subprocess.run(['tar', '-x', '-C', str(dst)], input=tar, check=True)
    if git_init:
        ukit.git(dst, 'init', '-q', '-b', 'main')
    return dst


def _relocate(u, sid, repo, *, author='alice', reason='The repository moved.', expect=0,
              **kw):
    args = ['relocate', '--session', sid, '--repo', repo]
    if author is not None:
        args += ['--author', author]
    if reason is not None:
        args += ['--reason', reason]
    return u.m(*args, expect=expect, **kw)


# --- C2-1: relocate is a recorded move, not a way to read freshness elsewhere -------------

def test_relocate_to_a_frozen_copy_while_the_repository_exists_is_refused(tmp_path):
    """Ported: the real sources change (stale, blocked); a relocation to a frozen copy of the
    old tree, Git work tree or not, is refused while the recorded repository still exists,
    so the gate stays blocked and the export handoff refuses."""
    u = U(tmp_path)
    sid = custom_flow(u, REQ)
    assert gate(u)['decision'] == 'allowed'
    plain = _archive_copy(u, tmp_path / 'crafted')
    gitted = _archive_copy(u, tmp_path / 'crafted-git', git_init=True)
    (u.repo / 'src/transforms.py').write_text('def fit_imputer(train):\n    return 0\n')
    g = gate(u)
    assert g['decision'] == 'blocked' and g['stale_dimensions'], g['reasons']
    rev = u.rev()
    out = _relocate(u, sid, plain, expect=2)
    assert code(out) == 'path_outside_scope'          # not a Git work tree
    out = _relocate(u, sid, gitted, expect=2)
    assert code(out) == 'invalid_transition'          # the recorded repository still exists
    assert u.rev() == rev
    assert gate(u)['decision'] == 'blocked'
    o = cli.run(['export', 'handoff', '--study', str(u.study), '--out', str(tmp_path / 'h')])
    assert o.exit_code not in (0, 3)


def test_relocate_needs_author_and_reason(tmp_path):
    u = U(tmp_path)
    sid = custom_flow(u, REQ)
    new = tmp_path / 'moved'
    shutil.move(str(u.repo), str(new))
    for author, reason in ((None, 'moved'), ('alice', None)):
        out = cli.run(['understanding', 'relocate', '--session', sid, '--repo', str(new),
                       *(['--author', author] if author else []),
                       *(['--reason', reason] if reason else []),
                       '--study', str(u.study), '--request-id', 'r-x',
                       '--expected-revision', str(u.rev())])
        assert out.exit_code != 0, out.payload
    out = _relocate(u, sid, new, author='alice', reason='   ', expect=2)
    assert code(out) == 'evidence_invalid'
    assert not u.ext()['sessions'][sid].get('relocations')


def test_relocate_needs_the_top_level_of_a_git_work_tree(tmp_path):
    u = U(tmp_path)
    sid = custom_flow(u, REQ)
    new = tmp_path / 'moved'
    shutil.move(str(u.repo), str(new))
    out = _relocate(u, sid, new / 'src', expect=2)
    assert code(out) == 'path_outside_scope'
    assert u.ext()['sessions'][sid]['repo_override'] is None


def test_relocation_is_recorded_and_shown_by_the_gate_and_status(tmp_path):
    """A real move: the recorded repository is gone, the new place is the top level of a
    Git work tree; the author and reason are kept in the session's relocation history, and
    the gate result and `status` name the repository each session's freshness was read
    from. Replays and stale revisions keep their usual semantics."""
    u = U(tmp_path)
    sid = custom_flow(u, REQ)
    before = gate(u)
    assert before['repositories'] == [{'session_id': sid, 'repository': str(u.repo.resolve()),
                                       'origin': 'recorded_at_start', 'exists': True,
                                       'relocations': 0}]
    new = tmp_path / 'moved'
    shutil.move(str(u.repo), str(new))
    assert gate(u)['decision'] != 'allowed'
    rev = u.rev()
    stale = _relocate(u, sid, new, expect=2, revision=rev - 1)
    assert code(stale) == 'stale_revision' and u.rev() == rev
    first = _relocate(u, sid, new, request_id='reloc-1', revision=rev)
    assert first['result']['from'] == str(u.repo.resolve())
    assert first['result']['to'] == str(new.resolve())
    again = _relocate(u, sid, new, request_id='reloc-1', revision=rev)
    assert again['replayed'] and again['result'] == first['result']
    history = u.ext()['sessions'][sid]['relocations']
    assert len(history) == 1
    assert history[0]['author_declared_id'] == 'alice'
    assert history[0]['reason'] == 'The repository moved.'
    g = gate(u)
    assert g['decision'] == 'allowed', g['reasons']
    assert g['repositories'] == [{'session_id': sid, 'repository': str(new.resolve()),
                                  'origin': 'relocated', 'exists': True, 'relocations': 1}]
    st = u.call('status', '--session', sid)['sessions'][0]
    assert st['repository']['repository'] == str(new.resolve())
    assert st['repository']['origin'] == 'relocated'
    assert st['relocations'][0]['author_declared_id'] == 'alice'
    preview = u.call('status', '--session', sid, '--repo', str(new))['sessions'][0]
    assert preview['repository']['origin'] == 'preview'
    # Relocating again to the same place, or back to the copy that is gone, is refused.
    assert code(_relocate(u, sid, new, expect=2)) == 'invalid_transition'


# --- C2-2: the gate re-checks only the arbitrations it relies on ---------------------------

def _arb(u, sid, arbiter, ids, res, chosen, evidence=(), expect=None):
    return u.m('arbitrate', '--session', sid, '--file', u.file(f'arb-{u.n}.json', {
        'arbiter_declared_id': arbiter, 'declaration': SIM, 'simulated': True,
        'conflicting_decision_ids': ids, 'reservation_ids': res, 'chosen_decision_id': chosen,
        'rationale': 'Simulated arbitration.', 'evidence_refs': list(evidence)}), expect=expect)


def _conflict_on_d3(u, sid, plan):
    t3 = next(t for t in plan['plan']['task_ids'] if u.bank_task(t)['dimension_ids'][0] == 'D3')
    a = u.submit(sid, t3)['result']['attempt_id']
    good = u.review(sid, [u.decision('D3', [a])], reviewer='bob')['result']['decisions'][0]
    bad = u.review(sid, [u.decision('D3', [a], status='to_consolidate')],
                   reviewer='dave')['result']['decisions'][0]
    res = [r for r, x in u.ext()['reservations'].items() if x['decision_id'] == bad['decision_id']]
    return good['decision_id'], bad['decision_id'], res


def test_an_old_arbitration_of_an_unused_session_does_not_block_for_ever(tmp_path):
    """Ported: session 1 (arbiters any_declared) has a conflict on D3 arbitrated by frank.
    The team adopts v2 (arbiters: erin); alice redoes everything in session 2.

    Expectation changed in review round 3 (R3C-1): the gate counts the conflicts and
    reservations of every session, so it does rely on frank's arbitration (it settles the
    session 1 conflict and closes its reservation). Under v2 it is not admissible, settles
    nothing, and the gate blocks (``arbitration_not_admissible``) where round 2 allowed. It
    does not block for ever: erin, the arbiter v2 names, settles the conflict again in
    session 1 (``arbitrate`` accepts an abandoned session since round 3), and frank's
    arbitration, which nothing relies on any more, no longer blocks."""
    u = U(tmp_path)
    u.set_policy(REQ)
    plan, out = u.start()
    s1 = out['result']['session_id']
    good, bad, res = _conflict_on_d3(u, s1, plan)
    r = _arb(u, s1, 'frank', [good, bad], res, good)
    assert r['ok'], r
    u.m('close', '--session', s1, '--to', 'abandoned', '--reason', 'restart under v2')
    v2 = ukit.policy(mode='required', version=2, role_policy={'arbiters': ['erin']})
    custom_flow(u, v2)
    g = gate(u)
    assert g['decision'] == 'blocked', g['reasons']
    assert {'code': 'arbitration_not_admissible', 'dimension': 'D3'} in g['reasons']
    assert {'code': 'unarbitrated_conflict', 'dimension': 'D3',
            'detail': f'{good},{bad}'} in g['reasons']
    assert {'code': 'open_reservation', 'dimension': 'D3', 'detail': res[0]} in g['reasons']
    again = _arb(u, s1, 'erin', [good, bad], res, good)
    assert again['ok'], again
    g = gate(u)
    assert g['decision'] == 'allowed', g['reasons']


def test_an_arbitration_the_gate_relies_on_is_still_rechecked(tmp_path):
    """C-M3 kept: the selected decision is the one an arbitration chose; under a policy
    whose arbiter list no longer names the arbiter, the gate reports
    arbitration_not_admissible for that dimension."""
    u = U(tmp_path)
    u.set_policy(REQ)
    plan, out = u.start()
    sid = out['result']['session_id']
    dims = out['result']['dimensions']
    good, bad, res = _conflict_on_d3(u, sid, plan)
    assert _arb(u, sid, 'frank', [good, bad], res, good)['ok']
    decisions = []
    for dim in dims:
        if dim == 'D3':
            continue
        t = next(t for t in plan['plan']['task_ids'] if u.bank_task(t)['dimension_ids'][0] == dim)
        a = u.submit(sid, t)['result']['attempt_id']
        decisions.append(u.decision(dim, [a]))
    u.review(sid, decisions, reviewer='bob')
    u.m('handover', 'set', '--session', sid, '--file', u.file('ho.json', ukit.HANDOVER))
    _, rv = transfer(u, sid)
    u.m('close', '--session', sid, '--to', 'completed', '--reason', 'done')
    ext = u.ext()
    dm = {d['dimension_id']: d['decision_id'] for d in ext['decisions'].values()
          if d['kind'] == 'attempt' and d['decision_id'] != bad}
    u.m('select', '--file', u.file('sel.json', {
        'milestone': 'handoff', 'actor_scope': {'actor_declared_id': 'alice',
                                                'profile': 'pipeline'},
        'dimension_decision_map': dm, 'transfer_decision_map': {'D2': rv['result']['decision_id']},
        'reservation_resolution_refs': []}))
    g = gate(u)
    assert g['decision'] == 'allowed', g['reasons']
    strict = u.file('strict.json', ukit.policy(mode='required',
                                               role_policy={'arbiters': ['erin']}))
    g2 = gate(u, '--policy-file', strict)
    assert {'code': 'arbitration_not_admissible', 'dimension': 'D3'} in g2['reasons']


def test_the_session_policy_arbiter_list_still_applies_after_a_toggle(tmp_path):
    """The session's own policy and the current one both bound who arbitrates: relaxing the
    current arbiter list does not admit an arbiter the session's policy does not name."""
    u = U(tmp_path)
    u.set_policy(ukit.policy(mode='required', role_policy={'arbiters': ['erin']}))
    plan, out = u.start()
    sid = out['result']['session_id']
    good, bad, res = _conflict_on_d3(u, sid, plan)
    u.set_policy(ukit.policy(mode='required', version=2))          # any_declared now
    refused = _arb(u, sid, 'frank', [good, bad], res, good, expect=2)
    assert code(refused) == 'review_required'
    assert _arb(u, sid, 'erin', [good, bad], res, good)['ok']


# --- C2-3: the exported peer coverage is the gate's ----------------------------------------

def _verify(u, policy_doc):
    pf = u.file(f'vpol-{u.n}.json', policy_doc)
    o = cli.run(['understanding', 'verify-export', '--repo', str(u.repo), '--target',
                 'worktree', '--policy-file', str(pf), '--study', str(u.study)]).payload
    return o['generations'][0]['gate_result']


def test_export_peer_coverage_follows_the_selection(tmp_path):
    """Ported: the selection names no transfer for D2, so the gate blocks
    (peer_coverage_missing). The export projection no longer searches for any demonstrated
    transfer: it reports the same gap, and verify-export under the same policy blocks.

    Expectation changed in review round 5: local verification returns the study's own gate,
    whose reason also carries the coverage status as ``detail``; the assertion compares code
    and dimension, and requires the very reason ``check`` gives."""
    u = U(tmp_path)
    sid = custom_flow(u, REQ, transfer_map=lambda u, sid, cur: {})
    g = gate(u)
    assert g['decision'] == 'blocked' and g['missing_peer_dimensions'] == ['D2'], g['reasons']
    prev = ukit.approve_all(u, sid)
    assert {'kind': 'peer_coverage_missing', 'ref': 'D2'} in prev['known_gaps']
    u.m('export', 'write', '--session', sid, '--repo', u.repo)
    gr = _verify(u, REQ)
    assert gr['decision'] != 'allowed'
    assert ('peer_coverage_missing', 'D2') in {(r['code'], r.get('dimension'))
                                               for r in gr['reasons']}
    assert [r for r in gr['reasons'] if r['code'] == 'peer_coverage_missing'] == \
        [r for r in g['reasons'] if r['code'] == 'peer_coverage_missing']


def test_export_peer_coverage_without_a_selection_is_missing(tmp_path):
    u = U(tmp_path)
    sid = custom_flow(u, REQ, select=False)
    prev = u.call('export', 'preview', '--session', sid, '--repo', u.repo)
    assert {'kind': 'peer_coverage_missing', 'ref': 'D2'} in prev['known_gaps']


def test_export_peer_coverage_agrees_with_an_allowing_gate(tmp_path):
    u = U(tmp_path)
    sid = custom_flow(u, REQ)
    assert gate(u)['decision'] == 'allowed'
    prev = u.call('export', 'preview', '--session', sid, '--repo', u.repo)
    assert not [g for g in prev['known_gaps'] if g['kind'] == 'peer_coverage_missing']


# --- C2-4 and C2-5: handover reservations ---------------------------------------------------

def test_transfer_reservation_cannot_be_arbitrated(tmp_path):
    """Ported: a negative handover review opens a reservation that only a later transfer
    review resolves; an arbitration naming it is refused and the gate stays blocked."""
    u = U(tmp_path)
    holder = {}

    def tmap(u, sid, current):
        _, rv = transfer(u, sid, peer='dave', reviewer='bob', status='not_reproducible')
        holder['arb'] = _arb(u, sid, 'erin', [], rv['result']['reservations'], None,
                             evidence=['src/transforms.py'])
        return current

    custom_flow(u, REQ, transfer_map=tmap)
    assert code(holder['arb']) == 'evidence_invalid'
    assert all(r['status'] == 'open' for r in u.ext()['reservations'].values())
    assert gate(u)['decision'] == 'blocked'


def _start_answer(u, sid, peer):
    task = next(t['task_id'] for t in u.bank()['tasks'] if t['kind'] == 'transfer')
    tid = u.m('transfer', 'start', '--session', sid, '--peer', peer,
              '--task', task)['result']['transfer_id']
    u.m('transfer', 'submit', '--transfer', tid, '--response-file',
        u.file(f'p-{u.n}.txt', 'The imputer is in src/transforms.py.'), '--assistance-file',
        u.file(f'pa-{u.n}.json', ukit.ASSIST), '--evidence-file',
        u.file(f'pe-{u.n}.json', {'evidence_refs': ['src/transforms.py'],
                                  'difficulty_or_blockers': []}))
    return tid


def _treview(u, tid, status, resolves=(), expect=0):
    return u.m('transfer', 'review', '--transfer', tid, '--file', u.file(f'r-{u.n}.json', {
        'reviewer_declared_id': 'alice', 'declaration': SIM, 'simulated': True,
        'dimension_ids': ['D2'], 'status': status, 'rationale': 'Simulated.',
        'resolves_reservation_ids': list(resolves)}), expect=expect)


def test_an_earlier_parallel_transfer_does_not_resolve_a_handover_reservation(tmp_path):
    """Ported: two handover tasks started together; the one reviewed after the failure was
    started before it, so it cannot resolve the reservation; a transfer started after the
    failed review can."""
    u = U(tmp_path)
    holder = {}

    def tmap(u, sid, current):
        early = {p: _start_answer(u, sid, p) for p in ('carol2', 'dave')}
        res = _treview(u, early['dave'], 'not_reproducible')['result']['reservations']
        holder['early'] = _treview(u, early['carol2'], 'demonstrated', res, expect=2)
        late = _start_answer(u, sid, 'erin')
        holder['late'] = _treview(u, late, 'demonstrated', res)
        return {'D2': holder['late']['result']['decision_id']}

    custom_flow(u, REQ, transfer_map=tmap)
    assert code(holder['early']) == 'evidence_invalid'
    assert holder['late']['ok']
    assert gate(u)['decision'] == 'allowed', gate(u)['reasons']


def test_a_resolving_transfer_must_be_on_the_current_handover(tmp_path):
    u = U(tmp_path)
    holder = {}

    def tmap(u, sid, current):
        _, rv = transfer(u, sid, peer='dave', status='not_reproducible')
        res = rv['result']['reservations']
        late = _start_answer(u, sid, 'erin')
        u.m('handover', 'set', '--session', sid, '--file',
            u.file('ho2.json', dict(ukit.HANDOVER, limits=['A newer limit.'])))
        holder['late'] = _treview(u, late, 'demonstrated', res, expect=2)
        return current

    custom_flow(u, REQ, transfer_map=tmap)
    assert code(holder['late']) == 'evidence_invalid'


# --- C2-6: a concurrent handoff reserving before this one builds ----------------------------

def test_concurrent_handoff_reserving_before_the_first_builds(tmp_path, monkeypatch):
    """Ported: handoff A reserves; before A builds its pack, handoff B runs to completion
    (its own reservation and record only). Both publish."""
    u = U(tmp_path)
    custom_flow(u, REQ)
    real = ce.build
    state = {'inner': None}

    def racing(study_dir):
        if state['inner'] is None:
            state['inner'] = 'running'
            monkeypatch.setattr(ce, 'build', real)
            o = cli.run(['export', 'handoff', '--study', str(u.study), '--out',
                         str(tmp_path / 'B')])
            state['inner'] = (o.exit_code, o.payload.get('error', {}).get('code'))
            monkeypatch.setattr(ce, 'build', racing)
        return real(study_dir)

    monkeypatch.setattr(ce, 'build', racing)
    o = cli.run(['export', 'handoff', '--study', str(u.study), '--out', str(tmp_path / 'A')])
    assert state['inner'][0] in (0, 3), state
    assert o.exit_code in (0, 3), o.payload
    ms = list(u.ext()['milestones'].values())
    assert sorted(m['status'] for m in ms) == ['published', 'published']


def test_a_relevant_write_before_the_build_still_refuses(tmp_path, monkeypatch):
    """Control: a write other than milestone bookkeeping between the reservation and the
    build is still a refusal (context_changed), never a published handoff."""
    u = U(tmp_path)
    sid = custom_flow(u, REQ)
    real = ce.build
    done = []

    def racing(study_dir):
        if not done:
            done.append(1)
            ukit.approve_all(u, sid)
        return real(study_dir)

    monkeypatch.setattr(ce, 'build', racing)
    o = cli.run(['export', 'handoff', '--study', str(u.study), '--out', str(tmp_path / 'A')])
    assert o.payload.get('error', {}).get('code') == 'context_changed', o.payload
    assert all(m['status'] != 'reserved' for m in u.ext()['milestones'].values())


# --- C2-7: the peer's declared assistance ---------------------------------------------------

def _assisted_peer_map(u, sid, current):
    task = next(t['task_id'] for t in u.bank()['tasks'] if t['kind'] == 'transfer')
    tid = u.m('transfer', 'start', '--session', sid, '--peer', 'carol',
              '--task', task)['result']['transfer_id']
    u.m('transfer', 'submit', '--transfer', tid, '--response-file',
        u.file('pp.txt', 'An assistant located the imputer for me.'),
        '--assistance-file', u.file('ppa.json', dict(
            ukit.ASSIST, ai_assistance_declared=True, independence_claim=None,
            resources_used=['chat assistant'])),
        '--evidence-file', u.file('ppe.json', {'evidence_refs': ['src/transforms.py'],
                                               'difficulty_or_blockers': []}))
    rv = _treview(u, tid, 'demonstrated')
    return {'D2': rv['result']['decision_id']}


def test_an_ai_assisted_handover_does_not_cover_an_unaided_required_dimension(tmp_path):
    """Ported (integrator default awaiting the owner): D2 is critical and the policy
    requires unaided work there; the peer declared AI assistance, so the transfer does not
    count toward D2's peer coverage, and the export says the same."""
    u = U(tmp_path)
    sid = custom_flow(u, REQ, peer=False, transfer_map=_assisted_peer_map)
    g = gate(u)
    assert g['decision'] == 'blocked'
    assert {'code': 'peer_coverage_missing', 'dimension': 'D2',
            'detail': 'peer_assistance_not_admissible'} in g['reasons']
    assert g['dimensions']['D2']['peer']['problems'] == ['peer_assistance_not_admissible']
    prev = u.call('export', 'preview', '--session', sid, '--repo', u.repo)
    assert {'kind': 'peer_coverage_missing', 'ref': 'D2'} in prev['known_gaps']


def test_an_ai_assisted_handover_counts_when_assistance_is_allowed(tmp_path):
    u = U(tmp_path)
    pol = ukit.policy(mode='required',
                      assistance_rule={'critical': 'aided_allowed', 'other': 'aided_allowed'})
    custom_flow(u, pol, peer=False, transfer_map=_assisted_peer_map)
    g = gate(u)
    assert g['decision'] == 'allowed', g['reasons']
    assert g['dimensions']['D2']['peer']['people'] == 2
