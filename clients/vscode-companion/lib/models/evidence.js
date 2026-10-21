'use strict';
// EvidenceModel: a pure projection of `hypotrail.evidence/1` (CLI-CONTRACT-COMPANION §5) for
// the Evidence tab (COMPANION-ADVANCED §6.4, §9). WP-U3.
//
// INV-7: a figure reaches the webview only from a result that is current and verified.
// Results that are stale or fail their integrity check carry no values, no headline, and
// no row count here; the view lists them with "Not cited". Nothing is computed from the
// figures: the model selects, renames, and orders engine values, and derives only the
// position of an interval against 0 (which of the fixed sentences of §6.4 applies).
//
// Keys (§9): revision, task, results, ledger, lineage, impacts, sources, detail,
// uncertainty; plus truncated and splitOverlap (the "explored rows" sentence of §6.4).
// WP-B5 (v0.2b) adds, all read from current, verified results only: crossValidation (the
// scheme of the split in values, and the spread across folds of each fit), variant (the
// variant against the candidate, paired), gain (the gain points and the share of each
// evaluated rule), finalEvaluation (the one evaluation of the final test), and diagnostics
// (the `diag.*` results of WP-B4, CLI-CONTRACT §13; see diagnosticsOf).

const { ModelError, str, strOrNull, list, obj, int, num, bool, expectSchema, segments, plain } = require('./common');

const SCHEMA = 'hypotrail.evidence/1';
const RESULT_ID = /^[0-9a-f]{64}$/;
// The order of artefact chips in a lineage (CLI-CONTRACT §8.3).
const ARTIFACT_ORDER = ['report', 'notebook', 'workbench'];
// Purposes whose rows chose something (§6.4: the highlighted ledger row). WP-B5: under
// cross-validation the choice reads out-of-fold predictions of the development rows.
const SELECTION_PURPOSES = {
  binary: [['validation_policy_selection', 'validation'], ['out_of_fold_policy_selection', 'development']],
  regression: [['validation_model_evaluation', 'validation'], ['out_of_fold_evaluation', 'development']],
};
const isSelection = (task, purpose, partition) => (SELECTION_PURPOSES[task] || [])
  .some(([p, part]) => p === purpose && part === partition);

const rid8 = id => String(id || '').slice(0, 8);

function staleReason(raw) {
  if (!raw || typeof raw !== 'object') return null;
  return {
    reason: strOrNull(raw.reason),
    codeChanged: list(raw.code_changed).map(str),
    upstreamNotCurrent: list(raw.upstream_not_current).map(x => rid8(str(x))),
    // The engine lists the changed sources (`['dataset']`, read.currency); older payloads
    // carried a boolean (WP-I drift fix).
    sourcesChanged: Array.isArray(raw.sources_changed) ? raw.sources_changed.length > 0 : bool(raw.sources_changed),
  };
}

/** True when the engine lets a client show this result's figures (CC §5 `values`). */
function citable(r) {
  return r.current === true && r.integrity === 'ok' && r.values !== null && typeof r.values === 'object';
}

function resultItem(r) {
  const cited = citable(r);
  const params = obj(r.params);
  return {
    resultId: str(r.result_id),
    rid8: rid8(r.result_id),
    activity: str(r.activity),
    slot: strOrNull(r.slot),
    promoted: bool(r.promoted),
    current: cited,
    integrity: str(r.integrity),
    staleReason: staleReason(r.stale_reason),
    partition: strOrNull(r.partition),
    nRows: cited ? int(r.n_rows) : null,
    headline: cited && r.headline ? segments(r.headline) : null,
    // Rule identifiers of an evaluation are parameters, not figures (§6.5.1 "Rule").
    rules: list(params.rules).map(str),
  };
}

/** Paired interval side: which fixed sentence of §6.4 applies. */
function side(low, high) {
  if (low === null || high === null) return 'undefined';
  return low > 0 || high < 0 ? 'one_side' : 'includes_zero';
}

function interval(raw, path) {
  const r = obj(raw);
  const low = num(r.low);
  const high = num(r.high);
  return { point: num(r.point), low, high, undefinedReplicates: int(r.undefined_replicates), path };
}

function bootstrapOf(values) {
  const b = obj(values.bootstrap);
  return { replicates: int(b.replicates), level: num(b.level), method: strOrNull(b.method) };
}

/** Candidate first, the reference last (the logistic or linear model, then the baseline). */
function orderFits(fits, reference) {
  return [...fits.filter(f => f !== reference), ...fits.filter(f => f === reference)];
}

/** Interval rows of a current `policy.evaluation` (§6.4 E, binary). */
function policyUncertainty(r) {
  const v = obj(r.values);
  const params = obj(r.params);
  const reference = str(v.reference || params.reference) || 'fit.baseline';
  const fits = orderFits(list(params.models).map(str), reference);
  const rules = list(params.rules).map(str).filter(rule => obj(v.rules)[rule]);
  return {
    kind: 'policy',
    resultId: str(r.result_id),
    // WP-B5: `out_of_fold` under cross-validation, `validation` otherwise (null before WP-B1).
    evaluation: strOrNull(v.evaluation),
    reference,
    bootstrap: bootstrapOf(v),
    rules: rules.map(rule => {
      const entry = obj(obj(v.rules)[rule]);
      const candidate = fits.find(f => f !== reference) || null;
      return {
        rule,
        metrics: ['precision', 'recall'].map(metric => {
          const delta = candidate ? obj(obj(entry.deltas)[candidate])[metric] : null;
          const d = delta ? interval(delta, `rules.${rule}.deltas.[${candidate}].${metric}`) : null;
          return {
            metric,
            models: fits.map(fit => {
              const i = interval(obj(obj(entry.intervals)[fit])[metric], `rules.${rule}.intervals.[${fit}].${metric}`);
              return { fit, point: num(obj(obj(entry.models)[fit])[metric]), low: i.low, high: i.high,
                path: `rules.${rule}.models.[${fit}].${metric}` };
            }),
            delta: d ? { fit: candidate, ...d, side: side(d.low, d.high) } : null,
          };
        }),
      };
    }),
  };
}

/** Interval rows of a current `evaluate.regression` (§6.4 E, regression). */
function regressionUncertainty(r) {
  const v = obj(r.values);
  const params = obj(r.params);
  const reference = str(v.reference || params.reference) || 'fit.baseline';
  const fits = orderFits(list(params.models).map(str), reference);
  const candidate = str(v.candidate || params.candidate) || fits.find(f => f !== reference) || null;
  return {
    kind: 'regression',
    resultId: str(r.result_id),
    evaluation: strOrNull(v.evaluation),
    reference,
    candidate,
    unit: strOrNull(v.unit),
    bootstrap: bootstrapOf(v),
    metrics: ['mae', 'rmse'].map(metric => {
      const delta = candidate ? obj(obj(v.deltas)[candidate])[metric] : null;
      const d = delta ? interval(delta, `deltas.[${candidate}].${metric}`) : null;
      return {
        metric,
        models: fits.map(fit => {
          const i = interval(obj(obj(v.intervals)[fit])[metric], `intervals.[${fit}].${metric}`);
          return { fit, point: num(obj(obj(v.models)[fit])[metric]), low: i.low, high: i.high, path: `models.[${fit}].${metric}` };
        }),
        delta: d ? { fit: candidate, ...d, side: side(d.low, d.high) } : null,
      };
    }),
  };
}

function uncertaintyOf(r) {
  if (!r || !citable(r)) return null;
  if (r.activity === 'policy.evaluation' || r.slot === 'policy.evaluation') return policyUncertainty(r);
  if (r.activity === 'evaluate.regression' || r.slot === 'evaluate.regression') return regressionUncertainty(r);
  return null;
}

function lineageOf(raw) {
  const l = obj(raw);
  return {
    nodes: list(l.nodes).map(n => ({ id: str(n && n.id), kind: str(n && n.kind), label: str(n && n.label), status: str(n && n.status) })),
    edges: list(l.edges).map(e => ({ from: str(e && e.from), to: str(e && e.to), role: str(e && e.role) })),
  };
}

/**
 * The lineage chain of one result (§6.4 "Lineage", EV-6): its ancestors in dependency order
 * (a depth-first walk of the incoming edges, in the engine's edge order), the result, its
 * current consumer results, then the artefacts that consume it. A confirmed decision whose
 * label is that of the result it produces (the split decision and the split result) is one
 * chip: "split · your decision". Stale consumers are left out: they no longer depend on it.
 */
function chainFor(lineage, resultId, consumers = []) {
  const byId = new Map(lineage.nodes.map(n => [n.id, n]));
  if (!byId.has(resultId)) return { chain: [], edges: [] };
  const incoming = new Map();
  const outgoing = new Map();
  for (const e of lineage.edges) {
    if (!incoming.has(e.to)) incoming.set(e.to, []);
    if (!outgoing.has(e.from)) outgoing.set(e.from, []);
    incoming.get(e.to).push(e);
    outgoing.get(e.from).push(e);
  }
  const ancestors = [];
  const seen = new Set([resultId]);
  (function walk(id) {
    for (const e of incoming.get(id) || []) {
      if (seen.has(e.from) || !byId.has(e.from)) continue;
      seen.add(e.from);
      walk(e.from);
      ancestors.push(e.from);
    }
  })(resultId);
  const results = [];
  const artifacts = new Set();
  const queue = [resultId];
  const reached = new Set([resultId]);
  while (queue.length) {
    const id = queue.shift();
    for (const e of outgoing.get(id) || []) {
      const node = byId.get(e.to);
      if (!node || reached.has(e.to)) continue;
      reached.add(e.to);
      if (node.kind === 'artifact') artifacts.add(e.to);
      else if (node.kind === 'result' && node.status === 'current') { results.push(e.to); queue.push(e.to); }
    }
  }
  for (const name of consumers) if (byId.has(`artifact:${name}`)) artifacts.add(`artifact:${name}`);
  // Merge a decision into the result of the same label that it produces.
  const merged = new Map();
  for (const id of ancestors) {
    const node = byId.get(id);
    if (node.kind !== 'decision') continue;
    const target = (outgoing.get(id) || []).map(e => byId.get(e.to))
      .find(n => n && n.kind === 'result' && n.label === node.label && (ancestors.includes(n.id) || n.id === resultId));
    if (target) merged.set(target.id, node);
  }
  const mergedIds = new Set([...merged.values()].map(n => n.id));
  const chip = (id, role) => {
    const n = byId.get(id);
    const decision = merged.get(id);
    // `name`: what the chip is (a source by its role, `dataset` or `case`; else its label).
    return { id, name: n.kind === 'source' ? n.id : n.label, kind: n.kind, label: n.label, status: n.status, role,
      decision: decision ? decision.status : null };
  };
  const order = id => ARTIFACT_ORDER.indexOf(byId.get(id).label);
  const chain = [
    ...ancestors.filter(id => !mergedIds.has(id)).map(id => chip(id, 'ancestor')),
    chip(resultId, 'self'),
    ...results.map(id => chip(id, 'consumer')),
    ...[...artifacts].sort((a, b) => order(a) - order(b)).map(id => chip(id, 'consumer')),
  ];
  const label = id => {
    const n = byId.get(id);
    return n ? n.label : id;
  };
  const inChain = new Set([...chain.map(c => c.id), ...mergedIds]);
  const edges = lineage.edges.filter(e => inChain.has(e.from) && inChain.has(e.to))
    .map(e => ({ from: label(e.from), to: label(e.to), role: e.role }));
  return { chain, edges };
}

function impactItem(i) {
  const kept = list(i && i.kept_slots).map(str);
  return {
    decisionId: str(i && i.decision_id),
    mutation: str(i && i.mutation),
    change: str(i && i.change),
    staleSlots: list(i && i.stale_slots).map(str),
    keptSlots: kept,
    keptFits: kept.filter(s => s.startsWith('fit.')),
    refit: list(i && i.refit).map(str),
    reconfirm: list(i && i.reconfirm).map(str),
    notes: list(i && i.notes).map(str),
  };
}

function exposureOf(raw) {
  if (!raw || typeof raw !== 'object') return null;
  return { purpose: str(raw.purpose), partition: str(raw.partition), rows: int(raw.n_rows), activity: str(raw.activity) };
}

function detailOf(raw, rawResults, lineage, impacts) {
  if (!raw || typeof raw !== 'object' || !RESULT_ID.test(str(raw.result_id))) return null;
  const id = raw.result_id;
  const r = rawResults.find(x => x && x.result_id === id) || { result_id: id, values: raw.values };
  const item = resultItem({ ...r, values: raw.values === undefined ? r.values : raw.values });
  const cited = item.current;
  const values = cited ? obj(raw.values) : {};
  const params = obj(raw.params || r.params);
  const inputs = obj(raw.inputs);
  const code = obj(raw.code);
  const modules = Object.entries(obj(code.modules)).map(([name, m]) => ({ name, matches: obj(m).matches === true }));
  const consumers = list(raw.consumers).map(str);
  const hint = raw.notebook_hint && typeof raw.notebook_hint === 'object'
    ? { path: str(raw.notebook_hint.path), search: str(raw.notebook_hint.search) } : null;
  const { chain, edges } = chainFor(lineage, id, consumers);
  const nPositive = cited ? int(obj(values.validation).n_positive) ?? int(values.n_positive) : null;
  return {
    ...item,
    nPositive,
    features: cited || list(inputs.features).length ? { count: list(inputs.features).length, names: list(inputs.features).map(str) } : null,
    preprocessing: strOrNull(params.preprocessing),
    code: { fingerprint: strOrNull(code.fingerprint), modules, changed: modules.filter(m => !m.matches).map(m => m.name) },
    exposure: exposureOf(raw.exposure),
    consumers,
    reportAnchor: typeof raw.report_anchor === 'string' && raw.report_anchor === `r-${id}` ? raw.report_anchor : null,
    notebookHint: hint,
    chain,
    lineageEdges: edges,
    impacts: item.slot ? impacts.filter(i => i.staleSlots.includes(item.slot)) : [],
    uncertainty: uncertaintyOf({ ...r, values: raw.values === undefined ? r.values : raw.values }),
  };
}

// --- v0.2b (WP-B5): cross-validation, the variant, the gain, the final test, diagnostics --

/** One segment of a value path (CLI-CONTRACT-COMPANION §5, `cite.format_path`). */
const seg = x => (/[.[\]]/.test(String(x)) ? `[${x}]` : String(x));
const pathOf = (...parts) => parts.map(seg).join('.');

/** The promoted, current, verified result of `slot`, or null. */
function promotedOf(rawResults, slot) {
  return rawResults.find(r => r && r.promoted === true && r.slot === slot && citable(r)) || null;
}

/**
 * The scheme of the current split when it is a cross-validation (CLI-CONTRACT §12), and
 * the spread across folds of the current candidate and variant: mean, sd, min, max of each
 * metric, as the engine computed them. Null under a train/validation split.
 */
function crossValidationOf(rawResults, task) {
  const split = promotedOf(rawResults, 'split');
  const v = split ? obj(split.values) : {};
  if (!split || v.scheme !== 'cross_validation') return null;
  const dup = v.duplicates && typeof v.duplicates === 'object' ? v.duplicates : null;
  const groups = v.groups && typeof v.groups === 'object' ? v.groups : null;
  const fits = (task === 'regression' ? ['fit.linear', 'fit.variant'] : ['fit.logistic', 'fit.variant']).map(slot => {
    const r = promotedOf(rawResults, slot);
    const cv = r ? obj(obj(r.values).cross_validation) : null;
    if (!cv || !cv.spread) return null;
    return {
      fit: slot, resultId: str(r.result_id),
      metrics: Object.entries(obj(cv.spread)).map(([metric, x]) => {
        const m = obj(x);
        const at = k => pathOf('cross_validation', 'spread', metric, k);
        return { metric, mean: num(m.mean), sd: num(m.sd), min: num(m.min), max: num(m.max),
          paths: { mean: at('mean'), sd: at('sd'), min: at('min'), max: at('max') } };
      }),
    };
  }).filter(Boolean);
  return {
    resultId: str(split.result_id), method: str(v.method), folds: int(v.folds), seed: int(v.seed),
    stratifiedOn: strOrNull(v.stratified_on), nRows: int(v.n_rows), orderColumn: strOrNull(v.order_column),
    duplicates: dup ? { policy: strOrNull(dup.policy), nGroups: int(dup.n_groups), dividedGroups: int(dup.divided_groups) } : null,
    sharedGroups: groups ? { column: strOrNull(groups.column), inSeveralFolds: int(groups.groups_in_several_folds),
      rows: int(groups.rows_in_shared_groups) } : null,
    foldRows: list(v.fold_rows).map(f => ({ fold: int(f && f.fold), nRows: int(f && f.n_rows) })),
    fits,
  };
}

/**
 * The variant (CLI-CONTRACT §12): what it changes, and its paired comparison with the
 * candidate in the current evaluation (variant minus candidate), per rule for a binary
 * study, per error for a regression study. Null without a current variant.
 */
function variantOf(rawResults, task) {
  const fit = promotedOf(rawResults, 'fit.variant');
  if (!fit) return null;
  const fv = obj(fit.values);
  const kind = obj(fv.variant);
  const evaluation = promotedOf(rawResults, task === 'regression' ? 'evaluate.regression' : 'policy.evaluation');
  const ev = evaluation ? obj(evaluation.values) : {};
  const metric = (raw, path) => {
    const d = interval(raw, path);
    return { ...d, side: side(d.low, d.high) };
  };
  // Each model's value and interval on the same rows (candidate, variant, baseline), so the
  // difference is read next to what it is a difference of.
  const FITS = [task === 'regression' ? 'fit.linear' : 'fit.logistic', 'fit.variant', 'fit.baseline'];
  const modelsOf = (entry, m, prefix) => FITS.filter(f => obj(entry.models)[f]).map(f => {
    const i = obj(obj(obj(entry.intervals)[f])[m]);
    return { fit: f, point: num(obj(obj(entry.models)[f])[m]), low: num(i.low), high: num(i.high),
      path: pathOf(...prefix, 'models', f, m) };
  });
  let comparisons = [];
  let reference = null;
  if (evaluation && task === 'binary') {
    const rules = list(obj(evaluation.params).rules).map(str)
      .filter(rule => obj(obj(obj(ev.rules)[rule]).comparisons)['fit.variant']);
    comparisons = rules.map(rule => {
      const c = obj(obj(obj(obj(ev.rules)[rule]).comparisons)['fit.variant']);
      reference = reference || strOrNull(c.reference);
      const entry = obj(obj(ev.rules)[rule]);
      return { rule, metrics: ['precision', 'recall'].map(m => ({ metric: m,
        ...metric(c[m], pathOf('rules', rule, 'comparisons', 'fit.variant', m, 'point')),
        models: modelsOf(entry, m, ['rules', rule]) })) };
    });
  } else if (evaluation) {
    const c = obj(obj(ev.comparisons)['fit.variant']);
    if (Object.keys(c).length) {
      reference = strOrNull(c.reference);
      comparisons = [{ rule: null, metrics: ['mae', 'rmse'].map(m => ({ metric: m,
        ...metric(c[m], pathOf('comparisons', 'fit.variant', m, 'point')), models: modelsOf(ev, m, []) })) }];
    }
  }
  const ranking = task === 'binary' && ev.ranking ? Object.entries(obj(ev.ranking)).map(([slot, r]) => ({
    fit: slot, rocAuc: num(obj(r).roc_auc), path: pathOf('ranking', slot, 'roc_auc') })) : [];
  return {
    resultId: str(fit.result_id),
    kind: strOrNull(kind.kind), strength: strOrNull(kind.strength), group: strOrNull(kind.group),
    evaluationId: evaluation ? str(evaluation.result_id) : null,
    reference: reference || (task === 'regression' ? 'fit.linear' : 'fit.logistic'),
    comparisons,
    ranking,
    bootstrap: evaluation ? bootstrapOf(ev) : null,
  };
}

/**
 * The gain points of the current policy evaluation (v0.2b, WP-B3): for the top 5, 10 and
 * 20 % of the scored rows, the share of the positive rows reached (recall) and the
 * precision; plus every evaluated rule with the share of the rows it acts on
 * (`capacity_share`, the engine's). The panel draws them; it computes none of them.
 */
function gainOf(rawResults) {
  const r = promotedOf(rawResults, 'policy.evaluation');
  if (!r) return null;
  const v = obj(r.values);
  const g = v.gain_points && typeof v.gain_points === 'object' ? v.gain_points : null;
  if (!g) return null;
  const model = str(g.model) || 'fit.logistic';
  const points = list(g.points).map((p, i) => ({
    share: num(p && p.share), rule: strOrNull(p && p.rule), capacity: int(p && p.capacity),
    precision: num(p && p.precision), recall: num(p && p.recall), gainPoints: num(p && p.gain_points), lift: num(p && p.lift),
    paths: { share: pathOf('gain_points', 'points', i, 'share'), recall: pathOf('gain_points', 'points', i, 'recall'),
      precision: pathOf('gain_points', 'points', i, 'precision'), capacity: pathOf('gain_points', 'points', i, 'capacity') },
  })).filter(p => p.share !== null && p.recall !== null);
  const rules = list(obj(r.params).rules).map(str).map(rule => {
    const entry = obj(obj(v.rules)[rule]);
    const m = obj(obj(entry.models)[model]);
    return { rule, share: num(entry.capacity_share), recall: num(m.recall), precision: num(m.precision),
      paths: { share: pathOf('rules', rule, 'capacity_share'), recall: pathOf('rules', rule, 'models', model, 'recall'),
        precision: pathOf('rules', rule, 'models', model, 'precision') } };
  }).filter(x => x.share !== null && x.recall !== null);
  return { resultId: str(r.result_id), model, n: int(g.n), nPositive: int(g.n_positive), baseRate: num(g.base_rate),
    points, rules, evaluation: strOrNull(v.evaluation) };
}

/**
 * The one evaluation of the final test (CLI-CONTRACT §12, `final_test.evaluation`): the
 * configuration, the rows, the chosen model against the baseline with intervals, and the
 * success criterion judged on these rows. Null while the final test is sealed.
 */
function finalEvaluationOf(rawResults, task) {
  const r = rawResults.find(x => x && x.slot === 'final_test.evaluation' && x.promoted === true) || null;
  if (!r) return null;
  if (!citable(r)) return { resultId: str(r.result_id), current: false };
  const v = obj(r.values);
  const chosen = str(v.model);
  const reference = 'fit.baseline';
  const fits = [chosen, ...Object.keys(obj(v.models)).filter(f => f !== chosen && f !== reference), reference]
    .filter(f => obj(v.models)[f]);
  const metrics = task === 'regression' ? ['mae', 'rmse'] : ['precision', 'recall'];
  const k = obj(v.criterion);
  const criterionPath = x => pathOf('criterion', x);
  return {
    resultId: str(r.result_id), current: true, created: strOrNull(r.created), model: chosen, rule: strOrNull(v.rule),
    ruleFinal: strOrNull(v.rule_final), capacityShare: num(v.capacity_share), n: int(v.n), nPositive: int(v.n_positive),
    refitRows: int(obj(v.refit).n_rows), unit: strOrNull(v.unit), note: strOrNull(v.note),
    bootstrap: bootstrapOf(v),
    metrics: metrics.map(metric => {
      const d = obj(obj(v.deltas)[chosen])[metric];
      const delta = d ? interval(d, pathOf('deltas', chosen, metric, 'point')) : null;
      return {
        metric,
        models: fits.map(fit => {
          const i = obj(obj(obj(v.intervals)[fit])[metric]);
          return { fit, point: num(obj(obj(v.models)[fit])[metric]), low: num(i.low), high: num(i.high),
            path: pathOf('models', fit, metric) };
        }),
        delta: delta ? { fit: chosen, ...delta, side: side(delta.low, delta.high) } : null,
      };
    }),
    criterion: Object.keys(k).length ? {
      metric: strOrNull(k.metric), minimum: num(k.minimum), unit: strOrNull(k.unit), gain: num(k.gain), low: num(k.low),
      high: num(k.high), includesZero: k.interval_includes_zero === true, status: strOrNull(k.status),
      paths: { gain: criterionPath('gain'), low: criterionPath('low'), high: criterionPath('high'), minimum: criterionPath('minimum') },
    } : null,
  };
}

// Model diagnostics (WP-B4; CLI-CONTRACT §13, CLI-CONTRACT-COMPANION §14). Results of the
// slots `diag.binary` or `diag.regression` (development evidence: the candidate and the
// variant) and `diag.final_test` (final evidence: the chosen model only). Only current,
// verified results are read; each number keeps its value path for citing
// (`models.[fit.logistic].calibration.brier`). Points of `curve`, `qq` and `scatter` are
// drawn as marks; the panel computes nothing.
const DIAG_SLOTS = ['diag.binary', 'diag.regression', 'diag.final_test'];
const MAX_TERMS = 8;

function binaryDiag(m, at) {
  const c = obj(m.confusion);
  const cell = k => ({ value: num(c[k]), path: at('confusion', k) });
  const cal = obj(m.calibration);
  const coef = obj(m.coefficients);
  return {
    confusion: { tp: cell('true_positives'), fp: cell('false_positives'), fn: cell('false_negatives'),
      tn: cell('true_negatives'), precision: cell('precision'), recall: cell('recall'), specificity: cell('specificity'),
      selection: strOrNull(c.selection) },
    curve: list(obj(m.curve).points).map((p, i) => ({ share: num(p && p.share), recall: num(p && p.recall),
      fpr: num(p && p.false_positive_rate), precision: num(p && p.precision),
      paths: { share: at('curve', 'points', i, 'share'), recall: at('curve', 'points', i, 'recall'),
        fpr: at('curve', 'points', i, 'false_positive_rate') } })).filter(p => p.share !== null && p.recall !== null),
    rocAuc: { value: num(m.roc_auc), path: at('roc_auc') },
    averagePrecision: { value: num(m.average_precision), path: at('average_precision') },
    calibration: {
      brier: { value: num(cal.brier), path: at('calibration', 'brier') },
      brierBase: { value: num(cal.brier_base_rate), path: at('calibration', 'brier_base_rate') },
      outside: int(cal.bins_outside_interval),
      bins: list(cal.bins).map((b, i) => ({ bin: int(b && b.bin), n: int(b && b.n), meanPred: num(b && b.mean_predicted),
        observed: num(b && b.observed_rate), low: num(b && b.low), high: num(b && b.high), inside: b && b.inside_interval === true,
        paths: { meanPred: at('calibration', 'bins', i, 'mean_predicted'), observed: at('calibration', 'bins', i, 'observed_rate'),
          n: at('calibration', 'bins', i, 'n') } })).filter(b => b.meanPred !== null && b.observed !== null),
    },
    segments: list(m.segments).map((s, si) => ({ column: str(s && s.column),
      groups: list(s && s.groups).map((g, gi) => {
        const p = k => at('segments', si, 'groups', gi, k);
        return { value: str(g && g.value), n: int(g && g.n), selected: num(g && g.selected), precision: num(g && g.precision),
          precisionLow: num(g && g.precision_low), precisionHigh: num(g && g.precision_high), recall: num(g && g.recall),
          small: g && g.small_cell === true,
          paths: { n: p('n'), selected: p('selected'), precision: p('precision'), recall: p('recall') } };
      }) })),
    coefficients: coefficientsOf(coef, at),
    examples: { falsePositives: list(obj(m.examples).false_positives).length, falseNegatives: list(obj(m.examples).false_negatives).length },
  };
}

function coefficientsOf(coef, at) {
  if (!coef || !Array.isArray(coef.terms)) return null;
  return {
    total: coef.terms.length, replicates: int(coef.replicates), level: num(coef.level), scale: strOrNull(coef.scale),
    terms: coef.terms.slice(0, MAX_TERMS).map((t, i) => ({ term: str(t && t.term), value: num(t && t.value),
      low: num(t && t.low), high: num(t && t.high), excludesZero: t && t.excludes_zero === true,
      path: at('coefficients', 'terms', i, 'value') })),
  };
}

function regressionDiag(m, at) {
  const e = obj(m.errors);
  const r = obj(m.residuals);
  const h = obj(m.heteroscedasticity);
  return {
    errors: { mae: { value: num(e.mae), path: at('errors', 'mae') }, rmse: { value: num(e.rmse), path: at('errors', 'rmse') } },
    residuals: { mean: { value: num(r.mean), path: at('residuals', 'mean') }, sd: { value: num(r.sd), path: at('residuals', 'sd') },
      skewness: { value: num(r.skewness), path: at('residuals', 'skewness') },
      kurtosis: { value: num(r.excess_kurtosis), path: at('residuals', 'excess_kurtosis') } },
    qq: list(obj(m.qq).points).map(p => ({ theoretical: num(p && p.theoretical), sample: num(p && p.sample) }))
      .filter(p => p.theoretical !== null && p.sample !== null),
    byPrediction: list(obj(m.by_prediction).bins).map((b, i) => ({ bin: int(b && b.bin), n: int(b && b.n),
      meanPrediction: num(b && b.mean_prediction), meanResidual: num(b && b.mean_residual), sd: num(b && b.sd_residual),
      paths: { meanPrediction: at('by_prediction', 'bins', i, 'mean_prediction'), meanResidual: at('by_prediction', 'bins', i, 'mean_residual'),
        n: at('by_prediction', 'bins', i, 'n') } })),
    heteroscedasticity: { correlation: { value: num(h.abs_residual_prediction_correlation), path: at('heteroscedasticity', 'abs_residual_prediction_correlation') },
      ratio: { value: num(h.spread_ratio_top_bottom), path: at('heteroscedasticity', 'spread_ratio_top_bottom') }, flag: h.flag === true },
    byFeature: list(m.by_feature).map((f, fi) => ({ column: str(f && f.column), binned: f && f.binned === true,
      groups: list(f && f.groups).map((g, gi) => ({ value: str(g && g.value), n: int(g && g.n), meanResidual: num(g && g.mean_residual),
        mae: num(g && g.mae), small: g && g.small_cell === true,
        paths: { n: at('by_feature', fi, 'groups', gi, 'n'), meanResidual: at('by_feature', fi, 'groups', gi, 'mean_residual') } })) })),
    coefficients: coefficientsOf(obj(m.coefficients), at),
    largestErrors: list(obj(m.examples).largest_errors).length,
  };
}

function diagnosticsOf(rawResults, task) {
  return rawResults.filter(r => r && r.promoted === true && DIAG_SLOTS.includes(str(r.slot)) && citable(r)).map(r => {
    const v = obj(r.values);
    const binary = task !== 'regression';
    const fits = Object.keys(obj(v.models));
    const models = fits.map(fit => {
      const at = (...parts) => pathOf('models', fit, ...parts);
      const m = obj(obj(v.models)[fit]);
      const body = binary ? binaryDiag(m, at) : regressionDiag(m, at);
      return { fit, ...body };
    });
    return {
      slot: str(r.slot), resultId: str(r.result_id), evidence: v.evidence === 'final' ? 'final' : 'development',
      partition: strOrNull(v.partition), evaluation: strOrNull(v.evaluation), purpose: strOrNull(v.purpose),
      startedRevision: int(r.started_revision), n: int(v.n), nPositive: int(v.n_positive),
      rule: strOrNull(v.rule), ruleSource: strOrNull(v.rule_source), model: strOrNull(v.model),
      unit: strOrNull(v.unit), targetTransform: v.target_transform === undefined ? null : v.target_transform,
      smearingApplies: obj(v.smearing).applies === true, segmentColumns: list(v.segment_columns).map(str),
      models,
    };
  });
}

// --- v0.3 (WP-F1, WP-K): the selection among the variants and each family's diagnostics ----
//
// `selection` is the `model_selection` the current evaluation stored (CLI-CONTRACT §14,
// "Selection"): every figure keeps its value path in that evaluation, so the panel cites a
// registered number. The engine's sentences come in both languages (`texts`); the panel
// shows the one of its language. `familyFits` are the `family_diagnostics` each current
// variant fit registered (the EBM's terms and shapes, the boosting's permutation importance).

const SELECTION_SLOTS = ['policy.evaluation', 'evaluate.regression'];
const VARIANT_SLOTS = ['fit.variant', 'fit.variant:2', 'fit.variant:3'];
const MAX_FAMILY_TERMS = 8;
const MAX_SHAPES = 3;

const textsOf = raw => ({ en: strOrNull(obj(raw).en), fr: strOrNull(obj(raw).fr) });
const cell = (value, path) => ({ value: num(value), path });

function selectionOf(rawResults) {
  const r = rawResults.find(x => x && x.promoted === true && SELECTION_SLOTS.includes(str(x.slot)) && citable(x)) || null;
  if (!r) return null;
  const s = obj(r.values).model_selection;
  if (!s || typeof s !== 'object') return null;
  const at = (...parts) => pathOf('model_selection', ...parts);
  const one = obj(s.one_se);
  const opt = obj(s.optimism);
  const adv = obj(s.advice);
  const b = obj(s.budget);
  return {
    resultId: str(r.result_id),
    activity: str(r.activity) || str(r.slot),
    available: bool(s.available),
    metric: strOrNull(s.metric),
    direction: strOrNull(s.direction),
    folds: int(s.folds),
    best: strOrNull(s.best),
    configurations: list(s.configurations).map((c, i) => {
      const d = c && c.difference && typeof c.difference === 'object' ? c.difference : null;
      const p = (...parts) => at('configurations', i, ...parts);
      // What the variant changes, from its own fit (the stored selection has its kind only).
      const fit = promotedOf(rawResults, str(c && c.slot));
      const spec = fit ? obj(obj(fit.values).variant) : {};
      return {
        slot: str(c && c.slot), kind: strOrNull(c && c.kind), family: strOrNull(c && c.family),
        strength: strOrNull(spec.strength), group: strOrNull(spec.group),
        perFold: list(c && c.per_fold).map((v, k) => cell(v, p('per_fold', k))),
        mean: cell(c && c.mean, p('mean')), se: cell(c && c.se, p('se')), sd: num(c && c.sd),
        difference: d ? { against: strOrNull(d.against), mean: cell(d.mean, p('difference', 'mean')),
          se: cell(d.se, p('difference', 'se')), low: num(d.low), high: num(d.high), withinNoise: bool(d.within_fold_noise) } : null,
        withinOneSe: bool(c && c.within_one_se),
      };
    }).filter(c => c.slot),
    oneSe: Object.keys(one).length ? { pick: strOrNull(one.pick), best: strOrNull(one.best),
      bound: cell(one.bound, at('one_se', 'bound')), seOfBest: cell(one.se_of_best, at('one_se', 'se_of_best')),
      texts: textsOf(one.texts), source: strOrNull(one.source) } : null,
    optimism: Object.keys(opt).length ? { estimate: cell(opt.estimate, at('optimism', 'estimate')),
      configurations: int(opt.configurations), texts: textsOf(opt.texts), source: strOrNull(opt.source),
      note: strOrNull(opt.note) } : null,
    advice: Object.keys(adv).length ? { code: strOrNull(adv.code), stop: bool(adv.stop), texts: textsOf(adv.texts),
      noise: cell(adv.noise, at('advice', 'noise')) } : null,
    budget: int(b.max) !== null && int(b.used) !== null ? { max: int(b.max), used: int(b.used), remaining: int(b.remaining),
      declared: int(b.declared), legacy: bool(b.legacy) } : null,
    trials: int(s.trials),
    note: strOrNull(s.note),
  };
}

function ebmOf(fd, at) {
  const terms = list(fd.terms).map((t, i) => ({ t, i }))
    .sort((a, b) => (num(b.t && b.t.importance) || 0) - (num(a.t && a.t.importance) || 0));
  const shapeOf = (t, i) => {
    const s = obj(t && t.shape);
    if (s.type === 'continuous') {
      return { type: 'continuous', points: list(s.points).map((x, k) => ({ from: num(x && x.from), to: num(x && x.to),
        score: num(x && x.score), path: at('terms', i, 'shape', 'points', k, 'score') }))
        .filter(x => x.from !== null && x.to !== null && x.score !== null) };
    }
    if (s.type === 'nominal') {
      return { type: 'nominal', points: list(s.points).map((x, k) => ({ value: str(x && x.value), score: num(x && x.score),
        path: at('terms', i, 'shape', 'points', k, 'score') })).filter(x => x.score !== null) };
    }
    return null;
  };
  const kept = terms.slice(0, MAX_FAMILY_TERMS);
  let shapes = 0;
  return {
    kind: 'ebm_terms',
    total: int(fd.n_terms) ?? list(fd.terms).length,
    interactions: int(fd.interactions),
    scoreScale: strOrNull(fd.score_scale),
    importance: strOrNull(fd.importance),
    note: strOrNull(fd.note),
    terms: kept.map(({ t, i }) => {
      const main = (t && t.kind) !== 'interaction';
      const shape = main && shapes < MAX_SHAPES ? shapeOf(t, i) : null;
      if (shape && shape.points.length) shapes += 1;
      return { term: str(t && t.term), kind: main ? 'main' : 'interaction', importance: cell(t && t.importance, at('terms', i, 'importance')),
        shape: shape && shape.points.length ? shape : null };
    }),
  };
}

function permutationOf(fd, at) {
  const cols = list(fd.columns).map((c, i) => ({ c, i }))
    .sort((a, b) => (num(b.c && b.c.importance) || 0) - (num(a.c && a.c.importance) || 0));
  return {
    kind: 'permutation_importance',
    total: list(fd.columns).length,
    metric: strOrNull(fd.metric),
    repeats: int(fd.repeats),
    definition: strOrNull(fd.definition),
    note: strOrNull(fd.note),
    columns: cols.slice(0, MAX_FAMILY_TERMS).map(({ c, i }) => ({ column: str(c && c.column),
      importance: cell(c && c.importance, at('columns', i, 'importance')) })),
  };
}

function familyFitsOf(rawResults) {
  return VARIANT_SLOTS.map(slot => promotedOf(rawResults, slot)).filter(Boolean).map(r => {
    const v = obj(r.values);
    const fd = obj(v.family_diagnostics);
    const at = (...parts) => pathOf('family_diagnostics', ...parts);
    const body = fd.kind === 'ebm_terms' ? ebmOf(fd, at) : fd.kind === 'permutation_importance' ? permutationOf(fd, at) : null;
    if (!body) return null;
    return { slot: str(r.slot), resultId: str(r.result_id), family: strOrNull(v.family), ...body };
  }).filter(Boolean);
}

function toEvidenceModel(payload) {
  const p = expectSchema(payload, SCHEMA);
  if (!Number.isInteger(p.revision)) throw new ModelError(`The CLI did not return a ${SCHEMA} document.`);
  const task = p.task === 'regression' ? 'regression' : p.task === 'binary' ? 'binary' : null;
  const rawResults = list(p.results).filter(r => r && RESULT_ID.test(str(r.result_id)));
  const results = rawResults.map(resultItem);
  const exposure = obj(p.exposure);
  const ledger = list(exposure.ledger).map(row => ({
    purpose: str(row && row.purpose),
    partition: str(row && row.partition),
    rows: int(row && row.rows),
    records: int(row && row.records),
    activities: list(row && row.activities).map(str),
    selection: isSelection(task, str(row && row.purpose), str(row && row.partition)),
  }));
  const lineage = lineageOf(p.lineage);
  const impacts = list(p.impacts).map(impactItem);
  const sources = Object.fromEntries(['case', 'dataset'].map(k => {
    const s = obj(obj(p.sources)[k]);
    return [k, { path: str(s.path), matches: s.matches === true }];
  }));
  const evaluation = rawResults.find(r => r.promoted && citable(r) &&
    (r.slot === 'policy.evaluation' || r.slot === 'evaluate.regression'));
  const split = rawResults.find(r => r.promoted && r.slot === 'split' && citable(r));
  return plain({
    revision: p.revision,
    task,
    results,
    truncated: bool(p.truncated),
    ledger,
    lineage,
    impacts,
    sources,
    detail: detailOf(p.detail, rawResults, lineage, impacts),
    uncertainty: uncertaintyOf(evaluation),
    splitOverlap: Boolean(split && split.values.overlap !== null && split.values.overlap !== undefined),
    crossValidation: crossValidationOf(rawResults, task),
    variant: variantOf(rawResults, task),
    gain: task === 'binary' ? gainOf(rawResults) : null,
    finalEvaluation: finalEvaluationOf(rawResults, task),
    diagnostics: diagnosticsOf(rawResults, task),
    selection: selectionOf(rawResults),
    familyFits: familyFitsOf(rawResults),
  });
}

const FIXTURES = ['evidence.binary', 'evidence.binary.detail', 'evidence.regression',
  'captured/evidence.binary.cv', 'captured/evidence.binary.cv.sealed', 'captured/evidence.regression.diag',
  'captured/evidence.binary.families'];

module.exports = { toEvidenceModel, chainFor, uncertaintyOf, side, citable, gainOf, pathOf, DIAG_SLOTS, FIXTURES, SCHEMA };
