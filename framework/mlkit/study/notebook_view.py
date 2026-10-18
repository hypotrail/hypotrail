"""Runtime helpers of the generated notebook and the workbench (ADR 0001, WP3.2).

The notebooks import this module and :mod:`mlkit.study.read` only (plus the pure
``mlkit.study.policy`` in the workbench). It never writes: :func:`open_study` installs
the read-only guard (``HYPOTRAIL_READ_ONLY=1``) before opening the study.

Numbers are shown from registry entries named by ``RESULT_IDS``, which the generator
froze at render time, so the notebook shows the same numbers as the HTML report of
that revision, formatted by the same :class:`mlkit.study.cite.Citer`.

pandas is imported only by :func:`workbench_scores` (through ``read.Study.predictions``).
"""
from __future__ import annotations

import hashlib
import html
import importlib
import importlib.util
from pathlib import Path
from typing import Any, Mapping

from . import cite, guard, read, render_html, texts, view as view_model
from .errors import StudyError

e = html.escape


def open_study(study_dir) -> read.Study:
    """Install the read-only guard (when requested), then open the study read-only."""
    guard.install(study_dir)
    return read.open(Path(study_dir))


def citer(study: read.Study, result_ids: Mapping[str, str]) -> cite.Citer:
    """A citer over the frozen ``RESULT_IDS`` (verified registry entries)."""
    results = {}
    for slot, rid in sorted(result_ids.items()):
        try:
            entry = study.result(rid)
        except StudyError as exc:
            results[rid] = cite.Cited(rid, slot, None, None, False, exc.code)
            continue
        results[rid] = cite.Cited(rid, slot, entry['output']['values'], entry['n_rows'], True, 'ok')
    facts = {fid: f['value'] for fid, f in study.state['facts'].items()}
    return cite.Citer(results, facts)


def banner_html(study: read.Study, generated_revision: int, result_ids: Mapping[str, str]) -> str:
    labels = texts.report()['notebook']
    state = study.state
    moved = [slot for slot, rid in sorted(result_ids.items())
             if state['current'].get(slot) != rid or rid in state['stale']]
    current = study.revision == generated_revision and not moved
    text = labels['banner_current'] if current else labels['banner_stale']
    status = 'current' if current else 'stale'
    return (f'<div class="notice" data-notebook-banner="{status}"><strong>Generated at revision '
            f'<span data-literal="revision">{generated_revision}</span></strong>; the study is at '
            f'revision <span data-literal="revision">{study.revision}</span>. {e(text)} '
            f'{e(labels["read_only"])}</div>')


def step_html(cited: cite.Citer, result_ids: Mapping[str, str], slots: list[str],
              context: str, interpretation: str) -> str:
    """Context, result figures, and interpretation of one step (numbers cited)."""
    pending = texts.load('steps')['pending']
    parts = [f'<p>{cited.expand(context)}</p>'] if context and cited.ready(context) else []
    for slot in slots:
        spec = texts.activity(slot)
        rid = result_ids.get(slot)
        title = e(spec.get('label', slot))
        if rid is None or not cited.citable(rid):
            parts.append(f'<h4>{title}</h4><p><em>{e(pending)}</em></p>')
            continue
        parts.append(f'<h4>{title}</h4>{render_html._figures(cited, rid, spec)}')
    if interpretation and cited.ready(interpretation) and (
            not slots or any(result_ids.get(s) for s in slots)):
        parts.append(f'<p><strong>Interpretation.</strong> {cited.expand(interpretation)}</p>')
    return ''.join(parts)


def decision_html(study: read.Study, decision_id: str) -> str:
    labels = texts.report()
    d = view_model.build(study)['decisions'][decision_id]
    out = f'<p><strong>Decision.</strong> {e(labels["decision_status"][d["status"]])}'
    if d['confirmation'] and d['status'] == 'confirmed':
        out += (f' — {e(labels["user_words"])}: <q data-literal="user_words">'
                f'{e(d["confirmation"]["user_words"])}</q>')
    return out + '</p>'


def source_md(study: read.Study, rid: str) -> str:
    """The activity source of ``rid`` as Markdown (displayed, never executed)."""
    labels = texts.report()['notebook']
    entry = study.result(rid)
    blocks = []
    for name, sha in sorted(entry['code']['modules'].items()):
        spec = importlib.util.find_spec(name)
        path = Path(spec.origin) if spec is not None and spec.origin else None
        if path is None or not path.is_file():
            blocks.append(f'`{name}`: source not found.')
            continue
        raw = path.read_bytes()
        note = '' if hashlib.sha256(raw).hexdigest() == sha else f'\n\n{labels["source_changed"]}'
        blocks.append(f'`{name}`{note}\n\n```python\n{raw.decode("utf-8")}\n```')
    return '\n\n'.join(blocks)


def source_block(study: read.Study, result_ids: Mapping[str, str], slots: list[str]):
    """A collapsed accordion with the source of each slot's result."""
    import marimo as mo

    labels = texts.report()['notebook']
    items = {f'{labels["source_label"]}: {slot}': mo.md(source_md(study, result_ids[slot]))
             for slot in slots if slot in result_ids}
    return mo.accordion(items) if items else mo.md('')


# --- workbench --------------------------------------------------------------------------

def policy_module():
    """``mlkit.study.policy`` if this version has it, else None."""
    if importlib.util.find_spec('mlkit.study.policy') is None:
        return None
    module = importlib.import_module('mlkit.study.policy')
    return module if callable(getattr(module, 'evaluate', None)) else None


def workbench_scores(study: read.Study, slot: str = 'fit.logistic') -> dict:
    """Stored validation predictions of ``slot`` for the slider (lists, not a frame)."""
    entry = study.current(slot)
    if entry is None:
        return {'slot': slot, 'result_id': None, 'current': False, 'n': 0, 'y': [], 'score': [],
                'message': f'No {slot} result yet: fit the model through the agent first.'}
    try:
        frame = study.predictions(entry['result_id'])
    except StudyError as exc:
        return {'slot': slot, 'result_id': entry['result_id'], 'current': False, 'n': 0, 'y': [],
                'score': [], 'message': exc.message}
    return {'slot': slot, 'result_id': entry['result_id'], 'current': study.is_current(slot),
            'n': len(frame), 'y': [int(v) for v in frame['y']],
            'score': [float(v) for v in frame['score']], 'message': None}


def _metrics_row(label: str, rule: str, result: Any) -> str:
    if not isinstance(result, Mapping):
        return f'<tr><td>{e(label)}</td><td><code>{e(rule)}</code></td><td colspan="3">{e(str(result))}</td></tr>'
    cells = []
    for key in ('volume', 'precision', 'recall'):
        value = result.get(key)
        if value is None and key == 'volume':
            value = result.get('selected')
        cells.append(f'<td>{e(cite.fmt_number(value, "pct1" if key != "volume" else "auto")) if cite.is_number(value) else ""}</td>')
    return f'<tr><td>{e(label)}</td><td><code>{e(rule)}</code></td>{"".join(cells)}</tr>'


def experiment_html(policy, scores: Mapping, study: read.Study, rule_kind: str, threshold: float,
                    capacity: int) -> str:
    """Experiment row (not adopted, not recorded) next to the adopted policy."""
    if policy is None:
        return ('<div class="notice">Policy evaluation is not available in this version: '
                '<code>mlkit.study.policy</code> is not installed. The slider changes nothing.</div>')
    if scores['message']:
        return f'<div class="notice">{e(scores["message"])}</div>'
    rule = f'threshold:{threshold}' if rule_kind == 'threshold' else f'capacity:{int(capacity)}'
    rows = [_metrics_row('Experiment, not adopted', rule, policy.evaluate(scores['y'], scores['score'], rule))]
    adopted = study.state['decisions']['policy']
    if adopted['status'] == 'confirmed':
        rows.append(_metrics_row('Adopted (from the study state)', adopted['value'],
                                 policy.evaluate(scores['y'], scores['score'], adopted['value'])))
    else:
        rows.append('<tr><td>Adopted (from the study state)</td><td colspan="4">No policy adopted yet.</td></tr>')
    stale = '' if scores['current'] else '<p class="notice">These predictions are stale.</p>'
    return (f'{stale}<table><thead><tr><th>Policy</th><th>Rule</th><th>Volume</th><th>Precision</th>'
            f'<th>Recall</th></tr></thead><tbody>{"".join(rows)}</tbody></table>'
            '<p><em>Experiments here are not recorded and are not decisions.</em></p>')
