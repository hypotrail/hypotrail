"""mlkit.drift and E4 (informative since 2026-10-13), on synthetic data (scripts/make_synthetic.py).
No label of the target is ever read.

    OMP_NUM_THREADS=1 python -m pytest -q tests/test_drift.py      # about three minutes
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

KIT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).resolve().parent / "fixtures/legacy-project"
sys.path.insert(0, str(KIT))
from mlkit import core, drift  # noqa: E402


def _load(path: Path, name: str):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


SYNTH = _load(FIXTURE / "scripts" / "make_synthetic.py", "synth_drift")
COLS = list(_load(FIXTURE / "model" / "pipeline.py", "pipeline_drift").FEATURES)
REG = yaml.safe_load((FIXTURE / "features.yaml").read_text(encoding="utf-8"))["features"]
Q = drift.DEFAULTS | {"psi_warn": 0.10}


def periods(seed: int, n: int = 20000):
    """Training period of the holdout model (<= 2012-07, gap 36 months) and the holdout months."""
    df = SYNTH.generate(n, seed=seed)
    m = pd.PeriodIndex(df["issue_d"], freq="M")
    ref = df[m <= pd.Period("2012-07", "M")].reset_index(drop=True)
    tgt = df[m >= pd.Period("2015-07", "M")].reset_index(drop=True)
    return ref, tgt


def through_csv(tgt: pd.DataFrame, ref: pd.DataFrame) -> pd.DataFrame:
    """As mlkit.drift reads a holdout: CSV typing, then core.align_like on the dev types."""
    buf = io.StringIO()
    tgt.to_csv(buf, index=False)
    buf.seek(0)
    return core.align_like(pd.read_csv(buf), ref)


# ---------------------------------------------------------------- statistics, in process
def test_no_drift_false_alarm_rate():
    """20 draws of one stationary process: at most 1 REVIEW and 0 BROKEN CONTRACT."""
    verdicts, aucs = [], []
    for seed in range(20):
        ref, tgt = periods(100 + seed)
        r = drift.analyse(ref, tgt, COLS, REG, Q)
        verdicts.append(r["verdict"])
        aucs.append(r["adversarial"]["auc"])
    print(f"\nfausses alertes : {verdicts.count('REVIEW')}/20 REVIEW, {verdicts.count(drift.MAJOR)}/20 {drift.MAJOR} ; "
          f"AUC adversarial max {max(aucs):.3f}")
    assert verdicts.count(drift.MAJOR) == 0
    assert verdicts.count("REVIEW") <= 1, verdicts


def test_recoding_of_a_categorical_breaks_the_contract():
    """XP: a grade « RL0..RL5 » that comes back « 1..7 » (here home_ownership RENT/MORTGAGE/OWN -> 1/2/3)."""
    ref, tgt = periods(1)
    tgt = tgt.copy()
    tgt["home_ownership"] = tgt["home_ownership"].map({"RENT": 1, "MORTGAGE": 2, "OWN": 3})
    r = drift.analyse(ref, through_csv(tgt, ref), COLS, REG, Q)
    assert r["verdict"] == drift.MAJOR
    hit = [f for f in r["findings"] if f["column"] == "home_ownership" and f["rule"] == "recoding probable"]
    assert hit and hit[0]["level"] == drift.MAJOR, r["findings"]
    assert r["columns"]["home_ownership"]["schema"]["overlap"] == 0.0


def test_text_in_a_numeric_column_breaks_the_contract():
    ref, tgt = periods(2)
    tgt = tgt.copy()
    tgt["open_acc"] = tgt["open_acc"].map(lambda v: f"{v} years")
    r = drift.analyse(ref, tgt, COLS, REG, Q, with_adversarial=False)
    assert any(f["column"] == "open_acc" and f["level"] == drift.MAJOR for f in r["findings"]), r["findings"]


def test_segment_share_change_is_detected():
    """A segment (purpose=other, 10%) triples its target share: REVIEW, not BROKEN CONTRACT."""
    ref, tgt = periods(3)
    other = tgt[tgt["purpose"] == "other"]
    tgt = pd.concat([tgt, other, other, other, other], ignore_index=True)      # about 10 % -> 36 %
    r = drift.analyse(ref, tgt, COLS, REG, Q)
    assert r["verdict"] == "REVIEW", r["findings"]
    rules = {(f["column"], f["rule"]) for f in r["findings"]}
    assert ("purpose", "category share") in rules, rules
    assert r["adversarial"]["top"][0]["column"] == "purpose"


def test_new_modality_share_is_reported():
    ref, tgt = periods(4)
    tgt = tgt.copy()
    idx = tgt.sample(frac=0.05, random_state=0).index
    tgt.loc[idx, "verification_status"] = "Pending"          # 5 % of an unseen modality
    r = drift.analyse(ref, tgt, COLS, REG, Q, with_adversarial=False)
    assert any(f["column"] == "verification_status" and f["rule"] == "new categories" for f in r["findings"])
    assert r["verdict"] == "REVIEW"


def test_permuted_recoding_is_detected():
    """exp. 3: a recoding that KEEPS the symbols (A->B, B->C ... G->A) leaves the overlap at 100 %; the profile of
    the other columns per modality shows that « B » now holds the former « A » loans."""
    ref, tgt = periods(5)
    tgt = tgt.copy()
    tgt["grade"] = tgt["grade"].map(dict(zip("ABCDEFG", "BCDEFGA")))
    r = drift.analyse(ref, tgt, COLS, REG, Q, with_adversarial=False)
    assert r["columns"]["grade"]["schema"]["overlap"] == 1.0
    hit = [f for f in r["findings"] if f["column"] == "grade" and f["rule"] == "probable permuted recoding"]
    assert hit and hit[0]["level"] == drift.MAJOR, r["findings"]
    assert r["columns"]["grade"]["profile"]["share"] > 0.8
    # a share change alone (same loans, more of them in one modality) is not a permutation
    ref, tgt = periods(6)
    tgt = pd.concat([tgt, tgt[tgt["grade"] == "E"], tgt[tgt["grade"] == "E"]], ignore_index=True)
    r = drift.analyse(ref, tgt, COLS, REG, Q, with_adversarial=False)
    assert not [f for f in r["findings"] if "permuted" in f["rule"] or "profil" in f["rule"]], r["findings"]


def test_no_permutation_false_alarm():
    """10 stationary draws, every code column of the pipeline: the profile check never fires."""
    for seed in range(10):
        ref, tgt = periods(200 + seed)
        r = drift.analyse(ref, tgt, COLS, REG, Q, with_adversarial=False)
        assert not [f for f in r["findings"] if "permuted" in f["rule"] or "profil" in f["rule"]], (seed, r["findings"])


def _with_macro(ref, tgt, inside: bool):
    """A macro series: one value per month (random walk), as in the bank case of exp. 1."""
    rng = np.random.default_rng(0)
    out = []
    for df in (ref, tgt):
        df = df.copy()
        df["_month"] = pd.PeriodIndex(df["issue_d"], freq="M")
        out.append(df)
    months = sorted(set(out[0]["_month"]) | set(out[1]["_month"]))
    walk = dict(zip(months, np.round(np.cumsum(rng.normal(0, 0.1, len(months))), 3)))
    lo, hi = min(walk[m] for m in set(out[0]["_month"])), max(walk[m] for m in set(out[0]["_month"]))
    for m in set(out[1]["_month"]):          # target months: inside the training range, or above it
        walk[m] = round(float(rng.uniform(lo, hi)), 3) if inside else hi + 1 + rng.uniform(0, 1)
    for df in out:
        df["emp_var_rate"] = df["_month"].map(walk).astype(float)
    return out


def test_monthly_series_is_a_series_not_a_recoding():
    """A series constant within each month naturally has new target values. This is never
a recoding: only outside training support (REVIEW), excluded from adversarial analysis."""
    ref, tgt = periods(7)
    cols = COLS + ["emp_var_rate"]
    r_in = drift.analyse(*_with_macro(ref, tgt, inside=True), cols, REG, Q, with_adversarial=True)
    e = r_in["columns"]["emp_var_rate"]
    assert e["type"] == "monthly_series" and "schema" not in e and e["support"]["share_outside"] == 0.0
    assert not [f for f in r_in["findings"] if f["column"] == "emp_var_rate"], r_in["findings"]
    assert r_in["monthly_series"] == ["emp_var_rate"] and "emp_var_rate" in r_in["adversarial"]["excluded_series"]
    assert r_in["adversarial"]["auc"] < 0.6 and r_in["verdict"] == "OK", r_in["findings"]
    r_out = drift.analyse(*_with_macro(ref, tgt, inside=False), cols, REG, Q, with_adversarial=False)
    hit = [f for f in r_out["findings"] if f["column"] == "emp_var_rate"]
    assert [(f["level"], f["rule"]) for f in hit] == [("REVIEW", "monthly series outside training support")], hit
    assert r_out["verdict"] == "REVIEW"


# ---------------------------------------------------------------- command, E4 and guard, on a project
def sh(cwd, *args, env=None, inp=None):
    e = {k: v for k, v in os.environ.items() if not k.startswith("OSML_")}
    e.update({"OSML_ROOT": str(cwd), "OSML_ACCEPT_EXAMPLES": "1", "OMP_NUM_THREADS": "1", **(env or {})})
    return subprocess.run([sys.executable, *args], cwd=cwd, env=e, capture_output=True, text=True, input=inp)


def commit(root, msg):
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", msg],
                   cwd=root, check=True)


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    """A project ready for a holdout reading, whose holdout has home_ownership recoded into numbers."""
    root = tmp_path_factory.mktemp("proj_drift")
    private = tmp_path_factory.mktemp("private_drift") / ".hypotrail-ml"
    for item in ("mlkit", "model", "scripts", "frame.yaml", "features.yaml", "decisions.md", "questions.yaml", "answers.yaml"):
        src = (KIT if item == "mlkit" else FIXTURE) / item
        (shutil.copytree if src.is_dir() else shutil.copy2)(src, root / item)
    for d in ("experiments", "holdout", "stops", "preregistrations", "reports"):
        (root / d).mkdir(exist_ok=True)
    fr = root / "frame.yaml"
    fr.write_text(fr.read_text().replace("value_per_point: 1750000", "value_per_point: 700000")
                  .replace("swap_share: 0.10", "swap_share: 0.05")
                  .replace("selection_rule: mean_rank_all", "selection_rule: best"))   # these tests pre-register a single run
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    commit(root, "init")
    assert sh(root, "scripts/make_synthetic.py", "--private", str(private), "--n", "40000").returncode == 0
    hf = private / "holdout" / "features.csv.gz"
    h = pd.read_csv(hf)
    h["home_ownership"] = h["home_ownership"].map({"RENT": 1, "MORTGAGE": 2, "OWN": 3})
    h.to_csv(hf, index=False)
    assert sh(root, "-m", "mlkit.run", "--reference").returncode == 0
    run = sh(root, "-m", "mlkit.run", "--pipeline", "model/pipeline.py")
    assert run.returncode in (0, 3), run.stderr
    for st in (root / "stops").glob("STOP-*.json"):
        st.with_name(st.stem + ".decision.md").write_text("Test: stop lifted.\nSigned: test\n")
    assert sh(root, "-m", "mlkit.run", "--pipeline", "model/pipeline.py", "--null").returncode == 0
    regs = [json.loads(l) for l in (root / "experiments" / "registry.jsonl").read_text().splitlines()]
    rid = [x for x in regs if x["status"] == "exploratory"][0]["run_id"]
    nid = [x for x in regs if x["status"] == "null"][-1]["run_id"]
    sh(root, "-m", "mlkit.evaluate", "--run", rid)
    (root / "preregistrations" / "c-001.yaml").write_text(
        f"id: c-001\npipeline: model/pipeline.py\nrun: {rid}\nhypothesis: h\nexpected_gain: '+0.5'\nnull_run: {nid}\n")
    commit(root, "prereg")
    return root, private, rid


def test_window_target_runs_without_holdout(project):
    root, _, rid = project
    r = sh(root, "-m", "mlkit.drift", "--target", "window:2015-01..2015-06", "--run", rid)
    assert r.returncode == 0, r.stdout + r.stderr
    rep = json.loads((root / "reports" / "drift-window-2015-01..2015-06.json").read_text())
    assert rep["verdict"] == "OK", rep["findings"]
    assert rep["score"]["approval_ref"] > 0 and "decision" in (root / "reports" / "drift-window-2015-01..2015-06.md").read_text()
    assert sh(root, "-m", "mlkit.drift", "--target", "recent").returncode == 0
    assert sh(root, "-m", "mlkit.drift", "--target", "window:2015-07..2015-12").returncode != 0   # holdout months: refused


def test_e4_requires_a_report_but_its_verdict_is_informative(project):
    root, private, _ = project
    env = {"OSML_HOLDOUT_DIR": str(private / "holdout")}
    read = lambda: sh(root, "-m", "mlkit.holdout", "--prereg", "preregistrations/c-001.yaml", env=env)
    no_report = read()
    assert no_report.returncode != 0 and "E4" in no_report.stderr and "no report" in no_report.stderr, no_report.stderr
    # drift computed on a copy of the holdout WITHOUT labels.csv.gz: it must run, and it stays valid for the holdout
    blind = private / "blind"
    blind.mkdir()
    shutil.copy2(private / "holdout" / "features.csv.gz", blind / "features.csv.gz")
    fr = root / "frame.yaml"
    frame_text = fr.read_text()
    assert "drift_blocking: false" in frame_text
    fr.write_text(frame_text.replace("drift_blocking: false", "drift_blocking: true"))     # option: E4 blocking
    try:
        d = sh(root, "-m", "mlkit.drift", "--target", "holdout", "--prereg", "preregistrations/c-001.yaml",
               env={"OSML_HOLDOUT_DIR": str(blind)})
        assert d.returncode == 3 and drift.MAJOR in d.stdout, d.stdout + d.stderr
        assert "DRIFT-ACK" in (root / "reports" / "drift-holdout.md").read_text()
    finally:
        fr.write_text(frame_text)
    d = sh(root, "-m", "mlkit.drift", "--target", "holdout", "--prereg", "preregistrations/c-001.yaml",
           env={"OSML_HOLDOUT_DIR": str(blind)})
    assert d.returncode == 0 and drift.MAJOR in d.stdout and "home_ownership" in d.stdout, d.stdout + d.stderr
    assert "not a loss of gain" in d.stdout
    assert not (blind / "labels.csv.gz").exists()
    rep = json.loads((root / "reports" / "drift-holdout.json").read_text())
    md = (root / "reports" / "drift-holdout.md").read_text()
    assert md.splitlines()[2].startswith("> Ces indicateurs mesurent un changement de population") and "DRIFT-ACK" not in md
    assert rep["restricted"]["pipeline"] == "model/pipeline.py" and "score" in rep and rep["blocking"] is False
    # (c) effect on the decision of the flagged column, neutralised (replaced by its training distribution)
    neu = rep["score"]["neutralised"]
    assert "home_ownership" in neu and 0 <= neu["home_ownership"]["approval_neutralised"] <= 1
    assert "Decision effect of neutralizing a column" in md
    fp = rep["fingerprint"]
    # option drift_blocking: a BROKEN CONTRACT needs a signed DRIFT-ACK (checked on the function, the frame is frozen)
    blocking = ("import sys; from mlkit import config, drift; spec = config.load_frame()['spec']; "
                "spec['evaluation']['drift_blocking'] = True; "
                "print(drift.require_for_holdout('preregistrations/c-001.yaml', "
                "config.sha256_file(config.ROOT / 'model/pipeline.py'), spec)['ack'])")
    b = sh(root, "-c", blocking, env=env)
    assert b.returncode != 0 and f"DRIFT-ACK {fp}" in b.stderr, b.stderr
    dec = root / "decisions.md"
    before = dec.read_text()
    dec.write_text(before + f"\nDRIFT-ACK {fp} — known recoding — Signed: test\n")
    b = sh(root, "-c", blocking, env=env)
    dec.write_text(before)
    assert b.returncode == 0 and b.stdout.strip() == "True", b.stdout + b.stderr
    # default: no signature asked, the reading goes through and carries the drift summary
    ok = read()
    assert ok.returncode == 0, ok.stdout + ok.stderr
    entry = [json.loads(l) for l in (root / "holdout" / "ledger.jsonl").read_text().splitlines()][-1]
    assert entry["drift"]["fingerprint"] == fp and entry["drift"]["verdict"] == drift.MAJOR
    assert entry["drift"]["blocking"] is False and entry["drift"]["ack"] is None
    assert any("home_ownership" in x for x in entry["drift"]["summary"]["lines"])
    reading = (root / "reports" / "c-001.md").read_text()
    assert "Unlabeled drift (E4, informative)" in reading and "Neutraliser home_ownership" in reading
    card = sh(root, "-m", "mlkit.card", "--prereg", "c-001")
    assert card.returncode == 0, card.stdout + card.stderr
    assert "Unlabeled drift" in (root / "reports" / "model_card.md").read_text()
    c = sh(root, "-m", "mlkit.checks")
    assert any(l.startswith("OK") and "E4" in l for l in c.stdout.splitlines()), c.stdout
    # E4 KO: report deleted after the reading; or a reading made under drift_blocking whose signature is gone
    f = root / "reports" / "drift-holdout.json"
    saved = f.read_text()
    f.unlink()
    c = sh(root, "-m", "mlkit.checks")
    f.write_text(saved)
    assert any(l.startswith("KO") and "E4" in l for l in c.stdout.splitlines()), c.stdout
    fake = ("from mlkit import checks, config; e = dict(prereg='c-x', frame_hash=config.frame_hash(), "
            f"drift=dict(fingerprint='{fp}', verdict='{drift.MAJOR}', blocking=True, ack=True)); "
            "checks.e4_drift_before_holdout([e], config.frame_hash()); print(checks.RESULTS[-1][1])")
    assert sh(root, "-c", fake).stdout.strip() == "False"


def test_e4_report_must_match_the_preregistered_code(project):
    root, private, _ = project
    pipe = root / "model" / "pipeline.py"
    old = pipe.read_text()
    pipe.write_text(old + "\n# changed\n")
    try:
        out = sh(root, "-c", "import sys; from mlkit import config, drift; "
                 "spec = config.load_frame()['spec']; "
                 "drift.require_for_holdout('preregistrations/c-001.yaml', config.sha256_file(config.ROOT / 'model/pipeline.py'), spec)",
                 env={"OSML_HOLDOUT_DIR": str(private / "holdout")})
    finally:
        pipe.write_text(old)
    assert out.returncode != 0 and "stale" in out.stderr, out.stderr


def test_guard_drift_roles(project):
    root, _, _ = project

    def guard(cmd, role):
        return sh(root, "mlkit/guard.py", env={"OSML_ROLE": role},
                  inp=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})).returncode
    for role in ("explorer", "data-analyst"):
        assert guard("python -m mlkit.drift --target holdout --prereg preregistrations/c-001.yaml", role) == 2
        assert guard("python -m mlkit.drift --target window:2015-01..2015-06 --pipeline model/pipeline.py", role) == 0
    assert guard("python -m mlkit.drift --target recent --run r-0001", "explorer") == 0
    assert guard("python -m mlkit.drift --target recent --run r-0001", "data-analyst") == 2
    for role in ("feature-builder", "leak-reviewer", "stop-writer", "validator"):
        assert guard("python -m mlkit.drift --target recent", role) == 2
