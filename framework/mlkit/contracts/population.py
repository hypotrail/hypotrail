"""The ``diagnostics.population`` activity: an Evidently profile on development populations.

``hypotrail run diagnostics.population`` (opt-in; needs the ``diagnostics`` extra) compares
two populations the study already reads, on the model's feature columns only, never the
target:

* under cross-validation, the rows of the first fold (reference) and of the last fold
  (current): in a temporal scheme, the earliest and the latest block;
* under an explicit evaluation plan, the first and the last validation windows;
* under a train/validation split, the training rows and the validation rows.

The profile is the demonstration profile of :mod:`mlkit.integrations.evidently_diagnostics`
built from the case's variable types (KS or chi-square at p < 0.05 with Holm, 5 % missing
and unknown-category shares); its thresholds are demonstration values. The performance
family is left out (it would read the target). The exposure is a structural inspection of
the two populations' feature columns. The Evidently snapshot is kept as a blob, the
``hypotrail.diagnostic_result/1`` document is the result's values, and the report's annex
shows it like every other result. A missing extra is refused before any row is read.
"""
from __future__ import annotations

import gzip
import importlib.util
import json
from typing import Mapping

from hypotrail_runtime.errors import ContractError

from . import errors as cerr

POPULATION = 'diagnostics.population'
NUMERIC_TYPES = ('numeric', 'integer')


def require_backend() -> None:
    if importlib.util.find_spec('evidently') is None:
        raise cerr.to_study_error(ContractError(
            'optional_dependency_missing', 'diagnostics.population needs Evidently, which is '
            'not installed.', remediation='Install the diagnostics extra (uv sync --extra '
            'diagnostics); the base workflow does not need it.',
            details={'extra': 'diagnostics'}))


def _populations(store, state: Mapping) -> dict:
    from mlkit.study import activities as act
    split_rid = state['current'][act.SPLIT]
    folds = act.fold_assignment(store, split_rid)
    if folds:
        ids = sorted(set(folds.values()))
        first, last = ids[0], ids[-1]
        return {'split': split_rid, 'scheme': 'folds', 'reference': f'fold {first}',
                'current': f'fold {last}',
                'reference_keys': sorted(k for k, f in folds.items() if f == first),
                'current_keys': sorted(k for k, f in folds.items() if f == last)}
    plan = act.evaluation_membership(store, split_rid)
    if plan is not None and plan.get('folds'):
        a, b = plan['folds'][0], plan['folds'][-1]
        return {'split': split_rid, 'scheme': 'evaluation_windows',
                'reference': f'window {a["id"]}', 'current': f'window {b["id"]}',
                'reference_keys': list(a['validation_keys']),
                'current_keys': list(b['validation_keys'])}
    keys = act.split_keys(store, split_rid)
    return {'split': split_rid, 'scheme': 'train_validation', 'reference': 'training rows',
            'current': 'validation rows', 'reference_keys': keys['train'],
            'current_keys': keys['validation']}


def plan(store, state: Mapping, case, inputs: dict, params: dict, expose) -> None:
    from mlkit.study import activities as act, partition
    from . import context as cx
    require_backend()
    availability = state['decisions']['feature_availability']['value'] or {}
    features, _ = act.used_features(case, availability)
    pops = _populations(store, state)
    if not features or not pops['reference_keys'] or not pops['current_keys']:
        raise cerr.to_study_error(ContractError(
            'capability_not_supported', 'There are no two development populations with '
            'features to compare.', remediation='Split the data and decide the features first.'))
    columns = {f: ('numerical' if case.variables[f]['type'] in NUMERIC_TYPES
                   else 'categorical') for f in features}
    inputs.update(results={act.SPLIT: pops['split']}, features=features, columns=columns)
    params.update(profile='demonstration', populations={
        k: pops[k] for k in ('scheme', 'reference', 'current')},
        semantic_dependencies=cx.semantic_dependencies('diagnostics.evidently'))
    keys = pops['reference_keys'] + pops['current_keys']
    expose('structural_inspection', partition.DEVELOPMENT, keys, features)


def compute(store, plan_: Mapping) -> dict:
    from mlkit.study import activities as act
    from mlkit.integrations import evidently_diagnostics as ed
    case, dataset = act.load(plan_, store)
    s_state = {'current': {act.SPLIT: plan_['inputs']['results'][act.SPLIT]}}
    pops = _populations(store, s_state)
    features = plan_['inputs']['features']
    frame = dataset.frame[features]
    profile = ed.demonstration_profile(plan_['inputs']['columns'])
    try:
        out = ed.run(profile, frame.loc[pops['reference_keys']], frame.loc[pops['current_keys']],
                     reference_partition='development', current_partition='development',
                     authorized=('development',))
    except ContractError as exc:
        raise cerr.to_study_error(exc) from None
    result = out['result'].model_dump(mode='json')
    values = {'diagnostic': result, 'alert': result['alert'], 'status': result['status'],
              'populations': {k: pops[k] for k in ('scheme', 'reference', 'current')},
              'n_reference': len(pops['reference_keys']), 'n_current': len(pops['current_keys']),
              'note': ('Development populations compared on feature columns only, with '
                       'demonstration thresholds; no alert does not mean the model is still '
                       'valid.')}
    raw = gzip.compress(json.dumps(out['raw'], sort_keys=True, default=str).encode(), mtime=0)
    return {'values': values, 'blobs': {'evidently_snapshot': raw}, 'partition': 'development',
            'n_rows': len(pops['reference_keys']) + len(pops['current_keys'])}
