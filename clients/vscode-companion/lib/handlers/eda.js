'use strict';
// Eda handler (COMPANION-ADVANCED §6.3, §7 W4). Owned by WP-U4.
//
//   load: eda   the EdaModel of the `evidence` read (lib/models/eda.js);
//   run_eda     W4 `run <eda.activity> --column=<c>` after the catalog check of §7: the
//               activity is a per-column, runnable entry of `eda_catalog` in the evidence
//               read at the revision the junior saw, and the column is one of its columns.
//               Anything else is `invalid` and no `run` starts (ED-1, INV-13). There is no
//               partition argument: the engine reads training rows only (CC §8).
//
// The cache key is `evidence`, shared with the Evidence and What if? loaders: the
// controller caches the payload and projects it with toEdaModel (COMPANION-ADVANCED §5).

const { toEdaModel, requestable } = require('../models/eda');

const KEY = 'evidence';
const MESSAGES = Object.freeze({
  unread: 'The list of charts could not be read, so nothing was run.',
  moved: 'The study changed since this list of charts was shown. Read it again; nothing was run.',
  notInCatalog: 'This chart is not in the engine\'s EDA catalog for this study. Nothing was run.',
  notRunnable: 'The engine cannot run this chart yet. Nothing was run.',
});

function readCatalog(ctx) {
  return ctx.read(KEY, ctx.cli.evidenceArgv(ctx.agent), toEdaModel);
}

async function runEda(message, ctx) {
  const { activity, column, revision } = message;
  const slot = `${activity}:${column}`;
  const shown = await readCatalog(ctx);
  if (!shown.ok) {
    ctx.invalid('W4', `${MESSAGES.unread} ${shown.message}`.trim(), slot);
    return;
  }
  if (shown.model.revision !== revision) {
    ctx.invalid('W4', MESSAGES.moved, slot);
    await ctx.refresh();
    return;
  }
  const entry = shown.model.catalog.find(a => a.activity === activity && a.perColumn);
  if (!entry || !entry.columns.some(c => c.name === column)) {
    ctx.invalid('W4', MESSAGES.notInCatalog, slot);
    return;
  }
  if (!requestable(shown.model, activity, column)) {
    ctx.invalid('W4', MESSAGES.notRunnable, slot);
    return;
  }
  await ctx.write('W4', {
    target: slot,
    argv: requestId => ctx.cli.runEdaArgv(ctx.agent, { activity, column, requestId, expectedRevision: revision }),
    record: p => {
      const r = p.result && typeof p.result === 'object' ? p.result : {};
      return { slot: typeof r.slot === 'string' ? r.slot : null,
        status: typeof r.status === 'string' ? r.status : typeof p.status === 'string' ? p.status : null };
    },
  });
}

module.exports = {
  types: { run_eda: runEda },
  loads: {
    eda: { stage: 'v2', key: () => KEY, argv: (cli, agent) => cli.evidenceArgv(agent), model: toEdaModel },
  },
  KEY, MESSAGES,
};
