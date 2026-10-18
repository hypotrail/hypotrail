"""Model card assembled from the project's own records. Nothing is typed by hand:
every line comes from frame.yaml, answers.yaml, the registries, the reports.

    python -m mlkit.card --prereg c-001        # writes reports/model_card.md

Sections follow the questions a validator asks (TRIPOD+AI / PROBAST+AI spirit):
intended use, data, target and population, method, results, limits, decisions.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import config, dataquality as dq, gate


def answer(answers, qid: str) -> str:
    a = answers.get(qid) or {}
    txt = str(a.get("answer", "")).strip() or "_unanswered_"
    return txt + (" _(example not replaced)_" if a.get("by") == "EXAMPLE" else "")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m mlkit.card")
    ap.add_argument("--prereg", required=True)
    args = ap.parse_args(argv)

    frame, registry = config.load_frame(), config.load_features()
    spec, fhash = frame["spec"], config.frame_hash()
    questions, answers, _ = gate.load()
    runs = [r for r in config.read_jsonl(config.REGISTRY_FILE) if r["frame_hash"] == fhash]
    ledger = [e for e in config.read_jsonl(config.LEDGER_FILE) if e["frame_hash"] == fhash]
    reading = next((e for e in reversed(ledger) if e["prereg"] == args.prereg), None)
    if reading is None:
        raise SystemExit(f"{args.prereg}: no holdout reading under the current frame")
    ev_path = config.REPORTS_DIR / f"{reading['evaluation']}.json"
    ev = json.loads(ev_path.read_text(encoding="utf-8")) if ev_path.exists() else {}
    man = dq.manifest() or {}
    explo = [r for r in runs if r["status"] == "exploratory"]
    comparisons = sum(r.get("n_candidates", 1) for r in explo)
    p = spec["metric_primary"]
    used = next((r["features"] for r in reversed(runs) if r.get("code_hash") == reading["code_hash"]), [])

    L = [f"# Fiche model — {frame.get('project', '')} · {args.prereg}", "",
         f"Generated from project registries · frame {fhash} · pipeline `{reading['pipeline']}` ({reading['code_hash']})", "",
         "## 1. Intended use", "",
         f"- **Decision**: {answer(answers, 'Q-CAD-01')}",
         f"- **Capacity**: {answer(answers, 'Q-CAD-02')}",
         f"- **Mode de calculation** : {answer(answers, 'Q-CAD-07')}",
         f"- **Required explanations**: {answer(answers, 'Q-CAD-09')}",
         f"- **Regulatory status**: {answer(answers, 'Q-CAD-10')} · {answer(answers, 'Q-CAD-11')}",
         "", "## 2. Data", "",
         f"- Source : {answer(answers, 'Q-DON-01')}",
         f"- Extraction (as_of) : {man.get('as_of', '_inconnue_')} · script `{man.get('script', '?')}` ({man.get('script_hash', '?')})",
         "- Preparation steps:"]
    L += [f"  - {s['decision']} {s['what']} : {s['rows_before']:,} → {s['rows_after']:,}" for s in man.get("steps", [])] or ["  - no recorded preparation step"]
    L += [f"- Features du model ({len(used)}) :"]
    L += [f"  - `{f}` — {registry.get(f, {}).get('meaning', '_undocumented meaning_')}" for f in used]
    L += ["", "## 3. Cible et population", "",
          f"- {frame['statements'].get('F2', {}).get('text', '')}",
          f"- Performance window: {answer(answers, 'Q-CIB-02')}",
          f"- Unresolved cases: {answer(answers, 'Q-CIB-03')}",
          f"- **Labeled versus scored population**: {answer(answers, 'Q-CIB-05')}",
          "", "## 4. Method", "",
          f"- Validation: backtest with {len(spec['backtest']['test_windows'])} origines, trou de {spec['backtest']['gap_months']} months.",
          f"- {frame['statements'].get('F9', {}).get('text', '')}",
          f"- **Number of experiments** : {len(explo)} runs exploratory, {comparisons} comparisons in total "
          f"(including tuning), budget {spec.get('exploration_budget', 'not fixed')}.",
          f"- Readings of the current holdout (all frame versions): {config.n_readings(config.readings_of_current_holdout(config.read_jsonl(config.LEDGER_FILE)))} / {spec['holdout']['budget']}.",
          "", "## 5. Results", "",
          f"- **Holdout** ({reading['n_test']:,} loans): gain {reading['gain']:+.4f} over {p}, "
          f"IC {spec['acceptance']['ci_level']:.0%} [{reading['gain_ci'][0]:+.4f} ; {reading['gain_ci'][1]:+.4f}] — "
          f"{'criterion met' if reading['accepted'] else 'criterion NOT met'}.",
          f"- At the threshold frozen on validation ({reading['at_threshold']['threshold']:.4f}) : acceptation "
          f"{reading['at_threshold']['approval']:.1%}, default rate among accepted cases "
          f"{reading['at_threshold']['bad_rate_accepted']:.2%}, calibration ECE {reading['at_threshold']['ece']:.4f}.",
          "", "| metric (holdout) | reference (incumbent score) | model |", "|---|---|---|"]
    L += [f"| {m} | {v['reference']:.4f} | {v['candidate']:.4f} |" for m, v in reading["metrics"].items()]
    if any("reference_secondary" in v for v in reading["metrics"].values()):
        L += ["", "Refitted reference, for information only (never used for gain): " +
              ", ".join(f"{m} {v['reference_secondary']:.4f}" for m, v in reading["metrics"].items() if "reference_secondary" in v) + "."]
    if ev:
        L += ["", f"Backtest and detailed analyses: `reports/{reading['evaluation']}.md` "
                  f"(calibration ECE {ev['calibration']['ece']:.4f}, {len(ev['segments'])} segments, "
                  f"{sum(1 for m in ev['monotonicity'] if not m['ok'])} effect(s) de sens inattendu)."]
    d = reading.get("drift") or {}
    L += ["", "### Unlabeled drift between training and holdout (E4, informative)", ""]
    if d.get("summary"):
        L += [f"- {x}" for x in d["summary"]["lines"]]
    elif d:
        L += [f"- Drift verdict: {d.get('verdict')} · fingerprint {d.get('fingerprint')} (`reports/drift-holdout.md`)"]
    else:
        L += ["- No drift report recorded for this reading (predates E4)."]
    exempt = [f"{k} — {v['exempt']}" for k, v in frame["statements"].items() if v.get("exempt")]
    L += ["", "## 6. Limites known", ""]
    L += [f"- {e}" for e in exempt]
    L += [f"- Fairness: {answer(answers, 'Q-CAD-12')}",
          "- Individual decision reasons are not produced by the kit; provide them before production if Q-CAD-09 requires them."]
    acks = [f"`{c}` : {e.get('drift_ack') or e.get('leak_ack')}" for c, e in registry.items() if e.get("drift_ack") or e.get("leak_ack")]
    L += [f"- Accepted findings: {', '.join(acks)}" if acks else "- No accepted drift or leakage findings."]
    open_q = [q["id"] for q in questions if not gate.is_answered(answers.get(q["id"]))]
    L += [f"- Open questions: {', '.join(open_q) if open_q else 'none'}."]
    L += ["", "## 7. Validation and responsibilities", "",
          f"- Independent validation: {answer(answers, 'Q-VAL-01')} (verdict in `docs/validation.md`)",
          f"- Production signed by: {answer(answers, 'Q-VAL-04')}",
          f"- Control group: {answer(answers, 'Q-DEP-03')}",
          f"- Suivi : {answer(answers, 'Q-SUI-01')} · {answer(answers, 'Q-SUI-02')}",
          "", "Complete decision log: `decisions.md`."]
    config.REPORTS_DIR.mkdir(exist_ok=True)
    (config.REPORTS_DIR / "model_card.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"fiche model : reports/model_card.md ({len(open_q)} question(s) encore open(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
