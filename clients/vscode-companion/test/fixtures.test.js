'use strict';
// Fixture tests (scope U, frozen by WP-0): every payload of test/fixtures/ has the frozen
// key lists of CLI-CONTRACT and CLI-CONTRACT-COMPANION, in emitted order
// (test/fixtures/contract-keys.json, which test_contract_keys.py checks against the
// engine's contract tests). Regression fixtures carry none of the vocabulary of a decision
// rule (INV-12), so a view scanned on them proves its own copy clean.

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const { fixture, names, DIR } = require('./fixture-cli');

const CONTRACT = JSON.parse(fs.readFileSync(path.join(DIR, 'contract-keys.json'), 'utf8'));
const INDEX = JSON.parse(fs.readFileSync(path.join(DIR, 'index.json'), 'utf8'));
const FORBIDDEN = /\b(threshold|capacity|precision|recall|positive class|policy|calling rule|selected)\b/i;

/** Every value at `selector` ("a.b[].c", "steps.*") of `value`, skipping nulls. */
function select(value, selector) {
  let nodes = [value];
  if (!selector) return nodes;
  for (const part of selector.split('.')) {
    const list = part.endsWith('[]');
    const key = list ? part.slice(0, -2) : part;
    nodes = nodes.flatMap(n => {
      if (n === null || n === undefined) return [];
      const next = key === '*' ? Object.values(n) : [n[key]];
      return list ? next.flatMap(x => (Array.isArray(x) ? x : [])) : next;
    }).filter(n => n !== null && n !== undefined);
  }
  return nodes;
}

function strings(value, out = []) {
  if (typeof value === 'string') out.push(value);
  else if (Array.isArray(value)) value.forEach(v => strings(v, out));
  else if (value && typeof value === 'object') Object.values(value).forEach(v => strings(v, out));
  return out;
}

test('every fixture is indexed, has an about block, and a known schema', () => {
  assert.deepEqual(Object.keys(INDEX).sort(), names());
  for (const name of names()) {
    const { about, payload } = fixture(name);
    assert.deepEqual(Object.keys(about), ['schema', 'task', 'exit_code', 'source', 'argv', 'note'], name);
    assert.equal(about.schema, payload.schema, name);
    assert.ok(['binary', 'regression'].includes(about.task), name);
    assert.ok(['captured', 'hand-authored'].includes(about.source), name);
    const schema = payload.schema === 'hypotrail.summary/1' && 'digest' in payload ? 'hypotrail.summary/1+digest' : payload.schema;
    assert.ok(CONTRACT.schemas[schema], `${name}: ${schema} has no frozen key list`);
    assert.equal(payload.ok === false, payload.schema === 'hypotrail.error/1', name);
  }
});

test('every fixture follows the frozen key lists, in emitted order', () => {
  let checked = 0;
  for (const name of names()) {
    const { payload } = fixture(name);
    const schema = payload.schema === 'hypotrail.summary/1' && 'digest' in payload ? 'hypotrail.summary/1+digest' : payload.schema;
    const rules = { ...CONTRACT.schemas[schema] };
    for (const [prefix, extra] of Object.entries(CONTRACT.fixtures)) if (name.startsWith(prefix)) Object.assign(rules, extra);
    for (const [selector, keys] of Object.entries(rules)) {
      for (const node of select(payload, selector)) {
        assert.deepEqual(Object.keys(node), keys, `${name} ${selector || '(top)'}`);
        checked += 1;
      }
    }
  }
  assert.ok(checked > 300, `checked ${checked} objects`);
});

test('the new schemas have a binary and a regression fixture each', () => {
  const tasks = {};
  for (const name of names()) {
    const { about } = fixture(name);
    (tasks[about.schema] = tasks[about.schema] || new Set()).add(about.task);
  }
  for (const schema of ['hypotrail.summary/1', 'hypotrail.decisions/1', 'hypotrail.preview_effects/1',
    'hypotrail.proposal_draft/1', 'hypotrail.evidence/1', 'hypotrail.explain/1']) {
    assert.deepEqual([...tasks[schema]].sort(), ['binary', 'regression'], schema);
  }
  for (const schema of ['hypotrail.export/1', 'hypotrail.handoff/1', 'hypotrail.check/1', 'hypotrail.session_report/1',
    'hypotrail.preview/1', 'hypotrail.run/1', 'hypotrail.render/1', 'hypotrail.decide/1', 'hypotrail.error/1']) {
    assert.ok(tasks[schema], schema);
  }
});

test('INV-12: regression fixtures hold none of the vocabulary of a decision rule', () => {
  for (const name of names()) {
    const { about, payload } = fixture(name);
    if (about.task !== 'regression') continue;
    for (const text of strings(payload)) assert.doesNotMatch(text, FORBIDDEN, `${name}: ${text.slice(0, 80)}`);
  }
});

test('the C1-C10 acceptance shapes the views rely on', () => {
  const ledger = fixture('evidence.binary').payload.exposure.ledger.map(r => `${r.purpose}:${r.partition}`);
  assert.deepEqual(ledger, ['structural_inspection:all', 'train_eda:train', 'train_fit:train',
    'validation_model_evaluation:validation', 'validation_policy_selection:validation'], 'EV-2: five ledger rows');
  const stale = fixture('evidence.binary').payload.results.filter(r => !r.current);
  assert.ok(stale.length && stale.every(r => r.values === null && r.headline === null), 'INV-7: no figure of a stale result');
  assert.deepEqual(fixture('preview_effects.binary.reconfirm').payload.reconfirm_required, ['conclusion'], 'DC-4');
  assert.equal(fixture('preview_effects.binary.blocked').payload.blocked[0].code, 'decision_on_hold', 'DC-2');
  assert.equal(fixture('proposal_draft.binary.unevaluated').payload.proposable, false, 'WI-3');
  assert.match(fixture('decisions.binary.injection').payload.history[0].user_words, /<img src=x onerror=alert\(1\)>/, 'DH-2');
  const history = fixture('decisions.binary').payload.history;
  assert.ok(history.some(h => h.decision_id === 'split' && h.basis === 'delegated_default'), 'DH-1 delegated split');
  assert.ok(history.some(h => h.decision_id === 'policy' && h.current === false && h.superseded_at), 'DH-1 superseded policy');
  assert.equal(fixture('error.not_implemented').payload.error.details.reason, CONTRACT.not_implemented_reason);
  assert.ok(fixture('check.binary').payload.findings.every(f => f.location), 'C10 locations');
  assert.equal(fixture('export.binary.stale_report').about.exit_code, 3, 'HO: exit 3');
});
