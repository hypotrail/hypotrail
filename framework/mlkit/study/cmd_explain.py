"""``hypotrail explain``: glossary terms with contextual examples, step texts, predictions.

    hypotrail explain --study DIR [--term ID] [--json]

CLI-CONTRACT-COMPANION §6 (C6), payload ``hypotrail.explain/1``: the learning layer's only
source of text. Read-only (R1-R5): it takes no lock, writes nothing, records no exposure,
reads no dataset row, and imports neither pandas, numpy, scikit-learn, nor scipy.

* ``terms``: the glossary of the study's task (``texts.glossary_terms``), in file order.
  Each term's ``example`` is the optional ``cited_example`` template of ``glossary.yaml``
  (decision CA.2; the agent's ``example`` text is never read), resolved into segments when
  every result it cites is current and verified (``example_status: shown``), else null
  (``needs_results``), or null when the term has none (``none``).
* ``steps``: the plan's step texts of ``steps.yaml`` (task-aware), each ``{segments}``; a
  text that cites a result that is not current is null and ``text_status`` is
  ``needs_results``.
* ``predictions``: the "predict before you look" questions of ``learn.yaml`` for the task.
  The engine never stores, receives, or grades an answer.

A **segment** is ``{text}``, or ``{text, result_id, path, value, format}`` for a cited
number (:func:`segments`, shared with ``evidence`` and ``export handoff``). Every number
of a segment is a cited registry value; a case statement (``{{fact:...}}``) is quoted as
recorded.
"""
from __future__ import annotations

import argparse
from typing import Mapping

from . import cite, read, texts
from . import commands as cmd
from . import records as rec
from . import state as st
from . import view as view_model
from .errors import StudyError

SCHEMA = 'hypotrail.explain/1'
PAYLOAD_KEYS = ('schema', 'ok', 'study', 'revision', 'task', 'terms', 'steps', 'predictions')
TERM_KEYS = ('id', 'term', 'definition', 'example', 'example_status', 'steps')
STEP_TEXT_KEYS = ('context', 'method', 'interpretation', 'consequence')
STEP_KEYS = ('concept', *STEP_TEXT_KEYS, 'text_status')
PREDICTION_KEYS = ('id', 'step', 'question', 'choices', 'reveal', 'available')
EXAMPLE_STATUSES = ('shown', 'needs_results', 'none')
NOT_SURE = 'not_sure'


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--term', default=None, metavar='ID', help='only this glossary term')


# --- segments (shared with evidence and export) ----------------------------------------

def placeholders(view: Mapping) -> dict:
    """The values of the ``<rule>`` and ``<unit>`` placeholders of the content templates.

    ``<rule>`` is a rule of the current, verified policy evaluation: the adopted (or
    to-reconfirm) policy when it was evaluated, else the rule of the newest open policy
    proposal, else the first evaluated rule. ``<unit>`` is the target unit recorded by the
    results of a regression study. A placeholder without a value is absent, and a template
    that needs it is not shown."""
    out = {}
    item = view['results'].get('policy.evaluation')
    if item and item['current'] and item['integrity'] == 'ok' \
            and isinstance(item.get('values'), Mapping) \
            and isinstance(item['values'].get('rules'), Mapping):
        by_rule = {rec.canonical_rule(r) or r: r for r in item['values']['rules']}
        decision = view['decisions'].get('policy') or {}
        adopted = decision.get('value') if decision.get('status') in (
            'confirmed', 'reconfirm_required') else None
        proposed = [p['value'] for p in reversed(view['open_proposals'])
                    if p['decision_id'] == 'policy']
        params = item['params'] if isinstance(item.get('params'), Mapping) else {}
        for candidate in [adopted, *proposed, *(params.get('rules') or [])]:
            key = rec.canonical_rule(candidate) or candidate if isinstance(candidate, str) \
                else None
            if key in by_rule:
                out['rule'] = by_rule[key]
                break
    units = sorted({r['values']['unit'] for r in view['results'].values()
                    if isinstance(r.get('values'), Mapping)
                    and isinstance(r['values'].get('unit'), str)})
    if units:
        out['unit'] = units[0]
    return out


def fill(template: str, values: Mapping) -> str | None:
    """``template`` with its ``<name>`` placeholders replaced, or None when one has no
    value."""
    out = template
    for name in ('rule', 'unit', 'sign'):
        marker = f'<{name}>'
        if marker in out:
            if values.get(name) is None:
                return None
            out = out.replace(marker, str(values[name]))
    return out


def segments(template: str | None, citer: cite.Citer, values: Mapping | None = None
             ) -> list[dict] | None:
    """The segments of a content template, or None when it cannot be shown now.

    It cannot be shown when a placeholder has no value, when a ``{{slot:...}}`` names a
    slot without a current, verified result, or when a cited path is absent from the
    result. Every ``{{r:...}}`` and ``{{slot:...}}`` becomes a cited segment; a
    ``{{fact:...}}`` becomes the case statement, quoted as recorded. Adjacent text
    segments are merged. Citations are recorded on ``citer.cited``."""
    if template is None:
        return None
    text = fill(template, values or {})
    if text is None or not citer.ready(text):
        return None
    out: list[dict] = []

    def plain(chunk: str) -> None:
        if not chunk:
            return
        if out and tuple(out[-1]) == ('text',):
            out[-1]['text'] += chunk
        else:
            out.append({'text': chunk})
    pos = 0
    try:
        for m in cite.TEMPLATE.finditer(text):
            plain(text[pos:m.start()])
            kind, ref, arg = m.group(1), m.group(2).strip(), m.group(3)
            if kind == 'fact':
                value = citer.facts.get(ref)
                plain(str(value) if value is not None else (arg or ''))
            else:
                if kind == 'r':
                    rid, _, path = ref.partition('.')
                else:
                    slot, path = citer.split_slot_ref(ref)
                    rid = citer.slot_rid(slot)
                fmt = arg or 'auto'
                number = citer.lookup(rid, path)
                shown = cite.fmt_number(number, fmt)
                citer.cited.append({'result_id': rid, 'path': path, 'value': number,
                                    'text': shown})
                out.append({'text': shown, 'result_id': rid, 'path': path, 'value': number,
                            'format': fmt})
            pos = m.end()
    except StudyError as exc:
        if exc.code == 'untraceable_number':
            return None
        raise
    plain(text[pos:])
    return out


def resolve(template: str | None, citer: cite.Citer, values: Mapping | None = None
            ) -> dict | None:
    """``{"segments": [...]}`` of a template, or None (:func:`segments`)."""
    found = segments(template, citer, values)
    return {'segments': found} if found is not None else None


def _sign(spec: Mapping | None, citer: cite.Citer, values: Mapping) -> str | None:
    """The sentence of ``spec`` chosen by the sign of the value at ``spec.ref``."""
    if not isinstance(spec, Mapping):
        return None
    ref = fill(str(spec.get('ref', '')), values)
    if not ref or not ref.startswith('slot:'):
        return None
    slot, path = citer.split_slot_ref(ref[len('slot:'):])
    rid = citer.slot_rid(slot)
    if rid is None:
        return None
    try:
        number = citer.lookup(rid, path)
    except StudyError:
        return None
    key = 'positive' if number > 0 else 'negative' if number < 0 else 'zero'
    return spec.get(key)


# --- the payload -----------------------------------------------------------------------

def _terms(task: str, plan_steps, citer: cite.Citer, values: Mapping) -> list[dict]:
    concepts: dict[str, list[str]] = {}
    for step_id in plan_steps:
        concept = texts.step(step_id, task).get('concept')
        if concept:
            concepts.setdefault(concept, []).append(step_id)
    out = []
    for term_id, entry in texts.glossary_terms(task).items():
        template = entry.get('cited_example')
        example = resolve(template, citer, values) if template else None
        status = 'none' if not template else ('shown' if example else 'needs_results')
        out.append({'id': term_id, 'term': entry.get('term'),
                    'definition': entry.get('definition'), 'example': example,
                    'example_status': status, 'steps': concepts.get(term_id, [])})
    return out


def _steps(task: str, plan_steps, citer: cite.Citer, values: Mapping) -> dict:
    out = {}
    for step_id in plan_steps:
        content = texts.step(step_id, task)
        term = texts.glossary(content.get('concept'), task) if content.get('concept') else None
        concept = {'segments': [{'text': term['term']}]} if term else None
        item, missing = {'concept': concept}, False
        for key in STEP_TEXT_KEYS:
            template = content.get(key)
            text = resolve(template, citer, values) if template else None
            missing = missing or (template is not None and text is None)
            item[key] = text
        item['text_status'] = 'needs_results' if missing else 'shown'
        out[step_id] = {k: item[k] for k in STEP_KEYS}
    return out


def _predictions(task: str, citer: cite.Citer, values: Mapping) -> list[dict]:
    out = []
    for q in texts.load('learn').get('predictions', []):
        if q.get('task') != task:
            continue
        own = dict(values)
        sign = _sign(q.get('sign'), citer, own)
        if sign is not None:
            own['sign'] = sign
        reveal = resolve(q.get('reveal'), citer, own)
        choices = [{'id': str(c['id']), 'label': str(c['label'])} for c in q['choices']]
        out.append({'id': q['id'], 'step': q['step'], 'question': q['question'],
                    'choices': choices, 'reveal': reveal, 'available': reveal is not None})
    return out


def explain(study_dir, *, term: str | None = None) -> dict:
    """The ``hypotrail.explain/1`` payload (CLI-CONTRACT-COMPANION §6)."""
    study = read.open(study_dir)
    view = view_model.build(study)
    task = st.task_of(view['task'])
    with texts.task_context(task):
        citer = cite.Citer.from_view(view)
        values = placeholders(view)
        plan_steps = [s['id'] for s in view['plan']]
        terms = _terms(task, plan_steps, citer, values)
        if term is not None:
            chosen = [t for t in terms if t['id'] == term]
            if not chosen:
                raise StudyError('invalid_arguments',
                                 f'{term!r} is not a glossary term of this {task} study.',
                                 details={'terms': [t['id'] for t in terms]})
            terms = chosen
        payload = {'schema': SCHEMA, 'ok': True, 'study': str(study.study_dir),
                   'revision': view['revision'], 'task': task, 'terms': terms,
                   'steps': _steps(task, plan_steps, citer, values),
                   'predictions': _predictions(task, citer, values)}
    return {k: payload[k] for k in PAYLOAD_KEYS}


def main(args: argparse.Namespace) -> cmd.Outcome:
    return cmd.Outcome(explain(args.study, term=args.term))
