'use strict';
// Owner session 2026-10-26, lot L8 (R6): the preparation's rare grouping is one minimum for
// every categorical column (an integer, as before) or one minimum per column ({column: n}).
// The panel's decision line says it per column, in English and in French; the integer keeps
// its words.

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');

const MEDIA = path.join(__dirname, '..', 'media');

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
    return { en: globalThis.Hypotrail.copy.junior, fr: globalThis.Hypotrail.copyFr.junior };
  } finally {
    globalThis.Hypotrail = saved;
  }
}

const base = { missing: 'none', caps: {}, log_transform: [] };

test('a per-column grouping is said per column, in both languages', () => {
  const { en, fr } = load();
  const value = { ...base, rare_category_min_rows: { company: 50, agent: 30, meal: 0 } };
  const english = en.value('preprocessing', value, 'binary');
  assert.match(english, /categories of agent under 30 rows grouped, categories of company under 50 rows grouped/);
  assert.doesNotMatch(english, /meal/);
  const french = fr.value('preprocessing', value, 'binary');
  assert.match(french, /catégories de agent de moins de 30 lignes regroupées, catégories de company de moins de 50 lignes regroupées/);
  assert.doesNotMatch(french, /meal/);
});

test('an integer keeps its words, and a mapping that groups nothing says nothing', () => {
  const { en, fr } = load();
  assert.match(en.value('preprocessing', { ...base, rare_category_min_rows: 30 }, 'binary'),
    /categories under 30 rows grouped/);
  assert.match(fr.value('preprocessing', { ...base, rare_category_min_rows: 30 }, 'binary'),
    /catégories de moins de 30 lignes regroupées/);
  for (const rare of [0, {}, { meal: 0 }]) {
    assert.doesNotMatch(en.value('preprocessing', { ...base, rare_category_min_rows: rare }, 'binary'),
      /grouped/);
    assert.doesNotMatch(fr.value('preprocessing', { ...base, rare_category_min_rows: rare }, 'binary'),
      /regroupées/);
  }
});
