"""WP-B6c: the fresh review of v0.2b, each finding with its test.

* B1: the binary final-test criterion is shown in percentage points at its registered size
  (the value is already in points); ``check`` catches a value shown 100 times too large
  (``test_report_and_notebook_real.py`` holds the real-study checks).
* H1: the data section says the final test was opened, and that something changed after.
* H3: under cross-validation a capacity or a share is applied within each fold (pure
  functions here; Bank full in ``test_wp_b1_integration.py``).
* H4: once opened, the criterion is judged on the final test; a ``keep_baseline`` verdict
  against a met final criterion is a limit and a check warning.

Studies and cases live in ``tmp_path``; the committed cases are only read.
"""
from __future__ import annotations

import json
import re

import numpy as np
import pytest

from mlkit.study import cmd_check, governance, manifest as mf, policy, state as st

import flowkit as fk
from flowkit import Flow

OPEN_WORDS = 'Yes, I open the final test now, because the model and the rule are fixed'


# --- helpers ----------------------------------------------------------------------------------

def _flow(tmp_path, task='binary', n_rows=600) -> Flow:
    case_dir = fk.make_case(tmp_path / 'case', task=task, n_rows=n_rows)['case'].parent
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
    if task == 'binary':
        flow.run('policy.evaluate', '--rule', 'capacity:40')
        flow.decide('policy', 'capacity:40',
                    words='Yes, I adopt that rule because the desk can make that many calls')
    else:
        flow.run('evaluate.regression')
        flow.decide('model_choice', 'fit.linear',
                    words='Yes, I choose that model because its error is smaller')
    return flow


def _open(flow):
    value = st.b1_default_value(flow.state(), 'final_test')
    pid = flow.call('decide', 'propose', 'final_test', '--value-json', json.dumps(value),
                    '--restatement', 'You open the sealed final test once, for the chosen '
                                     'configuration.', '--rationale', 'Everything is chosen.',
                    '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                    '--study', flow.study)['result']['proposal_id']
    out = flow.call('decide', 'confirm', pid, '--user-words', OPEN_WORDS, '--request-id',
                    flow.rid(), '--expected-revision', flow.rev(), '--study', flow.study)
    assert out['result']['opening']['status'] == 'promoted'


def _page(flow) -> str:
    flow.call('render', '--study', flow.study)
    return (flow.study / mf.ARTIFACTS['report']).read_text(encoding='utf-8')


def _section(page: str, sid: str) -> str:
    return re.search(rf'<section class="card[^"]*" id="{sid}">.*?</section>', page,
                     re.S).group(0)


@pytest.fixture(scope='module')
def opened(tmp_path_factory):
    flow = _flow(tmp_path_factory.mktemp('b6c_open'))
    _open(flow)
    return flow


# --- H1: the data section after the opening ----------------------------------------------------

def test_the_data_section_says_the_final_test_was_opened(opened, tmp_path):
    flow = Flow(fk.clone(opened.study, tmp_path / 'study'), opened.case_dir, prefix='h1')
    data = _section(_page(flow), 'data')
    assert 'no final test' not in data and 'stay sealed' not in data
    assert 'it has been opened once to measure the chosen configuration' in data
    assert 'Something changed after the opening' not in data
    # A change after the opening: the data section says so too.
    flow.run('policy.evaluate', '--rule', 'capacity:30')
    flow.decide('policy', 'capacity:30',
                words='Yes, I adopt that rule because the desk now has thirty slots')
    assert flow.view()['final_test']['post_final_test'] is True
    data = _section(_page(flow), 'data')
    assert 'Something changed after the opening' in data


# --- H4: the criterion judged on the final test ------------------------------------------------

def _view(final_status, dev_point, verdict, final_model='fit.logistic',
          final_rule='capacity:10'):
    gain = {'met': 8.0, 'uncertain': 6.0, 'not_met': 1.0}[final_status]
    low = {'met': 2.0, 'uncertain': -1.0, 'not_met': -3.0}[final_status]
    results = {
        'policy.evaluation': {'current': True, 'integrity': 'ok', 'result_id': 'r_pol',
                              'values': {'rules': {'capacity:10': {'deltas': {
                                  'fit.logistic': {'precision': {
                                      'point': dev_point, 'low': dev_point - 0.03,
                                      'high': dev_point + 0.03}}}}}}},
        'final_test.evaluation': {'current': True, 'integrity': 'ok', 'result_id': 'r_fin',
                                  'values': {'model': final_model, 'rule': final_rule,
                                             'criterion': {'status': final_status, 'gain': gain,
                                                           'low': low, 'high': gain + 4,
                                                           'minimum': 5,
                                                           'unit': 'percentage points',
                                                           'interval_includes_zero':
                                                               low <= 0}}}}
    decisions = {'success_criterion': {'status': 'confirmed',
                                       'value': {'metric': 'precision_gain', 'min_points': 5}},
                 'policy': {'status': 'confirmed', 'value': 'capacity:10'},
                 'conclusion': {'status': 'confirmed', 'value': {'verdict': verdict,
                                                                 'text': 'x'}}}
    return {'task': 'binary', 'decisions': decisions, 'results': results,
            'open_proposals': []}


@pytest.mark.parametrize('final_status, dev_point, verdict, judged, contradicts, keeps', [
    # The development figures met the criterion, the final test does not: adopting is
    # flagged, keeping the baseline is not.
    ('not_met', 0.10, 'adopt_policy', 'not_met', True, False),
    ('uncertain', 0.10, 'adopt_policy', 'uncertain', True, False),
    ('not_met', 0.10, 'keep_baseline', 'not_met', False, False),
    # The development figures did not meet it, the final test does: adopting is consistent,
    # keeping the baseline is a tension to explain.
    ('met', 0.02, 'adopt_policy', 'met', False, False),
    ('met', 0.02, 'keep_baseline', 'met', False, True),
])
def test_once_opened_the_criterion_is_judged_on_the_final_test(final_status, dev_point, verdict,
                                                                judged, contradicts, keeps):
    out = governance.assess(_view(final_status, dev_point, verdict))
    assert out['judged_on'] == 'final_test' and out['judged_status'] == judged
    assert out['status'] == ('met' if dev_point == 0.10 else 'not_met')   # context
    assert out['contradicts_verdict'] is contradicts
    assert governance.keeps_against_met(out) is keeps
    findings = cmd_check.check_criterion({'criterion': out})
    codes = [f['code'] for f in findings]
    if contradicts:
        assert codes == ['verdict_contradicts_criterion']
        assert findings[0]['details']['judged_on'] == 'final_test'
        assert 'on the final test' in findings[0]['message']
    elif keeps:
        assert codes == ['verdict_keeps_baseline_against_criterion']
        assert findings[0]['severity'] == 'warning'
        assert 'keeps the baseline although' in findings[0]['message']
        assert 'say which' in findings[0]['message']
    else:
        assert codes == []


def test_a_final_evaluation_of_another_configuration_does_not_judge_the_criterion():
    # The policy changed after the opening: the final test measured capacity:20.
    out = governance.assess(_view('met', 0.02, 'keep_baseline', final_rule='capacity:20'))
    assert out['judged_on'] == 'development' and out['judged_status'] == 'not_met'
    assert governance.keeps_against_met(out) is False
    out = governance.assess(_view('met', 0.10, 'adopt_policy', final_model='fit.variant'))
    assert out['judged_on'] == 'development'


def test_the_verdict_card_shows_one_judged_criterion(opened, tmp_path):
    view = opened.view()
    crit = view['criterion']
    assert crit['judged_on'] == 'final_test'
    assert crit['judged_status'] == crit['final_test']['status']
    verdict = _section(_page(Flow(fk.clone(opened.study, tmp_path / 'study'),
                                  opened.case_dir, prefix='h4')), 'verdict')
    row = verdict[verdict.index('<dt>Success criterion</dt>'):]
    row = row[:row.index('</dd>')]
    assert 'on the final test, where it is judged once the final test is opened' in row
    assert f'data-development-status="{crit["status"]}"' in row
    assert ('They differ because' in row) is (crit['status'] != crit['judged_status'])
    # One status badge for the criterion: the final-test figures row has none.
    final_row = verdict[verdict.index('Success criterion on the final test'):]
    final_row = final_row[:final_row.index('</dd>')]
    assert 'class="badge' not in final_row
    assert 'Precision gain over the baseline' in final_row


# --- H3: rules within each fold (pure) ----------------------------------------------------------

def test_a_share_is_applied_within_each_fold():
    # Two folds whose models score on different scales: pooled, the top 50 % are all rows of
    # fold 2; within folds, the best half of each fold.
    y = np.array([1, 0, 0, 0, 1, 0, 0, 0], dtype=float)
    score = np.array([0.30, 0.20, 0.10, 0.05, 0.90, 0.95, 0.85, 0.80])
    groups = np.array([1, 1, 1, 1, 2, 2, 2, 2])
    pooled = policy.evaluate(y, score, 'share:0.25')
    within = policy.evaluate(y, score, 'share:0.25', groups)
    assert pooled['true_positives'] == 1 and pooled['selected'] == 2      # fold 2 only
    assert within['selection_scope'] == 'within_fold' and within['capacity'] == 2
    assert within['true_positives'] == 1 and within['selected'] == 2
    assert [f['capacity'] for f in within['by_fold']] == [1, 1]
    assert [f['true_positives'] for f in within['by_fold']] == [1, 0]
    assert [f['precision'] for f in within['by_fold']] == [1.0, 0.0]
    # A capacity keeps its share of the rows in each fold: capacity:4 of 8 is half of each.
    cap = policy.evaluate(y, score, 'capacity:4', groups)
    assert [f['capacity'] for f in cap['by_fold']] == [2, 2] and cap['capacity'] == 4
    assert cap['true_positives'] == 2      # fold 1: rows 0 and 1; fold 2: rows 5 and 4
    assert policy.evaluate(y, score, 'capacity:4')['true_positives'] == 1
    # A threshold reads the scores as they are.
    th = policy.evaluate(y, score, 'threshold:0.5', groups)
    assert th['selection_scope'] == 'pooled' and th['selected'] == 4
    # The weights select the same rows as the counts.
    w, _ = policy.weights(score, 'share:0.25', groups)
    assert w.tolist() == [1, 0, 0, 0, 0, 1, 0, 0]
    gain = policy.gain_points(y, score, shares=(0.25,), groups=groups)
    assert gain['selection_scope'] == 'within_fold'
    assert gain['points'][0]['true_positives'] == 1 and gain['points'][0]['capacity'] == 2


def test_the_within_fold_bootstrap_keeps_each_fold_and_its_capacity():
    rng = np.random.default_rng(3)
    n = 300
    groups = np.repeat([1, 2, 3], 100)
    y = (rng.random(n) < 0.2).astype(float)
    score = rng.random(n) + groups            # a different scale per fold
    base = np.full(n, y.mean())
    out = policy.paired_bootstrap(y, {'fit.baseline': base, 'fit.logistic': score},
                                  'share:0.1', 50, 7, groups=groups)
    assert out['method'] == 'paired percentile bootstrap, rows resampled within each fold'
    point = policy.evaluate(y, score, 'share:0.1', groups)
    assert out['deltas']['fit.logistic']['precision']['point'] == pytest.approx(
        point['precision'] - y.mean())
    # Every replicate selects exactly the summed capacity (10 rows per fold).
    assert out['intervals']['fit.logistic']['volume']['low'] == 30
    assert out['intervals']['fit.logistic']['volume']['high'] == 30
    again = policy.paired_bootstrap(y, {'fit.baseline': base, 'fit.logistic': score},
                                    'share:0.1', 50, 7, groups=groups)
    assert again == out
