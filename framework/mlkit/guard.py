"""Pre-tool-use hook shared by Claude Code and GitHub Copilot.

Reads the hook payload (JSON) on stdin, whatever its format (Claude:
tool_name/tool_input, Copilot: toolName/toolArgs), and exits 2 to deny.
Both agents treat exit code 2 as "block this tool call".

This is a SPEED BUMP, not a wall: it matches path names in the payload, so a
script that builds a path dynamically gets through. Real isolation comes from
files that are absent from the agent's machine (holdout in CI) — see README.
Every denial is logged to .osml/guard.log; the count is a Friday-ritual metric.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ.get("OSML_ROOT", Path.cwd()))

# Never readable from an agent session, whatever the role.
PRIVATE_MARKERS = [".hypotrail-ml", "osml_private", "holdout_data", "stops_private",
                   "osml_holdout_dir", "osml_stops_file"]

# Readable, but only a person (or mlkit itself) writes them.
HUMAN_WRITE_ONLY = ["frame.yaml", "features.yaml", "experiments/registry.jsonl",
                    "holdout/ledger.jsonl", ".decision.md", ".claude/settings.json",
                    ".github/hooks/", "mlkit/guard.py", "decisions.md", "data/dev/manifest.json",
                    "answers.yaml", "questions.yaml", "docs/validation.md", "models/",
                    "mlkit/", "experiments/selection_ledger", "experiments/decision_rule"]

ROLE_FORBIDDEN = {
    "feature-builder": ["labels.csv", "data/dev/labels", "experiments/registry", "reports/", "stops/",
                        "mlkit.run", "mlkit.status"],
    "leak-reviewer": ["experiments/registry", "reports/", "stops/", "-stop-writer.json", "labels.csv",
                      "mlkit.run", "mlkit.status", "holdout/ledger"],
    "stop-writer": ["-leak-reviewer.json"],
    "data-analyst": ["labels.csv", "data/dev/labels", "experiments/registry", "stops/", "holdout/ledger",
                     "mlkit.run", "mlkit.status", "reports/c-"],
    "explorer": ["mlkit.package", "mlkit.holdout", "mlkit.bivariate"],
    "validator": ["mlkit.run", "mlkit.package", "mlkit.holdout", "mlkit.score"],
}
# mlkit.baselines starts runs: explorer or human only.
for _role in ("feature-builder", "leak-reviewer", "stop-writer", "data-analyst", "validator"):
    ROLE_FORBIDDEN[_role].append("mlkit.baselines")

# mlkit.residuals: explorer and data-analyst only; its ledger is written by mlkit alone.
for _role in ("feature-builder", "leak-reviewer", "stop-writer", "validator"):
    ROLE_FORBIDDEN[_role].append("mlkit.residuals")
HUMAN_WRITE_ONLY.append("experiments/residuals_ledger")
for _role in ("feature-builder", "leak-reviewer", "stop-writer", "data-analyst", "validator"):
    ROLE_FORBIDDEN[_role].append("mlkit.ensemble")        # explorer and person only

# mlkit.drift: explorer and data-analyst only, never on the holdout (a person runs that one);
# the data-analyst sees no model score (--run / --prereg fit on dev labels).
for _role in ("feature-builder", "leak-reviewer", "stop-writer", "validator"):
    ROLE_FORBIDDEN[_role].append("mlkit.drift")
DRIFT_HOLDOUT = re.compile(r"mlkit[./]drift.*--target[\s=\\\"']+holdout")
DRIFT_MODEL = re.compile(r"mlkit[./]drift.*--(run|prereg)\b")

# Tool names differ between agents and versions. Check .osml/guard.log after a
# first session and add any read-only tool that was wrongly blocked.
READ_ONLY_TOOLS = {"read", "grep", "glob", "ls", "view", "read_file", "readfile", "list_dir",
                   "listdirectory", "file_search", "findfiles", "grep_search", "textsearch",
                   "semantic_search", "search", "codebase", "notebookread"}


def deny(reason: str, tool: str) -> None:
    log = ROOT / ".osml" / "guard.log"
    try:
        log.parent.mkdir(exist_ok=True)
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"time": dt.datetime.now().isoformat(timespec="seconds"),
                                 "role": os.environ.get("OSML_ROLE", "explorer"),
                                 "tool": tool, "reason": reason}, ensure_ascii=False) + "\n")
    except OSError:
        pass
    print(f"[hypotrail-ml] Refused : {reason}. If needed, ask the human through escalation.", file=sys.stderr)
    sys.exit(2)


def main() -> None:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {}
    tool = str(payload.get("tool_name") or payload.get("toolName") or "").lower()
    args = payload.get("tool_input", payload.get("toolArgs", raw))
    blob = (json.dumps(args, ensure_ascii=False) if not isinstance(args, str) else args).lower()

    secret = os.environ.get("OSML_HOLDOUT_DIR")
    markers = PRIVATE_MARKERS + ([secret.lower()] if secret else [])
    for m in markers:
        if m and m in blob:
            deny(f"access to a private area ({m})", tool)

    role = os.environ.get("OSML_ROLE", "explorer")
    if DRIFT_HOLDOUT.search(blob):
        deny("mlkit.drift --target holdout is human-only", tool)
    if role == "data-analyst" and DRIFT_MODEL.search(blob):
        deny("data-analyst runs mlkit.drift without --run or --prereg (use --pipeline only)", tool)
    for m in ROLE_FORBIDDEN.get(role, []):
        if m in blob:
            deny(f"role {role} has no access to « {m} »", tool)

    if tool not in READ_ONLY_TOOLS:
        if re.search(r"reports/[^\s\"']*\.html", blob):
            deny("HTML in reports/ is generated by python -m mlkit.render, never written directly by an agent", tool)
        for m in HUMAN_WRITE_ONLY:
            if m in blob:
                deny(f"« {m} » can only be changed by a human; propose the change in your response", tool)
    sys.exit(0)


if __name__ == "__main__":
    main()
