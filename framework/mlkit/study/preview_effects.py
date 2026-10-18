"""``hypotrail preview effects PROPOSAL``: the dry run of ``decide confirm``.

CLI-CONTRACT-COMPANION §3 (C3), payload ``hypotrail.preview_effects/1``. Read-only
(R1-R5). Dispatched by :mod:`mlkit.study.cmd_preview`. It must call the same
``commands.confirmation_plan(state, store, proposal_id)`` as ``decide confirm``, on a deep
copy of the state, so the preview cannot drift from the confirmation.

**WP-0 stub.** Refuses with ``unsupported_capability`` (``details.reason:
not_implemented``) until WP-E1 replaces this module; WP-E1 removes ``WP0_STUB``.
"""
from __future__ import annotations

from .errors import not_implemented

SCHEMA = 'hypotrail.preview_effects/1'
PAYLOAD_KEYS = ('schema', 'ok', 'study', 'revision', 'proposal_id', 'decision_id', 'value',
                'previous', 'mutation', 'row', 'reason', 'stale_results', 'stale_slots',
                'kept_slots', 'refit', 're_eda', 're_policy', 'recompute', 'reconfirm_required',
                'supersedes_proposal', 'blocked', 'artifacts_after', 'notes', 'recorded', 'note')
NOTE = ('Preview of a confirmation: nothing was recorded. The engine still checks the words '
        'when you confirm.')
WP0_STUB = True


def preview_effects(study_dir, proposal_id: str) -> dict:
    """The ``hypotrail.preview_effects/1`` payload (WP-E1)."""
    raise not_implemented('preview effects')
