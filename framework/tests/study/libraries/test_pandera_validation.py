"""Spec L-07 / AC03: Pandera derived from the DataContract, no silent mutation."""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

from hypotrail_runtime import validate_data_contract
from hypotrail_runtime.errors import ContractError
from hypotrail_runtime.inference import check_frame
from mlkit.integrations import pandera_validation as pv

import docs_v1

AUTH = ('development',)


def _frame(n=6) -> pd.DataFrame:
    return pd.DataFrame({
        'age': [30.0, 41.5, np.nan, 25.0, 60.0, 33.0][:n],
        'branch': ['Alder', 'Brook', 'Alder', None, 'Brook', 'Alder'][:n],
        'band': np.array([1, 2, 3, 1, 2, 3][:n], dtype='int64'),
        'renewed': ['yes', 'no', 'no', 'yes', 'no', 'yes'][:n],
        'member_id': [f'm{i}' for i in range(n)]}, index=[f'r{i}' for i in range(n)])


def _validate(frame, purpose='inference', contract=docs_v1.DATA_CONTRACT):
    before = frame.copy(deep=True)
    out = pv.validate(contract, frame, partition='development', authorized=AUTH,
                      purpose=purpose)
    pd.testing.assert_frame_equal(frame, before)            # never mutated, order kept
    return out


def _checks(report) -> set:
    return {(i['column'], i['check']) for i in report['issues']}


def test_valid_rows_pass_for_both_purposes():
    assert _validate(_frame())['status'] == 'ok'
    assert _validate(_frame(), 'training')['status'] == 'ok'


def test_target_absent_at_inference_only_and_columns_may_be_permuted():
    frame = _frame().drop(columns=['renewed'])[['member_id', 'band', 'age', 'branch']]
    assert _validate(frame)['status'] == 'ok'
    report = _validate(frame, 'training')
    assert report['status'] == 'failed'
    assert report['issues'] == [{'column': None, 'check': 'column_in_dataframe', 'n_rows': 1,
                                 'rows': [], 'values': ['renewed']}]


@pytest.mark.parametrize('column, values, check', [
    ('band', [True, False, True, False, True, False], 'physical_type=int64'),    # bool as int
    ('age', ['30', '41.5', None, '25', '60', '33'], 'physical_type=float64'),  # numbers as text
    ('band', [1.0, 2.0, 3.0, 1.0, 2.0, 3.0], 'physical_type=int64'),          # no coercion
])
def test_wrong_physical_types_are_reported_not_coerced(column, values, check):
    frame = _frame()
    frame[column] = pd.Series(values, index=frame.index, dtype=object if column == 'age'
                              else None)
    report = _validate(frame)
    assert report['status'] == 'failed'
    assert (column, check) in _checks(report)


def test_unknown_and_duplicated_columns():
    frame = _frame()
    frame['extra'] = 1
    issue = _validate(frame)['issues'][0]
    assert (issue['column'], issue['check'], issue['values']) == \
        (None, 'column_in_schema', ['extra'])
    dup = pd.concat([_frame(), _frame()[['age']]], axis=1)
    assert _validate(dup)['issues'][0]['check'] == 'duplicate_columns'


def test_missing_values_where_forbidden_name_their_rows():
    frame = _frame()
    frame['band'] = pd.array([1, None, 3, 1, None, 3], dtype='Int64')
    report = _validate(frame)
    issue = next(i for i in report['issues'] if i['check'] == 'not_nullable')
    assert issue['column'] == 'band' and issue['rows'] == ['r1', 'r4']
    assert _validate(_frame())['status'] == 'ok'            # age may be missing


def test_duplicate_stable_keys_and_empty_set():
    frame = _frame()
    frame.loc['r5', 'member_id'] = 'm0'
    assert ('member_id', 'field_uniqueness') in _checks(_validate(frame))
    assert _validate(_frame().iloc[:0])['status'] == 'insufficient_data'


def test_unknown_categories_are_errors_only_when_the_predictor_does_not_handle_them():
    frame = _frame()
    frame.loc['r0', 'branch'] = 'Cedar'
    assert _validate(frame)['status'] == 'ok'               # predictor_handles
    strict = copy.deepcopy(docs_v1.DATA_CONTRACT)
    strict['inference_policy']['unknown_categories'] = 'reject'
    report = _validate(frame, contract=strict)
    issue = next(i for i in report['issues'] if i['column'] == 'branch')
    assert issue['values'] == ['Cedar'] and issue['rows'] == ['r0']


def test_an_unauthorised_partition_is_refused_before_reading():
    with pytest.raises(ContractError) as e:
        pv.validate(docs_v1.DATA_CONTRACT, _frame(), partition='final_test', authorized=AUTH)
    assert e.value.code == 'partition_not_authorized'


def test_pandera_and_the_runtime_read_the_same_contract():
    """Same verdict on each structural case (inference): one logical contract."""
    contract = validate_data_contract(docs_v1.DATA_CONTRACT)
    features = contract.features()
    cases = {'ok': _frame().drop(columns=['renewed'])}
    bad = _frame().drop(columns=['renewed'])
    bad['band'] = bad['band'].astype(bool)
    cases['bool_as_int'] = bad
    bad = _frame().drop(columns=['renewed', 'age'])
    cases['missing_column'] = bad
    bad = _frame().drop(columns=['renewed'])
    bad['zz'] = 0
    cases['unknown_column'] = bad
    bad = _frame().drop(columns=['renewed'])
    bad['band'] = pd.array([1, None, 3, 1, 2, 3], dtype='Int64')
    cases['forbidden_na'] = bad
    for name, frame in cases.items():
        pandera_ok = _validate(frame)['status'] == 'ok'
        try:
            check_frame(contract, frame, features=features)
            runtime_ok = True
        except ContractError:
            runtime_ok = False
        assert pandera_ok == runtime_ok, name
