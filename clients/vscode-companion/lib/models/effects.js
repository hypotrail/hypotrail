'use strict';
// EffectsModel: a pure projection of `hypotrail.preview_effects/1` (CLI-CONTRACT-COMPANION
// §3), the engine's dry run of `decide confirm`, for the "If you confirm" section of a
// pending decision card (COMPANION-ADVANCED §6.2.1, §9). The panel predicts nothing: every
// list here is the engine's. `titles` ({decisionId: title}, from the summary plan) only
// names the decisions to confirm again; without it a decision is named by its id.
//
// Owned by WP-U2.

const { str, strOrNull, list, obj, int, plain, showValue, expectSchema } = require('./common');

const SCHEMA = 'hypotrail.preview_effects/1';
const EFFECTS_KEYS = ['available', 'proposalId', 'decisionId', 'value', 'revision', 'firstConfirmation', 'previous', 'mutation',
  'reason', 'kept', 'reconfirm', 'stale', 'staleResults', 'refit', 'blocked', 'regenerated', 'supersedesProposal', 'notes', 'note'];
const FIT_PREFIX = 'fit.';

function toEffectsModel(payload, { titles = {} } = {}) {
  const p = expectSchema(payload, SCHEMA);
  const keptSlots = list(p.kept_slots).map(str);
  const staleSlots = list(p.stale_slots).map(str);
  const refit = list(p.refit).map(str);
  const keptFits = keptSlots.filter(s => s.startsWith(FIT_PREFIX));
  const previous = p.previous && typeof p.previous === 'object' ? {
    value: showValue(p.previous.value), userWords: str(p.previous.user_words), basis: str(p.previous.basis) || 'explicit',
    channel: str(p.previous.channel) || 'chat', revision: int(p.previous.revision), proposalId: strOrNull(p.previous.proposal_id),
  } : null;
  const after = obj(p.artifacts_after);
  return {
    available: true,
    proposalId: str(p.proposal_id),
    decisionId: str(p.decision_id),
    value: showValue(p.value),
    revision: int(p.revision) || 0,
    firstConfirmation: previous === null || p.mutation === 'first_confirmation',
    previous,
    mutation: strOrNull(p.mutation),
    reason: strOrNull(p.reason),
    // "both models and their predictions, nothing refitted" when every fit stays current.
    kept: {
      fitsAllKept: keptFits.length > 0 && refit.length === 0 && !staleSlots.some(s => s.startsWith(FIT_PREFIX)),
      fits: keptFits,
      slots: keptSlots,
    },
    reconfirm: list(p.reconfirm_required).map(x => {
      const id = typeof x === 'string' ? x : str(x && x.decision_id);
      return { id, title: str(titles[id]) || id };
    }),
    stale: staleSlots,
    staleResults: list(p.stale_results).length,
    refit,
    blocked: list(p.blocked).map(b => ({ code: str(b && b.code), reason: strOrNull(b && b.reason), message: str(b && b.message),
      details: plain(obj(b && b.details)) })),
    regenerated: Object.keys(after).filter(name => after[name] === 'regenerated'),
    supersedesProposal: strOrNull(p.supersedes_proposal),
    notes: list(p.notes).map(str).filter(Boolean),
    note: str(p.note),
  };
}

/** The model posted when the preview could not be read (an older engine, a refusal). */
function unavailableEffects(proposalId, message, refusal = null) {
  return { available: false, proposalId, message: str(message), code: refusal ? str(refusal.code) : null,
    reason: refusal ? strOrNull(refusal.reason) : null };
}

const FIXTURES = ['preview_effects.binary', 'preview_effects.binary.reconfirm', 'preview_effects.binary.blocked',
  'preview_effects.binary.first', 'preview_effects.binary.split', 'preview_effects.regression'];

module.exports = { toEffectsModel, unavailableEffects, EFFECTS_KEYS, SCHEMA, FIXTURES };
