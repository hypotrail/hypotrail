// A curve of registered points (WP-B5): the gain curve of the What if? tab and the Evidence
// diagnostics (gain, calibration). Signature:
//   curve(container, {title, points: [{x, y, low?, high?, label, tone?}], xDomain, yDomain,
//                     xTicks: [{value, text}], yTicks: [{value, text}], xLabel, yLabel,
//                     diagonal: {label} | null, marks: [{x, label, tone}], columns, rows})
// Geometry only (INV-14): each point sits at the engine's value; the points are joined in
// the order of x, with no point added between or after them. The diagonal (random
// selection for a gain curve, perfect calibration for a calibration plot) and the axis
// ticks are geometry: tick texts are rounded positions of the axis, aria-hidden, with
// `data-literal="axis"`. `low`/`high` draw the engine's interval of y as a vertical line.
// A mark is a vertical dashed line at x (a share the junior or the case chose), named in
// the figure's table, never a figure. The values table (`columns`, `rows`) carries the
// cited numbers. Returns the figure element.
(function (HT) {
  'use strict';
  const W = 380;
  const H = 266;
  // WP-E1 (R26): the y-axis label is written horizontally above the axis, so it is never
  // clipped by the viewBox nor overlapped by the tick texts (it was rotated at x = 12).
  const M = { left: 52, right: 26, top: 28, bottom: 44 };

  function curve(container, { title, points, xDomain = [0, 1], yDomain = [0, 1], xTicks = [], yTicks = [], xLabel = '',
    yLabel = '', diagonal = null, marks = [], columns, rows }) {
    const pw = W - M.left - M.right;
    const ph = H - M.top - M.bottom;
    const clamp = (v, [a, b]) => Math.min(b, Math.max(a, v));
    const x = v => M.left + ((clamp(v, xDomain) - xDomain[0]) / (xDomain[1] - xDomain[0])) * pw;
    const y = v => M.top + ph - ((clamp(v, yDomain) - yDomain[0]) / (yDomain[1] - yDomain[0])) * ph;
    const ok = v => typeof v === 'number' && Number.isFinite(v);
    const shown = points.filter(p => ok(p.x) && ok(p.y)).sort((a, b) => a.x - b.x);
    const path = shown.map((p, i) => `${i ? 'L' : 'M'}${x(p.x).toFixed(1)} ${y(p.y).toFixed(1)}`).join(' ');
    const baseY = M.top + ph;
    const diagonalStart = Math.max(xDomain[0], yDomain[0]);
    const diagonalEnd = Math.min(xDomain[1], yDomain[1]);
    const chart = HT.svg('svg', { viewBox: `0 0 ${W} ${H}`, width: '100%', class: 'ht-chart ht-curve' }, [
      // Axes.
      HT.svg('line', { x1: M.left, x2: M.left + pw, y1: baseY, y2: baseY, stroke: 'muted', 'data-axis': 'x' }),
      HT.svg('line', { x1: M.left, x2: M.left, y1: M.top, y2: baseY, stroke: 'muted', 'data-axis': 'y' }),
      ...xTicks.map(t => HT.svg('text', { x: x(t.value), y: baseY + 14, class: 'ht-muted-text', 'text-anchor': 'middle',
        'aria-hidden': 'true', 'data-literal': 'axis', text: t.text })),
      ...yTicks.map(t => HT.svg('text', { x: M.left - 6, y: y(t.value) + 4, class: 'ht-muted-text', 'text-anchor': 'end',
        'aria-hidden': 'true', 'data-literal': 'axis', text: t.text })),
      xLabel ? HT.svg('text', { x: M.left + pw / 2, y: H - 6, class: 'ht-label', 'text-anchor': 'middle', text: xLabel }) : null,
      yLabel ? HT.svg('text', { x: 4, y: 12, class: 'ht-label', 'text-anchor': 'start', 'data-axis-label': 'y', text: yLabel }) : null,
      // The reference diagonal.
      // y = x, up to the smaller of the two domains (the axes may be cut to the points' range).
      diagonal ? HT.svg('line', { x1: x(diagonalStart), y1: y(diagonalStart), x2: x(diagonalEnd), y2: y(diagonalEnd),
        stroke: 'baseline', 'stroke-dasharray': '4 3', 'data-diagonal': true }) : null,
      // The label sits below the diagonal: at its end, or at `diagonal.at` of its length
      // (a gain curve lies above the diagonal, so the space below it is free).
      diagonal ? (() => {
        const t = typeof diagonal.at === 'number' ? diagonalStart + diagonal.at * (diagonalEnd - diagonalStart) : diagonalEnd;
        return HT.svg('text', { x: x(t) + (diagonal.at ? 6 : -4), y: y(t) + 14, class: 'ht-muted-text',
          'text-anchor': diagonal.at ? 'start' : 'end', text: diagonal.label });
      })() : null,
      // Marks (a chosen share).
      ...marks.filter(m => ok(m.x)).map((m, i) => HT.svg('g', { 'data-mark': m.label }, [
        HT.svg('line', { x1: x(m.x), x2: x(m.x), y1: M.top, y2: baseY, stroke: m.tone === 'experiment' ? 'experiment' : 'accent',
          'stroke-dasharray': '2 3' }),
        HT.svg('text', { x: x(m.x) + 3, y: M.top + 10 + 12 * i, class: 'ht-muted-text', text: m.label }),
      ])),
      // The engine's points, joined in x order.
      shown.length > 1 ? HT.svg('path', { d: path, fill: 'none', stroke: 'accent', 'stroke-width': 2, 'data-curve': true }) : null,
      ...shown.map(p => HT.svg('g', { 'data-point': p.label }, [
        ok(p.low) && ok(p.high) ? HT.svg('line', { x1: x(p.x), x2: x(p.x), y1: y(p.low), y2: y(p.high), stroke: 'accent',
          'stroke-width': 2, 'data-interval': true }) : null,
        HT.svg('circle', { cx: x(p.x), cy: y(p.y), r: shown.length > 10 ? 2.5 : 4, fill: p.tone === 'baseline' ? 'baseline' : 'fg' }),
        // Below and to the right of the point: under a rising curve, away from its line.
        p.label ? HT.svg('text', { x: x(p.x) + 7, y: y(p.y) + 15, class: 'ht-value', text: p.label }) : null,
      ])),
    ]);
    return HT.components.figure(container, { title, chart, columns, rows });
  }

  HT.components.curve = curve;
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
