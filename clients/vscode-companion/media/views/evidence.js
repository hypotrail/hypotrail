// Evidence view (COMPANION-ADVANCED §6.4, stage v2). WP-U3.
//
// Left: the results registry with the filter Current / Stale / All. Right: the detail of
// the chosen result (facts, report and notebook, stale reason, uncertainty of an
// evaluation). Below: its lineage (chips, impact sentences, a table toggle) and the
// exposure ledger. Data: the `evidence` view, loaded by this view itself because it carries
// the chosen `resultId` (`evidence --result <rid>` holds the list too, so one read serves
// both columns). Figures appear only for current, verified results (INV-7); stale ones read
// "Not cited". Navigation targets: `data-nav="result:<rid>"` on the detail (deep links, "go
// to a result", chips of other tabs).
(function (HT) {
  'use strict';
  const RID = /^[0-9a-f]{64}$/;
  const FILTERS = ['current', 'stale', 'all'];
  const MAX_ROWS = 200;
  const requested = {};
  let tableOpen = false;
  let copyNote = null;

  const C = () => HT.copy.evidence;
  const int = (ctx, n) => (n === null || n === undefined ? '' : ctx.format.number(n, 'int'));
  const pct = (ctx, x) => ctx.format.number(x, 'pct1');
  const signed = (text, x) => (x > 0 ? `+${text}` : text);

  function selected(ctx) {
    const id = ctx.ui.get('selectedResult');
    return typeof id === 'string' && RID.test(id) ? id : null;
  }

  function filterOf(ctx) {
    const f = ctx.ui.get('evidenceFilter');
    return FILTERS.includes(f) ? f : 'current';
  }

  /** Ask for the evidence (with the chosen result) once per revision and choice. */
  function ensureLoad(ctx) {
    const snap = ctx.snapshot;
    if (!snap) return;
    const sel = selected(ctx);
    const d = ctx.data('evidence');
    if (d && d.revision >= snap.revision && (d.resultId || null) === sel) return;
    const key = `${snap.revision}|${sel || ''}`;
    if (requested[key]) return;
    requested[key] = true;
    ctx.load('evidence', sel ? { resultId: sel } : undefined);
  }

  function choose(ctx, id) {
    ctx.ui.set('selectedResult', id || undefined);
    ctx.rerender();
  }

  function fitLabel(task, fit) {
    const c = C();
    if (fit === 'fit.baseline') return c.reference[task === 'regression' ? 'regression' : 'binary'];
    return c.fits[fit] || fit;
  }

  // --- ask the agent (§6.8): a modal with an empty question; the bridge builds the text ---

  function askAgent(ctx, about, label, fallbackQuestion) {
    const c = C().ask;
    let area = null;
    const body = ctx.el('div', {}, [
      ctx.el('p', {}, [ctx.el('strong', { text: `${c.about}: ` }), label]),
      ctx.el('label', { for: 'ht-ev-ask', text: c.question }),
      (area = ctx.wordsArea({ kind: 'askDraft', id: 'ht-ev-ask' })),
      ctx.el('p', { className: 'muted', text: c.note }),
    ]);
    const actions = [{ label: c.copy, value: 'copy', primary: true }];
    if (ctx.chatInsert) actions.push({ label: c.insert, value: 'insert' });
    ctx.modal({ title: c.title, body, actions }).then(mode => {
      if (!mode) return;
      const typed = area ? area.value.trim() : '';
      ctx.send({ type: 'ask_agent', about, question: (typed || fallbackQuestion || '').slice(0, 2000), mode });
      ctx.ui.set('askDraft', undefined);
    });
  }

  // --- results registry --------------------------------------------------------------------

  function visible(results, filter) {
    if (filter === 'current') return results.filter(r => r.promoted && r.current);
    if (filter === 'stale') return results.filter(r => !r.current);
    return results;
  }

  function filterGroup(ctx, filter) {
    const c = C();
    return ctx.el('fieldset', { className: 'ht-ev-filter', 'data-evidence-filter': filter }, [
      ctx.el('legend', { className: 'sr-only', text: c.filterLabel }),
      ...FILTERS.map(f => ctx.el('label', { className: 'ht-ev-radio' }, [
        ctx.el('input', { type: 'radio', name: 'ht-ev-filter', id: `ht-ev-filter-${f}`, value: f, checked: f === filter,
          onchange: () => { ctx.ui.set('evidenceFilter', f); ctx.rerender(); } }),
        c.filters[f],
      ])),
    ]);
  }

  function resultRow(ctx, r, sel) {
    const c = C();
    const right = r.current && r.headline
      ? ctx.components.segments(ctx.el('span', { className: 'ht-ev-headline' }), r.headline)
      : ctx.el('span', { className: 'ht-ev-headline muted', text: r.current ? '' : c.notCited });
    return ctx.el('li', {}, [ctx.el('button', {
      type: 'button', className: 'ht-ev-item', 'data-result-item': r.resultId, 'aria-pressed': r.resultId === sel ? 'true' : 'false',
      'data-current': r.current ? 'true' : 'false', onclick: () => choose(ctx, r.resultId),
    }, [
      ctx.el('span', { className: 'ht-ev-slot' }, [
        r.slot || r.activity,
        r.current ? null : ctx.el('span', { className: 'ht-ev-badge', 'data-stale': true,
          text: r.integrity && r.integrity !== 'ok' ? c.integrityBadge : c.staleBadge }),
      ]),
      right,
    ])]);
  }

  function registry(ctx, model, sel) {
    const c = C();
    const filter = filterOf(ctx);
    const items = visible(model.results, filter);
    const shown = items.slice(0, MAX_ROWS);
    return ctx.el('section', { className: 'card ht-ev-registry', 'aria-labelledby': 'ht-ev-results' }, [
      ctx.el('h3', { id: 'ht-ev-results', text: c.resultsTitle }),
      filterGroup(ctx, filter),
      shown.length ? ctx.el('ul', { className: 'ht-ev-list', 'data-results': filter }, shown.map(r => resultRow(ctx, r, sel)))
        : ctx.el('p', { className: 'muted', text: c.empty[filter] }),
      items.length > shown.length ? ctx.el('p', { className: 'muted', text: c.more(items.length - shown.length) }) : null,
      model.truncated ? ctx.el('p', { className: 'muted', text: c.truncated }) : null,
    ]);
  }

  // --- result detail -----------------------------------------------------------------------

  function excludedFeatures(ctx, detail) {
    const d = ctx.snapshot && ctx.snapshot.decisions && ctx.snapshot.decisions.feature_availability;
    if (!d || !d.value) return [];
    let value = null;
    try { value = JSON.parse(d.value); } catch (_) { return []; }
    if (!value || typeof value !== 'object') return [];
    const used = new Set((detail.features && detail.features.names) || []);
    return [...(value.not_available || []), ...(value.uncertain_excluded || [])].map(String).filter(f => !used.has(f));
  }

  function facts(ctx, detail, task) {
    const c = C();
    const rows = [];
    const add = (label, value) => { if (value !== null && value !== undefined && value !== '') rows.push(ctx.el('dt', { text: label }), ctx.el('dd', {}, [value])); };
    if (detail.current) {
      const parts = [detail.partition, detail.nRows !== null ? c.rows(int(ctx, detail.nRows)) : null,
        task === 'binary' && detail.nPositive !== null ? c.positives(int(ctx, detail.nPositive)) : null].filter(Boolean);
      add(c.facts.evaluatedOn, parts.join(' · '));
      if (detail.headline && detail.headline.length) add(c.facts.headline, ctx.components.segments(ctx.el('span'), detail.headline));
    } else if (detail.partition) {
      add(c.facts.evaluatedOn, detail.partition);
    }
    if (detail.features && (detail.features.count > 0 || detail.slot === 'fit.baseline')) {
      add(c.facts.features, c.features(detail.features.count, excludedFeatures(ctx, detail)));
    }
    add(c.facts.preprocessing, detail.preprocessing);
    if (detail.code && detail.code.modules.length) {
      const names = detail.code.modules.map(m => m.name).join(', ');
      add(c.facts.code, ctx.el('span', { className: 'ht-mono', 'data-code': detail.code.changed.length ? 'changed' : 'matches',
        text: detail.code.changed.length ? c.codeChangedSince(names, detail.code.changed.join(', ')) : c.fingerprintMatches(names) }));
    }
    if (detail.exposure) {
      add(c.facts.exposure, c.exposure(c.purposes[detail.exposure.purpose] || detail.exposure.purpose, detail.exposure.partition,
        detail.exposure.rows !== null ? c.rows(int(ctx, detail.exposure.rows)) : null));
    }
    return ctx.el('dl', { className: 'ht-ev-facts' }, rows);
  }

  function staleBox(ctx, detail) {
    const c = C();
    const why = detail.staleReason;
    if (detail.current || !why) return null;
    const lines = [why.reason,
      why.codeChanged.length ? c.codeChanged(why.codeChanged.join(', ')) : null,
      why.upstreamNotCurrent.length ? c.upstreamNotCurrent(why.upstreamNotCurrent.join(', ')) : null,
      why.sourcesChanged ? c.sourcesChanged : null].filter(Boolean);
    return ctx.el('div', { className: 'card ht-warn', 'data-stale-reason': true }, [
      ctx.el('p', { className: 'title', text: c.staleTitle }),
      ctx.el('ul', {}, lines.map(l => ctx.el('li', { text: l }))),
    ]);
  }

  function deltaSentence(ctx, delta) {
    const c = C();
    const text = delta.side === 'one_side' ? c.oneSide : delta.side === 'includes_zero' ? c.includesZero : c.undefinedDelta;
    return ctx.el('p', { 'data-delta-sentence': delta.side, text });
  }

  function intervalText(fmt, low, high) {
    return low === null || high === null ? '' : `[${fmt(low)}, ${fmt(high)}]`;
  }

  function metricBlock(ctx, u, task, metric, fmt, deltaFmt, label, unit) {
    const c = C();
    const level = u.bootstrap.level !== null ? pct(ctx, u.bootstrap.level).replace('.0%', '%') : '';
    const box = ctx.el('div', { className: 'ht-ev-metric', 'data-metric': metric.metric });
    const notDefined = task === 'binary' ? c.binary.notDefined : '';
    ctx.components.intervalRows(box, {
      title: c.intervalTitle(label, level),
      zero: false,
      rows: metric.models.map(m => ({ label: fitLabel(task, m.fit), point: m.point, low: m.low, high: m.high,
        pointText: m.point === null ? notDefined : `${fmt(m.point)}${unit}`, intervalText: intervalText(fmt, m.low, m.high) })),
    });
    if (metric.delta) {
      const d = metric.delta;
      const cand = fitLabel(task, d.fit);
      const ref = fitLabel(task, u.reference);
      ctx.components.intervalRows(box, {
        title: c.differenceTitle(label, cand, ref),
        zero: true,
        rows: [{ label: c.difference(cand, ref), point: d.point, low: d.low, high: d.high,
          pointText: d.point === null ? notDefined : `${signed(deltaFmt(d.point), d.point)}${unit}`,
          intervalText: intervalText(x => signed(deltaFmt(x), x), d.low, d.high) }],
      });
      box.appendChild(deltaSentence(ctx, d));
    }
    return box;
  }

  function uncertainty(ctx, u, task) {
    const c = C();
    if (!u) return null;
    const replicates = u.bootstrap.replicates !== null ? int(ctx, u.bootstrap.replicates) : '';
    const level = u.bootstrap.level !== null ? pct(ctx, u.bootstrap.level).replace('.0%', '%') : '';
    const blocks = [];
    if (u.kind === 'policy') {
      for (const rule of u.rules) {
        blocks.push(ctx.el('h4', { text: c.binary.rule(rule.rule) }));
        for (const m of rule.metrics) {
          blocks.push(metricBlock(ctx, u, 'binary', m, x => pct(ctx, x), x => ctx.format.number(x, 'f3'), c.binary.metrics[m.metric], ''));
        }
      }
    } else {
      const unit = u.unit ? ` ${u.unit}` : '';
      for (const m of u.metrics) {
        blocks.push(metricBlock(ctx, u, 'regression', m, x => ctx.format.number(x, 'f2'), x => ctx.format.number(x, 'f2'), c.metrics[m.metric], unit));
      }
    }
    return ctx.el('section', { className: 'ht-ev-uncertainty', 'data-uncertainty': u.kind, 'aria-labelledby': 'ht-ev-unc' }, [
      ctx.el('h3', { id: 'ht-ev-unc', text: c.uncertaintyTitle }),
      ...blocks,
      replicates ? ctx.el('p', { className: 'muted', 'data-bootstrap': true, text: c.bootstrap(replicates, level) }) : null,
    ]);
  }

  function smallData(ctx, detail) {
    const top = (ctx.snapshot && ctx.snapshot.notYetDefensible && ctx.snapshot.notYetDefensible.top) || [];
    const slot = detail.slot || '';
    const ids = /^(policy\.evaluation|evaluate\.regression|fit\.)/.test(slot)
      ? ['small_validation_partition', 'capacity_exceeds_validation'] : /^eda\./.test(slot) ? ['high_cardinality_grouping'] : [];
    const items = top.filter(i => ids.includes(i.id));
    return items.map(i => ctx.el('div', { className: 'card ht-warn', role: 'note', 'data-small-data': i.id }, [ctx.el('p', { text: i.text })]));
  }

  function copyId(ctx, detail, code) {
    const c = C();
    const done = text => { copyNote = { id: detail.resultId, text }; ctx.rerender(); };
    const select = () => {
      const details = code.closest('details');
      if (details) details.open = true;
      const range = document.createRange();
      range.selectNodeContents(code);
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
    };
    try {
      if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
        navigator.clipboard.writeText(detail.resultId).then(() => done(c.copied), () => { select(); copyNote = { id: detail.resultId, text: c.copyFallback }; });
        return;
      }
    } catch (_) { /* fall back to a selection */ }
    select();
    copyNote = { id: detail.resultId, text: c.copyFallback };
  }

  function detailSection(ctx, model, sel, task) {
    const c = C();
    const head = [ctx.el('h3', { id: 'ht-ev-detail-title', className: 'sr-only', text: c.detailTitle })];
    if (!sel) return ctx.el('section', { className: 'card ht-ev-detail', 'aria-labelledby': 'ht-ev-detail-title' }, [...head, ctx.el('p', { className: 'muted', text: c.choose })]);
    const detail = model && model.detail && model.detail.resultId === sel ? model.detail : null;
    if (!detail) {
      return ctx.el('section', { className: 'card ht-ev-detail', 'aria-busy': 'true', 'aria-labelledby': 'ht-ev-detail-title' },
        [...head, ctx.el('p', { className: 'muted', text: c.readingDetail })]);
    }
    const code = ctx.el('code', { className: 'ht-mono', 'data-full-id': true, text: detail.resultId });
    const report = detail.reportAnchor
      ? ctx.el('button', { type: 'button', className: 'secondary', 'data-show-in-report': detail.resultId, text: c.showInReport,
        onclick: () => ctx.send({ type: 'open_artifact', artifact: 'report', resultId: detail.resultId }) })
      : ctx.el('button', { type: 'button', className: 'secondary', disabled: true, 'aria-describedby': 'ht-ev-not-in-report',
        'data-show-in-report': detail.resultId, text: c.showInReport });
    const note = copyNote && copyNote.id === detail.resultId ? copyNote.text : null;
    return ctx.el('section', { className: 'card ht-ev-detail', 'data-nav': `result:${detail.resultId}`, 'data-detail': detail.resultId,
      'aria-labelledby': 'ht-ev-detail-h' }, [
      ctx.el('div', { className: 'ht-ev-head' }, [
        ctx.el('h2', { id: 'ht-ev-detail-h', text: detail.slot || detail.activity }),
        ctx.el('span', { className: 'ht-mono muted', 'data-currency': detail.current ? 'current' : 'stale', text: c.idLine(detail.rid8, detail.current) }),
        ctx.el('button', { type: 'button', className: 'ht-link', 'data-copy-id': true, text: c.copyId, onclick: () => copyId(ctx, detail, code) }),
      ]),
      ctx.el('details', { className: 'ht-ev-fullid' }, [ctx.el('summary', { text: c.fullId }), code]),
      note ? ctx.el('p', { className: 'muted', role: 'status', text: note }) : null,
      staleBox(ctx, detail),
      facts(ctx, detail, task),
      ...smallData(ctx, detail),
      ctx.el('div', { className: 'ht-ev-actions' }, [
        report,
        ctx.el('button', { type: 'button', className: 'secondary', 'data-show-in-notebook': detail.resultId, disabled: !detail.notebookHint,
          'aria-describedby': detail.notebookHint ? 'ht-ev-notebook-hint' : null, text: c.showInNotebook,
          onclick: () => ctx.send({ type: 'open_artifact', artifact: 'notebook' }) }),
        ctx.el('button', { type: 'button', className: 'secondary', 'data-ask-agent': 'result', text: c.askAgent,
          onclick: () => askAgent(ctx, { kind: 'result', id: detail.resultId }, c.ask.result(detail.slot || detail.activity, detail.rid8)) }),
      ]),
      detail.reportAnchor ? null : ctx.el('p', { id: 'ht-ev-not-in-report', className: 'muted', text: c.notInReport }),
      detail.notebookHint ? ctx.el('p', { id: 'ht-ev-notebook-hint', className: 'muted',
        text: c.notebookHint(detail.notebookHint.search, detail.notebookHint.path) }) : null,
      detail.current ? uncertainty(ctx, detail.uncertainty, task) : null,
    ]);
  }

  // --- lineage -----------------------------------------------------------------------------

  function chipStatus(chip) {
    const c = C();
    if (chip.kind === 'source') return c.sourceStatus(chip.label, chip.status === 'ok');
    if (chip.decision) return c.yourDecision;
    return c.status[chip.status] || chip.status;
  }

  function lineage(ctx, model, sel) {
    const c = C();
    const detail = model && model.detail && model.detail.resultId === sel ? model.detail : null;
    const body = [];
    if (!detail) {
      body.push(ctx.el('p', { className: 'muted', text: c.lineageChoose }));
    } else {
      const chain = detail.chain;
      body.push(ctx.el('ol', { className: 'ht-chain', 'aria-label': c.lineageLabel(detail.slot || detail.activity), 'data-chain': detail.resultId },
        chain.map((chip, i) => ctx.el('li', { className: 'ht-chain-item' }, [
          i > 0 ? ctx.el('span', { className: 'ht-chain-arrow', 'aria-hidden': 'true', text: '→' }) : null,
          ctx.el('span', { className: `ht-chip ht-chip-${chip.role}${chip.status === 'stale' || chip.status === 'changed' ? ' ht-chip-warn' : ''}`,
            'data-chain-node': chip.name, 'data-kind': chip.kind }, [
            ctx.el('span', { className: 'sr-only', text: `${c.kinds[chip.kind] || chip.kind}: ` }),
            ctx.el('span', { className: 'ht-chip-name', text: chip.name }),
            ctx.el('span', { className: 'ht-chip-status', text: chipStatus(chip) }),
          ]),
        ]))));
      const sentences = detail.impacts.map(i => ctx.el('li', { 'data-impact': i.decisionId,
        text: c.impact(i.decisionId.replace(/_/g, ' '), i.change, i.staleSlots.join(', '), i.keptFits.join(', ')) }));
      body.push(sentences.length ? ctx.el('ul', { className: 'ht-ev-impacts' }, sentences)
        : ctx.el('p', { className: 'muted', 'data-impact': 'none', text: c.noImpact }));
      const toggle = ctx.el('button', { type: 'button', className: 'ht-link', 'aria-expanded': tableOpen ? 'true' : 'false',
        'aria-controls': 'ht-ev-lineage-table', text: tableOpen ? c.hideTable : c.showTable,
        onclick: () => { tableOpen = !tableOpen; ctx.rerender(); } });
      body.push(toggle);
      const wrap = ctx.el('div', { id: 'ht-ev-lineage-table', hidden: tableOpen ? null : true });
      if (tableOpen) {
        ctx.components.valuesTable(wrap, { caption: c.nodesCaption,
          columns: [{ key: 'name', label: c.nodeColumns.name }, { key: 'kind', label: c.nodeColumns.kind }, { key: 'status', label: c.nodeColumns.status }],
          rows: chain.map(chip => ({ name: chip.name, kind: c.kinds[chip.kind] || chip.kind, status: chipStatus(chip) })) });
        ctx.components.valuesTable(wrap, { caption: c.edgesCaption,
          columns: [{ key: 'from', label: c.edgeColumns.from }, { key: 'to', label: c.edgeColumns.to }, { key: 'role', label: c.edgeColumns.role }],
          rows: detail.lineageEdges });
      }
      body.push(wrap);
    }
    return ctx.el('section', { className: 'card ht-ev-lineage', 'aria-labelledby': 'ht-ev-lineage-h' }, [
      ctx.el('h3', { id: 'ht-ev-lineage-h', text: c.lineageTitle }),
      ctx.el('p', { className: 'muted', text: c.lineageIntro }),
      ...body,
    ]);
  }

  // --- exposure ledger ---------------------------------------------------------------------

  function ledger(ctx, model) {
    const c = C();
    const top = (ctx.snapshot && ctx.snapshot.notYetDefensible && ctx.snapshot.notYetDefensible.top) || [];
    const limits = top.filter(i => i.id === 'validation_is_not_independent' || i.id === 'public_data_already_explored');
    const head = ctx.el('thead', {}, [ctx.el('tr', {}, ['purpose', 'partition', 'rows', 'activities']
      .map(k => ctx.el('th', { scope: 'col', text: c.ledgerColumns[k] })))]);
    const rows = model.ledger.map(row => ctx.el('tr', { 'data-ledger-row': `${row.purpose}:${row.partition}`,
      className: row.selection ? 'ht-ledger-selection' : null }, [
      ctx.el('td', {}, [c.purposes[row.purpose] || row.purpose,
        row.selection ? ctx.el('span', { className: 'sr-only', text: ` (${c.usedToChoose})` }) : null]),
      ctx.el('td', { text: row.partition }),
      ctx.el('td', { 'data-rows': row.rows === null ? '' : String(row.rows), text: int(ctx, row.rows) }),
      ctx.el('td', { text: row.activities.join(', ') }),
    ]));
    return ctx.el('section', { className: 'card ht-ev-ledger', 'aria-labelledby': 'ht-ev-ledger-h', 'data-ledger': true }, [
      ctx.el('h3', { id: 'ht-ev-ledger-h', text: c.ledgerTitle }),
      rows.length ? ctx.el('table', { className: 'ht-values ht-ledger' }, [ctx.el('caption', { className: 'sr-only', text: c.ledgerTitle }), head,
        ctx.el('tbody', {}, rows)]) : ctx.el('p', { className: 'muted', text: c.ledgerEmpty }),
      ...limits.map(i => ctx.el('p', { className: 'hold', 'data-limit': i.id, text: i.text })),
      model.splitOverlap ? ctx.el('p', { className: 'hold', 'data-split-unseen': true, text: c.splitUnseen }) : null,
    ]);
  }

  // --- the tab -----------------------------------------------------------------------------

  function render(summary, ctx) {
    const c = C();
    ensureLoad(ctx);
    const d = ctx.data('evidence');
    const error = ctx.error('evidence');
    const sel = selected(ctx);
    const root = ctx.el('div', { className: 'ht-evidence' }, [ctx.el('h2', { className: 'sr-only', text: c.title })]);
    if (error) {
      root.appendChild(ctx.el('div', { className: 'card alert', role: 'alert', 'data-evidence-error': true }, [
        ctx.el('p', { className: 'title', text: c.loadError }),
        ctx.el('p', { text: error.message }),
        error.detail ? ctx.el('pre', { text: error.detail }) : null,
        sel ? ctx.el('button', { type: 'button', className: 'secondary', text: c.showList, onclick: () => choose(ctx, null) }) : null,
        ctx.el('button', { type: 'button', className: 'secondary', text: c.retry, onclick: () => {
          for (const k of Object.keys(requested)) delete requested[k];
          ctx.load('evidence', sel ? { resultId: sel } : undefined);
        } }),
      ]));
    }
    if (!d) {
      if (!error) root.appendChild(ctx.el('p', { className: 'muted', 'aria-busy': 'true', 'data-loading': 'evidence', text: c.reading }));
      return root;
    }
    const model = d.model;
    const task = model.task || (summary && summary.task) || 'binary';
    const stale = summary && d.revision < summary.revision;
    if (stale) root.appendChild(ctx.el('p', { className: 'muted', role: 'status', 'data-updating': true, text: c.updating }));
    root.appendChild(ctx.el('div', { className: `ht-ev-grid${stale ? ' ht-pending' : ''}` }, [
      registry(ctx, model, sel),
      detailSection(ctx, model, sel, task),
    ]));
    root.appendChild(lineage(ctx, model, sel));
    root.appendChild(ledger(ctx, model));
    return root;
  }

  HT.register('evidence', {
    tab: 'evidence',
    stage: 'v2',
    views: [],
    render,
    onMessage(m, ctx) {
      if (m.type === 'navigate' && m.tab === 'evidence' && m.kind === 'result' && RID.test(m.id)) {
        ctx.ui.set('selectedResult', m.id);
        ctx.rerender();
      }
      return undefined;
    },
  });
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
