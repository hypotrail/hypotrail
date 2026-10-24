"""Area D review: export, approvals, publication, Git path, verifier."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'understanding'))

import ukit  # noqa: E402
from mlkit.study import cli  # noqa: E402
from mlkit.study.understanding import canonical, export as ex  # noqa: E402


def code(p):
    return p['error']['code']


def verify(repo, target, *extra):
    out = cli.run(['understanding', 'verify-export', '--repo', str(repo), '--target', target,
                   *map(str, extra)])
    return out.payload


@pytest.fixture
def done(tmp_path):
    u = ukit.U(tmp_path)
    sid = ukit.full_flow(u)
    return u, sid


def exported(u, sid):
    ukit.approve_all(u, sid)
    w = u.m('export', 'write', '--session', sid, '--repo', u.repo)
    return w['review_id']


def gen(u, rid):
    return u.repo / ex.EXPORT_DIR / rid


def rewrite(dirpath: Path, doc: dict, *, rename=True) -> Path:
    """Rewrite a generation consistently (new review id from the projection, new
    Markdown, new manifest) — what any forger can do since nothing is signed."""
    proj = ex.approval_projection(doc)
    rid = ex.review_id(proj)
    doc = dict(doc, review_id=rid)
    files = ex.files_of(doc)
    target = dirpath.parent / rid if rename else dirpath
    if target != dirpath:
        shutil.rmtree(dirpath)
        target.mkdir()
    for n, data in files.items():
        (target / n).write_bytes(data)
    return target


# --- verifier: approval invariants ---------------------------------------------------------

def test_verifier_accepts_review_whose_contributors_did_not_approve(done):
    """privacy_review lists fewer required contributors than the aliases published; the
    approvals of bob and carol are removed. Expected: invalid or nonconforming."""
    u, sid = done
    rid = exported(u, sid)
    d = gen(u, rid)
    doc = canonical.loads((d / ex.JSON_FILE).read_bytes())
    assert {'bob', 'carol'} <= set(ex.required_contributors(ex.approval_projection(doc)))
    pr = doc['privacy_review']
    pr['approvals'] = [a for a in pr['approvals'] if a['approver_alias'] == 'alice']
    pr['required_contributors'] = ['alice']
    rewrite(d, doc, rename=False)
    out = verify(u.repo, 'worktree')
    g = out['generations'][0]
    strict = u.file('rel.json', ukit.policy(mode='required', context_requirement='public_only',
                                            evidence_requirement='recorded_decisions'))
    gated = verify(u.repo, 'worktree', '--policy-file', strict)['generations'][0]
    print('OBSERVED', g['public_integrity'], g['declared_conformity'], g['problems'],
          gated['gate_result'])
    assert g['public_integrity'] == 'invalid' or g['declared_conformity'] == 'nonconforming' \
        or gated['gate_result']['decision'] == 'blocked'


def test_verifier_accepts_approved_status_with_no_approval_at_all(done):
    u, sid = done
    rid = exported(u, sid)
    d = gen(u, rid)
    doc = canonical.loads((d / ex.JSON_FILE).read_bytes())
    doc['privacy_review'] = {'status': 'approved', 'required_contributors': [], 'approvals': []}
    rewrite(d, doc, rename=False)
    g = verify(u.repo, 'worktree')['generations'][0]
    print('OBSERVED', g['public_integrity'], g['declared_conformity'], g['problems'])
    assert g['public_integrity'] == 'invalid' or g['declared_conformity'] != 'conforming'


# --- verifier: local mode binds the artefact to the study? ---------------------------------

def test_local_mode_does_not_bind_artefact_to_the_study_export(done):
    """A forged generation (rationale and status changed, then everything recomputed and
    approvals re-stamped) carrying the real session_ref: in local mode, the study recorded
    another projection digest. Expected: the local check notices."""
    u, sid = done
    rid = exported(u, sid)
    d = gen(u, rid)
    doc = canonical.loads((d / ex.JSON_FILE).read_bytes())
    doc['dimensions'][0]['rationale'] = 'Forged rationale nobody approved.'
    doc['handover_content'] = dict(doc['handover_content'], purpose='Forged purpose.')
    doc['handover_digest'] = canonical.digest(doc['handover_content'])
    digest = canonical.digest(ex.approval_projection(doc))
    for a in doc['privacy_review']['approvals']:
        a['content_digest'] = digest
    shutil.rmtree(d)
    d.mkdir()
    new = rewrite(d, doc)
    ukit.git(u.repo, 'add', '--', ex.EXPORT_DIR)
    ukit.git(u.repo, 'commit', '-q', '-m', 'forged')
    out = verify(u.repo, 'HEAD', '--study', u.study)
    g = out['generations'][0]
    print('OBSERVED', new.name, {k: g[k] for k in ('public_integrity', 'declared_conformity',
                                                  'private_context_verification',
                                                  'evidence_availability')})
    recorded = {x['projection_digest'] for x in u.ext()['exports'].values()}
    assert digest not in recorded
    assert g['private_context_verification'] != 'verified' or \
        g['declared_conformity'] != 'conforming' or g['public_integrity'] != 'valid'


# --- verifier: Git tree with duplicate entries ------------------------------------------------

def _mktree_literal(repo, entries):
    """entries: list of (mode, name, oid hex); write a raw tree (duplicates allowed)."""
    body = b''.join(m.encode() + b' ' + n.encode() + b'\0' + bytes.fromhex(o)
                    for m, n, o in entries)
    p = subprocess.run(['git', '-C', str(repo), 'hash-object', '-t', 'tree', '--literally',
                        '-w', '--stdin'], input=body, capture_output=True, check=True)
    return p.stdout.decode().strip()


def test_duplicate_entries_in_a_commit_tree_are_not_refused(done, tmp_path):
    u, sid = done
    rid = exported(u, sid)
    ukit.git(u.repo, 'add', '--', ex.EXPORT_DIR)
    ukit.git(u.repo, 'commit', '-q', '-m', 'review')
    repo = u.repo
    gtree = ukit.git(repo, 'rev-parse', f'HEAD:{ex.EXPORT_DIR}/{rid}')
    lines = ukit.git(repo, 'ls-tree', gtree).splitlines()
    ents = []
    for ln in lines:
        meta, name = ln.split('\t')
        mode, _, oid = meta.split()
        ents.append((mode, name, oid))
    bad = subprocess.run(['git', '-C', str(repo), 'hash-object', '-w', '--stdin'],
                         input=b'TAMPERED markdown\n', capture_output=True,
                         check=True).stdout.decode().strip()
    new = []
    for m, n, o in ents:
        if n == ex.MD_FILE:
            new.append((m, n, bad))          # first (what a checkout may take)
        new.append((m, n, o))
    t_gen = _mktree_literal(repo, new)
    # rebuild parents: docs/understanding/<rid>
    def replace(tree_oid, name, child):
        out = []
        for ln in ukit.git(repo, 'ls-tree', tree_oid).splitlines():
            meta, n = ln.split('\t')
            mode, _, oid = meta.split()
            out.append((mode, n, child if n == name else oid))
        return _mktree_literal(repo, out)
    und = ukit.git(repo, 'rev-parse', f'HEAD:{ex.EXPORT_DIR}')
    docs = ukit.git(repo, 'rev-parse', 'HEAD:docs')
    root = ukit.git(repo, 'rev-parse', 'HEAD^{tree}')
    t_und = replace(und, rid, t_gen)
    t_docs = replace(docs, 'understanding', t_und)
    t_root = replace(root, 'docs', t_docs)
    c = ukit.git(repo, 'commit-tree', t_root, '-p', 'HEAD', '-m', 'dup')
    listing = ukit.git(repo, 'ls-tree', '-r', c, '--', f'{ex.EXPORT_DIR}/{rid}/')
    assert listing.count(ex.MD_FILE) == 2
    out = verify(repo, c)
    print('OBSERVED', out['public_integrity'], out['problems'])
    shown = subprocess.run(['git', '-C', str(repo), 'show', f'{c}:{ex.EXPORT_DIR}/{rid}/{ex.MD_FILE}'], capture_output=True).stdout[:20]
    wt = tmp_path / 'wt'
    subprocess.run(['git', '-C', str(repo), 'worktree', 'add', '-q', '--detach', str(wt), c], capture_output=True)
    co = (wt / ex.EXPORT_DIR / rid / ex.MD_FILE).read_bytes()[:20] if (wt / ex.EXPORT_DIR / rid / ex.MD_FILE).exists() else None
    fsck = subprocess.run(['git', '-C', str(repo), 'fsck'], capture_output=True, text=True)
    print('GIT-SHOW', shown, 'CHECKOUT', co, 'FSCK', fsck.returncode, fsck.stderr[-200:], fsck.stdout[-200:])
    assert out['public_integrity'] == 'invalid'


# --- verifier: index vs worktree --------------------------------------------------------------

def test_index_target_reads_index_bytes(done):
    u, sid = done
    rid = exported(u, sid)
    plan = u.call('git-plan', '--session', sid, '--repo', u.repo)
    u.call('git-stage', '--session', sid, '--repo', u.repo, '--index-identity',
           plan['index_identity'])
    # worktree tampered: index still valid
    md = gen(u, rid) / ex.MD_FILE
    good = md.read_bytes()
    md.write_bytes(b'tampered\n')
    assert verify(u.repo, 'index')['public_integrity'] == 'valid'
    assert verify(u.repo, 'worktree')['public_integrity'] == 'invalid'
    # index tampered, worktree restored
    ukit.git(u.repo, 'add', '--', str(md.relative_to(u.repo)))
    md.write_bytes(good)
    assert verify(u.repo, 'index')['public_integrity'] == 'invalid'
    assert verify(u.repo, 'worktree')['public_integrity'] == 'valid'


# --- verifier: hostile repository configuration ----------------------------------------------

def test_hostile_config_never_runs(done, tmp_path):
    u, sid = done
    rid = exported(u, sid)
    ukit.git(u.repo, 'add', '--', ex.EXPORT_DIR)
    ukit.git(u.repo, 'commit', '-q', '-m', 'review')
    trace = tmp_path / 'TRACE'
    script = tmp_path / 'evil.sh'
    script.write_text(f'#!/bin/sh\necho "$0 $@" >> {trace}\ncat\n')
    script.chmod(0o755)
    inc = tmp_path / 'inc.config'
    inc.write_text(f'[core]\n\tfsmonitor = {script}\n')
    cfg = [('core.fsmonitor', str(script)), ('core.pager', str(script)),
           ('pager.ls-files', str(script)), ('diff.external', str(script)),
           ('filter.evil.smudge', str(script)), ('filter.evil.clean', str(script)),
           ('filter.evil.process', str(script)), ('core.hooksPath', str(tmp_path)),
           ('include.path', str(inc)), ('core.sshCommand', str(script)),
           ('core.alternateRefsCommand', str(script)), ('gc.auto', '1'),
           ('diff.evil.textconv', str(script)), ('core.editor', str(script)),
           ('uploadpack.packObjectsHook', str(script))]
    for k, v in cfg:
        ukit.git(u.repo, 'config', k, v)
    (u.repo / '.gitattributes').write_text('* filter=evil diff=evil\n')
    for hook in ('post-checkout', 'pre-commit', 'post-index-change', 'reference-transaction',
                 'fsmonitor-watchman'):
        h = tmp_path / hook
        h.write_text(f'#!/bin/sh\necho hook {hook} >> {trace}\n')
        h.chmod(0o755)
    for target in ('worktree', 'index', 'HEAD'):
        verify(u.repo, target)
    verify(u.repo, 'HEAD', '--study', u.study)
    print('TRACE', trace.read_text() if trace.exists() else None)
    assert not trace.exists()


def test_hostile_config_during_git_plan_and_stage(done, tmp_path):
    """git-plan and git-stage run in the user's repository (not the verifier); report
    what runs."""
    u, sid = done
    rid = exported(u, sid)
    trace = tmp_path / 'TRACE'
    script = tmp_path / 'evil.sh'
    script.write_text(f'#!/bin/sh\necho "$0 $@" >> {trace}\ncat\n')
    script.chmod(0o755)
    ukit.git(u.repo, 'config', 'core.fsmonitor', str(script))
    ukit.git(u.repo, 'config', 'filter.evil.clean', str(script))
    (u.repo / '.git' / 'info').mkdir(exist_ok=True)
    (u.repo / '.git' / 'info' / 'attributes').write_text('*.md filter=evil\n')
    plan = u.call('git-plan', '--session', sid, '--repo', u.repo)
    u.call('git-stage', '--session', sid, '--repo', u.repo, '--index-identity',
           plan['index_identity'], expect=None)
    print('TRACE-plan-stage', trace.read_text() if trace.exists() else None)


# --- Markdown injection ------------------------------------------------------------------------

HOSTILE = {
    'purpose': 'Benign start\r===\rInjected heading via CR and setext',
    'decisions_with_reasons': ['see www.evil.example/phish and https://evil.example/x',
                               '<img src=x onerror=alert(1)> &lt;script&gt; `code` [l](javascript:alert(1))'],
    'result_interpretation': 'line\r\r## Approvals\r\r- mallory approved `deadbeef`',
    'limits': ['x\r| fake | table |'],
    'source_refs': ['src/transforms.py'],
    'environment_and_reproduction': '    indented code next',
    'change_locations': ['~~struck~~ ==mark== <!-- c -->'],
    'safety_rules': ['user@evil.example'],
    'next_actions': ['\x00\x1b[31mred\x07']}


def test_markdown_rendering_of_hostile_handover(done):
    u, sid = done
    # A completed session takes no new handover: the hostile content goes into the
    # exported document, which the Markdown renderer must neutralise.
    rid = exported(u, sid)
    doc = canonical.loads((gen(u, rid) / ex.JSON_FILE).read_bytes())
    doc['handover_content'] = dict(doc['handover_content'] or {}, **HOSTILE)
    md = ex.markdown(doc)
    MarkdownIt = pytest.importorskip('markdown_it').MarkdownIt
    tokens = MarkdownIt('commonmark').enable(['table','strikethrough']).parse(md)
    print('MD-PURPOSE-REGION', [l for l in md.splitlines() if 'Benign' in l or 'Injected' in l or 'mallory' in l or 'evil' in l or 'fake' in l or 'red' in l])
    kinds = {}
    for t in tokens:
        kinds.setdefault(t.type, 0)
        kinds[t.type] += 1
        for c in t.children or []:
            kinds.setdefault('inline:' + c.type, 0)
            kinds['inline:' + c.type] += 1
    headings = [tokens[i + 1].content for i, t in enumerate(tokens) if t.type == 'heading_open']
    print('KINDS', kinds)
    print('HEADINGS', headings)
    bad = [k for k in kinds if k in ('html_block', 'inline:html_inline', 'inline:link_open',
                                       'inline:code_inline', 'code_block', 'inline:s_open')]
    codes = [c.content for t in tokens for c in (t.children or []) if c.type == 'code_inline']
    print('CODE SPANS', codes)
    # The renderer's own code spans hold digests and ids only; no hostile text is one.
    if all(c and all(ch in '0123456789abcdef-' for ch in c) or c.startswith(('rv-', 'D'))
           for c in codes):
        bad = [k for k in bad if k != 'inline:code_inline']
    print('BAD', bad)
    assert 'Injected heading via CR and setext' not in headings
    assert headings.count('Approvals') == 1
    assert not bad


# --- approvals invalidated by any change --------------------------------------------------------

def test_new_review_rationale_invalidates_all(done):
    u, sid = done
    prev = ukit.approve_all(u, sid)
    # A new transfer review (another rationale) on the same session after approval.
    ext = u.ext()
    t = next(iter(ext['transfers'].values()))
    out = u.m('transfer', 'review', '--transfer', t['transfer_id'], '--file', u.file(
        'pr2.json', {'reviewer_declared_id': 'alice', 'declaration': ukit.SIM,
                     'simulated': True, 'dimension_ids': ['D2'], 'status': 'demonstrated',
                     'rationale': 'Another rationale.'}), expect=None)
    print('second transfer review', out.get('ok'), out.get('error', {}).get('code'))
    again = u.call('export', 'preview', '--session', sid, '--repo', u.repo)
    if out.get('ok'):
        assert again['content_digest'] != prev['content_digest']
        assert set(again['missing_approvals']) == set(again['required_contributors'])


def test_source_change_after_approval_invalidates(done):
    u, sid = done
    prev = ukit.approve_all(u, sid)
    (u.repo / 'src/transforms.py').write_text('changed\n')
    again = u.call('export', 'preview', '--session', sid, '--repo', u.repo)
    assert again['content_digest'] != prev['content_digest']
    out = u.m('export', 'write', '--session', sid, '--repo', u.repo, expect=2)
    assert code(out) == 'privacy_approval_required'


# --- private data in the exported bytes ---------------------------------------------------------

def test_no_private_values_in_export(done):
    u, sid = done
    rid = exported(u, sid)
    text = b''.join((gen(u, rid) / n).read_bytes() for n in ex.FILES).decode()
    ext = u.ext()
    state = u.state()
    s = ext['sessions'][sid]
    from mlkit.study.understanding import service as sv
    store = sv.open_store(u.study)
    snapdoc = sv.session_snapshot(store, s)
    secrets_ = {'salt': ext['salt'], 'session_id': sid,
                'local_snapshot_digest': s['local_snapshot_digest'],
                'case_id': str((state.get('case') or {}).get('id')),
                'study_path': str(u.study), 'root': str(u.root)}
    for e in snapdoc['local']['entries']:
        if e['origin'] != 'repo' and e['origin'] != 'contract':
            secrets_[e['logical_key']] = e['sha256']
    for aid, a in ext['attempts'].items():
        secrets_['attempt:' + aid] = aid
    for tid in ext['transfers']:
        secrets_['transfer:' + tid] = tid
    for k, v in ext['approvals'].items():
        secrets_['approval:' + k] = k
    leaks = {k: v for k, v in secrets_.items() if v and v in text}
    print('LEAKS', leaks)
    assert not leaks


# --- publication concurrency -------------------------------------------------------------------

def test_threads_publish_same_and_different_bytes(tmp_path):
    repo = tmp_path / 'r'
    repo.mkdir()
    rid = 'rv-' + '0' * 20
    a = {n: b'A-' + n.encode() for n in ex.FILES}
    b = {n: b'B-' + n.encode() for n in ex.FILES}
    results = []

    def run(files):
        try:
            results.append((files is a, ex.publish(repo, rid, files)))
        except Exception as exc:     # noqa: BLE001
            results.append((files is a, getattr(exc, 'code', repr(exc))))
    ths = [threading.Thread(target=run, args=(a if i % 2 else b,)) for i in range(40)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    dest = repo / ex.EXPORT_DIR / rid
    names = sorted(p.name for p in dest.iterdir())
    contents = {(dest / n).read_bytes()[:1] for n in names}
    winners = {r for r in results if r[1] == 'published'}
    print('RESULTS', sorted(set(results)))
    assert names == sorted(ex.FILES) and len(contents) == 1
    assert len(winners) == 1
    leftovers = [p.name for p in (repo / ex.EXPORT_DIR).iterdir() if p.name != rid]
    assert leftovers == []


def _proc_write(study, sid, repo, rid, rev, q):
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / 'understanding'))
    from mlkit.study import cli as c2
    out = c2.run(['understanding', 'export', 'write', '--session', sid, '--repo', repo,
                  '--study', study, '--request-id', rid, '--expected-revision', str(rev)])
    q.put((rid, out.exit_code, out.payload.get('error', {}).get('code'),
           out.payload.get('publication')))


def test_processes_export_concurrently(done):
    import multiprocessing as mp
    u, sid = done
    ukit.approve_all(u, sid)
    rev = u.rev()
    ctx = mp.get_context('fork')
    q = ctx.Queue()
    ps = [ctx.Process(target=_proc_write, args=(str(u.study), sid, str(u.repo), f'cw{i}', rev, q))
          for i in range(6)]
    for p in ps:
        p.start()
    for p in ps:
        p.join(120)
    res = [q.get() for _ in ps]
    print('RESULTS', res)
    base = u.repo / ex.EXPORT_DIR
    gens = [p for p in base.iterdir()]
    print('DIRS', [p.name for p in gens])
    assert len([p for p in gens if p.name.startswith('rv-')]) == 1
    assert not [p for p in gens if p.name.startswith('.')]
    ok = [r for r in res if r[1] == 0]
    assert ok
    intents = list(u.ext()['exports'].values())
    print('INTENTS', [(x['status'], x['review_id']) for x in intents])
    assert len(intents) == 1 and intents[0]['status'] == 'published'
    # Every retry with any request id now reconciles
    again = u.m('export', 'write', '--session', sid, '--repo', u.repo, expect=None)
    print('RETRY', again.get('publication'), again.get('error', {}).get('code'))
    assert again.get('publication') == 'already_published'


# --- crash between rename and receipt, then a re-approval ----------------------------------------

def test_interrupted_export_then_duplicate_approval_is_stuck(done):
    from mlkit.study import cmd_understanding as cu
    u, sid = done
    prev = ukit.approve_all(u, sid)
    args = argparse.Namespace(study=str(u.study), session=sid, repo=str(u.repo), latest=False,
                              request_id='w-1', expected_revision=u.rev())
    with pytest.raises(RuntimeError):
        cu._export_write(args, fault='after_rename')
    # bob approves the same content again (allowed: same digest)
    u.m('export', 'approve', '--session', sid, '--contributor', 'bob', '--content-digest',
        prev['content_digest'])
    args2 = argparse.Namespace(**{**vars(args), 'expected_revision': u.rev()})
    outs = []
    for a in (args2, argparse.Namespace(**{**vars(args2), 'request_id': 'w-2'})):
        try:
            outs.append(cu._export_write(a)['publication'])
        except Exception as exc:    # noqa: BLE001
            outs.append(getattr(exc, 'code', repr(exc)))
    intents = [(x['status']) for x in u.ext()['exports'].values()]
    print('OUTCOMES', outs, intents)
    assert 'reserved' not in intents, 'the interrupted generation can never be reconciled'


def test_public_freshness_without_any_public_source(tmp_path):
    u = ukit.U(tmp_path)
    u.set_policy(ukit.policy(mode='required', context_requirement='public_only',
                             evidence_requirement='recorded_decisions'))
    plan, out = u.start(sources=[])
    sid = out['result']['session_id']
    rid_ = None
    ukit.approve_all(u, sid)
    w = u.m('export', 'write', '--session', sid, '--repo', u.repo)
    rid_ = w['review_id']
    g = verify(u.repo, 'worktree')['generations'][0]
    doc = canonical.loads((gen(u, rid_) / ex.JSON_FILE).read_bytes())
    print('OBSERVED', g['public_source_freshness'], len(doc['source_manifest']),
          [d['freshness_at_export'] for d in doc['dimensions']])
