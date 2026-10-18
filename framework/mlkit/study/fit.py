"""Model fits with persisted validation predictions (plan WP2.3, §3.4).

* ``fit.baseline``: a constant score equal to the training positive rate (the prior).
  No feature and no scikit-learn: it is the reference every model must beat.
* ``fit.logistic``: ``mlkit.classical.pipeline('logistic', ...)``, fitted on training
  rows only (imputation, scaling, and encoding are learnt there). The features are
  those whose availability decision is ``available_at_prediction`` or
  ``uncertain_included``; ``activities.plan`` refuses to run while a candidate
  feature has no availability decision. A numeric special value (a sentinel such as
  "-1 means never") gets an indicator column ``<column>=<value>`` and is imputed
  rather than read as a magnitude; a categorical special value stays its own
  category, which one-hot encoding already turns into an indicator.

Each fit scores the validation rows and stores them as the ``predictions`` blob:
gzip-compressed CSV with header ``row_key,y,score`` (``y`` is 1 for the positive
label), deterministic bytes (gzip ``mtime=0``, scores written with ``repr``). The
registry entry records the exposure ``train_fit`` and ``validation_model_evaluation``.

Scores are ranking scores: their calibration as probabilities is not assessed.
``HYPOTRAIL_READ_ONLY=1`` makes every fit refuse (``read_only``).

A regression study (numeric target, M3) has two fits with the same rules:

* ``fit.baseline``: every row receives the training mean of the target (the training
  median is reported next to it). No feature, no scikit-learn.
* ``fit.linear``: an ordinary least-squares linear regression in the same pipeline
  machinery (``mlkit.classical.pipeline``: median imputation and standardisation of
  numeric features, most-frequent imputation and one-hot encoding of categorical ones,
  all fitted on training rows), with the same special-value indicators.

Their ``predictions`` blob is ``row_key,y,prediction`` (``y`` in the target unit). A
missing target value is refused (``unsupported_capability``): this version neither
drops nor imputes target rows silently.
"""
from __future__ import annotations

import gzip
from typing import Mapping

from . import case as c
from . import metrics

SCORE_SEMANTICS = ('Higher means more likely positive. Calibration as a probability is not '
                   'assessed.')


def predictions_blob(row_keys, y, score) -> bytes:
    """Deterministic gzip CSV ``row_key,y,score``."""
    lines = ['row_key,y,score']
    for key, label, value in zip(row_keys, y, score):
        lines.append(f'{key},{int(label)},{float(value)!r}')
    return gzip.compress(('\n'.join(lines) + '\n').encode('utf-8'), mtime=0)


def _ordered(frame):
    """Rows in file order (row key line number), so predictions have a stable order."""
    return frame.loc[sorted(frame.index, key=lambda k: int(k[1:]))]


def _validation_summary(y, score) -> dict:
    return {'n_rows': int(len(y)), 'n_positive': int(sum(y)),
            'roc_auc': metrics.roc_auc(y, score),
            'average_precision': metrics.average_precision(y, score)}


def _predictions_meta(case: c.Case, model: str, features: list, y) -> dict:
    return {'blob': 'predictions', 'format': 'gzip csv row_key,y,score', 'model': model,
            'partition': 'validation', 'positive_label': case.positive_label,
            'score_semantics': SCORE_SEMANTICS, 'n': int(len(y)), 'n_positive': int(sum(y)),
            'features': list(features)}


def baseline(case: c.Case, train, validation) -> dict:
    from .activities import guard_read_only, positive
    guard_read_only()
    train, validation = _ordered(train), _ordered(validation)
    y_train = positive(train, case)
    rate = float(y_train.mean())
    y_val = positive(validation, case).to_numpy()
    score = [rate] * len(validation)
    values = {'model': 'constant_prior', 'train_rate': rate, 'n_train': int(len(train)),
              'n_train_positive': int(y_train.sum()), 'features': [],
              'validation': _validation_summary(y_val, score),
              'predictions': _predictions_meta(case, 'constant_prior', [], y_val),
              'note': 'Every row receives the training positive rate: no ranking information.'}
    return {'values': values,
            'blobs': {'predictions': predictions_blob(validation.index, y_val, score)},
            'partition': 'validation', 'n_rows': int(len(validation))}


def design(frame, features: list, special: list, case: c.Case):
    """Model inputs: the features, numeric special values as indicators then missing.

    A feature the case declares as a ``category`` but whose codes are numbers (``origin``
    coded 1, 2, 3) is read as text, so it is one-hot encoded rather than taken as a
    magnitude."""
    from pandas.api.types import is_numeric_dtype
    from .activities import matches
    X = frame[features].copy()
    for name in features:
        if case.variables[name]['type'] == 'category' and is_numeric_dtype(X[name]):
            X[name] = X[name].map(lambda v: None if v != v else str(v)).astype(object)
    na_values = case.dataset.get('na_values', ())
    indicators = []
    for s in special:
        column, value = s['column'], s['value']
        if not is_numeric_dtype(frame[column]):
            continue
        mask = matches(frame[column], value, na_values)
        name = f'{column}={value}'
        X[name] = mask.astype(int)
        X[column] = X[column].mask(mask)
        indicators.append(name)
    return X, indicators


def logistic(case: c.Case, train, validation, inputs: Mapping, params: Mapping) -> dict:
    from .activities import guard_read_only, positive
    guard_read_only()
    from mlkit import classical

    train, validation = _ordered(train), _ordered(validation)
    features, special = list(inputs['features']), list(inputs['special_values'])
    X_train, indicators = design(train, features, special, case)
    X_val, _ = design(validation, features, special, case)
    y_train = positive(train, case)
    spec = {'task': {'kind': 'binary'}, 'model_options': {}}
    model = classical.pipeline('logistic', X_train, spec, params['seed'])
    model.fit(X_train, y_train.to_numpy())
    classes = list(model.classes_)
    score = model.predict_proba(X_val)[:, classes.index(1)]
    y_val = positive(validation, case).to_numpy()
    names = [str(n) for n in model['preprocess'].get_feature_names_out()]
    coef = model['model'].coef_[0]
    values = {'model': 'logistic', 'features': features, 'special_value_indicators': indicators,
              'n_train': int(len(train)), 'n_train_positive': int(y_train.sum()),
              'n_terms': len(names), 'intercept': float(model['model'].intercept_[0]),
              'coefficients': {n: float(v) for n, v in zip(names, coef)},
              'coefficient_scale': 'per standard deviation of the training rows (numeric) or '
                                   'per category (one-hot); associations, not effects',
              'iterations': int(model['model'].n_iter_[0]),
              'validation': _validation_summary(y_val, score),
              'predictions': _predictions_meta(case, 'logistic', features, y_val)}
    return {'values': values,
            'blobs': {'predictions': predictions_blob(validation.index, y_val, score)},
            'partition': 'validation', 'n_rows': int(len(validation))}


# --- regression ---------------------------------------------------------------------------

PREDICTION_SEMANTICS = 'A prediction of the target, in its unit.'


def regression_blob(row_keys, y, prediction) -> bytes:
    """Deterministic gzip CSV ``row_key,y,prediction``."""
    lines = ['row_key,y,prediction']
    for key, value, pred in zip(row_keys, y, prediction):
        lines.append(f'{key},{float(value)!r},{float(pred)!r}')
    return gzip.compress(('\n'.join(lines) + '\n').encode('utf-8'), mtime=0)


def _target(case: c.Case, frame, partition: str):
    from .eda import numeric_target
    from .errors import StudyError
    y = numeric_target(case, frame)
    missing = int(y.isna().sum())
    if missing:
        raise StudyError('unsupported_capability',
                         f'{missing} {partition} rows have no target value; this version neither '
                         f'drops nor imputes target rows.',
                         details={'reasons': [{'code': 'unsupported_capability',
                                               'capability': 'missing target values (v0.2)',
                                               'partition': partition, 'rows': missing}]})
    return y.to_numpy(dtype=float)


def _regression_meta(case: c.Case, model: str, features: list, y) -> dict:
    return {'blob': 'predictions', 'format': 'gzip csv row_key,y,prediction', 'model': model,
            'partition': 'validation', 'target': case.target_column, 'unit': case.target_unit,
            'prediction_semantics': PREDICTION_SEMANTICS, 'n': int(len(y)),
            'features': list(features)}


def _errors(y, prediction) -> dict:
    from . import regression
    e = regression.errors(y, prediction)
    return {'n_rows': e['n'], 'mae': e['mae'], 'rmse': e['rmse'],
            'mean_residual': e['mean_residual']}


def mean_baseline(case: c.Case, train, validation) -> dict:
    import numpy as np
    from .activities import guard_read_only
    guard_read_only()
    train, validation = _ordered(train), _ordered(validation)
    y_train = _target(case, train, 'training')
    y_val = _target(case, validation, 'validation')
    mean = float(y_train.mean())
    prediction = np.full(len(y_val), mean)
    values = {'model': 'train_mean', 'target': case.target_column, 'unit': case.target_unit,
              'train_mean': mean, 'train_median': float(np.median(y_train)),
              'n_train': int(len(train)), 'features': [],
              'train': _errors(y_train, np.full(len(y_train), mean)),
              'validation': _errors(y_val, prediction),
              'predictions': _regression_meta(case, 'train_mean', [], y_val),
              'note': 'Every row receives the training mean: the reference a model must beat.'}
    return {'values': values,
            'blobs': {'predictions': regression_blob(validation.index, y_val, prediction)},
            'partition': 'validation', 'n_rows': int(len(validation))}


def linear(case: c.Case, train, validation, inputs: Mapping, params: Mapping) -> dict:
    from .activities import guard_read_only
    guard_read_only()
    from sklearn.linear_model import LinearRegression
    from mlkit import classical

    train, validation = _ordered(train), _ordered(validation)
    features, special = list(inputs['features']), list(inputs['special_values'])
    X_train, indicators = design(train, features, special, case)
    X_val, _ = design(validation, features, special, case)
    y_train = _target(case, train, 'training')
    y_val = _target(case, validation, 'validation')
    spec = {'task': {'kind': 'regression'}, 'model_options': {}}
    model = classical.pipeline('ridge', X_train, spec, params['seed'])
    model.set_params(model=LinearRegression())
    model.fit(X_train, y_train)
    prediction = model.predict(X_val)
    names = [str(n) for n in model['preprocess'].get_feature_names_out()]
    coef = model['model'].coef_
    values = {'model': 'linear', 'target': case.target_column, 'unit': case.target_unit,
              'features': features, 'special_value_indicators': indicators,
              'n_train': int(len(train)), 'n_terms': len(names),
              'intercept': float(model['model'].intercept_),
              'coefficients': {n: float(v) for n, v in zip(names, coef)},
              'coefficient_scale': 'target units per standard deviation of the training rows '
                                   '(numeric) or per category (one-hot, not identifiable one by '
                                   'one); associations, not effects',
              'train': _errors(y_train, model.predict(X_train)),
              'validation': _errors(y_val, prediction),
              'predictions': _regression_meta(case, 'linear', features, y_val)}
    return {'values': values,
            'blobs': {'predictions': regression_blob(validation.index, y_val, prediction)},
            'partition': 'validation', 'n_rows': int(len(validation))}


def compute(activity: str, case: c.Case, train, validation, inputs: Mapping,
            params: Mapping) -> dict:
    if case.task == 'regression':
        if activity == 'fit.baseline':
            return mean_baseline(case, train, validation)
        return linear(case, train, validation, inputs, params)
    if activity == 'fit.baseline':
        return baseline(case, train, validation)
    return logistic(case, train, validation, inputs, params)

