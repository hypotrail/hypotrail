'use strict';
// DecisionsModel: a pure projection of `hypotrail.decisions/1` (CLI-CONTRACT-COMPANION §2)
// for the Decisions tab (COMPANION-ADVANCED §6.2.2, §6.2.3, §9). Nothing is computed from
// raw state: the history, the queue, and the proposals are the engine's lists, reordered
// for display only (the history is grouped by decision in plan order, newest first).
// Words, restatements, and reasons are copied verbatim; the webview sets them as text.
//
// Owned by WP-U2.

const { str, strOrNull, list, obj, int, bool, showValue, expectSchema } = require('./common');

const SCHEMA = 'hypotrail.decisions/1';
const DECISIONS_KEYS = ['revision', 'task', 'decisions', 'queue', 'history', 'unconfirmedProposals', 'notes'];
// The display order of the availability statuses (CLI-CONTRACT §5, feature_availability).
const AVAILABILITY_ORDER = ['available_at_prediction', 'uncertain_included', 'uncertain_excluded', 'not_available'];
// Proposals that ended without a confirmation (§6.2.3 "Proposals that were not confirmed").
const UNCONFIRMED = ['withdrawn', 'superseded'];

/**
 * The status groups of an availability value ({column: status}), or null for any other
 * value. Columns keep the engine's order within a group; unknown statuses come last.
 */
function availabilityGroups(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const entries = Object.entries(value);
  if (!entries.length || !entries.every(([, v]) => typeof v === 'string')) return null;
  const statuses = [...AVAILABILITY_ORDER, ...new Set(entries.map(([, v]) => v).filter(v => !AVAILABILITY_ORDER.includes(v)))];
  return statuses.map(status => ({ status, columns: entries.filter(([, v]) => v === status).map(([k]) => k) }))
    .filter(g => g.columns.length);
}

function value(raw) {
  return { value: showValue(raw), groups: availabilityGroups(raw) };
}

function origin(raw) {
  return raw && typeof raw === 'object' && typeof raw.channel === 'string' ? { channel: raw.channel } : null;
}

function toDecisionsModel(payload) {
  const p = expectSchema(payload, SCHEMA);
  const decisions = list(p.decisions).map((d, index) => {
    const c = d && d.confirmation && typeof d.confirmation === 'object' ? d.confirmation : null;
    return {
      decisionId: str(d && d.decision_id), title: str(d && d.title), pause: int(d && d.pause), order: index,
      status: str(d && d.status), ...value(d && d.value), reason: strOrNull(d && d.reason),
      dependsOn: list(d && d.depends_on).map(str),
      confirmation: c ? {
        userWords: str(c.user_words), basis: str(c.basis) || 'explicit', scope: strOrNull(c.delegation_scope),
        channel: str(c.channel) || 'chat', actor: strOrNull(c.actor), proposalId: strOrNull(c.proposal_id),
        revision: int(c.revision), time: strOrNull(c.time),
        // ADR 0005 (R3; WP-A7 shows it): the point the agent raised and the junior kept, verbatim.
        agentConcern: strOrNull(c.agent_concern),
      } : null,
      openProposals: list(d && d.open_proposals).map(x => (typeof x === 'string' ? x : str(x && x.proposal_id))).filter(Boolean),
    };
  });
  const order = Object.fromEntries(decisions.map(d => [d.decisionId, d.order]));
  const titles = Object.fromEntries(decisions.map(d => [d.decisionId, d.title]));
  const rank = id => (Object.prototype.hasOwnProperty.call(order, id) ? order[id] : decisions.length);
  const titleOf = id => titles[id] || id;

  const history = list(p.history).map((h, index) => ({
    decisionId: str(h && h.decision_id), title: titleOf(str(h && h.decision_id)), proposalId: strOrNull(h && h.proposal_id),
    ...value(h && h.value),
    // CC §2: a record without basis reads explicit, without channel reads chat.
    userWords: str(h && h.user_words), basis: str(h && h.basis) || 'explicit', scope: strOrNull(h && h.delegation_scope),
    channel: str(h && h.channel) || 'chat', actor: strOrNull(h && h.actor),
    revision: int(h && h.revision), time: strOrNull(h && h.time),
    current: bool(h && h.current), supersededAt: int(h && h.superseded_at), index,
    agentConcern: null,
  }));
  // WP-A7: the agent's concern belongs to the confirmation the decision holds now (the
  // history records carry none): the current row of that confirmation shows it.
  for (const h of history) {
    const d = decisions.find(x => x.decisionId === h.decisionId);
    const c = d && d.confirmation;
    if (h.current && c && c.agentConcern && c.revision === h.revision) h.agentConcern = c.agentConcern;
  }
  // Grouped by decision in plan order; newest first within a group (§6.2.3).
  history.sort((a, b) => rank(a.decisionId) - rank(b.decisionId) || (b.revision || 0) - (a.revision || 0) || b.index - a.index);
  for (const h of history) delete h.index;

  const queue = list(p.reconfirm_queue).map(q => {
    const prev = obj(q && q.previous);
    return {
      decisionId: str(q && q.decision_id), title: titleOf(str(q && q.decision_id)), reason: str(q && q.reason),
      sinceRevision: int(q && q.since_revision),
      previous: { ...value(prev.value), userWords: str(prev.user_words), basis: str(prev.basis) || 'explicit',
        channel: str(prev.channel) || 'chat' },
      openProposal: typeof (q && q.open_proposal) === 'string' ? q.open_proposal : null,
    };
  });
  queue.sort((a, b) => rank(a.decisionId) - rank(b.decisionId));

  const unconfirmedProposals = list(p.proposals).filter(x => x && UNCONFIRMED.includes(x.status)).map(x => ({
    proposalId: str(x.proposal_id), decisionId: str(x.decision_id), title: titleOf(str(x.decision_id)), ...value(x.value),
    restatement: str(x.restatement), status: str(x.status), revision: int(x.revision), closedRevision: int(x.closed_revision),
    closedReason: strOrNull(x.closed_reason), origin: origin(x.origin),
  }));

  const notes = list(p.notes).map(n => {
    const res = n && n.resolution && typeof n.resolution === 'object' ? n.resolution : null;
    // WP-A7: `kind` is `hold` or `correction` (ADR 0005, R3; a note without it is a hold).
    return { noteId: str(n && n.note_id), decisionId: str(n && n.decision_id), status: str(n && n.status),
      kind: str(n && n.kind) || 'hold', userWords: str(n && n.user_words), resolutionWords: res ? strOrNull(res.user_words) : null,
      revision: int(n && n.revision) };
  });

  return {
    revision: int(p.revision) || 0,
    task: p.task === 'binary' || p.task === 'regression' ? p.task : null,
    decisions: decisions.map(({ order: _o, ...d }) => d),
    queue, history, unconfirmedProposals, notes,
  };
}

const FIXTURES = ['decisions.binary', 'decisions.binary.reconfirm', 'decisions.binary.injection', 'decisions.regression'];

module.exports = { toDecisionsModel, availabilityGroups, DECISIONS_KEYS, AVAILABILITY_ORDER, SCHEMA, FIXTURES };
