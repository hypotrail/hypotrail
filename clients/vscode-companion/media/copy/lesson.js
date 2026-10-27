// Copy of the lesson pattern (2026-10-27, owner-approved mockup docs/plans/mockups/
// panel-lesson-style-fr.html; notes R29, R30): the journey rail and what remains, the position
// line, "At this step" of each tab, the notions, the guided readings of the charts, the
// "Learn more" folds, the "Next" lines, and the ready questions the panel copies for the chat.
// Panel-owned English strings: no digit outside placeholders filled from models, no
// exclamation mark, no suggested words of a decision, and none of the vocabulary of a decision
// rule in the texts a regression study shows (INV-12). The French twin is
// media/copy-fr/lesson.js (test/copy-fr.test.js). Functions return a string or a list of
// strings and nodes (components/lesson.js `parts`).
(function (HT) {
  'use strict';
  HT.copy.lesson = {
    atThisStep: 'At this step',
    inThisStudy: 'In this study',
    keep: 'What we keep',
    defSep: ': ',
    learnMore: 'Learn more',
    next: 'Next',
    andThen: 'And then',
    tags: { tool: 'tool', rule: 'rule', culture: 'culture' },
    folds: { ex: 'Example', why: 'Why it holds', casse: 'Where it breaks', code: 'Code', more: 'Learn more' },

    // --- the guided reading of a chart (R30) ------------------------------------------------
    guide: { why: 'Why this chart', frame: 'Frame', rows: 'Rows', model: 'Model', how: 'How to read it',
      howNote: 'step by step', concl: 'What we conclude', attn: 'Watch out' },
    frames: {
      structural: '◇ structural reading, without the target',
      target: '◐ exploration of the target · a look, counted',
      predictors: '◇ predictors only, without the target',
      development: '◐ development evidence · used to choose',
      final: '● final evidence · measured once',
      sandbox: '◐ development evidence · nothing is recorded',
    },
    none: 'none',
    rowsOf: n => `${n} rows`,
    developmentRows: n => `${n} development rows`,
    trainingRows: n => `${n} training rows`,
    validationRows: n => `${n} validation rows`,
    finalRows: n => `${n} final-test rows, read once`,
    read: {
      bars: {
        steps: ['Each bar is one row of the values; its length is the value written on its right.',
          'A grey bar is the reference; a hatched bar has too few rows to be read alone.'],
        attn: 'A bar says how much, not why: a difference between groups is not an effect of the group.',
      },
      points: {
        steps: ['Each point is the value of one group; the line around it is its interval.',
          'The grey band is what chance alone draws for groups of that size: a point outside it suggests a real difference.',
          'A hollow point has too few rows to be read alone.'],
        attn: 'Hunting through many groupings for one that shows something multiplies the chances of a pattern due to chance.',
      },
      intervals: {
        steps: ['One row per model or configuration: the dot is the estimate, the line its interval.',
          'The grey row is the reference.',
          'Every row shares one axis, so their positions compare directly.'],
        attn: 'Two overlapping lines do not prove two models equal when they were measured on the same rows: their paired difference decides.',
      },
      difference: {
        steps: ['The dot is the difference; the line is its interval.',
          'The vertical line marks zero: no difference at all.',
          'The side of zero says which one is ahead; an interval across zero says these rows cannot tell.'],
        attn: 'An interval that includes zero does not prove there is no difference; it says these rows cannot tell.',
      },
      histogram: {
        steps: ['Each column is a range of values; its height is the number of rows in it.',
          'The left axis names the largest count and its half.',
          'A tile apart counts the exact zeros of a skewed column.'],
        attn: 'A histogram describes the rows read here, not the future, and says nothing about causes.',
      },
      boxplot: {
        steps: ['The box covers the middle half of the rows; the thick line inside it is the median.',
          'The whiskers reach the lowest and the highest value.',
          'A longer whisker on one side means a tail on that side.'],
        attn: 'The box describes the rows themselves, not the uncertainty of an average.',
      },
      correlation: {
        steps: ['One cell per pair of columns, in the lower triangle; the diagonal is empty.',
          'The darker the cell, the stronger the association; the orange cells are negative.',
          'An outlined cell reaches the flag level.'],
        attn: 'A strong association between two predictors does not say which one matters for the target.',
      },
      curve: {
        steps: ['Each point is a value the engine recorded; the points are joined in the order of the horizontal axis.',
          'A vertical line marks a share chosen for the study.'],
        attn: 'A curve drawn on the rows used to choose is optimistic: read it again with the final test once it is open.',
      },
      generic: {
        steps: ['Each mark is a value the engine recorded; "Show values" lists them as numbers.'],
        attn: 'Read a chart with its frame: which rows, which model, and whether those rows served to choose.',
      },
    },
    whatifBias: ['One bar per group: to the right of zero, the model predicts too low on average in that group; to the left, too high.',
      'A hatched bar has too few rows to be read alone.'],
    steps: {
      rule: label => `The dashed line marks ${label}.`,
      diagonal: label => `The dashed diagonal is the reference: ${label}.`,
    },
    concl: {
      one: (label, v) => [label, ': ', v, '.'],
      bars: (hi, hiV, lo, loV) => ['Largest: ', hi, ' (', hiV, '). Smallest: ', lo, ' (', loV, ').'],
      points: (hi, hiV, lo, loV) => ['Highest: ', hi, ' (', hiV, '). Lowest: ', lo, ' (', loV, ').'],
      lowHigh: (lo, loV, hi, hiV) => ['Lowest: ', lo, ' at ', loV, '. Highest: ', hi, ' at ', hiV, '.'],
      zero: (label, v, side) => [label, ': ', v, ({ above: ', entirely above zero.', below: ', entirely below zero.',
        across: ', across zero: these rows cannot tell the two apart.', none: '.' })[side] || '.'],
      outsideBand: (k, n) => ` ${k} of ${n} groups lie outside the grey band.`,
      rule: label => ` The dashed line is ${label}.`,
      small: names => ` Too few rows to be read alone: ${names}.`,
      histogram: (lo, hi, n) => ['The fullest range runs from ', lo, ' to ', hi, ', with ', n, ' rows.'],
      zeros: v => [' Exact zeros, apart: ', v, '.'],
      box: (median, q25, q75, min, max) => ['Median ', median, '; the middle half runs from ', q25, ' to ', q75,
        '; the values run from ', min, ' to ', max, '.'],
      boxTail: { upper: ' The upper whisker is longer: a tail of high values.', lower: ' The lower whisker is longer: a tail of low values.',
        even: ' The two whiskers are of similar length.' },
      corrSome: (k, list) => [`${k} pairs reach the flag level: `, list, '.'],
      corrNone: 'No pair reaches the flag level: no two predictors carry almost the same information.',
      curve: (n, first, last) => `The curve joins ${n} labelled points, from ${first} to ${last}.`,
    },

    // --- the journey rail and what remains (R30) -------------------------------------------
    rail: {
      label: 'The journey of the study',
      moments: { frame: 'Frame', evidence: 'Prepare', compare: 'Compare', conclude: 'Conclude' },
      step: (i, n) => `Step ${i} of ${n}`,
      states: { done: 'done', auto: 'automatic, to review in the chat', cur: 'waits for you', wait: 'waits for you',
        ready: 'ready', later: 'after an earlier step' },
      legend: { done: 'done', auto: 'automatic, to review', cur: 'waits for you', ready: 'ready', later: 'after' },
      legendLabel: 'What the marks of the journey mean',
      remain: 'Still to do',
      remainNow: 'answer it in the chat',
      remainNone: 'Every step is done: the report and the notebook carry the study.',
      handoff: 'Then, if you wish, the handoff pack for a reviewer.',
      more: n => ` and ${n} more`,
    },
    where: {
      step: (i, n) => `Step ${i}/${n}`,
      tab: 'tab',
      rest: list => ` · still to do: ${list}`,
      toTabs: '↑ tabs',
      label: 'Where you are',
      states: { awaiting_confirmation: 'waiting for your answer in the chat', needs_reconfirmation: 'to confirm again in the chat',
        reopened: 'a new proposal, in the chat', ready: 'ready', blocked: 'after an earlier step', done: 'done',
        automatic: 'recorded by the automatic mode, to review in the chat' },
    },

    // --- "At this step" (R29): what the tab corresponds to in the study ---------------------
    intros: {
      overview: f => [
        'This is the board of the construction: it says which of the four moments the study is in, what waits for you, and what you cannot claim yet. ',
        f.step ? `Now: ${f.step}${f.waits ? ', waiting for your answer in the chat' : ''}. ` : '',
        'You read it here; you answer in the chat.'],
      eda: () => ['This part corresponds to the first two moments: understanding the data before drawing anything from them, then exploring them without touching the final test. ',
        'It answers "what does a row describe, and what are these columns worth?". ',
        'The decisions they motivate, the availability of the variables and the preparation, are taken in the chat.'],
      decisions: f => ['Every decision of the study goes through a proposal of the assistant and your answer, in the chat. ',
        f.waiting ? `Here you see what waits for you now (${f.waiting}), with its options and what it would change, then the history. `
          : 'Nothing waits for your answer now: here you read the history. ',
        'Nothing is confirmed in this panel: it prepares your answer.'],
      evidence: () => ['This part answers "where does each figure come from, and can it be trusted?". ',
        'It separates what served to choose, the development evidence, from the sealed final test, the one independent measure. ',
        'Read the configurations compared on the same rows and the diagnostics before you answer on the model in the chat.'],
      whatif: f => [f.task === 'regression'
        ? 'A sandbox on the figures already computed, to understand before you answer: where does the model err, and would another configuration do better where it matters? '
        : 'A sandbox on the figures already computed, to understand before you answer: what would a rule on the scores pick, and at what cost? ',
      'Nothing is recorded; if an idea convinces you, the panel copies the question for the chat.'],
      learn: () => ['The last moment, concluding and handing over, is prepared from now on. ',
        'This part takes up the terms of the study on its own figures, makes you say the reasoning out loud, and prepares the pack for a reviewer. ',
        'What you will say in the chat to conclude will lean on these sentences.'],
    },

    // --- "Next" at the end of each tab (R30), by the tab it leads to ----------------------------
    nextLines: {
      eda: 'See what everything rests on: the data, and what exploring them showed.',
      decisions: 'The decisions of the study: what waits for your answer, its options, what it would change, and the history.',
      evidence: 'The evidence the choices rest on, and what stays sealed. Your answer itself is given in the chat.',
      whatif: 'Explore where the model errs and what another configuration would change, without recording anything.',
      learn: 'Say the reasoning out loud, check the terms, and prepare the handoff.',
      overview: 'What remains is said in the chat; this panel shows it at the next revision.',
    },
    goTo: tab => `${tab} →`,
    backTo: tab => `↑ ${tab}`,

    // --- the next move: one action, copying a ready question for the chat ---------------------
    copyQuestion: 'Copy the question',
    inTheChat: 'in the chat',
    questions: {
      await_user_words: name => `I am reading the proposal on ${name}. Could you restate it so that I adopt it or change it in my own words?`,
      reconfirm: name => `Something changed under ${name}. Could you tell me what changed, so that I confirm it again or change it in my own words?`,
      review: name => `The automatic mode recorded ${name} without my words. Could you restate it, so that I adopt it or change it in my own words?`,
      choice: name => `Could you show me the options for ${name} and what each one would change, so that I choose in my own words?`,
      outcome_unknown: () => 'A run stopped before it finished and its outcome is unknown: what do we do? I want to acknowledge it in my own words, or run it again.',
      final_await: () => 'Could you restate the proposal to open the final test, so that I answer it in my own words?',
      final_next: () => 'When can I open the final test, and what will it measure?',
      next: step => `What is the next step, ${step}, and what will it change in my study?`,
      done: () => 'The study is done: what should I read again before I hand it over?',
    },

    // --- notions (the term first, then "In this study") -------------------------------------------
    notions: {
      sealed: {
        term: 'Sealed final test',
        definition: 'rows set aside when the study was created, before any look at the data; nothing reads them until they are opened, once, at the end',
        lead: 'Everything this panel shows before the end comes from the other rows, the development rows.',
        here: n => `${n} rows are sealed; no chart, fit or evaluation has read them.`,
        hereOpened: n => `${n} rows were opened once; a change made since is marked as made after the final test.`,
        why: 'Every choice made on the development rows flatters their figures a little. Only rows that served no choice give an independent figure of the error to expect.',
        casse: 'Opening them twice, or changing a choice after looking at them, turns them into one more development figure: the study marks every change made after the opening.',
        keep: 'The development rows choose; the final test measures, once.',
      },
      criterion: {
        term: 'Success criterion',
        definition: 'the bar a model must clear to be worth adopting, fixed before any result is seen',
        here: (value, status) => [value, ' · ', status, '.'],
        why: 'Fixed before the results, the bar cannot drift towards what happened to work.',
        casse: 'Moving it after seeing the results moves the bar towards what worked; changing it asks you to confirm the conclusion again.',
        keep: 'The bar is set before the race.',
      },
      looks: {
        term: 'Look at the target',
        definition: 'an analysis that read the variable to predict; each one is counted',
        lead: 'The exploration reads the development rows only; the data card and the quality check read the columns without the target.',
        here: n => `${n} looks at the target so far. The data card and the quality check do not read it: they are not looks.`,
        why: 'Each look is one more chance to notice a pattern: the count says how many chances there were.',
        casse: 'The more looks, the more a pattern found among them can be due to chance. A pattern found after many looks needs the final test to be believed.',
        keep: 'Count the looks before believing a pattern.',
      },
      special: {
        term: 'Special value',
        definition: 'a code that stands for something other than a measure, such as "never" or "unknown"; treated as an ordinary number, it distorts a model',
        here: (column, code, meaning, n) => [column, ' holds the code ', code, meaning ? ` (${meaning})` : '', n ? [' on ', n, ' rows'] : '', '.'],
        ex: (column, code) => `A row whose ${column} is ${code} does not have the quantity ${code}: the model receives an indicator and a value learnt from the other rows, never the code as a number.`,
        why: 'The indicator lets the model learn whether the code itself says something; what replaces the code is learnt on the rows each model is fitted on.',
        casse: 'Reading the code as a number puts these rows at the end of the scale. And looking at the target among these rows is already a look at the target: it is counted.',
        keep: 'A special value is a code, not a number.',
      },
      rare: {
        term: 'Rare category',
        definition: 'a value of a categorical column carried by very few rows; what a model learns about it rests on those few rows',
        here: (column, list) => [column, ': ', list, '.'],
        casse: 'A figure computed on a handful of rows can change entirely with one or two more rows: the panel marks such groups "too few rows to be read alone".',
        keep: 'A rare category is read with its count.',
      },
      proposal: {
        term: 'Proposal and decision',
        definition: 'a proposal is the assistant\'s restatement of a choice; it becomes a decision only when you answer it, in the chat',
        here: (n, name) => (name ? [`${n} waits for your answer: `, name, '.'] : 'Nothing waits for your answer now.'),
        why: 'Your words are the record of the decision: the engine keeps them with the revision, and the report quotes them.',
        casse: 'An "ok" before the closed question is not a decision; a question, or a "yes, but", is not an answer. Changing a decision later asks you to confirm again what rests on it.',
        keep: 'The panel shows; the chat decides.',
      },
      automatic: {
        term: 'Automatic decision',
        definition: 'a decision the automatic mode, chosen at launch, recorded with the engine\'s value and without your words; it is neither your answer nor a delegation',
        here: n => `${n} decisions are recorded this way; each one waits for your review in the chat.`,
        casse: 'Until you adopt or change each one in your own words, the study stays not defensible.',
        keep: 'An automatic decision is a draft, not your decision.',
      },
      oneSe: {
        term: 'One-standard-error rule',
        definition: 'among configurations compared on the same folds, keep the simplest whose mean is within one standard error of the best',
        here: (best, mean, se, bound, kept) => ['The best mean is that of ', best, ', ', mean, ', with a standard error of ', se,
          ': the bar sits at ', bound, '. The rule keeps ', kept, '.'],
        why: 'With a few folds, the error moves from one fold to the next; a small gap between two means can come from how the rows fell into the folds. At comparable accuracy, the simpler model is easier to read and to defend.',
        casse: 'The folds are the same for every configuration: the paired difference says whether a gain holds on the same rows, which the rule, reading each mean apart, does not. Whether a small gain is worth a less simple model is your question, in the chat.',
        keep: 'The rule guards against a gain due to the luck of the folds; the paired difference says whether the gain holds on the same rows.',
      },
      outOfFold: {
        term: 'Out-of-fold prediction',
        definition: 'a prediction of a development row by a model fitted without that row: the rows are split into folds, and each fold is predicted by a model fitted on the others',
        why: 'Every development row gets one honest prediction, so the error is read on all of them, not on one small part.',
        casse: 'These predictions served to compare and to choose: the figure of the model kept is flattered by the choice. Rows that share an entity can fall into several folds.',
        keep: 'Out of fold is honest for one model, optimistic for the one chosen.',
      },
      paired: {
        term: 'Paired interval',
        definition: 'the same rows are resampled many times for two models at once; the interval describes their difference',
        here: (cand, ref, text, reps) => ['Between ', cand, ' and ', ref, ': ', text, reps ? [', over ', reps, ' resamples'] : '', '.'],
        why: 'Both models are measured on the same rows, so the luck of the rows cancels out: the paired interval is narrower than the two separate ones.',
        casse: 'An interval that includes zero does not prove the models equal; and these rows served to choose.',
        keep: 'Compare two models on the same rows with their paired difference.',
      },
      residual: {
        term: 'Residual',
        definition: 'the observed value minus the predicted one; positive, the model predicted too low',
        here: (median, q25, q75) => ['Median residual ', median, '; the middle half lies between ', q25, ' and ', q75, '.'],
        why: 'A mean residual near zero in every group means the model errs in both directions as often; a group far from zero is predicted too high or too low as a whole.',
        casse: 'A mean residual near zero does not mean small errors: errors in both directions cancel out. Read it with the mean absolute error of the group.',
        keep: 'Where the residuals lean, the model leans.',
      },
      rule: {
        term: 'A rule on the scores',
        definition: 'turns the model\'s scores into actions: act on every case scored above a value, on the top cases, or on a share of them',
        here: words => ['The rule in the study: ', words, '.'],
        why: 'The scores rank the cases; only a rule says which ones are acted on, and so what it costs and what it gains.',
        casse: 'Choosing the rule on the rows used to compare is optimistic; and a rule that looks best here is still a choice of the business, made in the chat.',
        keep: 'A model ranks; a rule decides what to do with the ranking.',
      },
      handoff: {
        term: 'Handoff pack',
        definition: 'a folder for a reviewer: a summary, the cited results, and the report when it is current; it changes nothing in the study',
        here: n => `It would be named after revision ${n}.`,
        why: 'A reviewer reads the study without the panel and without the chat: every figure in the pack carries its source.',
        casse: 'A report that is not current is left out of the pack; regenerate it first if the reviewer needs it.',
        keep: 'The pack is what a reviewer can check without you.',
      },
    },

    // --- "Learn more" (R30): chips, symbols, abbreviations --------------------------------------
    more: {
      marksTitle: 'What do these marks mean?',
      marks: [
        'Final test sealed: rows set aside when the study was created, before any look. Nothing reads them until they are opened, once, as decided in the chat.',
        'Experimental · feature flag on: this panel sits behind a setting that is off by default; its stage decides which tabs it shows.',
        'Revision: the number of the latest recorded version of the study. Every decision or result increments it; a request made on an outdated revision is refused.',
        'Read from CLI: the panel reads the study only through the hypotrail command. It keeps no state of its own; Refresh reads again.',
        'EN | FR: the language of the panel only; the study is not touched. Words said in the chat stay in their language, marked (en) or (fr).',
        '◇ structural reading: the shape of the data, without the target. ◐ development evidence: computed on the development rows, it served to choose, so it is optimistic. ● final evidence: measured once, on the final test.',
      ],
      abbrTitle: 'Acronyms and abbreviations',
      abbr: {
        common: ['EDA: exploratory data analysis.', 'CLI: the hypotrail command, the panel\'s only source.',
          's.e.: standard error, the uncertainty of an average.', 'CI: confidence interval.',
          'EBM: Explainable Boosting Machine, a model that adds one shape function per variable, readable term by term.'],
        regression: ['MAE: mean absolute error, in the unit of the target.', 'RMSE: root mean squared error; it weighs large errors more than the MAE.'],
        binary: ['AUC: area under the ROC curve; how well the scores rank the cases where the outcome happens above the others (one half is chance).'],
      },
      ackTitle: 'Why words, and not an "ok" button?',
      ack: ['A run that stopped has an unknown outcome: it may have written part of its results. Saying, in your own words, that you know this records that nobody will read those figures as settled. A bare "ok" could be a reflex: the engine refuses it.',
        'Acknowledging restarts nothing and decides nothing. It is done in the chat: this panel does not take your words, it only copies the question.'],
      basisTitle: '"Restated", "endorsed", "automatic"',
      basis: ['Your words, restated: your words repeat what the proposal says.', 'Your words, endorsed: your words agree with the proposal without repeating it.',
        'Automatic, to review: the automatic mode chosen at launch recorded the engine\'s value, without your words. Adopt it or change it in your own words, in the chat.',
        'Left to the assistant: you delegated the choice; it stays to review like an automatic decision.'],
      exposureTitle: 'The exposure register and the sealed rows',
      exposure: ['The register counts which rows were read, and for what: inspection, looks at the target, fits, evaluations. Changing the split does not make rows already explored unseen.',
        'The final-test rows are opened once, after the model is chosen, when you say so in the chat; any change made afterwards is marked as made after the final test.'],
    },
  };
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
