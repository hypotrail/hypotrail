"""End-to-end self-test of the kit on synthetic data (about one minute).

    python -m pytest -q tests/

Each test checks that a guard catches what it claims to catch.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).resolve().parent / "fixtures/legacy-project"


def sh(cwd, *args, env=None, inp=None):
    e = {k: v for k, v in os.environ.items() if not k.startswith("OSML_")}
    e.update({"OSML_ROOT": str(cwd), "OSML_ACCEPT_EXAMPLES": "1", **(env or {})})
    e = {k: v for k, v in e.items() if v is not None}
    return subprocess.run([sys.executable, *args], cwd=cwd, env=e, capture_output=True, text=True, input=inp)


def drift_holdout(root, private, prereg="preregistrations/c-001.yaml"):
    """E4: a drift report on the holdout, restricted to the pre-registered pipeline, precedes any reading."""
    r = sh(root, "-m", "mlkit.drift", "--target", "holdout", "--prereg", prereg,
           env={"OSML_HOLDOUT_DIR": str(private / "holdout")})
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    root = tmp_path_factory.mktemp("proj")
    private = tmp_path_factory.mktemp("private") / ".hypotrail-ml"
    for item in ("mlkit", "model", "scripts", "frame.yaml", "features.yaml", "decisions.md", "questions.yaml", "answers.yaml"):
        src = (KIT if item == "mlkit" else FIXTURE) / item
        (shutil.copytree if src.is_dir() else shutil.copy2)(src, root / item)
    for d in ("experiments", "holdout", "stops", "preregistrations", "reports"):
        (root / d).mkdir(exist_ok=True)
    # 40 000 synthetic loans: the holdout cannot detect 0.2 point (E3). A small project prices its change
    # higher (350 000 / 700 000 = 0.5 point) and the synthetic model changes few accepted loans (5 %).
    fr = root / "frame.yaml"
    fr.write_text(fr.read_text().replace("value_per_point: 1750000", "value_per_point: 700000")
                  .replace("swap_share: 0.10", "swap_share: 0.05")
                  # With n_test/n_train > 1, Nadeau-Bengio fails the demo backtest; see
                  # the historical margin-rule benchmark. These guards are tested separately from N-B.
                  .replace("backtest_correction: nadeau_bengio", "backtest_correction: none")
                  # The synthetic candidate gains about 0.6 points against a 0.5 threshold: accepted under expected_value,
                  # the rule used by these tests, but refused under margin (lower bound about 0.3 points).
                  .replace("    rule: margin ", "    rule: expected_value ")
                  .replace("selection_rule: mean_rank_all", "selection_rule: best"))   # these tests evaluate single runs
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "init"], cwd=root, check=True)
    r = sh(root, "scripts/make_synthetic.py", "--private", str(private), "--n", "40000")
    assert r.returncode == 0, r.stderr
    return root, private


def test_reference_and_candidate(project):
    root, _ = project
    r = sh(root, "-m", "mlkit.run", "--reference")
    assert r.returncode == 0, r.stderr
    r = sh(root, "-m", "mlkit.run", "--pipeline", "model/pipeline.py", "--note", "first essai")
    assert r.returncode in (0, 3), r.stderr
    assert "gain" in r.stdout


def test_post_origination_feature_is_rejected(project):
    root, _ = project
    leaky = root / "model" / "leaky.py"
    leaky.write_text((root / "model" / "pipeline.py").read_text().replace(
        '"credit_history_months"]', '"credit_history_months", "total_pymnt"]'))
    r = sh(root, "-m", "mlkit.run", "--pipeline", "model/leaky.py")
    assert r.returncode == 4 and "total_pymnt" in r.stderr
    leaky.unlink()


def test_wrongly_declared_leak_triggers_stop(project):
    root, _ = project
    feats = root / "features.yaml"
    backup = feats.read_text()
    feats.write_text(backup.replace("  total_pymnt:          {available: post_origination",
                                    "  total_pymnt:          {available: origination"))
    leaky = root / "model" / "leaky2.py"
    leaky.write_text((root / "model" / "pipeline.py").read_text().replace(
        '"credit_history_months"]', '"credit_history_months", "total_pymnt"]'))
    r = sh(root, "-m", "mlkit.run", "--pipeline", "model/leaky2.py")
    assert r.returncode == 3 and "too beau" in r.stderr, r.stdout + r.stderr
    blocked = sh(root, "-m", "mlkit.run", "--pipeline", "model/pipeline.py")
    assert blocked.returncode == 5                      # open stop blocks further runs
    stop = sorted((root / "stops").glob("STOP-*.json"))[-1]
    h = sh(root, "-m", "mlkit.handoff", "--run", stop.stem.removeprefix("STOP-"), "--role", "leak-reviewer")
    assert h.returncode == 0
    handoff = json.loads(sorted((root / "handoff").glob("*-leak-reviewer.json"))[-1].read_text())
    assert "summary" not in handoff and "gain" not in handoff and "note" not in handoff
    (root / "stops" / f"{stop.stem}.decision.md").write_text("Leakage confirmed: total_pymnt reclassified as post_origination.")
    feats.write_text(backup)
    leaky.unlink()


def test_null_test_passes_on_clean_pipeline(project):
    root, _ = project
    r = sh(root, "-m", "mlkit.run", "--pipeline", "model/pipeline.py", "--null")
    assert r.returncode == 0, r.stdout + r.stderr


def test_checks_and_holdout(project):
    root, private = project
    r = sh(root, "-m", "mlkit.checks", "--data")
    assert r.returncode == 0, r.stdout
    runs = [json.loads(l) for l in (root / "experiments" / "registry.jsonl").read_text().splitlines()]
    null = [x for x in runs if x["status"] == "null" and x.get("null_pass")][-1]
    prereg = root / "preregistrations" / "c-001.yaml"
    cand0 = [x for x in runs if x["status"] == "exploratory" and x["pipeline"] == "model/pipeline.py"][0]
    prereg.write_text(f"id: c-001\npipeline: model/pipeline.py\nrun: {cand0['run_id']}\nhypothesis: gbm bat sub_grade only\n"
                      f"expected_gain: '+0.5 to +1.5 points'\nnull_run: {null['run_id']}\n")
    no = sh(root, "-m", "mlkit.holdout", "--prereg", "preregistrations/c-001.yaml",
            env={"OSML_HOLDOUT_DIR": str(private / "holdout")})
    assert no.returncode != 0 and "committed" in no.stderr     # uncommitted pre-registration refused
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "prereg c-001"], cwd=root, check=True)
    no_eval = sh(root, "-m", "mlkit.holdout", "--prereg", "preregistrations/c-001.yaml",
                 env={"OSML_HOLDOUT_DIR": str(private / "holdout")})
    assert no_eval.returncode != 0 and "evaluation" in no_eval.stderr       # an evaluation (threshold) is required
    cand = [x for x in runs if x["status"] == "exploratory" and x["pipeline"] == "model/pipeline.py"][0]
    ev = sh(root, "-m", "mlkit.evaluate", "--run", cand["run_id"])
    assert ev.returncode == 0, ev.stdout + ev.stderr
    drift_holdout(root, private)
    ok = sh(root, "-m", "mlkit.holdout", "--prereg", "preregistrations/c-001.yaml",
            env={"OSML_HOLDOUT_DIR": str(private / "holdout")})
    assert ok.returncode == 0, ok.stderr
    assert (root / "reports" / "c-001.md").exists()


def test_guard_blocks(project):
    root, _ = project
    def guard(payload, role="explorer"):
        return sh(root, "mlkit/guard.py", env={"OSML_ROLE": role}, inp=json.dumps(payload))
    assert guard({"tool_name": "Read", "tool_input": {"file_path": "/home/x/.hypotrail-ml/p/holdout/labels.csv.gz"}}).returncode == 2
    assert guard({"toolName": "bash", "toolArgs": {"command": "cat ~/.hypotrail-ml/p/holdout/labels.csv.gz"}}).returncode == 2
    assert guard({"tool_name": "Edit", "tool_input": {"file_path": "frame.yaml"}}).returncode == 2
    assert guard({"tool_name": "Read", "tool_input": {"file_path": "frame.yaml"}}).returncode == 0
    assert guard({"tool_name": "Read", "tool_input": {"file_path": "data/dev/labels.csv.gz"}}, "feature-builder").returncode == 2
    assert guard({"tool_name": "Bash", "tool_input": {"command": "python -m mlkit.status"}}, "leak-reviewer").returncode == 2
    assert guard({"tool_name": "Read", "tool_input": {"file_path": "handoff/r-0002-leak-reviewer.json"}}, "leak-reviewer").returncode == 0
    assert guard({"tool_name": "Read", "tool_input": {"file_path": "experiments/registry.jsonl"}}, "leak-reviewer").returncode == 2


# ---------------------------------------------------------------- data understanding (D1-D6)
def ko(output: str, check: str) -> bool:
    return any(line.startswith("KO") and check in line for line in output.splitlines())


def edit(path: Path, old: str, new: str) -> str:
    text = path.read_text()
    assert old in text, old
    path.write_text(text.replace(old, new, 1))
    return text


def test_profile_limits_target_analysis(project):
    root, _ = project
    r = sh(root, "-m", "mlkit.profile")
    assert r.returncode == 0, r.stderr
    prof = json.loads((root / "reports" / "data_profile.json").read_text())
    assert prof["exploration_period_end"] == "2011-01"          # first train_end, not the end of dev
    assert prof["columns"]["recoveries"]["strength"] > 0.8      # natural leak shows up
    assert any("individually predictive" in f for f in prof["columns"]["recoveries"]["flags"])
    assert prof["columns"]["sub_grade"]["strength"] < 0.8       # legitimate columns are not flagged


def test_d1_contract(project):
    root, _ = project
    f = root / "features.yaml"
    old = edit(f, "contract: {type: numeric, min: 500, max: 40000", "contract: {type: numeric, min: 500, max: 1000")
    r = sh(root, "-m", "mlkit.checks", "--data")
    run = sh(root, "-m", "mlkit.run", "--pipeline", "model/pipeline.py")
    f.write_text(old)
    assert r.returncode == 1 and ko(r.stdout, "D1") and "loan_amnt" in r.stdout
    assert run.returncode == 6 and "D1" in run.stderr


def test_d2_unregistered_column_blocks_runs(project):
    root, _ = project
    f = root / "features.yaml"
    text = f.read_text()
    lines = [l for l in text.splitlines(keepends=True) if not l.startswith("  initial_list_status:")]
    i = next(k for k, l in enumerate(lines) if l.startswith("                contract: {type: categorical, allowed: [w, f]"))
    del lines[i]
    f.write_text("".join(lines))
    r = sh(root, "-m", "mlkit.checks", "--data")
    run = sh(root, "-m", "mlkit.run", "--pipeline", "model/pipeline.py")
    f.write_text(text)
    assert ko(r.stdout, "D2") and "initial_list_status" in r.stdout
    assert run.returncode == 6


def test_d3_derived_from_post_origination(project):
    root, _ = project
    f = root / "features.yaml"
    old = edit(f, "derived_from: [issue_d, earliest_cr_line]", "derived_from: [issue_d, total_pymnt]")
    r = sh(root, "-m", "mlkit.checks")
    f.write_text(old)
    assert ko(r.stdout, "D3") and "credit_history_months" in r.stdout


def test_d5_untraced_preparation(project):
    root, _ = project
    script = root / "scripts" / "make_synthetic.py"
    old = script.read_text()
    script.write_text(old + "\n# filter added without a decision\n")
    r = sh(root, "-m", "mlkit.checks", "--data")
    run = sh(root, "-m", "mlkit.run", "--pipeline", "model/pipeline.py")
    script.write_text(old)
    assert ko(r.stdout, "D5") and run.returncode == 6


def test_d6_and_bait(project):
    root, private = project
    b = sh(root, "scripts/plant_bait.py", "--kind", "future_feature", "--private", str(private))
    assert b.returncode == 0, b.stderr
    f = root / "features.yaml"
    old = f.read_text()
    f.write_text(old + '  recent_contact_score: {available: origination, owner: INFERRED, meaning: "recent contact score"}\n')
    r = sh(root, "-m", "mlkit.checks", "--data")
    f.write_text(old)
    sh(root, "scripts/plant_bait.py", "--restore", "--private", str(private))
    assert ko(r.stdout, "D6") and "recent_contact_score" in r.stdout
    assert not ko(r.stdout, "D5")                      # the bait mimics a source flaw, not a tampering
    assert sh(root, "-m", "mlkit.checks", "--data").returncode == 0


def test_guard_data_analyst(project):
    root, _ = project
    def guard(payload):
        return sh(root, "mlkit/guard.py", env={"OSML_ROLE": "data-analyst"}, inp=json.dumps(payload))
    assert guard({"tool_name": "Read", "tool_input": {"file_path": "data/dev/labels.csv.gz"}}).returncode == 2
    assert guard({"tool_name": "Bash", "tool_input": {"command": "python -m mlkit.profile"}}).returncode == 0
    assert guard({"tool_name": "Edit", "tool_input": {"file_path": "decisions.md"}}).returncode == 2


def test_prepare_lendingclub_on_fake_source(tmp_path):
    """The real preparation script, on a small file shaped like Lending Club's."""
    import importlib.util

    import numpy as np
    import pandas as pd
    spec_ = importlib.util.spec_from_file_location("synth", FIXTURE / "scripts" / "make_synthetic.py")
    synth = importlib.util.module_from_spec(spec_)
    spec_.loader.exec_module(synth)
    df = synth.generate(8000, seed=3)
    rng = np.random.default_rng(1)
    per = pd.PeriodIndex(df["issue_d"], freq="M")
    df["issue_d"] = per.strftime("%b-%Y")
    df["term"] = rng.choice([" 36 months", " 60 months"], len(df), p=[0.75, 0.25])
    status = np.where(df["default"] == 1, "Charged Off", "Fully Paid").astype(object)
    status[rng.random(len(df)) < 0.02] = "Does not meet the credit policy. Status:Fully Paid"
    status[rng.random(len(df)) < 0.03] = "Current"
    df["loan_status"] = status
    df["application_type"] = rng.choice(["Individual", "Joint App"], len(df), p=[0.97, 0.03])
    df["emp_length"] = rng.choice(["< 1 year", "1 year", "10+ years", "n/a"], len(df), p=[0.3, 0.3, 0.35, 0.05])
    df["int_rate"] = df["int_rate"].map(lambda x: f"{x:.2f}%")
    df["earliest_cr_line"] = pd.PeriodIndex([p - int(m) for p, m in zip(per, df.pop("credit_history_months"))],
                                            freq="M").strftime("%b-%Y")
    df["column_not_in_registry"] = 1
    src = tmp_path / "lc.csv.gz"
    df.drop(columns=["default"]).to_csv(src, index=False)

    root = tmp_path / "proj"
    root.mkdir()
    for item in ("mlkit", "model", "scripts", "frame.yaml", "features.yaml", "decisions.md", "questions.yaml", "answers.yaml"):
        s = (KIT if item == "mlkit" else FIXTURE) / item
        (shutil.copytree if s.is_dir() else shutil.copy2)(s, root / item)
    r = sh(root, "scripts/prepare_lendingclub.py", str(src), "--private", str(tmp_path / "private"))
    assert r.returncode == 0, r.stderr
    dev = pd.read_csv(root / "data" / "dev" / "features.csv.gz")
    assert "column_not_in_registry" not in dev and "loan_status" not in dev
    assert pd.api.types.is_numeric_dtype(dev["int_rate"])
    assert set(dev["emp_length"].dropna().unique()) == {0, 1, 10}          # D-004: "< 1 year" is 0, not 1
    m = json.loads((root / "data" / "dev" / "manifest.json").read_text())
    assert {s["decision"] for s in m["steps"]} == {"D-001", "D-005", "D-006"}
    c = sh(root, "-m", "mlkit.checks", "--data")
    assert not ko(c.stdout, "D5") and not ko(c.stdout, "D2"), c.stdout



# ---------------------------------------------------------------- gates, tuning, maturity, production
def test_gate_requires_human_answers(project):
    root, _ = project
    r = sh(root, "-m", "mlkit.run", "--pipeline", "model/pipeline.py", env={"OSML_ACCEPT_EXAMPLES": None})
    assert r.returncode == 7 and "PHASE GATE" in r.stderr
    g = sh(root, "-m", "mlkit.gate", env={"OSML_ACCEPT_EXAMPLES": None})
    assert "Next phase : cadrage" in g.stdout and "Q-CAD-01" in g.stdout


def test_tuning_is_counted(project):
    root, _ = project
    tuned = root / "model" / "tuned.py"
    tuned.write_text((root / "model" / "pipeline.py").read_text()
                     .replace("from sklearn.preprocessing import OrdinalEncoder",
                              "from sklearn.preprocessing import OrdinalEncoder\nfrom mlkit.tuning import TimeAwareSearch")
                     .replace("    return make_pipeline(encode, model)",
                              "    return TimeAwareSearch(make_pipeline(encode, model),\n"
                              "        {'histgradientboostingclassifier__max_depth': [2, 3], 'histgradientboostingclassifier__learning_rate': [0.05, 0.1]})"))
    before = [json.loads(l) for l in (root / "experiments" / "registry.jsonl").read_text().splitlines()]
    total_before = sum(x.get("n_candidates", 1) for x in before if x["status"] == "exploratory")
    r = sh(root, "-m", "mlkit.run", "--pipeline", "model/tuned.py")
    tuned.unlink()
    assert r.returncode in (0, 3), r.stderr
    last = json.loads((root / "experiments" / "registry.jsonl").read_text().splitlines()[-1])
    assert last["n_candidates"] == 4 and last["comparisons_total"] == total_before + 4


def test_raw_grid_search_is_refused(project):
    root, _ = project
    bad = root / "model" / "raw.py"
    bad.write_text("from sklearn.model_selection import GridSearchCV\nFEATURES = ['loan_amnt']\n"
                   "def build():\n    return GridSearchCV(None, {})\n")
    r = sh(root, "-m", "mlkit.checks")
    bad.unlink()
    assert ko(r.stdout, "I5") and "TimeAwareSearch" in r.stdout


def test_d7_label_maturity(project):
    root, _ = project
    mpath = root / "data" / "dev" / "manifest.json"
    old = mpath.read_text()
    m = json.loads(old)
    m["as_of"] = "2017-06"
    mpath.write_text(json.dumps(m))
    r = sh(root, "-m", "mlkit.checks", "--data")
    mpath.write_text(old)
    assert ko(r.stdout, "D7")


def test_card_package_score_monitor(project, tmp_path):
    root, private = project
    import importlib.util
    assert sh(root, "-m", "mlkit.card", "--prereg", "c-001").returncode == 0
    assert "Number of experiments" in (root / "reports" / "model_card.md").read_text()
    refused = sh(root, "-m", "mlkit.package", "--prereg", "c-001")
    assert refused.returncode != 0 and "validation" in refused.stderr          # no signed validation yet
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs" / "validation.md").write_text("VERDICT: VALIDATED\nSigned: test, 2026-10-11\n")
    p = sh(root, "-m", "mlkit.package", "--prereg", "c-001")
    assert p.returncode == 0, p.stderr
    spec_ = importlib.util.spec_from_file_location("synth", root / "scripts" / "make_synthetic.py")
    synth = importlib.util.module_from_spec(spec_)
    spec_.loader.exec_module(synth)
    d = synth.generate(8000, seed=11).tail(4000).copy()
    d["id"] += 5_000_000
    d.loc[d.index[:25], "dti"] = 250                                   # out of contract
    d.drop(columns=["default"]).to_csv(tmp_path / "batch.csv", index=False)
    d[["id", "default"]].to_csv(tmp_path / "outcomes.csv", index=False)
    s = sh(root, "-m", "mlkit.score", "--model", "models/c-001", "--input", str(tmp_path / "batch.csv"),
           "--out", str(tmp_path / "scored.csv"))
    assert s.returncode == 0, s.stderr
    import pandas as pd
    scored = pd.read_csv(tmp_path / "scored.csv")
    assert (scored["decision"] == "revue_manuelle").sum() == 25
    share = (scored["groupe"] == "temoin").mean()
    assert 0.01 < share < 0.03                                          # 2 % control group, stable by id
    again = sh(root, "-m", "mlkit.score", "--model", "models/c-001", "--input", str(tmp_path / "batch.csv"),
               "--out", str(tmp_path / "scored2.csv"))
    assert again.returncode == 0
    assert (pd.read_csv(tmp_path / "scored2.csv")["groupe"] == scored["groupe"]).all()
    mon = sh(root, "-m", "mlkit.monitor", "--model", "models/c-001", "--input", str(tmp_path / "batch.csv"),
             "--scored", str(tmp_path / "scored.csv"), "--outcomes", str(tmp_path / "outcomes.csv"))
    assert mon.returncode == 0, mon.stdout + mon.stderr
    drifted = d.drop(columns=["default"]).copy()
    drifted["fico_range_low"] = (drifted["fico_range_low"] - 60).clip(600, 850)
    drifted.to_csv(tmp_path / "batch2.csv", index=False)
    sh(root, "-m", "mlkit.score", "--model", "models/c-001", "--input", str(tmp_path / "batch2.csv"),
       "--out", str(tmp_path / "scored3.csv"))
    alert = sh(root, "-m", "mlkit.monitor", "--model", "models/c-001", "--input", str(tmp_path / "batch2.csv"),
               "--scored", str(tmp_path / "scored3.csv"))
    assert alert.returncode == 1 and "fico_range_low" in alert.stdout
    c = sh(root, "-m", "mlkit.checks")
    assert not ko(c.stdout, "G1") and not ko(c.stdout, "E1"), c.stdout


# ---------------------------------------------------------------- selection and human pages
def git_commit(root, msg, *paths):
    subprocess.run(["git", "add", *paths], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", msg], cwd=root, check=True)


def test_bivariate_requires_committed_rule_and_tracks_changes(project):
    root, _ = project
    git_commit(root, "frame: selection rule", "frame.yaml")
    frame = root / "frame.yaml"
    original = frame.read_text()
    frame.write_text(original.replace("min_iv: 0.02", "min_iv: 0.03"))   # rule edited, not committed
    r = sh(root, "-m", "mlkit.bivariate")
    assert r.returncode == 7 and "NOT COMMITTED" in r.stderr
    frame.write_text(original)
    r = sh(root, "-m", "mlkit.bivariate")
    assert r.returncode == 0, r.stderr
    res = json.loads((root / "reports" / "bivariate.json").read_text())
    assert res["exploration_end"] == "2011-01"
    assert res["columns"]["fico_range_high"]["verdict"] == "excluded"   # redundant with fico_range_low
    assert all(c["floor"] > 0 for c in res["columns"].values())
    # the rule is changed after IVs were seen: I9 fails until a person ratifies it
    frame.write_text(original.replace("min_iv: 0.02", "min_iv: 0.05"))
    git_commit(root, "frame: stricter rule", "frame.yaml")
    assert sh(root, "-m", "mlkit.bivariate").returncode == 0
    r = sh(root, "-m", "mlkit.checks")
    assert "KO  I9" in r.stdout and "changed after reading IV values" in r.stdout
    new_hash = config_rule_hash(root)
    with open(root / "decisions.md", "a") as fh:
        fh.write(f"| D-090 | 2026-10-11 | DATA | HUMAN | selection | selection rule {new_hash} | test | | O |\n")
    assert "OK  I9" in sh(root, "-m", "mlkit.checks").stdout
    frame.write_text(original)
    git_commit(root, "frame: restore", "frame.yaml")


def config_rule_hash(root):
    return json.loads((root / "reports" / "bivariate.json").read_text())["rule_hash"]


def test_i9_flags_selection_outside_protocol(project):
    root, _ = project
    bad = root / "scripts" / "choose_features.py"
    bad.write_text("import pandas as pd\nfrom sklearn.feature_selection import mutual_info_classif\n"
                   "y = pd.read_csv('data/dev/labels.csv.gz')['default']\n")
    r = sh(root, "-m", "mlkit.checks")
    assert "choose_features.py" in r.stdout and "KO  I9" in r.stdout
    bad.unlink()


def test_selector_inside_pipeline_runs(project):
    root, _ = project
    shutil.copy2(FIXTURE / "model" / "pipeline_selection.py", root / "model" / "pipeline_selection.py")
    for p in (root / "stops").glob("STOP-*.json"):                 # earlier tests may leave a stop open
        (root / "stops" / f"{p.stem}.decision.md").write_text("Decision: continue\nSigned: test\n")
    r = sh(root, "-m", "mlkit.run", "--pipeline", "model/pipeline_selection.py")
    assert r.returncode in (0, 3), r.stderr
    (root / "model" / "pipeline_selection.py").unlink()


def test_render_pages_and_guard(project):
    root, _ = project
    assert sh(root, "-m", "mlkit.profile").returncode == 0
    r = sh(root, "-m", "mlkit.render")
    assert r.returncode == 0, r.stderr
    for name in ("index.html", "questions.html", "data.html"):
        txt = (root / "reports" / name).read_text()
        assert "<svg" in txt or name != "data.html"
        assert "http://" not in txt and "https://" not in txt          # self-contained, no network
    stops = list((root / "reports").glob("stop-STOP-*.html"))
    assert stops
    t = stops[0].read_text()
    assert "Your decision" in t or "Decision recorded" in t
    deny = sh(root, "mlkit/guard.py", inp=json.dumps({"tool_name": "Write", "tool_input": {"file_path": "reports/index.html"}}))
    assert deny.returncode == 2
    deny = sh(root, "mlkit/guard.py", inp=json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "mlkit/render.py"}}))
    assert deny.returncode == 2
    ok = sh(root, "mlkit/guard.py", inp=json.dumps({"tool_name": "Bash", "tool_input": {"command": "python -m mlkit.render"}}))
    assert ok.returncode == 0


# ---------------------------------------------------------------- lot 0 (after XP1)
def _registry(root):
    return [json.loads(l) for l in (root / "experiments" / "registry.jsonl").read_text().splitlines()]


def test_reference_is_the_existing_score(project):
    """XP1: a reference re-fitted on the grade was a weakened copy of it. The reference is the grade as is,
    declared in the frame (human-only file) and built by the kit."""
    root, _ = project
    import numpy as np
    import pandas as pd
    sys.path.insert(0, str(root))
    from mlkit.reference import ExistingScore
    grades = [f"{g}{i}" for g in "ABCDEFG" for i in range(1, 6)]
    X = pd.DataFrame({"sub_grade": ["B2", "A1", "G5", None]})
    p = ExistingScore("sub_grade", order=grades).fit(X, [1, 1, 1, 1]).predict_proba(X)[:, 1]
    assert p[1] < p[0] < p[2] and p[3] == p[2] == 1.0              # order kept; missing = riskiest; y ignored
    Xn = pd.DataFrame({"grade": [1.0, 3.0, np.nan]})                # integer grades read as float because of a NaN
    pn = ExistingScore("grade", order=[1, 2, 3]).fit(Xn).predict_proba(Xn)[:, 1]
    assert list(pn) == [0.0, 1.0, 1.0]
    with pytest.raises(ValueError):                                 # wrong column or incomplete list: refused
        ExistingScore("sub_grade", order=grades).fit(pd.DataFrame({"sub_grade": ["A1", "ZZ", "ZZ"]}))
    num = ExistingScore("fico", riskier="lower").fit(pd.DataFrame({"fico": [600, 700, 800]}))
    assert num.predict_proba(pd.DataFrame({"fico": [np.nan]}))[0, 1] == 1.0       # alone and missing: riskiest
    assert num.predict_proba(pd.DataFrame({"fico": [800, 600]}))[:, 1].tolist() == [0.0, 1.0]
    regs = _registry(root)
    refs = [r for r in regs if r["status"] == "reference"]
    seconds = [r for r in regs if r["status"] == "reference_secondary"]
    assert refs and refs[-1]["pipeline"] == "frame:reference(sub_grade)"
    assert seconds and seconds[-1]["reference_of"] == refs[-1]["run_id"]           # shown beside, never alone
    explo = [r for r in regs if r["status"] == "exploratory" and "reference" in r]
    assert explo and all(r["reference"].startswith("ref-") for r in explo)          # gains vs the score in place
    frame = root / "frame.yaml"
    old = frame.read_text()
    block = old[old.index("\n  reference:") + 1:old.index("  reference_secondary_pipeline")]
    refit = "  reference:\n    kind: refit\n    pipeline: model/reference_refit.py\n"
    frame.write_text(old.replace(block, refit))
    r = sh(root, "-m", "mlkit.run", "--reference")
    c = sh(root, "-m", "mlkit.checks")
    frame.write_text(old.replace(block, refit + "    justification: \"no incumbent score (test)\"\n"))
    c2 = sh(root, "-m", "mlkit.checks")
    frame.write_text(old)
    assert r.returncode == 2 and "justification" in r.stderr, r.stderr
    assert ko(c.stdout, "I3 reference") and not ko(c2.stdout, "I3 reference")


def test_budget_is_checked_before_the_run(project):
    """XP1: r-0026 compared 6 candidates when 4 were left (36 -> 42 for 40). Now refused before fitting."""
    root, _ = project
    big = root / "model" / "big_grid.py"
    big.write_text((root / "model" / "pipeline.py").read_text()
                   .replace("from sklearn.preprocessing import OrdinalEncoder",
                            "from sklearn.preprocessing import OrdinalEncoder\nfrom mlkit.tuning import TimeAwareSearch")
                   .replace("    return make_pipeline(encode, model)",
                            "    return TimeAwareSearch(make_pipeline(encode, model),\n"
                            "        {'histgradientboostingclassifier__max_depth': list(range(2, 13)),\n"
                            "         'histgradientboostingclassifier__learning_rate': [0.01, 0.03, 0.05, 0.1, 0.2],\n"
                            "         'histgradientboostingclassifier__max_iter': [50, 100]})"))
    before = len(_registry(root))
    r = sh(root, "-m", "mlkit.run", "--pipeline", "model/big_grid.py")
    big.unlink()
    assert r.returncode == 8 and "budget" in r.stderr, r.stdout + r.stderr
    regs = _registry(root)
    assert len(regs) == before + 1 and regs[-1]["status"] == "rejected" and regs[-1]["planned_candidates"] == 110
    assert "n_candidates" not in regs[-1]                    # nothing was fitted, nothing was spent
    sys.path.insert(0, str(root))
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from mlkit.core import planned_candidates
    from mlkit.tuning import TimeAwareSearch
    hidden = CalibratedClassifierCV(make_pipeline(StandardScaler(),
                                    TimeAwareSearch(LogisticRegression(), {"C": [0.01, 0.1, 1, 10, 100]})))
    assert planned_candidates(hidden) == 5                    # a grid wrapped in a calibrator is still counted


def test_d6_blocks_a_run_using_a_too_predictive_column(project):
    """XP1: D6 flagged the bait at AUC 0.93 but did not block runs; only the agent's judgement stopped it."""
    root, private = project
    b = sh(root, "scripts/plant_bait.py", "--kind", "future_feature", "--private", str(private))
    assert b.returncode == 0, b.stderr
    f = root / "features.yaml"
    old = f.read_text()
    f.write_text(old + '  recent_contact_score: {available: origination, owner: INFERRED, meaning: "recent contact score"}\n')
    bait = root / "model" / "bait.py"
    bait.write_text((root / "model" / "pipeline.py").read_text().replace(
        '"credit_history_months"]', '"credit_history_months", "recent_contact_score"]'))
    r = sh(root, "-m", "mlkit.run", "--pipeline", "model/bait.py")
    f.write_text(old + '  recent_contact_score: {available: origination, owner: INFERRED, meaning: "recent contact score", leak_ack: "test"}\n')
    r2 = sh(root, "-m", "mlkit.run", "--pipeline", "model/bait.py")   # acknowledged by a person: D6 lets it run
    for st in (root / "stops").glob("STOP-*.json"):                    # the gain is too good: close that stop
        d = st.with_name(st.stem + ".decision.md")
        if not d.exists():
            d.write_text("Test: bait deliberately acknowledged; branch stopped.")
    f.write_text(old)
    bait.unlink()
    sh(root, "scripts/plant_bait.py", "--restore", "--private", str(private))
    assert r.returncode == 4 and "D6" in r.stderr and "recent_contact_score" in r.stderr, r.stdout + r.stderr
    assert r2.returncode != 4, r2.stderr


def test_d6_exempts_the_score_in_place(project):
    """A strong score in place is not a leak: D6 must not block the reference run."""
    root, _ = project
    f = root / "features.yaml"
    old = f.read_text()
    f.write_text(old.replace("univariate_auc_stop: 0.80", "univariate_auc_stop: 0.55"))
    r = sh(root, "-m", "mlkit.run", "--reference")
    f.write_text(old)
    assert r.returncode == 0, r.stderr
    last = [x for x in _registry(root) if x["status"] == "reference"][-1]
    assert last["univariate_auc"]["sub_grade"] >= 0.55          # the exemption was actually exercised


def test_every_module_compiles():
    """A syntax error in a rarely-run module (holdout, package) must not wait for the holdout reading."""
    import py_compile
    for p in sorted((KIT / "mlkit").glob("*.py")):
        py_compile.compile(str(p), doraise=True)


# ---------------------------------------------------------------- lots 1-2 (decision rule v2, holdout policy)
def test_decision_rule_v2_units(project):
    root, _ = project
    import numpy as np
    sys.path.insert(0, str(root))
    from mlkit import decision
    spec = {"acceptance": {"cost_model": {"deployment": 150000, "validation": 50000, "run_per_year": 50000,
                                          "horizon_years": 3, "value_per_point": 1750000}}}
    assert abs(decision.min_gain(spec)["min_gain"] - 0.002) < 1e-12               # 350 000 / 1 750 000 = 0.2 point
    typed = decision.min_gain({"acceptance": {"min_gain": 0.002}})
    assert typed["source"] == "typed" and not typed["justification"]
    assert decision.backtest_gate(np.array([0.002, -0.001, 0.0005, -0.002, 0.001]))["pass"] is False
    assert decision.backtest_gate(np.full(18, 0.003) + np.linspace(-1e-4, 1e-4, 18))["pass"] is True
    rng = np.random.default_rng(0)
    n = 20000
    s_ref = rng.random(n)
    harmed = rng.random(n) < 0.3
    s_cand = np.where(harmed, rng.random(n), s_ref)                  # the candidate scrambles the order for 30 %
    y = (rng.random(n) < 0.05 + 0.25 * s_ref).astype(float)
    gate = decision.segment_gate(y, s_ref, s_cand, np.zeros(n), {"harmed": harmed, "autres": ~harmed}, 0.9, 0.005)
    assert gate["pass"] is False and "harmed" in gate["reason"] and "autres" not in gate["reason"]
    r = decision.mde(120000, 0.9, 0.25, 0.10)
    assert 0.0008 < r["mde"] < 0.0016                                 # about 0.1 point for an XP1-sized holdout


def test_holdout_policy_after_a_reading(project):
    """After a reading: the threshold cannot move, and a candidate born after it cannot be read."""
    root, private = project
    env = {"OSML_HOLDOUT_DIR": str(private / "holdout")}
    ledger = [json.loads(l) for l in (root / "holdout" / "ledger.jsonl").read_text().splitlines()]
    assert ledger and ledger[0]["holdout_hash"] and "min_gain" in ledger[0]
    frame = root / "frame.yaml"
    old = frame.read_text()
    frame.write_text(old.replace("value_per_point: 700000", "value_per_point: 900000"))   # renegotiated after reading
    r = sh(root, "-m", "mlkit.holdout", "--prereg", "preregistrations/c-001.yaml", env=env)
    frame.write_text(old)
    assert r.returncode != 0 and "holdout neuf" in r.stderr, r.stdout + r.stderr
    late = root / "model" / "late.py"
    late.write_text((root / "model" / "pipeline.py").read_text() + "\n# variant written after the first reading\n")
    run = sh(root, "-m", "mlkit.run", "--pipeline", "model/late.py")
    assert run.returncode in (0, 3), run.stderr
    for st in (root / "stops").glob("STOP-*.json"):
        d = st.with_name(st.stem + ".decision.md")
        if not d.exists():
            d.write_text("Test: stop lifted.")
    rid = [x for x in _registry(root) if x.get("pipeline") == "model/late.py" and x["status"] == "exploratory"][-1]["run_id"]
    null = sh(root, "-m", "mlkit.run", "--pipeline", "model/late.py", "--null")
    nid = [x for x in _registry(root) if x.get("pipeline") == "model/late.py" and x["status"] == "null"][-1]["run_id"]
    sh(root, "-m", "mlkit.evaluate", "--run", rid)
    pre = root / "preregistrations" / "c-002.yaml"
    pre.write_text(f"id: c-002\npipeline: model/late.py\nrun: {rid}\nhypothesis: variante\nexpected_gain: '+0.5 point'\nnull_run: {nid}\n")
    git_commit(root, "prereg c-002", "-A")
    r2 = sh(root, "-m", "mlkit.holdout", "--prereg", "preregistrations/c-002.yaml", env=env)
    assert null.returncode == 0 and r2.returncode != 0 and "after the first reading" in r2.stderr, r2.stdout + r2.stderr


@pytest.fixture(scope="module")
def project_e1_fails(tmp_path_factory):
    """A second, independent project whose E1 fails by construction (a pre-registered segment that does not exist)."""
    root = tmp_path_factory.mktemp("proj_e1")
    private = tmp_path_factory.mktemp("private_e1") / ".hypotrail-ml"
    for item in ("mlkit", "model", "scripts", "frame.yaml", "features.yaml", "decisions.md", "questions.yaml", "answers.yaml"):
        src = (KIT if item == "mlkit" else FIXTURE) / item
        (shutil.copytree if src.is_dir() else shutil.copy2)(src, root / item)
    for d in ("experiments", "holdout", "stops", "preregistrations", "reports"):
        (root / d).mkdir(exist_ok=True)
    fr = root / "frame.yaml"
    fr.write_text(fr.read_text().replace("value_per_point: 1750000", "value_per_point: 700000")
                  .replace("swap_share: 0.10", "swap_share: 0.05")
                  .replace("selection_rule: mean_rank_all", "selection_rule: best")   # these tests evaluate single runs
                  .replace('"home_ownership=MORTGAGE"', '"home_ownership=MORTGAG"'))     # typo: n = 0, fails visibly
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    git_commit(root, "init", "-A")
    r = sh(root, "scripts/make_synthetic.py", "--private", str(private), "--n", "40000")
    assert r.returncode == 0, r.stderr
    assert sh(root, "-m", "mlkit.run", "--reference").returncode == 0
    run = sh(root, "-m", "mlkit.run", "--pipeline", "model/pipeline.py")
    assert run.returncode in (0, 3), run.stderr
    null = sh(root, "-m", "mlkit.run", "--pipeline", "model/pipeline.py", "--null")
    assert null.returncode == 0, null.stderr
    regs = _registry(root)
    rid = [x for x in regs if x["status"] == "exploratory"][-1]["run_id"]
    nid = [x for x in regs if x["status"] == "null"][-1]["run_id"]
    ev = sh(root, "-m", "mlkit.evaluate", "--run", rid)
    assert ev.returncode == 1 and "MORTGAG" in ev.stdout, ev.stdout        # E1 fails on the misspelled segment
    (root / "preregistrations" / "c-001.yaml").write_text(
        f"id: c-001\npipeline: model/pipeline.py\nrun: {rid}\nhypothesis: h\nexpected_gain: '+0.5'\nnull_run: {nid}\n")
    git_commit(root, "prereg", "-A")
    drift_holdout(root, private)
    return root, private


def test_reading_allowed_when_e1_fails_but_not_acceptance(project_e1_fails):
    root, private = project_e1_fails
    env = {"OSML_HOLDOUT_DIR": str(private / "holdout")}
    r = sh(root, "-m", "mlkit.holdout", "--prereg", "preregistrations/c-001.yaml", env=env)
    assert r.returncode == 0, r.stdout + r.stderr                   # the best candidate can still be measured
    e = [json.loads(l) for l in (root / "holdout" / "ledger.jsonl").read_text().splitlines()][-1]
    assert e["e1_pass"] is False and e["accepted"] is False
    assert "NOT ACCEPTED" in (root / "reports" / "c-001.md").read_text()
    sh(root, "-m", "mlkit.card", "--prereg", "c-001")
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs" / "validation.md").write_text("VERDICT: VALIDATED\nSigned: test\n")
    pk = sh(root, "-m", "mlkit.package", "--prereg", "c-001")
    assert pk.returncode != 0 and "accepted" in pk.stderr, pk.stderr  # E1 still blocks the production package


def test_holdout_budget_survives_recompression_and_typed_threshold_refused(project_e1_fails):
    root, private = project_e1_fails
    env = {"OSML_HOLDOUT_DIR": str(private / "holdout")}
    import gzip
    for name in ("features.csv.gz", "labels.csv.gz"):              # same content, new gzip bytes
        f = private / "holdout" / name
        data = gzip.decompress(f.read_bytes())
        f.write_bytes(gzip.compress(data, mtime=12345))
    frame = root / "frame.yaml"
    old = frame.read_text()
    frame.write_text(old.replace("    cost_model:", "    min_gain: 0.001\n    cost_model_unused:"))
    typed = sh(root, "-m", "mlkit.holdout", "--prereg", "preregistrations/c-001.yaml", env=env)
    frame.write_text(old)
    assert typed.returncode != 0 and "min_gain_source" in typed.stderr, typed.stdout + typed.stderr
    import pandas as pd
    feats = private / "holdout" / "features.csv.gz"                  # a column dropped: still the same holdout
    pd.read_csv(feats).drop(columns=["recoveries"]).to_csv(feats, index=False)
    second = sh(root, "-m", "mlkit.holdout", "--prereg", "preregistrations/c-001.yaml", env=env)
    assert second.returncode == 0, second.stderr                     # 2/2, same holdout recognised
    third = sh(root, "-m", "mlkit.holdout", "--prereg", "preregistrations/c-001.yaml", env=env)
    assert third.returncode != 0 and "BUDGET EXHAUSTED" in third.stderr, third.stdout + third.stderr
    ledger = [json.loads(l) for l in (root / "holdout" / "ledger.jsonl").read_text().splitlines()]
    assert len({e["holdout_hash"] for e in ledger}) == 1


def test_decision_rule_is_frozen_after_its_first_use(project):
    """Changing a margin after seeing an E1 verdict needs a signed ratification (fresh review, lots 1-2)."""
    root, _ = project
    frame = root / "frame.yaml"
    old = frame.read_text()
    frame.write_text(old.replace("      margin: 0.005", "      margin: 0.02"))
    for st in (root / "stops").glob("STOP-*.json"):
        d = st.with_name(st.stem + ".decision.md")
        if not d.exists():
            d.write_text("Test: stop lifted.")
    assert sh(root, "-m", "mlkit.run", "--reference").returncode == 0
    run = sh(root, "-m", "mlkit.run", "--pipeline", "model/pipeline.py")
    assert run.returncode in (0, 3), run.stderr
    rid = [x for x in _registry(root) if x["status"] == "exploratory"][-1]["run_id"]
    ev = sh(root, "-m", "mlkit.evaluate", "--run", rid)
    h = json.loads((root / "reports" / f"eval-{rid}.json").read_text())["rule_hash"]
    dec = root / "decisions.md"
    before = dec.read_text()
    dec.write_text(before + f"\nDECISION-RULE {h} — margin enlarged for the test\n")          # not signed: refused
    ev2 = sh(root, "-m", "mlkit.evaluate", "--run", rid)
    dec.write_text(before + f"\nDECISION-RULE {h} — margin enlarged for the test — Signed: test\n")
    ev3 = sh(root, "-m", "mlkit.evaluate", "--run", rid)
    dec.write_text(before)
    frame.write_text(old)
    assert ev.returncode == 1 and "decision rule changed" in ev.stdout, ev.stdout
    assert "decision rule changed" in ev2.stdout
    assert "decision rule changed" not in ev3.stdout, ev3.stdout


def test_holdout_sketch_recognises_overlap():
    sys.path.insert(0, str(KIT))
    from mlkit.holdout import jaccard
    import hashlib
    h = lambda ids: sorted(int(hashlib.sha256(str(i).encode()).hexdigest()[:15], 16) for i in ids)[:256]
    a = h(range(10000))
    assert jaccard(a, h(range(500, 10000))) > 0.8          # 5 % of rows dropped: same holdout
    assert jaccard(a, h(range(10000, 20000))) < 0.05      # a new period: new holdout


def test_holdout_types_follow_dev():
    """XP2: a development text-code column (RL2, 1) is read as numbers in holdout."""
    import pandas as pd
    from mlkit import core
    dev = pd.DataFrame({"g": pd.Series(["RL2", "1", None], dtype=object), "x": [1.0, 2.0, 3.0]})
    hold = pd.DataFrame({"g": [2.0, None, 1.0], "x": [4.0, 5.0, 6.0]})
    out = core.align_like(hold, dev)
    assert list(out["g"].iloc[[0, 2]]) == ["2", "1"] and pd.isna(out["g"].iloc[1])
    assert out["x"].dtype == float
