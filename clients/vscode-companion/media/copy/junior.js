// The panel's own copy for the junior (WP-A5, COMPANION-ADVANCED §15.1 two-layer copy).
//
// Layer 1 (this file): sentences the panel shows as primary content, keyed by the engine's
// stable identifiers (`next_action.kind`, decision ids, `not_yet_defensible` ids, digest
// kinds, artefact names), written for the junior in plain business words. Layer 2: the
// engine's own text, shown as it is only when its `audience` is `junior` (or under its
// junior variant), and otherwise only inside a "Details" disclosure. A text whose
// audience is `agent` is never primary content.
//
// The strings hold no digit outside placeholders filled from engine values. Strings that
// differ by task are functions of the task; in a regression study none of them uses the
// vocabulary of a decision rule (INV-12). `values` turns a recorded decision value into a
// readable phrase; the raw value stays available in a hover and under "Details".
(function (HT) {
  'use strict';
  const regression = task => task === 'regression';
  const str = x => (typeof x === 'string' ? x : '');
  const cap = s => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);

  // --- decisions --------------------------------------------------------------------------

  const decisionName = (id, task) => ({
    prediction_time: 'the prediction moment',
    feature_availability: 'the variables you may use',
    split: 'the split',
    policy: regression(task) ? 'the third decision' : 'the calling rule',
    model_choice: 'the model choice',
    success_criterion: 'the success criterion',
    preprocessing: 'the data preparation',
    // WP-B1: named in words; WP-B5 gives them their panel views.
    model_variant: 'the variant to compare',
    final_test: 'the opening of the final test',
    conclusion: 'the conclusion',
  })[id] || String(id || '').replace(/_/g, ' ');

  // Why the decision matters, in the words of the use case (the term first, then its use).
  const why = (id, task) => ({
    prediction_time: 'The prediction moment fixes when the score is computed, so it decides which columns may be used at all.',
    feature_availability: 'Only columns known at the prediction moment may be used; a column filled in later would leak the outcome into the model.',
    split: 'The split sets aside rows the models never learn from, so their errors can be measured honestly.',
    policy: regression(task) ? 'This decision turns the results into an action.'
      : 'The calling rule turns scores into an action: how many clients to call, given what the team can handle.',
    model_choice: 'The model choice picks the model whose errors on the validation rows fit your use.',
    success_criterion: 'The success criterion fixes, before you see the results, how much better than the baseline a model must be to be worth adopting.',
    preprocessing: 'The data preparation says how missing values, rare categories, extreme values and skewed columns are handled; it is learned on the training rows only.',
    // WP-B5: the two decisions of WP-B1.
    model_variant: regression(task)
      ? 'A variant is one change to the model, compared under the same protocol, so the choice between the two has a purpose and is counted.'
      : 'A variant is one change to the model, such as stronger regularisation or one group of variables left out, compared under the same protocol: the choice between the two has a purpose and is counted.',
    final_test: 'The final test is the set of rows sealed when the study was created. Opened once, after the choices, it gives the one figure that did not help to choose; anything changed afterwards is marked as made after it.',
    conclusion: 'The conclusion says what the study supports, and what it does not.',
  })[id] || '';

  // --- readable values ----------------------------------------------------------------------

  const MODEL_NAMES = {
    'fit.logistic': 'the logistic model', 'fit.linear': 'the linear model',
    'fit.variant': 'the variant',
  };
  const modelName = (slot, task) => (slot === 'fit.baseline'
    ? (regression(task) ? 'the mean baseline' : 'the baseline')
    : MODEL_NAMES[slot] || `the ${str(slot).replace(/^fit\./, '').replace(/_/g, ' ')} model`);

  function parse(raw) {
    if (raw && typeof raw === 'object') return raw;
    if (typeof raw !== 'string') return null;
    const t = raw.trim();
    if (t.startsWith('{') || t.startsWith('[')) {
      try { return JSON.parse(t); } catch (_) { return raw; }
    }
    return raw;
  }

  /** The availability groups of a value: {available: [], uncertain: [], excluded: []}. */
  function availability(value) {
    const v = parse(value);
    if (!v || typeof v !== 'object' || Array.isArray(v)) return null;
    const out = { available: [], uncertainIn: [], uncertainOut: [], excluded: [] };
    const put = (status, column) => {
      if (status === 'available_at_prediction') out.available.push(column);
      else if (status === 'uncertain_included') out.uncertainIn.push(column);
      else if (status === 'uncertain_excluded') out.uncertainOut.push(column);
      else if (status === 'not_available') out.excluded.push(column);
    };
    for (const [k, x] of Object.entries(v)) {
      if (Array.isArray(x)) for (const c of x) put(k, String(c));
      else if (typeof x === 'string') put(x, k);
    }
    return out.available.length + out.uncertainIn.length + out.uncertainOut.length + out.excluded.length ? out : null;
  }

  /**
   * A share of rows as a percentage (`share:0.1` -> "10%"): a restatement of the recorded
   * parameter, rounded to two decimals of a percent, not a figure computed from results.
   */
  function sharePercent(p) {
    const x = Number(p);
    if (!Number.isFinite(x)) return null;
    return `${Number((x * 100).toFixed(2))}%`;
  }

  /** A recorded rule (`capacity:N`, `threshold:T`, `share:P`) in words; the numbers are the rule's own. */
  function rule(value, task) {
    // WP-B1: a rule applied to the variant ends with "@fit.variant".
    const [v, model] = str(value).split('@');
    const tail = model === 'fit.variant' ? ', with the variant' : '';
    let m = v.match(/^capacity:([0-9]+)$/);
    if (m && !regression(task)) return `Call the top ${m[1]} by score${tail}`;
    // WP-B5: a share of the scored rows (WP-B3).
    m = v.match(/^share:([0-9.]+)$/);
    if (m && !regression(task) && sharePercent(m[1])) return `Call the top ${sharePercent(m[1])} by score${tail}`;
    m = v.match(/^threshold:([0-9.]+)$/);
    if (m && !regression(task)) return `Call everyone scored ${m[1]} or more${tail}`;
    return null;
  }

  // WP-B1: the variant and the opening of the final test in words.
  function variant(raw) {
    const v = parse(raw);
    if (!v || typeof v !== 'object') return null;
    if (v.kind === 'regularisation') {
      return v.strength === 'weak' ? 'Compare with a less regularised variant'
        : 'Compare with a more regularised variant';
    }
    if (v.kind === 'drop_group') return `Compare with the model without the group "${str(v.group)}"`;
    return null;
  }

  function finalTest(raw, task) {
    const v = parse(raw);
    if (!v || typeof v !== 'object') return null;
    const r = v.rule ? rule(v.rule, task) : null;
    return `Open the final test once for ${modelName(v.model, task)}${r ? ` (${r.toLowerCase()})` : ''}`;
  }

  // v0.2a (WP-A4): the two governance decisions in words. The share is a recorded value
  // shown as a percentage, not a figure the panel computes from results.
  function criterion(raw) {
    const v = parse(raw);
    if (!v || typeof v !== 'object') return null;
    if (typeof v.min_points === 'number') {
      return `Adopt only if precision beats the baseline by at least ${v.min_points} points`;
    }
    if (typeof v.min_share === 'number') {
      return `Adopt only if the validation error is at least ${Math.round(100 * v.min_share)}% below the mean baseline`;
    }
    return null;
  }

  function preparation(raw) {
    const v = parse(raw);
    if (!v || typeof v !== 'object') return null;
    const parts = [];
    if (v.missing && typeof v.missing === 'object') {
      const flagged = Object.keys(v.missing).filter(k => v.missing[k] === 'indicator');
      parts.push(flagged.length ? `missing values flagged (${flagged.join(', ')})` : 'missing values not flagged');
    } else {
      parts.push(v.missing === 'indicator' ? 'missing values flagged' : 'missing values not flagged');
    }
    if (v.rare_category_min_rows) parts.push(`categories under ${v.rare_category_min_rows} rows grouped`);
    const caps = v.caps && typeof v.caps === 'object' ? Object.keys(v.caps) : [];
    parts.push(caps.length ? `extreme values capped (${caps.join(', ')})` : 'no capping');
    const logs = Array.isArray(v.log_transform) ? v.log_transform : [];
    parts.push(logs.length ? `log scale for ${logs.join(', ')}` : 'no log scale');
    const text = cap(parts.join(', '));
    return v.data_contingent ? `${text} (chosen after looking at the outcome)` : text;
  }

  function split(value) {
    const v = parse(value);
    if (!v || typeof v !== 'object') return null;
    const share = typeof v.validation_fraction === 'number' ? HT.format.number(v.validation_fraction, 'pct0') : null;
    if (v.method === 'stratified_random' && share) return `Stratified random split, ${share} of the rows for validation`;
    if (v.method === 'random' && share) return `Random split, ${share} of the rows for validation`;
    if (['kfold_stratified', 'kfold_quantile', 'temporal_folds'].includes(v.method) && typeof v.folds === 'number') {
      return `Cross-validation in ${v.folds} folds: every row is predicted once by a model that did not see it`;
    }
    if (v.method === 'ordinal_cutoff' && v.column !== undefined) {
      return `Split in time order: rows with ${v.column} from ${v.cutoff} on are for validation`;
    }
    return null;
  }

  const VERDICTS = {
    adopt_policy: 'Adopt the calling rule',
    adopt_model: 'Adopt the chosen model',
    keep_baseline: 'Keep the current practice',
    inconclusive: 'Inconclusive',
  };

  /**
   * A recorded decision value in words, or null when the panel has no wording for it (the
   * view then shows the value as recorded). `raw` is the value or its JSON text.
   */
  function value(decisionId, raw, task) {
    if (raw === null || raw === undefined || raw === '') return null;
    switch (decisionId) {
      case 'prediction_time': return typeof raw === 'string' ? cap(raw.trim()) : null;
      case 'feature_availability': {
        const g = availability(raw);
        if (!g) return null;
        const parts = [`${g.available.length} available`];
        if (g.uncertainIn.length) parts.push(`${g.uncertainIn.length} uncertain, kept (${g.uncertainIn.join(', ')})`);
        if (g.uncertainOut.length) parts.push(`${g.uncertainOut.length} uncertain, left out (${g.uncertainOut.join(', ')})`);
        parts.push(`${g.excluded.length} excluded${g.excluded.length ? ` (${g.excluded.join(', ')})` : ''}`);
        return parts.join(' · ');
      }
      case 'split': return split(raw);
      case 'success_criterion': return criterion(raw);
      case 'preprocessing': return preparation(raw);
      case 'model_variant': return variant(raw);
      case 'final_test': return finalTest(raw, task);
      case 'policy': return rule(raw, task);
      case 'model_choice': return typeof raw === 'string' && raw.startsWith('fit.') ? cap(`adopt ${modelName(raw, task)}`) : null;
      case 'conclusion': {
        const v = parse(raw);
        if (!v || typeof v !== 'object') return null;
        const verdict = regression(task) && v.verdict === 'adopt_policy' ? null : VERDICTS[v.verdict] || null;
        const text = str(v.text).trim();
        return [verdict, text].filter(Boolean).join(': ') || null;
      }
      default: return null;
    }
  }

  // --- the next move (keyed by next_action.kind) ------------------------------------------

  const nextMove = {
    eyebrow: 'Your next move',
    await_user_words: { title: name => `Answer the proposal on ${name}`, action: 'Answer in Decisions',
      lead: 'The assistant proposed this in the chat. Nothing changes until you answer in your own words.' },
    reconfirm: { title: name => `Confirm ${name} again`, action: 'Open in Decisions',
      lead: 'Something it rests on changed, so your earlier answer no longer holds until you confirm it again.' },
    acknowledge_interruption: { title: () => 'A run stopped before it finished', action: 'Go to the run',
      lead: 'Its outcome is unknown. Say in your own words that you know this; nothing restarts by itself.' },
    outcome_unknown: { title: () => 'A run stopped before it finished', action: 'Go to the run',
      lead: 'Its outcome is unknown. It is not in progress and does not restart by itself.' },
    propose: { title: step => `Next step: ${step}`, action: null,
      lead: 'Nothing waits for you here. The assistant proposes this step in the chat.' },
    run: { title: step => `Next step: ${step}`, action: null,
      lead: 'Nothing waits for you here. The assistant runs this step in the chat.' },
    blocked: { title: step => `Next step: ${step}`, action: null,
      lead: 'This step waits for an earlier one. The assistant guides you in the chat.' },
    done: { title: () => 'Every step is done', action: null,
      lead: 'The report and the notebook carry the study. Read them again before you hand them over.' },
    other: { title: () => 'Continue in the chat', action: null, lead: 'The assistant guides the next step in the chat.' },
    // WP-B5: the opening of the final test is a chat act. The panel explains it and points
    // to the chat; it never offers a control that opens it.
    finalTest: {
      await: { title: () => 'Open the final test, in the chat', action: null,
        lead: 'A proposal to open the final test waits for your answer. Give it in the chat, in your own words and with your reason: the final test opens once, and this panel has no control for it.' },
      propose: { title: () => 'Next step: open the final test once', action: null,
        lead: 'When the model and the rule are settled, say in the chat that you open the final test and why. It opens once; nothing is measured on it again.' },
      what: (model, rule) => `It would measure ${model}${rule ? ` with the rule: ${rule.charAt(0).toLowerCase()}${rule.slice(1)}` : ''}, once, on rows nobody has looked at.`,
    },
    proposalSaid: 'The proposal says',
    proposedValue: 'In short',
    whyTitle: 'Why it matters',
    supporting: 'What supports it',
    inChat: 'At this stage of the panel, answer in the chat; the panel shows where the study stands.',
    details: 'Details',
    engineSays: 'The engine\'s instruction to the assistant',
    engineLabel: 'Recorded value',
  };

  // --- limits (keyed by not_yet_defensible id) ----------------------------------------------

  // One vocabulary of severity (WP-A5): blocking, caveat, sealed, context.
  const SEVERITY = {
    unconfirmed_decisions: 'blocking', open_holds: 'blocking', conclusion_outdated: 'blocking',
    inconclusive_without_choice: 'blocking', adopted_rule_not_evaluated: 'blocking', interrupted_executions: 'blocking',
    result_integrity: 'blocking', sources_changed: 'blocking', stale_results: 'blocking', code_changed: 'blocking',
    uncertain_features_included: 'caveat', delegated_decisions: 'caveat', small_validation_partition: 'caveat',
    capacity_exceeds_validation: 'caveat', high_cardinality_grouping: 'caveat', grouped_split_unsupported: 'caveat',
    validation_is_not_independent: 'sealed',
    // WP-B5: the final test (ADR 0006 and its WP-B1 amendment), the scenario's capacity.
    final_test_sealed: 'sealed', changed_after_final_test: 'caveat', final_test_opening_interrupted: 'blocking',
    capacity_assumed_for_exercise: 'caveat', verdict_contradicts_criterion: 'blocking',
    // WP-B6c: keeping the baseline against a criterion met on the final test.
    verdict_keeps_baseline_against_criterion: 'caveat',
    public_data_already_explored: 'context', no_time_or_entity_identifier: 'context', no_causality: 'context',
    workbench_not_tracked: 'context',
  };
  const SEVERITY_ORDER = ['blocking', 'caveat', 'sealed', 'context'];
  const severityLabel = { blocking: 'blocking', caveat: 'caveat', sealed: 'not final', context: 'context' };

  // The panel's own wording of a limit, used when the engine gives no junior text, and for
  // the ids listed under "more" (which carry no text in the summary).
  const limitText = {
    unconfirmed_decisions: 'Some decisions are not confirmed by you yet.',
    open_holds: 'A condition you set is still open.',
    conclusion_outdated: 'The conclusion no longer matches the study; it needs your words again.',
    inconclusive_without_choice: 'The study is inconclusive and no choice is confirmed.',
    adopted_rule_not_evaluated: 'The adopted rule has no current evaluation.',
    interrupted_executions: 'A run has an unknown outcome.',
    result_integrity: 'A stored result failed its integrity check; it is not cited.',
    sources_changed: 'The case or the data changed since the study started; no result is current.',
    stale_results: 'Some results are out of date and are not cited.',
    code_changed: 'The engine code behind some results changed; they are not current.',
    uncertain_features_included: 'Some variables are used although they may not be known at the prediction moment.',
    delegated_decisions: 'Some decisions were left to the assistant\'s default rather than decided by you.',
    small_validation_partition: 'The validation rows are few, so the figures can move a lot.',
    capacity_exceeds_validation: 'A rule selects every validation row, so it says nothing about choosing.',
    high_cardinality_grouping: 'Some rare values were grouped together in a chart.',
    grouped_split_unsupported: 'Related rows may fall on both sides of the split.',
    validation_is_not_independent: 'The validation rows were used to choose, so their figures are not independent evidence.',
    public_data_already_explored: 'The data were published and explored before; its rows are not unseen.',
    no_time_or_entity_identifier: 'The data have no date or entity identifier, so drift and repeated entities cannot be checked.',
    no_causality: 'The study shows associations; it does not measure the effect of an action.',
    workbench_not_tracked: 'Your workbench is not tracked, so nothing in it counts as evidence.',
    // WP-B5.
    final_test_sealed: 'The final test is still sealed: every figure so far comes from the development rows that helped to choose.',
    changed_after_final_test: 'Something changed after the final test was opened, so the final test no longer measures what the study now holds.',
    final_test_opening_interrupted: 'The opening of the final test stopped before its result was recorded; the final test is used up and cannot be opened again.',
    capacity_assumed_for_exercise: 'The share of cases acted on is the teaching scenario\'s assumption, not a figure from a team.',
    verdict_contradicts_criterion: 'The conclusion adopts although the success criterion is not met.',
    // WP-B6c.
    verdict_keeps_baseline_against_criterion: 'The conclusion keeps the baseline although the success criterion is met on the final test; say why.',
  };
  const limitFallback = id => `${cap(String(id || '').replace(/_/g, ' '))}.`;

  // --- since your last session (keyed by digest kind) ----------------------------------------

  const GROUP_OF_KIND = {
    proposed: 'needs', hold_recorded: 'needs', run_failed: 'needs', run_interrupted: 'needs',
    confirmed: 'resolved', withdrawn: 'resolved', hold_resolved: 'resolved', interruption_acknowledged: 'resolved',
    result_added: 'evaluated', result_replaced: 'evaluated', other: 'other',
  };
  const groups = {
    needs: 'needs you', resolved: 'resolved', evaluated: 're-evaluated', deliverables: 'deliverables', other: 'other',
  };
  const GROUP_ORDER = ['needs', 'evaluated', 'resolved', 'deliverables', 'other'];

  const ACTIVITY = {
    split: 'The split', 'eda.target_rate': 'The outcome rate', 'eda.target_summary': 'The target summary',
    'eda.special_values': 'The special-value check', 'eda.rate_by': 'An outcome rate by group',
    'eda.mean_by': 'A target mean by group', 'eda.distribution': 'A distribution', 'fit.baseline': 'The baseline model',
    'fit.logistic': 'The logistic model', 'fit.linear': 'The linear model', 'policy.evaluate': 'The calling-rule evaluation',
    'evaluate.regression': 'The model comparison',
    // WP-A7: the quality check (development rows) and the leakage detector.
    'eda.quality': 'The data quality check', 'eda.single_feature_signal': 'The single-feature signal check',
  };
  ACTIVITY['policy.evaluation'] = ACTIVITY['policy.evaluate'];
  const activity = (a, task) => {
    const key = str(a).split(':')[0];
    return (regression(task) && key.startsWith('policy.') ? 'An evaluation' : ACTIVITY[key]) || 'A result';
  };

  /** One digest item in the panel's words; null keeps the engine text (audience junior). */
  function digestText(item, task, note) {
    const words = note && note.userWords ? ` "${note.userWords}"` : '';
    const name = decisionName(item.decisionId, task);
    const col = item.column ? ` of ${item.column}` : str(item.slot).includes(':') ? ` of ${str(item.slot).split(':')[1]}` : '';
    const act = item.activity || item.slot;
    switch (item.kind) {
      case 'proposed': return `${cap(name)} was proposed.`;
      case 'confirmed': return item.basis === 'delegated_default'
        ? `${cap(name)} was left to the assistant's default.` : `You confirmed ${name} in your own words.`;
      case 'withdrawn': return `The proposal on ${name} was withdrawn.`;
      case 'hold_recorded': return `You put ${name} on hold:${words || ' a condition of yours'}.`;
      case 'hold_resolved': return note && note.resolutionWords
        ? `Your condition on ${name},${words}, was resolved in your words: "${note.resolutionWords}".`
        : `Your condition on ${name} was resolved.`;
      case 'result_added': return `${activity(act, task)}${col} was computed.`;
      case 'result_replaced': return `${activity(act, task)}${col} was computed again.`;
      case 'run_failed': return `${activity(act, task)}${col} failed; nothing was stored.`;
      case 'run_interrupted': return `${activity(act, task)}${col} stopped before it finished.`;
      case 'interruption_acknowledged': return 'You acknowledged a run whose outcome is unknown.';
      default: return null;
    }
  }

  /**
   * The "Decided" line of the recap strip in the panel's words (the engine's junior recap
   * still quotes recorded tokens such as a rule): each confirmed decision and its value.
   */
  function decidedLine(model) {
    const task = model && model.task;
    const plan = Array.isArray(model && model.plan) ? model.plan : [];
    const parts = plan.filter(s => model.decisions && model.decisions[s.id]
      && ['confirmed', 'reconfirm_required'].includes(model.decisions[s.id].status)).map(s => {
      const d = model.decisions[s.id];
      const words = value(s.id, d.value, task) || str(d.value);
      return `${decisionName(s.id, task)}: ${words}${d.status === 'reconfirm_required' ? ' (to confirm again)' : ''}`;
    });
    return `Decided: ${parts.length ? parts.join('; ') : 'nothing yet'}.`;
  }

  // WP-B5: the confirmation modes (ADR 0005), what counts as an answer in each. The mode
  // changes in the chat only; the panel shows it and offers no control.
  const modes = {
    title: 'How your answers are read',
    names: { guided: 'guided', training: 'training', express: 'express' },
    line: name => `This study uses the ${name} mode.`,
    // `finalTest`: the study has the opening of a final test (WP-B1), which also needs a reason.
    rules: (mode, task, finalTest) => {
      const choice = regression(task) ? 'the model choice' : 'the calling rule';
      const opening = finalTest ? 'Opening the final test also needs your reason, and you give it in the chat only.' : null;
      if (mode === 'training') {
        return [
          'An answer says in your own words what the proposal decides, its key points, not only that you agree.',
          'When a key point is missing, the confirmation is stopped and the missing points are named, without words to copy.',
          `For ${choice} and the conclusion, also give your reason with a word such as "because".`,
          opening,
          'Words that keep a variable the proposal leaves out, or the other way round, stop the confirmation.',
        ].filter(Boolean);
      }
      if (mode === 'express') {
        return [
          'An answer is a reply to the open proposal, in your own words, that agrees with it, as in the guided mode.',
          'Once you say so in the chat, the success criterion and the data preparation may be left to the assistant\'s recommended default; they stay marked as not decided by you.',
          `${choice.charAt(0).toUpperCase()}${choice.slice(1)} and the conclusion are always yours, with your reason.`,
          opening,
        ].filter(Boolean);
      }
      return [
        'An answer is a reply to the open proposal, in your own words, that agrees with it.',
        'It is not an answer when it is only "ok", asks a question, or keeps a condition such as "yes, but" or "unless".',
        `For ${choice} and the conclusion, also give your reason: why it fits your situation.`,
        opening,
        'When the assistant raises a point about your reason, you may keep your words; the point is recorded next to them.',
      ].filter(Boolean);
    },
    change: 'The mode changes only in the chat: making it stricter needs no words, making it less strict needs your words naming the mode. This panel cannot change it.',
  };

  // WP-B5: the state of the final test in words (ADR 0006 and its WP-B1 amendment). Counts
  // and revisions are the engine's; the junior's words are quoted as recorded.
  const METHOD = {
    stratified: 'the same share of each outcome',
    quantile_stratified: 'the same share of each range of the target',
    temporal: 'the latest rows in time order',
  };
  const SLOTS = {
    split: 'the split', 'policy.evaluation': 'the calling-rule evaluation', 'evaluate.regression': 'the model comparison',
    'fit.baseline': 'the baseline', 'fit.logistic': 'the logistic model', 'fit.linear': 'the linear model', 'fit.variant': 'the variant',
  };
  /** A decision id or a result slot of `changed_after` in words. */
  function changedName(id, task) {
    const key = str(id);
    if (SLOTS[key]) return regression(task) && key === 'policy.evaluation' ? 'an evaluation' : SLOTS[key];
    return decisionName(key, task);
  }
  /** `sealed`, `opened`, `changed` (opened, then something changed), `interrupted`, `absent`, or null. */
  function finalTestState(ft) {
    if (!ft || !ft.status) return null;
    if (ft.status === 'absent') return 'absent';
    if (ft.status === 'sealed') return 'sealed';
    if (ft.status === 'opened' && !(ft.opening && ft.opening.resultId)) return 'interrupted';
    if (ft.status === 'opened') return ft.postFinalTest ? 'changed' : 'opened';
    return null;
  }
  const finalTestCopy = {
    eyebrow: 'Final test',
    titles: {
      sealed: 'Final test sealed', opened: 'Final test opened once', changed: 'Final test opened, then the study changed',
      interrupted: 'The opening of the final test stopped', absent: 'No final test',
    },
    sealed: (rows, method) => `${rows} rows were set aside when the study was created${METHOD[method] ? `, ${METHOD[method]}` : ''}. Nobody has read them: no chart, fit or evaluation uses them.`,
    sealedNext: 'They open once, in the chat, after the model and the rule are chosen. Until then every figure comes from the development rows that helped to choose, so it is optimistic.',
    opened: rev => `Opened once, at revision ${rev}, in your words:`,
    measured: (model, rule) => `It measured ${model}${rule ? `, ${rule.charAt(0).toLowerCase()}${rule.slice(1)}` : ''}, on rows nobody had looked at.`,
    changed: names => `Changed after the opening: ${names}. The final test measured what the study held then, not what it holds now; it is not opened again.`,
    interrupted: 'The opening started but no result was recorded. The final test is used up: it is not opened a second time.',
    absent: 'This study was created before a final test was set aside, so every figure comes from rows the study has already used.',
    criterion: 'Success criterion on the final test: ',
    trials: n => `Configurations evaluated: ${n}.`,
    trialsWhy: 'Each model or variant tried on the same rows is one more chance for a good figure by luck. The count is a disclosure: the more configurations, the more optimistic the best development figure.',
  };

  HT.copy.junior = {
    decidedLine, sharePercent, modes, finalTest: finalTestCopy, finalTestState, changedName,
    decisionName, why, value, availability, modelName, nextMove,
    SEVERITY, SEVERITY_ORDER, severityLabel, limitText, limitFallback,
    GROUP_OF_KIND, groups, GROUP_ORDER, digestText,
    digestFallback: 'The study changed.',
    deliverablesUpToDate: 'The report and notebook are up to date.',
    deliverablesBehind: 'The report or notebook is behind the study.',
  };
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
