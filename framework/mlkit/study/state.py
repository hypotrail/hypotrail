"""Study state ``hypotrail.study/1``: schema, validation, integrity, and derived views.

``.hypotrail/state.json`` is the single source of truth for decisions. It is written
only by :class:`mlkit.study.store.StudyStore` through
:func:`mlkit.reliability.apply_command`. Plan §3.1 and §3.2 define its content:

* ``facts``: what the case states, with an epistemic status. A fact is never
  "confirmed": confirmation is a human act and belongs to decisions.
* ``decisions``: the five study decisions. A decision moves
  ``open -> proposed -> confirmed -> reconfirm_required | superseded``. A confirmed
  decision carries a ``confirmation`` with the user's verbatim words.
* ``proposals``: first-class proposals the agent made, each with a restatement the
  user answers. A future webview "Confirm" button confirms a proposal by id.
* ``current``, ``stale``, ``executions``, ``invalidations``: result bookkeeping that
  later activities fill in.
* ``receipts``: idempotency receipts of :func:`mlkit.reliability.apply_command`.

This module is pure: it reads and writes no file, and imports neither pandas, numpy,
nor scikit-learn, so ``status`` and ``plan`` stay fast.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
from typing import Any, Mapping

from .case import EPISTEMIC_STATUSES, Case, require_supported
from .errors import StudyError

SCHEMA = 'hypotrail.study/1'
STATE_FILE = 'state.json'
SHA_FILE = 'state.sha256'

# The decisions of a binary study (frozen by the contract). A regression study has the same
# pauses, but its third decision is ``model_choice`` (adopt the candidate model or keep the
# mean baseline): a decision rule on scores has no meaning for a numeric target.
# :func:`decision_ids` gives the decisions of a study's task.
DECISION_IDS = ('prediction_time', 'feature_availability', 'split', 'policy', 'conclusion')
REGRESSION_DECISION_IDS = ('prediction_time', 'feature_availability', 'split', 'model_choice',
                           'conclusion')
BINARY, REGRESSION = 'binary', 'regression'
TASKS = (BINARY, REGRESSION)
DEFAULT_TASK = BINARY
DECISION_IDS_BY_TASK = {BINARY: DECISION_IDS, REGRESSION: REGRESSION_DECISION_IDS}
ALL_DECISION_IDS = tuple(dict.fromkeys(DECISION_IDS + REGRESSION_DECISION_IDS))
# The decision of the third pause, per task (the choice made on validation results).
CHOICE_DECISION = {BINARY: 'policy', REGRESSION: 'model_choice'}
DECISION_STATUSES = ('open', 'proposed', 'confirmed', 'reconfirm_required', 'superseded')
PROPOSAL_STATUSES = ('open', 'confirmed', 'withdrawn', 'superseded')
AVAILABILITY_DECISIONS = ('available_at_prediction', 'not_available', 'uncertain_excluded',
                          'uncertain_included')
CHANNELS = ('chat', 'cli', 'webview')
CONFIRMATION_KEYS = ('user_words', 'proposal_id', 'restatement', 'authenticated', 'channel',
                     'actor', 'revision', 'time')
# How the user decided (D1). ``explicit``: their own reply to the restatement.
# ``delegated_default``: they explicitly delegated to the assistant's recommended default,
# which the restatement stated. Optional in the record: a confirmation without it (written
# before the basis existed) is explicit.
EXPLICIT, DELEGATED_DEFAULT = 'explicit', 'delegated_default'
CONFIRMATION_BASES = (EXPLICIT, DELEGATED_DEFAULT)
DEFAULT_BASIS = EXPLICIT
# The scope of a delegation (R1). ``this_decision``: the junior delegated at this very
# pause. ``standing``: an earlier delegation that covers every question the junior cannot
# answer ("for questions I can't answer, use your recommended default"). A standing
# delegation covers only STANDING_DELEGATION_DECISIONS; the policy and the conclusion need
# the junior's own words or a delegation given at that pause (``this_decision``).
THIS_DECISION, STANDING = 'this_decision', 'standing'
DELEGATION_SCOPES = (THIS_DECISION, STANDING)
STANDING_DELEGATION_DECISIONS = ('prediction_time', 'feature_availability', 'split')
CONFIRMATION_OPTIONAL_KEYS = ('basis', 'delegation_scope')

# Which confirmed decisions a decision rests on. Changing one of them makes the
# dependants need reconfirmation (plan §3.7, rows 1, 2, 4, and 5).
DEPENDS_ON = {
    'prediction_time': (),
    'feature_availability': ('prediction_time',),
    'split': (),
    'policy': ('prediction_time', 'feature_availability', 'split'),
    'conclusion': ('prediction_time', 'feature_availability', 'split', 'policy'),
}
REGRESSION_DEPENDS_ON = {
    'prediction_time': (),
    'feature_availability': ('prediction_time',),
    'split': (),
    'model_choice': ('prediction_time', 'feature_availability', 'split'),
    'conclusion': ('prediction_time', 'feature_availability', 'split', 'model_choice'),
}
DEPENDS_ON_BY_TASK = {BINARY: DEPENDS_ON, REGRESSION: REGRESSION_DEPENDS_ON}

DEFAULT_SETTINGS = {'bootstrap': {'replicates': 2000, 'seed': 20261017, 'level': 0.95}}

# The plan (§4, three pauses). A step is done when its decision is confirmed and
# every listed result slot is current. With both, the decision comes first unless
# ``decide_first`` is False (a policy is confirmed only after it is evaluated).
STEPS = (
    {'id': 'prediction_time', 'pause': 1, 'decision': 'prediction_time', 'activities': (),
     'requires': (),
     'title': 'Define the prediction moment',
     'question': 'At what moment is the prediction made, and what is known at that moment?',
     'expected_output': 'A confirmed prediction time, restated and answered in your own words.',
     'completion': 'Decision prediction_time is confirmed.'},
    {'id': 'feature_availability', 'pause': 1, 'decision': 'feature_availability',
     'activities': (), 'requires': ('prediction_time',),
     'title': 'Decide which variables are available at prediction time',
     'question': 'Which variables are known at the prediction moment, and which must be '
                 'excluded?',
     'expected_output': 'A confirmed availability status for every candidate feature, with the '
                        'exclusions listed in your own words.',
     'completion': 'Decision feature_availability is confirmed.'},
    {'id': 'split', 'pause': 2, 'decision': 'split', 'activities': ('split',),
     'requires': ('prediction_time', 'feature_availability'),
     'title': 'Split the data before exploring it',
     'question': 'How are rows divided between training and validation, before any '
                 'exploration of the target?',
     'expected_output': 'A confirmed split decision and a recorded split result.',
     'completion': 'Decision split is confirmed and the split result is current.'},
    {'id': 'train_eda', 'pause': None, 'decision': None,
     'activities': ('eda.target_rate', 'eda.special_values'), 'requires': ('split',),
     'title': 'Explore the training partition',
     'question': 'What does the training partition show about the target and the special '
                 'values?',
     'expected_output': 'Target rate and special-value results on training rows, with their '
                        'exposure recorded.',
     'completion': 'The training EDA results are current.'},
    {'id': 'models', 'pause': None, 'decision': None,
     'activities': ('fit.baseline', 'fit.logistic'), 'requires': ('split',),
     'title': 'Fit a baseline and a logistic model',
     'question': 'How much does a simple model improve on a constant baseline on validation?',
     'expected_output': 'Persisted validation predictions for the baseline and the logistic '
                        'model.',
     'completion': 'Both fit results are current.'},
    {'id': 'policy', 'pause': 3, 'decision': 'policy', 'activities': ('policy.evaluation',),
     'requires': ('models',), 'decide_first': False,
     'title': 'Choose a decision policy',
     'question': 'Which rule turns scores into actions (a threshold or a capacity), and what '
                 'does it cost and gain?',
     'expected_output': 'A current policy evaluation and a confirmed policy adoption.',
     'completion': 'The policy evaluation is current and decision policy is confirmed.'},
    {'id': 'conclusion', 'pause': 3, 'decision': 'conclusion', 'activities': (),
     'requires': ('models',),
     'title': 'Conclude proportionately',
     'question': 'What can be said, for which use, and with which limits? Keeping the '
                 'baseline is a valid result.',
     'expected_output': 'A confirmed conclusion that names its limits.',
     'completion': 'Decision conclusion is confirmed.'},
)
STEP_IDS = tuple(s['id'] for s in STEPS)
ACTIVITY_SLOTS = tuple(a for s in STEPS for a in s['activities'])

# The plan of a regression study: the same pauses, a numeric target. The training EDA
# summarises the target distribution, the models are the training mean and a linear
# model, and the third pause chooses a model on the validation error (MAE and RMSE in the
# target unit, with paired bootstrap intervals), not a decision rule on scores.
REGRESSION_STEPS = (
    STEPS[0], STEPS[1], STEPS[2],
    {'id': 'train_eda', 'pause': None, 'decision': None,
     'activities': ('eda.target_summary', 'eda.special_values'), 'requires': ('split',),
     'title': 'Explore the training partition',
     'question': 'What does the training partition show about the distribution of the target '
                 'and the special values?',
     'expected_output': 'A target summary (count, mean, standard deviation, quantiles, missing '
                        'values) and special-value counts on training rows, with their exposure '
                        'recorded.',
     'completion': 'The training EDA results are current.'},
    {'id': 'models', 'pause': None, 'decision': None,
     'activities': ('fit.baseline', 'fit.linear'), 'requires': ('split',),
     'title': 'Fit a mean baseline and a linear model',
     'question': 'Which predictions do the training mean and a linear model give for the '
                 'validation rows?',
     'expected_output': 'Persisted validation predictions for the mean baseline and the linear '
                        'model.',
     'completion': 'Both fit results are current.'},
    {'id': 'model_choice', 'pause': 3, 'decision': 'model_choice',
     'activities': ('evaluate.regression',), 'requires': ('models',), 'decide_first': False,
     'title': 'Choose the model',
     'question': 'Does the linear model reduce the validation error of the mean baseline, in the '
                 'target unit, by enough to adopt it, given the paired intervals and the '
                 'residuals?',
     'expected_output': 'A current regression evaluation and a confirmed model choice.',
     'completion': 'The regression evaluation is current and decision model_choice is '
                   'confirmed.'},
    STEPS[6],
)
STEPS_BY_TASK = {BINARY: STEPS, REGRESSION: REGRESSION_STEPS}
REGRESSION_STEP_IDS = tuple(s['id'] for s in REGRESSION_STEPS)
REGRESSION_ACTIVITY_SLOTS = tuple(a for s in REGRESSION_STEPS for a in s['activities'])
ACTIVITY_SLOTS_BY_TASK = {BINARY: ACTIVITY_SLOTS, REGRESSION: REGRESSION_ACTIVITY_SLOTS}
# Optional slots outside the plan: ``eda.rate_by`` (binary) and ``eda.mean_by``
# (regression) have one slot per column, ``eda.rate_by:<column>``
# (``mlkit.study.activities.slot_of``). They are shown with the training EDA step and
# never block a step. ``eda.distribution:<column>`` (CLI-CONTRACT-COMPANION §8, C8) is a
# per-column activity of both tasks; WP-0 reserves its prefix, WP-E3 implements it.
PER_COLUMN_SLOT_PREFIXES = ('eda.rate_by:', 'eda.mean_by:', 'eda.distribution:')

TOP_KEYS = ('schema', 'revision', 'created', 'updated', 'case', 'dataset', 'facts',
            'structure', 'prior_exposure', 'decisions', 'proposals', 'current', 'stale',
            'executions', 'invalidations', 'receipts', 'settings')
# ``task`` (``binary`` or ``regression``) is written by every new study; a state written
# before it existed has no ``task`` and is a binary study. ``notes`` (post-v0.1, P2) holds
# the conditions the junior states at a pause; it appears with the first note.
TOP_OPTIONAL_KEYS = ('task', 'notes')
DECISION_KEYS = ('status', 'value', 'proposal_id', 'confirmation', 'depends_on', 'revision',
                 'reason')
PROPOSAL_KEYS = ('proposal_id', 'decision_id', 'value', 'restatement', 'rationale', 'revision',
                 'status', 'created')
# Written by ``hypotrail decide`` (WP1.4): the request that created the proposal, the
# confirmed values it was based on (a change makes it stale), and why it was closed.
# ``origin`` (CLI-CONTRACT-COMPANION §9, C9) is ``{channel}``, where the proposal came from;
# WP-0 reserves the key, WP-E1 writes and validates it.
PROPOSAL_OPTIONAL_KEYS = ('request_id', 'basis', 'closed_revision', 'closed_reason', 'origin')
EXECUTION_BUCKETS = ('active', 'interrupted', 'late')
# A junior's condition or hold on a decision (post-v0.1, P2): "don't adopt anything until I
# bring my manager's figure". Recorded verbatim by ``decide note --about``, it stays open
# until the junior's own words resolve it (``decide note --resolve``); while it is open the
# decision cannot be confirmed and ``not_yet_defensible`` lists it (``open_holds``). The
# junior may also withdraw it in their words (``decide note --withdraw``, D5): ``withdrawn``.
NOTE_KEYS = ('note_id', 'decision_id', 'kind', 'user_words', 'status', 'created', 'revision',
             'request_id', 'resolution')
NOTE_KINDS = ('hold',)
NOTE_STATUSES = ('open', 'resolved', 'withdrawn')
NOTE_RESOLUTION_KEYS = ('user_words', 'revision', 'time', 'request_id')


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


# --- task -------------------------------------------------------------------------------

def task_of(state: Mapping | str | None) -> str:
    """The task of a study state (``binary`` when the state predates the ``task`` key).
    A task name is returned as it is."""
    if isinstance(state, str):
        return state
    if isinstance(state, Mapping):
        return state.get('task', DEFAULT_TASK)
    return DEFAULT_TASK


def decision_ids(state: Mapping | str | None = None) -> tuple[str, ...]:
    """The decisions of a study (or of a task name)."""
    return DECISION_IDS_BY_TASK[task_of(state)]


def depends_on(state: Mapping | str | None, decision_id: str) -> tuple[str, ...]:
    return DEPENDS_ON_BY_TASK[task_of(state)][decision_id]


def steps(state: Mapping | str | None = None) -> tuple[dict, ...]:
    """The plan steps of a study's task."""
    return STEPS_BY_TASK[task_of(state)]


def activity_slots(state: Mapping | str | None = None) -> tuple[str, ...]:
    return ACTIVITY_SLOTS_BY_TASK[task_of(state)]


def choice_decision(state: Mapping | str | None = None) -> str:
    """The decision of the third pause: ``policy`` (binary) or ``model_choice``."""
    return CHOICE_DECISION[task_of(state)]


# --- construction -----------------------------------------------------------------------

def empty_decision(decision_id: str, task: str = DEFAULT_TASK) -> dict:
    return {'status': 'open', 'value': None, 'proposal_id': None, 'confirmation': None,
            'depends_on': list(depends_on(task, decision_id)), 'revision': None,
            'reason': None}


def initial_state(case: Case, *, created: str | None = None) -> dict:
    """The state of a new study on ``case``, before its first commit (revision 0).

    Refuses an unsupported case (``unsupported_capability``) without fallback. Facts
    and structure statements are copied from the case with their statuses; no
    decision is taken.
    """
    require_supported(case)
    doc = case.document
    stamp = created or now()
    task = case.task
    return {
        'schema': SCHEMA,
        'task': task,
        'revision': 0,
        'created': stamp,
        'updated': stamp,
        'case': {'id': doc['id'], 'path': str(case.path), 'sha256': _sha256_file(case.path)},
        'dataset': {'path': str(case.dataset_path), 'sha256': case.dataset['sha256'],
                    'rows': case.dataset['rows'],
                    'row_key': {'rule': doc['row_key']['rule'],
                                'format': doc['row_key']['format']}},
        'facts': {f['id']: {'value': f['value'], 'status': f['status'], 'source': f['source']}
                  for f in doc['facts']},
        'structure': copy.deepcopy(doc['structure']),
        'prior_exposure': copy.deepcopy(doc.get('prior_exposure', [])),
        'decisions': {d: empty_decision(d, task) for d in decision_ids(task)},
        'proposals': {},
        'current': {},
        'stale': {},
        'executions': {bucket: {} for bucket in EXECUTION_BUCKETS},
        'invalidations': [],
        'receipts': {},
        'settings': copy.deepcopy(DEFAULT_SETTINGS),
    }


def _sha256_file(path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def confirmation(*, user_words: str, proposal: dict, channel: str, actor: str, revision: int,
                 time: str | None = None, basis: str = DEFAULT_BASIS,
                 delegation_scope: str | None = None) -> dict:
    """The confirmation record of ``proposal`` (plan §3.2, §9 bis).

    ``user_words`` is the user's verbatim reply to the proposal's restatement.
    ``authenticated`` is always False: the engine cannot verify who typed the words.
    ``basis`` is ``explicit`` or ``delegated_default`` (:data:`CONFIRMATION_BASES`).
    ``delegation_scope`` is ``None`` for an explicit confirmation, else ``this_decision``,
    ``standing``, or ``None`` when the delegation did not state it (:data:`DELEGATION_SCOPES`).
    """
    record = {'user_words': user_words, 'proposal_id': proposal['proposal_id'],
              'restatement': proposal['restatement'], 'authenticated': False,
              'channel': channel, 'actor': actor, 'revision': revision, 'time': time or now(),
              'basis': basis, 'delegation_scope': delegation_scope}
    problems = _confirmation_problems(record, 'confirmation')
    if problems:
        raise StudyError('invalid_confirmation', 'The confirmation is incomplete.',
                         details={'problems': problems})
    return record


# --- validation -------------------------------------------------------------------------

def _keys(node: Any, path: str, keys, problems: list) -> bool:
    if not isinstance(node, dict):
        problems.append({'path': path, 'problem': 'must be a mapping'})
        return False
    for k in keys:
        if k not in node:
            problems.append({'path': f'{path}.{k}' if path else k, 'problem': 'is required'})
    for k in node:
        if k not in keys:
            problems.append({'path': f'{path}.{k}' if path else str(k),
                             'problem': 'is not part of the schema'})
    return all(k in node for k in keys)


def _text(node: Any) -> bool:
    return isinstance(node, str) and bool(node.strip())


def confirmation_basis(c: Any) -> str:
    """The basis of a confirmation record (``explicit`` when it predates the basis)."""
    return c.get('basis', DEFAULT_BASIS) if isinstance(c, dict) else DEFAULT_BASIS


def _confirmation_problems(c: Any, path: str) -> list[dict]:
    problems: list[dict] = []
    present = tuple(k for k in CONFIRMATION_OPTIONAL_KEYS if isinstance(c, dict) and k in c)
    if not _keys(c, path, CONFIRMATION_KEYS + present, problems):
        return problems
    if 'basis' in present and c['basis'] not in CONFIRMATION_BASES:
        problems.append({'path': f'{path}.basis',
                         'problem': f'must be one of {", ".join(CONFIRMATION_BASES)}'})
    if 'delegation_scope' in present and c['delegation_scope'] is not None:
        if c['delegation_scope'] not in DELEGATION_SCOPES:
            problems.append({'path': f'{path}.delegation_scope',
                             'problem': f'must be null or one of {", ".join(DELEGATION_SCOPES)}'})
        elif confirmation_basis(c) != DELEGATED_DEFAULT:
            problems.append({'path': f'{path}.delegation_scope',
                             'problem': 'must be null unless the basis is delegated_default'})
    for key in ('user_words', 'proposal_id', 'restatement', 'actor', 'time'):
        if not _text(c[key]):
            problems.append({'path': f'{path}.{key}', 'problem': 'must be a non-empty string'})
    if c['authenticated'] is not False:
        problems.append({'path': f'{path}.authenticated',
                         'problem': 'must be false: user words are not authenticated'})
    if c['channel'] not in CHANNELS:
        problems.append({'path': f'{path}.channel', 'problem': f'must be one of {", ".join(CHANNELS)}'})
    if type(c['revision']) is not int or c['revision'] < 0:
        problems.append({'path': f'{path}.revision', 'problem': 'must be a revision number'})
    return problems


def _decision_problems(decision_id: str, d: Any, proposals: dict,
                       task: str = DEFAULT_TASK) -> list[dict]:
    path = f'decisions.{decision_id}'
    problems: list[dict] = []
    if not _keys(d, path, DECISION_KEYS, problems):
        return problems
    if d['status'] not in DECISION_STATUSES:
        problems.append({'path': f'{path}.status',
                         'problem': f'must be one of {", ".join(DECISION_STATUSES)}'})
    expected = list(depends_on(task, decision_id))
    if d['depends_on'] != expected:
        problems.append({'path': f'{path}.depends_on', 'problem': f'must be {expected}'})
    if d['status'] == 'confirmed':
        problems += _confirmation_problems(d['confirmation'], f'{path}.confirmation')
        if isinstance(d['confirmation'], dict) and d['confirmation'].get('proposal_id') != d['proposal_id']:
            problems.append({'path': f'{path}.proposal_id',
                             'problem': 'must be the proposal named by the confirmation'})
    elif d['status'] == 'open' and (d['value'] is not None or d['confirmation'] is not None):
        problems.append({'path': path, 'problem': 'an open decision has no value or confirmation'})
    elif d['status'] in ('reconfirm_required', 'superseded') and not _text(d['reason']):
        problems.append({'path': f'{path}.reason', 'problem': 'must say why'})
    if d['proposal_id'] is not None and d['proposal_id'] not in proposals:
        problems.append({'path': f'{path}.proposal_id', 'problem': 'names no proposal'})
    if decision_id == 'feature_availability' and d['value'] is not None:
        if not isinstance(d['value'], dict) or not all(
                isinstance(k, str) and v in AVAILABILITY_DECISIONS for k, v in d['value'].items()):
            problems.append({'path': f'{path}.value',
                             'problem': 'must map each feature to one of '
                                        + ', '.join(AVAILABILITY_DECISIONS)})
    return problems


def _proposal_problems(pid: Any, p: Any, task: str = DEFAULT_TASK) -> list[dict]:
    path = f'proposals.{pid}'
    problems: list[dict] = []
    present = tuple(k for k in PROPOSAL_OPTIONAL_KEYS if isinstance(p, dict) and k in p)
    if not _keys(p, path, PROPOSAL_KEYS + present, problems):
        return problems
    if p['proposal_id'] != pid:
        problems.append({'path': f'{path}.proposal_id', 'problem': 'must equal its key'})
    if p['decision_id'] not in decision_ids(task):
        problems.append({'path': f'{path}.decision_id',
                         'problem': f'must be one of {", ".join(decision_ids(task))}'})
    if p['status'] not in PROPOSAL_STATUSES:
        problems.append({'path': f'{path}.status',
                         'problem': f'must be one of {", ".join(PROPOSAL_STATUSES)}'})
    for key in ('restatement', 'rationale', 'created'):
        if not _text(p[key]):
            problems.append({'path': f'{path}.{key}', 'problem': 'must be a non-empty string'})
    if type(p['revision']) is not int or p['revision'] < 0:
        problems.append({'path': f'{path}.revision', 'problem': 'must be a revision number'})
    return problems


def _notes_problems(notes: Any, task: str = DEFAULT_TASK) -> list[dict]:
    if not isinstance(notes, dict):
        return [{'path': 'notes', 'problem': 'must be a mapping'}]
    problems: list[dict] = []
    for nid, n in notes.items():
        path = f'notes.{nid}'
        if not _keys(n, path, NOTE_KEYS, problems):
            continue
        if n['note_id'] != nid:
            problems.append({'path': f'{path}.note_id', 'problem': 'must equal its key'})
        if n['decision_id'] not in decision_ids(task):
            problems.append({'path': f'{path}.decision_id',
                             'problem': f'must be one of {", ".join(decision_ids(task))}'})
        if n['kind'] not in NOTE_KINDS:
            problems.append({'path': f'{path}.kind',
                             'problem': f'must be one of {", ".join(NOTE_KINDS)}'})
        if n['status'] not in NOTE_STATUSES:
            problems.append({'path': f'{path}.status',
                             'problem': f'must be one of {", ".join(NOTE_STATUSES)}'})
        if not _text(n['user_words']):
            problems.append({'path': f'{path}.user_words', 'problem': 'must be a non-empty string'})
        if type(n['revision']) is not int or n['revision'] < 0:
            problems.append({'path': f'{path}.revision', 'problem': 'must be a revision number'})
        if n['status'] in ('resolved', 'withdrawn'):
            r = n['resolution']
            if _keys(r, f'{path}.resolution', NOTE_RESOLUTION_KEYS, problems) \
                    and not _text(r['user_words']):
                problems.append({'path': f'{path}.resolution.user_words',
                                 'problem': 'must be a non-empty string'})
        elif n['resolution'] is not None:
            problems.append({'path': f'{path}.resolution', 'problem': 'an open note has none'})
    return problems


def validate_state(state: Any) -> list[dict]:
    """Every schema problem of ``state`` (empty when it is valid)."""
    problems: list[dict] = []
    present = tuple(k for k in TOP_OPTIONAL_KEYS if isinstance(state, dict) and k in state)
    if not _keys(state, '', TOP_KEYS + present, problems):
        return problems
    if 'task' in present and state['task'] not in TASKS:
        problems.append({'path': 'task', 'problem': f'must be one of {", ".join(TASKS)}'})
        return problems
    task = task_of(state)
    if state['schema'] != SCHEMA:
        problems.append({'path': 'schema', 'problem': f'must be "{SCHEMA}"'})
    if type(state['revision']) is not int or state['revision'] < 0:
        problems.append({'path': 'revision', 'problem': 'must be a non-negative integer'})
    _keys(state['case'], 'case', ('id', 'path', 'sha256'), problems)
    if _keys(state['dataset'], 'dataset', ('path', 'sha256', 'rows', 'row_key'), problems):
        _keys(state['dataset']['row_key'], 'dataset.row_key', ('rule', 'format'), problems)
    if isinstance(state['facts'], dict):
        for fid, fact in state['facts'].items():
            if _keys(fact, f'facts.{fid}', ('value', 'status', 'source'), problems) \
                    and fact['status'] not in EPISTEMIC_STATUSES:
                problems.append({'path': f'facts.{fid}.status',
                                 'problem': 'must be one of ' + ', '.join(EPISTEMIC_STATUSES)
                                            + ' (a fact is never confirmed)'})
    else:
        problems.append({'path': 'facts', 'problem': 'must be a mapping'})
    if not isinstance(state['prior_exposure'], list):
        problems.append({'path': 'prior_exposure', 'problem': 'must be a list'})
    proposals = state['proposals'] if isinstance(state['proposals'], dict) else {}
    if not isinstance(state['proposals'], dict):
        problems.append({'path': 'proposals', 'problem': 'must be a mapping'})
    for pid, p in proposals.items():
        problems += _proposal_problems(pid, p, task)
    if _keys(state['decisions'], 'decisions', decision_ids(task), problems):
        for decision_id in decision_ids(task):
            problems += _decision_problems(decision_id, state['decisions'][decision_id],
                                           proposals, task)
    if 'notes' in present:
        problems += _notes_problems(state['notes'], task)
    for key in ('current', 'stale', 'receipts'):
        if not isinstance(state[key], dict):
            problems.append({'path': key, 'problem': 'must be a mapping'})
    if isinstance(state['current'], dict):
        for slot, rid in state['current'].items():
            if not _text(rid):
                problems.append({'path': f'current.{slot}', 'problem': 'must be a result id'})
    _keys(state['executions'], 'executions', EXECUTION_BUCKETS, problems)
    if not isinstance(state['invalidations'], list):
        problems.append({'path': 'invalidations', 'problem': 'must be a list'})
    if isinstance(state['receipts'], dict):
        for key, receipt in state['receipts'].items():
            _keys(receipt, f'receipts.{key}', ('signature', 'result', 'revision'), problems)
    if not isinstance(state['settings'], dict) or 'bootstrap' not in state['settings']:
        problems.append({'path': 'settings', 'problem': 'must be a mapping with "bootstrap"'})
    return problems


def check_state(state: Any) -> dict:
    problems = validate_state(state)
    if problems:
        raise StudyError('invalid_state', f'The study state does not follow {SCHEMA}.',
                         details={'problems': problems})
    return state


# --- serialisation and integrity --------------------------------------------------------

def dumps(state: dict) -> bytes:
    """Canonical bytes of ``state``: sorted keys, two-space indent, final newline."""
    return (json.dumps(state, sort_keys=True, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_line(hexdigest: str) -> str:
    """Content of ``state.sha256``, in ``sha256sum`` format."""
    return f'{hexdigest}  {STATE_FILE}\n'


def parse_sha_line(text: str) -> str | None:
    parts = text.split()
    if len(parts) == 2 and parts[1] == STATE_FILE and len(parts[0]) == 64:
        return parts[0]
    return None


def verify_integrity(data: bytes, sha_text: str | None, *, pending_sha256: str | None = None) -> None:
    """Refuse state bytes that do not match ``state.sha256`` (``integrity_error``).

    ``pending_sha256`` is the digest of a commit that reached its commit point but did
    not finish writing ``state.sha256``; the state is then consistent and recovery
    completes the commit under the writer lock.
    """
    actual = digest(data)
    recorded = parse_sha_line(sha_text) if sha_text is not None else None
    if actual == recorded or (pending_sha256 is not None and actual == pending_sha256):
        return
    raise StudyError('integrity_error',
                     'state.json does not match state.sha256: the state was changed outside '
                     'hypotrail, or a write was interrupted. Nothing is read from it until the '
                     'difference is explained.',
                     details={'state_sha256': actual, 'recorded_sha256': recorded,
                              'sha_file_present': sha_text is not None})


def loads(data: bytes) -> dict:
    try:
        state = json.loads(data.decode('utf-8'))
    except (UnicodeDecodeError, ValueError) as exc:
        raise StudyError('integrity_error', f'state.json is not valid JSON: {exc}') from exc
    return check_state(state)


# --- derived views (read-only) ----------------------------------------------------------

def is_current(state: dict, slot: str) -> bool:
    rid = state['current'].get(slot)
    return rid is not None and rid not in state['stale']


def open_proposals(state: dict) -> list[dict]:
    return [p for p in state['proposals'].values() if p['status'] == 'open']


def notes(state: Mapping) -> list[dict]:
    """The junior's notes (P2), oldest first; empty for a state without ``notes``."""
    items = (state.get('notes') or {}).values()
    return sorted(items, key=lambda n: int(str(n['note_id']).rsplit('_', 1)[-1]))


def open_holds(state: Mapping, decision_id: str | None = None) -> list[dict]:
    """Open holds (P2), for one decision or for all."""
    return [n for n in notes(state) if n['status'] == 'open'
            and (decision_id is None or n['decision_id'] == decision_id)]


def _confirmed(state: dict, decision_id: str) -> bool:
    return state['decisions'][decision_id]['status'] == 'confirmed'


def _step_done(state: dict, step: dict) -> bool:
    if step['decision'] and not _confirmed(state, step['decision']):
        return False
    return all(is_current(state, a) for a in step['activities'])


def _step_requirements_met(state: dict, step: dict) -> bool:
    by_id = {s['id']: s for s in steps(state)}
    return all(_step_done(state, by_id[r]) for r in step['requires'])


def derive_plan(state: dict) -> list[dict]:
    """The plan with a status per step, derived from state only.

    Status is one of ``done``, ``needs_reconfirmation``, ``awaiting_confirmation``
    (a proposal waits for the user's words), ``ready``, or ``blocked`` (a required
    step is not done). ``current`` marks the first step that is not done.
    """
    plan, current_found = [], False
    waiting = {p['decision_id'] for p in open_proposals(state)}
    for step in steps(state):
        decision = state['decisions'][step['decision']] if step['decision'] else None
        missing = [a for a in step['activities'] if not is_current(state, a)]
        if decision is not None and decision['status'] == 'reconfirm_required':
            status = 'needs_reconfirmation'
        elif _step_done(state, step):
            status = 'done'
        elif not _step_requirements_met(state, step):
            status = 'blocked'
        elif step['decision'] in waiting:
            status = 'awaiting_confirmation'
        else:
            status = 'ready'
        is_current_step = status != 'done' and not current_found
        current_found = current_found or is_current_step
        plan.append({'id': step['id'], 'title': step['title'], 'question': step['question'],
                     'expected_output': step['expected_output'],
                     'completion': step['completion'], 'pause': step['pause'],
                     'decision': step['decision'], 'activities': list(step['activities']),
                     'decide_first': step.get('decide_first', True),
                     'missing_results': missing, 'requires': list(step['requires']),
                     'status': status, 'current': is_current_step})
    return plan


def next_action(state: dict, suspected: Mapping | None = None) -> dict:
    """The single next thing to do, in priority order.

    0. an execution recorded as active whose lease nobody holds (``suspected``, from a
       read-only lease probe by ``status``, F1) has an unknown outcome: tell the junior,
       never call it in progress, and ask before acknowledging;
    1. an interrupted execution must be acknowledged (never restarted automatically);
    2. a decision needs reconfirmation;
    3. an open proposal waits for the user's verbatim answer to its restatement;
    4. the current step needs a proposal or a result;
    5. otherwise the plan is finished.
    """
    if suspected:
        eid = sorted(suspected)[0]
        return {'kind': 'outcome_unknown', 'execution_id': eid,
                'activity': suspected[eid].get('activity'),
                'message': 'This execution is recorded as running, but no process holds its '
                           'lease: it stopped and its outcome is unknown. Tell the junior the '
                           'outcome is unknown (never call it in progress) and ask before '
                           'acknowledging it; it is not restarted automatically.'}
    interrupted = sorted(state['executions']['interrupted'])
    if interrupted:
        return {'kind': 'acknowledge_interruption', 'execution_id': interrupted[0],
                'message': 'An execution was interrupted and its outcome is unknown. Inspect it '
                           'and acknowledge it; it is not restarted automatically.'}
    for decision_id in decision_ids(state):
        decision = state['decisions'][decision_id]
        if decision['status'] == 'reconfirm_required':
            return {'kind': 'reconfirm', 'decision': decision_id,
                    'message': f'Decision {decision_id} must be confirmed again: '
                               f'{decision["reason"]}'}
    pending = sorted(open_proposals(state), key=lambda p: (p['revision'], p['proposal_id']))
    if pending:
        p = pending[0]
        return {'kind': 'await_user_words', 'proposal_id': p['proposal_id'],
                'decision': p['decision_id'],
                'message': 'Show the restatement and record the user\'s own words in reply. '
                           'A bare "ok" is not a decision.'}
    for step in derive_plan(state):
        if step['status'] == 'done':
            continue
        if step['status'] == 'blocked':
            return {'kind': 'blocked', 'step': step['id'], 'requires': step['requires'],
                    'message': f'Step {step["id"]} needs: {", ".join(step["requires"])}.'}
        decide = step['decision'] and not _confirmed(state, step['decision'])
        if decide and (step['decide_first'] or not step['missing_results']):
            return {'kind': 'propose', 'step': step['id'], 'decision': step['decision'],
                    'message': step['question']}
        return {'kind': 'run', 'step': step['id'], 'activity': step['missing_results'][0],
                'message': step['question']}
    return {'kind': 'done', 'message': 'Every step is done. Review what is not yet defensible.'}


def delegated_decisions(state: dict) -> list[str]:
    """Decisions whose current confirmation is a delegation to the assistant's default."""
    out = []
    for d in decision_ids(state):
        dec = state['decisions'][d]
        if dec['status'] in ('confirmed', 'reconfirm_required') \
                and isinstance(dec['confirmation'], dict) \
                and confirmation_basis(dec['confirmation']) == DELEGATED_DEFAULT:
            out.append(d)
    return out


def not_yet_defensible(state: dict) -> list[dict]:
    """What the study cannot claim yet, from state only (plan §6)."""
    items = []
    unconfirmed = [d for d in decision_ids(state) if not _confirmed(state, d)]
    if unconfirmed:
        items.append({'id': 'unconfirmed_decisions', 'decisions': unconfirmed,
                      'text': 'These decisions are not confirmed: ' + ', '.join(unconfirmed) + '.'})
    if task_of(state) == REGRESSION:
        items.append({'id': 'validation_is_not_independent',
                      'text': 'Validation rows are used to compare the models and to choose '
                              'one, so validation errors are not independent evidence of '
                              'future error.'})
    else:
        items.append({'id': 'validation_is_not_independent',
                      'text': 'Validation rows are used to compare models and to choose the '
                              'policy and its threshold or capacity, so validation results '
                              'are not independent evidence of future performance.'})
    if state['prior_exposure']:
        items.append({'id': 'public_data_already_explored',
                      'text': 'The data were explored or published before this study; its rows '
                              'are not unseen.',
                      'sources': [p['source'] for p in state['prior_exposure']]})
    structure = state['structure']
    missing = [k for k in ('time_column', 'group_column') if structure[k]['value'] is None]
    group = structure['group_column']['value']
    if group is not None:
        items.append({'id': 'grouped_split_unsupported', 'column': group,
                      'capability': 'grouped split (v0.2)',
                      'text': f'Rows that share a value of {group} can fall in both partitions: '
                              f'this version has no grouped split, so a split reports how many '
                              f'group values its partitions share instead of preventing it. '
                              f'Validation rows of a shared group are not independent of the '
                              f'training rows.'})
    if missing:
        items.append({'id': 'no_time_or_entity_identifier', 'missing': missing,
                      'text': 'The data have no time column or entity identifier, so the study '
                              'cannot check drift over time or repeated entities across '
                              'partitions.'})
    availability = state['decisions']['feature_availability']['value'] or {}
    uncertain = sorted(f for f, v in availability.items() if v == 'uncertain_included')
    if uncertain:
        items.append({'id': 'uncertain_features_included', 'features': uncertain,
                      'text': 'These features are used although their availability at prediction '
                              'time is uncertain: ' + ', '.join(uncertain) + '.'})
    holds = open_holds(state)
    if holds:
        said = '; '.join(f'"{n["user_words"]}" ({n["decision_id"]})' for n in holds)
        items.append({'id': 'open_holds', 'notes': [n['note_id'] for n in holds],
                      'decisions': sorted({n['decision_id'] for n in holds}),
                      'text': 'The junior set a condition that is not resolved yet, so these '
                              'decisions cannot be confirmed until their own words resolve it: '
                              + said + '.'})
    conclusion = state['decisions'].get('conclusion') or {}
    if conclusion.get('status') == 'reconfirm_required':
        # D2: a decision the conclusion summarizes changed after it was confirmed.
        items.append({'id': 'conclusion_outdated', 'decisions': ['conclusion'],
                      'reason': conclusion.get('reason'),
                      'text': 'The conclusion was confirmed before a decision it summarizes '
                              'changed, so its text may no longer describe the study: rewrite '
                              'it if needed and ask the junior to confirm it again.'})
    choice = choice_decision(state)
    verdict = (conclusion.get('value') or {}).get('verdict') \
        if isinstance(conclusion.get('value'), Mapping) else None
    if verdict == 'inconclusive' and conclusion.get('status') in ('confirmed', 'reconfirm_required') \
            and not _confirmed(state, choice):
        # D6: an inconclusive conclusion without an adopted policy (or a chosen model).
        what = 'no policy is adopted' if choice == 'policy' else 'no model is chosen'
        items.append({'id': 'inconclusive_without_choice', 'decisions': [choice],
                      'text': f'The conclusion is inconclusive and {what}: the study recommends '
                              'nothing to act on yet; it records why and what would settle it.'})
    delegated = delegated_decisions(state)
    if delegated:
        items.append({'id': 'delegated_decisions', 'decisions': delegated,
                      'text': 'Decided by delegation to the assistant\'s default, not by the '
                              'junior\'s own judgment: ' + ', '.join(delegated) + '.'})
    if state['stale']:
        items.append({'id': 'stale_results', 'results': sorted(state['stale']),
                      'text': 'Some results are stale and must be recomputed before they are cited.'})
    if state['executions']['interrupted']:
        items.append({'id': 'interrupted_executions',
                      'executions': sorted(state['executions']['interrupted']),
                      'text': 'An execution has an unknown outcome.'})
    items.append({'id': 'no_causality',
                  'text': 'Associations in observational data do not show that acting on a '
                          'variable would change the outcome.'})
    items.append({'id': 'workbench_not_tracked',
                  'text': 'Experiments in the notebook workbench are not recorded and are not '
                          'decisions.'})
    return items
