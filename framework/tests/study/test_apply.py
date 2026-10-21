"""Generic command core ``reliability.apply_command`` (plan WP1.1).

The tests use a small directory-backed store defined here, so they exercise the core
alone: no legacy pilot, no ``.hypotrail`` study. Everything lives in ``tmp_path``.
The legacy wrapper keeps its own suite, ``framework/tests/test_reliability.py``.
"""
from __future__ import annotations

import contextlib
import copy
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from mlkit import reliability as r

FRAMEWORK = Path(__file__).resolve().parents[2]


class DirStore:
    """Minimal store: state.json is the commit point; notes.txt is a tracked file."""

    TRACKED = ('notes.txt',)
    reread_hint = 'the test state'

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, name: str) -> Path:
        return self.root / name

    def load(self) -> dict:
        path = self.path('state.json')
        return json.loads(path.read_text()) if path.exists() else {'revision': 0, 'items': {}}

    def _write(self, name: str, obj) -> None:
        temp = self.path(name + '.tmp')
        temp.write_text(json.dumps(obj, sort_keys=True))
        os.replace(temp, self.path(name))

    def _append(self, name: str, row: dict) -> None:
        with self.path(name).open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(row, sort_keys=True) + '\n')

    def _rows(self, name: str) -> list[dict]:
        path = self.path(name)
        return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []

    def snapshot_files(self) -> dict:
        return {n: self.path(n).read_text() if self.path(n).exists() else None for n in self.TRACKED}

    def write_transaction(self, row: dict) -> None:
        self._write('transaction.json', row)

    def read_transaction(self):
        path = self.path('transaction.json')
        return json.loads(path.read_text()) if path.exists() else None

    def clear_transaction(self) -> None:
        self.path('transaction.json').unlink()

    def restore_file(self, name, content) -> None:
        if content is None:
            self.path(name).unlink(missing_ok=True)
        else:
            self.path(name).write_text(content)

    @contextlib.contextmanager
    def mutating(self):
        yield

    def commit(self, state: dict, change: dict) -> None:
        state['revision'] = state.get('revision', 0) + 1
        self._write('state.json', state)
        self._append('revisions.jsonl', {'revision': state['revision'], **change})

    def event(self, kind: str, **fields) -> None:
        self._append('events.jsonl', {'kind': kind, **fields})

    def changes_since(self, revision: int) -> list:
        return [row for row in self._rows('revisions.jsonl') if row['revision'] > revision]

    def recover(self, state: dict) -> dict:
        r.rollback_transaction(self, state)
        return state


def _set_item(state, params):
    state.setdefault('items', {})[params['name']] = params['value']
    return {'name': params['name'], 'value': params['value']}


def _write_note_then_fail(store):
    def run(state, params):
        store.path('notes.txt').write_text(params['text'])
        state['items']['half'] = 'written'
        raise RuntimeError('handler failed after a file write')
    return run


def _refuse_empty(params):
    if not params['value']:
        raise r.CommandRefused('invalid_value', 'value must not be empty')


def handlers(store) -> dict:
    return {'set': r.Handler(frozenset({'name', 'value'}), _set_item, _refuse_empty),
            'note_and_fail': r.Handler(frozenset({'text'}), _write_note_then_fail(store))}


def req(state, key='request-1', action='set', **params):
    return {'request_id': key, 'expected_revision': state.get('revision', 0),
            'action': action, 'params': params or {'name': 'a', 'value': 'one'}}


@pytest.fixture
def store(tmp_path):
    return DirStore(tmp_path / 'store')


def _refused(code, store, state, request) -> r.CommandRefused:
    with pytest.raises(r.CommandRefused) as info:
        r.apply_command(store, state, request, handlers(store))
    assert info.value.code == code, info.value.to_dict()
    assert isinstance(info.value, ValueError)
    return info.value


def test_commit_returns_receipt_and_logs_revision(store):
    state = store.load()
    receipt = r.apply_command(store, state, req(state), handlers(store))
    assert receipt == {'signature': r.request_signature(req({'revision': 0})),
                       'result': {'name': 'a', 'value': 'one'}, 'revision': 1}
    assert store.load() == state and state['revision'] == 1
    assert state['receipts']['request-1'] == receipt
    assert store.changes_since(0) == [{'revision': 1, 'request_id': 'request-1', 'action': 'set',
                                       'params': {'name': 'a', 'value': 'one'},
                                       'result': {'name': 'a', 'value': 'one'}}]
    assert not store.path('transaction.json').exists()


def test_replay_is_a_no_op(store):
    state = store.load()
    first = req(state)
    receipt = r.apply_command(store, state, first, handlers(store))
    # A replay is recognised even after other commands moved the revision on.
    r.apply_command(store, state, req(state, 'request-2', name='b', value='two'), handlers(store))
    state_bytes = store.path('state.json').read_bytes()
    events = store.path('events.jsonl').read_text()
    again = r.apply_command(store, state, copy.deepcopy(first), handlers(store))
    assert again == {**receipt, 'replayed': True}
    assert store.path('state.json').read_bytes() == state_bytes
    assert store.path('events.jsonl').read_text() == events
    assert state['revision'] == 2


def test_same_key_with_different_signature_is_refused(store):
    state = store.load()
    first = req(state)
    r.apply_command(store, state, first, handlers(store))
    before = copy.deepcopy(state)
    altered = copy.deepcopy(first)
    altered['params']['value'] = 'other'
    refusal = _refused('idempotency_conflict', store, state, altered)
    assert refusal.details == {'request_id': 'request-1', 'revision': 1}
    assert state == before == store.load()
    assert state['items'] == {'a': 'one'}


def test_stale_revision_refusal_carries_current_revision_and_diff(store):
    state = store.load()
    seen = state['revision']
    r.apply_command(store, state, req(state, 'r1', name='a', value='one'), handlers(store))
    r.apply_command(store, state, req(state, 'r2', name='b', value='two'), handlers(store))
    late = {'request_id': 'r3', 'expected_revision': seen, 'action': 'set',
            'params': {'name': 'a', 'value': 'changed'}}
    refusal = _refused('stale_revision', store, state, late)
    assert 'stale' in str(refusal) and 'the test state' in str(refusal)
    details = refusal.details
    assert details['expected_revision'] == 0 and details['current_revision'] == 2
    assert [c['revision'] for c in details['changes_since']] == [1, 2]
    assert [c['request_id'] for c in details['changes_since']] == ['r1', 'r2']
    assert details['changes_since'][0]['params'] == {'name': 'a', 'value': 'one'}
    assert state['items'] == {'a': 'one', 'b': 'two'} and 'r3' not in state['receipts']
    late['expected_revision'] = 1
    assert [c['revision'] for c in _refused('stale_revision', store, state, late)
            .details['changes_since']] == [2]


@pytest.mark.parametrize('mutate, field', [
    (lambda q: q.pop('params'), 'params'),
    (lambda q: q.pop('request_id'), 'request_id'),
    (lambda q: q.pop('expected_revision'), 'expected_revision'),
    (lambda q: q.pop('action'), 'action'),
])
def test_missing_fields_are_refused(store, mutate, field):
    state = store.load()
    request = req(state)
    mutate(request)
    refusal = _refused('invalid_request', store, state, request)
    assert refusal.details['missing'] == [field]
    assert not store.path('state.json').exists() and not store.path('transaction.json').exists()


@pytest.mark.parametrize('request_value, code', [
    ({'request_id': 'k', 'expected_revision': 0, 'action': 'set',
      'params': {'name': 'a', 'value': 'v'}, 'extra': 1}, 'invalid_request'),
    ({'request_id': ' ', 'expected_revision': 0, 'action': 'set',
      'params': {'name': 'a', 'value': 'v'}}, 'invalid_request'),
    ({'request_id': 'k' * 201, 'expected_revision': 0, 'action': 'set',
      'params': {'name': 'a', 'value': 'v'}}, 'invalid_request'),
    ({'request_id': 'k', 'expected_revision': '0', 'action': 'set',
      'params': {'name': 'a', 'value': 'v'}}, 'invalid_request'),
    ({'request_id': 'k', 'expected_revision': 0, 'action': 'unknown',
      'params': {}}, 'invalid_command'),
    ({'request_id': 'k', 'expected_revision': 0, 'action': 'set',
      'params': {'name': 'a'}}, 'invalid_command'),
    ({'request_id': 'k', 'expected_revision': 0, 'action': 'set',
      'params': {'name': 'a', 'value': ''}}, 'invalid_value'),
    ([], 'invalid_request'),
])
def test_malformed_requests_are_refused_without_effect(store, request_value, code):
    state = store.load()
    _refused(code, store, state, request_value)
    assert state == {'revision': 0, 'items': {}}
    assert not store.path('state.json').exists() and not store.path('transaction.json').exists()


def test_exception_in_handler_rolls_back_state_and_files(store):
    state = store.load()
    r.apply_command(store, state, req(state), handlers(store))
    store.path('notes.txt').write_text('original note')
    before = copy.deepcopy(state)
    with pytest.raises(RuntimeError, match='handler failed'):
        r.apply_command(store, state, req(state, 'r2', action='note_and_fail', text='new note'),
                        handlers(store))
    assert state == before == store.load()
    assert store.path('notes.txt').read_text() == 'original note'
    assert not store.path('transaction.json').exists()
    kinds = [json.loads(x)['kind'] for x in store.path('events.jsonl').read_text().splitlines()]
    assert kinds == ['command_committed', 'transaction_rolled_back']


def test_rollback_removes_a_file_that_did_not_exist(store):
    state = store.load()
    with pytest.raises(RuntimeError):
        r.apply_command(store, state, req(state, action='note_and_fail', text='new'),
                        handlers(store))
    assert not store.path('notes.txt').exists()


def test_failure_at_commit_restores_state_and_files(store, monkeypatch):
    state = store.load()
    store.path('notes.txt').write_text('kept')
    before = copy.deepcopy(state)

    def run(state, params):
        store.path('notes.txt').write_text('changed')
        state['items']['x'] = 1
        return {}

    def fail_commit(state, change):
        raise OSError('Simulated interrupted write before commit')

    monkeypatch.setattr(store, 'commit', fail_commit)
    with pytest.raises(OSError):
        r.apply_command(store, state, req(state, action='write', text='t'),
                        {'write': r.Handler(frozenset({'text'}), run)})
    assert state == before
    assert store.path('notes.txt').read_text() == 'kept'
    assert not store.path('state.json').exists() and not store.path('transaction.json').exists()


def test_recovery_after_crash_keeps_a_committed_command(store):
    state = store.load()
    r.apply_command(store, state, req(state), handlers(store))
    store.path('notes.txt').write_text('after commit')
    # Crash after the commit point, before the transaction file was removed.
    store.write_transaction({'request_id': 'request-1', 'before_files': {'notes.txt': None}})
    assert r.rollback_transaction(store, store.load())
    assert store.path('notes.txt').read_text() == 'after commit'
    assert not store.path('transaction.json').exists()
    assert not r.rollback_transaction(store, store.load())


def test_recovery_after_crash_before_commit_restores_files(store):
    state = store.load()
    store.path('notes.txt').write_text('before')
    store.write_transaction({'request_id': 'crashed', 'before_files': {'notes.txt': 'before'}})
    store.path('notes.txt').write_text('half written')
    store.recover(state)
    assert store.path('notes.txt').read_text() == 'before'
    assert not store.path('transaction.json').exists()


CLIENT = textwrap.dedent('''
    import contextlib, fcntl, json, os, sys, time
    sys.path.insert(0, sys.argv[1])
    from mlkit import reliability as r
    from test_apply import DirStore, handlers
    store = DirStore(sys.argv[2])
    expected = int(sys.argv[4])
    go = sys.argv[5]
    while not os.path.exists(go):
        time.sleep(0.005)
    request = {'request_id': sys.argv[3], 'expected_revision': expected, 'action': 'set',
               'params': {'name': 'decision', 'value': 'confirmed by ' + sys.argv[3]}}
    fd = os.open(os.path.join(sys.argv[2], 'writer.lock'), os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        state = store.load()          # reread under the lock
        try:
            print(json.dumps({'ok': r.apply_command(store, state, request, handlers(store))}))
        except r.CommandRefused as refusal:
            print(json.dumps({'refused': refusal.to_dict()}))
    finally:
        os.close(fd)
''')


def test_two_concurrent_clients_confirming_the_same_thing(store, tmp_path):
    """Two processes read revision 0, then both confirm: one wins, one gets the diff."""
    state = store.load()
    script = tmp_path / 'client.py'
    script.write_text(CLIENT)
    go = tmp_path / 'go'
    env = {**os.environ, 'PYTHONPATH': os.pathsep.join([str(FRAMEWORK), str(Path(__file__).parent)])}
    clients = [subprocess.Popen([sys.executable, str(script), str(FRAMEWORK), str(store.root),
                                 name, str(state['revision']), str(go)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
               for name in ('chat', 'webview')]
    go.write_text('')
    outputs = []
    for proc in clients:
        out, err = proc.communicate(timeout=60)
        assert proc.returncode == 0, err
        outputs.append(json.loads(out.strip().splitlines()[-1]))
    wins = [o for o in outputs if 'ok' in o]
    refusals = [o['refused'] for o in outputs if 'refused' in o]
    assert len(wins) == 1 and len(refusals) == 1, outputs
    assert wins[0]['ok']['revision'] == 1
    refusal = refusals[0]
    assert refusal['code'] == 'stale_revision'
    assert refusal['details']['current_revision'] == 1
    changes = refusal['details']['changes_since']
    assert len(changes) == 1 and changes[0]['revision'] == 1
    winner = changes[0]['request_id']
    assert store.load()['items'] == {'decision': 'confirmed by ' + winner}
    assert list(store.load()['receipts']) == [winner]


def test_importing_the_core_loads_no_other_mlkit_module():
    """mlkit.study may import mlkit.reliability only because it pulls nothing legacy."""
    env = {**os.environ, 'PYTHONPATH': str(FRAMEWORK)}
    code = ('import json, sys, mlkit.reliability; '
            'print(json.dumps(sorted(m for m in sys.modules if m.startswith("mlkit"))))')
    proc = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                          env=env, cwd=FRAMEWORK, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == ['mlkit', 'mlkit.reliability']
