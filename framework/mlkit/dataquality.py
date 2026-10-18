"""Data-understanding computations shared by `mlkit.profile` and `mlkit.checks`.

Rule enforced here: anything that relates a column to the TARGET is computed only
on the exploration period (training part of the first backtest origin). Looking
at feature-target relations on the validation windows would be selection on the
validation data, which no run counter would ever see.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import KFold

from . import config, core

SENTINELS = [-1, 99, 999, 9999, 99999]   # 0 is a normal minimum for counts


def quality_settings() -> dict:
    return config.load_yaml(config.FEATURES_FILE).get("quality", {})


def exploration_end(spec: dict):
    """Last month usable for feature-target analysis."""
    return next(core.windows(spec))[1]


def read_features(spec: dict) -> pd.DataFrame:
    df = pd.read_csv(config.DEV_DIR / "features.csv.gz", low_memory=False)
    df["_month"] = pd.PeriodIndex(df[spec["time_col"]].astype(str), freq="M")
    return df


def months_with_volume(df: pd.DataFrame, min_rows: int) -> pd.Index:
    counts = df["_month"].value_counts()
    return counts[counts >= min_rows].index


# ---------------------------------------------------------------- D1 contract
def contract_violations(df: pd.DataFrame, registry: dict, min_rows: int) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    months = months_with_volume(df, min_rows)
    sub = df[df["_month"].isin(months)]
    for col, entry in registry.items():
        c = entry.get("contract")
        if not c or col not in df.columns or entry.get("excluded_by"):   # an excluded column cannot block runs (XP1)
            continue
        problems = []
        s = df[col]                      # types and ranges: every row
        if c.get("type") == "numeric":
            num = pd.to_numeric(s, errors="coerce")
            bad_type = int((num.isna() & s.notna()).sum())
            if bad_type:
                problems.append(f"{bad_type} nonnumeric values")
            if "min" in c and (num < c["min"]).any():
                problems.append(f"{int((num < c['min']).sum())} values < {c['min']} (observed min {num.min():g})")
            if "max" in c and (num > c["max"]).any():
                problems.append(f"{int((num > c['max']).sum())} values > {c['max']} (observed max {num.max():g})")
        elif c.get("type") == "categorical":
            vals = s.dropna().astype(str)
            if "allowed" in c:
                extra = sorted(set(vals) - {str(a) for a in c["allowed"]})
                if extra:
                    problems.append(f"values outside liste : {extra[:5]}{' …' if len(extra) > 5 else ''}")
            if "pattern" in c:
                bad = vals[~vals.str.match(c["pattern"])]
                if len(bad):
                    problems.append(f"{len(bad)} values outside motif {c['pattern']} (ex. {bad.iloc[0]!r})")
        if "max_missing" in c and len(sub):   # missing rate: months with enough rows only
            by_month = sub[col].isna().groupby(sub["_month"]).mean()
            worst = by_month.max()
            if worst > c["max_missing"]:
                problems.append(f"missingness up to {worst:.1%} en {by_month.idxmax()} (contract ≤ {c['max_missing']:.0%})")
        if problems:
            out[col] = problems
    return out


# ---------------------------------------------------------------- D4 stability
def psi(ref: pd.Series, cur: pd.Series, numeric: bool, bins: int = 10) -> float:
    eps = 1e-4
    if numeric:
        r, c = pd.to_numeric(ref, errors="coerce"), pd.to_numeric(cur, errors="coerce")
        edges = np.unique(np.nanquantile(r.dropna(), np.linspace(0, 1, bins + 1))) if r.notna().any() else np.array([])
        if r.nunique() <= bins:   # few distinct values (a monthly index, a count): compare values, not quantile bins (XP3)
            rb, cb = r.astype(str), c.astype(str)
        elif len(edges) < 2:
            rb, cb = r.isna().astype(str), c.isna().astype(str)
        else:
            edges[0], edges[-1] = -np.inf, np.inf
            rb = pd.cut(r, edges, duplicates="drop").astype(str)
            cb = pd.cut(c, edges, duplicates="drop").astype(str)
    else:
        rb, cb = ref.astype(str), cur.astype(str)
    p = rb.value_counts(normalize=True)
    q = cb.value_counts(normalize=True)
    idx = p.index.union(q.index)
    p, q = p.reindex(idx, fill_value=0) + eps, q.reindex(idx, fill_value=0) + eps
    return float(((q - p) * np.log(q / p)).sum())


def stability(df: pd.DataFrame, registry: dict, spec: dict) -> dict[str, dict]:
    end = exploration_end(spec)
    ref = df[df["_month"] <= end]
    out = {}
    for col in df.columns:
        if col in ("_month", spec["id_col"], spec["time_col"]):
            continue
        numeric = registry.get(col, {}).get("contract", {}).get("type") == "numeric" or (
            pd.api.types.is_numeric_dtype(df[col]) and not pd.api.types.is_bool_dtype(df[col]))   # True/False columns: categories (XP2)
        per = {}
        for name, _, start, stop in core.windows(spec):
            cur = df[(df["_month"] >= start) & (df["_month"] <= stop)]
            if len(cur) and len(ref):
                per[name] = psi(ref[col], cur[col], numeric)
        out[col] = {"per_window": per, "max": max(per.values()) if per else 0.0}
    return out


# ---------------------------------------------------------------- D6 univariate strength
def univariate_strength(df: pd.DataFrame, labels: pd.DataFrame, spec: dict) -> tuple[dict[str, float], str]:
    """max(AUC, 1 - AUC) of each column alone, on the exploration period only."""
    end = exploration_end(spec)
    d = df[df["_month"] <= end].merge(labels, on=spec["id_col"], how="inner")
    cols = [c for c in df.columns if c not in ("_month", spec["id_col"], spec["time_col"])]
    return strength_of(d, cols, d[spec["target_col"]].to_numpy()), str(end)


def used_strength(df: pd.DataFrame, cols: list[str], spec: dict) -> tuple[dict[str, float], str]:
    """Same measure for the columns a pipeline uses; df already carries the target (core.load_dev)."""
    end = exploration_end(spec)
    d = df[df["_month"] <= end]
    return strength_of(d, [c for c in cols if c in d.columns], d[spec["target_col"]].to_numpy()), str(end)


def strength_of(d: pd.DataFrame, cols: list[str], y: np.ndarray) -> dict[str, float]:
    out = {}
    if len(np.unique(y)) < 2:
        return out
    for col in cols:
        s = d[col]
        num = pd.to_numeric(s, errors="coerce")
        nonnull = s.notna()
        if not nonnull.any():
            continue
        if num[nonnull].notna().mean() >= 0.99:
            x = num.fillna(num.median()).to_numpy()
        else:
            # out-of-fold mean encoding: in-sample encoding would flag every high-cardinality column
            x = np.empty(len(d))
            cats = s.astype(str).to_numpy()
            for tr, te in KFold(5, shuffle=True, random_state=0).split(cats):
                means = pd.Series(y[tr]).groupby(cats[tr]).mean()
                x[te] = pd.Series(cats[te]).map(means).fillna(y[tr].mean()).to_numpy()
        try:
            auc = roc_auc_score(y, x)
            out[col] = float(max(auc, 1 - auc))
        except ValueError:
            continue
    return out


def leak_suspects(strength: dict[str, float], registry: dict, exempt=()) -> tuple[list[str], float]:
    """D6: columns that predict the target alone too well, without a human leak_ack.
    `exempt`: the score in place declared in the frame — a strong existing score is not a leak."""
    lim = quality_settings().get("univariate_auc_stop", 0.8)
    sus = [f"{c} (AUC {a:.2f})" for c, a in sorted(strength.items())
           if a >= lim and c not in exempt and not registry.get(c, {}).get("leak_ack")]
    return sus, lim


# ---------------------------------------------------------------- D5 provenance of the data
def manifest() -> dict | None:
    p = config.DEV_DIR / "manifest.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def decision_ids() -> set[str]:
    p = config.ROOT / "decisions.md"
    return set(re.findall(r"\bD-\d{3}\b", p.read_text(encoding="utf-8"))) if p.exists() else set()


def manifest_problems() -> list[str]:
    m = manifest()
    if m is None:
        return ["data/dev/manifest.json missing: data was generated outside tracked preparation"]
    problems = []
    script = config.ROOT / m["script"]
    if not script.exists():
        problems.append(f"preparation script not found: {m['script']}")
    elif config.sha256_file(script) != m["script_hash"]:
        problems.append(f"{m['script']} changed since data generation; rerun it")
    for name, h in m.get("outputs", {}).items():
        f = config.DEV_DIR / name
        if not f.exists() or config.sha256_file(f) != h:
            problems.append(f"data/dev/{name} changed outside the preparation script")
    known = decision_ids()
    tags = set(re.findall(r"DECISION (D-\d{3})", script.read_text(encoding="utf-8"))) if script.exists() else set()
    for step in m.get("steps", []):
        tags.add(step["decision"])
    missing = sorted(t for t in tags if t not in known)
    if missing:
        problems.append(f"cited decisions missing from decisions.md: {', '.join(missing)}")
    return problems
