'use strict';
// Overview handler (COMPANION-ADVANCED §6.1; owned by WP-U1).
//
//   open_artifact   v0: open a deliverable (the report in the browser, the others in the
//                   editor); v2: the report at the fragment `#r-<resultId>` (EV-4)
//   load: check     the Health section's "Checks of the deliverables" (cached per revision)
//   render          W5, "Regenerate the report and notebook"
//   acknowledge     W6, "Acknowledge in my words" for an interrupted execution
//   switch_study    the header's study switcher (§6.1.6): the extension's quick pick
//
// `ready`, `refresh`, and `load: summary` belong to the controller. Reviewer refusals and
// the stage gate are the controller's too; the pre-checks below are the ones of §7.

const { ARTIFACT_PATHS } = require('../models/summary');
const { toCheckModel } = require('../models/check');
const { MAX_WORDS } = require('../cli');

// The W5 outcome and busy state carry this target, so the Overview renders them in place.
const RENDER_TARGET = 'render';

async function openArtifact(message, ctx) {
  const target = ctx.artifactPath(message.artifact);
  if (!ctx.exists(target)) {
    ctx.post({ type: 'notice', politeness: 'assertive', text: `${ARTIFACT_PATHS[message.artifact]} does not exist yet.` });
    return;
  }
  const options = message.resultId ? { fragment: `r-${message.resultId}` } : {};
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

/** The header's study switcher: the extension shows the quick pick and reopens the panel. */
async function switchStudy(_message, ctx) {
  if (ctx.host && typeof ctx.host.switchStudy === 'function') await ctx.host.switchStudy();
}

module.exports = {
  types: { open_artifact: openArtifact, render, acknowledge, switch_study: switchStudy },
  loads: {
    check: { stage: 'v1', key: () => 'check', argv: (cli, agent) => cli.checkArgv(agent), model: toCheckModel },
  },
  RENDER_TARGET,
  acknowledgeable,
};
