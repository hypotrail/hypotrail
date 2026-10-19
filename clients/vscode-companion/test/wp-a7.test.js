'use strict';
// WP-A7, extension side (scope U): the data card read and its model, the summary's new keys
// (criterion, the target-look ledger, the mode, the digest's junior texts), and the
// Decisions model's agent concerns and corrections. Fake CLI (test/fixture-cli.js); no
// process is started. Requirement ids: DA-1 (the `data` read), OV-9, DC-8, INV-16.

const test = require('node:test');
const assert = require('node:assert/strict');
const { createController } = require('../lib/controller');
const { fakeCli, payload } = require('./fixture-cli');
const protocol = require('../lib/protocol');
const cli = require('../lib/cli');
const { toDataModel, DATA_KEYS, FIXTURES } = require('../lib/models/data');
const { toSummaryModel } = require('../lib/models/summary');
const { toDecisionsModel } = require('../lib/models/decisions');

const AGENT = { argv: ['/opt/py/bin/python', '-m', 'mlkit.study.cli'], studyDir: '/studies/bank marketing "demo"' };
const clone = x => JSON.parse(JSON.stringify(x));

function make(settings = { stage: 'v2' }) {
  const posted = [];
  const runCli = fakeCli(undefined, { agentArgv: AGENT.argv });
  const c = createController({ agent: AGENT, post: m => posted.push(m), runCli, settings, exists: () => true });
  return { c, posted, runCli, last: type => posted.filter(m => m.type === type).at(-1) };
}

test('DataModel: keys, development rows, groups in order, five rows with the target first', () => {
  for (const name of FIXTURES) {
    const p = payload(name);
    const m = toDataModel(p);
    assert.deepEqual(Object.keys(m), DATA_KEYS);
    assert.equal(m.development.rows, p.development.rows);
    assert.deepEqual(m.groups.map(g => g.group), p.groups.map(g => g.group));
    assert.equal(m.rows.columns[0], p.target.column);
    assert.equal(m.rows.items.length, 5);
    assert.ok(m.rows.items.every(r => r.cells.length === m.rows.columns.length));
    assert.equal(m.hasFrench, true);
    assert.equal(m.finalTest.status, 'sealed');
    assert.deepEqual(JSON.parse(JSON.stringify(m)), m);
  }
  const b = toDataModel(payload('data.binary'));
  const duration = b.groups.flatMap(g => g.variables).find(v => v.name === 'duration');
  assert.deepEqual(duration.decided, { status: 'confirmed', value: 'not_available' });
  const pdays = b.groups.flatMap(g => g.variables).find(v => v.name === 'pdays');
  assert.deepEqual(pdays.specialValues.map(s => s.value), ['-1']);
  assert.throws(() => toDataModel(payload('summary.binary')), /hypotrail.data\/1/);
});

test('DataModel: a note written for the agent is not kept; a missing cell stays null', () => {
  const p = clone(payload('data.binary'));
  p.note.audience = 'agent';
  p.rows.items[0].values.age = null;
  const m = toDataModel(p);
  assert.equal(m.note, null);
  assert.equal(m.rows.items[0].cells[m.rows.columns.indexOf('age')], null);
});

test('DA-1: load data runs `data --json --study S` once per version, at stage v2 only', async () => {
  assert.deepEqual(cli.dataArgv(AGENT), [...AGENT.argv, 'data', '--json', '--study', AGENT.studyDir]);
  assert.ok(protocol.VIEWS.includes('data'));
  const { c, runCli, last } = make();
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'load', view: 'data' });
  await c.handle({ v: 2, type: 'load', view: 'data' });
  const reads = runCli.calls.filter(x => x.tail[0] === 'data');
  assert.equal(reads.length, 1, 'cached per version');
  assert.deepEqual(reads[0].tail, ['data', '--json', '--study', AGENT.studyDir]);
  assert.equal(reads[0].options.env.HYPOTRAIL_SESSION_LOG, '0', 'a read is never session-logged');
  const v = last('view_data');
  assert.equal(v.view, 'data');
  assert.ok(protocol.validateOutgoing(v));
  const low = make({ stage: 'v1' });
  await low.c.handle({ v: 2, type: 'ready' });
  await low.c.handle({ v: 2, type: 'load', view: 'data' });
  assert.equal(low.runCli.calls.filter(x => x.tail[0] === 'data').length, 0, 'below v2 nothing is read');
});

test('OV-9: the summary model carries the criterion, the target looks, and the mode', () => {
  const m = toSummaryModel(payload('summary.binary'));
  assert.deepEqual(m.criterion, { decisionStatus: 'confirmed', value: '{"metric":"precision_gain","min_points":5}', status: 'met',
    gain: 30.5, low: 21.4, high: 40.2, minimum: 5, unit: 'percentage points', rule: 'capacity:100',
    resultId: 'ae80b53fe0f22e164e785d0939fef003c1b90c0482f5dd6f702ac28791426d02', contradictsVerdict: false });
  assert.equal(m.edaLooks.targetLooks, payload('summary.binary').eda_looks.target_looks);
  assert.equal(m.mode, 'guided');
  assert.equal(m.deliverables.launch.notebook.mode, 'run');
  const old = clone(payload('summary.binary'));
  delete old.criterion; delete old.eda_looks; delete old.mode;
  const o = toSummaryModel(old);
  assert.deepEqual([o.criterion, o.edaLooks, o.mode], [null, null, null]);
  const odd = clone(payload('summary.binary'));
  odd.criterion.status = 'something_else';
  assert.equal(toSummaryModel(odd).criterion.status, 'not_assessed');
});

test('INV-16: a digest item written for the agent carries its junior text; one for the junior keeps its text', () => {
  const m = toSummaryModel(payload('captured/summary.binary'));
  const agent = m.digest.items.filter(i => i.audience === 'agent');
  assert.ok(agent.length > 0);
  for (const i of agent) {
    assert.ok(i.juniorText && i.juniorText !== i.text, i.text);
    assert.doesNotMatch(i.juniorText, /junior|channel|capacity:\d|threshold:\d/);
  }
  for (const i of m.digest.items.filter(x => x.audience === 'junior')) assert.equal(i.juniorText, i.text);
});

test('DC-8: the decisions model keeps the agent concern on its current confirmation and the correction notes', () => {
  const m = toDecisionsModel(payload('decisions.binary'));
  const fa = m.decisions.find(d => d.decisionId === 'feature_availability');
  assert.match(fa.confirmation.agentConcern, /inflation applies to campaign/);
  const row = m.history.find(h => h.decisionId === 'feature_availability');
  assert.equal(row.agentConcern, fa.confirmation.agentConcern);
  assert.ok(m.history.filter(h => h.decisionId !== 'feature_availability').every(h => h.agentConcern === null));
  const corrections = m.notes.filter(n => n.kind === 'correction');
  assert.deepEqual(corrections.map(n => [n.noteId, n.decisionId, n.status]), [['n_2', 'feature_availability', 'recorded']]);
  assert.equal(m.notes.find(n => n.noteId === 'n_1').kind, 'hold');
  const old = clone(payload('decisions.binary'));
  for (const n of old.notes) delete n.kind;
  assert.ok(toDecisionsModel(old).notes.every(n => n.kind === 'hold'), 'a note without kind is a hold');
});
