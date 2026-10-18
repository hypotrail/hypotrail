'use strict';
// ExplainModel (COMPANION-ADVANCED §9, §6.6.1): the learning layer's only source of text,
// projected from `hypotrail.explain/1` (CLI-CONTRACT-COMPANION §6). Owned by WP-U5.
//
//   revision, task,
//   terms {id: {term, definition, example (segments | null), exampleStatus, steps}},
//   termOrder [id] (the engine's file order),
//   steps {stepId: {concept, context, method, interpretation, consequence (segments | null), textStatus}},
//   predictions [{id, step, question, choices [{id, label}], reveal (segments | null), available}]
//
// `example` is kept only when `example_status` is `shown`, and `reveal` only when
// `available` is true: a cited number of a result that is not current never reaches the
// webview (INV-7).

const { str, strOrNull, list, obj, bool, int, expectSchema, segments } = require('./common');

const SCHEMA = 'hypotrail.explain/1';
const ID = /^[a-z][a-z0-9_]{0,63}$/;
const QUESTION_ID = /^[a-z][a-z0-9_.:-]{0,99}$/;
const CHOICE_ID = /^[a-z0-9_]{1,40}$/;
const STEP_TEXTS = ['concept', 'context', 'method', 'interpretation', 'consequence'];

const text = raw => (raw && typeof raw === 'object' ? segments(raw) : null);

function toExplainModel(payload) {
  const p = expectSchema(payload, SCHEMA);
  const terms = {};
  const termOrder = [];
  for (const t of list(p.terms)) {
    const id = str(t && t.id);
    if (!ID.test(id) || terms[id]) continue;
    const status = str(t.example_status) || 'none';
    termOrder.push(id);
    terms[id] = { term: str(t.term), definition: str(t.definition),
      example: status === 'shown' ? text(t.example) : null, exampleStatus: status,
      steps: list(t.steps).map(str).filter(s => ID.test(s)) };
  }
  const steps = {};
  for (const [id, s] of Object.entries(obj(p.steps))) {
    if (!ID.test(id)) continue;
    const item = { textStatus: str(s && s.text_status) || 'shown' };
    for (const k of STEP_TEXTS) item[k] = text(s && s[k]);
    steps[id] = item;
  }
  const predictions = list(p.predictions).filter(q => q && QUESTION_ID.test(str(q.id))).map(q => {
    const available = bool(q.available) && Boolean(q.reveal);
    return { id: str(q.id), step: str(q.step), question: str(q.question),
      choices: list(q.choices).filter(c => c && CHOICE_ID.test(str(c.id))).map(c => ({ id: str(c.id), label: str(c.label) })),
      reveal: available ? text(q.reveal) : null, available };
  });
  return { revision: int(p.revision) === null ? 0 : int(p.revision), task: strOrNull(p.task), terms, termOrder, steps, predictions };
}

const FIXTURES = ['explain.binary', 'explain.regression'];

module.exports = { toExplainModel, FIXTURES, SCHEMA };
