// Dots on one scale (lot P, owner principle R42: prefer a chart whenever a value or a
// comparison can be drawn). Signature:
//   dotScale(container, {title, rows: [{label, point, low, high, dots: [number], tone?, pointText,
//     intervalText, mark?: 'final'|'development', highlight?}], refs: [{value, label}], band: {low, high, label}?,
//     zero, guide?, concl?, kind? (the guided reading's kind, `intervals` by default), plain? (no values toggle:
//     a table next to the chart lists them)})
// One row per configuration on one shared axis: the point (a ring when it is a mean over
// dots, a filled dot for the final test), its interval as a line, the per-fold values as
// small dots, reference values as dashed vertical lines named under the axis, and a band
// (best plus one standard error). The numbers are written at the end of each row. An HTML
// grid like intervals.js (fluid, no sideways scroll); positions are CSSOM custom properties.
(function (HT) {
  'use strict';
  const ok = v => typeof v === 'number' && Number.isFinite(v);

  function dotScale(container, { title, rows, refs = [], band = null, zero = false, guide = null, concl = null, showTitle = true, kind = 'intervals',
    plain = false }) {
    const values = rows.flatMap(r => [r.low, r.high, r.point, ...(r.dots || [])])
      .concat(refs.map(r => r.value), band ? [band.low, band.high] : []).filter(ok);
    let lo = Math.min(...values, zero ? 0 : Infinity);
    let hi = Math.max(...values, zero ? 0 : -Infinity);
    if (!Number.isFinite(lo) || !Number.isFinite(hi)) { lo = 0; hi = 1; }
    if (hi === lo) hi = lo + 1;
    const pad = (hi - lo) * 0.06;
    lo -= pad; hi += pad;
    const x = v => Math.max(0, Math.min(100, ((v - lo) / (hi - lo)) * 100)).toFixed(2);
    const items = rows.map(r => {
      const ref = r.tone === 'baseline';
      return HT.el('div', { className: `ht-row${r.highlight ? ' ht-row-hl' : ''}`, 'data-dot-row': r.label, 'data-mark': r.mark || null }, [
        HT.el('div', { className: 'ht-lab', text: r.label }),
        HT.el('div', { className: 'ht-trk' }, [
          band && ok(band.low) && ok(band.high) ? HT.el('span', { className: 'ht-band', 'data-band': true, 'aria-hidden': 'true',
            css: { '--a': x(band.low), '--b': x(band.high) } }) : null,
          zero ? HT.el('span', { className: 'ht-vline ht-vzero', 'aria-hidden': 'true', css: { '--x': x(0) } }) : null,
          ...refs.filter(f => ok(f.value)).map(f => HT.el('span', { className: 'ht-vline', 'data-ref': f.label, 'aria-hidden': 'true',
            css: { '--x': x(f.value) } })),
          ok(r.low) && ok(r.high) ? HT.el('span', { className: `ht-ci${ref ? ' ht-ref' : ''}`, 'data-interval': true, 'aria-hidden': 'true',
            css: { '--a': x(r.low), '--b': x(r.high) } }) : null,
          ...(r.dots || []).filter(ok).map(v => HT.el('span', { className: 'ht-dot', 'data-dot': true, 'aria-hidden': 'true', css: { '--x': x(v) } })),
          ok(r.point) ? HT.el('span', { className: `ht-pt${ref ? ' ht-ref' : ''}${r.mark === 'development' || (r.dots || []).length ? ' ht-ring' : ''}`,
            'data-point': true, 'aria-hidden': 'true', css: { '--x': x(r.point) } }) : null,
        ]),
        HT.el('div', { className: 'ht-val ht-value', text: [r.pointText, r.intervalText].filter(Boolean).join(' ') }),
      ]);
    });
    const marks = [...refs.filter(f => ok(f.value)).map(f => ({ value: f.value, text: f.label })),
      ...(zero ? [{ value: 0, text: '0' }] : [])];
    const axis = [HT.el('div', { 'aria-hidden': 'true' }),
      HT.el('div', { className: 'ht-axis ht-axis-refs', 'data-axis': true, 'aria-hidden': 'true' },
        marks.map(m => HT.el('span', { css: { '--x': x(m.value) }, text: m.text }))),
      HT.el('div', { 'aria-hidden': 'true' })];
    const chart = HT.el('div', { className: 'ht-hbars ht-intervals ht-dots', 'data-chart': 'dots' }, [...items, ...axis]);
    const legend = band && band.label ? [['band', band.label]] : [];
    if (plain) {
      // A chart whose values a table next to it already lists (the end's table, R52): no
      // second "Show values", only the title and the guided reading.
      chart.setAttribute('role', 'img');
      chart.setAttribute('aria-label', title);
      const lesson = HT.components.reading && HT.copy.lesson ? HT.components.reading(kind, { title, showTitle,
        guide: { ...((HT.components.currentGuide && HT.components.currentGuide()) || {}), ...(guide || {}) }, concl }) : null;
      const node = HT.el('figure', { className: 'ht-figure' }, [HT.el('figcaption', { className: lesson ? 'sr-only' : null, text: title }),
        lesson ? lesson.top : null, chart, lesson ? lesson.bottom : null]);
      if (container) container.appendChild(node);
      return node;
    }
    return HT.components.figure(container, {
      title, chart, showTitle, guide, legend, reading: { kind, concl },
      columns: [{ key: 'label', label: '' }, { key: 'point', label: '' }, { key: 'dots', label: '' }],
      rows: rows.map(r => ({ label: r.label, point: [r.pointText, r.intervalText].filter(Boolean).join(' '),
        dots: (r.dotTexts || []).join(' · ') })),
    });
  }

  HT.components.dotScale = dotScale;
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
