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
      // v0.3 (WP-E2): provenance on hover only; never underlined.
      title: `${HT.copy.core.sourceWord || 'Source'} · ${rid.slice(0, 6)} · ${c.path || ''}`, text });
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
  /**
   * A chart with its accessible name, its legend and its "Show values" alternative.
   * v0.3 (WP-E2): `chart` is an HTML grid (bars, histogram, matrix) or an SVG curve. An SVG
   * keeps one unit per CSS pixel (width = its viewBox width) and never grows past its
   * container (max-width: 100%), so a chart never scrolls sideways and its text is never
   * scaled up. `showTitle: false` keeps the title as the accessible name only (the card's
   * question is the one visible title, R17). `legend` is a list of [swatch, text] pairs;
   * `tools` are extra nodes next to the "Show values" toggle.
   */
  function figure(container, { title, chart, columns, rows, caption, legend = [], showTitle = true, tools = [] }) {
    figures += 1;
    const id = `ht-values-${figures}`;
    chart.setAttribute('role', 'img');
    chart.setAttribute('aria-label', title);
    const box = String(chart.getAttribute('viewBox') || '').split(/\s+/).map(Number);
    if (chart.namespaceURI === HT.SVG_NS && box.length === 4 && box.every(Number.isFinite)) {
      chart.setAttribute('width', String(box[2]));
      chart.setAttribute('height', String(box[3]));
    }
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
    const node = HT.el('figure', { className: 'ht-figure' }, [
      HT.el('figcaption', { className: showTitle ? null : 'sr-only', text: title }),
      chart,
      legend.length ? HT.el('div', { className: 'ht-legend', 'aria-hidden': 'true' },
        legend.map(([kind, text]) => HT.el('span', {}, [HT.el('i', { className: kind }), text]))) : null,
      HT.el('div', { className: 'ht-figure-tools' }, [toggle, ...tools]), wrap]);
    if (container) container.appendChild(node);
    return node;
  }

  /**
   * v0.3 (WP-E2): an SVG chart drawn at the width of its container and again when that
   * width changes (ResizeObserver), so a curve is fluid while one SVG unit stays one CSS
   * pixel. `draw(width)` returns the <svg>; the first drawing uses `initial`. Returns the
   * host element; the figure's role and name are copied to each new drawing.
   */
  function fluid(draw, initial) {
    const host = HT.el('div', { className: 'ht-fluid' });
    let width = initial;
    let current = draw(width);
    host.appendChild(current);
    if (typeof ResizeObserver === 'function') {
      const observer = new ResizeObserver(entries => {
        const w = Math.floor(entries[0].contentRect.width);
        if (!w || Math.abs(Math.min(720, Math.max(240, w)) - width) < 8) return;
        width = Math.max(240, Math.min(720, w));
        const next = draw(width);
        for (const a of ['role', 'aria-label']) if (current.hasAttribute(a)) next.setAttribute(a, current.getAttribute(a));
        const box = String(next.getAttribute('viewBox') || '').split(/\s+/).map(Number);
        if (box.length === 4) { next.setAttribute('width', String(box[2])); next.setAttribute('height', String(box[3])); }
        current.replaceWith(next);
        current = next;
      });
      observer.observe(host);
    }
    return host;
  }

  /**
   * An estimate, in SVG viewBox units, of the width of the longest of `texts` in the 11 px
   * chart font (6.2 units per character), bounded to [min, max]: geometry only (WP-I).
   */
  function textWidth(texts, min, max) {
    const longest = Math.max(0, ...(texts || []).map(t => String(t === null || t === undefined ? '' : t).length));
    return Math.max(min, Math.min(max, Math.ceil(longest * 6.2)));
  }

  Object.assign(HT.components, { valuesTable, figure, cited, textWidth, fluid });
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
