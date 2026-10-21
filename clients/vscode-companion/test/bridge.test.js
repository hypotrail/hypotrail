'use strict';
// Agent bridge tests (scope U, WP-U5; COMPANION-ADVANCED §6.8, AB-1, AB-2): the fixed
// template, the clipboard-only path, the guarded chat insertion, and the guarantee that
// nothing is ever sent. Controller with the fixture CLI, then the extension with the fake
// `vscode` module and a fake execFile. No VS Code, no chat, no CLI process.

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const childProcess = require('child_process');
const { createController } = require('../lib/controller');
const bridge = require('../lib/bridge');
const { createFake, load } = require('./fake-vscode');
const { fakeCli, payload, fixture, defaultRoute } = require('./fixture-cli');

const AGENT = { argv: ['/opt/py/bin/python', '-m', 'mlkit.study.cli'], studyDir: '/studies/bank marketing "demo"' };
const RID = '744b2d1cffbbdb905b9492fca6de249283b2144d61faaeeab794134ae0878db8';

function make({ settings = {}, host = {}, task = 'binary' } = {}) {
  const posted = [];
  const runCli = fakeCli(undefined, { agentArgv: AGENT.argv, task });
  const c = createController({ agent: AGENT, post: m => posted.push(m), runCli, settings: { stage: 'v2', ...settings }, host,
    exists: () => true, uuid: () => '0f8fad5b-d9cb-469f-a165-70867728950e' });
  return { c, posted, runCli, notices: () => posted.filter(m => m.type === 'notice') };
}

function recordingHost({ failInsert = false } = {}) {
  const calls = { clipboard: [], commands: [] };
  return {
    calls,
    writeClipboard: async text => { calls.clipboard.push(text); },
    executeCommand: async (id, ...args) => {
      calls.commands.push({ id, args });
      if (failInsert) throw new Error(`command '${id}' not found`);
      return undefined;
    },
  };
}

/** Every string that a decision card or the study could carry and the bridge must never copy. */
function forbiddenTexts() {
  const out = new Set();
  for (const name of ['summary.binary', 'decisions.binary', 'decisions.binary.injection', 'handoff.binary']) {
    const walk = v => {
      if (v && typeof v === 'object') {
        for (const [k, x] of Object.entries(v)) {
          if (['user_words', 'restatement', 'rationale'].includes(k) && typeof x === 'string' && x.length > 8) out.add(x);
          walk(x);
        }
      }
    };
    walk(payload(name));
  }
  return [...out];
}

test('template: the fixed English text of §6.8, the id of a result as its first 8 characters', () => {
  const text = bridge.template({ studyDir: AGENT.studyDir, revision: 26, about: { kind: 'result', id: RID },
    label: 'eda.target_rate, current', question: '' });
  assert.equal(text, [
    'Question about my Hypotrail study (bank marketing "demo"), revision 26.',
    'About: result 744b2d1c (eda.target_rate, current).',
    'My question: Can you explain this and what it means for my study?',
    'This is a question, not a confirmation of anything.',
  ].join('\n'));
  const typed = bridge.template({ studyDir: AGENT.studyDir, revision: 26, about: { kind: 'decision', id: 'policy' },
    label: 'proposal p_5, open', question: '  Why the top 100 and not 150?  ' });
  assert.equal(typed.split('\n')[1], 'About: decision policy (proposal p_5, open).');
  assert.equal(typed.split('\n')[2], 'My question: Why the top 100 and not 150?');
  assert.equal(bridge.template({ studyDir: '/s/x', revision: 3, about: { kind: 'step', id: 'split' } }).split('\n')[1], 'About: step split.');
});

test('AB-1: the text never holds draft words, a restatement, a rationale, or a study value; nothing is sent', async () => {
  const host = recordingHost();
  const { c, runCli, notices, posted } = make({ host, settings: { stage: 'v3' } });
  await c.handle({ v: 2, type: 'ready' });
  const snap = c.snapshot();
  assert.ok(snap.proposals[0].restatement.length > 8, 'the snapshot carries a restatement');
  const before = runCli.calls.length;
  // The webview sends only {about, question, mode}: the card's draft words never leave it,
  // and an extra field carrying them is dropped by the protocol (never answered).
  await c.handle({ v: 2, type: 'ask_agent', about: { kind: 'proposal', id: 'p_5' }, question: '', mode: 'copy',
    words: 'Yes: call the 100 best-scored clients.' });
  assert.equal(host.calls.clipboard.length, 0, 'an ask_agent with an extra field is dropped');
  for (const about of [{ kind: 'proposal', id: 'p_5' }, { kind: 'decision', id: 'policy' }, { kind: 'step', id: 'conclusion' },
    { kind: 'limit', id: 'unconfirmed_decisions' }, { kind: 'result', id: RID }, { kind: 'term', id: 'base_rate' },
    { kind: 'execution', id: 'e_1' }]) {
    await c.handle({ v: 2, type: 'ask_agent', about, question: '', mode: 'copy' });
  }
  assert.equal(host.calls.clipboard.length, 7);
  const forbidden = forbiddenTexts();
  assert.ok(forbidden.length >= 5, forbidden.length);
  for (const text of host.calls.clipboard) {
    const lines = text.split('\n');
    assert.equal(lines.length, 4, text);
    assert.match(lines[0], /^Question about my Hypotrail study \(bank marketing "demo"\), revision 26\.$/);
    assert.match(lines[1], /^About: (proposal|decision|step|limit|result|term|execution) [a-z0-9_.]+( \([^()]*\))?\.$/);
    assert.equal(lines[3], bridge.CLOSING);
    for (const f of forbidden) assert.ok(!text.includes(f), `${text} holds ${f}`);
    assert.doesNotMatch(lines[1], /\d+\.\d|%/, 'no study value');
  }
  assert.equal(host.calls.clipboard[0].split('\n')[1], 'About: proposal p_5 (decision policy, open).');
  assert.equal(host.calls.clipboard[4].split('\n')[1], 'About: result 744b2d1c (eda.target_rate, current).');
  assert.deepEqual(host.calls.commands, [], 'copy runs no command');
  assert.ok(notices().every(n => n.text === bridge.COPIED));
  // The only CLI calls are reads (evidence for the result label, explain for the term).
  const tails = runCli.calls.slice(before).map(x => x.tail[0]);
  assert.deepEqual([...new Set(tails)].sort(), ['evidence', 'explain']);
  assert.ok(!posted.some(m => m.type === 'outcome'), 'the bridge is not a write');
  // No vscode.lm, no chat submission option anywhere in the bridge.
  for (const f of ['lib/bridge.js', 'lib/handlers/bridge.js', 'media/terms.js']) {
    const src = fs.readFileSync(path.join(__dirname, '..', f), 'utf8');
    assert.doesNotMatch(src, /vscode\.lm|sendRequest|isPartialQuery:\s*false|submit:\s*true|autoSend/, f);
  }
});

test('AB-2: with chatInsert false only the clipboard is used, even for an insert request', async () => {
  const host = recordingHost();
  const { c, notices } = make({ host });
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'ask_agent', about: { kind: 'decision', id: 'policy' }, question: 'Why?', mode: 'insert' });
  assert.deepEqual(host.calls.commands, []);
  assert.equal(host.calls.clipboard.length, 1);
  assert.equal(notices().at(-1).text, 'Copied. Paste it into the chat with your assistant.');
});

test('AB-2: with chatInsert true, the chat input gets the text unsent; a throwing command falls back to the clipboard', async () => {
  const ok = recordingHost();
  const a = make({ host: ok, settings: { chatInsert: true } });
  await a.c.handle({ v: 2, type: 'ready' });
  await a.c.handle({ v: 2, type: 'ask_agent', about: { kind: 'decision', id: 'policy' }, question: 'Why?', mode: 'insert' });
  assert.equal(ok.calls.commands.length, 1);
  assert.equal(ok.calls.commands[0].id, 'workbench.action.chat.open');
  assert.deepEqual(Object.keys(ok.calls.commands[0].args[0]), ['query', 'isPartialQuery']);
  assert.equal(ok.calls.commands[0].args[0].isPartialQuery, true);
  assert.match(ok.calls.commands[0].args[0].query, /^Question about my Hypotrail study/);
  assert.deepEqual(ok.calls.clipboard, []);
  assert.equal(a.notices().at(-1).text, bridge.INSERTED);
  // Copy stays the clipboard even with chatInsert on.
  await a.c.handle({ v: 2, type: 'ask_agent', about: { kind: 'decision', id: 'policy' }, question: '', mode: 'copy' });
  assert.equal(ok.calls.commands.length, 1);
  assert.equal(ok.calls.clipboard.length, 1);

  const failing = recordingHost({ failInsert: true });
  const b = make({ host: failing, settings: { chatInsert: true } });
  await b.c.handle({ v: 2, type: 'ready' });
  await b.c.handle({ v: 2, type: 'ask_agent', about: { kind: 'decision', id: 'policy' }, question: 'Why?', mode: 'insert' });
  assert.equal(failing.calls.commands.length, 1);
  assert.equal(failing.calls.clipboard.length, 1);
  assert.equal(failing.calls.clipboard[0], failing.calls.commands[0].args[0].query, 'the same text is copied');
  assert.equal(b.notices().at(-1).text, bridge.FELL_BACK);
  assert.match(bridge.FELL_BACK, /copied instead/);
});

test('the bridge is stage v0 (WP-E1), stays in reviewer mode, and a missing clipboard says nothing was sent', async () => {
  const host = recordingHost();
  // WP-E1: the read-only proposal card asks the agent at every stage, so the bridge is v0.
  const v0 = make({ host, settings: { stage: 'v0' } });
  await v0.c.handle({ v: 2, type: 'ask_agent', about: { kind: 'proposal', id: 'p_7' }, question: '', mode: 'copy' });
  assert.equal(host.calls.clipboard.length, 1);
  assert.equal(v0.c.diagnostics().ignored, 0);
  assert.match(host.calls.clipboard[0], /^About: proposal p_7/m);
  assert.match(host.calls.clipboard[0], new RegExp(bridge.CLOSING));
  const reviewer = make({ host, settings: { reviewer: true } });
  await reviewer.c.handle({ v: 2, type: 'ready' });
  await reviewer.c.handle({ v: 2, type: 'ask_agent', about: { kind: 'decision', id: 'policy' }, question: '', mode: 'copy' });
  assert.equal(host.calls.clipboard.length, 2);
  const none = make({ host: {} });
  await none.c.handle({ v: 2, type: 'ask_agent', about: { kind: 'decision', id: 'policy' }, question: '', mode: 'copy' });
  assert.deepEqual(none.notices().at(-1), { v: 2, type: 'notice', politeness: 'assertive', text: bridge.FAILED });
});

// --- through the extension: vscode.env.clipboard and vscode.commands -----------------------

const realExecFile = childProcess.execFile;
test.afterEach(() => {
  childProcess.execFile = realExecFile;
  delete process.env.HYPOTRAIL_COMPANION;
  delete process.env.HYPOTRAIL_COMPANION_STAGE;
});

function makeStudy() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'bridge-'));
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
    const name = defaultRoute(tail);
    const f = fixture(name);
    setImmediate(() => cb(f.about.exit_code ? Object.assign(new Error('exit'), { code: f.about.exit_code }) : null,
      JSON.stringify({ ...f.payload, study: options.cwd }), ''));
  };
  return calls;
}

test('CR.8: the chatInsert setting is ignored until verified: init says false and "insert" copies', async () => {
  process.env.HYPOTRAIL_COMPANION = '1';
  process.env.HYPOTRAIL_COMPANION_STAGE = 'v2';
  fakeExec();
  const fake = createFake({ folders: [makeStudy()], settings: { 'hypotrail.companion.chatInsert': true } });
  const { extension, context } = load(fake);
  extension.activate(context);
  const opened = await fake.commands.executeCommand('hypotrail.companion.open');
  await opened.controller.handle({ v: 2, type: 'ready' });
  assert.ok(fake.calls.panels[0].posted.filter(m => m.type === 'init').every(m => m.chatInsert === false));
  await opened.controller.handle({ v: 2, type: 'ask_agent', about: { kind: 'proposal', id: 'p_5' }, question: '', mode: 'insert' });
  assert.ok(!fake.calls.executed.some(x => x.id === 'workbench.action.chat.open'), 'no chat command');
  assert.equal(fake.calls.clipboard.length, 1);
});

test('AB-1, AB-2 through the extension: vscode.env.clipboard only; no chat command unless chatInsert', async () => {
  process.env.HYPOTRAIL_COMPANION = '1';
  process.env.HYPOTRAIL_COMPANION_STAGE = 'v2';
  const exec = fakeExec();
  const dir = makeStudy();
  const fake = createFake({ folders: [dir] });
  const { extension, context } = load(fake);
  extension.activate(context);
  const opened = await fake.commands.executeCommand('hypotrail.companion.open');
  await opened.controller.handle({ v: 2, type: 'ready' });
  await opened.controller.handle({ v: 2, type: 'ask_agent', about: { kind: 'proposal', id: 'p_5' }, question: '', mode: 'insert' });
  assert.equal(fake.calls.clipboard.length, 1);
  assert.match(fake.calls.clipboard[0], new RegExp(`^Question about my Hypotrail study \\(${path.basename(dir)}\\), revision 26\\.`));
  assert.ok(!fake.calls.executed.some(x => x.id === 'workbench.action.chat.open'), 'chatInsert is off by default');
  assert.equal(fake.calls.panels[0].posted.at(-1).text, bridge.COPIED);
  assert.ok(exec.every(t => ['status'].includes(t[0])), JSON.stringify(exec));
});
