// Segments (CLI-CONTRACT-COMPANION §5, COMPANION-ADVANCED §9): engine text with cited
// numbers. A segment {text} is a text node; {text, resultId, path, value, format} is a
// <data> element with the result id, so a number in the panel is traced like one in the
// report. Frozen by WP-0: segments(container, segments) -> container.
(function (HT) {
  'use strict';

  function segments(container, items) {
    const node = container || HT.el('span');
    for (const s of items || []) {
      if (!s || typeof s.text !== 'string') continue;
      node.appendChild(typeof s.resultId === 'string'
        ? HT.components.cited(s.text, { resultId: s.resultId, path: s.path, value: s.value })
        : document.createTextNode(s.text));
    }
    return node;
  }

  HT.components.segments = segments;
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
