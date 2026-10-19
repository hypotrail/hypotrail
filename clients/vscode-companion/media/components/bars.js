// Horizontal bars (COMPANION-ADVANCED §6.3, §6.5). Frozen by WP-0:
//   bars(container, {items: [{label, value, valueText, small, cited: {resultId, path, value} | null}],
//                    max, rule: {value, label} | null, title, unit})
// Geometry only (INV-14): a bar's length is value / max of the plot width. The texts are
// the engine's values formatted by the view (valueText); a `small` bar is hatched AND
// carries the text "small" (never colour alone). Cited values carry data-result-id,
// data-path and data-value. Returns the figure element.
//
// WP-A5: an item with `tone: 'baseline'` (a reference such as the baseline model) is drawn
// in the baseline grey; every other bar is the model accent.
//
// WP-I: the label and value columns are as wide as their longest text (an estimate of
// the 11 px font, bounded), and the plot keeps its width, so a long label is not clipped;
// `labelWidth` and `valueWidth` (viewBox units) override the estimate.
(function (HT) {
  'use strict';
  const PLOT = 210;
  const ROW = 24;
  let charts = 0;

  function hatch(id) {
    return HT.svg('defs', {}, [HT.svg('pattern', { id, width: 6, height: 6, patternUnits: 'userSpaceOnUse',
      patternTransform: 'rotate(45)' }, [
      HT.svg('rect', { width: 6, height: 6, fill: 'surface' }),
      HT.svg('line', { x1: 0, y1: 0, x2: 0, y2: 6, stroke: 'accent', 'stroke-width': 3 })])]);
  }

  function bars(container, { items, max, rule = null, title, unit = '', labelWidth = null, valueWidth = null }) {
    charts += 1;
    const id = `ht-hatch-${charts}`;
    const fit = HT.components.textWidth;
    const LABEL = labelWidth || fit(items.map(i => (i.small ? `${i.label} (${HT.copy.core.small})` : i.label)), 60, 320) + 6;
    const VALUE = valueWidth || fit(items.map(i => i.valueText), 40, 200) + 8;
    const plot = PLOT;
    const W = LABEL + plot + VALUE;
    const top = max > 0 ? max : Math.max(0, ...items.map(i => Number(i.value) || 0)) || 1;
    const height = items.length * ROW + (rule ? 18 : 6);
    const x = v => LABEL + Math.max(0, Math.min(1, (Number(v) || 0) / top)) * plot;
    const chart = HT.svg('svg', { viewBox: `0 0 ${W} ${height}`, width: '100%', class: 'ht-chart ht-bars' }, [
      hatch(id),
      ...items.map((item, i) => {
        const y = i * ROW + 4;
        const text = HT.svg('text', { x: x(item.value) + 4, y: y + 13, class: 'ht-value', text: item.valueText });
        if (item.cited) {
          text.setAttribute('data-result-id', String(item.cited.resultId || ''));
          text.setAttribute('data-path', String(item.cited.path || ''));
          text.setAttribute('data-value', String(item.cited.value));
        }
        return HT.svg('g', { 'data-bar': item.label, 'data-small': item.small ? 'true' : null }, [
          HT.svg('text', { x: LABEL - 6, y: y + 13, class: 'ht-label', 'text-anchor': 'end',
            text: item.small ? `${item.label} (${HT.copy.core.small})` : item.label }),
          HT.svg('rect', { x: LABEL, y, height: ROW - 8, width: Math.max(1, x(item.value) - LABEL),
            fill: item.small ? `url(#${id})` : item.tone === 'baseline' ? 'baseline' : 'accent',
            'data-hatched': item.small ? 'true' : null, 'data-tone': item.tone === 'baseline' ? 'baseline' : 'model' }),
          text,
        ]);
      }),
      rule ? HT.svg('g', { 'data-rule': true }, [
        HT.svg('line', { x1: x(rule.value), x2: x(rule.value), y1: 0, y2: items.length * ROW + 4, stroke: 'fg',
          'stroke-dasharray': '3 3' }),
        HT.svg('text', { x: x(rule.value), y: items.length * ROW + 16, class: 'ht-muted-text', 'text-anchor': 'middle',
          text: rule.label }),
      ]) : null,
    ]);
    return HT.components.figure(container, {
      title, chart,
      columns: [{ key: 'label', label: '' }, { key: 'value', label: unit || '' }, { key: 'small', label: '' }],
      rows: items.map(i => ({ label: i.label, value: { text: i.valueText, cited: i.cited || null },
        small: i.small ? HT.copy.core.small : '' })),
    });
  }

  HT.components.bars = bars;
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
