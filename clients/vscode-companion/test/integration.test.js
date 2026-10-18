'use strict';
// Integration tests (scope S): the panel controller drives the REAL hypotrail CLI on a
// temporary study created from the synthetic case, outside the repository, in a folder
// whose path holds spaces and quotes. The CLI argv is the one `hypotrail init` recorded
// in .hypotrail/agent.json. The chat agent's part (propose, note) is played by direct
// CLI calls. No VS Code is involved: the controller has no `vscode` dependency.
//
// Needs the framework environment (`uv sync --project framework --group dev`).

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');
const { readAgent } = require('../lib/study');
const { createController } = require('../lib/controller');
const { watchStudy } = require('../lib/watch');

const REPO = path.resolve(__dirname, '..', '..', '..');
const FRAMEWORK = path.join(REPO, 'framework');
const PYTHON = path.join(FRAMEWORK, '.venv', 'bin', 'python');
const MAKE_CASE = path.join(FRAMEWORK, 'tests', 'fixtures', 'synthetic', 'make_case.py');
const skip = fs.existsSync(PYTHON) ? false : 'framework/.venv is missing: run uv sync --project framework --group dev';

let root, studyDir, agent;

function hyp(...args) {
  // The "chat agent" side, through the same recorded argv.
  try {
    const out = execFileSync(agent.argv[0], [...agent.argv.slice(1), ...args.map(String), '--study', studyDir],
      { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'], cwd: os.tmpdir() });
    return JSON.parse(out);
  } catch (e) {
    if (e.stdout) return JSON.parse(e.stdout);
    throw e;
  }
}

function status() {
  return hyp('status', '--json');
}

function controller() {
  const posted = [];
  const c = createController({ agent, post: m => posted.push(m), confirmWithdraw: async () => true });
  return { c, posted, outcome: () => posted.filter(m => m.type === 'outcome').at(-1), snapshot: () => posted.filter(m => m.type === 'snapshot').at(-1) };
}

test.before(() => {
  if (skip) return;
  root = fs.mkdtempSync(path.join(os.tmpdir(), "hypotrail companion 'it' \"q\" "));
  const caseDir = path.join(root, 'synthetic case');
  execFileSync(PYTHON, ['-I', MAKE_CASE, caseDir], { stdio: 'ignore', cwd: os.tmpdir() });
  studyDir = path.join(root, 'my "study" here');
  const init = JSON.parse(execFileSync(PYTHON, ['-m', 'mlkit.study.cli', 'init', '--case', path.join(caseDir, 'case.yaml'), '--study', studyDir],
    { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'], cwd: os.tmpdir() }));
  assert.equal(init.ok, true);
  agent = readAgent(studyDir);
});

test.after(() => {
  if (root) fs.rmSync(root, { recursive: true, force: true });
});

test('the panel reads the real study through the argv recorded by init', { skip }, async () => {
  assert.ok(Array.isArray(agent.argv) && agent.argv.length > 0);
  const propose = hyp('decide', 'propose', 'prediction_time', '--value', 'before the first reminder is sent',
    '--restatement', 'You predict before the first reminder is sent.', '--rationale', 'It matches the scenario.',
    '--request-id', 'chat-1', '--expected-revision', '1');
  assert.equal(propose.ok, true, JSON.stringify(propose));
  const { c, snapshot } = controller();
  await c.handle({ type: 'ready' });
  const model = snapshot().model;
  assert.equal(model.revision, 2);
  assert.equal(model.recap.length, 5);
  assert.equal(model.currentStep.id, 'prediction_time');
  assert.deepEqual(model.proposals.map(p => [p.proposalId, p.restatement]), [['p_1', 'You predict before the first reminder is sent.']]);
  assert.ok(model.artifacts.some(a => a.name === 'report' && a.message.includes('reports/study.html')));
  assert.ok(model.notYetDefensible.top.length > 0);
});

test('a bare "ok" is refused by the engine and shown verbatim; nothing is recorded', { skip }, async () => {
  const { c, outcome, snapshot } = controller();
  await c.handle({ type: 'ready' });
  const rev = snapshot().model.revision;
  await c.handle({ type: 'confirm', proposalId: 'p_1', words: 'ok', revision: rev });
  const o = outcome();
  assert.equal(o.kind, 'refused');
  assert.equal(o.exitCode, 2);
  assert.equal(o.refusal.code, 'ambiguous_confirmation');
  assert.equal(o.refusal.reason, 'bare_acknowledgement');
  // Same message as the CLI gives the chat agent for the same words.
  const direct = hyp('decide', 'confirm', 'p_1', '--user-words', 'ok', '--channel', 'webview',
    '--request-id', 'direct-ok', '--expected-revision', String(rev));
  assert.equal(o.refusal.engineMessage, direct.error.message);
  assert.equal(snapshot().model.revision, rev, 'refreshed, unchanged');
  assert.equal(status().view.decisions.prediction_time.confirmation, null);
});

test('a hold blocks the confirmation (decision_on_hold) until the junior resolves it in the chat', { skip }, async () => {
  const note = hyp('decide', 'note', '--about', 'prediction_time', '--text',
    'wait until I check with my manager about the reminder schedule', '--request-id', 'chat-2', '--expected-revision', '2');
  assert.equal(note.ok, true, JSON.stringify(note));
  const { c, outcome, snapshot } = controller();
  await c.handle({ type: 'ready' });
  const model = snapshot().model;
  assert.deepEqual(model.proposals[0].holds.map(h => h.userWords), ['wait until I check with my manager about the reminder schedule']);
  await c.handle({ type: 'confirm', proposalId: 'p_1', words: 'Yes, we predict before the first reminder is sent.', revision: model.revision });
  assert.equal(outcome().refusal.code, 'decision_on_hold');
  assert.deepEqual(outcome().refusal.details, ['On hold (n_1): "wait until I check with my manager about the reminder schedule"']);
  const resolve = hyp('decide', 'note', '--resolve', 'n_1', '--text',
    'Yes, my manager checked the reminder schedule and agrees with this prediction moment',
    '--request-id', 'chat-3', '--expected-revision', String(model.revision));
  assert.equal(resolve.ok, true, JSON.stringify(resolve));
});

test('a stale revision is refused with the diff, then the typed words confirm with channel webview', { skip }, async () => {
  const { c, outcome, snapshot } = controller();
  await c.handle({ type: 'ready' });
  const rev = snapshot().model.revision;
  assert.equal(snapshot().model.holds.length, 0);
  const words = 'Yes, I confirm: we predict before the first reminder is sent, "as stated".';
  await c.handle({ type: 'confirm', proposalId: 'p_1', words, revision: rev - 1 });
  assert.equal(outcome().refusal.code, 'stale_revision');
  assert.ok(outcome().refusal.details.includes(`Current revision: ${rev}`));
  await c.handle({ type: 'confirm', proposalId: 'p_1', words, revision: rev });
  const o = outcome();
  assert.equal(o.kind, 'confirmed', JSON.stringify(o));
  assert.equal(o.revision, rev + 1);
  assert.equal(o.channel, 'webview');
  assert.equal(o.userWords, words);
  const confirmation = status().view.decisions.prediction_time.confirmation;
  assert.equal(confirmation.channel, 'webview');
  assert.equal(confirmation.actor, 'user');
  assert.equal(confirmation.user_words, words);
  assert.equal(confirmation.basis, 'explicit');
  assert.equal(confirmation.authenticated, false);
  assert.equal(snapshot().model.revision, rev + 1);
  assert.equal(snapshot().model.proposals.length, 0);
});

test('a change made in the chat reaches the panel through the file watch', { skip }, async () => {
  const { c, snapshot } = controller();
  await c.handle({ type: 'ready' });
  const rev = snapshot().model.revision;
  const watcher = watchStudy(studyDir, () => c.refresh(), { debounceMs: 100 });
  try {
    const propose = hyp('decide', 'propose', 'prediction_time', '--value', 'when the membership expires',
      '--restatement', 'You predict when the membership expires.', '--rationale', 'A new scenario.',
      '--request-id', 'chat-4', '--expected-revision', String(rev));
    assert.equal(propose.ok, true, JSON.stringify(propose));
    const deadline = Date.now() + 10000;
    while (Date.now() < deadline && !(snapshot() && snapshot().model.revision > rev)) {
      await new Promise(r => setTimeout(r, 50));
    }
    assert.equal(snapshot().model.revision, rev + 1);
    assert.equal(snapshot().model.proposals[0].restatement, 'You predict when the membership expires.');
  } finally {
    watcher.dispose();
  }
});

test('withdraw through the panel', { skip }, async () => {
  const { c, outcome, snapshot } = controller();
  await c.handle({ type: 'ready' });
  const p = snapshot().model.proposals[0];
  await c.handle({ type: 'withdraw', proposalId: p.proposalId, reason: null, revision: snapshot().model.revision });
  assert.equal(outcome().kind, 'withdrawn', JSON.stringify(outcome()));
  assert.equal(snapshot().model.proposals.length, 0);
});
