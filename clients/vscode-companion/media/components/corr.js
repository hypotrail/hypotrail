// Correlation matrix (eda.correlation, v0.3 WP-E2, R28):
//   corr(container, {order: [name], cell: (a, b) => {value, text, cited, flag, measure} | null,
//                    title, legend, columns, rows})
// The lower triangle of an HTML grid in the engine's clustered order (`order`), diverging
// from the background: positive associations in the accent, negative ones in orange, the
// strength as the tint (--a, CSSOM), a flagged pair outlined (never colour alone: the
// values table and the flagged list name it). Unsigned measures (Cramér's V, eta) use the
// positive side. With more than eight columns the numbers move to the values table and the
// hover. Returns the figure element.
(function (HT) {
  'use strict';
  const DENSE = 8;

  function corr(container, { order, cell, title, legend = [], columns, rows, tools = [] }) {
    const n = order.length;
    const items = [];
    order.forEach((a, i) => {
      items.push(HT.el('div', { className: 'ht-rh', title: a, text: a }));
      order.forEach((b, j) => {
        if (j > i) { items.push(HT.el('div', { className: 'ht-c ht-e', 'aria-hidden': 'true' })); return; }
        if (j === i) { items.push(HT.el('div', { className: 'ht-c ht-diag', 'aria-hidden': 'true' })); return; }
        const c = cell(a, b);
        if (!c || c.value === null || c.value === undefined) {
          items.push(HT.el('div', { className: 'ht-c ht-e', 'data-pair': `${a}|${b}`, title: `${a} · ${b}` }));
          return;
        }
        const v = Number(c.value);
        const strength = Math.min(1, Math.abs(v));
        const node = HT.el('div', {
          className: `ht-c ${v < 0 ? 'ht-neg' : 'ht-pos'}${strength >= 0.55 ? ' ht-strong' : ''}${c.flag ? ' ht-flag' : ''}`,
          'data-pair': `${a}|${b}`, 'data-flag': c.flag ? 'true' : null, title: `${a} · ${b} · ${c.text}`,
          css: { '--a': (strength * 88).toFixed(1) } }, [c.cited ? HT.components.cited(c.text, c.cited) : HT.el('span', { text: c.text })]);
        if (c.cited) node.firstChild.classList.add('ht-corr-v');
        items.push(node);
      });
    });
    items.push(HT.el('div', { 'aria-hidden': 'true' }));
    order.forEach(b => items.push(HT.el('div', { className: 'ht-ch', 'aria-hidden': 'true', title: b, text: b })));
    const chart = HT.el('div', { className: `ht-corr${n > DENSE ? ' ht-dense' : ''}`, 'data-chart': 'correlation',
      css: { '--n': String(n) } }, items);
    return HT.components.figure(container, { title, chart, showTitle: false, legend, columns, rows, tools });
  }

  HT.components.corr = corr;
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
