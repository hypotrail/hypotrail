'use strict';
// WP-K tests (scope U): the models of what WP-F1 added (the stored selection among the
// variants, each family's own diagnostics, the live budget and the family shortlist of the
// full view), the one `status --json` read the What if? scenario and the Evidence trials
// share, the variant list in words, and the extension's words in French (refusals, notices,
// the language resolution). No process is started; every figure compared is read from the
// captured payloads, not typed here.

const test = require('node:test');
const assert = require('node:assert/strict');
const { createController } = require('../lib/controller');
const refusals = require('../lib/refusals');
const l10n = require('../lib/l10n');
const { toEvidenceModel } = require('../lib/models/evidence');
const { toTrialsModel } = require('../lib/models/trials');
const { fakeCli, payload } = require('./fixture-cli');

const AGENT = { argv: ['/opt/py/bin/python', '-m', 'mlkit.study.cli'], studyDir: '/studies/bank marketing "demo"' };
const UUID = '0f8fad5b-d9cb-469f-a165-70867728950e';

function make({ settings = { stage: 'v2' }, route } = {}) {
  const posted = [];
  const runCli = fakeCli(route, { agentArgv: AGENT.argv });
  const c = createController({ agent: AGENT, post: m => posted.push(m), runCli, settings, exists: () => false, uuid: () => UUID });
  return { c, posted, runCli, of: type => posted.filter(m => m.type === type) };
}

const promoted = (p, slot) => p.results.find(r => r.slot === slot && r.promoted && r.current);

// --- the stored selection and the family diagnostics (EvidenceModel) -----------------------

test('the selection is the evaluation\'s stored model_selection, every figure with its value path', () => {
  const raw = payload('captured/evidence.binary.families');
  const stored = promoted(raw, 'policy.evaluation').values.model_selection;
  const m = toEvidenceModel(raw);
  const s = m.selection;
  assert.equal(s.resultId, promoted(raw, 'policy.evaluation').result_id);
  assert.equal(s.available, true);
  assert.equal(s.folds, stored.folds);
  assert.deepEqual(s.configurations.map(c => c.slot), stored.configurations.map(c => c.slot));
  for (const [i, c] of s.configurations.entries()) {
    assert.equal(c.mean.value, stored.configurations[i].mean);
    assert.equal(c.mean.path, `model_selection.configurations.${i}.mean`);
    assert.deepEqual(c.perFold.map(x => x.value), stored.configurations[i].per_fold);
    if (stored.configurations[i].difference) {
      assert.equal(c.difference.mean.value, stored.configurations[i].difference.mean);
      assert.equal(c.difference.low, stored.configurations[i].difference.low);
    } else {
      assert.equal(c.difference, null);
    }
  }
  // What a regularisation variant changes comes from its own fit.
  assert.equal(s.configurations[1].strength, promoted(raw, 'fit.variant').values.variant.strength);
  assert.equal(s.oneSe.pick, stored.one_se.pick);
  assert.deepEqual(s.oneSe.texts, stored.one_se.texts);
  assert.equal(s.optimism.estimate.value, stored.optimism.estimate);
  assert.equal(s.advice.code, 'budget_exhausted');
  assert.equal(s.advice.stop, true);
  assert.deepEqual(s.budget, { max: 3, used: 3, remaining: 0, declared: 3, legacy: false });
});

test('a study without cross-validation keeps its budget and the engine\'s reason; no evaluation, no selection', () => {
  const s = toEvidenceModel(payload('captured/evidence.binary')).selection;
  assert.equal(s.available, false);
  assert.deepEqual(s.configurations, []);
  assert.equal(s.advice.code, 'not_available');
  assert.equal(s.budget.legacy, true);
  const sealed = payload('captured/evidence.binary.families');
  const stale = JSON.parse(JSON.stringify(sealed));
  for (const r of stale.results) if (r.slot === 'policy.evaluation') r.current = false;
  assert.equal(toEvidenceModel(stale).selection, null, 'INV-7: a stale evaluation is not cited');
});

test('each family fit brings its own diagnostics: the EBM terms and shapes, the boosting importance', () => {
  const raw = payload('captured/evidence.binary.families');
  const fits = toEvidenceModel(raw).familyFits;
  assert.deepEqual(fits.map(f => [f.slot, f.family, f.kind]),
    [['fit.variant:2', 'ebm', 'ebm_terms'], ['fit.variant:3', 'hgb', 'permutation_importance']]);
  const ebm = fits[0];
  const fd = promoted(raw, 'fit.variant:2').values.family_diagnostics;
  assert.equal(ebm.total, fd.n_terms);
  assert.ok(ebm.terms.length <= 8 && ebm.terms.length > 0);
  const top = ebm.terms[0];
  const i = fd.terms.findIndex(t => t.term === top.term);
  assert.equal(top.importance.value, fd.terms[i].importance);
  assert.equal(top.importance.path, `family_diagnostics.terms.${i}.importance`);
  assert.ok(ebm.terms.filter(t => t.shape).length <= 3);
  const hgb = fits[1];
  const pi = promoted(raw, 'fit.variant:3').values.family_diagnostics;
  assert.equal(hgb.columns[0].importance.value, Math.max(...pi.columns.map(c => c.importance)));
  assert.equal(hgb.repeats, pi.repeats);
  // A study whose variants are linear has no family diagnostics.
  assert.deepEqual(toEvidenceModel(payload('captured/evidence.binary.cv')).familyFits, []);
});

// --- the live budget and the shortlist (TrialsModel, `status --json`) -----------------------

test('the trials model keeps the live budget, each variant\'s question and the engine\'s shortlist', () => {
  const raw = payload('captured/status.binary.families');
  const t = toTrialsModel(raw);
  assert.deepEqual(t.budget, { max: 3, used: 3, remaining: 0, declared: 3, legacy: false });
  const questions = Object.fromEntries(raw.view.model_selection.configurations.filter(c => c.question).map(c => [c.slot, c.question]));
  assert.deepEqual(t.questions, questions);
  const f = raw.view.model_families;
  assert.equal(t.families.recommendation, f.recommendation);
  assert.deepEqual(t.families.texts, f.texts);
  assert.equal(t.families.source, f.evidence.source);
  assert.deepEqual(t.families.families.map(x => x.family), ['linear', 'ebm', 'hgb']);
  assert.deepEqual(t.families.shortlist, f.shortlist);
  assert.deepEqual(t.families.checks.nonlinearity.map(x => x.feature), f.evidence.checks.nonlinearity.map(x => x.feature));
  // Before the variant decision is confirmed, nothing of the budget is used.
  assert.equal(toTrialsModel(payload('captured/status.binary.families.proposal')).budget.used, 0);
  // A new study: no diagnostics yet, the shortlist waits for them.
  assert.equal(toTrialsModel(payload('captured/status.shoppers')).families.recommendation, 'run_diagnostics');
});

test('trials and the What if? scenario share one `status --json` read per version', async () => {
  const { c, runCli, of } = make({ settings: { stage: 'v2' }, route: tail => (tail[0] === 'status' && !tail.includes('--summary')
    ? 'captured/status.binary.families' : undefined) });
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'load', view: 'trials' });
  await c.handle({ v: 2, type: 'load', view: 'scenario' });
  const full = runCli.calls.filter(x => x.tail[0] === 'status' && !x.tail.includes('--summary'));
  assert.equal(full.length, 1);
  const data = of('view_data');
  assert.deepEqual(data.map(d => d.view), ['trials', 'scenario']);
  assert.equal(data[0].model.budget.used, 3);
});

// --- the variant list in words ----------------------------------------------------------------

test('a variant list reads in words, in English and in French', () => {
  const value = { variants: [{ kind: 'regularisation', strength: 'strong' }, { kind: 'family', family: 'ebm' },
    { kind: 'family', family: 'hgb' }] };
  globalThis.Hypotrail = { copy: {}, format: { number: x => String(x) } };
  for (const f of ['../media/copy/junior.js', '../media/copy-fr/junior.js']) delete require.cache[require.resolve(f)];
  require('../media/copy/junior.js');
  require('../media/copy-fr/junior.js');
  const en = globalThis.Hypotrail.copy.junior;
  const fr = globalThis.Hypotrail.copyFr.junior;
  assert.equal(en.value('model_variant', JSON.stringify(value), 'binary'),
    'Compare with a more regularised variant, an Explainable Boosting Machine and gradient boosting');
  assert.equal(fr.value('model_variant', JSON.stringify(value), 'binary'),
    'Comparer avec une variante plus régularisée, une Explainable Boosting Machine et le gradient boosting');
  assert.equal(en.value('model_variant', JSON.stringify({ variants: [{ kind: 'tuned' }] }), 'binary'),
    'Compare with the penalty tuned by nested cross-validation');
  // The v0.2b single value keeps its words.
  assert.equal(en.value('model_variant', '{"kind": "regularisation", "strength": "weak"}', 'binary'),
    'Compare with a less regularised variant');
  assert.equal(en.modelName('fit.variant:3', 'binary'), 'the third variant');
  delete globalThis.Hypotrail;
});

// --- the extension's words in French ------------------------------------------------------------

test('every refusal explanation and detail line has its French text, in the "vous" register', () => {
  const keys = [...Object.keys(refusals.BY_REASON).map(r => ['reason', r]), ...Object.keys(refusals.BY_CODE).map(c => ['code', c])];
  for (const [kind, key] of keys) {
    const fr = kind === 'reason' ? refusals.BY_REASON_FR[key] : refusals.BY_CODE_FR[key];
    assert.ok(typeof fr === 'string' && fr.length > 10, `${kind} ${key}`);
  }
  for (const [ctx, table] of Object.entries(refusals.BY_CONTEXT)) {
    assert.deepEqual(Object.keys(refusals.BY_CONTEXT_FR[ctx]).sort(), Object.keys(table).sort(), ctx);
  }
  const all = [...Object.values(refusals.BY_REASON_FR), ...Object.values(refusals.BY_CODE_FR),
    ...Object.values(refusals.BY_CONTEXT_FR).flatMap(t => Object.values(t)), refusals.OLDER_ENGINE_EXPORT_FR,
    ...Object.values(l10n.FR).map(v => (typeof v === 'function' ? v('Xa', 'Xb', 'Xc') : v))];
  const TU = /(^|[\s'’(«])(tu|toi|ton|ta|tes|te|t['’])(?=[\s,.;:!?»)]|$)/i;
  for (const s of all) assert.doesNotMatch(s, TU, s);
  const d = refusals.describe({ command: 'decide', error: { code: 'decision_on_hold', message: 'on hold',
    details: { notes: [{ note_id: 'n_1', user_words: 'wait' }] } } });
  assert.equal(d.human, `${refusals.BY_CODE.decision_on_hold} ${refusals.NOTHING}`);
  assert.equal(d.humanFr, `${refusals.BY_CODE_FR.decision_on_hold} ${refusals.NOTHING_FR}`);
  assert.deepEqual(d.details, ['On hold (n_1): "wait"']);
  assert.deepEqual(d.detailsFr, ['En suspens (n_1) : « wait »']);
});

test('the extension\'s words follow the language setting, else the study language', async () => {
  assert.equal(l10n.resolve('fr', 'en'), 'fr');
  assert.equal(l10n.resolve('auto', 'fr'), 'fr');
  assert.equal(l10n.resolve('auto', null, 'fr-FR'), 'fr');
  assert.equal(l10n.resolve('auto', null, 'en-US'), 'en');
  assert.deepEqual(Object.keys(l10n.FR).sort(), Object.keys(l10n.EN).sort());
  // A notice of a handler in a French setting: "go to a result" with an unknown prefix.
  const { c, of } = make({ settings: { stage: 'v2', language: 'fr' } });
  await c.handle({ v: 2, type: 'ready' });
  await c.command('go_to_result', { prefix: 'abcdef0123' });
  assert.equal(c.language(), 'fr');
  assert.match(of('notice').at(-1).text, /^Aucun résultat de cette étude ne commence par abcdef0123\./);
  // Auto, English study: unchanged English.
  const en = make({ settings: { stage: 'v2' } });
  await en.c.handle({ v: 2, type: 'ready' });
  await en.c.command('go_to_result', { prefix: 'abcdef0123' });
  assert.match(en.of('notice').at(-1).text, /^No result of this study starts with abcdef0123\./);
});
