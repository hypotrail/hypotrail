'use strict';
// Feature flag of the companion (ADR 0003). Off by default: the setting
// `hypotrail.companion.enabled` (default false) or the environment variable
// HYPOTRAIL_COMPANION=1 (tests, development host) turns it on.

const SETTING_SECTION = 'hypotrail.companion';
const SETTING_KEY = 'enabled';
const ENV_VAR = 'HYPOTRAIL_COMPANION';
const DISABLED_MESSAGE = 'Companion disabled (feature flag)';

function isEnabled(vscode, env = process.env) {
  if (env[ENV_VAR] === '1') return true;
  try {
    return vscode.workspace.getConfiguration(SETTING_SECTION).get(SETTING_KEY, false) === true;
  } catch (_) {
    return false;
  }
}

module.exports = { isEnabled, SETTING_SECTION, SETTING_KEY, ENV_VAR, DISABLED_MESSAGE };
