"""Executions of activities: reserve, compute with a lease, promote (plan WP2.1).

One ``hypotrail run`` goes through three steps:

1. **Reserve** under the writer lock (``run.reserve``, the client's request): the
   preconditions are checked, the activity's ``input_key`` is derived from current
   state (:func:`mlkit.study.activities.plan`), an execution lease is taken, and the
   execution is recorded in ``state.executions.active`` with its ``started_revision``.
2. **Compute** outside the general lock, holding only the lease. Other clients can
   decide in the meantime.
3. **Promote** under the writer lock: the result is always stored in the registry
   (``registry.put``) and its exposure recorded. It is promoted into
   ``state.current[slot]`` only if the ``input_key`` recomputed from the state *now*
   is identical; otherwise the execution is recorded in ``state.executions.late``
   with status ``late_not_promoted``. The lease is released after that commit.

This is the pattern of ``mlkit.reliability.start/finish/recover`` (durable
reservation before computing, an unknown outcome is never repeated), rebuilt on the
study store: the legacy functions are bound to the pilot and are not reused as code.

**Unknown outcome.** A lease file whose lock nobody holds means its process ended
without promoting. The next ``run`` (or acknowledgement) records the execution in
``state.executions.interrupted`` with status ``interrupted_unknown`` (``run.recover``)
and records the exposure it had planned, with ``result_id: null``: rows that may
have been read are never treated as unseen. From then on every ``run`` is refused
with ``interrupted_execution_pending`` (exit code 4) until ``hypotrail run
--acknowledge-interruption E --user-words TEXT``; the junior's words are recorded in
the acknowledgement and the execution history. Nothing is restarted automatically. ``status`` is
read-only and reports a dead execution as ``active`` until the next ``run``
detects it.

**Idempotency.** The execution id is derived from the client's ``request_id``.
Replaying a request returns the state of that execution (running, promoted, late,
failed, interrupted, acknowledged) and never fits a second time. Internal steps use
request ids derived from it (``promote:…``, ``fail:…``, ``recover:…``).

**Already current.** A ``run`` whose slot already holds a current result with the
same ``input_key`` answers ``already_current`` without reserving or computing.

Test hooks (``HYPOTRAIL_TEST_HOOKS=1`` only, see ``cmd_run``): stop the process after
the reservation or before the promotion, or pause before the promotion.

This module imports neither pandas nor scikit-learn; the computation does, lazily.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable, Mapping

from mlkit import reliability
from mlkit.reliability import CommandRefused, Handler

from . import activities as act
from . import commands as cmd
from . import exposure, lock, registry
from . import records as rec
from . import state as st
from .errors import StudyError
from .store import StudyStore, atomic_write_json

SCHEMA = 'hypotrail.run/1'
PAYLOAD_KEYS = ('schema', 'ok', 'study', 'action', 'request_id', 'replayed', 'revision',
                'activity', 'execution_id', 'status', 'result_id', 'values', 'result',
                'artifacts')
RESERVE, PROMOTE, FAIL, RECOVER, ACKNOWLEDGE = ('run.reserve', 'run.promote', 'run.fail',
                                               'run.recover', 'run.acknowledge')
STATUSES = ('running', 'promoted', 'late_not_promoted', 'already_current', 'failed',
            'interrupted_unknown', 'acknowledged')
HISTORY_DIR = 'executions'

# Plans computed by a reserve handler, handed to the computing step of the same
# process (keyed by execution id). Never persisted: a replay re-derives nothing.
_PLANS: dict[str, dict] = {}


def execution_id(request_id: str) -> str:
    return 'e_' + hashlib.sha256(request_id.encode('utf-8')).hexdigest()[:24]


def derived_request_id(step: str, key: str) -> str:
    return f'{step}:' + hashlib.sha256(key.encode('utf-8')).hexdigest()[:32]


def _history_path(store: StudyStore, eid: str) -> Path:
    return store.home / HISTORY_DIR / f'{eid}.json'


def _history(store: StudyStore, eid: str, record: Mapping) -> None:
    """Execution history file (informative; state is authoritative)."""
    atomic_write_json(_history_path(store, eid), dict(record))


def _read_history(store: StudyStore, eid: str) -> dict | None:
    import json
    path = _history_path(store, eid)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except ValueError:
        return None


def _interrupted_refusal(state: Mapping) -> CommandRefused:
    pending = sorted(state['executions']['interrupted'])
    return CommandRefused('interrupted_execution_pending',
                          'An execution has an unknown outcome. Inspect it and acknowledge it '
                          'with run --acknowledge-interruption; nothing is restarted '
                          'automatically.',
                          details={'interrupted': pending,
                                   'executions': {e: state['executions']['interrupted'][e]
                                                  for e in pending}})


# --- actions ----------------------------------------------------------------------------

def _reserve(ctx: cmd.Context) -> Handler:
    def check(params):
        if not isinstance(params['options'], Mapping):
            raise CommandRefused('invalid_arguments', 'options is a mapping.')
        if params['execution_id'] != execution_id(ctx.request_id):
            raise CommandRefused('invalid_command', 'The execution id comes from the request id.')

    def run(state, params):
        if state['executions']['interrupted']:
            raise _interrupted_refusal(state)
        cmd._verify_sources(state)
        activity = act.canonical(params['activity'])
        plan = act.plan(ctx.store, state, activity, params['options'], with_exposure=True)
        eid = params['execution_id']
        revision = state['revision'] + 1
        record = {'execution_id': eid, 'activity': activity, 'slot': plan['slot'],
                  'options': plan['options'], 'request_id': ctx.request_id, 'status': 'running',
                  'started_revision': revision, 'started': st.now(),
                  'input_key': plan['input_key'], 'code_fingerprint': plan['code']['fingerprint'],
                  'exposures': plan['exposures'],
                  'lease': str(lock.lease_path(ctx.store.study_dir, eid))}
        state['executions']['active'][eid] = record
        _PLANS[eid] = {**plan, 'started_revision': revision}
        return {'execution_id': eid, 'activity': activity, 'status': 'running',
                'input_key': plan['input_key'], 'started_revision': revision}
    return Handler(frozenset({'activity', 'options', 'execution_id'}), run, check)


def _promote(ctx: cmd.Context) -> Handler:
    def run(state, params):
        eid, rid = params['execution_id'], params['result_id']
        record = state['executions']['active'].pop(eid, None)
        if record is None:
            raise CommandRefused('unknown_execution', f'Execution {eid} is not active.',
                                 details={'execution_id': eid})
        reason = None
        try:
            now = act.plan(ctx.store, state, record['activity'], record['options'])
        except (CommandRefused, StudyError) as exc:
            now, reason = None, f'the activity can no longer run on current state: {exc.code}'
        if now is not None and now['input_key'] != params['input_key']:
            reason = ('the inputs changed while it was computing (decision, upstream result, '
                      'or code)')
        done = {**record, 'result_id': rid, 'finished': st.now(),
                'finished_revision': state['revision'] + 1}
        if reason is None:
            slot = record['slot']
            previous = state['current'].get(slot)
            state['current'][slot] = rid
            state['stale'].pop(rid, None)
            done.update(status='promoted', replaced=previous if previous != rid else None)
        else:
            done.update(status='late_not_promoted', reason=reason,
                        current_input_key=now['input_key'] if now else None)
            state['executions']['late'][eid] = done
        return {'execution_id': eid, 'activity': record['activity'], 'slot': record['slot'],
                'status': done['status'], 'result_id': rid, 'input_key': params['input_key'],
                'reason': reason, 'started_revision': record['started_revision']}
    return Handler(frozenset({'execution_id', 'result_id', 'input_key'}), run)


def _fail(ctx: cmd.Context) -> Handler:
    def run(state, params):
        eid = params['execution_id']
        record = state['executions']['active'].pop(eid, None)
        if record is None:
            raise CommandRefused('unknown_execution', f'Execution {eid} is not active.',
                                 details={'execution_id': eid})
        return {'execution_id': eid, 'activity': record['activity'], 'status': 'failed',
                'error': params['error'], 'started_revision': record['started_revision']}
    return Handler(frozenset({'execution_id', 'error'}), run)


def _recover(ctx: cmd.Context) -> Handler:
    def run(state, params):
        eid = params['execution_id']
        record = state['executions']['active'].pop(eid, None)
        if record is None:
            raise CommandRefused('unknown_execution', f'Execution {eid} is not active.',
                                 details={'execution_id': eid})
        record = {**record, 'status': 'interrupted_unknown', 'detected': st.now(),
                  'detected_revision': state['revision'] + 1,
                  'reason': 'Its process ended before promoting a result (orphaned lease). '
                            'Whether it computed anything is unknown; it is not restarted.'}
        state['executions']['interrupted'][eid] = record
        return {'execution_id': eid, 'activity': record['activity'],
                'status': 'interrupted_unknown', 'started_revision': record['started_revision']}
    return Handler(frozenset({'execution_id'}), run)


def _acknowledge(ctx: cmd.Context) -> Handler:
    def check(params):
        words = params['user_words']
        if not isinstance(words, str) or not words.strip():
            raise CommandRefused('invalid_arguments',
                                 'An acknowledgement records the junior\'s words (--user-words).')

    def run(state, params):
        eid = params['execution_id']
        record = state['executions']['interrupted'].pop(eid, None)
        if record is None:
            raise CommandRefused('unknown_execution',
                                 f'Execution {eid} has no unknown outcome to acknowledge.',
                                 details={'execution_id': eid,
                                          'interrupted': sorted(state['executions']['interrupted'])})
        return {'execution_id': eid, 'activity': record['activity'], 'status': 'acknowledged',
                'restarted': False, 'started_revision': record['started_revision'],
                'user_words': params['user_words'],
                'note': 'Acknowledged without restarting. Run the activity again with a new '
                        'request id only if the junior asks for it.'}
    return Handler(frozenset({'execution_id', 'user_words'}), run, check)


for _name, _factory in ((RESERVE, _reserve), (PROMOTE, _promote), (FAIL, _fail),
                        (RECOVER, _recover), (ACKNOWLEDGE, _acknowledge)):
    if _name not in cmd.ACTIONS:
        cmd.register_action(_name, _factory)


def _apply(store: StudyStore, state: dict, request_id: str, action: str, params: Mapping,
           expected_revision: int | None = None) -> dict:
    """Apply one action under the lock the caller holds, on the state it reread."""
    request = {'request_id': request_id,
               'expected_revision': state['revision'] if expected_revision is None
               else expected_revision, 'action': action, 'params': dict(params)}
    return reliability.apply_command(store, state, request,
                                     cmd.handlers(cmd.Context(store, request_id)))


# --- recovery ---------------------------------------------------------------------------

def _record_exposures(store: StudyStore, state: Mapping, eid: str, activity: str,
                      exposures, result_id: str | None, ids: list[str] | None = None) -> list[str]:
    ids = list(ids) if ids is not None else [exposure.new_exposure_id() for _ in exposures]
    for eid_x, x in zip(ids, exposures):
        exposure.record(store, exposure_id=eid_x, revision=state['revision'], activity=activity,
                        result_id=result_id, purpose=x['purpose'], partition=x['partition'],
                        row_keys=rec.parse_row_keys(store.read_blob(x['row_keys'])),
                        dataset_sha256=state['dataset']['sha256'], columns=x['columns'],
                        execution_id=eid)
    return ids


def recover(store: StudyStore, state: dict) -> list[str]:
    """Record every orphaned execution as ``interrupted_unknown`` (under the writer lock).

    Returns the execution ids recorded. Lease files without a reservation (a process
    that died before its reserve committed) are removed.
    """
    found = []
    for eid in sorted(state['executions']['active']):
        record = state['executions']['active'][eid]
        if lock.lease_is_held(lock.lease_path(store.study_dir, eid)):
            continue
        _apply(store, state, derived_request_id('recover', eid), RECOVER, {'execution_id': eid})
        _record_exposures(store, state, eid, record['activity'], record.get('exposures', []), None)
        store.event('interrupted_execution', execution_id=eid, activity=record['activity'])
        lock.remove_orphaned_lease(store.study_dir, eid)
        _history(store, eid, state['executions']['interrupted'][eid])
        found.append(eid)
    for orphan in lock.orphaned_leases(store.study_dir):
        if orphan['execution_id'] not in state['executions']['active']:
            Path(orphan['path']).unlink(missing_ok=True)
    return found


# --- outcomes ---------------------------------------------------------------------------

def _payload(store: StudyStore, *, action: str, request_id: str, replayed: bool, revision: int,
             activity: str | None, eid: str | None, status: str, result_id: str | None,
             result: Mapping | None) -> dict:
    values = None
    if result_id:
        try:
            values = registry.get(store, result_id)['output']['values']
        except StudyError:
            values = None
    return {'schema': SCHEMA, 'ok': True, 'study': str(store.study_dir), 'action': action,
            'request_id': request_id, 'replayed': replayed, 'revision': revision,
            'activity': activity, 'execution_id': eid, 'status': status, 'result_id': result_id,
            'values': values, 'result': dict(result or {}), 'artifacts': None}


def _outcome(store: StudyStore, payload: dict, *, render: bool) -> cmd.Outcome:
    code = cmd.EXIT_UNKNOWN_OUTCOME if payload['status'] == 'interrupted_unknown' else cmd.EXIT_OK
    if render and not payload['replayed']:
        artifacts = cmd.after_commit(store.study_dir, payload)
        if artifacts is not None:
            payload['artifacts'] = artifacts
            if code == cmd.EXIT_OK and any(a.get('status') in ('stale', 'failed')
                                           for a in artifacts.values()):
                code = cmd.EXIT_ARTIFACT_STALE
    return cmd.Outcome(payload, code)


def describe(store: StudyStore, state: Mapping, request_id: str, *,
             replayed: bool = True) -> dict:
    """The state of the execution created by ``request_id`` (for a replay).

    ``revision`` is the revision of its last step (promotion or failure), else of its
    reservation.
    """
    eid = execution_id(request_id)
    receipts = state['receipts']
    revision = receipts[request_id]['revision'] if request_id in receipts else state['revision']
    for step in ('promote', 'fail'):
        receipt = receipts.get(derived_request_id(step, request_id))
        if receipt is not None:
            r = receipt['result']
            return _payload(store, action='run', request_id=request_id, replayed=replayed,
                            revision=receipt['revision'], activity=r.get('activity'), eid=eid,
                            status=r['status'], result_id=r.get('result_id'), result=r)
    for bucket, status in (('active', 'running'), ('interrupted', 'interrupted_unknown'),
                           ('late', 'late_not_promoted')):
        record = state['executions'][bucket].get(eid)
        if record is not None:
            return _payload(store, action='run', request_id=request_id, replayed=replayed,
                            revision=revision, activity=record['activity'], eid=eid,
                            status=status, result_id=record.get('result_id'), result=record)
    history = _read_history(store, eid) or {}
    return _payload(store, action='run', request_id=request_id, replayed=replayed,
                    revision=revision, activity=history.get('activity'), eid=eid,
                    status=history.get('status', 'acknowledged'),
                    result_id=history.get('result_id'), result=history)


def _store(study_dir) -> StudyStore:
    store = StudyStore(study_dir)
    if not store.exists():
        raise StudyError('study_missing', f'No study here: {store.state_path} does not exist.',
                         details={'study': str(store.study_dir)})
    return store


Hook = Callable[[dict], None]


def run(study_dir, activity: str, options: Mapping | None, *, request_id: str,
        expected_revision: int, hooks: Mapping[str, Hook] | None = None) -> cmd.Outcome:
    """Run one activity (reserve, compute, promote) and describe the outcome.

    ``hooks`` (tests only) maps ``after_reserve`` and ``before_promote`` to callables
    that receive the plan.
    """
    act.guard_read_only()
    hooks = dict(hooks or {})
    store = _store(study_dir)
    activity = act.canonical(activity)
    options = act.normalize_options(activity, options)
    eid = execution_id(request_id)
    params = {'activity': activity, 'options': options, 'execution_id': eid}
    with store.writing() as state:
        recover(store, state)
        if request_id in state['receipts']:
            _apply(store, state, request_id, RESERVE, params, expected_revision)
            return _outcome(store, describe(store, state, request_id), render=False)
        if state['executions']['interrupted']:
            raise _interrupted_refusal(state)
        if expected_revision == state['revision']:
            shortcut = _already_current(store, state, activity, options, request_id)
            if shortcut is not None:
                return cmd.Outcome(shortcut)
        lease = lock.acquire_lease(store.study_dir, eid, activity=activity, request_id=request_id)
        try:
            receipt = _apply(store, state, request_id, RESERVE, params, expected_revision)
        except BaseException:
            lease.release()
            raise
        plan = _PLANS.pop(eid)
        _history(store, eid, state['executions']['active'][eid])
    try:
        if 'after_reserve' in hooks:
            hooks['after_reserve'](plan)
        output = act.compute(store, plan)
        if 'before_promote' in hooks:
            hooks['before_promote'](plan)
    except Exception as exc:
        with store.writing() as state:
            error = exc.to_dict() if hasattr(exc, 'to_dict') else {
                'code': 'internal_error', 'message': f'{type(exc).__name__}: {exc}'}
            _apply(store, state, derived_request_id('fail', request_id), FAIL,
                   {'execution_id': eid, 'error': error})
            _record_exposures(store, state, eid, activity, plan['exposures'], None)
            _history(store, eid, {**plan_summary(plan, eid), 'status': 'failed', 'error': error})
            lease.release()
        raise
    with store.writing() as state:
        # The entry names the exposure of the partition its values describe (the last
        # planned one: validation for a fit); every exposure carries the execution id.
        ids = [exposure.new_exposure_id() for _ in plan['exposures']]
        put = registry.put(store, activity=activity, params=plan['params'], inputs=plan['inputs'],
                           code=plan['code'], values=output['values'], blobs=output['blobs'],
                           partition=output['partition'], n_rows=output['n_rows'],
                           execution_id=eid, started_revision=plan['started_revision'],
                           exposure_id=ids[-1] if ids else None)
        exposure_ids = _record_exposures(store, state, eid, activity, plan['exposures'],
                                         put['result_id'], ids)
        receipt = _apply(store, state, derived_request_id('promote', request_id), PROMOTE,
                         {'execution_id': eid, 'result_id': put['result_id'],
                          'input_key': put['input_key']})
        result = {**receipt['result'], 'exposure_ids': exposure_ids,
                  'registry_created': put['created'], 'nondeterministic': put['nondeterministic']}
        _history(store, eid, {**plan_summary(plan, eid), **result})
        lease.release()
        payload = _payload(store, action='run', request_id=request_id, replayed=False,
                           revision=state['revision'], activity=activity, eid=eid,
                           status=result['status'], result_id=put['result_id'], result=result)
    return _outcome(store, payload, render=True)


def plan_summary(plan: Mapping, eid: str) -> dict:
    return {'execution_id': eid, 'activity': plan['activity'], 'options': plan['options'],
            'input_key': plan['input_key'], 'started_revision': plan['started_revision']}


def _already_current(store, state, activity, options, request_id) -> dict | None:
    slot = act.slot_of(activity, options)
    rid = state['current'].get(slot)
    if rid is None or not st.is_current(state, slot):
        return None
    try:
        now = act.plan(store, state, activity, options)
        entry = registry.get(store, rid)
    except (CommandRefused, StudyError):
        return None
    if entry['input_key'] != now['input_key']:
        return None
    return _payload(store, action='run', request_id=request_id, replayed=False,
                    revision=state['revision'], activity=activity, eid=entry['execution_id'],
                    status='already_current', result_id=rid,
                    result={'input_key': now['input_key'],
                            'note': 'The current result already answers this request on the '
                                    'current state; nothing was computed.'})


def acknowledge(study_dir, execution: str, *, request_id: str, expected_revision: int,
                user_words: str) -> cmd.Outcome:
    """Acknowledge an interrupted execution with the junior's words; never restarts it."""
    store = _store(study_dir)
    with store.writing() as state:
        recover(store, state)
        receipt = _apply(store, state, request_id, ACKNOWLEDGE,
                         {'execution_id': execution, 'user_words': user_words},
                         expected_revision)
        replayed = bool(receipt.get('replayed'))
        r = receipt['result']
        if not replayed:
            history = _read_history(store, execution) or {}
            _history(store, execution, {**history, **r, 'acknowledged_revision': receipt['revision']})
        payload = _payload(store, action=ACKNOWLEDGE, request_id=request_id, replayed=replayed,
                           revision=receipt['revision'], activity=r['activity'], eid=execution,
                           status='acknowledged', result_id=None, result=r)
    return _outcome(store, payload, render=True)
