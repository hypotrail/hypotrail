"""Time-aware hyper-parameter search, usable inside a pipeline's build().

    from mlkit.tuning import TimeAwareSearch
    def build():
        return TimeAwareSearch(make_pipeline(...), {"histgradientboostingclassifier__max_depth": [3, 5]})

Why a wrapper instead of GridSearchCV:
- the inner folds respect time (rows arrive sorted by issue month from the runner):
  each inner validation fold comes after its training fold, like the outer backtest;
- the number of candidates compared is exposed (n_candidates_) and counted by the
  runner in the exploration budget: a grid of 20 points is 20 comparisons, not one.
Raw GridSearchCV / RandomizedSearchCV are refused by the checks in model/*.py.
"""
from __future__ import annotations

from sklearn.base import BaseEstimator, ClassifierMixin, clone
from sklearn.model_selection import GridSearchCV, ParameterGrid, TimeSeriesSplit


class TimeAwareSearch(ClassifierMixin, BaseEstimator):
    def __init__(self, estimator, param_grid, n_splits: int = 3, scoring: str = "roc_auc"):
        self.estimator = estimator
        self.param_grid = param_grid
        self.n_splits = n_splits
        self.scoring = scoring

    def fit(self, X, y):
        self.n_candidates_ = len(ParameterGrid(self.param_grid))
        search = GridSearchCV(clone(self.estimator), self.param_grid, cv=TimeSeriesSplit(self.n_splits),
                              scoring=self.scoring, refit=True)
        search.fit(X, y)
        self.best_params_ = search.best_params_
        self.best_estimator_ = search.best_estimator_
        self.classes_ = search.best_estimator_.classes_
        return self

    def predict_proba(self, X):
        return self.best_estimator_.predict_proba(X)

    def predict(self, X):
        return self.best_estimator_.predict(X)
