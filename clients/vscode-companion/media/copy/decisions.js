// Copy of the Decisions view (COMPANION-ADVANCED §6.2.4, §15): panel-owned English strings.
// They hold no digit outside placeholders, never suggest words to type, and, for a
// regression study, none of the vocabulary of a decision rule (INV-12): the strings that
// differ by task are functions of the task. Owned by WP-U2.
(function (HT) {
  'use strict';
  const regression = task => task === 'regression';
  HT.copy.decisions = {
    trialsTitle: 'Before you answer: the trial budget and the family shortlist',
    waitingTitle: 'Waiting for your answer',
    nothingWaiting: 'Nothing is waiting for your answer. The assistant proposes decisions in the chat.',
    // v0 wording, kept at stage v0 (CA.11: v0 behaves as before).
    nothingWaitingV0: 'No open proposal. The assistant proposes decisions in the chat.',
    pause: (n, task) => `Pause ${n} · ${({ 1: 'framing', 2: 'evaluation design', 3: regression(task) ? 'model choice' : 'business trade-off' })[n] || ''}`,
    // WP-E1 (R22): the origin, the proposal id and the revision are under Details only.
    byAgent: 'Proposed by the agent; not a decision yet.',
    byPanel: 'Proposed from this panel by an earlier version; not a decision yet.',
    madeAt: (pid, rev) => (rev === null || rev === undefined ? `Proposal ${pid}` : `Proposal ${pid}, made at revision ${rev}`),
    restatedAs: 'The assistant proposes:',
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
    // WP-E1 (R22): one line when a confirmation invalidates nothing.
    effectsNothing: 'Confirming changes nothing already done.',
    effectsFirst: 'This is the first decision of the study, so nothing recorded so far is invalidated.',
    kept: 'Kept',
    keptFits: 'both models and their predictions, nothing refitted',
    toConfirmAgain: 'To confirm again',
    regenerated: 'Regenerated',
    becomesStale: 'Becomes stale',
    refitted: 'To compute again',
    nothing: 'nothing',
    artefactNames: { report: 'report', notebook: 'notebook', editable: 'editable notebook', workbench: 'workbench' },
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
      policy: regression(task) ? 'the third decision' : 'the decision rule',
      model_choice: 'the model choice',
      conclusion: 'the conclusion',
    }),
    supersedes: pid => `It replaces the open proposal ${pid}.`,
    supersedesOpen: 'It replaces the proposal that is open now.',
    blockedTitle: 'If you confirm it in the chat now, the engine will refuse it:',
    effectsMissing: 'The impact preview is not available.',
    // WP-E1 (R23, ADR 0004 amendment): decisions are made in the chat only.
    // R16 (owner session 2026-10-26): a choice the chat asks before any proposal exists.
    choiceTitle: name => `${name.charAt(0).toUpperCase()}${name.slice(1)}: the assistant asks you to choose in the chat`,
    choiceOptions: 'The options the engine accepts now:',
    choiceHint: 'Choose in the chat with your assistant: it then proposes your choice, and you adopt it there. This panel records no choice.',
    choiceAskQuestion: 'Can you explain these options and what each one would mean for my study?',
    answerInChat: 'Answer in the chat',
    answerInChatHint: 'Confirm, change, or withdraw this proposal in the chat with your assistant. This panel records no decision.',
    ask: 'Ask the agent about this',
    askQuestion: 'Can you explain this proposal and what confirming it would change in my study?',
    queueTitle: 'Needs your answer again',
    previously: 'Previously: ',
    openNew: 'Open the new proposal',
    noNewProposal: 'No new proposal yet. Ask the agent to propose it again.',
    askShort: 'Ask the agent',
    askAbout: title => `${title}, open`,
    chooseInWhatIf: 'Choose in What if?',
    historyTitle: 'Decision history',
    historyCaption: 'Confirmations recorded in the study, newest first. The revision and the time are in the hover of each decision.',
    columns: ['Decision', 'Your words', 'How'],
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
    channelWords: channel => (channel === 'webview' ? 'in this panel' : channel === 'chat' ? 'in the chat'
      : channel === 'choice' ? 'chosen as an option in the chat' : channel),
    // v0.3 (WP-B, R27): a trade-off confirmed without a reason.
    noReason: 'no reason given',
    concern: 'Point raised by the agent before you confirmed, kept by you: ',
    correction: 'Your later correction, in your words: ',
    corrections: 'Corrections in your words',
    // WP-A7 (ADR 0005): the confirmation mode, read only (it changes in the chat, in words).
    modeTitle: 'What counts as your answer',
    modeLine: mode => `This study uses the ${mode} mode.`,
    modeNames: { guided: 'guided', training: 'training', express: 'express' },
    modeRules: task => [
      'An answer adopts the open proposal: "yes, I adopt it" is enough, or a short yes to the question "Do you adopt this decision?".',
      'It is not an answer when it asks a question or keeps a condition such as "yes, but" or "unless".',
      `A reason is optional, also for ${regression(task) ? 'the model choice' : 'the decision rule'} and the conclusion; without one, the record says "no reason given".`,
      'When the assistant raises a point about your reason, you may keep your words; the point is recorded next to them.',
    ],
    modeOther: 'This mode is described in the chat; the panel shows its name only.',
    // WP-B5: the opening of the final test is a chat act; its card explains and points there.
    finalTestTitle: 'Answer this one in the chat',
    finalTestBody: 'Opening the final test is decided in the chat. This panel has no field and no button for it.',
    finalTestBodyTraining: 'Opening the final test is decided in the chat, in your own words and with your reason. This panel has no field and no button for it.',
    finalTestOnce: 'The final test opens once. Afterwards it is never measured again, and anything changed is marked as made after it.',
    modeChange: 'The mode changes only in the chat, in your own words; this panel cannot change it.',
    atRevision: rev => `revision ${rev}`,
    superseded: 'superseded',
    supersededAt: rev => (rev === null || rev === undefined ? 'superseded' : `superseded at revision ${rev}`),
    noHistory: 'No confirmation is recorded yet.',
    notAuthenticated: 'Recorded words, not an authenticated signature.',
    unconfirmedTitle: 'Proposals that were not confirmed',
    // WP-E1: the proposal id is in the hover, not in the text.
    proposalStatus: (status, reason) => `${status}${reason && reason !== status ? ' · ' + String(reason).replace(/_/g, ' ') : ''}`,
    historyError: 'The decision history could not be read.',
    retry: 'Retry',
  };
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
