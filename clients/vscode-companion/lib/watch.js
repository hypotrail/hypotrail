'use strict';
// Change detection without a daemon (ADR 0002): watch the study's `.hypotrail/` folder
// and call `onChange` once per burst of writes to the files that mark a new revision or
// a new render. The folder is watched, not the files, because the engine replaces
// `state.json` atomically (rename), which would end a watch on the old file.

const fs = require('fs');
const path = require('path');

const WATCHED = new Set(['state.json', 'state.sha256', 'revisions.jsonl', 'artifacts.json']);
const DEBOUNCE_MS = 250;

function watchStudy(studyDir, onChange, { fsImpl = fs, debounceMs = DEBOUNCE_MS, onError } = {}) {
  let timer = null;
  let closed = false;
  const fire = () => {
    timer = null;
    if (!closed) onChange();
  };
  const handler = (_event, filename) => {
    if (closed) return;
    // Some platforms do not report a filename: refresh anyway.
    if (filename && !WATCHED.has(String(filename))) return;
    if (timer) clearTimeout(timer);
    timer = setTimeout(fire, debounceMs);
  };
  let watcher = null;
  try {
    watcher = fsImpl.watch(path.join(studyDir, '.hypotrail'), { persistent: false }, handler);
    if (watcher && typeof watcher.on === 'function') {
      watcher.on('error', e => { if (onError) onError(e); });
    }
  } catch (e) {
    if (onError) onError(e);
  }
  return {
    trigger: handler,
    dispose() {
      closed = true;
      if (timer) clearTimeout(timer);
      if (watcher) watcher.close();
    },
  };
}

module.exports = { watchStudy, WATCHED, DEBOUNCE_MS };
