"""Pure business-objective scoring and success assessment for review-v1.

This module deliberately knows nothing about studies or result slots.  Tuning,
model selection, policy evaluation, final evaluation and generated notebooks can
therefore use the same arithmetic.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Mapping, Sequence

from .progress import step     # L8 (R10 level 2): a no-op unless ``run --progress`` listens

TOLERANCE = 1e-12
DECISION_RULES = ('point_estimate', 'lower_bound')
BINARY_METRICS = ('precision', 'recall')


def _number(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(float(value)):
        raise ValueError(f'{name} must be a finite number (not a boolean)')
    return float(value)


def validate_criterion(value: Mapping, task: str) -> None:
    if not isinstance(value, Mapping):
        raise ValueError('success criterion must be an object')
    decision_rule = value.get('decision_rule')
    if decision_rule not in DECISION_RULES:
        raise ValueError('decision_rule must be point_estimate or lower_bound')
    selection = value.get('selection')
    if not isinstance(selection, Mapping):
        raise ValueError('selection must be an object')
    if task == 'binary':
        metric = value.get('metric')
        expected = {'precision_gain': 'precision', 'recall_gain': 'recall'}
        if metric not in expected:
            raise ValueError('metric must be precision_gain or recall_gain')
        minimum = _number(value.get('min_points'), 'min_points')
        if not 0 <= minimum <= 100:
            raise ValueError('min_points must be between 0 and 100')
        if selection.get('metric') != expected[metric]:
            raise ValueError('selection.metric must match the declared gain metric')
        if not isinstance(selection.get('rule'), str):
            raise ValueError('selection.rule must fix the action rule')
        _rule(selection['rule'])
        if selection.get('scope') not in ('evaluation_window', 'column_batch'):
            raise ValueError('selection.scope must be evaluation_window or column_batch')
        if selection.get('aggregation') != 'pooled_counts':
            raise ValueError('binary selection aggregation must be pooled_counts')
        if selection['scope'] == 'column_batch':
            column = selection.get('batch_column')
            if not isinstance(column, str) or not column.strip():
                raise ValueError('column_batch scope requires batch_column')
        elif selection.get('batch_column') is not None:
            raise ValueError('batch_column must be null for evaluation_window scope')
    elif task == 'regression':
        if value.get('metric') != 'mae_reduction':
            raise ValueError('regression metric must be mae_reduction')
        minimum = _number(value.get('min_share'), 'min_share')
        if not 0 <= minimum < 1:
            raise ValueError('min_share must be from 0 to below 1')
        expected = {'metric': 'mae', 'rule': None, 'scope': 'evaluation_window',
                    'batch_column': None, 'aggregation': 'row_weighted'}
        if any(selection.get(k) != v for k, v in expected.items()):
            raise ValueError('regression selection must use row-weighted MAE')
    else:
        raise ValueError(f'unknown task {task!r}')


def _rule(rule: str) -> tuple[str, float]:
    kind, sep, raw = rule.partition(':')
    if not sep or kind not in ('share', 'capacity', 'threshold'):
        raise ValueError('rule must be share:p, capacity:k, or threshold:t')
    value = _number(float(raw), 'rule value')
    if kind == 'share' and not 0 < value <= 1:
        raise ValueError('share must be in (0, 1]')
    if kind == 'capacity' and (value < 1 or value != int(value)):
        raise ValueError('capacity must be a positive integer')
    return kind, value


def _select(y, scores, kind, value):
    """Expected confusion counts with pro-rata score ties at a top-k boundary."""
    n = len(y)
    if kind == 'threshold':
        weights = [1.0 if score >= value else 0.0 for score in scores]
    else:
        wanted = min(float(n), value * n if kind == 'share' else value)
        if wanted <= 0:
            weights = [0.0] * n
        else:
            order = sorted(range(n), key=lambda i: (-scores[i], i))
            boundary = scores[order[min(int(math.ceil(wanted)), n) - 1]]
            above = sum(score > boundary for score in scores)
            tied = sum(score == boundary for score in scores)
            fraction = min(1.0, max(0.0, (wanted - above) / tied))
            weights = [1.0 if score > boundary else fraction if score == boundary else 0.0
                       for score in scores]
    selected = sum(weights)
    tp = sum(weight for target, weight in zip(y, weights) if target == 1)
    positives = sum(1 for target in y if target == 1)
    return {'n': n, 'selected': selected, 'tp': tp, 'fp': selected - tp,
            'fn': positives - tp, 'positives': positives,
            'underfilled': kind == 'capacity' and n < value,
            'fractional_tie_counts': any(weight not in (0.0, 1.0) for weight in weights)}


def evaluate_binary(y: Sequence, scores: Sequence, *, metric: str, rule: str,
                    windows: Sequence | None = None, batches: Sequence | None = None,
                    scope: str = 'evaluation_window') -> dict:
    """Evaluate precision/recall by pooled counts over declared action batches."""
    if metric not in BINARY_METRICS:
        raise ValueError('binary objective metric must be precision or recall')
    if len(y) != len(scores) or not len(y):
        raise ValueError('y and scores must have the same non-zero length')
    y = [int(v) for v in y]
    if any(v not in (0, 1) for v in y):
        raise ValueError('binary targets must be 0 or 1')
    scores = [_number(v, 'score') for v in scores]
    kind, value = _rule(rule)
    grouping = batches if scope == 'column_batch' else windows
    if grouping is None:
        grouping = [1] * len(y)
    if len(grouping) != len(y):
        raise ValueError('window/batch identifiers must align with rows')
    positions = defaultdict(list)
    for i, group in enumerate(grouping):
        positions[(type(group).__name__, repr(group))].append(i)
    per_window = []
    for group, ii in positions.items():
        counts = _select([y[i] for i in ii], [scores[i] for i in ii], kind, value)
        precision = counts['tp'] / counts['selected'] if counts['selected'] else None
        recall = counts['tp'] / counts['positives'] if counts['positives'] else None
        per_window.append({'window': group[1], **counts,
                           'precision': precision, 'recall': recall})
    total = {key: sum(item[key] for item in per_window)
             for key in ('n', 'selected', 'tp', 'fp', 'fn', 'positives')}
    point = (total['tp'] / total['selected'] if metric == 'precision' and total['selected']
             else total['tp'] / total['positives'] if metric == 'recall' and total['positives']
             else None)
    reason = None if point is not None else ('no_rows_selected' if metric == 'precision'
                                             else 'no_positive_outcomes')
    return {'metric': metric, 'direction': 'maximize', 'point': point,
            'denominators': total, 'per_window': per_window,
            'available': point is not None, 'unavailability_reason': reason,
            'rule': rule, 'scope': scope, 'aggregation': 'pooled_counts'}


def evaluate_regression(y: Sequence, predictions: Sequence,
                        windows: Sequence | None = None) -> dict:
    if len(y) != len(predictions) or not len(y):
        raise ValueError('y and predictions must have the same non-zero length')
    y, predictions = ([_number(v, 'target') for v in y],
                      [_number(v, 'prediction') for v in predictions])
    windows = list(windows) if windows is not None else [1] * len(y)
    if len(windows) != len(y):
        raise ValueError('window identifiers must align with rows')
    positions = defaultdict(list)
    for i, window in enumerate(windows):
        positions[(type(window).__name__, repr(window))].append(i)
    per_window, absolute_sum = [], 0.0
    for window, ii in positions.items():
        total = sum(abs(y[i] - predictions[i]) for i in ii)
        absolute_sum += total
        per_window.append({'window': window[1], 'n': len(ii), 'absolute_error_sum': total,
                           'mae': total / len(ii)})
    return {'metric': 'mae', 'direction': 'minimize', 'point': absolute_sum / len(y),
            'denominators': {'n': len(y), 'absolute_error_sum': absolute_sum},
            'per_window': per_window, 'available': True,
            'unavailability_reason': None, 'rule': None,
            'scope': 'evaluation_window', 'aggregation': 'row_weighted'}


def regression_baseline(train_targets: Sequence, n: int) -> list[float]:
    """The review-v1 MAE reference: the training median, repeated ``n`` times."""
    values = sorted(_number(v, 'training target') for v in train_targets)
    if not values:
        raise ValueError('the baseline needs training targets')
    middle = len(values) // 2
    median = values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2
    return [median] * n


def relative_mae_reduction(model_mae, baseline_mae):
    model, baseline = _number(model_mae, 'model_mae'), _number(baseline_mae, 'baseline_mae')
    return None if abs(baseline) <= TOLERANCE else (baseline - model) / baseline


def paired_row_bootstrap(y: Sequence, predictions: Mapping[str, Sequence], evaluator,
                         *, replicates: int, seed: int, level: float = .95) -> dict:
    """Conservative paired bootstrap: one undefined replicate invalidates the interval.

    ``evaluator(y_sample, prediction_sample)`` returns an objective mapping with ``point``.
    Identical sampled positions are supplied to every model.
    """
    import random
    if type(replicates) is not int or replicates < 1:
        raise ValueError('replicates must be a positive integer')
    if not 0 < level < 1:
        raise ValueError('level must be between zero and one')
    n = len(y)
    if not n or any(len(values) != n for values in predictions.values()):
        raise ValueError('all bootstrap arrays must have the same non-zero length')
    names = list(predictions)
    reference = names[0]
    rng, samples = random.Random(seed), {name: [] for name in names}
    delta_samples = {name: [] for name in names if name != reference}
    undefined = 0
    for b in range(replicates):
        step('replicate', b + 1, replicates)
        positions = [rng.randrange(n) for _ in range(n)]
        yy = [y[i] for i in positions]
        points = {}
        for name, values in predictions.items():
            result = evaluator(yy, [values[i] for i in positions])
            points[name] = result.get('point') if isinstance(result, Mapping) else None
        if any(point is None for point in points.values()):
            undefined += 1
            continue
        for name, point in points.items():
            samples[name].append(float(point))
        for name in delta_samples:
            delta_samples[name].append(float(points[name]) - float(points[reference]))
    descriptor = {'method': 'paired_row_bootstrap', 'level': level,
                  'resampling_unit': 'row', 'target_quantity': 'declared_objective',
                  'conditioning': 'fixed selected configuration',
                  'dependence_assumptions': 'independent held-out observations',
                  'eligible': undefined == 0, 'replicates': replicates,
                  'undefined_replicates': undefined,
                  'reason': None if undefined == 0 else
                  'at least one required bootstrap replicate had an undefined objective'}
    if undefined:
        return {'intervals': {name: {'low': None, 'high': None} for name in predictions},
                'delta_intervals': {name: {'low': None, 'high': None}
                                    for name in delta_samples},
                'uncertainty': descriptor}
    alpha = (1 - level) / 2

    def quantile(values, q):
        values = sorted(values)
        position = q * (len(values) - 1)
        low, high = int(math.floor(position)), int(math.ceil(position))
        return values[low] + (values[high] - values[low]) * (position - low)
    return {'intervals': {name: {'low': quantile(values, alpha),
                                 'high': quantile(values, 1 - alpha)}
                          for name, values in samples.items()},
            'delta_intervals': {name: {'low': quantile(values, alpha),
                                       'high': quantile(values, 1 - alpha)}
                                for name, values in delta_samples.items()},
            'uncertainty': descriptor}


def assess(gain, minimum, *, decision_rule: str = 'point_estimate', low=None, high=None,
           interval_qualified: bool = False, uncertainty_status: str | None = None) -> dict:
    """Apply the complete point/lower-bound decision truth table."""
    if decision_rule not in DECISION_RULES:
        raise ValueError('unknown decision_rule')
    if gain is None:
        return {'point_meets_minimum': None, 'interval_excludes_zero': None,
                'lower_bound_meets_minimum': None,
                'uncertainty_status': uncertainty_status or 'unavailable',
                'decision_rule': decision_rule, 'decision_status': 'not_assessed',
                'basis': 'unavailable'}
    minimum = _number(minimum, 'minimum')
    gain = _number(gain, 'gain')
    if (low is None) != (high is None):
        raise ValueError('an interval requires both low and high')
    if low is not None:
        low, high = _number(low, 'low'), _number(high, 'high')
        if low > high:
            raise ValueError('interval low must not exceed high')
    qualified = bool(interval_qualified and low is not None)
    point_meets = gain >= minimum - TOLERANCE
    excludes_zero = None if low is None else not (low <= 0 <= high)
    lower_meets = low >= minimum - TOLERANCE if qualified else None
    status = uncertainty_status or ('available' if qualified else
                                    'descriptive' if low is not None else 'unavailable')
    if decision_rule == 'point_estimate':
        decision_status = 'met' if point_meets else 'not_met'
        basis = 'point_estimate'
    elif qualified and lower_meets:
        decision_status, basis = 'met', 'qualified_interval'
    elif qualified and not point_meets and high < minimum - TOLERANCE:
        decision_status, basis = 'not_met', 'qualified_interval'
    else:
        decision_status, basis = 'uncertain', ('qualified_interval' if qualified
                                               else 'unavailable')
    return {'point_meets_minimum': point_meets,
            'interval_excludes_zero': excludes_zero,
            'lower_bound_meets_minimum': lower_meets,
            'uncertainty_status': status, 'decision_rule': decision_rule,
            'decision_status': decision_status, 'basis': basis}


def evaluate(*args, task='binary', **kwargs):
    return evaluate_binary(*args, **kwargs) if task == 'binary' else evaluate_regression(*args,
                                                                                        **kwargs)
