'use strict';
// Learn & hand off tests (scope U, WP-U5; COMPANION-ADVANCED §6.6, §6.7, §10): the explain
// and session-report models and loads, learn_set (globalState only, LE-1 to LE-3), the
// handoff export (W7: HO-1, HO-2 read with CA.9, exit 3), navigate_external, and the term
// map of media/terms.js. Controller with the fixture CLI, then the extension with the fake
// `vscode` module and a fake execFile. No VS Code, no CLI process.

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const childProcess = require('child_process');
const { createController } = require('../lib/controller');
const { toExplainModel } = require('../lib/models/explain');
const { toSessionReportModel } = require('../lib/models/session_report');
const { ModelError } = require('../lib/models/common');
const localstore = require('../lib/localstore');
const learn = require('../lib/handlers/learn');
const { createFake, load, memento } = require('./fake-vscode');
const { fakeCli, payload, fixture, defaultRoute } = require('./fixture-cli');

const AGENT = { argv: ['/opt/py/bin/python', '-m', 'mlkit.study.cli'], studyDir: '/studies/bank marketing "demo"' };
const UUID = '0f8fad5b-d9cb-469f-a165-70867728950e';

function make({ settings = {}, host = {}, route, task = 'binary', globalState = memento() } = {}) {
  const posted = [];
  const runCli = fakeCli(route, { agentArgv: AGENT.argv, task });
  const c = createController({ agent: AGENT, post: m => posted.push(m), runCli, settings: { stage: 'v3', ...settings },
    host: { globalState, ...host }, exists: () => true, uuid: () => UUID });
  return { c, posted, runCli, globalState, last: type => posted.filter(m => m.type === type).at(-1),
    tails: () => runCli.calls.map(x => x.tail) };
}

// --- models ---------------------------------------------------------------------------------

test('ExplainModel: terms in file order, the example only when shown, the reveal only when available', () => {
  const b = toExplainModel(payload('explain.binary'));
  assert.deepEqual(Object.keys(b), ['revision', 'task', 'terms', 'termOrder', 'steps', 'predictions']);
  assert.equal(b.task, 'binary');
  assert.deepEqual(b.termOrder, payload('explain.binary').terms.map(t => t.id));
  assert.deepEqual(Object.keys(b.terms.base_rate), ['term', 'definition', 'example', 'exampleStatus', 'steps']);
  const cited = b.terms.base_rate.example.find(s => s.resultId);
  assert.deepEqual(cited.resultId, '744b2d1cffbbdb905b9492fca6de249283b2144d61faaeeab794134ae0878db8');
  assert.deepEqual(b.terms.base_rate.steps, ['train_eda']);
  assert.equal(b.terms.leakage.example, null);
  const q = b.predictions.find(x => x.id === 'binary.policy.beats_baseline');
  assert.equal(q.available, false);
  assert.equal(q.reveal, null);
  assert.ok(q.choices.some(c => c.id === 'not_sure'));
  assert.ok(b.steps.train_eda.concept.length && 'consequence' in b.steps.train_eda);
  // A term whose example is not shown carries no cited number, even if the payload had one.
  const raw = JSON.parse(JSON.stringify(payload('explain.binary')));
  raw.terms.find(t => t.id === 'base_rate').example_status = 'needs_results';
  raw.predictions[0].available = false;
  const m = toExplainModel(raw);
  assert.equal(m.terms.base_rate.example, null);
  assert.equal(m.predictions[0].reveal, null);
  const r = toExplainModel(payload('explain.regression'));
  assert.equal(r.task, 'regression');
  assert.ok(r.terms.mae.example.some(s => s.resultId) && !r.terms.policy, 'the task filter of the engine');
  assert.throws(() => toExplainModel(payload('evidence.binary')), ModelError);
});

test('SessionReportModel: log status, span, pauses, refusal counts, decisions, gaps; no timeline or words', () => {
  const m = toSessionReportModel(payload('session_report.binary'));
  assert.deepEqual(Object.keys(m), ['revision', 'log', 'span', 'pauses', 'refusals', 'decisions', 'gaps']);
  assert.deepEqual(m.log, { enabled: true, note: null });
  assert.equal(m.span.seconds, 5.7);
  assert.deepEqual(m.pauses.map(p => [p.pause, p.open]), [[1, false], [2, false], [3, true]]);
  assert.equal(m.decisions.length, 5);
  const raw = JSON.parse(JSON.stringify(payload('session_report.binary')));
  raw.refusals = [{ code: 'ambiguous_confirmation', reason: 'bare_acknowledgement' }, { code: 'ambiguous_confirmation', reason: 'bare_acknowledgement' },
    { code: 'stale_revision', reason: null }];
  raw.sources.session_log = { enabled: false, entries: 0, path: '.hypotrail/session-log.jsonl', note: 'The session log is off.' };
  const off = toSessionReportModel(raw);
  assert.deepEqual(off.refusals, [{ code: 'ambiguous_confirmation', reason: 'bare_acknowledgement', count: 2 },
    { code: 'stale_revision', reason: null, count: 1 }]);
  assert.deepEqual(off.log, { enabled: false, note: 'The session log is off.' });
  const text = JSON.stringify(m);
  assert.ok(!text.includes('timeline') && !text.includes('user_words') && !text.includes('commands'));
  assert.throws(() => toSessionReportModel(payload('explain.binary')), ModelError);
});

// --- loads ------------------------------------------------------------------------------------

test('load explain and session_report: stage v3, exact argv, cached per revision', async () => {
  const { c, last, tails } = make();
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'load', view: 'explain' });
  await c.handle({ v: 2, type: 'load', view: 'explain' });
  const data = last('view_data');
  assert.equal(data.view, 'explain');
  assert.equal(data.model.task, 'binary');
  assert.deepEqual(tails().filter(t => t[0] === 'explain'), [['explain', '--json', '--study', AGENT.studyDir]], 'one read, cached');
  await c.handle({ v: 2, type: 'load', view: 'session_report' });
  assert.equal(last('view_data').view, 'session_report');
  assert.deepEqual(tails().filter(t => t[0] === 'session-report'), [['session-report', '--json', '--study', AGENT.studyDir]]);
  const v2 = make({ settings: { stage: 'v2' } });
  await v2.c.handle({ v: 2, type: 'load', view: 'explain' });
  assert.equal(v2.last('load_error').message, 'Not available in this stage.');
  assert.equal(v2.runCli.calls.length, 0);
});

// --- learn_set: globalState only -------------------------------------------------------------

test('LE-1: a prediction choice never reaches cli.run; it goes to globalState only', async () => {
  const { c, runCli, globalState, last, posted } = make();
  await c.handle({ v: 2, type: 'ready' });
  assert.deepEqual(last('learn_state'), { v: 2, type: 'learn_state', prefs: { hideCards: false }, seen: {}, predictions: {} });
  await c.handle({ v: 2, type: 'load', view: 'explain' });
  const before = runCli.calls.length;
  await c.handle({ v: 2, type: 'learn_set', key: 'prediction', id: 'binary.train_eda.rare', value: 'rare' });
  await c.handle({ v: 2, type: 'learn_set', key: 'prediction', id: 'binary.policy.beats_baseline', value: 'not_sure' });
  assert.equal(runCli.calls.length, before, 'no CLI call at all (the explain read is cached)');
  for (const call of runCli.calls) {
    const argv = call.argv.join(' ');
    assert.ok(!argv.includes('rare') && !argv.includes('not_sure') && !argv.includes('beats_baseline'), argv);
  }
  assert.deepEqual(last('learn_state').predictions, { 'binary.train_eda.rare': 'rare', 'binary.policy.beats_baseline': 'not_sure' });
  assert.ok(!posted.some(m => m.type === 'outcome' || m.type === 'busy'), 'not a write');
  assert.deepEqual([...new Set(globalState.updates.map(u => u.key))], [localstore.KEYS.predictions]);
  // Unknown question or choice: nothing stored.
  const n = globalState.updates.length;
  await c.handle({ v: 2, type: 'learn_set', key: 'prediction', id: 'binary.train_eda.rare', value: 'maybe' });
  await c.handle({ v: 2, type: 'learn_set', key: 'prediction', id: 'binary.unknown', value: 'rare' });
  assert.equal(globalState.updates.length, n);
  assert.match(last('notice').text, /does not know that item\. Nothing was stored\./);
  // Reset clears this study's answers.
  await c.handle({ v: 2, type: 'learn_set', key: 'reset_predictions', id: 'study' });
  assert.deepEqual(last('learn_state').predictions, {});
  // Spy on run itself: the module never calls cli.run outside the controller's reads.
  const src = fs.readFileSync(path.join(__dirname, '..', 'lib', 'handlers', 'learn.js'), 'utf8');
  assert.doesNotMatch(src, /\.run\(|child_process|ctx\.write\('W[1-6]'/);
});

test('LE-2: a card is counted once per panel session; the count survives a reload (globalState)', async () => {
  const globalState = memento();
  const first = make({ globalState });
  await first.c.handle({ v: 2, type: 'ready' });
  await first.c.handle({ v: 2, type: 'learn_set', key: 'seen', id: 'binary:conclusion' });
  await first.c.handle({ v: 2, type: 'learn_set', key: 'seen', id: 'binary:conclusion' });
  assert.deepEqual(first.last('learn_state').seen, { 'binary:conclusion': 1 }, 'not counted twice in one panel session');
  // A new panel (a reload): the stored count is read back, and the second sighting counts.
  const second = make({ globalState });
  await second.c.handle({ v: 2, type: 'ready' });
  assert.deepEqual(second.last('learn_state').seen, { 'binary:conclusion': 1 });
  await second.c.handle({ v: 2, type: 'learn_set', key: 'seen', id: 'binary:conclusion' });
  assert.deepEqual(second.last('learn_state').seen, { 'binary:conclusion': 2 });
  // Ids the engine does not list (another task, an unknown step, free text) are not stored.
  for (const id of ['regression:conclusion', 'binary:nope', 'term:nope', 'p_5']) {
    await second.c.handle({ v: 2, type: 'learn_set', key: 'seen', id });
  }
  assert.deepEqual(second.last('learn_state').seen, { 'binary:conclusion': 2 });
  await second.c.handle({ v: 2, type: 'learn_set', key: 'prefs', id: 'prefs', value: { hideCards: true } });
  assert.deepEqual(second.last('learn_state').prefs, { hideCards: true });
  for (const u of globalState.updates) assert.equal(localstore.invalidReason(u.key, u.value), null, u.key);
});

test('LE-3: with the learning layer off nothing is stored, no learn_state is sent, and explain is never read', async () => {
  const { c, runCli, globalState, posted, last } = make({ settings: { learningLayer: false } });
  await c.handle({ v: 2, type: 'ready' });
  assert.ok(!posted.some(m => m.type === 'learn_state'));
  for (const m of [{ key: 'seen', id: 'binary:conclusion' }, { key: 'prediction', id: 'binary.train_eda.rare', value: 'rare' },
    { key: 'prefs', id: 'prefs', value: { hideCards: true } }]) {
    await c.handle({ v: 2, type: 'learn_set', ...m });
  }
  await c.handle({ v: 2, type: 'ask_agent', about: { kind: 'term', id: 'base_rate' }, question: '', mode: 'copy' });
  assert.equal(globalState.updates.length, 0);
  assert.ok(!runCli.calls.some(x => x.tail[0] === 'explain'), 'no explain call');
  assert.match(last('notice').text, /could not be copied|Copied/);
  assert.equal(posted.find(m => m.type === 'init').learningLayer, false);
});

// --- export (W7) --------------------------------------------------------------------------------

test('HO-1: export runs the exact argv of W7 into <chosen>/revision-<R>; files and folder recorded', async () => {
  const picked = [];
  const revealed = [];
  const host = { pickFolder: async d => { picked.push(d); return '/tmp/hand off'; }, revealInOS: async p => { revealed.push(p); } };
  const { c, runCli, last, posted } = make({ host });
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'export_handoff', revision: 26 });
  assert.deepEqual(picked, [path.join(AGENT.studyDir, 'handoff')], 'the default parent is <study>/handoff/');
  const call = runCli.calls.find(x => x.tail[0] === 'export');
  assert.deepEqual(call.argv, [...AGENT.argv, 'export', 'handoff', '--out=/tmp/hand off/revision-26', '--json', '--study', AGENT.studyDir]);
  assert.equal(call.options.timeoutMs, 120000);
  const o = posted.find(m => m.type === 'outcome');
  assert.equal(o.op, 'W7');
  assert.equal(o.kind, 'ok');
  assert.equal(o.target, 'handoff');
  assert.deepEqual(o.recorded.files.map(f => [f.path, f.bytes]), [['handoff.md', 8213], ['handoff.json', 15327], ['study.html', 91562],
    ['SHA256SUMS', 284]]);
  assert.equal(o.recorded.out, payload('export.binary').out);
  assert.equal(last('notice').text, 'The pack is incomplete: some proposals are still open; some decisions are not confirmed.');
  // Open folder: only the last export's folder.
  await c.handle({ v: 2, type: 'navigate_external', kind: 'reveal_export', path: '/etc' });
  assert.deepEqual(revealed, []);
  assert.match(last('notice').text, /not the last export/);
  await c.handle({ v: 2, type: 'navigate_external', kind: 'reveal_export', path: o.recorded.out });
  assert.deepEqual(revealed, [o.recorded.out]);
});

test('HO-1: a non-empty target gives export_target_exists verbatim; exit 3 is success with problems', async () => {
  const host = { pickFolder: async () => '/tmp/packs' };
  const refused = make({ host, route: t => (t[0] === 'export' ? 'error.export_target_exists' : undefined) });
  await refused.c.handle({ v: 2, type: 'ready' });
  await refused.c.handle({ v: 2, type: 'export_handoff', revision: 26 });
  const o = refused.last('outcome');
  assert.equal(o.kind, 'refused');
  assert.equal(o.refusal.code, 'export_target_exists');
  assert.equal(o.refusal.engineMessage, payload('error.export_target_exists').error.message);
  assert.ok(refused.posted.filter(m => m.type === 'snapshot').length >= 2, 'refreshed after the refusal');

  const stale = make({ host, route: t => (t[0] === 'export' ? 'export.binary.stale_report' : undefined) });
  await stale.c.handle({ v: 2, type: 'ready' });
  await stale.c.handle({ v: 2, type: 'export_handoff', revision: 26 });
  const s = stale.last('outcome');
  assert.equal(s.kind, 'ok_with_problems');
  assert.equal(s.exitCode, 3);
  assert.ok(!s.recorded.files.some(f => f.path === 'study.html'));
  assert.match(stale.last('notice').text, /the report was not current, so it is not in the pack/);
});

test('W7 pre-checks: a cancelled dialog, a stale revision, or a folder inside .hypotrail runs nothing', async () => {
  let answer = null;
  const host = { pickFolder: async () => answer };
  const { c, runCli, last } = make({ host });
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'export_handoff', revision: 26 });
  assert.deepEqual([last('outcome').kind, last('outcome').message], ['cancelled', 'No folder was chosen. Nothing was exported.']);
  await c.handle({ v: 2, type: 'export_handoff', revision: 25 });
  assert.equal(last('outcome').kind, 'invalid');
  assert.match(last('outcome').message, /study changed/);
  answer = path.join(AGENT.studyDir, '.hypotrail');
  await c.handle({ v: 2, type: 'export_handoff', revision: 26 });
  assert.equal(last('outcome').kind, 'invalid');
  assert.ok(!runCli.calls.some(x => x.tail[0] === 'export'));
});

test('HO-2 (read with CA.9): reviewer mode may export; every other write stays refused', async () => {
  const { c, runCli, last } = make({ settings: { reviewer: true }, host: { pickFolder: async () => '/tmp/review' } });
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'export_handoff', revision: 26 });
  assert.equal(last('outcome').kind, 'ok');
  assert.ok(runCli.calls.some(x => x.tail[0] === 'export'));
  await c.handle({ v: 2, type: 'render' });
  assert.equal(last('outcome').message, 'Read-only reviewer mode.');
});

// --- media/terms.js --------------------------------------------------------------------------

test('§6.7: every term id marked in the panel copy exists in the glossary of at least one task', () => {
  delete globalThis.Hypotrail;
  require('../media/terms.js');
  const map = globalThis.Hypotrail.terms.MAP;
  delete globalThis.Hypotrail;
  const glossary = new Set([...payload('explain.binary').terms, ...payload('explain.regression').terms].map(t => t.id));
  assert.ok(Object.keys(map).length >= 5);
  for (const [id, places] of Object.entries(map)) {
    assert.ok(glossary.has(id), `${id} is not a glossary id`);
    assert.ok(Array.isArray(places) && places.length, id);
  }
  const view = fs.readFileSync(path.join(__dirname, '..', 'media', 'views', 'learn.js'), 'utf8');
  for (const m of view.matchAll(/terms\.mark\([^,]+, '([a-z_]+)'\)/g)) assert.ok(map[m[1]], `${m[1]} is in MAP`);
});

test('the learn copy holds no digit outside placeholders except the quoted engine instruction', () => {
  globalThis.Hypotrail = { copy: {} };
  require('../media/copy/learn.js');
  const copy = globalThis.Hypotrail.copy.learn;
  delete globalThis.Hypotrail;
  for (const [k, v] of Object.entries(copy)) {
    if (typeof v !== 'string' || k === 'sessionLogOff') continue;
    assert.doesNotMatch(v, /\d/, k);
    assert.doesNotMatch(v, /\b(threshold|capacity|precision|recall|positive class|policy|calling rule|selected)\b/i, k);
  }
  assert.equal(copy.sessionLogOff,
    'Start the CLI once with HYPOTRAIL_SESSION_LOG=1 to turn it on; delete .hypotrail/session-log.jsonl to turn it off.');
});

// --- through the extension: globalState, the folder dialog, revealFileInOS ------------------

const realExecFile = childProcess.execFile;
test.afterEach(() => {
  childProcess.execFile = realExecFile;
  delete process.env.HYPOTRAIL_COMPANION;
  delete process.env.HYPOTRAIL_COMPANION_STAGE;
});

function makeStudy() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'learn-'));
  fs.mkdirSync(path.join(dir, '.hypotrail'));
  fs.writeFileSync(path.join(dir, '.hypotrail', 'agent.json'),
    JSON.stringify({ schema: 'hypotrail.agent/1', study: dir, cli: { argv: AGENT.argv } }));
  return fs.realpathSync(dir);
}

function fakeExec() {
  const calls = [];
  childProcess.execFile = (file, args, options, cb) => {
    const tail = args.slice(2);
    calls.push(tail);
    const f = fixture(defaultRoute(tail));
    setImmediate(() => cb(f.about.exit_code ? Object.assign(new Error('exit'), { code: f.about.exit_code }) : null,
      JSON.stringify({ ...f.payload, study: options.cwd }), ''));
  };
  return calls;
}

test('LE-1, LE-2, HO-1 through the extension: context.globalState, showOpenDialog, revealFileInOS', async () => {
  process.env.HYPOTRAIL_COMPANION = '1';
  process.env.HYPOTRAIL_COMPANION_STAGE = 'v3';
  const exec = fakeExec();
  const dir = makeStudy();
  const fake = createFake({ folders: [dir], answers: { openDialog: ['/tmp/packs'] },
    builtinCommands: { revealFileInOS: () => undefined } });
  const { extension, context } = load(fake);
  extension.activate(context);
  let opened = await fake.commands.executeCommand('hypotrail.companion.open');
  await opened.controller.handle({ v: 2, type: 'ready' });
  await opened.controller.handle({ v: 2, type: 'learn_set', key: 'prediction', id: 'binary.train_eda.rare', value: 'rare' });
  await opened.controller.handle({ v: 2, type: 'learn_set', key: 'seen', id: 'binary:conclusion' });
  assert.deepEqual(context.globalState.keys().sort(), [localstore.KEYS.predictions, localstore.KEYS.seen]);
  assert.ok(!JSON.stringify(context.globalState.updates).includes(dir), 'the study path is not stored');
  assert.ok(!exec.some(t => t.join(' ').includes('rare')), 'no CLI call carries the answer');
  await opened.controller.handle({ v: 2, type: 'export_handoff', revision: 26 });
  assert.equal(fake.calls.openDialog.at(-1).canSelectFolders, true);
  assert.equal(fake.calls.openDialog.at(-1).defaultUri.fsPath, path.join(dir, 'handoff'));
  assert.deepEqual(exec.find(t => t[0] === 'export'), ['export', 'handoff', '--out=/tmp/packs/revision-26', '--json', '--study', dir]);
  const out = fake.calls.panels[0].posted.find(m => m.type === 'outcome').recorded.out;
  await opened.controller.handle({ v: 2, type: 'navigate_external', kind: 'reveal_export', path: out });
  assert.deepEqual(fake.calls.executed.filter(x => x.id === 'revealFileInOS').map(x => x.args[0].fsPath), [out]);
  // A reload: a new panel reads the same globalState back.
  opened.panel.dispose();
  opened = await fake.commands.executeCommand('hypotrail.companion.open');
  await opened.controller.handle({ v: 2, type: 'ready' });
  const state = fake.calls.panels[1].posted.find(m => m.type === 'learn_state');
  assert.deepEqual(state.predictions, { 'binary.train_eda.rare': 'rare' });
  assert.deepEqual(state.seen, { 'binary:conclusion': 1 });
});

test('the warnings of an export have words for every code of CLI-CONTRACT-COMPANION §7', () => {
  for (const code of ['report_not_current', 'open_proposals', 'open_holds', 'interrupted_executions', 'sources_changed',
    'unconfirmed_decisions']) {
    assert.ok(learn.WARNINGS[code], code);
  }
  assert.equal(learn.warningsText([]), '');
});
