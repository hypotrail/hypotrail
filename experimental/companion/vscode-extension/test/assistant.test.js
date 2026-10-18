'use strict';
// Real Python engine with a simulated model: node --test test/*.test.js
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');
const { createEngine } = require('../engine');
const { createAssistant } = require('../assistant');
const { buildMessages } = require('../prompt');
const { createRouter } = require('../router');
const { createFakeProvider } = require('./fake-provider');
const markdown = require(path.join(__dirname, '../../runtime/markdown.js'));

const SOURCE = path.resolve(__dirname, '../../runtime');
const PYTHON = [path.join(SOURCE, '.venv/bin/python')].find(fs.existsSync) || 'python3';
const BANK = 'uci-bank-marketing-v1', MPG = 'uci-auto-mpg-v1';
const RESULTS = JSON.parse(fs.readFileSync(path.join(SOURCE, 'projects/bank-marketing/results.json'), 'utf8'));
const selection = t => RESULTS.results.find(r => r.id === `selection-${t.toFixed(2)}`).metrics;
const contextOf = call => JSON.parse(/```json\n([\s\S]*)\n```/.exec(call.messages[1].content)[1]);
const wait = ms => new Promise(r => setTimeout(r, ms));

function setup(script = {}, { db: dbPath, project = BANK, posts = [] } = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'osml-ai-'));
  const db = dbPath || path.join(dir, 'session.sqlite');
  // Shared machines can be busy: allow a generous timeout in tests only.
  const engine = createEngine({ python: PYTHON, bridge: path.join(SOURCE, 'bridge.py'), db, project, cwd: dir, timeoutMs: 60000 });
  const log = [];
  const run = async request => { log.push(request.action); return engine.run(request); };
  const provider = createFakeProvider(script);
  const assistant = createAssistant({ engine: run, provider, post: m => posts.push(m), projectId: project });
  let n = 0;
  async function register(answers, activity = 'selection') {
    const s = await run({ action: 'status' });
    return run({ action: 'submit', event: { protocol_version: 1, event_id: `ev${++n}${Date.now()}`, session_id: s.session_id, expected_revision: s.revision,
      context_hash: s.context_hash, type: 'submit_state', payload: { state: { activity, answers } } } });
  }
  async function applyExplain(answers, extra = {}) {
    const s = await register(answers, extra.activity || 'selection');
    return assistant.ops['apply-explain']({ eventId: s.pending_event_id, expectedRevision: s.revision, contextHash: s.context_hash, activity: 'selection', key: 'threshold', ...extra });
  }
  async function finished(exchangeId, timeout = 60000) {
    const until = Date.now() + timeout;
    while (Date.now() < until) {
      const done = posts.find(m => m.event === 'finished' && m.exchange.exchange_id === exchangeId);
      if (done) return done;
      await wait(10);
    }
    throw new Error('Response not completed: ' + exchangeId);
  }
  const status = () => run({ action: 'status' });
  return { dir, db, engine, run, log, provider, posts, assistant, register, applyExplain, finished, status };
}

const ask = (t, s, extra) => t.assistant.ops.ask({ question: 'What does this result mean?', activity: 'selection', subject: 'applied', contextHash: s.context_hash,
  expectedApplicationEventId: s.application?.event_id ?? null, ...extra });

test('1. successful application precedes the model call', async () => {
  let seen;
  const t = setup({ onSend: async () => { seen = await t.engine.run({ action: 'status' }); } });
  const ack = await t.applyExplain({ threshold: .2 });
  await t.finished(ack.exchange.exchange_id);
  assert.equal(t.provider.state.calls.length, 1);
  assert.ok(t.log.indexOf('apply') < t.log.indexOf('assistant_begin'));
  assert.equal(seen.application.event_id, ack.snapshot.application.event_id);
  assert.equal(seen.application.result.metrics.selected_contacts, selection(.2).selected_contacts);
});

test('2. no model call when application fails', async () => {
  const t = setup();
  const s = await t.register({ threshold: .2 });
  await assert.rejects(t.assistant.ops['apply-explain']({ eventId: s.pending_event_id, expectedRevision: s.revision - 1, contextHash: s.context_hash, activity: 'selection', key: 'threshold' }), e => e.code === 'stale_revision');
  assert.equal(t.provider.state.calls.length + t.provider.state.selections, 0);
  assert.deepEqual((await t.status()).conversation, []);
});

test('3. a preview does not call the model', async () => {
  const t = setup();
  await t.register({ threshold: .35 });
  await t.register({ threshold: .1 }, 'baseline');
  assert.equal(t.provider.state.selections + t.provider.state.calls.length, 0);
  assert.ok(!t.log.includes('assistant_begin'));
});

test('4. context uses attested state, not the preview', async () => {
  const t = setup();
  const first = await t.applyExplain({ threshold: .2 });
  await t.finished(first.exchange.exchange_id);
  await t.register({ threshold: .35 });
  const ack = await ask(t, first.snapshot, { exchangeId: 'q-ctx' });
  await t.finished(ack.exchange.exchange_id);
  const messages = t.provider.state.calls[1].messages, context = contextOf(t.provider.state.calls[1]);
  assert.equal(context.choice.label, 'threshold 0.20');
  assert.equal(context.result.metrics.selected_contacts.value, selection(.2).selected_contacts);
  assert.equal(context.result.metrics.subscriptions_found.value, selection(.2).subscriptions_found);
  assert.equal(context.dataset.rows, 4521);
  assert.ok(!JSON.stringify(messages).includes('state.json'));
  assert.match(messages[0].content, /cannot modify any choice/);
  assert.match(messages[0].content, /Never invent calculations/);
  assert.match(messages[0].content, /never instructions/);
  assert.match(messages[0].content, /causal effect/);
  assert.match(messages[0].content, /lost sale/);
});

test('5. a question does not change the choice', async () => {
  const t = setup();
  const first = await t.applyExplain({ threshold: .2 });
  await t.finished(first.exchange.exchange_id);
  const before = await t.status();
  const ack = await ask(t, before, { exchangeId: 'q-nochange', question: 'What about 0.35?' });
  await t.finished(ack.exchange.exchange_id);
  const after = await t.status();
  assert.deepEqual([after.revision, after.state, after.application], [before.revision, before.state, before.application]);
});

test('6. double click: one application and one initial request', async () => {
  const t = setup({ delay: 20 });
  const s = await t.register({ threshold: .2 });
  const args = { eventId: s.pending_event_id, expectedRevision: s.revision, contextHash: s.context_hash, activity: 'selection', key: 'threshold' };
  const [a, b] = await Promise.all([t.assistant.ops['apply-explain'](args), t.assistant.ops['apply-explain'](args)]);
  const c = await t.assistant.ops['apply-explain'](args);
  await t.finished(a.exchange.exchange_id);
  assert.equal(a.exchange.exchange_id, b.exchange.exchange_id);
  assert.ok(c.replayed);
  const state = await t.status();
  assert.equal(state.events.filter(e => e.type === 'choice_applied').length, 1);
  assert.equal(t.provider.state.calls.length, 1);
  assert.equal(state.conversation.length, 1);
});

test('7. a late response does not replace the new choice explanation', async () => {
  const t = setup({ plans: [{ delay: 400, ignoreAbort: true, chunks: ['ancien 1 ', 'ancien 2 ', 'ancien 3 ', 'ancien 4 ', 'ancien 5 ', 'ancien 6 '] }, { delay: 5, chunks: ['must be new'] }] });
  const old = await t.applyExplain({ threshold: .2 });
  while (!t.posts.some(m => m.event === 'delta')) await wait(5);
  const fresh = await t.applyExplain({ threshold: .35 });
  const doneOld = await t.finished(old.exchange.exchange_id);
  const doneNew = await t.finished(fresh.exchange.exchange_id);
  await wait(2600);
  assert.equal(doneOld.exchange.status, 'cancelled');
  assert.equal(doneOld.current, false);
  assert.equal(doneNew.current, true);
  assert.equal(doneNew.exchange.answer, 'must be new');
  const finishedAt = t.posts.findIndex(m => m.event === 'finished' && m.exchange.exchange_id === old.exchange.exchange_id);
  assert.ok(!t.posts.slice(finishedAt).some(m => m.event === 'delta' && m.exchangeId === old.exchange.exchange_id));
  const stored = (await t.status()).conversation;
  assert.ok(!stored.find(x => x.exchange_id === old.exchange.exchange_id).answer.includes('ancien 6'));
  assert.ok(t.provider.state.calls[0].afterAbort > 0, 'the simulated provider actually emitted delayed fragments');
  assert.equal(stored.find(x => x.current && x.kind === 'initial').exchange_id, fresh.exchange.exchange_id);
});

test('8. changed preview does not change the applied-choice explanation', async () => {
  const t = setup();
  const ack = await t.applyExplain({ threshold: .2 });
  await t.finished(ack.exchange.exchange_id);
  await t.register({ threshold: .35 });
  const s = await t.status();
  assert.equal(s.conversation[0].current, true);
  assert.equal(s.conversation[0].choice.label, 'threshold 0.20');
  const q = await ask(t, s, { exchangeId: 'q-preview', question: 'What about this preview?', subject: 'preview', previewValue: .35 });
  await t.finished(q.exchange.exchange_id);
  const context = contextOf(t.provider.state.calls[1]);
  assert.equal(context.subject, 'preview');
  assert.equal(context.choice.applied, false);
  assert.match(context.result.origin, /NOT applied/);
  assert.equal(context.applied_choice.label, 'threshold 0.20');
  assert.match(t.provider.state.calls[1].messages[0].content, /UNAPPLIED PREVIEW/);
  assert.equal((await t.status()).application.event_id, ack.snapshot.application.event_id);
});

test('9. navigation does not invalidate a correct explanation', async () => {
  const t = setup();
  const ack = await t.applyExplain({ threshold: .2 });
  await t.finished(ack.exchange.exchange_id);
  await t.register({ threshold: .2 }, 'use');
  await t.register({ threshold: .2 }, 'constraints');
  const s = await t.status();
  assert.ok(s.revision > ack.snapshot.revision);
  assert.equal(s.conversation[0].current, true);
});

test('10. cancellation labels partial text incomplete', async () => {
  const t = setup({ delay: 80, chunks: ['un ', 'deux ', 'trois ', 'quatre ', 'cinq '] });
  const ack = await t.applyExplain({ threshold: .2 });
  while (!t.posts.some(m => m.event === 'delta')) await wait(5);
  assert.deepEqual(await t.assistant.ops.stop({ exchangeId: ack.exchange.exchange_id }), { stopped: true });
  const done = await t.finished(ack.exchange.exchange_id);
  assert.equal(done.exchange.status, 'interrupted');
  assert.equal(done.exchange.error_code, 'stopped');
  assert.ok(done.exchange.answer.length > 0 && !done.exchange.answer.includes('cinq'));
});

for (const [name, script, code] of [
  ['quota', { error: { code: 'quota', message: 'Quota reached' } }, 'quota'],
  ['access denied', { error: { code: 'access_denied', message: 'Refused' } }, 'access_denied'],
  ['no model', { selectError: { code: 'no_model', message: 'No model' } }, 'no_model'],
  ['stream interruption', { failAt: 1, chunks: ['start ', 'suite'], error: { code: 'network', message: 'Network disconnected' } }, 'network']
]) {
  test(`11-12. ${name} : explicit error, choice and result retained`, async () => {
    const t = setup(script);
    const ack = await t.applyExplain({ threshold: .2 });
    const done = await t.finished(ack.exchange.exchange_id);
    assert.equal(done.exchange.status, 'error');
    assert.equal(done.exchange.error_code, code);
    const s = await t.status();
    assert.equal(s.application.event_id, ack.snapshot.application.event_id);
    assert.equal(s.application.result.metrics.selected_contacts, selection(.2).selected_contacts);
    assert.ok(s.application.current);
    t.provider.configure({ error: undefined, selectError: undefined, failAt: undefined, chunks: ['ok'] });
    const retried = await t.assistant.ops.retry({ exchangeId: ack.exchange.exchange_id });
    assert.equal(retried.replayed, false);
    const ends = () => t.posts.filter(m => m.event === 'finished' && m.exchange.exchange_id === ack.exchange.exchange_id);
    for (let i = 0; i < 3000 && ends().length < 2; i++) await wait(10);
    const last = ends().pop();
    assert.equal(last.exchange.status, 'completed');
    assert.equal(last.exchange.attempts, 2);
  });
}

test('13. resumption after closing sends no automatic generation', async () => {
  const t = setup({ delay: 400, chunks: ['a', 'b', 'c'] });
  const ack = await t.applyExplain({ threshold: .2 });
  while (!t.log.includes('assistant_update')) await wait(5);
  const restarted = setup({}, { db: t.db });
  const info = await restarted.assistant.ops.info({});
  assert.deepEqual(info.streaming, []);
  const row = (await restarted.status()).conversation.find(x => x.exchange_id === ack.exchange.exchange_id);
  assert.equal(row.status, 'interrupted');
  assert.equal(row.error_code, 'restart');
  assert.equal(restarted.provider.state.calls.length + restarted.provider.state.selections, 0);
  t.assistant.dispose();
});

test('14. migrate an existing session and complete the journey', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'osml-mig-'));
  const db = path.join(dir, 'old.sqlite');
  execFileSync(PYTHON, ['-c', `
import sqlite3,sys
d=sqlite3.connect(sys.argv[1])
d.execute('CREATE TABLE session (id INTEGER PRIMARY KEY, revision INTEGER, payload TEXT, message TEXT)')
d.execute('CREATE TABLE companion_meta (id INTEGER PRIMARY KEY, session_id TEXT, applied TEXT)')
d.execute('CREATE TABLE companion_events (seq INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT UNIQUE,request_hash TEXT,type TEXT,status TEXT,revision INTEGER,payload TEXT,created TEXT)')
d.execute("INSERT INTO session VALUES(1,3,'{\\"answers\\":{\\"goal\\":0},\\"step\\":1}','')")
d.execute("INSERT INTO companion_meta VALUES(1,'legacy',NULL)")
d.commit()`, db]);
  const t = setup({}, { db });
  const before = await t.status();
  assert.equal(before.schema_version, 3);
  assert.equal(before.session_id, 'legacy');
  assert.deepEqual(before.state, { activity: 'use', answers: { goal: 0 }, step: 1 });
  const ack = await t.applyExplain({ goal: 0, threshold: .2 });
  const done = await t.finished(ack.exchange.exchange_id);
  assert.equal(done.exchange.status, 'completed');
  assert.equal((await t.status()).session_id, 'legacy');
});

test('15. export: conversation and choice → application → result → explanation links', async () => {
  const t = setup();
  const ack = await t.applyExplain({ threshold: .2 });
  await t.finished(ack.exchange.exchange_id);
  const out = (await t.run({ action: 'export' })).export;
  const link = out.links.find(l => l.exchange_id === ack.exchange.exchange_id);
  const app = out.applications.find(a => a.event_id === link.choice_event_id);
  assert.equal(app.result.metrics.selected_contacts, selection(.2).selected_contacts);
  assert.equal(link.result_event_id, app.result_event_id);
  assert.equal(out.conversation[0].model.name, 'Simulated model (tests)');
  assert.ok(out.conversation[0].answer.includes('What you selected'));
});

test('16. chat tools coexist without replacing the panel response', async () => {
  const t = setup({ delay: 80, chunks: ['p1 ', 'p2 ', 'p3'] });
  const ack = await t.applyExplain({ threshold: .2 });
  while (!t.posts.some(m => m.event === 'delta')) await wait(5);
  const s = await t.run({ action: 'status' });
  await t.run({ action: 'explain', message: 'From chat.', application_event_id: s.application.event_id, context_hash: s.context_hash, source: 'chat_tool' });
  await t.run({ action: 'explain', message: 'Without a reference.', source: 'chat_tool' });
  const done = await t.finished(ack.exchange.exchange_id);
  assert.equal(done.exchange.answer, 'p1 p2 p3');
  const conv = (await t.status()).conversation;
  assert.deepEqual(conv.map(x => [x.kind, x.subject, x.status]), [['initial', 'applied', 'completed'], ['chat', 'applied', 'published'], ['chat', 'unattached', 'published']]);
});

test('17. regression context uses mpg, no threshold or alerts, and blocks choices before confirmation', async () => {
  const t = setup({}, { project: MPG });
  const s0 = await t.register({ model: 'linear-all' }, 'compare');
  await assert.rejects(t.assistant.ops['apply-explain']({ eventId: s0.pending_event_id, expectedRevision: s0.revision, contextHash: s0.context_hash, activity: 'compare', key: 'model' }), e => e.code === 'blocked');
  assert.equal(t.provider.state.calls.length + t.provider.state.selections, 0);
  await t.run({ action: 'confirm_fact', fact_id: 'prediction_time', decision: 'confirm' });
  const s = await t.status();
  const ack = await t.assistant.ops['apply-explain']({ eventId: s.pending_event_id, expectedRevision: s.revision, contextHash: s.context_hash, activity: 'compare', key: 'model' });
  await t.finished(ack.exchange.exchange_id);
  const context = contextOf(t.provider.state.calls[0]), all = JSON.stringify(t.provider.state.calls[0].messages);
  assert.equal(context.project.problem_type, 'regression');
  assert.equal(context.result.metrics.mae_mpg.unit, 'mpg');
  assert.ok(context.guidance.some(g => /target unit/.test(g)));
  for (const word of ['Bank', 'subscription', 'alerts', 'false_alarms', 'selected contacts']) assert.ok(!all.includes(word), word);
  assert.ok(t.posts.every(m => m.project_id === MPG));
});

test('18. project switching cancels a response without cross-project leakage', async () => {
  const posts = [];
  let active = BANK;
  const panel = [];
  // The panel receives only current-project events (filtering in the'extension et du panneau).
  const deliver = m => { posts.push(m); if (m.project_id === active) panel.push(m); };
  const bank = setup({ delay: 150, ignoreAbort: true, chunks: ['b1 ', 'b2 ', 'b3 ', 'b4 '] }, { posts: { push: deliver } });
  const ack = await bank.applyExplain({ threshold: .2 });
  while (!posts.some(m => m.event === 'delta')) await wait(5);
  bank.assistant.dispose('project_switch');
  active = MPG;
  const switchAt = posts.length, panelAt = panel.length;
  const mpg = setup({}, { project: MPG, posts: { push: deliver } });
  const before = await mpg.status();
  for (let i = 0; i < 3000 && !posts.some(m => m.event === 'finished' && m.exchange.exchange_id === ack.exchange.exchange_id); i++) await wait(10);
  await wait(800);
  const old = posts.find(m => m.event === 'finished' && m.exchange.exchange_id === ack.exchange.exchange_id);
  assert.equal(old.exchange.status, 'cancelled');
  assert.equal(old.exchange.error_code, 'project_switch');
  assert.ok(posts.slice(switchAt).filter(m => m.exchange?.exchange_id === ack.exchange.exchange_id || m.exchangeId === ack.exchange.exchange_id).every(m => m.project_id === BANK));
  assert.ok(panel.slice(panelAt).every(m => m.project_id === MPG));
  assert.ok(!posts.slice(switchAt).some(m => m.event === 'delta' && m.exchangeId === ack.exchange.exchange_id));
  const after = await mpg.status();
  assert.deepEqual(after.conversation, []);
  assert.equal(after.project_id, MPG);
  assert.equal(before.session_id, after.session_id);
  await assert.rejects(setup({}, { db: bank.db, project: MPG }).status(), e => e.code === 'project_mismatch');
});

test('limits: explain long questions and reject requests while busy', async () => {
  const t = setup({ delay: 100, chunks: ['a', 'b', 'c'] });
  const s = await t.status();
  const base = { activity: 'start', subject: 'step', contextHash: s.context_hash };
  await assert.rejects(t.assistant.ops.ask({ ...base, exchangeId: 'q-long', question: 'x'.repeat(4001) }), e => e.code === 'question_too_long' && /4000/.test(e.message));
  const ack = await t.assistant.ops.ask({ ...base, exchangeId: 'q-one', question: 'Bonjour' });
  await assert.rejects(t.assistant.ops.ask({ ...base, exchangeId: 'q-two', question: 'Encore' }), e => e.code === 'busy');
  await t.finished(ack.exchange.exchange_id);
  assert.equal(t.provider.state.calls.length, 1);
});

test('history contains at most 10 exchanges with alternating roles', () => {
  const history = Array.from({ length: 10 }, (_, i) => ({ kind: 'question', question: 'Q' + i, answer: 'R' + i, about: 'threshold 0.20', still_current: true }));
  const messages = buildMessages({ request: { kind: 'question', question: 'Latest', junior: true }, subject: 'applied', choice: { label: 'threshold 0.20' }, activity: { title: 'From score to action' }, history });
  assert.equal(messages.length, 2 + 20 + 1);
  assert.equal(messages[3].role, 'assistant');
  assert.match(messages.at(-1).content, /Latest/);
  assert.ok(!messages[1].content.includes('"history"'));
  for (const word of ['Bank', 'subscription', 'threshold', 'alert']) assert.ok(!messages[0].content.includes(word), word);
});

test('safe Markdown: no raw HTML or active links', () => {
  const blocks = markdown.parse('**Gras** <img src=x onerror=alert(1)>\n- [lien](javascript:alert(1))\n- `code`');
  const flat = JSON.stringify(blocks);
  assert.ok(flat.includes('<img src=x onerror=alert(1)>'));
  assert.equal(blocks[0].inlines[0].type, 'strong');
  assert.equal(blocks[1].items[0][0].text, 'lien (javascript:alert(1))');
  assert.ok(!/"type":"(a|html)"/.test(flat));
});

test('router filters actions and sizes; no chat command', async () => {
  const replies = [], switched = [];
  const router = createRouter({ engine: async r => ({ ok: r.action }), assistant: { ops: { info: async () => ({ model: null }) } }, post: m => replies.push(m), copy: async () => {}, saveExport: async () => {}, switchProject: async id => switched.push(id) });
  await router({ type: 'rpc', id: '1', request: { action: 'explain', message: 'x' } });
  await router({ type: 'assistant', id: '2', op: 'constructor' });
  await router({ type: 'assistant', id: '3', op: 'info', payload: { pad: 'x'.repeat(20000) } });
  await router({ type: 'assistant', id: '4', op: 'info' });
  await router({ type: 'rpc', id: '5', request: { action: 'assistant_clear', confirm: true } });
  await router({ type: 'switch-project', id: 'x'.repeat(200) });
  await router({ type: 'switch-project', id: MPG });
  assert.deepEqual(replies.map(r => r.error?.code || 'ok'), ['action', 'action', 'size', 'ok', 'action']);
  assert.deepEqual(switched, [MPG]);
  for (const file of ['extension.js', 'assistant.js', 'router.js', 'lm.js']) {
    const source = fs.readFileSync(path.join(__dirname, '..', file), 'utf8');
    assert.ok(!/executeCommand|chat\.open|workbench\.action\.chat/.test(source), file);
  }
});

test('shared code contains no business-specific content', () => {
  const files = ['assistant.js', 'prompt.js', 'router.js', 'lm.js', 'extension.js'].map(f => path.join(__dirname, '..', f))
    .concat(['companion.js', 'bridge.js', 'companion.html', 'protocol.py'].map(f => path.join(SOURCE, f)));
  for (const file of files) {
    // The VS Code disposable registry is infrastructure, not business vocabulary.
    const text = fs.readFileSync(file, 'utf8').replace(/\bcontext\.subscriptions\b/g, '');
    for (const word of ['subscription', 'balance', 'pdays', 'poutcome', 'duration', 'threshold', 'mpg', 'alerts', 'false_alarms', '0.35']) {
      assert.ok(!text.includes(word), `${path.basename(file)} contains « ${word} »`);
    }
  }
});
