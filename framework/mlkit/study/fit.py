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
    """Model inputs: the features, numeric special values as indicators then missing."""
    from pandas.api.types import is_numeric_dtype
    from .activities import matches
    X = frame[features].copy()
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


def compute(activity: str, case: c.Case, train, validation, inputs: Mapping,
            params: Mapping) -> dict:
    if activity == 'fit.baseline':
        return baseline(case, train, validation)
    return logistic(case, train, validation, inputs, params)
