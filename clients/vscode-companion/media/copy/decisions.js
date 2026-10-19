// Copy of the Decisions view (COMPANION-ADVANCED §6.2.4, §15): panel-owned English strings.
// They hold no digit outside placeholders, never suggest words to type, and, for a
// regression study, none of the vocabulary of a decision rule (INV-12): the strings that
// differ by task are functions of the task. Owned by WP-U2.
(function (HT) {
  'use strict';
  const regression = task => task === 'regression';
  HT.copy.decisions = {
    waitingTitle: 'Waiting for your words',
    nothingWaiting: 'Nothing is waiting for your answer. The assistant proposes decisions in the chat.',
    // v0 wording, kept at stage v0 (CA.11: v0 behaves as before).
    nothingWaitingV0: 'No open proposal. The assistant proposes decisions in the chat.',
    pause: (n, task) => `Pause ${n} · ${({ 1: 'framing', 2: 'evaluation design', 3: regression(task) ? 'model choice' : 'business trade-off' })[n] || ''}`,
    byAgent: 'proposal by the agent · not a decision yet',
    byPanel: 'proposal from this panel · not a decision yet',
    madeAt: (pid, rev) => (rev === null || rev === undefined ? `Proposal ${pid}` : `Proposal ${pid}, made at revision ${rev}`),
    restatedAs: 'The assistant restated it as:',
    proposedValue: 'Proposed value: ',
    availability: {
      available_at_prediction: 'available at prediction time',
      uncertain_included: 'uncertain, included',
      uncertain_excluded: 'uncertain, excluded',
      not_available: 'not available',
    },
    evidenceTitle: 'Evidence',
    evidenceChip: (activity, rid8) => `${activity} · ${rid8}…`,
    precisionDelta: (point, low, high) => `precision difference ${point} [${low}, ${high}]`,
    explore: task => (regression(task) ? 'explore the errors →' : 'try other rules →'),
    holdOpen: 'On hold in your words: ',
    holdSentence: '. The engine refuses a confirmation of this decision until you resolve the hold in the chat.',
    holdOpenV0: id => `On hold in your words (${id}): `,
    holdResolved: 'Your condition, resolved: ',
    holdsTitle: 'On hold',
    effectsTitle: 'If you confirm',
    effectsLoading: 'Reading what a confirmation would change...',
    effectsUpdating: 'Updating...',
    effectsFirst: 'Nothing recorded so far is invalidated.',
    kept: 'Kept',
    keptFits: 'both models and their predictions, nothing refitted',
    toConfirmAgain: 'To confirm again',
    regenerated: 'Regenerated',
    becomesStale: 'Becomes stale',
    refitted: 'To compute again',
    nothing: 'nothing',
    artefactNames: { report: 'report', notebook: 'notebook', workbench: 'workbench' },
    and: ' and ',
    // Short names of the decisions to confirm again (the mockup's "the conclusion").
    decisionNames: task => ({
      prediction_time: 'the prediction moment',
      feature_availability: 'the available variables',
      split: 'the split',
      policy: regression(task) ? 'the third decision' : 'the calling rule',
      model_choice: 'the model choice',
      conclusion: 'the conclusion',
    }),
    supersedes: pid => `It replaces the open proposal ${pid}.`,
    blockedTitle: 'The engine will refuse a confirmation now:',
    effectsMissing: 'The impact preview is not available.',
    answerLabel: 'Your answer to this proposal, in your own words',
    answerLabelV0: 'Your answer, in your own words',
    answerHint: 'Say what you accept and why it fits your situation. "ok" or "yes" alone is not enough. ' +
      'Nothing is filled in for you. What you type is recorded verbatim, with channel "webview".',
    answerHintV0: 'What you type is recorded verbatim as your confirmation, with channel "webview". ' +
      'The engine checks it like an answer in the chat: an acknowledgement alone is not a decision. ' +
      'To hand the choice to the assistant, say so in the chat; this panel does not record delegations.',
    noDelegation: 'To hand the choice to the assistant, say so in the chat; this panel does not record delegations.',
    typing: (before, after) => `The study changed while you were typing (revision ${before} to ${after}). ` +
      'Read the proposal again before you answer.',
    reviewerNote: 'Read-only reviewer mode: this panel records no answer.',
    confirm: 'Confirm in my words',
    withdraw: 'Withdraw proposal',
    ask: 'Ask the agent about this',
    working: 'Working...',
    confirmed: (name, channel) => `Confirmed ${name} in your words (channel ${channel}).`,
    recorded: 'Recorded: ',
    lastOutcomeTitle: 'Last answer from this panel',
    unknownHint: 'Look at the history below: a confirmation recorded in your words appears there.',
    queueTitle: 'Needs your words again',
    previously: 'Previously: ',
    openNew: 'Open the new proposal',
    noNewProposal: 'No new proposal yet. Ask the agent to propose it again.',
    askShort: 'Ask the agent',
    askAbout: title => `${title}, open`,
    chooseInWhatIf: 'Choose in What if?',
    historyTitle: 'Decision history',
    historyCaption: 'Confirmations recorded in the study, grouped by decision, newest first.',
    columns: ['Decision', 'Words', 'Basis and channel', 'When'],
    basis: (basis, scope) => (basis === 'delegated_default'
      ? (scope === 'standing' ? 'delegated (standing)' : scope === 'this_decision' ? 'delegated (this decision)' : 'delegated')
      : basis === 'explicit' ? 'explicit' : basis),
    basisChannel: (basisText, channel) => `${basisText} · ${channel}`,
    atRevision: rev => `revision ${rev}`,
    supersededAt: rev => (rev === null || rev === undefined ? 'superseded' : `superseded at revision ${rev}`),
    noHistory: 'No confirmation is recorded yet.',
    notAuthenticated: 'Recorded words, not an authenticated signature.',
    unconfirmedTitle: 'Proposals that were not confirmed',
    proposalStatus: (pid, status, reason) => `${pid} · ${status}${reason && reason !== status ? ' · ' + reason : ''}`,
    historyError: 'The decision history could not be read.',
    retry: 'Retry',
  };
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
