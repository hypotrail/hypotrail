'use strict';
// What if? tests (scope U, WP-U3): the WhatIf, PolicyPreview, and Draft models on the WP-0
// fixtures, and the What if? handler behind the real controller with the fixture CLI:
// the debounced, single-flight `preview policy` (WI-2, with fake timers) and the draft
// (read only; no W3 since the v0.3 narrowing, WI-3). COMPANION-ADVANCED §6.5, §7.
// No process is started.

const test = require('node:test');
const assert = require('node:assert/strict');
const { createController } = require('../lib/controller');
const whatif = require('../lib/handlers/whatif');
const { toWhatIfModel } = require('../lib/models/whatif');
const { toPolicyPreviewModel } = require('../lib/models/preview');
const { toDraftModel } = require('../lib/models/draft');
const { fakeCli, payload } = require('./fixture-cli');

const AGENT = { argv: ['/opt/py/bin/python', '-m', 'mlkit.study.cli'], studyDir: '/studies/bank marketing "demo"' };
const UUID = '0f8fad5b-d9cb-469f-a165-70867728950e';
const MUTATING = ['decide', 'run', 'render', 'export', 'init', 'plan'];

function make({ settings = { stage: 'v2' }, route, host = {}, task = 'binary', runCli } = {}) {
  const posted = [];
  const fake = runCli || fakeCli(route, { agentArgv: AGENT.argv, task });
  const c = createController({ agent: AGENT, post: m => posted.push(m), runCli: fake, settings, host, exists: () => true, uuid: () => UUID });
  return { c, posted, runCli: fake, of: type => posted.filter(m => m.type === type) };
}

const flush = () => new Promise(resolve => setImmediate(resolve));

// --- models ------------------------------------------------------------------------------

test('WhatIfModel (binary): the rules already evaluated, n, and the first evaluated rule', () => {
  const m = toWhatIfModel(payload('evidence.binary'));
  assert.equal(m.task, 'binary');
  assert.equal(m.n, 1357);
  assert.equal(m.initialRule, 'capacity:100');
  assert.equal(m.resultId, 'ae80b53fe0f22e164e785d0939fef003c1b90c0482f5dd6f702ac28791426d02');
  assert.deepEqual(m.evaluatedRules.map(r => [r.rule, r.selected, r.truePositives, r.precision, r.recall]),
    [['capacity:100', 100, 36, 0.36, 0.23076923076923078], ['threshold:0.2', 115, 40, 0.34782608695652173, 0.2564102564102564]]);
  assert.equal(m.evaluatedRules[0].paths.precision, 'rules.capacity:100.models.[fit.logistic].precision');
  assert.equal(m.targetLabel, 'y');
  assert.ok(!('residuals' in m), 'no regression part in a binary study');
  // Without a current evaluation: nothing evaluated, n from the split.
  const p = payload('evidence.binary');
  p.results = p.results.filter(r => r.slot !== 'policy.evaluation');
  const e = toWhatIfModel(p);
  assert.deepEqual(e.evaluatedRules, []);
  assert.equal(e.n, 1357);
  assert.equal(e.initialRule, null);
});

test('WhatIfModel (regression): errors, paired difference, residuals, bias by group, split limits', () => {
  const m = toWhatIfModel(payload('evidence.regression'));
  assert.equal(m.task, 'regression');
  assert.ok(!('evaluatedRules' in m) && !('initialRule' in m), 'none of the binary sandbox (WI-4)');
  assert.deepEqual(m.models, [{ fit: 'fit.linear', role: 'candidate' }, { fit: 'fit.baseline', role: 'reference' }]);
  assert.equal(m.errors['fit.linear'].mae, 6.308647265230509);
  assert.equal(m.errors['fit.baseline'].maeHigh, 11.181764527845038);
  assert.equal(m.deltas.fit, 'fit.linear');
  assert.equal(m.deltas.mae.side, 'one_side');
  assert.equal(m.residuals['fit.linear'].median, 5.385505011592155);
  assert.equal(m.residualsBy.column, 'model_year');
  assert.deepEqual(m.residualsBy.groups.map(g => [g.value, g.small, g.models['fit.linear'].meanResidual]),
    [['79', true, 4.042853350447878], ['80', true, 8.214577459344293], ['81', true, 5.581011579717216], ['82', false, 6.874480187231553]]);
  assert.deepEqual({ ...m.splitLimits, resultId: undefined }, { column: 'car_name', sharedGroups: 16, validationRowsInSharedGroups: 18, resultId: undefined });
  assert.deepEqual({ method: m.validation.method, column: m.validation.column, cutoff: m.validation.cutoff, n: m.validation.n },
    { method: 'ordinal_cutoff', column: 'model_year', cutoff: 79, n: 118 });
  assert.equal(m.splitOrdinal, true);
  assert.equal(m.unit, 'mpg');
});

// R9UX-5: a compared variant is named in words, with the model family its result records.
function regressionWithVariant(family) {
  const p = payload('evidence.regression');
  const evaluation = p.results.find(r => r.slot === 'evaluate.regression');
  evaluation.params.models = ['fit.baseline', 'fit.linear', 'fit.variant'];
  const linear = p.results.find(r => r.slot === 'fit.linear');
  const variant = JSON.parse(JSON.stringify(linear));
  variant.slot = 'fit.variant';
  variant.activity = 'fit.variant';
  variant.result_id = 'f'.repeat(64);
  if (family) variant.params = { model: family, family };
  p.results.push(variant);
  return p;
}

test('WhatIfModel (regression): the model family of each variant fit, from its result', () => {
  const m = toWhatIfModel(regressionWithVariant('ebm'));
  assert.deepEqual(m.models.map(x => x.fit), ['fit.linear', 'fit.variant', 'fit.baseline']);
  assert.deepEqual(m.families, { 'fit.variant': 'ebm' });
  assert.deepEqual(toWhatIfModel(regressionWithVariant(null)).families, {}, 'a linear variant records no family');
  assert.deepEqual(toWhatIfModel(payload('evidence.regression')).families, {});
});

test('PolicyPreviewModel: per rule and fit, intervals and deltas, the adopted rule', () => {
  const m = toPolicyPreviewModel(payload('preview.binary'));
  assert.deepEqual(m.rules, ['capacity:100']);
  // WP-B1: the variant is previewed with the candidate it is compared with.
  assert.deepEqual(m.fits, ['fit.logistic', 'fit.variant', 'fit.baseline']);
  const e = m.byRule['capacity:100'];
  assert.deepEqual(e.models['fit.logistic'], { selected: 100, truePositives: 36, precision: 0.36, recall: 0.23076923076923078,
    volume: 100, tiedAtCut: 0, n: 1357, nPositive: 156 });
  assert.equal(e.models['fit.baseline'].tiedAtCut, 1357);
  assert.equal(e.intervals['fit.logistic'].precision.low, 0.26);
  assert.equal(e.deltas['fit.logistic'].precision.side, 'one_side');
  assert.deepEqual(e.bootstrap, { replicates: 2000, level: 0.95, method: 'paired percentile bootstrap over validation rows' });
  assert.deepEqual(m.adopted, { status: 'confirmed', value: 'threshold:0.2' });
  assert.equal(m.modelsCurrent, true);
  assert.match(m.note, /^Experiment, not adopted/);
  const p = payload('preview.binary');
  delete p.intervals;
  assert.equal(toPolicyPreviewModel(p).byRule['capacity:100'].intervals, null);
  assert.throws(() => toPolicyPreviewModel(payload('evidence.binary')), /hypotrail.preview\/1/);
});

test('DraftModel: the engine texts byte for byte; an unevaluated rule has none', () => {
  const p = payload('proposal_draft.binary');
  const m = toDraftModel(p);
  assert.equal(m.proposable, true);
  assert.equal(m.restatement, p.restatement);
  assert.equal(m.rationale, p.rationale);
  assert.equal(m.supersedesProposal, 'p_5');
  assert.equal(m.revision, 26);
  const u = toDraftModel(payload('proposal_draft.binary.unevaluated'));
  assert.equal(u.proposable, false);
  assert.equal(u.restatement, null);
  assert.deepEqual(u.missing, [{ requirement: 'evaluated_rule', value: 'capacity:150' }]);
  assert.equal(toDraftModel(payload('proposal_draft.regression')).value, 'fit.linear');
});

// --- preview policy (WI-2) ------------------------------------------------------------------

test('WI-2: 20 slider moves run only `preview policy`, at most one per 300 ms window, the latest rule', async t => {
  t.mock.timers.enable({ apis: ['setTimeout', 'Date'] });
  const times = [];
  const base = fakeCli(undefined, { agentArgv: AGENT.argv });
  const runCli = async (argv, options) => { times.push(Date.now()); return base(argv, options); };
  runCli.calls = base.calls;
  const { c, of } = make({ runCli });
  await c.handle({ v: 2, type: 'ready' });
  const before = base.calls.length;
  for (let i = 0; i < 20; i += 1) {
    await c.handle({ v: 2, type: 'preview_policy', rules: [`capacity:${100 + i}`], intervals: false, seq: i + 1 });
    t.mock.timers.tick(50);
    await flush();
  }
  assert.equal(base.calls.length, before, 'nothing runs while the slider moves');
  t.mock.timers.tick(300);
  await whatif.settled(c.context);
  const calls = base.calls.slice(before);
  assert.deepEqual(calls.map(x => x.tail.slice(0, 4)), [['preview', 'policy', '--rule', 'capacity:119']]);
  assert.ok(calls.every(x => !MUTATING.includes(x.tail[0])));
  const results = of('preview_policy_result');
  assert.deepEqual(results.map(r => r.seq), [20], 'only the latest request is answered');
  // Moves 350 ms apart each run once, never two within 300 ms.
  const start = base.calls.length;
  times.length = 0;
  for (let i = 0; i < 20; i += 1) {
    await c.handle({ v: 2, type: 'preview_policy', rules: [`threshold:0.${10 + i}`], intervals: i % 2 === 0, seq: 100 + i });
    t.mock.timers.tick(350);
    await whatif.settled(c.context);
  }
  const spaced = base.calls.slice(start);
  assert.equal(spaced.length, 20);
  assert.ok(spaced.every(x => x.tail[0] === 'preview' && x.tail[1] === 'policy'));
  for (let i = 1; i < times.length; i += 1) assert.ok(times[i] - times[i - 1] >= whatif.DEBOUNCE_MS, `${times[i] - times[i - 1]} ms`);
  assert.equal(spaced.filter(x => x.tail.includes('--intervals')).length, 10);
});

test('preview policy: one at a time, cached per (revision, rules, intervals), errors are notices', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const base = fakeCli(tail => (tail.includes('capacity:7') ? 'error.not_implemented' : undefined), { agentArgv: AGENT.argv });
  let release;
  let active = 0;
  let most = 0;
  const runCli = async (argv, options) => {
    if (argv.includes('policy')) {
      active += 1;
      most = Math.max(most, active);
      await new Promise(resolve => { release = resolve; });
      active -= 1;
    }
    return base(argv, options);
  };
  runCli.calls = base.calls;
  const { c, of } = make({ runCli });
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'preview_policy', rules: ['capacity:100'], intervals: true, seq: 1 });
  t.mock.timers.tick(300);
  await flush();
  // A second request becomes due while the first still runs: it waits.
  await c.handle({ v: 2, type: 'preview_policy', rules: ['capacity:120'], intervals: false, seq: 2 });
  t.mock.timers.tick(300);
  await flush();
  assert.equal(base.calls.filter(x => x.tail[1] === 'policy').length, 0, 'the first is still running inside the fake');
  release();
  await flush(); await flush();
  release();
  await whatif.settled(c.context);
  assert.equal(most, 1, 'never two `preview policy` at once');
  assert.deepEqual(of('preview_policy_result').map(r => r.seq), [1, 2]);
  // The same rule again at the same revision: served from the cache.
  const n = base.calls.length;
  await c.handle({ v: 2, type: 'preview_policy', rules: ['capacity:100'], intervals: true, seq: 3 });
  t.mock.timers.tick(300);
  await whatif.settled(c.context);
  assert.equal(base.calls.length, n);
  assert.equal(of('preview_policy_result').at(-1).seq, 3);
  // A refusal is a notice; nothing else is posted for it.
  await c.handle({ v: 2, type: 'preview_policy', rules: ['capacity:7'], intervals: false, seq: 4 });
  t.mock.timers.tick(300);
  await flush();
  release();
  await whatif.settled(c.context);
  assert.match(of('notice').at(-1).text, /^The preview could not be computed: unsupported_capability/);
  assert.equal(of('preview_policy_result').at(-1).seq, 3);
});

test('preview policy and draft are v2 messages: ignored below, and an invalid rule never reaches the CLI', async () => {
  const { c, runCli } = make({ settings: { stage: 'v1' } });
  await c.handle({ v: 2, type: 'preview_policy', rules: ['capacity:100'], intervals: false, seq: 1 });
  await c.handle({ v: 2, type: 'draft', decisionId: 'policy', value: 'capacity:100', revision: 26 });
  await c.handle({ v: 2, type: 'propose', decisionId: 'policy', value: 'capacity:100', revision: 26 });
  assert.equal(c.diagnostics().ignored, 3);
  assert.equal(runCli.calls.length, 0);
  const v2 = make();
  for (const rules of [['capacity:0'], ['threshold:1.5'], ['capacity:-1'], ['threshold:0.2; rm'], []]) {
    await v2.c.handle({ v: 2, type: 'preview_policy', rules, intervals: false, seq: 1 });
  }
  assert.equal(v2.c.diagnostics().ignored, 5);
});

// --- draft, read only (WI-3) --------------------------------------------------------------

test('draft: `preview proposal` texts posted as draft_result; nothing is written', async () => {
  const { c, of, runCli } = make();
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'draft', decisionId: 'policy', value: 'capacity:100', revision: 26 });
  const d = of('draft_result').at(-1);
  assert.equal(d.decisionId, 'policy');
  assert.equal(d.value, 'capacity:100');
  assert.equal(d.revision, 26);
  assert.equal(d.model.restatement, payload('proposal_draft.binary').restatement);
  assert.deepEqual(runCli.calls.at(-1).tail, ['preview', 'proposal', 'policy', '--value=capacity:100', '--json', '--study', AGENT.studyDir]);
  assert.ok(runCli.calls.every(x => !MUTATING.includes(x.tail[0])));
});

test('WI-3 (WP-E1): no W3; propose is no message any more and nothing writes, at every stage and task', async () => {
  // v0.3 narrowing (ADR 0004 amendment, integrator decision I2): "Ask the agent to propose
  // this" copies a question (ask_agent, tested in bridge.test.js); the panel proposes nothing.
  // Lot P (R51): `open_whatif` opens the read-only editor tab; it writes nothing.
  assert.deepEqual(Object.keys(whatif.types), ['preview_policy', 'draft', 'open_whatif']);
  assert.equal(whatif.modalText, undefined);
  for (const [task, message] of [['binary', { decisionId: 'policy', value: 'capacity:100', revision: 26 }],
    ['regression', { decisionId: 'model_choice', value: 'fit.linear', revision: 22 }]]) {
    for (const settings of [{ stage: 'v2' }, { stage: 'v3' }, { stage: 'v2', reviewer: true }]) {
      const { c, of, runCli } = make({ task, settings });
      await c.handle({ v: 2, type: 'ready' });
      await c.handle({ v: 2, type: 'propose', ...message });
      assert.equal(c.diagnostics().ignored, 1, `${task} ${JSON.stringify(settings)}`);
      assert.equal(of('outcome').length, 0);
      assert.ok(runCli.calls.every(x => !MUTATING.includes(x.tail[0])), 'nothing writes');
    }
  }
  assert.equal(whatif.previewKey(['capacity:100'], true), 'preview:capacity:100:intervals');
});
