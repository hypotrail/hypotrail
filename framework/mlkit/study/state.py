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
from typing import Any

from .case import EPISTEMIC_STATUSES, Case, require_supported
from .errors import StudyError

SCHEMA = 'hypotrail.study/1'
STATE_FILE = 'state.json'
SHA_FILE = 'state.sha256'

DECISION_IDS = ('prediction_time', 'feature_availability', 'split', 'policy', 'conclusion')
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
# Optional slots outside the plan: ``eda.rate_by`` has one slot per column,
# ``eda.rate_by:<column>`` (``mlkit.study.activities.slot_of``). They are shown with the
# training EDA step and never block a step.
PER_COLUMN_SLOT_PREFIXES = ('eda.rate_by:',)

TOP_KEYS = ('schema', 'revision', 'created', 'updated', 'case', 'dataset', 'facts',
            'structure', 'prior_exposure', 'decisions', 'proposals', 'current', 'stale',
            'executions', 'invalidations', 'receipts', 'settings')
DECISION_KEYS = ('status', 'value', 'proposal_id', 'confirmation', 'depends_on', 'revision',
                 'reason')
PROPOSAL_KEYS = ('proposal_id', 'decision_id', 'value', 'restatement', 'rationale', 'revision',
                 'status', 'created')
# Written by ``hypotrail decide`` (WP1.4): the request that created the proposal, the
# confirmed values it was based on (a change makes it stale), and why it was closed.
PROPOSAL_OPTIONAL_KEYS = ('request_id', 'basis', 'closed_revision', 'closed_reason')
EXECUTION_BUCKETS = ('active', 'interrupted', 'late')


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


# --- construction -----------------------------------------------------------------------

def empty_decision(decision_id: str) -> dict:
    return {'status': 'open', 'value': None, 'proposal_id': None, 'confirmation': None,
            'depends_on': list(DEPENDS_ON[decision_id]), 'revision': None, 'reason': None}


def initial_state(case: Case, *, created: str | None = None) -> dict:
    """The state of a new study on ``case``, before its first commit (revision 0).

    Refuses an unsupported case (``unsupported_capability``) without fallback. Facts
    and structure statements are copied from the case with their statuses; no
    decision is taken.
    """
    require_supported(case)
    doc = case.document
    stamp = created or now()
    return {
        'schema': SCHEMA,
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
        'decisions': {d: empty_decision(d) for d in DECISION_IDS},
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


def _decision_problems(decision_id: str, d: Any, proposals: dict) -> list[dict]:
    path = f'decisions.{decision_id}'
    problems: list[dict] = []
    if not _keys(d, path, DECISION_KEYS, problems):
        return problems
    if d['status'] not in DECISION_STATUSES:
        problems.append({'path': f'{path}.status',
                         'problem': f'must be one of {", ".join(DECISION_STATUSES)}'})
    if d['depends_on'] != list(DEPENDS_ON[decision_id]):
        problems.append({'path': f'{path}.depends_on',
                         'problem': f'must be {list(DEPENDS_ON[decision_id])}'})
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


def _proposal_problems(pid: Any, p: Any) -> list[dict]:
    path = f'proposals.{pid}'
    problems: list[dict] = []
    present = tuple(k for k in PROPOSAL_OPTIONAL_KEYS if isinstance(p, dict) and k in p)
    if not _keys(p, path, PROPOSAL_KEYS + present, problems):
        return problems
    if p['proposal_id'] != pid:
        problems.append({'path': f'{path}.proposal_id', 'problem': 'must equal its key'})
    if p['decision_id'] not in DECISION_IDS:
        problems.append({'path': f'{path}.decision_id',
                         'problem': f'must be one of {", ".join(DECISION_IDS)}'})
    if p['status'] not in PROPOSAL_STATUSES:
        problems.append({'path': f'{path}.status',
                         'problem': f'must be one of {", ".join(PROPOSAL_STATUSES)}'})
    for key in ('restatement', 'rationale', 'created'):
        if not _text(p[key]):
            problems.append({'path': f'{path}.{key}', 'problem': 'must be a non-empty string'})
    if type(p['revision']) is not int or p['revision'] < 0:
        problems.append({'path': f'{path}.revision', 'problem': 'must be a revision number'})
    return problems


def validate_state(state: Any) -> list[dict]:
    """Every schema problem of ``state`` (empty when it is valid)."""
    problems: list[dict] = []
    if not _keys(state, '', TOP_KEYS, problems):
        return problems
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
        problems += _proposal_problems(pid, p)
    if _keys(state['decisions'], 'decisions', DECISION_IDS, problems):
        for decision_id in DECISION_IDS:
            problems += _decision_problems(decision_id, state['decisions'][decision_id], proposals)
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


def _confirmed(state: dict, decision_id: str) -> bool:
    return state['decisions'][decision_id]['status'] == 'confirmed'


def _step_done(state: dict, step: dict) -> bool:
    if step['decision'] and not _confirmed(state, step['decision']):
        return False
    return all(is_current(state, a) for a in step['activities'])


def _step_requirements_met(state: dict, step: dict) -> bool:
    by_id = {s['id']: s for s in STEPS}
    return all(_step_done(state, by_id[r]) for r in step['requires'])


def derive_plan(state: dict) -> list[dict]:
    """The plan with a status per step, derived from state only.

    Status is one of ``done``, ``needs_reconfirmation``, ``awaiting_confirmation``
    (a proposal waits for the user's words), ``ready``, or ``blocked`` (a required
    step is not done). ``current`` marks the first step that is not done.
    """
    plan, current_found = [], False
    waiting = {p['decision_id'] for p in open_proposals(state)}
    for step in STEPS:
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


def next_action(state: dict) -> dict:
    """The single next thing to do, in priority order.

    1. an interrupted execution must be acknowledged (never restarted automatically);
    2. a decision needs reconfirmation;
    3. an open proposal waits for the user's verbatim answer to its restatement;
    4. the current step needs a proposal or a result;
    5. otherwise the plan is finished.
    """
    interrupted = sorted(state['executions']['interrupted'])
    if interrupted:
        return {'kind': 'acknowledge_interruption', 'execution_id': interrupted[0],
                'message': 'An execution was interrupted and its outcome is unknown. Inspect it '
                           'and acknowledge it; it is not restarted automatically.'}
    for decision_id in DECISION_IDS:
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
    for d in DECISION_IDS:
        dec = state['decisions'][d]
        if dec['status'] in ('confirmed', 'reconfirm_required') \
                and isinstance(dec['confirmation'], dict) \
                and confirmation_basis(dec['confirmation']) == DELEGATED_DEFAULT:
            out.append(d)
    return out


def not_yet_defensible(state: dict) -> list[dict]:
    """What the study cannot claim yet, from state only (plan §6)."""
    items = []
    unconfirmed = [d for d in DECISION_IDS if not _confirmed(state, d)]
    if unconfirmed:
        items.append({'id': 'unconfirmed_decisions', 'decisions': unconfirmed,
                      'text': 'These decisions are not confirmed: ' + ', '.join(unconfirmed) + '.'})
    items.append({'id': 'validation_is_not_independent',
                  'text': 'Validation rows are used to compare models and to choose the policy '
                          'and its threshold or capacity, so validation results are not '
                          'independent evidence of future performance.'})
    if state['prior_exposure']:
        items.append({'id': 'public_data_already_explored',
                      'text': 'The data were explored or published before this study; its rows '
                              'are not unseen.',
                      'sources': [p['source'] for p in state['prior_exposure']]})
    structure = state['structure']
    missing = [k for k in ('time_column', 'group_column') if structure[k]['value'] is None]
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
