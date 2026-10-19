"""``hypotrail run``: execute one activity, or acknowledge an interrupted execution.

    hypotrail run ACTIVITY [--column X [--max-groups N]] [--rule RULE ...]
                  --request-id ID --expected-revision REV --study DIR
    hypotrail run --acknowledge-interruption EXECUTION_ID --user-words TEXT
                  --request-id ID --expected-revision REV --study DIR

Activities: ``split``, ``eda.target_rate``, ``eda.special_values``, ``eda.rate_by
--column X``, ``fit.baseline``, ``fit.logistic``, ``policy.evaluate --rule R``
(``policy.evaluation`` is the slot name and is accepted too). ``--rule`` repeats:
``threshold:t`` (inclusive ``>=``) or ``capacity:k``. A policy evaluation reuses the
persisted predictions of the current fits: it never fits a model.

Output: one ``hypotrail.run/1`` document (see ``mlkit.study.executions``). Its
``status`` is ``promoted``, ``late_not_promoted`` (stored, not promoted: the state
changed while it computed), ``already_current``, ``running`` (replay while another
process computes), ``failed``, ``interrupted_unknown``, or ``acknowledged``.

An acknowledgement needs ``--user-words``: the junior's verbatim reply after being told
that the outcome is unknown. It is recorded in the execution record (D2): an agent may
not acknowledge, or rerun, an interrupted execution on its own.

Exit codes: 0 committed or replayed; 2 refusal; 3 committed but an artefact is stale
or failed; 4 an execution has an unknown outcome (``interrupted_execution_pending``
refusals included).

Test hooks, honoured only with ``HYPOTRAIL_TEST_HOOKS=1``: ``HYPOTRAIL_FAULT`` set to
``run_after_reserve`` or ``run_before_promote`` ends the process abruptly at that
point (``os._exit``); ``run_pause_before_promote:DIR`` writes ``DIR/ready`` and waits
for ``DIR/go`` before promoting; ``run_fail_before_promote`` makes the computation fail;
``recover_kill`` and ``fail_kill`` end the process after an execution's exposure is
recorded and before the ``run.recover`` or ``run.fail`` commit (review fix M2). Several
faults may be listed, comma-separated.

pandas and scikit-learn are imported only by the computation.
"""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from . import activities as act
from . import commands as cmd

FAULT_ENV = 'HYPOTRAIL_FAULT'
HOOKS_ENV = 'HYPOTRAIL_TEST_HOOKS'
FAULT_EXIT = 70
PAUSE_TIMEOUT = 120.0


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('activity', nargs='?', choices=act.CLI_NAMES,
                        help='activity to run (omit with --acknowledge-interruption)')
    parser.add_argument('--column', default=None,
                        help='column of eda.rate_by, eda.mean_by, or eda.distribution')
    parser.add_argument('--max-groups', dest='max_groups', type=int, default=None,
                        help='eda.rate_by / eda.mean_by: show this many largest groups and fold '
                             'the other values into one group (default 20)')
    parser.add_argument('--rule', action='append', default=None,
                        help='policy rule: threshold:t or capacity:k (repeatable)')
    parser.add_argument('--acknowledge-interruption', dest='acknowledge', default=None,
                        metavar='EXECUTION_ID',
                        help='acknowledge an execution with an unknown outcome (no restart)')
    parser.add_argument('--user-words', default=None,
                        help="with --acknowledge-interruption: the junior's verbatim reply after "
                             'being told the outcome is unknown')
    parser.add_argument('--request-id', required=True,
                        help='fresh per intent; replay the same one after a timeout')
    parser.add_argument('--expected-revision', required=True, type=int,
                        help='the revision you read with status')


def _die(_plan) -> None:
    os._exit(FAULT_EXIT)


def _pause(folder: Path):
    def hook(_plan) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'ready').write_text(str(os.getpid()))
        deadline = time.monotonic() + PAUSE_TIMEOUT
        while not (folder / 'go').exists():
            if time.monotonic() > deadline:
                raise TimeoutError('test pause was never released')
            time.sleep(0.05)
    return hook


def _raise(_plan) -> None:
    raise RuntimeError('test hook: the computation failed')


def test_hooks() -> dict:
    """Fault hooks from the environment (only with ``HYPOTRAIL_TEST_HOOKS=1``).

    ``HYPOTRAIL_FAULT`` may list several faults, comma-separated."""
    if os.environ.get(HOOKS_ENV) != '1':
        return {}
    hooks = {}
    for fault in filter(None, os.environ.get(FAULT_ENV, '').split(',')):
        if fault == 'run_after_reserve':
            hooks['after_reserve'] = _die
        elif fault == 'run_before_promote':
            hooks['before_promote'] = _die
        elif fault == 'run_fail_before_promote':
            hooks['before_promote'] = _raise
        elif fault == 'recover_kill':
            hooks['recover_kill'] = _die
        elif fault == 'fail_kill':
            hooks['fail_kill'] = _die
        elif fault.startswith('run_pause_before_promote:'):
            hooks['before_promote'] = _pause(Path(fault.split(':', 1)[1]))
    return hooks


def main(args: argparse.Namespace) -> cmd.Outcome:
    from mlkit.reliability import CommandRefused
    from . import executions
    from .errors import StudyError

    # StudyError, not cli.ArgumentError: under ``python -m mlkit.study.cli`` the CLI module
    # is ``__main__`` and a class imported from ``mlkit.study.cli`` would not be caught.
    if args.acknowledge is not None:
        if args.activity or args.column or args.rule or args.max_groups is not None:
            raise StudyError('invalid_arguments',
                             '--acknowledge-interruption takes no activity or option.')
        if not isinstance(args.user_words, str) or not args.user_words.strip():
            raise StudyError('invalid_arguments',
                             '--acknowledge-interruption needs --user-words: tell the junior the '
                             'outcome is unknown, ask before acknowledging, and record their '
                             'reply verbatim.')
    elif not args.activity:
        raise StudyError('invalid_arguments',
                         'name an activity, or use --acknowledge-interruption EXECUTION_ID.')
    elif args.user_words is not None:
        raise StudyError('invalid_arguments',
                         '--user-words goes with --acknowledge-interruption only.')
    try:
        if args.acknowledge is not None:
            return executions.acknowledge(args.study, args.acknowledge,
                                          request_id=args.request_id,
                                          expected_revision=args.expected_revision,
                                          user_words=args.user_words)
        options = {'column': args.column, 'rules': args.rule, 'max_groups': args.max_groups}
        return executions.run(args.study, args.activity, options, request_id=args.request_id,
                              expected_revision=args.expected_revision, hooks=test_hooks())
    except (CommandRefused, StudyError) as exc:
        if exc.code == 'interrupted_execution_pending':
            return cmd.Outcome(cmd.error_payload('run', exc), cmd.EXIT_UNKNOWN_OUTCOME)
        raise
