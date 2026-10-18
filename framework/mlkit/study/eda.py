"""Training-partition exploratory analysis (plan WP2.2).

Every function receives **only the training rows** (``activities.rows`` selects them
from the current split) and the case. Nothing here knows a dataset: columns, labels,
and special values come from ``case.yaml``.

* ``eda.target_rate``: rows, positive rows, and the positive rate.
* ``eda.special_values``: for every special value the case declares on a feature
  (sentinels, undocumented categories, missing-value markers), how many training rows
  carry it, the positive rate among them, and how often two special values occur on
  the same rows (co-occurrence). Two markers that always coincide describe one fact
  twice, which matters when both enter a model.
* ``eda.rate_by --column X``: the positive rate by value of ``X`` with its
  denominator. A numeric column with many values is cut into training quantile
  bins; its special values and missing cells keep their own groups. A group with
  fewer than :data:`MIN_GROUP_ROWS` rows is flagged: its rate is too noisy to read
  alone.

A regression study (numeric target with a unit) has its own exploration, with the same
reading rules:

* ``eda.target_summary``: rows, missing values, mean, standard deviation, minimum,
  quartiles, and maximum of the target, in its unit.
* ``eda.special_values``: as above, with the mean target among the rows carrying each
  special value instead of a positive rate.
* ``eda.mean_by --column X``: the mean target by value of ``X`` with its count; the same
  groups as ``eda.rate_by`` and the same small-count warning.

These are associations on training rows, not effects. pandas is imported by the
caller (``activities.compute``), never at module import.
"""
from __future__ import annotations

from typing import Mapping

from . import case as c

MIN_GROUP_ROWS = 30
MAX_DISTINCT_BEFORE_BINNING = 12
QUANTILE_BINS = 5
MISSING_GROUP = '(missing)'


def _rate(n: int, n_positive: int) -> float | None:
    return n_positive / n if n else None


def _matches(series, value, case: c.Case):
    from .activities import matches
    return matches(series, value, case.dataset.get('na_values', ()))


def target_rate(case: c.Case, train) -> dict:
    from .activities import positive
    y = positive(train, case)
    n, n_positive = int(len(y)), int(y.sum())
    return {'partition': 'train', 'target': case.target_column,
            'positive_label': case.positive_label, 'n_rows': n, 'n_positive': n_positive,
            'n_negative': n - n_positive, 'rate': _rate(n, n_positive)}


def numeric_target(case: c.Case, frame):
    """The target of a regression case as floats (missing cells stay missing).

    A value that is not a number is refused (``invalid_case``): the case declares a
    numeric target."""
    import pandas as pd
    from .errors import StudyError
    try:
        return pd.to_numeric(frame[case.target_column], errors='raise').astype(float)
    except (TypeError, ValueError) as exc:
        raise StudyError('invalid_case', f'The target {case.target_column!r} is declared numeric '
                                         f'but holds a value that is not a number: {exc}',
                         details={'column': case.target_column}) from exc


def _moments(values) -> dict:
    """Count, mean, standard deviation, minimum, quartiles, maximum of a float series
    without missing cells (``None`` when empty)."""
    n = int(len(values))
    if not n:
        return {'n': 0, 'mean': None, 'sd': None, 'min': None, 'q25': None, 'median': None,
                'q75': None, 'max': None}
    return {'n': n, 'mean': float(values.mean()),
            'sd': float(values.std(ddof=1)) if n > 1 else None,
            'min': float(values.min()), 'q25': float(values.quantile(0.25)),
            'median': float(values.quantile(0.5)), 'q75': float(values.quantile(0.75)),
            'max': float(values.max())}


def target_summary(case: c.Case, train) -> dict:
    y = numeric_target(case, train)
    present = y[y.notna()]
    return {'partition': 'train', 'target': case.target_column, 'unit': case.target_unit,
            'n_rows': int(len(train)), 'n_missing': int(y.isna().sum()), **_moments(present),
            'note': 'Distribution of the target on training rows, in its unit. The mean is what '
                    'the baseline predicts for every row.'}


def _mean(values) -> float | None:
    return float(values.mean()) if len(values) else None


def special_values(case: c.Case, train) -> dict:
    if case.task == 'regression':
        return _special_values_numeric(case, train)
    from .activities import positive
    y = positive(train, case)
    specials = [s for s in case.document['special_values']
                if case.variables[s['column']]['role'] == 'feature']
    masks, items = [], []
    for s in specials:
        mask = _matches(train[s['column']], s['value'], case)
        masks.append(mask)
        n = int(mask.sum())
        n_positive = int(y[mask].sum())
        items.append({'column': s['column'], 'value': s['value'], 'meaning': s['meaning'],
                      'status': s['status'], 'source': s['source'], 'n_rows': n,
                      'share': n / len(train) if len(train) else None,
                      'n_positive': n_positive, 'rate': _rate(n, n_positive)})
    pairs = []
    for i in range(len(specials)):
        for j in range(i + 1, len(specials)):
            both = int((masks[i] & masks[j]).sum())
            either = int((masks[i] | masks[j]).sum())
            pairs.append({'a': {'column': specials[i]['column'], 'value': specials[i]['value']},
                          'b': {'column': specials[j]['column'], 'value': specials[j]['value']},
                          'n_a': items[i]['n_rows'], 'n_b': items[j]['n_rows'], 'n_both': both,
                          'n_either': either,
                          'same_rows': both == items[i]['n_rows'] == items[j]['n_rows'] and both > 0})
    return {'partition': 'train', 'n_rows': int(len(train)), 'special_values': items,
            'co_occurrence': pairs,
            'note': 'Counts on training rows. Special values that always occur together '
                    'describe one fact twice.'}


def _special_values_numeric(case: c.Case, train) -> dict:
    """Special values of a regression case: counts, shares, and the mean target."""
    y = numeric_target(case, train)
    specials = [s for s in case.document['special_values']
                if case.variables[s['column']]['role'] == 'feature']
    masks, items = [], []
    for s in specials:
        mask = _matches(train[s['column']], s['value'], case)
        masks.append(mask)
        n = int(mask.sum())
        items.append({'column': s['column'], 'value': s['value'], 'meaning': s['meaning'],
                      'status': s['status'], 'source': s['source'], 'n_rows': n,
                      'share': n / len(train) if len(train) else None,
                      'mean_target': _mean(y[mask].dropna())})
    pairs = []
    for i in range(len(specials)):
        for j in range(i + 1, len(specials)):
            both = int((masks[i] & masks[j]).sum())
            either = int((masks[i] | masks[j]).sum())
            pairs.append({'a': {'column': specials[i]['column'], 'value': specials[i]['value']},
                          'b': {'column': specials[j]['column'], 'value': specials[j]['value']},
                          'n_a': items[i]['n_rows'], 'n_b': items[j]['n_rows'], 'n_both': both,
                          'n_either': either,
                          'same_rows': both == items[i]['n_rows'] == items[j]['n_rows'] and both > 0})
    return {'partition': 'train', 'n_rows': int(len(train)), 'target': case.target_column,
            'unit': case.target_unit, 'special_values': items, 'co_occurrence': pairs,
            'note': 'Counts on training rows. A missing-value marker is imputed by the model, '
                    'with an indicator column for a numeric variable.'}


def _bins(values, special_mask):
    """Training quantile bins of the ordinary (non-special, non-missing) values."""
    import pandas as pd
    ordinary = values[~special_mask & values.notna()]
    binned = pd.qcut(ordinary, QUANTILE_BINS, duplicates='drop')
    return binned.astype(str), [str(i) for i in binned.cat.categories]


def _groups(case: c.Case, train, column: str):
    """``(labels, order, binned)``: the group label of every training row for ``column``.

    Special values and missing cells keep their own groups; a numeric column with more
    than :data:`MAX_DISTINCT_BEFORE_BINNING` ordinary values is cut into training quantile
    bins."""
    import pandas as pd
    from pandas.api.types import is_numeric_dtype

    values = train[column]
    specials = [s for s in case.document['special_values'] if s['column'] == column]
    labels = pd.Series(index=train.index, dtype=object)
    order: list[str] = []
    special_mask = pd.Series(False, index=train.index)
    for s in specials:
        mask = _matches(values, s['value'], case) & ~special_mask
        labels[mask] = f'{s["value"]} (special value)'
        special_mask |= mask
        order.append(f'{s["value"]} (special value)')
    missing = values.isna() & ~special_mask
    labels[missing] = MISSING_GROUP
    rest = ~special_mask & ~missing
    distinct = values[rest].nunique()
    binned = is_numeric_dtype(values) and distinct > MAX_DISTINCT_BEFORE_BINNING
    if binned:
        bin_labels, bin_order = _bins(values, special_mask)
        labels[bin_labels.index] = bin_labels
        order = bin_order + order
    else:
        ordinary = sorted(values[rest].unique().tolist(), key=lambda v: (str(type(v)), v))
        labels[rest] = values[rest].astype(str)
        order = [str(v) for v in ordinary] + order
    if missing.any():
        order.append(MISSING_GROUP)
    return labels, order, binned


def rate_by(case: c.Case, train, column: str) -> dict:
    from .activities import positive

    y = positive(train, case)
    labels, order, binned = _groups(case, train, column)
    groups, warnings = [], []
    for label in order:
        mask = labels == label
        n = int(mask.sum())
        if n == 0:
            continue
        n_positive = int(y[mask].sum())
        small = n < MIN_GROUP_ROWS
        groups.append({'value': label, 'n_rows': n, 'n_positive': n_positive,
                       'rate': _rate(n, n_positive), 'small_count': small})
        if small:
            warnings.append(f'{column} = {label}: only {n} training rows; its rate is too noisy '
                            f'to read on its own.')
    overall = target_rate(case, train)
    return {'partition': 'train', 'column': column, 'n_rows': int(len(train)),
            'overall_rate': overall['rate'], 'binned': bool(binned),
            'binning': (f'{QUANTILE_BINS} training quantile bins' if binned else None),
            'groups': groups, 'min_group_rows': MIN_GROUP_ROWS, 'warnings': warnings,
            'note': 'Rates by group on training rows are associations, not effects of the '
                    'variable.'}


def mean_by(case: c.Case, train, column: str) -> dict:
    """The mean target by group of ``column`` on training rows, with counts."""
    y = numeric_target(case, train)
    labels, order, binned = _groups(case, train, column)
    groups, warnings = [], []
    for label in order:
        mask = labels == label
        n = int(mask.sum())
        if n == 0:
            continue
        present = y[mask].dropna()
        small = n < MIN_GROUP_ROWS
        groups.append({'value': label, 'n_rows': n, 'mean': _mean(present),
                       'sd': float(present.std(ddof=1)) if len(present) > 1 else None,
                       'small_count': small})
        if small:
            warnings.append(f'{column} = {label}: only {n} training rows; its mean is too noisy '
                            f'to read on its own.')
    return {'partition': 'train', 'column': column, 'target': case.target_column,
            'unit': case.target_unit, 'n_rows': int(len(train)),
            'overall_mean': _mean(y.dropna()), 'binned': bool(binned),
            'binning': (f'{QUANTILE_BINS} training quantile bins' if binned else None),
            'groups': groups, 'min_group_rows': MIN_GROUP_ROWS, 'warnings': warnings,
            'note': 'Mean target by group on training rows: associations, not effects of the '
                    'variable.'}


def compute(activity: str, case: c.Case, train, params: Mapping) -> dict:
    if activity == 'eda.target_rate':
        values = target_rate(case, train)
    elif activity == 'eda.special_values':
        values = special_values(case, train)
    elif activity == 'eda.target_summary':
        values = target_summary(case, train)
    elif activity == 'eda.mean_by':
        values = mean_by(case, train, params['column'])
    else:
        values = rate_by(case, train, params['column'])

    return {'values': values, 'blobs': {}, 'partition': 'train', 'n_rows': int(len(train))}
