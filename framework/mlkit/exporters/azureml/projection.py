"""The scientific projection of an export, and the closed shape of its Hydra config.

The projection is the part of a run configuration that decides **what** is fitted and
judged: task, target, features and their types, preprocessing declarations, model family
and parameters, seeds, output contract, metrics, the evaluation protocol and the identities
of the recipe and data contract. Compute, paths, logs and tracking are operational and
stay out of it.

Two functions build the same projection: :func:`from_recipe` (the generator, from the
study's ``ModelRecipe`` and plan) and :func:`from_config` (the exported project, from the
resolved Hydra configuration). The generator renders ``src/conf`` so that both agree, and
records the SHA-256 of the projection as ``hypotrail.expected_scientific_sha256``; a run
whose resolved configuration projects to another value is refused with
``scientific_config_changed`` (a faithful replay accepts no scientific override).

:data:`CONFIG_SHAPE` is the closed set of keys of the composed configuration: a key that
is not listed (for example one added by a ``+key=value`` override, or a ``_target_``) is
refused. Standalone (standard library only): the export copies this file byte for byte
into the generated project (``src/pipeline/utils/hypotrail/projection.py``).
"""
from __future__ import annotations

from typing import Any, Mapping

SCHEMA = 'hypotrail.scientific_projection/1'
REPLAY_PURPOSE = 'replay_selected_recipe'
ANY = None  # a leaf whose value is free (validated by the projection or by its step)

# The closed shape of the composed Hydra configuration (``src/conf/config.yaml``). A
# mapping lists its allowed keys; ``ANY`` accepts any JSON value; ``'hydra'`` is Hydra's
# own node, removed before the check (Hydra validates it).
CONFIG_SHAPE: dict = {
    'debug': ANY,
    'mlflow_tracking': ANY,
    'data_dir': ANY,
    'raw_data': {'path': ANY, 'file': ANY},
    'preprocessed_data': {'path': ANY, 'file': ANY},
    'train_data': {'path': ANY},
    'models': {'path': ANY, 'evaluated_path': ANY},
    'reports': {'path': ANY},
    'contracts': {'path': ANY},
    'packaging': {'format': ANY, 'required': ANY},
    'components': {
        'data_preparation': {'debug': ANY, 'target': ANY, 'features': ANY,
                             'feature_types': ANY},
        'data_splitting': {'protocol_id': ANY, 'keys_sha256': ANY, 'roles': ANY},
        'training': {'status': ANY, 'task': ANY, 'model': {'type': ANY, 'params': ANY},
                     'preprocessing': ANY, 'seeds': ANY, 'output_contract': ANY,
                     'mode': ANY},
        'evaluation': {'metrics': ANY},
    },
    'hypotrail': {
        'execution': {'purpose': ANY, 'allow_scientific_override': ANY},
        'recipe_sha256': ANY, 'data_contract_sha256': ANY,
        'expected_scientific_sha256': ANY, 'method_contract_version': ANY,
        'runtime_api_version': ANY, 'selection_reference': ANY, 'study_id': ANY,
        'study_revision': ANY, 'snapshot_id': ANY,
    },
}
OPERATIONAL_TOP = ('debug', 'mlflow_tracking', 'data_dir', 'raw_data', 'preprocessed_data',
                   'train_data', 'models', 'reports', 'contracts', 'packaging')


class ProjectionError(ValueError):
    """A configuration outside :data:`CONFIG_SHAPE`, or a ``_target_``; ``path`` names it."""

    def __init__(self, message: str, path: str):
        super().__init__(f'{path}: {message}')
        self.path = path


def check_shape(config: Mapping, shape: Mapping = CONFIG_SHAPE, path: str = '') -> None:
    """Refuse a key outside ``shape`` and any ``_target_`` anywhere in ``config``."""
    for key, value in config.items():
        where = f'{path}.{key}' if path else str(key)
        if key == '_target_':
            raise ProjectionError('object instantiation from configuration is refused', where)
        if key not in shape:
            raise ProjectionError('unknown configuration key', where)
        child = shape[key]
        if isinstance(child, Mapping):
            if not isinstance(value, Mapping):
                raise ProjectionError('expected a mapping', where)
            check_shape(value, child, where)
        else:
            _no_target(value, where)


def _no_target(value: Any, path: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key == '_target_':
                raise ProjectionError('object instantiation from configuration is refused',
                                      f'{path}.{key}')
            _no_target(item, f'{path}.{key}')
    elif isinstance(value, list):
        for i, item in enumerate(value):
            _no_target(item, f'{path}[{i}]')


def from_recipe(recipe: Mapping, *, protocol_id: str, keys_sha256: str, metrics: list,
                recipe_sha256: str, data_contract_sha256: str) -> dict:
    """The projection of a study's selected recipe and development plan."""
    return {
        'schema_version': SCHEMA,
        'task': recipe['task'],
        'target': dict(recipe['target']),
        'features': list(recipe['features']),
        'feature_types': dict(recipe['feature_types']),
        'preprocessing': [dict(p) for p in recipe['preprocessing']],
        'model': {'family': recipe['family'], 'parameters': dict(recipe['parameters'])},
        'seeds': dict(recipe['seeds']),
        'output_contract': dict(recipe['output_contract']),
        'evaluation': {'metrics': list(metrics)},
        'plan': {'protocol_id': protocol_id, 'keys_sha256': keys_sha256},
        'recipe_sha256': recipe_sha256,
        'data_contract_sha256': data_contract_sha256,
        'method_contract_version': recipe['method_contract_version'],
        'runtime_api_version': recipe['runtime_api_version'],
        'selection_reference': dict(recipe['selection_reference']),
    }


def from_config(config: Mapping) -> dict:
    """The projection of a resolved configuration (plain containers, see
    ``OmegaConf.to_container(cfg, resolve=True, throw_on_missing=True)``)."""
    components = config['components']
    prep, split = components['data_preparation'], components['data_splitting']
    training, evaluation = components['training'], components['evaluation']
    hyp = config['hypotrail']
    return {
        'schema_version': SCHEMA,
        'task': training['task'],
        'target': dict(prep['target']),
        'features': list(prep['features']),
        'feature_types': dict(prep['feature_types']),
        'preprocessing': [dict(p) for p in training['preprocessing']],
        'model': {'family': training['model']['type'],
                  'parameters': dict(training['model']['params'] or {})},
        'seeds': dict(training['seeds'] or {}),
        'output_contract': dict(training['output_contract']),
        'evaluation': {'metrics': list(evaluation['metrics'])},
        'plan': {'protocol_id': split['protocol_id'], 'keys_sha256': split['keys_sha256']},
        'recipe_sha256': hyp['recipe_sha256'],
        'data_contract_sha256': hyp['data_contract_sha256'],
        'method_contract_version': hyp['method_contract_version'],
        'runtime_api_version': hyp['runtime_api_version'],
        'selection_reference': dict(hyp['selection_reference']),
    }


def differences(expected: Any, actual: Any, path: str = '') -> list[str]:
    """The paths where two projections differ (bounded by the caller)."""
    if isinstance(expected, Mapping) and isinstance(actual, Mapping):
        out = []
        for key in sorted(set(expected) | set(actual)):
            where = f'{path}.{key}' if path else key
            if key not in expected or key not in actual:
                out.append(where)
            else:
                out += differences(expected[key], actual[key], where)
        return out
    if isinstance(expected, list) and isinstance(actual, list) and len(expected) == len(actual):
        out = []
        for i, (a, b) in enumerate(zip(expected, actual)):
            out += differences(a, b, f'{path}[{i}]')
        return out
    same = type(expected) is type(actual) and expected == actual
    return [] if same else [path or '$']
