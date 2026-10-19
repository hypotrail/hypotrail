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
    // WP-A5: the proposal id is in the hover (title) and under Details, not in the text.
    madeAt: (pid, rev) => (rev === null || rev === undefined ? 'Proposed in the chat' : `Proposed at revision ${rev}`),
    restatedAs: 'The assistant restated it as:',
    proposedValue: 'In short: ',
    recordedValue: 'Recorded value: ',
    details: 'Details',
    availability: {
      available_at_prediction: 'available at prediction time',
      uncertain_included: 'uncertain, included',
      uncertain_excluded: 'uncertain, excluded',
      not_available: 'not available',
    },
    evidenceTitle: 'Evidence',
    evidenceChip: (activity, rid8) => `${activity} · result ${rid8}…`,
    evidenceChipWords: name => `See ${name} →`,
    precisionDelta: (point, low, high) => `Share of successes among the cases picked, against the baseline: ${point} (interval ${low} to ${high})`,
    explore: task => (regression(task) ? 'explore the errors →' : 'try other rules →'),
    holdOpen: 'On hold in your words: ',
    holdSentence: '. The engine refuses a confirmation of this decision until you resolve the hold in the chat.',
    holdOpenV0: id => `On hold in your words (${id}): `,
    holdResolved: 'Your condition, resolved: ',
    holdsTitle: 'On hold',
    effectsTitle: 'If you confirm',
    effectsTitleOpening: 'If you open it in the chat',
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
      // WP-A7: the two decisions of WP-A4, in the words of media/copy/junior.js.
      success_criterion: 'the success criterion',
      preprocessing: 'the data preparation',
      // WP-B5: the two decisions of WP-B1.
      model_variant: 'the variant to compare',
      final_test: 'the opening of the final test',
      policy: regression(task) ? 'the third decision' : 'the calling rule',
      model_choice: 'the model choice',
      conclusion: 'the conclusion',
    }),
    supersedes: pid => `It replaces the open proposal ${pid}.`,
    supersedesOpen: 'It replaces the proposal that is open now.',
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
      `Read the proposal again before you answer. A confirmation now names revision ${before}, so the engine refuses it.`,
    reread: revision => `I read the proposal again at revision ${revision}`,
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
    columns: ['Decision', 'Your words', 'How', 'When'],
    basis: (basis, scope) => (basis === 'delegated_default'
      ? (scope === 'standing' ? 'delegated (standing)' : scope === 'this_decision' ? 'delegated (this decision)' : 'delegated')
      : basis === 'explicit' ? 'explicit' : basis),
    basisChannel: (basisText, channel) => `${basisText} · ${channel}`,
    // WP-A7 (ADR 0005): the basis of a confirmation as a chip, with what it means in a hover.
    basisChip: {
      restated: 'restated', endorsed: 'endorsed', delegated_default: 'delegated', explicit: 'your words',
    },
    basisHelp: {
      restated: 'Your words repeat what the proposal says: you restated it.',
      endorsed: 'Your words agree with the proposal without repeating it: you endorsed it.',
      delegated_default: 'You handed this choice to the assistant\'s recommended default, in the chat.',
      explicit: 'Recorded in your own words before the guided rule named the kinds of answer.',
    },
    channelWords: channel => (channel === 'webview' ? 'in this panel' : channel === 'chat' ? 'in the chat' : channel),
    concern: 'Point raised by the agent before you confirmed, kept by you: ',
    correction: 'Your later correction, in your words: ',
    corrections: 'Corrections in your words',
    // WP-A7 (ADR 0005): the confirmation mode, read only (it changes in the chat, in words).
    modeTitle: 'What counts as your answer',
    modeLine: mode => `This study uses the ${mode} mode.`,
    modeNames: { guided: 'guided', training: 'training', express: 'express' },
    modeRules: task => [
      'An answer is a reply to the open proposal, in your own words, that agrees with it.',
      'It is not an answer when it is only "ok", asks a question, or keeps a condition such as "yes, but" or "unless".',
      `For ${regression(task) ? 'the model choice' : 'the calling rule'} and the conclusion, also give your reason: why it fits your situation.`,
      'When the assistant raises a point about your reason, you may keep your words; the point is recorded next to them.',
    ],
    modeOther: 'This mode is described in the chat; the panel shows its name only.',
    // WP-B5: the opening of the final test is a chat act; its card explains and points there.
    finalTestTitle: 'Answer this one in the chat',
    finalTestBody: 'Opening the final test is decided in the chat, in your own words and with your reason. This panel has no field and no button for it.',
    finalTestOnce: 'The final test opens once. Afterwards it is never measured again, and anything changed is marked as made after it.',
    modeChange: 'The mode changes only in the chat, in your own words; this panel cannot change it.',
    // WP-A7: the reason the guided rule asks for at a trade-off, said before typing.
    reasonHint: 'This decision is a trade-off: say why it fits your situation, not only that you agree.',
    reasonDecisions: ['policy', 'model_choice', 'conclusion', 'final_test'],
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
