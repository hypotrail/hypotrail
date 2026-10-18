'use strict';
// Local store tests (scope U, WP-U5): the globalState schema and limits of
// COMPANION-ADVANCED §10 (lib/localstore.js). The Memento is the fake of test/fake-vscode.js.

const test = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('crypto');
const { memento } = require('./fake-vscode');
const store = require('../lib/localstore');

const STUDY = '/studies/bank marketing "demo"';
const OTHER = '/studies/auto mpg';

function assertWhitelisted(m) {
  assert.ok(m.updates.length > 0);
  for (const u of m.updates) {
    assert.ok(store.ALLOWED_KEYS.includes(u.key), `globalState.update(${u.key})`);
    assert.equal(store.invalidReason(u.key, u.value), null, `${u.key}: ${JSON.stringify(u.value)}`);
  }
}

test('§10: the store updates only the three learning keys, with values that pass their schema', async () => {
  const m = memento();
  const s = store.createStore(m, STUDY);
  await s.markSeen('binary:train_eda');
  await s.markSeen('term:base_rate');
  await s.setPrediction('binary.train_eda.rare', 'rare');
  await s.setPrefs({ hideCards: true });
  await s.resetPredictions();
  await s.setPrediction('binary.policy.beats_baseline', 'not_sure');
  assertWhitelisted(m);
  assert.deepEqual(store.ALLOWED_KEYS, ['hypotrail.learn.prefs', 'hypotrail.learn.seen', 'hypotrail.learn.predictions']);
  assert.deepEqual(m.keys().sort(), ['hypotrail.learn.predictions', 'hypotrail.learn.prefs', 'hypotrail.learn.seen']);
});

test('§10: no path, word, revision, proposal or result id is stored; the study key is a hash prefix', async () => {
  const m = memento();
  const s = store.createStore(m, STUDY);
  await s.markSeen('binary:policy');
  await s.setPrediction('binary.train_eda.rare', 'common');
  const dump = JSON.stringify(m.keys().map(k => m.get(k)));
  assert.ok(!dump.includes('studies') && !dump.includes('bank marketing'), dump);
  const key = crypto.createHash('sha256').update(STUDY).digest('hex').slice(0, 16);
  assert.equal(store.studyKey(STUDY), key);
  assert.deepEqual(Object.keys(m.get('hypotrail.learn.predictions')), [key]);
  for (const bad of ['p_5', 'a'.repeat(64), '/studies/x', 'binary:Train', 'policy', 'regression:', 'binary:train eda']) {
    await assert.rejects(s.markSeen(bad), /card id/, bad);
  }
  await assert.rejects(s.setPrediction('binary.train_eda.rare', 'Rare <b>'), /choice id/);
  await assert.rejects(s.setPrediction('Q 1', 'rare'), /question id/);
  await assert.rejects(s.setPrefs({ hideCards: true, words: 'yes' }), /hideCards only/);
  await assert.rejects(s.setPrefs({ hideCards: 'yes' }), /boolean/);
  assert.equal(store.invalidReason('hypotrail.learn.words', {}), 'hypotrail.learn.words is not a learning-layer key');
  assert.match(store.invalidReason(store.KEYS.seen, { 'binary:x': 100 }), /out of range/);
  assert.match(store.invalidReason(store.KEYS.predictions, { [key]: { q: 'rare words here' } }), /choice id/);
});

test('§10 limits: a count stops at 99, at most 500 card ids, at most 50 studies (oldest removed first)', async () => {
  const m = memento();
  const s = store.createStore(m, STUDY);
  for (let i = 0; i < 105; i += 1) await s.markSeen('binary:train_eda');
  assert.equal(m.get(store.KEYS.seen)['binary:train_eda'], 99);
  for (let i = 0; i < 510; i += 1) await s.markSeen(`term:t${i}`);
  const seen = m.get(store.KEYS.seen);
  assert.equal(Object.keys(seen).length, 500);
  assert.ok(!('binary:train_eda' in seen) && !('term:t9' in seen) && 'term:t10' in seen && 'term:t509' in seen, 'oldest ids dropped');
  for (let i = 0; i < 55; i += 1) await store.createStore(m, `/studies/s${i}`).setPrediction('binary.train_eda.rare', 'rare');
  const all = m.get(store.KEYS.predictions);
  assert.equal(Object.keys(all).length, 50);
  assert.ok(!(store.studyKey('/studies/s0') in all) && !(store.studyKey('/studies/s4') in all) && store.studyKey('/studies/s5') in all);
  // Answering again moves a study to the most recent end.
  await store.createStore(m, '/studies/s5').setPrediction('binary.policy.beats_baseline', 'yes');
  await store.createStore(m, '/studies/new').setPrediction('binary.train_eda.rare', 'rare');
  const after = m.get(store.KEYS.predictions);
  assert.ok(store.studyKey('/studies/s5') in after && !(store.studyKey('/studies/s6') in after));
  assertWhitelisted(m);
});

test('learn_state is per study; a reset clears this study only; a foreign stored value is ignored', async () => {
  const m = memento();
  const a = store.createStore(m, STUDY);
  const b = store.createStore(m, OTHER);
  await a.setPrediction('binary.train_eda.rare', 'rare');
  await b.setPrediction('regression.models.sign', 'too_low');
  assert.deepEqual(a.state().predictions, { 'binary.train_eda.rare': 'rare' });
  assert.deepEqual(b.state().predictions, { 'regression.models.sign': 'too_low' });
  assert.deepEqual(await a.resetPredictions(), { prefs: { hideCards: false }, seen: {}, predictions: {} });
  assert.deepEqual(b.state().predictions, { 'regression.models.sign': 'too_low' });
  await m.update(store.KEYS.seen, { '/etc/passwd': 1 });
  assert.deepEqual(a.state().seen, {}, 'an invalid stored value reads as empty');
  assert.deepEqual(store.createStore(null, STUDY).state(), { prefs: { hideCards: false }, seen: {}, predictions: {} });
});
