"""WP-B6b: ``check --text`` traces what the v0.2b acceptance runs showed it could not.

* a diagnostic's coefficients and their bootstrap intervals (the instructions ask the
  agent to read them with the junior), while a fit's raw coefficients, the point check of
  the refit and the drawn scatter points stay internal;
* the success criterion as ``status`` shows it (``view.criterion``): the gain and its
  interval, in points for a scoring study, as a share of the baseline's MAE for a
  regression, on the development evidence and on the final test once opened;
* the French verb "gagne" names a gain.

Studies and cases live in ``tmp_path``.
"""
from __future__ import annotations

import json

import pytest

from mlkit.study import cmd_check, state as st

import flowkit as fk
from flowkit import Flow

OPEN_WORDS = 'Yes, I open the final test now, because the model and the rule are fixed'


def _ready(tmp_path, task) -> Flow:
    case_dir = fk.make_case(tmp_path / 'case', task=task, n_rows=600)['case'].parent
    flow = Flow(tmp_path / 'study', case_dir)
    flow.init()
    flow.decide('prediction_time', 'when the record is created, before the outcome')
    flow.decide('feature_availability', fk.availability(case_dir))
    flow.decide('split', flow.view()['next_action']['default_value'])
    flow.model_decisions()
    flow.run('split')
    flow.run('fit.baseline')
    flow.run('fit.linear' if task == 'regression' else 'fit.logistic')
    flow.variant()
    return flow


def _errors(study, text):
    out = cmd_check.run_check(study, text)
    return [f['details'].get('number') for f in out['findings']
            if f['code'] == 'untraceable_number']


def _open(flow, rule=None):
    value = st.b1_default_value(flow.state(), 'final_test')
    p = flow.call('decide', 'propose', 'final_test', '--value-json', json.dumps(value),
                  '--restatement', 'You open the sealed final test once.',
                  '--rationale', 'Everything is chosen.', '--request-id', flow.rid(),
                  '--expected-revision', flow.rev(), '--study', flow.study)
    flow.call('decide', 'confirm', p['result']['proposal_id'], '--user-words', OPEN_WORDS,
              '--request-id', flow.rid(), '--expected-revision', flow.rev(),
              '--study', flow.study)


def test_internal_paths_of_fits_and_diagnostics():
    assert cmd_check.internal_path('fit.logistic', 'coefficients.age')
    assert not cmd_check.internal_path('diag.binary',
                                       'models.[fit.logistic].coefficients.terms.0.value')
    assert not cmd_check.internal_path('diag.final_test',
                                       'models.[fit.logistic].coefficients.terms.0.low')
    assert cmd_check.internal_path('diag.binary', 'models.[fit.logistic].coefficients.'
                                                  'point_check.max_difference')
    assert cmd_check.internal_path('diag.regression',
                                   'models.[fit.linear].scatter.points.3.residual')
    # The bootstrap's own settings stay internal in a diagnostic too.
    assert cmd_check.internal_path('diag.binary', 'models.[fit.logistic].coefficients.seed')


def test_binary_diagnostic_coefficients_and_criterion_gain_are_traced(tmp_path):
    flow = _ready(tmp_path, 'binary')
    flow.run('policy.evaluate', '--rule', 'capacity:40')
    flow.decide('policy', 'capacity:40',
                words='I adopt capacity 40 because the desk can make 40 calls')
    values = flow.run('diag.binary')['values']
    term = values['models']['fit.logistic']['coefficients']['terms'][0]
    text = (f"{term['term'].split('__')[-1]}: {term['value']:.2f} "
            f"(interval {term['low']:.2f} to {term['high']:.2f}).")
    assert _errors(flow.study, text) == []
    crit = flow.view()['criterion']
    assert crit['status'] != 'not_assessed'
    gain = f"{crit['gain']:.1f}".replace('.', ',')
    assert _errors(flow.study, f'La précision gagne {gain} points sur la référence.') == []
    assert _errors(flow.study, f"Precision rose by {crit['gain']:.1f} points over the "
                               f"baseline.") == []
    # A figure no result holds is still untraceable.
    assert _errors(flow.study, 'La précision gagne 97,3 points sur la référence.') == ['97,3']
    # After the opening, the criterion on the final test is traced the same way.
    _open(flow)
    final = flow.view()['criterion']['final_test']
    assert final and final['gain'] is not None
    text = (f"On the final test, precision rose by {final['gain']:.1f} points over the "
            f"baseline (interval {final['low']:.1f} to {final['high']:.1f} points).")
    assert _errors(flow.study, text) == []


def test_regression_criterion_share_is_traced(tmp_path):
    flow = _ready(tmp_path, 'regression')
    flow.run('evaluate.regression')
    flow.run('diag.regression')
    crit = flow.view()['criterion']
    assert crit['unit'] == 'share' and crit['gain'] is not None
    text = (f"The linear model removes {100 * crit['gain']:.0f}% of the baseline's MAE "
            f"(interval {100 * crit['low']:.0f}% to {100 * crit['high']:.0f}%).")
    assert _errors(flow.study, text) == []
    text = (f"It removes a share of {crit['gain']:.2f} of the baseline's MAE "
            f"(interval {crit['low']:.2f} to {crit['high']:.2f}).")
    assert _errors(flow.study, text) == []


@pytest.mark.parametrize('criterion,expected', [
    (None, []),
    ({'metric': 'precision_gain', 'result_id': None, 'gain': 3.0}, []),
    ({'metric': 'mae_reduction', 'result_id': 'r1', 'gain': 0.4, 'low': 0.3, 'high': None,
      'final_test': {'result_id': 'r2', 'gain': 0.5, 'low': None, 'high': 0.6}},
     [('criterion.mae_reduction.gain', 0.4), ('criterion.mae_reduction.low', 0.3),
      ('criterion.final_test.mae_reduction.gain', 0.5),
      ('criterion.final_test.mae_reduction.high', 0.6)]),
])
def test_criterion_items(criterion, expected):
    items = cmd_check.criterion_items(criterion)
    assert [(i['path'], i['value']) for i in items] == expected


def _bind(text, number):
    start = text.index(number)
    return cmd_check.binding(text, start, start + len(number), number.endswith('%'))


def test_both_bounds_of_a_range_read_as_an_interval():
    text = '| Variant | 3.78 mpg | 3.44 à 4.13 | 4.96 mpg |'
    assert _bind(text, '3.44').interval and _bind(text, '4.13').interval
    # A bound alone, next to no range.
    assert not _bind('The MAE is 3.44 mpg.', '3.44').interval
    text = 'It removed 47% of the error (40% to 54%).'
    assert _bind(text, '40%').interval and _bind(text, '54%').interval


def test_model_years_name_no_model():
    text = "The baseline's mean residual goes from -5.19 mpg in model years 70 to 72 to 9.63"
    assert not cmd_check.MODEL_WORDS.search('in model years 70 to 72')
    assert cmd_check.MODEL_WORDS.search('the linear model errs less')
    assert not _bind(text, '9.63').model


def test_group_labels_are_literals():
    values = {'residuals_by': [{'column': 'model_year', 'groups': [
        {'value': '70 to 72 year (19xx)', 'n_rows': 67},
        {'value': '81 to 82 year (19xx)', 'n_rows': 50}]}],
        'models': {'m': {'by_feature': [{'groups': [{'value': '(2166.8, 2584.4]'}]}]}}}
    assert cmd_check.group_labels(values) == ['70 to 72 year (19xx)', '81 to 82 year (19xx)',
                                              '(2166.8, 2584.4]']


def test_period_labels_are_traced_in_a_regression_study(tmp_path):
    case_dir = fk.make_case(tmp_path / 'case', task='regression', n_rows=600,
                            time=True)['case'].parent
    flow = Flow(tmp_path / 'study', case_dir)
    flow.init()
    flow.decide('prediction_time', 'when the record is created, before the outcome')
    flow.decide('feature_availability', fk.availability(case_dir))
    flow.decide('split', flow.view()['next_action']['default_value'])
    flow.model_decisions()
    flow.run('split')
    flow.run('fit.baseline')
    flow.run('fit.linear')
    flow.variant()
    values = flow.run('evaluate.regression')['values']
    labels = [g['value'] for block in values.get('residuals_by') or [] for g in block['groups']]
    assert labels, values.get('residuals_by')
    text = 'The periods are ' + ', '.join(labels) + '.'
    assert _errors(flow.study, text) == [], text
