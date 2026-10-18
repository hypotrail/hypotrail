"""Phase gates: which questions of questions.yaml are answered, what is blocked.

    python -m mlkit.gate                 # status of every phase, next questions to ask
    python -m mlkit.gate --phase cible   # exit 1 if the phase has unanswered blocking questions
    python -m mlkit.gate --for run       # exit 1 if the command `run` is not yet allowed

An answer counts only if written by a person (by: HUMAN) in answers.yaml.
"""
from __future__ import annotations

import argparse
import os
import sys

from . import config

PHASES = ["cadrage", "donnees", "cible", "modelisation", "evaluation", "validation", "deploiement", "suivi"]

# Command -> phases that must be complete before it may run.
PHASE_GATES = {
    "run":     ["cadrage", "donnees", "cible"],
    "bivariate": ["cadrage", "donnees", "cible"],
    "holdout": ["cadrage", "donnees", "cible", "modelisation", "evaluation"],
    "package": ["cadrage", "donnees", "cible", "modelisation", "evaluation", "validation"],
    "score":   PHASES[:7],
    "monitor": PHASES,
}

QUESTIONS_FILE = config.ROOT / "questions.yaml"
ANSWERS_FILE = config.ROOT / "answers.yaml"
PROPOSED_FILE = config.ROOT / "answers.proposed.yaml"


def accept_examples() -> bool:
    return False  # Examples never constitute human answers.


def load():
    questions = config.load_yaml(QUESTIONS_FILE)["questions"]
    answers = (config.load_yaml(ANSWERS_FILE) or {}) if ANSWERS_FILE.exists() else {}
    proposed = (config.load_yaml(PROPOSED_FILE) or {}) if PROPOSED_FILE.exists() else {}
    return questions, answers, proposed


def is_answered(entry) -> bool:
    if not isinstance(entry, dict) or not str(entry.get("answer", "")).strip():
        return False
    by = entry.get("by")
    return by == "HUMAN" or (by == "EXAMPLE" and accept_examples())


def phase_status(phase: str, questions, answers, proposed) -> dict:
    qs = [q for q in questions if q["phase"] == phase]
    missing = [q for q in qs if q.get("blocking") and not is_answered(answers.get(q["id"]))]
    open_optional = [q for q in qs if not q.get("blocking") and not is_answered(answers.get(q["id"]))]
    examples = [q["id"] for q in qs if (answers.get(q["id"]) or {}).get("by") == "EXAMPLE"]
    return {"phase": phase, "total": len(qs), "blocking": sum(1 for q in qs if q.get("blocking")),
            "missing": missing, "optional_open": open_optional, "examples": examples,
            "proposed": [q["id"] for q in qs if q["id"] in proposed and not is_answered(answers.get(q["id"]))],
            "complete": not missing}


def missing_for(command: str) -> list[dict]:
    questions, answers, proposed = load()
    out = []
    for phase in PHASE_GATES[command]:
        out += phase_status(phase, questions, answers, proposed)["missing"]
    return out


def require(command: str) -> bool:
    """Print what blocks `command` and return False if anything does."""
    missing = missing_for(command)
    marker = config.ROOT / ".pilot" / "exploratory-only.json"
    if missing and command in {"run", "bivariate"} and marker.is_file():
        print("EXPLORATORY ONLY: unconfirmed assumptions; no certification possible", file=sys.stderr)
        return True
    if missing:
        ids = ", ".join(q["id"] for q in missing[:8]) + (" …" if len(missing) > 8 else "")
        print(f"PHASE GATE ({command}) : {len(missing)} question(s) blocking(s) without a human answer : {ids}\n"
              "Voir : python -m mlkit.gate", file=sys.stderr)
        return False
    return True


def consistency_problems() -> list[str]:
    questions, answers, _ = load()
    ids = {q["id"] for q in questions}
    statements = set(config.load_frame().get("statements", {}))
    problems = [f"{k} : question unknown" for k in answers if k not in ids]
    for k, a in answers.items():
        if isinstance(a, dict):
            if a.get("by") not in ("HUMAN", "EXAMPLE"):
                problems.append(f"{k}: by must be HUMAN or EXAMPLE")
            problems += [f"{k}: reference {r} missing du frame" for r in a.get("refs", []) if r not in statements]
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m mlkit.gate")
    ap.add_argument("--phase", choices=PHASES)
    ap.add_argument("--for", dest="command", choices=list(PHASE_GATES))
    args = ap.parse_args(argv)
    questions, answers, proposed = load()

    if args.command:
        return 0 if require(args.command) else 1
    if args.phase:
        st = phase_status(args.phase, questions, answers, proposed)
        for q in st["missing"]:
            print(f"{q['id']}  {q['question']}")
        return 0 if st["complete"] else 1

    phases = config.load_yaml(QUESTIONS_FILE)["phases"]
    print(f"{'phase':<14}{'state':<10}{'blocking':<12}{'missing':<12}{'examples':<10}proposed")
    first_open = None
    for p in PHASES:
        st = phase_status(p, questions, answers, proposed)
        state = "complete" if st["complete"] else "open"
        if not st["complete"] and first_open is None:
            first_open = (p, st)
        print(f"{p:<14}{state:<10}{st['blocking']:<12}{len(st['missing']):<12}{len(st['examples']):<10}{len(st['proposed'])}")
    allowed = [c for c in PHASE_GATES if not missing_for(c)]
    print(f"\nallowed commands: {', '.join(allowed) or 'none'}")
    if accept_examples():
        print("WARNING: OSML_ACCEPT_EXAMPLES=1 treats example answers as actual answers.")
    for p in consistency_problems():
        print(f"inconsistency: {p}")
    if first_open:
        p, st = first_open
        print(f"\nProchaine phase : {p} — {phases[p]}")
        for q in st["missing"]:
            print(f"\n{q['id']}  {q['question']}\n  pourquoi : {q['why']}\n  consequence: {q['consequence']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
