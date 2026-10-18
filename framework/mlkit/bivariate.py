"""Initial statistical analysis WITH the target, and a selection rule applied mechanically.

    python -m mlkit.bivariate        # writes reports/bivariate.md and .json, then the HTML pages

Why this command exists, and why it is constrained:
- feature-target relations are needed (risk by band, WoE/IV, direction of the effect);
- computed on the validation windows they would be selection on the validation data,
  so they use the EXPLORATION PERIOD only (training part of the first backtest origin,
  which is included in the training data of every later origin: no test row is seen);
- the selection rule (frame spec.selection) must be committed BEFORE the first run of
  this command. Each run is logged in experiments/selection_ledger.jsonl with the hash
  of the rule; a rule changed after IVs were seen is reported by check I9 until a
  person acknowledges it in decisions.md. Reading the IVs, then writing the rule, is
  the garden of forking paths with extra steps.
- the IV of a column is compared to its own NOISE FLOOR: the IV obtained when the
  target is permuted. Without it, columns with many bands always look informative.

Correlations and VIF do not use the target: they are computed on all of data/dev.
The output is a PROPOSAL. A person ratifies exclusions in decisions.md and features.yaml.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
import sys

import numpy as np
import pandas as pd
import yaml

from . import config, core, dataquality as dq, gate

SELECTION_LEDGER = config.ROOT / "experiments" / "selection_ledger.jsonl"
RULE_QUESTION = "Q-MOD-06"
MISSING = "missing"


def rule_hash(rule: dict) -> str:
    return hashlib.sha256(json.dumps(rule, sort_keys=True).encode()).hexdigest()[:12]


def committed_rule() -> tuple[dict | None, str]:
    """The selection rule as committed in HEAD:frame.yaml, or (None, reason)."""
    try:
        txt = subprocess.run(["git", "show", "HEAD:frame.yaml"], cwd=config.ROOT,
                             capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None, "frame.yaml is not committed (missing Git repository or file never committed)"
    rule = ((yaml.safe_load(txt) or {}).get("spec") or {}).get("selection")
    return (rule, "") if rule else (None, "HEAD:frame.yaml has no spec.selection")


# ---------------------------------------------------------------- binning and IV
def make_bins(s: pd.Series, numeric: bool, n_bins: int = 10, min_share: float = 0.01):
    """Return (codes 0..k-1, labels, numeric order flags). Missing values get their own band."""
    if numeric:
        x = pd.to_numeric(s, errors="coerce")
        v = x.dropna()
        if 1 < v.nunique() <= 30 and (v % 1 == 0).all():
            # few distinct values (counts such as pub_rec): one band per value, rare upper values pooled.
            # Quantile edges would collapse them into a single band and an IV of 0 by construction.
            share = v.value_counts(normalize=True).sort_index()
            cut, acc = share.index[-1], 0.0
            for val, sh in share[::-1].items():
                acc += sh
                if acc >= min_share:
                    cut = val
                    break
            lab = pd.Series(np.where(x.isna(), MISSING, np.where(x >= cut, f"≥ {cut:g}", x.map(lambda t: f"{t:g}"))), index=s.index)
            order = [f"{t:g}" for t in share.index if t < cut] + [f"≥ {cut:g}", MISSING]
            present = [o for o in order if (lab == o).any()]
            return pd.Categorical(lab, categories=present).codes, present, [o != MISSING for o in present]
        edges = np.unique(np.quantile(v, np.linspace(0, 1, n_bins + 1))) if len(v) else np.array([])
        if len(edges) < 2:
            lab = pd.Series(np.where(x.isna(), MISSING, "single value"), index=s.index)
        else:
            inner = edges[1:-1]
            idx = np.searchsorted(inner, x.to_numpy(), side="right")
            names = [f"< {edges[1]:.4g}"] + [f"[{edges[i]:.4g} ; {edges[i + 1]:.4g}[" for i in range(1, len(edges) - 2)] + [f"≥ {edges[-2]:.4g}"]\
                if len(edges) > 2 else ["all"]
            lab = pd.Series([names[i] if not np.isnan(val) else MISSING for i, val in zip(idx, x.to_numpy())], index=s.index)
            order = names + [MISSING]
            present = [o for o in order if (lab == o).any()]
            codes = pd.Categorical(lab, categories=present).codes
            return codes, present, [o != MISSING for o in present]
    else:
        lab = s.astype("string").fillna(MISSING)
        share = lab.value_counts(normalize=True)
        rare = share[share < min_share].index
        lab = lab.where(~lab.isin(rare), "autres")
    present = list(pd.Series(lab).value_counts().index)
    codes = pd.Categorical(lab, categories=present).codes
    return codes, present, [False] * len(present)


def iv_of(codes: np.ndarray, y: np.ndarray, k: int) -> tuple[float, np.ndarray, np.ndarray, np.ndarray]:
    n = np.bincount(codes, minlength=k).astype(float)
    bad = np.bincount(codes, weights=y, minlength=k)
    good = n - bad
    db = (bad + 0.5) / (bad.sum() + 0.5 * k)
    dg = (good + 0.5) / (good.sum() + 0.5 * k)
    woe = np.log(dg / db)
    return float(((dg - db) * woe).sum()), woe, n, bad


def direction(codes, y, ordered_mask) -> float | None:
    """Spearman-like correlation between band order and bad rate (numeric bands only)."""
    k = len(ordered_mask)
    n = np.bincount(codes, minlength=k).astype(float)
    bad = np.bincount(codes, weights=y, minlength=k)
    keep = [i for i in range(k) if ordered_mask[i] and n[i] > 0]
    if len(keep) < 3:
        return None
    rate = bad[keep] / n[keep]
    if np.std(rate) == 0:
        return 0.0
    return float(np.corrcoef(np.arange(len(keep)), pd.Series(rate).rank().to_numpy())[0, 1])


def subperiod_masks(months: pd.Series, k: int) -> list[np.ndarray]:
    counts = months.value_counts().sort_index()
    cum = counts.cumsum() / counts.sum()
    cuts = [cum.index[cum >= (i + 1) / k][0] for i in range(k - 1)]
    bounds = [None, *cuts, None]
    out = []
    for lo, hi in zip(bounds[:-1], bounds[1:]):
        m = np.ones(len(months), dtype=bool)
        if lo is not None:
            m &= (months > lo).to_numpy()
        if hi is not None:
            m &= (months <= hi).to_numpy()
        out.append(m)
    return out


def analyse(df: pd.DataFrame, labels: pd.DataFrame, spec: dict, registry: dict, rule: dict) -> dict:
    end = dq.exploration_end(spec)
    d = df[df["_month"] <= end].merge(labels, on=spec["id_col"], how="inner").reset_index(drop=True)
    y = d[spec["target_col"]].to_numpy(dtype=float)
    rng = np.random.default_rng(0)
    perms = [rng.permutation(y) for _ in range(int(rule.get("permutations", 20)))]
    subs = subperiod_masks(d["_month"], int(rule.get("subperiods", 3)))
    usable = [c for c, e in registry.items() if c in d.columns and e.get("available") == "origination" and not e.get("excluded_by")]

    cols = {}
    for c in usable:
        s = d[c]
        num = pd.to_numeric(s, errors="coerce")
        numeric = bool(s.notna().any() and num[s.notna()].notna().mean() >= 0.99)
        codes, names, ordered = make_bins(s, numeric)
        k = len(names)
        iv, woe, n, bad = iv_of(codes, y, k)
        floor = float(np.quantile([iv_of(codes, yp, k)[0] for yp in perms], float(rule.get("floor_quantile", 0.95))))
        rho = direction(codes, y, ordered) if numeric else None
        sub_iv, sub_dir = [], []
        for m in subs:
            sub_iv.append(iv_of(codes[m], y[m], k)[0] if m.sum() else None)
            sub_dir.append(direction(codes[m], y[m], ordered) if numeric and m.sum() else None)
        cols[c] = {"numeric": numeric, "iv": iv, "floor": floor, "direction": rho,
                   "expected": registry[c].get("expected_direction"),
                   "sub_iv": sub_iv, "sub_direction": sub_dir,
                   "bands": [{"band": names[i], "n": int(n[i]), "bad_rate": float(bad[i] / n[i]) if n[i] else None,
                              "woe": float(woe[i])} for i in range(k)]}

    # redundancy: no target, all of data/dev (sampled for speed)
    numeric_cols = [c for c in usable if cols[c]["numeric"]]
    full = df[numeric_cols].apply(pd.to_numeric, errors="coerce")
    if len(full) > 200_000:
        full = full.sample(200_000, random_state=0)
    corr = full.corr(method="spearman") if numeric_cols else pd.DataFrame()
    vif = {}
    if len(numeric_cols) > 1:
        z = (full - full.mean()) / full.std(ddof=0).replace(0, 1)
        r = np.corrcoef(z.fillna(0).to_numpy(), rowvar=False)
        inv = np.linalg.pinv(r)
        vif = {c: float(inv[i, i]) for i, c in enumerate(numeric_cols)}
    pairs = []
    lim = float(rule.get("max_abs_corr", 0.85))
    for i, a in enumerate(numeric_cols):
        for b in numeric_cols[i + 1:]:
            v = corr.loc[a, b]
            if pd.notna(v) and abs(v) >= lim:
                pairs.append({"a": a, "b": b, "rho": float(v)})

    # rule, applied mechanically
    min_iv = float(rule.get("min_iv", 0.02))
    for c, r in cols.items():
        reasons = []
        if r["iv"] < max(min_iv, r["floor"]):
            reasons.append(f"IV {r['iv']:.3f} below threshold (chance floor {r['floor']:.3f}, minimum {min_iv})")
        if rule.get("require_expected_direction") and r["expected"] in ("+", "-") and r["direction"] is not None:
            obs = "+" if r["direction"] > 0 else "-"
            if obs != r["expected"]:
                reasons.append(f"effect de sens {obs}, expected {r['expected']}")
        if rule.get("require_stable_direction") and r["numeric"]:
            signs = {np.sign(v) for v in r["sub_direction"] if v is not None and abs(v) >= 0.3}
            if len(signs) > 1:
                reasons.append("effect direction changes between subperiods")
        r["vif"] = vif.get(c)
        r["reasons"] = reasons
    for p in sorted(pairs, key=lambda p: -abs(p["rho"])):
        a, b = cols[p["a"]], cols[p["b"]]
        if a["reasons"] or b["reasons"]:
            continue
        weaker, stronger = (p["a"], p["b"]) if a["iv"] < b["iv"] else (p["b"], p["a"])
        cols[weaker]["reasons"].append(f"redundant with {stronger} (ρ = {p['rho']:+.2f}), IV plus weak")
    for r in cols.values():
        r["verdict"] = "excluded" if r["reasons"] else "retained"

    return {"exploration_end": str(end), "rows": int(len(d)), "bad_rate": float(y.mean()),
            "subperiods": [[str(d.loc[m, "_month"].min()), str(d.loc[m, "_month"].max()), int(m.sum())] for m in subs],
            "columns": cols, "pairs": pairs}


def write_md(res: dict, sel_id: str, rule: dict, rhash: str) -> None:
    cols = res["columns"]
    order = sorted(cols, key=lambda c: (cols[c]["verdict"] != "retained", -cols[c]["iv"]))
    L = [f"# Bivariate analysis and selection — {sel_id}", "",
         f"- Exploration period: through {res['exploration_end']} · {res['rows']:,} loans · default rate {res['bad_rate']:.1%}",
         f"- Applied rule (hash {rhash}) : " + ", ".join(f"{k}={v}" for k, v in rule.items()),
         f"- Retenues : {sum(1 for c in cols.values() if c['verdict'] == 'retained')} · excluded: {sum(1 for c in cols.values() if c['verdict'] != 'retained')}",
         "- **Proposal**: an exclusion applies only after ratification in decisions.md (cite " + sel_id + ").", "",
         "| column | IV | floor | observed direction | expected | IV by subperiod | VIF | verdict |", "|---|---|---|---|---|---|---|---|"]
    for c in order:
        r = cols[c]
        dirn = "" if r["direction"] is None else f"{r['direction']:+.2f}"
        sub = " / ".join("—" if v is None else f"{v:.3f}" for v in r["sub_iv"])
        vif = "" if r.get("vif") is None else f"{r['vif']:.1f}"
        L.append(f"| `{c}` | {r['iv']:.3f} | {r['floor']:.3f} | {dirn} | {r['expected'] or ''} | {sub} | {vif} | "
                 f"{r['verdict']}{': ' + '; '.join(r['reasons']) if r['reasons'] else ''} |")
    if res["pairs"]:
        L += ["", "## Correlated pairs (without the target, all development data)", ""]
        L += [f"- `{p['a']}` × `{p['b']}` : ρ = {p['rho']:+.2f}" for p in res["pairs"]]
    (config.REPORTS_DIR / "bivariate.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    frame, registry = config.load_frame(), config.load_features()
    spec = frame["spec"]
    if not gate.require("bivariate"):
        return 7
    _, answers, _ = gate.load()
    if not gate.is_answered(answers.get(RULE_QUESTION)):
        print(f"MISSING SELECTION RULE: first answer {RULE_QUESTION} and write spec.selection in frame.yaml, "
              "BEFORE inspecting any IV.", file=sys.stderr)
        return 7
    rule = spec.get("selection")
    committed, why = committed_rule()
    if not rule or committed is None or committed != rule:
        print("SELECTION RULE NOT COMMITTED: " + (why or "spec.selection differs from the committed version") +
              ". Commit frame.yaml (message: frame: selection rule), then retry.", file=sys.stderr)
        return 7
    problems = dq.manifest_problems()
    if problems:
        print("NONCONFORMING DATA (D5): " + " ; ".join(problems), file=sys.stderr)
        return 6

    df = dq.read_features(spec)
    labels = pd.read_csv(config.DEV_DIR / "labels.csv.gz")
    res = analyse(df, labels, spec, registry, rule)
    rhash = rule_hash(rule)
    previous = config.read_jsonl(SELECTION_LEDGER)
    sel_id = f"sel-{len(previous) + 1:04d}"
    data_hash = "-".join(config.sha256_file(p) for p in core.dev_files())
    res.update(sel_id=sel_id, rule=rule, rule_hash=rhash, frame_hash=config.frame_hash(), data_hash=data_hash,
               time=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
    config.REPORTS_DIR.mkdir(exist_ok=True)
    (config.REPORTS_DIR / "bivariate.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    write_md(res, sel_id, rule, rhash)
    config.append_jsonl(SELECTION_LEDGER, {
        "sel_id": sel_id, "time": res["time"], "rule_hash": rhash, "frame_hash": res["frame_hash"], "data_hash": data_hash,
        "retained": sorted(c for c, r in res["columns"].items() if r["verdict"] == "retained"),
        "dropped": sorted(c for c, r in res["columns"].items() if r["verdict"] != "retained")})
    kept = sum(1 for r in res["columns"].values() if r["verdict"] == "retained")
    print(f"{sel_id} : {kept} retaineds, {len(res['columns']) - kept} excluded (proposal) · reports/bivariate.md")
    if previous and previous[-1]["rule_hash"] != rhash:
        print("WARNING: the rule changed since the last analysis. I9 will fail until decisions.md "
              f"does not cite selection rule {rhash} ».", file=sys.stderr)
    from . import render
    render.safe_render()
    return 0


if __name__ == "__main__":
    sys.exit(main())
