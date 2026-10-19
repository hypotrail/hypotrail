"""Decision policies on persisted scores: pure evaluation and paired bootstrap (plan WP2.4).

A policy turns validation scores into actions. Two rule types exist in v0.1:

* ``threshold:t`` selects every row whose score is ``>= t`` (inclusive). Rows exactly
  at ``t`` are selected; ``tied_at_cut`` counts them.
* ``capacity:k`` selects the ``k`` highest scores. When the ``k``-th place falls
  inside a group of equal scores, every row of that group is selected with the same
  fraction (pro rata), so counts are **expected** counts. ``tied_at_cut`` is the
  size of that group, and ``cut`` says which score and fraction. This is the tie rule
  of ``mlkit.decision.accept_weights`` applied to the negated score with
  ``rate = k / n``; :func:`capacity_weights` takes ``k`` itself so the selected count
  is exactly ``k`` without floating-point drift (equality is tested).
* ``share:p`` (v0.2b, WP-B3, remark R6) is a capacity stated as a share of the rows
  evaluated: ``capacity:k`` with ``k = share_capacity(p, n)``, ``floor(p * n + 0.5)``
  rows and at least one, on the ``n`` rows scored. A bootstrap replicate has ``n`` rows
  too, so it keeps the same ``k``.

:func:`gain_points` (v0.2b) reports what acting on the top 5, 10 and 20 % of the
scored rows would select: the capacity, the precision and its gain in points over the
base rate, the lift, and the share of the positive rows found (the cumulative gain).

:func:`evaluate` is a pure function of ``(y, score, rule)``: it reads no file and no
state, and changing ``k`` or ``t`` never refits anything. ``hypotrail run
policy.evaluate`` records it with the exposure purpose ``validation_policy_selection``;
``hypotrail preview policy`` and the notebook workbench call the same function and
record nothing.

:func:`paired_bootstrap` resamples validation rows with replacement, the **same**
resample for every model in a replicate, and reports percentile intervals for
precision, recall, and volume, and for the difference of each model with a
reference model. Intervals describe the sampling variability of these validation
rows only; they are not evidence about future campaigns.

numpy only; no pandas, no scikit-learn, no study state.
"""
from __future__ import annotations

from typing import Mapping

import numpy as np

RULE_TYPES = ('threshold', 'capacity', 'share')
GAIN_SHARES = (0.05, 0.1, 0.2)
METRICS = ('precision', 'recall', 'volume')


def parse_rule(rule) -> tuple[str, float | int]:
    """``("threshold", t)``, ``("capacity", k)`` or ``("share", p)``; ``ValueError``
    otherwise.

    Same grammar as ``mlkit.study.dependencies.parse_policy`` (checked by a test).
    """
    from .records import parse_rule as parse

    parsed = parse(rule)
    if parsed is None:
        raise ValueError(f'a rule is "threshold:<t>" (0 <= t <= 1, decimal digits), '
                         f'"capacity:<k>" (an integer k >= 1, digits only), or "share:<p>" '
                         f'(0 < p <= 1, decimal digits), not {rule!r}')
    return parsed


def share_capacity(p: float, n: int) -> int:
    """The capacity of ``share:p`` on ``n`` rows: ``floor(p * n + 0.5)``, at least 1 (when
    ``n >= 1``) and at most ``n``."""
    if n < 1:
        return 0
    return min(n, max(1, int(np.floor(float(p) * n + 0.5))))


def _resolved(rule, n: int) -> tuple[str, float | int, int | None]:
    """``(kind, amount, k)``: ``k`` is the capacity of a ``capacity`` or ``share`` rule on
    ``n`` rows, None for a threshold."""
    kind, amount = parse_rule(rule)
    if kind == 'capacity':
        return kind, amount, int(amount)
    if kind == 'share':
        return kind, amount, share_capacity(amount, n)
    return kind, amount, None


def capacity_weights(score, k: int) -> tuple[np.ndarray, dict]:
    """Selection weights of the ``k`` highest scores, ties at the cut pro rata.

    Returns ``(weights, cut)`` where ``cut`` is ``{score, n_tied, fraction_selected}``
    for the tie group split by the cut, or ``{score: None, n_tied: 0, ...}`` when the
    cut falls between two distinct scores.
    """
    s = np.asarray(score, dtype=float)
    n = len(s)
    k = min(int(k), n)
    values, inverse, counts = np.unique(-s, return_inverse=True, return_counts=True)
    before = np.concatenate([[0], np.cumsum(counts)[:-1]])
    take = np.clip(k - before, 0, counts).astype(float)
    fraction = take / counts
    weights = fraction[inverse]
    partial = np.flatnonzero((take > 0) & (take < counts))
    if len(partial):
        g = int(partial[0])
        cut = {'score': float(-values[g]), 'n_tied': int(counts[g]),
               'fraction_selected': float(fraction[g])}
    else:
        cut = {'score': None, 'n_tied': 0, 'fraction_selected': None}
    return weights, cut


def _capacity_counts(y: np.ndarray, s: np.ndarray, k: int) -> tuple[float, float]:
    """Expected selected and true-positive counts of ``capacity:k``, by tie group.

    Whole groups contribute their counts exactly; the group split by the cut
    contributes ``taken * positives / size``. So a capacity selects exactly ``k`` rows.
    """
    _, inverse, counts = np.unique(-s, return_inverse=True, return_counts=True)
    positives = np.bincount(inverse, weights=y, minlength=len(counts))
    before = np.concatenate([[0], np.cumsum(counts)[:-1]])
    take = np.clip(min(int(k), len(s)) - before, 0, counts).astype(float)
    return float(take.sum()), float(np.sum(take * positives / counts))


def weights(score, rule, groups=None) -> tuple[np.ndarray, dict]:
    """Selection weights (1, 0, or a fraction) and the cut description of ``rule``; with
    ``groups`` (B6c, H3) a capacity or a share selects within each fold."""
    s = np.asarray(score, dtype=float)
    if groups is not None and parse_rule(rule)[0] != 'threshold':
        folds = fold_index(groups)
        caps = fold_capacities(rule, [len(ix) for _, ix in folds], len(s))
        w = np.zeros(len(s))
        tied = 0
        for (_, ix), k in zip(folds, caps):
            wf, cut = capacity_weights(s[ix], k)
            w[ix] = wf
            tied += cut['n_tied']
        return w, {'score': None, 'n_tied': tied, 'fraction_selected': None}
    kind, amount, k = _resolved(rule, len(s))
    if kind == 'threshold':
        at = s == amount
        return (s >= amount).astype(float), {
            'score': float(amount), 'n_tied': int(at.sum()),
            'fraction_selected': 1.0 if at.any() else None}
    return capacity_weights(s, k)


def _counts(y: np.ndarray, w: np.ndarray) -> tuple[float, float, float]:
    selected = float(w.sum())
    tp = float((w * y).sum())
    return selected, tp, float(y.sum())


def _ratios(selected: float, tp: float, positives: float, n: int) -> dict:
    return {'precision': tp / selected if selected > 0 else None,
            'recall': tp / positives if positives > 0 else None,
            'volume': selected, 'volume_rate': selected / n if n else None}


def fold_index(groups) -> list[tuple[int, np.ndarray]]:
    """``[(fold, positions)]`` of a fold assignment, folds in increasing order."""
    g = np.asarray(groups)
    return [(int(v), np.flatnonzero(g == v)) for v in np.unique(g)]


def fold_capacities(rule, sizes, n: int) -> list[int] | None:
    """B6c (H3): the capacity of ``rule`` within each fold of ``sizes`` rows: a share keeps
    its share of each fold, a capacity ``k`` its share ``k / n`` of each fold
    (:func:`share_capacity`); None for a threshold, which needs no capacity."""
    kind, amount = parse_rule(rule)
    if kind == 'threshold':
        return None
    p = float(amount) if kind == 'share' else (int(amount) / n if n else 0.0)
    return [share_capacity(p, int(m)) for m in sizes]


def _fold_rows(y: np.ndarray, s: np.ndarray, rule, folds) -> list[dict]:
    n = len(y)
    caps = fold_capacities(rule, [len(ix) for _, ix in folds], n)
    out = []
    for i, (fold, ix) in enumerate(folds):
        yf, sf = y[ix], s[ix]
        if caps is None:
            selected, tp, _ = _counts(yf, (sf >= parse_rule(rule)[1]).astype(float))
        else:
            selected, tp = _capacity_counts(yf, sf, caps[i])
        row = {'fold': fold, 'n': int(len(ix)), 'n_positive': int(yf.sum()),
               'selected': selected, 'true_positives': tp,
               'precision': tp / selected if selected > 0 else None}
        if caps is not None:
            row['capacity'] = caps[i]
        out.append(row)
    return out


def evaluate(y, score, rule, groups=None) -> dict:
    """Confusion counts and rates of ``rule`` on ``(y, score)``; pure.

    ``y`` is 1 for the positive label and 0 otherwise. Counts are expected counts
    when a capacity cut splits a tie group (``selection: "expected"``).

    ``groups`` (B6c, H3): the fold of each row of out-of-fold scores. Each fold's scores
    come from another model, so their scales differ (a temporal fold's model sees other
    periods); a capacity or a share is then applied **within each fold** (its share of
    the fold's rows, the best scores of that fold's model) and the counts are summed
    (``selection_scope: "within_fold"``, ``capacity`` the summed capacity). A threshold
    reads the scores as they are (``selection_scope: "pooled"``). ``by_fold`` gives each
    fold's counts and precision.
    """
    y = np.asarray(y, dtype=float)
    s = np.asarray(score, dtype=float)
    if y.shape != s.shape or y.ndim != 1:
        raise ValueError('y and score are one-dimensional arrays of the same length')
    if groups is not None:
        return _evaluate_within(y, s, rule, groups)
    kind, amount, k = _resolved(rule, len(s))
    w, cut = weights(s, rule)
    if k is not None:
        selected, tp = _capacity_counts(y, s, k)
        positives = float(y.sum())
    else:
        selected, tp, positives = _counts(y, w)
    n = len(y)
    prorated = k is not None and cut['n_tied'] > 0
    out = {'rule': rule, 'kind': kind, 'parameter': amount, 'n': n,
           'n_positive': int(positives), 'selected': selected, 'true_positives': tp,
           'false_positives': selected - tp, 'false_negatives': positives - tp,
           **_ratios(selected, tp, positives, n),
           'tied_at_cut': cut['n_tied'], 'cut': cut,
           'selection': 'expected' if prorated else 'exact'}
    if kind == 'share':
        out['capacity'] = k        # v0.2b: the rows a share selects on these n rows
    return out


def _evaluate_within(y: np.ndarray, s: np.ndarray, rule, groups) -> dict:
    g = np.asarray(groups)
    if g.shape != y.shape:
        raise ValueError('groups has one fold per row')
    kind, amount = parse_rule(rule)
    folds = fold_index(g)
    if kind == 'threshold':
        out = evaluate(y, s, rule)
        out['selection_scope'] = 'pooled'
        out['by_fold'] = _fold_rows(y, s, rule, folds)
        return out
    rows = _fold_rows(y, s, rule, folds)
    n = len(y)
    selected = float(sum(r['selected'] for r in rows))
    tp = float(sum(r['true_positives'] for r in rows))
    positives = float(y.sum())
    tied = 0
    for r, (_, ix) in zip(rows, folds):
        tied += capacity_weights(s[ix], r['capacity'])[1]['n_tied']
    return {'rule': rule, 'kind': kind, 'parameter': amount, 'n': n,
            'n_positive': int(positives), 'selected': selected, 'true_positives': tp,
            'false_positives': selected - tp, 'false_negatives': positives - tp,
            **_ratios(selected, tp, positives, n),
            'tied_at_cut': tied, 'cut': {'score': None, 'n_tied': tied,
                                         'fraction_selected': None},
            'selection': 'expected' if tied else 'exact',
            'capacity': int(sum(r['capacity'] for r in rows)),
            'selection_scope': 'within_fold', 'by_fold': rows}


def gain_points(y, score, shares=GAIN_SHARES, groups=None) -> dict:
    """What acting on the top ``shares`` of the scored rows selects (v0.2b, WP-B3, R6).

    For each share ``p``: the capacity ``k`` (:func:`share_capacity`), the expected
    selected and true-positive counts (ties at the cut pro rata, as ``capacity:k``), the
    precision, its gain over the base rate in percentage points, the lift (precision over
    base rate), and the share of the positive rows found (recall, the cumulative gain).
    Pure; reads nothing else."""
    y = np.asarray(y, dtype=float)
    s = np.asarray(score, dtype=float)
    n = len(y)
    positives = float(y.sum())
    base = positives / n if n else None
    points = []
    folds = fold_index(groups) if groups is not None else None
    for p in shares:
        if folds is None:
            k = share_capacity(p, n)
            selected, tp = _capacity_counts(y, s, k) if n else (0.0, 0.0)
        else:
            # B6c (H3): the top share of each fold, by that fold's model.
            rows = _fold_rows(y, s, f'share:{p:g}', folds)
            k = int(sum(r['capacity'] for r in rows))
            selected = float(sum(r['selected'] for r in rows))
            tp = float(sum(r['true_positives'] for r in rows))
        precision = tp / selected if selected > 0 else None
        points.append({'share': float(p), 'rule': f'share:{p:g}', 'capacity': k,
                       'selected': selected, 'true_positives': tp, 'precision': precision,
                       'gain_points': (100 * (precision - base)
                                       if precision is not None and base is not None else None),
                       'lift': precision / base if precision is not None and base else None,
                       'recall': tp / positives if positives > 0 else None})
    out = {'n': n, 'n_positive': int(positives), 'base_rate': base, 'points': points,
           'definition': 'gain_points is the precision of the top share minus the base rate, '
                         'in percentage points; recall is the share of the positive rows '
                         'found (the cumulative gain).'}
    if folds is not None:
        out['selection_scope'] = 'within_fold'
    return out


def _interval(samples: np.ndarray, level: float) -> dict:
    defined = samples[~np.isnan(samples)]
    undefined = int(len(samples) - len(defined))
    if not len(defined):
        return {'low': None, 'high': None, 'undefined_replicates': undefined}
    alpha = (1.0 - level) / 2.0
    low, high = np.percentile(defined, [100 * alpha, 100 * (1 - alpha)])
    return {'low': float(low), 'high': float(high), 'undefined_replicates': undefined}


def _replicate_within(y: np.ndarray, s: np.ndarray, kind: str, amount,
                      folds: list, caps: list[int] | None) -> tuple[float, float, float]:
    """One replicate of within-fold selection (``folds`` are positions in the resample)."""
    if kind == 'threshold':
        return _replicate(y, s, kind, amount)
    selected = tp = 0.0
    for (_, ix), k in zip(folds, caps):
        a, b = _capacity_counts(y[ix], s[ix], k)
        selected += a
        tp += b
    positives = float(y.sum())
    precision = tp / selected if selected > 0 else np.nan
    recall = tp / positives if positives > 0 else np.nan
    return precision, recall, selected


def _replicate(y: np.ndarray, s: np.ndarray, kind: str, amount) -> tuple[float, float, float]:
    if kind == 'threshold':
        selected, tp, positives = _counts(y, (s >= amount).astype(float))
    else:
        k = share_capacity(amount, len(s)) if kind == 'share' else amount
        selected, tp = _capacity_counts(y, s, k)
        positives = float(y.sum())
    precision = tp / selected if selected > 0 else np.nan
    recall = tp / positives if positives > 0 else np.nan
    return precision, recall, selected


def paired_bootstrap(y, scores: Mapping[str, object], rule, B: int, seed: int, *,
                     level: float = 0.95, reference: str | None = None, pairs=(),
                     groups=None) -> dict:
    """Percentile intervals of precision, recall, and volume for every model, and of
    each model's difference with ``reference`` (the first model by default).

    Every replicate draws one resample of row positions and applies it to every
    model (paired). The result is a pure function of the inputs and ``seed``.

    ``pairs`` (WP-B1): ``[(model, other)]``; ``comparisons[model]`` is then
    ``{reference: other, precision, recall, volume}``, each ``{point, low, high,
    undefined_replicates}``: the difference ``model - other`` on the same resamples (the
    variant against the candidate). The other keys do not depend on ``pairs``.
    """
    y = np.asarray(y, dtype=float)
    names = list(scores)
    if not names:
        raise ValueError('at least one model is needed')
    reference = names[0] if reference is None else reference
    if reference not in scores:
        raise ValueError(f'reference {reference!r} is not one of the models')
    arrays = {name: np.asarray(scores[name], dtype=float) for name in names}
    for name, s in arrays.items():
        if s.shape != y.shape:
            raise ValueError(f'scores of {name} do not match y')
    if type(B) is not int or B < 1:
        raise ValueError('B is a positive integer')
    kind, amount = parse_rule(rule)
    rng = np.random.default_rng(seed)
    n = len(y)
    samples = {name: np.empty((B, len(METRICS))) for name in names}
    if groups is None:
        for b in range(B):
            idx = rng.integers(0, n, n)
            yb = y[idx]
            for name in names:
                samples[name][b] = _replicate(yb, arrays[name][idx], kind, amount)
    else:
        # B6c (H3): resample within each fold (each keeps its size), select within each.
        folds = fold_index(groups)
        caps = fold_capacities(rule, [len(ix) for _, ix in folds], n)
        local, start = [], 0
        for fold, ix in folds:
            local.append((fold, np.arange(start, start + len(ix))))
            start += len(ix)
        for b in range(B):
            idx = np.concatenate([ix[rng.integers(0, len(ix), len(ix))] for _, ix in folds])
            yb = y[idx]
            for name in names:
                samples[name][b] = _replicate_within(yb, arrays[name][idx], kind, amount,
                                                     local, caps)
    intervals = {name: {m: _interval(samples[name][:, i], level) for i, m in enumerate(METRICS)}
                 for name in names}
    points = {name: evaluate(y, arrays[name], rule, groups) for name in names}
    deltas = {}
    for name in names:
        if name == reference:
            continue
        diff = samples[name] - samples[reference]
        deltas[name] = {}
        for i, m in enumerate(METRICS):
            a, r = points[name][m], points[reference][m]
            deltas[name][m] = {'point': (a - r) if a is not None and r is not None else None,
                               **_interval(diff[:, i], level)}
    comparisons = {}
    for name, other in pairs:
        diff = samples[name] - samples[other]
        comparisons[name] = {'reference': other}
        for i, m in enumerate(METRICS):
            a, r = points[name][m], points[other][m]
            comparisons[name][m] = {'point': (a - r) if a is not None and r is not None
                                    else None, **_interval(diff[:, i], level)}
    method = ('paired percentile bootstrap over validation rows' if groups is None else
              'paired percentile bootstrap, rows resampled within each fold')
    return {'rule': rule, 'replicates': B, 'seed': seed, 'level': level,
            'reference': reference, 'method': method,
            'intervals': intervals, 'deltas': deltas, 'comparisons': comparisons}
