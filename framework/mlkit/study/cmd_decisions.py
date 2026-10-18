"""``hypotrail decisions``: every decision, proposal, confirmation, and reconfirmation.

    hypotrail decisions --study DIR [--json]

CLI-CONTRACT-COMPANION §2 (C2), payload ``hypotrail.decisions/1``. Read-only (R1-R5).

**WP-0 stub.** The command is registered and its arguments are parsed. It refuses with
``unsupported_capability`` (``details.reason: not_implemented``) until WP-E1 replaces
this module. The names below are the frozen interface WP-E1 implements; WP-E1 removes
``WP0_STUB``.
"""
from __future__ import annotations

import argparse

from . import commands as cmd
from .errors import not_implemented

SCHEMA = 'hypotrail.decisions/1'
PAYLOAD_KEYS = ('schema', 'ok', 'study', 'revision', 'task', 'decisions', 'proposals', 'history',
                'reconfirm_queue', 'notes')
WP0_STUB = True


def configure(parser: argparse.ArgumentParser) -> None:
    """No arguments besides ``--study`` and ``--format``/``--json``."""


def decisions(study_dir) -> dict:
    """The ``hypotrail.decisions/1`` payload (WP-E1)."""
    raise not_implemented('decisions')


def main(args: argparse.Namespace) -> cmd.Outcome:
    return cmd.Outcome(decisions(args.study))
