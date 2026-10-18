'use strict';
// Read cache of the controller (COMPANION-ADVANCED §11): one entry per data key and
// revision. Entries of older revisions are dropped when a newer summary arrives, except
// `preview:*` keys, which are kept in a bounded most-recently-used list (64). The cache
// holds model objects already projected from CLI payloads; it is never written to disk.
//
// Frozen by WP-0.

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

  /** Drop the non-preview entries read at a revision below `revision`. */
  function prune(revision) {
    for (const [key, entry] of entries) if (entry.revision < revision) entries.delete(key);
  }

  function clear() {
    entries.clear();
    previews.clear();
  }

  return { get, set, prune, clear, size: () => entries.size + previews.size };
}

module.exports = { createCache, PREVIEW_PREFIX, PREVIEW_LIMIT };
