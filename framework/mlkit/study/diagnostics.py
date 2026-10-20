"""Model diagnostics (v0.2b, WP-B4, owner remark R9): where a model errs, and how far its
scores can be read as probabilities.

Three activities (``CLI-CONTRACT.md`` §13) read stored predictions, never a new model
fit for the predictions themselves:

* ``diag.binary`` and ``diag.regression`` read the **out-of-fold predictions** of the
  candidate and of the variant (the validation predictions in a train/validation study)
  on the development rows. They are **development evidence**: the model and the rule were
  chosen on these rows. Their exposure purpose is ``development_diagnostics``; each run
  reads the target, so it is counted as a look in the ledger of target looks.
* ``diag.final_test`` reads the predictions of the one evaluation of the final test, after
  the junior opened it, for the chosen configuration only. It is **final evidence**,
  recorded with the purpose ``final_evaluation`` on the final-test rows. Before the opening
  it is refused and reads nothing.

Binary diagnostics, per model, at one rule (the adopted rule, else the proposed one, else
the case's teaching share, else :data:`DEFAULT_RULE`):

* the confusion matrix (:func:`confusion`; counts are expected counts when a capacity cut
  splits a tie group, as in the policy evaluation);
* the gain curve: for the top 5 %, 10 %, ... 100 % of the scored rows, the positive rows
  found (recall, the cumulative gain), the lift, the precision, and the false positive
  rate, which also gives the ROC and precision-recall curves at those points
  (:func:`curve`), with the exact AUC and average precision;
* the calibration (:func:`calibration`): ten equal-count bins of the score, in score order,
  with the mean score, the observed rate and its Wilson interval, and the Brier score next
  to the Brier score of the constant base rate;
* precision and recall at the rule by segment (:func:`segments`) for at most two
  categorical features the model uses (case order), with Wilson intervals and counts, and
  small cells flagged;
* up to five false positives (selected, negative, highest scores first) and five false
  negatives (not selected, positive, lowest scores first) by row key with the feature values
  as written in the file (:func:`examples`).

Regression diagnostics, per model: the residual distribution with its skewness and excess
kurtosis, normal quantile-quantile points of the standardised residuals, residuals by ten
equal-count bins of the prediction, a heteroscedasticity indicator (the rank correlation of
the absolute residual with the prediction, and the ratio of the residual spread in the top
and bottom thirds of the predictions), residuals by feature (numeric features in quantile
bins, categorical ones by value), at most :data:`SCATTER_POINTS` points of predicted against
observed values, and the five largest errors. Normality is a post-fit question about the
residuals, not an EDA check (Lumley et al. 2002); with this many rows the coefficients and
the mean error do not need it, prediction intervals would. The engine has no target
transform, so no retransformation (Duan's smearing) applies; the values say so.

Development diagnostics of the candidate and the variant add the coefficients of the model
fitted on the rows its coefficients come from (every development row under
cross-validation), with percentile bootstrap intervals over :data:`COEFFICIENT_REPLICATES`
refits of the model on resampled rows (the preparation kept as fitted). The scale is that of the
fit: per standard deviation of a numeric feature, per category of a one-hot encoded one;
associations, never effects.

numpy and pandas are imported lazily by the functions that need them.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

DIAG_BINARY = 'diag.binary'
DIAG_REGRESSION = 'diag.regression'
DIAG_FINAL = 'diag.final_test'
DEVELOPMENT_PURPOSE = 'development_diagnostics'
FINAL_PURPOSE = 'final_evaluation'
# The rule of the binary diagnostics when no rule is adopted or proposed and the case
# declares no teaching share.
DEFAULT_RULE = 'share:0.1'
RULE_SOURCES = ('adopted', 'proposed', 'scenario_default', 'engine_default')
CURVE_SHARES = tuple(round(0.05 * i, 2) for i in range(1, 21))
CALIBRATION_BINS = 10
MAX_SEGMENT_COLUMNS = 2
SEGMENT_TYPES = ('category', 'binary', 'ordinal')
MAX_SEGMENT_VALUES = 12
SMALL_CELL_ROWS = 30
SMALL_CELL_SELECTED = 10
MAX_EXAMPLES = 5
COEFFICIENT_REPLICATES = 100
COEFFICIENT_SEED = 20261019
COEFFICIENT_LEVEL = 0.95
RESIDUAL_BINS = 10
FEATURE_BINS = 5
MAX_RESIDUAL_FEATURES = 8
SCATTER_POINTS = 150
QQ_PROBABILITIES = (0.01, 0.025, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55,
                    0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 0.975, 0.99)
# A rank correlation of the absolute residual with the prediction at least this large, or a
# spread ratio outside [1 / SPREAD_RATIO, SPREAD_RATIO], is flagged as heteroscedastic.
HETERO_CORRELATION = 0.2
SPREAD_RATIO = 1.5
MISSING = '(missing)'
OTHER = '(other values)'

# The value shapes (CLI-CONTRACT.md §13, frozen by test_contract_freeze.py).
BINARY_KEYS = ('question', 'evidence', 'purpose', 'partition', 'evaluation', 'n', 'n_positive',
               'base_rate', 'rule', 'rule_source', 'segment_columns', 'segment_rule', 'models',
               'coefficient_rows', 'note',
               # v0.3 (WP-F1): the checks of the candidate linear model.
               'linear_checks')
REGRESSION_KEYS = ('question', 'evidence', 'purpose', 'partition', 'evaluation', 'n', 'target',
                   'unit', 'residual_columns', 'residual_definition', 'target_transform',
                   'smearing', 'normality_note', 'models', 'coefficient_rows', 'note',
                   # v0.3 (WP-F1): the checks of the candidate linear model.
                   'linear_checks')
FINAL_BINARY_KEYS = ('question', 'evidence', 'purpose', 'partition', 'evaluation', 'n',
                     'model', 'final_evaluation', 'n_positive', 'base_rate', 'rule',
                     'segment_columns', 'segment_rule', 'models', 'note')
FINAL_REGRESSION_KEYS = ('question', 'evidence', 'purpose', 'partition', 'evaluation', 'n',
                         'model', 'final_evaluation', 'target', 'unit', 'residual_columns',
                         'residual_definition', 'target_transform', 'smearing',
                         'normality_note', 'models', 'note')
# One model's diagnostics; ``coefficients`` in the development diagnostics only.
BINARY_MODEL_KEYS = ('confusion', 'curve', 'roc_auc', 'average_precision', 'calibration',
                     'segments', 'examples', 'coefficients', 'predictions')
REGRESSION_MODEL_KEYS = ('errors', 'residuals', 'qq', 'by_prediction', 'heteroscedasticity',
                         'by_feature', 'scatter', 'examples', 'coefficients', 'predictions')
EVIDENCE = ('development', 'final')

QUESTIONS = {
    DIAG_BINARY: 'Where does the model err at the rule, and can its score be read as a '
                 'probability?',
    DIAG_REGRESSION: 'Where are the predictions off, by how much, and does the error grow '
                     'with the prediction or differ across groups?',
    'final_binary': 'On rows nothing had seen, where does the chosen model err at the rule, '
                    'and do its scores match the observed rates?',
    'final_regression': 'On rows nothing had seen, where are the chosen model\'s predictions '
                        'off, and does the error grow with the prediction?',
}
DEVELOPMENT_NOTE = ('Development evidence: computed on the out-of-fold predictions of the '
                    'development rows, on which the model and the rule were chosen. These '
                    'figures describe the choice; only the final test is independent evidence.')
VALIDATION_NOTE = ('Development evidence: computed on the validation predictions, on which the '
                   'model and the rule were chosen. These figures describe the choice; they '
                   'are not independent evidence.')
FINAL_NOTE = ('Final evidence: computed once the final test was opened, from the predictions '
              'of its one evaluation, on rows no choice had seen.')
SMEARING_NOTE = ('The model predicts the target on its own scale (no transform of the target), '
                 'so no retransformation correction such as Duan\'s smearing applies. Smearing '
                 'is not implemented: a log-transformed target would need it.')
NORMALITY_NOTE = ('The quantile-quantile points compare the standardised residuals with a '
                  'normal distribution. Normality is not needed for the mean error or the '
                  'coefficients with this many rows (Lumley et al. 2002); it matters for '
                  'prediction intervals, which this study does not give.')
# A stored coefficient further than this from the refit on the same prepared rows (the
# replicates' solver, every row) is flagged: its interval would not describe it.
POINT_TOLERANCE = 1e-4
POINT_CONSISTENT_NOTE = ('The coefficients and their intervals come from the same prepared rows '
                         'and the same penalised fit.')
POINT_INCONSISTENT_NOTE = ('The stored coefficients differ from a refit of the same model on the '
                           'same prepared rows (a fit recorded by an earlier engine version '
                           'stopped before its optimum): '
                           'the intervals describe the refit, not these values. Run the fit '
                           'again to align them.')
COEFFICIENT_NOTE = ('Coefficients of the model fitted on these rows, with percentile bootstrap '
                    'intervals: the model refitted on rows drawn with replacement, the '
                    'preparation of the variables kept as fitted. Associations given the other '
                    'variables, never effects.')


# --- small helpers -------------------------------------------------------------------------

def _f(value) -> float | None:
    """A finite float, or None."""
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def wilson(successes: float, n: float, z: float = 1.959963984540054) -> dict | None:
    """Wilson score interval of ``successes / n`` (fractional counts accepted), or None."""
    if not n or n <= 0:
        return None
    p = successes / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(max(0.0, p * (1 - p) / n + z * z / (4 * n * n))) / denominator
    # At p = 0 or p = 1 the bound is exactly 0 or 1 (rounding would leave it a hair off).
    low = 0.0 if successes <= 0 else max(0.0, min(p, centre - half))
    high = 1.0 if successes >= n else min(1.0, max(p, centre + half))
    return {'low': low, 'high': high}


def cell_text(value) -> str | None:
    """A cell as text (None for a missing cell): integers without a decimal point."""
    if value is None:
        return None
    try:
        if value != value:          # NaN
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def segment_columns(case, features) -> list[str]:
    """At most :data:`MAX_SEGMENT_COLUMNS` categorical features the model uses, in case
    order (the engine's choice: the case declares no segment)."""
    used = set(features)
    out = [v['name'] for v in case.document['variables']
           if v['role'] == 'feature' and v['name'] in used and v.get('type') in SEGMENT_TYPES]
    return out[:MAX_SEGMENT_COLUMNS]


SEGMENT_RULE = ('The first two categorical features the model uses, in the order of the case; '
                f'at most {MAX_SEGMENT_VALUES} values each, the rarer ones folded into '
                f'"{OTHER}".')


def _labels(series) -> list[str]:
    return [MISSING if (t := cell_text(v)) is None else t for v in series.tolist()]


def _fold(labels: list[str]) -> list[str]:
    """Keep the :data:`MAX_SEGMENT_VALUES` - 1 largest values when there are more."""
    from collections import Counter
    counts = Counter(labels)
    if len(counts) <= MAX_SEGMENT_VALUES:
        return labels
    kept = {v for v, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
            [:MAX_SEGMENT_VALUES - 1]}
    return [v if v in kept else OTHER for v in labels]


def _order(labels: list[str]) -> list[str]:
    distinct = sorted(set(labels) - {MISSING, OTHER})
    return distinct + [x for x in (OTHER, MISSING) if x in set(labels)]


# --- binary ---------------------------------------------------------------------------------

def selection_weights(score, rule, groups=None):
    """Selection weights (1, 0, or a fraction for a tie group split by a capacity cut);
    with ``groups`` (B6c, H3), within each fold of out-of-fold scores."""
    from . import policy
    return policy.weights(score, rule, groups)[0]


def confusion(y, score, rule, groups=None) -> dict:
    """The confusion matrix of ``rule`` on ``(y, score)`` (expected counts at a split tie);
    with ``groups`` (B6c, H3), a capacity or a share is applied within each fold, as the
    policy evaluation applies it."""
    from . import policy
    ev = policy.evaluate(y, score, rule, groups)
    n = ev['n']
    negatives = n - ev['n_positive']
    tn = negatives - ev['false_positives']
    out = {'rule': rule, 'n': n, 'n_positive': ev['n_positive'], 'n_negative': negatives,
           'selected': ev['selected'], 'true_positives': ev['true_positives'],
           'false_positives': ev['false_positives'],
           'false_negatives': ev['false_negatives'], 'true_negatives': tn,
           'precision': ev['precision'], 'recall': ev['recall'],
           'specificity': tn / negatives if negatives else None,
           'selection': ev['selection'], 'tied_at_cut': ev['tied_at_cut']}
    if ev.get('capacity') is not None:
        out['capacity'] = ev['capacity']
    if ev.get('selection_scope'):
        out['selection_scope'] = ev['selection_scope']
    return out


def curve(y, score, shares=CURVE_SHARES, groups=None) -> dict:
    """Gain, lift, ROC and precision-recall points at the top ``shares`` of the scored rows
    (ties at a cut counted pro rata, as a capacity); with ``groups`` (B6c, H3), the top
    share of each fold. The AUC and the average precision pool the rows."""
    import numpy as np
    from . import metrics, policy
    y = np.asarray(y, dtype=float)
    s = np.asarray(score, dtype=float)
    n = len(y)
    positives = float(y.sum())
    negatives = n - positives
    base = positives / n if n else None
    points = []
    folds = policy.fold_index(groups) if groups is not None else None
    for p in shares:
        if folds is None:
            k = policy.share_capacity(p, n)
            selected, tp = policy._capacity_counts(y, s, k) if n else (0.0, 0.0)
        else:
            rows = policy._fold_rows(y, s, f'share:{p:g}', folds)
            k = int(sum(r['capacity'] for r in rows))
            selected = float(sum(r['selected'] for r in rows))
            tp = float(sum(r['true_positives'] for r in rows))
        fp = selected - tp
        precision = tp / selected if selected > 0 else None
        points.append({'share': float(p), 'capacity': k, 'selected': selected,
                       'true_positives': tp, 'false_positives': fp,
                       'recall': tp / positives if positives > 0 else None,
                       'false_positive_rate': fp / negatives if negatives > 0 else None,
                       'precision': precision,
                       'lift': precision / base if precision is not None and base else None})
    return {'n': n, 'n_positive': int(positives), 'base_rate': base, 'points': points,
            'roc_auc': metrics.roc_auc(y, s), 'average_precision': metrics.average_precision(y, s),
            'definition': 'For the top share of the rows by score: recall is the share of the '
                          'positive rows found (the cumulative gain, and the true positive rate '
                          'of the ROC curve); lift is the precision over the base rate; the '
                          'false positive rate is the share of the negative rows selected.'}


def calibration_bins(score, n_bins: int = CALIBRATION_BINS):
    """The calibration bin (0 to ``n_bins`` - 1) of each row: equal-count bins in score
    order (a stable sort, so ties keep the row order)."""
    import numpy as np
    s = np.asarray(score, dtype=float)
    n = len(s)
    order = np.argsort(s, kind='stable')
    bins = np.empty(n, dtype=int)
    bins[order] = (np.arange(n) * n_bins) // max(n, 1)
    return bins


def calibration(y, score, n_bins: int = CALIBRATION_BINS) -> dict:
    """Mean score against the observed positive rate in equal-count bins, with Wilson
    intervals; the Brier score of the scores and of the constant base rate."""
    import numpy as np
    y = np.asarray(y, dtype=float)
    s = np.asarray(score, dtype=float)
    n = len(y)
    bins = calibration_bins(s, n_bins)
    out = []
    gaps = []
    for b in range(n_bins):
        mask = bins == b
        m = int(mask.sum())
        if not m:
            continue
        pos = float(y[mask].sum())
        rate = pos / m
        interval = wilson(pos, m) or {}
        mean_score = float(s[mask].mean())
        gaps.append((m, abs(mean_score - rate)))
        out.append({'bin': b + 1, 'n': m, 'n_positive': int(pos),
                    'score_min': float(s[mask].min()), 'score_max': float(s[mask].max()),
                    'mean_predicted': mean_score, 'observed_rate': rate,
                    'low': interval.get('low'), 'high': interval.get('high'),
                    'inside_interval': bool(interval.get('low', 0) <= mean_score
                                            <= interval.get('high', 1))})
    base = float(y.mean()) if n else None
    return {'binning': f'{n_bins} equal-count bins of the score, in score order',
            'bins': out, 'brier': float(np.mean((s - y) ** 2)) if n else None,
            'brier_base_rate': float(np.mean((base - y) ** 2)) if n else None,
            'mean_absolute_gap': (sum(m * g for m, g in gaps) / n) if n else None,
            'bins_outside_interval': sum(1 for b in out if not b['inside_interval']),
            'definition': 'The Brier score is the mean squared difference between the score and '
                          'the outcome (0 or 1); the constant base rate gives the reference. A '
                          'bin whose mean score lies outside the interval of its observed rate '
                          'is miscalibrated.'}


def segments(frame, y, w, columns) -> list[dict]:
    """Precision and recall at the rule (selection weights ``w``) by value of each column."""
    import numpy as np
    y = np.asarray(y, dtype=float)
    w = np.asarray(w, dtype=float)
    out = []
    for column in columns:
        labels = np.asarray(_fold(_labels(frame[column])), dtype=object)
        groups = []
        for value in _order(list(labels)):
            mask = labels == value
            n = int(mask.sum())
            pos = float(y[mask].sum())
            selected = float(w[mask].sum())
            tp = float((w[mask] * y[mask]).sum())
            precision = wilson(tp, selected) if selected > 0 else None
            recall = wilson(tp, pos) if pos > 0 else None
            small = n < SMALL_CELL_ROWS or selected < SMALL_CELL_SELECTED
            groups.append({'value': value, 'n': n, 'n_positive': int(pos), 'selected': selected,
                           'true_positives': tp,
                           'precision': tp / selected if selected > 0 else None,
                           'precision_low': (precision or {}).get('low'),
                           'precision_high': (precision or {}).get('high'),
                           'recall': tp / pos if pos > 0 else None,
                           'recall_low': (recall or {}).get('low'),
                           'recall_high': (recall or {}).get('high'),
                           'small_cell': small})
        out.append({'column': column, 'groups': groups,
                    'small_cell_rule': f'fewer than {SMALL_CELL_ROWS} rows or fewer than '
                                       f'{SMALL_CELL_SELECTED} selected rows'})
    return out


def _values(frame, key, features) -> dict:
    row = frame.loc[key]
    return {f: cell_text(row[f]) for f in features}


def examples(frame, keys, y, score, w, features, limit: int = MAX_EXAMPLES) -> dict:
    """Up to ``limit`` false positives (wholly selected negatives, highest scores first) and
    false negatives (unselected positives, lowest scores first), with their feature values."""
    import numpy as np
    y = np.asarray(y, dtype=float)
    s = np.asarray(score, dtype=float)
    w = np.asarray(w, dtype=float)
    keys = list(keys)
    fp = [i for i in np.argsort(-s, kind='stable') if w[i] == 1 and y[i] == 0][:limit]
    fn = [i for i in np.argsort(s, kind='stable') if w[i] == 0 and y[i] == 1][:limit]

    def item(i):
        return {'row_key': keys[i], 'score': float(s[i]),
                'values': _values(frame, keys[i], features)}
    return {'false_positives': [item(i) for i in fp], 'false_negatives': [item(i) for i in fn],
            'features': list(features),
            'note': 'Rows whose selection at the rule disagrees with the outcome, with the '
                    'feature values as written in the file. Examples to read, not a sample.'}


def binary_model(y, score, rule, frame, keys, segment_cols, features, groups=None) -> dict:
    """Every binary diagnostic of one model's predictions at ``rule`` (``groups``: the fold
    of each out-of-fold row, B6c H3)."""
    w = selection_weights(score, rule, groups)
    c = curve(y, score, groups=groups)
    return {'confusion': confusion(y, score, rule, groups),
            'curve': {k: v for k, v in c.items() if k not in ('roc_auc', 'average_precision')},
            'roc_auc': c['roc_auc'], 'average_precision': c['average_precision'],
            'calibration': calibration(y, score),
            'segments': segments(frame, y, w, segment_cols),
            'examples': examples(frame, keys, y, score, w, features)}


# --- regression -----------------------------------------------------------------------------

def _moments(r) -> dict:
    import numpy as np
    n = len(r)
    if n < 3:
        return {'skewness': None, 'excess_kurtosis': None}
    m = r.mean()
    sd = r.std(ddof=0)
    if sd == 0:
        return {'skewness': None, 'excess_kurtosis': None}
    z = (r - m) / sd
    return {'skewness': float(np.mean(z ** 3)), 'excess_kurtosis': float(np.mean(z ** 4) - 3)}


def qq_points(residual) -> dict:
    """Sample quantiles of the standardised residuals against normal quantiles."""
    import numpy as np
    from scipy import stats
    r = np.asarray(residual, dtype=float)
    sd = float(r.std(ddof=1)) if len(r) > 1 else 0.0
    z = (r - r.mean()) / sd if sd > 0 else r * 0
    points = [{'probability': p, 'theoretical': float(stats.norm.ppf(p)),
               'sample': float(np.quantile(z, p))} for p in QQ_PROBABILITIES]
    return {'points': points,
            'definition': 'Quantiles of the residuals standardised by their mean and standard '
                          'deviation, against the same quantiles of a normal distribution: on a '
                          'straight diagonal line when the residuals are normal.'}


def by_prediction(y, prediction, n_bins: int = RESIDUAL_BINS) -> dict:
    """Residuals by equal-count bins of the prediction."""
    import numpy as np
    y = np.asarray(y, dtype=float)
    p = np.asarray(prediction, dtype=float)
    r = y - p
    bins = calibration_bins(p, n_bins)
    out = []
    for b in range(n_bins):
        mask = bins == b
        m = int(mask.sum())
        if not m:
            continue
        out.append({'bin': b + 1, 'n': m, 'prediction_min': float(p[mask].min()),
                    'prediction_max': float(p[mask].max()),
                    'mean_prediction': float(p[mask].mean()),
                    'mean_observed': float(y[mask].mean()),
                    'mean_residual': float(r[mask].mean()),
                    'sd_residual': float(r[mask].std(ddof=1)) if m > 1 else None,
                    'mae': float(np.abs(r[mask]).mean())})
    return {'binning': f'{n_bins} equal-count bins of the prediction, in prediction order',
            'bins': out}


def heteroscedasticity(y, prediction) -> dict:
    """Does the size of the error grow (or shrink) with the prediction?"""
    import numpy as np
    from scipy import stats
    y = np.asarray(y, dtype=float)
    p = np.asarray(prediction, dtype=float)
    a = np.abs(y - p)
    corr = None
    if len(a) > 2 and np.ptp(p) > 0 and np.ptp(a) > 0:
        corr = float(stats.spearmanr(p, a).statistic)
    order = np.argsort(p, kind='stable')
    third = len(p) // 3
    ratio = None
    if third >= 2:
        low = (y - p)[order[:third]].std(ddof=1)
        high = (y - p)[order[-third:]].std(ddof=1)
        ratio = float(high / low) if low > 0 else None
    flag = bool((corr is not None and abs(corr) >= HETERO_CORRELATION)
                or (ratio is not None and (ratio >= SPREAD_RATIO or ratio <= 1 / SPREAD_RATIO)))
    return {'abs_residual_prediction_correlation': corr, 'spread_ratio_top_bottom': ratio,
            'flag': flag,
            'rule': f'Flagged when the rank correlation of the absolute residual with the '
                    f'prediction is at least {HETERO_CORRELATION} in size, or the residual '
                    f'standard deviation of the top third of the predictions is more than '
                    f'{SPREAD_RATIO} times (or less than 1/{SPREAD_RATIO} of) that of the '
                    f'bottom third',
            'meaning': 'An error that grows with the prediction makes one interval width wrong '
                       'for every row; the mean error stays a fair summary.'}


def by_feature(frame, y, prediction, columns, case) -> list[dict]:
    """Mean residual and MAE by value (categorical) or quantile bin (numeric) of each
    column."""
    import numpy as np
    import pandas as pd
    from pandas.api.types import is_numeric_dtype
    y = np.asarray(y, dtype=float)
    r = y - np.asarray(prediction, dtype=float)
    out = []
    for column in columns:
        series = frame[column]
        numeric = case.variables[column].get('type') in ('numeric', 'integer') \
            and is_numeric_dtype(series)
        binned = numeric and series.nunique(dropna=True) > FEATURE_BINS
        if binned:
            cut = pd.qcut(series, FEATURE_BINS, duplicates='drop')
            labels = [MISSING if v != v else str(v) for v in cut.astype(object).tolist()]
            order = [str(c) for c in cut.cat.categories] + ([MISSING] if MISSING in labels else [])
        else:
            labels = _fold(_labels(series))
            order = _order(labels)
            if numeric:
                order = sorted((v for v in order if v not in (MISSING, OTHER)), key=float) + \
                    [v for v in (OTHER, MISSING) if v in set(labels)]
        labels = np.asarray(labels, dtype=object)
        groups = []
        for value in order:
            mask = labels == value
            n = int(mask.sum())
            if not n:
                continue
            groups.append({'value': value, 'n': n, 'mean_residual': float(r[mask].mean()),
                           'mae': float(np.abs(r[mask]).mean()), 'small_cell': n < SMALL_CELL_ROWS})
        out.append({'column': column, 'binned': bool(binned),
                    'binning': f'{FEATURE_BINS} quantile bins of the rows shown' if binned else None,
                    'groups': groups})
    return out


def residual_columns(case, features) -> list[str]:
    """The features residuals are broken down by: the categorical segment columns, then the
    numeric features the model uses, in case order (at most :data:`MAX_RESIDUAL_FEATURES`)."""
    used = set(features)
    cats = segment_columns(case, features)
    nums = [v['name'] for v in case.document['variables']
            if v['role'] == 'feature' and v['name'] in used
            and v.get('type') in ('numeric', 'integer')]
    return (cats + nums)[:MAX_RESIDUAL_FEATURES]


def scatter(keys, y, prediction, cap: int = SCATTER_POINTS) -> dict:
    """At most ``cap`` points (prediction, observed, residual), evenly spaced in prediction
    order so the whole range is shown."""
    import numpy as np
    y = np.asarray(y, dtype=float)
    p = np.asarray(prediction, dtype=float)
    n = len(p)
    order = np.argsort(p, kind='stable')
    if n > cap:
        picks = order[np.unique(np.linspace(0, n - 1, cap).round().astype(int))]
    else:
        picks = order
    return {'n_rows': n, 'n_shown': int(len(picks)),
            'sampling': (f'every row' if n <= cap else
                         f'{cap} rows evenly spaced in prediction order'),
            'points': [{'row_key': keys[i], 'prediction': float(p[i]), 'observed': float(y[i]),
                        'residual': float(y[i] - p[i])} for i in picks]}


def largest_errors(frame, keys, y, prediction, features, limit: int = MAX_EXAMPLES) -> list:
    import numpy as np
    y = np.asarray(y, dtype=float)
    p = np.asarray(prediction, dtype=float)
    r = y - p
    keys = list(keys)
    order = np.argsort(-np.abs(r), kind='stable')[:limit]
    return [{'row_key': keys[i], 'observed': float(y[i]), 'prediction': float(p[i]),
             'residual': float(r[i]), 'values': _values(frame, keys[i], features)}
            for i in order]


def regression_model(y, prediction, frame, keys, case, features) -> dict:
    """Every regression diagnostic of one model's predictions."""
    import numpy as np
    from . import regression
    y = np.asarray(y, dtype=float)
    p = np.asarray(prediction, dtype=float)
    summary = regression.residual_summary(y, p)
    summary.update(_moments(y - p))
    return {'errors': regression.errors(y, p), 'residuals': summary, 'qq': qq_points(y - p),
            'by_prediction': by_prediction(y, p),
            'heteroscedasticity': heteroscedasticity(y, p),
            'by_feature': by_feature(frame, y, p, residual_columns(case, features), case),
            'scatter': scatter(list(keys), y, p),
            'examples': {'largest_errors': largest_errors(frame, keys, y, p, features),
                         'features': list(features),
                         'note': 'The rows with the largest absolute residuals, with the feature '
                                 'values as written in the file.'}}


# --- coefficients ---------------------------------------------------------------------------

def coefficient_intervals(case, frame, inputs: Mapping, params: Mapping, binary: bool,
                          point: Mapping[str, float], *, replicates: int = COEFFICIENT_REPLICATES,
                          seed: int = COEFFICIENT_SEED, level: float = COEFFICIENT_LEVEL) -> dict:
    """Percentile bootstrap intervals of the coefficients ``point`` (the fit's, on the rows
    of ``frame``). The variables are prepared once, as the fit prepared them on these rows
    (special-value indicators, the confirmed preprocessing, imputation, scaling, one-hot
    encoding); the model alone is refitted ``replicates`` times on prepared rows drawn with
    replacement. The intervals are therefore conditional on that preparation."""
    import numpy as np
    from sklearn.base import clone
    from . import fit
    from .activities import positive
    features, special = list(inputs['features']), list(inputs['special_values'])
    X, _ = fit.design(frame, features, special, case)
    X, _, _ = fit.prepare(case, frame, frame, X, X.copy(), features, inputs.get('preprocessing'),
                          special)
    model = fit._fit_predict(case, frame, frame.iloc[:1], inputs, params, binary)[1]
    Z = np.asarray(model['preprocess'].transform(X), dtype=float)
    names = [str(x) for x in model['preprocess'].get_feature_names_out()]
    y = positive(frame, case).to_numpy() if binary else fit._target(case, frame, 'development')
    stored = model['model'].coef_[0] if binary else model['model'].coef_
    # The point and the replicates must solve the same problem on the same design: the
    # refit of the fit's model on every row of Z, with the replicates' solver, is the
    # reference the stored point is compared with (WP-B6a).
    reference = clone(model['model'])
    if binary:
        reference.set_params(warm_start=True, solver='newton-cholesky')
        reference.coef_ = model['model'].coef_.copy()
        reference.intercept_ = model['model'].intercept_.copy()
    reference.fit(Z, y)
    ref = reference.coef_[0] if binary else reference.coef_
    drift = {term: abs(float(point[term]) - float(r)) for term, r in zip(names, ref)
             if term in point}
    misaligned = sorted(term for term, s_ in zip(names, stored)
                        if term in point and abs(float(point[term]) - float(s_)) > 1e-9)
    rng = np.random.default_rng(seed)
    n = len(frame)
    samples = []
    skipped = 0
    for _ in range(replicates):
        idx = rng.integers(0, n, n)
        if binary and y[idx].min() == y[idx].max():
            skipped += 1
            continue
        est = clone(model['model'])
        if binary:
            # Start from the fitted coefficients: the same optimum, reached in fewer steps.
            # Newton-Cholesky solves the same penalised likelihood as the fit's solver, in a
            # few steps when there are few prepared variables.
            est.set_params(warm_start=True, solver='newton-cholesky')
            est.coef_ = model['model'].coef_.copy()
            est.intercept_ = model['model'].intercept_.copy()
        est.fit(Z[idx], y[idx])
        samples.append(est.coef_[0] if binary else est.coef_)
    draws = np.asarray(samples, dtype=float).reshape(len(samples), len(names))
    alpha = (1 - level) / 2
    terms = []
    for j, term in enumerate(names):
        if term not in point:
            continue
        s = draws[:, j]
        low = float(np.quantile(s, alpha)) if len(s) >= 2 else None
        high = float(np.quantile(s, 1 - alpha)) if len(s) >= 2 else None
        value = float(point[term])
        terms.append({'term': term, 'value': value, 'low': low, 'high': high,
                      'excludes_zero': bool(low is not None and (low > 0 or high < 0)),
                      'inside_interval': None if low is None else bool(low <= value <= high)})
    terms.sort(key=lambda t: (-abs(t['value']), t['term']))
    largest = max(drift.values(), default=0.0)
    consistent = not misaligned and largest <= POINT_TOLERANCE
    return {'terms': terms, 'n_rows': n, 'replicates': replicates - skipped, 'seed': seed,
            'level': level, 'skipped_replicates': skipped,
            'point_check': {'consistent': consistent, 'max_difference': largest,
                            'tolerance': POINT_TOLERANCE, 'misaligned_terms': misaligned,
                            'note': POINT_CONSISTENT_NOTE if consistent
                            else POINT_INCONSISTENT_NOTE},
            'method': 'percentile bootstrap: the model refitted on prepared rows drawn with '
                      'replacement (the preparation kept as fitted on every row)',
            'note': COEFFICIENT_NOTE}


# --- v0.3 (WP-F1): what the linear fit cannot follow ------------------------------------------

CHECK_BINS = 5
CHECK_ALPHA = 0.01
MIN_SEGMENT_ROWS = 100
MIN_SEGMENT_POSITIVES = 10
SLOPE_BAND = (0.8, 1.2)
LINEAR_CHECK_KEYS = ('model', 'nonlinearity', 'interaction', 'calibration_slope', 'flags',
                     'alpha', 'method', 'note')
LINEAR_CHECKS_NOTE = ('Checks of the candidate linear model on its out-of-fold predictions: a '
                      'flag is evidence that another model family might follow the data more '
                      'closely, not proof; choosing a family after seeing it makes that '
                      'comparison data-contingent.')


def _slope(y, x, binary: bool) -> tuple[float | None, float | None]:
    """``(slope, standard error)`` of ``y`` on ``x``: a logistic regression of the outcome on
    the logit of the score (the calibration slope, Cox 1958), or the least-squares slope of
    the target on the prediction."""
    import numpy as np
    y = np.asarray(y, dtype=float)
    x = np.asarray(x, dtype=float)
    n = len(y)
    if n < 3 or np.ptp(x) == 0:
        return None, None
    if not binary:
        xc = x - x.mean()
        sxx = float((xc ** 2).sum())
        b = float((xc * (y - y.mean())).sum() / sxx)
        resid = y - y.mean() - b * xc
        s2 = float((resid ** 2).sum() / max(n - 2, 1))
        return b, float(np.sqrt(s2 / sxx))
    if y.min() == y.max():
        return None, None
    p = np.clip(x, 1e-6, 1 - 1e-6)
    z = np.log(p / (1 - p))
    X = np.column_stack([np.ones(n), z])
    beta = np.zeros(2)
    for _ in range(50):
        mu = 1 / (1 + np.exp(-(X @ beta)))
        w = mu * (1 - mu)
        H = X.T @ (X * w[:, None])
        g = X.T @ (y - mu)
        try:
            step = np.linalg.solve(H, g)
        except np.linalg.LinAlgError:
            return None, None
        beta = beta + step
        if np.max(np.abs(step)) < 1e-10:
            break
    mu = 1 / (1 + np.exp(-(X @ beta)))
    H = X.T @ (X * (mu * (1 - mu))[:, None])
    try:
        cov = np.linalg.inv(H)
    except np.linalg.LinAlgError:
        return float(beta[1]), None
    return float(beta[1]), float(np.sqrt(max(cov[1, 1], 0.0)))


def linear_checks(y, prediction, frame, case, features, binary: bool, model: str) -> dict:
    """v0.3 (WP-F1): three checks of the candidate linear model on its out-of-fold
    predictions, the evidence the shortlist of model families reads
    (:func:`mlkit.study.trials.shortlist`).

    * **non-linearity** of each numeric feature the model uses: the gap between the observed
      outcome rate and the mean score (binary), or the mean residual (regression), in
      :data:`CHECK_BINS` quantile bins of the feature, summed as ``sum((gap / se)^2)`` against
      a chi-square with as many degrees of freedom as bins; flagged below
      :data:`CHECK_ALPHA` divided by the number of features checked (Bonferroni);
    * **interaction** with each categorical segment feature: the calibration slope of the
      score within each value (at least :data:`MIN_SEGMENT_ROWS` rows, and
      :data:`MIN_SEGMENT_POSITIVES` rows of each class for a binary target), heterogeneity
      by Cochran's Q; a score whose effect differs by group is a sign of an interaction;
    * the overall **calibration slope** (Cox 1958): flagged when it lies outside
      :data:`SLOPE_BAND` and its 95 % interval excludes 1.
    """
    import numpy as np
    import pandas as pd
    from scipy.stats import chi2
    from pandas.api.types import is_numeric_dtype
    y = np.asarray(y, dtype=float)
    pred = np.asarray(prediction, dtype=float)
    resid_sd = float(np.std(y - pred, ddof=1)) if (not binary and len(y) > 1) else None
    numeric = [f for f in features if case.variables.get(f, {}).get('type') in
               ('numeric', 'integer') and f in frame and is_numeric_dtype(frame[f])]
    tested = [f for f in numeric if frame[f].nunique(dropna=True) > CHECK_BINS]
    nonlin = []
    for f in tested:
        values = frame[f].to_numpy(dtype=float)
        ok = ~np.isnan(values)
        labels = pd.qcut(pd.Series(values[ok]), CHECK_BINS, duplicates='drop',
                         labels=False).to_numpy()
        yy, pp, vv = y[ok], pred[ok], values[ok]
        bins, stat = [], 0.0
        for b in sorted(set(labels.tolist())):
            mask = labels == b
            n = int(mask.sum())
            if n < 2:
                continue
            gap = float(yy[mask].mean() - pp[mask].mean())
            if binary:
                se = float(np.sqrt(np.clip(pp[mask] * (1 - pp[mask]), 1e-12, None).sum()) / n)
            else:
                se = float((resid_sd or 0.0) / np.sqrt(n))
            stat += (gap / se) ** 2 if se > 0 else 0.0
            bins.append({'bin': int(b) + 1, 'n': n, 'low': float(vv[mask].min()),
                         'high': float(vv[mask].max()), 'gap': gap, 'se': se})
        df = len(bins)
        p_value = float(chi2.sf(stat, df)) if df else None
        threshold = CHECK_ALPHA / max(len(tested), 1)
        nonlin.append({'feature': f, 'bins': bins, 'statistic': float(stat), 'df': df,
                       'p_value': p_value, 'level': threshold,
                       'flagged': bool(p_value is not None and p_value < threshold)})
    interaction = []
    seg_cols = segment_columns(case, features)
    for col in seg_cols:
        labels = np.asarray(_fold(_labels(frame[col])), dtype=object)
        groups = []
        for value in _order(list(labels)):
            mask = labels == value
            n = int(mask.sum())
            positives = float(y[mask].sum()) if binary else None
            if n < MIN_SEGMENT_ROWS or (binary and (positives < MIN_SEGMENT_POSITIVES
                                                    or n - positives < MIN_SEGMENT_POSITIVES)):
                continue
            slope, se = _slope(y[mask], pred[mask], binary)
            if slope is None or not se:
                continue
            groups.append({'value': value, 'n': n, 'slope': slope, 'se': se})
        q = p_value = None
        if len(groups) >= 2:
            w = np.array([1 / g['se'] ** 2 for g in groups])
            s = np.array([g['slope'] for g in groups])
            pooled = float((w * s).sum() / w.sum())
            q = float((w * (s - pooled) ** 2).sum())
            p_value = float(chi2.sf(q, len(groups) - 1))
        threshold = CHECK_ALPHA / max(len(seg_cols), 1)
        interaction.append({'feature': col, 'groups': groups, 'q': q,
                            'df': max(len(groups) - 1, 0), 'p_value': p_value,
                            'level': threshold,
                            'flagged': bool(p_value is not None and p_value < threshold)})
    slope, se = _slope(y, pred, binary)
    z = 1.959963984540054
    low = slope - z * se if slope is not None and se else None
    high = slope + z * se if slope is not None and se else None
    cal = {'slope': slope, 'se': se, 'low': low, 'high': high, 'band': list(SLOPE_BAND),
           'flagged': bool(slope is not None and low is not None
                           and not SLOPE_BAND[0] <= slope <= SLOPE_BAND[1]
                           and not low <= 1 <= high),
           'definition': ('slope of a logistic regression of the outcome on the logit of the '
                          'score: 1 when the scores are as spread as the outcomes, below 1 '
                          'when they are too extreme' if binary else
                          'least-squares slope of the target on the prediction: 1 when the '
                          'predictions are as spread as the target')}
    flags = [{'check': 'nonlinearity', 'feature': x['feature'], 'p_value': x['p_value']}
             for x in nonlin if x['flagged']]
    flags += [{'check': 'interaction', 'feature': x['feature'], 'p_value': x['p_value']}
              for x in interaction if x['flagged']]
    if cal['flagged']:
        flags.append({'check': 'calibration_slope', 'feature': None, 'p_value': None,
                      'slope': slope})
    return {'model': model, 'nonlinearity': nonlin, 'interaction': interaction,
            'calibration_slope': cal, 'flags': flags, 'alpha': CHECK_ALPHA,
            'method': ('binned out-of-fold gaps per numeric feature (chi-square, Bonferroni); '
                       'calibration slope by segment (Cochran\'s Q); overall calibration slope '
                       '(Cox 1958)'),
            'note': LINEAR_CHECKS_NOTE}
