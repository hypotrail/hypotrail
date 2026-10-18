'use strict';
// Deep links and "go to a result" (CLI-CONTRACT-COMPANION §11, COMPANION-ADVANCED §4.2).
// WP-0 skeleton with the frozen signatures; owned by WP-U3, which implements them:
//
//   parseDeepLink(uri: {path, query}) -> {tab, kind, id, study: string | null} | null
//     vscode://hypotrail-local.hypotrail-companion/result/<64 hex>[?study=<abs path>]
//     .../decision/<decision id>, .../proposal/<p_n>; anything else -> null.
//   resultIdInput(text: string) -> string | null
//     the lowercase hex prefix of 8 to 64 characters a junior pasted, or null.
//
// extension.js already wires them: an invalid link shows "This Hypotrail link is not
// valid." and opens nothing; a valid one opens the panel (flag, trust, and stage checks)
// and posts `navigate`. Until WP-U3 lands every link reads as not valid.

const INVALID_LINK = 'This Hypotrail link is not valid.';

function parseDeepLink(_uri) {
  return null;
}

function resultIdInput(text) {
  const t = String(text || '').trim().toLowerCase();
  return /^[0-9a-f]{8,64}$/.test(t) ? t : null;
}

module.exports = { parseDeepLink, resultIdInput, INVALID_LINK };
