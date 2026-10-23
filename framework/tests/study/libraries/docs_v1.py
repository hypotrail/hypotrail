"""Reference v1 documents used by the contract tests (synthetic, no study data)."""
from __future__ import annotations

import copy

RECIPE = {
    'schema_version': 'hypotrail.model_recipe/1', 'task': 'binary', 'family': 'logistic',
    'parameters': {'C': 1.0, 'solver': 'newton-cholesky', 'tol': 1e-08, 'max_iter': 1000},
    'features': ['age', 'branch', 'band'],
    'feature_types': {'age': {'semantic': 'numeric', 'physical': 'float64'},
                      'branch': {'semantic': 'category', 'physical': 'string'},
                      'band': {'semantic': 'category', 'physical': 'int64'}},
    'preprocessing': [
        {'operation': 'category_as_text', 'version': 1, 'parameters': {'columns': ['band']}},
        {'operation': 'special_value_indicator', 'version': 1, 'parameters': {
            'values': [{'column': 'age', 'value': -1, 'name': 'age=-1',
                        'reads_missing': False}]}},
        {'operation': 'missing_indicator', 'version': 1, 'parameters': {'columns': ['age']}},
        {'operation': 'rare_category', 'version': 1, 'parameters': {'min_rows': 10}},
        {'operation': 'numeric_median_impute_scale', 'version': 1, 'parameters': {}},
        {'operation': 'categorical_mode_impute_onehot', 'version': 1,
         'parameters': {'handle_unknown': 'ignore'}}],
    'target': {'name': 'renewed', 'unit': None, 'positive_label': 'yes'},
    'seeds': {'estimator': 7},
    'output_contract': {'kind': 'binary_score', 'columns': ['score'], 'unit': None,
                        'positive_label': 'yes'},
    'selection_reference': {'decision_id': 'final_test', 'revision': 12,
                            'evidence_ids': ['r-abc']},
    'method_contract_version': 'hypotrail.method/1', 'runtime_api_version': '1.0',
    'extensions': {'azureml.note': 'carried, not interpreted'},
}

DATA_CONTRACT = {
    'schema_version': 'hypotrail.data_contract/1', 'dataset_id': 'synthetic',
    'source_sha256': 'a' * 64, 'format': 'csv',
    'parser': {'encoding': 'utf-8', 'delimiter': ';', 'na_values': ['NA'], 'decimal': '.'},
    'columns': [
        {'name': 'age', 'physical_type': 'float64', 'semantic_type': 'numeric',
         'nullable': True, 'allowed_values': None, 'role': 'feature'},
        {'name': 'branch', 'physical_type': 'string', 'semantic_type': 'category',
         'nullable': True, 'allowed_values': ['Alder', 'Brook'], 'role': 'feature'},
        {'name': 'band', 'physical_type': 'int64', 'semantic_type': 'category',
         'nullable': False, 'allowed_values': None, 'role': 'feature'},
        {'name': 'renewed', 'physical_type': 'string', 'semantic_type': 'category',
         'nullable': False, 'allowed_values': ['yes', 'no'], 'role': 'target'},
        {'name': 'member_id', 'physical_type': 'string', 'semantic_type': 'category',
         'nullable': False, 'allowed_values': None, 'role': 'key'}],
    'row_identity': {'kind': 'stable_key', 'columns': ['member_id'],
                     'source_hash_required': False},
    'exclusions': [],
    'inference_policy': {'required_columns': ['age', 'branch', 'band'],
                         'extra_columns': 'reject', 'conversions': [],
                         'canonical_order': ['age', 'branch', 'band'],
                         'unknown_categories': 'predictor_handles'},
    'extensions': {},
}


def recipe(**changes) -> dict:
    out = copy.deepcopy(RECIPE)
    out.update(changes)
    return out


def contract(**changes) -> dict:
    out = copy.deepcopy(DATA_CONTRACT)
    out.update(changes)
    return out
