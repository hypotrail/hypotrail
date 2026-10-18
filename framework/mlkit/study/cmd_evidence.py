"""``hypotrail evidence``: results, lineage, exposure ledger, impacts, and the EDA catalog.

    hypotrail evidence --study DIR [--result RID] [--limit N] [--json]

CLI-CONTRACT-COMPANION §5 (C5), payload ``hypotrail.evidence/1``. Read-only (R1-R5).

**WP-0 stub.** The arguments are parsed. The command refuses with
``unsupported_capability`` (``details.reason: not_implemented``) until WP-E2 replaces
this module; WP-E2 removes ``WP0_STUB``.
"""
from __future__ import annotations

import argparse

from . import commands as cmd
from .errors import not_implemented

SCHEMA = 'hypotrail.evidence/1'
PAYLOAD_KEYS = ('schema', 'ok', 'study', 'revision', 'task', 'results', 'truncated', 'lineage',
                'exposure', 'impacts', 'eda_catalog', 'sources', 'detail')
DEFAULT_LIMIT = 200
WP0_STUB = True


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--result', default=None, metavar='RID',
                        help='add the detail of this result (64 hexadecimal characters)')
    parser.add_argument('--limit', type=int, default=DEFAULT_LIMIT,
                        help='at most N registry entries (at least 1)')


def evidence(study_dir, *, result_id: str | None = None, limit: int = DEFAULT_LIMIT) -> dict:
    """The ``hypotrail.evidence/1`` payload (WP-E2)."""
    raise not_implemented('evidence')


def main(args: argparse.Namespace) -> cmd.Outcome:
    return cmd.Outcome(evidence(args.study, result_id=args.result, limit=args.limit))
