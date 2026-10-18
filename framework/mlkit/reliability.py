"""Revisioned local commands and durable log; requires the writer lock.
This mechanism confines no agent and manages no remote jobs.

``apply_command(store, state, request, handlers)`` is the generic core: it knows
nothing about the legacy pilot or about ``.hypotrail`` studies. A store provides
persistence (transaction file, commit, events, revision log); handlers provide the
actions. ``apply(pilot, state, request)`` and ``recover(pilot, state)`` keep their
historical behaviour through :class:`PilotStore`.

Importing this module loads no other ``mlkit`` module, so the junior study package
(``mlkit.study``) can use it without pulling the legacy pilot.
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import json
import os
import platform
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
from importlib.metadata import version, PackageNotFoundError


def provenance(root):
    root = Path(root)
    hashes = {}
    for folder in ['mlkit', 'model', 'scripts']:
        for path in sorted((root / folder).glob('*.py')):
            hashes[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    for path in sorted(Path(__file__).parent.glob('*.py')):
        hashes['kit/' + path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    packages = {}
    for name in ['numpy', 'pandas', 'scikit-learn', 'marimo']:
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    environment = {'python': sys.version, 'platform': platform.platform(), 'packages': packages}
    return {'code': hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(),
            'environment': hashlib.sha256(json.dumps(environment, sort_keys=True).encode()).hexdigest(),
            'versions': environment}


# --- generic command core ---------------------------------------------------------------

REQUEST_KEYS = frozenset({'request_id', 'expected_revision', 'action', 'params'})
MAX_REQUEST_ID_LENGTH = 200


class CommandRefused(ValueError):
    """A command refused without effect. ``to_dict()`` is the machine-readable form.

    Stable codes: ``invalid_request``, ``idempotency_conflict``, ``stale_revision``,
    ``invalid_command``, plus any code a handler's ``check`` raises.
    """

    def __init__(self, code: str, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        out = {'code': self.code, 'message': self.message}
        if self.details:
            out['details'] = self.details
        return out


@dataclass(frozen=True)
class Handler:
    """One action accepted by :func:`apply_command`.

    ``params`` is the exact set of parameter names. ``check(params)`` runs before any
    write and raises to refuse. ``run(state, params)`` mutates ``state`` in memory and
    returns the result recorded in the receipt; it must not commit state itself.
    """

    params: frozenset
    run: Callable[[dict, dict], Any]
    check: Callable[[dict], None] | None = None


def request_signature(request: Mapping) -> str:
    """SHA-256 of the canonical JSON of the whole request, the idempotency signature."""
    return hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()


def rollback_transaction(store, state) -> bool:
    """Undo an uncommitted transaction left by an interrupted command.

    Saving state is the commit point: a transaction whose request has a receipt in
    ``state`` committed, and its file is only removed. Returns True if one was found.
    """
    row = store.read_transaction()
    if row is None:
        return False
    if row['request_id'] not in state.get('receipts', {}):
        for name, content in row['before_files'].items():
            store.restore_file(name, content)
        store.event('transaction_rolled_back', request_id=row['request_id'])
    store.clear_transaction()
    return True


def _check_request(state: dict, request: Any):
    """Validate ``request`` and return ``(signature, receipt or None)``.

    The order matters: a replay is recognised before the revision check, so a client
    that retries after a timeout gets its receipt even if other commands followed.
    """
    if not isinstance(request, Mapping) or set(request) != REQUEST_KEYS:
        keys = set(request) if isinstance(request, Mapping) else set()
        raise CommandRefused('invalid_request',
                             'Command: request_id, expected_revision, action, params required',
                             details={'missing': sorted(REQUEST_KEYS - keys),
                                      'unexpected': sorted(map(str, keys - REQUEST_KEYS))})
    key = request['request_id']
    if not isinstance(key, str) or not key.strip() or len(key) > MAX_REQUEST_ID_LENGTH:
        raise CommandRefused('invalid_request', 'Invalid idempotency key',
                             details={'field': 'request_id'})
    signature = request_signature(request)
    receipt = state.get('receipts', {}).get(key)
    if receipt:
        if receipt['signature'] != signature:
            raise CommandRefused('idempotency_conflict',
                                 'Idempotency key already used for a different command',
                                 details={'request_id': key, 'revision': receipt['revision']})
        return signature, receipt
    expected = request['expected_revision']
    if type(expected) is not int:
        raise CommandRefused('invalid_request', 'expected_revision must be an integer',
                             details={'field': 'expected_revision'})
    return signature, None


def _check_revision(store, state: dict, request: Mapping) -> None:
    current = state.get('revision', 0)
    expected = request['expected_revision']
    if expected != current:
        hint = getattr(store, 'reread_hint', 'the state')
        raise CommandRefused('stale_revision',
                             f'Revision is stale: reread {hint} before deciding',
                             details={'expected_revision': expected, 'current_revision': current,
                                      'changes_since': store.changes_since(expected)})


def _check_action(request: Mapping, handlers: Mapping[str, Handler]) -> Handler:
    action, params = request['action'], request['params']
    handler = handlers.get(action) if isinstance(action, str) else None
    if handler is None or not isinstance(params, dict) or set(params) != set(handler.params):
        raise CommandRefused('invalid_command', 'Invalid action or command parameters',
                             details={'action': action if isinstance(action, str) else None,
                                      'actions': sorted(handlers),
                                      'params': sorted(handler.params) if handler else None})
    if handler.check is not None:
        handler.check(params)
    return handler


def apply_command(store, state: dict, request: Mapping, handlers: Mapping[str, Handler]) -> dict:
    """Apply one revisioned, idempotent command and return its receipt.

    The caller holds the writer lock and passes the state it has just reread.

    1. ``request`` has exactly ``request_id``, ``expected_revision``, ``action``, and
       ``params``; its signature is the SHA-256 of its canonical JSON.
    2. A known ``request_id`` with the same signature is a replay: the stored receipt
       is returned with ``replayed: True`` and nothing is written. With a different
       signature it is refused (``idempotency_conflict``).
    3. ``expected_revision`` must equal the state revision. Otherwise the refusal
       (``stale_revision``) carries ``current_revision`` and ``changes_since``, the
       revision log entries the client has not seen.
    4. The action and its exact parameter set must match a handler.
    5. The files the store tracks are saved in a transaction file, the handler mutates
       state in memory, and ``store.commit`` persists it (the commit point). On any
       exception before the commit, state is restored in memory and ``store.recover``
       restores the files and removes the transaction.

    The receipt is ``{signature, result, revision}`` where ``revision`` is the revision
    created by the command.

    A store provides: ``snapshot_files() -> {name: text or None}``,
    ``write_transaction(row)``, ``read_transaction() -> row or None``,
    ``clear_transaction()``, ``restore_file(name, content)``, ``mutating()`` (a context
    manager around the handler), ``commit(state, change)`` (increments the revision and
    persists), ``event(kind, **fields)``, ``changes_since(revision) -> list``, and
    ``recover(state)``. ``reread_hint`` is optional text for the stale message.
    """
    signature, receipt = _check_request(state, request)
    if receipt is not None:
        return {**receipt, 'replayed': True}
    _check_revision(store, state, request)
    handler = _check_action(request, handlers)

    key, action, params = request['request_id'], request['action'], request['params']
    before = copy.deepcopy(state)
    store.write_transaction({'request_id': key, 'before_files': store.snapshot_files()})
    committed = False
    try:
        with store.mutating():
            result = handler.run(state, params)
        receipt = {'signature': signature, 'result': result,
                   'revision': before.get('revision', 0) + 1}
        state.setdefault('receipts', {})[key] = receipt
        store.commit(state, {'request_id': key, 'action': action, 'params': params,
                             'result': result})
        committed = True
        store.clear_transaction()
        store.event('command_committed', request_id=key, action=action,
                    revision=state['revision'])
        return receipt
    except BaseException:
        if committed:
            raise
        state.clear()
        state.update(before)
        store.recover(state)
        raise


# --- legacy pilot adapter ---------------------------------------------------------------

class PilotStore:
    """Persistence of the legacy pilot (``.pilot/`` under ``pilot.config.ROOT``).

    ``pilot.save`` is looked up at commit time, and suspended while a handler runs,
    because pilot sub-operations call it; their state stays in memory until commit.
    """

    TRACKED = ('project.yaml', 'frame.yaml', 'answers.yaml')
    reread_hint = 'pilot next'

    def __init__(self, pilot):
        self.pilot = pilot

    @property
    def transaction_path(self) -> Path:
        return self.pilot.home() / 'transaction.json'

    def snapshot_files(self) -> dict:
        root = self.pilot.config.ROOT
        return {n: (root / n).read_text() if (root / n).exists() else None for n in self.TRACKED}

    def write_transaction(self, row: dict) -> None:
        self.pilot.write(self.transaction_path, row)

    def read_transaction(self) -> dict | None:
        path = self.transaction_path
        return json.loads(path.read_text()) if path.exists() else None

    def clear_transaction(self) -> None:
        self.transaction_path.unlink()

    def restore_file(self, name: str, content: str | None) -> None:
        path = self.pilot.config.ROOT / name
        if content is None:
            path.unlink(missing_ok=True)
        else:
            temp = path.with_suffix(path.suffix + '.recovery')
            temp.write_text(content)
            os.replace(temp, path)

    @contextlib.contextmanager
    def mutating(self):
        real_save = self.pilot.save
        self.pilot.save = lambda value: None
        try:
            yield
        finally:
            self.pilot.save = real_save

    def commit(self, state: dict, change: dict) -> None:
        self.pilot.save(state)

    def event(self, kind: str, **fields) -> None:
        self.pilot.event(kind, **fields)

    def changes_since(self, revision: int) -> list:
        """Committed commands after ``revision``, read from the pilot event log."""
        path = self.pilot.home() / 'events.jsonl'
        if not path.exists():
            return []
        changes = []
        for line in path.read_text(encoding='utf-8').splitlines():
            row = json.loads(line)
            if row.get('kind') == 'command_committed' and row.get('revision', 0) > revision:
                changes.append({k: row.get(k) for k in ('revision', 'request_id', 'action', 'time')})
        return changes

    def recover(self, state: dict) -> dict:
        return recover(self.pilot, state)


def _pilot_answer(pilot):
    def check(params):
        if type(params['confirmed']) is not bool:
            raise CommandRefused('invalid_command', 'Explicit boolean confirmation required')

    def run(state, params):
        pilot.propose(state, params['question'], params['value'], params['rationale'],
                      status='confirmed' if params['confirmed'] else 'assumed')
        return {'question': params['question'], 'status': state['answers'][params['question']]['status']}
    return Handler(frozenset({'question', 'value', 'rationale', 'confirmed'}), run, check)


def _pilot_revise(pilot):
    def run(state, params):
        path = pilot.home() / 'requested-revision.json'
        pilot.write(path, params['changes'])
        return pilot.revise(state, path, params['expected_context'])
    return Handler(frozenset({'changes', 'expected_context'}), run)


def _pilot_iterate(pilot):
    def run(state, params):
        return pilot.iterate(state, params['reason'], params['steps'], params['seconds'])
    return Handler(frozenset({'reason', 'steps', 'seconds'}), run)


def _pilot_mode():
    def check(params):
        if params['mode'] not in {'junior', 'senior', 'auto'}:
            raise CommandRefused('invalid_command', 'Unknown mode')

    def run(state, params):
        state['mode'] = params['mode']
        return {'mode': params['mode']}
    return Handler(frozenset({'mode'}), run, check)


def pilot_handlers(pilot) -> dict:
    return {'answer': _pilot_answer(pilot), 'revise': _pilot_revise(pilot),
            'iterate': _pilot_iterate(pilot), 'mode': _pilot_mode()}


def recover(pilot, state):
    """Under the acquired lock, no previous local process owns it.
Never repeat an action with an unknown outcome automatically.
"""
    changed = False
    rollback_transaction(PilotStore(pilot), state)
    active = state.pop('active_execution', None)
    if active:
        active.update(status='interrupted_unknown', finished=pilot.now())
        pilot.write(pilot.home() / 'executions' / (active['id'] + '.json'), active)
        state['interrupted_execution'] = active
        pilot.event('interrupted_execution', execution=active['id'])
        changed = True
    if changed:
        pilot.save(state)
    return state


def apply(pilot, state, request):
    """Recommended single entry point for multi-client decisions.
The retained historical CLI does not provide this guarantee.
"""
    return apply_command(PilotStore(pilot), state, request, pilot_handlers(pilot))


def start(pilot, state, key, argv):
    row = {'id': uuid.uuid4().hex, 'step': key, 'command': argv,
           'context': state['context'], 'revision': state.get('revision', 0),
           'iteration': state.get('iteration', 1), 'started': pilot.now(),
           'status': 'running', 'provenance': provenance(pilot.config.ROOT)}
    state['active_execution'] = row
    # Durable reservation before execution; interruption does not create a free budget.
    state['executions'] = state.get('executions', 0) + 1
    pilot.save(state)
    pilot.write(pilot.home() / 'executions' / (row['id'] + '.json'), row)
    return row


def finish(pilot, state, row, code, seconds):
    row = {**row, 'returncode': code, 'seconds': seconds, 'finished': pilot.now(),
           'status': 'succeeded' if code == 0 else 'failed'}
    current = provenance(pilot.config.ROOT)
    if row['context'] != pilot.context_hash() or row['provenance'] != current:
        row['status'] = 'stale'
    pilot.write(pilot.home() / 'executions' / (row['id'] + '.json'), row)
    state.pop('active_execution', None)
    return row


def summary(pilot, state):
    blockers = []
    if any('provenance' not in value for key, value in state['steps'].items() if key != 'quality'):
        blockers.append('Previous results retained: this new log does not attest their complete provenance.')
    if state.get('interrupted_execution'):
        blockers.append('Execution interrupted with unknown outcome; inspect before resuming.')
    failures = [k for k, v in state['steps'].items() if v.get('returncode') != 0]
    if failures:
        blockers.append('Failed calculations: ' + ', '.join(failures))
    if state.get('revision_pending'):
        blockers.append('Contract revised: an explicit new cycle is required.')
    unresolved = [q['id'] for q in pilot.pending(state)]
    if unresolved:
        blockers.append('Unconfirmed decisions: ' + ', '.join(unresolved))
    todo = pilot.remaining(state)
    if state.get('executions', 0) >= state['max_steps'] or state['seconds_used'] >= state['max_seconds']:
        status = 'budget_exhausted'; next_action = 'Review the summary and decide the next budget.'
    elif blockers:
        status = 'attention_required'; next_action = blockers[0]
    elif todo:
        labels = {'discovery':'Discover the data', 'classical-plan':'Prepare the comparison and evidence', 'classical-profile':'Check data quality and splitting', 'classical-run':'Run the exploratory comparison', 'quality':'Check tests for the change', 'notebooks':'Prepare explanatory notebooks'}
        status = 'ready'; next_action = labels.get(todo[0][0], 'Run the next workflow check')
    else:
        status = 'plan_finished'; next_action = 'Compare evidence and reach an exploratory conclusion.'
    return {'revision': state.get('revision', 0), 'context': state['context'],
            'status': status, 'blockers': blockers, 'next_action': next_action,
            'proof_scope': 'exploratory_only', 'generalization': 'not_established',
            'moments': ['Frame the change', 'Prepare evidence', 'Work and compare', 'Conclude and hand over'],
            'guidance': 'detailed' if state['mode'] == 'junior' else 'concise',
            'execution': 'bounded' if state['mode'] == 'auto' else 'interactive'}


def sync_provenance(pilot, state):
    """Invalidate a tracked result when code or environment changes.
Historical evidence without fingerprints is never retroactively certified.
"""
    current = provenance(pilot.config.ROOT)
    changed = [key for key, value in state['steps'].items()
               if value.get('provenance') and value['provenance'] != current]
    if changed:
        pilot.snapshot(state, suffix='-provenance-' + uuid.uuid4().hex[:12])
        previous = state['steps']; state['steps'] = {}
        for task in state['tasks']:
            if task['status'] == 'queued': task['status'] = 'stale'
        pilot.event('provenance_changed', affected=changed, invalidated=previous)
        pilot.save(state)
