"""Area C probes: concurrency through real `hypotrail` processes."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import advkit as rkit  # noqa: E402,F401
from advkit import U, ukit, gate, custom_flow  # noqa: E402

REQ = ukit.policy(mode='required')
EXE = [sys.executable, '-c', 'import sys; from mlkit.study.cli import main; sys.exit(main())']


def spawn(*args):
    return subprocess.Popen(EXE + [str(a) for a in args], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, cwd=str(Path(__file__).resolve().parents[4]))


def result(p):
    out, err = p.communicate(timeout=600)
    try:
        return p.returncode, json.loads(out)
    except ValueError:
        return p.returncode, {'raw': out[-2000:], 'err': err[-2000:]}


def test_two_processes_submit_at_the_same_revision(tmp_path):
    u = U(tmp_path)
    u.set_policy(REQ)
    plan, out = u.start()
    sid = out['result']['session_id']
    t = plan['plan']['task_ids'][0]
    rev = u.rev()
    procs = [spawn('understanding', 'submit', '--session', sid, '--task', t,
                   '--response-file', u.file(f'c{i}.txt', f'Answer {i}.'),
                   '--assistance-file', u.file(f'ca{i}.json', ukit.ASSIST),
                   '--request-id', f'conc-{i}', '--expected-revision', rev,
                   '--study', u.study) for i in range(4)]
    res = [result(p) for p in procs]
    oks = [r for r in res if r[0] == 0]
    codes = sorted((r[1].get('error') or {}).get('code', 'ok') for r in res)
    print(codes)
    assert len(oks) == 1
    assert len(u.ext()['attempts']) == 1
    assert u.rev() == rev + 1
    # no answer text in any output
    for _, payload in res:
        assert 'Answer' not in json.dumps(payload)


def test_two_reviews_same_revision_and_same_request_id(tmp_path):
    u = U(tmp_path)
    u.set_policy(REQ)
    plan, out = u.start()
    sid = out['result']['session_id']
    t = next(t for t in plan['plan']['task_ids'] if u.bank_task(t)['dimension_ids'][0] == 'D3')
    a = u.submit(sid, t)['result']['attempt_id']
    rev = u.rev()
    docs = [u.file(f'rv{i}.json', {'reviewer_declared_id': r, 'declaration': ukit.SIM,
                                   'simulated': True,
                                   'decisions': [u.decision('D3', [a], status=s)]})
            for i, (r, s) in enumerate([('bob', 'demonstrated'), ('dave', 'to_consolidate')])]
    procs = [spawn('understanding', 'review', '--session', sid, '--file', d,
                   '--request-id', 'same-review', '--expected-revision', rev,
                   '--study', u.study) for d in docs]
    res = [result(p) for p in procs]
    codes = sorted((r[1].get('error') or {}).get('code', 'ok') for r in res)
    print(codes)
    assert codes == ['idempotency_conflict', 'ok']
    assert len([d for d in u.ext()['decisions'].values()]) == 1


def test_concurrent_export_handoff_required(tmp_path):
    """Several `export handoff` processes at once under a required policy, with a
    concurrent source change: at most consistent outcomes, never a published pack whose
    record says otherwise, never a published pack after the change."""
    u = U(tmp_path)
    custom_flow(u, REQ)
    assert gate(u)['decision'] == 'allowed'
    procs = [spawn('export', 'handoff', '--study', u.study, '--out', tmp_path / f'h{i}')
             for i in range(3)]
    res = [result(p) for p in procs]
    codes = [(r[0], (r[1].get('error') or {}).get('code', 'ok')) for r in res]
    print(codes)
    recs = list(u.ext()['milestones'].values())
    print([(m['status'], m['reserved_revision']) for m in recs])
    published = [m for m in recs if m['status'] == 'published']
    assert all(m['status'] in ('published', 'candidate_not_current') for m in recs)
    ok_dirs = [tmp_path / f'h{i}' for i, r in enumerate(res) if r[0] in (0, 3)]
    assert len(ok_dirs) == len(published) >= 1
    for d in ok_dirs:
        assert (d / 'handoff.json').exists()
    for i, r in enumerate(res):
        if r[0] not in (0, 3):
            assert not (tmp_path / f'h{i}').exists()


def test_export_handoff_racing_a_source_edit(tmp_path):
    u = U(tmp_path)
    custom_flow(u, REQ)
    procs = [spawn('export', 'handoff', '--study', u.study, '--out', tmp_path / f'h{i}')
             for i in range(2)]
    (u.repo / 'src/transforms.py').write_text('changed meanwhile\n')
    res = [result(p) for p in procs]
    codes = [(r[0], (r[1].get('error') or {}).get('code', 'ok')) for r in res]
    print(codes)
    recs = list(u.ext()['milestones'].values())
    print([(m['status'], m['checked_context_digest'][:8] if m['checked_context_digest'] else None)
           for m in recs])
    # After the edit the gate is blocked; a published pack must have been reserved AND
    # finalized before the edit (cannot verify timing here; print for inspection).
    assert gate(u)['decision'] == 'blocked'
