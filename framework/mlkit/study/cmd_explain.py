"""``hypotrail explain``: glossary terms with contextual examples, step texts, predictions.

    hypotrail explain --study DIR [--term ID] [--json]

CLI-CONTRACT-COMPANION §6 (C6), payload ``hypotrail.explain/1``. Read-only (R1-R5).

**WP-0 stub.** The arguments are parsed. The command refuses with
``unsupported_capability`` (``details.reason: not_implemented``) until WP-E2 replaces
this module; WP-E2 removes ``WP0_STUB``.
"""
from __future__ import annotations

import argparse

from . import commands as cmd
from .errors import not_implemented

SCHEMA = 'hypotrail.explain/1'
PAYLOAD_KEYS = ('schema', 'ok', 'study', 'revision', 'task', 'terms', 'steps', 'predictions')
WP0_STUB = True


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--term', default=None, metavar='ID', help='only this glossary term')


def explain(study_dir, *, term: str | None = None) -> dict:
    """The ``hypotrail.explain/1`` payload (WP-E2)."""
    raise not_implemented('explain')


def main(args: argparse.Namespace) -> cmd.Outcome:
    return cmd.Outcome(explain(args.study, term=args.term))
