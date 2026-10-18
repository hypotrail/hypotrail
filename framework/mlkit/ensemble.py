"""Selection rule « mean_rank_all »: the confirmatory candidate is the rank average of ALL exploratory runs.

    python -m mlkit.ensemble            # explorer or person

Why: on the backtest the best runs sit inside the noise; picking « the best » is close to a draw
(winner's curse). Averaging the normalised ranks of every exploratory pipeline uses the whole
exploration instead of its luckiest point, and cannot be steered by choosing which runs to keep.

Declared in the frame (default `best`, the former behaviour):

    spec:
      selection_rule: mean_rank_all     # best | mean_rank_all

What the command does:
1. members = every distinct (pipeline, code_hash) of the exploratory runs of the CURRENT frame
   (ensemble runs excluded); a member whose file changed since its run is a refusal, never a silent
   exclusion — under this rule one idea = one new file in model/, never an overwrite;
2. writes model/ensemble_all.py: the member list with their hashes and runs in the file itself, so any
   later change of the list shows in the diff and changes the ensemble's code_hash;
3. launches it through mlkit.run (registered, counted as ONE comparison, note « ensemble de N runs »).

Rule enforcement (`problems`, used by mlkit.evaluate, mlkit.holdout and mlkit.checks): under
mean_rank_all only an ensemble run is evaluated or pre-registered, and only if it was built after the
last exploratory run of the frame, with exactly the members the registry implies.

Members are grouped by FAMILY before averaging (since 2026-10-13): mean of the ranks inside each family,
then mean across families. Otherwise 30 near-identical variants of one family weigh 30 times, and the
rule « average everything » becomes steerable by multiplying variants. The family of a member is DERIVED
from its estimator, never taken from a label:
1. the class of the FINAL estimator of build(): last step of a Pipeline, inner estimator of a wrapper
   (TimeAwareSearch, CalibratedClassifierCV, Bagging...), with a few aliases (ExtraTrees ->
   RandomForestClassifier, LogisticRegressionCV/SGD -> LogisticRegression, lightgbm/xgboost/catboost keep
   their own name);
2. a home-made combination (VotingClassifier, StackingClassifier, a class defined in the pipeline file
   itself) is the family « mixture ».
A `FAMILY = "..."` declared in the file (generated baselines declare one) is only a cross-check: accepted if
it names the derived family or the estimator's own class (« mixture » only for a real combination), refused
otherwise (code 9). Exp. 4: a declared label used to win, so 30 copies with 30 names regained the weight of
the plain mean.
The family is written next to each member in model/ensemble_all.py (visible in the diff, covered by
its code hash). Baselines (model/baselines/*.py) are exploratory runs: they are members like any other.

Ranks are taken against each member's score distribution on its TRAINING data (stored at fit), not inside
the scored batch: a single row gets the same score as in a batch, and a threshold fixed on validation keeps
its meaning. The score ranks, it is not a probability (calibration is meaningless: decision_use ranking).
"""
from __future__ import annotations

import argparse
import re
import sys

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin

from . import config, core

ENSEMBLE_PATH = "model/ensemble_all.py"
MIX = "mixture"
ALIASES = {"ExtraTreesClassifier": "RandomForestClassifier", "LogisticRegressionCV": "LogisticRegression",
           "SGDClassifier": "LogisticRegression", "AutoGluonClassifier": "AutoGluon"}
COMBINERS = {"VotingClassifier", "StackingClassifier", "RankAverage"}
# wrappers whose family is the one of the estimator they wrap (forests and boostings also have an
# `estimator` parameter, their trees: they are NOT unwrapped)
WRAPPER_CLASSES = {"TimeAwareSearch", "CalibratedClassifierCV", "BaggingClassifier", "OneVsRestClassifier",
                   "FrozenEstimator", "TunedThresholdClassifierCV", "FixedThresholdClassifier"}
WRAPPERS = ("estimator", "base_estimator")     # attribute holding the wrapped estimator


# ---------------------------------------------------------------- families
def final_estimator(model):
    """Last step of a Pipeline, unwrapped through TimeAwareSearch / CalibratedClassifierCV / Bagging..."""
    for _ in range(20):
        steps = getattr(model, "steps", None)
        if steps:
            model = steps[-1][1]
            continue
        if type(model).__name__ in COMBINERS:
            return model
        if type(model).__name__ not in WRAPPER_CLASSES:
            return model
        inner = next((getattr(model, a) for a in WRAPPERS if getattr(model, a, None) is not None
                      and hasattr(getattr(model, a), "fit")), None)
        if inner is None:
            return model
        model = inner
    return model


class FamilyRefused(SystemExit):
    """A declared FAMILY that does not match the estimator: refused, never trusted (exit code 9)."""


def derived_family(module) -> tuple[str, str]:
    """(family, class name of the final estimator), from build() only."""
    model = final_estimator(module.build())
    cls = type(model)
    if cls.__name__ in COMBINERS or cls.__module__ == module.__name__:
        return MIX, cls.__name__
    return ALIASES.get(cls.__name__, cls.__name__), cls.__name__


def family_of(module) -> str:
    """Family of a loaded pipeline, derived from its estimator. A declared FAMILY must agree
with the derived family or class; mixture is allowed only for a real combination. Otherwise raise FamilyRefused."""
    family, cls = derived_family(module)
    declared = getattr(module, "FAMILY", None)
    if declared is not None and str(declared) not in (family, cls):
        raise FamilyRefused(
            f"{getattr(module, '__file__', module.__name__)} : FAMILY = {declared!r} declared, but the final estimator is "
            f"{cls} (family {family!r}). Family is derived from the estimator class; a label may only "
            f"confirm it (« {MIX} » only for an actual mixture: Voting, Stacking, or a class defined in the file). "
            "Remove FAMILY or use the derived family.")
    return family


def family_mean(ranks: list, families) -> np.ndarray:
    """Mean of the ranks inside each family, then mean across families (plain mean without families)."""
    if not families:
        return np.mean(ranks, axis=0)
    groups: dict[str, list] = {}
    for r, f in zip(ranks, families):
        groups.setdefault(f, []).append(r)
    return np.mean([np.mean(g, axis=0) for g in groups.values()], axis=0)
RULES = ("best", "mean_rank_all")
EXIT_REFUSED = 9


# ---------------------------------------------------------------- the estimator
def verify_members(members) -> list[str]:
    """Every member file must still have the hash it had when its runs were made."""
    bad = []
    for path, h, *_ in members:
        p = config.ROOT / path
        if not p.exists():
            bad.append(f"{path} : fichier absent (expected {h})")
        elif core.code_hash(path) != h:
            bad.append(f"{path} : code changed ({h} au run, {core.code_hash(path)} maintenant)")
    return bad


class RankAverage(ClassifierMixin, BaseEstimator):
    """Fits every member on its own FEATURES; score = mean of the normalised ranks of predict_proba[:, 1],
    each rank read against that member's scores on the training data (stored at fit). Members are (path, hash) strings, not estimators, so the
    runner counts this ensemble as ONE comparison whatever the members' own grids."""

    def __init__(self, members=()):
        self.members = members

    def fit(self, X, y):
        bad = verify_members(self.members)
        if bad:
            raise SystemExit("ENSEMBLE REFUSED: member changed since its run — " + " ; ".join(bad))
        self.fitted_ = []
        for path, *_ in self.members:
            module = core.load_pipeline(path)
            model = module.build()
            model.fit(X[list(module.FEATURES)], y)
            ref = np.sort(model.predict_proba(X[list(module.FEATURES)])[:, 1])
            self.fitted_.append((list(module.FEATURES), model, ref))
        self.classes_ = np.array([0, 1])
        return self

    def predict_proba(self, X):
        ranks = []
        for f, m, ref in self.fitted_:
            p = m.predict_proba(X[f])[:, 1]
            lo, hi = np.searchsorted(ref, p, "left"), np.searchsorted(ref, p, "right")
            ranks.append((lo + hi) / 2 / len(ref))      # mid-rank within the training distribution
        # (path, hash, family): grouped by family; (path, hash) only (files written before families): plain mean
        families = [m[2] for m in self.members] if all(len(m) > 2 for m in self.members) else None
        s = family_mean(ranks, families)
        return np.column_stack([1 - s, s])

    def predict(self, X):
        return (self.predict_proba(X)[:, 1] > 0.5).astype(int)


# ---------------------------------------------------------------- the rule
def selection_rule(spec: dict) -> str:
    rule = spec.get("selection_rule", "best")
    if rule not in RULES:
        raise SystemExit(f"spec.selection_rule = {rule!r} : values possibles {', '.join(RULES)}")
    return rule


def is_ensemble(run: dict) -> bool:
    return run.get("pipeline") == ENSEMBLE_PATH


def expected_members(runs: list[dict], fhash: str, upto: int | None = None) -> dict[tuple[str, str], list[str]]:
    """(pipeline, code_hash) -> run ids, for the non-ensemble exploratory runs of the frame (before index `upto`)."""
    out: dict[tuple[str, str], list[str]] = {}
    for r in runs[:upto]:
        if r.get("status") == "exploratory" and r.get("frame_hash") == fhash and not is_ensemble(r):
            out.setdefault((r["pipeline"], r["code_hash"]), []).append(r["run_id"])
    return out


def file_members_families(text: str) -> list[str]:
    return re.findall(r'^\s*\("[^"]+",\s*"[0-9a-f]+",\s*"([^"]*)"\),', text, flags=re.M)


def file_members(text: str) -> list[tuple[str, str]]:
    return re.findall(r'^\s*\("([^"]+)",\s*"([0-9a-f]+)"(?:,\s*"[^"]*")?\),', text, flags=re.M)


def problems(spec: dict, runs: list[dict], fhash: str, run_id: str) -> list[str]:
    """Why `run_id` cannot be evaluated / pre-registered under the frame's selection rule ([] = fine)."""
    if selection_rule(spec) != "mean_rank_all":
        return []
    idx = next((i for i, r in enumerate(runs) if r.get("run_id") == run_id), None)
    if idx is None:
        return [f"{run_id} absent du registry"]
    run = runs[idx]
    if not is_ensemble(run):
        return [f"{run_id} is an isolated run ({run.get('pipeline')}): under selection_rule = mean_rank_all, only "
                f"the ensemble of all exploratory runs ({ENSEMBLE_PATH}, python -m mlkit.ensemble) is evaluated "
                "and preregistered"]
    bad = []
    later = [r["run_id"] for r in runs[idx + 1:] if r.get("status") == "exploratory"
             and r.get("frame_hash") == fhash and not is_ensemble(r)]
    if later:
        bad.append(f"ensemble {run_id} stale: exploratory runs started afterwards ({', '.join(later)}) ; "
                   "rebuild it: python -m mlkit.ensemble")
    path = config.ROOT / ENSEMBLE_PATH
    if not path.exists() or core.code_hash(ENSEMBLE_PATH) != run.get("code_hash"):
        bad.append(f"{ENSEMBLE_PATH} changed or missing since the run {run_id}")
    else:
        have = set(file_members(path.read_text(encoding="utf-8")))
        want = set(expected_members(runs, fhash, idx))
        if have != want:
            bad.append(f"members of {run_id} ≠ exploratory runs under this frame: missing "
                       f"{sorted(p for p, _ in want - have) or '-'}, en too {sorted(p for p, _ in have - want) or '-'}")
    return bad


def require(run_id: str, what: str) -> None:
    """Hook for mlkit.evaluate / mlkit.holdout: refuse unless the rule allows this run."""
    spec = config.load_frame()["spec"]
    bad = problems(spec, config.read_jsonl(config.REGISTRY_FILE), config.frame_hash(), run_id)
    if bad:
        raise SystemExit(f"{what.upper()} REFUSED (selection_rule mean_rank_all):\n  " + "\n  ".join(bad))


def check(frame: dict, runs: list[dict], ledger: list[dict], fhash: str, report) -> None:
    """mlkit.checks: pending pre-registrations and holdout readings follow the declared selection rule."""
    name = "E1 selection rule"
    try:
        rule = selection_rule(frame["spec"])
    except SystemExit as exc:
        report(name, False, str(exc))
        return
    if rule == "best":
        report(name, True, "best (default): choose the preregistered candidate among runs")
        return
    bad, n = [], 0
    read = {e.get("prereg") for e in ledger}
    for e in ledger:
        if e.get("frame_hash") == fhash and not e.get("legacy_adoption") and e.get("pipeline") != ENSEMBLE_PATH:
            bad.append(f"lecture {e.get('prereg')} : isolated run {e.get('pipeline')} lu under mean_rank_all")
    for p in sorted(config.PREREG_DIR.glob("*.yaml")) if config.PREREG_DIR.exists() else []:
        if p.name == "TEMPLATE.yaml":
            continue
        pr = config.load_yaml(p) or {}
        if pr.get("id") in read or "run" not in pr:
            continue
        n += 1
        bad += [f"{p.name} : {x}" for x in problems(frame["spec"], runs, fhash, str(pr["run"]))]
    report(name, not bad, "; ".join(bad) or
           f"mean_rank_all : {n} pending preregistrations, each on the current ensemble of all runs")


# ---------------------------------------------------------------- the command
def render(members: dict[tuple[str, str], list[str]], fhash: str) -> str:
    feats: list[str] = []
    fams: dict[tuple[str, str], str] = {}
    for key in members:
        module = core.load_pipeline(key[0])
        feats += [f for f in module.FEATURES if f not in feats]
        fams[key] = family_of(module)
    lines = [f'"""Rank-average ensemble of ALL exploratory runs under frame {fhash}',
             "(selection_rule: mean_rank_all). Generated by python -m mlkit.ensemble; do not edit manually.",
             "",
             "Changing MEMBERS changes this file hash: the ensemble is then no longer",
             "the one implied by the registry; mlkit.checks / mlkit.holdout reject it.",
             '"""',
             "from mlkit.ensemble import RankAverage, verify_members",
             "",
             f"# {len(members)} members, {len(set(fams.values()))} familles : (pipeline, code_hash, family) — runs du registry",
             "# score = average ranks within each family, then average across families (mlkit.ensemble)",
             "MEMBERS = ["]
    lines += [f'    ("{p}", "{h}", "{fams[(p, h)]}"),  # {", ".join(ids)}' for (p, h), ids in members.items()]
    lines += ["]",
              "",
              "FEATURES = [",
              *[f'    "{f}",' for f in feats],
              "]",
              "",
              "",
              "def build():",
              "    bad = verify_members(MEMBERS)",
              "    if bad:",
              '        raise SystemExit("ENSEMBLE REFUSED: member changed since its run — " + " ; ".join(bad))',
              "    return RankAverage(members=tuple(MEMBERS))",
              ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m mlkit.ensemble")
    ap.parse_args(argv)
    spec, fhash = config.load_frame()["spec"], config.frame_hash()
    rule = selection_rule(spec)
    runs = config.read_jsonl(config.REGISTRY_FILE)
    members = expected_members(runs, fhash)
    if len(members) < 2:
        print(f"ENSEMBLE REFUSED : {len(members)} pipeline(s) exploratory(s) under ce frame, il en faut au less 2.",
              file=sys.stderr)
        return EXIT_REFUSED
    bad = [f"{x} — run(s) {', '.join(members[k])}" for k in members for x in verify_members([k])]
    if bad:
        print("ENSEMBLE REFUSED: exploratory run code changed after measurement; the ensemble must "
              "contain all runs exactly as measured.\n  " + "\n  ".join(bad) +
              "\nRestore the run version from Git or ask a person to decide "
              "(changing the frame restarts exploration from an empty state).", file=sys.stderr)
        return EXIT_REFUSED
    last = [i for i, r in enumerate(runs) if r.get("status") == "exploratory" and r.get("frame_hash") == fhash
            and is_ensemble(r)]
    if last and not problems({**spec, "selection_rule": "mean_rank_all"}, runs, fhash, runs[last[-1]]["run_id"]):
        print(f"ensemble already current : {runs[last[-1]]['run_id']} (no exploratory run since); nothing to redo")
        return 0
    refused = []
    for key in members:
        try:
            family_of(core.load_pipeline(key[0]))
        except FamilyRefused as exc:
            refused.append(str(exc))
    if refused:
        print(f"ENSEMBLE REFUSED : {len(refused)} members declare a FAMILY incompatible with their estimator.\n  "
              + "\n  ".join(refused), file=sys.stderr)
        return EXIT_REFUSED
    path = config.ROOT / ENSEMBLE_PATH
    path.parent.mkdir(exist_ok=True)
    path.write_text(render(members, fhash), encoding="utf-8")
    fams = set(file_members_families(path.read_text(encoding="utf-8")))
    print(f"{ENSEMBLE_PATH} : {len(members)} members, {len(fams)} familles ({', '.join(sorted(fams))})" + ("" if rule == "mean_rank_all" else
          " (note: with selection_rule = best, the ensemble is just another candidate)"))
    from . import run
    return run.main(["--pipeline", ENSEMBLE_PATH, "--note", f"ensemble de {len(members)} runs"])


if __name__ == "__main__":
    sys.exit(main())
