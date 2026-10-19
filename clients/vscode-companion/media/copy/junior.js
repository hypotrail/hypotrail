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
    conclusion: 'The conclusion says what the study supports, and what it does not.',
  })[id] || '';

  // --- readable values ----------------------------------------------------------------------

  const MODEL_NAMES = {
    'fit.logistic': 'the logistic model', 'fit.linear': 'the linear model',
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

  /** A recorded rule (`capacity:N`, `threshold:T`) in words; the numbers are the rule's own. */
  function rule(value, task) {
    const v = str(value);
    let m = v.match(/^capacity:([0-9]+)$/);
    if (m && !regression(task)) return `Call the top ${m[1]} by score`;
    m = v.match(/^threshold:([0-9.]+)$/);
    if (m && !regression(task)) return `Call everyone scored ${m[1]} or more`;
    return null;
  }

  function split(value) {
    const v = parse(value);
    if (!v || typeof v !== 'object') return null;
    const share = typeof v.validation_fraction === 'number' ? HT.format.number(v.validation_fraction, 'pct0') : null;
    if (v.method === 'stratified_random' && share) return `Stratified random split, ${share} of the rows for validation`;
    if (v.method === 'random' && share) return `Random split, ${share} of the rows for validation`;
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

  HT.copy.junior = {
    decidedLine,
    decisionName, why, value, availability, modelName, nextMove,
    SEVERITY, SEVERITY_ORDER, severityLabel, limitText, limitFallback,
    GROUP_OF_KIND, groups, GROUP_ORDER, digestText,
    deliverablesUpToDate: 'The report and notebook are up to date.',
    deliverablesBehind: 'The report or notebook is behind the study.',
  };
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
