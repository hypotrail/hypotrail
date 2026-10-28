'use strict';
// Review round 3: every limit the engine emits for a study whose development rows hold
// delayed labels (review-v1, `delayed_labels_excluded`) is a caveat in the panel's one
// vocabulary of severity, with the panel's own wording in English and French (the term
// first). Before, it had no severity and read as mere context.

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');

const MEDIA = path.join(__dirname, '..', 'media');

function load() {
  const saved = globalThis.Hypotrail;
  globalThis.Hypotrail = { copy: {}, format: { number: x => String(x) } };
  try {
    for (const f of [path.join(MEDIA, 'copy', 'junior.js'), path.join(MEDIA, 'copy-fr', 'junior.js')]) {
      delete require.cache[require.resolve(f)];
      require(f);
    }
    return { en: globalThis.Hypotrail.copy.junior, fr: globalThis.Hypotrail.copyFr.junior };
  } finally {
    globalThis.Hypotrail = saved;
  }
}

test('delayed_labels_excluded is a caveat, worded in English and French, term first', () => {
  const { en, fr } = load();
  assert.equal(en.SEVERITY.delayed_labels_excluded, 'caveat');
  assert.ok(en.SEVERITY_ORDER.indexOf('caveat') < en.SEVERITY_ORDER.indexOf('context'));
  assert.match(en.limitText.delayed_labels_excluded, /^A delayed label is an outcome/);
  assert.match(fr.limitText.delayed_labels_excluded, /^Une étiquette tardive est un résultat/);
  // The panel's wording carries no figure (the engine's junior text gives this study's).
  assert.doesNotMatch(en.limitText.delayed_labels_excluded, /\d/);
  assert.doesNotMatch(fr.limitText.delayed_labels_excluded, /\d/);
});
