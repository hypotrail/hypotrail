"""Area C probes: the gated export handoff and export write retries; coaching never blocks."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import advkit as rkit  # noqa: E402,F401
from advkit import U, ukit, code, gate, custom_flow  # noqa: E402
from mlkit.study import cli  # noqa: E402

REQ = ukit.policy(mode='required')


def handoff(u, out, *extra):
    return cli.run(['export', 'handoff', '--study', str(u.study), '--out', str(out),
                    *[str(x) for x in extra]])


def test_export_write_full_retry_is_a_replay(tmp_path):
    u = U(tmp_path)
    sid = custom_flow(u, REQ)
    ukit.approve_all(u, sid)
    rev = u.rev()
    first = u.m('export', 'write', '--session', sid, '--repo', u.repo, request_id='ew1',
                revision=rev)
    again = u.m('export', 'write', '--session', sid, '--repo', u.repo, request_id='ew1',
                revision=rev, expect=None)
    print(again.get('error') or {k: again[k] for k in ('publication', 'receipt', 'replayed')})
    assert again.get('ok'), again


def test_coaching_and_off_never_block_handoff(tmp_path):
    u = U(tmp_path)
    u.set_policy(ukit.POLICY)                       # coaching, nothing done
    o = handoff(u, tmp_path / 'c')
    assert o.exit_code in (0, 3), o.payload
    assert 'understanding' not in o.payload
    u.set_policy(dict(ukit.POLICY, mode='off'))
    o = handoff(u, tmp_path / 'o')
    assert o.exit_code in (0, 3), o.payload
    g = gate(u)
    assert g['decision'] == 'not_applicable'


def test_gated_handoff_with_expected_revision(tmp_path):
    """Ungated, the pack is at --expected-revision. Gated, --expected-revision is checked
    before the reservation and the pack is rendered at the reservation's revision (one
    more): CLI-CONTRACT §16."""
    u = U(tmp_path)
    custom_flow(u, REQ)
    rev = u.rev()
    o = handoff(u, tmp_path / 'h', '--expected-revision', rev)
    pack = json.loads((tmp_path / 'h' / 'handoff.json').read_text())
    print('expected', rev, 'payload revision', o.payload.get('revision'), 'pack revision',
          pack['revision'], 'study now', u.rev())
    assert o.exit_code in (0, 3)
    rec = [m for m in u.ext()['milestones'].values() if m['status'] == 'published']
    assert pack['revision'] == rev + 1 == rec[0]['reserved_revision']
    stale = handoff(u, tmp_path / 'h3', '--expected-revision', rev)
    assert code(stale.payload) == 'stale_revision'


def test_gated_handoff_into_an_existing_folder_reason(tmp_path):
    u = U(tmp_path)
    custom_flow(u, REQ)
    target = tmp_path / 'h'
    target.mkdir()
    (target / 'other.txt').write_text('mine')
    o = handoff(u, target)
    print(o.exit_code, o.payload.get('error'))
    assert code(o.payload) != 'context_changed', 'reported as a concurrent change'


def test_gated_handoff_record_matches_the_files(tmp_path):
    u = U(tmp_path)
    custom_flow(u, REQ)
    o = handoff(u, tmp_path / 'h')
    rec = [m for m in u.ext()['milestones'].values() if m['status'] == 'published']
    assert len(rec) == 1
    import hashlib
    for f in o.payload['files']:
        data = (tmp_path / 'h' / f['path']).read_bytes()
        assert hashlib.sha256(data).hexdigest() == f['sha256'] == rec[0]['outcome']['files'][f['path']]
    # the pack's handoff.json carries no understanding data (answers etc.)
    text = ''.join((tmp_path / 'h' / f['path']).read_text(errors='replace') for f in o.payload['files'])
    assert 'My own answer' not in text
