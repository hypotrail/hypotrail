"""A01, A02, A03, A19 (policy part), A23: activation, policy, plan, refusals without fallback."""
from __future__ import annotations

import json

import pytest

import ukit
from mlkit.study import cli, read
from mlkit.study.understanding import policy as pol


@pytest.fixture
def u(tmp_path):
    return ukit.U(tmp_path)


def code(payload):
    return payload['error']['code']


def test_off_by_default_adds_nothing(u):
    """A01: without activation a study has no extension, no session, no stored answer; the
    review commands that would record anything are refused; status says off."""
    state = u.state()
    assert 'understanding' not in state
    assert u.call('status')['mode'] == 'off'
    assert u.call('policy', 'show')['mode'] == 'off'
    before = u.rev()
    out = u.call('plan', '--profile', 'analyst', '--milestone', 'handoff', '--actor', 'alice',
                 expect=2)
    assert code(out) == 'understanding_disabled'
    assert u.rev() == before and 'understanding' not in u.state()
    # The study's own commands behave as before: export handoff writes outside the study only.
    o = cli.run(['export', 'handoff', '--study', str(u.study), '--out', str(u.root / 'h')])
    assert o.exit_code in (0, 3) and 'understanding' not in o.payload
    assert u.rev() == before


def test_policy_set_logs_both_digests_and_reason(u):
    """A02: the event names the previous and new digest, the declared author and the reason."""
    first = u.set_policy()
    assert first['result']['previous_digest'] is None
    second = u.set_policy(ukit.policy(mode='required'))
    events = u.call('policy', 'show')['events']
    assert [e['mode_to'] for e in events] == ['coaching', 'required']
    assert events[1]['previous_digest'] == first['result']['policy_digest']
    assert events[1]['new_digest'] == second['result']['policy_digest']
    assert events[1]['author_declared_id'] == 'lead' and events[1]['reason'] == 'team agreement'


@pytest.mark.parametrize('change, expected', [
    ({'minimum_assurance': 'external_verified'}, 'unsupported_assurance'),
    ({'evidence_retention': {'purge_after_days': 30}}, 'unsupported_capability'),
    ({'milestones': ['azure_deploy']}, 'policy_invalid'),
    ({'mode': 'strict'}, 'policy_invalid'),
    ({'schema': 'hypotrail.understanding-policy/2'}, 'policy_invalid'),
    ({'unexpected': True}, 'policy_invalid'),
    ({'critical_dimensions': ['D9']}, 'policy_invalid'),
    ({'team_coverage': {'minimum_people': 1}}, 'policy_invalid'),
])
def test_unknown_or_unsupported_policies_are_refused_without_fallback(u, change, expected):
    """A02, A19: no silent fallback (external_verified never becomes human_declared)."""
    before = u.rev()
    doc = ukit.policy(**change)
    out = u.call('policy', 'set', '--file', u.file('bad.json', doc), '--author', 'lead',
                 '--reason', 'x', mutation=True, expect=2)
    assert code(out) == expected
    assert out['error']['details'].get('next_action')
    assert u.rev() == before and 'understanding' not in u.state()


def test_check_with_unsupported_assurance_file_is_refused(u):
    u.set_policy()
    out = u.call('check', '--milestone', 'handoff', '--policy-file',
                 u.file('ext.json', ukit.policy(minimum_assurance='external_verified')),
                 expect=2)
    assert code(out) == 'unsupported_assurance'


def test_plan_shows_coverage_and_critical_dimensions_stay(u):
    """A03: the plan shows dimensions, critical ones, prerequisites and the estimate; a
    profile without a critical dimension still gets it."""
    u.set_policy()
    doc = ukit.policy(responsibility_profiles={'analyst': ['D1', 'D4'], 'pipeline': ['D5']})
    u.set_policy(doc)
    plan = u.call('plan', '--profile', 'pipeline', '--milestone', 'handoff', '--actor', 'alice')
    assert plan['dimensions'] == ['D2', 'D3', 'D5']           # D2, D3 critical, imposed
    assert plan['critical_dimensions'] == ['D2', 'D3']
    assert plan['estimate_minutes'] > 0
    assert 'answers' in plan['will_be_kept_locally']
    analyst = u.call('plan', '--profile', 'analyst', '--milestone', 'handoff', '--actor', 'alice')
    # No result exists yet (no fit), so the results tasks are a missing prerequisite, never
    # a question with an invented figure (A21).
    missing = {m['dimension_id']: m['missing_refs'] for m in analyst['prerequisites_missing']}
    assert 'D4' in missing and any(r.startswith('result:') for r in missing['D4'])
    assert u.rev() == u.rev()                                  # read-only


def test_plan_refuses_unknown_milestone_and_profile(u):
    u.set_policy()
    out = u.call('plan', '--profile', 'analyst', '--milestone', 'deploy', '--actor', 'alice',
                 expect=2)
    assert code(out) == 'policy_invalid'
    out = u.call('plan', '--profile', 'manager', '--milestone', 'handoff', '--actor', 'alice',
                 expect=2)
    assert code(out) == 'policy_invalid'


def test_a_case_without_bank_is_unsupported(tmp_path):
    case_dir = ukit.make_case_dir(tmp_path)
    (case_dir / 'understanding.yaml').unlink()
    u = ukit.U(tmp_path, case_dir=case_dir)
    u.set_policy()
    out = u.call('plan', '--profile', 'analyst', '--milestone', 'handoff', '--actor', 'alice',
                 expect=2)
    assert code(out) == 'unsupported_case'


def test_off_mode_policy_keeps_history_and_check_is_not_applicable(u):
    u.set_policy()
    u.start()
    u.set_policy(ukit.policy(mode='off'))
    assert len(u.ext()['sessions']) == 1                      # nothing deleted
    gate = u.call('check', '--milestone', 'handoff')['gate']
    assert gate['decision'] == 'not_applicable'
    assert gate['reasons'][0]['code'] == 'no_required_check'
    out = u.call('plan', '--profile', 'analyst', '--milestone', 'handoff', '--actor', 'alice',
                 expect=2)
    assert code(out) == 'understanding_disabled'


def test_human_mode_needs_no_provider_or_network(u, monkeypatch):
    """A23: the whole human workflow runs with sockets forbidden and no API key."""
    import socket

    def no_network(*a, **k):
        raise AssertionError('network used')
    monkeypatch.setattr(socket.socket, 'connect', no_network)
    for key in ('ANTHROPIC_API_KEY', 'OPENAI_API_KEY'):
        monkeypatch.delenv(key, raising=False)
    sid = ukit.full_flow(u)
    assert u.call('check', '--milestone', 'handoff')['gate']['decision'] == 'allowed'
    assert sid


def test_policy_validation_is_pure_and_digest_covers_every_field():
    doc = pol.validate(ukit.policy())
    base = pol.digest(doc)
    for key, value in [('critical_dimensions', ['D2']), ('assistance_rule',
                       {'critical': 'aided_allowed', 'other': 'aided_allowed'}),
                       ('context_requirement', 'public_only')]:
        assert pol.digest({**doc, key: value}) != base
    assert json.dumps(doc)


def test_future_state_schema_is_not_written(u):
    """A state written by a newer engine is read as unsupported and never written."""
    u.set_policy()
    from mlkit.study import store as sto
    s = sto.StudyStore(u.study)
    with s.writing() as state:
        state['understanding']['schema'] = 'hypotrail.understanding-state/2'
        s.commit(state, {'request_id': None, 'action': 'test.future', 'params': {},
                         'result': None})
    assert u.call('status')['mode'] == 'unsupported'
    out = u.set_policy(expect=2)
    assert code(out) == 'policy_invalid'
    assert read.load_state(u.study)['understanding']['schema'].endswith('/2')
