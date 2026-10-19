// EDA view (COMPANION-ADVANCED §6.3; stage v2). A gallery of the registered EDA results
// only: every chart is an engine result of the training rows, every number is an engine
// value cited with its result id (INV-7), and bar lengths are geometry (INV-14). "Request a
// chart" offers only the per-column activities and columns of the engine's `eda_catalog`
// and sends `run_eda` (W4); the controller checks it again before any `run`. There is no
// partition control: free exploration belongs in the workbench notebook. Owned by WP-U4.
(function (HT) {
  'use strict';
  const el = HT.el;
  const arr = x => (Array.isArray(x) ? x : []);
  const str = x => (typeof x === 'string' ? x : '');
  const PER_COLUMN = ['eda.distribution', 'eda.rate_by', 'eda.mean_by'];

  // View memory (in this webview only; nothing here is study state): the Request choice
  // and the last W4 outcome, rendered in the Request card (`outcomes: ['W4']`).
  const memory = { column: null, activity: null, outcome: null };

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

  /** The axis maximum of a bar chart: the largest value rounded up to the next step. */
  function axisMax(values, step) {
    const top = Math.max(0, ...values.filter(v => typeof v === 'number' && Number.isFinite(v)));
    return top > 0 ? Math.ceil(top / step - 1e-9) * step : step;
  }

  function header(ctx, c, card, title, id) {
    const rid8 = card.resultId.slice(0, 8);
    return el('div', { className: 'eda-card-head' }, [
      el('h3', { id, text: title }),
      el('button', { type: 'button', className: 'ht-link ht-mono eda-chip', 'data-chip': card.resultId,
        'aria-label': c.chipLabel(rid8), text: c.chip(card.slot || card.activity, rid8),
        onclick: () => ctx.navigate({ tab: 'evidence', kind: 'result', id: card.resultId }) }),
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
        valueText: `${text(ctx, r.rate)} ${c.ofRows} ${text(ctx, r.nRows)}`,
        cited: { resultId: rid, path: r.rate.path, value: r.rate.value },
      }));
      out.push(ctx.components.bars(el('div'), { title: c.specialChart, items, max: axisMax(items.map(i => i.value), 0.05),
        unit: c.specialMeasureHead }));
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

  function byColumn(ctx, c, card, task) {
    const d = card.data;
    const rid = card.resultId;
    const column = card.column || d.column;
    const groups = [...d.groups, ...(d.other ? [{ ...d.other, label: c.other }] : [])];
    const items = groups.filter(g => g.value).map(g => ({
      label: g.label, value: g.value.value, small: g.small,
      valueText: task === 'binary' ? `${text(ctx, g.value)} ${c.ofRows} ${text(ctx, g.nRows)}`
        : `${text(ctx, g.value)} · ${text(ctx, g.nRows)} ${c.rows}`,
      cited: { resultId: rid, path: g.value.path, value: g.value.value },
    }));
    const step = task === 'binary' ? 0.05 : 5;
    const max = axisMax(items.map(i => i.value), step);
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
        { key: 'extra', label: c.extraHead }, { key: 'value', label: c.measureHead }, { key: 'small', label: c.smallHead }],
      rows: groups.map(g => ({ label: g.label, rows: cell(ctx, g.nRows, rid),
        extra: cell(ctx, task === 'binary' ? g.nPositive : g.sd, rid), value: cell(ctx, g.value, rid), small: g.small ? c.small : '' })),
    });
    return [
      chart,
      el('p', { className: 'muted eda-scale', 'aria-hidden': 'true', 'data-literal': 'axis', text: scaleText }),
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

  function cardNode(ctx, c, card, i, task) {
    const id = `eda-card-${i}`;
    const wide = card.kind === 'rate_by' || card.kind === 'mean_by' || (card.kind === 'special_values' && card.current);
    let body;
    if (!card.current || !card.data) {
      body = [el('p', { className: 'status status-stale', 'data-stale': true, text: c.stale })];
    } else if (card.kind === 'target_rate') body = targetRate(ctx, c, card);
    else if (card.kind === 'target_summary') body = targetSummary(ctx, c, card);
    else if (card.kind === 'special_values') body = specialValues(ctx, c, card, task);
    else if (card.kind === 'rate_by' || card.kind === 'mean_by') body = byColumn(ctx, c, card, task);
    else body = distribution(ctx, c, card);
    return el('section', { className: `card eda-card${wide ? ' eda-wide' : ''}`, 'aria-labelledby': id, 'data-eda-card': card.slot,
      'data-activity': card.activity, 'data-current': card.current ? 'true' : 'false', 'data-nav': `result:${card.resultId}` },
    [header(ctx, c, card, titleOf(c, card), id), ...body]);
  }

  // --- Request a chart --------------------------------------------------------------------

  function requestCard(ctx, c, data, task) {
    const model = data.model;
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
      const variable = el('select', { id: 'eda-variable', 'data-request': 'column',
        onchange: e => { memory.column = e.target.value; memory.activity = null; ctx.rerender(); } },
      columns.map(col => el('option', { value: col.name, selected: col.name === memory.column ? true : null,
        text: col.role ? `${col.name} (${col.role})` : col.name })));
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
      out.push(el('label', { for: 'eda-variable', text: c.variable }), variable,
        el('label', { for: 'eda-chart', text: c.chart }), chart, el('div', {}, [action]));
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

  function banner(ctx, c, data) {
    const seen = data.model.rowsSeen || {};
    const fmt = n => ctx.format.number(n, 'int');
    return el('div', { className: 'eda-banner', role: 'note' }, [
      el('p', {}, [el('strong', { text: c.bannerLead }), ` ${c.bannerText}`]),
      el('p', { className: 'ht-mono eda-seen' }, [`${c.rowsSeen} · ${c.train} `,
        el('span', { 'data-rows-seen': 'train', 'data-value': String(seen.trainEda || 0), text: fmt(seen.trainEda || 0) }),
        ` · ${c.validation} `,
        el('span', { 'data-rows-seen': 'validation', 'data-value': String(seen.validationEda || 0), text: fmt(seen.validationEda || 0) })]),
      Number.isInteger(seen.validationModels) ? el('p', { className: 'muted' }, [`${c.validationModels} `,
        el('span', { 'data-rows-seen': 'validation-models', 'data-value': String(seen.validationModels), text: fmt(seen.validationModels) })]) : null,
    ]);
  }

  HT.register('eda', {
    tab: 'eda',
    stage: 'v2',
    views: ['eda'],
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
      const out = [el('h2', { text: c.heading })];
      if (!data) {
        if (error) {
          out.push(el('div', { className: 'card alert', role: 'alert', 'data-eda-error': true }, [
            el('p', { className: 'title', text: c.loadError }), el('p', { text: error.message }),
            error.detail ? el('details', {}, [el('summary', { text: c.loadErrorDetail }), el('pre', { text: error.detail })]) : null,
            el('button', { type: 'button', className: 'secondary', text: c.retry, onclick: () => ctx.load('eda') }),
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
      out.push(banner(ctx, c, data));
      if (ctx.snapshot && data.revision < ctx.snapshot.revision) out.push(el('p', { className: 'muted', 'data-updating': true, text: c.updating }));
      if (error) out.push(el('p', { className: 'alert', role: 'alert', 'data-eda-error': true, text: `${c.loadError} ${error.message}` }));
      const cards = arr(data.model.cards);
      const gallery = el('div', { className: 'eda-gallery', 'aria-label': c.galleryLabel });
      if (!cards.length) out.push(el('p', { className: 'muted', 'data-eda-empty': true, text: c.empty }));
      cards.forEach((card, i) => gallery.appendChild(cardNode(ctx, c, card, i, task)));
      gallery.appendChild(requestCard(ctx, c, data, task));
      out.push(gallery);
      return out;
    },
  });
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
