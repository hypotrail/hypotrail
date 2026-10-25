"""Review round 6 (areas C and D): the export receipt, local verification on the verified
tree, unavailable payloads and the standalone reasons.

The reviewer's probes ``p1``..``p8`` are ported with the expected outcome of each fix (every
failing probe asserted the expected behaviour). ``p5`` was an exploratory probe that crashed
on its own last print (it read dimensions from an empty slice of the Markdown); its question,
whether ``check``, the export of a second active session of the same person and the
verifier agree, is now asserted. The comparison of the standalone reasons with the gate's on
every study state of round 5 lives in ``test_review_round5_cd.test_one_judgement_one_gap_list``.
Simulated humans only; everything lives in ``tmp_path``.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import advkit  # noqa: E402,F401
from advkit import U, ukit, gate, custom_flow  # noqa: E402
from mlkit.study import cli  # noqa: E402
from mlkit.study.store import BLOBS_DIR, StudyStore  # noqa: E402
from mlkit.study.understanding import export as ex, policy as pol  # noqa: E402
from mlkit.study.understanding import verify as vf  # noqa: E402
import test_review_round5_cd as r5  # noqa: E402

REQ = ukit.policy(mode='required')
ARTEFACT_ONLY = {'privacy_review_pending', 'public_integrity_invalid', 'public_sources_stale',
                 'public_sources_unknown', 'private_context_unknown'}
TREE = {'public_sources_stale', 'public_sources_unknown', 'privacy_review_pending',
        vf.OTHER_REPOSITORY}
GIT_ID = ('-c', 'user.name=T', '-c', 'user.email=t@example.invalid')


def _pairs(reasons):
    return {(r['code'], r.get('dimension') or 'handoff') for r in reasons
            if r['code'] != 'no_required_check'}


def _standalone(u, doc, repo=None):
    out = cli.run(['understanding', 'verify-export', '--repo', str(repo or u.repo), '--target',
                   'worktree', '--policy-file',
                   str(u.file(f'vp-{u.n}.json', doc['policy']))]).payload
    return out['generations'][0]


def _gate_pairs_of_standalone(gen):
    return {p for p in _pairs(gen['gate_result']['reasons'])
            if p[0] not in ARTEFACT_ONLY and p != ('evidence_unavailable', 'handoff')}


# --- R6-1: the receipt compares the applied policy -----------------------------------------

def test_p1_export_after_policy_change_is_published(tmp_path):
    """A session started under policy v1; the study's policy is then re-issued (v2). The
    export embeds the applied policy (v2) and its intent records that policy's digest, so the
    receipt says ``published`` and git-plan accepts it (it was ``not_current`` for ever)."""
    u = U(tmp_path)
    sid = custom_flow(u, ukit.POLICY)                       # coaching v1
    u.set_policy(ukit.policy(version=2))                    # coaching v2
    ukit.approve_all(u, sid)
    w = u.m('export', 'write', '--session', sid, '--repo', u.repo)
    doc = json.loads((u.repo / ex.EXPORT_DIR / w['review_id'] / ex.JSON_FILE).read_text())
    assert doc['policy']['version'] == 2
    assert w['receipt']['status'] == 'published', w['receipt']
    intent = u.ext()['exports'][w['receipt']['intent_id']]
    assert intent['policy_digest'] == doc['policy_digest'] == pol.digest(doc['policy'])
    assert intent['policy_digest'] != u.ext()['sessions'][sid]['policy_digest']
    plan = u.call('git-plan', '--session', sid, '--repo', u.repo, expect=None)
    assert plan.get('ok'), plan


def test_receipt_still_refuses_a_policy_changed_after_the_intent(tmp_path):
    """The receipt keeps its revalidation: a policy applied between the intent and the
    receipt (here by hand, under the writer lock of the receipt) makes it ``not_current``."""
    from mlkit.study.understanding import actions
    u = U(tmp_path)
    sid = custom_flow(u, ukit.POLICY)
    ukit.approve_all(u, sid)
    prev = u.call('export', 'preview', '--session', sid, '--repo', u.repo)
    files = {n: '0' * 64 for n in ex.FILES}
    st = u.state()
    intent = actions.apply(u.study, 'export_intent', {
        'session_id': sid, 'review_id': prev['review_id'],
        'projection_digest': prev['content_digest'],
        'destination': f'{ex.EXPORT_DIR}/{prev["review_id"]}', 'files': files,
        'created_at': '2026-10-25T00:00:00+00:00', 'base_commit': None,
        'repository': str(u.repo)}, request_id='intent-x', expected_revision=st['revision'])
    iid = intent['result']['intent_id']
    assert u.ext()['exports'][iid]['repository'] == str(u.repo)
    u.set_policy(ukit.policy(version=3))
    st = u.state()
    out = actions.apply(u.study, 'export_receipt', {'intent_id': iid, 'verified_files': files},
                        request_id='receipt-x', expected_revision=st['revision'])
    assert out['result']['status'] == 'not_current'


# --- R6-4: standalone reasons are the gate's --------------------------------------------

def test_p2_standalone_aided_gives_the_gate_reasons(tmp_path):
    """An aided demonstration on an unaided_required dimension: the export shows it
    ``needs_review`` because of ``assistance_not_admissible``, not because the decision is not
    demonstrated, so the standalone verifier no longer adds ``dimension_not_demonstrated``."""
    u = U(tmp_path)
    sid, _ = r5._aided(u)
    g = gate(u)
    doc = r5._written(u, sid)
    assert pol.digest(doc['policy']) == g['policy_digest']
    gen = _standalone(u, doc)
    assert _gate_pairs_of_standalone(gen) == _pairs(g['reasons'])


def test_p3_conflict_standalone_gives_the_gate_reasons(tmp_path):
    """A conflict and an open reservation on D5 (the selected decision is demonstrated): the
    export shows D5 not demonstrated because of them; the standalone reasons are the gate's."""
    u = U(tmp_path)
    sid, _ = r5._conflict(u)
    g = gate(u)
    doc = r5._written(u, sid)
    gen = _standalone(u, doc)
    assert _gate_pairs_of_standalone(gen) == _pairs(g['reasons'])


def test_p7_standalone_without_selection_imports_the_gaps(tmp_path):
    """Without ``coverage_selection`` the export's gaps (its gate on the decisions shown, a
    virtual selection) are imported too, as CLI-CONTRACT §16 says."""
    u = U(tmp_path)
    sid = custom_flow(u, REQ, select=False)
    doc = r5._written(u, sid)
    assert doc['coverage_selection'] is None
    gen = _standalone(u, doc)
    gp = {(g['kind'], g['ref']) for g in doc['known_gaps']
          if g['kind'] not in ('external_unverified', 'source_unreadable')}
    assert ('peer_coverage_missing', 'D2') in gp
    assert gp <= _pairs(gen['gate_result']['reasons'])
    assert _gate_pairs_of_standalone(gen) == gp


def test_standalone_status_rule_reads_the_recorded_status():
    """Unit check of the rule on the committed export: a dimension shown ``needs_review``
    whose decision the export lists as ``demonstrated`` is not ``dimension_not_demonstrated``
    (unless the export's gate said so); one the export lists as ``to_consolidate`` is; a
    decision of another session shown ``needs_review`` with no other reason of the export's
    gate on the dimension is too (nothing else explains the status)."""
    import copy
    doc = r5._fixture_doc()
    policy = doc['policy']
    dim = next(d for d in doc['dimensions'] if d['human_review_ref'])

    def pairs(d):
        return _pairs(vf._gate_on_export(d, policy, r5.AXES)['reasons'])
    d = copy.deepcopy(doc)
    x = next(x for x in d['dimensions'] if x['id'] == dim['id'])
    x['status'] = 'needs_review'
    d['known_gaps'].append({'kind': 'open_reservation', 'ref': dim['id']})
    assert ('dimension_not_demonstrated', dim['id']) not in pairs(d)
    for s in d['decisions_summary']:
        if s['decision_ref'] == dim['human_review_ref']:
            s['status'] = 'to_consolidate'
    assert ('dimension_not_demonstrated', dim['id']) in pairs(d)
    d = copy.deepcopy(doc)
    x = next(x for x in d['dimensions'] if x['id'] == dim['id'])
    x['status'] = 'needs_review'
    d['decisions_summary'] = [s for s in d['decisions_summary']
                              if s['decision_ref'] != dim['human_review_ref']]
    assert ('dimension_not_demonstrated', dim['id']) in pairs(d)


# --- R6-2: local mode judges the verified tree too -------------------------------------------

def test_p4_local_gate_reads_the_verified_commit(tmp_path):
    """verify-export --target COMMIT --study, where the commit's imputer differs from the
    snapshot but the working tree (which the study's gate reads) is back to it: the gate's
    reasons are ``check``'s, plus ``public_sources_stale`` of the verified commit, so the
    result blocks and the export does not conform."""
    u = U(tmp_path)
    sid = custom_flow(u, REQ)
    r5._written(u, sid)
    ukit.git(u.repo, 'add', '--', 'docs')
    ukit.git(u.repo, 'commit', '-q', '-m', 'export')
    (u.repo / 'src/transforms.py').write_text('def fit_imputer(train):\n    return 0\n')
    ukit.git(u.repo, 'commit', '-q', '-am', 'change the imputer')
    head = ukit.git(u.repo, 'rev-parse', 'HEAD')
    ukit.git(u.repo, 'checkout', '-q', 'HEAD~1', '--', 'src/transforms.py')   # worktree back
    g = gate(u, '--policy-file', u.file('check.json', REQ))
    assert g['decision'] == 'allowed'
    out = cli.run(['understanding', 'verify-export', '--repo', str(u.repo), '--target', head,
                   '--policy-file', str(u.file('vp.json', REQ)), '--study',
                   str(u.study)]).payload
    gen = out['generations'][0]
    assert gen['public_source_freshness'] == 'stale'
    assert gen['gate_result']['decision'] == 'blocked'
    assert gen['gate_result']['target_tree_reasons'] == ['public_sources_stale']
    assert _pairs(gen['gate_result']['reasons']) - {('public_sources_stale', 'handoff')} \
        == _pairs(g['reasons'])
    assert gen['declared_conformity'] == 'nonconforming'
    assert gen['verified_repository']['is_session_repository'] is True
    # The commit of the export itself (the snapshot's sources) is current: allowed.
    gen = cli.run(['understanding', 'verify-export', '--repo', str(u.repo), '--target',
                   'HEAD~1', '--policy-file', str(u.file('vp.json', REQ)), '--study',
                   str(u.study)]).payload['generations'][0]
    assert gen['gate_result']['decision'] == 'allowed', gen['gate_result']['reasons']
    assert gen['declared_conformity'] == 'conforming'


def test_p6_generation_in_another_repository_is_blocked(tmp_path):
    """export write --repo OTHER (a clone whose imputer differs): the intent records where it
    was written (a local path, never in the artefact); verify-export --study on OTHER at its
    HEAD blocks with ``public_sources_stale`` and ``verified_repository_not_the_session_one``
    (it gave the recorded repository's gate: allowed, conforming)."""
    u = U(tmp_path)
    sid = custom_flow(u, REQ)
    other = tmp_path / 'other'
    ukit.git(tmp_path, 'clone', '-q', str(u.repo), str(other))
    (other / 'src/transforms.py').write_text('def fit_imputer(train):\n    return 42\n')
    ukit.git(other, *GIT_ID, 'commit', '-q', '-am', 'another imputer')
    ukit.approve_all(u, sid)
    w = u.m('export', 'write', '--session', sid, '--repo', other)
    intent = u.ext()['exports'][w['receipt']['intent_id']]
    assert intent['repository'] == str(other.resolve())
    raw = (other / ex.EXPORT_DIR / w['review_id'] / ex.JSON_FILE).read_text()
    assert str(other) not in raw and str(tmp_path) not in raw
    ukit.git(other, 'add', '--', 'docs')
    ukit.git(other, *GIT_ID, 'commit', '-q', '-m', 'export')
    out = cli.run(['understanding', 'verify-export', '--repo', str(other), '--target', 'HEAD',
                   '--policy-file', str(u.file('vp.json', REQ)), '--study',
                   str(u.study)]).payload
    gen = out['generations'][0]
    assert gen['public_integrity'] == 'valid'
    assert gen['gate_result']['decision'] == 'blocked'
    codes = {r['code'] for r in gen['gate_result']['reasons']}
    assert {'public_sources_stale', vf.OTHER_REPOSITORY} <= codes
    assert gen['declared_conformity'] == 'nonconforming'
    vr = gen['verified_repository']
    assert vr['is_session_repository'] is False and vr['is_written_repository'] is True


def test_clone_with_the_same_sources_is_a_limitation_only(tmp_path):
    """A clone of the repository holding the committed export and the snapshot's sources:
    the verified repository is not the session's, which is a limitation (the verified tree's
    public sources are the snapshot's), and the result is the study's gate (allowed)."""
    u = U(tmp_path)
    sid = custom_flow(u, REQ)
    r5._written(u, sid)
    ukit.git(u.repo, 'add', '--', 'docs')
    ukit.git(u.repo, 'commit', '-q', '-m', 'export')
    clone = tmp_path / 'clone'
    ukit.git(tmp_path, 'clone', '-q', str(u.repo), str(clone))
    gen = cli.run(['understanding', 'verify-export', '--repo', str(clone), '--target', 'HEAD',
                   '--study', str(u.study)]).payload['generations'][0]
    assert gen['public_source_freshness'] == 'current'
    assert gen['gate_result']['decision'] == gate(u)['decision'] == 'allowed'
    assert vf.OTHER_REPOSITORY in gen['gate_result']['limitations']
    assert vf.OTHER_REPOSITORY in gen['limitations']
    assert vf.OTHER_REPOSITORY not in {r['code'] for r in gen['gate_result']['reasons']}
    assert gen['verified_repository']['is_session_repository'] is False
    assert gen['verified_repository']['is_written_repository'] is False


def test_waiver_holds_on_the_judged_tree_not_on_another_commit(tmp_path):
    """A waiver covers the D5 staleness check judged on the working tree. Verifying that
    working tree, or a commit holding the same bytes, gives check's ``allowed_by_waiver``
    (R5-9 kept: the tree's change is the one the gate judged per dimension). A commit whose
    imputer is a third version, which check never read, adds ``public_sources_stale``: the
    waiver does not cover it (``waiver_not_accepted``, no ``waiver_ref``)."""
    u = U(tmp_path)
    sid, _ = r5._waiver(u)
    g = gate(u)
    assert g['decision'] == 'allowed_by_waiver'
    doc = r5._written(u, sid)
    pol_ = doc['policy']
    gen = r5._verify(u, pol_)['generations'][0]
    assert gen['public_source_freshness'] == 'stale'
    assert gen['public_sources_judged_by_study'] is True
    assert gen['gate_result']['decision'] == 'allowed_by_waiver'
    assert gen['gate_result']['waiver_ref'] == g['waiver_ref']
    ukit.git(u.repo, 'add', '--', 'docs', 'src/transforms.py')
    ukit.git(u.repo, 'commit', '-q', '-m', 'export and the waived change')
    gen = r5._verify(u, pol_, target='HEAD')['generations'][0]
    assert gen['public_sources_judged_by_study'] is True
    assert gen['gate_result']['decision'] == 'allowed_by_waiver'
    waived = (u.repo / 'src/transforms.py').read_text()
    (u.repo / 'src/transforms.py').write_text('def fit_imputer(train):\n    return 7\n')
    ukit.git(u.repo, 'commit', '-q', '-am', 'a third imputer')
    (u.repo / 'src/transforms.py').write_text(waived)          # check reads this again
    assert gate(u)['decision'] == 'allowed_by_waiver'
    gen = r5._verify(u, pol_, target='HEAD')['generations'][0]
    assert gen['public_sources_judged_by_study'] is False
    res = gen['gate_result']
    assert res['decision'] == 'blocked' and res['waiver_ref'] is None
    assert res['target_tree_reasons'] == ['public_sources_stale']
    codes = [r['code'] for r in res['reasons']]
    assert 'waiver_not_accepted' in codes and 'waived_requirements' not in res['limitations']
    assert _pairs(res['reasons']) - {('public_sources_stale', 'handoff'),
                                     ('waiver_not_accepted', 'handoff')} == _pairs(g['reasons'])


def test_p5_second_active_session_agrees_with_check(tmp_path):
    """The selection maps S1's decisions; S2 (same person and profile, active, nothing
    reviewed) shows those decisions, and its export, ``check`` and the verifier agree."""
    u = U(tmp_path)
    custom_flow(u, REQ)
    _, out = u.start()
    s2 = out['result']['session_id']
    g = gate(u)
    assert g['decision'] == 'allowed'
    prev = u.call('export', 'preview', '--session', s2, '--repo', u.repo)
    assert r5._gap_pairs(prev['known_gaps']) == _pairs(g['reasons']) == set()
    doc = r5._written(u, s2)
    sel = u.ext()['selections']
    latest = max(sel.values(), key=lambda s: s['recorded_revision'])
    shown = {d['id']: d['human_review_ref'] for d in doc['dimensions']}
    assert {k: v for k, v in shown.items() if k in latest['dimension_decision_map']} == \
        latest['dimension_decision_map']
    gen = r5._verify(u, REQ)['generations'][0]
    assert gen['gate_result']['decision'] == 'allowed'
    assert _pairs(gen['gate_result']['reasons']) == _pairs(g['reasons'])


# --- R6-3: a missing stored payload ------------------------------------------------------------

@pytest.mark.parametrize('blob', ['snapshot_blob', 'plan_blob', 'policy_blob'])
def test_p8_missing_session_payload_in_local_verify(tmp_path, blob):
    """CLI-CONTRACT §16: a stored payload the gate needs gone -> gate_result null,
    declared_conformity unknown, study_gate_unavailable; never an invalid generation."""
    u = U(tmp_path)
    sid = custom_flow(u, REQ)
    r5._written(u, sid)
    sha = u.ext()['sessions'][sid][blob]
    (StudyStore(u.study).home / BLOBS_DIR / sha).unlink()
    out = cli.run(['understanding', 'verify-export', '--repo', str(u.repo), '--target',
                   'worktree', '--study', str(u.study)]).payload
    gen = out['generations'][0]
    assert gen['public_integrity'] == 'valid', gen['problems']
    assert gen['study_binding'] == 'verified'
    assert gen['gate_result'] is None
    assert gen['declared_conformity'] == 'unknown'
    assert gen['study_gate_unavailable'] == ['evidence_unavailable']
    # The private context needs the plan and the snapshot, not the session's policy.
    assert gen['private_context_verification'] == (
        'verified' if blob == 'policy_blob' else 'unknown')
    assert gen['private_context_changed'] is (False if blob == 'policy_blob' else None)
