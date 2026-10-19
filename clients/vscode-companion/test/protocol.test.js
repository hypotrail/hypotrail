'use strict';
// Protocol tests (scope U, frozen by WP-0): hypotrail.panel/2 (COMPANION-ADVANCED §8).
// For every message type, in both directions: one valid example, one with an extra field,
// and one with a field of the wrong type. The webview copy media/protocol.js equals the
// generated text, and every model fixture passes as `view_data` (round trip).

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const protocol = require('../lib/protocol');
const { fixture } = require('./fixture-cli');

const RID = 'a'.repeat(64);
const MODEL = { revision: 3, anything: [1, 'x', null] };

// One valid example per type; `wrong` names a field and a value of the wrong type.
const TO_EXTENSION = {
  ready: [{}, null],
  refresh: [{}, null],
  load: [{ view: 'evidence', resultId: RID }, ['view', 'nope']],
  confirm: [{ proposalId: 'p_1', words: 'Yes, before the call.', revision: 3 }, ['revision', '3']],
  withdraw: [{ proposalId: 'p_1', revision: 3 }, ['proposalId', 'p_x']],
  preview_effects: [{ proposalId: 'p_2', revision: 3 }, ['revision', 0]],
  preview_policy: [{ rules: ['capacity:100', 'threshold:0.2'], intervals: true, seq: 7 }, ['rules', ['capacity:0']]],
  draft: [{ decisionId: 'policy', value: 'capacity:100', revision: 3 }, ['decisionId', 'split']],
  propose: [{ decisionId: 'model_choice', value: 'fit.linear', revision: 3 }, ['value', 7]],
  run_eda: [{ activity: 'eda.distribution', column: 'age', revision: 3 }, ['activity', 'fit.logistic']],
  render: [{}, null],
  acknowledge: [{ executionId: 'e_1a2b', words: 'I know it was interrupted.', revision: 3 }, ['executionId', 'e 1']],
  open_artifact: [{ artifact: 'report', resultId: RID }, ['artifact', '../etc/passwd']],
  open_marimo: [{ artifact: 'workbench' }, ['artifact', 'report']],
  navigate_external: [{ kind: 'reveal_export', path: '/tmp/x/revision-3' }, ['kind', 'open']],
  ask_agent: [{ about: { kind: 'result', id: 'abcd1234' }, question: '', mode: 'copy' }, ['mode', 'send']],
  export_handoff: [{ revision: 3 }, ['revision', 1.5]],
  switch_study: [{}, null],
  learn_set: [{ key: 'prediction', id: 'binary.train_eda.rare', value: 'rare' }, ['key', 'words']],
};
const TO_WEBVIEW = {
  init: [{ stage: 'v1', reviewer: false, learningLayer: true, chatInsert: false, task: null }, ['stage', 'v9']],
  snapshot: [{ revision: 3, model: MODEL }, ['model', []]],
  view_data: [{ view: 'decisions', revision: 3, model: MODEL }, ['view', 'nope']],
  load_error: [{ view: null, message: 'm', detail: '' }, ['detail', null]],
  busy: [{ busy: true, op: 'W1', target: 'p_1' }, ['busy', 'yes']],
  outcome: [{ op: 'W1', kind: 'refused', target: 'p_1', exitCode: 2, refusal: { code: 'ambiguous_confirmation',
    reason: 'bare_acknowledgement', engineMessage: 'e', human: 'h', details: [] } }, ['kind', 'confirmed']],
  preview_policy_result: [{ seq: 3, revision: 3, model: MODEL }, ['seq', -1]],
  effects: [{ proposalId: 'p_1', revision: 3, model: MODEL }, ['proposalId', 1]],
  draft_result: [{ decisionId: 'policy', value: 'capacity:100', revision: 3, model: MODEL }, ['decisionId', 'conclusion']],
  learn_state: [{ prefs: {}, seen: {}, predictions: {} }, ['seen', []]],
  navigate: [{ tab: 'evidence', kind: 'result', id: RID }, ['tab', 'nowhere']],
  notice: [{ text: 'Copied.', politeness: 'polite' }, ['politeness', 'loud']],
};

function cases(table, validate, examples) {
  assert.deepEqual(Object.keys(examples).sort(), Object.keys(table).sort(), 'one example per type');
  for (const [type, [fields, wrong]] of Object.entries(examples)) {
    const valid = { v: 2, type, ...fields };
    assert.deepEqual(validate(valid), valid, `${type}: valid`);
    assert.equal(validate({ ...valid, extra: 1 }), null, `${type}: extra field`);
    assert.equal(validate({ ...valid, v: 1 }), null, `${type}: wrong version`);
    const { v: _v, ...noVersion } = valid;
    assert.equal(validate(noVersion), null, `${type}: no version`);
    if (wrong) assert.equal(validate({ ...valid, [wrong[0]]: wrong[1] }), null, `${type}: wrong ${wrong[0]}`);
  }
}

test('webview -> extension: every type validates, an extra field or a wrong type is dropped', () => {
  cases(protocol.TO_EXTENSION, protocol.validateIncoming, TO_EXTENSION);
  for (const bad of [null, [], 'ready', { v: 2 }, { v: 2, type: 'eval' }, { v: 2, type: 'toString' }]) {
    assert.equal(protocol.validateIncoming(bad), null);
  }
});

test('extension -> webview: every type validates, an extra field or a wrong type is dropped', () => {
  cases(protocol.TO_WEBVIEW, protocol.validateOutgoing, TO_WEBVIEW);
});

test('field rules: words, rules, load, learn_set', () => {
  const ok = m => protocol.validateIncoming({ v: 2, ...m }) !== null;
  assert.ok(ok({ type: 'confirm', proposalId: 'p_1', words: 'x'.repeat(4000), revision: 1 }));
  assert.ok(!ok({ type: 'confirm', proposalId: 'p_1', words: 'x'.repeat(4001), revision: 1 }));
  for (const rule of ['threshold:0', 'threshold:1', 'threshold:1.00', 'threshold:0.35', 'capacity:1', 'capacity:9999999']) {
    assert.ok(ok({ type: 'preview_policy', rules: [rule], intervals: false, seq: 0 }), rule);
  }
  for (const rule of ['threshold:1.5', 'threshold:-0.1', 'capacity:0', 'capacity:10000000', 'capacity:01', 'top:5']) {
    assert.ok(!ok({ type: 'preview_policy', rules: [rule], intervals: false, seq: 0 }), rule);
  }
  assert.ok(!ok({ type: 'preview_policy', rules: ['capacity:1', 'capacity:2', 'capacity:3', 'capacity:4', 'capacity:5'], intervals: false, seq: 0 }));
  assert.ok(!ok({ type: 'load', view: 'summary', resultId: 'a'.repeat(64) }), 'resultId only with evidence');
  assert.ok(ok({ type: 'load', view: 'summary', since: 0 }));
  assert.ok(!ok({ type: 'load', view: 'decisions', since: 1 }), 'since only with summary');
  assert.ok(ok({ type: 'learn_set', key: 'seen', id: 'binary:train_eda' }));
  assert.ok(!ok({ type: 'learn_set', key: 'seen', id: 'binary:train_eda', value: 1 }));
  assert.ok(ok({ type: 'learn_set', key: 'prefs', id: 'prefs', value: { hideCards: true } }));
  assert.ok(!ok({ type: 'learn_set', key: 'prefs', id: 'prefs', value: { words: 'x' } }));
  assert.ok(!ok({ type: 'learn_set', key: 'prediction', id: 'q', value: 'Rare <b>' }));
  // WP-I (U1, U3 requests): a result opens the report at its anchor or the notebook at its
  // line; a check finding's line opens an editor deliverable. The workbench has no result.
  assert.ok(ok({ type: 'open_artifact', artifact: 'notebook', resultId: 'a'.repeat(64) }), 'the notebook at a result');
  assert.ok(!ok({ type: 'open_artifact', artifact: 'workbench', resultId: 'a'.repeat(64) }), 'no result in the workbench');
  assert.ok(ok({ type: 'open_artifact', artifact: 'notebook', line: 12 }), 'an editor deliverable at a line');
  assert.ok(!ok({ type: 'open_artifact', artifact: 'report', line: 12 }), 'the report opens in the browser, without a line');
  assert.ok(!ok({ type: 'open_artifact', artifact: 'notebook', line: 0 }), 'lines start at 1');
  assert.ok(!ok({ type: 'open_artifact', artifact: 'notebook', line: 3, resultId: 'a'.repeat(64) }), 'one target');
});

test('stages: every incoming type has one; field stages raise it; writes carry their W id', () => {
  const writes = {};
  for (const [type, entry] of Object.entries(protocol.TO_EXTENSION)) {
    assert.ok(protocol.STAGES.includes(entry.stage), type);
    if (entry.write) writes[type] = entry.write;
  }
  assert.deepEqual(writes, { confirm: 'W1', withdraw: 'W2', propose: 'W3', run_eda: 'W4', render: 'W5',
    acknowledge: 'W6', export_handoff: 'W7' });
  assert.equal(protocol.stageOf({ v: 2, type: 'open_artifact', artifact: 'report' }), 'v0');
  // WP-I: from v1, for the check findings of the Overview (U1 request).
  assert.equal(protocol.stageOf({ v: 2, type: 'open_artifact', artifact: 'report', resultId: RID }), 'v1');
  assert.equal(protocol.stageOf({ v: 2, type: 'open_artifact', artifact: 'notebook', line: 4 }), 'v1');
  assert.ok(protocol.stageAllows('v2', 'v1') && !protocol.stageAllows('v1', 'v2') && !protocol.stageAllows('v3', 'v9'));
});

test('media/protocol.js is the generated copy of lib/protocol.js', () => {
  const copy = fs.readFileSync(path.join(__dirname, '..', 'media', 'protocol.js'), 'utf8');
  assert.equal(copy, protocol.webviewSource(), 'run: node lib/protocol.js --emit-webview');
  // The copy defines the same table when loaded the webview way.
  delete globalThis.Hypotrail;
  require('../media/protocol.js');
  assert.deepEqual(Object.keys(globalThis.Hypotrail.protocol.TO_EXTENSION), Object.keys(protocol.TO_EXTENSION));
  assert.deepEqual(Object.keys(globalThis.Hypotrail.protocol.TO_WEBVIEW), Object.keys(protocol.TO_WEBVIEW));
  delete globalThis.Hypotrail;
});

test('round trip: every model of every lib/models/*.js fixture passes as view_data and snapshot', () => {
  const dir = path.join(__dirname, '..', 'lib', 'models');
  let checked = 0;
  for (const file of fs.readdirSync(dir).filter(f => f.endsWith('.js') && f !== 'common.js')) {
    const mod = require(path.join(dir, file));
    const fn = Object.entries(mod).find(([k, v]) => /^to[A-Z]\w*Model$/.test(k) && typeof v === 'function');
    assert.ok(fn, `${file} exports a to<Name>Model function`);
    assert.ok(Array.isArray(mod.FIXTURES) && mod.FIXTURES.length, `${file} exports FIXTURES`);
    for (const name of mod.FIXTURES) {
      const model = fn[1](fixture(name).payload);
      const view = file === 'summary.js' ? 'summary' : null;
      for (const message of [{ v: 2, type: 'snapshot', revision: model.revision || 0, model },
        { v: 2, type: 'view_data', view: view || 'decisions', revision: model.revision || 0, model }]) {
        assert.ok(protocol.validateOutgoing(message), `${file} ${name}: ${protocol.explainOutgoing(message)}`);
      }
      assert.deepEqual(JSON.parse(JSON.stringify(model)), model, `${file} ${name}: plain values only`);
      checked += 1;
    }
  }
  assert.ok(checked >= 5);
});
