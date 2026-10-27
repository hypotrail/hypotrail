// Horizontal bars (COMPANION-ADVANCED §6.3, §6.5). Signature (frozen by WP-0, extended):
//   bars(container, {items: [{label, sub?, value, valueText, small, tone?, interval?, band?,
//                    cited: {resultId, path, value} | null}], max, rule: {value, label} | null,
//                    title, unit, ticks?: [{value, text}], point?: bool, guide?})
// Lesson style (R30): the figure carries the guided reading of the bars (lesson.js), with the
// conclusion drawn from the values below and the view's `guide` (question, frame, rows, model).
// v0.3 (WP-E2): an HTML grid, fluid at every width (no sideways scroll): a label column, a
// track, and a value column. Geometry only (INV-14): a bar's length is value / max of the
// track, set as the custom property --v through CSSOM. A `small` bar is hatched AND carries
// the text "small" (never colour alone). `tone: 'baseline'` draws a reference in grey.
// `interval: {low, high}` draws the engine's interval with end caps; `band: {low, high}` a
// grey band behind it (the range a null model draws). With `point: true` each row is a
// point inside its interval instead of a bar (rate by group: point + interval + band + n).
// `rule` is a dashed vertical line (the overall rate), named in the legend. `ticks` are
// rounded positions of the axis (aria-hidden, data-literal="axis"). Cited values carry
// data-result-id, data-path and data-value. Returns the figure element.
(function (HT) {
  'use strict';
  const ok = v => typeof v === 'number' && Number.isFinite(v);

  function pct(v, top) {
    return Math.max(0, Math.min(100, ((Number(v) || 0) / top) * 100));
  }

  function valueNode(item) {
    if (!item.cited) return document.createTextNode(item.valueText);
    return HT.components.cited(item.valueText, item.cited);
  }

  /**
   * Lesson style (R30): what the bars say, from the values they draw: the largest and the
   * smallest (rows too small to be read alone apart), the groups outside the grey band, the
   * dashed line. Texts are the panel's copy; figures are the chart's own value texts.
   */
  function conclusion(items, { point, rule }) {
    const R = HT.copy.lesson && HT.copy.lesson.concl;
    if (!R) return null;
    const q = i => HT.components.quote(i.valueText, i.cited);
    const read = items.filter(i => ok(Number(i.value)) && !i.small);
    const out = [];
    if (read.length === 1) out.push(R.one(read[0].label, q(read[0])));
    else if (read.length > 1) {
      const hi = read.reduce((a, b) => (Number(b.value) > Number(a.value) ? b : a));
      const lo = read.reduce((a, b) => (Number(b.value) < Number(a.value) ? b : a));
      out.push(point ? R.points(hi.label, q(hi), lo.label, q(lo)) : R.bars(hi.label, q(hi), lo.label, q(lo)));
    }
    const banded = items.filter(i => i.band && ok(i.band.low) && ok(i.band.high) && ok(Number(i.value)));
    if (banded.length) {
      const outside = banded.filter(i => Number(i.value) < i.band.low || Number(i.value) > i.band.high).length;
      out.push(R.outsideBand(HT.format.number(outside, 'int'), HT.format.number(banded.length, 'int')));
    }
    if (rule && rule.label) out.push(R.rule(rule.label));
    const small = items.filter(i => i.small).map(i => i.label);
    if (small.length) out.push(R.small(small.join(', ')));
    return out.length ? out : null;
  }

  function bars(container, { items, max, rule = null, title, unit = '', ticks = null, point = false, showTitle = true, guide = null }) {
    const top = max > 0 ? max : Math.max(0, ...items.map(i => Math.max(Number(i.value) || 0,
      i.interval && ok(i.interval.high) ? i.interval.high : 0))) || 1;
    const small = HT.copy.core.small;
    const rows = items.map(item => {
      const iv = item.interval && ok(item.interval.low) && ok(item.interval.high) ? item.interval : null;
      const band = item.band && ok(item.band.low) && ok(item.band.high) ? item.band : null;
      const ref = item.tone === 'baseline';
      const track = HT.el('div', { className: 'ht-trk' }, [
        band ? HT.el('span', { className: 'ht-band', 'data-band': true, 'aria-hidden': 'true',
          css: { '--a': pct(band.low, top).toFixed(2), '--b': pct(band.high, top).toFixed(2) } }) : null,
        point ? null : HT.el('span', {
          className: `ht-bar${item.small ? ' ht-hatch' : ref ? ' ht-ref' : ''}`, 'aria-hidden': 'true',
          'data-hatched': item.small ? 'true' : null, 'data-tone': ref ? 'baseline' : 'model',
          css: { '--v': pct(item.value, top).toFixed(2) } }),
        rule && ok(rule.value) ? HT.el('span', { className: 'ht-vline', 'data-rule': true, 'aria-hidden': 'true',
          css: { '--x': pct(rule.value, top).toFixed(2) } }) : null,
        iv ? HT.el('span', { className: `ht-ci${ref ? ' ht-ref' : ''}`, 'data-interval': true, 'aria-hidden': 'true',
          css: { '--a': pct(iv.low, top).toFixed(2), '--b': pct(iv.high, top).toFixed(2) } }) : null,
        point && ok(item.value) ? HT.el('span', { className: `ht-pt${ref ? ' ht-ref' : ''}`, 'data-point': true,
          'data-hatched': item.small ? 'true' : null, 'data-tone': ref ? 'baseline' : 'model', 'aria-hidden': 'true',
          css: { '--x': pct(item.value, top).toFixed(2) } }) : null,
      ]);
      return HT.el('div', { className: 'ht-row', 'data-bar': item.label, 'data-small': item.small ? 'true' : null }, [
        HT.el('div', { className: 'ht-lab' }, [item.label, item.small ? HT.el('small', { text: ` (${small})` }) : null,
          item.sub ? HT.el('small', { text: ` ${item.sub}` }) : null]),
        track,
        HT.el('div', { className: 'ht-val ht-value' }, [valueNode(item)]),
      ]);
    });
    const axis = ticks && ticks.length ? [HT.el('div', { 'aria-hidden': 'true' }),
      HT.el('div', { className: 'ht-axis', 'aria-hidden': 'true' }, ticks.map((t, i) => HT.el('span', {
        className: i === 0 && pct(t.value, top) < 4 ? 'ht-first' : pct(t.value, top) > 96 ? 'ht-last' : null,
        'data-literal': 'axis', text: t.text, css: { '--x': pct(t.value, top).toFixed(2) } }))),
      HT.el('div', { 'aria-hidden': 'true' })] : [];
    const chart = HT.el('div', { className: 'ht-hbars', 'data-chart': point ? 'intervals' : 'bars' }, [...rows, ...axis]);
    const legend = [];
    if (items.some(i => i.interval)) legend.push(['ci', HT.copy.core.legendInterval]);
    if (items.some(i => i.band)) legend.push(['band', HT.copy.core.legendBand]);
    if (rule && rule.label) legend.push(['line', rule.label]);
    if (items.some(i => i.small)) legend.push([point ? 'hollow' : 'hatch', HT.copy.core.legendSmall]);
    const R = HT.copy.lesson && HT.copy.lesson.steps;
    return HT.components.figure(container, {
      title, chart, legend, showTitle, guide,
      reading: { kind: point ? 'points' : 'bars', concl: conclusion(items, { point, rule }),
        steps: R && rule && rule.label ? [R.rule(rule.label)] : null },
      columns: [{ key: 'label', label: '' }, { key: 'value', label: unit || '' }, { key: 'small', label: '' }],
      rows: items.map(i => ({ label: i.label, value: { text: i.valueText, cited: i.cited || null },
        small: i.small ? small : '' })),
    });
  }

  HT.components.bars = bars;
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
