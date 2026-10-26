'use strict';
// Decisions tests (scope U, WP-U2; COMPANION-ADVANCED §6.2, INV-4, INV-8; WP-E1: no W1, no W2):
// the DecisionsModel and EffectsModel on the WP-0 fixtures, the decisions handler through
// the real controller with the fixture CLI (test/fixture-cli.js), and the refusal
// explanations of lib/refusals.js. No process is started; the webview side is in
// test_webview_decisions.py.

const test = require('node:test');
const assert = require('node:assert/strict');
const { createController } = require('../lib/controller');
const { toDecisionsModel, DECISIONS_KEYS, availabilityGroups } = require('../lib/models/decisions');
const { toEffectsModel, EFFECTS_KEYS } = require('../lib/models/effects');
const { ModelError } = require('../lib/models/common');
const refusals = require('../lib/refusals');
const { fakeCli, payload } = require('./fixture-cli');

const AGENT = { argv: ['/opt/py env/bin/python', '-m', 'mlkit.study.cli'], studyDir: '/studies/bank marketing "demo"' };
const UUIDS = ['0f8fad5b-d9cb-469f-a165-70867728950e', '7c9e6679-7425-40de-944b-e07fc1f90ae7', '9b2e7c1a-4d3f-4a8b-9c6d-1e2f3a4b5c6d'];
const TAIL = ['--json', '--study', AGENT.studyDir];

function make({ settings = { stage: 'v1' }, route, task = 'binary' } = {}) {
  const posted = [];
  const runCli = fakeCli(route, { agentArgv: AGENT.argv, task });
  let n = 0;
  const c = createController({ agent: AGENT, post: m => posted.push(m), runCli, settings, exists: () => true,
    uuid: () => UUIDS[n++ % UUIDS.length] });
  const tails = () => runCli.calls.map(x => x.tail);
  return { c, posted, runCli, tails, last: type => posted.filter(m => m.type === type).at(-1) };
}

// --- models ---------------------------------------------------------------------------------

test('DecisionsModel: keys, history newest first (DH-1, R25)', () => {
  const m = toDecisionsModel(payload('decisions.binary'));
  assert.deepEqual(Object.keys(m), DECISIONS_KEYS);
  assert.equal(m.revision, 27);
  assert.equal(m.task, 'binary');
  assert.deepEqual(m.history.map(h => `${h.decisionId}:${h.revision}`),
    ['policy:27', 'policy:23', 'split:7', 'feature_availability:5', 'prediction_time:3']);
  const split = m.history.find(h => h.decisionId === 'split');
  assert.equal(split.basis, 'delegated_default');
  assert.equal(split.scope, 'this_decision');
  assert.equal(split.channel, 'chat');
  const old = m.history.find(h => h.revision === 23);
  assert.equal(old.current, false);
  assert.equal(old.supersededAt, 27);
  assert.equal(m.history.find(h => h.revision === 27).channel, 'webview');
  assert.equal(m.history.at(-1).title, 'Define the prediction moment');
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
  const { decision_id: id, revision } = p.history[0];
  delete p.history[0].basis;
  delete p.history[0].channel;
  const h = toDecisionsModel(p).history.find(x => x.decisionId === id && x.revision === revision);
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
  assert.ok(m.history.some(h => h.userWords === 'Before the call <img src=x onerror=alert(1)> and <b>nothing</b> else.'));
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

// --- no W1, no W2 (v0.3 narrowing, ADR 0004 amendment; R23, I2) ---------------------------------

test('WP-E1: confirm and withdraw are no messages any more: dropped unanswered, no `decide` process, at every stage', async () => {
  for (const settings of [{ stage: 'v0' }, { stage: 'v1' }, { stage: 'v3' }, { stage: 'v1', reviewer: true }]) {
    const { c, posted, tails } = make({ settings });
    await c.handle({ v: 2, type: 'ready' });
    const before = tails().length;
    await c.handle({ v: 2, type: 'confirm', proposalId: 'p_5', words: 'Yes: call the 100 best-scored clients.', revision: 26 });
    await c.handle({ v: 2, type: 'withdraw', proposalId: 'p_5', revision: 26 });
    assert.equal(c.diagnostics().ignored, 2, JSON.stringify(settings));
    assert.equal(posted.filter(m => m.type === 'outcome').length, 0);
    assert.ok(!tails().some(t => t[0] === 'decide'), 'no decide command');
    assert.equal(tails().length, before);
  }
  // The handler has no write at all: only the preview of effects.
  assert.deepEqual(Object.keys(require('../lib/handlers/decisions').types), ['preview_effects']);
});

test('reviewer: effects and history still read', async () => {
  const { c, tails } = make({ settings: { stage: 'v1', reviewer: true } });
  await c.handle({ v: 2, type: 'ready' });
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
    ['run', 'ambiguous_confirmation', 'bare_acknowledgement'],
    ['run', 'stale_revision', null], ['export', 'export_target_exists', null], ['render', 'read_only', null],
    ['decide confirm', 'nonexistent_code', null]]) {
    const d = refusals.describe(error(command, code, 'engine text', reason ? { reason } : {}));
    assert.ok(d.human.endsWith(' Nothing was recorded.'), d.human);
    assert.equal(d.engineMessage, 'engine text', 'the engine message is kept verbatim');
  }
});

test('refusal contexts: W4 run, W6 acknowledge, W7 export, from the payload command (no W3 since v0.3)', () => {
  assert.equal(refusals.BY_CONTEXT.propose, undefined);
  assert.equal(refusals.contextOf({ command: 'decide propose' }, 'stale_revision', null, {}), null);
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

test('training mode refusals (ADR 0005, WP-B2): paraphrase_required names what is not said, words_contradict_value the variable', () => {
  const para = refusals.describe(error('decide confirm', 'paraphrase_required', 'In the training mode ...', {
    decision_id: 'prediction_time', mode: 'training',
    missing: [{ concept: 'timing_before', hint: 'when the score is computed, relative to the event (before it)' },
      { concept: 'event', hint: 'the event the prediction moment refers to' }],
  }));
  assert.equal(para.code, 'paraphrase_required');
  assert.match(para.human, /^In the training mode, a confirmation says in your own words/);
  assert.ok(para.human.endsWith(' Nothing was recorded.'));
  assert.deepEqual(para.details, ['Not said yet: when the score is computed, relative to the event (before it)',
    'Not said yet: the event the prediction moment refers to']);
  const contra = refusals.describe(error('decide confirm', 'words_contradict_value', 'In the training mode ...', {
    warnings: [{ code: 'words_contradict_value', variable: 'contact', said: 'exclude', value: 'available_at_prediction' }],
  }));
  assert.match(contra.human, /the engine stopped the confirmation/);
  assert.deepEqual(contra.details, ['Your words and the proposal disagree about contact']);
});

test('decisions model (v0.3, WP-B): reason_given reaches the current history row only', () => {
  const p = JSON.parse(JSON.stringify(payload('decisions.binary')));
  const policy = p.decisions.find(d => d.decision_id === 'policy');
  assert.equal(toDecisionsModel(p).decisions.find(d => d.decisionId === 'policy').confirmation.reasonGiven, true);
  policy.confirmation.reason_given = false;
  const m = toDecisionsModel(p);
  const rows = m.history.filter(h => h.decisionId === 'policy');
  assert.ok(rows.length >= 1);
  for (const h of rows) {
    assert.equal(h.reasonGiven, h.current && h.revision === policy.confirmation.revision ? false : null);
  }
  delete policy.confirmation.reason_given;
  assert.equal(toDecisionsModel(p).decisions.find(d => d.decisionId === 'policy').confirmation.reasonGiven, null);
});

test('refusals (v0.3, WP-B): the delegated final-test opening has its own explanation', () => {
  const d = refusals.describe({ schema: 'hypotrail.error/1', ok: false, command: 'decide confirm',
    error: { code: 'ambiguous_confirmation', message: 'engine text', details: { reason: 'delegation_not_allowed' } } });
  assert.equal(d.reason, 'delegation_not_allowed');
  assert.match(d.human, /never delegated/);
});

// --- R16 (owner session 2026-10-26, D20): a choice the chat waits for -------------------------

const fs = require('node:fs');
const path = require('node:path');
const { toSummaryModel } = require('../lib/models/summary');

/** The captured binary summary with the conclusion as a choice the chat asks (L1's key). */
function choiceSummary(options) {
  const raw = JSON.parse(JSON.stringify(payload('captured/summary.binary.cv.opening')));
  raw.next_action = { kind: 'propose', step: 'conclusion', decision: 'conclusion', message: 'Propose the conclusion.',
    audience: 'agent', junior_message: 'The assistant asks you to choose the conclusion.', choice_options: options };
  return raw;
}

test('DC-13: the summary carries the choice the chat asks, labels verbatim, malformed options dropped', () => {
  const options = [
    { id: 'adopt_policy', value: 'adopt_policy', label: 'Adopter la règle' },
    { id: 'keep_baseline', value: 'keep_baseline', label: 'Garder la référence' },
    { id: 'inconclusive', value: 'inconclusive', label: 'Ne pas conclure (non concluant)' },
    { id: '', value: 'x', label: 'no id' }, { id: 'no_label', value: 'y' }, 'adopt', null,
  ];
  const m = toSummaryModel(choiceSummary(options));
  assert.deepEqual(m.nextAction.choiceOptions, options.slice(0, 3));
  assert.equal(m.nextAction.decision, 'conclusion');
  // A model choice value is shown as text (a slot), never parsed; no choice reads as [].
  const slot = toSummaryModel(choiceSummary([{ id: 'fit.variant:2', value: 'fit.variant:2', label: 'La deuxième variante' }]));
  assert.deepEqual(slot.nextAction.choiceOptions.map(o => o.value), ['fit.variant:2']);
  assert.deepEqual(toSummaryModel(payload('captured/summary.binary.cv')).nextAction.choiceOptions, []);
  // The badge still counts the open proposals only: a choice is answered in the chat.
  assert.equal(m.waitingCount, toSummaryModel(payload('captured/summary.binary.cv.opening')).waitingCount);
});

test('DC-13: the choice card is read only: no write control, no words field, only the copy-only ask button', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'media', 'views', 'decisions.js'), 'utf8');
  const start = source.indexOf('function choiceCard(');
  const body = source.slice(start, source.indexOf('\n  }\n', start));
  assert.ok(start > 0 && body.includes("ctx.atLeast('v1')"), 'from v1 only (D20)');
  for (const forbidden of ['data-write', 'wordsArea', 'textarea', 'HT.send', 'ctx.send', "type: 'button'", 'onclick']) {
    assert.ok(!body.includes(forbidden), forbidden);
  }
  assert.match(body, /HT\.askButton\([^)]*\{ kind: 'decision', id \}/);
  assert.match(body, /direct: true/);
});

test('DC-13 (W1 integration): the captured conclusion of a real study is a choice; its values read as verdicts', () => {
  const raw = payload('captured/summary.binary.cv.conclusion');
  const m = toSummaryModel(raw);
  assert.deepEqual(m.nextAction.choiceOptions.map(o => [o.id, o.label]), raw.next_action.choice_options.map(o => [o.id, o.label]));
  assert.deepEqual(m.nextAction.choiceOptions.map(o => o.value), raw.next_action.choice_options.map(o => o.value.verdict));
  assert.equal(raw.next_action.pause.kind, 'choice');
});

test('DC-13 (W1 integration): a conclusion option from the engine has the value {verdict}; it reads as its verdict', () => {
  const engine = [{ id: 'keep_baseline', value: { verdict: 'keep_baseline' }, label: 'Keep the baseline' },
    { id: 'inconclusive', value: { verdict: 'inconclusive' }, label: 'Do not conclude (inconclusive)' }];
  const m = toSummaryModel(choiceSummary(engine));
  assert.deepEqual(m.nextAction.choiceOptions.map(o => o.value), ['keep_baseline', 'inconclusive']);
  assert.ok(!m.nextAction.choiceOptions.some(o => o.value.includes('{')));
});
