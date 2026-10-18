"""Supervised feature selection INSIDE the pipeline, so it is refitted in every backtest window.

    from mlkit.selection import SupervisedSelector
    def build():
        return make_pipeline(preprocess, SupervisedSelector(method="l1", C=0.05), model)

Selecting features on all of data/dev, then backtesting a model on the survivors, leaks
the validation windows into the choice of features (the largest leak measured in the
literature on tabular pipelines). Here the selector only ever sees the training rows of
each window, like any other fitted step.

Comparing several selector settings is a comparison like any other: put them in a
mlkit.tuning.TimeAwareSearch grid, which counts every candidate in the exploration budget.

Expects a numeric matrix: put it after imputation / encoding.
"""
from __future__ import annotations

import warnings

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.feature_selection import mutual_info_classif
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler


class SupervisedSelector(TransformerMixin, BaseEstimator):
    def __init__(self, method: str = "l1", k: int = 10, C: float = 0.05, random_state: int = 0):
        self.method = method
        self.k = k
        self.C = C
        self.random_state = random_state

    def fit(self, X, y):
        X = np.asarray(X, dtype=float)
        if self.method == "mi":
            score = mutual_info_classif(np.nan_to_num(X), y, random_state=self.random_state)
            keep = np.argsort(-score)[: min(self.k, X.shape[1])]
            self.support_ = np.zeros(X.shape[1], dtype=bool)
            self.support_[keep] = True
        elif self.method == "l1":
            z = StandardScaler().fit_transform(np.nan_to_num(X))
            lr = LogisticRegression(penalty="l1", solver="liblinear", C=self.C, random_state=self.random_state)
            with warnings.catch_warnings():          # 'penalty' is deprecated in recent scikit-learn
                warnings.simplefilter("ignore")
                lr.fit(z, y)
            self.support_ = np.abs(lr.coef_[0]) > 1e-8
            if not self.support_.any():                      # keep at least the strongest column
                self.support_[np.argmax(np.abs(lr.coef_[0]))] = True
        else:
            raise ValueError(f"unknown method: {self.method!r} (mi | l1)")
        self.n_features_in_ = X.shape[1]
        return self

    def transform(self, X):
        return np.asarray(X, dtype=float)[:, self.support_]
