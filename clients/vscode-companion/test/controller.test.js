'use strict';
// Controller tests (scope U, WP-0): the router of lib/controller.js with the fixture CLI
// (test/fixture-cli.js): stage gate, reviewer refusal, `load` dispatch, cache and
// coalescing, the read limits and the write lock, the outcome mapping of §7, the handler
// registry, settings, and the flag helpers. No process is started.

const test = require('node:test');
const assert = require('node:assert/strict');
const { createController, registry } = require('../lib/controller');
const flag = require('../lib/flag');
const { createCache } = require('../lib/cache');
const { createFake } = require('./fake-vscode');
const { fakeCli } = require('./fixture-cli');
const { studyKey } = require('../lib/localstore');

const AGENT = { argv: ['/opt/py/bin/python', '-m', 'mlkit.study.cli'], studyDir: '/studies/bank marketing "demo"' };

function make({ settings = {}, route, handlers, host = {} } = {}) {
  const posted = [];
  const runCli = fakeCli(route, { agentArgv: AGENT.argv });
  const c = createController({ agent: AGENT, post: m => posted.push(m), runCli, settings, host,
    exists: () => true, uuid: () => '0f8fad5b-d9cb-469f-a165-70867728950e', ...(handlers ? { handlers } : {}) });
  return { c, posted, runCli, last: type => posted.filter(m => m.type === type).at(-1) };
}

// ADR 0004 d13 (§5): the one page reads the summary with --digest at every stage (its P1 keys).
test('ready: init, then the summary; every stage reads with --digest', async () => {
  for (const [stage, digest, revision] of [['v0', true, 26], ['v1', true, 26]]) {
    const { c, posted, runCli } = make({ settings: { stage } });
    await c.handle({ v: 2, type: 'ready' });
    assert.equal(posted[0].type, 'init');
    assert.deepEqual(posted[0], { v: 2, type: 'init', stage, reviewer: false, learningLayer: true, chatInsert: false, task: null,
      study: studyKey(AGENT.studyDir),
      // WP-A5: what "Open in Marimo" runs, for display (lib/launch.js display).
      marimo: { kernel: '/opt/py/bin/python', notebook: '/opt/py/bin/python -m marimo run notebooks/study_generated.py',
        editable: '/opt/py/bin/python -m marimo edit notebooks/study_editable.py',
        workbench: '/opt/py/bin/python -m marimo edit notebooks/workbench.py' },
      // v0.3 (WP-E2, R21): the panel language setting, `auto` by default.
      language: 'auto',
      // ADR 0004 d13 (CLI-CONTRACT §17.1.5): the contract the panel speaks.
      panelContract: 2,
      // Lot P (R51): the surface this document draws (the one page; the What if? tab is `whatif`).
      surface: 'panel' });
    assert.equal(runCli.calls[0].tail.includes('--digest'), digest);
    const snap = posted.find(m => m.type === 'snapshot');
    assert.equal(snap.revision, revision);
    assert.equal(snap.model.task, 'binary');
    assert.equal(posted.filter(m => m.type === 'init').at(-1).task, 'binary', 'init again once the task is known');
    assert.equal(c.diagnostics().dropped, 0, JSON.stringify(c.diagnostics().invalid));
  }
});

test('session log: every read runs with HYPOTRAIL_SESSION_LOG=0, every write inherits the environment (CLI-CONTRACT §8.6)', async () => {
  const { c, runCli } = make({ settings: { stage: 'v3' } });
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'load', view: 'check' });
  await c.handle({ v: 2, type: 'render' });
  const reads = runCli.calls.filter(x => x.tail[0] !== 'render');
  const writes = runCli.calls.filter(x => x.tail[0] === 'render');
  assert.ok(reads.some(x => x.tail[0] === 'status') && reads.some(x => x.tail[0] === 'check'));
  for (const call of reads) {
    assert.equal(call.options.env.HYPOTRAIL_SESSION_LOG, '0', call.tail.join(' '));
    assert.equal(call.options.env.PATH, process.env.PATH, 'merged over the host environment');
  }
  assert.equal(writes.length, 1);
  assert.equal(writes[0].options.env, undefined, 'a write is logged like the chat\'s');
});

test('stage gate: a message above the active stage is ignored like an invalid one', async () => {
  const { c, posted, runCli } = make({ settings: { stage: 'v0' } });
  for (const m of [{ type: 'render' }, { type: 'load', view: 'decisions' }, { type: 'preview_effects', proposalId: 'p_5', revision: 26 },
    { type: 'preview_policy', rules: ['capacity:100'], intervals: false, seq: 1 }, { type: 'export_handoff', revision: 26 },
    { type: 'open_artifact', artifact: 'report', resultId: 'a'.repeat(64) }]) {
    await c.handle({ v: 2, ...m });
  }
  assert.equal(c.diagnostics().ignored, 6);
  assert.equal(posted.length, 0);
  assert.equal(runCli.calls.length, 0);
});

test('reviewer: every write of the study is refused as invalid, nothing runs; the export may run (CA.9)', async () => {
  const { c, posted, runCli } = make({ settings: { stage: 'v3', reviewer: true } });
  await c.handle({ v: 2, type: 'ready' });
  const before = runCli.calls.length;
  for (const m of [{ type: 'confirm', proposalId: 'p_5', words: 'Yes, call the top 100.', revision: 26 },
    { type: 'withdraw', proposalId: 'p_5', revision: 26 }, { type: 'propose', decisionId: 'policy', value: 'capacity:100', revision: 26 },
    { type: 'run_eda', activity: 'eda.distribution', column: 'age', revision: 26 }, { type: 'render' },
    { type: 'acknowledge', executionId: 'e_1', words: 'I know.', revision: 26 }]) {
    await c.handle({ v: 2, ...m });
  }
  const outcomes = posted.filter(m => m.type === 'outcome');
  // v0.3 narrowing: confirm, withdraw and propose are no message types any more; neither is
  // acknowledge since R31 (2026-10-27). They are dropped unanswered, whatever the mode.
  assert.deepEqual(outcomes.map(o => o.op), ['W4', 'W5']);
  assert.equal(c.diagnostics().ignored, 4);
  assert.ok(outcomes.every(o => o.kind === 'invalid' && o.message === 'Read-only reviewer mode.'));
  assert.equal(runCli.calls.length, before);
  // ctx.write refuses too, whatever the caller.
  assert.equal(await c.context.write('W5', { argv: () => assert.fail('no argv') }), null);
  // W7 is allowed: the controller runs it (here against the fixture CLI).
  const exported = await c.context.write('W7', { argv: () => c.context.cli.exportArgv(c.context.agent, { parent: '/tmp/packs', revision: 26 }) });
  assert.equal(exported.kind, 'ok');
});

test('load: a view without a loader answers "Not available in this stage."; a loader is cached per revision', async () => {
  const seen = [];
  const handlers = [{ name: 'probe', loads: { decisions: { stage: 'v1', key: () => 'decisions',
    argv: (cli, agent) => cli.decisionsArgv(agent), model: p => { seen.push(p.revision); return { revision: p.revision, n: p.history.length }; } } } }];
  const { c, posted, runCli } = make({ settings: { stage: 'v1' }, handlers });
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'load', view: 'evidence' });
  assert.deepEqual(posted.at(-1), { v: 2, type: 'load_error', view: 'evidence', message: 'Not available in this stage.', detail: '' });
  await Promise.all([c.handle({ v: 2, type: 'load', view: 'decisions' }), c.handle({ v: 2, type: 'load', view: 'decisions' })]);
  await c.handle({ v: 2, type: 'load', view: 'decisions' });
  assert.equal(runCli.calls.filter(x => x.tail[0] === 'decisions').length, 1, 'coalesced, then cached');
  const data = posted.filter(m => m.type === 'view_data');
  assert.equal(data.length, 3);
  assert.deepEqual(data[0], { v: 2, type: 'view_data', view: 'decisions', revision: 27, currency: c.snapshot().currency,
    model: { revision: 27, n: 5 } });
  assert.match(c.snapshot().currency, /^[0-9a-f]{16}$/, 'the read carries the version it was read at (CR.1)');
  // WP-I: the cache holds the payload of the read, and each answer projects it with its
  // loader's model (shared reads, below), so the model runs once per answer, the CLI once.
  assert.deepEqual(seen, [27, 27, 27]);
});

test('load: loaders of one command share one cached payload and project it with their own models (WP-I)', async () => {
  const model = name => p => ({ view: name, revision: p.revision, n: p.history.length });
  const loader = name => ({ stage: 'v1', key: () => 'decisions-read', argv: (cli, agent) => cli.decisionsArgv(agent), model: model(name) });
  const handlers = [{ name: 'a', loads: { decisions: loader('decisions') } }, { name: 'b', loads: { eda: loader('eda') } }];
  const { c, posted, runCli } = make({ settings: { stage: 'v1' }, handlers });
  await c.handle({ v: 2, type: 'ready' });
  await Promise.all([c.handle({ v: 2, type: 'load', view: 'decisions' }), c.handle({ v: 2, type: 'load', view: 'eda' })]);
  await c.handle({ v: 2, type: 'load', view: 'eda' });
  assert.equal(runCli.calls.filter(x => x.tail[0] === 'decisions').length, 1, 'one process for both views, then the cache');
  const data = posted.filter(m => m.type === 'view_data');
  assert.deepEqual(data.map(m => m.model.view).sort(), ['decisions', 'eda', 'eda']);
  assert.ok(data.every(m => m.view === m.model.view), 'each view gets its own model');
});

test('load: a loader whose `when(settings)` is false is refused like a stage gate, and runs nothing (WP-I)', async () => {
  const handlers = [{ name: 'probe', loads: { explain: { stage: 'v1', when: s => s.learningLayer !== false, key: () => 'explain',
    argv: (cli, agent) => cli.decisionsArgv(agent), model: p => ({ revision: p.revision }) } } }];
  const { c, posted, runCli } = make({ settings: { stage: 'v3', learningLayer: false }, handlers });
  await c.handle({ v: 2, type: 'ready' });
  const before = runCli.calls.length;
  await c.handle({ v: 2, type: 'load', view: 'explain' });
  assert.deepEqual(posted.at(-1), { v: 2, type: 'load_error', view: 'explain', message: 'Not available in this stage.', detail: '' });
  assert.equal(runCli.calls.length, before);
  c.updateSettings({ learningLayer: true });
  await c.handle({ v: 2, type: 'load', view: 'explain' });
  assert.equal(posted.at(-1).type, 'view_data');
});

test('load explain with the learning layer off: the Learn handler\'s loader is refused, `explain` never runs (LE-3, WP-I)', async () => {
  const { c, posted, runCli } = make({ settings: { stage: 'v3', learningLayer: false } });
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'load', view: 'explain' });
  assert.equal(posted.at(-1).type, 'load_error');
  assert.equal(runCli.calls.filter(x => x.tail[0] === 'explain').length, 0);
});

test('load summary with since, and a refusal of a loader becomes a load_error', async () => {
  const handlers = [{ name: 'probe', loads: { evidence: { key: () => 'evidence', argv: (cli, agent) => cli.evidenceArgv(agent), model: p => p } } }];
  const { c, posted, runCli } = make({ settings: { stage: 'v2' }, handlers, route: tail => (tail[0] === 'evidence' ? 'error.not_implemented' : undefined) });
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'load', view: 'summary', since: 1 });
  assert.deepEqual(runCli.calls.at(-1).tail.slice(0, 5), ['status', '--summary', '--digest', '--since', '1']);
  assert.equal(posted.at(-1).type, 'view_data');
  assert.equal(posted.at(-1).view, 'summary');
  await c.handle({ v: 2, type: 'load', view: 'evidence' });
  assert.equal(posted.at(-1).type, 'load_error');
  assert.match(posted.at(-1).message, /^unsupported_capability: evidence is reserved/);
});

test('an engine without C1: the v1 summary falls back to the v0 read', async () => {
  const { c, posted, runCli } = make({ settings: { stage: 'v1' }, route: tail => (tail.includes('--digest') ? 'error.not_implemented' : undefined) });
  await c.handle({ v: 2, type: 'ready' });
  assert.deepEqual(runCli.calls.map(x => x.tail.includes('--digest')), [true, false]);
  assert.equal(posted.find(m => m.type === 'snapshot').model.digest, null);
});

test('write outcome mapping: ok, exit 3, not promoted, exit 4, failed, replayed', async () => {
  const cases = [
    [{ name: 'render.binary' }, 'ok', null],
    [{ name: 'render.binary.problems' }, 'ok_with_problems', null],
    [{ name: 'run.eda_distribution.binary.late' }, 'not_promoted', /computed but not used/],
    [{ name: 'error.read_only', exitCode: 4 }, 'refused', /unknown outcome/],
    [{ failure: 'The hypotrail CLI could not be started (ENOENT: x).' }, 'failed', /outcome is unknown/],
    [{ payload: { schema: 'hypotrail.render/1', ok: true, revision: 26, replayed: true, artifacts: {} } }, 'ok', /replayed, no effect/],
  ];
  for (const [answer, kind, message] of cases) {
    const { c, posted } = make({ settings: { stage: 'v1' }, route: tail => (tail[0] === 'render' ? answer : undefined) });
    await c.handle({ v: 2, type: 'ready' });
    const outcome = await c.context.write('W5', { argv: requestId => c.context.cli.renderArgv(c.context.agent) });
    assert.equal(outcome.kind, kind, JSON.stringify(outcome));
    if (message) assert.match(outcome.message, message);
    const busy = posted.filter(m => m.type === 'busy');
    assert.deepEqual(busy.map(b => b.busy), [true, false]);
    assert.equal(posted.at(-1).type, 'snapshot', 'refresh after every write');
    assert.equal(c.diagnostics().dropped, 0, JSON.stringify(c.diagnostics().invalid));
  }
});

test('the write lock: a second write is invalid while one runs; reads wait for it', async () => {
  let release;
  const gate = new Promise(r => { release = r; });
  const order = [];
  const posted = [];
  const base = fakeCli(undefined, { agentArgv: AGENT.argv });
  const runCli = async (argv, options) => {
    const tail = argv.slice(AGENT.argv.length);
    order.push(`start ${tail[0]}`);
    if (tail[0] === 'render') await gate;
    const res = await base(argv, options);
    order.push(`end ${tail[0]}`);
    return res;
  };
  const c = createController({ agent: AGENT, post: m => posted.push(m), runCli, settings: { stage: 'v1' }, handlers: [] });
  await c.handle({ v: 2, type: 'ready' });
  order.length = 0;
  const first = c.context.write('W5', { argv: () => c.context.cli.renderArgv(AGENT) });
  await new Promise(r => setImmediate(r));
  const second = await c.context.write('W5', { argv: () => c.context.cli.renderArgv(AGENT) });
  assert.equal(second, null);
  assert.equal(posted.filter(m => m.type === 'outcome').at(-1).message, 'Another request is in progress.');
  const read = c.context.read('x', c.context.cli.checkArgv(AGENT), p => p);
  await new Promise(r => setImmediate(r));
  assert.deepEqual(order, ['start render'], 'the read waits for the write');
  release();
  await first;
  await read;
  assert.equal(order[0], 'start render');
  assert.equal(order[1], 'end render');
  assert.ok(order.indexOf('start check') > order.indexOf('end render'));
});

test('read limits: at most two reads and one preview at a time', async () => {
  let active = 0, peak = 0, previews = 0, previewPeak = 0;
  const base = fakeCli(undefined, { agentArgv: AGENT.argv });
  const runCli = async (argv, options) => {
    const preview = argv.includes('policy');
    active += 1; peak = Math.max(peak, active);
    if (preview) { previews += 1; previewPeak = Math.max(previewPeak, previews); }
    await new Promise(r => setTimeout(r, 10));
    active -= 1;
    if (preview) previews -= 1;
    return base(argv, options);
  };
  const c = createController({ agent: AGENT, post: () => {}, runCli, settings: { stage: 'v2' }, handlers: [] });
  const cli = c.context.cli;
  await Promise.all([
    ...[1, 2, 3, 4].map(i => c.context.read(`k${i}`, cli.checkArgv(AGENT), p => p)),
    ...[1, 2, 3].map(i => c.context.read(`preview:capacity:${i}`, cli.previewPolicyArgv(AGENT, { rules: [`capacity:${i}`] }), p => p)),
  ]);
  assert.ok(peak <= 3, `peak ${peak}`);
  assert.equal(previewPeak, 1);
});

test('handler registry: a type or a view claimed twice, or a core type, is refused', () => {
  assert.throws(() => registry([{ name: 'a', types: { render: () => {} } }, { name: 'b', types: { render: () => {} } }]), /handled twice/);
  assert.throws(() => registry([{ name: 'a', loads: { eda: {} } }, { name: 'b', loads: { eda: {} } }]), /loaded twice/);
  assert.throws(() => registry([{ name: 'a', types: { ready: () => {} } }]), /belongs to the controller/);
  assert.throws(() => registry([{ name: 'a', types: { open: () => {} } }]), /unknown type/);
  assert.throws(() => registry([{ name: 'a', loads: { summary: {} } }]), /cannot load summary/);
  // The shipped handlers load without a conflict.
  const { c } = make();
  assert.equal(typeof c.handle, 'function');
});

test('settings: updateSettings posts init again; navigate resolves and validates its anchor (§4.3)', async () => {
  const { c, posted } = make({ settings: { stage: 'v1' } });
  c.updateSettings({ stage: 'v2', chatInsert: true });
  assert.deepEqual(posted.at(-1), { v: 2, type: 'init', stage: 'v2', reviewer: false, learningLayer: true, chatInsert: true, task: null,
    study: studyKey(AGENT.studyDir),
    marimo: { kernel: '/opt/py/bin/python', notebook: '/opt/py/bin/python -m marimo run notebooks/study_generated.py',
        editable: '/opt/py/bin/python -m marimo edit notebooks/study_editable.py',
        workbench: '/opt/py/bin/python -m marimo edit notebooks/workbench.py' },
    language: 'auto', panelContract: 2, surface: 'panel' });
  // A result id the summary does not list (no snapshot yet) opens the path's head.
  assert.equal(c.navigate({ kind: 'result', id: 'a'.repeat(64) }), true);
  assert.equal(posted.at(-1).anchor, 'path');
  assert.equal(c.navigate({ anchor: 'nowhere', kind: 'result', id: 'x' }), false);
  assert.equal(await c.command('go_to_result', {}), undefined, 'no handler registers it in WP-0');
});

test('flag: stage, learning layer, reviewer, chatInsert and their overrides', () => {
  const fake = (settings = {}) => createFake({ settings });
  assert.deepEqual(flag.settings(fake(), {}), { stage: 'v0', reviewer: false, learningLayer: true, chatInsert: false,
    language: 'auto' });
  // v0.3 (WP-E2, R21): the panel language; an unknown value reads as auto.
  assert.equal(flag.language(fake({ 'hypotrail.companion.language': 'fr' })), 'fr');
  assert.equal(flag.language(fake({ 'hypotrail.companion.language': 'de' })), 'auto');
  assert.equal(flag.stage(fake({ 'hypotrail.companion.stage': 'v2' }), {}), 'v2');
  assert.equal(flag.stage(fake({ 'hypotrail.companion.stage': 'v2' }), { HYPOTRAIL_COMPANION_STAGE: 'v1' }), 'v1');
  assert.equal(flag.stage(fake({ 'hypotrail.companion.stage': 'v7' }), {}), 'v3', 'a higher stage reads as the highest known');
  assert.equal(flag.stage(fake({ 'hypotrail.companion.stage': 'beta' }), {}), 'v0');
  assert.equal(flag.learningLayer(fake({ 'hypotrail.companion.learningLayer': false }), {}), false);
  assert.equal(flag.learningLayer(fake(), { HYPOTRAIL_COMPANION_LEARNING: '0' }), false);
  assert.equal(flag.reviewer(fake(), { HYPOTRAIL_COMPANION_REVIEWER: '1' }), true);
  // Forced off until a real VS Code session verifies that the insertion does not send
  // (decision CR.8): the setting is ignored.
  assert.equal(flag.chatInsert(fake({ 'hypotrail.companion.chatInsert': true })), false);
  assert.equal(flag.settings(fake({ 'hypotrail.companion.chatInsert': true }), {}).chatInsert, false);
  assert.equal(flag.CHAT_INSERT_VERIFIED, false);
  assert.equal(flag.settings(fake(), { HYPOTRAIL_COMPANION_CHAT_INSERT: '1' }).chatInsert, false, 'no environment override');
  assert.equal(flag.settings(fake(), {}, { forceReviewer: true }).reviewer, true);
  assert.ok(flag.stageAtLeast('v2', 'v1') && !flag.stageAtLeast('v1', 'v2'));
});

test('cache: per key and revision; previews kept in a bounded list', () => {
  const cache = createCache({ previewLimit: 2 });
  cache.set('decisions', 3, 'a');
  assert.equal(cache.get('decisions', 3), 'a');
  assert.equal(cache.get('decisions', 4), undefined);
  cache.set('preview:capacity:1', 3, 1);
  cache.set('preview:capacity:2', 3, 2);
  cache.get('preview:capacity:1', 3);
  cache.set('preview:capacity:3', 3, 3);
  assert.equal(cache.get('preview:capacity:2', 3), undefined, 'least recently used dropped');
  assert.equal(cache.get('preview:capacity:1', 3), 1);
  cache.prune(4);
  assert.equal(cache.get('decisions', 3), undefined);
  assert.equal(cache.get('preview:capacity:3', 3), 3, 'previews survive a newer revision');
});

test('CR.2: init names the study by its key (16 hex of the path\'s SHA-256), never by its path; another study, another key', async () => {
  const { c, posted } = make({ settings: { stage: 'v1' } });
  await c.handle({ v: 2, type: 'ready' });
  const init = posted.find(m => m.type === 'init');
  assert.match(init.study, /^[0-9a-f]{16}$/);
  assert.ok(!JSON.stringify(init).includes(AGENT.studyDir), 'the path is never sent in init');
  assert.notEqual(studyKey('/studies/another one'), init.study);
});
