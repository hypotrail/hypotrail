"""``status --summary`` ``recap``: five resume lines generated from state (post-v0.1, T8, F5).

The final acceptance check rated T8 "decision lost between chats" partial in 3 of 3 runs,
and one resume dropped the caveat of a stand-in capacity. The recap gives a new chat five
deterministic lines it may quote: the goal (intended use and prediction moment), the
decisions made with the excluded features by name, the current position, the next
decision (an open restatement quoted as written), and one limit; no revision numbers or
ids.
"""
from __future__ import annotations

import json
import re

import pytest

from mlkit.study import view

import flowkit as fk


def _summary(flow) -> dict:
    return flow.call('status', '--summary', '--study', flow.study)


def _assert_shape(recap: list[str], summary: dict) -> None:
    assert len(recap) == 5
    assert [line.split(':', 1)[0] for line in recap] == list(view.RECAP_LABELS)
    for line in recap:
        assert '\n' not in line and len(line) < 600, line
        assert 'revision' not in line.lower(), line
        assert not re.search(r'\b(?:p|e)_[0-9a-f]+\b', line), line       # proposal, execution ids
        assert summary['study'] not in line
    for slot, r in summary['results'].items():
        rid = r['result_id']
        if slot == 'policy.evaluation' and r['current']:
            # Post-v0.1 fixes (D10): the one id a binary recap holds, next to its headline
            # figures (precision and recall at one rule), and only there.
            text = ' '.join(recap)
            assert text.count(rid[:8]) <= 1
            if rid[:8] in text:
                assert re.search(rf'precision [\d.]+%, recall [\d.]+%, result {rid[:8]}\)',
                                 text), text
            continue
        assert rid[:8] not in ' '.join(recap)


@pytest.fixture
def flow(tmp_path, synthetic_case_dir):
    f = fk.Flow(tmp_path / 'study', synthetic_case_dir, prefix='recap')
    f.init()
    return f


def test_a_new_study_recaps_the_goal_and_the_first_decision(flow):
    summary = _summary(flow)
    recap = summary['recap']
    _assert_shape(recap, summary)
    # v0.2a: the sealed final test (ADR 0006) sits between the holds and the recap, then the
    # success criterion and the target looks (WP-A4); the additive audience keys (WP-A1)
    # follow the recap.
    keys = tuple(summary)
    assert keys[keys.index('holds') + 1:keys.index('holds') + 5] == (
        'final_test', 'criterion', 'eda_looks', 'recap')
    # WP-A7: the confirmation mode and the notebook launch commands follow them; WP-B1: the
    # trial count, last.
    assert keys[-5:] == ('recap_audience', 'recap_junior', 'mode', 'deliverables', 'trials')
    intended = summary['goal']['intended_use']['value']
    assert recap[0].startswith(f'Goal: {intended}; the prediction is made ')
    assert recap[1] == 'Decided: nothing yet.'
    # WP-A4: the first step of a new study is reading the data card.
    assert recap[2].startswith('Now: Discover the data')
    # v0.2a (WP-A1): nothing was rendered yet, so nothing is "up to date".
    assert recap[2].endswith('report and notebook not rendered yet.'), recap[2]
    assert 'up to date' not in recap[2]
    assert recap[3].startswith('Next: ')
    assert recap[4].startswith('Limit: ') and 'not confirmed' not in recap[4]


def test_decisions_name_the_excluded_features_and_the_delegation(flow, synthetic_case_dir):
    flow.decide('prediction_time', 'when the membership expires, before any reminder')
    flow.decide('feature_availability',
                fk.availability(synthetic_case_dir, reminders_sent='not_available',
                                last_reminder_weekday='uncertain_excluded',
                                fines_outstanding='uncertain_included'))
    p = flow.call('decide', 'propose', 'split', '--value-json', json.dumps(fk.SPLIT),
                  '--restatement', 'My recommended default: a stratified random split, fixed '
                                   'before exploring.', '--rationale', 'The usual default.',
                  '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                  '--study', flow.study)['result']['proposal_id']
    flow.call('decide', 'confirm', p, '--user-words', 'Use your recommended default.',
              '--basis', 'delegated_default', '--delegation-scope', 'this_decision',
              '--request-id', flow.rid(), '--expected-revision', flow.rev(),
              '--study', flow.study)
    summary = _summary(flow)
    recap = summary['recap']
    _assert_shape(recap, summary)
    assert recap[0].endswith('the prediction is made when the membership expires, before any '
                             'reminder.')
    decided = recap[1]
    excluded = summary['decisions']['feature_availability']['value']
    for feature in excluded['not_available'] + excluded['uncertain_excluded']:
        assert feature in decided, feature
    assert 'excluded ' in decided and 'kept despite a doubt: fines_outstanding' in decided
    assert 'split (stratified random, 30% for validation) [delegated to the assistant]' \
        in decided
    assert decided.index('prediction moment') < decided.index('feature availability') \
        < decided.index('split')
    assert summary['recap'] == _summary(flow)['recap']                    # deterministic


def test_an_open_proposal_is_quoted_with_its_caveat(flow):
    flow.decide('prediction_time', 'when the membership expires')
    restatement = ('You exclude the reminder columns and keep the rest; the list is '
                   'illustrative until you check it.')
    flow.call('decide', 'propose', 'feature_availability', '--value-json',
              json.dumps(fk.availability(flow.case_dir)), '--restatement', restatement,
              '--rationale', 'From the case.', '--request-id', flow.rid(),
              '--expected-revision', flow.rev(), '--study', flow.study)
    summary = _summary(flow)
    _assert_shape(summary['recap'], summary)
    assert summary['recap'][3] == ('Next: your answer, in your own words, on the feature '
                                   f'availability: "{restatement}"')
    assert 'illustrative' in summary['recap'][3]


def test_the_recap_follows_the_state_through_the_plan(tmp_path, synthetic_case_dir):
    study = fk.prepare(synthetic_case_dir, tmp_path / 'study', upto='fits')
    flow = fk.Flow(study, synthetic_case_dir, prefix='later')
    flow.run('policy.evaluate', '--rule', 'capacity:100')
    summary = _summary(flow)
    recap = summary['recap']
    _assert_shape(recap, summary)
    assert recap[2].startswith('Now: ')
    titles = {s['id']: s['title'] for s in summary['plan']}
    assert titles[summary['current_step']] in recap[2]
    assert recap[4][len('Limit: '):] in {x['text'] for x in
                                          flow.view()['not_yet_defensible']}
