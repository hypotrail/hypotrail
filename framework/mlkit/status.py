"""Read-only summary of the experiment registry, for any role allowed to see results.

    python -m mlkit.status [--last 15]
"""
from __future__ import annotations

import argparse
import sys

from . import config
from .run import open_stops


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m mlkit.status")
    ap.add_argument("--last", type=int, default=15)
    args = ap.parse_args(argv)
    spec, fhash = config.load_frame()["spec"], config.frame_hash()
    runs = [r for r in config.read_jsonl(config.REGISTRY_FILE) if r["frame_hash"] == fhash]
    ledger = [e for e in config.read_jsonl(config.LEDGER_FILE) if e["frame_hash"] == fhash]
    p = spec["metric_primary"]
    n_exp = sum(1 for r in runs if r["status"] == "exploratory")
    comparisons = sum(r.get("n_candidates", 1) for r in runs if r["status"] == "exploratory")
    budget = spec.get("exploration_budget")
    print(f"frame {fhash} · {n_exp} runs exploratory · {comparisons}{'/' + str(budget) if budget else ''} comparisons"
          f" · current holdout {config.n_readings(config.readings_of_current_holdout(config.read_jsonl(config.LEDGER_FILE)))}/{spec['holdout']['budget']} readings")
    stops = open_stops()
    if stops:
        print("STOPS OPEN : " + ", ".join(stops))
    for r in runs[-args.last:]:
        val = r.get("summary", {}).get(p, {}).get("mean")
        g = r.get("gain", {}).get("mean")
        flag = "conclusive" if r.get("conclusive") else ""
        if r.get("triggers"):
            flag = "STOP"
        print(f"  {r['run_id']:<9} {r['status']:<11} {p}={'' if val is None else f'{val:.4f}':<7} "
              f"gain={'' if g is None else f'{g:+.4f}':<8} {flag}  {r['pipeline']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
