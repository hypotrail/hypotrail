"""A19, A25, A31 (concurrency): the handoff milestone under a required policy, waivers,
changes between check and handoff, concurrent publications."""
from __future__ import annotations

import threading

import pytest

import ukit
from mlkit.study import cli
from mlkit.study.understanding import export as ex, milestone


def code(p):
    return p['error']['code']


def handoff(u, out):
    return cli.run(['export', 'handoff', '--study', str(u.study), '--out', str(out)])


def test_direct_handoff_call_is_gated_and_check_is_not_a_token(tmp_path):
    """A25: export handoff applies the gate itself; without a prior check it refuses when
    blocked and publishes when allowed; a passed check is not reused after a change."""
    u = ukit.U(tmp_path)
    u.set_policy(ukit.policy(mode='required'))
    o = handoff(u, tmp_path / 'h0')
    assert o.exit_code == 2 and code(o.payload) == 'milestone_blocked'
    assert not (tmp_path / 'h0').exists()
    u.set_policy(ukit.POLICY)
    ukit.full_flow(u)                                       # sets the required policy again
    assert u.call('check', '--milestone', 'handoff')['gate']['decision'] == 'allowed'
    o = handoff(u, tmp_path / 'h1')
    assert o.exit_code in (0, 3), o.payload
    assert o.payload['understanding']['decision'] == 'allowed'
    assert (tmp_path / 'h1' / 'handoff.json').exists()
    assert 'simulated_human_decisions' in o.payload['understanding']['limitations']
    # A policy change after a passed check: the next handoff is refused.
    u.set_policy(ukit.policy(mode='required', critical_dimensions=['D2', 'D3', 'D5']))
    o = handoff(u, tmp_path / 'h2')
    assert o.exit_code == 2 and code(o.payload) == 'milestone_blocked'


@pytest.mark.parametrize('change', ['source', 'policy', 'decision'])
def test_concurrent_change_between_reservation_and_publication(tmp_path, change):
    """A25: a source, the policy or the scientific context changes after the reservation and
    before the publication: the folder stays a candidate, never a handoff."""
    u = ukit.U(tmp_path)
    ukit.full_flow(u)

    def hook(study_dir):
        if change == 'source':
            (u.repo / 'src/transforms.py').write_text('changed meanwhile\n')
        elif change == 'policy':
            u.set_policy(ukit.policy(mode='required', minimum_assurance='human_declared',
                                     version=2))
        else:
            u.flow.decide('split', {'method': 'stratified_random',
                                    'validation_fraction': 0.25, 'seed': 3})
    milestone.BEFORE_FINALIZE.append(hook)
    try:
        o = handoff(u, tmp_path / 'h')
    finally:
        milestone.BEFORE_FINALIZE.clear()
    assert o.exit_code == 2 and code(o.payload) == 'context_changed', o.payload
    assert not (tmp_path / 'h').exists()
    candidates = [p for p in tmp_path.iterdir() if p.name.startswith('h.candidate-')]
    assert candidates and (candidates[0] / 'handoff.json').exists()
    records = [m for m in u.ext()['milestones'].values()]
    assert records[-1]['status'] == 'candidate_not_current'


def test_waivers_are_refused_by_default(tmp_path):
    """A19: a recorded waiver stays ``waived``; a policy that does not accept waivers keeps
    the milestone blocked and says so."""
    u = ukit.U(tmp_path)
    ukit.full_flow(u)
    (u.repo / 'SECURITY.md').write_text('changed\n')                   # D8 stale
    w = u.m('waive', '--file', u.file('w.json', {
        'milestone': 'handoff', 'dimensions': ['D8'], 'reason': 'Pilot week',
        'scope': 'This handoff only', 'approver_declared_id': 'lead',
        'expires_on': '2999-01-01', 'unmet_requirements': ['D8 review after the change']}))
    assert w['result']['status'] == 'waived' and w['result']['accepted_by_policy'] is False
    gate = u.call('check', '--milestone', 'handoff')['gate']
    assert gate['decision'] == 'blocked'
    assert any(r['code'] == 'waiver_not_accepted' for r in gate['reasons'])


def test_waiver_gives_allowed_by_waiver_never_allowed(tmp_path):
    u = ukit.U(tmp_path)
    ukit.full_flow(u, required=False)
    u.set_policy(ukit.policy(mode='required', exemptions_policy={'waivers_allowed': True}))
    sel = next(iter(u.ext()['selections'].values()))
    u.m('select', '--file', u.file('sel.json', {
        'milestone': 'handoff', 'actor_scope': sel['actor_scope'],
        'dimension_decision_map': sel['dimension_decision_map'],
        'transfer_decision_map': sel['transfer_decision_map'],
        'reservation_resolution_refs': []}))
    gate = u.call('check', '--milestone', 'handoff')['gate']
    # The decisions were reviewed under the coaching policy: a new policy needs new reviews.
    assert gate['decision'] == 'blocked'
    dims = sorted({r['dimension'] for r in gate['reasons'] if r.get('dimension')})
    u.m('waive', '--file', u.file('w.json', {
        'milestone': 'handoff', 'dimensions': dims, 'reason': 'Transition to the new policy',
        'scope': 'one handoff', 'approver_declared_id': 'lead', 'expires_on': '2999-01-01',
        'unmet_requirements': ['reviews under the new policy']}))
    gate = u.call('check', '--milestone', 'handoff')['gate']
    assert gate['decision'] == 'allowed_by_waiver' and gate['waiver_ref']
    assert 'waived_requirements' in gate['limitations']
    u.m('waive', '--file', u.file('w2.json', {
        'milestone': 'handoff', 'dimensions': dims, 'reason': 'old', 'scope': 'x',
        'approver_declared_id': 'lead', 'expires_on': '2000-01-01', 'unmet_requirements': []}))
    gate = u.call('check', '--milestone', 'handoff')['gate']
    assert gate['decision'] == 'allowed_by_waiver'                     # the live one still


def test_relaxed_policy_in_the_candidate_is_not_an_authority(tmp_path):
    """A19: verify-export without --policy-file is a diagnostic; the embedded policy only
    gives declared_conformity, never a gate decision."""
    u = ukit.U(tmp_path)
    sid = ukit.full_flow(u)
    ukit.approve_all(u, sid)
    u.m('export', 'write', '--session', sid, '--repo', u.repo)
    out = cli.run(['understanding', 'verify-export', '--repo', str(u.repo), '--target',
                   'worktree']).payload
    assert out['policy_source'].startswith('embedded')
    assert out['generations'][0]['gate_result'] is None


def test_concurrent_publications_never_mix(tmp_path):
    """A31: two publications of one review id race; one wins, the other is the same bytes
    (idempotent) or refused; the published set is complete and consistent."""
    u = ukit.U(tmp_path, pauses=False)
    files_a = {ex.JSON_FILE: b'{"a":1}', ex.MD_FILE: b'a\n', ex.MANIFEST_FILE: b'{"m":1}'}
    files_b = {ex.JSON_FILE: b'{"b":1}', ex.MD_FILE: b'b\n', ex.MANIFEST_FILE: b'{"m":2}'}
    results = []

    def run(files):
        try:
            results.append(ex.publish(u.repo, 'rv-race', files))
        except Exception as exc:                 # noqa: BLE001
            results.append(getattr(exc, 'code', repr(exc)))
    threads = [threading.Thread(target=run, args=(f,)) for f in (files_a, files_b)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == ['export_stale', 'published']
    d = u.repo / ex.EXPORT_DIR / 'rv-race'
    got = {p.name: p.read_bytes() for p in d.iterdir()}
    assert got in (files_a, files_b)
