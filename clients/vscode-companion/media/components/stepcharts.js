// The drawings of a step card (lot 2026-10-28, docs/plans/LOT-2026-10-28-SPEC.md §5 PA-3,
// PA-6 to PA-11; approved mockup docs/plans/mockups/panel-all-steps-fr.html).
//
//   Hypotrail.components.stepPicture(ctx, picture)        block 1: the step in one picture
//   Hypotrail.components.stepChart(ctx, question, card)    block 3: one drawing per chart kind
//
// Every number drawn is a registered value (read from `evidence --json` at the result the
// question names), a value of the digest the panel already reads, or a `chart_data` value of
// the engine's step card; the panel computes no figure of its own except the common range of
// an observed-versus-predicted plot when the result has none (PA-10). A kind the panel does not
// know, or a chart whose values are not read yet, says so in one line. The timeline's slider
// is display only: it moves a marker, sends nothing and records nothing (PA-6).
//
// SVG colours are classes (`sc-f-<role>` fill, `sc-s-<role>` stroke) mapped to the theme's
// tokens in media/css/stepcard.css; sizes are attributes; study text is a text node.
(function (HT) {
  'use strict';
  const el = (...a) => HT.el(...a);
  const S = (tag, attrs, kids) => HT.svg(tag, attrs, kids);
  const C = () => HT.copy.stepcard;
  const arr = x => (Array.isArray(x) ? x : []);
  const ok = v => typeof v === 'number' && Number.isFinite(v);
  const obj = x => (x && typeof x === 'object' && !Array.isArray(x) ? x : {});
  /** A model's name in words (the study's variants by their family), capitalised. */
  function mname(ctx, slot) {
    const J = HT.copy.junior || {};
    const n = J.modelName ? J.modelName(slot, ctx.snapshot && ctx.snapshot.task) : null;
    return n ? n.charAt(0).toUpperCase() + n.slice(1) : String(slot || '');
  }

  // --- SVG helpers --------------------------------------------------------------------------

  function T(x, y, s, o = {}) {
    return S('text', { x: r2(x), y: r2(y), 'font-size': o.fs || 11, 'text-anchor': o.a || 'start', className: `sc-f-${o.c || 'muted'}`,
      'font-weight': o.w || null, 'font-style': o.st || null, opacity: o.op || null, transform: o.tr || null }, [String(s)]);
  }
  function Ln(x1, y1, x2, y2, c = 'muted', w = 1, da = null) {
    return S('line', { x1: r2(x1), y1: r2(y1), x2: r2(x2), y2: r2(y2), className: `sc-s-${c}`, 'stroke-width': w, 'stroke-dasharray': da });
  }
  function Rc(x, y, w, h, c, o = {}) {
    return S('rect', { x: r2(x), y: r2(y), width: r2(Math.max(0, w)), height: r2(Math.max(0, h)),
      className: `sc-f-${c}${o.s ? ` sc-s-${o.s}` : ''}`, rx: o.rx || null, opacity: o.op || null,
      'stroke-width': o.sw || null, 'stroke-dasharray': o.da || null, 'data-mark': o.mark || null });
  }
  function Ci(cx, cy, r, c, o = {}) {
    return S('circle', { cx: r2(cx), cy: r2(cy), r, className: `sc-f-${c}${o.s ? ` sc-s-${o.s}` : ''}`, opacity: o.op || null,
      'stroke-width': o.sw || null, 'data-mark': o.mark || null });
  }
  function P(d, c, o = {}) {
    return S('path', { d, className: `sc-f-${o.fill || 'none'} sc-s-${c}`, 'stroke-width': o.w || 1.5, 'stroke-dasharray': o.da || null });
  }
  const r2 = v => (typeof v === 'number' ? Math.round(v * 100) / 100 : v);
  function box(w, h, label, kids, attrs = {}) {
    return S('svg', { viewBox: `0 0 ${w} ${h}`, role: 'img', 'aria-label': label, className: 'sc-svg', ...attrs }, kids);
  }
  function hatch() {
    return S('defs', {}, [S('pattern', { id: 'ht-sc-hatch', width: 6, height: 6, patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)' }, [
      Rc(0, 0, 6, 6, 'hatchbg'), Ln(0, 0, 0, 6, 'now', 2)])]);
  }

  // --- reading helpers ------------------------------------------------------------------------

  const fmt = (ctx, v, f = 'f2') => (ok(v) ? ctx.format.number(v, f) : '');
  const lang = ctx => (ctx.language ? ctx.language() : 'en');

  /** A column's display name: the case's (`case_display`, EN-18), else the name with spaces. */
  function colName(ctx, column) {
    const cd = ctx.snapshot && ctx.snapshot.caseDisplay;
    const c = cd && cd.columns ? cd.columns[column] : null;
    const l = lang(ctx);
    if (c && (c[l] || c.en)) return c[l] || c.en;
    return String(column || '').replace(/_/g, ' ');
  }

  function evidence(ctx) {
    if (ctx.want) ctx.want('evidence');
    const d = ctx.data('evidence');
    return d && d.model ? d.model : null;
  }

  /** The registered values of a result by its id, else by its slot; null when not read yet. */
  function valuesOf(ctx, resultId, slot) {
    const ev = evidence(ctx);
    const v = ev && ev.values ? ev.values : null;
    if (!v) return null;
    if (resultId && v.byId[resultId]) return v.byId[resultId];
    const id = slot ? v.bySlot[slot] : null;
    return id && v.byId[id] ? v.byId[id] : null;
  }
  const idOf = (ctx, slot) => {
    const ev = evidence(ctx);
    return ev && ev.values ? ev.values.bySlot[slot] || null : null;
  };

  /** A value cited to its result and path (hover), as the other figures cite. */
  function cite(ctx, text, resultId, path, value) {
    return resultId ? ctx.components.cited(text, { resultId, path, value }) : text;
  }

  function note(text, attrs = {}) {
    return el('p', { className: 'sc-cap', ...attrs, text });
  }
  function unavailable(why = null) {
    return el('p', { className: 'sc-unavailable', 'data-chart-unavailable': why || 'kind', text: why === 'reading' ? C().reading : C().unavailable });
  }

  /** Ticks over [lo, hi]: about `n` round steps. */
  function ticks(lo, hi, n = 4) {
    const span = hi - lo || 1;
    const raw = span / n;
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw) || raw;
    const out = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(Math.round(v / step) * step);
    return { list: out, step };
  }

  // --- block 1: the step in one picture (illustrative or structural only, §8.5) ----------------

  function rowsPic(ctx, kids, label) {
    return box(130, 90, label, kids, { 'aria-hidden': 'true', role: null, className: 'sc-svg sc-pic' });
  }

  const PICTURES = {
    row_card: () => {
      const p = C().pictures;
      return [Rc(4, 4, 122, 82, 'none', { s: 'faint', rx: 4 }), T(10, 17, p.oneRow, { fs: 9, c: 'now' }),
        T(10, 32, '…  …  …  …', { fs: 9, c: 'ink' }), T(10, 46, '…  …', { fs: 9, c: 'ink' }), T(10, 60, '…  …  …', { fs: 9, c: 'ink' }),
        Rc(8, 66, 114, 15, 'nowtint', { rx: 2 }), T(10, 77, p.target, { fs: 8, c: 'now' }), T(110, 77, '…', { fs: 9, c: 'now' })];
    },
    moment_timeline: () => {
      const p = C().pictures;
      return [Ln(8, 50, 124, 50, 'faint', 1.5), ...[14, 46, 78, 112].map((x, i) => Ci(x, 50, i === 3 ? 4 : 3, i === 3 ? 'warn' : 'ink')),
        Ln(62, 24, 62, 72, 'now', 2, '3 2'), T(62, 18, p.moment, { fs: 9, a: 'middle', c: 'now' }),
        T(14, 66, p.knownBefore, { fs: 8, a: 'start', c: 'faint' }), T(124, 66, p.measured, { fs: 8, a: 'end', c: 'warn' }),
        T(4, 88, p.scenario, { fs: 7.5, c: 'faint', st: 'italic' })];
    },
    variables_board: () => {
      const p = C().pictures;
      const cols = [['✓', 3, 'ok', null], ['✕', 1, 'warn', '2 2'], ['—', 2, 'faint', null]];
      const out = [];
      cols.forEach(([s, n, c, da], i) => {
        const x = 6 + i * 42;
        out.push(T(x, 14, s, { fs: 10, c }));
        for (let k = 0; k < n; k++) out.push(Rc(x, 20 + k * 11, 36, 8, 'none', { s: c, rx: 2, da }));
      });
      out.push(T(6, 86, p.board, { fs: 7.5, c: 'faint' }));
      return out;
    },
    partition_strip: (ctx, d) => {
      const p = C().pictures;
      const dev = d && ok(d.development) ? d.development : null;
      const sealed = d && ok(d.sealed) ? d.sealed : null;
      const n = v => (v === null ? '…' : ctx.format.number(v, 'int'));
      return [Rc(4, 34, 92, 22, 'none', { s: 'faint', rx: 3 }), T(50, 49, p.development(n(dev)), { fs: 8.5, a: 'middle', c: 'ink' }),
        Rc(100, 34, 26, 22, 'seal', { rx: 3 }), T(113, 49, n(sealed), { fs: 9, a: 'middle', c: 'board' }),
        T(113, 26, p.sealed, { fs: 8.5, a: 'middle', c: 'seal' }), T(65, 74, p.countsOnly, { fs: 8, a: 'middle', c: 'faint' })];
    },
    error_gap: () => {
      const p = C().pictures;
      return [Ln(10, 78, 124, 78, 'faint'), Ln(10, 78, 10, 8, 'faint'), Ci(66, 22, 4, 'ink'), T(74, 25, p.observed, { fs: 9, c: 'ink' }),
        Ci(66, 60, 4, 'none', { s: 'now', sw: 1.8 }), T(74, 63, p.predicted, { fs: 9, c: 'now' }),
        Ln(60, 24, 60, 58, 'warn', 1.6), Ln(56, 24, 64, 24, 'warn', 1.2), Ln(56, 58, 64, 58, 'warn', 1.2),
        T(54, 44, p.error, { fs: 9, a: 'end', c: 'warn' }), T(14, 88, p.madeUp, { fs: 7.5, c: 'faint', st: 'italic' })];
    },
    criterion_bar: () => {
      const p = C().pictures;
      return [T(6, 14, p.referenceError, { fs: 8.5, c: 'faint' }), Rc(6, 18, 112, 14, 'none', { s: 'faint', rx: 2 }),
        T(6, 50, p.aimedError, { fs: 8.5, c: 'now' }), Rc(6, 54, 100, 14, 'nowtint', { s: 'now', rx: 2 }),
        Ln(106, 14, 106, 74, 'ok', 1.5, '3 2'), T(104, 84, p.lower, { fs: 8, a: 'middle', c: 'ok' }), T(6, 84, '✎', { fs: 9, c: 'faint' })];
    },
    quality_checks: () => {
      const p = C().pictures;
      return [Rc(8, 8, 22, 16, 'none', { s: 'faint' }), T(19, 20, '?', { fs: 11, a: 'middle', c: 'warn' }), T(38, 20, p.emptyCell, { fs: 8.5, c: 'ink' }),
        ...[10, 6, 2].map((h, i) => Rc(8 + i * 8, 48 - h * 1.6, 6, h * 1.6, 'faint')), T(38, 46, p.rareCategory, { fs: 8.5, c: 'ink' }),
        P('M8,72 C14,56 18,56 22,66 S28,72 32,72', 'faint'), T(38, 70, p.longTail, { fs: 8.5, c: 'ink' }),
        T(38, 86, p.outOfRange, { fs: 8.5, c: 'ink' }), Ln(8, 82, 30, 82, 'faint'), Ci(34, 82, 2, 'warn')];
    },
    log_before_after: () => {
      const p = C().pictures;
      return [...[20, 26, 16, 9, 6, 4, 3, 2].map((h, i) => Rc(4 + i * 6, 66 - h * 2, 5, h * 2, 'faint')),
        T(26, 80, p.before, { fs: 8.5, a: 'middle', c: 'faint' }), T(64, 46, p.toLog, { fs: 9, a: 'middle', c: 'now' }),
        ...[4, 9, 15, 19, 15, 9, 4, 2].map((h, i) => Rc(80 + i * 6, 66 - h * 2, 5, h * 2, 'now', { op: 0.85 })),
        T(104, 80, p.after, { fs: 8.5, a: 'middle', c: 'now' }), T(4, 10, p.madeUp, { fs: 7.5, c: 'faint', st: 'italic' })];
    },
    trend_reading: () => {
      const p = C().pictures;
      return [Ln(10, 80, 125, 80, 'faint'), Ln(10, 80, 10, 6, 'faint'),
        ...[[20, 18], [30, 26], [38, 24], [50, 38], [60, 44], [72, 52], [84, 58], [96, 62], [108, 64], [118, 66]].map(([x, y]) => Ci(x, y, 2.6, 'ink')),
        P('M18,20 C50,40 80,58 120,66', 'now', { w: 2 }), T(70, 22, p.trend, { fs: 9, c: 'now' }), T(14, 90, p.madeUp, { fs: 7.5, c: 'faint', st: 'italic' })];
    },
    mean_vs_line: () => {
      const p = C().pictures;
      return [Ln(10, 80, 125, 80, 'faint'), Ln(10, 80, 10, 6, 'faint'),
        ...[[18, 70], [28, 62], [36, 66], [48, 52], [58, 50], [68, 44], [80, 36], [92, 34], [104, 24], [116, 18]].map(([x, y]) => Ci(x, y, 2.6, 'ink')),
        Ln(12, 46, 124, 46, 'faint', 2, '4 3'), T(124, 58, p.mean, { fs: 8.5, a: 'end', c: 'faint' }),
        Ln(14, 72, 122, 16, 'now', 2), T(14, 14, p.line, { fs: 9, c: 'now' }), T(14, 90, p.madeUp, { fs: 7.5, c: 'faint', st: 'italic' })];
    },
    line_misses_curve: () => {
      const p = C().pictures;
      return [Ln(10, 80, 125, 80, 'faint'),
        ...[[18, 22], [30, 40], [42, 54], [54, 62], [66, 66], [78, 64], [90, 58], [102, 48], [114, 34]].map(([x, y]) => Ci(x, y, 2.6, 'ink')),
        Ln(14, 40, 120, 50, 'faint', 2, '4 3'), P('M16,22 Q66,96 116,32', 'now', { w: 2 }),
        T(18, 12, p.line, { fs: 9, c: 'faint' }), T(80, 12, p.curve, { fs: 9, c: 'now' }), T(14, 90, p.madeUp, { fs: 7.5, c: 'faint', st: 'italic' })];
    },
    one_se_rule: () => {
      const p = C().pictures;
      const dots = [[p.simple, 56, 26], [p.middle, 50, 42], [p.flexible, 22, 58]];
      return [Rc(20, 14, 44, 50, 'nowtint'), Ln(20, 14, 20, 64, 'now', 1), Ln(64, 14, 64, 64, 'now', 1, '3 2'),
        T(42, 10, p.bestPlusSe, { fs: 7.5, a: 'middle', c: 'now' }),
        ...dots.flatMap(([n, x, y]) => [Ci(x, y, 3.2, 'ink'), T(72, y + 3, n, { fs: 8.5, c: 'faint' })]),
        T(6, 80, p.simplestInBand, { fs: 8, c: 'now' }), T(6, 89, p.madeUp, { fs: 7.5, c: 'faint', st: 'italic' })];
    },
    sealed_once: (ctx, d) => {
      const p = C().pictures;
      const n = v => (ok(v) ? ctx.format.number(v, 'int') : '…');
      return [Rc(4, 30, 86, 22, 'none', { s: 'faint', rx: 3 }), T(47, 45, p.usedToChoose(n(d && d.development)), { fs: 8, a: 'middle', c: 'faint' }),
        Rc(94, 30, 32, 22, 'seal', { rx: 3 }), T(110, 45, n(d && d.sealed), { fs: 9, a: 'middle', c: 'board' }),
        Ln(110, 58, 110, 70, 'now', 2), T(110, 82, p.readOnce, { fs: 8.5, a: 'middle', c: 'now' }), T(110, 22, p.sealed, { fs: 8, a: 'middle', c: 'seal' })];
    },
    dev_vs_final: () => {
      const p = C().pictures;
      return [T(6, 16, p.devFrame, { fs: 9, c: 'ink' }), T(6, 28, p.optimistic, { fs: 8, c: 'faint' }),
        T(6, 54, p.finalTest, { fs: 9, c: 'seal' }), T(6, 66, p.independent, { fs: 8, c: 'faint' }), Ln(6, 38, 124, 38, 'line', 1),
        T(6, 86, p.twoFrames, { fs: 8, c: 'faint' })];
    },
  };

  /** Block 1's drawing, or null for a kind the panel does not draw (the caption stays). */
  function stepPicture(ctx, picture) {
    const fn = picture && PICTURES[picture.kind];
    if (!fn) return null;
    return rowsPic(ctx, fn(ctx, picture.data));
  }

  // --- block 3 charts read from chart_data ------------------------------------------------------

  /** The timeline (PA-6) at a marker position; `pos` indexes `positions` (EN-18, §8.6). */
  function timelineState(d, pos) {
    const positions = arr(d.positions);
    const at = positions[pos];
    if (at) return { after: at.after, kept: arr(at.kept), dropped: arr(at.dropped), uncertain: arr(at.uncertain) };
    // An engine without `positions`: the columns' own states at the recorded moment.
    const cols = arr(d.columns);
    return { after: d.moment_after, kept: cols.filter(c => c.state === 'kept').map(c => c.column),
      dropped: cols.filter(c => c.state !== 'kept' && !c.uncertain && c.known_at).map(c => c.column),
      uncertain: cols.filter(c => c.uncertain || !c.known_at).map(c => c.column) };
  }

  function timelineSvg(ctx, d, pos, moved) {
    const c = C().timeline;
    const ms = arr(d.milestones);
    const n = Math.max(ms.length, 2);
    const X = i => 30 + (i * (270 - 30)) / (n - 1);
    const st = timelineState(d, pos);
    const afterIdx = Math.max(0, ms.findIndex(m => m.id === st.after));
    const mx = (X(afterIdx) + X(Math.min(afterIdx + 1, n - 1))) / 2;
    const name = col => colName(ctx, col);
    const kids = [hatch(), T(0, 12, c.scenario, { fs: 10, c: 'acc', st: 'italic' }),
      Rc(mx, 22, 292 - mx, 134, 'shade'), T(288, 52, c.knownAfterShort, { fs: 9.5, a: 'end' }),
      Ln(10, 120, 292, 120, 'ink', 1.6), P('M292,120 l-6,-4 v8 z', 'ink', { fill: 'ink' })];
    ms.forEach((m, i) => {
      const last = i === ms.length - 1;
      kids.push(Ci(X(i), 120, last ? 5 : 4, last ? 'cwarn' : 'ink'));
      const words = String(m.label || m.id).split(' ');
      const half = Math.ceil(words.length / 2);
      const a = i === 0 ? 'start' : last ? 'end' : 'middle';
      const tx = i === 0 ? X(i) - 8 : last ? X(i) + 8 : X(i);
      kids.push(T(tx, 136, words.slice(0, half).join(' '), { fs: 10, a, c: last ? 'cwarn' : 'ink' }));
      kids.push(T(tx, 148, words.slice(half).join(' '), { fs: 10, a, c: last ? 'cwarn' : 'ink' }));
    });
    // The columns stacked above the milestone where they become known (uncertain ones in the lane).
    const at = {};
    for (const col of arr(d.columns)) {
      if (col.uncertain || !col.known_at || col.state === 'not_feature') continue;
      (at[col.known_at] = at[col.known_at] || []).push(col.column);
    }
    ms.forEach((m, i) => arr(at[m.id]).forEach((col, j) => {
      const kept = st.kept.includes(col);
      kids.push(T(i === 0 ? X(i) - 8 : X(i), 108 - j * 13, `${kept ? '✓' : '✕'} ${name(col)}`,
        { fs: 10.5, a: i === 0 ? 'start' : 'middle', c: kept ? 'leaf' : 'muted', op: kept ? null : 0.6 }));
    }));
    kids.push(Ln(mx, 24, mx, 128, 'acc', 2, '4 3'), P(`M${r2(mx - 5)},22 h10 l-5,7 z`, 'acc', { fill: 'acc' }));
    kids.push(T(mx, 36, moved ? c.moved : c.proposed, { fs: 10, a: mx > 200 ? 'end' : 'middle', c: 'acc', w: 600 }));
    kids.push(Rc(10, 160, 282, 22, 'hatch', { rx: 3, s: 'acc', da: '3 2' }),
      T(18, 175, `${c.lane}${st.uncertain.length ? ` : ${st.uncertain.map(name).join(', ')}` : ''}`, { fs: 10.5, c: 'acc' }));
    const label = c.aria(name(ms[afterIdx] ? ms[afterIdx].label : ''), st.kept.map(name).join(', '),
      st.dropped.map(name).join(', ') || c.none, st.uncertain.map(name).join(', ') || c.none);
    return box(300, 190, label, kids, { 'data-timeline-svg': String(pos) });
  }

  function timelineLists(ctx, d, pos) {
    const c = C().timeline;
    const st = timelineState(d, pos);
    const names = l => l.map(x => colName(ctx, x)).join(', ');
    const n = v => ctx.format.number(v, 'int');
    return el('div', { className: 'sc-tl-lists', 'aria-live': 'polite' }, [
      el('span', { className: 'sc-k', 'data-kept': st.kept.join(',') }, [el('b', { text: c.keptHead(n(st.kept.length)) }), ` ${names(st.kept)}`]),
      el('span', { className: 'sc-x', 'data-dropped': st.dropped.join(',') }, [el('b', { text: c.droppedHead(n(st.dropped.length)) }),
        ` ${names(st.dropped) || c.none}`]),
      st.uncertain.length ? el('span', { className: 'sc-u', 'data-uncertain': st.uncertain.join(',') }, [el('b', { text: c.uncertainHead(n(st.uncertain.length)) }),
        ` ${names(st.uncertain)}${c.whatever}`]) : null,
    ]);
  }

  /** PA-6: the timeline, with its display-only slider when `slider` is true. */
  function momentTimeline(ctx, q, d, interactive = true) {
    const c = C().timeline;
    const ms = arr(d.milestones);
    const positions = arr(d.positions);
    const home = Math.max(0, positions.findIndex(p => p.after === d.moment_after));
    const stops = positions.length ? positions.length : 0;
    const wrap = el('div', { className: 'sc-tl', 'data-timeline': q ? q.id : 'board' });
    if (!interactive || !d.slider || stops < 2) {
      wrap.appendChild(timelineSvg(ctx, d, home, false));
      if (interactive) wrap.appendChild(timelineLists(ctx, d, home));
      return wrap;
    }
    const labelOf = i => {
      const after = ms.find(m => m.id === positions[i].after);
      return c.afterMilestone(after ? after.label : positions[i].after);
    };
    const svgBox = el('div', { className: 'sc-tl-svg' }, [timelineSvg(ctx, d, home, false)]);
    const lists = el('div', { className: 'sc-tl-l' }, [timelineLists(ctx, d, home)]);
    const id = `sc-tl-${String(q.id).replace(/[^a-z0-9]/gi, '-')}`;
    const input = el('input', { type: 'range', id, min: '0', max: String(stops - 1), step: '1', value: String(home),
      'data-timeline-slider': true, 'aria-valuetext': labelOf(home),
      // Display only (PA-6): nothing is sent, nothing is recorded; the position is not kept.
      oninput: ev => {
        const pos = Number(ev.target.value);
        svgBox.replaceChildren(timelineSvg(ctx, d, pos, pos !== home));
        lists.replaceChildren(timelineLists(ctx, d, pos));
        ev.target.setAttribute('aria-valuetext', labelOf(pos));
      } });
    wrap.append(svgBox, el('label', { className: 'sr-only', for: id, text: c.sliderLabel }), input,
      el('div', { className: 'sc-tl-stops', 'aria-hidden': 'true' }, positions.map((_, i) => el('span', { text: labelOf(i) }))),
      lists, el('p', { className: 'sc-only', 'data-display-only': true, text: c.only }));
    return wrap;
  }

  /** PA-7: kept / excluded / not a variable, grouped by the case's groups, then the timeline. */
  function variablesBoard(ctx, q, d) {
    const c = C().board;
    const groups = [];
    for (const col of arr(d.columns)) {
      let g = groups.find(x => x.name === col.group);
      if (!g) groups.push(g = { name: col.group, cols: [] });
      g.cols.push(col);
    }
    const sign = { kept: '✓', excluded: '✕', not_feature: '—' };
    const word = { kept: c.kept, excluded: c.excluded, not_feature: c.notFeature };
    const out = [el('div', { className: 'sc-vb', 'data-variables-board': true }, groups.map(g => el('div', { className: 'sc-vb-g' }, [
      g.name ? el('div', { className: 'sc-vb-gn', text: g.name }) : null,
      el('div', { className: 'sc-vb-cs' }, g.cols.map(col => el('span', { className: `sc-vchip sc-vchip-${col.state}`, 'data-column': col.column,
        'data-state': col.state }, [
        el('span', { text: `${sign[col.state] || '·'} ${col.name || colName(ctx, col.column)}` }),
        el('small', { text: col.reason ? `${word[col.state] || ''} : ${col.reason}` : word[col.state] || '' }),
      ])))]))),
    note(c.legend)];
    if (arr(d.milestones).length) {
      out.push(el('p', { className: 'sc-cap sc-cap-b', text: c.onTimeline }), momentTimeline(ctx, null, d, false));
    }
    return out;
  }

  /** PA-8 (R63): one column per stratum, development and sealed counts written. */
  function partitionStrata(ctx, q, d) {
    const c = C().strata;
    const n = v => ctx.format.number(v, 'int');
    const strata = arr(d.strata);
    const kids = [Rc(0, 4, 12, 10, 'grey'), T(16, 13, c.development(n(d.development)), { fs: 10.5, c: 'ink' }),
      Rc(150, 4, 12, 10, 'cseal'), T(166, 13, `${c.sealed(n(d.sealed))}${d.opened ? c.opened : ''}`, { fs: 10.5, c: 'ink' })];
    if (!strata.length) {
      // No counts by stratum (an older study, or a binary one): the strip only, and why.
      const total = (d.development || 0) + (d.sealed || 0) || 1;
      const wd = (d.development / total) * 290;
      kids.push(Rc(0, 30, wd, 26, 'grey', { rx: 2 }), T(wd / 2, 47, n(d.development), { fs: 11, a: 'middle', c: 'ink', w: 600 }),
        Rc(wd + 2, 30, 288 - wd, 26, 'cseal', { rx: 2, s: d.opened ? 'ink' : null, sw: d.opened ? 1.5 : null }),
        T(wd + 2 + (288 - wd) / 2, 47, n(d.sealed), { fs: 11, a: 'middle', c: 'onseal', w: 600 }));
      return [box(300, 64, c.aria(n(d.sealed), n(d.development)), kids, { 'data-strata': 'none' }), note(c.recorded)];
    }
    const max = Math.max(...strata.map(s => (s.development || 0) + (s.sealed || 0)), 1);
    const scale = 120 / max;
    const w = Math.min(40, 260 / strata.length - 10);
    strata.forEach((s, i) => {
      const x = 22 + i * (260 / strata.length);
      const base = 158;
      const hd = (s.development || 0) * scale;
      const hs = (s.sealed || 0) * scale;
      kids.push(Rc(x, base - hd, w, hd, 'grey', { mark: 'development' }), T(x + w / 2, base - hd / 2 + 4, n(s.development), { fs: 11, a: 'middle', c: 'ink', w: 600 }));
      kids.push(Rc(x, base - hd - hs - 2, w, hs, 'cseal', { s: d.opened ? 'ink' : null, sw: d.opened ? 1.5 : null, mark: 'sealed' }),
        T(x + w / 2, base - hd - hs / 2 + 2, n(s.sealed), { fs: 11, a: 'middle', c: 'onseal', w: 600 }));
      kids.push(T(x + w / 2, 172, n(s.stratum), { fs: 11, a: 'middle' }));
    });
    kids.push(T(150, 188, c.axis, { fs: 10.5, a: 'middle' }));
    return [box(300, 194, c.aria(n(d.sealed), n(d.development)), kids, { 'data-strata': String(strata.length) })];
  }

  /** PA-8 (R59): the k rounds of the cross-validation, with its legend and the sealed rows aside. */
  function foldsChart(ctx, q, d) {
    const c = C().folds;
    const n = v => ctx.format.number(v, 'int');
    const k = ok(d.k) ? d.k : arr(d.blocks).length || 5;
    const blocks = arr(d.blocks);
    const W = 200 / k;
    const year = v => (ok(v) ? ctx.format.number(v, 'auto') : '');
    const kids = [hatch(), T(46, 11, c.title(d.order_column || ''), { fs: 10.5, c: 'ink', w: 600 })];
    if (blocks.length) {
      blocks.forEach((b, j) => {
        const x = 46 + j * W;
        kids.push(T(x + W / 2 - 1, 26, ok(b.min) && ok(b.max) ? `${year(b.min)}–${year(b.max)}` : '', { fs: 9.5, a: 'middle' }));
        kids.push(T(x + W / 2 - 1, 38, c.rows(n(b.n_rows)), { fs: 9.5, a: 'middle' }));
      });
    }
    for (let i = 0; i < k; i++) {
      const y = 46 + i * 24;
      kids.push(T(0, y + 14, c.round(n(i + 1)), { fs: 10.5, c: 'ink' }));
      for (let j = 0; j < k; j++) {
        const x = 46 + j * W;
        kids.push(Rc(x, y, W - 2, 19, i === j ? 'ochre' : 'grey', { rx: 2, mark: i === j ? 'validation' : 'training' }));
        if (i === j && W > 34) kids.push(T(x + W / 2 - 1, y + 13.5, c.predicted, { fs: 8.5, a: 'middle', c: 'ink', w: 600 }));
      }
    }
    const h = 46 + k * 24;
    if (ok(d.sealed)) {
      kids.push(Rc(252, 46, 46, h - 52, 'sealtint', { rx: 3, s: 'cseal', da: '4 2' }),
        T(275, 46 + (h - 52) / 2 - 14, n(d.sealed), { fs: 12, a: 'middle', c: 'cseal', w: 700 }),
        T(275, 46 + (h - 52) / 2, c.sealedWord, { fs: 9, a: 'middle', c: 'cseal' }),
        T(275, 46 + (h - 52) / 2 + 12, c.never, { fs: 9, a: 'middle', c: 'cseal' }),
        T(275, 46 + (h - 52) / 2 + 24, c.used, { fs: 9, a: 'middle', c: 'cseal' }));
    }
    kids.push(Rc(0, h + 6, 14, 11, 'ochre'), T(19, h + 15, c.validation, { fs: 10.5, c: 'ink' }));
    kids.push(Rc(0, h + 23, 14, 11, 'grey'), T(19, h + 32, c.training, { fs: 10.5, c: 'ink' }));
    const label = c.aria(n(k), n(d.n_rows), d.order_column || '', ok(d.sealed) ? n(d.sealed) : '');
    return [box(300, h + 38, label, kids, { 'data-folds': blocks.length ? 'computed' : 'illustrative', 'data-legend': '2' }),
      el('p', { className: 'sc-after', text: c.arrow }),
      d.illustrative ? note(c.illustrative) : null];
  }

  /** PA-9 (R60): the made-up errors, their squares, MAE and RMSE as marks. */
  function metricBars(ctx, q, d) {
    const c = C().metric;
    const e = arr(d.errors).filter(ok);
    const sq = arr(d.squares).filter(ok);
    if (!e.length) return [unavailable()];
    const unit = d.unit || '';
    const f = v => ctx.format.number(v, Number.isInteger(v) ? 'int' : 'f2');
    const kids = [T(0, 14, c.errors(ctx.format.number(e.length, 'int'), unit), { fs: 10.5, c: 'ink', w: 600 }),
      T(160, 14, c.squared, { fs: 10.5, c: 'ink', w: 600 })];
    const base = 140;
    const me = Math.max(...e, 1);
    const ms = Math.max(...sq, 1);
    kids.push(Ln(4, base, 140, base), Ln(160, base, 296, base));
    const bw = Math.min(18, 120 / e.length - 6);
    e.forEach((v, i) => {
      const x = 12 + i * (128 / e.length);
      const h = (v / me) * 95;
      kids.push(Rc(x, base - h, bw, h, 'pen', { op: 0.8, mark: 'error' }), T(x + bw / 2, base - h - 4, f(v), { fs: 11, a: 'middle', c: 'ink' }));
    });
    sq.forEach((v, i) => {
      const x = 168 + i * (128 / sq.length);
      const h = (v / ms) * 95;
      kids.push(Rc(x, base - h, bw, h, 'orange', { op: 0.75, mark: 'square' }), T(x + bw / 2, base - h - 4, f(v), { fs: 11, a: 'middle', c: 'ink' }));
    });
    if (ok(d.mae)) {
      const y = base - (d.mae / me) * 95;
      kids.push(Ln(4, y, 140, y, 'leaf', 1.8, '5 3'), T(4, y - 6, c.mean(f(d.mae)), { fs: 10.5, c: 'leaf', w: 600 }));
    }
    if (ok(d.mean_square)) {
      const y = base - (d.mean_square / ms) * 95;
      kids.push(Ln(160, y, 296, y, 'leaf', 1.8, '5 3'), T(232, y - 5, c.mean(f(d.mean_square)), { fs: 10.5, a: 'middle', c: 'leaf', w: 600 }));
    }
    const maeText = ok(d.mae) ? f(d.mae) : '';
    const rmseText = ok(d.rmse) ? ctx.format.number(d.rmse, 'f2') : '';
    kids.push(T(0, 160, c.mae(maeText, unit), { fs: 11, c: 'ink', w: 600, }), T(160, 160, c.rmse(ok(d.mean_square) ? f(d.mean_square) : '', rmseText, unit), { fs: 11, c: 'ink', w: 600 }));
    kids.push(T(0, 178, c.madeUp, { fs: 10.5, c: 'acc', st: 'italic', w: 600 }));
    const out = [box(300, 184, c.aria(e.map(f).join(', '), maeText, rmseText), kids, { 'data-metric-bars': true, 'data-mae': maeText, 'data-rmse': rmseText })];
    if (d.unit_note) out.push(el('p', { className: 'sc-after', 'data-unit-note': true, text: d.unit_note }));
    return out;
  }

  /** Horizontal bars of `chart_data.bars` (the criterion's made-up example, R67), or a result's shares. */
  function barsFromData(ctx, d) {
    const c = C().bars;
    const bars = arr(d.bars).filter(b => b && ok(b.value));
    if (!bars.length) return null;
    const max = Math.max(...bars.map(b => b.value)) * 1.15 || 1;
    const X = v => 110 + (v / max) * 150;
    const kids = [];
    const tk = ticks(0, max, 4);
    tk.list.forEach(t => kids.push(Ln(X(t), 8, X(t), 10 + bars.length * 27, 'grid'), T(X(t), 24 + bars.length * 27, ctx.format.number(t, 'auto'), { fs: 10.5, a: 'middle' })));
    const tone = ['grey', 'acc', 'orange', 'leaf', 'pen'];
    bars.forEach((b, i) => {
      const y = 10 + i * 27;
      kids.push(T(104, y + 9, b.label || '', { fs: 11, a: 'end', c: 'ink', w: 600 }), T(104, y + 21, b.note || '', { fs: 9.5, a: 'end' }),
        Rc(X(0), y + 2, X(b.value) - X(0), 16, b.tone && tone.includes(b.tone) ? b.tone : tone[i % tone.length], { op: 0.8, mark: b.id || 'bar' }),
        T(X(b.value) + 4, y + 14, `${ctx.format.number(b.value, b.fmt || 'f1')}${d.unit ? ` ${d.unit}` : ''}`, { fs: 10.5, c: 'ink' }));
    });
    if (d.axis_label) kids.push(T(180, 40 + bars.length * 27, d.axis_label, { fs: 10, a: 'middle', st: 'italic' }));
    return [box(300, 46 + bars.length * 27, d.label || c.aria, kids, { 'data-bars': String(bars.length) })];
  }

  // --- block 3 charts read from registered results ------------------------------------------

  function sampleTable(ctx, q) {
    const c = C().sample;
    if (ctx.want) ctx.want('data');
    const d = ctx.data('data');
    const m = d && d.model;
    if (!m) return [unavailable('reading')];
    const cols = arr(m.rows.columns);
    const target = m.target.column;
    const order = [target, ...cols.filter(x => x !== target)].filter(x => cols.includes(x));
    const n = v => ctx.format.number(v, 'int');
    const head = el('tr', {}, [el('th', { scope: 'col', text: c.row }), ...order.map(col => el('th', { scope: 'col',
      className: col === target ? 'sc-tgt' : null, text: col === target ? c.targetHead(colName(ctx, col)) : colName(ctx, col) }))]);
    const rows = arr(m.rows.items).map(r => el('tr', {}, [el('td', { className: 'sc-key', text: r.rowKey }),
      ...order.map(col => {
        const v = r.cells[cols.indexOf(col)];
        return el('td', { className: `${col === target ? 'sc-tgt ' : ''}${v === '?' ? 'sc-q' : ''}`.trim() || null, text: v === null ? '' : v });
      })]));
    return [el('p', { className: 'sc-cap sc-cap-b', 'data-raw-values': true },
      [el('b', { text: c.caption(n(arr(m.rows.items).length), n(m.development.rows)) }), ` · ${c.raw}`]),
    el('div', { className: 'sc-scrollx', tabindex: '0', role: 'region', 'aria-label': c.region }, [
      el('table', { className: 'sc-mini sc-sample' }, [el('thead', {}, [head]), el('tbody', {}, rows)])]),
    note(c.scroll)];
  }

  /** §8.10: the column dictionary and the "?" rows of step 1, as folds under the sample. */
  function sampleFolds(ctx, fold, idBase) {
    const c = C().sample;
    const d = ctx.data('data');
    const m = d && d.model;
    if (!m) return [];
    const l = lang(ctx);
    const out = [];
    const vars = arr(m.groups).flatMap(g => g.variables);
    if (vars.length) {
      out.push(fold(`${idBase}-dict`, c.dictionary(ctx.format.number(vars.length, 'int')), () => el('div', { className: 'sc-scrollx' }, [el('table', { className: 'sc-mini' }, [
        el('tr', {}, [el('th', { text: c.shown }), el('th', { text: c.inFile }), el('th', { text: c.meaning }), el('th', { className: 'sc-n', text: c.missing })]),
        ...vars.map(v => el('tr', { 'data-dictionary': v.name }, [el('td', { text: colName(ctx, v.name) }), el('td', { text: v.name }),
          el('td', { text: (l === 'fr' && v.descriptionFr) || v.description }), el('td', { className: 'sc-n', text: v.nMissing === null ? '' : ctx.format.number(v.nMissing, 'int') })]))])])));
    }
    const sr = m.specialRows;
    if (sr && sr.nRows > 0) {
      out.push(fold(`${idBase}-q`, c.questionRows(ctx.format.number(sr.nRows, 'int')), () => {
        const cols = arr(sr.columns);
        return el('div', {}, [el('div', { className: 'sc-scrollx', tabindex: '0', role: 'region', 'aria-label': c.questionRegion }, [
          el('table', { className: 'sc-mini sc-sample' }, [
            el('tr', {}, [el('th', { text: c.row }), ...cols.map(col => el('th', { text: colName(ctx, col) }))]),
            ...arr(sr.items).map(r => el('tr', {}, [el('td', { className: 'sc-key', text: r.rowKey }),
              ...arr(r.cells).map(v => el('td', { className: v === '?' ? 'sc-q' : null, text: v === null ? '' : v }))]))])]),
        note(c.withoutTarget)]);
      }));
    }
    return out;
  }

  function structureBars(ctx, q) {
    const c = C().structure;
    const snap = ctx.snapshot || {};
    const ds = snap.dataStructure;
    const ft = snap.finalTest;
    if (!ds) return [unavailable()];
    const dev = ft && ok(ft.developmentRows) ? ft.developmentRows : null;
    const g = arr(ds.groups)[0] || null;
    const rows = [[c.development, dev, 'pen'], g ? [c.distinct(colName(ctx, g.column)), g.groups, 'pen'] : null,
      g ? [c.repeated, g.rowsInRepeatedGroups, 'orange'] : null, [c.duplicates, ds.duplicates.rows, 'pen']].filter(r => r && ok(r[1]));
    const max = Math.max(...rows.map(r => r[1]), 1);
    const kids = [];
    rows.forEach(([label, v, tone], i) => {
      const y = 18 + i * 36;
      const w = (v / max) * 230;
      kids.push(T(0, y, label, { fs: 11, c: 'ink' }), Rc(0, y + 5, Math.max(w, 1.5), 13, tone, { op: 0.75 }),
        T(w + 5, y + 16, ctx.format.number(v, 'int'), { fs: 11, c: 'ink', w: 600 }));
    });
    return [box(300, 18 + rows.length * 36, c.aria, kids, { 'data-structure-bars': String(rows.length) })];
  }

  function missingBars(ctx, q) {
    const c = C().bars;
    const v = valuesOf(ctx, q.resultId, q.source.slot || 'eda.quality');
    if (!v) return [unavailable('reading')];
    const rows = arr(v.missing).filter(m => ok(m.share)).sort((a, b) => b.share - a.share).slice(0, 8);
    const max = Math.max(...rows.map(r => r.share), 0.01) * 1.25;
    const X = s => 84 + (s / max) * 170;
    const rid = q.resultId || idOf(ctx, 'eda.quality');
    const kids = [Ln(X(0), 6, X(0), 10 + rows.length * 22, 'muted')];
    rows.forEach((r, i) => {
      const y = 10 + i * 22;
      kids.push(T(78, y + 11, colName(ctx, r.column), { fs: 11, a: 'end', c: 'ink' }), Rc(X(0), y, Math.max(X(r.share) - X(0), 1.5), 14, r.share > 0 ? 'orange' : 'grey'),
        T(X(r.share) + 5, y + 11, r.share > 0 ? `${ctx.format.number(r.share, 'pct1')} (${ctx.format.number(r.n_missing, 'int')})` : '0', { fs: 11, c: 'ink' }));
    });
    return [box(300, 18 + rows.length * 22, c.missingAria, kids, { 'data-missing-bars': rid || '' })];
  }

  function verdictsTable(ctx, q, which = 'all') {
    const c = C().verdicts;
    const qv = ctx.snapshot && ctx.snapshot.qualityVerdicts;
    if (!qv || !arr(qv.columns).length) return [unavailable()];
    let cols = arr(qv.columns);
    if (which === 'unchanged') cols = cols.filter(x => !x.changed);
    cols = [...cols].sort((a, b) => Number(b.changed) - Number(a.changed));
    const rows = [];
    for (const col of cols) {
      for (const k of arr(col.checks)) {
        rows.push(el('tr', { className: col.changed ? 'sc-chosen' : null, 'data-verdict-column': col.column }, [
          el('td', { text: colName(ctx, col.column) }), el('td', { text: c.rules[k.rule] || k.rule }),
          el('td', { className: 'sc-n' }, [cite(ctx, ok(k.value) ? ctx.format.number(k.value, 'auto') : '', qv.resultId, k.path, k.value), ' · ',
            ok(k.threshold) ? ctx.format.number(k.threshold, 'auto') : '']),
          el('td', {}, [el('span', { className: `sc-chip ${k.exceeds ? 'sc-chip-over' : 'sc-chip-under'}`, text: which === 'unchanged' ? c.noChange : k.exceeds ? c.over : c.under })]),
        ]));
      }
    }
    return [el('div', { className: 'sc-scrollx', role: 'region', tabindex: '0', 'aria-label': c.region }, [el('table', { className: 'sc-mini', 'data-verdicts-table': which }, [
      el('tr', {}, [el('th', { text: c.column }), el('th', { text: c.check }), el('th', { className: 'sc-n', text: c.valueBound }), el('th', { text: c.verdict })]),
      ...rows])])];
  }

  function histogramOf(ctx, values, rid, path, label, tone = 'pen', xAt = null, w = 300, x0 = 30) {
    const bins = arr(values.bins).filter(b => ok(b.low) && ok(b.high) && ok(b.n_rows));
    if (!bins.length) return null;
    const lo = bins[0].low;
    const hi = bins[bins.length - 1].high;
    const width = w - x0 - 10;
    const X = v => x0 + ((v - lo) / (hi - lo || 1)) * width;
    const max = Math.max(...bins.map(b => b.n_rows), 1);
    const kids = bins.map(b => Rc(X(b.low), 115 - (b.n_rows / max) * 100, Math.max(1, X(b.high) - X(b.low) - 1.5), (b.n_rows / max) * 100, tone, { op: 0.75 }));
    kids.push(Ln(x0, 115, x0 + width, 115));
    ticks(lo, hi, 4).list.forEach(t => kids.push(T(X(t), 130, ctx.format.number(t, 'auto'), { a: 'middle' })));
    if (xAt) kids.push(T(x0 + width / 2, 146, xAt, { a: 'middle' }));
    return box(w, 150, label, kids, { 'data-histogram': rid || '' });
  }

  /** The target's summary (no bins are registered): its range, quartiles and median on one scale. */
  function targetSummary(ctx, q) {
    const c = C().summary;
    const v = valuesOf(ctx, q.resultId, q.source.slot || 'eda.target_summary');
    if (!v) return [unavailable('reading')];
    if (arr(v.bins).length) return [histogramOf(ctx, v, q.resultId, 'bins', c.aria, 'pen', v.unit || '')];
    const rid = q.resultId || idOf(ctx, 'eda.target_summary');
    const keys = ['min', 'q25', 'median', 'q75', 'max'];
    if (!keys.every(k => ok(v[k]))) return [unavailable()];
    const X = x => 20 + ((x - v.min) / (v.max - v.min || 1)) * 260;
    const kids = [Ln(X(v.min), 50, X(v.max), 50, 'muted', 1.5), Rc(X(v.q25), 34, X(v.q75) - X(v.q25), 32, 'pentint', { s: 'pen', sw: 1.4 }),
      Ln(X(v.median), 28, X(v.median), 72, 'acc', 2.2), Ln(X(v.min), 42, X(v.min), 58, 'muted', 1.5), Ln(X(v.max), 42, X(v.max), 58, 'muted', 1.5)];
    keys.forEach((k, i) => kids.push(T(X(v[k]), i % 2 ? 90 : 20, `${c[k]} ${ctx.format.number(v[k], 'auto')}`, { fs: 10, a: i === 0 ? 'start' : i === 4 ? 'end' : 'middle', c: k === 'median' ? 'acc' : 'ink' })));
    kids.push(T(150, 108, c.axis(v.target || '', v.unit || '', ctx.format.number(v.n_rows || v.n || 0, 'int')), { fs: 10.5, a: 'middle' }));
    return [box(300, 114, c.aria, kids, { 'data-target-summary': rid || '' })];
  }

  /** The target's mean by bins of a column, with its intervals and the overall mean. */
  function trendByBins(ctx, q, slot = null) {
    const c = C().trend;
    const s = slot || q.source.slot;
    const v = valuesOf(ctx, slot ? null : q.resultId, s);
    if (!v) return [unavailable('reading')];
    const g = arr(v.groups).filter(x => ok(x.mean));
    if (!g.length) return [unavailable()];
    const lows = g.map(x => (x.interval && ok(x.interval.low) ? x.interval.low : x.mean));
    const highs = g.map(x => (x.interval && ok(x.interval.high) ? x.interval.high : x.mean));
    const lo = Math.min(...lows, ok(v.overall_mean) ? v.overall_mean : Infinity);
    const hi = Math.max(...highs, ok(v.overall_mean) ? v.overall_mean : -Infinity);
    const tk = ticks(lo, hi, 4);
    const y0 = tk.list[0] <= lo ? tk.list[0] : lo;
    const y1 = tk.list[tk.list.length - 1] >= hi ? tk.list[tk.list.length - 1] : hi;
    const Y = x => 130 - ((x - y0) / (y1 - y0 || 1)) * 112;
    const X = i => 46 + ((i + 0.5) * 244) / g.length;
    const kids = [Ln(40, 130, 292, 130), Ln(40, 14, 40, 130)];
    tk.list.forEach(t => kids.push(T(36, Y(t) + 4, ctx.format.number(t, 'auto'), { a: 'end' }), Ln(40, Y(t), 292, Y(t), 'grid')));
    if (ok(v.overall_mean)) kids.push(Ln(40, Y(v.overall_mean), 292, Y(v.overall_mean), 'muted', 1.2, '4 3'), T(290, Y(v.overall_mean) - 4, c.overall, { fs: 9.5, a: 'end' }));
    let d = '';
    g.forEach((x, i) => {
      kids.push(Ln(X(i), Y(lows[i]), X(i), Y(highs[i]), 'ink', 1.4), Ci(X(i), Y(x.mean), 3.6, 'ink'));
      d += `${d ? 'L' : 'M'}${r2(X(i))},${r2(Y(x.mean))}`;
      kids.push(T(X(i), 144, String(i + 1), { fs: 9.5, a: 'middle' }));
    });
    kids.push(P(d, 'orange', { w: 2.2 }), T(44, 11, `${v.target || ''}${v.unit && v.unit !== v.target ? ` (${v.unit})` : ''}`, { c: 'ink' }));
    kids.push(T(166, 158, c.axis(colName(ctx, v.column || ''), v.binned ? ctx.format.number(g.length, 'int') : ''), { a: 'middle' }));
    const out = [box(300, 162, c.aria(colName(ctx, v.column || '')), kids, { 'data-trend': s })];
    out.push(el('ol', { className: 'sc-binlist' }, g.map((x, i) => el('li', {}, [`${i + 1} · ${x.value} · `,
      cite(ctx, ctx.format.number(x.mean, 'f2'), q.resultId || idOf(ctx, s), `groups.${i}.mean`, x.mean)]))));
    return out;
  }

  /** The predictor correlation matrix, with the case's short names (ST-12). */
  function correlation(ctx, q) {
    const c = C().corr;
    const v = valuesOf(ctx, q.resultId, q.source.slot || 'eda.correlation');
    if (!v) return [unavailable('reading')];
    const names = arr(v.columns).filter(x => x.kind === 'numeric').map(x => x.name);
    const pair = (a, b) => arr(v.pairs).find(p => (p.a === a && p.b === b) || (p.a === b && p.b === a));
    const n = names.length;
    if (n < 2) return [unavailable()];
    const cell = Math.min(40, 220 / n);
    const x0 = 78;
    const y0 = 64;
    const kids = [];
    names.forEach((a, i) => {
      kids.push(T(x0 - 6, y0 + i * cell + cell / 2 + 4, colName(ctx, a), { fs: 10, a: 'end', c: 'ink' }));
      const cx = x0 + i * cell + cell / 2;
      kids.push(T(cx, y0 - 6, colName(ctx, a), { fs: 10, c: 'ink', tr: `rotate(-35 ${r2(cx)} ${y0 - 6})` }));
      names.forEach((b, j) => {
        const p = i === j ? { value: 1 } : pair(a, b);
        const x = p && ok(p.value) ? p.value : null;
        const ax = x === null ? 0 : Math.abs(x);
        kids.push(Rc(x0 + j * cell, y0 + i * cell, cell - 2, cell - 2, x === null ? 'grid' : x > 0 ? 'pen' : 'orange', { op: (0.12 + ax * 0.75).toFixed(2) }));
        if (x !== null) kids.push(T(x0 + j * cell + cell / 2 - 1, y0 + i * cell + cell / 2 + 4, i === j ? '1' : ctx.format.number(x, 'f2'), { fs: 9.5, a: 'middle', c: ax > 0.6 ? 'white' : 'ink' }));
      });
    });
    return [box(300, y0 + n * cell + 6, c.aria, kids, { 'data-correlation': String(n) })];
  }

  /** Per-fold errors of the reference and the linear model, mean marked (models.beat). */
  function modelDots(ctx, q) {
    const c = C().dots;
    const fits = ['fit.baseline', 'fit.linear'];
    const metric = metricOf(ctx);
    const rows = fits.map(slot => {
      const v = valuesOf(ctx, null, slot);
      const cv = v && v.cross_validation;
      if (!cv) return null;
      const pf = arr(cv.per_fold).map(f => f[metric]).filter(ok);
      const sp = cv.spread && cv.spread[metric];
      return { slot, label: mname(ctx, slot), perFold: pf, mean: sp && ok(sp.mean) ? sp.mean : null, rid: idOf(ctx, slot) };
    }).filter(Boolean);
    if (!rows.length) return [unavailable('reading')];
    const all = rows.flatMap(r => r.perFold);
    const lo = Math.floor(Math.min(...all));
    const hi = Math.ceil(Math.max(...all));
    const X = v => 86 + ((v - lo) / (hi - lo || 1)) * 200;
    const kids = [];
    ticks(lo, hi, 5).list.forEach(t => kids.push(Ln(X(t), 14, X(t), 18 + rows.length * 42, 'grid'), T(X(t), 30 + rows.length * 42, ctx.format.number(t, 'auto'), { a: 'middle' })));
    rows.forEach((r, i) => {
      const y = 38 + i * 42;
      kids.push(T(78, y + 4, r.label, { fs: 11.5, a: 'end', c: 'ink' }));
      r.perFold.forEach(v => kids.push(Ci(X(v), y - 8, 3, 'none', { s: 'muted', sw: 1.3, mark: 'fold' })));
      if (ok(r.mean)) kids.push(Ci(X(r.mean), y + 6, 4.5, 'ink', { mark: 'mean' }), T(X(r.mean), y + 22, ctx.format.number(r.mean, 'f2'), { fs: 10.5, a: 'middle', c: 'ink', w: 600 }));
    });
    const yb = 46 + rows.length * 42;
    kids.push(T(160, yb, c.axis(C().measures[metric] || metric), { a: 'middle' }),
      Ci(6, yb + 14, 3, 'none', { s: 'muted', sw: 1.3 }), T(13, yb + 18, c.fold, { fs: 10.5 }), Ci(140, yb + 14, 4, 'ink'), T(148, yb + 18, c.mean, { fs: 10.5 }));
    return [box(300, yb + 24, c.aria, kids, { 'data-model-dots': String(rows.length) })];
  }

  function metricOf(ctx) {
    const snap = ctx.snapshot || {};
    const em = snap.decisions && snap.decisions.error_metric;
    let m = null;
    try { m = em && em.value ? (typeof em.value === 'string' ? JSON.parse(em.value) : em.value).metric : null; } catch (_) { m = null; }
    if (m === 'rmse' || m === 'mae') return m;
    const cc = snap.criterionConfigurations;
    return cc && cc.metric === 'rmse_reduction' ? 'rmse' : 'mae';
  }

  /** PA-10 (R62): a square plot, the same range and ticks on both axes, the diagonal y = x. */
  function observedPredicted(ctx, q) {
    const c = C().obsPred;
    const slot = q.source.slot || 'diag.regression';
    const v = valuesOf(ctx, q.resultId, slot);
    if (!v) return [unavailable('reading')];
    const models = obj(v.models);
    const fit = models['fit.linear'] ? 'fit.linear' : Object.keys(models)[0];
    const sc = fit ? models[fit].scatter : null;
    const pts = sc ? arr(sc.points).filter(p => ok(p.prediction) && ok(p.observed)) : [];
    if (!pts.length) return [unavailable()];
    const unit = v.unit || '';
    let lo;
    let hi;
    if (sc.axis && ok(sc.axis.min) && ok(sc.axis.max)) { lo = sc.axis.min; hi = sc.axis.max; } else {
      // The common range of observed and predicted values, rounded outward (PA-10, §8 cut of EN-15).
      const all = pts.flatMap(p => [p.prediction, p.observed]);
      const tk0 = ticks(Math.min(...all), Math.max(...all), 4);
      lo = Math.floor(Math.min(...all) / tk0.step) * tk0.step;
      hi = Math.ceil(Math.max(...all) / tk0.step) * tk0.step;
    }
    const P0 = 46;
    const PS = 228;
    const X = x => P0 + ((x - lo) / (hi - lo || 1)) * PS;
    const Y = y => 12 + PS - ((y - lo) / (hi - lo || 1)) * PS;
    const tk = ticks(lo, hi, 4).list;
    const kids = [Rc(P0, 12, PS, PS, 'plot', { s: 'grid' })];
    tk.forEach(t => kids.push(Ln(X(t), 12, X(t), 12 + PS, 'grid'), Ln(P0, Y(t), P0 + PS, Y(t), 'grid'),
      T(X(t), 12 + PS + 14, ctx.format.number(t, 'auto'), { a: 'middle' }), T(P0 - 5, Y(t) + 4, ctx.format.number(t, 'auto'), { a: 'end' })));
    const dm = lo + (hi - lo) * 0.7;
    kids.push(Ln(X(lo), Y(lo), X(hi), Y(hi), 'leaf', 1.6, '5 3'),
      T(X(dm), Y(dm) - 6, c.perfect, { fs: 10.5, c: 'leaf', tr: `rotate(-45 ${r2(X(dm))} ${r2(Y(dm) - 6)})` }));
    const final = slot === 'diag.final_test';
    pts.forEach(p => kids.push(Ci(X(p.prediction), Y(p.observed), pts.length > 100 ? 2.2 : 2.8, final ? 'pen' : 'ink', { op: final ? 0.75 : 0.5 })));
    kids.push(T(P0, 8, c.y(unit), { fs: 10.5, c: 'ink' }), T(P0 + PS, 12 + PS + 30, c.x(unit), { fs: 10.5, a: 'end', c: 'ink' }));
    const fmt0 = x => ctx.format.number(x, 'auto');
    const out = [box(300, 12 + PS + 36, c.aria(mname(ctx, fit), fmt0(lo), fmt0(hi)), kids,
      { 'data-observed-predicted': fit, 'data-x-domain': `${lo},${hi}`, 'data-y-domain': `${lo},${hi}` })];
    if (ok(sc.n_shown) && ok(sc.n_rows)) out.push(note(c.shown(ctx.format.number(sc.n_shown, 'int'), ctx.format.number(sc.n_rows, 'int'))));
    return out;
  }

  /** Residuals of the linear model along one column (variants.shape), zero line marked. */
  function residualByFeature(ctx, q) {
    const c = C().resid;
    const v = valuesOf(ctx, q.resultId, q.source.slot || 'diag.regression');
    if (!v) return [unavailable('reading')];
    const m = obj(obj(v.models)['fit.linear']);
    const feats = arr(m.by_feature).filter(f => arr(f.groups).length > 1);
    const want = q.chartData && q.chartData.column;
    const f = feats.find(x => x.column === want) || feats.find(x => x.column === 'horsepower') || feats.find(x => x.binned) || feats[0];
    if (!f) return [unavailable()];
    const g = arr(f.groups).filter(x => ok(x.mean_residual));
    const lim = Math.max(...g.map(x => Math.abs(x.mean_residual)), 0.5) * 1.2;
    const Y = e => 80 - (e / lim) * 62;
    const X = i => 46 + ((i + 0.5) * 244) / g.length;
    const kids = [Ln(40, Y(0), 292, Y(0), 'ink', 1.2), T(290, Y(0) - 4, c.zero, { a: 'end', c: 'ink', fs: 10 })];
    let d = '';
    g.forEach((x, i) => {
      kids.push(Ci(X(i), Y(x.mean_residual), 3.6, 'ink'), T(X(i), 160, String(i + 1), { fs: 9.5, a: 'middle' }));
      d += `${d ? 'L' : 'M'}${r2(X(i))},${r2(Y(x.mean_residual))}`;
    });
    kids.push(P(d, 'orange', { w: 2.2 }), T(40, 12, c.y(v.unit || ''), { c: 'ink' }), T(166, 174, colName(ctx, f.column), { a: 'middle' }));
    return [box(300, 178, c.aria(colName(ctx, f.column)), kids, { 'data-residual-feature': f.column })];
  }

  /** The mean bias per period (variants.period), sides labelled (PA-11). */
  function biasByPeriod(ctx, q) {
    const c = C().bias;
    let groups = q.chartData && arr(q.chartData.groups);
    let unit = q.chartData ? q.chartData.unit : '';
    if (!groups || !groups.length) {
      const v = valuesOf(ctx, q.resultId, q.source.slot || 'diag.regression');
      const bp = v && obj(obj(v.models)['fit.linear']).by_period;
      groups = bp ? arr(bp.groups) : [];
      unit = v ? v.unit : '';
    }
    groups = groups.filter(x => ok(x.mean_residual));
    if (!groups.length) return [unavailable()];
    const lim = Math.max(...groups.map(x => Math.abs(x.mean_residual)), 0.5) * 1.25;
    const X = e => 150 + (e / lim) * 120;
    const kids = [Ln(X(0), 10, X(0), 18 + groups.length * 22, 'ink', 1.2)];
    groups.forEach((x, i) => {
      const y = 22 + i * 22;
      kids.push(T(56, y + 4, x.label || x.value, { fs: 11, a: 'end', c: 'ink' }),
        Rc(Math.min(X(0), X(x.mean_residual)), y - 7, Math.abs(X(x.mean_residual) - X(0)), 14, x.mean_residual > 0 ? 'orange' : 'pen', { op: 0.85 }),
        T(x.mean_residual > 0 ? X(x.mean_residual) + 4 : X(x.mean_residual) - 4, y + 4, `${x.mean_residual > 0 ? '+' : ''}${ctx.format.number(x.mean_residual, 'f2')}`,
          { fs: 11, a: x.mean_residual > 0 ? 'start' : 'end', c: 'ink' }));
    });
    const yb = 34 + groups.length * 22;
    kids.push(T(150, yb, c.sides(unit || ''), { a: 'middle', fs: 10 }));
    return [box(300, yb + 6, c.aria, kids, { 'data-bias-period': String(groups.length) })];
  }

  function selectionOf(ctx, q) {
    const v = valuesOf(ctx, q.resultId, q.source.slot || 'evaluate.regression');
    const s = v && v.model_selection;
    return s && s.available ? { s, rid: q.resultId || idOf(ctx, 'evaluate.regression') } : null;
  }

  /** Paired differences with the candidate, ± one standard error (choice.best). */
  function pairedIntervals(ctx, q) {
    const c = C().paired;
    const sel = selectionOf(ctx, q);
    if (!sel) return [unavailable('reading')];
    const rows = arr(sel.s.configurations).filter(x => x.difference && ok(x.difference.mean));
    if (!rows.length) return [unavailable()];
    const lo = Math.min(...rows.map(x => x.difference.low), 0);
    const hi = Math.max(...rows.map(x => x.difference.high), 0);
    const pad = (hi - lo) * 0.15 || 0.1;
    const X = v => 110 + ((v - (lo - pad)) / (hi - lo + 2 * pad)) * 180;
    const kids = [T(X(lo - pad) + 2, 14, c.less, { fs: 10.5 }), T(X(hi + pad) - 2, 14, c.more, { fs: 10.5, a: 'end' })];
    ticks(lo - pad, hi + pad, 4).list.forEach(t => kids.push(Ln(X(t), 20, X(t), 24 + rows.length * 28, t === 0 ? 'ink' : 'grid', t === 0 ? 1.5 : 1),
      T(X(t), 38 + rows.length * 28, ctx.format.number(t, 'auto'), { a: 'middle' })));
    rows.forEach((x, i) => {
      const y = 36 + i * 28;
      const name = `${mname(ctx, x.slot)} − ${mname(ctx, x.difference.against)}`;
      kids.push(T(0, y + 4, name, { fs: 10.5, c: 'ink' }), Ln(X(x.difference.low), y, X(x.difference.high), y, 'muted', 2.2),
        Ln(X(x.difference.low), y - 5, X(x.difference.low), y + 5, 'muted', 2), Ln(X(x.difference.high), y - 5, X(x.difference.high), y + 5, 'muted', 2),
        Ci(X(x.difference.mean), y, 4.5, 'ink'), T(X(x.difference.mean), y - 8, ctx.format.number(x.difference.mean, 'f2'), { fs: 10, a: 'middle', c: 'ink', w: 600 }));
    });
    const yb = 52 + rows.length * 28;
    kids.push(T(150, yb, c.axis, { fs: 10.5, a: 'middle' }));
    return [box(300, yb + 6, c.aria, kids, { 'data-paired': String(rows.length) })];
  }

  /** Per-fold errors of every configuration (choice.best's other chart). */
  function perFoldDots(ctx, q) {
    const c = C().dots;
    const sel = selectionOf(ctx, q);
    if (!sel) return [unavailable('reading')];
    const rows = arr(sel.s.configurations).filter(x => arr(x.per_fold).length);
    const all = rows.flatMap(x => x.per_fold);
    const lo = Math.floor(Math.min(...all));
    const hi = Math.ceil(Math.max(...all));
    const X = v => 86 + ((v - lo) / (hi - lo || 1)) * 200;
    const kids = [];
    ticks(lo, hi, 5).list.forEach(t => kids.push(Ln(X(t), 10, X(t), 16 + rows.length * 30, 'grid'), T(X(t), 28 + rows.length * 30, ctx.format.number(t, 'auto'), { a: 'middle' })));
    rows.forEach((x, i) => {
      const y = 24 + i * 30;
      kids.push(T(78, y + 4, mname(ctx, x.slot), { fs: 11, a: 'end', c: 'ink' }));
      x.per_fold.forEach(v => kids.push(Ci(X(v), y, 3, 'none', { s: 'muted', sw: 1.3 })));
      if (ok(x.mean)) kids.push(Ci(X(x.mean), y, 4.5, 'ink'));
    });
    return [box(300, 40 + rows.length * 30, c.aria, kids, { 'data-per-fold': String(rows.length) })];
  }

  /** The one-standard-error rule with the study's values (choice.simplest). */
  function oneSeRule(ctx, q) {
    const c = C().oneSe;
    const sel = selectionOf(ctx, q);
    if (!sel) return [unavailable('reading')];
    const s = sel.s;
    const rows = arr(s.configurations).filter(x => ok(x.mean));
    const one = obj(s.one_se);
    const best = rows.find(x => x.slot === (one.best || s.best));
    const bound = ok(one.bound) ? one.bound : null;
    const vals = rows.map(x => x.mean).concat(bound === null ? [] : [bound]);
    const lo = Math.min(...vals) - 0.3;
    const hi = Math.max(...vals) + 0.3;
    const X = v => 92 + ((v - lo) / (hi - lo || 1)) * 196;
    const kids = [];
    if (best && bound !== null) {
      kids.push(Rc(X(best.mean), 18, X(bound) - X(best.mean), 22 + rows.length * 30, 'ochretint'),
        Ln(X(bound), 16, X(bound), 42 + rows.length * 30, 'acc', 1.6, '4 3'),
        T(Math.min(X(bound) + 3, 296), 11, c.band(ctx.format.number(bound, 'f2')), { fs: 10.5, a: 'end', c: 'acc' }));
    }
    ticks(lo, hi, 4).list.forEach(t => kids.push(T(X(t), 56 + rows.length * 30, ctx.format.number(t, 'auto'), { a: 'middle' })));
    rows.forEach((x, i) => {
      const y = 36 + i * 30;
      const picked = x.slot === one.pick;
      kids.push(T(0, y + 1, mname(ctx, x.slot), { fs: 11.5, c: 'ink', w: picked ? 600 : null }),
        T(0, y + 13, picked ? c.picked : x.slot === (one.best || s.best) ? c.best : '', { fs: 9.5, c: picked ? 'acc' : 'muted', w: picked ? 600 : null }),
        Ci(X(x.mean), y, 4.5, 'ink', { mark: picked ? 'picked' : 'config' }),
        T(X(x.mean), y - 8, ctx.format.number(x.mean, 'f2'), { fs: 10.5, a: 'middle', c: 'ink' }));
    });
    return [box(300, 64 + rows.length * 30, c.aria, kids, { 'data-one-se': one.pick || '' })];
  }

  /** Development and final evidence on one scale, the criterion's final bound as a line. */
  function devVsFinal(ctx, q) {
    const c = C().devFinal;
    const metric = metricOf(ctx);
    const ft = valuesOf(ctx, null, 'final_test.evaluation');
    const sel = valuesOf(ctx, null, 'evaluate.regression');
    if (!ft) return [unavailable('reading')];
    const ms = sel && sel.model_selection ? arr(sel.model_selection.configurations) : [];
    const fits = Object.keys(obj(ft.models));
    const rows = fits.map(slot => {
      const m = ft.models[slot];
      const iv = obj(obj(ft.intervals)[slot])[metric] || {};
      const dev = ms.find(x => x.slot === slot);
      const base = slot === 'fit.baseline' ? valuesOf(ctx, null, 'fit.baseline') : null;
      const devMean = dev && ok(dev.mean) ? dev.mean : base && base.cross_validation && base.cross_validation.spread
        ? obj(base.cross_validation.spread[metric]).mean : null;
      return { slot, f: m[metric], fl: iv.low, fh: iv.high, d: ok(devMean) ? devMean : null };
    });
    const cc = ctx.snapshot && ctx.snapshot.criterionConfigurations;
    const bound = cc && cc.finalTest && cc.finalTest.bound && ok(cc.finalTest.bound.value) ? cc.finalTest.bound.value : null;
    const vals = rows.flatMap(r => [r.f, r.fl, r.fh, r.d]).filter(ok).concat(bound === null ? [] : [bound]);
    const lo = Math.floor(Math.min(...vals));
    const hi = Math.ceil(Math.max(...vals));
    const X = v => 86 + ((v - lo) / (hi - lo || 1)) * 200;
    const kids = [];
    ticks(lo, hi, 5).list.forEach(t => kids.push(Ln(X(t), 22, X(t), 26 + rows.length * 40, 'grid'), T(X(t), 40 + rows.length * 40, ctx.format.number(t, 'auto'), { a: 'middle' })));
    if (bound !== null) kids.push(Ln(X(bound), 16, X(bound), 26 + rows.length * 40, 'leaf', 1.8), T(X(bound) - 3, 14, c.bound(ctx.format.number(bound, 'f2')), { fs: 10.5, a: 'end', c: 'leaf' }));
    rows.forEach((r, i) => {
      const y = 40 + i * 40;
      kids.push(T(78, y + 10, mname(ctx, r.slot), { fs: 11.5, a: 'end', c: 'ink' }));
      if (r.d !== null) kids.push(Ci(X(r.d), y, 4.5, 'card', { s: 'ink', sw: 1.8, mark: 'development' }));
      if (ok(r.fl) && ok(r.fh)) kids.push(Ln(X(r.fl), y + 15, X(r.fh), y + 15, 'pen', 2));
      if (ok(r.f)) kids.push(Ci(X(r.f), y + 15, 4.5, 'pen', { mark: 'final' }));
    });
    const yb = 52 + rows.length * 40;
    kids.push(Ci(8, yb, 4, 'card', { s: 'ink', sw: 1.6 }), T(16, yb + 4, c.dev, { fs: 10.5 }), Ci(150, yb, 4, 'pen'), T(158, yb + 4, c.final, { fs: 10.5 }));
    return [box(300, yb + 10, c.aria, kids, { 'data-dev-final': String(rows.length) })];
  }

  /** The criterion on the final test: the reduction, its interval and the minimum (verdict chip outside). */
  function criterionGauge(ctx, q) {
    const c = C().gauge;
    const ft = valuesOf(ctx, null, 'final_test.evaluation');
    const k = ft && ft.criterion;
    if (!k || !ok(k.gain)) return [unavailable('reading')];
    const X = v => 16 + v * 268;
    const pct = v => ctx.format.number(v, 'pct1');
    const kids = [];
    [0, 0.25, 0.5, 0.75, 1].forEach(t => kids.push(T(X(t), 72, ctx.format.number(t, 'pct0'), { a: t === 1 ? 'end' : t === 0 ? 'start' : 'middle' })));
    if (ok(k.minimum)) kids.push(Ln(X(k.minimum), 8, X(k.minimum), 58, 'leaf', 1.8), T(X(k.minimum) + 3, 16, c.minimum(pct(k.minimum)), { c: 'leaf' }));
    if (ok(k.low) && ok(k.high)) kids.push(Ln(X(k.low), 38, X(k.high), 38, 'pen', 2.4));
    kids.push(Ci(X(k.gain), 38, 5, 'pen'), T(X(k.gain), 28, pct(k.gain), { a: 'middle', c: 'ink', w: 600 }));
    // R67: the business bar, when the criterion has two levels, is said under the gauge.
    return [box(300, 80, c.aria(pct(k.gain), ok(k.minimum) ? pct(k.minimum) : ''), kids, { 'data-criterion-gauge': k.status || '' })];
  }

  function distributionBeforeAfter(ctx, q) {
    const c = C().distribution;
    const slot = q.source.slot && q.source.slot.startsWith('eda.distribution') ? q.source.slot : 'eda.distribution:horsepower';
    const v = valuesOf(ctx, q.resultId, slot);
    if (!v || !v.numeric) return [unavailable('reading')];
    const h = histogramOf(ctx, v.numeric, q.resultId || idOf(ctx, slot), 'numeric.bins', c.aria(colName(ctx, v.column)), 'pen', colName(ctx, v.column));
    return h ? [h] : [unavailable()];
  }

  const CHARTS = {
    sample_table: sampleTable,
    structure_bars: structureBars,
    moment_timeline: (ctx, q) => (q.chartData ? [momentTimeline(ctx, q, q.chartData, true)] : [unavailable()]),
    variables_board: (ctx, q) => (q.chartData ? variablesBoard(ctx, q, q.chartData) : [unavailable()]),
    partition_strata: (ctx, q) => (q.chartData ? partitionStrata(ctx, q, q.chartData) : [unavailable()]),
    folds: (ctx, q) => (q.chartData ? foldsChart(ctx, q, q.chartData) : [unavailable()]),
    metric_bars: (ctx, q) => (q.chartData ? metricBars(ctx, q, q.chartData) : [unavailable()]),
    bars: (ctx, q) => (q.chartData && arr(q.chartData.bars).length ? barsFromData(ctx, q.chartData) : missingBars(ctx, q)),
    criterion_bars: (ctx, q) => (q.chartData ? barsFromData(ctx, q.chartData) || [unavailable()] : [unavailable()]),
    verdicts_table: (ctx, q) => verdictsTable(ctx, q, q.id === 'prep.unchanged' ? 'unchanged' : 'all'),
    distribution_before_after: distributionBeforeAfter,
    histogram: targetSummary,
    trend_by_bins: (ctx, q) => trendByBins(ctx, q),
    correlation,
    model_dots: modelDots,
    observed_predicted: observedPredicted,
    residual_by_feature: residualByFeature,
    bias_by_period: biasByPeriod,
    per_fold_dots: perFoldDots,
    paired_intervals: pairedIntervals,
    one_se_rule: oneSeRule,
    dev_vs_final: devVsFinal,
    criterion_gauge: criterionGauge,
  };

  /** One chart of a question; `kind` defaults to the question's main chart. */
  function stepChart(ctx, q, card, kind = null, slot = null) {
    const k = kind || q.chart;
    const fn = CHARTS[k];
    if (!fn) return [unavailable()];
    if (slot && k === 'trend_by_bins') return trendByBins(ctx, q, slot);
    try {
      return arr(fn(ctx, q, card)).filter(Boolean);
    } catch (e) {
      // A drawing that cannot read its values says so; the reading stays.
      return [unavailable()];
    }
  }

  HT.components = HT.components || {};
  Object.assign(HT.components, { stepPicture, stepChart, stepSampleFolds: sampleFolds, stepColName: colName, STEP_CHART_KINDS: Object.keys(CHARTS) });
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
