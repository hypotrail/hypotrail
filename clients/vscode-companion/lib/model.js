'use strict';
// Panel model: a pure projection of `hypotrail.summary/1` (CLI-CONTRACT §3) for the
// webview. Nothing here is computed from raw state; unknown keys are ignored.

const SUMMARY_SCHEMA = 'hypotrail.summary/1';
// Artefact names and paths are fixed by the contract (CLI-CONTRACT §8.3).
const ARTIFACT_PATHS = {
  report: 'reports/study.html',
  notebook: 'notebooks/study_generated.py',
  workbench: 'notebooks/workbench.py',
};
const ARTIFACT_LABELS = { report: 'Report', notebook: 'Generated notebook', workbench: 'Workbench' };
const PROPOSAL_ID = /^p_[0-9]+$/;

function str(x) { return typeof x === 'string' ? x : ''; }
function list(x) { return Array.isArray(x) ? x : []; }

function showValue(value) {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value;
  try { return JSON.stringify(value); } catch (_) { return String(value); }
}

class SummaryError extends Error {}

function toModel(summary) {
  if (!summary || summary.schema !== SUMMARY_SCHEMA || summary.ok !== true || !Number.isInteger(summary.revision)) {
    throw new SummaryError('The CLI did not return a hypotrail.summary/1 document.');
  }
  const plan = list(summary.plan).map(step => ({
    id: str(step && step.id), title: str(step && step.title), status: str(step && step.status),
  }));
  const titles = Object.fromEntries(plan.map(s => [s.id, s.title]));
  const index = plan.findIndex(s => s.id === summary.current_step);
  const notes = list(summary.notes).map(n => ({
    noteId: str(n && n.note_id), decisionId: str(n && n.decision_id), status: str(n && n.status),
    userWords: str(n && n.user_words),
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
      holds: holds.filter(h => h.decisionId === str(p.decision_id)).map(h => ({ noteId: h.noteId, userWords: h.userWords })),
    }));
  const items = (summary.artifacts && summary.artifacts.items) || {};
  const artifacts = Object.keys(ARTIFACT_PATHS).filter(name => items[name]).map(name => ({
    name, label: ARTIFACT_LABELS[name], path: ARTIFACT_PATHS[name],
    status: str(items[name].status), message: str(items[name].message),
  }));
  const nyd = summary.not_yet_defensible || {};
  const next = summary.next_action || {};
  return {
    study: str(summary.study),
    revision: summary.revision,
    recap: list(summary.recap).map(str),
    currentStep: index >= 0 ? { id: plan[index].id, title: plan[index].title, position: index + 1, total: plan.length } : null,
    plan,
    nextAction: { kind: str(next.kind), message: str(next.message) },
    artifacts,
    artifactsStatus: str(summary.artifacts && summary.artifacts.status),
    proposals,
    holds: holds.map(h => ({ ...h, decisionTitle: titles[h.decisionId] || h.decisionId })),
    notYetDefensible: {
      top: list(nyd.top).map(i => ({ id: str(i && i.id), text: str(i && i.text) })),
      more: list(nyd.more).map(str),
    },
  };
}

module.exports = { toModel, SummaryError, ARTIFACT_PATHS, PROPOSAL_ID, SUMMARY_SCHEMA };
