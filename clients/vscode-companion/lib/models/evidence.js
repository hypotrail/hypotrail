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

const { ModelError, str, strOrNull, list, obj, int, num, bool, expectSchema, segments, plain } = require('./common');

const SCHEMA = 'hypotrail.evidence/1';
const RESULT_ID = /^[0-9a-f]{64}$/;
// The order of artefact chips in a lineage (CLI-CONTRACT §8.3).
const ARTIFACT_ORDER = ['report', 'notebook', 'workbench'];
// Purposes whose validation rows chose something (§6.4: the highlighted ledger row).
const SELECTION_PURPOSE = { binary: 'validation_policy_selection', regression: 'validation_model_evaluation' };

const rid8 = id => String(id || '').slice(0, 8);

function staleReason(raw) {
  if (!raw || typeof raw !== 'object') return null;
  return {
    reason: strOrNull(raw.reason),
    codeChanged: list(raw.code_changed).map(str),
    upstreamNotCurrent: list(raw.upstream_not_current).map(x => rid8(str(x))),
    sourcesChanged: bool(raw.sources_changed),
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
    selection: str(row && row.purpose) === SELECTION_PURPOSE[task] && str(row && row.partition) === 'validation',
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
  });
}

const FIXTURES = ['evidence.binary', 'evidence.binary.detail', 'evidence.regression'];

module.exports = { toEvidenceModel, chainFor, uncertaintyOf, side, citable, FIXTURES, SCHEMA };
