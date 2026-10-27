// Copy of the Overview view (COMPANION-ADVANCED §6.1, §15): panel-owned English strings.
// They hold no digit outside placeholders filled from models, never suggest the words of
// an acknowledgement or a confirmation (both are said in the chat: R23, R31), and use none of the vocabulary of a decision rule
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

    // Your next move (§6.1.0, WP-A5)
    hero: {
      pause: (n, task) => `Pause ${n} · ${({ 1: 'framing', 2: 'evaluation design', 3: task === 'regression' ? 'model choice' : 'business trade-off' })[n] || ''}`,
      nextStep: 'the next step',
      becauseChanged: 'Your earlier answer was set aside because something it rests on changed. The reason is in Decisions.',
      successShare: 'On the validation rows, the share of successes among the cases it picks is ',
      // WP-B5: under cross-validation the evaluation reads out-of-fold predictions.
      successShareOutOfFold: 'On the out-of-fold predictions of the development rows, the share of successes among the cases it picks is ',
      averageErrorOutOfFold: name => `On the out-of-fold predictions of the development rows, ${name} is off by `,
      finalChat: 'Answer it in the chat. This panel has no control that opens the final test.',
      interval: level => (level ? ` (${level} interval ` : ' (interval '),
      to: ' to ',
      close: ')',
      againstBaseline: ', against ',
      averageError: name => `On the validation rows, ${name} is off by `,
      againstOther: name => ` on average, against ${name} at `,
    },

    // Where we are (§6.1.1)
    whereTitle: 'Where we are',
    goal: 'Goal',
    decided: 'Decided',
    nothingDecided: 'Nothing is decided yet.',
    toConfirmAgain: 'to confirm again',
    delegated: 'left to the assistant',
    // L9 (R20): recorded by the automatic mode, waiting for your review.
    automatic: 'automatic, to review',
    recapDetails: 'Details: the engine\'s recap',
    // WP-A7: the success criterion against the evaluation (the term first, then its use).
    criterion: {
      title: 'Success criterion',
      status: { met: 'met', uncertain: 'uncertain', not_met: 'not met', not_assessed: 'not assessed yet' },
      why: {
        met: 'The gain reaches your minimum, and its interval stays above zero.',
        uncertain: 'The gain reaches your minimum, but its interval includes zero: it may be chance.',
        not_met: 'The gain stays below the minimum you fixed before seeing the results.',
        not_assessed: 'There is no current evaluation to compare with it yet.',
      },
      gain: rule => `Gain over the baseline in the share of successes among the cases picked${rule ? ` when you ${rule}` : ''}: `,
      reduction: 'Reduction of the mean baseline\'s validation error: ',
      points: ' points',
      interval: ' (interval ',
      to: ' to ',
      close: ')',
      contradicts: 'Your conclusion adopts although the criterion is not met. The checks flag it; confirm it again only with a reason.',
    },
    noRecap: 'No recap yet.',
    openInDecisions: 'Open in Decisions',

    // WP-B5: the final test in "Where we are" (sealed, opened, changed after), and the
    // confirmation mode explained (ADR 0005); both are read only.
    finalTestTitle: 'Final test',
    modeTitle: 'Answers',

    // The journey (§6.1.2)
    journeyTitle: 'The plan',
    mapTitle: 'The journey',
    // v0.3 (WP-E2): the journey bar and why a step came back.
    stepsDone: (done, total) => `${done} of ${total} steps done`,
    // v0.3 (WP-K): the journey bar's short step labels (the validated mockup's words), so a
    // narrow panel never breaks a word; the plan's full title stays in the hover and for
    // screen readers. A step without a label here shows its title.
    journeyLabels: {
      discover_data: 'Data', prediction_time: 'Moment', feature_availability: 'Variables', split: 'Split',
      success_criterion: 'Criterion', structural_eda: 'Quality', train_eda: 'Explore', preprocessing: 'Preparation', models: 'Models',
      model_variant: 'Variants', policy: 'Rule', model_choice: 'Choice', final_test: 'Final test', conclusion: 'Conclusion',
    },
    reopenedWhy: 'A step came back: a new proposal or a changed decision asks you to answer again in the chat. The steps after it stay as they are until you do.',
    // v0.3 (owner addition, I1): how the panel works.
    guide: {
      eyebrow: 'About this panel',
      title: 'How this panel works',
      lead: 'This panel reads the study through the hypotrail command line and shows it. It keeps nothing of its own: the chat, the report and the notebook stay complete without it.',
      points: [
        'Decisions are proposed, confirmed or withdrawn in the chat only. Here you read them, and a button copies a ready question for the chat.',
        'The panel can run an exploration chart of the engine, regenerate the report and notebook, and export a handoff pack. Nothing else: a run that stopped is acknowledged in the chat.',
        'Every figure is an engine value; hover a number to see where it comes from. "Why?" opens the reasons and caveats behind a sentence.',
        'The language toggle at the top changes the panel only; the study is not touched.',
      ],
      tabsLabel: 'What each tab is for',
    },
    noMoments: 'The study engine does not group the steps into moments yet; the plan is listed in order.',
    marks: { done: '✓', awaiting_confirmation: '●', needs_reconfirmation: '↺', ready: '○', blocked: '○', reopened: '↺' },
    markText: { done: 'done', awaiting_confirmation: 'waiting for you', needs_reconfirmation: 'confirm again', ready: 'ready',
      blocked: 'blocked', reopened: 'reopened, waiting for you' },
    pauseWords: pause => `pause ${pause} · your words`,
    pauseDelegated: pause => `pause ${pause} · delegated`,
    pauseAutomatic: pause => `pause ${pause} · automatic, to review`,
    pauseWaiting: pause => `pause ${pause} · waiting for you`,
    pauseAgain: pause => `pause ${pause} · confirm again`,
    pauseReopened: pause => `pause ${pause} · new proposal, waiting for you`,
    reopened: 'new proposal, waiting for you',
    waitingForYou: 'waiting for you',
    confirmAgain: 'confirm again',
    ready: 'ready',
    after: title => `after ${title}`,
    blocked: 'blocked',
    currentStep: 'current step',

    // What you cannot claim yet (limits)
    limitsTitle: 'What you cannot claim yet',
    limitsDetails: 'Details: the engine\'s wording',
    forAgent: 'to the assistant',

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
    showAll: n => `Show all ${n} changes`,
    engineRecord: 'Details: the engine\'s record of these changes',

    // Deliverables (§6.1.4, local launch WP-A5)
    deliverablesTitle: 'Your deliverables',
    deliverableLabel: (label, file) => `${label} · ${file}`,
    deliverable: {
      report: { label: 'Report', what: 'The evolving HTML report for your manager or a reviewer.' },
      notebook: { label: 'Study notebook', what: 'Generated by the engine. Read it as an app; it is regenerated after each decision.' },
      editable: { label: 'Editable study copy', what: 'Tracks the generated notebook until your first edit, then is never overwritten. It is not official evidence.' },
      workbench: { label: 'Your workbench', what: 'Your own space. Never overwritten, and not tracked: nothing in it counts as evidence.' },
    },
    statusChip: { ok: 'current', stale: 'out of date', failed: 'failed', missing: 'missing', edited: 'edited', yours: 'yours' },
    statusText: { ok: 'Up to date.', stale: 'Behind the study: regenerate it before you rely on it.', failed: 'It could not be written.',
      missing: 'The file is missing.', edited: 'It was edited by hand.' },
    open: 'Open',
    openFile: 'Open file',
    openInBrowser: 'Open in browser',
    marimoRead: 'Open in Marimo (read)',
    marimoEdit: 'Open in Marimo (edit)',
    marimoName: (action, label) => `${action}: ${label}`,
    openReportName: 'Open the report in the browser',
    openInEditorName: label => `Open ${label.toLowerCase()} in the editor`,
    launchTitle: 'What "Open in Marimo" does',
    launchWhat: 'It opens a VS Code terminal named after the notebook and runs Marimo\'s own local server there:',
    kernel: 'Kernel: the engine environment ',
    kernelUnknown: '(as recorded for this study)',
    kernelTail: '. Stop it with Ctrl+C in that terminal; the panel owns no process.',
    nothingRendered: 'Nothing rendered yet.',
    regenerate: 'Regenerate the report and notebook',
    regenerateWhat: 'Writes only those two files; your workbench and notebook annotations are kept.',
    regeneratedProblems: 'Regenerated with problems',

    // Health (§6.1.5)
    healthTitle: 'Needs attention',
    detailsLabel: 'Details',
    executionsTitle: 'Executions',
    noExecutions: 'No execution has an unknown outcome or a late result.',
    unknownOutcome: activity => `${activity}: the outcome is unknown. Nothing will be restarted.`,
    lateResult: activity => `${activity}: a result was computed for a state that no longer holds; it is stored, not used.`,
    // R31 (owner decision 2026-10-27): the acknowledgement is made in the chat, not here.
    ackInChat: 'Acknowledging this interruption is done in the chat, in your own words: say there that you know this run was interrupted and that its outcome is unknown. \'ok\' alone is not enough. This panel records nothing.',
    rerunInChat: 'Ask in the chat, to acknowledge it or to run it again.',
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
