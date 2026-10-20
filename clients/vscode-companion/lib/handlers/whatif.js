'use strict';
// What if? handler (COMPANION-ADVANCED §6.5, §11; CLI-CONTRACT-COMPANION §4). WP-U3.
//
//   loads.whatif     `evidence --json` projected by toWhatIfModel (the shared key `evidence`).
//   loads.scenario   WP-B5: `status --json` projected by toScenarioModel (the teaching
//                    scenario's default share, labelled as an assumption of the exercise).
//   preview_policy   the slider: debounced (300 ms, only the latest request is kept), at most
//                    one `preview policy` at a time, cached per (revision, rules, intervals)
//                    under a `preview:` key (the 64 most recent). The answer carries the
//                    request's `seq`; the webview drops one that is not its latest.
//   draft            `preview proposal <d> --value=<v>`: the engine's draft texts (read only),
//                    shown so the junior sees what the agent would propose before asking.
// Nothing here writes: W3 (a proposal made from the panel) was withdrawn by the v0.3
// narrowing (ADR 0004 amendment, integrator decision I2); "Ask the agent to propose this"
// copies a question for the chat instead. No `policy.evaluate`, no fit (INV-13, WI-2).

const { toWhatIfModel } = require('../models/whatif');
const { toPolicyPreviewModel } = require('../models/preview');
const { toDraftModel } = require('../models/draft');
const { toScenarioModel } = require('../models/scenario');

const DEBOUNCE_MS = 300;
const RULE = /^(threshold:(0(\.[0-9]+)?|1(\.0+)?)|capacity:[1-9][0-9]{0,6}|share:(0\.[0-9]*[1-9][0-9]*|1(\.0+)?))$/;
const FIT_SLOT = /^fit\.[a-z_]+$/;
const NOTHING = 'Nothing was recorded.';

const sliders = new WeakMap();   // ctx -> {timer, latest (debouncing), queued (due), running}

function slider(ctx) {
  if (!sliders.has(ctx)) sliders.set(ctx, { timer: null, latest: null, queued: null, running: null });
  return sliders.get(ctx);
}

const previewKey = (rules, intervals) => `preview:${rules.join('|')}:${intervals ? 'intervals' : 'points'}`;

/** Run the latest pending preview, then any request that arrived meanwhile (one at a time). */
async function pump(ctx, s) {
  while (s.queued) {
    const m = s.queued;
    s.queued = null;
    let argv;
    try {
      argv = ctx.cli.previewPolicyArgv(ctx.agent, { rules: m.rules, intervals: m.intervals });
    } catch (e) {
      ctx.post({ type: 'notice', politeness: 'assertive', text: `The preview could not be asked: ${e.message}.` });
      continue;
    }
    const out = await ctx.read(previewKey(m.rules, m.intervals), argv, toPolicyPreviewModel, { group: 'preview' });
    if (!out.ok) {
      ctx.post({ type: 'notice', politeness: 'assertive', text: `The preview could not be computed: ${out.message}` });
      continue;
    }
    ctx.post({ type: 'preview_policy_result', seq: m.seq, revision: out.revision, ...(out.currency ? { currency: out.currency } : {}),
      model: out.model });
  }
}

function previewPolicy(message, ctx) {
  const s = slider(ctx);
  s.latest = message;
  if (s.timer) clearTimeout(s.timer);
  s.timer = setTimeout(() => {
    s.timer = null;
    // The request that stayed the latest for DEBOUNCE_MS; an older queued one is dropped.
    s.queued = s.latest;
    s.latest = null;
    start(ctx, s);
  }, DEBOUNCE_MS);
}

function start(ctx, s) {
  if (s.running || !s.queued) return;
  s.running = pump(ctx, s).catch(e => ctx.log(e)).finally(() => {
    s.running = null;
    start(ctx, s);
  });
}

/** Test hook: resolves when no preview is scheduled or running for this controller. */
async function settled(ctx) {
  const s = slider(ctx);
  while (s.running || s.timer) {
    if (s.running) await s.running;
    else await new Promise(resolve => setImmediate(resolve));
  }
}

function valueOk(decisionId, value) {
  return decisionId === 'policy' ? RULE.test(value) : FIT_SLOT.test(value);
}

/** `preview proposal`, cached per version like any read. */
async function readDraft(ctx, decisionId, value) {
  let argv;
  try {
    argv = ctx.cli.previewProposalArgv(ctx.agent, { decisionId, value });
  } catch (e) {
    return { ok: false, message: e.message };
  }
  return ctx.read(`draft:${decisionId}:${value}`, argv, toDraftModel);
}

async function draft(message, ctx) {
  const { decisionId, value } = message;
  if (!valueOk(decisionId, value)) {
    ctx.post({ type: 'notice', politeness: 'assertive', text: `${value} is not a value the panel can draft. ${NOTHING}` });
    return;
  }
  const out = await readDraft(ctx, decisionId, value);
  if (!out.ok) {
    ctx.post({ type: 'notice', politeness: 'assertive', text: `The draft could not be read: ${out.message}` });
    return;
  }
  ctx.post({ type: 'draft_result', decisionId, value, revision: out.revision, ...(out.currency ? { currency: out.currency } : {}),
    model: out.model });
}

const loads = {
  whatif: {
    stage: 'v2',
    key: () => 'evidence',
    argv: (cli, agent) => cli.evidenceArgv(agent),
    model: toWhatIfModel,
  },
  // WP-B5: the full view holds `scenario_defaults` (the summary and the evidence do not);
  // cached per version like any read. Engine request: carry it in the summary.
  scenario: {
    stage: 'v2',
    key: () => 'scenario',
    argv: (cli, agent) => cli.viewArgv(agent),
    model: toScenarioModel,
  },
};

module.exports = {
  types: { preview_policy: previewPolicy, draft },
  loads,
  DEBOUNCE_MS, previewKey, settled,
};
