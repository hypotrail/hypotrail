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
// (the `diag.*` results of WP-B4, in the shape of its plan; see diagnosticsOf).

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
  let comparisons = [];
  let reference = null;
  if (evaluation && task === 'binary') {
    const rules = list(obj(evaluation.params).rules).map(str)
      .filter(rule => obj(obj(obj(ev.rules)[rule]).comparisons)['fit.variant']);
    comparisons = rules.map(rule => {
      const c = obj(obj(obj(obj(ev.rules)[rule]).comparisons)['fit.variant']);
      reference = reference || strOrNull(c.reference);
      return { rule, metrics: ['precision', 'recall'].map(m => ({ metric: m,
        ...metric(c[m], pathOf('rules', rule, 'comparisons', 'fit.variant', m, 'point')) })) };
    });
  } else if (evaluation) {
    const c = obj(obj(ev.comparisons)['fit.variant']);
    if (Object.keys(c).length) {
      reference = strOrNull(c.reference);
      comparisons = [{ rule: null, metrics: ['mae', 'rmse'].map(m => ({ metric: m,
        ...metric(c[m], pathOf('comparisons', 'fit.variant', m, 'point')) })) }];
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

// WP-B4 is written in parallel. Until its contract lands, the diagnostics are read in the
// shape of its plan (V0.2-IMPLEMENTATION-PLAN WP-B4; INTEGRATOR: reconcile with the engine's
// `diag.*` payload and test/fixtures/evidence.binary.diagnostics.json): a current result
// whose activity starts with `diag.`, its kind named by the activity, its values
//   confusion    {rule, model, evaluation, n, confusion: {tp, fp, fn, tn}}
//   gain         {model, evaluation, points: [{share, recall, precision}]}
//   calibration  {model, evaluation, bins: [{mean_pred, observed, low, high, n}]}
//   segments     {model, rule, evaluation, segments: [{variable, group, precision, recall, n, low, high}]}
//   residuals    {model, evaluation, bins: [{mean_pred, mean_residual, low, high, n}]}
// where `evaluation` is `out_of_fold` (development rows) or `final_test`. Anything else is
// listed by name only. Every number shown is one of these values.
const DIAG_KINDS = ['confusion', 'gain', 'calibration', 'segments', 'residuals'];

function diagKind(activity) {
  const a = str(activity).toLowerCase();
  if (a.includes('confusion')) return 'confusion';
  if (a.includes('calibration')) return 'calibration';
  if (a.includes('segment')) return 'segments';
  if (a.includes('residual')) return 'residuals';
  if (a.includes('gain') || a.includes('lift')) return 'gain';
  return 'other';
}

function diagnosticsOf(rawResults) {
  return rawResults.filter(r => r && r.current === true && r.integrity === 'ok' && /^diag\./.test(str(r.activity))
    && r.values && typeof r.values === 'object').map(r => {
    const v = obj(r.values);
    const kind = diagKind(r.activity);
    const base = { kind, resultId: str(r.result_id), activity: str(r.activity), slot: strOrNull(r.slot),
      evaluation: strOrNull(v.evaluation) || (r.partition === 'final_test' ? 'final_test' : 'out_of_fold'),
      model: strOrNull(v.model), rule: strOrNull(v.rule), n: int(v.n) ?? int(r.n_rows) };
    if (kind === 'confusion') {
      const c = obj(v.confusion);
      const cell = k => ({ value: num(c[k]), path: pathOf('confusion', k) });
      return { ...base, cells: { tp: cell('tp'), fp: cell('fp'), fn: cell('fn'), tn: cell('tn') } };
    }
    if (kind === 'gain') {
      return { ...base, points: list(v.points).map((p, i) => ({ share: num(p && p.share), recall: num(p && p.recall),
        precision: num(p && p.precision), paths: { share: pathOf('points', i, 'share'), recall: pathOf('points', i, 'recall'),
          precision: pathOf('points', i, 'precision') } })).filter(p => p.share !== null && p.recall !== null) };
    }
    if (kind === 'calibration') {
      return { ...base, bins: list(v.bins).map((b, i) => ({ meanPred: num(b && b.mean_pred), observed: num(b && b.observed),
        low: num(b && b.low), high: num(b && b.high), n: int(b && b.n),
        paths: { meanPred: pathOf('bins', i, 'mean_pred'), observed: pathOf('bins', i, 'observed'),
          low: pathOf('bins', i, 'low'), high: pathOf('bins', i, 'high'), n: pathOf('bins', i, 'n') } }))
        .filter(b => b.meanPred !== null && b.observed !== null) };
    }
    if (kind === 'segments') {
      return { ...base, segments: list(v.segments).map((g, i) => ({ variable: str(g && g.variable), group: str(g && g.group),
        precision: num(g && g.precision), recall: num(g && g.recall), n: int(g && g.n), low: num(g && g.low), high: num(g && g.high),
        paths: { precision: pathOf('segments', i, 'precision'), recall: pathOf('segments', i, 'recall'), n: pathOf('segments', i, 'n'),
          low: pathOf('segments', i, 'low'), high: pathOf('segments', i, 'high') } })) };
    }
    if (kind === 'residuals') {
      return { ...base, bins: list(v.bins).map((b, i) => ({ meanPred: num(b && b.mean_pred), meanResidual: num(b && b.mean_residual),
        low: num(b && b.low), high: num(b && b.high), n: int(b && b.n),
        paths: { meanPred: pathOf('bins', i, 'mean_pred'), meanResidual: pathOf('bins', i, 'mean_residual'),
          low: pathOf('bins', i, 'low'), high: pathOf('bins', i, 'high'), n: pathOf('bins', i, 'n') } }))
        .filter(b => b.meanResidual !== null) };
    }
    return base;
  });
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
    diagnostics: diagnosticsOf(rawResults),
  });
}

const FIXTURES = ['evidence.binary', 'evidence.binary.detail', 'evidence.regression', 'evidence.binary.diagnostics',
  'captured/evidence.binary.cv', 'captured/evidence.binary.cv.sealed'];

module.exports = { toEvidenceModel, chainFor, uncertaintyOf, side, citable, gainOf, pathOf, DIAG_KINDS, FIXTURES, SCHEMA };
