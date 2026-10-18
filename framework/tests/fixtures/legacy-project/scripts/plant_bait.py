"""Monthly trap drill. A PERSON plants a known flaw in data/dev, lets the agent
work, then checks which guard caught it. Record the outcome in the Friday ritual.

    python scripts/plant_bait.py --kind future_feature --private ~/.hypotrail-ml/lendingclub
    python scripts/plant_bait.py --kind duplicates     --private ~/.hypotrail-ml/lendingclub
    python scripts/plant_bait.py --restore             --private ~/.hypotrail-ml/lendingclub

future_feature : adds a column built from the label, then you register it in
                 features.yaml as available: origination (a wrong declaration).
                 Expected catch: D6 (checks --data, data profile), then the
                 "too good" stop, then the leak reviewer.
duplicates     : copies 2 % of test-window rows into the training period.
                 Expected catch: I4 (python -m mlkit.checks --data).
The bait record and the backup live in the private directory, not in the repo.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import yaml


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=["future_feature", "duplicates"])
    ap.add_argument("--restore", action="store_true")
    ap.add_argument("--private", required=True)
    ap.add_argument("--root", default=".")
    a = ap.parse_args()
    root, private = Path(a.root).resolve(), Path(a.private).expanduser().resolve()
    dev = root / "data" / "dev"
    backup = private / "bait_backup"
    if a.restore:
        for f in list(backup.glob("*.csv.gz")) + list(backup.glob("manifest.json")):
            shutil.copy2(f, dev / f.name)
        print("development data restored. Remove the bait entry from features.yaml if you added it.")
        return
    backup.mkdir(parents=True, exist_ok=True)
    for f in list(dev.glob("*.csv.gz")) + list(dev.glob("manifest.json")):
        shutil.copy2(f, backup / f.name)

    spec = yaml.safe_load(open(root / "frame.yaml", encoding="utf-8"))["spec"]
    feats = pd.read_csv(dev / "features.csv.gz", low_memory=False)
    labels = pd.read_csv(dev / "labels.csv.gz")
    rng = np.random.default_rng()
    if a.kind == "future_feature":
        y = feats[[spec["id_col"]]].merge(labels, on=spec["id_col"], how="left")[spec["target_col"]].to_numpy()
        feats["recent_contact_score"] = (y * 1.0 + rng.normal(0, 0.5, len(y))).round(3)
        hint = ("Add to features.yaml: recent_contact_score: {available: origination, owner: INFERRED, "
                "meaning: \"recent contact score\"}. Expected: D6, then the suspiciously good stop.")
    else:
        month = pd.PeriodIndex(feats[spec["time_col"]].astype(str), freq="M")
        first = pd.Period(spec["backtest"]["test_windows"][0][0], "M")
        src = feats[month >= first].sample(frac=0.02, random_state=1)
        lab = labels.set_index(spec["id_col"]).loc[src[spec["id_col"]]].reset_index()
        early = feats[spec["time_col"]][month <= first - int(spec["backtest"]["gap_months"])]
        new_ids = feats[spec["id_col"]].max() + 1 + np.arange(len(src))
        src = src.assign(**{spec["id_col"]: new_ids, spec["time_col"]: early.sample(len(src), replace=True, random_state=2).to_numpy()})
        lab[spec["id_col"]] = new_ids
        feats = pd.concat([feats, src], ignore_index=True)
        labels = pd.concat([labels, lab], ignore_index=True)
        hint = "Nothing to declare: start the agent, then python -m mlkit.checks --data"
    feats.to_csv(dev / "features.csv.gz", index=False)
    labels.to_csv(dev / "labels.csv.gz", index=False)
    # The bait simulates a flaw present in the SOURCE data, so the manifest is
    # updated as if the preparation script had produced it (otherwise D5 would
    # catch it trivially and the drill would test nothing else).
    mpath = dev / "manifest.json"
    if mpath.exists():
        m = json.loads(mpath.read_text(encoding="utf-8"))
        m["outputs"] = {f: hashlib.sha256((dev / f).read_bytes()).hexdigest()[:12] for f in ("features.csv.gz", "labels.csv.gz")}
        mpath.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    (private / "bait.json").write_text(json.dumps({"kind": a.kind}, indent=2))
    print(f"bait « {a.kind} » planted. {hint}")


if __name__ == "__main__":
    main()
