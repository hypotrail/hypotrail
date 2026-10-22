'use strict';
// Unit tests (scope U): the extension against a fake `vscode` module and a fake
// child_process.execFile. No VS Code and no CLI process. Run: node --test test/*.test.js
//
// Migrated by WP-0 to protocol hypotrail.panel/2 (messages carry `v: 2`, `open` is
// `open_artifact`, an outcome is {op, kind: ok|refused|...}); every v0 assertion is kept.

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const childProcess = require('child_process');
const { createFake, load } = require('./fake-vscode');

const realExecFile = childProcess.execFile;
const CLI = ['/opt/my tools/py "q"/bin/python', '-m', 'mlkit.study.cli'];
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

function tmp(name = 'hyp') {
  return fs.mkdtempSync(path.join(os.tmpdir(), `${name}-`));
}

function makeStudy(parent, name, { argv = CLI, study, schema = 'hypotrail.agent/1' } = {}) {
  const dir = path.join(parent, name);
  fs.mkdirSync(path.join(dir, '.hypotrail'), { recursive: true });
  fs.writeFileSync(path.join(dir, '.hypotrail', 'agent.json'), JSON.stringify({
    schema, study: study || dir, cli: { argv, shell: 'ignored; rm -rf /', how: 'override' } }));
  return fs.realpathSync(dir);
}

function summary(studyDir, revision = 3, extra = {}) {
  return {
    schema: 'hypotrail.summary/1', ok: true, study: studyDir, revision, since: null, changed: null,
    goal: {}, current_step: 'prediction_time',
    plan: [{ id: 'prediction_time', title: 'Define the prediction moment', status: 'awaiting_confirmation' },
      { id: 'feature_availability', title: 'Decide which variables are available at prediction time', status: 'blocked' }],
    next_action: { kind: 'await_user_words', proposal_id: 'p_1', decision: 'prediction_time', message: 'Show the restatement.' },
    open_proposals: [{ proposal_id: 'p_1', decision_id: 'prediction_time', value: 'before the first reminder',
      restatement: 'You predict <b>before</b> the first reminder.', revision: 2 }],
    decisions: {}, results: {},
    artifacts: { status: 'ok', items: { report: { status: 'ok', revision: 3, last_ok_revision: 3, message: 'The report (reports/study.html) is up to date.' } } },
    executions: { active: [], interrupted: [], late: [], suspected_interrupted: [] },
    not_yet_defensible: { top: [{ id: 'open_holds', text: 'On hold.' }], more: ['workbench_not_tracked'] },
    notes: [{ note_id: 'n_1', decision_id: 'prediction_time', status: 'open', user_words: 'wait for my manager', resolution_words: null }],
    recap: ['Goal: g', 'Decided: nothing yet.', 'Now: n', 'Next: x', 'Limit: l'],
    ...extra,
  };
}

/** Replace execFile; `respond(args)` returns {payload, code} or {stdout} or {error}. */
function fakeCli(respond) {
  const calls = [];
  childProcess.execFile = (file, args, options, cb) => {
    calls.push({ file, args, options });
    const r = respond(args, calls.length) || {};
    setImmediate(() => {
      if (r.spawnError) return cb(Object.assign(new Error('spawn'), { code: r.spawnError }), '', '');
      const stdout = r.stdout !== undefined ? r.stdout : JSON.stringify(r.payload) + '\n';
      const err = r.code ? Object.assign(new Error('exit'), { code: r.code }) : null;
      cb(err, stdout, r.stderr || 'warning: The `UV_NATIVE_TLS` environment variable is deprecated\n');
    });
  };
  return calls;
}

function clearFlagEnvironment() {
  delete process.env.HYPOTRAIL_COMPANION;
  delete process.env.HYPOTRAIL_COMPANION_STAGE;
}

test.beforeEach(clearFlagEnvironment);
test.afterEach(() => {
  childProcess.execFile = realExecFile;
  clearFlagEnvironment();
});

async function openWith(fake) {
  const { extension, context } = load(fake);
  const api = extension.activate(context);
  const opened = await fake.commands.executeCommand('hypotrail.companion.open');
  return { api, opened, context, extension };
}

test('INV-10 flag off: the command shows one message and nothing else runs', async () => {
  const calls = fakeCli(() => assert.fail('no CLI call when the flag is off'));
  const folder = tmp();
  makeStudy(folder, 'study');
  const fake = createFake({ folders: [path.join(folder, 'study')] });
  const { extension, context } = load(fake);
  const api = extension.activate(context);
  assert.deepEqual([...fake.registered.keys()], ['hypotrail.companion.open', 'hypotrail.companion.openReviewer',
    'hypotrail.companion.goToResult']);
  assert.equal(fake.uriHandlers.length, 1, 'the URI handler is registered (onUri)');
  assert.equal(fake.calls.configuration.length, 0, 'activation reads no setting');
  assert.equal(await fake.commands.executeCommand('hypotrail.companion.open'), null);
  assert.deepEqual(fake.calls.info, ['Companion disabled (feature flag)']);
  // Every entry point is behind the flag: the reviewer command, go to a result, a link.
  assert.equal(await fake.commands.executeCommand('hypotrail.companion.openReviewer'), null);
  assert.equal(await fake.commands.executeCommand('hypotrail.companion.goToResult'), null);
  assert.equal(await fake.uriHandlers[0].handleUri({ path: '/result/' + 'a'.repeat(64), query: '' }), null);
  assert.deepEqual(fake.calls.info, Array(4).fill('Companion disabled (feature flag)'));
  assert.equal(fake.calls.panels.length, 0);
  assert.equal(fake.calls.openDialog.length + fake.calls.quickPick.length + fake.calls.error.length + fake.calls.inputBox.length, 0);
  assert.equal(calls.length, 0);
  assert.equal(api.current(), null);
});

test('flag: setting default false; setting true or HYPOTRAIL_COMPANION=1 turns it on', () => {
  const { isEnabled } = require('../lib/flag');
  assert.equal(isEnabled(createFake(), {}), false);
  assert.equal(isEnabled(createFake({ settings: { 'hypotrail.companion.enabled': false } }), {}), false);
  assert.equal(isEnabled(createFake(), { HYPOTRAIL_COMPANION: '0' }), false);
  assert.equal(isEnabled(createFake(), { HYPOTRAIL_COMPANION: 'true' }), false);
  assert.equal(isEnabled(createFake({ settings: { 'hypotrail.companion.enabled': true } }), {}), true);
  assert.equal(isEnabled(createFake(), { HYPOTRAIL_COMPANION: '1' }), true);
  const pkg = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'package.json'), 'utf8'));
  assert.equal(pkg.contributes.configuration.properties['hypotrail.companion.enabled'].default, false);
  assert.equal(pkg.contributes.configuration.properties['hypotrail.companion.stage'].default, 'v0');
  assert.equal(pkg.contributes.configuration.properties['hypotrail.companion.chatInsert'], undefined, 'chatInsert is hidden');
  assert.deepEqual(pkg.activationEvents, ['onCommand:hypotrail.companion.open', 'onCommand:hypotrail.companion.openReviewer',
    'onCommand:hypotrail.companion.goToResult', 'onUri']);
  assert.equal(pkg.capabilities.untrustedWorkspaces.supported, false);
  assert.equal(pkg.dependencies, undefined, 'no runtime dependency');
});

test('INV-11 untrusted workspace: refused before any CLI call', async () => {
  const calls = fakeCli(() => assert.fail('no CLI call'));
  process.env.HYPOTRAIL_COMPANION = '1';
  const folder = tmp();
  makeStudy(folder, 'study');
  const fake = createFake({ folders: [path.join(folder, 'study')], trusted: false });
  const { opened } = await openWith(fake);
  assert.equal(opened, null);
  assert.match(fake.calls.error[0], /trusted workspace/);
  assert.equal(fake.calls.panels.length, 0);
  assert.equal(calls.length, 0);
});

test('discovery: one study folder, several (quick pick), none (folder dialog), invalid agent.json', async () => {
  const { findStudies, readAgent } = require('../lib/study');
  const folder = tmp();
  const a = makeStudy(folder, 'a study');
  const b = makeStudy(folder, 'b');
  fs.mkdirSync(path.join(folder, 'plain'));
  assert.deepEqual(findStudies([path.join(folder, 'plain'), a, b, a]), [a, b]);
  assert.deepEqual(readAgent(a).argv, CLI);
  assert.equal(readAgent(a).studyDir, a);

  process.env.HYPOTRAIL_COMPANION = '1';
  fakeCli(() => ({ payload: summary(a) }));
  let fake = createFake({ folders: [path.join(folder, 'plain'), a, b], answers: { quickPick: items => items[1] } });
  let { opened } = await openWith(fake);
  assert.equal(fake.calls.quickPick.length, 1);
  assert.equal(opened.agent.studyDir, b);

  fake = createFake({ folders: [path.join(folder, 'plain')], answers: { openDialog: [a] } });
  ({ opened } = await openWith(fake));
  assert.equal(fake.calls.openDialog.length, 1);
  assert.equal(opened.agent.studyDir, a);

  fake = createFake({ folders: [path.join(folder, 'plain')], answers: { openDialog: [path.join(folder, 'plain')] } });
  ({ opened } = await openWith(fake));
  assert.equal(opened, null);
  assert.match(fake.calls.error[0], /No study here/);

  for (const [name, options, pattern] of [
    ['badschema', { schema: 'other/1' }, /not a hypotrail.agent\/1 record/],
    ['badargv', { argv: 'uv run hypotrail' }, /no valid cli.argv/],
    ['emptyargv', { argv: [] }, /no valid cli.argv/],
    ['moved', { study: '/somewhere/else' }, /created at \/somewhere\/else/],
  ]) {
    const dir = makeStudy(folder, name, options);
    fake = createFake({ folders: [dir] });
    ({ opened } = await openWith(fake));
    assert.equal(opened, null, name);
    assert.match(fake.calls.error[0], pattern, name);
    assert.equal(fake.calls.panels.length, 0, name);
  }
});

test('argv: taken from agent.json, paths with spaces and quotes, execFile without a shell', async () => {
  process.env.HYPOTRAIL_COMPANION = '1';
  const folder = tmp('with space');
  const dir = makeStudy(folder, `study "quoted" it's`);
  const calls = fakeCli(() => ({ payload: summary(dir) }));
  const fake = createFake({ folders: [dir] });
  const { opened } = await openWith(fake);
  await opened.controller.handle({ v: 2, type: 'ready' });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].file, CLI[0]);
  assert.deepEqual(calls[0].args, [...CLI.slice(1), 'status', '--summary', '--json', '--study', dir]);
  assert.equal(calls[0].options.shell, false);
  assert.equal(calls[0].options.cwd, dir);
  const snapshot = fake.calls.panels[0].posted.find(m => m.type === 'snapshot');
  assert.equal(snapshot.model.revision, 3);
  assert.equal(snapshot.model.proposals[0].restatement, 'You predict <b>before</b> the first reminder.');
  assert.deepEqual(snapshot.model.proposals[0].holds, [{ noteId: 'n_1', userWords: 'wait for my manager' }]);
  assert.equal(snapshot.model.currentStep.position, 1);
  assert.equal(snapshot.model.recap.length, 5);
});

test('webview document: strict CSP with a nonce, scripts enabled, no remote resource', async () => {
  process.env.HYPOTRAIL_COMPANION = '1';
  const dir = makeStudy(tmp(), 'study');
  fakeCli(() => ({ payload: summary(dir) }));
  const fake = createFake({ folders: [dir] });
  await openWith(fake);
  const panel = fake.calls.panels[0];
  assert.equal(panel.options.enableScripts, true);
  assert.equal(panel.options.enableCommandUris, false);
  assert.deepEqual(panel.options.localResourceRoots, []);
  const html = panel.webview.html;
  const csp = html.match(/http-equiv="Content-Security-Policy" content="([^"]+)"/)[1];
  const nonce = csp.match(/script-src 'nonce-([A-Za-z0-9]+)'/)[1];
  assert.match(csp, /^default-src 'none';/);
  assert.match(csp, /connect-src 'none'/);
  assert.doesNotMatch(csp, /unsafe-inline|unsafe-eval|https?:/);
  assert.equal((html.match(/<script /g) || []).length, 1);
  assert.match(html, new RegExp(`<script nonce="${nonce}">`));
  assert.doesNotMatch(html, /https?:\/\//);
  assert.doesNotMatch(html, /\son[a-z]+=/i, 'no inline handler');
});

/** Resolve once `cond()` holds, polling on the event loop (no fixed sleep); fail after 5 s. */
async function until(cond, what = 'the condition') {
  const deadline = Date.now() + 5000;
  while (!cond()) {
    if (Date.now() > deadline) assert.fail(`timed out waiting for ${what}`);
    await new Promise(r => setImmediate(r));
  }
}

/** Let pending callbacks and promise jobs run (a few turns of the event loop). */
async function flush(turns = 20) {
  for (let i = 0; i < turns; i += 1) await new Promise(r => setImmediate(r));
}

test('refresh on change: the panel\'s watcher is wired to the real folder; closing the panel closes it', async t => {
  process.env.HYPOTRAIL_COMPANION = '1';
  const dir = makeStudy(tmp(), 'study');
  const calls = fakeCli(() => ({ payload: summary(dir) }));
  const fake = createFake({ folders: [dir] });
  const { opened } = await openWith(fake);
  await opened.controller.handle({ v: 2, type: 'ready' });
  const before = calls.length;
  fs.writeFileSync(path.join(dir, '.hypotrail', 'state.json'), '{}');
  await until(() => calls.length === before + 1, 'the refresh after a write to state.json');
  const watcher = opened.watcher;
  fake.calls.panels[0].dispose();
  assert.equal(opened.watcher, null);
  // Closed: neither a reported change nor a late event of the real folder refreshes.
  t.mock.timers.enable({ apis: ['setTimeout'] });
  watcher.trigger('change', 'state.json');
  fs.writeFileSync(path.join(dir, '.hypotrail', 'state.json'), '{"x":1}');
  await flush();
  t.mock.timers.tick(10000);
  await flush();
  assert.equal(calls.length, before + 1, 'no refresh after the panel is closed');
});

test('watchStudy: one call per burst of the watched files, after the debounce; other files are ignored (fake timers)', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const { watchStudy, WATCHED, DEBOUNCE_MS } = require('../lib/watch');
  let handler = null;
  let closed = false;
  const fsImpl = { watch: (dir, options, fn) => { handler = fn; return { on() {}, close() { closed = true; } }; } };
  let changes = 0;
  const w = watchStudy('/studies/s', () => { changes += 1; }, { fsImpl });
  assert.deepEqual([...WATCHED].sort(), ['artifacts.json', 'revisions.jsonl', 'state.json', 'state.sha256']);
  handler('change', 'unrelated.tmp');
  t.mock.timers.tick(DEBOUNCE_MS * 4);
  assert.equal(changes, 0, 'an unrelated file does not refresh');
  handler('change', 'state.json');
  t.mock.timers.tick(DEBOUNCE_MS - 1);
  handler('rename', 'revisions.jsonl');
  t.mock.timers.tick(DEBOUNCE_MS - 1);
  handler('change', 'revisions.jsonl');
  assert.equal(changes, 0, 'still inside the burst');
  t.mock.timers.tick(DEBOUNCE_MS);
  assert.equal(changes, 1, 'one refresh per burst (debounced)');
  handler('change', null);
  t.mock.timers.tick(DEBOUNCE_MS);
  assert.equal(changes, 2, 'no filename reported: refresh anyway');
  w.dispose();
  assert.equal(closed, true);
  handler('change', 'state.json');
  t.mock.timers.tick(DEBOUNCE_MS * 4);
  assert.equal(changes, 2, 'nothing after dispose');
});

test('panel becoming visible refreshes; messages go through onDidReceiveMessage', async () => {
  process.env.HYPOTRAIL_COMPANION = '1';
  const dir = makeStudy(tmp(), 'study');
  const calls = fakeCli(() => ({ payload: summary(dir) }));
  const fake = createFake({ folders: [dir] });
  await openWith(fake);
  const panel = fake.calls.panels[0];
  panel.receive({ v: 2, type: 'ready' });
  await until(() => calls.length === 1, 'the summary read of ready');
  await until(() => panel.posted.some(m => m.type === 'snapshot'), 'the snapshot');
  assert.equal(calls.length, 1);
  panel.setVisible(true);
  await until(() => calls.length === 2, 'the refresh on visible');
  await until(() => panel.posted.filter(m => m.type === 'snapshot').length === 2, 'the second snapshot');
  assert.equal(calls.length, 2);
});

async function readyPanel(respond, { stage = null } = {}) {
  process.env.HYPOTRAIL_COMPANION = '1';
  if (stage) process.env.HYPOTRAIL_COMPANION_STAGE = stage;
  const dir = makeStudy(tmp('with space'), 'my study');
  // An interrupted execution waits for an acknowledgement (W6, stage v1).
  const executions = { active: [], interrupted: [{ execution_id: 'e_1', activity: 'fit.logistic', reason: 'stopped' }],
    late: [], suspected_interrupted: [] };
  const calls = fakeCli((args, n) => (args.includes('status') ? { payload: summary(dir, n === 1 ? 3 : 4, { executions }) } : respond(args, dir)));
  const fake = createFake({ folders: [dir] });
  const { opened } = await openWith(fake);
  await opened.controller.handle({ v: 2, type: 'ready' });
  return { dir, calls, fake, controller: opened.controller, panel: fake.calls.panels[0] };
}

test('v0 panel (default stage): no write at all; confirm, withdraw, and propose are dropped, no decide process (WP-E1)', async () => {
  const { calls, panel, controller } = await readyPanel(() => assert.fail('no mutation'));
  const before = calls.length;
  for (const bad of [
    // v0.3 narrowing (ADR 0004 amendment, R23, I2): these are no message types any more.
    { v: 2, type: 'confirm', proposalId: 'p_1', words: 'Yes, before the first reminder.', revision: 3 },
    { v: 2, type: 'withdraw', proposalId: 'p_1', revision: 3 },
    { v: 2, type: 'propose', decisionId: 'policy', value: 'capacity:100', revision: 3 },
    // Malformed messages.
    { v: 2, type: 'confirm', proposalId: 'p_1', words: 'yes', revision: 3, basis: 'delegated_default' },
    { v: 2, type: 'run', activity: 'split' },
    { v: 2, type: 'open_artifact', artifact: '../../etc/passwd' },
    { v: 2, type: 'acknowledge', executionId: 'e_1', words: 'I know it stopped.', revision: '3' },
    'confirm', null, [],
  ]) await controller.handle(bad);
  assert.equal(controller.diagnostics().ignored, 10);
  // A v0 message without the v2 envelope is dropped too.
  await controller.handle({ type: 'confirm', proposalId: 'p_1', words: 'yes before the reminder', revision: 3 });
  assert.equal(controller.diagnostics().ignored, 11);
  // A write of a later stage (W6 is v1) is dropped at v0.
  await controller.handle({ v: 2, type: 'acknowledge', executionId: 'e_1', words: 'I know it stopped.', revision: 3 });
  assert.equal(controller.diagnostics().ignored, 12);
  assert.ok(calls.slice(before).every(c => c.args.includes('status')), 'only reads');
  assert.ok(!calls.some(c => c.args.includes('decide')), 'never a decide command');
  assert.equal(panel.posted.filter(m => m.type === 'outcome').length, 0);
});

test('acknowledge (W6): exact argv with the typed words, uuid, revision read; blank words never reach the CLI', async () => {
  const words = '-- I know: the fit stopped, "quoted" & <b>not</b> html';
  const { dir, calls, panel, controller } = await readyPanel(() => ({ code: 0, payload: {
    schema: 'hypotrail.run/1', ok: true, action: 'run.acknowledge', request_id: 'x', replayed: false, revision: 4,
    result: { execution_id: 'e_1', status: 'acknowledged', user_words: words },
    artifacts: { report: { status: 'ok', message: 'The report (reports/study.html) is up to date.' } } } }), { stage: 'v1' });
  await controller.handle({ v: 2, type: 'acknowledge', executionId: 'e_1', words: '   \n', revision: 3 });
  assert.equal(panel.posted.at(-1).kind, 'invalid');
  assert.ok(!calls.some(c => c.args.includes('--acknowledge-interruption')));
  await controller.handle({ v: 2, type: 'acknowledge', executionId: 'e_1', words, revision: 3 });
  const ack = calls.find(c => c.args.includes('--acknowledge-interruption'));
  const rid = ack.args[ack.args.indexOf('--request-id') + 1];
  assert.match(rid, UUID);
  assert.deepEqual(ack.args, [...CLI.slice(1), 'run', '--acknowledge-interruption', 'e_1', `--user-words=${words}`,
    '--channel=webview', '--request-id', rid, '--expected-revision', '3', '--json', '--study', dir]);
  assert.equal(ack.options.shell, false);
  const outcome = panel.posted.filter(m => m.type === 'outcome').at(-1);
  assert.equal(outcome.v, 2);
  assert.equal(outcome.op, 'W6');
  assert.equal(outcome.kind, 'ok');
  assert.equal(outcome.target, 'e_1');
  assert.equal(outcome.recorded.userWords, words);
  assert.equal(calls.at(-1).args.includes('status'), true, 'the panel refreshes after the outcome');
});

test('refusal: the engine message is shown verbatim with the human message, then a refresh', async () => {
  const engineMessage = 'A bare acknowledgement is not an acknowledgement. Say what you know about the interruption.';
  const { calls, panel, controller } = await readyPanel(() => ({ code: 2, payload: {
    schema: 'hypotrail.error/1', ok: false, command: 'run',
    error: { code: 'ambiguous_confirmation', message: engineMessage,
      details: { reason: 'bare_acknowledgement', user_words: 'ok', execution_id: 'e_1' } } } }), { stage: 'v1' });
  await controller.handle({ v: 2, type: 'acknowledge', executionId: 'e_1', words: 'ok', revision: 3 });
  const outcome = panel.posted.find(m => m.type === 'outcome');
  assert.equal(outcome.kind, 'refused');
  assert.equal(outcome.exitCode, 2);
  assert.equal(outcome.refusal.code, 'ambiguous_confirmation');
  assert.equal(outcome.refusal.reason, 'bare_acknowledgement');
  assert.equal(outcome.refusal.engineMessage, engineMessage);
  assert.match(outcome.refusal.human, /only acknowledged.*Nothing was recorded\.$/);
  assert.ok(calls.at(-1).args.includes('status'));
});

test('stale revision: the diff is summarised and the panel refreshes', async () => {
  const { panel, controller } = await readyPanel(() => ({ code: 2, payload: {
    schema: 'hypotrail.error/1', ok: false, command: 'run',
    error: { code: 'stale_revision', message: 'Revision is stale: reread hypotrail status before deciding',
      details: { expected_revision: 2, current_revision: 3, changes_since: [{ revision: 3, action: 'decide.note',
        params: { decision_id: 'prediction_time', user_words: 'wait' } }] } } } }), { stage: 'v1' });
  await controller.handle({ v: 2, type: 'acknowledge', executionId: 'e_1', words: 'I know the fit stopped.', revision: 2 });
  const outcome = panel.posted.find(m => m.type === 'outcome');
  assert.equal(outcome.refusal.code, 'stale_revision');
  assert.equal(outcome.refusal.engineMessage, 'Revision is stale: reread hypotrail status before deciding');
  assert.deepEqual(outcome.refusal.details, ['Revision read by the panel: 2', 'Current revision: 3',
    'Changed at revision 3: decide.note (prediction_time)']);
  assert.match(outcome.refusal.human, /refreshed/);
  assert.equal(panel.posted.at(-1).type, 'snapshot');
});

test('a CLI that cannot start or prints no JSON: an unknown outcome, never a success', async () => {
  const { panel, controller } = await readyPanel(() => ({ spawnError: 'ENOENT' }), { stage: 'v1' });
  await controller.handle({ v: 2, type: 'acknowledge', executionId: 'e_1', words: 'I know the fit stopped.', revision: 3 });
  const outcome = panel.posted.find(m => m.type === 'outcome');
  assert.equal(outcome.kind, 'failed');
  assert.match(outcome.message, /could not be started \(ENOENT/);
  assert.match(outcome.message, /outcome is unknown/);
});

test('open: the report in the browser, the notebook in the editor, a missing file is reported', async () => {
  const { dir, fake, panel, controller } = await readyPanel(() => assert.fail('no mutation'));
  fs.mkdirSync(path.join(dir, 'reports'));
  fs.writeFileSync(path.join(dir, 'reports', 'study.html'), '<p>r</p>');
  await controller.handle({ v: 2, type: 'open_artifact', artifact: 'report' });
  assert.deepEqual(fake.calls.openExternal, [path.join(dir, 'reports', 'study.html')]);
  await controller.handle({ v: 2, type: 'open_artifact', artifact: 'notebook' });
  assert.equal(panel.posted.at(-1).type, 'notice');
  assert.match(panel.posted.at(-1).text, /notebooks\/study_generated.py does not exist yet/);
  fs.mkdirSync(path.join(dir, 'notebooks'));
  fs.writeFileSync(path.join(dir, 'notebooks', 'study_generated.py'), '');
  await controller.handle({ v: 2, type: 'open_artifact', artifact: 'notebook' });
  assert.deepEqual(fake.calls.showTextDocument, [path.join(dir, 'notebooks', 'study_generated.py')]);
});

test('sources: no shell, no network module, no storage of their own', () => {
  const root = path.join(__dirname, '..');
  const walk = dir => fs.readdirSync(path.join(root, dir), { withFileTypes: true }).flatMap(e =>
    (e.isDirectory() ? walk(`${dir}/${e.name}`) : e.name.endsWith('.js') ? [`${dir}/${e.name}`] : []));
  const files = ['extension.js', ...walk('lib'), ...walk('media')];
  assert.ok(files.includes('media/core.js') && files.includes('lib/handlers/decisions.js'));
  for (const f of files) {
    const text = fs.readFileSync(path.join(root, f), 'utf8');
    assert.doesNotMatch(text, /require\(['"](https?|net|tls|dgram|http2|ws|sqlite3?|better-sqlite3|node:sqlite)['"]\)/, f);
    assert.doesNotMatch(text, /shell:\s*true|\bexecSync\b|\bspawn\(|childProcess\.exec\(|\bexec\(/, f);
    assert.doesNotMatch(text, /vscode\.lm\b|localStorage|indexedDB|WebSocket|fetch\(/, f);
  }
});
