"""Runtime helpers of the generated notebook and the workbench (ADR 0001, WP3.2).

The notebooks import this module and :mod:`mlkit.study.read` only (plus the pure
``mlkit.study.policy`` in the workbench). It never writes: :func:`open_study` installs
the read-only guard (``HYPOTRAIL_READ_ONLY=1``) before opening the study.

Numbers are shown from registry entries named by ``RESULT_IDS``, which the generator
froze at render time, so the notebook shows the same numbers as the HTML report of
that revision, formatted by the same :class:`mlkit.study.cite.Citer`.

pandas is imported only by the functions that return rows or predictions
(:func:`workbench_scores`, :func:`development_frame`, :func:`training_frame`,
:func:`model_inputs`); the engine views import neither pandas nor scikit-learn.

Rows (v0.2a, WP-A6): :func:`development_frame` and :func:`training_frame` return the study's
**development rows** only, through :func:`mlkit.study.data.load_development`, the same
choke point every activity uses: the sealed final test is never loaded (ADR 0006). The
generated notebook recomputes results the registry already holds from these rows (the same
rows, already recorded as exposure by the activity that computed them); nothing here
records a read, a result, or a decision.
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
              context: str, interpretation: str, task: str | None = None,
              scheme: str | None = None) -> str:
    """Context, result figures, and interpretation of one step (numbers cited).

    ``task`` (``regression`` for a regression study) and ``scheme`` (``cross_validation``,
    B6c) select the display texts."""
    with texts.task_context(task), texts.scheme_context(scheme):
        return _step_html(cited, result_ids, slots, context, interpretation)


def _step_html(cited: cite.Citer, result_ids: Mapping[str, str], slots: list[str],
               context: str, interpretation: str) -> str:
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
        delegated = d['confirmation'].get('basis') == 'delegated_default'
        label = labels['delegated_words'] if delegated else labels['user_words']
        out += (f' — {e(label)}: <q data-literal="user_words">'
                f'{e(d["confirmation"]["user_words"])}</q>')
        if d['confirmation'].get('reason_given') is False:     # v0.3 (WP-B, R27)
            out += f' <em data-reason-given="false">({e(labels["no_reason_given"])})</em>'
        if delegated:
            out += f' <em data-basis="delegated_default">{e(labels["delegated_note"])}</em>'
    return out + '</p>'


def source_md(study: read.Study, rid: str) -> str:
    """The activity source of ``rid`` as Markdown (displayed, never executed)."""
    labels = texts.report()['notebook']
    entry = study.result(rid)
    blocks = []
    for name, sha in sorted(entry['code']['modules'].items()):
        path = read._module_path(name)        # R5E-2: a package data file too
        if path is None or not path.is_file():
            blocks.append(f'`{name}`: source not found.')
            continue
        raw = path.read_bytes()
        note = '' if hashlib.sha256(raw).hexdigest() == sha else f'\n\n{labels["source_changed"]}'
        fence = 'json' if path.suffix == '.json' else 'python'
        blocks.append(f'`{name}`{note}\n\n```{fence}\n{raw.decode("utf-8")}\n```')
    return '\n\n'.join(blocks)


def source_block(study: read.Study, result_ids: Mapping[str, str], slots: list[str]):
    """A collapsed accordion with the source of each slot's result."""
    import marimo as mo

    labels = texts.report()['notebook']
    items = {f'{labels["source_label"]}: {slot}': mo.md(source_md(study, result_ids[slot]))
             for slot in slots if slot in result_ids}
    return mo.accordion(items) if items else mo.md('')


# --- rows for the recomputation cells (v0.2a, WP-A6) -------------------------------------

def values(study: read.Study, rid: str) -> dict:
    """The registered values of result ``rid`` (verified registry entry)."""
    return study.result(rid)['output']['values']


def _development(study: read.Study):
    from . import case as c, data as dt, partition

    state = study.state
    case = c.case_of(state, verify_data=True)
    keys = partition.development_keys(study.blob, partition.inputs(state))
    return case, dt.load_development(case, keys).frame


def _split_keys(study: read.Study, rid: str) -> dict[str, list[str]]:
    from . import records as rec

    entry = study.result(rid)
    if entry['activity'] != 'split':
        raise StudyError('invalid_arguments', f'Result {rid} is not a split.',
                         details={'result_id': rid})
    blobs = entry.get('blobs') or {}
    if not {'train', 'validation'} <= set(blobs):
        raise StudyError('integrity_error', f'Split result {rid} holds no row keys.',
                         details={'result_id': rid, 'blobs': sorted(blobs)})
    return {part: rec.parse_row_keys(study.blob(blobs[part])) for part in ('train', 'validation')}


# Review round 3 (E3-1): the ``partition`` of a development row whose label is delayed (its
# outcome is known only at or after the start of the final test): no split, look at the
# target or fit reads it.
DELAYED_LABEL = 'delayed_label'


def _exclusions(study: read.Study, rid: str | None):
    """The training exclusions the split result ``rid`` was computed without (its
    ``inputs.training_exclusions``), else, before any split, the study's; None when none."""
    from . import partition
    if rid:
        return study.result(rid)['inputs'].get('training_exclusions')
    return partition.training_exclusions(study.state)


def delayed_label_keys(study: read.Study, split_rid: str | None = None) -> list[str]:
    """Review round 3 (E3-1): the development rows the split ``split_rid`` (the current one
    when omitted) leaves out for a delayed label, in file order; empty when none."""
    from . import partition
    rid = split_rid or study.state['current'].get('split')
    keys = partition.excluded_keys(study.blob, _exclusions(study, rid))
    return sorted(keys, key=lambda k: int(k[1:]))


def development_frame(study: read.Study, split_rid: str | None = None):
    """The development rows (pandas DataFrame indexed by row key, in file order), with a
    ``partition`` column: ``train`` or ``validation`` from the split result ``split_rid``
    (the current split when omitted), or None before any split. Never the final test.

    WP-B1: under cross-validation every row the split holds is explored and fitted on, so
    its ``partition`` is ``train``; :func:`folds` gives the fold of each scored row.

    Review round 3 (E3-1): a row the split left out for a delayed label (review-v1,
    ``partition.training_exclusions``) has the partition :data:`DELAYED_LABEL`: it is a
    development row, which the structural checks read, but no look at the target and no fit
    reads it, exactly as the engine leaves it out."""
    _, frame = _development(study)
    frame = frame.copy()
    rid = split_rid or study.state['current'].get('split')
    frame['partition'] = None
    if rid:
        keys = _split_keys(study, rid)
        if _fold_blob(study, rid) is not None:
            frame.loc[[k for k in keys['train'] if k in frame.index], 'partition'] = 'train'
        else:
            for part, rows in keys.items():
                frame.loc[[k for k in rows if k in frame.index], 'partition'] = part
    delayed = [k for k in delayed_label_keys(study, rid) if k in frame.index]
    if delayed:
        frame.loc[delayed, 'partition'] = DELAYED_LABEL
    return frame


def delayed_labels_text(study: read.Study) -> str:
    """Review round 3 (E3-1): the engine's ``delayed_labels_excluded`` limit in the study
    language (the term first, then this study's example), or '' when no row is left out."""
    from . import junior, state as st
    item = st.delayed_labels_limit(study.state)
    if item is None:
        return ''
    return junior.limit_fr(item) if st.language_of(study.state) == junior.FR else item['text']


def delayed_labels_html(study: read.Study) -> str:
    """:func:`delayed_labels_text` as a paragraph of the notebook (empty when none)."""
    text = delayed_labels_text(study)
    return f'<p data-limit="delayed_labels_excluded">{e(text)}</p>' if text else ''


def evaluation_plan(study: read.Study, split_rid: str | None = None):
    """The explicit row-membership plan of a review-v1 split (``{folds: [{id, train_keys,
    validation_keys, ...}], unscored_keys, ...}``, verified against its digest), or None for
    a split without one. Each fold is fitted on its ``train_keys`` and scores its
    ``validation_keys``, as the engine does (:func:`mlkit.study.fit.compute_explicit_cv`)."""
    import json
    from . import evaluation_plan as ep
    rid = split_rid or study.state['current'].get('split')
    if not rid:
        return None
    entry = study.result(rid)
    sha = (entry.get('blobs') or {}).get('evaluation_plan')
    if sha is None:
        return None
    plan = json.loads(study.blob(sha))
    recorded = (entry['output']['values'].get('evaluation_plan') or {}).get('digest')
    if plan.get('schema') != ep.SCHEMA or ep.digest(plan) != recorded:
        raise StudyError('integrity_error', 'The evaluation plan does not match its digest.',
                         details={'result_id': rid})
    return plan


def _fold_blob(study: read.Study, rid: str):
    return (study.result(rid).get('blobs') or {}).get('folds')


def folds(study: read.Study, split_rid: str | None = None):
    """WP-B1: the fold of each development row (pandas Series indexed by row key, in file
    order) of a cross-validation split, or None for a train/validation split."""
    import pandas as pd
    rid = split_rid or study.state['current'].get('split')
    sha = _fold_blob(study, rid) if rid else None
    if sha is None:
        return None
    lines = study.blob(sha).decode('utf-8').splitlines()[1:]
    pairs = [line.split(',') for line in lines if line]
    series = pd.Series([int(f) for _, f in pairs], index=[k for k, _ in pairs], name='fold')
    return series.loc[sorted(series.index, key=lambda k: int(k[1:]))]


def training_frame(study: read.Study):
    """The training rows of the current split (development rows only, never the final
    test), without the ``partition`` column; an empty frame before any split."""
    rid = study.state['current'].get('split')
    blobs = (study.result(rid).get('blobs') or {}) if rid else {}
    if not {'train', 'validation'} <= set(blobs):          # no split, or no row keys
        return _development(study)[1].iloc[0:0]
    frame = development_frame(study, rid)
    return frame[frame['partition'] == 'train'].drop(columns=['partition'])


def model_inputs(study: read.Study, rid: str, train, validation):
    """``(X_train, X_validation)`` exactly as the fit ``rid`` built them: its features, its
    special values as indicator columns, and its confirmed preprocessing learnt on the
    training rows only (:func:`mlkit.study.fit.design` and :func:`mlkit.study.fit.prepare`,
    pure functions; nothing is fitted here)."""
    from . import case as c, fit

    entry = study.result(rid)
    inputs = entry['inputs']
    case = c.case_of(study.state)
    features, special = list(inputs['features']), list(inputs['special_values'])
    train = train.drop(columns=['partition'], errors='ignore')
    validation = validation.drop(columns=['partition'], errors='ignore')
    X_train, _ = fit.design(train, features, special, case)
    X_val, _ = fit.design(validation, features, special, case)
    X_train, X_val, _ = fit.prepare(case, train, validation, X_train, X_val, features,
                                    inputs.get('preprocessing'), special)
    return X_train, X_val


def design_inputs(study: read.Study, rid: str, train, validation):
    """``(X_train, X_validation)`` of the fit ``rid`` before its preparation: its features
    and its special values as indicator columns (:func:`mlkit.study.fit.design`). The
    generated notebook then applies the confirmed preparation as readable pandas steps
    (WP-A9, M3)."""
    from . import case as c, fit

    inputs = study.result(rid)['inputs']
    case = c.case_of(study.state)
    features, special = list(inputs['features']), list(inputs['special_values'])
    train = train.drop(columns=['partition'], errors='ignore')
    validation = validation.drop(columns=['partition'], errors='ignore')
    X_train, _ = fit.design(train, features, special, case)
    X_val, _ = fit.design(validation, features, special, case)
    return X_train, X_val


def preprocessing_words(study: read.Study, rid: str) -> str:
    """The preparation of fit ``rid`` in words (as the report writes it)."""
    value = study.result(rid)['inputs'].get('preprocessing')
    if value is None:
        return 'Preparation: none recorded (a study created before the preprocessing decision)'
    return render_html.value_words('preprocessing', value, None)


def example_html(cited: cite.Citer, term_id: str | None, task: str | None = None,
                 scheme: str | None = None) -> str:
    """The contextual example of a glossary term, with this study's cited numbers, or ''
    when the term has none or its results are not computed yet."""
    with texts.task_context(task), texts.scheme_context(scheme):
        entry = texts.glossary(term_id) if term_id else None
        example = (entry or {}).get('cited_example')
        if not example or not cited.ready(example):
            return ''
        try:
            expanded = cited.expand(example)
        except StudyError as exc:
            # Review round 3: a result that does not hold the value the example cites (the
            # baseline of a review-v1 plan scores each window with the base rate of its own
            # training rows: there is no single training rate) shows no example, as
            # ``hypotrail explain`` does; the term and its definition stay.
            if exc.code == 'untraceable_number':
                return ''
            raise
        return f'<p><em>In this study.</em> {expanded}</p>'


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


def regression_predictions(study: read.Study) -> dict:
    """Stored validation predictions of both regression fits (lists, not frames)."""
    out = {'models': {}, 'message': None}
    for slot in ('fit.linear', 'fit.baseline'):
        entry = study.current(slot)
        if entry is None:
            continue
        try:
            frame = study.predictions(entry['result_id'])
        except StudyError as exc:
            out['message'] = exc.message
            continue
        out['models'][slot] = {'result_id': entry['result_id'], 'current': study.is_current(slot),
                               'row_keys': [str(k) for k in frame['row_key']],
                               'y': [float(v) for v in frame['y']],
                               'prediction': [float(v) for v in frame['prediction']]}
    if not out['models'] and out['message'] is None:
        out['message'] = 'No fitted model yet: fit the models through the agent first.'
    return out


def residuals_html(preds: Mapping, model: str, rows: int) -> str:
    """The validation rows with the largest absolute residuals of ``model`` (an
    experiment: computed here, not recorded, not a decision)."""
    if preds.get('message') and not preds.get('models'):
        return f'<div class="notice">{e(preds["message"])}</div>'
    data = preds['models'].get(model)
    if data is None:
        return f'<div class="notice">No current predictions for {e(model)}.</div>'
    from . import regression
    summary = regression.errors(data['y'], data['prediction'])
    order = sorted(range(len(data['y'])),
                   key=lambda i: (-abs(data['y'][i] - data['prediction'][i]), data['row_keys'][i]))
    body = []
    for i in order[:max(1, int(rows))]:
        residual = data['y'][i] - data['prediction'][i]
        body.append(f'<tr><td><code>{e(data["row_keys"][i])}</code></td>'
                    f'<td>{e(cite.fmt_number(data["y"][i], "f2"))}</td>'
                    f'<td>{e(cite.fmt_number(data["prediction"][i], "f2"))}</td>'
                    f'<td>{e(cite.fmt_number(residual, "f2"))}</td></tr>')
    stale = '' if data['current'] else '<p class="notice">These predictions are stale.</p>'
    return (f'{stale}<p>Experiment, not recorded: MAE {e(cite.fmt_number(summary["mae"], "f2"))}, '
            f'RMSE {e(cite.fmt_number(summary["rmse"], "f2"))}, mean residual '
            f'{e(cite.fmt_number(summary["mean_residual"], "f2"))} on these validation rows.</p>'
            '<table><thead><tr><th>Row</th><th>Observed</th><th>Predicted</th><th>Residual</th>'
            f'</tr></thead><tbody>{"".join(body)}</tbody></table>'
            '<p><em>Experiments here are not recorded and are not decisions.</em></p>')


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
