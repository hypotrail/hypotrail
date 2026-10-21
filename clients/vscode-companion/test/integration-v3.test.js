'use strict';
// Stage v3 on the real CLI (scope S, WP-I; COMPANION-ADVANCED §3.2 v3, §6.6, §7 W7, §10;
// CLI-CONTRACT-COMPANION C6, C7; decision CA.9). The controller and real `hypotrail`
// processes on a temporary Bank Marketing study walked by the chat agent to the fits, with
// the session log on. Not a VS Code session. Needs framework/.venv.

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { Study, panel, report, strings, skip, FORBIDDEN } = require('./realstudy');

let bank, auto, parent;
const store = () => {
  const data = new Map();
  return { get: k => data.get(k), update: async (k, v) => { data.set(k, v); }, keys: () => [...data.keys()], data };
};

test.before(() => {
  if (skip) return;
  process.env.HYPOTRAIL_SESSION_LOG = '1';
  bank = new Study('binary', 'bank v3');
  bank.walk();
  auto = new Study('regression', 'auto v3');
  auto.walk();
  parent = fs.mkdtempSync(path.join(os.tmpdir(), 'hypotrail packs "q" '));
});

test.after(() => {
  delete process.env.HYPOTRAIL_SESSION_LOG;
  for (const st of [bank, auto]) if (st) st.dispose();
  if (parent) fs.rmSync(parent, { recursive: true, force: true });
});

test('W7: the export pack lands in <chosen>/revision-<R>, its handoff.md checks clean, a second export is refused verbatim (HO-1)', { skip }, async () => {
  const revealed = [];
  const p = panel(bank, { stage: 'v3' }, { pickFolder: async () => parent, globalState: store(), revealInOS: async x => { revealed.push(x); } });
  await p.send({ type: 'ready' });
  await p.send({ type: 'render' });
  const rev = p.snapshot().revision;
  await p.send({ type: 'export_handoff', revision: rev });
  const o = p.last('outcome');
  assert.ok(o.kind === 'ok' || o.kind === 'ok_with_problems', JSON.stringify(o));
  const out = path.join(parent, `revision-${rev}`);
  assert.equal(o.recorded.out, out);
  for (const f of o.recorded.files) {
    assert.ok(fs.existsSync(path.join(out, f.path)), f.path);
    assert.equal(fs.statSync(path.join(out, f.path)).size, f.bytes, f.path);
  }
  assert.ok(o.recorded.files.some(f => f.path === 'handoff.md') && o.recorded.files.some(f => f.path === 'handoff.json'));
  assert.ok(Array.isArray(o.recorded.warnings), 'the warnings, in words (CI.3)');
  assert.ok(!fs.existsSync(path.join(bank.studyDir, '.hypotrail', 'handoff')), 'nothing written into the study state');
  assert.equal(bank.rev(), rev, 'an export writes no study state');
  const checked = bank.hyp(['check', '--text', path.join(out, 'handoff.md'), '--json']);
  assert.equal(checked.clean, true, JSON.stringify(checked.findings));
  await p.send({ type: 'navigate_external', kind: 'reveal_export', path: out });
  assert.deepEqual(revealed, [out], '"Open folder" reveals the last export only');
  // The same folder again: the engine's refusal, verbatim.
  await p.send({ type: 'export_handoff', revision: rev });
  const again = p.last('outcome');
  assert.equal(again.kind, 'refused');
  assert.equal(again.refusal.code, 'export_target_exists');
  const direct = bank.hyp(['export', 'handoff', `--out=${out}`, '--json']);
  assert.equal(again.refusal.engineMessage, direct.error.message);
  assert.equal(direct.command, 'export handoff');
});

test('a reviewer may export (CA.9) and refuses the study writes', { skip }, async () => {
  const reviewerParent = fs.mkdtempSync(path.join(parent, 'reviewer '));
  const p = panel(bank, { stage: 'v3', reviewer: true }, { pickFolder: async () => reviewerParent });
  await p.send({ type: 'ready' });
  await p.send({ type: 'render' });
  assert.equal(p.last('outcome').kind, 'invalid');
  await p.send({ type: 'export_handoff', revision: p.snapshot().revision });
  assert.ok(['ok', 'ok_with_problems'].includes(p.last('outcome').kind), JSON.stringify(p.last('outcome')));
});

test('explain: read once per revision with the learning layer on, never with it off (LE-3); predictions stay local (LE-1)', { skip }, async t => {
  const globalState = store();
  const on = panel(bank, { stage: 'v3', learningLayer: true }, { globalState });
  await on.send({ type: 'ready' });
  await on.send({ type: 'load', view: 'explain' });
  await on.send({ type: 'load', view: 'explain' });
  assert.equal(on.commands().filter(x => x.startsWith('explain')).length, 1);
  const explain = on.last('view_data').model;
  assert.ok(explain.terms.distribution && explain.terms.base_rate, 'the glossary of the task, with distribution (CI.7)');
  const question = explain.predictions[0];
  const commands = on.commands().length;
  await on.send({ type: 'learn_set', key: 'prediction', id: question.id, value: question.choices[0].id });
  assert.ok(!on.commands().slice(commands).some(x => !x.startsWith('explain')), 'a prediction runs no write');
  assert.deepEqual(globalState.keys().filter(k => k !== 'hypotrail.learn.seen' && k !== 'hypotrail.learn.prefs'), ['hypotrail.learn.predictions']);
  const log = fs.readFileSync(path.join(bank.studyDir, '.hypotrail', 'session-log.jsonl'), 'utf8');
  assert.ok(!log.includes(question.id), 'no CLI invocation carried the prediction');
  const off = panel(bank, { stage: 'v3', learningLayer: false }, { globalState: store() });
  await off.send({ type: 'ready' });
  await off.send({ type: 'load', view: 'explain' });
  assert.equal(off.last('load_error').view, 'explain');
  assert.equal(off.commands().filter(x => x.startsWith('explain')).length, 0, 'explain is never called with the layer off');
  report(t, on, 'v3 Bank reads');
});

test('session report: the log is on, the report holds no conversation content (SR-1)', { skip }, async () => {
  const p = panel(bank, { stage: 'v3' }, { globalState: store() });
  await p.send({ type: 'ready' });
  await p.send({ type: 'load', view: 'session_report' });
  const m = p.last('view_data');
  assert.equal(m.view, 'session_report');
  assert.equal(m.model.log.enabled, true);
  const text = JSON.stringify(m.model);
  for (const words of ['Yes, I want the prediction_time exactly as you stated it', 'It fits the scenario.']) {
    assert.ok(!text.includes(words), words);
  }
  assert.ok(fs.existsSync(path.join(bank.studyDir, '.hypotrail', 'session-log.jsonl')));
});

test('v3 on Auto MPG: explain, the export, and the session report hold no decision-rule vocabulary (INV-12)', { skip }, async () => {
  const autoParent = fs.mkdtempSync(path.join(parent, 'auto '));
  const p = panel(auto, { stage: 'v3' }, { pickFolder: async () => autoParent, globalState: store() });
  await p.send({ type: 'ready' });
  await p.send({ type: 'load', view: 'explain' });
  assert.ok(p.last('view_data').model.terms.mae, 'the regression glossary');
  await p.send({ type: 'load', view: 'session_report' });
  await p.send({ type: 'export_handoff', revision: p.snapshot().revision });
  const o = p.last('outcome');
  assert.ok(['ok', 'ok_with_problems'].includes(o.kind), JSON.stringify(o));
  const shown = p.posted.filter(m => ['snapshot', 'view_data', 'outcome', 'notice'].includes(m.type));
  assert.deepEqual(strings(shown).filter(x => FORBIDDEN.test(x)), [], 'no decision-rule word in the regression panel data');
  const md = fs.readFileSync(path.join(o.recorded.out, 'handoff.md'), 'utf8');
  assert.equal(FORBIDDEN.test(md), false, 'the handoff text of a regression study');
});
