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
// WP-A7: `question`, the question the result answers (the engine's `values.question`), which
// titles its card.
const CARD_KEYS = ['slot', 'activity', 'column', 'resultId', 'current', 'kind', 'question', 'data'];

// Gallery order (§6.3): the target, the special values, the by-column results, then the
// distributions; by column name inside a group.
// WP-A7: the single-feature signal (the leakage detector) after the special values, and
// the structural quality check of the development rows last (the view shows it with the data
// card, apart from the training-row gallery).
const ORDER = {
  'eda.target_rate': 0, 'eda.target_summary': 0, 'eda.special_values': 1, 'eda.single_feature_signal': 2,
  'eda.rate_by': 3, 'eda.mean_by': 3, 'eda.distribution': 4, 'eda.quality': 5,
  // v0.3 (WP-E2, R28): the predictor matrix after the single-feature signal.
  'eda.correlation': 2.5,
};
const KINDS = {
  'eda.target_rate': 'target_rate', 'eda.target_summary': 'target_summary', 'eda.special_values': 'special_values',
  'eda.rate_by': 'rate_by', 'eda.mean_by': 'mean_by', 'eda.distribution': 'distribution',
  'eda.single_feature_signal': 'signal', 'eda.quality': 'quality', 'eda.correlation': 'correlation',
};
// v0.3 (WP-E2): the catalog activities the panel may run without a column (W4): structural
// readings of the development rows that never read the target.
const WHOLE_STUDY = Object.freeze(['eda.correlation']);

// Precision of each number, from framework/mlkit/study/content/activities.yaml (highlights
// and table columns). `eda.distribution` has no display specification yet (WP-E3 adds it):
// counts are `int`, shares `pct1`, and quantiles `auto`, the format of `cite` for a value
// without a declared precision. test/eda.test.js reads the YAML and checks this table.
// WP-A7: an interval or a null band has the precision of the value it bounds; the
// single-feature score has two decimals, as the engine's own question text writes it.
const FMT = Object.freeze({
  'eda.target_rate': { rate: 'pct1', n_positive: 'int', n_negative: 'int', n_rows: 'int', low: 'pct1', high: 'pct1' },
  'eda.target_summary': { n_rows: 'int', n_missing: 'int', mean: 'f2', sd: 'f2', min: 'f2', q25: 'f2', median: 'f2',
    q75: 'f2', max: 'f2', low: 'f2', high: 'f2' },
  'eda.special_values': { n_rows: 'int', share: 'pct1', n_positive: 'int', rate: 'pct1', mean_target: 'f2', n_both: 'int',
    n_either: 'int', low: 'pct1', high: 'pct1' },
  'eda.rate_by': { n_rows: 'int', overall_rate: 'pct1', min_group_rows: 'int', n_positive: 'int', rate: 'pct1',
    low: 'pct1', high: 'pct1', observed: 'pct1', null_min: 'pct1', null_max: 'pct1', shuffles: 'int' },
  'eda.mean_by': { n_rows: 'int', overall_mean: 'f2', min_group_rows: 'int', mean: 'f2', sd: 'f2',
    low: 'f2', high: 'f2', observed: 'f2', null_min: 'f2', null_max: 'f2', shuffles: 'int' },
  'eda.single_feature_signal': { n_rows: 'int', folds: 'int', score: 'f2', median: 'f2', level: 'f2', gap: 'f2' },
  'eda.quality': { n_rows: 'int', n_columns: 'int', n_missing: 'int', share: 'pct1', n_rows_with_missing: 'int',
    n_groups: 'int', n_distinct: 'int', rare_rows: 'int', min: 'auto', max: 'auto', n_special: 'int', n_below: 'int',
    n_above: 'int' },
  'eda.distribution': { n_rows: 'int', n_missing: 'int', share: 'pct1', min_group_rows: 'int', n_values: 'int', n: 'int',
    min: 'auto', q25: 'auto', median: 'auto', q75: 'auto', max: 'auto', low: 'auto', high: 'auto', mean: 'auto' },
  // v0.3 (WP-E2): an association to two decimals, as the level it is compared with.
  'eda.correlation': { n_rows: 'int', value: 'f2', level: 'f2', n_flagged: 'int' },
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

/** An engine interval `{low, high}` at `path` as two cited values, or null (WP-A7). */
function interval(v, path, f) {
  const low = cite(v, `${path}.low`, f.low);
  const high = cite(v, `${path}.high`, f.high);
  return low && high ? { low, high } : null;
}

function targetRate(v, f) {
  const rate = cite(v, 'rate', f.rate);
  return {
    target: str(v.target), positiveLabel: label(v.positive_label),
    rate, nPositive: cite(v, 'n_positive', f.n_positive), nNegative: cite(v, 'n_negative', f.n_negative),
    nRows: cite(v, 'n_rows', f.n_rows), interval: interval(v, 'interval', f),
    imbalanced: rate !== null && (rate.value < IMBALANCE.low || rate.value > IMBALANCE.high),
  };
}

function targetSummary(v, f) {
  const out = { target: str(v.target), unit: str(v.unit), note: str(v.note) };
  for (const [key, name] of [['n_rows', 'nRows'], ['n_missing', 'nMissing'], ['mean', 'mean'], ['sd', 'sd'], ['min', 'min'],
    ['q25', 'q25'], ['median', 'median'], ['q75', 'q75'], ['max', 'max']]) out[name] = cite(v, key, f[key]);
  out.meanInterval = interval(v, 'mean_interval', f);
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
      interval: interval(v, `special_values.${i}.interval`, f),
    })),
    together: list(v.co_occurrence).map((c, i) => ({ c, i })).filter(({ c }) => c && c.same_rows === true).map(({ c, i }) => ({
      a: { column: str(obj(c.a).column), value: label(obj(c.a).value) },
      b: { column: str(obj(c.b).column), value: label(obj(c.b).value) },
      nBoth: cite(v, `co_occurrence.${i}.n_both`, f.n_both),
    })),
  };
}

/** The permutation null band of a by-column chart (CLI-CONTRACT §11.2), or null. */
function nullBand(v, f) {
  const band = obj(v.null_band);
  const chart = obj(band.chart);
  if (!Object.keys(chart).length) return null;
  return {
    statistic: str(chart.statistic), observed: cite(v, 'null_band.chart.observed', f.observed),
    nullMin: cite(v, 'null_band.chart.null_min', f.null_min), nullMax: cite(v, 'null_band.chart.null_max', f.null_max),
    outside: chart.outside === true, shuffles: cite(v, 'null_band.shuffles', f.shuffles), note: str(band.note),
  };
}

function byColumn(v, f, measure) {
  const other = v.other && typeof v.other === 'object' ? v.other : null;
  return {
    nullBand: nullBand(v, f),
    column: str(v.column), unit: str(v.unit), note: str(v.note), warnings: list(v.warnings).map(str),
    nRows: cite(v, 'n_rows', f.n_rows), minGroupRows: cite(v, 'min_group_rows', f.min_group_rows),
    overall: cite(v, measure === 'rate' ? 'overall_rate' : 'overall_mean', measure === 'rate' ? f.overall_rate : f.overall_mean),
    groups: list(v.groups).map((g, i) => ({
      label: label(g && g.value), small: bool(g && g.small_count),
      value: cite(v, `groups.${i}.${measure}`, f[measure]), nRows: cite(v, `groups.${i}.n_rows`, f.n_rows),
      nPositive: measure === 'rate' ? cite(v, `groups.${i}.n_positive`, f.n_positive) : null,
      sd: measure === 'mean' ? cite(v, `groups.${i}.sd`, f.sd) : null,
      interval: interval(v, `groups.${i}.interval`, f),
      band: interval(v, `groups.${i}.null_band`, f),
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
      mean: cite(v, 'numeric.mean', f.mean),
      // v0.3 (WP-E2, R17): the exact zeros apart and log bins of a skewed column (engine keys).
      zeros: n.zeros && typeof n.zeros === 'object' ? { nRows: cite(v, 'numeric.zeros.n_rows', f.n_rows),
        share: cite(v, 'numeric.zeros.share', f.share) } : null,
      skewed: n.skewed === true && Array.isArray(n.log_bins) && n.log_bins.length > 0,
      logBins: list(n.log_bins).map((b, i) => ({
        low: num(b && b.low), high: num(b && b.high), closed: str(b && b.closed),
        lowCited: cite(v, `numeric.log_bins.${i}.low`, f.low), highCited: cite(v, `numeric.log_bins.${i}.high`, f.high),
        nRows: cite(v, `numeric.log_bins.${i}.n_rows`, f.n_rows), share: cite(v, `numeric.log_bins.${i}.share`, f.share),
      })),
      bins: list(n.bins).map((b, i) => ({
        low: num(b && b.low), high: num(b && b.high), closed: str(b && b.closed),
        // The edges as cited engine values (WP-I, U4 request: the histogram cites them).
        lowCited: cite(v, `numeric.bins.${i}.low`, f.low), highCited: cite(v, `numeric.bins.${i}.high`, f.high),
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

/** The single-feature signal (the leakage detector, CLI-CONTRACT §11.2). */
function signal(v, f) {
  return {
    metric: str(v.metric), nRows: cite(v, 'n_rows', f.n_rows), folds: cite(v, 'folds', f.folds), note: str(v.note),
    median: cite(v, 'median', f.median), level: cite(v, 'level', f.level),
    signals: list(v.signals).map((s, i) => ({
      feature: str(s && s.feature), availability: strOrNull(s && s.availability), flag: bool(s && s.flag),
      rank: int(s && s.rank), score: cite(v, `signals.${i}.score`, f.score),
    })),
    questions: list(v.questions).map((q, i) => ({
      feature: str(q && q.feature), availability: strOrNull(q && q.availability),
      score: cite(v, `questions.${i}.score`, f.score), text: str(q && q.text),
    })),
  };
}

/** The structural quality of the development rows (the target is not read). */
function quality(v, f) {
  const dup = obj(v.duplicates);
  return {
    partition: str(v.partition), nRows: cite(v, 'n_rows', f.n_rows), nColumns: cite(v, 'n_columns', f.n_columns),
    targetRead: v.target_read === true, note: str(v.note),
    nRowsWithMissing: cite(v, 'n_rows_with_missing', f.n_rows_with_missing),
    missing: list(v.missing).map((m, i) => ({ column: str(m && m.column), nMissing: cite(v, `missing.${i}.n_missing`, f.n_missing),
      share: cite(v, `missing.${i}.share`, f.share) })).filter(m => m.nMissing && m.nMissing.value > 0),
    coMissing: list(v.co_missing).map((m, i) => ({ columns: list(m && m.columns).map(str),
      nRows: cite(v, `co_missing.${i}.n_rows`, f.n_rows), share: cite(v, `co_missing.${i}.share`, f.share) })),
    duplicates: { nRows: cite(v, 'duplicates.n_rows', f.n_rows), nGroups: cite(v, 'duplicates.n_groups', f.n_groups),
      definition: str(dup.definition) },
    rare: list(v.cardinality).map((c, i) => ({ column: str(c && c.column), nDistinct: cite(v, `cardinality.${i}.n_distinct`, f.n_distinct),
      rareRows: cite(v, `cardinality.${i}.rare_rows`, f.rare_rows),
      rare: list(c && c.rare).map((r, j) => ({ value: label(r && r.value), nRows: cite(v, `cardinality.${i}.rare.${j}.n_rows`, f.n_rows) })) }))
      .filter(c => c.rare.length),
    ranges: list(v.ranges).map((r, i) => ({ column: str(r && r.column), min: cite(v, `ranges.${i}.min`, f.min),
      max: cite(v, `ranges.${i}.max`, f.max), declared: Boolean(r && r.declared),
      nBelow: cite(v, `ranges.${i}.n_below`, f.n_below), nAbove: cite(v, `ranges.${i}.n_above`, f.n_above) })),
  };
}

/** v0.3 (WP-E2, R28): the predictor-versus-predictor association matrix (no target). */
function correlation(v, f) {
  const columns = list(v.columns).filter(c => c && typeof c.name === 'string').map(c => ({ name: c.name, kind: str(c.kind) }));
  const names = columns.map(c => c.name);
  const order = list(v.order).filter(n => names.includes(n));
  return {
    partition: str(v.partition), targetRead: v.target_read === true, note: str(v.note),
    nRows: cite(v, 'n_rows', f.n_rows), level: cite(v, 'level', f.level), nFlagged: cite(v, 'n_flagged', f.n_flagged),
    columns, order: order.length === names.length ? order : names,
    measures: Object.fromEntries(Object.entries(obj(v.measures)).map(([k, t]) => [k, str(t)])),
    pairs: list(v.pairs).map((p, i) => ({ a: str(p && p.a), b: str(p && p.b), measure: str(p && p.measure),
      flag: bool(p && p.flag), value: cite(v, `pairs.${i}.value`, f.value), nRows: cite(v, `pairs.${i}.n_rows`, f.n_rows) })),
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
    case 'eda.single_feature_signal': return signal(v, f);
    case 'eda.quality': return quality(v, f);
    case 'eda.correlation': return correlation(v, f);
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
  const values = obj(r.values);
  return {
    slot: str(r.slot), activity, column: columnOf(r), resultId: str(r.result_id), current,
    kind: KINDS[activity], question: current ? str(values.question) : '', data: current ? cardData(activity, r.values) : null,
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
    // WP-A9 (M5): the rows the activity reads; the panel runs training-row charts only.
    // An engine before WP-A9 lists training-row activities only (no `partition`).
    partition: typeof a.partition === 'string' ? a.partition : 'train',
    missing: list(a.missing).map(missingText).filter(Boolean),
    columns: list(a.columns).filter(c => c && typeof c.name === 'string' && c.name).map(c => ({
      name: c.name, role: str(c.role), type: str(c.type), slot: strOrNull(c.slot), resultId: strOrNull(c.result_id),
    })),
  }));
}

// WP-B1 cross-validation records its exposure on the `development` partition (no train or
// validation partition exists); a single split records `train` and `validation`.
const CV_PURPOSES = ['cross_validated_fit', 'out_of_fold_evaluation', 'out_of_fold_policy_selection'];

/**
 * The rows the EDA read, split-aware (WP-E1, R26): `scope` is `development` under
 * cross-validation (EDA reads the development rows; there is no validation partition) and
 * `split` otherwise. `trainEda` counts the rows EDA read in the explored partition (the
 * training rows of a split, the development rows under cross-validation).
 */
function rowsSeenOf(payload) {
  const exposure = obj(payload.exposure);
  const ledger = list(exposure.ledger).map(obj);
  const eda = ledger.filter(r => r.purpose === 'train_eda');
  const cv = eda.some(r => r.partition === 'development') || ledger.some(r => CV_PURPOSES.includes(r.purpose));
  const rowsIn = partition => eda.filter(r => r.partition === partition).reduce((sum, r) => sum + (int(r.rows) || 0), 0);
  return {
    scope: cv ? 'development' : 'split',
    trainEda: cv ? rowsIn('development') : rowsIn('train'),
    validationEda: cv ? 0 : rowsIn('validation'),
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
  const a = list(model && model.catalog).find(x => x.activity === activity && x.perColumn && x.runnable
    && x.partition === 'train');
  if (!a) return null;
  return a.columns.find(c => c.name === column) || null;
}

/** v0.3 (WP-E2): the catalog entry that lets the panel run `activity` without a column. */
function requestableWhole(model, activity) {
  if (!WHOLE_STUDY.includes(activity)) return null;
  return list(model && model.catalog).find(x => x.activity === activity && !x.perColumn && x.runnable) || null;
}

module.exports = { toEdaModel, requestable, requestableWhole, WHOLE_STUDY, EDA_KEYS, CARD_KEYS, FMT, IMBALANCE, ORDER, FIXTURES, EVIDENCE_SCHEMA, ModelError };
