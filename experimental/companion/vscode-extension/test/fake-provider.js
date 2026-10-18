'use strict';
// Test-only simulated provider: delayed fragments, errors, and interruptions.
const { AssistantError } = require('../assistant');

const sleep = (ms, signal, ignoreAbort) => new Promise(resolve => {
  const timer = setTimeout(resolve, ms);
  if (signal && !ignoreAbort) signal.addEventListener('abort', () => { clearTimeout(timer); resolve(); }, { once: true });
});

function defaultChunks(messages) {
  const last = messages[messages.length - 1].content;
  const about = /« ([^»]+) »/.exec(last)?.[1] || 'this step';
  return [`**What you selected** — ${about}. `, '\n\n**What changes** — simulated test response. ',
    '\n\n**Keep in mind** — an unselected subscription is not an established lost sale. ',
    '\n\n**Possible next step** — compare another threshold.'];
}

function createFakeProvider(initial = {}) {
  const model = { id: 'fake-model', name: 'Simulated model (tests)', vendor: 'test', family: 'fake' };
  const state = { script: { delay: 5, ...initial }, plans: [...(initial.plans || [])], calls: [], selections: 0, remembered: initial.remembered === false ? null : model, chosen: 0 };
  async function* send(messages, signal) {
    const plan = state.plans.length ? { ...state.script, ...state.plans.shift() } : state.script;
    const call = { messages, aborted: false, yielded: 0, afterAbort: 0 };
    state.calls.push(call);
    if (plan.onSend) await plan.onSend(call);
    if (plan.error && plan.failAt === undefined) throw new AssistantError(plan.error.code, plan.error.message);
    const chunks = plan.chunks || defaultChunks(messages);
    for (let i = 0; i < chunks.length; i++) {
      if (plan.failAt === i) throw new AssistantError(plan.error.code, plan.error.message);
      await sleep(plan.delay, signal, plan.ignoreAbort);
      if (signal.aborted) { call.aborted = true; if (!plan.ignoreAbort) return; call.afterAbort++; }
      call.yielded++;
      yield chunks[i];
    }
  }
  return {
    state,
    configure(script) { Object.assign(state.script, script); if (script.plans) state.plans = [...script.plans]; },
    current() { return state.remembered; },
    async ensureModel() {
      state.selections++;
      const failure = state.script.selectError;
      if (failure) throw new AssistantError(failure.code, failure.message);
      state.remembered = model;
      return { info: model, send };
    },
    async chooseModel() { state.chosen++; state.remembered = model; return model; }
  };
}

module.exports = { createFakeProvider };
