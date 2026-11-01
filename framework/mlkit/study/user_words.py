"""``--user-words-file``: the junior's verbatim words read from a file or stdin.

Every command that takes ``--user-words`` also takes ``--user-words-file PATH`` (``-``
for stdin), mutually exclusive with it. A shell is not a safe carrier for free text:
PowerShell and ``cmd.exe`` mangle quotes, apostrophes, and non-ASCII characters. The
file is read as UTF-8 (a leading byte-order mark, which Windows editors and PowerShell
5.1 write, is dropped) and only one trailing newline is removed; the words are kept
otherwise exactly as written. A file that is not valid UTF-8 is refused.

:func:`add` declares the pair on a parser; :func:`resolve`, called by the CLI once the
arguments are parsed, replaces the file by its words so that commands see one value.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

FILE_SUFFIX = '__file'
FILE_FLAG = '--user-words-file'


class WordsFileError(Exception):
    """The words file cannot be read; the CLI refuses with ``invalid_arguments``."""


def add(parser: argparse.ArgumentParser, *flags: str, dest: str = 'user_words',
        required: bool = False, help: str | None = None) -> None:
    """Add ``flags`` (default ``--user-words``) and ``--user-words-file``, exclusive."""
    group = parser.add_mutually_exclusive_group(required=required)
    group.add_argument(*(flags or ('--user-words',)), dest=dest, default=None, help=help)
    group.add_argument(FILE_FLAG, dest=dest + FILE_SUFFIX, default=None, metavar='PATH',
                       help='the same words read from a UTF-8 file (- for stdin), so that no '
                            'shell quoting can change them; one trailing newline is removed')


def strip_trailing_newline(text: str) -> str:
    """Remove one trailing ``\\n`` (or ``\\r\\n``), nothing else."""
    if text.endswith('\r\n'):
        return text[:-2]
    if text.endswith('\n'):
        return text[:-1]
    return text


def read(source: str, *, stdin=None) -> str:
    """The words of ``source`` (a path, or ``-`` for stdin)."""
    try:
        if source == '-':
            stream = stdin if stdin is not None else sys.stdin
            raw = stream.buffer.read() if hasattr(stream, 'buffer') else stream.read()
        else:
            raw = Path(source).read_bytes()
    except OSError as exc:
        raise WordsFileError(f'{FILE_FLAG} {source}: cannot be read ({exc.strerror or exc}).') \
            from None
    if isinstance(raw, str):
        text = raw
    else:
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError as exc:
            raise WordsFileError(f'{FILE_FLAG} {source}: not valid UTF-8 (byte {exc.start}); '
                                 'save the file as UTF-8 and retry.') from None
    return strip_trailing_newline(text)


def resolve(args: argparse.Namespace, *, stdin=None) -> argparse.Namespace:
    """Replace every ``<dest>__file`` given on ``args`` by the words it holds, in ``dest``."""
    for key in [k for k in vars(args) if k.endswith(FILE_SUFFIX)]:
        source = getattr(args, key)
        delattr(args, key)
        if source is not None:
            setattr(args, key[:-len(FILE_SUFFIX)], read(source, stdin=stdin))
    return args
