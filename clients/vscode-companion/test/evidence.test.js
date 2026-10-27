'use strict';
// Evidence tests (scope U, WP-U3): the EvidenceModel (lib/models/evidence.js) on the WP-0
// fixtures, and the Evidence handler (lib/handlers/evidence.js) behind the real controller
// with the fixture CLI: loads, cache keys, stage gate, and "go to a result". COMPANION-
// ADVANCED §6.4, EV-1, EV-2, EV-4, EV-5 (the sentence choice), EV-6. No process is started.

const test = require('node:test');
const assert = require('node:assert/strict');
const { createController } = require('../lib/controller');
const { toEvidenceModel, chainFor } = require('../lib/models/evidence');
const { fakeCli, payload } = require('./fixture-cli');

const AGENT = { argv: ['/opt/py/bin/python', '-m', 'mlkit.study.cli'], studyDir: '/studies/bank marketing "demo"' };
const LOGISTIC = 'd0af48b239d736c2c2b888841085499145e3fa4cfb56b13540251fa0af3883f5';
const STALE = 'b7e3c1d09a4f5e6b8c2d1f0e3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b';
const UUID = '0f8fad5b-d9cb-469f-a165-70867728950e';

function make({ settings = { stage: 'v2' }, route, host = {}, task = 'binary' } = {}) {
  const posted = [];
  const runCli = fakeCli(route, { agentArgv: AGENT.argv, task });
  const c = createController({ agent: AGENT, post: m => posted.push(m), runCli, settings, host, exists: () => true, uuid: () => UUID });
  return { c, posted, runCli, last: type => posted.filter(m => m.type === type).at(-1) };
}

// --- model -------------------------------------------------------------------------------

test('EV-1: the Current filter lists the promoted current results; stale ones carry no figure', () => {
  const p = payload('evidence.binary');
  const m = toEvidenceModel(p);
  const current = m.results.filter(r => r.promoted && r.current).map(r => r.resultId);
  assert.deepEqual(current, p.results.filter(r => r.promoted && r.current && r.integrity === 'ok').map(r => r.result_id));
  assert.equal(current.length, 10);   // WP-A7: the fixture gained the signal and quality results
  const stale = m.results.filter(r => !r.current);
  assert.deepEqual(stale.map(r => r.resultId), [STALE]);
  for (const r of stale) {
    assert.equal(r.headline, null);
    assert.equal(r.nRows, null);
    assert.deepEqual(r.staleReason, { reason: 'replaced by a newer result of the same slot', codeChanged: [], upstreamNotCurrent: [], sourcesChanged: false });
  }
  // No value of a stale result reaches the model: the payload values are null already, and
  // a current result whose integrity fails is treated as stale.
  const broken = JSON.parse(JSON.stringify(p));
  broken.results[6].integrity = 'integrity_error';
  const b = toEvidenceModel(broken).results[6];
  assert.equal(b.current, false);
  assert.equal(b.headline, null);
  assert.equal(b.nRows, null);
  // A current result's headline is its cited segments.
  const logistic = m.results.find(r => r.resultId === LOGISTIC);
  assert.equal(logistic.headline.find(s => s.resultId).text, '0.709');
});

test('EV-2: the ledger rows and counts equal evidence.exposure.ledger (five Bank rows)', () => {
  const p = payload('evidence.binary');
  const m = toEvidenceModel(p);
  assert.equal(m.ledger.length, 5);
  assert.deepEqual(m.ledger.map(({ purpose, partition, rows, records, activities }) => ({ purpose, partition, rows, records, activities })),
    p.exposure.ledger.map(({ purpose, partition, rows, records, activities }) => ({ purpose, partition, rows, records, activities })));
  assert.deepEqual(m.ledger.filter(r => r.selection).map(r => r.purpose), ['validation_policy_selection']);
  for (const row of m.ledger) assert.equal(row.rows, p.exposure.summary.by_partition[row.partition][row.purpose]);
  // Regression: selection is recorded under model evaluation, which is the highlighted row.
  const r = toEvidenceModel(payload('evidence.regression'));
  assert.equal(r.ledger.length, 4);
  assert.deepEqual(r.ledger.filter(x => x.selection).map(x => x.purpose), ['validation_model_evaluation']);
  assert.equal(m.splitOverlap, false, 'no overlap recorded: the "explored rows" sentence is not shown');
});

test('EV-6: the lineage of fit.logistic lists dataset, split, feature availability, fit.logistic, policy.evaluation, report, notebook', () => {
  const m = toEvidenceModel(payload('evidence.binary.detail'));
  assert.equal(m.detail.resultId, LOGISTIC);
  assert.deepEqual(m.detail.chain.map(c => c.name),
    ['dataset', 'split', 'feature_availability', 'fit.logistic', 'policy.evaluation', 'report', 'notebook']);
  assert.deepEqual(m.detail.chain.map(c => c.role), ['ancestor', 'ancestor', 'ancestor', 'self', 'consumer', 'consumer', 'consumer']);
  const split = m.detail.chain[1];
  assert.equal(split.kind, 'result');
  assert.equal(split.decision, 'confirmed', 'the split decision and its result are one chip: "split · your decision"');
  assert.ok(!m.detail.chain.some(c => c.id === STALE), 'a stale consumer is not part of the lineage');
  assert.ok(m.detail.lineageEdges.some(e => e.from === 'split' && e.to === 'fit.logistic'));
  // The stale evaluation's own lineage: its fits upstream, nothing downstream.
  const stale = chainFor(m.lineage, STALE, []);
  assert.deepEqual(stale.chain.map(c => c.name), ['dataset', 'split', 'fit.baseline', 'feature_availability', 'fit.logistic', 'policy.evaluation']);
});

test('detail: facts, report anchor, notebook hint, impacts, and code status', () => {
  const m = toEvidenceModel(payload('evidence.binary.detail'));
  const d = m.detail;
  assert.equal(d.slot, 'fit.logistic');
  assert.equal(d.partition, 'validation');
  assert.equal(d.nRows, 1357);
  assert.equal(d.nPositive, 156);
  assert.equal(d.features.count, 12);
  assert.match(d.preprocessing, /fitted on training rows only$/);
  assert.deepEqual(d.code.changed, []);
  assert.equal(d.code.modules.length, 4);
  assert.deepEqual(d.exposure, { purpose: 'train_fit', partition: 'train', rows: 3164, activity: 'fit.logistic' });
  assert.equal(d.reportAnchor, `r-${LOGISTIC}`);
  assert.deepEqual(d.notebookHint, { path: 'notebooks/study_generated.py', search: 'd0af48b2' });
  assert.deepEqual(d.impacts.map(i => [i.decisionId, i.keptFits]), [['feature_availability', ['fit.baseline']], ['split', []]]);
  assert.equal(d.uncertainty, null, 'a fit has no paired interval of its own');
  // A report anchor that is not this result's is not trusted.
  const p = payload('evidence.binary.detail');
  p.detail.report_anchor = 'r-somewhere-else';
  assert.equal(toEvidenceModel(p).detail.reportAnchor, null);
});

test('EV-5: uncertainty of the current evaluation; the side of an interval picks the sentence', () => {
  const m = toEvidenceModel(payload('evidence.binary'));
  const u = m.uncertainty;
  assert.equal(u.kind, 'policy');
  assert.deepEqual(u.rules.map(r => r.rule), ['capacity:100', 'threshold:0.2']);
  const cap = u.rules[0].metrics.find(x => x.metric === 'precision');
  assert.deepEqual(cap.models.map(x => [x.fit, x.point, x.low, x.high]), [['fit.logistic', 0.36, 0.26, 0.47],
    ['fit.baseline', 0.11495946941783347, 0.09727339719970524, 0.13264554163596168]]);
  assert.equal(cap.delta.side, 'one_side');
  assert.equal(cap.delta.point, 0.24504053058216652);
  const thr = u.rules[1].metrics.find(x => x.metric === 'precision');
  assert.equal(thr.delta.side, 'undefined', 'no row selected by the baseline: the difference is not defined');
  assert.deepEqual(u.bootstrap, { replicates: 2000, level: 0.95, method: 'paired percentile bootstrap over validation rows' });
  // An interval that includes 0.
  const p = payload('evidence.binary');
  const ev = p.results.find(r => r.result_id.startsWith('ae80b53f'));
  ev.values.rules['capacity:100'].deltas['fit.logistic'].precision = { point: 0.02, low: -0.03, high: 0.07, undefined_replicates: 0 };
  assert.equal(toEvidenceModel(p).uncertainty.rules[0].metrics[0].delta.side, 'includes_zero');
  // Regression: MAE and RMSE with intervals, and the paired difference.
  const r = toEvidenceModel(payload('evidence.regression')).uncertainty;
  assert.equal(r.kind, 'regression');
  assert.equal(r.unit, 'mpg');
  const mae = r.metrics.find(x => x.metric === 'mae');
  assert.deepEqual(mae.models.map(x => x.fit), ['fit.linear', 'fit.baseline']);
  assert.equal(mae.delta.side, 'one_side');
  assert.equal(mae.delta.path, 'deltas.[fit.linear].mae');
});

test('models: a wrong schema throws; unknown keys are ignored; results without a valid id are dropped', () => {
  assert.throws(() => toEvidenceModel(payload('summary.binary')), /hypotrail.evidence\/1/);
  const p = payload('evidence.binary');
  p.extra = { anything: true };
  p.results.push({ result_id: 'not-an-id', activity: 'x' });
  const m = toEvidenceModel(p);
  assert.equal(m.results.length, 11);   // WP-A7: two more results in the fixture
  assert.deepEqual(JSON.parse(JSON.stringify(m)), m);
});

// --- handler -----------------------------------------------------------------------------

test('load evidence: the list, then a result with --result; cached per key and revision; stage v2', async () => {
  const { c, posted, runCli } = make();
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'load', view: 'evidence' });
  await c.handle({ v: 2, type: 'load', view: 'evidence' });
  await c.handle({ v: 2, type: 'load', view: 'evidence', resultId: LOGISTIC });
  const reads = runCli.calls.filter(x => x.tail[0] === 'evidence').map(x => x.tail);
  assert.deepEqual(reads, [['evidence', '--json', '--study', AGENT.studyDir],
    ['evidence', '--result', LOGISTIC, '--json', '--study', AGENT.studyDir]]);
  const data = posted.filter(m => m.type === 'view_data' && m.view === 'evidence');
  assert.equal(data.length, 3);
  assert.equal(data[0].model.detail, null);
  assert.equal(data[2].resultId, LOGISTIC);
  assert.equal(data[2].model.detail.resultId, LOGISTIC);
  assert.equal(c.diagnostics().dropped, 0, JSON.stringify(c.diagnostics().invalid));
  // The What if? view reads the same command under its own key and model.
  await c.handle({ v: 2, type: 'load', view: 'whatif' });
  const whatif = posted.filter(m => m.type === 'view_data' && m.view === 'whatif').at(-1);
  assert.equal(whatif.model.task, 'binary');
  assert.ok(Array.isArray(whatif.model.evaluatedRules));
  // Below v2 the load is not available and nothing runs.
  const v1 = make({ settings: { stage: 'v1' } });
  await v1.c.handle({ v: 2, type: 'load', view: 'evidence' });
  assert.equal(v1.runCli.calls.length, 0);
});

test('load evidence: an unknown result or a stub engine is a load_error with the engine message', async () => {
  const { c, posted } = make({ route: tail => (tail[0] === 'evidence' ? (tail.includes('--result') ? 'error.unknown_result' : 'error.not_implemented') : undefined) });
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'load', view: 'evidence', resultId: 'a'.repeat(64) });
  assert.equal(posted.at(-1).type, 'load_error');
  assert.match(posted.at(-1).message, /^unknown_result: /);
  await c.handle({ v: 2, type: 'load', view: 'evidence' });
  assert.match(posted.at(-1).message, /^unsupported_capability: evidence is reserved/);
});

test('EV-4: "Show in report" asks the report with the fragment r-<rid> (open_artifact)', async () => {
  const opened = [];
  const { c } = make({ host: { openArtifact: async (name, target, options) => opened.push({ name, target, options }) } });
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'open_artifact', artifact: 'report', resultId: LOGISTIC });
  assert.equal(opened.length, 1);
  assert.equal(opened[0].name, 'report');
  assert.match(opened[0].target, /reports[\\/]study\.html$/);
  assert.deepEqual(opened[0].options, { fragment: `r-${LOGISTIC}` });
});

test('go to a result: one match navigates; none, several, or a failed read only tells', async () => {
  const notified = [];
  const { c, posted, runCli } = make({ host: { notify: t => notified.push(t) } });
  assert.equal(await c.command('go_to_result', {}), undefined, 'no prefix: nothing to do');
  assert.equal(runCli.calls.length, 0);
  assert.equal(await c.command('go_to_result', { prefix: 'D0AF48B2' }), LOGISTIC);
  assert.deepEqual(posted.at(-1), { v: 2, type: 'navigate', anchor: 'path', kind: 'result', id: LOGISTIC });
  assert.equal(await c.command('go_to_result', { prefix: 'ffffffff' }), null);
  assert.equal(posted.at(-1).type, 'notice');
  assert.equal(posted.at(-1).text, 'No result of this study starts with ffffffff.');
  assert.deepEqual(notified, ['No result of this study starts with ffffffff.']);
  assert.equal(runCli.calls.filter(x => x.tail[0] === 'evidence').length, 1, 'the listing is cached');

  const twins = payload('evidence.binary');
  twins.results.push({ ...twins.results[0], result_id: `040ccd81${'0'.repeat(56)}` });
  const t = make({ route: tail => (tail[0] === 'evidence' ? { payload: twins } : undefined) });
  assert.equal(await t.c.command('go_to_result', { prefix: '040ccd81' }), null);
  assert.match(t.posted.at(-1).text, /^Several results start with 040ccd81\./);
  assert.equal(await t.c.command('go_to_result', { prefix: '040ccd8142' }), twins.results[0].result_id);

  const f = make({ route: tail => (tail[0] === 'evidence' ? { failure: 'The hypotrail CLI did not print one JSON document.' } : undefined) });
  assert.equal(await f.c.command('go_to_result', { prefix: 'd0af48b2' }), null);
  assert.match(f.posted.at(-1).text, /^The results of this study could not be read: /);
  assert.ok(f.runCli.calls.every(x => x.tail[0] === 'evidence'), 'reads only');
});

// --- R11 (owner session 2026-10-26): one card per compared variant (EV-15) --------------------

const { VARIANT_SLOTS } = require('../lib/models/evidence');

const promotedRaw = (raw, slot) => raw.results.find(r => r.slot === slot && r.promoted && r.current);

test('EV-15: every compared variant has its own card, in slot order, with its figures cited', () => {
  const raw = payload('captured/evidence.binary.families');
  const m = toEvidenceModel(raw);
  assert.deepEqual(m.variantCards.map(v => [v.slot, v.kind, v.family]),
    [['fit.variant', 'regularisation', null], ['fit.variant:2', 'family', 'ebm'], ['fit.variant:3', 'family', 'hgb']]);
  const selection = promotedRaw(raw, 'policy.evaluation');
  const stored = selection.values.model_selection.configurations;
  for (const [i, v] of m.variantCards.entries()) {
    assert.equal(v.resultId, promotedRaw(raw, VARIANT_SLOTS[i]).result_id);
    const k = stored.findIndex(c => c.slot === v.slot);
    // Beside the candidate's, cited from the stored `model_selection` of the evaluation.
    assert.equal(v.comparison.resultId, selection.result_id);
    assert.equal(v.comparison.variant.mean.value, stored[k].mean);
    assert.equal(v.comparison.variant.mean.path, `model_selection.configurations.${k}.mean`);
    assert.equal(v.comparison.difference.mean.value, stored[k].difference.mean);
    assert.equal(v.comparison.candidate.slot, 'fit.logistic');
    assert.equal(v.comparison.candidate.mean.value, stored.find(c => c.kind === 'candidate').mean);
    assert.equal(v.question, stored[k].question);
  }
  // The penalised variant: its coefficients from the current development diagnostics.
  const diag = promotedRaw(raw, 'diag.binary');
  const [reg, ebm, hgb] = m.variantCards;
  assert.equal(reg.diagnostics, 'current');
  assert.equal(reg.diagnosticsId, diag.result_id);
  assert.equal(reg.coefficients.terms[0].value, diag.values.models['fit.variant'].coefficients.terms[0].value);
  assert.equal(reg.coefficients.terms[0].path, 'models.[fit.variant].coefficients.terms.0.value');
  assert.equal(reg.analysis, null);
  assert.equal(reg.tuning, null);
  // The families: their own diagnostics (the cards of EV-14), and the tuning of each fold.
  assert.equal(ebm.analysis.kind, 'ebm_terms');
  assert.equal(hgb.analysis.kind, 'permutation_importance');
  assert.deepEqual(ebm.analysis, m.familyFits[0]);
  const tuning = promotedRaw(raw, 'fit.variant:2').values.tuning;
  assert.equal(ebm.tuning.parameter, tuning.parameter);
  assert.deepEqual(ebm.tuning.perFold.map(f => [f.fold, f.value]), tuning.per_fold.map(f => [f.fold, f.value]));
  assert.equal(ebm.tuning.perFold[2].path, 'tuning.per_fold.2.value');
  assert.equal(ebm.tuning.development.value, tuning.development.value);
});

test('EV-15: a tuned and a drop-group variant get their card; a variant the diagnostics miss says so', () => {
  const raw = JSON.parse(JSON.stringify(payload('captured/evidence.binary.families')));
  const first = promotedRaw(raw, 'fit.variant');
  first.values.variant = { kind: 'tuned' };
  first.values.tuning = { parameter: 'C', values: [0.01, 0.1, 1], inner_folds: 3, metric: 'roc_auc',
    meaning: 'inverse penalty strength', per_fold: [1, 2, 3, 4, 5].map(fold => ({ fold, value: fold % 2 ? 0.1 : 1 })),
    development: { value: 0.1 } };
  const second = promotedRaw(raw, 'fit.variant:2');
  second.values.variant = { kind: 'drop_group', group: 'campaign' };
  delete second.values.family_diagnostics;
  delete second.values.family;
  // The development diagnostics cover the candidate and the first variant only.
  const diag = promotedRaw(raw, 'diag.binary');
  for (const slot of ['fit.variant:2', 'fit.variant:3']) delete diag.values.models[slot];
  const [tuned, drop, hgb] = toEvidenceModel(raw).variantCards;
  assert.equal(tuned.kind, 'tuned');
  assert.deepEqual(tuned.tuning.perFold.map(f => f.value), [0.1, 1, 0.1, 1, 0.1]);
  assert.equal(tuned.tuning.perFold[0].path, 'tuning.per_fold.0.value');
  assert.equal(tuned.tuning.development.value, 0.1);
  assert.equal(tuned.diagnostics, 'current');
  assert.ok(tuned.coefficients.terms.length > 0);
  assert.deepEqual([drop.kind, drop.group, drop.analysis, drop.diagnostics, drop.coefficients], ['drop_group', 'campaign', null, 'not_run', null]);
  assert.equal(hgb.diagnostics, 'not_run');
  assert.equal(hgb.analysis.kind, 'permutation_importance');
  // No current development diagnostic at all: every variant says it is not run yet.
  diag.current = false;
  assert.deepEqual(toEvidenceModel(raw).variantCards.map(v => v.diagnostics), ['not_run', 'not_run', 'not_run']);
  // INV-7: a stale variant fit gets no card; a stale evaluation leaves the figures out.
  second.current = false;
  promotedRaw(raw, 'policy.evaluation').current = false;
  const cards = toEvidenceModel(raw).variantCards;
  assert.deepEqual(cards.map(v => v.slot), ['fit.variant', 'fit.variant:3']);
  assert.ok(cards.every(v => v.comparison === null));
});

test('EV-15: a study with one variant and no selection keeps one card; none without a variant', () => {
  const cv = toEvidenceModel(payload('captured/evidence.binary.cv'));
  assert.deepEqual(cv.variantCards.map(v => v.slot), ['fit.variant']);
  assert.equal(toEvidenceModel(payload('evidence.binary')).variantCards.length, 0);
  const regression = toEvidenceModel(payload('captured/evidence.regression.diag'));
  assert.deepEqual(regression.variantCards.map(v => [v.slot, v.diagnostics]), [['fit.variant', 'current']]);
  assert.equal(regression.variantCards[0].coefficients.terms[0].path, 'models.[fit.variant].coefficients.terms.0.value');
});
