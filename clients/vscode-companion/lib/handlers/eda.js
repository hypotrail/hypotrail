'use strict';
// Eda handler (COMPANION-ADVANCED §6.3, §7 W4). Owned by WP-U4.
//
//   load: data  the DataModel of the `data` read (lib/models/data.js; WP-A7, the data card);
//   load: eda   the EdaModel of the `evidence` read (lib/models/eda.js);
//   run_eda     W4 `run <eda.activity> --column=<c>` after the catalog check of §7: the
//               activity is a per-column, runnable entry of `eda_catalog` in the evidence
//               read at the revision the junior saw, and the column is one of its columns.
//               Anything else is `invalid` and no `run` starts (ED-1, INV-13). There is no
//               partition argument: the engine reads training rows only (CC §8).
//               v0.3 (WP-E2): `run eda.correlation` without a column, when the catalog
//               lists it as a runnable whole-study entry (structural, no target).
//
// The cache key is `evidence`, shared with the Evidence and What if? loaders: the
// controller caches the payload and projects it with toEdaModel (COMPANION-ADVANCED §5).

const { toEdaModel, requestable, requestableWhole } = require('../models/eda');
const { toDataModel } = require('../models/data');
const l10n = require('../l10n');

const KEY = 'evidence';
// The refusals of W4, by l10n key (R9UX-6: in the extension's language, lib/l10n.js);
// MESSAGES keeps their English text for the tests and the contract.
const KEYS = Object.freeze({ unread: 'edaUnread', moved: 'edaMoved', notInCatalog: 'edaNotInCatalog',
  notRunnable: 'edaNotRunnable' });
const MESSAGES = Object.freeze(Object.fromEntries(Object.entries(KEYS).map(([k, key]) => [k, l10n.EN[key]])));
const say = (ctx, name) => (ctx.say ? ctx.say(KEYS[name]) : MESSAGES[name]);

function readCatalog(ctx) {
  return ctx.read(KEY, ctx.cli.evidenceArgv(ctx.agent), toEdaModel);
}

async function runEda(message, ctx) {
  const { activity, column, revision } = message;
  const whole = column === undefined;
  const slot = whole ? activity : `${activity}:${column}`;
  const shown = await readCatalog(ctx);
  if (!shown.ok) {
    ctx.invalid('W4', `${say(ctx, 'unread')} ${shown.message}`.trim(), slot);
    return;
  }
  if (shown.model.revision !== revision) {
    ctx.invalid('W4', say(ctx, 'moved'), slot);
    await ctx.refresh();
    return;
  }
  const entry = shown.model.catalog.find(a => a.activity === activity && a.perColumn === !whole);
  if (!entry || (!whole && !entry.columns.some(c => c.name === column))) {
    ctx.invalid('W4', say(ctx, 'notInCatalog'), slot);
    return;
  }
  if (whole ? !requestableWhole(shown.model, activity) : !requestable(shown.model, activity, column)) {
    ctx.invalid('W4', say(ctx, 'notRunnable'), slot);
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
    // WP-A7: the data card at the top of the Data & EDA tab (`hypotrail data`, development
    // rows only; the engine records no exposure for it).
    data: { stage: 'v2', key: () => 'data', argv: (cli, agent) => cli.dataArgv(agent), model: toDataModel },
  },
  KEY, MESSAGES,
};
