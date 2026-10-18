"""Decision rule v2: when is a candidate accepted? Pure functions, used by mlkit.evaluate,
mlkit.holdout, mlkit.mde AND by the decision bench (bench/banc_decision.py), so the rule the
bench measures is the rule the kit applies.

Why v2 (bench of 1 600 simulated projects, XP1): the v1 rule (no negative segment among all
segments, calibration error < 0.02) accepted 0 % of genuinely good models. Calibration failed
every time because default rates drift over the 36-month gap; « no negative segment » failed
by chance on small segments. v2, on the same bench: 0 % accepted at zero true gain, 99.5 % at
twice the threshold.

The rule, in the order it is applied:
  1. backtest   : the gain is computed in each test WINDOW (the model is re-fitted per window,
                  so the window is the independent unit — months of one window share a model
                  and are correlated); one-sided lower bound (Student t, windows - 1 degrees of
                  freedom) of the mean window gain must be > 0. Monthly gains are shown, weighted
                  by volume, for information (and a prediction bound for the next month).
  2. segments   : non-inferiority on segments written in the frame BEFORE the results: no
                  segment loses more than `margin`, with one-sided confidence `level`. All must
                  pass (intersection-union), so no multiplicity correction is needed.
  3. calibration: blocks only when the score is used as a probability (decision_use).
  4. holdout    : one reading; gain >= min_gain and lower bound of the CI > 0.
Informative, never blocking: prediction interval for the next month, calibration (ranking use).

Gains use the kit metric: acceptance at `rate`, ties at the cut-off taken pro rata. Standard
errors come from the paired linearisation of that metric (same loans for both scores), checked
against a real bootstrap in the bench.

v3 (literature review, R1):
  - acceptance.rule: expected_value (gain >= min_gain and two-sided lower bound > 0; maximises the
    expected value under a linear, risk-neutral utility, but accepts ~50 % of models whose true gain
    is exactly min_gain) | margin (one-sided lower bound at ci_level > min_gain: superiority with a
    margin). Frames without the field keep expected_value; new frames (template) declare margin.
  - holdout CI: paired bootstrap by MONTHLY blocks (loans of one month share shocks), beside the
    linearisation; the decision uses the blocks when there are >= 6 months.
  - backtest: evaluation.backtest_correction = none (frame without the field: t on the window gains) |
    months (template default since exp. 2: t on the monthly gains of all windows, >= 6 months) |
    nadeau_bengio (training sets of the windows overlap; valid only with the REAL n_test/n_train of each
    window, warning when > 0.5); worst window, number of negative windows; pre-registered stress windows
    judged on their own gain (> -stress_margin).
  - segments: Holm over the evaluable segments; a segment under min_size, or where one score accepts
    nobody, is « not evaluable » (listed, never nan); `unevaluable: fail` makes it block E1.
"""
from __future__ import annotations

import itertools
import math

import numpy as np
from scipy import stats

RULES = ("expected_value", "margin")
MIN_BLOCKS = 6            # below, the block bootstrap has too few blocks: linearisation, with a warning


def acceptance_rule(spec: dict) -> str:
    """Declared acceptance rule; a frame without the field keeps the v2 behaviour (expected_value)."""
    rule = str((spec.get("acceptance") or {}).get("rule", "expected_value"))
    if rule not in RULES:
        raise SystemExit(f"acceptance.rule = {rule!r} : values admises {', '.join(RULES)}")
    return rule


# ---------------------------------------------------------------- metric pieces
def accept_weights(score, rate: float) -> np.ndarray:
    """1 accepted, 0 refused, a fraction for the tied group at the cut-off (low score = low risk)."""
    s = np.asarray(score, dtype=float)
    vals, inv = np.unique(s, return_inverse=True)
    n = np.bincount(inv).astype(float)
    prev = np.concatenate([[0.0], np.cumsum(n)[:-1]])
    take = np.clip(rate * len(s) - prev, 0, n)
    return (take / n)[inv]


def gain_and_se(y, w_ref, w_cand) -> tuple[float, float]:
    """gain = bad rate among accepted (reference) - (candidate); paired linearised standard error."""
    y = np.asarray(y, dtype=float)
    if w_ref.sum() == 0 or w_cand.sum() == 0:
        return float("nan"), float("nan")
    a = w_ref / w_ref.sum() - w_cand / w_cand.sum()
    return float((a * y).sum()), float(np.sqrt(((a * (y - y.mean())) ** 2).sum()))


def gain(y, s_ref, s_cand, rate: float) -> tuple[float, float]:
    return gain_and_se(y, accept_weights(s_ref, rate), accept_weights(s_cand, rate))


# ---------------------------------------------------------------- 1. backtest, window by window
def group_gains(y, s_ref, s_cand, groups, rate: float, min_n: int = 20) -> tuple[np.ndarray, np.ndarray]:
    """Gain inside each group (window or month), cut-off recomputed in the group. Returns (gains, sizes)."""
    y, s_ref, s_cand, groups = (np.asarray(v) for v in (y, s_ref, s_cand, groups))
    out, size = [], []
    for g in sorted(set(groups.tolist())):
        k = groups == g
        if k.sum() >= min_n:
            out.append(gain(y[k], s_ref[k], s_cand[k], rate)[0])
            size.append(int(k.sum()))
    return np.array(out, dtype=float), np.array(size, dtype=float)


def monthly_gains(y, s_ref, s_cand, months, rate: float) -> np.ndarray:
    return group_gains(y, s_ref, s_cand, months, rate)[0]


def backtest_gate(window_gains: np.ndarray, level: float = 0.95, monthly=None, n_train=None, n_test=None,
                  names=None, stress=(), stress_margin: float = 0.0, correction: str = "none") -> dict:
    """t on the WINDOW gains (re-fits). `monthly` = (gains, sizes), informative unless correction == "months".

    months (exp. 2, bench of 12 000 simulated projects): t on the volume-weighted MONTHLY gains of all test
    windows, months - 1 degrees of freedom. Same size as the window t (measured correlation of window
    gains 0.07-0.13), but 3 to 7 windows give a t with 2 to 6 df that refuses good models when one window is
    a crisis: power at 1.5 x threshold 99 % instead of 79 % (none) / 65 % (nadeau_bengio).

    Nadeau-Bengio: the training sets of the windows overlap (expanding window), so window gains are
    positively correlated; the variance of the mean is sd² · (1/k + n_test/n_train) instead of sd²/k
    (n_test/n_train averaged over the windows). Applied when n_train and n_test are given and
    correction == "nadeau_bengio". `stress` = names of pre-registered stress windows: each must have a
    gain >= -stress_margin (worst case, no averaging)."""
    wg = np.asarray(window_gains, dtype=float)
    n = int(len(wg))
    names = list(names) if names is not None else [f"W{i + 1}" for i in range(n)]
    info = {}
    if monthly is not None and len(monthly[0]) >= 3:
        mg, ms = (np.asarray(v, dtype=float) for v in monthly)
        w = ms / ms.sum()
        m_mean = float((w * mg).sum())
        m_sd = float(np.sqrt((w * (mg - m_mean) ** 2).sum() * len(mg) / (len(mg) - 1)))
        tm = float(stats.t.ppf(level, len(mg) - 1))
        info = {"n_months": int(len(mg)), "monthly_mean": m_mean, "monthly_sd": m_sd,
                "prediction_lower": float(m_mean - tm * m_sd * np.sqrt(1 + 1 / len(mg)))}
    if n:
        worst = int(np.nanargmin(wg)) if np.isfinite(wg).any() else 0
        info.update({"worst_window": names[worst], "worst_gain": float(wg[worst]),
                     "n_negative": int((wg < 0).sum())})
    st_rows = []
    for name in stress or ():
        g = float(wg[names.index(name)]) if name in names else float("nan")
        st_rows.append({"window": name, "gain": g, "pass": bool(np.isfinite(g) and g >= -stress_margin)})
    st_bad = [r for r in st_rows if not r["pass"]]
    st_reason = "; ".join(f"stress window {r['window']} : gain {r['gain']:+.4f} < −{stress_margin}"
                          if np.isfinite(r["gain"]) else f"stress window {r['window']} missing from results"
                          for r in st_bad)
    info["stress"] = {"margin": float(stress_margin), "windows": st_rows, "pass": not st_bad}
    if n < 3:
        return {"n_windows": n, "pass": False, **info,
                "reason": "; ".join(x for x in [f"{n} test windows: at least three required", st_reason] if x)}
    mean, sd = float(wg.mean()), float(wg.std(ddof=1))
    t = float(stats.t.ppf(level, n - 1))
    naive = mean - t * sd / np.sqrt(n)
    ratio = None
    if correction not in ("none", "nadeau_bengio", "months"):
        raise SystemExit(f"backtest_correction = {correction!r} : none | months | nadeau_bengio")
    used = "none"
    if correction == "nadeau_bengio" and n_train is not None and n_test is not None:
        ratio = float(np.mean(np.asarray(n_test, dtype=float) / np.asarray(n_train, dtype=float)))
        lower = mean - t * sd * np.sqrt(1 / n + ratio)
        used = "nadeau_bengio"
        if ratio > 0.5:   # implied window correlation ratio/(1+ratio) > 1/3, measured 0.07-0.13 (exp. 2)
            info["warning"] = (f"Nadeau-Bengio with n_test/n_train = {ratio:.2f}: implicit correlation "
                               f"{ratio / (1 + ratio):.2f} across windows, far above measured correlation (about 0.1)")
    elif correction == "months" and info.get("n_months", 0) >= MIN_BLOCKS:
        lower = info["monthly_mean"] - float(stats.t.ppf(level, info["n_months"] - 1)) * info["monthly_sd"] / np.sqrt(info["n_months"])
        used = "months"
    else:
        lower = naive
        if correction == "months":         # never a silent fallback
            info["warning"] = (f"backtest_correction: months requested, but {info.get('n_months', 0)} months de test "
                               f"(< {MIN_BLOCKS}): t-test on window gains")
        elif correction == "nadeau_bengio":
            info["warning"] = "backtest_correction: nadeau_bengio requested but n_train / n_test unknown: t-test on window gains"
    t_pass = bool(lower > 0)
    tag = {"nadeau_bengio": " (Nadeau-Bengio)", "months": " (gains monthly)"}.get(used, "")
    reasons = ([] if t_pass else [f"gain moyen {mean if used != 'months' else info['monthly_mean']:+.4f}, "
                                  f"bound basse {lower:+.4f} ≤ 0{tag}"]) + ([st_reason] if st_reason else [])
    return {"n_windows": n, "window_names": names, "window_gains": [float(x) for x in wg], "mean": mean, "sd": sd,
            "level": level, "lower": float(lower), "lower_naive": float(naive),
            "correction": used, "correction_requested": correction, "test_train_ratio": ratio,
            "t_pass": t_pass, "pass": bool(t_pass and not st_bad), **info, "reason": "; ".join(reasons)}


# ---------------------------------------------------------------- 2. segments, non-inferiority
def segment_gate(y, s_ref, s_cand, windows, masks: dict, rate: float, margin: float, level: float = 0.95,
                 min_size: int = 0, multiplicity: str = "none", unevaluable: str = "pass") -> dict:
    """Acceptance decided per window over everyone (the real policy), gain read inside each segment.

    A segment is « not evaluable » when it has fewer than `min_size` loans, or when one of the two scores
    accepts nobody in it (no gain can be computed): it is listed, never reported as nan, and blocks only
    if `unevaluable == "fail"`. Holm (step-down) over the evaluable segments, on the one-sided p-values of
    H0 « gain <= -margin »; `lower` is the bound at the segment's Holm level."""
    if multiplicity not in ("holm", "none") or unevaluable not in ("pass", "fail"):
        raise SystemExit("noninferiority : multiplicity ∈ {holm, none}, unevaluable ∈ {pass, fail}")
    y, s_ref, s_cand, windows = (np.asarray(v) for v in (y, s_ref, s_cand, windows))
    w_ref, w_cand = np.zeros(len(y)), np.zeros(len(y))
    for w in set(windows.tolist()):
        k = windows == w
        w_ref[k], w_cand[k] = accept_weights(s_ref[k], rate), accept_weights(s_cand[k], rate)
    alpha = 1 - level
    rows, todo = [], []
    for name, m in masks.items():
        m = np.asarray(m, dtype=bool)
        n = int(m.sum())
        row = {"segment": name, "n": n}
        if n < max(int(min_size), 1):
            row.update({"evaluable": False, "why": f"{n} loans < minimum size {int(min_size)}"})
        elif w_ref[m].sum() == 0 or w_cand[m].sum() == 0:
            row.update({"evaluable": False, "why": ("the reference" if w_ref[m].sum() == 0 else "the candidate")
                        + " accepts nobody in this segment"})
        else:
            g, se = gain_and_se(y[m], w_ref[m], w_cand[m])
            p = float(stats.norm.sf((g + margin) / se)) if se > 0 else (0.0 if g > -margin else 1.0)
            row.update({"evaluable": True, "gain": g, "se": se, "p": p})
            todo.append(row)
        rows.append(row)
    k = len(todo)
    still = True
    for j, r in enumerate(sorted(todo, key=lambda r: r["p"])):
        a = alpha / (k - j) if multiplicity == "holm" else alpha
        r["level_used"] = 1 - a
        r["lower"] = float(r["gain"] - stats.norm.ppf(1 - a) * r["se"])
        still = still and r["p"] <= a
        r["pass"] = bool(still) if multiplicity == "holm" else bool(r["p"] <= a)
    bad = [r for r in rows if r["evaluable"] and not r["pass"]]
    unev = [r for r in rows if not r["evaluable"]]
    reason = [f"{r['segment']} : bound basse {r['lower']:+.4f} < −{margin}" for r in bad]
    if unevaluable == "fail":
        reason += [f"{r['segment']} not evaluable ({r['why']})" for r in unev]
    return {"margin": margin, "level": level, "multiplicity": multiplicity, "min_size": int(min_size),
            "unevaluable_policy": unevaluable, "segments": rows,
            "unevaluable": [{"segment": r["segment"], "n": r["n"], "why": r["why"]} for r in unev],
            "pass": not bad and not (unevaluable == "fail" and unev), "reason": "; ".join(reason)}


# ---------------------------------------------------------------- 4. holdout
def holdout_gate(g: float, se: float, min_gain: float, ci_level: float, rule: str = "expected_value",
                 df: int | None = None) -> dict:
    """expected_value: g >= min_gain and lower bound of the two-sided ci_level interval > 0.
    margin: one-sided lower bound at ci_level > min_gain. `df` (block bootstrap) -> Student t quantiles."""
    if rule not in RULES:
        raise SystemExit(f"unknown acceptance rule: {rule!r}")
    q = (lambda p: float(stats.t.ppf(p, df))) if df else (lambda p: float(stats.norm.ppf(p)))
    z2, z1 = q(1 - (1 - ci_level) / 2), q(ci_level)
    lo, hi = g - z2 * se, g + z2 * se
    lower1 = g - z1 * se
    ok = (g >= min_gain and lo > 0) if rule == "expected_value" else (lower1 > min_gain)
    return {"gain": g, "se": se, "ci": [float(lo), float(hi)], "ci_level": ci_level, "min_gain": min_gain,
            "lower_one_sided": float(lower1), "rule": rule, "df": df, "pass": bool(np.isfinite(g) and ok)}


def _tie_tables(score, y, block, n_blocks: int, rate: float):
    """Per (tie group of the score) x (block): loans and bads, rows that can never move across the cut-off
    collapsed. The cut-off of any re-weighting of the blocks lies between the smallest and the largest
    per-block cut-off, so groups strictly below always stay accepted, strictly above always refused."""
    s = np.asarray(score, dtype=float)
    cuts = [np.quantile(s[block == b], rate, method="inverted_cdf") for b in range(n_blocks) if (block == b).any()]
    lo, hi = min(cuts), max(cuts)
    vals, inv = np.unique(s, return_inverse=True)
    keep = (vals >= lo) & (vals <= hi)
    code = np.zeros(len(vals), dtype=int)
    code[keep] = np.arange(1, keep.sum() + 1)
    code[vals > hi] = keep.sum() + 1
    gid = code[inv]                                   # 0 = always accepted, K+1 = always refused
    K = int(keep.sum()) + 2
    idx = gid * n_blocks + block
    n = np.bincount(idx, minlength=K * n_blocks).reshape(K, n_blocks).astype(float)
    b = np.bincount(idx, weights=np.asarray(y, dtype=float), minlength=K * n_blocks).reshape(K, n_blocks)
    return n, b


def _bad_rates(n, b, C, rate: float, chunk: int = 64) -> np.ndarray:
    """Bad rate among accepted for each column of block multiplicities C (blocks x R), ties pro rata."""
    out = []
    for j in range(0, C.shape[1], chunk):
        c = C[:, j:j + chunk]
        N, Bd = n @ c, b @ c
        prev = np.cumsum(N, axis=0) - N
        take = np.clip(rate * N.sum(axis=0) - prev, 0, N)
        frac = np.divide(take, N, out=np.zeros_like(N), where=N > 0)
        out.append((frac * Bd).sum(axis=0) / take.sum(axis=0))
    return np.concatenate(out)


def block_bootstrap(y, s_ref, s_cand, blocks, rate: float, B: int = 2000, seed: int = 0) -> dict:
    """Paired bootstrap by blocks (months): whole months are resampled with replacement, the same loans for
    both scores, the cut-off recomputed on each resample. When the number of distinct resamples is <= B
    (6 months: 462, 7: 1 716), they are enumerated exactly with their multinomial probabilities.
    se is inflated by sqrt(G/(G-1)) (the bootstrap of a mean of G blocks under-estimates its variance by
    that factor); use it with Student t, G-1 degrees of freedom."""
    y = np.asarray(y, dtype=float)
    _, blk = np.unique(np.asarray(blocks).astype(str), return_inverse=True)
    G = int(blk.max()) + 1
    point = gain(y, s_ref, s_cand, rate)[0]
    if G < 2:
        return {"gain": point, "se": float("nan"), "n_blocks": G, "df": None, "exact": False, "B": 0}
    n_distinct = math.comb(2 * G - 1, G)
    if n_distinct <= B:
        combos = np.array([np.bincount(c, minlength=G) for c in itertools.combinations_with_replacement(range(G), G)]).T
        logw = (math.lgamma(G + 1) - np.sum([[math.lgamma(k + 1) for k in col] for col in combos.T], axis=1)
                - G * math.log(G))
        w, C, exact = np.exp(logw), combos.astype(float), True
    else:
        rng = np.random.default_rng(seed)
        C = rng.multinomial(G, np.full(G, 1 / G), size=B).T.astype(float)
        w, exact = np.full(B, 1 / B), False
    nr, br = _tie_tables(s_ref, y, blk, G, rate)
    nc, bc = _tie_tables(s_cand, y, blk, G, rate)
    draws = _bad_rates(nr, br, C, rate) - _bad_rates(nc, bc, C, rate)
    w = w / w.sum()
    mean = float((w * draws).sum())
    sd = float(np.sqrt((w * (draws - mean) ** 2).sum()))
    order = np.argsort(draws)
    cw = np.cumsum(w[order])
    pct = lambda p: float(draws[order][min(np.searchsorted(cw, p), len(cw) - 1)])
    return {"gain": point, "se": sd * math.sqrt(G / (G - 1)), "se_raw": sd, "n_blocks": G, "df": G - 1,
            "exact": exact, "B": int(C.shape[1]), "boot_mean": mean, "pct": {"0.05": pct(0.05), "0.95": pct(0.95)}}


def holdout_decision(y, s_ref, s_cand, months, rate: float, min_gain: float, ci_level: float,
                     rule: str = "expected_value", B: int = 2000, seed: int = 0) -> dict:
    """Both intervals, shown side by side; the decision uses the monthly blocks when there are >= 6 months,
    otherwise the linearisation (independence between loans), with a warning."""
    g, se = gain(y, s_ref, s_cand, rate)
    lin = holdout_gate(g, se, min_gain, ci_level, rule)
    bb = block_bootstrap(y, s_ref, s_cand, months, rate, B=B, seed=seed)
    blk = holdout_gate(g, bb["se"], min_gain, ci_level, rule, df=bb["df"]) if bb["df"] else None
    use_blocks = blk is not None and bb["n_blocks"] >= MIN_BLOCKS
    used = blk if use_blocks else lin
    warn = "" if use_blocks else (f"{bb['n_blocks']} months in holdout (< {MIN_BLOCKS}) : intervalle par "
                                  "linearization assumes independent loans (monthly shocks ignored, confidence interval too narrow)")
    return {**used, "method": "block_bootstrap" if use_blocks else "linearisation", "warning": warn,
            "linearisation": lin, "block_bootstrap": {**bb, "gate": blk}}


# ---------------------------------------------------------------- threshold and detectability
def min_gain(spec: dict) -> dict:
    """Acceptance threshold. Preferred: computed from costs (Q-CAD-03, Q-EVA-05), so that it can only be
    renegotiated by changing its inputs, visibly. A typed number needs a written source."""
    acc = spec.get("acceptance", {})
    cm = acc.get("cost_model")
    if cm:
        need = ("deployment", "validation", "run_per_year", "horizon_years", "value_per_point")
        missing = [k for k in need if k not in cm]
        if missing:   # a forgotten cost would silently lower the threshold (fresh review, lots 1-2)
            raise SystemExit(f"acceptance.cost_model incomplet : {', '.join(missing)} missing(s)")
        if any(float(cm[k]) < 0 for k in need) or float(cm["value_per_point"]) <= 0:
            raise SystemExit("acceptance.cost_model: negative values or zero value_per_point")
        total = float(cm["deployment"]) + float(cm["validation"]) + float(cm["run_per_year"]) * float(cm["horizon_years"])
        per_point = float(cm["value_per_point"])          # value of 1 point less of bad rate, over the horizon
        points = total / per_point
        if points <= 0:
            raise SystemExit("acceptance.cost_model: zero total cost would yield a zero threshold")
        return {"min_gain": points / 100, "source": "cost_model", "total_cost": total,
                "value_per_point": per_point, "points": points,
                "text": f"{total:,.0f} costs / {per_point:,.0f} par point = {points:.3f} point".replace(",", " ")}
    if "min_gain" in acc:
        src = str(acc.get("min_gain_source", "")).strip()
        if float(acc["min_gain"]) <= 0:
            raise SystemExit("acceptance.min_gain must be > 0")
        return {"min_gain": float(acc["min_gain"]), "source": "typed", "justification": src,
                "text": f"{float(acc['min_gain']) * 100:.3f} point saisi" + (f" ({src})" if src else " without justification")}
    raise SystemExit("frame : acceptance.cost_model (ou min_gain + min_gain_source) missing")


def z_detect(ci_level: float, power: float = 0.8) -> float:
    """The holdout test is « lower bound of the two-sided ci_level interval > 0 »: one-sided alpha (1-ci)/2."""
    return float(stats.norm.ppf(1 - (1 - ci_level) / 2) + stats.norm.ppf(power))


def required_gain(min_gain_: float, se: float, ci_level: float, power: float = 0.8) -> float:
    """Rule margin: true gain needed to be accepted with probability `power`: δ + (z_ci + z_power)·se."""
    return float(min_gain_ + (stats.norm.ppf(ci_level) + stats.norm.ppf(power)) * se)


def require_usable(mg: dict) -> None:
    """Before reading the holdout: a typed threshold needs a written source (not only a check)."""
    if mg["source"] == "typed" and not mg.get("justification"):
        raise SystemExit("threshold entered without acceptance.min_gain_source: derive it from costs "
                         "(acceptance.cost_model) or document its source before any holdout reading")


def mde(n_holdout: int, rate: float, p_cut: float, swap_share: float, alpha: float = 0.05, power: float = 0.8) -> dict:
    """Smallest gain the holdout can tell from zero. Two scores accepting the same share differ by
    `swap_share` of the accepted (k loans in, k out); the gain is (bad out - bad in) / accepted, whose
    standard error is about sqrt(2 * swap_share * p(1-p) / accepted), p = bad rate near the cut-off."""
    accepted = rate * n_holdout
    se = float(np.sqrt(2 * swap_share * p_cut * (1 - p_cut) / accepted))
    k = float(stats.norm.ppf(1 - alpha) + stats.norm.ppf(power))
    return {"se": se, "mde": k * se, "n_holdout": n_holdout, "accepted": accepted, "p_cut": p_cut,
            "swap_share": swap_share, "alpha": alpha, "power": power}
