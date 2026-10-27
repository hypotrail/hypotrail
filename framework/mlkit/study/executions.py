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
read-only and takes no writer lock: it probes the leases (``lock.probe_leases``) and
reports a dead execution under ``executions.suspected_interrupted`` with liveness
``outcome_unknown`` (never as running) until the next ``run`` records it (F1).

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

import contextlib
import hashlib
import io
import logging
import os
import warnings
from pathlib import Path
from typing import Callable, Mapping, TextIO

from mlkit import reliability
from mlkit.reliability import CommandRefused, Handler

from . import activities as act
from . import commands as cmd
from . import dependencies as dep
from . import exposure, guard, lock, partition, progress as progress_mod, registry
from . import records as rec
from . import state as st
from .errors import StudyError
from .store import StudyStore, atomic_write_json

SCHEMA = 'hypotrail.run/1'
PAYLOAD_KEYS = ('schema', 'ok', 'study', 'action', 'request_id', 'replayed', 'revision',
                'activity', 'execution_id', 'status', 'result_id', 'values', 'result',
                'artifacts',
                # v0.3 (WP-J): the next action after the run, as status gives it.
                'next_action',
                # L3 (owner session 2026-10-26, R4): the question the result answers, in the
                # study language (``values.question`` stays the stored English), or null.
                'question_junior')
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
        if activity == act.FINAL and st.final_test_opened(state):
            # Before planning: once opened, the plan's own refusals (a capture no longer
            # current) would name a remedy that no longer exists.
            raise cmd.final_test_opened_refusal(state)
        if activity == act.FINAL:
            # Review round 3 (E3-3): every result the opening rests on (the split, the fits,
            # the variants, the evaluation, the diagnostics under review-v1) is current by the
            # rule of ``status`` before anything is marked opened; the plan checks the capture
            # (E2-1) and that it loads (A F1). Review round 4 (E4-1): and the whole rule of the
            # confirmation holds now (the stale map, the configuration the study chooses now,
            # nothing to confirm again, the confirmation itself), so a confirmed final test
            # whose opening did not run never opens on evidence or a choice that changed.
            from . import assurance, preconditions
            # The profile's refusals keep their place first (as in the plan).
            assurance.require_activity(state, activity)
            preconditions.refuse_missing(preconditions.opening_missing(state, ctx.store),
                                         'Opening the final test')
        if activity == act.DIAG_FINAL and st.final_test_opened(state):
            # Review round 3 (E3-4): the final evaluation the diagnostics read is never
            # recomputed; when it is not current, say so before the plan names a remedy (run
            # it again) that no longer exists.
            final = state['current'].get(act.FINAL)
            if final is not None:
                from . import read
                currency = read.Study.at_state(ctx.store.study_dir, state).currency(final)
                if not currency['current']:
                    raise _not_recomputable(state, activity, state['current'].get(activity),
                                            currency, final_currency=True)
        plan = act.plan(ctx.store, state, activity, params['options'], with_exposure=True)
        eid = params['execution_id']
        for other, running in sorted(state['executions']['active'].items()):
            if running['slot'] == plan['slot'] and running['input_key'] == plan['input_key']:
                # L7: the same computation is already running; never compute it twice.
                raise CommandRefused('execution_in_progress',
                                     f'{plan["slot"]} is already being computed on these inputs '
                                     f'by execution {other}. Wait for it, then read status.',
                                     details={'execution_id': other, 'slot': plan['slot'],
                                              'activity': running['activity'],
                                              'started_revision': running['started_revision']})
        revision = state['revision'] + 1
        if activity == act.FINAL:
            # WP-B1: the final test is opened here, before any of its rows is read, so the
            # one evaluation can never be scored twice (an interrupted one consumes it too).
            if plan['inputs'].get('predictor'):
                # Review round 2 (A F1): the captured predictor is loaded as the evaluation
                # will load it (bundle, environment, parity rows) before the opening is
                # recorded; a refusal leaves the final test sealed. The plan already checked
                # that the capture is current by the rule of ``status`` (E2-1).
                from mlkit.contracts import capture
                capture.require_loadable(ctx.store, state, plan['inputs']['predictor'])
            config = state['decisions'][st.FINAL_TEST]['value'] or {}
            conf = state['decisions'][st.FINAL_TEST]['confirmation'] or {}
            state['partition']['status'] = partition.OPENED
            state['partition']['opening'] = partition.open_record(
                revision=revision, execution_id=eid, proposal_id=conf.get('proposal_id'),
                user_words=conf.get('user_words'), model=config.get('model'),
                rule=config.get('rule'), time=st.now(),
                # L9 (ADR 0006 amendment): the demo's automatic opening says so, for good.
                basis=st.AUTOMATIC if st.confirmation_basis(conf) == st.AUTOMATIC else None)
        record = {'execution_id': eid, 'activity': activity, 'slot': plan['slot'],
                  'options': plan['options'], 'request_id': ctx.request_id, 'status': 'running',
                  'started_revision': revision, 'started': st.now(),
                  'input_key': plan['input_key'], 'code_fingerprint': plan['code']['fingerprint'],
                  'exposures': plan['exposures'],
                  'lease': str(lock.lease_path(ctx.store.study_dir, eid))}
        state['executions']['active'][eid] = record
        if activity == act.POLICY_INSPECT:
            state.setdefault('exploration', {'events': {}})['events'][eid] = {
                'event_id': eid, 'status': 'reserved', 'request_id': ctx.request_id,
                'revision': revision, 'time': record['started'],
                'rules': list(plan['params']['rules']),
                'query_count': len(plan['params']['rules']),
                'result_id': None,
            }
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
        if record['activity'] == act.POLICY_INSPECT:
            event = state.setdefault('exploration', {'events': {}})['events'][eid]
            event.update(status='completed', result_id=rid, finished=done['finished'],
                         finished_revision=done['finished_revision'])
        opening = (state.get('partition') or {}).get('opening')
        if record['activity'] == act.FINAL and opening \
                and opening.get('execution_id') == eid:
            opening['result_id'] = rid      # WP-B1: the one evaluation of the final test
        if reason is None:
            slot = record['slot']
            previous = state['current'].get(slot)
            state['current'][slot] = rid
            state['stale'].pop(rid, None)
            done.update(status='promoted', replaced=previous if previous != rid else None)
            if previous and previous != rid and slot != act.POLICY_INSPECTION:
                # H2: what was computed from the replaced result no longer holds.
                code_changed = (registry.get(ctx.store, previous)['code']['fingerprint']
                                != record['code_fingerprint'])
                invalidation = dep.apply_replacement(
                    state, slot, previous, rid, revision=state['revision'] + 1,
                    store=ctx.store, code_changed=code_changed)
                if invalidation is not None and (invalidation['stale_results']
                                                 or invalidation['reconfirm_required']):
                    done['invalidation'] = {k: invalidation[k] for k in (
                        'mutation', 'row', 'reason', 'stale_results', 'stale_slots',
                        'reconfirm_required')}
        else:
            done.update(status='late_not_promoted', reason=reason,
                        current_input_key=now['input_key'] if now else None)
            state['executions']['late'][eid] = done
        return {'execution_id': eid, 'activity': record['activity'], 'slot': record['slot'],
                'status': done['status'], 'result_id': rid, 'input_key': params['input_key'],
                'reason': reason, 'started_revision': record['started_revision'],
                'invalidation': done.get('invalidation')}
    return Handler(frozenset({'execution_id', 'result_id', 'input_key'}), run)


def _fail(ctx: cmd.Context) -> Handler:
    def run(state, params):
        eid = params['execution_id']
        record = state['executions']['active'].pop(eid, None)
        if record is None:
            raise CommandRefused('unknown_execution', f'Execution {eid} is not active.',
                                 details={'execution_id': eid})
        if record['activity'] == act.POLICY_INSPECT:
            event = state.setdefault('exploration', {'events': {}})['events'][eid]
            event.update(status='failed', error=params['error'], finished=st.now(),
                         finished_revision=state['revision'] + 1)
        out = {'execution_id': eid, 'activity': record['activity'], 'status': 'failed',
               'error': params['error'], 'started_revision': record['started_revision']}
        part = state.get('partition') or {}
        opening = part.get('opening') or {}
        if params.get('final_test_unread') and record['activity'] == act.FINAL \
                and opening.get('execution_id') == eid and opening.get('result_id') is None:
            # Review round 2 (A F1): the evaluation failed before it read any final-test row
            # (its captured predictor was refused when loaded): the opening it recorded is
            # withdrawn and the final test is sealed again; no final-test exposure was
            # recorded. The confirmation of ``final_test`` stands.
            part['status'] = 'sealed'
            part.pop('opening', None)
            out['final_test'] = 'sealed'
        return out
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
        if record['activity'] == act.POLICY_INSPECT:
            event = state.setdefault('exploration', {'events': {}})['events'][eid]
            event.update(status='outcome_unknown', detected=record['detected'],
                         detected_revision=record['detected_revision'])
        return {'execution_id': eid, 'activity': record['activity'],
                'status': 'interrupted_unknown', 'started_revision': record['started_revision']}
    return Handler(frozenset({'execution_id'}), run)


def _acknowledge(ctx: cmd.Context) -> Handler:
    def check(params):
        words = params['user_words']
        if not isinstance(words, str) or not words.strip():
            raise CommandRefused('invalid_arguments',
                                 'An acknowledgement records the junior\'s words (--user-words).')
        # L5: the same rule as a confirmation; a refusal or a bare "ok" acknowledges nothing.
        reason = cmd.reply_problem(words)
        if reason is not None:
            raise CommandRefused('ambiguous_confirmation', cmd.REPLY_MESSAGES[reason],
                                 details={'reason': reason, 'user_words': words})

    def run(state, params):
        eid = params['execution_id']
        record = state['executions']['interrupted'].get(eid)
        if record is None:
            raise CommandRefused('unknown_execution',
                                 f'Execution {eid} has no unknown outcome to acknowledge.',
                                 details={'execution_id': eid,
                                          'interrupted': sorted(state['executions']['interrupted'])})
        # The words must be about this interruption: its activity, or its unknown outcome.
        if cmd.reply_problem(params['user_words'], value=record['activity'],
                             topic=cmd.ACKNOWLEDGEMENT_TOPIC) == 'unrelated_reply':
            raise CommandRefused('ambiguous_confirmation',
                                 'These words do not mention the interrupted activity or its '
                                 'unknown outcome. Tell the junior what happened and record '
                                 'their reply.',
                                 details={'reason': 'unrelated_reply', 'execution_id': eid,
                                          'activity': record['activity'],
                                          'user_words': params['user_words']})
        state['executions']['interrupted'].pop(eid)
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
    available = cmd.handlers(cmd.Context(store, request_id))
    optional = OPTIONAL_PARAMS.get(action, frozenset()) & set(params)
    if optional and action in available:
        handler = available[action]
        available[action] = Handler(handler.params | optional, handler.run, handler.check)
    return reliability.apply_command(store, state, request, available)


# v0.3 (WP-J, R35): the channel a run or an acknowledgement came from, recorded only when it
# is not the chat, so every earlier request keeps its identity (a replay stays a replay).
OPTIONAL_PARAMS = {RESERVE: frozenset({'channel'}), ACKNOWLEDGE: frozenset({'channel'}),
                   # Review round 2 (A F1): a final evaluation that failed before reading any
                   # final-test row (only then is it given).
                   FAIL: frozenset({'final_test_unread'})}


def channel_param(channel: str | None) -> dict:
    """``{'channel': channel}`` for a channel other than the chat (checked), else ``{}``."""
    if channel in (None, cmd.DEFAULT_CHANNEL):
        return {}
    cmd.check_channel(channel)
    return {'channel': channel}


# --- recovery ---------------------------------------------------------------------------

def _record_exposures(store: StudyStore, state: Mapping, eid: str, activity: str,
                      exposures, result_id: str | None, ids: list[str] | None = None,
                      *, once: bool = False) -> list[str]:
    """Record the planned exposures of execution ``eid``.

    ``once``: record nothing when the execution already has exposure records (a
    recovery or failure retried after a process died between recording and committing,
    or a promotion that recorded them before dying). Exposure is recorded **before**
    the commit that closes the execution, so a crash can duplicate the attempt but never
    lose the rows (review fix M2).
    """
    if once and any(r.get('execution_id') == eid for r in exposure.records(store)):
        return []
    ids = list(ids) if ids is not None else [exposure.new_exposure_id() for _ in exposures]
    for eid_x, x in zip(ids, exposures):
        exposure.record(store, exposure_id=eid_x, revision=state['revision'], activity=activity,
                        result_id=result_id, purpose=x['purpose'], partition=x['partition'],
                        row_keys=rec.parse_row_keys(store.read_blob(x['row_keys'])),
                        dataset_sha256=state['dataset']['sha256'], columns=x['columns'],
                        execution_id=eid)
    return ids


def recover(store: StudyStore, state: dict, hooks: Mapping | None = None) -> list[str]:
    """Record every orphaned execution as ``interrupted_unknown`` (under the writer lock).

    Returns the execution ids recorded. Lease files without a reservation (a process
    that died before its reserve committed) are removed.
    """
    found = []
    for eid in sorted(state['executions']['active']):
        record = state['executions']['active'][eid]
        if lock.lease_is_held(lock.lease_path(store.study_dir, eid)):
            continue
        _record_exposures(store, state, eid, record['activity'], record.get('exposures', []), None,
                          once=True)
        if 'recover_kill' in (hooks or {}):
            hooks['recover_kill'](record)
        _apply(store, state, derived_request_id('recover', eid), RECOVER, {'execution_id': eid})
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
    result = dict(result or {})
    late = status == 'late_not_promoted'
    if late:
        # L6: stored, never promoted: its values describe a state that no longer holds.
        result['citable'] = False
    if result_id and not late:
        try:
            values = registry.get(store, result_id)['output']['values']
        except StudyError:
            values = None
    return {'schema': SCHEMA, 'ok': True, 'study': str(store.study_dir), 'action': action,
            'request_id': request_id, 'replayed': replayed, 'revision': revision,
            'activity': activity, 'execution_id': eid, 'status': status, 'result_id': result_id,
            'values': values, 'result': result, 'artifacts': None}


def _outcome(store: StudyStore, payload: dict, *, render: bool,
             reporter: progress_mod.Reporter | None = None) -> cmd.Outcome:
    code = cmd.EXIT_UNKNOWN_OUTCOME if payload['status'] == 'interrupted_unknown' else cmd.EXIT_OK
    if render and not payload['replayed']:
        with progress_mod.phase_of(reporter, 'deliverables'):
            artifacts = cmd.after_commit(store.study_dir, payload)
        if artifacts is not None:
            payload['artifacts'] = artifacts
            if code == cmd.EXIT_OK and any(a.get('status') in ('stale', 'failed')
                                           for a in artifacts.values()):
                code = cmd.EXIT_ARTIFACT_STALE
    # v0.3 (WP-J): the next action after the run, as ``status`` gives it; R1b (2026-10-26):
    # with what the run produced, for ``next_action.panel.shown``.
    produced = {'command': 'run', 'action': payload['action'], 'activity': payload['activity'],
                'slot': (payload['result'] or {}).get('slot'), 'status': payload['status'],
                # Contract P1 (§17.1.1): a chart that read no target is filed under the
                # structural step.
                'target_read': _target_read(payload)}
    payload['next_action'] = cmd.refreshed_next_action(store.study_dir, produced)
    from . import l10n
    payload['question_junior'] = l10n.question_junior(
        payload['values'], (payload['next_action'] or {}).get('language') or l10n.EN)
    return cmd.Outcome(payload, code)


def _target_read(payload: Mapping) -> bool | None:
    """Whether a run's result read the target: its ``target_read`` value, or for a
    distribution whether its column is the target; None when the result does not say."""
    values = payload.get('values') if isinstance(payload.get('values'), Mapping) else {}
    if isinstance(values.get('target_read'), bool):
        return values['target_read']
    if str(payload.get('activity') or '') == 'eda.distribution' and values.get('role'):
        return values['role'] == 'target'
    return None


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


# Third session of 2026-10-26: the journey now captures the chosen model (with the MLflow
# workshop package) before the opening, so a CLI run of ``predictor.capture`` or of the
# final evaluation that loads it wrote MLflow's warnings, log lines and download progress
# bars on stderr, where a handled outcome writes nothing (CLI-CONTRACT, NR-17) and the
# junior's agent reads ``--progress`` lines. The packaging module is fingerprinted, so the
# noise is silenced here, around the computation only: Python warnings, the ``mlflow``
# loggers, the artifact progress bar, and stray writes to ``sys.stderr``. The ``--progress``
# reporter keeps the stream it was given; a failure is still raised and recorded.
QUIET_ACTIVITIES = (act.CAPTURE, act.FINAL)
_PROGRESS_BAR_ENV = 'MLFLOW_ENABLE_ARTIFACTS_PROGRESS_BAR'


@contextlib.contextmanager
def _quiet_packaging(activity: str):
    if activity not in QUIET_ACTIVITIES:
        yield
        return
    logger = logging.getLogger('mlflow')
    level, previous = logger.level, os.environ.get(_PROGRESS_BAR_ENV)
    os.environ[_PROGRESS_BAR_ENV] = 'false'
    logger.setLevel(logging.ERROR)
    try:
        with warnings.catch_warnings(), contextlib.redirect_stderr(io.StringIO()):
            warnings.simplefilter('ignore')
            yield
    finally:
        logger.setLevel(level)
        if previous is None:
            os.environ.pop(_PROGRESS_BAR_ENV, None)
        else:
            os.environ[_PROGRESS_BAR_ENV] = previous


def run(study_dir, activity: str, options: Mapping | None, *, request_id: str,
        expected_revision: int, hooks: Mapping[str, Hook] | None = None,
        render: bool = True, channel: str | None = None, progress: TextIO | None = None,
        progress_interval: float = progress_mod.HEARTBEAT_SECONDS) -> cmd.Outcome:
    """Run one activity (reserve, compute, promote) and describe the outcome.

    ``hooks`` (tests only) maps ``after_reserve`` and ``before_promote`` to callables
    that receive the plan. ``render`` False leaves the deliverables to the caller (the
    opening of the final test renders once, after the confirmation it follows).
    ``progress`` (``run --progress``: stderr) receives the progress lines of the computation
    and of the deliverables, in the study language (:mod:`mlkit.study.progress`); nothing is
    written to it otherwise, and the returned payload is the same.
    """
    act.guard_read_only()
    hooks = dict(hooks or {})
    store = _store(study_dir)
    requested = activity if ':' in str(activity) or not (options or {}).get('column') \
        else f'{activity}:{options["column"]}'
    activity, options = act.resolve(activity, options)    # v0.3 (WP-F1): fit.variant:2
    activity = act.canonical(activity)
    options = act.normalize_options(activity, options)
    eid = execution_id(request_id)
    with store.writing() as state:
        # Contract P1.9: a study created before the step-1 sample records its look on its
        # first write, before the write's own work (once per seed).
        exposure.ensure_sample(store, state)
        if activity == act.CAPTURE and not options:
            # Round 5 (review E, R5E-3): a capture run again without --profile or --packager
            # keeps the options of the capture it replaces, so an MLflow package is never
            # dropped by a re-capture; give --profile base to capture without one.
            options = capture_options(store, state)
        params = {'activity': activity, 'options': options, 'execution_id': eid,
                  **channel_param(channel)}
        recover(store, state, hooks)
        if request_id in state['receipts']:
            _apply(store, state, request_id, RESERVE, params, expected_revision)
            return _outcome(store, describe(store, state, request_id), render=False)
        if state['executions']['interrupted']:
            raise _interrupted_refusal(state)
        if expected_revision == state['revision'] and activity != act.POLICY_INSPECT:
            shortcut = _already_current(store, state, activity, options, request_id)
            if shortcut is not None:
                return _outcome(store, shortcut, render=False)
        lease = lock.acquire_lease(store.study_dir, eid, activity=activity, request_id=request_id)
        try:
            receipt = _apply(store, state, request_id, RESERVE, params, expected_revision)
        except BaseException:
            lease.release()
            raise
        plan = _PLANS.pop(eid)
        _history(store, eid, state['executions']['active'][eid])
        reporter = (progress_mod.Reporter(progress, st.language_of(state),
                                          interval=progress_interval)
                    if progress is not None else None)
    try:
        if 'after_reserve' in hooks:
            hooks['after_reserve'](plan)
        with progress_mod.phase_of(reporter, 'activity', requested), \
                _quiet_packaging(activity):
            output = act.compute(store, plan)
            if 'during_compute' in hooks:
                hooks['during_compute'](plan)
        if 'before_promote' in hooks:
            hooks['before_promote'](plan)
    except Exception as exc:
        with store.writing() as state:
            error = exc.to_dict() if hasattr(exc, 'to_dict') else {
                'code': 'internal_error', 'message': f'{type(exc).__name__}: {exc}'}
            # Review round 2 (A F1): a final evaluation that failed before reading any
            # final-test row records only the rows it read, and the opening is withdrawn.
            # (``capture.FINAL_TEST_ROWS_READ``; capture is not imported for other runs.)
            unread = activity == act.FINAL and isinstance(exc, StudyError) \
                and exc.details.get('final_test_rows_read') is False
            exposures = [x for x in plan['exposures']
                         if not (unread and x['partition'] == partition.FINAL_TEST)]
            _record_exposures(store, state, eid, activity, exposures, None, once=True)
            if 'fail_kill' in hooks:
                hooks['fail_kill'](plan)
            _apply(store, state, derived_request_id('fail', request_id), FAIL,
                   {'execution_id': eid, 'error': error,
                    **({'final_test_unread': True} if unread else {})})
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
        if activity == act.FINAL and plan['inputs'].get('predictor') \
                and result.get('status') == 'promoted':
            # Library integration v1: the evaluated predictor's evidence binding, written
            # beside its bundle once the result exists (the hashed bundle is not modified).
            from mlkit.contracts import capture
            try:
                capture.bind_evidence(store, plan, put['result_id'], state['revision'])
                result['evidence_binding'] = 'written'
            except Exception as exc:          # noqa: BLE001 - derived, re-creatable record
                result['evidence_binding'] = f'failed: {type(exc).__name__}: {exc}'
        _history(store, eid, {**plan_summary(plan, eid), **result})
        lease.release()
        payload = _payload(store, action='run', request_id=request_id, replayed=False,
                           revision=state['revision'], activity=activity, eid=eid,
                           status=result['status'], result_id=put['result_id'], result=result)
    return _outcome(store, payload, render=render, reporter=reporter)


def capture_options(store, state: Mapping) -> dict:
    """Round 5 (review E, R5E-3): the options of the study's current capture (``profile``
    other than the default, ``packager``), as ``run`` takes them; ``{}`` when the study holds
    no capture or its entry cannot be read. A re-capture defaults to them."""
    rid = state['current'].get(act.CAPTURE)
    if rid is None:
        return {}
    try:
        params = registry.get(store, rid).get('params') or {}
    except StudyError:
        return {}
    from .view import capture_options as options_of      # the one rule, read side too
    return act.normalize_options(act.CAPTURE, options_of(params))


def plan_summary(plan: Mapping, eid: str) -> dict:
    return {'execution_id': eid, 'activity': plan['activity'], 'options': plan['options'],
            'input_key': plan['input_key'], 'started_revision': plan['started_revision']}


def _already_current(store, state, activity, options, request_id) -> dict | None:
    """The ``already_current`` answer to a request the slot's result answers, or None.

    Review round 2 (E2-2, E2-3): the result must be current by the rule ``status`` and
    ``evidence`` use (:meth:`mlkit.study.read.Study.currency`: stale map, code changed under
    the code attestations, upstream), and it answers the request when the request's plan has
    its params and inputs and the same modules, each with the digest the result recorded or
    one an exact attestation declares equivalent for this activity (the rule of
    ``code_changed``). An unattested change of any module, a different module set or any
    other input is a new request. A result that is not current and cannot be recomputed
    (the final test is opened once) is refused with that reason, never ``already_current``.
    """
    from . import read
    slot = act.slot_of(activity, options)
    rid = state['current'].get(slot)
    snapshot = read.Study.at_state(store.study_dir, state)
    if activity == act.FINAL and st.final_test_opened(state) and rid is not None:
        currency = snapshot.currency(rid)
        if not currency['current']:
            raise _not_recomputable(state, act.FINAL, rid, currency)
    if rid is None or not st.is_current(state, slot):
        return None
    try:
        now = act.plan(store, state, activity, options)
        entry = registry.get(store, rid)
    except (CommandRefused, StudyError):
        return None
    if not _answers(snapshot, entry, now):
        return None
    if activity == act.CAPTURE and not st.final_test_opened(state):
        # Round 5 (review E, R5E-2): a capture the final evaluation could not load (another
        # runtime installed, an altered bundle, another environment) does not answer the
        # request, whatever its fingerprint says: it is computed again.
        from mlkit.contracts import capture
        if capture.loading_problem(store, state) is not None:
            return None
    currency = snapshot.currency(rid)
    if not currency['current']:
        final = state['current'].get(act.FINAL)
        if activity == act.DIAG_FINAL and final in ((currency['reason'] or {})
                                                    .get('upstream_not_current') or []):
            # Recomputing gives the same result: the final evaluation it reads is not
            # current and is never recomputed.
            raise _not_recomputable(state, activity, rid, currency)
        return None
    return _payload(store, action='run', request_id=request_id, replayed=False,
                    revision=state['revision'], activity=activity, eid=entry['execution_id'],
                    status='already_current', result_id=rid,
                    result={'input_key': entry['input_key'],
                            'note': 'The current result already answers this request on the '
                                    'current state; nothing was computed.'})


def _answers(snapshot, entry: Mapping, now: Mapping) -> bool:
    """Whether the registry ``entry`` answers the request planned as ``now`` (E2-3)."""
    if entry['input_key'] == now['input_key']:
        return True
    if entry['activity'] != now['activity'] \
            or set(entry['code']['modules']) != set(now['code']['modules']):
        return False
    same_inputs = rec.input_key(now['activity'], act.rec_json(now['params']),
                                act.rec_json(now['inputs']),
                                entry['code']['fingerprint']) == entry['input_key']
    return same_inputs and not snapshot.code_changed(entry)


def _not_recomputable(state: Mapping, activity: str, rid: str | None,
                      currency: Mapping | None, *, final_currency: bool = False
                      ) -> CommandRefused:
    """E2-2: a final-test result that is not current, after the opening: it cannot be
    recomputed, so the request is refused with the reason instead of ``already_current``.

    Review round 3 (E3-4): with ``final_currency``, ``currency`` is that of the final
    evaluation ``diag.final_test`` would read (``rid`` is the diagnostics result, None when
    there is none yet); the junior message is in the study language."""
    reason = (currency or {}).get('reason') or {}
    why = reason.get('reason') or 'not current'
    opening = (state.get('partition') or {}).get('opening') or {}
    fr = st.language_of(state) == 'fr'
    if activity == act.FINAL:
        message = (f'The final evaluation is not current ({why}) and cannot be recomputed: the '
                   'final test was already opened, and it is opened once. Its recorded figures '
                   'stay as history, shown as not current.')
        junior = ("Votre résultat sur l'échantillon de test final n'est plus à jour et ne peut "
                  "pas être recalculé : le test final ne s'ouvre qu'une fois. Ses chiffres "
                  "restent dans l'étude comme historique, marqués comme n'étant plus à jour."
                  if fr else
                  'Your final-test result is no longer current and cannot be computed again: '
                  'the final test is opened only once. Its figures stay in the study as '
                  'history, marked not current.')
        code = 'final_test_already_opened'
    elif final_currency:
        message = (f'{activity} cannot be computed: the final evaluation it reads is not '
                   f'current ({why}) and cannot be recomputed, since the final test was already '
                   'opened and it is opened once. Its recorded figures stay as history, shown '
                   'as not current.')
        junior = ("Les diagnostics du test final ne peuvent pas être calculés : le résultat "
                  "sur l'échantillon de test final qu'ils lisent n'est plus à jour, et il ne "
                  "peut pas être recalculé, car le test final ne s'ouvre qu'une fois. Ses "
                  "chiffres restent dans l'étude comme historique, marqués comme n'étant plus "
                  "à jour." if fr else
                  'The final-test diagnostics cannot be computed: the final-test result they '
                  'read is no longer current, and it cannot be computed again, since the final '
                  'test is opened only once. Its figures stay in the study as history, marked '
                  'not current.')
        code = 'precondition_missing'
    else:
        message = (f'{activity} is not current ({why}) and recomputing it cannot make it '
                   'current: the final evaluation it reads is not current and is never '
                   'recomputed (the final test is opened once).')
        junior = ("Les diagnostics du test final ne sont plus à jour, car le résultat sur "
                  "l'échantillon de test final qu'ils lisent ne l'est plus ; ce résultat ne "
                  "peut pas être recalculé, car le test final ne s'ouvre qu'une fois."
                  if fr else
                  'The final-test diagnostics are not current because the final-test result '
                  'they read is no longer current; that result cannot be computed again, since '
                  'the final test is opened only once.')
        code = 'precondition_missing'
    details = {'slot': activity, 'result_id': rid, 'current': False, 'stale_reason': why,
               'code_changed': list(reason.get('code_changed') or []),
               'upstream_not_current': list(reason.get('upstream_not_current') or []),
               'opening': {k: opening.get(k) for k in ('revision', 'model', 'rule',
                                                       'result_id')},
               'junior_message': junior}
    if final_currency:
        # The reason is the final evaluation's (the diagnostics may not exist yet).
        details['final_result_id'] = state['current'].get(act.FINAL)
        details['delayed_labels_included'] = bool(reason.get('delayed_labels_included'))
    if code == 'precondition_missing':
        details['missing'] = [{'requirement': 'result_current', 'slot': act.FINAL,
                               'detail': 'The final evaluation is not current and is never '
                                         'recomputed.'}]
    return CommandRefused(code, message, details=details)


def acknowledge(study_dir, execution: str, *, request_id: str, expected_revision: int,
                user_words: str, channel: str | None = None) -> cmd.Outcome:
    """Acknowledge an interrupted execution with the junior's words; never restarts it."""
    guard.assert_writable()
    store = _store(study_dir)
    with store.writing() as state:
        read_revision = state['revision']
        if recover(store, state) and expected_revision == read_revision:
            # F1: ``status`` showed this execution as ``outcome_unknown`` at the revision
            # the client read; recording it as interrupted is not a change the client
            # missed, so the acknowledgement applies to the revision recovery produced.
            expected_revision = state['revision']
        receipt = _apply(store, state, request_id, ACKNOWLEDGE,
                         {'execution_id': execution, 'user_words': user_words,
                          **channel_param(channel)},
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
