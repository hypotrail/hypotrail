// Data & EDA view (COMPANION-ADVANCED §6.3; stage v2; WP-A7; v0.3 WP-E2 design system). The
// tab opens on the data card (`hypotrail data`: what one row describes, the grouped
// dictionary, five fixed rows with the target first, the sealed final test) and the structural
// quality check of the development rows; then the exploration: a gallery of the registered
// EDA results only, one card each (an eyebrow, the question it answers as its title, the
// column's meaning, the chart, one sentence, and a footer with "Why?" and a faint source
// line). Every chart is an engine result, every number is an engine value cited with its
// result id (INV-7), and bar lengths are geometry (INV-14). "Run another chart" offers the
// per-column training-row activities and the whole-study `eda.correlation` of the engine's
// `eda_catalog` and sends `run_eda` (W4); the controller checks it again before any `run`.
// There is no partition control: free exploration belongs in the workbench notebook.
(function (HT) {
  'use strict';
  const el = HT.el;
  const arr = x => (Array.isArray(x) ? x : []);
  // The per-column activities the panel may request: each reads training rows only.
  const PER_COLUMN = ['eda.distribution', 'eda.rate_by', 'eda.mean_by'];
  // v0.3 (WP-E2): the whole-study charts the panel may request (no column, no target).
  const WHOLE = ['eda.correlation'];
  // Activities whose run reads the outcome, so each run is one more look (CLI-CONTRACT §11.2).
  const READS_TARGET = ['eda.rate_by', 'eda.mean_by'];
  const EXCLUDED = ['not_available', 'uncertain_excluded'];
  const RARE_SHOWN = 6;

  // View memory (in this webview only; nothing here is study state): the Request choice,
  // the last W4 outcome (rendered in the Request card, `outcomes: ['W4']`), the language
  // of the dictionary's meanings (null: the panel language), and the cards the junior opened
  // or closed (slot -> open), so a re-render or the language toggle keeps them as they were.
  const memory = { column: null, activity: null, outcome: null, meanings: null, open: new Map() };

  function taskOf(data, ctx, model) {
    const t = (data && data.task) || ctx.task || (model && model.task);
    return t === 'regression' ? 'regression' : 'binary';
  }

  /** An engine number `{value, path, fmt}` as a cited <data> element of result `rid`. */
  function num(ctx, c, rid) {
    if (!c) return null;
    return ctx.components.cited(ctx.format.number(c.value, c.fmt), { resultId: rid, path: c.path, value: c.value });
  }
  function text(ctx, c) {
    return c ? ctx.format.number(c.value, c.fmt) : '';
  }
  /** A values-table cell for an engine number. */
  function cell(ctx, c, rid) {
    return c ? { text: text(ctx, c), cited: { resultId: rid, path: c.path, value: c.value } } : '';
  }
  /** Interleave fixed strings with nodes: parts[0] n[0] parts[1] n[1] ... */
  function weave(parts, nodes) {
    const out = [];
    parts.forEach((p, i) => {
      if (p) out.push(p);
      if (i < nodes.length && nodes[i] !== null && nodes[i] !== undefined) out.push(nodes[i]);
    });
    return out;
  }
  /** "low–high" of an engine interval, as text (for chart labels and values tables). */
  function range(ctx, iv) {
    return iv ? `${text(ctx, iv.low)}–${text(ctx, iv.high)}` : '';
  }
  /** An engine count of the data card (a recorded literal, INV-7 c), grouped as the report does. */
  function count(ctx, n) {
    return Number.isInteger(n) ? ctx.format.number(n, 'int') : '';
  }

  /** The axis maximum of a bar chart: the largest value rounded up to the next step. */
  function axisMax(values, step) {
    const top = Math.max(0, ...values.filter(v => typeof v === 'number' && Number.isFinite(v)));
    return top > 0 ? Math.ceil(top / step - 1e-9) * step : step;
  }
  /** Rounded axis positions: 0, half, max (geometry of the axis, never a figure). */
  function ticks(ctx, max, task) {
    const f = v => (task === 'binary' ? ctx.format.number(v, 'pct0') : ctx.format.number(v, Math.abs(max) >= 10 ? 'int' : 'f1'));
    return [0, max / 2, max].map(v => ({ value: v, text: f(v) }));
  }

  /** The panel language of the dictionary's meanings (R12 merged into R21). */
  function meaningsFr(d) {
    if (!d || !d.hasFrench) return false;
    return (memory.meanings || HT.language()) === 'fr';
  }

  /** A column's meaning from the data card, in the panel language when the case has it. */
  function meaningOf(ctx, column) {
    const entry = ctx.data('data');
    const d = entry && entry.model;
    if (!d || !column) return null;
    if (d.target && d.target.column === column) return meaningsFr(d) && d.target.descriptionFr ? d.target.descriptionFr : d.target.description;
    for (const g of arr(d.groups)) {
      for (const v of arr(g.variables)) {
        if (v.name === column) return meaningsFr(d) && v.descriptionFr ? v.descriptionFr : v.description;
      }
    }
    return null;
  }

  /** The card's sub-line: the column name (code) and its meaning. */
  function subLine(ctx, column) {
    if (!column) return null;
    const meaning = meaningOf(ctx, column);
    return el('p', { className: 'ht-sub', 'data-column-meaning': column }, [el('code', { text: column }), meaning ? ` · ${meaning}` : '']);
  }

  /** The faint source line, which opens the result in Evidence (the former result chip). */
  function sourceButton(ctx, c, card) {
    const rid6 = card.resultId.slice(0, 6);
    return el('button', { type: 'button', className: 'ht-link ht-src', 'data-chip': card.resultId,
      'aria-label': c.chipLabel(rid6), title: card.resultId,
      text: `${HT.copy.core.sourceWord} · ${card.activity} · ${rid6}`,
      onclick: () => ctx.navigate({ tab: 'evidence', kind: 'result', id: card.resultId }) });
  }

  /** Whether the card of `slot` is open: the junior's last choice, else the default. */
  function isOpen(slot, expanded) {
    return memory.open.has(slot) ? memory.open.get(slot) : expanded;
  }

  /** One EDA card in the pattern of the design system. */
  function edaCard(ctx, c, card, { id, eyebrow, title, sub = null, body = [], finding = null, why = [], wide = false, expanded = false, attrs = {} }) {
    const w = ctx.components.why(why);
    return el('section', { className: `card eda-card${wide ? ' eda-wide' : ''}`, 'aria-labelledby': id,
      'data-eda-card': card.slot, 'data-activity': card.activity, 'data-current': card.current ? 'true' : 'false',
      'data-nav': `result:${card.resultId}`, ...attrs }, [
      el('details', { className: 'eda-analysis', open: isOpen(card.slot, expanded) ? true : null,
        // Remembered only where it differs from the default, so a card that becomes the
        // default open one later is not held closed by a choice nobody made.
        ontoggle: e => {
          if (e.target !== e.currentTarget) return;
          if (e.currentTarget.open === expanded) memory.open.delete(card.slot);
          else memory.open.set(card.slot, e.currentTarget.open);
        } }, [
      el('summary', { className: 'ht-card-h' }, [el('div', {}, [
        el('span', { className: 'ht-cap', 'data-eyebrow': true, text: eyebrow }),
        // Each card is titled by the engine's question (ED-7). In a French panel a per-column
        // chart takes the panel's French question rather than the English engine text; other
        // cards keep the engine's text with its "(en)" marker.
        // L3: the engine's French question when it gives one (`localCard`).
        HT.language && HT.language() === 'fr' && PER_COLUMN.includes(card.activity) && card.column
          && (!card.langs || card.langs.question !== 'fr')
          ? el('h3', { id, className: 'eda-question', 'data-question': true,
            text: c.requestQuestion(card.activity, card.column) })
          : el('h3', { id, className: card.question ? 'eda-question' : null, 'data-question': card.question ? true : null },
            [card.question ? ctx.components.engineText(card.question, { lang: card.langs ? card.langs.question : 'en' }) : title]),
        sub,
      ])]),
      el('div', { className: 'eda-analysis-body' }, [
      ...body,
      finding ? el('p', { className: 'ht-finding', 'data-finding': true }, Array.isArray(finding) ? finding : [finding]) : null,
      el('div', { className: 'ht-card-f' }, [w, sourceButton(ctx, c, card)]),
      ]),
      ]),
    ]);
  }

  function titleOf(c, card) {
    const d = card.data || {};
    switch (card.kind) {
      case 'target_rate':
      case 'target_summary': return c.targetTitle(d.target || card.slot);
      case 'special_values': return c.specialTitle;
      case 'rate_by':
      case 'mean_by': return c.byTitle(card.column || '');
      case 'signal': return c.signalTitle;
      case 'quality': return c.qualityTitle;
      case 'correlation': return c.corr.title;
      default: return c.distributionTitle(card.column || '');
    }
  }

  function explainTerm(ctx, id) {
    const d = ctx.data('explain');
    const terms = d && d.model && d.model.terms;
    if (!terms) return null;
    if (Array.isArray(terms)) return terms.find(t => t && t.id === id) || null;
    return terms[id] || null;
  }

  /**
   * An engine text (a note, a warning) in `lang`, the language it is shown in: the panel's
   * when the engine gave it (L3, `localCard`), else the stored English, marked "(en)" in a
   * French panel.
   */
  function engine(ctx, t, attrs, lang = 'en') {
    return t ? ctx.components.engineText(t, { tag: 'p', attrs, lang }) : null;
  }

  /**
   * L3 (owner session 2026-10-26, R4, D4b): the card with the engine's junior texts in the
   * panel language when the evidence result gives them (`texts`, CLI-CONTRACT-COMPANION §5):
   * the question, the note, the warnings and the special values' meanings. `langs` names the
   * language each text is in now; a text the engine has not in that language stays the stored
   * English (an EDA result stores its sentences in English), and the view marks it.
   */
  function localCard(card) {
    const lang = HT.language ? HT.language() : 'en';
    const t = (card && card.texts && card.texts[lang]) || null;
    const out = { ...card, langs: { question: 'en', note: 'en', warnings: 'en' } };
    if (t && t.question && card.question) { out.question = t.question; out.langs.question = lang; }
    if (!card.data) return out;
    const d = { ...card.data };
    if (t && t.note && d.note) { d.note = t.note; out.langs.note = lang; }
    const warnings = Array.isArray(d.warnings) ? d.warnings : [];
    if (t && warnings.length && Array.isArray(t.warnings) && t.warnings.length === warnings.length && t.warnings.every(Boolean)) {
      d.warnings = t.warnings.slice();
      out.langs.warnings = lang;
    }
    if (Array.isArray(d.rows)) {
      d.rows = d.rows.map(r => {
        const m = t && t.meanings ? t.meanings[`${r.column}=${r.value}`] : null;
        return m ? { ...r, meaning: m } : r;
      });
    }
    out.data = d;
    return out;
  }

  // --- the data card (WP-A7) -------------------------------------------------------------

  /**
   * L3 (D4b): a junior line of the data card in the panel language when the engine gives it
   * in it (`lines`: {en, fr}), else the line as sent, in the study language, marked.
   */
  function lineOf(ctx, both, fallback) {
    // An English study's junior line is the one to show (its `junior_text`, `fallback`); a
    // French study gives it in French (`junior_text`) and in English (`line`), and the panel
    // shows the one of its language.
    const lang = HT.language ? HT.language() : 'en';
    const study = HT.studyLanguage ? HT.studyLanguage() : 'en';
    if (study === 'en' || !both) return ctx.components.engineText(fallback, { lang: study });
    if (both[lang]) return ctx.components.engineText(both[lang], { lang });
    return ctx.components.engineText(fallback, { lang: study });
  }

  /** A variable's availability in words: the junior's decision when there is one, else the case. */
  function knownCell(c, v, fr = false) {
    if (v.role === 'target') return el('span', { className: 'ht-status ht-st-accent', 'data-known': 'target', text: c.data.target });
    if (v.decided && v.decided.value) {
      const excluded = EXCLUDED.includes(v.decided.value);
      return el('span', {}, [
        el('span', { className: `ht-status ${excluded ? 'ht-st-error' : v.decided.value === 'uncertain_included' ? 'ht-st-stale' : 'ht-st-ok'}`,
          'data-known': v.decided.value, title: c.data.yourDecision, text: c.data.availability[v.decided.value] || v.decided.value }),
      ]);
    }
    const a = v.availability || {};
    const stated = a.value && a.value !== 'unknown' ? (c.data.availability[a.value] || a.value) : c.data.notDocumented;
    // L3: the case's source in French when the panel shows the meanings in French.
    const source = fr && a.sourceFr ? a.sourceFr : a.source;
    return el('span', { title: [a.status ? c.data.factStatus[a.status] || a.status : '', source || ''].filter(Boolean).join(' · ') || null }, [
      el('span', { className: 'ht-status ht-st-neutral', 'data-known': a.value || 'unknown', text: stated }),
    ]);
  }

  function typeText(ctx, c, v) {
    const parts = [c.data.types[v.type] || v.type];
    if (v.unit) parts.push(v.unit);
    if (!['integer', 'numeric'].includes(v.type) && Number.isInteger(v.nDistinct)) parts.push(c.data.values(count(ctx, v.nDistinct)));
    return parts.filter(Boolean).join(' · ');
  }

  function meaningCell(ctx, c, v, fr) {
    const french = fr && v.descriptionFr;
    return el('div', {}, [
      el('span', { lang: french ? 'fr' : 'en', 'data-description': french ? 'fr' : 'en', text: french ? v.descriptionFr : v.description }),
      v.examples.length ? el('div', { className: 'ht-sub', text: c.data.examples(v.examples.join(' · ')) }) : null,
      ...v.specialValues.map(s => el('div', { className: 'ht-sub eda-special-line', 'data-special': `${v.name}:${s.value}` }, [
        c.data.special, el('code', { text: s.value }), ': ',
        el('span', { lang: fr && s.meaningFr ? 'fr' : 'en', 'data-special-meaning': fr && s.meaningFr ? 'fr' : 'en',
          text: fr && s.meaningFr ? s.meaningFr : s.meaning }),
        Number.isInteger(s.nRows) ? ` (${c.data.rows(count(ctx, s.nRows))})` : '',
      ])),
    ]);
  }

  function dictionary(ctx, c, d, fr) {
    const head = c.data.columns;
    const rows = [];
    for (const g of d.groups) {
      rows.push(el('tr', { className: 'eda-group-row', 'data-group': g.group }, [
        el('th', { scope: 'colgroup', colspan: String(head.length), lang: fr && g.groupFr ? 'fr' : null,
          text: fr && g.groupFr ? g.groupFr : g.group })]));
      for (const v of g.variables) {
        rows.push(el('tr', { 'data-variable': v.name, 'data-role': v.role }, [
          el('td', { className: 'eda-name' }, [el('span', { className: 'colname', text: v.name }),
            el('div', { className: 'ht-sub', text: typeText(ctx, c, v) })]),
          el('td', { className: 'eda-meaning' }, [meaningCell(ctx, c, v, fr)]),
          el('td', {}, [knownCell(c, v, fr)]),
          el('td', { className: 'eda-num', 'data-missing-cell': v.name, text: count(ctx, v.nMissing) }),
        ]));
      }
    }
    return el('div', { className: 'eda-scroll', 'data-scroll-ok': true }, [el('table', { className: 'ht-tbl eda-dictionary', 'data-dictionary': true }, [
      el('caption', { className: 'sr-only', text: c.data.dictionaryCaption }),
      el('thead', {}, [el('tr', {}, head.map(h => el('th', { scope: 'col', text: h })))]),
      el('tbody', {}, rows),
    ])]);
  }

  /** The five fixed development rows, the target first, excluded columns marked. */
  function fiveRows(ctx, c, d) {
    const decided = {};
    for (const g of d.groups) for (const v of g.variables) decided[v.name] = v.decided ? v.decided.value : null;
    const excluded = name => EXCLUDED.includes(decided[name]);
    const cols = d.rows.columns;
    const table = el('table', { className: 'ht-tbl eda-rows', 'data-five-rows': true }, [
      el('caption', { className: 'sr-only', text: c.data.rowsCaption }),
      el('thead', {}, [el('tr', {}, cols.map((name, i) => el('th', { scope: 'col', className: [i === 0 ? 'eda-target-col' : '',
        excluded(name) ? 'eda-excluded' : ''].join(' ').trim() || null, 'data-column': name,
      title: excluded(name) ? c.data.excludedTitle : null, text: excluded(name) ? `${name} ✗` : name })))]),
      el('tbody', {}, d.rows.items.map(r => el('tr', { 'data-row-key': r.rowKey }, r.cells.map((v, i) => el('td', {
        className: [i === 0 ? 'eda-target-col' : '', excluded(cols[i]) ? 'eda-excluded' : ''].join(' ').trim() || null,
        text: v === null ? c.data.missingCell : v }))))),
    ]);
    const anyExcluded = cols.some(excluded);
    return el('details', { className: 'ht-details eda-five', 'data-five-rows-box': true }, [
      el('summary', { text: c.data.rowsTitle }),
      el('div', { className: 'eda-scroll', 'data-scroll-ok': true }, [table]),
      anyExcluded ? el('p', { className: 'ht-sub', 'data-excluded-legend': true, text: c.data.excludedLegend }) : null]);
  }

  function stat(value, label, attrs = {}) {
    return el('div', { className: 'ht-stat', ...attrs }, [el('div', { className: 'ht-stat-v' }, value), el('div', { className: 'ht-stat-l', text: label })]);
  }

  function dataCard(ctx, c, entry, task) {
    const d = entry.model;
    const t = d.target;
    // The labels, unless the description already names them ("(yes/no)").
    const named = [t.positiveLabel, t.negativeLabel].every(x => x !== null && t.description.includes(x));
    const labels = t.positiveLabel !== null && t.negativeLabel !== null && !named ? ` (${t.positiveLabel} / ${t.negativeLabel})` : '';
    const unit = d.observationUnit;
    const fr = meaningsFr(d);
    const tDescription = fr && t.descriptionFr ? t.descriptionFr : t.description;
    // R12 merged into R21: the meanings follow the panel language; this toggle names which
    // language the Meaning column shows and switches it for this view only.
    const toggle = d.hasFrench ? el('div', { className: 'ht-seg', role: 'group', 'aria-label': c.data.meaningsLabel,
      'data-french-toggle': true, 'aria-pressed': fr ? 'true' : 'false' }, ['en', 'fr'].map(l => el('button', {
      type: 'button', lang: l, 'aria-pressed': (fr ? 'fr' : 'en') === l ? 'true' : 'false', 'data-meanings': l,
      text: c.data.meaningsButton(l), onclick: () => { memory.meanings = l; ctx.rerender(); } }))) : null;
    const ft = d.finalTest;
    const sealedRows = ft && Number.isInteger(ft.rows) ? ft.rows : null;
    return el('section', { className: 'card eda-data', 'aria-labelledby': 'eda-data-title', 'data-data-card': true }, [
      el('div', { className: 'ht-card-h' }, [
        el('div', {}, [el('span', { className: 'ht-cap', text: c.data.eyebrow }),
          el('h3', { id: 'eda-data-title', 'data-fact': 'unit' }, [c.data.oneRowIs((fr && unit.valueFr) || unit.value || c.data.notStated)])]),
        el('span', { className: 'ht-status ht-st-neutral', text: c.data.structural }),
      ]),
      el('div', { className: 'ht-grid ht-g4 eda-facts' }, [
        stat([el('span', { 'data-development-rows': String(d.development.rows), text: count(ctx, d.development.rows) })],
          d.development.partition === 'all' ? c.data.allRowsLabel : c.data.developmentRows, { 'data-fact': 'size' }),
        stat([count(ctx, d.development.columns)], c.data.columnsLabel),
        sealedRows !== null && ft.status === 'sealed'
          ? stat([count(ctx, sealedRows), el('small', { text: c.data.sealedWord })], c.data.finalTestLabel) : null,
      ]),
      el('div', { className: 'ht-note', 'data-fact': 'target' }, [el('span', {}, [
        el('strong', {}, [c.data.targetLead, el('code', { text: t.column })]), ': ',
        el('span', { lang: fr && t.descriptionFr ? 'fr' : null, text: `${tDescription}${labels}` }), '. ',
        el('span', { className: 'muted', text: task === 'regression' ? c.data.targetLater : c.data.targetLater })])]),
      d.finalTest.line && d.finalTest.audience !== 'agent'
        ? el('p', { className: 'eda-seal-line ht-sub', 'data-seal-line': d.finalTest.status || '' }, [
          el('span', { className: 'ht-status ht-st-sealed', text: c.data.sealed }), ' ',
          lineOf(ctx, d.finalTest.lines, d.finalTest.line)]) : null,
      el('div', { className: 'ht-section-h' }, [el('h4', { text: c.data.dictionaryTitle(count(ctx, d.development.columns)) }), toggle]),
      d.hasFrench ? el('p', { className: 'ht-sub', 'data-meanings-hint': true, text: c.data.meaningsHint }) : null,
      dictionary(ctx, c, d, fr),
      fiveRows(ctx, c, d),
      d.note ? el('p', { className: 'ht-sub', 'data-data-note': true }, [lineOf(ctx, d.noteLines, d.note)]) : null,
    ]);
  }

  function dataSection(ctx, c, task) {
    const entry = ctx.data('data');
    const error = ctx.error('data');
    if (entry && entry.model) return dataCard(ctx, c, entry, task);
    if (error) {
      return el('div', { className: 'card alert', role: 'alert', 'data-data-error': true }, [
        el('p', { className: 'title', text: c.data.loadError }), el('p', { text: error.message }),
        el('button', { type: 'button', className: 'secondary', text: c.retry, onclick: () => { ctx.retry('data'); ctx.load('data'); } }),
      ]);
    }
    return el('div', { className: 'card eda-skeleton', 'aria-busy': 'true', 'data-data-loading': true },
      [el('p', { className: 'muted', text: c.data.loading })]);
  }

  // --- card bodies ----------------------------------------------------------------------

  function targetRate(ctx, c, card) {
    const d = card.data;
    const rid = card.resultId;
    const items = [
      { label: d.positiveLabel, value: d.rate ? d.rate.value : 0, small: false, valueText: text(ctx, d.rate),
        cited: d.rate ? { resultId: rid, path: d.rate.path, value: d.rate.value } : null },
      { label: c.otherLabel, value: d.rate ? 1 - d.rate.value : 0, small: false, tone: 'baseline',
        valueText: text(ctx, d.nNegative), cited: d.nNegative ? { resultId: rid, path: d.nNegative.path, value: d.nNegative.value } : null },
    ];
    const box = el('div', { className: 'eda-stack' });
    ctx.components.bars(box, { title: c.targetChart(d.target), items, max: 1, unit: c.measureHead });
    box.querySelector('[data-chart]').setAttribute('data-target-bars', 'true');
    const term = d.imbalanced ? [c.imbalanceTerm, c.imbalanceText] : [c.baseRateTerm, c.baseRateText];
    const example = ctx.learningLayer ? explainTerm(ctx, 'base_rate') : null;
    return {
      body: [
        el('div', { className: 'ht-stat' }, [el('div', { className: 'ht-stat-v' }, [num(ctx, d.rate, rid)]),
          el('div', { className: 'ht-stat-l' }, weave(c.targetOf, [num(ctx, d.nRows, rid)]))]),
        d.interval ? el('p', { className: 'ht-sub', 'data-interval-line': true }, weave(c.intervalLine,
          [num(ctx, d.interval.low, rid), num(ctx, d.interval.high, rid)])) : null,
        box,
      ],
      finding: el('span', { 'data-term': d.imbalanced ? 'class_imbalance' : 'base_rate' }, [el('strong', { text: term[0] }), term[1]]),
      why: [
        el('p', { className: 'eda-split' }, [
          el('span', {}, weave(c.targetLine, [num(ctx, d.nPositive, rid), d.positiveLabel, num(ctx, d.rate, rid), num(ctx, d.nRows, rid)])),
          ' · ', el('span', {}, [num(ctx, d.nNegative, rid), c.otherRows])]),
        example && Array.isArray(example.example) && example.example.length
          ? ctx.components.segments(el('p', { 'data-example': 'base_rate' }), example.example) : null,
      ],
    };
  }

  function targetSummary(ctx, c, card) {
    const d = card.data;
    const rid = card.resultId;
    const box = el('div');
    ctx.components.boxplot(box, {
      title: c.summaryChart(d.target), min: d.min && d.min.value, q25: d.q25 && d.q25.value, median: d.median && d.median.value,
      q75: d.q75 && d.q75.value, max: d.max && d.max.value,
      texts: { min: cell(ctx, d.min, rid), q25: cell(ctx, d.q25, rid), median: cell(ctx, d.median, rid), q75: cell(ctx, d.q75, rid),
        max: cell(ctx, d.max, rid) },
    });
    const term = explainTerm(ctx, 'target_distribution');
    return {
      body: [box, statRow(ctx, c, d, rid, true)],
      finding: d.meanInterval ? el('span', { 'data-interval-line': true }, weave(c.meanIntervalLine,
        [num(ctx, d.meanInterval.low, rid), num(ctx, d.meanInterval.high, rid)])) : null,
      why: [
        el('p', { 'data-term': 'target_distribution' }, [el('strong', { text: c.summaryTerm }),
          term && typeof term.definition === 'string' ? `: ${term.definition}` : null]),
        el('p', {}, weave(c.summaryLine, [num(ctx, d.median, rid), num(ctx, d.q25, rid), num(ctx, d.q75, rid), num(ctx, d.min, rid),
          num(ctx, d.max, rid), num(ctx, d.mean, rid), num(ctx, d.nRows, rid)])),
        engine(ctx, d.note, { 'data-note': true }, card.langs.note),
      ],
    };
  }

  function specialValues(ctx, c, card, task) {
    const d = card.data;
    const rid = card.resultId;
    const body = [];
    const why = [];
    for (const t of d.together) {
      const [before, after] = c.together(`${t.a.column} = ${t.a.value}`, `${t.b.column} = ${t.b.value}`);
      body.push(el('p', { className: 'ht-note eda-together', 'data-together': `${t.a.column}:${t.b.column}` }, [before, num(ctx, t.nBoth, rid), after]));
    }
    if (task === 'binary' && d.rows.some(r => r.rate)) {
      const items = d.rows.filter(r => r.rate).map(r => ({
        label: `${r.column} = ${r.value}`, value: r.rate.value, small: false,
        interval: r.interval ? { low: r.interval.low.value, high: r.interval.high.value } : null,
        valueText: `${text(ctx, r.rate)} · n ${text(ctx, r.nRows)}`,
        cited: { resultId: rid, path: r.rate.path, value: r.rate.value },
      }));
      const max = axisMax(items.flatMap(i => [i.value, i.interval ? i.interval.high : null]), 0.05);
      body.push(ctx.components.bars(el('div'), { title: c.specialChart, items, max, unit: c.specialMeasureHead,
        ticks: ticks(ctx, max, task), point: true }));
    }
    const measure = task === 'binary' ? 'rate' : 'meanTarget';
    const table = el('div', { className: 'eda-table' });
    ctx.components.valuesTable(table, {
      caption: c.specialTable,
      columns: [{ key: 'column', label: c.columnHead }, { key: 'value', label: c.codeHead }, { key: 'meaning', label: c.meaningHead },
        { key: 'rows', label: c.rowsHead }, { key: 'share', label: c.shareHead }, { key: 'measure', label: c.specialMeasureHead }],
      rows: d.rows.map(r => ({ column: r.column, value: r.value, meaning: r.meaning, rows: cell(ctx, r.nRows, rid),
        share: cell(ctx, r.share, rid), measure: cell(ctx, r[measure], rid) })),
    });
    body.push(table);
    why.push(engine(ctx, d.note, { 'data-note': true }, card.langs.note));
    return { body, why };
  }

  /** The null band of a by-column chart in words: is the spread more than chance draws? */
  function nullBandLine(ctx, c, band, rid) {
    if (!band || !band.observed || !band.nullMax) return null;
    const parts = band.outside ? c.bandOutside : c.bandInside;
    return el('span', { className: `eda-band-line ${band.outside ? 'eda-band-outside' : ''}`.trim(), 'data-null-band': band.outside ? 'outside' : 'inside' },
      weave(parts, [num(ctx, band.observed, rid), num(ctx, band.shuffles, rid), num(ctx, band.nullMax, rid)]));
  }

  function byColumn(ctx, c, card, task) {
    const d = card.data;
    const rid = card.resultId;
    const column = card.column || d.column;
    const groups = [...d.groups, ...(d.other ? [{ ...d.other, label: c.other }] : [])];
    const pair = iv => (iv ? { low: iv.low.value, high: iv.high.value } : null);
    const items = groups.filter(g => g.value).map(g => ({
      label: g.label, sub: g.nRows ? `n ${text(ctx, g.nRows)}` : '', value: g.value.value, small: g.small,
      interval: pair(g.interval), band: pair(g.band),
      valueText: `${text(ctx, g.value)}${g.interval ? ` · ${range(ctx, g.interval)}` : ''}`,
      cited: { resultId: rid, path: g.value.path, value: g.value.value },
    }));
    const step = task === 'binary' ? 0.05 : 5;
    const max = axisMax(items.flatMap(i => [i.value, i.interval && i.interval.high, i.band && i.band.high]), step);
    const chart = ctx.components.bars(el('div'), {
      title: c.byChart(column), items, max, point: true, ticks: ticks(ctx, max, task),
      rule: d.overall ? { value: d.overall.value, label: `${c.overall} ${text(ctx, d.overall)}` } : null,
      unit: c.measureHead,
    });
    const counts = el('details', { className: 'ht-details eda-counts' }, [el('summary', { text: c.countsSummary })]);
    ctx.components.valuesTable(counts, {
      caption: c.byChart(column),
      columns: [{ key: 'label', label: c.groupHead }, { key: 'rows', label: c.rowsHead },
        { key: 'extra', label: c.extraHead }, { key: 'value', label: c.measureHead }, { key: 'interval', label: c.intervalHead },
        { key: 'band', label: c.bandHead }, { key: 'small', label: c.smallHead }],
      rows: groups.map(g => ({ label: g.label, rows: cell(ctx, g.nRows, rid),
        extra: cell(ctx, task === 'binary' ? g.nPositive : g.sd, rid), value: cell(ctx, g.value, rid),
        interval: range(ctx, g.interval), band: range(ctx, g.band), small: g.small ? c.small : '' })),
    });
    const anyBand = items.some(i => i.band);
    const anyInterval = items.some(i => i.interval);
    return {
      body: [chart, counts],
      finding: nullBandLine(ctx, c, d.nullBand, rid) || el('span', {}, weave(c.overallLine, [num(ctx, d.overall, rid), num(ctx, d.nRows, rid)])),
      why: [
        el('p', {}, weave(c.overallLine, [num(ctx, d.overall, rid), num(ctx, d.nRows, rid)])),
        anyInterval || anyBand ? el('p', { className: 'eda-legend', 'data-legend': true },
          [anyInterval ? c.intervalLegend : '', anyInterval && anyBand ? ' ' : '', anyBand ? c.bandLegend : '']) : null,
        el('p', { 'data-hatch-caption': true }, weave(c.hatch, [num(ctx, d.minGroupRows, rid)])),
        el('p', { className: 'eda-noncausal', 'data-noncausal': true, text: c.nonCausal(column) }),
        d.warnings.length ? el('ul', { className: 'eda-warnings', 'data-warnings': true },
          d.warnings.map(w => ctx.components.engineText(w, { tag: 'li', lang: card.langs.warnings }))) : null,
        engine(ctx, d.note, { 'data-note': true }, card.langs.note),
      ],
    };
  }

  /** Median, IQR, mean, max and missing, named with their standard terms (R17). */
  function statRow(ctx, c, n, rid, withMin) {
    const item = (label, node) => (node ? el('span', {}, [`${label} `, el('strong', {}, [node])]) : null);
    const iqr = n.q25 && n.q75 ? el('span', {}, [num(ctx, n.q25, rid), '–', num(ctx, n.q75, rid)]) : null;
    return el('p', { className: 'ht-statrow', 'data-numeric-line': true }, [
      item(c.stats.median, num(ctx, n.median, rid)), item(c.stats.iqr, iqr), item(c.stats.mean, num(ctx, n.mean, rid)),
      withMin ? item(c.stats.min, num(ctx, n.min, rid)) : null, item(c.stats.max, num(ctx, n.max, rid)),
    ]);
  }

  function distribution(ctx, c, card) {
    const d = card.data;
    const rid = card.resultId;
    const column = card.column || d.column;
    const body = [];
    let finding = null;
    const why = [el('p', { 'data-term-line': 'distribution' }, [el('strong', {}, [HT.terms.mark(c.distribution, 'distribution')]), c.distributionOnTrain])];
    if (d.numeric) {
      const n = d.numeric;
      // R17: a skewed column shows its exact zeros apart and its positive values on log bins.
      const skewed = n.skewed && n.logBins.length > 0;
      const bins = skewed ? n.logBins : n.bins;
      const edge = b => (b.lowCited ? ctx.format.number(b.lowCited.value, 'auto') : String(b.low));
      const zeros = skewed && n.zeros && n.zeros.nRows ? n.zeros : null;
      body.push(ctx.components.histogram(el('div'), {
        title: c.distributionChart(column), showTitle: false,
        axisLabel: skewed ? c.logAxis : c.linearAxis,
        zero: zeros ? { label: c.zeroLabel, share: zeros.share ? zeros.share.value : 0, valueText: num(ctx, zeros.share, rid),
          rowsText: el('span', {}, weave(c.zeroRows, [num(ctx, zeros.nRows, rid), num(ctx, d.nRows, rid)])) } : null,
        bins: bins.map((b, i) => ({ low: b.low, high: b.high, count: b.nRows ? b.nRows.value : 0, countText: cell(ctx, b.nRows, rid),
          lowText: cell(ctx, b.lowCited, rid), highText: cell(ctx, b.highCited, rid),
          edgeText: i === 0 && skewed ? `${edge(b)}` : edge(b) })),
      }));
      const missing = d.nMissing && d.nMissing.value > 0 ? num(ctx, d.nMissing, rid) : null;
      const row = statRow(ctx, c, n, rid, false);
      if (missing) row.appendChild(el('span', {}, [`${c.stats.missing} `, el('strong', {}, [missing])]));
      body.push(row);
      if (skewed) why.push(el('p', { 'data-log-scale': true, text: c.logWhy }));
      why.push(el('p', {}, weave(c.numericLine, [num(ctx, n.median, rid), num(ctx, n.q25, rid),
        num(ctx, n.q75, rid), num(ctx, n.min, rid), num(ctx, n.max, rid), num(ctx, n.n, rid)])));
      why.push(el('p', { text: c.statTerms }));
      finding = zeros ? el('span', {}, weave(c.zeroFinding, [num(ctx, zeros.share, rid)])) : null;
    } else {
      const groups = [...d.groups, ...(d.other ? [{ ...d.other, label: c.other, small: false }] : [])];
      const items = groups.filter(g => g.nRows).map(g => ({
        label: g.label, value: g.nRows.value, small: g.small,
        valueText: g.share ? `${text(ctx, g.nRows)} · ${text(ctx, g.share)}` : text(ctx, g.nRows),
        cited: { resultId: rid, path: g.nRows.path, value: g.nRows.value },
      }));
      body.push(ctx.components.bars(el('div'), { title: c.groupsChart(column), items, max: 0, unit: c.rowsHead }));
      if (groups.some(g => g.small)) {
        why.push(el('p', { 'data-hatch-caption': true }, weave(c.distributionHatch, [num(ctx, d.minGroupRows, rid)])));
      }
    }
    // Missing and special values as their own bars (R17).
    const own = [...d.specials.filter(s => s.nRows).map(s => ({ label: `${column} = ${s.value}`, value: s.nRows.value, small: false,
      tone: 'baseline', valueText: s.share ? `${text(ctx, s.nRows)} · ${text(ctx, s.share)}` : text(ctx, s.nRows),
      cited: { resultId: rid, path: s.nRows.path, value: s.nRows.value } }))];
    if (d.nMissing && d.nMissing.value > 0) {
      own.push({ label: c.missingLabel, value: d.nMissing.value, small: false, tone: 'baseline', valueText: text(ctx, d.nMissing),
        cited: { resultId: rid, path: d.nMissing.path, value: d.nMissing.value } });
    }
    if (own.length) {
      const box = el('div', { 'data-specials-line': true, className: 'eda-specials' });
      const top = d.nRows ? d.nRows.value : 0;
      ctx.components.bars(box, { title: c.specialsChart(column), items: own, max: top, unit: c.rowsHead, showTitle: false });
      body.push(el('p', { className: 'ht-sub', text: c.specialsLine }), box);
    }
    if (d.warnings.length) why.push(el('ul', { className: 'eda-warnings', 'data-warnings': true }, d.warnings.map(w => ctx.components.engineText(w, { tag: 'li', lang: card.langs.warnings }))));
    why.push(engine(ctx, d.note, { 'data-note': true }, card.langs.note));
    return { body, finding, why };
  }

  /**
   * The single-feature signal (WP-A7): each feature alone, scored out of fold on the training
   * rows; a flagged feature raises the legitimacy question of the leakage detector. The
   * panel states the question and the junior's availability decision for that feature in
   * words; it never keeps or drops a feature.
   */
  function signal(ctx, c, card, task) {
    const d = card.data;
    const rid = card.resultId;
    const metric = task === 'regression' ? c.signalR2 : c.signalAuc;
    const items = d.signals.filter(s => s.score).map(s => ({
      label: EXCLUDED.includes(s.availability) ? `${s.feature} ${c.signalExcluded}` : s.feature,
      value: Math.max(0, s.score.value), small: false, tone: s.flag ? null : 'baseline',
      valueText: text(ctx, s.score), cited: { resultId: rid, path: s.score.path, value: s.score.value },
    }));
    const body = [ctx.components.bars(el('div'), { title: c.signalChart(metric), items, max: 1,
      ticks: [0, 0.5, 1].map(v => ({ value: v, text: ctx.format.number(v, 'f1') })),
      rule: d.level ? { value: d.level.value, label: `${c.level} ${text(ctx, d.level)}` } : null, unit: metric })];
    let finding = null;
    if (d.questions.length) {
      for (const q of d.questions) {
        const decided = q.availability ? (EXCLUDED.includes(q.availability) ? c.leakExcluded
          : c.leakKept) : c.leakUndecided;
        body.push(el('div', { className: 'ht-note ht-note-warn eda-leak', role: 'note', 'data-leak': q.feature }, [
          el('div', {}, [
            el('p', {}, [el('strong', { text: `${c.leakTitle}: ` }), el('code', { text: q.feature }), ...weave(c.leakLine(metric), [num(ctx, q.score, rid)])]),
            el('p', { text: c.leakQuestion }),
            el('p', { 'data-leak-decision': q.availability || 'none' }, [el('span', { className: 'ht-status ht-st-neutral',
              text: q.availability ? (c.availabilityWords[q.availability] || q.availability) : c.noDecision }), ` ${decided}`]),
          ]),
        ]));
      }
    } else {
      finding = el('span', { 'data-no-leak': true }, weave(c.noLeak(metric), [num(ctx, d.level, rid)]));
    }
    return { body, finding, why: [
      el('p', { 'data-signal-legend': true }, weave(c.signalLegend(metric), [num(ctx, d.folds, rid), num(ctx, d.nRows, rid), num(ctx, d.median, rid)])),
      engine(ctx, d.note, { 'data-note': true }, card.langs.note)] };
  }

  /**
   * v0.3 (WP-E2, R28): the predictor-versus-predictor association matrix, read on the
   * development rows without the target (never a look at the outcome). The lower triangle in
   * the engine's clustered order, the flagged pairs (|value| >= the level) outlined and named.
   */
  function correlation(ctx, c, card) {
    const d = card.data;
    const rid = card.resultId;
    const k = c.corr;
    const byPair = {};
    for (const p of d.pairs) { byPair[`${p.a}|${p.b}`] = p; byPair[`${p.b}|${p.a}`] = p; }
    const two = v => ctx.format.number(v, 'f2').replace(/^(-?)0\./, '$1.');
    const flagged = d.pairs.filter(p => p.flag && p.value).sort((x, y) => Math.abs(y.value.value) - Math.abs(x.value.value));
    const box = el('div');
    ctx.components.corr(box, {
      order: d.order, title: k.chart,
      cell: (a, b) => {
        const p = byPair[`${a}|${b}`];
        if (!p || !p.value) return null;
        return { value: p.value.value, text: two(p.value.value), flag: p.flag, measure: p.measure,
          cited: { resultId: rid, path: p.value.path, value: p.value.value } };
      },
      legend: [['pos', k.legendPos], ['neg', k.legendNeg]],
      columns: [{ key: 'a', label: k.first }, { key: 'b', label: k.second }, { key: 'measure', label: k.measure },
        { key: 'value', label: k.value }, { key: 'rows', label: c.rowsHead }],
      rows: d.pairs.map(p => ({ a: p.a, b: p.b, measure: k.measures[p.measure] || p.measure, value: cell(ctx, p.value, rid),
        rows: cell(ctx, p.nRows, rid) })),
    });
    const body = [box, el('div', { className: 'ht-ramp', 'aria-hidden': 'true' }, [el('span', { text: '−1' }), el('i'), el('span', { text: '+1' }),
      el('span', {}, [k.outlined, ` |r| ≥ ${text(ctx, d.level)}`])])];
    if (flagged.length) {
      body.push(el('ul', { className: 'eda-flagged', 'data-flagged': String(flagged.length) }, flagged.slice(0, 8).map(p => el('li', {}, [
        el('code', { text: p.a }), ' · ', el('code', { text: p.b }), ' ', num(ctx, p.value, rid), el('span', { className: 'ht-sub', text: ` (${k.measuresShort[p.measure] || p.measure})` })]))));
    }
    const finding = flagged.length ? el('span', { 'data-collinear': 'some' }, weave(k.findingSome, [num(ctx, d.level, rid), num(ctx, d.nFlagged, rid)]))
      : el('span', { 'data-collinear': 'none' }, weave(k.findingNone, [num(ctx, d.level, rid)]));
    return { body, finding, why: [
      el('p', {}, [el('strong', { text: k.term }), k.termText]),
      el('p', { text: k.measuresText }),
      el('p', {}, weave(k.rowsRead, [num(ctx, d.nRows, rid)])),
      el('p', { text: k.notALook }),
      engine(ctx, d.note, { 'data-note': true }, card.langs.note),
    ] };
  }

  /** The structural quality of the development rows (WP-A7): the target is not read. */
  function qualityCard(ctx, c, card, i) {
    const id = `eda-quality-${i}`;
    const q = c.quality;
    if (!card.current || !card.data) {
      return el('section', { className: 'card eda-card eda-quality', 'aria-labelledby': id, 'data-quality-card': card.slot,
        'data-current': 'false' }, [el('div', { className: 'ht-card-h' }, [el('div', {}, [
        el('span', { className: 'ht-cap', text: q.eyebrow }), el('h3', { id, text: titleOf(c, card) })])]),
      el('p', { className: 'status status-stale', 'data-stale': true, text: c.stale }), sourceButton(ctx, c, card)]);
    }
    const d = card.data;
    const rid = card.resultId;
    const chips = [];
    chips.push(el('span', { className: `ht-status ${d.missing.length ? 'ht-st-stale' : 'ht-st-ok'}`, 'data-quality': 'missing' },
      d.missing.length ? weave(q.chipMissing, [num(ctx, d.nRowsWithMissing, rid)]) : [q.chipNoMissing]));
    const dup = d.duplicates.nRows && d.duplicates.nRows.value > 0;
    chips.push(el('span', { className: `ht-status ${dup ? 'ht-st-stale' : 'ht-st-ok'}`, 'data-quality': 'duplicates' },
      dup ? weave(q.chipDuplicates, [num(ctx, d.duplicates.nRows, rid)]) : [q.chipNoRepeat]));
    const rareCount = d.rare.reduce((s, r) => s + r.rare.length, 0);
    chips.push(el('span', { className: `ht-status ${rareCount ? 'ht-st-stale' : 'ht-st-ok'}`, 'data-quality': 'rare' },
      rareCount ? [q.chipRare(ctx.format.number(rareCount, 'int'))] : [q.chipNoRare]));
    const declared = d.ranges.some(r => r.declared);
    const zero = x => !x || x.value === 0;
    const outsideAny = d.ranges.some(r => r.declared && !(zero(r.nBelow) && zero(r.nAbove)));
    if (declared) chips.push(el('span', { className: `ht-status ${outsideAny ? 'ht-st-error' : 'ht-st-ok'}`, 'data-quality': 'ranges',
      text: outsideAny ? q.chipOutside : q.chipInRange }));
    const why = [];
    why.push(el('p', {}, weave(q.read, [num(ctx, d.nRows, rid), num(ctx, d.nColumns, rid)])));
    if (d.missing.length) {
      why.push(el('p', { 'data-quality-detail': 'missing' }, [q.missingSome, ...d.missing.flatMap((m, k) => [k ? '; ' : ' ', el('code', { text: m.column }), ' ',
        num(ctx, m.nMissing, rid), ' (', num(ctx, m.share, rid), ')']), '.']));
    }
    for (const m of d.coMissing) {
      why.push(el('p', { 'data-quality': 'co-missing' }, [q.together, m.columns.join(', '), ': ', num(ctx, m.nRows, rid), ` ${c.rows}`]));
    }
    if (dup) why.push(el('p', {}, [...weave(q.duplicatesSome, [num(ctx, d.duplicates.nRows, rid), num(ctx, d.duplicates.nGroups, rid)]), ` (${d.duplicates.definition}).`]));
    if (d.rare.length) {
      why.push(el('p', { 'data-quality-detail': 'rare' }, [...weave(q.rareSome, [num(ctx, d.rare[0].rareRows, rid)]), ...d.rare.flatMap((r, k) => [k ? '; ' : ' ', el('code', { text: r.column }), ': ',
        // A column with many rare values (a name per row) lists the first few, then their count.
        ...r.rare.slice(0, RARE_SHOWN).flatMap((x, j) => [j ? ', ' : '', `${x.value} (`, num(ctx, x.nRows, rid), ')']),
        r.rare.length > RARE_SHOWN ? q.rareMore(ctx.format.number(r.rare.length, 'int')) : '']), '.']));
    }
    const ranges = el('details', { className: 'ht-details eda-ranges' }, [el('summary', { text: q.rangesTitle })]);
    if (d.ranges.length) {
      // WP-E1 (R26): the "outside the declared range" column exists only when a column
      // declares a range; none outside reads "none" (never "0 / 0").
      const outside = r => (!r.declared ? '' : zero(r.nBelow) && zero(r.nAbove) ? q.noneOutside
        : q.outsideCounts(text(ctx, r.nBelow) || '0', text(ctx, r.nAbove) || '0'));
      ctx.components.valuesTable(ranges, {
        caption: q.rangesCaption,
        columns: [{ key: 'column', label: c.columnHead }, { key: 'min', label: q.lowest }, { key: 'max', label: q.highest },
          ...(declared ? [{ key: 'outside', label: q.outside }] : [])],
        rows: d.ranges.map(r => ({ column: r.column, min: cell(ctx, r.min, rid), max: cell(ctx, r.max, rid),
          ...(declared ? { outside: outside(r) } : {}) })),
      });
    }
    why.push(engine(ctx, d.note, { 'data-note': true }, card.langs.note));
    return el('section', { className: 'card eda-card eda-quality', 'aria-labelledby': id, 'data-quality-card': card.slot,
      'data-current': 'true', 'data-nav': `result:${card.resultId}` }, [
      el('div', { className: 'ht-card-h' }, [el('div', {}, [
        el('span', { className: 'ht-cap', 'data-eyebrow': true, text: q.eyebrow }),
        el('h3', { id, className: card.question ? 'eda-question' : null, 'data-question': card.question ? true : null },
          [card.question ? ctx.components.engineText(card.question, { lang: card.langs ? card.langs.question : 'en' }) : titleOf(c, card)])])]),
      el('div', { className: 'ht-chips eda-chips' }, chips),
      d.ranges.length ? ranges : null,
      el('div', { className: 'ht-card-f' }, [ctx.components.why(why), sourceButton(ctx, c, card)]),
    ]);
  }

  function eyebrowOf(c, card) {
    const e = c.eyebrows;
    switch (card.kind) {
      case 'target_rate': return e.targetRate;
      case 'target_summary': return e.targetSummary;
      case 'special_values': return e.special;
      case 'rate_by': return e.rateBy;
      case 'mean_by': return e.meanBy;
      case 'signal': return e.signal;
      case 'correlation': return e.correlation;
      default: return e.distribution;
    }
  }

  function cardNode(ctx, c, card, i, task, expanded = false) {
    const id = `eda-card-${i}`;
    const wide = card.kind === 'rate_by' || card.kind === 'mean_by' || card.kind === 'correlation'
      || (card.kind === 'distribution' && card.data && card.data.numeric && card.data.numeric.skewed)
      || (card.kind === 'special_values' && card.current);
    let parts;
    if (!card.current || !card.data) {
      parts = { body: [el('p', { className: 'status status-stale', 'data-stale': true, text: c.stale })] };
    } else if (card.kind === 'target_rate') parts = targetRate(ctx, c, card);
    else if (card.kind === 'target_summary') parts = targetSummary(ctx, c, card);
    else if (card.kind === 'special_values') parts = specialValues(ctx, c, card, task);
    else if (card.kind === 'rate_by' || card.kind === 'mean_by') parts = byColumn(ctx, c, card, task);
    else if (card.kind === 'signal') parts = signal(ctx, c, card, task);
    else if (card.kind === 'correlation') parts = correlation(ctx, c, card);
    else parts = distribution(ctx, c, card);
    const column = ['rate_by', 'mean_by', 'distribution'].includes(card.kind) ? card.column : null;
    return edaCard(ctx, c, card, { id, eyebrow: eyebrowOf(c, card), title: titleOf(c, card), sub: subLine(ctx, column),
      body: parts.body || [], finding: parts.finding || null, why: parts.why || [], wide, expanded });
  }

  // --- Run another chart --------------------------------------------------------------------

  /**
   * The columns the recorded availability decision marks `not_available` (decision CR.7).
   * The summary holds the value as JSON, either {status: [columns]} or {column: status}.
   * EDA still runs on them (training rows); the panel only says so next to their name.
   */
  function notAtPrediction(ctx) {
    const d = ctx.snapshot && ctx.snapshot.decisions && ctx.snapshot.decisions.feature_availability;
    let value = null;
    try { value = d && d.value ? JSON.parse(d.value) : null; } catch (_) { value = null; }
    const out = new Set();
    if (!value || typeof value !== 'object' || Array.isArray(value)) return out;
    for (const [k, v] of Object.entries(value)) {
      if (k === 'not_available' && Array.isArray(v)) v.filter(x => typeof x === 'string').forEach(x => out.add(x));
      else if (v === 'not_available') out.add(k);
    }
    return out;
  }

  /** v0.3 (WP-E2): the whole-study charts of the catalog (the correlation matrix). */
  function wholeStudy(ctx, c, data) {
    const model = data.model;
    const entries = arr(model.catalog).filter(a => !a.perColumn && WHOLE.includes(a.activity) && a.runnable);
    return entries.map(entry => {
      const shown = model.cards.find(k => k.activity === entry.activity && k.current);
      const working = ctx.busyOp === 'W4';
      return el('div', { className: 'eda-whole', 'data-whole': entry.activity }, [
        el('p', { className: 'ht-sub', 'data-request-question': entry.activity }, [`${c.answers} ${c.corr.request}`]),
        el('p', { className: 'ht-sub', text: c.corr.noLook }),
        shown ? el('button', { type: 'button', className: 'secondary', 'data-show-card': shown.slot, text: c.showIt,
          onclick: () => ctx.navigate({ tab: 'eda', kind: 'result', id: shown.resultId }) })
          : el('button', { type: 'button', className: 'secondary', 'data-write': 'run_eda', 'data-activity': entry.activity,
            disabled: ctx.busy ? true : null, 'aria-busy': working ? 'true' : null, text: working ? c.working : c.corr.run,
            onclick: () => ctx.send({ type: 'run_eda', activity: entry.activity, revision: data.revision }) }),
      ]);
    });
  }

  function requestCard(ctx, c, data, task) {
    const model = data.model;
    // Training-row charts only (WP-A7): the per-column activities of the catalog.
    const perColumn = arr(model.catalog).filter(a => a.perColumn && PER_COLUMN.includes(a.activity));
    const runnable = perColumn.filter(a => a.runnable);
    const out = [el('span', { className: 'ht-cap', text: c.requestEyebrow }), el('h3', { id: 'eda-request-title', text: c.requestTitle })];
    if (!runnable.length) {
      const missing = [...new Set(perColumn.flatMap(a => a.missing))];
      out.push(el('p', { 'data-not-runnable': true, text: missing.length ? `${c.notAvailable} ${missing.join('; ')}` : c.nothingToRequest }));
    } else {
      const columns = [];
      for (const a of runnable) for (const col of a.columns) if (!columns.some(x => x.name === col.name)) columns.push(col);
      if (!columns.some(x => x.name === memory.column)) memory.column = columns.length ? columns[0].name : null;
      const charts = runnable.filter(a => a.columns.some(x => x.name === memory.column))
        .sort((a, b) => PER_COLUMN.indexOf(a.activity) - PER_COLUMN.indexOf(b.activity));
      if (!charts.some(a => a.activity === memory.activity)) memory.activity = charts.length ? charts[0].activity : null;
      const label = activity => (activity === 'eda.distribution' ? c.distribution : c.byChartLabel);
      const unavailable = notAtPrediction(ctx);
      const roleWord = r => (c.roles && c.roles[r]) || r;
      const tags = col => [roleWord(col.role), unavailable.has(col.name) ? c.notAtPrediction : null].filter(Boolean);
      const variable = el('select', { id: 'eda-variable', 'data-request': 'column',
        onchange: e => { memory.column = e.target.value; memory.activity = null; ctx.rerender(); } },
      columns.map(col => el('option', { value: col.name, selected: col.name === memory.column ? true : null,
        text: tags(col).length ? `${col.name} (${tags(col).join(', ')})` : col.name })));
      const chart = el('select', { id: 'eda-chart', 'data-request': 'activity',
        onchange: e => { memory.activity = e.target.value; ctx.rerender(); } },
      charts.map(a => el('option', { value: a.activity, selected: a.activity === memory.activity ? true : null, text: label(a.activity) })));
      const entry = charts.find(a => a.activity === memory.activity);
      const col = entry ? entry.columns.find(x => x.name === memory.column) : null;
      const shown = col && col.resultId ? model.cards.find(k => k.resultId === col.resultId && k.current) : null;
      const working = ctx.busyOp === 'W4';
      const action = shown
        ? el('button', { type: 'button', id: 'eda-show', 'data-show-card': shown.slot, text: c.showIt,
          onclick: () => ctx.navigate({ tab: 'eda', kind: 'result', id: shown.resultId }) })
        : el('button', { type: 'button', id: 'eda-run', 'data-write': 'run_eda', disabled: ctx.busy || !entry ? true : null,
          'aria-busy': working ? 'true' : null, text: working ? c.working : c.run,
          onclick: () => ctx.send({ type: 'run_eda', activity: entry.activity, column: memory.column, revision: data.revision }) });
      // WP-A7: the question the chart answers is said before it runs; a chart that reads the
      // outcome is one more look.
      const question = entry ? c.requestQuestion(entry.activity, memory.column) : null;
      out.push(el('div', { className: 'eda-request-row' }, [
        el('div', {}, [el('label', { for: 'eda-variable', text: c.variable }), variable]),
        el('div', {}, [el('label', { for: 'eda-chart', text: c.chart }), chart]),
        el('div', { className: 'eda-request-go' }, [action])]),
      unavailable.has(memory.column) ? el('p', { className: 'ht-sub', 'data-not-at-prediction': memory.column,
        text: c.notAtPredictionHint(memory.column) }) : null,
      question ? el('p', { className: 'ht-sub eda-request-question', 'data-request-question': entry.activity }, [
        `${c.answers} ${question}`]) : null,
      entry && READS_TARGET.includes(entry.activity) && !shown
        ? el('p', { className: 'ht-sub', 'data-one-more-look': true, text: c.oneMoreLook }) : null);
    }
    out.push(...wholeStudy(ctx, c, data));
    out.push(el('div', { className: 'ht-card-f' }, [ctx.components.why([el('p', { 'data-hint': true, text: c.hint })]),
      el('button', { type: 'button', className: 'ht-link', 'data-open': 'workbench', text: c.openWorkbench,
        onclick: () => ctx.send({ type: 'open_artifact', artifact: 'workbench' }) })]));
    const o = memory.outcome;
    if (o) {
      const region = el('div', { 'data-eda-outcome': o.kind }, [ctx.renderOutcome(o)]);
      if (o.recorded && o.recorded.slot) region.appendChild(el('p', { className: 'muted', text: c.recorded(o.recorded.slot, o.recorded.status || '') }));
      out.push(region);
    }
    return el('section', { className: 'card eda-card eda-request eda-wide', 'aria-labelledby': 'eda-request-title', 'data-eda-request': task }, out);
  }

  // --- the tab --------------------------------------------------------------------------------

  function banner(ctx, c, data, model) {
    const seen = data.model.rowsSeen || {};
    const fmt = n => ctx.format.number(n, 'int');
    const ft = model && model.finalTest;
    const looks = model && model.edaLooks && Number.isInteger(model.edaLooks.targetLooks) ? model.edaLooks.targetLooks : null;
    const why = [el('p', { text: c.bannerText })];
    // WP-E1 (R26): split-aware; under cross-validation EDA reads the development rows and
    // there is no validation partition. Prose, not monospace.
    why.push(seen.scope === 'development'
      ? el('p', { className: 'eda-seen', 'data-rows-scope': 'development' }, [`${c.rowsSeen}: `,
        el('span', { 'data-rows-seen': 'development', 'data-value': String(seen.trainEda || 0), text: fmt(seen.trainEda || 0) }),
        ` ${c.development}.`])
      : el('p', { className: 'eda-seen', 'data-rows-scope': 'split' }, [`${c.rowsSeen}: `,
        el('span', { 'data-rows-seen': 'train', 'data-value': String(seen.trainEda || 0), text: fmt(seen.trainEda || 0) }),
        ` ${c.train} · `,
        el('span', { 'data-rows-seen': 'validation', 'data-value': String(seen.validationEda || 0), text: fmt(seen.validationEda || 0) }),
        ` ${c.validation}.`]));
    if (looks !== null) why.push(el('p', { text: c.looksText }));
    if (Number.isInteger(seen.validationModels)) {
      why.push(el('p', {}, [`${c.validationModels} `,
        el('span', { 'data-rows-seen': 'validation-models', 'data-value': String(seen.validationModels), text: fmt(seen.validationModels) })]));
    }
    return el('div', { className: 'ht-note ht-note-seal eda-banner', role: 'note' }, [el('div', {}, [
      el('p', {}, [el('strong', { text: c.bannerLead }), ' ',
        ft && ft.status === 'sealed' && Number.isInteger(ft.rows)
          ? el('span', { className: 'eda-banner-seal', 'data-banner-seal': true }, [c.sealedRows(fmt(ft.rows))]) : null,
        ft && ft.status === 'absent' ? el('span', { className: 'eda-banner-seal', 'data-banner-seal': 'absent', text: c.noFinalTest }) : null,
        looks !== null ? el('span', { className: 'eda-looks', 'data-looks': String(looks) }, [' ',
          el('strong', {}, [c.looksLead, el('span', { 'data-looks-count': true, text: fmt(looks) })])]) : null]),
      ctx.components.why(why, c.bannerWhy),
    ])]);
  }

  HT.register('eda', {
    tab: 'eda',
    stage: 'v2',
    views: ['eda', 'data'],
    outcomes: ['W4'],
    onMessage(m) {
      if (m.type === 'outcome' && m.op === 'W4') memory.outcome = m;
      return undefined;
    },
    render(model, ctx) {
      const data = ctx.data('eda');
      const error = ctx.error('eda');
      const task = taskOf(data && data.model, ctx, model);
      // WP-E1 (R26): under cross-validation the exploration reads the development rows; the
      // strings that name the rows or the validation partition take their `cv` variant.
      const base = ctx.copy.eda[task];
      const cv = Boolean(data && data.model && data.model.rowsSeen && data.model.rowsSeen.scope === 'development');
      const c = cv ? { ...base, ...base.cv, eyebrows: { ...base.eyebrows, ...(base.cv.eyebrows || {}) } } : base;
      // R1b (owner session 2026-10-26): the data card and the quality check carry the section
      // headings the engine's panel line names ("Data & EDA → Data card", "→ Data quality").
      const out = [el('h2', { text: c.heading }),
        el('h3', { className: 'ht-section eda-part-title', 'data-section': 'data_card', text: c.data.cardTitle }),
        dataSection(ctx, c, task)];
      if (!data) {
        if (error) {
          out.push(el('div', { className: 'card alert', role: 'alert', 'data-eda-error': true }, [
            el('p', { className: 'title', text: c.loadError }), el('p', { text: error.message }),
            error.detail ? el('details', { className: 'ht-details' }, [el('summary', { text: c.loadErrorDetail }), el('pre', { text: error.detail })]) : null,
            el('button', { type: 'button', className: 'secondary', text: c.retry, onclick: () => { ctx.retry('eda'); ctx.load('eda'); } }),
          ]));
          return out;
        }
        // Loading: skeleton cards until the first read answers.
        out.push(el('div', { className: 'eda-gallery', 'aria-busy': 'true', 'data-eda-loading': true }, [
          el('div', { className: 'card eda-skeleton' }, [el('p', { className: 'muted', text: c.loading })]),
          el('div', { className: 'card eda-skeleton', 'aria-hidden': 'true' }),
        ]));
        return out;
      }
      // L3 (D4b): each card's engine texts in the panel language when the engine gave them.
      const cards = arr(data.model.cards).map(localCard);
      // The structural quality check reads the development rows without the target: it
      // belongs with the data card, before the training-row exploration.
      const quality = cards.filter(k => k.kind === 'quality');
      if (quality.length) out.push(el('h3', { className: 'ht-section eda-part-title', 'data-section': 'quality', text: c.qualityTitle }));
      quality.forEach((card, i) => out.push(qualityCard(ctx, c, card, i)));
      const gallery = cards.filter(k => k.kind !== 'quality');
      out.push(el('h3', { className: 'ht-section eda-section-title', text: c.explorationTitle }));
      out.push(banner(ctx, c, data, model));
      if (ctx.snapshot && !ctx.fresh(data)) out.push(el('p', { className: 'muted', 'data-updating': true, text: c.updating }));
      if (error) out.push(el('p', { className: 'alert', role: 'alert', 'data-eda-error': true, text: `${c.loadError} ${error.message}` }));
      const grid = el('div', { className: 'eda-gallery', 'aria-label': c.galleryLabel });
      if (!gallery.length) out.push(el('div', { className: 'ht-empty', 'data-eda-empty': true, text: c.empty }));
      gallery.forEach((card, i) => grid.appendChild(cardNode(ctx, c, card, i, task,
        i === gallery.length - 1)));
      grid.appendChild(requestCard(ctx, c, data, task));
      out.push(grid);
      return out;
    },
  });
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
