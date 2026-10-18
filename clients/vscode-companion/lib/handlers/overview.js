'use strict';
// Overview handler. WP-0 skeleton: `open_artifact` (v0, and the report fragment
// `#r-<resultId>` of v2, COMPANION-ADVANCED §6.4 EV-4). Owned by WP-U1, which adds
// `load: check`, `render` (W5), `acknowledge` (W6), and `switch_study` (§6.1).

const { ARTIFACT_PATHS } = require('../models/summary');

async function openArtifact(message, ctx) {
  const target = ctx.artifactPath(message.artifact);
  if (!ctx.exists(target)) {
    ctx.post({ type: 'notice', politeness: 'assertive', text: `${ARTIFACT_PATHS[message.artifact]} does not exist yet.` });
    return;
  }
  const options = message.resultId ? { fragment: `r-${message.resultId}` } : {};
  await ctx.openArtifact(message.artifact, target, options);
}

module.exports = { types: { open_artifact: openArtifact }, loads: {} };
