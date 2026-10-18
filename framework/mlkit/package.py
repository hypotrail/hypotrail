"""Freeze the confirmed model for production. Run by a PERSON.

    python -m mlkit.package --prereg c-001

Refuses unless: the phase gate "package" is open, the holdout reading of this
pre-registration was accepted under the current frame, the model card exists and
docs/validation.md carries a signed "VERDICT: VALIDATED".
Writes models/<prereg>/: model.joblib, reference_model.joblib (the rule kept for the
control group), reference.csv.gz (sample for drift monitoring) and metadata.json.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys

import joblib
import numpy as np
import pandas as pd

from . import config, core, dataquality as dq, gate


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m mlkit.package")
    ap.add_argument("--prereg", required=True, help="pre-registration id, e.g. c-001")
    args = ap.parse_args(argv)
    if not gate.require("package"):
        return 7

    raise SystemExit("Reviewed 4.2-dev: production packaging is suspended. The v4.1 protocol confirms neither the frozen policy nor the refitted model. See the implementation handoff.")

    frame, registry = config.load_frame(), config.load_features()
    spec, fhash = frame["spec"], config.frame_hash()
    dep = spec.get("deployment", {})
    readings = [e for e in config.read_jsonl(config.LEDGER_FILE) if e["prereg"] == args.prereg and e["frame_hash"] == fhash]
    if not readings or not readings[-1]["accepted"]:
        raise SystemExit(f"{args.prereg}: no accepted holdout reading under the current frame")
    reading = readings[-1]
    if not (config.REPORTS_DIR / "model_card.md").exists():
        raise SystemExit("model card missing: python -m mlkit.card --prereg " + args.prereg)
    validation = config.ROOT / "docs" / "validation.md"
    text = validation.read_text(encoding="utf-8") if validation.exists() else ""
    if not re.search(r"^VERDICT: VALIDATED", text, re.M) or not re.search(r"^Signed: \S+", text, re.M):
        raise SystemExit("docs/validation.md must contain VERDICT: VALIDATED and Signed: <name> (independent validation, Q-VAL-01)")

    module = core.load_pipeline(reading["pipeline"])
    if config.sha256_file(config.ROOT / reading["pipeline"]) != reading["code_hash"]:
        raise SystemExit("pipeline changed since the holdout reading: this is no longer the confirmed model")
    from . import reference as reference_mod
    ref_mod = reference_mod.module(spec)
    df = core.load_dev(spec)
    if dep.get("final_fit", "dev") == "dev+holdout":
        df = pd.concat([df, core.align_like(core.load_split(config.holdout_dir(), spec), df)], ignore_index=True)
    y = df[spec["target_col"]]

    X_fit, y_fit = core.training_sample(df[module.FEATURES], y, spec)
    model = module.build().fit(X_fit, y_fit)
    reference = ref_mod.build().fit(df[ref_mod.FEATURES], y)
    rate = float(spec.get("evaluation", {}).get("decision_rate", 0.9))
    ref_threshold = float(np.quantile(reference.predict_proba(df[ref_mod.FEATURES])[:, 1], rate))

    out = config.MODELS_DIR / args.prereg
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, out / "model.joblib")
    joblib.dump(reference, out / "reference_model.joblib")
    sample = df.sample(min(5000, len(df)), random_state=0)
    ref_sample = sample[sorted(set(module.FEATURES))].copy()
    ref_sample["_score"] = model.predict_proba(sample[module.FEATURES])[:, 1]
    ref_sample.to_csv(out / "reference.csv.gz", index=False)

    used = sorted(set(module.FEATURES) | set(ref_mod.FEATURES))
    meta = {
        "model_id": args.prereg, "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "pipeline": reading["pipeline"], "code_hash": reading["code_hash"], "frame_hash": fhash,
        "data_manifest": dq.manifest(), "final_fit": dep.get("final_fit", "dev"), "n_train": int(len(df)),
        "features": list(module.FEATURES), "reference_features": list(ref_mod.FEATURES),
        "threshold": reading["at_threshold"]["threshold"], "reference_threshold": ref_threshold,
        "decision_rate": rate, "id_col": spec["id_col"], "deployment": dep, "monitoring": spec.get("monitoring", {}),
        "contracts": {c: registry[c]["contract"] for c in used if "contract" in registry.get(c, {})},
        "holdout": {k: reading[k] for k in ("gain", "gain_ci", "metrics", "at_threshold")},
    }
    (out / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"frozen model: models/{args.prereg}/ · threshold {meta['threshold']:.4f} · trained on {meta['n_train']:,} rows ({meta['final_fit']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
