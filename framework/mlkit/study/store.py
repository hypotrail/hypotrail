"""Durable storage of a study under ``<study>/.hypotrail/`` (plan §3).

Layout::

    .hypotrail/
      state.json          the single source of truth (hypotrail.study/1)
      state.sha256        digest of state.json; a mismatch is an integrity_error
      revisions.jsonl     one line per committed revision (append-only)
      events.jsonl        operational events (append-only)
      registry/<rid>.json immutable result entries (written once)
      blobs/<sha256>      immutable content-addressed bytes (written once)
      registry-index.jsonl input_key -> result_id index (append-only; registry.py)
      exposure.jsonl      data-exposure log keyed by row key (append-only; exposure.py)
      executions/         execution records and leases (see lock.py)
      writer.lock         the single-writer lock (see lock.py)
      transaction.json    present only while a command is being applied
      commit.pending.json present only while a commit is being finished

Writes are atomic: a temporary file in the same directory, fsync, then
``os.replace``. Registry entries and blobs are created with ``O_EXCL`` and never
rewritten. A study is named explicitly (``--study DIR``) and recognised by its
``.hypotrail/`` marker; it is never searched for, and there is no global index.

:class:`StudyStore` is also the store that :func:`mlkit.reliability.apply_command`
needs. Use :meth:`StudyStore.execute` (or :meth:`StudyStore.writing`) so every
command runs under the writer lock on freshly reread state.

Commit protocol. ``commit`` writes ``commit.pending.json`` (the new state digest and
the revision record), replaces ``state.json`` (the commit point), writes
``state.sha256``, appends the revision record, and removes the pending file. A crash
after the commit point leaves a consistent state that readers accept and that the
next writer completes; a crash before it leaves the previous state untouched.

This module imports neither pandas, numpy, nor scikit-learn.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Iterator, Mapping

from mlkit import reliability

from . import guard, lock, state as st
from .errors import StudyError

HOME = lock.HOME
REVISIONS_FILE = 'revisions.jsonl'
EVENTS_FILE = 'events.jsonl'
TRANSACTION_FILE = 'transaction.json'
PENDING_FILE = 'commit.pending.json'
REGISTRY_DIR = 'registry'
BLOBS_DIR = 'blobs'


# --- low-level writes -------------------------------------------------------------------

def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def atomic_write(path: Path, data: bytes) -> None:
    """Replace ``path`` with ``data`` atomically (temporary file, fsync, os.replace)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f'.{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp')
    try:
        with open(temp, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    _fsync_dir(path.parent)


def atomic_write_json(path: Path, obj) -> None:
    atomic_write(path, (json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + '\n')
                 .encode('utf-8'))


def write_once(path: Path, data: bytes) -> bool:
    """Create ``path`` with ``data`` exclusively (``O_EXCL``); never rewrite it.

    Returns True if the file was created, False if it already holds exactly ``data``.
    Different existing bytes are an ``integrity_error``: an immutable object never
    changes. A failed write removes its partial file.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        if path.read_bytes() == data:
            return False
        raise StudyError('integrity_error', f'Immutable file {path.name} already exists with '
                                            'different content.',
                         details={'path': str(path)}) from None
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    _fsync_dir(path.parent)
    return True


def append_jsonl(path: Path, record: Mapping) -> None:
    """Append one JSON line durably. A torn final line from a crash is closed first."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True, ensure_ascii=False) + '\n'
    with open(path, 'ab+') as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell():
            handle.seek(-1, os.SEEK_END)
            if handle.read(1) != b'\n':
                handle.write(b'\n')
        handle.write(line.encode('utf-8'))
        handle.flush()
        os.fsync(handle.fileno())


def read_jsonl(path: Path) -> list[dict]:
    """Records of an append-only log. Lines that are not JSON (torn writes) are skipped."""
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


# --- the study store --------------------------------------------------------------------

class StudyStore:
    """Persistence of one study, and the store protocol of ``apply_command``."""

    reread_hint = 'hypotrail status'

    def __init__(self, study_dir, *, tracked: tuple[str, ...] = ()):
        self.study_dir = Path(study_dir).resolve()
        self.home = self.study_dir / HOME
        # Mutable files (relative to the study directory) that a command may change
        # besides state.json; apply_command restores them if the command fails. The study
        # commands track none: inside a transaction they change state.json only. Every
        # other write is immutable (registry entries, blobs), append-only (revisions,
        # events, exposure, the registry index), informative (execution histories), or
        # made after the commit (rendered artefacts), so a failed command has nothing
        # else to restore. The parameter stays for the apply_command store protocol.
        self.tracked = tuple(tracked)
        for name in self.tracked:
            self._inside(name)

    # paths

    @property
    def state_path(self) -> Path:
        return self.home / st.STATE_FILE

    @property
    def sha_path(self) -> Path:
        return self.home / st.SHA_FILE

    @property
    def revisions_path(self) -> Path:
        return self.home / REVISIONS_FILE

    @property
    def events_path(self) -> Path:
        return self.home / EVENTS_FILE

    @property
    def transaction_path(self) -> Path:
        return self.home / TRANSACTION_FILE

    @property
    def pending_path(self) -> Path:
        return self.home / PENDING_FILE

    def exists(self) -> bool:
        return self.state_path.is_file()

    def _inside(self, name: str) -> Path:
        path = (self.study_dir / name).resolve()
        if not path.is_relative_to(self.study_dir):
            raise ValueError(f'{name} is outside the study directory')
        return path

    # creation and reading

    def create(self, state: dict, *, timeout: float = lock.DEFAULT_TIMEOUT) -> dict:
        """Write the first revision of a new study; refuse if one exists (``state_exists``).

        ``state`` comes from :func:`mlkit.study.state.initial_state` (revision 0).
        """
        guard.assert_writable()
        lock.require_posix()
        if self.exists():
            raise StudyError('state_exists', 'A study already exists here; it is never '
                                             'overwritten.',
                             details={'study': str(self.study_dir)})
        self.home.mkdir(parents=True, exist_ok=True)
        with lock.writer_lock(self.study_dir, timeout=timeout):
            if self.exists():
                raise StudyError('state_exists', 'A study already exists here; it is never '
                                                 'overwritten.',
                                 details={'study': str(self.study_dir)})
            if state.get('revision') != 0:
                raise StudyError('invalid_state', 'A new study starts from revision 0.')
            self.commit(state, {'request_id': None, 'action': 'init', 'params': {},
                                'result': {'case': state['case']['id']}})
            self.event('study_created', revision=state['revision'])
        return state

    def _pending(self) -> dict | None:
        try:
            return json.loads(self.pending_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None

    def load_state(self) -> dict:
        """Read and verify state; refuse a divergent or invalid one (``integrity_error``).

        Read-only: it never repairs anything, so ``status`` can call it without the lock.
        A read that overlaps a commit is retried (:func:`mlkit.study.read.load_state`).
        """
        from . import read   # the read side; it never imports this module

        return read.load_state(self.study_dir)

    def revisions(self, since: int = 0) -> list[dict]:
        """Revision records after revision ``since``, oldest first."""
        return [r for r in read_jsonl(self.revisions_path) if r.get('revision', 0) > since]

    # writing under the lock

    def finish_pending_commit(self) -> bool:
        """Complete a commit interrupted after its commit point, or discard one that
        never reached it. Call under the writer lock. Returns True if one was found."""
        pending = self._pending()
        if pending is None:
            self.pending_path.unlink(missing_ok=True)
            return False
        data = self.state_path.read_bytes() if self.exists() else b''
        if st.digest(data) == pending['state_sha256']:
            atomic_write(self.sha_path, st.sha_line(pending['state_sha256']).encode())
            record = pending['record']
            logged = read_jsonl(self.revisions_path)
            if not logged or logged[-1].get('revision', 0) < record['revision']:
                append_jsonl(self.revisions_path, record)
            self.event('commit_completed_after_interruption', revision=record['revision'])
        self.pending_path.unlink(missing_ok=True)
        return True

    @contextlib.contextmanager
    def writing(self, *, timeout: float = lock.DEFAULT_TIMEOUT) -> Iterator[dict]:
        """Hold the writer lock and yield freshly reread, recovered state.

        Refused (``read_only``) in a read-only process (``HYPOTRAIL_READ_ONLY=1``): every
        mutation of a study goes through here or through :meth:`create`.
        """
        guard.assert_writable()
        with lock.writer_lock(self.study_dir, timeout=timeout):
            self.finish_pending_commit()
            state = self.load_state()
            reliability.rollback_transaction(self, state)
            yield state

    def execute(self, request: Mapping, handlers: Mapping[str, reliability.Handler], *,
                timeout: float = lock.DEFAULT_TIMEOUT, on_commit=None) -> dict:
        """Apply one command under the writer lock; return its receipt.

        Refusals raise :class:`mlkit.reliability.CommandRefused`. ``on_commit(state)``, when
        given, runs under the same lock right after the command commits (never for a refusal
        or a replay); the committed command stands whatever it does.
        """
        guard.assert_writable()
        with self.writing(timeout=timeout) as state:
            receipt = reliability.apply_command(self, state, request, handlers)
            if on_commit is not None and not receipt.get('replayed'):
                on_commit(state)
            return receipt

    # immutable objects

    def put_blob(self, data: bytes) -> str:
        """Store ``data`` under its sha256 and return the digest."""
        sha = hashlib.sha256(data).hexdigest()
        write_once(self.home / BLOBS_DIR / sha, data)
        return sha

    def read_blob(self, sha: str) -> bytes:
        path = self.home / BLOBS_DIR / sha
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != sha:
            raise StudyError('integrity_error', f'Blob {sha} does not match its digest.',
                             details={'path': str(path)})
        return data

    def put_registry(self, rid: str, entry: Mapping) -> bool:
        """Write registry entry ``rid`` once. Identity is checked by the registry (WP1.3).

        The entry is written in the key order it is given: :func:`mlkit.study.registry.put`
        sorts every key except those of ``output.values``, which keep their emitted order."""
        if not rid or '/' in rid or rid.startswith('.'):
            raise ValueError('invalid result id')
        data = (json.dumps(entry, indent=2, ensure_ascii=False) + '\n').encode()
        return write_once(self.home / REGISTRY_DIR / f'{rid}.json', data)

    def read_registry(self, rid: str) -> dict:
        return json.loads((self.home / REGISTRY_DIR / f'{rid}.json').read_text(encoding='utf-8'))

    # store protocol of reliability.apply_command

    def snapshot_files(self) -> dict:
        out = {}
        for name in self.tracked:
            path = self._inside(name)
            out[name] = path.read_text(encoding='utf-8') if path.exists() else None
        return out

    def write_transaction(self, row: dict) -> None:
        atomic_write_json(self.transaction_path, row)

    def read_transaction(self) -> dict | None:
        if not self.transaction_path.exists():
            return None
        return json.loads(self.transaction_path.read_text(encoding='utf-8'))

    def clear_transaction(self) -> None:
        self.transaction_path.unlink(missing_ok=True)

    def restore_file(self, name: str, content: str | None) -> None:
        path = self._inside(name)
        if content is None:
            path.unlink(missing_ok=True)
        else:
            atomic_write(path, content.encode('utf-8'))

    def mutating(self):
        return contextlib.nullcontext()

    def commit(self, state: dict, change: Mapping) -> None:
        """Persist ``state`` as the next revision and log ``change``.

        An invalid state is refused before anything is written. Failures after the
        commit point are left to :meth:`finish_pending_commit` and do not raise: the
        command has committed.
        """
        candidate = dict(state)
        candidate['revision'] = state.get('revision', 0) + 1
        candidate['updated'] = st.now()
        st.check_state(candidate)
        data = st.dumps(candidate)
        sha = st.digest(data)
        record = {'revision': candidate['revision'], 'time': candidate['updated'],
                  'state_sha256': sha, **change}
        atomic_write_json(self.pending_path, {'state_sha256': sha, 'record': record})
        atomic_write(self.state_path, data)                       # commit point
        state['revision'] = candidate['revision']
        state['updated'] = candidate['updated']
        try:
            atomic_write(self.sha_path, st.sha_line(sha).encode())
            append_jsonl(self.revisions_path, record)
            self.pending_path.unlink(missing_ok=True)
        except OSError:
            pass   # completed by finish_pending_commit under the next writer lock

    def event(self, kind: str, **fields) -> None:
        append_jsonl(self.events_path, {'time': st.now(), 'kind': kind, **fields})

    def changes_since(self, revision: int) -> list:
        return self.revisions(revision)

    def recover(self, state: dict) -> dict:
        reliability.rollback_transaction(self, state)
        return state
