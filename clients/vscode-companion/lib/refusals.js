'use strict';
// What the panel says, for a junior, next to the engine's own refusal message, which is
// always shown verbatim (COMPANION-ADVANCED INV-8, CW.8). These sentences explain what
// happened and that nothing was recorded; they never suggest words to type (the junior's
// confirmation must stay their own): no example reply, no quotation, no wording to copy.
//
// v0 table, extended by WP-U2 with `export_target_exists` (CLI-CONTRACT-COMPANION §12) and
// the refusal contexts of W3 (propose), W4 (run an EDA request), W6 (acknowledge an
// interruption), and W7 (export). The context comes from the payload's `command`, so the
// frozen `describe(payload)` signature of the controller is unchanged.

const NOTHING = 'Nothing was recorded.';

const BY_REASON = {
  missing_user_words: 'Your reply was empty.',
  bare_acknowledgement: 'Your reply only acknowledged the proposal; it did not say, in your words, what you are deciding.',
  negative_reply: 'Your reply reads as a refusal, a hesitation, or a reservation, so it was not taken as a confirmation. If you disagree, say so in the chat or withdraw the proposal.',
  unrelated_reply: 'Your reply does not read as an answer to this proposal: it does not agree with it while talking about it.',
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
  // ADR 0005 (guided confirmation).
  question_reply: 'Your reply asks a question, so it was not taken as a confirmation. Ask it in the chat first.',
  conditional_reply: 'Your reply sets a condition, keeps a reservation, or accepts only part of the proposal, so it was not taken as a confirmation. Settle it in the chat first.',
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
  export_target_exists: 'The chosen folder already holds files, so the engine wrote nothing there. Choose an empty folder or a new one.',
  unknown_result: 'The study has no result with this id.',
  unknown_decision: 'The engine does not know this decision.',
  literal_number_in_text: 'The engine found a number in the proposal text that it cannot trace to a current result.',
  causal_or_forecast_wording: 'The engine found causal or forecast wording in the proposal text.',
  misattributed_delegation: 'The engine found a recommended default credited to the analyst in the proposal text.',
  interrupted_execution_pending: 'An execution has an unknown outcome, so the engine runs nothing until it is acknowledged in your words (Overview, Health).',
  execution_in_progress: 'The same computation is already running.',
  unknown_execution: 'The engine does not list this execution as interrupted any more.',
  invalid_request: 'The engine refused the form of this request.',
  invalid_command: 'The engine does not accept this request.',
  // ADR 0005: the policy, the model choice and the conclusion need a reason.
  reason_required: 'This decision is a trade-off, so the engine records it only with your reason, in your own words.',
  // ADR 0005, v0.2b (WP-B2): the training mode.
  paraphrase_required: 'In the training mode, a confirmation says in your own words what the proposal decides, not only that you agree. The lines below name what your reply does not say yet.',
  // WP-A9 (H3): also a stop in the guided mode until the point is raised in the chat.
  words_contradict_value: 'Your words and the proposal disagree about a variable, so the engine stopped the confirmation. Settle which one you mean in the chat.',
};

// Explanations that depend on the write that was refused (the payload's `command`). A
// `run` refusal about an execution (ambiguous words, unknown execution) is an
// acknowledgement (W6); any other `run` refusal is an EDA request (W4).
const BY_CONTEXT = {
  propose: {
    stale_revision: 'The study changed after the panel read the draft. The panel has been refreshed: look at the draft again before proposing.',
    invalid_value: 'The engine does not accept this value as a proposal for this decision.',
    precondition_missing: 'An earlier step must be confirmed before this decision can be proposed.',
  },
  run: {
    stale_revision: 'The study changed after the panel showed it. The panel has been refreshed: look at the list again before asking for a chart.',
    precondition_missing: 'An earlier step of the plan must be done before this chart can be computed.',
    invalid_value: 'The engine does not accept this column for this chart.',
  },
  acknowledge: {
    stale_revision: 'The study changed after the panel showed it. The panel has been refreshed: read the execution again before acknowledging it.',
    missing_user_words: 'Your acknowledgement was empty.',
    bare_acknowledgement: 'Your reply only acknowledged the interruption; it did not say, in your words, what you know about it.',
    negative_reply: 'Your reply reads as a refusal or a hesitation, so it was not taken as an acknowledgement.',
    unrelated_reply: 'Your reply shares no word with the interrupted execution, so it cannot be read as an acknowledgement of it.',
  },
  export: {
    read_only: 'This process is read-only (HYPOTRAIL_READ_ONLY=1), so the engine exported nothing.',
  },
};

// An engine older than `export --expected-revision` (CR.6) refuses the option itself
// (`invalid_arguments` whose message names it). The panel never exports without it.
const OLDER_ENGINE_EXPORT = 'The study engine in this environment is older than this panel: it does not know the ' +
  'revision check of an export (--expected-revision), so it exported nothing. Update the hypotrail engine of this ' +
  'environment, then export again.';

/** True for an older engine's refusal of `export --expected-revision` (CR.6). */
function olderEngineExport(context, code, message) {
  return context === 'export' && code === 'invalid_arguments' && /--expected-revision/.test(message);
}

/** The refusal context of a payload: propose, run, acknowledge, export, or null. */
function contextOf(payload, code, reason, details) {
  const command = typeof (payload && payload.command) === 'string' ? payload.command : '';
  if (command === 'decide propose') return 'propose';
  if (command.startsWith('export')) return 'export';
  if (command === 'run') {
    const aboutExecution = code === 'ambiguous_confirmation' || code === 'unknown_execution' ||
      (typeof details.execution_id === 'string' && code !== 'execution_in_progress');
    return aboutExecution ? 'acknowledge' : 'run';
  }
  return null;
}

/** {code, reason, engineMessage, human, details} for a `hypotrail.error/1` payload. */
function describe(payload) {
  const error = (payload && payload.error) || {};
  const code = typeof error.code === 'string' ? error.code : 'unknown_error';
  const details = error.details && typeof error.details === 'object' ? error.details : {};
  const reason = typeof details.reason === 'string' ? details.reason : null;
  const where = contextOf(payload, code, reason, details);
  const context = BY_CONTEXT[where] || {};
  const human = olderEngineExport(where, code, String(error.message || '')) ? OLDER_ENGINE_EXPORT
    : (reason && context[reason]) || context[code] || (reason && BY_REASON[reason]) || BY_CODE[code] ||
    'The engine refused this request.';
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
  if (code === 'export_target_exists' && typeof details.path === 'string') lines.push(`Folder: ${details.path}`);
  if (code === 'paraphrase_required' && Array.isArray(details.missing)) {
    for (const m of details.missing.slice(0, 10)) {
      if (m && typeof m.hint === 'string') lines.push(`Not said yet: ${m.hint}`);
    }
  }
  if (code === 'words_contradict_value' && Array.isArray(details.warnings)) {
    for (const w of details.warnings.slice(0, 10)) {
      if (w && typeof w.variable === 'string') lines.push(`Your words and the proposal disagree about ${w.variable}`);
    }
  }
  if (code === 'interrupted_execution_pending' && Array.isArray(details.interrupted)) {
    for (const e of details.interrupted.slice(0, 10)) {
      const id = typeof e === 'string' ? e : (e && e.execution_id);
      if (id) lines.push(`Unknown outcome: ${id}${e && e.activity ? ' (' + e.activity + ')' : ''}`);
    }
  }
  return lines.map(l => String(l));
}

module.exports = { describe, contextOf, BY_REASON, BY_CODE, BY_CONTEXT, NOTHING, OLDER_ENGINE_EXPORT };
