"""Unlabeled drift between a training period and a target period.

    python -m mlkit.drift --target window:2015-01..2015-06 [--pipeline model/x.py | --run r-0004]
    python -m mlkit.drift --target recent [--run r-0004]
    python -m mlkit.drift --target holdout --prereg preregistrations/c-001.yaml

The reference uses the development months available before the target minus the
label-maturity gap. No target labels are read. Reported indicators describe a
population shift rather than measuring lost model gain. Concept drift is not
identifiable from unlabeled inputs alone. E4 therefore requires a matching report
before holdout reading but treats its verdict as informative by default.

Checks include category/code schema changes, potentially permuted encodings,
monthly series outside training support, univariate tests with Bonferroni and
effect-size thresholds, adversarial classification, score drift (BBSD), and
acceptance shifts at the frozen threshold. Neutralizing a flagged model feature
compares decisions with values sampled from its training distribution.

A BROKEN CONTRACT indicates probable recoding, changed type, or missing target
columns. REVIEW marks material distribution shifts, new categories, missingness,
adversarial discrimination, or decision shifts. Neither verdict quantifies gain
loss. Monthly-constant series are excluded from adversarial and univariate tests.

When evaluation.drift_blocking is true, a broken holdout contract requires an
explicit signed DRIFT-ACK. Holdout access remains a human-only operation.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys

import numpy as np
import pandas as pd

from . import config, core, dataquality as dq

DEFAULTS = {
    "drift_alpha": 0.01,              # Global error rate, Bonferroni across columns.
    "drift_wasserstein": 0.10,        # Wasserstein distance / reference IQR.
    "drift_share_abs": 0.05,          # Absolute change in a category share.
    "drift_share_ratio": 1.5,         # And ratio of shares.
    "drift_new_share": 0.01,          # Unseen category share; out-of-support series share.
    "drift_recode_overlap": 0.50,     # Category overlap below which a recoding is suspected.
    "drift_permuted_share": 0.50,     # Target share whose profile points to another category: permuted recoding.
    "drift_profile_min_share": 0.02,  # Categories included in profiles: minimum share on both sides.
    "drift_profile_ratio": 2.0,       # Distance to the same category exceeds ratio times distance to the closest different category.
    "drift_missing_abs": 0.05,        # Missingness rate difference.
    "drift_adversarial_auc": 0.60,    # AUC adversarial
    "drift_approval_shift": 0.05,     # Acceptance-rate shift at the frozen threshold.
    "drift_code_levels": 20,          # Numeric columns with <= 20 values are also treated as codes.
    "drift_max_rows": 20000,          # Rows per period for the adversarial classifier.
    "drift_bbsd_max_rows": 150000,    # Training rows for out-of-fold scores (BBSD): random sampling above this limit.
}
MAJOR = "BROKEN CONTRACT"
LEVELS = ["OK", "REVIEW", MAJOR]
LEGACY_MAJOR = "BLOQUANT"             # Level name in readings recorded before 2026-10-13.
CAVEAT = ("These indicators measure a population change between training and target, not a loss "
          "of gain: none predicted holdout gain loss (experiments 1 and 3), and concept drift "
          "(feature-target relationship) is invisible without labels. The verdict is informative.")


def settings() -> dict:
    q = dict(DEFAULTS)
    try:
        q.update(dq.quality_settings() or {})
    except FileNotFoundError:
        pass
    q.setdefault("psi_warn", 0.10)
    return q


def blocking(spec: dict) -> bool:
    """evaluation.drift_blocking (default false): a BROKEN CONTRACT on holdout then requires a signed DRIFT-ACK."""
    return bool((spec.get("evaluation") or {}).get("drift_blocking", False))


# ---------------------------------------------------------------- periods
def parse_target(target: str, spec: dict):
    """-> (name, kind, train_end, start, end) ; months as Periods (start/end None = to be read from data)."""
    gap = int(spec["backtest"]["gap_months"])
    if target == "holdout":
        train_end, start, end = core.holdout_window(spec)
        return "holdout", "holdout", train_end, start, end
    if target == "recent":
        return "recent", "recent", None, None, None
    m = re.fullmatch(r"window:(\d{4}-\d{2})\.\.(\d{4}-\d{2})", target)
    if not m:
        raise SystemExit("--target : holdout | recent | window:AAAA-MM..AAAA-MM")
    start, end = pd.Period(m.group(1), "M"), pd.Period(m.group(2), "M")
    if end < start:
        raise SystemExit("--target window: end precedes start")
    return f"window-{m.group(1)}..{m.group(2)}", "window", start - gap, start, end


def ids_identity(ids: pd.Series) -> str:
    """Same formula as mlkit.holdout.holdout_identity, computed from the FEATURES file."""
    return config.sha256_text("\n".join(sorted(set(ids.astype(str)))))


def load_periods(target: str, spec: dict):
    dev = dq.read_features(spec)
    name, kind, train_end, start, end = parse_target(target, spec)
    if kind == "recent":
        last = dev["_month"].max()
        train_end, start, end = last - int(spec["backtest"]["gap_months"]), None, last
        start = train_end + 1
    ref = dev[dev["_month"] <= train_end]
    if kind == "holdout":
        d = config.holdout_dir()
        tgt = pd.read_csv(d / "features.csv.gz", low_memory=False)     # never labels.csv.gz
        tgt["_month"] = pd.PeriodIndex(tgt[spec["time_col"]].astype(str), freq="M")
        tgt = core.align_like(tgt, dev)
        identity = ids_identity(tgt[spec["id_col"]])
        tgt = tgt[(tgt["_month"] >= start) & (tgt["_month"] <= end)]
    else:
        if end > dev["_month"].max():
            raise SystemExit(f"--target {target} : end {end} after development ends ({dev['_month'].max()}) ; "
                             "Read the holdout period with --target holdout (human only)")
        tgt = dev[(dev["_month"] >= start) & (dev["_month"] <= end)]
        identity = ids_identity(tgt[spec["id_col"]])
    if len(ref) < 200 or len(tgt) < 200:
        raise SystemExit(f"periods too small: reference {len(ref)} rows (<= {train_end}), cible {len(tgt)}")
    return {"name": name, "kind": kind, "train_end": str(train_end), "start": str(start), "end": str(end),
            "identity": identity}, ref.reset_index(drop=True), tgt.reset_index(drop=True)


# ---------------------------------------------------------------- statistics
def as_codes(s: pd.Series) -> pd.Series:
    """Text codes, NaN kept; 2.0 -> "2" so that a CSV read as float compares with a text code."""
    def one(x):
        if pd.isna(x):
            return np.nan
        if isinstance(x, (float, np.floating)) and float(x).is_integer():
            return str(int(x))
        return str(x)
    return s.map(one).astype(object)


def is_categorical(col: str, ref: pd.Series, registry: dict) -> bool:
    t = registry.get(col, {}).get("contract", {}).get("type")
    if t:
        return t == "categorical"
    return not (pd.api.types.is_numeric_dtype(ref) and not pd.api.types.is_bool_dtype(ref))


def is_monthly_series(s: pd.Series, months: pd.Series | None) -> bool:
    """A numeric column constant inside each month of the training period, with >= 2 distinct values over
    >= 2 months: a monthly series (macro indicator), not a code — its future values are new by nature."""
    if months is None:
        return False
    x = pd.to_numeric(s, errors="coerce")
    ok = x.notna().to_numpy()
    if ok.sum() == 0 or x[ok].nunique() < 2:
        return False
    per = x[ok].groupby(np.asarray(months)[ok]).nunique()
    return len(per) >= 2 and int(per.max()) <= 1


def out_of_support(ref: pd.Series, tgt: pd.Series) -> dict:
    r, t = pd.to_numeric(ref, errors="coerce").dropna(), pd.to_numeric(tgt, errors="coerce").dropna()
    lo, hi = float(r.min()), float(r.max())
    share = float(((t < lo) | (t > hi)).mean()) if len(t) else 0.0
    return {"min_ref": lo, "max_ref": hi, "min_target": float(t.min()) if len(t) else None,
            "max_target": float(t.max()) if len(t) else None, "share_outside": share}


def schema(ref: pd.Series, tgt: pd.Series, q: dict) -> dict:
    """Contract of a code column: what the target contains that training never saw, and the reverse."""
    r, t = as_codes(ref), as_codes(tgt)
    rs, ts = r.value_counts(normalize=True), t.value_counts(normalize=True)
    new = ts[~ts.index.isin(rs.index)]
    gone = rs[~rs.index.isin(ts.index)]
    overlap = float(min(1 - new.sum(), 1 - gone.sum())) if len(rs) and len(ts) else 0.0
    idx = rs.index.union(ts.index)
    p, c = rs.reindex(idx, fill_value=0.0), ts.reindex(idx, fill_value=0.0)
    ratio = (np.maximum(p, c) + 1e-9) / (np.minimum(p, c) + 1e-9)
    moved = [(str(k), float(p[k]), float(c[k])) for k in idx
             if abs(c[k] - p[k]) > q["drift_share_abs"] and ratio[k] > q["drift_share_ratio"]
             and k not in new.index and k not in gone.index]
    return {"n_ref_levels": int(len(rs)), "n_target_levels": int(len(ts)),
            "new": {str(k): float(v) for k, v in new.sort_values(ascending=False).head(10).items()},
            "new_share": float(new.sum()),
            "gone": {str(k): float(v) for k, v in gone.sort_values(ascending=False).head(10).items()},
            "gone_share": float(gone.sum()), "overlap": overlap,
            "missing_ref": float(r.isna().mean()), "missing_target": float(t.isna().mean()),
            "moved": sorted(moved, key=lambda m: -abs(m[2] - m[1]))[:10]}


def permuted_recoding(ref: pd.DataFrame, tgt: pd.DataFrame, col: str, others: list[str], cats: set[str], q: dict) -> dict | None:
    """Recoding with the SAME symbols (a permutation): invisible to the schema contract (overlap 100 %).
    Each modality is described by the profile of the other columns (missing rate of each, mean standardised by
    the training period for the numeric ones). A target modality whose profile is much closer to ANOTHER training
    modality (d(same) > drift_profile_ratio × d(nearest other)) points to a permutation; `share` = part of the
    target in such modalities. Prototype: scratchpad exp3/drift_proto.py."""
    if not others:
        return None
    r, t = as_codes(ref[col]), as_codes(tgt[col])
    rs, ts = r.value_counts(normalize=True), t.value_counts(normalize=True)
    mn = float(q["drift_profile_min_share"])
    ref_levels = [L for L in rs.index if rs[L] >= mn]
    common = [L for L in ts.index if ts[L] >= mn and rs.get(L, 0.0) >= mn]
    if len(ref_levels) < 2 or not common:
        return None
    num = [c for c in others if c not in cats]
    rn = ref[num].apply(pd.to_numeric, errors="coerce")
    tn = tgt[num].apply(pd.to_numeric, errors="coerce")
    mu, sd = rn.mean(), rn.std().replace(0, 1).fillna(1)
    rmiss, tmiss = ref[others].isna(), tgt[others].isna()

    def prof(miss, numeric, codes, L):
        """(profile, variance of each component within the modality, rows)"""
        m = (codes == L).to_numpy()
        z = (numeric[m] - mu) / sd
        mi = miss[m].mean().to_numpy(dtype=float)
        return (np.r_[mi, z.mean().fillna(0).to_numpy(dtype=float)],
                np.r_[mi * (1 - mi), z.var().fillna(0).to_numpy(dtype=float)], int(m.sum()))
    pr = {L: prof(rmiss, rn, r, L) for L in ref_levels}
    rows, share = [], 0.0
    ratio = float(q["drift_profile_ratio"])
    for L in common:
        pt, vt, nt = prof(tmiss, tn, t, L)
        d = {K: float(np.linalg.norm(pt - v[0])) for K, v in pr.items()}
        near = min((K for K in d if K != L), key=d.get)
        # sampling noise of d(same): without it, two modalities with the same profile (d ~ noise on both sides)
        # would point to each other by chance
        _, vr, nr = pr[L]
        noise = float(np.sqrt(np.sum((vr + vt) / 2 * (1 / max(nr, 1) + 1 / max(nt, 1)))))
        flag = d[L] > ratio * d[near] and d[L] > 3 * noise
        share += float(ts[L]) if flag else 0.0
        rows.append({"level": str(L), "share_target": float(ts[L]), "nearest_other": str(near),
                     "d_same": d[L], "d_nearest_other": d[near], "noise": noise, "points_elsewhere": bool(flag)})
    return {"share": share, "levels": rows}


def univariate(ref: pd.Series, tgt: pd.Series, categorical: bool) -> dict:
    from scipy import stats
    if categorical:
        r, t = as_codes(ref).fillna("<missing>"), as_codes(tgt).fillna("<missing>")
        tab = pd.concat([r.value_counts(), t.value_counts()], axis=1).fillna(0).to_numpy()
        n = tab.sum()
        exp_ = tab.sum(1, keepdims=True) * tab.sum(0, keepdims=True) / n
        rare = exp_.min(1) < 5                       # merge rare modalities so chi2 stays valid
        if rare.any():
            tab = np.vstack([tab[~rare], tab[rare].sum(0, keepdims=True)])
            tab = tab[tab.sum(1) > 0]
        if tab.shape[0] < 2:
            return {"test": "chi2", "p": 1.0, "psi": 0.0, "cramer_v": 0.0}
        chi2, p, _, _ = stats.chi2_contingency(tab, correction=False)
        v = float(np.sqrt(chi2 / (n * (min(tab.shape) - 1))))
        return {"test": "chi2", "p": float(p), "psi": dq.psi(r, t, numeric=False), "cramer_v": v}
    r, t = pd.to_numeric(ref, errors="coerce").dropna(), pd.to_numeric(tgt, errors="coerce").dropna()
    if len(r) < 2 or len(t) < 2:
        return {"test": "ks", "p": 1.0, "psi": 0.0, "wasserstein_norm": 0.0}
    p = float(stats.ks_2samp(r, t).pvalue)
    iqr = float(np.subtract(*np.nanquantile(r, [0.75, 0.25])))
    scale = iqr if iqr > 0 else float(r.std() or 1.0)
    w = float(stats.wasserstein_distance(r, t) / scale)
    return {"test": "ks", "p": p, "psi": dq.psi(ref, tgt, numeric=True), "wasserstein_norm": w}


def encode(ref: pd.DataFrame, tgt: pd.DataFrame, cols: list[str], cats: set[str]) -> tuple[np.ndarray, np.ndarray]:
    both = pd.concat([ref[cols], tgt[cols]], ignore_index=True)
    X = np.empty((len(both), len(cols)))
    for j, c in enumerate(cols):
        if c in cats:
            codes = pd.Categorical(as_codes(both[c])).codes.astype(float)
            codes[codes < 0] = np.nan
            X[:, j] = codes
        else:
            X[:, j] = pd.to_numeric(both[c], errors="coerce").to_numpy(dtype=float)
    y = np.r_[np.zeros(len(ref)), np.ones(len(tgt))]
    return X, y


def adversarial(ref: pd.DataFrame, tgt: pd.DataFrame, cols: list[str], cats: set[str], q: dict, seed: int = 0) -> dict:
    """Can a classifier tell the training period from the target? AUC ~ 0.5 expected."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.inspection import permutation_importance
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import StratifiedKFold
    rng = np.random.default_rng(seed)
    cap = int(q["drift_max_rows"])
    ref = ref.iloc[rng.permutation(len(ref))[:cap]]
    tgt = tgt.iloc[rng.permutation(len(tgt))[:cap]]
    X, y = encode(ref, tgt, cols, cats)
    oof = np.zeros(len(y))
    imp = np.zeros(len(cols))
    for tr, te in StratifiedKFold(5, shuffle=True, random_state=seed).split(X, y):
        m = HistGradientBoostingClassifier(max_iter=100, learning_rate=0.1, max_leaf_nodes=15,
                                           min_samples_leaf=50, random_state=seed).fit(X[tr], y[tr])
        oof[te] = m.predict_proba(X[te])[:, 1]
        imp += permutation_importance(m, X[te], y[te], scoring="roc_auc", n_repeats=2,
                                      random_state=seed).importances_mean / 5
    auc = float(roc_auc_score(y, oof))
    top = sorted(zip(cols, imp), key=lambda t: -t[1])[:10]
    return {"auc": auc, "n_ref": int(len(ref)), "n_target": int(len(tgt)),
            "top": [{"column": c, "importance": float(v)} for c, v in top]}


# ---------------------------------------------------------------- analysis (pure, on frames)
def analyse(ref: pd.DataFrame, tgt: pd.DataFrame, cols: list[str], registry: dict, q: dict | None = None,
            with_adversarial: bool = True) -> dict:
    q = q or settings()
    alpha = q["drift_alpha"] / max(len(cols), 1)          # Bonferroni
    findings, per_col, cats, series = [], {}, set(), set()
    months = ref["_month"] if "_month" in ref.columns else None

    def add(level, col, rule, detail):
        findings.append({"level": level, "column": col, "rule": rule, "detail": detail})

    present = []
    for c in cols:
        if c not in tgt.columns or tgt[c].isna().all():
            add(MAJOR, c, "column missing", "missing or entirely empty in the target")
            continue
        if c not in ref.columns or ref[c].isna().all():
            add(MAJOR, c, "column missing", "missing or empty in training")
            continue
        present.append(c)
        cat = is_categorical(c, ref[c], registry)
        if cat:
            cats.add(c)
        entry = {"type": "categorical" if cat else "numeric"}
        if not cat:                                      # text in a numeric column: the coding changed
            def bad(s):
                nn = s.dropna()
                return float(pd.to_numeric(nn, errors="coerce").isna().mean()) if len(nn) else 0.0
            b_ref, b_tgt = bad(ref[c]), bad(tgt[c])
            entry["non_numeric_target"] = b_tgt
            if b_tgt - b_ref > 0.01:
                add(MAJOR, c, "changed type", f"{b_tgt:.1%} nonnumeric target values "
                                             f"(training {b_ref:.1%}) : recoding probable")
        uni = univariate(ref[c], tgt[c], cat)
        entry.update(uni)
        mr, mt = float(ref[c].isna().mean()), float(tgt[c].isna().mean())
        entry["missing_ref"], entry["missing_target"] = mr, mt
        if abs(mt - mr) > q["drift_missing_abs"]:
            add("REVIEW", c, "missing", f"{mr:.1%} → {mt:.1%}")
        if not cat and is_monthly_series(ref[c], months):
            # a monthly series: its new values are expected; only values outside the training support matter
            series.add(c)
            sup = out_of_support(ref[c], tgt[c])
            entry.update(type="monthly_series", support=sup, flagged=sup["share_outside"] > q["drift_new_share"])
            if entry["flagged"]:
                add("REVIEW", c, "monthly series outside training support",
                    f"{sup['share_outside']:.1%} target values outside training support "
                    f"[{sup['min_ref']:g} ; {sup['max_ref']:g}] (cible [{sup['min_target']:g} ; {sup['max_target']:g}])")
            per_col[c] = entry
            continue
        codes = cat or pd.to_numeric(ref[c], errors="coerce").nunique() <= q["drift_code_levels"]
        sig = uni["p"] < alpha
        if codes:
            sc = schema(ref[c], tgt[c], q)
            entry["schema"] = sc
            if sc["overlap"] < q["drift_recode_overlap"]:
                add(MAJOR, c, "recoding probable",
                    f"category overlap {sc['overlap']:.0%} (threshold {q['drift_recode_overlap']:.0%}) ; "
                    f"nouvelles : {list(sc['new'])[:5]} ; disparues : {list(sc['gone'])[:5]}")
            else:
                if sc["new_share"] > q["drift_new_share"]:
                    add("REVIEW", c, "new categories",
                        f"{sc['new_share']:.1%} of the target: {list(sc['new'])[:5]}")
                if sc["moved"] and sig:
                    add("REVIEW", c, "category share",
                        "; ".join(f"{k} {a:.1%} → {b:.1%}" for k, a, b in sc["moved"][:3]))
        effect = uni["psi"] > q["psi_warn"] or uni.get("wasserstein_norm", 0.0) > q["drift_wasserstein"]
        if sig and effect:
            add("REVIEW", c, "univariate drift",
                f"{uni['test']} p={uni['p']:.1e} (threshold Bonferroni {alpha:.1e}), PSI {uni['psi']:.2f}"
                + (f", W/IQR {uni['wasserstein_norm']:.2f}" if "wasserstein_norm" in uni else f", V {uni['cramer_v']:.2f}"))
        entry["flagged"] = bool(sig and effect)
        per_col[c] = entry
    # permuted recoding: categoricals whose symbols are kept (a disjoint recoding is already caught above)
    for c in sorted(cats):
        sc = per_col[c].get("schema")
        if sc is None or sc["overlap"] < q["drift_recode_overlap"]:
            continue
        others = [o for o in present if o != c and o not in series]
        pm = permuted_recoding(ref, tgt, c, others, cats, q)
        if pm is None:
            continue
        per_col[c]["profile"] = pm
        moved = [x for x in pm["levels"] if x["points_elsewhere"]]
        detail = "; ".join(f"{x['level']} resembles {x['nearest_other']} (d {x['d_nearest_other']:.2f} contre "
                           f"{x['d_same']:.2f})" for x in moved[:4])
        if pm["share"] > q["drift_permuted_share"]:
            add(MAJOR, c, "probable permuted recoding",
                f"{pm['share']:.0%} target values in categories whose profiles point to another category: {detail}")
        elif pm["share"] > q["drift_share_abs"]:
            add("REVIEW", c, "category profile",
                f"{pm['share']:.0%} target values in categories whose profiles point to another category: {detail}")
    adv = None
    adv_cols = [c for c in present if c not in series]
    if with_adversarial and adv_cols:
        adv = adversarial(ref, tgt, adv_cols, cats, q)
        adv["excluded_series"] = sorted(series)
        if adv["auc"] > q["drift_adversarial_auc"]:
            add("REVIEW", None, "classifieur adversarial",
                f"AUC {adv['auc']:.3f} > {q['drift_adversarial_auc']}; most discriminating columns: "
                + ", ".join(t["column"] for t in adv["top"][:3]))
    return {"columns": per_col, "findings": findings, "adversarial": adv, "alpha_bonferroni": alpha,
            "monthly_series": sorted(series),
            "n_ref": int(len(ref)), "n_target": int(len(tgt)), "verdict": verdict(findings)}


def verdict(findings: list[dict]) -> str:
    return max((f["level"] for f in findings), key=LEVELS.index, default="OK")


def flagged_columns(rep: dict) -> list[str]:
    out = []
    for f in rep["findings"]:
        if f["column"] and f["column"] not in out:
            out.append(f["column"])
    return out


# ---------------------------------------------------------------- (d) model score (BBSD) and decision
def score_shift(module, spec: dict, run_id: str | None, train_end, tgt: pd.DataFrame, code_hash: str, q: dict,
                neutralise: list[str] = (), seed: int = 0) -> dict:
    """Fit on dev <= train_end (dev labels only), score the target (features only).
    Reference distribution: out-of-fold scores on the training period (in-sample scores would be optimistic).
    `neutralise`: columns replaced, one at a time, by a draw from their training distribution; the shift of the
    approval rate at the frozen threshold says how much of the decision moves BECAUSE of that column."""
    from scipy import stats
    from sklearn.model_selection import KFold
    dev = core.load_dev(spec)
    tr = dev[dev["_month"] <= pd.Period(train_end, "M")].reset_index(drop=True)
    cap = int(q.get("drift_bbsd_max_rows", 150_000))
    n_train_full = len(tr)
    if len(tr) > cap:                       # Four pipeline fits (3 folds + 1): monitor memory and time on large panels.
        tr = tr.sample(cap, random_state=seed).reset_index(drop=True)
    y = tr[spec["target_col"]].to_numpy()
    feats = list(module.FEATURES)
    oof = np.zeros(len(tr))
    for a, b in KFold(3, shuffle=True, random_state=0).split(tr):
        oof[b] = core.fit_predict(module, tr.loc[a, feats], y[a], tr.loc[b, feats])
    s_tgt, model = core.fit_predict_model(module, tr[feats], y, tgt[feats])
    rate = float(spec.get("evaluation", {}).get("decision_rate", 0.9))
    thr, source = float(np.quantile(oof, rate)), f"quantile {rate:.0%} training out-of-fold scores"
    ev = config.REPORTS_DIR / f"eval-{run_id}.json" if run_id else None
    if ev is not None and ev.exists():
        e = json.loads(ev.read_text(encoding="utf-8"))
        if e.get("code_hash") == code_hash and e.get("threshold"):
            thr, source = float(e["threshold"]["mean"]), f"threshold frozen on validation (eval-{run_id})"
    acc_r, acc_t = oof <= thr, s_tgt <= thr
    iqr = float(np.subtract(*np.quantile(oof, [0.75, 0.25]))) or float(oof.std() or 1.0)

    def implied(s, a):      # model-implied default rate among accepted: valid only if calibration holds
        return float(s[a].mean()) if a.any() else float("nan")
    out = {"threshold": thr, "threshold_source": source, "train_rows_used": int(len(tr)), "train_rows_total": int(n_train_full),
           "ks_p": float(stats.ks_2samp(oof, s_tgt).pvalue),
           "wasserstein_norm": float(stats.wasserstein_distance(oof, s_tgt) / iqr),
           "psi": dq.psi(pd.Series(oof), pd.Series(s_tgt), numeric=True),
           "mean_ref": float(oof.mean()), "mean_target": float(s_tgt.mean()),
           "approval_ref": float(acc_r.mean()), "approval_target": float(acc_t.mean()),
           "implied_bad_accepted_ref": implied(oof, acc_r), "implied_bad_accepted_target": implied(s_tgt, acc_t)}
    # expected defaults among accepted, per 1000 applicants; and the part of the change due to the volume
    # accepted (approval shift) vs. the risk of who is accepted (mix shift)
    e_ref = out["approval_ref"] * out["implied_bad_accepted_ref"] * 1000
    e_tgt = out["approval_target"] * out["implied_bad_accepted_target"] * 1000
    vol = (out["approval_target"] - out["approval_ref"]) * out["implied_bad_accepted_ref"] * 1000
    out.update(expected_bad_per_1000_ref=e_ref, expected_bad_per_1000_target=e_tgt,
               expected_bad_change=e_tgt - e_ref, part_volume=vol, part_mix=(e_tgt - e_ref) - vol)
    neu = {}
    for c in neutralise:
        if c not in feats:
            continue
        X = tgt[feats].copy()
        draw = tr[c].sample(len(X), replace=True, random_state=seed).to_numpy()
        X[c] = pd.Series(draw, index=X.index, dtype=tr[c].dtype)
        a = float((model.predict_proba(X)[:, 1] <= thr).mean())
        neu[c] = {"approval_target": out["approval_target"], "approval_neutralised": a,
                  "shift": out["approval_target"] - a}
    out["neutralised"] = neu
    return out


# ---------------------------------------------------------------- report
def fingerprint(rep: dict) -> str:
    key = {k: rep.get(k) for k in ("target", "dev_hash", "restricted", "verdict")}
    key["blocking"] = sorted(f"{f['column']}:{f['rule']}" for f in rep["findings"] if f["level"] == MAJOR)
    return config.sha256_text(json.dumps(key, sort_keys=True, ensure_ascii=False, default=str))


def summary(rep: dict) -> dict:
    """Short form, carried by the holdout reading (ledger), its report and the model card."""
    n = {lvl: sum(1 for f in rep["findings"] if f["level"] == lvl) for lvl in LEVELS[1:]}
    lines = [f"Informative drift verdict: {rep['verdict']} · {n[MAJOR]} contract(s) rompu(s), "
             f"{n['REVIEW']} constat(s) to examine · fingerprint {rep['fingerprint']}"]
    lines += [f"{f['level']} · {f['column'] or '(all)'} · {f['rule']} : {f['detail']}"
              for f in sorted(rep["findings"], key=lambda f: -LEVELS.index(f["level"]))[:6]]
    if len(rep["findings"]) > 6:
        lines.append(f"… {len(rep['findings']) - 6} other findings : reports/drift-{rep['target']['name']}.md")
    s = rep.get("score")
    if s:
        lines.append(f"Acceptation au threshold {s['approval_ref']:.1%} (training, outside pli) → {s['approval_target']:.1%} (cible)")
        for c, v in s.get("neutralised", {}).items():
            lines.append(f"Neutraliser {c} : acceptation {v['approval_target']:.1%} → {v['approval_neutralised']:.1%} "
                         f"(column shifts the decision by {v['shift']:+.1%})")
    lines.append(CAVEAT)
    return {"verdict": rep["verdict"], "counts": n, "lines": lines}


def markdown(rep: dict) -> str:
    t = rep["target"]
    lines = [f"# Drift — target {t['name']}", "",
             f"> {CAVEAT}", "",
             f"- Training : dev ≤ {t['train_end']} ({rep['n_ref']} rows) · cible : {t['start']}..{t['end']} "
             f"({rep['n_target']} rows); no target label read",
             f"- Columns : {len(rep['columns'])}" + (f" (pipeline {rep['restricted']['pipeline']}, code {rep['restricted']['code_hash']})"
                                                       if rep.get("restricted") else " (all origination columns)"),
             f"- **Verdict : {rep['verdict']}** (informatif) · fingerprint `{rep['fingerprint']}`", ""]
    if rep["verdict"] == MAJOR and t["kind"] == "holdout" and rep.get("blocking"):
        lines += [f"Holdout access refused (E4, evaluation.drift_blocking: true) until decisions.md contains "
                  f"a line DRIFT-ACK {rep['fingerprint']} — <reason> — Signed: <name>.", ""]
    lines += ["## Constats", ""]
    lines += [f"- **{f['level']}** · {f['column'] or '(all)'} · {f['rule']} : {f['detail']}" for f in rep["findings"]] or ["- none"]
    lines += ["", "## Schema contract (codes)", "",
              "| column | training/target categories | new (share) | disappeared (share) | overlap | profile points to another category | missing |",
              "|---|---|---|---|---|---|---|"]
    for c, e in rep["columns"].items():
        s = e.get("schema")
        if s:
            pm = e.get("profile")
            lines.append(f"| {c} | {s['n_ref_levels']}/{s['n_target_levels']} | {s['new_share']:.1%} {list(s['new'])[:3]} | "
                         f"{s['gone_share']:.1%} {list(s['gone'])[:3]} | {s['overlap']:.0%} | "
                         f"{(format(pm['share'], '.0%') if pm else '—')} | {s['missing_ref']:.1%} → {s['missing_target']:.1%} |")
    ser = [(c, e) for c, e in rep["columns"].items() if e.get("type") == "monthly_series"]
    if ser:
        lines += ["", "## Monthly series (constant within each month: neither codes nor univariate tests; excluded from adversarial analysis)", "",
                  "| column | support appr. | cible | part outside support |", "|---|---|---|---|"]
        lines += [f"| {c} | [{e['support']['min_ref']:g} ; {e['support']['max_ref']:g}] | "
                  f"[{e['support']['min_target']:g} ; {e['support']['max_target']:g}] | {e['support']['share_outside']:.1%} |"
                  for c, e in ser]
    lines += ["", f"## Univariate tests (Bonferroni: p < {rep['alpha_bonferroni']:.1e}, with effect above threshold)", "",
              "| column | test | p | PSI | effect | flagged |", "|---|---|---|---|---|---|"]
    for c, e in sorted(((c, e) for c, e in rep["columns"].items() if e.get("type") != "monthly_series"),
                       key=lambda kv: -kv[1]["psi"]):
        eff = f"W/IQR {e['wasserstein_norm']:.3f}" if "wasserstein_norm" in e else f"V {e.get('cramer_v', 0):.3f}"
        lines.append(f"| {c} | {e['test']} | {e['p']:.1e} | {e['psi']:.3f} | {eff} | {'yes' if e['flagged'] else ''} |")
    a = rep.get("adversarial")
    if a:
        lines += ["", f"## Classifieur adversarial (training vs cible)", "",
                  f"AUC {a['auc']:.3f} (0,5 = indiscernables ; threshold {rep['settings']['drift_adversarial_auc']}) · "
                  f"{a['n_ref']} + {a['n_target']} rows"
                  + (f" · monthly series excluded: {', '.join(a['excluded_series'])}" if a.get("excluded_series") else ""),
                  "", "| column | importance (loss d'AUC) |", "|---|---|"]
        lines += [f"| {x['column']} | {x['importance']:.4f} |" for x in a["top"]]
    s = rep.get("score")
    if s:
        lines += ["", "## Model score (BBSD) and decision", "",
                  f"- Threshold: {s['threshold']:.4f} ({s['threshold_source']})",
                  f"- Score moyen {s['mean_ref']:.4f} → {s['mean_target']:.4f} · KS p={s['ks_p']:.1e} · "
                  f"PSI {s['psi']:.3f} · W/IQR {s['wasserstein_norm']:.3f}",
                  f"- Taux d'acceptation au threshold : {s['approval_ref']:.1%} → {s['approval_target']:.1%}",
                  f"- Expected defaults among accepted cases (model-based, conditional on calibration): "
                  f"{s['implied_bad_accepted_ref']:.2%} → {s['implied_bad_accepted_target']:.2%}",
                  f"- Expected defaults per 1000 applications: {s['expected_bad_per_1000_ref']:.1f} → "
                  f"{s['expected_bad_per_1000_target']:.1f} ({s['expected_bad_change']:+.1f}, including accepted volume "
                  f"{s['part_volume']:+.1f}, accepted composition {s['part_mix']:+.1f})"]
        if s.get("neutralised"):
            lines += ["", "### Decision effect of neutralizing a column", "",
                      "Each flagged column used by the model is replaced by a draw from its training "
                      "distribution while other columns retain target values; compare acceptance at the same threshold.", "",
                      "| column | acceptance (target) | acceptance (neutralized column) | column-attributable shift |",
                      "|---|---|---|---|"]
            lines += [f"| {c} | {v['approval_target']:.1%} | {v['approval_neutralised']:.1%} | {v['shift']:+.1%} |"
                      for c, v in s["neutralised"].items()]
    lines += ["", f"Niveaux : {MAJOR} = probable recoding (disjoint or permuted symbols), changed type, or missing column; "
              "REVIEW = significant drift above the effect threshold, new categories, changed category share or profile, "
              "monthly series outside support, missingness, adversarial AUC, or shifted acceptance. "
              "None of these levels measures a loss of gain."]
    return "\n".join(lines) + "\n"


def restriction(args, spec) -> tuple[object | None, dict | None, str | None]:
    """-> (pipeline module, restricted info, run id)."""
    run_id, path = args.run, args.pipeline
    if args.prereg:
        pre = config.load_yaml(config.ROOT / args.prereg)
        run_id, path = str(pre["run"]), pre["pipeline"]
    if run_id:
        runs = {r["run_id"]: r for r in config.read_jsonl(config.REGISTRY_FILE)}
        r = runs.get(run_id)
        if not r or "pipeline" not in r:
            raise SystemExit(f"run {run_id} absent du registry")
        if path and path != r["pipeline"]:
            raise SystemExit(f"run {run_id} : pipeline {r['pipeline']}, not {path}")
        path = r["pipeline"]
        if r.get("code_hash") and r["code_hash"] != core.code_hash(path):
            raise SystemExit(f"run {run_id} : {path} changed since the run; rerun it")
    if not path:
        return None, None, None
    module = core.load_pipeline(path)
    return module, {"pipeline": path, "code_hash": core.code_hash(path), "run": run_id}, run_id


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m mlkit.drift")
    ap.add_argument("--target", required=True, help="holdout (human) | recent | window:AAAA-MM..AAAA-MM")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--pipeline", help="restrict to this pipeline features")
    g.add_argument("--run", help="restricted to the run pipeline; adds score drift (BBSD)")
    g.add_argument("--prereg", help="preregistration: its run and pipeline (required by E4 for holdout)")
    args = ap.parse_args(argv)

    frame, registry = config.load_frame(), config.load_features()
    spec, q = frame["spec"], settings()
    module, restricted, run_id = restriction(args, spec)
    target, ref, tgt = load_periods(args.target, spec)
    if module is not None:
        cols = list(module.FEATURES)
    else:
        cols = [c for c, e in registry.items() if e.get("available") == "origination" and not e.get("excluded_by")
                and c in ref.columns and c not in (spec["id_col"], spec["time_col"])]
    rep = analyse(ref, tgt, cols, registry, q)
    if module is not None and run_id:
        sc = score_shift(module, spec, run_id, target["train_end"], tgt, restricted["code_hash"], q,
                         neutralise=[c for c in flagged_columns(rep) if c in tgt.columns])
        rep["score"] = sc
        if abs(sc["approval_target"] - sc["approval_ref"]) > q["drift_approval_shift"]:
            rep["findings"].append({"level": "REVIEW", "column": None, "rule": "decision shifted",
                                    "detail": f"acceptation au threshold {sc['approval_ref']:.1%} → {sc['approval_target']:.1%}"})
        rep["verdict"] = verdict(rep["findings"])
    block = blocking(spec)
    rep.update(target=target, restricted=restricted, dev_hash=config.sha256_file(config.DEV_DIR / "features.csv.gz"),
               frame_hash=config.frame_hash(), settings={k: q[k] for k in (*DEFAULTS, "psi_warn")},
               blocking=block, caveat=CAVEAT,
               time=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
    rep["fingerprint"] = fingerprint(rep)
    config.REPORTS_DIR.mkdir(exist_ok=True)
    out_json = config.REPORTS_DIR / f"drift-{target['name']}.json"     # not with_suffix: "..2015-06" has a dot
    out_md = config.REPORTS_DIR / f"drift-{target['name']}.md"
    out_json.write_text(json.dumps(rep, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    out_md.write_text(markdown(rep), encoding="utf-8")
    print(f"drift {target['name']} : {rep['verdict']} (informatif) · {len(rep['findings'])} constat(s) · "
          f"fingerprint {rep['fingerprint']} · {out_md.relative_to(config.ROOT)}")
    for f in rep["findings"]:
        print(f"  {f['level']} · {f['column'] or '(all)'} · {f['rule']} : {f['detail']}")
    for c, v in (rep.get("score") or {}).get("neutralised", {}).items():
        print(f"  neutraliser {c} : acceptation {v['approval_target']:.1%} → {v['approval_neutralised']:.1%}")
    print("  " + CAVEAT)
    return 3 if (block and rep["verdict"] == MAJOR) else 0


# ---------------------------------------------------------------- E4, used by mlkit.holdout and mlkit.checks
def acknowledged(fp: str) -> bool:
    p = config.ROOT / "decisions.md"
    text = p.read_text(encoding="utf-8") if p.exists() else ""
    return bool(re.search(rf"DRIFT-ACK {re.escape(fp)}\b.*Signed: \S+", text))


def require_for_holdout(prereg_path: str, code_hash: str, spec: dict) -> dict:
    """E4: a drift report on the holdout, restricted to the pre-registered pipeline, for this code, these dev data
    and this holdout, must exist. Its verdict is INFORMATIVE: it is returned (ledger, reading report, model card),
    it blocks nothing — unless evaluation.drift_blocking is true, where a BROKEN CONTRACT needs a signed DRIFT-ACK."""
    cmd = f"OSML_HOLDOUT_DIR=... python -m mlkit.drift --target holdout --prereg {prereg_path}"
    f = config.REPORTS_DIR / "drift-holdout.json"
    if not f.exists():
        raise SystemExit(f"E4: no holdout drift report. First run: {cmd}")
    rep = json.loads(f.read_text(encoding="utf-8"))
    r = rep.get("restricted") or {}
    stale = []
    if r.get("code_hash") != code_hash:
        stale.append("not restricted to the preregistered pipeline (or code version differs)")
    if rep.get("dev_hash") != config.sha256_file(config.DEV_DIR / "features.csv.gz"):
        stale.append("development data changed since calculation")
    d = config.holdout_dir()
    ids = pd.read_csv(d / "features.csv.gz", usecols=[spec["id_col"]])[spec["id_col"]]
    if rep.get("target", {}).get("identity") != ids_identity(ids):
        stale.append("different holdout")
    if stale:
        raise SystemExit("E4: drift report is stale (" + "; ".join(stale) + f"). Relance : {cmd}")
    fp = rep["fingerprint"]
    block = blocking(spec)
    major = rep["verdict"] in (MAJOR, LEGACY_MAJOR)
    ack = acknowledged(fp) if block else None
    if block and major and not ack:
        raise SystemExit(f"E4 (evaluation.drift_blocking: true) : {rep['verdict']} on holdout (reports/drift-holdout.md). "
                         f"Reading refused until decisions.md contains DRIFT-ACK {fp} — <reason> — Signed: <name>.")
    return {"fingerprint": fp, "verdict": rep["verdict"], "blocking": block, "ack": ack, "summary": summary(rep)}


if __name__ == "__main__":
    sys.exit(main())
