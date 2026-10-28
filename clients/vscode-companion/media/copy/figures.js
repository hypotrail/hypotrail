// Copy of the step figures, method diagrams and end-of-study blocks (lot P: owner remarks R34
// to R53 of 2026-10-28; ADR 0004 decision 14). Panel-owned English strings: no digit outside
// placeholders filled from the engine's values or counts, no exclamation mark, no suggested
// words of a decision, none of the vocabulary of a decision rule in a regression study
// (INV-12). The French twin is media/copy-fr/figures.js (test/copy-fr.test.js).
(function (HT) {
  'use strict';
  HT.copy.figures = {
    // --- Now: the figures behind the step (R39-R45) -------------------------------------------
    lookAt: 'To answer, look at',
    figuresOf: 'The figures of this step',
    noChart: 'No chart for this point.',
    stageLine: stage => `The figures of each step appear from stage ${stage}.`,
    reading: 'Reading the figures...',
    frames: {
      structural: '◇ structural reading, without the target',
      target: '◐ exploration of the target · a look, counted',
      development: '◐ development evidence · out of fold, used to choose',
      final: '● final evidence · measured once',
      method: '◇ how the study is run · no result',
    },

    // --- the quality check, one row per column (R41) -------------------------------------------
    quality: {
      title: 'Each column of the development rows: its range, its skewness, its missing cells',
      columns: { column: 'Column', range: 'Range (low percentile, median, high percentile)', skew: 'Skewness', missing: 'Missing', verdict: 'Verdict' },
      changed: 'changed',
      kept: 'no change',
      noVerdict: 'The engine gives no verdict per column here: these are the figures the draft read.',
      threshold: t => `bound ${t}`,
      concl: (changed, n) => (changed ? `The draft changes ${changed}; the other ${n} columns keep the fixed preparation, on the same figures.`
        : `No column is changed: the ${n} columns keep the fixed preparation, on the same figures.`),
      rows: n => `${n} development rows, the target not read`,
      category: 'category',
      indicator: 'The draft also adds an indicator column of the missing cells, for the columns that have some.',
    },

    // --- the diagnostics behind the variants (R44) and the models (R45) -------------------------
    residuals: {
      scatterTitle: model => `Observed against predicted, out of fold · ${model}`,
      x: 'predicted', y: 'observed', diagonal: 'perfect prediction',
      sample: (shown, n) => `${shown} of the ${n} development rows, evenly spaced in prediction order.`,
      byFeature: (column, model) => `Mean residual by ${column} · ${model}`,
      bias: (model, value) => `Mean residual of ${model}: ${value}; above zero, the model predicts too low on average.`,
      bend: 'A residual that changes sign along a column is a curve the linear model misses.',
    },
    budget: {
      title: 'Trial budget',
      line: (used, max) => `${used} of ${max} variants used`,
      why: 'Each variant tried on the same rows is one more chance of a good figure by luck: the budget bounds it.',
    },

    // --- the comparison as dots (R42, R45, R47) -------------------------------------------------
    perFold: {
      title: metric => `${metric} of each configuration, fold by fold (dots) and their mean (ring)`,
      reading: 'One row per configuration: each dot is one time-ordered fold, the ring the mean over the folds. The spread of the dots is what the folds say about the noise.',
      numbers: 'The figures as a table',
      mean: 'mean',
    },
    intervalKind: {
      bootstrap: level => ` (bootstrap interval, ${level})`,
      oneSe: ' (mean ± one standard error over the folds)',
    },

    // --- method diagrams (R53) ------------------------------------------------------------------
    diagrams: {
      partition: {
        title: 'How the rows are split',
        development: n => `${n} development rows`,
        sealed: n => `${n} final-test rows, sealed`,
        opened: n => `${n} final-test rows, read once`,
        methods: { quantile_stratified: 'drawn at random within quantiles, so the sealed rows look like the others',
          random: 'drawn at random', temporal: 'the latest rows, in time order' },
        reading: 'The sealed rows are set aside at creation: no chart, no model and no choice reads them until the final test is opened once, in the chat.',
      },
      folds: {
        title: ordered => (ordered ? 'Cross-validation: the development rows in time-ordered blocks' : 'Cross-validation: the development rows in blocks'),
        block: i => `fold ${i}`,
        reading: 'Each block is predicted by a model fitted on the other blocks, later years included; every development row is predicted once, out of fold.',
        span: (lo, hi) => `${lo} to ${hi}`,
      },
      pipeline: {
        title: 'The preparation, learnt inside each fold',
        steps: { column: 'columns', impute: 'missing cells', transform: 'log, cap, grouping', model: 'model' },
        columnText: 'the columns kept',
        modelText: 'fitted on the other folds',
        log: cols => `log: ${cols}`,
        caps: cols => `cap: ${cols}`,
        indicator: 'an indicator of missing cells',
        none: 'no change',
        reading: 'Each fold learns its preparation on the rows of the other folds only, then applies it to the rows it predicts: the predicted rows never shape their own preparation.',
      },
      oneSe: {
        title: metric => `The one-standard-error rule on ${metric}`,
        band: 'best + one standard error',
        best: 'best',
        picked: 'kept: the simplest inside the band',
        reading: 'The configurations whose mean lies inside the band cannot be told apart from the best on these folds; the rule keeps the simplest of them. It is a rule of the tool, not your decision.',
      },
      ledger: {
        title: 'Exposure ledger: when the target was looked at',
        look: 'a look at the target',
        opening: 'the final test opened',
        now: 'now',
        revision: r => `revision ${r}`,
        reading: 'Every look at the target is counted; the final test is opened once. Changing the split later does not make what was seen unseen.',
        none: 'No look at the target recorded yet.',
      },
    },

    // --- the end (R48, R52, R49) --------------------------------------------------------------
    devFinal: {
      title: 'Development and final test, side by side',
      configuration: 'Configuration',
      development: 'Development (out of fold, used to choose)',
      final: 'Final test (read once)',
      difference: chosen => `Difference: ${chosen} minus the reference`,
      criterion: 'Your success criterion',
      notMeasured: 'not measured: the final test measures only the chosen model',
      chosen: 'chosen',
      chart: metric => `${metric} with its interval, development (◐) and final test (●), on one scale`,
      bound: 'the criterion\'s bound on the final test',
      met: 'met', notMet: 'not met', uncertain: 'uncertain',
      criterionCell: (bound, verdict) => `error at most ${bound}: ${verdict}`,
    },
    conclusionParts: {
      establishes: 'What the study establishes',
      notEstablish: 'What it does not establish',
      next: 'And after',
    },
    after: {
      handoffLead: 'The handoff pack collects your decisions, the cited results and the limits for a reviewer.',
      handoffWhere: 'You choose a parent folder; the files written are listed in the Deliverables drawer.',
      azureTitle: 'Azure ML export plan',
      azureLead: 'Read only: the plan lists the files the export would write; nothing is written to read it.',
      azureFiles: n => `${n} files`,
      azureKinds: { added: 'added', adapted: 'adapted', rendered: 'rendered', preserved: 'kept from the template', generated: 'generated',
        copied: 'copied', shared: 'shared' },
      azureFamilies: { linear: 'linear regression', logistic: 'logistic regression', ridge: 'ridge regression', ebm: 'Explainable Boosting Machine',
        hgb: 'gradient boosting' },
      azureModel: family => `Model: ${family}`,
      azureTemplate: (id, version) => `Template: ${id} ${version}`,
      azureStatus: (config, artifact) => `Configuration: ${config} · model file: ${artifact}`,
      azureMissing: n => `${n} fields still to fill in by the team (workspace, compute, identity)`,
      azureCloud: 'Never run in the cloud: no Azure job or endpoint is ever started from this panel or from these exports.',
      azureFilesFold: 'The files of the plan',
      azureButton: 'Export the Azure ML project',
      azureHint: 'You choose a folder outside the study; the study records nothing.',
      azureNotSupported: 'The Azure ML export is not available for this model.',
      azureReading: 'Reading the export plan...',
      azureOut: path => `Written to ${path}`,
      azureDone: n => `${n} files written.`,
      exportPlanLater: stage => `The Azure ML export plan appears here from stage ${stage}; ask for it in the chat meanwhile.`,
    },

    // --- What if? in its own tab (R51) --------------------------------------------------------
    whatif: {
      open: 'Open What if? in a wide tab',
      openHint: 'A read-only editor tab: nothing is recorded there.',
      tabTitle: 'What if? · read only',
      calm: 'A preview on figures already computed: nothing is recorded.',
      why: 'Why it matters',
      whyBody: 'A rule or a model changed after seeing the validation figures becomes a result-dependent choice. The study marks it, whether you came through What if? or not; this preview records nothing and decides nothing: the chat does.',
      residualTitle: 'Residual explorer',
      largestTitle: model => `The largest errors · ${model}`,
      largestColumns: { row: 'row', observed: 'observed', predicted: 'predicted', residual: 'residual' },
      configuration: 'Configuration',
      noDiagnostics: 'No diagnostics registered yet: the residual explorer appears once the models are diagnosed.',
      byYearMissing: 'No chart by model year: the diagnostics register no residual by that column.',
    },

    // --- R44: a calm line for a result-dependent change -------------------------------------
    contingent: {
      line: 'Chosen after seeing results: noted as data-dependent.',
      why: 'Why it is noted',
    },

    // --- R43: the running card and the limit lines -----------------------------------------
    running: 'Computing, started from the chat. The result will appear here; nothing to answer yet.',
    runningWhat: what => `Computing: ${what}.`,
    limits: {
      prediction_time: 'Nothing is measured yet: the moment of the prediction fixes which columns may be used.',
      feature_availability: 'Nothing is measured yet: a column known only after the prediction would leak the answer.',
      split: 'Nothing is measured yet: the split decides which rows will judge the models.',
      success_criterion: 'No model is seen yet: the criterion is fixed before any figure of a model.',
      structural_eda: 'This check reads the development rows without the target: it is not a look at the answer.',
      preprocessing: 'The preparation rests on the structure of the development rows, not on the target.',
      train_eda: 'These charts read the target of the development rows: every look is counted.',
      final_test: 'The final test is read once, for the chosen model: it judges the choice, it does not make it.',
      conclusion: 'The final test establishes how the chosen model did on rows it never saw; it does not establish future performance or a cause.',
    },

    // --- R38: a done step without a headline ------------------------------------------------
    fallbackHeadlines: {
      discover_data: (rows, dev, sealed) => (rows ? `${rows} rows read: ${dev} to develop, ${sealed} sealed for the final test.` : 'The data card was read.'),
      structural_eda: 'The structure of the development rows was checked.',
      train_eda: 'The target was explored on the development rows.',
      models: 'The reference and the candidate model were fitted and compared out of fold.',
      default: 'Done.',
    },

    // --- R50: an opened done step in the path -------------------------------------------------
    decidedBy: { own: 'decided by you', automatic: 'recorded by the automatic mode', delegated: 'delegated to the assistant' },
    decision: 'Decision: ',
    figuresInPath: 'Its figures',
  };
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
