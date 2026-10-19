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

v0.2a (WP-A4, review synthesis §3) adds the EDA governance catalog:

* ``eda.quality``: the structural quality of the **development rows without the target**
  (missing cells and co-missing patterns, repeated rows, cardinality and rare categories,
  ranges against the ranges the case declares);
* intervals and counts on every target-related analysis (Wilson for a rate, a t interval
  for a mean) and a permutation null band per ``eda.rate_by`` / ``eda.mean_by`` chart
  (:data:`NULL_SHUFFLES` shuffles of the target, seed :data:`NULL_SEED`);
* ``eda.single_feature_signal``: each candidate feature alone, out of fold on the training
  rows, raising a legitimacy question only;
* ``question`` on every analysis: the question it answers.

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
            'n_negative': n - n_positive, 'rate': _rate(n, n_positive),
            # v0.2a (WP-A4)
            'interval': wilson(n_positive, n), 'question': question('eda.target_rate')}


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
                    'the baseline predicts for every row.',
            # v0.2a (WP-A4)
            'mean_interval': mean_interval(present), 'question': question('eda.target_summary')}


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
                      'n_positive': n_positive, 'rate': _rate(n, n_positive),
                      'interval': wilson(n_positive, n)})
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
                    'describe one fact twice.',
            'question': question('eda.special_values')}


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
                    'with an indicator column for a numeric variable.',
            'question': question('eda.special_values')}


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
                       'rate': _rate(n, n_positive), 'small_count': small,
                       'interval': wilson(n_positive, n)})
        if small:
            warnings.append(f'{column} = {label}: only {n} training rows; its rate is too noisy '
                            f'to read on its own.')
    other, warning = _folded(column, folded, max_groups, groups)
    if other is not None:
        g = next(g for g in groups if g['value'] == OTHER_GROUP)
        other.update(n_positive=g['n_positive'], rate=g['rate'])
        warnings.insert(0, warning)
    overall = target_rate(case, train)
    out = {'partition': 'train', 'column': column, 'n_rows': int(len(train)),
           'overall_rate': overall['rate'], 'binned': bool(binned),
           'binning': (f'{QUANTILE_BINS} training quantile bins' if binned else None),
           'groups': groups, 'min_group_rows': MIN_GROUP_ROWS, 'warnings': warnings,
           'n_groups': len(groups) + (folded['n_values'] - 1 if folded else 0),
           'max_groups': max_groups, 'other': other,
           'note': 'Rates by group on training rows are associations, not effects of the '
                   'variable.',
           'question': question('eda.rate_by', column)}
    return _with_null_band(out, labels, y.astype(float), lambda v: float(v.mean()), 'null_band')


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
                       'small_count': small, 'interval': mean_interval(present)})
        if small:
            warnings.append(f'{column} = {label}: only {n} training rows; its mean is too noisy '
                            f'to read on its own.')
    other, warning = _folded(column, folded, max_groups, groups)
    if other is not None:
        other.update(mean=next(g['mean'] for g in groups if g['value'] == OTHER_GROUP))
        warnings.insert(0, warning)
    out = {'partition': 'train', 'column': column, 'target': case.target_column,
           'unit': case.target_unit, 'n_rows': int(len(train)),
           'overall_mean': _mean(y.dropna()), 'binned': bool(binned),
           'binning': (f'{QUANTILE_BINS} training quantile bins' if binned else None),
           'groups': groups, 'min_group_rows': MIN_GROUP_ROWS, 'warnings': warnings,
           'n_groups': len(groups) + (folded['n_values'] - 1 if folded else 0),
           'max_groups': max_groups, 'other': other,
           'note': 'Mean target by group on training rows: associations, not effects of the '
                   'variable.',
           'question': question('eda.mean_by', column)}
    return _with_null_band(out, labels, y, lambda v: float(v.mean()), 'null_band')


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
            'min_group_rows': MIN_GROUP_ROWS, 'warnings': warnings, 'note': DISTRIBUTION_NOTE,
            'question': question('eda.distribution', column)}


# --- v0.2a (WP-A4): EDA governance (review synthesis §3) ---------------------------------
#
# Every analysis states the question it answers (``question``). Target-related analyses on
# training rows carry their counts and an interval (Wilson for a rate, a t interval for a
# mean) and, by chart, a permutation null band: the same chart computed after shuffling the
# target among the training rows NULL_SHUFFLES times (fixed seed). A pattern inside the band
# is what chance alone draws. The structural quality overview reads the development rows
# without the target. The single-feature signal only raises a legitimacy question.

Z95 = 1.959963984540054
NULL_SHUFFLES = 19
NULL_SEED = 20261019
# Rare categories in the quality overview: fewer training-scale rows than a readable group.
RARE_CATEGORY_ROWS = MIN_GROUP_ROWS
MAX_MISSING_PATTERNS = 10
SIGNAL_FOLDS = 5
SIGNAL_SEED = 20261019
# A feature whose signal alone reaches these levels, or stands far above the others, raises
# a legitimacy question. Never a selection rule: no feature is kept or dropped by it.
SIGNAL_AUC_LEVEL = 0.75
SIGNAL_AUC_GAP = 0.15
SIGNAL_R2_LEVEL = 0.8
SIGNAL_R2_GAP = 0.4
NULL_BAND_NOTE = (f'The band is the range of the same figure after shuffling the target among '
                  f'the training rows {NULL_SHUFFLES} times (fixed seed): what chance alone '
                  f'draws. A pattern inside it is not distinguishable from chance; one above '
                  f'every shuffle happens by chance about once in {NULL_SHUFFLES + 1} looks.')

QUESTIONS = {
    'eda.target_rate': 'How often is the outcome positive among the training rows?',
    'eda.target_summary': 'How is the target distributed among the training rows?',
    'eda.special_values': 'How many training rows carry each special value, and how does the '
                          'outcome look among them?',
    'eda.quality': 'Are there missing cells, repeated rows, rare categories, or values outside '
                   'their possible range in the development rows?',
    'eda.single_feature_signal': 'Does any single feature, on its own, predict the outcome so '
                                 'well that its availability at the prediction moment should be '
                                 'questioned?',
}


def question(activity: str, column: str | None = None) -> str:
    if activity == 'eda.rate_by':
        return (f'Does the positive rate differ across the groups of {column} by more than '
                f'chance alone draws?')
    if activity == 'eda.mean_by':
        return (f'Does the mean target differ across the groups of {column} by more than '
                f'chance alone draws?')
    if activity == 'eda.distribution':
        return f'How are the values of {column} distributed among the training rows?'
    return QUESTIONS[activity]


def wilson(n_positive: int, n: int, z: float = Z95) -> dict | None:
    """The Wilson score interval of a proportion (95 % by default), or None for n = 0."""
    if not n:
        return None
    p = n_positive / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / denominator
    return {'low': max(0.0, centre - half), 'high': min(1.0, centre + half),
            'level': 0.95, 'method': 'wilson'}


def mean_interval(values) -> dict | None:
    """A 95 % t interval of the mean of a float series without missing cells (None below
    two values)."""
    n = int(len(values))
    if n < 2:
        return None
    from scipy import stats
    mean = float(values.mean())
    half = float(stats.t.ppf(0.975, n - 1)) * float(values.std(ddof=1)) / n ** 0.5
    return {'low': mean - half, 'high': mean + half, 'level': 0.95, 'method': 't'}


def _null_band(labels, order: list, y, statistic) -> dict:
    """Per group and chart-level permutation band: ``statistic(values)`` of each group is
    computed on NULL_SHUFFLES permutations of ``y`` (fixed seed)."""
    import numpy as np
    rng = np.random.default_rng(NULL_SEED)
    values = y.to_numpy(dtype=float)
    masks = {g: (labels == g).to_numpy() for g in order}
    masks = {g: m for g, m in masks.items() if m.any()}
    shuffled = {g: [] for g in masks}
    spreads = []
    for _ in range(NULL_SHUFFLES):
        perm = rng.permutation(values)
        stats_ = {}
        for g, m in masks.items():
            v = perm[m]
            v = v[~np.isnan(v)]
            stats_[g] = statistic(v) if len(v) else None
            shuffled[g].append(stats_[g])
        spreads.append(_spread(stats_, masks))
    groups = {g: {'low': min(s for s in vals if s is not None) if any(
        s is not None for s in vals) else None,
                  'high': max(s for s in vals if s is not None) if any(
        s is not None for s in vals) else None}
              for g, vals in shuffled.items()}
    observed = {}
    for g, m in masks.items():
        v = values[m]
        v = v[~np.isnan(v)]
        observed[g] = statistic(v) if len(v) else None
    observed_spread = _spread(observed, masks)
    finite = [s for s in spreads if s is not None]
    return {'groups': groups,
            'chart': {'statistic': 'spread between the largest and the smallest group value '
                                   f'among groups of at least {MIN_GROUP_ROWS} training rows',
                      'observed': observed_spread,
                      'null_min': min(finite) if finite else None,
                      'null_max': max(finite) if finite else None,
                      'outside': (observed_spread is not None and bool(finite)
                                  and observed_spread > max(finite))},
            'shuffles': NULL_SHUFFLES, 'seed': NULL_SEED, 'note': NULL_BAND_NOTE}


def _spread(stats_: dict, masks: dict):
    large = [s for g, s in stats_.items() if s is not None and masks[g].sum() >= MIN_GROUP_ROWS]
    pool = large if len(large) >= 2 else [s for s in stats_.values() if s is not None]
    return (max(pool) - min(pool)) if len(pool) >= 2 else None


def _with_null_band(out: dict, labels, y, statistic, band_key: str) -> dict:
    order = [g['value'] for g in out['groups']]
    band = _null_band(labels, order, y, statistic)
    for g in out['groups']:
        g['null_band'] = band['groups'].get(g['value'])
    out[band_key] = {k: band[k] for k in ('chart', 'shuffles', 'seed', 'note')}
    return out


def quality(case: c.Case, frame) -> dict:
    """The structural quality of the development rows, **without the target** (the caller
    drops the target column): missing cells by column and their co-missing patterns,
    repeated rows, the cardinality of categorical columns with their rare categories, and the
    range of numeric columns against the range the case declares, if any. Special values
    are counted apart from the ordinary values of their column."""
    import pandas as pd
    from pandas.api.types import is_numeric_dtype

    n = int(len(frame))
    columns = [v['name'] for v in case.document['variables']
               if v['name'] in frame.columns and v['role'] != 'target']
    data = frame[columns]
    missing = []
    for name in columns:
        k = int(data[name].isna().sum())
        missing.append({'column': name, 'n_missing': k, 'share': _share(k, n)})
    mask = data.isna()
    any_missing = mask.any(axis=1)
    patterns = {}
    for row in mask[any_missing].itertuples(index=False):
        key = tuple(col for col, flag in zip(columns, row) if flag)
        patterns[key] = patterns.get(key, 0) + 1
    ordered = sorted(patterns.items(), key=lambda kv: (-kv[1], kv[0]))
    co_missing = [{'columns': list(k), 'n_rows': v, 'share': _share(v, n)}
                  for k, v in ordered[:MAX_MISSING_PATTERNS]]
    duplicated = data.astype(str).duplicated(keep='first')
    n_dup = int(duplicated.sum())
    groups = int(data.astype(str)[data.astype(str).duplicated(keep=False)]
                 .drop_duplicates().shape[0]) if n_dup else 0
    cardinality, ranges = [], []
    for v in case.document['variables']:
        name = v['name']
        if name not in columns:
            continue
        values = data[name]
        specials = [s for s in case.document['special_values'] if s['column'] == name]
        special_mask = pd.Series(False, index=values.index)
        for s in specials:
            special_mask |= _matches(values, s['value'], case)
        ordinary = values[~special_mask & values.notna()]
        numeric = v.get('type') in NUMERIC_TYPES and is_numeric_dtype(ordinary)
        if not numeric:
            counts = ordinary.astype(str).value_counts()
            rare = sorted(((str(k), int(c_)) for k, c_ in counts.items()
                           if c_ < RARE_CATEGORY_ROWS), key=lambda kv: (kv[1], kv[0]))
            cardinality.append({'column': name, 'type': v.get('type'),
                                'n_distinct': int(len(counts)),
                                'rare': [{'value': k, 'n_rows': c_} for k, c_ in rare],
                                'rare_rows': RARE_CATEGORY_ROWS})
        else:
            declared = v.get('range')
            low = declared.get('min') if isinstance(declared, dict) else None
            high = declared.get('max') if isinstance(declared, dict) else None
            item = {'column': name, 'type': v.get('type'),
                    'min': _plain(ordinary.min()) if len(ordinary) else None,
                    'max': _plain(ordinary.max()) if len(ordinary) else None,
                    'n_special': int(special_mask.sum()),
                    'declared': ({'min': low, 'max': high} if declared else None),
                    'n_below': int((ordinary < low).sum()) if low is not None else None,
                    'n_above': int((ordinary > high).sum()) if high is not None else None}
            ranges.append(item)
    return {'partition': 'development', 'n_rows': n, 'n_columns': len(columns),
            'target_read': False, 'missing': missing,
            'n_rows_with_missing': int(any_missing.sum()), 'co_missing': co_missing,
            'duplicates': {'n_rows': n_dup, 'n_groups': groups,
                           'definition': 'rows identical on every column except the target'},
            'cardinality': cardinality, 'ranges': ranges,
            'question': question('eda.quality'),
            'note': 'Structural reading of the development rows: the target is not read, and '
                    'nothing here is a rate or an association. A range is checked only against '
                    'a range the case declares.'}


def single_feature_signal(case: c.Case, train, candidates: list, availability: Mapping,
                          special: list, groups: list | None = None) -> dict:
    """Out-of-fold signal of each candidate feature alone on the training rows (5 folds,
    fixed seed): the AUC of a one-feature logistic model (binary) or the R² of a one-feature
    linear model (regression). A feature whose signal reaches the level, or stands far above
    the others, raises a legitimacy question: is its value really known at the prediction
    moment? It never selects or drops a feature.

    ``groups`` (v0.2b, WP-B3, ``duplicates: {policy: group}``): the entity group of every
    training row; the folds then keep each group of identical records whole
    (``StratifiedGroupKFold`` or ``GroupKFold``)."""
    import numpy as np
    from sklearn.linear_model import LinearRegression
    from sklearn.model_selection import KFold, StratifiedKFold, cross_val_predict
    from mlkit import classical
    from . import metrics
    from .fit import design

    binary = case.task == 'binary'
    if binary:
        from .activities import positive
        y = positive(train, case).to_numpy()
        folds = StratifiedKFold(SIGNAL_FOLDS, shuffle=True, random_state=SIGNAL_SEED)
    else:
        y = numeric_target(case, train).to_numpy(dtype=float)
        folds = KFold(SIGNAL_FOLDS, shuffle=True, random_state=SIGNAL_SEED)
    if groups is not None:
        from sklearn.model_selection import GroupKFold, StratifiedGroupKFold
        folds = (StratifiedGroupKFold(SIGNAL_FOLDS, shuffle=True, random_state=SIGNAL_SEED)
                 if binary else GroupKFold(SIGNAL_FOLDS))
        folds = list(folds.split(np.zeros(len(y)), y, groups))
    signals = []
    for name in candidates:
        own = [s for s in special if s['column'] == name]
        X, _ = design(train, [name], own, case)
        if binary:
            spec = {'task': {'kind': 'binary'}, 'model_options': {}}
            model = classical.pipeline('logistic', X, spec, SIGNAL_SEED)
            score = cross_val_predict(model, X, y, cv=folds, method='predict_proba')[:, 1]
            value = metrics.roc_auc(y, score)
        else:
            spec = {'task': {'kind': 'regression'}, 'model_options': {}}
            model = classical.pipeline('ridge', X, spec, SIGNAL_SEED)
            model.set_params(model=LinearRegression())
            pred = cross_val_predict(model, X, y, cv=folds)
            total = float(((y - y.mean()) ** 2).sum())
            value = 1.0 - float(((y - pred) ** 2).sum()) / total if total else None
        signals.append({'feature': name, 'availability': availability.get(name),
                        'score': value})
    scores = [s['score'] for s in signals if s['score'] is not None]
    median = float(np.median(scores)) if scores else None
    top = max(scores) if scores else None
    level, gap = (SIGNAL_AUC_LEVEL, SIGNAL_AUC_GAP) if binary else (SIGNAL_R2_LEVEL, SIGNAL_R2_GAP)
    metric = 'roc_auc' if binary else 'r2'
    questions = []
    for rank, s in enumerate(sorted(signals, key=lambda s: (-(s['score'] if s['score'] is not None
                                                              else -np.inf), s['feature'])), 1):
        s['rank'] = rank
    signals.sort(key=lambda s: s['rank'])
    for s in signals:
        value = s['score']
        if value is None:
            s['flag'] = False
            continue
        far = median is not None and value == top and value - median >= gap
        s['flag'] = bool(value >= level or far)
        if s['flag']:
            what = (f'ranks the training rows with an out-of-fold AUC of {value:.2f}' if binary
                    else f'explains {value:.2f} of the variance of the target out of fold (R²)')
            why = (' on its own' + (f', far above the other features (median {median:.2f})'
                                    if far else ''))
            status = s['availability'] or 'no availability decision'
            questions.append({
                'feature': s['feature'], 'score': value, 'availability': s['availability'],
                'text': f'{s["feature"]} {what}{why}. Is its value really known at the '
                        f'prediction moment, or is it recorded at or after the outcome? '
                        f'(availability decided: {status})'})
    out = {'partition': 'train', 'n_rows': int(len(train)), 'metric': metric,
            'folds': SIGNAL_FOLDS, 'seed': SIGNAL_SEED, 'signals': signals, 'median': median,
            'level': level, 'gap': gap, 'questions': questions,
            'question': question('eda.single_feature_signal'),
            'note': 'Each feature alone, scored out of fold on the training rows. A high value '
                    'only raises a question about when the value is known; it never keeps or '
                    'drops a feature, and a legitimate feature may score high.'}
    if groups is not None:
        out['grouped_folds'] = 'identical records kept in one fold (duplicates: group)'
    return out


def compute(activity: str, case: c.Case, train, params: Mapping) -> dict:
    if activity == 'eda.quality':
        values = quality(case, train)
        return {'values': values, 'blobs': {}, 'partition': params['partition'],
                'n_rows': int(len(train))}
    if activity == 'eda.single_feature_signal':
        values = single_feature_signal(case, train, params['candidates'],
                                       params['availability'], params['special_values'],
                                       params.get('groups'))
    elif activity == 'eda.distribution':
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
