'use strict';
// Currency of the cache (decision CR.1, COMPANION-ADVANCED §5, §11): a cached read is
// valid for one (revision, currency) of the summary, not for a revision alone. `currency`
// is the engine's digest (`status --summary --digest`, root field `currency`) when the
// engine sends one, else a digest the controller computes from the summary fields that
// carry currency (artefact statuses and messages, the not-yet-defensible items, the
// result slots' current, integrity and stale reason, `sources_changed`). Both paths are
// tested. An explicit Refresh and every write also empty the non-preview cache.

const test = require('node:test');
const assert = require('node:assert/strict');
const { createController } = require('../lib/controller');
const { currencyOf } = require('../lib/models/summary');
const { fakeCli, payload } = require('./fixture-cli');

const AGENT = { argv: ['/opt/py/bin/python', '-m', 'mlkit.study.cli'], studyDir: '/studies/bank' };
const clone = x => JSON.parse(JSON.stringify(x));
/** The summary fixture as an engine without `status --summary --digest` sends it: no root `currency`. */
const withoutCurrency = () => { const s = payload('summary.binary'); delete s.currency; return s; };

/** A controller whose summary is whatever `summary.current` holds when it is read. */
function make({ stage = 'v2', engineCurrency = true } = {}) {
  const summary = { current: engineCurrency ? payload('summary.binary') : withoutCurrency() };
  const posted = [];
  const runCli = fakeCli(tail => (tail[0] === 'status' ? { payload: clone(summary.current) } : undefined), { agentArgv: AGENT.argv });
  const c = createController({ agent: AGENT, post: m => posted.push(m), runCli, settings: { stage },
    exists: () => true, uuid: () => '0f8fad5b-d9cb-469f-a165-70867728950e', host: { confirmModal: async () => true } });
  const count = command => runCli.calls.filter(x => x.tail[0] === command).length;
  return { c, posted, runCli, summary, count, last: type => posted.filter(m => m.type === type).at(-1) };
}

test('currencyOf: the engine digest when present, else a stable digest of the currency fields', () => {
  assert.equal(currencyOf(payload('summary.binary')), payload('summary.binary').currency, 'the captured engine digest is used');
  const base = withoutCurrency();
  const own = currencyOf(base);
  assert.match(own, /^[0-9a-f]{16}$/);
  assert.equal(currencyOf(clone(base)), own, 'stable for the same summary');
  assert.equal(currencyOf({ ...base, currency: '0a1b2c3d4e5f6789' }), '0a1b2c3d4e5f6789', 'the engine digest wins');
  assert.match(currencyOf({ ...base, currency: 'Not Hex!' }), /^[0-9a-f]{16}$/, 'a malformed engine digest is hashed, not trusted as is');
  const variants = {
    'a report status': s => { s.artifacts.items.report.status = 'stale'; },
    'a report message': s => { s.artifacts.items.report.message = 'The report was edited.'; },
    'an alert': s => { s.not_yet_defensible.top.push({ id: 'sources_changed', text: 'The dataset changed.' }); },
    'sources_changed': s => { s.sources_changed = true; },
    'a result that stops being current': s => { const k = Object.keys(s.results)[0]; s.results[k].current = false; },
    'a result integrity': s => { const k = Object.keys(s.results)[0]; s.results[k].integrity = 'mismatch'; },
  };
  for (const [name, change] of Object.entries(variants)) {
    const s = clone(base);
    change(s);
    assert.notEqual(currencyOf(s), own, name);
    assert.equal(s.revision, base.revision, 'same revision');
  }
});

test('H1, engine path: a new engine currency at the same revision re-reads a cached view; the reply carries it', async () => {
  const { c, posted, summary, count } = make();
  summary.current = { ...payload('summary.binary'), currency: '00000000000000aa' };
  await c.handle({ v: 2, type: 'ready' });
  assert.equal(posted.find(m => m.type === 'snapshot').model.currency, '00000000000000aa');
  await c.handle({ v: 2, type: 'load', view: 'decisions' });
  await c.handle({ v: 2, type: 'load', view: 'decisions' });
  assert.equal(count('decisions'), 1, 'cached at one (revision, currency)');
  assert.equal(posted.filter(m => m.type === 'view_data').at(-1).currency, '00000000000000aa');
  summary.current = { ...summary.current, currency: '00000000000000bb' };
  await c.refresh();   // a watch event, not the explicit Refresh
  await c.handle({ v: 2, type: 'load', view: 'decisions' });
  assert.equal(count('decisions'), 2, 'the new currency is a new cache key');
  assert.equal(posted.filter(m => m.type === 'view_data').at(-1).currency, '00000000000000bb');
  assert.equal(c.snapshot().revision, payload('summary.binary').revision);
});

test('H1, fallback path: an engine without `currency` — a dataset edit (alert), a deleted report (status), a result no longer current', async () => {
  const changes = [
    s => { s.not_yet_defensible.top.unshift({ id: 'sources_changed', text: 'The case or dataset file changed since the study started.' }); },
    s => { s.artifacts.items.report.status = 'missing'; s.artifacts.items.report.message = 'The report is missing.'; },
    s => { for (const r of Object.values(s.results)) r.current = false; },
  ];
  for (const change of changes) {
    const { c, summary, count, posted } = make({ engineCurrency: false });
    assert.equal(summary.current.currency, undefined, 'the fixture is an engine without the field');
    await c.handle({ v: 2, type: 'ready' });
    await c.handle({ v: 2, type: 'load', view: 'evidence' });
    await c.handle({ v: 2, type: 'load', view: 'check' });
    const before = posted.filter(m => m.type === 'view_data').at(-1).currency;
    assert.match(before, /^[0-9a-f]{16}$/);
    const s = clone(summary.current);
    change(s);
    summary.current = s;
    await c.refresh();
    await c.handle({ v: 2, type: 'load', view: 'evidence' });
    await c.handle({ v: 2, type: 'load', view: 'check' });
    assert.equal(count('evidence'), 2);
    assert.equal(count('check'), 2);
    assert.notEqual(posted.filter(m => m.type === 'view_data').at(-1).currency, before);
  }
});

test('H1: effects:<pid> are re-read when the currency changes at the same revision, and carry it', async () => {
  const { c, summary, runCli, last } = make({ stage: 'v1' });
  await c.handle({ v: 2, type: 'ready' });
  const pid = c.snapshot().proposals[0].proposalId;
  const effects = () => runCli.calls.filter(x => x.tail[0] === 'preview' && x.tail[1] === 'effects').length;
  await c.handle({ v: 2, type: 'preview_effects', proposalId: pid, revision: c.snapshot().revision });
  await c.handle({ v: 2, type: 'preview_effects', proposalId: pid, revision: c.snapshot().revision });
  assert.equal(effects(), 1);
  const first = last('effects').currency;
  summary.current = { ...summary.current, currency: '00000000000000cc' };
  await c.refresh();
  await c.handle({ v: 2, type: 'preview_effects', proposalId: pid, revision: c.snapshot().revision });
  assert.equal(effects(), 2);
  assert.equal(last('effects').currency, '00000000000000cc');
  assert.notEqual(first, '00000000000000cc');
});

test('H1: the explicit Refresh empties the non-preview cache (same revision, same currency); previews stay', async () => {
  const { c, count, runCli } = make();
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'load', view: 'check' });
  const preview = () => runCli.calls.filter(x => x.tail[0] === 'preview' && x.tail[1] === 'policy').length;
  const argv = c.context.cli.previewPolicyArgv(AGENT, { rules: ['capacity:100'] });
  await c.context.read('preview:capacity:100:points', argv, p => p);
  await c.refresh();   // a watch event: the cache stays
  await c.handle({ v: 2, type: 'load', view: 'check' });
  assert.equal(count('check'), 1);
  await c.handle({ v: 2, type: 'refresh' });
  await c.handle({ v: 2, type: 'load', view: 'check' });
  assert.equal(count('check'), 2, 'read again after the explicit Refresh');
  await c.context.read('preview:capacity:100:points', argv, p => p);
  assert.equal(preview(), 1, 'a preview of the same (revision, currency) is still cached');
});

test('H1: every write empties the non-preview cache, even when the summary does not move (W5, W7)', async () => {
  const { c, count } = make({ stage: 'v3' });
  await c.handle({ v: 2, type: 'ready' });
  await c.handle({ v: 2, type: 'load', view: 'check' });
  await c.handle({ v: 2, type: 'render' });
  await c.handle({ v: 2, type: 'load', view: 'check' });
  assert.equal(count('check'), 2, 'read again after W5');
  await c.context.write('W7', { argv: () => c.context.cli.exportArgv(AGENT, { parent: '/tmp/packs', revision: 26 }) });
  await c.handle({ v: 2, type: 'load', view: 'check' });
  assert.equal(count('check'), 3, 'read again after W7');
});
