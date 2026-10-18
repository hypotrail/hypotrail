"""The mandatory launcher. Every experiment goes through it, so every run is counted.

    python -m mlkit.run --reference
    python -m mlkit.run --pipeline model/pipeline.py --note "gbm, 30-day windows"
    python -m mlkit.run --pipeline model/pipeline.py --null

Exit codes: 0 ok · 2 no reference, or reference not conform (reference_kind)
            · 3 stop triggered · 4 feature rejected (I5, or D6: too predictive alone without leak_ack)
            · 5 open stop blocks runs
            · 6 data not produced by a traced preparation, unregistered columns, or contract violated
            · 7 phase gate: blocking questions of questions.yaml without a human answer
            · 8 exploration budget: this run would compare more candidates than the budget has left
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys

import numpy as np
import pandas as pd

from . import config, core, dataquality as dq, gate, reference


def _next_id(prefix: str, runs: list[dict]) -> str:
    n = sum(1 for r in runs if r["run_id"].startswith(prefix + "-")) + 1
    return f"{prefix}-{n:04d}"


def valid_stop_decision(path) -> bool:
    """Check structure, not signer identity; an external service is required for authentication."""
    if not path.is_file():
        return False
    import re
    text = path.read_text(encoding="utf-8")
    return all(re.search(pattern, text, re.M) for pattern in (
        r"^Decision: (RESUME|ACCEPT)\s*$", r"^Signed: \S.+$",
        r"^Reason: \S.+$", r"^Date: \d{4}-\d{2}-\d{2}\s*$"))


def open_stops() -> list[str]:
    if not config.STOPS_DIR.exists():
        return []
    return sorted(
        p.stem for p in config.STOPS_DIR.glob("STOP-*.json")
        if not valid_stop_decision(config.STOPS_DIR / f"{p.stem}.decision.md")
    )


def latest_reference(runs: list[dict], fhash: str):
    refs = [r for r in runs if r["status"] == "reference" and r["frame_hash"] == fhash]
    return refs[-1] if refs else None


def refuse(record: dict, reason: list[str], code: int, title: str) -> int:
    record.update(status="rejected", reason=reason)
    config.append_jsonl(config.REGISTRY_FILE, record)
    print(f"{title} :\n  " + "\n  ".join(reason), file=sys.stderr)
    return code


def secondary_reference(spec, fhash, primary_record, df, registry, runs) -> None:
    """A re-fitted reference, shown beside the score in place, never used for a gain.
    Written after the primary reference, so a failure here cannot lose the primary."""
    second = spec["reference_secondary_pipeline"]
    rec = {"run_id": _next_id("ref2", runs), "status": "reference_secondary", "pipeline": second,
           "reference_of": primary_record["run_id"], "time": primary_record["time"], "frame_hash": fhash,
           "data_hash": primary_record["data_hash"], "note": "secondary reference"}
    try:
        mod2 = core.load_pipeline(second)
        rec.update(code_hash=core.code_hash(second), features=list(mod2.FEATURES))
        bad = core.feature_violations(mod2.FEATURES, registry)
        if bad:
            rec.update(status="rejected", reason=bad)
        else:
            rec.update(evaluate(mod2, df, spec, permute=False))
    except Exception as exc:          # never lose the primary reference because of the secondary one
        rec.update(status="rejected", reason=[f"{type(exc).__name__}: {exc}"])
    config.append_jsonl(config.REGISTRY_FILE, rec)
    if rec["status"] == "rejected":
        print(f"   secondary reference refused: {'; '.join(rec['reason'])}", file=sys.stderr)
    else:
        p = spec["metric_primary"]
        print(f"   secondary reference ({second}) {p} {rec['summary'][p]['mean']:.4f} — displayed, never used for gain")


def evaluate(module, df, spec, permute: bool, seed: int = 0, preds_path=None) -> dict:
    y_all = df[spec["target_col"]].to_numpy()
    if permute:
        y_all = np.random.default_rng(seed).permutation(y_all)
    per_window, candidates, preds = {}, 1, []
    for name, train_end, start, end in core.windows(spec):
        tr = (df["_month"] <= train_end).to_numpy()
        te = ((df["_month"] >= start) & (df["_month"] <= end)).to_numpy()
        if tr.sum() == 0 or te.sum() == 0:
            raise SystemExit(f"window {name}: train={tr.sum()} test={te.sum()} — data insuffisantes")
        score, model = core.fit_predict_model(module, df.loc[tr, module.FEATURES], y_all[tr], df.loc[te, module.FEATURES])
        candidates = max(candidates, core.n_candidates(model))
        preds.append(pd.DataFrame({spec["id_col"]: df.loc[te, spec["id_col"]].to_numpy(), "window": name,
                                   "y": y_all[te], "score": score}))
        per_window[name] = {m: core.compute_metric(m, y_all[te], score) for m in core.all_metrics(spec)}
        per_window[name]["n_train"], per_window[name]["n_test"] = int(tr.sum()), int(te.sum())
    summary = {}
    for m in core.all_metrics(spec):
        vals = [w[m] for w in per_window.values()]
        summary[m] = {"mean": float(np.mean(vals)), "std": float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0}
    if preds_path is not None:
        preds_path.parent.mkdir(parents=True, exist_ok=True)
        pd.concat(preds).to_csv(preds_path, index=False)
    return {"per_window": per_window, "summary": summary, "n_candidates": candidates}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m mlkit.run")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--pipeline", help="pipeline module, e.g. model/pipeline.py")
    g.add_argument("--reference", action="store_true", help="run the frame's reference pipeline")
    ap.add_argument("--null", action="store_true", help="null test: permuted target, must score at chance")
    ap.add_argument("--note", default="", help="free text, never passed to reviewers")
    args = ap.parse_args(argv)

    frame, registry = config.load_frame(), config.load_features()
    spec, fhash = frame["spec"], config.frame_hash()
    runs = config.read_jsonl(config.REGISTRY_FILE)

    if not gate.require("run"):
        return 7

    blocking = open_stops()
    if blocking and not args.null:
        print(f"STOP OPEN : {', '.join(blocking)}. A human decision (stops/<id>.decision.md) "
              "is required before any new run.", file=sys.stderr)
        return 5

    data_problems = dq.manifest_problems()
    header = pd.read_csv(config.DEV_DIR / "features.csv.gz", nrows=0).columns
    unknown = [c for c in header if c not in registry]
    if unknown:
        data_problems.append(f"columns missing de features.yaml : {', '.join(unknown)}")
    if data_problems:
        print("NONCONFORMING DATA (D2/D5): " + " ; ".join(data_problems), file=sys.stderr)
        return 6

    if args.reference:
        bad = reference.problems(spec)
        if bad:
            print("NONCONFORMING REFERENCE (F9):\n  " + "\n  ".join(bad), file=sys.stderr)
            return 2
        module = reference.module(spec)
        path = module.PATH
    else:
        path = args.pipeline
        module = core.load_pipeline(path)
    status = "reference" if args.reference else ("null" if args.null else "exploratory")
    prefix = {"reference": "ref", "null": "n", "exploratory": "r"}[status]
    run_id = _next_id(prefix, runs)
    record = {
        "run_id": run_id, "status": status, "pipeline": path,
        "time": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "frame_hash": fhash, "code_hash": core.code_hash(path),
        "data_hash": "-".join(config.sha256_file(p) for p in core.dev_files()),
        "features": list(module.FEATURES), "note": args.note,
    }

    problems = core.feature_violations(module.FEATURES, registry)
    if problems:
        return refuse(record, problems, 4, "RUN REFUSED (I5)")

    # budget checked BEFORE spending it: a grid that would overshoot is refused, not counted
    budget = spec.get("exploration_budget")
    recent = [r for r in runs if r["status"] == "exploratory" and r["frame_hash"] == fhash]
    before = sum(r.get("n_candidates", 1) for r in recent)
    prototype = module.build()
    from sklearn.model_selection import GridSearchCV, RandomizedSearchCV
    def raw_search(m):
        return isinstance(m, (GridSearchCV, RandomizedSearchCV)) or any(raw_search(c) for c in core._children(m))
    if raw_search(prototype):
        return refuse(record, ["raw sklearn search refused before fitting; use an audited temporal procedure"], 4, "RUN REFUSED (search)")
    planned = core.planned_candidates(prototype)
    record["planned_candidates"] = planned
    if status == "exploratory" and budget and before + planned > budget:
        left = max(budget - before, 0)
        return refuse(record, [f"budget d'exploration : {before}/{budget} comparisons done, il en reste {left} ; "
                               f"ce run en compare {planned}. Reduce the grid or request a human decision "
                               "(increase the budget only through a justified frame: commit)."], 8, "RUN REFUSED (budget)")

    df = core.load_dev(spec)
    strength, end = dq.used_strength(df, list(module.FEATURES), spec)
    suspects, lim = dq.leak_suspects(strength, registry, exempt=reference.columns(spec))
    record["univariate_auc"] = {c: round(a, 4) for c, a in strength.items()}
    if suspects and not args.null:
        return refuse(record, [f"D6: individually predicts the target above AUC {lim} (measured through {end}) : "
                               + ", ".join(suspects) + ". A person must explain it (leak_ack in features.yaml) "
                               "or exclude it before any run."], 4, "RUN REFUSED (D6, probable leakage)")
    violations = dq.contract_violations(df, registry, dq.quality_settings().get("min_rows_month", 200))
    if violations:
        print("DATA CONTRACT VIOLATED (D1) — human decision required before any run:\n  " +
              "\n  ".join(f"{c}: {', '.join(p)}" for c, p in violations.items()), file=sys.stderr)
        return 6
    result = evaluate(module, df, spec, permute=args.null,
                      preds_path=None if args.null else config.PREDS_DIR / f"{run_id}.csv.gz")
    record.update(result)
    primary = spec["metric_primary"]
    code = 0

    if status == "null":
        auc = result["summary"].get("roc_auc", {}).get("mean")
        lo, hi = config.stops_config()[0]["null_auc_band"]
        record["null_pass"] = auc is not None and lo <= auc <= hi
        print(f"{run_id} test nul : AUC {auc:.3f} — {'OK' if record['null_pass'] else 'FAILURE: the pipeline learns from a random target'}")
        if not record["null_pass"]:
            code = 3
    elif status == "exploratory":
        ref = latest_reference(runs, fhash)
        if ref is None:
            print("No reference for this frame: first run `python -m mlkit.run --reference`.", file=sys.stderr)
            return 2
        gains = [core.gain(spec, ref["per_window"][w][primary], result["per_window"][w][primary])
                 for w in result["per_window"]]
        g_mean, g_std = float(np.mean(gains)), float(np.std(gains, ddof=1)) if len(gains) > 1 else 0.0
        conclusive = g_mean - g_std > 0          # heuristic noise floor, see README
        record.update(reference=ref["run_id"], gain={"mean": g_mean, "std": g_std, "per_window": gains},
                      conclusive=bool(conclusive))
        thresholds, private = config.stops_config()
        triggers = []
        if result["n_candidates"] != planned:   # build() changed between the check and the fit
            triggers.append(f"announced candidates {planned} ≠ compared {result['n_candidates']}: the budget was checked against another model")
        if g_mean > thresholds["too_good_gain"]:
            triggers.append(f"gain too beau : {g_mean:+.4f} au-dessus du threshold")
        streak = 0
        for r in reversed(recent):
            if r.get("conclusive"):
                break
            streak += 1
        if not conclusive and streak + 1 >= thresholds["stagnation_runs"]:
            triggers.append(f"stagnation : {streak + 1} runs exploratory without gain conclusive")
        record["n_candidates"] = max(result["n_candidates"], planned)   # the larger one is what was spent
        after = before + record["n_candidates"]
        record["comparisons_total"] = after
        if budget and before < budget <= after:
            triggers.append(f"budget d'exploration reached : {after} comparisons for a budget of {budget} (Q-MOD-03)")
        record["triggers"] = triggers
        print(f"{run_id} {primary} {result['summary'][primary]['mean']:.4f} · gain {g_mean:+.4f} ± {g_std:.4f} · "
              f"{'conclusive' if conclusive else 'non conclusive'} · comparisons {after}"
              + (f"/{budget}" if budget else "") + (f" (tuning: {result['n_candidates']} candidats)" if result["n_candidates"] > 1 else ""))
        if triggers:
            config.STOPS_DIR.mkdir(parents=True, exist_ok=True)
            stop = {"stop_id": f"STOP-{run_id}", "run_id": run_id, "triggers": triggers,
                    "thresholds_private": private, "time": record["time"]}
            (config.STOPS_DIR / f"STOP-{run_id}.json").write_text(json.dumps(stop, ensure_ascii=False, indent=2))
            print("STOP TRIGGERED: " + " ; ".join(triggers) +
                  f"\nPrepare the report: python -m mlkit.handoff --run {run_id} --role stop-writer", file=sys.stderr)
            code = 3
    else:
        print(f"{run_id} reference {primary} {result['summary'][primary]['mean']:.4f}")

    config.append_jsonl(config.REGISTRY_FILE, record)
    if status == "reference" and spec.get("reference_secondary_pipeline"):
        secondary_reference(spec, fhash, record, df, registry, runs)
    from . import render
    render.safe_render()
    return code


if __name__ == "__main__":
    sys.exit(main())
