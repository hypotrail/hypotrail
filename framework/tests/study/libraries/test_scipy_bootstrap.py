"""Spec L-11/L-12 / AC10, AC11: the SciPy paired percentile bootstrap against an exact oracle.

The oracle enumerates every resample of a tiny sample (n**n equally likely position tuples)
and gives the exact bootstrap distribution of the contrast. Both backends are compared to
it with a Dvoretzky–Kiefer–Wolfowitz bound on their empirical distribution; no test assumes
that two generators with the same seed draw the same resamples.
"""
from __future__ import annotations

import itertools
import math

import numpy as np
import pytest

from mlkit.integrations import scipy_bootstrap as sb
from mlkit.study import objective

Y = [3.0, 7.0, 4.0]
REF = [5.0, 5.0, 5.0]                  # a constant reference
CAND = [3.5, 6.0, 4.5]


def mae(yy, pp):
    return objective.evaluate_regression(yy, pp)


def _exact_delta_distribution(y, ref, cand):
    n = len(y)
    out = []
    for pos in itertools.product(range(n), repeat=n):
        yy = [y[i] for i in pos]
        a = mae(yy, [ref[i] for i in pos])['point']
        b = mae(yy, [cand[i] for i in pos])['point']
        out.append(b - a)
    return np.sort(np.array(out))


def _dkw(sample, exact, alpha=1e-6) -> None:
    sample = np.sort(np.asarray(sample))
    grid = np.unique(exact)
    emp = np.searchsorted(sample, grid, side='right') / len(sample)
    ref = np.searchsorted(exact, grid, side='right') / len(exact)
    eps = math.sqrt(math.log(2 / alpha) / (2 * len(sample)))
    assert np.max(np.abs(emp - ref)) <= eps


def test_the_method_is_explicit():
    out = sb.paired_bootstrap(Y, {'baseline': REF, 'model': CAND}, mae, replicates=200,
                              seed=4, level=0.9, direction='minimize', unit='mpg')
    u = out['uncertainty']
    assert (u['paired'], u['interval'], u['resampling_unit']) == (True, 'percentile', 'row')
    assert u['generator'].startswith('numpy.random.default_rng')
    assert u['gain'] == 'model - baseline' and u['direction'] == 'minimize'
    assert set(u['versions']) == {'scipy', 'numpy'} and u['seed'] == 4
    assert out['status'] == 'ok' and u['eligible'] and u['undefined_replicates'] == 0


def test_interval_is_the_direct_linear_quantile_of_its_own_resamples():
    out = sb.paired_bootstrap(Y, {'baseline': REF, 'model': CAND}, mae, replicates=999,
                              seed=7, level=0.8, direction='minimize')
    dist = out['distribution'][2]
    low, high = np.percentile(dist, [10, 90])          # numpy linear interpolation
    assert out['delta']['low'] == pytest.approx(low, abs=1e-12)
    assert out['delta']['high'] == pytest.approx(high, abs=1e-12)
    # Every resampled contrast is a value the exact enumeration can produce.
    exact = _exact_delta_distribution(Y, REF, CAND)
    assert np.all(np.isclose(dist[:, None], np.unique(exact)[None, :]).any(axis=1))


def test_both_backends_estimate_the_exact_bootstrap_distribution():
    exact = _exact_delta_distribution(Y, REF, CAND)
    B = 4000
    scipy_out = sb.paired_bootstrap(Y, {'baseline': REF, 'model': CAND}, mae, replicates=B,
                                    seed=11, level=0.9, direction='minimize')
    _dkw(scipy_out['distribution'][2], exact)
    # The historical generator, studied through its own draws (same positions logic).
    import random
    rng = random.Random(11)
    legacy = []
    for _ in range(B):
        pos = [rng.randrange(3) for _ in range(3)]
        yy = [Y[i] for i in pos]
        legacy.append(mae(yy, [CAND[i] for i in pos])['point']
                      - mae(yy, [REF[i] for i in pos])['point'])
    _dkw(legacy, exact)
    hist = objective.paired_row_bootstrap(Y, {'baseline': REF, 'model': CAND}, mae,
                                          replicates=B, seed=11, level=0.9)
    lo_q, hi_q = np.quantile(exact, [0.03, 0.97])           # generous exact bracket
    for low, high in ((scipy_out['delta']['low'], scipy_out['delta']['high']),
                      (hist['delta_intervals']['model']['low'],
                       hist['delta_intervals']['model']['high'])):
        assert lo_q - 1e-12 <= low <= high <= hi_q + 1e-12


def test_an_undefined_replicate_invalidates_the_interval_without_dropping_it():
    y = [1, 0, 0]

    def precision_at_one(yy, pp):          # undefined when nothing is selected
        sel = [t for t, p in zip(yy, pp) if p >= 0.5]
        return {'point': None if not sel else sum(sel) / len(sel)}
    out = sb.paired_bootstrap(y, {'baseline': [0.2, 0.2, 0.2], 'model': [0.9, 0.1, 0.6]},
                              precision_at_one, replicates=300, seed=3)
    assert out['status'] == 'insufficient_data'
    assert out['uncertainty']['undefined_replicates'] > 0
    assert out['delta']['low'] is None and out['delta']['high'] is None
    # The historical backend applies the same policy.
    hist = objective.paired_row_bootstrap(y, {'baseline': [0.2] * 3, 'model': [0.9, .1, .6]},
                                          precision_at_one, replicates=300, seed=3)
    assert hist['uncertainty']['eligible'] is False


def test_perfect_and_constant_references_keep_aligned_outputs():
    out = sb.paired_bootstrap(Y, {'perfect': list(Y), 'model': CAND}, mae, replicates=300,
                              seed=1, direction='minimize')
    assert out['point']['perfect'] == 0.0
    assert out['intervals']['perfect'] == {'low': 0.0, 'high': 0.0}
    assert out['delta']['low'] >= 0                           # the model never beats it


def test_dependence_and_tiny_samples_are_named_not_computed():
    out = sb.paired_bootstrap(Y, {'a': REF, 'b': CAND}, mae, replicates=50, seed=1,
                              dependence='temporal')
    assert out['status'] == 'not_applicable' and out['delta']['low'] is None
    out = sb.paired_bootstrap([1.0], {'a': [0.0], 'b': [1.0]}, mae, replicates=50, seed=1)
    assert out['status'] == 'insufficient_data'
    assert sb.CAPABILITIES['single_row']['scipy'].startswith('insufficient_data')


def test_a_backend_exception_is_failed_with_its_cause():
    def broken(yy, pp):
        raise RuntimeError('boom')
    with pytest.raises(RuntimeError):
        broken([], [])
    out = sb.paired_bootstrap(Y, {'a': REF, 'b': CAND},
                              lambda yy, pp: (_ for _ in ()).throw(RuntimeError('boom'))
                              if len(set(yy)) == 1 else mae(yy, pp),
                              replicates=200, seed=2)
    assert out['status'] == 'failed' and 'boom' in out['reason']
