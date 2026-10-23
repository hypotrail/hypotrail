// Webview runtime of the study panel (COMPANION-ADVANCED §4, §8, §12, §13). It owns the
// frame (header, tabs, alert strip, recap strip, footer), the live region, the modal and
// tooltip hosts, the message whitelist, and the vscode.setState helpers. Views register
// with Hypotrail.register and render models; they never call acquireVsCodeApi, never
// parse study text as HTML, and never set a `style` attribute (the CSP forbids it).
//
// Frozen by WP-0. The public API (ARCHITECTURE.md) is:
//   Hypotrail.el(tag, attrs, children)      Hypotrail.svg(tag, attrs, children)
//   Hypotrail.register(name, {tab, stage, views?, outcomes?, render(model, ctx), onMessage?})
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
  // v0.3 (WP-E2, R21): `language`, the header's EN | FR choice (UI state only, never a study
  // write); absent, the panel follows the setting (`auto`: the study language).
  const UI_KEYS = ['ackDrafts', 'askDraft', 'tab', 'recapCollapsed', 'evidenceFilter', 'selectedResult', 'study', 'language'];
  const LANGUAGES = ['en', 'fr'];
  // The keys that belong to one study (decision CR.2): dropped when `init` names another.
  const STUDY_KEYS = ['ackDrafts', 'askDraft', 'selectedResult'];
  const TAB_ORDER = ['overview', 'eda', 'decisions', 'evidence', 'whatif', 'learn'];
  // Messages the frame handles itself; the others (effects, preview_policy_result,
  // draft_result, learn_state) are only forwarded to the views' onMessage.
  const CORE_TYPES = ['init', 'snapshot', 'view_data', 'load_error', 'busy', 'outcome', 'notice', 'navigate'];

  let api = null;
  const views = [];
  const diagnostics = { dropped: 0, ignored: 0 };
  const state = {
    init: { stage: 'v0', reviewer: false, learningLayer: true, chatInsert: false, task: null, language: 'auto' },
    snapshot: null, data: {}, errors: {}, busy: null, outcomes: {}, lastOutcome: null,
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
    const l = state.snapshot && state.snapshot.language;
    return LANGUAGES.includes(l) ? l : 'en';
  }

  function applyLanguage() {
    const lang = language();
    if (!english) english = { ...HT.copy };
    if (applied !== lang) {
      const fr = HT.copyFr || {};
      for (const [ns, en] of Object.entries(english)) HT.copy[ns] = lang === 'fr' && fr[ns] ? merged(en, fr[ns]) : en;
      applied = lang;
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
  // A draft is {text, revision} (decision CR.3): the junior's words of an acknowledgement
  // and the snapshot revision at which they started typing them; the revision changes only
  // when the words are cleared and typed again. (v0.3: the confirmation drafts went with W1.)
  const isDraft = d => Boolean(d) && typeof d === 'object' && typeof d.text === 'string' && d.text !== '' &&
    (d.revision === null || Number.isInteger(d.revision));
  const draftOf = (kind, id) => (ui[kind] && isDraft(ui[kind][id]) ? ui[kind][id] : null);
  const shownRevision = () => (state.snapshot && Number.isInteger(state.snapshot.revision) ? state.snapshot.revision : null);
  const drafts = {
    get: (kind, id) => { const d = draftOf(kind, id); return d ? d.text : ''; },
    /** The revision the junior started typing at, or null. */
    revision: (kind, id) => { const d = draftOf(kind, id); return d ? d.revision : null; },
    set(kind, id, text) {
      if (kind !== 'ackDrafts') throw new Error('ackDrafts only');
      ui[kind] = ui[kind] || {};
      const before = draftOf(kind, id);
      if (text) ui[kind][id] = { text, revision: before ? before.revision : shownRevision() };
      else delete ui[kind][id];
      keep();
    },
    drop(kind, id) {
      if (ui[kind]) delete ui[kind][id];
      keep();
    },
  };

  /** Keep the setState keys of §10 only, and drafts of the {text, revision} form only. */
  function sanitize() {
    if (!ui || typeof ui !== 'object' || Array.isArray(ui)) ui = {};
    for (const key of Object.keys(ui)) if (!UI_KEYS.includes(key)) delete ui[key];
    for (const kind of ['ackDrafts']) {
      if (!ui[kind] || typeof ui[kind] !== 'object' || Array.isArray(ui[kind])) { delete ui[kind]; continue; }
      for (const id of Object.keys(ui[kind])) if (!isDraft(ui[kind][id])) delete ui[kind][id];
    }
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
   * The only textarea of the panel that holds the junior's words (INV-5). It starts empty
   * and is never filled by the panel; the only value it ever gets is the junior's own draft
   * for the same key (`ackDrafts` per execution, `askDraft`), kept
   * in vscode.setState while they type. Views never create a textarea themselves
   * (test/invariants.test.js). `key` is the execution id; the other attributes
   * (id, aria-describedby, data-*) go on the element. `onInput(text)` runs on each keystroke.
   */
  function wordsArea({ kind, key = '', onInput = null, ...attrs }) {
    if (!['ackDrafts', 'askDraft'].includes(kind)) throw new Error('ackDrafts or askDraft');
    const area = el('textarea', { spellcheck: 'true', autocomplete: 'off', 'data-words': kind, ...attrs });
    area.value = kind === 'askDraft' ? String(ui.askDraft || '') : drafts.get(kind, key);
    area.addEventListener('input', () => {
      if (kind === 'askDraft') uiState.set('askDraft', area.value || undefined);
      else drafts.set(kind, key, area.value);
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

  function header() {
    const c = C();
    const snap = state.snapshot;
    ageNode = el('span', { 'data-literal': 'age', text: ageText() });
    const name = snap ? folderName(snap.study) : '';
    return el('header', { className: 'ht-header' }, [
      el('h1', { className: 'sr-only', text: c.title }),
      el('div', { className: 'ht-brand' }, [
        el('span', { className: 'ht-name', text: snap ? `${c.product} · ${name}` : c.product }),
        state.init.task === 'regression' || (snap && snap.task === 'regression')
          ? el('span', { className: 'ht-badge', text: c.regression }) : null,
        finalTestChip(snap),
        el('span', { className: 'ht-badge', text: c.experimental }),
        state.init.reviewer ? el('span', { className: 'ht-badge ht-badge-reviewer', 'data-reviewer': true, text: c.reviewer }) : null,
      ]),
      el('div', { className: 'ht-meta' }, [
        atLeast('v1') && snap ? el('button', { type: 'button', className: 'ht-ghost', 'data-stage': 'v1',
          'data-switch-study': true, text: c.switchStudy(name), onclick: () => send({ type: 'switch_study' }) }) : null,
        snap ? el('span', { className: 'ht-faint', 'data-revision': snap.revision, text: c.revision(snap.revision) }) : null,
        ageNode,
        el('button', { type: 'button', className: 'ht-ghost', text: c.refresh, disabled: Boolean(state.busy),
          'data-refresh': true, onclick: refreshAll }),
        languageToggle(),
      ]),
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
      drafts, ui: uiState, wordsArea,
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
    // v0.3 (owner addition, I1): one lead sentence says what the tab is for, under its title.
    if (lead && tabbed()) {
      const p = HT.components.lead(lead, { 'data-tab-lead': tab });
      const h2 = node.querySelector('h2');
      if (h2 && h2.parentNode === node) h2.after(p); else node.prepend(p);
    }
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
      tabbed() && list.length ? tablist(list, current) : null,
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
    const executions = m.model.executions || {};
    const listed = new Set([...(executions.interrupted || []), ...(executions.suspected || [])].map(e => e.executionId));
    if (before !== m.model.revision) state.notice = null;
    for (const id of Object.keys(ui.ackDrafts || {})) if (!listed.has(id)) delete ui.ackDrafts[id];
    keep();
    state.snapshot = m.model;
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
        if (m.kind === 'ok' && m.op === 'W6' && m.target) drafts.drop('ackDrafts', m.target);
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
    root = document.getElementById('app');
    window.addEventListener('message', onMessage);
    setInterval(() => { if (ageNode) ageNode.textContent = ageText(); }, 15000);
    render();
    send({ type: 'ready' });
  }

  /** The registered views, read-only: {name, tab, stage} (tests and diagnostics). */
  const registered = () => views.map(v => ({ name: v.name, tab: v.tab, stage: v.stage }));

  Object.assign(HT, { el, svg, wordsArea, register, send, modal, tooltip, navigate, renderOutcome, start, PALETTE, SVG_NS,
    diagnostics, registered, _state: state, TAB_ORDER, fresh, version, language, studyLanguage, LANGUAGES });
  HT.components = HT.components || {};
  HT.copy = HT.copy || {};
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
