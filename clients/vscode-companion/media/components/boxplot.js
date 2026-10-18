// Box and whisker (eda.target_summary, residual quantiles, COMPANION-ADVANCED §6.3, §6.5.2).
// Frozen by WP-0:
//   boxplot(container, {min, q25, median, q75, max, texts: {min, q25, median, q75, max}, title})
// Positions are geometry of the engine's quantiles (INV-14); `texts` are the view's
// formatted engine values. Returns the figure element.
(function (HT) {
  'use strict';
  const W = 420;
  const H = 60;

  function boxplot(container, { min, q25, median, q75, max, texts = {}, title }) {
    const lo = Number(min);
    const hi = Number(max) > lo ? Number(max) : lo + 1;
    const x = v => 20 + ((Number(v) - lo) / (hi - lo)) * (W - 40);
    const y = 26;
    const chart = HT.svg('svg', { viewBox: `0 0 ${W} ${H}`, width: '100%', class: 'ht-chart ht-boxplot' }, [
      HT.svg('line', { x1: x(min), x2: x(max), y1: y, y2: y, stroke: 'muted' }),
      HT.svg('rect', { x: x(q25), y: y - 10, width: Math.max(1, x(q75) - x(q25)), height: 20, fill: 'surface', stroke: 'accent' }),
      HT.svg('line', { x1: x(median), x2: x(median), y1: y - 10, y2: y + 10, stroke: 'fg', 'stroke-width': 2, 'data-median': true }),
      HT.svg('text', { x: x(min), y: H - 6, class: 'ht-muted-text', 'text-anchor': 'start', text: texts.min || '' }),
      HT.svg('text', { x: x(max), y: H - 6, class: 'ht-muted-text', 'text-anchor': 'end', text: texts.max || '' }),
    ]);
    const keys = ['min', 'q25', 'median', 'q75', 'max'];
    return HT.components.figure(container, {
      title, chart,
      columns: keys.map(k => ({ key: k, label: k })),
      rows: [Object.fromEntries(keys.map(k => [k, texts[k] || '']))],
    });
  }

  HT.components.boxplot = boxplot;
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
