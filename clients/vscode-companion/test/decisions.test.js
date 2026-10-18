'use strict';
// Decisions tests (scope U, WP-U2; COMPANION-ADVANCED §6.2, §7 W1 W2, INV-4, INV-5, INV-8):
// the DecisionsModel and EffectsModel on the WP-0 fixtures, the decisions handler through
// the real controller with the fixture CLI (test/fixture-cli.js), and the refusal
// explanations of lib/refusals.js. No process is started; the webview side is in
// test_webview_decisions.py.

const test = require('node:test');
const assert = require('node:assert/strict');
const { createController, UNKNOWN_OUTCOME } = require('../lib/controller');
const { toDecisionsModel, DECISIONS_KEYS, availabilityGroups } = require('../lib/models/decisions');
const { toEffectsModel, EFFECTS_KEYS } = require('../lib/models/effects');
const { ModelError } = require('../lib/models/common');
const refusals = require('../lib/refusals');
const { fakeCli, payload } = require('./fixture-cli');

const AGENT = { argv: ['/opt/py env/bin/python', '-m', 'mlkit.study.cli'], studyDir: '/studies/bank marketing "demo"' };
const UUIDS = ['0f8fad5b-d9cb-469f-a165-70867728950e', '7c9e6679-7425-40de-944b-e07fc1f90ae7', '9b2e7c1a-4d3f-4a8b-9c6d-1e2f3a4b5c6d'];
const TAIL = ['--json', '--study', AGENT.studyDir];

function make({ settings = { stage: 'v1' }, route, task = 'binary', withdrawAnswer = true } = {}) {
  const posted = [];
  const asked = [];
  const runCli = fakeCli(route, { agentArgv: AGENT.argv, task });
  let n = 0;
  const c = createController({ agent: AGENT, post: m => posted.push(m), runCli, settings, exists: () => true,
    confirmWithdraw: async p => { asked.push(p); return withdrawAnswer; }, uuid: () => UUIDS[n++ % UUIDS.length] });
  const tails = () => runCli.calls.map(x => x.tail);
  return { c, posted, runCli, asked, tails, last: type => posted.filter(m => m.type === type).at(-1) };
}

// --- models ---------------------------------------------------------------------------------

test('DecisionsModel: keys, history grouped by decision in plan order, newest first (DH-1)', () => {
  const m = toDecisionsModel(payload('decisions.binary'));
  assert.deepEqual(Object.keys(m), DECISIONS_KEYS);
  assert.equal(m.revision, 27);
  assert.equal(m.task, 'binary');
  assert.deepEqual(m.history.map(h => `${h.decisionId}:${h.revision}`),
    ['prediction_time:3', 'feature_availability:5', 'split:7', 'policy:27', 'policy:23']);
  const split = m.history.find(h => h.decisionId === 'split');
  assert.equal(split.basis, 'delegated_default');
  assert.equal(split.scope, 'this_decision');
  assert.equal(split.channel, 'chat');
  const old = m.history.find(h => h.revision === 23);
  assert.equal(old.current, false);
  assert.equal(old.supersededAt, 27);
  assert.equal(m.history.find(h => h.revision === 27).channel, 'webview');
  assert.equal(m.history[0].title, 'Define the prediction moment');
  // Proposals that were not confirmed: withdrawn and superseded only.
  assert.deepEqual(m.unconfirmedProposals.map(p => [p.proposalId, p.status, p.closedReason]), [['p_6', 'withdrawn', 'withdrawn']]);
  assert.deepEqual(m.queue, []);
  assert.equal(m.notes[0].resolutionWords, 'my manager says the team can make 100 calls per wave');
  // Availability values are grouped by status for display, columns in the engine's order.
  const fa = m.history.find(h => h.decisionId === 'feature_availability');
  assert.deepEqual(fa.groups.map(g => g.status), ['available_at_prediction', 'uncertain_included', 'not_available']);
  assert.deepEqual(fa.groups.at(-1).columns, ['campaign', 'day', 'duration', 'month']);
  assert.equal(availabilityGroups('capacity:100'), null);
  assert.throws(() => toDecisionsModel(payload('preview_effects.binary')), ModelError);
  assert.throws(() => toDecisionsModel(payload('error.stale_revision')), ModelError);
});

test('DecisionsModel: a record without basis reads explicit, without channel reads chat (CC §2)', () => {
  const p = JSON.parse(JSON.stringify(payload('decisions.binary')));
  delete p.history[0].basis;
  delete p.history[0].channel;
  const h = toDecisionsModel(p).history[0];
  assert.equal(h.basis, 'explicit');
  assert.equal(h.channel, 'chat');
});

test('RQ-1: every reconfirm_required decision is queued once, with its previous words verbatim', () => {
  const raw = payload('decisions.binary.reconfirm');
  const m = toDecisionsModel(raw);
  const required = raw.decisions.filter(d => d.status === 'reconfirm_required').map(d => d.decision_id);
  assert.ok(required.length >= 1);
  assert.deepEqual(m.queue.map(q => q.decisionId).sort(), [...new Set(required)].sort());
  const q = m.queue[0];
  assert.equal(q.title, 'Conclude proportionately');
  assert.equal(q.reason, 'policy changed: capacity:100 replaces threshold:0.2');
  assert.equal(q.previous.userWords, 'We adopt the threshold policy for the next wave, knowing the figures are optimistic.');
  assert.equal(q.previous.basis, 'explicit');
  assert.equal(q.previous.channel, 'chat');
  assert.equal(q.openProposal, null);
  assert.equal(q.sinceRevision, 27);
});

test('DH-2: words and restatements are copied verbatim, markup included (rendered as text)', () => {
  const m = toDecisionsModel(payload('decisions.binary.injection'));
  assert.equal(m.history[0].userWords, 'Before the call <img src=x onerror=alert(1)> and <b>nothing</b> else.');
  const raw = payload('decisions.binary.injection');
  for (const h of raw.history) assert.ok(m.history.some(x => x.userWords === h.user_words));
});

test('EffectsModel: kept fits, decisions to confirm again, blocked refusals, first confirmation, split (DC-2, DC-4)', () => {
  const titles = { conclusion: 'Conclude proportionately', policy: 'Choose a decision policy' };
  const base = toEffectsModel(payload('preview_effects.binary'), { titles });
  assert.deepEqual(Object.keys(base), EFFECTS_KEYS);
  assert.equal(base.available, true);
  assert.equal(base.kept.fitsAllKept, true);
  assert.deepEqual(base.kept.fits, ['fit.baseline', 'fit.logistic']);
  assert.deepEqual(base.reconfirm, []);
  assert.deepEqual(base.regenerated, ['report', 'notebook']);
  assert.equal(base.firstConfirmation, false);
  assert.equal(base.previous.userWords, 'Yes, call everyone scored at 0.2 or more');
  assert.equal(base.note, 'Preview of a confirmation: nothing was recorded. The engine still checks the words when you confirm.');

  const again = toEffectsModel(payload('preview_effects.binary.reconfirm'), { titles });
  assert.deepEqual(again.reconfirm, [{ id: 'conclusion', title: 'Conclude proportionately' }]);
  assert.deepEqual(toEffectsModel(payload('preview_effects.binary.reconfirm')).reconfirm, [{ id: 'conclusion', title: 'conclusion' }]);

  const blocked = toEffectsModel(payload('preview_effects.binary.blocked'));
  assert.equal(blocked.blocked.length, 1);
  assert.equal(blocked.blocked[0].code, 'decision_on_hold');
  assert.equal(blocked.blocked[0].message, "This decision is on hold in the junior's own words; resolve the note first.");

  const first = toEffectsModel(payload('preview_effects.binary.first'));
  assert.equal(first.firstConfirmation, true);
  assert.equal(first.previous, null);
  assert.equal(first.kept.fitsAllKept, false);

  const split = toEffectsModel(payload('preview_effects.binary.split'));
  assert.equal(split.kept.fitsAllKept, false);
  assert.ok(split.stale.includes('fit.logistic'));
  assert.deepEqual(split.refit, ['fit.baseline', 'fit.logistic']);
  assert.equal(split.staleResults, 7);
  assert.deepEqual(split.reconfirm.map(r => r.id), ['policy']);

  const regression = toEffectsModel(payload('preview_effects.regression'));
  assert.equal(regression.kept.fitsAllKept, true);
  assert.equal(regression.firstConfirmation, true);
  assert.throws(() => toEffectsModel(payload('decisions.binary')), ModelError);
});

// --- handler: load, preview_effects -----------------------------------------------------------

test('load: decisions at v1 reads `decisions` once per revision and answers the DecisionsModel', async () => {
  const { c, posted, tails } = make();
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'load', view: 'decisions' });
  await c.handle({ v: 2, type: 'load', view: 'decisions' });
  assert.deepEqual(tails().filter(t => t[0] === 'decisions'), [['decisions', ...TAIL]]);
  const data = posted.filter(m => m.type === 'view_data' && m.view === 'decisions');
  assert.equal(data.length, 2);
  assert.deepEqual(data[0].model, toDecisionsModel(payload('decisions.binary')));
  assert.equal(data[0].revision, 27);
  assert.equal(c.diagnostics().dropped, 0, JSON.stringify(c.diagnostics().invalid));
  // An engine without C2 answers its refusal as a load error of the view.
  const old = make({ route: t => (t[0] === 'decisions' ? { payload: { ...payload('error.not_implemented'),
    error: { code: 'unsupported_capability', message: 'decisions is reserved.', details: { command: 'decisions', reason: 'not_implemented' } } } } : undefined) });
  await old.c.handle({ v: 2, type: 'ready' });
  await old.c.handle({ v: 2, type: 'load', view: 'decisions' });
  assert.deepEqual(old.last('load_error'), { v: 2, type: 'load_error', view: 'decisions', message: 'unsupported_capability: decisions is reserved.', detail: '' });
});

test('preview_effects: exact read argv, cached per proposal and revision, titles from the plan', async () => {
  const { c, posted, tails } = make({ route: t => (t[1] === 'effects' ? 'preview_effects.binary.reconfirm' : undefined) });
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'preview_effects', proposalId: 'p_5', revision: 26 });
  await c.handle({ v: 2, type: 'preview_effects', proposalId: 'p_5', revision: 26 });
  assert.deepEqual(tails().filter(t => t[0] === 'preview'), [['preview', 'effects', 'p_5', ...TAIL]]);
  const effects = posted.filter(m => m.type === 'effects');
  assert.equal(effects.length, 2);
  assert.equal(effects[0].proposalId, 'p_5');
  assert.equal(effects[0].revision, 26);
  assert.deepEqual(effects[0].model.reconfirm, [{ id: 'conclusion', title: 'Conclude proportionately' }]);
  assert.equal(effects[0].model.kept.fitsAllKept, true);
  // Nothing is a write: no request id, no revision, no busy message.
  assert.ok(!tails().some(t => t.includes('--request-id')));
  assert.equal(posted.filter(m => m.type === 'busy').length, 0);
});

test('preview_effects: a proposal the snapshot does not hold is never read; v0 ignores the message', async () => {
  const { c, posted, tails } = make();
  await c.handle({ v: 2, type: 'ready' });
  const before = tails().length;
  await c.handle({ v: 2, type: 'preview_effects', proposalId: 'p_99', revision: 26 });
  assert.equal(tails().length, before);
  assert.equal(posted.filter(m => m.type === 'effects').length, 0);
  const v0 = make({ settings: { stage: 'v0' } });
  await v0.c.handle({ v: 2, type: 'ready' });
  await v0.c.handle({ v: 2, type: 'preview_effects', proposalId: 'p_5', revision: 26 });
  assert.equal(v0.c.diagnostics().ignored, 1);
  assert.ok(!v0.tails().some(t => t[0] === 'preview'));
});

test('preview_effects: an engine refusal answers an unavailable preview with the engine message verbatim', async () => {
  const { c, last } = make({ route: t => (t[1] === 'effects' ? { payload: { schema: 'hypotrail.error/1', ok: false, command: 'preview',
    error: { code: 'unsupported_capability', message: 'preview effects is reserved for the advanced companion and is not implemented in this version. Nothing was read or written.',
      details: { command: 'preview effects', reason: 'not_implemented' } } }, exitCode: 2 } : undefined) });
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'preview_effects', proposalId: 'p_5', revision: 26 });
  const e = last('effects');
  assert.equal(e.model.available, false);
  assert.equal(e.model.code, 'unsupported_capability');
  assert.equal(e.model.reason, 'not_implemented');
  assert.match(e.model.message, /preview effects is reserved for the advanced companion and is not implemented in this version\. Nothing was read or written\.$/);
  assert.equal(e.revision, 26);
  // A failed process (no JSON) answers the same way.
  const broken = make({ route: t => (t[1] === 'effects' ? { failure: 'The hypotrail CLI printed no JSON.' } : undefined) });
  await broken.c.handle({ v: 2, type: 'ready' });
  await broken.c.handle({ v: 2, type: 'preview_effects', proposalId: 'p_5', revision: 26 });
  assert.equal(broken.last('effects').model.available, false);
  assert.match(broken.last('effects').model.message, /printed no JSON/);
});

// --- handler: W1 and W2 ---------------------------------------------------------------------

test('DC-3: the confirm argv is exactly W1, with a fresh request id per submission, then a refresh', async () => {
  const { c, posted, tails, last } = make();
  await c.handle({ v: 2, type: 'ready' });
  const words = 'Yes: we can make 100 calls per wave, so call the 100 best-scored clients.';
  await c.handle({ v: 2, type: 'confirm', proposalId: 'p_5', words, revision: 26 });
  const confirm = tails().find(t => t[0] === 'decide');
  assert.deepEqual(confirm, ['decide', 'confirm', 'p_5', `--user-words=${words}`, '--channel', 'webview', '--actor', 'user',
    '--request-id', UUIDS[0], '--expected-revision', '26', ...TAIL]);
  assert.ok(!confirm.some(a => a.startsWith('--basis') || a.startsWith('--delegation-scope')), 'INV-4: never a delegation');
  const o = last('outcome');
  assert.equal(o.op, 'W1');
  assert.equal(o.kind, 'ok');
  assert.equal(o.target, 'p_5');
  assert.equal(o.recorded.userWords, words);
  assert.equal(o.recorded.channel, 'webview');
  assert.equal(o.recorded.decisionId, 'policy');
  const after = tails().slice(tails().indexOf(confirm) + 1);
  assert.equal(after[0][0], 'status', 'refreshed after the write');
  assert.deepEqual(posted.filter(m => m.type === 'busy').map(m => m.busy), [true, false]);
  await c.handle({ v: 2, type: 'confirm', proposalId: 'p_5', words: 'Again, the 100 best-scored clients per wave.', revision: 26 });
  const ids = tails().filter(t => t[0] === 'decide').map(t => t[t.indexOf('--request-id') + 1]);
  assert.equal(new Set(ids).size, 2, 'a new request id per submission');
});

test('DC-3: a stale revision is the v0 stale display (code, verbatim message, the diff) and a refresh', async () => {
  const { c, tails, last } = make({ route: t => (t[0] === 'decide' ? 'error.stale_revision' : undefined) });
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'confirm', proposalId: 'p_5', words: 'Yes, the 100 best-scored clients.', revision: 25 });
  const o = last('outcome');
  assert.equal(o.kind, 'refused');
  assert.equal(o.refusal.code, 'stale_revision');
  assert.equal(o.refusal.engineMessage, 'Revision is stale: reread hypotrail status before deciding');
  assert.deepEqual(o.refusal.details, ['Revision read by the panel: 25', 'Current revision: 26',
    'Changed at revision 26: decide.propose (policy)']);
  assert.match(o.refusal.human, /read the proposal again before answering\. Nothing was recorded\.$/);
  const i = tails().findIndex(t => t[0] === 'decide');
  assert.equal(tails()[i + 1][0], 'status');
});

test('DC-2, INV-5: blank words, a proposal that is not open, or a malformed message never reach the CLI', async () => {
  const { c, posted, tails } = make();
  await c.handle({ v: 2, type: 'ready' });
  const before = tails().length;
  await c.handle({ v: 2, type: 'confirm', proposalId: 'p_5', words: ' \n\t ', revision: 26 });
  assert.equal(posted.at(-1).kind, 'invalid');
  assert.equal(posted.at(-1).message, 'Type your own answer first. Nothing was recorded.');
  await c.handle({ v: 2, type: 'confirm', proposalId: 'p_4', words: 'Yes, the linear model.', revision: 26 });
  assert.equal(posted.filter(m => m.type === 'outcome').at(-1).message, 'This proposal is not open in the panel any more. Nothing was recorded.');
  for (const bad of [{ basis: 'delegated_default' }, { delegationScope: 'standing' }, { words: 'x'.repeat(4001) }, { revision: 0 }]) {
    await c.handle({ v: 2, type: 'confirm', proposalId: 'p_5', words: 'Yes, the 100 best-scored clients.', revision: 26, ...bad });
  }
  assert.equal(c.diagnostics().ignored, 4);
  assert.ok(!tails().slice(before).some(t => t[0] === 'decide'));
});

test('INV-8: a write without a JSON answer is "outcome unknown", never a success, then a refresh', async () => {
  const { c, tails, last } = make({ route: t => (t[0] === 'decide' ? { failure: 'The hypotrail CLI timed out.' } : undefined) });
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'confirm', proposalId: 'p_5', words: 'Yes, the 100 best-scored clients.', revision: 26 });
  const o = last('outcome');
  assert.equal(o.kind, 'failed');
  assert.equal(o.target, 'p_5');
  assert.ok(o.message.endsWith(UNKNOWN_OUTCOME), o.message);
  assert.equal(o.recorded, undefined);
  const i = tails().findIndex(t => t[0] === 'decide');
  assert.equal(tails()[i + 1][0], 'status');
});

test('INV-4: a typed delegation is refused by the engine and the panel says to delegate in the chat', async () => {
  const { c, tails, last } = make({ route: t => (t[0] === 'decide' ? 'error.delegation_needs_basis' : undefined) });
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'confirm', proposalId: 'p_5', words: 'Go with your recommended default.', revision: 26 });
  const argv = tails().find(t => t[0] === 'decide');
  assert.ok(!argv.some(a => /^--(basis|delegation-scope)/.test(a)));
  const o = last('outcome');
  assert.equal(o.refusal.reason, 'delegation_needs_basis');
  assert.equal(o.refusal.human, 'Your reply hands the choice to the assistant. A delegation is recorded in the chat, not in this panel. Nothing was recorded.');
  assert.equal(o.refusal.engineMessage, 'The reply delegates the choice; record it with --basis delegated_default in the chat.');
});

test('W2: the VS Code modal asks first; "Withdraw" runs exactly W2, a cancel records nothing', async () => {
  const yes = make();
  await yes.c.handle({ v: 2, type: 'ready' });
  await yes.c.handle({ v: 2, type: 'withdraw', proposalId: 'p_5', revision: 26 });
  assert.equal(yes.asked.length, 1);
  assert.equal(yes.asked[0].proposalId, 'p_5');
  assert.equal(yes.asked[0].decisionTitle, 'Choose a decision policy');
  assert.deepEqual(yes.tails().find(t => t[0] === 'decide'), ['decide', 'withdraw', 'p_5', '--request-id', UUIDS[0],
    '--expected-revision', '26', ...TAIL]);
  assert.deepEqual(yes.last('outcome').recorded, { proposalId: 'p_5', decisionId: 'policy', status: 'withdrawn' });
  const no = make({ withdrawAnswer: false });
  await no.c.handle({ v: 2, type: 'ready' });
  await no.c.handle({ v: 2, type: 'withdraw', proposalId: 'p_5', revision: 26 });
  assert.ok(!no.tails().some(t => t[0] === 'decide'));
  assert.deepEqual(no.last('outcome'), { v: 2, type: 'outcome', op: 'W2', kind: 'cancelled', target: 'p_5', message: 'Nothing was recorded.' });
});

test('reviewer: W1 and W2 are refused before any modal or process; effects and history still read', async () => {
  const { c, posted, asked, tails } = make({ settings: { stage: 'v1', reviewer: true } });
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'confirm', proposalId: 'p_5', words: 'Yes, the 100 best-scored clients.', revision: 26 });
  await c.handle({ v: 2, type: 'withdraw', proposalId: 'p_5', revision: 26 });
  assert.deepEqual(posted.filter(m => m.type === 'outcome').map(o => [o.op, o.kind, o.message]),
    [['W1', 'invalid', 'Read-only reviewer mode.'], ['W2', 'invalid', 'Read-only reviewer mode.']]);
  assert.equal(asked.length, 0);
  await c.handle({ v: 2, type: 'preview_effects', proposalId: 'p_5', revision: 26 });
  await c.handle({ v: 2, type: 'load', view: 'decisions' });
  assert.deepEqual(tails().map(t => t[0]), ['status', 'preview', 'decisions']);
});

// --- refusal explanations (INV-8, CW.8) ----------------------------------------------------------

function error(command, code, message, details = {}) {
  return { schema: 'hypotrail.error/1', ok: false, command, error: { code, message, details } };
}

test('INV-8: refusal explanations never suggest words: no quotation, no example, always "Nothing was recorded."', () => {
  const tables = [refusals.BY_REASON, refusals.BY_CODE, ...Object.values(refusals.BY_CONTEXT)];
  for (const table of tables) {
    for (const [key, text] of Object.entries(table)) {
      assert.doesNotMatch(text, /["“”«»]|\be\.g\.|for example|for instance|such as|\btype\b|\bwrite\b|\bsay that\b|\btry (typing|writing|saying)\b/i, key);
    }
  }
  for (const [command, code, reason] of [['decide confirm', 'ambiguous_confirmation', 'bare_acknowledgement'],
    ['run', 'ambiguous_confirmation', 'bare_acknowledgement'], ['decide propose', 'stale_revision', null],
    ['run', 'stale_revision', null], ['export', 'export_target_exists', null], ['render', 'read_only', null],
    ['decide confirm', 'nonexistent_code', null]]) {
    const d = refusals.describe(error(command, code, 'engine text', reason ? { reason } : {}));
    assert.ok(d.human.endsWith(' Nothing was recorded.'), d.human);
    assert.equal(d.engineMessage, 'engine text', 'the engine message is kept verbatim');
  }
});

test('refusal contexts: W3 propose, W4 run, W6 acknowledge, W7 export, from the payload command', () => {
  const p = refusals.describe(error('decide propose', 'stale_revision', 'Revision is stale.'));
  assert.match(p.human, /look at the draft again before proposing/);
  const c = refusals.describe(error('decide confirm', 'stale_revision', 'Revision is stale.'));
  assert.match(c.human, /read the proposal again before answering/);
  const run = refusals.describe(error('run', 'stale_revision', 'Revision is stale.'));
  assert.match(run.human, /before asking for a chart/);
  const ack = refusals.describe(error('run', 'ambiguous_confirmation', 'A bare acknowledgement is not an acknowledgement.',
    { reason: 'bare_acknowledgement', execution_id: 'e_1' }));
  assert.match(ack.human, /acknowledged the interruption/);
  assert.equal(refusals.contextOf({ command: 'run' }, 'unknown_execution', null, {}), 'acknowledge');
  assert.equal(refusals.contextOf({ command: 'run' }, 'precondition_missing', null, {}), 'run');
  assert.equal(refusals.contextOf({ command: 'run' }, 'execution_in_progress', null, { execution_id: 'e_1' }), 'run');
  const exp = refusals.describe(payload('error.export_target_exists'));
  assert.equal(exp.code, 'export_target_exists');
  assert.match(exp.human, /^The chosen folder already holds files/);
  assert.deepEqual(exp.details, ['Folder: /studies/bank marketing "demo"/handoff/revision-26']);
  const pending = refusals.describe(error('run', 'interrupted_execution_pending', 'An execution has an unknown outcome.',
    { interrupted: [{ execution_id: 'e_8', activity: 'fit.logistic' }] }));
  assert.deepEqual(pending.details, ['Unknown outcome: e_8 (fit.logistic)']);
  // The v0 explanations are unchanged.
  const hold = refusals.describe(payload('error.decision_on_hold'));
  assert.equal(hold.human, 'This decision is on hold in your own words. Resolve the hold in the chat before confirming. Nothing was recorded.');
  assert.deepEqual(hold.details, ['On hold (n_1): "don\'t adopt anything until I bring my manager\'s figure"']);
});
