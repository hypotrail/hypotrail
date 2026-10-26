"""``hypotrail`` command-line interface (plan §4, ``docs/specs/CLI-CONTRACT.md``).

    hypotrail init --case CASE --study DIR [--lang en|fr]
                   [--automation until_final_test|full_demo]                 (L9, R20)
    hypotrail status --study DIR [--since REV] [--json] [--summary [--fields KEY,...]]
    hypotrail plan --study DIR
    hypotrail decide propose DECISION (--value TEXT | --value-json JSON)
                     --restatement TEXT --rationale TEXT [--lang en|fr]
                     [--restatement-en TEXT] [--restatement-fr TEXT]
                     --request-id ID --expected-revision REV --study DIR
    hypotrail decide confirm (PROPOSAL | --proposal PROPOSAL) [--user-words TEXT]
                     [--channel chat|cli|webview|choice] [--adoption-question] [--actor NAME]
                     [--basis explicit|delegated_default|automatic]
                     [--delegation-scope this_decision|standing] [--agent-concern TEXT]
                     --request-id ID --expected-revision REV --study DIR
    hypotrail decide withdraw PROPOSAL [--reason TEXT]
                     --request-id ID --expected-revision REV --study DIR
    hypotrail decide note (--about DECISION | --resolve NOTE_ID | --withdraw NOTE_ID) --text TEXT
                     [--kind hold|correction]
                     --request-id ID --expected-revision REV --study DIR
    hypotrail mode set guided|training|express [--user-words TEXT]
                     --request-id ID --expected-revision REV --study DIR      (ADR 0005)

Post-v0.1, read-only, for observed sessions (``cmd_session_report``, ``sessionlog``)::

    hypotrail session-report --study DIR [--since REV] [--gap-minutes M]

Advanced companion (``docs/specs/CLI-CONTRACT-COMPANION.md``; C1 to C10 are implemented,
behind the companion's own feature flag on the client side)::

    hypotrail status --study DIR --summary --digest [--since REV]       (C1, WP-E1)
    hypotrail decisions --study DIR                                     (C2, WP-E1)
    hypotrail preview effects PROPOSAL --study DIR                      (C3, WP-E1)
    hypotrail preview proposal DECISION --value V --study DIR           (C4, WP-E3)
    hypotrail evidence --study DIR [--result RID] [--limit N]           (C5, WP-E2)
    hypotrail explain --study DIR [--term ID]                           (C6, WP-E2)
    hypotrail export handoff --study DIR [--out DIR]                    (C7, WP-E2)
    hypotrail decide propose ... [--channel chat|cli|webview]           (C9, WP-E1)

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
    # Post-v0.1: read-only timeline of a study for observed sessions.
    'session-report': 'mlkit.study.cmd_session_report',
    # Advanced companion (CLI-CONTRACT-COMPANION §13): registered by WP-0, implemented by
    # WP-E1 (decisions), WP-E2 (evidence, explain, export).
    'decisions': 'mlkit.study.cmd_decisions',
    'evidence': 'mlkit.study.cmd_evidence',
    'explain': 'mlkit.study.cmd_explain',
    'export': 'mlkit.study.cmd_export',
    # v0.2a (WP-A4, R2): the read-only data card.
    'data': 'mlkit.study.cmd_data',
    # ADR 0008: the opt-in understanding and handover review (off by default).
    'understanding': 'mlkit.study.cmd_understanding',
    # Owner session 2026-10-26 (L9, R20): the automatic mode chosen at init (run, stop).
    'automation': 'mlkit.study.cmd_automation',
}
# One line per extension command for ``hypotrail --help`` (v0.2a, WP-A1): the help lists
# every command without importing the extension modules.
EXTENSION_HELP = {
    'run': 'run one activity (split, exploration, fit, evaluation) and record its result',
    'render': 'write the HTML report and the notebooks for the current revision',
    'check': 'check the numbers and wording of the deliverables, or of a text',
    'preview': 'preview a policy or the effects of a proposal; records nothing',
    'session-report': 'read-only timeline of the study, by working session',
    'decisions': 'read-only history of every decision and proposal',
    'evidence': 'read-only results, lineage, rows read, and exploration catalog',
    'explain': 'glossary terms, step texts, and examples cited from this study',
    'export': 'export a handoff pack of the study into a new folder',
    'data': 'read-only data card: row unit, sizes, grouped columns, five development rows',
    'understanding': 'opt-in understanding and handover review (off by default; ADR 0008)',
    'automation': 'run the automatic mode chosen at init, or stop it in the junior\'s words',
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


def _common(study_required: bool = True) -> argparse.ArgumentParser:
    common = Parser(add_help=False)
    common.add_argument('--study', required=study_required, default=None,
                        help='study directory (holds .hypotrail/)')
    common.add_argument('--format', choices=('json', 'text'), default='json')
    common.add_argument('--json', dest='format', action='store_const', const='json',
                        help='JSON output (the default)')
    return common


def _mutation(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--request-id', required=True,
                        help='fresh per intent; replay the same one after a timeout')
    parser.add_argument('--expected-revision', required=True, type=int,
                        help='the revision you read with status')


def build_parser(extension: str | None = None, *, listing: bool = False
                 ) -> argparse.ArgumentParser:
    """The parser; ``listing`` adds every extension command with its one-line help (for
    ``hypotrail --help``) without importing it."""
    common = _common()
    parser = Parser(prog='hypotrail', description='Junior ML study engine. Every command takes '
                                                  '--study DIR and prints one JSON document '
                                                  '(--format text for a readable summary).',
                    formatter_class=lambda prog: argparse.HelpFormatter(
                        prog, max_help_position=20, width=110))
    sub = parser.add_subparsers(dest='command', required=True, parser_class=Parser,
                                metavar='COMMAND')

    p = sub.add_parser('init', parents=[common], help='create a study on a case')
    p.add_argument('--case', required=True, help='case.yaml or its directory')
    p.add_argument('--lang', choices=st.LANGUAGES, default=st.DEFAULT_LANGUAGE,
                   help='the study language: surfaces show restatements in it (ADR 0005)')
    p.add_argument('--reliability-profile', choices=('legacy', 'review-v1'), default=None,
                   help='opt-in reliability profile; review-v1 enforces the declared evaluation protocol')
    p.add_argument('--automation', choices=st.AUTOMATION_MODES, default=None,
                   help='the automatic mode, chosen at launch only (L9): until_final_test '
                        'records every decision before the final test with the engine\'s '
                        'values; full_demo also opens the final test and concludes (a '
                        'demonstration). Every automatic decision is reviewed at the end')
    p = sub.add_parser('status', parents=[common], help='read-only view of the study')
    p.add_argument('--since', type=int, default=None, help='report revisions after REV')
    p.add_argument('--summary', action='store_true',
                   help='compact digest (hypotrail.summary/1) instead of the full view')
    p.add_argument('--digest', action='store_true',
                   help='with --summary: add moments, pauses, last_session, and digest '
                        '(CLI-CONTRACT-COMPANION §1)')
    p.add_argument('--fields', default=None, metavar='KEY[,KEY...]',
                   help='with --summary: print only these keys of the summary (for example '
                        'next_action,criterion), after schema, ok, study and revision; read '
                        'them as they are instead of piping the JSON into a script')
    sub.add_parser('plan', parents=[common], help='read-only plan with step statuses')

    decide = sub.add_parser('decide', help='propose, confirm, or withdraw a decision, or '
                                           'record a note on one')
    verbs = decide.add_subparsers(dest='verb', required=True, parser_class=Parser)
    p = verbs.add_parser('propose', parents=[common])
    p.add_argument('decision_id')
    value = p.add_mutually_exclusive_group(required=True)
    value.add_argument('--value', help='text value')
    value.add_argument('--value-json', help='JSON value (mappings, numbers)')
    p.add_argument('--restatement', required=True,
                   help='the decision restated for the user to answer')
    p.add_argument('--rationale', required=True)
    # C9 (CLI-CONTRACT-COMPANION §9): the channel the proposal came from. No argparse
    # choices: a value outside ``state.CHANNELS`` is ``invalid_value`` (``details.field``).
    p.add_argument('--channel', default=None,
                   help='chat (the default), cli, or webview: where the proposal came from')
    # ADR 0005: a restatement per language. ``--lang`` names the language of --restatement.
    p.add_argument('--lang', choices=st.LANGUAGES, default=None,
                   help='the language of --restatement')
    for lang in st.LANGUAGES:
        p.add_argument(f'--restatement-{lang}', default=None, dest=f'restatement_{lang}',
                       help=f'the restatement in {lang} (shown when the study language is '
                            f'{lang})')
    _mutation(p)
    p = verbs.add_parser('confirm', parents=[common])
    p.add_argument('proposal_id', nargs='?', default=None)
    p.add_argument('--proposal', default=None, dest='proposal_flag', metavar='PROPOSAL',
                   help='the open proposal the words answer (same as the positional PROPOSAL)')
    p.add_argument('--user-words', default=None,
                   help="the user's verbatim reply to the restatement (required, except with "
                        '--basis automatic, which records no words)')
    p.add_argument('--channel', choices=st.CONFIRMATION_CHANNELS, default=cmd.DEFAULT_CHANNEL,
                   help='chat (the default), cli, webview, or choice: the junior picked the '
                        'adoption option of an interactive choice; --user-words is the option '
                        'label, verbatim (v0.3, R16)')
    p.add_argument('--adoption-question', action='store_true', dest='adoption_question',
                   help='the words answer the closed question "Do you adopt this decision?" '
                        'asked right after the restatement: a short yes ("oui", "ok") then '
                        'confirms in the guided and express modes (v0.3, R14)')
    p.add_argument('--actor', default=cmd.DEFAULT_ACTOR)
    p.add_argument('--basis', choices=st.REQUEST_BASES, default=cmd.DEFAULT_BASIS,
                   help="explicit (the default): the junior's own reply decides (recorded as "
                        'endorsed or restated); delegated_default: the reply explicitly '
                        "delegates to the assistant's recommended default, which the "
                        'restatement states; automatic: the automatic mode chosen at init '
                        'records the engine\'s value (no words; reviewed at the end, L9)')
    p.add_argument('--delegation-scope', choices=st.DELEGATION_SCOPES, default=None,
                   help='with delegated_default: this_decision (the junior delegated at this '
                        'pause) or standing (an earlier delegation for questions they cannot '
                        'answer; it never covers the policy or the conclusion)')
    p.add_argument('--agent-concern', default=None,
                   help='a point you raised about the junior\'s words before they confirmed, '
                        'and that they kept (R3); shown with the decision')
    _mutation(p)
    p = verbs.add_parser('withdraw', parents=[common])
    p.add_argument('proposal_id')
    p.add_argument('--reason', default=None)
    _mutation(p)
    p = verbs.add_parser('note', parents=[common])
    target = p.add_mutually_exclusive_group(required=True)
    target.add_argument('--about', default=None, metavar='DECISION',
                        help='record a condition or hold the junior stated on this decision')
    target.add_argument('--resolve', default=None, metavar='NOTE_ID',
                        help="resolve an open hold with the junior's own words")
    target.add_argument('--withdraw', default=None, metavar='NOTE_ID',
                        help="withdraw an open hold that no longer applies, with the junior's "
                             'own words')
    p.add_argument('--text', '--user-words', required=True, dest='text',
                   help="the junior's words, verbatim (the condition, or what resolves it)")
    p.add_argument('--kind', choices=st.NOTE_KINDS, default=None,
                   help='with --about: hold (the default) blocks the decision until resolved; '
                        "correction records a later correction of a confirmed decision's "
                        'reasoning without asking for it again')
    _mutation(p)

    mode = sub.add_parser('mode', help='set the confirmation mode (ADR 0005)')
    mverbs = mode.add_subparsers(dest='verb', required=True, parser_class=Parser)
    p = mverbs.add_parser('set', parents=[common])
    p.add_argument('mode', help='guided, training, or express')
    p.add_argument('--user-words', dest='user_words', default=None,
                   help="the user's verbatim words asking for this mode (needed unless the "
                        "change makes confirmations stricter)")
    _mutation(p)

    if extension is not None:
        module = importlib.import_module(EXTENSIONS[extension])
        # ADR 0008: a module may name verbs that need no study (the standalone verifier);
        # their ``--study`` is optional and the module checks it for the other verbs.
        optional = bool(getattr(module, 'STUDY_OPTIONAL', ()))
        p = sub.add_parser(extension, parents=[_common(not optional) if optional else common],
                           help=EXTENSION_HELP.get(extension))
        module.configure(p)
    elif listing:
        for name in EXTENSIONS:
            sub.add_parser(name, help=EXTENSION_HELP[name], add_help=False)
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
        # C9: ``channel`` is passed only when it is not ``chat``, so every earlier request
        # keeps its identity (a replay stays a replay).
        if args.channel not in (None, cmd.DEFAULT_CHANNEL):
            cmd.check_channel(args.channel)
            params['channel'] = args.channel
        # ADR 0005: ``labels`` only when a language is given, so earlier requests keep
        # their identity.
        labels = {lang: getattr(args, f'restatement_{lang}') for lang in st.LANGUAGES
                  if getattr(args, f'restatement_{lang}') is not None}
        if args.lang is not None:
            labels.setdefault(args.lang, args.restatement)
        if labels:
            params['labels'] = labels
    elif args.verb == 'confirm':
        if (args.proposal_id is None) == (args.proposal_flag is None):
            raise ArgumentError('decide confirm names one proposal: PROPOSAL or --proposal')
        if args.user_words is None and args.basis != st.AUTOMATIC:
            raise ArgumentError('the following arguments are required: --user-words')
        action, params = cmd.ACTION_CONFIRM, {'proposal_id': args.proposal_id
                                              or args.proposal_flag,
                                              'user_words': args.user_words,
                                              'channel': args.channel, 'actor': args.actor,
                                              'basis': args.basis,
                                              'delegation_scope': args.delegation_scope}
        if args.agent_concern is not None:
            params['agent_concern'] = args.agent_concern
        if args.adoption_question:     # v0.3 (WP-B): only when given (request identity)
            params['adoption_question'] = True
    elif args.verb == 'note' and args.resolve is not None:
        action, params = cmd.ACTION_RESOLVE_NOTE, {'note_id': args.resolve,
                                                   'user_words': args.text}
    elif args.verb == 'note' and args.withdraw is not None:
        action, params = cmd.ACTION_WITHDRAW_NOTE, {'note_id': args.withdraw,
                                                    'user_words': args.text}
    elif args.verb == 'note':
        action, params = cmd.ACTION_NOTE, {'decision_id': args.about, 'user_words': args.text}
        if args.kind not in (None, st.HOLD):
            params['kind'] = args.kind
    else:
        action, params = cmd.ACTION_WITHDRAW, {'proposal_id': args.proposal_id,
                                               'reason': args.reason}
    return cmd.apply(args.study, action=action, params=params, request_id=args.request_id,
                     expected_revision=args.expected_revision)


def dispatch(args) -> cmd.Outcome:
    if args.command == 'init':
        return cmd.init(args.case, args.study, language=args.lang,
                        reliability_profile=args.reliability_profile,
                        automation=args.automation)
    if args.command == 'mode':
        return cmd.apply(args.study, action=cmd.ACTION_SET_MODE,
                         params={'mode': args.mode, 'user_words': args.user_words},
                         request_id=args.request_id, expected_revision=args.expected_revision,
                         command='mode set')
    if args.command == 'status':
        if args.digest and not args.summary:
            raise ArgumentError('--digest requires --summary')
        if args.fields is not None and not args.summary:
            raise ArgumentError('--fields requires --summary')
        fields = None if args.fields is None else [
            f.strip() for f in args.fields.split(',') if f.strip()]
        return cmd.status(args.study, since=args.since, summary=args.summary,
                          digest=args.digest, fields=fields)
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
            if delegated and conf.get('delegation_scope'):
                delegated += f' ({conf["delegation_scope"]})'
            lines.append(f'decision {d["decision_id"]}: {d["status"]}'
                         + (f' - "{words}" ({conf["channel"]}{delegated})' if words else ''))
        ex = v['executions']
        for eid, r in ex['active'].items():
            lines.append(f'execution {eid} ({r.get("activity")}): {r.get("liveness")}')
        for eid, r in ex['suspected_interrupted'].items():
            lines.append(f'execution {eid} ({r.get("activity")}): outcome unknown, no process '
                         f'holds its lease')
        for eid, r in ex['interrupted'].items():
            lines.append(f'execution {eid} ({r.get("activity")}): interrupted, outcome unknown')
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
    if schema.startswith('hypotrail.session_report/'):
        from .cmd_session_report import markdown
        return markdown(payload)
    if schema == cmd.SCHEMAS['init']:
        lines = [f'study created at {payload["study"]} (revision {payload["revision"]}) on case '
                 f'{payload["case"]["id"]}', f'next action: {payload["next_action"]["message"]}']
        lines += [f'notice: {n["message"]}' for n in payload.get('notices') or []]
        for name, launch in ((payload.get('deliverables') or {}).get('launch') or {}).items():
            lines.append(f'open the {name}: {launch["shell"]}')
        return '\n'.join(lines)
    # v0.2a (WP-A1): readable text for the learning and evidence commands.
    if schema == 'hypotrail.explain/1':
        from .cmd_explain import text
        return text(payload)
    if schema == 'hypotrail.evidence/1':
        from .cmd_evidence import text
        return text(payload)
    if schema == 'hypotrail.data/1':
        from .cmd_data import text
        return text(payload)
    if schema.startswith('hypotrail.understanding'):
        from .cmd_understanding import text
        return text(payload)
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
    """Parse ``argv`` and run the command; never raises for refusals.

    When the opt-in session log is enabled (:mod:`mlkit.study.sessionlog`), the outcome
    is recorded there, without content, after it is final.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    outcome = _run(argv)
    from . import sessionlog

    sessionlog.record(argv, outcome.payload, outcome.exit_code)
    return outcome


def _run(argv: list) -> cmd.Outcome:
    name = argv[0] if argv else ''
    # A command with a verb is named with it (`decide confirm`, `export handoff`), as its
    # own payloads name it (WP-I).
    command = ' '.join(argv[:2]) if name in ('decide', 'export', 'mode', 'understanding',
                                             'automation') \
        else name
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
        build_parser(listing=True).print_help()
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
