"""``hypotrail hook pretool``: the PreToolUse hook of a study's chat agent (Onboarding Lot 1).

``hypotrail new`` installs it as ``<study>/.github/hooks/hypotrail.json`` (VS Code agent
hooks, preview). VS Code runs it before each tool call of the agent, with the call as JSON
on stdin, and reads a decision on stdout:

* **allow** one plain engine command: the study's own CLI invocation (the argument list in
  ``.hypotrail/agent.json``, matched token by token, so ``uv run --project ... hypotrail``,
  an installed ``hypotrail`` executable and a PowerShell ``& 'C:\\...\\hypotrail.exe'``
  line all work), with no shell operator (no ``; & | ` $ < >`` and no newline), so the
  junior is not asked to approve each step of the study;
* **deny** any call that names the case's raw data file (its file name, read from the
  study's state). The file holds the sealed final-test rows; a raw read would be an
  unrecorded look. The study shows its data through ``hypotrail data``, the panel and the
  notebooks;
* **no decision** (``{}``) for everything else: VS Code asks the junior as usual.

Each decision is appended to the log file (``--log``) when one is given. The hook is a
cooperative aid, not a security boundary: the agent can still do anything the junior
approves, and a script or a glob reaches the file without naming it. The hook never fails
the tool call: any problem (no study, unreadable input) gives no decision.

``scripts/workshop/hooks/pretool.py`` delegates here (:func:`legacy_main`), with its
historical flags ``--repo`` and ``--data-file``. Standard library only on the decision path.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import ntpath
import os
import re
import shlex
import sys
from pathlib import Path
from typing import Iterable, Sequence

HOOK_FILE = '.github/hooks/hypotrail.json'
LOG_FILE = '.github/hooks/hypotrail-hook.log'
SHELL_OPERATORS = re.compile(r'[;&|`$<>\n\r]')
STUDY_OPTIONAL = ('pretool',)
REASONS = {
    'en': {'deny': 'The raw file {name} also holds the sealed final-test rows: use '
                   '"hypotrail data", the study panel, or the notebooks.',
           'allow': 'A plain hypotrail engine command, allowed by the study\'s hook.'},
    'fr': {'deny': 'Le fichier brut {name} contient aussi les lignes du test final scellé : '
                   'passez par « hypotrail data », le panneau ou les notebooks.',
           'allow': "Commande du moteur hypotrail, autorisée par le hook de l'étude."},
}


def strings(value) -> Iterable[str]:
    """Every string inside a tool input (nested dicts and lists included)."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from strings(item)


def tool_input(event: dict):
    """The call's arguments: ``tool_input`` (VS Code) or ``toolArgs`` (Copilot CLI), which
    may arrive as a JSON string."""
    raw = event.get('tool_input', event.get('toolArgs'))
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except ValueError:
            return raw
    return raw if raw is not None else {}


def _norm(token: str, windows: bool) -> str:
    if not windows:
        return token
    return ntpath.normcase(token)   # lower case, '/' as '\\', on any host


def tokens(command: str, *, windows: bool | None = None) -> list[str] | None:
    """The words of a one-line command, or None when it holds a shell operator or cannot
    be split. A leading PowerShell call operator ``&`` is dropped first; on Windows the
    words are split without POSIX escapes (a backslash is a path separator there) and
    single or double quotes around a word are removed (``''`` inside single quotes is one
    quote, as PowerShell reads it)."""
    windows = os.name == 'nt' if windows is None else windows
    text = command.strip()
    if text.startswith('& '):
        text = text[2:].lstrip()
    if not text or SHELL_OPERATORS.search(text):
        return None
    try:
        if not windows:
            return shlex.split(text)
        lexer = shlex.shlex(text, posix=False)
        lexer.whitespace_split = True
        words = []
        for w in lexer:
            if len(w) >= 2 and w[0] == w[-1] == "'":
                w = w[1:-1].replace("''", "'")
            elif len(w) >= 2 and w[0] == w[-1] == '"':
                w = w[1:-1]
            words.append(w)
        return words
    except ValueError:
        return None


def engine_prefixes(argv: Sequence[str]) -> list[list[str]]:
    """The argument lists that start an engine command: the study's own ``argv``, and for a
    ``uv run`` invocation the same with ``--quiet`` after ``run`` (scripts use it)."""
    argv = [str(a) for a in argv]
    out = [argv]
    if argv[:2] == ['uv', 'run'] and '--quiet' not in argv:
        out.append(['uv', 'run', '--quiet', *argv[2:]])
    return out


def is_engine_command(command: str, prefixes: Sequence[Sequence[str]], *,
                      windows: bool | None = None) -> bool:
    windows = os.name == 'nt' if windows is None else windows
    words = tokens(command, windows=windows)
    if not words:
        return False
    for prefix in prefixes:
        if len(words) >= len(prefix) and all(
                _norm(w, windows) == _norm(p, windows) for w, p in zip(words, prefix)):
            return True
    return False


def decide(event: dict, prefixes: Sequence[Sequence[str]], data_files: Sequence[str],
           language: str = 'en', *, windows: bool | None = None) -> tuple[str | None, str]:
    """``(decision, reason)``: ``deny`` when the call names a data file, ``allow`` for one
    plain engine command, ``(None, '')`` otherwise."""
    texts = REASONS.get(language, REASONS['en'])
    args = tool_input(event)
    found = list(strings(args))
    for name in data_files:
        if name and any(name in t for t in found):
            return 'deny', texts['deny'].format(name=name)
    command = args.get('command') if isinstance(args, dict) else None
    if isinstance(command, str) and is_engine_command(command, prefixes, windows=windows):
        return 'allow', texts['allow']
    return None, ''


def respond(decision: str | None, reason: str) -> dict:
    if decision is None:
        return {}
    return {'hookSpecificOutput': {'hookEventName': 'PreToolUse',
                                   'permissionDecision': decision,
                                   'permissionDecisionReason': reason}}


def log(path, event, decision: str | None) -> None:
    """Append one line ``{at, tool, decision, call}`` to ``path``; never raises."""
    if not path:
        return
    args = tool_input(event) if isinstance(event, dict) else {}
    summary = args.get('command') if isinstance(args, dict) and 'command' in args else args
    line = {'at': dt.datetime.now().isoformat(timespec='seconds'),
            'tool': event.get('tool_name', event.get('toolName'))
            if isinstance(event, dict) else None,
            'decision': decision or 'ask', 'call': str(summary)[:300]}
    try:
        with open(path, 'a', encoding='utf-8') as handle:
            handle.write(json.dumps(line, ensure_ascii=False) + '\n')
    except OSError:
        pass


def study_rule(study_dir) -> tuple[list[list[str]], list[str], str]:
    """``(prefixes, data_files, language)`` of a study: the engine invocation recorded in
    ``.hypotrail/agent.json`` and the file name of the case's data, from the state."""
    home = Path(study_dir) / '.hypotrail'
    prefixes: list[list[str]] = []
    try:
        record = json.loads((home / 'agent.json').read_text(encoding='utf-8'))
        argv = record['cli']['argv']
        if isinstance(argv, list) and argv:
            prefixes = engine_prefixes(argv)
    except (OSError, ValueError, KeyError, TypeError):
        pass
    data_files, language = [], 'en'
    try:
        state = json.loads((home / 'state.json').read_text(encoding='utf-8'))
        path = (state.get('dataset') or {}).get('path')
        if isinstance(path, str) and path:
            data_files.append(Path(path).name)
        language = state.get('language') or 'en'
    except (OSError, ValueError, AttributeError):
        pass
    return prefixes, data_files, language


def read_event(stream=None):
    try:
        event = json.load(stream or sys.stdin)
    except ValueError:
        return {}
    return event if isinstance(event, dict) else {}


def hook_command(cli_argv: Sequence[str], study, log_file) -> list[str]:
    """The argument list a hook configuration runs: ``<cli> hook pretool --study S --log L``."""
    return [*cli_argv, 'hook', 'pretool', '--study', str(study), '--log', str(log_file)]


def hook_config(cli_argv: Sequence[str], study) -> dict:
    """The ``.github/hooks/hypotrail.json`` document of a study (VS Code agent hooks): one
    ``PreToolUse`` command, quoted for the user's shell (PowerShell on Windows)."""
    from .agent_files import display_command
    study = Path(study)
    argv = hook_command(cli_argv, study, study / LOG_FILE)
    return {'hooks': {'PreToolUse': [{'type': 'command', 'command': display_command(argv),
                                      'timeout': 15}]}}


# --- CLI ----------------------------------------------------------------------------------

def configure(parser: argparse.ArgumentParser) -> None:
    from .cli import Parser, _common

    verbs = parser.add_subparsers(dest='verb', required=True, parser_class=Parser)
    # --study is optional: a hook without a study answers "no decision", never an error.
    p = verbs.add_parser('pretool', parents=[_common(False)],
                         help='decide on one tool call of the chat agent (JSON on stdin): '
                              'allow plain engine commands, deny raw reads of the data file, '
                              'otherwise no decision')
    p.add_argument('--log', default=None, help='append each decision to this file')


def main(args: argparse.Namespace):
    from .commands import Outcome

    event = read_event()
    decision, reason = None, ''
    try:
        if args.study:
            prefixes, data_files, language = study_rule(args.study)
            decision, reason = decide(event, prefixes, data_files, language)
    except Exception:   # noqa: BLE001 - a hook never fails the tool call
        decision, reason = None, ''
    log(args.log, event, decision)
    return Outcome(respond(decision, reason))


def legacy_main(argv=None) -> int:
    """``scripts/workshop/hooks/pretool.py``: the historical flags ``--repo REPO`` (the
    engine is ``uv run [--quiet] --project REPO/framework hypotrail``), ``--data-file``
    (repeatable) and ``--log``; optionally ``--study`` to read the rule from the study."""
    parser = argparse.ArgumentParser(description='Workshop PreToolUse hook (legacy flags).')
    parser.add_argument('--repo')
    parser.add_argument('--study')
    parser.add_argument('--data-file', action='append', default=[])
    parser.add_argument('--log')
    opts = parser.parse_args(argv)
    event = read_event()
    prefixes, data_files, language = [], list(opts.data_file), 'fr'
    if opts.study:
        prefixes, found, language = study_rule(opts.study)
        data_files += found
    if opts.repo:
        project = str(Path(opts.repo).resolve() / 'framework')
        prefixes += engine_prefixes(['uv', 'run', '--project', project, 'hypotrail'])
    try:
        decision, reason = decide(event, prefixes, data_files, language)
    except Exception:   # noqa: BLE001 - a hook never fails the tool call
        decision, reason = None, ''
    print(json.dumps(respond(decision, reason), ensure_ascii=False))
    log(opts.log, event, decision)
    return 0
