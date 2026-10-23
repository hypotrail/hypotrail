"""Tabular validation with Pandera, derived from the DataContract (spec L-07, AC03).

One logical contract, two readers: :func:`schema_from_contract` builds the Pandera schema
from the same ``hypotrail.data_contract/1`` the runtime checks at inference
(:func:`hypotrail_runtime.inference.check_frame`), so there is no second hand-written
contract for a case. Three levels stay separate:

1. declared parsing (the case's reading parameters; not redone here);
2. structural checks: required, unknown and duplicated columns, physical types, empty set;
3. value checks: missing values where forbidden, categories outside a declared list,
   duplicate stable keys.

Nothing is coerced, dropped, imputed or added; the frame and its row order are never
changed (validation reads it). Unknown categories are reported only when the contract says
the predictor does not handle them. :func:`validate` refuses a partition its caller is not
authorised to read (the final test is never validated through this path before it is opened),
so value checks can never bypass the exposure policy. Reports bound the examples they show.
"""
from __future__ import annotations

from typing import Iterable, Mapping

from hypotrail_runtime.contracts import DataContract, validate_data_contract
from hypotrail_runtime.errors import ContractError
from hypotrail_runtime.inference import physical_type

MAX_EXAMPLES = 5
PURPOSES = ('inference', 'training')


def _contract(contract) -> DataContract:
    if isinstance(contract, DataContract):
        return contract
    return validate_data_contract(contract)


def schema_from_contract(contract, *, purpose: str = 'inference'):
    """The Pandera schema of ``contract`` for ``purpose``: at inference the target is never
    required (and its presence is not an error); for training it is required."""
    import pandera.pandas as pa
    contract = _contract(contract)
    if purpose not in PURPOSES:
        raise ValueError(f'purpose is one of {PURPOSES}')
    policy = contract.inference_policy
    columns = {}
    for spec in contract.columns:
        required = (spec.name in policy.required_columns
                    or (purpose == 'training' and spec.role == 'target'))
        checks = [pa.Check(lambda s, t=spec.physical_type: physical_type(s) == t,
                           name=f'physical_type={spec.physical_type}',
                           error=f'physical_type={spec.physical_type}')]
        if spec.allowed_values is not None and policy.unknown_categories == 'reject':
            checks.append(pa.Check.isin(list(spec.allowed_values), ignore_na=True))
        unique = (contract.row_identity.kind == 'stable_key'
                  and contract.row_identity.columns == [spec.name])
        columns[spec.name] = pa.Column(None, checks=checks, nullable=spec.nullable,
                                       required=required, unique=unique, coerce=False)
    unique_keys = (list(contract.row_identity.columns)
                   if contract.row_identity.kind == 'stable_key'
                   and len(contract.row_identity.columns) > 1 else None)
    return pa.DataFrameSchema(columns, strict=policy.extra_columns == 'reject', ordered=False,
                              coerce=False, unique=unique_keys,
                              name=f'{contract.dataset_id}:{purpose}')


def _issues(failure_cases) -> list[dict]:
    grouped: dict[tuple, dict] = {}
    for row in failure_cases.to_dict('records'):
        column = row.get('column')
        if row.get('schema_context') == 'DataFrameSchema':
            column = None          # a table-level check: the column is the failure case
        key = (str(column) if column is not None else None, str(row.get('check')))
        item = grouped.setdefault(key, {'column': key[0], 'check': key[1], 'n_rows': 0,
                                        'rows': [], 'values': []})
        item['n_rows'] += 1
        index = row.get('index')
        if index is not None and len(item['rows']) < MAX_EXAMPLES:
            item['rows'].append(index if isinstance(index, (int, str)) else str(index))
        value = row.get('failure_case')
        text = None if value is None or value != value else str(value)
        if text is not None and text not in item['values'] and len(item['values']) < MAX_EXAMPLES:
            item['values'].append(text)
    return sorted(grouped.values(), key=lambda i: (i['column'] or '', i['check']))


def validate(contract, frame, *, partition: str, authorized: Iterable[str],
             purpose: str = 'inference') -> dict:
    """``{status, partition, purpose, n_rows, n_columns, issues}``; ``status`` is ``ok``,
    ``failed`` (with every issue, bounded) or ``insufficient_data`` (an empty set). A
    partition outside ``authorized`` is refused before the frame is read."""
    import pandera.pandas as pa
    contract = _contract(contract)
    if partition not in set(authorized):
        raise ContractError('partition_not_authorized',
                            f'Validating the {partition} rows is not authorised here.',
                            path='partition',
                            remediation='Validate only rows the study already exposes to this '
                                        'activity; the final test is read once, at its opening.',
                            details={'partition': partition, 'authorized': sorted(authorized)})
    schema = schema_from_contract(contract, purpose=purpose)
    names = [str(c) for c in frame.columns]
    dupes = sorted({n for n in names if names.count(n) > 1})
    base = {'partition': partition, 'purpose': purpose, 'n_rows': int(len(frame)),
            'n_columns': len(names), 'backend': 'pandera'}
    if dupes:
        return {**base, 'status': 'failed', 'issues': [
            {'column': None, 'check': 'duplicate_columns', 'n_rows': 0, 'rows': [],
             'values': dupes[:MAX_EXAMPLES]}]}
    if not len(frame):
        return {**base, 'status': 'insufficient_data', 'issues': [
            {'column': None, 'check': 'empty_set', 'n_rows': 0, 'rows': [], 'values': []}]}
    try:
        schema.validate(frame, lazy=True, inplace=False)
    except pa.errors.SchemaErrors as exc:
        return {**base, 'status': 'failed', 'issues': _issues(exc.failure_cases)}
    return {**base, 'status': 'ok', 'issues': []}
