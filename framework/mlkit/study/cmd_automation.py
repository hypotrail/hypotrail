"""``hypotrail automation``: the automatic mode chosen at ``init`` (owner session 2026-10-26,
lot L9, remark R20; ADR 0005 and ADR 0006 amendments of 2026-10-26).

    hypotrail automation run [--progress] [--json | --format text|json]
                             --request-id ID --expected-revision REV --study DIR
    hypotrail automation stop --user-words TEXT
                              --request-id ID --expected-revision REV --study DIR

``run`` follows ``next_action`` with the automatic mode the study was created with
(``init --automation until_final_test|full_demo``), recording each decision with
``--basis automatic`` and running each activity, until the mode stops covering the plan,
the junior is needed, or the engine refuses something (:mod:`mlkit.study.automation`). Its
payload is ``hypotrail.automation/1``: ``status`` (``ended`` when the mode reached what it
covers, else ``stopped``), ``reason``, ``stopped_at``, ``refusal``, the ``steps`` taken, and
the ``review_queue`` the junior then walks. ``--progress`` tells on stderr, in the study
language, what is going on (owner session 2026-10-27, R23; :mod:`mlkit.study.automation_words`):
a header (the mode, the case, what the run does, where it stops), one line per decision with
its value in words and why, each computation with the activities' own progress lines and its
key result with the registered figures, and a closing summary (the decisions to review, the
model kept and its figure, what the junior does next). stdout is the one JSON document, or,
with ``--format text`` or by default when stdout is a terminal, its readable summary
(``--json`` keeps the JSON document on a terminal).

``stop`` ends the automatic mode midway, one way, in the junior's own words (recorded in
``mode_history``); the decisions already recorded stay automatic until the junior reviews
them.
"""
from __future__ import annotations

import argparse
import sys

from . import commands as cmd


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('verb', choices=('run', 'stop'),
                        help='run: follow the plan with the automatic mode; stop: end it in '
                             "the junior's words")
    parser.add_argument('--user-words', default=None,
                        help="with stop: the junior's verbatim words asking to stop it")
    parser.add_argument('--progress', action='store_true',
                        help='with run: what is going on, in the study language, on stderr '
                             '(decisions, results, a closing summary); stdout is unchanged')
    parser.add_argument('--request-id', required=True,
                        help='fresh per intent; replay the same one after a timeout')
    parser.add_argument('--expected-revision', required=True, type=int,
                        help='the revision you read with status')


def main(args: argparse.Namespace) -> cmd.Outcome:
    from .errors import StudyError

    if args.verb == 'stop':
        if args.progress:
            raise StudyError('invalid_arguments', '--progress goes with run only.')
        return cmd.apply(args.study, action=cmd.ACTION_END_AUTOMATION,
                         params={'reason': 'stopped', 'user_words': args.user_words},
                         request_id=args.request_id, expected_revision=args.expected_revision,
                         command='automation stop')
    if args.user_words is not None:
        raise StudyError('invalid_arguments', '--user-words goes with stop only: the '
                                              'automatic mode records no words.')
    from . import automation
    from .cmd_run import progress_interval
    payload = automation.run(args.study, request_id=args.request_id,
                             expected_revision=args.expected_revision,
                             progress=sys.stderr if args.progress else None,
                             progress_interval=progress_interval())
    code = cmd.EXIT_OK
    artifacts = payload.get('artifacts') or {}
    if any(isinstance(a, dict) and a.get('status') in ('stale', 'failed')
           for a in artifacts.values()):
        code = cmd.EXIT_ARTIFACT_STALE
    return cmd.Outcome(payload, code)


__all__ = ['configure', 'main']
