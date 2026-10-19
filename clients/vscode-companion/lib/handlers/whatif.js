'use strict';
// What if? handler (COMPANION-ADVANCED §6.5, §7 W3, §11; CLI-CONTRACT-COMPANION §4). WP-U3.
//
//   loads.whatif     `evidence --json` projected by toWhatIfModel (the shared key `evidence`).
//   loads.scenario   WP-B5: `status --json` projected by toScenarioModel (the teaching
//                    scenario's default share, labelled as an assumption of the exercise).
//   preview_policy   the slider: debounced (300 ms, only the latest request is kept), at most
//                    one `preview policy` at a time, cached per (revision, rules, intervals)
//                    under a `preview:` key (the 64 most recent). The answer carries the
//                    request's `seq`; the webview drops one that is not its latest.
//   draft            `preview proposal <d> --value=<v>`: the engine's draft texts (read only).
//   propose          W3. The controller re-reads the draft immediately before (never the
//                    cache), requires `proposable` and the revision the junior saw, asks
//                    the host's modal, then runs `decide propose` with the draft's texts,
//                    byte for byte, and `--channel webview`. It creates a proposal only.
// Nothing here runs `policy.evaluate`, a fit, or any other write (INV-13, WI-2).

const { toWhatIfModel } = require('../models/whatif');
const { toPolicyPreviewModel } = require('../models/preview');
const { toDraftModel } = require('../models/draft');
const { toScenarioModel } = require('../models/scenario');

const DEBOUNCE_MS = 300;
const RULE = /^(threshold:(0(\.[0-9]+)?|1(\.0+)?)|capacity:[1-9][0-9]{0,6}|share:(0\.[0-9]*[1-9][0-9]*|1(\.0+)?))$/;
const FIT_SLOT = /^fit\.[a-z_]+$/;
const DECISION_OF_TASK = { binary: 'policy', regression: 'model_choice' };
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

/** `preview proposal`; `fresh` (the read before W3) neither reads nor fills the cache. */
async function readDraft(ctx, decisionId, value, { fresh = false } = {}) {
  let argv;
  try {
    argv = ctx.cli.previewProposalArgv(ctx.agent, { decisionId, value });
  } catch (e) {
    return { ok: false, message: e.message };
  }
  return ctx.read(`draft:${decisionId}:${value}`, argv, toDraftModel, fresh ? { cache: false } : {});
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

/** §7 W3: the decision is named by its plan title (CR.9), else by its id in words. */
function modalText(decisionId, value, model, planTitle = null) {
  const title = planTitle ? `"${planTitle}"` : decisionId.replace(/_/g, ' ');
  const replaces = model.supersedesProposal ? ` It replaces the open proposal ${model.supersedesProposal}.` : '';
  return `Create a proposal for ${title}: ${value}? It is not a decision. You will confirm it in your own words in Decisions.${replaces}`;
}

async function propose(message, ctx) {
  const { decisionId, value, revision } = message;
  const snapshot = ctx.snapshot();
  const expected = snapshot ? DECISION_OF_TASK[snapshot.task] : null;
  if (decisionId !== expected) {
    ctx.invalid('W3', `The panel proposes only ${expected ? expected.replace(/_/g, ' ') : 'the choice of the third pause'} in this study. ${NOTHING}`, decisionId);
    return;
  }
  if (!valueOk(decisionId, value)) {
    ctx.invalid('W3', `${value} is not a value the panel can propose. ${NOTHING}`, decisionId);
    return;
  }
  if (!snapshot || revision !== snapshot.revision) {
    ctx.invalid('W3', `The study changed since you looked at this value. Read it again. ${NOTHING}`, decisionId);
    await ctx.refresh();
    return;
  }
  const out = await readDraft(ctx, decisionId, value, { fresh: true });
  if (!out.ok) {
    ctx.invalid('W3', `The draft could not be read: ${out.message} ${NOTHING}`, decisionId);
    return;
  }
  const model = out.model;
  if (!model.proposable || model.decisionId !== decisionId || model.value !== value) {
    ctx.invalid('W3', `The engine has not evaluated ${value}, so it cannot be proposed here. ${NOTHING}`, decisionId);
    return;
  }
  if (model.revision !== revision) {
    ctx.invalid('W3', `The study changed since you looked at this value. Read it again. ${NOTHING}`, decisionId);
    await ctx.refresh();
    return;
  }
  const ask = ctx.host && typeof ctx.host.confirmModal === 'function' ? ctx.host.confirmModal : null;
  const step = (snapshot.plan || []).find(s => s.id === decisionId);
  if (!ask || !(await ask(modalText(decisionId, value, model, step && step.title ? step.title : null), 'Propose'))) {
    ctx.post({ type: 'outcome', op: 'W3', kind: 'cancelled', target: decisionId, message: NOTHING });
    return;
  }
  await ctx.write('W3', {
    target: decisionId,
    argv: requestId => ctx.cli.proposeArgv(ctx.agent, { decisionId, value, restatement: model.restatement,
      rationale: model.rationale, requestId, expectedRevision: model.revision }),
    record: p => {
      const r = p.result || {};
      return { proposalId: typeof r.proposal_id === 'string' ? r.proposal_id : null,
        decisionId: typeof r.decision_id === 'string' ? r.decision_id : decisionId,
        status: typeof r.status === 'string' ? r.status : null, channel: 'webview' };
    },
  });
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
  types: { preview_policy: previewPolicy, draft, propose },
  loads,
  DEBOUNCE_MS, previewKey, settled, modalText,
};
