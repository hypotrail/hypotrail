// PageModel: where each part of a SummaryModel goes on the one page (ADR 0004 decision 13;
// COMPANION-ADVANCED §4, §6, §9). A pure function, shared by the extension's tests (Node)
// and the webview (lib/html.js inlines this file; the webview reads `Hypotrail.pageModel`):
//
//   toPageModel(summaryModel, {stage, reviewer, lang, learningLayer}) -> {
//     header, progress, current, todo, since, now, waiting, path, tools, anchors }
//
// It decides placement only: which block holds what, which folds start open, which anchors
// exist. Every fact it places is the engine's (OP-2): the defensibility pill's kind and
// items, the headlines, the criterion per configuration, the ledger counts, the automation
// and its review queue, a result's channel. When a P1 key is absent (an older engine) the
// part that needs it is null and the block shows its fallback (HON-9); nothing is derived
// in its place. The words are the panel's copy (media/copy*/page.js) or the engine's texts
// in the panel language, never built here.
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else {
    root.Hypotrail = root.Hypotrail || {};
    root.Hypotrail.pageModel = api;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, () => {
  'use strict';
  const STAGES = ['v0', 'v1', 'v2', 'v3'];
  const LANGS = ['en', 'fr'];
  const DRAWERS = ['data', 'whatif', 'notions', 'deliverables'];
  const TODO_KINDS = ['execution', 'sources', 'integrity', 'deliverables', 'checks'];
  // The step of a result (CLI-CONTRACT §17.1.1, `companion_env.step_of`): the plan step whose
  // activities list the activity (state.STEPS, REGRESSION_STEPS and the B1/L5 steps), else an
  // EDA chart that reads no target under `structural_eda`, any other under `train_eda`, a fit
  // or a diagnostic under `models`. The digest names no step per result, so the panel keeps
  // this table in step with the engine's (the integrator's `results.<slot>.step` would replace it).
  const STEP_OF_ACTIVITY = {
    split: 'split', 'eda.quality': 'structural_eda', 'eda.target_rate': 'train_eda', 'eda.target_summary': 'train_eda',
    'eda.special_values': 'train_eda', 'fit.baseline': 'models', 'fit.logistic': 'models', 'fit.linear': 'models',
    'fit.variant': 'model_variant', 'policy.evaluation': 'policy', 'evaluate.regression': 'model_choice',
    'final_test.evaluation': 'final_test', 'diag.final_test': 'final_test',
  };
  // EDA charts that read no target (a feature's distribution, the predictor correlation).
  const STRUCTURAL_EDA = ['eda.distribution', 'eda.correlation'];
  // The results whose figures a step's comparison shows (its Now card, its Waiting card).
  const FIGURE_ACTIVITIES = {
    model_choice: ['evaluate.regression', 'fit.baseline', 'fit.linear', 'fit.variant'],
    policy: ['policy.evaluation', 'fit.baseline', 'fit.logistic', 'fit.variant'],
    model_variant: ['fit.variant', 'evaluate.regression', 'policy.evaluation'],
    final_test: ['final_test.evaluation'],
  };
  // The bases that are the junior's own words (ADR 0005), for the end's "Your path" count.
  const OWN_BASES = ['endorsed', 'restated', 'explicit'];

  const arr = x => (Array.isArray(x) ? x : []);
  const obj = x => (x && typeof x === 'object' && !Array.isArray(x) ? x : {});
  const rank = s => STAGES.indexOf(s);
  const atLeast = (stage, wanted) => rank(stage) >= rank(wanted);
  const activityOf = slot => String(slot || '').split(':')[0];

  /** The plan step a result slot is filed under (§17.1.1), or null when the plan has none. */
  function stepOf(slot, planIds) {
    const activity = activityOf(slot);
    const has = id => planIds.includes(id);
    const direct = STEP_OF_ACTIVITY[activity];
    if (direct && has(direct)) return direct;
    if (activity.startsWith('eda.')) {
      if (STRUCTURAL_EDA.includes(activity) && has('structural_eda')) return 'structural_eda';
      if (has('train_eda')) return 'train_eda';
    }
    if ((activity.startsWith('fit.') || activity.startsWith('diag.')) && has('models')) return 'models';
    if (activity === 'evaluate.regression' && has('models')) return 'models';
    return null;
  }

  /**
   * An engine text of the panel language from `texts.<lang>.<key>[.<id>]`: {text, lang}, the
   * other language's text (marked by the view) when only that one exists, or null.
   */
  function textOf(texts, lang, key, id) {
    const order = [lang, ...LANGS.filter(l => l !== lang)];
    for (const l of order) {
      const t = obj(obj(texts)[l]);
      const v = id === undefined ? t[key] : obj(t[key])[id];
      if (typeof v === 'string' && v.trim()) return { text: v, lang: l };
    }
    return null;
  }

  /** The options of `texts.<lang>.options` in the chat's order: {items: [{id, label}], lang}. */
  function optionsOf(texts, lang) {
    for (const l of [lang, ...LANGS.filter(x => x !== lang)]) {
      const items = arr(obj(obj(texts)[l]).options);
      if (items.length) return { items: items.map(o => ({ id: o.id, label: o.label })), lang: l };
    }
    return { items: [], lang };
  }

  /**
   * The step that waits for the junior (§A.1.2, blocker-aware): during a review, the decision
   * under review; the decision of the next action when it waits for words; else the first step
   * awaiting the junior; else the engine's current step. Null at `done`.
   */
  function currentStepId(s) {
    const plan = arr(s.plan);
    const next = obj(s.nextAction);
    if (next.kind === 'done') return null;
    const inPlan = id => plan.some(p => p.id === id);
    if (next.decision && inPlan(next.decision) && ['await_user_words', 'reconfirm', 'propose', 'resolve_hold'].includes(next.kind)) {
      return next.decision;
    }
    if (next.step && inPlan(next.step)) return next.step;
    const waiting = plan.find(p => p.status === 'awaiting_confirmation' || p.status === 'needs_reconfirmation');
    if (waiting) return waiting.id;
    return s.currentStep ? s.currentStep.id : null;
  }

  /** {slot: {...result, slot, step}} of the summary's results, filed by step. */
  // The reading order of the exploration's figures inside their step (the EDA model's ORDER,
  // lib/models/eda.js): the target first, then special values, the single-feature signal, the
  // predictor matrix, by-column figures, distributions, the quality check; by column inside.
  const EDA_ORDER = { 'eda.target_rate': 0, 'eda.target_summary': 0, 'eda.special_values': 1, 'eda.single_feature_signal': 2,
    'eda.correlation': 2.5, 'eda.rate_by': 3, 'eda.mean_by': 3, 'eda.distribution': 4, 'eda.quality': 5 };

  function resultsByStep(s, planIds) {
    const out = {};
    for (const [slot, r] of Object.entries(obj(s.results))) {
      const step = stepOf(slot, planIds);
      if (!step) continue;
      (out[step] = out[step] || []).push({ slot, step, resultId: r.resultId, current: r.current === true && r.integrity !== 'failed'
        && (r.integrity === null || r.integrity === 'ok'), staleReason: r.staleReason || null, channel: r.channel || null,
      integrity: r.integrity || null });
    }
    const rank = slot => { const a = slot.split(':')[0]; return a in EDA_ORDER ? EDA_ORDER[a] : 10; };
    for (const list of Object.values(out)) {
      list.sort((a, b) => (rank(a.slot) - rank(b.slot)) || (rank(a.slot) < 10 ? a.slot.localeCompare(b.slot, 'en') : 0));
    }
    return out;
  }

  // --- the header -------------------------------------------------------------------------------

  function sealOf(s) {
    const ft = s.finalTest;
    if (!ft || !ft.status) return null;
    const demo = arr(obj(s.notYetDefensible).top).some(i => i.id === 'final_test_opened_automatically')
      || (s.automation && s.automation.variant === 'full_demo' && ft.status === 'opened');
    const kind = ft.status === 'opened' ? (ft.postFinalTest ? 'changed' : 'opened') : ft.status === 'sealed' ? 'sealed'
      : ft.status === 'absent' ? 'absent' : null;
    if (!kind) return null;
    return { kind, rows: ft.rows, changedAfter: arr(ft.changedAfter), openingTime: ft.opening ? ft.opening.time || null : null,
      demo: Boolean(demo) };
  }

  /** The pill of PG-6: the engine's `defensibility`, else the neutral fallback (HON-5). */
  function defensibilityOf(s) {
    if (s.defensibility) {
      return { kind: s.defensibility.kind, count: s.defensibility.count, items: arr(s.defensibility.items), fallback: false };
    }
    const nyd = obj(s.notYetDefensible);
    const ids = [...arr(nyd.top).map(i => i.id), ...arr(nyd.more)];
    return { kind: 'fallback', count: ids.length, items: ids.map(id => ({ id, severity: null })), fallback: true };
  }

  /** PG-7: active, a demonstration (for good), or ended with a review still open; else null. */
  function automationOf(s) {
    const a = s.automation;
    if (!a) return null;
    if (a.variant === 'full_demo') return { state: 'demo', variant: a.variant };
    if (a.active) return { state: 'active', variant: a.variant };
    const pending = s.reviewQueue && arr(s.reviewQueue.items).length > 0;
    return pending ? { state: 'ended', variant: a.variant } : null;
  }

  // --- progress ---------------------------------------------------------------------------------

  /** The moments in plan order; a step no moment lists joins the moment of the step before it. */
  function momentsOf(s) {
    const plan = arr(s.plan);
    const moments = arr(s.moments).map(m => ({ id: m.id, title: m.title, steps: [] }));
    const owner = {};
    for (const m of arr(s.moments)) for (const id of arr(m.steps)) owner[id] = m.id;
    let last = moments.length ? moments[0].id : 'all';
    if (!moments.length) moments.push({ id: 'all', title: '', steps: [] });
    for (const step of plan) {
      const id = owner[step.id] || last;
      last = id;
      const m = moments.find(x => x.id === id) || moments[moments.length - 1];
      m.steps.push(step.id);
    }
    return moments.filter(m => m.steps.length);
  }

  function inReview(s) {
    const next = obj(s.nextAction);
    return next.review === true || Boolean(s.reviewQueue && arr(s.reviewQueue.items).length && next.kind !== 'done'
      && s.automation && !s.automation.active);
  }

  function progressOf(s, moments, current) {
    const plan = arr(s.plan);
    const next = obj(s.nextAction);
    if (inReview(s) && s.reviewQueue) {
      const q = s.reviewQueue;
      const total = Math.max(q.total, 0);
      const done = Math.min(q.done, total);
      return { mode: 'review', groups: [{ moment: 'review', segments: Array.from({ length: total }, (_, i) => ({
        step: null, state: i < done ? 'done' : i === done ? 'current' : 'auto' })) }], k: Math.min(done + 1, total), n: total };
    }
    const groups = moments.map(m => ({ moment: m.id, title: m.title, segments: m.steps.map(id => {
      const step = plan.find(p => p.id === id) || {};
      return { step: id, state: id === current ? 'current' : step.status === 'done' ? 'done' : 'todo' };
    }) }));
    if (next.kind === 'done' || !current) return { mode: 'done', groups, index: plan.length, total: plan.length };
    const index = plan.findIndex(p => p.id === current) + 1;
    const moment = moments.find(m => m.steps.includes(current));
    return { mode: 'steps', groups, index, total: plan.length, moment: moment ? moment.id : null,
      momentTitle: moment ? moment.title : '' };
  }

  // --- To handle --------------------------------------------------------------------------------

  function todoOf(s, stage) {
    const items = [];
    const ex = obj(s.executions);
    const runs = [...arr(ex.interrupted).map(e => ({ ...e, state: 'interrupted' })), ...arr(ex.suspected).map(e => ({ ...e, state: 'suspected' })),
      ...arr(ex.late).map(e => ({ ...e, state: 'late' }))];
    if (runs.length) items.push({ kind: 'execution', anchor: 'todo:execution', runs });
    const top = arr(obj(s.notYetDefensible).top);
    const sources = top.find(i => i.id === 'sources_changed');
    if (sources) items.push({ kind: 'sources', anchor: 'todo:sources', limit: sources });
    const integrity = top.find(i => i.id === 'result_integrity');
    if (integrity) items.push({ kind: 'integrity', anchor: 'todo:integrity', limit: integrity });
    const generated = arr(s.artifacts).filter(a => (a.name === 'report' || a.name === 'notebook') && a.status !== 'ok');
    const notRendered = s.artifactsStatus === 'not_rendered';
    if (generated.length || notRendered) {
      items.push({ kind: 'deliverables', anchor: 'todo:deliverables', artifacts: generated, notRendered,
        regenerate: atLeast(stage, 'v1') && s.regenerate === true });
    }
    return items;
  }

  // --- Now --------------------------------------------------------------------------------------

  function nowKind(s, step) {
    const next = obj(s.nextAction);
    const plan = arr(s.plan);
    if (next.kind === 'outcome_unknown' || next.kind === 'acknowledge_interruption') return 'execution';
    if (next.review) return 'review';
    if (next.kind === 'show_data_card') return 'data_card';
    if (next.kind === 'done') return 'done';
    if (next.kind === 'reconfirm') return 'reopened';
    if (next.kind === 'resolve_hold') return 'hold';
    if (next.kind === 'run') return 'run';
    if (next.kind === 'blocked') return 'blocked';
    if (next.kind === 'propose' && arr(next.choiceOptions).length) return 'choice';
    // A new proposal on a decision already made (a change the chat proposes) waits for words:
    // it is a proposal, not a reopened decision (that one is `reconfirm`).
    if (next.kind === 'await_user_words') return 'proposal';
    const open = arr(s.proposals).find(p => p.decisionId === step);
    const done = plan.some(p => p.id === step && p.status === 'done');
    if (open && done) return 'reopened';
    if (open) return 'proposal';
    return 'question';
  }

  /** The next plan step not done after `step`, or null. */
  function nextStepAfter(s, step) {
    const plan = arr(s.plan);
    const i = plan.findIndex(p => p.id === step);
    const later = plan.slice(i + 1).find(p => p.status !== 'done');
    return later ? { id: later.id, title: later.title } : null;
  }

  function limitOf(s, kind, lang) {
    if (kind === 'data_card') return { kind: 'step1' };
    if (kind === 'review') return { kind: 'review' };
    const t = obj(obj(s.texts)[lang]);
    const lines = arr(t.recap).length ? arr(t.recap) : arr(s.recapJunior);
    const line = lines.length >= 5 ? lines[4] : null;
    if (!line) return null;
    const text = String(line).replace(/^[^:：]{1,20}\s?[:：]\s*/, '');
    return text ? { kind: 'engine', text, lang: arr(t.recap).length ? lang : (s.language || 'en') } : null;
  }

  function nowOf(s, opts, current, results) {
    const { stage, lang } = opts;
    const next = obj(s.nextAction);
    const plan = arr(s.plan);
    const step = next.kind === 'done' ? null : (next.decision || next.step || current);
    const kind = nowKind(s, step);
    const stepRow = plan.find(p => p.id === step) || null;
    const proposal = arr(s.proposals).find(p => (next.proposalId && p.proposalId === next.proposalId) || p.decisionId === step) || null;
    const question = kind === 'run' || kind === 'blocked' || kind === 'execution' ? null : textOf(s.texts, lang, 'question');
    let options = question ? optionsOf(s.texts, lang) : { items: [], lang };
    // HON-9: an engine before P1 names a choice's options in `next_action.choice_options`
    // (R16), in the study language.
    if (!options.items.length && kind !== 'run' && kind !== 'blocked' && kind !== 'execution' && arr(next.choiceOptions).length) {
      options = { items: next.choiceOptions.map(o => ({ id: o.id, label: o.label })), lang: s.language || 'en' };
    }
    const note = question ? textOf(s.texts, lang, 'options_note') : null;
    const reopenedFirst = kind === 'reopened';
    const hasFigureStage = atLeast(stage, 'v2');
    const effects = atLeast(stage, 'v1') && (Boolean(proposal) || kind === 'review' || kind === 'reopened')
      ? { proposalId: proposal ? proposal.proposalId : null, decisionId: step } : null;
    const criterion = hasFigureStage && (kind === 'choice' || kind === 'done' || (kind === 'proposal' && ['model_choice', 'policy'].includes(step)))
      ? (s.criterionConfigurations ? 'configurations' : s.criterion ? 'single' : null) : null;
    const contingent = proposal && proposal.dataContingent === true ? textOf(s.texts, lang, 'data_contingent', proposal.proposalId) : null;
    const decision = step ? obj(s.decisions)[step] || null : null;
    const reviewItem = kind === 'review' && s.reviewQueue ? arr(s.reviewQueue.items).find(i => i.decisionId === step) || null : null;
    const figure = kind === 'choice' || (kind === 'proposal' && ['model_choice', 'policy'].includes(step))
      ? { step, slots: arr(results[step]).concat(arr(results.models)).filter(r => arr(FIGURE_ACTIVITIES[step]).includes(activityOf(r.slot))) }
      : null;
    return {
      kind, step, title: stepRow ? stepRow.title : null, first: reopenedFirst,
      question, options: options.items, optionsLang: options.lang, optionsNote: note,
      proposal, decision, reviewItem, contingent, effects, criterion, figure,
      choiceOptions: arr(next.choiceOptions),
      hold: kind === 'hold' ? arr(s.holds).filter(h => h.decisionId === step) : [],
      digest: kind === 'review' ? textOf(s.texts, lang, 'junior_digest') : null,
      nextMessage: textOf(s.texts, lang, 'next_action') || (next.juniorMessage ? { text: next.juniorMessage, lang: s.language || 'en' } : null),
      activity: next.activity || null, requires: stepRow && stepRow.after ? stepRow.after : null,
      limit: kind === 'done' || kind === 'execution' ? null : limitOf(s, kind, lang),
      next: kind === 'done' ? null : nextStepAfter(s, step),
      afterStudy: kind === 'done' ? next.afterStudy || null : null,
      // NOW-7: the opening of the final test is answered in the chat, with no control.
      finalTest: step === 'final_test',
      dataCard: kind === 'data_card' ? (hasFigureStage ? 'card' : 'stage_line') : null,
    };
  }

  // --- Waiting cards ----------------------------------------------------------------------------

  function waitingOf(s, now, results) {
    if (!now.first) return [];
    const plan = arr(s.plan);
    const i = plan.findIndex(p => p.id === now.step);
    const others = arr(s.proposals).filter(p => p.decisionId !== now.step).map(p => p.decisionId);
    const later = plan.slice(i + 1).find(p => p.status !== 'done');
    const ids = [...new Set([...others, ...(later ? [later.id] : [])])];
    const ex = obj(s.executions);
    const stopped = [...arr(ex.interrupted), ...arr(ex.suspected)];
    return ids.map(id => {
      const row = plan.find(p => p.id === id) || { id, title: id };
      const wanted = arr(FIGURE_ACTIVITIES[id]);
      const slots = Object.values(results).flat().filter(r => wanted.includes(activityOf(r.slot)));
      const stale = slots.filter(r => !r.current);
      const reasons = [...new Set(stale.map(r => r.staleReason).filter(Boolean))];
      const unknown = [...new Set(stopped.map(e => e.activity).filter(a => wanted.includes(a)))];
      return { step: id, title: row.title, stale: stale.length > 0 || unknown.length > 0, reasons, unknown };
    });
  }

  // --- the path ---------------------------------------------------------------------------------

  /** The state of one step line (PATH-3) and its flags. */
  function stepLine(step, s, ctx) {
    const { current, results, review, now } = ctx;
    const d = obj(s.decisions)[step.id] || null;
    const basis = d ? d.basis : null;
    const open = arr(s.proposals).some(p => p.decisionId === step.id);
    const held = arr(s.holds).some(h => h.decisionId === step.id);
    const res = arr(results[step.id]);
    const staleRes = res.filter(r => !r.current);
    const flags = [];
    if (basis === 'automatic' && step.status === 'done') flags.push('auto');
    if (!d && step.status === 'done' && res.length && res.every(r => r.channel === 'cli')) flags.push('computed');
    if (step.status === 'needs_reconfirmation' || (d && d.status === 'reconfirm_required') || (step.status === 'done' && open)) flags.push('again');
    if (staleRes.length) flags.push('stale');
    if (held) flags.push('held');
    if (basis === 'delegated_default') flags.push('delegated');
    let state;
    if (step.id === current && !(review && step.id !== now.step)) state = 'current';
    else if (flags.includes('again')) state = 'again';
    else if (flags.includes('held')) state = 'held';
    else if (flags.includes('auto')) state = 'auto';
    else if (flags.includes('computed')) state = 'computed';
    else if (flags.includes('stale')) state = 'stale';
    else if (flags.includes('delegated')) state = 'delegated';
    else if (step.status === 'done') state = 'done';
    else state = 'later';
    const headline = obj(s.headlines)[step.id] || null;
    return {
      id: step.id, title: step.title, status: step.status, state, flags,
      headline: headline ? { ...headline, text: textOf(s.texts, ctx.lang, 'headlines', step.id) } : null,
      decision: d ? { status: d.status, value: d.value, basis, userWords: d.userWords, reason: d.reason,
        delegationScope: d.delegationScope } : null,
      results: res,
      // A step's detail (PATH-5): a done or flagged step line is a fold, and so is any step
      // that holds results (a chart computed while its step is still open stays reachable).
      detail: res.length > 0 || (state !== 'later' && (state !== 'current' || step.status === 'done')),
    };
  }

  function pathOf(s, opts, moments, current, results, now) {
    const review = inReview(s);
    const plan = arr(s.plan);
    const ctx = { current: review ? now.step : current, results, review, now, lang: opts.lang };
    const lines = Object.fromEntries(plan.map(step => [step.id, stepLine(step, s, ctx)]));
    const phases = moments.map(m => {
      const steps = m.steps.map(id => lines[id]).filter(Boolean);
      const flagged = steps.filter(x => x.flags.length > 0 && x.state !== 'done');
      const hasCurrent = steps.some(x => x.state === 'current');
      const allDone = steps.every(x => x.status === 'done');
      const started = steps.some(x => x.status === 'done' || x.state === 'current' || x.flags.length);
      const kind = allDone && !flagged.length && !hasCurrent ? 'done' : !started ? 'later' : 'open';
      const counts = {};
      for (const x of flagged) for (const f of x.flags) counts[f] = (counts[f] || 0) + 1;
      return { moment: m.id, title: m.title, kind, open: kind === 'open', steps, counts, current: hasCurrent };
    });
    return { ledger: s.ledger || null, sampleNote: textOf(s.texts, opts.lang, 'sample_note'), phases };
  }

  // --- tools ------------------------------------------------------------------------------------

  function toolsOf(s, opts) {
    const { stage, learningLayer } = opts;
    const evaluated = Object.entries(obj(s.results)).some(([slot, r]) =>
      ['policy.evaluation', 'evaluate.regression'].includes(activityOf(slot)) && r.current === true);
    const out = [];
    if (atLeast(stage, 'v2')) out.push({ id: 'data', stage: 'v2' });
    if (atLeast(stage, 'v2') && evaluated) out.push({ id: 'whatif', stage: 'v2' });
    if (atLeast(stage, 'v3') && learningLayer !== false) out.push({ id: 'notions', stage: 'v3' });
    out.push({ id: 'deliverables', stage: 'v0' });
    return out;
  }

  /** "Your path" at the end (§6.5.2 `done`): counts of the engine's lists only. */
  function journeyOf(s) {
    const decisions = Object.values(obj(s.decisions));
    return {
      steps: arr(s.plan).length,
      ownWords: decisions.filter(d => d.status === 'confirmed' && OWN_BASES.includes(d.basis)).length,
      looks: s.ledger ? s.ledger.targetLooks.total : null,
      openings: s.ledger && s.ledger.finalTest ? s.ledger.finalTest.openings : null,
    };
  }

  function toPageModel(summary, options = {}) {
    const s = summary || {};
    const opts = { stage: STAGES.includes(options.stage) ? options.stage : 'v0', reviewer: options.reviewer === true,
      lang: LANGS.includes(options.lang) ? options.lang : 'en', learningLayer: options.learningLayer !== false };
    const planIds = arr(s.plan).map(p => p.id);
    const moments = momentsOf(s);
    const current = currentStepId(s);
    const results = resultsByStep(s, planIds);
    const now = nowOf(s, opts, current, results);
    const path = pathOf(s, opts, moments, current, results, now);
    const todo = todoOf(s, opts.stage);
    const tools = toolsOf(s, opts);
    const anchors = ['now', ...todo.map(t => t.anchor), 'path', ...planIds.map(id => `path:${id}`)];
    if (atLeast(opts.stage, 'v2')) {
      for (const list of Object.values(results)) for (const r of list) anchors.push(`path:${r.step}/${r.slot}`);
    }
    for (const t of tools) anchors.push(`tools:${t.id}`);
    return {
      stage: opts.stage, lang: opts.lang, reviewer: opts.reviewer,
      header: { study: s.study || '', seal: sealOf(s), defensibility: defensibilityOf(s), automation: automationOf(s),
        reviewer: opts.reviewer, skew: s.panelContract !== null && s.panelContract !== undefined ? s.panelContract : null },
      progress: progressOf(s, moments, now.kind === 'review' ? now.step : current),
      current, todo,
      since: atLeast(opts.stage, 'v1') && Boolean(s.digest && arr(s.digest.items).length),
      now, waiting: waitingOf(s, now, results), path, tools, journey: journeyOf(s), anchors,
    };
  }

  /** The anchor of a result id (§4.3): `path:<step>/<slot>` from the summary, else `path`. */
  function anchorOfResult(summary, resultId) {
    const s = summary || {};
    const planIds = arr(s.plan).map(p => p.id);
    for (const [slot, r] of Object.entries(obj(s.results))) {
      if (r && r.resultId === resultId) {
        const step = stepOf(slot, planIds);
        return step ? `path:${step}/${slot}` : 'path';
      }
    }
    for (const [step, h] of Object.entries(obj(s.headlines))) if (arr(h.results).includes(resultId)) return `path:${step}`;
    return 'path';
  }

  /** The anchor grammar of CLI-CONTRACT §17.1.1 (`companion_env.ANCHOR_RE`). */
  const ANCHOR_RE = /^(now|todo:(execution|deliverables|checks|sources|integrity)|path|path:[a-z_]+(\/[A-Za-z0-9_.:-]+)?|tools:(data|whatif|notions|deliverables))$/;

  return { toPageModel, stepOf, currentStepId, anchorOfResult, textOf, ANCHOR_RE, DRAWERS, TODO_KINDS, STEP_OF_ACTIVITY,
    FIGURE_ACTIVITIES, STAGES };
});
