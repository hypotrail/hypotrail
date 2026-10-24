"""Area C probes: handover versioning across linked sessions, vacuous policies, waivers,
reservation release after a failed handoff."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import advkit as rkit  # noqa: E402,F401
from advkit import U, ukit, code, gate, custom_flow  # noqa: E402
from mlkit.study import cli  # noqa: E402

REQ = ukit.policy(mode='required')


def test_newer_handover_in_a_linked_session_stales_the_old_transfer(tmp_path):
    u = U(tmp_path)
    sid = custom_flow(u, REQ)
    assert gate(u)['decision'] == 'allowed'
    # The author opens a linked session and records a shorter note (a removal).
    args = ['plan', '--profile', 'pipeline', '--milestone', 'handoff', '--actor', 'alice',
            '--previous-session', sid, '--repo', u.repo, '--sources-file',
            u.file('s2.json', ukit.SOURCES), '--write-plan', u.root / 'inputs' / 'p2.json']
    u.call(*args)
    s2 = u.m('start', '--plan-file', u.root / 'inputs' / 'p2.json')['result']['session_id']
    u.m('handover', 'set', '--session', s2, '--file',
        u.file('h2.json', dict(ukit.HANDOVER, safety_rules=[])))
    g = gate(u)
    print(g['decision'], g['reasons'])
    assert g['decision'] == 'blocked', 'the transfer on the older note is still current'


def test_required_policy_requiring_nothing(tmp_path):
    u = U(tmp_path)
    pol = ukit.policy(mode='required', required_dimensions=[],
                      responsibility_profiles={'pipeline': []}, critical_dimensions=[],
                      peer_required_dimensions=[])
    out = u.m('policy', 'set', '--file', u.file('empty-policy.json', pol), '--author', 'lead',
              '--reason', 'probe',
              expect=2)
    assert code(out) == 'policy_invalid', out


def test_waiver_approved_by_the_author(tmp_path):
    u = U(tmp_path)
    custom_flow(u, ukit.policy(mode='required', exemptions_policy={'waivers_allowed': True}))
    (u.repo / 'SECURITY.md').write_text('changed\n')
    assert gate(u)['decision'] == 'blocked'
    u.m('waive', '--file', u.file('w.json', {
        'milestone': 'handoff', 'dimensions': ['D8'], 'reason': 'mine', 'scope': 'x',
        'approver_declared_id': 'alice', 'expires_on': '2999-01-01',
        'unmet_requirements': []}))
    g = gate(u)
    print(g['decision'])
    assert g['decision'] == 'blocked', 'the author waived their own requirement'


def test_failed_handoff_releases_the_reservation(tmp_path):
    u = U(tmp_path)
    custom_flow(u, REQ)
    target = tmp_path / 'h'
    target.mkdir()
    (target / 'x').write_text('x')
    o = cli.run(['export', 'handoff', '--study', str(u.study), '--out', str(target)])
    assert o.exit_code == 2
    recs = list(u.ext()['milestones'].values())
    print([m['status'] for m in recs])
    assert all(m['status'] != 'reserved' for m in recs)


def test_task_and_errors_never_show_answers_or_rubric_before_first_answer(tmp_path):
    import json
    u = U(tmp_path)
    u.set_policy(REQ)
    plan, out = u.start()
    sid = out['result']['session_id']
    t = u.call('task', '--session', sid)
    txt = json.dumps(t)
    for r in u.bank()['rubrics']:
        for c in r['criteria']:
            assert c['text'] not in txt
        for h in r.get('hints', []):
            assert h not in txt
    # a refused submit (unknown cite) does not echo the answer
    o = u.submit(sid, plan['plan']['task_ids'][0], 'SECRET-ANSWER-XYZ', cite=['../x'],
                 expect=2)
    assert 'SECRET-ANSWER-XYZ' not in json.dumps(o)
    o = u.submit(sid, plan['plan']['task_ids'][0], 'SECRET-ANSWER-XYZ')
    st = u.call('status')
    assert 'SECRET-ANSWER-XYZ' not in json.dumps(st) + json.dumps(o)
    assert 'SECRET-ANSWER-XYZ' not in (u.study / '.hypotrail' / 'state.json').read_text()
