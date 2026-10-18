"""Prepare Lending Club data for hypotrail-ml. Run by a PERSON, once per change.

    python scripts/prepare_lendingclub.py path/to/accepted_2007_to_2018Q4.csv.gz \
        --private ~/.hypotrail-ml/lendingclub

This script is the ONLY place where rows are removed or values change meaning.
Each such step cites a decision of decisions.md (comment "DECISION D-xxx") and is
counted in data/dev/manifest.json (rows before / after). The checks (D5) refuse
data whose manifest does not match this script, or whose decisions are unknown.

Writes:
  data/dev/features.csv.gz   features of loans issued before the holdout window
  data/dev/labels.csv.gz     id + default (the feature-builder role never reads it)
  data/dev/manifest.json     script hash, source hash, every step with its row counts
  <private>/holdout/...      holdout features + labels, OUTSIDE the repository

Post-origination columns are KEPT in the features file on purpose: they are
natural bait, and the registry (features.yaml) is what keeps them out of models.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

DEFAULT_STATUSES = {"Charged Off", "Default"}
PAID_STATUSES = {"Fully Paid"}
POLICY_STATUSES = {"Does not meet the credit policy. Status:Charged Off",
                   "Does not meet the credit policy. Status:Fully Paid"}
EMP_LENGTH = {"< 1 year": 0, "1 year": 1, "2 years": 2, "3 years": 3, "4 years": 4, "5 years": 5,
              "6 years": 6, "7 years": 7, "8 years": 8, "9 years": 9, "10+ years": 10}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


class Steps:
    """Counts rows around each filtering step, for the manifest."""
    def __init__(self):
        self.items: dict[str, dict] = {}

    def apply(self, df, mask, decision: str, what: str):
        rec = self.items.setdefault(what, {"decision": decision, "what": what, "rows_before": 0, "rows_after": 0})
        rec["rows_before"] += len(df)
        rec["rows_after"] += int(mask.sum())
        return df[mask]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", help="Lending Club accepted loans CSV (.csv or .csv.gz)")
    ap.add_argument("--private", required=True, help="private directory outside the repo")
    ap.add_argument("--root", default=".")
    ap.add_argument("--as-of", default="2018-12", help="month of the extraction (Q-CIB-08); 2018-12 for the 2007-2018 export")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    frame = yaml.safe_load(open(root / "frame.yaml", encoding="utf-8"))
    registry = yaml.safe_load(open(root / "features.yaml", encoding="utf-8"))["features"]
    spec = frame["spec"]
    h_first, h_last = (pd.Period(x, "M") for x in spec["holdout"]["window"])
    keep = set(registry) | {"issue_d", "loan_status", "term", "application_type"}
    steps = Steps()

    parts = []
    for chunk in pd.read_csv(args.source, chunksize=200_000, low_memory=False, usecols=lambda c: c in keep):
        # DECISION D-001: 36-month loans only.
        chunk = steps.apply(chunk, chunk["term"].astype(str).str.strip() == "36 months", "D-001", "36-month loans")
        # DECISION D-005: exclude loans issued outside credit policy.
        chunk = steps.apply(chunk, ~chunk["loan_status"].isin(POLICY_STATUSES), "D-005", "outside-credit-policy loans excluded")
        # DECISION D-001 : status terminal only (cible observable, frame F2)
        chunk = steps.apply(chunk, chunk["loan_status"].isin(DEFAULT_STATUSES | PAID_STATUSES), "D-001", "status terminal")
        # DECISION D-006 : demandes individuelles only
        if "application_type" in chunk:
            chunk = steps.apply(chunk, chunk["application_type"].astype(str).str.lower().str.startswith("indiv"),
                                "D-006", "demandes individuelles")
        chunk = chunk.assign(_month=pd.to_datetime(chunk["issue_d"], format="%b-%Y").dt.to_period("M"))
        chunk = steps.apply(chunk, chunk["_month"] <= h_last, "D-001", "issued before holdout end (observable label)")
        parts.append(chunk)
        print(f"  {sum(len(p) for p in parts):>9,} retained loans", end="\r", file=sys.stderr)
    df = pd.concat(parts, ignore_index=True)

    df["default"] = df["loan_status"].isin(DEFAULT_STATUSES).astype(int)
    df["issue_d"] = df["_month"].astype(str)
    for col in ("int_rate", "revol_util"):
        if col in df and not pd.api.types.is_numeric_dtype(df[col]):
            df[col] = pd.to_numeric(df[col].astype(str).str.rstrip("%").str.strip(), errors="coerce")
    if "emp_length" in df:
        # DECISION D-004 : explicit lookup; unmatched values become missing and are checked by D1
        df["emp_length"] = df["emp_length"].map(EMP_LENGTH)
    if "earliest_cr_line" in df:
        ecl = pd.to_datetime(df["earliest_cr_line"], format="%b-%Y", errors="coerce").dt.to_period("M")
        df["credit_history_months"] = [(i - e).n if pd.notna(e) else np.nan for i, e in zip(df["_month"], ecl)]

    label_cols = [spec["id_col"], "default"]
    drop = [c for c in ("loan_status", "term", "application_type", "_month", "default") if c in df]
    dev = df[df["_month"] < h_first]
    hold = df[(df["_month"] >= h_first) & (df["_month"] <= h_last)]

    dev_dir = root / "data" / "dev"
    hold_dir = Path(args.private).expanduser().resolve() / "holdout"
    dev_dir.mkdir(parents=True, exist_ok=True)
    hold_dir.mkdir(parents=True, exist_ok=True)
    dev.drop(columns=drop).to_csv(dev_dir / "features.csv.gz", index=False)
    dev[label_cols].to_csv(dev_dir / "labels.csv.gz", index=False)
    hold.drop(columns=drop).to_csv(hold_dir / "features.csv.gz", index=False)
    hold[label_cols].to_csv(hold_dir / "labels.csv.gz", index=False)

    script = "scripts/prepare_lendingclub.py"
    manifest = {"script": script, "script_hash": sha(root / script), "source_hash": sha(Path(args.source)),
                "as_of": args.as_of,
                "steps": list(steps.items.values()),
                "outputs": {f: sha(dev_dir / f) for f in ("features.csv.gz", "labels.csv.gz")}}
    (dev_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\ndev     : {len(dev):>8,} loans, {dev['_month'].min()} → {dev['_month'].max()}, default {dev['default'].mean():.1%}")
    print(f"holdout : {len(hold):>8,} loans, {h_first} → {h_last}, default {hold['default'].mean():.1%}")
    for s in manifest["steps"]:
        print(f"  {s['decision']} {s['what']:<50} {s['rows_before']:>9,} → {s['rows_after']:>9,}")
    print(f"holdout written to {hold_dir} — outside the repository. Next: python -m mlkit.profile")
    return 0


if __name__ == "__main__":
    sys.exit(main())
