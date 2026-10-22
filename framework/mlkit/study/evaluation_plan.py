"""Pure, explicit evaluation-membership planning for the review-v1 profile.

Unlike the legacy folds file, a plan records both sides of every comparison.  A
consumer therefore never has to reconstruct training rows as the complement of a
validation fold (which is incorrect for forward-looking protocols).
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from typing import Any, Mapping, Sequence

from .errors import StudyError

SCHEMA = 'hypotrail.evaluation_plan/1'
TEMPORAL_METHODS = ('forward_chaining', 'ordered_retrospective')
INDEPENDENT_METHODS = ('kfold_stratified', 'kfold_quantile', 'group_disjoint')
METHODS = INDEPENDENT_METHODS + TEMPORAL_METHODS


def _refuse(reason: str, **details):
    raise StudyError('unsupported_capability',
                     f'The evaluation protocol is infeasible: {reason}.',
                     details={'reason': reason, **details})


def _values(keys: Sequence[str], values: Mapping | Sequence | None, name: str):
    if values is None:
        return None
    if isinstance(values, Mapping):
        missing = [key for key in keys if key not in values]
        if missing:
            _refuse(f'missing_{name}', keys=missing)
        return [values[key] for key in keys]
    out = list(values)
    if len(out) != len(keys):
        _refuse(f'invalid_{name}_length', expected=len(keys), actual=len(out))
    return out


def _components(keys: Sequence[str], *relations) -> list[str] | None:
    """Transitive union of entity and duplicate relations, one component per row."""
    arrays = [_values(keys, r, 'group') for r in relations if r is not None]
    if not arrays:
        return None
    parent = list(range(len(keys)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        a, b = find(a), find(b)
        if a != b:
            parent[max(a, b)] = min(a, b)

    for values in arrays:
        first = {}
        for i, value in enumerate(values):
            marker = (type(value).__name__, repr(value))
            if marker in first:
                union(i, first[marker])
            else:
                first[marker] = i
    return [keys[find(i)] for i in range(len(keys))]


def _array_split(values: Sequence[Any], n: int) -> list[list[Any]]:
    q, r = divmod(len(values), n)
    out, at = [], 0
    for i in range(n):
        size = q + (1 if i < r else 0)
        out.append(list(values[at:at + size]))
        at += size
    return out


def _validate(plan: Mapping, universe: set[str]) -> None:
    seen = set()
    for fold in plan['folds']:
        train, validation = set(fold['train_keys']), set(fold['validation_keys'])
        if not train or not validation:
            _refuse('empty_train_or_validation', fold=fold['id'])
        if train & validation:
            _refuse('train_validation_overlap', fold=fold['id'])
        if seen & validation:
            _refuse('validation_key_repeated', fold=fold['id'])
        seen |= validation
        returned = train | validation | set(fold.get('excluded_train_keys') or [])
        if not returned <= universe:
            _refuse('key_outside_universe', keys=sorted(returned - universe))
    if not set(plan['unscored_keys']) <= universe:
        _refuse('key_outside_universe')


def digest(plan: Mapping) -> str:
    """Stable sha256 of the canonical JSON plan."""
    raw = json.dumps(plan, ensure_ascii=False, sort_keys=True,
                     separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def _temporal(keys, protocol, prediction, outcome, components, labels):
    method = protocol['method']
    k, gap = int(protocol.get('folds', 0)), protocol.get('gap', 0)
    if k < 2 or isinstance(gap, bool) or not isinstance(gap, (int, float)) or gap < 0:
        _refuse('invalid_temporal_protocol', folds=k, gap=gap)
    if prediction is None:
        _refuse('prediction_order_missing')
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
           for v in prediction):
        _refuse('invalid_prediction_order')
    if method == 'forward_chaining':
        if outcome is None:
            _refuse('outcome_available_order_missing')
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
               for v in outcome):
            _refuse('invalid_outcome_available_order')
    distinct = sorted(set(prediction))
    if len(distinct) < k + 1:
        _refuse('too_few_distinct_times', distinct_times=len(distinct), folds=k)
    chunks = _array_split(distinct, k + 1)
    if any(not chunk for chunk in chunks):
        _refuse('empty_time_window')
    folds = []
    scored = set()
    for fold_id, window in enumerate(chunks[1:], 1):
        start, end = window[0], window[-1]
        validation_positions = [i for i, value in enumerate(prediction) if value in set(window)]
        validation = [keys[i] for i in validation_positions]
        validation_groups = ({components[i] for i in validation_positions}
                             if components is not None else set())
        train, excluded, reasons = [], [], defaultdict(list)
        for i, key in enumerate(keys):
            if i in validation_positions or prediction[i] >= start:
                continue
            eligible_prediction = prediction[i] < start - gap
            eligible_outcome = method == 'ordered_retrospective' or outcome[i] < start - gap
            group_ok = components is None or components[i] not in validation_groups
            if eligible_prediction and eligible_outcome and group_ok:
                train.append(key)
            else:
                excluded.append(key)
                if not eligible_prediction:
                    reasons['prediction_not_strictly_before_window'].append(key)
                if not eligible_outcome:
                    reasons['outcome_not_available_before_window'].append(key)
                if not group_ok:
                    reasons['overlapping_group'].append(key)
        if not train:
            _refuse('empty_train_after_purge', fold=fold_id)
        if labels is not None and len({labels[keys.index(key)] for key in train}) < 2:
            _refuse('single_class_training_fold', fold=fold_id)
        scored.update(validation)
        folds.append({'id': fold_id, 'train_keys': train, 'validation_keys': validation,
                      'excluded_train_keys': excluded,
                      'excluded_train': [{'reason': reason, 'count': len(rows), 'keys': rows}
                                         for reason, rows in sorted(reasons.items())],
                      'validation_start': start, 'validation_end': end})
    return folds, [key for key in keys if key not in scored]


def _independent(keys, protocol, strata, components, labels):
    k, seed = int(protocol.get('folds', 0)), int(protocol.get('seed', 20261017))
    if k < 2 or len(keys) < k:
        _refuse('too_few_rows', rows=len(keys), folds=k)
    if strata is None:
        strata = [0] * len(keys)
    if components is None:
        counts = Counter(strata)
        if min(counts.values()) < k:
            _refuse('incompatible_stratum_sizes', smallest=min(counts.values()), folds=k)
        validation = [[] for _ in range(k)]
        by_stratum = defaultdict(list)
        for i, value in enumerate(strata):
            by_stratum[(type(value).__name__, repr(value))].append(i)
        rng = random.Random(seed)
        for positions in by_stratum.values():
            rng.shuffle(positions)
            for j, position in enumerate(positions):
                validation[j % k].append(position)
    else:
        by_group = defaultdict(list)
        for i, group in enumerate(components):
            by_group[group].append(i)
        if len(by_group) < k:
            _refuse('too_few_groups', groups=len(by_group), folds=k)
        # Stable greedy assignment: largest components first, seeded ordering for ties.
        rng = random.Random(seed)
        groups = list(by_group)
        rng.shuffle(groups)
        groups.sort(key=lambda g: -len(by_group[g]))
        validation, sizes = [[] for _ in range(k)], [0] * k
        for group in groups:
            target = min(range(k), key=lambda j: (sizes[j], j))
            validation[target].extend(by_group[group])
            sizes[target] += len(by_group[group])
    folds, universe = [], set(keys)
    for fold_id, positions in enumerate(validation, 1):
        val = [keys[i] for i in sorted(positions)]
        val_set = set(val)
        train = [key for key in keys if key not in val_set]
        if labels is not None and len({labels[keys.index(key)] for key in train}) < 2:
            _refuse('single_class_training_fold', fold=fold_id)
        folds.append({'id': fold_id, 'train_keys': train, 'validation_keys': val,
                      'excluded_train_keys': [], 'excluded_train': [],
                      'validation_start': None, 'validation_end': None})
    return folds, []


def build(row_keys: Sequence[str], protocol: Mapping, *, prediction_order=None,
          outcome_available_order=None, strata=None, labels=None, groups=None,
          duplicate_groups=None, assumptions=(), group_goal=None) -> dict:
    """Build a canonical explicit evaluation plan.

    Metadata accepts either a sequence aligned with ``row_keys`` or a mapping by key.
    ``groups`` and ``duplicate_groups`` are combined transitively when disjointness is
    requested.
    """
    keys = list(row_keys)
    if not keys or len(keys) != len(set(keys)):
        _refuse('row_keys_must_be_nonempty_and_unique')
    method = protocol.get('method')
    if method not in METHODS:
        _refuse('unsupported_method', method=method, supported=list(METHODS))
    prediction = _values(keys, prediction_order, 'prediction_order')
    outcome = _values(keys, outcome_available_order, 'outcome_available_order')
    strata_ = _values(keys, strata, 'strata')
    labels_ = _values(keys, labels, 'labels')
    components = _components(keys, groups, duplicate_groups)
    if method in TEMPORAL_METHODS:
        folds, unscored = _temporal(keys, protocol, prediction, outcome, components, labels_)
    else:
        folds, unscored = _independent(keys, protocol, strata_, components, labels_)
    plan = {'schema': SCHEMA, 'method': method, 'folds': folds,
            'unscored_keys': unscored, 'assumptions': list(assumptions),
            'group_goal': group_goal,
            'outcome_timing_verified': method != 'ordered_retrospective'}
    _validate(plan, set(keys))
    return plan


# Descriptive aliases for callers and small contract tests.
create = build
plan = build
