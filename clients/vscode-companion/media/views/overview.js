// Overview view (COMPANION-ADVANCED §6.1; owned by WP-U1). Mockup: Main.dc.html.
//
//   stage v0   the v0 panel's read-only sections (recap, plan, deliverables, not yet
//              defensible), unchanged in behaviour (decision CA.11)
//   stage v1+  Where we are (recap as a <dl>), Study map (moments), Since your last
//              session (digest), Deliverables (Open, Regenerate W5), Health (executions
//              with the typed acknowledgement W6, check findings, not yet defensible)
//
// Study text is always set as text (INV-9). The only words field is ctx.wordsArea
// (INV-5): it starts empty, and "Acknowledge in my words" stays disabled until it holds a
// non-blank character. No control restarts a run (HE-2).
(function (HT) {
  'use strict';
  const el = HT.el;
  const str = x => (typeof x === 'string' ? x : '');
  const arr = x => (Array.isArray(x) ? x : []);
  const copy = () => HT.copy.overview;
  const RENDER_TARGET = 'render';
  const MAP_STATUSES = ['done', 'awaiting_confirmation', 'needs_reconfirmation', 'ready', 'blocked'];

  // View-local, not persisted: the chosen digest boundary, the Health check expansion, the
  // reads asked per revision, and the executions acknowledged from this panel.
  const local = { since: null, checksOpen: false, asked: {}, acknowledged: [] };

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

  // --- v0 subset ----------------------------------------------------------------------------

  function renderV0(model, ctx) {
    const c = copy().v0;
    const out = [];
    out.push(section('h-recap', c.recap, [
      el('ul', { 'data-recap': true }, arr(model.recap).map(line => el('li', { text: str(line) }))),
    ]));
    const step = model.currentStep;
    out.push(section('h-plan', c.plan, [
      el('p', { 'data-current-step': step ? step.id : '', text: step ? c.step(step.position, step.total, str(step.title)) : c.allDone }),
      model.nextAction && model.nextAction.message ? el('p', { className: 'muted', text: c.next(str(model.nextAction.message)) }) : null,
      el('ol', {}, arr(model.plan).map(s => el('li', { 'aria-current': step && s.id === step.id ? 'step' : null },
        [`${str(s.title)} `, el('span', { className: 'muted', text: `(${str(s.status).replace(/_/g, ' ')})` })]))),
    ]));
    out.push(section('h-artifacts', c.deliverables, arr(model.artifacts).length
      ? arr(model.artifacts).map(a => el('div', { className: 'card', 'data-artifact': str(a.name) }, [
        el('p', {}, [el('span', { className: `status status-${str(a.status)}`, text: `${str(a.label)}: ${str(a.status)}` })]),
        el('p', { text: str(a.message) }),
        el('button', { type: 'button', className: 'secondary', disabled: ctx.busy,
          text: a.name === 'report' ? c.openReport : c.open(str(a.label)),
          onclick: () => ctx.send({ type: 'open_artifact', artifact: a.name }) }),
      ]))
      : [el('p', { className: 'muted', text: c.nothingRendered })]));
    const nyd = model.notYetDefensible || {};
    out.push(section('h-nyd', c.nyd, [
      el('ul', {}, arr(nyd.top).map(i => el('li', { 'data-nyd': str(i.id), 'data-nav': `limit:${str(i.id)}`, text: str(i.text) }))),
      arr(nyd.more).length ? el('p', { className: 'muted', text: c.alsoListed(arr(nyd.more).join(', ')) }) : null,
    ]));
    return out;
  }

  // --- Where we are (§6.1.1) ----------------------------------------------------------------

  /** Split a recap line at its first ": " into the label and the rest (verbatim, OV-1). */
  function splitLine(line) {
    const i = line.indexOf(': ');
    return i > 0 ? [line.slice(0, i), line.slice(i + 2)] : ['', line];
  }

  function whereWeAre(model, ctx) {
    const c = copy();
    const recap = arr(model.recap).map(str);
    const next = model.nextAction || {};
    const link = (next.kind === 'await_user_words' && next.proposalId) ? { kind: 'proposal', id: next.proposalId }
      : (next.kind === 'reconfirm' && next.decision) ? { kind: 'decision', id: next.decision } : null;
    const body = recap.length
      ? el('dl', { className: 'ov-recap', 'data-recap-list': true }, recap.map(line => {
        const [label, rest] = splitLine(line);
        return el('div', { className: 'ov-recap-row', 'data-recap-line': label }, [
          el('dt', { text: label }),
          el('dd', {}, [
            el('span', { 'data-recap-text': true, text: rest }),
            label === 'Next' && link ? [' ', el('button', { type: 'button', className: 'ht-link', 'data-open-decisions': link.id,
              text: c.openInDecisions, onclick: () => ctx.navigate({ tab: 'decisions', kind: link.kind, id: link.id }) })] : null,
          ]),
        ]);
      }))
      : el('p', { className: 'muted', 'data-no-recap': true, text: c.noRecap });
    return section('ov-where', c.whereTitle, [el('p', { className: 'muted ov-source', text: c.whereSource }), body],
      { 'data-ov': 'where' });
  }

  // --- Study map (§6.1.2) -------------------------------------------------------------------

  function subLabel(step) {
    const c = copy();
    const p = Number.isInteger(step.pause) ? step.pause : null;
    switch (step.status) {
      case 'done':
        if (p !== null && step.decisionStatus === 'confirmed') {
          if (step.basis === 'explicit') return c.pauseWords(p);
          if (step.basis === 'delegated_default') return c.pauseDelegated(p);
        }
        return '';
      case 'awaiting_confirmation': return p !== null ? c.pauseWaiting(p) : c.waitingForYou;
      case 'needs_reconfirmation': return p !== null ? c.pauseAgain(p) : c.confirmAgain;
      case 'ready': return c.ready;
      case 'blocked': return step.after ? c.after(str(step.after.title)) : c.blocked;
      default: return '';
    }
  }

  function stepItem(step, model) {
    const c = copy();
    const status = MAP_STATUSES.includes(step.status) ? step.status : 'ready';
    const current = model.currentStep && model.currentStep.id === step.id;
    const label = subLabel(step);
    return el('li', { className: `ov-step ov-step-${status}`, 'data-step': step.id, 'data-status': step.status,
      'data-nav': `step:${step.id}`, 'aria-current': current ? 'step' : null }, [
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
    let body;
    if (moments.length) {
      body = el('div', { className: 'ov-map', 'data-map': true }, moments.map(m => {
        const id = `ov-moment-${str(m.id)}`;
        return el('section', { className: 'ov-moment', 'data-moment': str(m.id), 'aria-labelledby': id }, [
          el('h3', { id, className: 'ov-moment-title', text: str(m.title) }),
          el('ol', { className: 'ov-steps' }, arr(m.steps).filter(sid => byId[sid]).map(sid => stepItem(byId[sid], model))),
        ]);
      }));
    } else {
      // An engine without C1 (decision CA.14): the plan in order, in one column.
      body = el('div', {}, [
        el('p', { className: 'muted', text: c.noMoments }),
        el('ol', { className: 'ov-steps', 'data-map': true }, plan.map(s => stepItem(s, model))),
      ]);
    }
    return section('ov-map', c.mapTitle, [body], { 'data-ov': 'map' });
  }

  // --- Since your last session (§6.1.3) -----------------------------------------------------

  function digestItem(item) {
    const c = copy();
    const text = str(item.text);
    const kept = Array.isArray(item.refit) && item.refit.length === 0 && arr(item.keptFits).length > 0;
    const children = [];
    if (kept && text.endsWith(c.keptFits)) {
      // The engine's sentence already ends with it: keep the text verbatim, in bold.
      const head = text.slice(0, text.length - c.keptFits.length);
      children.push(head, el('strong', { 'data-kept-fits': true, text: c.keptFits }));
    } else {
      children.push(text);
      if (kept) children.push(' ', el('strong', { 'data-kept-fits': true, text: c.keptFits }));
    }
    return el('li', { 'data-digest-item': str(item.kind), 'data-text': text }, children);
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
    const items = arr(digest.items);
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
    if (updating) children.push(el('p', { className: 'muted', 'aria-busy': 'true', 'data-updating': 'summary', text: c.updating }));
    else if (items.length) {
      children.push(el('ul', { className: 'ov-digest', 'data-digest': true }, items.map(digestItem)));
      if (digest.truncated) children.push(el('p', { className: 'muted', 'data-truncated': true, text: c.truncated }));
    } else {
      children.push(el('p', { className: 'muted', 'data-nothing-changed': true, text: c.nothingChanged }));
    }
    return section('ov-since', c.sinceTitle, children, { 'data-ov': 'since' });
  }

  // --- Deliverables (§6.1.4) ----------------------------------------------------------------

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

  function deliverables(model, ctx) {
    const c = copy();
    const items = arr(model.artifacts);
    const rows = items.map(a => el('div', { className: 'ov-deliverable', 'data-artifact': str(a.name), 'data-status': str(a.status) }, [
      el('div', {}, [
        el('div', { className: 'ov-deliverable-label', text: c.deliverableLabel(str(a.label), fileName(a.path)) }),
        el('div', { className: `ov-deliverable-status status-${str(a.status)}`, 'data-message': true, text: str(a.message) }),
      ]),
      el('button', { type: 'button', className: 'secondary', 'data-open': str(a.name), text: c.open,
        'aria-label': a.name === 'report' ? c.openReportName : c.openInEditorName(str(a.label)),
        onclick: () => ctx.send({ type: 'open_artifact', artifact: a.name }) }),
    ]));
    const children = rows.length ? rows : [el('p', { className: 'muted', text: c.nothingRendered })];
    if (model.regenerate && !ctx.reviewer) {
      const working = ctx.busy && ctx.busyTarget === RENDER_TARGET;
      children.push(el('button', { type: 'button', 'data-write': 'render', disabled: ctx.busy,
        'aria-busy': working ? 'true' : null, text: working ? c.working : c.regenerate,
        onclick: () => { if (!ctx.busy) ctx.send({ type: 'render' }); } }));
    }
    const o = ctx.outcome(RENDER_TARGET);
    if (o) children.push(renderOutcomeW5(o, ctx));
    return section('ov-deliverables', c.deliverablesTitle, children, { 'data-ov': 'deliverables' });
  }

  // --- Health (§6.1.5) ----------------------------------------------------------------------

  function executionCard(e, model, ctx) {
    const c = copy();
    const id = str(e.executionId);
    const titleId = `ov-exec-${id}`;
    const children = [
      el('h4', { id: titleId, text: c.unknownOutcome(str(e.activity)) }),
      e.reason ? el('p', { className: 'muted', 'data-reason': true, text: str(e.reason) }) : null,
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
    // Acknowledged from this panel: the card is gone once the engine lists it no more, so
    // its outcome is shown here.
    const listed = new Set(pending.map(e => e.executionId));
    const done = local.acknowledged.filter(id => !listed.has(id)).map(id => ctx.outcome(id)).filter(o => o && o.op === 'W6');
    if (done.length) {
      children.push(el('div', { 'data-acknowledged': true, 'aria-label': c.acknowledgedEarlier }, done.map(o => ctx.renderOutcome(o))));
    }
    if (!pending.length && !late.length && !done.length) {
      children.push(el('p', { className: 'muted', 'data-no-executions': true, text: c.noExecutions }));
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
      el('code', { text: str(f.code) }), ' ',
      el('span', { 'data-finding-message': true, text: str(f.message) }), ' ',
      el('span', { className: 'muted', 'data-where': true, text: str(f.where) }),
      canOpen ? el('button', { type: 'button', className: 'secondary', 'data-open-finding': f.deliverable,
        text: copy().open, 'aria-label': c.openFinding(str(f.where) || str(f.deliverable)),
        onclick: () => {
          const message = { type: 'open_artifact', artifact: f.deliverable };
          // The report at the cited result's anchor, an editor deliverable at the finding's
          // line (open_artifact.resultId and .line, stage v1).
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
        if (!fresh) body.push(el('p', { className: 'muted', 'aria-busy': 'true', 'data-updating': 'check', text: c.updating }));
        const findings = arr(got.model.findings);
        body.push(findings.length ? el('ul', { className: 'ov-findings', 'data-findings': true }, findings.map(f => findingItem(f, ctx)))
          : el('p', { className: 'muted', text: c.checksNone }));
      }
    }
    const details = el('details', { className: 'ov-checks', 'data-check': true, open: local.checksOpen ? true : null }, [
      el('summary', { id: 'ov-check-summary', 'data-check-summary': true, text: checksSummary(model, ctx) }),
      ...body,
    ]);
    details.addEventListener('toggle', () => {
      if (details.open === local.checksOpen) return;
      local.checksOpen = details.open;
      ctx.rerender();
    });
    return details;
  }

  function notYetDefensible(model, navUsed) {
    const c = copy();
    const nyd = model.notYetDefensible || {};
    const top = arr(nyd.top);
    if (!top.length && !arr(nyd.more).length) return null;
    return el('section', { className: 'ov-sub-section ov-nyd', 'aria-labelledby': 'ov-nyd', 'data-health': 'nyd' }, [
      el('h3', { id: 'ov-nyd', text: c.nydTitle }),
      el('ul', {}, top.map(i => {
        const id = str(i.id);
        const nav = navUsed.has(id) ? null : `limit:${id}`;
        navUsed.add(id);
        return el('li', { 'data-nyd': id, 'data-nav': nav, text: str(i.text) });
      })),
      arr(nyd.more).length ? el('p', { className: 'muted', 'data-nyd-more': true, text: c.more(arr(nyd.more).join(', ')) }) : null,
    ]);
  }

  function health(model, ctx) {
    const c = copy();
    const navUsed = new Set();
    return section('ov-health', c.healthTitle, [
      executions(model, ctx, navUsed),
      el('section', { className: 'ov-sub-section', 'data-health': 'checks', 'aria-label': c.checksTitle }, [checks(model, ctx)]),
      notYetDefensible(model, navUsed),
    ], { 'data-ov': 'health', 'data-nav': 'limit:health' });
  }

  // --- registration -------------------------------------------------------------------------

  function renderV1(model, ctx) {
    const gate = node => ctx.gate('v1', node);
    return [
      gate(whereWeAre(model, ctx)),
      gate(studyMap(model)),
      gate(el('div', { className: 'ov-grid' }, [sinceSection(model, ctx), deliverables(model, ctx)])),
      gate(health(model, ctx)),
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
      // A W6 outcome for an execution acknowledged from another panel instance (or after a
      // reload) is still shown by the card or the acknowledgements list.
      if (m.type === 'outcome' && m.op === 'W6' && m.target && !local.acknowledged.includes(m.target)) local.acknowledged.push(m.target);
      return undefined;
    },
  });

  // Test hook: the view-local state (not persisted, not a study fact).
  HT._overview = local;
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
