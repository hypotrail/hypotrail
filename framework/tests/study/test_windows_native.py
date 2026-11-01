"""Lot 4 (ONBOARDING-SPEC §3): native Windows support of the study engine.

* The writer lock and the execution leases run on either lock backend: ``fcntl.flock``
  (Linux, macOS) or ``msvcrt.locking`` on one byte beyond the content (Windows). On Linux
  the Windows branch runs against :mod:`fake_msvcrt` (per-handle byte-range locks), so
  the same semantics are checked: busy refusal with a readable holder, two processes
  contending, held, released, and orphaned leases.
* ``platform_compat.replace`` retries ``os.replace`` on Windows sharing violations.
* stdout is UTF-8 whatever the locale; ``--user-words-file`` carries the junior's words.

What only CI on ``windows-latest`` confirms: the real ``msvcrt`` (mandatory locks, lock
release when a process dies), a reader really blocking ``os.replace`` and ``unlink``,
and the console and pipe encodings. On that runner the whole study suite runs on the
real ``msvcrt`` backend, and the reader-holds-the-file test below meets real sharing
violations.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

import fake_msvcrt
from mlkit.study import case as c, cli, lock, platform_compat as pc, state as st, store as sto
from mlkit.study import user_words
from mlkit.study.errors import StudyError

TESTS = Path(__file__).resolve().parent
FRAMEWORK = TESTS.parents[1]

BACKENDS = [
    pytest.param('native', id='native'),
    pytest.param('windows', id='emulated-windows',
                 marks=pytest.mark.skipif(not fake_msvcrt.SUPPORTED or os.name == 'nt',
                                          reason='needs Linux open-file-description locks')),
]


def _env() -> dict:
    path = [str(FRAMEWORK), str(TESTS)] + [p for p in os.environ.get('PYTHONPATH', '')
                                           .split(os.pathsep) if p]
    return {**os.environ, 'PYTHONPATH': os.pathsep.join(path), 'PYTHONIOENCODING': ''}


def _spawn(code: str, *args) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, '-c', code, *map(str, args)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            encoding='utf-8', env=_env())


SETUP = textwrap.dedent('''
    import sys
    if sys.argv[1] == 'windows':
        import fake_msvcrt
        fake_msvcrt.install()
    from mlkit.study import lock
''')


@pytest.fixture
def backend(request, monkeypatch):
    name = request.param
    if name == 'windows':
        monkeypatch.setitem(sys.modules, 'msvcrt', fake_msvcrt.module())
        monkeypatch.setattr(pc, '_FORCED_BACKEND', 'windows')
        monkeypatch.setattr(pc, 'RETRY_SHARING_VIOLATIONS', True)
    return name


@pytest.fixture
def study(tmp_path, synthetic_case_dir):
    store = sto.StudyStore(tmp_path / 'study')
    store.create(st.initial_state(c.load_case(synthetic_case_dir)))
    return store


# --- the lock backends ------------------------------------------------------------------

def test_the_backend_is_chosen_by_what_the_platform_has(monkeypatch):
    assert pc.lock_backend() == ('windows' if os.name == 'nt' else 'posix')
    assert lock.require_locking() == pc.lock_backend()
    monkeypatch.setattr(pc, '_FORCED_BACKEND', 'windows')
    assert pc.lock_backend() == 'windows'
    with pytest.raises(ValueError):
        pc.set_lock_backend('vms')


@pytest.mark.parametrize('backend', BACKENDS, indirect=True)
def test_writer_lock_is_exclusive_per_handle_and_its_holder_stays_readable(study, backend):
    with lock.writer_lock(study.study_dir) as path:
        # Windows locks are mandatory on their range: the locked byte is beyond the content,
        # so the holder record reads back while the lock is held.
        assert path.stat().st_size < pc.LOCK_OFFSET
        assert json.loads(path.read_text(encoding='utf-8'))['pid'] == os.getpid()
        with pytest.raises(StudyError) as info:
            with lock.writer_lock(study.study_dir, timeout=0.1):
                pass
        assert info.value.code == 'study_busy'
        assert info.value.details['holder']['pid'] == os.getpid()
    with lock.writer_lock(study.study_dir, timeout=1):     # released on exit
        pass


CONTEND = SETUP + textwrap.dedent('''
    import os, time
    from pathlib import Path
    counter = Path(sys.argv[2]) / 'counter.txt'
    go = Path(sys.argv[2]) / 'go'
    while not go.exists():
        time.sleep(0.002)
    for _ in range(int(sys.argv[3])):
        with lock.writer_lock(sys.argv[2], timeout=60):
            value = int(counter.read_text(encoding='utf-8'))
            time.sleep(0.001)              # widen the window a missing lock would lose
            counter.write_text(str(value + 1), encoding='utf-8')
    print('done', flush=True)
''')


@pytest.mark.parametrize('backend', BACKENDS, indirect=True)
def test_two_processes_contending_for_the_writer_lock_lose_no_update(study, backend):
    """Concurrency test 1 (review B §6): two writers, every read-modify-write serialised."""
    counter = study.study_dir / 'counter.txt'
    counter.write_text('0', encoding='utf-8')
    rounds = 40
    procs = [_spawn(CONTEND, backend, study.study_dir, rounds) for _ in range(2)]
    (study.study_dir / 'go').write_text('', encoding='utf-8')
    for proc in procs:
        out, err = proc.communicate(timeout=120)
        assert proc.returncode == 0, err
        assert out.strip() == 'done'
    assert int(counter.read_text(encoding='utf-8')) == 2 * rounds


HOLD = SETUP + textwrap.dedent('''
    import time
    with lock.writer_lock(sys.argv[2]):
        print('held', flush=True)
        time.sleep(float(sys.argv[3]))
''')


@pytest.mark.parametrize('backend', BACKENDS, indirect=True)
def test_a_killed_writer_releases_the_lock(study, backend):
    holder = _spawn(HOLD, backend, study.study_dir, 30)
    assert holder.stdout.readline().strip() == 'held'
    with pytest.raises(StudyError) as info:
        with lock.writer_lock(study.study_dir, timeout=0.2):
            pass
    assert info.value.code == 'study_busy'
    assert info.value.details['holder']['pid'] == holder.pid
    holder.kill()
    holder.communicate(timeout=30)
    with lock.writer_lock(study.study_dir, timeout=5):
        pass


LEASE = SETUP + textwrap.dedent('''
    import os
    lock.acquire_lease(sys.argv[2], sys.argv[3], activity='fit.logistic')
    print('leased', flush=True)
    if sys.argv[4] == 'die':
        os._exit(0)     # dies without releasing: the outcome is unknown
    sys.stdin.readline()
''')


@pytest.mark.parametrize('backend', BACKENDS, indirect=True)
def test_leases_held_released_and_orphaned(study, backend):
    lease = lock.acquire_lease(study.study_dir, 'e1', activity='eda.target_rate')
    assert lease.held and lock.lease_is_held(lease.path)
    assert lock.read_lease(lease.path)['activity'] == 'eda.target_rate'   # readable while held
    assert lock.probe_leases(study.study_dir) == {'e1': True}
    assert lock.orphaned_leases(study.study_dir) == []
    with pytest.raises(StudyError) as info:
        lock.remove_orphaned_lease(study.study_dir, 'e1')
    assert info.value.code == 'lease_held'
    lease.release()
    lease.release()
    assert not lease.path.exists() and not lock.lease_is_held(lease.path)
    assert lock.probe_leases(study.study_dir) == {}

    # Another process alive and holding its lease: held, never an orphan.
    alive = subprocess.Popen([sys.executable, '-c', LEASE, backend, study.study_dir, 'e2',
                              'wait'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, env=_env())
    try:
        assert alive.stdout.readline().strip() == 'leased'
        assert lock.lease_is_held(lock.lease_path(study.study_dir, 'e2'))
        assert lock.orphaned_leases(study.study_dir) == []
    finally:
        alive.communicate('\n', timeout=30)
    # Its process ended without releasing: an orphan, with its record.
    [orphan] = lock.orphaned_leases(study.study_dir)
    assert orphan['execution_id'] == 'e2' and orphan['pid'] == alive.pid
    assert lock.probe_leases(study.study_dir) == {'e2': False}

    dead = _spawn(LEASE, backend, study.study_dir, 'e3', 'die')
    assert dead.stdout.readline().strip() == 'leased'
    dead.communicate(timeout=30)
    assert {o['execution_id'] for o in lock.orphaned_leases(study.study_dir)} == {'e2', 'e3'}
    lock.remove_orphaned_lease(study.study_dir, 'e2')
    lock.remove_orphaned_lease(study.study_dir, 'e3')
    assert lock.orphaned_leases(study.study_dir) == []


@pytest.mark.parametrize('backend', BACKENDS, indirect=True)
def test_an_emptied_lease_reads_as_starting_for_the_probe(study, backend):
    """The Windows release empties the record before unlocking; the read-only probe then
    counts the lease as held (starting), never as an interrupted execution."""
    folder = lock.home_of(study.study_dir) / lock.LEASE_DIR
    folder.mkdir(exist_ok=True)
    (folder / ('e9' + lock.LEASE_SUFFIX)).write_bytes(b'')
    assert lock.probe_leases(study.study_dir) == {'e9': True}


def test_a_lease_id_never_names_a_path():
    for bad in ('', '.x', 'a/b', 'a\\b'):
        with pytest.raises(ValueError):
            lock.lease_path('study', bad)


# --- replace with retries ---------------------------------------------------------------

def _flaky_replace(monkeypatch, failures: int) -> list:
    calls = []
    real = os.replace

    def replace(src, dst):
        calls.append((src, dst))
        if len(calls) <= failures:
            raise PermissionError(13, 'The process cannot access the file because it is '
                                      'being used by another process')
        return real(src, dst)
    monkeypatch.setattr(pc.os, 'replace', replace)
    return calls


def test_atomic_write_retries_a_sharing_violation(tmp_path, monkeypatch):
    """Concurrency test 2, emulated: a reader on Windows makes os.replace fail a few times."""
    monkeypatch.setattr(pc, 'RETRY_SHARING_VIOLATIONS', True)
    slept = []
    monkeypatch.setattr(pc.time, 'sleep', slept.append)
    target = tmp_path / 'state.json'
    target.write_text('old', encoding='utf-8')
    calls = _flaky_replace(monkeypatch, 3)
    sto.atomic_write(target, 'new é'.encode('utf-8'))
    assert target.read_text(encoding='utf-8') == 'new é'
    assert len(calls) == 4 and len(slept) == 3
    assert slept == sorted(slept) and max(slept) <= pc.REPLACE_MAX_DELAY
    assert [p.name for p in tmp_path.iterdir()] == ['state.json']      # no temporary left


def test_atomic_write_gives_up_after_bounded_retries(tmp_path, monkeypatch):
    monkeypatch.setattr(pc, 'RETRY_SHARING_VIOLATIONS', True)
    monkeypatch.setattr(pc.time, 'sleep', lambda s: None)
    target = tmp_path / 'state.json'
    target.write_text('old', encoding='utf-8')
    calls = _flaky_replace(monkeypatch, 10 ** 6)
    with pytest.raises(PermissionError):
        sto.atomic_write(target, b'new')
    assert len(calls) == pc.REPLACE_ATTEMPTS
    assert target.read_text(encoding='utf-8') == 'old'
    assert [p.name for p in tmp_path.iterdir()] == ['state.json']


def test_on_posix_a_permission_error_is_not_retried(tmp_path, monkeypatch):
    monkeypatch.setattr(pc, 'RETRY_SHARING_VIOLATIONS', False)
    calls = _flaky_replace(monkeypatch, 1)
    with pytest.raises(PermissionError):
        sto.atomic_write(tmp_path / 'x.json', b'{}')
    assert len(calls) == 1


def test_render_notebook_replaces_through_the_retrying_helper(monkeypatch):
    from mlkit.study import render_notebook
    assert render_notebook.platform_compat is pc
    source = Path(render_notebook.__file__).read_text(encoding='utf-8')
    assert 'os.replace(' not in source.replace('``os.replace``', '')


READER = textwrap.dedent('''
    import sys, time
    with open(sys.argv[1], 'rb') as handle:
        handle.read(1)
        print('open', flush=True)
        time.sleep(float(sys.argv[2]))
    print('closed', flush=True)
''')


def test_replace_while_another_process_reads_the_file(tmp_path):
    """Concurrency test 2, real: another process holds the target open. On POSIX the
    replace succeeds at once; on Windows it meets sharing violations until the reader
    closes the file, and the bounded retries outlast the reader."""
    target = tmp_path / 'report.html'
    target.write_text('old', encoding='utf-8')
    reader = _spawn(READER, target, 0.6)
    try:
        assert reader.stdout.readline().strip() == 'open'
        sto.atomic_write(target, b'new')
    finally:
        out, err = reader.communicate(timeout=30)
    assert reader.returncode == 0, err
    assert target.read_bytes() == b'new'


def test_unlink_retries_a_sharing_violation(tmp_path, monkeypatch):
    monkeypatch.setattr(pc, 'RETRY_SHARING_VIOLATIONS', True)
    monkeypatch.setattr(pc.time, 'sleep', lambda s: None)
    victim = tmp_path / 'e1.lease'
    victim.write_text('{}', encoding='utf-8')
    real, calls = Path.unlink, []

    def unlink(self, missing_ok=False):
        calls.append(self)
        if len(calls) < 3:
            raise PermissionError(13, 'in use')
        return real(self, missing_ok=missing_ok)
    monkeypatch.setattr(Path, 'unlink', unlink)
    pc.unlink(victim)
    assert len(calls) == 3 and not victim.exists()


# --- interpreter paths and display ------------------------------------------------------

@pytest.mark.parametrize('name, scripts, suffix', [('posix', 'bin', ''),
                                                   ('nt', 'Scripts', '.exe')])
def test_virtual_environment_paths_follow_the_platform(monkeypatch, name, scripts, suffix):
    monkeypatch.setattr(pc, 'is_windows', lambda: name == 'nt')
    venv = Path('framework') / '.venv'
    assert pc.venv_python(venv) == venv / scripts / ('python' + suffix)
    assert pc.venv_executable(venv, 'hypotrail') == venv / scripts / ('hypotrail' + suffix)


def test_display_command_quotes_for_the_platform(monkeypatch):
    argv = ['C:\\Program Files\\uv\\uv.exe', 'run', "l'étude"]
    monkeypatch.setattr(pc, 'is_windows', lambda: True)
    assert pc.display_command(argv) == '"C:\\Program Files\\uv\\uv.exe" run l\'étude'
    monkeypatch.setattr(pc, 'is_windows', lambda: False)
    assert pc.display_command(argv) == "'C:\\Program Files\\uv\\uv.exe' run 'l'\"'\"'étude'"


# --- UTF-8 output -----------------------------------------------------------------------

def test_cli_output_is_utf8_whatever_the_locale(tmp_path):
    """A pipe in a cp1252 locale (Windows' default) still receives UTF-8 JSON."""
    env = {**_env(), 'PYTHONIOENCODING': 'cp1252', 'PYTHONUTF8': '0'}
    proc = subprocess.run([sys.executable, '-m', 'mlkit.study.cli', 'status', '--study',
                           str(tmp_path / 'nowhere — étude ✓'), '--json'],
                          capture_output=True, env=env, cwd=tmp_path, timeout=120)
    payload = json.loads(proc.stdout.decode('utf-8'))
    assert payload['ok'] is False
    assert 'nowhere — étude ✓' in json.dumps(payload, ensure_ascii=False)


def test_utf8_streams_leaves_a_replaced_stream_alone(monkeypatch):
    class Plain:
        def write(self, text):
            return len(text)
    monkeypatch.setattr(sys, 'stdout', Plain())
    cli.utf8_streams()


# --- --user-words-file ------------------------------------------------------------------

WORDS = "Oui : on prédit avant l'envoi du premier rappel — c'est « notre » moment.\n\n  "


@pytest.mark.parametrize('argv, dest', [
    (['decide', 'confirm', 'p_1'], 'user_words'),
    (['decide', 'note', '--about', 'prediction_time'], 'text'),
    (['mode', 'set', 'express'], 'user_words'),
    (['run', 'split'], 'user_words'),
    (['automation', 'stop'], 'user_words'),
    (['brief', 'set'], 'user_words'),
])
def test_every_user_words_flag_has_a_file_twin(tmp_path, argv, dest):
    common = ['--request-id', 'r1', '--expected-revision', '1', '--study', str(tmp_path)]
    path = tmp_path / 'words.txt'
    path.write_bytes(b'\xef\xbb\xbf' + WORDS.encode('utf-8') + b'\n')   # BOM, as Notepad
    extension = argv[0] if argv[0] in cli.EXTENSIONS else None
    args = cli.build_parser(extension).parse_args(argv + ['--user-words-file', str(path)]
                                                  + common)
    user_words.resolve(args)
    assert getattr(args, dest) == WORDS          # one trailing newline removed, nothing else
    assert not any(k.endswith(user_words.FILE_SUFFIX) for k in vars(args))
    flag = '--text' if dest == 'text' else '--user-words'
    with pytest.raises(cli.ArgumentError, match='not allowed with'):
        cli.build_parser(extension).parse_args(argv + [flag, 'x', '--user-words-file',
                                                       str(path)] + common)


def test_the_words_file_is_read_exactly(tmp_path):
    path = tmp_path / 'w.txt'
    for raw, words in ((b'a\r\n', 'a'), (b'a\n\n', 'a\n'), (b'a', 'a'), (b' a \t', ' a \t'),
                       (b'', '')):
        path.write_bytes(raw)
        assert user_words.read(str(path)) == words

    class Stdin:
        class buffer:
            @staticmethod
            def read():
                return "d'accord\n".encode('utf-8')
    assert user_words.read('-', stdin=Stdin) == "d'accord"
    path.write_bytes('é'.encode('cp1252'))
    with pytest.raises(user_words.WordsFileError, match='not valid UTF-8'):
        user_words.read(str(path))
    with pytest.raises(user_words.WordsFileError, match='cannot be read'):
        user_words.read(str(tmp_path / 'missing.txt'))


def _hyp(*args, cwd, stdin=None):
    proc = subprocess.run([sys.executable, '-m', 'mlkit.study.cli', *map(str, args)],
                          capture_output=True, cwd=cwd, env=_env(), timeout=120, input=stdin)
    assert proc.stderr == b'', proc.stderr
    return proc.returncode, json.loads(proc.stdout.decode('utf-8'))


def test_confirm_with_a_words_file_records_the_words_verbatim(tmp_path, synthetic_case_dir):
    work = tmp_path / 'cwd'
    work.mkdir()
    target = tmp_path / 'study'
    assert _hyp('init', '--case', synthetic_case_dir, '--study', target, cwd=work)[0] == 0
    code, out = _hyp('decide', 'propose', 'prediction_time', '--value',
                     'before the first reminder is sent', '--restatement',
                     'You predict before the first reminder is sent.', '--rationale',
                     'It matches the scenario.', '--request-id', 'r1',
                     '--expected-revision', 1, '--study', target, cwd=work)
    assert code == 0, out
    pid = out['result']['proposal_id']
    words = "Oui : on prédit avant l'envoi du premier rappel, c'est le bon moment."
    file = tmp_path / 'words.txt'
    file.write_text(words + '\n', encoding='utf-8')
    code, out = _hyp('decide', 'confirm', pid, '--user-words-file', file, '--request-id', 'r2',
                     '--expected-revision', 2, '--study', target, cwd=work)
    assert code == 0, out
    assert out['result']['status'] == 'confirmed'
    view = _hyp('status', '--study', target, '--json', cwd=work)[1]['view']
    assert view['decisions']['prediction_time']['confirmation']['user_words'] == words

    # stdin, and a refusal that names the problem for a file that is not UTF-8
    code, out = _hyp('decide', 'note', '--about', 'prediction_time', '--user-words-file', '-',
                     '--request-id', 'r3', '--expected-revision', 3, '--study', target,
                     cwd=work, stdin="Seulement si l'équipe valide.\n".encode('utf-8'))
    assert code == 0, out
    bad = tmp_path / 'bad.txt'
    bad.write_bytes('prédit'.encode('cp1252'))
    code, out = _hyp('decide', 'note', '--about', 'prediction_time', '--user-words-file', bad,
                     '--request-id', 'r4', '--expected-revision', 4, '--study', target,
                     cwd=work)
    assert code == 2 and out['error']['code'] == 'invalid_arguments'
    assert 'not valid UTF-8' in out['error']['message']
