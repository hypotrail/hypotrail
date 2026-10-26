"""Owner session 2026-10-26, lot L8 (R6, D7): rare categories grouped per column, in the fit,
the recipe and the runtime.

``rare_category_min_rows`` is one integer for every categorical feature (as before) or a
mapping ``{column: min_rows}`` (a column it leaves out keeps every category). The engine's
fit (``fit.prepare``) applies each column's own minimum; the recipe writes the operation
``rare_category`` in version 1 for an integer (unchanged bytes) and in version 2 for a
mapping; the runtime reads both versions and reproduces the engine's fit fold by fold within
the declared float64 tolerance (rtol 1e-10, atol 1e-12, never relaxed).
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

from hypotrail_runtime import fit_predictor, validate_recipe
from hypotrail_runtime.errors import ContractError
from hypotrail_runtime.preprocess import (OPERATION_VERSIONS, HypotrailPreparation,
                                          preparation_from_recipe)
from mlkit.contracts.recipe import data_contract_from_case, recipe_from_fit
from mlkit.study import fit, governance

import libkit
from test_predictor_parity import _parity

PER_COLUMN = {'last_lapse_reason': 50, 'last_reminder_weekday': 70}


def _prep(value) -> dict:
    return {**governance.DEFAULT_PREPROCESSING, 'rare_category_min_rows': value}


@pytest.fixture(scope='module')
def binary_flow(tmp_path_factory):
    return libkit.study_at_fits(tmp_path_factory.mktemp('rare-bin'), task='binary', n_rows=600)


def _frames(flow, preprocessing):
    """The prepared training and held-out inputs of the first fold, with ``preprocessing``."""
    case, frame = libkit.development(flow)
    inputs, _ = libkit.candidate_plan(flow)
    folds = libkit.folds(flow)
    held = [k for k in frame.index if folds[k] == 1]
    rest = [k for k in frame.index if folds[k] != 1]
    train, test = fit._ordered(frame.loc[rest]), fit._ordered(frame.loc[held])
    features, special = list(inputs['features']), list(inputs['special_values'])
    X_train, _ = fit.design(train, features, special, case)
    X_test, _ = fit.design(test, features, special, case)
    return fit.prepare(case, train, test, X_train, X_test, features, preprocessing, special), \
        train, features


def test_the_fit_groups_each_column_with_its_own_minimum(binary_flow):
    (X_train, X_test, fitted), train, features = _frames(binary_flow, _prep(PER_COLUMN))
    (D_train, D_test, _), _, _ = _frames(binary_flow, _prep(0))
    assert set(fitted['rare_categories']) == set(PER_COLUMN)
    for column, k in PER_COLUMN.items():
        counts = D_train[column].dropna().astype(str).value_counts()
        kept = set(counts[counts >= k].index)
        assert fitted['rare_categories'][column] == {'kept': len(kept),
                                                     'folded': sorted(set(counts.index) - kept)}
        assert fitted['rare_categories'][column]['folded'], column     # the case folds some
        assert set(X_train[column].dropna()) == kept | {governance.RARE_GROUP}
        assert set(X_test[column].dropna()) <= kept | {governance.RARE_GROUP}
    # A column the mapping leaves out keeps every category, and so does every numeric one.
    for column in features:
        if column not in PER_COLUMN:
            pd.testing.assert_series_equal(X_train[column], D_train[column])
            pd.testing.assert_series_equal(X_test[column], D_test[column])
    assert fitted['ignored'] == []


def test_an_integer_still_applies_to_every_categorical_column(binary_flow):
    """The integer reads exactly as a mapping that gives every categorical feature that
    minimum: the frames and what was learnt are the same."""
    (X_train, X_test, fitted), _, features = _frames(binary_flow, _prep(70))
    categorical = {c: 70 for c in features if not pd.api.types.is_numeric_dtype(X_train[c])}
    (M_train, M_test, mapped), _, _ = _frames(binary_flow, _prep(categorical))
    pd.testing.assert_frame_equal(X_train, M_train)
    pd.testing.assert_frame_equal(X_test, M_test)
    assert fitted['rare_categories'] == mapped['rare_categories'] != {}
    assert fitted['ignored'] == mapped['ignored'] == []


def test_a_mapping_naming_an_unused_feature_is_listed_as_ignored(binary_flow):
    case, _ = libkit.development(binary_flow)
    inputs, _ = libkit.candidate_plan(binary_flow)
    unused = [v['name'] for v in case.document['variables']
              if v['role'] == 'feature' and v['type'] == 'category'
              and v['name'] not in inputs['features']]
    value = dict(PER_COLUMN)
    if unused:
        value[unused[0]] = 10
    (_, _, fitted), _, _ = _frames(binary_flow, _prep(value))
    assert fitted['ignored'] == sorted(unused[:1])


def _recipe(flow, preprocessing):
    case, frame = libkit.development(flow)
    inputs, params = libkit.candidate_plan(flow)
    inputs = {**inputs, 'preprocessing': preprocessing}
    return recipe_from_fit(case, frame, inputs, params)[0]


def _rare_steps(recipe) -> list[dict]:
    return [{'operation': s.operation, 'version': s.version, 'parameters': dict(s.parameters)}
            for s in recipe.preprocessing if s.operation == 'rare_category']


def test_the_recipe_writes_version_1_for_an_integer_and_version_2_for_a_mapping(binary_flow):
    inputs, _ = libkit.candidate_plan(binary_flow)
    assert _rare_steps(_recipe(binary_flow, _prep(30))) == [
        {'operation': 'rare_category', 'version': 1, 'parameters': {'min_rows': 30}}]
    assert _rare_steps(_recipe(binary_flow, _prep(0))) == []
    mapping = {'last_reminder_weekday': 70, 'home_branch': 0, 'last_lapse_reason': 50}
    [step] = _rare_steps(_recipe(binary_flow, _prep(mapping)))
    assert step['operation'] == 'rare_category' and step['version'] == 2
    # The features the fit uses, in their order; a zero keeps every category (left out).
    order = [c for c in inputs['features'] if c in PER_COLUMN]
    assert list(step['parameters']['min_rows']) == order
    assert dict(step['parameters']['min_rows']) == PER_COLUMN
    assert _rare_steps(_recipe(binary_flow, _prep({'home_branch': 0}))) == []


@pytest.mark.parametrize('task', ['binary', 'regression'])
def test_the_runtime_reproduces_a_per_column_grouping_fold_by_fold(tmp_path, task):
    flow = libkit.study_at_fits(tmp_path / 'probe', task=task, n_rows=600)
    case, frame = libkit.development(flow)
    inputs, _ = libkit.candidate_plan(flow)
    # A category is read as text (``category_as_text``) even when its values are numbers.
    categorical = [n for n in inputs['features'] if case.variables[n]['type'] == 'category']
    assert categorical
    mapping = {categorical[0]: 40}
    if len(categorical) > 1:
        mapping[categorical[-1]] = 70
    pre = {**governance.DEFAULT_PREPROCESSING, 'missing': 'indicator',
           'rare_category_min_rows': mapping}
    flow2 = libkit.study_at_fits(tmp_path / 'rich', task=task, n_rows=600, preprocessing=pre)
    recipe = _parity(flow2)
    [step] = _rare_steps(recipe)
    assert step['version'] == 2 and dict(step['parameters']['min_rows']) == mapping


def test_the_runtime_reads_both_versions_and_refuses_others(binary_flow):
    assert OPERATION_VERSIONS['rare_category'] == (1, 2)
    assert all(v == (1,) for k, v in OPERATION_VERSIONS.items() if k != 'rare_category')
    doc = _recipe(binary_flow, _prep(PER_COLUMN)).model_dump(mode='json')
    prep = preparation_from_recipe(validate_recipe(doc))
    assert prep.rare_min_rows == PER_COLUMN
    v1 = _recipe(binary_flow, _prep(30)).model_dump(mode='json')
    assert preparation_from_recipe(validate_recipe(v1)).rare_min_rows == 30

    def refused(edit) -> ContractError:
        """The step is refused when the preparation is built (fit, capture, export)."""
        bad = copy.deepcopy(doc)
        [step] = [s for s in bad['preprocessing'] if s['operation'] == 'rare_category']
        edit(step)
        with pytest.raises(ContractError) as e:
            preparation_from_recipe(validate_recipe(bad))
        assert e.value.code == 'contract_invalid'
        return e.value

    assert 'version 3 of rare_category' in refused(lambda s: s.update(version=3)).message
    refused(lambda s: s.update(version=1))                     # a mapping is not version 1
    refused(lambda s: s['parameters'].update(min_rows=30))     # an integer is not version 2
    refused(lambda s: s['parameters'].update(min_rows={}))
    refused(lambda s: s['parameters'].update(min_rows={'last_lapse_reason': 0}))
    refused(lambda s: s['parameters'].update(min_rows={'last_lapse_reason': True}))
    assert 'is not a feature' in refused(
        lambda s: s['parameters'].update(min_rows={'no_such_column': 5})).message
    bad = copy.deepcopy(doc)
    bad['preprocessing'][0]['version'] = 2                     # category_as_text has only 1
    with pytest.raises(ContractError):
        preparation_from_recipe(validate_recipe(bad))


def test_a_version_1_preparation_is_unchanged(binary_flow):
    """The runtime's version-1 path learns what it learnt before: every categorical column
    with the one minimum."""
    case, frame = libkit.development(binary_flow)
    inputs, _ = libkit.candidate_plan(binary_flow)
    features = list(inputs['features'])
    one = HypotrailPreparation(features=features, rare_min_rows=70).fit(frame)
    categorical = [c for c in features if not pd.api.types.is_numeric_dtype(frame[c])]
    many = HypotrailPreparation(features=features,
                                rare_min_rows={c: 70 for c in categorical}).fit(frame)
    assert one.learnt_state() == many.learnt_state()
    assert set(one.rare_kept_) == set(categorical)
    pd.testing.assert_frame_equal(one.transform(frame), many.transform(frame))
    some = HypotrailPreparation(features=features,
                                rare_min_rows={categorical[0]: 70}).fit(frame)
    assert set(some.rare_kept_) == {categorical[0]}


def test_the_captured_contract_keeps_a_per_column_recipe(binary_flow):
    case, frame = libkit.development(binary_flow)
    recipe = _recipe(binary_flow, _prep(PER_COLUMN))
    contract = data_contract_from_case(case, frame, dataset_sha256='0' * 64,
                                       features=list(recipe.features))
    fitted = fit_predictor(recipe, contract, frame, {'role': 'fold_fit', 'dataset_id': 'x',
                                                     'membership_sha256': '0' * 64,
                                                     'protocol_id': None})
    state = fitted.learnt_state()
    assert set(state['rare_categories']) == set(PER_COLUMN)
    scores = fitted.predict(frame[list(recipe.features)]).values
    assert np.isfinite(np.asarray(scores, dtype=float)).all()
