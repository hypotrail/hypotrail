'use strict';
// Stage v2 on the real CLI (scope S, WP-I; COMPANION-ADVANCED §3.2 v2, §6.3, §6.4, §6.5, §7
// W4 (no W3 since the v0.3 narrowing), §11; CLI-CONTRACT-COMPANION C4, C5, C8, C9). The controller and real `hypotrail`
// processes on temporary Bank Marketing and Auto MPG studies walked by the chat agent (direct
// CLI calls) to the fits. Not a VS Code session. Needs framework/.venv.

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const { Study, panel, report, strings, skip, FORBIDDEN } = require('./realstudy');
const whatif = require('../lib/handlers/whatif');

let bank, auto;

test.before(() => {
  if (skip) return;
  bank = new Study('binary', 'bank v2');
  bank.walk();
  auto = new Study('regression', 'auto v2');
  auto.walk();
});

test.after(() => {
  for (const s of [bank, auto]) if (s) s.dispose();
});

const ledger = study => study.hyp(['evidence', '--json']).exposure.ledger
  .map(r => ({ key: `${r.purpose}:${r.partition}`, rows: r.rows, records: r.records, activities: r.activities }));

test('EDA, Evidence and What if? share one evidence read per revision; a result detail is its own read (§5, §11)', { skip }, async t => {
  const p = panel(bank, { stage: 'v2' });
  await p.send({ type: 'ready' });
  await Promise.all([p.send({ type: 'load', view: 'eda' }), p.send({ type: 'load', view: 'evidence' }), p.send({ type: 'load', view: 'whatif' })]);
  await p.send({ type: 'load', view: 'eda' });
  assert.equal(p.commands().filter(x => x === 'evidence --json').length, 1, 'one process for the three views');
  const byView = Object.fromEntries(p.all('view_data').map(m => [m.view, m.model]));
  assert.ok(byView.eda.catalog.some(a => a.activity === 'eda.distribution' && a.perColumn && a.runnable));
  const logistic = byView.evidence.results.find(r => r.slot === 'fit.logistic' && r.current);
  assert.ok(byView.whatif.evaluatedRules.some(r => r.rule === 'capacity:100'));
  await p.send({ type: 'load', view: 'evidence', resultId: logistic.resultId });
  const detail = p.last('view_data');
  assert.equal(detail.resultId, logistic.resultId);
  assert.equal(detail.model.detail.resultId, logistic.resultId);
  assert.equal(p.commands().filter(x => x === 'evidence --result').length, 1);
  report(t, p, 'v2 Bank reads');
});

test('W4: a feature distribution runs on training rows only; the exposure ledger gains train rows only (ED-1, INV-13)', { skip }, async () => {
  const p = panel(bank, { stage: 'v2' });
  await p.send({ type: 'ready' });
  const before = ledger(bank);
  const rev = p.snapshot().revision;
  // Not in the catalog as a per-column activity: invalid, no process.
  const n = p.commands().length;
  await p.send({ type: 'run_eda', activity: 'eda.target_rate', column: 'age', revision: rev });
  assert.equal(p.last('outcome').kind, 'invalid');
  await p.send({ type: 'run_eda', activity: 'eda.distribution', column: 'no_such_column', revision: rev });
  assert.equal(p.last('outcome').kind, 'invalid');
  assert.ok(!p.commands().slice(n).some(x => x.startsWith('run')), 'nothing ran');
  await p.send({ type: 'run_eda', activity: 'eda.distribution', column: 'age', revision: rev });
  const o = p.last('outcome');
  assert.equal(o.kind, 'ok', JSON.stringify(o));
  assert.deepEqual([o.recorded.slot, o.recorded.status], ['eda.distribution:age', 'promoted']);
  const after = ledger(bank);
  const changed = after.filter(r => JSON.stringify(r) !== JSON.stringify(before.find(b => b.key === r.key)));
  assert.deepEqual(changed.map(r => r.key), ['train_eda:train'], JSON.stringify({ before, after }));
  assert.ok(changed[0].activities.includes('eda.distribution'));
  for (const key of ['validation_model_evaluation:validation', 'validation_policy_selection:validation']) {
    assert.deepEqual(after.find(r => r.key === key), before.find(r => r.key === key), key);
  }
  await p.send({ type: 'load', view: 'eda' });
  assert.ok(p.last('view_data').model.cards.some(c => c.slot === 'eda.distribution:age' && c.current));
});

test('no W3 (v0.3): the panel previews and drafts; it asks the agent to propose (clipboard); the chat proposes', { skip }, async () => {
  const copied = [];
  const p = panel(bank, { stage: 'v2' }, { writeClipboard: async text => { copied.push(text); } });
  await p.send({ type: 'ready' });
  // The slider: a preview, never a write.
  await p.send({ type: 'preview_policy', rules: ['capacity:150'], intervals: false, seq: 1 });
  await whatif.settled(p.c.context);
  const preview = p.last('preview_policy_result');
  assert.equal(preview.seq, 1);
  assert.ok(preview.model.byRule['capacity:150'], JSON.stringify(preview.model).slice(0, 300));
  let rev = p.snapshot().revision;
  await p.send({ type: 'draft', decisionId: 'policy', value: 'capacity:150', revision: rev });
  assert.equal(p.last('draft_result').model.proposable, false, 'WI-3: not evaluated');
  // ADR 0004 amendment (I2): a propose message is dropped; nothing is written.
  const n = p.commands().length;
  await p.send({ type: 'propose', decisionId: 'policy', value: 'capacity:150', revision: rev });
  assert.equal(p.posted.filter(m => m.type === 'outcome').length, 0);
  assert.ok(!p.commands().slice(n).some(x => x.startsWith('decide')), 'no proposal was written');
  // The agent (this test) evaluates the rule in the chat; the draft becomes proposable.
  bank.run('policy.evaluate', '--rule', 'capacity:150');
  await p.send({ type: 'refresh' });
  rev = p.snapshot().revision;
  await p.send({ type: 'draft', decisionId: 'policy', value: 'capacity:150', revision: rev });
  assert.equal(p.last('draft_result').model.proposable, true);
  // "Ask the agent to propose this": a ready question on the clipboard, no study write.
  await p.send({ type: 'ask_agent', about: { kind: 'decision', id: 'policy' },
    question: 'Could you propose the decision rule "top 150 rows" (capacity:150)?', mode: 'copy' });
  assert.equal(copied.length, 1);
  assert.match(copied[0], /capacity:150/);
  assert.equal(bank.rev(), rev, 'nothing recorded');
  // The chat proposes and the junior confirms there; the panel reads both.
  const pid = bank.propose('policy', 'capacity:150', { json: false });
  await p.send({ type: 'refresh' });
  assert.deepEqual(p.snapshot().proposals.find(x => x.proposalId === pid).origin, { channel: 'chat' });
  const words = 'Yes, call the 150 best-scored clients in each wave, it fits our call capacity';
  const confirm = bank.hyp(['decide', 'confirm', pid, '--user-words', words, '--request-id', bank.rid(), '--expected-revision', bank.rev()]);
  assert.equal(confirm.ok, true, JSON.stringify(confirm));
  const policy = bank.view().decisions.policy;
  assert.deepEqual([policy.status, policy.value, policy.confirmation.channel], ['confirmed', 'capacity:150', 'chat']);
});

test('v2 on Auto MPG: residual explorer, a model-choice draft (no proposal from the panel), and no decision-rule vocabulary (INV-12)', { skip }, async t => {
  const p = panel(auto, { stage: 'v2' });
  await p.send({ type: 'ready' });
  await p.send({ type: 'load', view: 'whatif' });
  const model = p.last('view_data').model;
  assert.equal(model.task, 'regression');
  assert.ok(model.models.length >= 2 && model.errors['fit.linear'], JSON.stringify(model).slice(0, 300));
  await p.send({ type: 'load', view: 'eda' });
  await p.send({ type: 'load', view: 'evidence' });
  const rev = p.snapshot().revision;
  await p.send({ type: 'draft', decisionId: 'model_choice', value: 'fit.linear', revision: rev });
  assert.equal(p.last('draft_result').model.proposable, true);
  // No W3 since v0.3: a propose message is dropped and nothing is proposed.
  await p.send({ type: 'propose', decisionId: 'model_choice', value: 'fit.linear', revision: rev });
  assert.equal(p.posted.filter(m => m.type === 'outcome').length, 0);
  assert.equal(auto.rev(), rev);
  await p.send({ type: 'run_eda', activity: 'eda.distribution', column: 'weight', revision: p.snapshot().revision });
  assert.equal(p.last('outcome').kind, 'ok', JSON.stringify(p.last('outcome')));
  const shown = p.posted.filter(m => ['snapshot', 'view_data', 'draft_result', 'outcome', 'notice'].includes(m.type));
  assert.deepEqual(strings(shown).filter(s => FORBIDDEN.test(s)), [], 'no decision-rule word in the regression panel data');
  report(t, p, 'v2 Auto MPG reads');
});
