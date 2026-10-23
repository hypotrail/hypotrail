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
    magnitude. A column pandas reads as booleans (``TRUE``/``FALSE`` in the file, v0.2b) is
    read as text too, ``True``/``False``, like any other two-valued category."""
    from pandas.api.types import is_bool_dtype, is_numeric_dtype
    from .activities import matches
    X = frame[features].copy()
    for name in features:
        if is_bool_dtype(X[name]) or (case.variables[name]['type'] == 'category'
                                      and is_numeric_dtype(X[name])):
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


def prepare(case: c.Case, train, validation, X_train, X_val, features: list,
            preprocessing: Mapping | None, special: list = ()):
    """Apply the confirmed ``preprocessing`` decision (v0.2a, WP-A4) to the model inputs.

    Every parameter is learnt on the training rows only and applied unchanged to the
    validation rows: the missing-value indicators (``<column>=(missing)``, added for a
    feature whose training cells hold a missing value, unless a declared special value that
    the case reads as missing already gives it an indicator), the minimum rows of a category (categories with fewer
    training rows are grouped as ``(rare)``, and a validation category unseen in training
    too), the caps (training quantiles; values outside are clipped), and the signed log
    transform ``sign(x) * log(1 + |x|)``, after the caps. A parameter naming a feature the
    model does not use is listed in ``ignored``. Returns ``(X_train, X_val, fitted)``;
    ``fitted`` is None when there is no decision (a study created before WP-A4), and the
    inputs are then unchanged. The default value changes nothing."""
    if preprocessing is None:
        return X_train, X_val, None
    import numpy as np
    from pandas.api.types import is_numeric_dtype
    from . import governance

    X_train, X_val = X_train.copy(), X_val.copy()
    fitted = {'missing_indicators': [], 'rare_categories': {}, 'caps': {}, 'log_transform': [],
              'ignored': []}
    used = set(features)
    named = set(preprocessing['caps']) | set(preprocessing['log_transform'])
    if isinstance(preprocessing['missing'], Mapping):
        named |= set(preprocessing['missing'])
    fitted['ignored'] = sorted(named - used)
    na_values = {str(v) for v in case.dataset.get('na_values', ())}
    covered = {s['column'] for s in special if str(s['value']) in na_values}
    for column in features:
        if governance.missing_strategy(preprocessing, column) != 'indicator' \
                or column in covered:
            continue
        if not train[column].isna().any():
            continue
        name = f'{column}=(missing)'
        X_train[name] = train[column].isna().astype(int).to_numpy()
        X_val[name] = validation[column].isna().astype(int).to_numpy()
        fitted['missing_indicators'].append(name)
    k = preprocessing['rare_category_min_rows']
    if k > 0:
        for column in features:
            if is_numeric_dtype(X_train[column]):
                continue
            counts = X_train[column].dropna().astype(str).value_counts()
            kept = set(counts[counts >= k].index)
            folded = sorted(set(counts.index) - kept)
            if not folded and X_val[column].dropna().astype(str).isin(kept).all():
                continue
            for X in (X_train, X_val):
                text = X[column].map(lambda v: v if v != v else str(v))
                X[column] = text.where(text.isna() | text.isin(kept), governance.RARE_GROUP)
            fitted['rare_categories'][column] = {'kept': len(kept), 'folded': folded}
    for column, (q_low, q_high) in sorted(preprocessing['caps'].items()):
        if column not in used:
            continue
        low = float(X_train[column].quantile(q_low))
        high = float(X_train[column].quantile(q_high))
        X_train[column] = X_train[column].clip(low, high)
        X_val[column] = X_val[column].clip(low, high)
        fitted['caps'][column] = [low, high]
    for column in preprocessing['log_transform']:
        if column not in used:
            continue
        for X in (X_train, X_val):
            v = X[column].astype(float)
            X[column] = np.sign(v) * np.log1p(np.abs(v))
        fitted['log_transform'].append(column)
    return X_train, X_val, fitted


def _preprocessing_values(inputs: Mapping, fitted) -> dict:
    if fitted is None:
        return {}
    return {'preprocessing': {'value': dict(inputs['preprocessing']), 'fitted': fitted,
                              'note': 'Parameters learnt on training rows only and applied '
                                      'unchanged to validation rows.'}}


def _fit_predict(case: c.Case, train, test, inputs: Mapping, params: Mapping, binary: bool,
                 info: dict | None = None):
    """Fit the model of ``params`` on ``train`` with the model ``inputs`` (features, special
    values, preprocessing), and predict ``test``: ``(prediction, model, indicators,
    fitted, in_sample)`` (``in_sample``: the prediction of ``train`` itself). A binary model scores the positive class; a regression model predicts the
    target. Shared by the train/validation fits, the cross-validated fits (one call per
    fold), and the final evaluation (WP-B1); the candidate's own parameters are unchanged
    since v0.1, the variant's (``C``, ``alpha``) come from :data:`activities.VARIANT_C` and
    :data:`activities.VARIANT_ALPHA`.

    v0.3 (WP-F1): ``params['family']`` (``ebm`` or ``hgb``; the linear model otherwise) and
    ``params['tuning']`` (a grid, :func:`mlkit.study.trials.grid`): the hyperparameter is
    chosen by an inner cross-validation of ``train`` (:func:`mlkit.study.families.choose`)
    unless ``params['tuned_value']`` fixes it. ``info`` (optional) receives ``tuning`` (the
    choice), and with ``info['keep']`` the prepared ``X_test``."""
    from .activities import positive
    from mlkit import classical
    if params.get('tuning') and params.get('tuned_value') is None:
        from . import families
        choice = families.choose(case, train, inputs, params, binary)
        params = {**params, 'tuned_value': choice['value']}
        if info is not None:
            info['tuning'] = choice
    features, special = list(inputs['features']), list(inputs['special_values'])
    X_train, indicators = design(train, features, special, case)
    X_test, _ = design(test, features, special, case)
    X_train, X_test, fitted = prepare(case, train, test, X_train, X_test, features,
                                      inputs.get('preprocessing'), special)
    if info is not None and info.get('keep'):
        info['X_test'] = X_test
    family = params.get('family') or 'linear'
    tuned = params.get('tuned_value')
    if family != 'linear':
        from . import families
        y_train = positive(train, case).to_numpy() if binary else _target(case, train,
                                                                           'training')
        model = families.fit_family(family, X_train, y_train, binary, tuned, params['seed'])
        prediction = families.predict_family(family, model, X_test, binary)
        in_sample = None if binary else families.predict_family(family, model, X_train, False)
        return prediction, model, indicators, fitted, in_sample
    if binary:
        y_train = positive(train, case)
        spec = {'task': {'kind': 'binary'}, 'model_options': {}}
        model = classical.pipeline('logistic', X_train, spec, params['seed'])
        if params.get('solver') is not None:
            model.set_params(model__solver=str(params['solver']))
        if params.get('tol') is not None:
            model.set_params(model__tol=float(params['tol']))
        if params.get('C') is not None:
            model.set_params(model__C=float(params['C']))
        if tuned is not None:
            model.set_params(model__C=float(tuned))
        model.fit(X_train, y_train.to_numpy())
        classes = list(model.classes_)
        return (model.predict_proba(X_test)[:, classes.index(1)], model, indicators, fitted,
                None)
    from sklearn.linear_model import LinearRegression, Ridge
    y_train = _target(case, train, 'training')
    spec = {'task': {'kind': 'regression'}, 'model_options': {}}
    model = classical.pipeline('ridge', X_train, spec, params['seed'])
    if tuned is not None:
        model.set_params(model=Ridge(alpha=float(tuned)))
    elif params.get('alpha') is not None:
        model.set_params(model=Ridge(alpha=float(params['alpha'])))
    else:
        model.set_params(model=LinearRegression())
    model.fit(X_train, y_train)
    return model.predict(X_test), model, indicators, fitted, model.predict(X_train)


def _variant_values(inputs: Mapping, params: Mapping) -> dict:
    """WP-B1: what makes a variant (additive keys of ``fit.variant``'s values)."""
    if 'variant' not in inputs:
        return {}
    out = {'variant': dict(inputs['variant'])}
    for key in ('C', 'candidate_C', 'alpha', 'dropped_group', 'family', 'variant_index'):
        if key in params:
            out[key] = params[key]
    return out


TUNING_NOTE = ('The value is chosen inside each outer fold by an inner cross-validation of that '
               'fold\'s training rows only, so the out-of-fold figures include the choice '
               '(nested cross-validation). One tuning is one trial.')


def _inner_scores(choice: Mapping) -> list[dict]:
    return [{'value': s['value'], 'mean': s['mean']} for s in choice.get('scores') or []]


def tuning_values(params: Mapping, per_fold: list, development: Mapping | None) -> dict | None:
    """v0.3 (WP-F1): the hyperparameter chosen in each outer fold (``per_fold``: the
    :func:`mlkit.study.families.choose` results in fold order) and on the rows of the final
    fit (``development``); None for a model without tuning."""
    tuning = params.get('tuning')
    if not tuning:
        return None
    out = {k: tuning[k] for k in ('parameter', 'values', 'inner_folds', 'seed', 'metric',
                                  'method', 'tie', 'meaning') if k in tuning}
    out['per_fold'] = [{'fold': i, 'value': c['value'], 'inner_scores': _inner_scores(c)}
                       for i, c in enumerate(per_fold, start=1) if c is not None]
    out['development'] = ({'value': development['value'],
                           'inner_scores': _inner_scores(development)}
                          if development is not None else None)
    out['note'] = TUNING_NOTE
    return out


def _family_values(case, frame, model, indicators, features, params, binary,
                   n_positive) -> dict:
    """The values of a model of another family (WP-F1): no coefficients; the EBM's terms
    (its own diagnostics) from this fit."""
    from . import families
    family = params['family']
    out = {'model': family, 'family': family, 'features': features,
           'special_value_indicators': indicators, 'n_train': int(len(frame)),
           'versions': families.versions(family),
           'settings': dict(params.get('settings') or {})}
    if binary:
        out['n_train_positive'] = int(n_positive)
    else:
        out.update(target=case.target_column, unit=case.target_unit)
    if family == 'ebm':
        out['family_diagnostics'] = families.ebm_terms(model, binary)
    return out


def _model_values(case, frame, model, indicators, features, params, binary,
                  n_positive=0) -> dict:
    if (params.get('family') or 'linear') != 'linear':
        return _family_values(case, frame, model, indicators, features, params, binary,
                              n_positive)
    if binary:
        return _logistic_values(case, frame, model, indicators, features, n_positive)
    return _linear_values(case, frame, model, indicators, features, params)


def _logistic_values(case, frame, model, indicators, features, n_positive) -> dict:
    names = [str(n) for n in model['preprocess'].get_feature_names_out()]
    coef = model['model'].coef_[0]
    return {'model': 'logistic', 'features': features, 'special_value_indicators': indicators,
            'n_train': int(len(frame)), 'n_train_positive': int(n_positive),
            'n_terms': len(names), 'intercept': float(model['model'].intercept_[0]),
            'coefficients': {n: float(v) for n, v in zip(names, coef)},
            'coefficient_scale': 'per standard deviation of the training rows (numeric) or '
                                 'per category (one-hot); associations, not effects',
            'iterations': int(model['model'].n_iter_[0])}


def logistic(case: c.Case, train, validation, inputs: Mapping, params: Mapping) -> dict:
    from .activities import guard_read_only, positive
    guard_read_only()

    train, validation = _ordered(train), _ordered(validation)
    features = list(inputs['features'])
    info = {'keep': params.get('family') == 'hgb'}
    score, model, indicators, fitted, _ = _fit_predict(case, train, validation, inputs,
                                                       params, binary=True, info=info)
    y_train = positive(train, case)
    y_val = positive(validation, case).to_numpy()
    name = params.get('family') or 'logistic'
    values = {**_model_values(case, train, model, indicators, features, params, True,
                              y_train.sum()),
              'validation': _validation_summary(y_val, score),
              'predictions': _predictions_meta(case, name, features, y_val),
              **_preprocessing_values(inputs, fitted), **_variant_values(inputs, params)}
    _split_extras(values, params, info, model, y_val, True)
    return {'values': values,
            'blobs': {'predictions': predictions_blob(validation.index, y_val, score)},
            'partition': 'validation', 'n_rows': int(len(validation))}


def _split_extras(values: dict, params: Mapping, info: Mapping, model, y_val,
                  binary: bool) -> None:
    """WP-F1, train/validation split: the tuning chosen on the training rows, and the
    permutation importance of a boosting model on the validation rows."""
    tuning = tuning_values(params, [], info.get('tuning'))
    if tuning is not None:
        tuning['note'] = ('The value is chosen by an inner cross-validation of the training '
                          'rows only; the validation rows never choose it. One tuning is one '
                          'trial.')
        values['tuning'] = tuning
    if params.get('family') == 'hgb':
        from . import families
        imp = families.permutation_importance(model, info['X_test'], y_val, binary,
                                              params['seed'])
        values['family_diagnostics'] = families.combine_importance([(len(y_val), imp)], binary)


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



def _linear_values(case, train, model, indicators, features, params) -> dict:
    names = [str(n) for n in model['preprocess'].get_feature_names_out()]
    coef = model['model'].coef_
    return {'model': 'ridge' if params.get('alpha') is not None or params.get('tuning')
            else 'linear',
            'target': case.target_column, 'unit': case.target_unit,
            'features': features, 'special_value_indicators': indicators,
            'n_train': int(len(train)), 'n_terms': len(names),
            'intercept': float(model['model'].intercept_),
            'coefficients': {n: float(v) for n, v in zip(names, coef)},
            'coefficient_scale': 'target units per standard deviation of the training rows '
                                 '(numeric) or per category (one-hot, not identifiable one by '
                                 'one); associations, not effects'}


def linear(case: c.Case, train, validation, inputs: Mapping, params: Mapping) -> dict:
    from .activities import guard_read_only
    guard_read_only()

    train, validation = _ordered(train), _ordered(validation)
    features = list(inputs['features'])
    info = {'keep': params.get('family') == 'hgb'}
    prediction, model, indicators, fitted, in_sample = _fit_predict(
        case, train, validation, inputs, params, binary=False, info=info)
    y_train = _target(case, train, 'training')
    y_val = _target(case, validation, 'validation')
    name = params.get('family') or 'linear'
    values = {**_model_values(case, train, model, indicators, features, params, False),
              'train': _errors(y_train, in_sample),
              'validation': _errors(y_val, prediction),
              'predictions': _regression_meta(case, name, features, y_val),
              **_preprocessing_values(inputs, fitted), **_variant_values(inputs, params)}
    _split_extras(values, params, info, model, y_val, False)
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


# --- cross-validation on the development rows (WP-B1) ------------------------------------

CV_NOTE = ('Every development row is predicted once, by a model fitted on the other folds '
           '(the preparation of the variables learnt on those rows too): out-of-fold figures '
           'are development evidence, not independent evidence.')
SPREAD_KEYS = ('mean', 'sd', 'min', 'max')


def _spread(values) -> dict:
    """Mean, standard deviation (n - 1), minimum and maximum of the per-fold figures (the
    folds that have one)."""
    import numpy as np
    v = np.array([x for x in values if x is not None], dtype=float)
    if not len(v):
        return {k: None for k in SPREAD_KEYS}
    return {'mean': float(v.mean()), 'sd': float(v.std(ddof=1)) if len(v) > 1 else None,
            'min': float(v.min()), 'max': float(v.max())}


def compute_cv(activity: str, case: c.Case, frame, folds: Mapping, inputs: Mapping,
               params: Mapping) -> dict:
    """Out-of-fold predictions of every development row (WP-B1).

    For each fold, the model (and the preparation of its variables) is fitted on the rows of
    the other folds and predicts the fold's rows. The figures of ``validation`` are those of
    the out-of-fold predictions (all rows), ``cross_validation`` gives them per fold with
    their spread, and the coefficients come from one more fit on every development row (the
    model a final test would measure). The binary baseline scores every row with the
    development positive rate: a constant has no ranking information, and a per-fold rate
    would rank the rows by fold. The regression baseline predicts each fold with the mean of
    the other folds."""
    import numpy as np
    from .activities import guard_read_only, positive
    guard_read_only()

    if folds.get('schema') == 'hypotrail.evaluation_plan/1':
        return compute_explicit_cv(activity, case, frame, folds, inputs, params)

    frame = _ordered(frame)
    keys = list(frame.index)
    fold = np.array([int(folds[k]) for k in keys])
    k = int(fold.max())
    binary = case.task == 'binary'
    features = list(inputs.get('features') or [])
    n = len(keys)
    if binary:
        y = positive(frame, case).to_numpy()
    else:
        y = _target(case, frame, 'development')
    oof = np.zeros(n, dtype=float)
    candidate = activity != 'fit.baseline'
    family = params.get('family') or 'linear'
    choices, importances = [], []
    for i in range(1, k + 1):
        test = fold == i
        if not candidate:
            oof[test] = y.mean() if binary else y[~test].mean()
            continue
        info = {'keep': family == 'hgb'}
        pred, fold_model = _fit_predict(case, frame.loc[[kk for kk, t in zip(keys, ~test) if t]],
                                        frame.loc[[kk for kk, t in zip(keys, test) if t]],
                                        inputs, params, binary, info=info)[:2]
        oof[test] = pred
        choices.append(info.get('tuning'))
        if family == 'hgb':
            # WP-F1: the boosting model's own diagnostic, on the rows it did not see.
            from . import families
            importances.append((int(test.sum()), families.permutation_importance(
                fold_model, info['X_test'], y[test], binary, params['seed'])))
    per_fold = []
    for i in range(1, k + 1):
        test = fold == i
        item = {'fold': i, 'n_rows': int(test.sum())}
        if binary:
            item.update(n_positive=int(y[test].sum()),
                        roc_auc=metrics.roc_auc(y[test], oof[test]),
                        average_precision=metrics.average_precision(y[test], oof[test]))
        else:
            e = _errors(y[test], oof[test])
            item.update(mae=e['mae'], rmse=e['rmse'])
        per_fold.append(item)
    names = ('roc_auc', 'average_precision') if binary else ('mae', 'rmse')
    cv = {'method': inputs.get('evaluation', {}).get('method'), 'folds': k,
          'per_fold': per_fold,
          'spread': {m: _spread(f[m] for f in per_fold) for m in names},
          'note': CV_NOTE}
    common = {'evaluation': 'out_of_fold', 'cross_validation': cv}
    if not candidate:
        if binary:
            values = {'model': 'constant_prior', 'train_rate': float(y.mean()), 'n_train': n,
                      'n_train_positive': int(y.sum()), 'features': [],
                      'validation': _validation_summary(y, oof),
                      'predictions': _cv_meta(_predictions_meta(case, 'constant_prior', [], y)),
                      'note': 'Every row receives the development positive rate: no ranking '
                              'information.', **common}
            blob = predictions_blob(keys, y, oof)
        else:
            mean = float(y.mean())
            values = {'model': 'train_mean', 'target': case.target_column,
                      'unit': case.target_unit, 'train_mean': mean,
                      'train_median': float(np.median(y)), 'n_train': n, 'features': [],
                      'train': _errors(y, np.full(n, mean)),
                      'validation': _errors(y, oof),
                      'predictions': _cv_meta(_regression_meta(case, 'train_mean', [], y)),
                      'note': 'Each fold receives the mean of the other folds: the reference a '
                              'model must beat.', **common}
            blob = regression_blob(keys, y, oof)
        return {'values': values, 'blobs': {'predictions': blob}, 'partition': 'development',
                'n_rows': n}
    # One more fit on every development row: its coefficients and preparation are shown.
    full_info: dict = {}
    _, model, indicators, fitted, in_sample = _fit_predict(case, frame, frame, inputs, params,
                                                           binary, info=full_info)
    if binary:
        values = {**_model_values(case, frame, model, indicators, features, params, True,
                                  y.sum()),
                  'validation': _validation_summary(y, oof),
                  'predictions': _cv_meta(_predictions_meta(case, family if family != 'linear'
                                                            else 'logistic', features, y))}
        blob = predictions_blob(keys, y, oof)
    else:
        values = {**_model_values(case, frame, model, indicators, features, params, False),
                  'train': _errors(y, in_sample), 'validation': _errors(y, oof),
                  'predictions': _cv_meta(_regression_meta(case, family if family != 'linear'
                                                           else 'linear', features, y))}
        blob = regression_blob(keys, y, oof)
    tuning = tuning_values(params, choices, full_info.get('tuning'))
    if tuning is not None:
        values['tuning'] = tuning
    if importances:
        from . import families
        values['family_diagnostics'] = families.combine_importance(importances, binary)
    pre = _preprocessing_values(inputs, fitted)
    if pre:
        pre['preprocessing']['note'] = ('Parameters learnt, in each fold, on the rows of the '
                                        'other folds and applied to the fold they predict; '
                                        'shown here as learnt on every development row.')
    values.update(pre)
    # B6c (M3): the coefficients come from the fit on every development row.
    if 'coefficient_scale' in values:
        values['coefficient_scale'] = values['coefficient_scale'].replace(
            'of the training rows', 'of the development rows')
    values.update(_variant_values(inputs, params))
    values.update(common)
    return {'values': values, 'blobs': {'predictions': blob}, 'partition': 'development',
            'n_rows': n}


def compute_explicit_cv(activity: str, case: c.Case, frame, plan: Mapping,
                        inputs: Mapping, params: Mapping) -> dict:
    """J1 fits exactly the memberships recorded by the planner (warm-up stays unscored)."""
    import numpy as np
    from .activities import positive
    from . import evaluation_plan as ep
    frame = _ordered(frame)
    universe = set(frame.index)
    binary, candidate = case.task == 'binary', activity != 'fit.baseline'
    family = params.get('family') or 'linear'
    scored_keys = [key for fold in plan['folds'] for key in fold['validation_keys']]
    if len(scored_keys) != len(set(scored_keys)) or not set(scored_keys) <= universe:
        from .errors import StudyError
        raise StudyError('integrity_error', 'The explicit plan has invalid scored keys.')
    criterion = inputs.get('success_criterion')
    selection = (criterion or {}).get('selection') if isinstance(criterion, Mapping) else None
    if isinstance(selection, Mapping) and selection.get('scope') == 'column_batch':
        column = selection['batch_column']
        if column == case.target_column or column not in frame.columns:
            from .errors import StudyError
            raise StudyError('invalid_value', 'The declared action batch column is invalid.',
                             details={'batch_column': column})
        seen = {}
        for fold in plan['folds']:
            for value in frame.loc[fold['validation_keys'], column].astype(str):
                previous = seen.setdefault(value, fold['id'])
                if previous != fold['id']:
                    from .errors import StudyError
                    raise StudyError('unsupported_capability',
                                     'The evaluation split cuts an action batch.',
                                     details={'reason': 'batch_cut_across_windows',
                                              'batch_column': column, 'batch': value,
                                              'folds': [previous, fold['id']]})
    y_all = (positive(frame, case).astype(int) if binary else
             _target(case, frame, 'development'))
    predictions, observed, keys_out = [], [], []
    per_fold, choices, importances = [], [], []
    for fold in plan['folds']:
        train_keys, validation_keys = fold['train_keys'], fold['validation_keys']
        if not set(train_keys + validation_keys) <= universe or set(train_keys) & set(validation_keys):
            from .errors import StudyError
            raise StudyError('integrity_error', 'An explicit fold has invalid memberships.',
                             details={'fold': fold['id']})
        train, test = frame.loc[train_keys], frame.loc[validation_keys]
        y_train, y_test = y_all.loc[train_keys].to_numpy(), y_all.loc[validation_keys].to_numpy()
        if not candidate:
            if binary:
                pred = np.full(len(test), float(y_train.mean()))
            else:
                # J3: MAE is minimized by the training median in review-v1.
                pred = np.full(len(test), float(np.median(y_train)))
        else:
            info = {'keep': family == 'hgb'}
            nested_inputs = {**inputs, 'parent_protocol': {
                'method': plan['method'], 'fold': fold['id'],
                'outer_train_keys': list(train_keys),
                'outer_validation_keys': list(validation_keys)}}
            pred, fold_model = _fit_predict(case, train, test, nested_inputs, params, binary,
                                            info=info)[:2]
            choices.append(info.get('tuning'))
            if family == 'hgb':
                from . import families
                importances.append((len(test), families.permutation_importance(
                    fold_model, info['X_test'], y_test, binary, params['seed'])))
        predictions.extend(float(v) for v in pred)
        observed.extend(float(v) for v in y_test)
        keys_out.extend(validation_keys)
        item = {'fold': fold['id'], 'n_rows': len(validation_keys),
                'n_train': len(train_keys), 'validation_start': fold['validation_start'],
                'validation_end': fold['validation_end']}
        if binary:
            item.update(n_positive=int(y_test.sum()), roc_auc=metrics.roc_auc(y_test, pred),
                        average_precision=metrics.average_precision(y_test, pred))
            if isinstance(criterion, Mapping):
                from . import objective
                selection = criterion['selection']
                batches = (test[selection['batch_column']].tolist()
                           if selection['scope'] == 'column_batch' else None)
                item['objective'] = objective.evaluate_binary(
                    y_test, pred, metric=selection['metric'], rule=selection['rule'],
                    windows=[fold['id']] * len(test), batches=batches,
                    scope=selection['scope'])
        else:
            item.update(_errors(y_test, pred))
        per_fold.append(item)
    y, oof = np.asarray(observed), np.asarray(predictions)
    names = ('roc_auc', 'average_precision') if binary else ('mae', 'rmse')
    cv = {'method': plan['method'], 'folds': len(plan['folds']), 'per_fold': per_fold,
          'spread': {name: _spread(item.get(name) for item in per_fold) for name in names},
          'plan_digest': ep.digest(plan), 'n_development': len(frame),
          'n_scored': len(keys_out), 'n_warmup': len(plan['unscored_keys']),
          'note': ('Explicit train/validation memberships; warm-up rows are not predicted '
                   'and are absent from every metric denominator.')}
    if isinstance(criterion, Mapping):
        from . import objective
        windows = [fold['id'] for fold in plan['folds']
                   for _ in fold['validation_keys']]
        if binary:
            selection = criterion['selection']
            batches = ([frame.loc[key, selection['batch_column']] for key in keys_out]
                       if selection['scope'] == 'column_batch' else None)
            cv['objective'] = objective.evaluate_binary(
                y, oof, metric=selection['metric'], rule=selection['rule'], windows=windows,
                batches=batches, scope=selection['scope'])
        else:
            cv['objective'] = objective.evaluate_regression(y, oof, windows=windows)
    common = {'evaluation': 'out_of_sample_windows', 'cross_validation': cv}
    if not candidate:
        if binary:
            values = {'model': 'constant_training_prior', 'baseline_strategy': 'fold_train_rate',
                      'n_train': len(frame), 'features': [],
                      'validation': _validation_summary(y, oof),
                      'predictions': _cv_meta(_predictions_meta(
                          case, 'constant_training_prior', [], y)), **common}
            blob = predictions_blob(keys_out, y, oof)
        else:
            values = {'model': 'train_median', 'baseline_strategy': 'fold_train_median',
                      'target': case.target_column, 'unit': case.target_unit,
                      'train_median': float(np.median(y_all)), 'n_train': len(frame),
                      'features': [], 'validation': _errors(y, oof),
                      'predictions': _cv_meta(_regression_meta(case, 'train_median', [], y)),
                      **common}
            blob = regression_blob(keys_out, y, oof)
        return {'values': values, 'blobs': {'predictions': blob},
                'partition': 'development', 'n_rows': len(keys_out)}
    full_info = {}
    _, model, indicators, fitted, in_sample = _fit_predict(case, frame, frame, inputs, params,
                                                           binary, info=full_info)
    if binary:
        values = {**_model_values(case, frame, model, indicators, list(inputs['features']),
                                  params, True, int(y_all.sum())),
                  'validation': _validation_summary(y, oof),
                  'predictions': _cv_meta(_predictions_meta(case, family if family != 'linear'
                                                            else 'logistic',
                                                            list(inputs['features']), y))}
        blob = predictions_blob(keys_out, y, oof)
    else:
        values = {**_model_values(case, frame, model, indicators, list(inputs['features']),
                                  params, False),
                  'train': _errors(y_all.to_numpy(), in_sample),
                  'validation': _errors(y, oof),
                  'predictions': _cv_meta(_regression_meta(case, family if family != 'linear'
                                                           else 'linear',
                                                           list(inputs['features']), y))}
        blob = regression_blob(keys_out, y, oof)
    tuning = tuning_values(params, choices, full_info.get('tuning'))
    if tuning is not None:
        values['tuning'] = tuning
    if importances:
        from . import families
        values['family_diagnostics'] = families.combine_importance(importances, binary)
    values.update(_preprocessing_values(inputs, fitted))
    values.update(_variant_values(inputs, params))
    values.update(common)
    return {'values': values, 'blobs': {'predictions': blob},
            'partition': 'development', 'n_rows': len(keys_out)}


def _cv_meta(meta: dict) -> dict:
    return {**meta, 'partition': 'development', 'evaluation': 'out_of_fold'}


# --- the final test, scored once (WP-B1) --------------------------------------------------

def criterion_status(gain, low, high, minimum) -> tuple[str, bool | None]:
    """``(status, interval_includes_zero)`` of a gain against the success criterion's
    minimum, as ``governance.assess`` judges it: ``met`` (the gain reaches the minimum and
    its interval excludes 0), ``uncertain`` (it reaches it, the interval includes 0),
    ``not_met``; ``not_assessed`` without a gain."""
    if gain is None or minimum is None:
        return 'not_assessed', None
    includes = low is not None and high is not None and low <= 0 <= high
    if gain < minimum - 1e-12:
        return 'not_met', includes
    return ('uncertain' if includes else 'met'), includes


FINAL_NOTE = ('Measured once on the sealed final-test rows, with the configuration chosen on '
              'the development rows refitted on all of them: this is the study\'s independent '
              'evidence. Any later change is made after the final test.')


def final_evaluation(case: c.Case, development, final, inputs: Mapping,
                     params: Mapping, predictor=None) -> dict:
    """The chosen configuration on the final test (WP-B1): refit on every development row,
    score the final-test rows once, compare with the baseline refitted the same way, and
    judge the success criterion on them.

    Library integration v1: ``predictor`` (``(loaded, parity)`` from
    :func:`mlkit.contracts.capture.load_for_final`) is the reloaded capture of the chosen
    configuration; it scores the final-test rows instead of a new fit, and the values name
    its predictor id."""
    import numpy as np
    from . import policy, regression
    from .activities import guard_read_only, positive
    guard_read_only()

    development, final = _ordered(development), _ordered(final)
    binary = case.task == 'binary'
    chosen = params['model']
    model_inputs, model_params = inputs['model_inputs'], params['model_params']
    boot = inputs['bootstrap']
    B, seed, level = int(boot['replicates']), int(boot['seed']), float(boot['level'])
    criterion = inputs.get('criterion') or {}
    review = 'decision_rule' in criterion
    dependency = ((inputs.get('model_inputs') or {}).get('analysis_contract') or {}) \
        .get('dependencies', {}).get('kind')
    review_uncertainty = None
    n = len(final)
    values = {'model': chosen, 'rule': params.get('rule'), 'n': n,
              'refit': {'n_rows': int(len(development)),
                        'features': list(model_inputs.get('features') or [])},
              'evaluation': 'final_test'}
    final_info: dict = {}

    def chosen_output(binary_task: bool):
        if predictor is not None:
            loaded, _ = predictor
            return loaded.predict(final[list(loaded.recipe.features)]).values
        return _fit_predict(case, development, final, model_inputs, model_params, binary_task,
                            info=final_info)[0]
    if (model_params or {}).get('family'):
        values['family'] = model_params['family']      # WP-F1 (additive)
    if binary:
        y_dev = positive(development, case).to_numpy()
        y = positive(final, case).to_numpy()
        base = np.full(n, float(y_dev.mean()))
        score = base if chosen == 'fit.baseline' else chosen_output(True)
        from .records import capacity_of
        rule = params['rule']
        if capacity_of(rule) is not None and params.get('capacity_share') is not None:
            # The capacity keeps its share of the rows on the final test.
            k = max(1, int(np.floor(params['capacity_share'] * n + 0.5)))
            rule_final = f'capacity:{k}'
        else:
            rule_final = rule
        scores = {'fit.baseline': base, chosen: score}
        paired = policy.paired_bootstrap(y, scores, rule_final, B, seed, level=level,
                                         reference='fit.baseline')
        delta_metric = {'precision_gain': 'precision', 'recall_gain': 'recall'}.get(
            criterion.get('metric'), 'precision')
        delta = paired['deltas'].get(chosen, {}).get(delta_metric) or {}
        gain = 100 * delta['point'] if delta.get('point') is not None else None
        low = 100 * delta['low'] if delta.get('low') is not None else None
        high = 100 * delta['high'] if delta.get('high') is not None else None
        minimum = criterion.get('min_points')
        unit = 'percentage points'
        values.update(rule_final=rule_final, capacity_share=params.get('capacity_share'),
                      n_positive=int(y.sum()),
                      models={s: policy.evaluate(y, v, rule_final) for s, v in scores.items()},
                      intervals=paired['intervals'], deltas=paired['deltas'],
                      ranking={s: {'roc_auc': metrics.roc_auc(y, v),
                                   'average_precision': metrics.average_precision(y, v)}
                               for s, v in scores.items()})
        blob = predictions_blob(final.index, y, score)
        if review:
            from . import objective
            selection = criterion['selection']
            batches = (final[selection['batch_column']].tolist()
                       if selection['scope'] == 'column_batch' else None)
            values['objective'] = {slot: objective.evaluate_binary(
                y, scores_, metric=selection['metric'], rule=selection['rule'],
                windows=[1] * n, batches=batches, scope=selection['scope'])
                for slot, scores_ in scores.items()}
            baseline_point = values['objective']['fit.baseline']['point']
            chosen_point = values['objective'][chosen]['point']
            gain = (100 * (chosen_point - baseline_point)
                    if baseline_point is not None and chosen_point is not None else None)
            low = high = None
            if dependency == 'independent' and selection['scope'] == 'evaluation_window':
                if chosen == 'fit.baseline':
                    low = high = 0.0
                    review_uncertainty = {
                        'method': 'paired_row_bootstrap', 'level': level,
                        'resampling_unit': 'row', 'target_quantity': criterion.get('metric'),
                        'conditioning': 'fixed selected configuration',
                        'dependence_assumptions': 'independent held-out observations',
                        'eligible': True, 'replicates': B, 'undefined_replicates': 0,
                        'reason': None}
                else:
                    boot_objective = objective.paired_row_bootstrap(
                        y, scores,
                        lambda yy, ss: objective.evaluate_binary(
                            yy, ss, metric=selection['metric'], rule=selection['rule'],
                            windows=[1] * len(yy), scope='evaluation_window'),
                        replicates=B, seed=seed, level=level)
                    review_uncertainty = boot_objective['uncertainty']
                    interval = boot_objective['delta_intervals'].get(chosen) or {}
                    if review_uncertainty['eligible']:
                        low = 100 * interval['low']
                        high = 100 * interval['high']
            elif dependency == 'independent':
                review_uncertainty = {
                    'method': None, 'level': level, 'resampling_unit': None,
                    'target_quantity': criterion.get('metric'),
                    'conditioning': 'fixed selected configuration',
                    'dependence_assumptions': 'fixed action batches', 'eligible': False,
                    'replicates': B, 'undefined_replicates': None,
                    'reason': 'no batch-preserving inferential interval is implemented'}
    else:
        y_dev = _target(case, development, 'development')
        y = _target(case, final, 'final test')
        baseline_value = float(np.median(y_dev)) if review else float(y_dev.mean())
        base = np.full(n, baseline_value)
        pred = base if chosen == 'fit.baseline' else chosen_output(False)
        predictions = {'fit.baseline': base}
        if chosen != 'fit.baseline':
            predictions[chosen] = pred
        paired = regression.paired_bootstrap(y, predictions, B, seed, level=level,
                                             reference='fit.baseline')
        base_mae = paired['models']['fit.baseline']['mae']
        delta = paired['deltas'].get(chosen, {}).get('mae')
        if delta and base_mae > 0:
            gain, low, high = (-delta['point'] / base_mae, -delta['high'] / base_mae,
                               -delta['low'] / base_mae)
        else:
            gain = low = high = None
        minimum = criterion.get('min_share')
        unit = 'share'
        values.update(target=case.target_column, unit=case.target_unit,
                      baseline_strategy=('development_median' if review else
                                         'development_mean'),
                      models=paired['models'], intervals=paired['intervals'],
                      deltas=paired['deltas'],
                      residuals={s: regression.residual_summary(y, p)
                                 for s, p in predictions.items()})
        if review:
            from . import objective
            values['objective'] = {slot: objective.evaluate_regression(y, prediction,
                                                                        windows=[1] * n)
                                   for slot, prediction in predictions.items()}
            baseline_point = values['objective']['fit.baseline']['point']
            chosen_point = values['objective'][chosen]['point']
            gain = objective.relative_mae_reduction(chosen_point, baseline_point)
            low = high = None
            if dependency == 'independent' and baseline_point > 0:
                if chosen == 'fit.baseline':
                    low = high = 0.0
                    review_uncertainty = {
                        'method': 'paired_row_bootstrap', 'level': level,
                        'resampling_unit': 'row', 'target_quantity': criterion.get('metric'),
                        'conditioning': 'fixed selected configuration',
                        'dependence_assumptions': 'independent held-out observations',
                        'eligible': True, 'replicates': B, 'undefined_replicates': 0,
                        'reason': None}
                else:
                    boot_objective = objective.paired_row_bootstrap(
                        y, predictions,
                        lambda yy, pp: objective.evaluate_regression(yy, pp,
                                                                     windows=[1] * len(yy)),
                        replicates=B, seed=seed, level=level)
                    review_uncertainty = boot_objective['uncertainty']
                    interval = boot_objective['delta_intervals'].get(chosen) or {}
                    if review_uncertainty['eligible']:
                        low = -interval['high'] / baseline_point
                        high = -interval['low'] / baseline_point
        blob = regression_blob(final.index, y, pred)
    tuning = tuning_values(model_params or {}, [], final_info.get('tuning'))
    if tuning is not None:
        # WP-F1 (additive): the hyperparameter chosen on every development row.
        tuning['note'] = ('The value is chosen by an inner cross-validation of the development '
                          'rows only, before the final-test rows are scored.')
        values['tuning'] = tuning
    if review:
        from . import objective
        if review_uncertainty is None:
            review_uncertainty = {
                'method': None, 'level': level, 'resampling_unit': None,
                'target_quantity': criterion.get('metric'),
                'conditioning': 'fixed selected configuration',
                'dependence_assumptions': dependency or 'unspecified', 'eligible': False,
                'replicates': B, 'undefined_replicates': None,
                'reason': 'group or temporal dependence has no supported inferential interval'}
        qualified = bool(review_uncertainty['eligible'])
        assessment = objective.assess(
            gain, minimum, decision_rule=criterion['decision_rule'],
            low=low, high=high, interval_qualified=qualified,
            uncertainty_status='available' if qualified else 'unavailable')
        values['criterion'] = {'metric': criterion.get('metric'), 'minimum': minimum,
                               'unit': unit, 'gain': gain,
                               'low': low if qualified else None,
                               'high': high if qualified else None,
                               'interval_includes_zero': (
                                   None if assessment['interval_excludes_zero'] is None else
                                   not assessment['interval_excludes_zero']),
                               'status': assessment['decision_status'],
                               **assessment}
        values['uncertainty'] = review_uncertainty
    else:
        status, includes = criterion_status(gain, low, high, minimum)
        values['criterion'] = {'metric': criterion.get('metric'), 'minimum': minimum,
                               'unit': unit, 'gain': gain, 'low': low, 'high': high,
                               'interval_includes_zero': includes, 'status': status}
    values['bootstrap'] = {'replicates': B, 'seed': seed, 'level': level,
                           'method': 'paired percentile bootstrap over the final-test rows'}
    values['note'] = FINAL_NOTE
    if predictor is not None:
        loaded, parity = predictor
        values['predictor'] = {           # library integration v1 (additive)
            'predictor_id': loaded.predictor_id, 'capture': inputs['predictor']['result_id'],
            'evaluated': 'reloaded_capture', 'parity_before_opening': parity.status,
            'note': 'The final-test rows were scored by the captured predictor, reloaded and '
                    'checked on its parity rows before they were read; no model was refitted.'}
    return {'values': values, 'blobs': {'predictions': blob}, 'partition': 'final_test',
            'n_rows': n}
