'use strict';
// DraftModel: a pure projection of `hypotrail.proposal_draft/1` (`preview proposal`,
// CLI-CONTRACT-COMPANION §4) for the What if? draft card (COMPANION-ADVANCED §6.5, §9).
// WP-U3. The restatement and the rationale are the engine's texts, passed through byte for
// byte: the panel never writes a restatement. Since the v0.3 narrowing (no W3) the draft is
// shown read only, next to "Ask the agent to propose this".
//
// Keys (§9): proposable, missing, restatement, rationale, evidence, supersedesProposal,
// note; plus revision, decisionId, value.

const { str, strOrNull, list, obj, int, num, expectSchema, plain } = require('./common');

const SCHEMA = 'hypotrail.proposal_draft/1';

function toDraftModel(payload) {
  const p = expectSchema(payload, SCHEMA);
  const ev = p.evidence && typeof p.evidence === 'object' ? p.evidence : null;
  const proposable = p.proposable === true && typeof p.restatement === 'string' && typeof p.rationale === 'string';
  return plain({
    revision: int(p.revision),
    decisionId: str(p.decision_id),
    value: str(p.value),
    proposable,
    missing: list(p.missing).map(m => ({ requirement: str(obj(m).requirement), value: str(obj(m).value) })),
    restatement: proposable ? p.restatement : null,
    rationale: proposable ? p.rationale : null,
    evidence: ev ? {
      resultId: str(ev.result_id), activity: str(ev.activity),
      figures: list(ev.figures).map(f => ({ path: str(obj(f).path), value: num(obj(f).value), shown: str(obj(f).shown) })),
    } : null,
    supersedesProposal: strOrNull(p.supersedes_proposal),
    note: str(p.note),
  });
}

const FIXTURES = ['proposal_draft.binary', 'proposal_draft.binary.unevaluated', 'proposal_draft.regression'];

module.exports = { toDraftModel, FIXTURES };
