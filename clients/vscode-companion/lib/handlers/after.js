'use strict';
// "And after" handler (lot P, owner request R49, ADR 0004 decision 14; COMPANION-ADVANCED
// §6.5.2 `done`, §7 W8). Stage v3.
//
//   loads.azureml    `export azureml --expected-revision R --plan --json`: the Azure ML
//                    export plan (files, template, statuses), which writes nothing; read
//                    only when the engine says the chosen model is supported
//                    (`next_action.after_study.azureml.supported`, the summary's
//                    `afterStudy.exportPlanAvailable`).
//   export_azureml   W8: `export azureml --out=<folder>/azureml-revision-<R>`, outside the
//                    study state (the engine records nothing), only when supported, never an
//                    Azure job: the panel never runs a command that reaches the cloud.

const path = require('path');
const { toAzuremlPlanModel } = require('../models/azureml');

const supported = snapshot => Boolean(snapshot && snapshot.nextAction && snapshot.nextAction.kind === 'done'
  && snapshot.nextAction.afterStudy && snapshot.nextAction.afterStudy.exportPlanAvailable === true);

/** W8. The outcome's `out` is the folder the engine answered, never one the panel computed. */
async function exportAzureml(message, ctx) {
  const snapshot = ctx.snapshot();
  if (!snapshot || snapshot.revision !== message.revision) return ctx.invalid('W8', ctx.say('exportStale'), 'azureml');
  if (!supported(snapshot)) return ctx.invalid('W8', ctx.say('azuremlUnsupported'), 'azureml');
  const fallback = path.join(ctx.agent.studyDir, 'exports');
  const parent = ctx.host && typeof ctx.host.pickFolder === 'function' ? await ctx.host.pickFolder(fallback) : null;
  if (!parent) {
    ctx.post({ type: 'outcome', op: 'W8', kind: 'cancelled', target: 'azureml', message: ctx.say('exportCancelled') });
    return null;
  }
  return ctx.write('W8', {
    target: 'azureml',
    argv: () => ctx.cli.WRITES.W8(ctx.agent, { parent, revision: message.revision }),
    record: payload => ({
      files: (Array.isArray(payload.files) ? payload.files : [])
        .filter(f => f && typeof f.path === 'string' && Number.isInteger(f.bytes) && f.bytes >= 0)
        .map(f => ({ path: f.path, bytes: f.bytes })),
      out: typeof payload.out === 'string' ? payload.out : null,
      warnings: Array.isArray(payload.warnings) ? payload.warnings.filter(w => typeof w === 'string') : [],
    }),
  });
}

module.exports = {
  types: { export_azureml: exportAzureml },
  loads: {
    azureml: {
      stage: 'v3',
      key: () => 'azureml_plan',
      argv: (cli, agent, message, snapshot) => cli.READS.azureml_plan(agent, { revision: snapshot ? snapshot.revision : 0 }),
      model: toAzuremlPlanModel,
    },
  },
  supported,
};
