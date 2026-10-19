// Data & EDA view (COMPANION-ADVANCED §6.3; stage v2; WP-A7). The tab opens on the data card
// (`hypotrail data`: what one row describes, the grouped dictionary, five fixed rows with the
// target first, the sealed final test) and the structural quality check of the development
// rows; then the exploration of the training rows: a gallery of the registered EDA results
// only, each card titled by the question it answers, with its intervals and n, the shuffled-
// outcome null band, and the single-feature signal (the leakage detector). Every chart is an
// engine result, every number is an engine value cited with its result id (INV-7), and bar
// lengths are geometry (INV-14). "Run another chart" offers only the per-column training-row
// activities and columns of the engine's `eda_catalog` and sends `run_eda` (W4); the
// controller checks it again before any `run`. There is no partition control: free
// exploration belongs in the workbench notebook. Owned by WP-U4; WP-A7 added the data card.
(function (HT) {
  'use strict';
  const el = HT.el;
  const arr = x => (Array.isArray(x) ? x : []);
  const str = x => (typeof x === 'string' ? x : '');
  // The per-column activities the panel may request: each reads training rows only.
  const PER_COLUMN = ['eda.distribution', 'eda.rate_by', 'eda.mean_by'];
  // Activities whose run reads the outcome, so each run is one more look (CLI-CONTRACT §11.2).
  const READS_TARGET = ['eda.rate_by', 'eda.mean_by'];
  const EXCLUDED = ['not_available', 'uncertain_excluded'];
  const RARE_SHOWN = 6;

  // View memory (in this webview only; nothing here is study state): the Request choice,
  // the last W4 outcome (rendered in the Request card, `outcomes: ['W4']`), and the language
  // of the dictionary's labels.
  const memory = { column: null, activity: null, outcome: null, french: false };

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

  /**
   * A card's head (WP-A7): its title is the question the result answers (the engine's
   * `values.question`), then the name of the chart and the chip of its result id.
   */
  function header(ctx, c, card, title, id) {
    const rid8 = card.resultId.slice(0, 8);
    return el('div', { className: 'eda-card-head' }, [
      el('h3', { id, className: card.question ? 'eda-question' : null, 'data-question': card.question ? true : null,
        text: card.question || title }),
      el('div', { className: 'eda-card-meta' }, [
        card.question ? el('span', { className: 'muted eda-chart-name', text: title }) : null,
        el('button', { type: 'button', className: 'ht-link ht-mono eda-chip', 'data-chip': card.resultId,
          'aria-label': c.chipLabel(rid8), text: c.chip(card.slot || card.activity, rid8),
          onclick: () => ctx.navigate({ tab: 'evidence', kind: 'result', id: card.resultId }) }),
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

  // --- the data card (WP-A7) -------------------------------------------------------------

  /** A variable's availability in words: the junior's decision when there is one, else the case. */
  function knownCell(c, v) {
    if (v.role === 'target') return el('span', { className: 'ht-status ht-st-neutral', 'data-known': 'target', text: c.data.target });
    if (v.decided && v.decided.value) {
      const excluded = EXCLUDED.includes(v.decided.value);
      return el('span', {}, [
        el('span', { className: `ht-status ${excluded ? 'ht-st-error' : v.decided.value === 'uncertain_included' ? 'ht-st-stale' : 'ht-st-ok'}`,
          'data-known': v.decided.value, title: v.decided.value, text: c.data.availability[v.decided.value] || v.decided.value }),
        el('span', { className: 'muted eda-known-source', text: ` ${c.data.yourDecision}` }),
      ]);
    }
    const a = v.availability || {};
    const stated = a.value && a.value !== 'unknown' ? (c.data.availability[a.value] || a.value) : c.data.notDocumented;
    return el('span', { title: a.source || null }, [
      el('span', { className: 'ht-status ht-st-neutral', 'data-known': a.value || 'unknown', text: stated }),
      a.status ? el('span', { className: 'muted eda-known-source', text: ` ${c.data.factStatus[a.status] || a.status}` }) : null,
    ]);
  }

  function typeText(ctx, c, v) {
    const parts = [c.data.types[v.type] || v.type];
    if (v.unit) parts.push(v.unit);
    if (!['integer', 'numeric'].includes(v.type) && Number.isInteger(v.nDistinct)) parts.push(c.data.values(count(ctx, v.nDistinct)));
    return parts.filter(Boolean).join(' · ');
  }

  function meaningCell(ctx, c, v) {
    const fr = memory.french && v.descriptionFr;
    return el('div', {}, [
      el('span', { lang: fr ? 'fr' : null, 'data-description': fr ? 'fr' : 'en', text: fr ? v.descriptionFr : v.description }),
      ...v.specialValues.map(s => el('div', { className: 'muted eda-special-line', 'data-special': `${v.name}:${s.value}` }, [
        c.data.special, el('code', { text: s.value }), `: ${s.meaning}`,
        Number.isInteger(s.nRows) ? ` (${c.data.rows(count(ctx, s.nRows))})` : '',
      ])),
    ]);
  }

  function dictionary(ctx, c, d) {
    const head = c.data.columns;
    const rows = [];
    for (const g of d.groups) {
      rows.push(el('tr', { className: 'eda-group-row', 'data-group': g.group }, [
        el('th', { scope: 'colgroup', colspan: String(head.length), text: g.group })]));
      for (const v of g.variables) {
        rows.push(el('tr', { 'data-variable': v.name, 'data-role': v.role }, [
          el('td', { className: 'eda-name' }, [el('code', { text: v.name })]),
          el('td', { className: 'muted', text: typeText(ctx, c, v) }),
          el('td', {}, [meaningCell(ctx, c, v)]),
          el('td', {}, [knownCell(c, v)]),
          el('td', { className: 'eda-num', 'data-missing-cell': v.name, text: count(ctx, v.nMissing) }),
          el('td', { className: 'muted', text: v.examples.join(', ') }),
        ]));
      }
    }
    return el('div', { className: 'eda-scroll' }, [el('table', { className: 'eda-dictionary', 'data-dictionary': true }, [
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
    const table = el('table', { className: 'eda-rows', 'data-five-rows': true }, [
      el('caption', { className: 'sr-only', text: c.data.rowsCaption }),
      el('thead', {}, [el('tr', {}, cols.map((name, i) => el('th', { scope: 'col', className: [i === 0 ? 'eda-target-col' : '',
        excluded(name) ? 'eda-excluded' : ''].join(' ').trim() || null, 'data-column': name,
      title: excluded(name) ? c.data.excludedTitle : null, text: excluded(name) ? `${name} ✗` : name })))]),
      el('tbody', {}, d.rows.items.map(r => el('tr', { 'data-row-key': r.rowKey }, r.cells.map((v, i) => el('td', {
        className: [i === 0 ? 'eda-target-col' : '', excluded(cols[i]) ? 'eda-excluded' : ''].join(' ').trim() || null,
        text: v === null ? c.data.missingCell : v }))))),
    ]);
    const anyExcluded = cols.some(excluded);
    return [el('div', { className: 'eda-scroll' }, [table]),
      anyExcluded ? el('p', { className: 'muted', 'data-excluded-legend': true, text: c.data.excludedLegend }) : null];
  }

  function dataCard(ctx, c, entry, task) {
    const d = entry.model;
    const t = d.target;
    // The labels, unless the description already names them ("(yes/no)").
    const named = [t.positiveLabel, t.negativeLabel].every(x => x !== null && t.description.includes(x));
    const labels = t.positiveLabel !== null && t.negativeLabel !== null && !named ? ` (${t.positiveLabel} / ${t.negativeLabel})` : '';
    const unit = d.observationUnit;
    const french = memory.french && d.hasFrench;
    const tDescription = french && t.descriptionFr ? t.descriptionFr : t.description;
    const toggle = d.hasFrench ? el('button', { type: 'button', className: 'secondary', 'data-french-toggle': true,
      'aria-pressed': french ? 'true' : 'false', text: french ? c.data.englishLabels : c.data.frenchLabels,
      onclick: () => { memory.french = !memory.french; ctx.rerender(); } }) : null;
    return el('section', { className: 'card eda-data', 'aria-labelledby': 'eda-data-title', 'data-data-card': true }, [
      el('div', { className: 'eda-card-head' }, [
        el('h3', { id: 'eda-data-title', text: c.data.title }),
        el('span', { className: 'ht-status ht-st-neutral', text: c.data.structural }),
      ]),
      el('div', { className: 'eda-facts' }, [
        el('div', { className: 'eda-fact', 'data-fact': 'unit' }, [el('strong', { text: c.data.oneRow }),
          el('span', { text: unit.value || c.data.notStated }),
          unit.status ? el('span', { className: 'muted', title: unit.source || null, text: c.data.factStatus[unit.status] || unit.status }) : null]),
        el('div', { className: 'eda-fact', 'data-fact': 'size' }, [
          el('strong', { 'data-development-rows': String(d.development.rows),
            text: c.data.size(count(ctx, d.development.rows), count(ctx, d.development.columns)) }),
          el('span', { text: d.development.partition === 'all' ? c.data.allRows : c.data.developmentOnly })]),
        el('div', { className: 'eda-fact', 'data-fact': 'target' }, [el('strong', {}, [c.data.targetLead, el('code', { text: t.column })]),
          el('span', { lang: french && t.descriptionFr ? 'fr' : null, text: `${tDescription}${labels}` }),
          el('span', { className: 'muted', text: task === 'regression' ? c.data.targetLaterRegression : c.data.targetLater })]),
      ]),
      d.finalTest.line && d.finalTest.audience !== 'agent'
        ? el('p', { className: 'eda-seal-line', 'data-seal-line': d.finalTest.status || '' }, [
          el('span', { className: 'ht-status ht-st-sealed', text: c.data.sealed }), ` ${d.finalTest.line}`]) : null,
      el('h4', { text: c.data.rowsTitle }),
      ...fiveRows(ctx, c, d),
      el('div', { className: 'eda-dictionary-head' }, [el('h4', { text: c.data.dictionaryTitle(count(ctx, d.development.columns)) }), toggle]),
      dictionary(ctx, c, d),
      d.note ? el('p', { className: 'muted', 'data-data-note': true, text: d.note }) : null,
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
    const W = 420;
    const share = d.rate ? Math.max(0, Math.min(1, d.rate.value)) : 0;
    const chart = ctx.svg('svg', { viewBox: `0 0 ${W} 28`, width: '100%', class: 'ht-chart eda-stack' }, [
      ctx.svg('rect', { x: 0, y: 0, height: 28, width: Math.max(1, share * W), fill: 'accent', 'data-segment': 'positive' }),
      ctx.svg('rect', { x: share * W, y: 0, height: 28, width: Math.max(0, W - share * W), fill: 'baseline', 'data-segment': 'other' }),
    ]);
    const box = el('div');
    ctx.components.figure(box, {
      title: c.targetChart(d.target), chart,
      columns: [{ key: 'label', label: c.groupHead }, { key: 'rows', label: c.rowsHead }, { key: 'rate', label: c.measureHead }],
      rows: [{ label: d.positiveLabel, rows: cell(ctx, d.nPositive, rid), rate: cell(ctx, d.rate, rid) },
        { label: c.otherRows.trim(), rows: cell(ctx, d.nNegative, rid), rate: '' }],
    });
    const term = d.imbalanced ? [c.imbalanceTerm, c.imbalanceText] : [c.baseRateTerm, c.baseRateText];
    const example = ctx.learningLayer ? explainTerm(ctx, 'base_rate') : null;
    return [
      box,
      el('p', { className: 'eda-split' }, [
        el('span', {}, weave(c.targetLine, [num(ctx, d.nPositive, rid), d.positiveLabel, num(ctx, d.rate, rid), num(ctx, d.nRows, rid)])),
        el('span', {}, [num(ctx, d.nNegative, rid), c.otherRows]),
      ]),
      d.interval ? el('p', { 'data-interval-line': true }, weave(c.intervalLine,
        [num(ctx, d.interval.low, rid), num(ctx, d.interval.high, rid)])) : null,
      el('p', { 'data-term': d.imbalanced ? 'class_imbalance' : 'base_rate' }, [el('strong', { text: term[0] }), term[1]]),
      example && Array.isArray(example.example) && example.example.length
        ? ctx.components.segments(el('p', { className: 'muted', 'data-example': 'base_rate' }), example.example) : null,
    ];
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
    return [
      box,
      el('p', {}, weave(c.summaryLine, [num(ctx, d.median, rid), num(ctx, d.q25, rid), num(ctx, d.q75, rid), num(ctx, d.min, rid),
        num(ctx, d.max, rid), num(ctx, d.mean, rid), num(ctx, d.nRows, rid)])),
      d.meanInterval ? el('p', { 'data-interval-line': true }, weave(c.meanIntervalLine,
        [num(ctx, d.meanInterval.low, rid), num(ctx, d.meanInterval.high, rid)])) : null,
      el('p', { 'data-term': 'target_distribution' }, [el('strong', { text: c.summaryTerm }),
        term && typeof term.definition === 'string' ? `: ${term.definition}` : null]),
      d.note ? el('p', { className: 'muted', 'data-note': true, text: d.note }) : null,
    ];
  }

  function specialValues(ctx, c, card, task) {
    const d = card.data;
    const rid = card.resultId;
    const out = [];
    for (const t of d.together) {
      const [before, after] = c.together(`${t.a.column} = ${t.a.value}`, `${t.b.column} = ${t.b.value}`);
      out.push(el('p', { className: 'eda-together', 'data-together': `${t.a.column}:${t.b.column}` }, [before, num(ctx, t.nBoth, rid), after]));
    }
    if (task === 'binary' && d.rows.some(r => r.rate)) {
      const items = d.rows.filter(r => r.rate).map(r => ({
        label: `${r.column} = ${r.value}`, value: r.rate.value, small: false,
        interval: r.interval ? { low: r.interval.low.value, high: r.interval.high.value } : null,
        valueText: `${text(ctx, r.rate)}${r.interval ? ` [${range(ctx, r.interval)}]` : ''} ${c.ofRows} ${text(ctx, r.nRows)}`,
        cited: { resultId: rid, path: r.rate.path, value: r.rate.value },
      }));
      out.push(ctx.components.bars(el('div'), { title: c.specialChart, items,
        max: axisMax(items.flatMap(i => [i.value, i.interval ? i.interval.high : null]), 0.05), unit: c.specialMeasureHead }));
    }
    const measure = task === 'binary' ? 'rate' : 'meanTarget';
    ctx.components.valuesTable(out[out.push(el('div', { className: 'eda-table' })) - 1], {
      caption: c.specialTable,
      columns: [{ key: 'column', label: c.columnHead }, { key: 'value', label: c.codeHead }, { key: 'meaning', label: c.meaningHead },
        { key: 'rows', label: c.rowsHead }, { key: 'share', label: c.shareHead }, { key: 'measure', label: c.specialMeasureHead }],
      rows: d.rows.map(r => ({ column: r.column, value: r.value, meaning: r.meaning, rows: cell(ctx, r.nRows, rid),
        share: cell(ctx, r.share, rid), measure: cell(ctx, r[measure], rid) })),
    });
    if (d.note) out.push(el('p', { className: 'muted', 'data-note': true, text: d.note }));
    return out;
  }

  /** The null band of a by-column chart in words: is the spread more than chance draws? */
  function nullBandLine(ctx, c, band, rid) {
    if (!band || !band.observed || !band.nullMax) return null;
    const parts = band.outside ? c.bandOutside : c.bandInside;
    return el('p', { className: `eda-band-line ${band.outside ? 'eda-band-outside' : ''}`.trim(), 'data-null-band': band.outside ? 'outside' : 'inside' },
      weave(parts, [num(ctx, band.observed, rid), num(ctx, band.shuffles, rid), num(ctx, band.nullMax, rid)]));
  }

  function byColumn(ctx, c, card, task) {
    const d = card.data;
    const rid = card.resultId;
    const column = card.column || d.column;
    const groups = [...d.groups, ...(d.other ? [{ ...d.other, label: c.other }] : [])];
    const pair = iv => (iv ? { low: iv.low.value, high: iv.high.value } : null);
    const items = groups.filter(g => g.value).map(g => ({
      label: g.label, value: g.value.value, small: g.small, interval: pair(g.interval), band: pair(g.band),
      valueText: task === 'binary' ? `${text(ctx, g.value)}${g.interval ? ` [${range(ctx, g.interval)}]` : ''} ${c.ofRows} ${text(ctx, g.nRows)}`
        : `${text(ctx, g.value)}${g.interval ? ` [${range(ctx, g.interval)}]` : ''} · ${text(ctx, g.nRows)} ${c.rows}`,
      cited: { resultId: rid, path: g.value.path, value: g.value.value },
    }));
    const step = task === 'binary' ? 0.05 : 5;
    const max = axisMax(items.flatMap(i => [i.value, i.interval && i.interval.high, i.band && i.band.high]), step);
    const scaleText = c.scale(ctx.format.number(0, task === 'binary' ? 'pct0' : 'int'),
      task === 'binary' ? ctx.format.number(max, 'pct0') : `${ctx.format.number(max, 'int')}${d.unit ? ' ' + d.unit : ''}`);
    const chart = ctx.components.bars(el('div'), {
      title: c.byChart(column), items, max,
      rule: d.overall ? { value: d.overall.value, label: `${c.overall} ${text(ctx, d.overall)}` } : null,
      unit: c.measureHead,
    });
    const counts = el('details', { className: 'eda-counts' }, [el('summary', { text: c.countsSummary })]);
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
    return [
      chart,
      el('p', { className: 'muted eda-scale', 'aria-hidden': 'true', 'data-literal': 'axis', text: scaleText }),
      anyInterval || anyBand ? el('p', { className: 'muted eda-legend', 'data-legend': true },
        [anyInterval ? c.intervalLegend : '', anyInterval && anyBand ? ' ' : '', anyBand ? c.bandLegend : '']) : null,
      nullBandLine(ctx, c, d.nullBand, rid),
      el('p', {}, weave(c.overallLine, [num(ctx, d.overall, rid), num(ctx, d.nRows, rid)])),
      el('p', { className: 'muted', 'data-hatch-caption': true }, weave(c.hatch, [num(ctx, d.minGroupRows, rid)])),
      el('p', { className: 'eda-noncausal', 'data-noncausal': true, text: c.nonCausal(column) }),
      d.warnings.length ? el('ul', { className: 'eda-warnings', 'data-warnings': true }, d.warnings.map(w => el('li', { text: w }))) : null,
      d.note ? el('p', { className: 'muted', 'data-note': true, text: d.note }) : null,
      counts,
    ];
  }

  function distribution(ctx, c, card) {
    const d = card.data;
    const rid = card.resultId;
    const column = card.column || d.column;
    // The glossary term, for the learning layer's hover (§6.7; WP-I).
    const out = [el('p', { className: 'muted', 'data-term-line': 'distribution' }, [HT.terms.mark(c.distribution, 'distribution'), c.distributionOnTrain])];
    if (d.numeric) {
      const n = d.numeric;
      out.push(ctx.components.histogram(el('div'), {
        title: c.distributionChart(column), axisLabel: column,
        bins: n.bins.map(b => ({ low: b.low, high: b.high, count: b.nRows ? b.nRows.value : 0, countText: cell(ctx, b.nRows, rid),
          lowText: cell(ctx, b.lowCited, rid), highText: cell(ctx, b.highCited, rid) })),
      }));
      out.push(el('p', { 'data-numeric-line': true }, weave(c.numericLine, [num(ctx, n.median, rid), num(ctx, n.q25, rid),
        num(ctx, n.q75, rid), num(ctx, n.min, rid), num(ctx, n.max, rid), num(ctx, n.n, rid)])));
    } else {
      const groups = [...d.groups, ...(d.other ? [{ ...d.other, label: c.other, small: false }] : [])];
      const items = groups.filter(g => g.nRows).map(g => ({
        label: g.label, value: g.nRows.value, small: g.small,
        valueText: g.share ? `${text(ctx, g.nRows)} · ${text(ctx, g.share)}` : text(ctx, g.nRows),
        cited: { resultId: rid, path: g.nRows.path, value: g.nRows.value },
      }));
      out.push(ctx.components.bars(el('div'), { title: c.groupsChart(column), items, max: 0, unit: c.rowsHead }));
      if (groups.some(g => g.small)) {
        out.push(el('p', { className: 'muted', 'data-hatch-caption': true }, weave(c.distributionHatch, [num(ctx, d.minGroupRows, rid)])));
      }
    }
    const extra = [];
    if (d.specials.length) {
      extra.push(c.specialsLine);
      d.specials.forEach((s, i) => extra.push(i ? ' · ' : ' ', `${column} = ${s.value} `, num(ctx, s.nRows, rid), ` ${c.rows}`));
    }
    if (d.nMissing && d.nMissing.value > 0) extra.push(extra.length ? ' · ' : '', `${c.missingLine} `, num(ctx, d.nMissing, rid), ` ${c.rows}`);
    if (extra.length) out.push(el('p', { className: 'muted', 'data-specials-line': true }, extra));
    if (d.warnings.length) out.push(el('ul', { className: 'eda-warnings', 'data-warnings': true }, d.warnings.map(w => el('li', { text: w }))));
    if (d.note) out.push(el('p', { className: 'muted', 'data-note': true, text: d.note }));
    return out;
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
    const out = [ctx.components.bars(el('div'), { title: c.signalChart(metric), items, max: 1,
      rule: d.level ? { value: d.level.value, label: `${c.level} ${text(ctx, d.level)}` } : null, unit: metric })];
    out.push(el('p', { className: 'muted', 'data-signal-legend': true }, weave(c.signalLegend(metric),
      [num(ctx, d.folds, rid), num(ctx, d.nRows, rid), num(ctx, d.median, rid)])));
    if (d.questions.length) {
      for (const q of d.questions) {
        const decided = q.availability ? (EXCLUDED.includes(q.availability) ? c.leakExcluded
          : c.leakKept) : c.leakUndecided;
        out.push(el('div', { className: 'eda-leak', role: 'note', 'data-leak': q.feature }, [
          el('strong', { text: c.leakTitle }),
          el('p', {}, [el('code', { text: q.feature }), ...weave(c.leakLine(metric), [num(ctx, q.score, rid)])]),
          el('p', { text: c.leakQuestion }),
          el('p', { 'data-leak-decision': q.availability || 'none' }, [el('span', { className: 'ht-status ht-st-neutral',
            text: q.availability ? (c.availabilityWords[q.availability] || q.availability) : c.noDecision }), ` ${decided}`]),
        ]));
      }
    } else {
      out.push(el('p', { 'data-no-leak': true }, weave(c.noLeak(metric), [num(ctx, d.level, rid)])));
    }
    if (d.note) out.push(el('p', { className: 'muted', 'data-note': true, text: d.note }));
    return out;
  }

  /** The structural quality of the development rows (WP-A7): the target is not read. */
  function qualityCard(ctx, c, card, i) {
    const id = `eda-quality-${i}`;
    const head = header(ctx, c, card, titleOf(c, card), id);
    if (!card.current || !card.data) {
      return el('section', { className: 'card eda-card eda-quality', 'aria-labelledby': id, 'data-quality-card': card.slot,
        'data-current': 'false' }, [head, el('p', { className: 'status status-stale', 'data-stale': true, text: c.stale })]);
    }
    const d = card.data;
    const rid = card.resultId;
    const q = c.quality;
    const lines = [];
    lines.push(el('p', { 'data-quality': 'missing' }, d.missing.length
      ? [q.missingSome, ...d.missing.flatMap((m, k) => [k ? '; ' : ' ', el('code', { text: m.column }), ' ', num(ctx, m.nMissing, rid),
        ' (', num(ctx, m.share, rid), ')']), '. ', ...weave(q.rowsWithMissing, [num(ctx, d.nRowsWithMissing, rid)])]
      : [q.missingNone]));
    for (const m of d.coMissing) {
      lines.push(el('p', { className: 'muted', 'data-quality': 'co-missing' }, [q.together, m.columns.join(', '), ': ', num(ctx, m.nRows, rid), ` ${c.rows}`]));
    }
    lines.push(el('p', { 'data-quality': 'duplicates' }, d.duplicates.nRows && d.duplicates.nRows.value > 0
      ? [...weave(q.duplicatesSome, [num(ctx, d.duplicates.nRows, rid), num(ctx, d.duplicates.nGroups, rid)]), ` (${d.duplicates.definition}).`]
      : [q.duplicatesNone, d.duplicates.definition ? ` (${d.duplicates.definition}).` : '.']));
    lines.push(el('p', { 'data-quality': 'rare' }, d.rare.length
      ? [...weave(q.rareSome, [num(ctx, d.rare[0].rareRows, rid)]), ...d.rare.flatMap((r, k) => [k ? '; ' : ' ', el('code', { text: r.column }), ': ',
        // A column with many rare values (a name per row) lists the first few, then their count.
        ...r.rare.slice(0, RARE_SHOWN).flatMap((x, j) => [j ? ', ' : '', `${x.value} (`, num(ctx, x.nRows, rid), ')']),
        r.rare.length > RARE_SHOWN ? q.rareMore(ctx.format.number(r.rare.length, 'int')) : '']), '.']
      : [q.rareNone]));
    const ranges = el('div', { className: 'eda-table' });
    if (d.ranges.length) {
      ctx.components.valuesTable(ranges, {
        caption: q.rangesCaption,
        columns: [{ key: 'column', label: c.columnHead }, { key: 'min', label: q.lowest }, { key: 'max', label: q.highest },
          { key: 'outside', label: q.outside }],
        rows: d.ranges.map(r => ({ column: r.column, min: cell(ctx, r.min, rid), max: cell(ctx, r.max, rid),
          outside: r.declared ? `${text(ctx, r.nBelow)} / ${text(ctx, r.nAbove)}` : q.noRange })),
      });
    }
    return el('section', { className: 'card eda-card eda-quality', 'aria-labelledby': id, 'data-quality-card': card.slot,
      'data-current': 'true', 'data-nav': `result:${card.resultId}` }, [
      head,
      el('p', {}, [el('span', { className: 'ht-status ht-st-neutral', text: q.tag }), ' ',
        ...weave(q.read, [num(ctx, d.nRows, rid), num(ctx, d.nColumns, rid)])]),
      ...lines,
      d.ranges.length ? el('h4', { text: q.rangesTitle }) : null,
      ranges,
      d.note ? el('p', { className: 'muted', 'data-note': true, text: d.note }) : null,
    ]);
  }

  function cardNode(ctx, c, card, i, task) {
    const id = `eda-card-${i}`;
    const wide = card.kind === 'rate_by' || card.kind === 'mean_by' || card.kind === 'signal'
      || (card.kind === 'special_values' && card.current);
    let body;
    if (!card.current || !card.data) {
      body = [el('p', { className: 'status status-stale', 'data-stale': true, text: c.stale })];
    } else if (card.kind === 'target_rate') body = targetRate(ctx, c, card);
    else if (card.kind === 'target_summary') body = targetSummary(ctx, c, card);
    else if (card.kind === 'special_values') body = specialValues(ctx, c, card, task);
    else if (card.kind === 'rate_by' || card.kind === 'mean_by') body = byColumn(ctx, c, card, task);
    else if (card.kind === 'signal') body = signal(ctx, c, card, task);
    else body = distribution(ctx, c, card);
    return el('section', { className: `card eda-card${wide ? ' eda-wide' : ''}`, 'aria-labelledby': id, 'data-eda-card': card.slot,
      'data-activity': card.activity, 'data-current': card.current ? 'true' : 'false', 'data-nav': `result:${card.resultId}` },
    [header(ctx, c, card, titleOf(c, card), id), ...body]);
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

  function requestCard(ctx, c, data, task) {
    const model = data.model;
    // Training-row charts only (WP-A7): the per-column activities of the catalog.
    const perColumn = arr(model.catalog).filter(a => a.perColumn && PER_COLUMN.includes(a.activity));
    const runnable = perColumn.filter(a => a.runnable);
    const out = [el('h3', { id: 'eda-request-title', text: c.requestTitle })];
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
      const tags = col => [col.role, unavailable.has(col.name) ? c.notAtPrediction : null].filter(Boolean);
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
      out.push(el('label', { for: 'eda-variable', text: c.variable }), variable,
        unavailable.has(memory.column) ? el('p', { className: 'muted', 'data-not-at-prediction': memory.column,
          text: c.notAtPredictionHint(memory.column) }) : null,
        el('label', { for: 'eda-chart', text: c.chart }), chart,
        question ? el('p', { className: 'eda-request-question', 'data-request-question': entry.activity }, [
          el('span', { className: 'muted', text: c.answers }), ` ${question}`]) : null,
        entry && READS_TARGET.includes(entry.activity) && !shown
          ? el('p', { className: 'muted', 'data-one-more-look': true, text: c.oneMoreLook }) : null,
        el('div', {}, [action]));
    }
    out.push(el('p', { className: 'muted', 'data-hint': true }, [c.hint]),
      el('button', { type: 'button', className: 'secondary', 'data-open': 'workbench', text: c.openWorkbench,
        onclick: () => ctx.send({ type: 'open_artifact', artifact: 'workbench' }) }));
    const o = memory.outcome;
    if (o) {
      const region = el('div', { 'data-eda-outcome': o.kind }, [ctx.renderOutcome(o)]);
      if (o.recorded && o.recorded.slot) region.appendChild(el('p', { className: 'muted', text: c.recorded(o.recorded.slot, o.recorded.status || '') }));
      out.push(region);
    }
    return el('section', { className: 'card eda-card eda-request', 'aria-labelledby': 'eda-request-title', 'data-eda-request': task }, out);
  }

  // --- the tab --------------------------------------------------------------------------------

  function banner(ctx, c, data, model) {
    const seen = data.model.rowsSeen || {};
    const fmt = n => ctx.format.number(n, 'int');
    const ft = model && model.finalTest;
    const looks = model && model.edaLooks && Number.isInteger(model.edaLooks.targetLooks) ? model.edaLooks.targetLooks : null;
    return el('div', { className: 'eda-banner', role: 'note' }, [
      el('p', {}, [el('strong', { text: c.bannerLead }), ` ${c.bannerText}`]),
      ft && ft.status === 'sealed' && Number.isInteger(ft.rows)
        ? el('p', { className: 'eda-banner-seal', 'data-banner-seal': true }, [el('span', { className: 'ht-status ht-st-sealed', text: c.sealedChip }),
          ` ${c.sealedRows(fmt(ft.rows))}`]) : null,
      ft && ft.status === 'absent' ? el('p', { className: 'eda-banner-seal', 'data-banner-seal': 'absent', text: c.noFinalTest }) : null,
      el('p', { className: 'ht-mono eda-seen' }, [`${c.rowsSeen} · ${c.train} `,
        el('span', { 'data-rows-seen': 'train', 'data-value': String(seen.trainEda || 0), text: fmt(seen.trainEda || 0) }),
        ` · ${c.validation} `,
        el('span', { 'data-rows-seen': 'validation', 'data-value': String(seen.validationEda || 0), text: fmt(seen.validationEda || 0) })]),
      looks !== null ? el('p', { className: 'eda-looks', 'data-looks': String(looks) }, [
        el('strong', {}, [c.looksLead, el('span', { 'data-looks-count': true, text: fmt(looks) })]), ` ${c.looksText}`]) : null,
      Number.isInteger(seen.validationModels) ? el('p', { className: 'muted' }, [`${c.validationModels} `,
        el('span', { 'data-rows-seen': 'validation-models', 'data-value': String(seen.validationModels), text: fmt(seen.validationModels) })]) : null,
    ]);
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
      const c = ctx.copy.eda[task];
      const out = [el('h2', { text: c.heading }), dataSection(ctx, c, task)];
      if (!data) {
        if (error) {
          out.push(el('div', { className: 'card alert', role: 'alert', 'data-eda-error': true }, [
            el('p', { className: 'title', text: c.loadError }), el('p', { text: error.message }),
            error.detail ? el('details', {}, [el('summary', { text: c.loadErrorDetail }), el('pre', { text: error.detail })]) : null,
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
      const cards = arr(data.model.cards);
      // The structural quality check reads the development rows without the target: it
      // belongs with the data card, before the training-row exploration.
      cards.filter(k => k.kind === 'quality').forEach((card, i) => out.push(qualityCard(ctx, c, card, i)));
      const gallery = cards.filter(k => k.kind !== 'quality');
      out.push(el('h3', { className: 'eda-section-title', text: c.explorationTitle }));
      out.push(banner(ctx, c, data, model));
      if (ctx.snapshot && !ctx.fresh(data)) out.push(el('p', { className: 'muted', 'data-updating': true, text: c.updating }));
      if (error) out.push(el('p', { className: 'alert', role: 'alert', 'data-eda-error': true, text: `${c.loadError} ${error.message}` }));
      const grid = el('div', { className: 'eda-gallery', 'aria-label': c.galleryLabel });
      if (!gallery.length) out.push(el('p', { className: 'muted', 'data-eda-empty': true, text: c.empty }));
      gallery.forEach((card, i) => grid.appendChild(cardNode(ctx, c, card, i, task)));
      grid.appendChild(requestCard(ctx, c, data, task));
      out.push(grid);
      return out;
    },
  });
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
