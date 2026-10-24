"""Round-2 adversarial review, area D (export, verifier, Git path)."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path

import pytest

import ukit
from mlkit.study import cli
from mlkit.study.understanding import canonical, export as ex, verify as vf


def verify(repo, target, *extra):
    return cli.run(['understanding', 'verify-export', '--repo', str(repo), '--target', target,
                    *map(str, extra)]).payload


@pytest.fixture
def done(tmp_path):
    u = ukit.U(tmp_path)
    sid = ukit.full_flow(u)
    return u, sid


def exported(u, sid):
    ukit.approve_all(u, sid)
    return u.m('export', 'write', '--session', sid, '--repo', u.repo)['review_id']


def gen(u, rid):
    return u.repo / ex.EXPORT_DIR / rid


def write_gen(dirpath: Path, doc: dict, manifest_renderer=None) -> Path:
    files = ex.files_of(doc)
    if manifest_renderer is not None:
        m = canonical.loads(files[ex.MANIFEST_FILE])
        m['renderer_version'] = manifest_renderer
        files[ex.MANIFEST_FILE] = canonical.dumps(m)
    dirpath.mkdir(parents=True, exist_ok=True)
    for n, data in files.items():
        (dirpath / n).write_bytes(data)
    return dirpath


def restamp(doc):
    """Recompute review id, policy/handover digests and approvals for a forged doc."""
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


def commit_all(u, msg):
    ukit.git(u.repo, 'add', '-A', '--', ex.EXPORT_DIR)
    ukit.git(u.repo, 'commit', '-q', '-m', msg)


# --- D2-1: local binding ignores the bytes the intent announced -------------------------

def test_local_binding_accepts_tampered_privacy_review_and_provenance(done):
    """Same projection, but approvals, approval times, created_at and base_commit edited
    (an approval by 'mallory' who never approved, and a fake base commit): the files differ
    from the hashes the study recorded in its intent. Expected: local mode notices."""
    u, sid = done
    rid = exported(u, sid)
    d = gen(u, rid)
    real = {n: (d / n).read_bytes() for n in ex.FILES}
    doc = canonical.loads(real[ex.JSON_FILE])
    dg = canonical.digest(ex.approval_projection(doc))
    doc['privacy_review']['approvals'].append(
        {'approver_alias': 'mallory', 'approved_at': '2026-01-01T00:00:00Z',
         'content_digest': dg})
    doc['privacy_review']['approvals'].append(dict(doc['privacy_review']['approvals'][0]))
    for a in doc['privacy_review']['approvals']:
        a['approved_at'] = '1999-01-01T00:00:00Z'
    doc['created_at'] = '1999-01-01T00:00:00Z'
    doc['provenance']['base_commit'] = '0' * 40
    shutil.rmtree(d)
    write_gen(d, doc)
    assert (d / ex.JSON_FILE).read_bytes() != real[ex.JSON_FILE]
    intent = next(iter(u.ext()['exports'].values()))
    assert intent['files'][ex.JSON_FILE] != canonical.sha256_hex((d / ex.JSON_FILE).read_bytes())
    commit_all(u, 'tampered')
    out = verify(u.repo, 'HEAD', '--study', u.study)
    g = out['generations'][0]
    print('OBSERVED', out['public_integrity'], g.get('study_binding'),
          g['private_context_verification'], g['declared_conformity'], g['problems'])
    assert g.get('study_binding') != 'verified' or out['public_integrity'] == 'invalid'


# --- D2-2: fields rendered unescaped, never checked by the verifier ----------------------

@pytest.mark.parametrize('where', ['policy_version', 'renderer_version', 'peer_status',
                                   'dimension_id', 'people'])
def test_forged_markdown_injection_is_public_integrity_valid(done, where):
    u, sid = done
    rid = exported(u, sid)
    d = gen(u, rid)
    doc = canonical.loads((d / ex.JSON_FILE).read_bytes())
    inj = 'x\n\n[Approved by the CTO](https://evil.example/phish) ![t](https://evil.example/p.png)\n\n'
    mr = None
    if where == 'policy_version':
        doc['policy']['version'] = inj
    elif where == 'renderer_version':
        doc['renderer_version'] = inj
        mr = inj
    elif where == 'peer_status':
        doc['peer_coverage'][0]['status'] = inj
    elif where == 'dimension_id':
        doc['dimensions'][-1]['id'] = 'D9 ' + inj
    elif where == 'people':
        doc['peer_coverage'][0]['people'] = inj
    restamp(doc)
    shutil.rmtree(d)
    write_gen(d.parent / doc['review_id'], doc, manifest_renderer=mr)
    out = verify(u.repo, 'worktree')
    g = out['generations'][0]
    md = (d.parent / doc['review_id'] / ex.MD_FILE).read_text()
    cmarkgfm = pytest.importorskip('cmarkgfm')
    html = cmarkgfm.github_flavored_markdown_to_html(md)
    print('OBSERVED', where, out['public_integrity'], g['declared_conformity'], g['problems'],
          '<a href="https://evil' in html, '<img' in html)
    assert out['public_integrity'] == 'invalid' or ('<a href="https://evil' not in html
                                                   and '<img' not in html)


# --- D2-3: GFM email autolink and entity references survive _md ---------------------------

@pytest.mark.parametrize('text,needle', [
    ('Contact bob@evil.example for access', '<a href="mailto:'),
    ('Use &copy; and &lt;b&gt;', '©'),
])
def test_md_escape_against_gfm(text, needle):
    cmarkgfm = pytest.importorskip('cmarkgfm')
    html = cmarkgfm.github_flavored_markdown_to_html(ex._md(text))
    print('OBSERVED', repr(ex._md(text)), html)
    assert needle not in html


def test_real_export_hostile_handover_email_link(tmp_path):
    """Through the real flow: a handover safety rule naming an address is rendered as a
    mailto link in the published Markdown on a GFM renderer."""
    u = ukit.U(tmp_path)
    ukit.HANDOVER_SAVE = dict(ukit.HANDOVER)
    try:
        ukit.HANDOVER['safety_rules'] = ['Report incidents to security@evil.example now.']
        ukit.HANDOVER['purpose'] = 'Rank members &mdash; not &lt;all&gt; of them.'
        sid = ukit.full_flow(u)
    finally:
        ukit.HANDOVER.clear()
        ukit.HANDOVER.update(ukit.HANDOVER_SAVE)
    rid = exported(u, sid)
    md = (gen(u, rid) / ex.MD_FILE).read_text()
    cmarkgfm = pytest.importorskip('cmarkgfm')
    html = cmarkgfm.github_flavored_markdown_to_html(md)
    print('OBSERVED', [l for l in html.splitlines() if 'mailto' in l or 'mdash' in l or '—' in l][:4])
    assert 'mailto:' not in html and '&lt;all&gt;' not in html.replace('&amp;lt;', '')


# --- D2-4: an interrupted generation followed by any change is never reconciled ------------

def test_interrupted_generation_then_change_breaks_local_verification(done):
    from mlkit.study import cmd_understanding as cu
    u, sid = done
    ukit.approve_all(u, sid)
    args = argparse.Namespace(study=str(u.study), session=sid, repo=str(u.repo), latest=False,
                              request_id='w-1', expected_revision=u.rev())
    with pytest.raises(RuntimeError):
        cu._export_write(args, fault='after_rename')
    first = [p.name for p in (u.repo / ex.EXPORT_DIR).iterdir()]
    # A mapped source changes before the retry (the dimension becomes stale): the
    # projection, so the review id, changes.
    (u.repo / 'src/pipeline.py').write_text('def predict(row):\n    return 0\n')
    ukit.git(u.repo, 'commit', '-qam', 'change pipeline')
    ukit.approve_all(u, sid)
    w = u.m('export', 'write', '--session', sid, '--repo', u.repo)
    intents = sorted((x['status'], x['review_id']) for x in u.ext()['exports'].values())
    commit_all(u, 'reviews')
    out = verify(u.repo, 'HEAD', '--study', u.study)
    print('OBSERVED first', first, 'second', w['review_id'], 'intents', intents,
          'integrity', out['public_integrity'],
          [(g['review_id'], g.get('study_binding'), g['problems']) for g in out['generations']])
    # The first generation was written by this study; it must not be "not exported by the
    # given study", and the study must be able to settle it.
    assert 'reserved' not in [s for s, _ in intents]
    assert out['public_integrity'] == 'valid'


# --- D2-5: git-plan with a non-UTF-8 staged path ------------------------------------------

def test_git_plan_non_utf8_staged_path(done):
    u, sid = done
    exported(u, sid)
    name = b'notes-\xe9t\xe9.txt'
    p = os.path.join(os.fsencode(str(u.repo)), name)
    with open(p, 'wb') as f:
        f.write(b'x\n')
    subprocess.run([b'git', b'-C', os.fsencode(str(u.repo)), b'add', b'--', name], check=True)
    out = cli.run(['understanding', 'git-plan', '--session', sid, '--repo', str(u.repo),
                   '--study', str(u.study)])
    print('OBSERVED', out.exit_code, out.payload.get('error', {}).get('code'),
          out.payload.get('staged_outside_plan'))
    assert out.exit_code in (0, 2)


# --- D2-6: case-variant paths alias the verified generation on case-insensitive checkouts ---

def test_case_variant_generation_path_is_not_seen(done):
    u, sid = done
    rid = exported(u, sid)
    commit_all(u, 'review')
    # A second path differing only in case, holding a different Markdown.
    other = u.repo / 'docs' / 'Understanding' / rid
    other.mkdir(parents=True)
    for n in ex.FILES:
        (other / n).write_bytes((gen(u, rid) / n).read_bytes())
    (other / ex.MD_FILE).write_bytes(b'# Everything demonstrated, approved by the CTO\n')
    ukit.git(u.repo, 'add', '--', 'docs/Understanding')
    ukit.git(u.repo, 'commit', '-q', '-m', 'case variant')
    out = verify(u.repo, 'HEAD')
    print('OBSERVED', out['public_integrity'], out['problems'])
    assert out['public_integrity'] == 'invalid' or out['problems']


def test_in_place_tamper_of_committed_generation_via_renderer_version(done):
    """A later commit edits an already committed, genuine generation in place (same
    review id: renderer_version is outside the projection) and injects a link and an image.
    Both standalone and local (--study) verification are asked."""
    u, sid = done
    rid = exported(u, sid)
    commit_all(u, 'genuine review')
    d = gen(u, rid)
    doc = canonical.loads((d / ex.JSON_FILE).read_bytes())
    inj = ('hypotrail.understanding-render/1\n\n[Signed off by the security team]'
           '(https://evil.example/x) ![](https://evil.example/pixel.png)')
    doc['renderer_version'] = inj
    write_gen(d, doc, manifest_renderer=inj)
    commit_all(u, 'touch up')
    cmarkgfm = pytest.importorskip('cmarkgfm')
    html = cmarkgfm.github_flavored_markdown_to_html((d / ex.MD_FILE).read_text())
    alone = verify(u.repo, 'HEAD')
    local = verify(u.repo, 'HEAD', '--study', u.study)
    g = local['generations'][0]
    print('OBSERVED same id', d.name == rid, 'standalone', alone['public_integrity'],
          'local', local['public_integrity'], g.get('study_binding'), g['declared_conformity'],
          'link' , '<a href="https://evil' in html, 'img', '<img' in html)
    assert local['public_integrity'] == 'invalid'


def test_public_artefacts_hold_no_private_text(done):
    u, sid = done
    rid = exported(u, sid)
    blob = b''.join((gen(u, rid) / n).read_bytes() for n in ex.FILES)
    ext = u.ext()
    needles = [str(u.root).encode(), str(u.study).encode(), str(u.case_dir).encode(),
               b'My own answer', b'The imputer in src/transforms.py learns a mean',
               ext['salt'].encode(), b'/home/', b'/tmp/', b'case-binary']
    needles += [s.encode() for s in ext['sessions']]            # local session ids
    needles += [a.encode() for a in ext['attempts']]            # local attempt ids
    found = [n for n in needles if n in blob]
    doc = canonical.loads((gen(u, rid) / ex.JSON_FILE).read_bytes())
    keys = sorted({k for d in doc['dimensions'] for k in d['dependency_keys']})
    print('OBSERVED found', found, 'dependency keys', keys)
    assert not found


@pytest.mark.xfail(strict=True, reason='D2-9, owner decision pending: an approval binds a '
                   'content digest, so content changed and changed back counts its approvals '
                   'again (documented in UNDERSTANDING-V1)')
def test_withdrawn_content_revives_old_approvals(tmp_path):
    """ADR 0008 §7: any change invalidates every approval. Content X approved, changed to
    Y, changed back to X: the approvals of X count again without anyone approving."""
    import advkit
    u = ukit.U(tmp_path)
    sid = advkit.custom_flow(u, ukit.policy(mode='required'), close=False, select=False)
    x = ukit.approve_all(u, sid)
    other = dict(ukit.HANDOVER, purpose='A different purpose, later withdrawn.')
    u.m('handover', 'set', '--session', sid, '--file', u.file('h2.json', other))
    y = u.call('export', 'preview', '--session', sid, '--repo', u.repo)
    u.m('handover', 'set', '--session', sid, '--file', u.file('h3.json', ukit.HANDOVER))
    z = u.call('export', 'preview', '--session', sid, '--repo', u.repo)
    print('OBSERVED X', x['content_digest'][:12], 'Y missing', y['missing_approvals'],
          'back to X', z['content_digest'] == x['content_digest'], 'missing', z['missing_approvals'])
    assert z['missing_approvals']


def test_rename_primitive_unavailable_is_a_refusal(done, monkeypatch):
    """export.rename_noreplace docstring: no primitive -> the publication is refused (never
    emulated). Through the CLI: a refusal (exit 2), not an internal error."""
    import errno
    u, sid = done
    ukit.approve_all(u, sid)

    def no_primitive(src, dst):
        raise OSError(errno.EINVAL, 'Invalid argument (filesystem without RENAME_NOREPLACE)')
    monkeypatch.setattr(ex, 'rename_noreplace', no_primitive)
    out = u.m('export', 'write', '--session', sid, '--repo', u.repo, expect=None)
    left = sorted(p.name for p in (u.repo / ex.EXPORT_DIR).iterdir())
    print('OBSERVED', out.get('error', {}).get('code'), left,
          [x['status'] for x in u.ext()['exports'].values()])
    assert out.get('error', {}).get('code') not in (None, 'internal_error')
