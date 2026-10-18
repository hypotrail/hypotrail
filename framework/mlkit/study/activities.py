"""Study activities: what each one reads, its identity, and its computation (plan WP2.2-2.4).

An activity is named by its slot (``CLI-CONTRACT.md`` §8.1): ``split``,
``eda.target_rate``, ``eda.special_values``, ``eda.rate_by:<column>`` (one slot per
column, :func:`slot_of`), ``fit.baseline``, ``fit.logistic``, ``policy.evaluation``
(``policy.evaluate`` is accepted as an alias).

Two functions per run, called by :mod:`mlkit.study.executions`:

* :func:`plan` (under the writer lock, no pandas): checks the preconditions and
  derives the activity's ``params``, ``inputs`` (decision values, dataset digest,
  upstream result ids), code fingerprint, and ``input_key`` **from the state it is
  given**. Calling it again on a later state tells whether a computed result still
  answers the current question (promotion, WP2.1). With ``with_exposure`` it also
  lists the rows the computation will read, by purpose (plan §3.5).
* :func:`compute` (outside the lock): reads the rows and returns the values and
  blobs to store. It never touches state.

Generic by construction: column names, labels, and special values come from the case
(``case.yaml``); no dataset is named in this package.

What each activity reads, and the exposure it records:

==================  =============================  ===========================================
activity            rows read                      exposure purpose
==================  =============================  ===========================================
split               target column of every row     ``structural_inspection`` (stratification)
eda.*               training rows only             ``train_eda``
fit.*               training rows, then validation ``train_fit``, ``validation_model_evaluation``
policy.evaluation   validation predictions         ``validation_policy_selection``
==================  =============================  ===========================================

``HYPOTRAIL_READ_ONLY=1`` makes :func:`compute` refuse (``read_only``): a notebook
opened read-only can display results but never produce one.
"""
from __future__ import annotations

import os
from typing import Any, Mapping

from mlkit.reliability import CommandRefused

from . import case as c
from . import preconditions as pre
from . import records as rec
from . import registry
from .errors import StudyError

SPLIT = 'split'
TARGET_RATE = 'eda.target_rate'
SPECIAL_VALUES = 'eda.special_values'
RATE_BY = 'eda.rate_by'
BASELINE = 'fit.baseline'
LOGISTIC = 'fit.logistic'
POLICY = 'policy.evaluation'
ACTIVITIES = (SPLIT, TARGET_RATE, SPECIAL_VALUES, RATE_BY, BASELINE, LOGISTIC, POLICY)
ALIASES = {'policy.evaluate': POLICY}
CLI_NAMES = ACTIVITIES + tuple(ALIASES)
EDA = (TARGET_RATE, SPECIAL_VALUES, RATE_BY)
FITS = (BASELINE, LOGISTIC)

# Modules whose source defines each result (registry code fingerprint, plan §3.3).
_BASE = 'mlkit.study.activities'
MODULES = {
    SPLIT: (_BASE, 'mlkit.classical'),
    TARGET_RATE: (_BASE, 'mlkit.study.eda'),
    SPECIAL_VALUES: (_BASE, 'mlkit.study.eda'),
    RATE_BY: (_BASE, 'mlkit.study.eda'),
    BASELINE: (_BASE, 'mlkit.study.fit', 'mlkit.study.metrics'),
    LOGISTIC: (_BASE, 'mlkit.study.fit', 'mlkit.study.metrics', 'mlkit.classical'),
    POLICY: (_BASE, 'mlkit.study.policy'),
}
READ_ONLY_ENV = 'HYPOTRAIL_READ_ONLY'
SPLIT_BLOBS = ('train', 'validation')
PREDICTIONS = 'predictions'
LOGISTIC_PARAMS = {'model': 'logistic', 'implementation': 'mlkit.classical.pipeline',
                   'max_iter': 1000,
                   'preprocessing': 'numeric: median imputation and standardisation; '
                                    'categorical: most frequent imputation and one-hot encoding; '
                                    'fitted on training rows only',
                   'special_values': 'numeric special values: indicator column, value imputed; '
                                     'categorical special values: their own category'}


def slot_of(activity: str, options: Mapping | None = None) -> str:
    """The slot a result of ``activity`` is promoted into (``state.current``).

    One slot per activity, except ``eda.rate_by``: one slot per column,
    ``eda.rate_by:<column>``, so exploring a second column never replaces the first.
    The registry entry keeps ``activity: "eda.rate_by"`` and ``params.column``.
    """
    activity = canonical(activity)
    if activity == RATE_BY:
        column = (options or {}).get('column')
        if not isinstance(column, str) or not column:
            raise CommandRefused('invalid_arguments', 'eda.rate_by needs --column NAME.')
        return f'{RATE_BY}:{column}'
    return activity


def activity_of(slot: str) -> str:
    """The activity of a slot (``eda.rate_by:<column>`` -> ``eda.rate_by``)."""
    return RATE_BY if slot.startswith(RATE_BY + ':') else slot


def guard_read_only() -> None:
    if os.environ.get(READ_ONLY_ENV) == '1':
        raise StudyError('read_only', f'{READ_ONLY_ENV}=1: this process may read results but '
                                      'never compute or record one.',
                         details={'environment': READ_ONLY_ENV})


def canonical(activity: str) -> str:
    name = ALIASES.get(activity, activity)
    if name not in ACTIVITIES:
        raise CommandRefused('invalid_arguments', f'Unknown activity {activity!r}.',
                             details={'activities': list(CLI_NAMES)})
    return name


def normalize_options(activity: str, options: Mapping | None) -> dict:
    """The activity's options: ``{"column"}`` for ``eda.rate_by``, ``{"rules"}`` for the
    policy evaluation, ``{}`` otherwise. Anything else is refused."""
    options = dict(options or {})
    given = {k for k, v in options.items() if v not in (None, [], ())}
    allowed = {RATE_BY: {'column'}, POLICY: {'rules'}}.get(activity, set())
    if given - allowed:
        raise CommandRefused('invalid_arguments',
                             f'{activity} does not take {", ".join(sorted(given - allowed))}.',
                             details={'activity': activity, 'options': sorted(allowed)})
    if activity == RATE_BY:
        column = options.get('column')
        if not isinstance(column, str) or not column:
            raise CommandRefused('invalid_arguments', 'eda.rate_by needs --column NAME.')
        return {'column': column}
    if activity == POLICY:
        from . import policy
        rules = options.get('rules') or []
        if isinstance(rules, str) or not rules:
            raise CommandRefused('invalid_arguments', 'policy.evaluation needs at least one '
                                                      '--rule (threshold:t or capacity:k).')
        for rule in rules:
            try:
                policy.parse_rule(rule)
            except ValueError as exc:
                raise CommandRefused('invalid_arguments', str(exc), details={'rule': rule}) from None
        return {'rules': list(dict.fromkeys(rules))}
    return {}


# --- identity (no pandas) ---------------------------------------------------------------

def case_of(state: Mapping, *, verify_data: bool = False) -> c.Case:
    return c.load_case(state['case']['path'], verify_data=verify_data)


def _base_inputs(state: Mapping) -> dict:
    return {'dataset_sha256': state['dataset']['sha256'], 'case_sha256': state['case']['sha256']}


def _target(case: c.Case) -> dict:
    return {'column': case.target_column, 'positive_label': case.positive_label}


def split_keys(store, rid: str) -> dict[str, list[str]]:
    """``{"train": [...], "validation": [...]}`` row keys of split result ``rid``."""
    entry = registry.get(store, rid)
    return {part: rec.parse_row_keys(store.read_blob(entry['blobs'][part])) for part in SPLIT_BLOBS}


def used_features(case: c.Case, availability: Mapping) -> tuple[list[str], dict]:
    """Features a model may use (case column order) and why the others are left out."""
    from .dependencies import USABLE_AVAILABILITY
    used, left_out = [], {}
    for v in case.document['variables']:
        if v['role'] != 'feature':
            continue
        status = availability.get(v['name'])
        if status in USABLE_AVAILABILITY:
            used.append(v['name'])
        else:
            left_out[v['name']] = status
    return used, left_out


def feature_special_values(case: c.Case, columns) -> list[dict]:
    wanted = set(columns)
    return [{'column': s['column'], 'value': s['value']}
            for s in case.document['special_values'] if s['column'] in wanted]


def _previous_split(store, state: Mapping) -> tuple[str | None, int | None]:
    """The split result made stale most recently, and the revision it became stale at.

    The overlap of a new split is reported against it, counting the exposure recorded
    up to that revision, so the result depends on state only (not on later reads).
    """
    best, since = None, None
    for rid, info in state['stale'].items():
        try:
            entry = registry.get(store, rid)
        except StudyError:
            continue
        if entry['activity'] == SPLIT and (since is None or info['since'] > since):
            best, since = rid, info['since']
    return best, since


def _refuse(missing: list[dict], subject: str) -> None:
    if missing:
        raise CommandRefused('precondition_missing', f'{subject} is not possible yet.',
                             details={'missing': missing})


def plan(store, state: Mapping, activity: str, options: Mapping, *,
         with_exposure: bool = False) -> dict:
    """Identity and reads of ``activity`` on ``state`` (see the module docstring).

    Refusals: ``precondition_missing`` (pauses, a missing availability decision, or
    missing fits), ``invalid_arguments`` (an unknown ``--column``).
    """
    activity = canonical(activity)
    options = normalize_options(activity, options)
    pre.require_activity(state, activity)
    case = case_of(state)
    inputs = _base_inputs(state)
    params: dict[str, Any] = {}
    exposures: list[dict] = []
    target = case.target_column

    def expose(purpose, partition, keys, columns):
        if with_exposure:
            data = rec.row_keys_bytes(keys)
            exposures.append({'purpose': purpose, 'partition': partition,
                              'row_keys': store.put_blob(data),
                              'n_rows': len(rec.parse_row_keys(data)), 'columns': list(columns)})

    if activity == SPLIT:
        inputs.update(decision=state['decisions']['split']['value'], target=_target(case))
        previous, since = _previous_split(store, state)
        if previous:
            inputs['results'] = {'previous_split': previous}
            inputs['previous_split_stale_since'] = since
        if with_exposure:
            from . import data as dt
            expose('structural_inspection', 'all', dt.row_index(case).keys, [target])
    else:
        split_rid = state['current'][SPLIT]
        keys = split_keys(store, split_rid)
        inputs['results'] = {SPLIT: split_rid}
        if activity in EDA:
            inputs['target'] = _target(case)
            columns = [target]
            if activity == SPECIAL_VALUES:
                specials = [s for s in case.document['special_values']
                            if case.variables[s['column']]['role'] == 'feature']
                inputs['special_values'] = [{'column': s['column'], 'value': s['value']}
                                            for s in specials]
                columns += sorted({s['column'] for s in specials})
            elif activity == RATE_BY:
                column = options['column']
                variable = case.variables.get(column)
                if variable is None or variable['role'] != 'feature':
                    raise CommandRefused('invalid_arguments',
                                         f'{column!r} is not a feature of this case.',
                                         details={'features': [v['name'] for v in
                                                               case.document['variables']
                                                               if v['role'] == 'feature']})
                params['column'] = column
                inputs['special_values'] = feature_special_values(case, [column])
                columns.append(column)
            expose('train_eda', 'train', keys['train'], columns)
        elif activity in FITS:
            inputs['target'] = _target(case)
            features: list[str] = []
            if activity == LOGISTIC:
                availability = state['decisions']['feature_availability']['value'] or {}
                candidates = [v['name'] for v in case.document['variables']
                              if v['role'] == 'feature']
                missing = [f for f in candidates if f not in availability]
                _refuse([{'requirement': 'availability_decision', 'feature': f,
                          'detail': 'Every candidate feature needs an availability decision '
                                    'before a model may use or ignore it.'} for f in missing],
                        f'Running {activity}')
                features, _ = used_features(case, availability)
                _refuse([] if features else [{'requirement': 'usable_feature',
                                              'detail': 'No feature is available_at_prediction '
                                                        'or uncertain_included.'}],
                        f'Running {activity}')
                inputs['features'] = features
                inputs['special_values'] = feature_special_values(case, features)
                params = dict(LOGISTIC_PARAMS, seed=state['decisions']['split']['value']['seed'])
            else:
                params = {'model': 'constant_prior'}
            expose('train_fit', 'train', keys['train'], features + [target])
            expose('validation_model_evaluation', 'validation', keys['validation'],
                   features + [target])
        else:   # policy evaluation
            missing = [{'requirement': 'result_current', 'slot': s} for s in FITS
                       if s not in state['current']]
            _refuse(missing, f'Running {activity}')
            inputs['results'] = {s: state['current'][s] for s in FITS}
            inputs['bootstrap'] = dict(state['settings']['bootstrap'])
            params = {'rules': list(options['rules']), 'models': list(FITS),
                      'reference': BASELINE}
            expose('validation_policy_selection', 'validation', keys['validation'], [target])
    code = registry.code_fingerprint(MODULES[activity])
    key = rec.input_key(activity, rec_json(params), rec_json(inputs), code['fingerprint'])
    return {'activity': activity, 'slot': slot_of(activity, options), 'options': options,
            'params': params,
            'inputs': inputs, 'code': code, 'input_key': key, 'exposures': exposures,
            'case_path': state['case']['path'], 'dataset_sha256': state['dataset']['sha256']}


def rec_json(obj):
    """``obj`` as the registry stores it (canonical JSON round trip)."""
    import json
    return json.loads(rec.canonical(obj))


# --- computation (outside the lock) -----------------------------------------------------

def matches(series, value, na_values=()):
    """Boolean mask of rows of ``series`` equal to the case value ``value``.

    A value listed in the case ``na_values`` is read as missing, so it matches missing
    cells. A number matches a numeric column by value; anything else by text.
    """
    from pandas.api.types import is_numeric_dtype
    if str(value) in {str(v) for v in na_values}:
        return series.isna()
    if isinstance(value, (int, float)) and not isinstance(value, bool) and is_numeric_dtype(series):
        return series == value
    return series.astype(str) == str(value)


def positive(frame, case: c.Case):
    """1 for rows whose target is the case positive label, else 0."""
    return matches(frame[case.target_column], case.positive_label).astype(int)


def rows(dataset, keys):
    """The rows of ``dataset`` with row keys ``keys``, in that order.

    The single access point to dataset rows for activities: EDA receives only the
    training rows it returns (``test_activities_eda.py`` probes it).
    """
    return dataset.frame.loc[list(keys)]


def load(plan_: Mapping):
    """Case and dataset of a plan, with the dataset bytes verified against state."""
    from . import data as dt
    case = c.load_case(plan_['case_path'])
    if case.dataset['sha256'] != plan_['dataset_sha256']:
        raise StudyError('dataset_changed', 'The case now names a different dataset digest.',
                         details={'expected_sha256': plan_['dataset_sha256'],
                                  'actual_sha256': case.dataset['sha256']})
    return case, dt.load_dataset(case)


def compute_split(store, plan_: Mapping) -> dict:
    import numpy as np
    from mlkit import classical

    case, dataset = load(plan_)
    decision = plan_['inputs']['decision']
    frame = dataset.frame
    y = positive(frame, case)
    spec = {'data': {'group_col': None, 'query_col': None, 'time_col': None},
            'split': {'kind': 'random', 'test_size': decision['validation_fraction'],
                      'seed': decision['seed']},
            'task': {'kind': 'binary'}}
    try:
        train, validation = classical.split(frame, y, spec)
    except ValueError as exc:
        raise StudyError('unsupported_capability', f'The split cannot be made: {exc}',
                         details={'reasons': [str(exc)]}) from exc
    keys = np.asarray(frame.index)
    parts = {'train': sorted(keys[train], key=_line), 'validation': sorted(keys[validation], key=_line)}
    blobs = {part: rec.row_keys_bytes(parts[part]) for part in SPLIT_BLOBS}
    positives = {'train': int(y.iloc[train].sum()), 'validation': int(y.iloc[validation].sum())}
    # The positive counts per partition come from the stratification read of the target
    # (structural_inspection); they show that stratification kept the rate, nothing more.
    values = {'method': decision['method'], 'validation_fraction': decision['validation_fraction'],
              'seed': decision['seed'], 'stratified_on': case.target_column,
              'n_rows': len(frame),
              'partitions': {part: {'n_rows': len(parts[part]), 'n_positive': positives[part],
                                    'rate': positives[part] / len(parts[part])}
                             for part in SPLIT_BLOBS},
              'implementation': 'mlkit.classical.split (stratified train_test_split)',
              'overlap': None}
    previous = plan_['inputs'].get('results', {}).get('previous_split')
    if previous:
        values['overlap'] = _overlap(store, previous,
                                     plan_['inputs'].get('previous_split_stale_since'), parts)
    return {'values': values, 'blobs': blobs, 'partition': 'all', 'n_rows': len(frame)}


def _line(key: str) -> int:
    return int(key[1:])


def _overlap(store, previous: str, since: int | None, parts: Mapping) -> dict:
    """Overlap with the previous split, with the exposure recorded up to revision
    ``since`` (when that split became stale). Explored rows are never unseen."""
    from . import exposure
    exposed: dict[str, set] = {}
    for record in exposure.records(store):
        if since is not None and record['revision'] > since:
            continue
        exposed.setdefault(record['purpose'], set()).update(exposure.rows(store, record))
    out = rec.overlap(split_keys(store, previous), parts, exposed)
    out['previous_split'] = previous
    out['exposure_up_to_revision'] = since
    return out


def compute(store, plan_: Mapping) -> dict:
    """Run the computation of ``plan_`` (from :func:`plan`) and return
    ``{values, blobs, partition, n_rows}``. Never touches state."""
    guard_read_only()
    activity = plan_['activity']
    if activity == SPLIT:
        return compute_split(store, plan_)
    if activity in EDA:
        from . import eda
        case, dataset = load(plan_)
        train = rows(dataset, split_keys(store, plan_['inputs']['results'][SPLIT])['train'])
        return eda.compute(activity, case, train, plan_['params'])
    if activity in FITS:
        from . import fit
        case, dataset = load(plan_)
        keys = split_keys(store, plan_['inputs']['results'][SPLIT])
        return fit.compute(activity, case, rows(dataset, keys['train']),
                           rows(dataset, keys['validation']), plan_['inputs'], plan_['params'])
    return compute_policy(store, plan_)


def read_predictions(store, rid: str) -> dict:
    """``{row_keys, y, score}`` arrays of the predictions blob of fit result ``rid``."""
    import csv
    import gzip
    import io
    import numpy as np

    entry = registry.get(store, rid)
    sha = entry['blobs'].get(PREDICTIONS)
    if sha is None:
        raise StudyError('no_predictions', f'Result {rid} has no predictions blob.',
                         details={'result_id': rid})
    reader = csv.reader(io.StringIO(gzip.decompress(store.read_blob(sha)).decode('utf-8')))
    header = next(reader)
    if header != ['row_key', 'y', 'score']:
        raise StudyError('integrity_error', f'Predictions of {rid} have header {header}.')
    keys, y, score = [], [], []
    for row_key, label, value in reader:
        keys.append(row_key)
        y.append(int(label))
        score.append(float(value))
    return {'row_keys': keys, 'y': np.asarray(y, dtype=float), 'score': np.asarray(score)}


def compute_policy(store, plan_: Mapping) -> dict:
    from . import policy

    fits = plan_['inputs']['results']
    preds = {slot: read_predictions(store, fits[slot]) for slot in FITS}
    first = preds[FITS[0]]
    for slot in FITS[1:]:
        if preds[slot]['row_keys'] != first['row_keys'] or \
                not (preds[slot]['y'] == first['y']).all():
            raise StudyError('integrity_error', 'The fits were not scored on the same validation '
                                                'rows; their policies cannot be compared.',
                             details={'results': dict(fits)})
    boot = plan_['inputs']['bootstrap']
    y = first['y']
    out = {}
    for rule in plan_['params']['rules']:
        points = {slot: policy.evaluate(y, preds[slot]['score'], rule) for slot in FITS}
        paired = policy.paired_bootstrap(y, {s: preds[s]['score'] for s in FITS}, rule,
                                         int(boot['replicates']), int(boot['seed']),
                                         level=float(boot['level']),
                                         reference=plan_['params']['reference'])
        out[rule] = {'models': points, 'intervals': paired['intervals'],
                     'deltas': paired['deltas']}
    values = {'rules': out, 'n': len(y), 'n_positive': int(y.sum()),
              'predictions': dict(fits), 'reference': plan_['params']['reference'],
              'bootstrap': {'replicates': int(boot['replicates']), 'seed': int(boot['seed']),
                            'level': float(boot['level']),
                            'method': 'paired percentile bootstrap over validation rows'},
              'counts': 'expected counts when a capacity cut splits a tie group (tied_at_cut)',
              'note': 'The rule is chosen on validation rows: these figures are not independent '
                      'evidence of future performance. No model was refitted.'}
    return {'values': values, 'blobs': {}, 'partition': 'validation', 'n_rows': len(y)}
