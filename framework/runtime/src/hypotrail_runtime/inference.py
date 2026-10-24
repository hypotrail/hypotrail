"""The inference input contract: raw features checked against the DataContract.

The same logical contract drives the engine's Pandera schema
(``mlkit.integrations.pandera_validation``); this module is the runtime's dependency-free
reading of it, used before every prediction. Nothing is coerced, dropped, imputed or added
silently: a declared conversion (``inference_policy.conversions``) is applied to a copy and
reported; the caller's frame and its row order are never changed.

Every feature the recipe reads must be present, required by the contract or not: a feature
outside ``required_columns`` that the input lacks is ``missing_columns``, never a raw
``KeyError``. A string column is handed to the predictor as Python strings with ``NaN`` for
a missing value, whatever pandas representation held it (``object`` with ``None`` or
``NaN``, ``string[python]`` or ``string[pyarrow]`` with ``pd.NA``): the values are
unchanged, only the missing marker is the one the preparation and the parity rows read.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .contracts import DataContract, ModelRecipe
from .errors import ContractError

MAX_EXAMPLES = 5
CONVERSIONS = {('int64', 'float64'): 'int_to_float'}


def physical_type(series: pd.Series) -> str | None:
    """The contract physical type a pandas column holds, or None if it holds another."""
    from pandas.api.types import (is_bool_dtype, is_float_dtype, is_integer_dtype,
                                  is_object_dtype, is_string_dtype)
    dtype = series.dtype
    if is_bool_dtype(dtype):
        return 'bool'
    if is_integer_dtype(dtype) and str(dtype) == 'int64':
        return 'int64'
    if is_float_dtype(dtype) and str(dtype) == 'float64':
        return 'float64'
    if is_string_dtype(dtype) or is_object_dtype(dtype):
        values = series.dropna()
        if all(isinstance(v, str) for v in values):
            return 'string'
    return None


def _examples(index) -> list[int]:
    return [int(i) for i in list(index)[:MAX_EXAMPLES]]


def check_frame(contract: DataContract, frame: Any, *, features: list[str],
                purpose: str = 'inference') -> tuple[pd.DataFrame, list[dict]]:
    """``(view, applied_conversions)``: the feature columns in canonical order (a copy), or a
    ``contract_invalid`` refusal listing every problem with its columns and the positions of
    a few rows."""
    if not isinstance(frame, pd.DataFrame):
        raise ContractError('contract_invalid', 'The predictor reads a pandas DataFrame of raw '
                            'features.', path='input', remediation='Pass a DataFrame.')
    issues: list[dict] = []
    names = [str(c) for c in frame.columns]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        issues.append({'code': 'contract_invalid', 'path': 'input/columns',
                       'kind': 'duplicate_columns', 'columns': dupes})
    declared = {c.name: c for c in contract.columns}
    policy = contract.inference_policy
    missing = [c for c in policy.required_columns if c not in names]
    missing += [c for c in features if c not in names and c not in missing]
    if missing:
        issues.append({'code': 'contract_invalid', 'path': 'input/columns',
                       'kind': 'missing_columns', 'columns': missing})
    unknown = [n for n in names if n not in declared]
    if unknown and policy.extra_columns == 'reject':
        issues.append({'code': 'contract_invalid', 'path': 'input/columns',
                       'kind': 'unknown_columns', 'columns': unknown})
    if issues:
        _refuse(issues, purpose)
    conversions = {c.column: c for c in policy.conversions}
    applied = []
    view = pd.DataFrame(index=frame.index)
    for name in features:
        spec = declared[name]
        series = frame[name]
        found = physical_type(series)
        if found != spec.physical_type:
            conv = conversions.get(name)
            if conv is not None and conv.source == found and conv.target == spec.physical_type \
                    and CONVERSIONS.get((found, spec.physical_type)) == conv.rule:
                series = series.astype('float64')
                applied.append({'column': name, 'from': found, 'to': spec.physical_type,
                                'rule': conv.rule})
            else:
                issues.append({'code': 'contract_invalid', 'path': f'input/{name}',
                               'kind': 'wrong_type', 'expected': spec.physical_type,
                               'found': found or str(series.dtype)})
                continue
        na = series.isna()
        if spec.physical_type == 'string':
            series = series.astype(object).where(~na, np.nan)
        if na.any() and not spec.nullable:
            issues.append({'code': 'contract_invalid', 'path': f'input/{name}',
                           'kind': 'missing_values', 'n_rows': int(na.sum()),
                           'rows': _examples(np.flatnonzero(na.to_numpy()))})
        if spec.allowed_values is not None and policy.unknown_categories == 'reject':
            allowed = set(spec.allowed_values)
            bad = ~(na | series.isin(allowed))
            if bad.any():
                issues.append({'code': 'contract_invalid', 'path': f'input/{name}',
                               'kind': 'unknown_categories', 'n_rows': int(bad.sum()),
                               'values': sorted({str(v) for v in series[bad]})[:MAX_EXAMPLES],
                               'rows': _examples(np.flatnonzero(bad.to_numpy()))})
        view[name] = series.copy()
    if issues:
        _refuse(issues, purpose)
    return view, applied


def _refuse(issues: list[dict], purpose: str) -> None:
    first = issues[0]
    raise ContractError(
        'contract_invalid',
        f'The {purpose} rows do not satisfy the data contract: {first["kind"]} at '
        f'{first["path"]}' + (f' (and {len(issues) - 1} more)' if len(issues) > 1 else ''),
        path=first['path'],
        remediation='Send the raw feature columns with their declared types; nothing is '
                    'converted, dropped or imputed unless the contract declares it.',
        issues=issues)


def feature_columns_of(recipe: ModelRecipe) -> list[str]:
    return list(recipe.features)
