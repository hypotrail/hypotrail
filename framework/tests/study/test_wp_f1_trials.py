"""v0.3 WP-F1 (ADR 0007, CLI-CONTRACT §14): the trial budget, nested tuning, the model
families, the selection rule, and the diagnostics in the plan (R28).

* pure: the variant values (v0.2b form read as one variant), the budget, the changed slots,
  the selection (one-standard-error rule, Tibshirani & Tibshirani optimism, advice), the
  shortlist (case constraints and linear checks), the linear checks themselves;
* families: an EBM and a boosting fit are seeded and reproducible;
* flows on small synthetic cases (three folds, a few hundred rows, so the suite stays short):
  three variants with a tuned penalty and a boosting family, their selection stored and
  shown, the diagnostics run by the plan, a rule adopted for the second variant, the final
  test opened on it; a regression study choosing a tuned variant; an EBM's shapes; a v0.2b
  variant kept as one trial of the budget.

Studies live in temporary directories; nothing committed is written.
"""
from __future__ import annotations

import json
import types

import numpy as np
import pandas as pd
import pytest
import yaml

from mlkit.study import activities as act, case as c, code_cells, diagnostics as dg
from mlkit.study import families, notebook_view, registry, render_notebook
from mlkit.study import state as st, store as sto, trials

import flowkit as fk
from flowkit import Flow

CV3 = {'method': 'kfold_stratified', 'folds': 3, 'seed': 7}
CV3_REG = {'method': 'kfold_quantile', 'folds': 3, 'seed': 7}
OPEN_WORDS = 'Yes, I open the final test now, because the model and the rule are fixed'
TUNED = {'kind': 'tuned', 'question': 'Does a tuned penalty rank the rows better?'}
HGB = {'kind': 'family', 'family': 'hgb', 'question': 'Does boosting find what the line misses?'}
STRONG = {'kind': 'regularisation', 'strength': 'strong',
          'question': 'Is a stronger penalty as good?'}
EBM = {'kind': 'family', 'family': 'ebm', 'question': 'Does an EBM follow the shapes?'}


# --- pure: values and budget ------------------------------------------------------------------

def test_a_v02b_value_is_one_variant_and_a_list_keeps_its_order():
    legacy = {'kind': 'regularisation', 'strength': 'strong'}
    assert trials.variants_of(legacy) == [legacy]
    assert not trials.is_list_value(legacy)
    value = {'variants': [TUNED, HGB]}
    assert trials.variants_of(value) == [TUNED, HGB]
    assert trials.spec_of(TUNED) == {'kind': 'tuned'}
    assert trials.variants_of(None) == [] and trials.variants_of({'kind': 'other'}) == []
    assert [trials.variant_slot(i) for i in (1, 2, 3)] == ['fit.variant', 'fit.variant:2',
                                                          'fit.variant:3']
    assert trials.variant_index('fit.variant:3') == 3 and trials.variant_index('fit.x') is None


@pytest.mark.parametrize('value, words', [
    ({'variants': []}, 'list of 1 to 3'),
    ({'variants': [TUNED, HGB, STRONG, EBM]}, 'At most 3'),
    ({'variants': [{'kind': 'tuned'}]}, 'question'),
    ({'variants': [{**TUNED, 'question': ' '}]}, 'question'),
    ({'variants': [{'kind': 'family', 'family': 'forest', 'question': 'q'}]}, 'family is one of'),
    ({'variants': [{'kind': 'family', 'family': 'linear', 'question': 'q'}]}, 'family is one of'),
    ({'variants': [{'kind': 'drop_group', 'group': 'nope', 'question': 'q'}]}, 'not a group'),
    ({'variants': [TUNED, {**TUNED, 'question': 'Same model, other words?'}]}, 'twice'),
    ({'variants': [{'kind': 'tuned', 'question': 'q', 'C': 3}]}, 'A tuned variant'),
    ({'kind': 'tuned'}, None),
])
def test_values_that_are_not_variants_are_refused(value, words):
    problem = trials.check_value(value, {'contact': ['contact']}, 'binary')
    if words is None:       # a tuned variant is valid alone; commands refuses it outside a list
        assert problem is None
    else:
        assert problem is not None and words in problem, problem


def test_changed_slots_ignore_a_reworded_question_and_name_a_dropped_variant():
    before = {'variants': [TUNED, HGB]}
    reworded = {'variants': [{**TUNED, 'question': 'Other words'}, HGB]}
    assert trials.changed_slots(before, reworded) == []
    assert trials.changed_slots(before, {'variants': [TUNED, STRONG]}) == ['fit.variant:2']
    assert trials.changed_slots(before, {'variants': [TUNED]}) == ['fit.variant:2']
    assert trials.changed_slots(before, {'variants': [TUNED, HGB, STRONG]}) == []
    legacy = {'kind': 'regularisation', 'strength': 'strong'}
    assert trials.changed_slots(legacy, {'variants': [STRONG, TUNED]}) == []


def test_selection_plan_freezes_questions_outside_its_numerical_identity():
    before = _state([{'variants': [TUNED, HGB]}])
    reworded = _state([{'variants': [{**TUNED, 'question': 'Other words'}, HGB]}])
    before_inputs, reworded_inputs = {}, {}

    before_display = act._selection_inputs(before, before_inputs,
                                           ['fit.logistic', 'fit.variant', 'fit.variant:2'])
    reworded_display = act._selection_inputs(
        reworded, reworded_inputs, ['fit.logistic', 'fit.variant', 'fit.variant:2'])

    assert before_inputs == reworded_inputs
    assert before_inputs['variants'] == [{'kind': 'tuned'},
                                         {'kind': 'family', 'family': 'hgb'}]
    assert before_display[0]['question'] == TUNED['question']
    assert reworded_display[0]['question'] == 'Other words'


def _state(confirmed=(), current=None, language='en'):
    proposals = {f'p_{i}': {'proposal_id': f'p_{i}', 'decision_id': 'model_variant',
                            'status': 'confirmed', 'revision': i, 'value': v}
                 for i, v in enumerate(confirmed, start=1)}
    value = current if current is not None else (confirmed[-1] if confirmed else None)
    return {'language': language, 'proposals': proposals,
            'decisions': {'model_variant': {'status': 'confirmed' if value else 'open',
                                            'value': value}}}


def test_the_budget_counts_every_distinct_variant_ever_confirmed():
    legacy = {'kind': 'regularisation', 'strength': 'strong'}
    one = _state([legacy])
    assert trials.budget(one) == {'max': 3, 'declared': 1, 'used': 1, 'remaining': 2,
                                  'legacy': True}
    # The same variant restated with a question is not a new trial.
    two = _state([legacy, {'variants': [STRONG, TUNED]}])
    assert trials.budget(two)['used'] == 2 and trials.budget(two)['legacy'] is False
    # A replaced variant still counts.
    three = _state([legacy, {'variants': [STRONG, TUNED]}, {'variants': [STRONG, HGB]}])
    assert trials.budget(three)['used'] == 3 and trials.budget(three)['declared'] == 2
    assert len(trials.used_specs(three, {'variants': [STRONG, EBM]})) == 4


# --- pure: selection ------------------------------------------------------------------------------

def _fit(per_fold, metric='roc_auc', n_features=3):
    return {'features': [f'f{i}' for i in range(n_features)],
            'cross_validation': {'per_fold': [{'fold': i + 1, metric: v}
                                              for i, v in enumerate(per_fold)]}}


def test_selection_one_standard_error_rule_optimism_and_advice():
    fits = {'fit.logistic': _fit([0.80, 0.82, 0.78, 0.81, 0.79]),
            'fit.variant': _fit([0.81, 0.83, 0.79, 0.80, 0.80]),
            'fit.variant:2': _fit([0.83, 0.79, 0.82, 0.85, 0.79])}
    variants = [TUNED, HGB]
    out = trials.select(fits, variants, 'binary', {'max': 3, 'used': 2})
    assert out['available'] and out['folds'] == 5 and out['metric'] == 'roc_auc'
    by = {c['slot']: c for c in out['configurations']}
    cand = np.array([0.80, 0.82, 0.78, 0.81, 0.79])
    boost = np.array([0.83, 0.79, 0.82, 0.85, 0.79])
    assert by['fit.logistic']['mean'] == pytest.approx(cand.mean())
    assert by['fit.logistic']['se'] == pytest.approx(cand.std(ddof=1) / np.sqrt(5))
    d = boost - cand
    assert by['fit.variant:2']['difference']['mean'] == pytest.approx(d.mean())
    assert by['fit.variant:2']['difference']['se'] == pytest.approx(d.std(ddof=1) / np.sqrt(5))
    assert out['best'] == 'fit.variant:2'
    # One standard error of the best: the tuned linear model is within it, the candidate is
    # not; the simplest within it is kept (a linear model before the boosting one).
    threshold = boost.mean() - boost.std(ddof=1) / np.sqrt(5)
    assert out['one_se']['bound'] == pytest.approx(threshold)
    assert by['fit.variant']['within_one_se'] and not by['fit.logistic']['within_one_se']
    assert by['fit.variant:2']['within_one_se']
    assert out['one_se']['pick'] == 'fit.variant'
    # Tibshirani & Tibshirani (2009): mean over folds of (fold best - chosen config).
    table = np.vstack([cand, [0.81, 0.83, 0.79, 0.80, 0.80], boost])
    assert (table.max(axis=0) - boost).mean() > 0
    assert out['optimism']['estimate'] == pytest.approx((table.max(axis=0) - boost).mean())
    assert out['advice']['code'] == 'may_continue' and not out['advice']['stop']
    assert out['advice']['texts']['fr'] and out['one_se']['texts']['fr']


def test_selection_advises_stopping_within_fold_noise_or_at_the_budget():
    fits = {'fit.logistic': _fit([0.80, 0.82, 0.78]),
            'fit.variant': _fit([0.81, 0.81, 0.78])}
    noise = trials.select(fits, [TUNED], 'binary', {'max': 3, 'used': 1})
    assert noise['advice']['code'] == 'fold_noise' and noise['advice']['stop']
    full = trials.select(fits, [TUNED], 'binary', {'max': 3, 'used': 3})
    assert full['advice']['code'] == 'budget_exhausted'
    alone = trials.select({'fit.logistic': fits['fit.logistic']}, [], 'binary',
                          {'max': 3, 'used': 0})
    assert alone['advice']['code'] == 'no_variant'
    assert alone['advice']['noise'] == pytest.approx(np.std([0.80, 0.82, 0.78], ddof=1)
                                                     / np.sqrt(3))
    assert alone['optimism']['estimate'] == 0.0
    split = trials.select({'fit.logistic': {'features': []}}, [], 'binary', {'used': 0})
    assert split['available'] is False and split['advice']['code'] == 'not_available'


def test_selection_of_a_regression_prefers_the_lower_error():
    fits = {'fit.linear': _fit([3.0, 3.2, 2.9], 'mae'),
            'fit.variant': _fit([2.5, 2.6, 2.4], 'mae')}
    out = trials.select(fits, [TUNED], 'regression', {'max': 3, 'used': 1})
    assert out['direction'] == 'lower' and out['best'] == 'fit.variant'
    assert out['optimism']['estimate'] == pytest.approx(0.0)
    # Every fold prefers the variant by more than the noise: the pick is the variant.
    assert out['one_se']['pick'] == 'fit.variant'


# --- pure: shortlist and checks ---------------------------------------------------------------

def _diag(flags):
    return {'linear_checks': {'flags': flags, 'nonlinearity': [], 'interaction': [],
                              'calibration_slope': {'flagged': False}}}


def test_the_shortlist_follows_the_constraints_and_the_linear_checks():
    doc = {'constraints': {'interpretability': {'value': 'required', 'status':
                                                'documented_fact', 'source': 'x'}}}
    assert trials.shortlist({}, None, 'binary')['recommendation'] == 'run_diagnostics'
    calm = trials.shortlist({}, _diag([]), 'binary', 'fr')
    assert calm['recommendation'] == 'stay_linear' and calm['shortlist'] == ['linear']
    assert calm['text'] == calm['texts']['fr'] and not calm['data_contingent']
    flag = [{'check': 'nonlinearity', 'feature': 'age', 'p_value': 1e-5}]
    open_ = trials.shortlist({}, _diag(flag), 'binary')
    assert open_['shortlist'] == ['linear', 'ebm', 'hgb'] and open_['data_contingent']
    strict = trials.shortlist(doc, _diag(flag), 'binary')
    assert strict['shortlist'] == ['linear', 'ebm']
    hgb = next(f for f in strict['families'] if f['family'] == 'hgb')
    assert not hgb['allowed'] and 'black box' in hgb['excluded_reason']
    assert strict['constraints'] == {'interpretability': 'required', 'declared': True}
    contingent, why = trials.data_contingency({'variants': [EBM]}, _diag(flag), 'r1')
    assert contingent and why['flags'] == flag and 'ebm' in why['text']
    assert trials.data_contingency({'variants': [TUNED]}, _diag(flag), 'r1') == (False, None)


def test_case_constraints_are_validated(tmp_path):
    doc = yaml.safe_load(fk.make_case(tmp_path / 'case', n_rows=200)['case'].read_text())
    doc['constraints'] = {'interpretability': {'value': 'preferred', 'status': 'scenario_assumption',
                                               'source': 'The team reads the model.'}}
    assert c.validate(doc) == []
    for bad, path in (({}, 'constraints'), ({'latency': 1}, 'constraints.latency'),
                      ({'interpretability': {'value': 'maybe', 'status': 'unknown',
                                             'source': 'x'}},
                       'constraints.interpretability.value')):
        doc['constraints'] = bad
        assert path in {p['path'] for p in c.validate(doc)}, (bad, c.validate(doc))


def _case_stub(numeric=('x',), categorical=('g',)):
    variables = [{'name': n, 'role': 'feature', 'type': 'numeric'} for n in numeric]
    variables += [{'name': n, 'role': 'feature', 'type': 'category'} for n in categorical]
    return types.SimpleNamespace(variables={v['name']: v for v in variables},
                                 document={'variables': variables})


def test_linear_checks_flag_a_shape_the_line_misses_and_nothing_else():
    rng = np.random.default_rng(3)
    n = 4000
    x = rng.normal(size=n)
    g = rng.choice(['a', 'b'], n)
    frame = pd.DataFrame({'x': x, 'g': g})
    case = _case_stub()
    truth = 1 / (1 + np.exp(-(x ** 2 - 1.5)))
    y = (rng.random(n) < truth).astype(float)
    linear = np.full(n, y.mean())            # a model that cannot follow x squared
    out = dg.linear_checks(y, linear, frame, case, ['x', 'g'], True, 'fit.logistic')
    assert [f['check'] for f in out['flags']] == ['nonlinearity']
    assert out['nonlinearity'][0]['feature'] == 'x' and out['nonlinearity'][0]['flagged']
    calibrated = dg.linear_checks(y, truth, frame, case, ['x', 'g'], True, 'fit.logistic')
    assert calibrated['flags'] == []
    assert calibrated['calibration_slope']['slope'] == pytest.approx(1.0, abs=0.15)
    assert tuple(out) == dg.LINEAR_CHECK_KEYS
    # Regression: the same shape in the residuals.
    yr = x ** 2 + rng.normal(scale=0.3, size=n)
    reg = dg.linear_checks(yr, np.full(n, yr.mean()), frame, case, ['x', 'g'], False,
                           'fit.linear')
    assert reg['nonlinearity'][0]['flagged']


# --- families ---------------------------------------------------------------------------------

def test_family_fits_are_seeded_and_reproducible():
    rng = np.random.default_rng(1)
    X = pd.DataFrame({'a': rng.normal(size=300), 'b': rng.choice(['p', 'q', 'r'], 300)})
    X['b'] = X['b'].astype(object)
    y = ((X['a'] ** 2 + (X['b'] == 'p') + rng.normal(size=300)) > 1.2).astype(int).to_numpy()
    for family, value in (('ebm', 0), ('hgb', 2)):
        one = families.fit_family(family, X, y, True, value, 5)
        two = families.fit_family(family, X, y, True, value, 5)
        assert np.array_equal(families.predict_family(family, one, X, True),
                              families.predict_family(family, two, X, True))
    terms = families.ebm_terms(families.fit_family('ebm', X, y, True, 0, 5), True)
    assert terms['kind'] == 'ebm_terms' and {t['term'] for t in terms['terms']} == {'a', 'b'}
    shapes = {t['term']: t['shape'] for t in terms['terms']}
    assert shapes['a']['type'] == 'continuous' and shapes['b']['type'] == 'nominal'
    assert len(shapes['a']['points']) <= families.MAX_SHAPE_POINTS
    assert families.versions('ebm')['interpret-core'] == '0.7.3'


# --- flows ------------------------------------------------------------------------------------

def _flow(tmp_path, task='binary', n_rows=300, split=CV3) -> Flow:
    case_dir = fk.make_case(tmp_path / 'case', task=task, n_rows=n_rows)['case'].parent
    flow = Flow(tmp_path / 'study', case_dir)
    flow.init()
    flow.decide('prediction_time', 'when the record is created, before the outcome')
    flow.decide('feature_availability', fk.availability(case_dir))
    flow.decide('split', split)
    flow.model_decisions()
    flow.run('split')
    explore = next(s for s in st.steps(flow.state()) if s['id'] == 'train_eda')
    for activity in explore['activities']:
        flow.run(activity)
    return flow


def _propose(flow, decision, value, expect=0):
    return flow.call('decide', 'propose', decision, '--value-json', json.dumps(value),
                     '--restatement', f'You decide the {decision} as stated.',
                     '--rationale', 'It fits the scenario.', '--request-id', flow.rid(),
                     '--expected-revision', flow.rev(), '--study', flow.study, expect=expect)


def _confirm(flow, pid, words):
    return flow.call('decide', 'confirm', pid, '--user-words', words, '--request-id',
                     flow.rid(), '--expected-revision', flow.rev(), '--study', flow.study)


def _values(flow, slot):
    store = sto.StudyStore(flow.study)
    return registry.get(store, flow.state()['current'][slot])['output']['values']


def _run_next(flow, activity):
    action = flow.view()['next_action']
    assert action['kind'] == 'run' and action['activity'] == activity, action
    return flow.run(activity)


def test_three_variants_are_compared_chosen_and_opened(tmp_path):
    flow = _flow(tmp_path)
    flow.run('fit.baseline')
    flow.run('fit.logistic')
    # R28: the diagnostics of the first linear fit are the next step, before any variant.
    _run_next(flow, 'diag.binary')
    view = flow.view()
    assert view['model_families']['evidence']['checked']
    assert view['model_families']['recommendation'] in ('stay_linear', 'compare_nonlinear')
    action = view['next_action']
    assert action['decision'] == 'model_variant'
    assert action['default_value'] == trials.draft('binary')
    value = {'variants': [TUNED, HGB, STRONG]}
    proposed = _propose(flow, 'model_variant', value)['result']
    assert proposed['data_contingent'] in (True, False)
    _confirm(flow, proposed['proposal_id'], fk.default_words('model_variant'))
    state = flow.state()
    assert state['current']['diag.binary'] in state['stale']      # it compares the variants
    assert trials.declared_slots(state) == list(trials.VARIANT_SLOTS)
    for slot in trials.VARIANT_SLOTS:
        _run_next(flow, slot)
    tuned, boost, strong = (_values(flow, s) for s in trials.VARIANT_SLOTS)
    assert [f['value'] in trials.GRIDS[('linear', 'binary')]['values']
            for f in tuned['tuning']['per_fold']] == [True] * 3
    assert tuned['tuning']['development']['value'] in trials.GRIDS[('linear', 'binary')]['values']
    assert boost['family'] == 'hgb' and 'coefficients' not in boost
    assert boost['family_diagnostics']['kind'] == 'permutation_importance'
    assert boost['variant_index'] == 2 and strong['variant_index'] == 3
    assert strong['C'] == act.VARIANT_C['strong']
    # A fourth distinct variant is over the budget.
    refused = _propose(flow, 'model_variant', {'variants': [TUNED, HGB, EBM]}, expect=2)
    assert refused['error']['code'] == 'invalid_value'
    assert refused['error']['details']['budget'] == {'max': 3, 'used': 3, 'would_use': 4}
    assert flow.view()['next_action']['decision'] == 'model_choice'
    flow.decide('model_choice', 'fit.variant:2',
                words='Yes, retain the boosting variant because it ranks best')
    assert flow.view()['next_action']['activity'] == 'policy.evaluation'
    flow.run('policy.evaluate', '--rule', 'capacity:30')
    evaluation = _values(flow, 'policy.evaluation')
    assert set(evaluation['rules']['capacity:30']['comparisons']) == set(trials.VARIANT_SLOTS)
    assert set(evaluation['gain_points_variants']) == {'fit.variant:2', 'fit.variant:3'}
    stored = evaluation['model_selection']
    # The within-fold rule scope of B6c keeps its own key.
    assert evaluation['selection']['scope'] == 'within_fold'
    live = flow.view()['model_selection']
    assert stored['available'] and len(stored['configurations']) == 4
    assert [c.get('question') for c in stored['configurations'][1:]] == \
        [TUNED['question'], HGB['question'], STRONG['question']]
    assert [c['mean'] for c in stored['configurations']] == \
        [c['mean'] for c in live['configurations']]
    assert stored['optimism']['estimate'] == live['optimism']['estimate']
    assert live['budget']['used'] == 3 and live['advice']['code'] == 'budget_exhausted'
    _run_next(flow, 'diag.binary')
    diag = _values(flow, 'diag.binary')
    assert set(diag['models']) == {'fit.logistic', *trials.VARIANT_SLOTS}
    assert diag['models']['fit.variant:2']['coefficients'] is None
    assert diag['models']['fit.variant:2']['family_diagnostics']['kind'] == \
        'permutation_importance'
    assert diag['linear_checks']['model'] == 'fit.logistic'
    # The rule adopted for the second variant: the diagnostics run again at that rule.
    policy = flow.call('decide', 'propose', 'policy', '--value-json',
                       json.dumps('capacity:30@fit.variant:2'), '--restatement',
                       'You call the top 30 rows by the boosting score.', '--rationale', 'r',
                       '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                       '--study', flow.study)['result']['proposal_id']
    _confirm(flow, policy, 'Yes, I adopt that rule because the desk can make that many calls')
    _run_next(flow, 'diag.binary')
    assert _values(flow, 'diag.binary')['rule'] == 'capacity:30'
    assert flow.view()['next_action']['decision'] == 'final_test'
    opening = st.b1_default_value(flow.state(), 'final_test')
    assert opening == {'model': 'fit.variant:2', 'rule': 'capacity:30'}
    pid = _propose(flow, 'final_test', opening)['result']['proposal_id']
    result = _confirm(flow, pid, OPEN_WORDS)['result']
    assert result['opening']['status'] == 'promoted', result['opening']
    final = _values(flow, 'final_test.evaluation')
    assert final['model'] == 'fit.variant:2' and final['family'] == 'hgb'
    assert final['tuning']['development']['value'] in (2, 4)
    # The deliverables cite every number, and the notebook's selection cell holds.
    flow.call('render', '--study', flow.study)
    check = flow.call('check', '--study', flow.study, expect=None)
    assert check['clean'], check['findings']
    html = (flow.study / 'reports' / 'study.html').read_text()
    assert 'id="variants"' in html and 'data-advice="budget_exhausted"' in html
    view = flow.view()
    _, code = code_cells.selection_cell(view, 'binary')
    study = notebook_view.open_study(flow.study)
    exec(code, {'nv': notebook_view, 'study': study, 'np': np, 'pd': pd,
                'RESULT_IDS': render_notebook.result_ids(view),
                'TOLERANCE': code_cells.TOLERANCE})


def test_a_regression_study_chooses_a_tuned_ridge(tmp_path):
    flow = _flow(tmp_path, task='regression', split=CV3_REG)
    flow.run('fit.baseline')
    flow.run('fit.linear')
    _run_next(flow, 'diag.regression')
    pid = _propose(flow, 'model_variant', {'variants': [TUNED]})['result']['proposal_id']
    _confirm(flow, pid, fk.default_words('model_variant'))
    _run_next(flow, 'fit.variant')
    variant = _values(flow, 'fit.variant')
    assert variant['model'] == 'ridge' and variant['tuning']['parameter'] == 'alpha'
    _run_next(flow, 'evaluate.regression')
    selection = _values(flow, 'evaluate.regression')['model_selection']
    assert selection['metric'] == 'mae' and selection['direction'] == 'lower'
    _run_next(flow, 'diag.regression')
    flow.decide('model_choice', 'fit.variant',
                words='Yes, I choose that model because its error is smaller')
    # Review round 9 (R9E-4): adopting rests on the final test, so it is opened first.
    flow.decide('final_test', st.choice_config(flow.state()),
                words='Yes, I open the final test now, because the model is fixed')
    flow.decide('conclusion', {'verdict': 'adopt_model', 'text': 'The tuned ridge is kept.'},
                words='Yes, I conclude that, because the tuned model is the one I chose')
    assert flow.state()['decisions']['conclusion']['status'] == 'confirmed'


def test_an_ebm_variant_registers_its_shapes(tmp_path):
    flow = _flow(tmp_path, n_rows=200)
    flow.run('fit.baseline')
    flow.run('fit.logistic')
    flow.run('diag.binary')
    pid = _propose(flow, 'model_variant', {'variants': [EBM]})['result']['proposal_id']
    _confirm(flow, pid, fk.default_words('model_variant'))
    flow.run('fit.variant')
    values = _values(flow, 'fit.variant')
    terms = values['family_diagnostics']
    assert values['family'] == 'ebm' and terms['kind'] == 'ebm_terms'
    assert any(t['shape'] for t in terms['terms'] if t['kind'] == 'main')
    assert values['versions']['interpret-core'] == '0.7.3'
    assert len(values['tuning']['per_fold']) == 3
    entry = registry.get(sto.StudyStore(flow.study), flow.state()['current']['fit.variant'])
    assert {'interpret._version', 'sklearn'} <= set(entry['code']['modules'])


def test_a_v02b_variant_is_one_trial_and_restating_it_refits_nothing(tmp_path):
    flow = _flow(tmp_path, n_rows=200)
    flow.run('fit.baseline')
    flow.run('fit.logistic')
    legacy = {'kind': 'regularisation', 'strength': 'strong'}
    flow.decide('model_variant', legacy)       # the diagnostics are not required to name it
    flow.run('fit.variant')
    first = flow.state()['current']['fit.variant']
    budget = flow.view()['model_selection']['budget']
    assert budget == {'max': 3, 'declared': 1, 'used': 1, 'remaining': 2, 'legacy': True}
    flow.decide('model_variant', {'variants': [{**legacy, 'question': 'Is a stronger penalty '
                                                'as good?'}, TUNED]})
    state = flow.state()
    assert state['current']['fit.variant'] == first and first not in state['stale']
    assert trials.declared_slots(state) == ['fit.variant', 'fit.variant:2']
    assert flow.view()['next_action']['activity'] == 'fit.variant:2'
    refused = flow.call('run', 'fit.variant:3', '--request-id', flow.rid(),
                        '--expected-revision', flow.rev(), '--study', flow.study, expect=2)
    assert refused['error']['code'] == 'precondition_missing'


def test_source_compatibility_needs_an_exact_destination_and_activity(tmp_path):
    """J4 replaces the old module allowlist with exact directed attestations."""
    from mlkit.study import code_compat, read
    case_dir = fk.make_case(tmp_path / 'case', n_rows=200)['case'].parent
    Flow(tmp_path / 'study', case_dir).init()
    study = read.open(tmp_path / 'study')
    now = registry.code_fingerprint(['mlkit.study.metrics'])['modules']
    assert code_compat.integrity()
    # The pre-WP-J digests: the first edge of each module that covers diag.final_test only.
    old = {}
    for r in code_compat.ATTESTATIONS:
        if r['activities'] == ['diag.final_test']:
            old.setdefault(r['module'], r['from_sha256'])
    assert set(old) == {'mlkit.study.activities', 'mlkit.study.diagnostics'}
    entry = {'activity': 'diag.final_test', 'code': {'modules': {**old, **now}}}
    assert study.code_changed(entry) == []
    entry['activity'] = 'diag.binary'
    assert study.code_changed(entry) == ['mlkit.study.activities', 'mlkit.study.diagnostics']
    first = code_compat.ATTESTATIONS[0]
    assert not code_compat.equivalent(first['module'], first['from_sha256'],
                                      first['to_sha256'], None)
