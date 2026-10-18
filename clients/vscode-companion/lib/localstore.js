'use strict';
// The learning layer's local store (COMPANION-ADVANCED §10). It lives in the extension's
// `context.globalState`, under exactly three keys, and nowhere else:
//
//   hypotrail.learn.prefs        {hideCards: bool}
//   hypotrail.learn.seen         {cardId: count <= 99}                    (at most 500 ids)
//   hypotrail.learn.predictions  {studyKey: {questionId: choiceId}}      (at most 50 studies)
//
// It may hold learning-layer preferences, seen cards, and prediction answers. It must not
// hold study values, words, revisions, proposal or result ids, or paths: a `cardId` is
// `<task>:<step id>` or `term:<id>`, a `studyKey` is the first 16 hexadecimal characters of
// the SHA-256 of the absolute study path (the path itself is never stored), and a choice is
// a choice id of `explain.predictions`. A prediction answer is never sent to the CLI, the
// chat, or the study (LE-1): this module is the only place it goes.
//
// Owned by WP-U5. Pure apart from the Memento it is given; test/localstore.test.js checks
// the key whitelist, the schemas, and the limits.

const crypto = require('crypto');

const KEYS = Object.freeze({
  prefs: 'hypotrail.learn.prefs',
  seen: 'hypotrail.learn.seen',
  predictions: 'hypotrail.learn.predictions',
});
const ALLOWED_KEYS = Object.freeze(Object.values(KEYS));
const MAX_SEEN_COUNT = 99;
const MAX_SEEN_IDS = 500;
const MAX_STUDIES = 50;
const MAX_ANSWERS = 100;

const CARD_ID = /^(binary|regression|term):[a-z][a-z0-9_]{0,63}$/;
const QUESTION_ID = /^[a-z][a-z0-9_.:-]{0,99}$/;
const CHOICE_ID = /^[a-z0-9_]{1,40}$/;
const STUDY_KEY = /^[0-9a-f]{16}$/;

const isPlain = x => Boolean(x) && typeof x === 'object' && !Array.isArray(x);

/** The study key of an absolute study path (the path is never stored). */
function studyKey(studyDir) {
  return crypto.createHash('sha256').update(String(studyDir), 'utf8').digest('hex').slice(0, 16);
}

/** null when `value` is a valid value of the globalState key `key`, else the reason. */
function invalidReason(key, value) {
  if (!ALLOWED_KEYS.includes(key)) return `${key} is not a learning-layer key`;
  if (!isPlain(value)) return `${key} holds an object`;
  if (key === KEYS.prefs) {
    const extra = Object.keys(value).filter(k => k !== 'hideCards');
    if (extra.length) return `prefs holds hideCards only, not ${extra.join(', ')}`;
    return value.hideCards === undefined || typeof value.hideCards === 'boolean' ? null : 'hideCards is a boolean';
  }
  if (key === KEYS.seen) {
    const ids = Object.keys(value);
    if (ids.length > MAX_SEEN_IDS) return `seen holds at most ${MAX_SEEN_IDS} ids`;
    for (const id of ids) {
      if (!CARD_ID.test(id)) return `seen: ${id} is not a card id`;
      const n = value[id];
      if (!Number.isInteger(n) || n < 1 || n > MAX_SEEN_COUNT) return `seen: ${id} has a count out of range`;
    }
    return null;
  }
  const studies = Object.keys(value);
  if (studies.length > MAX_STUDIES) return `predictions hold at most ${MAX_STUDIES} studies`;
  for (const s of studies) {
    if (!STUDY_KEY.test(s)) return `predictions: ${s} is not a study key`;
    const answers = value[s];
    if (!isPlain(answers)) return `predictions: ${s} holds an object`;
    if (Object.keys(answers).length > MAX_ANSWERS) return `predictions: ${s} holds too many answers`;
    for (const [q, c] of Object.entries(answers)) {
      if (!QUESTION_ID.test(q)) return `predictions: ${q} is not a question id`;
      if (typeof c !== 'string' || !CHOICE_ID.test(c)) return `predictions: ${q} has no choice id`;
    }
  }
  return null;
}

function read(memento, key) {
  let value = null;
  try { value = memento && typeof memento.get === 'function' ? memento.get(key, null) : null; } catch (_) { value = null; }
  // A value written by an older or a foreign version is ignored, never repaired in place.
  return invalidReason(key, value) === null ? JSON.parse(JSON.stringify(value)) : {};
}

async function write(memento, key, value) {
  const why = invalidReason(key, value);
  if (why) throw new Error(`refusing to store ${key}: ${why}`);
  if (memento && typeof memento.update === 'function') await memento.update(key, value);
}

/**
 * The store of one study: `state()` is the `learn_state` message body for this study
 * only; each setter validates, applies the limits, writes one key, and returns `state()`.
 * `memento` is `context.globalState` (null: an empty store that never writes).
 */
function createStore(memento, studyDir) {
  const key = studyKey(studyDir);

  function state() {
    const prefs = read(memento, KEYS.prefs);
    const predictions = read(memento, KEYS.predictions);
    return { prefs: prefs.hideCards === true ? { hideCards: true } : { hideCards: false },
      seen: read(memento, KEYS.seen), predictions: predictions[key] || {} };
  }

  async function markSeen(cardId) {
    if (!CARD_ID.test(cardId)) throw new Error(`${cardId} is not a card id`);
    const seen = read(memento, KEYS.seen);
    const count = Math.min(MAX_SEEN_COUNT, (seen[cardId] || 0) + 1);
    delete seen[cardId];
    seen[cardId] = count;                       // most recent last
    const ids = Object.keys(seen);
    for (const old of ids.slice(0, Math.max(0, ids.length - MAX_SEEN_IDS))) delete seen[old];
    await write(memento, KEYS.seen, seen);
    return state();
  }

  async function setPrediction(questionId, choiceId) {
    if (!QUESTION_ID.test(questionId)) throw new Error(`${questionId} is not a question id`);
    if (!CHOICE_ID.test(choiceId)) throw new Error(`${choiceId} is not a choice id`);
    const all = read(memento, KEYS.predictions);
    const mine = { ...(all[key] || {}), [questionId]: choiceId };
    if (Object.keys(mine).length > MAX_ANSWERS) throw new Error('too many answers for one study');
    delete all[key];
    all[key] = mine;                            // most recent study last
    const studies = Object.keys(all);
    for (const old of studies.slice(0, Math.max(0, studies.length - MAX_STUDIES))) delete all[old];
    await write(memento, KEYS.predictions, all);
    return state();
  }

  async function resetPredictions() {
    const all = read(memento, KEYS.predictions);
    if (all[key]) {
      delete all[key];
      await write(memento, KEYS.predictions, all);
    }
    return state();
  }

  async function setPrefs(prefs) {
    const why = invalidReason(KEYS.prefs, prefs);
    if (why) throw new Error(why);
    const next = { ...read(memento, KEYS.prefs) };
    if (prefs.hideCards !== undefined) next.hideCards = prefs.hideCards;
    await write(memento, KEYS.prefs, next);
    return state();
  }

  return { studyKey: key, state, markSeen, setPrediction, resetPredictions, setPrefs };
}

module.exports = { createStore, studyKey, invalidReason, KEYS, ALLOWED_KEYS, MAX_SEEN_COUNT, MAX_SEEN_IDS, MAX_STUDIES,
  CARD_ID, QUESTION_ID, CHOICE_ID };
