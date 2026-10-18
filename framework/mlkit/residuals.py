"""Where does the candidate still get it wrong? Residual analysis on the backtest windows.

    python -m mlkit.residuals --run r-0007
    python -m mlkit.residuals --pipeline model/pipeline.py [--top-k 8] [--permutations 30]

Writes reports/residuals-<run>.md and .json (<run> = the run id, or the analysis id `res-NNNN`
with --pipeline) and appends one line to experiments/residuals_ledger.jsonl, so the number of
residual analyses is traceable. Reads data/dev only. Never compares with the reference and
never writes the run registry: it spends no exploration budget.

Method (each step is deliberately simple, so a person can check it):
1. Out-of-sample predictions: for every backtest window, build() is fitted on loans issued
   <= train_end and scores the window, exactly as mlkit.run does. With --run, the predictions
   saved by the run (.osml/preds/<run>.csv.gz) are reused when code and data are unchanged.
2. Recalibration per window: logistic regression of y on (z, z^2, z^3), z = standardised
   logit of the score (or the score itself when it is not in [0, 1]). Four parameters per
   window, fitted on the window: it turns a rank (e.g. the score in place) into a probability
   and removes level shifts between windows, which no feature can fix and the primary metric
   (ranking inside a window) ignores. eta = logit of that probability is the baseline.
3. Residual models, all on the logit scale with eta as fixed offset (a Newton/LogitBoost step):
   - one column: one effect per band (quantile bands, missing band, rare categories pooled;
     same banding as mlkit.bivariate), ridge-shrunk: f_b += (G_b - lam f_b) / (H_b + lam),
     G = sum(y - p), H = sum p(1 - p), 4 iterations;
   - one pair: one effect per cell of a coarse 2-D grid; its INTERACTION is the gain of the
     grid minus the gain of the additive model of the same two bandings (backfitting).
   Every column `available: origination` and not excluded in features.yaml is tried, used by
   the pipeline or not. Pairs: among the K best single columns plus the candidate's own score
   in deciles (`__score__`: an effect that depends on the risk level).
4. Validation: cross-fitting by window: the effects are learnt on the other windows and scored
   on the left-out one. Score = out-of-sample log-likelihood gain over the baseline, in
   millinats per loan (1 mnat/loan = 1 nat of log-likelihood per 1000 loans).
5. Chance floor by permutation: inside each window, the rows of (y, eta) are permuted against
   the features (one permutation shared by every column and pair, so the X-X structure stays).
   Per candidate: 95th percentile of its own null gains. Family-wise: 95th percentile of the
   MAXIMUM over all candidates of the same kind (single / pair) in each permutation. A candidate
   is `signal` above the family floor, `to confirm` above its own floor only, `noise` otherwise.

Known blind spots (see README): the backtest windows are also those that judge the gain, so a
hypothesis read here and tested there is selected on the validation data (the holdout stays
the guard; the ledger counts the analyses). Pairs of columns that are each useless alone are
found only if both are in the K best (use --top-k 0 for every pair). Effect shapes are
described on all windows (in sample): they illustrate, the gain and floors decide.

Exit codes: 0 ok · 2 run unknown or not analysable · 4 pipeline uses a refused column (I5)
            · 6 data not conform (D2/D5) · 7 phase gate closed · 9 role not allowed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

import numpy as np
import pandas as pd
from scipy.special import expit
from sklearn.linear_model import LogisticRegression

from . import config, core, dataquality as dq, gate, reference
from .bivariate import make_bins

ALLOWED_ROLES = {"explorer", "data-analyst"}
LEDGER = config.ROOT / "experiments" / "residuals_ledger.jsonl"
SCORE = "__score__"
LAM = 30.0            # ridge on band effects, in units of p(1-p): ~200 loans at a 15 % default rate
ITERS = 4
PAIR_BINS = 5


# ---------------------------------------------------------------- predictions
def oos_predictions(module, df: pd.DataFrame, spec: dict) -> pd.DataFrame:
    """Row index of df, window, y, score: the candidate re-fitted per window, as in mlkit.run."""
    y_all = df[spec["target_col"]].to_numpy()
    out = []
    for name, train_end, start, end in core.windows(spec):
        tr = (df["_month"] <= train_end).to_numpy()
        te = ((df["_month"] >= start) & (df["_month"] <= end)).to_numpy()
        if tr.sum() == 0 or te.sum() == 0:
            raise SystemExit(f"window {name}: train={tr.sum()} test={te.sum()} — data insuffisantes")
        score = core.fit_predict(module, df.loc[tr, module.FEATURES], y_all[tr], df.loc[te, module.FEATURES])
        out.append(pd.DataFrame({"row": np.flatnonzero(te), "window": name, "y": y_all[te], "score": score}))
    return pd.concat(out, ignore_index=True)


def cached_predictions(run: dict, df: pd.DataFrame, spec: dict, data_hash: str):
    """Predictions saved by mlkit.run, if they still describe the current code and data."""
    path = config.PREDS_DIR / f"{run['run_id']}.csv.gz"
    if not path.exists() or run.get("data_hash") != data_hash:
        return None
    try:
        if run.get("code_hash") != core.code_hash(run["pipeline"]):
            return None
    except OSError:
        return None
    ids = df[spec["id_col"]]
    if ids.duplicated().any():
        return None
    p = pd.read_csv(path)
    pos = pd.Series(np.arange(len(df)), index=ids.to_numpy())
    p = p[p[spec["id_col"]].isin(pos.index)]
    return pd.DataFrame({"row": pos.loc[p[spec["id_col"]]].to_numpy(), "window": p["window"].to_numpy(),
                         "y": p["y"].to_numpy(), "score": p["score"].to_numpy()})


def recalibrate(y: np.ndarray, score: np.ndarray, window: np.ndarray) -> np.ndarray:
    """Logit of a per-window cubic logistic recalibration of the score (see module docstring)."""
    eta = np.zeros(len(y))
    for w in pd.unique(window):
        m = window == w
        s = score[m].astype(float)
        z = np.log(np.clip(s, 1e-4, 1 - 1e-4) / (1 - np.clip(s, 1e-4, 1 - 1e-4))) if (s.min() >= 0 and s.max() <= 1) else s
        z = (z - z.mean()) / (z.std() or 1.0)
        X = np.c_[z, z ** 2, z ** 3]
        if len(np.unique(y[m])) < 2:
            eta[m] = np.log((y[m].mean() + 0.5 / m.sum()) / (1 - y[m].mean() + 0.5 / m.sum()))
            continue
        lr = LogisticRegression(C=1e4, max_iter=1000).fit(X, y[m])
        eta[m] = lr.decision_function(X)
    return np.clip(eta, -9, 9)


# ---------------------------------------------------------------- residual models
def loglik(y, eta) -> np.ndarray:
    return y * eta - np.logaddexp(0, eta)


def fit_offsets(codes, k, eta, y, iters=ITERS, lam=LAM) -> np.ndarray:
    f = np.zeros(k)
    for _ in range(iters):
        p = expit(eta + f[codes])
        g = np.bincount(codes, weights=y - p, minlength=k)
        h = np.bincount(codes, weights=p * (1 - p), minlength=k)
        f += (g - lam * f) / (h + lam)
    return f


def fit_additive(ca, ka, cb, kb, eta, y, rounds=2):
    fa, fb = np.zeros(ka), np.zeros(kb)
    for _ in range(rounds):
        fa = fit_offsets(ca, ka, eta + fb[cb], y)
        fb = fit_offsets(cb, kb, eta + fa[ca], y)
    return fa, fb


def crossfit(folds, y, eta, codes, k, pair=None) -> np.ndarray:
    """Out-of-sample log-likelihood gain (nats, summed) per fold. pair=(ca, ka, cb, kb): additive model."""
    out = []
    for test in folds:
        tr = ~test
        if pair is None:
            f = fit_offsets(codes[tr], k, eta[tr], y[tr])
            delta = f[codes[test]]
        else:
            ca, ka, cb, kb = pair
            fa, fb = fit_additive(ca[tr], ka, cb[tr], kb, eta[tr], y[tr])
            delta = fa[ca[test]] + fb[cb[test]]
        out.append(float((loglik(y[test], eta[test] + delta) - loglik(y[test], eta[test])).sum()))
    return np.array(out)


def within_window_permutation(window: np.ndarray, rng) -> np.ndarray:
    idx = np.arange(len(window))
    out = idx.copy()
    for w in pd.unique(window):
        m = np.flatnonzero(window == w)
        out[m] = rng.permutation(idx[m])
    return out


# ---------------------------------------------------------------- banding and shapes
def band(s: pd.Series, n_bins: int, min_share: float):
    num = pd.to_numeric(s, errors="coerce")
    numeric = bool(s.notna().any() and num[s.notna()].notna().mean() >= 0.99)
    codes, names, ordered = make_bins(s.reset_index(drop=True), numeric, n_bins=n_bins, min_share=min_share)
    return np.asarray(codes, dtype=int), list(names), list(ordered), numeric


def coarse_band(s: pd.Series, k: int):
    """Pair grids: k quantile bands (+ missing) for numbers, the main categories (>= 5 %) otherwise."""
    s = s.reset_index(drop=True)
    num = pd.to_numeric(s, errors="coerce")
    if s.notna().any() and num[s.notna()].notna().mean() >= 0.99 and num.nunique() > k:
        q = pd.qcut(num.rank(method="average"), k, duplicates="drop")
        cats = list(q.cat.categories)
        if len(cats) < 2:          # heavy ties (a dominant value): qcut collapses, fall back to plain bands (eval XP crash)
            codes, names, _, _ = band(s, k, 0.05)
            return codes, names, len(names)
        edges = [num[q == c].min() for c in cats]
        names = [f"< {edges[1]:.4g}"] + [f"[{edges[i]:.4g} ; {edges[i + 1]:.4g}[" for i in range(1, len(cats) - 1)] + [f"≥ {edges[-1]:.4g}"]
        codes = q.cat.codes.to_numpy().astype(int)
        if (codes < 0).any():
            codes = np.where(codes < 0, len(names), codes)
            names.append("missing")
        return codes, names, len(names)
    codes, names, _, _ = band(s, k, 0.05)
    return codes, names, len(names)


def zone(codes, names, y, p, k) -> dict:
    """The band (or cell) with the largest excess of defaults over the predicted count, in either direction."""
    n = np.bincount(codes, minlength=k)
    g = np.bincount(codes, weights=y - p, minlength=k)
    b = int(np.argmax(np.abs(g)))
    return {"where": names[b], "n": int(n[b]), "observed": float(np.bincount(codes, weights=y, minlength=k)[b] / max(n[b], 1)),
            "predicted": float(np.bincount(codes, weights=p, minlength=k)[b] / max(n[b], 1)), "excess": float(g[b])}


def describe_single(f, names, ordered, n) -> tuple[str, str]:
    """(shape, sense) of the band effects f (logit). Sense: f > 0 = risk underestimated by the candidate."""
    idx = [i for i, o in enumerate(ordered) if o and n[i] > 0]
    miss = [i for i, o in enumerate(ordered) if not o and names[i] == "missing" and n[i] > 0]
    extra = ""
    if miss and abs(f[miss[0]]) >= 0.15:
        extra = f" ; missing value: risk {'under' if f[miss[0]] > 0 else 'over'}-estimated"
    if len(idx) < 3:                              # categorical, or too few bands
        if not len(f):
            return "none", ""
        order = np.argsort(-np.abs(f) * np.sqrt(np.maximum(n, 1)))[:2]
        parts = [f"`{names[i]}` ({'under' if f[i] > 0 else 'over'}-estimated)" for i in order]
        return "segment-specific", "risk " + ", ".join(parts) + extra
    v = f[idx]
    rng = float(v.max() - v.min())
    if rng < 0.05:
        return "weak", "effect plat" + extra
    jumps = np.diff(v)
    j = int(np.argmax(np.abs(jumps)))
    rho = float(np.corrcoef(np.arange(len(v)), v)[0, 1]) if np.std(v) > 0 else 0.0
    left, right = v[: j + 1], v[j + 1:]
    flat_sides = max(np.ptp(left), np.ptp(right)) <= 0.45 * rng
    lab = names[idx[j + 1]]
    if abs(jumps[j]) >= 0.5 * rng and flat_sides:
        where = "starting at" if jumps[j] > 0 else "before"
        return "threshold", f"risk underestimated {where} bin {lab} (logit jump {jumps[j]:+.2f})" + extra
    lo, hi = int(np.argmin(v)), int(np.argmax(v))
    if 0 < lo < len(v) - 1 and min(v[0], v[-1]) - v[lo] >= 0.5 * rng:
        return "U-shaped", f"risk underestimated at both extremes; minimum near {names[idx[lo]]}" + extra
    if 0 < hi < len(v) - 1 and v[hi] - max(v[0], v[-1]) >= 0.5 * rng:
        return "bell-shaped", f"risk underestimated in the middle; maximum near {names[idx[hi]]}" + extra
    if abs(rho) >= 0.7:
        return "monotone", f"risk {'under' if rho > 0 else 'over'}-estimated as the value increases" + extra
    return "irregular", "no simple shape" + extra


# ---------------------------------------------------------------- analysis
def analyse(df: pd.DataFrame, preds: pd.DataFrame, columns: list[str], used: set[str], top_k: int,
            permutations: int, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    y = preds["y"].to_numpy(dtype=float)
    window = preds["window"].to_numpy()
    eta = recalibrate(y, preds["score"].to_numpy(dtype=float), window)
    p = expit(eta)
    rows = preds["row"].to_numpy()
    d = df.iloc[rows].reset_index(drop=True)
    wins = list(pd.unique(window))
    if len(wins) >= 2:
        folds = [window == w for w in wins]
    else:                                         # one window: three blocks of months
        months = d["_month"].astype(str).to_numpy()
        um = np.unique(months)
        folds = [np.isin(months, part) for part in np.array_split(um, 3) if len(part)]
    perms = [within_window_permutation(window, rng) for _ in range(permutations)]
    n = len(y)
    base = float(-loglik(y, eta).mean())

    singles = {}
    for c in columns:
        codes, names, ordered, numeric = band(d[c], 10, 0.01)
        k = len(names)
        if k < 2:
            continue
        per_fold = crossfit(folds, y, eta, codes, k)
        null = np.array([crossfit(folds, y, eta, codes[pi], k).sum() / n for pi in perms])
        f_all = fit_offsets(codes, k, eta, y)
        shape, sense = describe_single(f_all, names, ordered, np.bincount(codes, minlength=k))
        singles[c] = {"kind": "column", "columns": [c], "used_by_pipeline": c in used,
                      "gain": 1000 * per_fold.sum() / n, "per_window": [1000 * g / max(m.sum(), 1) for g, m in zip(per_fold, folds)],
                      "null": 1000 * null, "shape": shape, "sense": sense,
                      "zone": zone(codes, names, y, p, k), "_codes": codes, "_numeric": numeric}

    order = sorted(singles, key=lambda c: -singles[c]["gain"])
    pool = order if top_k <= 0 else order[:top_k]
    coarse = {}
    for c in pool:
        coarse[c] = coarse_band(d[c], PAIR_BINS)
    deciles = np.minimum((pd.Series(p).rank(method="first").to_numpy() - 1) * PAIR_BINS // n, PAIR_BINS - 1).astype(int)
    coarse[SCORE] = (deciles, [f"quintile de risk {i + 1}/{PAIR_BINS}" for i in range(PAIR_BINS)], PAIR_BINS)
    names_pool = [*pool, SCORE]
    pairs = {}
    for i, a in enumerate(names_pool):
        for b in names_pool[i + 1:]:
            ca, la, ka = coarse[a]
            cb, lb, kb = coarse[b]
            if ka < 2 or kb < 2:
                continue
            cells = ca * kb + cb
            k2 = ka * kb

            def gains(perm=None):
                c2, xa, xb = (cells, ca, cb) if perm is None else (cells[perm], ca[perm], cb[perm])
                full = crossfit(folds, y, eta, c2, k2)
                add = crossfit(folds, y, eta, None, None, pair=(xa, ka, xb, kb))
                return full, add

            full, add = gains()
            null = np.array([(lambda fa: (fa[0].sum() - fa[1].sum()) / n)(gains(pi)) for pi in perms])
            f2 = fit_offsets(cells, k2, eta, y)
            fa, fb = fit_additive(ca, ka, cb, kb, eta, y)
            inter = f2 - (fa[:, None] + fb[None, :]).ravel()
            ncell = np.bincount(cells, minlength=k2)
            # described where the 2-D effect (vs the candidate) is strongest; the gain counted is its non-additive part
            cbest = int(np.argmax(np.abs(f2) * np.sqrt(ncell)))
            ia, ib = divmod(cbest, kb)
            obs = float(y[cells == cbest].mean()) if ncell[cbest] else float("nan")
            pred = float(p[cells == cbest].mean()) if ncell[cbest] else float("nan")
            pairs[(a, b)] = {"kind": "paire", "columns": [a, b],
                             "used_by_pipeline": [x in used for x in (a, b)],
                             "gain": 1000 * (full.sum() - add.sum()) / n, "gain_grid": 1000 * full.sum() / n,
                             "per_window": [1000 * (g1 - g0) / max(m.sum(), 1) for g1, g0, m in zip(full, add, folds)],
                             "null": 1000 * null, "shape": "segment-specific",
                             "sense": f"`{a}` ∈ {la[ia]} and `{b}` ∈ {lb[ib]} : risk {'under' if f2[cbest] > 0 else 'over'}-estimated "
                                      f"(logit difference {f2[cbest]:+.2f}, dont non additif {inter[cbest]:+.2f})",
                             "zone": {"where": f"{a} ∈ {la[ia]} × {b} ∈ {lb[ib]}", "n": int(ncell[cbest]),
                                      "observed": obs, "predicted": pred}}

    q = 0.95
    fam_single = float(np.quantile(np.max(np.vstack([s["null"] for s in singles.values()]), axis=0), q)) if singles and perms else 0.0
    fam_pair = float(np.quantile(np.max(np.vstack([s["null"] for s in pairs.values()]), axis=0), q)) if pairs and perms else 0.0
    entries = []
    for e, fam in [*((s, fam_single) for s in singles.values()), *((s, fam_pair) for s in pairs.values())]:
        own = float(np.quantile(e["null"], q)) if perms else 0.0
        e.update(floor=own, floor_family=fam,
                 status="signal" if e["gain"] > max(fam, 0) else ("to confirm" if e["gain"] > max(own, 0) else "noise"),
                 windows_positive=int(sum(g > 0 for g in e["per_window"])))
        e.pop("_codes", None), e.pop("_numeric", None)
        e["null"] = [round(float(v), 4) for v in e["null"]]
        entries.append(e)
    rank = {"signal": 0, "to confirm": 1, "noise": 2}
    entries.sort(key=lambda e: (rank[e["status"]], -e["gain"]))
    return {"rows": int(n), "windows": [str(w) for w in wins], "baseline_logloss": base,
            "default_rate": float(y.mean()), "permutations": permutations, "top_k": top_k,
            "pair_pool": names_pool, "floor_family": {"column": fam_single, "paire": fam_pair},
            "entries": entries}


# ---------------------------------------------------------------- hypotheses and report
def _cols(e) -> str:
    return " × ".join(f"`{c}`" for c in e["columns"])


def hypotheses(entries: list[dict], res_id: str) -> list[dict]:
    out, seen = [], set()
    for e in entries:
        if len(out) == 3 or e["status"] == "noise":
            break
        key = tuple(e["columns"])
        if key in seen:
            continue
        seen.add(key)
        z = e["zone"]
        zone_txt = (f"worst-predicted region: {z['where']} ({z['n']} loans, observed default {z['observed']:.1%}, "
                    f"predicted {z['predicted']:.1%})")
        conf = "solide (au-dessus du floor du chance global)" if e["status"] == "signal" else "fragile (au-dessus de son only floor)"
        if e["kind"] == "paire":
            a, b = e["columns"]
            if SCORE in (a, b):
                col = b if a == SCORE else a
                idea = (f"L'effect de `{col}` depends on risk level: {e['sense']}. Direction : interaction de `{col}` "
                        "with the main scoring variables, or deeper trees on this column.")
            else:
                unused = [c for c, u in zip(e["columns"], e["used_by_pipeline"]) if not u]
                idea = (f"Ajouter l'interaction {_cols(e)} : {e['sense']}. Direction: crossed-segment indicator or product "
                        "of both columns, or trees of depth ≥ 2 on these columns"
                        + (f" (not currently used: {', '.join(f'`{c}`' for c in unused)})" if unused else "") + ".")
        else:
            c = e["columns"][0]
            hint = {"threshold": "a threshold indicator or binning",
                    "U-shaped": "a nonmonotonic transform (distance to minimum, bins)",
                    "bell-shaped": "a nonmonotonic transform (bins)",
                    "monotone": "the unchanged column or a monotonic transform (log, rank)",
                    "segment-specific": "pooling the flagged categories",
                    "irregular": "binning"}.get(e["shape"], "binning")
            if e["used_by_pipeline"]:
                idea = (f"`{c}` is used but poorly captured (shape {e['shape']} : {e['sense']}). Direction : {hint}, "
                        "or less regularization on this column.")
            else:
                idea = f"Ajouter `{c}` (not currently used), shape {e['shape']} : {e['sense']}. Direction : {hint}."
        out.append({"id": f"{res_id}/H{len(out) + 1}", "columns": e["columns"], "text": idea, "zone": zone_txt,
                    "expected_gain_mnats": round(e["gain"], 3), "confidence": conf})
    while len(out) < 3:
        out.append({"id": f"{res_id}/H{len(out) + 1}", "columns": [], "confidence": "none",
                    "text": "No remaining signal above the chance floor in declared columns: "
                            "another variant on these columns is unlikely to improve. Remaining directions are "
                            "outside the registry (new source, target definition, population): escalate.",
                    "zone": "", "expected_gain_mnats": 0.0})
    return out


def write_reports(res: dict, stem: str) -> tuple:
    config.REPORTS_DIR.mkdir(exist_ok=True)
    jpath = config.REPORTS_DIR / f"residuals-{stem}.json"
    mpath = config.REPORTS_DIR / f"residuals-{stem}.md"
    jpath.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    ff = res["floor_family"]
    L = [f"# Signal restant — {res['res_id']} ({res['target']})", "",
         f"- Pipeline : `{res['pipeline']}` · windows: {', '.join(res['windows'])} · {res['rows']:,} loans "
         f"· default {res['default_rate']:.1%} · baseline log-loss (recalibrated per window) {res['baseline_logloss']:.4f}",
         f"- Gain = out-of-sample log-likelihood improvement, learned on other windows, in millinats per loan. "
         f"Floor du chance : {res['permutations']} permutations per window; global (family maximum, 95%) "
         f"columns {ff['column']:.3f}, paires {ff['paire']:.3f}.",
         "- signal: above the global floor; to confirm: above its own floor only; noise: otherwise.",
         "- Pair: gain from the interaction alone (2-D grid minus the two-column additive model). "
         f"`{SCORE}` = quintiles du score du candidat.",
         "- **No reference comparison and no budget spent.** These are also the windows used to judge "
         "gain: independent evidence is required for confirmation.", "",
         "## Hypotheses to test (cite the identifier in --note)", ""]
    for h in res["hypotheses"]:
        L.append(f"- **{h['id']}** — {h['text']}" + (f" ({h['zone']} ; gain expected ≈ {h['expected_gain_mnats']:.2f} mnats/loan; "
                                                     f"confidence {h['confidence']})" if h["columns"] else ""))
    L += ["", "## Remaining signal, ranked", "",
          "| # | column(s) | used | gain | floor | global floor | windows > 0 | status | shape | direction |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for i, e in enumerate(res["entries"], 1):
        if e["status"] == "noise" and i > 25:
            continue
        used = e["used_by_pipeline"]
        used_txt = ("yes" if used else "non") if isinstance(used, bool) else "/".join("yes" if u else "non" for u in used)
        L.append(f"| {i} | {_cols(e)} | {used_txt} | {e['gain']:.3f} | {e['floor']:.3f} | {e['floor_family']:.3f} | "
                 f"{e['windows_positive']}/{len(e['per_window'])} | {e['status']} | {e['shape']} | {e['sense']} |")
    mpath.write_text("\n".join(L) + "\n", encoding="utf-8")
    return mpath, jpath


# ---------------------------------------------------------------- command
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m mlkit.residuals")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--run", help="run id of the registry (its pipeline is re-fitted, or its saved predictions reused)")
    g.add_argument("--pipeline", help="pipeline module, e.g. model/pipeline.py")
    ap.add_argument("--top-k", type=int, default=8, help="pairs among the K best columns (0 = all columns)")
    ap.add_argument("--permutations", type=int, default=30)
    ap.add_argument("--max-rows", type=int, default=300_000, help="analysis on a random sample of the window rows")
    args = ap.parse_args(argv)

    role = os.environ.get("OSML_ROLE", "explorer")
    if role not in ALLOWED_ROLES:
        print(f"ROLE REFUSED : {role} has no residual-analysis access (allowed roles: {', '.join(sorted(ALLOWED_ROLES))}).",
              file=sys.stderr)
        return 9
    frame, registry = config.load_frame(), config.load_features()
    spec = frame["spec"]
    if not gate.require("run"):
        return 7
    problems = dq.manifest_problems()
    header = pd.read_csv(config.DEV_DIR / "features.csv.gz", nrows=0).columns
    unknown = [c for c in header if c not in registry]
    if unknown:
        problems.append(f"columns missing de features.yaml : {', '.join(unknown)}")
    if problems:
        print("NONCONFORMING DATA (D2/D5): " + " ; ".join(problems), file=sys.stderr)
        return 6

    run = None
    if args.run:
        run = next((r for r in config.read_jsonl(config.REGISTRY_FILE) if r["run_id"] == args.run), None)
        if run is None or run.get("status") not in ("exploratory", "reference", "reference_secondary"):
            print(f"UNKNOWN OR UNANALYZABLE RUN : {args.run} (exploratory runs and references only; "
                  "a null test has a permuted target)", file=sys.stderr)
            return 2
        path = run["pipeline"]
        module = reference.module(spec) if path.startswith("frame:") else core.load_pipeline(path)
    else:
        path = args.pipeline
        module = core.load_pipeline(path)
    bad = core.feature_violations(list(module.FEATURES), registry)
    if bad:
        print("PIPELINE REFUSED (I5):\n  " + "\n  ".join(bad), file=sys.stderr)
        return 4

    df = core.load_dev(spec)
    data_hash = "-".join(config.sha256_file(p) for p in core.dev_files())
    preds = cached_predictions(run, df, spec, data_hash) if run else None
    reused = preds is not None
    if run and not reused:
        print(f"note: predictions for {args.run} missing or stale (code or data changed): pipeline refitted per window.",
              file=sys.stderr)
    if preds is None:
        preds = oos_predictions(module, df, spec)
    if len(preds) > args.max_rows:
        preds = preds.sample(args.max_rows, random_state=0).sort_index()

    columns = [c for c, e in registry.items() if c in df.columns and e.get("available") == "origination"
               and not e.get("excluded_by") and c != spec["target_col"]]
    # D6 suspects (predict the target alone too well, no leak_ack) are not scanned: otherwise a leak tops
    # every report and becomes hypothesis 1 (eval XP, 2026-10-12)
    from . import dataquality as _dq, reference as _ref
    strength, _ = _dq.used_strength(df, columns, spec)
    sus, _ = _dq.leak_suspects(strength, registry, exempt=_ref.columns(spec))
    sus = [x.split(" (AUC")[0] for x in sus]
    if sus:
        print("unanalyzed columns (D6, suspected leakage): " + ", ".join(sus))
        columns = [c for c in columns if c not in sus]
    res = analyse(df, preds, columns, set(module.FEATURES), args.top_k, args.permutations)

    previous = config.read_jsonl(LEDGER)
    res_id = f"res-{len(previous) + 1:04d}"
    stem = args.run or res_id
    res.update(res_id=res_id, target=args.run or path, pipeline=path, role=role,
               code_hash=core.code_hash(path), data_hash=data_hash, frame_hash=config.frame_hash(),
               predictions_reused=reused, time=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
    res["hypotheses"] = hypotheses(res["entries"], res_id)
    mpath, jpath = write_reports(res, stem)
    signals = [e for e in res["entries"] if e["status"] == "signal"]
    config.append_jsonl(LEDGER, {
        "res_id": res_id, "time": res["time"], "role": role, "run_id": args.run, "pipeline": path,
        "code_hash": res["code_hash"], "data_hash": data_hash, "frame_hash": res["frame_hash"],
        "permutations": args.permutations, "top_k": args.top_k, "n_signal": len(signals),
        "signals": [" × ".join(e["columns"]) for e in signals], "hypotheses": [h["id"] for h in res["hypotheses"]],
        "report": str(mpath.relative_to(config.ROOT))})
    print(f"{res_id} : {len(signals)} signal(s) restant(s) au-dessus du floor du chance · "
          f"{mpath.relative_to(config.ROOT)} (no budget spent)")
    for e in signals[:5]:
        print(f"   {' × '.join(e['columns'])} : {e['gain']:+.3f} mnats/loan (global floor {e['floor_family']:.3f}) · {e['shape']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
