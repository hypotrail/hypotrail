'use strict';
// The webview document. Its scripts and styles are concatenated in a fixed order and
// inlined under one per-load nonce, with the v0 Content-Security-Policy unchanged: no
// remote resource, no inline handler, no eval, no network connection, no build step.
// Study data never enters this string; it arrives by postMessage and is set as text.
//
// Frozen by WP-0 (docs/plans/COMPANION-ADVANCED-PLAN.md §2.2 item 5). Order:
//   CSS: media/css/tokens.css, media/css/core.css, then the other media/css/*.css (a-z);
//   JS:  media/protocol.js, media/format.js, lib/models/page.js (the page model, ADR 0004 d13:
//        one pure function shared with the extension's tests), media/core.js, media/components/*.js (a-z),
//        media/copy/core.js, the other media/copy/*.js (a-z), media/copy-fr/*.js (a-z; v0.3
//        WP-E2, the French translation of the same keys), media/terms.js (if present),
//        media/views/*.js (a-z), then `Hypotrail.start();`.
// A file that contains `</script` or `</style` is refused.

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const MEDIA = path.join(__dirname, '..', 'media');
// The page model is a pure function of lib/models/ that the webview runs too (relative to media/).
const PAGE_MODEL = '../lib/models/page.js';

function csp(nonce) {
  return [
    "default-src 'none'",
    `style-src 'nonce-${nonce}'`,
    `script-src 'nonce-${nonce}'`,
    "img-src 'none'",
    "font-src 'none'",
    "connect-src 'none'",
    "frame-src 'none'",
    "form-action 'none'",
    "base-uri 'none'",
  ].join('; ');
}

function newNonce() {
  return crypto.randomBytes(18).toString('base64').replace(/[^A-Za-z0-9]/g, '');
}

function listDir(dir, ext) {
  try {
    return fs.readdirSync(path.join(MEDIA, dir)).filter(f => f.endsWith(ext)).sort().map(f => `${dir}/${f}`);
  } catch (_) {
    return [];
  }
}

/** The media files of the document, in their fixed order: {css: [...], js: [...]}. */
function files(media = MEDIA) {
  const has = rel => fs.existsSync(path.join(media, rel));
  const css = ['css/tokens.css', 'css/core.css', ...listDir('css', '.css').filter(f => f !== 'css/tokens.css' && f !== 'css/core.css')];
  const js = ['protocol.js', 'format.js', PAGE_MODEL, 'core.js', ...listDir('components', '.js'), 'copy/core.js',
    ...listDir('copy', '.js').filter(f => f !== 'copy/core.js'), ...listDir('copy-fr', '.js'),
    ...(has('terms.js') ? ['terms.js'] : []),
    ...listDir('views', '.js')];
  return { css, js };
}

function read(rel, kind) {
  const text = fs.readFileSync(path.join(MEDIA, rel), 'utf8');
  if (text.includes('</script') || text.includes('</style')) throw new Error(`media must not close its own element (${rel})`);
  return `/* --- ${rel.startsWith('../') ? rel.slice(3) : `media/${rel}`} (${kind}) --- */\n${text}`;
}

function renderHtml({ nonce = newNonce() } = {}) {
  if (!/^[A-Za-z0-9]{16,}$/.test(nonce)) throw new Error('invalid nonce');
  const list = files();
  const style = list.css.map(f => read(f, 'css')).join('\n');
  const script = `${list.js.map(f => read(f, 'js')).join('\n')}\nglobalThis.Hypotrail.start();\n`;
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="${csp(nonce)}">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hypotrail study</title>
<style nonce="${nonce}">
${style}
</style>
</head>
<body>
<div id="app"></div>
<script nonce="${nonce}">
${script}
</script>
</body>
</html>
`;
}

module.exports = { renderHtml, csp, newNonce, files };

if (require.main === module) {
  // Used by the browser tests: print the document for a fixed nonce.
  process.stdout.write(renderHtml({ nonce: process.argv[2] || newNonce() }));
}
