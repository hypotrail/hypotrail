'use strict';
// WP-B5 tests (scope U): the models of the v0.2b views on the captured cross-validated Bank
// study (final test opened once, then a rule changed after it) and on the hand-written
// diagnostics fixture, the share rules through the protocol, the preview and W3, the
// refusal of W1 for the opening of the final test, and the refusal copy. COMPANION-ADVANCED
// §6.1.0, §6.1.1, §6.2.5, §6.4.1, §6.5.4, §7. No process is started; every figure compared
// is read from the payload, not typed here.

const test = require('node:test');
const assert = require('node:assert/strict');
const { createController } = require('../lib/controller');
const cli = require('../lib/cli');
const protocol = require('../lib/protocol');
const refusals = require('../lib/refusals');
const { toSummaryModel } = require('../lib/models/summary');
const { toEvidenceModel } = require('../lib/models/evidence');
const { toWhatIfModel } = require('../lib/models/whatif');
const { toScenarioModel } = require('../lib/models/scenario');
const { fakeCli, payload } = require('./fixture-cli');

const AGENT = { argv: ['/opt/py/bin/python', '-m', 'mlkit.study.cli'], studyDir: '/studies/bank marketing "demo"' };
const UUID = '0f8fad5b-d9cb-469f-a165-70867728950e';

function make({ settings = { stage: 'v2' }, route, host = {} } = {}) {
  const posted = [];
  const runCli = fakeCli(route, { agentArgv: AGENT.argv });
  const c = createController({ agent: AGENT, post: m => posted.push(m), runCli, settings, host, exists: () => true, uuid: () => UUID });
  return { c, posted, runCli, of: type => posted.filter(m => m.type === type) };
}

const promoted = (p, slot) => p.results.find(r => r.slot === slot && r.promoted && r.current);

// --- the final test, the trials (EV-7, OV-11) -------------------------------------------

test('EV-7, OV-11: the summary model keeps the opening, what changed after it, the final criterion and the trials', () => {
  const raw = payload('captured/summary.binary.cv');
  const m = toSummaryModel(raw);
  const ft = raw.final_test;
  assert.equal(m.finalTest.status, 'opened');
  assert.deepEqual(m.finalTest.opening, { revision: ft.opening.revision, model: ft.opening.model, rule: ft.opening.rule,
    resultId: ft.opening.result_id, userWords: ft.opening.user_words });
  assert.equal(m.finalTest.postFinalTest, true);
  assert.deepEqual(m.finalTest.changedAfter, ft.changed_after);
  assert.ok(m.finalTest.changedAfter.includes('policy'));
  assert.equal(m.trials.count, raw.trials.count);
  const k = raw.criterion.final_test;
  assert.deepEqual(m.criterion.finalTest, { status: k.status, gain: k.gain, low: k.low, high: k.high, minimum: k.minimum,
    unit: k.unit, intervalIncludesZero: k.interval_includes_zero, resultId: k.result_id });
  // Sealed, waiting for the opening: no opening, nothing changed after, no final criterion.
  const sealed = toSummaryModel(payload('captured/summary.binary.cv.opening'));
  assert.equal(sealed.finalTest.status, 'sealed');
  assert.equal(sealed.finalTest.opening, null);
  assert.deepEqual(sealed.finalTest.changedAfter, []);
  assert.equal(sealed.criterion.finalTest, null);
  // A summary of an older engine: no trials, no opening keys.
  const before = JSON.parse(JSON.stringify(payload('summary.binary')));
  delete before.trials;
  for (const k of ['opening', 'post_final_test', 'changed_after']) delete before.final_test[k];
  const old = toSummaryModel(before);
  assert.equal(old.finalTest.postFinalTest, false);
  assert.deepEqual(old.finalTest.changedAfter, []);
  assert.equal(old.trials, null);
  assert.equal(old.finalTest.opening, null);
});

// --- the ledger (EV-8), development and final evidence (EV-9, EV-10, EV-11) ---------------

test('EV-8: the ledger rows equal the engine ledger; out-of-fold selection is highlighted; the final test is a partition', () => {
  const p = payload('captured/evidence.binary.cv');
  const m = toEvidenceModel(p);
  assert.deepEqual(m.ledger.map(r => [r.purpose, r.partition, r.rows]), p.exposure.ledger.map(r => [r.purpose, r.partition, r.rows]));
  assert.deepEqual(m.ledger.filter(r => r.selection).map(r => r.purpose), ['out_of_fold_policy_selection']);
  assert.deepEqual(m.ledger.filter(r => r.partition === 'final_test').map(r => r.purpose).sort(), ['final_evaluation', 'sealed']);
});

test('EV-10: the cross-validation scheme and the spread across folds are the engine values', () => {
  const p = payload('captured/evidence.binary.cv');
  const cv = toEvidenceModel(p).crossValidation;
  const split = promoted(p, 'split').values;
  assert.equal(cv.method, split.method);
  assert.equal(cv.folds, split.folds);
  assert.equal(cv.nRows, split.n_rows);
  assert.deepEqual(cv.fits.map(f => f.fit), ['fit.logistic', 'fit.variant']);
  for (const f of cv.fits) {
    const spread = promoted(p, f.fit).values.cross_validation.spread;
    for (const metric of f.metrics) {
      const s = spread[metric.metric];
      assert.deepEqual([metric.mean, metric.sd, metric.min, metric.max], [s.mean, s.sd, s.min, s.max], `${f.fit} ${metric.metric}`);
      assert.equal(metric.paths.mean, `cross_validation.spread.${metric.metric}.mean`);
    }
  }
  // A train/validation split has no cross-validation section.
  assert.equal(toEvidenceModel(payload('captured/evidence.binary')).crossValidation, null);
});

test('EV-11: the variant against the candidate: each model, the paired difference, its side, cited paths', () => {
  const p = payload('captured/evidence.binary.cv');
  const v = toEvidenceModel(p).variant;
  const evaluation = promoted(p, 'policy.evaluation');
  assert.equal(v.kind, promoted(p, 'fit.variant').values.variant.kind);
  assert.equal(v.evaluationId, evaluation.result_id);
  assert.equal(v.reference, 'fit.logistic');
  assert.deepEqual(v.comparisons.map(x => x.rule), evaluation.params.rules);
  for (const comp of v.comparisons) {
    const raw = evaluation.values.rules[comp.rule];
    for (const m of comp.metrics) {
      const d = raw.comparisons['fit.variant'][m.metric];
      assert.deepEqual([m.point, m.low, m.high], [d.point, d.low, d.high]);
      assert.equal(m.side, d.low > 0 || d.high < 0 ? 'one_side' : 'includes_zero');
      assert.equal(m.path, `rules.[${comp.rule}].comparisons.[fit.variant].${m.metric}.point`);
      assert.deepEqual(m.models.map(x => x.fit), ['fit.logistic', 'fit.variant', 'fit.baseline']);
      for (const x of m.models) assert.equal(x.point, raw.models[x.fit][m.metric]);
    }
  }
});

test('EV-9: the final evaluation is the engine\'s, apart from development evidence; sealed studies have none', () => {
  const p = payload('captured/evidence.binary.cv');
  const fe = toEvidenceModel(p).finalEvaluation;
  const r = promoted(p, 'final_test.evaluation');
  assert.equal(r.partition, 'final_test');
  assert.equal(fe.resultId, r.result_id);
  assert.equal(fe.n, r.values.n);
  assert.equal(fe.refitRows, r.values.refit.n_rows);
  assert.equal(fe.ruleFinal, r.values.rule_final);
  assert.equal(fe.criterion.gain, r.values.criterion.gain);
  assert.equal(fe.criterion.status, r.values.criterion.status);
  const precision = fe.metrics.find(x => x.metric === 'precision');
  assert.deepEqual(precision.models.map(x => [x.fit, x.point]), [[r.values.model, r.values.models[r.values.model].precision],
    ['fit.baseline', r.values.models['fit.baseline'].precision]]);
  assert.equal(precision.delta.point, r.values.deltas[r.values.model].precision.point);
  assert.equal(toEvidenceModel(payload('captured/evidence.binary.cv.sealed')).finalEvaluation, null);
});

// --- diagnostics (EV-12) --------------------------------------------------------------------

test('EV-12: diagnostics are read from current diag.* results in the frozen shape (CLI-CONTRACT §13), development and final apart', () => {
  const p = payload('captured/evidence.binary.cv');
  const d = toEvidenceModel(p).diagnostics;
  assert.deepEqual(d.map(x => [x.slot, x.evidence]).sort(), [['diag.binary', 'development'], ['diag.final_test', 'final']]);
  const dev = d.find(x => x.slot === 'diag.binary');
  const raw = p.results.find(r => r.result_id === dev.resultId).values;
  assert.equal(dev.rule, raw.rule);
  assert.equal(dev.ruleSource, 'adopted');
  assert.deepEqual(dev.models.map(m => m.fit), Object.keys(raw.models));
  const m = dev.models[0];
  const rc = raw.models[m.fit].confusion;
  assert.deepEqual([m.confusion.tp.value, m.confusion.fp.value, m.confusion.fn.value, m.confusion.tn.value],
    [rc.true_positives, rc.false_positives, rc.false_negatives, rc.true_negatives]);
  assert.equal(m.confusion.tn.path, `models.[${m.fit}].confusion.true_negatives`);
  assert.equal(m.curve.length, raw.models[m.fit].curve.points.length);
  assert.equal(m.calibration.brier.value, raw.models[m.fit].calibration.brier);
  assert.equal(m.calibration.brier.path, `models.[${m.fit}].calibration.brier`);
  assert.deepEqual(m.segments.map(s => s.column), raw.models[m.fit].segments.map(s => s.column));
  assert.equal(m.coefficients.total, raw.models[m.fit].coefficients.terms.length);
  assert.ok(m.coefficients.terms.length <= 8);
  const fin = d.find(x => x.slot === 'diag.final_test');
  assert.deepEqual(fin.models.map(x => x.fit), [p.results.find(r => r.result_id === fin.resultId).values.model]);
  assert.equal(fin.evaluation, 'final_test');
  // The superseded development diagnostic (stale after the new rule) is not read.
  assert.equal(p.results.filter(r => r.slot === 'diag.binary').length, 2);
  // Regression: errors, residuals, bins by prediction, quantiles, by feature.
  const r = toEvidenceModel(payload('captured/evidence.regression.diag')).diagnostics;
  assert.deepEqual(r.map(x => x.slot), ['diag.regression']);
  const rm = r[0].models[0];
  const rraw = payload('captured/evidence.regression.diag').results.find(x => x.slot === 'diag.regression').values.models[rm.fit];
  assert.equal(rm.errors.mae.value, rraw.errors.mae);
  assert.equal(rm.byPrediction.length, rraw.by_prediction.bins.length);
  assert.equal(rm.qq.length, rraw.qq.points.length);
  assert.equal(rm.heteroscedasticity.flag, rraw.heteroscedasticity.flag);
  assert.equal(r[0].smearingApplies, false);
  // v0.3 (WP-F1, R28): the main Bank capture runs its development diagnostics where the
  // plan requires them (at the adopted rule), and nothing else.
  assert.deepEqual(toEvidenceModel(payload('captured/evidence.binary')).diagnostics
    .map(x => [x.slot, x.evidence]), [['diag.binary', 'development']]);
});

test('DC-10: a waiting final_test proposal is not counted on the Decisions badge (a chat act)', () => {
  const raw = payload('captured/summary.binary.cv.opening');
  const m = toSummaryModel(raw);
  assert.ok(m.proposals.some(p => p.decisionId === 'final_test'));
  assert.equal(m.waitingCount, raw.open_proposals.filter(p => p.decision_id !== 'final_test').length);
  assert.equal(m.waitingCount, 0);
});

// --- the gain curve and share rules (WI-6, WI-7) ---------------------------------------------

test('WI-6: the gain points and each evaluated rule\'s share are the engine values; the scenario share is the case\'s', () => {
  const p = payload('captured/evidence.binary.cv');
  const m = toWhatIfModel(p);
  const values = promoted(p, 'policy.evaluation').values;
  assert.equal(m.evaluation, 'out_of_fold');
  assert.deepEqual(m.gain.points.map(x => [x.share, x.recall, x.precision]),
    values.gain_points.points.map(x => [x.share, x.recall, x.precision]));
  assert.deepEqual(m.gain.rules.map(x => [x.rule, x.share]), Object.entries(values.rules).map(([rule, x]) => [rule, x.capacity_share]));
  assert.equal(m.gain.points[1].paths.recall, 'gain_points.points.1.recall');
  assert.deepEqual(m.evaluatedRules.map(r => r.share), Object.values(values.rules).map(x => x.capacity_share));
  const s = toScenarioModel(payload('captured/status.shoppers'));
  assert.equal(s.capacityShare.value, payload('captured/status.shoppers').view.scenario_defaults.capacity_share.value);
  assert.equal(s.capacityShare.status, 'scenario_assumption');
  assert.throws(() => toScenarioModel(payload('summary.binary')), /hypotrail.status\/1/);
});

test('WI-7: a share rule passes the protocol, the preview argv and the engine draft, byte for byte (no W3 since v0.3)', async () => {
  for (const rule of ['share:0.1', 'share:0.05', 'share:1']) {
    assert.ok(protocol.validateIncoming({ v: 2, type: 'preview_policy', rules: [rule], intervals: true, seq: 1 }), rule);
    assert.deepEqual(cli.previewPolicyArgv(AGENT, { rules: [rule] }).slice(AGENT.argv.length, AGENT.argv.length + 4),
      ['preview', 'policy', '--rule', rule]);
  }
  for (const rule of ['share:0', 'share:0.0', 'share:1.5', 'share:-0.1', 'share:.1']) {
    assert.equal(protocol.validateIncoming({ v: 2, type: 'preview_policy', rules: [rule], intervals: true, seq: 1 }), null, rule);
    assert.throws(() => cli.previewPolicyArgv(AGENT, { rules: [rule] }), rule);
  }
  const draft = payload('captured/proposal_draft.binary.share');
  const summary = { ...payload('captured/summary.binary.cv'), revision: draft.revision };
  const route = tail => (tail[0] === 'status' ? { payload: summary } : tail[1] === 'proposal' ? 'captured/proposal_draft.binary.share' : undefined);
  const { c, of, runCli } = make({ route });
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'draft', decisionId: 'policy', value: 'share:0.2', revision: draft.revision });
  assert.equal(of('draft_result').at(-1).model.restatement, draft.restatement, 'byte for byte');
  assert.ok(!runCli.calls.some(x => x.tail[0] === 'decide'), 'the panel proposes nothing');
});

// --- the opening of the final test is a chat act (OV-10, DC-10) ---------------------------------

test('DC-10, OV-10: a confirm of the final_test proposal is dropped (no W1 since v0.3) and runs nothing', async () => {
  const summary = payload('captured/summary.binary.cv.opening');
  const proposal = summary.open_proposals.find(p => p.decision_id === 'final_test');
  assert.ok(proposal, 'the capture waits for the opening');
  const route = tail => (tail[0] === 'status' ? 'captured/summary.binary.cv.opening' : undefined);
  const { c, of, runCli } = make({ route, settings: { stage: 'v0' } });
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'confirm', proposalId: proposal.proposal_id,
    words: 'Yes, I open the final test now, because everything is chosen', revision: summary.revision });
  assert.ok(!runCli.calls.some(x => x.tail[0] === 'decide'), 'no decide confirm');
  assert.equal(of('outcome').length, 0);
  assert.equal(c.diagnostics().ignored, 1);
  assert.equal(summary.next_action.decision, 'final_test');
});

// --- refusals and copy (DC-11) -----------------------------------------------------------------

test('DC-11: the refusals of v0.2b are explained in words, without words to type', () => {
  const opened = refusals.describe(payload('captured/error.final_test_already_opened'));
  assert.equal(opened.code, 'final_test_already_opened');
  assert.match(opened.human, /already opened/);
  assert.match(opened.human, /Nothing was recorded\.$/);
  assert.deepEqual(opened.details, [`Opened at revision ${payload('captured/error.final_test_already_opened').error.details.opening.revision}`]);
  const paraphrase = refusals.describe({ schema: 'hypotrail.error/1', ok: false, command: 'decide confirm',
    error: { code: 'paraphrase_required', message: 'm', details: { missing: [{ concept: 'restatement', hint: 'what the proposal decides' }] } } });
  assert.deepEqual(paraphrase.details, ['Not said yet: what the proposal decides']);
  for (const code of ['paraphrase_required', 'words_contradict_value', 'final_test_already_opened']) {
    const text = refusals.BY_CODE[code];
    assert.ok(text && !/\d/.test(text) && !/"/.test(text), code);
  }
});

test('copy (WP-B5): share rules in words; the junior copy holds no digit and, for regression, no rule words', () => {
  globalThis.Hypotrail = { copy: {}, format: { number: x => String(x) } };
  require('../media/copy/junior.js');
  const J = globalThis.Hypotrail.copy.junior;
  assert.equal(J.value('policy', 'share:0.1', 'binary'), 'Select the top 10% by score');
  assert.equal(J.value('policy', 'share:0.25@fit.variant', 'binary'), 'Select the top 25% by score, with the variant');
  assert.equal(J.value('policy', 'share:0.1', 'regression'), null);
  assert.equal(J.finalTestState({ status: 'opened', opening: { resultId: 'x' }, postFinalTest: true }), 'changed');
  assert.equal(J.finalTestState({ status: 'opened', opening: { resultId: null } }), 'interrupted');
  assert.equal(J.finalTestState({ status: 'absent' }), 'absent');
  const FORBIDDEN = /\b(threshold|capacity|precision|recall|positive class|policy|calling rule|decision rule|selected)\b/i;
  for (const mode of ['guided', 'training', 'express']) {
    for (const line of J.modes.rules(mode, 'regression', true)) {
      assert.ok(!FORBIDDEN.test(line), line);
      assert.ok(!/\d/.test(line), line);
    }
  }
  assert.ok(J.why('final_test', 'regression') && !FORBIDDEN.test(J.why('final_test', 'regression')));
  assert.ok(!FORBIDDEN.test(J.why('model_variant', 'regression')));
  for (const [k, v] of Object.entries(J.finalTest)) if (typeof v === 'string') assert.ok(!/\d/.test(v), k);
  delete globalThis.Hypotrail;
});

test('copy (v0.2 closure): rule words are case-neutral (no "call" or "clients" for a sessions or a regression case)', () => {
  globalThis.Hypotrail = { copy: {}, format: { number: x => String(x) } };
  delete require.cache[require.resolve('../media/copy/junior.js')];
  require('../media/copy/junior.js');
  const J = globalThis.Hypotrail.copy.junior;
  assert.equal(J.value('policy', 'capacity:100', 'binary'), 'Select the top 100 by score');
  assert.equal(J.value('policy', 'threshold:0.2', 'binary'), 'Select every case scored 0.2 or more');
  const texts = [
    J.value('policy', 'capacity:100', 'binary'), J.value('policy', 'share:0.1', 'binary'),
    J.value('policy', 'threshold:0.2@fit.variant', 'binary'), J.why('policy', 'binary'),
  ];
  for (const t of texts) {
    assert.ok(t, 'a rule text');
    assert.doesNotMatch(t, /\b(call|calls|calling|clients?)\b/i, t);
  }
  delete globalThis.Hypotrail;
});
