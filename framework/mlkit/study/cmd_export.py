"""``hypotrail export handoff``: a reviewer's pack written under ``--out`` only.

    hypotrail export handoff --study DIR [--out DIR] [--json]

CLI-CONTRACT-COMPANION §7 (C7), payloads ``hypotrail.export/1`` (stdout) and
``hypotrail.handoff/1`` (``handoff.json``). It never changes the study.

**WP-0 stub.** The arguments are parsed. The command refuses with
``unsupported_capability`` (``details.reason: not_implemented``) until WP-E2 replaces
this module; WP-E2 removes ``WP0_STUB``. Nothing is written.
"""
from __future__ import annotations

import argparse

from . import commands as cmd
from .errors import not_implemented

SCHEMA = 'hypotrail.export/1'
HANDOFF_SCHEMA = 'hypotrail.handoff/1'
PAYLOAD_KEYS = ('schema', 'ok', 'study', 'revision', 'kind', 'out', 'files', 'included_report',
                'warnings')
HANDOFF_KEYS = ('schema', 'study', 'revision', 'task', 'case', 'dataset', 'goal', 'decisions',
                'results_cited', 'exposure', 'not_yet_defensible', 'open_items', 'deliverables',
                'reproduce', 'environment')
KINDS = ('handoff',)
FILES = ('handoff.md', 'handoff.json', 'study.html', 'SHA256SUMS')
WARNINGS = ('report_not_current', 'open_proposals', 'open_holds', 'interrupted_executions',
            'sources_changed', 'unconfirmed_decisions')
WP0_STUB = True


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('kind', choices=KINDS)
    parser.add_argument('--out', default=None, metavar='DIR',
                        help='a new or empty folder (default <study>/handoff/revision-<n>/)')


def export_handoff(study_dir, *, out=None) -> tuple[dict, int]:
    """``(hypotrail.export/1 payload, exit code)`` (WP-E2)."""
    raise not_implemented('export handoff')


def main(args: argparse.Namespace) -> cmd.Outcome:
    payload, code = export_handoff(args.study, out=args.out)
    return cmd.Outcome(payload, code)
