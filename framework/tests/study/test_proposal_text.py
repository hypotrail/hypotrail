"""Numbers and wording a proposal may carry (review findings M1, L2, L3, L4).

* M1: the conclusion text is a claim. Its numbers must trace to current results (the
  proposed value is no whitelist for itself), and causal or forecast wording is refused
  when the conclusion is proposed (the reviewer's ``t7.py`` text used to be confirmed and
  rendered).
* L3: a percentage traces to a result, or to a fraction of the value ("30%" for a
  ``validation_fraction`` of 0.3), never to another number of the value
  ("capacity:100" does not allow "100% precision").
* L4: digits glued to letters ("top250") are numbers; identifiers (``p_5``,
  ``r_1a2b``, digests) are not.
* L2: policy rules have one canonical spelling.

Studies live in ``tmp_path``.
"""
from __future__ import annotations

import json

import pytest

from mlkit.study import commands as cmd, dependencies as dep, read

import flowkit as fk
from flowkit import Flow

REVIEWER_TEXT = ('The model reaches 95% precision on 4000 future clients, which causes a '
                 'doubling of subscriptions.')


@pytest.fixture(scope='module')
def evaluated(tmp_path_factory, synthetic_case_dir):
    study = fk.prepare(synthetic_case_dir, tmp_path_factory.mktemp('txt') / 'study')
    flow = Flow(study, synthetic_case_dir, prefix='t')
    flow.run('policy.evaluate', '--rule', 'capacity:20')
    flow.decide('policy', 'capacity:20', words='Yes, call the twenty highest-scored clients')
    return study


@pytest.fixture
def flow(evaluated, tmp_path, synthetic_case_dir):
    return Flow(fk.clone(evaluated, tmp_path / 'study'), synthetic_case_dir)


def _propose(flow, decision, value, restatement='You decide as stated.', rationale='Fits.',
             expect=0):
    return flow.call('decide', 'propose', decision, '--value-json', json.dumps(value),
                     '--restatement', restatement, '--rationale', rationale, '--request-id',
                     flow.rid(), '--expected-revision', flow.rev(), '--study', flow.study,
                     expect=expect)


def test_the_reviewers_conclusion_is_refused_at_propose(flow):
    rev = flow.rev()
    out = _propose(flow, 'conclusion', {'verdict': 'adopt_policy', 'text': REVIEWER_TEXT},
                   'Adopt the policy.', 'Strong.', expect=2)
    assert out['error']['code'] == 'literal_number_in_text'
    assert out['error']['details']['field'] == 'value.text'
    # "4000" is no registered figure. WP-A9 (H2): "95%" named a precision, and no
    # precision is 0.95; before, it was traced to the bootstrap level (0.95). The causal
    # clause is refused on its own below.
    assert out['error']['details']['numbers'] == ['4000', '95%']
    fixed = REVIEWER_TEXT.replace(' 95% precision on 4000 future clients', ' a good ranking')
    out = _propose(flow, 'conclusion', {'verdict': 'adopt_policy', 'text': fixed},
                   'Adopt the policy.', 'Strong.', expect=2)
    assert out['error']['code'] == 'causal_or_forecast_wording'
    assert flow.rev() == rev


@pytest.mark.parametrize('text, phrase', [
    ('Calling these clients causes more subscriptions.', 'causes'),
    ('With this policy we will get more subscribers next quarter, about 20 of them.', 'we will'),
])
def test_causal_or_forecast_conclusions_are_refused(flow, text, phrase):
    out = _propose(flow, 'conclusion', {'verdict': 'adopt_policy', 'text': text},
                   'Adopt the policy.', 'Ranked.', expect=2)
    assert out['error']['code'] == 'causal_or_forecast_wording'
    assert phrase in {f['details']['phrase'] for f in out['error']['details']['findings']}


def test_a_conclusion_citing_current_figures_is_accepted(flow):
    v = flow.view()
    ev = v['results']['policy.evaluation']['values']['rules']['capacity:20']['models']
    tp = ev['fit.logistic']['true_positives']
    tp_text = f'{tp:.0f}' if float(tp).is_integer() else f'{tp:g}'
    text = (f'On the validation rows, the 20 highest logistic scores (capacity:20) held '
            f'{tp_text} subscribers. These are associations on past rows, not effects.')
    done = _propose(flow, 'conclusion', {'verdict': 'adopt_policy', 'text': text},
                    'You adopt the capacity:20 policy.', 'It ranks better than the baseline.')
    assert done['result']['status'] == 'open'


def test_a_percentage_traces_to_results_not_to_the_value(tmp_path, synthetic_case_dir):
    flow = Flow(tmp_path / 'fresh', synthetic_case_dir)      # no result to trace to
    flow.init()
    out = _propose(flow, 'policy', 'capacity:100', 'Call the top 100 clients, at 100% precision.',
                   expect=2)
    assert out['error']['code'] == 'literal_number_in_text'
    assert out['error']['details']['numbers'] == ['100%']
    _propose(flow, 'policy', 'capacity:100', 'Call the top 100 clients.')
    _propose(flow, 'split', {**fk.SPLIT, 'validation_fraction': 0.3},
             'Keep 30% of the rows for validation, 70 % for training, seed 20261017.')


def test_digits_glued_to_letters_are_numbers_but_identifiers_are_not(flow):
    out = _propose(flow, 'policy', 'capacity:100', 'Call the top250 clients.', expect=2)
    assert out['error']['details']['numbers'] == ['250']
    _propose(flow, 'policy', 'capacity:100',
             'Call the top100 clients, as proposal p_5 said (request r_1a2b, result 1a2b3c4d5e).')
    assert cmd.literal_numbers('top100 and x2', 'capacity:100') == ['2']


@pytest.mark.parametrize('raw, canonical', [
    ('threshold:0.30', 'threshold:0.3'), ('threshold:0.3', 'threshold:0.3'),
    ('threshold:1', 'threshold:1'), ('threshold:1.0', 'threshold:1'), ('threshold:0', 'threshold:0'),
    ('capacity:5', 'capacity:5'), ('capacity: 5', 'capacity:5'), ('capacity:005', 'capacity:5'),
])
def test_policy_rules_have_one_canonical_spelling(raw, canonical):
    assert dep.canonical_rule(raw) == canonical


@pytest.mark.parametrize('raw', ['capacity:1_000', 'capacity:1e3', 'capacity:0', 'capacity:5.0',
                                 'threshold:1.5', 'threshold:nan', 'threshold:inf', 'capacity:',
                                 'threshold:-0.1', 'capacity:+5', 'capacity:٥'])
def test_malformed_rules_are_refused(raw):
    assert dep.canonical_rule(raw) is None and dep.parse_policy(raw) is None


def test_equivalent_spellings_are_one_rule_everywhere(flow):
    """threshold:0.30 is threshold:0.3 when evaluated, proposed and confirmed."""
    run = flow.run('policy.evaluate', '--rule', 'threshold:0.30', '--rule', 'threshold:0.3')
    assert read.open(flow.study).current('policy.evaluation')['params']['rules'] == [
        'threshold:0.3', 'capacity:20']
    assert set(run['values']['rules']) == {'threshold:0.3', 'capacity:20'}
    p = _propose(flow, 'policy', 'threshold:0.30', 'You call every client scored 0.3 or more.')
    assert flow.state()['proposals'][p['result']['proposal_id']]['value'] == 'threshold:0.3'
    done = flow.call('decide', 'confirm', p['result']['proposal_id'], '--user-words',
                     'Yes, call every client with a score of at least 0.3', '--request-id',
                     flow.rid(), '--expected-revision', flow.rev(), '--study', flow.study)
    assert done['result']['value'] == 'threshold:0.3'
    out = flow.run('policy.evaluate', '--rule', 'capacity:1_000', expect=2)
    assert out['error']['code'] == 'invalid_arguments'


def test_an_expected_count_is_not_a_forecast():
    """"11.5 expected for the constant baseline" is a pro rata expected count, not a
    forecast; "we expect 47 renewals" stays one (the propose-time wording check)."""
    from mlkit.study import cmd_check
    assert cmd_check.wording('It held 36 rows, against 11.5 expected for the baseline.', 'x') == []
    assert [f['code'] for f in cmd_check.wording('We expect 47 renewals.', 'x')] == [
        'forecast_wording']
