'use strict';
// Panel orchestration: apply through the engine, then explain; never reverse the order.
const { buildMessages } = require('./prompt');

class AssistantError extends Error {
  constructor(code, message) { super(message); this.code = code; }
}

const ID = /^[A-Za-z0-9_-]{1,200}$/;
const KEY = /^[a-z][a-z0-9_]{0,39}$/;
const ACTIVITY = /^[a-z0-9][a-z0-9-]{0,63}$/;
const LIMITS = { question: 4000, answer: 20000, errorMessage: 500 };
const MODEL_ERRORS = new Set(['no_model', 'model_unavailable', 'model_not_chosen', 'access_denied', 'quota', 'network', 'model_error']);
const STOP_REASONS = {
  superseded: ['cancelled', 'Response stopped: a new choice was applied.'],
  stopped: ['interrupted', 'Response stopped at your request; text is incomplete.'],
  cleared: ['cancelled', 'Conversation cleared.'],
  project_switch: ['cancelled', 'Response stopped: you switched projects.'],
  disposed: ['interrupted', 'Extension stopped during the response; text is incomplete.']
};

function invalid(message) { return new AssistantError('invalid', message || 'Demande invalid.'); }
function object(value) { if (!value || typeof value !== 'object' || Array.isArray(value)) throw invalid(); return value; }
function id(value) { if (typeof value !== 'string' || !ID.test(value)) throw invalid('Identifiant invalid.'); return value; }
function step(value) { if (typeof value !== 'string' || !ACTIVITY.test(value)) throw invalid('Invalid activity.'); return value; }
function bool(value, fallback) { if (value === undefined) return fallback; if (typeof value !== 'boolean') throw invalid(); return value; }
function hash(value) { if (typeof value !== 'string' || !/^[a-f0-9]{64}$/.test(value)) throw invalid('Contexte invalid.'); return value; }

function race(promise, signal) {
  if (signal.aborted) return Promise.resolve({ done: true });
  return new Promise((resolve, reject) => {
    const onAbort = () => resolve({ done: true });
    signal.addEventListener('abort', onAbort, { once: true });
    promise.then(v => { signal.removeEventListener('abort', onAbort); resolve(v); },
      e => { signal.removeEventListener('abort', onAbort); reject(e); });
  });
}

function createAssistant({ engine, provider, post: send, projectId = null, projects = async () => [], log = () => {} }) {
  // Each event identifies its project; the panel ignores events from'a project already left.
  const post = message => send({ ...message, project_id: projectId });
  const active = new Map();
  const applying = new Map();
  const stats = { modelRequests: 0, applyCalls: 0 };
  let recovered = null;

  function recover() {
    // Once per host, mark abandoned in-progress generations interrupted without retrying.
    if (!recovered) recovered = engine({ action: 'assistant_recover' }).catch(e => { recovered = null; throw e; });
    return recovered;
  }
  function generating() { return [...active.values()].some(entry => !entry.cancelled); }
  function cancelAll(reason) { for (const entry of active.values()) entry.cancel(reason); }

  function start(exchange, context) {
    const controller = new AbortController();
    const entry = {
      id: exchange.exchange_id, text: '', cancelled: false, reason: null,
      cancel(reason) { if (entry.cancelled) return; entry.cancelled = true; entry.reason = reason; controller.abort(); }
    };
    active.set(entry.id, entry);
    entry.done = generate(exchange, context, entry, controller.signal)
      .catch(e => log('generation', e))
      .finally(() => { if (active.get(entry.id) === entry) active.delete(entry.id); });
    return entry;
  }

  async function generate(exchange, context, entry, signal) {
    const exchangeId = exchange.exchange_id;
    post({ type: 'assistant-event', event: 'started', exchange });
    let info = null, status = 'completed', code = null, message = null, iterator = null;
    try {
      const model = await provider.ensureModel();
      info = model.info;
      post({ type: 'assistant-event', event: 'model', model: info });
      if (entry.cancelled) throw new AssistantError('cancelled', 'Cancelled');
      await engine({ action: 'assistant_update', exchange_id: exchangeId, status: 'streaming', model: info });
      post({ type: 'assistant-event', event: 'streaming', exchangeId, model: info });
      stats.modelRequests++;
      iterator = model.send(buildMessages(context), signal)[Symbol.asyncIterator]();
      for (;;) {
        const next = await race(iterator.next(), signal);
        if (entry.cancelled || next.done) break;
        const fragment = String(next.value ?? '');
        if (entry.text.length + fragment.length > LIMITS.answer) {
          entry.text += fragment.slice(0, LIMITS.answer - entry.text.length);
          status = 'interrupted'; code = 'answer_truncated'; message = 'Response truncated at 20,000 characters.';
          break;
        }
        entry.text += fragment;
        post({ type: 'assistant-event', event: 'delta', exchangeId, text: fragment });
      }
    } catch (e) {
      if (!entry.cancelled) {
        status = 'error';
        code = MODEL_ERRORS.has(e.code) ? e.code : 'model_error';
        message = String(e.message || 'Erreur du model').slice(0, LIMITS.errorMessage);
      }
    }
    if (entry.cancelled) {
      [status, message] = STOP_REASONS[entry.reason] || STOP_REASONS.stopped;
      code = entry.reason || 'stopped';
      try { iterator?.return?.(); } catch (_) { /* stream already closed */ }
    }
    active.delete(exchangeId);
    const done = await engine({ action: 'assistant_update', exchange_id: exchangeId, status, answer: entry.text, model: info, error_code: code, error_message: message });
    post({ type: 'assistant-event', event: 'finished', exchange: done.exchange, current: done.current });
  }

  async function applyExplain(payload) {
    const p = object(payload);
    const request = { eventId: id(p.eventId), expectedRevision: p.expectedRevision, contextHash: hash(p.contextHash), activity: step(p.activity), key: p.key, junior: bool(p.junior, true) };
    if (!Number.isInteger(request.expectedRevision) || typeof request.key !== 'string' || !KEY.test(request.key)) throw invalid();
    const known = applying.get(request.eventId);
    if (known) return known;
    const job = (async () => {
      await recover();
      stats.applyCalls++;
      // 1. Apply through the engine. Failure stops processing before any model request.
      const snapshot = await engine({ action: 'apply', event_id: request.eventId, expected_revision: request.expectedRevision, context_hash: request.contextHash });
      const application = snapshot.application;
      if (!application || application.event_id !== request.eventId) throw new AssistantError('stale_context', 'This is no longer the applied choice: reread state.');
      if (!(request.key in application.answers)) return { snapshot, exchange: null, replayed: false };
      // 2. Explain the attested result; derive a unique identifier from'application, therefore unique.
      const begun = await engine({ action: 'assistant_begin', request: {
        exchange_id: `initial-${request.eventId}-${request.key}`, kind: 'initial', activity: request.activity, subject: 'applied',
        context_hash: snapshot.context_hash, expected_application_event_id: request.eventId, junior: request.junior } });
      if (!begun.replayed) { cancelAll('superseded'); start(begun.exchange, begun.context); }
      return { snapshot, exchange: begun.exchange, replayed: begun.replayed };
    })();
    applying.set(request.eventId, job);
    try { return await job; } finally { applying.delete(request.eventId); }
  }

  async function ask(payload) {
    const p = object(payload);
    const exchangeId = id(p.exchangeId);
    if (!exchangeId.startsWith('q-')) throw invalid('Identifiant de invalid question.');
    if (typeof p.question !== 'string' || !p.question.trim()) throw new AssistantError('question', 'Write a question.');
    if (p.question.length > LIMITS.question) throw new AssistantError('question_too_long', `Questions are limited to ${LIMITS.question} characters to keep context focused; shorten the question.`);
    if (!['applied', 'preview', 'step'].includes(p.subject)) throw invalid();
    if (p.expectedApplicationEventId != null) id(p.expectedApplicationEventId);
    if (generating()) throw new AssistantError('busy', 'A response is in progress: stop it or wait until completion.');
    await recover();
    const request = { exchange_id: exchangeId, kind: 'question', activity: step(p.activity), subject: p.subject, context_hash: hash(p.contextHash),
      question: p.question, junior: bool(p.junior, true), compare_previous: bool(p.comparePrevious, false) };
    if (p.expectedApplicationEventId != null) request.expected_application_event_id = p.expectedApplicationEventId;
    if (p.subject === 'preview') request.preview_value = p.previewValue;
    const begun = await engine({ action: 'assistant_begin', request });
    if (!begun.replayed) start(begun.exchange, begun.context);
    return { exchange: begun.exchange, replayed: begun.replayed };
  }

  async function retry(payload) {
    const exchangeId = id(object(payload).exchangeId);
    if (generating()) throw new AssistantError('busy', 'A response is in progress: stop it or wait until completion.');
    await recover();
    const begun = await engine({ action: 'assistant_begin', request: { exchange_id: exchangeId, retry: true } });
    if (!begun.replayed) start(begun.exchange, begun.context);
    return { exchange: begun.exchange, replayed: begun.replayed };
  }

  async function stop(payload) {
    const entry = active.get(id(object(payload).exchangeId));
    if (entry) entry.cancel('stopped');
    return { stopped: Boolean(entry) };
  }

  async function info() {
    await recover();
    return { model: provider.current(), projects: await projects(), streaming: [...active.values()].filter(e => !e.cancelled).map(e => ({ exchangeId: e.id, text: e.text })) };
  }

  async function chooseModel() {
    const model = await provider.chooseModel();
    post({ type: 'assistant-event', event: 'model', model });
    return { model };
  }

  async function clear(payload) {
    if (object(payload).confirm !== true) throw invalid('Confirmation required.');
    cancelAll('cleared');
    return engine({ action: 'assistant_clear', confirm: true });
  }

  function dispose(reason = 'disposed') { cancelAll(reason); }

  const ops = { 'apply-explain': applyExplain, ask, retry, stop, info, 'choose-model': chooseModel, clear };
  return { ops, recover, dispose, stats, active, cancelAll };
}

module.exports = { createAssistant, AssistantError, LIMITS };
