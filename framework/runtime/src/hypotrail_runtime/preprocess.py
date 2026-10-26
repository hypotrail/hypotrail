"""The engine's preparation of the model inputs as one fitted scikit-learn step (spec L-08).

Before v1 the study engine prepared the inputs outside the scikit-learn pipeline
(:func:`mlkit.study.fit.design` and :func:`mlkit.study.fit.prepare`) and fitted only the
imputation, scaling, encoding and estimator inside it, so a fitted pipeline alone could not
predict raw rows. :class:`HypotrailPreparation` carries that preparation, with the same
rules, in the same order, learnt on the rows it is fitted on only:

1. ``category_as_text``: a column declared as a category whose values are numbers (or a
   boolean column) is read as text (``str`` of each value, missing stays missing);
2. ``special_value_indicator``: a numeric special value gets the indicator column
   ``<column>=<value>`` and is masked as missing (a value the case reads as missing marks
   the missing cells);
3. ``missing_indicator``: ``<column>=(missing)`` for a candidate feature whose *training*
   cells hold a missing value (learnt at fit; never added from the rows predicted);
4. ``rare_category``: categories with fewer training rows than ``min_rows`` (and any
   category unseen in training) become ``(rare)``; version 1 applies one minimum to every
   categorical column, version 2 (owner session 2026-10-26, L8, R6) one per column
   (``{column: min_rows}``; a column it leaves out keeps every category);
5. ``cap_quantiles``: values clipped to the training quantiles;
6. ``signed_log``: ``sign(x) * log(1 + |x|)``, after the caps.

Then :func:`build_pipeline` adds the engine's ``mlkit.classical.pipeline`` steps: median
imputation and standardisation of the numeric columns, most-frequent imputation and one-hot
encoding (unknown categories ignored) of the others, and the estimator. ``transform``
never mutates its input and keeps the row order.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin

RARE_GROUP = '(rare)'
MISSING_SUFFIX = '=(missing)'
# The versions of each preprocessing operation this runtime reads (owner session 2026-10-26,
# L8, R6): ``rare_category`` version 2 holds one minimum per column (``min_rows``:
# ``{column: n}``, n >= 1); version 1 one minimum for every categorical column (n >= 0).
# Checked when the preparation is built (:func:`preparation_from_recipe`), so the contracts
# module, which other activities fingerprint, is unchanged.
OPERATION_VERSIONS = {name: (1,) for name in (
    'category_as_text', 'special_value_indicator', 'missing_indicator', 'cap_quantiles',
    'signed_log', 'numeric_median_impute_scale', 'categorical_mode_impute_onehot')}
OPERATION_VERSIONS['rare_category'] = (1, 2)


def _nan_like(value: Any) -> bool:
    """NaN, or pandas' NA/NaT, which the engine's test ``v != v`` reads as missing for NaN
    but cannot evaluate for ``pd.NA`` (its comparison is not a boolean). ``None`` keeps the
    engine's reading (``None != None`` is false), so the engine's fit is reproduced."""
    if value is pd.NA or value is pd.NaT:
        return True
    return isinstance(value, float) and value != value


def _matches(series: pd.Series, value: Any, reads_missing: bool) -> pd.Series:
    """The engine's ``activities.matches`` for a numeric column."""
    from pandas.api.types import is_numeric_dtype
    if reads_missing:
        return series.isna()
    if isinstance(value, (int, float)) and not isinstance(value, bool) \
            and is_numeric_dtype(series):
        return series == value
    return series.astype(str) == str(value)


class HypotrailPreparation(TransformerMixin, BaseEstimator):
    """Steps 1–6 above. Parameters are the recipe's declarations; learnt state ends with
    ``_``."""

    def __init__(self, features: Sequence[str] = (), text_columns: Sequence[str] = (),
                 special_values: Sequence[Mapping] = (),
                 missing_candidates: Sequence[str] = (),
                 rare_min_rows: int | Mapping[str, int] = 0,
                 caps: Mapping[str, Sequence[float]] | None = None,
                 log_columns: Sequence[str] = ()):
        self.features = features
        self.text_columns = text_columns
        self.special_values = special_values
        self.missing_candidates = missing_candidates
        self.rare_min_rows = rare_min_rows
        self.caps = caps
        self.log_columns = log_columns

    # -- the design step (stateless) -------------------------------------------------------
    def _design(self, frame: pd.DataFrame) -> pd.DataFrame:
        X = frame[list(self.features)].copy()
        for name in self.text_columns:
            X[name] = X[name].map(lambda v: None if _nan_like(v) else str(v)).astype(object)
        for s in self.special_values:
            column = s['column']
            mask = _matches(frame[column], s['value'], bool(s.get('reads_missing')))
            X[s['name']] = mask.astype(int)
            X[column] = X[column].mask(mask)
        return X

    def fit(self, X: pd.DataFrame, y=None):
        from pandas.api.types import is_numeric_dtype
        self._check_frame(X)
        design = self._design(X)
        self.missing_indicators_ = [c for c in self.missing_candidates if X[c].isna().any()]
        for c in self.missing_indicators_:
            design[c + MISSING_SUFFIX] = X[c].isna().astype(int).to_numpy()
        self.rare_kept_ = {}
        self.rare_folded_ = {}
        for column in self.features:
            # L8 (R6): one minimum for every column (version 1) or each column's own (2).
            k = self._rare_rows(column)
            if k > 0:
                if is_numeric_dtype(design[column]):
                    continue
                counts = design[column].dropna().astype(str).value_counts()
                kept = sorted(counts[counts >= k].index)
                self.rare_kept_[column] = kept
                self.rare_folded_[column] = sorted(set(counts.index) - set(kept))
                design[column] = self._fold(design[column], set(kept))
        self.cap_bounds_ = {}
        for column, (q_low, q_high) in sorted((self.caps or {}).items()):
            low = float(design[column].quantile(q_low))
            high = float(design[column].quantile(q_high))
            self.cap_bounds_[column] = [low, high]
        self.columns_out_ = list(design.columns)
        self.n_features_in_ = len(self.features)
        self.feature_names_in_ = np.asarray(list(self.features), dtype=object)
        return self

    def _rare_rows(self, column: str) -> int:
        k = self.rare_min_rows
        if isinstance(k, Mapping):
            return int(k.get(column, 0) or 0)
        return int(k or 0)

    @staticmethod
    def _fold(series: pd.Series, kept: set) -> pd.Series:
        text = series.map(lambda v: np.nan if _nan_like(v) else str(v))
        return text.where(text.isna() | text.isin(kept), RARE_GROUP)

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        self._check_frame(X)
        out = self._design(X)
        for c in self.missing_indicators_:
            out[c + MISSING_SUFFIX] = X[c].isna().astype(int).to_numpy()
        for column, kept in self.rare_kept_.items():
            out[column] = self._fold(out[column], set(kept))
        for column, (low, high) in self.cap_bounds_.items():
            out[column] = out[column].clip(low, high)
        for column in self.log_columns:
            v = out[column].astype(float)
            out[column] = np.sign(v) * np.log1p(np.abs(v))
        return out[self.columns_out_]

    def _check_frame(self, X) -> None:
        if not isinstance(X, pd.DataFrame):
            raise TypeError('HypotrailPreparation reads a pandas DataFrame of raw features')
        missing = [c for c in self.features if c not in X.columns]
        if missing:
            raise KeyError(f'missing feature columns: {missing}')

    def get_feature_names_out(self, input_features=None):
        return np.asarray(self.columns_out_, dtype=object)

    def learnt_state(self) -> dict:
        """The learnt state as JSON (shown in the manifest's extensions; the payload holds
        the authoritative object)."""
        return {'missing_indicators': [c + MISSING_SUFFIX for c in self.missing_indicators_],
                'rare_categories': {c: {'kept': len(k), 'folded': self.rare_folded_[c]}
                                    for c, k in self.rare_kept_.items()},
                'caps': {c: list(b) for c, b in self.cap_bounds_.items()},
                'log_transform': list(self.log_columns),
                'columns_out': list(self.columns_out_)}


def _whole(value, minimum: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def operation_issues(recipe) -> list[dict]:
    """L8 (R6): the steps whose version this runtime does not read, and a ``rare_category``
    whose ``min_rows`` does not fit its version (a whole number >= 0 in version 1, a
    non-empty mapping of features to whole numbers >= 1 in version 2)."""
    issues = []
    for step in recipe.preprocessing:
        path = f'preprocessing/{step.operation}'
        supported = OPERATION_VERSIONS.get(step.operation, (1,))
        if step.version not in supported:
            issues.append({'path': path, 'message': f'version {step.version} of '
                                                    f'{step.operation} is not supported (this '
                                                    f'runtime reads {list(supported)})'})
            continue
        if step.operation != 'rare_category':
            continue
        rows = step.parameters.get('min_rows')
        if step.version == 1 and not _whole(rows, 0):
            issues.append({'path': path, 'message': 'min_rows of version 1 is a whole number '
                                                    '>= 0'})
        elif step.version == 2:
            if not (isinstance(rows, Mapping) and rows
                    and all(_whole(n, 1) for n in rows.values())):
                issues.append({'path': path, 'message': 'min_rows of version 2 maps columns '
                                                        'to whole numbers >= 1'})
            else:
                issues += [{'path': path, 'message': f'{column!r} is not a feature'}
                           for column in rows if column not in recipe.features]
    return issues


def preparation_from_recipe(recipe) -> HypotrailPreparation:
    """The unfitted preparation the recipe declares (operations in the engine's order).
    A step this runtime does not read is refused (``contract_invalid``, L8)."""
    issues = operation_issues(recipe)
    if issues:
        from .errors import ContractError
        raise ContractError(
            'contract_invalid', f'hypotrail.model_recipe/1: {issues[0]["message"]} at '
            f'{issues[0]["path"]}', path=issues[0]['path'],
            remediation='Use a runtime that reads this operation version, or export the '
                        'recipe again from the engine that wrote it.',
            issues=[{'code': 'contract_invalid', **i} for i in issues])
    params = {s.operation: dict(s.parameters) for s in recipe.preprocessing}
    versions = {s.operation: s.version for s in recipe.preprocessing}
    special = params.get('special_value_indicator', {}).get('values') or []
    rare = params.get('rare_category', {}).get('min_rows')
    if versions.get('rare_category') == 2:
        # L8 (R6): one minimum per column.
        rare_min_rows: int | dict = {str(c): int(n) for c, n in dict(rare or {}).items()}
    else:
        rare_min_rows = int(rare or 0)
    return HypotrailPreparation(
        features=list(recipe.features),
        text_columns=list(params.get('category_as_text', {}).get('columns') or []),
        special_values=[dict(v) for v in special],
        missing_candidates=list(params.get('missing_indicator', {}).get('columns') or []),
        rare_min_rows=rare_min_rows,
        caps={c: [float(q[0]), float(q[1])] for c, q in
              (params.get('cap_quantiles', {}).get('quantiles') or {}).items()},
        log_columns=list(params.get('signed_log', {}).get('columns') or []))


def build_pipeline(recipe):
    """The complete unfitted pipeline of a recipe: preparation, imputation/scaling/encoding
    (``mlkit.classical.pipeline``), estimator."""
    from sklearn.compose import ColumnTransformer, make_column_selector
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler
    from . import families
    prep = ColumnTransformer([
        ('num', Pipeline([('impute', SimpleImputer(strategy='median', keep_empty_features=True)),
                          ('scale', StandardScaler())]),
         make_column_selector(dtype_include='number')),
        ('cat', Pipeline([('impute', SimpleImputer(strategy='most_frequent',
                                                   keep_empty_features=True)),
                          ('encode', OneHotEncoder(handle_unknown='ignore',
                                                   sparse_output=False))]),
         make_column_selector(dtype_exclude='number'))])
    return Pipeline([('prepare', preparation_from_recipe(recipe)), ('preprocess', prep),
                     ('model', families.estimator(recipe.family, recipe.parameters,
                                                  recipe.seeds))])
