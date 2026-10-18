"""Opt-in, content-free log of CLI invocations for observed sessions (post-v0.1).

The study's own records (``revisions.jsonl``, ``events.jsonl``) hold every committed
change. They do not hold what an observation of a junior's session also needs: refused
commands with their codes, ``status`` reads, ``check`` runs with their finding counts,
and policy previews. This module appends one line per CLI invocation to
``.hypotrail/session-log.jsonl``, **only when the log is enabled**:

* ``HYPOTRAIL_SESSION_LOG=1`` enables it for that process and creates the file;
* once the file exists, every later invocation appends to it, in any chat, until the
  file is deleted;
* ``HYPOTRAIL_SESSION_LOG=0`` disables it for that process even when the file exists;
* a read-only process (``HYPOTRAIL_READ_ONLY=1``) never writes it.

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
from collections import Counter
from pathlib import Path
from typing import Mapping, Sequence

SCHEMA = 'hypotrail.session_log/1'
LOG_FILE = 'session-log.jsonl'
ENV = 'HYPOTRAIL_SESSION_LOG'
HOME = '.hypotrail'
# Commands never logged: the report reads the log and must not grow it.
UNLOGGED = ('session-report',)
# Flags whose values are identifiers the study already shows; every other value is dropped.
SAFE_VALUE_FLAGS = ('--basis', '--delegation-scope', '--rule', '--column', '--channel',
                    '--acknowledge-interruption', '--since', '--about', '--resolve',
                    '--max-groups')
SAFE_SWITCHES = ('--summary', '--json', '--intervals')


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
        from . import state as st
        from .store import append_jsonl

        line = entry(argv, payload, exit_code, st.now())
        json.dumps(line)
        append_jsonl(path(study), line)
    except Exception:   # noqa: BLE001 - the log must never change a command's outcome
        return
