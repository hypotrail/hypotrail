'use strict';
// Decisions handler (COMPANION-ADVANCED §6.2): `preview_effects` (the engine's dry run of a
// confirmation, CLI-CONTRACT-COMPANION §3) and `load: decisions` (§2). Owned by WP-U2.
//
// Read only. The v0.3 narrowing (ADR 0004 amendment; owner decision R23, integrator
// decision I2) withdrew W1 (confirm) and W2 (withdraw): a decision is confirmed or
// withdrawn in the chat only, and this handler has no write.

const { toDecisionsModel } = require('../models/decisions');
const { toEffectsModel, unavailableEffects } = require('../models/effects');

const EFFECTS_UNAVAILABLE = 'The engine could not preview this confirmation.';

function openProposal(ctx, proposalId) {
  const snapshot = ctx.snapshot();
  return (snapshot && snapshot.proposals.find(p => p.proposalId === proposalId)) || null;
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
  // The version the preview was read at (CR.1): the card asks again when it moves.
  const currency = out.ok ? out.currency : (snapshot ? snapshot.currency : undefined);
  const model = out.ok ? out.model
    : unavailableEffects(proposalId, out.refusal ? `${EFFECTS_UNAVAILABLE} ${out.refusal.engineMessage}` : `${EFFECTS_UNAVAILABLE} ${out.message}`,
      out.refusal || null);
  ctx.post({ type: 'effects', proposalId, revision, ...(currency ? { currency } : {}), model });
}

module.exports = {
  types: { preview_effects: previewEffects },
  loads: {
    decisions: { stage: 'v1', key: () => 'decisions', argv: (cli, agent) => cli.decisionsArgv(agent), model: toDecisionsModel },
  },
};
