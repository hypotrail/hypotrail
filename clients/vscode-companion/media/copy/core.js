// Copy of the frame (COMPANION-ADVANCED §4.1, §15): panel-owned English strings. They
// never contain digits except through placeholders filled from models, never suggest
// confirmation words, and never use the vocabulary of a decision rule (INV-12), so the
// frame reads the same in a binary and a regression study.
//
// Frozen by WP-0 (keys may be added, not renamed). Each view keeps its strings in
// media/copy/<view>.js under Hypotrail.copy.<view>.
(function (HT) {
  'use strict';
  HT.copy = HT.copy || {};
  HT.copy.core = {
    title: 'Hypotrail study',
    product: 'Hypotrail',
    experimental: 'Experimental · feature flag on',
    stage: s => `stage ${s}`,
    regression: 'regression',
    reviewer: 'Reviewer, read-only',
    switchStudy: name => `Study: ${name} ▾`,
    revision: n => `revision ${n}`,
    // v0.3 (WP-E2, R21): the header's language toggle (UI state only).
    languageLabel: 'Panel language',
    languageNames: { en: 'English', fr: 'Français' },
    // v0.3 (owner addition, I1): one lead sentence at the top of each tab.
    tabLeads: {
      overview: 'Where the study stands, what waits for you, and what you cannot claim yet. Decisions are made in the chat; this panel only shows them.',
      eda: 'First what the data are, read without looking at what is predicted. Then charts on the training rows, each answering one question.',
      decisions: 'Every decision of the study, as recorded. You answer a proposal in the chat; here you read what it says and what it would change.',
      evidence: 'Where every figure comes from: which rows were read, for what, and how sure each figure is.',
      whatif: 'Try a rule or a model on the figures already computed. Nothing here is recorded or decided.',
      learn: 'The terms of the study explained on its own figures, and the pack to hand the study to someone else.',
    },
    // v0.3 (WP-E2): the card pattern (one sentence + "Why?", the faint source line) and the
    // legends of the charts.
    why: 'Why?',
    sourceWord: 'Source',
    legendInterval: 'confidence interval',
    legendBand: 'what chance alone draws',
    legendSmall: 'too few rows to read alone',
    binFrom: 'From',
    binTo: 'To',
    rowsWord: 'Rows',
    readAge: age => `read from CLI · ${age}`,
    justNow: 'just now',
    secondsAgo: s => `${s} s ago`,
    minutesAgo: m => `${m} min ago`,
    refresh: 'Refresh',
    tabsLabel: 'Study panel sections',
    // WP-A7: the EDA tab opens on the data card, so it reads "Data & EDA" (its id stays `eda`).
    tabs: { overview: 'Overview', eda: 'Data & EDA', decisions: 'Decisions', evidence: 'Evidence', whatif: 'What if?',
      learn: 'Learn & hand off' },
    // WP-A7: the header's final-test chip (ADR 0006), on every tab.
    finalTest: {
      sealed: rows => `Final test sealed · ${rows} rows`,
      sealedTitle: 'Set aside when the study was created, before any look at the data. No chart, fit or evaluation reads these rows; they give the one independent figure at the end.',
      opened: rows => `Final test opened · ${rows} rows`,
      openedTitle: 'The final test was opened once, at the end. A figure computed after that is labelled as such.',
      absent: 'No final test',
      absentTitle: 'This study was created before a final test was set aside at the start: no rows are sealed, so every figure comes from rows the study has already used.',
    },
    waiting: n => `${n} waiting for you`,
    reading: 'Reading the study...',
    updating: 'Updating...',
    loadErrorTitle: 'The panel could not read the study.',
    loadErrorDetail: 'Details from the CLI',
    loadErrorNext: 'Nothing shown before is current until the study can be read again. Press Retry. If it fails again, ask the assistant in the chat to run the study status and read the message below.',
    retry: 'Retry',
    lastRead: n => `Last read at revision ${n}; the study could not be read now.`,
    viewError: 'This part of the panel could not be read.',
    notAvailable: 'Not available in this stage.',
    recapTitle: 'Where the study stands',
    recapShow: 'Show the recap',
    recapHide: 'Hide the recap',
    alertsLabel: 'Alerts',
    openHealth: 'Go to what needs attention',
    footer: 'Reads the hypotrail CLI only · no state of its own · the chat, report and notebook stay complete without it.',
    updated: n => `Updated to revision ${n}.`,
    refusedTitle: (code, reason) => `The engine refused: ${code}${reason ? ' (' + reason + ')' : ''}`,
    engineVerbatim: 'Engine message, verbatim:',
    failedTitle: 'The request failed.',
    invalidTitle: 'Not sent.',
    cancelledTitle: 'Cancelled.',
    problemsTitle: 'Done, with problems:',
    notPromotedTitle: 'Computed, not used.',
    recordedWords: 'Recorded in your words: ',
    done: {
      W4: 'Ran on training rows.',
      W5: 'Regenerated the report and notebook.',
      W7: 'Exported the handoff pack.',
    },
    modalCancel: 'Cancel',
    close: 'Close',
    showValues: 'Show values',
    hideValues: 'Hide values',
    small: 'small',
    working: 'Working...',
  };
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
