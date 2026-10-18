"""Data loading, backtest windows, metrics and pipeline loading."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, roc_auc_score

from . import config


# ---------------------------------------------------------------- data
def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False)


def load_split(directory: Path, spec: dict) -> pd.DataFrame:
    """features.csv.gz joined with labels.csv.gz on the id column."""
    feats = _read(directory / "features.csv.gz")
    labels = _read(directory / "labels.csv.gz")
    key, target = spec["id_col"], spec["target_col"]
    for name, table in (("features", feats), ("labels", labels)):
        if table[key].isna().any() or table[key].duplicated().any():
            raise ValueError(f"{name}: missing or duplicate identifiers")
    if set(feats[key]) != set(labels[key]):
        raise ValueError("features/labels: identifier sets differ")
    if labels[target].isna().any() or not labels[target].isin([0, 1]).all():
        raise ValueError("target: complete binary 0/1 values required")
    if target in feats:
        raise ValueError("target present among features")
    df = feats.merge(labels[[key, target]], on=key, how="inner", validate="one_to_one")
    df["_month"] = pd.PeriodIndex(df[spec["time_col"]].astype(str), freq="M")
    # time order inside every window: inner, time-aware tuning (mlkit.tuning) relies on it
    return df.sort_values("_month", kind="mergesort").reset_index(drop=True)


def align_like(df: pd.DataFrame, ref: pd.DataFrame) -> pd.DataFrame:
    """Give every column of `df` (holdout) the kind it has in `ref` (dev).

    A CSV column is typed from its content: a code column that is text in dev ("RL2", "1")
    and only digits or empty in the holdout comes back as float, and a pipeline fitted on
    text cannot score it. Text columns of dev are turned back into text: 2.0 -> "2", NaN kept.
    """
    out = df.copy()
    for c in ref.columns.intersection(out.columns):
        if pd.api.types.is_numeric_dtype(ref[c]) or pd.api.types.is_bool_dtype(ref[c]):
            continue
        if pd.api.types.is_numeric_dtype(out[c]) or pd.api.types.is_bool_dtype(out[c]):
            v = out[c]
            txt = v.map(lambda x: x if pd.isna(x) else (str(int(x)) if isinstance(x, float) and float(x).is_integer() else str(x)))
            out[c] = txt.astype(ref[c].dtype) if str(ref[c].dtype) != "object" else txt.astype(object)
    return out


def load_dev(spec: dict) -> pd.DataFrame:
    return load_split(config.DEV_DIR, spec)


def dev_files() -> list[Path]:
    return [config.DEV_DIR / "features.csv.gz", config.DEV_DIR / "labels.csv.gz"]


# ---------------------------------------------------------------- backtest
def windows(spec: dict, stress: bool = True):
    """Yield (name, train_end, test_start, test_end) as monthly Periods.

    A loan issued in month m has a known outcome at month m + gap, so a model
    used at test_start may only learn from loans issued <= test_start - gap.
    Pre-registered stress windows (backtest.stress_windows) that are not already
    test windows are added after them (stress=False: the test windows only).
    """
    gap = int(spec["backtest"]["gap_months"])
    test = [tuple(map(str, w)) for w in spec["backtest"]["test_windows"]]
    extra = [tuple(map(str, w)) for w in spec["backtest"].get("stress_windows") or [] if stress]
    for first, last in test + [w for i, w in enumerate(extra) if w not in test and w not in extra[:i]]:
        start, end = pd.Period(first, "M"), pd.Period(last, "M")
        yield f"{first}..{last}", start - gap, start, end


def stress_names(spec: dict) -> list[str]:
    return [f"{a}..{b}" for a, b in spec["backtest"].get("stress_windows") or []]


def holdout_window(spec: dict):
    gap = int(spec["backtest"]["gap_months"])
    first, last = spec["holdout"]["window"]
    start, end = pd.Period(first, "M"), pd.Period(last, "M")
    return start - gap, start, end


# ---------------------------------------------------------------- metrics
def bad_rate_at_approval(y, score, rate: float) -> float:
    """Bad rate among the `rate` lowest-risk cases. Tied scores at the cut-off are
    taken in proportion (expected value), never in file order: a coarse score such
    as a grade has large ties, and file order (sorted by month) would bias it (XP1)."""
    s, y = np.asarray(score, dtype=float), np.asarray(y, dtype=float)
    k = rate * len(s)
    vals, inv = np.unique(s, return_inverse=True)
    n = np.bincount(inv).astype(float)
    bad = np.bincount(inv, weights=y)
    prev = np.concatenate([[0.0], np.cumsum(n)[:-1]])
    take = np.clip(k - prev, 0, n)
    return float((take * bad / n).sum() / take.sum())


def compute_metric(name: str, y, score) -> float:
    if name.startswith("bad_rate_at_approval_"):
        return bad_rate_at_approval(y, score, int(name.rsplit("_", 1)[1]) / 100)
    if name == "roc_auc":
        return float(roc_auc_score(y, score))
    if name == "brier":
        return float(brier_score_loss(y, np.clip(score, 0, 1)))
    raise ValueError(f"unknown metric {name!r}: add it to mlkit/core.py, then to the frame")


def all_metrics(spec: dict) -> list[str]:
    return [spec["metric_primary"], *spec.get("metrics_secondary", [])]


def gain(spec: dict, reference: float, candidate: float) -> float:
    """Positive gain = candidate is better, whatever the metric direction."""
    if spec.get("metric_primary_direction", "lower") == "lower":
        return reference - candidate
    return candidate - reference


# ---------------------------------------------------------------- pipelines
def load_pipeline(path: str):
    """A pipeline module defines FEATURES (list[str]) and build() -> estimator."""
    p = (config.ROOT / path).resolve()
    module_spec = importlib.util.spec_from_file_location(f"osml_pipeline_{p.stem}", p)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    if not hasattr(module, "FEATURES") or not hasattr(module, "build"):
        raise SystemExit(f"{path}: a pipeline must define FEATURES and build()")
    return module


def feature_violations(features: list[str], registry: dict) -> list[str]:
    """Invariant I5 on one pipeline: every column registered and usable."""
    problems = []
    for col in features:
        entry = registry.get(col)
        if entry is None:
            problems.append(f"{col}: absent from features.yaml; a human must declare it")
        elif entry.get("available") != "origination":
            problems.append(f"{col}: available '{entry.get('available')}' — later than prediction time")
        elif entry.get("excluded_by"):
            problems.append(f"{col}: exclue par {entry['excluded_by']}")
    return problems


def fit_predict(module, X_train, y_train, X_test) -> np.ndarray:
    return fit_predict_model(module, X_train, y_train, X_test)[0]


def training_sample(X, y, spec: dict | None = None):
    """Rows a pipeline is FITTED on, when the frame caps them (spec.training_sample) : big panels (millions of rows)
    exhaust memory and time, mostly in the majority class. Every fit of the kit goes through here (backtest, null test,
    drift, holdout, package), so the rule is the same everywhere and is part of the frozen frame.

        training_sample: {max_rows: 300000, keep_minority: true, seed: 0}

    keep_minority (default true): every row of the minority class is kept, the rest is drawn at random. The scores
    may rank differently from a model fitted on all rows and are NOT calibrated probabilities: refused with decision_use: probability
    (use keep_minority: false, a uniform draw, in that case). Scoring and evaluation always use ALL rows."""
    if spec is None:
        try:
            spec = config.load_frame().get("spec", {}) or {}
        except Exception:                                   # noqa: BLE001 — no frame: no cap
            spec = {}
    cfg = spec.get("training_sample") or {}
    cap = int(cfg.get("max_rows") or 0)
    if not cap or len(X) <= cap:
        return X, y
    keep_min = bool(cfg.get("keep_minority", True))
    if keep_min and spec.get("evaluation", {}).get("decision_use") == "probability":
        raise SystemExit("training_sample.keep_minority with decision_use: probability would distort probabilities; "
                         "mettre keep_minority: false (tirage uniforme)")
    rng = np.random.default_rng(int(cfg.get("seed", 0)))
    yv = np.asarray(y)
    if keep_min:
        vals, counts = np.unique(yv, return_counts=True)
        if len(vals) != 2:
            raise ValueError("training_sample: deux classes required")
        if counts.min() >= cap:
            raise ValueError("training_sample: max_rows must exceed minority size; set keep_minority=false or raise the cap")
        minority = vals[counts.argmin()]
        keep = np.nonzero(yv == minority)[0]
        rest = np.nonzero(yv != minority)[0]
        pick = rng.choice(rest, max(min(cap - len(keep), len(rest)), 0), replace=False)
        idx = np.sort(np.concatenate([keep, pick]))
    else:
        idx = np.sort(rng.choice(len(yv), cap, replace=False))
    Xs = X.iloc[idx] if hasattr(X, "iloc") else X[idx]
    ys = y.iloc[idx] if hasattr(y, "iloc") else yv[idx]
    return Xs, ys


def fit_predict_model(module, X_train, y_train, X_test):
    model = module.build()
    X_fit, y_fit = training_sample(X_train, y_train)
    model.fit(X_fit, y_fit)
    return model.predict_proba(X_test)[:, 1], model


def _children(model):
    """Estimators nested in `model`: pipeline steps, wrapped estimators, ensembles, transformers."""
    from sklearn.base import BaseEstimator
    get = getattr(model, "get_params", None)
    out = []
    if get is not None:
        for v in get(deep=False).values():
            for it in (v if isinstance(v, (list, tuple)) else [v]):
                if isinstance(it, tuple):
                    it = next((x for x in it if isinstance(x, BaseEstimator)), None)
                if isinstance(it, BaseEstimator):
                    out.append(it)
    # fitted copies live in attributes, not in parameters (calibration wrappers, ensembles)
    for c in getattr(model, "calibrated_classifiers_", None) or []:
        if getattr(c, "estimator", None) is not None:
            out.append(c.estimator)
    for c in getattr(model, "estimators_", None) or []:
        if isinstance(c, BaseEstimator):
            out.append(c)
    return out


def planned_candidates(model) -> int:
    """Candidates a built (unfitted) model WILL compare, known before the run so the budget can be
    checked before spending it (XP1: r-0026 went from 36 to 42 for a budget of 40). Grids nested
    anywhere (pipeline, calibration wrapper, ensemble) are found; nested grids multiply."""
    from sklearn.model_selection import ParameterGrid
    own = len(ParameterGrid(model.param_grid)) if getattr(model, "param_grid", None) is not None else 1
    return own * max((planned_candidates(c) for c in _children(model)), default=1)


def n_candidates(model) -> int:
    """Hyper-parameter candidates compared inside a fitted model (mlkit.tuning), wherever nested."""
    own = int(getattr(model, "n_candidates_", 0) or 0)
    return max([own, *(n_candidates(c) for c in _children(model)), 1])


def code_hash(path: str) -> str:
    """Hash of a pipeline file; a reference declared in the frame is covered by the frame hash."""
    if path.startswith("frame:"):
        return config.frame_hash()
    return config.sha256_file(config.ROOT / path)
