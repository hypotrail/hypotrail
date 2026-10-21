// Histogram (eda.distribution, CLI-CONTRACT-COMPANION §8). Signature (frozen by WP-0, extended):
//   histogram(container, {bins: [{low, high, count, countText, lowText?, highText?, edgeText?}],
//                         title, axisLabel, zero?: {share, valueText, rowsText, label},
//                         showTitle?, legend?})
// v0.3 (WP-E2, R17): an HTML grid, fluid at every width. Column heights are geometry of the
// engine's counts (INV-14), set as --v through CSSOM; the y axis names the largest count and
// half of it (rounded positions of the axis, aria-hidden), the x axis the bins' lower edges
// as the view formatted them (`edgeText`, at most six shown, the others kept for the values
// table). `zero` is the tile of the exact zeros of a skewed column, beside the plot of its
// positive values on log bins. `countText`, `lowText`, and `highText` are a text or a cited
// cell `{text, cited: {resultId, path, value}}`. Returns the figure element.
(function (HT) {
  'use strict';
  const MAX_EDGE_LABELS = 6;

  function niceTop(n) {
    if (n <= 0) return 1;
    const p = 10 ** Math.floor(Math.log10(n));
    for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= n) return m * p;
    return 10 * p;
  }

  function histogram(container, { bins, title, axisLabel = '', zero = null, showTitle = true, legend = [] }) {
    const counts = bins.map(b => Number(b.count) || 0);
    const top = niceTop(Math.max(1, ...counts));
    const fmt = n => HT.format.number(n, 'int');
    const step = Math.max(1, Math.ceil(bins.length / MAX_EDGE_LABELS));
    const plot = HT.el('div', { className: 'ht-hist', 'data-chart': 'histogram' }, [
      HT.el('div', { className: 'ht-yax', 'aria-hidden': 'true' }, [
        HT.el('span', { 'data-literal': 'axis', text: fmt(top) }), HT.el('span', { 'data-literal': 'axis', text: fmt(top / 2) }),
        HT.el('span', { 'data-literal': 'axis', text: '0' })]),
      HT.el('div', { className: 'ht-plot' }, [HT.el('div', { className: 'ht-cols' }, bins.map((b, i) => HT.el('i', {
        className: counts[i] === 0 ? 'ht-empty' : null, 'data-bin': i, 'aria-hidden': 'true',
        css: { '--v': ((counts[i] / top) * 100).toFixed(2) } })))]),
      HT.el('div', { className: 'ht-xax', 'aria-hidden': 'true' }, bins.map((b, i) => HT.el('span', {
        className: i % step === 0 ? null : 'ht-skip', 'data-literal': 'axis', text: b.edgeText || '' }))),
      axisLabel ? HT.el('div', { className: 'ht-xt', 'aria-hidden': 'true', 'data-literal': 'axis', text: axisLabel }) : null,
    ]);
    let chart = plot;
    if (zero) {
      chart = HT.el('div', { className: 'ht-split-fig' }, [
        HT.el('div', { className: 'ht-zero', 'data-zero-tile': true }, [
          HT.el('span', { className: 'ht-cap', text: zero.label }),
          HT.el('span', { className: 'ht-zero-v' }, [zero.valueText]),
          HT.el('span', { className: 'ht-zero-bar', 'aria-hidden': 'true' }, [HT.el('i', {
            css: { '--v': (Math.max(0, Math.min(1, Number(zero.share) || 0)) * 100).toFixed(2) } })]),
          HT.el('span', { className: 'ht-sub' }, [zero.rowsText]),
        ]),
        plot,
      ]);
    }
    return HT.components.figure(container, {
      title, chart, showTitle, legend,
      columns: [{ key: 'low', label: HT.copy.core.binFrom }, { key: 'high', label: HT.copy.core.binTo },
        { key: 'count', label: HT.copy.core.rowsWord }],
      rows: bins.map(b => ({ low: b.lowText !== undefined ? b.lowText : String(b.low),
        high: b.highText !== undefined ? b.highText : String(b.high), count: b.countText })),
    });
  }

  HT.components.histogram = histogram;
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
