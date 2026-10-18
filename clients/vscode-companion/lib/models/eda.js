'use strict';
// EdaModel: a pure projection of `hypotrail.evidence/1` (CLI-CONTRACT-COMPANION §5, §8) for
// the EDA tab (COMPANION-ADVANCED §6.3, §9). It keeps the promoted results of the `eda.*`
// activities, in the gallery order of §6.3, the EDA catalog (the only source of the
// columns the panel may request, INV-13), and the rows seen in EDA from the exposure ledger.
//
// Nothing is computed here. Every number of a card is an engine value carried as
// `{value, path, fmt}`: `path` addresses the result's `values` as `mlkit.study.cite` does
// (dots, list indices), and `fmt` is the precision of `content/activities.yaml`, so the view
// formats it with media/format.js and cites it with the card's result id. A result that is
// not current, or not verified, has `data: null` and is listed "Stale · not cited" (INV-7).
// Owned by WP-U4.

const { ModelError, str, strOrNull, list, obj, int, num, bool, expectSchema } = require('./common');

const EVIDENCE_SCHEMA = 'hypotrail.evidence/1';
const EDA_KEYS = ['revision', 'task', 'cards', 'catalog', 'rowsSeen'];
const CARD_KEYS = ['slot', 'activity', 'column', 'resultId', 'current', 'kind', 'data'];

// Gallery order (§6.3): the target, the special values, the by-column results, then the
// distributions; by column name inside a group.
const ORDER = {
  'eda.target_rate': 0, 'eda.target_summary': 0, 'eda.special_values': 1,
  'eda.rate_by': 2, 'eda.mean_by': 2, 'eda.distribution': 3,
};
const KINDS = {
  'eda.target_rate': 'target_rate', 'eda.target_summary': 'target_summary', 'eda.special_values': 'special_values',
  'eda.rate_by': 'rate_by', 'eda.mean_by': 'mean_by', 'eda.distribution': 'distribution',
};

// Precision of each number, from framework/mlkit/study/content/activities.yaml (highlights
// and table columns). `eda.distribution` has no display specification yet (WP-E3 adds it):
// counts are `int`, shares `pct1`, and quantiles `auto`, the format of `cite` for a value
// without a declared precision. test/eda.test.js reads the YAML and checks this table.
const FMT = Object.freeze({
  'eda.target_rate': { rate: 'pct1', n_positive: 'int', n_negative: 'int', n_rows: 'int' },
  'eda.target_summary': { n_rows: 'int', n_missing: 'int', mean: 'f2', sd: 'f2', min: 'f2', q25: 'f2', median: 'f2',
    q75: 'f2', max: 'f2' },
  'eda.special_values': { n_rows: 'int', share: 'pct1', n_positive: 'int', rate: 'pct1', mean_target: 'f2', n_both: 'int',
    n_either: 'int' },
  'eda.rate_by': { n_rows: 'int', overall_rate: 'pct1', min_group_rows: 'int', n_positive: 'int', rate: 'pct1' },
  'eda.mean_by': { n_rows: 'int', overall_mean: 'f2', min_group_rows: 'int', mean: 'f2', sd: 'f2' },
  'eda.distribution': { n_rows: 'int', n_missing: 'int', share: 'pct1', min_group_rows: 'int', n_values: 'int', n: 'int',
    min: 'auto', q25: 'auto', median: 'auto', q75: 'auto', max: 'auto' },
});
// Class imbalance (§6.3): the term is introduced when the positive share is below or above these.
const IMBALANCE = Object.freeze({ low: 0.2, high: 0.8 });

const FIXTURES = ['evidence.binary', 'evidence.regression', 'evidence.binary.detail'];

/** One engine number of `values` at `path`, with its format; null when it is not a number. */
function cite(values, path, fmt) {
  let at = values;
  for (const seg of path.split('.')) {
    if (at === null || at === undefined) return null;
    at = Array.isArray(at) ? at[Number(seg)] : at[seg];
  }
  const value = num(at);
  return value === null ? null : { value, path, fmt };
}

/** A recorded value shown as text (a group label, a special value code). */
function label(value) {
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return value === null || value === undefined ? '' : JSON.stringify(value);
}

function targetRate(v, f) {
  const rate = cite(v, 'rate', f.rate);
  return {
    target: str(v.target), positiveLabel: label(v.positive_label),
    rate, nPositive: cite(v, 'n_positive', f.n_positive), nNegative: cite(v, 'n_negative', f.n_negative),
    nRows: cite(v, 'n_rows', f.n_rows),
    imbalanced: rate !== null && (rate.value < IMBALANCE.low || rate.value > IMBALANCE.high),
  };
}

function targetSummary(v, f) {
  const out = { target: str(v.target), unit: str(v.unit), note: str(v.note) };
  for (const [key, name] of [['n_rows', 'nRows'], ['n_missing', 'nMissing'], ['mean', 'mean'], ['sd', 'sd'], ['min', 'min'],
    ['q25', 'q25'], ['median', 'median'], ['q75', 'q75'], ['max', 'max']]) out[name] = cite(v, key, f[key]);
  return out;
}

function specialValues(v, f) {
  return {
    nRows: cite(v, 'n_rows', f.n_rows), note: str(v.note), unit: str(v.unit),
    rows: list(v.special_values).map((s, i) => ({
      column: str(s && s.column), value: label(s && s.value), meaning: str(s && s.meaning),
      nRows: cite(v, `special_values.${i}.n_rows`, f.n_rows), share: cite(v, `special_values.${i}.share`, f.share),
      nPositive: cite(v, `special_values.${i}.n_positive`, f.n_positive), rate: cite(v, `special_values.${i}.rate`, f.rate),
      meanTarget: cite(v, `special_values.${i}.mean_target`, f.mean_target),
    })),
    together: list(v.co_occurrence).map((c, i) => ({ c, i })).filter(({ c }) => c && c.same_rows === true).map(({ c, i }) => ({
      a: { column: str(obj(c.a).column), value: label(obj(c.a).value) },
      b: { column: str(obj(c.b).column), value: label(obj(c.b).value) },
      nBoth: cite(v, `co_occurrence.${i}.n_both`, f.n_both),
    })),
  };
}

function byColumn(v, f, measure) {
  const other = v.other && typeof v.other === 'object' ? v.other : null;
  return {
    column: str(v.column), unit: str(v.unit), note: str(v.note), warnings: list(v.warnings).map(str),
    nRows: cite(v, 'n_rows', f.n_rows), minGroupRows: cite(v, 'min_group_rows', f.min_group_rows),
    overall: cite(v, measure === 'rate' ? 'overall_rate' : 'overall_mean', measure === 'rate' ? f.overall_rate : f.overall_mean),
    groups: list(v.groups).map((g, i) => ({
      label: label(g && g.value), small: bool(g && g.small_count),
      value: cite(v, `groups.${i}.${measure}`, f[measure]), nRows: cite(v, `groups.${i}.n_rows`, f.n_rows),
      nPositive: measure === 'rate' ? cite(v, `groups.${i}.n_positive`, f.n_positive) : null,
      sd: measure === 'mean' ? cite(v, `groups.${i}.sd`, f.sd) : null,
    })),
    other: other ? {
      value: cite(v, `other.${measure}`, f[measure]), nRows: cite(v, 'other.n_rows', f.n_rows),
      nValues: cite(v, 'other.n_values', 'int'), small: bool(other.small_count),
    } : null,
  };
}

function distribution(v, f) {
  const n = v.numeric && typeof v.numeric === 'object' ? v.numeric : null;
  const other = v.other && typeof v.other === 'object' ? v.other : null;
  return {
    column: str(v.column), role: str(v.role), type: str(v.type), distKind: str(v.kind), partition: str(v.partition),
    nRows: cite(v, 'n_rows', f.n_rows), nMissing: cite(v, 'n_missing', f.n_missing),
    minGroupRows: cite(v, 'min_group_rows', f.min_group_rows), note: str(v.note), warnings: list(v.warnings).map(str),
    specials: list(v.special_values).map((s, i) => ({
      value: label(s && s.value), meaning: str(s && s.meaning),
      nRows: cite(v, `special_values.${i}.n_rows`, f.n_rows), share: cite(v, `special_values.${i}.share`, f.share),
    })),
    numeric: n ? {
      n: cite(v, 'numeric.n', f.n), min: cite(v, 'numeric.min', f.min), q25: cite(v, 'numeric.q25', f.q25),
      median: cite(v, 'numeric.median', f.median), q75: cite(v, 'numeric.q75', f.q75), max: cite(v, 'numeric.max', f.max),
      bins: list(n.bins).map((b, i) => ({
        low: num(b && b.low), high: num(b && b.high), closed: str(b && b.closed),
        nRows: cite(v, `numeric.bins.${i}.n_rows`, f.n_rows), share: cite(v, `numeric.bins.${i}.share`, f.share),
      })),
    } : null,
    groups: list(v.groups).map((g, i) => ({
      label: label(g && g.value), small: bool(g && g.small_count),
      nRows: cite(v, `groups.${i}.n_rows`, f.n_rows), share: cite(v, `groups.${i}.share`, f.share),
    })),
    other: other ? { nRows: cite(v, 'other.n_rows', f.n_rows), share: cite(v, 'other.share', f.share),
      nValues: cite(v, 'other.n_values', f.n_values) } : null,
  };
}

function cardData(activity, values) {
  const v = obj(values);
  const f = FMT[activity];
  switch (activity) {
    case 'eda.target_rate': return targetRate(v, f);
    case 'eda.target_summary': return targetSummary(v, f);
    case 'eda.special_values': return specialValues(v, f);
    case 'eda.rate_by': return byColumn(v, f, 'rate');
    case 'eda.mean_by': return byColumn(v, f, 'mean');
    default: return distribution(v, f);
  }
}

function columnOf(r) {
  const params = obj(r.params);
  if (typeof params.column === 'string') return params.column;
  const slot = str(r.slot);
  return slot.includes(':') ? slot.slice(slot.indexOf(':') + 1) : null;
}

function card(r) {
  const activity = str(r.activity);
  const current = r.current === true && r.integrity === 'ok' && r.values !== null && typeof r.values === 'object';
  return {
    slot: str(r.slot), activity, column: columnOf(r), resultId: str(r.result_id), current,
    kind: KINDS[activity], data: current ? cardData(activity, r.values) : null,
  };
}

function missingText(m) {
  if (typeof m === 'string') return m;
  const o = obj(m);
  if (typeof o.detail === 'string' && o.detail) return o.detail;
  if (o.requirement === 'decision_confirmed' && typeof o.decision === 'string') return `the decision ${o.decision} is confirmed`;
  if (o.requirement === 'result_current' && typeof o.slot === 'string') return `a current ${o.slot} result`;
  return [str(o.requirement), str(o.slot || o.decision)].filter(Boolean).join(' ');
}

function catalogOf(payload) {
  return list(obj(payload.eda_catalog).activities).filter(a => a && typeof a.activity === 'string').map(a => ({
    activity: a.activity, label: a.activity, perColumn: bool(a.per_column), runnable: bool(a.runnable),
    missing: list(a.missing).map(missingText).filter(Boolean),
    columns: list(a.columns).filter(c => c && typeof c.name === 'string' && c.name).map(c => ({
      name: c.name, role: str(c.role), type: str(c.type), slot: strOrNull(c.slot), resultId: strOrNull(c.result_id),
    })),
  }));
}

function rowsSeenOf(payload) {
  const exposure = obj(payload.exposure);
  const ledger = list(exposure.ledger).map(obj);
  const train = ledger.find(r => r.purpose === 'train_eda' && r.partition === 'train');
  const validation = ledger.filter(r => r.purpose === 'train_eda' && r.partition === 'validation')
    .reduce((sum, r) => sum + (int(r.rows) || 0), 0);
  return {
    trainEda: train ? int(train.rows) || 0 : 0,
    validationEda: validation,
    validationModels: int(obj(exposure.summary).validation_rows_used_for_selection),
  };
}

/** `hypotrail.evidence/1` -> EdaModel (§9). Throws ModelError for another schema. */
function toEdaModel(payload) {
  expectSchema(payload, EVIDENCE_SCHEMA);
  const task = payload.task === 'binary' || payload.task === 'regression' ? payload.task : null;
  const cards = list(payload.results)
    .filter(r => r && typeof r.activity === 'string' && Object.prototype.hasOwnProperty.call(KINDS, r.activity) && r.promoted === true)
    .map(card)
    .sort((a, b) => (ORDER[a.activity] - ORDER[b.activity]) || String(a.column || '').localeCompare(String(b.column || ''), 'en')
      || a.activity.localeCompare(b.activity, 'en'));
  return { revision: int(payload.revision) || 0, task, cards, catalog: catalogOf(payload), rowsSeen: rowsSeenOf(payload) };
}

/** The catalog entry that lets the panel request `activity` on `column` (§7 W4), or null. */
function requestable(model, activity, column) {
  const a = list(model && model.catalog).find(x => x.activity === activity && x.perColumn && x.runnable);
  if (!a) return null;
  return a.columns.find(c => c.name === column) || null;
}

module.exports = { toEdaModel, requestable, EDA_KEYS, CARD_KEYS, FMT, IMBALANCE, ORDER, FIXTURES, EVIDENCE_SCHEMA, ModelError };
