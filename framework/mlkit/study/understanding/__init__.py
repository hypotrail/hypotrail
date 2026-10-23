"""Understanding and handover review (SPEC-COMPREHENSION v1.0, ADR 0008).

An opt-in review that keeps the understanding of a study inside the team: the author
explains the decisions and behaviours that matter, a colleague takes the critical parts
over, and a reviewed synthesis is versioned with the work. It is **off** by default; it
certifies neither general competence, nor security, nor the scientific validity of the
study, and it never changes a scientific decision, a partition, an exposure record, a
result or the final test.

Modules:

* :mod:`.canonical` canonical JSON v1 and its digests;
* :mod:`.policy` the versioned policy (modes off, coaching, required);
* :mod:`.bank` the task bank and rubrics of a case (``<case>/understanding.yaml``);
* :mod:`.snapshot` the local snapshot and the public source scope, freshness;
* :mod:`.model` the ``understanding`` extension of the study state and input checks;
* :mod:`.evaluate` dimension states, conflicts, reservations, peer coverage, the gate;
* :mod:`.actions` the revisioned actions (through :meth:`StudyStore.execute`);
* :mod:`.export` the reviewed projection, approvals, JSON/Markdown and publication;
* :mod:`.verify` the standalone export verifier and the Git reading (no study needed);
* :mod:`.render` the report section "Understanding and handover".

Assurance is ``human_declared``: a review attributed to a person by a local declaration,
not an authenticated identity. The policy is a cooperative local control.
"""
from __future__ import annotations

from mlkit.study.errors import StudyError

STATE_SCHEMA = 'hypotrail.understanding-state/1'
DIMENSIONS = ('D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7', 'D8')
DIMENSION_TITLES = {
    'D1': 'Purpose', 'D2': 'Data', 'D3': 'Evaluation', 'D4': 'Results',
    'D5': 'Transformations', 'D6': 'Implementation', 'D7': 'Limits',
    'D8': 'Handover and safety'}
# Symbolic refusals (SPEC §15). ``stale_revision`` and the idempotency conflict are the
# engine's existing codes (``idempotency_conflict`` is the spec's ``request_id_conflict``).
CODES = ('understanding_disabled', 'policy_invalid', 'unsupported_assurance', 'stale_revision',
         'idempotency_conflict', 'invalid_transition', 'context_changed', 'unsupported_case',
         'prerequisite_missing', 'evidence_invalid', 'review_required',
         'privacy_approval_required', 'evidence_unavailable', 'path_outside_scope',
         'git_index_conflict', 'export_stale', 'milestone_blocked', 'unsupported_capability')


def refuse(code: str, message: str, next_action: str | None = None, **details) -> StudyError:
    """A refusal without effect: a stable code, a message, the next action, no payload of
    a person's answer."""
    if next_action:
        details['next_action'] = next_action
    return StudyError(code, message, details=details)
