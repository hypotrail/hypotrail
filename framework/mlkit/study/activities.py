"""Study activities: what each one reads, its identity, and its computation (plan WP2.2-2.4).

An activity is named by its slot (``CLI-CONTRACT.md`` §8.1): ``split``,
``eda.target_rate``, ``eda.special_values``, ``eda.rate_by:<column>`` (one slot per
column, :func:`slot_of`), ``fit.baseline``, ``fit.logistic``, ``policy.evaluation``
(``policy.evaluate`` is accepted as an alias). Both tasks also have
``eda.distribution:<column>`` (CLI-CONTRACT-COMPANION §8, C8): one column's training
distribution, which reads that column only and never the outcome.

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
split               target column of every         ``structural_inspection`` (stratification)
                    development row
eda.quality         development rows, every column ``structural_inspection`` (no target)
                    except the target
eda.*               training rows only             ``train_eda``
fit.*               training rows, then validation ``train_fit``, ``validation_model_evaluation``
policy.evaluation   validation predictions         ``validation_policy_selection``
==================  =============================  ===========================================

v0.2b (WP-B1, ADR 0006 amendment). A study whose ``split`` decision is a cross-validation
scheme (``kfold_stratified``, ``kfold_quantile``, ``temporal_folds``; ``state.CV_METHODS``)
assigns every development row to one of ``folds`` folds. Its "training rows" for the
exploration are every development row (the target looks are still counted); each fit is
fitted on the other folds and predicts the rows of each fold, so every development row gets
one out-of-fold prediction (the preprocessing is learnt on each fold's training rows), and
the evaluations read those predictions:

==================  =============================  ===========================================
activity            rows read                      exposure purpose
==================  =============================  ===========================================
split (CV)          the target (or time) column    ``structural_inspection``
eda.*               every development row          ``train_eda`` (partition ``development``)
fit.* (CV)          every development row          ``cross_validated_fit``,
                                                   ``out_of_fold_evaluation``
policy.evaluation   out-of-fold predictions        ``out_of_fold_policy_selection``
evaluate.regression out-of-fold predictions        ``out_of_fold_evaluation``
final_test          development rows (refit), then ``train_fit`` (development),
.evaluation         the final-test rows, once      ``final_evaluation`` (``final_test``)
==================  =============================  ===========================================

``fit.variant`` fits the variant the junior named (``model_variant``: a regularisation
strength, or the candidate without one group of variables) under the same protocol as the
candidate; the evaluations compare it with the candidate (``comparisons``).
``final_test.evaluation`` runs once, after the ``final_test`` decision: it refits the chosen
configuration on every development row and scores the sealed rows; reserving it marks the
final test ``opened`` (:mod:`mlkit.study.partition`).

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
import json
from typing import Any, Mapping

from mlkit.reliability import CommandRefused

from . import case as c
from . import data as dt
from . import preconditions as pre
from . import records as rec
from . import partition
from . import registry
from . import trials
from .errors import StudyError

SPLIT = 'split'
TARGET_RATE = 'eda.target_rate'
SPECIAL_VALUES = 'eda.special_values'
RATE_BY = 'eda.rate_by'
BASELINE = 'fit.baseline'
LOGISTIC = 'fit.logistic'
POLICY = 'policy.evaluation'
POLICY_INSPECT = 'policy.inspect'
POLICY_INSPECTION = 'policy.inspection'
TARGET_SUMMARY = 'eda.target_summary'
MEAN_BY = 'eda.mean_by'
LINEAR = 'fit.linear'
REGRESSION_EVALUATION = 'evaluate.regression'
DISTRIBUTION = 'eda.distribution'
# v0.2a (WP-A4): the structural quality of the development rows (no target) and the
# single-feature signal (a legitimacy question), in both tasks.
QUALITY = 'eda.quality'
SIGNAL = 'eda.single_feature_signal'
# v0.3 (WP-E2, R28): the predictor-versus-predictor association matrix of the development
# rows, without the target (structural, like the quality check; never a target look).
CORRELATION = 'eda.correlation'
# v0.2b (WP-B1): the variant of the candidate, and the one evaluation of the final test.
VARIANT = 'fit.variant'
FINAL = 'final_test.evaluation'
# v0.2b (WP-B4, R9): the model diagnostics of the development rows (one activity per task)
# and of the final test (after its opening, both tasks).
DIAG_BINARY = 'diag.binary'
DIAG_REGRESSION = 'diag.regression'
DIAG_FINAL = 'diag.final_test'
# Library integration v1 (workstream A): the complete predictor of the chosen configuration,
# captured before the final test is opened (mlkit.contracts.capture).
CAPTURE = 'predictor.capture'
ACTIVITIES = (SPLIT, TARGET_RATE, SPECIAL_VALUES, RATE_BY, BASELINE, LOGISTIC, POLICY,
              POLICY_INSPECT,
              TARGET_SUMMARY, MEAN_BY, LINEAR, REGRESSION_EVALUATION, DISTRIBUTION, QUALITY,
              SIGNAL, VARIANT, FINAL, DIAG_BINARY, DIAG_REGRESSION, DIAG_FINAL, CORRELATION,
              CAPTURE)
TASK_ACTIVITIES = {
    'binary': (SPLIT, TARGET_RATE, SPECIAL_VALUES, RATE_BY, BASELINE, LOGISTIC, POLICY,
               POLICY_INSPECT),
    'regression': (SPLIT, TARGET_SUMMARY, SPECIAL_VALUES, MEAN_BY, BASELINE, LINEAR,
                   REGRESSION_EVALUATION),
}
# C8: activities of every task. ``TASK_ACTIVITIES`` is frozen by test_contract_freeze.py,
# so the shared ones are listed here and added by :func:`task_activities`.
SHARED_ACTIVITIES = (DISTRIBUTION, QUALITY, SIGNAL, CORRELATION)
# WP-B1: activities of every task in a study created since WP-B1.
B1_ACTIVITIES = (VARIANT, FINAL)
# WP-B4: the diagnostics of each task. ``diag.final_test`` needs a final test (WP-B1).
DIAG_ACTIVITIES = {'binary': (DIAG_BINARY, DIAG_FINAL),
                   'regression': (DIAG_REGRESSION, DIAG_FINAL)}
DEVELOPMENT_DIAGNOSTICS = (DIAG_BINARY, DIAG_REGRESSION)
# Library integration v1: activities of every task in a study that has a final test.
EXPORT_ACTIVITIES = (CAPTURE,)


def task_activities(task: str) -> tuple[str, ...]:
    """Every activity of a ``task`` study: its own, then the shared ones, then (WP-B1) the
    variant and the final evaluation, which only a study with their decisions can run, then
    (WP-B4) the diagnostics."""
    return (TASK_ACTIVITIES[task] + SHARED_ACTIVITIES + B1_ACTIVITIES + EXPORT_ACTIVITIES
            + DIAG_ACTIVITIES[task])
ALIASES = {'policy.evaluate': POLICY}
# v0.3 (WP-F1): the second and third variants are run by their slot name
# (``fit.variant:2``); the first keeps ``fit.variant``.
VARIANT_SLOT_NAMES = trials.VARIANT_SLOTS[1:]
CLI_NAMES = ACTIVITIES + tuple(ALIASES) + VARIANT_SLOT_NAMES
EDA = (TARGET_RATE, SPECIAL_VALUES, RATE_BY, TARGET_SUMMARY, MEAN_BY, DISTRIBUTION, QUALITY,
       SIGNAL, CORRELATION)
# The EDA activities that read the development rows without the target and need no split.
STRUCTURAL_EDA = (QUALITY, CORRELATION)
PER_COLUMN = (RATE_BY, MEAN_BY, DISTRIBUTION)
# C8: the roles a distribution accepts (a feature, the declared time column, the target).
DISTRIBUTION_ROLES = ('feature', 'time', 'target')
FITS = (BASELINE, LOGISTIC)
REGRESSION_FITS = (BASELINE, LINEAR)
CANDIDATE_FITS = (LOGISTIC, LINEAR)
# Every fit that produces out-of-fold (or validation) predictions of a model.
MODEL_FITS = (BASELINE, LOGISTIC, LINEAR, VARIANT)

# Modules whose source defines each result (registry code fingerprint, plan §3.3).
_BASE = 'mlkit.study.activities'
MODULES = {
    SPLIT: (_BASE, 'mlkit.classical', 'mlkit.study.evaluation_plan'),
    TARGET_RATE: (_BASE, 'mlkit.study.eda'),
    SPECIAL_VALUES: (_BASE, 'mlkit.study.eda'),
    RATE_BY: (_BASE, 'mlkit.study.eda'),
    BASELINE: (_BASE, 'mlkit.study.fit', 'mlkit.study.metrics', 'mlkit.study.objective'),
    LOGISTIC: (_BASE, 'mlkit.study.fit', 'mlkit.study.metrics', 'mlkit.classical',
               'mlkit.study.governance', 'mlkit.study.objective'),
    POLICY: (_BASE, 'mlkit.study.policy', 'mlkit.study.trials', 'mlkit.study.objective'),
    POLICY_INSPECT: (_BASE, 'mlkit.study.policy', 'mlkit.study.trials',
                     'mlkit.study.objective'),
    TARGET_SUMMARY: (_BASE, 'mlkit.study.eda'),
    MEAN_BY: (_BASE, 'mlkit.study.eda'),
    LINEAR: (_BASE, 'mlkit.study.fit', 'mlkit.study.regression', 'mlkit.classical',
             'mlkit.study.governance', 'mlkit.study.objective'),
    REGRESSION_EVALUATION: (_BASE, 'mlkit.study.regression', 'mlkit.study.trials',
                            'mlkit.study.objective'),
    DISTRIBUTION: (_BASE, 'mlkit.study.eda'),
    QUALITY: (_BASE, 'mlkit.study.eda'),
    CORRELATION: (_BASE, 'mlkit.study.correlation'),
    SIGNAL: (_BASE, 'mlkit.study.eda', 'mlkit.study.fit', 'mlkit.study.metrics',
             'mlkit.classical'),
    # v0.3 (WP-F1): the model families, their grids, and the versions of the libraries that
    # fit them (``interpret._version`` and ``sklearn`` hold the version strings).
    VARIANT: (_BASE, 'mlkit.study.fit', 'mlkit.study.metrics', 'mlkit.study.regression',
              'mlkit.classical', 'mlkit.study.governance', 'mlkit.study.families',
              'mlkit.study.trials', 'mlkit.study.objective', 'mlkit.study.evaluation_plan',
              'interpret._version', 'sklearn'),
    FINAL: (_BASE, 'mlkit.study.fit', 'mlkit.study.metrics', 'mlkit.study.policy',
            'mlkit.study.regression', 'mlkit.classical', 'mlkit.study.governance',
            'mlkit.study.families', 'mlkit.study.trials', 'mlkit.study.objective',
            'mlkit.study.evaluation_plan', 'interpret._version', 'sklearn'),
    DIAG_BINARY: (_BASE, 'mlkit.study.diagnostics', 'mlkit.study.fit', 'mlkit.study.metrics',
                  'mlkit.study.policy', 'mlkit.classical', 'mlkit.study.governance'),
    DIAG_REGRESSION: (_BASE, 'mlkit.study.diagnostics', 'mlkit.study.fit',
                      'mlkit.study.regression', 'mlkit.classical', 'mlkit.study.governance'),
    DIAG_FINAL: (_BASE, 'mlkit.study.diagnostics', 'mlkit.study.metrics', 'mlkit.study.policy',
                 'mlkit.study.regression'),
    # Library integration v1: the engine fit it is compared with, the recipe translation and
    # the runtime that fits, captures and reloads it (and the libraries that compute it).
    CAPTURE: (_BASE, 'mlkit.study.fit', 'mlkit.classical', 'mlkit.study.governance',
              'mlkit.study.families', 'mlkit.study.trials', 'mlkit.contracts.capture',
              'mlkit.contracts.recipe', 'mlkit.contracts.context',
              'mlkit.integrations.pandera_validation', 'hypotrail_runtime',
              'hypotrail_runtime.contracts', 'hypotrail_runtime.preprocess',
              'hypotrail_runtime.predictor', 'hypotrail_runtime.families',
              'hypotrail_runtime.inference', 'hypotrail_runtime.canonical', 'sklearn'),
}
# The regression fit of the baseline also uses the error module.
REGRESSION_MODULES = {BASELINE: (_BASE, 'mlkit.study.fit', 'mlkit.study.regression')}
READ_ONLY_ENV = 'HYPOTRAIL_READ_ONLY'
SPLIT_BLOBS = ('train', 'validation')
PREDICTIONS = 'predictions'
# WP-B6a: the Newton-Cholesky solver reaches the optimum of the penalised likelihood. The
# default L-BFGS stopped early along the nearly flat direction that a full one-hot encoding
# and the intercept share, so a stored coefficient could lie outside its own bootstrap
# interval (a one-hot category of a real case). Results recorded without ``solver`` keep
# L-BFGS.
# A tight tolerance (quadratic convergence: a few more steps) keeps the solver's own noise
# along that direction far below the width of a bootstrap interval.
LOGISTIC_SOLVER = 'newton-cholesky'
LOGISTIC_TOL = 1e-8
LOGISTIC_PARAMS = {'model': 'logistic', 'implementation': 'mlkit.classical.pipeline',
                   'max_iter': 1000, 'solver': LOGISTIC_SOLVER, 'tol': LOGISTIC_TOL,
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
# WP-B1: a cross-validation needs at least ``folds`` rows in each stratum it keeps.
CAPABILITY_FOLDS = 'cross-validation folds with fewer rows of a stratum than folds'
FOLDS_BLOB = 'folds'
EVALUATION_PLAN_BLOB = 'evaluation_plan'
# WP-B1: the variant's regularisation (decision ``model_variant``). The candidate logistic
# model has C = 1 (scikit-learn's default); a weaker regularisation is C = 10, a stronger one
# C = 0.1. The candidate linear model is unregularised (ordinary least squares); its
# regularised variants are ridge regressions with alpha = 1 (weak) or 10 (strong), on the
# standardised features.
VARIANT_C = {'weak': 10.0, 'strong': 0.1}
CANDIDATE_C = 1.0
VARIANT_ALPHA = {'weak': 1.0, 'strong': 10.0}


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
    if activity == VARIANT:
        return trials.variant_slot(int((options or {}).get('index') or 1))
    if activity == POLICY_INSPECT:
        return POLICY_INSPECTION
    return activity


def activity_of(slot: str) -> str:
    """The activity of a slot (``eda.rate_by:<column>`` -> ``eda.rate_by``,
    ``fit.variant:2`` -> ``fit.variant``)."""
    for activity in PER_COLUMN + (VARIANT,):
        if slot.startswith(activity + ':'):
            return activity
    if slot == POLICY_INSPECTION:
        return POLICY_INSPECT
    return slot


def resolve(activity: str, options: Mapping | None) -> tuple[str, dict]:
    """v0.3 (WP-F1): a variant slot name (``fit.variant:2``) as its activity and
    ``{"index": 2}``; any other name is returned as it is."""
    options = dict(options or {})
    if activity in VARIANT_SLOT_NAMES:
        given = options.get('index')
        index = trials.variant_index(activity)
        if given not in (None, index):
            raise CommandRefused('invalid_arguments', f'{activity} is variant {index}.')
        options['index'] = index
        return VARIANT, options
    return activity, options


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
               DISTRIBUTION: {'column', 'max_groups'}, POLICY: {'rules'},
               POLICY_INSPECT: {'rules', 'intervals'},
               VARIANT: {'index'}, CAPTURE: {'profile', 'packager'}}.get(activity, set())
    if given - allowed:
        raise CommandRefused('invalid_arguments',
                             f'{activity} does not take {", ".join(sorted(given - allowed))}.',
                             details={'activity': activity, 'options': sorted(allowed)})
    if activity == CAPTURE:
        from mlkit.contracts import capture
        out = {}
        for key in ('profile', 'packager'):
            value = options.get(key)
            if value is not None and (not isinstance(value, str) or not value):
                raise CommandRefused('invalid_arguments', f'--{key} is a name.')
        if options.get('profile') is not None:
            if options['profile'] not in capture.PROFILES:
                raise CommandRefused('invalid_arguments', '--profile is base or workshop.',
                                     details={'profiles': list(capture.PROFILES)})
            out['profile'] = options['profile']
        if options.get('packager') is not None:
            out['packager'] = options['packager']
        return out
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
    if activity in (POLICY, POLICY_INSPECT):
        from . import policy
        rules = options.get('rules') or []
        if isinstance(rules, str) or not rules:
            raise CommandRefused('invalid_arguments', f'{activity} needs at least one '
                                                      '--rule (threshold:t, capacity:k, '
                                                      'or share:p).')
        canonical = []
        for rule in rules:
            try:
                policy.parse_rule(rule)
            except ValueError as exc:
                raise CommandRefused('invalid_arguments', str(exc), details={'rule': rule}) from None
            canonical.append(rec.canonical_rule(rule))
        out = {'rules': list(dict.fromkeys(canonical))}
        if activity == POLICY_INSPECT:
            out['intervals'] = bool(options.get('intervals'))
        return out
    if activity == VARIANT:
        # v0.3 (WP-F1): the first variant has no option, so its identity is unchanged.
        index = options.get('index')
        if index in (None, 1):
            return {}
        if isinstance(index, bool) or not isinstance(index, int) \
                or not 1 <= index <= trials.MAX_VARIANTS:
            raise CommandRefused('invalid_arguments',
                                 f'A variant is numbered 1 to {trials.MAX_VARIANTS}.',
                                 details={'index': index})
        return {'index': index}
    return {}


# --- identity (no pandas) ---------------------------------------------------------------

case_of = c.case_of


def _base_inputs(state: Mapping) -> dict:
    """Inputs every activity records. A study with a sealed final test (ADR 0006) adds
    ``development``, the blob of the rows its activities may read; a legacy study has no
    such key, so its identities are unchanged."""
    out = {'dataset_sha256': state['dataset']['sha256'], 'case_sha256': state['case']['sha256']}
    development = partition.inputs(state)
    if development is not None:
        out['development'] = development
    return out


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
    activity, options = resolve(activity, options)
    activity = canonical(activity)
    task = state.get('task', 'binary')
    if activity not in task_activities(task):
        raise CommandRefused('invalid_arguments',
                             f'{activity} is not an activity of a {task} study.',
                             details={'activities': list(task_activities(task)), 'task': task})
    options = normalize_options(activity, options)
    from . import state as st
    if (activity in B1_ACTIVITIES or activity in EXPORT_ACTIVITIES or activity == DIAG_FINAL) \
            and not st.has_wp_b1_decisions(state):
        raise CommandRefused('invalid_arguments',
                             f'{activity} is not an activity of this study: it was created before '
                             f'the variant and the final test existed.',
                             details={'activities': [a for a in task_activities(task)
                                                     if a not in B1_ACTIVITIES], 'task': task})
    # v0.3 (WP-F1): a variant's requirements name its slot (its index).
    pre.require_activity(state, slot_of(activity, options) if activity == VARIANT
                         else activity)
    case = case_of(state)
    inputs = _base_inputs(state)
    params: dict[str, Any] = {}
    # Human-authored wording belongs in the result we present, but not in the numerical
    # identity of the evaluation.  Keep a frozen copy in the in-memory execution plan: the
    # registry still receives only ``params`` and ``inputs`` below.
    presentation: dict[str, Any] = {}
    exposures: list[dict] = []
    target = case.target_column

    def expose(purpose, partition, keys, columns):
        if with_exposure:
            data = rec.row_keys_bytes(keys)
            exposures.append({'purpose': purpose, 'partition': partition,
                              'row_keys': store.put_blob(data),
                              'n_rows': len(rec.parse_row_keys(data)), 'columns': list(columns)})

    if activity == QUALITY:
        # WP-A4: the development rows without the target; no split, no decision needed. The
        # rows read are those of the structural inspection recorded at ``init``.
        columns = [v['name'] for v in case.document['variables'] if v['name'] != target]
        params['partition'] = _rows_partition(inputs)
        inputs['columns'] = columns
        if case.duplicates_policy:
            inputs['duplicates'] = case.duplicates_policy   # record groups reported (WP-B3)
        if with_exposure:
            keys = partition.development_keys(store.read_blob, inputs.get('development'))
            if keys is None:
                from . import data as dt
                keys = dt.row_index(case).keys
            expose('structural_inspection', _rows_partition(inputs), keys, columns)
    elif activity == CORRELATION:
        # v0.3 (WP-E2): the candidate features of the development rows, never the target;
        # no split and no decision needed, recorded as a structural inspection.
        columns = [v['name'] for v in case.document['variables'] if v['role'] == 'feature']
        params['partition'] = _rows_partition(inputs)
        inputs['columns'] = columns
        inputs['special_values'] = feature_special_values(case, columns)
        if with_exposure:
            keys = partition.development_keys(store.read_blob, inputs.get('development'))
            if keys is None:
                from . import data as dt
                keys = dt.row_index(case).keys
            expose('structural_inspection', _rows_partition(inputs), keys, columns)
    elif activity == SPLIT:
        decision = state['decisions']['split']['value']
        inputs.update(decision=decision, target=_target(case))
        previous, since = _previous_split(store, state)
        if previous:
            inputs['results'] = {'previous_split': previous}
            inputs['previous_split_stale_since'] = since
        # A stratified split reads the target; a random or ordinal split reads no target,
        # only the time column it cuts on. Each reads the declared group column, whose
        # overlap between partitions it reports.
        if decision.get('method') in ('stratified_random', 'kfold_stratified',
                                      'kfold_quantile'):
            read = [target]
        elif decision.get('method') in ('temporal_folds', 'forward_chaining',
                                        'ordered_retrospective'):
            # WP-B1: blocks in time order, by the time column (else the declared order).
            column = time_order_column(case)
            inputs['order_column'] = column
            read = [column] if column != 'line' else []
            if decision.get('method') in ('forward_chaining', 'ordered_retrospective'):
                contract = case.document['analysis_contract']
                inputs['analysis_contract'] = contract
                prediction = contract['timing']['prediction_order']['by']
                outcome = contract['timing'].get('outcome_available_order')
                read = [] if prediction == 'line' else [prediction]
                if isinstance(outcome, Mapping) and outcome['by'] != 'line':
                    read.append(outcome['by'])
        elif decision.get('method') == 'group_disjoint':
            read = [target]
            inputs['analysis_contract'] = case.document['analysis_contract']
        else:
            read = [decision['column']] if decision.get('method') == 'ordinal_cutoff' else []
        if case.group_column:
            read.append(case.group_column)
            inputs['group_column'] = case.group_column
        contract = case.document.get('analysis_contract')
        if decision.get('method') in st.REVIEW_CV_METHODS and contract:
            inputs['analysis_contract'] = contract
            group_column = contract['dependencies'].get('group_column')
            if group_column:
                inputs['group_column'] = group_column
                if group_column not in read:
                    read.append(group_column)
        if case.duplicates_policy:
            # v0.2b (WP-B3): identical records stay together (no key otherwise, so earlier
            # identities are unchanged).
            inputs['duplicates'] = case.duplicates_policy
        if with_exposure:
            # The stratification reads the development rows only (ADR 0006); a legacy
            # study without a final test reads every row.
            keys = partition.development_keys(store.read_blob, inputs.get('development'))
            if keys is None:
                from . import data as dt
                keys = dt.row_index(case).keys
            expose('structural_inspection', _rows_partition(inputs), keys, read)
    elif activity == FINAL:
        _plan_final(store, state, case, inputs, params, exposures, expose)
    elif activity == CAPTURE:
        from mlkit.contracts import capture
        capture.plan(store, state, case, inputs, params, options, expose)
    elif activity == DIAG_FINAL:
        params = _plan_final_diagnostics(store, state, case, inputs, expose)
    elif activity in DEVELOPMENT_DIAGNOSTICS:
        params = _plan_diagnostics(store, state, case, activity, inputs, expose)
    else:
        split_rid = state['current'][SPLIT]
        keys = split_keys(store, split_rid)
        inputs['results'] = {SPLIT: split_rid}
        cv = split_scheme(store, split_rid)
        # WP-B1: under cross-validation the exploration reads every development row.
        eda_partition = partition.DEVELOPMENT if cv else 'train'
        if activity == DISTRIBUTION:
            # C8: one column of the training rows, never the outcome (unless the column
            # is the target itself); no target in the inputs, the result does not depend
            # on it.
            column = options['column']
            variable = case.variables.get(column)
            if variable is None or variable['role'] not in DISTRIBUTION_ROLES:
                raise CommandRefused('invalid_arguments',
                                     f'{column!r} is not a feature, the time column, or the '
                                     f'target of this case.',
                                     details={'columns': [v['name'] for v in
                                                          case.document['variables']
                                                          if v['role'] in DISTRIBUTION_ROLES]})
            params['column'] = column
            if 'max_groups' in options:
                params['max_groups'] = options['max_groups']
            inputs['special_values'] = feature_special_values(case, [column])
            expose('train_eda', eda_partition, keys['train'], [column])
        elif activity == SIGNAL:
            # WP-A4: every candidate feature alone, out of fold, on training rows; the
            # availability decision is shown next to each signal, never acted upon.
            availability = dict(state['decisions']['feature_availability']['value'] or {})
            candidates = [v['name'] for v in case.document['variables']
                          if v['role'] == 'feature']
            inputs['target'] = _target(case)
            inputs['candidates'] = candidates
            inputs['availability'] = availability
            inputs['special_values'] = feature_special_values(case, candidates)
            from . import eda
            params = {'folds': eda.SIGNAL_FOLDS, 'seed': eda.SIGNAL_SEED,
                      'metric': 'roc_auc' if task == 'binary' else 'r2'}
            if case.duplicates_policy:
                inputs['duplicates'] = case.duplicates_policy   # grouped folds (WP-B3)
            expose('train_eda', eda_partition, keys['train'], candidates + [target])
        elif activity in EDA:
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
                from . import assurance
                contract = case.document.get('analysis_contract') or {}
                dependence = (contract.get('dependencies') or {}).get('kind')
                if assurance.profile(state) == 'review-v1' and dependence != 'independent':
                    params['shuffle_envelope'] = False
            expose('train_eda', eda_partition, keys['train'], columns)
        elif activity in MODEL_FITS:
            inputs['target'] = _target(case)
            features: list[str] = []
            if activity in CANDIDATE_FITS or activity == VARIANT:
                model_inputs, params = model_plan(state, case, activity,
                                                  index=int(options.get('index') or 1))
                inputs.update(model_inputs)
                features = list(inputs['features'])
            elif task == 'regression':
                params = {'model': 'train_mean'}
            else:
                params = {'model': 'constant_prior'}
            if cv:
                # WP-B1: each fold fitted on the other folds; every development row predicted
                # once, out of fold.
                inputs['evaluation'] = dict(cv)
                expose('cross_validated_fit', partition.DEVELOPMENT, keys['train'],
                       features + [target])
                expose('out_of_fold_evaluation', partition.DEVELOPMENT, keys['validation'],
                       features + [target])
            else:
                expose('train_fit', 'train', keys['train'], features + [target])
                expose('validation_model_evaluation', 'validation', keys['validation'],
                       features + [target])
        elif activity == REGRESSION_EVALUATION:
            # Current fits are a precondition (require_activity). The time column, when the
            # case declares one, breaks the residuals down by period.
            models = compared_models(state, REGRESSION_FITS)
            inputs['results'] = {SPLIT: split_rid, **{s: state['current'][s] for s in models}}
            inputs['bootstrap'] = dict(state['settings']['bootstrap'])
            inputs['target'] = _target(case)
            columns = [case.time_column] if case.time_column else []
            inputs['residual_columns'] = columns
            params = {'models': models, 'reference': BASELINE,
                      'candidate': LINEAR, 'metrics': ['mae', 'rmse']}
            display_variants = _selection_inputs(state, inputs, models)
            if display_variants is not None:
                presentation['variants'] = display_variants
            from . import assurance, state as st
            if assurance.profile(state) == 'review-v1':
                inputs['success_criterion'] = dict(
                    state['decisions'][st.SUCCESS_CRITERION]['value'])
            if cv:
                params['evaluation'] = 'out_of_fold'
                expose('out_of_fold_evaluation', partition.DEVELOPMENT, keys['validation'],
                       [target] + columns)
            else:
                expose('validation_model_evaluation', 'validation', keys['validation'],
                       [target] + columns)
        else:   # policy evaluation/inspection; current fits are a precondition
            models = compared_models(state, FITS)
            inputs['results'] = {s: state['current'][s] for s in models}
            if activity == POLICY or options.get('intervals'):
                inputs['bootstrap'] = dict(state['settings']['bootstrap'])
            rules = (evaluated_rules(state, options['rules']) if activity == POLICY
                     else list(options['rules']))
            params = {'rules': rules, 'models': models,
                      'reference': BASELINE}
            if activity == POLICY_INSPECT:
                params.update(intervals=bool(options.get('intervals')),
                              purpose='policy_exploration')
                inputs['prediction_blobs'] = {
                    slot: registry.get(store, rid)['blobs'][PREDICTIONS]
                    for slot, rid in inputs['results'].items()}
            from . import assurance, state as st
            if assurance.profile(state) == 'review-v1':
                inputs['success_criterion'] = dict(
                    state['decisions'][st.SUCCESS_CRITERION]['value'])
            display_variants = _selection_inputs(state, inputs, models)
            if display_variants is not None:
                presentation['variants'] = display_variants
            if cv:
                params['evaluation'] = 'out_of_fold'
                # B6c (H3): a capacity or a share is applied within each fold, so the folds
                # are an input (the split that assigned them).
                params['selection'] = WITHIN_FOLD
                inputs['fold_split'] = split_rid
                expose('policy_exploration' if activity == POLICY_INSPECT
                       else 'out_of_fold_policy_selection',
                       partition.DEVELOPMENT, keys['validation'],
                       [target])
            else:
                expose('policy_exploration' if activity == POLICY_INSPECT
                       else 'validation_policy_selection',
                       'validation', keys['validation'], [target])
    modules = (REGRESSION_MODULES.get(activity, MODULES[activity]) if task == 'regression'
               else MODULES[activity])
    code = registry.code_fingerprint(modules)
    key = rec.input_key(activity, rec_json(params), rec_json(inputs), code['fingerprint'])
    result = {'activity': activity, 'slot': slot_of(activity, options), 'options': options,
              'params': params,
              'inputs': inputs, 'code': code, 'input_key': key, 'exposures': exposures,
              'case_path': state['case']['path'], 'dataset_sha256': state['dataset']['sha256']}
    if presentation:
        result['presentation'] = presentation
    return result


def _selection_inputs(state: Mapping, inputs: dict, models: list) -> list[dict] | None:
    """v0.3 (WP-F1): an evaluation that compares variants also records the selection among
    them (:func:`mlkit.study.trials.select`). Its identity inputs name only the numerical
    variant specs and the budget. The returned full variants are presentation metadata,
    frozen for this execution without making their questions part of ``input_key``."""
    if not any(trials.is_variant_slot(m) for m in models):
        return None
    from . import state as st
    variants = trials.variants_of(state['decisions'][st.MODEL_VARIANT]['value'])
    inputs['variants'] = [trials.spec_of(v) for v in variants]
    inputs['trial_budget'] = trials.budget(state)
    return variants


def _selection_values(store, plan_: Mapping, models: list, task: str,
                      objectives: Mapping | None = None) -> dict | None:
    """The stored selection of an evaluation (WP-F1), from the fits it compares."""
    variants = (plan_.get('presentation') or {}).get('variants')
    if variants is None:       # legacy/direct plans contained only the numerical specs
        variants = plan_['inputs'].get('variants')
    if variants is None:
        return None
    results = plan_['inputs']['results']
    fits = {m: registry.get(store, results[m])['output']['values'] for m in models
            if m != BASELINE and m in results}
    return trials.select(fits, variants, task, plan_['inputs']['trial_budget'],
                         objectives=objectives)


def adopted_rule(state: Mapping) -> str | None:
    """The policy rule currently adopted (confirmed, or awaiting reconfirmation), if any
    (WP-B1: the rule part of a value that names the variant)."""
    decision = state['decisions']['policy']
    value = decision['value']
    if decision['status'] in ('confirmed', 'reconfirm_required') and isinstance(value, str):
        return rec.policy_rule(value) or value
    return None


# --- WP-B1: models, folds, variant, final test (no pandas) -------------------------------

def time_order_column(case: c.Case) -> str:
    """The column temporal folds follow: the time column, else the declared order's column
    (``line`` for the file order)."""
    if case.time_column:
        return case.time_column
    order = case.order or {}
    return order.get('by') or 'line'


def split_scheme(store, split_rid: str) -> dict | None:
    """``{scheme, method, folds}`` of a cross-validation split result, else None."""
    entry = registry.get(store, split_rid)
    values = entry['output']['values']
    from . import state as st
    if values.get('method') in st.CV_METHODS:
        return {'scheme': 'cross_validation', 'method': values['method'],
                'folds': values['folds']}
    return None


def fold_assignment(store, split_rid: str) -> dict[str, int] | None:
    """``{row_key: fold}`` of a cross-validation split result (folds numbered from 1), or
    None for a train/validation split."""
    entry = registry.get(store, split_rid)
    sha = entry['blobs'].get(FOLDS_BLOB)
    if sha is None:
        return None
    out = {}
    for line in store.read_blob(sha).decode('utf-8').splitlines()[1:]:
        key, _, fold = line.partition(',')
        out[key] = int(fold)
    return out


def evaluation_membership(store, split_rid: str) -> dict | None:
    """The explicit J1 plan, or ``None`` for an immutable legacy split result."""
    entry = registry.get(store, split_rid)
    sha = entry['blobs'].get(EVALUATION_PLAN_BLOB)
    if sha is None:
        return None
    try:
        plan = json.loads(store.read_blob(sha))
    except (ValueError, UnicodeDecodeError) as exc:
        raise StudyError('integrity_error', 'The evaluation-plan blob is not valid JSON.') from exc
    from . import evaluation_plan as ep
    if plan.get('schema') != ep.SCHEMA or ep.digest(plan) != \
            (entry['output']['values'].get('evaluation_plan') or {}).get('digest'):
        raise StudyError('integrity_error', 'The evaluation plan does not match its digest.')
    return plan


def compared_models(state: Mapping, fits: tuple) -> list[str]:
    """The model slots an evaluation compares: the baseline and the candidate, and (WP-B1)
    the variant once the junior named it (v0.3, WP-F1: every variant the junior named, up to
    three, in order)."""
    from . import state as st
    models = list(fits)
    if st.has_wp_b1_decisions(state) and \
            state['decisions'][st.MODEL_VARIANT]['status'] == 'confirmed':
        models += trials.declared_slots(state)
    return models


def variant_pairs(models, candidate: str) -> list[tuple[str, str]]:
    """The paired comparisons of an evaluation: each variant against the candidate."""
    return [(m, candidate) for m in models if trials.is_variant_slot(m)]


def model_plan(state: Mapping, case: c.Case, activity: str,
               variant: Mapping | None = None, index: int = 1) -> tuple[dict, dict]:
    """``(inputs, params)`` of a model fit: the candidate (``fit.logistic`` or
    ``fit.linear``) or a variant (``fit.variant``, the variant ``index`` of the confirmed
    ``model_variant``, or ``variant``). Refusals: ``precondition_missing`` (a feature without
    an availability decision, no usable feature, a variant that removes every feature or
    none, a variant the decision does not declare).

    v0.3 (WP-F1): the question a variant answers is not part of its identity; a ``tuned``
    variant adds ``tuning`` (the grid of the candidate's penalty), a ``family`` variant adds
    ``family``, its fixed ``settings``, its ``tuning`` grid, and the library ``versions``;
    variants 2 and 3 add ``variant_index``."""
    from . import governance, state as st
    task = st.task_of(state)
    availability = state['decisions']['feature_availability']['value'] or {}
    from . import assurance, validity
    if assurance.profile(state) == 'review-v1':
        # Recheck at the computation boundary: a hand-edited decision must not bypass a
        # documented scenario restriction.
        validity.require_availability(case, availability)
    candidates = [v['name'] for v in case.document['variables'] if v['role'] == 'feature']
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
    if activity == VARIANT:
        if variant is None:
            declared = trials.variants_of(state['decisions'][st.MODEL_VARIANT]['value'])
            _refuse([] if index <= len(declared) else [{
                'requirement': 'variant_declared', 'index': index,
                'detail': f'The variant decision declares {len(declared)} variant(s); name '
                          f'variant {index} before fitting it.'}], f'Running {activity}')
            variant = declared[index - 1]
        variant = trials.spec_of(variant)
        if assurance.profile(state) == 'review-v1' \
                and variant.get('kind') == 'family' and variant.get('family') == 'hgb' \
                and (((case.document.get('constraints') or {}).get('interpretability') or {})
                     .get('value') == 'required'):
            _refuse([{'requirement': 'interpretability_constraint_satisfied',
                      'family': 'hgb',
                      'detail': 'The case requires an interpretable model; histogram '
                                'gradient boosting is not admissible.'}], f'Running {activity}')
        if variant.get('kind') == 'drop_group':
            group = {v['name'] for v in case.document['variables']
                     if v['role'] == 'feature' and v.get('group') == variant['group']}
            kept = [f for f in features if f not in group]
            dropped = [f for f in features if f in group]
            _refuse([] if kept and dropped else [{
                'requirement': 'variant_changes_model', 'group': variant['group'],
                'detail': ('Leaving out this group removes no feature the candidate uses.'
                           if not dropped else 'Leaving out this group leaves no feature.')}],
                f'Running {activity}')
            features = kept
    inputs = {'features': features, 'special_values': feature_special_values(case, features)}
    if assurance.profile(state) == 'review-v1':
        inputs['analysis_contract'] = case.document['analysis_contract']
        inputs['evaluation_protocol'] = dict(state['decisions']['split']['value'])
    # WP-A4: the confirmed preprocessing, in a study that has the decision (an earlier study
    # keeps its identities: no key).
    preprocessing = governance.effective_preprocessing(state)
    if preprocessing is not None:
        inputs['preprocessing'] = preprocessing
    seed = state['decisions']['split']['value'].get('seed') or 0
    if task == st.REGRESSION:
        params = dict(LINEAR_PARAMS, seed=0)
    else:
        params = dict(LOGISTIC_PARAMS, seed=seed)
    if activity == VARIANT:
        inputs['variant'] = variant
        kind = variant.get('kind')
        if kind == 'regularisation':
            if task == st.REGRESSION:
                params.update(model='ridge', estimator='sklearn.linear_model.Ridge',
                              alpha=VARIANT_ALPHA[variant['strength']])
            else:
                params.update(C=VARIANT_C[variant['strength']], candidate_C=CANDIDATE_C)
        elif kind == 'drop_group':
            params['dropped_group'] = variant['group']
        elif kind == 'tuned':
            # WP-F1: the candidate's penalty chosen by nested cross-validation.
            if task == st.REGRESSION:
                params.update(model='ridge', estimator='sklearn.linear_model.Ridge')
            params['tuning'] = trials.grid('linear', task)
        elif kind == 'family':
            family = variant['family']
            settings = dict(trials.EBM_SETTINGS if family == 'ebm' else trials.HGB_SETTINGS)
            params = {'model': family, 'family': family,
                      'implementation': trials.CATALOGUE[family]['implementation'],
                      'preprocessing': LOGISTIC_PARAMS['preprocessing'],
                      'special_values': LOGISTIC_PARAMS['special_values'],
                      'settings': settings, 'tuning': trials.grid(family, task),
                      'seed': params['seed']}
        if index > 1:
            params['variant_index'] = index
    if assurance.profile(state) == 'review-v1' and params.get('tuning'):
        criterion_value = (state['decisions'].get(st.SUCCESS_CRITERION) or {}).get('value')
        if criterion_value is not None:
            inputs['success_criterion'] = {'metric': criterion_value['metric'],
                                           'selection': dict(criterion_value['selection'])}
    return inputs, params


def _plan_final(store, state: Mapping, case: c.Case, inputs: dict, params: dict,
                exposures: list, expose) -> None:
    """WP-B1: the identity and reads of ``final_test.evaluation`` (in place). The chosen
    configuration (the ``final_test`` decision's value), its model inputs, the bootstrap,
    the criterion, and the two row sets; no upstream result (the evaluation stays the record
    of what was measured, whatever changes after it)."""
    from . import state as st
    task = st.task_of(state)
    config = dict(state['decisions'][st.FINAL_TEST]['value'])
    part = partition.of(state)
    model = config['model']
    inputs['target'] = _target(case)
    inputs['configuration'] = config
    if model in CANDIDATE_FITS:
        model_inputs, model_params = model_plan(state, case, model)
    elif trials.is_variant_slot(model):
        model_inputs, model_params = model_plan(state, case, VARIANT,
                                                index=trials.variant_index(model))
    else:   # the baseline was chosen (regression)
        model_inputs, model_params = {'features': [], 'special_values': []}, {}
    inputs['model_inputs'] = model_inputs
    if state['current'].get(CAPTURE):
        # Library integration v1: once a study captured its predictor, the final test
        # evaluates the reloaded capture of this exact configuration (no key otherwise, so
        # earlier identities are unchanged).
        from mlkit.contracts import capture
        predictor = capture.matching_capture(store, state, case, model_inputs, model_params,
                                             config)
        if predictor is not None:
            inputs['predictor'] = predictor
            inputs.setdefault('results', {})[CAPTURE] = predictor['result_id']
    inputs['final_test'] = {'row_keys': part['final_test']['row_keys'],
                            'n_rows': part['final_test']['n_rows']}
    inputs['bootstrap'] = dict(state['settings']['bootstrap'])
    criterion = state['decisions'][st.SUCCESS_CRITERION]['value']
    inputs['criterion'] = criterion
    params.update(model=model, rule=config.get('rule'), model_params=model_params,
                  reference=BASELINE, task=task)
    review_criterion = isinstance(criterion, Mapping) and 'decision_rule' in criterion
    if rec.capacity_of(config.get('rule')) is not None and not review_criterion:
        # The capacity was chosen on the rows the policy evaluation scored (every development
        # row out of fold, or the validation rows); on the final test it keeps its share.
        chosen_on = registry.get(store, state['current'][POLICY])['output']['values']['n']
        params['capacity_share'] = rec.capacity_share(config.get('rule'), chosen_on)
    elif rec.share_of(config.get('rule')) is not None:
        # v0.2b (WP-B3): a share is already a share; the rule is applied as it is.
        params['capacity_share'] = rec.share_of(config.get('rule'))
    features = list(model_inputs['features'])
    target = case.target_column
    development = partition.development_keys(store.read_blob, inputs.get('development'))
    final = rec.parse_row_keys(store.read_blob(part['final_test']['row_keys'])) \
        if exposures is not None else []
    expose('train_fit', partition.DEVELOPMENT, development, features + [target])
    expose('final_evaluation', partition.FINAL_TEST, final, features + [target])


# --- WP-B4: diagnostics (no pandas) ---------------------------------------------------------

def diagnostic_rule(state: Mapping, case: c.Case) -> tuple[str, str]:
    """``(rule, source)`` of the binary diagnostics: the adopted rule, else the rule of the
    latest open policy proposal, else the case's teaching share, else
    :data:`mlkit.study.diagnostics.DEFAULT_RULE`."""
    from . import diagnostics
    adopted = adopted_rule(state)
    if adopted is not None:
        return adopted, 'adopted'
    proposals = sorted((p for p in state['proposals'].values()
                        if p['status'] == 'open' and p['decision_id'] == 'policy'),
                       key=lambda p: (p['revision'], p['proposal_id']))
    for p in reversed(proposals):
        rule = rec.policy_rule(p['value'])
        if rule is not None:
            return rule, 'proposed'
    share = ((case.scenario_defaults or {}).get('capacity_share') or {}).get('value')
    if isinstance(share, (int, float)) and not isinstance(share, bool) and 0 < share <= 1:
        return rec.canonical_rule(f'share:{share:g}') or f'share:{share:g}', 'scenario_default'
    return diagnostics.DEFAULT_RULE, 'engine_default'


def _plan_diagnostics(store, state: Mapping, case: c.Case, activity: str, inputs: dict,
                      expose) -> dict:
    """WP-B4: the identity and reads of ``diag.binary`` / ``diag.regression`` (inputs in
    place); returns the params. The predictions of the candidate and the variant are read
    back from their fits; the rows they scored are read for the segments, the examples and
    the residuals by feature, and the rows their coefficients come from for their intervals."""
    from . import diagnostics, state as st
    task = st.task_of(state)
    expected = DIAG_REGRESSION if task == st.REGRESSION else DIAG_BINARY
    if activity != expected:
        raise CommandRefused('invalid_arguments', f'{activity} is not an activity of a {task} '
                                                  f'study; run {expected}.',
                             details={'activities': list(task_activities(task)), 'task': task})
    split_rid = state['current'][SPLIT]
    keys = split_keys(store, split_rid)
    cv = split_scheme(store, split_rid)
    fits = FITS if task == st.BINARY else REGRESSION_FITS
    models = [m for m in compared_models(state, fits) if m != BASELINE]
    inputs['results'] = {SPLIT: split_rid, **{m: state['current'][m] for m in models}}
    inputs['target'] = _target(case)
    features: list[str] = []
    for m in models:
        for f in registry.get(store, state['current'][m])['inputs'].get('features') or []:
            if f not in features:
                features.append(f)
    params: dict[str, Any] = {
        'models': models, 'evaluation': 'out_of_fold' if cv else 'validation',
        'coefficients': {'intervals': diagnostics.COEFFICIENT_INTERVALS,
                         'level': diagnostics.COEFFICIENT_LEVEL},
        'segments': diagnostics.segment_columns(case, features)}
    if task == st.BINARY:
        rule, source = diagnostic_rule(state, case)
        params.update(rule=rule, rule_source=source)
    else:
        params['residual_columns'] = diagnostics.residual_columns(case, features)
    target = case.target_column
    scored = partition.DEVELOPMENT if cv else 'validation'
    expose(diagnostics.DEVELOPMENT_PURPOSE, scored, keys['validation'], features + [target])
    if not cv:   # the coefficients come from the training rows
        expose(diagnostics.DEVELOPMENT_PURPOSE, 'train', keys['train'], features + [target])
    return params


def _plan_final_diagnostics(store, state: Mapping, case: c.Case, inputs: dict,
                            expose) -> dict:
    """WP-B4: ``diag.final_test``, once the final test is opened: the predictions of its one
    evaluation and the final-test rows (``final_evaluation``, partition ``final_test``)."""
    from . import diagnostics, state as st
    task = st.task_of(state)
    rid = state['current'][FINAL]
    entry = registry.get(store, rid)
    values = entry['output']['values']
    part = partition.of(state)
    inputs['results'] = {FINAL: rid}
    inputs['target'] = _target(case)
    inputs['final_test'] = {'row_keys': part['final_test']['row_keys'],
                            'n_rows': part['final_test']['n_rows']}
    features = list(entry['inputs']['model_inputs'].get('features') or [])
    params: dict[str, Any] = {'model': values['model'], 'evaluation': 'final_test',
                              'segments': diagnostics.segment_columns(case, features)}
    if task == st.BINARY:
        params['rule'] = values.get('rule_final')
    else:
        params['residual_columns'] = diagnostics.residual_columns(case, features)
    final = rec.parse_row_keys(store.read_blob(part['final_test']['row_keys']))
    expose(diagnostics.FINAL_PURPOSE, partition.FINAL_TEST, final,
           features + [case.target_column])
    return params


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


def _rows_partition(inputs: Mapping) -> str:
    """``development`` when the study has a sealed final test, else ``all``."""
    return partition.DEVELOPMENT if inputs.get('development') else 'all'


def load(plan_: Mapping, store):
    """Case and dataset of a plan, with the case and dataset bytes verified against the
    digests the plan was derived from (the case file is read again here, review fix L1).

    The dataset holds the study's development rows only (ADR 0006,
    :func:`mlkit.study.data.load_development`): the sealed final test never reaches an
    activity."""
    from . import data as dt
    path = plan_['case_path']
    if os.path.isdir(path):
        path = os.path.join(path, c.CASE_FILE)
    expected = plan_['inputs'].get('case_sha256')
    actual = c.sha256_file(path) if os.path.isfile(path) else None
    if expected is not None and actual != expected \
            and (expected, actual) not in c.EQUIVALENT_CASE_FILES:     # v0.3 (WP-J)
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
    keys = partition.development_keys(store.read_blob, plan_['inputs'].get('development'))
    return case, dt.load_development(case, keys)


def compute_split(store, plan_: Mapping) -> dict:
    import numpy as np
    from mlkit import classical

    case, dataset = load(plan_, store)
    decision = plan_['inputs']['decision']
    from . import state as st
    if decision['method'] in st.CV_METHODS:
        return compute_cv_split(store, plan_, case, dataset)
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
    keys = np.asarray(frame.index)
    if plan_['inputs'].get('duplicates'):
        parts = _grouped_parts(dataset, [str(v) for v in y], decision)
        train = np.flatnonzero(frame.index.isin(parts['train']))
        validation = np.flatnonzero(frame.index.isin(parts['validation']))
    else:
        try:
            train, validation = classical.split(frame, y, spec)
        except ValueError as exc:
            raise _split_refusal(exc) from exc
        parts = {'train': sorted(keys[train], key=_line),
                 'validation': sorted(keys[validation], key=_line)}
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
    if plan_['inputs'].get('duplicates'):
        values['implementation'] = GROUPED_SPLIT_IMPLEMENTATION
        values['duplicates'] = _duplicates_across(dataset, parts)
    previous = plan_['inputs'].get('results', {}).get('previous_split')
    if previous:
        values['overlap'] = _overlap(store, previous,
                                     plan_['inputs'].get('previous_split_stale_since'), parts)
    return {'values': values, 'blobs': blobs, 'partition': _rows_partition(plan_['inputs']),
            'n_rows': len(frame)}


GROUPED_SPLIT_IMPLEMENTATION = ('mlkit.study.partition.grouped_stratified (whole groups of '
                                'identical records, per-stratum permutation from '
                                'numpy.random.default_rng(seed))')


def _grouped_parts(dataset, strata: list[str], decision: Mapping) -> dict[str, list[str]]:
    """Training and validation rows that never divide a group of identical records
    (``duplicates: {policy: group}``, v0.2b WP-B3): whole groups are drawn for validation,
    stratum by stratum, as the final test is (:func:`partition.grouped_stratified`)."""
    keys = list(dataset.frame.index)
    groups = dt.entity_groups(dataset.index)
    validation = set(partition.grouped_stratified(keys, strata, groups,
                                                  float(decision['validation_fraction']),
                                                  int(decision['seed'])))
    if not validation or len(validation) == len(keys):
        raise StudyError('invalid_value', 'The validation share leaves a partition empty.',
                         details={'validation_fraction': decision['validation_fraction']})
    return {'train': sorted((k for k in keys if k not in validation), key=_line),
            'validation': sorted(validation, key=_line)}


def _duplicates_across(dataset, parts: Mapping) -> dict:
    """``{policy, n_groups, n_rows, divided_groups}`` of the identical records of the
    development rows: ``divided_groups`` counts the groups with rows in more than one
    partition (the two of a split, or the folds of a cross-validation; 0 by construction
    under the ``group`` policy)."""
    groups = dt.entity_groups(dataset.index)
    side = {k: p for p, part_keys in parts.items() for k in part_keys}
    seen: dict[str, set] = {}
    for k, g in groups.items():
        seen.setdefault(g, set()).add(side.get(k))
    summary = dt.duplicate_summary(dataset.case, dataset.index)
    return {'policy': summary['policy'], 'n_groups': summary['n_groups'],
            'n_rows': summary['n_rows'],
            'divided_groups': sum(1 for sides in seen.values() if len(sides) > 1)}


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
        if plan_['inputs'].get('duplicates'):
            parts = _grouped_parts(dataset, ['all'] * len(frame), decision)
        else:
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
    if plan_['inputs'].get('duplicates'):
        if decision['method'] != 'ordinal_cutoff':
            values_out['implementation'] = GROUPED_SPLIT_IMPLEMENTATION
        values_out['duplicates'] = _duplicates_across(dataset, parts)
    values_out['overlap'] = None
    previous = plan_['inputs'].get('results', {}).get('previous_split')
    if previous:
        values_out['overlap'] = _overlap(store, previous,
                                         plan_['inputs'].get('previous_split_stale_since'), parts)
    blobs = {part: rec.row_keys_bytes(parts[part]) for part in SPLIT_BLOBS}
    return {'values': values_out, 'blobs': blobs, 'partition': _rows_partition(plan_['inputs']),
            'n_rows': len(frame)}


def compute_cv_split(store, plan_: Mapping, case: c.Case, dataset) -> dict:
    """WP-B1: assign every development row to one of ``folds`` folds.

    * ``kfold_stratified``: ``sklearn.model_selection.StratifiedKFold`` (shuffled with the
      seed) on the binary target, so each fold keeps the outcome share;
    * ``kfold_quantile``: the same on :data:`partition.QUANTILE_BINS` quantile bins of a
      numeric target;
    * ``temporal_folds``: contiguous blocks in time order (the time column, else the
      declared order; ties broken by file line), fold 1 the earliest. Each block is
      predicted by a model fitted on the other blocks, later ones included: it measures how
      the model holds across periods, not a forecast; the final test (temporal when the case
      declares an order) is the forward check.

    The ``train`` and ``validation`` blobs both hold every development row (the exploration
    reads them all, and every row is predicted once, out of fold); the ``folds`` blob is the
    assignment, ``row_key,fold`` per line in file order."""
    import numpy as np
    import pandas as pd

    decision = plan_['inputs']['decision']
    if decision['method'] in ('forward_chaining', 'ordered_retrospective',
                              'group_disjoint'):
        return compute_review_cv_split(plan_, case, dataset)
    method, k, seed = decision['method'], decision['folds'], decision['seed']
    frame = dataset.frame
    keys = sorted(frame.index, key=_line)
    frame = frame.loc[keys]
    n = len(keys)
    if n < 2 * k:
        raise StudyError('unsupported_capability', f'The folds cannot be made: {CAPABILITY_FOLDS}.',
                         details={'reasons': [{'code': 'unsupported_capability',
                                               'capability': CAPABILITY_FOLDS,
                                               'path': 'decisions.split', 'rows': n, 'folds': k,
                                               'reason': 'Each fold needs at least two rows.'}]})
    stratified_on, extra, order, strata = None, {}, None, None
    if method == 'temporal_folds':
        column = plan_['inputs'].get('order_column') or time_order_column(case)
        lines = np.array([_line(key) for key in keys])
        if column == 'line':
            order = np.argsort(lines, kind='mergesort')
        else:
            values = pd.to_numeric(frame[column], errors='coerce').to_numpy(dtype=float)
            if np.isnan(values).any():
                raise StudyError('invalid_value', f'The time column {column!r} must hold a number '
                                                  f'on every row to make temporal folds.',
                                 details={'column': column})
            order = np.lexsort((lines, values))
        extra['order_column'] = column
    elif method == 'kfold_stratified':
        strata = positive(frame, case).to_numpy()
        stratified_on = case.target_column
    else:
        from .eda import numeric_target
        y = numeric_target(case, frame)
        strata = pd.qcut(y, partition.QUANTILE_BINS, labels=False, duplicates='drop').to_numpy()
        stratified_on = case.target_column
        extra['bins'] = partition.QUANTILE_BINS
    # v0.2b (WP-B3): identical records (``duplicates: {policy: group}``) stay in one fold.
    grouped = bool(plan_['inputs'].get('duplicates'))
    entity = dt.entity_groups(dataset.index) if grouped else None
    groups = [entity[key] for key in keys] if grouped else None
    fold = assign_folds(n, k, seed=seed, strata=strata, order=order, groups=groups)
    if method == 'temporal_folds' and extra['order_column'] != 'line':
        values = pd.to_numeric(frame[extra['order_column']], errors='coerce').to_numpy(dtype=float)
        extra['fold_ranges'] = [{'fold': i, 'min': float(values[fold == i].min()),
                                 'max': float(values[fold == i].max())}
                                for i in range(1, k + 1)]
    lines_out = ['row_key,fold'] + [f'{key},{int(f)}' for key, f in zip(keys, fold)]
    blobs = {'train': rec.row_keys_bytes(keys), 'validation': rec.row_keys_bytes(keys),
             FOLDS_BLOB: ('\n'.join(lines_out) + '\n').encode('utf-8')}
    binary = case.task == 'binary'
    y = positive(frame, case).to_numpy() if binary else None
    fold_rows = []
    for i in range(1, k + 1):
        mask = fold == i
        item = {'fold': i, 'n_rows': int(mask.sum())}
        if binary:
            item.update(n_positive=int(y[mask].sum()), rate=float(y[mask].mean()))
        fold_rows.append(item)
    every = {'n_rows': n}
    if binary:
        every.update(n_positive=int(y.sum()), rate=float(y.mean()))
    implementation = ('mlkit.study.activities (contiguous blocks in time order)'
                      if method == 'temporal_folds' else
                      'sklearn.model_selection.StratifiedKFold (shuffled, seeded)')
    if grouped:
        implementation = (GROUPED_TEMPORAL_FOLDS_IMPLEMENTATION if method == 'temporal_folds'
                          else GROUPED_FOLDS_IMPLEMENTATION)
    values = {'method': method, 'folds': k,
              'seed': seed if method != 'temporal_folds' else None,
              'stratified_on': stratified_on, 'n_rows': n, 'scheme': 'cross_validation',
              'fold_rows': fold_rows, **extra,
              # Every development row is in the exploration and is predicted once out of fold.
              'partitions': {'train': dict(every), 'validation': dict(every)},
              'implementation': implementation, 'overlap': None,
              'note': 'Every development row is explored and predicted once, by a model fitted '
                      'on the other folds; out-of-fold figures are development evidence.'}
    group = plan_['inputs'].get('group_column')
    parts = {f'fold_{i}': [key for key, f in zip(keys, fold) if f == i] for i in range(1, k + 1)}
    values['groups'] = _fold_groups(frame, group, parts) if group else None
    if grouped:
        values['duplicates'] = _duplicates_across(dataset, parts)
    previous = plan_['inputs'].get('results', {}).get('previous_split')
    if previous:
        values['overlap'] = _overlap(store, previous,
                                     plan_['inputs'].get('previous_split_stale_since'), parts)
    return {'values': values, 'blobs': blobs, 'partition': _rows_partition(plan_['inputs']),
            'n_rows': n}


def compute_review_cv_split(plan_: Mapping, case: c.Case, dataset) -> dict:
    """J1 explicit memberships for the opt-in review-v1 methods."""
    import pandas as pd
    from . import evaluation_plan as ep
    decision, frame = plan_['inputs']['decision'], dataset.frame
    keys = sorted(frame.index, key=_line)
    contract = plan_['inputs']['analysis_contract']
    timing, dependencies = contract['timing'], contract['dependencies']

    def clock(spec):
        if not isinstance(spec, Mapping):
            return None
        if spec['by'] == 'line':
            return {key: _line(key) for key in keys}
        values = pd.to_numeric(frame.loc[keys, spec['by']], errors='coerce')
        if values.isna().any():
            raise StudyError('invalid_value', f'The clock {spec["by"]!r} must be numeric.',
                             details={'column': spec['by'], 'missing': int(values.isna().sum())})
        return dict(zip(keys, values.astype(float)))

    prediction = clock(timing.get('prediction_order'))
    outcome = clock(timing.get('outcome_available_order'))
    binary = case.task == 'binary'
    labels = dict(zip(keys, positive(frame.loc[keys], case).astype(int))) if binary else None
    if binary:
        strata = labels
    else:
        from .eda import numeric_target
        bins = pd.qcut(numeric_target(case, frame.loc[keys]), partition.QUANTILE_BINS,
                       labels=False, duplicates='drop')
        strata = dict(zip(keys, bins.astype(int)))
    groups = None
    group_column = dependencies.get('group_column')
    if group_column:
        groups = dict(zip(keys, frame.loc[keys, group_column].astype(str)))
    duplicates = None
    if plan_['inputs'].get('duplicates'):
        duplicates = dt.entity_groups(dataset.index)
    protocol = dict(decision)
    plan = ep.build(keys, protocol, prediction_order=prediction,
                    outcome_available_order=outcome, strata=strata, labels=labels,
                    groups=groups, duplicate_groups=duplicates,
                    assumptions=[f'scenario:{contract["scenario_id"]}'],
                    group_goal=dependencies.get('group_goal'))
    plan_digest = ep.digest(plan)
    assignment = {key: fold['id'] for fold in plan['folds']
                  for key in fold['validation_keys']}
    lines = ['row_key,fold'] + [f'{key},{assignment[key]}' for key in keys if key in assignment]
    plan_bytes = (json.dumps(plan, ensure_ascii=False, sort_keys=True,
                             separators=(',', ':')) + '\n').encode('utf-8')
    every = {'n_rows': len(keys)}
    if binary:
        every.update(n_positive=sum(labels.values()), rate=sum(labels.values()) / len(keys))
    fold_rows = []
    for fold in plan['folds']:
        val = fold['validation_keys']
        item = {'fold': fold['id'], 'n_rows': len(val),
                'n_train': len(fold['train_keys']),
                'n_purged': len(fold['excluded_train_keys']),
                'validation_start': fold['validation_start'],
                'validation_end': fold['validation_end']}
        if binary:
            item.update(n_positive=sum(labels[k] for k in val),
                        rate=sum(labels[k] for k in val) / len(val))
        fold_rows.append(item)
    purged = sum(len(fold['excluded_train_keys']) for fold in plan['folds'])
    scored_part = {'n_rows': len(assignment)}
    if binary:
        positives = sum(labels[key] for key in assignment)
        scored_part.update(n_positive=positives,
                           rate=positives / len(assignment) if assignment else None)
    values = {'method': decision['method'], 'folds': len(plan['folds']),
              'seed': decision.get('seed'), 'gap': decision.get('gap'),
              'stratified_on': case.target_column if decision['method'] == 'group_disjoint'
              else None, 'n_rows': len(keys), 'n_development': len(keys),
              'n_scored': len(assignment), 'n_warmup': len(plan['unscored_keys']),
              'n_purged': purged, 'scheme': 'cross_validation', 'fold_rows': fold_rows,
              'evaluation_plan': {'schema': ep.SCHEMA, 'digest': plan_digest,
                                  'blob': EVALUATION_PLAN_BLOB},
              'partitions': {'train': dict(every),
                             'validation': scored_part},
              'implementation': 'mlkit.study.evaluation_plan (explicit memberships)',
              'overlap': None,
              'note': ('Only validation-window rows are scored. Warm-up rows remain in '
                       'development provenance and are absent from metric denominators.')}
    blobs = {'train': rec.row_keys_bytes(keys),
             'validation': rec.row_keys_bytes([key for key in keys if key in assignment]),
             FOLDS_BLOB: ('\n'.join(lines) + '\n').encode('utf-8'),
             EVALUATION_PLAN_BLOB: plan_bytes}
    return {'values': values, 'blobs': blobs,
            'partition': _rows_partition(plan_['inputs']), 'n_rows': len(keys)}


GROUPED_FOLDS_IMPLEMENTATION = ('sklearn.model_selection.StratifiedGroupKFold (shuffled, '
                                'seeded; whole groups of identical records)')
GROUPED_TEMPORAL_FOLDS_IMPLEMENTATION = ('mlkit.study.activities (contiguous blocks in time '
                                         'order; a divided group of identical records moves '
                                         'to the fold of its earliest record)')


def assign_folds(n: int, k: int, *, seed=None, strata=None, order=None, groups=None):
    """The fold (1 to ``k``) of each of ``n`` rows: the one place folds are built (WP-B1).

    * ``order`` (row positions in time order): contiguous blocks, fold 1 the earliest;
      with ``groups``, every row of a group moves to the fold of its earliest row (as the
      temporal final test moves a divided group, :mod:`partition`);
    * else ``strata``: ``StratifiedKFold`` (shuffled with ``seed``), each fold keeping the
      share of every stratum; with ``groups`` (one value per row; rows of a group stay in
      one fold), ``StratifiedGroupKFold`` instead;
    * ``groups`` without strata: ``GroupKFold``.

    Refuses (``unsupported_capability``, :data:`CAPABILITY_FOLDS`) a stratum with fewer rows
    than folds."""
    import numpy as np
    import pandas as pd
    fold = np.zeros(n, dtype=int)
    if order is not None:
        for i, block in enumerate(np.array_split(np.asarray(order), k), start=1):
            fold[block] = i
        if groups is not None:
            first: dict = {}
            for position in np.asarray(order):
                first.setdefault(groups[position], fold[position])
            fold = np.array([first[g] for g in groups], dtype=int)
        return fold
    from sklearn import model_selection as ms
    if strata is not None:
        counts = pd.Series(strata).value_counts()
        if counts.min() < k:
            raise StudyError('unsupported_capability',
                             f'The folds cannot be made: {CAPABILITY_FOLDS}.',
                             details={'reasons': [{
                                 'code': 'unsupported_capability', 'capability': CAPABILITY_FOLDS,
                                 'path': 'decisions.split', 'folds': k,
                                 'smallest_stratum_rows': int(counts.min()),
                                 'reason': 'Each fold keeps every stratum, which needs at least '
                                           'as many rows of each stratum as folds.'}]})
        if groups is not None:
            splits = ms.StratifiedGroupKFold(n_splits=k, shuffle=True,
                                             random_state=seed).split(np.zeros(n), strata, groups)
        else:
            splits = ms.StratifiedKFold(n_splits=k, shuffle=True,
                                        random_state=seed).split(np.zeros(n), strata)
    else:
        splits = ms.GroupKFold(n_splits=k).split(np.zeros(n), groups=groups)
    for i, (_, test) in enumerate(splits, start=1):
        fold[test] = i
    return fold


def _fold_groups(frame, column: str, parts: Mapping) -> dict:
    """How many values of the group column fall in more than one fold (WP-B1): rows of one
    entity in two folds are predicted by a model that saw that entity."""
    seen: dict[str, set] = {}
    for part, keys in parts.items():
        for value in frame.loc[list(keys), column].astype(str):
            seen.setdefault(value, set()).add(part)
    shared = sorted(v for v, folds in seen.items() if len(folds) > 1)
    values = frame[column].astype(str)
    rows = int(values.isin(shared).sum())
    return {'column': column, 'n_groups': len(seen), 'groups_in_several_folds': len(shared),
            'rows_in_shared_groups': rows, 'examples': shared[:MAX_GROUP_EXAMPLES],
            'capability': c.CAPABILITY_GROUPED_SPLIT,
            'note': 'Grouped folds are not available in this version: a row whose group is in '
                    'another fold is predicted by a model that saw that group.'}


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
    if activity == QUALITY:
        from . import eda
        case, dataset = load(plan_, store)
        frame = dataset.frame[plan_['inputs']['columns']]     # never the target
        out = eda.compute(activity, case, frame, plan_['params'])
        if plan_['inputs'].get('duplicates'):
            # v0.2b (WP-B3): the groups of identical records (content hashes of the
            # development rows; no value is read).
            out['values']['duplicates']['records'] = dt.duplicate_summary(case, dataset.index)
        return out
    if activity == CORRELATION:
        from . import correlation
        case, dataset = load(plan_, store)
        columns = plan_['inputs']['columns']
        frame = dataset.frame[columns]                        # never the target
        return correlation.compute(case, frame, {**plan_['params'], 'columns': columns})
    if activity in EDA:
        from . import eda
        case, dataset = load(plan_, store)
        train = rows(dataset, split_keys(store, plan_['inputs']['results'][SPLIT])['train'])
        if activity == DISTRIBUTION:      # C8: the column only, never the outcome
            train = train[[plan_['params']['column']]]
        params = plan_['params']
        if split_scheme(store, plan_['inputs']['results'][SPLIT]) is not None:
            # WP-B6a: under cross-validation the "training" rows are every development row,
            # and the bins are said to be cut on them (not part of the identity).
            params = {**params, 'rows_word': 'development'}
        if activity == SIGNAL:
            params = {**params, 'candidates': plan_['inputs']['candidates'],
                      'availability': plan_['inputs']['availability'],
                      'special_values': plan_['inputs']['special_values']}
            if plan_['inputs'].get('duplicates'):
                groups = dt.entity_groups(dataset.index)
                params['groups'] = [groups[k] for k in train.index]
        return eda.compute(activity, case, train, params)
    if activity == CAPTURE:
        from mlkit.contracts import capture
        return capture.compute(store, plan_)
    if activity in MODEL_FITS:
        from . import fit
        case, dataset = load(plan_, store)
        split_rid = plan_['inputs']['results'][SPLIT]
        keys = split_keys(store, split_rid)
        folds = fold_assignment(store, split_rid)
        explicit = evaluation_membership(store, split_rid)
        if folds is not None:      # WP-B1/J1: out-of-sample predictions under the split plan
            return fit.compute_cv(activity, case, rows(dataset, keys['train']),
                                  explicit or folds,
                                  plan_['inputs'], plan_['params'])
        return fit.compute(activity, case, rows(dataset, keys['train']),
                           rows(dataset, keys['validation']), plan_['inputs'], plan_['params'])
    if activity == FINAL:
        return compute_final(store, plan_)
    if activity in DEVELOPMENT_DIAGNOSTICS:
        return compute_diagnostics(store, plan_)
    if activity == DIAG_FINAL:
        return compute_final_diagnostics(store, plan_)
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


def _residual_groups(column: str, values, y, preds: Mapping, unit: str | None = None,
                     rows_word: str = 'validation') -> dict:
    """Residuals by value of ``column`` on the evaluated rows (validation rows, or the
    out-of-fold development rows under cross-validation; training-free bins). WP-A9: a
    numeric column is cut into quantile bins labelled by their smallest and largest values
    ("70 to 75"), and ``binning`` says how many bins were made and on which rows."""
    import pandas as pd
    from . import eda, regression
    labels = values.astype(str).to_numpy()
    distinct = sorted(set(values.dropna().tolist()), key=lambda v: (str(type(v)), v))
    binned = len(distinct) > eda.MAX_DISTINCT_BEFORE_BINNING
    if binned:
        bin_labels, order = eda._bins(values, pd.Series(False, index=values.index), unit)
        labels = bin_labels.reindex(values.index).astype(str).to_numpy()
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
            'binning': eda.binning_words(len(order), rows_word) if binned else None,
            'groups': groups, 'min_group_rows': eda.MIN_GROUP_ROWS}


def compute_regression_evaluation(store, plan_: Mapping) -> dict:
    """MAE, RMSE, and residuals of both regression fits on the validation rows, with
    paired bootstrap intervals of each and of the candidate's difference with the
    baseline. The predictions are read back from the fits; nothing is refitted."""
    from . import regression

    results = plan_['inputs']['results']
    models = list(plan_['params'].get('models') or REGRESSION_FITS)
    preds = {slot: read_predictions(store, results[slot]) for slot in models}
    first = preds[models[0]]
    for slot in models[1:]:
        if preds[slot]['row_keys'] != first['row_keys'] or \
                not (preds[slot]['y'] == first['y']).all():
            raise StudyError('integrity_error', 'The fits were not scored on the same validation '
                                                'rows; their errors cannot be compared.',
                             details={'results': {s: results[s] for s in models}})
    y = first['y']
    predictions = {slot: preds[slot]['prediction'] for slot in models}
    boot = plan_['inputs'].get('bootstrap')
    pairs = variant_pairs(models, LINEAR)
    paired = regression.paired_bootstrap(y, predictions, int(boot['replicates']),
                                         int(boot['seed']), level=float(boot['level']),
                                         reference=plan_['params']['reference'], pairs=pairs)
    case, dataset = load(plan_, store)
    frame = rows(dataset, first['row_keys'])
    rows_word = ('out-of-fold' if plan_['params'].get('evaluation') == 'out_of_fold'
                 else 'validation')
    by = [_residual_groups(column, frame[column], y, predictions,
                           (case.variables.get(column) or {}).get('unit'), rows_word)
          for column in plan_['inputs']['residual_columns']]

    values = {'n': len(y), 'target': case.target_column, 'unit': case.target_unit,
              'models': paired['models'], 'intervals': paired['intervals'],
              'deltas': paired['deltas'],
              'residuals': {slot: regression.residual_summary(y, p)
                            for slot, p in predictions.items()},
              'residuals_by': by,
              'predictions': {slot: results[slot] for slot in models},
              'reference': plan_['params']['reference'],
              'candidate': plan_['params']['candidate'],
              'bootstrap': {'replicates': int(boot['replicates']), 'seed': int(boot['seed']),
                            'level': float(boot['level']), 'method': paired['method']},
              'residual_definition': regression.RESIDUAL_DEFINITION,
              'note': 'The model is chosen on these validation rows: these errors are not '
                      'independent evidence of future error. No model was refitted.'}
    criterion_value = plan_['inputs'].get('success_criterion')
    if isinstance(criterion_value, Mapping):
        from . import objective
        assignment = fold_assignment(store, results[SPLIT]) or {}
        windows = [assignment.get(key, 1) for key in first['row_keys']]
        values['objective'] = {slot: objective.evaluate_regression(y, prediction,
                                                                   windows=windows)
                               for slot, prediction in predictions.items()}
    out_of_fold = plan_['params'].get('evaluation') == 'out_of_fold'
    selection = _selection_values(store, plan_, models, 'regression', values.get('objective'))
    if selection is not None:
        values['model_selection'] = selection      # v0.3 (WP-F1, additive)
    if pairs or out_of_fold:
        # WP-B1 (additive): the variant against the candidate, and the evaluation scheme.
        values['comparisons'] = paired['comparisons']
        values['evaluation'] = 'out_of_fold' if out_of_fold else 'validation'
        if out_of_fold:
            values['note'] = ('The model is chosen on these out-of-fold predictions of the '
                              'development rows: these errors are development evidence, not '
                              'independent evidence of future error. No model was refitted.')
    return {'values': values, 'blobs': {},
            'partition': partition.DEVELOPMENT if out_of_fold else 'validation',
            'n_rows': len(y)}


CANDIDATE_GAIN_MODEL = 'fit.logistic'
# B6c (H3): under cross-validation, each fold's out-of-fold scores come from a different
# model (fitted without that fold), so their scales differ; a capacity or a share selects
# the best rows of each fold by that fold's model, and the counts are summed.
WITHIN_FOLD = 'within_fold'
WITHIN_FOLD_NOTE = ('Under cross-validation each fold is scored by a model fitted on the other '
                    'folds, so scores of different folds are not on the same scale (with '
                    'temporal folds, each period is scored by a model of other periods). A '
                    'capacity or a share is therefore applied within each fold: the best-scored '
                    'share of each fold\'s rows, by that fold\'s model, and the counts are '
                    'summed; by_fold gives each fold\'s precision. A threshold reads the scores '
                    'as they are.')


def policy_groups(store, plan_: Mapping, row_keys: list[str]):
    """The fold of each scored row (B6c, H3), or None when the evaluation pools the rows."""
    if plan_['params'].get('selection') != WITHIN_FOLD:
        return None
    import numpy as np
    assignment = fold_assignment(store, plan_['inputs']['fold_split'])
    if assignment is None or any(k not in assignment for k in row_keys):
        raise StudyError('integrity_error', 'The folds of the split do not cover the scored '
                                            'rows; the rules cannot be applied within folds.')
    return np.asarray([assignment[k] for k in row_keys])


def compute_policy(store, plan_: Mapping) -> dict:

    from . import policy

    fits = plan_['inputs']['results']
    models = list(plan_['params'].get('models') or FITS)
    preds = {slot: read_predictions(store, fits[slot]) for slot in models}
    first = preds[models[0]]
    for slot in models[1:]:
        if preds[slot]['row_keys'] != first['row_keys'] or \
                not (preds[slot]['y'] == first['y']).all():
            raise StudyError('integrity_error', 'The fits were not scored on the same validation '
                                                'rows; their policies cannot be compared.',
                             details={'results': dict(fits)})
    boot = plan_['inputs'].get('bootstrap')
    y = first['y']
    out_of_fold = plan_['params'].get('evaluation') == 'out_of_fold'
    pairs = variant_pairs(models, LOGISTIC)
    groups = policy_groups(store, plan_, first['row_keys'])
    out = {}
    for rule in plan_['params']['rules']:
        points = {slot: policy.evaluate(y, preds[slot]['score'], rule, groups)
                  for slot in models}
        paired = None
        if boot is not None:
            paired = policy.paired_bootstrap(
                y, {s: preds[s]['score'] for s in models}, rule,
                int(boot['replicates']), int(boot['seed']), level=float(boot['level']),
                reference=plan_['params']['reference'], pairs=pairs, groups=groups)
        out[rule] = {'models': points}
        if paired is not None:
            out[rule].update(intervals=paired['intervals'], deltas=paired['deltas'])
        if paired is not None and (pairs or out_of_fold):
            # WP-B1 (additive): the variant against the candidate; a capacity as a share of
            # the rows it was chosen on.
            out[rule]['comparisons'] = paired['comparisons']
            out[rule]['capacity_share'] = rec.capacity_share(rule, len(y))
    values = {'rules': out, 'n': len(y), 'n_positive': int(y.sum()),
              'predictions': dict(fits), 'reference': plan_['params']['reference'],
              'population_digest': rec.sha256_hex(rec.canonical(first['row_keys'])),
              'mode': ('inspection' if plan_['activity'] == POLICY_INSPECT
                       else 'evaluation'),
              # v0.2b (WP-B3, R6): the top 5, 10 and 20 % of the scored rows.
              'gain_points': {'model': CANDIDATE_GAIN_MODEL,
                              **policy.gain_points(y, preds[CANDIDATE_GAIN_MODEL]['score'],
                                                   groups=groups)},
              'counts': 'expected counts when a capacity cut splits a tie group (tied_at_cut)',
              'note': 'The rule is chosen on validation rows: these figures are not independent '
                      'evidence of future performance. No model was refitted.'}
    if boot is not None:
        values['bootstrap'] = {
            'replicates': int(boot['replicates']), 'seed': int(boot['seed']),
            'level': float(boot['level']),
            'method': 'paired percentile bootstrap over validation rows'}
    criterion_value = plan_['inputs'].get('success_criterion')
    if isinstance(criterion_value, Mapping):
        from . import objective
        selection_spec = criterion_value['selection']
        windows = groups.tolist() if groups is not None else [1] * len(y)
        batches = None
        if selection_spec['scope'] == 'column_batch':
            case, dataset = load(plan_, store)
            batches = rows(dataset, first['row_keys'])[selection_spec['batch_column']].tolist()
        values['objective'] = {
            slot: objective.evaluate_binary(
                y, preds[slot]['score'], metric=selection_spec['metric'],
                rule=selection_spec['rule'], windows=windows, batches=batches,
                scope=selection_spec['scope']) for slot in models}
        split_method = None
        split_rid = plan_['inputs'].get('fold_split')
        if split_rid:
            split_method = registry.get(store, split_rid)['output']['values'].get('method')
        inferential = split_method in ('kfold_stratified', 'kfold_quantile', None) \
            and not out_of_fold
        values['uncertainty'] = {
            'method': 'paired_row_bootstrap' if inferential else 'descriptive_only',
            'level': float(boot['level']) if boot is not None else None,
            'resampling_unit': 'row',
            'target_quantity': selection_spec['metric'],
            'conditioning': 'fixed selected configuration',
            'dependence_assumptions': 'independent held-out observations',
            'eligible': inferential,
            'reason': None if inferential else
            'adaptive OOF or group/temporal dependence has no supported inferential interval'}
    if pairs or out_of_fold:
        from . import metrics
        values['evaluation'] = 'out_of_fold' if out_of_fold else 'validation'
        values['ranking'] = {slot: {'roc_auc': metrics.roc_auc(y, preds[slot]['score']),
                                    'average_precision': metrics.average_precision(
                                        y, preds[slot]['score'])} for slot in models}
        if out_of_fold and boot is not None:
            values['bootstrap']['method'] = ('paired percentile bootstrap over the out-of-fold '
                                             'predictions of the development rows')
            values['note'] = ('The rule and the model are chosen on out-of-fold predictions of '
                              'the development rows: these figures are development evidence, '
                              'not independent evidence of future performance. No model was '
                              'refitted.')
        if groups is not None and boot is not None:
            values['bootstrap']['method'] = ('paired percentile bootstrap over the out-of-fold '
                                             'predictions, rows resampled within each fold')
            values['selection'] = {'scope': WITHIN_FOLD, 'folds': int(len(set(groups.tolist()))),
                                   'note': WITHIN_FOLD_NOTE}
        if VARIANT in models:
            # B6c (M4): the top shares for the variant too, so a policy that applies its rule
            # to the variant can show its own gain points.
            values['gain_points_variant'] = {'model': VARIANT, **policy.gain_points(
                y, preds[VARIANT]['score'], groups=groups)}
        extra = [m for m in models if trials.is_variant_slot(m) and m != VARIANT]
        if extra:
            # v0.3 (WP-F1, additive): the same for the second and third variants.
            values['gain_points_variants'] = {m: {'model': m, **policy.gain_points(
                y, preds[m]['score'], groups=groups)} for m in extra}
    selection = _selection_values(store, plan_, models, 'binary', values.get('objective'))
    if selection is not None:
        values['model_selection'] = selection      # v0.3 (WP-F1, additive)
    return {'values': values, 'blobs': {},
            'partition': partition.DEVELOPMENT if out_of_fold else 'validation',
            'n_rows': len(y)}


# --- WP-B1: the one evaluation of the final test -----------------------------------------

def compute_final(store, plan_: Mapping) -> dict:
    """Refit the chosen configuration (and the baseline) on every development row, score the
    final-test rows once, and evaluate: the adopted rule (a capacity keeps its share of the
    rows) or the errors, with paired bootstrap intervals against the baseline, and the
    success criterion on the final test. The final-test rows are read here only, through
    :func:`mlkit.study.data.load_final_test`."""
    from . import data as dt
    from . import fit
    inputs, params = plan_['inputs'], plan_['params']
    case, development = load(plan_, store)
    final_keys = rec.parse_row_keys(store.read_blob(inputs['final_test']['row_keys']))
    if len(final_keys) != inputs['final_test']['n_rows']:
        raise StudyError('integrity_error', 'The final-test rows blob does not hold the '
                                            'recorded number of rows.')
    predictor = None
    if inputs.get('predictor'):
        # Library integration v1: the reloaded capture is verified (digests, environment,
        # its own parity rows) before any final-test row is read.
        from mlkit.contracts import capture
        predictor = capture.load_for_final(store, inputs['predictor'])
    final = dt.load_final_test(case, final_keys)
    return fit.final_evaluation(case, development.frame, final.frame, inputs, params,
                                predictor=predictor)


# --- WP-B4: diagnostics -------------------------------------------------------------------

def _model_inputs(entry: Mapping) -> dict:
    keep = ('features', 'special_values', 'preprocessing')
    return {k: entry['inputs'][k] for k in keep if k in entry['inputs']}


def _regression_extras(case: c.Case, params: Mapping) -> dict:
    from . import diagnostics as dg
    return {'target': case.target_column, 'unit': case.target_unit,
            'residual_columns': list(params['residual_columns']),
            'residual_definition': 'residual = observed minus predicted',
            'target_transform': None,
            'smearing': {'applies': False, 'implemented': False, 'note': dg.SMEARING_NOTE},
            'normality_note': dg.NORMALITY_NOTE}


def compute_diagnostics(store, plan_: Mapping) -> dict:
    """The development diagnostics of the candidate and the variant (WP-B4): read their
    stored predictions back, and the rows those predictions describe; refit only for the
    intervals of the coefficients (one refit, WP-J)."""
    from . import diagnostics as dg
    inputs, params = plan_['inputs'], plan_['params']
    case, dataset = load(plan_, store)
    results = inputs['results']
    models = list(params['models'])
    binary = case.task != 'regression'
    preds = {m: read_predictions(store, results[m]) for m in models}
    first = preds[models[0]]
    for m in models[1:]:
        if preds[m]['row_keys'] != first['row_keys'] or not (preds[m]['y'] == first['y']).all():
            raise StudyError('integrity_error', 'The fits were not scored on the same rows; '
                                                'their diagnostics cannot be compared.',
                             details={'results': {m: results[m] for m in models}})
    keys = first['row_keys']
    y = first['y']
    frame = rows(dataset, keys)
    fitted_rows = rows(dataset, split_keys(store, results[SPLIT])['train'])
    boot = params['coefficients']
    groups = None
    if binary and params['evaluation'] == 'out_of_fold':
        # B6c (H3): the rule is applied within each fold, as the policy evaluation applies it.
        assignment = fold_assignment(store, results[SPLIT]) or {}
        if all(k in assignment for k in keys):
            import numpy as np
            groups = np.asarray([assignment[k] for k in keys])
    out_models = {}
    for m in models:
        entry = registry.get(store, results[m])
        features = list(entry['inputs'].get('features') or [])
        if binary:
            diag = dg.binary_model(y, preds[m]['score'], params['rule'], frame, keys,
                                   params['segments'], features, groups)
        else:
            diag = dg.regression_model(y, preds[m]['prediction'], frame, keys, case, features)
        fitted = entry['output']['values']
        if entry['params'].get('family'):
            # v0.3 (WP-F1): a model of another family has no coefficients; its own
            # diagnostics (the EBM's shape functions, the boosting model's permutation
            # importance) are part of its fit result and are shown here.
            diag['coefficients'] = None
            diag['family_diagnostics'] = fitted.get('family_diagnostics')
        else:
            fit_params = dict(entry['params'])
            development = (fitted.get('tuning') or {}).get('development') or {}
            if fit_params.get('tuning') and development.get('value') is not None:
                # WP-F1: the penalty the fit chose on these rows, not a new inner search.
                fit_params['tuned_value'] = development['value']
            diag['coefficients'] = dg.coefficient_intervals(
                case, fitted_rows, _model_inputs(entry), fit_params, binary,
                fitted.get('coefficients') or {}, level=float(boot['level']),
                intercept=fitted.get('intercept'))
            diag['coefficients']['scale'] = fitted.get('coefficient_scale')
        if fitted.get('tuning'):
            diag['tuning'] = fitted['tuning']
        diag['predictions'] = results[m]
        out_models[m] = diag
    cv = params['evaluation'] == 'out_of_fold'
    values = {'question': dg.QUESTIONS[plan_['activity']], 'evidence': 'development',
              'purpose': dg.DEVELOPMENT_PURPOSE,
              'partition': partition.DEVELOPMENT if cv else 'validation',
              'evaluation': params['evaluation'], 'n': len(y)}
    if binary:
        values.update(n_positive=int(y.sum()), base_rate=float(y.mean()) if len(y) else None,
                      rule=params['rule'], rule_source=params['rule_source'],
                      segment_columns=list(params['segments']), segment_rule=dg.SEGMENT_RULE)
    else:
        values.update(_regression_extras(case, params))
    values['models'] = out_models
    values['coefficient_rows'] = int(len(fitted_rows))
    values['note'] = dg.DEVELOPMENT_NOTE if cv else dg.VALIDATION_NOTE
    candidate = models[0] if models and models[0] in CANDIDATE_FITS else None
    if candidate is not None:
        # v0.3 (WP-F1): what the candidate linear model cannot follow, the evidence the
        # shortlist of model families reads.
        features = list(registry.get(store, results[candidate])['inputs'].get('features')
                        or [])
        values['linear_checks'] = dg.linear_checks(
            y, preds[candidate]['score' if binary else 'prediction'], frame, case, features,
            binary, candidate)
    return {'values': values, 'blobs': {},
            'partition': partition.DEVELOPMENT if cv else 'validation', 'n_rows': len(y)}


def compute_final_diagnostics(store, plan_: Mapping) -> dict:
    """The diagnostics of the chosen configuration on the final test (WP-B4), from the
    predictions of its one evaluation; the final-test rows are read again (after the
    opening only) for the segments, the examples and the residuals by feature."""
    from . import data as dt
    from . import diagnostics as dg
    inputs, params = plan_['inputs'], plan_['params']
    case, _ = load(plan_, store)
    rid = inputs['results'][FINAL]
    entry = registry.get(store, rid)
    preds = read_predictions(store, rid)
    final_keys = rec.parse_row_keys(store.read_blob(inputs['final_test']['row_keys']))
    if sorted(final_keys) != sorted(preds['row_keys']):
        raise StudyError('integrity_error', 'The final evaluation did not score the recorded '
                                            'final-test rows.', details={'result_id': rid})
    final = dt.load_final_test(case, final_keys)
    keys = preds['row_keys']
    frame = rows(final, keys)
    y = preds['y']
    model = params['model']
    features = list(entry['inputs']['model_inputs'].get('features') or [])
    binary = case.task != 'regression'
    if binary:
        diag = dg.binary_model(y, preds['score'], params['rule'], frame, keys,
                               params['segments'], features)
    else:
        diag = dg.regression_model(y, preds['prediction'], frame, keys, case, features)
    diag['predictions'] = rid
    values = {'question': dg.QUESTIONS['final_binary' if binary else 'final_regression'],
              'evidence': 'final', 'purpose': dg.FINAL_PURPOSE,
              'partition': partition.FINAL_TEST, 'evaluation': 'final_test', 'n': len(y),
              'model': model, 'final_evaluation': rid}
    if binary:
        values.update(n_positive=int(y.sum()), base_rate=float(y.mean()) if len(y) else None,
                      rule=params['rule'], segment_columns=list(params['segments']),
                      segment_rule=dg.SEGMENT_RULE)
    else:
        values.update(_regression_extras(case, params))
    values['models'] = {model: diag}
    values['note'] = dg.FINAL_NOTE
    return {'values': values, 'blobs': {}, 'partition': partition.FINAL_TEST, 'n_rows': len(y)}
