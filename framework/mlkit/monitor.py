"""Monitoring of a deployed model, on a scored batch, before and after labels mature.

    python -m mlkit.monitor --model models/c-001 --input batch.csv --scored scored.csv
    python -m mlkit.monitor --model models/c-001 --input batch.csv --scored scored.csv --outcomes outcomes.csv

Without outcomes: drift of every used feature and of the score (PSI against the
training sample), missing rates against the contract.
With outcomes (id + matured target): performance and calibration of the model
group, and the outcome of the model group against the control group.
Exit code 1 when an alert threshold of frame spec.monitoring is crossed (Q-SUI-01/02).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from . import config, dataquality as dq, gate
from .evaluate import calibration


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m mlkit.monitor")
    ap.add_argument("--model", required=True)
    ap.add_argument("--input", required=True, help="features of the scored batch")
    ap.add_argument("--scored", required=True, help="output of mlkit.score")
    ap.add_argument("--outcomes", help="id + target, once labels are mature")
    args = ap.parse_args(argv)
    if not gate.require("monitor"):
        return 7

    mdir = Path(args.model)
    meta = json.loads((mdir / "metadata.json").read_text(encoding="utf-8"))
    mon, idc = meta.get("monitoring", {}), meta["id_col"]
    ref = pd.read_csv(mdir / "reference.csv.gz")
    batch = pd.read_csv(args.input, low_memory=False)
    scored = pd.read_csv(args.scored)
    alerts, lines = [], []

    psi_alert = float(mon.get("psi_alert", 0.25))
    drift = {}
    for col in meta["features"]:
        numeric = meta["contracts"].get(col, {}).get("type") == "numeric" or (pd.api.types.is_numeric_dtype(ref[col]) and not pd.api.types.is_bool_dtype(ref[col]))
        drift[col] = dq.psi(ref[col], batch[col], numeric)
    drift["_score"] = dq.psi(ref["_score"], scored["score"].dropna(), True)
    for col, v in sorted(drift.items(), key=lambda kv: -kv[1]):
        if v > psi_alert:
            alerts.append(f"drift {('du score' if col == '_score' else col)} : PSI {v:.2f} > {psi_alert}")
    for col, c in meta["contracts"].items():
        if col in batch and "max_missing" in c and batch[col].isna().mean() > c["max_missing"]:
            alerts.append(f"{col} : {batch[col].isna().mean():.1%} missing > contract {c['max_missing']:.0%}")
    n_review = int((scored["decision"] == "revue_manuelle").sum())

    perf = {}
    if args.outcomes:
        out = pd.read_csv(args.outcomes)
        target = [c for c in out.columns if c != idc][0]
        d = scored.merge(out, on=idc, how="inner")
        m = d[(d["groupe"] == "modele") & d["score"].notna()]
        if m[target].nunique() == 2:
            perf["auc"] = float(roc_auc_score(m[target], m["score"]))
            perf["ece"] = calibration(m[target].to_numpy(), m["score"].to_numpy())[1]
            if perf["auc"] < float(mon.get("min_auc", 0)):
                alerts.append(f"performance : AUC {perf['auc']:.3f} < {mon['min_auc']}")
            if perf["ece"] > float(mon.get("max_calibration_error", 1)):
                alerts.append(f"calibration : ECE {perf['ece']:.3f} > {mon['max_calibration_error']}")
        acc = d[d["decision"] == "accepte"]
        perf["outcome_rate_accepted"] = {g: float(x[target].mean()) for g, x in acc.groupby("groupe")}
        perf["n_matured"] = int(len(d))

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    L = [f"# Suivi du model {meta['model_id']} — {stamp}", "",
         f"Alertes : **{len(alerts)}**" + ("" if not alerts else "\n\n" + "\n".join(f"- {a}" for a in alerts)), "",
         f"Lot : {len(batch):,} rows · {n_review} en revue manuelle (outside contract) · "
         f"{int((scored['groupe'] == 'temoin').sum())} controls", "",
         "## Drift (PSI against the training sample)", "", "| variable | PSI |", "|---|---|"]
    L += [f"| {'score' if k == '_score' else '`' + k + '`'} | {v:.3f} |" for k, v in sorted(drift.items(), key=lambda kv: -kv[1])]
    if perf:
        L += ["", "## Performance on mature labels", "", f"- rows with known outcomes: {perf['n_matured']:,}"]
        if "auc" in perf:
            L += [f"- groupe model : AUC {perf['auc']:.3f}, ECE {perf['ece']:.3f}"]
        L += [f"- event rate among accepted cases, group {g} : {v:.2%}" for g, v in perf["outcome_rate_accepted"].items()]
        L += ["", "The model/control comparison measures the actual model effect (Q-SUI-05)."]
    config.REPORTS_DIR.mkdir(exist_ok=True)
    (config.REPORTS_DIR / f"monitoring-{stamp}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    config.append_jsonl(config.LOGS_DIR / "monitoring.jsonl", {"time": stamp, "model_id": meta["model_id"],
                                                              "alerts": alerts, "drift": drift, "performance": perf})
    print(f"report : reports/monitoring-{stamp}.md · {len(alerts)} alerte(s)" + ("" if not alerts else " : " + " ; ".join(alerts[:3])))
    return 1 if alerts else 0


if __name__ == "__main__":
    sys.exit(main())
