"""Study store, writer lock, and execution leases (plan WP1.2).

Studies are created in ``tmp_path`` from the synthetic case; nothing touches
``use-cases/`` or an existing study.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from mlkit import reliability as r
from mlkit.study import case as c, lock, state as st, store as sto
from mlkit.study.errors import StudyError

TESTS = Path(__file__).resolve().parents[1]
FRAMEWORK = TESTS.parent
_spec = importlib.util.spec_from_file_location('synthetic_make_case_for_store',
                                               TESTS / 'fixtures/synthetic/make_case.py')
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
make_case = _module.make_case


# --- test handlers (the real decide commands arrive in WP1.4) ---------------------------

def _propose(state, params):
    pid = f'p_{len(state["proposals"]) + 1}'
    state['proposals'][pid] = {
        'proposal_id': pid, 'decision_id': params['decision_id'], 'value': params['value'],
        'restatement': params['restatement'], 'rationale': params['rationale'],
        'revision': state['revision'] + 1, 'status': 'open', 'created': st.now()}
    decision = state['decisions'][params['decision_id']]
    decision.update(status='proposed', value=params['value'], proposal_id=pid,
                    revision=state['revision'] + 1)
    return {'proposal_id': pid}


def _confirm(state, params):
    proposal = state['proposals'].get(params['proposal_id'])
    if proposal is None or proposal['status'] != 'open':
        raise r.CommandRefused('proposal_not_open', 'The proposal is not open.')
    proposal['status'] = 'confirmed'
    decision = state['decisions'][proposal['decision_id']]
    decision.update(status='confirmed', value=proposal['value'],
                    proposal_id=proposal['proposal_id'], revision=state['revision'] + 1,
                    confirmation=st.confirmation(user_words=params['user_words'],
                                                 proposal=proposal, channel=params['channel'],
                                                 actor=params['actor'],
                                                 revision=state['revision'] + 1))
    return {'decision': proposal['decision_id'], 'status': 'confirmed'}


def _corrupt(state, params):
    state['facts']['bad'] = {'value': 1, 'status': 'confirmed', 'source': 'x'}
    return {}


HANDLERS = {
    'propose': r.Handler(frozenset({'decision_id', 'value', 'restatement', 'rationale'}), _propose),
    'confirm': r.Handler(frozenset({'proposal_id', 'user_words', 'channel', 'actor'}), _confirm),
    'corrupt': r.Handler(frozenset(), _corrupt),
}


def request(state, key, action, **params):
    return {'request_id': key, 'expected_revision': state['revision'], 'action': action,
            'params': params}


PROPOSAL = dict(decision_id='prediction_time', value='before the first reminder',
                restatement='You predict before the first reminder is sent.',
                rationale='Synthetic test proposal, not a demo decision.')


@pytest.fixture(scope='module')
def case_dir(tmp_path_factory):
    return make_case(tmp_path_factory.mktemp('case'), n_rows=300)['case'].parent


@pytest.fixture
def study(tmp_path, case_dir):
    store = sto.StudyStore(tmp_path / 'study')
    store.create(st.initial_state(c.load_case(case_dir)))
    return store


# --- low-level writes -------------------------------------------------------------------

def test_atomic_write_replaces_without_leftovers(tmp_path):
    path = tmp_path / 'x' / 'file.json'
    sto.atomic_write_json(path, {'a': 1})
    sto.atomic_write_json(path, {'a': 2})
    assert json.loads(path.read_text()) == {'a': 2}
    assert [p.name for p in path.parent.iterdir()] == ['file.json']


def test_write_once_is_exclusive_and_immutable(tmp_path):
    path = tmp_path / 'registry' / 'r1.json'
    assert sto.write_once(path, b'one') is True
    assert sto.write_once(path, b'one') is False
    with pytest.raises(StudyError) as info:
        sto.write_once(path, b'two')
    assert info.value.code == 'integrity_error'
    assert path.read_bytes() == b'one'


def test_append_jsonl_closes_a_torn_line(tmp_path):
    path = tmp_path / 'log.jsonl'
    sto.append_jsonl(path, {'n': 1})
    with open(path, 'a') as handle:
        handle.write('{"n": 2, "tor')           # crash in the middle of a line
    sto.append_jsonl(path, {'n': 3})
    assert sto.read_jsonl(path) == [{'n': 1}, {'n': 3}]


def test_blobs_are_content_addressed_and_verified(study):
    sha = study.put_blob(b'row_key,y,score\n')
    assert study.read_blob(sha) == b'row_key,y,score\n'
    assert study.put_blob(b'row_key,y,score\n') == sha
    (study.home / 'blobs' / sha).chmod(0o644)
    (study.home / 'blobs' / sha).write_bytes(b'tampered')
    with pytest.raises(StudyError) as info:
        study.read_blob(sha)
    assert info.value.code == 'integrity_error'


def test_registry_entries_are_written_once(study):
    assert study.put_registry('abc', {'x': 1})
    assert not study.put_registry('abc', {'x': 1})
    with pytest.raises(StudyError):
        study.put_registry('abc', {'x': 2})
    assert study.read_registry('abc') == {'x': 1}


# --- creation, integrity, and commits ---------------------------------------------------

def test_create_writes_revision_one_and_never_overwrites(study, case_dir):
    state = study.load_state()
    assert state['revision'] == 1 and state['schema'] == st.SCHEMA
    assert study.sha_path.read_text() == st.sha_line(st.digest(study.state_path.read_bytes()))
    assert [x['revision'] for x in study.revisions()] == [1]
    assert study.revisions()[0]['action'] == 'init'
    with pytest.raises(StudyError) as info:
        study.create(st.initial_state(c.load_case(case_dir)))
    assert info.value.code == 'state_exists'
    assert study.load_state() == state


def test_hand_edit_of_state_is_an_integrity_error(study):
    state = json.loads(study.state_path.read_text())
    state['decisions']['prediction_time']['status'] = 'confirmed'
    study.state_path.write_text(json.dumps(state))
    with pytest.raises(StudyError) as info:
        study.load_state()
    assert info.value.code == 'integrity_error'
    assert info.value.details['recorded_sha256'] != info.value.details['state_sha256']


def test_missing_sha_file_is_an_integrity_error(study):
    study.sha_path.unlink()
    with pytest.raises(StudyError) as info:
        study.load_state()
    assert info.value.code == 'integrity_error'


def test_consistent_but_invalid_state_is_an_integrity_error(study):
    state = json.loads(study.state_path.read_text())
    state['facts']['x'] = {'value': 1, 'status': 'confirmed', 'source': 'hand edit'}
    data = st.dumps(state)
    study.state_path.write_bytes(data)
    study.sha_path.write_text(st.sha_line(st.digest(data)))
    with pytest.raises(StudyError) as info:
        study.load_state()
    assert info.value.code == 'integrity_error'


def test_execute_commits_logs_and_replays(study):
    state = study.load_state()
    first = request(state, 'req-1', 'propose', **PROPOSAL)
    receipt = study.execute(first, HANDLERS)
    assert receipt['revision'] == 2 and receipt['result'] == {'proposal_id': 'p_1'}
    log = study.revisions_path.read_bytes()
    assert study.execute(copy.deepcopy(first), HANDLERS) == {**receipt, 'replayed': True}
    assert study.revisions_path.read_bytes() == log
    after = study.load_state()
    assert after['revision'] == 2 and after['proposals']['p_1']['status'] == 'open'
    assert study.revisions()[-1]['state_sha256'] == st.digest(study.state_path.read_bytes())


def test_invalid_state_is_refused_before_any_write(study):
    before = study.state_path.read_bytes()
    state = study.load_state()
    with pytest.raises(StudyError) as info:
        study.execute(request(state, 'bad', 'corrupt'), HANDLERS)
    assert info.value.code == 'invalid_state'
    assert study.state_path.read_bytes() == before
    assert not study.transaction_path.exists() and not study.pending_path.exists()


def test_tracked_file_is_restored_when_a_command_fails(tmp_path, case_dir):
    store = sto.StudyStore(tmp_path / 's', tracked=('reports/notes.txt',))
    store.create(st.initial_state(c.load_case(case_dir)))
    notes = store.study_dir / 'reports' / 'notes.txt'
    notes.parent.mkdir()
    notes.write_text('kept')

    def fail(state, params):
        notes.write_text('half')
        raise RuntimeError('boom')

    state = store.load_state()
    with pytest.raises(RuntimeError):
        store.execute(request(state, 'x', 'fail'), {'fail': r.Handler(frozenset(), fail)})
    assert notes.read_text() == 'kept' and store.load_state()['revision'] == 1


def test_crash_after_commit_point_is_completed_by_the_next_writer(study, monkeypatch):
    state = study.load_state()
    real = sto.atomic_write

    def no_sha(path, data):
        if Path(path).name == st.SHA_FILE:
            raise OSError('Simulated crash after the commit point')
        real(path, data)

    monkeypatch.setattr(sto, 'atomic_write', no_sha)
    receipt = study.execute(request(state, 'req-1', 'propose', **PROPOSAL), HANDLERS)
    monkeypatch.setattr(sto, 'atomic_write', real)
    assert study.pending_path.exists()
    assert [x['revision'] for x in study.revisions()] == [1]
    assert study.load_state()['revision'] == 2          # readers accept the pending commit
    with study.writing() as reread:
        assert reread['receipts']['req-1'] == receipt
    assert not study.pending_path.exists()
    assert [x['revision'] for x in study.revisions()] == [1, 2]
    assert study.sha_path.read_text() == st.sha_line(st.digest(study.state_path.read_bytes()))


def test_crash_before_commit_point_discards_the_pending_commit(study):
    before = study.state_path.read_bytes()
    sto.atomic_write_json(study.pending_path, {'state_sha256': '0' * 64,
                                               'record': {'revision': 2}})
    with study.writing() as state:
        assert state['revision'] == 1
    assert not study.pending_path.exists() and study.state_path.read_bytes() == before
    assert [x['revision'] for x in study.revisions()] == [1]


# --- concurrency ------------------------------------------------------------------------

CLIENT = textwrap.dedent('''
    import json, os, sys, time
    from mlkit import reliability as r
    from mlkit.study import store as sto
    from test_store import HANDLERS
    study, key, channel, expected, go = sys.argv[1:6]
    while not os.path.exists(go):
        time.sleep(0.005)
    request = {'request_id': key, 'expected_revision': int(expected), 'action': 'confirm',
               'params': {'proposal_id': 'p_1', 'user_words': 'Yes, before the first reminder.',
                          'channel': channel, 'actor': 'junior'}}
    try:
        print(json.dumps({'ok': sto.StudyStore(study).execute(request, HANDLERS)}))
    except r.CommandRefused as refusal:
        print(json.dumps({'refused': refusal.to_dict()}))
''')


def test_chat_and_webview_confirm_the_same_proposal_concurrently(study, tmp_path):
    """Plan §9 bis: one confirmation; the other client gets stale_revision with a diff."""
    state = study.load_state()
    study.execute(request(state, 'propose-1', 'propose', **PROPOSAL), HANDLERS)
    seen = study.load_state()['revision']          # both clients read this revision
    script = tmp_path / 'client.py'
    script.write_text(CLIENT)
    go = tmp_path / 'go'
    env = {**os.environ,
           'PYTHONPATH': os.pathsep.join([str(FRAMEWORK), str(Path(__file__).parent)])}
    clients = [subprocess.Popen([sys.executable, str(script), str(study.study_dir), f'{ch}-1', ch,
                                 str(seen), str(go)], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, env=env)
               for ch in ('chat', 'webview')]
    go.write_text('')
    outputs = []
    for proc in clients:
        out, err = proc.communicate(timeout=60)
        assert proc.returncode == 0, err
        outputs.append(json.loads(out.strip().splitlines()[-1]))
    wins = [o['ok'] for o in outputs if 'ok' in o]
    refusals = [o['refused'] for o in outputs if 'refused' in o]
    assert len(wins) == 1 and len(refusals) == 1, outputs
    assert refusals[0]['code'] == 'stale_revision'
    details = refusals[0]['details']
    assert details['expected_revision'] == seen and details['current_revision'] == seen + 1
    [change] = details['changes_since']
    assert change['action'] == 'confirm' and change['revision'] == seen + 1
    final = study.load_state()
    confirmation = final['decisions']['prediction_time']['confirmation']
    assert change['request_id'] == f'{confirmation["channel"]}-1'
    assert confirmation['authenticated'] is False and confirmation['actor'] == 'junior'
    assert final['revision'] == seen + 1


# --- lock and leases --------------------------------------------------------------------

HOLD = textwrap.dedent('''
    import sys, time
    from mlkit.study import lock
    with lock.writer_lock(sys.argv[1]):
        print('held', flush=True)
        time.sleep(float(sys.argv[2]))
''')


def _spawn(code: str, *args) -> subprocess.Popen:
    env = {**os.environ, 'PYTHONPATH': str(FRAMEWORK)}
    return subprocess.Popen([sys.executable, '-c', code, *map(str, args)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)


def test_writer_lock_refuses_when_busy_and_is_released_on_exit(study):
    holder = _spawn(HOLD, study.study_dir, 30)
    assert holder.stdout.readline().strip() == 'held'
    with pytest.raises(StudyError) as info:
        with lock.writer_lock(study.study_dir, timeout=0.2):
            pass
    assert info.value.code == 'study_busy'
    assert info.value.details['holder']['pid'] == holder.pid
    holder.kill()
    holder.communicate(timeout=30)
    with lock.writer_lock(study.study_dir, timeout=5):   # the OS released the dead holder
        pass


def test_writer_lock_needs_an_existing_study(tmp_path):
    with pytest.raises(StudyError) as info:
        with lock.writer_lock(tmp_path):
            pass
    assert info.value.code == 'study_missing'
    assert not (tmp_path / '.hypotrail').exists()


def test_native_windows_is_refused(study, monkeypatch):
    monkeypatch.setattr(lock.os, 'name', 'nt')
    with pytest.raises(StudyError) as info:
        lock.require_posix()
    assert info.value.code == 'platform_unsupported'
    with pytest.raises(StudyError) as info:
        with lock.writer_lock(study.study_dir):
            pass
    assert info.value.code == 'platform_unsupported'


LEASE = textwrap.dedent('''
    import os, sys
    from mlkit.study import lock
    lock.acquire_lease(sys.argv[1], sys.argv[2], activity='fit.logistic')
    print('leased', flush=True)
    os._exit(0)     # dies without releasing: the outcome is unknown
''')


def test_lease_held_released_and_orphaned(study):
    lease = lock.acquire_lease(study.study_dir, 'e1', activity='eda.target_rate')
    assert lease.held and lock.lease_is_held(lease.path)
    with pytest.raises(StudyError) as info:
        lock.acquire_lease(study.study_dir, 'e1')
    assert info.value.code == 'lease_exists'
    assert lock.orphaned_leases(study.study_dir) == []
    with pytest.raises(StudyError):
        lock.remove_orphaned_lease(study.study_dir, 'e1')
    lease.release()
    lease.release()
    assert not lease.path.exists()

    proc = _spawn(LEASE, study.study_dir, 'e2')
    assert proc.stdout.readline().strip() == 'leased'
    proc.communicate(timeout=30)
    [orphan] = lock.orphaned_leases(study.study_dir)
    assert orphan['execution_id'] == 'e2' and orphan['activity'] == 'fit.logistic'
    assert orphan['pid'] == proc.pid
    lock.remove_orphaned_lease(study.study_dir, 'e2')
    assert lock.orphaned_leases(study.study_dir) == []
