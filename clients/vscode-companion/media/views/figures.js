// The figures behind each step, the method diagrams, the end's development-vs-final table and
// "And after", and the What if? editor tab (lot P: owner remarks R38 to R53 of 2026-10-28;
// ADR 0004 decision 14). A parts provider (HT.parts.figures) that page.js calls:
//
//   nowFigures(ctx, now)        "To answer, look at": every registered result the step rests
//                               on, drawn inline with its frame and "What we conclude" (R39-R45),
//                               the trial budget as a bar at the variants (R44), and the step's
//                               method diagrams (R53). The quality check is a per-column view
//                               with each column's verdict and bound when the engine sends one (R41).
//   stepFigures(ctx, line)      the same figures, inline, in an opened step of the path (R50).
//   diagram(ctx, id)            partition, folds, pipeline, one_se, ledger (R53), from registered values.
//   devFinal(ctx)               the end's one table (R52): rows = configurations, the difference
//                               with the reference, the criterion; columns development / final;
//                               then the same as dots with intervals on one scale (R48).
//   after(ctx, now)             "And after" (R49): the handoff export (W7) and the Azure ML plan
//                               (a read) with its export (W8), from v3.
//   whatifTab(ctx)              the What if? editor tab (R51): the residual explorer
//                               (regression) or the policy sandbox (binary), read only.
//
// Every number is an engine value of a registered result (OP-2, HON-1); every word is the
// panel's copy (media/copy*/figures.js) or an engine text. Nothing here writes, except the
// two buttons of "And after" (W7, W8), which send their message to the extension.
(function (HT) {
  'use strict';
  const el = (...a) => HT.el(...a);
  const F = () => HT.copy.figures;
  const J = () => HT.copy.junior;
  const L = () => HT.copy.lesson;
  const PARTS = name => (HT.parts && HT.parts[name]) || {};
  const arr = x => (Array.isArray(x) ? x : []);
  const ok = v => typeof v === 'number' && Number.isFinite(v);
  const cap = s => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);
  const VARIANTS = ['fit.variant', 'fit.variant:2', 'fit.variant:3'];

  /** Lot P (R45): the variants the study compares, for their names (ridge, EBM). */
  function setStudyVariants(snap) {
    const parse = raw => {
      if (raw && typeof raw === 'object') return raw;
      try { return JSON.parse(String(raw || '')); } catch (_) { return null; }
    };
    const d = snap && snap.decisions && snap.decisions.model_variant;
    const open = snap ? arr(snap.proposals).find(p => p.decisionId === 'model_variant') : null;
    const v = parse(d && d.value) || parse(open && open.value);
    HT.studyVariants = v && Array.isArray(v.variants) ? v.variants : v && v.kind ? [v] : [];
  }

  const evidenceOf = ctx => {
    ctx.want('evidence');
    const d = ctx.data('evidence');
    return d && d.model ? d.model : null;
  };
  const edaOf = ctx => {
    ctx.want('eda');
    const d = ctx.data('eda');
    return d && d.model ? d.model : null;
  };
  const task = ctx => (ctx.snapshot && ctx.snapshot.task) || 'binary';
  const label = (ctx, fit) => {
    if (fit === 'fit.baseline') return HT.copy.evidence.reference[task(ctx) === 'regression' ? 'regression' : 'binary'];
    return (J().variantLabel && J().variantLabel(fit)) || HT.copy.evidence.fits[fit] || fit;
  };
  const f2 = (ctx, x) => ctx.format.number(x, 'f2');
  const signed = (ctx, x) => `${x > 0 ? '+' : ''}${f2(ctx, x)}`;

  // --- frames and blocks ---------------------------------------------------------------------

  /** The frame of a result's figure (which rows, used to choose or final). */
  function frameOf(slot) {
    const a = String(slot).split(':')[0];
    if (['eda.quality', 'eda.distribution', 'eda.correlation', 'split'].includes(a)) return 'structural';
    if (a.startsWith('eda.')) return 'target';
    if (a === 'final_test.evaluation' || a === 'diag.final_test') return 'final';
    return 'development';
  }

  function block(ctx, frame, nodes, attrs = {}) {
    const list = arr(nodes).filter(Boolean);
    if (!list.length) return null;
    return el('div', { className: 'ht-figblock', 'data-figure-frame': frame, ...attrs }, [
      el('p', { className: 'ht-frame', 'data-frame': frame }, [el('strong', { text: F().frames[frame] || '' })]),
      ...list]);
  }

  // --- the quality check, one row per column (R41) ---------------------------------------------

  /** A strip of one column's range (min, low and high percentiles, median, max), on its own scale. */
  function strip(ctx, r) {
    const q = r.quantiles || {};
    const vals = [r.min ? r.min.value : null, q.q01, q.q50, q.q99, r.max ? r.max.value : null];
    const [mn, a, m, b, mx] = vals;
    if (!ok(mn) || !ok(mx)) return el('span', { className: 'muted', text: '—' });
    const span = mx - mn || 1;
    const x = v => (ok(v) ? (((v - mn) / span) * 100).toFixed(2) : null);
    const fmt = v => ctx.format.number(v, 'auto');
    return el('span', { className: 'ht-strip', 'data-strip': r.column }, [
      el('span', { className: 'ht-strip-trk', 'aria-hidden': 'true' }, [
        el('span', { className: 'ht-strip-line' }),
        ok(a) && ok(b) ? el('span', { className: 'ht-strip-box', css: { '--a': x(a), '--b': x(b) } }) : null,
        ok(m) ? el('span', { className: 'ht-strip-med', css: { '--x': x(m) } }) : null,
      ]),
      el('span', { className: 'ht-strip-txt' }, [ctx.components.cited(fmt(mn), { resultId: r.resultId, path: r.min.path, value: mn }),
        ' – ', ctx.components.cited(fmt(mx), { resultId: r.resultId, path: r.max.path, value: mx })]),
    ]);
  }

  /** The skewness as a dot on a small symmetric scale, the engine's bound as a line when it sends one. */
  function skewMark(ctx, r) {
    const s = r.skewness;
    if (!s || !ok(s.value)) return el('span', { className: 'muted', text: '—' });
    const bound = r.verdict && r.verdict.threshold !== null ? Number(String(r.verdict.threshold).replace(',', '.')) : null;
    const lim = Math.max(3, Math.abs(s.value), ok(bound) ? Math.abs(bound) : 0);
    const x = v => (((v + lim) / (2 * lim)) * 100).toFixed(2);
    return el('span', { className: 'ht-skew', 'data-skew': String(s.value) }, [
      el('span', { className: 'ht-skew-trk', 'aria-hidden': 'true' }, [
        el('span', { className: 'ht-skew-zero', css: { '--x': x(0) } }),
        ok(bound) ? el('span', { className: 'ht-skew-bound', 'data-bound': String(bound), css: { '--x': x(bound) } }) : null,
        el('span', { className: 'ht-skew-dot', css: { '--x': x(s.value) } }),
      ]),
      ctx.components.cited(f2(ctx, s.value), { resultId: r.resultId, path: s.path, value: s.value }),
    ]);
  }

  function verdictCell(ctx, r, changed) {
    const c = F().quality;
    const v = r.verdict;
    const lang = ctx.language();
    // The digest's words are in the study language (`v.lang`); a range's verdict has both.
    const text = v && v.texts ? v.texts[lang] || v.texts.en : null;
    const textLang = v && v.lang ? v.lang : v && v.texts && v.texts[lang] ? lang : 'en';
    const isChanged = v && v.changed !== null ? v.changed : changed.includes(r.column);
    return el('span', { className: `ht-verdict${isChanged ? ' ht-verdict-changed' : ''}`, 'data-verdict': isChanged ? 'changed' : 'kept' }, [
      el('strong', { text: isChanged ? c.changed : c.kept }),
      text ? [' · ', HT.components.engineText(text, { lang: textLang })] : null,
      v && v.threshold ? el('span', { className: 'ht-faint', text: ` (${c.threshold(v.threshold)})` }) : null,
    ]);
  }

  function qualityColumns(ctx, slot, changed = [], indicator = false) {
    const c = F().quality;
    const model = edaOf(ctx);
    if (!model) return el('p', { className: 'muted', 'aria-busy': 'true', text: F().reading });
    const card = arr(model.cards).find(k => k.slot === slot && k.kind === 'quality' && k.data);
    if (!card) return el('p', { className: 'muted', text: F().noChart });
    const d = card.data;
    const missing = Object.fromEntries(arr(d.missing).map(m => [m.column, m.nMissing]));
    // The engine's verdicts (digest `quality_verdicts`, R41) when they are of this check;
    // else the verdict a range carries; else none, and the figures stand alone.
    const qv = ctx.snapshot && ctx.snapshot.qualityVerdicts;
    const digestOf = col => (qv && (!qv.resultId || qv.resultId === card.resultId) ? arr(qv.columns).find(v => v.column === col) : null);
    const asVerdict = v => {
      const skew = arr(v.checks).find(k => /\.skewness$/.test(k.path || '') || /skew/.test(k.rule));
      const words = arr(v.checks).map(k => k.words).filter(Boolean).join(' · ') || v.text;
      return { changed: v.changed, parameter: v.parameters.join(', ') || null, threshold: skew && skew.threshold !== null ? String(skew.threshold) : null,
        texts: { en: words, fr: words }, lang: ctx.snapshot.language || 'en' };
    };
    const ranges = arr(d.ranges).map(r => {
      const v = digestOf(r.column);
      return { ...r, resultId: card.resultId, verdict: v ? asVerdict(v) : r.verdict };
    });
    const known = new Set(ranges.map(r => r.column));
    const categories = [...arr(d.verdicts), ...(qv ? arr(qv.columns).map(v => ({ column: v.column, ...asVerdict(v) })) : [])]
      .filter((v, i, a) => !known.has(v.column) && a.findIndex(x => x.column === v.column) === i);
    const isChanged = r => (r.verdict && r.verdict.changed !== null ? r.verdict.changed : changed.includes(r.column));
    ranges.sort((a, b) => Number(isChanged(b)) - Number(isChanged(a)));
    const head = el('div', { className: 'ht-qrow ht-qhead', 'aria-hidden': 'true' },
      ['column', 'range', 'skew', 'missing', 'verdict'].map(k => el('span', { text: c.columns[k] })));
    const rows = ranges.map(r => el('div', { className: `ht-qrow${isChanged(r) ? ' ht-qrow-changed' : ''}`, 'data-quality-column': r.column,
      role: 'listitem' }, [
      el('span', { className: 'ht-qcol' }, [el('code', { text: r.column })]),
      strip(ctx, r),
      skewMark(ctx, r),
      el('span', { className: 'ht-qmiss', 'data-missing': missing[r.column] ? String(missing[r.column].value) : '0' }, [
        missing[r.column] ? ctx.components.cited(ctx.format.number(missing[r.column].value, 'int'),
          { resultId: card.resultId, path: missing[r.column].path, value: missing[r.column].value }) : ctx.format.number(0, 'int')]),
      verdictCell(ctx, r, changed),
    ]));
    for (const v of categories) {
      rows.push(el('div', { className: 'ht-qrow', 'data-quality-column': v.column, role: 'listitem' }, [
        el('span', { className: 'ht-qcol' }, [el('code', { text: v.column })]), el('span', { className: 'muted', text: c.category }),
        el('span'), el('span'), verdictCell(ctx, { column: v.column, verdict: v }, changed)]));
    }
    const names = ranges.filter(isChanged).map(r => r.column);
    const others = ranges.length + categories.length - names.length;
    const anyVerdict = ranges.some(r => r.verdict) || categories.length > 0;
    return el('div', { className: 'ht-quality-cols', 'data-quality-columns': String(ranges.length + categories.length) }, [
      el('p', { className: 'ht-figtitle', text: c.title }),
      el('div', { className: 'ht-qgrid', role: 'list', 'aria-label': c.title }, [head, ...rows]),
      d.nRows ? el('p', { className: 'ht-faint', text: c.rows(ctx.format.number(d.nRows.value, 'int')) }) : null,
      anyVerdict ? null : el('p', { className: 'ht-faint', 'data-no-verdict': true, text: c.noVerdict }),
      el('p', { className: 'ht-concl ht-paper', 'data-concl': true }, [el('span', { className: 'ht-pk', text: L().guide.concl }),
        c.concl(names.join(', '), ctx.format.number(others, 'int')), indicator ? ` ${c.indicator}` : '']),
    ]);
  }

  // --- the diagnostics behind the variants (R44) -------------------------------------------------

  function residualFigures(ctx, slot, { features = 2, model: wanted = null } = {}) {
    const ev = evidenceOf(ctx);
    if (!ev) return [el('p', { className: 'muted', 'aria-busy': 'true', text: F().reading })];
    const d = arr(ev.diagnostics).find(x => x.slot === slot);
    if (!d) return [el('p', { className: 'muted', text: F().noChart })];
    const c = F().residuals;
    const m = arr(d.models).find(x => x.fit === wanted) || arr(d.models).find(x => x.fit === 'fit.linear') || arr(d.models)[0];
    if (!m) return [el('p', { className: 'muted', text: F().noChart })];
    const name = label(ctx, m.fit);
    const unit = d.unit ? ` ${d.unit}` : '';
    const out = [];
    if (arr(m.scatter).length) {
      const box = el('div', { 'data-figure': 'observed-predicted', 'data-model': m.fit });
      const all = m.scatter.flatMap(p => [p.predicted, p.observed]);
      const lo = Math.floor(Math.min(...all));
      const hi = Math.ceil(Math.max(...all));
      const ticks = [lo, Math.round((lo + hi) / 2), hi].map(v => ({ value: v, text: ctx.format.number(v, 'int') }));
      ctx.components.curve(box, { title: c.scatterTitle(name), xDomain: [lo, hi], yDomain: [lo, hi], xTicks: ticks, yTicks: ticks,
        xLabel: c.x, yLabel: c.y, diagonal: { label: c.diagonal, at: 0.8 }, joined: false,
        points: m.scatter.map(p => ({ x: p.predicted, y: p.observed, label: '' })),
        columns: [{ key: 'x', label: c.x }, { key: 'y', label: c.y }],
        rows: m.scatter.map(p => ({ x: f2(ctx, p.predicted), y: f2(ctx, p.observed) })) });
      if (m.scatterShown !== null && m.scatterRows !== null) {
        box.appendChild(el('p', { className: 'ht-faint', text: c.sample(ctx.format.number(m.scatterShown, 'int'), ctx.format.number(m.scatterRows, 'int')) }));
      }
      out.push(box);
    }
    if (m.residuals && m.residuals.mean && ok(m.residuals.mean.value)) {
      out.push(el('p', { 'data-bias': m.fit }, [c.bias(name, `${signed(ctx, m.residuals.mean.value)}${unit}`)]));
    }
    // Residuals along the columns the linear checks flag first (horsepower, weight), else the first ones.
    const flagged = arr(ctx.data('trials') && ctx.data('trials').model && ctx.data('trials').model.families
      && ctx.data('trials').model.families.flags).map(f => f.feature).filter(Boolean);
    // Then the numeric columns (binned) before the categories: a curve shows along a range.
    const score = f => (flagged.includes(f.column) ? 2 : 0) + (f.binned ? 1 : 0);
    const cols = [...arr(m.byFeature)].sort((a, b) => score(b) - score(a)).filter(f => f.groups.length > 1).slice(0, features);
    for (const f of cols) {
      const box = el('div', { 'data-figure': 'residual-by-feature', 'data-column': f.column });
      ctx.components.dotScale(box, { title: c.byFeature(f.column, name), zero: true,
        rows: f.groups.map(g => ({ label: g.value, point: g.meanResidual, low: null, high: null,
          pointText: g.meanResidual === null ? '' : `${signed(ctx, g.meanResidual)}${unit}`, intervalText: '' })),
        concl: c.bend, kind: 'generic' });
      out.push(box);
    }
    return out;
  }

  // --- the trial budget as a bar (R44, R47) ---------------------------------------------------

  function budgetBar(ctx, budget, line = null) {
    if (!budget || !ok(budget.max) || !ok(budget.used)) return null;
    const c = F().budget;
    const n = v => ctx.format.number(v, 'int');
    return el('div', { className: 'ht-budget', 'data-budget-bar': `${budget.used}/${budget.max}` }, [
      line ? null : el('span', { className: 'ht-budget-l', text: c.title }),
      el('span', { className: 'ht-budget-cells', 'aria-hidden': 'true' }, Array.from({ length: budget.max }, (_, i) =>
        el('i', { className: i < budget.used ? 'ht-used' : null }))),
      el('span', { className: 'ht-budget-v', text: line || c.line(n(budget.used), n(budget.max)) }),
    ]);
  }

  // --- one result's figure ---------------------------------------------------------------------

  function slotFigure(ctx, step, r, opts = {}) {
    const a = String(r.slot).split(':')[0];
    let nodes;
    if (a === 'eda.quality') nodes = [qualityColumns(ctx, r.slot, opts.changed || [], opts.indicator === true)];
    else if (a.startsWith('eda.')) nodes = [PARTS('eda').cardFor ? PARTS('eda').cardFor(ctx, r.slot) : null];
    else if (a === 'diag.regression') nodes = residualFigures(ctx, r.slot, opts);
    else nodes = [PARTS('evidence').slotFigure ? PARTS('evidence').slotFigure(ctx, step, r.slot) : null];
    return block(ctx, frameOf(r.slot), nodes, { 'data-step-figure': r.slot });
  }

  // --- method diagrams (R53) ---------------------------------------------------------------------

  function partition(ctx) {
    const c = F().diagrams.partition;
    const ft = ctx.snapshot && ctx.snapshot.finalTest;
    if (!ft || !ok(ft.rows) || !ok(ft.developmentRows)) return null;
    const total = ft.rows + ft.developmentRows;
    const n = v => ctx.format.number(v, 'int');
    const opened = ft.status === 'opened';
    return el('div', { className: 'ht-diagram', 'data-diagram': 'partition' }, [
      el('p', { className: 'ht-figtitle', text: c.title }),
      el('div', { className: 'ht-partition', role: 'img', 'aria-label': `${c.development(n(ft.developmentRows))} · ${opened ? c.opened(n(ft.rows)) : c.sealed(n(ft.rows))}` }, [
        el('span', { className: 'ht-part-dev', css: { '--w': ((ft.developmentRows / total) * 100).toFixed(2) } }, [c.development(n(ft.developmentRows))]),
        el('span', { className: `ht-part-final${opened ? ' ht-part-opened' : ''}`, css: { '--w': ((ft.rows / total) * 100).toFixed(2) } },
          [opened ? c.opened(n(ft.rows)) : `🔒 ${c.sealed(n(ft.rows))}`]),
      ]),
      ft.method && c.methods[ft.method] ? el('p', { className: 'ht-faint', 'data-partition-method': ft.method, text: c.methods[ft.method] }) : null,
      el('p', { className: 'ht-faint', text: c.reading }),
    ]);
  }

  function folds(ctx) {
    const c = F().diagrams.folds;
    const ev = evidenceOf(ctx);
    const cv = ev && ev.crossValidation;
    if (!cv || !arr(cv.foldRows).length) return null;
    const total = cv.foldRows.reduce((s, f) => s + (f.nRows || 0), 0) || 1;
    const fmt = v => ctx.format.number(v, Number.isInteger(v) ? 'int' : 'auto');
    const rows = cv.foldRows.map((f, i) => {
      const range = arr(cv.foldRanges).find(x => x.fold === f.fold);
      return el('div', { className: 'ht-foldrow', 'data-fold': String(f.fold) }, [
        el('span', { className: 'ht-foldlab', text: c.block(ctx.format.number(f.fold, 'int')) }),
        el('span', { className: 'ht-foldtrk', 'aria-hidden': 'true' }, cv.foldRows.map((g, j) =>
          el('i', { className: j === i ? 'ht-fold-pred' : 'ht-fold-fit', css: { '--w': (((g.nRows || 0) / total) * 100).toFixed(2) } }))),
        el('span', { className: 'ht-foldtxt' }, [ctx.format.number(f.nRows, 'int'),
          range && ok(range.min) && ok(range.max) ? ` · ${c.span(fmt(range.min), fmt(range.max))}` : '']),
      ]);
    });
    return el('div', { className: 'ht-diagram', 'data-diagram': 'folds' }, [
      // The order column is a data name: set as code, never in the prose (NOW-12).
      el('p', { className: 'ht-figtitle' }, [c.title(Boolean(cv.orderColumn)), cv.orderColumn ? [' (', el('code', { text: cv.orderColumn }), ')'] : null]),
      el('div', { className: 'ht-folds', role: 'list' }, rows),
      el('p', { className: 'ht-faint', text: c.reading }),
    ]);
  }

  function pipeline(ctx) {
    const c = F().diagrams.pipeline;
    const snap = ctx.snapshot || {};
    const d = snap.decisions && snap.decisions.preprocessing;
    const open = arr(snap.proposals).find(p => p.decisionId === 'preprocessing');
    let v = open ? open.value : d ? d.value : null;
    try { v = typeof v === 'string' ? JSON.parse(v) : v; } catch (_) { v = null; }
    if (!v || typeof v !== 'object') return null;
    const logs = arr(v.log_transform);
    const caps = Object.keys(v.caps || {});
    const transform = [logs.length ? c.log(logs.join(', ')) : null, caps.length ? c.caps(caps.join(', ')) : null].filter(Boolean).join(' · ') || c.none;
    const impute = v.missing === 'indicator' ? c.indicator : c.none;
    const step = (k, text, attrs = {}) => el('li', { className: 'ht-pipe-step', ...attrs }, [el('strong', { text: c.steps[k] }),
      text ? [el('br'), text] : null]);
    return el('div', { className: 'ht-diagram', 'data-diagram': 'pipeline' }, [
      el('p', { className: 'ht-figtitle', text: c.title }),
      el('ol', { className: 'ht-pipe' }, [step('column', c.columnText), step('impute', impute), step('transform', transform, { 'data-pipe-transform': logs.join(',') }),
        step('model', c.modelText)]),
      el('p', { className: 'ht-faint', text: c.reading }),
    ]);
  }

  function oneSe(ctx) {
    const c = F().diagrams.oneSe;
    const ev = evidenceOf(ctx);
    const s = ev && ev.selection;
    if (!s || !s.oneSe || !arr(s.configurations).length) return null;
    const metric = HT.copy.evidence.measures[s.metric] || s.metric || '';
    const best = s.configurations.find(x => x.slot === s.oneSe.best);
    const box = el('div', { className: 'ht-diagram', 'data-diagram': 'one_se' });
    ctx.components.dotScale(box, { title: c.title(metric),
      band: best && ok(best.mean.value) && ok(s.oneSe.bound.value) ? { low: Math.min(best.mean.value, s.oneSe.bound.value),
        high: Math.max(best.mean.value, s.oneSe.bound.value), label: c.band } : null,
      rows: s.configurations.map(x => ({ label: `${cap(label(ctx, x.slot))}${x.slot === s.oneSe.pick ? ` · ${c.picked}` : x.slot === s.oneSe.best ? ` · ${c.best}` : ''}`,
        point: x.mean.value, low: null, high: null, highlight: x.slot === s.oneSe.pick,
        pointText: ok(x.mean.value) ? f2(ctx, x.mean.value) : '', intervalText: '' })),
      concl: c.reading });
    return box;
  }

  function ledgerTimeline(ctx) {
    const c = F().diagrams.ledger;
    const snap = ctx.snapshot || {};
    const looks = new Set(arr(snap.edaLooks && snap.edaLooks.results));
    const items = arr(snap.digest && snap.digest.items);
    const marks = [];
    const seen = new Set();
    for (const i of items) {
      if (i.resultId && looks.has(i.resultId) && !seen.has(i.resultId) && ok(i.revision)) {
        seen.add(i.resultId);
        marks.push({ revision: i.revision, kind: 'look' });
      }
    }
    const opening = snap.finalTest && snap.finalTest.opening;
    if (opening && ok(opening.revision)) marks.push({ revision: opening.revision, kind: 'opening' });
    const now = snap.revision || 1;
    if (!marks.length) return el('div', { className: 'ht-diagram', 'data-diagram': 'ledger' }, [
      el('p', { className: 'ht-figtitle', text: c.title }), el('p', { className: 'ht-faint', text: c.none })]);
    const x = r => ((Math.max(0, r - 1) / Math.max(1, now - 1)) * 100).toFixed(2);
    return el('div', { className: 'ht-diagram', 'data-diagram': 'ledger' }, [
      el('p', { className: 'ht-figtitle', text: c.title }),
      el('div', { className: 'ht-timeline', role: 'img', 'aria-label': `${marks.filter(m => m.kind === 'look').length} · ${c.look}` }, [
        el('span', { className: 'ht-tl-line' }),
        ...marks.map(m => el('span', { className: `ht-tl-mark ht-tl-${m.kind}`, 'data-ledger-mark': m.kind, title: `${c[m.kind]} · ${c.revision(m.revision)}`,
          css: { '--x': x(m.revision) } })),
      ]),
      el('p', { className: 'ht-legend', 'aria-hidden': 'true' }, [el('span', {}, [el('i', { className: 'ht-tl-key-look' }), c.look]),
        opening ? el('span', {}, [el('i', { className: 'ht-tl-key-opening' }), c.opening]) : null,
        el('span', { className: 'ht-faint', text: ` · ${c.revision(now)} = ${c.now}` })]),
      el('p', { className: 'ht-faint', text: c.reading }),
    ]);
  }

  const DIAGRAMS = { partition, folds, pipeline, one_se: oneSe, ledger: ledgerTimeline };

  function diagram(ctx, id) {
    const fn = DIAGRAMS[id];
    const node = fn ? fn(ctx) : null;
    return node ? block(ctx, 'method', [node], { 'data-method-diagram': id }) : null;
  }

  // --- Now: "To answer, look at" (R39-R45, R53) ---------------------------------------------------

  function nowFigures(ctx, now) {
    const c = F();
    const f = now.figures;
    if (!f) return null;
    const nodes = f.slots.filter(r => r.current).map(r => slotFigure(ctx, f.step, r, { changed: f.changed, indicator: f.indicator }));
    const diagrams = f.diagrams.map(id => diagram(ctx, id)).filter(Boolean);
    const list = [...nodes.filter(Boolean), ...diagrams];
    return el('section', { className: 'ht-nowfigs', 'data-now-figures': f.source, 'aria-labelledby': 'ht-nowfigs-h' }, [
      // At a choice the comparison card already says "To answer, look at": these are the step's own figures.
      el('h3', { id: 'ht-nowfigs-h', className: 'ht-k', text: now.figure ? c.figuresOf : c.lookAt }),
      ...(list.length ? list : [el('p', { className: 'muted', 'data-no-chart': true, text: c.noChart })]),
    ]);
  }

  /** R50: an opened step's figures, inline, then its diagrams. */
  function stepFigures(ctx, line) {
    const results = arr(line.results).filter(r => r.current);
    const nodes = results.map(r => slotFigure(ctx, line.id, r, { changed: [] }));
    const diagrams = arr(line.diagrams).map(id => diagram(ctx, id));
    const list = [...nodes, ...diagrams].filter(Boolean);
    return list.length ? el('div', { className: 'ht-stepfigs', 'data-step-figures': line.id }, list) : null;
  }

  // --- the end: one table, then dots on one scale (R48, R52) -------------------------------------

  function devFinal(ctx) {
    const c = F().devFinal;
    const ev = evidenceOf(ctx);
    if (!ev) return el('p', { className: 'muted', 'aria-busy': 'true', text: F().reading });
    const snap = ctx.snapshot;
    const regression = task(ctx) === 'regression';
    const metricId = regression ? 'mae' : 'precision';
    const metric = HT.copy.evidence.measures[metricId] || metricId;
    const u = ev.uncertainty;
    const fe = ev.finalEvaluation && ev.finalEvaluation.current ? ev.finalEvaluation : null;
    const devM = u ? (u.kind === 'policy' ? arr((arr(u.rules)[0] || {}).metrics) : arr(u.metrics)).find(m => m.metric === metricId) : null;
    const finM = fe ? arr(fe.metrics).find(m => m.metric === metricId) : null;
    const chosen = (fe && fe.model) || (snap.finalTest && snap.finalTest.opening && snap.finalTest.opening.model) || null;
    const fmt = x => (regression ? f2(ctx, x) : ctx.format.number(x, 'pct1'));
    const unit = regression && ev.uncertainty && ev.uncertainty.unit ? ` ${ev.uncertainty.unit}` : '';
    const cellOf = (m, rid, fit) => {
      const x = m && arr(m.models).find(y => y.fit === fit && y.point !== null);
      if (!x) return null;
      return { x, text: x.low !== null && x.high !== null ? `${fmt(x.point)} [${fmt(x.low)} ; ${fmt(x.high)}]` : fmt(x.point), rid };
    };
    const fits = arr(devM && devM.models).map(m => m.fit);
    const order = [...fits.filter(f => f !== 'fit.baseline'), 'fit.baseline'].filter((f, i, a) => a.indexOf(f) === i);
    const td = (cell, attrs = {}) => el('td', attrs, cell ? [ctx.components.cited(cell.text, { resultId: cell.rid, path: cell.x.path, value: cell.x.point })] : []);
    const rows = order.map(fit => {
      const dv = cellOf(devM, u && u.resultId, fit);
      const fv = cellOf(finM, fe && fe.resultId, fit);
      const name = `${cap(label(ctx, fit))}${fit === chosen ? ` · ${c.chosen}` : ''}`;
      return el('tr', { 'data-config': fit, className: fit === chosen ? 'ht-chosen' : null }, [
        el('td', { className: 'ht-rowhead', text: name }), td(dv),
        fv ? td(fv) : el('td', { className: 'ht-faint', 'data-not-measured': fit, text: fe ? c.notMeasured : '—' })]);
    });
    const dd = devM && devM.delta;
    const fd = finM && finM.delta;
    const dText = x => (x && x.point !== null ? `${signed(ctx, x.point)}${x.low !== null ? ` [${signed(ctx, x.low)} ; ${signed(ctx, x.high)}]` : ''}` : '');
    if (dd || fd) {
      const who = cap(label(ctx, (fd || dd).fit));
      rows.push(el('tr', { 'data-config': 'difference' }, [el('td', { className: 'ht-rowhead', text: c.difference(who) }),
        el('td', {}, dd ? [ctx.components.cited(dText(dd), { resultId: u.resultId, path: dd.path, value: dd.point })] : []),
        el('td', {}, fd ? [ctx.components.cited(dText(fd), { resultId: fe.resultId, path: fd.path, value: fd.point })] : [])]));
    }
    const cc = snap.criterionConfigurations;
    if (cc && cc.bound) {
      const st = s => ({ met: c.met, not_met: c.notMet, uncertain: c.uncertain })[s] || s || '';
      const devCfg = arr(cc.configurations).find(x => x.slot === chosen);
      const ft = cc.finalTest;
      rows.push(el('tr', { 'data-config': 'criterion' }, [el('td', { className: 'ht-rowhead', text: c.criterion }),
        el('td', { text: cc.bound.value !== null ? c.criterionCell(`${fmt(cc.bound.value)}${unit}`, st(devCfg && devCfg.status)) : '' }),
        el('td', { 'data-criterion-final': ft ? ft.status : '' , text: ft && ft.bound && ft.bound.value !== null ? c.criterionCell(`${fmt(ft.bound.value)}${unit}`, st(ft.status)) : '' })]));
    }
    const table = el('table', { className: 'ht-devfinal', 'data-dev-final': String(order.length) }, [
      el('caption', { text: c.title }),
      el('thead', {}, [el('tr', {}, [el('th', { scope: 'col', text: c.configuration }), el('th', { scope: 'col', text: c.development }),
        el('th', { scope: 'col', text: c.final })])]),
      el('tbody', {}, rows)]);
    const wrap = el('div', { className: 'ht-scrollx', 'data-scroll-ok': true, tabindex: '0', role: 'region', 'aria-label': c.title }, [table]);
    // The same as dots with intervals on one scale: development (◐ ring) and final (● dot).
    const box = el('div', { 'data-figure': 'dev-final-dots' });
    const level = fe && fe.bootstrap && fe.bootstrap.level !== null ? ctx.format.number(fe.bootstrap.level, 'pct0') : null;
    const dotRows = [];
    for (const fit of order) {
      const dv = cellOf(devM, null, fit);
      const fv = cellOf(finM, null, fit);
      if (dv) dotRows.push({ label: `◐ ${cap(label(ctx, fit))}`, point: dv.x.point, low: dv.x.low, high: dv.x.high, mark: 'development',
        tone: fit === 'fit.baseline' ? 'baseline' : null, highlight: fit === chosen, pointText: fmt(dv.x.point), intervalText: '' });
      if (fv) dotRows.push({ label: `● ${cap(label(ctx, fit))}`, point: fv.x.point, low: fv.x.low, high: fv.x.high, mark: 'final',
        tone: fit === 'fit.baseline' ? 'baseline' : null, highlight: fit === chosen, pointText: fmt(fv.x.point), intervalText: '' });
    }
    if (dotRows.length) {
      const bound = cc && cc.finalTest && cc.finalTest.bound && cc.finalTest.bound.value !== null ? cc.finalTest.bound.value : null;
      ctx.components.dotScale(box, { title: `${c.chart(metric)}${level ? F().intervalKind.bootstrap(level) : ''}`, rows: dotRows,
        refs: bound !== null ? [{ value: bound, label: `${c.bound} ${fmt(bound)}` }] : [], plain: true });
    }
    return el('div', { className: 'ht-devfinal-wrap', 'data-frame': 'final' }, [
      el('p', { className: 'ht-frame' }, [el('strong', { text: F().frames.final })]), wrap, box]);
  }

  // --- "And after" (R49) ------------------------------------------------------------------------

  function azureOutcome(ctx) {
    const c = F().after;
    const o = ctx.outcome('azureml');
    if (!o) return null;
    const rec = o.recorded || {};
    const okk = o.kind === 'ok' || o.kind === 'ok_with_problems';
    return el('div', { 'data-azureml-outcome': o.kind }, [ctx.renderOutcome(o),
      okk && arr(rec.files).length ? el('p', { text: c.azureDone(ctx.format.number(rec.files.length, 'int')) }) : null,
      okk && rec.out ? el('p', { className: 'ht-mono', 'data-azureml-out': true, text: c.azureOut(rec.out) }) : null]);
  }

  function azurePlan(ctx, now) {
    const c = F().after;
    const after = now.afterStudy;
    if (!after) return null;
    if (!after.exportPlanAvailable) {
      return el('div', { className: 'card ht-azure', 'data-azureml': 'unsupported' }, [el('h3', { text: c.azureTitle }),
        el('p', { text: c.azureNotSupported }),
        after.azureReason ? HT.components.engineText(after.azureReason, { tag: 'p', lang: ctx.snapshot.language || 'en' }) : null,
        el('p', { className: 'ht-faint', text: c.azureCloud })]);
    }
    if (!ctx.atLeast('v3')) return el('p', { className: 'ht-faint', 'data-stage-line': 'v3', text: c.exportPlanLater('v3') });
    ctx.want('azureml');
    const d = ctx.data('azureml');
    const err = ctx.error('azureml');
    const kids = [el('h3', { text: c.azureTitle }), el('p', { className: 'ht-faint', text: c.azureLead })];
    if (err) kids.push(el('p', { role: 'alert', 'data-azureml-error': true, text: err.message }));
    else if (!d || !d.model) kids.push(el('p', { className: 'muted', 'aria-busy': 'true', text: c.azureReading }));
    else {
      const m = d.model;
      const n = v => ctx.format.number(v, 'int');
      const kinds = Object.entries(m.kinds).map(([k, v]) => `${n(v)} ${c.azureKinds[k] || k}`).join(' · ');
      kids.push(el('ul', { className: 'ht-azure-facts', 'data-azureml-plan': String(m.files.length) }, [
        el('li', { text: `${c.azureFiles(n(m.files.length))}${kinds ? ` (${kinds})` : ''}` }),
        after.azureFamily ? el('li', { text: c.azureModel(c.azureFamilies[after.azureFamily] || after.azureFamily) }) : null,
        el('li', { text: c.azureTemplate(m.template.id, m.template.version) }),
        m.configurationStatus || m.artifactStatus ? el('li', { text: c.azureStatus(m.configurationStatus || '', m.artifactStatus || '') }) : null,
        m.missingFields.length ? el('li', { text: c.azureMissing(n(m.missingFields.length)) }) : null,
      ]));
      kids.push(el('details', { className: 'ht-details' }, [el('summary', { text: c.azureFilesFold }),
        el('ul', { className: 'ht-mono ht-azure-files' }, m.files.map(f => el('li', { text: f.path })))]));
    }
    kids.push(el('p', { className: 'ht-azure-cloud', 'data-azureml-cloud': 'never', text: c.azureCloud }));
    const running = ctx.busy && ctx.busyOp === 'W8';
    kids.push(el('button', { type: 'button', 'data-write': 'azureml', 'data-stage': 'v3', disabled: ctx.busy ? true : null,
      'aria-busy': running ? 'true' : null, text: running ? HT.copy.core.working : c.azureButton,
      onclick: () => ctx.send({ type: 'export_azureml', revision: ctx.snapshot.revision }) }));
    kids.push(el('p', { className: 'ht-faint', text: c.azureHint }));
    kids.push(azureOutcome(ctx));
    return el('div', { className: 'card ht-azure', 'data-azureml': 'supported' }, kids);
  }

  function after(ctx, now) {
    const kids = [];
    if (ctx.atLeast('v3')) {
      // W7 here too (R49): the same message as the Deliverables drawer's button, whose card
      // shows the outcome and the files.
      const c = F().after;
      const running = ctx.busy && ctx.busyOp === 'W7';
      kids.push(el('div', { className: 'card ht-azure', 'data-after-handoff': true }, [
        el('h3', { text: HT.copy.learn.handoffTitle }), el('p', { text: c.handoffLead }),
        el('button', { type: 'button', 'data-write': 'export', 'data-stage': 'v3', disabled: ctx.busy ? true : null,
          'aria-busy': running ? 'true' : null, text: running ? HT.copy.core.working : HT.copy.learn.exportButton,
          onclick: () => ctx.send({ type: 'export_handoff', revision: ctx.snapshot.revision }) }),
        el('p', { className: 'ht-faint', text: c.handoffWhere })]));
    }
    kids.push(azurePlan(ctx, now));
    return kids.filter(Boolean);
  }

  // --- What if? in its own tab (R51) -------------------------------------------------------------

  const tab = { fit: null };

  function largestTable(ctx, d, m) {
    const c = F().whatif;
    const cols = c.largestColumns;
    const t = el('table', { className: 'ht-largest', 'data-largest': String(m.largest.length) }, [
      el('caption', { text: c.largestTitle(label(ctx, m.fit)) }),
      el('thead', {}, [el('tr', {}, [cols.row, cols.observed, cols.predicted, cols.residual, ...Object.keys(m.largest[0].values)]
        .map(h => el('th', { scope: 'col', text: h })))]),
      el('tbody', {}, m.largest.map(x => el('tr', {}, [el('td', { className: 'ht-mono', text: x.rowKey }),
        el('td', { text: ok(x.observed) ? f2(ctx, x.observed) : '' }), el('td', { text: ok(x.predicted) ? f2(ctx, x.predicted) : '' }),
        el('td', {}, ok(x.residual) ? [ctx.components.cited(signed(ctx, x.residual), { resultId: d.resultId, path: x.path, value: x.residual })] : []),
        ...Object.values(x.values).map(v => el('td', { text: v }))]))),
    ]);
    return el('div', { className: 'ht-scrollx', 'data-scroll-ok': true, tabindex: '0', role: 'region', 'aria-label': c.largestTitle(label(ctx, m.fit)) }, [t]);
  }

  function residualExplorer(ctx) {
    const c = F().whatif;
    const ev = evidenceOf(ctx);
    if (!ev) return [el('p', { className: 'muted', 'aria-busy': 'true', text: F().reading })];
    const d = arr(ev.diagnostics).find(x => x.slot === 'diag.regression');
    if (!d || !arr(d.models).length) return [el('p', { className: 'muted', 'data-no-diagnostics': true, text: c.noDiagnostics })];
    if (!tab.fit || !d.models.some(m => m.fit === tab.fit)) tab.fit = d.models[0].fit;
    const m = d.models.find(x => x.fit === tab.fit);
    const picker = el('fieldset', { className: 'ht-wi-models', 'data-tab-configuration': true }, [el('legend', { text: c.configuration }),
      ...d.models.map(x => el('label', { className: 'ht-ev-radio' }, [
        el('input', { type: 'radio', name: 'ht-tab-fit', value: x.fit, checked: x.fit === tab.fit,
          onchange: () => { tab.fit = x.fit; ctx.rerender(); } }), cap(label(ctx, x.fit))]))]);
    const out = [el('h2', { text: c.residualTitle }), picker];
    out.push(block(ctx, 'development', residualFigures(ctx, 'diag.regression', { features: 6, model: m.fit })));
    if (!arr(m.byFeature).some(f => /year/i.test(f.column))) out.push(el('p', { className: 'ht-faint', 'data-no-chart': 'model_year', text: c.byYearMissing }));
    if (arr(m.largest).length) out.push(block(ctx, 'development', [largestTable(ctx, d, m)]));
    return out;
  }

  function whatifTab(ctx) {
    const c = F().whatif;
    const snap = ctx.snapshot;
    const head = el('header', { className: 'ht-top ht-tabhead', 'data-block': 'header' }, [
      el('h1', { className: 'ht-tabtitle', text: c.tabTitle }),
      el('p', { className: 'ht-calm', 'data-whatif-calm': true, text: c.calm }),
      el('details', { className: 'ht-why' }, [el('summary', { text: c.why }), el('p', { text: c.whyBody })]),
    ]);
    if (!snap) return [head, el('main', { id: 'main', 'aria-busy': 'true' }, [el('p', { className: 'muted', text: HT.copy.page.reading })])];
    setStudyVariants(snap);
    const body = snap.task === 'regression' ? residualExplorer(ctx) : [PARTS('whatif').body ? PARTS('whatif').body(ctx) : null];
    return [head, el('main', { id: 'main', className: 'ht-whatif-tab', 'data-whatif-tab': snap.task }, body.filter(Boolean))];
  }

  HT.parts = HT.parts || {};
  HT.parts.figures = { nowFigures, stepFigures, diagram, devFinal, after, whatifTab, budgetBar, qualityColumns, residualFigures,
    setStudyVariants, frameOf };
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
