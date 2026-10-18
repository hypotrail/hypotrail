'use strict';
// PolicyPreviewModel: a pure projection of `hypotrail.preview/1` (`preview policy`,
// CLI-CONTRACT §8.1) for the What if? sandbox (COMPANION-ADVANCED §6.5.1, §9). WP-U3.
// These values are an experiment computed from saved predictions: the view shows them only
// inside the What if? tab, under "Experiment, not adopted" (INV-6, INV-7 b, WI-5).
//
// Keys (§9): rules, byRule{rule: {models: {fit: {selected, truePositives, precision,
// recall, volume, tiedAtCut}}, intervals, deltas}}, adopted, note, modelsCurrent; plus
// revision, fits (candidate first), warnings.

const { str, strOrNull, list, obj, int, num, expectSchema, plain } = require('./common');
const { side } = require('./evidence');

const SCHEMA = 'hypotrail.preview/1';

function range(raw) {
  const r = obj(raw);
  const low = num(r.low);
  const high = num(r.high);
  return { point: num(r.point), low, high, side: side(low, high), undefinedReplicates: int(r.undefined_replicates) };
}

function toPolicyPreviewModel(payload) {
  const p = expectSchema(payload, SCHEMA);
  const rules = list(p.rules).map(str);
  const models = obj(p.models);
  const allFits = Object.keys(models);
  const intervalsAll = obj(p.intervals);
  const reference = rules.map(r => strOrNull(obj(intervalsAll[r]).reference)).find(Boolean) || 'fit.baseline';
  const fits = [...allFits.filter(f => f !== reference), ...allFits.filter(f => f === reference)];
  const byRule = {};
  for (const rule of rules) {
    const ev = obj(obj(p.evaluations)[rule]);
    const iv = intervalsAll[rule] && typeof intervalsAll[rule] === 'object' ? intervalsAll[rule] : null;
    byRule[rule] = {
      models: Object.fromEntries(fits.map(fit => {
        const m = obj(ev[fit]);
        return [fit, { selected: num(m.selected), truePositives: num(m.true_positives), precision: num(m.precision),
          recall: num(m.recall), volume: num(m.volume), tiedAtCut: num(m.tied_at_cut), n: int(m.n), nPositive: int(m.n_positive) }];
      })),
      intervals: iv ? Object.fromEntries(fits.map(fit => {
        const i = obj(obj(iv.intervals)[fit]);
        return [fit, { precision: range(i.precision), recall: range(i.recall) }];
      })) : null,
      deltas: iv ? Object.fromEntries(Object.entries(obj(iv.deltas)).map(([fit, d]) => [fit,
        { precision: range(obj(d).precision), recall: range(obj(d).recall) }])) : null,
      bootstrap: iv ? { replicates: int(iv.replicates), level: num(iv.level), method: strOrNull(iv.method) } : null,
    };
  }
  const adopted = p.adopted && typeof p.adopted === 'object'
    ? { status: str(p.adopted.status), value: str(p.adopted.value) } : null;
  return plain({
    revision: int(p.revision),
    rules,
    fits,
    reference,
    byRule,
    adopted,
    note: str(p.note),
    modelsCurrent: allFits.length > 0 && allFits.every(f => obj(models[f]).current === true),
    warnings: list(p.warnings).map(w => (typeof w === 'string' ? w : str(obj(w).message || obj(w).text))).filter(Boolean),
  });
}

const FIXTURES = ['preview.binary'];

module.exports = { toPolicyPreviewModel, FIXTURES };
