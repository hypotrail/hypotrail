'use strict';
// Decisions handler. WP-0 skeleton: the v0 writes W1 (confirm) and W2 (withdraw), moved
// from the v0 controller unchanged in behaviour. Owned by WP-U2, which adds
// `preview_effects`, `load: decisions`, and the v1 Decisions tab (COMPANION-ADVANCED §6.2).

const { MAX_WORDS } = require('../cli');

function shown(ctx, proposalId) {
  const snapshot = ctx.snapshot();
  return Boolean(snapshot && snapshot.proposals.some(p => p.proposalId === proposalId));
}

/** The v0 pre-checks of W1 and W2: the proposal must be one the panel showed. */
async function precheck(ctx, op, proposalId) {
  if (!shown(ctx, proposalId)) {
    ctx.invalid(op, 'This proposal is not open in the panel any more. Nothing was recorded.', proposalId);
    await ctx.refresh();
    return false;
  }
  return true;
}

async function confirm(message, ctx) {
  const { proposalId, words, revision } = message;
  if (!words.trim()) {
    ctx.invalid('W1', 'Type your own answer first. Nothing was recorded.', proposalId);
    return;
  }
  if (words.length > MAX_WORDS) {
    ctx.invalid('W1', `Your answer is longer than ${MAX_WORDS} characters. Nothing was recorded.`, proposalId);
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
  const snapshot = ctx.snapshot();
  const proposal = snapshot && snapshot.proposals.find(p => p.proposalId === proposalId);
  if (!(await precheck(ctx, 'W2', proposalId))) return;
  if (!(await ctx.confirmWithdraw(proposal))) {
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

module.exports = { types: { confirm, withdraw }, loads: {} };
