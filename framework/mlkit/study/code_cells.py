"""Readable recomputation cells of the generated notebook (v0.2a, WP-A6; ADR 0001 amended).

For each step with a registered result, the generated notebook shows plain pandas and
scikit-learn code that a junior can copy to the workbench. Each cell recomputes the
registered result from the **development rows** (loaded with
:func:`mlkit.study.notebook_view.development_frame`, never the sealed final test) and
``assert``\\ s that it equals the registry value, within a stated tolerance:

* counts are compared exactly;
* rates, means and medians to :data:`TOLERANCE` (``1e-9``: the same arithmetic, in another
  order);
* a fitted model's metric (AUC, MAE) to :data:`FIT_TOLERANCE` (``1e-6``: the same solver on
  the same rows, whose floating-point sums may differ in the last digits).

Covered: the split counts, the target rate (binary) or summary (regression), one rate or
mean by group, the candidate model's validation metric with the confirmed preprocessing
(WP-B1: under cross-validation, its out-of-fold metric, refitted fold by fold),
and, for a binary study, the policy at the adopted rule (selected rows, positive rows
found, precision); for a regression study, the baseline's validation error.

A cell is generated only when the registered result is current, its registry entry holds
what the cell reads (the split's row keys, the fit's features and special values), and its
recomputation is exact with this plain code: a binned or folded group table, a capacity cut that splits a
tie group (counted pro rata by the engine), or a target that is not a plain column is
explained in words instead (:func:`skipped`).

Every name a cell defines is unique in the notebook (Marimo runs cells as a graph of
definitions); loop variables start with ``_`` (local to their cell in Marimo).

This module generates text only: it imports neither pandas nor scikit-learn.
"""
from __future__ import annotations

import json
from typing import Any, Mapping


def q(text: Any) -> str:
    """A string literal of the generated code, in double quotes."""
    return json.dumps(str(text), ensure_ascii=False)

TOLERANCE = 1e-9
FIT_TOLERANCE = 1e-6
SPECIAL_SUFFIX = ' (special value)'

IMPORTS = '''import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import {model}
from sklearn.metrics import {metric}
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

# Recomputed figures must equal the registered ones: counts exactly, rates and means
# up to rounding (TOLERANCE), a refitted model's metric up to solver noise (FIT_TOLERANCE).
TOLERANCE = 1e-9
FIT_TOLERANCE = 1e-6'''


def imports(task: str) -> str:
    """The imports cell of the recomputation (the model and metric of the task)."""
    if task == 'regression':
        return IMPORTS.format(model='LinearRegression', metric='mean_absolute_error')
    return IMPORTS.format(model='LogisticRegression', metric='roc_auc_score')


def _current(view: Mapping, slot: str) -> Mapping | None:
    item = view['results'].get(slot)
    if item and item['current'] and item['integrity'] == 'ok' \
            and isinstance(item.get('values'), Mapping):
        return item
    return None


def _positive_expr(frame: str, target: str, positive: Any) -> str:
    return f'({frame}[{q(target)}].astype(str) == {q(str(positive))})'


def is_cv(view: Mapping) -> bool:
    """WP-B1: whether the current split is a cross-validation (its result holds folds)."""
    item = _current(view, 'split')
    return bool(item) and 'folds' in (item.get('blobs') or {})


def split_cell(view: Mapping, task: str) -> tuple[str, str] | None:
    item = _current(view, 'split')
    # The registry entry must hold what the cell reads: the row keys of both partitions.
    if item is None or not {'train', 'validation'} <= set(item.get('blobs') or {}):
        return None
    if is_cv(view):
        code = f'''# The development rows only: the final test stays sealed and is never loaded.
# Cross-validation: every development row is explored, and each fold is predicted by a
# model fitted on the other folds. "folds" says which fold each row belongs to.
development = nv.development_frame(study, RESULT_IDS["split"])
split = nv.values(study, RESULT_IDS["split"])
folds = nv.folds(study, RESULT_IDS["split"])
train = development
validation = development
fold_counts = folds.value_counts().sort_index()
print(fold_counts)

assert len(development) == split["n_rows"]
for _item in split["fold_rows"]:
    assert fold_counts[_item["fold"]] == _item["n_rows"]'''
        return 'recompute_split', code
    code = f'''# The development rows only: the final test stays sealed and is never loaded.
# "partition" says whether each row trains the models or validates them.
development = nv.development_frame(study, RESULT_IDS["split"])
split = nv.values(study, RESULT_IDS["split"])

train = development[development["partition"] == "train"]
validation = development[development["partition"] == "validation"]
partition_counts = development["partition"].value_counts()
print(partition_counts)

assert len(development) == split["n_rows"]
assert partition_counts["train"] == split["partitions"]["train"]["n_rows"]
assert partition_counts["validation"] == split["partitions"]["validation"]["n_rows"]'''
    return 'recompute_split', code


def target_cell(view: Mapping, task: str, target: str, positive: Any) -> tuple[str, str] | None:
    if task == 'regression':
        if _current(view, 'eda.target_summary') is None:
            return None
        code = f'''target_summary = nv.values(study, RESULT_IDS["eda.target_summary"])
train_target = pd.to_numeric(train[{q(target)}])
print(train_target.describe())

assert train_target.count() == target_summary["n"]
assert abs(train_target.mean() - target_summary["mean"]) < TOLERANCE
assert abs(train_target.median() - target_summary["median"]) < TOLERANCE
assert abs(train_target.std() - target_summary["sd"]) < TOLERANCE'''
        return 'recompute_target', code
    if _current(view, 'eda.target_rate') is None:
        return None
    code = f'''target_rate = nv.values(study, RESULT_IDS["eda.target_rate"])
# 1 when the outcome is the positive label {q(str(positive))}, else 0.
train_positive = {_positive_expr("train", target, positive)}.astype(int)
print(f"{{train_positive.sum()}} positive rows of {{len(train)}} training rows: "
      f"rate {{train_positive.mean():.4f}}")

assert train_positive.sum() == target_rate["n_positive"]
assert len(train) == target_rate["n_rows"]
assert abs(train_positive.mean() - target_rate["rate"]) < TOLERANCE'''
    return 'recompute_target', code


def group_slot(view: Mapping, task: str) -> str | None:
    """The first rate_by (binary) or mean_by (regression) slot that plain code recomputes
    exactly: not binned, not folded, without a missing-value group."""
    prefix = 'eda.mean_by:' if task == 'regression' else 'eda.rate_by:'
    for slot in sorted(s for s in view['results'] if s.startswith(prefix)):
        item = _current(view, slot)
        if item is None:
            continue
        v = item['values']
        groups = v.get('groups') or []
        if v.get('binned') or v.get('other') or any(
                g.get('value') == '(missing)' for g in groups if isinstance(g, Mapping)):
            continue
        return slot
    return None


def group_cell(view: Mapping, task: str, target: str, positive: Any) -> tuple[str, str] | None:
    slot = group_slot(view, task)
    if slot is None:
        return None
    column = slot.split(':', 1)[1]
    if task == 'regression':
        code = f'''by_group = nv.values(study, RESULT_IDS[{q(slot)}])
# The mean of the target in each group of {q(column)}, on training rows.
group_means = (
    train.assign(target=pd.to_numeric(train[{q(target)}]))
    .groupby(train[{q(column)}].astype(str))["target"]
    .agg(["size", "mean"])
)
print(group_means)

for _group in by_group["groups"]:
    _value = _group["value"].removesuffix({q(SPECIAL_SUFFIX)})
    assert group_means.loc[_value, "size"] == _group["n_rows"]
    assert abs(group_means.loc[_value, "mean"] - _group["mean"]) < TOLERANCE'''
        return 'recompute_by_group', code
    code = f'''by_group = nv.values(study, RESULT_IDS[{q(slot)}])
# The positive rate in each group of {q(column)}, on training rows.
group_rates = (
    train.assign(positive=train_positive)
    .groupby(train[{q(column)}].astype(str))["positive"]
    .agg(["size", "sum", "mean"])
)
print(group_rates)

for _group in by_group["groups"]:
    _value = _group["value"].removesuffix({q(SPECIAL_SUFFIX)})
    assert group_rates.loc[_value, "size"] == _group["n_rows"]
    assert group_rates.loc[_value, "sum"] == _group["n_positive"]
    assert abs(group_rates.loc[_value, "mean"] - _group["rate"]) < TOLERANCE'''
    return 'recompute_by_group', code


PIPELINE = '''numeric = X_train.select_dtypes("number").columns.tolist()
categorical = [name for name in X_train.columns if name not in numeric]
prepare_columns = ColumnTransformer(
    [
        ("numeric", Pipeline([
            ("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("scale", StandardScaler()),
        ]), numeric),
        ("categorical", Pipeline([
            ("impute", SimpleImputer(strategy="most_frequent", keep_empty_features=True)),
            ("encode", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]), categorical),
    ]
)'''


def preparation_steps(values: Mapping) -> str | None:
    """WP-A9 (M3): the confirmed preparation of a fit as readable pandas steps, in the
    engine's order (missing-value indicators, rare categories grouped, caps, signed log),
    each learnt on the training rows only and applied unchanged to the validation rows. It
    reads what the fit recorded (``values.preprocessing``: the value and what was learnt),
    so the steps are the fit's own. None when the fit recorded no preparation (a study
    created before the decision)."""
    pre = values.get('preprocessing') if isinstance(values, Mapping) else None
    if not isinstance(pre, Mapping) or not isinstance(pre.get('value'), Mapping) \
            or not isinstance(pre.get('fitted'), Mapping):
        return None
    value, fitted = pre['value'], pre['fitted']
    lines = []
    for name in fitted.get('missing_indicators') or []:
        column = name[:-len('=(missing)')] if name.endswith('=(missing)') else name
        lines += [f'# Missing-value indicator for {column}: 1 where the cell is empty.',
                  f'X_train[{q(name)}] = train[{q(column)}].isna().astype(int).to_numpy()',
                  f'X_validation[{q(name)}] = validation[{q(column)}].isna().astype(int).to_numpy()']
    k = value.get('rare_category_min_rows')
    for column in fitted.get('rare_categories') or {}:
        lines += [f'# Categories of {column} with fewer than {k} training rows are grouped as '
                  f'"(rare)" (a category unseen in training too).',
                  f'_counts = X_train[{q(column)}].dropna().astype(str).value_counts()',
                  f'_kept = set(_counts[_counts >= {int(k)}].index)',
                  'for _X in (X_train, X_validation):',
                  f'    _text = _X[{q(column)}].map(lambda v: v if v != v else str(v))',
                  f'    _X[{q(column)}] = _text.where(_text.isna() | _text.isin(_kept), "(rare)")']
    for column, bounds in sorted((value.get('caps') or {}).items()):
        if column not in (fitted.get('caps') or {}):
            continue
        q_low, q_high = bounds
        lines += [f'# Cap {column} at its training quantiles {q_low} and {q_high}; values '
                  f'outside are clipped.',
                  f'_low = float(X_train[{q(column)}].quantile({q_low!r}))',
                  f'_high = float(X_train[{q(column)}].quantile({q_high!r}))',
                  f'X_train[{q(column)}] = X_train[{q(column)}].clip(_low, _high)',
                  f'X_validation[{q(column)}] = X_validation[{q(column)}].clip(_low, _high)']
    for column in fitted.get('log_transform') or []:
        lines += [f'# Signed log of {column}: sign(x) * log(1 + |x|), after the caps.',
                  'for _X in (X_train, X_validation):',
                  f'    _v = _X[{q(column)}].astype(float)',
                  f'    _X[{q(column)}] = np.sign(_v) * np.log1p(np.abs(_v))']
    if not lines:
        return '# The default preparation: nothing added, grouped, capped, or transformed.'
    return '\n'.join(lines)


CV_PIPELINE = '''def _prepare_columns(_X):
    _numeric = _X.select_dtypes("number").columns.tolist()
    _categorical = [_name for _name in _X.columns if _name not in _numeric]
    return ColumnTransformer(
        [
            ("numeric", Pipeline([
                ("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
                ("scale", StandardScaler()),
            ]), _numeric),
            ("categorical", Pipeline([
                ("impute", SimpleImputer(strategy="most_frequent", keep_empty_features=True)),
                ("encode", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
            ]), _categorical),
        ]
    )'''


def cv_fit_cell(view: Mapping, task: str, target: str, positive: Any,
                slot: str, item: Mapping) -> tuple[str, str] | None:
    """WP-B1: the candidate's out-of-fold metric, recomputed fold by fold: each fold is
    predicted by a model fitted (with its preparation) on the other folds."""
    head = f'''candidate = nv.values(study, RESULT_IDS[{q(slot)}])
# Cross-validation: each fold is predicted by a model fitted on the other folds, the
# preparation of the variables learnt on those rows too. Every development row gets one
# out-of-fold prediction.
print(nv.preprocessing_words(study, RESULT_IDS[{q(slot)}]))
{CV_PIPELINE}
'''
    if task == 'regression':
        code = head + f'''y_validation = pd.to_numeric(development[{q(target)}])
prediction = np.zeros(len(development))
for _fold in sorted(folds.unique()):
    _held = (folds == _fold).to_numpy()
    _X_fit, _X_held = nv.model_inputs(study, RESULT_IDS[{q(slot)}], development[~_held],
                                      development[_held])
    _model = Pipeline([("prepare", _prepare_columns(_X_fit)), ("model", LinearRegression())])
    _model.fit(_X_fit, y_validation[~_held])
    prediction[_held] = _model.predict(_X_held)
validation_mae = mean_absolute_error(y_validation, prediction)
print(f"Out-of-fold mean absolute error: {{validation_mae:.4f}}")

assert abs(validation_mae - candidate["validation"]["mae"]) < FIT_TOLERANCE'''
        return 'recompute_model', code
    seed = (item.get('params') or {}).get('seed')
    if not isinstance(seed, int):
        return None
    code = head + f'''y_validation = {_positive_expr("development", target, positive)}.astype(int)
score = np.zeros(len(development))
for _fold in sorted(folds.unique()):
    _held = (folds == _fold).to_numpy()
    _X_fit, _X_held = nv.model_inputs(study, RESULT_IDS[{q(slot)}], development[~_held],
                                      development[_held])
    _model = Pipeline([
        ("prepare", _prepare_columns(_X_fit)),
        ("model", LogisticRegression(max_iter=1000, random_state={seed})),
    ])
    _model.fit(_X_fit, y_validation[~_held])
    score[_held] = _model.predict_proba(_X_held)[:, 1]
validation_auc = roc_auc_score(y_validation, score)
print(f"Out-of-fold AUC: {{validation_auc:.4f}}")

assert abs(validation_auc - candidate["validation"]["roc_auc"]) < FIT_TOLERANCE'''
    return 'recompute_model', code


def fit_cell(view: Mapping, task: str, target: str, positive: Any) -> tuple[str, str] | None:
    slot = 'fit.linear' if task == 'regression' else 'fit.logistic'
    item = _current(view, slot)
    inputs = (item or {}).get('inputs')
    if item is None or not isinstance(inputs, Mapping) \
            or not {'features', 'special_values'} <= set(inputs):
        return None
    if is_cv(view):
        # Under cross-validation the preparation is learnt on each fold's training rows.
        return cv_fit_cell(view, task, target, positive, slot, item)
    steps = preparation_steps(item['values'])
    if steps is None:
        head = f'''candidate = nv.values(study, RESULT_IDS[{q(slot)}])
# The inputs exactly as the model saw them: the features you kept and special values as
# indicator columns.
X_train, X_validation = nv.model_inputs(study, RESULT_IDS[{q(slot)}], train, validation)
print(nv.preprocessing_words(study, RESULT_IDS[{q(slot)}]))
'''
    else:
        head = f'''candidate = nv.values(study, RESULT_IDS[{q(slot)}])
# The inputs as the model saw them: the features you kept, special values as indicator
# columns.
X_train, X_validation = nv.design_inputs(study, RESULT_IDS[{q(slot)}], train, validation)
print(nv.preprocessing_words(study, RESULT_IDS[{q(slot)}]))
# The preparation you confirmed, learnt on the training rows only and applied unchanged
# to the validation rows.
{steps}
# The same inputs as the engine's fit.
_engine_train, _engine_validation = nv.model_inputs(study, RESULT_IDS[{q(slot)}], train,
                                                    validation)
pd.testing.assert_frame_equal(X_train, _engine_train)
pd.testing.assert_frame_equal(X_validation, _engine_validation)
'''
    if task == 'regression':
        code = head + f'''y_train = pd.to_numeric(train[{q(target)}])
y_validation = pd.to_numeric(validation[{q(target)}])

{PIPELINE}
model = Pipeline([("prepare", prepare_columns), ("model", LinearRegression())])
model.fit(X_train, y_train)
prediction = model.predict(X_validation)
validation_mae = mean_absolute_error(y_validation, prediction)
print(f"Validation mean absolute error: {{validation_mae:.4f}}")

assert abs(validation_mae - candidate["validation"]["mae"]) < FIT_TOLERANCE'''
        return 'recompute_model', code
    seed = (item.get('params') or {}).get('seed')
    if not isinstance(seed, int):
        return None
    code = head + f'''y_train = {_positive_expr("train", target, positive)}.astype(int)
y_validation = {_positive_expr("validation", target, positive)}.astype(int)

{PIPELINE}
model = Pipeline([
    ("prepare", prepare_columns),
    ("model", LogisticRegression(max_iter=1000, random_state={seed})),
])
model.fit(X_train, y_train)
score = model.predict_proba(X_validation)[:, 1]
validation_auc = roc_auc_score(y_validation, score)
print(f"Validation AUC: {{validation_auc:.4f}}")

assert abs(validation_auc - candidate["validation"]["roc_auc"]) < FIT_TOLERANCE'''
    return 'recompute_model', code


def _adopted_rule(view: Mapping) -> str | None:
    policy = view['decisions'].get('policy') or {}
    criterion = view.get('criterion') or {}
    if policy.get('status') == 'confirmed' and isinstance(policy.get('value'), str):
        if '@' in policy['value']:
            return None      # WP-B1: a rule of the variant; the cell recomputes the candidate
        return policy['value']
    if criterion.get('model') not in (None, 'fit.logistic'):
        return None
    return criterion.get('rule')


def policy_cell(view: Mapping) -> tuple[str, str] | None:
    item = _current(view, 'policy.evaluation')
    rule = _adopted_rule(view)
    if item is None or rule is None or _current(view, 'fit.logistic') is None:
        return None
    entry = ((item['values'].get('rules') or {}).get(rule) or {}).get('models', {}) \
        .get('fit.logistic')
    if not isinstance(entry, Mapping) or entry.get('tied_at_cut'):
        return None                    # a tie at the cut is counted pro rata by the engine
    kind, _, amount = rule.partition(':')
    if kind == 'share':
        # v0.2b: a share of the n validation rows is a capacity of round(p * n) rows.
        amount = str(entry.get('capacity') or '')
        kind = 'capacity' if amount.isdigit() else kind
    if kind == 'capacity':
        select = (f'''# The {amount} validation rows with the highest scores.
order = np.argsort(-score, kind="stable")
selected = np.zeros(len(score), dtype=bool)
selected[order[:{int(amount)}]] = True''')
    elif kind == 'threshold':
        select = f'''# Every validation row scored {amount} or more.
selected = score >= {float(amount)!r}'''
    else:
        return None
    code = f'''policy = nv.values(study, RESULT_IDS["policy.evaluation"])
at_rule = policy["rules"][{q(rule)}]["models"]["fit.logistic"]
{select}
found = int(y_validation.to_numpy()[selected].sum())
precision = found / selected.sum()
print(f"{{selected.sum()}} rows selected, {{found}} positive: precision {{precision:.4f}}")

assert selected.sum() == at_rule["selected"]
assert found == at_rule["true_positives"]
assert abs(precision - at_rule["precision"]) < TOLERANCE'''
    return 'recompute_policy', code


def baseline_error_cell(view: Mapping, target: str) -> tuple[str, str] | None:
    if _current(view, 'evaluate.regression') is None or _current(view, 'fit.linear') is None:
        return None
    if is_cv(view):
        code = '''evaluation = nv.values(study, RESULT_IDS["evaluate.regression"])
# The baseline predicts, for each fold, the mean of the other folds.
baseline_prediction = np.zeros(len(development))
for _fold in sorted(folds.unique()):
    _held = (folds == _fold).to_numpy()
    baseline_prediction[_held] = y_validation[~_held].mean()
baseline_mae = np.abs(y_validation.to_numpy() - baseline_prediction).mean()
print(f"Baseline MAE {baseline_mae:.4f}, linear model MAE {validation_mae:.4f}")

assert abs(baseline_mae - evaluation["models"]["fit.baseline"]["mae"]) < TOLERANCE
assert abs(validation_mae - evaluation["models"]["fit.linear"]["mae"]) < FIT_TOLERANCE'''
        return 'recompute_comparison', code
    code = '''evaluation = nv.values(study, RESULT_IDS["evaluate.regression"])
# The baseline predicts the training mean for every validation row.
baseline_mae = (y_validation - y_train.mean()).abs().mean()
print(f"Baseline MAE {baseline_mae:.4f}, linear model MAE {validation_mae:.4f}")

assert abs(baseline_mae - evaluation["models"]["fit.baseline"]["mae"]) < TOLERANCE
assert abs(validation_mae - evaluation["models"]["fit.linear"]["mae"]) < FIT_TOLERANCE'''
    return 'recompute_comparison', code


# --- WP-B4: the diagnostics, recomputed from the stored predictions ---------------------------

def _diag_model(view: Mapping, item: Mapping, final: bool) -> str | None:
    values = item['values']
    models = list(values.get('models') or {})
    if final:
        return values.get('model') if values.get('model') in models else None
    wanted = (view.get('criterion') or {}).get('model')
    if wanted in models:
        return wanted
    return next((m for m in ('fit.logistic', 'fit.linear') if m in models), None)


def diagnostics_cell(view: Mapping, task: str, final: bool = False) -> tuple[str, str] | None:
    """WP-B4: the confusion matrix at the rule and the calibration bins (binary), or the
    residuals by bin of prediction (regression), recomputed with numpy from the stored
    predictions the diagnostics read, and asserted equal to the registry. A rule whose cut
    splits a tie group (counted pro rata by the engine) is explained instead."""
    slot = 'diag.final_test' if final else ('diag.regression' if task == 'regression'
                                            else 'diag.binary')
    item = _current(view, slot)
    if item is None:
        return None
    model = _diag_model(view, item, final)
    if model is None:
        return None
    p = 'final_' if final else 'dev_'
    name = f'recompute_{p}diagnostics'
    rows = 'final-test row' if final else 'development row'
    head = f'''{p}diagnostics = nv.values(study, RESULT_IDS[{q(slot)}])
{p}model = {p}diagnostics["models"][{q(model)}]
# The predictions the diagnostics read: one per {rows}, stored by the model's evaluation.
{p}predicted = study.predictions({p}model["predictions"])
{p}y = {p}predicted["y"].to_numpy(dtype=float)
'''
    if task == 'regression':
        code = head + f'''{p}prediction = {p}predicted["prediction"].to_numpy(dtype=float)
{p}residual = {p}y - {p}prediction
# Ten bins of equal size in prediction order (a stable sort keeps tied rows in file order).
{p}order = np.argsort({p}prediction, kind="stable")
{p}bins = np.empty(len({p}prediction), dtype=int)
{p}bins[{p}order] = np.arange(len({p}prediction)) * 10 // len({p}prediction)
{p}by_bin = pd.DataFrame({{"bin": {p}bins + 1, "prediction": {p}prediction,
                         "residual": {p}residual}}).groupby("bin").agg(
    n=("residual", "size"), mean_residual=("residual", "mean"))
print({p}by_bin)

assert abs({p}residual.mean() - {p}model["residuals"]["mean"]) < TOLERANCE
for _item in {p}model["by_prediction"]["bins"]:
    assert {p}by_bin.loc[_item["bin"], "n"] == _item["n"]
    assert abs({p}by_bin.loc[_item["bin"], "mean_residual"] - _item["mean_residual"]) < TOLERANCE'''
        return name, code
    conf = (item['values']['models'][model] or {}).get('confusion') or {}
    rule = str(item['values'].get('rule') or '')
    kind, _, amount = rule.partition(':')
    if conf.get('tied_at_cut') or conf.get('selection') != 'exact':
        return None
    if kind in ('capacity', 'share'):
        k = str(conf.get('capacity') if kind == 'share' else amount)
        if not k.isdigit():
            return None
        select = (f'# The rule {rule}: the {int(k)} rows with the highest scores.\n'
                  f'{p}selected = np.zeros(len({p}score), dtype=bool)\n'
                  f'{p}selected[np.argsort(-{p}score, kind="stable")[:{int(k)}]] = True')
    elif kind == 'threshold':
        select = (f'# The rule {rule}: every row scored {amount} or more.\n'
                  f'{p}selected = {p}score >= {float(amount)!r}')
    else:
        return None
    code = head + f'''{p}score = {p}predicted["score"].to_numpy(dtype=float)
{select}
{p}positive = {p}y == 1
{p}confusion = {{
    "true_positives": int(({p}selected & {p}positive).sum()),
    "false_positives": int(({p}selected & ~{p}positive).sum()),
    "false_negatives": int((~{p}selected & {p}positive).sum()),
    "true_negatives": int((~{p}selected & ~{p}positive).sum()),
}}
print({p}confusion)
for _key, _count in {p}confusion.items():
    assert _count == {p}model["confusion"][_key], _key

# Calibration: ten bins of equal size in score order (a stable sort keeps tied rows in file
# order), the mean score against the observed positive rate, and the Brier score.
{p}order = np.argsort({p}score, kind="stable")
{p}bins = np.empty(len({p}score), dtype=int)
{p}bins[{p}order] = np.arange(len({p}score)) * 10 // len({p}score)
{p}calibration = pd.DataFrame({{"bin": {p}bins + 1, "score": {p}score,
                              "y": {p}y}}).groupby("bin").agg(
    n=("y", "size"), mean_predicted=("score", "mean"), observed_rate=("y", "mean"))
print({p}calibration)
for _item in {p}model["calibration"]["bins"]:
    _row = {p}calibration.loc[_item["bin"]]
    assert _row["n"] == _item["n"]
    assert abs(_row["mean_predicted"] - _item["mean_predicted"]) < TOLERANCE
    assert abs(_row["observed_rate"] - _item["observed_rate"]) < TOLERANCE
assert abs(np.mean(({p}score - {p}y) ** 2) - {p}model["calibration"]["brier"]) < TOLERANCE'''
    return name, code


def cells_by_step(view: Mapping, task: str, target: str | None,
                  positive: Any) -> dict[str, list[tuple[str, str]]]:
    """Step id -> recomputation cells (name, code), in notebook order."""
    out: dict[str, list[tuple[str, str]]] = {}
    if target is None:
        return out
    split = split_cell(view, task)
    if split is None:
        return out
    out['split'] = [split]
    target_code = target_cell(view, task, target, positive)
    group_code = group_cell(view, task, target, positive)
    if task != 'regression' and target_code is None:
        group_code = None          # a binary group cell reads ``train_positive``
    eda = [c for c in (target_code, group_code) if c]
    if eda:
        out['train_eda'] = eda
    fit = fit_cell(view, task, target, positive)
    if fit:
        out['models'] = [fit]
        if task == 'regression':
            comparison = baseline_error_cell(view, target)
            if comparison:
                out['model_choice'] = [comparison]
        else:
            policy = policy_cell(view)
            if policy:
                out['policy'] = [policy]
    # WP-B4: the diagnostics, with the choice they describe and with the final test.
    choice = 'model_choice' if task == 'regression' else 'policy'
    development = diagnostics_cell(view, task)
    if development:
        out.setdefault(choice, []).append(development)
    final = diagnostics_cell(view, task, final=True)
    if final:
        out.setdefault('final_test', []).append(final)
    return out


def skipped() -> str:
    return ('_No recomputation cell for this step: plain code would not reproduce the '
            'registered result exactly (binned or folded groups, a tie at the cut counted pro '
            'rata, or no current result). The engine view below shows the registered figures._')
