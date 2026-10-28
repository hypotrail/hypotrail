// Overview parts (COMPANION-ADVANCED §6.4, §6.7.4, TODO-3, TODO-4; formerly the Overview tab,
// WP-U1, WP-A5). The one page (ADR 0004 d13) places them through media/views/page.js:
//
//   since         "Since your last visit" (§6.4): the engine's digest, grouped in the panel's
//                 words, the engine record under a disclosure (SINCE-1, SINCE-2)
//   deliverables  the Deliverables drawer (§6.7.4): Open, the three Marimo launches,
//                 Regenerate (W5, from v1) and the checks, read when their fold opens (TODO-4)
//   findings      the check findings of To handle (TODO-4)
//
// Two-layer copy (§15.1): the primary sentences are the panel's own (media/copy/junior.js) or
// the engine's junior variants; an engine text written for the agent appears only under a
// "Details" disclosure. Study text is always set as text (INV-9). The panel takes no words
// of the junior here (R23, R31). No control restarts a run (HE-2).
(function (HT) {
  'use strict';
  const el = HT.el;
  const str = x => (typeof x === 'string' ? x : '');
  const arr = x => (Array.isArray(x) ? x : []);
  const copy = () => HT.copy.overview;
  const J = () => HT.copy.junior;
  const RENDER_TARGET = 'render';
  const MAX_DIGEST = 4;

  // View-local, not persisted: the chosen digest boundary, the checks expansion, and the
  // reads asked per version.
  const local = { since: null, checksOpen: false, asked: {} };

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
        // The engine's record is written for the assistant, in English (two-layer copy, §15.1).
        HT.components.engineText(str(r.text), { lang: r.lang || 'en' })]))),
    ]);
  }

  const taskOf = (model, ctx) => model.task || ctx.task || null;

  // --- Since your last session (§6.1.3, grouped) ------------------------------------------------

  function digestRows(digest, model, ctx) {
    const task = taskOf(model, ctx);
    const open = new Set(arr(model.proposals).map(p => p.proposalId));
    const notes = Object.fromEntries(arr(model.notes).map(n => [n.noteId, n]));
    const rows = arr(digest.items).map(item => {
      let group = J().GROUP_OF_KIND[item.kind] || 'other';
      if (item.kind === 'proposed' && !open.has(item.proposalId)) group = 'resolved';
      if (item.kind === 'result_replaced' || item.kind === 'result_added') group = 'evaluated';
      // Two-layer copy: the panel's words, else the engine's junior variant (WP-A7), else
      // the engine text when it is written for the junior; never an `agent` text.
      const own = J().digestText(item, task, item.noteId ? notes[item.noteId] : null);
      const text = own || str(item.juniorText) || (item.audience === 'agent' ? J().digestFallback : str(item.text));
      return { item, group, text, fromEngine: !own && text !== J().digestFallback };
    });
    // Newest first inside each group; groups in a fixed order (needs you first).
    const order = J().GROUP_ORDER;
    return rows.map((r, i) => ({ ...r, i }))
      .sort((a, b) => order.indexOf(a.group) - order.indexOf(b.group) || b.i - a.i);
  }

  function digestItem(row) {
    const c = copy();
    const { item, group, text, fromEngine } = row;
    const kept = Array.isArray(item.refit) && item.refit.length === 0 && arr(item.keptFits).length > 0;
    return el('li', { className: 'ov-digest-item', 'data-digest-item': str(item.kind), 'data-group': group, 'data-text': text,
      title: str(item.text) || null }, [
      el('span', { className: `ht-tag ht-tag-${group}`, 'data-chip': group, text: J().groups[group] }), ' ',
      fromEngine ? HT.components.engineText(text, { attrs: { 'data-digest-text': true } }) : el('span', { 'data-digest-text': true, text }),
      kept ? [' ', el('strong', { 'data-kept-fits': true, text: c.keptFits })] : null,
    ]);
  }

  function sinceSection(model, ctx) {
    const c = copy();
    const base = model.digest;
    if (!base) return el('div', { 'data-ov': 'since' }, [el('p', { className: 'muted', 'data-no-digest': true, text: c.noDigest })]);
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
    return el('div', { className: 'ov-since', 'data-ov': 'since' }, children);
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
      const edit = a.name === 'workbench' || a.name === 'editable';
      if (!(edit && ctx.reviewer)) {
        // Two rows have an "edit" button: the accessible name says which deliverable it opens.
        buttons.push(el('button', { type: 'button', 'data-marimo': a.name, text: edit ? c.marimoEdit : c.marimoRead,
          'aria-label': c.marimoName(edit ? c.marimoEdit : c.marimoRead, str(d.label || a.label)),
          onclick: () => ctx.send({ type: 'open_marimo', artifact: a.name }) }));
      }
      buttons.push(el('button', { type: 'button', className: 'secondary', 'data-open': a.name, text: c.openFile,
        'aria-label': c.openInEditorName(str(a.label)), onclick: () => ctx.send({ type: 'open_artifact', artifact: a.name }) }));
    }
    const owned = a.name === 'workbench' || a.name === 'editable';
    const status = owned ? 'yours' : str(a.status);
    // The workbench row says nothing more than its description; the editable copy shows the
    // engine's junior message (it tracks the generated notebook until the first edit and is
    // never official evidence), as the other deliverables do.
    const text = a.name === 'workbench' ? ''
      : a.juniorMessage || (owned ? '' : a.audience === 'agent' ? (c.statusText[a.status] || '') : str(a.message));
    return el('div', { className: 'ov-deliverable', 'data-artifact': str(a.name), 'data-status': str(a.status) }, [
      el('div', { className: 'ov-deliverable-main' }, [
        el('div', { className: 'ov-deliverable-label', text: c.deliverableLabel(str(d.label || a.label), fileName(a.path)) }),
        el('div', { className: 'ht-mono ov-path muted', text: str(a.path) }),
        el('div', { className: 'ov-deliverable-what', text: str(d.what) }),
        el('div', {}, [
          el('span', { className: `ht-status ${owned ? 'ht-st-neutral' : STATUS_CLASS[a.status] || 'ht-st-stale'}`,
            'data-status-chip': status, text: c.statusChip[status] || status }), ' ',
          a.juniorMessage && text === a.juniorMessage
            ? HT.components.engineText(text, { attrs: { className: 'ov-deliverable-status', 'data-message': true, title: a.message || null } })
            : el('span', { className: 'ov-deliverable-status', 'data-message': true, title: a.message || null, text }),
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
    if (m && (m.notebook || m.editable || m.workbench)) {
      children.push(el('div', { className: 'ov-launch', 'data-launch-info': true }, [
        el('p', { className: 'ov-launch-title', text: c.launchTitle }),
        el('p', { text: c.launchWhat }),
        m.notebook ? el('pre', { className: 'ht-mono', 'data-launch': 'notebook', text: m.notebook }) : null,
        m.editable ? el('pre', { className: 'ht-mono', 'data-launch': 'editable', text: m.editable }) : null,
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
    return el('div', { className: 'ov-deliverables', 'data-ov': 'deliverables' }, children);
  }

  // --- Health (§6.1.5): only when something is wrong -----------------------------------------

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

  /** The findings of the check read (HE-3), as a list; To handle shows the errors (TODO-4). */
  function findingsList(ctx, findings) {
    const c = copy();
    return findings.length ? el('ul', { className: 'ov-findings', 'data-findings': true }, findings.map(f => findingItem(f, ctx)))
      : el('p', { className: 'muted', text: c.checksNone });
  }

  /** "Checks of the deliverables" (v1): a fold of the page; opening it reads `check` (§5). */
  function checks(model, ctx) {
    const c = copy();
    return ctx.fold('checks', { summary: checksSummary(model, ctx), className: 'ov-checks', attrs: { 'data-check': true },
      summaryAttrs: { 'data-check-summary': true } }, () => {
      const got = ctx.data('check');
      const error = ctx.error('check');
      const fresh = ctx.fresh(got);
      if (!fresh) askOnce(ctx, 'check');
      if (error && !fresh) {
        return el('div', { className: 'card alert', role: 'alert', 'data-check-error': true }, [
          el('p', { className: 'title', text: c.checksFailed }),
          el('p', { text: str(error.message) }),
          error.detail ? el('pre', { text: str(error.detail) }) : null,
          el('button', { type: 'button', className: 'secondary', text: c.retry, onclick: () => { ctx.retry('check'); ctx.load('check'); } }),
        ]);
      }
      if (!got) return el('p', { className: 'muted', 'aria-busy': 'true', 'data-check-loading': true, text: c.checksRunning });
      const list = findingsList(ctx, arr(got.model.findings));
      // Older findings are dimmed while the new ones are read; no "Updating" next to current content.
      return fresh ? list : el('div', { className: 'ht-stale', 'aria-busy': 'true', 'data-updating': 'check' }, [list]);
    });
  }

  // --- registration -------------------------------------------------------------------------

  // The one page (ADR 0004 d13): the Overview tab is gone; its parts are placed by
  // media/views/page.js: since your last visit (§6.4), the deliverables (§6.7.4) with the
  // checks (TODO-4), and the outcome of Regenerate (W5).
  HT.register('overview', { stage: 'v0', outcomes: ['W5'] });
  HT.parts = HT.parts || {};
  HT.parts.overview = {
    since: ctx => sinceSection(ctx.snapshot, ctx),
    deliverables: ctx => deliverables(ctx.snapshot, ctx),
    findings: (ctx, list) => findingsList(ctx, list),
    renderOutcomeW5,
  };

  // Test hook: the view-local state (not persisted, not a study fact).
  HT._overview = local;
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
