"""SciPy backend of the paired row bootstrap (spec L-11, L-12; AC10, AC11).

The engine's review-v1 bootstrap (:func:`mlkit.study.objective.paired_row_bootstrap`) draws
row positions with Python's ``random.Random``. This adapter computes the same *method* with
:func:`scipy.stats.bootstrap`, every choice explicit:

* ``paired=True``: one resample of row positions is applied to the target and to every
  model's predictions (reference first, then candidate);
* ``method="percentile"``: SciPy's default (BCa) would not reproduce the engine's method;
* ``confidence_level``, ``n_resamples`` and the generator ``numpy.random.default_rng(seed)``
  (PCG64) are recorded, with the SciPy and NumPy versions. The same seed does **not** give
  the same resamples as ``random.Random(seed)``: results of the two backends are different
  results, never presented as one;
* the gain is ``candidate - reference`` in the objective's unit; its direction (higher or
  lower is better) is stated by the caller and recorded;
* the undefined-replicate policy is the engine's: one required replicate whose objective is
  undefined invalidates the interval (``eligible: false``, bounds null, the count kept);
  nothing is dropped silently.

Admissibility is decided before the call: rows must be independent observations. Temporal,
grouped or batched dependence returns ``not_applicable``: a SciPy computation does not make a
row bootstrap valid for them. Small samples SciPy refuses (a single row) are reported as
``insufficient_data`` rather than replaced by the historical backend: there is no silent
fallback. :data:`CAPABILITIES` is the published matrix.
"""
from __future__ import annotations

from typing import Callable, Mapping, Sequence

METHOD = {'name': 'paired_row_bootstrap', 'version': '1', 'interval': 'percentile',
          'resampling_unit': 'row', 'backend': 'scipy.stats.bootstrap',
          'generator': 'numpy.random.default_rng (PCG64)'}
LEGACY_METHOD = {'name': 'paired_row_bootstrap', 'version': '1', 'interval': 'percentile',
                 'resampling_unit': 'row', 'backend': 'mlkit.study.objective',
                 'generator': 'random.Random (Mersenne Twister)'}
# Which situations each backend handles (published, tested).
CAPABILITIES = {
    'independent_rows': {'scipy': 'supported', 'legacy': 'supported'},
    'undefined_replicate': {'scipy': 'interval invalidated (same policy)',
                            'legacy': 'interval invalidated'},
    'single_row': {'scipy': 'insufficient_data (SciPy refuses a sample of one)',
                   'legacy': 'computed (every resample is the same row)'},
    'temporal_or_grouped_dependence': {'scipy': 'not_applicable', 'legacy': 'not_applicable'},
    'capacity_or_share_rules': {'scipy': 'not in this contract', 'legacy': 'policy module'},
}


def descriptor(*, level: float, replicates: int, seed: int, reference: str, candidate: str,
               direction: str, unit: str | None) -> dict:
    import numpy
    import scipy
    return {**METHOD, 'paired': True, 'level': float(level), 'replicates': int(replicates),
            'seed': int(seed), 'reference': reference, 'candidate': candidate,
            'gain': f'{candidate} - {reference}', 'direction': direction, 'unit': unit,
            'versions': {'scipy': scipy.__version__, 'numpy': numpy.__version__}, 'warnings': []}


def paired_bootstrap(y: Sequence, predictions: Mapping[str, Sequence],
                     evaluator: Callable[[list, list], Mapping | None], *, replicates: int,
                     seed: int, level: float = .95, direction: str = 'maximize',
                     unit: str | None = None, dependence: str = 'independent') -> dict:
    """Percentile intervals of each model's objective and of ``candidate - reference``
    (``predictions`` holds exactly two models, reference first).

    Returns ``{status, reason, point, intervals, delta, uncertainty}``; ``status`` is ``ok``,
    ``not_applicable`` (dependence), ``insufficient_data`` (too few rows, or an undefined
    replicate) or ``failed`` (a backend exception, with its cause)."""
    import numpy as np
    from scipy import stats
    if type(replicates) is not int or replicates < 1:
        raise ValueError('replicates must be a positive integer')
    if not 0 < level < 1:
        raise ValueError('level must be between zero and one')
    if direction not in ('maximize', 'minimize'):
        raise ValueError('direction is maximize or minimize')
    names = list(predictions)
    if len(names) != 2:
        raise ValueError('the paired contrast compares exactly two models, reference first')
    reference, candidate = names
    desc = descriptor(level=level, replicates=replicates, seed=seed, reference=reference,
                      candidate=candidate, direction=direction, unit=unit)
    n = len(y)
    if any(len(predictions[m]) != n for m in names):
        raise ValueError('all arrays must have the same length')

    def outcome(status, reason, **extra):
        return {'status': status, 'reason': reason, 'point': extra.get('point'),
                'intervals': extra.get('intervals', {m: {'low': None, 'high': None}
                                                     for m in names}),
                'delta': extra.get('delta', {'point': None, 'low': None, 'high': None}),
                'uncertainty': {**desc, 'eligible': status == 'ok',
                                'undefined_replicates': extra.get('undefined')}}
    if dependence != 'independent':
        return outcome('not_applicable', f'{dependence} dependence: a row bootstrap does not '
                                         'describe it')
    if n < 2:
        return outcome('insufficient_data', 'at least two rows are needed')

    def point_of(yy, pp):
        result = evaluator(list(yy), list(pp))
        value = result.get('point') if isinstance(result, Mapping) else None
        return np.nan if value is None else float(value)

    point = {m: point_of(y, predictions[m]) for m in names}
    points = {m: (None if np.isnan(v) else v) for m, v in point.items()}
    delta_point = (None if None in points.values()
                   else points[candidate] - points[reference])

    def statistic(yy, ref, cand):
        a, b = point_of(yy, ref), point_of(yy, cand)
        return np.array([a, b, b - a])
    data = tuple(np.asarray(v, dtype=float) for v in (y, predictions[reference],
                                                      predictions[candidate]))
    import warnings
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            res = stats.bootstrap(data, statistic, paired=True, vectorized=False,
                                  n_resamples=replicates, method='percentile',
                                  confidence_level=level, rng=np.random.default_rng(seed))
        desc['warnings'] = sorted({f'{w.category.__name__}: {w.message}' for w in caught})
    except Exception as exc:                 # noqa: BLE001 - named, never "no interval"
        return outcome('failed', f'backend_failed: {type(exc).__name__}: {exc}',
                       point=points)
    dist = np.asarray(res.bootstrap_distribution)
    undefined = int(np.isnan(dist).any(axis=0).sum())
    if undefined:
        return outcome('insufficient_data', 'at least one required bootstrap replicate had an '
                                            'undefined objective', point=points,
                       delta={'point': delta_point, 'low': None, 'high': None},
                       undefined=undefined)
    low, high = np.asarray(res.confidence_interval.low), np.asarray(res.confidence_interval.high)
    intervals = {reference: {'low': float(low[0]), 'high': float(high[0])},
                 candidate: {'low': float(low[1]), 'high': float(high[1])}}
    return outcome('ok', None, point=points, intervals=intervals,
                   delta={'point': delta_point, 'low': float(low[2]), 'high': float(high[2])},
                   undefined=0) | {'distribution': dist}


def legacy_descriptor(uncertainty: Mapping, *, seed: int) -> dict:
    """The historical backend's result described with the same vocabulary, so a report can
    show which generator produced which interval (they are distinct results)."""
    return {**LEGACY_METHOD, 'paired': True, 'seed': int(seed),
            'level': uncertainty.get('level'), 'replicates': uncertainty.get('replicates'),
            'undefined_replicates': uncertainty.get('undefined_replicates'),
            'eligible': uncertainty.get('eligible')}
