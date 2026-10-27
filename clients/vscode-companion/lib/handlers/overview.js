'use strict';
// Overview handler (COMPANION-ADVANCED §6.1; owned by WP-U1).
//
//   open_artifact   v0: open a deliverable (the report in the browser, the others in the
//                   editor); v1: the report at the fragment `#r-<resultId>` (EV-4), the
//                   notebook at the line that names a result, an editor at a finding's line
//   load: check     the Health section's "Checks of the deliverables" (cached per revision)
//   render          W5, "Regenerate the report and notebook"
//   switch_study    the header's study switcher (§6.1.6): the extension's quick pick
//
// `ready`, `refresh`, and `load: summary` belong to the controller. Reviewer refusals and
// the stage gate are the controller's too; the pre-checks below are the ones of §7.
// Owner decision R31 (2026-10-27, ADR 0004 amendment): there is no acknowledgement of an
// interrupted execution here any more (the former W6). The panel takes no words of the
// junior; the Overview copies a question for the chat, where the acknowledgement is made.

const fs = require('fs');
const { ARTIFACT_PATHS } = require('../models/summary');
const { toCheckModel } = require('../models/check');
const launch = require('../launch');

// The W5 outcome and busy state carry this target, so the Overview renders them in place.
const RENDER_TARGET = 'render';

/**
 * The 1-based line of a deliverable that names `resultId` (the full id, else its first
 * eight characters, as the evidence `notebook_hint` says), or null. Reading a deliverable
 * to open it is allowed (INV-1); the study state is never read.
 */
function lineOf(target, resultId, read = file => fs.readFileSync(file, 'utf8')) {
  let text;
  try { text = read(target); } catch (_) { return null; }
  const lines = String(text).split(/\r?\n/);
  for (const needle of [resultId, resultId.slice(0, 8)]) {
    const i = lines.findIndex(l => l.includes(needle));
    if (i >= 0) return i + 1;
  }
  return null;
}

async function openArtifact(message, ctx) {
  const target = ctx.artifactPath(message.artifact);
  if (!ctx.exists(target)) {
    ctx.post({ type: 'notice', politeness: 'assertive', text: ctx.say('artifactMissing', ARTIFACT_PATHS[message.artifact]) });
    return;
  }
  const options = {};
  if (message.resultId && message.artifact === 'report') options.fragment = `r-${message.resultId}`;
  if (message.line) options.line = message.line;
  if (message.resultId && message.artifact !== 'report') {
    const line = lineOf(target, message.resultId);
    if (line) options.line = line;
    else ctx.post({ type: 'notice', politeness: 'polite', text: ctx.say('artifactTop', ARTIFACT_PATHS[message.artifact]) });
  }
  await ctx.openArtifact(message.artifact, target, options);
}

/** W5: `render --json --study S` (no revision, no words). */
async function render(_message, ctx) {
  await ctx.write('W5', {
    target: RENDER_TARGET,
    argv: () => ctx.cli.renderArgv(ctx.agent),
    record: null,
  });
}

/** The engine's `deliverables` of `status --json` (`view.deliverables`), or null. */
function deliverablesOf(payload) {
  const d = payload && payload.view && payload.view.deliverables;
  return d && typeof d === 'object' && !Array.isArray(d) ? d : null;
}

/**
 * Open a notebook with Marimo's own local server (WP-A5; ADR 0004 amendment "local
 * launch"): `marimo run` for the generated notebook, `marimo edit` for the workbench, in a
 * VS Code terminal the extension creates with an argument list. The engine's launch argv
 * (`status --json`, `view.deliverables.launch`) is used when it has the expected form,
 * else the one built from `.hypotrail/agent.json` (lib/launch.js). Writes nothing to the
 * study. In reviewer mode only the read-only `marimo run` is offered.
 */
async function openMarimo(message, ctx) {
  const name = message.artifact;
  const rel = ARTIFACT_PATHS[name];
  if (ctx.settings.reviewer && (name === 'workbench' || name === 'editable')) {
    ctx.post({ type: 'notice', politeness: 'assertive', text: ctx.say('reviewerWorkbench') });
    return;
  }
  if (!ctx.exists(ctx.artifactPath(name))) {
    ctx.post({ type: 'notice', politeness: 'assertive', text: ctx.say('notebookMissing', rel) });
    return;
  }
  let engine = null;
  const snap = ctx.snapshot();
  if (snap && snap.deliverables && snap.deliverables.launch) engine = snap.deliverables.launch[name] || null;
  else {
    const out = await ctx.read('view', ctx.cli.viewArgv(ctx.agent), deliverablesOf, { cache: false });
    engine = out.ok && out.model && out.model.launch ? out.model.launch[name] || null : null;
  }
  const spec = launch.launchFor(ctx.agent, name, engine);
  if (!spec) {
    ctx.post({ type: 'notice', politeness: 'assertive',
      text: ctx.say('noMarimoCommand', rel) });
    return;
  }
  if (!ctx.host || typeof ctx.host.launchMarimo !== 'function') {
    ctx.post({ type: 'notice', politeness: 'assertive', text: ctx.say('noTerminal') });
    return;
  }
  const reused = await ctx.host.launchMarimo(spec);
  ctx.post({ type: 'notice', politeness: 'polite', text: reused
    ? ctx.say('terminalReused', spec.terminalName, rel)
    : ctx.say('terminalStarted', spec.mode, rel, spec.terminalName) });
}

/** The header's study switcher: the extension shows the quick pick and reopens the panel. */
async function switchStudy(_message, ctx) {
  if (ctx.host && typeof ctx.host.switchStudy === 'function') await ctx.host.switchStudy();
}

module.exports = {
  types: { open_artifact: openArtifact, open_marimo: openMarimo, render, switch_study: switchStudy },
  loads: {
    check: { stage: 'v1', key: () => 'check', argv: (cli, agent) => cli.checkArgv(agent), model: toCheckModel },
  },
  RENDER_TARGET,
  lineOf,
  deliverablesOf,
};
