'use strict';
// Argv tests (scope U, frozen by WP-0): the exact argv of every read of
// COMPANION-ADVANCED §5 and of the seven writes of §7, with a study path holding spaces and
// quotes, free text in `--opt=value` form (a text that starts with "-" stays one token), and
// the per-op timeouts and buffer of `run()`.

const test = require('node:test');
const assert = require('node:assert/strict');
const cli = require('../lib/cli');

const A = ['/opt/my tools/py "q"/bin/python', '-m', 'mlkit.study.cli'];
const S = '/studies/my "study" it\'s here';
const AGENT = { argv: A, studyDir: S };
const ID = '0f8fad5b-d9cb-469f-a165-70867728950e';
const RID = 'b'.repeat(64);
const T = ['--json', '--study', S];

test('reads: exact argv (§5)', () => {
  assert.deepEqual(cli.statusArgv(AGENT), [...A, 'status', '--summary', ...T]);
  assert.deepEqual(cli.statusArgv(AGENT, { digest: true }), [...A, 'status', '--summary', '--digest', ...T]);
  assert.deepEqual(cli.statusArgv(AGENT, { digest: true, since: 0 }), [...A, 'status', '--summary', '--digest', '--since', '0', ...T]);
  assert.deepEqual(cli.decisionsArgv(AGENT), [...A, 'decisions', ...T]);
  assert.deepEqual(cli.previewEffectsArgv(AGENT, { proposalId: 'p_7' }), [...A, 'preview', 'effects', 'p_7', ...T]);
  assert.deepEqual(cli.evidenceArgv(AGENT), [...A, 'evidence', ...T]);
  assert.deepEqual(cli.evidenceArgv(AGENT, { resultId: RID }), [...A, 'evidence', '--result', RID, ...T]);
  assert.deepEqual(cli.previewPolicyArgv(AGENT, { rules: ['capacity:100', 'threshold:0.2'], intervals: true }),
    [...A, 'preview', 'policy', '--rule', 'capacity:100', '--rule', 'threshold:0.2', '--intervals', ...T]);
  assert.deepEqual(cli.previewProposalArgv(AGENT, { decisionId: 'policy', value: 'capacity:100' }),
    [...A, 'preview', 'proposal', 'policy', '--value=capacity:100', ...T]);
  assert.deepEqual(cli.checkArgv(AGENT), [...A, 'check', ...T]);
  assert.deepEqual(cli.explainArgv(AGENT), [...A, 'explain', ...T]);
  assert.deepEqual(cli.sessionReportArgv(AGENT), [...A, 'session-report', ...T]);
  // WP-A7: the data card of the Data & EDA tab, a read like the others.
  assert.deepEqual(cli.dataArgv(AGENT), [...A, 'data', ...T]);
  for (const bad of [() => cli.previewEffectsArgv(AGENT, { proposalId: 'p_1; rm' }),
    () => cli.evidenceArgv(AGENT, { resultId: 'ABC' }), () => cli.previewPolicyArgv(AGENT, { rules: [] }),
    () => cli.previewPolicyArgv(AGENT, { rules: ['capacity:0'] }), () => cli.statusArgv(AGENT, { digest: true, since: -1 }),
    () => cli.previewProposalArgv(AGENT, { decisionId: 'split', value: 'x' })]) {
    assert.throws(bad, cli.ArgvError);
  }
});

test('writes: exact argv of W1-W7 (§7)', () => {
  const words = '-- yes: "quoted" & <b>not</b> html';
  assert.deepEqual(cli.WRITES.W1(AGENT, { proposalId: 'p_1', words, requestId: ID, expectedRevision: 3 }),
    [...A, 'decide', 'confirm', 'p_1', `--user-words=${words}`, '--channel', 'webview', '--actor', 'user',
      '--request-id', ID, '--expected-revision', '3', ...T]);
  assert.deepEqual(cli.WRITES.W2(AGENT, { proposalId: 'p_1', requestId: ID, expectedRevision: 3 }),
    [...A, 'decide', 'withdraw', 'p_1', '--request-id', ID, '--expected-revision', '3', ...T]);
  assert.deepEqual(cli.WRITES.W3(AGENT, { decisionId: 'policy', value: 'capacity:100', restatement: '-Adopt the rule.',
    rationale: 'Chosen in the panel.', requestId: ID, expectedRevision: 26 }),
  [...A, 'decide', 'propose', 'policy', '--value=capacity:100', '--restatement=-Adopt the rule.',
    '--rationale=Chosen in the panel.', '--channel', 'webview', '--request-id', ID, '--expected-revision', '26', ...T]);
  assert.deepEqual(cli.WRITES.W4(AGENT, { activity: 'eda.distribution', column: '-age', requestId: ID, expectedRevision: 3 }),
    [...A, 'run', 'eda.distribution', '--column=-age', '--request-id', ID, '--expected-revision', '3', ...T]);
  assert.deepEqual(cli.WRITES.W5(AGENT), [...A, 'render', ...T]);
  assert.deepEqual(cli.WRITES.W6(AGENT, { executionId: 'e_4c1d', words: 'I know it stopped.', requestId: ID, expectedRevision: 3 }),
    [...A, 'run', '--acknowledge-interruption', 'e_4c1d', '--user-words=I know it stopped.', '--request-id', ID,
      '--expected-revision', '3', ...T]);
  // CR.6: the export names the revision the junior saw, so the engine refuses a stale one;
  // there is no form without the option (an unknown `legacy` flag changes nothing).
  assert.deepEqual(cli.WRITES.W7(AGENT, { parent: '/tmp/hand off', revision: 26 }),
    [...A, 'export', 'handoff', '--out=/tmp/hand off/revision-26', '--expected-revision', '26', ...T]);
  assert.deepEqual(cli.WRITES.W7(AGENT, { parent: '/tmp/hand off', revision: 26, legacy: true }),
    cli.WRITES.W7(AGENT, { parent: '/tmp/hand off', revision: 26 }));
});

test('timeouts and buffer (§7, §11)', () => {
  assert.equal(cli.MAX_BUFFER, 16 * 1024 * 1024);
  assert.deepEqual({ ...cli.TIMEOUTS }, { read: 30000, W1: 120000, W2: 120000, W3: 120000, W4: 300000, W5: 120000,
    W6: 120000, W7: 120000 });
});

test('run: no shell, the buffer, and every failure is a message (never a rejection)', async () => {
  const seen = [];
  const fake = answer => (file, args, options, cb) => { seen.push({ file, args, options }); setImmediate(() => answer(cb)); };
  let res = await cli.run(['/bin/x', 'a'], { execFile: fake(cb => cb(null, '{"ok":true}\n', 'warn')) });
  assert.deepEqual(res.payload, { ok: true });
  assert.equal(seen[0].options.shell, false);
  assert.equal(seen[0].options.maxBuffer, cli.MAX_BUFFER);
  res = await cli.run(['/bin/x'], { execFile: fake(cb => cb(Object.assign(new Error('big'), { code: 'ERR_CHILD_PROCESS_STDIO_MAXBUFFER' }), '{"ok":', '')) });
  assert.equal(res.failure, cli.TOO_LARGE);
  res = await cli.run(['/bin/x'], { timeoutMs: 1000, execFile: fake(cb => cb(Object.assign(new Error('t'), { killed: true }), '', '')) });
  assert.match(res.failure, /did not answer within 1 s/);
  res = await cli.run(['/bin/x'], { execFile: fake(cb => cb(Object.assign(new Error('e'), { code: 'ENOENT' }), '', '')) });
  assert.match(res.failure, /could not be started \(ENOENT/);
  res = await cli.run(['/bin/x'], { execFile: fake(cb => cb(Object.assign(new Error('e'), { code: 2 }), 'not json', '')) });
  assert.equal(res.exitCode, 2);
  assert.match(res.failure, /did not print one JSON document/);
});
