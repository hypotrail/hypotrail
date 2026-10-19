"""``hypotrail evidence``: results, lineage, exposure ledger, impacts, and the EDA catalog.

    hypotrail evidence --study DIR [--result RID] [--limit N] [--json]

CLI-CONTRACT-COMPANION §5 (C5), payload ``hypotrail.evidence/1``: everything the EDA,
Evidence, and What if? tabs of the companion show, in one call. Read-only (R1-R5): no
lock, no write, no exposure, no dataset row read, no pandas, numpy, scikit-learn, or scipy.

* ``results``: the registry entries, newest last, at most ``--limit`` of them; the
  entries promoted to a slot always come first. A figure (``values``, ``headline``) is
  given **only** for a current result whose integrity is verified: a client never shows a
  figure of a non-current result.
* ``lineage``: sources, confirmed decisions, the listed results, and the report and the
  notebook, with the edges between them.
* ``exposure``: the summary of ``read.Study.exposure_summary()``, every record without its
  row keys, and one ledger row per purpose and partition (distinct rows).
* ``impacts``: for each row of the dependency table that can change a confirmed decision,
  what would go stale now (``dependencies.effects_for_mutation``, on a copy of the state).
* ``eda_catalog``: the EDA activities of the task, the columns each one accepts (the only
  columns the companion may request), and whether they can run.
* ``sources``: the case and dataset files, with their recorded digest and whether the
  file still matches it.
* ``detail``: with ``--result``, the full record of one result.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping

from . import activities as act
from . import cite, currency, dependencies, preconditions, read, texts
from . import commands as cmd
from . import manifest as mf
from . import records as rec
from . import state as st
from . import view as view_model
from .cmd_explain import placeholders, resolve
from .errors import StudyError

SCHEMA = 'hypotrail.evidence/1'
PAYLOAD_KEYS = ('schema', 'ok', 'study', 'revision', 'task', 'results', 'truncated', 'lineage',
                'exposure', 'impacts', 'eda_catalog', 'sources', 'detail')
RESULT_KEYS = ('result_id', 'activity', 'slot', 'promoted', 'current', 'stale_reason',
               'integrity', 'partition', 'n_rows', 'params', 'upstream', 'downstream',
               'created', 'started_revision', 'execution_id', 'exposure_id', 'values',
               'headline')
EXPOSURE_RECORD_KEYS = ('exposure_id', 'revision', 'time', 'activity', 'result_id',
                        'execution_id', 'purpose', 'partition', 'n_rows', 'columns')
LEDGER_KEYS = ('purpose', 'partition', 'rows', 'records', 'activities', 'first_revision',
               'last_revision')
IMPACT_KEYS = ('decision_id', 'mutation', 'row', 'change', 'stale_slots', 'kept_slots', 'refit',
               'reconfirm', 'notes')
DETAIL_KEYS = ('result_id', 'values', 'params', 'inputs', 'code', 'environment', 'blobs',
               'exposure', 'consumers', 'report_anchor', 'notebook_hint')
PARTITION_ORDER = ('all', 'development', 'train', 'validation', 'final_test')
# The EDA activities of each task, in plan order: those of ``activities.task_activities``
# (the task's own, then the shared ``eda.distribution``), so the catalog cannot drift from
# what ``run`` accepts (WP-I).
EDA_CATALOG = {task: tuple(a for a in act.task_activities(task) if a in act.EDA)
               for task in (st.BINARY, st.REGRESSION)}
# The roles of the columns each per-column activity accepts (as ``run`` would accept them).
PER_COLUMN_ROLES = {act.RATE_BY: ('feature',), act.MEAN_BY: ('feature', 'time'),
                    act.DISTRIBUTION: act.DISTRIBUTION_ROLES}
LINEAGE_ARTIFACTS = ('report', 'notebook')
NOTEBOOK_HINT_CHARS = 8
DEFAULT_LIMIT = 200


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--result', default=None, metavar='RID',
                        help='add the detail of this result (64 hexadecimal characters)')
    parser.add_argument('--limit', type=int, default=DEFAULT_LIMIT,
                        help='at most N registry entries (at least 1)')


class _Blobs:
    """What :func:`mlkit.study.registry.get` reads (``home``, ``read_blob``), backed by the
    read-only study: lineage propagation of :func:`dependencies.effects_for_mutation`
    without a writer store."""

    def __init__(self, study: read.Study):
        self.home = study.home
        self._study = study

    def read_blob(self, sha: str) -> bytes:
        return self._study.blob(sha)


# --- results ---------------------------------------------------------------------------

def _promotions(study: read.Study) -> dict[str, str]:
    """``{result_id: slot}`` of the last promotion of each result (``run.promote``)."""
    out = {}
    for r in study.revisions():
        result = r.get('result') or {}
        if r.get('action') == 'run.promote' and result.get('status') == 'promoted' \
                and result.get('result_id') and result.get('slot'):
            out[result['result_id']] = result['slot']
    return out


def _entries(study: read.Study) -> list[dict]:
    """Every registry entry, verified where it can be: ``{rid, entry, integrity}``."""
    out = []
    for rid in study.result_ids():
        try:
            entry, integrity = study.result(rid), 'ok'
        except StudyError as exc:
            entry, integrity = study.raw_result(rid) or {}, exc.code
        out.append({'rid': rid, 'entry': entry, 'integrity': integrity})
    return out


def _order(item: dict):
    entry = item['entry']
    started = entry.get('started_revision')
    return (started if isinstance(started, int) else -1, str(entry.get('created') or ''),
            item['rid'])


def _select(items: list[dict], promoted: set, limit: int) -> tuple[list[dict], bool]:
    """Promoted entries first (newest last), then the newest others up to ``limit``."""
    items = sorted(items, key=_order)
    first = [i for i in items if i['rid'] in promoted]
    others = [i for i in items if i['rid'] not in promoted]
    room = max(0, limit - len(first))
    kept = others[len(others) - room:] if room else []
    return first + kept, len(kept) < len(others)


def _headline(task: str, activity: str | None, rid: str, citer: cite.Citer,
              values: Mapping) -> dict | None:
    data = texts.load('evidence')
    table = data.get('regression_headlines' if task == st.REGRESSION else 'headlines') or {}
    template = table.get(activity or '')
    if not template:
        return None
    return resolve(template.replace('{{r:@.', '{{r:' + rid + '.'), citer, values)


def _result_items(study: read.Study, view: Mapping, selected: list[dict], slots: Mapping,
                  promotions: Mapping, children: Mapping, citer: cite.Citer,
                  values: Mapping) -> list[dict]:
    out = []
    task = view['task']
    for item in selected:
        rid, entry, integrity = item['rid'], item['entry'], item['integrity']
        promoted_slot = slots.get(rid)
        currency_ = study.currency(rid)
        current = currency_['current'] and integrity == 'ok'
        inputs = entry.get('inputs') if isinstance(entry.get('inputs'), Mapping) else {}
        upstream = {}
        for role, parent in sorted((inputs.get('results') or {}).items()):
            upstream[role] = ({'role': role, 'result_id': parent, 'history': True}
                              if role in rec.HISTORY_ROLES else parent)
        shown = current and isinstance(entry.get('output'), Mapping)
        out.append({
            'result_id': rid, 'activity': entry.get('activity'),
            'slot': promoted_slot or promotions.get(rid),
            'promoted': promoted_slot is not None,
            'current': bool(current),
            'stale_reason': currency_['reason'] if not current else None,
            'integrity': integrity, 'partition': entry.get('partition'),
            'n_rows': entry.get('n_rows'), 'params': entry.get('params'),
            'upstream': upstream, 'downstream': children.get(rid, []),
            'created': entry.get('created'), 'started_revision': entry.get('started_revision'),
            'execution_id': entry.get('execution_id'), 'exposure_id': entry.get('exposure_id'),
            'values': entry['output'].get('values') if shown else None,
            'headline': _headline(task, entry.get('activity'), rid, citer, values)
            if shown else None})
        if integrity != 'ok' and out[-1]['stale_reason'] is None:
            out[-1]['stale_reason'] = {'reason': integrity, 'since': None}
    return out


# --- lineage ---------------------------------------------------------------------------

def _decision_edges(state: Mapping, entry: Mapping) -> list[tuple[str, str]]:
    """``(decision_id, role)`` of the confirmed decisions whose value is an input of
    ``entry``: the split it was cut by, the features it was fitted with, the rule it
    evaluated, the model it compared."""
    decisions = state['decisions']
    inputs = entry.get('inputs') if isinstance(entry.get('inputs'), Mapping) else {}
    params = entry.get('params') if isinstance(entry.get('params'), Mapping) else {}
    out = []

    def value(d):
        dec = decisions.get(d) or {}
        return dec.get('value') if dec.get('status') in ('confirmed',
                                                          'reconfirm_required') else None
    if 'decision' in inputs and value('split') is not None \
            and rec.canonical(inputs['decision']) == rec.canonical(value('split')):
        out.append(('split', 'split'))
    if 'features' in inputs and isinstance(value('feature_availability'), Mapping):
        out.append(('feature_availability', 'features'))
    rule = value('policy')
    if isinstance(rule, str) and isinstance(params.get('rules'), list) \
            and (rec.canonical_rule(rule) or rule) in preconditions.evaluated_rules(entry):
        out.append(('policy', 'rule'))
    choice = value('model_choice')
    if isinstance(choice, str) and choice in (params.get('models') or []):
        out.append(('model_choice', 'model'))
    return out


def _lineage(study: read.Study, view: Mapping, results: list[dict], entries: Mapping,
             manifest: Mapping, sources: Mapping) -> dict:
    state = study.state
    nodes, edges = [], []
    for key in ('case', 'dataset'):
        nodes.append({'id': key, 'kind': 'source',
                      'label': Path(state[key]['path']).name,
                      'status': 'ok' if sources[key]['matches'] else 'changed'})
    for d in st.decision_ids(state):
        dec = state['decisions'][d]
        if dec['status'] in ('confirmed', 'reconfirm_required'):
            nodes.append({'id': f'decision:{d}', 'kind': 'decision', 'label': d,
                          'status': dec['status']})
    listed = {r['result_id'] for r in results}
    decision_nodes = {n['id'] for n in nodes if n['kind'] == 'decision'}
    for r in results:
        nodes.append({'id': r['result_id'], 'kind': 'result',
                      'label': r['slot'] or r['activity'] or r['result_id'][:8],
                      'status': 'current' if r['current'] else 'stale'})
    items = manifest.get('artifacts') or {}

    def is_current(rid):
        return study.currency(rid)['current']
    for name in LINEAGE_ARTIFACTS:
        nodes.append({'id': f'artifact:{name}', 'kind': 'artifact', 'label': name,
                      'status': currency.effective_status(
                          items.get(name), state, is_current,
                          currency.file_check(study.study_dir, items.get(name)))})
    for r in results:
        rid, entry = r['result_id'], entries[r['result_id']]
        if entry.get('exposure_id'):
            edges.append({'from': 'dataset', 'to': rid, 'role': 'rows'})
        for decision_id, role in _decision_edges(state, entry):
            if f'decision:{decision_id}' in decision_nodes:
                edges.append({'from': f'decision:{decision_id}', 'to': rid, 'role': role})
        for role, parent in sorted(((entry.get('inputs') or {}).get('results') or {}).items()):
            if parent in listed:
                edges.append({'from': parent, 'to': rid, 'role': role})
    for r in results:
        for name in LINEAGE_ARTIFACTS:
            if r['result_id'] in ((items.get(name) or {}).get('consumed') or []):
                edges.append({'from': r['result_id'], 'to': f'artifact:{name}',
                              'role': 'consumed'})
    return {'nodes': nodes, 'edges': edges}


# --- exposure --------------------------------------------------------------------------

def _exposure(study: read.Study) -> dict:
    records = study.exposure_records()
    views, rows, ledger = [], {}, {}
    for r in records:
        views.append({k: r.get(k) for k in EXPOSURE_RECORD_KEYS})
        key = (r['purpose'], r.get('partition') or 'all')
        row = ledger.setdefault(key, {'purpose': key[0], 'partition': key[1], 'rows': 0,
                                      'records': 0, 'activities': [], 'first_revision': None,
                                      'last_revision': None})
        rows.setdefault(key, set()).update(rec.parse_row_keys(study.blob(r['row_keys'])))
        row['records'] += 1
        if r.get('activity') not in row['activities']:
            row['activities'].append(r.get('activity'))
        revision = r.get('revision')
        if isinstance(revision, int):
            row['first_revision'] = revision if row['first_revision'] is None \
                else min(row['first_revision'], revision)
            row['last_revision'] = revision if row['last_revision'] is None \
                else max(row['last_revision'], revision)
    for key, row in ledger.items():
        row['rows'] = len(rows[key])
    purpose_rank = {p: i for i, p in enumerate(rec.EXPOSURE_PURPOSES)}
    part_rank = {p: i for i, p in enumerate(PARTITION_ORDER)}
    ordered = sorted(ledger.values(), key=lambda x: (
        purpose_rank.get(x['purpose'], len(purpose_rank)), x['purpose'],
        part_rank.get(x['partition'], len(part_rank)), x['partition']))
    return {'summary': study.exposure_summary(), 'records': views,
            'ledger': [{k: row[k] for k in LEDGER_KEYS} for row in ordered],
            'prior_exposure': study.state['prior_exposure']}


# --- impacts ---------------------------------------------------------------------------

def _slot_order(state: Mapping):
    plan = list(st.activity_slots(state))

    def key(slot):
        base = slot.partition(':')[0]
        if slot in plan:
            return (plan.index(slot), 0, slot)
        if base.startswith('eda.'):     # per-column EDA after the plan's training EDA
            last = max((i for i, s in enumerate(plan) if s.startswith('eda.')), default=0)
            return (last, 1, slot)
        return (len(plan), 0, slot)
    return key


def _impacts(study: read.Study, view: Mapping) -> list[dict]:
    state = study.state
    task = st.task_of(state)
    changes = texts.load('evidence').get('changes') or {}
    store = _Blobs(study)
    order = _slot_order(state)

    def current(slot):
        rid = state['current'].get(slot)
        return rid is not None and study.currency(rid)['current']
    out = []
    for mutation in dependencies.DECISION_MUTATIONS[task]:
        decision_id = dependencies.DECISION_OF_MUTATION[mutation]
        if decision_id not in state['decisions'] or \
                state['decisions'][decision_id]['status'] not in ('confirmed', 'reconfirm_required'):
            continue
        eff = dependencies.effects_for_mutation(state, mutation, store)
        out.append({'decision_id': decision_id, 'mutation': mutation, 'row': eff['row'],
                    'change': changes.get(mutation, mutation),
                    'stale_slots': sorted((s for s in eff['stale_slots'] if current(s)),
                                          key=order),
                    'kept_slots': sorted((s for s in eff['kept_slots'] if current(s)),
                                         key=order),
                    'refit': eff['refit'], 'reconfirm': eff['reconfirm'],
                    'notes': eff['notes']})
    return out


# --- EDA catalog and sources ------------------------------------------------------------

def _eda_catalog(study: read.Study) -> dict:
    from .case import CaseError, case_of

    state = study.state
    task = st.task_of(state)
    try:
        variables = case_of(state).document['variables']
    except CaseError:       # the case file is gone or invalid: no column can be offered
        variables = []
    out = []
    for activity in EDA_CATALOG[task]:
        roles = PER_COLUMN_ROLES.get(activity)
        columns = []
        for v in variables if roles else ():
            if v['role'] not in roles:
                continue
            slot = f'{activity}:{v["name"]}'
            rid = state['current'].get(slot)
            current = rid is not None and study.currency(rid)['current']
            columns.append({'name': v['name'], 'role': v['role'], 'type': v['type'],
                            'slot': slot if current else None,
                            'result_id': rid if current else None})
        missing = preconditions.missing_for_activity(state, activity)
        out.append({'activity': activity, 'per_column': roles is not None, 'columns': columns,
                    'runnable': not missing, 'missing': missing})
    return {'activities': out}


def _sources(study: read.Study) -> dict:
    state = study.state
    changed = {c['label'] for c in study.source_changes()}
    return {key: {'path': state[key]['path'], 'sha256': state[key]['sha256'],
                  'matches': key not in changed} for key in ('case', 'dataset')}


# --- detail ----------------------------------------------------------------------------

def _detail(study: read.Study, rid: str, item: dict, manifest: Mapping) -> dict:
    state = study.state
    entry = item['entry']
    items = manifest.get('artifacts') or {}
    record = next((r for r in study.exposure_records()
                   if r.get('exposure_id') and r.get('exposure_id') == entry.get('exposure_id')),
                  None)
    consumers = [name for name in mf.ARTIFACTS
                 if rid in ((items.get(name) or {}).get('consumed') or [])]

    def is_current(r):
        return study.currency(r)['current']
    report = items.get('report')
    cited = currency.effective_status(report, state, is_current,
                                      currency.file_check(study.study_dir, report)) == 'ok' \
        and rid in ((report or {}).get('consumed') or [])
    notebook = study.study_dir / mf.ARTIFACTS['notebook']
    hint = None
    if notebook.is_file():
        try:
            text = notebook.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            text = ''
        if rid in text:
            hint = {'path': mf.ARTIFACTS['notebook'], 'search': rid[:NOTEBOOK_HINT_CHARS]}
    current = item['integrity'] == 'ok' and study.currency(rid)['current']
    code = entry.get('code') if isinstance(entry.get('code'), Mapping) else {}
    return {'result_id': rid,
            'values': (entry.get('output') or {}).get('values') if current else None,
            'params': entry.get('params'), 'inputs': entry.get('inputs'),
            'code': {'fingerprint': code.get('fingerprint'),
                     'modules': study.module_status(entry)},
            'environment': entry.get('environment'),
            'blobs': sorted((entry.get('blobs') or {}).keys()),
            'exposure': {k: record.get(k) for k in EXPOSURE_RECORD_KEYS} if record else None,
            'consumers': consumers,
            'report_anchor': f'r-{rid}' if cited else None,
            'notebook_hint': hint}


# --- the payload -----------------------------------------------------------------------

def evidence(study_dir, *, result_id: str | None = None, limit: int = DEFAULT_LIMIT) -> dict:
    """The ``hypotrail.evidence/1`` payload (CLI-CONTRACT-COMPANION §5)."""
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise StudyError('invalid_arguments', '--limit must be at least 1.',
                         details={'limit': limit})
    study = read.open(study_dir)
    view = view_model.build(study)
    state = study.state
    task = st.task_of(state)
    with texts.task_context(task):
        items = _entries(study)
        by_rid = {i['rid']: i for i in items}
        if result_id is not None and result_id not in by_rid:
            raise StudyError('unknown_result', f'No result {result_id} in the registry.',
                             details={'result_id': result_id})
        slots = {rid: slot for slot, rid in state['current'].items()}
        children: dict[str, list[str]] = {}
        for i in sorted(items, key=_order):
            for parent in rec.upstream(i['entry'], history=False) if i['entry'] else []:
                children.setdefault(parent, []).append(i['rid'])
        selected, truncated = _select(items, set(slots), limit)
        citer = cite.Citer.from_view(view)
        values = placeholders(view)
        results = _result_items(study, view, selected, slots, _promotions(study), children,
                                citer, values)
        manifest = study.artifacts()
        manifest = manifest if isinstance(manifest, dict) and isinstance(
            manifest.get('artifacts'), dict) else {'artifacts': {}}
        sources = _sources(study)
        payload = {
            'schema': SCHEMA, 'ok': True, 'study': str(study.study_dir),
            'revision': state['revision'], 'task': task, 'results': results,
            'truncated': truncated,
            'lineage': _lineage(study, view, results,
                                {i['rid']: i['entry'] for i in selected}, manifest, sources),
            'exposure': _exposure(study), 'impacts': _impacts(study, view),
            'eda_catalog': _eda_catalog(study), 'sources': sources,
            'detail': _detail(study, result_id, by_rid[result_id], manifest)
            if result_id is not None else None}
    return {k: payload[k] for k in PAYLOAD_KEYS}


def main(args: argparse.Namespace) -> cmd.Outcome:
    return cmd.Outcome(evidence(args.study, result_id=args.result, limit=args.limit))


# --- text output (v0.2a, WP-A1) --------------------------------------------------------

def _segments_text(block) -> str:
    if not isinstance(block, Mapping):
        return ''
    return ' '.join(''.join(str(s.get('text', '')) for s in block.get('segments') or [])
                    .split())


def text(payload: Mapping) -> str:
    """``evidence --format text``: the results with their currency and headline, the
    exposure ledger, the sources, and the EDA catalog, in readable lines. Not a contract."""
    lines = [f'Evidence of the {payload["task"]} study at revision {payload["revision"]}', '',
             'Results' + (' (the oldest are not listed)' if payload.get('truncated') else '')]
    if not payload['results']:
        lines.append('  none yet')
    for r in payload['results']:
        name = r.get('slot') or r.get('activity') or r['result_id'][:12]
        if r.get('integrity') != 'ok':
            state = f'fails its integrity check ({r.get("integrity")})'
        elif r.get('current'):
            state = 'current'
        else:
            reason = r.get('stale_reason')
            why = reason.get('reason') if isinstance(reason, Mapping) else reason
            state = 'not current' + (f': {why}' if why else '')
        rows = f', {r["n_rows"]} rows' if isinstance(r.get('n_rows'), int) else ''
        part = f' on {r["partition"]}' if r.get('partition') else ''
        lines.append(f'  {name} (result {r["result_id"][:8]}){part}{rows}: {state}')
        headline = _segments_text(r.get('headline'))
        if headline:
            lines.append(f'    {headline}')
    ledger = (payload.get('exposure') or {}).get('ledger') or []
    lines += ['', 'Rows read (exposure ledger)']
    if not ledger:
        lines.append('  none yet')
    for row in ledger:
        lines.append(f'  {" ".join(str(row["purpose"]).split("_"))} on {row["partition"]}: '
                     f'{row["rows"]} distinct rows, {row["records"]} reads '
                     f'({", ".join(row.get("activities") or [])})')
    lines += ['', 'Sources']
    for label, src in (payload.get('sources') or {}).items():
        lines.append(f'  {label}: {src.get("path")} '
                     + ('(unchanged)' if src.get('matches') else '(changed since the study started)'))
    catalog = (payload.get('eda_catalog') or {}).get('activities') or []
    if catalog:
        lines += ['', 'Exploration catalog (training rows)']
        for a in catalog:
            done = [c['name'] for c in a.get('columns') or [] if c.get('result_id')]
            extra = (f'; explored: {", ".join(done)}' if done else '') if a.get('per_column') \
                else ''
            needs = [str(m.get('decision') or m.get('slot') or m.get('requirement'))
                     if isinstance(m, Mapping) else str(m) for m in a.get('missing') or []]
            ready = 'can run' if a.get('runnable') else \
                'waits for: ' + ', '.join(dict.fromkeys(needs))
            lines.append(f'  {a["activity"]}: {ready}{extra}')
    detail = payload.get('detail')
    if isinstance(detail, Mapping):
        lines += ['', f'Detail of result {str(detail.get("result_id"))[:8]}']
        lines.append('  ' + json.dumps(detail.get('values'), ensure_ascii=False, sort_keys=True))
    return '\n'.join(lines).rstrip()
