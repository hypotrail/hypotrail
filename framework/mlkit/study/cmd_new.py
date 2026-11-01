"""``hypotrail new NAME``: start a study (onboarding, ``docs/plans/ONBOARDING-SPEC.md`` §3).

    hypotrail new NAME --data FILE [--brief FILE] [--context TEXT | --context-file FILE]
                  [--lang en|fr]                                   (Lot 2, agent S)
    hypotrail new NAME --case PATH ...                             (Lot 1, agent P)

The ``--data`` path is :func:`mlkit.study.cmd_prepare.start`: a case folder ``NAME.case/``
and a study folder ``NAME/`` in a preparing state, sealed later by ``hypotrail seal``. The
``--case`` path (an existing case) belongs to Lot 1 (``create_study``); this module only
dispatches between the two.
"""
from __future__ import annotations

import argparse

from . import commands as cmd
from .errors import StudyError

# The study is NAME itself: ``--study`` is not used.
STUDY_OPTIONAL = ('new',)


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('name', help='the study folder to create (NAME.case/ is created next '
                                     'to it with --data)')
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--data', default=None, help='one data file (CSV, UTF-8)')
    source.add_argument('--case', default=None, help='an existing case (case.yaml or folder)')
    parser.add_argument('--brief', default=None,
                        help='with --data: the brief (PDF, Word .docx, Markdown .md, or .txt)')
    parser.add_argument('--context', default=None,
                        help='with --data: a short free-text context, instead of a brief')
    parser.add_argument('--context-file', default=None,
                        help='with --data: a UTF-8 file holding that context')
    parser.add_argument('--lang', choices=('en', 'fr'), default='en',
                        help='the study language')


def main(args: argparse.Namespace) -> cmd.Outcome:
    if args.study is not None:
        raise StudyError('invalid_arguments', 'new takes NAME, not --study.')
    if args.data is not None:
        from . import cmd_prepare
        return cmd_prepare.start(args.name, args.data, brief=args.brief,
                                 context=args.context, context_file=args.context_file,
                                 language=args.lang)
    raise StudyError('unsupported_capability', 'new --case is not available in this version.',
                     details={'command': 'new --case'})
