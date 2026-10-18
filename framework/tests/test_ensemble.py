"""Selection rule mean_rank_all (mlkit.ensemble) on a temporary synthetic project.

    python -m pytest -q tests/test_ensemble.py
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

LR = '''from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

FEATURES = {features}


def build():
    return make_pipeline(StandardScaler(), LogisticRegression(max_iter=500))
'''
HGB = '''from sklearn.ensemble import HistGradientBoostingClassifier

FEATURES = ["fico_range_low", "dti", "annual_inc", "inq_last_6mths", "revol_util"]


def build():
    return HistGradientBoostingClassifier(max_iter=40, max_depth=3, random_state=0)
'''


def sh(cwd, *args, env=None):
    e = {k: v for k, v in os.environ.items() if not k.startswith("OSML_")}
    e.update({"OSML_ROOT": str(cwd), "OSML_ACCEPT_EXAMPLES": "1", "OSML_STOPS_FILE": str(cwd / ".stops.yaml"), **(env or {})})
    return subprocess.run([sys.executable, *args], cwd=cwd, env=e, capture_output=True, text=True)


def registry(root):
    return [json.loads(l) for l in (root / "experiments" / "registry.jsonl").read_text().splitlines()]


def ko(output: str, check: str) -> bool:
    return any(line.startswith("KO") and check in line for line in output.splitlines())


def prereg(root, run_id, pipeline):
    (root / "preregistrations" / "c-001.yaml").write_text(
        f"id: c-001\npipeline: {pipeline}\nrun: {run_id}\nhypothesis: test\nexpected_gain: '+0.1'\nnull_run: n-0001\n")


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    root = tmp_path_factory.mktemp("ens")
    private = tmp_path_factory.mktemp("private") / ".hypotrail-ml"
    for item in ("mlkit", "scripts", "frame.yaml", "features.yaml", "decisions.md", "questions.yaml", "answers.yaml"):
        src = (KIT if item == "mlkit" else FIXTURE) / item
        (shutil.copytree if src.is_dir() else shutil.copy2)(src, root / item)
    for d in ("experiments", "holdout", "stops", "preregistrations", "reports", "model"):
        (root / d).mkdir(exist_ok=True)
    shutil.copy2(FIXTURE / "model" / "reference_refit.py", root / "model" / "reference_refit.py")
    fr = root / "frame.yaml"
    text = fr.read_text()
    assert "\nspec:\n" in text
    if "selection_rule: mean_rank_all" not in text:                     # the example frame declares it since 2026-10-13
        text = text.replace("\nspec:\n", "\nspec:\n  selection_rule: mean_rank_all\n", 1)
    fr.write_text(text)
    (root / ".stops.yaml").write_text("too_good_gain: 1.0\nstagnation_runs: 1000\n")   # no stop in the way
    (root / "model" / "lr.py").write_text(LR.format(features='["fico_range_low", "dti", "annual_inc"]'))
    (root / "model" / "hgb.py").write_text(HGB)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "init"], cwd=root, check=True)
    r = sh(root, "scripts/make_synthetic.py", "--private", str(private), "--n", "40000")
    assert r.returncode == 0, r.stderr
    assert sh(root, "-m", "mlkit.run", "--reference").returncode == 0
    for p in ("model/lr.py", "model/hgb.py"):
        r = sh(root, "-m", "mlkit.run", "--pipeline", p, "--note", p)
        assert r.returncode == 0, r.stdout + r.stderr
    return root, private


def test_build_counts_one_comparison(project):
    root, _ = project
    before = sum(r.get("n_candidates", 1) for r in registry(root) if r["status"] == "exploratory")
    r = sh(root, "-m", "mlkit.ensemble")
    assert r.returncode == 0, r.stdout + r.stderr
    last = registry(root)[-1]
    assert last["pipeline"] == "model/ensemble_all.py" and last["status"] == "exploratory"
    assert last["note"] == "ensemble de 2 runs"
    assert last["n_candidates"] == 1 and last["comparisons_total"] == before + 1
    src = (root / "model" / "ensemble_all.py").read_text()
    runs = {x["pipeline"]: x for x in registry(root)}
    for p, fam in (("model/lr.py", "LogisticRegression"), ("model/hgb.py", "HistGradientBoostingClassifier")):
        assert f'("{p}", "{runs[p]["code_hash"]}", "{fam}")' in src    # members, hashes and families in the header
    assert set(last["features"]) == {"fico_range_low", "dti", "annual_inc", "inq_last_6mths", "revol_util"}
    again = sh(root, "-m", "mlkit.ensemble")                              # up to date: nothing spent
    assert again.returncode == 0 and "already current" in again.stdout
    assert registry(root)[-1]["run_id"] == last["run_id"]


def test_isolated_run_refused(project):
    root, private = project
    lr = next(x for x in registry(root) if x["pipeline"] == "model/lr.py")
    ev = sh(root, "-m", "mlkit.evaluate", "--run", lr["run_id"])
    assert ev.returncode != 0 and "isolated run" in ev.stderr
    prereg(root, lr["run_id"], "model/lr.py")
    c = sh(root, "-m", "mlkit.checks")
    assert ko(c.stdout, "E1 selection rule") and "isolated run" in c.stdout
    h = sh(root, "-m", "mlkit.holdout", "--prereg", "preregistrations/c-001.yaml",
           env={"OSML_HOLDOUT_DIR": str(private / "holdout")})
    assert h.returncode != 0 and "PREREGISTRATION REFUSED" in h.stderr and "isolated run" in h.stderr
    ens = registry(root)[-1]
    prereg(root, ens["run_id"], "model/ensemble_all.py")
    c = sh(root, "-m", "mlkit.checks")
    assert not ko(c.stdout, "E1 selection rule"), c.stdout
    ev = sh(root, "-m", "mlkit.evaluate", "--run", ens["run_id"])
    assert ev.returncode in (0, 1) and "report" in ev.stdout, ev.stderr  # evaluated (E1 verdict either way)


def test_stale_ensemble_is_ko(project):
    root, _ = project
    ens = registry(root)[-1]
    (root / "model" / "lr2.py").write_text(LR.format(features='["fico_range_low", "dti", "revol_util"]'))
    assert sh(root, "-m", "mlkit.run", "--pipeline", "model/lr2.py").returncode == 0
    prereg(root, ens["run_id"], "model/ensemble_all.py")
    c = sh(root, "-m", "mlkit.checks")
    assert ko(c.stdout, "E1 selection rule") and "stale" in c.stdout
    ev = sh(root, "-m", "mlkit.evaluate", "--run", ens["run_id"])
    assert ev.returncode != 0 and "stale" in ev.stderr
    r = sh(root, "-m", "mlkit.ensemble")
    assert r.returncode == 0, r.stdout + r.stderr
    new = registry(root)[-1]
    assert new["note"] == "ensemble de 3 runs"
    prereg(root, new["run_id"], "model/ensemble_all.py")
    assert not ko(sh(root, "-m", "mlkit.checks").stdout, "E1 selection rule")


def test_hand_edited_member_list_is_ko(project):
    root, _ = project
    ens = registry(root)[-1]
    f = root / "model" / "ensemble_all.py"
    old = f.read_text()
    f.write_text("\n".join(l for l in old.splitlines() if '("model/lr2.py"' not in l) + "\n")
    c = sh(root, "-m", "mlkit.checks")
    f.write_text(old)
    assert ko(c.stdout, "E1 selection rule") and "changed" in c.stdout
    prereg(root, ens["run_id"], "model/ensemble_all.py")


def test_changed_member_code_is_refused(project):
    root, _ = project
    lr = root / "model" / "lr.py"
    old = lr.read_text()
    lr.write_text(old + "\n# edited after the run\n")
    n = len(registry(root))
    r = sh(root, "-m", "mlkit.ensemble")
    direct = sh(root, "-m", "mlkit.run", "--pipeline", "model/ensemble_all.py")
    lr.write_text(old)
    assert r.returncode == 9 and "model/lr.py" in r.stderr and "code changed" in r.stderr
    assert direct.returncode != 0 and "ENSEMBLE REFUSED" in direct.stderr
    assert len(registry(root)) == n                                     # nothing registered, nothing spent


def test_guard_roles(project):
    root, _ = project
    def guard(role):
        payload = {"tool_name": "Bash", "tool_input": {"command": "python -m mlkit.ensemble"}}
        return subprocess.run([sys.executable, "mlkit/guard.py"], cwd=root, input=json.dumps(payload), text=True,
                              capture_output=True, env={**os.environ, "OSML_ROOT": str(root), "OSML_ROLE": role})
    assert guard("explorer").returncode == 0
    assert guard("feature-builder").returncode == 2 and guard("validator").returncode == 2


def test_ensemble_score_does_not_depend_on_the_batch():
    """Ranks are read against the training distribution: one row alone scores as in a batch."""
    import numpy as np
    import pandas as pd
    from sklearn.linear_model import LogisticRegression
    from mlkit.ensemble import RankAverage
    rng = np.random.default_rng(0)
    X = pd.DataFrame({"a": rng.normal(size=300), "b": rng.normal(size=300)})
    y = (X["a"] + rng.normal(size=300) > 0).astype(int)
    ens = RankAverage(members=())
    ens.fitted_ = []
    for cols in (["a"], ["a", "b"]):
        m = LogisticRegression().fit(X[cols], y)
        ens.fitted_.append((cols, m, np.sort(m.predict_proba(X[cols])[:, 1])))
    ens.classes_ = np.array([0, 1])
    new = pd.DataFrame({"a": rng.normal(size=50), "b": rng.normal(size=50)})
    batch = ens.predict_proba(new)[:, 1]
    alone = np.array([ens.predict_proba(new.iloc[[i]])[0, 1] for i in range(50)])
    # one training rank of tolerance: a single-row predict can differ from the batch by one ulp
    assert np.allclose(batch, alone, atol=1 / 300) and 0 <= batch.min() and batch.max() <= 1


# ---------------------------------------------------------------- families (2026-10-13)
def _fitted(members, cols_per_member, X, y):
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from mlkit.ensemble import RankAverage
    ens = RankAverage(members=tuple(members))
    ens.fitted_ = []
    for cols in cols_per_member:
        m = LogisticRegression().fit(X[cols], y)
        ens.fitted_.append((cols, m, np.sort(m.predict_proba(X[cols])[:, 1])))
    ens.classes_ = np.array([0, 1])
    return ens


def test_ten_copies_of_one_family_do_not_outweigh_another():
    """Mean inside each family, then across families: 10 near-identical variants weigh as one family."""
    import numpy as np
    import pandas as pd
    rng = np.random.default_rng(1)
    X = pd.DataFrame({"a": rng.normal(size=400), "b": rng.normal(size=400)})
    y = (X["a"] + X["b"] + rng.normal(size=400) > 0).astype(int)
    members = [(f"model/a{i}.py", "0" * 8, "LogisticRegression") for i in range(10)] + [("model/b.py", "1" * 8, "HistGradientBoostingClassifier")]
    ens = _fitted(members, [["a"]] * 10 + [["b"]], X, y)
    one_a = _fitted(members[:1] + members[10:], [["a"], ["b"]], X, y)        # one copy per family
    new = pd.DataFrame({"a": rng.normal(size=60), "b": rng.normal(size=60)})
    assert np.allclose(ens.predict_proba(new)[:, 1], one_a.predict_proba(new)[:, 1])
    flat = _fitted([m[:2] for m in members], [["a"]] * 10 + [["b"]], X, y)   # old files (no family): plain mean
    s_flat, s_fam = flat.predict_proba(new)[:, 1], ens.predict_proba(new)[:, 1]
    # with the plain mean the score follows « a » almost alone; by family, « b » counts half
    corr = lambda u, v: np.corrcoef(u, v)[0, 1]
    assert corr(s_flat, new["b"]) < 0.3 < corr(s_fam, new["b"])


def test_family_rule_and_explicit_label(tmp_path):
    from mlkit import core
    from mlkit.ensemble import MIX, family_of
    files = {
        "lr.py": "from sklearn.pipeline import make_pipeline\nfrom sklearn.preprocessing import StandardScaler\n"
                 "from sklearn.linear_model import LogisticRegression\nFEATURES = ['a']\n"
                 "def build():\n    return make_pipeline(StandardScaler(), LogisticRegression())\n",
        "et.py": "from sklearn.ensemble import ExtraTreesClassifier\nFEATURES = ['a']\n"
                 "def build():\n    return ExtraTreesClassifier()\n",
        "tuned.py": "from sklearn.pipeline import make_pipeline\nfrom sklearn.ensemble import HistGradientBoostingClassifier\n"
                    "from mlkit.tuning import TimeAwareSearch\nFEATURES = ['a']\n"
                    "def build():\n    return TimeAwareSearch(make_pipeline(HistGradientBoostingClassifier()), "
                    "{'histgradientboostingclassifier__max_depth': [2, 3]})\n",
        "vote.py": "from sklearn.ensemble import VotingClassifier, RandomForestClassifier\n"
                   "from sklearn.linear_model import LogisticRegression\nFEATURES = ['a']\n"
                   "def build():\n    return VotingClassifier([('l', LogisticRegression()), ('r', RandomForestClassifier())], voting='soft')\n",
        "home.py": "from sklearn.base import BaseEstimator, ClassifierMixin\nFEATURES = ['a']\n"
                   "class Blend(ClassifierMixin, BaseEstimator):\n    pass\n"
                   "def build():\n    return Blend()\n",
        # declared labels: only a cross-check of the derived family
        "label_family.py": "from sklearn.ensemble import ExtraTreesClassifier\nFAMILY = 'RandomForestClassifier'\nFEATURES = ['a']\n"
                           "def build():\n    return ExtraTreesClassifier()\n",
        "label_class.py": "from sklearn.ensemble import ExtraTreesClassifier\nFAMILY = 'ExtraTreesClassifier'\nFEATURES = ['a']\n"
                          "def build():\n    return ExtraTreesClassifier()\n",
        "label_mix.py": "from sklearn.ensemble import VotingClassifier, RandomForestClassifier\n"
                        "from sklearn.linear_model import LogisticRegression\nFAMILY = 'mixture'\nFEATURES = ['a']\n"
                        "def build():\n    return VotingClassifier([('l', LogisticRegression()), ('r', RandomForestClassifier())])\n",
    }
    got = {}
    for name, src in files.items():
        (tmp_path / name).write_text(src)
        got[name] = family_of(core.load_pipeline(str(tmp_path / name)))
    assert got == {"lr.py": "LogisticRegression", "et.py": "RandomForestClassifier",
                   "tuned.py": "HistGradientBoostingClassifier", "vote.py": MIX, "home.py": MIX,
                   "label_family.py": "RandomForestClassifier", "label_class.py": "RandomForestClassifier",
                   "label_mix.py": MIX}


def test_declared_family_incompatible_with_the_estimator_is_refused(tmp_path):
    """A label that disagrees with the estimator is refused: an invented family name,
or mixture declared for a plain logistic regression."""
    from mlkit import core
    from mlkit.ensemble import FamilyRefused, family_of
    for name, label in (("invented.py", "arbres-maison"), ("fake_mix.py", "mixture"), ("other.py", "HistGradientBoostingClassifier")):
        (tmp_path / name).write_text(f"from sklearn.linear_model import LogisticRegression\nFAMILY = {label!r}\n"
                                     "FEATURES = ['a']\ndef build():\n    return LogisticRegression()\n")
        with pytest.raises(FamilyRefused) as exc:
            family_of(core.load_pipeline(str(tmp_path / name)))
        assert exc.value.code != 0 and "LogisticRegression" in str(exc.value) and repr(label) in str(exc.value)


def test_thirty_copies_with_thirty_labels_gain_no_weight(tmp_path):
    """Exp. 4: 30 copies of one logistic regression, each declaring its own FAMILY, used to make 30 families
    and regain the weight of the plain mean. Now every such label is refused; without labels (or with the
    true one) the 30 copies are ONE family and weigh as one copy against the other family."""
    import numpy as np
    import pandas as pd
    from mlkit import core
    from mlkit.ensemble import FamilyRefused, family_of
    lr = ("from sklearn.linear_model import LogisticRegression\n{label}FEATURES = ['a']\n"
          "def build():\n    return LogisticRegression(C={c})\n")
    refused = 0
    for i in range(30):
        f = tmp_path / f"copy_{i}.py"
        f.write_text(lr.format(label=f"FAMILY = 'famille-{i}'\n", c=1 + i / 100))
        try:
            family_of(core.load_pipeline(str(f)))
        except FamilyRefused:
            refused += 1
    assert refused == 30
    fams = []
    for i in range(30):
        f = tmp_path / f"honest_{i}.py"
        f.write_text(lr.format(label="FAMILY = 'LogisticRegression'\n" if i % 2 else "", c=1 + i / 100))
        fams.append(family_of(core.load_pipeline(str(f))))
    (tmp_path / "hgb.py").write_text(HGB)
    fams.append(family_of(core.load_pipeline(str(tmp_path / "hgb.py"))))
    assert set(fams) == {"LogisticRegression", "HistGradientBoostingClassifier"}
    rng = np.random.default_rng(2)
    X = pd.DataFrame({"a": rng.normal(size=400), "b": rng.normal(size=400)})
    y = (X["a"] + X["b"] + rng.normal(size=400) > 0).astype(int)
    members = [(f"model/c{i}.py", "0" * 8, fams[i]) for i in range(30)] + [("model/h.py", "1" * 8, fams[30])]
    thirty = _fitted(members, [["a"]] * 30 + [["b"]], X, y)
    one = _fitted([members[0], members[30]], [["a"], ["b"]], X, y)
    new = pd.DataFrame({"a": rng.normal(size=80), "b": rng.normal(size=80)})
    assert np.allclose(thirty.predict_proba(new)[:, 1], one.predict_proba(new)[:, 1])


def test_baselines_are_members_with_their_family(project):
    """Baselines are exploratory runs: members of the rank average, each with its declared FAMILY."""
    root, _ = project
    fr = root / "frame.yaml"
    backup = fr.read_text()
    fr.write_text(backup.replace("baselines: [splines_logit, monotone_hgb, ebm, autogluon]",
                                 "baselines: [splines_logit, monotone_hgb]"))        # a new frame: fresh exploration
    try:
        b = sh(root, "-m", "mlkit.baselines", env={"OMP_NUM_THREADS": "1"})
        assert b.returncode == 0, b.stdout + b.stderr
        assert "Best baseline" not in b.stdout and "starting point for exploration" not in b.stdout
        r = sh(root, "-m", "mlkit.ensemble", env={"OMP_NUM_THREADS": "1"})
        assert r.returncode == 0, r.stdout + r.stderr
        src = (root / "model" / "ensemble_all.py").read_text()
    finally:
        fr.write_text(backup)
    assert registry(root)[-1]["note"] == "ensemble de 2 runs"
    assert '"model/baselines/splines_logit.py"' in src and '"LogisticRegression"),' in src
    assert '"model/baselines/monotone_hgb.py"' in src and '"HistGradientBoostingClassifier"),' in src


def test_ensemble_command_refuses_an_incompatible_family(project):
    """Last test of the module (it leaves a refused member in the registry): mlkit.ensemble exits 9, writes and
    registers nothing."""
    root, _ = project
    (root / "model" / "lr_label.py").write_text(LR.format(features='["fico_range_low", "annual_inc"]')
                                                + "\nFAMILY = 'famille-inventee'\n")
    assert sh(root, "-m", "mlkit.run", "--pipeline", "model/lr_label.py").returncode == 0
    ens = root / "model" / "ensemble_all.py"
    before_file, n = ens.read_text(), len(registry(root))
    r = sh(root, "-m", "mlkit.ensemble")
    assert r.returncode == 9 and "FAMILY" in r.stderr and "famille-inventee" in r.stderr, r.stdout + r.stderr
    assert ens.read_text() == before_file and len(registry(root)) == n
