'use strict';
// EDA tab, extension side (scope U, WP-U4; COMPANION-ADVANCED §6.3, §7 W4, §9): the
// EdaModel of lib/models/eda.js and the handler lib/handlers/eda.js, driven through the
// real controller with the fixture CLI (test/fixture-cli.js). No process is started.
// Requirement map: ED-1 (W4 argv exactly; a column or activity outside eda_catalog is
// `invalid` before any `run`), ED-2 (after a run, the new card and the ledger count;
// validation 0), INV-7 (no figure of a non-current result), INV-8 (refusals), INV-13
// (only eda.* per-column activities of the catalog), §7 outcomes (not promoted).

const test = require('node:test');
const assert = require('node:assert/strict');
const { createController } = require('../lib/controller');
const { fakeCli, payload } = require('./fixture-cli');
const protocol = require('../lib/protocol');
const { toEdaModel, requestable, EDA_KEYS, CARD_KEYS, FMT, FIXTURES, ModelError } = require('../lib/models/eda');
const handler = require('../lib/handlers/eda');

const AGENT = { argv: ['/opt/py/bin/python', '-m', 'mlkit.study.cli'], studyDir: '/studies/bank marketing "demo"' };
const UUID = '0f8fad5b-d9cb-469f-a165-70867728950e';
const clone = x => JSON.parse(JSON.stringify(x));

function make({ settings = { stage: 'v2' }, route } = {}) {
  const posted = [];
  const runCli = fakeCli(route, { agentArgv: AGENT.argv });
  const c = createController({ agent: AGENT, post: m => posted.push(m), runCli, settings, exists: () => true, uuid: () => UUID });
  return { c, posted, runCli, last: type => posted.filter(m => m.type === type).at(-1),
    commands: () => runCli.calls.map(x => x.tail[0]) };
}

function resolve(values, path) {
  return path.split('.').reduce((at, seg) => (Array.isArray(at) ? at[Number(seg)] : at[seg]), values);
}

// --- model ---------------------------------------------------------------------------------

test('EdaModel: keys, gallery order, and the catalog of both fixtures', () => {
  for (const name of FIXTURES) {
    const m = toEdaModel(payload(name));
    assert.deepEqual(Object.keys(m), EDA_KEYS);
    for (const card of m.cards) assert.deepEqual(Object.keys(card), CARD_KEYS);
  }
  const b = toEdaModel(payload('evidence.binary'));
  assert.equal(b.task, 'binary');
  // WP-A7: the fixture gained the single-feature signal and the quality check (captured);
  // the signal follows the special values, the quality check (development rows) comes last.
  assert.deepEqual(b.cards.map(c => c.slot), ['eda.target_rate', 'eda.special_values', 'eda.single_feature_signal',
    'eda.rate_by:job', 'eda.distribution:age', 'eda.quality']);
  assert.deepEqual(b.cards.map(c => c.kind), ['target_rate', 'special_values', 'signal', 'rate_by', 'distribution', 'quality']);
  assert.deepEqual(b.catalog.map(a => [a.activity, a.perColumn, a.runnable]), [['eda.target_rate', false, true],
    ['eda.special_values', false, true], ['eda.rate_by', true, true], ['eda.distribution', true, true]]);
  assert.deepEqual(b.rowsSeen, { scope: 'split', trainEda: 3164, validationEda: 0, validationModels: 1357 });
  const r = toEdaModel(payload('evidence.regression'));
  assert.equal(r.task, 'regression');
  assert.deepEqual(r.cards.map(c => c.kind), ['target_summary', 'special_values', 'signal', 'mean_by', 'distribution', 'quality']);
  assert.deepEqual(r.rowsSeen, { scope: 'split', trainEda: 280, validationEda: 0, validationModels: 118 });
  assert.throws(() => toEdaModel(payload('decisions.binary')), ModelError);
  assert.throws(() => toEdaModel({ schema: 'hypotrail.evidence/1', ok: false }), ModelError);
});

test('EdaModel rows seen under cross-validation: the development rows EDA read, never "train 0" (WP-E1, R26)', () => {
  // The captured cross-validated Bank study records EDA on the `development` partition.
  const raw = payload('captured/evidence.binary.cv');
  const ledger = raw.exposure.ledger.find(r => r.purpose === 'train_eda');
  assert.equal(ledger.partition, 'development');
  const m = toEdaModel(raw);
  assert.equal(m.rowsSeen.scope, 'development');
  assert.equal(m.rowsSeen.trainEda, ledger.rows);
  assert.ok(m.rowsSeen.trainEda > 0);
  assert.equal(m.rowsSeen.validationEda, 0);
  assert.equal(m.rowsSeen.validationModels, raw.exposure.summary.validation_rows_used_for_selection);
  // A split study keeps its two partitions.
  assert.equal(toEdaModel(payload('captured/evidence.binary')).rowsSeen.scope, 'split');
});

test('EdaModel: every number is an engine value at its path, with a format of FMT (INV-14, ED-4)', () => {
  for (const name of ['evidence.binary', 'evidence.regression']) {
    const p = payload(name);
    const m = toEdaModel(p);
    let seen = 0;
    const walk = (x, card) => {
      if (Array.isArray(x)) return x.forEach(y => walk(y, card));
      if (!x || typeof x !== 'object') return undefined;
      if (typeof x.path === 'string' && typeof x.fmt === 'string' && 'value' in x) {
        const entry = p.results.find(e => e.result_id === card.resultId);
        assert.equal(resolve(entry.values, x.path), x.value, `${card.slot} ${x.path}`);
        assert.ok(Object.values(FMT[card.activity]).includes(x.fmt) || x.fmt === 'int', `${card.slot} ${x.fmt}`);
        seen += 1;
        return undefined;
      }
      return Object.values(x).forEach(y => walk(y, card));
    };
    for (const card of m.cards) walk(card.data, card);
    assert.ok(seen > 40, `${name}: ${seen} cited numbers`);
  }
});

test('EdaModel: a stale or unverified result carries no figure; an unpromoted one is not a card (INV-7)', () => {
  const p = clone(payload('evidence.binary'));
  const rateBy = p.results.find(r => r.slot === 'eda.rate_by:job');
  rateBy.current = false;
  rateBy.values = null;
  const dist = p.results.find(r => r.slot === 'eda.distribution:age');
  dist.integrity = 'integrity_error';
  p.results.push({ ...clone(dist), result_id: 'f'.repeat(64), promoted: false, slot: null });
  const m = toEdaModel(p);
  assert.equal(m.cards.length, 6);   // WP-A7: the signal and quality results of the fixture
  for (const slot of ['eda.rate_by:job', 'eda.distribution:age']) {
    const card = m.cards.find(c => c.slot === slot);
    assert.equal(card.current, false);
    assert.equal(card.data, null);
    assert.ok(card.column);
  }
});

test('EdaModel: class imbalance below 0.2 or above 0.8 of the positive share; a missing text reads the engine detail', () => {
  const p = clone(payload('evidence.binary'));
  const target = p.results.find(r => r.activity === 'eda.target_rate');
  for (const [rate, imbalanced] of [[0.115, true], [0.2, false], [0.5, false], [0.8, false], [0.81, true]]) {
    target.values.rate = rate;
    assert.equal(toEdaModel(p).cards[0].data.imbalanced, imbalanced, String(rate));
  }
  p.eda_catalog.activities[3].runnable = false;
  p.eda_catalog.activities[3].missing = [{ requirement: 'result_current', slot: 'split', detail: 'Split the data before exploring or fitting it.' },
    { requirement: 'decision_confirmed', decision: 'split', status: 'proposed' }];
  const a = toEdaModel(p).catalog[3];
  assert.deepEqual(a.missing, ['Split the data before exploring or fitting it.', 'the decision split is confirmed']);
  assert.equal(requestable(toEdaModel(p), 'eda.distribution', 'age'), null);
  assert.equal(requestable(toEdaModel(p), 'eda.rate_by', 'age').name, 'age');
  assert.equal(requestable(toEdaModel(p), 'eda.target_rate', 'age'), null);
});

// --- handler: load -----------------------------------------------------------------------------

test('load eda: one evidence read, its EdaModel as valid view_data, cached per revision; absent below v2', async () => {
  const { c, posted, runCli, last } = make();
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'load', view: 'eda' });
  const reads = runCli.calls.filter(x => x.tail[0] === 'evidence');
  assert.deepEqual(reads.map(x => x.tail), [['evidence', '--json', '--study', AGENT.studyDir]]);
  const data = last('view_data');
  assert.equal(data.view, 'eda');
  assert.equal(data.revision, 27);
  assert.deepEqual(data.model, toEdaModel(payload('evidence.binary')));
  assert.ok(protocol.validateOutgoing(data));
  await c.handle({ v: 2, type: 'load', view: 'eda' });
  assert.equal(runCli.calls.filter(x => x.tail[0] === 'evidence').length, 1, 'cached at this revision');
  assert.equal(c.diagnostics().dropped, 0);

  const v1 = make({ settings: { stage: 'v1' } });
  await v1.c.handle({ v: 2, type: 'ready' });
  await v1.c.handle({ v: 2, type: 'load', view: 'eda' });
  assert.equal(v1.last('load_error').message, 'Not available in this stage.');
  await v1.c.handle({ v: 2, type: 'run_eda', activity: 'eda.distribution', column: 'balance', revision: 27 });
  assert.equal(v1.c.diagnostics().ignored, 1, 'run_eda is a v2 message');
  assert.ok(!v1.runCli.calls.some(x => x.tail[0] === 'evidence' || x.tail[0] === 'run'));
  assert.equal(posted.filter(m => m.type === 'load_error').length, 0);
});

test('load eda: a refusal or a wrong payload is a load_error', async () => {
  const { c, last } = make({ route: tail => (tail[0] === 'evidence' ? 'error.unknown_result' : undefined) });
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'load', view: 'eda' });
  assert.match(last('load_error').message, /^unknown_result: /);
  const wrong = make({ route: tail => (tail[0] === 'evidence' ? 'decisions.binary' : undefined) });
  await wrong.c.handle({ v: 2, type: 'ready' });
  await wrong.c.handle({ v: 2, type: 'load', view: 'eda' });
  assert.equal(wrong.last('load_error').message, 'The CLI did not return a hypotrail.evidence/1 document.');
});

// --- handler: run_eda (W4) ------------------------------------------------------------------

test('ED-1: run_eda is exactly W4 with the catalog activity and column, then a refresh', async () => {
  const { c, runCli, last } = make();
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'load', view: 'eda' });
  const before = runCli.calls.length;
  await c.handle({ v: 2, type: 'run_eda', activity: 'eda.distribution', column: 'balance', revision: 27 });
  const tails = runCli.calls.slice(before).map(x => x.tail);
  assert.deepEqual(tails[0], ['run', 'eda.distribution', '--column=balance', '--request-id', UUID,
    '--expected-revision', '27', '--json', '--study', AGENT.studyDir], 'cached catalog: the run is the first process');
  assert.deepEqual(runCli.calls[before].argv.slice(0, AGENT.argv.length), AGENT.argv);
  assert.equal(runCli.calls[before].options.timeoutMs, 300000);
  assert.equal(tails[1][0], 'status', 'refreshed after the outcome');
  const o = last('outcome');
  assert.equal(o.op, 'W4');
  assert.equal(o.kind, 'ok');
  assert.equal(o.target, 'eda.distribution:balance');
  assert.deepEqual(o.recorded, { slot: 'eda.distribution:age', status: 'promoted' }, 'the slot the engine recorded');
  assert.ok(protocol.validateOutgoing(o));
  assert.ok(!tails.flat().some(a => /validation|partition|--max-groups/.test(a)), 'no partition option exists');
});

test('ED-1, INV-13: an activity or column outside the catalog is invalid, and no run starts', async () => {
  const cases = [
    [{ activity: 'eda.distribution', column: 'duration' }, handler.MESSAGES.notInCatalog],
    [{ activity: 'eda.distribution', column: '--max-groups=999' }, handler.MESSAGES.notInCatalog],
    [{ activity: 'eda.rate_by', column: 'y' }, handler.MESSAGES.notInCatalog],
    [{ activity: 'eda.target_rate', column: 'age' }, handler.MESSAGES.notInCatalog],
    [{ activity: 'eda.mean_by', column: 'age' }, handler.MESSAGES.notInCatalog],
    [{ activity: 'eda.fit_anything', column: 'age' }, handler.MESSAGES.notInCatalog],
  ];
  for (const [m, message] of cases) {
    const { c, runCli, last } = make();
    await c.handle({ v: 2, type: 'ready' });
    await c.handle({ v: 2, type: 'load', view: 'eda' });
    const before = runCli.calls.length;
    await c.handle({ v: 2, type: 'run_eda', revision: 27, ...m });
    assert.equal(runCli.calls.length, before, `${m.activity} ${m.column}: no CLI call at all`);
    assert.deepEqual(last('outcome'), { v: 2, type: 'outcome', op: 'W4', kind: 'invalid', target: `${m.activity}:${m.column}`, message });
  }
  // Not an eda.* activity: the protocol drops it before the handler.
  const { c, runCli } = make();
  await c.handle({ v: 2, type: 'ready' });
  const before = runCli.calls.length;
  await c.handle({ v: 2, type: 'run_eda', activity: 'split', column: 'age', revision: 27 });
  await c.handle({ v: 2, type: 'run_eda', activity: 'fit.logistic', column: 'age', revision: 27 });
  assert.equal(c.diagnostics().ignored, 2);
  assert.equal(runCli.calls.length, before);
});

test('W4 pre-checks: a not runnable activity, a moved revision, and reviewer mode run nothing', async () => {
  const blocked = clone(payload('evidence.binary'));
  blocked.eda_catalog.activities[3].runnable = false;
  let r = make({ route: tail => (tail[0] === 'evidence' ? { payload: blocked } : undefined) });
  await r.c.handle({ v: 2, type: 'ready' });
  await r.c.handle({ v: 2, type: 'run_eda', activity: 'eda.distribution', column: 'balance', revision: 27 });
  assert.equal(r.last('outcome').message, handler.MESSAGES.notRunnable);
  assert.ok(!r.commands().includes('run'));

  r = make();
  await r.c.handle({ v: 2, type: 'ready' });
  await r.c.handle({ v: 2, type: 'run_eda', activity: 'eda.distribution', column: 'balance', revision: 25 });
  assert.equal(r.last('outcome').kind, 'invalid');
  assert.equal(r.last('outcome').message, handler.MESSAGES.moved);
  assert.ok(!r.commands().includes('run'));
  assert.equal(r.commands().at(-1), 'status', 'the panel refreshes');

  r = make({ settings: { stage: 'v2', reviewer: true } });
  await r.c.handle({ v: 2, type: 'ready' });
  await r.c.handle({ v: 2, type: 'run_eda', activity: 'eda.distribution', column: 'balance', revision: 27 });
  assert.deepEqual([r.last('outcome').kind, r.last('outcome').message], ['invalid', 'Read-only reviewer mode.']);
  assert.ok(!r.commands().includes('run') && !r.commands().includes('evidence'));

  r = make({ route: tail => (tail[0] === 'evidence' ? { failure: 'The hypotrail CLI did not print one JSON document.' } : undefined) });
  await r.c.handle({ v: 2, type: 'ready' });
  await r.c.handle({ v: 2, type: 'run_eda', activity: 'eda.distribution', column: 'balance', revision: 27 });
  assert.equal(r.last('outcome').kind, 'invalid');
  assert.ok(r.last('outcome').message.startsWith(handler.MESSAGES.unread));
  assert.ok(!r.commands().includes('run'));
});

test('W4 outcomes: a refusal (INV-8), a late result not promoted, and an unknown outcome', async () => {
  let r = make({ route: tail => (tail[0] === 'run' ? 'error.stale_revision' : undefined) });
  await r.c.handle({ v: 2, type: 'ready' });
  await r.c.handle({ v: 2, type: 'run_eda', activity: 'eda.rate_by', column: 'age', revision: 27 });
  let o = r.last('outcome');
  assert.equal(o.kind, 'refused');
  assert.equal(o.refusal.code, 'stale_revision');
  assert.equal(o.refusal.engineMessage, payload('error.stale_revision').error.message);
  assert.equal(r.commands().at(-1), 'status');

  r = make({ route: tail => (tail[0] === 'run' ? 'run.eda_distribution.binary.late' : undefined) });
  await r.c.handle({ v: 2, type: 'ready' });
  await r.c.handle({ v: 2, type: 'run_eda', activity: 'eda.distribution', column: 'balance', revision: 27 });
  o = r.last('outcome');
  assert.equal(o.kind, 'not_promoted');
  assert.deepEqual(o.recorded, { slot: null, status: 'late_not_promoted' });

  r = make({ route: tail => (tail[0] === 'run' ? { failure: 'The hypotrail CLI did not answer within 300 s.' } : undefined) });
  await r.c.handle({ v: 2, type: 'ready' });
  await r.c.handle({ v: 2, type: 'run_eda', activity: 'eda.distribution', column: 'balance', revision: 27 });
  o = r.last('outcome');
  assert.equal(o.kind, 'failed');
  assert.match(o.message, /The outcome is unknown/);
});

test('ED-2: after a successful run, the reread gallery holds the new card and the ledger count; validation stays 0', async () => {
  const summary = clone(payload('summary.binary'));
  const after = clone(payload('evidence.binary'));
  after.revision = 28;
  const age = after.results.find(r => r.slot === 'eda.distribution:age');
  const balance = { ...clone(age), result_id: 'b'.repeat(64), slot: 'eda.distribution:balance', params: { column: 'balance' } };
  balance.values.column = 'balance';
  after.results.push(balance);
  after.eda_catalog.activities[3].columns.find(x => x.name === 'balance').result_id = balance.result_id;
  after.exposure.ledger.find(x => x.purpose === 'train_eda').rows = 3164;
  after.exposure.ledger.find(x => x.purpose === 'train_eda').records = 5;
  let ran = false;
  const route = tail => {
    if (tail[0] === 'run') { ran = true; return undefined; }
    if (tail[0] === 'status' && ran) return { payload: { ...summary, revision: 28 } };
    if (tail[0] === 'evidence' && ran) return { payload: after };
    return undefined;
  };
  const { c, last } = make({ route });
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'load', view: 'eda' });
  assert.equal(last('view_data').model.cards.length, 6);   // WP-A7: with the signal and quality cards
  await c.handle({ v: 2, type: 'run_eda', activity: 'eda.distribution', column: 'balance', revision: 27 });
  assert.equal(last('snapshot').revision, 28);
  await c.handle({ v: 2, type: 'load', view: 'eda' });
  const m = last('view_data').model;
  assert.equal(last('view_data').revision, 28);
  assert.deepEqual(m.cards.map(x => x.slot), ['eda.target_rate', 'eda.special_values', 'eda.single_feature_signal', 'eda.rate_by:job',
    'eda.distribution:age', 'eda.distribution:balance', 'eda.quality']);
  assert.equal(m.rowsSeen.trainEda, after.exposure.ledger.find(x => x.purpose === 'train_eda' && x.partition === 'train').rows);
  assert.equal(m.rowsSeen.validationEda, 0);
});
