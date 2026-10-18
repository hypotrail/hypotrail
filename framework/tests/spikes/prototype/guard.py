"""Read-only guard for notebook kernels.

When ``HYPOTRAIL_READ_ONLY=1`` is set, ``install`` registers a Python audit
hook that refuses any write-mode ``open``, rename, replace, or removal that
targets the study's ``.hypotrail`` directory. Audit hooks cannot be removed,
so the guard lasts for the whole kernel process; this is intended, since a
notebook kernel must never become a writer.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ENV = "HYPOTRAIL_READ_ONLY"
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
_guarded: set[str] = set()


class ReadOnlyError(PermissionError):
    """Raised when a read-only process attempts to change study state."""


def read_only() -> bool:
    return os.environ.get(ENV) == "1"


def assert_writable() -> None:
    """Called by every writer before touching study state."""
    if read_only():
        raise ReadOnlyError(f"{ENV}=1: this process may not write study state")


def _inside(path: object) -> bool:
    if isinstance(path, int):
        return False
    try:
        resolved = str(Path(os.fsdecode(path)).resolve())
    except (TypeError, ValueError, OSError):
        return False
    return any(resolved == root or resolved.startswith(root + os.sep) for root in _guarded)


def _is_write_mode(mode: object, flags: object) -> bool:
    if isinstance(mode, str) and any(ch in mode for ch in "wax+"):
        return True
    return isinstance(flags, int) and bool(flags & _WRITE_FLAGS)


def _hook(event: str, args: tuple) -> None:
    if event == "open":
        path, mode, flags = (tuple(args) + (None, None, None))[:3]
        if _is_write_mode(mode, flags) and _inside(path):
            raise ReadOnlyError(f"{ENV}=1: write refused for {path}")
    elif event in {"os.rename", "os.replace"}:
        if _inside(args[0]) or _inside(args[1]):
            raise ReadOnlyError(f"{ENV}=1: {event} refused for {args[0]}")
    elif event in {"os.remove", "os.rmdir", "os.truncate", "shutil.rmtree", "os.mkdir"}:
        if _inside(args[0]):
            raise ReadOnlyError(f"{ENV}=1: {event} refused for {args[0]}")


def install(study_dir: Path) -> None:
    """Protect ``<study>/.hypotrail`` in this process when read-only is set."""
    if not read_only():
        return
    root = str((Path(study_dir) / ".hypotrail").resolve())
    if not _guarded:
        sys.addaudithook(_hook)
    _guarded.add(root)
