"""Round 4 of the understanding review, area C (C4-1 to C4-6): regression tests.

Every human here is a simulated declaration (``ukit.SIM``, ``simulated: true``); every study
and repository lives in a temporary directory. The reviewer's reproducing tests of round 4
are ported (their names keep the reviewer's wording where they still describe the scenario)
and completed with the expected outcome of each fix.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import advkit  # noqa: E402,F401
from advkit import U, ukit, gate, custom_flow, code, SIM  # noqa: E402
from mlkit.study import cli  # noqa: E402
from mlkit.study.store import BLOBS_DIR, StudyStore  # noqa: E402
from mlkit.study.understanding import canonical, export as ex, render  # noqa: E402
from mlkit.study.understanding import verify as vf  # noqa: E402

REQ = ukit.policy(mode='required')      # D2, D3 critical; unaided_required on critical only
STRICT_OTHER = ukit.policy(mode='required', version=2,
                           assistance_rule={'critical': 'unaided_required',
                                            'other': 'unaided_required'})
AIDED = dict(ukit.ASSIST, ai_assistance_declared=True, independence_claim=None,
             resources_used=['chat assistant'])
FIXTURE = Path(__file__).resolve().parents[2] / 'fixtures' / 'understanding' / 'export-valid'


def _verify(u, policy_doc=None, study=True):
    args = ['understanding', 'verify-export', '--repo', str(u.repo), '--target', 'worktree']
    if policy_doc is not None:
        args += ['--policy-file', str(u.file(f'vpol-{u.n}.json', policy_doc))]
    if study:
        args += ['--study', str(u.study)]
    return cli.run(args).payload


def _reselect(u, **dm):
    last = max(u.ext()['selections'].values(), key=lambda s: s['recorded_revision'])
    m = dict(last['dimension_decision_map'], **dm)
    return u.m('select', '--file', u.file(f'sel-{u.n}.json', {
        'milestone': 'handoff', 'actor_scope': last['actor_scope'],
        'dimension_decision_map': m, 'transfer_decision_map': last['transfer_decision_map'],
        'reservation_resolution_refs': []}))


def _arb(u, sid, arbiter, ids, res, chosen, expect=None):
    return u.m('arbitrate', '--session', sid, '--file', u.file(f'arb-{u.n}.json', {
        'arbiter_declared_id': arbiter, 'declaration': SIM, 'simulated': True,
        'conflicting_decision_ids': ids, 'reservation_ids': res, 'chosen_decision_id': chosen,
        'rationale': 'Simulated arbitration.', 'evidence_refs': ['src/pipeline.py']}),
        expect=expect)


def _decision_of(u, attempt_id) -> str:
    return next(d['decision_id'] for d in u.ext()['decisions'].values()
                if d['kind'] == 'attempt' and d['attempt_ids'] == [attempt_id])


def _written(u, sid) -> dict:
    ukit.approve_all(u, sid)
    w = u.m('export', 'write', '--session', sid, '--repo', u.repo)
    return json.loads((u.repo / ex.EXPORT_DIR / w['review_id'] / ex.JSON_FILE).read_text())


def _negative_then_resolution(u, dim, resolve_assist, held):
    """``attempts_for`` of custom_flow: on ``dim``, an unaided answer a1 (the one the
    selection will map), a second one a2 reviewed to_consolidate by dave (a reservation),
    and an answer a3 to variant b given with ``resolve_assist``, reviewed demonstrated by bob
    and naming the reservation."""
    def attempts_for(u, sid, d, tid):
        if d != dim:
            return None
        a1 = u.submit(sid, tid, f'My own answer for {dim}.')['result']['attempt_id']
        a2 = u.submit(sid, tid, 'My own second answer.')['result']['attempt_id']
        neg = u.review(sid, [u.decision(dim, [a2], status='to_consolidate')],
                       reviewer='dave')['result']['decisions'][0]['decision_id']
        held['res'] = [r for r, x in u.ext()['reservations'].items()
                       if x['decision_id'] == neg]
        a3 = u.submit(sid, u.task_for(dim, 'b'), 'An answer to the new variant.',
                      assist=resolve_assist)['result']['attempt_id']
        held['resolve'] = u.review(sid, [u.decision(dim, [a3], evidence_refs=['src/pipeline.py'],
                                                    resolves_reservation_ids=held['res'])],
                                   reviewer='bob', expect=None)
        held['a1'], held['a3'] = a1, a3
        return [a1]
    return attempts_for


# --- C4-1: a reservation is resolved only with admissible help -----------------------------

def test_aided_attempt_does_not_resolve_an_unaided_required_reservation(tmp_path):
    """Ported (reviewer: "aided attempt resolves an unaided_required reservation"). D3 is
    critical and unaided_required. Expectation changed from the probe, which recorded the
    resolution: an AI-assisted demonstration naming the reservation is now refused at record
    time (evidence_invalid), so the reservation stays open and the gate blocks."""
    u = U(tmp_path)
    held = {}
    custom_flow(u, REQ, attempts_for=_negative_then_resolution(u, 'D3', AIDED, held))
    assert not held['resolve']['ok'] and code(held['resolve']) == 'evidence_invalid'
    assert held['resolve']['error']['details']['reservation_id'] == held['res'][0]
    rid = held['res'][0]
    assert u.ext()['reservations'][rid]['status'] == 'open'
    _reselect(u, D3=_decision_of(u, held['a1']))
    g = gate(u)
    assert g['decision'] == 'blocked'
    assert {'code': 'open_reservation', 'dimension': 'D3', 'detail': rid} in g['reasons']


def test_an_unaided_new_variant_still_resolves_the_reservation(tmp_path):
    """Control: the same flow with an unaided answer to the new variant resolves it."""
    u = U(tmp_path)
    held = {}
    custom_flow(u, REQ, attempts_for=_negative_then_resolution(u, 'D3', None, held))
    assert held['resolve']['ok']
    _reselect(u, D3=_decision_of(u, held['a1']))
    assert gate(u)['decision'] == 'allowed', gate(u)['reasons']


def test_rectified_resolving_attempt_reopens_the_reservation(tmp_path):
    """Ported (reviewer: "rectified resolving attempt keeps the reservation closed"): the
    resolving attempt is declared AI-assisted afterwards; the gate re-checks the resolution
    with the help known now, so the reservation counts again (open_reservation and
    assistance_not_admissible, detail the reservation)."""
    u = U(tmp_path)
    held = {}
    custom_flow(u, REQ, attempts_for=_negative_then_resolution(u, 'D3', None, held))
    assert held['resolve']['ok']
    _reselect(u, D3=_decision_of(u, held['a1']))
    assert gate(u)['decision'] == 'allowed'
    u.m('rectify', '--attempt', held['a3'], '--assistance-file', u.file('rect.json', AIDED))
    g = gate(u)
    rid = held['res'][0]
    assert g['decision'] == 'blocked'
    assert {'code': 'open_reservation', 'dimension': 'D3', 'detail': rid} in g['reasons']
    assert {'code': 'assistance_not_admissible', 'dimension': 'D3', 'detail': rid} \
        in g['reasons']


def test_an_aided_resolution_under_a_looser_rule_is_rechecked_and_can_be_resolved_anew(
        tmp_path):
    """D5 is aided_allowed under REQ: an AI-assisted resolution is recorded. Under a policy
    making D5 unaided_required, the gate does not count that resolution (the stricter of the
    applied and the session policies). Once the team applies that rule, the reservation is
    open again for the engine: a new variant may be asked and an unaided demonstration on it
    resolves the reservation again (the replaced resolution stays in the history)."""
    u = U(tmp_path)
    held = {}
    custom_flow(u, REQ, attempts_for=_negative_then_resolution(u, 'D5', AIDED, held))
    assert held['resolve']['ok']
    _reselect(u, D5=_decision_of(u, held['a1']))
    assert gate(u)['decision'] == 'allowed', gate(u)['reasons']
    rid = held['res'][0]
    g = gate(u, '--policy-file', u.file('strict.json', STRICT_OTHER))
    assert {'code': 'open_reservation', 'dimension': 'D5', 'detail': rid} in g['reasons']
    assert {'code': 'assistance_not_admissible', 'dimension': 'D5', 'detail': rid} \
        in g['reasons']
    u.set_policy(STRICT_OTHER)
    _, out = u.start()
    s2 = out['result']['session_id']
    # Variant b is not in the new session's plan: it is admitted as the new variant of a
    # reservation that still counts.
    a4 = u.submit(s2, u.task_for('D5', 'b'), 'Alone this time.')['result']['attempt_id']
    again = u.review(s2, [u.decision('D5', [a4], evidence_refs=['src/pipeline.py'],
                                     resolves_reservation_ids=[rid])], reviewer='bob')
    r = u.ext()['reservations'][rid]
    assert r['resolved_by'] == again['result']['decisions'][0]['decision_id']
    assert len(r['previous_resolutions']) == 1
    reasons = gate(u)['reasons']
    assert {'code': 'open_reservation', 'dimension': 'D5', 'detail': rid} not in reasons
    assert {'code': 'assistance_not_admissible', 'dimension': 'D5', 'detail': rid} \
        not in reasons


# --- C4-2: the export and the report fold in the gate's problems of a selected decision -----

def test_superseded_selected_decision_export_report_and_verify_agree_with_check(tmp_path):
    """Ported (reviewer: "superseded selected decision: export and verify disagree with
    check"). bob replaces his D5 decision in a linked session; the selection still maps the
    replaced one. The gate blocks (decision_superseded); the export shows D5 as needs_review
    with a gap of that code, the report lists the gap, and verify-export with the same policy
    blocks."""
    u = U(tmp_path)
    sid = custom_flow(u, REQ)
    assert gate(u)['decision'] == 'allowed'
    sel = max(u.ext()['selections'].values(), key=lambda s: s['recorded_revision'])
    old = sel['dimension_decision_map']['D5']
    _, out = u.start()
    s2 = out['result']['session_id']
    a2 = u.submit(s2, u.task_for('D5', 'a'), 'Another answer for D5.')['result']['attempt_id']
    assert u.review(s2, [u.decision('D5', [a2], supersedes_ids=[old],
                                    evidence_refs=['src/pipeline.py'])], reviewer='bob')['ok']
    g = gate(u)
    assert g['decision'] == 'blocked'
    assert {'code': 'decision_superseded', 'dimension': 'D5'} in g['reasons']
    prev = u.call('export', 'preview', '--session', sid, '--repo', u.repo)
    assert {'kind': 'decision_superseded', 'ref': 'D5'} in prev['known_gaps']
    assert {'kind': 'dimension_not_demonstrated', 'ref': 'D5'} in prev['known_gaps']
    doc = _written(u, sid)
    d5 = next(d for d in doc['dimensions'] if d['id'] == 'D5')
    assert d5['status'] == 'needs_review' and d5['human_review_ref'] == old
    assert ex.validate_review(doc) == []
    gen = _verify(u, REQ)['generations'][0]
    assert gen['public_integrity'] == 'valid'
    assert gen['gate_result']['decision'] == 'blocked'
    assert {'code': 'dimension_not_demonstrated', 'dimension': 'D5'} \
        in gen['gate_result']['reasons']
    html = render.section(u.study, u.state())
    gaps = html[html.find('<h3>Gaps'):]
    assert 'D5</code>' in gaps and 'decision_superseded</code>' in gaps


def test_an_unproblematic_selection_still_exports_demonstrated(tmp_path):
    """Control: without a gate problem the selected dimensions stay demonstrated."""
    u = U(tmp_path)
    sid = custom_flow(u, REQ)
    doc = _written(u, sid)
    assert all(d['status'] == 'demonstrated' for d in doc['dimensions'])
    assert _verify(u, REQ)['generations'][0]['gate_result']['decision'] == 'allowed'


def _edit_d5_rubric(u):
    f = u.case_dir / 'understanding.yaml'
    old = 'Explains how the same fitted transformation is applied at prediction time.'
    text = f.read_text()
    assert old in text
    f.write_text(text.replace(old, 'Explains how the fitted transformation is reused at '
                              'prediction time, and why.'))


def test_rubric_edited_after_review_export_and_verify_block(tmp_path):
    """Ported (reviewer: "rubric edited after review: export and verify allow")."""
    u = U(tmp_path)
    sid = custom_flow(u, REQ)
    _edit_d5_rubric(u)
    g = gate(u)
    assert g['decision'] == 'blocked'
    assert {'code': 'rubric_changed', 'dimension': 'D5'} in g['reasons']
    doc = _written(u, sid)
    d5 = next(d for d in doc['dimensions'] if d['id'] == 'D5')
    assert d5['status'] == 'needs_review'
    assert {'kind': 'rubric_changed', 'ref': 'D5'} in doc['known_gaps']
    assert {'kind': 'taskset_changed', 'ref': 'D5'} in doc['known_gaps']
    assert _verify(u, REQ)['generations'][0]['gate_result']['decision'] == 'blocked'


def test_rubric_edited_after_review_public_only(tmp_path):
    """Ported: the same under context_requirement public_only (no private-context reason
    hides the result)."""
    pol = ukit.policy(mode='required', context_requirement='public_only')
    u = U(tmp_path)
    sid = custom_flow(u, pol)
    assert gate(u)['decision'] == 'allowed'
    _edit_d5_rubric(u)
    assert gate(u)['decision'] == 'blocked'
    _written(u, sid)
    gen = _verify(u, pol)['generations'][0]
    assert gen['public_integrity'] == 'valid'
    assert gen['gate_result']['decision'] == 'blocked'
    assert {'code': 'dimension_not_demonstrated', 'dimension': 'D5'} \
        in gen['gate_result']['reasons']


# --- C4-3: verify-export applies the taskset qualification rule ------------------------------

def test_unqualified_taskset_export_does_not_verify_as_conforming(tmp_path):
    """Ported (reviewer: "unqualified taskset export verifies as conforming")."""
    u = U(tmp_path)
    f = u.case_dir / 'understanding.yaml'
    f.write_text(f.read_text().replace('  status: reviewed', '  status: to_qualify', 1))
    sid = custom_flow(u, REQ)
    g = gate(u)
    assert g['decision'] == 'blocked'
    assert 'taskset_not_qualified' in {r['code'] for r in g['reasons']}
    doc = _written(u, sid)
    assert doc['provenance']['taskset_qualification'] == 'to_qualify'
    gen = _verify(u, REQ)['generations'][0]
    assert gen['gate_result']['decision'] == 'blocked'
    assert {'code': 'taskset_not_qualified'} in gen['gate_result']['reasons']
    assert _verify(u, None)['generations'][0]['declared_conformity'] == 'nonconforming'


def _fixture_doc() -> dict:
    return canonical.loads((FIXTURE / ex.JSON_FILE).read_bytes())


AXES = {'public_integrity': 'valid', 'public_source_freshness': 'current',
        'private_context_verification': 'verified', 'evidence_availability': 'available'}


def test_gate_on_export_reads_the_qualification_and_its_limitation():
    """On the committed export: no taskset reason as published; one when the provenance
    says to_qualify, and one when only the limitation says it."""
    doc = _fixture_doc()
    policy = doc['policy']
    assert {'code': 'taskset_not_qualified'} not in vf._gate_on_export(doc, policy, AXES)[
        'reasons']
    d = copy.deepcopy(doc)
    d['provenance']['taskset_qualification'] = 'to_qualify'
    assert {'code': 'taskset_not_qualified'} in vf._gate_on_export(d, policy, AXES)['reasons']
    d = copy.deepcopy(doc)
    d['limitations'] = sorted(d['limitations'] + ['taskset_not_qualified'])
    assert {'code': 'taskset_not_qualified'} in vf._gate_on_export(d, policy, AXES)['reasons']


# --- C4-4: superseding uses the gate's view of the conflicts ----------------------------------

def test_supersede_in_a_conflict_reopened_by_a_stale_arbitration_is_refused(tmp_path):
    """Ported (reviewer: "supersede in a conflict reopened by a stale arbitration"). D5:
    bob demonstrated, dave to_consolidate on the same attempt; frank (any_declared then)
    arbitrates. The team then names erin as the only arbiter, so the gate counts the conflict
    again. dave can no longer leave it by superseding his own decision: review_required."""
    u = U(tmp_path)
    u.set_policy(REQ)
    plan, out = u.start()
    s1 = out['result']['session_id']
    t5 = next(t for t in plan['plan']['task_ids'] if u.bank_task(t)['dimension_ids'][0] == 'D5')
    a = u.submit(s1, t5)['result']['attempt_id']
    good = u.review(s1, [u.decision('D5', [a])], reviewer='bob')['result']['decisions'][0]
    bad = u.review(s1, [u.decision('D5', [a], status='to_consolidate')],
                   reviewer='dave')['result']['decisions'][0]
    res = [r for r, x in u.ext()['reservations'].items() if x['decision_id'] == bad['decision_id']]
    assert _arb(u, s1, 'frank', [good['decision_id'], bad['decision_id']], res,
                good['decision_id'])['ok']
    u.m('close', '--session', s1, '--to', 'completed', '--reason', 'done')
    strict = ukit.policy(mode='required', version=2, role_policy={'arbiters': ['erin']})
    custom_flow(u, strict)
    assert gate(u)['decision'] == 'blocked'
    _, out = u.start()
    s3 = out['result']['session_id']
    a3 = u.submit(s3, u.task_for('D5', 'a'), 'Again.')['result']['attempt_id']
    r = u.review(s3, [u.decision('D5', [a3], supersedes_ids=[bad['decision_id']],
                                 resolves_reservation_ids=res, correction_of_review_error=True,
                                 evidence_refs=['src/pipeline.py'])],
                 reviewer='dave', expect=None)
    assert not r['ok'] and code(r) == 'review_required'
    g = gate(u)
    assert g['decision'] == 'blocked'
    assert any(x['code'] == 'unarbitrated_conflict' and x['dimension'] == 'D5'
               for x in g['reasons'])
    # erin, the arbiter the policy names now, settles it again.
    assert _arb(u, s1, 'erin', [good['decision_id'], bad['decision_id']], [],
                good['decision_id'])['ok']
    assert not any(x['code'] == 'unarbitrated_conflict' and x['dimension'] == 'D5'
                   for x in gate(u)['reasons'])


def test_control_supersede_in_an_unarbitrated_conflict_is_refused(tmp_path):
    """Ported control: unchanged."""
    u = U(tmp_path)
    u.set_policy(REQ)
    plan, out = u.start()
    s1 = out['result']['session_id']
    t5 = next(t for t in plan['plan']['task_ids'] if u.bank_task(t)['dimension_ids'][0] == 'D5')
    a = u.submit(s1, t5)['result']['attempt_id']
    u.review(s1, [u.decision('D5', [a])], reviewer='bob')
    bad = u.review(s1, [u.decision('D5', [a], status='to_consolidate')],
                   reviewer='dave')['result']['decisions'][0]
    a3 = u.submit(s1, u.task_for('D5', 'a'), 'Again.')['result']['attempt_id']
    r = u.review(s1, [u.decision('D5', [a3], supersedes_ids=[bad['decision_id']],
                                 correction_of_review_error=True)], reviewer='dave', expect=None)
    assert not r['ok'] and code(r) == 'review_required'


# --- C4-5: one applied policy for the peer coverage and its gap -------------------------------

def test_peer_gap_rule_with_a_policy_raised_during_the_session(tmp_path):
    """Ported: the team raises minimum_people to three mid-session; the gate, the export
    preview and the report all report the D2 peer gap."""
    u = U(tmp_path)
    p3 = ukit.policy(mode='required', version=2, team_coverage={'minimum_people': 3})

    def tmap(u, sid, current):
        u.set_policy(p3)
        _, rv = advkit.transfer(u, sid)
        return {'D2': rv['result']['decision_id']}

    sid = custom_flow(u, REQ, peer=False, transfer_map=tmap)
    g = gate(u)
    assert 'D2' in g['missing_peer_dimensions']
    prev = u.call('export', 'preview', '--session', sid, '--repo', u.repo)
    assert {'kind': 'peer_coverage_missing', 'ref': 'D2'} in prev['known_gaps']
    assert 'handover by a colleague' in render.section(u.study, u.state())


# --- C4-6: coaching never blocks, even when the policy payload is gone -----------------------

def _purge_blobs(u):
    """Remove every stored payload the review's state names (policy, plans, snapshots,
    tasksets, answers...). The study's own payloads (exposure row keys...) stay: the
    reviewer's probe removed them too, and the core export then refuses with integrity_error,
    a rule of the study engine that the review does not change."""
    blobs = StudyStore(u.study).home / BLOBS_DIR
    named = set()

    def walk(node):
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, str) and len(node) == 64:
            named.add(node)
    walk(u.ext())
    gone = [p for p in blobs.iterdir() if p.name in named and p.is_file()]
    assert gone
    for p in gone:
        p.unlink()


def test_coaching_with_purged_blobs_does_not_block_export_handoff(tmp_path):
    """Ported: stored payloads removed by hand (ADR 0008 keeps the historical judgement).
    The state records mode coaching: the export keeps its ungated contract, and status
    reports the policy as unavailable instead of failing."""
    u = U(tmp_path)
    custom_flow(u, ukit.POLICY)        # coaching
    assert cli.run(['export', 'handoff', '--study', str(u.study)]).exit_code == 0
    recorded = u.ext()['policy']
    _purge_blobs(u)
    st = u.call('status')
    assert st['policy_available'] is False
    assert st['mode'] == 'coaching' and st['policy_digest'] == recorded['digest']
    assert all(d['freshness'] == 'unknown' for s in st['sessions'] for d in s['dimensions'])
    out = cli.run(['export', 'handoff', '--study', str(u.study),
                   '--out', str(tmp_path / 'pack2')])
    assert (out.payload.get('error') or {}).get('code') != 'milestone_blocked'
    assert out.exit_code in (0, 3), out.payload
    assert 'understanding' not in out.payload


def test_required_with_an_unreadable_policy_still_blocks_export_handoff(tmp_path):
    """Control: the state records mode required; with its policy payload gone the handoff
    goes through the gated protocol, which refuses and writes no pack."""
    u = U(tmp_path)
    custom_flow(u, REQ)
    blob = u.ext()['policy']['blob']
    (StudyStore(u.study).home / BLOBS_DIR / blob).unlink()
    target = tmp_path / 'pack'
    out = cli.run(['export', 'handoff', '--study', str(u.study), '--out', str(target)])
    assert out.exit_code != 0 and not out.payload.get('ok'), out.payload
    assert not target.exists()
    assert u.call('status')['policy_available'] is False
