"""AutoGluon wrapped as a scikit-learn classifier, for the `autogluon` baseline (mlkit.baselines).

Why: on tabular benchmarks (AMLB, JMLR 2024; SELA 2024) an AutoML system that builds ensembles is
not reliably beaten by LLM agents. One AutoGluon run is a cheap, strong reference that enters the
final rank average like any other exploratory run.

Contract (the runner sees an ordinary estimator: fit / predict_proba / classes_):
- fit(X, y) learns ONLY on the rows it is given (the training rows of one backtest window);
  AutoGluon's internal validation (holdout or bagging, depending on `presets`) is drawn from them,
  never from the test window. No tuning on the test windows.
- time_limit (seconds per fit) and presets are fixed in the frame (spec.baselines_autogluon) and
  written into the generated pipeline file: they are covered by its code hash.
- seeds fixed (AutoGluon splits with random_state 42, models with seed 0 by default; we set them
  explicitly), verbosity 0. A time budget still makes the result depend on machine speed: two runs
  on two machines may train a different number of models. That is AutoGluon's nature, not a bug.
- models are written to a temporary directory, deleted when the estimator is garbage collected
  (weakref.finalize) or at interpreter exit. Pickling (mlkit.package) stores the directory's content
  inside the pickle, so the packaged model does not depend on a temporary path.
- the estimator is ONE candidate for the budget (no param_grid, no n_candidates_): AutoGluon's own
  internal model selection is part of the method, like the inner early stopping of a boosting.
"""
from __future__ import annotations

import io
import shutil
import tarfile
import tempfile
import weakref

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin

LABEL = "__osml_target__"


def autogluon_problem() -> str | None:
    """None if autogluon.tabular can be imported here; otherwise why not."""
    try:
        from autogluon.tabular import TabularPredictor  # noqa: F401
    except Exception as exc:          # ImportError, or a broken dependency (pandas, numpy, ...)
        return (f"autogluon.tabular cannot be imported ({type(exc).__name__}: {exc}) ; "
                "pip install 'autogluon.tabular[lightgbm,catboost,xgboost]==1.6.3' "
                "(requires pandas < 2.4: use a separate environment; see README)")
    return None


def autogluon_version() -> str:
    try:
        from importlib.metadata import version
        return version("autogluon.tabular")
    except Exception:
        return "absent"


def _without_torch() -> list[str]:
    """Neural models need torch (the `fastai` extra, several GB): without it they are left out explicitly
    instead of failing one by one with a warning. Trees, boostings, linear and kNN models remain."""
    try:
        import torch  # noqa: F401
        return []
    except ImportError:
        return ["NN_TORCH", "FASTAI"]


class AutoGluonClassifier(ClassifierMixin, BaseEstimator):
    def __init__(self, time_limit: int = 120, presets: str = "medium_quality", eval_metric: str = "roc_auc",
                 seed: int = 0, num_cpus="auto"):
        self.time_limit = time_limit
        self.presets = presets
        self.eval_metric = eval_metric
        self.seed = seed
        self.num_cpus = num_cpus

    # ------------------------------------------------------------ temporary directory
    def _new_dir(self) -> str:
        path = tempfile.mkdtemp(prefix="osml-autogluon-")
        self._cleanup = weakref.finalize(self, shutil.rmtree, path, True)
        return path

    def _drop_dir(self) -> None:
        cleanup = getattr(self, "_cleanup", None)
        if cleanup is not None:
            cleanup()

    # ------------------------------------------------------------ sklearn API
    def fit(self, X, y):
        import logging
        from autogluon.tabular import TabularPredictor
        # GPU detection imports torch and logs an error at level 40 when it is absent (verbosity does not cover it)
        logging.getLogger("autogluon.common.utils.resource_utils").setLevel(logging.CRITICAL)
        X = pd.DataFrame(X).reset_index(drop=True)
        if LABEL in X.columns:
            raise ValueError(f"reserved column {LABEL!r} present in X")
        y = np.asarray(y).astype(int)
        self.classes_ = np.array([0, 1])
        self.feature_names_in_ = np.asarray(X.columns, dtype=object)
        self._drop_dir()
        path = self._new_dir()
        np.random.seed(self.seed)
        train = X.assign(**{LABEL: y})
        self.predictor_ = TabularPredictor(label=LABEL, problem_type="binary", eval_metric=self.eval_metric,
                                           path=path, verbosity=0).fit(
            train, time_limit=self.time_limit, presets=self.presets, num_cpus=self.num_cpus, num_gpus=0,
            excluded_model_types=_without_torch(), ag_args_fit={"random_seed": self.seed})
        positive = self.predictor_.positive_class
        if positive != 1:
            raise RuntimeError(f"classe positive AutoGluon = {positive!r}, expected 1")
        self.model_best_ = self.predictor_.model_best
        return self

    def predict_proba(self, X):
        X = pd.DataFrame(X)[list(self.feature_names_in_)].reset_index(drop=True)
        p = self.predictor_.predict_proba(X, as_multiclass=False).to_numpy(dtype=float)
        return np.column_stack([1 - p, p])

    def predict(self, X):
        return (self.predict_proba(X)[:, 1] > 0.5).astype(int)

    # ------------------------------------------------------------ pickling (mlkit.package)
    def __getstate__(self):
        state = {k: v for k, v in self.__dict__.items() if k not in ("predictor_", "_cleanup")}
        if "predictor_" in self.__dict__:
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as tar:
                tar.add(self.predictor_.path, arcname="predictor")
            state["_archive"] = buf.getvalue()
        return state

    def __setstate__(self, state):
        archive = state.pop("_archive", None)
        self.__dict__.update(state)
        if archive is not None:
            from autogluon.tabular import TabularPredictor
            path = self._new_dir()
            with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
                tar.extractall(path, filter="data")
            self.predictor_ = TabularPredictor.load(f"{path}/predictor", verbosity=0, require_py_version_match=False)
