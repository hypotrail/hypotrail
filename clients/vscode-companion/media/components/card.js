// The one card pattern of the panel (v0.3, WP-E2; docs/design/companion-v0.3-mockups):
//   card({eyebrow, title, titleId, sub, right, body, finding, why, source, className, attrs})
// an eyebrow (KIND · ROWS), a title phrased as a question, a sub-line (the column's meaning),
// the body (the figure), one sentence of finding, then a footer with "Why?" (every caveat,
// definition and provenance), and a faint "Source" line (activity and a 6-character id;
// never in the prose). Also:
//   why(children, label?)   the "one sentence + Why?" disclosure (details.ht-why)
//   source(activity, id)    the faint source line
//   chip(tone, text, attrs) a filled status chip (ok, needs, sealed, error, stale, neutral, accent)
//   lead(text)              the one lead sentence at the top of a tab (owner addition, I1)
//   engineText(text)        an engine text as sent; in a French panel an English engine text
//                           is marked "(en)" (R21)
(function (HT) {
  'use strict';

  function why(children, label) {
    const list = (Array.isArray(children) ? children : [children]).filter(x => x !== null && x !== undefined && x !== false && x !== '');
    if (!list.length) return null;
    return HT.el('details', { className: 'ht-why', 'data-why': true }, [
      HT.el('summary', { text: label || HT.copy.core.why }),
      HT.el('div', { className: 'ht-why-body' }, list.map(c => (typeof c === 'string' ? HT.el('p', { text: c }) : c))),
    ]);
  }

  function source(activity, id) {
    const c = HT.copy.core;
    return HT.el('span', { className: 'ht-src', 'data-source': id || activity || '', title: id || null }, [
      `${c.sourceWord} · ${activity || ''}`, id ? ` · ${String(id).slice(0, 6)}` : '']);
  }

  function chip(tone, text, attrs) {
    return HT.el('span', { ...(attrs || {}), className: `ht-status ht-st-${tone || 'neutral'}${attrs && attrs.className ? ` ${attrs.className}` : ''}`,
      text });
  }

  function lead(text, attrs) {
    return text ? HT.el('p', { className: 'ht-lead', 'data-lead': true, ...(attrs || {}), text }) : null;
  }

  function card({ eyebrow = null, title = null, titleId = null, titleAttrs = null, sub = null, right = null, body = [],
    finding = null, why: whyItems = null, source: src = null, tools = [], className = '', attrs = {} }) {
    const head = title || eyebrow ? HT.el('div', { className: 'ht-card-h' }, [
      HT.el('div', {}, [
        eyebrow ? HT.el('span', { className: 'ht-cap', 'data-eyebrow': true, text: eyebrow }) : null,
        title ? HT.el('h3', { id: titleId, ...(titleAttrs || {}), text: title }) : null,
        sub ? (typeof sub === 'string' ? HT.el('p', { className: 'ht-sub', text: sub }) : sub) : null,
      ]),
      right,
    ]) : null;
    const w = whyItems ? why(whyItems) : null;
    const footer = w || src || tools.length ? HT.el('div', { className: 'ht-card-f' }, [w, ...tools,
      src ? source(src.activity, src.id) : null]) : null;
    return HT.el('section', { className: `card ${className}`.trim(), 'aria-labelledby': titleId, ...attrs }, [
      head, ...body,
      finding ? (typeof finding === 'string' ? HT.el('p', { className: 'ht-finding', text: finding })
        : HT.el('p', { className: 'ht-finding' }, Array.isArray(finding) ? finding : [finding])) : null,
      footer,
    ]);
  }

  /**
   * An engine text shown as content, as the engine sent it (two-layer copy, §15.1). In a
   * French panel, a text the engine wrote in English (the study language, or `lang`, is not
   * French) carries a faint "(en)" marker with `lang="en"`, so the switch is visible.
   */
  function engineText(text, { lang = null, tag = 'span', attrs = {} } = {}) {
    const panel = HT.language ? HT.language() : 'en';
    const source = lang || (HT.studyLanguage ? HT.studyLanguage() : 'en') || 'en';
    const foreign = panel === 'fr' && source !== 'fr';
    return HT.el(tag, { ...attrs, lang: foreign ? 'en' : null }, [text,
      foreign && text ? HT.el('span', { className: 'ht-en-marker', 'data-en-marker': true, text: '(en)' }) : null]);
  }

  Object.assign(HT.components, { card, why, source, chip, lead, engineText });
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
