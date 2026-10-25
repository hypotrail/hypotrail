"""Round-3 adversarial probes, area D. Simulated humans only; everything in tmp dirs."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

import ukit
import flowkit as fk
from mlkit.study import cli
from mlkit.study.understanding import canonical, export as ex, verify as vf


def verify(repo, target, *extra):
    return cli.run(['understanding', 'verify-export', '--repo', str(repo), '--target', target,
                    *map(str, extra)]).payload


def gen(repo, rid):
    return Path(repo) / ex.EXPORT_DIR / rid


def restamp(doc):
    doc['policy_digest'] = canonical.digest(doc['policy'])
    if doc['handover_content'] is not None:
        doc['handover_digest'] = canonical.digest(doc['handover_content'])
    proj = ex.approval_projection(doc)
    dg = canonical.digest(proj)
    for a in doc['privacy_review']['approvals']:
        a['content_digest'] = dg
    doc['privacy_review']['required_contributors'] = sorted(ex.required_contributors(proj))
    doc['review_id'] = ex.review_id(proj)
    return doc


def write_gen(parent: Path, doc, files=None):
    files = files or ex.files_of(doc)
    d = parent / doc['review_id']
    d.mkdir(parents=True, exist_ok=True)
    for n, data in files.items():
        (d / n).write_bytes(data)
    return d


@pytest.fixture(scope='module')
def base(tmp_path_factory):
    root = tmp_path_factory.mktemp('base')
    u = ukit.U(root)
    sid = ukit.full_flow(u)
    ukit.approve_all(u, sid)
    rid = u.m('export', 'write', '--session', sid, '--repo', u.repo)['review_id']
    ukit.git(u.repo, 'add', '--', ex.EXPORT_DIR)
    ukit.git(u.repo, 'commit', '-q', '-m', 'genuine review')
    return u, sid, rid


def clone_repo(u, dst):
    shutil.copytree(u.repo, dst)
    return dst


# --- R3-1: --study naming a study without the review extension skips the binding ----------

def test_binding_skipped_with_study_without_extension(base, tmp_path):
    u, sid, rid = base
    repo = clone_repo(u, tmp_path / 'repo')
    # A forged generation: other rationale, consistently restamped (public integrity holds).
    doc = canonical.loads((gen(repo, rid) / ex.JSON_FILE).read_bytes())
    doc['dimensions'][0]['rationale'] = 'Forged: approved by the head of risk.'
    restamp(doc)
    shutil.rmtree(gen(repo, rid))
    write_gen(repo / ex.EXPORT_DIR, doc)
    # Another study, never enabled for the review (realistic: the wrong --study).
    other = fk.Flow(tmp_path / 'plain-study', u.case_dir, prefix='p')
    other.init()
    with_ext = verify(repo, 'worktree', '--study', u.study)
    without = verify(repo, 'worktree', '--study', other.study)
    g1, g2 = with_ext['generations'][0], without['generations'][0]
    print('OBSERVED with understanding study', with_ext['public_integrity'],
          g1.get('study_binding'), '| plain study', without['public_integrity'],
          g2.get('study_binding'), g2['limitations'], g2['declared_conformity'])
    assert with_ext['public_integrity'] == 'invalid'
    assert without['public_integrity'] == 'invalid' or g2.get('study_binding') is not None


# --- R3-2: a replace ref substitutes the blobs the verifier reads ---------------------------

def test_replace_ref_makes_verifier_read_other_bytes(base, tmp_path):
    u, sid, rid = base
    repo = clone_repo(u, tmp_path / 'repo')
    md = gen(repo, rid) / ex.MD_FILE
    genuine_blob = ukit.git(repo, 'rev-parse', f'HEAD:{ex.EXPORT_DIR}/{rid}/{ex.MD_FILE}')
    md.write_text(md.read_text().replace('This note records', 'APPROVED BY THE BOARD. This '
                                                              'note records'))
    ukit.git(repo, 'commit', '-qam', 'edit the review in place')
    tampered_blob = ukit.git(repo, 'rev-parse', f'HEAD:{ex.EXPORT_DIR}/{rid}/{ex.MD_FILE}')
    before = verify(repo, 'HEAD')
    ukit.git(repo, 'replace', tampered_blob, genuine_blob)
    after = verify(repo, 'HEAD')
    after_local = verify(repo, 'HEAD', '--study', u.study)
    real = subprocess.run(['git', '-C', str(repo), '--no-replace-objects', 'cat-file', 'blob',
                           tampered_blob], capture_output=True).stdout
    print('OBSERVED before replace', before['public_integrity'], 'after replace',
          after['public_integrity'], 'local', after_local['public_integrity'],
          after_local['generations'][0].get('study_binding'),
          'commit really holds tampered text', b'APPROVED BY THE BOARD' in real)
    assert before['public_integrity'] == 'invalid'
    assert after['public_integrity'] == 'invalid'


# --- R3-3: verifier consistency gaps a forger can use (standalone) ------------------------

def test_manifest_extra_fields_and_no_contributor(base, tmp_path):
    u, sid, rid = base
    repo = clone_repo(u, tmp_path / 'repo')
    d = gen(repo, rid)
    files = {n: (d / n).read_bytes() for n in ex.FILES}
    m = canonical.loads(files[ex.MANIFEST_FILE])
    m['authority'] = True
    m['approved_by'] = 'cto'
    m['files']['understanding-review.html'] = {'sha256': '0' * 64, 'bytes': 1}
    files[ex.MANIFEST_FILE] = canonical.dumps(m)
    (d / ex.MANIFEST_FILE).write_bytes(files[ex.MANIFEST_FILE])
    out = verify(repo, 'worktree')
    print('OBSERVED manifest with extra fields', out['public_integrity'],
          out['generations'][0]['problems'])
    assert out['public_integrity'] == 'invalid'


def test_approved_with_no_approval_when_author_is_null(base, tmp_path):
    u, sid, rid = base
    repo = clone_repo(u, tmp_path / 'repo')
    doc = canonical.loads((gen(repo, rid) / ex.JSON_FILE).read_bytes())
    doc['author_alias'] = None
    doc['coverage_selection'] = None
    for dim in doc['dimensions']:
        dim['reviewer_alias'] = None
    for p in doc['peer_coverage']:
        p['transfers'] = []
    doc['decisions_summary'] = []
    doc['privacy_review']['approvals'] = []
    doc['privacy_review']['status'] = 'approved'
    restamp(doc)
    shutil.rmtree(gen(repo, rid))
    write_gen(repo / ex.EXPORT_DIR, doc)
    out = verify(repo, 'worktree')
    g = out['generations'][0]
    print('OBSERVED approved with zero approvals', out['public_integrity'],
          doc['privacy_review'], g['problems'])
    assert out['public_integrity'] == 'invalid'


def test_duplicate_peer_coverage_entries(base, tmp_path):
    u, sid, rid = base
    repo = clone_repo(u, tmp_path / 'repo')
    doc = canonical.loads((gen(repo, rid) / ex.JSON_FILE).read_bytes())
    first = dict(doc['peer_coverage'][0])
    doc['peer_coverage'] = [dict(first, status='missing', people=1),
                            dict(first, status='current', people=9)]
    restamp(doc)
    shutil.rmtree(gen(repo, rid))
    write_gen(repo / ex.EXPORT_DIR, doc)
    out = verify(repo, 'worktree')
    print('OBSERVED duplicate peer coverage', out['public_integrity'],
          out['generations'][0]['problems'])
    assert out['public_integrity'] == 'invalid'


# --- R3-4: a gap's ref is an object when a mapped source is unreadable (schema says string) --

def test_unreadable_source_gap_matches_schema(tmp_path):
    u = ukit.U(tmp_path)
    (u.repo / 'SECURITY.md').unlink()
    ukit.git(u.repo, 'commit', '-qam', 'drop the security rule')
    sid = ukit.full_flow(u)
    ukit.approve_all(u, sid)
    rid = u.m('export', 'write', '--session', sid, '--repo', u.repo)['review_id']
    doc = canonical.loads((gen(u.repo, rid) / ex.JSON_FILE).read_bytes())
    gaps = [g for g in doc['known_gaps'] if g['kind'] == 'source_unreadable']
    md = (gen(u.repo, rid) / ex.MD_FILE).read_text()
    print('OBSERVED gaps', gaps, [l for l in md.splitlines() if 'source' in l and 'unreadable' in l])
    try:
        import jsonschema
        from mlkit.study.understanding import schemas
        reg_policy = schemas.policy_schema()
        schema = schemas.review_schema()
        from referencing import Registry, Resource
        reg = Registry().with_resource('understanding-policy-1.schema.json',
                                       Resource.from_contents(reg_policy))
        errs = [e.message for e in jsonschema.Draft202012Validator(schema, registry=reg)
                .iter_errors(doc)]
        print('OBSERVED schema errors', errs[:5])
    except ImportError:
        errs = None
    assert all(isinstance(g['ref'], str) for g in gaps)


# --- R3-5: export write retried after success; concurrent first writes ----------------------

def test_retry_after_publication_is_idempotent(base):
    u, sid, rid = base
    before = {n: (gen(u.repo, rid) / n).read_bytes() for n in ex.FILES}
    intents = len(u.ext()['exports'])
    again = u.m('export', 'write', '--session', sid, '--repo', u.repo, '--latest', expect=None)
    after = {n: (gen(u.repo, rid) / n).read_bytes() for n in ex.FILES}
    print('OBSERVED retry', again.get('publication'), again.get('replayed'),
          again.get('error'), len(u.ext()['exports']) - intents, before == after)
    assert again.get('publication') == 'already_published' and before == after
    assert len(u.ext()['exports']) == intents


def _child_write(study, sid, repo, req, q):
    out = cli.run(['understanding', 'export', 'write', '--session', sid, '--repo', str(repo),
                   '--study', str(study), '--request-id', req, '--expected-revision',
                   str(json.loads(json.dumps(ukit.read.load_state(study)['revision'])))])
    q.put((req, out.exit_code, out.payload.get('publication'),
           (out.payload.get('error') or {}).get('code')))


def test_concurrent_first_exports(tmp_path):
    import multiprocessing as mp
    u = ukit.U(tmp_path)
    sid = ukit.full_flow(u)
    ukit.approve_all(u, sid)
    ctx = mp.get_context('fork')
    q = ctx.Queue()
    ps = [ctx.Process(target=_child_write, args=(u.study, sid, u.repo, f'cw{i}', q))
          for i in range(3)]
    for p in ps:
        p.start()
    for p in ps:
        p.join(120)
    res = sorted(q.get() for _ in ps)
    exports = sorted((x['status'], x['review_id']) for x in u.ext()['exports'].values())
    left = sorted(p.name for p in (u.repo / ex.EXPORT_DIR).iterdir())
    out = verify(u.repo, 'worktree', '--study', u.study)
    print('OBSERVED', res, exports, left, out['public_integrity'], out['problems'])
    assert any(r[1] == 0 for r in res)
    assert all(r[1] == 0 or r[3] not in (None, 'internal_error') for r in res)
    assert out['public_integrity'] == 'valid'
    assert all(s == 'published' for s, _ in exports)


# --- R3-6: a publication killed mid-write leaves a temporary folder ------------------------

def test_killed_publication_leftover(tmp_path):
    from mlkit.study import cmd_understanding as cu
    u = ukit.U(tmp_path)
    sid = ukit.full_flow(u)
    ukit.approve_all(u, sid)
    pid = os.fork()
    if pid == 0:
        try:
            def die(path):
                os._exit(9)
            ex._fsync_dir = die
            args = argparse.Namespace(study=str(u.study), session=sid, repo=str(u.repo),
                                      latest=False, request_id='kill-1',
                                      expected_revision=u.rev())
            cu._export_write(args)
        finally:
            os._exit(3)
    _, status = os.waitpid(pid, 0)
    leftovers = sorted(p.name for p in (u.repo / ex.EXPORT_DIR).iterdir())
    assert any('.tmp-' in name for name in leftovers)
    # A retry right away keeps a folder that may belong to a live concurrent publication;
    # once it is older than ex.LEFTOVER_AGE_SECONDS the retry removes it (fix of D3-5).
    for name in leftovers:
        old = os.stat(u.repo / ex.EXPORT_DIR / name).st_mtime - ex.LEFTOVER_AGE_SECONDS - 5
        os.utime(u.repo / ex.EXPORT_DIR / name, (old, old))
    w = u.m('export', 'write', '--session', sid, '--repo', u.repo)
    after = sorted(p.name for p in (u.repo / ex.EXPORT_DIR).iterdir())
    out = verify(u.repo, 'worktree', '--study', u.study)
    print('OBSERVED child', os.waitstatus_to_exitcode(status), 'leftovers', leftovers,
          'retry', w['publication'], 'after', after, 'verify', out['public_integrity'],
          out['problems'], 'write mentions leftover', '.tmp-' in json.dumps(w))
    assert out['public_integrity'] == 'valid'
    assert not [name for name in after if '.tmp-' in name]


# --- R3-7: partial clone declared through an included config file ---------------------------

def test_partial_clone_via_include(base, tmp_path):
    u, sid, rid = base
    ukit.git(u.repo, 'config', 'uploadpack.allowFilter', 'true')
    ukit.git(u.repo, 'config', 'uploadpack.allowAnySHA1InWant', 'true')
    clone = tmp_path / 'clone'
    subprocess.run(['git', 'clone', '-q', '--no-checkout', '--filter=blob:none',
                    f'file://{u.repo}', str(clone)], check=True)
    cfg = (clone / '.git' / 'config').read_text()
    # Move the promisor settings into an included file.
    inc = clone / '.git' / 'promisor.inc'
    lines = cfg.splitlines()
    keep, moved, section = [], [], None
    for line in lines:
        s = line.strip()
        if s.startswith('['):
            section = s
        if ('promisor' in s or 'partialclonefilter' in s.lower()) and not s.startswith('['):
            moved.append(f'{section}\n{line}')
        elif 'partialclone' in s.lower() and not s.startswith('['):
            moved.append(f'{section}\n{line}')
        else:
            keep.append(line)
    (clone / '.git' / 'config').write_text('\n'.join(keep) + '\n[include]\n\tpath = promisor.inc\n')
    inc.write_text('\n'.join(moved) + '\n')
    trace = tmp_path / 'TRACE'
    script = tmp_path / 'up.sh'
    script.write_text(f'#!/bin/sh\necho ran >> {trace}\nexec git-upload-pack "$@"\n')
    script.chmod(0o755)
    ukit.git(clone, 'config', 'remote.origin.uploadpack', str(script))
    out = verify(clone, 'HEAD')
    print('OBSERVED', (out.get('error') or {}).get('code'), trace.exists(), inc.read_text())
    assert not trace.exists()


# --- R3-8: git-plan / git-stage on a repository given as a subdirectory --------------------

def test_markdown_fidelity_double_at():
    s = ex._md('ping a@@b')
    cmarkgfm = pytest.importorskip('cmarkgfm')
    html = cmarkgfm.github_flavored_markdown_to_html(s)
    print('OBSERVED', repr(s), html)
    assert '``' not in html
