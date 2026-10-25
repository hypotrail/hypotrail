"""Round 3 of the understanding review, area C (R3C-1 to R3C-6): regression tests.

Every human here is a simulated declaration (``ukit.SIM``, ``simulated: true``); every study
and repository lives in a temporary directory. The reviewer's reproducing tests of round 3
are ported (their names keep the reviewer's wording) and completed with the expected
outcome of each fix.
"""
from __future__ import annotations

import json
import shutil
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import advkit  # noqa: E402,F401
from advkit import U, ukit, gate, custom_flow, code, SIM  # noqa: E402
from mlkit.study import cli, cmd_export as ce  # noqa: E402
from mlkit.study.store import BLOBS_DIR, StudyStore  # noqa: E402
from mlkit.study.understanding import canonical, export as ex, render  # noqa: E402
from mlkit.study.understanding import service as sv  # noqa: E402

REQ = ukit.policy(mode='required')      # D2, D3 critical; unaided_required on critical
STRICT = ukit.policy(mode='required', version=3)
RELAXED = ukit.policy(mode='required', version=2, critical_dimensions=['D2'])
AIDED = dict(ukit.ASSIST, ai_assistance_declared=True, independence_claim=None,
             resources_used=['chat assistant'])


def _arb(u, sid, arbiter, ids, res, chosen, evidence=('src/pipeline.py',), expect=None):
    return u.m('arbitrate', '--session', sid, '--file', u.file(f'arb-{u.n}.json', {
        'arbiter_declared_id': arbiter, 'declaration': SIM, 'simulated': True,
        'conflicting_decision_ids': ids, 'reservation_ids': res, 'chosen_decision_id': chosen,
        'rationale': 'Simulated arbitration.', 'evidence_refs': list(evidence)}), expect=expect)


def _verify(u, policy_doc=None, study=True):
    args = ['understanding', 'verify-export', '--repo', str(u.repo), '--target', 'worktree']
    if policy_doc is not None:
        args += ['--policy-file', str(u.file(f'vpol-{u.n}.json', policy_doc))]
    if study:
        args += ['--study', str(u.study)]
    return cli.run(args).payload


def _projection(u, sid):
    state = u.state()
    return ex.projection(sv.open_store(u.study), state, state['understanding']['sessions'][sid])


# --- R3C-1: every arbitration the gate relies on, in any session, is re-checked -----------

def _negative_d3_session(u, policy_doc):
    u.set_policy(policy_doc)
    plan, out = u.start()
    s1 = out['result']['session_id']
    t3 = next(t for t in plan['plan']['task_ids'] if u.bank_task(t)['dimension_ids'][0] == 'D3')
    a = u.submit(s1, t3)['result']['attempt_id']
    bad = u.review(s1, [u.decision('D3', [a], status='to_consolidate')],
                   reviewer='bob')['result']['decisions'][0]
    res = [r for r, x in u.ext()['reservations'].items() if x['decision_id'] == bad['decision_id']]
    return s1, res


def test_control_without_arbitration_the_old_reservation_blocks(tmp_path):
    """Ported control: an open reservation of an abandoned session still counts."""
    u = U(tmp_path)
    s1, res = _negative_d3_session(u, RELAXED)
    u.m('close', '--session', s1, '--to', 'abandoned', '--reason', 'restart')
    custom_flow(u, STRICT)
    g = gate(u)
    assert g['decision'] == 'blocked'
    assert {'code': 'open_reservation', 'dimension': 'D3', 'detail': res[0]} in g['reasons']


def test_author_self_arbitration_of_a_critical_reservation_in_an_unused_session(tmp_path):
    """Ported (C-M3 through a second session): under a relaxed policy (D3 not critical) the
    author settles the negative review of D3 herself; the team restores the strict policy and
    alice is reviewed again in session 2. The gate counts the reservations of every session,
    so it relies on that arbitration: re-checked under the current policy, it is not
    admissible, settles nothing, and the reservation counts again. A new admissible
    arbitration settles it, and the old one, which nothing relies on any more, no longer
    blocks."""
    u = U(tmp_path)
    s1, res = _negative_d3_session(u, RELAXED)
    assert _arb(u, s1, 'alice', [], res, None)['ok']          # admissible under RELAXED
    u.m('close', '--session', s1, '--to', 'completed', '--reason', 'done under v2')
    custom_flow(u, STRICT)
    g = gate(u)
    assert g['decision'] != 'allowed', 'self-arbitration of a critical reservation accepted'
    assert {'code': 'open_reservation', 'dimension': 'D3', 'detail': res[0]} in g['reasons']
    assert {'code': 'arbitration_not_admissible', 'dimension': 'D3'} in g['reasons']
    assert 'D3' in g['missing_dimensions']
    # The history still records the arbitration as it was made.
    assert u.ext()['reservations'][res[0]]['status'] == 'resolved'
    # The same arbitration made now is refused; another declared person settles it again.
    refused = _arb(u, s1, 'alice', [], res, None, expect=2)
    assert code(refused) == 'review_required'
    first = u.ext()['reservations'][res[0]]['resolved_by']
    again = _arb(u, s1, 'erin', [], res, None)
    assert again['ok'], again
    r = u.ext()['reservations'][res[0]]
    assert r['resolved_by'] == again['result']['arbitration_id']
    assert [p['resolved_by'] for p in r['previous_resolutions']] == [first]
    g = gate(u)
    assert g['decision'] == 'allowed', g['reasons']


def test_a_reservation_settled_by_a_non_admissible_arbitration_can_be_resolved_anew(tmp_path):
    """The other way out: a demonstrated decision on a new variant, in the new session,
    resolves the reservation the non-admissible arbitration claimed to settle (`submit`
    accepts that variant, outside the plan, because the reservation counts again). Then
    nothing relies on the old arbitration, which never blocks (C2-2's property)."""
    u = U(tmp_path)
    s1, res = _negative_d3_session(u, RELAXED)
    assert _arb(u, s1, 'alice', [], res, None)['ok']
    u.m('close', '--session', s1, '--to', 'abandoned', '--reason', 'restart under v3')
    held = {}

    def attempts_for(u, sid, dim, tid):
        if dim != 'D3':
            return None
        variant = u.task_for('D3', 'b')
        assert variant not in u.ext()['sessions'][sid]['task_ids']   # for the reservation
        a = u.submit(sid, variant, 'My own answer to the new variant.')['result']['attempt_id']
        held['resolve'] = u.review(sid, [u.decision('D3', [a], evidence_refs=['src/pipeline.py'],
                                                    resolves_reservation_ids=res)],
                                   reviewer='bob')
        return [a]

    sid = custom_flow(u, STRICT, attempts_for=attempts_for)
    assert held['resolve']['ok']
    r = u.ext()['reservations'][res[0]]
    assert r['resolved_by'] in u.ext()['decisions']
    # The selection names session 2's own D3 decisions (two: the resolving one and the one
    # custom_flow records on the same attempt); select the resolving one explicitly.
    ext = u.ext()
    sel = max(ext['selections'].values(), key=lambda s: s['recorded_revision'])
    dm = dict(sel['dimension_decision_map'], D3=r['resolved_by'])
    u.m('select', '--file', u.file('sel-d3.json', {
        'milestone': 'handoff', 'actor_scope': sel['actor_scope'],
        'dimension_decision_map': dm, 'transfer_decision_map': sel['transfer_decision_map'],
        'reservation_resolution_refs': []}))
    g = gate(u)
    assert g['decision'] == 'allowed', g['reasons']
    assert sid


def test_an_arbitration_of_another_dimension_is_not_relied_on(tmp_path):
    """C2-2's property kept: an arbitration that settles nothing the gate counts (here a
    conflict of the analyst profile on D1, outside the pipeline selection) is never asked,
    even when the current policy no longer names its arbiter."""
    u = U(tmp_path)
    u.set_policy(REQ)
    plan, out = u.start(profile='analyst')
    s1 = out['result']['session_id']
    t1 = next(t for t in plan['plan']['task_ids'] if u.bank_task(t)['dimension_ids'][0] == 'D1')
    a = u.submit(s1, t1)['result']['attempt_id']
    good = u.review(s1, [u.decision('D1', [a])], reviewer='bob')['result']['decisions'][0]
    bad = u.review(s1, [u.decision('D1', [a], status='to_consolidate')],
                   reviewer='dave')['result']['decisions'][0]
    res = [r for r, x in u.ext()['reservations'].items() if x['decision_id'] == bad['decision_id']]
    assert _arb(u, s1, 'frank', [good['decision_id'], bad['decision_id']], res,
                good['decision_id'])['ok']
    u.m('close', '--session', s1, '--to', 'abandoned', '--reason', 'other profile')
    custom_flow(u, ukit.policy(mode='required', version=2, role_policy={'arbiters': ['erin']}))
    assert gate(u)['decision'] == 'allowed', gate(u)['reasons']


# --- R3C-2: the export shows the selected decisions; the verifier checks the map ------------

def _two_d3_decisions(u, sid, dim, tid, held):
    if dim != 'D3':
        return None
    a1 = u.submit(sid, tid, 'An assistant drafted this answer.', assist=AIDED)
    x = u.review(sid, [u.decision('D3', [a1['result']['attempt_id']],
                                  evidence_refs=['src/pipeline.py'])])
    held['X'] = x['result']['decisions'][0]['decision_id']
    a2 = u.submit(sid, tid, 'My own answer for D3, written alone.')
    return [a2['result']['attempt_id']]


def test_verify_export_allows_what_the_gate_blocks_on_the_selected_decision(tmp_path):
    """Ported: the selection names the aided D3 decision X while the latest D3 decision is
    unaided. check blocks (assistance_not_admissible); the export now shows X (its
    human_review_ref and assistance) and verify-export under the same policy blocks too."""
    u = U(tmp_path)
    held = {}
    sid = custom_flow(u, REQ, attempts_for=lambda *a: _two_d3_decisions(*a, held))
    assert gate(u)['decision'] == 'allowed'
    last = max(u.ext()['selections'].values(), key=lambda s: s['recorded_revision'])
    dm = dict(last['dimension_decision_map'], D3=held['X'])
    u.m('select', '--file', u.file('sel2.json', {
        'milestone': 'handoff', 'actor_scope': last['actor_scope'],
        'dimension_decision_map': dm, 'transfer_decision_map': last['transfer_decision_map'],
        'reservation_resolution_refs': []}))
    g = gate(u)
    assert g['decision'] == 'blocked'
    assert {'code': 'assistance_not_admissible', 'dimension': 'D3'} in g['reasons']
    ukit.approve_all(u, sid)
    w = u.m('export', 'write', '--session', sid, '--repo', u.repo)
    doc = json.loads((u.repo / ex.EXPORT_DIR / w['review_id'] / ex.JSON_FILE).read_text())
    d3 = next(d for d in doc['dimensions'] if d['id'] == 'D3')
    assert d3['human_review_ref'] == held['X'] == doc['coverage_selection'][
        'dimension_decision_map']['D3']
    assert d3['assistance_summary'] == 'aided'
    gen = _verify(u, REQ)['generations'][0]
    assert gen['public_integrity'] == 'valid', gen['problems']
    assert gen['gate_result']['decision'] != 'allowed', \
        'verify-export allows under the policy what check blocks for the same selection'
    assert {'code': 'assistance_not_admissible', 'dimension': 'D3'} in \
        gen['gate_result']['reasons']
    # The report section shows the same decision (aided), not the latest one.
    html = render.section(u.study, u.state())
    row = html[html.find('<code data-literal="identifier">D3</code>'):]
    row = row[:row.find('</tr>')]
    assert '<td>aided</td>' in row, row


def test_without_a_selection_for_the_profile_the_export_claims_none(tmp_path):
    """The latest selection is about another profile: the export keeps the history-based
    dimensions and claims no coverage_selection (it used to publish that selection)."""
    u = U(tmp_path)
    sid = custom_flow(u, REQ)
    u.m('select', '--file', u.file('sel-analyst.json', {
        'milestone': 'handoff', 'actor_scope': {'actor_declared_id': 'alice',
                                                'profile': 'analyst'},
        'dimension_decision_map': {}, 'transfer_decision_map': {},
        'reservation_resolution_refs': []}))
    proj = _projection(u, sid)
    assert proj['coverage_selection'] is None
    assert all(d['human_review_ref'] for d in proj['dimensions'])
    other = U(tmp_path / 'none')
    sid2 = custom_flow(other, REQ, select=False)
    assert _projection(other, sid2)['coverage_selection'] is None


def _rewrite_generation(u, rid, change):
    """Re-publish generation ``rid`` after ``change(doc)``, with every derived field
    recomputed as a forger would (review id, approvals, Markdown, manifest, folder)."""
    base = u.repo / ex.EXPORT_DIR
    doc = json.loads((base / rid / ex.JSON_FILE).read_text())
    shutil.rmtree(base / rid)
    change(doc)
    proj = ex.approval_projection(doc)
    doc['review_id'] = ex.review_id(proj)
    digest = canonical.digest(proj)
    for a in doc['privacy_review']['approvals']:
        a['content_digest'] = digest
    out = base / doc['review_id']
    out.mkdir()
    for name, data in ex.files_of(doc).items():
        (out / name).write_bytes(data)
    return doc['review_id']


def test_verifier_refuses_a_dimension_that_is_not_the_selected_decision(tmp_path):
    """A document whose D3 shows another review than the one its coverage_selection maps
    contradicts itself: public_integrity is invalid (the engine never produces it, and no
    conformity can be judged on it). The control rewrite without that change is valid, so
    the problem is the mismatch alone."""
    u = U(tmp_path)
    held = {}
    sid = custom_flow(u, REQ, attempts_for=lambda *a: _two_d3_decisions(*a, held))
    ukit.approve_all(u, sid)
    w = u.m('export', 'write', '--session', sid, '--repo', u.repo)
    rid = _rewrite_generation(u, w['review_id'], lambda doc: None)
    out = _verify(u, REQ, study=False)
    assert out['public_integrity'] == 'valid', out
    rid = _rewrite_generation(u, rid, lambda doc: next(
        d for d in doc['dimensions'] if d['id'] == 'D3').update(human_review_ref=held['X']))
    out = _verify(u, REQ, study=False)
    gen = out['generations'][0]
    assert gen['review_id'] == rid
    assert gen['public_integrity'] == 'invalid'
    assert 'dimension D3 human_review_ref differs from the coverage selection' in gen['problems']


# --- R3C-3: the report's peer gap follows team_coverage.minimum_people ---------------------

def test_report_shows_the_gate_peer_gap_when_people_are_too_few(tmp_path):
    """Ported: minimum_people 3 and one peer: check and the export report the D2 gap, and
    so does the report section now."""
    u = U(tmp_path)
    sid = custom_flow(u, ukit.policy(mode='required', team_coverage={'minimum_people': 3}))
    g = gate(u)
    assert g['decision'] == 'blocked'
    assert g['missing_peer_dimensions'] == ['D2'], g['reasons']
    prev = u.call('export', 'preview', '--session', sid, '--repo', u.repo)
    assert {'kind': 'peer_coverage_missing', 'ref': 'D2'} in prev['known_gaps']
    html = render.section(u.study, u.state())
    assert 'handover by a colleague' in html, 'report shows no D2 peer gap; gate blocks on it'
    assert 'two declared people, the policy asks for three' in html


def test_report_shows_no_peer_gap_when_the_gate_has_none(tmp_path):
    u = U(tmp_path)
    custom_flow(u, REQ)
    assert gate(u)['decision'] == 'allowed'
    assert 'handover by a colleague' not in render.section(u.study, u.state())


# --- R3C-4: a handover reservation under unaided_required -----------------------------------

def _start_answer(u, sid, peer, ai=False):
    task = next(t['task_id'] for t in u.bank()['tasks'] if t['kind'] == 'transfer')
    tid = u.m('transfer', 'start', '--session', sid, '--peer', peer,
              '--task', task)['result']['transfer_id']
    assist = AIDED if ai else ukit.ASSIST
    u.m('transfer', 'submit', '--transfer', tid, '--response-file',
        u.file(f'p-{u.n}.txt', 'The imputer is in src/transforms.py.'), '--assistance-file',
        u.file(f'pa-{u.n}.json', assist), '--evidence-file',
        u.file(f'pe-{u.n}.json', {'evidence_refs': ['src/transforms.py'],
                                  'difficulty_or_blockers': []}))
    return tid


def _treview(u, tid, status, resolves=(), expect=0):
    return u.m('transfer', 'review', '--transfer', tid, '--file', u.file(f'r-{u.n}.json', {
        'reviewer_declared_id': 'alice', 'declaration': SIM, 'simulated': True,
        'dimension_ids': ['D2'], 'status': status, 'rationale': 'Simulated.',
        'resolves_reservation_ids': list(resolves)}), expect=expect)


def test_ai_assisted_handover_resolves_a_reservation_on_an_unaided_required_dimension(tmp_path):
    """Ported: the failed handover of D2 (critical, unaided_required) opens a reservation; a
    later handover whose peer declared AI assistance is refused as its resolution
    (evidence_invalid, nothing recorded), the reservation stays open and the gate blocks; an
    unaided later handover resolves it."""
    u = U(tmp_path)
    holder = {}

    def tmap(u, sid, current):
        failed = _start_answer(u, sid, 'dave')
        holder['res'] = _treview(u, failed, 'not_reproducible')['result']['reservations']
        aided = _start_answer(u, sid, 'erin', ai=True)
        rev = u.rev()
        holder['aided'] = _treview(u, aided, 'demonstrated', resolves=holder['res'],
                                   expect=None)
        holder['unchanged'] = u.rev() == rev
        return current

    custom_flow(u, REQ, transfer_map=tmap)
    assert not holder['aided']['ok'], holder['aided']
    assert code(holder['aided']) == 'evidence_invalid'
    assert holder['aided']['error']['details']['reservation_id'] == holder['res'][0]
    assert holder['unchanged']
    assert u.ext()['reservations'][holder['res'][0]]['status'] == 'open'
    g = gate(u)
    assert g['decision'] != 'allowed', \
        'an AI-assisted handover settled the reservation of an unaided_required dimension'
    assert {'code': 'open_reservation', 'dimension': 'D2', 'detail': holder['res'][0]} \
        in g['reasons']


def test_an_unaided_handover_still_resolves_the_reservation(tmp_path):
    u = U(tmp_path)
    holder = {}

    def tmap(u, sid, current):
        failed = _start_answer(u, sid, 'dave')
        res = _treview(u, failed, 'not_reproducible')['result']['reservations']
        late = _start_answer(u, sid, 'erin')
        holder['late'] = _treview(u, late, 'demonstrated', resolves=res)
        return {'D2': holder['late']['result']['decision_id']}

    custom_flow(u, REQ, transfer_map=tmap)
    assert holder['late']['ok']
    assert gate(u)['decision'] == 'allowed', gate(u)['reasons']


def test_an_aided_resolution_under_a_looser_policy_does_not_settle_for_the_gate(tmp_path):
    """Recorded while the assistance rule allowed help, an AI-assisted handover resolves the
    reservation; under the unaided_required rule the gate applies now, that resolution does
    not settle the reservation (open_reservation, peer_assistance_not_admissible) until an
    unaided handover resolves it again."""
    u = U(tmp_path)
    loose = ukit.policy(mode='required', assistance_rule={'critical': 'aided_allowed',
                                                          'other': 'aided_allowed'})
    holder = {}

    def tmap(u, sid, current):
        failed = _start_answer(u, sid, 'dave')
        holder['res'] = _treview(u, failed, 'not_reproducible')['result']['reservations']
        aided = _start_answer(u, sid, 'erin', ai=True)
        assert _treview(u, aided, 'demonstrated', resolves=holder['res'])['ok']
        return current

    custom_flow(u, loose, transfer_map=tmap)
    assert gate(u)['decision'] == 'allowed', gate(u)['reasons']
    g = gate(u, '--policy-file', u.file('strict.json', REQ))
    rid = holder['res'][0]
    assert {'code': 'open_reservation', 'dimension': 'D2', 'detail': rid} in g['reasons']
    assert {'code': 'peer_assistance_not_admissible', 'dimension': 'D2', 'detail': rid} \
        in g['reasons']
    # Once the team applies that rule, an unaided handover (in a linked session) resolves the
    # reservation again; the replaced resolution stays in the history.
    u.set_policy(REQ)
    _, out = u.start()
    late = _start_answer(u, out['result']['session_id'], 'frank')
    again = _treview(u, late, 'demonstrated', resolves=[rid])
    r = u.ext()['reservations'][rid]
    assert r['resolved_by'] == again['result']['decision_id']
    assert len(r['previous_resolutions']) == 1
    g = gate(u)
    assert {'code': 'peer_assistance_not_admissible', 'dimension': 'D2', 'detail': rid} \
        not in g['reasons']
    assert {'code': 'open_reservation', 'dimension': 'D2', 'detail': rid} not in g['reasons']


# --- R3C-5: concurrent handoffs on the default target --------------------------------------

def _race(u, monkeypatch, argv_for):
    real = ce.build
    barrier = threading.Barrier(2, timeout=60)

    def build(study_dir):
        barrier.wait()
        return real(study_dir)

    monkeypatch.setattr(ce, 'build', build)
    out = {}

    def run(name):
        o = cli.run(argv_for(name))
        out[name] = (o.exit_code, (o.payload.get('error') or {}).get('code'),
                     o.payload.get('out'))

    threads = [threading.Thread(target=run, args=(n,)) for n in 'AB']
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return out


def test_two_concurrent_default_target_handoffs_both_publish(tmp_path, monkeypatch):
    """Ported: both reserve, then both build at the same revision (only bookkeeping in
    between) and target handoff/revision-N. CLI-CONTRACT §16: concurrent handoffs each
    publish; the second one takes handoff/revision-N-<its reservation>."""
    u = U(tmp_path)
    custom_flow(u, REQ)
    out = _race(u, monkeypatch, lambda n: ['export', 'handoff', '--study', str(u.study)])
    assert all(v[0] in (0, 3) for v in out.values()), out
    ms = list(u.ext()['milestones'].values())
    assert sorted(m['status'] for m in ms) == ['published', 'published']
    folders = sorted(Path(v[2]) for v in out.values())
    assert len(set(folders)) == 2
    names = sorted(f.name for f in folders)
    default = next(n for n in names if '-' not in n.removeprefix('revision-'))
    other = next(n for n in names if n != default)
    assert other.startswith(default + '-')
    assert any(other.endswith(m['reservation_id'].split('-', 1)[1][:8]) for m in ms)
    for f in folders:
        assert f.parent == u.study / ce.DEFAULT_PARENT
        assert (f / 'handoff.json').exists()


def test_concurrent_handoffs_on_the_same_out_never_replace(tmp_path, monkeypatch):
    """--out keeps its meaning: one folder, never a replacement; the second handoff does not
    publish elsewhere."""
    u = U(tmp_path)
    custom_flow(u, REQ)
    target = tmp_path / 'pack'
    out = _race(u, monkeypatch, lambda n: ['export', 'handoff', '--study', str(u.study),
                                           '--out', str(target)])
    ok = [v for v in out.values() if v[0] in (0, 3)]
    assert len(ok) == 1, out
    assert ok[0][2] == str(target)
    assert sorted(m['status'] for m in u.ext()['milestones'].values()) == \
        ['candidate_not_current', 'published']
    assert not list((u.study / ce.DEFAULT_PARENT).glob('revision-*'))


# --- R3C-6: payloads_available and the peer's answer ---------------------------------------

def _drop_peer_answer(u):
    t = next(iter(u.ext()['transfers'].values()))
    (StudyStore(u.study).home / BLOBS_DIR / t['response_ref']).unlink()


def test_peer_answer_removed_still_counts_as_coverage(tmp_path):
    """Ported: under payloads_available, a selected transfer whose peer answer is gone does
    not count (evidence_unavailable); the export reports the gap and local verification says
    the evidence is unavailable."""
    u = U(tmp_path)
    sid = custom_flow(u, REQ)
    assert gate(u)['decision'] == 'allowed'
    ukit.approve_all(u, sid)
    u.m('export', 'write', '--session', sid, '--repo', u.repo)
    _drop_peer_answer(u)
    g = gate(u)
    assert g['decision'] != 'allowed', 'peer answer gone, payloads_available, still allowed'
    assert {'code': 'peer_coverage_missing', 'dimension': 'D2',
            'detail': 'evidence_unavailable'} in g['reasons']
    assert g['dimensions']['D2']['peer']['problems'] == ['evidence_unavailable']
    prev = u.call('export', 'preview', '--session', sid, '--repo', u.repo)
    assert {'kind': 'peer_coverage_missing', 'ref': 'D2'} in prev['known_gaps']
    gen = _verify(u)['generations'][0]
    assert gen['evidence_availability'] == 'unavailable'


def test_peer_answer_removed_under_recorded_decisions_is_a_limitation(tmp_path):
    """A28 kept: under recorded_decisions the judgement stands; the coverage counts and the
    gate says the evidence is not re-auditable."""
    u = U(tmp_path)
    custom_flow(u, ukit.policy(mode='required', evidence_requirement='recorded_decisions'))
    _drop_peer_answer(u)
    g = gate(u)
    assert g['decision'] == 'allowed', g['reasons']
    assert g['dimensions']['D2']['peer']['evidence_availability'] == 'unavailable'
    assert 'evidence_not_reauditable' in g['limitations']
