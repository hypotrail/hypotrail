"""Batch scoring with the frozen model: contract, control group, decision, log.

    python -m mlkit.score --model models/c-001 --input batch.csv --out scored.csv

Per row:
- the input contract is checked (same contract as training, features.yaml);
  out-of-contract rows follow frame spec.deployment.on_contract_violation
  (review: no score, manual review · flag: score and flag);
- a stable share of ids goes to the control group (hash of id + salt), decided
  by the reference rule: this is what keeps the effect of the model measurable;
- the decision applies the threshold fixed on validation.
Every call appends one line to logs/scoring.jsonl.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from . import config, gate


def control_flag(ids, salt: str, share: float) -> np.ndarray:
    u = [int(hashlib.sha256(f"{salt}:{i}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF for i in ids]
    return np.asarray(u) < share


def row_violations(df: pd.DataFrame, contracts: dict) -> pd.Series:
    out = pd.Series([""] * len(df), index=df.index, dtype=object)
    for col, c in contracts.items():
        if col not in df:
            continue
        s, bad = df[col], pd.Series(False, index=df.index)
        if c.get("max_missing") == 0:
            bad |= s.isna()
        if c.get("type") == "numeric":
            num = pd.to_numeric(s, errors="coerce")
            bad |= num.isna() & s.notna()
            if "min" in c:
                bad |= num < c["min"]
            if "max" in c:
                bad |= num > c["max"]
        else:
            v = s.astype(str)
            if "allowed" in c:
                bad |= s.notna() & ~v.isin([str(a) for a in c["allowed"]])
            if "pattern" in c:
                bad |= s.notna() & ~v.str.match(c["pattern"])
        out[bad] = out[bad] + col + ";"
    return out.str.rstrip(";")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m mlkit.score")
    ap.add_argument("--model", required=True)
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    if not gate.require("score"):
        return 7

    mdir = Path(args.model)
    meta = json.loads((mdir / "metadata.json").read_text(encoding="utf-8"))
    model, reference = joblib.load(mdir / "model.joblib"), joblib.load(mdir / "reference_model.joblib")
    df = pd.read_csv(args.input, low_memory=False)
    need = sorted(set(meta["features"]) | set(meta["reference_features"]) | {meta["id_col"]})
    missing = [c for c in need if c not in df]
    if missing:
        raise SystemExit(f"missing batch columns: {', '.join(missing)}")

    dep = meta["deployment"]
    viol = row_violations(df, meta["contracts"])
    ok = (viol == "").to_numpy()
    control = control_flag(df[meta["id_col"]], dep.get("control_salt", "salt"), float(dep.get("control_share", 0)))
    score = np.full(len(df), np.nan)
    ref_score = np.full(len(df), np.nan)
    scorable = ok | (dep.get("on_contract_violation", "review") == "flag")
    if scorable.any():
        score[scorable] = model.predict_proba(df.loc[scorable, meta["features"]])[:, 1]
        ref_score[scorable] = reference.predict_proba(df.loc[scorable, meta["reference_features"]])[:, 1]

    decision = np.where(control, np.where(ref_score <= meta["reference_threshold"], "accepte", "refuse"),
                        np.where(score <= meta["threshold"], "accepte", "refuse")).astype(object)
    decision[~scorable] = "revue_manuelle"
    out = pd.DataFrame({meta["id_col"]: df[meta["id_col"]], "score": score,
                        "groupe": np.where(control, "temoin", "modele"), "decision": decision,
                        "hors_contrat": viol.to_numpy(), "model_id": meta["model_id"]})
    out.to_csv(args.out, index=False)

    config.LOGS_DIR.mkdir(exist_ok=True)
    log = {"time": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "model_id": meta["model_id"],
           "input_hash": config.sha256_file(Path(args.input)), "n": int(len(df)),
           "n_hors_contrat": int((~ok).sum()), "n_temoin": int(control.sum()),
           "decisions": {k: int(v) for k, v in pd.Series(decision).value_counts().items()}}
    config.append_jsonl(config.LOGS_DIR / "scoring.jsonl", log)
    print(f"{len(df):,} rows · {log['n_hors_contrat']} outside contract · {log['n_temoin']} controls · decisions {log['decisions']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
