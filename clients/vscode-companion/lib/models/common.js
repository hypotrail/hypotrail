'use strict';
// Shared helpers of the model functions (COMPANION-ADVANCED §9). A model is a pure
// projection of one CLI payload into plain values (strings, numbers, booleans, arrays,
// null, objects). Unknown payload keys are ignored; a missing key becomes null or [].
// Each model function throws ModelError for a payload of the wrong schema.
//
// Frozen by WP-0. Every lib/models/<name>.js exports its `to<Name>Model` function and
// `FIXTURES`, the fixture names (test/fixtures/<name>.json) it must accept; the protocol
// round-trip test discovers both.

class ModelError extends Error {}

const str = x => (typeof x === 'string' ? x : '');
const strOrNull = x => (typeof x === 'string' ? x : null);
const list = x => (Array.isArray(x) ? x : []);
const obj = x => (x && typeof x === 'object' && !Array.isArray(x) ? x : {});
const int = x => (Number.isInteger(x) ? x : null);
const num = x => (typeof x === 'number' && Number.isFinite(x) ? x : null);
const bool = x => x === true;

function showValue(value) {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value;
  try { return JSON.stringify(value); } catch (_) { return String(value); }
}

/** Throw ModelError unless `payload` is an `ok` document of `schema`. */
function expectSchema(payload, schema) {
  if (!payload || typeof payload !== 'object' || payload.schema !== schema || payload.ok !== true) {
    throw new ModelError(`The CLI did not return a ${schema} document.`);
  }
  return payload;
}

/**
 * Segments (CLI-CONTRACT-COMPANION §5): `{text}` or a cited number
 * `{text, resultId, path, value, format}`. Anything else is dropped.
 */
function segments(raw) {
  const items = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw.segments : raw;
  return list(items).filter(s => s && typeof s.text === 'string').map(s => (typeof s.result_id === 'string'
    ? { text: s.text, resultId: s.result_id, path: str(s.path), value: num(s.value), format: strOrNull(s.format) }
    : { text: s.text }));
}

/** A JSON-safe deep copy (models carry plain values only). */
function plain(value) {
  return value === undefined ? null : JSON.parse(JSON.stringify(value));
}

module.exports = { ModelError, str, strOrNull, list, obj, int, num, bool, showValue, expectSchema, segments, plain };
