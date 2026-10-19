// Overview view (COMPANION-ADVANCED §6.1; WP-U1, restructured by WP-A5). Mockups:
// docs/design/companion-v0.2-mockups/overview.html and deliverables.html.
//
// Every stage, v0 included, opens on the same first block: "Your next move" (§6.1.0), the
// one thing that waits for the junior, why it matters, what supports it, and a link to
// where it is answered. Then:
//
//   stage v0   the journey (the plan, blocker-aware), where we are (goal, decisions in
//              words), what you cannot claim yet (limits by severity, once), deliverables
//              (Open file, Open in Marimo)
//   stage v1+  the journey as the study map (moments), since your last session (grouped),
//              what you cannot claim yet, where we are, deliverables (Regenerate W5,
//              checks), and Health only when something is wrong (executions with the typed
//              acknowledgement W6, alerts)
//
// Two-layer copy (§15.1): the primary sentences are the panel's own (media/copy/junior.js,
// keyed by kind and id) or the engine's junior variants; an engine text written for the
// agent appears only under a "Details" disclosure. Study text is always set as text
// (INV-9). The only words field is ctx.wordsArea (INV-5). No control restarts a run (HE-2).
(function (HT) {
  'use strict';
  const el = HT.el;
  const str = x => (typeof x === 'string' ? x : '');
  const arr = x => (Array.isArray(x) ? x : []);
  const copy = () => HT.copy.overview;
  const J = () => HT.copy.junior;
  const RENDER_TARGET = 'render';
  const MAP_STATUSES = ['done', 'awaiting_confirmation', 'needs_reconfirmation', 'ready', 'blocked', 'reopened'];
  const MAX_DIGEST = 4;
  const DECISIONS = ['prediction_time', 'feature_availability', 'split', 'policy', 'model_choice', 'conclusion'];

  // View-local, not persisted: the chosen digest boundary, the checks expansion, the reads
  // asked per version, and the executions acknowledged from this panel.
  const local = { since: null, checksOpen: false, asked: {}, acknowledged: [] };

  const taskOf = (model, ctx) => model.task || ctx.task || null;

  function section(id, title, children, attrs) {
    return el('section', { 'aria-labelledby': id, className: 'ov-section', ...(attrs || {}) },
      [el('h2', { id, text: title }), ...children]);
  }

  /** Ask once per (view, version, variant) for a data view (CR.1: revision, currency, epoch). */
  function askOnce(ctx, view, extra) {
    const key = `${view}@${ctx.version()}@${extra ? JSON.stringify(extra) : ''}`;
    if (local.asked[key]) return;
    local.asked[key] = true;
    ctx.load(view, extra);
  }

  /** A "Details" disclosure holding engine texts as they are (layer 2 of §15.1). */
  function details(label, rows, attrs) {
    const items = rows.filter(r => r && str(r.text));
    if (!items.length) return null;
    return el('details', { className: 'ht-details', ...(attrs || {}) }, [
      el('summary', { text: label }),
      el('ul', {}, items.map(r => el('li', { 'data-engine-text': r.id || '' }, [
        r.label ? el('span', { className: 'muted', text: `${r.label}: ` }) : null,
        el('span', { text: str(r.text) })]))),
    ]);
  }

  // --- the decision in words ----------------------------------------------------------------

  /** A decision value as the junior reads it; the recorded value in its hover (title). */
  function valueNode(decisionId, raw, task, attrs) {
    const readable = J().value(decisionId, raw, task);
    const text = readable || str(raw);
    return el('span', { className: readable ? 'ht-value-words' : 'ht-value-raw', title: readable && str(raw) ? `${J().nextMove.engineLabel}: ${str(raw)}` : null,
      'data-value-raw': str(raw), ...(attrs || {}), text });
  }

  // --- the step that waits for the junior ----------------------------------------------------

  /**
   * The step the journey marks as current: the decision of the next action when it waits
   * for the junior (an open proposal, a reconfirmation), else the engine's current step.
   */
  function currentStepId(model) {
    const next = model.nextAction || {};
    if ((next.kind === 'await_user_words' || next.kind === 'reconfirm') && next.decision
      && arr(model.plan).some(s => s.id === next.decision)) return next.decision;
    const waiting = arr(model.plan).find(s => s.status === 'awaiting_confirmation' || s.status === 'needs_reconfirmation');
    if (waiting) return waiting.id;
    return model.currentStep ? model.currentStep.id : null;
  }

  /** A step whose decision is done but has a new open proposal is reopened (visibly). */
  function displayStatus(step, model) {
    if (step.status === 'done' && arr(model.proposals).some(p => p.decisionId === step.id)) return 'reopened';
    return MAP_STATUSES.includes(step.status) ? step.status : 'ready';
  }

  // --- Your next move (§6.1.0) ---------------------------------------------------------------

  function supporting(model, ctx, proposal) {
    if (!proposal || !ctx.atLeast('v2')) return null;
    const got = ctx.data('evidence');
    ctx.want('evidence');
    const m = got && got.model;
    const u = m && m.uncertainty;
    if (!u) return null;
    const c = copy().hero;
    const pct = x => ctx.format.number(x, 'pct1');
    const cite = (text, path, value) => ctx.components.cited(text, { resultId: u.resultId, path, value });
    if (u.kind === 'policy' && proposal.decisionId === 'policy') {
      const rule = arr(u.rules).find(r => r && r.rule === proposal.value);
      const metric = rule && arr(rule.metrics).find(x => x && x.metric === 'precision');
      const model0 = metric && arr(metric.models).find(x => x && x.fit !== u.reference && typeof x.point === 'number');
      const base = metric && arr(metric.models).find(x => x && x.fit === u.reference && typeof x.point === 'number');
      if (!model0) return null;
      return el('p', { className: 'ov-hero-support', 'data-hero-support': 'policy' }, [
        c.successShare, cite(pct(model0.point), model0.path, model0.point),
        typeof model0.low === 'number' && typeof model0.high === 'number'
          ? [c.interval(u.bootstrap && typeof u.bootstrap.level === 'number' ? ctx.format.number(u.bootstrap.level, 'pct0') : null), cite(pct(model0.low), model0.path, model0.low), c.to, cite(pct(model0.high), model0.path, model0.high), c.close] : null,
        base ? [c.againstBaseline, cite(pct(base.point), base.path, base.point), '.'] : '.',
      ]);
    }
    if (u.kind === 'regression' && proposal.decisionId === 'model_choice') {
      const metric = arr(u.metrics).find(x => x && x.metric === 'mae');
      const chosen = metric && arr(metric.models).find(x => x && x.fit === proposal.value && typeof x.point === 'number');
      const other = metric && arr(metric.models).find(x => x && x.fit !== proposal.value && typeof x.point === 'number');
      if (!chosen) return null;
      const f2 = x => ctx.format.number(x, 'f2');
      const unit = u.unit ? ` ${u.unit}` : '';
      return el('p', { className: 'ov-hero-support', 'data-hero-support': 'model_choice' }, [
        c.averageError(J().modelName(chosen.fit, 'regression')), cite(`${f2(chosen.point)}${unit}`, chosen.path, chosen.point),
        other ? [c.againstOther(J().modelName(other.fit, 'regression')), cite(`${f2(other.point)}${unit}`, other.path, other.point), '.'] : '.',
      ]);
    }
    return null;
  }

  function hero(model, ctx) {
    const c = copy().hero;
    const N = J().nextMove;
    const task = taskOf(model, ctx);
    const next = model.nextAction || {};
    const kind = N[next.kind] ? next.kind : 'other';
    const spec = N[kind];
    const step = arr(model.plan).find(s => s.id === (next.decision || next.step));
    const pause = step && Number.isInteger(step.pause) ? step.pause : null;
    const proposal = next.kind === 'await_user_words'
      ? arr(model.proposals).find(p => p.proposalId === next.proposalId) || arr(model.proposals)[0] || null : null;
    const decision = next.decision || (proposal && proposal.decisionId) || null;
    const name = decision ? J().decisionName(decision, task) : '';
    const title = kind === 'await_user_words' || kind === 'reconfirm' ? spec.title(name)
      : kind === 'propose' || kind === 'run' || kind === 'blocked' ? spec.title(step ? str(step.title) : c.nextStep) : spec.title();
    const eyebrow = [N.eyebrow, pause ? c.pause(pause, task) : null].filter(Boolean).join(' · ');
    const children = [
      el('p', { className: 'ov-eyebrow', 'data-hero-eyebrow': true, text: eyebrow }),
      el('h2', { id: 'ov-hero-title', 'data-hero-title': kind, text: title }),
      el('p', { className: 'ov-hero-lead', 'data-hero-lead': true, text: spec.lead }),
    ];
    if (proposal) {
      children.push(el('blockquote', { className: 'ov-hero-quote', 'data-hero-restatement': proposal.proposalId, text: proposal.restatement }));
      const readable = J().value(proposal.decisionId, proposal.value, task);
      if (readable) {
        children.push(el('p', { className: 'ov-hero-short' }, [el('span', { className: 'muted', text: `${N.proposedValue}: ` }),
          valueNode(proposal.decisionId, proposal.value, task, { 'data-hero-value': true })]));
      }
    }
    if (decision && J().why(decision, task)) {
      children.push(el('p', { className: 'ov-hero-why', 'data-hero-why': decision }, [
        el('strong', { text: `${N.whyTitle}. ` }), J().why(decision, task)]));
    }
    if (kind === 'reconfirm' && model.decisions && model.decisions[decision] && model.decisions[decision].reason) {
      children.push(el('p', { className: 'muted', 'data-hero-reason': true, text: c.becauseChanged }));
    }
    const support = supporting(model, ctx, proposal);
    if (support) children.push(support);
    // The action: where the junior answers.
    const actions = [];
    const target = kind === 'await_user_words' && proposal ? { tab: 'decisions', kind: 'proposal', id: proposal.proposalId }
      : kind === 'reconfirm' && decision ? { tab: 'decisions', kind: 'decision', id: decision }
        : (kind === 'outcome_unknown' || kind === 'acknowledge_interruption') && next.executionId && ctx.atLeast('v1')
          ? { tab: 'overview', kind: 'execution', id: next.executionId } : null;
    if (target && spec.action) {
      actions.push(el('button', { type: 'button', className: 'ov-hero-action', 'data-hero-action': `${target.kind}:${target.id}`,
        text: spec.action, onclick: () => ctx.navigate(target) }));
    } else if (kind === 'outcome_unknown' || kind === 'acknowledge_interruption') {
      children.push(el('p', { className: 'muted', text: N.inChat }));
    }
    if (actions.length) children.push(el('div', { className: 'ov-hero-actions' }, actions));
    // Layer 2: the engine's own words, for whoever wants them.
    const engine = [];
    if (next.juniorMessage && next.juniorMessage !== spec.lead) engine.push({ id: 'next_action', text: next.juniorMessage });
    if (next.audience === 'agent' && next.message) engine.push({ id: 'next_action.agent', label: N.engineSays, text: next.message });
    else if (next.message && next.message !== next.juniorMessage) engine.push({ id: 'next_action', text: next.message });
    if (proposal && proposal.value) engine.push({ id: proposal.proposalId, label: N.engineLabel, text: `${proposal.value} (${proposal.proposalId})` });
    children.push(details(N.details, engine, { 'data-hero-details': true }));
    return el('section', { className: 'ov-hero', 'aria-labelledby': 'ov-hero-title', 'data-ov': 'hero', 'data-hero': kind }, children);
  }

  // --- the journey (§6.1.2, blocker-aware) --------------------------------------------------

  function subLabel(step, status) {
    const c = copy();
    const p = Number.isInteger(step.pause) ? step.pause : null;
    switch (status) {
      case 'done':
        if (p !== null && step.decisionStatus === 'confirmed') {
          // ADR 0005: endorsed and restated are the junior's own words, like explicit.
          if (['explicit', 'endorsed', 'restated'].includes(step.basis)) return c.pauseWords(p);
          if (step.basis === 'delegated_default') return c.pauseDelegated(p);
        }
        return '';
      case 'reopened': return p !== null ? c.pauseReopened(p) : c.reopened;
      case 'awaiting_confirmation': return p !== null ? c.pauseWaiting(p) : c.waitingForYou;
      case 'needs_reconfirmation': return p !== null ? c.pauseAgain(p) : c.confirmAgain;
      case 'ready': return c.ready;
      case 'blocked': return step.after ? c.after(str(step.after.title)) : c.blocked;
      default: return '';
    }
  }

  function stepItem(step, model, currentId) {
    const c = copy();
    const status = displayStatus(step, model);
    const current = currentId === step.id;
    const label = subLabel(step, status);
    return el('li', { className: `ov-step ov-step-${status}`, 'data-step': step.id, 'data-status': step.status,
      'data-display-status': status, 'data-nav': `step:${step.id}`, 'aria-current': current ? 'step' : null }, [
      el('span', { className: 'ov-mark', 'aria-hidden': 'true', text: c.marks[status] }),
      el('span', { className: 'sr-only', 'data-mark-text': true, text: `${c.markText[status]}: ` }),
      el('span', { className: 'ov-step-title', text: str(step.title) }),
      label ? el('span', { className: 'ov-sub', 'data-sub': true, text: label }) : null,
    ]);
  }

  function studyMap(model) {
    const c = copy();
    const plan = arr(model.plan);
    const byId = Object.fromEntries(plan.map(s => [s.id, s]));
    const moments = arr(model.moments);
    const currentId = currentStepId(model);
    let body;
    if (moments.length) {
      body = el('div', { className: 'ov-map', 'data-map': true }, moments.map(m => {
        const id = `ov-moment-${str(m.id)}`;
        return el('section', { className: 'ov-moment', 'data-moment': str(m.id), 'aria-labelledby': id }, [
          el('h3', { id, className: 'ov-moment-title', text: str(m.title) }),
          el('ol', { className: 'ov-steps' }, arr(m.steps).filter(sid => byId[sid]).map(sid => stepItem(byId[sid], model, currentId))),
        ]);
      }));
    } else {
      body = el('ol', { className: 'ov-steps ov-steps-flat', 'data-map': true }, plan.map(s => stepItem(s, model, currentId)));
    }
    return section('ov-map', c.mapTitle, [body], { 'data-ov': 'map' });
  }

  // --- Where we are (§6.1.1) ----------------------------------------------------------------

  const lineOf = (lines, label) => {
    const line = arr(lines).map(str).find(l => l.startsWith(`${label}: `));
    return line ? line.slice(label.length + 2) : null;
  };

  function whereWeAre(model, ctx) {
    const c = copy();
    const task = taskOf(model, ctx);
    const junior = arr(model.recapJunior);
    const goal = lineOf(junior.length ? junior : (model.recapAudience === 'agent' ? [] : model.recap), 'Goal');
    const decided = arr(model.plan).filter(s => DECISIONS.includes(s.id) && model.decisions && model.decisions[s.id]
      && ['confirmed', 'reconfirm_required'].includes(model.decisions[s.id].status));
    const rows = [];
    if (goal) rows.push(el('div', { className: 'ov-recap-row', 'data-recap-line': 'Goal' }, [el('dt', { text: c.goal }), el('dd', { text: goal })]));
    rows.push(el('div', { className: 'ov-recap-row', 'data-recap-line': 'Decided' }, [
      el('dt', { text: c.decided }),
      el('dd', {}, [decided.length ? el('ul', { className: 'ov-decided', 'data-decided': true }, decided.map(s => {
        const d = model.decisions[s.id];
        const tag = d.status === 'reconfirm_required' ? c.toConfirmAgain : d.basis === 'delegated_default' ? c.delegated : null;
        return el('li', { 'data-decided-item': s.id }, [
          el('span', { className: 'ov-decided-name', text: `${J().decisionName(s.id, task)}: ` }),
          valueNode(s.id, d.value, task),
          tag ? el('span', { className: 'ht-status ht-st-needs', text: tag }) : null,
        ]);
      })) : el('span', { className: 'muted', text: c.nothingDecided })]),
    ]));
    const body = el('dl', { className: 'ov-recap', 'data-recap-list': true }, rows);
    // The engine's recap under Details: its junior variant; an older engine's recap (no
    // audience) as it is; never a recap written for the agent.
    const recap = junior.length ? junior : model.recapAudience === 'agent' ? [] : arr(model.recap);
    return section('ov-where', c.whereTitle, [body,
      details(c.recapDetails, recap.map((line, i) => ({ id: `recap:${i}`, text: line })), { 'data-recap-details': true })],
    { 'data-ov': 'where' });
  }

  // --- Since your last session (§6.1.3, grouped) ------------------------------------------------

  function digestRows(digest, model, ctx) {
    const task = taskOf(model, ctx);
    const open = new Set(arr(model.proposals).map(p => p.proposalId));
    const notes = Object.fromEntries(arr(model.notes).map(n => [n.noteId, n]));
    const rows = arr(digest.items).map(item => {
      let group = J().GROUP_OF_KIND[item.kind] || 'other';
      if (item.kind === 'proposed' && !open.has(item.proposalId)) group = 'resolved';
      if (item.kind === 'result_replaced' || item.kind === 'result_added') group = 'evaluated';
      const text = J().digestText(item, task, item.noteId ? notes[item.noteId] : null) || str(item.text);
      return { item, group, text };
    });
    // Newest first inside each group; groups in a fixed order (needs you first).
    const order = J().GROUP_ORDER;
    return rows.map((r, i) => ({ ...r, i }))
      .sort((a, b) => order.indexOf(a.group) - order.indexOf(b.group) || b.i - a.i);
  }

  function digestItem(row) {
    const c = copy();
    const { item, group, text } = row;
    const kept = Array.isArray(item.refit) && item.refit.length === 0 && arr(item.keptFits).length > 0;
    return el('li', { className: 'ov-digest-item', 'data-digest-item': str(item.kind), 'data-group': group, 'data-text': text,
      title: str(item.text) || null }, [
      el('span', { className: `ht-tag ht-tag-${group}`, 'data-chip': group, text: J().groups[group] }), ' ',
      el('span', { 'data-digest-text': true, text }),
      kept ? [' ', el('strong', { 'data-kept-fits': true, text: c.keptFits })] : null,
    ]);
  }

  function sinceSection(model, ctx) {
    const c = copy();
    const base = model.digest;
    if (!base) {
      return section('ov-since', c.sinceTitle, [el('p', { className: 'muted', 'data-no-digest': true, text: c.noDigest })],
        { 'data-ov': 'since' });
    }
    const boundary = Number.isInteger(base.boundary) ? base.boundary : base.since;
    const wanted = local.since !== null && local.since !== boundary ? local.since : null;
    let digest = base;
    let updating = false;
    if (wanted !== null) {
      const got = ctx.data('summary');
      const m = got && got.model && got.model.digest;
      if (ctx.fresh(got) && m && m.since === wanted) digest = m;
      else {
        updating = true;
        askOnce(ctx, 'summary', { since: wanted });
      }
    }
    const header = wanted !== null ? c.sinceStart
      : base.gapMinutes === null || base.gapMinutes === undefined ? c.thisSession
        : c.sinceTime(base.sinceTime ? ctx.format.localTime(base.sinceTime) : '');
    const children = [];
    if (boundary !== null && boundary !== undefined && boundary !== 1) {
      const id = 'ov-since-select';
      const select = el('select', { id, 'data-since-select': true }, [
        el('option', { value: String(boundary), text: c.optionBoundary(boundary) }),
        el('option', { value: '1', text: c.optionStart }),
      ]);
      select.value = wanted !== null ? String(wanted) : String(boundary);
      select.addEventListener('change', () => {
        const v = Number(select.value);
        local.since = v === boundary ? null : v;
        ctx.rerender();
      });
      children.push(el('div', { className: 'ov-since-select' }, [el('label', { for: id, text: c.showSince }), select]));
    }
    children.push(el('p', { className: 'muted', 'data-since-header': true, text: header }));
    const rows = updating ? [] : digestRows(digest, model, ctx);
    if (updating) children.push(el('p', { className: 'muted', 'aria-busy': 'true', 'data-updating': 'summary', text: c.updating }));
    else if (rows.length) {
      const art = arr(model.artifacts).filter(a => a.name !== 'workbench');
      const behind = art.some(a => a.status !== 'ok');
      const deliverable = art.length ? [el('li', { className: 'ov-digest-item', 'data-digest-item': 'deliverables', 'data-group': 'deliverables' }, [
        el('span', { className: 'ht-tag ht-tag-deliverables', 'data-chip': 'deliverables', text: J().groups.deliverables }), ' ',
        el('span', { text: behind ? J().deliverablesBehind : J().deliverablesUpToDate })])] : [];
      const shown = rows.slice(0, MAX_DIGEST).map(digestItem);
      children.push(el('ul', { className: 'ov-digest', 'data-digest': true }, [...shown, ...deliverable]));
      if (rows.length > MAX_DIGEST) {
        children.push(el('details', { className: 'ov-digest-more', 'data-digest-more': true }, [
          el('summary', { text: c.showAll(rows.length) }),
          el('ul', { className: 'ov-digest' }, rows.slice(MAX_DIGEST).map(digestItem)),
        ]));
      }
      if (digest.truncated) children.push(el('p', { className: 'muted', 'data-truncated': true, text: c.truncated }));
      children.push(details(c.engineRecord, arr(digest.items).map((i, n) => ({ id: `digest:${n}`, text: i.text })),
        { 'data-digest-details': true }));
    } else {
      children.push(el('p', { className: 'muted', 'data-nothing-changed': true, text: c.nothingChanged }));
    }
    return section('ov-since', c.sinceTitle, children, { 'data-ov': 'since' });
  }

  // --- What you cannot claim yet (limits by severity, listed once) ---------------------------

  function limitItems(model) {
    const nyd = model.notYetDefensible || {};
    const seen = new Set();
    const items = [];
    for (const i of arr(nyd.top)) {
      if (seen.has(i.id)) continue;
      seen.add(i.id);
      items.push({ id: i.id, text: i.juniorText || J().limitText[i.id] || J().limitFallback(i.id), engine: i.text, audience: i.audience });
    }
    for (const id of arr(nyd.more)) {
      if (seen.has(id)) continue;
      seen.add(id);
      items.push({ id, text: J().limitText[id] || J().limitFallback(id), engine: null });
    }
    const order = J().SEVERITY_ORDER;
    const sev = id => J().SEVERITY[id] || 'context';
    return items.map((x, n) => ({ ...x, severity: sev(x.id), n }))
      .sort((a, b) => order.indexOf(a.severity) - order.indexOf(b.severity) || a.n - b.n);
  }

  function limits(model, navUsed) {
    const c = copy();
    const items = limitItems(model);
    if (!items.length) return null;
    return section('ov-limits', c.limitsTitle, [
      el('ul', { className: 'ov-limits', 'data-limits': true }, items.map(i => {
        const nav = navUsed.has(i.id) ? null : `limit:${i.id}`;
        navUsed.add(i.id);
        return el('li', { 'data-nyd': i.id, 'data-severity': i.severity, 'data-nav': nav }, [
          el('span', { className: `ht-tag ht-sev-${i.severity}`, 'data-chip': i.severity, text: J().severityLabel[i.severity] }), ' ',
          el('span', { 'data-limit-text': true, text: i.text }),
        ]);
      })),
      details(c.limitsDetails, items.filter(i => i.engine && i.engine !== i.text)
        .map(i => ({ id: i.id, label: i.audience === 'agent' ? c.forAgent : null, text: i.engine })), { 'data-limits-details': true }),
    ], { 'data-ov': 'limits', 'data-health': 'nyd' });
  }

  // --- Deliverables (§6.1.4, with the local launch) ------------------------------------------

  function fileName(p) {
    const parts = str(p).split('/');
    return parts[parts.length - 1];
  }

  function renderOutcomeW5(o, ctx) {
    if (!o) return null;
    const c = copy();
    if (o.kind === 'ok_with_problems') {
      return el('div', { className: 'card success', role: 'status', 'data-outcome': o.kind, 'data-op': o.op }, [
        el('p', { className: 'title', text: c.regeneratedProblems }),
        el('ul', {}, arr(o.artifacts).map(a => el('li', { 'data-artifact-message': str(a.name), text: str(a.message) }))),
      ]);
    }
    const node = ctx.renderOutcome(o);
    if (node && o.kind === 'ok') {
      for (const li of node.querySelectorAll('li')) li.setAttribute('data-artifact-message', '');
    }
    return node;
  }

  const STATUS_CLASS = { ok: 'ht-st-ok', stale: 'ht-st-stale', failed: 'ht-st-error', missing: 'ht-st-error', edited: 'ht-st-stale' };

  function deliverableRow(a, model, ctx) {
    const c = copy();
    const d = c.deliverable[a.name] || {};
    const buttons = [];
    if (a.name === 'report') {
      buttons.push(el('button', { type: 'button', 'data-open': 'report', text: c.openInBrowser, 'aria-label': c.openReportName,
        onclick: () => ctx.send({ type: 'open_artifact', artifact: 'report' }) }));
    } else {
      const edit = a.name === 'workbench';
      if (!(edit && ctx.reviewer)) {
        buttons.push(el('button', { type: 'button', 'data-marimo': a.name, text: edit ? c.marimoEdit : c.marimoRead,
          onclick: () => ctx.send({ type: 'open_marimo', artifact: a.name }) }));
      }
      buttons.push(el('button', { type: 'button', className: 'secondary', 'data-open': a.name, text: c.openFile,
        'aria-label': c.openInEditorName(str(a.label)), onclick: () => ctx.send({ type: 'open_artifact', artifact: a.name }) }));
    }
    const status = a.name === 'workbench' ? 'yours' : str(a.status);
    const text = a.name === 'workbench' ? '' : a.juniorMessage || (a.audience === 'agent' ? (c.statusText[a.status] || '') : str(a.message));
    return el('div', { className: 'ov-deliverable', 'data-artifact': str(a.name), 'data-status': str(a.status) }, [
      el('div', { className: 'ov-deliverable-main' }, [
        el('div', { className: 'ov-deliverable-label', text: c.deliverableLabel(str(d.label || a.label), fileName(a.path)) }),
        el('div', { className: 'ht-mono ov-path muted', text: str(a.path) }),
        el('div', { className: 'ov-deliverable-what', text: str(d.what) }),
        el('div', {}, [
          el('span', { className: `ht-status ${a.name === 'workbench' ? 'ht-st-neutral' : STATUS_CLASS[a.status] || 'ht-st-stale'}`,
            'data-status-chip': status, text: c.statusChip[status] || status }), ' ',
          el('span', { className: 'ov-deliverable-status', 'data-message': true, title: a.message || null, text }),
        ]),
      ]),
      el('div', { className: 'ov-deliverable-actions' }, buttons),
    ]);
  }

  function deliverables(model, ctx) {
    const c = copy();
    const items = arr(model.artifacts);
    const children = items.length ? items.map(a => deliverableRow(a, model, ctx))
      : [el('p', { className: 'muted', text: c.nothingRendered })];
    const m = ctx.init && ctx.init.marimo;
    if (m && (m.notebook || m.workbench)) {
      children.push(el('div', { className: 'ov-launch', 'data-launch-info': true }, [
        el('p', { className: 'ov-launch-title', text: c.launchTitle }),
        el('p', { text: c.launchWhat }),
        m.notebook ? el('pre', { className: 'ht-mono', 'data-launch': 'notebook', text: m.notebook }) : null,
        m.workbench ? el('pre', { className: 'ht-mono', 'data-launch': 'workbench', text: m.workbench }) : null,
        el('p', { className: 'muted', 'data-kernel': true }, [c.kernel, m.kernel ? el('code', { text: m.kernel }) : c.kernelUnknown, c.kernelTail]),
      ]));
    }
    if (model.regenerate && !ctx.reviewer && ctx.atLeast('v1')) {
      const working = ctx.busy && ctx.busyTarget === RENDER_TARGET;
      children.push(el('div', { className: 'ov-regenerate' }, [
        el('button', { type: 'button', 'data-write': 'render', disabled: ctx.busy,
          'aria-busy': working ? 'true' : null, text: working ? c.working : c.regenerate,
          onclick: () => { if (!ctx.busy) ctx.send({ type: 'render' }); } }),
        el('span', { className: 'muted', text: c.regenerateWhat }),
      ]));
    }
    const o = ctx.outcome(RENDER_TARGET);
    if (o) children.push(renderOutcomeW5(o, ctx));
    if (ctx.atLeast('v1')) children.push(el('div', { className: 'ov-sub-section', 'data-health': 'checks' }, [checks(model, ctx)]));
    return section('ov-deliverables', c.deliverablesTitle, children, { 'data-ov': 'deliverables' });
  }

  // --- Health (§6.1.5): only when something is wrong -----------------------------------------

  function executionCard(e, model, ctx) {
    const c = copy();
    const id = str(e.executionId);
    const titleId = `ov-exec-${id}`;
    const children = [
      el('h4', { id: titleId, text: c.unknownOutcome(str(e.activity)) }),
      e.reason ? el('details', { className: 'ht-details' }, [el('summary', { text: copy().detailsLabel }),
        el('p', { className: 'muted', 'data-reason': true, text: str(e.reason) })]) : null,
    ];
    if (!ctx.reviewer) {
      const areaId = `ack-${id}`;
      const hintId = `ack-hint-${id}`;
      const button = el('button', { type: 'button', 'data-write': 'acknowledge', 'data-execution': id, text: c.acknowledge });
      const area = ctx.wordsArea({ kind: 'ackDrafts', key: id, id: areaId, name: areaId, 'aria-describedby': hintId,
        'data-execution': id, 'data-write': 'acknowledge', onInput: () => sync() });
      const sync = () => {
        button.disabled = ctx.busy || !area.value.trim();
        if (ctx.busy && ctx.busyTarget === id) { button.setAttribute('aria-busy', 'true'); button.textContent = c.working; }
      };
      button.addEventListener('click', () => {
        if (ctx.busy || !area.value.trim()) return;
        if (!local.acknowledged.includes(id)) local.acknowledged.push(id);
        ctx.send({ type: 'acknowledge', executionId: id, words: area.value, revision: model.revision });
      });
      sync();
      children.push(el('div', { className: 'ov-ack', 'data-write': 'acknowledge' }, [
        el('label', { for: areaId, text: c.reply }),
        area,
        el('p', { id: hintId, className: 'muted', text: c.replyHint }),
        button,
      ]));
    }
    children.push(el('p', { className: 'muted', 'data-rerun': true, text: c.rerunInChat }));
    const o = ctx.outcome(id);
    if (o && o.op === 'W6') children.push(ctx.renderOutcome(o));
    return el('article', { className: 'card ov-execution', 'data-execution-card': id, 'data-nav': `execution:${id}`,
      'aria-labelledby': titleId }, children);
  }

  function executions(model, ctx, navUsed) {
    const c = copy();
    const ex = model.executions || {};
    const pending = [...arr(ex.interrupted), ...arr(ex.suspected)];
    const late = arr(ex.late);
    const listed = new Set(pending.map(e => e.executionId));
    const done = local.acknowledged.filter(id => !listed.has(id)).map(id => ctx.outcome(id)).filter(o => o && o.op === 'W6');
    if (!pending.length && !late.length && !done.length) return null;
    const next = model.nextAction || {};
    const children = [el('h3', { id: 'ov-executions', text: c.executionsTitle })];
    for (const e of pending) {
      const card = executionCard(e, model, ctx);
      if (next.kind === 'outcome_unknown' && next.executionId === e.executionId && !navUsed.has('outcome_unknown')) {
        navUsed.add('outcome_unknown');
        children.push(el('div', { 'data-nav': 'limit:outcome_unknown' }, [card]));
      } else children.push(card);
    }
    if (late.length) {
      children.push(el('ul', { className: 'ov-late', 'data-late': true }, late.map(e =>
        el('li', { 'data-late-item': str(e.executionId), text: c.lateResult(str(e.activity)) }))));
    }
    if (done.length) {
      children.push(el('div', { 'data-acknowledged': true, 'aria-label': c.acknowledgedEarlier }, done.map(o => ctx.renderOutcome(o))));
    }
    navUsed.add('interrupted_executions');
    return el('section', { className: 'ov-sub-section', 'aria-labelledby': 'ov-executions', 'data-nav': 'limit:interrupted_executions',
      'data-health': 'executions' }, children);
  }

  function checksSummary(model, ctx) {
    const c = copy();
    const got = ctx.data('check');
    const parts = [c.checksTitle];
    if (got && got.model) {
      const counts = got.model.counts || {};
      parts.push(got.model.clean ? c.checksClean
        : [c.checksErrors(counts.error || 0), counts.warning ? c.checksWarnings(counts.warning) : null].filter(Boolean).join(', '));
    }
    return parts.join(' · ');
  }

  function findingItem(f, ctx) {
    const c = copy();
    const canOpen = Boolean(f.deliverable);
    return el('li', { className: `ov-finding ov-finding-${str(f.severity)}`, 'data-finding': str(f.code), 'data-severity': str(f.severity) }, [
      el('span', { className: 'ov-severity', text: str(f.severity) }), ' ',
      el('span', { 'data-finding-message': true, text: str(f.message) }), ' ',
      el('span', { className: 'muted', 'data-where': true, text: str(f.where) }), ' ',
      el('code', { className: 'muted', text: str(f.code) }),
      canOpen ? el('button', { type: 'button', className: 'secondary', 'data-open-finding': f.deliverable,
        text: copy().open, 'aria-label': c.openFinding(str(f.where) || str(f.deliverable)),
        onclick: () => {
          const message = { type: 'open_artifact', artifact: f.deliverable };
          if (f.deliverable === 'report' && f.resultId && ctx.atLeast('v1')) message.resultId = f.resultId;
          const line = f.location && f.location.line;
          if (f.deliverable !== 'report' && Number.isInteger(line) && line > 0 && ctx.atLeast('v1')) message.line = line;
          ctx.send(message);
        } }) : null,
    ]);
  }

  function checks(model, ctx) {
    const c = copy();
    const got = ctx.data('check');
    const error = ctx.error('check');
    const body = [];
    if (local.checksOpen) {
      const fresh = ctx.fresh(got);
      if (!fresh) askOnce(ctx, 'check');
      if (error && !fresh) {
        body.push(el('div', { className: 'card alert', role: 'alert', 'data-check-error': true }, [
          el('p', { className: 'title', text: c.checksFailed }),
          el('p', { text: str(error.message) }),
          error.detail ? el('pre', { text: str(error.detail) }) : null,
          el('button', { type: 'button', className: 'secondary', text: c.retry, onclick: () => { ctx.retry('check'); ctx.load('check'); } }),
        ]));
      } else if (!got) {
        body.push(el('p', { className: 'muted', 'aria-busy': 'true', 'data-check-loading': true, text: c.checksRunning }));
      } else {
        const findings = arr(got.model.findings);
        const list = findings.length ? el('ul', { className: 'ov-findings', 'data-findings': true }, findings.map(f => findingItem(f, ctx)))
          : el('p', { className: 'muted', text: c.checksNone });
        // Older findings are dimmed while the new ones are read; no "Updating" label next to
        // content that is current.
        if (!fresh) body.push(el('div', { className: 'ht-stale', 'aria-busy': 'true', 'data-updating': 'check' }, [list]));
        else body.push(list);
      }
    }
    const node = el('details', { className: 'ov-checks', 'data-check': true, open: local.checksOpen ? true : null }, [
      el('summary', { id: 'ov-check-summary', 'data-check-summary': true, text: checksSummary(model, ctx) }),
      ...body,
    ]);
    node.addEventListener('toggle', () => {
      if (node.open === local.checksOpen) return;
      local.checksOpen = node.open;
      ctx.rerender();
    });
    return node;
  }

  function health(model, ctx, navUsed) {
    const c = copy();
    const ex = executions(model, ctx, navUsed);
    const alerts = arr(model.alerts).filter(a => a.id !== 'outcome_unknown' && a.id !== 'interrupted_executions');
    if (!ex && !alerts.length) return null;
    const children = [ex];
    if (alerts.length) {
      children.push(el('ul', { className: 'ov-health-alerts', 'data-health': 'alerts' }, alerts.map(a => {
        const nav = navUsed.has(a.id) ? null : `limit:${a.id}`;
        navUsed.add(a.id);
        return el('li', { 'data-nav': nav, 'data-health-alert': a.id }, [
          el('span', { className: 'ht-tag ht-sev-blocking', text: J().severityLabel.blocking }), ' ',
          a.juniorText || J().limitText[a.id] || J().limitFallback(a.id)]);
      })));
    }
    return section('ov-health', c.healthTitle, children, { 'data-ov': 'health', 'data-nav': 'limit:health' });
  }

  // --- registration -------------------------------------------------------------------------

  function journeyV0(model) {
    const c = copy();
    const currentId = currentStepId(model);
    return section('ov-map', c.journeyTitle, [
      el('ol', { className: 'ov-steps ov-steps-flat', 'data-map': true }, arr(model.plan).map(s => stepItem(s, model, currentId))),
    ], { 'data-ov': 'map' });
  }

  function renderV0(model, ctx) {
    const navUsed = new Set();
    return [hero(model, ctx), journeyV0(model), whereWeAre(model, ctx), limits(model, navUsed), deliverables(model, ctx)];
  }

  function renderV1(model, ctx) {
    const gate = node => ctx.gate('v1', node);
    const navUsed = new Set();
    const healthNode = health(model, ctx, navUsed);
    return [
      hero(model, ctx),
      healthNode ? gate(healthNode) : null,
      gate(studyMap(model)),
      gate(el('div', { className: 'ov-grid' }, [sinceSection(model, ctx), limits(model, navUsed)])),
      gate(whereWeAre(model, ctx)),
      gate(deliverables(model, ctx)),
    ];
  }

  HT.register('overview', {
    tab: 'overview',
    stage: 'v0',
    views: [],
    outcomes: ['W5', 'W6'],
    render(model, ctx) {
      return ctx.atLeast('v1') ? renderV1(model, ctx) : renderV0(model, ctx);
    },
    onMessage(m) {
      if (m.type === 'outcome' && m.op === 'W6' && m.target && !local.acknowledged.includes(m.target)) local.acknowledged.push(m.target);
      return undefined;
    },
  });

  // Test hook: the view-local state (not persisted, not a study fact).
  HT._overview = local;
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
