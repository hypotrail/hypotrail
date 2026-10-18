"""``hypotrail preview proposal DECISION --value V``: the engine's draft of a proposal.

CLI-CONTRACT-COMPANION §4 (C4), payload ``hypotrail.proposal_draft/1``. Read-only
(R1-R5). Dispatched by :mod:`mlkit.study.cmd_preview`. The draft texts come from
``content/drafts.yaml``; a client never writes a restatement itself.

**WP-0 stub.** Refuses with ``unsupported_capability`` (``details.reason:
not_implemented``) until WP-E3 replaces this module; WP-E3 removes ``WP0_STUB``.
"""
from __future__ import annotations

from .errors import not_implemented

SCHEMA = 'hypotrail.proposal_draft/1'
PAYLOAD_KEYS = ('schema', 'ok', 'study', 'revision', 'decision_id', 'value', 'proposable',
                'missing', 'restatement', 'rationale', 'evidence', 'supersedes_proposal',
                'recorded', 'note')
DRAFT_DECISIONS = {'binary': ('policy',), 'regression': ('model_choice',)}
NOTE = 'Draft only: nothing was recorded. Proposing creates a proposal, not a decision.'
WP0_STUB = True


def preview_proposal(study_dir, decision_id: str, value: str) -> dict:
    """The ``hypotrail.proposal_draft/1`` payload (WP-E3)."""
    raise not_implemented('preview proposal')
