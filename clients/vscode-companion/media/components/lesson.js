// The lesson pattern of the panel (2026-10-27, owner-approved mockup docs/plans/mockups/
// panel-lesson-style-fr.html; notes R29, R30 of docs/acceptance/runs/copilot-companion-
// 2026-10-26.md). Every text is the panel's copy (Hypotrail.copy.lesson, English and French)
// or an engine value given by the view; nothing is parsed as HTML. Signatures:
//
//   intro(text, attrs?)          "At this step": two or three sentences at the top of a tab,
//                                saying what the step does and what it corresponds to (R29)
//   notion({id, term, tag?, lead?, definition, here, folds?, keep?, extra?})
//                                the term first, then "In this study" with the study's own
//                                values, foldable Example / Why it holds / Where it breaks,
//                                then "What we keep" (the lessons' pattern)
//   notions(list, attrs?)        a numbered list of notions (null when none applies)
//   fold(kind, title, body, attrs?, note?)   a fold on paper: 'ex', 'why', 'casse', 'more', 'lire'
//   more(id, title, body)        "Learn more": a fold for a chip, a symbol or an abbreviation (R30)
//   reading(kind, options)       the guided reading of a chart (R30): {top, bottom}. `top` is
//                                "Why this chart" (the question, the frame, the rows, the
//                                model); `bottom` is "How to read it" (steps), "What we
//                                conclude" (built by the chart from the values it draws, or
//                                given by the view) and "Watch out". Used by `figure`
//                                (values-table.js), so every chart of the panel has it.
//   trans({tab, text, label, onclick, last?})   the "Next" line at the end of a tab (R30)
//   trap(title, body)            a reading trap on the board or on paper
//   withGuide(guide, fn)         run fn with a guide (frame, rows, model) for every chart it draws
//   parts(list)                  interleave strings and nodes (copy functions return arrays)
//   quote(text, cited?)          a figure quoted in a conclusion (provenance in the hover, not a
//                                second cited element)
(function (HT) {
  'use strict';
  const L = () => HT.copy.lesson;
  const el = (...a) => HT.el(...a);

  /** Strings and nodes in order; arrays are flattened, empty parts dropped. */
  function parts(list) {
    const out = [];
    const walk = x => {
      if (x === null || x === undefined || x === false || x === '') return;
      if (Array.isArray(x)) x.forEach(walk);
      else out.push(x);
    };
    walk(list);
    return out;
  }

  /**
   * A text with the half-disc of development evidence ("◐", which the system fonts draw
   * poorly) drawn in CSS instead (`i.ht-hd`, aria-hidden; the words that follow say it).
   */
  function marked(text) {
    if (typeof text !== 'string' || !text.includes('◐')) return text;
    return text.split('◐').flatMap((piece, i) => (i ? [el('span', { className: 'ht-hd', 'aria-hidden': 'true' }), piece] : [piece]));
  }

  /** A body: a string is a paragraph, an array holds paragraphs (strings) or nodes. */
  function body(content) {
    const list = Array.isArray(content) ? content : [content];
    return list.filter(x => x !== null && x !== undefined && x !== false && x !== '')
      .map(x => (typeof x === 'string' ? el('p', {}, parts([marked(x)])) : x));
  }

  function intro(text, attrs = {}) {
    if (!text) return null;
    return el('p', { className: 'ht-intro', 'data-intro': true, ...attrs }, [
      el('span', { className: 'ht-ie', text: L().atThisStep }), ...parts(Array.isArray(text) ? text : [text])]);
  }

  const FOLDS = { ex: 'ht-ex', why: 'ht-whyfold', casse: 'ht-casse', more: 'ht-more', lire: 'ht-lire', code: 'ht-ex' };

  function fold(kind, title, content, attrs = {}, note = null) {
    return el('details', { className: `ht-fold ht-paper ${FOLDS[kind] || 'ht-more'}`, 'data-fold': kind, ...attrs }, [
      el('summary', {}, [kind === 'more' ? el('span', { className: 'ht-mk2', text: L().learnMore }) : null, title,
        note ? el('small', { text: note }) : null]),
      el('div', { className: 'ht-in' }, body(content)),
    ]);
  }

  function more(id, title, content) {
    return fold('more', title, content, { 'data-more': id });
  }

  function notion({ id, term, tag = null, lead = null, definition, here = null, folds = [], keep = null, extra = [] }) {
    const t = L();
    const idee = el('div', { className: 'ht-idee' }, [
      lead ? el('p', { className: 'ht-nlead' }, [el('span', { className: 'ht-k', text: t.atThisStep }), ...parts(lead)]) : null,
      el('p', { className: 'ht-terme' }, [el('dfn', { text: term }), ...parts([t.defSep, definition])]),
      here ? el('p', { className: 'ht-ici', 'data-here': true }, [el('span', { className: 'ht-k', text: t.inThisStudy }),
        ...parts(here)]) : null,
    ]);
    return el('section', { className: 'ht-notion', 'data-notion': id, 'aria-label': term }, [
      el('h4', {}, [term, tag ? el('span', { className: 'ht-ntag', text: t.tags[tag] || tag }) : null]),
      idee,
      ...parts(extra),
      ...folds.filter(Boolean).map(f => fold(f.kind, f.title || t.folds[f.kind], f.body, { 'data-notion-fold': f.kind })),
      keep ? el('p', { className: 'ht-garde', 'data-notion-keep': true }, [el('span', { className: 'ht-k', text: t.keep }), ...parts(keep)]) : null,
    ]);
  }

  function notions(list, attrs = {}) {
    const items = (list || []).filter(Boolean);
    if (!items.length) return null;
    return el('div', { className: 'ht-notions', 'data-notions': String(items.length), ...attrs }, items);
  }

  /**
   * The guided reading of a chart. `kind` names the chart's anatomy (bars, points,
   * intervals, difference, histogram, boxplot, correlation, curve, matrix); `options`:
   * {title, showTitle, guide: {q?, frame?, rows?, model?, steps?, concl?, attn?}, steps,
   * concl, attn}. The view's `guide` wins over the chart's own conclusion and steps.
   */
  function reading(kind, options = {}) {
    const t = L();
    const g = options.guide || {};
    const k = t.read[kind] ? kind : 'generic';
    // `q: false`: the card's own title is the question (an EDA card), so it is not repeated.
    const q = g.q === false ? null : g.q || options.title;
    const facts = [['frame', g.frame], ['rows', g.rows], ['model', g.model]].filter(([, v]) => v !== null && v !== undefined && v !== '');
    const top = el('div', { className: 'ht-pq ht-paper', 'data-guide': k }, [
      el('span', { className: 'ht-pk', text: t.guide.why }),
      q ? el('p', { className: 'ht-qq', 'data-guide-question': true, text: q }) : null,
      facts.length ? el('p', { className: 'ht-fm' }, facts.map(([key, v]) => el('span', { 'data-guide-fact': key }, [
        `${t.guide[key]} · `, el('strong', {}, parts([marked(v)]))]))) : null,
    ]);
    const steps = [...(g.steps || t.read[k].steps), ...(options.steps || [])];
    const concl = g.concl || options.concl || null;
    const attn = g.attn || options.attn || t.read[k].attn;
    const bottom = el('div', { className: 'ht-reading', 'data-reading': k }, [
      el('details', { className: 'ht-fold ht-paper ht-lire', 'data-lire': true }, [
        el('summary', {}, [t.guide.how, el('small', { text: t.guide.howNote })]),
        el('div', { className: 'ht-in' }, [el('ol', {}, steps.map(s => el('li', {}, parts([s]))))]),
      ]),
      concl && parts([concl]).length ? el('p', { className: 'ht-concl ht-paper', 'data-concl': true }, [
        el('span', { className: 'ht-pk', text: t.guide.concl }), ...parts([concl])]) : null,
      attn ? el('p', { className: 'ht-attn ht-paper', 'data-attn': true }, [
        el('span', { className: 'ht-pk', text: t.guide.attn }), ...parts([attn])]) : null,
    ]);
    return { top, bottom };
  }

  function trans({ tab, text, label, onclick, last = false }) {
    const t = L();
    return el('div', { className: 'ht-trans', 'data-next-tab': tab || '', role: 'note' }, [
      el('span', { className: 'ht-tk', text: last ? t.andThen : t.next }),
      el('p', {}, parts([text])),
      label ? el('button', { type: 'button', className: 'ht-link', 'data-goto': tab, text: label, onclick }) : null,
    ]);
  }

  function trap(title, content, attrs = {}) {
    return el('div', { className: 'ht-trap', role: 'note', ...attrs }, [el('span', { className: 'ht-tt', text: title }), ...body(content)]);
  }

  /**
   * A figure quoted in a conclusion: the same text as the chart shows, with its provenance in
   * the hover. It is a copy, not a second citation: the cited <data> element stays the one in
   * the chart or the values table (one element per cited value).
   */
  function quote(text, cited) {
    const value = text === null || text === undefined ? '' : (typeof text === 'object' && !text.nodeType && text.text !== undefined ? text.text : text);
    const c = cited || (text && typeof text === 'object' && !text.nodeType ? text.cited : null);
    if (value === '' || value === null) return null;
    if (value && typeof value === 'object' && value.nodeType) {
      return el('span', { className: 'ht-quote', 'data-concl-value': true, title: value.getAttribute ? value.getAttribute('title') : null,
        text: value.textContent });
    }
    const rid = c && c.resultId ? String(c.resultId).slice(0, 6) : null;
    return el('span', { className: 'ht-quote', 'data-concl-value': true,
      title: rid ? `${HT.copy.core.sourceWord} · ${rid} · ${c.path || ''}` : null, text: String(value) });
  }

  // The guide a view sets around the charts it draws (`withGuide`), merged under the guide a
  // chart call gives: the frame, the rows and the model of a whole card or section.
  let ambient = null;
  function withGuide(guide, fn) {
    const before = ambient;
    ambient = { ...(before || {}), ...(guide || {}) };
    try { return fn(); } finally { ambient = before; }
  }
  const currentGuide = () => ambient;

  Object.assign(HT.components, { intro, notion, notions, fold, more, reading, trans, trap, parts, quote, withGuide, currentGuide, marked });
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
