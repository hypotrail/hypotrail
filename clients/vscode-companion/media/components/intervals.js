// Interval rows (uncertainty, COMPANION-ADVANCED §6.4 E). Signature (frozen by WP-0):
//   intervalRows(container, {rows: [{label, point, low, high, pointText, intervalText, tone?}], zero, title})
// Each row is a point inside its interval on one shared axis; with `zero: true` the axis
// includes 0 and draws a 0 rule, labelled. Positions are geometry of engine values (INV-14);
// the texts are the view's formatted engine values. `tone: 'baseline'` draws the reference
// (the baseline model) in grey. v0.3 (WP-E2): an HTML grid like bars.js, fluid at every
// width (no sideways scroll); positions are custom properties set through CSSOM. Returns the
// figure element.
(function (HT) {
  'use strict';
  const ok = v => typeof v === 'number' && Number.isFinite(v);

  function intervalRows(container, { rows, zero = false, title, showTitle = true }) {
    const values = rows.flatMap(r => [r.low, r.high, r.point]).filter(ok);
    let lo = Math.min(...values, zero ? 0 : Infinity);
    let hi = Math.max(...values, zero ? 0 : -Infinity);
    if (!Number.isFinite(lo) || !Number.isFinite(hi)) { lo = 0; hi = 1; }
    if (hi === lo) hi = lo + 1;
    const pad = (hi - lo) * 0.05;
    lo -= pad; hi += pad;
    const x = v => Math.max(0, Math.min(100, ((v - lo) / (hi - lo)) * 100)).toFixed(2);
    const items = rows.map(r => {
      const ref = r.tone === 'baseline';
      const tone = ref ? 'baseline' : 'model';
      return HT.el('div', { className: 'ht-row', 'data-interval-row': r.label }, [
        HT.el('div', { className: 'ht-lab', text: r.label }),
        HT.el('div', { className: 'ht-trk' }, [
          zero ? HT.el('span', { className: 'ht-vline ht-vzero', 'data-zero': true, 'aria-hidden': 'true', css: { '--x': x(0) } }) : null,
          ok(r.low) && ok(r.high) ? HT.el('span', { className: `ht-ci${ref ? ' ht-ref' : ''}`, 'data-interval': true,
            'data-tone': tone, 'aria-hidden': 'true', css: { '--a': x(r.low), '--b': x(r.high) } }) : null,
          ok(r.point) ? HT.el('span', { className: `ht-pt${ref ? ' ht-ref' : ''}`, 'data-point': true, 'data-tone': tone,
            'aria-hidden': 'true', css: { '--x': x(r.point) } }) : null,
        ]),
        HT.el('div', { className: 'ht-val ht-value', text: [r.pointText, r.intervalText].filter(Boolean).join(' ') }),
      ]);
    });
    const axis = [HT.el('div', { 'aria-hidden': 'true' }),
      HT.el('div', { className: 'ht-axis', 'data-axis': true, 'aria-hidden': 'true' },
        zero ? [HT.el('span', { 'data-literal': 'axis', css: { '--x': x(0) }, text: '0' })] : []),
      HT.el('div', { 'aria-hidden': 'true' })];
    const chart = HT.el('div', { className: 'ht-hbars ht-intervals', 'data-chart': 'intervals' }, [...items, ...axis]);
    return HT.components.figure(container, {
      title, chart, showTitle,
      columns: [{ key: 'label', label: '' }, { key: 'point', label: '' }, { key: 'interval', label: '' }],
      rows: rows.map(r => ({ label: r.label, point: r.pointText || '', interval: r.intervalText || '' })),
    });
  }

  HT.components.intervalRows = intervalRows;
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
