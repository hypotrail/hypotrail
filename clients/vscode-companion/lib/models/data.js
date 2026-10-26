'use strict';
// DataModel: a pure projection of `hypotrail.data/1` (CLI-CONTRACT §11.1) for the data card
// at the top of the Data & EDA tab (WP-A7). It reads the development rows only: what one row
// describes, the grouped dictionary, five fixed rows with the target first, and the sealed
// final test. It never holds a target rate or a distribution: the engine sends none.
//
// Nothing is computed here. Counts (rows, columns, missing cells, distinct values, rows of a
// special value) are the engine's own counts, shown as recorded literals (INV-7 c); a cell
// of the five rows is the stored value, shown as text. A variable's `decided` is the
// availability the junior's decision recorded, else null (the case's statement only).

const { str, strOrNull, list, obj, int, expectSchema } = require('./common');

const SCHEMA = 'hypotrail.data/1';
const DATA_KEYS = ['revision', 'observationUnit', 'development', 'target', 'finalTest', 'groups', 'rows', 'note', 'hasFrench',
  // L3 (owner session 2026-10-26): the card's note in each language the engine gives it in.
  'noteLines'];
const FIXTURES = ['data.binary', 'data.regression'];

/** A stored cell as text: a missing cell is null (shown as an empty cell, marked missing). */
function cell(value) {
  if (value === null || value === undefined) return null;
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return JSON.stringify(value);
}

// L3 (owner session 2026-10-26, R4, D4b): the French form of a case statement, from its
// `texts` (`{en, fr}`, the case's translation sidecar through the engine), or null.
const frOf = raw => { const t = obj(obj(raw).texts); return typeof t.fr === 'string' && t.fr.trim() ? t.fr : null; };

function statement(raw) {
  const s = obj(raw);
  return { value: cell(s.value), status: strOrNull(s.status), source: strOrNull(s.source), sourceFr: frOf(s) };
}

/** A junior line of the card in English (`line`/`text`) and in French (`junior_text` of a French study). */
function lines(en, junior) {
  const english = strOrNull(en);
  const other = strOrNull(junior);
  return { en: english, fr: other && other !== english ? other : null };
}

function variable(v) {
  const decided = v && v.decided && typeof v.decided === 'object' ? v.decided : null;
  return {
    name: str(v && v.name), role: str(v && v.role), type: str(v && v.type), unit: strOrNull(v && v.unit),
    description: str(v && v.description), descriptionFr: strOrNull(v && v.description_fr),
    availability: statement(v && v.availability),
    decided: decided ? { status: strOrNull(decided.status), value: strOrNull(decided.value) } : null,
    specialValues: list(v && v.special_values).map(s => ({ value: cell(s && s.value) || '', meaning: str(s && s.meaning),
      meaningFr: frOf(s), status: strOrNull(s && s.status), nRows: int(s && s.n_rows) })),
    nMissing: int(v && v.n_missing), nDistinct: int(v && v.n_distinct),
    examples: list(v && v.examples).map(cell).filter(x => x !== null),
  };
}

/** `hypotrail.data/1` -> DataModel. Throws ModelError for another schema. */
function toDataModel(payload) {
  const p = expectSchema(payload, SCHEMA);
  const unit = obj(p.observation_unit);
  const dev = obj(p.development);
  const target = obj(p.target);
  const ft = obj(p.final_test);
  const rows = obj(p.rows);
  const groups = list(p.groups).map(g => ({ group: str(g && g.group), groupFr: frOf(g), variables: list(g && g.variables).map(variable) }));
  const columns = list(rows.columns).map(str).filter(Boolean);
  return {
    revision: int(p.revision) || 0,
    observationUnit: { value: strOrNull(unit.value), valueFr: frOf(unit), status: strOrNull(unit.status), source: strOrNull(unit.source) },
    development: { rows: int(dev.rows), columns: int(dev.columns), partition: strOrNull(dev.partition) },
    target: {
      column: str(target.column), task: strOrNull(target.task), positiveLabel: cell(target.positive_label),
      negativeLabel: cell(target.negative_label), unit: strOrNull(target.unit), description: str(target.description),
      descriptionFr: strOrNull(target.description_fr),
    },
    finalTest: { status: strOrNull(ft.status), rows: int(ft.rows), developmentRows: int(ft.development_rows),
      // v0.3 (WP-C): the line in the study language (`junior_text`) when the engine sends it.
      method: strOrNull(ft.method), line: strOrNull(ft.junior_text || ft.line), audience: strOrNull(ft.audience),
      // L3: the line in each language the engine gives it in.
      lines: lines(ft.line, ft.junior_text) },
    groups,
    rows: {
      columns, order: strOrNull(rows.order),
      items: list(rows.items).map(r => {
        const values = obj(r && r.values);
        return { rowKey: str(r && r.row_key), cells: columns.map(c => cell(values[c])) };
      }),
    },
    note: (() => { const n = obj(p.note); return n.audience === 'agent' ? null : strOrNull(n.junior_text || n.text); })(),
    hasFrench: Boolean(target.description_fr) || groups.some(g => g.groupFr || g.variables.some(v => v.descriptionFr)),
    noteLines: (() => { const n = obj(p.note); return n.audience === 'agent' ? null : lines(n.text, n.junior_text); })(),
  };
}

module.exports = { toDataModel, DATA_KEYS, FIXTURES, SCHEMA };
