// Shared components (COMPANION-ADVANCED §13 "Charts"): the values table, and the figure
// wrapper every chart uses (an accessible name, a "Show values" toggle, the table).
// Frozen by WP-0:
//   valuesTable(container, {columns: [{key, label}], rows: [{<key>: text | {text, cited}}], caption})
//   figure(container, {title, chart, columns, rows, caption?})   (used by the charts)
// A cell `{text, cited: {resultId, path, value}}` renders as a cited <data> element.
(function (HT) {
  'use strict';

  function cell(value) {
    if (value && typeof value === 'object' && typeof value.text === 'string') {
      return value.cited ? HT.components.cited(value.text, value.cited) : document.createTextNode(value.text);
    }
    return document.createTextNode(value === null || value === undefined ? '' : String(value));
  }

  /** The cited-number convention of the report: <data value data-result-id data-path title>. */
  function cited(text, c) {
    const rid = String(c.resultId || '');
    return HT.el('data', { value: c.value === null || c.value === undefined ? '' : String(c.value), 'data-result-id': rid,
      'data-path': String(c.path || ''), 'data-value': c.value === null || c.value === undefined ? null : String(c.value),
      title: `result ${rid.slice(0, 8)}... · ${c.path || ''}`, text });
  }

  function valuesTable(container, { columns, rows, caption }) {
    const table = HT.el('table', { className: 'ht-values' }, [
      caption ? HT.el('caption', { text: caption }) : null,
      HT.el('thead', {}, [HT.el('tr', {}, columns.map(c => HT.el('th', { scope: 'col', text: c.label })))]),
      HT.el('tbody', {}, rows.map(r => HT.el('tr', {}, columns.map(c => HT.el('td', {}, [cell(r[c.key])]))))),
    ]);
    if (container) container.appendChild(table);
    return table;
  }

  let figures = 0;
  /** A chart with its accessible name and its "Show values" alternative. */
  function figure(container, { title, chart, columns, rows, caption }) {
    figures += 1;
    const id = `ht-values-${figures}`;
    chart.setAttribute('role', 'img');
    chart.setAttribute('aria-label', title);
    const table = valuesTable(null, { columns, rows, caption: caption || title });
    const wrap = HT.el('div', { id, hidden: true }, [table]);
    const c = HT.copy.core;
    const toggle = HT.el('button', { type: 'button', className: 'ht-link', 'aria-expanded': 'false', 'aria-controls': id,
      text: c.showValues });
    toggle.addEventListener('click', () => {
      const open = wrap.hidden;
      wrap.hidden = !open;
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      toggle.textContent = open ? c.hideValues : c.showValues;
    });
    const node = HT.el('figure', { className: 'ht-figure' }, [HT.el('figcaption', { text: title }), chart, toggle, wrap]);
    if (container) container.appendChild(node);
    return node;
  }

  Object.assign(HT.components, { valuesTable, figure, cited });
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
