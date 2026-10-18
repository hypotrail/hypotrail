"""Ranking metrics of a binary score, in plain numpy (plan WP2.3).

Both fits use the same definitions, so the constant baseline needs no scikit-learn:

* ``roc_auc``: the probability that a random positive scores above a random
  negative, ties counted one half (Mann-Whitney with average ranks). A constant
  score has an AUC of exactly 0.5.
* ``average_precision``: the sum over distinct score thresholds, from the highest
  down, of ``(recall_i - recall_{i-1}) * precision_i``. This is the definition of
  ``sklearn.metrics.average_precision_score``; ``framework/tests/study/test_fit.py``
  checks the equality. A constant score has an average precision equal to the
  positive rate.

Pure: no file I/O, numpy only.
"""
from __future__ import annotations

import numpy as np


def _arrays(y, score):
    y = np.asarray(y, dtype=float)
    s = np.asarray(score, dtype=float)
    if y.shape != s.shape or y.ndim != 1:
        raise ValueError('y and score are one-dimensional arrays of the same length')
    return y, s


def average_ranks(values) -> np.ndarray:
    """1-based ranks of ``values``, ties sharing their average rank."""
    v = np.asarray(values, dtype=float)
    _, inverse, counts = np.unique(v, return_inverse=True, return_counts=True)
    starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
    return (starts + (counts + 1) / 2.0)[inverse]


def roc_auc(y, score) -> float | None:
    """Area under the ROC curve, or None when one class is absent."""
    y, s = _arrays(y, score)
    positives = float(y.sum())
    negatives = float(len(y) - positives)
    if positives == 0 or negatives == 0:
        return None
    ranks = average_ranks(s)
    return float((ranks[y == 1].sum() - positives * (positives + 1) / 2.0) / (positives * negatives))


def average_precision(y, score) -> float | None:
    """Average precision (step-wise, distinct thresholds), or None without positives."""
    y, s = _arrays(y, score)
    positives = float(y.sum())
    if positives == 0:
        return None
    order = np.argsort(-s, kind='mergesort')
    s_sorted, y_sorted = s[order], y[order]
    last_of_group = np.r_[np.flatnonzero(np.diff(s_sorted)), len(s_sorted) - 1]
    tps = np.cumsum(y_sorted)[last_of_group]
    selected = last_of_group + 1.0
    precision = tps / selected
    recall = tps / positives
    previous = np.concatenate([[0.0], recall[:-1]])
    return float(np.sum((recall - previous) * precision))
