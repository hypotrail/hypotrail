"""python -m mlkit.baselines: generated from the registry, run through mlkit.run, counted, idempotent.

    python -m pytest -q tests/test_baselines.py
"""
from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

KIT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).resolve().parent / "fixtures/legacy-project"
ELIGIBLE_SYNTHETIC = {"loan_amnt", "int_rate", "installment", "emp_length", "annual_inc", "dti", "credit_history_months",
                      "fico_range_low", "fico_range_high", "inq_last_6mths", "open_acc", "revol_util", "total_acc",
                      "grade", "sub_grade", "home_ownership", "verification_status", "purpose", "initial_list_status"}


def sh(cwd, *args, env=None):
    e = {k: v for k, v in os.environ.items() if not k.startswith("OSML_")}
    # one OpenMP thread: on a loaded machine HistGradientBoosting oversubscribes (5 s -> 80 s measured)
    e.update({"OMP_NUM_THREADS": "1", "OSML_ROOT": str(cwd), "OSML_ACCEPT_EXAMPLES": "1",
              "OSML_STOPS_FILE": str(cwd.parent / "stops-baselines.yaml"), **(env or {})})
    e = {k: v for k, v in e.items() if v is not None}
    return subprocess.run([sys.executable, *args], cwd=cwd, env=e, capture_output=True, text=True)


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    root = tmp_path_factory.mktemp("projbl")
    private = tmp_path_factory.mktemp("privatebl") / ".hypotrail-ml"
    for item in ("mlkit", "model", "scripts", "frame.yaml", "features.yaml", "decisions.md", "questions.yaml", "answers.yaml"):
        src = (KIT if item == "mlkit" else FIXTURE) / item
        (shutil.copytree if src.is_dir() else shutil.copy2)(src, root / item)
    shutil.rmtree(root / "model" / "baselines", ignore_errors=True)
    # autogluon (minutes per run) is tested on its own, with a short time limit, at the end of this file
    fr = root / "frame.yaml"
    fr.write_text(fr.read_text().replace("baselines: [splines_logit, monotone_hgb, ebm, autogluon]",
                                         "baselines: [splines_logit, monotone_hgb, ebm]"))
    for d in ("experiments", "holdout", "stops", "preregistrations", "reports"):
        (root / d).mkdir(exist_ok=True)
    # a strong baseline may beat the score in place by more than the default "too good" threshold:
    # that stop is tested elsewhere, here it would only hide what is tested
    (root.parent / "stops-baselines.yaml").write_text("too_good_gain: 1.0\nstagnation_runs: 50\nnull_auc_band: [0.45, 0.55]\n")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    r = sh(root, "scripts/make_synthetic.py", "--private", str(private), "--n", "40000")
    assert r.returncode == 0, r.stderr
    return root


def registry(root) -> list[dict]:
    f = root / "experiments" / "registry.jsonl"
    return [json.loads(line) for line in f.read_text().splitlines()] if f.exists() else []


def ebm_usable(root) -> bool:
    r = sh(root, "-c", "from mlkit.baselines import interpret_problem as p; print(p() or 'OK')")
    return r.stdout.strip().endswith("OK")


def literals(path: Path) -> dict:
    """Module-level literal assignments of a generated file, read without importing it."""
    out = {}
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            try:
                out[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                pass
    return out


def with_frame(root, edit):
    """Context: frame.yaml temporarily edited (a new frame hash), restored afterwards."""
    class _Ctx:
        def __enter__(self):
            self.backup = (root / "frame.yaml").read_text()
            (root / "frame.yaml").write_text(edit(self.backup))
        def __exit__(self, *exc):
            (root / "frame.yaml").write_text(self.backup)
    return _Ctx()


def test_unknown_baseline_is_refused(project):
    root = project
    before = len(registry(root))
    with with_frame(root, lambda t: t.replace("baselines: [splines_logit, monotone_hgb, ebm]",
                                              "baselines: [splines_logit, boosting_magique]")):
        r = sh(root, "-m", "mlkit.baselines")
    assert r.returncode == 9 and "boosting_magique" in r.stderr, r.stdout + r.stderr
    assert len(registry(root)) == before and not (root / "model" / "baselines").exists()


def test_generated_files_follow_the_registry(project):
    root = project
    r = sh(root, "-m", "mlkit.baselines", "--dry-run")
    assert r.returncode == 0, r.stderr
    expected = ["splines_logit", "monotone_hgb", "ebm"]
    if not ebm_usable(root):
        assert "ebm SKIPPED" in r.stderr and "interpret" in r.stderr     # clear message, the others continue
        expected.remove("ebm")
    assert sorted(p.stem for p in (root / "model" / "baselines").glob("*.py")) == sorted(expected)
    assert registry(root) == []                                          # --dry-run spends nothing
    reg = yaml.safe_load((root / "features.yaml").read_text())["features"]
    for name in expected:
        lit = literals(root / "model" / "baselines" / f"{name}.py")
        num, cat = lit["NUMERIC"], lit["CATEGORICAL"]
        assert set(num) | set(cat) == ELIGIBLE_SYNTHETIC and not set(num) & set(cat)
        for c in num + cat:
            assert reg[c]["available"] == "origination" and not reg[c].get("excluded_by")
        assert all(reg[c]["contract"]["type"] == "numeric" for c in num)
        assert all(reg[c]["contract"]["type"] == "categorical" for c in cat)
        assert lit["FAMILY"] == {"splines_logit": "LogisticRegression", "monotone_hgb": "HistGradientBoostingClassifier",
                                 "ebm": "ExplainableBoostingClassifier"}[name]
    mono = literals(root / "model" / "baselines" / "monotone_hgb.py")["MONOTONIC"]
    assert mono == {c: (1 if reg[c]["expected_direction"] == "+" else -1)
                    for c in ELIGIBLE_SYNTHETIC if reg[c].get("expected_direction") in ("+", "-")}
    assert mono["fico_range_low"] == -1 and mono["int_rate"] == 1
    # the EBM template is valid code with the same columns, whether interpret works here or not
    src = sh(root, "-c", "from mlkit.baselines import render; print(render('ebm', ['a', 'b'], ['c'], {}))").stdout
    compile(src, "ebm.py", "exec")
    assert "NUMERIC = ['a', 'b']" in src and "interactions=10" in src


def test_baselines_are_runs_counted_once_and_idempotent(project):
    root = project
    r = sh(root, "-m", "mlkit.baselines")
    assert r.returncode == 0, r.stdout + r.stderr
    names = sorted(p.stem for p in (root / "model" / "baselines").glob("*.py"))
    regs = registry(root)
    assert regs[0]["status"] == "reference"                              # launched first when missing
    runs = [x for x in regs if x["status"] == "exploratory"]
    assert sorted(x["note"] for x in runs) == sorted(f"baseline automatic {n}" for n in names)
    assert all(x["n_candidates"] == 1 and x["planned_candidates"] == 1 for x in runs)
    assert [x["comparisons_total"] for x in runs] == list(range(1, len(names) + 1))
    assert all(x["pipeline"].startswith("model/baselines/") and "gain" in x for x in runs)
    # references, not a starting point: no « best baseline » is named (anchoring observed, 2026-10-13)
    assert "Best baseline" not in r.stdout and "starting point for exploration" not in r.stdout
    assert "not a starting point" in r.stdout

    again = sh(root, "-m", "mlkit.baselines")
    assert again.returncode == 0, again.stderr
    assert len(registry(root)) == len(regs) and again.stdout.count("not rerun") == len(names)

    # a changed registry changes the generated code: that baseline is new code, so it runs again
    feats = root / "features.yaml"
    backup = feats.read_text()
    feats.write_text(backup.replace('  int_rate:    {expected_direction: "+", ', "  int_rate:    {"))
    try:
        r3 = sh(root, "-m", "mlkit.baselines")
    finally:
        feats.write_text(backup)
    assert r3.returncode == 0, r3.stderr
    new = registry(root)[len(regs):]
    assert [x["note"] for x in new] == ["baseline automatic monotone_hgb"]
    assert new[0]["comparisons_total"] == len(names) + 1


def test_budget_is_checked_before_each_baseline(project):
    root = project
    with with_frame(root, lambda t: t.replace("exploration_budget: 100", "exploration_budget: 1")):
        r = sh(root, "-m", "mlkit.baselines")             # new frame: reference, then the first baseline uses the budget
        first = registry(root)[-1]
        assert r.returncode == 3 and "budget d'exploration reached" in r.stderr, r.stdout + r.stderr
        assert first["note"] == "baseline automatic splines_logit" and first["comparisons_total"] == 1
        stop = root / "stops" / f"STOP-{first['run_id']}.json"
        (root / "stops" / f"{stop.stem}.decision.md").write_text("test: deliberately reduced budget")
        r2 = sh(root, "-m", "mlkit.baselines")            # splines_logit not run again; the next one is refused before fitting
        last = registry(root)[-1]
    assert r2.returncode == 8 and "budget" in r2.stderr, r2.stdout + r2.stderr
    assert "splines_logit: already in registry" in r2.stdout
    assert last["status"] == "rejected" and last["pipeline"] == "model/baselines/monotone_hgb.py"
    assert "n_candidates" not in last                       # nothing fitted, nothing spent


def test_roles(project):
    root = project
    def guard(command, role):
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
        e = {k: v for k, v in os.environ.items() if not k.startswith("OSML_")}
        e.update(OSML_ROOT=str(root), OSML_ROLE=role)
        return subprocess.run([sys.executable, "mlkit/guard.py"], cwd=root, env=e, input=payload,
                              capture_output=True, text=True).returncode
    assert guard("python -m mlkit.baselines", "explorer") == 0
    for role in ("feature-builder", "leak-reviewer", "stop-writer", "data-analyst", "validator"):
        assert guard("python -m mlkit.baselines", role) == 2, role
    r = sh(root, "-m", "mlkit.baselines", env={"OSML_ROLE": "validator"})
    assert r.returncode == 10 and "explorateur" in r.stderr


# ---------------------------------------------------------------- autogluon (2026-10-13)
def autogluon_usable(root) -> bool:
    r = sh(root, "-c", "from mlkit.automl import autogluon_problem as p; print(p() or 'OK')")
    return r.stdout.strip().endswith("OK")


def test_autogluon_file_is_generated_from_the_frame(project):
    root = project
    src = sh(root, "-c", "from mlkit.baselines import render; "
                         "print(render('autogluon', ['a', 'b'], ['c'], {}, {'baselines_autogluon': {'time_limit': 33}}))").stdout
    compile(src, "autogluon.py", "exec")
    (root.parent / "autogluon_rendered.py").write_text(src)
    lit = literals(root.parent / "autogluon_rendered.py")
    assert lit["FAMILY"] == "AutoGluon" and lit["NUMERIC"] == ["a", "b"] and lit["CATEGORICAL"] == ["c"]
    assert lit["TIME_LIMIT"] == 33 and lit["PRESETS"] == "medium_quality"          # frame value, default presets
    assert len(lit["WRAPPER_SHA256"]) >= 12 and "AUTOGLUON_VERSION" in lit
    with with_frame(root, lambda t: t.replace("baselines: [splines_logit, monotone_hgb, ebm]", "baselines: [autogluon]")):
        r = sh(root, "-m", "mlkit.baselines", "--dry-run")
    assert r.returncode == 0, r.stderr
    if autogluon_usable(root):
        assert (root / "model" / "baselines" / "autogluon.py").exists()
    else:                                                   # clear message, nothing generated, nothing spent
        assert "autogluon SKIPPED" in r.stderr and "pip install" in r.stderr, r.stderr


def test_autogluon_wrapper_pickles_and_cleans_its_directory():
    pytest.importorskip("autogluon.tabular")
    import gc
    import pickle
    import numpy as np
    import pandas as pd
    from mlkit.automl import AutoGluonClassifier
    from mlkit import core
    rng = np.random.default_rng(0)
    X = pd.DataFrame({"a": rng.normal(size=1500), "c": rng.choice(["x", "y"], 1500)})
    y = (X["a"] + (X["c"] == "x") + rng.normal(size=1500) > 0.5).astype(int).to_numpy()
    m = AutoGluonClassifier(time_limit=10)
    assert core.planned_candidates(m) == 1
    m.fit(X[:1000], y[:1000])
    p = m.predict_proba(X[1000:])[:, 1]
    assert p.shape == (500,) and 0 <= p.min() and p.max() <= 1
    copy = pickle.loads(pickle.dumps(m))                     # mlkit.package: no dependency on a temporary path
    path = Path(m.predictor_.path)
    del m
    gc.collect()
    assert not path.exists()
    assert np.allclose(copy.predict_proba(X[1000:])[:, 1], p)


def test_autogluon_baseline_runs_counted_once(project):
    pytest.importorskip("autogluon.tabular")
    root = project
    edit = lambda t: (t.replace("baselines: [splines_logit, monotone_hgb, ebm]", "baselines: [autogluon]")
                       .replace("baselines_autogluon: {time_limit: 120, presets: medium_quality}",
                                "baselines_autogluon: {time_limit: 15, presets: medium_quality}"))
    with with_frame(root, edit):
        r = sh(root, "-m", "mlkit.baselines")
        regs = registry(root)
    assert r.returncode == 0, r.stdout + r.stderr
    last = regs[-1]
    assert last["status"] == "exploratory" and last["note"] == "baseline automatic autogluon"
    assert last["pipeline"] == "model/baselines/autogluon.py" and last["n_candidates"] == 1
    assert set(last["features"]) == ELIGIBLE_SYNTHETIC                    # I5 passed, no D6 suspect here
    assert literals(root / "model" / "baselines" / "autogluon.py")["TIME_LIMIT"] == 15
