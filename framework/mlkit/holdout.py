"""Confirmatory evaluation on the holdout. Run by a PERSON, or by the CI holdout
workflow behind an approval. Never from an agent session.

    OSML_HOLDOUT_DIR=~/.hypotrail-ml/<project>/holdout \
        python -m mlkit.holdout --prereg preregistrations/c-001.yaml

Refuses unless: the phase gate "holdout" is open (questions answered), the
pre-registration is committed in git, a passing null test and an evaluation report
exist for the same code, budget remains, and a drift report on the holdout (E4, mlkit.drift)
exists for the same code and data. Its verdict is INFORMATIVE (it measures a change of population, not a loss
of gain): it is copied into the ledger, the reading report and the model card, and blocks nothing — unless
evaluation.drift_blocking: true, where a BROKEN CONTRACT needs a DRIFT-ACK line in decisions.md. The decision
threshold comes from the evaluation report: it was fixed on the validation windows, never on the holdout.

Policy (lot 2, after the reviews of XP1):
- the reading does NOT require E1 to pass: the best candidate can be measured, to be
  discussed with the business; E1 still blocks ACCEPTANCE and mlkit.package;
- the budget belongs to the HOLDOUT (fingerprint of its files), not to a frame version:
  changing the frame no longer re-opens readings;
- after a first reading, the acceptance threshold cannot change (renegotiation needs a
  new holdout), and a later reading must be on a candidate that existed before the first.
"""
from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys

import numpy as np

import json

from . import config, core, decision, gate, reference
from .evaluate import calibration


def committed_at(path: str) -> int | None:
    try:
        out = subprocess.run(["git", "log", "--diff-filter=A", "--format=%ct", "--", path],
                             cwd=config.ROOT, capture_output=True, text=True, check=True).stdout.split()
        return int(out[-1]) if out else None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


SKETCH = 256


def holdout_identity(spec: dict) -> dict:
    """Who the holdout IS: the set of its loan ids, not its bytes (re-compressing, dropping a column or a few
    rows must not make it « new » — fresh reviews, lots 1-2). `hash` names the exact set; `sketch` (the 256
    smallest hashed ids, a bottom-k sketch) lets a later reading recognise a holdout that overlaps an old one."""
    import hashlib
    import pandas as pd
    ids = pd.read_csv(config.holdout_dir() / "labels.csv.gz", usecols=[spec["id_col"]])[spec["id_col"]].astype(str)
    ids = sorted(set(ids))
    h = [int(hashlib.sha256(i.encode()).hexdigest()[:15], 16) for i in ids]
    return {"hash": config.sha256_text("\n".join(ids)), "sketch": sorted(h)[:SKETCH], "n": len(ids)}


def jaccard(a: list[int], b: list[int]) -> float:
    """Bottom-k estimate of |A ∩ B| / |A ∪ B| from two sketches."""
    union = sorted(set(a) | set(b))[:SKETCH]
    if not union:
        return 0.0
    return len(set(union) & set(a) & set(b)) / len(union)


def readings_of(ledger: list[dict], ident: dict) -> list[dict]:
    """Earlier readings of this holdout: same id set, or an id set overlapping it by more than half."""
    out = []
    for e in ledger:
        if e.get("holdout_hash") == ident["hash"] or (e.get("holdout_sketch") and jaccard(e["holdout_sketch"], ident["sketch"]) > 0.5):
            out.append(e)
    return out


def metrics_table(metrics: dict) -> str:
    """Reference (score in place) and candidate; a re-fitted reference, if declared, beside — never alone."""
    second = any("reference_secondary" in v for v in metrics.values())
    head = "| metric | reference (incumbent score) |" + (" refitted reference (information) |" if second else "") + " candidat |\n"
    head += "|---|---|" + ("---|" if second else "") + "---|\n"
    return head + "".join(
        f"| {m} | {v['reference']:.4f} |" + (f" {v.get('reference_secondary', float('nan')):.4f} |" if second else "")
        + f" {v['candidate']:.4f} |\n" for m, v in metrics.items())


def adopt_legacy(min_gain: float | None) -> int:
    """Append-only: one adoption entry stands for the earlier, unfingerprinted readings."""
    if min_gain is None:
        raise SystemExit("--legacy-min-gain is required: the historical threshold freezes subsequent readings")
    ledger = config.read_jsonl(config.LEDGER_FILE)
    legacy = [e for e in ledger if "holdout_hash" not in e and not e.get("legacy_adoption")]
    adopted = sum(e.get("count", 0) for e in ledger if e.get("legacy_adoption"))
    n = len(legacy) - adopted
    if n <= 0:
        print("nothing to attach")
        return 0
    spec = config.load_frame()["spec"]
    ident = holdout_identity(spec)
    config.append_jsonl(config.LEDGER_FILE, {
        "legacy_adoption": True, "count": n, "min_gain": float(min_gain), "holdout_hash": ident["hash"],
        "holdout_sketch": ident["sketch"], "holdout_n": ident["n"], "frame_hash": config.frame_hash(),
        "time": min(e["time"] for e in legacy), "prereg": "anciennes-readings"})
    print(f"{n} pre-lot-2 readings attached to this holdout, threshold {min_gain}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m mlkit.holdout")
    ap.add_argument("--prereg", required=True)
    ap.add_argument("--allow-uncommitted", action="store_true",
                    help="local dry run only; the ledger entry is marked unverified")
    ap.add_argument("--adopt-legacy", action="store_true",
                    help="attach pre-lot-2 readings to the OSML_HOLDOUT_DIR holdout (one human action)")
    ap.add_argument("--legacy-min-gain", type=float, help="threshold en vigueur lors de ces readings")
    args = ap.parse_args(argv)

    raise SystemExit("Reviewed 4.2-dev: confirmatory reading is suspended pending an isolated evaluator and protocol validation. Development analyses and the pilot remain available.")

    if args.adopt_legacy:
        return adopt_legacy(args.legacy_min_gain)
    if not gate.require("holdout"):
        return 7
    frame = config.load_frame()
    spec, fhash = frame["spec"], config.frame_hash()
    prereg = config.load_yaml(config.ROOT / args.prereg)
    for key in ("id", "pipeline", "run", "hypothesis", "expected_gain", "null_run"):
        if key not in prereg:
            raise SystemExit(f"incomplete preregistration: field {key!r} missing")
    from . import ensemble; ensemble.require(str(prereg["run"]), "preregistration")   # spec.selection_rule

    ledger = config.read_jsonl(config.LEDGER_FILE)
    legacy = [e for e in ledger if "holdout_hash" not in e and not e.get("legacy_adoption")]
    adopted = sum(e.get("count", 0) for e in ledger if e.get("legacy_adoption"))
    if len(legacy) > adopted:
        raise SystemExit(f"{len(legacy)} pre-lot-2 ledger readings do not identify their holdout. "
                         "A person must attach them once: python -m mlkit.holdout --adopt-legacy "
                         "--legacy-min-gain <historical threshold> (with OSML_HOLDOUT_DIR pointing to the holdout previously read).")
    ident = holdout_identity(spec)
    hhash = ident["hash"]
    used = readings_of(ledger, ident)
    n_used = sum(int(e.get("count", 1)) for e in used)
    budget = int(spec["holdout"]["budget"])
    if n_used >= budget:
        raise SystemExit(f"BUDGET EXHAUSTED : {n_used}/{budget} readings de ce holdout, all versions du frame confondues. "
                         "A fresh holdout is required.")
    mg = decision.min_gain(spec)
    decision.require_usable(mg)
    rate = float(spec.get("evaluation", {}).get("decision_rate", 0.9))
    p = spec["metric_primary"]
    if p.startswith("bad_rate_at_approval_") and abs(int(p.rsplit("_", 1)[1]) / 100 - rate) > 1e-9:
        raise SystemExit(f"metric_primary ({p}) et evaluation.decision_rate ({rate}) describe different policies")
    if used and any("min_gain" not in e for e in used):
        raise SystemExit("an earlier reading of this holdout did not record its threshold: cannot establish "
                         "that it was not renegotiated. A fresh holdout is required.")
    rule = decision.acceptance_rule(spec)
    if used and any(e.get("acceptance_rule", "expected_value") != rule for e in used):
        raise SystemExit(f"Acceptance rule changed after reading this holdout (→ {rule}). "
                         "Choosing a rule after seeing results is renegotiation: a fresh holdout is required.")
    if used and any(abs(e["min_gain"] - mg["min_gain"]) > 1e-12 for e in used):
        raise SystemExit(f"Acceptance threshold changed after reading this holdout ({used[0].get('min_gain')} → "
                         f"{mg['min_gain']}). Post-reading renegotiation requires a fresh holdout.")

    t_commit = committed_at(args.prereg)
    if t_commit is None and not args.allow_uncommitted:
        raise SystemExit("Preregistration must be committed BEFORE reading the holdout.")

    module = core.load_pipeline(prereg["pipeline"])
    code_hash = config.sha256_file(config.ROOT / prereg["pipeline"])
    runs = {r["run_id"]: r for r in config.read_jsonl(config.REGISTRY_FILE)}
    null = runs.get(prereg["null_run"])
    if not null or null.get("status") != "null" or not null.get("null_pass") or null["code_hash"] != code_hash:
        raise SystemExit("Null test missing, failed, or performed on another pipeline version.")
    run = runs.get(prereg["run"])
    if not run or run.get("status") != "exploratory" or run.get("code_hash") != code_hash or run["frame_hash"] != fhash:
        raise SystemExit(f"run {prereg['run']}: missing, nonexploratory, stale, or measured with another pipeline version")
    f = config.REPORTS_DIR / f"eval-{prereg['run']}.json"
    if not f.exists():
        raise SystemExit("Evaluation report missing for this run: python -m mlkit.evaluate --run " + prereg["run"] +
                         " (sets the decision threshold on validation)")
    ev = json.loads(f.read_text(encoding="utf-8"))
    if ev["code_hash"] != code_hash or ev["frame_hash"] != fhash:
        raise SystemExit("evaluation report does not match this code or frame: rerun mlkit.evaluate")
    if used:
        first = min(e["time"] for e in used)
        born = run.get("time")
        if not born or born > first:
            raise SystemExit(f"{ev['run']} was created after the first reading of this holdout ({first}): a reading "
                             "subsequent reading cannot concern a candidate changed after seeing a result.")
    problems = core.feature_violations(module.FEATURES, config.load_features())
    if problems:
        raise SystemExit("Refused features (I5): " + "; ".join(problems))
    from . import drift
    drift_record = drift.require_for_holdout(args.prereg, code_hash, spec)     # E4

    dev = core.load_dev(spec)
    hold = core.align_like(core.load_split(config.holdout_dir(), spec), dev)
    train_end, start, end = core.holdout_window(spec)
    tr = dev["_month"] <= train_end
    te = (hold["_month"] >= start) & (hold["_month"] <= end)
    overlap = set(dev[spec["id_col"]]) & set(hold[spec["id_col"]])
    if overlap:
        raise SystemExit(f"I4 : {len(overlap)} identifiers in both development and holdout")

    bad_ref = reference.problems(spec)
    if bad_ref:
        raise SystemExit("nonconforming reference (F9): " + "; ".join(bad_ref))
    ref_mod = reference.module(spec)
    y = hold.loc[te, spec["target_col"]].to_numpy()
    s_ref = core.fit_predict(ref_mod, dev.loc[tr, ref_mod.FEATURES], dev.loc[tr, spec["target_col"]], hold.loc[te, ref_mod.FEATURES])
    s_cand = core.fit_predict(module, dev.loc[tr, module.FEATURES], dev.loc[tr, spec["target_col"]], hold.loc[te, module.FEATURES])

    metrics = {m: {"reference": core.compute_metric(m, y, s_ref), "candidate": core.compute_metric(m, y, s_cand)}
               for m in core.all_metrics(spec)}
    if spec.get("reference_secondary_pipeline"):   # shown beside, never used for the gain
        mod2 = core.load_pipeline(spec["reference_secondary_pipeline"])
        s_ref2 = core.fit_predict(mod2, dev.loc[tr, mod2.FEATURES], dev.loc[tr, spec["target_col"]], hold.loc[te, mod2.FEATURES])
        for m in metrics:
            metrics[m]["reference_secondary"] = core.compute_metric(m, y, s_ref2)
    g = core.gain(spec, metrics[p]["reference"], metrics[p]["candidate"])
    acc = spec["acceptance"]
    boot = acc.get("bootstrap", {}) or {}
    hg = decision.holdout_decision(y, s_ref, s_cand, hold.loc[te, "_month"].astype(str).to_numpy(), rate,
                                   mg["min_gain"], float(acc["ci_level"]), rule,
                                   B=int(boot.get("B", 2000)), seed=int(boot.get("seed", 0)))
    se = hg["se"]
    lo, hi = hg["ci"]
    lin, bb = hg["linearisation"], hg["block_bootstrap"]
    accepted = hg["pass"] and bool(ev["e1_pass"])
    mde_obs = decision.z_detect(float(acc["ci_level"])) * se    # smallest gain this reading could tell from zero
    thr = ev["threshold"]["mean"]
    acc_mask = s_cand <= thr
    _, ece = calibration(y, s_cand)
    at_threshold = {"threshold": thr, "approval": float(acc_mask.mean()),
                    "bad_rate_accepted": float(y[acc_mask].mean()) if acc_mask.any() else None, "ece": ece}

    entry = {"prereg": prereg["id"], "pipeline": prereg["pipeline"], "code_hash": code_hash,
             "frame_hash": fhash, "time": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
             "n_test": int(te.sum()), "metrics": metrics, "gain": g, "gain_ci": [lo, hi],
             "accepted": bool(accepted), "holdout_pass": hg["pass"], "e1_pass": bool(ev["e1_pass"]),
             "gain_se": se, "mde_observed": mde_obs, "acceptance_rule": rule, "ci_method": hg["method"],
             "lower_one_sided": hg["lower_one_sided"], "ci_warning": hg["warning"],
             "ci_linearisation": lin["ci"], "se_linearisation": lin["se"],
             "ci_block_bootstrap": (bb["gate"] or {}).get("ci"), "se_block_bootstrap": bb["se"],
             "n_months": bb["n_blocks"], "bootstrap_B": bb["B"], "bootstrap_exact": bb["exact"], "min_gain": mg["min_gain"], "min_gain_source": mg["text"],
             "holdout_hash": hhash, "holdout_sketch": ident["sketch"], "holdout_n": ident["n"],
             "verified_commit": t_commit is not None,
             "evaluation": f"eval-{ev['run']}", "at_threshold": at_threshold,
             "reading": n_used + 1, "budget": budget, "drift": drift_record}
    config.append_jsonl(config.LEDGER_FILE, entry)

    n_runs = sum(1 for r in runs.values() if r["frame_hash"] == fhash and r["status"] == "exploratory")
    config.REPORTS_DIR.mkdir(exist_ok=True)
    report = config.REPORTS_DIR / f"{prereg['id']}.md"
    report.write_text(
        f"# Confirmatory result {prereg['id']}\n\n"
        f"- Hypothesis : {prereg['hypothesis']}\n- Expected gain (preregistered): {prereg['expected_gain']}\n"
        f"- Observed holdout gain ({p}) : {g:+.4f}, IC {acc['ci_level']:.0%} [{lo:+.4f} ; {hi:+.4f}] "
        f"({'paired monthly-block bootstrap' if hg['method'] == 'block_bootstrap' else 'linearization'}, used for the decision)\n"
        f"- Both intervals: linearization (independent loans) [{lin['ci'][0]:+.4f} ; {lin['ci'][1]:+.4f}] · "
        + (f"bootstrap par blocs ({bb['n_blocks']} months, {'exact enumeration' if bb['exact'] else str(bb['B']) + ' tirages'}, "
           f"t at {bb['n_blocks'] - 1} ddl) [{bb['gate']['ci'][0]:+.4f} ; {bb['gate']['ci'][1]:+.4f}]\n" if bb["gate"] else "bootstrap par blocs impossible (un only months)\n")
        + (f"- **Warning** : {hg['warning']}\n" if hg["warning"] else "")
        + f"- Acceptance rule: **{rule}** — "
        + (f"gain ≥ threshold AND two-sided CI lower bound > 0 (expected value)" if rule == "expected_value" else
           f"one-sided lower bound at {acc['ci_level']:.0%} ({hg['lower_one_sided']:+.4f}) > threshold (superiority with margin)") + "\n"
        f"- Acceptance threshold: {mg['min_gain']:+.4f} ({mg['text']}) · smallest gain this reading could "
        f"distinguish from zero: {mde_obs:.4f}\n"
        f"- Holdout test: {'PASS' if hg['pass'] else 'FAILURE'} · backtest E1 evaluation: "
        f"{'PASS' if ev['e1_pass'] else 'FAILURE — ' + '; '.join(ev.get('e1_reasons', []))}\n"
        f"- **Decision: {'ACCEPTED' if accepted else 'NOT ACCEPTED'}** (both required)\n"
        f"- Lecture du holdout : {n_used + 1}/{budget}\n"
        f"- Threshold frozen on validation (run:{ev['run']}) : {thr:.4f} → acceptation {at_threshold['approval']:.1%}, "
        f"default rate among accepted cases {at_threshold['bad_rate_accepted']:.2%}, calibration ECE {ece:.4f}\n"
        f"- Runs exploratory under ce frame : {n_runs}\n- Test nul : run:{prereg['null_run']}\n\n"
        + metrics_table(metrics)
        + "\n## Unlabeled drift (E4, informative" + (", blocking under the frame" if drift_record.get("blocking") else "")
        + ") — reports/drift-holdout.md\n\n" + "".join(f"- {x}\n" for x in drift_record["summary"]["lines"]),
        encoding="utf-8")
    print(f"{prereg['id']} : gain {g:+.4f} [{lo:+.4f} ; {hi:+.4f}] — {'ACCEPTED' if accepted else 'REFUSED'} "
          f"· lecture {n_used + 1}/{budget} · report {report.relative_to(config.ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
