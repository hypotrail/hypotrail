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
mean by group, the candidate model's validation metric with the confirmed preprocessing,
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


def split_cell(view: Mapping, task: str) -> tuple[str, str] | None:
    item = _current(view, 'split')
    # The registry entry must hold what the cell reads: the row keys of both partitions.
    if item is None or not {'train', 'validation'} <= set(item.get('blobs') or {}):
        return None
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


def fit_cell(view: Mapping, task: str, target: str, positive: Any) -> tuple[str, str] | None:
    slot = 'fit.linear' if task == 'regression' else 'fit.logistic'
    item = _current(view, slot)
    inputs = (item or {}).get('inputs')
    if item is None or not isinstance(inputs, Mapping) \
            or not {'features', 'special_values'} <= set(inputs):
        return None
    head = f'''candidate = nv.values(study, RESULT_IDS[{q(slot)}])
# The inputs exactly as the model saw them: the features you kept, special values as
# indicator columns, and the preparation you confirmed, learnt on training rows only.
X_train, X_validation = nv.model_inputs(study, RESULT_IDS[{q(slot)}], train, validation)
print("Preparation:", nv.preprocessing_words(study, RESULT_IDS[{q(slot)}]))
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
        return policy['value']
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
    code = '''evaluation = nv.values(study, RESULT_IDS["evaluate.regression"])
# The baseline predicts the training mean for every validation row.
baseline_mae = (y_validation - y_train.mean()).abs().mean()
print(f"Baseline MAE {baseline_mae:.4f}, linear model MAE {validation_mae:.4f}")

assert abs(baseline_mae - evaluation["models"]["fit.baseline"]["mae"]) < TOLERANCE
assert abs(validation_mae - evaluation["models"]["fit.linear"]["mae"]) < FIT_TOLERANCE'''
    return 'recompute_comparison', code


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
    return out


def skipped() -> str:
    return ('_No recomputation cell for this step: plain code would not reproduce the '
            'registered result exactly (binned or folded groups, a tie at the cut counted pro '
            'rata, or no current result). The engine view below shows the registered figures._')
