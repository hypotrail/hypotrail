'use strict';
// SessionReportModel (COMPANION-ADVANCED §9, §6.6.3), projected from
// `hypotrail.session_report/1`. Owned by WP-U5.
//
//   revision, log {enabled, note}, span {first, last, seconds},
//   pauses [{pause, seconds, open}], refusals [{code, reason, count}] (counts by code and reason),
//   decisions [{proposalId, decisionId, outcome, secondsOpen, refusedConfirmations}],
//   gaps [{from, to, minutes}]
//
// The report holds no conversation content, and this model copies none of what it could
// carry: no command lines, no timeline, no words. Only identifiers, counts, durations, and
// the session log note (verbatim).

const { str, strOrNull, list, obj, num, int, bool, expectSchema } = require('./common');

const SCHEMA = 'hypotrail.session_report/1';

function toSessionReportModel(payload) {
  const p = expectSchema(payload, SCHEMA);
  const log = obj(obj(p.sources).session_log);
  const span = obj(p.span);
  const counts = new Map();
  for (const r of list(p.refusals)) {
    const code = str(r && r.code);
    if (!code) continue;
    const reason = strOrNull(r && r.reason);
    const key = `${code}\u0000${reason || ''}`;
    const item = counts.get(key) || { code, reason, count: 0 };
    item.count += 1;
    counts.set(key, item);
  }
  return {
    revision: int(p.revision) === null ? 0 : int(p.revision),
    log: { enabled: bool(log.enabled), note: strOrNull(log.note) },
    span: { first: strOrNull(span.first), last: strOrNull(span.last), seconds: num(span.seconds) },
    pauses: list(p.pauses).map(x => ({ pause: int(x && x.pause), seconds: num(x && x.seconds), open: !(x && x.closed_at) })),
    refusals: [...counts.values()],
    decisions: list(p.decisions).map(d => ({ proposalId: str(d && d.proposal_id), decisionId: str(d && d.decision_id),
      outcome: str(d && d.outcome), secondsOpen: num(d && d.seconds_open), refusedConfirmations: int(d && d.refused_confirmations) || 0 })),
    gaps: list(p.gaps).map(g => ({ from: str(g && g.from), to: str(g && g.to), minutes: num(g && g.minutes) })),
  };
}

const FIXTURES = ['session_report.binary'];

module.exports = { toSessionReportModel, FIXTURES, SCHEMA };
