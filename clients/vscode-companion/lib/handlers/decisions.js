'use strict';
// Decisions handler (COMPANION-ADVANCED §6.2, §7 W1 and W2): `confirm` (W1), `withdraw`
// (W2, after the VS Code modal), `preview_effects` (the engine's dry run of a confirmation,
// CLI-CONTRACT-COMPANION §3), and `load: decisions` (§2). Owned by WP-U2.
//
// The webview sends identifiers and the junior's typed words only; every argv is built by
// lib/cli.js. No write here delegates (INV-4): there is no basis and no scope to send.

const { MAX_WORDS } = require('../cli');
const { toDecisionsModel } = require('../models/decisions');
const { toEffectsModel, unavailableEffects } = require('../models/effects');

const NOT_OPEN = 'This proposal is not open in the panel any more. Nothing was recorded.';
const BLANK = 'Type your own answer first. Nothing was recorded.';
const TOO_LONG = `Your answer is longer than ${MAX_WORDS} characters. Nothing was recorded.`;
const EFFECTS_UNAVAILABLE = 'The engine could not preview this confirmation.';

function openProposal(ctx, proposalId) {
  const snapshot = ctx.snapshot();
  return (snapshot && snapshot.proposals.find(p => p.proposalId === proposalId)) || null;
}

/** The v0 pre-checks of W1 and W2: the proposal must be one the panel showed. */
async function precheck(ctx, op, proposalId) {
  if (!openProposal(ctx, proposalId)) {
    ctx.invalid(op, NOT_OPEN, proposalId);
    await ctx.refresh();
    return false;
  }
  return true;
}

async function confirm(message, ctx) {
  const { proposalId, words, revision } = message;
  if (!words.trim()) {
    ctx.invalid('W1', BLANK, proposalId);
    return;
  }
  if (words.length > MAX_WORDS) {
    ctx.invalid('W1', TOO_LONG, proposalId);
    return;
  }
  if (!(await precheck(ctx, 'W1', proposalId))) return;
  await ctx.write('W1', {
    target: proposalId,
    argv: requestId => ctx.cli.confirmArgv(ctx.agent, { proposalId, words, requestId, expectedRevision: revision }),
    record: p => {
      const r = p.result || {};
      return { userWords: typeof r.user_words === 'string' ? r.user_words : null,
        channel: typeof r.channel === 'string' ? r.channel : null,
        decisionId: typeof r.decision_id === 'string' ? r.decision_id : null, proposalId };
    },
  });
}

async function withdraw(message, ctx) {
  const { proposalId, revision } = message;
  if (!(await precheck(ctx, 'W2', proposalId))) return;
  if (!(await ctx.confirmWithdraw(openProposal(ctx, proposalId)))) {
    ctx.post({ type: 'outcome', op: 'W2', kind: 'cancelled', target: proposalId, message: 'Nothing was recorded.' });
    return;
  }
  await ctx.write('W2', {
    target: proposalId,
    argv: requestId => ctx.cli.withdrawArgv(ctx.agent, { proposalId, requestId, expectedRevision: revision }),
    record: p => {
      const r = p.result || {};
      return { proposalId, decisionId: typeof r.decision_id === 'string' ? r.decision_id : null,
        status: typeof r.status === 'string' ? r.status : null };
    },
  });
}

/** Decision titles of the last snapshot's plan, to name the decisions to confirm again. */
function titles(ctx) {
  const snapshot = ctx.snapshot();
  return Object.fromEntries(((snapshot && snapshot.plan) || []).map(s => [s.id, s.title]));
}

/**
 * `preview effects <pid>` (cached per proposal and revision). Only an open proposal of the
 * last snapshot is previewed. A refusal or an older engine answers an `available: false`
 * model, so the card says the preview is missing instead of guessing.
 */
async function previewEffects(message, ctx) {
  const { proposalId } = message;
  if (!openProposal(ctx, proposalId)) return;
  const names = titles(ctx);
  const out = await ctx.read(`effects:${proposalId}`, ctx.cli.previewEffectsArgv(ctx.agent, { proposalId }),
    p => toEffectsModel(p, { titles: names }));
  const snapshot = ctx.snapshot();
  const revision = out.ok ? out.revision : (snapshot ? snapshot.revision : 0);
  const model = out.ok ? out.model
    : unavailableEffects(proposalId, out.refusal ? `${EFFECTS_UNAVAILABLE} ${out.refusal.engineMessage}` : `${EFFECTS_UNAVAILABLE} ${out.message}`,
      out.refusal || null);
  ctx.post({ type: 'effects', proposalId, revision, model });
}

module.exports = {
  types: { confirm, withdraw, preview_effects: previewEffects },
  loads: {
    decisions: { stage: 'v1', key: () => 'decisions', argv: (cli, agent) => cli.decisionsArgv(agent), model: toDecisionsModel },
  },
};
