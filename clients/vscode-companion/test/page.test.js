'use strict';
// The page model (ADR 0004 decision 13; COMPANION-ADVANCED §6, §9 `PageModel`): which block of
// the one page holds what, on the five states of the approved mockup (contract P1 fixtures,
// test/fixtures/captured/summary.regression.<state>, captured from the engine, E-8) and on the captured payloads of
// an older engine. Scope U: a pure function, no process, no browser.

const test = require('node:test');
const assert = require('node:assert/strict');
const { payload } = require('./fixture-cli');
const { toSummaryModel } = require('../lib/models/summary');
const P = require('../lib/models/page');

const STATES = ['step1', 'choice', 'reopened', 'review', 'done'];
const summary = name => toSummaryModel(payload(name));
const page = (name, stage = 'v3', more = {}) => P.toPageModel(summary(name), { stage, lang: 'en', ...more });
const steps = pm => pm.path.phases.flatMap(ph => ph.steps);

test('OP-1, PG-1, NOW-1: Now follows the engine\'s next action; one current step; every plan step once, in plan order', () => {
  const want = { step1: ['data_card', 'discover_data'], choice: ['choice', 'model_choice'], reopened: ['reopened', 'preprocessing'],
    review: ['review', 'prediction_time'], done: ['done', null] };
  for (const name of STATES) {
    const s = summary(`captured/summary.regression.${name}`);
    const pm = P.toPageModel(s, { stage: 'v3', lang: 'en' });
    assert.deepEqual([pm.now.kind, pm.now.step], want[name], name);
    // PATH-4: every plan step appears once, in plan order; exactly one is current except at the end.
    assert.deepEqual(steps(pm).map(x => x.id), s.plan.map(x => x.id), name);
    assert.equal(steps(pm).filter(x => x.state === 'current').length, name === 'done' ? 0 : 1, name);
    // NOW-2: the question and the options are the engine's texts, in the chat's order.
    if (name !== 'done') assert.equal(pm.now.question.text, s.texts.en.question, name);
    assert.deepEqual(pm.now.options.map(o => o.id), s.texts.en.options.map(o => o.id), name);
    if (name !== 'done') assert.equal(P.toPageModel(s, { stage: 'v3', lang: 'fr' }).now.question.text, s.texts.fr.question, `${name} fr`);
    // At the end the engine asks nothing (CLI-CONTRACT §17.2.3: `question` null).
    else assert.equal(s.texts.fr.question, null);
  }
  // NOW-5: a reopened decision is Now ("First: ...") although the junior was at a later step.
  assert.equal(page('captured/summary.regression.reopened').now.first, true);
  // NOW-10: the next line names the next step not done; none at the end.
  assert.equal(page('captured/summary.regression.step1').now.next.id, 'prediction_time');
  assert.equal(page('captured/summary.regression.done').now.next, null);
});

test('TODO-1, NOW-13: To handle holds only what lies outside the current step; the stale step waits below Now', () => {
  for (const name of ['step1', 'choice', 'reopened', 'review', 'done']) assert.deepEqual(page(`captured/summary.regression.${name}`).todo, [], name);
  // The reopened preparation is Now's, never To handle's; the next step waits, stale, with why and without figures.
  const pm = page('captured/summary.regression.reopened');
  assert.deepEqual(pm.waiting.map(w => [w.step, w.stale]), [['models', true]]);
  assert.deepEqual(pm.waiting[0].reasons, ['preprocessing changed']);
  assert.deepEqual(pm.waiting[0].unknown, []);
  // The same study once a run was interrupted: the engine's next action is the interruption (it
  // comes first), so Now says so; To handle holds the run and the deliverables it made stale.
  const stopped = page('captured/summary.regression.interrupted');
  assert.deepEqual([stopped.now.kind, stopped.now.question], ['execution', null]);
  assert.deepEqual(stopped.todo.map(t => t.anchor), ['todo:execution', 'todo:deliverables']);
  assert.equal(stopped.todo[0].runs[0].activity, 'eda.distribution');
  assert.deepEqual(stopped.waiting, [], 'Waiting cards follow a reopened Now only');
  // Regenerate is offered from v1 only (W5).
  assert.equal(page('captured/summary.regression.interrupted', 'v0').todo[1].regenerate, false);
  assert.equal(page('captured/summary.regression.interrupted', 'v1').todo[1].regenerate, true);
});

test('PATH-2, PATH-3, PATH-6, HON-3: phases fold by their state; automatic decisions and computations are told apart, never done', () => {
  const kinds = pm => Object.fromEntries(pm.path.phases.map(ph => [ph.moment, ph.kind]));
  assert.deepEqual(kinds(page('captured/summary.regression.step1')), { frame: 'open', evidence: 'later', compare: 'later', conclude: 'later' });
  assert.deepEqual(kinds(page('captured/summary.regression.choice')), { frame: 'done', evidence: 'done', compare: 'open', conclude: 'later' });
  assert.deepEqual(kinds(page('captured/summary.regression.done')), { frame: 'done', evidence: 'done', compare: 'done', conclude: 'done' });
  const review = page('captured/summary.regression.review');
  const states = steps(review).reduce((acc, x) => ({ ...acc, [x.state]: (acc[x.state] || 0) + 1 }), {});
  // The mockup's `auto` state: seven automatic decisions (one under review is Now's), three computations.
  assert.equal(states.auto, 6);
  assert.equal(steps(review).find(x => x.id === 'prediction_time').decision.basis, 'automatic');
  assert.equal(states.computed, 3);
  assert.ok(steps(review).filter(x => x.decision && x.decision.basis === 'automatic').every(x => x.state !== 'done'));
  assert.deepEqual(kinds(review), { frame: 'open', evidence: 'open', compare: 'open', conclude: 'later' });
  // The reopened state: the preparation to confirm again, the models and variants stale.
  const reopened = page('captured/summary.regression.reopened');
  const by = Object.fromEntries(steps(reopened).map(x => [x.id, x]));
  assert.equal(by.preprocessing.state, 'current');
  assert.ok(by.preprocessing.flags.includes('again'));
  assert.equal(by.models.state, 'stale');
  assert.equal(reopened.path.phases.find(p => p.moment === 'compare').counts.stale, 3);
  // The interruption does not change the path: the preparation stays to confirm again.
  const stopped = Object.fromEntries(steps(page('captured/summary.regression.interrupted')).map(x => [x.id, x]));
  assert.ok(stopped.preprocessing.flags.includes('again'));
});

test('PG-9, PG-6, PG-7, HON-5: the progress counts the review; the pills come from the engine only', () => {
  const review = page('captured/summary.regression.review');
  assert.equal(review.progress.mode, 'review');
  assert.deepEqual([review.progress.k, review.progress.n], [1, 7]);
  assert.ok(review.progress.groups[0].segments.every(s => s.state !== 'done'), 'no automatic decision counted done');
  assert.deepEqual(review.header.automation, { state: 'ended', variant: 'until_final_test' });
  assert.equal(review.header.defensibility.kind, 'warn');
  assert.equal(page('captured/summary.regression.step1').header.defensibility.kind, 'pending');
  assert.equal(page('captured/summary.regression.done').header.defensibility.kind, 'limits');
  assert.equal(page('captured/summary.regression.done').header.seal.kind, 'opened');
  assert.equal(page('captured/summary.regression.step1').progress.index, 1);
  // HON-9: an older engine (no `defensibility`, no P1 key) gives the neutral fallback, its ids in the engine's order.
  const raw = payload('summary.binary');
  for (const key of ['panel_contract', 'automation', 'review_queue', 'defensibility', 'ledger', 'sample', 'headlines',
    'criterion_configurations']) delete raw[key];
  const s = toSummaryModel(raw);
  const old = P.toPageModel(s, { stage: 'v3', lang: 'en' });
  assert.equal(old.header.defensibility.kind, 'fallback');
  assert.deepEqual(old.header.defensibility.items.map(i => i.id), [...s.notYetDefensible.top.map(i => i.id), ...s.notYetDefensible.more]);
  assert.equal(old.header.automation, null);
  assert.equal(old.path.ledger, null);
});

test('§3.2, PG-12: what a stage does not offer is absent from the page model', () => {
  const at = stage => page('captured/summary.regression.choice', stage);
  assert.deepEqual(at('v0').tools.map(t => t.id), ['deliverables']);
  assert.deepEqual(at('v2').tools.map(t => t.id), ['data', 'whatif', 'deliverables']);
  assert.deepEqual(at('v3').tools.map(t => t.id), ['data', 'whatif', 'notions', 'deliverables']);
  assert.deepEqual(page('captured/summary.regression.choice', 'v3', { learningLayer: false }).tools.map(t => t.id), ['data', 'whatif', 'deliverables']);
  assert.equal(at('v0').now.effects, null, 'no effects at v0');
  assert.equal(at('v0').now.criterion, null, 'no figure below v2');
  assert.equal(at('v2').now.criterion, 'configurations');
  assert.equal(at('v0').since, false);
  assert.equal(at('v1').since, true);
  assert.equal(page('captured/summary.regression.step1', 'v1').now.dataCard, 'stage_line');
  assert.equal(page('captured/summary.regression.step1', 'v2').now.dataCard, 'card');
  assert.ok(!at('v1').anchors.some(a => /^path:[a-z_]+\//.test(a)), 'no figure anchor below v2');
  assert.ok(at('v2').anchors.includes('path:train_eda/eda.mean_by:model_year'));
});

test('PG-13: every anchor the engine names for a payload (CLI-CONTRACT §17.1.2, §17.1.3 with its stage fallback) is on the page', () => {
  const where = kind => (['outcome_unknown', 'acknowledge_interruption'].includes(kind) ? 'todo:execution' : 'now');
  const fallback = (anchor, stage) => {
    if (/^path:[a-z_]+\//.test(anchor) && !['v2', 'v3'].includes(stage)) return anchor.split('/')[0];
    if (/^tools:(data|whatif)$/.test(anchor) && ['v0', 'v1'].includes(stage)) return 'now';
    return anchor;
  };
  for (const name of [...STATES.map(n => `captured/summary.regression.${n}`), 'summary.binary', 'summary.regression', 'summary.binary.health']) {
    const s = summary(name);
    for (const stage of ['v0', 'v1', 'v2', 'v3']) {
      const pm = P.toPageModel(s, { stage, lang: 'en' });
      assert.ok(pm.anchors.every(a => P.ANCHOR_RE.test(a)), `${name} ${stage}: the grammar`);
      const anchor = fallback(where(s.nextAction.kind), stage);
      assert.ok(pm.anchors.includes(anchor), `${name} ${stage}: ${anchor}`);
      // `shown` of a promoted run of another step: the figure of that result (§17.1.3).
      for (const slot of Object.keys(s.results)) {
        const step = P.stepOf(slot, s.plan.map(p => p.id));
        if (step) assert.ok(pm.anchors.includes(fallback(`path:${step}/${slot}`, stage)), `${name} ${stage}: ${slot}`);
      }
      assert.ok(s.plan.every(p => pm.anchors.includes(`path:${p.id}`)), `${name} ${stage}: every step line`);
    }
  }
});

test('§17.1.1, §4.3, NAV-2: a result is filed under its step; a link to it resolves to that figure', () => {
  const plan = summary('captured/summary.regression.choice').plan.map(p => p.id);
  const want = { split: 'split', 'eda.quality': 'structural_eda', 'eda.correlation': 'structural_eda', 'eda.distribution:weight': 'structural_eda',
    'eda.mean_by:model_year': 'train_eda', 'eda.target_summary': 'train_eda', 'fit.baseline': 'models', 'fit.linear': 'models',
    'fit.variant': 'model_variant', 'evaluate.regression': 'model_choice', 'final_test.evaluation': 'final_test' };
  for (const [slot, step] of Object.entries(want)) assert.equal(P.stepOf(slot, plan), step, slot);
  const s = summary('captured/summary.regression.choice');
  assert.equal(P.anchorOfResult(s, s.results['eda.mean_by:model_year'].resultId), 'path:train_eda/eda.mean_by:model_year');
  // NAV-2: a stale result resolves the same way; its step line lists it without figures.
  const r = summary('captured/summary.regression.reopened');
  assert.equal(r.results['fit.variant'].current, false);
  assert.equal(P.anchorOfResult(r, r.results['fit.variant'].resultId), 'path:model_variant/fit.variant');
  assert.equal(P.anchorOfResult(s, 'f'.repeat(64)), 'path', 'unknown: the path\'s head');
});

test('PATH-1, PATH-7, SINCE-3: the ledger counts, the channel of each result, and the end\'s journey are the engine\'s', () => {
  const choice = page('captured/summary.regression.choice');
  assert.deepEqual(choice.path.ledger.targetLooks, payload('captured/summary.regression.choice').ledger.target_looks);
  assert.deepEqual(choice.path.ledger.targetLooks, { eda: 5, sample: 1, total: 6 });
  const explore = steps(choice).find(x => x.id === 'train_eda');
  assert.equal(explore.results.find(r => r.slot === 'eda.mean_by:model_year').channel, 'webview');
  const done = page('captured/summary.regression.done');
  assert.deepEqual(done.journey, { steps: 13, ownWords: 9, looks: 6, openings: 1 });
  assert.equal(done.path.ledger.finalTest.openings, 1);
});
