'use strict';
// CheckModel: a pure projection of `hypotrail.check/1` (CLI-CONTRACT §8.2, and the
// `location` of each finding, CLI-CONTRACT-COMPANION §10) for the Overview Health section
// (COMPANION-ADVANCED §6.1.5, §9). Owned by WP-U1.
//
// A finding's `deliverable` is the artefact name (`report`, `notebook`, `workbench`) when
// its `location.path` is exactly one of the three deliverables of the contract
// (CLI-CONTRACT §8.3); only then does the panel offer "Open" (§12, "Location paths"). Any
// other path, an absolute one, or one that leaves the study folder gets no "Open".

const path = require('path');
const { expectSchema, str, strOrNull, list, obj, int } = require('./common');
const { ARTIFACT_PATHS } = require('./summary');

const CHECK_SCHEMA = 'hypotrail.check/1';
const RESULT_ANCHOR = /^r-([0-9a-f]{64})$/;
const CHECK_KEYS = ['revision', 'clean', 'counts', 'findings'];

/** The deliverable named by a study-relative path, or null. */
function deliverableOf(rel) {
  if (typeof rel !== 'string' || !rel || rel.includes('\0') || path.isAbsolute(rel) || /^[A-Za-z]:/.test(rel)) return null;
  const normal = path.posix.normalize(rel.replace(/\\/g, '/'));
  if (normal.startsWith('../') || normal === '..') return null;
  const found = Object.entries(ARTIFACT_PATHS).find(([, p]) => p === normal);
  return found ? found[0] : null;
}

function location(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const line = int(raw.line);
  return { path: strOrNull(raw.path), anchor: strOrNull(raw.anchor), line: line !== null && line > 0 ? line : null };
}

function toCheckModel(payload) {
  expectSchema(payload, CHECK_SCHEMA);
  const counts = obj(payload.counts);
  return {
    revision: int(payload.revision),
    clean: payload.clean === true,
    counts: { error: int(counts.error) || 0, warning: int(counts.warning) || 0 },
    findings: list(payload.findings).map(f => {
      const loc = location(f && f.location);
      const deliverable = loc ? deliverableOf(loc.path) : null;
      const anchor = loc && loc.anchor ? loc.anchor.match(RESULT_ANCHOR) : null;
      return {
        code: str(f && f.code), severity: str(f && f.severity), where: str(f && f.where), message: str(f && f.message),
        location: loc,
        deliverable,
        // The report anchor `r-<result id>` (C10): the panel opens the report there (v2).
        resultId: deliverable === 'report' && anchor ? anchor[1] : null,
      };
    }),
  };
}

const FIXTURES = ['check.binary', 'check.binary.clean'];

module.exports = { toCheckModel, deliverableOf, CHECK_SCHEMA, CHECK_KEYS, FIXTURES };
