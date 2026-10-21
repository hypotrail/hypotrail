"""Model families and nested cross-validation (v0.3, WP-F1, ADR 0007).

The catalogue and its grids are in :mod:`mlkit.study.trials` (pure); this module fits them.

* :func:`choose`: the hyperparameter of a model chosen by an inner cross-validation of the
  rows a model is fitted on (``trials.INNER_FOLDS`` folds, shuffled with ``trials.INNER_SEED``;
  stratified on a binary target). Each grid value is fitted on the inner training rows (the
  preparation of the variables learnt there too) and scored on the inner held-out rows; the
  best mean wins, a tie keeps the simplest value (the grid lists it first). Called within
  each outer fold, it is nested cross-validation: the outer held-out rows never choose the
  value they are scored with.
* :func:`fit_family`: an Explainable Boosting Machine (``interpret-core``) or a histogram
  gradient boosting model (scikit-learn), seeded, with small fixed settings
  (``trials.EBM_SETTINGS``, ``trials.HGB_SETTINGS``) so a fit stays short.
* :func:`ebm_terms` and :func:`permutation_importance`: each family's own diagnostics, the
  shape function of each feature and the interaction terms of the EBM, and the permutation
  importance of the boosting model on the rows it did not see.

The versions of scikit-learn and interpret-core are part of every family fit's parameters
(:func:`versions`), so a fit made with another version is another result.
"""
from __future__ import annotations

import warnings
from typing import Mapping

from . import trials

MAX_SHAPE_POINTS = 40
MAX_CATEGORY_POINTS = 20
MAX_TERMS = 30
PERMUTATION_REPEATS = 3


def versions(family: str) -> dict:
    """The library versions a family's fit depends on."""
    import sklearn
    out = {'scikit-learn': sklearn.__version__}
    if family == 'ebm':
        import interpret
        out['interpret-core'] = getattr(interpret, '__version__', 'unknown')
    return out


def _score(y, pred, binary: bool) -> float | None:
    import numpy as np
    from . import metrics
    if binary:
        return metrics.roc_auc(np.asarray(y), np.asarray(pred))
    return float(np.mean(np.abs(np.asarray(y, dtype=float) - np.asarray(pred, dtype=float))))


def inner_folds(y, binary: bool, k: int = trials.INNER_FOLDS, seed: int = trials.INNER_SEED):
    """``[(train_positions, test_positions)]`` of the inner cross-validation."""
    import numpy as np
    from sklearn import model_selection as ms
    y = np.asarray(y)
    n = len(y)
    if binary:
        counts = np.bincount(y.astype(int), minlength=2)
        if counts.min() >= k:
            return list(ms.StratifiedKFold(n_splits=k, shuffle=True,
                                           random_state=seed).split(np.zeros(n), y))
    return list(ms.KFold(n_splits=k, shuffle=True, random_state=seed).split(np.zeros(n)))


def choose(case, train, inputs: Mapping, params: Mapping, binary: bool) -> dict:
    """The grid value of ``params['tuning']`` an inner cross-validation of ``train`` picks:
    ``{value, scores: [{value, mean, per_fold}], metric}``."""
    from . import fit
    from .activities import positive
    tuning = params['tuning']
    train = fit._ordered(train)
    y = positive(train, case).to_numpy() if binary else fit._target(case, train, 'training')
    splits = inner_folds(y, binary, int(tuning['inner_folds']), int(tuning['seed']))
    scores = []
    for value in tuning['values']:
        per_fold = []
        for tr, te in splits:
            pred = fit._fit_predict(case, train.iloc[tr], train.iloc[te], inputs,
                                    {**params, 'tuned_value': value}, binary)[0]
            per_fold.append(_score(y[te], pred, binary))
        valid = [s for s in per_fold if s is not None]
        mean = sum(valid) / len(valid) if valid else None
        scores.append({'value': value, 'mean': mean, 'per_fold': per_fold})
    sign = 1 if binary else -1
    best = None
    for s in scores:                      # the grid lists the simplest value first
        if s['mean'] is None:
            continue
        if best is None or sign * s['mean'] > sign * best['mean'] + 1e-12:
            best = s
    chosen = best['value'] if best is not None else tuning['values'][0]
    return {'value': chosen, 'scores': scores, 'metric': tuning['metric']}


# --- the non-linear families ---------------------------------------------------------------

def _split_columns(X):
    from pandas.api.types import is_numeric_dtype
    cats = [c for c in X.columns if not is_numeric_dtype(X[c])]
    nums = [c for c in X.columns if c not in cats]
    return cats, nums


def _as_ebm(X, cats):
    import numpy as np
    X = X.copy()
    for c in X.columns:
        if c in cats:
            X[c] = X[c].map(lambda v: None if v is None or v != v else str(v)).astype(object)
        else:
            X[c] = X[c].astype(float)
    return X


def _as_hgb(X, cats):
    import numpy as np
    X = X.copy()
    for c in cats:
        X[c] = X[c].map(lambda v: np.nan if v is None or v != v else str(v)).astype(object)
    return X


def fit_family(family: str, X_train, y_train, binary: bool, value, seed: int):
    """A fitted model of ``family`` (``ebm`` or ``hgb``) with hyperparameter ``value``,
    on the prepared inputs ``X_train``."""
    import numpy as np
    cats, nums = _split_columns(X_train)
    if family == 'ebm':
        from interpret.glassbox import (ExplainableBoostingClassifier,
                                        ExplainableBoostingRegressor)
        cls = ExplainableBoostingClassifier if binary else ExplainableBoostingRegressor
        model = cls(interactions=int(value), random_state=int(seed), **trials.EBM_SETTINGS)
        with warnings.catch_warnings():
            # interpret warns that its plots do not draw missing values; the engine reads
            # the terms, not the plots.
            warnings.simplefilter('ignore', UserWarning)
            model.fit(_as_ebm(X_train, cats), np.asarray(y_train))
        return model
    if family == 'hgb':
        from sklearn.compose import ColumnTransformer
        from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import OrdinalEncoder
        settings = dict(trials.HGB_SETTINGS)
        max_categories = settings.pop('max_categories_encoded')
        parts = []
        if cats:
            parts.append(('categorical', OrdinalEncoder(
                handle_unknown='use_encoded_value', unknown_value=np.nan,
                encoded_missing_value=np.nan, max_categories=max_categories), cats))
        if nums:
            parts.append(('numeric', 'passthrough', nums))
        prep = ColumnTransformer(parts, verbose_feature_names_out=False)
        cls = HistGradientBoostingClassifier if binary else HistGradientBoostingRegressor
        est = cls(max_depth=int(value), random_state=int(seed),
                  categorical_features=[True] * len(cats) + [False] * len(nums) or None,
                  **settings)
        model = Pipeline([('preprocess', prep), ('model', est)])
        with one_thread():
            model.fit(_as_hgb(X_train, cats), np.asarray(y_train))
        return model
    raise ValueError(f'unknown model family {family!r}')


def one_thread():
    """The OpenMP thread pool limited to one thread while a boosting model fits or predicts:
    the result does not depend on the thread count, and a busy-waiting pool on a shared
    machine cannot stall the fit."""
    from threadpoolctl import threadpool_limits
    return threadpool_limits(limits=1, user_api='openmp')


def predict_family(family: str, model, X, binary: bool):
    import numpy as np
    cats, _ = _split_columns(X)
    Z = _as_ebm(X, cats) if family == 'ebm' else _as_hgb(X, cats)
    with one_thread():
        if binary:
            classes = list(model.classes_)
            return np.asarray(model.predict_proba(Z)[:, classes.index(1)], dtype=float)
        return np.asarray(model.predict(Z), dtype=float)


# --- each family's diagnostics ----------------------------------------------------------------

def ebm_terms(model, binary: bool) -> dict:
    """The terms of a fitted EBM: each feature's shape function (at most
    :data:`MAX_SHAPE_POINTS` points of a continuous one, the :data:`MAX_CATEGORY_POINTS`
    largest of a nominal one) and the pairwise interaction terms, by importance."""
    import numpy as np
    names = [str(n) for n in model.term_names_]
    importance = [float(v) for v in model.term_importances()]
    explanation = model.explain_global()
    terms = []
    for i, name in enumerate(names):
        features = model.term_features_[i]
        item = {'term': name, 'kind': 'main' if len(features) == 1 else 'interaction',
                'importance': importance[i], 'shape': None}
        if len(features) == 1:
            data = explanation.data(i) or {}
            names_, scores_ = data.get('names'), data.get('scores')
            labels = list(names_) if names_ is not None else []
            scores = [float(v) for v in scores_] if scores_ is not None else []
            ftype = model.feature_types_in_[features[0]]
            if ftype == 'continuous' and len(labels) == len(scores) + 1:
                step = max(1, int(np.ceil(len(scores) / MAX_SHAPE_POINTS)))
                points = [{'from': float(labels[j]), 'to': float(labels[min(j + step,
                                                                              len(scores))]),
                           'score': float(np.mean(scores[j:j + step]))}
                          for j in range(0, len(scores), step)]
                item['shape'] = {'type': 'continuous', 'points': points}
            else:
                pairs = sorted(zip(labels, scores), key=lambda p: -abs(float(p[1])))
                item['shape'] = {'type': 'nominal',
                                 'points': [{'value': str(lab), 'score': float(s)}
                                            for lab, s in pairs[:MAX_CATEGORY_POINTS]]}
        terms.append(item)
    terms.sort(key=lambda t: (-t['importance'], t['term']))
    return {'kind': 'ebm_terms', 'terms': terms[:MAX_TERMS], 'n_terms': len(terms),
            'interactions': [t['term'] for t in terms if t['kind'] == 'interaction'],
            'score_scale': ('log-odds added to the intercept' if binary
                            else 'target units added to the intercept'),
            'importance': 'mean absolute contribution of the term over the rows it was fitted '
                          'on',
            'note': 'Shape functions of the EBM fitted on every development row: how the '
                    'model\'s score moves with each feature, the others held as they are. '
                    'Associations, not effects.'}


def permutation_importance(model, X, y, binary: bool, seed: int) -> dict:
    """The drop in the out-of-fold metric when one input column is shuffled (scikit-learn's
    ``permutation_importance``, :data:`PERMUTATION_REPEATS` repeats), by column of ``X``."""
    import numpy as np
    from sklearn.inspection import permutation_importance as pi
    cats, _ = _split_columns(X)
    Z = _as_hgb(X, cats)
    scoring = 'roc_auc' if binary else 'neg_mean_absolute_error'
    if binary and len(set(np.asarray(y).tolist())) < 2:
        return {}
    with one_thread():
        res = pi(model, Z, np.asarray(y), scoring=scoring, n_repeats=PERMUTATION_REPEATS,
                 random_state=int(seed), n_jobs=1)
    return {str(c): float(m) for c, m in zip(X.columns, res.importances_mean)}


def combine_importance(per_fold: list[tuple[int, dict]], binary: bool) -> dict:
    """The permutation importances of the folds, weighted by their rows."""
    total = sum(n for n, imp in per_fold if imp)
    columns: list[str] = []
    for _, imp in per_fold:
        for c in imp:
            if c not in columns:
                columns.append(c)
    rows = []
    for c in columns:
        value = sum(n * imp.get(c, 0.0) for n, imp in per_fold if imp) / total if total else None
        rows.append({'column': c, 'importance': value,
                     'per_fold': [imp.get(c) for _, imp in per_fold]})
    rows.sort(key=lambda r: (-(r['importance'] or 0.0), r['column']))
    return {'kind': 'permutation_importance', 'columns': rows,
            'metric': 'roc_auc' if binary else 'mae',
            'repeats': PERMUTATION_REPEATS,
            'definition': ('drop in the out-of-fold ROC AUC when the column is shuffled' if binary
                           else 'increase in the out-of-fold MAE when the column is shuffled'),
            'note': 'Measured, fold by fold, on the rows each fold\'s model did not see, and '
                    'weighted by the rows of each fold. A column the model leans on loses '
                    'more when shuffled; correlated columns share their importance.'}
