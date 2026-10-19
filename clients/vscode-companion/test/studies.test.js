'use strict';
// Study discovery and the study switch (scope U, WP-U1; COMPANION-ADVANCED §6.1.6, ST-1,
// ST-2): lib/study.js `findStudies` on temporary folders, and the switch through the
// extension with the fake `vscode` module and a fake execFile. No CLI process is started.

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const childProcess = require('child_process');
const { findStudies, MAX_VISITED } = require('../lib/study');
const { createFake, load } = require('./fake-vscode');
const { payload } = require('./fixture-cli');

const CLI = ['/opt/py/bin/python', '-m', 'mlkit.study.cli'];
const realExecFile = childProcess.execFile;
const realWatch = fs.watch;

function tmp() {
  return fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'ht-studies-')));
}

function study(dir) {
  fs.mkdirSync(path.join(dir, '.hypotrail'), { recursive: true });
  fs.writeFileSync(path.join(dir, '.hypotrail', 'agent.json'), JSON.stringify({ schema: 'hypotrail.agent/1', study: dir, cli: { argv: CLI } }));
  return dir;
}

test.afterEach(() => {
  childProcess.execFile = realExecFile;
  fs.watch = realWatch;
  delete process.env.HYPOTRAIL_COMPANION;
  delete process.env.HYPOTRAIL_COMPANION_STAGE;
});

test('ST-1, ST-2: studies at depth 0, 1, and 2 are found, sorted; deeper ones are not', () => {
  const root = tmp();
  const top = study(root);
  const one = study(path.join(root, 'zeta'));
  const two = study(path.join(root, 'alpha', 'bank marketing "demo"'));
  study(path.join(root, 'alpha', 'beta', 'too-deep'));
  assert.deepEqual(findStudies([root]), [top, two, one].sort());
  assert.ok(!findStudies([root]).some(d => d.endsWith('too-deep')), 'ST-2: depth 3 is not listed');
  // The deep study is still reachable as a workspace folder of its own (or by "Pick another folder...").
  assert.deepEqual(findStudies([path.join(root, 'alpha', 'beta', 'too-deep')]), [path.join(root, 'alpha', 'beta', 'too-deep')]);
});

test('§6.1.6: node_modules, .git, .venv, and dot-folders are skipped; symbolic links are not followed', () => {
  const root = tmp();
  const kept = study(path.join(root, 'kept'));
  for (const skipped of ['node_modules', '.git', '.venv', '.cache']) study(path.join(root, skipped, 'inner'));
  study(path.join(root, 'node_modules'));
  study(path.join(root, '.hidden'));
  const outside = study(path.join(tmp(), 'outside'));
  fs.symlinkSync(outside, path.join(root, 'link'), 'dir');
  assert.deepEqual(findStudies([root]), [kept]);
});

test('§6.1.6: duplicates and invalid folders are ignored; the visit stops after the folder limit', () => {
  const root = tmp();
  const a = study(path.join(root, 'a'));
  assert.deepEqual(findStudies([root, root, path.join(root, 'a'), '', null, path.join(root, 'missing')]), [a]);
  assert.equal(MAX_VISITED, 500);
  // A wide tree: the limit cuts the search (breadth first), so a study after it is not listed.
  const wide = tmp();
  for (let i = 0; i < 30; i += 1) fs.mkdirSync(path.join(wide, `d${String(i).padStart(2, '0')}`));
  study(path.join(wide, 'd29'));
  assert.deepEqual(findStudies([wide], fs, { maxVisited: 10 }), []);
  assert.deepEqual(findStudies([wide], fs, { maxVisited: 31 }), [path.join(wide, 'd29')]);
  let visits = 0;
  const counting = { ...fs, statSync: (...args) => { visits += 1; return fs.statSync(...args); },
    readdirSync: fs.readdirSync.bind(fs) };
  findStudies([wide], counting, { maxVisited: 12 });
  assert.equal(visits, 12, 'one agent.json probe per visited folder, at most the limit');
});

function fakeExec() {
  const calls = [];
  childProcess.execFile = (file, args, options, cb) => {
    calls.push(args);
    const studyDir = args[args.indexOf('--study') + 1];
    setImmediate(() => cb(null, JSON.stringify({ ...payload('summary.v0.binary'), study: studyDir }), ''));
  };
  return calls;
}

function fakeWatch() {
  const watchers = [];
  fs.watch = (target, options, handler) => {
    const w = { target, closed: false, close() { this.closed = true; }, on() { return this; } };
    watchers.push(w);
    return w;
  };
  return watchers;
}

test('ST-1: two studies in one workspace give a quick pick of both; switching reads the new study and disposes the old watcher', async () => {
  process.env.HYPOTRAIL_COMPANION = '1';
  process.env.HYPOTRAIL_COMPANION_STAGE = 'v1';
  const calls = fakeExec();
  const watchers = fakeWatch();
  const root = tmp();
  const a = study(path.join(root, 'auto-mpg'));
  const b = study(path.join(root, 'bank-marketing'));
  let choice = 0;
  const fake = createFake({ folders: [root], answers: { quickPick: items => items[choice] } });
  const { extension, context } = load(fake);
  const api = extension.activate(context);
  const first = await fake.commands.executeCommand('hypotrail.companion.open');
  const pick = fake.calls.quickPick[0].items.filter(i => i.dir).map(i => i.dir);
  assert.deepEqual(pick, [a, b], 'a quick pick of both studies, from one workspace folder');
  // WP-I (U1 request): labelled with the folder name, described by the path (§6.1.6).
  assert.deepEqual(fake.calls.quickPick[0].items.filter(i => i.dir).map(i => [i.label, i.description]),
    [['auto-mpg', a], ['bank-marketing', b]]);
  assert.equal(first.agent.studyDir, a);
  await first.controller.handle({ v: 2, type: 'ready' });
  assert.ok(calls.some(args => args.includes('status') && args[args.indexOf('--study') + 1] === a));
  assert.equal(watchers.length, 1);
  assert.equal(watchers[0].target, path.join(a, '.hypotrail'));

  // The header's switcher posts switch_study; the WP-U1 handler runs the extension's switch.
  choice = 1;
  const oldController = first.controller;
  await oldController.handle({ v: 2, type: 'switch_study' });
  const items = fake.calls.quickPick.at(-1).items;
  assert.equal(items.at(-1).label, 'Pick another folder...');
  // WP-I (U1 request, §6.1.6): the new study opens in the same panel; the old controller
  // and watcher are disposed.
  assert.equal(fake.calls.panels.length, 1, 'the same panel');
  assert.equal(fake.calls.panels[0].disposed, false);
  assert.notEqual(api.current().controller, oldController, 'a new controller');
  assert.equal(api.current().agent.studyDir, b);
  const before = fake.calls.panels[0].posted.length;
  await oldController.refresh();
  assert.equal(fake.calls.panels[0].posted.length, before, 'the old controller is disposed: it posts nothing');
  assert.equal(watchers[0].closed, true, 'the old watcher is disposed');
  assert.equal(watchers.length, 2);
  assert.equal(watchers[1].target, path.join(b, '.hypotrail'));
  const panel = fake.calls.panels[0];
  panel.receive({ v: 2, type: 'ready' });
  await new Promise(resolve => setTimeout(resolve, 50));
  assert.ok(calls.some(args => args.includes('status') && args[args.indexOf('--study') + 1] === b), 'status on the new --study');
  assert.ok(calls.filter(args => args.includes('status')).every(args => args.includes('--digest')), 'v1 reads the digest');
});

test('ST-2: "Pick another folder..." reaches a study deeper than two levels', async () => {
  process.env.HYPOTRAIL_COMPANION = '1';
  process.env.HYPOTRAIL_COMPANION_STAGE = 'v1';
  fakeExec();
  fakeWatch();
  const root = tmp();
  const a = study(path.join(root, 'a'));
  const deep = study(path.join(root, 'x', 'y', 'z', 'deep'));
  const fake = createFake({ folders: [root], answers: { quickPick: items => items.at(-1), openDialog: [deep] } });
  const { extension, context } = load(fake);
  const api = extension.activate(context);
  const first = await fake.commands.executeCommand('hypotrail.companion.open');
  assert.equal(first.agent.studyDir, a, 'one study found: opened directly');
  await first.controller.handle({ v: 2, type: 'switch_study' });
  assert.ok(!fake.calls.quickPick[0].items.some(i => i.dir === deep), 'not listed');
  assert.equal(fake.calls.openDialog.length, 1);
  assert.equal(api.current().agent.studyDir, deep, 'the deep study is open');
  assert.equal(fake.calls.panels.at(-1).disposed, false);
  assert.equal(fake.calls.panels.length, 1, 'in the same panel (WP-I, §6.1.6)');
});
