"""``hypotrail decisions`` (CLI-CONTRACT-COMPANION §2, C2) on the Bank walkthrough.

A threshold policy replaced by a capacity, a delegated split, a hold, and a
reconfirmation queue that empties once the junior confirms again. The flow runs in process
through ``cli.run``; R1 and R3 run as real processes.
"""
from __future__ import annotations

import json

import pytest

import companion_contract as cc
import flowkit as fk
from mlkit.study import cmd_decisions

DELEGATION_WORDS = 'Go with your recommended default.'


def _propose(flow, decision, value, restatement=None, *extra):
    out = flow.call('decide', 'propose', decision, '--value-json', json.dumps(value),
                    '--restatement', restatement or f'You decide the {decision} as stated.',
                    '--rationale', 'It fits the scenario.', *extra, '--request-id', flow.rid(),
                    '--expected-revision', flow.rev(), '--study', flow.study)
    return out['result']['proposal_id']


def _confirm(flow, pid, words, *extra):
    return flow.call('decide', 'confirm', pid, '--user-words', words, *extra, '--request-id',
                     flow.rid(), '--expected-revision', flow.rev(), '--study', flow.study)


def _decisions(flow) -> dict:
    code, p = cc.run('decisions', '--study', flow.study)
    assert code == 0, p
    return p


@pytest.fixture(scope='module')
def bank(tmp_path_factory):
    flow = fk.Flow(tmp_path_factory.mktemp('bank') / 'study', fk.BANK, prefix='d')
    flow.init()
    flow.decide('prediction_time', 'before the first contact of the campaign')
    flow.decide('feature_availability', fk.availability(
        fk.BANK, duration='not_available', day='not_available', month='not_available',
        campaign='not_available'))
    pid = _propose(flow, 'split', fk.SPLIT, 'My recommended default: a stratified random split, '
                                            'thirty percent of rows for validation.')
    _confirm(flow, pid, DELEGATION_WORDS, '--basis', 'delegated_default', '--delegation-scope',
             'this_decision')
    flow.model_decisions()          # WP-A4: success criterion and default preprocessing
    for activity in ('split', 'eda.target_rate', 'eda.special_values', 'fit.baseline',
                     'fit.logistic'):
        flow.run(activity)
    flow.run('policy.evaluate', '--rule', 'threshold:0.2')
    flow.decide('policy', 'threshold:0.2')
    flow.run('policy.evaluate', '--rule', 'capacity:100')
    pid = _propose(flow, 'policy', 'capacity:100', None, '--channel', 'webview')
    _confirm(flow, pid, 'Yes: our desk can make 100 calls, take the top 100 for the policy.',
             '--channel', 'webview')
    return flow


def test_history_proposals_and_delegation(bank):
    p = _decisions(bank)
    assert tuple(p) == cmd_decisions.PAYLOAD_KEYS == cc.DECISIONS_KEYS
    policy = [h for h in p['history'] if h['decision_id'] == 'policy']
    assert [h['value'] for h in policy] == ['threshold:0.2', 'capacity:100']
    assert [h['current'] for h in policy] == [False, True]
    assert policy[0]['superseded_at'] == policy[1]['revision'] and policy[1]['superseded_at'] is None
    assert policy[1]['channel'] == 'webview' and policy[0]['channel'] == 'chat'
    # WP-A4: the success criterion and the preprocessing are confirmed too; WP-B1: and the
    # variant the policy compares.
    assert sum(h['current'] for h in p['history']) == 7
    split = next(h for h in p['history'] if h['decision_id'] == 'split')
    assert (split['basis'], split['delegation_scope']) == ('delegated_default', 'this_decision')
    assert split['user_words'] == DELEGATION_WORDS
    threshold = next(x for x in p['proposals'] if x['value'] == 'threshold:0.2')
    assert threshold['status'] == 'superseded' and threshold['closed_revision'] is not None
    capacity = next(x for x in p['proposals'] if x['value'] == 'capacity:100')
    assert capacity['origin'] == {'channel': 'webview'} and capacity['status'] == 'confirmed'
    assert threshold['origin'] == {'channel': 'chat'}
    assert [x['revision'] for x in p['proposals']] == sorted(x['revision'] for x in p['proposals'])
    assert p['reconfirm_queue'] == []
    items = {d['decision_id']: d for d in p['decisions']}
    assert (items['split']['pause'], items['split']['step']) == (2, 'split')
    assert items['policy']['title'] == 'Choose a decision policy'
    assert items['policy']['confirmation']['channel'] == 'webview'
    assert items['conclusion']['confirmation'] is None


def test_reconfirm_queue_after_a_split_change(bank, tmp_path):
    flow = fk.Flow(fk.clone(bank.study, tmp_path / 'study'), fk.BANK, prefix='q')
    out = flow.decide('split', {**fk.SPLIT, 'seed': 5})
    p = _decisions(flow)
    [queued] = p['reconfirm_queue']
    assert tuple(queued) == cc.RECONFIRM_QUEUE_KEYS
    assert tuple(queued['previous']) == cc.RECONFIRM_PREVIOUS_KEYS
    assert queued['decision_id'] == 'policy' and queued['open_proposal'] is None
    assert queued['since_revision'] == out['revision']
    assert queued['previous']['value'] == 'capacity:100'
    assert queued['previous']['channel'] == 'webview'
    assert queued['reason']
    split = [h for h in p['history'] if h['decision_id'] == 'split']
    assert [h['current'] for h in split] == [False, True]
    # proposing again links the open proposal; confirming empties the queue
    flow.run('split')
    for activity in ('fit.baseline', 'fit.logistic'):
        flow.run(activity)
    flow.run('policy.evaluate', '--rule', 'capacity:100')
    pid = _propose(flow, 'policy', 'capacity:100')
    assert _decisions(flow)['reconfirm_queue'][0]['open_proposal'] == pid
    _confirm(flow, pid, 'Yes, I want the policy exactly as you stated it, because it fits our situation')
    assert _decisions(flow)['reconfirm_queue'] == []


def test_notes_and_a_pre_c9_proposal(bank, tmp_path):
    flow = fk.Flow(fk.clone(bank.study, tmp_path / 'study'), fk.BANK, prefix='n')
    flow.call('decide', 'note', '--about', 'conclusion', '--text', 'not before the pilot',
              '--request-id', flow.rid(), '--expected-revision', flow.rev(), '--study',
              flow.study)
    p = _decisions(flow)
    assert [n['user_words'] for n in p['notes']] == ['not before the pilot']
    # A proposal recorded before C9 carries no origin: it reads null.
    home = flow.study / '.hypotrail'
    state = json.loads((home / 'state.json').read_text())
    for proposal in state['proposals'].values():
        proposal.pop('origin', None)
    from mlkit.study import state as st

    data = st.dumps(state)
    (home / 'state.json').write_bytes(data)
    (home / 'state.sha256').write_text(st.sha_line(st.digest(data)))
    p = _decisions(flow)
    assert p['proposals'] and all(x['origin'] is None for x in p['proposals'])


def test_decisions_is_read_only_and_light(bank, tmp_path):
    study = fk.clone(bank.study, tmp_path / 'study')
    code, p = cc.r1_read_only(study, 'decisions')
    assert code == 0 and p['ok'] is True
    assert cc.r3_imported(study, 'decisions') == []
    assert json.dumps(p['history']) == json.dumps(_decisions(fk.Flow(study, fk.BANK))['history'])


def test_refusals(tmp_path):
    code, p = cc.run('decisions', '--study', tmp_path / 'nothing')
    assert code == 2 and cc.refusal(p)[0] == 'study_missing', p
    code, p = cc.run('decisions', '--bogus', '--study', tmp_path)
    assert code == 2 and cc.refusal(p)[0] == 'invalid_arguments', p


def test_regression_decisions(tmp_path):
    study = cc.regression_study(tmp_path / 'work', tmp_path / 'study')
    p = cc.run('decisions', '--study', study)[1]
    assert p['task'] == 'regression'
    # WP-A4: the two decisions of the split pause before the models.
    # WP-B1: the variant before the model choice, the final test after it.
    assert [d['decision_id'] for d in p['decisions']] == ['prediction_time',
                                                          'feature_availability', 'split',
                                                          'success_criterion', 'preprocessing',
                                                          'model_variant', 'model_choice',
                                                          'final_test', 'conclusion']
    assert [d['pause'] for d in p['decisions']] == [1, 1, 2, 2, 2, 3, 3, 3, 3]
    assert p['history'] == [] and p['proposals'] == []
