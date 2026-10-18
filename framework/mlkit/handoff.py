"""Filtered handoff between roles. WHITELIST: only listed fields leave.

    python -m mlkit.handoff --run r-0024 --role leak-reviewer   # code, no results
    python -m mlkit.handoff --run r-0024 --role stop-writer     # results, no notes

The explorer's free notes, file names and messages never reach another role.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

from . import config


def git_diff(path: str) -> str:
    try:
        return subprocess.run(["git", "diff", "--no-color", "HEAD", "--", path], cwd=config.ROOT,
                              capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def build(run: dict, role: str) -> dict:
    registry = config.load_features()
    common = {"run_id": run["run_id"], "frame_hash": run["frame_hash"], "pipeline": run["pipeline"],
              "features": [{"name": f, **registry.get(f, {"available": "UNDECLARED"})} for f in run["features"]]}
    if role == "leak-reviewer":
        code = (config.ROOT / run["pipeline"]).read_text(encoding="utf-8")
        return {**common, "pipeline_code": code, "pipeline_diff": git_diff(run["pipeline"]),
                "question": "Could information unavailable at prediction time (frame §F3) "
                            "reach this pipeline? Results are intentionally hidden from you."}
    if role == "stop-writer":
        stop_file = config.STOPS_DIR / f"STOP-{run['run_id']}.json"
        stop = json.loads(stop_file.read_text(encoding="utf-8")) if stop_file.exists() else None
        return {**common, "stop": stop, "summary": run.get("summary"), "gain": run.get("gain"),
                "per_window": run.get("per_window"), "reference": run.get("reference")}
    raise SystemExit(f"unknown role: {role}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m mlkit.handoff")
    ap.add_argument("--run", required=True)
    ap.add_argument("--role", required=True, choices=["leak-reviewer", "stop-writer"])
    args = ap.parse_args(argv)
    runs = {r["run_id"]: r for r in config.read_jsonl(config.REGISTRY_FILE)}
    if args.run not in runs:
        raise SystemExit(f"{args.run} absent du registry")
    out = config.HANDOFF_DIR / f"{args.run}-{args.role}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(build(runs[args.run], args.role), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"handoff written: {out.relative_to(config.ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
