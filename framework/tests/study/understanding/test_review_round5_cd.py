"""Review round 5 (areas C and D): one judgement, one gap list.

The reviewer's probes ``p1``..``p12`` are ported with the expected outcome of each fix (the
failing ones were defects). ``p11`` failed only because its assertion was too strict: the
study store's own bookkeeping (``receipts``, the idempotency receipts of every request, and
``updated``, the time of the last write) changes with any recorded request; the port
excludes those two keys and checks instead that every new receipt is one of the review's own
requests and that no earlier receipt changed.

The invariant of ADR 0008, CLI-CONTRACT §16 and the handoff is then checked on many study
states: for one state, ``understanding check``, the export projection (preview), the report
section and ``verify-export --policy-file <same policy> --study`` reach the same verdict and
the same gaps. Simulated humans only; everything lives in ``tmp_path``.
"""
from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import advkit  # noqa: E402,F401
from advkit import U, ukit, gate, custom_flow, SIM  # noqa: E402
from mlkit.study import cli  # noqa: E402
from mlkit.study.store import BLOBS_DIR, StudyStore  # noqa: E402
from mlkit.study.understanding import evaluate as ev, export as ex, render  # noqa: E402
from mlkit.study.understanding import verify as vf  # noqa: E402

REQ = ukit.policy(mode='required')
AIDED = dict(ukit.ASSIST, ai_assistance_declared=True, independence_claim=None,
             resources_used=['chat assistant'])
NON_GATE_GAPS = set(vf.EXPORT_ONLY_GAPS) | set(ev.LIMITATION_GAPS)
# What the standalone verifier adds from the artefact itself (not a reason of the gate).
STANDALONE_ARTEFACT_ONLY = {'privacy_review_pending', 'public_integrity_invalid',
                            'public_sources_stale', 'public_sources_unknown',
                            'private_context_unknown'}


def _verify(u, policy_doc=None, study=True, target='worktree', repo=None):
    args = ['understanding', 'verify-export', '--repo', str(repo or u.repo), '--target', target]
    if policy_doc is not None:
        args += ['--policy-file', str(u.file(f'vpol-{u.n}.json', policy_doc))]
    if study:
        args += ['--study', str(u.study)]
    return cli.run(args).payload


def _written(u, sid) -> dict:
    ukit.approve_all(u, sid)
    w = u.m('export', 'write', '--session', sid, '--repo', u.repo)
    return json.loads((u.repo / ex.EXPORT_DIR / w['review_id'] / ex.JSON_FILE).read_text())


def _report_gaps(u) -> str:
    html = render.section(u.study, u.state())
    i = html.find('<h3>Gaps')
    return html[i:html.find('</ul>', i)] if i >= 0 else ''


def _literals(text: str) -> set:
    return set(re.findall(r'data-literal="identifier">([^<]+)</code>', text))


def _pairs(reasons) -> set:
    return {(r['code'], r.get('dimension') or 'handoff') for r in reasons
            if r['code'] != 'no_required_check'}


def _gap_pairs(gaps) -> set:
    return {(g['kind'], g['ref']) for g in gaps if g['kind'] not in NON_GATE_GAPS}


def _edit_d5_rubric(u):
    f = u.case_dir / 'understanding.yaml'
    old = 'Explains how the same fitted transformation is applied at prediction time.'
    text = f.read_text()
    assert old in text
    f.write_text(text.replace(old, 'Explains how the fitted transformation is reused at '
                              'prediction time, and why.'))


def _select(u, sid, tmap=None):
    ext = u.ext()
    dm = {d['dimension_id']: d['decision_id'] for d in ext['decisions'].values()
          if d['kind'] == 'attempt' and d['session_id'] == sid
          and d['reviewer_declared_id'] == 'bob'}
    if tmap is None:
        tmap = {'D2': next(d['decision_id'] for d in ext['decisions'].values()
                           if d['kind'] == 'transfer')}
    u.m('select', '--file', u.file(f'sel-{u.n}.json', {
        'milestone': 'handoff', 'actor_scope': {'actor_declared_id': 'alice',
                                                'profile': 'pipeline'},
        'dimension_decision_map': dm, 'transfer_decision_map': tmap,
        'reservation_resolution_refs': []}))


def _arb(u, sid, arbiter, ids, res, chosen):
    return u.m('arbitrate', '--session', sid, '--file', u.file(f'arb-{u.n}.json', {
        'arbiter_declared_id': arbiter, 'declaration': SIM, 'simulated': True,
        'conflicting_decision_ids': ids, 'reservation_ids': res, 'chosen_decision_id': chosen,
        'rationale': 'Simulated arbitration.', 'evidence_refs': ['src/pipeline.py']}))


def _d5_conflict(u, sid):
    """dave reviews the D5 attempt bob demonstrated as to_consolidate: a conflict and a
    reservation (before the session is closed)."""
    ext = u.ext()
    good = next(d for d in ext['decisions'].values() if d['kind'] == 'attempt'
                and d['dimension_id'] == 'D5')
    bad = u.review(sid, [u.decision('D5', good['attempt_ids'], status='to_consolidate')],
                   reviewer='dave')['result']['decisions'][0]
    res = [r for r, x in u.ext()['reservations'].items()
           if x['decision_id'] == bad['decision_id']]
    return good['decision_id'], bad['decision_id'], res


# --- the reviewer's probes, ported ---------------------------------------------------------

def test_p1_unrelated_study_progress_one_verdict(tmp_path):
    """R5-1. The junior keeps working after the review: one more study decision is confirmed
    (no pipeline dimension depends on it). check allows; the export and the report show no
    gap of the gate; verify-export --policy-file <same> --study allows too (it blocked with
    private_context_unknown from its own rule). The private context changed, which the
    private_context_verification axis still says."""
    u = U(tmp_path)
    sid = custom_flow(u, REQ)
    assert gate(u)['decision'] == 'allowed'
    u.flow.variant(run=False)
    g = gate(u)
    assert g['decision'] == 'allowed'
    prev = u.call('export', 'preview', '--session', sid, '--repo', u.repo)
    assert _gap_pairs(prev['known_gaps']) == set()
    assert _report_gaps(u) == ''
    _written(u, sid)
    gen = _verify(u, REQ)['generations'][0]
    assert gen['gate_result']['decision'] == g['decision'] == 'allowed'
    assert gen['judgement'] == 'study' and gen['exported_content_current'] is True
    assert gen['private_context_verification'] == 'unknown'


def test_p2_public_only_private_unknown_one_verdict(tmp_path):
    """R5-2. public_only: a rubric depends on a study decision the junior has not confirmed
    yet. check allows with the limitation private_context_unknown; the export says that
    dimension's freshness is unknown with a private_context_unknown gap (a limitation, as the
    gate counts it); verify-export with the same policy allows (it blocked)."""
    pol_ = ukit.policy(mode='required', context_requirement='public_only')
    u = U(tmp_path, pauses=False)
    u.flow.pauses(model_decisions=False)
    sid = custom_flow(u, pol_)
    g = gate(u)
    assert g['decision'] == 'allowed', g['reasons']
    assert 'private_context_unknown' in g['limitations']
    unknown = sorted(d for d, i in g['dimensions'].items()
                     if i.get('freshness_limitation') == 'private_context_unknown')
    assert unknown
    prev = u.call('export', 'preview', '--session', sid, '--repo', u.repo)
    assert _gap_pairs(prev['known_gaps']) == set()
    assert {('private_context_unknown', d) for d in unknown} <= {
        (x['kind'], x['ref']) for x in prev['known_gaps']}
    doc = _written(u, sid)
    assert {d['id']: d['freshness_at_export'] for d in doc['dimensions']
            if d['id'] in unknown} == {d: 'unknown' for d in unknown}
    assert 'private_context_unknown' in doc['limitations']
    gen = _verify(u, pol_)['generations'][0]
    assert gen['gate_result']['decision'] == g['decision']
    # Standalone, on the same content: the limitation is read from the export, no block.
    alone = _verify(u, pol_, study=False)['generations'][0]['gate_result']
    assert not [r for r in alone['reasons'] if r.get('dimension') in unknown], alone


def test_p3_aided_selected_decision_gaps(tmp_path):
    """R5-6. D3 critical, unaided_required; its only attempt was AI-assisted and reviewed
    demonstrated. check blocks (assistance_not_admissible); the export shows D3 needs_review
    with that gap (it showed demonstrated and no gap), the report names the code, and the
    standalone verifier gives the same code."""
    def attempts_for(u, sid, dim, tid):
        if dim != 'D3':
            return None
        return [u.submit(sid, tid, 'With help.', assist=AIDED)['result']['attempt_id']]
    u = U(tmp_path)
    sid = custom_flow(u, REQ, attempts_for=attempts_for)
    g = gate(u)
    assert g['decision'] == 'blocked'
    assert ('assistance_not_admissible', 'D3') in _pairs(g['reasons'])
    prev = u.call('export', 'preview', '--session', sid, '--repo', u.repo)
    assert {'kind': 'assistance_not_admissible', 'ref': 'D3'} in prev['known_gaps']
    assert _gap_pairs(prev['known_gaps']) == _pairs(g['reasons'])
    assert 'assistance_not_admissible' in _literals(_report_gaps(u))
    doc = _written(u, sid)
    assert next(d for d in doc['dimensions'] if d['id'] == 'D3')['status'] == 'needs_review'
    alone = _verify(u, REQ, study=False)['generations'][0]['gate_result']
    assert ('assistance_not_admissible', 'D3') in _pairs(alone['reasons'])


def test_p4_expired_policy_gaps(tmp_path):
    """R5-7. The policy expired: the gate says every selected dimension is stale; the export
    shows them stale with the gate's ``stale`` gaps (it claimed no gap), so does the report,
    and the standalone verifier applies the rule too."""
    pol_ = ukit.policy(mode='required', expiration_rule={'kind': 'until', 'date': '2026-01-01'})
    u = U(tmp_path)
    sid = custom_flow(u, pol_)
    g = gate(u)
    assert g['decision'] == 'blocked'
    stale = {d for c, d in _pairs(g['reasons']) if c == 'stale'}
    assert stale == set(g['dimensions'])
    prev = u.call('export', 'preview', '--session', sid, '--repo', u.repo)
    assert _gap_pairs(prev['known_gaps']) == _pairs(g['reasons'])
    assert 'stale' in _literals(_report_gaps(u))
    doc = _written(u, sid)
    assert {d['freshness_at_export'] for d in doc['dimensions'] if d['id'] in stale} == \
        {'stale'}
    alone = _verify(u, pol_, study=False)['generations'][0]['gate_result']
    assert {('stale', d) for d in stale} <= _pairs(alone['reasons'])


def test_p5_same_policy_file_for_check_and_verify(tmp_path):
    """R5-4. The organisation's policy file is the study's policy re-issued as version 2.
    check --policy-file F blocks every dimension (decision_policy_changed); verify-export
    --policy-file F --study blocks with the same reasons (it allowed), and so does the
    standalone verifier (the digest rule of the gate)."""
    u = U(tmp_path)
    sid = custom_flow(u, REQ)
    f = ukit.policy(mode='required', version=2)
    g = gate(u, '--policy-file', u.file('org.json', f))
    assert g['decision'] == 'blocked'
    _written(u, sid)
    gen = _verify(u, f)['generations'][0]
    assert gen['gate_result']['decision'] == g['decision']
    assert _pairs(gen['gate_result']['reasons']) == _pairs(g['reasons'])
    alone = _verify(u, f, study=False)['generations'][0]['gate_result']
    assert alone['decision'] == 'blocked'
    assert {c for c, _ in _pairs(g['reasons'])} <= {c for c, _ in _pairs(alone['reasons'])}


def test_p6_stale_dimension_report_gap(tmp_path):
    """R5-7 (report). A source D5 depends on changes: the report lists D5 with the gate's
    code (it listed only the peer gap)."""
    u = U(tmp_path)
    sid = custom_flow(u, REQ)
    (u.repo / 'src/transforms.py').write_text('def fit_imputer(train):\n    return train.median()\n')
    g = gate(u)
    assert g['decision'] == 'blocked'
    rep = _report_gaps(u)
    assert 'D5' in rep and 'stale' in _literals(rep)
    prev = u.call('export', 'preview', '--session', sid, '--repo', u.repo)
    assert _gap_pairs(prev['known_gaps']) == _pairs(g['reasons'])


def test_p7_selection_under_another_policy(tmp_path):
    """R5-5. Session, reviews and handover under the required policy; the team switches to
    coaching, selects, then switches back. check blocks (selection_policy_changed); the
    export shows that gap and verify-export --policy-file <the required policy> --study
    blocks (it allowed)."""
    u = U(tmp_path)
    sid = custom_flow(u, REQ, select=False)
    u.set_policy(ukit.POLICY)
    _select(u, sid)
    u.set_policy(REQ)
    g = gate(u)
    assert g['decision'] == 'blocked'
    assert ('selection_policy_changed', 'handoff') in _pairs(g['reasons'])
    prev = u.call('export', 'preview', '--session', sid, '--repo', u.repo)
    assert {'kind': 'selection_policy_changed', 'ref': 'handoff'} in prev['known_gaps']
    _written(u, sid)
    gen = _verify(u, REQ)['generations'][0]
    assert gen['gate_result']['decision'] == g['decision']
    assert _pairs(gen['gate_result']['reasons']) == _pairs(g['reasons'])
    # Standalone with the embedded policy: the export's gate reasons are reasons there.
    alone = _verify(u, REQ, study=False)['generations'][0]['gate_result']
    assert ('selection_policy_changed', 'handoff') in _pairs(alone['reasons'])


def test_p8_waiver(tmp_path):
    """R5-9. A waiver: verify-export --study gives the gate's own verdict (waivers are
    judged by the study's gate); the standalone verifier cannot see a waiver and blocks
    (documented in CLI-CONTRACT §16)."""
    pol_ = ukit.policy(mode='required', exemptions_policy={'waivers_allowed': True})
    u = U(tmp_path)
    sid = custom_flow(u, pol_)
    (u.repo / 'src/transforms.py').write_text('def fit_imputer(train):\n    return train.median()\n')
    ukit.git(u.repo, 'commit', '-qam', 'median')
    assert gate(u)['decision'] == 'blocked'
    u.m('waive', '--file', u.file('w.json', {
        'milestone': 'handoff', 'dimensions': ['D2', 'D5'],
        'reason': 'Imputer change reviewed in the PR.', 'scope': 'D5 only',
        'approver_declared_id': 'lead', 'expires_on': '2099-01-01',
        'unmet_requirements': ['stale']}))
    g = gate(u)
    assert g['decision'] == 'allowed_by_waiver', g['reasons']
    _written(u, sid)
    gens = _verify(u, pol_)['generations']
    assert gens and all(x['gate_result']['decision'] == g['decision'] for x in gens)
    assert all(x['gate_result']['waiver_ref'] == g['waiver_ref'] for x in gens)
    alone = _verify(u, pol_, study=False)['generations'][0]['gate_result']
    assert alone['decision'] == 'blocked'


def test_p9_report_mode_unreadable_policy(tmp_path):
    """R5-8. The required policy's stored payload is gone: the report shows the recorded
    mode (it said ``off``) and says the policy is unavailable; check refuses."""
    u = U(tmp_path)
    custom_flow(u, REQ)
    blob = u.ext()['policy']['blob']
    (StudyStore(u.study).home / BLOBS_DIR / blob).unlink()
    st = u.call('status')
    assert (st['mode'], st['policy_available']) == ('required', False)
    html = render.section(u.study, u.state())
    assert 'identifier">required<' in html
    assert 'policy_unavailable' in _literals(_report_gaps(u))
    chk = u.call('check', '--milestone', 'handoff', expect=None)
    assert chk['error']['code'] == 'evidence_unavailable'


def test_p10_no_answer_text_in_outputs(tmp_path):
    MARK = 'ZQXJ-secret-answer-marker'

    def attempts_for(u, sid, dim, tid):
        return [u.submit(sid, tid, f'{MARK} for {dim}.')['result']['attempt_id']]
    u = U(tmp_path)
    sid = custom_flow(u, REQ, attempts_for=attempts_for)
    outs = [u.call('status'), u.call('check', '--milestone', 'handoff'),
            u.call('task', '--session', sid, expect=None),
            u.call('export', 'preview', '--session', sid, '--repo', u.repo)]
    ukit.approve_all(u, sid)
    outs.append(u.m('export', 'write', '--session', sid, '--repo', u.repo))
    outs.append(u.call('git-plan', '--session', sid, '--repo', u.repo))
    outs.append(_verify(u, REQ))
    outs.append(_verify(u, REQ, study=False))
    blob = json.dumps(outs) + render.section(u.study, u.state())
    for p in (u.repo / 'docs').rglob('*'):
        if p.is_file():
            blob += p.read_text(errors='replace')
    home = StudyStore(u.study).home
    for name in ('state.json', 'revisions.jsonl', 'events.jsonl'):
        for p in home.rglob(name):
            blob += p.read_text(errors='replace')
    assert MARK not in blob


def test_p11_no_scientific_record_change(tmp_path):
    """Port of p11 with its over-strict assertion corrected: ``receipts`` (the store's
    idempotency receipts, one per recorded request) and ``updated`` (the time of the last
    write) change with any request. No other key changes, every new receipt is one of the
    review's requests and no earlier receipt changed."""
    u = U(tmp_path)
    before = copy.deepcopy(u.state())
    sid = custom_flow(u, REQ)
    _written(u, sid)
    after = u.state()
    diff = sorted(k for k in set(before) | set(after)
                  if k not in ('understanding', 'revision', 'receipts', 'updated')
                  and before.get(k) != after.get(k))
    assert not diff
    old, new = before['receipts'], after['receipts']
    assert all(new.get(k) == v for k, v in old.items())
    added = set(new) - set(old)
    assert added and all(re.fullmatch(r'ur\d+|receipt-.+', k) for k in added), sorted(added)


def test_p12_public_only_private_stale_after_export(tmp_path):
    """R5-3. public_only. The export is written; then the junior changes the preprocessing
    decision D5 depends on. check blocks (stale D5); verify-export --policy-file <same>
    --study blocks too (it allowed) and says the exported content is no longer current."""
    pol_ = ukit.policy(mode='required', context_requirement='public_only')
    u = U(tmp_path)
    sid = custom_flow(u, pol_)
    _written(u, sid)
    u.flow.decide('preprocessing', {'missing': 'none', 'rare_category_min_rows': 5, 'caps': {},
                                    'log_transform': []})
    g = gate(u)
    assert g['decision'] == 'blocked'
    assert ('stale', 'D5') in _pairs(g['reasons'])
    gen = _verify(u, pol_)['generations'][0]
    assert gen['gate_result']['decision'] == g['decision']
    assert _pairs(gen['gate_result']['reasons']) == _pairs(g['reasons'])
    assert gen['exported_content_current'] is False


# --- R5-10: the written attributes cancel every transforming attribute ------------------------

def test_attributes_cancel_working_tree_encoding_and_eol(tmp_path):
    """R5-10. The repository sets ``*.md working-tree-encoding=UTF-16LE`` and ``*.json text
    eol=crlf`` at its root. The written ``docs/understanding/.gitattributes`` unsets them for
    the generations: staging, committing and a fresh clone keep the exported bytes, and the
    verifier finds them valid in the index, the commit and the clone's working tree."""
    u = U(tmp_path)
    (u.repo / '.gitattributes').write_text('*.md working-tree-encoding=UTF-16LE\n'
                                           '*.json text eol=crlf\n')
    ukit.git(u.repo, 'add', '--', '.gitattributes')
    ukit.git(u.repo, 'commit', '-qm', 'attributes')
    sid = custom_flow(u, REQ)
    ukit.approve_all(u, sid)
    w = u.m('export', 'write', '--session', sid, '--repo', u.repo)
    assert w['git_attributes'] == 'written'
    attrs = (u.repo / ex.EXPORT_DIR / ex.ATTRIBUTES_FILE).read_bytes()
    assert attrs == ex.ATTRIBUTES == \
        b'rv-*/** binary -filter -ident -working-tree-encoding -eol\n'
    md = f'{ex.EXPORT_DIR}/{w["review_id"]}/{ex.MD_FILE}'
    shown = ukit.git(u.repo, 'check-attr', 'working-tree-encoding', 'eol', 'text', 'filter',
                     'ident', 'diff', 'merge', '--', md)
    assert all(line.endswith(': unset') for line in shown.splitlines()), shown
    plan = u.call('git-plan', '--session', sid, '--repo', u.repo)
    assert f'{ex.EXPORT_DIR}/{ex.ATTRIBUTES_FILE}' in [a['path'] for a in plan['artefacts']]
    u.call('git-stage', '--session', sid, '--repo', u.repo, '--index-identity',
           plan['index_identity'])
    assert _verify(u, study=False, target='index')['public_integrity'] == 'valid'
    ukit.git(u.repo, 'commit', '-qm', 'review')
    assert _verify(u, study=False, target='HEAD')['public_integrity'] == 'valid'
    clone = tmp_path / 'clone'
    subprocess.run(['git', 'clone', '-q', str(u.repo), str(clone)], check=True)
    for name in ex.FILES:
        rel = f'{ex.EXPORT_DIR}/{w["review_id"]}/{name}'
        assert (clone / rel).read_bytes() == (u.repo / rel).read_bytes(), name
    assert _verify(u, study=False, repo=clone)['public_integrity'] == 'valid'


def test_attributes_of_round_4_read_as_differs(tmp_path):
    """The exact-bytes rule is kept: a ``.gitattributes`` holding the round-4 line (which
    let ``working-tree-encoding`` and ``eol`` apply) is left untouched and reported
    ``differs``."""
    u = U(tmp_path)
    sid = custom_flow(u, REQ)
    old = b'rv-*/** binary -filter -ident\n'
    (u.repo / ex.EXPORT_DIR).mkdir(parents=True)
    (u.repo / ex.EXPORT_DIR / ex.ATTRIBUTES_FILE).write_bytes(old)
    ukit.approve_all(u, sid)
    w = u.m('export', 'write', '--session', sid, '--repo', u.repo)
    assert w['git_attributes'] == 'differs'
    assert (u.repo / ex.EXPORT_DIR / ex.ATTRIBUTES_FILE).read_bytes() == old
    assert any(ex.ATTRIBUTES_FILE in s for s in w['next_steps'])


# --- the standalone verifier mirrors the gate's rules on the content --------------------------

FIXTURE = Path(__file__).resolve().parents[2] / 'fixtures' / 'understanding' / 'export-valid'
AXES = {'public_integrity': 'valid', 'public_source_freshness': 'current',
        'private_context_verification': 'verified', 'evidence_availability': 'available'}


def _fixture_doc() -> dict:
    from mlkit.study.understanding import canonical
    return canonical.loads((FIXTURE / ex.JSON_FILE).read_bytes())


def test_standalone_rules_mirror_the_gate_on_the_committed_export():
    """On the committed export (allowed as published): each rule of the gate the content can
    carry gives the gate's code on the dimension it concerns."""
    doc = _fixture_doc()
    policy = doc['policy']
    assert vf._gate_on_export(doc, policy, AXES)['decision'] == 'allowed'
    actor = doc['coverage_selection']['actor_alias']

    def pairs(d, p=policy, today=None):
        return _pairs(vf._gate_on_export(d, p, AXES, today=today)['reasons'])
    d = copy.deepcopy(doc)
    crit = next(x for x in d['dimensions'] if x['critical'])
    crit['reviewer_alias'] = actor
    assert ('reviewer_not_distinct', crit['id']) in pairs(d)
    d = copy.deepcopy(doc)
    crit = next(x for x in d['dimensions'] if x['critical'])
    crit['assistance_summary'] = 'aided'
    assert ('assistance_not_admissible', crit['id']) in pairs(d)
    d = copy.deepcopy(doc)
    d['dimensions'][0]['evidence_availability'] = 'unavailable'
    assert ('evidence_unavailable', d['dimensions'][0]['id']) in pairs(d)
    relaxed = dict(policy, evidence_requirement='recorded_decisions')
    out = vf._gate_on_export(d, relaxed, AXES)
    assert ('evidence_unavailable', d['dimensions'][0]['id']) not in _pairs(out['reasons'])
    assert 'evidence_not_reauditable' in out['limitations']
    expired = dict(policy, expiration_rule={'kind': 'until', 'date': '2026-01-01'})
    got = pairs(doc, expired, today='2026-10-25')
    assert {('stale', x['id']) for x in doc['dimensions'] if x['human_review_ref']} <= got
    d = copy.deepcopy(doc)
    d['known_gaps'] = d['known_gaps'] + [{'kind': 'open_reservation', 'ref': 'D5'}]
    assert ('open_reservation', 'D5') in pairs(d)
    v2 = dict(policy, version=policy['version'] + 1)
    got = pairs(doc, v2)
    assert ('selection_policy_changed', 'handoff') in got
    assert {('decision_policy_changed', x['id']) for x in doc['dimensions']
            if x['human_review_ref']} <= got
    # A gap recorded under another policy is not imported (it was judged under that one).
    d = copy.deepcopy(doc)
    d['known_gaps'] = d['known_gaps'] + [{'kind': 'open_reservation', 'ref': 'D5'}]
    assert ('open_reservation', 'D5') not in pairs(d, v2)


# --- the invariant on many study states ---------------------------------------------------------

def _base(u):
    return custom_flow(u, REQ), None


def _unrelated(u):
    sid = custom_flow(u, REQ)
    u.flow.variant(run=False)
    return sid, None


def _stale_source(u):
    sid = custom_flow(u, REQ)
    (u.repo / 'src/transforms.py').write_text('def fit_imputer(train):\n    return 0\n')
    return sid, None


def _aided(u):
    def attempts_for(u, sid, dim, tid):
        if dim not in ('D3', 'D6'):
            return None
        return [u.submit(sid, tid, 'With help.', assist=AIDED)['result']['attempt_id']]
    return custom_flow(u, REQ, attempts_for=attempts_for), None


def _conflict(u):
    sid = custom_flow(u, REQ, close=False, select=False)
    _d5_conflict(u, sid)
    u.m('close', '--session', sid, '--to', 'completed', '--reason', 'review done')
    _select(u, sid)
    return sid, None


def _stale_arbitration(u):
    sid = custom_flow(u, REQ, close=False, select=False)
    good, bad, res = _d5_conflict(u, sid)
    assert _arb(u, sid, 'frank', [good, bad], res, good)['ok']
    u.m('close', '--session', sid, '--to', 'completed', '--reason', 'review done')
    _select(u, sid)
    assert gate(u)['decision'] == 'allowed'
    u.set_policy(ukit.policy(mode='required', version=2, role_policy={'arbiters': ['erin']}))
    return sid, None


def _second_session_reservation(u):
    sid = custom_flow(u, REQ)
    plan, out = u.start()
    s2 = out['result']['session_id']
    t6 = next(t for t in plan['plan']['task_ids'] if u.bank_task(t)['dimension_ids'][0] == 'D6')
    a = u.submit(s2, t6, 'Another answer.')['result']['attempt_id']
    u.review(s2, [u.decision('D6', [a], status='to_consolidate')], reviewer='bob')
    return sid, None


def _no_peer(u):
    return custom_flow(u, REQ, peer=False), None


def _policy_v2(u):
    sid = custom_flow(u, REQ)
    u.set_policy(ukit.policy(mode='required', version=2))
    return sid, None


def _expired(u):
    return custom_flow(u, ukit.policy(mode='required', expiration_rule={
        'kind': 'until', 'date': '2026-01-01'})), None


def _rubric(u):
    sid = custom_flow(u, REQ)
    _edit_d5_rubric(u)
    return sid, None


def _private_stale(u):
    sid = custom_flow(u, ukit.policy(mode='required', context_requirement='public_only'))
    u.flow.decide('preprocessing', {'missing': 'none', 'rare_category_min_rows': 5, 'caps': {},
                                    'log_transform': []})
    return sid, None


def _private_unknown(u):
    u.flow.pauses(model_decisions=False)
    return custom_flow(u, ukit.policy(mode='required', context_requirement='public_only')), None


def _waiver(u):
    pol_ = ukit.policy(mode='required', exemptions_policy={'waivers_allowed': True})
    sid = custom_flow(u, pol_)
    (u.repo / 'src/transforms.py').write_text('def fit_imputer(train):\n    return 3\n')
    u.m('waive', '--file', u.file('w.json', {
        'milestone': 'handoff', 'dimensions': ['D2', 'D5'], 'reason': 'Reviewed in the PR.',
        'scope': 'D5 only', 'approver_declared_id': 'lead', 'expires_on': '2099-01-01',
        'unmet_requirements': ['stale']}))
    return sid, None


def _unreadable_answer(u):
    sid = custom_flow(u, REQ)
    ext = u.ext()
    d5 = next(d for d in ext['decisions'].values() if d['kind'] == 'attempt'
              and d['dimension_id'] == 'D5')
    sha = ext['attempts'][d5['attempt_ids'][0]]['response_sha256']
    (StudyStore(u.study).home / BLOBS_DIR / sha).unlink()
    return sid, None


def _coaching(u):
    def attempts_for(u, sid, dim, tid):
        if dim != 'D3':
            return None
        return [u.submit(sid, tid, 'With help.', assist=AIDED)['result']['attempt_id']]
    return custom_flow(u, ukit.POLICY, attempts_for=attempts_for), None


def _selection_other_policy(u):
    sid = custom_flow(u, REQ, select=False)
    u.set_policy(ukit.POLICY)
    _select(u, sid)
    u.set_policy(REQ)
    return sid, None


def _no_selection(u):
    return custom_flow(u, REQ, select=False), None


def _explicit_policy_file(u):
    return custom_flow(u, REQ), ukit.policy(mode='required', version=2)


def _rectified(u):
    sid = custom_flow(u, REQ)
    ext = u.ext()
    d6 = next(d for d in ext['decisions'].values() if d['kind'] == 'attempt'
              and d['dimension_id'] == 'D6')
    u.m('rectify', '--attempt', d6['attempt_ids'][0], '--assistance-file',
        u.file('rect.json', AIDED))
    return sid, None


SCENARIOS = {
    'base': _base, 'unrelated_private_progress': _unrelated, 'stale_source': _stale_source,
    'aided_attempts': _aided, 'conflict_and_reservation': _conflict,
    'arbitration_no_longer_admissible': _stale_arbitration,
    'reservation_in_another_session': _second_session_reservation, 'no_peer': _no_peer,
    'policy_reissued': _policy_v2, 'expired_policy': _expired, 'rubric_changed': _rubric,
    'private_decision_changed': _private_stale, 'private_reference_unknown': _private_unknown,
    'waiver': _waiver, 'answer_blob_removed': _unreadable_answer, 'coaching': _coaching,
    'selection_under_another_policy': _selection_other_policy, 'no_selection': _no_selection,
    'explicit_policy_file': _explicit_policy_file, 'help_rectified': _rectified,
}


# The verdict and some of the codes each state must give (``g``: with the policy file when
# the scenario has one), so the invariant is checked on states that block for many reasons.
EXPECT = {
    'base': ('allowed', set()), 'unrelated_private_progress': ('allowed', set()),
    'stale_source': ('blocked', {'stale'}),
    'aided_attempts': ('blocked', {'assistance_not_admissible'}),
    'conflict_and_reservation': ('blocked', {'unarbitrated_conflict', 'open_reservation'}),
    'arbitration_no_longer_admissible': ('blocked', {'arbitration_not_admissible',
                                                     'decision_policy_changed'}),
    'reservation_in_another_session': ('blocked', {'open_reservation'}),
    'no_peer': ('blocked', {'peer_coverage_missing'}),
    'policy_reissued': ('blocked', {'decision_policy_changed', 'selection_policy_changed',
                                    'dimension_not_demonstrated'}),
    'expired_policy': ('blocked', {'stale'}),
    'rubric_changed': ('blocked', {'rubric_changed', 'taskset_changed',
                                   'dimension_not_demonstrated'}),
    'private_decision_changed': ('blocked', {'stale'}),
    'private_reference_unknown': ('allowed', set()),
    'waiver': ('allowed_by_waiver', {'stale'}),
    'answer_blob_removed': ('blocked', {'evidence_unavailable'}),
    'coaching': ('not_applicable', set()),
    'selection_under_another_policy': ('blocked', {'selection_policy_changed'}),
    'no_selection': ('blocked', {'no_selection'}),
    'explicit_policy_file': ('blocked', {'decision_policy_changed'}),
    'help_rectified': ('blocked', {'assistance_rectified_after_review'}),
}


@pytest.mark.parametrize('scenario', sorted(SCENARIOS))
def test_one_judgement_one_gap_list(tmp_path, scenario):
    """For one study state: ``check`` (with the policy file when the scenario has one),
    the export preview, the report section and ``verify-export [--policy-file F] --study``
    reach the same verdict, and the gate's reason codes are the export's and the report's
    gap codes (both ways for the dimension gaps, when a selection of the session's person
    exists and the policy requires the milestone).

    Review round 6: the local ``gate_result`` may differ from ``check`` only by reasons
    established on a verified tree whose bytes ``check`` did not read (R6-2; none here, the
    session's own working tree is verified); the standalone verifier's reasons under the
    embedded policy are compared with the export's recorded gate reasons on every state
    (R6-4)."""
    u = U(tmp_path, pauses=scenario != 'private_reference_unknown')
    sid, policy_file = SCENARIOS[scenario](u)
    study_gate = gate(u)
    g = gate(u, '--policy-file', u.file('check-policy.json', policy_file)) \
        if policy_file else study_gate
    decision, some = EXPECT[scenario]
    assert g['decision'] == decision, g['reasons']
    assert some <= {r['code'] for r in g['reasons']}, g['reasons']
    ext = u.ext()
    s = ext['sessions'][sid]
    has_selection = ev.selection_for(ext, 'handoff', s['actor_declared_id'],
                                     s['profile']) is not None
    prev = u.call('export', 'preview', '--session', sid, '--repo', u.repo)
    gate_pairs, gap_pairs = _pairs(study_gate['reasons']), _gap_pairs(prev['known_gaps'])
    assert gate_pairs <= gap_pairs, (gate_pairs, prev['known_gaps'])
    if scenario == 'coaching':       # not a pass, but every reason is in the export
        assert ('assistance_not_admissible', 'D3') in gap_pairs
    exact = has_selection and study_gate['decision'] != 'not_applicable'
    if exact:
        assert gap_pairs == gate_pairs, (gate_pairs, prev['known_gaps'])
    # The report: every gate code is named, and only gate codes (and dimension ids, people,
    # the milestone and the limitation gaps) appear as literals in its gap list.
    lits = _literals(_report_gaps(u))
    codes = {c for c, _ in gate_pairs}
    assert codes <= lits, (codes, lits)
    if exact:
        people = {'alice', 'bob', 'carol', 'dave', 'frank', 'handoff'}
        extra = lits - codes - set(ev.LIMITATION_GAPS) - people - set(ex.DIMENSIONS)
        assert not extra, extra
    # The export is producible whatever the gate says; the verifier's judgement is the
    # study's gate for the exported session.
    doc = _written(u, sid)
    assert set(study_gate['limitations']) <= set(doc['limitations'])
    gen = _verify(u, policy_file)['generations'][0]
    assert gen['public_integrity'] == 'valid', gen['problems']
    assert gen['judgement'] == 'study'
    # Review round 6 (R6-2): the local gate_result is check's plus the reasons established
    # on the verified tree that check did not judge. Here the verified tree is the working
    # tree of the session's repository, the very bytes check read (a public source changed
    # since the snapshot is check's ``stale`` on the dimensions it concerns, which a waiver
    # may cover), so nothing is added and the result is exactly check's.
    assert gen['gate_result']['target_tree_reasons'] == []
    assert gen['public_sources_judged_by_study'] is True
    if scenario in ('stale_source', 'waiver'):        # a public source changed in the tree
        assert gen['public_source_freshness'] == 'stale'
    assert gen['gate_result']['decision'] == g['decision'], (g['reasons'], gen['gate_result'])
    assert _pairs(gen['gate_result']['reasons']) == _pairs(g['reasons'])
    assert gen['gate_result']['waiver_ref'] == g['waiver_ref']
    assert gen['exported_content_current'] is True
    if policy_file:
        plain = _verify(u)['generations'][0]['gate_result']
        assert plain['decision'] == study_gate['decision']
    # Review round 6 (R6-4): with the embedded policy, the standalone verifier's reasons
    # (other than what only the artefact establishes) are the reasons the export's gate
    # recorded, and check's when the export is about the selection check judges.
    out = _verify(u, doc['policy'], study=False)['generations'][0]
    standalone = {p for p in _pairs(out['gate_result']['reasons'])
                  if p[0] not in STANDALONE_ARTEFACT_ONLY
                  and p != ('evidence_unavailable', 'handoff')}
    assert standalone == _gap_pairs(doc['known_gaps']), (standalone, doc['known_gaps'])
    if exact and not policy_file:
        assert standalone == gate_pairs


# --- the invariant on cross-session states (review round 7) -----------------------------------

NARROW = [s for s in ukit.SOURCES if s['path'] == 'src/pipeline.py']
OTHER_IMPUTER = 'def fit_imputer(train):\n    return 0\n'
GIT_ID = ('-c', 'user.name=T', '-c', 'user.email=t@example.invalid')
# (S2 in a clone of S1's repository, S2's mapped sources, what changes, verdict of HEAD):
# ``commit``: a commit after the export changes the imputer and the working tree is
# reverted (check reads the snapshot's bytes); ``conflict``: the imputer changes before S2
# starts, so S1 and S2 map the same logical key with different bytes; ``None``: nothing.
CROSS = {
    'same_repository': (False, ukit.SOURCES, 'commit', 'blocked'),
    'same_repository_narrow_scope': (False, NARROW, 'commit', 'blocked'),
    'same_repository_unchanged': (False, NARROW, None, 'allowed'),
    'clone': (True, ukit.SOURCES, 'commit', 'blocked'),
    'clone_narrow_scope': (True, NARROW, 'commit', 'blocked'),
    'clone_unchanged': (True, NARROW, None, 'allowed'),
    'scope_conflict': (False, ukit.SOURCES, 'conflict', 'blocked'),
    'clone_scope_conflict': (True, ukit.SOURCES, 'conflict', 'blocked'),
}


@pytest.mark.parametrize('scenario', sorted(CROSS))
def test_one_judgement_one_gap_list_cross_session(tmp_path, scenario):
    """S1 is selected (the selection maps its decisions); S2, of the same person and profile,
    is exported, in S1's repository or in a clone, with S1's sources or a narrower scope.
    Its export is committed and verified at HEAD.

    * The export's public scope covers every source the shown decisions depend on, or
      records ``scope_does_not_cover_shown_decision`` for the dimensions it cannot (R7-2).
    * ``verify-export --study`` never relaxes ``check`` (its reasons hold check's), and its
      verdict is the verdict of ``check`` run on the verified bytes (HEAD's bytes put in the
      working tree of every repository the gate reads; R7-1). On those bytes its reasons are
      check's, plus ``verified_repository_not_the_session_one`` when a judged session's
      repository is not the verified one and its scope is not current there.
    * The standalone verifier never says ``allowed`` or ``conforming`` where check on those
      bytes blocks, nor ``current`` where check finds a source stale or unknown."""
    clone, sources, change, verdict = CROSS[scenario]
    u = U(tmp_path)
    s1 = custom_flow(u, REQ)
    repo = u.repo
    if clone:
        repo = tmp_path / 'clone'
        ukit.git(tmp_path, 'clone', '-q', str(u.repo), str(repo))
        u.repo = repo
    if change == 'conflict':
        (repo / 'src/transforms.py').write_text(OTHER_IMPUTER)
        ukit.git(repo, *GIT_ID, 'commit', '-q', '-am', 'another imputer before S2')
    _, out = u.start(sources=sources)
    s2 = out['result']['session_id']
    doc = _written(u, s2)
    ext = u.ext()
    owners = {}
    for d in doc['dimensions']:
        x = ext['decisions'].get(d['human_review_ref'])
        if x is not None and x['session_id'] != s2:
            owners.setdefault(x['session_id'], set()).add(d['id'])
    assert set(owners) == {s1}
    store = StudyStore(u.study)
    from mlkit.study.understanding import canonical
    s1_scope = canonical.loads(store.read_blob(ext['sessions'][s1]['snapshot_blob']))['public']
    in_doc = {e['logical_key']: e for e in doc['public_source_scope']['entries']}
    uncovered = {e['logical_key'] for e in s1_scope['entries']
                 if in_doc.get(e['logical_key']) != e}
    gap_refs = {g['ref'] for g in doc['known_gaps'] if g['kind'] == ex.SCOPE_GAP}
    if uncovered:
        assert change == 'conflict', uncovered
        assert gap_refs == owners[s1]
    else:
        assert not gap_refs
    ukit.git(repo, 'add', '--', 'docs')
    ukit.git(repo, *GIT_ID, 'commit', '-q', '-m', 'export')
    if change == 'commit':
        (repo / 'src/transforms.py').write_text(OTHER_IMPUTER)
        ukit.git(repo, *GIT_ID, 'commit', '-q', '-am', 'change the imputer')
        ukit.git(repo, 'checkout', '-q', 'HEAD~1', '--', 'src/transforms.py')
    head = ukit.git(repo, 'rev-parse', 'HEAD')
    now = gate(u)
    gen = _verify(u, target=head, repo=repo)['generations'][0]
    assert gen['public_integrity'] == 'valid', gen['problems']
    assert gen['gate_result']['decision'] == verdict, gen['gate_result']
    assert _pairs(now['reasons']) <= _pairs(gen['gate_result']['reasons'])
    sa = _verify(u, doc['policy'], study=False, target=head, repo=repo)['generations'][0]
    # check on the verified bytes: HEAD's sources in every working tree the gate reads.
    tree = vf.Tree(repo, head)
    places = {line['repository'] for line in gen['verified_repository']['judged_sessions']}
    assert None not in places and str(repo.resolve()) in places
    for place in places:
        for s in ukit.SOURCES:
            (Path(place) / s['path']).write_bytes(tree.read(s['path']))
    on_bytes = gate(u)
    assert gen['gate_result']['decision'] == on_bytes['decision'], (
        gen['gate_result']['reasons'], on_bytes['reasons'])
    codes = {r['code'] for r in on_bytes['reasons']}
    if on_bytes['decision'] not in ('allowed', 'allowed_by_waiver'):
        assert sa['gate_result']['decision'] not in ('allowed', 'allowed_by_waiver')
        assert sa['declared_conformity'] != 'conforming'
    if codes & {'stale', 'freshness_unknown'}:
        assert sa['public_source_freshness'] != 'current'
    # On those bytes, local verification is check's result (the tree holds what it read).
    again = _verify(u, target=head, repo=repo)['generations'][0]
    assert again['public_sources_judged_by_study'] is True
    assert set(again['gate_result']['target_tree_reasons']) <= {vf.OTHER_REPOSITORY}
    assert again['gate_result']['decision'] == on_bytes['decision']
    assert _pairs(again['gate_result']['reasons']) - {(vf.OTHER_REPOSITORY, 'handoff')} == \
        _pairs(on_bytes['reasons'])
