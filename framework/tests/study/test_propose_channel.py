"""``decide propose --channel`` and the stored ``origin`` (CLI-CONTRACT-COMPANION §9, C9).

The channel changes no rule: a webview proposal is checked like any other and is
confirmed only by a later request with acceptable words. ``channel`` reaches the action
parameters only when it is not ``chat``, so a request recorded before C9 still replays.
"""
from __future__ import annotations

import json

import pytest

import companion_contract as cc
import flowkit as fk
from mlkit.reliability import CommandRefused
from mlkit.study import commands as cmd, read, sessionlog


@pytest.fixture(scope='module')
def binary(tmp_path_factory, synthetic_case_dir):
    return cc.binary_study(synthetic_case_dir, tmp_path_factory.mktemp('channel') / 'study')


@pytest.fixture
def clone(binary, tmp_path):
    return fk.Flow(fk.clone(binary.study, tmp_path / 'study'), binary.case_dir, prefix='w')


def _propose(flow, *extra, value=cc.POLICY_RULE, restatement='You decide the policy as stated.',
             request_id=None, expect=0):
    return flow.call('decide', 'propose', 'policy', '--value', value, '--restatement',
                     restatement, '--rationale', 'Chosen in the panel.', *extra,
                     '--request-id', request_id or flow.rid(), '--expected-revision',
                     flow.rev(), '--study', flow.study, expect=expect)


def _record(flow, request_id) -> dict:
    lines = (flow.study / '.hypotrail' / 'revisions.jsonl').read_text().splitlines()
    return next(json.loads(x) for x in lines if json.loads(x).get('request_id') == request_id)


def test_each_channel_is_stored_and_only_a_non_chat_one_is_a_parameter(clone):
    for extra, channel in (((), 'chat'), (('--channel', 'chat'), 'chat'),
                           (('--channel', 'cli'), 'cli'), (('--channel', 'webview'), 'webview')):
        rid = clone.rid()
        out = _propose(clone, *extra, request_id=rid)
        pid = out['result']['proposal_id']
        assert read.open(clone.study).state['proposals'][pid]['origin'] == {'channel': channel}
        params = _record(clone, rid)['params']
        assert ('channel' in params) == (channel != 'chat'), params
        if channel != 'chat':
            assert params['channel'] == channel


def test_a_webview_proposal_follows_every_rule(clone):
    # numbers that are not figures of a result are refused, as from the chat
    refused = _propose(clone, '--channel', 'webview', restatement='Call 12345 members.',
                       expect=2)
    assert refused['error']['code'] == 'literal_number_in_text'
    pid = _propose(clone, '--channel', 'webview')['result']['proposal_id']
    bare = clone.call('decide', 'confirm', pid, '--user-words', 'ok', '--channel', 'webview',
                      '--request-id', clone.rid(), '--expected-revision', clone.rev(),
                      '--study', clone.study, expect=2)
    assert bare['error']['details']['reason'] == 'bare_acknowledgement'
    out = clone.call('decide', 'confirm', pid, '--user-words', 'Yes, I want the policy exactly '
                     'as you stated it', '--channel', 'webview', '--request-id', clone.rid(),
                     '--expected-revision', clone.rev(), '--study', clone.study, expect=None)
    assert out['ok'] is True and out['result']['channel'] == 'webview'
    assert read.open(clone.study).state['proposals'][pid]['origin'] == {'channel': 'webview'}


def test_an_unknown_channel_is_an_invalid_value_and_writes_nothing(clone):
    before = cc.study_tree_digest(clone.study)
    refused = _propose(clone, '--channel', 'pigeon', expect=2)
    assert refused['error']['code'] == 'invalid_value'
    assert refused['error']['details']['field'] == 'channel'
    assert cc.study_tree_digest(clone.study) == before
    # the same rule holds for a request built without the CLI
    with pytest.raises(CommandRefused) as err:
        cmd.apply(clone.study, action=cmd.ACTION_PROPOSE,
                  params={'decision_id': 'policy', 'value': cc.POLICY_RULE,
                          'restatement': 'You decide the policy as stated.',
                          'rationale': 'It fits.', 'channel': 'pigeon'},
                  request_id='direct', expected_revision=clone.rev())
    assert err.value.code == 'invalid_value' and err.value.details['field'] == 'channel'
    # (the writer lock file records its last holder; no study record changed)
    after = cc.study_tree_digest(clone.study)
    assert {k: v for k, v in after.items() if not k.endswith('writer.lock')} == {
        k: v for k, v in before.items() if not k.endswith('writer.lock')}


def test_a_request_without_channel_replays_and_a_new_channel_conflicts(clone):
    rid = clone.rid()
    first = _propose(clone, request_id=rid)
    again = clone.call('decide', 'propose', 'policy', '--value', cc.POLICY_RULE,
                       '--restatement', 'You decide the policy as stated.', '--rationale',
                       'Chosen in the panel.', '--channel', 'chat', '--request-id', rid,
                       '--expected-revision', first['revision'] - 1, '--study', clone.study)
    assert again['replayed'] is True and again['revision'] == first['revision']
    conflict = clone.call('decide', 'propose', 'policy', '--value', cc.POLICY_RULE,
                          '--restatement', 'You decide the policy as stated.', '--rationale',
                          'Chosen in the panel.', '--channel', 'webview', '--request-id', rid,
                          '--expected-revision', first['revision'] - 1, '--study', clone.study,
                          expect=2)
    assert conflict['error']['code'] == 'idempotency_conflict'


def test_the_session_log_records_the_channel(clone, monkeypatch):
    monkeypatch.setenv(sessionlog.ENV, '1')
    _propose(clone, '--channel', 'webview')
    lines = sessionlog.path(clone.study).read_text().splitlines()
    last = json.loads(lines[-1])
    assert 'webview' in json.dumps(last)
    assert 'Chosen in the panel' not in json.dumps(last)


def test_origin_shows_in_decisions_the_digest_and_the_view_not_the_v01_summary(clone):
    pid = _propose(clone, '--channel', 'webview')['result']['proposal_id']
    code, d = cc.run('decisions', '--study', clone.study)
    assert {x['proposal_id']: x['origin'] for x in d['proposals']}[pid] == {'channel': 'webview'}
    code, s = cc.run('status', '--summary', '--digest', '--study', clone.study)
    assert s['open_proposals'][-1]['origin'] == {'channel': 'webview'}
    # WP-I, decision CI.6 (amends CA.4 for the view only): `status --json` lists the origin
    # as the last key of each open proposal, so the report can say "Proposed from the
    # companion"; `status --summary` without --digest keeps the v0.1 shape.
    code, full = cc.run('status', '--json', '--study', clone.study)
    assert {p['proposal_id']: p['origin'] for p in full['view']['open_proposals']}[pid] == {'channel': 'webview'}
    assert all(list(p)[-1] == 'origin' for p in full['view']['open_proposals'])
    code, v01 = cc.run('status', '--summary', '--study', clone.study)
    assert all('origin' not in p for p in v01['open_proposals'])


def test_the_state_schema_checks_the_origin(binary):
    from mlkit.study import state as st

    state = read.open(binary.study).state
    pid = cc.open_proposal(binary, 'policy')
    assert st.validate_state(state) == []
    for bad in ({'channel': 'pigeon'}, {'channel': 'chat', 'by': 'x'}, 'webview', None):
        state['proposals'][pid]['origin'] = bad
        assert [p['path'] for p in st.validate_state(state)] == [f'proposals.{pid}.origin'], bad
    del state['proposals'][pid]['origin']       # a proposal recorded before C9
    assert st.validate_state(state) == []
