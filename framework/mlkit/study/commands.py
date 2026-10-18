"""Commands of the ``hypotrail`` CLI (plan §4; contract in ``docs/specs/CLI-CONTRACT.md``).

Every command returns an :class:`Outcome`: a JSON payload with a versioned ``schema``
and an exit code. Mutations go through :func:`mlkit.reliability.apply_command` as
``{request_id, expected_revision, action, params}`` under the writer lock
(:meth:`mlkit.study.store.StudyStore.execute`).

Actions (``ACTIONS``) are registered by name with a factory that receives the
:class:`Context` of the request and returns a :class:`mlkit.reliability.Handler`.
Phase 2 activities add their own actions with :func:`register_action` (for example
``run.reserve`` and ``run.promote``) and call the precondition checks in
:mod:`mlkit.study.preconditions`.

Decision actions:

* ``decide.propose``: records a first-class proposal with its restatement. Proposing
  never changes a confirmed decision; it supersedes an older open proposal for the
  same decision.
* ``decide.confirm``: needs the user's verbatim words in reply to the restatement,
  and an open proposal created by an earlier request whose basis (the confirmed
  decisions it rests on) is unchanged. Otherwise it refuses with
  ``ambiguous_confirmation``. It checks the three-pause preconditions, applies the
  §3.7 dependency table, and records the invalidation.
* ``decide.withdraw``: closes an open proposal.

pandas is never imported here, so ``status`` and ``plan`` stay fast.
"""
from __future__ import annotations

import copy
import importlib
import importlib.util
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from mlkit.reliability import CommandRefused, Handler

from . import case as c
from . import data as dt
from . import dependencies as dep
from . import exposure, lock, preconditions, read, view
from . import state as st
from .errors import StudyError
from .store import StudyStore

# --- contract constants (frozen by tests/study/test_contract_freeze.py) -----------------

SCHEMAS = {'init': 'hypotrail.init/1', 'status': 'hypotrail.status/1',
           'plan': 'hypotrail.plan/1', 'decide': 'hypotrail.decide/1',
           'error': 'hypotrail.error/1'}
EXIT_OK = 0
EXIT_INTERNAL = 1
EXIT_REFUSED = 2
EXIT_ARTIFACT_STALE = 3
EXIT_UNKNOWN_OUTCOME = 4

ACTION_PROPOSE = 'decide.propose'
ACTION_CONFIRM = 'decide.confirm'
ACTION_WITHDRAW = 'decide.withdraw'
PROPOSE_PARAMS = frozenset({'decision_id', 'value', 'restatement', 'rationale'})
CONFIRM_PARAMS = frozenset({'proposal_id', 'user_words', 'channel', 'actor'})
WITHDRAW_PARAMS = frozenset({'proposal_id', 'reason'})
DEFAULT_CHANNEL = 'chat'
DEFAULT_ACTOR = 'user'

SPLIT_METHODS = ('stratified_random',)
SPLIT_KEYS = ('method', 'validation_fraction', 'seed')
CONCLUSION_KEYS = ('verdict', 'text')
AGENT_TEMPLATES = Path(__file__).resolve().parent / 'agent'
AGENT_TEMPLATE_README = 'README.md'
# Companion files that may sit next to a case. They are never read by init: their
# statuses are tutorial choices, not human decisions (AGENTS.md).
IGNORED_CASE_SOURCES = ('project.json', 'results.json', 'tutorial-results.json',
                        'answers.yaml', 'project.yaml', 'frame.yaml')

# Words that alone never confirm anything (plan §5): a reply made only of these is a
# bare acknowledgement, not the user's own restatement of the decision.
ACKNOWLEDGEMENT_WORDS = frozenset('''
    ok okay okey k kk yes y yep yeah yup ya sure fine go ahead do it agreed agree approve
    approved confirm confirmed correct right exactly perfect good great sounds looks lgtm
    keep that this one it is s let lets please thanks thank you so alright all done
    oui ouais d accord daccord garde ça ca vas parfait c est cest bon très tres bien super
    merci valide validé go
'''.split())


@dataclass(frozen=True)
class Outcome:
    """A command result: the JSON payload printed and the process exit code."""

    payload: dict
    exit_code: int = EXIT_OK


@dataclass(frozen=True)
class Context:
    """What an action factory knows about the request it serves."""

    store: StudyStore
    request_id: str


ActionFactory = Callable[[Context], Handler]
ACTIONS: dict[str, ActionFactory] = {}


def register_action(name: str, factory: ActionFactory) -> None:
    """Register an ``apply_command`` action (Phase 2 extension point).

    ``factory(ctx)`` returns a :class:`mlkit.reliability.Handler` whose ``run(state,
    params)`` mutates state in memory and returns a JSON-serialisable result. Names are
    dotted (``run.promote``); registering a name twice is an error.
    """
    if name in ACTIONS:
        raise ValueError(f'action {name} is already registered')
    ACTIONS[name] = factory


def handlers(ctx: Context) -> dict[str, Handler]:
    return {name: factory(ctx) for name, factory in ACTIONS.items()}


def error_payload(command: str, exc: Exception) -> dict:
    if hasattr(exc, 'to_dict'):
        error = exc.to_dict()
    else:
        error = {'code': 'internal_error', 'message': f'{type(exc).__name__}: {exc}'}
    return {'schema': SCHEMAS['error'], 'ok': False, 'command': command, 'error': error}


def refused(command: str, exc: Exception) -> Outcome:
    return Outcome(error_payload(command, exc), EXIT_REFUSED)


# --- value checks -----------------------------------------------------------------------

NUMBER = re.compile(r'(?<![\w.])\d+(?:[.,]\d+)?')


def _numbers(text: str) -> set[float]:
    return {float(m.replace(',', '.')) for m in NUMBER.findall(text)}


def _value_numbers(value: Any) -> set[float]:
    found: set[float] = set()

    def walk(node):
        if isinstance(node, bool):
            return
        if isinstance(node, (int, float)):
            found.add(float(node))
            if 0 < node < 1:   # a fraction may be written as a percentage
                found.update({round(100 * node, 6), round(100 * (1 - node), 6)})
        elif isinstance(node, str):
            found.update(_numbers(node))
        elif isinstance(node, Mapping):
            for k, v in node.items():
                walk(k)
                walk(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                walk(v)
    walk(value)
    return found


def literal_numbers(text: str, value: Any) -> list[str]:
    """Numbers written in ``text`` that do not come from ``value``.

    A proposal's restatement and rationale may repeat the numbers of the proposed
    value; any other number must come from a registry result, never from free text.
    """
    allowed = _value_numbers(value)
    return sorted({m for m in NUMBER.findall(text)
                   if round(float(m.replace(',', '.')), 6) not in allowed})


def _invalid(message: str, **details) -> CommandRefused:
    return CommandRefused('invalid_value', message, details=details)


def case_of(state: Mapping) -> c.Case:
    return c.load_case(state['case']['path'], verify_data=False)


def candidate_features(case: c.Case) -> list[str]:
    return [v['name'] for v in case.document['variables'] if v['role'] == 'feature']


def validate_value(state: Mapping, decision_id: str, value: Any) -> None:
    """Refuse a value that does not fit ``decision_id`` (``invalid_value``)."""
    if decision_id == 'prediction_time':
        if not isinstance(value, str) or not value.strip():
            raise _invalid('prediction_time is a non-empty description of the prediction moment.')
    elif decision_id == 'feature_availability':
        features = candidate_features(case_of(state))
        if not isinstance(value, Mapping):
            raise _invalid('feature_availability maps every candidate feature to a status.',
                           features=features, statuses=list(st.AVAILABILITY_DECISIONS))
        missing = sorted(set(features) - set(value))
        unknown = sorted(set(value) - set(features))
        bad = sorted(k for k, v in value.items() if v not in st.AVAILABILITY_DECISIONS)
        if missing or unknown or bad:
            raise _invalid('Every candidate feature needs exactly one availability status.',
                           missing=missing, not_features=unknown, invalid_status=bad,
                           statuses=list(st.AVAILABILITY_DECISIONS))
    elif decision_id == 'split':
        if not isinstance(value, Mapping) or set(value) != set(SPLIT_KEYS):
            raise _invalid('split is {"method", "validation_fraction", "seed"}.',
                           keys=list(SPLIT_KEYS))
        if value['method'] not in SPLIT_METHODS:
            raise CommandRefused('unsupported_capability',
                                 f'Split method {value["method"]!r} is not available.',
                                 details={'methods': list(SPLIT_METHODS)})
        fraction = value['validation_fraction']
        if isinstance(fraction, bool) or not isinstance(fraction, (int, float)) \
                or not 0 < fraction < 1:
            raise _invalid('validation_fraction is strictly between 0 and 1.')
        if type(value['seed']) is not int:
            raise _invalid('seed is an integer.')
    elif decision_id == 'policy':
        if dep.parse_policy(value) is None:
            raise _invalid('policy is "threshold:<t in [0, 1]>" or "capacity:<k >= 1>".')
    elif decision_id == 'conclusion':
        if not isinstance(value, Mapping) or set(value) != set(CONCLUSION_KEYS) \
                or value['verdict'] not in preconditions.CONCLUSION_VERDICTS \
                or not isinstance(value['text'], str) or not value['text'].strip():
            raise _invalid('conclusion is {"verdict", "text"}.',
                           verdicts=list(preconditions.CONCLUSION_VERDICTS))


def is_bare_acknowledgement(words: str) -> bool:
    """True when a reply has no content beyond acknowledgement words ("ok", "garde ça")."""
    tokens = re.sub(r"[^\w\s]", ' ', words.lower()).split()
    return all(t in ACKNOWLEDGEMENT_WORDS for t in tokens)


def basis(state: Mapping, decision_id: str) -> dict:
    """Confirmed values a proposal rests on (its ``depends_on`` decisions)."""
    out = {}
    for d in st.DEPENDS_ON[decision_id]:
        dec = state['decisions'][d]
        out[d] = dec['value'] if dec['status'] == 'confirmed' else None
    return out


def _ambiguous(reason: str, message: str, **details) -> CommandRefused:
    return CommandRefused('ambiguous_confirmation', message, details={'reason': reason, **details})


def _verify_sources(state: Mapping) -> None:
    """Plan §3.7 row 12: a changed case or dataset is refused, never absorbed."""
    case_path, data_path = Path(state['case']['path']), Path(state['dataset']['path'])
    for label, path, expected in (('case', case_path, state['case']['sha256']),
                                  ('dataset', data_path, state['dataset']['sha256'])):
        actual = c.sha256_file(path) if path.is_file() else None
        if actual != expected:
            raise CommandRefused('dataset_changed',
                                 f'The {label} file changed since the study started; decisions '
                                 f'and results refer to the original bytes.',
                                 details={'path': str(path), 'expected_sha256': expected,
                                          'actual_sha256': actual})


# --- decision actions -------------------------------------------------------------------

def _propose(ctx: Context) -> Handler:
    def check(params):
        if params['decision_id'] not in st.DECISION_IDS:
            raise CommandRefused('unknown_decision', f'Unknown decision {params["decision_id"]!r}.',
                                 details={'decisions': list(st.DECISION_IDS)})
        for key in ('restatement', 'rationale'):
            if not isinstance(params[key], str) or not params[key].strip():
                raise _invalid(f'{key} is a non-empty string.', field=key)
            found = literal_numbers(params[key], params['value'])
            if found:
                raise CommandRefused('literal_number_in_text',
                                     f'The {key} contains numbers that are not part of the '
                                     f'proposed value. Cite results by their result_id instead.',
                                     details={'field': key, 'numbers': found})

    def run(state, params):
        decision_id, value = params['decision_id'], params['value']
        validate_value(state, decision_id, value)
        revision = state['revision'] + 1
        superseded = []
        for p in st.open_proposals(state):
            if p['decision_id'] == decision_id:
                p.update(status='superseded', closed_revision=revision,
                         closed_reason='a newer proposal replaced it')
                superseded.append(p['proposal_id'])
        pid = f'p_{len(state["proposals"]) + 1}'
        state['proposals'][pid] = {
            'proposal_id': pid, 'decision_id': decision_id, 'value': copy.deepcopy(value),
            'restatement': params['restatement'], 'rationale': params['rationale'],
            'revision': revision, 'status': 'open', 'created': st.now(),
            'request_id': ctx.request_id, 'basis': basis(state, decision_id)}
        decision = state['decisions'][decision_id]
        if decision['status'] in ('open', 'proposed'):
            decision.update(status='proposed', value=copy.deepcopy(value), proposal_id=pid,
                            revision=revision)
        return {'proposal_id': pid, 'decision_id': decision_id, 'status': 'open',
                'decision_status': decision['status'], 'superseded': superseded,
                'restatement': params['restatement']}
    return Handler(PROPOSE_PARAMS, run, check)


def _confirm(ctx: Context) -> Handler:
    def check(params):
        words = params['user_words']
        if not isinstance(words, str) or not words.strip():
            raise _ambiguous('missing_user_words', 'A confirmation needs the user\'s own words in '
                                                   'reply to the restatement.')
        if is_bare_acknowledgement(words):
            raise _ambiguous('bare_acknowledgement',
                             'A bare acknowledgement is not a decision. Restate the proposal and '
                             'ask the user to answer it in their own words.',
                             user_words=words)
        if params['channel'] not in st.CHANNELS:
            raise _invalid(f'channel is one of {", ".join(st.CHANNELS)}.')
        if not isinstance(params['actor'], str) or not params['actor'].strip():
            raise _invalid('actor is a non-empty string.')

    def run(state, params):
        pid = params['proposal_id']
        proposal = state['proposals'].get(pid)
        if proposal is None:
            raise _ambiguous('proposal_not_found', f'There is no proposal {pid}; propose first.',
                             proposal_id=pid, open_proposals=[p['proposal_id'] for p in
                                                              st.open_proposals(state)])
        if proposal['status'] != 'open':
            raise _ambiguous(f'proposal_{proposal["status"]}',
                             f'Proposal {pid} is {proposal["status"]}; only an open proposal '
                             f'can be confirmed.', proposal_id=pid,
                             open_proposals=[p['proposal_id'] for p in st.open_proposals(state)])
        if proposal.get('request_id') == ctx.request_id or proposal['revision'] > state['revision']:
            raise _ambiguous('same_request', 'A proposal is confirmed by a later request than the '
                                             'one that created it.', proposal_id=pid)
        decision_id, value = proposal['decision_id'], proposal['value']
        current_basis = basis(state, decision_id)
        if proposal.get('basis', current_basis) != current_basis:
            raise _ambiguous('proposal_stale', f'Proposal {pid} rests on decisions that changed '
                                               f'since it was made; propose again.',
                             proposal_id=pid, basis=proposal.get('basis'),
                             current_basis=current_basis)
        _verify_sources(state)
        validate_value(state, decision_id, value)
        preconditions.require_decision(state, decision_id, value, store=ctx.store)
        decision = state['decisions'][decision_id]
        revision = state['revision'] + 1
        had = decision['status'] in ('confirmed', 'reconfirm_required') \
            and decision['confirmation'] is not None
        old = copy.deepcopy(decision['value']) if had else None
        previous = ({'value': old, 'confirmation': copy.deepcopy(decision['confirmation']),
                     'proposal_id': decision['proposal_id']} if had else None)
        eff = dep.effects(copy.deepcopy(state), decision_id, old, value)
        if had and decision['proposal_id'] in state['proposals'] \
                and decision['proposal_id'] != pid:
            state['proposals'][decision['proposal_id']].update(
                status='superseded', closed_revision=revision,
                closed_reason=f'replaced by {pid}')
        confirmation = st.confirmation(user_words=params['user_words'], proposal=proposal,
                                       channel=params['channel'], actor=params['actor'],
                                       revision=revision)
        proposal.update(status='confirmed', closed_revision=revision, closed_reason='confirmed')
        decision.update(status='confirmed', value=copy.deepcopy(value), proposal_id=pid,
                        confirmation=confirmation, revision=revision, reason=None)
        record = dep.apply_effects(state, eff, revision=revision, decision_id=decision_id,
                                   store=ctx.store, previous=previous)
        return {'decision_id': decision_id, 'proposal_id': pid, 'status': 'confirmed',
                'value': copy.deepcopy(value), 'user_words': params['user_words'],
                'channel': params['channel'], 'actor': params['actor'],
                'invalidation': {k: record[k] for k in ('mutation', 'row', 'reason',
                                                         'stale_results', 'stale_slots',
                                                         'reconfirm_required')}}
    return Handler(CONFIRM_PARAMS, run, check)


def _withdraw(ctx: Context) -> Handler:
    def check(params):
        if params['reason'] is not None and not isinstance(params['reason'], str):
            raise _invalid('reason is a string.')

    def run(state, params):
        pid = params['proposal_id']
        proposal = state['proposals'].get(pid)
        if proposal is None:
            raise CommandRefused('unknown_proposal', f'There is no proposal {pid}.',
                                 details={'proposal_id': pid})
        if proposal['status'] != 'open':
            raise CommandRefused('proposal_not_open', f'Proposal {pid} is {proposal["status"]}.',
                                 details={'proposal_id': pid, 'status': proposal['status']})
        revision = state['revision'] + 1
        proposal.update(status='withdrawn', closed_revision=revision,
                        closed_reason=params['reason'] or 'withdrawn')
        decision = state['decisions'][proposal['decision_id']]
        if decision['status'] == 'proposed' and decision['proposal_id'] == pid:
            decision.update(status='open', value=None, proposal_id=None, revision=revision)
        return {'proposal_id': pid, 'decision_id': proposal['decision_id'], 'status': 'withdrawn',
                'decision_status': decision['status']}
    return Handler(WITHDRAW_PARAMS, run, check)


register_action(ACTION_PROPOSE, _propose)
register_action(ACTION_CONFIRM, _confirm)
register_action(ACTION_WITHDRAW, _withdraw)


# --- commands ---------------------------------------------------------------------------

def _case_file(path) -> Path:
    path = Path(path).resolve()
    return path / c.CASE_FILE if path.is_dir() else path


def _copy_agent_templates(study_dir: Path) -> dict:
    """Copy the study agent instructions (plan §5) without overwriting anything."""
    copied, skipped = [], []
    if AGENT_TEMPLATES.is_dir():
        for src in sorted(AGENT_TEMPLATES.rglob('*')):
            rel = src.relative_to(AGENT_TEMPLATES)
            if not src.is_file() or rel.as_posix() == AGENT_TEMPLATE_README \
                    or '__pycache__' in rel.parts:
                continue
            dest = study_dir / rel
            if dest.exists():
                skipped.append(rel.as_posix())
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            copied.append(rel.as_posix())
    status = 'copied' if copied else ('kept_existing' if skipped else 'no_templates_yet')
    return {'source': str(AGENT_TEMPLATES), 'copied': copied, 'skipped_existing': skipped,
            'status': status}


def init(case_path, study_dir) -> Outcome:
    """Create a study on a case (revision 1). Never overwrites an existing study."""
    lock.require_posix()
    study_dir = Path(study_dir).resolve()
    store = StudyStore(study_dir)
    if store.exists():
        raise StudyError('state_exists', 'A study already exists here; it is never overwritten.',
                         details={'study': str(study_dir)})
    case = c.require_supported(c.load_case(_case_file(case_path)))
    index = dt.row_index(case)
    state = st.initial_state(case)
    study_dir.mkdir(parents=True, exist_ok=True)
    store.create(state)
    with lock.writer_lock(study_dir):
        record = exposure.record(store, exposure_id=exposure.new_exposure_id(),
                                 revision=state['revision'], activity='init.structure',
                                 result_id=None, purpose='structural_inspection', partition='all',
                                 row_keys=index.keys, dataset_sha256=index.dataset_sha256,
                                 columns=case.column_names)
    agent = _copy_agent_templates(study_dir)
    ignored = sorted(n for n in IGNORED_CASE_SOURCES if (case.root / n).exists())
    snapshot = read.open(study_dir).state
    return Outcome({'schema': SCHEMAS['init'], 'ok': True, 'study': str(study_dir),
                    'revision': snapshot['revision'], 'case': snapshot['case'],
                    'dataset': snapshot['dataset'],
                    'structural_exposure': {'exposure_id': record['exposure_id'],
                                            'n_rows': record['n_rows']},
                    'plan': st.derive_plan(snapshot), 'next_action': st.next_action(snapshot),
                    'agent_instructions': agent,
                    'ignored_sources': ignored,
                    'note': 'Companion files next to the case are not read: their statuses are '
                            'tutorial choices, not decisions. Every decision starts open.'})


def status(study_dir, since: int | None = None) -> Outcome:
    study = read.open(study_dir)
    payload = {'schema': SCHEMAS['status'], 'ok': True, 'study': str(study.study_dir),
               'revision': study.revision, 'since': since,
               'changed': None if since is None else study.revision > since,
               'changes_since': None if since is None else study.revisions(since),
               'view': view.build(study)}
    return Outcome(payload)


def plan(study_dir) -> Outcome:
    study = read.open(study_dir)
    state = study.state
    steps = st.derive_plan(state)
    return Outcome({'schema': SCHEMAS['plan'], 'ok': True, 'study': str(study.study_dir),
                    'revision': study.revision, 'steps': steps,
                    'current_step': next((s['id'] for s in steps if s['current']), None),
                    'next_action': st.next_action(state)})


def apply(study_dir, *, action: str, params: dict, request_id: str, expected_revision: int,
          command: str = 'decide') -> Outcome:
    """Apply one registered action through ``apply_command`` and describe the receipt."""
    store = StudyStore(study_dir)
    if not store.exists():
        raise StudyError('study_missing', f'No study here: {store.state_path} does not exist.',
                         details={'study': str(store.study_dir)})
    request = {'request_id': request_id, 'expected_revision': expected_revision,
               'action': action, 'params': params}
    receipt = store.execute(request, handlers(Context(store, request_id)))
    payload = {'schema': SCHEMAS['decide'], 'ok': True, 'study': str(store.study_dir),
               'action': action, 'request_id': request_id,
               'replayed': bool(receipt.get('replayed')), 'revision': receipt['revision'],
               'result': receipt['result'], 'artifacts': None}
    code = EXIT_OK
    if not payload['replayed']:
        artifacts = after_commit(store.study_dir, payload)
        if artifacts is not None:
            payload['artifacts'] = artifacts
            if any(a.get('status') in ('stale', 'failed') for a in artifacts.values()):
                code = EXIT_ARTIFACT_STALE
    return Outcome(payload, code)


# Phase 3 extension point: a module that renders artefacts after every committed
# mutation (WP3.4). It defines ``after_commit(study_dir: Path, payload: dict) ->
# {artifact name: {"status": "ok" | "stale" | "failed", ...}}``. A render failure never
# undoes the commit; it makes the command exit with code 3.
AFTER_COMMIT_MODULE = 'mlkit.study.cmd_render'


def after_commit(study_dir: Path, payload: dict) -> dict | None:
    if importlib.util.find_spec(AFTER_COMMIT_MODULE) is None:
        return None
    module = importlib.import_module(AFTER_COMMIT_MODULE)
    hook = getattr(module, 'after_commit', None)
    return hook(Path(study_dir), payload) if hook else None

