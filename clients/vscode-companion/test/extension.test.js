'use strict';
// Extension tests (scope U, WP-0): the entry points added for the advanced companion, with
// the fake `vscode` module and a fake execFile: the reviewer command, "go to a result",
// the URI handler, the study switch, and a settings change. No VS Code, no CLI process.

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const childProcess = require('child_process');
const { createFake, load } = require('./fake-vscode');
const { payload } = require('./fixture-cli');

const realExecFile = childProcess.execFile;
const CLI = ['/opt/py/bin/python', '-m', 'mlkit.study.cli'];

function makeStudy(name) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), `${name}-`));
  fs.mkdirSync(path.join(dir, '.hypotrail'));
  fs.writeFileSync(path.join(dir, '.hypotrail', 'agent.json'), JSON.stringify({ schema: 'hypotrail.agent/1', study: dir, cli: { argv: CLI } }));
  return fs.realpathSync(dir);
}

function fakeExec() {
  const calls = [];
  childProcess.execFile = (file, args, options, cb) => {
    calls.push(args);
    const summary = { ...payload('summary.v0.binary'), study: options.cwd };
    setImmediate(() => cb(null, JSON.stringify(summary), ''));
  };
  return calls;
}

test.afterEach(() => {
  childProcess.execFile = realExecFile;
  delete process.env.HYPOTRAIL_COMPANION;
  delete process.env.HYPOTRAIL_COMPANION_STAGE;
});

async function activate(fake) {
  const { extension, context } = load(fake);
  const api = extension.activate(context);
  return { api, context };
}

test('reviewer command: a reviewer panel, init says reviewer, writes are refused', async () => {
  process.env.HYPOTRAIL_COMPANION = '1';
  // v0.3: the panel has no write at v0 (W1-W3 withdrawn); Regenerate (W5) is v1.
  process.env.HYPOTRAIL_COMPANION_STAGE = 'v1';
  fakeExec();
  const dir = makeStudy('rev');
  const fake = createFake({ folders: [dir] });
  const { api } = await activate(fake);
  const opened = await fake.commands.executeCommand('hypotrail.companion.openReviewer');
  assert.equal(opened.reviewer, true);
  assert.match(fake.calls.panels[0].title, /reviewer/);
  await opened.controller.handle({ v: 2, type: 'ready' });
  const init = fake.calls.panels[0].posted.find(m => m.type === 'init');
  assert.equal(init.reviewer, true);
  await opened.controller.handle({ v: 2, type: 'render' });
  assert.equal(fake.calls.panels[0].posted.at(-1).message, 'Read-only reviewer mode.');
  assert.equal(api.current(), opened);
});

test('go to a result: needs stage v2, and a pasted id of 8 or more hex characters', async () => {
  process.env.HYPOTRAIL_COMPANION = '1';
  fakeExec();
  const dir = makeStudy('go');
  let fake = createFake({ folders: [dir], answers: { inputBox: 'deadbeef' } });
  await activate(fake);
  assert.equal(await fake.commands.executeCommand('hypotrail.companion.goToResult'), null);
  assert.match(fake.calls.info[0], /not available in the current stage/);
  assert.equal(fake.calls.inputBox.length, 0);
  process.env.HYPOTRAIL_COMPANION_STAGE = 'v2';
  fake = createFake({ folders: [dir], answers: { inputBox: 'not an id' } });
  await activate(fake);
  assert.equal(await fake.commands.executeCommand('hypotrail.companion.goToResult'), null);
  assert.deepEqual(fake.calls.info, ['This Hypotrail link is not valid.']);
  assert.equal(fake.calls.panels.length, 0);
  // A valid prefix opens the panel; WP-U3's handler resolves it through `evidence`. This
  // fake CLI answers a summary to every command, so the results cannot be read.
  fake = createFake({ folders: [dir], answers: { inputBox: 'DEADBEEF00' } });
  await activate(fake);
  assert.equal(await fake.commands.executeCommand('hypotrail.companion.goToResult'), null);
  assert.equal(fake.calls.panels.length, 1);
  assert.match(fake.calls.info.at(-1), /^The results of this study could not be read: /);
});

test('URI handler: an invalid link opens nothing', async () => {
  process.env.HYPOTRAIL_COMPANION = '1';
  const calls = fakeExec();
  const fake = createFake({ folders: [makeStudy('uri')] });
  await activate(fake);
  assert.equal(await fake.uriHandlers[0].handleUri({ path: '/result/nothex', query: '' }), null);
  assert.deepEqual(fake.calls.info, ['This Hypotrail link is not valid.']);
  assert.equal(fake.calls.panels.length, 0);
  assert.equal(calls.length, 0);
});

test('INV-11 untrusted workspace: the reviewer command, go to a result, and a link are refused', async () => {
  process.env.HYPOTRAIL_COMPANION = '1';
  const calls = fakeExec();
  const fake = createFake({ folders: [makeStudy('trust')], trusted: false });
  await activate(fake);
  await fake.commands.executeCommand('hypotrail.companion.openReviewer');
  await fake.commands.executeCommand('hypotrail.companion.goToResult');
  await fake.uriHandlers[0].handleUri({ path: '/result/' + 'a'.repeat(64), query: '' });
  assert.equal(fake.calls.error.length, 3);
  assert.ok(fake.calls.error.every(m => /trusted workspace/.test(m)));
  assert.equal(calls.length, 0);
});

test('settings change posts init again; the study switch offers "Pick another folder..."', async () => {
  process.env.HYPOTRAIL_COMPANION = '1';
  fakeExec();
  const a = makeStudy('a');
  const b = makeStudy('b');
  const fake = createFake({ folders: [a, b], answers: { quickPick: items => items[0] } });
  await activate(fake);
  const opened = await fake.commands.executeCommand('hypotrail.companion.open');
  await opened.controller.handle({ v: 2, type: 'ready' });
  const panel = fake.calls.panels[0];
  fake.changeSettings({ 'hypotrail.companion.stage': 'v1' });
  assert.deepEqual(panel.posted.filter(m => m.type === 'init').at(-1).stage, 'v1');
  await opened.controller.handle({ v: 2, type: 'switch_study' });
  // WP-U1: switch_study runs the extension's study switch, which shows the quick pick.
  assert.equal(fake.calls.quickPick.length, 2, 'switch_study shows the quick pick (WP-U1 handler)');
  const opened2 = await opened.controller.context.host.switchStudy();
  assert.equal(fake.calls.quickPick.at(-1).items.at(-1).label, 'Pick another folder...');
  assert.equal(opened2.agent.studyDir, a);
});

test('URI handler (WP-I): a valid link opens the panel and navigates; its study must be a discovered one', async () => {
  process.env.HYPOTRAIL_COMPANION = '1';
  process.env.HYPOTRAIL_COMPANION_STAGE = 'v2';
  fakeExec();
  const a = makeStudy('link-a');
  const b = makeStudy('link-b');
  const rid = 'a'.repeat(64);
  const fake = createFake({ folders: [a, b], answers: { quickPick: items => items[0] } });
  const { api } = await activate(fake);
  // No study in the link: the quick pick (two studies), then the navigation.
  const opened = await fake.uriHandlers[0].handleUri({ path: `/result/${rid}`, query: '' });
  assert.equal(opened.agent.studyDir, a);
  assert.deepEqual(fake.calls.panels[0].posted.at(-1), { v: 2, type: 'navigate', anchor: 'path', kind: 'result', id: rid });
  // A discovered study in the link: opened in the same panel, without a quick pick.
  const picks = fake.calls.quickPick.length;
  // vscode.Uri.query is decoded: the handler gets the path as is.
  const again = await fake.uriHandlers[0].handleUri({ path: '/proposal/p_5', query: `study=${b}` });
  assert.equal(again.agent.studyDir, b);
  assert.equal(fake.calls.quickPick.length, picks, 'no quick pick for a discovered study');
  assert.equal(fake.calls.panels.length, 1);
  assert.deepEqual(fake.calls.panels[0].posted.at(-1), { v: 2, type: 'navigate', anchor: 'path', kind: 'proposal', id: 'p_5' });
  // An unknown study in the link: the quick pick asks.
  await fake.uriHandlers[0].handleUri({ path: '/proposal/p_5', query: `study=${path.join(os.tmpdir(), 'elsewhere')}` });
  assert.equal(fake.calls.quickPick.length, picks + 1);
  assert.equal(api.current().agent.studyDir, a, 'the junior chose a study in the quick pick');
});

test('M2, INV-10: turning the master flag off while the panel is open disposes the panel, its controller and its watcher', async () => {
  const calls = fakeExec();
  const dir = makeStudy('flag-off');
  const fake = createFake({ folders: [dir], settings: { 'hypotrail.companion.enabled': true } });
  const { api } = await activate(fake);
  const opened = await fake.commands.executeCommand('hypotrail.companion.open');
  await opened.controller.handle({ v: 2, type: 'ready' });
  const panel = fake.calls.panels[0];
  const controller = opened.controller;
  // Another setting: the panel stays.
  fake.changeSettings({ 'hypotrail.companion.stage': 'v1' });
  assert.equal(panel.disposed, false);
  fake.changeSettings({ 'hypotrail.companion.enabled': false });
  assert.equal(panel.disposed, true, 'the panel is closed');
  assert.equal(api.current(), null);
  assert.equal(opened.watcher, null, 'the watcher is disposed');
  assert.equal(opened.controller, null, 'the controller is detached');
  const before = calls.length;
  const posted = panel.posted.length;
  await controller.refresh();
  assert.equal(calls.length, before, 'no process starts after the flag is off');
  assert.equal(panel.posted.length, posted);
  // The command now says the companion is disabled, and opens nothing.
  await fake.commands.executeCommand('hypotrail.companion.open');
  assert.equal(fake.calls.panels.length, 1);
  assert.match(fake.calls.info.at(-1), /Companion disabled \(feature flag\)/);
});

test('M2: the environment override keeps the companion on when the setting is turned off', async () => {
  process.env.HYPOTRAIL_COMPANION = '1';
  fakeExec();
  const dir = makeStudy('flag-env');
  const fake = createFake({ folders: [dir], settings: { 'hypotrail.companion.enabled': true } });
  await activate(fake);
  await fake.commands.executeCommand('hypotrail.companion.open');
  fake.changeSettings({ 'hypotrail.companion.enabled': false });
  assert.equal(fake.calls.panels[0].disposed, false);
});

test('WP-A5 local launch: "Open in Marimo" starts marimo run or edit in a named terminal with an argument list, reused per file', async () => {
  process.env.HYPOTRAIL_COMPANION = '1';
  const dir = makeStudy('marimo');
  fs.mkdirSync(path.join(dir, 'notebooks'));
  fs.writeFileSync(path.join(dir, 'notebooks', 'study_generated.py'), '# generated\n');
  fs.writeFileSync(path.join(dir, 'notebooks', 'workbench.py'), '# workbench\n');
  const calls = [];
  childProcess.execFile = (file, args, options, cb) => {
    calls.push(args);
    // `status --json` (the view) has no deliverables in this fake: the launch falls back to
    // the argv recorded in agent.json.
    const body = args.includes('--summary') ? { ...payload('summary.v0.binary'), study: options.cwd }
      : { schema: 'hypotrail.status/1', ok: true, study: options.cwd, revision: 26, view: {} };
    setImmediate(() => cb(null, JSON.stringify(body), ''));
  };
  const fake = createFake({ folders: [dir] });
  await activate(fake);
  const opened = await fake.commands.executeCommand('hypotrail.companion.open');
  await opened.controller.handle({ v: 2, type: 'ready' });
  await opened.controller.handle({ v: 2, type: 'open_marimo', artifact: 'notebook' });
  assert.equal(fake.calls.terminals.length, 1);
  const t = fake.calls.terminals[0];
  assert.equal(t.options.shellPath, CLI[0]);
  assert.deepEqual(t.options.shellArgs, ['-m', 'marimo', 'run', path.join(dir, 'notebooks', 'study_generated.py')]);
  assert.equal(t.options.cwd, dir);
  assert.equal(t.options.name, 'Hypotrail · marimo run study_generated.py');
  assert.ok(!('shellArgs' in t.options) || Array.isArray(t.options.shellArgs), 'an argument list, not a shell string');
  // WP-A7: the summary carries `deliverables` (CLI-CONTRACT §3), so the launch reads no
  // `status --json` (its argv names the fixture's study, not this one: the agent.json form is used).
  assert.ok(!calls.some(a => a.includes('status') && !a.includes('--summary')), 'no status --json read');
  // The same file again: the open terminal is shown, no second one.
  await opened.controller.handle({ v: 2, type: 'open_marimo', artifact: 'notebook' });
  assert.equal(fake.calls.terminals.length, 1);
  assert.ok(t.shown >= 2);
  await opened.controller.handle({ v: 2, type: 'open_marimo', artifact: 'workbench' });
  assert.equal(fake.calls.terminals.length, 2);
  assert.deepEqual(fake.calls.terminals[1].options.shellArgs, ['-m', 'marimo', 'edit', path.join(dir, 'notebooks', 'workbench.py')]);
  // A closed terminal is not reused.
  t.dispose();
  await opened.controller.handle({ v: 2, type: 'open_marimo', artifact: 'notebook' });
  assert.equal(fake.calls.terminals.length, 3);
  const notices = fake.calls.panels[0].posted.filter(m => m.type === 'notice').map(m => m.text);
  assert.ok(notices.some(n => /Started "marimo run"/.test(n)), notices.join('\n'));
});
