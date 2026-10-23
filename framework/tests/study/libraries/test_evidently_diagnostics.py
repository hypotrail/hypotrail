"""Spec L-13/L-14 / AC12: the eight synthetic scenarios of the diagnostics profile.

Fixed seeds; each scenario states what the univariate test can and cannot see. The thresholds
are the demonstration profile's (KS / chi-square p < 0.05 with Holm, 5 % shares).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

pytest.importorskip('evidently')

from hypotrail_runtime.errors import ContractError  # noqa: E402
from mlkit.integrations import evidently_diagnostics as ed  # noqa: E402

AUTH = ('development', 'monitoring')


def _run(ref, cur, columns, **kw):
    labels = kw.pop('labels', None)
    profile = ed.demonstration_profile(columns, **kw)
    return ed.run(profile, ref, cur, reference_partition='development',
                  current_partition='monitoring', authorized=AUTH, labels=labels)['result']


def _check(result, check_id):
    return next(c for c in result.checks if c.id == check_id)


def _normal(seed, n=1000, loc=0.0):
    return np.random.default_rng(seed).normal(loc, 1.0, n)


def test_1_mean_shift_is_alerted_by_the_marginal_test():
    r = _run(pd.DataFrame({'x': _normal(1)}), pd.DataFrame({'x': _normal(2, loc=0.5)}),
             {'x': 'numerical'})
    c = _check(r, 'ks:x')
    assert c.status == 'ok' and c.alert is True and c.comparison == 'lt'
    assert c.adjusted_p_value >= c.p_value and r.alert is True


def test_2_missing_share_change_is_reported_apart_from_the_distribution():
    cur = _normal(4)
    cur[:200] = np.nan
    r = _run(pd.DataFrame({'x': _normal(3)}), pd.DataFrame({'x': cur}), {'x': 'numerical'})
    miss = _check(r, 'missing_share:x')
    assert miss.alert is True and miss.statistic_value == pytest.approx(0.2)
    ks = _check(r, 'ks:x')
    assert ks.n_current == 800 and ks.alert is False        # NA excluded, same distribution


def test_3_unknown_category_is_a_data_quality_alert():
    rng = np.random.default_rng(5)
    ref = pd.DataFrame({'c': rng.choice(['a', 'b'], 1000)})
    cur = pd.DataFrame({'c': rng.choice(['a', 'b', 'z'], 1000, p=[.45, .45, .1])})
    r = _run(ref, cur, {'c': 'categorical'})
    unknown = _check(r, 'unknown_categories:c')
    assert unknown.alert is True and unknown.statistic_value == pytest.approx(0.1, abs=0.03)


def test_4_constant_column():
    same = _run(pd.DataFrame({'k': np.ones(500)}), pd.DataFrame({'k': np.ones(500)}),
                {'k': 'numerical'})
    assert _check(same, 'ks:k').alert is False
    moved = _run(pd.DataFrame({'k': np.ones(500)}), pd.DataFrame({'k': _normal(6, 500)}),
                 {'k': 'numerical'})
    assert _check(moved, 'ks:k').alert is True
    rel = _run(pd.DataFrame({'k': np.ones(500), 'x': _normal(7, 500)}),
               pd.DataFrame({'k': np.ones(500), 'x': _normal(8, 500)}),
               {'k': 'numerical', 'x': 'numerical'}, relationships=[('k', 'x')])
    assert _check(rel, 'pearson:k~x').status == 'insufficient_data'


def test_5_an_empty_column_is_not_a_quiet_column():
    r = _run(pd.DataFrame({'x': _normal(9)}), pd.DataFrame({'x': np.full(1000, np.nan)}),
             {'x': 'numerical'})
    ks = _check(r, 'ks:x')
    assert ks.status == 'insufficient_data' and ks.alert is None
    assert _check(r, 'missing_share:x').alert is True
    assert r.alert is True


def test_6_one_more_row_does_not_change_the_method():
    a = _run(pd.DataFrame({'x': _normal(10)}), pd.DataFrame({'x': _normal(11)}),
             {'x': 'numerical'})
    b = _run(pd.DataFrame({'x': _normal(10)}), pd.DataFrame({'x': _normal(11, 1001)}),
             {'x': 'numerical'})
    ca, cb = _check(a, 'ks:x'), _check(b, 'ks:x')
    assert (ca.statistic_name, ca.threshold, ca.comparison) == \
        (cb.statistic_name, cb.threshold, cb.comparison)
    assert a.method.parameters == b.method.parameters
    assert (ca.n_current, cb.n_current) == (1000, 1001)


def _pair(seed, rho, n=1000):
    cov = [[1, rho], [rho, 1]]
    xy = np.random.default_rng(seed).multivariate_normal([0, 0], cov, n)
    return pd.DataFrame({'x': xy[:, 0], 'y': xy[:, 1]})


def test_7_inverted_correlation_with_unchanged_margins():
    r = _run(_pair(12, 0.8), _pair(13, -0.8), {'x': 'numerical', 'y': 'numerical'},
             relationships=[('x', 'y')])
    assert _check(r, 'ks:x').alert is False and _check(r, 'ks:y').alert is False
    rel = _check(r, 'pearson:x~y')
    assert rel.alert is True and rel.effect_size < -1.0     # the marginals could not see it


def test_8_inverted_target_relation_shows_only_through_labelled_performance():
    x_ref, x_cur = _normal(14), _normal(15)
    noise = np.random.default_rng(16).normal(0, .3, 1000)
    y_ref, y_cur = x_ref + noise, -x_cur + noise
    ref, cur = pd.DataFrame({'x': x_ref}), pd.DataFrame({'x': x_cur})
    blind = _run(ref, cur, {'x': 'numerical'}, performance='mae')
    assert _check(blind, 'ks:x').alert is False
    assert _check(blind, 'performance:mae').status == 'not_applicable'
    seen = _run(ref, cur, {'x': 'numerical'}, performance='mae',
                labels={'reference': (y_ref, x_ref), 'current': (y_cur, x_cur)})
    perf = _check(seen, 'performance:mae')
    assert perf.alert is True and perf.statistic_value > 1.0


def test_backend_exception_is_failed_with_null_alert(monkeypatch):
    import evidently.metrics as m

    class Broken:
        def __init__(self, **kw):
            raise RuntimeError('backend exploded')
    monkeypatch.setattr(m, 'ValueDrift', Broken)
    r = _run(pd.DataFrame({'x': _normal(1)}), pd.DataFrame({'x': _normal(2)}),
             {'x': 'numerical'})
    ks = _check(r, 'ks:x')
    assert ks.status == 'failed' and ks.alert is None and 'backend exploded' in ks.reason
    assert r.alert is None                                 # never "no alert"


def test_unauthorised_population_and_inconsistent_profile_are_refused():
    with pytest.raises(ContractError) as e:
        ed.run(ed.demonstration_profile({'x': 'numerical'}), pd.DataFrame({'x': [1.0]}),
               pd.DataFrame({'x': [1.0]}), reference_partition='development',
               current_partition='final_test', authorized=AUTH)
    assert e.value.code == 'partition_not_authorized'
    bad = ed.demonstration_profile({'x': 'numerical'}).model_dump(mode='json')
    bad['columns']['x']['statistic'] = 'distance'
    with pytest.raises(ContractError):
        ed.profile_of(bad)


def test_holm_adjustment_is_monotone_and_bounded():
    adj = ed.holm([0.01, 0.04, 0.03, 0.5])
    assert adj == pytest.approx([0.04, 0.09, 0.09, 0.5])
