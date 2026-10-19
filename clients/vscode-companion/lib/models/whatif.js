'use strict';
// WhatIfModel: the What if? tab's projection of `hypotrail.evidence/1` (COMPANION-ADVANCED
// §6.5, §9). WP-U3. It reads only the current, verified evaluation of the study:
//   binary:     the rules of the current `policy.evaluation` (the table "Rules already
//               evaluated"), the validation rows `n` that bound the capacity slider, and
//               the first evaluated rule (the slider's start when nothing is proposed);
//   regression: the current `evaluate.regression` (errors with intervals, the paired
//               difference, the residual quantiles, residuals by group) and the limits
//               of the split (shared groups).
// No figure is computed; `n` and the counts are the engine's. The adopted or proposed
// status of a rule comes from the summary, in the view.
//
// WP-B5: binary also `gain` (the gain points and the share each evaluated rule acts on,
// the engine's `capacity_share`), and `evaluatedRules[].share`; `share:p` rules are rules
// like the others (WP-B3).
//
// Keys (§9): task, binary: n, evaluatedRules, initialRule; regression: models, errors,
// deltas, residuals, residualsBy, splitLimits; plus revision, resultId, bootstrap, and
// (binary) targetLabel, (regression) unit, validation, splitOrdinal, residualDefinition.

const { ModelError, str, strOrNull, list, obj, int, num, expectSchema, plain } = require('./common');
const { citable, side, gainOf, pathOf } = require('./evidence');

const SCHEMA = 'hypotrail.evidence/1';

function bootstrapOf(values) {
  const b = obj(values.bootstrap);
  return { replicates: int(b.replicates), level: num(b.level), method: strOrNull(b.method) };
}

function promoted(results, slot) {
  return results.find(r => r && r.promoted === true && r.slot === slot && citable(r)) || null;
}

function binary(results, base) {
  const evaluation = promoted(results, 'policy.evaluation');
  const split = promoted(results, 'split');
  const target = promoted(results, 'eda.target_rate');
  const splitN = split ? int(obj(obj(obj(split.values).partitions).validation).n_rows) : null;
  if (!evaluation) {
    return { ...base, resultId: null, n: splitN, nPositive: null, evaluatedRules: [], initialRule: null,
      reference: null, candidate: null, bootstrap: null, targetLabel: target ? strOrNull(target.values.target) : null, gain: null };
  }
  const v = obj(evaluation.values);
  const params = obj(evaluation.params);
  const reference = str(v.reference || params.reference) || 'fit.baseline';
  const candidate = list(params.models).map(str).find(f => f !== reference) || null;
  const rules = list(params.rules).map(str).filter(rule => obj(v.rules)[rule]);
  return {
    ...base,
    resultId: str(evaluation.result_id),
    n: int(v.n) ?? splitN,
    nPositive: int(v.n_positive),
    reference,
    candidate,
    bootstrap: bootstrapOf(v),
    targetLabel: target ? strOrNull(target.values.target) : null,
    evaluatedRules: rules.map(rule => {
      const entry = obj(obj(v.rules)[rule]);
      const m = obj(obj(entry.models)[candidate]);
      const at = key => pathOf('rules', rule, 'models', candidate, key);
      return { rule, selected: num(m.selected), truePositives: num(m.true_positives), precision: num(m.precision),
        recall: num(m.recall), tiedAtCut: num(m.tied_at_cut), status: null, share: num(entry.capacity_share),
        paths: { selected: at('selected'), truePositives: at('true_positives'), precision: at('precision'), recall: at('recall'),
          share: pathOf('rules', rule, 'capacity_share') } };
    }),
    initialRule: rules.length ? rules[0] : null,
    gain: gainOf(results),
  };
}

function regression(results, base) {
  const evaluation = promoted(results, 'evaluate.regression');
  const split = promoted(results, 'split');
  const sv = split ? obj(split.values) : {};
  const groups = obj(sv.groups);
  const splitLimits = split && int(groups.shared_groups) > 0
    ? { column: str(groups.column), sharedGroups: int(groups.shared_groups),
      validationRowsInSharedGroups: int(groups.validation_rows_in_shared_groups), resultId: str(split.result_id) }
    : null;
  const validation = split ? { method: strOrNull(sv.method), column: strOrNull(sv.column), cutoff: num(sv.cutoff),
    n: int(obj(obj(sv.partitions).validation).n_rows), resultId: str(split.result_id) } : null;
  const empty = { ...base, resultId: null, models: [], errors: {}, deltas: null, residuals: {}, residualsBy: null,
    splitLimits, validation, splitOrdinal: Boolean(validation && validation.method === 'ordinal_cutoff'),
    unit: null, bootstrap: null, n: validation ? validation.n : null, residualDefinition: null };
  if (!evaluation) return empty;
  const v = obj(evaluation.values);
  const params = obj(evaluation.params);
  const reference = str(v.reference || params.reference) || 'fit.baseline';
  const fits = list(params.models).map(str);
  const candidate = str(v.candidate || params.candidate) || fits.find(f => f !== reference) || null;
  const ordered = [...fits.filter(f => f !== reference), ...fits.filter(f => f === reference)];
  const errors = {};
  const residuals = {};
  for (const fit of ordered) {
    const m = obj(obj(v.models)[fit]);
    const i = obj(obj(v.intervals)[fit]);
    errors[fit] = {
      mae: num(m.mae), maeLow: num(obj(i.mae).low), maeHigh: num(obj(i.mae).high),
      rmse: num(m.rmse), rmseLow: num(obj(i.rmse).low), rmseHigh: num(obj(i.rmse).high),
    };
    const q = obj(obj(v.residuals)[fit]);
    residuals[fit] = { min: num(q.min), q05: num(q.q05), q25: num(q.q25), median: num(q.median), q75: num(q.q75),
      q95: num(q.q95), max: num(q.max), mean: num(q.mean), n: int(q.n) };
  }
  const delta = metric => {
    const d = obj(obj(obj(v.deltas)[candidate])[metric]);
    const low = num(d.low);
    const high = num(d.high);
    return { point: num(d.point), low, high, side: side(low, high) };
  };
  const by = list(v.residuals_by)[0];
  const residualsBy = by ? {
    column: str(by.column),
    minGroupRows: int(by.min_group_rows),
    groups: list(by.groups).map(g => ({
      value: str(g && g.value), nRows: int(g && g.n_rows), small: g && g.small_count === true,
      models: Object.fromEntries(ordered.map(fit => {
        const m = obj(obj(g && g.models)[fit]);
        return [fit, { meanResidual: num(m.mean_residual), mae: num(m.mae) }];
      })),
    })),
  } : null;
  return {
    ...empty,
    resultId: str(evaluation.result_id),
    n: int(v.n) ?? empty.n,
    unit: strOrNull(v.unit),
    bootstrap: bootstrapOf(v),
    reference,
    candidate,
    models: ordered.map(fit => ({ fit, role: fit === reference ? 'reference' : 'candidate' })),
    errors,
    deltas: candidate ? { fit: candidate, mae: delta('mae'), rmse: delta('rmse') } : null,
    residuals,
    residualsBy,
    residualDefinition: strOrNull(v.residual_definition),
  };
}

function toWhatIfModel(payload) {
  const p = expectSchema(payload, SCHEMA);
  if (!Number.isInteger(p.revision)) throw new ModelError(`The CLI did not return a ${SCHEMA} document.`);
  const task = p.task === 'regression' ? 'regression' : 'binary';
  const results = list(p.results);
  const base = { task, revision: p.revision };
  return plain(task === 'regression' ? regression(results, base) : binary(results, base));
}

const FIXTURES = ['evidence.binary', 'evidence.binary.detail', 'evidence.regression', 'captured/evidence.binary.cv'];

module.exports = { toWhatIfModel, FIXTURES };
