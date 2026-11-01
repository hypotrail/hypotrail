"""A stand-in for Windows' ``msvcrt.locking`` on Linux, for the Lot 4 tests.

It locks the requested byte range at the descriptor's current position with an
open-file-description lock (``F_OFD_SETLK``), which, like a Windows lock, belongs to one
open handle (two handles of the same process conflict) and is released when the handle
is closed or the process exits. A read-only handle takes a read lock (it would conflict
with a holder's write lock), as ``msvcrt`` lets a read handle lock a range.

What it cannot emulate: Windows locks are mandatory (a read of the locked range fails),
and a file open in another process cannot be removed or replaced. Only CI on
``windows-latest`` with the real ``msvcrt`` checks those.
"""
from __future__ import annotations

import errno
import fcntl
import os
import struct
import sys
import types

LK_UNLCK, LK_LCK, LK_NBLCK, LK_RLCK, LK_NBRLCK = 0, 1, 2, 3, 4
SUPPORTED = sys.platform.startswith('linux') and hasattr(fcntl, 'F_OFD_SETLK')


def locking(fd: int, mode: int, nbytes: int) -> None:
    start = os.lseek(fd, 0, os.SEEK_CUR)
    if mode == LK_UNLCK:
        kind = fcntl.F_UNLCK
    else:
        readonly = fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY
        kind = fcntl.F_RDLCK if readonly else fcntl.F_WRLCK
    # struct flock: l_type, l_whence, l_start, l_len, l_pid (0 for OFD locks), padding.
    record = struct.pack('hhqqi4x', kind, os.SEEK_SET, start, nbytes, 0)
    try:
        fcntl.fcntl(fd, fcntl.F_OFD_SETLK, record)
    except OSError as exc:
        if exc.errno in (errno.EAGAIN, errno.EACCES):
            raise PermissionError(errno.EACCES, 'Permission denied') from None   # as msvcrt
        raise


def module() -> types.ModuleType:
    fake = types.ModuleType('msvcrt')
    for name in ('LK_UNLCK', 'LK_LCK', 'LK_NBLCK', 'LK_RLCK', 'LK_NBRLCK'):
        setattr(fake, name, globals()[name])
    fake.locking = locking
    return fake


def install() -> None:
    """Make this process use the emulated Windows locks (subprocess helpers call it)."""
    from mlkit.study import platform_compat
    sys.modules['msvcrt'] = module()
    platform_compat.set_lock_backend('windows')
