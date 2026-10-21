'use strict';
// TrialsModel (v0.3, WP-K): the trial budget and the model-family shortlist, read from the
// full view (`status --json`, `view.model_selection` and `view.model_families`, CLI-CONTRACT
// §14, ADR 0007). The same read as the What if? scenario (one process, one cache entry).
//
// Only what the evaluation does not hold is kept: the live budget (every distinct variant
// the study ever confirmed counts, so a replaced variant still counts), the question each
// variant answers (the stored selection drops it), and the engine's drafted shortlist with
// the flags of the linear checks that motivate it. The per-fold figures are cited from the
// evaluation's stored `model_selection` (EvidenceModel.selection), never from this view: the
// view recomputes them and is not a registered result. Nothing is computed here.
//
// Keys: revision, budget ({max, used, remaining, declared, legacy} or null), questions
// ({slot: question}), families (null before the variant decision exists, else
// {recommendation, texts, text, dataContingent, interpretability, declared, checked, source,
// flags, checks, families, shortlist}).

const { ModelError, str, strOrNull, list, obj, int, num, bool, expectSchema, plain } = require('./common');

const SCHEMA = 'hypotrail.status/1';
const RECOMMENDATIONS = ['run_diagnostics', 'rerun_diagnostics', 'stay_linear', 'compare_nonlinear'];

function budgetOf(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const b = obj(raw);
  const max = int(b.max);
  const used = int(b.used);
  if (max === null || used === null) return null;
  return { max, used, remaining: int(b.remaining), declared: int(b.declared), legacy: bool(b.legacy) };
}

function textsOf(raw) {
  const t = obj(raw);
  return { en: strOrNull(t.en), fr: strOrNull(t.fr) };
}

/** The linear checks the shortlist read (CLI-CONTRACT §14 "Linear checks"), flags first. */
function checksOf(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const c = obj(raw);
  const slope = obj(c.calibration_slope);
  return {
    model: strOrNull(c.model),
    nonlinearity: list(c.nonlinearity).map(x => ({ feature: str(x && x.feature), pValue: num(x && x.p_value),
      level: num(x && x.level), flagged: bool(x && x.flagged) })),
    interaction: list(c.interaction).map(x => ({ feature: str(x && x.feature), pValue: num(x && x.p_value),
      level: num(x && x.level), flagged: bool(x && x.flagged), groups: list(x && x.groups).length })),
    calibrationSlope: Object.keys(slope).length ? { slope: num(slope.slope), low: num(slope.low), high: num(slope.high),
      band: list(slope.band).map(num), flagged: bool(slope.flagged) } : null,
    alpha: num(c.alpha),
  };
}

function familiesOf(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const f = obj(raw);
  const cons = obj(f.constraints);
  const ev = obj(f.evidence);
  const recommendation = RECOMMENDATIONS.includes(f.recommendation) ? f.recommendation : null;
  return {
    recommendation,
    text: strOrNull(f.text),
    texts: textsOf(f.texts),
    dataContingent: bool(f.data_contingent),
    interpretability: strOrNull(cons.interpretability),
    declared: bool(cons.declared),
    checked: bool(ev.checked),
    source: /^[0-9a-f]{64}$/.test(str(ev.source)) ? ev.source : null,
    flags: list(ev.flags).map(x => ({ check: str(x && x.check), feature: strOrNull(x && x.feature),
      pValue: num(x && x.p_value), slope: num(x && x.slope) })),
    checks: checksOf(ev.checks),
    families: list(f.families).map(x => ({ family: str(x && x.family), interpretability: strOrNull(x && x.interpretability),
      default: bool(x && x.default), allowed: x && x.allowed !== false, excluded: x && x.allowed === false,
      motivated: bool(x && x.motivated) })).filter(x => x.family),
    shortlist: list(f.shortlist).map(str).filter(Boolean),
  };
}

function toTrialsModel(payload) {
  const p = expectSchema(payload, SCHEMA);
  if (!Number.isInteger(p.revision)) throw new ModelError(`The CLI did not return a ${SCHEMA} document.`);
  const view = obj(p.view);
  const selection = view.model_selection && typeof view.model_selection === 'object' ? view.model_selection : null;
  const questions = {};
  for (const c of list(selection && selection.configurations)) {
    if (c && typeof c.slot === 'string' && typeof c.question === 'string' && c.question) questions[c.slot] = c.question;
  }
  return plain({
    revision: p.revision,
    budget: selection ? budgetOf(selection.budget) : null,
    questions,
    families: familiesOf(view.model_families),
  });
}

const FIXTURES = ['captured/status.binary.families', 'captured/status.shoppers'];

module.exports = { toTrialsModel, FIXTURES, SCHEMA, RECOMMENDATIONS };
