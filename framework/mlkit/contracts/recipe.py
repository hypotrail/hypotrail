"""The engine's model fit as a ``hypotrail.model_recipe/1`` and a ``hypotrail.data_contract/1``.

:func:`recipe_from_fit` translates the inputs and parameters of an engine fit
(:func:`mlkit.study.activities.model_plan`: features, special values, the confirmed
preprocessing, the family, its penalty or tuning grid, the seed) into a recipe whose
complete pipeline (:mod:`hypotrail_runtime.preprocess`) reproduces
:func:`mlkit.study.fit._fit_predict` on the same rows. Every resolved choice is explicit:
which columns are read as text, which special values become indicators, which features may
receive a missing indicator, the rare-category threshold (one for every column, operation
``rare_category`` version 1, or one per column, version 2 since L8), the caps, the log transforms, the
estimator parameters and seeds. A tuned hyperparameter is chosen by the engine's inner
cross-validation of the rows the recipe is fitted on, before the recipe is written, and
recorded with its choice. Families the runtime is not qualified for (EBM, histogram
boosting) are refused with ``capability_not_supported``; they are never replaced.

:func:`data_contract_from_case` derives the data contract from the case file (names, types,
roles, reading parameters) and the physical types of the loaded development rows; it never
derives domains or bounds from the data.
"""
from __future__ import annotations

from typing import Any, Mapping

from hypotrail_runtime import METHOD_CONTRACT_VERSION, RUNTIME_API_VERSION
from hypotrail_runtime.contracts import DataContract, ModelRecipe, validate_data_contract, \
    validate_recipe
from hypotrail_runtime.errors import ContractError
from hypotrail_runtime.inference import physical_type

SEMANTIC = {'numeric': 'numeric', 'integer': 'numeric', 'binary': 'category',
            'category': 'category', 'ordinal': 'category', 'string': 'category'}


def _family(params: Mapping, binary: bool, tuned) -> tuple[str, dict]:
    family = params.get('family') or 'linear'
    if family != 'linear':
        raise ContractError('capability_not_supported',
                            f'The {family} family is not qualified for the predictor runtime '
                            'v1; the chosen model is kept and its export is unavailable.',
                            path='family', remediation='Report the limit; no other family is '
                                                       'substituted.',
                            details={'family': family})
    if binary:
        out = {'max_iter': 1000}
        for key in ('solver', 'tol'):
            if params.get(key) is not None:
                out[key] = params[key] if key == 'solver' else float(params[key])
        if tuned is not None:
            out['C'] = float(tuned)
        elif params.get('C') is not None:
            out['C'] = float(params['C'])
        return 'logistic', out
    if tuned is not None:
        return 'ridge', {'alpha': float(tuned)}
    if params.get('alpha') is not None:
        return 'ridge', {'alpha': float(params['alpha'])}
    return 'linear', {}


def recipe_from_fit(case, train, inputs: Mapping, params: Mapping, *,
                    selection_reference: Mapping | None = None) -> tuple[ModelRecipe, dict]:
    """``(recipe, info)`` of the model the engine fits on ``train`` with ``inputs`` and
    ``params``; ``info['tuning']`` holds the hyperparameter choice when there is one."""
    from pandas.api.types import is_bool_dtype, is_numeric_dtype
    from mlkit.study import governance
    binary = case.task == 'binary'
    info: dict[str, Any] = {}
    tuned = params.get('tuned_value')
    if (params.get('family') or 'linear') != 'linear':
        _family(params, binary, None)        # refuses before any computation
    if params.get('tuning') and tuned is None:
        from mlkit.study import families
        choice = families.choose(case, train, inputs, params, binary)
        tuned = choice['value']
        info['tuning'] = choice
    family, parameters = _family(params, binary, tuned)
    features = list(inputs['features'])
    na_values = {str(v) for v in case.dataset.get('na_values', ())}
    text = [n for n in features
            if is_bool_dtype(train[n]) or (case.variables[n]['type'] == 'category'
                                          and is_numeric_dtype(train[n]))]
    special = []
    for s in inputs.get('special_values') or []:
        column, value = s['column'], s['value']
        if not is_numeric_dtype(train[column]):
            continue
        special.append({'column': column, 'value': value, 'name': f'{column}={value}',
                        'reads_missing': str(value) in na_values})
    steps = [{'operation': 'category_as_text', 'version': 1, 'parameters': {'columns': text}},
             {'operation': 'special_value_indicator', 'version': 1,
              'parameters': {'values': special}}]
    pre = inputs.get('preprocessing')
    if pre is not None:
        covered = {s['column'] for s in inputs.get('special_values') or []
                   if str(s['value']) in na_values}
        candidates = [c for c in features if governance.missing_strategy(pre, c) == 'indicator'
                      and c not in covered]
        steps.append({'operation': 'missing_indicator', 'version': 1,
                      'parameters': {'columns': candidates}})
        rare = pre['rare_category_min_rows']
        if isinstance(rare, Mapping):
            # L8 (R6): version 2, a minimum per column (the features the fit uses, in their
            # order; a column the mapping leaves out keeps every category).
            per_column = {c: int(rare[c]) for c in features if int(rare.get(c, 0) or 0) > 0}
            if per_column:
                steps.append({'operation': 'rare_category', 'version': 2,
                              'parameters': {'min_rows': per_column}})
        elif int(rare) > 0:
            steps.append({'operation': 'rare_category', 'version': 1,
                          'parameters': {'min_rows': int(rare)}})
        caps = {c: [float(q[0]), float(q[1])] for c, q in sorted(pre['caps'].items())
                if c in features}
        if caps:
            steps.append({'operation': 'cap_quantiles', 'version': 1,
                          'parameters': {'quantiles': caps}})
        logs = [c for c in pre['log_transform'] if c in features]
        if logs:
            steps.append({'operation': 'signed_log', 'version': 1,
                          'parameters': {'columns': logs}})
    steps += [{'operation': 'numeric_median_impute_scale', 'version': 1, 'parameters': {}},
              {'operation': 'categorical_mode_impute_onehot', 'version': 1,
               'parameters': {'handle_unknown': 'ignore'}}]
    types = {}
    for n in features:
        found = physical_type(train[n])
        if found is None:
            raise ContractError('capability_not_supported', f'The column {n!r} has the pandas '
                                f'type {train[n].dtype}, which the contract v1 cannot declare.',
                                path=f'features/{n}', remediation='Declare a conversion in the '
                                                                  'case.')
        types[n] = {'semantic': SEMANTIC.get(case.variables[n]['type'], 'category'),
                    'physical': found}
    unit = case.target_unit if not binary else None
    positive = case.positive_label if binary else None
    doc = {'schema_version': 'hypotrail.model_recipe/1', 'task': case.task,
           'family': family, 'parameters': parameters, 'features': features,
           'feature_types': types, 'preprocessing': steps,
           'target': {'name': case.target_column, 'unit': unit, 'positive_label': positive},
           'seeds': {'estimator': int(params['seed'])} if binary else {},
           'output_contract': {'kind': 'binary_score' if binary else 'regression_point',
                               'columns': ['score' if binary else 'prediction'],
                               'unit': unit, 'positive_label': positive},
           'selection_reference': dict(selection_reference) if selection_reference else None,
           'method_contract_version': METHOD_CONTRACT_VERSION,
           'runtime_api_version': RUNTIME_API_VERSION,
           'extensions': {}}
    if 'tuning' in info:
        doc['extensions']['hypotrail.tuning'] = {
            'parameter': (params['tuning'] or {}).get('parameter'), 'value': tuned,
            'scores': [{'value': s['value'], 'mean': s['mean']}
                       for s in info['tuning'].get('scores') or []]}
    return validate_recipe(doc), info


AS_TEXT_EXTENSION = 'hypotrail.auxiliary_as_text'


def delayed_label_exclusions(limit: Mapping | None) -> list[dict]:
    """The data contract's ``exclusions`` for the delayed-label rows of a study
    (``limit`` is :func:`mlkit.study.state.delayed_labels_limit`, None when there are none):
    the term first, then the study's example in its own clock, with the count."""
    from mlkit.study import partition
    from mlkit.study.state import _clock_value
    if not limit or not limit.get('n_rows'):
        return []
    n = int(limit['n_rows'])
    clock, start = limit.get('clock'), limit.get('final_start')
    if clock and start is not None:
        where = f'{clock} {_clock_value(start)}'
    else:
        where = 'the start of the final test'
    rows = 'row' if n == 1 else 'rows'
    return [{'rule': partition.DELAYED_LABEL_REASON,
             'justification': f'A delayed label is an outcome known only some time after the '
                              f'prediction. Here {n} development {rows} had an outcome known '
                              f'only at or after the start of the final test ({where}): they '
                              f'are left out of every fit, the final refit and the captured '
                              f'predictor, since nobody knew their outcome at that moment.'}]


def data_contract_from_case(case, frame, *, dataset_sha256: str, features: list[str],
                            exclusions: list[dict] | None = None) -> DataContract:
    """The data contract of the case's dataset as the engine reads it: the recipe's features
    (required at inference, in this order), the target (never required at inference), and
    every other case column as auxiliary (never read by the predictor).

    An auxiliary column whose pandas type the contract v1 cannot declare (an integer above
    the int64 range read as ``uint64``, a boolean column with a missing token read as an
    ``object`` of booleans) is declared ``string`` and listed under the extension
    ``hypotrail.auxiliary_as_text`` with the type the engine read: a reader of the contract
    reads its cells as their text (the exported project does). ``exclusions`` lists the
    rows the engine leaves out of every fit (:func:`delayed_label_exclusions`)."""
    columns, as_text = [], []
    for v in case.document['variables']:
        name = v['name']
        if name in features:
            role = 'feature'
        elif name == case.target_column:
            role = 'target'
        else:
            role = 'auxiliary'
        found = physical_type(frame[name]) if name in frame.columns else None
        if found is None:
            if role != 'auxiliary':
                raise ContractError('capability_not_supported', f'The column {name!r} has a '
                                    'type the contract v1 cannot declare.', path=name,
                                    remediation='Declare a conversion in the case.')
            found = 'string'
            if name in frame.columns:
                as_text.append({'column': name, 'engine_dtype': str(frame[name].dtype)})
        columns.append({'name': name, 'physical_type': found,
                        'semantic_type': SEMANTIC.get(v['type'], 'category'),
                        # Features may be missing: the predictor imputes them (declared, not
                        # inferred from the rows). The target is never imputed.
                        'nullable': role != 'target',
                        'allowed_values': None, 'role': role})
    doc = {'schema_version': 'hypotrail.data_contract/1', 'dataset_id': case.id,
           'source_sha256': dataset_sha256, 'format': 'csv',
           'parser': {'encoding': str(case.dataset['encoding']),
                      'delimiter': str(case.dataset['sep']),
                      'header': bool(case.dataset['header']),
                      'quotechar': case.dataset.get('quotechar', '"'),
                      'na_values': [str(x) for x in case.dataset.get('na_values', ())],
                      'decimal': str(case.dataset.get('decimal', '.'))},
           'columns': columns,
           'row_identity': {'kind': 'source_position', 'columns': [],
                            'source_hash_required': True},
           'exclusions': [dict(e) for e in exclusions or []],
           'inference_policy': {'required_columns': list(features), 'extra_columns': 'reject',
                                'conversions': [], 'canonical_order': list(features),
                                'unknown_categories': 'predictor_handles'},
           'extensions': {AS_TEXT_EXTENSION: as_text} if as_text else {}}
    return validate_data_contract(doc)
