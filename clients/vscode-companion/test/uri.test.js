'use strict';
// Deep links and "go to a result" input (scope U, WP-U3): lib/uri.js (CLI-CONTRACT-COMPANION
// §11, COMPANION-ADVANCED §4.2, §12 "URI handler", EV-3), and the extension's URI handler
// with the fake `vscode` module and a fake execFile. No VS Code, no CLI process.

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const childProcess = require('child_process');
const { parseDeepLink, resultIdInput, INVALID_LINK, AUTHORITY } = require('../lib/uri');
const { createFake, load } = require('./fake-vscode');
const { payload } = require('./fixture-cli');
const pkg = require('../package.json');

const RID = 'd0af48b239d736c2c2b888841085499145e3fa4cfb56b13540251fa0af3883f5';

test('the authority is <publisher>.<name> of package.json', () => {
  assert.equal(AUTHORITY, `${pkg.publisher}.${pkg.name}`);
});

test('parseDeepLink: result, decision, and proposal links, with an optional absolute study', () => {
  assert.deepEqual(parseDeepLink({ path: `/result/${RID}`, query: '' }), { tab: 'evidence', kind: 'result', id: RID, study: null });
  assert.deepEqual(parseDeepLink({ authority: AUTHORITY, path: `/result/${RID}`, query: 'study=%2Fstudies%2Fbank%20marketing' }),
    { tab: 'evidence', kind: 'result', id: RID, study: '/studies/bank marketing' });
  for (const id of ['prediction_time', 'feature_availability', 'split', 'policy', 'model_choice', 'conclusion']) {
    assert.deepEqual(parseDeepLink({ path: `/decision/${id}`, query: '' }), { tab: 'decisions', kind: 'decision', id, study: null });
  }
  assert.deepEqual(parseDeepLink({ path: '/proposal/p_12', query: '?study=/s' }), { tab: 'decisions', kind: 'proposal', id: 'p_12', study: '/s' });
});

test('parseDeepLink: anything else is not a link (EV-3)', () => {
  const bad = [
    null, {}, { path: 7 }, { path: '' }, { path: '/' }, { path: '/result' }, { path: '/result/' },
    { path: '/result/nothex' }, { path: `/result/${RID.toUpperCase()}` }, { path: `/result/${RID.slice(1)}` },
    { path: `/result/${RID}a` }, { path: `/result/${RID}/more` }, { path: `result/${RID}` }, { path: `//result/${RID}` },
    { path: `/results/${RID}` }, { path: '/decision/budget' }, { path: '/decision/Policy' }, { path: '/proposal/p_' },
    { path: '/proposal/p_1x' }, { path: '/proposal/7' }, { path: '/run/eda.rate_by' },
    { path: `/result/${RID}`, query: 'study=relative/path' }, { path: `/result/${RID}`, query: 'study=' },
    { path: `/result/${RID}`, query: 'study=/a&study=/b' }, { path: `/result/${RID}`, query: 'study=/a&run=1' },
    { path: `/result/${RID}`, query: 'confirm=yes' }, { path: `/result/${RID}`, query: 'study=/a%00b' },
    { path: `/result/${RID}`, fragment: 'x' }, { authority: 'someone.else', path: `/result/${RID}` },
  ];
  for (const uri of bad) assert.equal(parseDeepLink(uri), null, JSON.stringify(uri));
});

test('resultIdInput: a hex prefix of 8 to 64 characters, as the report shows it', () => {
  assert.equal(resultIdInput('  D0AF48B2 '), 'd0af48b2');
  assert.equal(resultIdInput(RID), RID);
  assert.equal(resultIdInput(`r-${RID}`), RID);
  assert.equal(resultIdInput('#r-d0af48b2'), 'd0af48b2');
  assert.equal(resultIdInput('d0af48b2...'), 'd0af48b2');
  assert.equal(resultIdInput('d0af48b2…'), 'd0af48b2');
  for (const t of ['', 'd0af48b', `${RID}0`, 'not an id', 'd0af48b2 extra', 'g0af48b2', null, undefined, 42]) {
    assert.equal(resultIdInput(t), null, String(t));
  }
});

// --- the extension's URI handler (EV-3) --------------------------------------------------

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
    const name = args.includes('evidence') ? 'evidence.binary' : 'summary.binary';
    setImmediate(() => cb(null, JSON.stringify({ ...payload(name), study: options.cwd }), ''));
  };
  return calls;
}

test.afterEach(() => {
  childProcess.execFile = realExecFile;
  delete process.env.HYPOTRAIL_COMPANION;
  delete process.env.HYPOTRAIL_COMPANION_STAGE;
});

test('EV-3: a result link opens the panel on Evidence with that result; an invalid one opens nothing', async () => {
  process.env.HYPOTRAIL_COMPANION = '1';
  process.env.HYPOTRAIL_COMPANION_STAGE = 'v2';
  const calls = fakeExec();
  let fake = createFake({ folders: [makeStudy('link')] });
  let { extension, context } = load(fake);
  extension.activate(context);
  const opened = await fake.uriHandlers[0].handleUri({ path: `/result/${RID}`, query: '' });
  assert.ok(opened);
  assert.equal(fake.calls.panels.length, 1);
  assert.deepEqual(fake.calls.panels[0].posted.at(-1), { v: 2, type: 'navigate', tab: 'evidence', kind: 'result', id: RID });
  assert.equal(calls.length, 0, 'a link reads nothing by itself and never writes');

  fake = createFake({ folders: [makeStudy('badlink')] });
  ({ extension, context } = load(fake));
  extension.activate(context);
  assert.equal(await fake.uriHandlers[0].handleUri({ path: `/result/${RID.slice(0, 63)}g`, query: '' }), null);
  assert.deepEqual(fake.calls.info, [INVALID_LINK]);
  assert.equal(fake.calls.panels.length, 0);
});

test('go to a result: a pasted prefix is resolved through evidence and navigates', async () => {
  process.env.HYPOTRAIL_COMPANION = '1';
  process.env.HYPOTRAIL_COMPANION_STAGE = 'v2';
  const calls = fakeExec();
  const fake = createFake({ folders: [makeStudy('goto')], answers: { inputBox: 'D0AF48B2' } });
  const { extension, context } = load(fake);
  extension.activate(context);
  assert.equal(await fake.commands.executeCommand('hypotrail.companion.goToResult'), RID);
  assert.deepEqual(fake.calls.panels[0].posted.at(-1), { v: 2, type: 'navigate', tab: 'evidence', kind: 'result', id: RID });
  assert.deepEqual(calls.map(a => a.slice(CLI.length - 1, CLI.length + 1)), [['evidence', '--json']]);
});
