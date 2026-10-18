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
  alone. A column with more than ``max_groups`` ordinary values (default
  :data:`MAX_GROUPS`, ``--max-groups N``; G.12) shows its largest groups by count and folds
  the others into one group, :data:`OTHER_GROUP`, with its count of values and rows.

A regression study (numeric target with a unit) has its own exploration, with the same
reading rules:

* ``eda.target_summary``: rows, missing values, mean, standard deviation, minimum,
  quartiles, and maximum of the target, in its unit.
* ``eda.special_values``: as above, with the mean target among the rows carrying each
  special value instead of a positive rate.
* ``eda.mean_by --column X``: the mean target by value of ``X`` with its count; the same
  groups as ``eda.rate_by`` and the same small-count warning.

Both tasks also describe one column at a time (CLI-CONTRACT-COMPANION §8, C8):

* ``eda.distribution --column X``: the distribution of ``X`` on training rows, without
  the outcome (the caller passes the column ``X`` only). A numeric column with more than
  :data:`MAX_DISTINCT_BEFORE_BINNING` ordinary values gets its quantiles and
  :data:`DISTRIBUTION_BINS` fixed-width bins; any other column is counted by group
  (``discrete`` in value order, ``categorical`` by descending count), with the G.12 fold
  of the smallest groups. Special values and missing cells are counted apart.

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
# G.12 (post-v0.1): a high-cardinality column shows its largest groups and "other".
MAX_GROUPS = 20
OTHER_GROUP = '(other values)'
# C8: fixed-width bins of a numeric distribution, and the declared types read as numbers.
DISTRIBUTION_BINS = 10
NUMERIC_TYPES = ('numeric', 'number', 'integer')
DISTRIBUTION_NOTE = ('Counts of training rows only. A distribution describes this sample; it '
                     'is not a rate of the outcome and says nothing about causes.')


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


def _groups(case: c.Case, train, column: str, max_groups: int = MAX_GROUPS):
    """``(labels, order, binned, folded)``: the group label of every training row for
    ``column``.

    Special values and missing cells keep their own groups; a numeric column with more
    than :data:`MAX_DISTINCT_BEFORE_BINNING` ordinary values is cut into training quantile
    bins. When more than ``max_groups`` ordinary values remain, the ``max_groups`` largest
    (by rows, then in value order) keep their groups and the others are labelled
    :data:`OTHER_GROUP`; ``folded`` is ``{n_groups, n_values}`` (the ordinary values before
    folding, and how many were folded), else None."""
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
    folded = None
    if not binned:
        ordinary = sorted(values[rest].unique().tolist(), key=lambda v: (str(type(v)), v))
        labels[rest] = values[rest].astype(str)
        names = [str(v) for v in ordinary]
        if len(names) > max_groups:
            counts = labels[rest].value_counts()
            rank = {name: i for i, name in enumerate(names)}
            kept = set(sorted(names, key=lambda n: (-int(counts.get(n, 0)), rank[n]))[:max_groups])
            labels[rest & ~labels.isin(kept)] = OTHER_GROUP
            folded = {'n_groups': len(names), 'n_values': len(names) - len(kept)}
            names = [n for n in names if n in kept] + [OTHER_GROUP]
        order = names + order
    if missing.any():
        order.append(MISSING_GROUP)
    return labels, order, binned, folded


def _folded(column: str, folded: dict | None, max_groups: int, groups: list) -> tuple:
    """The ``other`` summary and its warning for a folded column (G.12)."""
    if folded is None:
        return None, None
    other = next((g for g in groups if g['value'] == OTHER_GROUP), None)
    summary = {'n_values': folded['n_values'], 'n_rows': other['n_rows'] if other else 0}
    warning = (f'{column} has {folded["n_groups"]} values: the {max_groups} largest groups are '
               f'shown and the other {folded["n_values"]} values are grouped as '
               f'{OTHER_GROUP!r} ({summary["n_rows"]} training rows).')
    return summary, warning


def rate_by(case: c.Case, train, column: str, max_groups: int = MAX_GROUPS) -> dict:
    from .activities import positive

    y = positive(train, case)
    labels, order, binned, folded = _groups(case, train, column, max_groups)
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
    other, warning = _folded(column, folded, max_groups, groups)
    if other is not None:
        g = next(g for g in groups if g['value'] == OTHER_GROUP)
        other.update(n_positive=g['n_positive'], rate=g['rate'])
        warnings.insert(0, warning)
    overall = target_rate(case, train)
    return {'partition': 'train', 'column': column, 'n_rows': int(len(train)),
            'overall_rate': overall['rate'], 'binned': bool(binned),
            'binning': (f'{QUANTILE_BINS} training quantile bins' if binned else None),
            'groups': groups, 'min_group_rows': MIN_GROUP_ROWS, 'warnings': warnings,
            'n_groups': len(groups) + (folded['n_values'] - 1 if folded else 0),
            'max_groups': max_groups, 'other': other,
            'note': 'Rates by group on training rows are associations, not effects of the '
                    'variable.'}


def mean_by(case: c.Case, train, column: str, max_groups: int = MAX_GROUPS) -> dict:
    """The mean target by group of ``column`` on training rows, with counts."""
    y = numeric_target(case, train)
    labels, order, binned, folded = _groups(case, train, column, max_groups)
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
    other, warning = _folded(column, folded, max_groups, groups)
    if other is not None:
        other.update(mean=next(g['mean'] for g in groups if g['value'] == OTHER_GROUP))
        warnings.insert(0, warning)
    return {'partition': 'train', 'column': column, 'target': case.target_column,
            'unit': case.target_unit, 'n_rows': int(len(train)),
            'overall_mean': _mean(y.dropna()), 'binned': bool(binned),
            'binning': (f'{QUANTILE_BINS} training quantile bins' if binned else None),
            'groups': groups, 'min_group_rows': MIN_GROUP_ROWS, 'warnings': warnings,
            'n_groups': len(groups) + (folded['n_values'] - 1 if folded else 0),
            'max_groups': max_groups, 'other': other,
            'note': 'Mean target by group on training rows: associations, not effects of the '
                    'variable.'}


def _plain(value):
    """A cell value as JSON: a whole float as an int, numpy scalars as Python ones."""
    if hasattr(value, 'item'):
        value = value.item()
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _share(n: int, total: int) -> float | None:
    return n / total if total else None


def _numeric_bins(ordinary, n_total: int) -> dict:
    """Quantiles (as :func:`target_summary`) and :data:`DISTRIBUTION_BINS` fixed-width bins
    from the minimum to the maximum; every bin is closed on the left, the last on both
    sides."""
    import numpy as np
    moments = _moments(ordinary)
    out = {k: moments[k] for k in ('n', 'min', 'q25', 'median', 'q75', 'max', 'mean', 'sd')}
    low, high = out['min'], out['max']
    edges = np.linspace(low, high, DISTRIBUTION_BINS + 1)
    index = np.clip(np.searchsorted(edges, ordinary.to_numpy(), side='right') - 1,
                    0, DISTRIBUTION_BINS - 1)
    counts = np.bincount(index, minlength=DISTRIBUTION_BINS)
    bins = [{'low': float(edges[i]), 'high': float(edges[i + 1]), 'n_rows': int(counts[i]),
             'share': _share(int(counts[i]), n_total),
             'closed': 'both' if i == DISTRIBUTION_BINS - 1 else 'left'}
            for i in range(DISTRIBUTION_BINS)]
    return {**out, 'n_bins': DISTRIBUTION_BINS, 'bin_width': (high - low) / DISTRIBUTION_BINS,
            'bins': bins}


def distribution(case: c.Case, train, column: str, max_groups: int = MAX_GROUPS) -> dict:
    """The distribution of ``column`` on training rows (CLI-CONTRACT-COMPANION §8).

    ``train`` may hold ``column`` only: the outcome is never read. Every ``share`` is a
    share of the training rows, so the bins (or groups), the special values, and the
    missing cells add up to one.
    """
    import pandas as pd
    from .errors import StudyError

    variable = case.variables[column]
    values = train[column]
    n_total = int(len(values))
    special_mask = pd.Series(False, index=values.index)
    specials = []
    for s in case.document['special_values']:
        if s['column'] != column:
            continue
        mask = _matches(values, s['value'], case) & ~special_mask
        special_mask |= mask
        n = int(mask.sum())
        specials.append({'value': s['value'], 'meaning': s['meaning'], 'n_rows': n,
                         'share': _share(n, n_total)})
    missing = values.isna() & ~special_mask
    rest = values[~special_mask & ~missing]
    numeric_type = variable.get('type') in NUMERIC_TYPES
    if numeric_type:
        try:
            rest = pd.to_numeric(rest, errors='raise').astype(float)
        except (TypeError, ValueError) as exc:
            raise StudyError('invalid_case', f'{column!r} is declared {variable.get("type")} but '
                                             f'holds a value that is not a number: {exc}',
                             details={'column': column}) from exc
    distinct = int(rest.nunique())
    if numeric_type and distinct > MAX_DISTINCT_BEFORE_BINNING:
        kind = 'numeric'
    elif numeric_type:
        kind = 'discrete'
    else:
        kind = 'categorical'
        rest = rest.astype(str)
    numeric, groups, other, n_groups, warnings = None, None, None, None, []
    if kind == 'numeric':
        numeric = _numeric_bins(rest, n_total)
    else:
        counts = rest.value_counts()
        ordered = sorted(counts.index.tolist(), key=lambda v: (str(type(v)), v))
        rank = {v: i for i, v in enumerate(ordered)}
        by_count = sorted(ordered, key=lambda v: (-int(counts[v]), rank[v]))
        n_groups = len(ordered)
        kept = by_count[:max_groups]
        # Discrete groups in value order; categorical ones by descending count.
        names = [v for v in ordered if v in set(kept)] if kind == 'discrete' else kept
        groups = []
        for v in names:
            n = int(counts[v])
            groups.append({'value': _plain(v), 'n_rows': n, 'share': _share(n, n_total),
                           'small_count': n < MIN_GROUP_ROWS})
        if n_groups > max_groups:      # G.12: the largest groups, the others folded
            folded = by_count[max_groups:]
            n = int(sum(int(counts[v]) for v in folded))
            other = {'n_values': len(folded), 'n_rows': n, 'share': _share(n, n_total)}
            groups.append({'value': OTHER_GROUP, 'n_rows': n, 'share': _share(n, n_total),
                           'small_count': n < MIN_GROUP_ROWS})
            warnings.append(f'{column} has {n_groups} values: the {max_groups} largest groups '
                            f'are shown and the other {len(folded)} values are grouped as '
                            f'{OTHER_GROUP!r} ({n} training rows).')
    return {'partition': 'train', 'column': column, 'role': variable.get('role'),
            'type': variable.get('type'), 'kind': kind, 'n_rows': n_total,
            'n_missing': int(missing.sum()), 'special_values': specials, 'numeric': numeric,
            'groups': groups, 'n_groups': n_groups, 'max_groups': max_groups, 'other': other,
            'min_group_rows': MIN_GROUP_ROWS, 'warnings': warnings, 'note': DISTRIBUTION_NOTE}


def compute(activity: str, case: c.Case, train, params: Mapping) -> dict:
    if activity == 'eda.distribution':
        values = distribution(case, train, params['column'],
                              params.get('max_groups', MAX_GROUPS))
    elif activity == 'eda.target_rate':
        values = target_rate(case, train)
    elif activity == 'eda.special_values':
        values = special_values(case, train)
    elif activity == 'eda.target_summary':
        values = target_summary(case, train)
    elif activity == 'eda.mean_by':
        values = mean_by(case, train, params['column'],
                         params.get('max_groups', MAX_GROUPS))
    else:
        values = rate_by(case, train, params['column'], params.get('max_groups', MAX_GROUPS))

    return {'values': values, 'blobs': {}, 'partition': 'train', 'n_rows': int(len(train))}
