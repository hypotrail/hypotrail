'use strict';
// Deep links and "go to a result" (CLI-CONTRACT-COMPANION §11, COMPANION-ADVANCED §4.2,
// §12 "URI handler"). WP-U3 implements the signatures frozen by WP-0:
//
//   parseDeepLink(uri: {path, query, authority?}) -> {tab, kind, id, study: string | null} | null
//     vscode://hypotrail-local.hypotrail-companion/result/<64 hex>[?study=<abs path>]
//     .../decision/<decision id>, .../proposal/<p_n>; anything else -> null.
//   resultIdInput(text: string) -> string | null
//     the lowercase hex prefix of 8 to 64 characters a junior pasted, or null.
//
// extension.js wires them: an invalid link shows "This Hypotrail link is not valid." and
// opens nothing; a valid one opens the panel (flag, trust, and stage checks) and posts
// `navigate`. A link never triggers a write: the target is only a tab and an identifier.

const path = require('path');

const INVALID_LINK = 'This Hypotrail link is not valid.';
// `<publisher>.<name>` of package.json (CC §11).
const AUTHORITY = 'hypotrail-local.hypotrail-companion';
const RESULT_ID = /^[0-9a-f]{64}$/;
const PROPOSAL_ID = /^p_[0-9]+$/;
// state.ALL_DECISION_IDS of the engine (binary and regression decisions).
const DECISION_IDS = ['prediction_time', 'feature_availability', 'split', 'policy', 'conclusion', 'model_choice'];
const MAX_STUDY = 4096;

function studyOf(query) {
  const text = typeof query === 'string' ? query.replace(/^\?/, '') : '';
  if (!text) return { ok: true, study: null };
  let params;
  try { params = new URLSearchParams(text); } catch (_) { return { ok: false }; }
  const keys = [...params.keys()];
  if (keys.some(k => k !== 'study') || keys.length > 1) return { ok: false };
  const study = params.get('study');
  if (typeof study !== 'string' || !study || study.length > MAX_STUDY || study.includes('\0') || !path.isAbsolute(study)) {
    return { ok: false };
  }
  return { ok: true, study };
}

/** The navigation target of a deep link, or null for anything that is not one of CC §11. */
function parseDeepLink(uri) {
  if (!uri || typeof uri !== 'object' || typeof uri.path !== 'string') return null;
  if (typeof uri.authority === 'string' && uri.authority !== '' && uri.authority.toLowerCase() !== AUTHORITY) return null;
  if (typeof uri.fragment === 'string' && uri.fragment !== '') return null;
  const parts = uri.path.split('/');
  if (parts.length !== 3 || parts[0] !== '') return null;
  const [, kind, id] = parts;
  const q = studyOf(uri.query);
  if (!q.ok) return null;
  if (kind === 'result' && RESULT_ID.test(id)) return { tab: 'evidence', kind: 'result', id, study: q.study };
  if (kind === 'decision' && DECISION_IDS.includes(id)) return { tab: 'decisions', kind: 'decision', id, study: q.study };
  if (kind === 'proposal' && PROPOSAL_ID.test(id)) return { tab: 'decisions', kind: 'proposal', id, study: q.study };
  return null;
}

/**
 * The result-id prefix a junior pasted ("Hypotrail: go to a result..."), or null. It
 * accepts the id as the report shows it: the whole id or its first 8 or more characters,
 * optionally written `r-<id>` (the report anchor) or followed by "..." or "…".
 */
function resultIdInput(text) {
  let t = String(text || '').trim().toLowerCase();
  t = t.replace(/^#?r-/, '').replace(/(\.\.\.|…)$/, '').trim();
  return /^[0-9a-f]{8,64}$/.test(t) ? t : null;
}

module.exports = { parseDeepLink, resultIdInput, INVALID_LINK, AUTHORITY, DECISION_IDS };
