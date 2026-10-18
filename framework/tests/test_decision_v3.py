"""Decision rule v3: margin rule, monthly-block holdout CI, Nadeau-Bengio, stress windows,
Holm, and non-evaluable segments. Pure functions, a few seconds.

    OMP_NUM_THREADS=1 python -m pytest -q tests/test_decision_v3.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy import stats

KIT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).resolve().parent / "fixtures/legacy-project"
sys.path.insert(0, str(KIT))
from mlkit import config, core, decision, evaluate  # noqa: E402

RATE = 0.9


# ---------------------------------------------------------------- 1. acceptance rule
def test_rule_defaults_and_validation():
    assert decision.acceptance_rule({"acceptance": {}}) == "expected_value"          # old frames: v2 behaviour
    assert decision.acceptance_rule({"acceptance": {"rule": "margin"}}) == "margin"
    with pytest.raises(SystemExit):
        decision.acceptance_rule({"acceptance": {"rule": "optimiste"}})
    template = config.load_yaml(FIXTURE / "frame.yaml")["spec"]
    assert decision.acceptance_rule(template) == "expected_value"   # bench: maximises expected value; margin is opt-in


def test_margin_vs_expected_value_at_the_threshold():
    """True gain = δ: expected_value accepts about half the time, margin about (1 - ci_level)."""
    delta, se = 0.002, 0.0004
    rng = np.random.default_rng(0)
    g = rng.normal(delta, se, 20000)
    ev = np.mean([decision.holdout_gate(x, se, delta, 0.9, "expected_value")["pass"] for x in g])
    mg = np.mean([decision.holdout_gate(x, se, delta, 0.9, "margin")["pass"] for x in g])
    assert 0.47 < ev < 0.53
    assert 0.08 < mg < 0.12
    big = decision.holdout_gate(delta + 4 * se, se, delta, 0.9, "margin")
    assert big["pass"] and big["lower_one_sided"] > delta
    # legacy call (bench, v2 ledgers) unchanged
    assert decision.holdout_gate(0.003, 0.001, 0.002, 0.9)["pass"] is True


def test_required_gain_for_80_percent_power():
    need = decision.required_gain(0.002, 0.0004, 0.9)
    assert abs(need - (0.002 + (stats.norm.ppf(0.9) + stats.norm.ppf(0.8)) * 0.0004)) < 1e-12
    rng = np.random.default_rng(1)
    acc = np.mean([decision.holdout_gate(x, 0.0004, 0.002, 0.9, "margin")["pass"] for x in rng.normal(need, 0.0004, 20000)])
    assert 0.78 < acc < 0.82


def test_rule_is_in_the_frozen_fingerprint(tmp_path, monkeypatch):
    """An explicit expected_value keeps the fingerprint of a frame without the field; margin changes it."""
    monkeypatch.setattr(config, "ROOT", tmp_path)
    base = {"acceptance": {"ci_level": 0.9, "min_gain": 0.002}, "evaluation": {"decision_rate": 0.9}}
    first = evaluate.rule_status(base)
    explicit = evaluate.rule_status({**base, "acceptance": {**base["acceptance"], "rule": "expected_value"}})
    margin = evaluate.rule_status({**base, "acceptance": {**base["acceptance"], "rule": "margin"}})
    assert first["ok"] and explicit["ok"] and explicit["hash"] == first["hash"]
    assert not margin["ok"] and margin["hash"] != first["hash"] and "DECISION-RULE" in margin["reason"]


# ---------------------------------------------------------------- 2. holdout CI by monthly blocks
def _shocked(rng, months, n, gam=0.6, sg=0.6, su=0.3):
    """Loans of a month share a level shock u and a strength g of the hidden information."""
    z, h = rng.normal(size=(months, n)), rng.normal(size=(months, n))
    u, g = rng.normal(0, su, (months, 1)), gam * np.exp(rng.normal(0, sg, (months, 1)))
    p = 1 / (1 + np.exp(-(-2 + u + 0.8 * z + g * h)))
    return z, h, p


def _true_gain(gam=0.6, sg=0.6, su=0.3):
    """Expected gain over NEW months (the deployment question), not conditional on the months drawn."""
    rng = np.random.default_rng(99)
    z, h = rng.normal(size=30000), rng.normal(size=30000)
    wr, wc = decision.accept_weights(z, RATE), decision.accept_weights(0.8 * z + gam * h, RATE)
    a = wr / wr.sum() - wc / wc.sum()
    u, g = rng.normal(0, su, (2000, 1)), gam * np.exp(rng.normal(0, sg, (2000, 1)))
    return float(np.concatenate([(1 / (1 + np.exp(-(-2 + u[k:k + 250] + 0.8 * z + g[k:k + 250] * h)))) @ a
                                 for k in range(0, 2000, 250)]).mean())


def test_block_bootstrap_equals_explicit_resampling():
    rng = np.random.default_rng(1)
    n, G = 4000, 6
    blk = rng.integers(0, G, n)
    y = (rng.random(n) < 0.15).astype(float)
    s_ref, s_cand = rng.integers(0, 35, n).astype(float), np.round(rng.random(n), 2)   # ties on both scores
    C = rng.multinomial(G, np.full(G, 1 / G), size=15).T.astype(float)
    nr, br = decision._tie_tables(s_ref, y, blk, G, RATE)
    nc, bc = decision._tie_tables(s_cand, y, blk, G, RATE)
    fast = decision._bad_rates(nr, br, C, RATE) - decision._bad_rates(nc, bc, C, RATE)
    slow = []
    for j in range(C.shape[1]):
        idx = np.concatenate([np.flatnonzero(blk == b) for b in range(G) for _ in range(int(C[b, j]))])
        slow.append(decision.gain(y[idx], s_ref[idx], s_cand[idx], RATE)[0])
    assert np.abs(fast - np.array(slow)).max() < 1e-12
    bb = decision.block_bootstrap(y, s_ref, s_cand, blk, RATE)
    assert bb["exact"] and bb["B"] == 462 and bb["df"] == 5                 # C(11, 6) distinct resamples
    m12 = rng.integers(0, 12, n)
    bb12 = decision.block_bootstrap(y, s_ref, s_cand, m12, RATE, B=500, seed=3)
    assert not bb12["exact"] and bb12["B"] == 500 and bb12["df"] == 11
    assert bb12["se"] == decision.block_bootstrap(y, s_ref, s_cand, m12, RATE, B=500, seed=3)["se"]   # fixed seed


def test_block_ci_covers_under_monthly_shocks_linearisation_does_not():
    truth = _true_gain()
    rng = np.random.default_rng(0)
    cov_lin = cov_blk = 0
    R = 200
    for r in range(R):
        z, h, p = _shocked(rng, 6, 1500)
        y = (rng.random(p.shape) < p).astype(float).ravel()
        d = decision.holdout_decision(y, z.ravel(), (0.8 * z + 0.6 * h).ravel(), np.repeat(np.arange(6), 1500),
                                      RATE, 0.0, 0.9, B=2000, seed=r)
        assert d["method"] == "block_bootstrap" and not d["warning"]
        lo, hi = d["linearisation"]["ci"]
        cov_lin += lo <= truth <= hi
        lo, hi = d["block_bootstrap"]["gate"]["ci"]
        cov_blk += lo <= truth <= hi
    cov_lin, cov_blk = cov_lin / R, cov_blk / R
    assert 0.84 <= cov_blk <= 0.96, cov_blk            # nominal 90 %
    assert cov_lin < 0.75, cov_lin                       # independence between loans: far too narrow


def test_without_shocks_both_intervals_cover():
    truth = _true_gain(sg=0.0, su=0.0)
    rng = np.random.default_rng(5)
    cov = np.zeros(2)
    for r in range(120):
        z, h, p = _shocked(rng, 6, 1500, sg=0.0, su=0.0)
        y = (rng.random(p.shape) < p).astype(float).ravel()
        d = decision.holdout_decision(y, z.ravel(), (0.8 * z + 0.6 * h).ravel(), np.repeat(np.arange(6), 1500), RATE, 0.0, 0.9)
        cov += [d["linearisation"]["ci"][0] <= truth <= d["linearisation"]["ci"][1],
                d["block_bootstrap"]["gate"]["ci"][0] <= truth <= d["block_bootstrap"]["gate"]["ci"][1]]
    assert (cov / 120 > 0.82).all(), cov / 120


def test_few_months_fall_back_to_linearisation_with_warning():
    rng = np.random.default_rng(2)
    z, h, p = _shocked(rng, 4, 2000)
    y = (rng.random(p.shape) < p).astype(float).ravel()
    d = decision.holdout_decision(y, z.ravel(), (0.8 * z + 0.6 * h).ravel(), np.repeat(np.arange(4), 2000), RATE, 0.002, 0.9, "margin")
    assert d["method"] == "linearisation" and "4 months" in d["warning"]
    assert d["block_bootstrap"]["gate"] is not None                       # still shown
    assert d["pass"] == d["linearisation"]["pass"] and d["rule"] == "margin"


# ---------------------------------------------------------------- 3. backtest: Nadeau-Bengio, worst window, stress
def test_nadeau_bengio_widens_the_bound():
    wg = np.array([0.0030, 0.0018, 0.0025, 0.0012])
    naive = decision.backtest_gate(wg, 0.95)
    nb = decision.backtest_gate(wg, 0.95, n_train=[10000, 15000, 20000, 25000], n_test=[5000] * 4, correction="nadeau_bengio")
    ratio = np.mean([0.5, 1 / 3, 0.25, 0.2])
    t = stats.t.ppf(0.95, 3)
    assert abs(nb["lower"] - (wg.mean() - t * wg.std(ddof=1) * np.sqrt(1 / 4 + ratio))) < 1e-12
    assert nb["lower"] < naive["lower"] and nb["lower_naive"] == naive["lower"]
    assert naive["correction"] == "none" and nb["correction"] == "nadeau_bengio"
    assert nb["worst_gain"] == 0.0012 and nb["n_negative"] == 0
    flip = decision.backtest_gate(np.array([0.002, 0.0005, 0.0015]), 0.95, n_train=[1e4] * 3, n_test=[4e4] * 3, correction="nadeau_bengio")
    assert flip["lower_naive"] > 0 and not flip["pass"] and "Nadeau-Bengio" in flip["reason"]
    off = decision.backtest_gate(np.array([0.002, 0.0005, 0.0015]), 0.95, n_train=[1e4] * 3, n_test=[4e4] * 3, correction="none")
    assert off["pass"]


def test_nadeau_bengio_warns_when_the_ratio_is_large():
    """exp. 2: the implied correlation r/(1+r) is ~0.1 measured; above n_test/n_train = 0.5 the correction is
    far too strong (r = 5 with a capped training set: -163 k€/project). Warn, never silently."""
    wg = np.array([0.002, 0.0015, 0.0025, 0.0018])
    small = decision.backtest_gate(wg, 0.95, n_train=[4e4] * 4, n_test=[8e3] * 4, correction="nadeau_bengio")
    assert small["correction"] == "nadeau_bengio" and "warning" not in small
    big = decision.backtest_gate(wg, 0.95, n_train=[1e4] * 4, n_test=[5e4] * 4, correction="nadeau_bengio")
    assert big["test_train_ratio"] == 5.0 and "n_test/n_train = 5.00" in big["warning"] and "0.83" in big["warning"]
    blind = decision.backtest_gate(wg, 0.95, correction="nadeau_bengio")         # sizes unknown: no silent fallback
    assert blind["correction"] == "none" and "inconnus" in blind["warning"]
    with pytest.raises(SystemExit):
        decision.backtest_gate(wg, 0.95, correction="bonferroni")


def test_months_correction_uses_the_monthly_gains_of_all_windows():
    """backtest_correction: months — t on the volume-weighted monthly gains, months - 1 df (exp. 2). One crisis
    window among four: the window t (3 df) refuses, the monthly t (23 df) keeps the power."""
    rng = np.random.default_rng(3)
    mg = np.r_[rng.normal(0.004, 0.002, 18), rng.normal(-0.002, 0.002, 6)]     # 4 windows x 6 months, the last a crisis
    ms = rng.integers(800, 1200, 24).astype(float)
    wg = np.array([np.average(mg[i * 6:(i + 1) * 6], weights=ms[i * 6:(i + 1) * 6]) for i in range(4)])
    none = decision.backtest_gate(wg, 0.95, monthly=(mg, ms), correction="none")
    months = decision.backtest_gate(wg, 0.95, monthly=(mg, ms), correction="months")
    w = ms / ms.sum()
    m = float((w * mg).sum())
    sd = float(np.sqrt((w * (mg - m) ** 2).sum() * 24 / 23))
    assert abs(months["lower"] - (m - stats.t.ppf(0.95, 23) * sd / np.sqrt(24))) < 1e-12
    assert months["correction"] == "months" and months["lower_naive"] == none["lower"]
    assert months["pass"] and not none["pass"]
    assert "warning" not in months
    # a candidate with no gain is still refused: same size as the window t
    flat = decision.backtest_gate(wg * 0, 0.95, monthly=(mg * 0 + rng.normal(0, 0.002, 24) - 0.001, ms), correction="months")
    assert not flat["pass"] and "gains monthly" in flat["reason"]
    # fewer than 6 test months: window t, with a warning (never a silent fallback)
    few = decision.backtest_gate(wg, 0.95, monthly=(mg[:4], ms[:4]), correction="months")
    assert few["correction"] == "none" and few["correction_requested"] == "months" and "4 months" in few["warning"]


def test_months_is_the_template_default_and_absent_field_keeps_none():
    """PATCH exp. 2: new frames (the template) declare months; a frame without the field keeps none."""
    import yaml
    frame = yaml.safe_load((FIXTURE / "frame.yaml").read_text(encoding="utf-8"))
    assert frame["spec"]["evaluation"]["backtest_correction"] == "months"
    src = (KIT / "mlkit" / "evaluate.py").read_text(encoding="utf-8")
    assert 'ev.get("backtest_correction", "none")' in src


def test_stress_windows_are_judged_on_their_own_gain():
    names = ["2014-01..2014-06", "2014-07..2014-12", "2015-01..2015-06", "2009-01..2009-06"]
    wg = np.array([0.004, 0.0035, 0.0045, -0.008])
    g = decision.backtest_gate(wg, 0.95, names=names, stress=["2009-01..2009-06"], stress_margin=0.005)
    assert not g["pass"] and not g["stress"]["pass"] and "stress 2009-01..2009-06" in g["reason"]
    assert g["worst_window"] == "2009-01..2009-06" and g["n_negative"] == 1
    ok = decision.backtest_gate(wg, 0.95, names=names, stress=["2009-01..2009-06"], stress_margin=0.01)
    assert ok["stress"]["pass"]
    missing = decision.backtest_gate(wg[:3], 0.95, names=names[:3], stress=["2009-01..2009-06"])
    assert not missing["pass"] and "missing" in missing["reason"]
    spec = {"backtest": {"gap_months": 36, "test_windows": [["2014-01", "2014-06"], ["2014-07", "2014-12"]],
                         "stress_windows": [["2014-07", "2014-12"], ["2012-01", "2012-06"]]}}
    assert [w[0] for w in core.windows(spec)] == ["2014-01..2014-06", "2014-07..2014-12", "2012-01..2012-06"]
    assert [w[0] for w in core.windows(spec, stress=False)] == ["2014-01..2014-06", "2014-07..2014-12"]
    assert core.stress_names(spec) == ["2014-07..2014-12", "2012-01..2012-06"]


# 4. Segments: Holm and non-evaluable cases.
def _segments(rng, n=40000):
    s_ref = rng.random(n)
    y = (rng.random(n) < 0.05 + 0.25 * s_ref).astype(float)
    return y, s_ref


def test_holm_is_stricter_than_per_segment_bounds():
    """Five segments each just non-inferior at 95 % one-sided: without correction all pass, Holm fails some."""
    rng = np.random.default_rng(4)
    y, s_ref = _segments(rng)
    seg = rng.integers(0, 5, len(y))
    masks = {f"s{k}": seg == k for k in range(5)}
    # same through the gate: candidate = reference perturbed, margin tuned so p ≈ 0.03 per segment
    s_c = np.where(rng.random(len(y)) < 0.3, rng.random(len(y)), s_ref)
    raw = decision.segment_gate(y, s_ref, s_c, np.zeros(len(y)), masks, RATE, 0.0, 0.95, multiplicity="none")
    m = float(np.median([stats.norm.ppf(0.97) * r["se"] - r["gain"] for r in raw["segments"]]))
    none = decision.segment_gate(y, s_ref, s_c, np.zeros(len(y)), masks, RATE, m, 0.95, multiplicity="none")
    holm = decision.segment_gate(y, s_ref, s_c, np.zeros(len(y)), masks, RATE, m, 0.95, multiplicity="holm")
    n_none = sum(r["pass"] for r in none["segments"])
    n_holm = sum(r["pass"] for r in holm["segments"])
    assert n_holm < n_none and holm["multiplicity"] == "holm"
    levels = sorted(r["level_used"] for r in holm["segments"])
    assert abs(levels[-1] - (1 - 0.05 / 5)) < 1e-12 and abs(levels[0] - 0.95) < 1e-12   # α/5 ... α/1


def test_unevaluable_segments_are_listed_not_nan():
    rng = np.random.default_rng(6)
    y, s_ref = _segments(rng, 20000)
    s_cand = s_ref + rng.normal(0, 0.05, len(y))
    worst = s_ref > np.quantile(s_ref, 0.95)                # the reference refuses every one of them
    small = rng.random(len(y)) < 0.01
    masks = {"rejected by the reference": worst, "small": small, "all": np.ones(len(y), bool)}
    g = decision.segment_gate(y, s_ref, s_cand, np.zeros(len(y)), masks, RATE, 0.005, 0.95, min_size=500)
    rows = {r["segment"]: r for r in g["segments"]}
    assert not rows["rejected by the reference"]["evaluable"] and "the reference accepts nobody" in rows["rejected by the reference"]["why"]
    assert not rows["small"]["evaluable"] and "taille minimum" in rows["small"]["why"]
    assert rows["all"]["evaluable"] and rows["all"]["level_used"] == 0.95          # k = 1 evaluable: no correction
    assert g["pass"] and len(g["unevaluable"]) == 2
    assert "nan" not in json.dumps(g, default=str).lower()
    strict = decision.segment_gate(y, s_ref, s_cand, np.zeros(len(y)), masks, RATE, 0.005, 0.95, min_size=500, unevaluable="fail")
    assert not strict["pass"] and "not evaluable" in strict["reason"]
