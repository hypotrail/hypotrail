"""Review round 7 (areas C and D): exports that show decisions of another session.

An export of session S2 may show decisions of another session S1 (the selection maps them).
Local verification now compares the verified tree with every session whose decisions or
context the gate judged (R7-1), the export's public scope covers the sources the shown
decisions depend on (R7-2), and the export intent records every repository the generation
was written to (R7-3).

The reviewer's probes ``q1``, ``q1b`` and ``q4`` are ported with the expected outcome of each
fix (``q1`` and ``q1b`` failed on round 6; ``q4`` passed and now also asserts ``written_to``).
The cross-session states of the round-5 invariant live in
``test_review_round5_cd.test_one_judgement_one_gap_list_cross_session``. Simulated humans
only; everything lives in ``tmp_path``.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import advkit  # noqa: E402,F401
from advkit import U, ukit, gate, custom_flow  # noqa: E402
from mlkit.study import cli  # noqa: E402
from mlkit.study import cmd_understanding as cu  # noqa: E402
from mlkit.study.understanding import export as ex  # noqa: E402
from mlkit.study.understanding import verify as vf  # noqa: E402

REQ = ukit.policy(mode='required')
NARROW = [s for s in ukit.SOURCES if s['path'] == 'src/pipeline.py']
GIT_ID = ('-c', 'user.name=T', '-c', 'user.email=t@example.invalid')
OTHER_IMPUTER = 'def fit_imputer(train):\n    return 0\n'


def _pairs(reasons):
    return {(r['code'], r.get('dimension') or 'handoff') for r in reasons
            if r['code'] != 'no_required_check'}


def _verify(u, target='worktree', repo=None, policy=None, study=True):
    args = ['understanding', 'verify-export', '--repo', str(repo or u.repo), '--target', target]
    if policy is not None:
        args += ['--policy-file', str(u.file(f'vp-{u.n}-{target}.json', policy))]
    if study:
        args += ['--study', str(u.study)]
    u.n += 1
    return cli.run(args).payload


def _write(u, sid, repo=None):
    ukit.approve_all(u, sid)
    w = u.m('export', 'write', '--session', sid, '--repo', repo or u.repo)
    doc = json.loads(((repo or u.repo) / ex.EXPORT_DIR / w['review_id'] / ex.JSON_FILE)
                     .read_text())
    return w, doc


def _scope_paths(doc):
    return sorted(e['path'] for e in doc['public_source_scope']['entries'] if e['path'])


# --- R7-1 and R7-2: probe q1 ------------------------------------------------------------------

def test_q1_narrow_scope_second_session(tmp_path):
    """S1 is selected (sources: pipeline, imputer, security rule); S2 of the same person and
    profile maps only the pipeline, and its export shows S1's decisions. A commit changes the
    imputer and the working tree is reverted, so ``check`` reads the snapshot's bytes and
    allows. Round 6 allowed HEAD: the export's scope (S2's) did not map the imputer, and the
    verified tree was compared with S2's sources only. Now the scope covers S1's sources
    (R7-2) and HEAD is compared with S1's too (R7-1): HEAD blocks, as ``check`` does on the
    commit's bytes; the standalone verifier says stale and never allowed."""
    u = U(tmp_path)
    s1 = custom_flow(u, REQ)
    _, out = u.start(sources=NARROW)
    s2 = out['result']['session_id']
    assert gate(u)['decision'] == 'allowed'
    w, doc = _write(u, s2)
    assert {d['human_review_ref'] for d in doc['dimensions']} <= {
        d['decision_id'] for d in u.ext()['decisions'].values() if d['session_id'] == s1}
    # R7-2: the public scope covers the imputer S1's decisions depend on.
    assert _scope_paths(doc) == ['SECURITY.md', 'src/pipeline.py', 'src/transforms.py']
    assert not [g for g in doc['known_gaps'] if g['kind'] == ex.SCOPE_GAP]
    ukit.git(u.repo, 'add', '--', 'docs')
    ukit.git(u.repo, 'commit', '-q', '-m', 'export')
    (u.repo / 'src/transforms.py').write_text(OTHER_IMPUTER)
    ukit.git(u.repo, 'commit', '-q', '-am', 'change the imputer')
    head = ukit.git(u.repo, 'rev-parse', 'HEAD')
    ukit.git(u.repo, 'checkout', '-q', 'HEAD~1', '--', 'src/transforms.py')
    assert gate(u)['decision'] == 'allowed'                 # check reads the reverted tree
    gen = _verify(u, target=head)['generations'][0]
    assert gen['public_integrity'] == 'valid', gen['problems']
    assert gen['public_source_freshness'] == 'stale'
    assert gen['public_sources_judged_by_study'] is False
    assert gen['gate_result']['decision'] == 'blocked'
    assert gen['gate_result']['target_tree_reasons'] == ['public_sources_stale']
    assert gen['declared_conformity'] == 'nonconforming'
    lines = {x['session_id']: x for x in gen['verified_repository']['judged_sessions']}
    assert set(lines) == {s1, s2}
    assert lines[s2]['same_bytes'] is True and lines[s2]['tree_freshness'] == 'current'
    assert lines[s1]['same_bytes'] is False and lines[s1]['tree_freshness'] == 'stale'
    sa = _verify(u, target=head, study=False, policy=doc['policy'])['generations'][0]
    assert sa['public_source_freshness'] == 'stale'
    assert sa['gate_result']['decision'] == 'blocked'
    assert sa['declared_conformity'] != 'conforming'
    assert ('public_sources_stale', 'handoff') in _pairs(sa['gate_result']['reasons'])
    # check on the commit's bytes blocks too: verify and check agree.
    ukit.git(u.repo, 'checkout', '-q', head, '--', 'src/transforms.py')
    g2 = gate(u)
    assert g2['decision'] == 'blocked' and ('stale', 'D5') in _pairs(g2['reasons'])
    # On the very bytes check read, local verification is check's result again, plus
    # (review round 9, R9CD-1) ``exported_content_not_current``: the generation shows D5
    # current, which the study no longer exports. Round 7 asserted no target-tree reason
    # at all; that is what R9CD-1 proved wrong (the old content was verified as is).
    gen = _verify(u, target=head)['generations'][0]
    assert gen['public_sources_judged_by_study'] is True
    assert gen['exported_content_current'] is False
    assert gen['gate_result']['target_tree_reasons'] == [vf.CONTENT_NOT_CURRENT]
    assert _pairs(gen['gate_result']['reasons']) == \
        _pairs(g2['reasons']) | {(vf.CONTENT_NOT_CURRENT, 'handoff')}


def test_q1b_second_session_in_a_clone(tmp_path):
    """S1 (repository A) is selected; S2 of the same person and profile is started on a
    clone B with the same mapped sources and exported there. B's imputer is changed and
    committed with the export. ``check`` reads A (S1's decisions) and allows. Round 6
    compared B's HEAD with B's working tree only (S2's repository) and allowed; now B's HEAD
    is compared with A for S1's sources (R7-1): blocked, with
    ``verified_repository_not_the_session_one`` for S1's repository."""
    u = U(tmp_path)
    s1 = custom_flow(u, REQ)
    a = u.repo
    b = tmp_path / 'clone'
    ukit.git(tmp_path, 'clone', '-q', str(a), str(b))
    u.repo = b
    _, out = u.start()
    s2 = out['result']['session_id']
    w, doc = _write(u, s2, repo=b)
    ukit.git(b, 'add', '--', 'docs')
    (b / 'src/transforms.py').write_text(OTHER_IMPUTER)
    ukit.git(b, *GIT_ID, 'commit', '-q', '-am', 'export and another imputer')
    assert gate(u)['decision'] == 'allowed'
    gen = _verify(u, target='HEAD', repo=b)['generations'][0]
    assert gen['public_source_freshness'] == 'stale'
    assert gen['public_sources_judged_by_study'] is False
    res = gen['gate_result']
    assert res['decision'] == 'blocked', 'stale verified tree, allowed'
    assert set(res['target_tree_reasons']) == {'public_sources_stale', vf.OTHER_REPOSITORY}
    assert gen['declared_conformity'] == 'nonconforming'
    vr = gen['verified_repository']
    assert vr['is_session_repository'] is True              # S2's own repository is B
    assert vr['is_written_repository'] is True
    lines = {x['session_id']: x for x in vr['judged_sessions']}
    assert lines[s1]['is_verified_repository'] is False
    assert lines[s1]['repository'] == str(a.resolve())
    assert lines[s1]['same_bytes'] is False
    sa = _verify(u, target='HEAD', repo=b, study=False, policy=doc['policy'])['generations'][0]
    assert sa['gate_result']['decision'] == 'blocked'
    assert sa['declared_conformity'] != 'conforming'


def test_clone_unchanged_is_a_limitation_for_every_session(tmp_path):
    """The same layout without a change: B's HEAD holds the bytes A's working tree has for
    every source of S1 and S2; the result is check's (allowed), and S1's other repository is
    a limitation, never a blocking reason."""
    u = U(tmp_path)
    custom_flow(u, REQ)
    b = tmp_path / 'clone'
    ukit.git(tmp_path, 'clone', '-q', str(u.repo), str(b))
    u.repo = b
    _, out = u.start()
    s2 = out['result']['session_id']
    _write(u, s2, repo=b)
    ukit.git(b, 'add', '--', 'docs')
    ukit.git(b, *GIT_ID, 'commit', '-q', '-m', 'export')
    gen = _verify(u, target='HEAD', repo=b)['generations'][0]
    assert gen['public_source_freshness'] == 'current'
    assert gen['public_sources_judged_by_study'] is True
    assert gen['gate_result']['decision'] == gate(u)['decision'] == 'allowed'
    assert gen['gate_result']['target_tree_reasons'] == []
    assert vf.OTHER_REPOSITORY in gen['gate_result']['limitations']
    assert vf.OTHER_REPOSITORY not in {r['code'] for r in gen['gate_result']['reasons']}


def test_scope_conflict_is_a_gap_and_never_current(tmp_path):
    """S1 captured the imputer; the imputer changes; S2 starts and captures the new bytes
    under the same logical key. One scope cannot hold both digests, so the export keeps S2's
    entry and records ``scope_does_not_cover_shown_decision`` for every dimension it shows
    from S1 (R7-2). The standalone verifier then reads the public sources ``unknown`` (never
    ``current``, although the tree holds S2's bytes) and never allows, as check blocks."""
    u = U(tmp_path)
    s1 = custom_flow(u, REQ)
    (u.repo / 'src/transforms.py').write_text(OTHER_IMPUTER)
    _, out = u.start()
    s2 = out['result']['session_id']
    g = gate(u)
    assert g['decision'] == 'blocked' and ('stale', 'D5') in _pairs(g['reasons'])
    w, doc = _write(u, s2)
    shown = {d['id'] for d in doc['dimensions'] if d['human_review_ref'] in {
        x['decision_id'] for x in u.ext()['decisions'].values() if x['session_id'] == s1}}
    assert shown
    gaps = {g_['ref'] for g_ in doc['known_gaps'] if g_['kind'] == ex.SCOPE_GAP}
    assert gaps == shown
    sa = _verify(u, study=False, policy=doc['policy'])['generations'][0]
    assert sa['public_integrity'] == 'valid', sa['problems']
    assert sa['public_source_freshness'] == 'unknown'
    assert sa['gate_result']['decision'] == 'blocked'
    assert sa['declared_conformity'] != 'conforming'
    # The export-only gap is not a reason of the gate's (no such code in check).
    assert ex.SCOPE_GAP not in {r['code'] for r in sa['gate_result']['reasons']}
    # Local: the working tree is what check read for both sessions: check's result.
    gen = _verify(u)['generations'][0]
    assert gen['public_sources_judged_by_study'] is True
    assert gen['gate_result']['decision'] == 'blocked'
    assert _pairs(gen['gate_result']['reasons']) == _pairs(g['reasons'])


def test_single_session_scope_is_unchanged(tmp_path):
    """An export showing only its own session's decisions keeps that session's public scope
    exactly (the union adds nothing; the committed fixture's bytes are unchanged)."""
    u = U(tmp_path)
    sid = custom_flow(u, REQ)
    w, doc = _write(u, sid)
    from mlkit.study.store import StudyStore
    from mlkit.study.understanding import canonical
    store = StudyStore(u.study)
    session = u.ext()['sessions'][sid]
    own = canonical.loads(store.read_blob(session['snapshot_blob']))['public']
    assert doc['public_source_scope'] == own
    assert doc['source_scope_digest'] == session['source_scope_digest']


# --- R7-3 and probe q4 -------------------------------------------------------------------------

def test_q4_no_leak_and_every_written_repository(tmp_path):
    """The same generation written to a clone (with ``--latest``) then to the session's
    repository: no answer text, salt or local path in the files written to either; the
    intent lists both places (local state only), and local verification of either says it is
    a repository the generation was written to (round 6 recorded the first place only)."""
    u = U(tmp_path)
    sid = custom_flow(u, REQ)
    other = tmp_path / 'other'
    ukit.git(tmp_path, 'clone', '-q', str(u.repo), str(other))
    ukit.approve_all(u, sid)
    first = u.m('export', 'write', '--session', sid, '--repo', other, '--latest')
    w, doc = _write(u, sid)
    assert w['review_id'] == first['review_id']
    salt = u.ext()['salt']
    bad = [str(tmp_path), salt, 'My own answer', 'The imputer in src/transforms.py learns']
    for repo in (u.repo, other):
        for p in (repo / 'docs').rglob('*'):
            if p.is_file():
                t = p.read_text(errors='replace')
                assert not [b for b in bad if b in t], p
    intents = [x for x in u.ext()['exports'].values() if x['review_id'] == w['review_id']]
    assert len(intents) == 1
    places = [str(other.resolve()), str(u.repo.resolve())]
    assert intents[0]['repositories'] == places
    assert intents[0]['repository'] == places[0]
    for repo in (other, u.repo):
        gen = _verify(u, repo=repo)['generations'][0]
        vr = gen['verified_repository']
        assert vr['written_to'] == places
        assert vr['is_written_repository'] is True
    # A third write to the same place records nothing new.
    u.m('export', 'write', '--session', sid, '--repo', u.repo)
    assert [x['repositories'] for x in u.ext()['exports'].values()
            if x['review_id'] == w['review_id']] == [places]


def test_written_repositories_of_older_intents():
    """An intent of round 6 (one ``repository``) and one recorded before round 6 (none)."""
    assert cu.written_repositories({'repository': '/a'}) == ['/a']
    assert cu.written_repositories({'repository': '/a', 'repositories': ['/a', '/b']}) == \
        ['/a', '/b']
    assert cu.written_repositories({}) == []
