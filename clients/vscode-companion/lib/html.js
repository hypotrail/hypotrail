'use strict';
// The webview document. Its script and style are inlined with a per-load nonce under a
// strict Content-Security-Policy: no remote resource, no inline handler, no eval, no
// network connection. Study data never enters this string; it arrives by postMessage
// and is set with textContent (media/panel.js).

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const MEDIA = path.join(__dirname, '..', 'media');

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

function renderHtml({ nonce = newNonce() } = {}) {
  if (!/^[A-Za-z0-9]{16,}$/.test(nonce)) throw new Error('invalid nonce');
  const style = fs.readFileSync(path.join(MEDIA, 'panel.css'), 'utf8');
  const script = fs.readFileSync(path.join(MEDIA, 'panel.js'), 'utf8');
  if (script.includes('</script') || style.includes('</style')) throw new Error('media must not close its own element');
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
<main id="root" aria-label="Hypotrail study panel"></main>
<script nonce="${nonce}">
${script}
</script>
</body>
</html>
`;
}

module.exports = { renderHtml, csp, newNonce };

if (require.main === module) {
  // Used by the browser test: print the document for a fixed nonce.
  process.stdout.write(renderHtml({ nonce: process.argv[2] || newNonce() }));
}
