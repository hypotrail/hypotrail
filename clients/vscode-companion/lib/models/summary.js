'use strict';
// SummaryModel: a pure projection of `hypotrail.summary/1` (CLI-CONTRACT §3, and the
// `--digest` keys of CLI-CONTRACT-COMPANION §1) for the webview frame, Overview, and the
// Decisions cards (COMPANION-ADVANCED §9). Nothing here is computed from raw state; unknown
// keys are ignored, and the `--digest` keys are null or [] when the summary has none (v0).
//
// Moved from lib/model.js by WP-0. WP-U1 owns and extends it; its key list is frozen
// (docs/plans/COMPANION-ADVANCED-PLAN.md §2.2): add keys, never rename or remove one.
// WP-U1 added: `plan[].decisionStatus`, `plan[].after` (the step a blocked step waits
// for), `digest.boundary` (the last-session boundary revision), and `regenerate`
// (whether "Regenerate" is offered, §6.1.4).

const { ModelError, str, strOrNull, list, obj, int, showValue } = require('./common');

const SUMMARY_SCHEMA = 'hypotrail.summary/1';
// Artefact names and paths are fixed by the contract (CLI-CONTRACT §8.3).
const ARTIFACT_PATHS = {
  report: 'reports/study.html',
  notebook: 'notebooks/study_generated.py',
  workbench: 'notebooks/workbench.py',
};
const ARTIFACT_LABELS = { report: 'Report', notebook: 'Generated notebook', workbench: 'Workbench' };
const PROPOSAL_ID = /^p_[0-9]+$/;
// The items of `not_yet_defensible.top` that the frame's alert strip shows (§4.1).
const ALERT_IDS = ['sources_changed', 'interrupted_executions', 'result_integrity'];
// The pause of each decision when the summary has no `pauses` (v0 summaries).
const DECISION_PAUSE = { prediction_time: 1, feature_availability: 1, split: 2, policy: 3, model_choice: 3, conclusion: 3 };
const SUMMARY_KEYS = ['study', 'revision', 'task', 'recap', 'goal', 'currentStep', 'plan', 'moments', 'pauses',
  'nextAction', 'artifacts', 'artifactsStatus', 'proposals', 'holds', 'notes', 'decisions', 'executions',
  'notYetDefensible', 'alerts', 'digest', 'waitingCount', 'regenerate'];
// Generated deliverables: the workbench is the junior's own file and is never regenerated.
const GENERATED = ['report', 'notebook'];

class SummaryError extends ModelError {}

function taskOf(summary, plan) {
  if (summary.task === 'binary' || summary.task === 'regression') return summary.task;
  if (plan.some(s => s.id === 'model_choice')) return 'regression';
  if (plan.some(s => s.id === 'policy')) return 'binary';
  return null;
}

function execution(e) {
  return { executionId: str(e && e.execution_id), activity: str(e && e.activity), reason: strOrNull(e && e.reason),
    liveness: strOrNull(e && e.liveness), resultId: strOrNull(e && e.result_id) };
}

function digestModel(raw, lastSession) {
  if (!raw || typeof raw !== 'object') return null;
  const session = obj(lastSession);
  return {
    since: int(raw.since),
    until: int(raw.until),
    boundary: int(session.boundary_revision),
    sinceTime: strOrNull(session.boundary_time),
    gapMinutes: int(session.gap_minutes),
    items: list(raw.items).map(i => {
      const inv = i && i.invalidation && typeof i.invalidation === 'object' ? i.invalidation : null;
      return {
        revision: int(i && i.revision), time: strOrNull(i && i.time), kind: str(i && i.kind), text: str(i && i.text),
        decisionId: strOrNull(i && i.decision_id), proposalId: strOrNull(i && i.proposal_id),
        resultId: strOrNull(i && i.result_id), slot: strOrNull(i && i.slot),
        keptFits: inv ? list(inv.kept_fits).map(str) : [], refit: inv ? list(inv.refit).map(str) : null,
      };
    }),
    truncated: raw.truncated === true,
    counts: obj(raw.counts),
  };
}

function toSummaryModel(summary) {
  if (!summary || summary.schema !== SUMMARY_SCHEMA || summary.ok !== true || !Number.isInteger(summary.revision)) {
    throw new SummaryError('The CLI did not return a hypotrail.summary/1 document.');
  }
  const pauses = list(summary.pauses).map(p => ({ pause: int(p && p.pause), decisions: list(p && p.decisions).map(str),
    status: str(p && p.status), confirmed: list(p && p.confirmed).map(str) }));
  const pauseOf = {};
  for (const p of pauses) for (const d of p.decisions) pauseOf[d] = p.pause;
  const decisionsRaw = obj(summary.decisions);
  const decisions = {};
  for (const [id, d] of Object.entries(decisionsRaw)) {
    decisions[id] = { status: str(d && d.status), basis: strOrNull(d && d.basis), delegationScope: strOrNull(d && d.delegation_scope),
      userWords: strOrNull(d && d.user_words), reason: strOrNull(d && d.reason), value: showValue(d && d.value) };
  }
  const plan = list(summary.plan).map(step => {
    const id = str(step && step.id);
    const isDecision = Object.prototype.hasOwnProperty.call(decisionsRaw, id) || Object.prototype.hasOwnProperty.call(DECISION_PAUSE, id);
    return {
      id, title: str(step && step.title), status: str(step && step.status),
      pause: isDecision ? (pauseOf[id] || DECISION_PAUSE[id] || null) : null,
      basis: decisions[id] ? decisions[id].basis : null,
      decisionStatus: decisions[id] ? decisions[id].status : null,
      requires: list(step && step.requires).map(str).filter(Boolean),
      after: null,
    };
  });
  const titles = Object.fromEntries(plan.map(s => [s.id, s.title]));
  // A blocked step waits for its first unmet requirement: the summary's `requires` when it
  // carries one (the full plan does, CLI-CONTRACT §3.1), else the `blocked` next action of
  // this step, else the first earlier step of the plan that is not done.
  const nextRaw = summary.next_action || {};
  plan.forEach((s, i) => {
    if (s.status !== 'blocked') return;
    const done = id => plan.some(p => p.id === id && p.status === 'done');
    const fromNext = str(nextRaw.kind) === 'blocked' && str(nextRaw.step) === s.id
      ? list(Array.isArray(nextRaw.requires) ? nextRaw.requires : [nextRaw.requires]).map(str) : [];
    const candidates = [...s.requires, ...fromNext].filter(id => titles[id] && !done(id));
    const id = candidates[0] || (plan.slice(0, i).find(p => p.status !== 'done') || {}).id || null;
    s.after = id ? { id, title: titles[id] } : null;
  });
  for (const s of plan) delete s.requires;
  const index = plan.findIndex(s => s.id === summary.current_step);
  const notes = list(summary.notes).map(n => ({
    noteId: str(n && n.note_id), decisionId: str(n && n.decision_id), status: str(n && n.status),
    userWords: str(n && n.user_words), resolutionWords: strOrNull(n && n.resolution_words),
  }));
  const holds = notes.filter(n => n.status === 'open');
  const proposals = list(summary.open_proposals)
    .filter(p => p && PROPOSAL_ID.test(str(p.proposal_id)))
    .map(p => ({
      proposalId: p.proposal_id,
      decisionId: str(p.decision_id),
      decisionTitle: titles[str(p.decision_id)] || str(p.decision_id),
      value: showValue(p.value),
      restatement: str(p.restatement),
      revision: Number.isInteger(p.revision) ? p.revision : null,
      origin: p.origin && typeof p.origin === 'object' && typeof p.origin.channel === 'string' ? { channel: p.origin.channel } : null,
      holds: holds.filter(h => h.decisionId === str(p.decision_id)).map(h => ({ noteId: h.noteId, userWords: h.userWords })),
      resolvedNotes: notes.filter(n => n.status === 'resolved' && n.decisionId === str(p.decision_id))
        .map(n => ({ noteId: n.noteId, userWords: n.userWords, resolutionWords: n.resolutionWords })),
    }));
  const items = (summary.artifacts && summary.artifacts.items) || {};
  const artifacts = Object.keys(ARTIFACT_PATHS).filter(name => items[name]).map(name => ({
    name, label: ARTIFACT_LABELS[name], path: ARTIFACT_PATHS[name],
    status: str(items[name].status), message: str(items[name].message),
  }));
  const nyd = summary.not_yet_defensible || {};
  const next = summary.next_action || {};
  const top = list(nyd.top).map(i => ({ id: str(i && i.id), text: str(i && i.text) }));
  const alerts = top.filter(i => ALERT_IDS.includes(i.id));
  if (str(next.kind) === 'outcome_unknown') alerts.push({ id: 'outcome_unknown', text: str(next.message) });
  const ex = obj(summary.executions);
  const reconfirm = Object.values(decisions).filter(d => d.status === 'reconfirm_required').length;
  return {
    study: str(summary.study),
    revision: summary.revision,
    task: taskOf(summary, plan),
    recap: list(summary.recap).map(str),
    goal: obj(summary.goal),
    currentStep: index >= 0 ? { id: plan[index].id, title: plan[index].title, position: index + 1, total: plan.length } : null,
    plan,
    moments: list(summary.moments).map(m => ({ id: str(m && m.id), title: str(m && m.title), steps: list(m && m.steps).map(str) })),
    pauses,
    nextAction: { kind: str(next.kind), message: str(next.message), proposalId: strOrNull(next.proposal_id),
      decision: strOrNull(next.decision), executionId: strOrNull(next.execution_id) },
    artifacts,
    artifactsStatus: str(summary.artifacts && summary.artifacts.status),
    proposals,
    holds: holds.map(h => ({ ...h, decisionTitle: titles[h.decisionId] || h.decisionId })),
    notes,
    decisions,
    executions: {
      interrupted: list(ex.interrupted).map(execution),
      suspected: list(ex.suspected_interrupted).map(execution),
      late: list(ex.late).map(execution),
      active: list(ex.active).map(e => (typeof e === 'string' ? e : str(e && e.execution_id))),
    },
    notYetDefensible: { top, more: list(nyd.more).map(str) },
    alerts,
    digest: digestModel(summary.digest, summary.last_session),
    waitingCount: proposals.length + reconfirm,
    // "Regenerate" is offered when a generated deliverable is stale or failed, or nothing
    // was rendered yet (COMPANION-ADVANCED §6.1.4, OV-7).
    regenerate: str(summary.artifacts && summary.artifacts.status) === 'not_rendered' ||
      artifacts.some(a => GENERATED.includes(a.name) && (a.status === 'stale' || a.status === 'failed')),
  };
}

const FIXTURES = ['summary.v0.binary', 'summary.v0.regression', 'summary.binary', 'summary.regression', 'summary.binary.health'];

// v0 name, kept for the migrated tests and older callers.
const toModel = toSummaryModel;

module.exports = { toSummaryModel, toModel, SummaryError, ARTIFACT_PATHS, ARTIFACT_LABELS, PROPOSAL_ID, SUMMARY_SCHEMA,
  SUMMARY_KEYS, ALERT_IDS, GENERATED, FIXTURES };
