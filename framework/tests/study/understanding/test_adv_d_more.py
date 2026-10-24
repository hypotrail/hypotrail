"""Area D review: more verifier / Git-path probes."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'understanding'))

import ukit  # noqa: E402
from mlkit.study import cli  # noqa: E402
from mlkit.study.understanding import canonical, export as ex  # noqa: E402


def verify(repo, target, *extra):
    return cli.run(['understanding', 'verify-export', '--repo', str(repo), '--target', target,
                    *map(str, extra)]).payload


@pytest.fixture(scope='module')
def base(tmp_path_factory):
    root = tmp_path_factory.mktemp('more')
    u = ukit.U(root)
    sid = ukit.full_flow(u)
    ukit.approve_all(u, sid)
    w = u.m('export', 'write', '--session', sid, '--repo', u.repo)
    ukit.git(u.repo, 'add', '--', ex.EXPORT_DIR)
    ukit.git(u.repo, 'commit', '-q', '-m', 'review')
    return u, sid, w['review_id']


def clone(u, tmp_path, name='c'):
    dst = tmp_path / name
    subprocess.run(['git', 'clone', '-q', str(u.repo), str(dst)], check=True)
    return dst


def test_leftover_temp_dir_and_foreign_dirs_are_silently_ignored(base, tmp_path):
    u, sid, rid = base
    c = clone(u, tmp_path)
    d = c / ex.EXPORT_DIR
    tmp = d / f'.{rid}.tmp-deadbeef'
    tmp.mkdir()
    (tmp / ex.JSON_FILE).write_bytes(b'{"partial":')
    foreign = d / 'not-a-review'
    foreign.mkdir()
    (foreign / ex.JSON_FILE).write_bytes(b'garbage')
    (d / 'rv-file-not-dir').write_bytes(b'x')
    ukit.git(c, 'add', '--', ex.EXPORT_DIR)
    ukit.git(c, 'commit', '-q', '-m', 'junk')
    out = verify(c, 'HEAD')
    wt = verify(c, 'worktree')
    print('OBSERVED commit', out['public_integrity'], [g['review_id'] for g in out['generations']],
          out['problems'])
    print('OBSERVED worktree', wt['public_integrity'],
          [(g['review_id'], g['public_integrity']) for g in wt['generations']])


def test_worktree_generation_dir_symlinked_inside_repo(base, tmp_path):
    u, sid, rid = base
    c = clone(u, tmp_path)
    real = c / 'elsewhere'
    shutil.move(str(c / ex.EXPORT_DIR / rid), str(real))
    os.symlink(real, c / ex.EXPORT_DIR / rid)
    g = verify(c, 'worktree')
    print('OBSERVED symlinked generation dir (worktree):', g['public_integrity'], g['problems'])


def test_rename_hides_staged_deletion_from_plan(base, tmp_path):
    u, sid, rid = base
    ukit.git(u.repo, 'mv', 'README.md', 'README2.md')
    try:
        plan = u.call('git-plan', '--session', sid, '--repo', u.repo)
        print('OBSERVED staged_outside_plan', plan['staged_outside_plan'])
        assert 'README.md' in plan['staged_outside_plan']
    finally:
        ukit.git(u.repo, 'mv', 'README2.md', 'README.md')


def test_amended_source_in_later_commit_is_stale_and_old_commit_still_valid(base, tmp_path):
    u, sid, rid = base
    c = clone(u, tmp_path)
    old = ukit.git(c, 'rev-parse', 'HEAD')
    (c / 'src/pipeline.py').write_text('changed\n')
    ukit.git(c, 'commit', '-qam', 'x')
    assert verify(c, 'HEAD')['generations'][0]['public_source_freshness'] == 'stale'
    assert verify(c, old)['generations'][0]['public_source_freshness'] == 'current'
    # history rewrite: drop the review commit's parent chain (orphan with same tree)
    tree = ukit.git(c, 'rev-parse', f'{old}^{{tree}}')
    orphan = ukit.git(c, 'commit-tree', tree, '-m', 'rewritten')
    g = verify(c, orphan)['generations'][0]
    print('OBSERVED orphan', g['public_integrity'], g['public_source_freshness'])


def test_source_removed_from_commit_is_unknown_not_current(base, tmp_path):
    u, sid, rid = base
    c = clone(u, tmp_path)
    ukit.git(c, 'rm', '-q', 'src/transforms.py')
    ukit.git(c, 'commit', '-qm', 'rm')
    strict = u.file('po.json', ukit.policy(mode='required', context_requirement='public_only',
                                           evidence_requirement='recorded_decisions'))
    g = verify(c, 'HEAD', '--policy-file', strict)['generations'][0]
    print('OBSERVED', g['public_source_freshness'], g['gate_result']['decision'])
    assert g['public_source_freshness'] == 'unknown'
    assert g['gate_result']['decision'] == 'blocked'


def test_review_id_option_traversal(base):
    u, sid, rid = base
    for bad in ('../../etc', 'rv-../x', '/abs', 'rv-x/..'):
        out = verify(u.repo, 'HEAD', '--review-id', bad)
        print('OBSERVED', bad, out.get('public_integrity'), out.get('problems'),
              [g['problems'] for g in out.get('generations', [])])
        assert out.get('public_integrity', 'invalid') == 'invalid'


def test_target_option_injection(base, tmp_path):
    u, sid, rid = base
    marker = tmp_path / 'out.txt'
    for bad in (f'--output={marker}', '-h', 'HEAD;touch x', 'HEAD^{tree}', 'HEAD:docs'):
        out = cli.run(['understanding', 'verify-export', '--repo', str(u.repo), '--target', bad])
        print('OBSERVED', bad, out.exit_code, out.payload.get('error', {}).get('code'))
    assert not marker.exists()


def test_duplicate_dimension_ids_in_forged_doc(base, tmp_path):
    """A hand-made doc listing D2 twice (not_evaluated then demonstrated)."""
    u, sid, rid = base
    c = clone(u, tmp_path)
    d = c / ex.EXPORT_DIR / rid
    doc = canonical.loads((d / ex.JSON_FILE).read_bytes())
    d2 = next(x for x in doc['dimensions'] if x['id'] == 'D2')
    doc['dimensions'].insert(0, dict(d2, status='to_consolidate'))
    proj = ex.approval_projection(doc)
    new = ex.review_id(proj)
    dig = canonical.digest(proj)
    for a in doc['privacy_review']['approvals']:
        a['content_digest'] = dig
    doc['review_id'] = new
    shutil.rmtree(d)
    nd = c / ex.EXPORT_DIR / new
    nd.mkdir()
    for n, data in ex.files_of(doc).items():
        (nd / n).write_bytes(data)
    po = u.file('po2.json', ukit.policy(mode='required', context_requirement='public_only',
                                        evidence_requirement='recorded_decisions'))
    g = verify(c, 'worktree', '--policy-file', po)['generations'][0]
    print('OBSERVED dup dims', g['public_integrity'], g['problems'])
    assert g['public_integrity'] == 'invalid'


def test_stage_reports_success_when_staged_bytes_differ(tmp_path):
    u = ukit.U(tmp_path)
    sid = ukit.full_flow(u)
    ukit.approve_all(u, sid)
    u.m('export', 'write', '--session', sid, '--repo', u.repo)
    script = tmp_path / 'clean.sh'
    script.write_text('#!/bin/sh\nsed s/Understanding/Misunderstanding/\n')
    script.chmod(0o755)
    ukit.git(u.repo, 'config', 'filter.x.clean', str(script))
    (u.repo / '.git' / 'info' / 'attributes').write_text('*.md filter=x\n')
    plan = u.call('git-plan', '--session', sid, '--repo', u.repo)
    st = u.call('git-stage', '--session', sid, '--repo', u.repo, '--index-identity',
                plan['index_identity'], expect=None)
    v = verify(u.repo, 'index')
    print('OBSERVED stage', st.get('ok'), st.get('error', {}).get('code'),
          st.get('unexpected_index_changes'), 'index verify', v['public_integrity'])
