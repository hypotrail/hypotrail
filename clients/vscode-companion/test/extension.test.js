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
  await opened.controller.handle({ v: 2, type: 'confirm', proposalId: 'p_5', words: 'Yes, the top 100.', revision: 26 });
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
  assert.deepEqual(fake.calls.panels[0].posted.at(-1), { v: 2, type: 'navigate', tab: 'evidence', kind: 'result', id: rid });
  // A discovered study in the link: opened in the same panel, without a quick pick.
  const picks = fake.calls.quickPick.length;
  const again = await fake.uriHandlers[0].handleUri({ path: '/proposal/p_5', query: `study=${encodeURIComponent(b)}` });
  assert.equal(again.agent.studyDir, b);
  assert.equal(fake.calls.quickPick.length, picks, 'no quick pick for a discovered study');
  assert.equal(fake.calls.panels.length, 1);
  assert.deepEqual(fake.calls.panels[0].posted.at(-1), { v: 2, type: 'navigate', tab: 'decisions', kind: 'proposal', id: 'p_5' });
  // An unknown study in the link: the quick pick asks.
  await fake.uriHandlers[0].handleUri({ path: '/proposal/p_5', query: `study=${encodeURIComponent(path.join(os.tmpdir(), 'elsewhere'))}` });
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
