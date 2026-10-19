'use strict';
// Feature flag, stage, and preferences of the companion (ADR 0003, ADR 0004 decision 5,
// COMPANION-ADVANCED §3.1). Off by default: the setting `hypotrail.companion.enabled`
// (default false) or the environment variable HYPOTRAIL_COMPANION=1 (tests, development
// host) turns it on. Nothing here is read at activation; the command reads it when run.
//
// - stage: `hypotrail.companion.stage` ("v0" to "v3", default "v0");
//   HYPOTRAIL_COMPANION_STAGE overrides it (tests, observation sessions). A stage above the
//   ones this extension knows reads as the highest it knows; anything else reads as "v0".
// - learningLayer: `hypotrail.companion.learningLayer` (default true; effective from v3);
//   HYPOTRAIL_COMPANION_LEARNING=0 or 1 overrides it.
// - reviewer: `hypotrail.companion.reviewer` (default false); HYPOTRAIL_COMPANION_REVIEWER=1.
// - chatInsert: `hypotrail.companion.chatInsert` (default false). It is NOT contributed in
//   package.json (hidden) and has no environment override, until a real VS Code session
//   verifies that the chat insertion does not send (integrator decision CA.8). Until then
//   the setting is ignored and reads as false (CHAT_INSERT_VERIFIED, decision CR.8): the
//   bridge copies to the clipboard only. Verifying it is a change of this constant, with
//   the observation recorded in docs/plans/V0.1-DECISIONS.md.

const SETTING_SECTION = 'hypotrail.companion';
const SETTING_KEY = 'enabled';
const ENV_VAR = 'HYPOTRAIL_COMPANION';
const STAGE_ENV = 'HYPOTRAIL_COMPANION_STAGE';
const LEARNING_ENV = 'HYPOTRAIL_COMPANION_LEARNING';
const REVIEWER_ENV = 'HYPOTRAIL_COMPANION_REVIEWER';
const DISABLED_MESSAGE = 'Companion disabled (feature flag)';
const STAGES = ['v0', 'v1', 'v2', 'v3'];
// CR.8: false until a real VS Code session shows that the chat insertion does not send.
const CHAT_INSERT_VERIFIED = false;
const DEFAULTS = Object.freeze({ stage: 'v0', learningLayer: true, reviewer: false, chatInsert: false });

function setting(vscode, key, fallback) {
  try {
    const value = vscode.workspace.getConfiguration(SETTING_SECTION).get(key, fallback);
    return value === undefined ? fallback : value;
  } catch (_) {
    return fallback;
  }
}

function isEnabled(vscode, env = process.env) {
  if (env[ENV_VAR] === '1') return true;
  return setting(vscode, SETTING_KEY, false) === true;
}

/** "v0".."v3": a known stage, the highest known for a higher "vN", else "v0". */
function normalizeStage(raw) {
  if (STAGES.includes(raw)) return raw;
  const m = typeof raw === 'string' ? raw.match(/^v([0-9]{1,3})$/) : null;
  if (m && Number(m[1]) > STAGES.length - 1) return STAGES[STAGES.length - 1];
  return DEFAULTS.stage;
}

function stage(vscode, env = process.env) {
  if (typeof env[STAGE_ENV] === 'string' && env[STAGE_ENV]) return normalizeStage(env[STAGE_ENV]);
  return normalizeStage(setting(vscode, 'stage', DEFAULTS.stage));
}

function stageRank(value) {
  return STAGES.indexOf(value);
}

function stageAtLeast(active, wanted) {
  return stageRank(active) >= stageRank(wanted) && stageRank(wanted) >= 0;
}

function learningLayer(vscode, env = process.env) {
  if (env[LEARNING_ENV] === '0') return false;
  if (env[LEARNING_ENV] === '1') return true;
  return setting(vscode, 'learningLayer', DEFAULTS.learningLayer) !== false;
}

function reviewer(vscode, env = process.env) {
  if (env[REVIEWER_ENV] === '1') return true;
  return setting(vscode, 'reviewer', DEFAULTS.reviewer) === true;
}

function chatInsert(vscode) {
  return CHAT_INSERT_VERIFIED && setting(vscode, 'chatInsert', DEFAULTS.chatInsert) === true;
}

/** {stage, reviewer, learningLayer, chatInsert}; `forceReviewer` for the reviewer command. */
function settings(vscode, env = process.env, { forceReviewer = false } = {}) {
  return { stage: stage(vscode, env), reviewer: forceReviewer || reviewer(vscode, env),
    learningLayer: learningLayer(vscode, env), chatInsert: chatInsert(vscode) };
}

module.exports = {
  isEnabled, stage, normalizeStage, stageRank, stageAtLeast, learningLayer, reviewer, chatInsert, settings,
  CHAT_INSERT_VERIFIED, SETTING_SECTION, SETTING_KEY, ENV_VAR, STAGE_ENV, LEARNING_ENV, REVIEWER_ENV, DISABLED_MESSAGE, STAGES, DEFAULTS,
};
