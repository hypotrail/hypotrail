"""mlkit.residuals on synthetic data whose remaining signal is known (about one minute).

    python -m pytest -q tests/test_residuals.py

Two data sets, generated here (not the project's twins), same columns and months:
- "planted": risk = linear(fico, dti) + an INTERACTION between open_acc and revol_util (both unused
  by the pipeline) + a THRESHOLD on credit_history_months (unused). The pipeline is a logistic
  regression on fico and dti only: everything planted is left in its residuals.
- "clean": risk = linear(fico, dti) only. The same pipeline is well specified: nothing remains.
Criterion on "clean": at most one candidate above the family-wise chance floor (expected rate
of a false alarm: about 5 % for columns + 5 % for pairs), and no candidate twice above it.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

KIT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).resolve().parent / "fixtures/legacy-project"
GRADES = [f"{g}{i}" for g in "ABCDEFG" for i in range(1, 6)]

PIPELINE = '''"""Logistic regression on two columns: well specified for the clean data set only."""
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

FEATURES = ["fico_range_low", "dti"]


def build():
    return make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
'''


def generate(n: int, planted: bool, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    months = pd.period_range("2007-06", "2015-06", freq="M")
    m = rng.integers(0, len(months), n)
    fico = rng.normal(700, 30, n).clip(620, 845)
    dti = rng.gamma(4, 4.5, n).clip(0, 45)
    open_acc = rng.poisson(11, n)
    revol = rng.uniform(0, 100, n).round(1)
    hist = rng.integers(36, 400, n)
    risk = -1.9 - 0.03 * (fico - 700) + 0.05 * (dti - 18)
    if planted:
        risk = risk + 1.3 * ((open_acc >= 14) & (revol >= 60)) + 1.0 * (hist < 80)
    default = (rng.random(n) < 1 / (1 + np.exp(-risk))).astype(int)
    grade = np.clip(((-0.03 * (fico - 700) + 0.05 * (dti - 18) + rng.normal(0, 0.4, n) + 2.5) / 0.15).astype(int), 0, 34)
    return pd.DataFrame({
        "id": rng.permutation(n) + 1_000_000, "issue_d": months[m].astype(str),
        "loan_amnt": rng.integers(10, 351, n) * 100, "sub_grade": [GRADES[i] for i in grade],
        "emp_length": rng.integers(0, 11, n),
        "home_ownership": rng.choice(["RENT", "MORTGAGE", "OWN"], n, p=[0.4, 0.5, 0.1]),
        "purpose": rng.choice(["debt_consolidation", "credit_card", "home_improvement", "other"], n, p=[0.6, 0.2, 0.1, 0.1]),
        "dti": dti.round(2), "fico_range_low": (fico // 5 * 5).astype(int), "revol_util": revol,
        "open_acc": open_acc, "total_acc": rng.poisson(24, n), "credit_history_months": hist,
        "default": default,
    }).sort_values("issue_d").reset_index(drop=True)


def sh(cwd, *args, env=None, inp=None):
    e = {k: v for k, v in os.environ.items() if not k.startswith("OSML_")}
    e.update({"OSML_ROOT": str(cwd), "OSML_ACCEPT_EXAMPLES": "1", **(env or {})})
    return subprocess.run([sys.executable, *args], cwd=cwd, env=e, capture_output=True, text=True, input=inp)


def make_project(root: Path, planted: bool) -> Path:
    for item in ("mlkit", "frame.yaml", "features.yaml", "decisions.md", "questions.yaml", "answers.yaml"):
        src = (KIT if item == "mlkit" else FIXTURE) / item
        (shutil.copytree if src.is_dir() else shutil.copy2)(src, root / item, **({"ignore": shutil.ignore_patterns("__pycache__")} if src.is_dir() else {}))
    for d in ("experiments", "stops", "reports", "model", "scripts"):
        (root / d).mkdir(exist_ok=True)
    (root / "model" / "base.py").write_text(PIPELINE)
    shutil.copy2(__file__, root / "scripts" / "make_residual_data.py")      # traced generator (D5)
    df = generate(80_000, planted, seed=1 if planted else 2)
    dev = root / "data" / "dev"
    dev.mkdir(parents=True)
    df.drop(columns=["default"]).to_csv(dev / "features.csv.gz", index=False)
    df[["id", "default"]].to_csv(dev / "labels.csv.gz", index=False)
    h = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()[:12]
    (dev / "manifest.json").write_text(json.dumps({
        "script": "scripts/make_residual_data.py", "script_hash": h(root / "scripts" / "make_residual_data.py"),
        "source_hash": "synthetic", "as_of": "2018-12", "steps": [],
        "outputs": {f: h(dev / f) for f in ("features.csv.gz", "labels.csv.gz")}}))
    return root


@pytest.fixture(scope="module")
def planted(tmp_path_factory):
    return make_project(tmp_path_factory.mktemp("planted"), planted=True)


@pytest.fixture(scope="module")
def clean(tmp_path_factory):
    return make_project(tmp_path_factory.mktemp("clean"), planted=False)


def run_residuals(root, *args, role="explorer"):
    r = sh(root, "-m", "mlkit.residuals", *args, env={"OSML_ROLE": role})
    assert r.returncode == 0, r.stdout + r.stderr
    ledger = [json.loads(l) for l in (root / "experiments" / "residuals_ledger.jsonl").read_text().splitlines()]
    stem = args[1] if args[0] == "--run" else ledger[-1]["res_id"]
    return json.loads((root / "reports" / f"residuals-{stem}.json").read_text()), ledger


def test_planted_signal_comes_first(planted):
    res, ledger = run_residuals(planted, "--pipeline", "model/base.py")
    entries = res["entries"]
    signals = [e for e in entries if e["status"] == "signal"]
    planted_cols = {"open_acc", "revol_util", "credit_history_months"}
    # the planted interaction is the best pair, above the family-wise floor
    pairs = [e for e in entries if e["kind"] == "paire"]
    assert set(pairs[0]["columns"]) == {"open_acc", "revol_util"} and pairs[0]["status"] == "signal", pairs[:3]
    assert pairs[0]["shape"] == "segment-specific" and "underestimated" in pairs[0]["sense"]
    # the threshold is found, with its shape
    hist = next(e for e in entries if e["columns"] == ["credit_history_months"])
    assert hist["status"] == "signal" and hist["shape"] == "threshold", hist
    assert hist["windows_positive"] == len(hist["per_window"])
    # nothing else than the planted columns is called a signal, and they lead the ranking
    for e in signals:
        assert set(e["columns"]) <= planted_cols | {"__score__"}, e
    assert {c for e in entries[:3] for c in e["columns"]} <= planted_cols
    # three hypotheses, citable, built from the signals
    hyp = res["hypotheses"]
    assert [h["id"] for h in hyp] == [f"{res['res_id']}/H{i}" for i in (1, 2, 3)]
    assert all(set(h["columns"]) <= planted_cols for h in hyp if h["columns"])
    assert any(set(h["columns"]) == {"open_acc", "revol_util"} for h in hyp)
    md = (planted / "reports" / f"residuals-{res['res_id']}.md").read_text()
    assert f"{res['res_id']}/H1" in md and "floor" in md
    assert ledger[-1]["res_id"] == res["res_id"] and ledger[-1]["n_signal"] == len(signals)


def test_no_signal_stays_under_the_chance_floor(clean):
    res, _ = run_residuals(clean, "--pipeline", "model/base.py")
    above = [e for e in res["entries"] if e["gain"] > e["floor_family"]]
    assert len(above) <= 1, [(e["columns"], e["gain"], e["floor_family"]) for e in above]
    assert all(e["gain"] <= 2 * max(e["floor_family"], 1e-9) for e in res["entries"])
    assert sum(h["confidence"].startswith("solide") for h in res["hypotheses"]) <= len(above)


def test_run_id_spends_no_budget_and_is_logged(planted):
    r = sh(planted, "-m", "mlkit.run", "--reference")
    assert r.returncode == 0, r.stderr
    r = sh(planted, "-m", "mlkit.run", "--pipeline", "model/base.py", "--note", "base")
    assert r.returncode in (0, 3), r.stderr
    reg = planted / "experiments" / "registry.jsonl"
    before = reg.read_text()
    run_id = [json.loads(l) for l in before.splitlines() if json.loads(l)["status"] == "exploratory"][-1]["run_id"]
    led = planted / "experiments" / "residuals_ledger.jsonl"
    n_ledger = len(led.read_text().splitlines()) if led.exists() else 0      # no dependence on test order
    res, ledger = run_residuals(planted, "--run", run_id, "--permutations", "10", role="data-analyst")
    assert reg.read_text() == before                      # nothing counted, no comparison with the reference
    assert res["predictions_reused"] is True              # the run's own out-of-sample predictions
    assert len(ledger) == n_ledger + 1 and ledger[-1]["run_id"] == run_id and ledger[-1]["role"] == "data-analyst"
    assert (planted / "reports" / f"residuals-{run_id}.md").exists()
    ref = [json.loads(l) for l in before.splitlines() if json.loads(l)["status"] == "reference"][-1]["run_id"]
    res_ref, _ = run_residuals(planted, "--run", ref, "--permutations", "5")   # the score in place, a rank: recalibrated
    assert res_ref["rows"] > 0


def test_roles(planted):
    for role in ("leak-reviewer", "feature-builder", "validator", "stop-writer"):
        r = sh(planted, "-m", "mlkit.residuals", "--pipeline", "model/base.py", env={"OSML_ROLE": role})
        assert r.returncode == 9 and "ROLE REFUSED" in r.stderr
    def guard(role):
        payload = {"tool_name": "Bash", "tool_input": {"command": "python -m mlkit.residuals --run r-0001"}}
        return sh(planted, "mlkit/guard.py", env={"OSML_ROLE": role}, inp=json.dumps(payload)).returncode
    assert guard("explorer") == 0 and guard("data-analyst") == 0
    assert guard("leak-reviewer") == 2 and guard("feature-builder") == 2 and guard("validator") == 2
    edit = {"tool_name": "Edit", "tool_input": {"file_path": "experiments/residuals_ledger.jsonl"}}
    assert sh(planted, "mlkit/guard.py", env={"OSML_ROLE": "explorer"}, inp=json.dumps(edit)).returncode == 2
    bad = sh(planted, "-m", "mlkit.residuals", "--run", "r-9999")
    assert bad.returncode == 2
