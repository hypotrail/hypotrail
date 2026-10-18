"""Single-writer lock and per-execution leases of a study (POSIX only).

* The **writer lock** is an exclusive ``flock`` on ``.hypotrail/writer.lock``. Every
  mutation of study state happens under it: the command reads the state, applies
  one request, commits, and releases. The operating system releases the lock when
  the process exits, even abnormally, so a crashed writer never blocks the study.
* An **execution lease** is a file ``.hypotrail/executions/<execution_id>.lease``
  held with an exclusive ``flock`` by the process that computes an activity outside
  the writer lock. If the file exists but nobody holds its lock, the process died:
  the execution outcome is unknown (``interrupted_unknown``), and it is never
  restarted automatically.

Lease release and orphan checks both happen under the writer lock, so a lease that is
released normally is never mistaken for an orphan.

Native Windows is refused with ``platform_unsupported``: ``fcntl.flock`` does not exist
there. Linux, macOS, and WSL are supported.
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

from .errors import StudyError

HOME = '.hypotrail'
LOCK_FILE = 'writer.lock'
LEASE_DIR = 'executions'
LEASE_SUFFIX = '.lease'
DEFAULT_TIMEOUT = 30.0
POLL_SECONDS = 0.02


def require_posix() -> None:
    """Refuse native Windows, where POSIX file locking is unavailable."""
    if os.name == 'nt':
        raise StudyError('platform_unsupported',
                         'Hypotrail studies need POSIX file locking (fcntl.flock). '
                         'Use Linux, macOS, or WSL; native Windows is not supported.',
                         details={'os_name': os.name})


def _fcntl():
    require_posix()
    import fcntl
    return fcntl


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
    fcntl = _fcntl()
    path = _require_home(study_dir) / LOCK_FILE
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise StudyError('study_busy',
                                     'Another process is writing to this study; retry when it '
                                     'has finished.',
                                     details={'holder': _read_holder(path),
                                              'waited_seconds': timeout}) from None
                time.sleep(POLL_SECONDS)
        os.ftruncate(fd, 0)
        os.write(fd, json.dumps({'pid': os.getpid(), 'since': _now()}).encode())
        try:
            yield path
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _read_holder(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text() or 'null')
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
        """Remove the lease file, then drop its lock. Idempotent."""
        if self.fd is None:
            return
        fcntl = _fcntl()
        try:
            self.path.unlink(missing_ok=True)
            fcntl.flock(self.fd, fcntl.LOCK_UN)
        finally:
            os.close(self.fd)
            self.fd = None

    def __enter__(self) -> 'Lease':
        return self

    def __exit__(self, *exc) -> None:
        self.release()


def lease_path(study_dir, execution_id: str) -> Path:
    if not execution_id or '/' in execution_id or execution_id.startswith('.'):
        raise ValueError('invalid execution id')
    return home_of(study_dir) / LEASE_DIR / (execution_id + LEASE_SUFFIX)


def acquire_lease(study_dir, execution_id: str, **info) -> Lease:
    """Create and lock the lease of ``execution_id``; refuse if it already exists."""
    fcntl = _fcntl()
    _require_home(study_dir)
    path = lease_path(study_dir, execution_id)
    path.parent.mkdir(exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
    except FileExistsError:
        raise StudyError('lease_exists', f'Execution {execution_id} already has a lease.',
                         details={'execution_id': execution_id}) from None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        record = {'execution_id': execution_id, 'pid': os.getpid(),
                  'host': socket.gethostname(), 'acquired': _now(), **info}
        os.write(fd, json.dumps(record, sort_keys=True).encode())
        os.fsync(fd)
    except BaseException:
        path.unlink(missing_ok=True)
        os.close(fd)
        raise
    return Lease(execution_id, path, fd)


def lease_is_held(path: Path) -> bool:
    """True if a live process holds the lease lock at ``path``."""
    fcntl = _fcntl()
    try:
        fd = os.open(path, os.O_RDWR)
    except FileNotFoundError:
        return False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


def read_lease(path: Path) -> dict:
    try:
        return json.loads(path.read_text() or '{}')
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
    path.unlink(missing_ok=True)
