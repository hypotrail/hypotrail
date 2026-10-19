"""Regression study units (M3): errors and bootstrap, split methods, decisions, the
dependency table, task blocks of the instructions, and the task-aware texts.

Studies are created in ``tmp_path`` from the committed Auto MPG case (only read) or from
the regression variant of the synthetic generator.
"""
from __future__ import annotations

import copy
import json

import numpy as np
import pandas as pd
import pytest

from mlkit.reliability import CommandRefused
from mlkit.study import (activities as act, agent_files as af, case as c, commands as cmd,
                         dependencies as dep, preconditions as pre, regression, state as st,
                         texts)

import flowkit as fk

AUTO = fk.REPO / 'use-cases' / 'auto-mpg'
BINARY_VOCABULARY = ('threshold', 'positive class', 'precision', 'recall', 'capacity')


@pytest.fixture(scope='module')
def auto_state():
    return st.initial_state(c.load_case(AUTO))


# --- errors and the paired bootstrap ---------------------------------------------------------

def test_errors_and_residuals_are_in_the_unit_of_the_target():
    y = [10.0, 12.0, 14.0, 20.0]
    pred = [11.0, 11.0, 15.0, 16.0]
    e = regression.errors(y, pred)
    assert e['mae'] == pytest.approx((1 + 1 + 1 + 4) / 4)
    assert e['rmse'] == pytest.approx(np.sqrt((1 + 1 + 1 + 16) / 4))
    assert e['mean_residual'] == pytest.approx((-1 + 1 - 1 + 4) / 4)      # observed - predicted
    assert e['max_abs_residual'] == 4.0 and e['n'] == 4
    r = regression.residual_summary(y, pred)
    assert r['mean'] == pytest.approx(e['mean_residual'])
    assert r['min'] <= r['q05'] <= r['q25'] <= r['median'] <= r['q75'] <= r['q95'] <= r['max']
    with pytest.raises(ValueError):
        regression.errors([1.0, float('nan')], [1.0, 1.0])
    with pytest.raises(ValueError):
        regression.errors([1.0], [1.0, 2.0])


def test_paired_bootstrap_is_deterministic_and_paired():
    rng = np.random.default_rng(3)
    y = rng.normal(20, 5, 120)
    preds = {'fit.baseline': np.full(120, y.mean()), 'fit.linear': y + rng.normal(0, 2, 120)}
    a = regression.paired_bootstrap(y, preds, 500, 7, reference='fit.baseline')
    b = regression.paired_bootstrap(y, preds, 500, 7, reference='fit.baseline')
    assert a == b
    d = a['deltas']['fit.linear']['mae']
    assert d['point'] == pytest.approx(a['models']['fit.linear']['mae']
                                       - a['models']['fit.baseline']['mae'])
    assert d['low'] <= d['point'] <= d['high'] < 0          # clearly smaller error
    assert 'fit.baseline' not in a['deltas']
    for model in preds:
        for m in ('mae', 'rmse'):
            iv = a['intervals'][model][m]
            assert iv['low'] <= a['models'][model][m] <= iv['high']
    # Identical predictions: every paired difference is exactly zero.
    same = regression.paired_bootstrap(y, {'a': preds['fit.linear'], 'b': preds['fit.linear']},
                                       200, 1)
    assert same['deltas']['b']['mae'] == {'point': 0.0, 'low': 0.0, 'high': 0.0}
    with pytest.raises(ValueError):
        regression.paired_bootstrap(y, preds, 0, 1)


# --- split methods and integer time columns ----------------------------------------------------

def test_split_methods_follow_the_task_and_the_time_column(auto_state, new_study):
    binary = new_study.load_state()
    assert cmd.split_methods(binary) == ['stratified_random']
    assert cmd.split_methods(auto_state) == ['ordinal_cutoff']
    no_time = copy.deepcopy(auto_state)
    no_time['structure']['time_column']['value'] = None
    assert cmd.split_methods(no_time) == ['random']
    cmd.validate_split(auto_state, {'method': 'ordinal_cutoff', 'column': 'model_year',
                                    'cutoff': 79})
    cmd.validate_split(no_time, {'method': 'random', 'validation_fraction': 0.3, 'seed': 1})
    for state, value, code in (
            (auto_state, {'method': 'random', 'validation_fraction': 0.3, 'seed': 1},
             'invalid_value'),
            (auto_state, {'method': 'ordinal_cutoff', 'column': 'weight', 'cutoff': 79},
             'invalid_value'),
            (auto_state, {'method': 'ordinal_cutoff', 'column': 'model_year', 'cutoff': 79.5},
             'invalid_value'),
            (auto_state, {'method': 'ordinal_cutoff', 'column': 'model_year', 'cutoff': True},
             'invalid_value'),
            (no_time, {'method': 'stratified_random', 'validation_fraction': 0.3, 'seed': 1},
             'invalid_value'),
            (no_time, {'method': 'ordinal_cutoff', 'column': 'model_year', 'cutoff': 79},
             'invalid_value'),
            (binary, {'method': 'random', 'validation_fraction': 0.3, 'seed': 1},
             'invalid_value'),
            (auto_state, {'method': 'grouped', 'validation_fraction': 0.3, 'seed': 1},
             'unsupported_capability')):
        with pytest.raises(CommandRefused) as info:
            cmd.validate_split(state, value)
        assert info.value.code == code, (value, info.value.message)


def test_ordinal_values_never_convert_integers_to_dates(monkeypatch):
    def no_dates(*args, **kwargs):
        raise AssertionError('pd.to_datetime must not be called on an integer time column')
    monkeypatch.setattr(pd, 'to_datetime', no_dates)
    frame = pd.DataFrame({'year': [70, 71, 82]}, index=['L1', 'L2', 'L3'])
    assert act.ordinal_values(frame, 'year').tolist() == [70, 71, 82]
    with pytest.raises(Exception) as info:
        act.ordinal_values(pd.DataFrame({'year': [70.5, 71]}, index=['L1', 'L2']), 'year')
    assert info.value.code == 'invalid_value' and info.value.details['rows'] == ['L1']
    with pytest.raises(Exception) as info:
        act.ordinal_values(pd.DataFrame({'year': [None, 71]}, index=['L1', 'L2']), 'year')
    assert info.value.code == 'invalid_value'


def test_group_overlap_counts_shared_groups():
    frame = pd.DataFrame({'g': ['a', 'a', 'b', 'c', 'c', 'd']},
                         index=['L1', 'L2', 'L3', 'L4', 'L5', 'L6'])
    out = act.group_overlap(frame, 'g', {'train': ['L1', 'L3', 'L4'],
                                         'validation': ['L2', 'L5', 'L6']})
    assert (out['n_groups'], out['train_groups'], out['validation_groups']) == (4, 3, 3)
    assert out['shared_groups'] == 2 and out['examples'] == ['a', 'c']
    assert out['validation_rows_in_shared_groups'] == 2
    assert out['validation_share_in_shared_groups'] == pytest.approx(2 / 3)
    assert out['capability'] == 'grouped split (v0.2)'


# --- decisions and preconditions --------------------------------------------------------------

def test_model_choice_and_regression_verdicts(auto_state):
    state = copy.deepcopy(auto_state)
    for d in ('prediction_time', 'feature_availability', 'split'):
        state['decisions'][d]['status'] = 'confirmed'
    assert cmd.validate_value(state, 'model_choice', 'fit.linear') is None
    with pytest.raises(CommandRefused):
        cmd.validate_value(state, 'model_choice', 'fit.logistic')
    with pytest.raises(CommandRefused):
        cmd.validate_value(state, 'conclusion', {'verdict': 'adopt_policy', 'text': 'x'})
    cmd.validate_value(state, 'conclusion', {'verdict': 'adopt_model', 'text': 'x'})
    missing = pre.missing_for_decision(state, 'model_choice', 'fit.linear')
    assert [m['slot'] for m in missing] == ['evaluate.regression']
    assert pre.missing_for_decision(state, 'conclusion',
                                    {'verdict': 'keep_baseline', 'text': 'x'}) == []
    [need] = pre.missing_for_decision(state, 'conclusion', {'verdict': 'adopt_model', 'text': 'x'})
    assert need['decision'] == 'model_choice'
    # Post-v0.1 fixes (D6): "inconclusive" is allowed before a model is chosen.
    assert pre.missing_for_decision(state, 'conclusion',
                                    {'verdict': 'inconclusive', 'text': 'x'}) == []
    with_choice = copy.deepcopy(state)
    with_choice['decisions']['conclusion'].update(
        status='confirmed', value={'verdict': 'inconclusive', 'text': 'x'})
    [item] = [x for x in st.not_yet_defensible(with_choice)
              if x['id'] == 'inconclusive_without_choice']
    assert item['decisions'] == ['model_choice'] and 'no model is chosen' in item['text']
    state['decisions']['model_choice'].update(status='confirmed', value='fit.baseline')
    assert pre.missing_for_decision(state, 'conclusion',
                                    {'verdict': 'inconclusive', 'text': 'x'}) == []
    [need] = pre.missing_for_decision(state, 'conclusion', {'verdict': 'adopt_model', 'text': 'x'})
    assert 'fit.linear' in need['detail']
    state['decisions']['model_choice']['value'] = 'fit.linear'
    assert pre.missing_for_decision(state, 'conclusion',
                                    {'verdict': 'adopt_model', 'text': 'x'}) == []
    state['current']['split'] = 'r_split'
    assert [m['slot'] for m in pre.missing_for_activity(state, 'evaluate.regression')] == [
        'fit.baseline', 'fit.linear']


def test_regression_activities_are_refused_in_a_binary_study_and_back(auto_state, new_study):
    with pytest.raises(CommandRefused) as info:
        act.plan(new_study, new_study.load_state(), 'evaluate.regression', {})
    assert info.value.code == 'invalid_arguments'
    assert info.value.details['task'] == 'binary'
    with pytest.raises(CommandRefused) as info:
        act.plan(None, auto_state, 'policy.evaluate', {'rules': ['capacity:10']})
    assert info.value.code == 'invalid_arguments'
    assert 'evaluate.regression' in info.value.details['activities']
    assert act.slot_of('eda.mean_by', {'column': 'origin'}) == 'eda.mean_by:origin'
    assert act.activity_of('eda.mean_by:origin') == 'eda.mean_by'


# --- dependency table (plan §3.7, regression) -------------------------------------------------

@pytest.mark.parametrize('decision, old, new, mutation, row, refit, reconfirm', [
    ('prediction_time', 'a', 'b', 'prediction_time', 1, ['fit.linear'],
     ['feature_availability', 'model_choice', 'conclusion']),
    ('feature_availability', {'x': 'available_at_prediction'}, {'x': 'not_available'},
     'feature_availability.feature_set', 2, ['fit.linear'], ['model_choice', 'conclusion']),
    ('feature_availability', {'x': 'not_available'}, {'x': 'uncertain_excluded'},
     'feature_availability.wording', 3, [], []),
    ('split', {'method': 'ordinal_cutoff', 'column': 'y', 'cutoff': 1},
     {'method': 'ordinal_cutoff', 'column': 'y', 'cutoff': 2}, 'split', 4,
     ['fit.baseline', 'fit.linear'], ['model_choice', 'conclusion']),
    ('model_choice', 'fit.linear', 'fit.baseline', 'model_choice', 13, [], ['conclusion']),
    ('conclusion', {'verdict': 'keep_baseline', 'text': 'a'},
     {'verdict': 'adopt_model', 'text': 'a'}, 'conclusion', 10, [], []),
    ('model_choice', 'fit.linear', {'odd': 1}, 'unknown', '*', ['fit.baseline', 'fit.linear'],
     ['prediction_time', 'feature_availability', 'split', 'conclusion']),
])
def test_regression_dependency_rows(auto_state, decision, old, new, mutation, row, refit,
                                    reconfirm):
    eff = dep.effects(auto_state, decision, old, new)
    assert (eff['mutation'], eff['row']) == (mutation, row)
    assert eff['refit'] == refit and eff['reconfirm'] == reconfirm
    if mutation in ('prediction_time', 'feature_availability.feature_set', 'split'):
        assert eff['re_policy'] == ['evaluate.regression']
    assert 'policy' not in eff['reconfirm'] and 'fit.logistic' not in eff['refit']


def test_regression_replacement_reconfirms_model_choice(auto_state):
    state = copy.deepcopy(auto_state)
    for d in ('model_choice', 'conclusion'):
        state['decisions'][d].update(status='confirmed', value='fit.linear',
                                     confirmation={'user_words': 'w'})
    record = dep.apply_replacement(state, 'fit.linear', 'r_old', 'r_new', revision=9,
                                   store=None)
    assert record['reconfirm_required'] == ['model_choice', 'conclusion']


# --- instructions and texts -------------------------------------------------------------------

def test_task_blocks_select_one_task_and_drop_markers():
    text = ('a\n<!-- hypotrail:task binary -->\nb\n<!-- hypotrail:task regression -->\nr\n'
            '<!-- hypotrail:end -->\nz\n')
    assert af.select_task(text, 'binary') == 'a\nb\nz\n'
    assert af.select_task(text, 'regression') == 'a\nr\nz\n'
    for broken in ('<!-- hypotrail:end -->\n', '<!-- hypotrail:task binary -->\nx\n'):
        with pytest.raises(ValueError):
            af.select_task(broken, 'binary')
    with pytest.raises(ValueError):
        af.select_task(text, 'multiclass')


def test_regression_instructions_and_glossary_hold_no_binary_vocabulary(tmp_path):
    for rel in af.templates():
        text = af.select_task((af.SOURCE / rel).read_text(encoding='utf-8'), 'regression')
        found = [w for w in BINARY_VOCABULARY if w in text.lower()]
        assert not found, (rel, found)
        assert 'hypotrail:' not in text
    glossary = af.glossary_bytes('regression').decode('utf-8').lower()
    assert not [w for w in BINARY_VOCABULARY if w in glossary]
    assert af.glossary_bytes('binary') == af.GLOSSARY.read_bytes()


def test_regression_glossary_terms():
    terms = texts.glossary_terms('regression')
    for term in ('mae', 'rmse', 'residual', 'bias', 'extrapolation', 'ordinal_split',
                 'group_overlap', 'target_distribution', 'linear_regression'):
        assert terms[term]['term'] and terms[term]['definition'], term
    for hidden in ('threshold', 'capacity', 'precision', 'recall', 'policy', 'base_rate'):
        assert hidden not in terms
    assert texts.glossary('threshold', 'binary') is not None
    assert texts.glossary('threshold', 'regression') is None
    assert 'training mean' in texts.glossary('baseline', 'regression')['definition']
    with texts.task_context('regression'):
        assert texts.glossary('threshold') is None
        assert texts.report()['sections']['policy'] == 'Model comparison'
        assert texts.step('model_choice')['concept'] == 'mae'
        assert texts.activity('eda.mean_by:origin')['label'].endswith(': origin')
    assert texts.report()['sections']['policy'] == 'Policy comparison'
    assert texts.report('regression')['verdict']['adopt_model'] == 'Adopt the linear model'


def test_regression_view_names_its_task(tmp_path):
    flow = fk.Flow(tmp_path / 's', AUTO, prefix='v')
    flow.init()
    view = flow.view()
    assert view['task'] == 'regression'
    assert tuple(view['decisions']) == st.REGRESSION_DECISION_IDS
    question = view['plan'][0]['question']
    # v0.2a (WP-A1): plus the audience of the message and its junior variant (the question).
    assert view['next_action'] == {'kind': 'propose', 'step': 'prediction_time',
                                   'decision': 'prediction_time', 'message': question,
                                   'audience': 'junior', 'junior_message': question}
    text = json.dumps(view).lower()
    assert not [w for w in BINARY_VOCABULARY if w in text]
