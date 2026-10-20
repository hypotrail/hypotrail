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
    regression: 'regression',
    reviewer: 'Reviewer, read-only',
    switchStudy: name => `Study: ${name} ▾`,
    revision: n => `revision ${n}`,
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
      W6: 'Acknowledged in your words.',
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
