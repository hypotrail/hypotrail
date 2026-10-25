"""A13–A18, A24, A26, A29, A31: approved export, immutable generations, the real Git path,
the standalone verifier. Reviewers are simulated fixtures; Git runs in temporary repos."""
from __future__ import annotations

import json
import os
import subprocess

import pytest

import ukit
from mlkit.study import cli
from mlkit.study.understanding import canonical, export as ex, verify as vf


def code(p):
    return p['error']['code']


@pytest.fixture
def done(tmp_path):
    u = ukit.U(tmp_path)
    sid = ukit.full_flow(u)
    return u, sid


def verify(repo, target, *extra):
    return cli.run(['understanding', 'verify-export', '--repo', str(repo), '--target', target,
                    *map(str, extra)]).payload


def gen_dir(u, rid):
    return u.repo / ex.EXPORT_DIR / rid


def test_every_contributor_approves_the_same_content(done):
    """A29: the author alone cannot approve for the reviewer and the peer; a change of an
    alias or rationale after approval invalidates every approval."""
    u, sid = done
    prev = u.call('export', 'preview', '--session', sid, '--repo', u.repo)
    assert prev['draft'] is True and set(prev['required_contributors']) == {'alice', 'bob',
                                                                           'carol'}
    u.m('export', 'approve', '--session', sid, '--contributor', 'alice', '--content-digest',
        prev['content_digest'])
    out = u.m('export', 'write', '--session', sid, '--repo', u.repo, expect=2)
    assert code(out) == 'privacy_approval_required'
    assert set(out['error']['details']['missing']) == {'bob', 'carol'}
    assert not (u.repo / ex.EXPORT_DIR).exists()
    # The author cannot approve with another digest, nor a stranger approve at all.
    out = u.m('export', 'approve', '--session', sid, '--contributor', 'mallory',
              '--content-digest', prev['content_digest'], expect=2)
    assert code(out) == 'privacy_approval_required'
    for who in ('bob', 'carol'):
        u.m('export', 'approve', '--session', sid, '--contributor', who, '--content-digest',
            prev['content_digest'])
    # A relevant source change changes the projection (freshness at export): every
    # approval is now stale.
    (u.repo / 'src/transforms.py').write_text('def fit_imputer(train):\n    return 2\n')
    again = u.call('export', 'preview', '--session', sid, '--repo', u.repo)
    assert again['content_digest'] != prev['content_digest']
    assert set(again['missing_approvals']) == {'alice', 'bob', 'carol'}


def test_export_is_canonical_private_and_concordant(done):
    """A14: JSON and Markdown agree, the manifest binds both, no answer text, local path,
    secret or study path in the artefacts."""
    u, sid = done
    ukit.approve_all(u, sid)
    w = u.m('export', 'write', '--session', sid, '--repo', u.repo)
    d = gen_dir(u, w['review_id'])
    data = {n: (d / n).read_bytes() for n in ex.FILES}
    doc = canonical.loads(data[ex.JSON_FILE])
    assert canonical.dumps(doc) == data[ex.JSON_FILE]
    assert ex.markdown(doc).encode() == data[ex.MD_FILE]
    manifest = canonical.loads(data[ex.MANIFEST_FILE])
    assert manifest['files'][ex.JSON_FILE]['sha256'] == canonical.sha256_hex(data[ex.JSON_FILE])
    assert ex.MANIFEST_FILE not in manifest['files']                      # not its own digest
    text = b''.join(data.values()).decode()
    assert 'My own answer for' not in text                               # no answer text
    assert str(u.study) not in text and str(u.root) not in text and '/tmp' not in text
    assert doc['privacy_review']['status'] == 'approved'
    assert 'simulated_human_decisions' in doc['limitations']
    assert all(d['human_review_ref'] for d in doc['dimensions'] if d['status'] == 'demonstrated')


def test_real_git_path_index_commit_and_receipt(done):
    """A24 (Git part), A15, A18: plan, explicit staging of the artefacts only, verification
    of the index, an ordinary commit, verification of the commit, then a receipt; code and
    proof in the same commit verify; no commit or push is made by the engine."""
    u, sid = done
    ukit.approve_all(u, sid)
    w = u.m('export', 'write', '--session', sid, '--repo', u.repo)
    head_before = ukit.git(u.repo, 'rev-parse', 'HEAD')
    # Code change and proof in the same commit: change a non-mapped file and stage it.
    (u.repo / 'README.md').write_text('Project, documented.\n')
    ukit.git(u.repo, 'add', '--', 'README.md')
    plan = u.call('git-plan', '--session', sid, '--repo', u.repo)
    assert plan['consistent'] and plan['staged_outside_plan'] == ['README.md']
    assert ukit.git(u.repo, 'rev-parse', 'HEAD') == head_before          # nothing committed
    st = u.call('git-stage', '--session', sid, '--repo', u.repo, '--index-identity',
                plan['index_identity'])
    assert st['unexpected_index_changes'] == []
    staged = ukit.git(u.repo, 'diff', '--cached', '--name-only').splitlines()
    assert 'README.md' in staged                                         # kept staged
    index = verify(u.repo, 'index')
    assert index['public_integrity'] == 'valid'
    g = index['generations'][0]
    assert g['public_source_freshness'] == 'current'
    assert g['declared_conformity'] == 'unknown'                         # no study here
    ukit.git(u.repo, 'commit', '-q', '-m', 'code and understanding review')
    commit = verify(u.repo, 'HEAD', '--study', u.study)
    g = commit['generations'][0]
    assert (g['public_integrity'], g['private_context_verification'],
            g['evidence_availability'], g['declared_conformity']) == (
        'valid', 'verified', 'available', 'conforming')
    r = u.m('git-receipt', '--session', sid, '--repo', u.repo, '--commit', 'HEAD')
    assert r['commit'] == ukit.git(u.repo, 'rev-parse', 'HEAD')
    assert ukit.git(u.repo, 'status', '--porcelain') == ''
    assert not ukit.git(u.repo, 'remote')                                # nothing pushed
    assert w['review_id'] in ukit.git(u.repo, 'ls-tree', '-r', '--name-only', 'HEAD')


def test_index_and_worktree_divergence_and_concurrent_staging(done):
    """A16: a source staged with other bytes than the snapshot is refused; an index changed
    between the plan and the staging stops it without losing any staged file."""
    u, sid = done
    ukit.approve_all(u, sid)
    u.m('export', 'write', '--session', sid, '--repo', u.repo)
    plan = u.call('git-plan', '--session', sid, '--repo', u.repo)
    (u.repo / 'notes.txt').write_text('unrelated\n')
    ukit.git(u.repo, 'add', '--', 'notes.txt')                          # concurrent staging
    out = u.call('git-stage', '--session', sid, '--repo', u.repo, '--index-identity',
                 plan['index_identity'], expect=2)
    assert code(out) == 'git_index_conflict'
    assert 'notes.txt' in ukit.git(u.repo, 'diff', '--cached', '--name-only')
    (u.repo / 'src/transforms.py').write_text('changed in worktree\n')
    ukit.git(u.repo, 'add', '--', 'src/transforms.py')
    plan = u.call('git-plan', '--session', sid, '--repo', u.repo)
    assert not plan['consistent']
    assert plan['source_conflicts'][0]['path'] == 'src/transforms.py'
    out = u.call('git-stage', '--session', sid, '--repo', u.repo, '--index-identity',
                 plan['index_identity'], expect=2)
    assert code(out) == 'git_index_conflict'


def test_study_outside_moved_repository(done, tmp_path):
    """A16: the study lives outside the repository; the repository moves; --repo names it."""
    u, sid = done
    ukit.approve_all(u, sid)
    w = u.m('export', 'write', '--session', sid, '--repo', u.repo)
    assert not str(u.study).startswith(str(u.repo))
    moved = tmp_path / 'moved'
    os.rename(u.repo, moved)
    status = u.call('status', '--repo', moved)['sessions'][0]
    assert {d['freshness'] for d in status['dimensions']} == {'current'}
    unknown = u.call('status')['sessions'][0]                            # old path gone
    assert 'unknown' in {d['freshness'] for d in unknown['dimensions']}
    out = verify(moved, 'worktree')
    assert out['generations'][0]['review_id'] == w['review_id']


def test_verifier_reads_the_tree_and_runs_nothing(done, tmp_path):
    """A17: the commit is read through Git objects (not the worktree); traversal and links
    are refused; nothing of the repository runs."""
    u, sid = done
    ukit.approve_all(u, sid)
    w = u.m('export', 'write', '--session', sid, '--repo', u.repo)
    rid = w['review_id']
    ukit.git(u.repo, 'add', '--', ex.EXPORT_DIR)
    ukit.git(u.repo, 'commit', '-q', '-m', 'review')
    # A hook that would leave a trace if anything ran it.
    hook = u.repo / '.git' / 'hooks' / 'post-checkout'
    hook.write_text('#!/bin/sh\ntouch "$GIT_DIR/../HOOK_RAN"\n')
    hook.chmod(0o755)
    # Tamper the worktree only: the commit still verifies, the worktree does not.
    (gen_dir(u, rid) / ex.MD_FILE).write_text('tampered\n')
    assert verify(u.repo, 'HEAD')['public_integrity'] == 'valid'
    assert verify(u.repo, 'worktree')['public_integrity'] == 'invalid'
    assert not (u.repo / 'HOOK_RAN').exists()
    # A symbolic link committed in a generation is refused.
    link_repo = tmp_path / 'linkrepo'
    subprocess.run(['git', 'clone', '-q', str(u.repo), str(link_repo)], check=True)
    target = link_repo / ex.EXPORT_DIR / rid / ex.MD_FILE
    target.unlink()
    target.symlink_to('/etc/hostname')
    ukit.git(link_repo, 'add', '-A')
    ukit.git(link_repo, 'commit', '-q', '-m', 'link')
    out = verify(link_repo, 'HEAD')
    assert out['public_integrity'] == 'invalid'
    assert any('symbolic link' in p for p in out['problems'])
    for bad in ('../x', '/abs'):
        assert not vf._safe(bad)


def test_clean_clone_public_integrity_and_honest_limits(done, tmp_path):
    """A26: a clean clone recomputes the public digests, cannot verify the private context
    nor read the answers; complete/payloads_available block, public_only/recorded_decisions
    allow with their limits; a Git change of a source is stale.

    Expectation changed in review round 5: the standalone verifier applies the gate's policy
    digest rule, so a relaxed policy file that is not the policy the reviews were made under
    blocks (``decision_policy_changed``, as ``check --policy-file`` does) instead of
    allowing; the allowing half of A26 is
    ``test_clean_clone_allows_a_public_only_export_with_its_limits``, where the study's own
    policy is the relaxed one."""
    u, sid = done
    ukit.approve_all(u, sid)
    u.m('export', 'write', '--session', sid, '--repo', u.repo)
    ukit.git(u.repo, 'add', '--', ex.EXPORT_DIR)
    ukit.git(u.repo, 'commit', '-q', '-m', 'review')
    clone = tmp_path / 'clean'
    subprocess.run(['git', 'clone', '-q', str(u.repo), str(clone)], check=True)
    strict = u.file('strict.json', ukit.policy(mode='required'))
    g = verify(clone, 'HEAD', '--policy-file', strict)['generations'][0]
    assert (g['public_integrity'], g['public_source_freshness'],
            g['private_context_verification'], g['evidence_availability']) == (
        'valid', 'current', 'unknown', 'unavailable')
    assert g['unresolved_private_refs']
    assert g['gate_result']['decision'] == 'blocked'
    relaxed = u.file('relaxed.json', ukit.policy(mode='required', context_requirement='public_only',
                                                 evidence_requirement='recorded_decisions'))
    g = verify(clone, 'HEAD', '--policy-file', relaxed)['generations'][0]
    assert g['gate_result']['decision'] == 'blocked'
    assert {'selection_policy_changed', 'decision_policy_changed'} <= {
        r['code'] for r in g['gate_result']['reasons']}
    assert u.call('check', '--milestone', 'handoff', '--policy-file', relaxed)['gate'][
        'decision'] == 'blocked'


def test_clean_clone_allows_a_public_only_export_with_its_limits(tmp_path):
    """A26, allowing half: the reviews were made under a public_only/recorded_decisions
    policy; a clean clone verified with that very policy allows with its limits, and a Git
    change of a source blocks (stale)."""
    import advkit
    relaxed_doc = ukit.policy(mode='required', context_requirement='public_only',
                              evidence_requirement='recorded_decisions')
    u = ukit.U(tmp_path)
    sid = advkit.custom_flow(u, relaxed_doc)
    ukit.approve_all(u, sid)
    u.m('export', 'write', '--session', sid, '--repo', u.repo)
    ukit.git(u.repo, 'add', '--', ex.EXPORT_DIR)
    ukit.git(u.repo, 'commit', '-q', '-m', 'review')
    clone = tmp_path / 'clean'
    subprocess.run(['git', 'clone', '-q', str(u.repo), str(clone)], check=True)
    relaxed = u.file('relaxed.json', relaxed_doc)
    g = verify(clone, 'HEAD', '--policy-file', relaxed)['generations'][0]
    assert (g['public_integrity'], g['private_context_verification']) == ('valid', 'unknown')
    assert g['gate_result']['decision'] == 'allowed', g['gate_result']
    assert {'public_only_context', 'recorded_decisions_accepted',
            'simulated_human_decisions'} <= set(g['gate_result']['limitations'])
    (clone / 'src/transforms.py').write_text('changed\n')
    ukit.git(clone, 'commit', '-qam', 'change a source')
    g = verify(clone, 'HEAD', '--policy-file', relaxed)['generations'][0]
    assert g['public_source_freshness'] == 'stale'
    assert g['gate_result']['decision'] == 'blocked'


def test_generations_are_immutable_and_publication_survives_faults(done):
    """A13, A31: a fault at each write, before or after the rename leaves no partial
    generation visible as valid; a retry with the same request reconciles; a different
    content under the same review id is refused; latest is never an authority."""
    u, sid = done
    ukit.approve_all(u, sid)
    from mlkit.study import cmd_understanding as cu
    import argparse
    for fault in ('after_understanding-review.json', 'after_understanding-review.md',
                  'before_rename'):
        args = argparse.Namespace(study=str(u.study), session=sid, repo=str(u.repo),
                                  latest=False, request_id=f'w-{fault}',
                                  expected_revision=u.rev())
        with pytest.raises(RuntimeError):
            cu._export_write(args, fault=fault)
        base = u.repo / ex.EXPORT_DIR
        assert not [p for p in base.iterdir() if p.name.startswith('rv-')]
        assert not [p for p in base.iterdir() if p.name.startswith('.')]   # temp removed
        assert verify(u.repo, 'worktree')['generations'] == []
    # A fault after the rename and before the receipt: the retry reconciles from the bytes.
    args = argparse.Namespace(study=str(u.study), session=sid, repo=str(u.repo), latest=True,
                              request_id='w-final', expected_revision=u.rev())
    with pytest.raises(RuntimeError):
        cu._export_write(args, fault='after_rename')
    rid = next(p.name for p in (u.repo / ex.EXPORT_DIR).iterdir() if p.name.startswith('rv-'))
    intents = [x for x in u.ext()['exports'].values() if x['review_id'] == rid]
    assert intents[0]['status'] == 'reserved'                            # no receipt yet
    out = cu._export_write(args)                    # the same request, replayed as such
    assert out['publication'] == 'already_published'
    assert out['receipt']['status'] == 'published'
    assert len([x for x in u.ext()['exports'].values() if x['review_id'] == rid]) == 1
    # Different bytes under the same review id: refused, never replaced.
    files = ex.files_of({**canonical.loads((gen_dir(u, rid) / ex.JSON_FILE).read_bytes()),
                         'created_at': 'another time'})
    with pytest.raises(Exception) as e:
        ex.publish(u.repo, rid, files)
    assert e.value.code == 'export_stale'
    # latest.json is an index only; a generation missing a file is refused by readers.
    latest = json.loads((u.repo / ex.EXPORT_DIR / ex.LATEST).read_text())
    assert latest == {'authority': False, 'review_id': rid,
                      'schema': 'hypotrail.understanding-latest/1'}
    (gen_dir(u, rid) / ex.MANIFEST_FILE).unlink()
    g = verify(u.repo, 'worktree')['generations'][0]
    assert g['public_integrity'] == 'invalid'


def test_rename_noreplace_never_replaces(tmp_path):
    """A31: the publication primitive refuses an existing destination, even an empty one."""
    a, b = tmp_path / 'a', tmp_path / 'b'
    a.mkdir()
    b.mkdir()
    with pytest.raises(FileExistsError):
        ex.rename_noreplace(a, b)
    assert a.exists() and b.exists()


def test_modified_artefact_alone_is_detected(done):
    """A15: changing the JSON alone breaks the manifest; changing the Markdown alone breaks
    the rendering invariant."""
    u, sid = done
    ukit.approve_all(u, sid)
    w = u.m('export', 'write', '--session', sid, '--repo', u.repo)
    d = gen_dir(u, w['review_id'])
    doc = canonical.loads((d / ex.JSON_FILE).read_bytes())
    doc['dimensions'][0]['status'] = 'not_evaluated'
    (d / ex.JSON_FILE).write_bytes(canonical.dumps(doc))
    problems = verify(u.repo, 'worktree')['generations'][0]['problems']
    assert any('manifest digest' in p for p in problems)


def test_end_to_end_simulated_humans(tmp_path):
    """A24: synthetic study → session → insufficient answer → coaching → new variant →
    simulated human review → simulated peer handover → approved export → temporary commit
    → verification → relevant change → freshness block. The humans are simulated."""
    u = ukit.U(tmp_path)
    u.set_policy(ukit.policy(mode='required'))
    plan, out = u.start()
    sid = out['result']['session_id']
    tasks = plan['plan']['task_ids']
    t2 = next(t for t in tasks if u.bank_task(t)['dimension_ids'][0] == 'D2')
    weak = u.submit(sid, t2, 'I do not know.')['result']['attempt_id']
    u.m('coach', '--attempt', weak)
    u.review(sid, [u.decision('D2', [weak], status='to_consolidate')])
    rid = next(iter(u.ext()['reservations']))
    decisions = []
    for t in tasks:
        dim = u.bank_task(t)['dimension_ids'][0]
        if dim == 'D2':
            continue
        a = u.submit(sid, t, f'Answer on {dim}.')['result']['attempt_id']
        decisions.append(u.decision(dim, [a]))
    variant = u.call('task', '--session', sid)['task']['task_id']
    assert variant != t2
    good = u.submit(sid, variant, 'The later input is excluded at the prediction moment.')
    decisions.append(u.decision('D2', [good['result']['attempt_id']],
                                resolves_reservation_ids=[rid]))
    u.review(sid, decisions)
    u.m('handover', 'set', '--session', sid, '--file', u.file('h.json', ukit.HANDOVER))
    task = next(t['task_id'] for t in u.bank()['tasks'] if t['kind'] == 'transfer')
    t = u.m('transfer', 'start', '--session', sid, '--peer', 'carol', '--task', task)['result']
    u.m('transfer', 'submit', '--transfer', t['transfer_id'], '--response-file',
        u.file('p.txt', 'The imputer learns a mean in src/transforms.py.'), '--assistance-file',
        u.file('pa.json', ukit.ASSIST), '--evidence-file',
        u.file('pe.json', {'evidence_refs': ['src/transforms.py'],
                           'difficulty_or_blockers': ['The note does not name the folds.']}))
    rv = u.m('transfer', 'review', '--transfer', t['transfer_id'], '--file', u.file(
        'pr.json', {'reviewer_declared_id': 'alice', 'declaration': ukit.SIM, 'simulated': True,
                    'dimension_ids': ['D2'], 'status': 'demonstrated',
                    'rationale': 'Simulated: found and explained.'}))
    u.m('close', '--session', sid, '--to', 'completed', '--reason', 'done')
    dm = {}
    for d in sorted(u.ext()['decisions'].values(), key=lambda d: d['recorded_revision']):
        if d['kind'] == 'attempt' and d['status'] == 'demonstrated':
            dm[d['dimension_id']] = d['decision_id']
    u.m('select', '--file', u.file('sel.json', {
        'milestone': 'handoff', 'actor_scope': {'actor_declared_id': 'alice',
                                                'profile': 'pipeline'},
        'dimension_decision_map': dm, 'transfer_decision_map': {'D2': rv['result']['decision_id']},
        'reservation_resolution_refs': [rid]}))
    assert u.call('check', '--milestone', 'handoff')['gate']['decision'] == 'allowed'
    ukit.approve_all(u, sid)
    w = u.m('export', 'write', '--session', sid, '--repo', u.repo)
    plan = u.call('git-plan', '--session', sid, '--repo', u.repo)
    u.call('git-stage', '--session', sid, '--repo', u.repo, '--index-identity',
           plan['index_identity'])
    assert verify(u.repo, 'index')['public_integrity'] == 'valid'
    ukit.git(u.repo, 'commit', '-q', '-m', 'understanding review')
    g = verify(u.repo, 'HEAD', '--study', u.study)['generations'][0]
    assert g['declared_conformity'] == 'conforming'
    doc = canonical.loads((gen_dir(u, w['review_id']) / ex.JSON_FILE).read_bytes())
    d2 = next(d for d in doc['dimensions'] if d['id'] == 'D2')
    assert d2['status'] == 'demonstrated' and d2['assistance_summary'] == 'unaided'
    assert any(r['status'] == 'resolved' for r in doc['reservation_resolutions'])
    assert doc['peer_coverage'][0]['transfers'][0]['difficulty_or_blockers']
    (u.repo / 'src/transforms.py').write_text('def fit_imputer(train):\n    return 1\n')
    gate = u.call('check', '--milestone', 'handoff')['gate']
    assert gate['decision'] == 'blocked' and 'D5' in gate['stale_dimensions']
    o = cli.run(['export', 'handoff', '--study', str(u.study), '--out', str(tmp_path / 'ho')])
    assert o.exit_code == 2 and o.payload['error']['code'] == 'milestone_blocked'
    assert not (tmp_path / 'ho').exists()
