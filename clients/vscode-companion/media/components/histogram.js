// Histogram of fixed-width bins (eda.distribution, CLI-CONTRACT-COMPANION §8). Frozen by WP-0:
//   histogram(container, {bins: [{low, high, count, countText}], title, axisLabel})
// Column heights are geometry of the engine's counts (INV-14). Bin edges are shown in the
// values table as the engine gave them. Returns the figure element.
(function (HT) {
  'use strict';
  const W = 420;
  const H = 140;
  const BASE = 120;

  function histogram(container, { bins, title, axisLabel = '' }) {
    const top = Math.max(1, ...bins.map(b => Number(b.count) || 0));
    const width = (W - 20) / Math.max(1, bins.length);
    const chart = HT.svg('svg', { viewBox: `0 0 ${W} ${H}`, width: '100%', class: 'ht-chart ht-histogram' }, [
      ...bins.map((b, i) => {
        const h = ((Number(b.count) || 0) / top) * (BASE - 10);
        return HT.svg('rect', { x: 10 + i * width + 1, y: BASE - h, width: Math.max(1, width - 2), height: Math.max(0, h),
          fill: 'accent', 'data-bin': i });
      }),
      HT.svg('line', { x1: 10, x2: W - 10, y1: BASE, y2: BASE, stroke: 'border' }),
      axisLabel ? HT.svg('text', { x: W / 2, y: H - 4, class: 'ht-muted-text', 'text-anchor': 'middle', 'aria-hidden': 'true',
        'data-literal': 'axis', text: axisLabel }) : null,
    ]);
    return HT.components.figure(container, {
      title, chart,
      columns: [{ key: 'low', label: '' }, { key: 'high', label: '' }, { key: 'count', label: '' }],
      rows: bins.map(b => ({ low: String(b.low), high: String(b.high), count: b.countText })),
    });
  }

  HT.components.histogram = histogram;
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
