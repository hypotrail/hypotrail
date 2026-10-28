'use strict';
// Invariant tests (scope U, frozen by WP-0): INV-1 to INV-5 and INV-13 of
// COMPANION-ADVANCED §2, as static checks of the sources and behavioural checks of the
// argv builders. A later WP that needs to break one asks the integrator first.

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const cli = require('../lib/cli');

const ROOT = path.join(__dirname, '..');
const AGENT = { argv: ['/opt/py env/bin/python', '-m', 'mlkit.study.cli'], studyDir: '/studies/my "study"' };
const UUID = '0f8fad5b-d9cb-469f-a165-70867728950e';

function walk(dir) {
  return fs.readdirSync(path.join(ROOT, dir), { withFileTypes: true }).flatMap(e =>
    (e.isDirectory() ? walk(`${dir}/${e.name}`) : e.name.endsWith('.js') ? [`${dir}/${e.name}`] : []));
}
const SOURCES = ['extension.js', ...walk('lib'), ...walk('media')];
const read = f => fs.readFileSync(path.join(ROOT, f), 'utf8');

/** One valid call of each write builder. */
const SAMPLES = {
  W4: () => cli.WRITES.W4(AGENT, { activity: 'eda.distribution', column: 'age', requestId: UUID, expectedRevision: 3 }),
  W5: () => cli.WRITES.W5(AGENT),
  W7: () => cli.WRITES.W7(AGENT, { parent: '/tmp/handoff packs', revision: 3 }),
  // ADR 0004 decision 14 (R49): the Azure ML export, outside the study state.
  W8: () => cli.WRITES.W8(AGENT, { parent: '/tmp/azure exports', revision: 3 }),
};

test('INV-1: only lib/cli.js requires child_process, and nothing reads .hypotrail/*.json', () => {
  for (const f of SOURCES) {
    const text = read(f);
    if (f === 'lib/cli.js') assert.match(text, /require\('child_process'\)/);
    else assert.doesNotMatch(text, /child_process/, f);
    // lib/watch.js names the files whose change marks a new revision; it reads none of them.
    if (f !== 'lib/watch.js') assert.doesNotMatch(text, /state\.json|revisions\.jsonl|registry-index|exposure\.jsonl/, `${f} names engine state`);
  }
  // The watcher names state files but only watches the folder.
  assert.match(read('lib/watch.js'), /fsImpl\.watch\(path\.join\(studyDir, '\.hypotrail'\)/);
});

test('INV-2: no vscode.lm, network module, socket, browser storage, or workspaceState', () => {
  for (const f of SOURCES) {
    const text = read(f);
    assert.doesNotMatch(text, /vscode\.lm\b|localStorage|indexedDB|WebSocket|\bfetch\(|workspaceState|XMLHttpRequest/, f);
    assert.doesNotMatch(text, /require\(['"](node:)?(https?|net|tls|dgram|http2|ws)['"]\)/, f);
  }
});

test('INV-3, INV-13: exactly four write builders W4, W5, W7, W8 (W1-W3 withdrawn, v0.3; W6 withdrawn, R31; W8 added by ADR 0004 d14), each a whitelisted argv', () => {
  assert.deepEqual(Object.keys(cli.WRITES), ['W4', 'W5', 'W7', 'W8']);
  const builders = Object.entries(cli).filter(([k, v]) => typeof v === 'function' && /Argv$/.test(k)).map(([k]) => k);
  const writes = Object.values(cli.WRITES).map(fn => fn.name);
  const reads = Object.values(cli.READS).map(fn => fn.name);
  assert.deepEqual(builders.sort(), [...writes, ...reads].sort(), 'every argv builder is a listed read or write');
  assert.equal(new Set(writes).size, 4);
  assert.deepEqual(Object.keys(cli.READS), ['summary', 'decisions', 'effects', 'evidence', 'preview', 'draft', 'check',
    'explain', 'session_report', 'view', 'data', 'azureml_plan']);
  // The Azure ML plan is a read: `--plan` writes nothing; W8 never carries it.
  assert.ok(cli.READS.azureml_plan(AGENT, { revision: 3 }).includes('--plan'));
  assert.ok(!SAMPLES.W8().includes('--plan'));
  for (const [w, sample] of Object.entries(SAMPLES)) {
    const tail = sample().slice(AGENT.argv.length);
    const verbs = tail.slice(0, 2).join(' ');
    // v0.3 (WP-J, R35): every write that the engine records names the panel as its channel;
    // W8 records nothing in the study (no state, event or channel record), so it has none.
    assert.equal(tail.filter(a => a === '--channel=webview').length, w === 'W8' ? 0 : 1, `${w} names its channel once`);
    assert.ok(['run eda.distribution', 'render --channel=webview', 'export handoff', 'export azureml'].includes(verbs),
      `${w}: ${verbs}`);
    // ADR 0004 amendment (R23, I2): no write of the panel is a `decide` command; R31: none
    // acknowledges an interruption, and none passes the junior's words.
    assert.notEqual(tail[0], 'decide', w);
    assert.ok(!tail.includes('--acknowledge-interruption') && !tail.some(a => a.startsWith('--user-words')), w);
    if (w === 'W5') {
      assert.ok(!tail.includes('--request-id') && !tail.includes('--expected-revision'), `${w} has no revision`);
    } else if (w === 'W7' || w === 'W8') {
      // CR.6: the export names the revision the junior saw; it writes no study state, so
      // it carries no request id.
      assert.ok(!tail.includes('--request-id'), 'W7 has no request id');
      const folder = tail.find(a => a.startsWith('--out=')).match(/revision-([0-9]+)$/)[1];
      assert.ok(tail.includes('--expected-revision'), w);
      assert.equal(tail[tail.indexOf('--expected-revision') + 1], folder, 'the folder and the option name one revision');
    } else {
      assert.equal(tail[tail.indexOf('--request-id') + 1], UUID, w);
      assert.equal(tail[tail.indexOf('--expected-revision') + 1], '3', w);
    }
    assert.deepEqual(tail.slice(-3), ['--json', '--study', AGENT.studyDir], w);
  }
});

test('INV-4, INV-13: no builder emits a delegation, a note, a fit, a split, or an evaluation', () => {
  const forbidden = /^(--basis|--delegation-scope|note|split|policy\.evaluate|evaluate\.regression|init|--max-groups|--text)$|^fit\.|^--basis=|^--delegation-scope=/;
  for (const [w, sample] of Object.entries(SAMPLES)) {
    for (const token of sample().slice(AGENT.argv.length)) {
      if (token.startsWith('--value=') || token.startsWith('--restatement=') || token.startsWith('--rationale=') ||
          token.startsWith('--user-words=') || token.startsWith('--out=') || token.startsWith('--column=')) continue;
      assert.doesNotMatch(token, forbidden, `${w} emits ${token}`);
    }
  }
  const bad = [
    () => cli.WRITES.W4(AGENT, { activity: 'fit.logistic', column: 'age', requestId: UUID, expectedRevision: 3 }),
    () => cli.WRITES.W4(AGENT, { activity: 'split', column: 'age', requestId: UUID, expectedRevision: 3 }),
    () => cli.WRITES.W4(AGENT, { activity: 'policy.evaluate', column: 'x', requestId: UUID, expectedRevision: 3 }),
    () => cli.WRITES.W4(AGENT, { activity: 'eda.distribution', column: 'age\0--basis', requestId: UUID, expectedRevision: 3 }),
    () => cli.WRITES.W4(AGENT, { activity: 'eda.distribution', column: 'age', requestId: 'not-a-uuid', expectedRevision: 3 }),
    () => cli.WRITES.W7(AGENT, { parent: path.join(AGENT.studyDir, '.hypotrail'), revision: 3 }),
    () => cli.WRITES.W8(AGENT, { parent: path.join(AGENT.studyDir, '.hypotrail'), revision: 3 }),
  ];
  for (const fn of bad) assert.throws(fn, cli.ArgvError);
});

test('INV-5: only media/core.js creates the words textarea, and nothing sets a words value', () => {
  for (const f of walk('media')) {
    const text = read(f);
    if (f === 'media/core.js') continue;
    assert.doesNotMatch(text, /['"]textarea['"]/, `${f} creates a textarea: use Hypotrail.wordsArea`);
    assert.doesNotMatch(text, /(area|words|textarea)\w*\.value\s*=(?!=)/i, `${f} sets the value of a words field`);
    assert.doesNotMatch(text, /acquireVsCodeApi/, `${f} acquires the VS Code API`);
  }
  const core = read('media/core.js');
  assert.equal((core.match(/el\('textarea'/g) || []).length, 1, 'one textarea factory');
  assert.equal((core.match(/\.value = /g) || []).length, 1, 'one value assignment: the own draft');
  // R31: the only words field is the "Ask the agent" question; no acknowledgement draft.
  assert.match(core, /area\.value = String\(ui\.askDraft \|\| ''\);/);
  assert.doesNotMatch(core, /ackDrafts'\]|kind: 'ackDrafts'|drafts\.get\(/);
});

test('INV-9: no innerHTML, outerHTML, insertAdjacentHTML, document.write, eval, or Function in media', () => {
  for (const f of walk('media')) {
    assert.doesNotMatch(read(f), /\.innerHTML\s*=|outerHTML\s*=|insertAdjacentHTML|document\.write|\beval\(|new Function\(|setAttribute\(['"]style/, f);
  }
});

test('§12 clipboard: only the agent bridge writes it (lib/bridge.js through the host); the webview never does (CI.5)', () => {
  for (const f of SOURCES) {
    const text = read(f);
    assert.doesNotMatch(text, /navigator\.clipboard|execCommand\(\s*['"]copy/, f);
    if (/writeClipboard\(|clipboard\.writeText\(/.test(text)) assert.ok(['extension.js', 'lib/bridge.js'].includes(f), f);
  }
});

test('INV-15: no source reads precomputed tutorial outputs (use-cases/*/results.json, project.json)', () => {
  for (const f of SOURCES) {
    const text = read(f);
    assert.doesNotMatch(text, /results\.json|project\.json|tutorial-results|use-cases/, f);
  }
});
