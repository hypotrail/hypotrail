// Minimal safe Markdown rendering with textContent, no raw HTML or active links.
(function (root) {
  'use strict';
  function inline(text) {
    // Render links as labels and addresses, never clickable elements.
    const source = String(text).replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, '$1 ($2)');
    const out = [], pattern = /\*\*([^*]+)\*\*|__([^_]+)__|`([^`]+)`|\*([^*\s][^*]*)\*|_([^_\s][^_]*)_/g;
    let last = 0, match;
    while ((match = pattern.exec(source))) {
      if (match.index > last) out.push({ type: 'text', text: source.slice(last, match.index) });
      if (match[1] != null || match[2] != null) out.push({ type: 'strong', text: match[1] ?? match[2] });
      else if (match[3] != null) out.push({ type: 'code', text: match[3] });
      else out.push({ type: 'em', text: match[4] ?? match[5] });
      last = pattern.lastIndex;
    }
    if (last < source.length) out.push({ type: 'text', text: source.slice(last) });
    return out;
  }
  function parse(src) {
    const blocks = []; let para = [], list = null;
    const endPara = () => { if (para.length) { blocks.push({ type: 'p', inlines: inline(para.join(' ')) }); para = []; } };
    const endList = () => { if (list) { blocks.push(list); list = null; } };
    for (const raw of String(src).replace(/\r\n?/g, '\n').split('\n')) {
      const line = raw.trim(); let m;
      if (!line) { endPara(); endList(); continue; }
      if ((m = /^#{1,6}\s+(.*)$/.exec(line))) { endPara(); endList(); blocks.push({ type: 'h', inlines: inline(m[1]) }); continue; }
      if ((m = /^(?:[-*+•])\s+(.*)$/.exec(line)) || (m = /^\d+[.)]\s+(.*)$/.exec(line))) {
        const type = /^\d/.test(line) ? 'ol' : 'ul';
        endPara(); if (!list || list.type !== type) { endList(); list = { type, items: [] }; }
        list.items.push(inline(m[1])); continue;
      }
      if (/^```/.test(line) || /^(-{3,}|\*{3,})$/.test(line)) continue;
      if (list) { list.items[list.items.length - 1].push(...inline(' ' + line)); continue; }
      para.push(line);
    }
    endPara(); endList();
    return blocks;
  }
  function render(container, src) {
    const doc = container.ownerDocument;
    const fill = (node, parts) => { for (const part of parts) { const el = part.type === 'text' ? doc.createTextNode(part.text) : doc.createElement(part.type === 'strong' ? 'strong' : part.type === 'em' ? 'em' : 'code'); if (part.type !== 'text') el.textContent = part.text; node.append(el); } return node; };
    container.replaceChildren();
    for (const block of parse(src)) {
      if (block.type === 'p') container.append(fill(doc.createElement('p'), block.inlines));
      else if (block.type === 'h') container.append(fill(doc.createElement('h4'), block.inlines));
      else { const list = doc.createElement(block.type); for (const item of block.items) list.append(fill(doc.createElement('li'), item)); container.append(list); }
    }
  }
  root.osmlMarkdown = { parse, inline, render };
  if (typeof module !== 'undefined' && module.exports) module.exports = { parse, inline };
})(typeof window !== 'undefined' ? window : globalThis);
