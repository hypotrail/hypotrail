"""Spec L-15–L-17 / AC13–AC16: calibration discipline, risk control, split-conformal.

The oracles are independent implementations: Hoeffding–Bentkus p-values and the
Bonferroni–Holm step-down for risk control; the finite-sample residual quantile for the
intervals. The simulation has a fixed budget and an announced binomial tolerance; a
favourable simulation is not a universal proof.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

pytest.importorskip('mapie')

from scipy.stats import binom  # noqa: E402

from hypotrail_runtime.errors import ContractError  # noqa: E402
from mlkit.integrations import mapie_uncertainty as mu  # noqa: E402

THRESHOLDS = [round(0.05 * i, 2) for i in range(20)]


def _calibration(keys=('c1', 'c2', 'c3'), **changes):
    cal = {'id': 'calibration', 'role': 'calibration', 'keys': list(keys),
           'reserved_revision': 3, 'frozen_revision': 9, **changes}
    others = {'train': ['t1', 't2'], 'tuning': [], 'selection': ['s1'], 'final_test': ['f1']}
    return mu.eligibility(cal, other_partitions=others,
                          exposures=[{'purpose': 'reserved', 'row_keys': list(keys)}])


ELIGIBLE = _calibration()


def _uniform_scores(seed, n):
    rng = np.random.default_rng(seed)
    s = rng.uniform(size=n)
    y = (rng.uniform(size=n) < s).astype(int)      # P(y=1 | s) = s: precision(t) = (1+t)/2
    return s, y


# --- AC13 / AC15: eligibility, adaptive reuse ---------------------------------------------

def test_calibration_must_be_reserved_disjoint_and_unexplored():
    assert ELIGIBLE['eligible'] and ELIGIBLE['calibration_ref'].startswith('calibration@')
    assert not mu.eligibility(None, other_partitions={})['eligible']
    assert 'overlaps_final_test' in _calibration(keys=('c1', 'f1'))['reasons']
    assert 'overlaps_train' in _calibration(keys=('t1',))['reasons']
    late = _calibration(reserved_revision=12)
    assert 'not_reserved_before_the_model_was_frozen' in late['reasons']
    explored = mu.eligibility(
        {'id': 'c', 'role': 'calibration', 'keys': ['c1'], 'reserved_revision': 1,
         'frozen_revision': 2},
        other_partitions={}, exposures=[{'purpose': 'train_eda', 'row_keys': ['c1']}])
    assert explored['reasons'] == ['explored:train_eda']


def test_not_applicable_without_an_eligible_partition():
    s, y = _uniform_scores(1, 300)
    r = mu.control_precision(s, y, thresholds=THRESHOLDS, target_precision=.8,
                             confidence_level=.9, predictor_id=None,
                             calibration=mu.eligibility(None, other_partitions={}))
    assert r.status == 'not_applicable' and r.selected_threshold is None
    assert r.valid_thresholds is None


def test_adaptive_reuse_is_refused_and_exposure_is_kept(tmp_path):
    ledger = mu.CalibrationLedger(tmp_path / 'calibration.jsonl')
    proc = {'predictor_id': 'p' * 64, 'recipe_sha256': 'r' * 64, 'positive_label': 'yes',
            'rule_family': 'threshold', 'objective': 'precision>=0.8'}
    first = ledger.claim(ELIGIBLE['calibration_ref'], proc)
    assert ledger.claim(ELIGIBLE['calibration_ref'], proc) == first        # reproduction
    with pytest.raises(ContractError) as e:
        ledger.claim(ELIGIBLE['calibration_ref'], {**proc, 'objective': 'precision>=0.7'})
    assert e.value.code == 'calibration_not_eligible'
    assert len(ledger.uses()) == 1                       # the use stays recorded
    assert not mu.is_current(proc, predictor_id='q' * 64, recipe_sha256='r' * 64,
                             positive_label='yes', rule_family='threshold',
                             objective='precision>=0.8')


def test_top_k_and_share_rules_are_refused():
    s, y = _uniform_scores(1, 100)
    for rule in ('capacity:10', 'share:0.1', 'top_k:5'):
        with pytest.raises(ContractError) as e:
            mu.control_precision(s, y, thresholds=THRESHOLDS, target_precision=.8,
                                 confidence_level=.9, rule=rule, predictor_id=None,
                                 calibration=ELIGIBLE)
        assert e.value.code == 'capability_not_supported'


# --- AC14: deterministic oracle and the negative result -----------------------------------

def _hb_p_value(r_hat: float, n: int, alpha: float) -> float:
    """Hoeffding–Bentkus p-value for H0: risk > alpha (binary loss), independent code."""
    if n <= 0:
        return 1.0
    r = min(r_hat, alpha)

    def h1(a, b):
        left = 0.0 if a == 0 else a * math.log(a / b)
        return left + (1 - a) * math.log((1 - a) / (1 - b))
    hoeffding = math.exp(-n * h1(r, alpha))
    bentkus = binom.cdf(math.ceil(n * r_hat), n, alpha)
    return min(hoeffding, bentkus)


def _holm(p_values, delta):
    order = sorted(range(len(p_values)), key=lambda i: p_values[i])
    rejected = []
    for rank, i in enumerate(order):
        if p_values[i] <= delta / (len(p_values) - rank):
            rejected.append(i)
        else:
            break
    return sorted(rejected)


def test_admissible_thresholds_match_an_independent_learn_then_test():
    s, y = _uniform_scores(3, 400)
    target, conf = 0.8, 0.9
    r = mu.control_precision(s, y, thresholds=THRESHOLDS, target_precision=target,
                             confidence_level=conf, predictor_id='a' * 64,
                             calibration=ELIGIBLE)
    p = []
    for t in THRESHOLDS:
        sel = s >= t
        n = int(sel.sum())
        p.append(_hb_p_value(1 - y[sel].mean() if n else 1.0, n, 1 - target))
    expected = [THRESHOLDS[i] for i in _holm(p, 1 - conf)]
    assert r.status == 'ok'
    assert r.valid_thresholds == pytest.approx(expected)
    assert r.selected_threshold == min(expected)       # max_recall: the lowest admissible
    assert r.extensions['hypotrail.p_values'] == pytest.approx(p, rel=1e-9, abs=1e-12)
    assert r.risk_target == target and r.confidence_level == conf
    assert any('not a precision promised' in a for a in r.assumptions)


def test_no_admissible_threshold_is_a_negative_result_without_substitute():
    s, y = _uniform_scores(4, 60)                       # too few rows for 0.95 precision
    r = mu.control_precision(s, y, thresholds=THRESHOLDS, target_precision=.95,
                             confidence_level=.95, predictor_id=None, calibration=ELIGIBLE)
    assert r.status == 'insufficient_data' and r.reason == 'no_admissible_threshold'
    assert r.valid_thresholds == [] and r.selected_threshold is None
    one_class = mu.control_precision(s, np.zeros_like(y), thresholds=THRESHOLDS,
                                     target_precision=.5, confidence_level=.9,
                                     predictor_id=None, calibration=ELIGIBLE)
    assert one_class.status == 'insufficient_data' and one_class.selected_threshold is None


def test_the_procedure_rarely_certifies_a_bad_threshold():
    """Budget 200 calibrations of 300 rows; a certified threshold below 0.6 has true precision
    below 0.8. Allowed error rate: 0.10 plus three binomial standard errors."""
    errors, budget = 0, 200
    for seed in range(budget):
        s, y = _uniform_scores(1000 + seed, 300)
        r = mu.control_precision(s, y, thresholds=THRESHOLDS, target_precision=.8,
                                 confidence_level=.9, predictor_id=None, calibration=ELIGIBLE)
        if r.status == 'ok' and min(r.valid_thresholds) < 0.6 - 1e-9:
            errors += 1
    assert errors / budget <= 0.10 + 3 * math.sqrt(0.1 * 0.9 / budget)


# --- AC16: split-conformal intervals -------------------------------------------------------

def _regression(seed, n):
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, 1))
    return X, 2 * X[:, 0] + rng.normal(size=n)


def predict(X):
    return 2 * np.asarray(X)[:, 0]


def test_interval_half_width_is_the_finite_sample_residual_quantile():
    X, y = _regression(5, 49)
    X_new, y_new = _regression(6, 500)
    r = mu.split_conformal(predict, X, y, X_new, confidence_level=.9, predictor_id=None,
                           calibration=ELIGIBLE, y_new=y_new, groups=X_new[:, 0] > 0)
    residuals = np.sort(np.abs(y - predict(X)))
    k = math.ceil((49 + 1) * .9)                        # rank 45 of 49
    half = residuals[k - 1]
    widths = {round(b.high - b.low, 10) for b in r.interval_bounds}
    assert widths == {round(2 * half, 10)}
    assert r.status == 'ok' and r.coverage_level == .9
    cov = r.extensions['hypotrail.empirical_coverage']
    assert 0.8 <= cov <= 0.98                            # empirical, descriptive
    assert set(r.extensions['hypotrail.subgroup_coverage_descriptive']) == {'False', 'True'}
    assert any('marginal' in a for a in r.assumptions)


def test_too_few_calibration_rows_is_insufficient_not_infinite():
    X, y = _regression(7, 8)
    r = mu.split_conformal(predict, X, y, X[:2], confidence_level=.95, predictor_id=None,
                           calibration=ELIGIBLE)
    assert r.status == 'insufficient_data' and r.interval_bounds is None
    assert mu.finite_sample_rank(8, .95) == 9


def test_the_fixed_model_is_never_refitted_and_export_is_refused():
    X, y = _regression(8, 40)
    r = mu.split_conformal(predict, X, y, X[:3], confidence_level=.8, predictor_id=None,
                           calibration=ELIGIBLE)
    assert r.status == 'ok'
    with pytest.raises(ContractError) as e:
        mu.require_exportable('split_conformal')
    assert e.value.code == 'capability_not_supported'
