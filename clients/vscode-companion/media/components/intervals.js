// Interval rows (uncertainty, COMPANION-ADVANCED §6.4 E). Frozen by WP-0:
//   intervalRows(container, {rows: [{label, point, low, high, pointText, intervalText}], zero, title})
// Each row is a point inside its interval on one shared axis; with `zero: true` the axis
// includes 0 and draws a 0 rule. Positions are geometry of engine values (INV-14); the texts
// are the view's formatted engine values. Returns the figure element.
//
// WP-I: the label and text columns are as wide as their longest text (bounded estimate,
// as bars.js), so no label or interval text is clipped; `labelWidth` and `textWidth`
// (viewBox units) override the estimate.
(function (HT) {
  'use strict';
  const PLOT = 200;
  const ROW = 26;

  function intervalRows(container, { rows, zero = false, title, labelWidth = null, textWidth = null }) {
    const fit = HT.components.textWidth;
    const LABEL = labelWidth || fit(rows.map(r => r.label), 60, 320) + 6;
    const TEXT = textWidth || fit(rows.map(r => [r.pointText, r.intervalText].filter(Boolean).join(' ')), 60, 320) + 12;
    const W = LABEL + PLOT + TEXT;
    const values = rows.flatMap(r => [r.low, r.high, r.point]).filter(v => typeof v === 'number' && Number.isFinite(v));
    let lo = Math.min(...values, zero ? 0 : Infinity);
    let hi = Math.max(...values, zero ? 0 : -Infinity);
    if (!Number.isFinite(lo) || !Number.isFinite(hi)) { lo = 0; hi = 1; }
    if (hi === lo) { hi = lo + 1; }
    const pad = (hi - lo) * 0.05;
    lo -= pad; hi += pad;
    const plot = PLOT;
    const x = v => LABEL + ((v - lo) / (hi - lo)) * plot;
    const height = rows.length * ROW + 6;
    const ok = v => typeof v === 'number' && Number.isFinite(v);
    const chart = HT.svg('svg', { viewBox: `0 0 ${W} ${height}`, width: '100%', class: 'ht-chart ht-intervals' }, [
      zero ? HT.svg('line', { x1: x(0), x2: x(0), y1: 0, y2: height, stroke: 'fg', 'data-zero': true }) : null,
      ...rows.map((r, i) => {
        const y = i * ROW + ROW / 2;
        return HT.svg('g', { 'data-interval': r.label }, [
          HT.svg('text', { x: LABEL - 6, y: y + 4, class: 'ht-label', 'text-anchor': 'end', text: r.label }),
          ok(r.low) && ok(r.high) ? HT.svg('line', { x1: x(r.low), x2: x(r.high), y1: y, y2: y, stroke: 'accent', 'stroke-width': 3 }) : null,
          ok(r.point) ? HT.svg('circle', { cx: x(r.point), cy: y, r: 4, fill: 'fg' }) : null,
          HT.svg('text', { x: W - TEXT + 6, y: y + 4, class: 'ht-value', text: [r.pointText, r.intervalText].filter(Boolean).join(' ') }),
        ]);
      }),
    ]);
    return HT.components.figure(container, {
      title, chart,
      columns: [{ key: 'label', label: '' }, { key: 'point', label: '' }, { key: 'interval', label: '' }],
      rows: rows.map(r => ({ label: r.label, point: r.pointText || '', interval: r.intervalText || '' })),
    });
  }

  HT.components.intervalRows = intervalRows;
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
