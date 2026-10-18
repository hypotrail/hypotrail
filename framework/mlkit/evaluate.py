"""Full evaluation report of one exploratory run, on the backtest windows only.

    python -m mlkit.evaluate --run r-0007

Writes reports/eval-<run>.md and .json. Covers what one mean metric hides:
decision curve, threshold fixed on validation (frame E2), calibration, segments,
stability of the score over time, direction of effects (Q-MOD-02).

Verdict E1 = decision rule v2 (mlkit.decision): monthly gain with a lower bound > 0,
non-inferiority on the segments written in the frame, calibration only if the score is
used as a probability. E1 does not block the holdout reading; it blocks ACCEPTANCE and
mlkit.package. Never touches the holdout.
"""
from __future__ import annotations

import argparse
import json
import sys

import numpy as np
import pandas as pd

from . import config, core, dataquality as dq, decision


def thresholds(preds: pd.DataFrame, rate: float) -> dict[str, float]:
    """Score below which a case is accepted, per window (lower score = lower risk)."""
    return {w: float(np.quantile(g["score"], rate)) for w, g in preds.groupby("window")}


def accepted(preds: pd.DataFrame, thr: dict[str, float]) -> np.ndarray:
    return (preds["score"] <= preds["window"].map(thr)).to_numpy()


def calibration(y, s, bins: int = 10):
    order = np.argsort(s, kind="mergesort")
    rows, ece = [], 0.0
    for chunk in np.array_split(order, bins):
        if len(chunk) == 0:
            continue
        pred, obs = float(np.mean(s[chunk])), float(np.mean(y[chunk]))
        rows.append({"n": int(len(chunk)), "predicted": pred, "observed": obs})
        ece += len(chunk) / len(s) * abs(pred - obs)
    return rows, float(ece)


def segment_table(df, cand, ref, thr_c, thr_r, spec, col, min_size):
    s = df[col]
    if pd.api.types.is_numeric_dtype(s) and s.nunique() > 10:
        s = pd.qcut(s, 4, duplicates="drop").astype(str)
    s = s.astype(str).fillna("missing")
    acc_c, acc_r = accepted(cand, thr_c), accepted(ref, thr_r)
    y = cand["y"].to_numpy()
    out = []
    for value in sorted(s.unique()):
        m = (s == value).to_numpy()
        if m.sum() < min_size:
            continue
        rc = float(y[m & acc_c].mean()) if (m & acc_c).any() else float("nan")
        rr = float(y[m & acc_r].mean()) if (m & acc_r).any() else float("nan")
        out.append({"segment": f"{col}={value}", "n": int(m.sum()), "approval": float(acc_c[m].mean()),
                    "bad_rate": rc, "bad_rate_reference": rr, "gain": rr - rc})
    return out


RULE_LEDGER = "experiments/decision_rule.jsonl"


def rule_status(spec: dict) -> dict:
    """Freeze the decision rule (evaluation and acceptance blocks) at first use, like selection
rule M2. Changes after seeing an E1 verdict require decisions.md ratification
(DECISION-RULE <hash>); otherwise E1 cannot pass."""
    block = {k: spec.get(k) for k in ("evaluation", "acceptance", "power", "backtest", "metric_primary",
                                      "metric_primary_direction", "reference", "target_col", "label_delay_months")}
    # acceptance.rule is part of the frozen rule; written « expected_value » it is the v2 behaviour of a frame
    # without the field, so it keeps that frame's fingerprint (no ratification for a no-op)
    if isinstance(block["acceptance"], dict) and block["acceptance"].get("rule") == "expected_value":
        block["acceptance"] = {k: v for k, v in block["acceptance"].items() if k != "rule"}
    # evaluation.drift_blocking: false is the default (E4 informative): written or absent, same fingerprint
    if isinstance(block["evaluation"], dict) and block["evaluation"].get("drift_blocking") is False:
        block["evaluation"] = {k: v for k, v in block["evaluation"].items() if k != "drift_blocking"}
    h = config.sha256_text(json.dumps(block, sort_keys=True, ensure_ascii=False))
    path = config.ROOT / RULE_LEDGER
    seen = config.read_jsonl(path)
    if not seen or seen[-1]["rule_hash"] != h:
        import datetime as dt
        config.append_jsonl(path, {"rule_hash": h, "time": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                                   "first": not seen})
    if not seen or seen[0]["rule_hash"] == h:      # first rule, or back to it: nothing to ratify
        return {"hash": h, "ok": True, "reason": ""}
    dec = config.ROOT / "decisions.md"
    text = dec.read_text(encoding="utf-8") if dec.exists() else ""
    import re
    if re.search(rf"DECISION-RULE {h}\b.*Signed: \S+", text):
        return {"hash": h, "ok": True, "reason": "", "ratified": True}
    return {"hash": h, "ok": False,
            "reason": f"decision rule changed since first use (fingerprint {h}): ratify it in "
                      f"decisions.md with a line DECISION-RULE {h} — <reason> — Signed: <name>; otherwise E1 cannot pass"}


def psi_scores(preds):
    wins = sorted(preds["window"].unique())
    base = preds[preds["window"] == wins[0]]["score"]
    return {w: dq.psi(base, preds[preds["window"] == w]["score"], numeric=True) for w in wins[1:]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m mlkit.evaluate")
    ap.add_argument("--run", required=True)
    args = ap.parse_args(argv)

    frame, registry = config.load_frame(), config.load_features()
    spec, ev = frame["spec"], frame["spec"].get("evaluation", {})
    runs = {r["run_id"]: r for r in config.read_jsonl(config.REGISTRY_FILE)}
    run = runs.get(args.run)
    if not run or run["status"] != "exploratory":
        raise SystemExit(f"{args.run} : run exploratory introuvable")
    if run["frame_hash"] != config.frame_hash():
        raise SystemExit(f"{args.run} is stale (frame changed); rerun it")
    from . import ensemble; ensemble.require(args.run, "evaluation")      # spec.selection_rule
    ref_id = run["reference"]
    try:
        cand = pd.read_csv(config.PREDS_DIR / f"{args.run}.csv.gz")
        ref = pd.read_csv(config.PREDS_DIR / f"{ref_id}.csv.gz")
    except FileNotFoundError:
        raise SystemExit("predictions missing from .osml/preds: rerun the candidate and reference")
    ref = ref.set_index([spec["id_col"], "window"]).loc[pd.MultiIndex.from_frame(cand[[spec["id_col"], "window"]])].reset_index()
    feats = core.load_dev(spec).set_index(spec["id_col"])
    df = feats.loc[cand[spec["id_col"]]].reset_index()

    rate = float(ev.get("decision_rate", 0.9))
    p0 = spec["metric_primary"]
    if p0.startswith("bad_rate_at_approval_") and abs(int(p0.rsplit("_", 1)[1]) / 100 - rate) > 1e-9:
        raise SystemExit(f"metric_primary ({p0}) et evaluation.decision_rate ({rate}) describe different policies")
    thr_c, thr_r = thresholds(cand, rate), thresholds(ref, rate)
    y, s = cand["y"].to_numpy(), cand["score"].to_numpy()

    # decision curve: bad rate among accepted, candidate vs reference, per approval rate
    curve = []
    for a in (0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 1.0):
        bc = np.mean([core.bad_rate_at_approval(g["y"], g["score"], a) for _, g in cand.groupby("window")])
        br = np.mean([core.bad_rate_at_approval(g["y"], g["score"], a) for _, g in ref.groupby("window")])
        curve.append({"approval": a, "bad_rate": float(bc), "bad_rate_reference": float(br)})

    calib_rows, ece = calibration(y, s)
    max_ece = ev.get("max_calibration_error")
    min_size = int(ev.get("min_segment_size", 500))
    segs = []
    for col in ev.get("segments", []):
        if col in df.columns:
            segs += segment_table(df, cand, ref, thr_c, thr_r, spec, col, min_size)
    stab = psi_scores(cand)

    # ---- decision rule v2/v3
    s_ref = ref["score"].to_numpy()
    months = df["_month"].astype(str).to_numpy()
    wins = cand["window"].to_numpy()
    names = sorted(set(wins.tolist()))
    wg = np.array([decision.gain(y[wins == w], s_ref[wins == w], s[wins == w], rate)[0] for w in names])
    pw = run.get("per_window", {})
    ntr = [pw.get(w, {}).get("n_train") for w in names]
    nte = [pw.get(w, {}).get("n_test") for w in names]
    nb = None not in ntr and None not in nte
    ni = ev.get("noninferiority", {})
    bt = decision.backtest_gate(wg, float(ev.get("backtest_level", 0.95)),
                                monthly=decision.group_gains(y, s_ref, s, months, rate),
                                n_train=ntr if nb else None, n_test=nte if nb else None, names=names,
                                stress=core.stress_names(spec),
                                stress_margin=float(ev.get("stress_margin", ni.get("margin", 0.005))),
                                correction=str(ev.get("backtest_correction", "none")))
    masks, missing = {}, []
    for item in ni.get("segments", []):
        col, _, val = str(item).partition("=")
        if col in df.columns and (df[col].astype(str) == val).any():
            masks[item] = (df[col].astype(str) == val).to_numpy()
        else:
            missing.append(item)          # a declared segment that does not exist is a frame error: fails, visibly
    sg = decision.segment_gate(y, s_ref, s, cand["window"].to_numpy(), masks, rate,
                               float(ni.get("margin", 0.005)), float(ni.get("level", 0.95)),
                               min_size=min_size, multiplicity=str(ni.get("multiplicity", "none")),
                               unevaluable=str(ni.get("unevaluable", "pass")))
    if missing:
        sg.update({"pass": False, "missing": missing,
                   "reason": "; ".join(x for x in [sg["reason"], "declared segments missing from data: "
                                                    + ", ".join(missing)] if x)})
    use = ev.get("decision_use", "ranking")

    mono = []
    for col, e in registry.items():
        d = e.get("expected_direction")
        if d and col in run["features"] and col in df.columns:
            x = pd.to_numeric(df[col], errors="coerce")
            rho = float(pd.Series(s).corr(x.rank(), method="spearman"))
            ok = (rho >= 0) if d == "+" else (rho <= 0)
            mono.append({"feature": col, "expected": d, "spearman": rho, "ok": bool(ok or abs(rho) < 0.02)})

    calib_ok = max_ece is None or ece <= max_ece
    calib_blocks = use == "probability"
    if not masks and not missing:
        sg.update({"pass": False, "reason": "no segment declared in the frame (evaluation.noninferiority.segments)"})
    rule = rule_status(spec)
    verdict = bt["pass"] and sg["pass"] and (calib_ok or not calib_blocks) and rule["ok"]
    reasons = ([] if bt["pass"] else [f"backtest : {bt['reason']}"]) +\
              ([] if sg["pass"] else [f"segments : {sg['reason']}"]) +\
              ([] if calib_ok or not calib_blocks else [f"calibration : ECE {ece:.3f} > {max_ece} (score used as probability)"]) +\
              ([] if rule["ok"] else [rule["reason"]])
    out = {"run": args.run, "reference": ref_id, "code_hash": run["code_hash"], "frame_hash": run["frame_hash"],
           "decision_rate": rate, "threshold": {"per_window": thr_c, "mean": float(np.mean(list(thr_c.values()))),
                                                "std": float(np.std(list(thr_c.values())))},
           "curve": curve, "calibration": {"bins": calib_rows, "ece": ece, "max": max_ece, "ok": calib_ok},
           "segments": segs, "score_psi": stab, "monotonicity": mono,
           "rule": "v3", "acceptance_rule": decision.acceptance_rule(spec), "rule_hash": rule["hash"], "decision_use": use, "backtest": bt, "noninferiority": sg,
           "e1_pass": bool(verdict), "e1_reasons": reasons}
    config.REPORTS_DIR.mkdir(exist_ok=True)
    (config.REPORTS_DIR / f"eval-{args.run}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    p = spec["metric_primary"]
    L = [f"# Evaluation of run:{args.run} (reference run:{ref_id})", "",
         f"Verdict E1 : **{'PASS' if verdict else 'FAILURE'}**" + ("" if verdict else " — " + " ; ".join(reasons)), "",
         "This report uses backtest windows only. The holdout is not read.",
         "E1 blocks acceptance and production, not holdout reading.", "",
         "## Decision rule v3", "",
         f"1. **Gain by window** ({bt['n_windows']} windows, each with its own training): "
         f"{', '.join(f'{x:+.4f}' for x in bt.get('window_gains', []))} ; moyenne {bt.get('mean', float('nan')):+.4f}, "
         f"one-sided lower bound at {bt.get('level', 0.95):.0%} {bt.get('lower', float('nan')):+.4f}"
         + ({"nadeau_bengio": f" (Nadeau-Bengio, n_test/n_train moyen {bt.get('test_train_ratio') or 0:.2f} ; without correction "
                              f"{bt.get('lower_naive', float('nan')):+.4f})",
             "months": f" (t-test on {bt.get('n_months', 0)} monthly gains across windows, mean "
                       f"{bt.get('monthly_mean', float('nan')):+.4f}; t-test on windows {bt.get('lower_naive', float('nan')):+.4f})"}
            .get(bt.get("correction"), " (t-test on window gains, no correction)"))
         + f" → **{'PASS' if bt.get('t_pass', bt['pass']) else 'FAILURE'}**. Worst window {bt.get('worst_window', '—')} "
         f"({bt.get('worst_gain', float('nan')):+.4f}), negative windows: {bt.get('n_negative', 0)}/{bt['n_windows']}. "
         f"Months par months ({bt.get('n_months', 0)} months weighted by volume): mean "
         f"{bt.get('monthly_mean', float('nan')):+.4f}, lower bound for next month {bt.get('prediction_lower', float('nan')):+.4f}."
         + (f" **Warning** : {bt['warning']}." if bt.get("warning") else ""),
         ("   Preregistered stress windows (worst case, tolerated loss " + f"{bt['stress']['margin']:.4f}) : "
          + ", ".join(f"{r['window']} {r['gain']:+.4f} {'ok' if r['pass'] else '**FAILURE**'}" for r in bt["stress"]["windows"])
          if bt["stress"]["windows"] else "   No preregistered stress window (backtest.stress_windows)."),
         f"2. **Noninferiority** (no segment loses more than {sg['margin']:.4f}, confidence {sg['level']:.0%}, "
         f"{'correction de Holm' if sg['multiplicity'] == 'holm' else 'without correction'}, taille minimum {sg['min_size']}) → "
         f"**{'PASS' if sg['pass'] else 'FAILURE'}**" + (" — no segment declared in the frame" if not masks and not missing else ""), "",
         "| preregistered segment | n | gain | standard error | level (Holm) | lower bound |", "|---|---|---|---|---|---|"]
    L += [f"| {r['segment']} | {r['n']} | {r['gain']:+.4f} | {r['se']:.4f} | {r['level_used']:.2%} | "
          f"{'**' if not r['pass'] else ''}{r['lower']:+.4f}{'**' if not r['pass'] else ''} |"
          if r["evaluable"] else f"| {r['segment']} | {r['n']} | **not evaluable** | — | — | {r['why']} |"
          for r in sg["segments"]]
    if sg["unevaluable"]:
        L += ["", f"Preregistered NOT EVALUABLE segments ({len(sg['unevaluable'])}) : "
              + ", ".join(u["segment"] for u in sg["unevaluable"])
              + (" — these fail E1 (noninferiority.unevaluable: fail)." if sg["unevaluable_policy"] == "fail"
                 else " — these do not fail E1 (noninferiority.unevaluable: pass), but nothing is established for them.")]
    L += ["", f"3. **Calibration** : ECE {ece:.4f} — " + ("blocking (score used as probability)" if calib_blocks
          else "display only (score used for ranking, Q-CAD-04)") + ".", "",
         "## By window", "", f"| window | {p} | roc_auc | brier | n test |", "|---|---|---|---|---|"]
    for w, m in run["per_window"].items():
        L.append(f"| {w} | {m[p]:.4f} | {m.get('roc_auc', float('nan')):.4f} | {m.get('brier', float('nan')):.4f} | {m['n_test']} |")
    L += ["", f"## Decision curve (default rate among accepted cases)", "",
          "| acceptance rate | candidate | reference | difference |", "|---|---|---|---|"]
    L += [f"| {c['approval']:.0%} | {c['bad_rate']:.2%} | {c['bad_rate_reference']:.2%} | {c['bad_rate_reference'] - c['bad_rate']:+.2%} |" for c in curve]
    L += ["", f"## Threshold (set on validation, frame E2)", "",
          f"Maximum accepted score for {rate:.0%} d'acceptation : moyenne {out['threshold']['mean']:.4f}, "
          f"window variation {out['threshold']['std']:.4f}. Retain this threshold unchanged in preregistration and deployment.",
          "", f"## Calibration — ECE {ece:.4f}" + (f" (tolerance {max_ece})" if max_ece is not None else ""), "",
          "| bin | n | predicted | observed |", "|---|---|---|---|"]
    L += [f"| {i + 1} | {b['n']} | {b['predicted']:.3f} | {b['observed']:.3f} |" for i, b in enumerate(calib_rows)]
    L += ["", f"## All segments (≥ {min_size} loans), informative only; small negative segments can reflect chance", "",
          "| segment | n | acceptance rate | accepted default rate | reference | gain |", "|---|---|---|---|---|---|"]
    L += [f"| {x['segment']} | {x['n']} | {x['approval']:.1%} | {x['bad_rate']:.2%} | {x['bad_rate_reference']:.2%} | "
          f"{'**' if x['gain'] < 0 else ''}{x['gain']:+.2%}{'**' if x['gain'] < 0 else ''} |" for x in segs]
    L += ["", "## Score stability over time (PSI relative to the first window)", ""]
    L += [f"- {w} : {v:.3f}" for w, v in stab.items()] or ["- only one window"]
    L += ["", "## Effect directions (Q-MOD-02)", "", "| feature | expected | rank correlation with score | conforms |", "|---|---|---|---|"]
    L += [f"| `{m['feature']}` | {m['expected']} | {m['spearman']:+.3f} | {'yes' if m['ok'] else '**NON**'} |" for m in mono]
    L += ["", "## No couvert par ce report", "",
          "- individual decision reasons (Q-CAD-09): produce them using a method suited to the retained model;",
          "- fairness on protected attributes: impossible without those attributes (Q-CAD-12)."]
    (config.REPORTS_DIR / f"eval-{args.run}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"report : reports/eval-{args.run}.md · E1 {'PASS' if verdict else 'FAILURE'}"
          + ("" if verdict else " : " + " ; ".join(reasons[:3])))
    if bt.get("warning"):
        print(f"warning (backtest) : {bt['warning']}")
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(main())
