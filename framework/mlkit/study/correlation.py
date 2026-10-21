"""Predictor-versus-predictor association matrix, ``eda.correlation`` (v0.3, WP-E2, R28).

A structural reading of the **development rows without the target** (the caller passes the
candidate features only), like ``eda.quality``: it is not a look at the outcome and is never
counted as one. It answers one question: which predictors carry nearly the same
information, so that a model would split their weight between them (collinearity)?

One measure per pair of features, chosen by their kinds:

* two numeric features: **Spearman's rank correlation** (signed, -1 to 1), on the rows where
  both hold an ordinary value (special values and missing cells left out);
* two categorical features: **Cramér's V** with the bias correction of Bergsma (unsigned,
  0 to 1), on every row, a missing cell being its own category;
* a numeric and a categorical feature: the **correlation ratio** (eta) of the numeric
  feature's ranks across the categories (unsigned, 0 to 1).

A pair whose association reaches :data:`COLLINEARITY_LEVEL` in absolute value is flagged.
The order of the features groups the strongly associated ones together: an average-linkage
hierarchical clustering on the distance 1 - |association|, leaves in dendrogram order (a
fixed, data-derived order; no randomness).

These are associations among predictors in this sample, not effects. pandas, numpy, and
scipy are imported by the caller's process, never at module import.
"""
from __future__ import annotations

from typing import Mapping

from . import case as c

COLLINEARITY_LEVEL = 0.8
MISSING_CATEGORY = '(missing)'
# A pair needs at least this many rows with both values to be measured.
MIN_PAIR_ROWS = 10
NUMERIC_TYPES = ('numeric', 'number', 'integer')
MEASURES = {
    'spearman': "Spearman's rank correlation (two numeric features, signed)",
    'cramers_v': "Cramér's V, bias-corrected (two categorical features, unsigned)",
    'eta': 'Correlation ratio of the ranks across the categories (a numeric and a categorical '
           'feature, unsigned)',
}
QUESTION = ('Do any two predictors carry nearly the same information in the development rows, '
            'so that a model would split its weight between them?')
NOTE = ('Structural reading of the development rows: the target is not read, so this is not a '
        'look at the outcome. An association between two predictors is not an effect on the '
        'outcome; a flagged pair only asks whether both are needed.')


def _numeric(case: c.Case, values, name: str):
    """The column as floats, with its special values and missing cells as NaN."""
    import numpy as np
    import pandas as pd
    from .activities import matches
    mask = pd.Series(False, index=values.index)
    for s in case.document['special_values']:
        if s['column'] == name:
            mask |= matches(values, s['value'], case.dataset.get('na_values', ()))
    out = pd.to_numeric(values.where(~mask), errors='coerce').astype(float)
    return out.replace([np.inf, -np.inf], np.nan)


def _categorical(values):
    return values.astype(object).where(values.notna(), MISSING_CATEGORY).astype(str)


def _spearman(a, b) -> tuple[float | None, int]:
    both = a.notna() & b.notna()
    n = int(both.sum())
    if n < MIN_PAIR_ROWS:
        return None, n
    ra, rb = a[both].rank(), b[both].rank()
    if ra.std() == 0 or rb.std() == 0:
        return None, n
    return float(ra.corr(rb)), n


def _cramers_v(a, b) -> tuple[float | None, int]:
    """Bias-corrected Cramér's V (Bergsma 2013)."""
    import numpy as np
    import pandas as pd
    n = int(len(a))
    if n < MIN_PAIR_ROWS:
        return None, n
    table = pd.crosstab(a, b).to_numpy(dtype=float)
    r, k = table.shape
    if r < 2 or k < 2:
        return None, n
    expected = table.sum(axis=1, keepdims=True) * table.sum(axis=0, keepdims=True) / n
    chi2 = float(((table - expected) ** 2 / expected).sum())
    phi2 = chi2 / n
    phi2c = max(0.0, phi2 - (k - 1) * (r - 1) / (n - 1))
    rc = r - (r - 1) ** 2 / (n - 1)
    kc = k - (k - 1) ** 2 / (n - 1)
    denominator = min(kc - 1, rc - 1)
    if denominator <= 0:
        return None, n
    return float(min(1.0, np.sqrt(phi2c / denominator))), n


def _eta(numeric, categories) -> tuple[float | None, int]:
    both = numeric.notna()
    n = int(both.sum())
    if n < MIN_PAIR_ROWS:
        return None, n
    ranks = numeric[both].rank()
    groups = categories[both]
    total = float(((ranks - ranks.mean()) ** 2).sum())
    if total == 0 or groups.nunique() < 2:
        return None, n
    means = ranks.groupby(groups).transform('mean')
    between = float(((means - ranks.mean()) ** 2).sum())
    return float(min(1.0, (between / total) ** 0.5)), n


def _order(names: list[str], strength: Mapping[tuple[str, str], float]) -> list[str]:
    """Average-linkage clustering on 1 - |association|; leaves in dendrogram order."""
    if len(names) < 3:
        return list(names)
    import numpy as np
    from scipy.cluster.hierarchy import leaves_list, linkage
    from scipy.spatial.distance import squareform
    size = len(names)
    distance = np.ones((size, size))
    np.fill_diagonal(distance, 0.0)
    for i in range(size):
        for j in range(i + 1, size):
            value = strength.get((names[i], names[j]))
            d = 1.0 if value is None else 1.0 - abs(value)
            distance[i, j] = distance[j, i] = max(0.0, d)
    tree = linkage(squareform(distance, checks=False), method='average')
    return [names[i] for i in leaves_list(tree)]


def correlation(case: c.Case, frame, columns: list[str]) -> dict:
    """The association of every pair of ``columns`` (the candidate features, in the case's
    order) on the development rows of ``frame``, which never holds the target."""
    kinds = {}
    series = {}
    for name in columns:
        variable = case.variables[name]
        if variable.get('type') in NUMERIC_TYPES:
            values = _numeric(case, frame[name], name)
            kinds[name] = 'numeric'
        else:
            values = _categorical(frame[name])
            kinds[name] = 'categorical'
        series[name] = values
    pairs, strength = [], {}
    for i, a in enumerate(columns):
        for b in columns[i + 1:]:
            if kinds[a] == 'numeric' and kinds[b] == 'numeric':
                measure = 'spearman'
                value, n = _spearman(series[a], series[b])
            elif kinds[a] == 'categorical' and kinds[b] == 'categorical':
                measure = 'cramers_v'
                value, n = _cramers_v(series[a], series[b])
            else:
                measure = 'eta'
                num, cat = (a, b) if kinds[a] == 'numeric' else (b, a)
                value, n = _eta(series[num], series[cat])
            strength[(a, b)] = strength[(b, a)] = value
            pairs.append({'a': a, 'b': b, 'measure': measure, 'value': value, 'n_rows': n,
                          'flag': value is not None and abs(value) >= COLLINEARITY_LEVEL})
    order = _order(list(columns), strength)
    flagged = sorted((p for p in pairs if p['flag']),
                     key=lambda p: (-abs(p['value']), p['a'], p['b']))
    return {'partition': 'development', 'n_rows': int(len(frame)), 'target_read': False,
            'columns': [{'name': n, 'kind': kinds[n]} for n in columns], 'order': order,
            'pairs': pairs, 'flagged': [{'a': p['a'], 'b': p['b'], 'measure': p['measure'],
                                         'value': p['value']} for p in flagged],
            'n_flagged': len(flagged), 'level': COLLINEARITY_LEVEL, 'measures': dict(MEASURES),
            'question': QUESTION, 'note': NOTE}


def compute(case: c.Case, frame, params: Mapping) -> dict:
    values = correlation(case, frame, list(params['columns']))
    return {'values': values, 'blobs': {}, 'partition': params['partition'],
            'n_rows': int(len(frame))}
