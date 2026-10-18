"""Errors of numeric predictions: pure metrics, residuals, and a paired bootstrap (M3).

A regression study compares models by their error **in the unit of the target**:

* ``mae``, mean absolute error: the average size of an error, ``mean(|y - prediction|)``;
* ``rmse``, root mean squared error: ``sqrt(mean((y - prediction) ** 2))``. Squaring
  weighs large errors more, so ``rmse >= mae`` and a gap between them signals a few large
  errors;
* the **residual** of a row is ``y - prediction`` (observed minus predicted): a positive
  residual means the model predicted too low. The mean residual is the **bias**.

:func:`paired_bootstrap` resamples the validation rows with replacement, the **same**
resample for every model in a replicate, and reports percentile intervals of each
model's MAE and RMSE and of each model's difference with a reference model (model minus
reference: a negative difference means a smaller error than the reference). Intervals
describe the sampling variability of these validation rows only; they are not evidence
about future rows.

Pure: numpy only, no file, no state, no pandas, no scikit-learn.
"""
from __future__ import annotations

from typing import Mapping

import numpy as np

METRICS = ('mae', 'rmse')
QUANTILES = (('q05', 5), ('q25', 25), ('median', 50), ('q75', 75), ('q95', 95))
RESIDUAL_DEFINITION = ('residual = observed minus predicted; a positive residual means the '
                       'model predicted too low; the mean residual is the bias')


def _arrays(y, prediction) -> tuple[np.ndarray, np.ndarray]:
    y = np.asarray(y, dtype=float)
    p = np.asarray(prediction, dtype=float)
    if y.shape != p.shape or y.ndim != 1 or not len(y):
        raise ValueError('y and prediction are non-empty one-dimensional arrays of one length')
    if not (np.isfinite(y).all() and np.isfinite(p).all()):
        raise ValueError('y and prediction must be finite numbers')
    return y, p


def errors(y, prediction) -> dict:
    """``n``, ``mae``, ``rmse``, ``mean_residual`` (bias), ``median_abs_residual``, and
    ``max_abs_residual`` of ``prediction`` against ``y``."""
    y, p = _arrays(y, prediction)
    r = y - p
    a = np.abs(r)
    return {'n': int(len(y)), 'mae': float(a.mean()), 'rmse': float(np.sqrt(np.mean(r ** 2))),
            'mean_residual': float(r.mean()), 'median_abs_residual': float(np.median(a)),
            'max_abs_residual': float(a.max())}


def residual_summary(y, prediction) -> dict:
    """Distribution of the residuals ``y - prediction``: mean (bias), standard deviation,
    minimum, quantiles, maximum."""
    y, p = _arrays(y, prediction)
    r = y - p
    out = {'n': int(len(r)), 'mean': float(r.mean()),
           'sd': float(r.std(ddof=1)) if len(r) > 1 else None, 'min': float(r.min())}
    for name, q in QUANTILES:
        out[name] = float(np.percentile(r, q))
    out['max'] = float(r.max())
    return out


def _metric_rows(y: np.ndarray, p: np.ndarray, idx: np.ndarray) -> np.ndarray:
    r = y[idx] - p[idx]
    return np.array([np.mean(np.abs(r)), np.sqrt(np.mean(r ** 2))])


def _interval(samples: np.ndarray, level: float) -> dict:
    alpha = (1.0 - level) / 2.0
    low, high = np.percentile(samples, [100 * alpha, 100 * (1 - alpha)])
    return {'low': float(low), 'high': float(high)}


def paired_bootstrap(y, predictions: Mapping[str, object], B: int, seed: int, *,
                     level: float = 0.95, reference: str | None = None) -> dict:
    """Percentile intervals of MAE and RMSE for every model, and of each model's
    difference with ``reference`` (the first model by default).

    Every replicate draws one resample of row positions and applies it to every model
    (paired). The result is a pure function of the inputs and ``seed``.
    """
    y = np.asarray(y, dtype=float)
    names = list(predictions)
    if not names:
        raise ValueError('at least one model is needed')
    reference = names[0] if reference is None else reference
    if reference not in predictions:
        raise ValueError(f'reference {reference!r} is not one of the models')
    arrays = {}
    for name in names:
        _, arrays[name] = _arrays(y, predictions[name])
    if type(B) is not int or B < 1:
        raise ValueError('B is a positive integer')
    rng = np.random.default_rng(seed)
    n = len(y)
    samples = {name: np.empty((B, len(METRICS))) for name in names}
    for b in range(B):
        idx = rng.integers(0, n, n)
        for name in names:
            samples[name][b] = _metric_rows(y, arrays[name], idx)
    points = {name: errors(y, arrays[name]) for name in names}
    intervals = {name: {m: _interval(samples[name][:, i], level) for i, m in enumerate(METRICS)}
                 for name in names}
    deltas = {}
    for name in names:
        if name == reference:
            continue
        diff = samples[name] - samples[reference]
        deltas[name] = {m: {'point': points[name][m] - points[reference][m],
                            **_interval(diff[:, i], level)}
                        for i, m in enumerate(METRICS)}
    return {'replicates': B, 'seed': seed, 'level': level, 'reference': reference,
            'method': 'paired percentile bootstrap over validation rows',
            'models': points, 'intervals': intervals, 'deltas': deltas}
