// Box and whisker (eda.target_summary, residual quantiles, COMPANION-ADVANCED §6.3, §6.5.2).
// Frozen by WP-0:
//   boxplot(container, {min, q25, median, q75, max, texts: {min, q25, median, q75, max}, title})
// Positions are geometry of the engine's quantiles (INV-14); `texts` are the view's
// formatted engine values, each a text or a cited cell `{text, cited: {resultId, path,
// value}}` (WP-I, U4 request): the axis texts then carry data-result-id, data-path, and
// data-value, and the values table cites them. Returns the figure element.
(function (HT) {
  'use strict';
  const W = 420;
  const H = 60;

  const textOf = t => (t && typeof t === 'object' ? String(t.text || '') : String(t || ''));

  /** An axis text, cited when its cell is. */
  function axisText(attrs, t) {
    const node = HT.svg('text', { ...attrs, text: textOf(t) });
    if (t && typeof t === 'object' && t.cited) {
      node.setAttribute('data-result-id', String(t.cited.resultId || ''));
      node.setAttribute('data-path', String(t.cited.path || ''));
      node.setAttribute('data-value', String(t.cited.value));
    }
    return node;
  }

  /** Lesson style (R30): the median, the middle half, the range, and which side has the tail. */
  function conclusion({ min, q25, median, q75, max, texts }) {
    const R = HT.copy.lesson && HT.copy.lesson.concl;
    const v = [min, q25, median, q75, max].map(Number);
    if (!R || !v.every(Number.isFinite)) return null;
    const q = k => HT.components.quote(texts[k]);
    const upper = v[4] - v[3];
    const lower = v[1] - v[0];
    const side = upper > 1.5 * lower ? 'upper' : lower > 1.5 * upper ? 'lower' : 'even';
    return [R.box(q('median'), q('q25'), q('q75'), q('min'), q('max')), R.boxTail[side]];
  }

  function boxplot(container, { min, q25, median, q75, max, texts = {}, title, guide = null }) {
    const lo = Number(min);
    const hi = Number(max) > lo ? Number(max) : lo + 1;
    const x = v => 20 + ((Number(v) - lo) / (hi - lo)) * (W - 40);
    const y = 26;
    const chart = HT.svg('svg', { viewBox: `0 0 ${W} ${H}`, width: '100%', class: 'ht-chart ht-boxplot' }, [
      HT.svg('line', { x1: x(min), x2: x(max), y1: y, y2: y, stroke: 'muted' }),
      HT.svg('rect', { x: x(q25), y: y - 10, width: Math.max(1, x(q75) - x(q25)), height: 20, fill: 'surface', stroke: 'accent' }),
      HT.svg('line', { x1: x(median), x2: x(median), y1: y - 10, y2: y + 10, stroke: 'fg', 'stroke-width': 2, 'data-median': true }),
      axisText({ x: x(min), y: H - 6, class: 'ht-muted-text', 'text-anchor': 'start' }, texts.min),
      axisText({ x: x(max), y: H - 6, class: 'ht-muted-text', 'text-anchor': 'end' }, texts.max),
    ]);
    const keys = ['min', 'q25', 'median', 'q75', 'max'];
    return HT.components.figure(container, {
      title, chart, guide, reading: { kind: 'boxplot', concl: conclusion({ min, q25, median, q75, max, texts }) },
      columns: keys.map(k => ({ key: k, label: k })),
      rows: [Object.fromEntries(keys.map(k => [k, texts[k] && typeof texts[k] === 'object' ? texts[k] : (texts[k] || '')]))],
    });
  }

  HT.components.boxplot = boxplot;
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
