"""``hypotrail check --text``: numbers written in words and retired proposals (final
acceptance F3, T9).

Agents wrote self-made ratios and counts in words ("roughly one call in nine", "the 11 kept
columns" as "the eleven kept columns"), which the digit parser could not see, and repeated
the figures of withdrawn proposals. Both directions are tested: a word number used
quantitatively is traced like digits (and reported when it matches nothing), and ordinary
words ("one model", "a single", "first") are never read as numbers.
"""
from __future__ import annotations

import uuid

import pytest

from mlkit.study import cmd_check, commands as cmd, read, view, wordnum


def codes(result) -> list[str]:
    return [f['code'] for f in result['findings']]


@pytest.fixture
def study(full_study):
    return full_study


# --- the parser ---------------------------------------------------------------------------

@pytest.mark.parametrize('text, kind, value', [
    ('roughly one call in nine', 'ratio', 1 / 9),
    ('one in nine', 'ratio', 1 / 9),
    ('two out of three clients', 'ratio', 2 / 3),
    ('un sur neuf', 'ratio', 1 / 9),
    ('un client sur neuf', 'ratio', 1 / 9),
    ('the eleven kept columns', 'count', 11),
    ('twenty-one clients', 'count', 21),
    ('a hundred calls', 'count', 100),
    ('vingt et un clients', 'count', 21),
    ('quatre-vingt-dix appels', 'count', 90),
    ('soixante-dix-sept lignes', 'count', 77),
    ('three quarters of the rows', 'fraction', 0.75),
    ('half of the clients', 'fraction', 0.5),
    ('a third of the rows', 'fraction', 1 / 3),
    ('la moitié des clients', 'fraction', 0.5),
    ('deux tiers des lignes', 'fraction', 2 / 3),
    ('trois quarts des appels', 'fraction', 0.75),
    ('a dozen calls', 'count', 12),
    ('two dozen calls', 'count', 24),
    ('une douzaine de clients', 'count', 12),
    ('eleven percent of the rows', 'percent', 11),
    ('onze pour cent des clients', 'percent', 11),
    ('five percentage points', 'points', 5),
])
def test_quantitative_word_numbers_are_read(text, kind, value):
    found = wordnum.parse(text)
    assert len(found) == 1, found
    assert found[0].kind == kind and found[0].value == pytest.approx(value)


@pytest.mark.parametrize('text', [
    'We fit one model and a single baseline.',
    'The first step is the prediction moment.',
    'One of the columns describes the call.',
    'Both models use the same rows; nine models would be too many.',
    'Step two is the split; pause one is the prediction moment.',
    'On a un modèle et une seule colonne en doute.',
    'In the first half of the plan we frame the change; the other half compares.',
    'One or two questions remain.',
    'Two hundred clients is outside the words read.',
    'Dozens of variables, several rules, and most clients.',
])
def test_ordinary_words_are_not_numbers(text):
    assert wordnum.parse(text) == []


# --- tracing ------------------------------------------------------------------------------

@pytest.mark.parametrize('draft, number', [
    ('Roughly one call in fifty ends in a subscription.', 'one call in fifty'),
    ('The model combines the forty-three kept columns.', 'forty-three'),
    ('Environ un client sur cinquante souscrit.', 'un client sur cinquante'),
    ('The logistic model ranks quarante-trois clients first.', 'quarante-trois'),
    ('Two thirds of the rows are negatives.', 'Two thirds'),
    ('About one client in six subscribes.', 'one client in six'),
])
def test_untraceable_numbers_in_words_are_reported(study, draft, number):
    result = cmd_check.run_check(study, draft)
    assert codes(result) == ['untraceable_number'], result['findings']
    details = result['findings'][0]['details']
    assert details['number'] == number and details['in_words'] is True
    assert result['clean'] is False


def test_numbers_in_words_that_match_a_registered_value_are_traced(study):
    """The base rate 25 / 210 (0.119) is about "one in eight"; the validation partition
    holds 11 positives, written "eleven subscribers"."""
    v = view.build(study)
    result = cmd_check.run_check(study, 'On the training rows, about one client in eight '
                                        'subscribed; the validation rows hold eleven '
                                        'subscribers.')
    assert result['findings'] == [], result['findings']
    traced = {t['text']: t for t in result['traced']}
    assert set(traced) == {'one client in eight', 'eleven'}
    assert all(t['in_words'] is True for t in traced.values())
    assert traced['one client in eight']['result_id'] in {
        r['result_id'] for r in v['results'].values()}


def test_ordinary_words_in_a_draft_are_not_claims(study):
    draft = ('We fit one model, a single logistic regression, and the first step was the '
             'prediction moment. One of the columns stays a doubt.')
    result = cmd_check.run_check(study, draft)
    assert result['findings'] == [] and result['traced'] == []


def test_the_juniors_own_words_may_be_repeated_in_words(study):
    draft = 'You said the team reaches one client in six.'
    assert codes(cmd_check.run_check(study, draft)) == ['untraceable_number']
    result = cmd_check.run_check(study, draft, ['We usually reach one client in six.'])
    assert result['findings'] == [], result['findings']
    assert result['traced'][0]['source'] == 'user_text'


def test_a_number_in_words_can_make_a_forecast(study):
    result = cmd_check.run_check(study, 'We will get one client in eight next campaign.')
    assert 'forecast_wording' in codes(result)


# --- retired proposals --------------------------------------------------------------------

def _apply(study, action, params):
    out = cmd.apply(study, action=action, params=params, request_id=uuid.uuid4().hex,
                    expected_revision=read.open(study).revision)
    assert out.exit_code in (0, 3), out.payload
    return out.payload['result']


def _propose(study, value):
    return _apply(study, cmd.ACTION_PROPOSE,
                  {'decision_id': 'policy', 'value': value,
                   'restatement': 'You call the clients the rule selects.',
                   'rationale': 'An illustrative capacity.'})['proposal_id']


def _withdraw(study, pid):
    _apply(study, cmd.ACTION_WITHDRAW, {'proposal_id': pid, 'reason': 'stand-in figure'})


def test_an_open_proposal_figure_is_a_literal(study):
    draft = 'The open proposal calls the 20 best-scored clients.'
    _propose(study, 'capacity:20')
    result = cmd_check.run_check(study, draft)
    assert result['findings'] == [], result['findings']


@pytest.mark.parametrize('retire', ['withdrawn', 'superseded'])
def test_a_retired_proposal_figure_is_not_traceable(study, retire, monkeypatch):
    """F3: "Withdraw the 136 proposal" repeated a figure that is no longer on the table.
    The figure is untraceable once its proposal is withdrawn or superseded, and the finding
    names the proposal. An evaluated rule is still a literal, so the test drops it."""
    def drop_rules(view_model):
        item = view_model['results'].get('policy.evaluation')
        if item and isinstance(item.get('params'), dict):
            item['params']['rules'] = []
        return view_model
    build = view.build
    monkeypatch.setattr(cmd_check.view_model, 'build',
                        lambda *a, **k: drop_rules(build(*a, **k)))
    draft = 'I removed the 137-call placeholder.'
    pid = _propose(study, 'capacity:137')
    assert cmd_check.run_check(study, draft)['findings'] == []
    if retire == 'withdrawn':
        _withdraw(study, pid)
    else:
        _propose(study, 'capacity:20')
    result = cmd_check.run_check(study, draft)
    assert codes(result) == ['untraceable_number'], result['findings']
    details = result['findings'][0]['details']
    assert details['number'] == '137'
    assert details['retired_proposal'] == pid and details['proposal_status'] == retire
    assert pid in result['findings'][0]['message']


def test_retired_proposals_are_read_from_state(study):
    pid = _propose(study, 'capacity:137')
    _withdraw(study, pid)
    retired = cmd_check.retired_proposals(read.open(study))
    assert {'proposal_id': pid, 'status': 'withdrawn', 'value': 'capacity:137'} in retired
