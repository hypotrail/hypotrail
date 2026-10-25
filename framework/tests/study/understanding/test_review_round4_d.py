"""Round-4 adversarial probes, area D, kept as regression tests. Simulated humans only;
everything in tmp dirs."""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

import ukit
from mlkit.study import cli
from mlkit.study.understanding import canonical, export as ex, verify as vf


def verify(repo, target, *extra, env=None):
    return cli.run(['understanding', 'verify-export', '--repo', str(repo), '--target', target,
                    *map(str, extra)]).payload


@pytest.fixture
def ready(tmp_path):
    u = ukit.U(tmp_path)
    sid = ukit.full_flow(u)
    ukit.approve_all(u, sid)
    return u, sid


KILLER = r'''
import os, signal, sys
from pathlib import Path
from mlkit.study import cli
from mlkit.study.understanding import export as ex
def die(src, dst):
    os.kill(os.getpid(), signal.SIGKILL)
ex.rename_noreplace = die
argv = sys.argv[1:]
cli.run(argv)
'''


def run_killed(u, sid, tmp_path):
    script = tmp_path / 'killer.py'
    script.write_text(KILLER)
    argv = ['understanding', 'export', 'write', '--session', sid, '--repo', str(u.repo),
            '--study', str(u.study), '--request-id', 'killed-1', '--expected-revision',
            str(u.rev())]
    p = subprocess.run([sys.executable, str(script), *argv], capture_output=True)
    print('KILLER', p.returncode, p.stdout[-500:], p.stderr[-1500:])
    return p.returncode


def test_retry_right_after_kill_leaves_leftover(ready, tmp_path):
    """SIGKILL (closing the terminal, OOM) during publication, then an immediate retry."""
    u, sid = ready
    rc = run_killed(u, sid, tmp_path)
    parent = u.repo / ex.EXPORT_DIR
    left = sorted(p.name for p in parent.iterdir())
    print('OBSERVED after kill rc', rc, left)
    out = u.m('export', 'write', '--session', sid, '--repo', u.repo)
    after = sorted(p.name for p in parent.iterdir())
    v = verify(u.repo, 'worktree', '--study', u.study)
    print('OBSERVED retry', out['publication'], after, v['public_integrity'], v['problems'])
    # A young leftover may be a live concurrent publication: it is kept, but export write
    # names it with what to do and the verifier says why it is invalid (fix of D4-1).
    young = [n for n in after if n.startswith('.rv-')]
    assert young and out['leftover_temporary_folders'] == young
    assert any('interrupted export' in step for step in out['next_steps'])
    assert any('interrupted export' in p for p in v['problems'])
    shutil.rmtree(parent / young[0])
    assert verify(u.repo, 'worktree', '--study', u.study)['public_integrity'] == 'valid'


def test_leftover_of_previous_projection_never_removed(ready, tmp_path):
    u, sid = ready
    rc = run_killed(u, sid, tmp_path)
    parent = u.repo / ex.EXPORT_DIR
    old = [p for p in parent.iterdir() if p.name.startswith('.rv-')]
    # make it old (more than a minute)
    for p in old:
        os.utime(p, (time.time() - 3600, time.time() - 3600))
    # The content changes (a source of the scope changes is not projection; use a new approval
    # flow: change the handover, which changes the projection), then a new export.
    h = dict(ukit.HANDOVER, purpose=ukit.HANDOVER['purpose'] + ' Updated.')
    # handover set on a completed session may be refused; try
    r = u.call('handover', 'set', '--session', sid, '--file', u.file('h2.json', h),
               mutation=True, expect=None)
    print('OBSERVED handover set', r.get('ok'), r.get('error', {}).get('code') if isinstance(r.get('error'), dict) else r.get('code'))
    prev = ukit.approve_all(u, sid)
    out = u.call('export', 'write', '--session', sid, '--repo', u.repo, mutation=True, expect=None)
    names = sorted(p.name for p in parent.iterdir())
    v = verify(u.repo, 'worktree')
    print('OBSERVED new export', out.get('review_id'), out.get('publication'), names, v['problems'])
    assert not [n for n in names if n.startswith('.rv-')]


def test_git_dir_inherited(ready, tmp_path, monkeypatch):
    u, sid = ready
    u.m('export', 'write', '--session', sid, '--repo', u.repo)
    ukit.git(u.repo, 'add', '--', ex.EXPORT_DIR)
    ukit.git(u.repo, 'commit', '-q', '-m', 'genuine review')
    other = tmp_path / 'other'
    other.mkdir()
    ukit.git(other, 'init', '-q', '-b', 'main')
    (other / 'x').write_text('x')
    ukit.git(other, 'add', 'x')
    ukit.git(other, 'commit', '-qm', 'other')
    monkeypatch.setenv('GIT_DIR', str(u.repo / '.git'))
    v = verify(other, 'HEAD')
    print('OBSERVED verify --repo other with GIT_DIR of project:', v.get('public_integrity'),
          v.get('commit'), [g['review_id'] for g in v.get('generations', [])])
    assert v.get('generations') == [] or v.get('ok') is False
    assert v.get('commit') != ukit.git(u.repo, 'rev-parse', 'HEAD').strip()


def test_blobless_clone_project_git_path(tmp_path):
    """The team's project is a blobless clone (git clone --filter=blob:none), common for large
    repositories: the user's own Git path (git-plan, verify --target index) on it."""
    u = ukit.U(tmp_path)
    origin = u.repo
    ukit.git(origin, 'config', 'uploadpack.allowFilter', 'true')
    clone = tmp_path / 'clone'
    subprocess.run(['git', 'clone', '-q', '--filter=blob:none', f'file://{origin}', str(clone)],
                   check=True, capture_output=True)
    print('OBSERVED partialclone config', ukit.git(clone, 'config', '--get', 'remote.origin.promisor'))
    # the study's session reads the clone
    u.repo = clone
    sid = ukit.full_flow(u)
    ukit.approve_all(u, sid)
    out = u.m('export', 'write', '--session', sid, '--repo', clone)
    plan = u.call('git-plan', '--session', sid, '--repo', clone, expect=None)
    v = verify(clone, 'worktree')
    vi = verify(clone, 'index')
    print('OBSERVED blobless: export', out['publication'], '| git-plan', plan.get('ok'),
          plan.get('error') or plan.get('code'), '| verify worktree', v.get('public_integrity'),
          '| verify index', vi.get('ok'), vi.get('error', vi.get('code')))
    if vf.git_version() >= vf.NO_LAZY_FETCH_SINCE:
        assert plan.get('ok') is True
    else:       # older Git: refused, and the advice names what works (fix of D4-3)
        assert plan['error']['code'] == 'git_index_conflict'
        assert '2.44' in plan['error']['message'] + json.dumps(plan['error'].get('details'))


def test_concurrent_publish_threads(tmp_path):
    import threading
    repo = tmp_path / 'r'
    repo.mkdir()
    files = {n: (n * 50).encode() for n in ex.FILES}
    results, errors = [], []
    barrier = threading.Barrier(16)

    def go():
        barrier.wait()
        try:
            results.append(ex.publish(repo, 'rv-0123456789abcdef0123', files))
        except Exception as exc:     # noqa: BLE001
            errors.append(repr(exc))
    ts = [threading.Thread(target=go) for _ in range(16)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    names = sorted(p.name for p in (repo / ex.EXPORT_DIR).iterdir())
    print('OBSERVED concurrent', sorted(results), errors, names)
    assert not errors and results.count('published') == 1


def test_autocrlf_checkout_of_a_teammate(ready, tmp_path):
    u, sid = ready
    u.m('export', 'write', '--session', sid, '--repo', u.repo)
    ukit.git(u.repo, 'add', '--', ex.EXPORT_DIR)
    ukit.git(u.repo, 'commit', '-q', '-m', 'genuine review')
    clone = tmp_path / 'win-clone'
    subprocess.run(['git', '-c', 'core.autocrlf=true', 'clone', '-q', str(u.repo), str(clone)],
                   check=True, capture_output=True)
    w = verify(clone, 'worktree')
    h = verify(clone, 'HEAD')
    print('OBSERVED autocrlf clone: worktree', w['public_integrity'],
          [g['problems'] for g in w['generations']], '| HEAD', h['public_integrity'])
    # The export's .gitattributes travels with the generation: no CRLF conversion (D4-4).
    assert (u.repo / ex.EXPORT_DIR / ex.ATTRIBUTES_FILE).read_bytes() == ex.ATTRIBUTES
    assert w['public_integrity'] == 'valid' and h['public_integrity'] == 'valid'


def _restamp(doc):
    doc['policy_digest'] = canonical.digest(doc['policy'])
    proj = ex.approval_projection(doc)
    dg = canonical.digest(proj)
    for a in doc['privacy_review']['approvals']:
        a['content_digest'] = dg
    doc['privacy_review']['required_contributors'] = sorted(ex.required_contributors(proj))
    doc['review_id'] = ex.review_id(proj)
    return doc


def test_unmapped_dimension_shows_a_review(ready, tmp_path):
    u, sid = ready
    rid = u.m('export', 'write', '--session', sid, '--repo', u.repo)['review_id']
    repo = tmp_path / 'forged'
    shutil.copytree(u.repo, repo)
    g = repo / ex.EXPORT_DIR / rid
    doc = canonical.loads((g / ex.JSON_FILE).read_bytes())
    m = doc['coverage_selection']['dimension_decision_map']
    dim = sorted(m)[0]
    del m[dim]
    _restamp(doc)
    shutil.rmtree(g)
    d = repo / ex.EXPORT_DIR / doc['review_id']
    d.mkdir()
    for n, data in ex.files_of(doc).items():
        (d / n).write_bytes(data)
    v = verify(repo, 'worktree')
    gen = v['generations'][0]
    print('OBSERVED unmapped', dim, v['public_integrity'], gen['declared_conformity'],
          gen['problems'], [x['status'] for x in doc['dimensions'] if x['id'] == dim])
    assert v['public_integrity'] == 'invalid'
    assert any('does not map' in p for p in gen['problems'])
