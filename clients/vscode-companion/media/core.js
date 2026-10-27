// Webview runtime of the study panel (COMPANION-ADVANCED §4, §8, §12, §13). It owns the
// frame (header, the views' band above the tabs, tabs, the sticky position line, alert
// strip, recap strip, footer; each tab's "At this step" and "Next" lines, lesson style
// 2026-10-27), the live region, the modal and tooltip hosts, the message whitelist, and
// the vscode.setState helpers. Views register
// with Hypotrail.register and render models; they never call acquireVsCodeApi, never
// parse study text as HTML, and never set a `style` attribute (the CSP forbids it).
//
// Frozen by WP-0. The public API (ARCHITECTURE.md) is:
//   Hypotrail.el(tag, attrs, children)      Hypotrail.svg(tag, attrs, children)
//   Hypotrail.register(name, {tab, stage, views?, outcomes?, render(model, ctx), onMessage?, band?(model, ctx)})
//   Hypotrail.send(message)                 Hypotrail.modal({title, body, actions})
//   Hypotrail.tooltip.attach(target, contentFn)   Hypotrail.navigate({tab, kind, id})
//   Hypotrail.renderOutcome(outcome)        Hypotrail.PALETTE
//   Hypotrail.start()                       (called once by the document, after every view)
(function (HT) {
  'use strict';
  const P = () => HT.protocol;
  const C = () => HT.copy.core;
  // Fixed palette of chart marks (§12): SVG `fill`/`stroke` take one of these names and
  // become classes `ht-fill-<name>` / `ht-stroke-<name>`, coloured by tokens.css.
  const PALETTE = ['accent', 'baseline', 'muted', 'fg', 'warn', 'error', 'done', 'experiment', 'border', 'bg',
    'surface', 'link', 'none'];
  // The SVG namespace is an identifier, not a resource: it is assembled here so that the
  // document holds no URL literal at all (test/unit.test.js).
  const SVG_NS = ['http:', '', 'www.w3.org', '2000', 'svg'].join('/');
  // v0.3 (WP-E1): no `drafts` key any more; the confirmation words went with W1.
  // R31 (owner decision 2026-10-27): no `ackDrafts` either; the acknowledgement of an
  // interrupted execution (the former W6) is made in the chat, and the panel takes no words.
  // v0.3 (WP-E2, R21): `language`, the header's EN | FR choice (UI state only, never a study
  // write); absent, the panel follows the setting (`auto`: the study language).
  const UI_KEYS = ['askDraft', 'tab', 'recapCollapsed', 'evidenceFilter', 'selectedResult', 'study', 'language'];
  const LANGUAGES = ['en', 'fr'];
  // The keys that belong to one study (decision CR.2): dropped when `init` names another.
  const STUDY_KEYS = ['askDraft', 'selectedResult'];
  const TAB_ORDER = ['overview', 'eda', 'decisions', 'evidence', 'whatif', 'learn'];
  // Messages the frame handles itself; the others (effects, preview_policy_result,
  // draft_result, learn_state) are only forwarded to the views' onMessage.
  const CORE_TYPES = ['init', 'snapshot', 'view_data', 'load_error', 'busy', 'outcome', 'notice', 'navigate'];

  let api = null;
  const views = [];
  const diagnostics = { dropped: 0, ignored: 0 };
  const state = {
    init: { stage: 'v0', reviewer: false, learningLayer: true, chatInsert: false, task: null, language: 'auto' },
    snapshot: null, raw: null, snapshotLanguage: null, localizedFrom: null, data: {}, errors: {}, busy: null, outcomes: {}, lastOutcome: null,
    loadError: null, notice: null, lastRead: null, requested: {}, pendingNav: null,
    // CR.1: `epoch` counts the junior's explicit Refreshes; data read before the last one
    // is read again. `loadEpoch[view]` is the epoch at which a view's load was sent.
    epoch: 0, loadEpoch: {},
  };
  let ui = {};
  let root = null;
  let ageNode = null;

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
        // A palette name, or a reference to a pattern the component defined (the hatch).
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

  // --- language (v0.3, WP-E2, R21) -----------------------------------------------------------
  //
  // English is the source language: media/copy/*.js. A French translation of the same keys
  // lives in media/copy-fr/*.js under Hypotrail.copyFr.<view> (test/copy-fr.test.js checks that
  // every English key has one). Switching swaps each Hypotrail.copy.<view> for the English
  // object or the French one merged over it; views read Hypotrail.copy.<view> at render time.

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

  /** The panel language: the header choice, else the setting, else the study language. */
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

  /**
   * The language the summary's engine texts are shown in (L3, D4b): the panel language when
   * the engine gave them in it (`texts` of `status --summary --digest`), else the study
   * language. An engine text in another language is marked (components `engineText`).
   */
  function textsLanguage() {
    const snap = state.snapshot;
    return snap && LANGUAGES.includes(snap.textsLanguage) ? snap.textsLanguage : studyLanguage();
  }

  /**
   * L3 (owner session 2026-10-26, R4, D4b): the snapshot with the engine's junior texts in
   * `lang`, from the engine's own `texts` tables: step and moment titles, the next move, the
   * choice labels, the limits, the deliverables' lines, the recap, the digest, the goal, and
   * each proposal's restatement when the chat gave it in that language (else the one written,
   * with `restatementLang` so the view says whose wording it is). Nothing is translated here.
   * Without `texts` (an older engine, stage v0) the snapshot is shown as sent.
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
    // L3 (D4b): the engine's junior texts follow the panel language too, when the engine
    // gave them in it.
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
  // v0.3: the confirmation drafts went with W1; R31 (2026-10-27): the acknowledgement drafts
  // went with W6. The only words field left is the "Ask the agent" question (`askDraft`).

  /** Keep the setState keys of §10 only (a stored `ackDrafts` of an older panel is dropped). */
  function sanitize() {
    if (!ui || typeof ui !== 'object' || Array.isArray(ui)) ui = {};
    for (const key of Object.keys(ui)) if (!UI_KEYS.includes(key)) delete ui[key];
    if (typeof ui.askDraft !== 'string') delete ui.askDraft;
    if (ui.study !== undefined && !(typeof ui.study === 'string' && /^[0-9a-f]{16}$/.test(ui.study))) delete ui.study;
    if (ui.language !== undefined && !LANGUAGES.includes(ui.language)) delete ui.language;
  }

  /** `init` names the study (CR.2): the words and the choice of another study are dropped. */
  function bindStudy(study) {
    if (typeof study !== 'string' || ui.study === study) return;
    for (const key of STUDY_KEYS) delete ui[key];
    ui.study = study;
    keep();
  }

  /**
   * The only textarea of the panel (INV-5): the question of "Ask the agent about this",
   * which the extension copies for the chat (never a decision's or an acknowledgement's
   * words: R23 and R31). It starts empty and is never filled by the panel; the only value it
   * ever gets is the junior's own draft (`askDraft`), kept in vscode.setState while they
   * type. Views never create a textarea themselves (test/invariants.test.js). The other
   * attributes (id, aria-describedby, data-*) go on the element. `onInput(text)` runs on
   * each keystroke.
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

  // --- currency (decision CR.1) ---------------------------------------------------------

  /** The version of the snapshot the panel shows: revision, currency, and Refresh epoch. */
  function version() {
    const snap = state.snapshot;
    return snap ? `${snap.revision}:${snap.currency || ''}:${state.epoch}` : '';
  }

  /**
   * Whether data `{revision, currency?, epoch?}` was read at the snapshot's version: a
   * newer revision, or the same revision with the same currency and since the last
   * explicit Refresh. A model read at the same revision but another currency (a dataset
   * edit, a deliverable deleted or edited) is not current any more.
   */
  function fresh(entry) {
    const snap = state.snapshot;
    if (!entry || !snap || !Number.isInteger(entry.revision)) return false;
    if (entry.revision > snap.revision) return true;
    return entry.revision === snap.revision && (entry.currency || '') === (snap.currency || '') &&
      (entry.epoch === undefined ? 0 : entry.epoch) === state.epoch;
  }

  /** The stamp of a message read now: its revision and currency, and the current epoch. */
  function stamp(m, epoch = state.epoch) {
    return { revision: m.revision, currency: m.currency || '', epoch };
  }

  /** The junior's explicit Refresh (header, load-error Retry): every view reads again. */
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
    if (!TAB_ORDER.includes(def.tab)) throw new Error(`view ${name} has an unknown tab`);
    if (rank(def.stage) < 0) throw new Error(`view ${name} has an unknown stage`);
    if (typeof def.render !== 'function') throw new Error(`view ${name} has no render`);
    views.push({ name, views: [], outcomes: [], ...def });
  }

  function visibleViews() {
    return views.filter(v => atLeast(v.stage))
      .sort((a, b) => TAB_ORDER.indexOf(a.tab) - TAB_ORDER.indexOf(b.tab));
  }
  function tabs() {
    return [...new Set(visibleViews().map(v => v.tab))];
  }
  const tabbed = () => atLeast('v1');
  function activeTab() {
    const list = tabs();
    return list.includes(ui.tab) ? ui.tab : list[0];
  }

  // --- outcome rendering (v0, INV-8) --------------------------------------------------------

  function renderOutcome(o) {
    if (!o) return null;
    const c = C();
    const str = x => (typeof x === 'string' ? x : '');
    if (o.kind === 'refused' && o.refusal) {
      const r = o.refusal;
      // v0.3 (WP-K, R21): the explanation in the panel language (the engine's message stays as sent).
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
  /** A modal dialog; resolves the chosen action's value, or null (Escape, Cancel). */
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
    /** Show `contentFn()` in a tooltip on hover and focus of `target`; Escape closes it. */
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

  /** Open a tab, then scroll to and focus `[data-nav="<kind>:<id>"]` and highlight it. */
  function navigate(target) {
    if (!target || !tabs().includes(target.tab)) return false;
    uiState.set('tab', target.tab);
    state.pendingNav = target;
    render();
    return true;
  }

  function applyNavigation() {
    const target = state.pendingNav;
    if (!target) return;
    const node = document.querySelector(`[data-nav="${CSS.escape(`${target.kind}:${target.id}`)}"]`);
    if (!node) return;
    state.pendingNav = null;
    // Result cards may be collapsed to keep EDA scannable; a deep link always reveals it.
    const disclosure = node.matches('details') ? node : node.querySelector('details.eda-analysis');
    if (disclosure) disclosure.open = true;
    // Its own heading (h2 to h4, WP-I), else the first h2 or h3 inside it (a wrapper of one
    // card), else the target itself; never the h4 of a nested target.
    const heading = [...node.querySelectorAll('h2, h3, h4')].find(h => h.closest('[data-nav]') === node)
      || node.querySelector('h2, h3') || node;
    if (!heading.hasAttribute('tabindex')) heading.setAttribute('tabindex', '-1');
    node.scrollIntoView({ block: 'center' });
    heading.focus();
    node.classList.add('ht-highlight');
    setTimeout(() => node.classList.remove('ht-highlight'), 2000);
  }

  // --- frame ------------------------------------------------------------------------------

  function ageText() {
    const c = C();
    if (state.lastRead === null) return '';
    const s = Math.round((Date.now() - state.lastRead) / 1000);
    return c.readAge(s < 10 ? c.justNow : s < 60 ? c.secondsAgo(s) : c.minutesAgo(Math.floor(s / 60)));
  }

  function folderName(study) {
    const parts = String(study || '').split(/[\\/]/).filter(Boolean);
    return parts[parts.length - 1] || '';
  }

  /**
   * WP-A7: the final-test chip of the header (ADR 0006), on every tab: sealed with its row
   * count (the engine's count), opened, or "No final test" for a study created before the
   * seal. An engine without `final_test` gives no chip.
   */
  function finalTestChip(snap) {
    const ft = snap && snap.finalTest;
    if (!ft || !ft.status) return null;
    const c = C().finalTest;
    const rows = Number.isInteger(ft.rows) ? HT.format.number(ft.rows, 'int') : null;
    if (ft.status === 'sealed' && rows) {
      return el('span', { className: 'ht-status ht-st-sealed ht-seal', 'data-final-test': 'sealed', title: c.sealedTitle,
        text: c.sealed(rows) });
    }
    if (ft.status === 'opened' && rows) {
      return el('span', { className: 'ht-status ht-st-neutral ht-seal', 'data-final-test': 'opened', title: c.openedTitle,
        text: c.opened(rows) });
    }
    if (ft.status === 'absent') {
      return el('span', { className: 'ht-status ht-st-stale ht-seal', 'data-final-test': 'absent', title: c.absentTitle,
        text: c.absent });
    }
    return null;
  }

  /**
   * The band at the top of the board (lesson style, 2026-10-27): the product and the flag,
   * the language toggle, the study's name in chalk, the study switch, the revision, the read
   * age and Refresh, the chips, and "Learn more" on what these marks mean (R30).
   */
  function header() {
    const c = C();
    const snap = state.snapshot;
    ageNode = el('span', { 'data-literal': 'age', text: ageText() });
    const name = snap ? folderName(snap.study) : '';
    const chip = finalTestChip(snap);
    const L = HT.copy.lesson;
    return el('header', { className: 'ht-header' }, [
      el('h1', { className: 'sr-only', text: c.title }),
      el('div', { className: 'ht-row1' }, [
        el('span', { className: 'ht-prod', text: c.product }),
        el('span', { className: 'ht-badge', 'data-experimental': state.init.stage, text: `${c.experimental} · ${c.stage(state.init.stage)}` }),
        state.init.reviewer ? el('span', { className: 'ht-badge ht-badge-reviewer', 'data-reviewer': true, text: c.reviewer }) : null,
        el('span', { className: 'ht-spacer', 'aria-hidden': 'true' }),
        languageToggle(),
      ]),
      snap ? el('div', { className: 'ht-brand' }, [el('span', { className: 'ht-name', text: name || c.product })]) : null,
      el('div', { className: 'ht-meta' }, [
        atLeast('v1') && snap ? el('button', { type: 'button', className: 'ht-ghost', 'data-stage': 'v1',
          'data-switch-study': true, text: c.switchStudy(name), onclick: () => send({ type: 'switch_study' }) }) : null,
        state.init.task === 'regression' || (snap && snap.task === 'regression')
          ? el('span', { className: 'ht-badge', text: c.regression }) : null,
        snap ? el('span', { className: 'ht-faint', 'data-revision': snap.revision, text: c.revision(snap.revision) }) : null,
        ageNode,
        el('button', { type: 'button', className: 'ht-ghost', text: c.refresh, disabled: Boolean(state.busy),
          'data-refresh': true, onclick: refreshAll }),
      ]),
      chip ? el('div', { className: 'ht-chips-row' }, [chip]) : null,
      snap && L && HT.components.more && activeTab() === 'overview' ? HT.components.more('marks', L.more.marksTitle, [el('ul', {}, L.more.marks.map(t => el('li', {}, HT.components.parts([HT.components.marked(t)]))))]) : null,
    ]);
  }

  /** The header's EN | FR toggle (R21): UI state only, nothing is written to the study. */
  function languageToggle() {
    const c = C();
    const lang = language();
    return el('div', { className: 'ht-seg', role: 'group', 'aria-label': c.languageLabel, 'data-language-toggle': lang },
      LANGUAGES.map(l => el('button', { type: 'button', lang: l, 'aria-pressed': l === lang ? 'true' : 'false',
        'data-language': l, title: c.languageNames[l], text: l.toUpperCase(), onclick: () => setLanguage(l) })));
  }

  // --- the journey, the band, the position line (lesson style, R30) ---------------------------

  /**
   * The step the journey marks as current: the decision of the next action when it waits for
   * the junior (an open proposal, a reconfirmation), else the first step waiting for an
   * answer, else the engine's current step.
   */
  function currentStepId(snap) {
    if (!snap) return null;
    const plan = Array.isArray(snap.plan) ? snap.plan : [];
    const next = snap.nextAction || {};
    if ((next.kind === 'await_user_words' || next.kind === 'reconfirm') && next.decision && plan.some(s => s.id === next.decision)) {
      return next.decision;
    }
    const waiting = plan.find(s => s.status === 'awaiting_confirmation' || s.status === 'needs_reconfirmation');
    if (waiting) return waiting.id;
    return snap.currentStep ? snap.currentStep.id : null;
  }

  /** A step's state for the rail and the position line (never colour alone: words too). */
  function stepState(step, snap) {
    const open = (snap.proposals || []).some(p => p.decisionId === step.id);
    if (step.status === 'done' && open) return 'reopened';
    if (step.status === 'done' && step.basis === 'automatic') return 'automatic';
    return step.status;
  }

  /** {index, total, step, state, remaining: [{step, n}]} of the snapshot, or null. */
  function journeyPosition(snap) {
    const plan = snap && Array.isArray(snap.plan) ? snap.plan : [];
    if (!plan.length) return null;
    const id = currentStepId(snap);
    const i = plan.findIndex(s => s.id === id);
    const step = i >= 0 ? plan[i] : null;
    const remaining = plan.map((s, k) => ({ step: s, n: k + 1 })).filter(x => x.n - 1 > i && x.step.status !== 'done');
    return { index: i + 1, total: plan.length, step, state: step ? stepState(step, snap) : null, remaining };
  }

  /** A step's short label (the journey bar's words), else its title. */
  function shortLabel(step) {
    const labels = (HT.copy.overview && HT.copy.overview.journeyLabels) || {};
    return labels[step.id] || String(step.title || step.id);
  }

  /**
   * The views' band: what a view shows above the tabs on every tab (the Overview's journey
   * rail and the next move). A view opts in with `band(model, ctx)`; `ctx.tab` is the tab
   * shown under it.
   */
  function bandViews() {
    if (!state.snapshot) return null;
    const out = [];
    for (const v of visibleViews()) {
      if (typeof v.band !== 'function') continue;
      try {
        out.push(v.band(state.snapshot, { ...context(v), tab: activeTab() }));
      } catch (e) {
        out.push(el('p', { className: 'alert', role: 'alert', 'data-view-error': `${v.name}:band`, text: `${C().viewError} ${String((e && e.message) || e)}` }));
      }
    }
    return out.length ? el('div', { className: 'ht-band', 'data-band': true }, out) : null;
  }

  /**
   * The position line under the tabs, sticky (R30): the step and its state, the tab, what
   * remains, and a way back to the tabs.
   */
  function whereLine(current) {
    const snap = state.snapshot;
    const W = HT.copy.lesson && HT.copy.lesson.where;
    if (!snap || !W) return null;
    const pos = journeyPosition(snap);
    const kids = [];
    if (pos && pos.step) {
      kids.push(el('strong', { text: W.step(pos.index, pos.total) }), ` · ${String(pos.step.title || '')}`);
      const words = pos.state !== 'done' ? W.states[pos.state] : null;
      if (words) kids.push(el('span', { className: 'ht-wl', text: `, ${words}` }));
      kids.push(' · ');
    }
    kids.push(`${W.tab} `, el('strong', { text: C().tabs[current] }));
    if (pos && pos.remaining.length) {
      const shown = pos.remaining.slice(0, 3).map(x => `${x.n} ${shortLabel(x.step)}`).join(', ');
      kids.push(el('span', { className: 'ht-rest', text: W.rest(`${shown}${pos.remaining.length > 3 ? ', …' : ''}`) }));
    }
    kids.push(el('button', { type: 'button', className: 'ht-link', 'data-to-tabs': true, text: W.toTabs, onclick: () => {
      const tab = document.querySelector('[role="tab"][aria-selected="true"]');
      if (tab) { tab.scrollIntoView({ block: 'start' }); tab.focus(); }
    } }));
    return el('div', { className: 'ht-where', 'data-where': current, 'aria-label': W.label }, kids);
  }

  /** What "At this step" of a tab names (R29): facts of the snapshot, never a raw id. */
  function introFacts() {
    const snap = state.snapshot || {};
    const pos = journeyPosition(snap);
    return {
      step: pos && pos.step ? String(pos.step.title || '') : null,
      waits: Boolean(pos && pos.step && ['awaiting_confirmation', 'needs_reconfirmation', 'reopened', 'automatic'].includes(pos.state)),
      waiting: snap.waitingCount > 0 ? HT.format.number(snap.waitingCount, 'int') : null,
      task: snap.task || state.init.task || null,
      stage: state.init.stage,
    };
  }

  /** The "Next" line at the end of a tab (R30): the next tab of this stage, else back. */
  function transition(tab) {
    const L = HT.copy.lesson;
    const list = tabs();
    if (!L || !HT.components.trans || !tabbed() || list.length < 2) return null;
    const next = list[list.indexOf(tab) + 1];
    const go = target => () => {
      uiState.set('tab', target);
      render();
      const button = document.getElementById(`tab-${target}`);
      if (button) { button.scrollIntoView({ block: 'start' }); button.focus(); }
    };
    if (next) return HT.components.trans({ tab: next, text: L.nextLines[next], label: L.goTo(C().tabs[next]), onclick: go(next) });
    return HT.components.trans({ tab: list[0], text: L.nextLines.overview, label: L.backTo(C().tabs[list[0]]), onclick: go(list[0]), last: true });
  }

  function tablist(list, current) {
    const c = C();
    const buttons = list.map(tab => {
      const count = tab === 'decisions' && state.snapshot ? state.snapshot.waitingCount : 0;
      const stage = visibleViews().find(v => v.tab === tab).stage;
      return el('button', {
        type: 'button', role: 'tab', id: `tab-${tab}`, 'data-tab': tab, 'aria-selected': tab === current ? 'true' : 'false',
        'aria-controls': `panel-${tab}`, tabindex: tab === current ? '0' : '-1',
        'data-stage': rank(stage) > 0 ? stage : null,
        onclick: () => { uiState.set('tab', tab); render(); },
      }, [c.tabs[tab], count > 0 ? el('span', { className: 'ht-count', 'aria-label': c.waiting(count), text: String(count) }) : null]);
    });
    const nav = el('nav', { 'aria-label': c.tabsLabel }, [el('div', { role: 'tablist', className: 'ht-tabs' }, buttons)]);
    nav.addEventListener('keydown', e => {
      const i = list.indexOf(activeTab());
      const next = e.key === 'ArrowRight' ? (i + 1) % list.length : e.key === 'ArrowLeft' ? (i - 1 + list.length) % list.length
        : e.key === 'Home' ? 0 : e.key === 'End' ? list.length - 1 : -1;
      if (next < 0) return;
      e.preventDefault();
      uiState.set('tab', list[next]);
      render();
      const button = document.getElementById(`tab-${list[next]}`);
      if (button) button.focus();
    });
    return nav;
  }

  function alertStrip() {
    const snap = state.snapshot;
    if (!snap || !(snap.alerts || []).length) return null;
    // One alert per event: an unknown outcome is also listed as an interrupted execution.
    const unknown = snap.alerts.some(a => a.id === 'outcome_unknown');
    const alerts = snap.alerts.filter(a => !(unknown && a.id === 'interrupted_executions'));
    return el('section', { className: 'ht-alerts', 'aria-label': C().alertsLabel, 'data-stage': 'v1' },
      alerts.map(a => el('div', { className: 'card alert', role: 'alert', 'data-alert': a.id }, [
        // Two-layer copy (WP-A5): the junior variant, else the panel's own words for the id.
        a.juniorText ? HT.components.engineText(a.juniorText, { tag: 'p' })
          : el('p', { text: (HT.copy.junior && HT.copy.junior.limitText[a.id]) || (a.audience === 'agent' ? '' : a.text) }),
        el('button', { type: 'button', className: 'secondary', text: C().openHealth,
          onclick: () => navigate({ tab: 'overview', kind: 'limit', id: a.id }) }),
      ])));
  }

  function recapStrip() {
    const snap = state.snapshot;
    // Two-layer copy (WP-A5): the junior recap only; the agent recap is never shown here.
    const lines = Array.isArray(snap && snap.recapJunior) ? snap.recapJunior
      : snap && snap.recapAudience !== 'agent' ? snap.recap || [] : [];
    if (!lines.length) return null;
    // v0.3 (WP-E2): collapsed by default; the Overview says where the study stands.
    const collapsed = ui.recapCollapsed !== false;
    const c = C();
    return el('section', { className: 'ht-recap', 'aria-label': c.recapTitle, 'data-stage': 'v1', 'data-recap-strip': true }, [
      el('button', { type: 'button', className: 'ht-link', 'aria-expanded': collapsed ? 'false' : 'true',
        text: collapsed ? c.recapShow : c.recapHide, onclick: () => { uiState.set('recapCollapsed', !collapsed); render(); } }),
      // WP-A5: the Decided line in the panel's words (no recorded token such as a rule).
      collapsed ? null : el('ul', {}, lines.map(line => el('li', {
        'data-recap-strip-line': line.split(':')[0],
        text: line.startsWith('Decided: ') && HT.copy.junior ? HT.copy.junior.decidedLine(snap) : line }))),
    ]);
  }

  /**
   * The load error (WP-A5): it replaces the content, so nothing read before is shown as
   * current, and it says what to do next. The CLI's message and stderr are under Details.
   */
  function loadErrorBanner() {
    const e = state.loadError;
    if (!e) return null;
    const c = C();
    return el('div', { className: 'card alert ht-error-state', role: 'alert', 'data-load-error': true }, [
      el('p', { className: 'title', text: c.loadErrorTitle }),
      el('p', { 'data-next-step': true, text: c.loadErrorNext }),
      state.snapshot ? el('p', { className: 'muted', 'data-last-read': true, text: c.lastRead(state.snapshot.revision) }) : null,
      el('button', { type: 'button', text: c.retry, onclick: refreshAll }),
      el('details', { className: 'ht-details' }, [el('summary', { text: c.loadErrorDetail }),
        el('p', { 'data-error-message': true, text: e.message }), e.detail ? el('pre', { text: e.detail }) : null]),
    ]);
  }

  function liveRegion(mounted) {
    const owned = new Set(mounted.flatMap(v => v.outcomes || []));
    const o = state.lastOutcome && !owned.has(state.lastOutcome.op) ? state.lastOutcome : null;
    const n = state.notice;
    return el('div', { id: 'outcome', 'aria-live': 'polite' }, [
      n ? el('p', { className: 'hold', role: n.politeness === 'assertive' ? 'alert' : 'status', 'data-notice': true, text: n.text }) : null,
      renderOutcome(o),
    ]);
  }

  // --- view context -----------------------------------------------------------------------

  function context(view) {
    return {
      init: { ...state.init }, stage: state.init.stage, reviewer: state.init.reviewer, task: state.init.task,
      learningLayer: state.init.learningLayer, chatInsert: state.init.chatInsert,
      snapshot: state.snapshot,
      data: name => state.data[name] || null,
      error: name => state.errors[name] || null,
      busy: Boolean(state.busy), busyOp: state.busy ? state.busy.op : null, busyTarget: state.busy ? state.busy.target : null,
      send, load: (name, extra) => send({ type: 'load', view: name, ...(extra || {}) }),
      // WP-A5: ask for a data view once per version, shared with the frame's own requests
      // (another tab that needs the same view does not ask again).
      wanted: name => Boolean(state.requested[`${name}@${version()}`]) && !state.errors[name],
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
      gate: (stage, node) => (atLeast(stage) && node ? (node.setAttribute('data-stage', stage), node) : null),
      atLeast, modal, tooltip, navigate,
      placeholder: () => el('p', { className: 'muted', 'data-placeholder': view.name, text: C().notAvailable }),
      rerender: () => render(),
    };
  }

  /**
   * Ask for the data views a mounted view needs when the snapshot moved past them: a new
   * revision, a new currency, or an explicit Refresh (CR.1). A failed load is asked again
   * at the next version, or when the view's Retry calls `ctx.retry(view)`.
   */
  function requestLoads(mounted) {
    if (!state.snapshot) return;
    for (const v of mounted) {
      for (const name of v.views || []) {
        const have = state.data[name];
        const key = `${name}@${version()}`;
        if (fresh(have) || state.requested[key]) continue;
        state.requested[key] = true;
        send({ type: 'load', view: name });
      }
    }
  }

  function panel(tab, current, mounted) {
    const inTab = visibleViews().filter(v => v.tab === tab);
    const hidden = tabbed() && tab !== current;
    const node = el('section', {
      id: `panel-${tab}`, 'data-tab': tab, role: tabbed() ? 'tabpanel' : null,
      'aria-labelledby': tabbed() ? `tab-${tab}` : null, hidden: hidden ? true : null,
      'aria-busy': state.snapshot ? null : 'true', 'data-stage': rank(inTab[0].stage) > 0 ? inTab[0].stage : null,
    });
    if (hidden) return node;
    if (!state.snapshot) {
      node.appendChild(el('p', { className: 'muted', text: C().reading }));
      return node;
    }
    const lead = C().tabLeads && C().tabLeads[tab];
    for (const v of inTab) {
      mounted.push(v);
      let out;
      try {
        out = v.render(state.snapshot, context(v));
      } catch (e) {
        out = el('p', { className: 'alert', role: 'alert', 'data-view-error': v.name, text: `${C().viewError} ${String((e && e.message) || e)}` });
      }
      append(node, [out]);
    }
    // v0.3 (owner addition, I1): one lead sentence says what the tab is for, under its title;
    // lesson style (R29): then "At this step", what this step does in the study.
    const intros = HT.copy.lesson && HT.copy.lesson.intros;
    const intro = intros && intros[tab] && HT.components.intro ? HT.components.intro(intros[tab](introFacts()), { 'data-intro': tab }) : null;
    const top = [lead && tabbed() ? HT.components.lead(lead, { 'data-tab-lead': tab }) : null, intro].filter(Boolean);
    if (top.length) {
      const h2 = node.querySelector('h2');
      if (h2 && h2.parentNode === node) h2.after(...top); else node.prepend(...top);
    }
    // R30: the "Next" line at the end of the tab.
    const trans = transition(tab);
    if (trans) node.appendChild(trans);
    return node;
  }

  /**
   * WP-A5: every table can turn into cards on a narrow panel (core.css, below 600 px): each
   * body cell gets its column's head text as `data-label`. Text only, set as an attribute.
   */
  function cardTables(node) {
    for (const table of node.querySelectorAll('table')) {
      const heads = [...table.querySelectorAll('thead th')].map(th => th.textContent.trim());
      table.classList.add('ht-cardable');
      for (const row of table.querySelectorAll('tbody tr')) {
        [...row.children].forEach((cell, i) => { if (heads[i] !== undefined) cell.setAttribute('data-label', heads[i]); });
      }
    }
  }

  function render() {
    if (!root) return;
    applyLanguage();
    const focused = document.activeElement;
    const focusId = focused && focused.id ? focused.id : null;
    const selection = focused && (focused.tagName === 'TEXTAREA' || focused.tagName === 'INPUT') &&
      typeof focused.selectionStart === 'number' ? [focused.selectionStart, focused.selectionEnd] : null;
    const scroll = window.scrollY;
    const list = tabs();
    const current = activeTab();
    const mounted = [];
    const panels = state.loadError ? [] : list.map(tab => panel(tab, current, mounted));
    root.textContent = '';
    append(root, [
      header(),
      // Lesson style (2026-10-27): the journey rail and the next move above the tabs, on every
      // tab; under the tabs, the sticky position line.
      state.loadError ? null : bandViews(),
      tabbed() && list.length ? tablist(list, current) : null,
      state.loadError || !tabbed() || !list.length ? null : whereLine(current),
      // WP-A5: the Overview opens on the next move and its "Needs attention" section, so the
      // alert strip is shown on the other tabs only (nothing pushes the next move down).
      state.loadError ? null : (tabbed() && current !== 'overview' ? alertStrip() : null),
      state.loadError ? null : (tabbed() && current !== 'overview' ? recapStrip() : null),
      liveRegion(mounted),
      el('main', { id: 'main' }, state.loadError ? [loadErrorBanner()] : panels),
      el('footer', { className: 'ht-footer muted', text: C().footer }),
    ]);
    cardTables(root);
    // Reviewer mode: no write control, except the handoff export (decision CA.9).
    if (state.init.reviewer) for (const node of root.querySelectorAll('[data-write]:not([data-write="export"])')) node.remove();
    if (focusId) {
      const again = document.getElementById(focusId);
      if (again) {
        again.focus();
        if (selection && typeof again.setSelectionRange === 'function') again.setSelectionRange(selection[0], selection[1]);
      }
    }
    window.scrollTo(0, scroll);
    requestLoads(mounted);
    applyNavigation();
  }

  // --- incoming messages ------------------------------------------------------------------

  function onSnapshot(m) {
    const before = state.snapshot ? state.snapshot.revision : null;
    if (before !== m.model.revision) state.notice = null;
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
          marimo: m.marimo || null, language: m.language || 'auto' };
        break;
      case 'snapshot': onSnapshot(m); break;
      case 'view_data':
        state.data[m.view] = { ...stamp(m, state.loadEpoch[m.view] === undefined ? state.epoch : state.loadEpoch[m.view]),
          model: m.model, resultId: m.resultId || null };
        delete state.errors[m.view];
        // A request made at another version is answered (or superseded): forget it, so a
        // later return to that version asks again (WP-A5, the shared `want`).
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
        // A view that updates its own DOM for a forwarded message returns false: no re-render.
        if (v.onMessage(m, context(v)) === false && forwarded) redraw = false;
      } catch (_) { /* a view error never breaks the frame */ }
    }
    if (redraw) render();
  }

  function start() {
    if (api) return;
    api = acquireVsCodeApi();
    try { ui = api.getState() || {}; } catch (_) { ui = {}; }
    sanitize();
    // The sanitised state is kept at once, so a key of an earlier panel (the confirmation or
    // acknowledgement drafts of W1 and W6) does not outlive this load.
    keep();
    root = document.getElementById('app');
    window.addEventListener('message', onMessage);
    setInterval(() => { if (ageNode) ageNode.textContent = ageText(); }, 15000);
    render();
    send({ type: 'ready' });
  }

  /** The registered views, read-only: {name, tab, stage} (tests and diagnostics). */
  const registered = () => views.map(v => ({ name: v.name, tab: v.tab, stage: v.stage }));

  Object.assign(HT, { el, svg, wordsArea, register, send, modal, tooltip, navigate, renderOutcome, start, PALETTE, SVG_NS,
    diagnostics, registered, _state: state, TAB_ORDER, fresh, version, language, studyLanguage, LANGUAGES,
    textsLanguage, localize, currentStepId, journeyPosition, stepState });
  HT.components = HT.components || {};
  HT.copy = HT.copy || {};
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
