'use strict';
// v0.3 (WP-E2, R21): the French translation of the panel's own copy. English
// (media/copy/*.js) is the source language; media/copy-fr/*.js holds the same keys in
// French. Every English key has a French counterpart of the same kind (a text, a function,
// a list of the same length, a table), except the data tables that hold no text; a French
// key without an English one is an error too. The French strings follow the English rules:
// no digit outside placeholders, no exclamation mark.

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');

const MEDIA = path.join(__dirname, '..', 'media');
// Keys of the junior table that are data or readers of recorded values, not text.
const NOT_TEXT = { junior: ['SEVERITY', 'SEVERITY_ORDER', 'GROUP_OF_KIND', 'GROUP_ORDER', 'finalTestState', 'sharePercent',
  'availability'] };
// The one string that quotes an environment variable's value (as in English).
const DIGITS_ALLOWED = ['learn.sessionLogOff'];

function load() {
  const saved = globalThis.Hypotrail;
  globalThis.Hypotrail = { copy: {}, format: { number: x => String(x) } };
  try {
    const files = dir => fs.readdirSync(path.join(MEDIA, dir)).filter(f => f.endsWith('.js')).sort()
      .map(f => path.join(MEDIA, dir, f));
    for (const f of [...files('copy'), ...files('copy-fr')]) {
      delete require.cache[require.resolve(f)];
      require(f);
    }
    return { en: globalThis.Hypotrail.copy, fr: globalThis.Hypotrail.copyFr };
  } finally {
    globalThis.Hypotrail = saved;
  }
}

const kind = v => (Array.isArray(v) ? 'array' : v === null ? 'null' : typeof v);

function compare(en, fr, where, problems) {
  if (kind(en) !== kind(fr)) { problems.push(`${where}: ${kind(en)} in English, ${kind(fr)} in French`); return; }
  if (Array.isArray(en)) {
    if (en.length !== fr.length) problems.push(`${where}: ${en.length} parts in English, ${fr.length} in French`);
    return;
  }
  if (kind(en) !== 'object') return;
  for (const k of Object.keys(en)) {
    if (!(k in fr)) problems.push(`${where}.${k}: missing in French`);
    else compare(en[k], fr[k], `${where}.${k}`, problems);
  }
  for (const k of Object.keys(fr)) if (!(k in en)) problems.push(`${where}.${k}: not an English key`);
}

test('copy (R21, LANG-2): every English key of the panel copy has its French counterpart', () => {
  const { en, fr } = load();
  assert.ok(fr, 'media/copy-fr defines Hypotrail.copyFr');
  // LANG-2: the one page's copy (media/copy/page.js) is covered like every other file.
  assert.ok(en.page && fr.page, 'media/copy/page.js and media/copy-fr/page.js');
  assert.deepEqual(Object.keys(fr).sort(), Object.keys(en).sort(), 'one French table per English one');
  const problems = [];
  for (const ns of Object.keys(en)) {
    const skip = NOT_TEXT[ns] || [];
    const e = Object.fromEntries(Object.entries(en[ns]).filter(([k]) => !skip.includes(k)));
    compare(e, fr[ns], ns, problems);
  }
  assert.deepEqual(problems, []);
});

test('copy (R21): French strings hold no digit outside placeholders and no exclamation mark', () => {
  const { fr } = load();
  const strings = [];
  const walk = (v, where) => {
    if (typeof v === 'string') strings.push([where, v]);
    else if (typeof v === 'function') {
      try { const out = v('Xa', 'Xb', 'Xc', 'Xd'); walk(out, where); } catch (_) { /* a reader of recorded values */ }
    } else if (Array.isArray(v)) v.forEach((x, i) => walk(x, `${where}.${i}`));
    else if (v && typeof v === 'object') for (const [k, x] of Object.entries(v)) walk(x, `${where}.${k}`);
  };
  for (const [ns, table] of Object.entries(fr)) walk(table, ns);
  assert.ok(strings.length > 400);
  for (const [where, s] of strings) {
    assert.doesNotMatch(s, /!/, `${where}: ${s}`);
    if (!DIGITS_ALLOWED.includes(where)) assert.doesNotMatch(s, /\d/, `${where}: ${s}`);
  }
});
