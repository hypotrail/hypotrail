"""Read-only guard for notebook kernels (ADR 0001, finding 2).

When ``HYPOTRAIL_READ_ONLY=1`` is set, :func:`install` registers a Python audit hook
that refuses, inside ``<study>/.hypotrail``:

* any write-mode ``open``;
* ``os.rename`` and ``os.replace`` (as source or target);
* ``os.remove``, ``os.rmdir``, ``os.truncate``, ``shutil.rmtree``, and ``os.mkdir``.

Audit hooks cannot be removed, so the guard lasts for the whole process; a notebook
kernel never becomes a writer. Renderers call :func:`assert_writable` first, so a
render started from a read-only process is refused.

This is defence in depth, not a sandbox: ``ctypes`` or a subprocess can bypass it.
The structural guarantee is that the notebooks import only the read side
(:mod:`mlkit.study.read`, :mod:`mlkit.study.notebook_view`) and the pure policy
function, never a writer or an activity.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from .errors import StudyError

ENV = 'HYPOTRAIL_READ_ONLY'
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
_guarded: set[str] = set()
_installed = False


class ReadOnlyError(PermissionError):
    """Raised when a read-only process attempts to change study state."""


def read_only() -> bool:
    return os.environ.get(ENV) == '1'


def assert_writable() -> None:
    """Refuse (``read_only``) when this process is a read-only notebook kernel."""
    if read_only():
        raise StudyError('read_only',
                         f'{ENV}=1: this process is a read-only notebook kernel and may not '
                         'render or write study state.', details={'variable': ENV})


def _inside(path: object) -> bool:
    if isinstance(path, int) or path is None:
        return False
    try:
        resolved = str(Path(os.fsdecode(path)).resolve())
    except (TypeError, ValueError, OSError):
        return False
    return any(resolved == root or resolved.startswith(root + os.sep) for root in _guarded)


def _is_write_mode(mode: object, flags: object) -> bool:
    if isinstance(mode, str) and any(ch in mode for ch in 'wax+'):
        return True
    return isinstance(flags, int) and bool(flags & _WRITE_FLAGS)


def _hook(event: str, args: tuple) -> None:
    if not _guarded:
        return
    if event == 'open':
        path, mode, flags = (tuple(args) + (None, None, None))[:3]
        if _is_write_mode(mode, flags) and _inside(path):
            raise ReadOnlyError(f'{ENV}=1: write refused for {path}')
    elif event in {'os.rename', 'os.replace'}:
        if _inside(args[0]) or _inside(args[1]):
            raise ReadOnlyError(f'{ENV}=1: {event} refused for {args[0]}')
    elif event in {'os.remove', 'os.rmdir', 'os.truncate', 'shutil.rmtree', 'os.mkdir'}:
        if _inside(args[0]):
            raise ReadOnlyError(f'{ENV}=1: {event} refused for {args[0]}')


def install(study_dir) -> bool:
    """Protect ``<study>/.hypotrail`` in this process when read-only is set.

    Returns True when the guard is active for ``study_dir``.
    """
    global _installed
    if not read_only():
        return False
    _guarded.add(str((Path(study_dir) / '.hypotrail').resolve()))
    if not _installed:
        sys.addaudithook(_hook)
        _installed = True
    return True
