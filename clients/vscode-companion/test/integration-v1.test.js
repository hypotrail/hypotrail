'use strict';
// Stage v1 on the real CLI (scope S, WP-I; COMPANION-ADVANCED §3.2 v1, §6.1, §6.2, §7 W5,
// §11; no W1/W2 since the v0.3 narrowing, no W6 since R31: an interruption is acknowledged in
// the chat). The controller and real `hypotrail` processes on temporary Bank Marketing
// (binary) and Auto MPG (regression) studies created from the committed cases, outside the
// repository, in paths with spaces and quotes. The chat agent is played by direct CLI
// calls. Not a VS Code session. Needs framework/.venv.

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const { Study, panel, report, strings, skip, FORBIDDEN } = require('./realstudy');

const WORDS = 'Yes, we score before the first contact, from the client file only';
let bank, auto;

test.before(() => {
  if (skip) return;
  bank = new Study('binary', 'bank v1');
  auto = new Study('regression', 'auto v1');
});

test.after(() => {
  for (const s of [bank, auto]) if (s) s.dispose();
});

test('v1 open: one summary read with the digest; the decisions read is cached per revision (§11)', { skip }, async t => {
  bank.propose('prediction_time', 'before the first contact of the campaign, from the client file');
  const p = panel(bank, { stage: 'v1' });
  await p.send({ type: 'ready' });
  assert.deepEqual(p.commands(), ['status --summary'], 'one CLI call on open');
  const snap = p.snapshot();
  assert.equal(snap.task, 'binary');
  assert.ok(snap.digest && Array.isArray(snap.digest.items), 'the digest is read (C1)');
  assert.deepEqual(snap.proposals.map(x => [x.proposalId, x.origin && x.origin.channel]), [['p_1', 'chat']]);
  await Promise.all([p.send({ type: 'load', view: 'decisions' }), p.send({ type: 'load', view: 'decisions' })]);
  await p.send({ type: 'load', view: 'decisions' });
  assert.equal(p.commands().filter(x => x.startsWith('decisions')).length, 1, 'coalesced, then cached');
  // WP-A4: a new study holds seven decisions (success criterion and preprocessing added);
  // WP-B1: ten for a new binary study: variant, explicit model choice, and final test.
  assert.equal(p.last('view_data').model.decisions.length, 10);
  await p.send({ type: 'load', view: 'check' });
  assert.equal(p.last('view_data').view, 'check');
  report(t, p, 'v1 Bank reads');
});

test('no W1 (v0.3): a hold blocks in effects.blocked; the panel drops a confirm; the chat confirms and the panel shows it', { skip }, async () => {
  const p = panel(bank, { stage: 'v1' });
  await p.send({ type: 'ready' });
  let rev = p.snapshot().revision;
  // ADR 0004 amendment (R23, I2): the panel records no decision; a confirm is dropped.
  await p.send({ type: 'confirm', proposalId: 'p_1', words: WORDS, revision: rev });
  assert.equal(p.posted.filter(m => m.type === 'outcome').length, 0);
  assert.ok(!p.commands().some(x => x.startsWith('decide')), 'no decide command');
  assert.equal(bank.rev(), rev, 'nothing recorded');
  // The junior's condition, recorded in the chat, blocks the confirmation (the engine's preview says so).
  const note = bank.hyp(['decide', 'note', '--about', 'prediction_time', '--text', 'only once I have checked the client file schedule',
    '--request-id', bank.rid(), '--expected-revision', rev]);
  assert.equal(note.ok, true, JSON.stringify(note));
  await p.send({ type: 'refresh' });
  rev = p.snapshot().revision;
  await p.send({ type: 'preview_effects', proposalId: 'p_1', revision: rev });
  const effects = p.last('effects');
  assert.equal(effects.proposalId, 'p_1');
  assert.deepEqual(effects.model.blocked.map(b => b.code), ['decision_on_hold']);
  const resolve = bank.hyp(['decide', 'note', '--resolve', 'n_1', '--text', 'I checked the client file schedule and it holds',
    '--request-id', bank.rid(), '--expected-revision', rev]);
  assert.equal(resolve.ok, true, JSON.stringify(resolve));
  await p.send({ type: 'refresh' });
  rev = p.snapshot().revision;
  await p.send({ type: 'preview_effects', proposalId: 'p_1', revision: rev });
  assert.deepEqual(p.last('effects').model.blocked, []);
  // The chat confirms; the panel reads it on its next refresh.
  const confirm = bank.hyp(['decide', 'confirm', 'p_1', '--user-words', WORDS, '--request-id', bank.rid(), '--expected-revision', rev]);
  assert.equal(confirm.ok, true, JSON.stringify(confirm));
  await p.send({ type: 'refresh' });
  assert.ok(!p.snapshot().proposals.some(x => x.proposalId === 'p_1'), 'the card is gone');
  const conf = bank.view().decisions.prediction_time.confirmation;
  assert.deepEqual([conf.user_words, conf.channel], [WORDS, 'chat']);
  await p.send({ type: 'load', view: 'decisions' });
  assert.equal(p.last('view_data').model.history[0].decisionId, 'prediction_time', 'newest first (R25)');
});

test('no W2 (v0.3): a withdrawal in the chat reaches the panel', { skip }, async () => {
  const pid = bank.propose('feature_availability', require('./realstudy').availability('binary'));
  const p = panel(bank, { stage: 'v1' });
  await p.send({ type: 'ready' });
  await p.send({ type: 'withdraw', proposalId: pid, revision: p.snapshot().revision });
  assert.equal(p.posted.filter(m => m.type === 'outcome').length, 0, 'the panel withdraws nothing');
  const out = bank.hyp(['decide', 'withdraw', pid, '--request-id', bank.rid(), '--expected-revision', p.snapshot().revision]);
  assert.equal(out.ok, true, JSON.stringify(out));
  await p.send({ type: 'refresh' });
  const state = JSON.parse(fs.readFileSync(path.join(bank.studyDir, '.hypotrail', 'state.json'), 'utf8'));
  assert.equal(state.proposals[pid].status, 'withdrawn');
  assert.ok(!p.snapshot().proposals.some(x => x.proposalId === pid), 'refreshed: no longer open');
});

test('W5: Regenerate writes the report and the notebook; R31: an interrupted run is shown read only and acknowledged in the chat', { skip }, async () => {
  bank.decide('feature_availability', require('./realstudy').availability('binary'));
  bank.decide('split', { method: 'stratified_random', validation_fraction: 0.3, seed: 20261017 });
  bank.run('split');
  const p = panel(bank, { stage: 'v1' });
  await p.send({ type: 'ready' });
  await p.send({ type: 'render' });
  const rendered = p.last('outcome');
  assert.equal(rendered.op, 'W5');
  assert.ok(['ok', 'ok_with_problems'].includes(rendered.kind), JSON.stringify(rendered));
  assert.ok(rendered.artifacts.some(a => a.name === 'report'));
  assert.ok(fs.existsSync(path.join(bank.studyDir, 'reports', 'study.html')));
  // The agent's run is killed after its reservation (a real process, the fault hook).
  const rev = bank.rev();
  bank.hyp(['run', 'eda.target_rate', '--request-id', 'fault-1', '--expected-revision', rev],
    { HYPOTRAIL_TEST_HOOKS: '1', HYPOTRAIL_FAULT: 'run_after_reserve' });
  await p.send({ type: 'refresh' });
  const ex = p.snapshot().executions;
  const pending = [...ex.interrupted, ...ex.suspected];
  assert.equal(pending.length, 1, JSON.stringify(ex));
  const eid = pending[0].executionId;
  // The panel takes no acknowledgement (R31): the message is dropped and runs nothing.
  const before = p.commands().length;
  await p.send({ type: 'acknowledge', executionId: eid, words: 'I know it stopped', revision: p.snapshot().revision });
  assert.equal(p.commands().length, before, 'no CLI process');
  // The chat acknowledges it in the junior's words (the agent, played by a direct CLI call);
  // the panel reads it back.
  bank.hyp(['run', '--acknowledge-interruption', eid, '--user-words=I know this run was cut off and its outcome is unknown',
    '--request-id', 'chat-ack-1', '--expected-revision', bank.rev(), '--json']);
  await p.send({ type: 'refresh' });
  const after = p.snapshot().executions;
  assert.ok(![...after.interrupted, ...after.suspected].some(e => e.executionId === eid), 'no longer waiting');
});

test('reviewer mode refuses every write of the study before any process starts (RV-2)', { skip }, async () => {
  const p = panel(bank, { stage: 'v3', reviewer: true });
  await p.send({ type: 'ready' });
  const before = p.commands().length;
  const rev = p.snapshot().revision;
  for (const m of [{ type: 'render' },
    { type: 'run_eda', activity: 'eda.distribution', column: 'age', revision: rev }]) {
    await p.send(m);
    assert.deepEqual([p.last('outcome').kind, p.last('outcome').message], ['invalid', 'Read-only reviewer mode.'], m.type);
  }
  assert.equal(p.commands().length, before, 'no CLI process for a refused write');
  assert.equal(bank.rev(), rev);
});

test('v1 on Auto MPG: the regression study reads, decides, and holds no decision-rule vocabulary (INV-12)', { skip }, async t => {
  auto.propose('prediction_time', 'when the technical characteristics of a new model are fixed, before its fuel efficiency is measured');
  const p = panel(auto, { stage: 'v1' });
  await p.send({ type: 'ready' });
  assert.equal(p.snapshot().task, 'regression');
  await p.send({ type: 'load', view: 'decisions' });
  const decisions = p.last('view_data').model;
  assert.ok(decisions.decisions.some(d => d.decisionId === 'model_choice'));
  const confirm = auto.hyp(['decide', 'confirm', 'p_1', '--user-words', 'Yes, once the technical characteristics of the model are fixed',
    '--request-id', auto.rid(), '--expected-revision', p.snapshot().revision]);
  assert.equal(confirm.ok, true, JSON.stringify(confirm));
  await p.send({ type: 'refresh' });
  await p.send({ type: 'load', view: 'decisions' });
  await p.send({ type: 'load', view: 'check' });
  const shown = p.posted.filter(m => m.type === 'snapshot' || m.type === 'view_data' || m.type === 'effects' || m.type === 'outcome');
  const words = strings(shown).filter(s => FORBIDDEN.test(s));
  assert.deepEqual(words, [], 'no decision-rule word in what the regression panel received');
  report(t, p, 'v1 Auto MPG reads');
});
