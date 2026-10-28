"""Workshop PreToolUse hook for a study's Copilot agent (VS Code agent hooks, preview).

Installed by scripts/workshop/new-mpg-study.sh as <study>/.github/hooks/hypotrail.json. VS
Code runs it before each tool call of the agent, with the call as JSON on stdin, and reads a
decision on stdout:

* allow: one plain engine command, ``uv run [--quiet] --project <repo>/framework hypotrail
  ...``, with no shell operator (no ``; & | ` $ < >`` and no newline), so the junior is not
  asked to approve each step of the study;
* deny: any call that names the case's raw data file (``--data-file``, repeatable). The file
  holds the sealed final-test rows; a raw read would be an unrecorded look. The study shows
  its data through ``hypotrail data``, the panel, and the notebooks;
* no decision (``{}``) for everything else: VS Code asks the junior as usual.

Each decision is appended to ``hypotrail-hook.log`` next to this hook's configuration, so the
workshop can show what the rule allowed and refused. Standard library only. The hook is a
convenience, not a security boundary: the agent can still be asked to do anything the junior
approves.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

SHELL_OPERATORS = re.compile(r'[;&|`$<>\n]')


def strings(value):
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


def engine_command(repo: str) -> re.Pattern:
    project = re.escape(str(Path(repo).resolve() / 'framework'))
    return re.compile(rf'^\s*uv run (--quiet )?--project {project} hypotrail(\s|$)')


def decide(event: dict, repo: str, data_files: list[str]) -> tuple[str | None, str]:
    args = tool_input(event)
    texts = list(strings(args))
    for name in data_files:
        if any(name in t for t in texts):
            return 'deny', (f'Le fichier brut {name} contient aussi les lignes du test final '
                            'scellé : passez par « hypotrail data », le panneau ou les notebooks.')
    command = args.get('command') if isinstance(args, dict) else None
    if isinstance(command, str) and engine_command(repo).match(command) \
            and not SHELL_OPERATORS.search(command):
        return 'allow', "Commande du moteur hypotrail, autorisée par la règle de l'atelier."
    return None, ''


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--repo', required=True)
    parser.add_argument('--data-file', action='append', default=[])
    parser.add_argument('--log')
    opts = parser.parse_args(argv)
    try:
        event = json.load(sys.stdin)
    except ValueError:
        print('{}')
        return 0
    decision, reason = decide(event if isinstance(event, dict) else {}, opts.repo, opts.data_file)
    if decision is None:
        print('{}')
    else:
        print(json.dumps({'hookSpecificOutput': {
            'hookEventName': 'PreToolUse', 'permissionDecision': decision,
            'permissionDecisionReason': reason}}, ensure_ascii=False))
    if opts.log:
        args = tool_input(event) if isinstance(event, dict) else {}
        summary = args.get('command') if isinstance(args, dict) and 'command' in args else args
        line = {'at': dt.datetime.now().isoformat(timespec='seconds'),
                'tool': event.get('tool_name', event.get('toolName')) if isinstance(event, dict) else None,
                'decision': decision or 'ask', 'call': str(summary)[:300]}
        try:
            with open(opts.log, 'a', encoding='utf-8') as handle:
                handle.write(json.dumps(line, ensure_ascii=False) + '\n')
        except OSError:
            pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
