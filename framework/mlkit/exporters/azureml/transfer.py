"""What Azure ML would upload from a project folder (``code:`` and ``.amlignore``).

Azure ML uploads the ``code:`` folder minus the paths matched by its ``.amlignore`` (which
takes precedence over ``.gitignore``), with gitignore pattern semantics. This module
implements the subset of those semantics that ``.amlignore`` files use here: comments,
blank lines, ``!`` negation, a trailing ``/`` for folders only, a ``/`` inside the pattern
anchoring it to the root, ``*``, ``?``, ``[...]`` within one path component and ``**``
across components. A path inside an ignored folder is ignored (a negation cannot
re-include it, as in git).

The export tests the **effective** upload with :func:`transferable` rather than the mere
presence of ``.amlignore``. Standalone (standard library only): it is copied byte for byte
into the generated project (``src/pipeline/utils/hypotrail/transfer.py``).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Rule:
    pattern: re.Pattern
    negate: bool
    directory_only: bool


def _translate(glob: str) -> str:
    out, i = [], 0
    while i < len(glob):
        c = glob[i]
        if glob.startswith('**/', i):
            out.append('(?:.*/)?')
            i += 3
        elif glob.startswith('/**', i) and i + 3 == len(glob):
            out.append('/.*')
            i += 3
        elif glob.startswith('**', i):
            out.append('.*')
            i += 2
        elif c == '*':
            out.append('[^/]*')
            i += 1
        elif c == '?':
            out.append('[^/]')
            i += 1
        elif c == '[':
            end = glob.find(']', i + 1)
            if end < 0:
                out.append(re.escape(c))
                i += 1
            else:
                body = glob[i + 1:end].replace('\\', '\\\\')
                if body.startswith('!'):
                    body = '^' + body[1:]
                out.append(f'[{body}]')
                i = end + 1
        else:
            out.append(re.escape(c))
            i += 1
    return ''.join(out)


def parse(text: str) -> list[Rule]:
    rules = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line.startswith('#'):
            continue
        negate = line.startswith('!')
        if negate:
            line = line[1:]
        directory_only = line.endswith('/')
        line = line.rstrip('/')
        anchored = '/' in line
        line = line.lstrip('/')
        body = _translate(line)
        regex = f'{body}' if anchored else f'(?:.*/)?{body}'
        rules.append(Rule(re.compile(regex), negate, directory_only))
    return rules


def ignored(relative: str, is_dir: bool, rules: list[Rule]) -> bool:
    """Whether one path (not its parents) is matched; the last matching rule wins."""
    result = False
    for rule in rules:
        if rule.directory_only and not is_dir:
            continue
        if rule.pattern.fullmatch(relative):
            result = not rule.negate
    return result


def transferable(root: Path, ignore_file: str = '.amlignore') -> list[str]:
    """The POSIX relative paths of the files Azure ML would upload from ``root``."""
    root = Path(root)
    path = root / ignore_file
    rules = parse(path.read_text(encoding='utf-8')) if path.is_file() else []
    out = []

    def walk(folder: Path, prefix: str) -> None:
        for entry in sorted(folder.iterdir(), key=lambda p: p.name):
            relative = f'{prefix}{entry.name}'
            is_dir = entry.is_dir() and not entry.is_symlink()
            if ignored(relative, is_dir, rules):
                continue
            if is_dir:
                walk(entry, relative + '/')
            else:
                out.append(relative)

    walk(root, '')
    return out
