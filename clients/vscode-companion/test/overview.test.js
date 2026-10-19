'use strict';
// Overview tests (scope U, WP-U1; COMPANION-ADVANCED §6.1, §3.3 reviewer, §7 W5 and W6):
// the SummaryModel extensions, the CheckModel, and the Overview handler (`load: check`,
// `render`, `acknowledge`, `switch_study`) through the real controller with the fixture
// CLI (test/fixture-cli.js). No process is started. Requirement ids are in the test names.

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const { createController } = require('../lib/controller');
const { toSummaryModel } = require('../lib/models/summary');
const { toCheckModel, deliverableOf } = require('../lib/models/check');
const { ModelError } = require('../lib/models/common');
const overview = require('../lib/handlers/overview');
const { fakeCli, payload } = require('./fixture-cli');

const AGENT = { argv: ['/opt/py/bin/python', '-m', 'mlkit.study.cli'], studyDir: '/studies/bank marketing "demo"' };
const UUID = '0f8fad5b-d9cb-469f-a165-70867728950e';
const ROOT = path.join(__dirname, '..');
const FORBIDDEN = /\b(threshold|capacity|precision|recall|positive class|policy|calling rule|decision rule|selected)\b/i;
const MOMENT_TITLES = ['Frame the change', 'Prepare evidence', 'Work and compare', 'Conclude and hand over'];
const INTERRUPTED = 'e_4c1d9a7b2e3f5a6b7c8d9e0f';
const SUSPECTED = 'e_8e7d6c5b4a39281706f5e4d3';
const LATE = 'e_1f2e3d4c5b6a79880a1b2c3d';

function make({ settings = { stage: 'v1' }, route, host = {}, task = 'binary' } = {}) {
  const posted = [];
  const runCli = fakeCli(route, { agentArgv: AGENT.argv, task });
  const c = createController({ agent: AGENT, post: m => posted.push(m), runCli, settings, host,
    exists: () => true, uuid: () => UUID });
  const tails = () => runCli.calls.map(x => x.tail);
  return { c, posted, runCli, tails, last: type => posted.filter(m => m.type === type).at(-1) };
}

const health = route => tail => (tail[0] === 'status' ? 'summary.binary.health' : route ? route(tail) : undefined);

// --- SummaryModel (§6.1.1 to §6.1.4) ---------------------------------------------------------

test('OV-1: the recap lines are summary.recap, byte for byte', () => {
  for (const name of ['summary.binary', 'summary.regression', 'summary.binary.health']) {
    const p = payload(name);
    const m = toSummaryModel(p);
    assert.deepEqual(m.recap, p.recap, name);
    assert.equal(m.recap.length, 5);
    assert.deepEqual(m.recap.map(l => l.slice(0, l.indexOf(':'))), ['Goal', 'Decided', 'Now', 'Next', 'Limit']);
  }
});

test('OV-2: an empty recap gives an empty list (the view says "No recap yet.")', () => {
  const m = toSummaryModel({ ...payload('summary.binary'), recap: [] });
  assert.deepEqual(m.recap, []);
  const view = fs.readFileSync(path.join(ROOT, 'media', 'copy', 'overview.js'), 'utf8');
  assert.match(view, /noRecap: 'No recap yet\.'/);
});

test('OV-3: four moments with the CC §1.1 titles; every plan step in exactly one of them', () => {
  for (const name of ['summary.binary', 'summary.regression']) {
    const m = toSummaryModel(payload(name));
    assert.deepEqual(m.moments.map(x => x.title), MOMENT_TITLES, name);
    const listed = m.moments.flatMap(x => x.steps);
    assert.deepEqual([...listed].sort(), m.plan.map(s => s.id).sort(), name);
    assert.equal(new Set(listed).size, listed.length, `${name}: once each`);
    assert.ok(m.currentStep && listed.includes(m.currentStep.id));
  }
});

test('OV-3, OV-4: plan items carry the pause, the basis, the decision status, and what a blocked step waits for', () => {
  const m = toSummaryModel(payload('summary.binary'));
  const policy = m.plan.find(s => s.id === 'policy');
  assert.deepEqual({ pause: policy.pause, basis: policy.basis, decisionStatus: policy.decisionStatus },
    { pause: 3, basis: 'explicit', decisionStatus: 'confirmed' });
  assert.equal(m.plan.find(s => s.id === 'train_eda').pause, null, 'not a decision');
  const p = payload('summary.binary');
  const blocked = { ...p, plan: p.plan.map(s => (s.id === 'policy' ? { ...s, status: 'awaiting_confirmation' }
    : s.id === 'conclusion' ? { ...s, status: 'blocked' } : s)) };
  assert.deepEqual(toSummaryModel(blocked).plan.find(s => s.id === 'conclusion').after,
    { id: 'policy', title: 'Choose a decision policy' }, 'the first earlier step that is not done');
  const viaNext = { ...blocked, next_action: { kind: 'blocked', step: 'conclusion', requires: ['models'], message: '' },
    plan: blocked.plan.map(s => (s.id === 'models' ? { ...s, status: 'ready' } : s)) };
  assert.equal(toSummaryModel(viaNext).plan.find(s => s.id === 'conclusion').after.id, 'models');
  assert.ok(toSummaryModel(p).plan.every(s => s.after === null), 'no blocked step');
  assert.ok(toSummaryModel(p).plan.every(s => !('requires' in s)));
});

test('OV-5: the Bank digest after a capacity change: re-evaluation with kept fits, reconfirmation, resolved hold', () => {
  const p = payload('summary.binary');
  const d = toSummaryModel(p).digest;
  assert.deepEqual(d.items.map(i => i.text), p.digest.items.map(i => i.text), 'verbatim, oldest first');
  assert.equal(d.since, 23);
  assert.equal(d.boundary, 23);
  assert.equal(d.sinceTime, p.last_session.boundary_time);
  assert.equal(d.gapMinutes, 1395);
  const replaced = d.items.find(i => i.kind === 'result_replaced');
  assert.deepEqual(replaced.refit, []);
  assert.deepEqual(replaced.keptFits, ['fit.baseline', 'fit.logistic']);
  assert.match(replaced.text, /re-?evaluat|evaluation was replaced/);
  assert.ok(d.items.some(i => /needs confirmation again/.test(i.text)), 'the reconfirmation sentence');
  const hold = d.items.find(i => i.kind === 'hold_resolved');
  assert.match(hold.text, /"my manager says the team can make 100 calls per wave"/);
  assert.equal(d.items.find(i => i.kind === 'hold_resolved').refit, null, 'no invalidation: refit is null');
  const r = toSummaryModel(payload('summary.regression')).digest;
  assert.equal(r.truncated, true);
  assert.equal(r.gapMinutes, null, 'one session: "This session"');
});

test('OV-6: digest texts hold no revision number', () => {
  for (const name of ['summary.binary', 'summary.regression', 'summary.binary.health']) {
    for (const item of toSummaryModel(payload(name)).digest.items) assert.doesNotMatch(item.text, /revision \d/i, name);
  }
});

test('OV-7: deliverable messages verbatim, in the order report, notebook, workbench; Regenerate only when needed', () => {
  const p = payload('summary.binary');
  const m = toSummaryModel(p);
  assert.deepEqual(m.artifacts.map(a => a.name), ['report', 'notebook', 'workbench']);
  for (const a of m.artifacts) assert.equal(a.message, p.artifacts.items[a.name].message);
  assert.equal(m.regenerate, false, 'everything is up to date');
  assert.equal(toSummaryModel(payload('summary.binary.health')).regenerate, true, 'the report is stale');
  const failed = { ...p, artifacts: { status: 'failed', items: { ...p.artifacts.items,
    notebook: { ...p.artifacts.items.notebook, status: 'failed', message: 'could not be regenerated' } } } };
  assert.equal(toSummaryModel(failed).regenerate, true, 'a failed notebook');
  assert.equal(toSummaryModel({ ...p, artifacts: { status: 'not_rendered', items: {} } }).regenerate, true, 'not rendered');
  const workbench = { ...p, artifacts: { status: 'ok', items: { ...p.artifacts.items,
    workbench: { ...p.artifacts.items.workbench, status: 'stale' } } } };
  assert.equal(toSummaryModel(workbench).regenerate, false, 'the workbench is not generated');
  assert.equal(toSummaryModel({ ...p, artifacts: null }).regenerate, false);
});

// --- CheckModel (§6.1.5) ---------------------------------------------------------------------

test('HE-3: check findings carry severity, code, message verbatim, where, and an openable deliverable', () => {
  const p = payload('check.binary');
  const m = toCheckModel(p);
  assert.equal(m.clean, false);
  assert.deepEqual(m.counts, { error: 1, warning: 1 });
  const stale = m.findings.find(f => f.code === 'stale_number');
  assert.equal(stale.severity, 'error');
  assert.equal(stale.message, p.findings[0].message);
  assert.equal(stale.where, 'reports/study.html');
  assert.equal(stale.deliverable, 'report');
  assert.equal(stale.resultId, p.findings[0].details.result_id);
  const causal = m.findings.find(f => f.code === 'causal_wording');
  assert.equal(causal.deliverable, 'workbench');
  assert.equal(causal.location.line, 42);
  assert.equal(causal.resultId, null);
  assert.deepEqual(toCheckModel(payload('check.binary.clean')), { revision: 26, clean: true, counts: { error: 0, warning: 0 }, findings: [] });
  assert.throws(() => toCheckModel(payload('summary.binary')), ModelError);
});

test('HE-3, §12: "Open" only for a location that is one of the three deliverables inside the study', () => {
  assert.equal(deliverableOf('reports/study.html'), 'report');
  assert.equal(deliverableOf('notebooks/study_generated.py'), 'notebook');
  assert.equal(deliverableOf('./notebooks/workbench.py'), 'workbench');
  for (const bad of ['../reports/study.html', '/etc/passwd', '/studies/x/reports/study.html', 'C:\\x\\study.html',
    'reports/other.html', '.hypotrail/agent.json', '', null, 'reports/study.html\0x']) {
    assert.equal(deliverableOf(bad), null, String(bad));
  }
  const odd = toCheckModel({ ...payload('check.binary'), findings: [{ code: 'x', severity: 'error', where: 'w', message: 'm',
    location: { path: '../../outside.html', anchor: 'r-' + 'a'.repeat(64), line: 0 } }, { code: 'y', severity: 'warning' }] });
  assert.equal(odd.findings[0].deliverable, null);
  assert.equal(odd.findings[0].resultId, null);
  assert.equal(odd.findings[0].location.line, null);
  assert.equal(odd.findings[1].location, null);
});

// --- handler: load check ------------------------------------------------------------------------

test('HE-3: load check runs `check --json --study S` once per revision and posts the CheckModel', async () => {
  const { c, posted, tails, last } = make();
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'load', view: 'check' });
  await c.handle({ v: 2, type: 'load', view: 'check' });
  const checks = tails().filter(t => t[0] === 'check');
  assert.deepEqual(checks, [['check', '--json', '--study', AGENT.studyDir]], 'cached per revision');
  const data = posted.filter(m => m.type === 'view_data' && m.view === 'check');
  assert.equal(data.length, 2);
  assert.equal(data[0].revision, 26);
  assert.equal(data[0].model.findings[0].code, 'stale_number');
  // At v0, a check load is ignored (stage gate).
  const v0 = make({ settings: { stage: 'v0' } });
  await v0.c.handle({ v: 2, type: 'load', view: 'check' });
  assert.equal(v0.runCli.calls.length, 0);
  assert.equal(c.diagnostics().dropped, 0, JSON.stringify(c.diagnostics().invalid));
  assert.equal(last('load_error'), undefined);
});

test('HE-3: a check that fails is a load_error for the check view, not the summary', async () => {
  const { c, last } = make({ route: tail => (tail[0] === 'check' ? { failure: 'The hypotrail CLI did not print one JSON document.' } : undefined) });
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'load', view: 'check' });
  assert.deepEqual(last('load_error'), { v: 2, type: 'load_error', view: 'check',
    message: 'The hypotrail CLI did not print one JSON document.', detail: '' });
});

// --- handler: render (W5) ---------------------------------------------------------------------

test('OV-8: Regenerate runs exactly `render --json --study S` and lists each artefact message', async () => {
  const { c, posted, tails, last } = make({ route: health() });
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'render' });
  const render = tails().find(t => t[0] === 'render');
  assert.deepEqual(render, ['render', '--json', '--study', AGENT.studyDir]);
  const o = last('outcome');
  assert.equal(o.op, 'W5');
  assert.equal(o.kind, 'ok');
  assert.equal(o.target, overview.RENDER_TARGET);
  assert.deepEqual(o.artifacts.map(a => a.message), Object.values(payload('render.binary').artifacts).map(a => a.message));
  const busy = posted.filter(m => m.type === 'busy');
  assert.deepEqual(busy.map(b => [b.busy, b.op, b.target]), [[true, 'W5', 'render'], [false, 'W5', 'render']]);
  assert.equal(tails().at(-1)[0], 'status', 'refreshed after the write');
});

test('OV-8: exit 3 is "ok with problems", with the messages verbatim, not a failure', async () => {
  const { c, last } = make({ route: health(tail => (tail[0] === 'render' ? 'render.binary.problems' : undefined)) });
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'render' });
  const o = last('outcome');
  assert.equal(o.kind, 'ok_with_problems');
  assert.equal(o.exitCode, 3);
  assert.equal(o.artifacts.find(a => a.name === 'notebook').message,
    payload('render.binary.problems').artifacts.notebook.message);
  const copy = fs.readFileSync(path.join(ROOT, 'media', 'copy', 'overview.js'), 'utf8');
  assert.match(copy, /regeneratedProblems: 'Regenerated with problems'/);
});

// --- handler: acknowledge (W6) ----------------------------------------------------------------

test('HE-1: an acknowledgement typed in the panel runs the exact argv of W6 and records the words', async () => {
  const words = 'I know the policy run was cut off and nobody knows what it did.';
  const { c, tails, last } = make({ route: health() });
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'acknowledge', executionId: INTERRUPTED, words, revision: 26 });
  const run = tails().find(t => t[0] === 'run');
  assert.deepEqual(run, ['run', '--acknowledge-interruption', INTERRUPTED, `--user-words=${words}`,
    '--request-id', UUID, '--expected-revision', '26', '--json', '--study', AGENT.studyDir]);
  const o = last('outcome');
  assert.equal(o.op, 'W6');
  assert.equal(o.kind, 'ok');
  assert.equal(o.target, INTERRUPTED);
  assert.equal(o.recorded.userWords, words);
  assert.equal(o.recorded.status, 'acknowledged');
});

test('HE-1: the suspected execution can be acknowledged too; a late one cannot', async () => {
  const { c, tails, last } = make({ route: health() });
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'acknowledge', executionId: SUSPECTED, words: 'I know it stopped; its outcome is unknown.', revision: 26 });
  assert.equal(tails().filter(t => t[0] === 'run').length, 1);
  await c.handle({ v: 2, type: 'acknowledge', executionId: LATE, words: 'I know.', revision: 26 });
  assert.equal(tails().filter(t => t[0] === 'run').length, 1, 'nothing ran');
  assert.equal(last('outcome').kind, 'invalid');
  assert.match(last('outcome').message, /not waiting for an acknowledgement.*Nothing was recorded\./);
});

test('HE-1: a bare "ok" is refused by the engine and shown verbatim; the panel never pre-refuses it', async () => {
  const refusal = payload('error.bare_acknowledgement');
  const { c, tails, last } = make({ route: health(tail => (tail[0] === 'run' ? 'error.bare_acknowledgement' : undefined)) });
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'acknowledge', executionId: INTERRUPTED, words: 'ok', revision: 26 });
  assert.ok(tails().some(t => t[0] === 'run' && t.includes('--user-words=ok')), 'sent as typed');
  const o = last('outcome');
  assert.equal(o.kind, 'refused');
  assert.equal(o.refusal.code, 'ambiguous_confirmation');
  assert.equal(o.refusal.reason, 'bare_acknowledgement');
  assert.equal(o.refusal.engineMessage, refusal.error.message);
  assert.match(o.refusal.human, /Nothing was recorded\.$/);
  assert.doesNotMatch(o.refusal.human, /type|write ["“']/i, 'never suggests words');
  assert.equal(tails().at(-1)[0], 'status', 'refreshed after the refusal');
});

test('HE-1, INV-5: blank or unknown acknowledgements are invalid and run nothing', async () => {
  const { c, runCli, last } = make({ route: health() });
  await c.handle({ v: 2, type: 'ready' });
  const before = runCli.calls.length;
  await c.handle({ v: 2, type: 'acknowledge', executionId: INTERRUPTED, words: '   \n', revision: 26 });
  assert.equal(last('outcome').kind, 'invalid');
  assert.match(last('outcome').message, /Type your own reply first\. Nothing was recorded\./);
  assert.equal(runCli.calls.length, before);
  await c.handle({ v: 2, type: 'acknowledge', executionId: 'e_unknown', words: 'I know.', revision: 26 });
  assert.equal(last('outcome').kind, 'invalid');
  assert.ok(!runCli.calls.some(x => x.tail[0] === 'run'));
  await c.handle({ v: 2, type: 'acknowledge', executionId: 'e 1; rm', words: 'I know.', revision: 26 });
  assert.equal(c.diagnostics().ignored, 1, 'a malformed id never reaches the handler');
});

test('HE-2: no write of the Overview restarts or runs an activity', () => {
  const src = fs.readFileSync(path.join(ROOT, 'lib', 'handlers', 'overview.js'), 'utf8');
  assert.doesNotMatch(src, /runEdaArgv|proposeArgv|W4|W3/);
  const view = fs.readFileSync(path.join(ROOT, 'media', 'views', 'overview.js'), 'utf8') +
    fs.readFileSync(path.join(ROOT, 'media', 'copy', 'overview.js'), 'utf8');
  assert.doesNotMatch(view, /'(Restart|Run|Rerun)\b[^']*'/);
  assert.doesNotMatch(view, /type: 'run_eda'|type: 'propose'/);
  assert.deepEqual(Object.keys(overview.types).sort(), ['acknowledge', 'open_artifact', 'open_marimo', 'render', 'switch_study']);
});

// --- reviewer (RV-2) -------------------------------------------------------------------------

test('RV-2: reviewer mode refuses every write type with "Read-only reviewer mode." and runs nothing', async () => {
  const { c, runCli, posted } = make({ settings: { stage: 'v3', reviewer: true }, route: health() });
  await c.handle({ v: 2, type: 'ready' });
  const before = runCli.calls.length;
  const writes = [
    [{ type: 'confirm', proposalId: 'p_5', words: 'Yes, call the top 100.', revision: 26 }, 'W1'],
    [{ type: 'withdraw', proposalId: 'p_5', revision: 26 }, 'W2'],
    [{ type: 'propose', decisionId: 'policy', value: 'capacity:100', revision: 26 }, 'W3'],
    [{ type: 'run_eda', activity: 'eda.distribution', column: 'age', revision: 26 }, 'W4'],
    [{ type: 'render' }, 'W5'],
    [{ type: 'acknowledge', executionId: INTERRUPTED, words: 'I know it stopped.', revision: 26 }, 'W6'],
  ];
  for (const [m, op] of writes) {
    await c.handle({ v: 2, ...m });
    const o = posted.filter(x => x.type === 'outcome').at(-1);
    assert.deepEqual([o.op, o.kind, o.message], [op, 'invalid', 'Read-only reviewer mode.'], op);
  }
  assert.equal(runCli.calls.length, before, 'no process for a refused write');
  // Reads stay: the check and opening a deliverable.
  await c.handle({ v: 2, type: 'load', view: 'check' });
  assert.ok(runCli.calls.some(x => x.tail[0] === 'check'));
});

// --- switch_study (ST) -----------------------------------------------------------------------

test('ST-1: switch_study asks the extension for its study switch', async () => {
  let switched = 0;
  const { c } = make({ host: { switchStudy: async () => { switched += 1; } } });
  await c.handle({ v: 2, type: 'switch_study' });
  assert.equal(switched, 1);
  const v0 = make({ settings: { stage: 'v0' }, host: { switchStudy: async () => { switched += 1; } } });
  await v0.c.handle({ v: 2, type: 'switch_study' });
  assert.equal(switched, 1, 'a v1 message is ignored at v0');
});

test('open_artifact: a missing deliverable is a notice; an existing one opens (the report at a fragment)', async () => {
  const opened = [];
  const posted = [];
  const c = createController({ agent: AGENT, post: m => posted.push(m), runCli: fakeCli(undefined, { agentArgv: AGENT.argv }),
    settings: { stage: 'v2' }, exists: target => !target.endsWith('workbench.py'),
    openArtifact: async (name, target, options) => opened.push([name, target, options]), uuid: () => UUID });
  await c.handle({ v: 2, type: 'open_artifact', artifact: 'workbench' });
  assert.deepEqual(posted.at(-1), { v: 2, type: 'notice', politeness: 'assertive', text: 'notebooks/workbench.py does not exist yet.' });
  const rid = 'b'.repeat(64);
  await c.handle({ v: 2, type: 'open_artifact', artifact: 'report', resultId: rid });
  assert.deepEqual(opened, [['report', path.join(AGENT.studyDir, 'reports/study.html'), { fragment: `r-${rid}` }]]);
});

test('open_artifact (WP-I): a finding\'s line opens an editor there; a result opens the notebook at the line naming it', async () => {
  const fs = require('fs');
  const os = require('os');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ht open "nb" '));
  fs.mkdirSync(path.join(dir, 'notebooks'));
  const rid = 'c'.repeat(8) + 'd'.repeat(56);
  fs.writeFileSync(path.join(dir, 'notebooks/study_generated.py'), `import marimo\n\n# result ${rid.slice(0, 8)}\nx = 1\n`);
  const opened = [];
  const posted = [];
  const agent = { ...AGENT, studyDir: dir };
  const c = createController({ agent, post: m => posted.push(m), runCli: fakeCli(undefined, { agentArgv: AGENT.argv }),
    settings: { stage: 'v1' }, openArtifact: async (name, target, options) => opened.push([name, target, options]), uuid: () => UUID });
  const notebook = path.join(dir, 'notebooks/study_generated.py');
  await c.handle({ v: 2, type: 'open_artifact', artifact: 'notebook', line: 4 });
  await c.handle({ v: 2, type: 'open_artifact', artifact: 'notebook', resultId: rid });
  await c.handle({ v: 2, type: 'open_artifact', artifact: 'notebook', resultId: 'e'.repeat(64) });
  assert.deepEqual(opened, [['notebook', notebook, { line: 4 }], ['notebook', notebook, { line: 3 }], ['notebook', notebook, {}]]);
  assert.match(posted.at(-1).text, /does not name this result; it opens at the top/);
  fs.rmSync(dir, { recursive: true, force: true });
});

// --- copy (INV-12, §15) ----------------------------------------------------------------------

test('copy: English strings without digits, decision-rule vocabulary, or suggested words', () => {
  const file = path.join(ROOT, 'media', 'copy', 'overview.js');
  const saved = globalThis.Hypotrail;
  globalThis.Hypotrail = { copy: {} };
  try {
    delete require.cache[require.resolve(file)];
    require(file);
    const copy = globalThis.Hypotrail.copy.overview;
    const strings = [];
    const walk = v => {
      if (typeof v === 'string') strings.push(v);
      else if (typeof v === 'function') strings.push(String(v('Xa', 'Xb', 'Xc')));
      else if (v && typeof v === 'object') Object.values(v).forEach(walk);
    };
    walk(copy);
    assert.ok(strings.length > 40);
    for (const s of strings) {
      assert.doesNotMatch(s, FORBIDDEN, s);
      assert.doesNotMatch(s, /!/, s);
      assert.doesNotMatch(s, /\d/, `no digit outside placeholders: ${s}`);
    }
    assert.match(copy.replyHint, /'ok' alone is not enough\.$/);
  } finally {
    globalThis.Hypotrail = saved;
  }
});
