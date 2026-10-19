// Evidence view (COMPANION-ADVANCED §6.4, stage v2). WP-U3; reordered by WP-B5 (v0.2b).
//
// WP-B5: the tab leads with the final test (sealed, opened once in the junior's words,
// changed after the opening, or absent) and the trial count, then the exposure ledger in
// words, then the development evidence (the cross-validation scheme and its spread across
// folds, the variant against the candidate) apart from the final evidence (measured once),
// then the diagnostics when the engine has them, then the results registry (development
// and final-test results listed apart), the detail, and the lineage. Opening the final
// test is a chat act: no control here offers it.
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

  // The intervalRows component sizes its label and text columns to their texts (WP-I).
  function intervals(ctx, container, options) {
    return ctx.components.intervalRows(container, options);
  }

  function selected(ctx) {
    const id = ctx.ui.get('selectedResult');
    return typeof id === 'string' && RID.test(id) ? id : null;
  }

  function filterOf(ctx) {
    const f = ctx.ui.get('evidenceFilter');
    return FILTERS.includes(f) ? f : 'current';
  }

  /** Ask for the evidence (with the chosen result) once per version and choice (CR.1). */
  function ensureLoad(ctx) {
    const snap = ctx.snapshot;
    if (!snap) return;
    const sel = selected(ctx);
    const d = ctx.data('evidence');
    if (ctx.fresh(d) && (d.resultId || null) === sel) return;
    const key = `${ctx.version()}|${sel || ''}`;
    if (requested[key]) return;
    requested[key] = true;
    // WP-A5: the plain read may already be asked by another tab (the Overview's next move).
    if (!sel && ctx.wanted && ctx.wanted('evidence')) return;
    ctx.load('evidence', sel ? { resultId: sel } : undefined);
  }

  function choose(ctx, id) {
    // A choice after a load error asks again (the earlier answer for it may have failed).
    if (ctx.error('evidence') && ctx.snapshot) delete requested[`${ctx.version()}|${id || ''}`];
    ctx.ui.set('selectedResult', id || undefined);
    ctx.rerender();
  }

  function fitLabel(task, fit) {
    const c = C();
    if (fit === 'fit.baseline') return c.reference[task === 'regression' ? 'regression' : 'binary'];
    return c.fits[fit] || fit;
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
        f === 'stale' ? HT.terms.mark(c.filters[f], 'stale_result') : c.filters[f],
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
    // WP-B5: the results measured on the final test are listed apart, under their label.
    const final = shown.filter(r => r.partition === 'final_test');
    const development = shown.filter(r => r.partition !== 'final_test');
    const list = (rows, part) => ctx.el('ul', { className: 'ht-ev-list', 'data-results': filter, 'data-results-partition': part },
      rows.map(r => resultRow(ctx, r, sel)));
    return ctx.el('section', { className: 'card ht-ev-registry', 'aria-labelledby': 'ht-ev-results' }, [
      ctx.el('h3', { id: 'ht-ev-results', text: c.resultsTitle }),
      filterGroup(ctx, filter),
      shown.length && final.length ? ctx.el('div', {}, [
        ctx.el('h4', { className: 'ht-ev-list-head', text: c.developmentTitle }), development.length ? list(development, 'development') : null,
        ctx.el('h4', { className: 'ht-ev-list-head', 'data-final-results': true, text: c.finalEvidenceTitle }), list(final, 'final_test'),
      ]) : shown.length ? list(shown, 'development')
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
    return ctx.el('p', { 'data-delta-sentence': delta.side }, [HT.terms.mark(text, 'paired_difference')]);
  }

  function intervalText(fmt, low, high) {
    return low === null || high === null ? '' : `[${fmt(low)}, ${fmt(high)}]`;
  }

  function metricBlock(ctx, u, task, metric, fmt, deltaFmt, label, unit) {
    const c = C();
    const level = u.bootstrap.level !== null ? pct(ctx, u.bootstrap.level).replace('.0%', '%') : '';
    const box = ctx.el('div', { className: 'ht-ev-metric', 'data-metric': metric.metric });
    // A regression metric is named by its glossary term (MAE, RMSE) for the hovers (§6.7).
    if (task === 'regression') box.appendChild(ctx.el('h4', {}, [HT.terms.mark(label, metric.metric)]));
    const notDefined = task === 'binary' ? c.binary.notDefined : '';
    intervals(ctx, box, {
      title: c.intervalTitle(label, level),
      zero: false,
      rows: metric.models.map(m => ({ label: fitLabel(task, m.fit), point: m.point, low: m.low, high: m.high,
        tone: m.fit === u.reference || m.fit === 'fit.baseline' ? 'baseline' : null,
        pointText: m.point === null ? notDefined : `${fmt(m.point)}${unit}`, intervalText: intervalText(fmt, m.low, m.high) })),
    });
    if (metric.delta) {
      const d = metric.delta;
      const cand = fitLabel(task, d.fit);
      const ref = fitLabel(task, u.reference);
      intervals(ctx, box, {
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
      ctx.el('h3', { id: 'ht-ev-unc' }, [HT.terms.mark(c.uncertaintyTitle, 'confidence_interval')]),
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

  // "Select the id": opens the full id and selects it, for the junior to copy with the
  // keyboard. The panel writes the clipboard only through the agent bridge (§12, decision
  // CI.5), so this button never calls the clipboard API.
  function selectId(ctx, detail, code) {
    const details = code.closest('details');
    if (details) details.open = true;
    const range = document.createRange();
    range.selectNodeContents(code);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
    copyNote = { id: detail.resultId, text: C().copyFallback };
    const note = document.querySelector('[data-select-note]');
    if (note) note.textContent = copyNote.text;
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
        ctx.el('button', { type: 'button', className: 'ht-link', 'data-select-id': true, text: c.copyId, onclick: () => selectId(ctx, detail, code) }),
      ]),
      ctx.el('details', { className: 'ht-ev-fullid' }, [ctx.el('summary', { text: c.fullId }), code]),
      ctx.el('p', { className: 'muted', role: 'status', 'data-select-note': true, text: note || '' }),
      staleBox(ctx, detail),
      facts(ctx, detail, task),
      ...smallData(ctx, detail),
      ctx.el('div', { className: 'ht-ev-actions' }, [
        report,
        ctx.el('button', { type: 'button', className: 'secondary', 'data-show-in-notebook': detail.resultId, disabled: !detail.notebookHint,
          'aria-describedby': detail.notebookHint ? 'ht-ev-notebook-hint' : null, text: c.showInNotebook,
          onclick: () => ctx.send({ type: 'open_artifact', artifact: 'notebook', resultId: detail.resultId }) }),
        // The shared agent-bridge helper of media/terms.js (§6.8; WP-I).
        HT.askButton(ctx, { kind: 'result', id: detail.resultId }, detail.slot || detail.activity,
          { label: c.askAgent, attrs: { 'data-ask-agent': 'result' } }),
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
    // WP-B5: each purpose in words (what was done with the rows), and the partitions named
    // for the junior (development rows, final test); the final-test rows stand out.
    const partitionWords = part => c.partitions[part] || part;
    const rows = model.ledger.map(row => ctx.el('tr', { 'data-ledger-row': `${row.purpose}:${row.partition}`,
      className: row.selection ? 'ht-ledger-selection' : row.partition === 'final_test' ? 'ht-ledger-final' : null,
      'data-ledger-final': row.partition === 'final_test' ? 'true' : null }, [
      ctx.el('td', {}, [row.selection ? HT.terms.mark(c.purposes[row.purpose] || row.purpose, 'selection_on_validation')
        : c.purposes[row.purpose] || row.purpose,
        row.selection ? ctx.el('span', { className: 'sr-only', text: ` (${c.usedToChoose})` }) : null,
        c.purposeWords[row.purpose] ? ctx.el('div', { className: 'muted ht-ledger-words', text: c.purposeWords[row.purpose] }) : null]),
      ctx.el('td', { 'data-partition': row.partition }, [row.partition === 'validation'
        ? HT.terms.mark(partitionWords(row.partition), 'validation_partition') : partitionWords(row.partition)]),
      ctx.el('td', { 'data-rows': row.rows === null ? '' : String(row.rows), text: int(ctx, row.rows) }),
      ctx.el('td', { text: row.activities.join(', ') }),
    ]));
    return ctx.el('section', { className: 'card ht-ev-ledger', 'aria-labelledby': 'ht-ev-ledger-h', 'data-ledger': true }, [
      ctx.el('h3', { id: 'ht-ev-ledger-h' }, [HT.terms.mark(c.ledgerTitle, 'exposure')]),
      rows.length ? ctx.el('table', { className: 'ht-values ht-ledger' }, [ctx.el('caption', { className: 'sr-only', text: c.ledgerTitle }), head,
        ctx.el('tbody', {}, rows)]) : ctx.el('p', { className: 'muted', text: c.ledgerEmpty }),
      ...limits.map(i => ctx.el('p', { className: 'hold', 'data-limit': i.id, text: i.text })),
      model.splitOverlap ? ctx.el('p', { className: 'hold', 'data-split-unseen': true, text: c.splitUnseen }) : null,
    ]);
  }

  // --- WP-B5: the final test first, then the ledger, development and final evidence apart ---

  const J = () => HT.copy.junior;
  const pts = (ctx, x) => `${x > 0 ? '+' : ''}${ctx.format.number(100 * x, 'f1')}`;
  const pct0 = (ctx, x) => ctx.format.number(x, 'pct0');

  /** The configuration of an opening or an evaluation in words (the model, the rule). */
  function configWords(model, rule, task) {
    const r = rule ? J().value('policy', rule, task) : null;
    const name = J().modelName(model, task);
    return r ? `${name}, ${r.charAt(0).toLowerCase()}${r.slice(1)}` : name;
  }

  /**
   * The final test (ADR 0006, WP-B1 amendment), at the top of the tab: sealed (its rows,
   * nobody has read them, what must be confirmed before it opens, and that the opening is a
   * chat act), opened (when, in the junior's words, what was measured), changed after the
   * opening (what), or absent (a study created before the seal). Then the trial count and
   * why it matters. No control: the opening is never offered here.
   */
  function finalTestCard(summary, model, ctx) {
    const c = C();
    const F = J().finalTest;
    const ft = summary && summary.finalTest;
    const state = J().finalTestState(ft);
    if (!state) return null;
    const task = (summary && summary.task) || model.task || 'binary';
    const kids = [
      ctx.el('div', { className: 'ht-ev-final-head' }, [
        ctx.el('span', { className: `ht-status ${state === 'sealed' ? 'ht-st-sealed' : state === 'opened' ? 'ht-st-ok'
          : state === 'absent' ? 'ht-st-neutral' : 'ht-st-stale'}`, 'data-final-state': state, text: F.titles[state] }),
        state === 'sealed' && ft.rows !== null ? ctx.el('strong', { className: 'ht-ev-final-count', text: c.sealedRows(int(ctx, ft.rows)) }) : null,
      ]),
    ];
    if (state === 'sealed') {
      kids.push(ctx.el('p', { className: 'muted', text: F.sealed(int(ctx, ft.rows), ft.method) }));
      kids.push(ctx.el('ul', { className: 'ht-ev-partitions' }, [
        ft.developmentRows !== null ? ctx.el('li', { 'data-partition-line': 'development', text: c.developmentRows(int(ctx, ft.developmentRows)) }) : null,
        ft.rows !== null ? ctx.el('li', { 'data-partition-line': 'final_test', text: c.finalRows(int(ctx, ft.rows)) }) : null,
      ]));
    }
    kids.push(ctx.el('p', { 'data-final-lead': state, text: c.finalLead[state] }));
    if (state === 'sealed') {
      const decisions = (summary && summary.decisions) || {};
      const choice = task === 'regression' ? 'model_choice' : 'policy';
      const items = [['choice', choice], ['model_variant', 'model_variant'], ['success_criterion', 'success_criterion']]
        .filter(([, id]) => decisions[id]).map(([key, id]) => {
          const done = decisions[id].status === 'confirmed';
          const label = typeof c.beforeItem[key] === 'function' ? c.beforeItem[key](task) : c.beforeItem[key];
          return ctx.el('li', { 'data-before': id, 'data-done': done ? 'true' : 'false' }, [
            ctx.el('span', { 'aria-hidden': 'true', text: done ? '✓ ' : '✗ ' }), label,
            ctx.el('span', { className: 'sr-only', text: ` (${done ? c.done : c.notYet})` })]);
        });
      if (items.length) kids.push(ctx.el('div', { className: 'ht-ev-before' }, [ctx.el('p', { text: c.before }), ctx.el('ul', {}, items)]));
      kids.push(ctx.el('p', { className: 'ht-ev-chat', 'data-open-in-chat': true, text: c.openInChat }));
    }
    if ((state === 'opened' || state === 'changed') && ft.opening) {
      const fe = model.finalEvaluation && model.finalEvaluation.current ? model.finalEvaluation : null;
      const time = fe && fe.created ? ctx.format.localTime(fe.created) : null;
      kids.push(ctx.el('p', { 'data-opened-at': String(ft.opening.revision) }, [c.openedAt(ft.opening.revision, time)]));
      kids.push(ctx.el('blockquote', { 'data-opening-words': true, text: ft.opening.userWords || '' }));
      if (fe) {
        kids.push(ctx.el('p', { 'data-opening-measured': true,
          text: c.evaluated(configWords(fe.model, fe.ruleFinal || fe.rule, task), int(ctx, fe.n), int(ctx, fe.refitRows)) }));
      }
    }
    if (state === 'changed') {
      kids.push(ctx.el('div', { className: 'hold', role: 'note', 'data-changed-after': true }, [
        ctx.el('p', { className: 'title', text: c.changedAfter }),
        ctx.el('ul', {}, (ft.changedAfter || []).map(x => ctx.el('li', { 'data-changed': x, title: x, text: J().changedName(x, task) }))),
      ]));
    }
    const trials = summary && summary.trials;
    if (trials && trials.count !== null) {
      kids.push(ctx.el('div', { className: 'ht-ev-trials', 'data-trials': String(trials.count) }, [
        ctx.el('p', { className: 'title', text: c.trials(int(ctx, trials.count)) }),
        ctx.el('p', { className: 'muted', text: c.trialsWhy }),
      ]));
    }
    return ctx.el('section', { className: `card ht-ev-final ht-ev-final-${state}`, 'aria-labelledby': 'ht-ev-final-h',
      'data-ev': 'final-test', 'data-final-test-card': state }, [
      ctx.el('h3', { id: 'ht-ev-final-h', text: c.finalTitle }),
      ...kids,
    ]);
  }

  /** The cross-validation scheme in words, the spread across folds, the variant (development). */
  function developmentSection(ctx, model, task) {
    const c = C();
    const kids = [];
    const cv = model.crossValidation;
    if (cv) {
      const scheme = c.scheme[cv.method];
      kids.push(ctx.el('p', { 'data-cv-scheme': cv.method, text: scheme ? scheme(int(ctx, cv.folds)) : cv.method }));
      kids.push(ctx.el('p', { className: 'muted', text: c.schemeWhy }));
      if (cv.duplicates && cv.duplicates.nGroups !== null) {
        kids.push(ctx.el('p', { 'data-cv-duplicates': true, text: c.grouped(int(ctx, cv.duplicates.nGroups), int(ctx, cv.duplicates.dividedGroups || 0)) }));
      }
      if (cv.sharedGroups && cv.sharedGroups.inSeveralFolds) {
        kids.push(ctx.el('p', { className: 'hold', text: c.sharedGroups(int(ctx, cv.sharedGroups.inSeveralFolds), cv.sharedGroups.column || '') }));
      }
      const rows = [];
      for (const f of cv.fits) {
        for (const m of f.metrics) {
          const fmt = x => ctx.format.number(x, m.metric === 'mae' || m.metric === 'rmse' ? 'f2' : 'f3');
          rows.push({ model: fitLabel(task, f.fit), metric: c.measures[m.metric] || m.metric,
            mean: m.mean === null ? '' : { text: `${fmt(m.mean)} ± ${fmt(m.sd)}`, cited: { resultId: f.resultId, path: m.paths.mean, value: m.mean } },
            range: m.min === null ? '' : { text: `${fmt(m.min)} – ${fmt(m.max)}`, cited: { resultId: f.resultId, path: m.paths.min, value: m.min } } });
        }
      }
      if (rows.length) {
        const cols = c.spreadColumns;
        const table = ctx.components.valuesTable(null, { caption: c.spreadTitle,
          columns: [{ key: 'model', label: cols.model }, { key: 'metric', label: cols.metric }, { key: 'mean', label: cols.mean },
            { key: 'range', label: cols.range }], rows });
        table.setAttribute('data-cv-spread', String(rows.length));
        kids.push(ctx.el('h4', { text: c.spreadTitle }), table, ctx.el('p', { className: 'muted', text: c.spreadWhy }));
      }
    } else if (model.results.some(r => r.slot === 'split' && r.current)) {
      kids.push(ctx.el('p', { 'data-cv-scheme': 'split', text: c.schemeSplit }));
    }
    const v = model.variant;
    if (v) {
      const box = ctx.el('div', { className: 'ht-ev-variant', 'data-variant': v.kind || 'variant' }, [
        ctx.el('h4', { text: c.variantTitle }),
        ctx.el('p', { text: c.variantKind(v.kind, v.strength, v.group) }),
      ]);
      const binaryFmt = x => `${pts(ctx, x)}${c.points}`;
      // One rule (binary): the adopted one, else the proposed one, else the first evaluated.
      const policy = ctx.snapshot && ctx.snapshot.decisions && ctx.snapshot.decisions.policy;
      const open = ((ctx.snapshot && ctx.snapshot.proposals) || []).find(p => p.decisionId === 'policy');
      const wanted = [policy && policy.value, open && open.value].map(x => String(x || '').split('@')[0]).filter(Boolean);
      const chosen = v.comparisons.find(x => wanted.includes(x.rule)) || v.comparisons[0];
      for (const comp of chosen ? [chosen] : []) {
        for (const m of comp.metrics) {
          if (m.point === null) continue;
          const label = task === 'regression' ? c.metrics[m.metric] || m.metric : c.binary.metrics[m.metric] || m.metric;
          const fmt = task === 'regression' ? x => `${x > 0 ? '+' : ''}${ctx.format.number(x, 'f2')}` : binaryFmt;
          const ruleWords = comp.rule ? J().value('policy', comp.rule, task) || comp.rule : null;
          // Each model on the same rows first (the baseline in grey), then the paired difference.
          const vfmt = task === 'regression' ? x => ctx.format.number(x, 'f2') : x => pct(ctx, x);
          if ((m.models || []).length) {
            intervals(ctx, box, { title: c.variantModels(label, ruleWords), zero: false,
              rows: m.models.map(x => ({ label: fitLabel(task, x.fit), point: x.point, low: x.low, high: x.high,
                tone: x.fit === 'fit.baseline' ? 'baseline' : null, pointText: x.point === null ? '' : vfmt(x.point),
                intervalText: x.low === null || x.high === null ? '' : `[${vfmt(x.low)}, ${vfmt(x.high)}]` })) });
          }
          intervals(ctx, box, { title: c.variantDifference(label, ruleWords), zero: true,
            rows: [{ label: label, point: m.point, low: m.low, high: m.high, pointText: fmt(m.point),
              intervalText: m.low === null || m.high === null ? '' : `[${fmt(m.low)}, ${fmt(m.high)}]` }] });
          box.appendChild(ctx.el('p', { 'data-variant-sentence': m.side }, [
            ctx.components.cited(`${label} ${fmt(m.point)}`, { resultId: v.evaluationId, path: m.path, value: m.point }), ' · ',
            c.variantSentence[m.side] || c.variantSentence.undefined]));
        }
      }
      if (v.ranking.length) {
        const table = ctx.components.valuesTable(null, { caption: c.rankingTitle,
          columns: [{ key: 'model', label: c.spreadColumns.model }, { key: 'auc', label: c.measures.roc_auc }],
          rows: v.ranking.map(r => ({ model: fitLabel(task, r.fit),
            auc: r.rocAuc === null ? '' : { text: ctx.format.number(r.rocAuc, 'f3'), cited: { resultId: v.evaluationId, path: r.path, value: r.rocAuc } } })) });
        box.appendChild(table);
      }
      if (v.bootstrap && v.bootstrap.replicates !== null) {
        box.appendChild(ctx.el('p', { className: 'muted', text: c.bootstrap(int(ctx, v.bootstrap.replicates), pct0(ctx, v.bootstrap.level)) }));
      }
      kids.push(box);
    }
    if (!kids.length) return null;
    return ctx.el('section', { className: 'card ht-ev-development', 'aria-labelledby': 'ht-ev-dev-h', 'data-ev': 'development' }, [
      ctx.el('h3', { id: 'ht-ev-dev-h', text: c.developmentTitle }), ...kids]);
  }

  /** The final evaluation (measured once): the chosen model against the baseline, the criterion. */
  function finalEvidenceSection(ctx, model, summary, task) {
    const c = C();
    const state = J().finalTestState(summary && summary.finalTest);
    const fe = model.finalEvaluation;
    const kids = [];
    if (!fe) {
      if (!state) return null;
      kids.push(ctx.el('p', { className: 'muted', 'data-final-evidence': state === 'absent' ? 'absent' : 'none',
        text: state === 'absent' ? c.finalAbsent : c.finalNotYet }));
    } else if (!fe.current) {
      kids.push(ctx.el('p', { className: 'muted', 'data-final-evidence': 'stale', text: c.finalStale }));
    } else {
      const level = fe.bootstrap.level !== null ? pct0(ctx, fe.bootstrap.level) : '';
      for (const m of fe.metrics) {
        const isRate = task !== 'regression';
        const fmt = isRate ? x => pct(ctx, x) : x => ctx.format.number(x, 'f2');
        const unit = !isRate && fe.unit ? ` ${fe.unit}` : '';
        const label = isRate ? c.binary.metrics[m.metric] : c.metrics[m.metric];
        const box = ctx.el('div', { className: 'ht-ev-metric', 'data-final-metric': m.metric });
        intervals(ctx, box, { title: c.finalModels(label, int(ctx, fe.n)) + (level ? ` (${level})` : ''), zero: false,
          rows: m.models.map(x => ({ label: fitLabel(task, x.fit), point: x.point, low: x.low, high: x.high,
            tone: x.fit === 'fit.baseline' ? 'baseline' : null, pointText: x.point === null ? '' : `${fmt(x.point)}${unit}`,
            intervalText: x.low === null || x.high === null ? '' : `[${fmt(x.low)}, ${fmt(x.high)}]` })) });
        if (m.delta) {
          const d = m.delta;
          const dfmt = isRate ? x => `${pts(ctx, x)}${c.points}` : x => `${x > 0 ? '+' : ''}${ctx.format.number(x, 'f2')}${unit}`;
          intervals(ctx, box, { title: c.differenceTitle(label, fitLabel(task, d.fit), fitLabel(task, 'fit.baseline')), zero: true,
            rows: [{ label: c.difference(fitLabel(task, d.fit), fitLabel(task, 'fit.baseline')), point: d.point, low: d.low, high: d.high,
              pointText: d.point === null ? '' : dfmt(d.point), intervalText: d.low === null ? '' : `[${dfmt(d.low)}, ${dfmt(d.high)}]` }] });
          box.appendChild(deltaSentence(ctx, d));
        }
        kids.push(box);
      }
      const k = fe.criterion;
      if (k && k.gain !== null) {
        const share = k.unit === 'share';
        const f = x => (share ? pct(ctx, x) : `${x > 0 ? '+' : ''}${ctx.format.number(x, 'f1')}`);
        const cite = (x, p) => ctx.components.cited(f(x), { resultId: fe.resultId, path: p, value: x });
        kids.push(ctx.el('p', { 'data-final-criterion': k.status || '' }, [c.finalCriterion,
          ctx.el('span', { className: `ht-status ht-st-${k.status === 'met' ? 'ok' : k.status === 'not_met' ? 'error' : 'stale'}`,
            text: c.criterionStatus[k.status] || k.status || '' }), ' · ',
          cite(k.gain, k.paths.gain), share ? '' : c.points,
          k.low !== null && k.high !== null ? [c.interval, cite(k.low, k.paths.low), c.to, cite(k.high, k.paths.high), c.close] : null, '.']));
      }
      if (fe.bootstrap.replicates !== null) {
        kids.push(ctx.el('p', { className: 'muted', 'data-bootstrap': true, text: c.bootstrap(int(ctx, fe.bootstrap.replicates), level) }));
      }
    }
    return ctx.el('section', { className: 'card ht-ev-final-evidence', 'aria-labelledby': 'ht-ev-fe-h', 'data-ev': 'final' }, [
      ctx.el('h3', { id: 'ht-ev-fe-h', text: c.finalEvidenceTitle }), ...kids]);
  }

  // --- diagnostics (WP-B4's results, in the shape of its plan; see lib/models/evidence.js) ---

  function diagConfusion(ctx, d) {
    const t = C().diag.confusion;
    const cell = (k, label) => {
      const x = d.cells[k];
      return ctx.el('td', { 'data-cell': k }, [
        x.value === null ? '' : ctx.components.cited(ctx.format.number(x.value, Number.isInteger(x.value) ? 'int' : 'f1'),
          { resultId: d.resultId, path: x.path, value: x.value }),
        ctx.el('div', { className: 'muted', text: label })]);
    };
    return ctx.el('table', { className: 'ht-values ht-confusion', 'data-confusion': d.evaluation }, [
      ctx.el('caption', { text: t.question }),
      ctx.el('thead', {}, [ctx.el('tr', {}, [ctx.el('td', {}), ctx.el('th', { scope: 'col', text: t.actedOn }),
        ctx.el('th', { scope: 'col', text: t.notActedOn })])]),
      ctx.el('tbody', {}, [
        ctx.el('tr', {}, [ctx.el('th', { scope: 'row', text: t.positive }), cell('tp', t.tp), cell('fn', t.fn)]),
        ctx.el('tr', {}, [ctx.el('th', { scope: 'row', text: t.negative }), cell('fp', t.fp), cell('tn', t.tn)]),
      ]),
    ]);
  }

  const TICKS = [0, 0.5, 1].map(v => ({ value: v, text: `${v * 100}%` }));

  function diagCurve(ctx, d, kind) {
    const c = C().diag[kind];
    const box = ctx.el('div', { 'data-diag-chart': kind });
    if (kind === 'gain') {
      ctx.components.curve(box, { title: c.question, xDomain: [0, 1], yDomain: [0, 1], xTicks: TICKS, yTicks: TICKS,
        xLabel: HT.copy.whatif.binary.gain.x, yLabel: HT.copy.whatif.binary.gain.y, diagonal: { label: HT.copy.whatif.binary.gain.random },
        points: d.points.map(p => ({ x: p.share, y: p.recall, label: `${pct0(ctx, p.share)}: ${pct0(ctx, p.recall)}` })),
        columns: [{ key: 'share', label: HT.copy.whatif.binary.gain.x }, { key: 'recall', label: HT.copy.whatif.binary.gain.y }],
        rows: d.points.map(p => ({ share: { text: pct(ctx, p.share), cited: { resultId: d.resultId, path: p.paths.share, value: p.share } },
          recall: { text: pct(ctx, p.recall), cited: { resultId: d.resultId, path: p.paths.recall, value: p.recall } } })) });
    } else {
      ctx.components.curve(box, { title: c.question, xDomain: [0, 1], yDomain: [0, 1], xTicks: TICKS, yTicks: TICKS,
        xLabel: c.x, yLabel: c.y, diagonal: { label: c.diagonal },
        points: d.bins.map(b => ({ x: b.meanPred, y: b.observed, low: b.low, high: b.high, label: '' })),
        columns: [{ key: 'pred', label: c.x }, { key: 'obs', label: c.y }, { key: 'n', label: C().diag.segments.columns.interval }],
        rows: d.bins.map(b => ({ pred: { text: pct(ctx, b.meanPred), cited: { resultId: d.resultId, path: b.paths.meanPred, value: b.meanPred } },
          obs: { text: pct(ctx, b.observed), cited: { resultId: d.resultId, path: b.paths.observed, value: b.observed } },
          n: b.low === null ? '' : `[${pct(ctx, b.low)}, ${pct(ctx, b.high)}]` })) });
    }
    return box;
  }

  function diagSegments(ctx, d, task) {
    const t = C().diag.segments;
    const table = ctx.components.valuesTable(null, { caption: t.question,
      columns: [{ key: 'group', label: t.columns.group }, { key: 'n', label: t.columns.n }, { key: 'precision', label: t.columns.precision },
        { key: 'interval', label: t.columns.interval }, { key: 'recall', label: t.columns.recall }],
      rows: d.segments.map(g => ({ group: `${g.variable} = ${g.group}`,
        n: g.n === null ? '' : { text: int(ctx, g.n), cited: { resultId: d.resultId, path: g.paths.n, value: g.n } },
        precision: g.precision === null ? '' : { text: pct(ctx, g.precision), cited: { resultId: d.resultId, path: g.paths.precision, value: g.precision } },
        interval: g.low === null || g.high === null ? '' : `[${pct(ctx, g.low)}, ${pct(ctx, g.high)}]`,
        recall: g.recall === null ? '' : { text: pct(ctx, g.recall), cited: { resultId: d.resultId, path: g.paths.recall, value: g.recall } } })) });
    table.setAttribute('data-segments', String(d.segments.length));
    return table;
  }

  function diagResiduals(ctx, d, task) {
    const t = C().diag.residuals;
    const box = ctx.el('div', { 'data-diag-chart': 'residuals' });
    const f2 = x => ctx.format.number(x, 'f2');
    intervals(ctx, box, { title: t.question, zero: true,
      rows: d.bins.map(b => ({ label: t.row(b.meanPred === null ? '' : f2(b.meanPred)), point: b.meanResidual, low: b.low, high: b.high,
        pointText: `${b.meanResidual > 0 ? '+' : ''}${f2(b.meanResidual)}`, intervalText: b.low === null ? '' : `[${f2(b.low)}, ${f2(b.high)}]` })) });
    return box;
  }

  function diagnosticsSection(ctx, model, task) {
    const c = C();
    const items = model.diagnostics || [];
    if (!items.length) return null;
    const where = ev => c.diagnosticsWhere[ev] || ev;
    const groups = ['out_of_fold', 'final_test'].map(ev => [ev, items.filter(d => (d.evaluation === 'final_test' ? 'final_test' : 'out_of_fold') === ev)])
      .filter(([, list]) => list.length);
    const kids = [ctx.el('p', { className: 'muted', text: c.diagnosticsLead })];
    for (const [ev, list] of groups) {
      const block = ctx.el('div', { className: 'ht-ev-diag-group', 'data-diag-evaluation': ev }, [
        ctx.el('h4', { text: where(ev) })]);
      for (const d of list) {
        // Binary diagnostics use the vocabulary of a decision rule; a regression study shows
        // residuals only (INV-12).
        if (task === 'regression' && d.kind !== 'residuals' && d.kind !== 'other') continue;
        const card = ctx.el('div', { className: 'ht-ev-diag', 'data-diag': d.kind, 'data-result-ref': d.resultId });
        if (d.kind === 'confusion') card.appendChild(diagConfusion(ctx, d));
        else if (d.kind === 'gain' && d.points.length) card.appendChild(diagCurve(ctx, d, 'gain'));
        else if (d.kind === 'calibration' && d.bins.length) card.appendChild(diagCurve(ctx, d, 'calibration'));
        else if (d.kind === 'segments') card.appendChild(diagSegments(ctx, d, task));
        else if (d.kind === 'residuals' && d.bins.length) card.appendChild(diagResiduals(ctx, d, task));
        else card.appendChild(ctx.el('p', { className: 'muted', text: `${d.activity} · ${c.reconcile}` }));
        block.appendChild(card);
      }
      kids.push(block);
    }
    return ctx.el('section', { className: 'card ht-ev-diagnostics', 'aria-labelledby': 'ht-ev-diag-h', 'data-ev': 'diagnostics' }, [
      ctx.el('h3', { id: 'ht-ev-diag-h', text: c.diagnosticsTitle }), ...kids]);
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
    const stale = summary && !ctx.fresh(d);
    if (stale) root.appendChild(ctx.el('p', { className: 'muted', role: 'status', 'data-updating': true, text: c.updating }));
    // WP-B5: the final test and the ledger first, development and final evidence apart.
    const first = [finalTestCard(summary, model, ctx), ledger(ctx, model), developmentSection(ctx, model, task),
      finalEvidenceSection(ctx, model, summary, task), diagnosticsSection(ctx, model, task)].filter(Boolean);
    for (const node of first) root.appendChild(node);
    root.appendChild(ctx.el('div', { className: `ht-ev-grid${stale ? ' ht-pending' : ''}` }, [
      registry(ctx, model, sel),
      detailSection(ctx, model, sel, task),
    ]));
    root.appendChild(lineage(ctx, model, sel));
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
