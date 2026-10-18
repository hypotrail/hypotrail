"""``hypotrail`` command-line interface (plan §4, ``docs/specs/CLI-CONTRACT.md``).

    hypotrail init --case CASE --study DIR
    hypotrail status --study DIR [--since REV] [--json]
    hypotrail plan --study DIR
    hypotrail decide propose DECISION (--value TEXT | --value-json JSON)
                     --restatement TEXT --rationale TEXT
                     --request-id ID --expected-revision REV --study DIR
    hypotrail decide confirm PROPOSAL --user-words TEXT [--channel chat|cli|webview]
                     [--actor NAME] [--basis explicit|delegated_default]
                     --request-id ID --expected-revision REV --study DIR
    hypotrail decide withdraw PROPOSAL [--reason TEXT]
                     --request-id ID --expected-revision REV --study DIR

Output is JSON on stdout by default (one document); ``--format text`` prints a short
human summary. ``--study`` is mandatory: the study is never taken from the current
directory or from ``OSML_ROOT``.

Exit codes: 0 success or replay; 1 internal error; 2 refusal without effect; 3 the
command committed but an artefact is stale or failed; 4 an execution has an unknown
outcome.

Extension commands (Phase 2 and 3) live in their own modules, listed in
:data:`EXTENSIONS`, and are imported only when invoked, so ``status`` stays fast.
Each module defines ``configure(parser: argparse.ArgumentParser) -> None`` (it adds
its arguments; ``--study`` and ``--format`` are already present) and
``main(args: argparse.Namespace) -> mlkit.study.commands.Outcome``.
"""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import sys
from typing import Sequence

from mlkit.reliability import CommandRefused

from . import commands as cmd
from . import state as st
from .case import CaseError
from .errors import StudyError

EXTENSIONS = {
    'run': 'mlkit.study.cmd_run',          # Phase 2: activities, executions (WP2.x)
    'render': 'mlkit.study.cmd_render',    # Phase 3: manifest, HTML, notebook (WP3.1-3.2)
    'check': 'mlkit.study.cmd_check',      # Phase 3: number and wording checks (WP3.3)
    'preview': 'mlkit.study.cmd_preview',  # Phase 2: read-only policy preview (WP2.4)
}
REFUSALS = (CommandRefused, StudyError, CaseError)


class ArgumentError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def to_dict(self) -> dict:
        return {'code': 'invalid_arguments', 'message': self.message}


class Parser(argparse.ArgumentParser):
    """Argument errors become ``hypotrail.error/1`` refusals instead of usage text."""

    def error(self, message):   # noqa: D401 - argparse API
        raise ArgumentError(message)


def _common() -> argparse.ArgumentParser:
    common = Parser(add_help=False)
    common.add_argument('--study', required=True, help='study directory (holds .hypotrail/)')
    common.add_argument('--format', choices=('json', 'text'), default='json')
    common.add_argument('--json', dest='format', action='store_const', const='json',
                        help='JSON output (the default)')
    return common


def _mutation(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--request-id', required=True,
                        help='fresh per intent; replay the same one after a timeout')
    parser.add_argument('--expected-revision', required=True, type=int,
                        help='the revision you read with status')


def build_parser(extension: str | None = None) -> argparse.ArgumentParser:
    common = _common()
    parser = Parser(prog='hypotrail', description='Junior ML study engine.')
    sub = parser.add_subparsers(dest='command', required=True, parser_class=Parser)

    p = sub.add_parser('init', parents=[common], help='create a study on a case')
    p.add_argument('--case', required=True, help='case.yaml or its directory')
    p = sub.add_parser('status', parents=[common], help='read-only view of the study')
    p.add_argument('--since', type=int, default=None, help='report revisions after REV')
    sub.add_parser('plan', parents=[common], help='read-only plan with step statuses')

    decide = sub.add_parser('decide', help='propose, confirm, or withdraw a decision')
    verbs = decide.add_subparsers(dest='verb', required=True, parser_class=Parser)
    p = verbs.add_parser('propose', parents=[common])
    p.add_argument('decision_id')
    value = p.add_mutually_exclusive_group(required=True)
    value.add_argument('--value', help='text value')
    value.add_argument('--value-json', help='JSON value (mappings, numbers)')
    p.add_argument('--restatement', required=True,
                   help='the decision restated for the user to answer')
    p.add_argument('--rationale', required=True)
    _mutation(p)
    p = verbs.add_parser('confirm', parents=[common])
    p.add_argument('proposal_id')
    p.add_argument('--user-words', required=True,
                   help="the user's verbatim reply to the restatement")
    p.add_argument('--channel', choices=('chat', 'cli', 'webview'), default=cmd.DEFAULT_CHANNEL)
    p.add_argument('--actor', default=cmd.DEFAULT_ACTOR)
    p.add_argument('--basis', choices=st.CONFIRMATION_BASES, default=cmd.DEFAULT_BASIS,
                   help='explicit (the default): the reply decides; delegated_default: the reply '
                        "explicitly delegates to the assistant's recommended default, which the "
                        'restatement states')
    _mutation(p)
    p = verbs.add_parser('withdraw', parents=[common])
    p.add_argument('proposal_id')
    p.add_argument('--reason', default=None)
    _mutation(p)

    if extension is not None:
        module = importlib.import_module(EXTENSIONS[extension])
        p = sub.add_parser(extension, parents=[common])
        module.configure(p)
    return parser


def _decide(args) -> cmd.Outcome:
    if args.verb == 'propose':
        if args.value_json is not None:
            try:
                value = json.loads(args.value_json)
            except ValueError as exc:
                raise ArgumentError(f'--value-json is not valid JSON: {exc}') from exc
        else:
            value = args.value
        action, params = cmd.ACTION_PROPOSE, {'decision_id': args.decision_id, 'value': value,
                                              'restatement': args.restatement,
                                              'rationale': args.rationale}
    elif args.verb == 'confirm':
        action, params = cmd.ACTION_CONFIRM, {'proposal_id': args.proposal_id,
                                              'user_words': args.user_words,
                                              'channel': args.channel, 'actor': args.actor,
                                              'basis': args.basis}
    else:
        action, params = cmd.ACTION_WITHDRAW, {'proposal_id': args.proposal_id,
                                               'reason': args.reason}
    return cmd.apply(args.study, action=action, params=params, request_id=args.request_id,
                     expected_revision=args.expected_revision)


def dispatch(args) -> cmd.Outcome:
    if args.command == 'init':
        return cmd.init(args.case, args.study)
    if args.command == 'status':
        return cmd.status(args.study, since=args.since)
    if args.command == 'plan':
        return cmd.plan(args.study)
    if args.command == 'decide':
        return _decide(args)
    module = importlib.import_module(EXTENSIONS[args.command])
    return module.main(args)


# --- text output ------------------------------------------------------------------------

def _text(payload: dict) -> str:
    schema = payload.get('schema', '')
    if not payload.get('ok', False):
        e = payload['error']
        lines = [f'refused ({e["code"]}): {e["message"]}']
        for k, v in (e.get('details') or {}).items():
            lines.append(f'  {k}: {json.dumps(v, ensure_ascii=False)}')
        return '\n'.join(lines)
    if schema == cmd.SCHEMAS['status']:
        v = payload['view']
        lines = [f'study {v["study"]} at revision {v["revision"]}',
                 f'current step: {v["current_step"]}',
                 f'next action: {v["next_action"]["kind"]}: {v["next_action"]["message"]}']
        for p in v['open_proposals']:
            lines.append(f'open proposal {p["proposal_id"]} ({p["decision_id"]}): '
                         f'{p["restatement"]}')
        for d in v['decisions'].values():
            conf = d['confirmation']
            words = conf['user_words'] if conf else None
            delegated = ', delegated to the assistant\'s default' \
                if conf and conf.get('basis') == st.DELEGATED_DEFAULT else ''
            lines.append(f'decision {d["decision_id"]}: {d["status"]}'
                         + (f' - "{words}" ({conf["channel"]}{delegated})' if words else ''))
        if payload['since'] is not None:
            lines.append(f'changes since revision {payload["since"]}: '
                         f'{len(payload["changes_since"])}')
        lines.append('not yet defensible: ' + ', '.join(x['id'] for x in v['not_yet_defensible']))
        return '\n'.join(lines)
    if schema == cmd.SCHEMAS['plan']:
        return '\n'.join(f'{"> " if s["current"] else "  "}{s["id"]}: {s["status"]} - '
                         f'{s["title"]}' for s in payload['steps'])
    if schema == cmd.SCHEMAS['decide']:
        r = payload['result']
        head = f'{payload["action"]} at revision {payload["revision"]}' + (
            ' (replayed, no effect)' if payload['replayed'] else '')
        return head + '\n' + '\n'.join(f'  {k}: {json.dumps(v, ensure_ascii=False)}'
                                       for k, v in r.items())
    if schema == cmd.SCHEMAS['init']:
        return (f'study created at {payload["study"]} (revision {payload["revision"]}) on case '
                f'{payload["case"]["id"]}\nnext action: {payload["next_action"]["message"]}')
    return json.dumps(payload, ensure_ascii=False, indent=2)


def emit(outcome: cmd.Outcome, fmt: str, stream=None) -> None:
    stream = stream or sys.stdout
    if fmt == 'text':
        stream.write(_text(outcome.payload) + '\n')
    else:
        stream.write(json.dumps(outcome.payload, ensure_ascii=False) + '\n')
    stream.flush()


def _wanted_format(argv: Sequence[str]) -> str:
    argv = list(argv)
    if '--format' in argv:
        i = argv.index('--format')
        if i + 1 < len(argv) and argv[i + 1] in ('json', 'text'):
            return argv[i + 1]
    return 'text' if '--format=text' in argv else 'json'


def run(argv: Sequence[str] | None = None) -> cmd.Outcome:
    """Parse ``argv`` and run the command; never raises for refusals."""
    argv = list(sys.argv[1:] if argv is None else argv)
    name = argv[0] if argv else ''
    command = ' '.join(argv[:2]) if name == 'decide' else name
    try:
        extension = name if name in EXTENSIONS else None
        if extension and importlib.util.find_spec(EXTENSIONS[extension]) is None:
            raise StudyError('unsupported_capability',
                             f'Command {extension!r} is not available in this version.',
                             details={'command': extension})
        args = build_parser(extension).parse_args(argv)
        return dispatch(args)
    except (*REFUSALS, ArgumentError) as exc:
        return cmd.refused(command or 'hypotrail', exc)
    except Exception as exc:   # an internal error still answers in the contract format
        return cmd.Outcome(cmd.error_payload(command or 'hypotrail', exc), cmd.EXIT_INTERNAL)


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv in (['-h'], ['--help']) or not argv:
        build_parser().print_help()
        return cmd.EXIT_OK if argv else cmd.EXIT_REFUSED
    outcome = run(argv)
    try:
        emit(outcome, _wanted_format(argv))
    except BrokenPipeError:
        # The reader closed the pipe (``status | head``): the outcome stands, nothing more
        # can be told, and no traceback goes to stderr (a handled outcome writes none).
        _silence_stdout()
    return outcome.exit_code


def _silence_stdout() -> None:
    """Point stdout at /dev/null so the interpreter's final flush cannot fail again."""
    import os

    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        os.close(devnull)
    except (OSError, ValueError):   # stdout is not a real file (tests); nothing to flush
        pass


if __name__ == '__main__':
    sys.exit(main())
