"""Deterministic invariants. No LLM. Run in CI and locally.

    python -m mlkit.checks                 # structural checks (CI, no data needed)
    python -m mlkit.checks --data          # + checks that read data/dev
    python -m mlkit.checks --base origin/main   # + append-only check against a base

I1-I8 protect the evaluation. D1-D6 protect the data: its contract, its registry,
its meaning, its stability over time and the traceability of its preparation.

Each line says what is verified. Each check has a known blind spot (README).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd

from . import config, core, dataquality as dq, gate

RESULTS: list[tuple[str, bool, str]] = []


def report(check: str, ok: bool, detail: str) -> None:
    RESULTS.append((check, ok, detail))


def i1_frame_coverage(frame):
    bad = []
    for sid, st in frame["statements"].items():
        checks = set(st.get("checked_by", []))
        if not checks and not st.get("exempt"):
            bad.append(f"{sid} without a check or exemption")
        if checks - config.KNOWN_CHECKS:
            bad.append(f"{sid} cites an unknown check {sorted(checks - config.KNOWN_CHECKS)}")
    report("I1 couverture du frame", not bad, "; ".join(bad) or f"{len(frame['statements'])} statements covered or exempted")


def i2_metrics_declared(frame, runs, fhash):
    wanted = set(core.all_metrics(frame["spec"]))
    bad = [r["run_id"] for r in runs
           if r["frame_hash"] == fhash and r["status"] in ("reference", "exploratory")
           and not wanted <= set(r.get("summary", {}))]
    report("I2 frame metrics present", not bad, ", ".join(bad) or "all preregistered metrics are calculated")


def i3_provenance(runs, ledger, fhash):
    ids = {r["run_id"]: r for r in runs}
    bad = []
    for rep in sorted(config.REPORTS_DIR.glob("*.md")) if config.REPORTS_DIR.exists() else []:
        for ref in re.findall(r"run:([a-z0-9]+-\d{4})", rep.read_text(encoding="utf-8")):
            if ref not in ids:
                bad.append(f"{rep.name} cite run:{ref} absent du registry")
            elif ids[ref]["frame_hash"] != fhash:
                bad.append(f"{rep.name} cite run:{ref}, stale (I7)")
    for e in ledger:
        if e.get("legacy_adoption"):
            continue
        if not e.get("verified_commit"):
            bad.append(f"lecture holdout {e['prereg']} without preregistration committed")
    if not any(r["status"] == "reference" and r["frame_hash"] == fhash for r in runs) and runs:
        bad.append("no reference calculated under the current frame")
    report("I3 numerical provenance", not bad, "; ".join(bad) or "each reported number has a valid run")


def i3_reference(frame):
    """The reference is the score in place, as is (XP1); a re-fitted one must be justified."""
    from . import reference
    spec = frame["spec"]
    try:
        bad = reference.problems(spec)
        if not bad:
            reference.module(spec).build()
    except (SystemExit, Exception) as exc:   # a broken reference file is a failure, not a crash
        bad = [f"reference: {exc}"]
    kind = reference.settings(spec).get("kind")
    report("I3 reference = incumbent score", not bad, "; ".join(bad) or
           ("incumbent score used unchanged" if kind == "existing_score" else "refitted reference justified in the frame"))


def i5_pipelines(registry):
    bad = []
    for path in sorted((config.ROOT / "model").glob("*.py")):
        src = path.read_text(encoding="utf-8")
        if re.search(r"\b(train_test_split|KFold|TimeSeriesSplit|cross_val_score|GridSearchCV|RandomizedSearchCV|HalvingGridSearchCV)\b", src):
            bad.append(f"{path.name}: creates its own split; the runner owns splitting. Use mlkit.tuning.TimeAwareSearch for tuning.")
        if re.search(r"\b(read_csv|read_parquet|dropna\(|drop_duplicates|\.query\()", src):
            bad.append(f"{path.name}: reads or filters rows; source cleaning belongs in preparation")
        if "FEATURES" in src:
            module = core.load_pipeline(str(path.relative_to(config.ROOT)))
            bad += [f"{path.name}: {p}" for p in core.feature_violations(module.FEATURES, registry)]
    inferred = [k for k, v in registry.items() if v.get("owner") != "HUMAN"]
    detail = "; ".join(bad) or "pipelines conformes au registry"
    if inferred:
        detail += f" · review first (owner INFERRED): {', '.join(inferred)}"
    report("I5 feature provenance", not bad, detail)


def i6_budget(frame, ledger, fhash):
    """The budget belongs to the holdout (its fingerprint), whatever the frame version; the threshold
    does not move after a reading. Same counting as mlkit.holdout (config.readings_of_current_holdout)."""
    budget = int(frame["spec"]["holdout"]["budget"])
    cur = config.readings_of_current_holdout(ledger)
    n = config.n_readings(cur)
    bad = [f"{n}/{budget} readings of the current holdout"] if n > budget else []
    if len({e.get("min_gain") for e in cur}) > 1:
        bad.append("threshold differs between two readings of the same holdout")
    report("I6 holdout budget", not bad, "; ".join(bad) or f"{n}/{budget} readings of the current holdout")


def i7_staleness(runs, fhash):
    stale = sum(1 for r in runs if r["frame_hash"] != fhash)
    report("I7 staleness", True, f"{stale} stale runs (frame changed); ignored by other checks")


def i8_open_stops():
    from .run import open_stops
    opened = open_stops()
    report("I8 resolved stops", not opened, ", ".join(opened) or "no stop awaiting a decision")


def append_only(base: str):
    for rel in ("experiments/registry.jsonl", "holdout/ledger.jsonl"):
        try:
            old = subprocess.run(["git", "show", f"{base}:{rel}"], cwd=config.ROOT,
                                 capture_output=True, text=True, check=True).stdout
        except subprocess.CalledProcessError:
            continue  # file absent in base
        new = (config.ROOT / rel).read_text(encoding="utf-8") if (config.ROOT / rel).exists() else ""
        report(f"ajout only {rel}", new.startswith(old), "historique intact" if new.startswith(old)
               else "existing rows were modified or deleted")


def i4_split_integrity(frame):
    spec = frame["spec"]
    df = core.load_dev(spec)
    bad = []
    dup = int(df[spec["id_col"]].duplicated().sum())
    if dup:
        bad.append(f"{dup} duplicate development identifiers")
    for name, train_end, start, end in core.windows(spec):
        tr = df[df["_month"] <= train_end]
        te = df[(df["_month"] >= start) & (df["_month"] <= end)]
        if (start - tr["_month"].max()).n < int(spec["backtest"]["gap_months"]):
            bad.append(f"{name}: gap shorter than observation delay")
        if spec.get("group_col"):
            shared = set(tr[spec["group_col"]]) & set(te[spec["group_col"]])
            if shared:
                bad.append(f"{name}: {len(shared)} groups in both training and test")
        cols = [c for c in df.columns if c not in (spec["id_col"], spec["target_col"], "_month", spec["time_col"])]
        n_dup = len(pd.merge(tr[cols].drop_duplicates(), te[cols].drop_duplicates(), how="inner"))
        if n_dup:
            bad.append(f"{name}: {n_dup} rows identiques (outside id) en train et en test")
    report("I4 split integrity", not bad, "; ".join(bad) or "no overlap; gap respected")


# ---------------------------------------------------------------- data invariants
ALLOWED_KEYS = {"available", "owner", "excluded_by", "meaning", "unit", "note", "transform", "special_values",
                "derived_from", "formula", "contract", "drift_ack", "leak_ack", "expected_direction"}


def d3_registry_semantics(registry):
    """Structural: derived features, keys, contract types. No data needed."""
    bad = []
    for col, e in registry.items():
        unknown = set(e) - ALLOWED_KEYS
        if unknown:
            bad.append(f"{col}: unknown keys {sorted(unknown)}")
        if e.get("available") not in ("origination", "post_origination"):
            bad.append(f"{col}: available must be origination or post_origination")
        if "contract" in e and e["contract"].get("type") not in ("numeric", "categorical"):
            bad.append(f"{col}: contract.type must be numeric or categorical")
        srcs = e.get("derived_from", [])
        if srcs and "formula" not in e:
            bad.append(f"{col}: derived without a formula")
        for s in srcs:
            if s not in registry:
                bad.append(f"{col}: source {s} missing du registry")
            elif registry[s].get("available") != "origination" and e.get("available") == "origination":
                bad.append(f"{col}: declared available at origination but derived from {s} ({registry[s].get('available')})")
        if e.get("available") == "origination" and not e.get("excluded_by") and "meaning" not in e:
            bad.append(f"{col}: utilisable mais undocumented meaning")
    report("D3 registry: meaning and derivations", not bad, "; ".join(bad) or f"{len(registry)} documented columns")


def used_features():
    used = set()
    for path in sorted((config.ROOT / "model").glob("*.py")):
        if "FEATURES" in path.read_text(encoding="utf-8"):
            used |= set(core.load_pipeline(str(path.relative_to(config.ROOT))).FEATURES)
    return used


def data_invariants(frame, registry):
    spec, q = frame["spec"], dq.quality_settings()
    df = dq.read_features(spec)
    labels = pd.read_csv(config.DEV_DIR / "labels.csv.gz")

    viol = dq.contract_violations(df, registry, q.get("min_rows_month", 200))
    report("D1 data contract", not viol,
           "; ".join(f"{c}: {', '.join(p)}" for c, p in viol.items()) or "all columns meet their contract")

    data_cols = [c for c in df.columns if c != "_month"]
    unknown = [c for c in data_cols if c not in registry]
    absent = [c for c, e in registry.items() if c not in data_cols and e.get("available") == "origination"
              and not e.get("excluded_by")]
    detail = (f"columns inconnues du registry : {', '.join(unknown)}" if unknown else "all columns are declared")
    if absent:
        detail += f" · declared but absent from data: {', '.join(absent)}"
    report("D2 registry complet", not unknown, detail)

    used = used_features()
    stab = dq.stability(df, registry, spec)
    stop, warn = q.get("psi_stop", 0.25), q.get("psi_warn", 0.1)
    bad = [f"{c} (PSI {stab[c]['max']:.2f})" for c in sorted(used)
           if c in stab and stab[c]["max"] > stop and not registry.get(c, {}).get("drift_ack")]
    warned = [c for c in used if c in stab and warn < stab[c]["max"] <= stop]
    report("D4 stability of used features", not bad,
           ("unstable without drift_ack: " + ", ".join(bad)) if bad else
           f"no drift above {stop}" + (f" · monitor: {', '.join(sorted(warned))}" if warned else ""))

    probs = dq.manifest_problems()
    report("D5 tracked preparation", not probs, "; ".join(probs) or "data comes from declared scripts and decisions")

    strength, end = dq.univariate_strength(df, labels, spec)
    lim = q.get("univariate_auc_stop", 0.8)
    sus = [f"{c} (AUC {strength[c]:.2f})" for c, e in registry.items()
           if e.get("available") == "origination" and not e.get("excluded_by") and not e.get("leak_ack")
           and strength.get(c, 0) >= lim]
    report("D6 individually overpredictive feature", not sus,
           ("justify with leak_ack or reclassify: " + ", ".join(sus) + f" — measured through {end}") if sus
           else f"no origination column above AUC {lim} alone")


# ---------------------------------------------------------------- maturity, evaluation, gates
def d7_label_maturity(frame):
    spec, m = frame["spec"], dq.manifest() or {}
    as_of = m.get("as_of")
    if not as_of:
        report("D7 label maturity", False, "date d'extraction (as_of) missing du manifeste (Q-CIB-08)")
        return
    last = pd.Period(spec["holdout"]["window"][1], "M")
    due = last + int(spec["label_delay_months"])
    ok = due <= pd.Period(as_of, "M")
    report("D7 label maturity", ok, f"latest month used {last} + {spec['label_delay_months']} months = {due}, extraction {as_of}"
           + ("" if ok else ": some labels are not yet observable and are incorrectly treated as negatives"))


def e1_evaluation(ledger, fhash):
    bad = []
    for e in ledger:
        if e["frame_hash"] != fhash or e.get("legacy_adoption"):
            continue
        f = config.REPORTS_DIR / f"{e.get('evaluation', '?')}.json"
        if not f.exists():
            bad.append(f"{e['prereg']} : report d'evaluation absent")
            continue
        ev = json.loads(f.read_text(encoding="utf-8"))
        if ev["code_hash"] != e["code_hash"]:
            bad.append(f"{e['prereg']} : evaluation used different code")
        elif e.get("accepted") and not ev["e1_pass"]:
            bad.append(f"{e['prereg']}: accepted although E1 evaluation failed")
    unev = sorted({f"{u['segment']} ({u['why']})" for f in config.REPORTS_DIR.glob("eval-*.json")
                   for u in (json.loads(f.read_text(encoding="utf-8")).get("noninferiority", {}).get("unevaluable") or [])
                   if json.loads(f.read_text(encoding="utf-8")).get("frame_hash") == fhash})
    report("E1 evaluation before confirmation", not bad, ("; ".join(bad) or
           "each reading follows evaluation of the same code; no acceptance without E1")
           + (" · preregistered segments NOT EVALUABLE: " + "; ".join(unev) if unev else ""))


def e3_threshold(frame, with_data: bool):
    """The threshold comes from costs (or a written source), and is above what the holdout can detect."""
    from . import decision
    spec = frame["spec"]
    try:
        mg = decision.min_gain(spec)
    except SystemExit as exc:
        report("E3 calculated and measurable threshold", False, str(exc))
        return
    bad = []
    if mg["source"] == "typed" and not mg.get("justification"):
        bad.append("threshold entered without min_gain_source: derive it from costs (acceptance.cost_model)")
    detail = mg["text"]
    if with_data:
        from . import mde
        x = mde.inputs(spec)
        m = decision.mde(x["n_holdout"], x["rate"], x["p_cut"], x["swap_share"],
                         alpha=(1 - float(spec["acceptance"].get("ci_level", 0.9))) / 2)
        detail += f" · detectable ≥ {m['mde'] * 100:.3f} point"
        if mg["min_gain"] < m["mde"]:
            bad.append(f"threshold {mg['min_gain'] * 100:.3f} points below the minimum detectable gain "
                       f"{m['mde'] * 100:.3f} point (python -m mlkit.mde)")
        if decision.acceptance_rule(spec) == "margin":
            r = mde.plausibility(spec, mg["min_gain"], m["se"])
            detail += f" · margin rule: required gain (80% power) ≈ {r['required'] * 100:.3f} point"
            if not r["plausible"]:
                bad.append(f"margin rule: required gain ≈ {r['required'] * 100:.3f} point, {r['why']}")
    report("E3 calculated and measurable threshold", not bad, "; ".join(bad) or detail)


def e4_drift_before_holdout(ledger, fhash):
    """E4 = a drift report on the holdout was present and up to date (same code, dev data, holdout) at every
    reading — mlkit.holdout refuses otherwise and records it (`drift` in the ledger) — and is still there.
    The drift VERDICT is informative and never makes E4 fail, except for readings made under
    evaluation.drift_blocking: true (or before 2026-10-13, when E4 was blocking), whose BROKEN CONTRACT / BLOQUANT
    must keep its signed DRIFT-ACK line. Readings logged before E4 carry no `drift` field."""
    from . import drift
    bad, before, n, verdicts = [], 0, 0, []
    for e in ledger:
        if e.get("legacy_adoption") or e.get("frame_hash") != fhash:
            continue
        d = e.get("drift")
        if not d:
            before += 1
            continue
        n += 1
        verdicts.append(f"{e['prereg']} {d.get('verdict')}")
        was_blocking = d.get("blocking", True)          # no field: recorded when E4 was still blocking
        if was_blocking and d.get("verdict") in (drift.MAJOR, drift.LEGACY_MAJOR)\
                and not drift.acknowledged(d.get("fingerprint", "?")):
            bad.append(f"{e['prereg']}: read under drift_blocking with verdict {d.get('verdict')} ; "
                       f"DRIFT-ACK {d.get('fingerprint')} signature missing from decisions.md")
    if n and not (config.REPORTS_DIR / "drift-holdout.json").exists():
        bad.append("reports/drift-holdout.json missing although the holdout was read")
    detail = "; ".join(bad) or (f"drift report present and current at each reading ({n}) ; verdicts informatifs : "
                                + ", ".join(verdicts) if n else "no holdout reading under this frame")
    if before:
        detail += f" · {before} readings before E4"
    report("E4 drift report before holdout", not bad, detail)


def g1_gates(runs, ledger, fhash):
    reached = []
    if any(r["frame_hash"] == fhash for r in runs):
        reached.append("run")
    if any(e["frame_hash"] == fhash for e in ledger):
        reached.append("holdout")
    if config.MODELS_DIR.exists() and any(config.MODELS_DIR.glob("*/metadata.json")):
        reached.append("package")
    bad = [f"{c} used while {', '.join(q['id'] for q in gate.missing_for(c)[:5])} remains unanswered"
           for c in reached if gate.missing_for(c)]
    bad += gate.consistency_problems()
    report("G1 phase gates", not bad, "; ".join(bad) or f"phases reached: {', '.join(reached) or 'none'} — required questions answered")


# ---------------------------------------------------------------- I9 selection outside the protocol
SELECTION_CALLS = r"\b(mutual_info_classif|SelectKBest|SelectPercentile|SelectFromModel|RFECV|RFE|f_classif|chi2|information_value|woe|weight_of_evidence|corrwith)\b"
SKIP_DIRS = {"mlkit", "tests", ".git", ".venv", "venv", "node_modules", ".osml", "data"}


def i9_selection(frame):
    """Rule changed after IVs were seen; target-based selection outside build() / mlkit.bivariate.

    Blind spot: pure text match. A notebook that hides the label file name gets through.
    """
    bad = []
    ledger = config.read_jsonl(config.ROOT / "experiments" / "selection_ledger.jsonl")
    decisions = (config.ROOT / "decisions.md").read_text(encoding="utf-8") if (config.ROOT / "decisions.md").exists() else ""
    seen = []
    for e in ledger:
        if seen and e["rule_hash"] not in seen and f"selection rule {e['rule_hash']}" not in decisions:
            bad.append(f"{e['sel_id']}: rule {e['rule_hash']} changed after reading IV values ({seen[-1]}), not ratified in decisions.md")
        if e["rule_hash"] not in seen:
            seen.append(e["rule_hash"])
    target = frame["spec"]["target_col"]
    files = []
    for dirpath, dirnames, filenames in os.walk(config.ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        files += [Path(dirpath) / f for f in filenames if f.endswith((".py", ".ipynb"))]
    for p in files:
        rel = p.relative_to(config.ROOT)
        if rel.parts[0] == "model" or (rel.parts[0] == "scripts" and p.name.startswith(("prepare_", "make_synthetic", "plant_bait"))):
            continue
        src = p.read_text(encoding="utf-8", errors="ignore")
        uses_target = "labels.csv" in src or re.search(rf"[\"']{re.escape(target)}[\"']", src)
        if uses_target and re.search(SELECTION_CALLS + r"|groupby\(", src):
            bad.append(f"{rel}: feature-target relationship calculated outside mlkit.bivariate and build()")
    for p in sorted((config.ROOT / "model").glob("*.py")):
        if "labels.csv" in p.read_text(encoding="utf-8"):
            bad.append(f"model/{p.name}: reads the labels file")
    report("I9 selection within the protocol", not bad,
           "; ".join(bad) or f"{len(ledger)} bivariate analyses; rule stable or ratified; no out-of-protocol selection found")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m mlkit.checks")
    ap.add_argument("--data", action="store_true", help="also run checks that read data/dev")
    ap.add_argument("--base", help="git ref for the append-only check, e.g. origin/main")
    args = ap.parse_args(argv)

    frame, registry, fhash = config.load_frame(), config.load_features(), config.frame_hash()
    runs, ledger = config.read_jsonl(config.REGISTRY_FILE), config.read_jsonl(config.LEDGER_FILE)
    i1_frame_coverage(frame)
    i2_metrics_declared(frame, runs, fhash)
    i3_provenance(runs, ledger, fhash)
    i3_reference(frame)
    i5_pipelines(registry)
    i6_budget(frame, ledger, fhash)
    i7_staleness(runs, fhash)
    i8_open_stops()
    i9_selection(frame)
    d3_registry_semantics(registry)
    e1_evaluation(ledger, fhash)
    from . import ensemble; ensemble.check(frame, runs, ledger, fhash, report)   # spec.selection_rule
    e3_threshold(frame, args.data)
    e4_drift_before_holdout(ledger, fhash)
    g1_gates(runs, ledger, fhash)
    if args.base:
        append_only(args.base)
    if args.data:
        i4_split_integrity(frame)
        data_invariants(frame, registry)
        d7_label_maturity(frame)

    width = max(len(c) for c, _, _ in RESULTS)
    for check, ok, detail in RESULTS:
        print(f"{'OK ' if ok else 'KO '} {check.ljust(width)}  {detail}")
    failed = [c for c, ok, _ in RESULTS if not ok]
    print(f"\nframe {fhash} · {len(runs)} runs · {sum(1 for r in runs if r['status'] == 'exploratory' and r['frame_hash'] == fhash)} exploratory under ce frame")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
