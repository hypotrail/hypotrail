"""Spec L-08 / AC06 / AC07: the complete predictor reproduces the engine's fit path.

The engine fits with its preparation outside the scikit-learn pipeline
(``fit.design`` + ``fit.prepare`` + ``mlkit.classical.pipeline``). The runtime pipeline
(``hypotrail_runtime.preprocess``) carries the same rules; on the same training rows it must
predict the same held-out rows within the declared float64 tolerance (rtol 1e-10, atol
1e-12), fold by fold (state learnt on each fold's training rows only).
"""
from __future__ import annotations

import numpy as np
import pytest

from hypotrail_runtime import fit_predictor
from hypotrail_runtime.errors import ContractError
from mlkit.contracts.recipe import data_contract_from_case, recipe_from_fit
from mlkit.study import fit, governance

import libkit

RTOL, ATOL = 1e-10, 1e-12
SCOPE = {'role': 'fold_fit', 'dataset_id': 'x', 'membership_sha256': '0' * 64,
         'protocol_id': None}

RICH = {**governance.DEFAULT_PREPROCESSING, 'missing': 'indicator',
        'rare_category_min_rows': 30}


def _parity(flow, *, n_folds=None):
    case, frame = libkit.development(flow)
    inputs, params = libkit.candidate_plan(flow)
    folds = libkit.folds(flow)
    binary = case.task == 'binary'
    contract = data_contract_from_case(case, frame, dataset_sha256='0' * 64,
                                       features=list(inputs['features']))
    checked = 0
    for i in sorted(set(folds.values()))[:n_folds]:
        held = [k for k in frame.index if folds[k] == i]
        rest = [k for k in frame.index if folds[k] != i]
        train, test = fit._ordered(frame.loc[rest]), fit._ordered(frame.loc[held])
        expected = fit._fit_predict(case, train, test, inputs, params, binary)[0]
        recipe, _ = recipe_from_fit(case, train, inputs, params)
        fitted = fit_predictor(recipe, contract, train, SCOPE)
        got = fitted.predict(test[list(recipe.features)]).values
        np.testing.assert_allclose(got, expected, rtol=RTOL, atol=ATOL)
        # The learnt state comes from the fold's training rows only.
        state = fitted.learnt_state()
        for column, (low, high) in state['caps'].items():
            assert low == float(fit.design(train, list(inputs['features']),
                                           list(inputs['special_values']), case)[0][column]
                                .quantile(inputs['preprocessing']['caps'][column][0]))
        checked += 1
    assert checked
    return recipe


@pytest.mark.parametrize('task', ['binary', 'regression'])
def test_runtime_reproduces_engine_fold_fits_with_default_preprocessing(tmp_path, task):
    flow = libkit.study_at_fits(tmp_path, task=task)
    recipe = _parity(flow)
    ops = [s.operation for s in recipe.preprocessing]
    assert ops[0] == 'category_as_text' and ops[-1] == 'categorical_mode_impute_onehot'


@pytest.mark.parametrize('task', ['binary', 'regression'])
def test_runtime_reproduces_engine_with_every_preparation_rule(tmp_path, task):
    flow = libkit.study_at_fits(tmp_path, task=task)
    case, frame = libkit.development(flow)
    numeric = [n for n in libkit.candidate_plan(flow)[0]['features']
               if str(frame[n].dtype).startswith(('float', 'int'))]
    pre = {**RICH, 'caps': {numeric[0]: [0.05, 0.95]}, 'log_transform': numeric[-1:]}
    flow2 = libkit.study_at_fits(tmp_path / 'rich', task=task, preprocessing=pre)
    recipe = _parity(flow2)
    ops = {s.operation for s in recipe.preprocessing}
    assert {'missing_indicator', 'rare_category', 'cap_quantiles', 'signed_log'} <= ops


def test_runtime_reproduces_engine_on_auto_mpg_development_rows(tmp_path):
    flow = libkit.study_at_fits(tmp_path, case_dir=libkit.AUTO)
    recipe = _parity(flow, n_folds=2)
    assert recipe.task == 'regression' and recipe.output_contract.unit == 'mpg'


def test_unqualified_family_is_refused_not_replaced(tmp_path):
    flow = libkit.study_at_fits(tmp_path, task='binary', n_rows=300)
    case, frame = libkit.development(flow)
    inputs, params = libkit.candidate_plan(flow)
    with pytest.raises(ContractError) as e:
        recipe_from_fit(case, frame, inputs, {**params, 'family': 'hgb'})
    assert e.value.code == 'capability_not_supported'
    assert e.value.details['family'] == 'hgb'
