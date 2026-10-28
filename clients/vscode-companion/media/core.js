// Webview runtime of the study panel: the one page of ADR 0004 decision 13
// (COMPANION-ADVANCED §4, §8, §10, §12, §13). It owns the state of the page, the render loop,
// the folds and the focus kept across re-renders (FOLD-1 to FOLD-3, FOCUS-1 to FOCUS-4), the
// panel theme (THEME-1 to THEME-5), the language (LANG-1), the popovers of the sticky header
// (PG-14), navigation to an anchor (§4.3), the live region, the modal and tooltip hosts, the
// message whitelist, and the vscode.setState helpers (§10). What the page shows is drawn by
// media/views/page.js from the page model (lib/models/page.js, `Hypotrail.pageModel`); the
// other views register parts that the page places (figures, cards, drawers). Views never call
// acquireVsCodeApi, never parse study text as HTML, and never set a `style` attribute.
//
// Public API (ARCHITECTURE.md):
//   Hypotrail.el(tag, attrs, children)      Hypotrail.svg(tag, attrs, children)
//   Hypotrail.register(name, {stage, views?, outcomes?, render?(model, ctx), onMessage?})
//   Hypotrail.send(message)                 Hypotrail.modal({title, body, actions})
//   Hypotrail.tooltip.attach(target, contentFn)   Hypotrail.navigate({anchor, kind?, id?})
//   Hypotrail.renderOutcome(outcome)        Hypotrail.PALETTE
//   Hypotrail.start()                       (called once by the document, after every view)
(function (HT) {
  'use strict';
  const P = () => HT.protocol;
  const C = () => HT.copy.core;
  const PALETTE = ['accent', 'baseline', 'muted', 'fg', 'warn', 'error', 'done', 'experiment', 'border', 'bg',
    'surface', 'link', 'none'];
  const SVG_NS = ['http:', '', 'www.w3.org', '2000', 'svg'].join('/');
  // §10: the only setState keys. `folds` (FOLD-1) and `theme` (THEME-2) are the one page's;
  // `tab`, `recapCollapsed`, `evidenceFilter`, `selectedResult` of the tabbed panel are dropped.
  const UI_KEYS = ['askDraft', 'folds', 'study', 'language', 'theme'];
  const LANGUAGES = ['en', 'fr'];
  const THEMES = ['auto', 'dark', 'light'];
  const MAX_FOLDS = 300;
  // The keys that belong to one study (decision CR.2): dropped when `init` names another.
  const STUDY_KEYS = ['askDraft', 'folds'];
  // Messages the frame handles itself; the others (effects, preview_policy_result,
  // draft_result, learn_state) are only forwarded to the views' onMessage.
  const CORE_TYPES = ['init', 'snapshot', 'view_data', 'load_error', 'busy', 'outcome', 'notice', 'navigate'];

  let api = null;
  const views = [];
  const diagnostics = { dropped: 0, ignored: 0 };
  const state = {
    init: { stage: 'v0', reviewer: false, learningLayer: true, chatInsert: false, task: null, language: 'auto', panelContract: null,
      surface: 'panel' },
    snapshot: null, raw: null, snapshotLanguage: null, localizedFrom: null, data: {}, errors: {}, busy: null, outcomes: {}, lastOutcome: null,
    loadError: null, notice: null, lastRead: null, requested: {}, pendingNav: null, popover: null, copied: null,
    epoch: 0, loadEpoch: {},
  };
  let ui = {};
  let root = null;
  let ageNode = null;
  let rendering = false;

  // --- DOM helpers ----------------------------------------------------------------------

  function setAttrs(node, attrs, isSvg) {
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === 'style' || k === 'innerHTML' || k === 'outerHTML' || k === 'html' || k === 'srcdoc') {
        throw new Error(`attribute ${k} is not allowed`);
      }
      if (k === 'text') node.textContent = String(v);
      else if (k === 'className' || k === 'class') for (const name of String(v).split(/\s+/).filter(Boolean)) node.classList.add(name);
      else if (k === 'css') for (const [p, value] of Object.entries(v)) node.style.setProperty(p, String(value));
      else if (k.startsWith('on')) {
        if (typeof v !== 'function') throw new Error(`${k} must be a function`);
        node.addEventListener(k.slice(2), v);
      } else if (isSvg && (k === 'fill' || k === 'stroke')) {
        if (typeof v === 'string' && /^url\(#ht-[a-z0-9-]+\)$/.test(v)) node.setAttribute(k, v);
        else if (PALETTE.includes(v)) node.classList.add(`ht-${k}-${v}`);
        else throw new Error(`${k} must be a palette colour, not ${v}`);
      } else node.setAttribute(k, v === true ? '' : String(v));
    }
  }

  function append(node, children) {
    for (const child of children || []) {
      if (child === null || child === undefined || child === false) continue;
      if (Array.isArray(child)) append(node, child);
      else node.appendChild(typeof child === 'string' || typeof child === 'number' ? document.createTextNode(String(child)) : child);
    }
    return node;
  }

  /** An HTML element; text is always a text node (INV-9). */
  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    setAttrs(node, attrs, false);
    return append(node, children);
  }

  /** An SVG element; geometry by attributes, colour by palette name (§12). */
  function svg(tag, attrs, children) {
    const node = document.createElementNS(SVG_NS, tag);
    setAttrs(node, attrs, true);
    return append(node, children);
  }

  // --- language (LANG-1; v0.3, WP-E2, R21) ---------------------------------------------------

  let english = null;
  let applied = null;

  function isPlain(x) {
    return Boolean(x) && typeof x === 'object' && !Array.isArray(x);
  }
  function merged(en, fr) {
    if (!isPlain(en) || !isPlain(fr)) return fr === undefined ? en : fr;
    const out = {};
    for (const k of Object.keys(en)) out[k] = Object.prototype.hasOwnProperty.call(fr, k) ? merged(en[k], fr[k]) : en[k];
    return out;
  }

  /** The panel language: the "more" menu's choice, else the setting, else the study language. */
  function language() {
    if (LANGUAGES.includes(ui.language)) return ui.language;
    const setting = state.init.language;
    if (LANGUAGES.includes(setting)) return setting;
    return studyLanguage();
  }
  function studyLanguage() {
    const snap = state.raw || state.snapshot;
    const l = snap && snap.language;
    return LANGUAGES.includes(l) ? l : 'en';
  }

  function textsLanguage() {
    const snap = state.snapshot;
    return snap && LANGUAGES.includes(snap.textsLanguage) ? snap.textsLanguage : studyLanguage();
  }

  /**
   * L3 (R4, D4b): the snapshot with the engine's junior texts in `lang`, from the engine's
   * own `texts` tables. Nothing is translated here. Without `texts` the snapshot is shown as sent.
   */
  function localize(snap, lang) {
    if (!snap || !snap.texts || !snap.texts[lang]) return snap;
    const T = snap.texts[lang];
    const pick = (table, id, fallback) => (table && typeof table[id] === 'string' ? table[id] : fallback);
    const title = s => (s ? { ...s, title: pick(T.plan, s.id, s.title) } : s);
    const shown = snap.language || 'en';
    const out = { ...snap, textsLanguage: lang };
    out.plan = (snap.plan || []).map(s => ({ ...title(s), after: title(s.after) }));
    out.currentStep = title(snap.currentStep);
    out.moments = (snap.moments || []).map(m => ({ ...m, title: pick(T.moments, m.id, m.title) }));
    out.proposals = (snap.proposals || []).map(p => {
      const own = pick(T.proposals, p.proposalId, null);
      return { ...p, decisionTitle: pick(T.plan, p.decisionId, p.decisionTitle), restatement: own || p.restatement,
        restatementLang: own ? lang : shown };
    });
    out.holds = (snap.holds || []).map(h => ({ ...h, decisionTitle: pick(T.plan, h.decisionId, h.decisionTitle) }));
    const next = snap.nextAction || {};
    out.nextAction = { ...next, juniorMessage: T.next_action || next.juniorMessage,
      choiceOptions: (next.choiceOptions || []).map(o => ({ ...o, label: pick(T.choice_options, o.id, o.label) })) };
    const limit = i => ({ ...i, juniorText: i.id === 'outcome_unknown' ? T.next_action || i.juniorText : pick(T.limits, i.id, i.juniorText) });
    const nyd = snap.notYetDefensible || { top: [], more: [] };
    out.notYetDefensible = { ...nyd, top: (nyd.top || []).map(limit) };
    out.alerts = (snap.alerts || []).map(limit);
    out.artifacts = (snap.artifacts || []).map(a => ({ ...a, juniorMessage: pick(T.artifacts, a.name, a.juniorMessage) }));
    out.recapJunior = Array.isArray(snap.recapJunior) && snap.recapJunior.length && Array.isArray(T.recap) && T.recap.length
      ? T.recap.slice() : snap.recapJunior;
    out.digest = snap.digest ? { ...snap.digest, items: (snap.digest.items || []).map(i =>
      ({ ...i, juniorText: pick(T.digest, String(i.revision), i.juniorText) })) } : snap.digest;
    const goal = {};
    for (const [k, v] of Object.entries(snap.goal || {})) {
      goal[k] = v && typeof v === 'object' ? { ...v, value: pick(T.goal, k, v.value) } : v;
    }
    out.goal = goal;
    return out;
  }

  function applyLanguage() {
    const lang = language();
    if (!english) english = { ...HT.copy };
    if (applied !== lang) {
      const fr = HT.copyFr || {};
      for (const [ns, en] of Object.entries(english)) HT.copy[ns] = lang === 'fr' && fr[ns] ? merged(en, fr[ns]) : en;
      applied = lang;
    }
    if (state.raw && (state.snapshot === null || state.snapshotLanguage !== lang || state.localizedFrom !== state.raw)) {
      state.snapshot = localize(state.raw, lang);
      state.snapshotLanguage = lang;
      state.localizedFrom = state.raw;
    }
    document.documentElement.setAttribute('lang', lang);
  }

  function setLanguage(lang) {
    if (!LANGUAGES.includes(lang)) return;
    uiState.set('language', lang);
    render();
  }

  /**
   * French typography (owner charter): a narrow no-break space before ; : ? ! » and after «,
   * applied to the page's text nodes when the panel is in French (code and figures untouched).
   */
  const NNBSP = ' ';
  function frenchSpaces(node) {
    if (language() !== 'fr' || !node) return;
    const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
    const fix = [];
    while (walker.nextNode()) {
      const t = walker.currentNode;
      const p = t.parentElement;
      // The engine's own texts stay byte for byte (NOW-1): only the panel's copy is set.
      if (!p || p.closest('code, pre, .ht-mono, data, svg, textarea, option, [data-verbatim]')) continue;
      if (/[  ]([;:?!»])|« /.test(t.nodeValue)) fix.push(t);
    }
    for (const t of fix) t.nodeValue = t.nodeValue.replace(/[  ]([;:?!»])/g, `${NNBSP}$1`).replace(/« /g, `«${NNBSP}`);
  }

  // --- theme (THEME-1 to THEME-5) ------------------------------------------------------------

  function theme() {
    return THEMES.includes(ui.theme) ? ui.theme : 'auto';
  }
  /** High Contrast is the editor's (or the system's): it overrides the panel theme (THEME-4). */
  function highContrast() {
    const b = document.body;
    const forced = typeof matchMedia === 'function' && matchMedia('(forced-colors: active)').matches;
    return Boolean(b && (b.classList.contains('vscode-high-contrast') || b.classList.contains('vscode-high-contrast-light'))) || forced;
  }
  function applyTheme() {
    if (document.body) document.body.setAttribute('data-theme', theme());
  }
  function setTheme(value) {
    if (!THEMES.includes(value)) return;
    uiState.set('theme', value === 'auto' ? undefined : value);
    applyTheme();
    render();
  }

  // --- state helpers ----------------------------------------------------------------------

  function keep() {
    try { api.setState(ui); } catch (_) { /* no state */ }
  }
  const uiState = {
    get: key => (UI_KEYS.includes(key) ? ui[key] : undefined),
    set(key, value) {
      if (!UI_KEYS.includes(key)) throw new Error(`setState key ${key} is not allowed`);
      if (value === undefined) delete ui[key]; else ui[key] = value;
      keep();
    },
  };

  /** Keep the setState keys of §10 only, each value of its form; older keys are dropped. */
  function sanitize() {
    if (!ui || typeof ui !== 'object' || Array.isArray(ui)) ui = {};
    for (const key of Object.keys(ui)) if (!UI_KEYS.includes(key)) delete ui[key];
    if (typeof ui.askDraft !== 'string') delete ui.askDraft;
    if (ui.study !== undefined && !(typeof ui.study === 'string' && /^[0-9a-f]{16}$/.test(ui.study))) delete ui.study;
    if (ui.language !== undefined && !LANGUAGES.includes(ui.language)) delete ui.language;
    if (ui.theme !== undefined && !['dark', 'light'].includes(ui.theme)) delete ui.theme;
    if (ui.folds !== undefined) {
      if (!isPlain(ui.folds)) delete ui.folds;
      else {
        const entries = Object.entries(ui.folds).filter(([k, v]) => typeof k === 'string' && k.length <= 200 && typeof v === 'boolean');
        ui.folds = Object.fromEntries(entries.slice(-MAX_FOLDS));
      }
    }
  }

  /** `init` names the study (CR.2): the question draft and the folds of another study are dropped. */
  function bindStudy(study) {
    if (typeof study !== 'string' || ui.study === study) return;
    for (const key of STUDY_KEYS) delete ui[key];
    ui.study = study;
    keep();
  }

  // --- folds (FOLD-1 to FOLD-3) ---------------------------------------------------------------

  /** The kept state of a fold, or undefined when the junior never set it (its default applies). */
  function foldState(id) {
    const f = ui.folds;
    return f && Object.prototype.hasOwnProperty.call(f, id) ? f[id] : undefined;
  }
  function setFold(id, open) {
    const folds = { ...(ui.folds || {}) };
    delete folds[id];
    folds[id] = open === true;
    const keys = Object.keys(folds);
    for (const k of keys.slice(0, Math.max(0, keys.length - MAX_FOLDS))) delete folds[k];
    uiState.set('folds', folds);
  }
  const isOpen = (id, dflt) => {
    const kept = foldState(id);
    return kept === undefined ? Boolean(dflt) : kept;
  };

  /**
   * A fold of the page: `<details data-fold-id>` whose open state is kept (FOLD-1). Its body
   * (`content()`) is built only while it is open, so a closed fold reads nothing (§5, §11);
   * opening it re-renders the page with the body. `summary` is text or nodes.
   */
  function fold(id, { summary, open = false, className = '', attrs = {}, summaryAttrs = {} }, content) {
    const opened = isOpen(id, open);
    const node = el('details', { className, 'data-fold-id': id, 'data-fold-default': open ? 'open' : 'closed',
      'data-lazy': typeof content === 'function' ? 'true' : null, open: opened ? true : null, ...attrs }, [
      el('summary', { 'data-focus-id': `fold:${id}`, ...summaryAttrs }, Array.isArray(summary) ? summary : [summary]),
    ]);
    if (opened && typeof content === 'function') append(node, [content()]);
    else if (content && typeof content !== 'function') append(node, [content]);
    return node;
  }

  function onToggle(e) {
    const d = e.target;
    if (rendering || !(d instanceof HTMLDetailsElement)) return;
    const id = d.getAttribute('data-fold-id');
    if (!id) return;
    const dflt = d.getAttribute('data-fold-default') === 'open';
    if (d.open === isOpen(id, dflt)) return;
    setFold(id, d.open);
    // A lazy fold builds its body when it opens (and drops it when it closes).
    if (d.getAttribute('data-lazy') === 'true') render();
  }

  /**
   * Every `details` of the page carries a stable fold id (FOLD-1), and every focusable
   * element a stable focus id (FOCUS-1): the ones a view did not name get one from their
   * place, the nearest named ancestor (fold, anchor, block) and their rank inside it.
   */
  /**
   * WP-A5: every table can turn into cards on a narrow panel (core.css, below 600 px): each
   * body cell gets its column's head text as `data-label`. Text only, set as an attribute. A
   * table in a region that scrolls on purpose (the sample, `data-scroll-ok`) stays a table.
   */
  function cardTables(node) {
    for (const table of node.querySelectorAll('table')) {
      if (table.closest('[data-scroll-ok]')) continue;
      const heads = [...table.querySelectorAll('thead th')].map(th => th.textContent.trim());
      table.classList.add('ht-cardable');
      for (const row of table.querySelectorAll('tbody tr')) {
        [...row.children].forEach((cell, i) => { if (heads[i] !== undefined) cell.setAttribute('data-label', heads[i]); });
      }
    }
  }

  function nameRest(node) {
    const owner = n => {
      const a = n.parentElement && n.parentElement.closest('[data-fold-id], [data-anchor], [data-block], [data-drawer]');
      return a ? (a.getAttribute('data-fold-id') || a.getAttribute('data-anchor') || a.getAttribute('data-block')
        || a.getAttribute('data-drawer')) : 'page';
    };
    const ranks = {};
    for (const d of node.querySelectorAll('details:not([data-fold-id])')) {
      const key = `${owner(d)}~d`;
      ranks[key] = (ranks[key] || 0) + 1;
      const id = `${key}${ranks[key]}`;
      d.setAttribute('data-fold-id', id);
      d.setAttribute('data-fold-default', d.open ? 'open' : 'closed');
      const kept = foldState(id);
      if (kept !== undefined && kept !== d.open) d.open = kept;
    }
    const FOCUSABLE = 'button, summary, select, input, textarea, [tabindex="0"], [tabindex="-1"][data-anchor]';
    for (const n of node.querySelectorAll(FOCUSABLE)) {
      if (n.hasAttribute('data-focus-id')) continue;
      const tag = n.tagName.toLowerCase();
      const hint = n.getAttribute('data-copy-question') || n.getAttribute('data-term') || n.getAttribute('data-write')
        || n.getAttribute('data-open') || n.getAttribute('data-marimo') || '';
      const key = `${owner(n)}~${tag}${hint ? `:${hint}` : ''}`;
      ranks[key] = (ranks[key] || 0) + 1;
      n.setAttribute('data-focus-id', `${key}${ranks[key]}`);
    }
  }

  // --- currency (decision CR.1) ---------------------------------------------------------

  function version() {
    const snap = state.snapshot;
    return snap ? `${snap.revision}:${snap.currency || ''}:${state.epoch}` : '';
  }

  function fresh(entry) {
    const snap = state.snapshot;
    if (!entry || !snap || !Number.isInteger(entry.revision)) return false;
    if (entry.revision > snap.revision) return true;
    return entry.revision === snap.revision && (entry.currency || '') === (snap.currency || '') &&
      (entry.epoch === undefined ? 0 : entry.epoch) === state.epoch;
  }

  function stamp(m, epoch = state.epoch) {
    return { revision: m.revision, currency: m.currency || '', epoch };
  }

  /** The junior's explicit Refresh (the "more" menu, the load-error Retry): every open block reads again. */
  function refreshAll() {
    state.epoch += 1;
    state.requested = {};
    send({ type: 'refresh' });
  }

  const rank = s => P().stageRank(s);
  const atLeast = s => P().stageAllows(state.init.stage, s);

  /** Send one whitelisted, validated message to the extension. */
  function send(message) {
    const env = P().envelope(message.type, Object.fromEntries(Object.entries(message).filter(([k]) => k !== 'type')));
    const valid = P().validateIncoming(env);
    if (!valid) {
      diagnostics.dropped += 1;
      return false;
    }
    if (valid.type === 'load') state.loadEpoch[valid.view] = state.epoch;
    api.postMessage(valid);
    return true;
  }

  function register(name, def) {
    if (views.some(v => v.name === name)) throw new Error(`view ${name} is registered twice`);
    if (rank(def.stage) < 0) throw new Error(`view ${name} has an unknown stage`);
    views.push({ name, views: [], outcomes: [], ...def });
  }

  // --- outcome rendering (v0, INV-8) --------------------------------------------------------

  function renderOutcome(o) {
    if (!o) return null;
    const c = C();
    const str = x => (typeof x === 'string' ? x : '');
    if (o.kind === 'refused' && o.refusal) {
      const r = o.refusal;
      const fr = language() === 'fr' && typeof r.humanFr === 'string';
      const lines = fr && Array.isArray(r.detailsFr) ? r.detailsFr : r.details || [];
      return el('div', { className: 'card alert', role: 'alert', 'data-outcome': 'refused', 'data-op': o.op,
        'data-code': str(r.code), 'data-reason': str(r.reason) }, [
        el('p', { className: 'title', text: c.refusedTitle(str(r.code), r.reason) }),
        el('p', { text: str(fr ? r.humanFr : r.human), 'data-human': true, lang: fr ? 'fr' : null }),
        el('p', { className: 'muted', text: c.engineVerbatim }),
        el('blockquote', { text: str(r.engineMessage), 'data-engine-message': true }),
        lines.length ? el('ul', {}, lines.map(line => el('li', { text: str(line) }))) : null,
        o.message ? el('p', { text: o.message }) : null,
      ]);
    }
    if (o.kind === 'ok' || o.kind === 'ok_with_problems' || o.kind === 'not_promoted') {
      const rec = o.recorded || {};
      const title = o.kind === 'ok' ? c.done[o.op] : o.kind === 'not_promoted' ? c.notPromotedTitle : c.problemsTitle;
      return el('div', { className: 'card success', role: 'status', 'data-outcome': o.kind, 'data-op': o.op }, [
        el('p', { className: 'title', text: title }),
        typeof rec.userWords === 'string' ? el('p', {}, [c.recordedWords, el('q', { text: rec.userWords })]) : null,
        (o.artifacts || []).length ? el('ul', {}, o.artifacts.map(a => el('li', { text: str(a.message) }))) : null,
        o.message ? el('p', { text: o.message }) : null,
      ]);
    }
    const title = o.kind === 'failed' ? c.failedTitle : o.kind === 'cancelled' ? c.cancelledTitle : c.invalidTitle;
    return el('div', { className: 'card alert', role: 'alert', 'data-outcome': str(o.kind), 'data-op': o.op }, [
      el('p', { className: 'title', text: title }),
      o.message ? el('p', { text: str(o.message) }) : null,
    ]);
  }

  // --- modal and tooltip hosts ----------------------------------------------------------------

  let modalOpen = null;
  function modal({ title, body, actions }) {
    if (modalOpen) modalOpen.close(null);
    const opener = document.activeElement;
    return new Promise(resolve => {
      const id = `modal-title-${Date.now()}`;
      const buttons = (actions || []).map(a => el('button', { type: 'button', className: a.primary ? '' : 'secondary',
        'data-modal-action': String(a.value), text: a.label, onclick: () => close(a.value) }));
      buttons.push(el('button', { type: 'button', className: 'secondary', text: C().modalCancel, onclick: () => close(null) }));
      const dialog = el('div', { className: 'ht-modal', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': id }, [
        el('h2', { id, text: title }), el('div', {}, [body]), el('div', { className: 'ht-actions' }, buttons)]);
      const overlay = el('div', { className: 'ht-overlay' }, [dialog]);
      function close(value) {
        overlay.remove();
        modalOpen = null;
        if (opener && typeof opener.focus === 'function') opener.focus();
        resolve(value);
      }
      overlay.addEventListener('keydown', e => {
        if (e.key === 'Escape') { e.preventDefault(); close(null); }
        if (e.key === 'Tab') {
          const items = [...dialog.querySelectorAll('button, textarea, input, select, [tabindex="0"]')];
          const first = items[0]; const last = items[items.length - 1];
          if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
          else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
        }
      });
      document.body.appendChild(overlay);
      modalOpen = { close };
      (buttons[0] || dialog).focus();
    });
  }

  let tooltipCount = 0;
  const tooltip = {
    attach(target, contentFn) {
      tooltipCount += 1;
      const id = `ht-tooltip-${tooltipCount}`;
      let tip = null;
      const hide = () => { if (tip) { tip.remove(); tip = null; } };
      const show = () => {
        hide();
        tip = el('div', { id, role: 'tooltip', className: 'ht-tooltip' }, [contentFn()]);
        target.after(tip);
      };
      target.setAttribute('aria-describedby', id);
      if (!target.hasAttribute('tabindex') && !/^(BUTTON|A|INPUT|SELECT|TEXTAREA)$/.test(target.tagName)) target.setAttribute('tabindex', '0');
      target.addEventListener('mouseenter', show);
      target.addEventListener('focus', show);
      target.addEventListener('mouseleave', hide);
      target.addEventListener('blur', hide);
      target.addEventListener('keydown', e => { if (e.key === 'Escape') hide(); });
      return target;
    },
  };

  // --- navigation (§4.3, NAV-1, FOLD-3) --------------------------------------------------------

  /** The folds that hold an anchor: its phase, its step, its figure, or its drawer. */
  function foldsOf(anchor, page) {
    const out = [];
    const m = String(anchor || '').match(/^path:([a-z_]+)(?:\/(.+))?$/);
    if (m && page) {
      const phase = page.path.phases.find(p => p.steps.some(s => s.id === m[1]));
      if (phase && phase.kind !== 'later') out.push(`ph-${phase.moment}`);
      out.push(`st-${m[1]}`);
      if (m[2]) out.push(`fig-${m[2]}`);
    }
    if (anchor === 'path' && atLeast('v2')) out.push('ledger');
    const t = String(anchor || '').match(/^tools:([a-z]+)$/);
    if (t) out.push(`t-${t[1]}`);
    return out;
  }

  /**
   * Go to an anchor (a deep link, "go to a result...", a "See the figure" link): open every
   * fold that holds it and record them as opened (FOLD-3), then, after the render, scroll it
   * below the sticky region, focus its own heading and highlight it for 2 s (NAV-1).
   */
  function navigate(target) {
    if (!target || typeof target.anchor !== 'string') return false;
    const page = pageModel();
    for (const id of foldsOf(target.anchor, page)) setFold(id, true);
    state.pendingNav = target;
    state.popover = null;
    render();
    return true;
  }

  function applyNavigation() {
    const target = state.pendingNav;
    if (!target) return;
    state.pendingNav = null;
    const esc = s => (typeof CSS !== 'undefined' && CSS.escape ? CSS.escape(s) : s);
    let node = document.querySelector(`[data-anchor="${esc(target.anchor)}"]`);
    if (!node) node = document.querySelector('[data-anchor="path"]');
    if (!node) return;
    const heading = (node.matches('h2, h3, h4, summary') ? node : null)
      || [...node.querySelectorAll('h2, h3, h4, summary')].find(h => h.closest('[data-anchor]') === node) || node;
    if (!heading.hasAttribute('tabindex') && heading.tagName !== 'SUMMARY') heading.setAttribute('tabindex', '-1');
    const top = document.querySelector('[data-block="header"]');
    const offset = top ? top.getBoundingClientRect().height + 8 : 0;
    const y = node.getBoundingClientRect().top + window.scrollY - offset;
    window.scrollTo(0, Math.max(0, y));
    heading.focus({ preventScroll: true });
    node.classList.add('ht-highlight');
    setTimeout(() => node.classList.remove('ht-highlight'), 2000);
  }

  // --- popovers of the sticky region (PG-6, PG-14, FOCUS-3) -----------------------------------

  let popoverOpened = null;
  function togglePopover(name) {
    state.popover = state.popover === name ? null : name;
    render();
    if (!state.popover) focusOpener(name);
  }
  function closePopover() {
    const was = state.popover;
    if (!was) return;
    state.popover = null;
    render();
    focusOpener(was);
  }
  function focusOpener(name) {
    const opener = document.querySelector(`[data-popover-opener="${name}"]`);
    if (opener) opener.focus();
  }

  // --- the page --------------------------------------------------------------------------------

  /** The page model of the snapshot in the panel language, stage and mode (lib/models/page.js). */
  function pageModel() {
    if (!state.snapshot || !HT.pageModel) return null;
    return HT.pageModel.toPageModel(state.snapshot, { stage: state.init.stage, reviewer: state.init.reviewer,
      lang: language(), learningLayer: state.init.learningLayer });
  }

  function ageText() {
    const c = HT.copy.page;
    if (state.lastRead === null) return '';
    const s = Math.round((Date.now() - state.lastRead) / 1000);
    return s < 10 ? c.ageNow : s < 60 ? c.ageSeconds(s) : c.ageMinutes(Math.floor(s / 60));
  }

  function liveRegion() {
    const owned = new Set(views.flatMap(v => v.outcomes || []));
    const o = state.lastOutcome && !owned.has(state.lastOutcome.op) ? state.lastOutcome : null;
    const n = state.notice;
    return el('div', { id: 'outcome', 'aria-live': 'polite', className: 'ht-live' }, [
      n ? el('p', { className: 'hold', role: n.politeness === 'assertive' ? 'alert' : 'status', 'data-notice': true, text: n.text }) : null,
      renderOutcome(o),
    ]);
  }

  function context(view) {
    return {
      init: { ...state.init }, stage: state.init.stage, reviewer: state.init.reviewer, task: state.init.task,
      learningLayer: state.init.learningLayer, chatInsert: state.init.chatInsert,
      snapshot: state.snapshot, page: null,
      data: name => state.data[name] || null,
      error: name => state.errors[name] || null,
      busy: Boolean(state.busy), busyOp: state.busy ? state.busy.op : null, busyTarget: state.busy ? state.busy.target : null,
      send, load: (name, extra) => send({ type: 'load', view: name, ...(extra || {}) }),
      wanted: name => Boolean(state.requested[`${name}@${version()}`]) && !state.errors[name],
      /** Ask for a data view once per version (CR.1); a closed fold never calls it (§11). */
      want: name => {
        const key = `${name}@${version()}`;
        if (fresh(state.data[name]) || state.requested[key] || state.errors[name]) return;
        state.requested[key] = true;
        send({ type: 'load', view: name });
      },
      version, fresh, stamp, epoch: () => state.epoch,
      retry: name => { delete state.errors[name]; for (const k of Object.keys(state.requested)) if (k.startsWith(`${name}@`)) delete state.requested[k]; },
      ui: uiState, wordsArea,
      outcome: target => state.outcomes[target] || null,
      renderOutcome, el, svg, format: HT.format, components: HT.components, copy: HT.copy,
      gate: (stage, node) => (atLeast(stage) && node ? (rank(stage) > 0 ? node.setAttribute('data-stage', stage) : null, node) : null),
      atLeast, modal, tooltip, navigate, fold, isOpen, setFold,
      language, theme, highContrast, setTheme, setLanguage, refreshAll, ageText,
      popover: () => state.popover, togglePopover, closePopover,
      copied: () => state.copied, markCopied: id => { state.copied = id; },
      loadError: () => state.loadError, lastRead: () => state.lastRead,
      placeholder: () => el('p', { className: 'muted', 'data-placeholder': view ? view.name : '', text: C().notAvailable }),
      rerender: () => render(),
    };
  }

  /**
   * The only textarea of the panel (INV-5): the question of "Ask the agent about this".
   * It starts empty and is never filled by the panel; the only value it ever gets is the
   * junior's own draft (`askDraft`).
   */
  function wordsArea({ kind, onInput = null, ...attrs }) {
    if (kind !== 'askDraft') throw new Error('askDraft only');
    const area = el('textarea', { spellcheck: 'true', autocomplete: 'off', 'data-words': kind, ...attrs });
    area.value = String(ui.askDraft || '');
    area.addEventListener('input', () => {
      uiState.set('askDraft', area.value || undefined);
      if (onInput) onInput(area.value);
    });
    return area;
  }

  /**
   * One render of the page (§4.1): the registered page view draws the sticky region and the
   * flow from the page model. The folds, the focus (FOCUS-1, FOCUS-2) and the scroll are kept.
   */
  function render() {
    if (!root || rendering) return;
    rendering = true;
    try {
      applyLanguage();
      applyTheme();
      const active = document.activeElement;
      const focusHolder = active && active.closest ? active.closest('[data-focus-id]') : null;
      const focusId = focusHolder ? focusHolder.getAttribute('data-focus-id') : null;
      const focusBlock = focusHolder && focusHolder.closest('[data-block]') ? focusHolder.closest('[data-block]').getAttribute('data-block') : null;
      const selection = active && (active.tagName === 'TEXTAREA' || active.tagName === 'INPUT') &&
        typeof active.selectionStart === 'number' ? [active.selectionStart, active.selectionEnd] : null;
      const scroll = window.scrollY;
      const page = pageModel();
      const out = [];
      for (const v of views) {
        if (typeof v.render !== 'function' || !atLeast(v.stage)) continue;
        const ctx = context(v);
        ctx.page = page;
        try {
          out.push(v.render(state.snapshot, ctx));
        } catch (e) {
          out.push(el('p', { className: 'alert', role: 'alert', 'data-view-error': v.name, text: `${C().viewError} ${String((e && e.message) || e)}` }));
        }
      }
      root.textContent = '';
      append(root, [...out, liveRegion()]);
      // Reviewer mode: no write control, except the handoff export (decision CA.9).
      if (state.init.reviewer) for (const node of root.querySelectorAll('[data-write]:not([data-write="export"])')) node.remove();
      nameRest(root);
      cardTables(root);
      if (HT.terms && typeof HT.terms.place === 'function') HT.terms.place(root);
      frenchSpaces(root);
      ageNode = root.querySelector('[data-literal="age"]');
      window.scrollTo(0, scroll);
      if (state.popover && popoverOpened !== state.popover) {
        const pop = root.querySelector('[data-popover]');
        if (pop) pop.focus();
      } else if (focusId) {
        const esc = s => (typeof CSS !== 'undefined' && CSS.escape ? CSS.escape(s) : s);
        const again = root.querySelector(`[data-focus-id="${esc(focusId)}"]`)
          || (focusBlock ? root.querySelector(`[data-block="${esc(focusBlock)}"] h2, [data-block="${esc(focusBlock)}"] h1`) : null);
        if (again) {
          if (!again.hasAttribute('tabindex') && /^H[1-6]$/.test(again.tagName)) again.setAttribute('tabindex', '-1');
          again.focus({ preventScroll: true });
          if (selection && typeof again.setSelectionRange === 'function') again.setSelectionRange(selection[0], selection[1]);
        }
      }
      popoverOpened = state.popover;
    } finally {
      rendering = false;
    }
    applyNavigation();
  }

  // --- incoming messages ------------------------------------------------------------------

  function onSnapshot(m) {
    const before = state.snapshot ? state.snapshot.revision : null;
    if (before !== m.model.revision) { state.notice = null; state.copied = null; }
    state.raw = m.model;
    state.snapshot = localize(m.model, language());
    state.snapshotLanguage = language();
    state.localizedFrom = m.model;
    state.loadError = null;
    state.lastRead = Date.now();
  }

  function onMessage(event) {
    const m = P().validateOutgoing(event.data);
    if (!m) { diagnostics.ignored += 1; return; }
    let redraw = true;
    switch (m.type) {
      case 'init':
        bindStudy(m.study);
        state.init = { stage: m.stage, reviewer: m.reviewer, learningLayer: m.learningLayer, chatInsert: m.chatInsert, task: m.task,
          marimo: m.marimo || null, language: m.language || 'auto',
          panelContract: Number.isInteger(m.panelContract) ? m.panelContract : null,
          // Lot P (R51): the read-only What if? editor tab draws What if? only.
          surface: m.surface === 'whatif' ? 'whatif' : 'panel' };
        break;
      case 'snapshot': onSnapshot(m); break;
      case 'view_data':
        state.data[m.view] = { ...stamp(m, state.loadEpoch[m.view] === undefined ? state.epoch : state.loadEpoch[m.view]),
          model: m.model, resultId: m.resultId || null };
        delete state.errors[m.view];
        for (const k of Object.keys(state.requested)) {
          if (k.startsWith(`${m.view}@`) && k !== `${m.view}@${version()}`) delete state.requested[k];
        }
        break;
      case 'load_error':
        if (m.view === null) state.loadError = { message: m.message, detail: m.detail };
        else state.errors[m.view] = { message: m.message, detail: m.detail };
        break;
      case 'busy': state.busy = m.busy ? { op: m.op, target: m.target || null } : null; break;
      case 'outcome':
        state.lastOutcome = m;
        if (m.target) state.outcomes[m.target] = m;
        state.notice = null;
        break;
      case 'notice': state.notice = { text: m.text, politeness: m.politeness }; break;
      case 'navigate': navigate(m); redraw = false; break;
      default: break;
    }
    const forwarded = !CORE_TYPES.includes(m.type);
    for (const v of views) {
      if (typeof v.onMessage !== 'function') continue;
      try {
        if (v.onMessage(m, context(v)) === false && forwarded) redraw = false;
      } catch (_) { /* a view error never breaks the page */ }
    }
    if (redraw) render();
  }

  function start() {
    if (api) return;
    api = acquireVsCodeApi();
    try { ui = api.getState() || {}; } catch (_) { ui = {}; }
    sanitize();
    keep();
    root = document.getElementById('app');
    window.addEventListener('message', onMessage);
    document.addEventListener('toggle', onToggle, true);
    // PG-14: Escape closes a popover (focus back on its button); a click outside closes it.
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && state.popover) { e.preventDefault(); closePopover(); } });
    document.addEventListener('click', e => {
      if (!state.popover || !e.target || !e.target.closest) return;
      if (e.target.closest('[data-popover]') || e.target.closest('[data-popover-opener]')) return;
      closePopover();
    });
    setInterval(() => { if (ageNode) ageNode.textContent = ageText(); }, 15000);
    render();
    send({ type: 'ready' });
  }

  /** The registered views, read-only: {name, stage} (tests and diagnostics). */
  const registered = () => views.map(v => ({ name: v.name, stage: v.stage }));

  Object.assign(HT, { el, svg, wordsArea, register, send, modal, tooltip, navigate, renderOutcome, start, PALETTE, SVG_NS,
    diagnostics, registered, _state: state, fresh, version, language, studyLanguage, LANGUAGES, THEMES,
    textsLanguage, localize, fold, currentPage: pageModel, theme, highContrast, foldOpen: isOpen, setFold, rerender: () => render() });
  HT.components = HT.components || {};
  HT.copy = HT.copy || {};
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
