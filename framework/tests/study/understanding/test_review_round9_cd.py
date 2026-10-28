"""Review round 9 (areas C and D): the reviewer's probes, ported with the expected outcome of
each fix (R9CD-1 to R9CD-7).

* R9CD-1: a generation whose content is no longer what the study exports now is never
  verified ``allowed`` or ``conforming`` locally, and ``git-plan`` says so (``git-stage``
  refuses); unrelated study progress leaves the projection unchanged (R5-1 still holds).
* R9CD-2: a mapped source Git converts on its way to the index (``core.autocrlf``) is the
  conflict ``source_transformed_by_git``, with what to do.
* R9CD-3: a problem of the verified tree makes every generation invalid and blocked.
* R9CD-4: a ``not_current`` generation whose content is current again is revalidated by
  ``export write``; ``git-plan`` never falls back silently to older content.
* R9CD-5: ``--repo`` must be the top level of its Git work tree.
* R9CD-6: a case or Unicode variant of a mapped source is a problem of the tree.
* R9CD-7: a mapped source that becomes unreadable after ``start`` reads ``unknown``.

Simulated humans only; everything lives in ``tmp_path``.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import unicodedata
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import advkit  # noqa: E402,F401
from advkit import U, ukit, gate, custom_flow  # noqa: E402
from mlkit.study import cli  # noqa: E402
from mlkit.study import cmd_understanding as cu  # noqa: E402
from mlkit.study.understanding import export as ex  # noqa: E402
from mlkit.study.understanding import verify as vf  # noqa: E402

REQ = ukit.policy(mode='required')


def _verify(u, target, study=True, policy=None, repo=None):
    args = ['understanding', 'verify-export', '--repo', str(repo or u.repo), '--target', target]
    if study:
        args += ['--study', str(u.study)]
    if policy is not None:
        args += ['--policy-file', str(u.file(f'vp-{u.n}.json', policy))]
        u.n += 1
    return cli.run(args).payload


def _codes(result) -> list:
    return [r['code'] for r in result['reasons']]


def _select_session(u, sid):
    ext = u.ext()
    dm = {d['dimension_id']: d['decision_id'] for d in ext['decisions'].values()
          if d['kind'] == 'attempt' and d['session_id'] == sid}
    tm = {'D2': next(d['decision_id'] for d in ext['decisions'].values()
                     if d['kind'] == 'transfer')}
    u.m('select', '--file', u.file(f'sel-{u.n}.json', {
        'milestone': 'handoff', 'actor_scope': {'actor_declared_id': 'alice',
                                                'profile': 'pipeline'},
        'dimension_decision_map': dm, 'transfer_decision_map': tm,
        'reservation_resolution_refs': []}))


# --- R9CD-1 ---------------------------------------------------------------------------------

def test_r9cd1_generation_exported_while_blocked_is_not_allowed_later(tmp_path):
    """p1. A generation exported while the gate blocked (no selection yet) says so in its
    content; the study then passes. Local verification of that old generation is blocked
    (``exported_content_not_current``) and nonconforming, as the standalone verifier says;
    ``git-plan`` says the content is not current and ``git-stage`` refuses. A new generation
    of the current content is allowed and planned."""
    u = U(tmp_path)
    sid = custom_flow(u, REQ, select=False)
    assert _codes(gate(u)) == ['no_selection']
    ukit.approve_all(u, sid)
    old = u.m('export', 'write', '--session', sid, '--repo', u.repo)['review_id']
    doc = json.loads((u.repo / ex.EXPORT_DIR / old / ex.JSON_FILE).read_text())
    assert 'no_selection' in [g['kind'] for g in doc['known_gaps']]
    _select_session(u, sid)
    assert gate(u)['decision'] == 'allowed'
    gen = _verify(u, 'worktree')['generations'][0]
    assert gen['exported_content_current'] is False
    assert gen['gate_result']['decision'] == 'blocked'
    assert gen['gate_result']['target_tree_reasons'] == [vf.CONTENT_NOT_CURRENT]
    assert gen['declared_conformity'] == 'nonconforming'
    standalone = _verify(u, 'worktree', study=False, policy=REQ)['generations'][0]
    assert standalone['gate_result']['decision'] == 'blocked'
    plan = u.call('git-plan', '--session', sid, '--repo', u.repo)
    assert plan['review_id'] == old
    assert plan['exported_content_current'] is False and plan['consistent'] is False
    assert any('export write' in w for w in plan['warnings'])
    refused = u.call('git-stage', '--session', sid, '--repo', u.repo, '--index-identity',
                     plan['index_identity'], expect=2)
    assert refused['error']['code'] == 'export_stale'
    assert 'export write' in refused['error']['details']['next_action']
    assert ukit.git(u.repo, 'diff', '--cached', '--name-only') == ''
    # The current content, exported, is allowed and planned.
    ukit.approve_all(u, sid)
    new = u.m('export', 'write', '--session', sid, '--repo', u.repo)['review_id']
    assert new != old
    out = _verify(u, 'worktree', policy=REQ)
    by_id = {g['review_id']: g for g in out['generations']}
    assert by_id[new]['gate_result']['decision'] == 'allowed'
    assert by_id[new]['declared_conformity'] == 'conforming'
    assert by_id[old]['gate_result']['decision'] == 'blocked'
    plan = u.call('git-plan', '--session', sid, '--repo', u.repo)
    assert plan['review_id'] == new and plan['consistent'] is True
    assert plan['exported_content_current'] is True and plan['warnings'] == []


def test_r9cd1_unrelated_progress_does_not_make_the_content_not_current(tmp_path):
    """R5-1 still holds after R9CD-1: the junior keeps working after the export (a study
    decision no dimension depends on): the projection is unchanged, so the generation stays
    current, allowed and plannable."""
    u = U(tmp_path)
    sid = custom_flow(u, REQ)
    ukit.approve_all(u, sid)
    w = u.m('export', 'write', '--session', sid, '--repo', u.repo)
    before = u.call('export', 'preview', '--session', sid, '--repo', u.repo)['content_digest']
    u.flow.variant(run=False)
    assert gate(u)['decision'] == 'allowed'
    after = u.call('export', 'preview', '--session', sid, '--repo', u.repo)['content_digest']
    assert after == before
    gen = _verify(u, 'worktree', policy=REQ)['generations'][0]
    assert gen['review_id'] == w['review_id']
    assert gen['exported_content_current'] is True
    assert gen['gate_result']['decision'] == 'allowed'
    assert gen['gate_result']['target_tree_reasons'] == []
    assert gen['private_context_verification'] == 'unknown'      # the context did change
    plan = u.call('git-plan', '--session', sid, '--repo', u.repo)
    assert plan['consistent'] is True and plan['exported_content_current'] is True


# --- R9CD-2 ---------------------------------------------------------------------------------

def test_r9cd2_autocrlf_sources_are_diagnosed(tmp_path):
    """p2. core.autocrlf=true (Git for Windows' default): the reviewed sources are the
    checked-out CRLF bytes, Git stores LF. ``git-plan`` reports each as
    ``source_transformed_by_git`` with the conversion and what to do, and ``git-stage``
    refuses with that reason. The digests are unchanged (fail closed): staged and committed,
    the sources read ``stale`` at the index and at HEAD."""
    u = U(tmp_path)
    ukit.git(u.repo, 'config', 'core.autocrlf', 'true')
    for p in ('src/pipeline.py', 'src/transforms.py', 'SECURITY.md', 'README.md'):
        (u.repo / p).unlink()
    ukit.git(u.repo, 'checkout', '--', '.')
    assert b'\r\n' in (u.repo / 'src/pipeline.py').read_bytes()
    sid = custom_flow(u, REQ)
    ukit.approve_all(u, sid)
    u.m('export', 'write', '--session', sid, '--repo', u.repo)
    plan = u.call('git-plan', '--session', sid, '--repo', u.repo)
    assert plan['consistent'] is False
    conflicts = {c['path']: c for c in plan['source_conflicts']}
    assert set(conflicts) == {'src/pipeline.py', 'src/transforms.py', 'SECURITY.md'}
    for c in conflicts.values():
        assert c['code'] == vf.SOURCE_TRANSFORMED
        assert c['git_conversion'] == ['core.autocrlf=true']
        assert c['worktree'] == c['snapshot'] != c['index']
        assert '-text' in c['next_action']
    assert any('Git converts' in w for w in plan['warnings'])
    refused = u.call('git-stage', '--session', sid, '--repo', u.repo, '--index-identity',
                     plan['index_identity'], expect=2)
    assert refused['error']['code'] == 'git_index_conflict'
    assert refused['error']['details']['reason'] == vf.SOURCE_TRANSFORMED
    assert '-text' in refused['error']['details']['next_action']
    # Fail closed, unchanged: the bytes Git stores are not the reviewed ones.
    ukit.git(u.repo, 'add', '--', 'docs/understanding')
    for target in ('index',):
        gen = _verify(u, target)['generations'][0]
        assert gen['public_source_freshness'] == 'stale'
        assert gen['gate_result']['decision'] == 'blocked'
    # Disabling the conversion for these paths makes the plan consistent.
    (u.repo / '.gitattributes').write_text(
        ''.join(f'{p} -text\n' for p in sorted(conflicts)))
    ukit.git(u.repo, 'add', '--renormalize', '--', *sorted(conflicts))
    plan = u.call('git-plan', '--session', sid, '--repo', u.repo)
    assert plan['source_conflicts'] == [] and plan['consistent'] is True


def test_r9cd2_a_real_difference_is_not_called_a_conversion(tmp_path):
    """Control: under core.autocrlf, a source staged with other content is
    ``source_differs``, never a conversion."""
    u = U(tmp_path)
    sid = custom_flow(u, REQ)
    ukit.approve_all(u, sid)
    u.m('export', 'write', '--session', sid, '--repo', u.repo)
    ukit.git(u.repo, 'config', 'core.autocrlf', 'true')
    keep = (u.repo / 'src/transforms.py').read_bytes()
    (u.repo / 'src/transforms.py').write_text('def fit_imputer(train):\n    return 0\n')
    ukit.git(u.repo, 'add', '--', 'src/transforms.py')
    (u.repo / 'src/transforms.py').write_bytes(keep)
    plan = u.call('git-plan', '--session', sid, '--repo', u.repo)
    conflicts = {c['path']: c for c in plan['source_conflicts']}
    assert conflicts['src/transforms.py']['code'] == vf.SOURCE_DIFFERS
    assert 'git_conversion' not in conflicts['src/transforms.py']


# --- R9CD-3 ---------------------------------------------------------------------------------

def test_r9cd3_a_tree_problem_invalidates_every_generation(tmp_path):
    """p4 (the generation's variant only). A case variant of a generation folder, with
    other bytes, is committed next to it: every generation is invalid, blocked and
    nonconforming, locally and standalone, with the problem listed."""
    u = U(tmp_path)
    sid = custom_flow(u, REQ)
    ukit.approve_all(u, sid)
    rid = u.m('export', 'write', '--session', sid, '--repo', u.repo)['review_id']
    plan = u.call('git-plan', '--session', sid, '--repo', u.repo)
    u.call('git-stage', '--session', sid, '--repo', u.repo, '--index-identity',
           plan['index_identity'])
    d = u.repo / ex.EXPORT_DIR / ('RV' + rid[2:])
    d.mkdir()
    (d / ex.MD_FILE).write_text('# Everything demonstrated, no gaps\n')
    ukit.git(u.repo, 'add', '--', str(d.relative_to(u.repo)))
    ukit.git(u.repo, 'commit', '-qm', 'review')
    for study, policy in ((True, None), (False, REQ)):
        out = _verify(u, 'HEAD', study=study, policy=policy)
        assert out['public_integrity'] == 'invalid' and out['problems']
        [gen] = out['generations']
        assert gen['review_id'] == rid
        assert gen['public_integrity'] == 'invalid'
        assert set(out['problems']) <= set(gen['problems'])
        assert gen['gate_result']['decision'] == 'blocked'
        assert 'public_integrity_invalid' in _codes(gen['gate_result'])
        assert gen['declared_conformity'] == 'nonconforming'
    local = _verify(u, 'HEAD')['generations'][0]
    assert 'public_integrity_invalid' in local['gate_result']['target_tree_reasons']


# --- R9CD-4 ---------------------------------------------------------------------------------

def test_r9cd4_not_current_generation_revalidated_after_a_revert(tmp_path):
    """p5. Generation A is interrupted before its receipt; a source is edited and B is
    written (A then gets its receipt: ``not_current``); the edit is reverted. ``git-plan``
    does not fall back silently to B: it says B is not the current content and that A is,
    to be written again. ``export write`` then revalidates A (``published``, its earlier
    receipt kept) and ``git-plan`` plans A."""
    u = U(tmp_path)
    sid = custom_flow(u, REQ)
    orig = (u.repo / 'src/pipeline.py').read_text()
    ukit.approve_all(u, sid)
    args = argparse.Namespace(study=str(u.study), session=sid, repo=str(u.repo), latest=False,
                              request_id='w-1', expected_revision=u.rev())
    with pytest.raises(RuntimeError):
        cu._export_write(args, fault='after_rename')
    [rid_a] = [x['review_id'] for x in u.ext()['exports'].values()]
    (u.repo / 'src/pipeline.py').write_text('def predict(row):\n    return 0\n')
    ukit.approve_all(u, sid)
    rid_b = u.m('export', 'write', '--session', sid, '--repo', u.repo)['review_id']
    status = {x['review_id']: x['status'] for x in u.ext()['exports'].values()}
    assert status == {rid_a: 'not_current', rid_b: 'published'}
    (u.repo / 'src/pipeline.py').write_text(orig)
    plan = u.call('git-plan', '--session', sid, '--repo', u.repo)
    assert plan['review_id'] == rid_b
    assert plan['exported_content_current'] is False and plan['consistent'] is False
    assert any(rid_a in w and 'export write' in w for w in plan['warnings'])
    refused = u.call('git-stage', '--session', sid, '--repo', u.repo, '--index-identity',
                     plan['index_identity'], expect=2)
    assert refused['error']['code'] == 'export_stale'
    ukit.approve_all(u, sid)
    again = u.m('export', 'write', '--session', sid, '--repo', u.repo)
    assert again['review_id'] == rid_a and again['receipt']['status'] == 'published'
    intent = next(x for x in u.ext()['exports'].values() if x['review_id'] == rid_a)
    assert intent['status'] == 'published'
    assert [r['status'] for r in intent['previous_receipts']] == ['not_current']
    plan = u.call('git-plan', '--session', sid, '--repo', u.repo)
    assert plan['review_id'] == rid_a
    assert plan['consistent'] is True and plan['exported_content_current'] is True
    # A replayed write changes nothing more.
    replay = u.m('export', 'write', '--session', sid, '--repo', u.repo)
    assert replay['receipt']['status'] == 'published'
    intent = next(x for x in u.ext()['exports'].values() if x['review_id'] == rid_a)
    assert len(intent['previous_receipts']) == 1


# --- R9CD-5 ---------------------------------------------------------------------------------

def test_r9cd5_repo_must_be_the_top_level(tmp_path):
    """p6. A project inside a monorepo: ``plan --repo`` on the subdirectory is refused
    (``path_outside_scope``) with what to do; nothing is recorded. ``git-plan`` and
    ``git-receipt`` refuse a subdirectory too, and ``verify-export`` on a commit says why it
    finds no generation instead of an empty invalid result."""
    u = U(tmp_path)
    mono = tmp_path / 'mono'
    mono.mkdir()
    shutil.rmtree(u.repo / '.git')
    shutil.move(str(u.repo), str(mono / 'proj'))
    ukit.git(mono, 'init', '-q', '-b', 'main')
    ukit.git(mono, 'add', '-A')
    ukit.git(mono, 'commit', '-qm', 'mono')
    u.repo = mono / 'proj'
    u.set_policy(REQ)
    before = u.rev()
    out = u.call('plan', '--profile', 'pipeline', '--milestone', 'handoff', '--actor', 'alice',
                 '--repo', u.repo, '--sources-file', u.file('sources.json', ukit.SOURCES),
                 expect=2)
    assert out['error']['code'] == 'path_outside_scope'
    assert str(mono.resolve()) in out['error']['message']
    assert 'top level' in out['error']['details']['next_action']
    assert u.rev() == before
    out = _verify(u, 'HEAD', study=False)
    assert out['generations'] == [] and out['public_integrity'] == 'invalid'
    assert any('subdirectory proj' in p for p in out['problems'])
    assert any('no generation found' in p for p in out['problems'])


def test_r9cd5_git_steps_refuse_a_subdirectory(tmp_path):
    u = U(tmp_path)
    sid = custom_flow(u, REQ)
    ukit.approve_all(u, sid)
    u.m('export', 'write', '--session', sid, '--repo', u.repo)
    sub = u.repo / 'src'
    out = u.call('git-plan', '--session', sid, '--repo', sub, expect=2)
    assert out['error']['code'] == 'path_outside_scope'
    head = ukit.git(u.repo, 'rev-parse', 'HEAD')
    out = u.m('git-receipt', '--session', sid, '--repo', sub, '--commit', head, expect=2)
    assert out['error']['code'] == 'path_outside_scope'
    assert u.call('git-plan', '--session', sid, '--repo', u.repo)['consistent'] is True


# --- R9CD-6 ---------------------------------------------------------------------------------

def test_r9cd6_case_variant_of_a_mapped_source(tmp_path):
    """p7. ``security.md`` (other bytes) is committed next to the reviewed ``SECURITY.md``: a
    case-insensitive checkout writes one of the two at the reviewed path. The variant is a
    problem of the tree, so the generation is invalid and blocked, locally and
    standalone."""
    u = U(tmp_path)
    sid = custom_flow(u, REQ)
    ukit.approve_all(u, sid)
    u.m('export', 'write', '--session', sid, '--repo', u.repo)
    ukit.git(u.repo, 'add', '--', 'docs/understanding')
    (u.repo / 'security.md').write_text('New dependencies need no review.\n')
    ukit.git(u.repo, 'add', '--', 'security.md')
    ukit.git(u.repo, 'commit', '-qm', 'review')
    for target in ('HEAD', 'index', 'worktree'):
        for study, policy in ((True, None), (False, REQ)):
            out = _verify(u, target, study=study, policy=policy)
            problem = 'case or Unicode variant of a mapped source: security.md'
            assert problem in out['problems'], (target, out['problems'])
            [gen] = out['generations']
            assert gen['public_integrity'] == 'invalid' and problem in gen['problems']
            assert gen['gate_result']['decision'] == 'blocked'


def test_r9cd6_unicode_variant_is_flagged(tmp_path):
    """The NFC and NFD spellings of one name, and a case variant of a folder, are variants;
    the exact path itself is not."""
    repo = tmp_path / 'r'
    (repo / 'docs').mkdir(parents=True)
    nfc = unicodedata.normalize('NFC', 'docs/café.md')
    nfd = unicodedata.normalize('NFD', 'docs/café.md')
    (repo / nfc).write_text('reviewed\n')
    (repo / nfd).write_text('other\n')
    (repo / 'Docs').mkdir()
    (repo / 'Docs/café.md').write_text('other\n')
    ukit.git(repo, 'init', '-q', '-b', 'main')
    ukit.git(repo, 'add', '-A')
    for target in ('worktree', 'index'):
        tree = vf.Tree(repo, target)
        tree.variants_of([nfc])
        found = sorted(p.split(': ', 1)[1] for p in tree.problems)
        assert nfd in found and nfc not in found, (target, found)
        assert any(p.startswith('Docs') for p in found), (target, found)


# --- R9CD-7 ---------------------------------------------------------------------------------

def _run(u, *args):
    out = cli.run(['understanding', *map(str, args), '--study', str(u.study)])
    return out.exit_code, out.payload


@pytest.mark.parametrize('change', ['oversized', 'link_outside', 'folder'])
def test_r9cd7_source_unreadable_after_start_reads_unknown(tmp_path, change):
    """p3. After ``start``, the mapped transform recipe grows past the size the review reads,
    becomes a link leaving the repository, or a folder. ``check``, ``status`` and ``export
    preview`` no longer refuse (``path_outside_scope``): the current capture records it as
    unreadable, so its dependency reads ``unknown`` and the gate blocks on it. ``plan`` still
    refuses such a source."""
    u = U(tmp_path)
    sid = custom_flow(u, REQ)
    assert gate(u)['decision'] == 'allowed'
    target = u.repo / 'src/transforms.py'
    target.unlink()
    if change == 'oversized':
        target.write_text('# x\n' * 700_000)
    elif change == 'link_outside':
        outside = tmp_path / 'outside.py'
        outside.write_text('def fit_imputer(train):\n    return 0\n')
        os.symlink(outside, target)
    else:
        target.mkdir()
    code, out = _run(u, 'check', '--milestone', 'handoff')
    assert code == 0, out
    assert out['gate']['decision'] == 'blocked'
    assert 'freshness_unknown' in _codes(out['gate'])
    code, out = _run(u, 'status')
    assert code == 0, out
    assert 'unknown' in [d['freshness'] for d in out['sessions'][0]['dimensions']]
    code, out = _run(u, 'export', 'preview', '--session', sid, '--repo', u.repo)
    assert code == 0, out
    code, out = _run(u, 'plan', '--profile', 'pipeline', '--milestone', 'handoff', '--actor',
                     'alice', '--repo', u.repo, '--sources-file',
                     u.file('sources.json', ukit.SOURCES))
    assert code == 2 and out['error']['code'] == 'path_outside_scope'
