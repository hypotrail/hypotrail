"""Cross-platform primitives: file locks, atomic replace, virtual environments, display.

Standard library only, and no other ``mlkit`` import, so the legacy modules, the
integrations, and the study engine can all use it.

**File locks.** On Linux and macOS a lock is an ``fcntl.flock`` on the whole file; on
native Windows it is an ``msvcrt.locking`` lock on **one byte at** :data:`LOCK_OFFSET`,
far beyond the content. Windows byte-range locks are mandatory: a reader of a locked
range fails. Locking a byte outside the content keeps the holder and lease records
readable while they are held, as they are on POSIX. Both kinds are released by the
operating system when the process exits, which is what orphan detection relies on.
Windows has no shared lock in ``msvcrt``: a "shared" probe takes the exclusive byte for
an instant, so two concurrent probes may each see the other as a holder (they then
report a lease as held, the conservative answer).

**Atomic replace.** On Windows ``os.replace`` fails with ``PermissionError`` while
another process (the panel, Marimo, an antivirus, a search indexer) has the target
open without delete sharing. :func:`replace` retries a bounded number of times; the
same holds for :func:`unlink`.

No third-party lock package (``portalocker``, ``filelock``) is used: ``fcntl`` and
``msvcrt`` cover the three platforms in a few lines, and the study's locks need
non-blocking probes on files that stay readable, which this module controls directly.
"""
from __future__ import annotations

import importlib
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

LOCK_OFFSET = 1 << 30          # the locked byte on Windows: far beyond any lock-file content
POLL_SECONDS = 0.02
REPLACE_ATTEMPTS = 10
REPLACE_FIRST_DELAY = 0.05     # seconds; doubled each attempt, capped below
REPLACE_MAX_DELAY = 0.5
# A PermissionError from replace or unlink is a sharing violation worth retrying only on
# Windows; on POSIX it is a real permission problem. Tests set it to emulate Windows.
RETRY_SHARING_VIOLATIONS = os.name == 'nt'

_FORCED_BACKEND: str | None = None


class LockUnavailable(OSError):
    """No file-locking primitive exists on this platform."""


# --- file locks ---------------------------------------------------------------------------

def set_lock_backend(name: str | None) -> None:
    """Force ``'posix'`` or ``'windows'`` (tests that emulate Windows); None restores."""
    if name not in (None, 'posix', 'windows'):
        raise ValueError(name)
    global _FORCED_BACKEND
    _FORCED_BACKEND = name


def lock_backend() -> str | None:
    """``'posix'`` (fcntl), ``'windows'`` (msvcrt), or None when neither is importable."""
    if _FORCED_BACKEND is not None:
        return _FORCED_BACKEND
    for name, module in (('posix', 'fcntl'), ('windows', 'msvcrt')):
        try:
            importlib.import_module(module)
        except ImportError:
            continue
        return name
    return None


def require_locking() -> str:
    """The lock backend; raise :class:`LockUnavailable` if there is none."""
    backend = lock_backend()
    if backend is None:
        raise LockUnavailable(f'no file locking on this platform (os.name={os.name!r}, '
                              f'sys.platform={sys.platform!r}): neither fcntl nor msvcrt')
    return backend


def _windows_lock(fd: int, mode_name: str) -> None:
    msvcrt = importlib.import_module('msvcrt')
    position = os.lseek(fd, 0, os.SEEK_CUR)
    os.lseek(fd, LOCK_OFFSET, os.SEEK_SET)
    try:
        msvcrt.locking(fd, getattr(msvcrt, mode_name), 1)
    finally:
        os.lseek(fd, position, os.SEEK_SET)


def try_lock(fd: int, *, shared: bool = False) -> bool:
    """Take the lock of ``fd`` without waiting; True if taken, False if someone holds it.

    ``shared`` asks for a shared lock where the platform has one (POSIX); on Windows
    every lock is exclusive.
    """
    if require_locking() == 'posix':
        fcntl = importlib.import_module('fcntl')
        try:
            fcntl.flock(fd, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        return True
    try:
        _windows_lock(fd, 'LK_NBLCK')
    except OSError:              # PermissionError / EDEADLOCK: the byte is locked elsewhere
        return False
    return True


def unlock(fd: int) -> None:
    """Release the lock of ``fd`` taken by :func:`try_lock` or :func:`lock`."""
    if require_locking() == 'posix':
        fcntl = importlib.import_module('fcntl')
        fcntl.flock(fd, fcntl.LOCK_UN)
    else:
        _windows_lock(fd, 'LK_UNLCK')


def lock(fd: int, *, timeout: float | None = None) -> bool:
    """Wait for the exclusive lock of ``fd``; False if ``timeout`` seconds pass first."""
    if timeout is None and require_locking() == 'posix':
        fcntl = importlib.import_module('fcntl')
        fcntl.flock(fd, fcntl.LOCK_EX)
        return True
    deadline = None if timeout is None else time.monotonic() + timeout
    while not try_lock(fd):
        if deadline is not None and time.monotonic() >= deadline:
            return False
        time.sleep(POLL_SECONDS)
    return True


def open_lock_file(path, *, flags: int = os.O_RDWR) -> int:
    """Open (create) a lock or lease file as a binary descriptor."""
    return os.open(path, os.O_CREAT | flags | getattr(os, 'O_BINARY', 0), 0o600)


# --- replace and unlink with retries ------------------------------------------------------

def _retrying(operation, *args, attempts: int, sleep=None):
    sleep = sleep or time.sleep
    delay = REPLACE_FIRST_DELAY
    for attempt in range(attempts):
        try:
            return operation(*args)
        except PermissionError:
            # Windows: the target (or source) is open in another process without delete
            # sharing. On POSIX a PermissionError is a real permission problem: no retry.
            if not RETRY_SHARING_VIOLATIONS or attempt == attempts - 1:
                raise
            sleep(delay)
            delay = min(delay * 2, REPLACE_MAX_DELAY)


def replace(source, target, *, attempts: int = REPLACE_ATTEMPTS, sleep=None) -> None:
    """``os.replace(source, target)``, retried on Windows sharing violations.

    About five seconds in total before the last ``PermissionError`` is raised.
    """
    _retrying(os.replace, source, target, attempts=attempts, sleep=sleep)


def unlink(path, *, missing_ok: bool = True, attempts: int = REPLACE_ATTEMPTS,
           sleep=None) -> None:
    """Remove ``path``, retried on Windows sharing violations."""
    def remove(p):
        Path(p).unlink(missing_ok=missing_ok)
    _retrying(remove, path, attempts=attempts, sleep=sleep)


# --- virtual environments and command display -------------------------------------------

def is_windows() -> bool:
    return os.name == 'nt'


def venv_bin(venv) -> Path:
    """The scripts folder of a virtual environment: ``Scripts`` on Windows, else ``bin``."""
    return Path(venv) / ('Scripts' if is_windows() else 'bin')


def venv_executable(venv, name: str) -> Path:
    """An executable of a virtual environment (``python``, ``hypotrail``, ``marimo``)."""
    return venv_bin(venv) / (name + '.exe' if is_windows() else name)


def venv_python(venv) -> Path:
    """The interpreter of a virtual environment, on this platform."""
    return venv_executable(venv, 'python')


def display_command(argv) -> str:
    """One command line to show a person: ``list2cmdline`` on Windows, else ``shlex.join``.

    For display only; commands are always run as argument lists, without a shell.
    """
    argv = [str(a) for a in argv]
    return subprocess.list2cmdline(argv) if is_windows() else shlex.join(argv)
