"""Single-writer lock and per-execution leases of a study (Linux, macOS, Windows).

* The **writer lock** is an exclusive lock on ``.hypotrail/writer.lock``. Every
  mutation of study state happens under it: the command reads the state, applies
  one request, commits, and releases. The operating system releases the lock when
  the process exits, even abnormally, so a crashed writer never blocks the study.
* An **execution lease** is a file ``.hypotrail/executions/<execution_id>.lease``
  held with an exclusive lock by the process that computes an activity outside
  the writer lock. If the file exists but nobody holds its lock, the process died:
  the execution outcome is unknown (``interrupted_unknown``), and it is never
  restarted automatically.

Lease release and orphan checks both happen under the writer lock, so a lease that is
released normally is never mistaken for an orphan.

The lock primitive comes from :mod:`.platform_compat`: ``fcntl.flock`` on Linux and
macOS, ``msvcrt.locking`` on one byte far beyond the content on native Windows (Windows
locks are mandatory on their range, and the holder and lease records must stay
readable). On Windows a lease file cannot be removed while it is open, so a lease is
released by emptying it, unlocking, closing, then removing it (an empty lease file reads
as "starting", hence held, for the read-only probe). A platform with neither primitive
is refused with ``platform_unsupported``.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import json
import os
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from . import platform_compat as pc
from .errors import StudyError

HOME = '.hypotrail'
LOCK_FILE = 'writer.lock'
LEASE_DIR = 'executions'
LEASE_SUFFIX = '.lease'
DEFAULT_TIMEOUT = 30.0
POLL_SECONDS = 0.02
PROBE_GRACE_SECONDS = 1.0


def require_locking() -> str:
    """The file-lock backend (``posix`` or ``windows``); refuse a platform without one."""
    try:
        return pc.require_locking()
    except pc.LockUnavailable as exc:
        raise StudyError('platform_unsupported',
                         'Hypotrail studies need file locking (fcntl on Linux and macOS, '
                         'msvcrt on Windows), and neither is available here.',
                         details={'os_name': os.name, 'reason': str(exc)}) from None


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def home_of(study_dir) -> Path:
    return Path(study_dir) / HOME


def _require_home(study_dir) -> Path:
    home = home_of(study_dir)
    if not home.is_dir():
        raise StudyError('study_missing', f'No study here: {home} does not exist.',
                         details={'study': str(study_dir)})
    return home


@contextlib.contextmanager
def writer_lock(study_dir, *, timeout: float = DEFAULT_TIMEOUT) -> Iterator[Path]:
    """Hold the study writer lock; wait up to ``timeout`` seconds, then refuse.

    ``.hypotrail/`` must already exist: taking the lock never creates a study marker.
    The refusal ``study_busy`` names the process that holds the lock, when known.
    """
    require_locking()
    path = _require_home(study_dir) / LOCK_FILE
    fd = pc.open_lock_file(path)
    try:
        deadline = time.monotonic() + timeout
        while not pc.try_lock(fd):
            if time.monotonic() >= deadline:
                raise StudyError('study_busy',
                                 'Another process is writing to this study; retry when it '
                                 'has finished.',
                                 details={'holder': _read_holder(path),
                                          'waited_seconds': timeout})
            time.sleep(POLL_SECONDS)
        os.ftruncate(fd, 0)
        os.write(fd, json.dumps({'pid': os.getpid(), 'since': _now()}).encode())
        try:
            yield path
        finally:
            pc.unlock(fd)
    finally:
        os.close(fd)


def _read_holder(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding='utf-8') or 'null')
    except (OSError, ValueError):
        return None


# --- execution leases -------------------------------------------------------------------

@dataclass
class Lease:
    """A held execution lease. Release it under the writer lock."""

    execution_id: str
    path: Path
    fd: int | None

    @property
    def held(self) -> bool:
        return self.fd is not None

    def release(self) -> None:
        """Remove the lease file, then drop its lock. Idempotent.

        POSIX removes the file first, so nobody ever sees it unlocked. Windows cannot
        remove an open file: the record is emptied first (an empty lease reads as held),
        then the lock is dropped, the file closed and removed (with retries).
        """
        if self.fd is None:
            return
        if require_locking() == 'posix':
            try:
                self.path.unlink(missing_ok=True)
                pc.unlock(self.fd)
            finally:
                os.close(self.fd)
                self.fd = None
            return
        try:
            os.ftruncate(self.fd, 0)
            pc.unlock(self.fd)
        finally:
            os.close(self.fd)
            self.fd = None
        pc.unlink(self.path)

    def __enter__(self) -> 'Lease':
        return self

    def __exit__(self, *exc) -> None:
        self.release()


def lease_path(study_dir, execution_id: str) -> Path:
    if not execution_id or '/' in execution_id or '\\' in execution_id \
            or execution_id.startswith('.'):
        raise ValueError('invalid execution id')
    return home_of(study_dir) / LEASE_DIR / (execution_id + LEASE_SUFFIX)


def acquire_lease(study_dir, execution_id: str, **info) -> Lease:
    """Create and lock the lease of ``execution_id``; refuse if it already exists."""
    require_locking()
    _require_home(study_dir)
    path = lease_path(study_dir, execution_id)
    path.parent.mkdir(exist_ok=True)
    try:
        fd = pc.open_lock_file(path, flags=os.O_EXCL | os.O_RDWR)
    except FileExistsError:
        raise StudyError('lease_exists', f'Execution {execution_id} already has a lease.',
                         details={'execution_id': execution_id}) from None
    try:
        # A read-only probe (:func:`lease_is_held`, from ``status``) may hold a shared lock
        # on the new file for an instant; nobody else can, since the file is ours (O_EXCL).
        if not pc.lock(fd, timeout=PROBE_GRACE_SECONDS):
            raise BlockingIOError(f'lease {execution_id} stayed locked by a probe')
        record = {'execution_id': execution_id, 'pid': os.getpid(),
                  'host': socket.gethostname(), 'acquired': _now(), **info}
        os.write(fd, json.dumps(record, sort_keys=True).encode())
        os.fsync(fd)
    except BaseException:
        os.close(fd)
        pc.unlink(path)
        raise
    return Lease(execution_id, path, fd)


def lease_is_held(path: Path) -> bool:
    """True if a live process holds the lease lock at ``path``.

    A read-only check: it opens the file read-only and tries a non-blocking *shared*
    lock, which fails only while the computing process holds its exclusive lock. It
    writes nothing and needs no writer lock, so ``status`` may call it (F1). On Windows
    the probe lock is exclusive for an instant (``msvcrt`` has no shared lock).
    """
    backend = require_locking()
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_BINARY', 0))
    except FileNotFoundError:
        return False
    except PermissionError:
        if backend == 'posix':
            raise
        return False      # Windows: a removal is pending, so its execution has ended
    try:
        if not pc.try_lock(fd, shared=True):
            return True
        pc.unlock(fd)
        return False
    finally:
        os.close(fd)


def probe_leases(study_dir) -> dict[str, bool]:
    """Read-only liveness probe of every execution lease: ``{execution_id: held}``.

    Used by ``status`` without the writer lock (F1). Take the probe **before** reading
    the state: an execution reserved after the probe has no entry here and is treated as
    running, and a lease is always taken before its reservation is committed. A lease
    file that is still empty belongs to a process that is starting: it counts as held.
    """
    folder = home_of(study_dir) / LEASE_DIR
    if not folder.is_dir():
        return {}
    out = {}
    for path in sorted(folder.glob('*' + LEASE_SUFFIX)):
        eid = path.name[:-len(LEASE_SUFFIX)]
        held = lease_is_held(path)
        if not held:
            try:
                held = not path.read_text(encoding='utf-8').strip()
            except OSError:
                continue          # removed meanwhile: its execution ended normally
        out[eid] = held
    return out


def read_lease(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding='utf-8') or '{}')
    except ValueError:
        return {}


def orphaned_leases(study_dir) -> list[dict]:
    """Leases whose process is gone: their executions have an unknown outcome.

    Call it under the writer lock. Each item is the lease record plus ``path``.
    """
    folder = home_of(study_dir) / LEASE_DIR
    if not folder.is_dir():
        return []
    found = []
    for path in sorted(folder.glob('*' + LEASE_SUFFIX)):
        if not lease_is_held(path):
            record = read_lease(path)
            record.setdefault('execution_id', path.name[:-len(LEASE_SUFFIX)])
            found.append({**record, 'path': str(path)})
    return found


def remove_orphaned_lease(study_dir, execution_id: str) -> None:
    """Delete an orphaned lease once its interruption is recorded (under the writer lock)."""
    path = lease_path(study_dir, execution_id)
    if lease_is_held(path):
        raise StudyError('lease_held', f'Execution {execution_id} is still running.',
                         details={'execution_id': execution_id})
    pc.unlink(path)
