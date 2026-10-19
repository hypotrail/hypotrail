'use strict';
// Stage v1 on the real CLI (scope S, WP-I; COMPANION-ADVANCED §3.2 v1, §6.1, §6.2, §7 W1, W2,
// W5, W6, §11). The controller and real `hypotrail` processes on temporary Bank Marketing
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
  assert.equal(p.last('view_data').model.decisions.length, 5);
  await p.send({ type: 'load', view: 'check' });
  assert.equal(p.last('view_data').view, 'check');
  report(t, p, 'v1 Bank reads');
});

test('W1: a bare "ok" is refused verbatim; a hold blocks with effects.blocked; typed words confirm with channel webview', { skip }, async () => {
  const p = panel(bank, { stage: 'v1' });
  await p.send({ type: 'ready' });
  let rev = p.snapshot().revision;
  await p.send({ type: 'confirm', proposalId: 'p_1', words: 'ok', revision: rev });
  const bare = p.last('outcome');
  assert.equal(bare.kind, 'refused');
  assert.deepEqual([bare.refusal.code, bare.refusal.reason], ['ambiguous_confirmation', 'bare_acknowledgement']);
  const direct = bank.hyp(['decide', 'confirm', 'p_1', '--user-words', 'ok', '--channel', 'webview', '--request-id', 'direct-ok',
    '--expected-revision', rev]);
  assert.equal(bare.refusal.engineMessage, direct.error.message, 'the engine message, verbatim');
  // The junior's condition, recorded in the chat, blocks the confirmation.
  const note = bank.hyp(['decide', 'note', '--about', 'prediction_time', '--text', 'only once I have checked the client file schedule',
    '--request-id', bank.rid(), '--expected-revision', rev]);
  assert.equal(note.ok, true, JSON.stringify(note));
  await p.send({ type: 'refresh' });
  rev = p.snapshot().revision;
  await p.send({ type: 'preview_effects', proposalId: 'p_1', revision: rev });
  const effects = p.last('effects');
  assert.equal(effects.proposalId, 'p_1');
  assert.deepEqual(effects.model.blocked.map(b => b.code), ['decision_on_hold']);
  await p.send({ type: 'confirm', proposalId: 'p_1', words: WORDS, revision: rev });
  assert.equal(p.last('outcome').refusal.code, 'decision_on_hold');
  assert.equal(bank.view().decisions.prediction_time.status !== 'confirmed', true, 'nothing recorded');
  const resolve = bank.hyp(['decide', 'note', '--resolve', 'n_1', '--text', 'I checked the client file schedule and it holds',
    '--request-id', bank.rid(), '--expected-revision', rev]);
  assert.equal(resolve.ok, true, JSON.stringify(resolve));
  await p.send({ type: 'refresh' });
  // A stale revision is refused, then the revision the junior now sees confirms.
  await p.send({ type: 'confirm', proposalId: 'p_1', words: WORDS, revision: rev });
  assert.equal(p.last('outcome').refusal.code, 'stale_revision');
  rev = p.snapshot().revision;
  await p.send({ type: 'preview_effects', proposalId: 'p_1', revision: rev });
  assert.deepEqual(p.last('effects').model.blocked, []);
  await p.send({ type: 'confirm', proposalId: 'p_1', words: WORDS, revision: rev });
  const ok = p.last('outcome');
  assert.equal(ok.kind, 'ok', JSON.stringify(ok));
  assert.deepEqual([ok.recorded.userWords, ok.recorded.channel, ok.recorded.decisionId], [WORDS, 'webview', 'prediction_time']);
  const conf = bank.view().decisions.prediction_time.confirmation;
  assert.deepEqual([conf.user_words, conf.channel, conf.actor, conf.basis], [WORDS, 'webview', 'user', 'explicit']);
});

test('W2: withdraw after the modal; the proposal is withdrawn in the state', { skip }, async () => {
  const pid = bank.propose('feature_availability', require('./realstudy').availability('binary'));
  const p = panel(bank, { stage: 'v1' });
  await p.send({ type: 'ready' });
  await p.send({ type: 'withdraw', proposalId: pid, revision: p.snapshot().revision });
  assert.equal(p.last('outcome').kind, 'ok');
  const state = JSON.parse(fs.readFileSync(path.join(bank.studyDir, '.hypotrail', 'state.json'), 'utf8'));
  assert.equal(state.proposals[pid].status, 'withdrawn');
  assert.ok(!p.snapshot().proposals.some(x => x.proposalId === pid), 'refreshed: no longer open');
});

test('W5: Regenerate writes the report and the notebook; W6: an interrupted run is acknowledged in typed words only', { skip }, async () => {
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
  await p.send({ type: 'acknowledge', executionId: eid, words: 'ok', revision: p.snapshot().revision });
  const bare = p.last('outcome');
  assert.deepEqual([bare.op, bare.kind, bare.refusal.code, bare.refusal.reason], ['W6', 'refused', 'ambiguous_confirmation', 'bare_acknowledgement']);
  const words = 'I know this run was cut off and its outcome is unknown';
  await p.send({ type: 'acknowledge', executionId: eid, words, revision: p.snapshot().revision });
  const ack = p.last('outcome');
  assert.equal(ack.kind, 'ok', JSON.stringify(ack));
  assert.equal(ack.recorded.userWords, words);
  const after = p.snapshot().executions;
  assert.ok(![...after.interrupted, ...after.suspected].some(e => e.executionId === eid), 'no longer waiting');
});

test('reviewer mode refuses every write of the study before any process starts (RV-2)', { skip }, async () => {
  const p = panel(bank, { stage: 'v3', reviewer: true });
  await p.send({ type: 'ready' });
  const before = p.commands().length;
  const rev = p.snapshot().revision;
  for (const m of [{ type: 'confirm', proposalId: 'p_1', words: WORDS, revision: rev }, { type: 'withdraw', proposalId: 'p_1', revision: rev },
    { type: 'propose', decisionId: 'policy', value: 'capacity:100', revision: rev }, { type: 'render' },
    { type: 'run_eda', activity: 'eda.distribution', column: 'age', revision: rev },
    { type: 'acknowledge', executionId: 'e_1', words: 'I know it stopped', revision: rev }]) {
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
  await p.send({ type: 'confirm', proposalId: 'p_1', words: 'Yes, once the technical characteristics of the model are fixed', revision: p.snapshot().revision });
  assert.equal(p.last('outcome').kind, 'ok');
  await p.send({ type: 'load', view: 'check' });
  const shown = p.posted.filter(m => m.type === 'snapshot' || m.type === 'view_data' || m.type === 'effects' || m.type === 'outcome');
  const words = strings(shown).filter(s => FORBIDDEN.test(s));
  assert.deepEqual(words, [], 'no decision-rule word in what the regression panel received');
  report(t, p, 'v1 Auto MPG reads');
});
