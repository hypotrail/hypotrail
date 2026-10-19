'use strict';
// Read cache of the controller (COMPANION-ADVANCED §11): one entry per data key and
// version. The controller's version is `<revision>:<currency>` of the last summary
// (decision CR.1), so a dataset edit or a deleted deliverable, which changes the currency
// without a new revision, is a new key. Entries of another version are dropped when a new
// summary arrives (`prune`), and every non-preview entry on an explicit Refresh and after
// each write (`clearData`), except `preview:*` keys, which are kept in a bounded
// most-recently-used list (64). The cache holds the CLI payloads (successful reads only);
// the controller projects them per view model on each hit. It is never written to disk.
//
// Frozen by WP-0; `clearData` and versions other than a revision added by CR.1.

const PREVIEW_PREFIX = 'preview:';
const PREVIEW_LIMIT = 64;

function createCache({ previewLimit = PREVIEW_LIMIT } = {}) {
  const entries = new Map();   // key -> {revision, value}
  const previews = new Map();  // `${revision}|${key}` -> value, in use order

  function get(key, revision) {
    if (key.startsWith(PREVIEW_PREFIX)) {
      const id = `${revision}|${key}`;
      if (!previews.has(id)) return undefined;
      const value = previews.get(id);
      previews.delete(id);
      previews.set(id, value);
      return value;
    }
    const entry = entries.get(key);
    return entry && entry.revision === revision ? entry.value : undefined;
  }

  function set(key, revision, value) {
    if (key.startsWith(PREVIEW_PREFIX)) {
      const id = `${revision}|${key}`;
      previews.delete(id);
      previews.set(id, value);
      while (previews.size > previewLimit) previews.delete(previews.keys().next().value);
      return;
    }
    entries.set(key, { revision, value });
  }

  /** Drop the non-preview entries read at another version than `version`. */
  function prune(version) {
    for (const [key, entry] of entries) if (entry.revision !== version) entries.delete(key);
  }

  /** Drop every non-preview entry (the explicit Refresh, after a write). */
  function clearData() {
    entries.clear();
  }

  function clear() {
    entries.clear();
    previews.clear();
  }

  return { get, set, prune, clear, clearData, size: () => entries.size + previews.size };
}

module.exports = { createCache, PREVIEW_PREFIX, PREVIEW_LIMIT };
