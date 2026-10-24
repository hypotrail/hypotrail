"""Round-2 area D: verifier and Git plumbing in a partial clone; git-plan blind spots."""
from __future__ import annotations

import subprocess

import pytest

import ukit
from mlkit.study import cli
from mlkit.study.understanding import export as ex


def verify(repo, target, *extra):
    return cli.run(['understanding', 'verify-export', '--repo', str(repo), '--target', target,
                    *map(str, extra)]).payload


@pytest.fixture
def done(tmp_path):
    u = ukit.U(tmp_path)
    sid = ukit.full_flow(u)
    ukit.approve_all(u, sid)
    rid = u.m('export', 'write', '--session', sid, '--repo', u.repo)['review_id']
    return u, sid, rid


def test_verifier_lazy_fetch_runs_configured_program_in_partial_clone(done, tmp_path):
    u, sid, rid = done
    ukit.git(u.repo, 'add', '--', ex.EXPORT_DIR)
    ukit.git(u.repo, 'commit', '-q', '-m', 'review')
    ukit.git(u.repo, 'config', 'uploadpack.allowFilter', 'true')
    ukit.git(u.repo, 'config', 'uploadpack.allowAnySHA1InWant', 'true')
    clone = tmp_path / 'clone'
    subprocess.run(['git', 'clone', '-q', '--no-checkout', '--filter=blob:none',
                    f'file://{u.repo}', str(clone)], check=True)
    trace = tmp_path / 'TRACE'
    script = tmp_path / 'up.sh'
    script.write_text(f'#!/bin/sh\necho "upload-pack ran $@" >> {trace}\nexec git-upload-pack "$@"\n')
    script.chmod(0o755)
    ukit.git(clone, 'config', 'remote.origin.uploadpack', str(script))
    out = verify(clone, 'HEAD')
    print('OBSERVED', out, trace.read_text() if trace.exists() else 'no program ran')
    assert not trace.exists(), 'the verifier ran a configured program (lazy fetch)'
    # A partial clone is refused rather than read (fix of D2-5).
    assert out['error']['code'] == 'git_index_conflict'


def test_git_plan_hides_staged_submodule_change_with_ignore_config(done, tmp_path):
    u, sid, rid = done
    sub = tmp_path / 'sub'
    sub.mkdir()
    ukit.git(sub, 'init', '-q', '-b', 'main')
    (sub / 'f').write_text('1\n')
    ukit.git(sub, 'add', 'f')
    ukit.git(sub, 'commit', '-q', '-m', 'one')
    c1 = ukit.git(sub, 'rev-parse', 'HEAD')
    (sub / 'f').write_text('2\n')
    ukit.git(sub, 'commit', '-qam', 'two')
    c2 = ukit.git(sub, 'rev-parse', 'HEAD')
    ukit.git(u.repo, 'update-index', '--add', '--cacheinfo', f'160000,{c1},vendor/lib')
    ukit.git(u.repo, 'commit', '-q', '-m', 'add gitlink')
    ukit.git(u.repo, 'update-index', '--cacheinfo', f'160000,{c2},vendor/lib')   # staged bump
    plain = u.call('git-plan', '--session', sid, '--repo', u.repo)['staged_outside_plan']
    ukit.git(u.repo, 'config', 'diff.ignoreSubmodules', 'all')
    hidden = u.call('git-plan', '--session', sid, '--repo', u.repo)['staged_outside_plan']
    print('OBSERVED plain', plain, 'with diff.ignoreSubmodules=all', hidden)
    assert hidden == plain


def test_git_plan_hides_staged_submodule_change_via_committed_gitmodules(done, tmp_path):
    """Repository content (.gitmodules ignore = all), not local configuration."""
    u, sid, rid = done
    sub = tmp_path / 'sub'
    sub.mkdir()
    ukit.git(sub, 'init', '-q', '-b', 'main')
    (sub / 'f').write_text('1\n')
    ukit.git(sub, 'add', 'f')
    ukit.git(sub, 'commit', '-q', '-m', 'one')
    c1 = ukit.git(sub, 'rev-parse', 'HEAD')
    (sub / 'f').write_text('2\n')
    ukit.git(sub, 'commit', '-qam', 'two')
    c2 = ukit.git(sub, 'rev-parse', 'HEAD')
    (u.repo / '.gitmodules').write_text(
        '[submodule "lib"]\n\tpath = vendor/lib\n\turl = ../sub\n\tignore = all\n')
    ukit.git(u.repo, 'add', '.gitmodules')
    ukit.git(u.repo, 'update-index', '--add', '--cacheinfo', f'160000,{c1},vendor/lib')
    ukit.git(u.repo, 'commit', '-q', '-m', 'add submodule')
    ukit.git(u.repo, 'update-index', '--cacheinfo', f'160000,{c2},vendor/lib')
    staged = ukit.git(u.repo, 'diff', '--cached', '--name-only', '--ignore-submodules=none')
    hidden = u.call('git-plan', '--session', sid, '--repo', u.repo)['staged_outside_plan']
    print('OBSERVED actually staged', staged.split(), 'plan reports', hidden)
    assert 'vendor/lib' in hidden
