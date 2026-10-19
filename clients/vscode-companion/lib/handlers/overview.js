'use strict';
// Overview handler (COMPANION-ADVANCED §6.1; owned by WP-U1).
//
//   open_artifact   v0: open a deliverable (the report in the browser, the others in the
//                   editor); v1: the report at the fragment `#r-<resultId>` (EV-4), the
//                   notebook at the line that names a result, an editor at a finding's line
//   load: check     the Health section's "Checks of the deliverables" (cached per revision)
//   render          W5, "Regenerate the report and notebook"
//   acknowledge     W6, "Acknowledge in my words" for an interrupted execution
//   switch_study    the header's study switcher (§6.1.6): the extension's quick pick
//
// `ready`, `refresh`, and `load: summary` belong to the controller. Reviewer refusals and
// the stage gate are the controller's too; the pre-checks below are the ones of §7.

const fs = require('fs');
const { ARTIFACT_PATHS } = require('../models/summary');
const { toCheckModel } = require('../models/check');
const { MAX_WORDS } = require('../cli');
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
    ctx.post({ type: 'notice', politeness: 'assertive', text: `${ARTIFACT_PATHS[message.artifact]} does not exist yet.` });
    return;
  }
  const options = {};
  if (message.resultId && message.artifact === 'report') options.fragment = `r-${message.resultId}`;
  if (message.line) options.line = message.line;
  if (message.resultId && message.artifact !== 'report') {
    const line = lineOf(target, message.resultId);
    if (line) options.line = line;
    else ctx.post({ type: 'notice', politeness: 'polite', text: `${ARTIFACT_PATHS[message.artifact]} does not name this result; it opens at the top.` });
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

/** The executions the panel showed that an acknowledgement may name (§7, W6). */
function acknowledgeable(snapshot) {
  if (!snapshot || !snapshot.executions) return [];
  return [...(snapshot.executions.interrupted || []), ...(snapshot.executions.suspected || [])].map(e => e.executionId);
}

/** W6: `run --acknowledge-interruption <eid> --user-words=<words> ...` after the §7 pre-checks. */
async function acknowledge(message, ctx) {
  const { executionId, words, revision } = message;
  if (!words.trim()) {
    ctx.invalid('W6', 'Type your own reply first. Nothing was recorded.', executionId);
    return;
  }
  if (words.length > MAX_WORDS) {
    ctx.invalid('W6', `Your reply is longer than ${MAX_WORDS} characters. Nothing was recorded.`, executionId);
    return;
  }
  if (!acknowledgeable(ctx.snapshot()).includes(executionId)) {
    ctx.invalid('W6', 'This execution is not waiting for an acknowledgement any more. Nothing was recorded.', executionId);
    await ctx.refresh();
    return;
  }
  await ctx.write('W6', {
    target: executionId,
    argv: requestId => ctx.cli.acknowledgeArgv(ctx.agent, { executionId, words, requestId, expectedRevision: revision }),
    record: p => {
      const r = (p && p.result) || {};
      return { userWords: typeof r.user_words === 'string' ? r.user_words : null,
        status: typeof r.status === 'string' ? r.status : (typeof p.status === 'string' ? p.status : null) };
    },
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
  if (ctx.settings.reviewer && name === 'workbench') {
    ctx.post({ type: 'notice', politeness: 'assertive', text: 'Read-only reviewer mode: the workbench is not opened for editing. Nothing was started.' });
    return;
  }
  if (!ctx.exists(ctx.artifactPath(name))) {
    ctx.post({ type: 'notice', politeness: 'assertive', text: `${rel} does not exist yet. Nothing was started.` });
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
      text: `The panel cannot build the Marimo command for ${rel} from this study's engine. Open the file, or ask the agent for the command. Nothing was started.` });
    return;
  }
  if (!ctx.host || typeof ctx.host.launchMarimo !== 'function') {
    ctx.post({ type: 'notice', politeness: 'assertive', text: 'This host cannot open a terminal. Nothing was started.' });
    return;
  }
  const reused = await ctx.host.launchMarimo(spec);
  ctx.post({ type: 'notice', politeness: 'polite', text: reused
    ? `The terminal "${spec.terminalName}" already runs ${rel}; it is shown again.`
    : `Started "marimo ${spec.mode}" for ${rel} in the terminal "${spec.terminalName}". Stop it with Ctrl+C in that terminal.` });
}

/** The header's study switcher: the extension shows the quick pick and reopens the panel. */
async function switchStudy(_message, ctx) {
  if (ctx.host && typeof ctx.host.switchStudy === 'function') await ctx.host.switchStudy();
}

module.exports = {
  types: { open_artifact: openArtifact, open_marimo: openMarimo, render, acknowledge, switch_study: switchStudy },
  loads: {
    check: { stage: 'v1', key: () => 'check', argv: (cli, agent) => cli.checkArgv(agent), model: toCheckModel },
  },
  RENDER_TARGET,
  acknowledgeable,
  lineOf,
  deliverablesOf,
};
