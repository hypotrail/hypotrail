// Copy of the Overview view (COMPANION-ADVANCED §6.1, §15): panel-owned English strings.
// They hold no digit outside placeholders filled from models, never suggest the words of
// an acknowledgement or a confirmation, and use none of the vocabulary of a decision rule
// (INV-12), so one table serves a binary and a regression study. Owned by WP-U1.
(function (HT) {
  'use strict';
  HT.copy.overview = {
    // v0 subset (stage v0, unchanged in behaviour).
    v0: {
      recap: 'Where the study stands',
      plan: 'Plan',
      step: (position, total, title) => `Step ${position} of ${total}: ${title}.`,
      allDone: 'Every step is done.',
      next: message => `Next: ${message}`,
      deliverables: 'Deliverables',
      nothingRendered: 'Nothing rendered yet.',
      openReport: 'Open the report in the browser',
      open: label => `Open ${label.toLowerCase()}`,
      nyd: 'Not yet defensible',
      alsoListed: ids => `Also listed: ${ids}.`,
    },

    // Where we are (§6.1.1)
    whereTitle: 'Where we are',
    whereSource: 'recap from status --summary',
    noRecap: 'No recap yet.',
    openInDecisions: 'Open in Decisions',

    // Study map (§6.1.2)
    mapTitle: 'Study map',
    noMoments: 'The study engine does not group the steps into moments yet; the plan is listed in order.',
    marks: { done: '✓', awaiting_confirmation: '●', needs_reconfirmation: '↺', ready: '○', blocked: '○' },
    markText: { done: 'done', awaiting_confirmation: 'waiting for you', needs_reconfirmation: 'confirm again', ready: 'ready',
      blocked: 'blocked' },
    pauseWords: pause => `pause ${pause} · your words`,
    pauseDelegated: pause => `pause ${pause} · delegated`,
    pauseWaiting: pause => `pause ${pause} · waiting for you`,
    pauseAgain: pause => `pause ${pause} · confirm again`,
    waitingForYou: 'waiting for you',
    confirmAgain: 'confirm again',
    ready: 'ready',
    after: title => `after ${title}`,
    blocked: 'blocked',
    currentStep: 'current step',

    // Since your last session (§6.1.3)
    sinceTitle: 'Since your last session',
    sinceTime: time => `Since ${time}`,
    thisSession: 'This session',
    sinceStart: 'Since the start of the study',
    keptFits: 'Models unchanged, nothing refitted.',
    truncated: 'Older changes are not listed. The Decisions tab has the full history.',
    nothingChanged: 'Nothing has changed since then.',
    noDigest: 'The study engine does not list the changes between sessions yet.',
    showSince: 'Show changes since',
    optionBoundary: revision => `your last session (revision ${revision})`,
    optionStart: 'the start of the study',

    // Deliverables (§6.1.4)
    deliverablesTitle: 'Deliverables',
    deliverableLabel: (label, file) => `${label} · ${file}`,
    open: 'Open',
    openReportName: 'Open the report in the browser',
    openInEditorName: label => `Open ${label.toLowerCase()} in the editor`,
    nothingRendered: 'Nothing rendered yet.',
    regenerate: 'Regenerate the report and notebook',
    regeneratedProblems: 'Regenerated with problems',

    // Health (§6.1.5)
    healthTitle: 'Health',
    executionsTitle: 'Executions',
    noExecutions: 'No execution has an unknown outcome or a late result.',
    unknownOutcome: activity => `${activity}: the outcome is unknown. Nothing will be restarted.`,
    lateResult: activity => `${activity}: a result was computed for a state that no longer holds; it is stored, not used.`,
    reply: 'Your reply, in your own words',
    replyHint: 'Say that you know this run was interrupted and its outcome is unknown. \'ok\' alone is not enough.',
    acknowledge: 'Acknowledge in my words',
    rerunInChat: 'To run it again, ask the agent in the chat.',
    acknowledgedEarlier: 'Acknowledgements',
    checksTitle: 'Checks of the deliverables',
    checksRunning: 'Running the checks...',
    checksClean: 'clean',
    checksErrors: n => (n === 1 ? `${n} error` : `${n} errors`),
    checksWarnings: n => (n === 1 ? `${n} warning` : `${n} warnings`),
    checksNone: 'No finding.',
    checksFailed: 'The checks could not be read.',
    retry: 'Retry',
    openFinding: where => `Open ${where}`,
    nydTitle: 'Not yet defensible',
    more: ids => `More: ${ids}`,
    updating: 'Updating...',
    working: 'Working...',
  };
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
