"""Opt-in, content-free log of CLI invocations for observed sessions (post-v0.1).

The study's own records (``revisions.jsonl``, ``events.jsonl``) hold every committed
change. They do not hold what an observation of a junior's session also needs: refused
commands with their codes, refused confirmations among them, and how often the junior
looks at where the study stands (``status``) or checks a text (``check``). This module
appends one line per invocation of a mutating command or of a logged read
(:data:`LOGGED_READS`) to ``.hypotrail/session-log.jsonl``, **only when the log is
enabled**:

* ``HYPOTRAIL_SESSION_LOG=1`` enables it for that process and creates the file;
* once the file exists, every later logged invocation appends to it, in any chat, until
  the file is deleted;
* ``HYPOTRAIL_SESSION_LOG=0`` disables it for that process even when the file exists;
* a read-only process (``HYPOTRAIL_READ_ONLY=1``) never writes it.

Reads (owner decision at the companion integration, which amends the review fix "reads
write nothing"): of the read-only commands (:data:`READ_COMMANDS`), ``status`` and
``check`` (:data:`LOGGED_READS`) are logged again **when the log is on**, because how often
the junior checks is what an observation wants to see. The other reads (``plan``,
``preview``, ``decisions``, ``evidence``, ``explain``) never append a line: a preview
follows a slider, and the panel's reads are not the junior's checks. With
``HYPOTRAIL_SESSION_LOG=1`` they may still create the empty file, which is the opt-in
itself. With the log on, a logged read changes the study tree by its log line only; with
the log off, every read leaves it byte-identical. ``export`` and ``session-report``
(:data:`UNLOGGED`) never touch the file at all: an export leaves the study tree
byte-identical (CLI-CONTRACT-COMPANION C7), and the report reads the log.

Privacy: a line holds no conversation content and no data values beyond identifiers the
study already shows. It never records ``--user-words``, a restatement, a rationale, a
proposed value, the text given to ``check --text`` or ``--allow-user-text``, a message,
or a request id. It records the time, the command and its verb, the exit code, the
refusal code and reason code, the revision, decision and proposal ids, the confirmation
basis and delegation scope, the activity and its rule identifiers or column name, the
result slot and the first 8 characters of its id, deliverable statuses, and for
``check`` the target, ``clean``, counts per severity and per finding code, and how many
numbers were traced (and how many of them were written in words).

The log never affects a command: a failure to write it is ignored, and it is written
after the command's outcome is final.
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Mapping, Sequence

SCHEMA = 'hypotrail.session_log/1'
LOG_FILE = 'session-log.jsonl'
ENV = 'HYPOTRAIL_SESSION_LOG'
HOME = '.hypotrail'
# Commands that never touch the log: the report reads it and must not grow it; an export
# leaves the study tree byte-identical (CLI-CONTRACT-COMPANION C7).
UNLOGGED = ('session-report', 'export')
# Read-only commands. Those not in LOGGED_READS never append a line (the opt-in may still
# create the empty file); those in LOGGED_READS append one when the log is on.
READ_COMMANDS = ('status', 'plan', 'preview', 'decisions', 'evidence', 'explain', 'check')
# Owner decision (companion integration): how often the junior checks is observed.
LOGGED_READS = ('status', 'check')
# Flags whose values are identifiers the study already shows; every other value is dropped.
SAFE_VALUE_FLAGS = ('--basis', '--delegation-scope', '--rule', '--column', '--channel',
                    '--acknowledge-interruption', '--since', '--about', '--resolve', '--withdraw',
                    '--max-groups',
                    # Advanced companion (CLI-CONTRACT-COMPANION R5): identifiers and a count.
                    '--limit', '--result', '--term')
SAFE_SWITCHES = ('--summary', '--json', '--intervals',
                 # Advanced companion (CLI-CONTRACT-COMPANION R5).
                 '--digest')
# ``preview proposal DECISION --value V`` (R5): the value is logged only when it is an
# identifier, a rule (``threshold:t``, ``capacity:k``) or a model slot (``fit.<name>``);
# any other text is dropped. ``preview`` kinds are logged as the ``verb``.
SAFE_PREVIEW_VALUE = re.compile(r'(?:threshold:(?:0(?:\.\d+)?|1(?:\.0+)?)|capacity:[1-9]\d{0,6}'
                                r'|fit\.[a-z_]+)')


def path(study_dir) -> Path:
    return Path(study_dir) / HOME / LOG_FILE


def enabled(study_dir) -> bool:
    """True when this invocation should be logged (module docstring)."""
    from . import guard

    if guard.read_only():
        return False
    flag = os.environ.get(ENV)
    if flag == '0':
        return False
    home = Path(study_dir) / HOME
    if not home.is_dir():
        return False
    return flag == '1' or path(study_dir).is_file()


def _study_arg(argv: Sequence[str]) -> str | None:
    for i, token in enumerate(argv):
        if token == '--study' and i + 1 < len(argv):
            return argv[i + 1]
        if token.startswith('--study='):
            return token.split('=', 1)[1]
    return None


def _options(argv: Sequence[str], *, text_flag: bool = True) -> dict:
    """Identifier-valued options and switches of ``argv``; free text is never kept."""
    out: dict = {}
    for i, token in enumerate(argv):
        name, _, inline = token.partition('=')
        if name in SAFE_SWITCHES:
            out[name.lstrip('-')] = True
        elif name in SAFE_VALUE_FLAGS:
            value = inline or (argv[i + 1] if i + 1 < len(argv) else None)
            if value is None or value.startswith('--'):
                continue
            key = name.lstrip('-').replace('-', '_')
            if name == '--rule':
                out.setdefault('rules', []).append(value)
            else:
                out[key] = value
        elif name == '--text' and not text_flag:
            continue   # a note's text is the junior's words: never kept
        elif name == '--text':
            out['text'] = 'stdin' if (inline or (argv[i + 1] if i + 1 < len(argv) else '')) \
                == '-' else 'file'
        elif name == '--allow-user-text':
            out['allow_user_text'] = out.get('allow_user_text', 0) + 1
    return out


def _value(argv: Sequence[str]) -> str | None:
    for i, token in enumerate(argv):
        if token == '--value':
            return argv[i + 1] if i + 1 < len(argv) else None
        if token.startswith('--value='):
            return token.split('=', 1)[1]
    return None


def _short(rid) -> str | None:
    return rid[:8] if isinstance(rid, str) else None


def _artifacts(payload: Mapping) -> dict | None:
    items = payload.get('artifacts')
    if not isinstance(items, Mapping):
        return None
    return {name: item.get('status') for name, item in sorted(items.items())
            if isinstance(item, Mapping)}


def entry(argv: Sequence[str], payload: Mapping, exit_code: int, time: str) -> dict:
    """The log line of one invocation (no content; module docstring)."""
    argv = [str(a) for a in argv]
    command = argv[0] if argv else ''
    verb = argv[1] if command in ('decide', 'preview') and len(argv) > 1 else None
    line = {'schema': SCHEMA, 'time': time, 'command': command, 'verb': verb,
            'exit_code': exit_code, 'ok': bool(payload.get('ok')),
            'revision': payload.get('revision') if isinstance(payload.get('revision'), int)
            else None, 'options': _options(argv[1:], text_flag=command != 'decide')}
    if command == 'decide' and verb in ('propose',) and len(argv) > 2:
        line['decision_id'] = argv[2]
    if command == 'decide' and verb in ('confirm', 'withdraw') and len(argv) > 2:
        line['proposal_id'] = argv[2]
    if command == 'run' and len(argv) > 1 and not argv[1].startswith('--'):
        line['activity'] = argv[1]
    if not payload.get('ok'):
        error = payload.get('error') if isinstance(payload.get('error'), Mapping) else {}
        details = error.get('details') if isinstance(error.get('details'), Mapping) else {}
        reason = details.get('reason')
        line['refusal'] = {'code': error.get('code'),
                           'reason': reason if isinstance(reason, str) and reason.isidentifier()
                           else None}
        return line
    result = payload.get('result') if isinstance(payload.get('result'), Mapping) else {}
    if command == 'decide':
        line['replayed'] = bool(payload.get('replayed'))
        for key in ('decision_id', 'proposal_id', 'note_id', 'status', 'basis',
                    'delegation_scope'):
            if result.get(key) is not None:
                line[key] = result[key]
        inv = result.get('invalidation')
        if isinstance(inv, Mapping):
            line['invalidation'] = {'mutation': inv.get('mutation'),
                                    'stale_results': len(inv.get('stale_results') or [])}
        line['artifacts'] = _artifacts(payload)
    elif command == 'run':
        line['status'] = payload.get('status')
        line['slot'] = result.get('slot')
        line['result_id'] = _short(result.get('result_id'))
        line['artifacts'] = _artifacts(payload)
    elif command == 'render':
        line['status'] = payload.get('status')
        line['artifacts'] = _artifacts(payload)
    elif command == 'check':
        findings = payload.get('findings') or []
        traced = payload.get('traced') or []
        line['check'] = {'target': payload.get('target'), 'clean': payload.get('clean'),
                         'counts': payload.get('counts'),
                         'codes': dict(sorted(Counter(f.get('code') for f in findings).items())),
                         'traced': len(traced),
                         'in_words': sum(1 for t in traced if t.get('in_words'))
                         + sum(1 for f in findings
                               if (f.get('details') or {}).get('in_words'))}
    elif command == 'status':
        v = payload.get('view') if isinstance(payload.get('view'), Mapping) else payload
        nxt = v.get('next_action') if isinstance(v.get('next_action'), Mapping) else {}
        line['current_step'] = v.get('current_step')
        line['next_action'] = nxt.get('kind')
    elif command == 'preview':
        line['rules'] = list(payload.get('rules') or [])
    if command == 'preview' and verb in ('effects', 'proposal') and len(argv) > 2 \
            and not argv[2].startswith('-'):
        # The positional identifier: a proposal id (effects) or a decision id (proposal).
        line['proposal_id' if verb == 'effects' else 'decision_id'] = argv[2]
    if command == 'preview' and verb == 'proposal':
        value = _value(argv)
        if value is not None and SAFE_PREVIEW_VALUE.fullmatch(value):
            line['options']['value'] = value
    return line


def record(argv: Sequence[str], payload: Mapping, exit_code: int) -> None:
    """Append the line of this invocation when the log is enabled; never raises."""
    try:
        argv = [str(a) for a in argv]
        if not argv or argv[0] in UNLOGGED:
            return
        study = _study_arg(argv)
        if study is None or not enabled(study):
            return
        if argv[0] in READ_COMMANDS and argv[0] not in LOGGED_READS:
            if os.environ.get(ENV) == '1' and not path(study).exists():
                path(study).touch()          # the opt-in: an empty log, never a line
            return
        from . import state as st
        from .store import append_jsonl

        line = entry(argv, payload, exit_code, st.now())
        json.dumps(line)
        append_jsonl(path(study), line)
    except Exception:   # noqa: BLE001 - the log must never change a command's outcome
        return
