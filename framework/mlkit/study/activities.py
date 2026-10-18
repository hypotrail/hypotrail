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

A regression study (M3) has its own activities, chosen by the task of the study:
``split`` (``random`` or ``ordinal_cutoff``), ``eda.target_summary``,
``eda.special_values``, ``eda.mean_by:<column>``, ``fit.baseline`` (the training mean),
``fit.linear``, and ``evaluate.regression`` (MAE, RMSE, residuals, paired bootstrap
intervals on validation rows, exposure ``validation_model_evaluation``). Running an
activity of the other task is refused (``invalid_arguments``).

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
TARGET_SUMMARY = 'eda.target_summary'
MEAN_BY = 'eda.mean_by'
LINEAR = 'fit.linear'
REGRESSION_EVALUATION = 'evaluate.regression'
ACTIVITIES = (SPLIT, TARGET_RATE, SPECIAL_VALUES, RATE_BY, BASELINE, LOGISTIC, POLICY,
              TARGET_SUMMARY, MEAN_BY, LINEAR, REGRESSION_EVALUATION)
TASK_ACTIVITIES = {
    'binary': (SPLIT, TARGET_RATE, SPECIAL_VALUES, RATE_BY, BASELINE, LOGISTIC, POLICY),
    'regression': (SPLIT, TARGET_SUMMARY, SPECIAL_VALUES, MEAN_BY, BASELINE, LINEAR,
                   REGRESSION_EVALUATION),
}
ALIASES = {'policy.evaluate': POLICY}
CLI_NAMES = ACTIVITIES + tuple(ALIASES)
EDA = (TARGET_RATE, SPECIAL_VALUES, RATE_BY, TARGET_SUMMARY, MEAN_BY)
PER_COLUMN = (RATE_BY, MEAN_BY)
FITS = (BASELINE, LOGISTIC)
REGRESSION_FITS = (BASELINE, LINEAR)
CANDIDATE_FITS = (LOGISTIC, LINEAR)

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
    TARGET_SUMMARY: (_BASE, 'mlkit.study.eda'),
    MEAN_BY: (_BASE, 'mlkit.study.eda'),
    LINEAR: (_BASE, 'mlkit.study.fit', 'mlkit.study.regression', 'mlkit.classical'),
    REGRESSION_EVALUATION: (_BASE, 'mlkit.study.regression'),
}
# The regression fit of the baseline also uses the error module.
REGRESSION_MODULES = {BASELINE: (_BASE, 'mlkit.study.fit', 'mlkit.study.regression')}
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
LINEAR_PARAMS = {'model': 'linear', 'estimator': 'sklearn.linear_model.LinearRegression',
                 'implementation': 'mlkit.classical.pipeline',
                 'preprocessing': LOGISTIC_PARAMS['preprocessing'],
                 'special_values': LOGISTIC_PARAMS['special_values']}
# A split result's ``groups`` lists at most this many shared group values as examples.
MAX_GROUP_EXAMPLES = 5
MIN_PARTITION_ROWS = 5
# Named refusals of a split (``details.reasons[].capability``).
CAPABILITY_STRATIFY = 'stratified split with fewer than two rows of each class'
CAPABILITY_SPLIT_PARAMETERS = 'random split of these rows with these parameters'


def slot_of(activity: str, options: Mapping | None = None) -> str:
    """The slot a result of ``activity`` is promoted into (``state.current``).

    One slot per activity, except ``eda.rate_by``: one slot per column,
    ``eda.rate_by:<column>``, so exploring a second column never replaces the first.
    The registry entry keeps ``activity: "eda.rate_by"`` and ``params.column``.
    """
    activity = canonical(activity)
    if activity in PER_COLUMN:
        column = (options or {}).get('column')
        if not isinstance(column, str) or not column:
            raise CommandRefused('invalid_arguments', f'{activity} needs --column NAME.')
        return f'{activity}:{column}'
    return activity


def activity_of(slot: str) -> str:
    """The activity of a slot (``eda.rate_by:<column>`` -> ``eda.rate_by``)."""
    for activity in PER_COLUMN:
        if slot.startswith(activity + ':'):
            return activity
    return slot


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
    """The activity's options: ``{"column"}`` (and ``{"max_groups"}`` when given, G.12) for
    ``eda.rate_by`` and ``eda.mean_by``, ``{"rules"}`` for the policy evaluation, ``{}``
    otherwise. Anything else is refused."""
    options = dict(options or {})
    given = {k for k, v in options.items() if v not in (None, [], ())}
    allowed = {RATE_BY: {'column', 'max_groups'}, MEAN_BY: {'column', 'max_groups'},
               POLICY: {'rules'}}.get(activity, set())
    if given - allowed:
        raise CommandRefused('invalid_arguments',
                             f'{activity} does not take {", ".join(sorted(given - allowed))}.',
                             details={'activity': activity, 'options': sorted(allowed)})
    if activity in PER_COLUMN:
        column = options.get('column')
        if not isinstance(column, str) or not column:
            raise CommandRefused('invalid_arguments', f'{activity} needs --column NAME.')
        out = {'column': column}
        if options.get('max_groups') is not None:
            limit = options['max_groups']
            if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
                raise CommandRefused('invalid_arguments', '--max-groups is a whole number of at '
                                                          'least 1.', details={'max_groups': limit})
            out['max_groups'] = limit
        return out
    if activity == POLICY:
        from . import policy
        rules = options.get('rules') or []
        if isinstance(rules, str) or not rules:
            raise CommandRefused('invalid_arguments', 'policy.evaluation needs at least one '
                                                      '--rule (threshold:t or capacity:k).')
        canonical = []
        for rule in rules:
            try:
                policy.parse_rule(rule)
            except ValueError as exc:
                raise CommandRefused('invalid_arguments', str(exc), details={'rule': rule}) from None
            canonical.append(rec.canonical_rule(rule))
        return {'rules': list(dict.fromkeys(canonical))}
    return {}


# --- identity (no pandas) ---------------------------------------------------------------

case_of = c.case_of


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
    task = state.get('task', 'binary')
    if activity not in TASK_ACTIVITIES[task]:
        raise CommandRefused('invalid_arguments',
                             f'{activity} is not an activity of a {task} study.',
                             details={'activities': list(TASK_ACTIVITIES[task]), 'task': task})
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
        decision = state['decisions']['split']['value']
        inputs.update(decision=decision, target=_target(case))
        previous, since = _previous_split(store, state)
        if previous:
            inputs['results'] = {'previous_split': previous}
            inputs['previous_split_stale_since'] = since
        # A stratified split reads the target; a random or ordinal split reads no target,
        # only the time column it cuts on. Each reads the declared group column, whose
        # overlap between partitions it reports.
        if decision.get('method') == 'stratified_random':
            read = [target]
        else:
            read = [decision['column']] if decision.get('method') == 'ordinal_cutoff' else []
        if case.group_column:
            read.append(case.group_column)
            inputs['group_column'] = case.group_column
        if with_exposure:
            from . import data as dt
            expose('structural_inspection', 'all', dt.row_index(case).keys, read)
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
            elif activity in PER_COLUMN:
                column = options['column']
                variable = case.variables.get(column)
                roles = ('feature', 'time') if activity == MEAN_BY else ('feature',)
                if variable is None or variable['role'] not in roles:
                    raise CommandRefused('invalid_arguments',
                                         f'{column!r} is not a feature of this case.',
                                         details={'features': [v['name'] for v in
                                                               case.document['variables']
                                                               if v['role'] in roles]})
                params['column'] = column
                if 'max_groups' in options:      # G.12: only when given, so the default
                    params['max_groups'] = options['max_groups']   # keeps earlier identities
                inputs['special_values'] = feature_special_values(case, [column])
                columns.append(column)
            expose('train_eda', 'train', keys['train'], columns)
        elif activity in FITS or activity == LINEAR:
            inputs['target'] = _target(case)
            features: list[str] = []
            if activity in CANDIDATE_FITS:
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
                if activity == LINEAR:
                    params = dict(LINEAR_PARAMS, seed=0)
                else:
                    params = dict(LOGISTIC_PARAMS,
                                  seed=state['decisions']['split']['value']['seed'])
            elif task == 'regression':
                params = {'model': 'train_mean'}
            else:
                params = {'model': 'constant_prior'}
            expose('train_fit', 'train', keys['train'], features + [target])
            expose('validation_model_evaluation', 'validation', keys['validation'],
                   features + [target])
        elif activity == REGRESSION_EVALUATION:
            # Current fits are a precondition (require_activity). The time column, when the
            # case declares one, breaks the residuals down by period.
            inputs['results'] = {SPLIT: split_rid,
                                 **{s: state['current'][s] for s in REGRESSION_FITS}}
            inputs['bootstrap'] = dict(state['settings']['bootstrap'])
            inputs['target'] = _target(case)
            columns = [case.time_column] if case.time_column else []
            inputs['residual_columns'] = columns
            params = {'models': list(REGRESSION_FITS), 'reference': BASELINE,
                      'candidate': LINEAR, 'metrics': ['mae', 'rmse']}
            expose('validation_model_evaluation', 'validation', keys['validation'],
                   [target] + columns)
        else:   # policy evaluation; current fits are a precondition (require_activity)
            inputs['results'] = {s: state['current'][s] for s in FITS}
            inputs['bootstrap'] = dict(state['settings']['bootstrap'])
            params = {'rules': evaluated_rules(state, options['rules']), 'models': list(FITS),
                      'reference': BASELINE}
            expose('validation_policy_selection', 'validation', keys['validation'], [target])
    modules = (REGRESSION_MODULES.get(activity, MODULES[activity]) if task == 'regression'
               else MODULES[activity])
    code = registry.code_fingerprint(modules)
    key = rec.input_key(activity, rec_json(params), rec_json(inputs), code['fingerprint'])
    return {'activity': activity, 'slot': slot_of(activity, options), 'options': options,
            'params': params,
            'inputs': inputs, 'code': code, 'input_key': key, 'exposures': exposures,
            'case_path': state['case']['path'], 'dataset_sha256': state['dataset']['sha256']}


def adopted_rule(state: Mapping) -> str | None:
    """The policy rule currently adopted (confirmed, or awaiting reconfirmation), if any."""
    decision = state['decisions']['policy']
    value = decision['value']
    if decision['status'] in ('confirmed', 'reconfirm_required') and isinstance(value, str):
        return rec.canonical_rule(value) or value
    return None


def evaluated_rules(state: Mapping, requested) -> list[str]:
    """The rules a policy evaluation computes: the requested ones, then the adopted rule.

    A new evaluation replaces the current one in its slot, so it always includes the
    adopted rule: an adopted policy never silently loses its current evaluation.
    """
    rules = [rec.canonical_rule(r) or r for r in requested]
    adopted = adopted_rule(state)
    if adopted is not None and adopted not in rules:
        rules.append(adopted)
    return rules


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
    """Case and dataset of a plan, with the case and dataset bytes verified against the
    digests the plan was derived from (the case file is read again here, review fix L1)."""
    from . import data as dt
    path = plan_['case_path']
    if os.path.isdir(path):
        path = os.path.join(path, c.CASE_FILE)
    expected = plan_['inputs'].get('case_sha256')
    actual = c.sha256_file(path) if os.path.isfile(path) else None
    if expected is not None and actual != expected:
        raise StudyError('dataset_changed', 'The case file changed after this execution was '
                                            'reserved; its result would not describe the '
                                            'recorded case.',
                         details={'path': str(path), 'expected_sha256': expected,
                                  'actual_sha256': actual})
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
    if decision['method'] != 'stratified_random':
        return compute_unstratified_split(store, plan_, case, dataset)
    frame = dataset.frame
    y = positive(frame, case)
    spec = {'data': {'group_col': None, 'query_col': None, 'time_col': None},
            'split': {'kind': 'random', 'test_size': decision['validation_fraction'],
                      'seed': decision['seed']},
            'task': {'kind': 'binary'}}
    negative = case.document['target'].get('negative_label')
    counts = {str(case.positive_label): int(y.sum()),
              str(negative) if negative is not None else f'not {case.positive_label}':
                  int(len(y) - y.sum())}
    if min(counts.values()) < 2:
        raise StudyError('unsupported_capability',
                         f'The split cannot be made: {CAPABILITY_STRATIFY}.',
                         details={'reasons': [{
                             'code': 'unsupported_capability', 'capability': CAPABILITY_STRATIFY,
                             'path': 'decisions.split', 'counts': counts,
                             'reason': 'A stratified split keeps the outcome share in both '
                                       'partitions, which needs at least two rows of each '
                                       'class; a class with fewer rows cannot be validated.'}]})
    try:
        train, validation = classical.split(frame, y, spec)
    except ValueError as exc:
        raise _split_refusal(exc) from exc
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
    group = plan_['inputs'].get('group_column')
    if group:
        values['groups'] = group_overlap(frame, group, parts)
    previous = plan_['inputs'].get('results', {}).get('previous_split')
    if previous:
        values['overlap'] = _overlap(store, previous,
                                     plan_['inputs'].get('previous_split_stale_since'), parts)
    return {'values': values, 'blobs': blobs, 'partition': 'all', 'n_rows': len(frame)}


def _split_refusal(exc: ValueError) -> StudyError:
    """A split the sampler cannot make with these rows and parameters, as a named reason."""
    return StudyError('unsupported_capability', f'The split cannot be made: {exc}',
                      details={'reasons': [{'code': 'unsupported_capability',
                                            'capability': CAPABILITY_SPLIT_PARAMETERS,
                                            'path': 'decisions.split', 'reason': str(exc)}]})


def _line(key: str) -> int:
    return int(key[1:])


def ordinal_values(frame, column: str):
    """The integer values of a time column, as written (never converted to a date).

    pandas would read an integer such as a two-digit year as nanoseconds since 1970;
    the values are compared as integers instead. Missing or non-integer values are
    refused (``invalid_value``)."""
    import pandas as pd
    raw = frame[column]
    values = pd.to_numeric(raw, errors='coerce')
    bad = raw[values.isna() | (values != values.round())]
    if len(bad):
        raise StudyError('invalid_value', f'The time column {column!r} must hold an integer on '
                                          f'every row to be cut by an ordinal cutoff.',
                         details={'column': column, 'rows': sorted(bad.index, key=_line)[:20]})
    return values.astype('int64')


def group_overlap(frame, column: str, parts: Mapping) -> dict:
    """How many values of the group column the partitions share (M3).

    This version has no grouped split: rows of one group (an entity recorded in several
    periods) can fall in both partitions. The overlap is reported, never hidden, so
    the validation rows are not silently claimed independent of the training rows."""
    groups = {part: frame.loc[list(keys), column].astype(str) for part, keys in parts.items()}
    train, validation = set(groups['train']), set(groups['validation'])
    shared = sorted(train & validation)
    in_shared = groups['validation'].isin(shared)
    n_val = len(groups['validation'])
    return {'column': column, 'n_groups': len(train | validation),
            'train_groups': len(train), 'validation_groups': len(validation),
            'shared_groups': len(shared), 'validation_rows': n_val,
            'validation_rows_in_shared_groups': int(in_shared.sum()),
            'validation_share_in_shared_groups': (float(in_shared.sum()) / n_val
                                                  if n_val else None),
            'examples': shared[:MAX_GROUP_EXAMPLES],
            'capability': c.CAPABILITY_GROUPED_SPLIT,
            'note': 'Grouped split is not available in this version: validation rows of a shared '
                    'group are not independent of the training rows.'}


def compute_unstratified_split(store, plan_: Mapping, case: c.Case, dataset) -> dict:
    """A ``random`` split (numeric target, not stratified) or an ``ordinal_cutoff`` split
    on an integer time column (rows at or above the cutoff go to validation)."""
    import numpy as np
    from mlkit import classical

    decision = plan_['inputs']['decision']
    frame = dataset.frame
    keys = np.asarray(frame.index)
    if decision['method'] == 'ordinal_cutoff':
        column, cutoff = decision['column'], decision['cutoff']
        values = ordinal_values(frame, column)
        is_validation = (values >= cutoff).to_numpy()
        parts = {'train': sorted(keys[~is_validation], key=_line),
                 'validation': sorted(keys[is_validation], key=_line)}
        small = {p: len(k) for p, k in parts.items() if len(k) < MIN_PARTITION_ROWS}
        if small:
            raise StudyError('invalid_value',
                             f'The cutoff {cutoff} on {column!r} leaves fewer than '
                             f'{MIN_PARTITION_ROWS} rows in a partition.',
                             details={'column': column, 'cutoff': cutoff, 'rows': small,
                                      'min': int(values.min()), 'max': int(values.max())})

        def describe(part):
            v = values.loc[parts[part]]
            return {'n_rows': len(parts[part]), 'column_min': int(v.min()),
                    'column_max': int(v.max()), 'distinct_values': int(v.nunique())}
        values_out = {'method': 'ordinal_cutoff', 'column': column, 'cutoff': cutoff,
                      'n_rows': len(frame), 'partitions': {p: describe(p) for p in SPLIT_BLOBS},
                      'validation_share': len(parts['validation']) / len(frame),
                      'stratified_on': None,
                      'implementation': 'mlkit.study.activities (ordinal cutoff on the integer '
                                        'values of the time column, never converted to a date)',
                      'scenario': f'Rows with {column} >= {cutoff} are validated on a model fitted '
                                  f'on rows with {column} < {cutoff}: later periods validated on '
                                  f'earlier ones. Values beyond the training range are '
                                  f'extrapolation.'}
    else:
        spec = {'data': {'group_col': None, 'query_col': None, 'time_col': None},
                'split': {'kind': 'random', 'test_size': decision['validation_fraction'],
                          'seed': decision['seed']},
                'task': {'kind': 'regression'}}
        try:
            train, validation = classical.split(frame, frame.index.to_series(), spec)
        except ValueError as exc:
            raise _split_refusal(exc) from exc
        parts = {'train': sorted(keys[train], key=_line),
                 'validation': sorted(keys[validation], key=_line)}
        values_out = {'method': 'random', 'validation_fraction': decision['validation_fraction'],
                      'seed': decision['seed'], 'stratified_on': None, 'n_rows': len(frame),
                      'partitions': {p: {'n_rows': len(parts[p])} for p in SPLIT_BLOBS},
                      'implementation': 'mlkit.classical.split (random train_test_split, not '
                                        'stratified)'}
    group = plan_['inputs'].get('group_column')
    values_out['groups'] = group_overlap(frame, group, parts) if group else None
    values_out['overlap'] = None
    previous = plan_['inputs'].get('results', {}).get('previous_split')
    if previous:
        values_out['overlap'] = _overlap(store, previous,
                                         plan_['inputs'].get('previous_split_stale_since'), parts)
    blobs = {part: rec.row_keys_bytes(parts[part]) for part in SPLIT_BLOBS}
    return {'values': values_out, 'blobs': blobs, 'partition': 'all', 'n_rows': len(frame)}


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
    if activity in FITS or activity == LINEAR:
        from . import fit
        case, dataset = load(plan_)
        keys = split_keys(store, plan_['inputs']['results'][SPLIT])
        return fit.compute(activity, case, rows(dataset, keys['train']),
                           rows(dataset, keys['validation']), plan_['inputs'], plan_['params'])
    if activity == REGRESSION_EVALUATION:
        return compute_regression_evaluation(store, plan_)
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
    if header == ['row_key', 'y', 'prediction']:
        keys, y, pred = [], [], []
        for row_key, value, prediction in reader:
            keys.append(row_key)
            y.append(float(value))
            pred.append(float(prediction))
        return {'row_keys': keys, 'y': np.asarray(y, dtype=float),
                'prediction': np.asarray(pred, dtype=float)}
    if header != ['row_key', 'y', 'score']:
        raise StudyError('integrity_error', f'Predictions of {rid} have header {header}.')
    keys, y, score = [], [], []
    for row_key, label, value in reader:
        keys.append(row_key)
        y.append(int(label))
        score.append(float(value))
    return {'row_keys': keys, 'y': np.asarray(y, dtype=float), 'score': np.asarray(score)}


def _residual_groups(column: str, values, y, preds: Mapping) -> dict:
    """Residuals by value of ``column`` on validation rows (training-free bins)."""
    import numpy as np
    from . import eda, regression
    labels = values.astype(str).to_numpy()
    distinct = sorted(set(values.dropna().tolist()), key=lambda v: (str(type(v)), v))
    binned = len(distinct) > eda.MAX_DISTINCT_BEFORE_BINNING
    if binned:
        import pandas as pd
        cut = pd.qcut(values, eda.QUANTILE_BINS, duplicates='drop')
        labels = cut.astype(str).to_numpy()
        order = [str(i) for i in cut.cat.categories]
    else:
        order = [str(v) for v in distinct]
    groups = []
    for label in order:
        mask = labels == label
        n = int(mask.sum())
        if not n:
            continue
        groups.append({'value': label, 'n_rows': n, 'small_count': n < eda.MIN_GROUP_ROWS,
                       'models': {slot: {k: v for k, v in regression.errors(
                           y[mask], p[mask]).items() if k in ('mae', 'mean_residual')}
                                  for slot, p in preds.items()}})
    return {'column': column, 'binned': bool(binned),
            'binning': (f'{eda.QUANTILE_BINS} validation quantile bins' if binned else None),
            'groups': groups, 'min_group_rows': eda.MIN_GROUP_ROWS}


def compute_regression_evaluation(store, plan_: Mapping) -> dict:
    """MAE, RMSE, and residuals of both regression fits on the validation rows, with
    paired bootstrap intervals of each and of the candidate's difference with the
    baseline. The predictions are read back from the fits; nothing is refitted."""
    from . import regression

    results = plan_['inputs']['results']
    preds = {slot: read_predictions(store, results[slot]) for slot in REGRESSION_FITS}
    first = preds[REGRESSION_FITS[0]]
    for slot in REGRESSION_FITS[1:]:
        if preds[slot]['row_keys'] != first['row_keys'] or \
                not (preds[slot]['y'] == first['y']).all():
            raise StudyError('integrity_error', 'The fits were not scored on the same validation '
                                                'rows; their errors cannot be compared.',
                             details={'results': {s: results[s] for s in REGRESSION_FITS}})
    y = first['y']
    predictions = {slot: preds[slot]['prediction'] for slot in REGRESSION_FITS}
    boot = plan_['inputs']['bootstrap']
    paired = regression.paired_bootstrap(y, predictions, int(boot['replicates']),
                                         int(boot['seed']), level=float(boot['level']),
                                         reference=plan_['params']['reference'])
    case, dataset = load(plan_)
    frame = rows(dataset, first['row_keys'])
    by = [_residual_groups(column, frame[column], y, predictions)
          for column in plan_['inputs']['residual_columns']]

    values = {'n': len(y), 'target': case.target_column, 'unit': case.target_unit,
              'models': paired['models'], 'intervals': paired['intervals'],
              'deltas': paired['deltas'],
              'residuals': {slot: regression.residual_summary(y, p)
                            for slot, p in predictions.items()},
              'residuals_by': by,
              'predictions': {slot: results[slot] for slot in REGRESSION_FITS},
              'reference': plan_['params']['reference'],
              'candidate': plan_['params']['candidate'],
              'bootstrap': {'replicates': int(boot['replicates']), 'seed': int(boot['seed']),
                            'level': float(boot['level']), 'method': paired['method']},
              'residual_definition': regression.RESIDUAL_DEFINITION,
              'note': 'The model is chosen on these validation rows: these errors are not '
                      'independent evidence of future error. No model was refitted.'}
    return {'values': values, 'blobs': {}, 'partition': 'validation', 'n_rows': len(y)}


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
