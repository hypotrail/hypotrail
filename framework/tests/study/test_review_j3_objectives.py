"""Independent numeric oracles for reliability-roadmap J3."""
import math
import pytest

from mlkit.study import objective


Y = [1, 1, 1, 0, 0, 0, 0, 0]
A = [.8, .7, .6, .9, .5, .4, .3, .2]
B = [.9, .8, .1, .7, .6, .5, .4, .3]


def test_j3_a01_business_objective_picks_b_not_auc_winner():
    a = objective.evaluate_binary(Y, A, metric='precision', rule='share:0.25')
    b = objective.evaluate_binary(Y, B, metric='precision', rule='share:0.25')
    assert a['point'] == .5 and b['point'] == 1


def test_j3_a03_median_baseline_minimizes_fixture_mae():
    y = [0, 0, 0, 0, 100]
    mean = objective.evaluate_regression(y, [20] * 5)
    median = objective.evaluate_regression(y, objective.regression_baseline(y, 5))
    assert mean['point'] == 32 and median['point'] == 20


@pytest.mark.parametrize(('gain', 'low', 'high', 'point', 'lower'), [
    (6, 1, 11, 'met', 'uncertain'), (6, None, None, 'met', 'uncertain'),
    (7, 5.1, 9, 'met', 'met'), (5, 5, 5, 'met', 'met'),
    (4, 1, 4.9, 'not_met', 'not_met'), (4, 1, 9, 'not_met', 'uncertain'),
])
def test_j3_a05_truth_table(gain, low, high, point, lower):
    qualified = low is not None
    assert objective.assess(gain, 5, decision_rule='point_estimate', low=low, high=high,
                            interval_qualified=qualified)['decision_status'] == point
    assert objective.assess(gain, 5, decision_rule='lower_bound', low=low, high=high,
                            interval_qualified=qualified)['decision_status'] == lower


def test_j3_a05_malformed_intervals_and_nonfinite_values_are_rejected():
    with pytest.raises(ValueError):
        objective.assess(6, 5, low=9, high=1, interval_qualified=True)
    with pytest.raises(ValueError):
        objective.assess(math.nan, 5)


def test_j3_a06_capacity_is_literal_per_batch():
    y = [1] * 240
    out = objective.evaluate_binary(y, list(range(240)), metric='precision',
                                    rule='capacity:100',
                                    batches=['small'] * 40 + ['large'] * 200,
                                    scope='column_batch')
    assert [w['selected'] for w in out['per_window']] == [40, 100]
    assert out['per_window'][0]['underfilled']


def test_j3_a07_precision_uses_pooled_counts_not_fold_mean():
    out = objective.evaluate_binary([1] + [0] * 9, list(range(10, 0, -1)),
                                    metric='precision', rule='capacity:10',
                                    windows=['a'] + ['b'] * 9)
    assert out['point'] == .1


def test_j3_a08_undefined_threshold_objectives_stay_unavailable():
    precision = objective.evaluate_binary([1, 0], [.1, .2], metric='precision',
                                          rule='threshold:0.9')
    recall = objective.evaluate_binary([0, 0], [.9, .8], metric='recall',
                                       rule='threshold:0.5')
    assert not precision['available'] and precision['point'] is None
    assert not recall['available'] and recall['point'] is None


def test_j3_a09_unqualified_interval_cannot_satisfy_lower_bound_rule():
    out = objective.assess(7, 5, decision_rule='lower_bound', low=6, high=8,
                           interval_qualified=False, uncertainty_status='unavailable')
    assert out['decision_status'] == 'uncertain'
    assert out['basis'] == 'unavailable'


def test_review_criterion_rejects_boolean_and_mismatched_metric():
    value = {'metric': 'precision_gain', 'min_points': True,
             'decision_rule': 'point_estimate',
             'selection': {'metric': 'precision', 'rule': 'share:0.1',
                           'scope': 'evaluation_window', 'batch_column': None,
                           'aggregation': 'pooled_counts'}}
    with pytest.raises(ValueError):
        objective.validate_criterion(value, 'binary')
