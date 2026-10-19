'use strict';
// Evidence handler (COMPANION-ADVANCED §6.4, §4.2; CLI-CONTRACT-COMPANION §5, §11). WP-U3.
//
//   loads.evidence          `evidence --json` (the registry, lineage, ledger) or, with a
//                           `resultId`, `evidence --result <rid> --json` (the same plus the
//                           detail of that result). Cached per key and revision.
//   commands.go_to_result   "Hypotrail: go to a result...": resolve a pasted id prefix
//                           through `evidence`, then post `navigate` to the Evidence tab.
//
// Cache keys are `evidence` and `evidence:<rid>` (COMPANION-ADVANCED §5): the controller
// caches the payload per key, so the EDA and What if? loaders, which read the same
// `evidence --json` with other model functions, share the listing's process and entry.
// "Show in report" and "Show in the notebook" are `open_artifact` messages, which the
// Overview handler serves (the report fragment `#r-<rid>` is WP-0's).

const { toEvidenceModel } = require('../models/evidence');
const { resultIdInput } = require('../uri');

const LIST_KEY = 'evidence';
const keyOf = message => (message.resultId ? `${LIST_KEY}:${message.resultId}` : LIST_KEY);

const loads = {
  evidence: {
    stage: 'v2',
    key: keyOf,
    argv: (cli, agent, message) => cli.evidenceArgv(agent, { resultId: message.resultId || null }),
    model: toEvidenceModel,
  },
};

function tell(ctx, text) {
  ctx.post({ type: 'notice', politeness: 'assertive', text });
  if (ctx.host && typeof ctx.host.notify === 'function') ctx.host.notify(text);
}

/**
 * Resolve `prefix` (8 to 64 hex characters) to one result id and navigate to it. Returns
 * the id, null when nothing was opened, or undefined without a prefix (nothing to do).
 */
async function goToResult(args, ctx) {
  const prefix = args && typeof args.prefix === 'string' ? resultIdInput(args.prefix) : null;
  if (!prefix) return undefined;
  const out = await ctx.read(LIST_KEY, ctx.cli.evidenceArgv(ctx.agent), toEvidenceModel);
  if (!out.ok) {
    tell(ctx, `The results of this study could not be read: ${out.message}`);
    return null;
  }
  const ids = [...new Set(out.model.results.map(r => r.resultId).filter(id => id.startsWith(prefix)))];
  let id = ids.length === 1 ? ids[0] : null;
  // A full id that the listing left out (older entries beyond the limit): the detail read
  // checks it, and refuses an unknown one with `unknown_result`.
  if (!id && ids.length === 0 && prefix.length === 64 && out.model.truncated) id = prefix;
  if (!id) {
    tell(ctx, ids.length > 1
      ? `Several results start with ${prefix}. Paste more characters of the id.`
      : `No result of this study starts with ${prefix}.${out.model.truncated ? ' Older results are not listed; paste the whole id.' : ''}`);
    return null;
  }
  ctx.post({ type: 'navigate', tab: 'evidence', kind: 'result', id });
  return id;
}

module.exports = { types: {}, loads, commands: { go_to_result: goToResult }, LIST_KEY };
