"""WP-A7 (v0.2a): the companion's engine requests on ``status --summary`` (CLI-CONTRACT §3,
§3.3; CLI-CONTRACT-COMPANION §1.4).

* the summary carries the confirmation ``mode`` and the notebooks' launch argument lists
  (``deliverables``), so a surface needs no full view for them;
* ``recap_junior`` says decision values in words (a rule, a verdict, never a recorded
  token) and its ``Now`` line names the step that waits for the junior;
* every digest item says who its ``text`` is written for (``audience``) and carries its
  junior variant (``junior_text``, null when the text is already the junior's);
* the junior message of an unknown outcome names the run's activity in words.

Scope U (pure functions) and S (the CLI code path in process, on the synthetic case).
"""
from __future__ import annotations

import re

import pytest

from mlkit.study import audience, read, view

import companion_contract as cc
import flowkit as fk

# Recorded tokens that are never primary content for the junior (COMPANION-ADVANCED INV-16).
TOKENS = re.compile(r'capacity:\d|threshold:\d|fit\.\w|eda\.\w|policy\.\w|adopt_policy|'
                    r'keep_baseline|\bchannel\b|junior')


@pytest.fixture(scope='module')
def binary(tmp_path_factory, synthetic_case_dir):
    return cc.binary_study(synthetic_case_dir, tmp_path_factory.mktemp('wpa7') / 'study')


def _summary(flow, *extra):
    code, p = cc.run('status', '--summary', *extra, '--study', flow.study)
    assert code == 0, p
    return p


def test_the_summary_carries_the_mode_and_the_launch_argument_lists(binary):
    p = _summary(binary)
    # WP-B1: the trial count follows them.
    assert tuple(p)[-3:] == ('mode', 'deliverables', 'trials')
    assert p['mode'] == 'guided'
    full = binary.view()['deliverables']
    for name in ('notebook', 'workbench'):
        item = p['deliverables']['launch'][name]
        assert item == {k: full['launch'][name][k] for k in ('mode', 'path', 'argv')}
    assert [p['deliverables']['launch'][n]['argv'][-2] for n in ('notebook', 'workbench')] == [
        'run', 'edit']
    # The digest keys still follow, in their order.
    d = _summary(binary, '--digest')
    keys = tuple(d)
    assert keys[keys.index('trials') + 1:] == view.DIGEST_SUMMARY_KEYS      # WP-B1: trials


def test_recap_junior_names_the_waiting_step_and_says_values_in_words(binary, tmp_path):
    flow = fk.Flow(fk.clone(binary.study, tmp_path / 'study'), binary.case_dir, prefix='j')
    p = _summary(flow)
    assert p['next_action']['kind'] == 'await_user_words'
    title = {s['id']: s['title'] for s in p['plan']}['policy']
    now = p['recap_junior'][2]
    assert now.startswith(f'Now: {title}, waiting for your answer'), now
    pid = cc.open_proposal(flow, 'policy')
    flow.call('decide', 'confirm', pid, '--user-words', 'Yes, I want the policy exactly as '
              'you stated it because it fits our call capacity', '--request-id', flow.rid(),
              '--expected-revision', flow.rev(), '--study', flow.study)
    p = _summary(flow)
    decided = p['recap_junior'][1]
    assert 'the decision policy: call the top 20 by score' in decided, decided
    assert 'the feature availability' in decided and 'the split (' in decided
    assert not TOKENS.search(' '.join(p['recap_junior'])), p['recap_junior']
    # The agent recap keeps its tokens: it is quoted by the assistant, not shown to the junior.
    assert 'policy capacity:20' in p['recap'][1]


def test_every_digest_item_has_an_audience_and_a_junior_variant(binary, tmp_path):
    flow = fk.Flow(fk.clone(binary.study, tmp_path / 'study'), binary.case_dir, prefix='g')
    start = flow.rev()
    pid = cc.open_proposal(flow, 'policy')
    flow.call('decide', 'confirm', pid, '--user-words', 'Yes, I want the policy exactly as '
              'you stated it because it fits our call capacity', '--request-id', flow.rid(),
              '--expected-revision', flow.rev(), '--study', flow.study)
    flow.call('decide', 'note', '--about', 'policy', '--text', "wait for my manager's figure",
              '--request-id', flow.rid(), '--expected-revision', flow.rev(), '--study',
              flow.study)
    flow.run('policy.evaluate', '--rule', 'capacity:20', '--rule', 'capacity:30')
    flow.call('decide', 'propose', 'policy', '--value', 'capacity:30', '--restatement',
              'You decide the policy as stated.', '--rationale', 'It fits.', '--request-id',
              flow.rid(), '--expected-revision', flow.rev(), '--study', flow.study)
    flow.run('eda.quality')
    items = _summary(flow, '--digest', '--since', start)['digest']['items']
    assert all(tuple(i) == view.DIGEST_ITEM_KEYS for i in items)
    assert view.DIGEST_ITEM_KEYS[-2:] == ('audience', 'junior_text')
    by_kind = {i['kind']: i for i in items}
    confirmed, hold = by_kind['confirmed'], by_kind['hold_recorded']
    assert confirmed['audience'] == 'agent'
    assert confirmed['junior_text'] == 'You confirmed the policy in your own words.'
    assert hold['junior_text'] == ('You put the policy on hold: "wait for my manager\'s '
                                   'figure". The policy needs confirmation again: you put the '
                                   'policy on hold.')
    replaced = by_kind['result_replaced']
    assert replaced['junior_text'] == ('The policy evaluation was replaced for: call the top '
                                       '20 by score; call the top 30 by score. Models '
                                       'unchanged, nothing refitted.')
    assert by_kind['proposed']['junior_text'] == ('The policy was proposed: call the top 30 '
                                                  'by score.')
    quality = by_kind['result_added']
    assert quality['text'] == 'The data quality check was computed.'
    assert quality['audience'] == 'junior' and quality['junior_text'] is None
    for item in items:
        shown = item['junior_text'] if item['audience'] == 'agent' else item['text']
        assert shown and not TOKENS.search(shown), shown
        assert (item['junior_text'] is None) == (item['audience'] == 'junior')


def test_an_unknown_outcome_names_the_activity_in_words():
    action = audience.next_action({'kind': 'outcome_unknown', 'execution_id': 'e_1',
                                   'activity': 'eda.distribution', 'message': 'agent text'})
    assert action['audience'] == 'agent'
    assert action['junior_message'].startswith('A run of the distribution of a column stopped')
    assert not TOKENS.search(action['junior_message'])
    unknown = audience.next_action({'kind': 'outcome_unknown', 'execution_id': 'e_2',
                                    'activity': 'something.new', 'message': 'agent text'})
    assert unknown['junior_message'].startswith('A run of an analysis stopped')
    assert audience.activity_words('eda.rate_by:job') == 'an outcome rate by group (job)'
    assert audience.rule_words('threshold:0.2') == 'call everyone scored 0.2 or more'


def test_the_junior_now_line_of_an_unknown_outcome_names_the_run():
    summary_out = {'next_action': {'kind': 'outcome_unknown', 'activity': 'fit.logistic'},
                   'plan': []}
    assert view._junior_now(summary_out, {}, 'Fit the models') == (
        'a run of the logistic model stopped and its outcome is unknown, waiting for your '
        'acknowledgement')
    summary_out['next_action'] = {'kind': 'run', 'step': 'models'}
    assert view._junior_now(summary_out, {}, 'Fit the models') == 'Fit the models'


def test_a_regression_recap_says_the_model_choice_and_verdict_in_words(tmp_path):
    work = tmp_path / 'work'
    study = cc.regression_study(work, tmp_path / 'study')
    state = read.open(study).state
    out = {'decisions': {'model_choice': {'status': 'confirmed', 'value': 'fit.linear',
                                          'basis': 'restated'},
                         'conclusion': {'status': 'confirmed', 'basis': 'restated',
                                        'value': {'verdict': 'adopt_model', 'text': 'x'}}}}
    words = [view._recap_decision(d, out['decisions'][d], junior=True)
             for d in ('model_choice', 'conclusion')]
    assert words == ['the model choice: the linear model',
                     'the conclusion: adopt the chosen model']
    assert state['task'] == 'regression'
