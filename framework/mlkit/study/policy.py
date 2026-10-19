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

RULE_TYPES = ('threshold', 'capacity')
METRICS = ('precision', 'recall', 'volume')


def parse_rule(rule) -> tuple[str, float | int]:
    """``("threshold", t)`` or ``("capacity", k)``; ``ValueError`` otherwise.

    Same grammar as ``mlkit.study.dependencies.parse_policy`` (checked by a test).
    """
    from .records import parse_rule as parse

    parsed = parse(rule)
    if parsed is None:
        raise ValueError(f'a rule is "threshold:<t>" (0 <= t <= 1, decimal digits) or '
                         f'"capacity:<k>" (an integer k >= 1, digits only), not {rule!r}')
    return parsed


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


def weights(score, rule) -> tuple[np.ndarray, dict]:
    """Selection weights (1, 0, or a fraction) and the cut description of ``rule``."""
    kind, amount = parse_rule(rule)
    s = np.asarray(score, dtype=float)
    if kind == 'threshold':
        at = s == amount
        return (s >= amount).astype(float), {
            'score': float(amount), 'n_tied': int(at.sum()),
            'fraction_selected': 1.0 if at.any() else None}
    return capacity_weights(s, amount)


def _counts(y: np.ndarray, w: np.ndarray) -> tuple[float, float, float]:
    selected = float(w.sum())
    tp = float((w * y).sum())
    return selected, tp, float(y.sum())


def _ratios(selected: float, tp: float, positives: float, n: int) -> dict:
    return {'precision': tp / selected if selected > 0 else None,
            'recall': tp / positives if positives > 0 else None,
            'volume': selected, 'volume_rate': selected / n if n else None}


def evaluate(y, score, rule) -> dict:
    """Confusion counts and rates of ``rule`` on ``(y, score)``; pure.

    ``y`` is 1 for the positive label and 0 otherwise. Counts are expected counts
    when a capacity cut splits a tie group (``selection: "expected"``).
    """
    y = np.asarray(y, dtype=float)
    s = np.asarray(score, dtype=float)
    if y.shape != s.shape or y.ndim != 1:
        raise ValueError('y and score are one-dimensional arrays of the same length')
    kind, amount = parse_rule(rule)
    w, cut = weights(s, rule)
    if kind == 'capacity':
        selected, tp = _capacity_counts(y, s, amount)
        positives = float(y.sum())
    else:
        selected, tp, positives = _counts(y, w)
    n = len(y)
    prorated = kind == 'capacity' and cut['n_tied'] > 0
    return {'rule': rule, 'kind': kind, 'parameter': amount, 'n': n,
            'n_positive': int(positives), 'selected': selected, 'true_positives': tp,
            'false_positives': selected - tp, 'false_negatives': positives - tp,
            **_ratios(selected, tp, positives, n),
            'tied_at_cut': cut['n_tied'], 'cut': cut,
            'selection': 'expected' if prorated else 'exact'}


def _interval(samples: np.ndarray, level: float) -> dict:
    defined = samples[~np.isnan(samples)]
    undefined = int(len(samples) - len(defined))
    if not len(defined):
        return {'low': None, 'high': None, 'undefined_replicates': undefined}
    alpha = (1.0 - level) / 2.0
    low, high = np.percentile(defined, [100 * alpha, 100 * (1 - alpha)])
    return {'low': float(low), 'high': float(high), 'undefined_replicates': undefined}


def _replicate(y: np.ndarray, s: np.ndarray, kind: str, amount) -> tuple[float, float, float]:
    if kind == 'threshold':
        selected, tp, positives = _counts(y, (s >= amount).astype(float))
    else:
        selected, tp = _capacity_counts(y, s, amount)
        positives = float(y.sum())
    precision = tp / selected if selected > 0 else np.nan
    recall = tp / positives if positives > 0 else np.nan
    return precision, recall, selected


def paired_bootstrap(y, scores: Mapping[str, object], rule, B: int, seed: int, *,
                     level: float = 0.95, reference: str | None = None, pairs=()) -> dict:
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
    for b in range(B):
        idx = rng.integers(0, n, n)
        yb = y[idx]
        for name in names:
            samples[name][b] = _replicate(yb, arrays[name][idx], kind, amount)
    intervals = {name: {m: _interval(samples[name][:, i], level) for i, m in enumerate(METRICS)}
                 for name in names}
    points = {name: evaluate(y, arrays[name], rule) for name in names}
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
    return {'rule': rule, 'replicates': B, 'seed': seed, 'level': level,
            'reference': reference, 'method': 'paired percentile bootstrap over validation rows',
            'intervals': intervals, 'deltas': deltas, 'comparisons': comparisons}
