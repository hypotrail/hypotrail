'use strict';
// Review 2026-10-24 (panel minor items): the question "Run another chart" states before a
// per-column chart runs is the question of the card that run adds to the gallery. In English
// it is the engine's own question (mlkit/study/eda.py `question`), checked here against every
// per-column result of the captured engine payloads; under cross-validation the engine words
// it for the development rows (eda.py `development_words`), and so does the panel's `cv`
// variant, in English and in French, for both tasks.

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');

const MEDIA = path.join(__dirname, '..', 'media');
const CAPTURED = path.join(__dirname, 'fixtures', 'captured');
const PER_COLUMN = ['eda.distribution', 'eda.rate_by', 'eda.mean_by'];

function load() {
  const saved = globalThis.Hypotrail;
  globalThis.Hypotrail = { copy: {}, format: { number: x => String(x) } };
  try {
    for (const f of [path.join(MEDIA, 'copy', 'eda.js'), path.join(MEDIA, 'copy-fr', 'eda.js')]) {
      delete require.cache[require.resolve(f)];
      require(f);
    }
    return { en: globalThis.Hypotrail.copy.eda, fr: globalThis.Hypotrail.copyFr.eda };
  } finally {
    globalThis.Hypotrail = saved;
  }
}

/** The per-column results of a captured evidence payload: [task, activity, column, question]. */
function perColumn(name) {
  const p = JSON.parse(fs.readFileSync(path.join(CAPTURED, `${name}.json`), 'utf8')).payload;
  return p.results.filter(r => PER_COLUMN.includes(r.activity) && r.values && r.values.question)
    .map(r => [r.activity, r.params.column, r.values.question]);
}

const development = q => q.replace('the training rows', 'the development rows').replace('training rows', 'development rows');

test('English request questions are the engine questions of the captured per-column results', () => {
  const { en } = load();
  const cases = [['binary', perColumn('evidence.binary')], ['regression', perColumn('evidence.regression')]];
  let n = 0;
  for (const [task, rows] of cases) {
    assert.ok(rows.some(r => r[0] === 'eda.distribution'), task);
    assert.ok(rows.some(r => r[0] !== 'eda.distribution'), task);
    for (const [activity, column, question] of rows) {
      assert.equal(en[task].requestQuestion(activity, column), question, `${task} ${activity} ${column}`);
      // The cross-validated variant: the engine's rewording of the same question.
      assert.equal(en[task].cv.requestQuestion(activity, column), development(question), `${task} cv ${activity} ${column}`);
      n += 1;
    }
  }
  assert.ok(n >= 6);
});

test('Cross-validated request questions never name the training rows, in English and in French', () => {
  const { en, fr } = load();
  for (const task of ['binary', 'regression']) {
    const by = task === 'binary' ? 'eda.rate_by' : 'eda.mean_by';
    for (const activity of ['eda.distribution', by]) {
      assert.doesNotMatch(en[task].cv.requestQuestion(activity, 'age'), /training/);
      assert.doesNotMatch(fr[task].cv.requestQuestion(activity, 'age'), /entraînement/);
    }
    assert.match(en[task].cv.requestQuestion('eda.distribution', 'age'), /development rows/);
    assert.match(fr[task].cv.requestQuestion('eda.distribution', 'age'), /lignes de développement/);
    assert.match(fr[task].requestQuestion('eda.distribution', 'age'), /lignes d'entraînement/);
    // The same question in both languages: the French names the column and asks one question.
    for (const activity of ['eda.distribution', by]) {
      for (const variant of [fr[task], fr[task].cv]) {
        const q = variant.requestQuestion(activity, 'age');
        assert.ok(q.includes('age') && q.endsWith(' ?') && q.split('?').length === 2, q);
      }
    }
  }
});
