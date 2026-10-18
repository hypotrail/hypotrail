'use strict';
// What the panel says, for a junior, next to the engine's own refusal message, which is
// always shown verbatim. These sentences explain what happened; they never suggest
// words to type (the junior's confirmation must stay their own).

const NOTHING = 'Nothing was recorded.';

const BY_REASON = {
  missing_user_words: 'Your reply was empty.',
  bare_acknowledgement: 'Your reply only acknowledged the proposal; it did not say, in your words, what you are deciding.',
  negative_reply: 'Your reply reads as a refusal, a hesitation, or a reservation, so it was not taken as a confirmation. If you disagree, say so in the chat or withdraw the proposal.',
  unrelated_reply: 'Your reply shares no word or number with the proposal, so it cannot be read as an answer to it.',
  proposal_not_found: 'This proposal does not exist any more.',
  proposal_withdrawn: 'This proposal was withdrawn.',
  proposal_superseded: 'A newer proposal replaced this one.',
  proposal_confirmed: 'This proposal is already confirmed.',
  same_request: 'This proposal cannot be confirmed by the request that created it.',
  proposal_stale: 'A decision this proposal rests on changed since it was made; it needs a new proposal.',
  delegation_needs_basis: 'Your reply hands the choice to the assistant. A delegation is recorded in the chat, not in this panel.',
  not_a_delegation: 'The engine did not read this reply as a delegation.',
  restatement_not_default: 'The proposal does not state that it is the assistant\'s recommended default.',
  delegation_not_given_at_this_pause: 'This decision needs your own words or a delegation given at this pause, in the chat.',
  // CLI-CONTRACT-COMPANION §13 (WP-0): a reserved command of an engine that predates it.
  not_implemented: 'The study engine in this environment does not have this command yet.',
};

const BY_CODE = {
  stale_revision: 'The study changed after the panel showed it. The panel has been refreshed: read the proposal again before answering.',
  decision_on_hold: 'This decision is on hold in your own words. Resolve the hold in the chat before confirming.',
  precondition_missing: 'An earlier step must be confirmed first.',
  dataset_changed: 'The case or dataset files changed since the study was created. Start a new study.',
  invalid_value: 'The proposed value is not valid for this decision.',
  study_busy: 'Another command is writing to the study. Try again in a moment.',
  idempotency_conflict: 'This request id was already used for another request.',
  unknown_proposal: 'This proposal does not exist.',
  proposal_not_open: 'This proposal is not open any more.',
  read_only: 'This process is read-only (HYPOTRAIL_READ_ONLY=1).',
  study_missing: 'The study state is missing.',
  integrity_error: 'The study state does not match its digest. Do not edit `.hypotrail/` by hand.',
  invalid_arguments: 'The CLI refused the arguments of this request.',
  internal_error: 'The CLI failed unexpectedly.',
  unsupported_capability: 'The study engine does not support this request.',
};

/** {code, reason, engineMessage, human, details} for a `hypotrail.error/1` payload. */
function describe(payload) {
  const error = (payload && payload.error) || {};
  const code = typeof error.code === 'string' ? error.code : 'unknown_error';
  const details = error.details && typeof error.details === 'object' ? error.details : {};
  const reason = typeof details.reason === 'string' ? details.reason : null;
  const human = (reason && BY_REASON[reason]) || BY_CODE[code] || 'The engine refused this request.';
  return {
    code, reason,
    engineMessage: typeof error.message === 'string' ? error.message : '',
    human: `${human} ${NOTHING}`,
    details: summariseDetails(code, details),
  };
}

/** A few safe, flat lines from the refusal details (the full payload stays in the CLI). */
function summariseDetails(code, details) {
  const lines = [];
  if (code === 'stale_revision') {
    if (Number.isInteger(details.expected_revision)) lines.push(`Revision read by the panel: ${details.expected_revision}`);
    if (Number.isInteger(details.current_revision)) lines.push(`Current revision: ${details.current_revision}`);
    for (const change of Array.isArray(details.changes_since) ? details.changes_since.slice(0, 10) : []) {
      const params = (change && change.params) || {};
      const about = params.decision_id || params.proposal_id || params.note_id || '';
      lines.push(`Changed at revision ${change && change.revision}: ${change && change.action}${about ? ' (' + about + ')' : ''}`);
    }
  }
  if (code === 'decision_on_hold') {
    for (const note of Array.isArray(details.notes) ? details.notes : []) {
      lines.push(`On hold (${note && note.note_id}): "${note && note.user_words}"`);
    }
  }
  if (code === 'precondition_missing' && Array.isArray(details.missing)) {
    for (const m of details.missing.slice(0, 10)) {
      lines.push(`Missing: ${typeof m === 'string' ? m : (m && (m.text || m.decision || m.id || JSON.stringify(m)))}`);
    }
  }
  return lines.map(l => String(l));
}

module.exports = { describe, BY_REASON, BY_CODE };
