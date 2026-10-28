"""The nine chapters of the HTML report, each a lesson (lot L6, R8; v4: owner decision
2026-10-27, R25 to R30).

The report reads as an explanation of the study, end to end, in the order it was carried
out: 1. the question and the data; 2. the framing (prediction moment, availability); 3. how it
is evaluated (the sealed final test, the split, the success criterion); 4. what the
exploration showed (the structure first, then the looks at the target, counted); 5. the
preparation of the variables and the readings that motivated it; 6. the models and their
comparison (baseline, candidate, diagnostics, variants; the binary model choice); 7. the
decision rule (binary) or the model choice (regression); 8. the final test; 9. the conclusion
and its limits.

Each chapter is a notion (R25, R29, R30), in this order: its status and evidence marks; "At
this step" (what the step does, why now, what the junior sees and decides); the statistical
term first (``.terme``, from the glossary), then "In this study" (``.ici``, with cited
values); the choice (decision cards with their basis: your words, or automatic and to review,
never both, R26); the evidence, each figure or table in a graph-paper frame with its guided
reading (:func:`mlkit.study.render_guide.frame`); the folds "Example", "Why it holds", "Code"
(an excerpt of the generated notebook's cells), "Where it breaks", "What remains uncertain",
"Learn more"; "What we keep"; and the transition "Done: ... → Next: ...".

The four parts of L6 stay marked with ``data-part`` (``choice``, ``evidence``, ``why``,
``uncertain``); decisions are ``article.decision[data-decision][data-status]``; each result is
placed with ``data-for-slot`` and ``data-evidence-class``.

Every number is a cited registry value (:mod:`mlkit.study.cite`) or a recorded literal; every
text comes from ``content/lesson.yaml``, ``content/report.yaml`` (``narrative``) or
``content/report_fr.yaml``, and ``content/steps.yaml``. Pure: no pandas, numpy, or
scikit-learn.
"""
from __future__ import annotations

import html
import re
from typing import Mapping

from . import cite, render_charts, render_diagnostics, render_guide as g, render_trials, texts
from . import render_evidence as ev
from . import render_html as rh

e = html.escape
lit = rh.lit

CHAPTERS = ('ch1', 'ch2', 'ch3', 'ch4', 'ch5', 'ch6', 'ch7', 'ch8', 'ch9')
# The chapter of each step of the plan (L5's ``structural_eda`` goes with the exploration).
STEP_CHAPTER = {'discover_data': 'ch1', 'prediction_time': 'ch2',
                'feature_availability': 'ch2', 'split': 'ch3', 'error_metric': 'ch3',
                'success_criterion': 'ch3',
                'structural_eda': 'ch4', 'train_eda': 'ch4', 'preprocessing': 'ch5',
                'models': 'ch6', 'model_variant': 'ch6', 'model_choice': 'ch6',
                'policy': 'ch7', 'final_test': 'ch8', 'conclusion': 'ch9'}
# A regression study has no rule: its model choice is chapter seven.
REGRESSION_STEP_CHAPTER = {**STEP_CHAPTER, 'model_choice': 'ch7'}
# The results drawn by a section of their own rather than by a result block.
SECTION_SLOTS = ('policy.evaluation', 'evaluate.regression', 'diag.binary', 'diag.regression',
                 'final_test.evaluation', 'diag.final_test')
# The limits (``not_yet_defensible`` ids) a chapter repeats in its "what remains uncertain";
# every limit is listed in chapter nine.
LIMIT_CHAPTER = {'public_data_already_explored': 'ch1', 'no_time_or_entity_identifier': 'ch1',
                 'sources_changed': 'ch1', 'delayed_labels_excluded': 'ch1',
                 'uncertain_features_included': 'ch2', 'small_validation_partition': 'ch3',
                 'grouped_split_unsupported': 'ch3', 'high_cardinality_grouping': 'ch4',
                 'no_causality': 'ch4', 'data_contingent_preprocessing': 'ch5',
                 'validation_is_not_independent': 'ch6', 'capacity_assumed_for_exercise': 'ch7',
                 'capacity_exceeds_validation': 'ch7', 'adopted_rule_not_evaluated': 'ch7',
                 'final_test_sealed': 'ch8', 'final_test_opening_interrupted': 'ch8',
                 'changed_after_final_test': 'ch8'}
EVIDENCE_CLASSES = ('none', 'structural', 'development', 'final')
GLYPHS = {'none': '○', 'structural': '◇', 'development': '◐', 'final': '●'}
STATUS_GLYPHS = {'done': '✓', 'in_progress': '◔', 'pending': '…', 'absent': '–'}
MAX_NONLINEAR_CHARTS = 2
MAX_CODE_LINES = 28
ACCENTS = {'ch1': 'teal', 'ch2': 'violet', 'ch3': 'blue', 'ch4': 'coral', 'ch5': 'mint',
           'ch6': 'yellow', 'ch7': 'teal', 'ch8': 'pink', 'ch9': 'violet'}


def _labels() -> dict:
    return texts.report()


def _words() -> dict:
    return _labels()['narrative']


def anchor_id(slot: str) -> str:
    return 'ev-' + re.sub(r'[^A-Za-z0-9_-]+', '-', slot)


_HEADING = re.compile(r'<(/?)h([2-5])\b')


def demote(fragment: str, by: int = 1) -> str:
    """A section placed inside a chapter: its headings ``by`` levels down."""
    return _HEADING.sub(lambda m: f'<{m.group(1)}h{min(6, int(m.group(2)) + by)}', fragment)


# --- evidence classes ----------------------------------------------------------------------

def evidence_class(view: Mapping, slot: str, item: Mapping | None) -> str:
    """``final`` for the final test's rows, ``development`` for a look at the outcome or a
    model result, ``structural`` for an exploration that read no target, ``none``
    otherwise (nothing read yet)."""
    if item is None:
        return 'none'
    if item.get('partition') == 'final_test' or slot in ('final_test.evaluation',
                                                         'diag.final_test'):
        return 'final'
    looks = set((view.get('eda_looks') or {}).get('results') or [])
    if item.get('result_id') in looks:
        return 'development'
    if slot.startswith('eda.') and slot != 'eda.single_feature_signal':
        return 'structural'
    return 'development'


def ev_label(kind: str, short: bool = False) -> str:
    words = _words()['evidence_short' if short else 'evidence_class']
    return (f'<span class="ev ev-{kind}" data-evidence-label="{kind}">'
            f'<span aria-hidden="true">{GLYPHS[kind]}</span> {e(words[kind])}</span>')


# --- plan and chapters -----------------------------------------------------------------------

def _step_chapter(view: Mapping) -> dict[str, list[Mapping]]:
    """``{chapter: [step, ...]}`` in plan order; a step the mapping does not know follows
    the chapter of the step before it."""
    mapping = REGRESSION_STEP_CHAPTER if view.get('task') == 'regression' else STEP_CHAPTER
    out: dict[str, list[Mapping]] = {c: [] for c in CHAPTERS}
    last = 'ch1'
    for step in view['plan']:
        last = mapping.get(step['id'], last)
        out[last].append(step)
    return out


def _slot_chapter(slot: str, task: str) -> str | None:
    if slot == 'eda.single_feature_signal':
        return 'ch2'
    if slot == 'split':
        return 'ch3'
    if slot.startswith('eda.'):
        return 'ch4'
    if slot in ('fit.baseline', 'fit.logistic', 'fit.linear') or slot.startswith('fit.variant'):
        return 'ch6'
    if slot in ('diag.binary', 'diag.regression'):
        return 'ch6'
    if slot in ('policy.evaluation', 'evaluate.regression'):
        return 'ch7'
    if slot in ('final_test.evaluation', 'diag.final_test'):
        return 'ch8'
    return None


def _chapter_slots(view: Mapping, cid: str, steps: list[Mapping]) -> list[str]:
    """The result slots of a chapter: those its steps expect (pending ones included), then
    the recorded ones that belong to it."""
    task = view.get('task') or 'binary'
    out: list[str] = []
    for step in steps:
        for slot in rh.slots_of_step(step['id'], view['results'], task, view['plan']):
            if _slot_chapter(slot, task) == cid and slot not in out:
                out.append(slot)
    for slot in sorted(view['results']):
        if _slot_chapter(slot, task) == cid and slot not in out:
            out.append(slot)
    return out


def _status(view: Mapping, cid: str, steps: list[Mapping], slots: list[str]) -> str:
    if cid == 'ch1' and not steps:
        return 'done'                    # the case and the data card are always there
    if not steps:
        return 'absent'
    statuses = [s['status'] for s in steps]
    if all(x == 'done' for x in statuses):
        return 'done'
    decided = [view['decisions'].get(s['decision']) for s in steps if s.get('decision')]
    started = any(x in ('done', 'needs_reconfirmation', 'awaiting_confirmation')
                  for x in statuses) or any(slot in view['results'] for slot in slots) \
        or any(d and d.get('status') != 'open' for d in decided) \
        or any(p['decision_id'] in {s.get('decision') for s in steps}
               for p in view['open_proposals'])
    return 'in_progress' if started else 'pending'


# --- the context of one edition ---------------------------------------------------------------

class Context:
    """What the chapters of one edition share: the view (in the edition's language), the
    citer, the figure numbering, the code cells, the step titles."""

    def __init__(self, view, citer, variables, sample, numbering: g.Numbering | None = None):
        self.view, self.citer = view, citer
        self.variables, self.sample = variables or [], sample
        self.task = view.get('task') or 'binary'
        self.lang = texts.report_language()
        self.titles = rh._step_titles(view.get('task'))
        self.charts = rh.chart_map(view, citer)
        self.steps = _step_chapter(view)
        self.numbering = numbering or g.Numbering()
        self.cells = _code_cells(view, self.task)
        self.status: dict[str, str] = {}
        self.keeps: dict[str, str] = {}
        self.figures: dict[str, str] = {}      # figure kind -> its number (references)
        self.figure_ids: dict[str, str] = {}

    def frame(self, cid: str, kind: str, body: str, **kw) -> str:
        if not body:
            return ''
        out = g.frame(self.numbering, cid, kind, body, **kw)
        if cid != 'verdict':
            self.figures.setdefault(kind, f'{cid[2:]}.{self.numbering.next.get(cid, 0)}')
            found = re.search(r'(?<![\w-])id="([^"]+)"', out)
            if found:
                self.figure_ids.setdefault(kind, found.group(1))
        return out

    def figure_ref(self, kind: str) -> str:
        number = self.figures.get(kind)
        return g.ordinal(number) if number else ''


def _code_cells(view: Mapping, task: str) -> dict:
    """The recomputation cells of the generated notebook, by step (excerpted per chapter)."""
    from . import code_cells, render_notebook
    try:
        target, positive, facts = render_notebook._target(view)
        return code_cells.cells_by_step(view, task, target, positive, facts,
                                        [s['id'] for s in view['plan']])
    except Exception:                    # the report still renders without the excerpts
        return {}


# --- values shared by the texts -----------------------------------------------------------------

def _structure(value) -> str:
    return g.count('structure', value)


def _fact(c: Context, fact_id: str) -> str | None:
    if c.citer.facts.get(fact_id) is None:
        return None
    return c.citer.fact(fact_id, '')


def _rows(c: Context) -> dict[str, str]:
    """The counts of the file: every row, the development rows, the sealed rows."""
    view, citer = c.view, c.citer
    final = view.get('final_test') or {}
    out = {}
    total = (view.get('dataset') or {}).get('rows')
    if cite.is_number(total):
        out['total'] = _structure(total)
    split = citer.slot_rid('split')
    if split and citer.has(split, 'n_rows') \
            and not citer.has(split, 'training_exclusions.n_rows'):
        out['dev'] = citer.num(split, 'n_rows', 'int')
    elif cite.is_number(final.get('development_rows')):
        out['dev'] = _structure(final['development_rows'])
    elif cite.is_number(total):
        out['dev'] = _structure(total)
    if final.get('status') not in (None, 'absent') and cite.is_number(final.get('rows')):
        out['sealed'] = _structure(final['rows'])
    return out


def _available(c: Context) -> tuple[list[str], list[str]]:
    value = (c.view['decisions'].get('feature_availability') or {}).get('value')
    if not isinstance(value, Mapping):
        return [], []
    order = [v['name'] for v in c.variables if v.get('role') == 'feature'] or sorted(value)
    order += sorted(set(value) - set(order))
    used = [n for n in order if value.get(n) in ('available_at_prediction',
                                                 'uncertain_included')]
    excluded = [n for n in order if value.get(n) and n not in used]
    return used, excluded


def _names(names: list[str]) -> str:
    return ', '.join(lit('identifier', n, 'code') for n in names)


def _try(path: str, values: Mapping) -> str | None:
    """The text at ``path`` filled with ``values``, or None when a placeholder has no value
    (a sentence that needs a figure the study does not hold is left out)."""
    if not g.has(path):
        return None
    try:
        return g.t(path, **values)
    except KeyError:
        return None


def _try_text(text: str, values: Mapping) -> str | None:
    try:
        return g.fill(text, values)
    except KeyError:
        return None


# --- the parts of a chapter ---------------------------------------------------------------------

class Parts:
    def __init__(self):
        self.choice = ''
        self.evidence: list[str] = []
        self.values: dict[str, str] = {}
        self.ici: dict[str, str] = {}
        self.keep = ''
        self.breaks: list[str] = []
        self.uncertain: list[str] = []
        self.uncertain_html = ''
        self.plus: list[tuple[str, str]] = []
        self.code_steps: list[str] = []
        self.code_extra: list[tuple[str, str]] = []
        self.after_evidence = ''


def _limits(view: Mapping, cid: str) -> list[str]:
    out = []
    for item in view['not_yet_defensible']:
        if item.get('junior') is False or LIMIT_CHAPTER.get(item['id']) != cid:
            continue
        text = item.get('junior_text') or item['text']
        out.append(f'<li data-limit="{e(item["id"])}">{lit("message", text)}</li>')
    return out


def _decision_cards(c: Context, steps: list[Mapping], skip: tuple = ()) -> list[str]:
    cards = []
    for step in steps:
        did = step.get('decision')
        if did and did in c.view['decisions'] and did not in skip:
            cards.append(rh.decision_card(c.view, did, c.variables, c.titles))
    return cards


def _choice(cards: list[str], label: str | None = None) -> str:
    if not cards:
        return ''
    head = f'<div class="lbl">{e(label or g.say("ui.choice"))}</div>' if label is not False else ''
    return f'<div class="choice">{head}{"".join(cards)}</div>'


def _choice_label(c: Context, steps: list[Mapping]) -> str:
    """"The choice · automatic decisions" when every decision shown is automatic."""
    bases = [((c.view['decisions'].get(s['decision']) or {}).get('confirmation') or {})
             .get('basis') for s in steps if s.get('decision')
             and s['decision'] in c.view['decisions']]
    if bases and all(b == 'automatic' for b in bases):
        return g.say('ui.choice_automatic')
    return g.say('ui.choice')


def _muted(text: str) -> str:
    return f'<p class="muted">{e(text)}</p>'


def _result_figures(c: Context, slot: str) -> str:
    """The figures and tables of one result (``render_html._result_block``)."""
    return rh._result_block(c.view, c.citer, slot)


def _slot_label(slot: str) -> str:
    return rh.slot_title(slot)


def _frame_rows(c: Context, rid: str | None) -> str:
    if rid and c.citer.has(rid, '@n_rows'):
        return g.rows_words(c.citer.num(rid, '@n_rows', 'int'))
    return ''


def _scored() -> str:
    return g.say('ui.frame_words.oof' if texts.is_cv() else 'ui.frame_words.validation')


# --- chapters -----------------------------------------------------------------------------------

BRIEF_LABELS = {
    'en': {'title': 'The use case', 'problem': 'The problem', 'decision': 'The decision helped',
           'objective': 'The objective', 'production': 'In production',
           'data_provenance': 'Where the data come from',
           'users_and_cost_of_error': 'Who uses it, and what an error costs',
           'out_of_scope_and_risks': 'Out of scope and risks',
           'links': 'What it changes for the study'},
    'fr': {'title': "Le cas d'usage", 'problem': 'Le problème', 'decision': 'La décision aidée',
           'objective': "L'objectif", 'production': 'En production',
           'data_provenance': "D'où viennent les données",
           'users_and_cost_of_error': "Qui l'utilise, et ce que coûte une erreur",
           'out_of_scope_and_risks': 'Hors périmètre et risques',
           'links': "Ce que ça change pour l'étude"},
}


def _brief(c: Context) -> str:
    """R66: the use-case brief (``case-brief.yaml`` next to the case), in the edition's
    language, or nothing without one. Its numbers come from the product owner, never from the
    data; the brief says when the scenario is fictitious."""
    from pathlib import Path
    from . import case_brief
    path = ((c.view.get('case') or {}).get('path'))
    if not path:
        return ''
    from .case import load_case
    try:
        case = load_case(path, verify_data=False)
    except Exception:                    # noqa: BLE001 - no readable case: no brief
        return ''
    # R68: the study's own brief, confirmed from the product owner's PDF, comes first.
    own = (c.view.get('brief') or {}).get('confirmed')
    brief = case_brief.validate(own['document']) if own else case_brief.load(
        Path(path).parent, case.target_unit if case.task == 'regression' else None)
    texts_ = case_brief.texts(brief, c.lang)
    if not texts_:
        return ''
    labels = BRIEF_LABELS['fr' if c.lang == 'fr' else 'en']
    rows = ''.join(f'<dt>{e(labels[k])}</dt><dd>{lit("case", texts_[k])}</dd>'
                   for k in case_brief.TEXT_KEYS)
    folds = ''.join(
        f'<details><summary>{e(labels[k])}</summary>'
        + ''.join(f'<p>{lit("case", v)}</p>' for v in texts_[k].values()) + '</details>'
        for k in ('data_provenance', 'users_and_cost_of_error', 'out_of_scope_and_risks'))
    links = ' '.join(texts_['links'].values())
    return (f'<div class="choice case card plain brief" id="brief" data-brief="'
            f'{"fictitious" if brief["source"]["fictitious"] else "real"}">'
            f'<div class="lbl">{e(labels["title"])}</div>'
            f'<p class="cap">{lit("case", texts_["source"])}</p><dl>{rows}</dl>{folds}'
            f'<p><b>{e(labels["links"])}</b> : {lit("case", links)}</p></div>'
            if c.lang == 'fr' else
            f'<div class="choice case card plain brief" id="brief" data-brief="'
            f'{"fictitious" if brief["source"]["fictitious"] else "real"}">'
            f'<div class="lbl">{e(labels["title"])}</div>'
            f'<p class="cap">{lit("case", texts_["source"])}</p><dl>{rows}</dl>{folds}'
            f'<p><b>{e(labels["links"])}</b>: {lit("case", links)}</p></div>')


def _ch1(c: Context, steps, status) -> Parts:
    p, view, citer = Parts(), c.view, c.citer
    rows = _rows(c)
    unit, target = _fact(c, 'observation_unit'), _fact(c, 'target')
    p.values.update(rows)
    p.values['unit'] = unit or e(g.say('ui.unit_unknown'))
    if target:
        p.values['target'] = target
    objective = []
    for fid in ('decision', 'intended_use'):
        fact = rh._fact_value(view, fid)
        if fact:
            objective.append(f'<p class="dec">{lit("case", fact["value"])}</p>')
    if objective:
        p.choice = (f'<div class="choice case card plain" id="objective" data-choice="case">'
                    f'<div class="lbl">{e(g.say("ui.choice_case"))}</div><div class="row">'
                    + ''.join(objective)
                    + f'<div class="meta">{g.stamp("scenario")}<span>'
                      f'{e(g.say("ui.nothing_decided"))}</span></div></div></div>')
    # Lot 2026-10-28 (R66): the product owner's brief of the use case opens the report.
    p.choice = _brief(c) + (p.choice or '')
    final = view.get('final_test') or {}
    opened = final.get('status') == 'opened'
    language = c.lang
    if rows.get('total'):
        dev_n = final.get('development_rows') if cite.is_number(final.get('development_rows')) \
            else view['dataset'].get('rows')
        sealed_n = final.get('rows') if 'sealed' in rows else 0
        bar = render_charts.parts_bar(view['dataset']['rows'], dev_n or 0, sealed_n or 0,
                                      language, opened=opened)
        method = final.get('method')
        if bar and sealed_n and g.has(f'evidence.methods.{method}') \
                and cite.is_number(final.get('fraction')):
            # R53: how the sealed rows were drawn, from the study state.
            bar += (f'<p class="cap" data-partition-method="{e(str(method))}">'
                    + ev.t('partition_how', method=e(ev.say(f'methods.{method}')),
                           fraction=lit('structure', cite.format_value(
                               final['fraction'], 'pct0', language)))
                    + '</p>')
        p.evidence.append(c.frame(
            'ch1', 'parts', bar, stamp_kind='state',
            values={k: rows[k] for k in ('total', 'dev', 'sealed') if k in rows},
            conclude=('opened' if opened else None) if 'sealed' in rows else 'absent',
            attention='opened' if opened else None,
            frame_html=g.frame_line('none', g.rows_words(rows['total']), '',
                                    e(g.say('ui.frame_words.no_model')))))
    facts = rh.data_facts(view, citer, c.variables)
    table = (rh.data_dictionary(view, citer, c.variables) + rh.data_rows(c.sample))
    body = (g.dl(((e(k), v) for k, v in facts), 'facts') + table)
    p.evidence.append(c.frame(
        'ch1', 'columns', body, what='table', figure_id='data', evidence='none',
        values={'n_columns': _structure(len(c.variables))} if c.variables else {},
        conclude=None if c.variables else 'generic',
        frame_html=g.frame_line('structural', rows.get('dev') and g.rows_words(rows['dev'])
                                or '', '', e(g.say('ui.frame_words.no_model')))))
    p.values['fig'] = c.figure_ref('columns')
    structure = view.get('structure') or {}
    group = (structure.get('group_column') or {}).get('value')
    if isinstance(group, str) and group:
        p.values['group'] = lit('identifier', group, 'code')
    time = (structure.get('time_column') or {}).get('value')
    if isinstance(time, str) and time:
        p.values['time'] = lit('identifier', time, 'code')
    if 'sealed' in rows:
        p.ici['final_test'] = g.t('chapters.ch1.here.final_test' + ('_opened' if opened else ''),
                                  sealed=rows['sealed'])
    elif final.get('status') in (None, 'absent'):
        p.ici['final_test'] = g.t('chapters.ch1.here.final_test_absent')
    key = ('keep_opened' if opened else 'keep') if 'sealed' in rows else 'keep_absent'
    p.keep = _try(f'chapters.ch1.{key}', p.values) or ''
    if rows:
        p.plus.append((' · '.join(rows[k] for k in ('total', 'dev', 'sealed') if k in rows),
                       g.t('chapters.ch1.plus.parts')))
    p.code_steps = ['discover_data']
    unknown = view['facts']['by_status'].get('unknown') or []
    for f in unknown:
        translated = rh._fact_value(view, f['id']) or f
        p.breaks.append(f'<li>{lit("case", translated["value"])}</li>')
    p.uncertain = _limits(view, 'ch1')
    return p


def _ch2(c: Context, steps, status) -> Parts:
    p, view, citer = Parts(), c.view, c.citer
    p.choice = _choice(_decision_cards(c, steps), _choice_label(c, steps))
    pt = view['decisions'].get('prediction_time') or {}
    if pt.get('value') and pt.get('status') in ('confirmed', 'reconfirm_required'):
        words = rh.value_words('prediction_time', pt['value'], c.task)
        p.ici['prediction_time'] = g.t('chapters.ch2.here.prediction_time',
                                       moment=rh.recorded('decision_value', words))
    elif _fact(c, 'prediction_time'):
        p.ici['prediction_time'] = g.t('chapters.ch2.here.prediction_time_open',
                                       moment=_fact(c, 'prediction_time'))
    used, excluded = _available(c)
    if used:
        p.values['available'] = _names(used)
        p.values['n_available'] = g.count('decision_value', len(used))
        ici = g.t('chapters.ch2.here.feature_availability', available=p.values['available'],
                  n_available=p.values['n_available'])
        if excluded:
            ici += ' ' + g.t('chapters.ch2.here.feature_availability_excluded',
                             excluded=_names(excluded))
        p.ici['feature_availability'] = ici
        p.ici['leakage'] = g.t('chapters.ch2.here.leakage')
        p.keep = g.t('chapters.ch2.keep', available=p.values['available'])
        p.plus.append((p.values['n_available'], g.t('chapters.ch2.plus.available')))
    else:
        p.ici['feature_availability'] = g.t('chapters.ch2.here.feature_availability_open')
        p.keep = g.t('chapters.ch2.keep_open')
    table = rh._availability_table(view, c.variables)
    if table:
        p.evidence.append(c.frame(
            'ch2', 'availability', table, what='table', stamp_kind='state',
            values={'n_available': g.count('decision_value', len(used)),
                    'n_excluded': g.count('decision_value', len(excluded))},
            conclude=None if used else 'none',
            frame_html=g.frame_line('none', '', '', e(g.say('ui.frame_words.no_model')))))
    for slot in _chapter_slots(view, 'ch2', steps):
        item = view['results'].get(slot)
        rid = item['result_id'] if item else None
        if not citer.citable(rid):
            p.evidence.append(_pending_block(c, slot))
            continue
        values = item['values'] if isinstance(item.get('values'), Mapping) else {}
        flagged = [s.get('feature') for s in values.get('signals') or []
                   if isinstance(s, Mapping) and s.get('flag')]
        chart = ''.join(c.charts.get(slot, []))
        p.evidence.append(c.frame(
            'ch2', 'signal', chart + _result_figures(c, slot), slot=slot,
            evidence=evidence_class(view, slot, item),
            values={'flagged': _names([f for f in flagged if f])} if flagged else {},
            conclude='flagged' if flagged else None,
            frame_html=g.frame_line('development', _frame_rows(c, rid), _scored())))
    items = _limits(view, 'ch2')
    value = (view['decisions'].get('feature_availability') or {}).get('value')
    if isinstance(value, Mapping):
        words = _words()
        doubtful = [n for n in sorted(value)
                    if value[n] in ('uncertain_included', 'uncertain_excluded')]
        if doubtful:
            items.append(f'<li data-limit="uncertain_availability">'
                         f'{e(words["uncertain_features"])} '
                         + ', '.join(f'{lit("identifier", n, "code")} '
                                     f'({e(_labels()["availability"][value[n]].lower())})'
                                     for n in doubtful) + '</li>')
    p.uncertain = items
    return p


def _pending_block(c: Context, slot: str) -> str:
    """A result a chapter expects that cannot be cited: pending or stale, in words."""
    item = c.view['results'].get(slot)
    state = 'stale' if item else 'pending'
    return (f'<div class="evidence-block ev-{state}" id="{anchor_id(slot)}" '
            f'data-evidence-class="{state}" data-for-slot="{e(slot)}">'
            f'{rh._result_block(c.view, c.citer, slot)}</div>')


def _sealing(view: Mapping) -> str:
    """The final test sealed at ``init``: an automatic choice, from the case."""
    final = view.get('final_test') or {}
    if final.get('status') in (None, 'absent'):
        return ''
    rows = (cite.format_value(final['rows'], 'int', texts.report_language())
            if isinstance(final.get('rows'), int) else '')
    key = 'sealed_at_creation' if final.get('status') == 'sealed' else 'opened_at_creation'
    return (f'<div class="row" data-choice="final_test_sealing">'
            f'<p class="dec">{g.t("ui." + key, n=lit("structure", rows))}</p>'
            f'<div class="meta">{g.stamp("creation")}'
            f'<span>{e(_words()["sealing_note"])}</span></div></div>')


def _ch3(c: Context, steps, status) -> Parts:
    p, view, citer = Parts(), c.view, c.citer
    cards = _decision_cards(c, steps)
    sealing = _sealing(view)
    if sealing:
        cards.insert(0, f'<div class="card plain sealing">{sealing}</div>')
    p.choice = _choice(cards, _choice_label(c, steps))
    rows = _rows(c)
    p.values.update(rows)
    split = view['decisions'].get('split') or {}
    if split.get('value') is not None:
        p.values['split'] = lit('decision_value', rh.value_words('split', split['value'],
                                                                 c.task))
        p.ici['cross_validation'] = g.t('chapters.ch3.here.cross_validation',
                                        split=p.values['split'])
        p.ici['validation_partition'] = p.ici['cross_validation']
    else:
        p.ici['cross_validation'] = g.t('chapters.ch3.here.cross_validation_open')
    if 'dev' in rows and texts.is_cv():
        p.ici['out_of_fold'] = g.t('chapters.ch3.here.out_of_fold', dev=rows['dev'])
    sc = view['decisions'].get('success_criterion') or {}
    if sc.get('value') is not None:
        p.values['criterion'] = lit('decision_value', rh._lower_first(rh.value_words(
            'success_criterion', sc['value'], c.task)))
        p.ici['success_criterion'] = g.t('chapters.ch3.here.success_criterion',
                                         criterion=p.values['criterion'])
    else:
        p.ici['success_criterion'] = g.t('chapters.ch3.here.success_criterion_open')
    p.keep = _try('chapters.ch3.keep', p.values) or g.t('chapters.ch3.keep_open')
    rid = citer.slot_rid('split')
    for slot in _chapter_slots(view, 'ch3', steps):
        item = view['results'].get(slot)
        if slot != 'split' or not citer.citable((item or {}).get('result_id')):
            p.evidence.append(_pending_block(c, slot))
            continue
        values = item['values'] if isinstance(item.get('values'), Mapping) else {}
        groups = values.get('groups') if isinstance(values.get('groups'), Mapping) else {}
        fvalues = {'dev': rows.get('dev', '')}
        folds = values.get('folds') if cite.is_number(values.get('folds')) else None
        if folds:
            fvalues['folds'] = citer.num(rid, 'folds', 'int')
        attention = 'temporal' if values.get('method') == 'temporal_folds' else 'none'
        if cite.is_number(groups.get('groups_in_several_folds')) \
                and groups['groups_in_several_folds'] > 0 \
                and citer.has(rid, 'groups.rows_in_shared_groups'):
            fvalues['shared'] = citer.num(rid, 'groups.groups_in_several_folds', 'int')
            fvalues['shared_rows'] = citer.num(rid, 'groups.rows_in_shared_groups', 'int')
            attention = None
        chart = render_charts.fold_blocks(citer, rid, values)
        conclude = None if folds and rows.get('dev') else 'generic'
        if not folds and citer.has(rid, 'partitions.train.n_rows') \
                and citer.has(rid, 'partitions.validation.n_rows') and not texts.is_cv():
            fvalues['train'] = citer.num(rid, 'partitions.train.n_rows', 'int')
            fvalues['validation'] = citer.num(rid, 'partitions.validation.n_rows', 'int')
            conclude = 'holdout'
        p.evidence.append(c.frame(
            'ch3', 'folds', chart + _result_figures(c, slot), slot=slot,
            evidence=evidence_class(view, slot, item), values=fvalues,
            conclude=conclude,
            attention=attention,
            frame_html=g.frame_line('none', _frame_rows(c, rid), '',
                                    e(g.say('ui.frame_words.no_model')))))
        if folds:
            p.plus.append((fvalues['folds'], g.t('chapters.ch3.plus.folds')))
            rotation = ev.cv_rotation(citer, rid, values)
            if rotation and rows.get('dev'):
                p.evidence.append(c.frame(
                    'ch3', 'cv_rotation', rotation, slot=slot,
                    evidence=evidence_class(view, slot, item),
                    values={'folds': citer.num(rid, 'folds', 'int'), 'dev': rows['dev']},
                    attention=None if values.get('method') == 'temporal_folds' else 'none',
                    frame_html=g.frame_line('none', _frame_rows(c, rid), '',
                                            e(g.say('ui.frame_words.no_model')))))
    p.values['fig'] = c.figure_ref('folds')
    p.code_steps = ['split']
    p.uncertain = _limits(view, 'ch3')
    return p


# The order of the explorations in chapter four (mockup D14): quality, distributions and
# associations first; then the target, its special values, and the rates or means by group.
EXPLORATION_ORDER = ('eda.quality', 'eda.distribution', 'eda.correlation', 'eda.target_rate',
                     'eda.target_summary', 'eda.special_values', 'eda.rate_by', 'eda.mean_by')
EDA_KIND = {'eda.quality': 'quality', 'eda.distribution': 'distribution',
            'eda.correlation': 'correlation', 'eda.target_rate': 'target_balance',
            'eda.target_summary': 'target_summary', 'eda.special_values': 'special_values',
            'eda.rate_by': 'by_group', 'eda.mean_by': 'by_group'}


BY_GROUP_SLOTS = ('eda.mean_by', 'eda.rate_by')


def _exploration_order(slot: str) -> tuple:
    base = slot.partition(':')[0]
    rank = EXPLORATION_ORDER.index(base) if base in EXPLORATION_ORDER else len(EXPLORATION_ORDER)
    return rank, slot


def _eda_values(c: Context, slot: str, rid: str, values: Mapping) -> tuple[dict, str | None]:
    citer = c.citer
    base = slot.partition(':')[0]
    if base == 'eda.quality' and citer.has(rid, 'n_rows_with_missing') \
            and citer.has(rid, 'n_rows'):
        return ({'rows_missing': citer.num(rid, 'n_rows_with_missing', 'int'),
                 'rows': citer.num(rid, 'n_rows', 'int')}, None)
    if base == 'eda.target_summary' and citer.has(rid, 'mean') and citer.has(rid, 'sd'):
        return {'mean': citer.num(rid, 'mean', 'f2'), 'sd': citer.num(rid, 'sd', 'f2')}, None
    if base == 'eda.target_rate' and citer.has(rid, 'rate'):
        return {'rate': citer.num(rid, 'rate', 'pct1')}, None
    if base == 'eda.distribution' and citer.has(rid, 'n_rows'):
        return {'rows': citer.num(rid, 'n_rows', 'int')}, None
    if base in ('eda.special_values', 'eda.rate_by', 'eda.mean_by', 'eda.correlation'):
        return {}, None
    return {}, 'none'


def _ch4(c: Context, steps, status) -> Parts:
    p, view, citer = Parts(), c.view, c.citer
    words = _words()
    slots = sorted(_chapter_slots(view, 'ch4', steps), key=_exploration_order)
    structural = [s for s in slots if view['results'].get(s) and
                  evidence_class(view, s, view['results'][s]) == 'structural']
    looks = [s for s in slots if s not in structural]
    run = [s for s in slots if s in view['results']]
    if run:
        items = ''.join(
            f'<li><a href="#{anchor_id(s)}">{e(_slot_label(s))}</a> '
            f'{ev_label(evidence_class(view, s, view["results"][s]), True)}</li>'
            for s in structural + [x for x in looks if x in view['results']])
        p.choice = (f'<div class="choice"><div class="lbl">'
                    f'{e(g.say("ui.choice_explorations"))}</div><div class="card plain">'
                    f'<p>{e(words["exploration_choice"])}</p><ul class="explored">{items}</ul>'
                    f'</div></div>')
    else:
        p.choice = _muted(words['exploration_none'])
    for group, heading, note in ((structural, words['structural_heading'],
                                  words['structural_note']),
                                 (looks, words['target_heading'], '')):
        if not group:
            continue
        p.evidence.append(f'<h4 class="sub-h">{e(heading)}</h4>'
                          + (f'<p class="src">{e(note)}</p>' if note else ''))
        for slot in group:
            item = view['results'].get(slot)
            rid = item['result_id'] if item else None
            if not citer.citable(rid):
                p.evidence.append(_pending_block(c, slot))
                continue
            kind = EDA_KIND.get(slot.partition(':')[0], 'distribution')
            values = item['values'] if isinstance(item.get('values'), Mapping) else {}
            fvalues, conclude = _eda_values(c, slot, rid, values)
            cls = evidence_class(view, slot, item)
            charts = c.charts.get(slot, [])
            # 2026-10-28 (R42): under a chart, the result's figures without the question,
            # the term and the rows the chart and the frame already give; a mean or rate by
            # group keeps its highlighted figures, its table being the chart's own values.
            figures = (rh._result_block(view, citer, slot, compact=True,
                                        tables=slot.partition(':')[0] not in BY_GROUP_SLOTS)
                       if charts else _result_figures(c, slot))
            body = (f'<div class="evidence-block ev-{cls}" id="{anchor_id(slot)}">'
                    + ''.join(charts) + figures + '</div>')
            p.evidence.append(c.frame(
                'ch4', kind, body, slot=slot, evidence=cls, values=fvalues, conclude=conclude,
                what='chart' if c.charts.get(slot) else 'table',
                frame_html=g.frame_line('structural' if cls == 'structural' else 'development',
                                        _frame_rows(c, rid), '',
                                        e(g.say('ui.frame_words.no_model')))))
            if slot == 'eda.quality' and conclude is None:
                view_chart = ev.column_view(citer, rid, values, _transformed(c))
                if view_chart:
                    p.evidence.append(c.frame(
                        'ch4', 'column_view', view_chart, slot=slot, evidence=cls,
                        values=fvalues,
                        frame_html=g.frame_line('structural', _frame_rows(c, rid), '',
                                                e(g.say('ui.frame_words.no_model')))))
    looks_data = view.get('eda_looks') or {}
    count = looks_data.get('target_looks')
    if isinstance(count, int) and count:
        labels = {a: texts.activity(a).get('label') or a for a in looks_data.get('by_activity') or {}}
        chart = render_charts.looks_chart(looks_data.get('by_activity') or {}, labels, c.lang)
        p.evidence.append(c.frame(
            'ch4', 'looks', chart + rh._looks(view), stamp_kind='state',
            values={'looks': _structure(count)},
            frame_html=g.frame_line('development', '', '', '', final_note=False)))
        p.values['looks'] = _structure(count)
        p.ici['target_look'] = g.t('chapters.ch4.here.target_look', looks=_structure(count))
        p.keep = g.t('chapters.ch4.keep', looks=_structure(count))
        p.plus.append((_structure(count), g.t('chapters.ch4.plus.looks')))
    else:
        p.ici['target_look'] = g.t('chapters.ch4.here.target_look_none')
        p.keep = g.t('chapters.ch4.keep_none')
    p.values['fig'] = c.figure_ref('looks')
    p.code_steps = ['train_eda']
    items = _limits(view, 'ch4')
    if isinstance(count, int) and count:
        items.insert(0, f'<li data-limit="target_looks">{e(words["looks_limit"])} '
                        f'({_structure(count)} {e(words["looks_count"])})</li>')
    p.uncertain = items
    return p


def _transformed(c: Context) -> list[str]:
    """The columns the recorded preparation transforms (signed log, caps)."""
    value = (c.view['decisions'].get('preprocessing') or {}).get('value')
    if not isinstance(value, Mapping):
        return []
    return [str(x) for x in value.get('log_transform') or []] + \
        [str(x) for x in (value.get('caps') or {})]


def _ch5(c: Context, steps, status) -> Parts:
    p, view = Parts(), c.view
    words = _words()
    p.choice = _choice(_decision_cards(c, steps), _choice_label(c, steps))
    decision = view['decisions'].get('preprocessing') or {}
    value = decision.get('value')
    if isinstance(value, Mapping):
        prep = lit('decision_value', rh.value_words('preprocessing', value, c.task))
        contingent = g.t('chapters.ch5.contingent_yes' if value.get('data_contingent')
                         else 'chapters.ch5.contingent_no')
        p.ici['data_contingent_decision'] = g.t('chapters.ch5.here.data_contingent_decision',
                                                preparation=prep, contingent=contingent)
        p.keep = g.t('chapters.ch5.keep', preparation=prep)
    else:
        p.ici['data_contingent_decision'] = g.t('chapters.ch5.here.data_contingent_decision_open')
        p.keep = g.t('chapters.ch5.keep_open')
    links = []
    by_rid = {item.get('result_id'): slot for slot, item in view['results'].items()}
    for rid in (value.get('motivated_by') or []) if isinstance(value, Mapping) else []:
        slot = by_rid.get(rid)
        if slot and c.citer.citable(rid):
            links.append(f'<li data-motivated-by="{e(rid)}"><a href="#{anchor_id(slot)}">'
                         f'{e(_slot_label(slot))}</a> '
                         f'{ev_label(evidence_class(view, slot, view["results"][slot]), True)}'
                         f'</li>')
    if links:
        p.evidence.append(f'<div class="card plain motivation-card"><p>'
                          f'{e(words["motivation_heading"])}</p>'
                          f'<ul class="motivation">{"".join(links)}</ul></div>')
    elif status == 'absent':
        p.evidence.append(_muted(words['absent_chapter']))
    else:
        p.evidence.append(_muted(words['motivation_none']))
    fit_slot = 'fit.linear' if c.task == 'regression' else 'fit.logistic'
    fit = c.citer.slot_rid(fit_slot)
    pipe = ev.pipeline(view, c.citer, fit_slot, c.citer.slot_rid('eda.quality')) if fit else ''
    if pipe and isinstance(value, Mapping):
        p.evidence.insert(0, c.frame(
            'ch5', 'pipeline', pipe, slot=fit_slot, evidence='development',
            values={'preparation': lit('decision_value', rh.value_words('preprocessing', value,
                                                                        c.task))},
            attention=None if value.get('data_contingent') else 'none',
            frame_html=g.frame_line('development', _frame_rows(c, fit), '',
                                    e(rh.capital(rh.model_name(fit_slot))), final_note=False)))
    if fit:
        from .code_cells import preparation_steps
        code = preparation_steps(c.citer.results[fit].values)
        if code:
            p.code_extra.append(('preparation', code))
    p.uncertain = _limits(view, 'ch5')
    return p


def _nonlinear_frames(c: Context, cid: str) -> list[str]:
    """L6: the gap between the observed outcome and the mean prediction by range of each
    flagged feature (``linear_checks`` of the development diagnostics, recorded values)."""
    slot = render_diagnostics.DEVELOPMENT_SLOTS[c.task]
    rid = c.citer.slot_rid(slot)
    if rid is None:
        return []
    checks = (c.citer.results[rid].values.get('linear_checks') or {})
    out = []
    for i, check in enumerate(checks.get('nonlinearity') or []):
        if isinstance(check, Mapping) and check.get('flagged') \
                and len(out) < MAX_NONLINEAR_CHARTS:
            chart = render_charts.nonlinearity(c.citer, rid, i, check, _words()['charts'],
                                               binary=c.task != 'regression')
            feature = lit('identifier', check.get('feature', ''), 'code')
            out.append(c.frame(cid, 'nonlinearity', chart, values={'feature': feature},
                               slot=slot, evidence='development',
                               frame_html=g.frame_line('development', _frame_rows(c, rid),
                                                       _scored(),
                                                       e(rh.model_name(
                                                           'fit.linear' if c.task == 'regression'
                                                           else 'fit.logistic')))))
    return [f for f in out if f]


def _diag_wrap(c: Context, cid: str, slot: str, evidence: str, model: str):
    rid = c.citer.slot_rid(slot)
    line = g.frame_line(evidence, _frame_rows(c, rid), _scored() if evidence != 'final' else '',
                        e(rh.model_name(model)) if model else '')

    def wrap(kind, body, *, values=None, conclude=None, attention=None, what='chart'):
        if not body:
            return ''
        return c.frame(cid, kind, body, values=values or {}, conclude=conclude,
                       attention=attention, what=what, slot=slot, evidence=evidence,
                       frame_html=line)
    return wrap


def _models_frame(c: Context, slots: list[str]) -> str:
    """The fitted models of chapter six, side by side: each result's recorded figures."""
    blocks = []
    for slot in slots:
        item = c.view['results'].get(slot)
        rid = item['result_id'] if item else None
        if not c.citer.citable(rid):
            blocks.append(_pending_block(c, slot))
            continue
        cls = evidence_class(c.view, slot, item)
        blocks.append(f'<div class="evidence-block ev-{cls}" id="{anchor_id(slot)}" '
                      f'data-evidence-class="{cls}" data-for-slot="{e(slot)}">'
                      f'{_result_figures(c, slot)}</div>')
    return ''.join(blocks)


def _ch6(c: Context, steps, status) -> Parts:
    p, view, citer = Parts(), c.view, c.citer
    skip = () if c.task != 'regression' else ('model_choice',)
    p.choice = _choice(_decision_cards(c, steps, skip), _choice_label(c, steps))
    slots = [s for s in _chapter_slots(view, 'ch6', steps) if s not in SECTION_SLOTS]
    evaluation = citer.slot_rid('evaluate.regression' if c.task == 'regression'
                                else 'policy.evaluation')
    fvalues, conclude = {}, 'none'
    candidate = 'fit.linear' if c.task == 'regression' else 'fit.logistic'
    if c.task == 'regression' and evaluation:
        m = cite.format_path(['models', candidate, 'mae'])
        b = cite.format_path(['models', 'fit.baseline', 'mae'])
        if citer.has(evaluation, m) and citer.has(evaluation, b):
            fvalues = {'mae_model': citer.num(evaluation, m, 'f2'),
                       'mae_base': citer.num(evaluation, b, 'f2')}
            conclude = None
            p.keep = g.t('chapters.ch6.keep', **fvalues)
            p.ici['baseline'] = g.t('chapters.ch6.here.baseline', mae_base=fvalues['mae_base'])
    elif c.task != 'regression' and evaluation:
        auc = cite.format_path(['ranking', candidate, 'roc_auc'])
        if citer.has(evaluation, auc):
            fvalues = {'auc': citer.num(evaluation, auc, 'f3')}
            conclude = 'binary'
            p.keep = g.t('chapters.ch6.keep', auc=fvalues['auc'])
        p.ici['baseline'] = g.t('chapters.ch6.here.baseline')
    if conclude == 'none':
        conclude = 'generic'
    if not p.keep:
        p.keep = g.t('chapters.ch6.keep_none')
    if slots:
        p.evidence.append(c.frame(
            'ch6', 'fits', _models_frame(c, slots), what='table', values=fvalues,
            conclude=conclude, frame_html=g.frame_line('development', '', _scored())))
    diag_slot = render_diagnostics.DEVELOPMENT_SLOTS[c.task]
    diag_rid = citer.slot_rid(diag_slot)
    if diag_rid:
        model = render_diagnostics._focus(view, citer.results[diag_rid].values, c.task)
        wrap = _diag_wrap(c, 'ch6', diag_slot, 'development', model)
        nonlinear = ''.join(_nonlinear_frames(c, 'ch6'))
        body = render_diagnostics.section(view, citer, final=False, wrap=wrap)
        p.evidence.append(f'<div class="evidence-block ev-development diag-block" '
                          f'id="{anchor_id(diag_slot)}" data-evidence-class="development" '
                          f'data-for-slot="{e(diag_slot)}">{nonlinear}'
                          f'{demote(body, 2)}</div>')
    elif status != 'pending':
        p.evidence.append(demote(render_diagnostics.section(view, citer, final=False), 2))
    trials = render_trials.section(view, citer)
    if trials:
        p.evidence.append(_fold_frame(c))
        p.evidence.append(_variants_frame(c, trials))
    trials_count = (view.get('trials') or {}).get('count')
    if isinstance(trials_count, int) and trials_count:
        p.plus.append((_structure(trials_count), g.t('chapters.ch6.plus.trials')))
    p.code_steps = ['models', 'model_variant']
    p.uncertain = _limits(view, 'ch6')
    return p


def _selection_values(c: Context):
    slot = 'evaluate.regression' if c.task == 'regression' else 'policy.evaluation'
    rid = c.citer.slot_rid(slot)
    values = c.citer.results[rid].values if rid else None
    sel = values.get('model_selection') if isinstance(values, Mapping) else None
    if not isinstance(sel, Mapping) or not sel.get('available'):
        return None, None, None
    return rid, values, sel


def _fold_frame(c: Context) -> str:
    rid, values, sel = _selection_values(c)
    if sel is None:
        return ''
    names = [rh.model_name(str(conf.get('slot'))) for conf in sel.get('configurations') or []
             if isinstance(conf, Mapping)]
    chart = render_charts.fold_scores(c.citer, rid, sel, names, _words()['charts'])
    if not chart:
        return ''
    configs = [x for x in sel.get('configurations') or [] if isinstance(x, Mapping)]
    fmt = 'f3' if sel.get('metric') == 'roc_auc' else 'f2'
    best = sel.get('best')
    fvalues, conclude = {}, 'none'
    index = {str(x.get('slot')): i for i, x in enumerate(configs)}
    if best in index and configs:
        fvalues = {'best': e(rh.model_phrase(best)),
                   'best_mean': c.citer.num(rid, f'model_selection.configurations.'
                                                 f'{index[best]}.mean', fmt),
                   'candidate_mean': c.citer.num(rid, 'model_selection.configurations.0.mean',
                                                 fmt)}
        conclude = None
    noise = 'noise' if (sel.get('advice') or {}).get('code') == 'fold_noise' else None
    return ('<div class="evidence-block ev-development" id="ev-fold-scores" '
            'data-evidence-class="development" data-for-chart="fold_scores">'
            + c.frame('ch6', 'fold_lines', chart, values=fvalues, conclude=conclude,
                      attention=noise, evidence='development',
                      frame_html=g.frame_line('development', _frame_rows(c, rid), _scored()))
            + '</div>')


def _variants_frame(c: Context, trials: str) -> str:
    rid, values, sel = _selection_values(c)
    fvalues, conclude = {}, 'generic'
    if sel is not None:
        one = sel.get('one_se') or {}
        if one.get('pick') and one.get('best'):
            fvalues = {'pick': e(rh.model_phrase(one['pick'])),
                       'best': e(rh.model_phrase(one['best']))}
            conclude = None
    return c.frame('ch6', 'variants', demote(trials, 2), what='table', values=fvalues,
                   conclude=conclude,
                   frame_html=g.frame_line('development', _frame_rows(c, rid), _scored()))


def _tension(c: Context) -> str:
    """R26: the one-standard-error rule keeps a simpler configuration while a paired
    difference shows another one better with an interval that excludes zero: say so."""
    rid, values, sel = _selection_values(c)
    if sel is None:
        return ''
    one = sel.get('one_se') or {}
    pick, best = one.get('pick'), one.get('best')
    if not pick or not best or pick == best:
        return ''
    lower = sel.get('direction', 'lower') == 'lower'
    metric = sel.get('metric') or 'mae'
    comparisons = values.get('comparisons') if isinstance(values.get('comparisons'), Mapping) \
        else {}
    d = ((comparisons.get(best) or {}).get(metric) if isinstance(comparisons.get(best), Mapping)
         else None)
    reference = (comparisons.get(best) or {}).get('reference') \
        if isinstance(comparisons.get(best), Mapping) else None
    fmt = 'f3' if metric == 'roc_auc' else 'f2'
    if isinstance(d, Mapping) and reference == pick \
            and all(cite.is_number(d.get(k)) for k in ('point', 'low', 'high')):
        excludes = d['high'] < 0 if lower else d['low'] > 0
        base = cite.format_path(['comparisons', best, metric])
        if not excludes:
            return ''
        gap = c.citer.num(rid, base + '.point', fmt)
        low, high = c.citer.num(rid, base + '.low', fmt), c.citer.num(rid, base + '.high', fmt)
    else:
        configs = {str(x.get('slot')): (i, x) for i, x in
                   enumerate(sel.get('configurations') or []) if isinstance(x, Mapping)}
        found = configs.get(best)
        diff = (found[1].get('difference') or {}) if found else {}
        if not found or diff.get('against') != pick or not all(
                cite.is_number(diff.get(k)) for k in ('mean', 'low', 'high')):
            return ''
        excludes = diff['high'] < 0 if lower else diff['low'] > 0
        if not excludes:
            return ''
        base = f'model_selection.configurations.{found[0]}.difference'
        gap = c.citer.num(rid, base + '.mean', fmt)
        low, high = c.citer.num(rid, base + '.low', fmt), c.citer.num(rid, base + '.high', fmt)
    return ('<p data-tension="one_se">'
            + g.t('figures.paired.tension', pick=e(rh.model_phrase(pick)),
                  other=e(rh.model_phrase(best)), gap=gap, low=low, high=high) + '</p>')


def _ch7(c: Context, steps, status) -> Parts:
    p, view, citer = Parts(), c.view, c.citer
    p.choice = _choice(_decision_cards(c, steps), _choice_label(c, steps))
    slot = 'evaluate.regression' if c.task == 'regression' else 'policy.evaluation'
    rid = citer.slot_rid(slot)
    if rid is None:
        if status == 'absent':
            p.evidence.append(_muted(_words()['absent_chapter']))
        else:
            p.evidence.append(_pending_block(c, slot))
        p.keep = g.t('chapters.ch7.keep_none')
        p.uncertain = _limits(view, 'ch7')
        return p
    values = citer.results[rid].values
    line = g.frame_line('development', _frame_rows(c, rid), _scored())
    if c.task == 'regression':
        _ch7_regression(c, p, rid, values, line)
    else:
        _ch7_binary(c, p, rid, values, line)
    sel = values.get('model_selection') if isinstance(values, Mapping) else None
    one = (sel or {}).get('one_se') or {}
    rule = ev.one_se(citer, rid, sel) if isinstance(sel, Mapping) else ''
    if rule and one.get('pick') and one.get('best'):
        p.evidence.insert(1, c.frame(
            'ch7', 'one_se', rule, slot=slot, evidence='development',
            values={'pick': e(rh.model_phrase(one['pick'])),
                    'best': e(rh.model_phrase(one['best']))},
            frame_html=line))
    if one.get('pick') and one.get('best'):
        p.ici['one_se'] = g.t('chapters.ch7.here.one_se', pick=e(rh.model_phrase(one['pick'])),
                              best=e(rh.model_phrase(one['best']))) \
            if g.has('chapters.ch7.here.one_se') else ''
    p.code_steps = ['model_choice', 'policy']
    p.uncertain = _limits(view, 'ch7')
    return p


def _ch7_regression(c: Context, p: Parts, rid: str, values: Mapping, line: str) -> None:
    citer, view = c.citer, c.view
    candidate = values.get('candidate') or 'fit.linear'
    chart = render_charts.paired_differences(citer, rid, values, 'mae', 'f2',
                                             rh.model_short('fit.baseline'),
                                             rh.model_short(candidate))
    d = cite.format_path(['deltas', candidate, 'mae'])
    pvalues, conclude = {}, 'none'
    if all(citer.has(rid, f'{d}.{k}') for k in ('point', 'low', 'high')):
        pvalues = {k: citer.num(rid, f'{d}.{x}', 'f2')
                   for k, x in (('delta', 'point'), ('low', 'low'), ('high', 'high'))}
        conclude = None
    tension = _tension(c)
    p.evidence.append(c.frame('ch7', 'paired', chart, values=pvalues, conclude=conclude,
                              extra_attention=tension, slot='evaluate.regression',
                              evidence='development', frame_html=line))
    res = values.get('residuals') if isinstance(values.get('residuals'), Mapping) else {}
    rvalues, rconclude = {}, 'none'
    q = cite.format_path(['residuals', candidate])
    qb = cite.format_path(['residuals', 'fit.baseline'])
    if all(citer.has(rid, f'{x}.{k}') for x in (q, qb) for k in ('q25', 'q75')):
        rvalues = {'q25': citer.num(rid, f'{q}.q25', 'f2'), 'q75': citer.num(rid, f'{q}.q75', 'f2'),
                   'base_q25': citer.num(rid, f'{qb}.q25', 'f2'),
                   'base_q75': citer.num(rid, f'{qb}.q75', 'f2')}
        rconclude = None
    if res:
        p.evidence.append(c.frame('ch7', 'residual_boxes',
                                  render_charts.residuals(citer, rid, values), values=rvalues,
                                  conclude=rconclude, frame_html=line))
    blocks = values.get('residuals_by') or []
    if blocks and isinstance(blocks[0], Mapping):
        groups = [(j, g_) for j, g_ in enumerate(blocks[0].get('groups') or [])
                  if isinstance(g_, Mapping)
                  and cite.is_number(((g_.get('models') or {}).get(candidate) or {}).get(
                      'mean_residual'))]
        bvalues, bconclude = {}, 'none'
        if len(groups) >= 2:
            first, last = groups[0][0], groups[-1][0]
            path = 'residuals_by.0.groups.{}.models.' + cite.format_path([candidate]) \
                + '.mean_residual'
            bvalues = {'first': citer.num(rid, path.format(first), 'f2'),
                       'last': citer.num(rid, path.format(last), 'f2')}
            bconclude = None
        column = lit('identifier', blocks[0].get('column', ''), 'code')
        p.evidence.append(c.frame('ch7', 'residual_by_period',
                                  render_charts.residuals_by(citer, rid, values),
                                  values=bvalues, conclude=bconclude,
                                  title_values={'column': column}, frame_html=line))
    p.evidence.append(c.frame('ch7', 'comparison',
                              demote(rh._model_comparison(view, citer, charted=True), 1),
                              what='table', values={'delta': pvalues.get('delta', '')},
                              conclude='none' if not pvalues else None, frame_html=line))
    choice = view['decisions'].get('model_choice') or {}
    chosen = choice.get('value') if choice.get('status') in ('confirmed', 'reconfirm_required') \
        else None
    dc = cite.format_path(['deltas', str(chosen), 'mae']) if chosen else ''
    if chosen and all(citer.has(rid, f'{dc}.{k}') for k in ('point', 'low', 'high')):
        p.keep = g.t('chapters.ch7.keep', chosen=e(rh.capital(rh.model_phrase(chosen))),
                     delta=citer.num(rid, f'{dc}.point', 'f2'),
                     low=citer.num(rid, f'{dc}.low', 'f2'),
                     high=citer.num(rid, f'{dc}.high', 'f2'))
    else:
        p.keep = g.t('chapters.ch7.keep_none')


def _ch7_binary(c: Context, p: Parts, rid: str, values: Mapping, line: str) -> None:
    citer, view = c.citer, c.view
    rule = (view.get('criterion') or {}).get('rule')
    adopted = view['decisions'].get('policy') or {}
    if rule is None and adopted.get('status') in ('confirmed', 'reconfirm_required'):
        rule = str(adopted.get('value')).partition('@')[0]
    from .records import policy_model
    model = (view.get('criterion') or {}).get('model') or (
        policy_model(adopted.get('value')) if adopted.get('value') else 'fit.logistic')
    pvalues, conclude = {}, 'none'
    if rule:
        m = cite.format_path(['rules', rule, 'models', model, 'precision'])
        b = cite.format_path(['rules', rule, 'models', 'fit.baseline', 'precision'])
        if citer.has(rid, m) and citer.has(rid, b):
            pvalues = {'precision': citer.num(rid, m, 'pct1'),
                       'base_precision': citer.num(rid, b, 'pct1')}
            conclude = None
            if adopted.get('status') in ('confirmed', 'reconfirm_required'):
                p.keep = g.t('chapters.ch7.keep', rule=lit('decision_value', rh.rule_words(rule)),
                             **pvalues)
    p.evidence.append(c.frame('ch7', 'policy', demote(rh._policy(view, citer), 1), what='table',
                              values=pvalues, conclude=conclude, slot='policy.evaluation',
                              evidence='development', frame_html=line))
    rules = values.get('rules') if isinstance(values.get('rules'), Mapping) else {}
    if rule and isinstance(rules.get(rule), Mapping):
        sub = {'deltas': rules[rule].get('deltas'), 'comparisons': rules[rule].get('comparisons')}
        prefix_values = {'deltas': {k: v for k, v in (sub['deltas'] or {}).items()},
                         'comparisons': {k: v for k, v in (sub['comparisons'] or {}).items()}}
        chart = _rule_paired(c, rid, rule, prefix_values)
        d = cite.format_path(['rules', rule, 'deltas', model, 'precision'])
        dvalues, dconclude = {}, 'none'
        if all(citer.has(rid, f'{d}.{k}') for k in ('point', 'low', 'high')):
            dvalues = {k: citer.num(rid, f'{d}.{x}', 'pts1')
                       for k, x in (('delta', 'point'), ('low', 'low'), ('high', 'high'))}
            dconclude = None
        if chart:
            p.evidence.append(c.frame('ch7', 'paired', chart, values=dvalues,
                                      conclude=dconclude, extra_attention=_tension(c),
                                      frame_html=line))
    for figure in c.charts.get('policy.evaluation', []):
        p.evidence.append(c.frame('ch7', 'selection', figure, frame_html=line))
    if not p.keep:
        p.keep = g.t('chapters.ch7.keep_none')


def _rule_paired(c: Context, rid: str, rule: str, groups: Mapping) -> str:
    """The paired gains of precision at one rule (``rules.<rule>.deltas``), as figure 7.1."""
    values = {'deltas': groups.get('deltas') or {}, 'comparisons': groups.get('comparisons') or {}}
    sub_citer = _RulePrefixCiter(c.citer, rid, rule)
    return render_charts.paired_differences(sub_citer, rid, values, 'precision', 'pts1',
                                            rh.model_short('fit.baseline'),
                                            rh.model_short('fit.logistic'))


class _RulePrefixCiter:
    """A citer whose paths are read under ``rules.<rule>`` (the paired chart of a rule)."""

    def __init__(self, citer: cite.Citer, rid: str, rule: str):
        self.citer, self.rid = citer, rid
        self.prefix = cite.format_path(['rules', rule]) + '.'

    def svg_num(self, rid, path, fmt='auto', **kw):
        return self.citer.svg_num(rid, self.prefix + path, fmt, **kw)

    def value(self, rid, path):
        return self.citer.value(rid, self.prefix + path)


def _versus_frame(c: Context) -> str:
    """Development evidence and final evidence side by side (a row only when both sides
    are cited)."""
    citer, words = c.citer, _words()['versus']
    final_rid = citer.slot_rid('final_test.evaluation')
    dev_slot = 'evaluate.regression' if c.task == 'regression' else 'policy.evaluation'
    dev_rid = citer.slot_rid(dev_slot)
    if not final_rid or not dev_rid:
        return ''
    final = citer.results[final_rid].values
    model = str(final.get('model'))
    rows: list[tuple[str, str, str]] = []

    def row(label, dev_path, final_path, fmt):
        if citer.has(dev_rid, dev_path) and citer.has(final_rid, final_path):
            rows.append((label, citer.num(dev_rid, dev_path, fmt),
                         citer.num(final_rid, final_path, fmt)))

    if c.task == 'regression':
        # R52: the one table is the verdict's (table V); one copy keeps the page in budget.
        return (f'<p class="see-v" data-see="tab-V">{ev.t("see_table")} '
                f'<a href="#tab-V">{e(ev.say("table_v"))}</a>.</p>')
    else:
        rule = final.get('rule_final') or final.get('rule')
        if not rule:
            return ''
        r = ['rules', str(rule)]
        row(words['rows'], 'n', 'n', 'int')
        row(words['base_rate'], cite.format_path(r + ['models', 'fit.baseline', 'precision']),
            cite.format_path(['models', 'fit.baseline', 'precision']), 'pct1')
        row(words['precision'], cite.format_path(r + ['models', model, 'precision']),
            cite.format_path(['models', model, 'precision']), 'pct1')
        row(words['gain'], cite.format_path(r + ['deltas', model, 'precision', 'point']),
            cite.format_path(['deltas', model, 'precision', 'point']), 'pts1')
        row(words['recall'], cite.format_path(r + ['models', model, 'recall']),
            cite.format_path(['models', model, 'recall']), 'pct1')
        row(words['auc'], cite.format_path(['ranking', model, 'roc_auc']),
            cite.format_path(['ranking', model, 'roc_auc']), 'f3')
    if not rows:
        return ''
    body = ''.join(f'<tr><th scope="row">{e(label)}</th><td>{dev}</td><td>{fin}</td></tr>'
                   for label, dev, fin in rows)
    table = (f'<div class="tbl"><table class="versus">'
             f'<thead><tr><th scope="col">{e(words["measure"])}</th>'
             f'<th scope="col">{ev_label("development", True)}</th>'
             f'<th scope="col">{ev_label("final", True)}</th></tr></thead>'
             f'<tbody>{body}</tbody></table></div>')
    return c.frame('ch8', 'versus', table, what='table', slot='final_test.evaluation',
                   evidence='final', frame_html=g.frame_line('final', _frame_rows(c, final_rid)))


def evidence_table_frame(c: Context, cid: str = 'verdict',
                         figure_id: str | None = 'tab-V') -> str:
    """R52: development and final evidence in one table, configuration by configuration (in
    the verdict, "Table V"; the chapters refer to it)."""
    citer, view = c.citer, c.view
    table = ev.regression_table(view, citer)
    if not table:
        return ''
    fin = citer.slot_rid('final_test.evaluation')
    fvalues, conclude = {}, 'sealed'
    if fin:
        fv = citer.results[fin].values
        model = cite.format_path(['models', str(fv.get('model')), 'mae'])
        base = cite.format_path(['models', 'fit.baseline', 'mae'])
        status = ((fv.get('criterion') or {}).get('status')) or 'not_assessed'
        if citer.has(fin, model) and citer.has(fin, base):
            fvalues = {'final': citer.num(fin, model, 'f2'), 'base': citer.num(fin, base, 'f2'),
                       'status': e(ev.say('status_final.' + status))}
            conclude = None
    return c.frame(cid, 'evidence_table', table, what='table', figure_id=figure_id,
                   slot='final_test.evaluation' if fin else 'evaluate.regression',
                   evidence='final' if fin else 'development', values=fvalues,
                   conclude=conclude, attention=None if fin else 'none',
                   frame_html=g.frame_line('final' if fin else 'development',
                                           _frame_rows(c, fin or citer.slot_rid(
                                               'evaluate.regression')),
                                           '' if fin else _scored()))


def _exposure_frame(c: Context) -> str:
    """R53: the exposure ledger as a timeline."""
    view = c.view
    chart = ev.exposure_timeline(view, _slot_label)
    looks = (view.get('eda_looks') or {}).get('target_looks')
    if not chart or not isinstance(looks, int):
        return ''
    opened = (view.get('final_test') or {}).get('status') == 'opened'
    return c.frame('ch8', 'exposure_timeline', chart, stamp_kind='state',
                   values={'looks': _structure(looks)},
                   conclude=None if opened else 'sealed',
                   frame_html=g.frame_line('none', '', '', '', final_note=False))


def _ch8(c: Context, steps, status) -> Parts:
    p, view, citer = Parts(), c.view, c.citer
    p.choice = _choice(_decision_cards(c, steps), _choice_label(c, steps))
    final = view.get('final_test') or {}
    card = _labels()['verdict_card']
    rows = _rows(c)
    if 'final_test' not in view['decisions'] or final.get('status') in (None, 'absent'):
        p.evidence.append(_muted(card['final_absent']))
        p.keep = g.t('chapters.ch8.keep_absent')
        p.uncertain = _limits(view, 'ch8')
        return p
    state = 'opened' if final.get('status') == 'opened' else 'sealed'
    if 'sealed' in rows:
        p.ici['final_test'] = g.t('chapters.ch8.here.final_test', sealed=rows['sealed'],
                                  state=g.t(f'chapters.ch8.state.{state}'))
    facts = g.dl(((e(k), v) for k, v in rh._final_rows(view, citer, c.task)), 'facts')
    rid = citer.slot_rid('final_test.evaluation')
    attention = ''
    if c.task == 'regression' and final.get('method') == 'quantile_stratified':
        attention = f'<p data-drift="unordered">{g.t("chapters.ch8.drift_regression")}</p>'
    fvalues = {'sealed': rows.get('sealed', '')}
    if rid and citer.has(rid, 'n'):
        fvalues['n'] = citer.num(rid, 'n', 'int')
    p.evidence.append(c.frame(
        'ch8', 'final_state', facts, what='table', stamp_kind='state', values=fvalues,
        variant=state,
        conclude='opened' if rid else ('sealed' if state == 'sealed' else 'none'),
        extra_attention=attention, slot='final_test.evaluation' if rid else None,
        evidence='final' if rid else None,
        frame_html=g.frame_line('final' if rid else 'none', rows.get('sealed') and
                                g.rows_words(rows['sealed']) or '')))
    p.evidence.append(_exposure_frame(c))
    if rid:
        p.evidence.append(_versus_frame(c))
        dslot = render_diagnostics.FINAL_SLOT
        model = str(citer.results[rid].values.get('model'))
        wrap = _diag_wrap(c, 'ch8', dslot, 'final', model)
        p.evidence.append(f'<div class="evidence-block ev-final diag-block" '
                          f'data-evidence-class="final" data-for-slot="{e(dslot)}">'
                          f'{demote(render_diagnostics.final_part(view, citer, wrap), 2)}</div>')
        p.keep = g.t('chapters.ch8.keep_opened', n=fvalues.get('n', ''))
    else:
        p.evidence.append(demote(render_diagnostics.final_part(view, citer), 2))
        p.keep = _try('chapters.ch8.keep_sealed', rows) or ''
    p.code_steps = ['final_test']
    p.uncertain = _limits(view, 'ch8')
    return p


def _established(c: Context) -> list[str]:
    """R48: what the study establishes, the numbers carried by charts: the criterion judged on
    the final test and the development and final errors on one scale (regression); the
    criterion row otherwise."""
    view, citer = c.view, c.citer
    fin = citer.slot_rid('final_test.evaluation')
    fallback = [g.dl(((e(k), v) for k, v in rh.criterion_rows(view)), 'facts')]
    if c.task != 'regression':
        return fallback
    if not fin:
        return [f'<p class="established">{ev.t("established_none")}</p>']
    fv = citer.results[fin].values
    model = str(fv.get('model'))
    m = cite.format_path(['models', model, 'mae'])
    b = cite.format_path(['models', 'fit.baseline', 'mae'])
    if not all(citer.has(fin, x) for x in (m, b, 'n', 'criterion.gain', 'criterion.minimum')):
        return fallback
    unit = fv.get('unit')
    unit_html = f' {lit("case", unit)}' if unit else ''
    out = ['<p class="established">' + ev.t(
        'established_regression', n=citer.num(fin, 'n', 'int'),
        model=e(rh.model_phrase(model)), mae=citer.num(fin, m, 'f2') + unit_html,
        base=citer.num(fin, b, 'f2'), gain=citer.num(fin, 'criterion.gain', 'pct1'),
        interval=ev._interval(citer, fin, 'criterion', 'pct1'),
        minimum=citer.num(fin, 'criterion.minimum', 'pct0')) + '</p>']
    chart = ev.criterion_final(view, citer)
    status = (fv.get('criterion') or {}).get('status') or 'not_assessed'
    if chart and citer.has(fin, 'criterion.low') and citer.has(fin, 'criterion.high'):
        out.append(c.frame(
            'ch9', 'criterion_final', chart, slot='final_test.evaluation', evidence='final',
            values={'gain': citer.num(fin, 'criterion.gain', 'pct1'),
                    'low': citer.num(fin, 'criterion.low', 'pct1'),
                    'high': citer.num(fin, 'criterion.high', 'pct1'),
                    'minimum': citer.num(fin, 'criterion.minimum', 'pct0'),
                    'status': e(ev.say('status_final.' + status))},
            frame_html=g.frame_line('final', _frame_rows(c, fin), '',
                                    e(rh.capital(rh.model_name(model))))))
    # R48: the development and final errors on one scale are figure V, under table V.
    out.append(f'<p class="see-v" data-see="fig-V">{ev.t("see_dots")} '
               f'<a href="#fig-V">{e(ev.say("figure_v"))}</a> · '
               f'<a href="#tab-V">{e(ev.say("table_v"))}</a>.</p>')
    return out


def _no_chart(c: Context) -> str:
    """R40/R48: the conclusion's charts the engine cannot draw, said rather than left out."""
    if c.task != 'regression' or not c.citer.slot_rid('final_test.evaluation'):
        return ''
    return (f'<div class="nochart" data-no-chart="final_rows"><p>{e(ev.say("no_chart"))}</p>'
            f'<ul><li data-no-chart="observed_predicted">{e(ev.say("no_chart_observed"))}</li>'
            f'<li data-no-chart="error_by_period">{e(ev.say("no_chart_by_year"))}</li></ul>'
            f'</div>')


def _ch9(c: Context, steps, status) -> Parts:
    p, view = Parts(), c.view
    words = _words()
    p.choice = _choice(_decision_cards(c, steps), _choice_label(c, steps))
    shown = [x for x in view['not_yet_defensible'] if x.get('junior') is not False]
    n = _structure(len(shown))
    # R48: three parts, "what the study establishes", "what it does not establish", "and
    # then", the numbers carried by the charts.
    p.evidence.append(f'<h4 class="concl-part" data-part="established">'
                      f'{e(ev.say("established"))}</h4>')
    p.evidence.extend(_established(c))
    p.evidence.append(f'<h4 class="concl-part" data-part="not_established">'
                      f'{e(ev.say("not_established"))}</h4>')
    p.evidence.append(c.frame('ch9', 'limits', demote(rh._not_yet_defensible(view), 2),
                              what='list', stamp_kind='text', values={'n': n},
                              frame_html=g.frame_line('none')))
    p.evidence.append(_no_chart(c))
    p.evidence.append(f'<h4 class="concl-part" data-part="next">{e(ev.say("next"))}</h4>')
    links = (f'<p>{e(words["conclusion_evidence"])} '
             f'<a href="#verdict">{e(words["chapters"]["verdict"])}</a> · '
             f'<a href="#ch8">{e(words["chapters"]["ch8"]["title"])}</a></p>')
    conclusion = view['decisions'].get('conclusion') or {}
    if conclusion.get('status') == 'confirmed':
        p.evidence.append(f'<p class="next-step">{e(words["next_step"])}</p>' + links)
        p.keep = g.t('chapters.ch9.keep_done', n=n)
    else:
        p.evidence.append(links)
        p.keep = g.t('chapters.ch9.keep_open', n=n)
    p.uncertain = [f'<li><a href="#{c.figure_ids.get("limits", "not-yet-defensible")}">'
                   f'{e(g.say("figures.limits.title"))}</a></li>']
    return p


BUILDERS = {'ch1': _ch1, 'ch2': _ch2, 'ch3': _ch3, 'ch4': _ch4, 'ch5': _ch5, 'ch6': _ch6,
            'ch7': _ch7, 'ch8': _ch8, 'ch9': _ch9}


# --- assembling a chapter -----------------------------------------------------------------------

def _terms(c: Context, cid: str, p: Parts) -> str:
    """The term cards of a chapter: the term first (glossary, or ``terms`` of the lesson
    file), then "In this study" with the study's own values."""
    from . import cmd_explain
    out = []
    holders = cmd_explain.placeholders(c.view)
    for term_id in texts.lesson(f'chapters.{cid}.terms'):
        found = texts.concept(term_id)
        if found:
            term, definition, lang = found
        elif g.has(f'terms.{term_id}'):
            term, definition, lang = (g.say(f'terms.{term_id}.term'),
                                      g.say(f'terms.{term_id}.def'), c.lang)
        else:
            continue
        attr = f' lang="{lang}"' if lang != c.lang else ''
        term = rh.capital(term)
        out.append(f'<p class="terme"{attr}><dfn>{e(term)}</dfn> : {e(definition)}</p>'
                   if c.lang == 'fr' else
                   f'<p class="terme"{attr}><dfn>{e(term)}</dfn>: {e(definition)}</p>')
        ici = p.ici.get(term_id)
        if ici is None:
            ici = _cited_example(c, term_id, holders) or _try(
                f'chapters.{cid}.here.{term_id}', p.values)
        if ici:
            out.append(f'<p class="ici"><span class="ici-k">{e(g.say("ui.in_study"))}</span>'
                       f'{ici}</p>')
    return ''.join(out)


def _cited_example(c: Context, term_id: str, holders: Mapping) -> str | None:
    from . import cmd_explain
    from .errors import StudyError
    entry = texts.glossary(term_id)
    if not entry:
        return None
    template = (entry.get('cited_example_fr') if c.lang == 'fr' else None) \
        or entry.get('cited_example')
    if not template:
        return None
    rule = holders.get('rule')
    template = cmd_explain.fill(template, {**holders, 'rule': '\x00rule\x00'} if rule
                                else holders)
    if template is None or not c.citer.ready(template):
        return None
    mark = len(c.citer.cited)
    try:
        out = c.citer.expand(template)
        if rule:
            # a rule is a recorded decision value, in words (never its raw identifier)
            out = out.replace('\x00rule\x00', lit('decision_value', rh.rule_words(rule)))
        return out
    except StudyError as exc:
        del c.citer.cited[mark:]
        if exc.code == 'untraceable_number':
            return None
        raise


def _fold(cls: str, title: str, body: str, small: str = '', part: str = '') -> str:
    if not body:
        return ''
    data = f' data-part="{part}"' if part else ''
    sub = f' <small>{e(small)}</small>' if small else ''
    return (f'<details class="f {cls}"{data}><summary>{e(title)}{sub}</summary>'
            f'<div class="in">{body}</div></details>')


def _list(items: list[str]) -> str:
    return f'<ul>{"".join(items)}</ul>' if items else ''


def _code(c: Context, p: Parts) -> str:
    cells: list[tuple[str, str]] = []
    for step in p.code_steps:
        cells += list(c.cells.get(step, []))[:2]
    cells += p.code_extra
    if not cells:
        return f'<p>{e(g.say("ui.code_none"))}</p>'
    out = []
    for name, code in cells[:3]:
        lines = code.strip('\n').split('\n')
        cut = len(lines) > MAX_CODE_LINES
        shown = '\n'.join(lines[:MAX_CODE_LINES])
        out.append(f'<p class="origin">{e(g.say("ui.code_origin"))} · '
                   f'{lit("identifier", name, "code")}</p>'
                   # the notebook's code and its comments are written in English
                   f'<pre class="py" data-literal="code" lang="en" translate="no">{e(shown)}'
                   '</pre>'
                   + (f'<p class="small">{e(g.say("ui.code_cut"))}</p>' if cut else ''))
    return ''.join(out)


def _transition(c: Context, cid: str, index: int) -> str:
    opened = (c.view.get('final_test') or {}).get('status') == 'opened'
    done = g.t(f'chapters.{cid}.done_opened' if opened and g.has(f'chapters.{cid}.done_opened')
               else f'chapters.{cid}.done')
    if cid == 'ch9':
        nxt = g.t('ui.next_end')
        return (f'<p class="next"><b>{e(g.say("ui.done"))}</b> {done}'
                f'<span class="arr" aria-hidden="true">→</span>'
                f'<a href="#resume">{nxt}</a></p>')
    following = CHAPTERS[index]
    title = _words()['chapters'][following]['title']
    ref = g.t('ui.chapter_ref', n=g.ordinal(index + 1))
    return (f'<p class="next"><b>{e(g.say("ui.done"))}</b> {done}'
            f'<span class="arr" aria-hidden="true">→</span><b>{e(g.say("ui.next"))}</b>, '
            f'<a href="#{following}">{ref}, {e(title[:1].lower() + title[1:])}</a> : '
            f'{g.t(f"chapters.{cid}.next")}</p>' if c.lang == 'fr' else
            f'<p class="next"><b>{e(g.say("ui.done"))}</b> {done}'
            f'<span class="arr" aria-hidden="true">→</span><b>{e(g.say("ui.next"))}</b>, '
            f'<a href="#{following}">{ref}, {e(title[:1].lower() + title[1:])}</a>: '
            f'{g.t(f"chapters.{cid}.next")}</p>')


def chapter(c: Context, cid: str, index: int) -> dict:
    """One chapter as a lesson: ``{id, title, status, classes, html, keep}``."""
    words = _words()
    steps = c.steps[cid]
    slots = _chapter_slots(c.view, cid, steps)
    status = _status(c.view, cid, steps, slots)
    title = words['chapters'][cid]['title']
    p = BUILDERS[cid](c, steps, status)
    classes = []
    for slot in slots:
        item = c.view['results'].get(slot)
        if item and c.citer.citable(item['result_id']):
            kind = evidence_class(c.view, slot, item)
            if kind not in classes:
                classes.append(kind)
    if cid == 'ch1':
        classes = ['none', 'structural']
    if not classes:
        classes = ['none']
    classes = [k for k in EVIDENCE_CLASSES if k in classes]
    c.status[cid] = status
    c.keeps[cid] = p.keep
    tag_cls = 'ok' if status == 'done' else 'wait'
    tags = (f'<span class="tag {tag_cls} chapter-status {status}" '
            f'data-chapter-status="{status}">{e(g.say("ui.status." + status))}</span>')
    step_titles = ' · '.join(f'« {e(s["title"])} »' if c.lang == 'fr' else
                             f'"{e(s["title"])}"' for s in steps)
    src = g.t('ui.src', n=g.ordinal(index),
              steps=(f'{e(g.say("ui.steps_word" if len(steps) > 1 else "ui.step_word"))} '
                     f'{step_titles}') if steps else '',
              lede=e(words['chapters'][cid]['lede']))
    pending = (f'<p class="notice" data-pending="true">{e(words["pending_chapter"])}</p>'
               if status == 'pending' else '')
    absent = (f'<p class="notice" data-absent="true">{e(words["absent_chapter"])}</p>'
              if status == 'absent' else '')
    example_items = [x for x in (_try_text(t_, p.values) for t_ in
                                 g.items(f'chapters.{cid}.example')) if x]
    why_items = [f'<p>{g.fill(t_)}</p>' for t_ in g.items(f'chapters.{cid}.why')]
    step_texts = ''.join(rh.why_step(c.view, c.citer, s) for s in steps) \
        if status != 'absent' else ''
    why_body = ''.join(why_items) + (
        f'<div class="steps-why"><p class="origin">{e(g.say("ui.fold.step_texts"))}</p>'
        f'{demote(step_texts, 1)}</div>' if step_texts else '')
    breaks = [f'<li>{g.fill(t_)}</li>' for t_ in g.items(f'chapters.{cid}.breaks')] + p.breaks
    uncertain = p.uncertain or [f'<li>{e(words["uncertain_none"])}</li>']
    plus = [(k, v) for k, v in p.plus if k]
    body = [f'<section class="notion chapter" id="{cid}" aria-labelledby="{cid}-t" '
            f'data-status="{status}" style="--ac:var(--{ACCENTS[cid]})">',
            f'<h3 id="{cid}-t"><span class="ch-n" aria-hidden="true">{g.ordinal(index)}</span>'
            f'{e(title)} {tags}</h3>',
            '<div class="evrow">' + ''.join(g.evidence_badge(k) for k in classes) + '</div>',
            f'<p class="src">{src}</p>',
            f'<div class="intro"><span class="intro-k">{e(g.say("ui.at_step"))}</span>'
            f'<p>{g.t(f"chapters.{cid}.intro")}</p></div>',
            pending, absent,
            f'<div class="idee">{_terms(c, cid, p)}</div>',
            f'<div class="part" data-part="choice">{p.choice or _muted(words["choice_none"])}'
            f'</div>',
            f'<div class="part evidence" data-part="evidence">'
            f'{"".join(x for x in p.evidence if x) or _muted(words["pending_chapter"] if status in ("pending", "in_progress") else g.say("ui.no_figure"))}'
            f'</div>',
            _fold('ex', g.say('ui.fold.example'), ''.join(f'<p>{x}</p>' for x in example_items)),
            _fold('preuve', g.say('ui.fold.why'), why_body, part='why'),
            _fold('code', g.say('ui.fold.code'), _code(c, p)),
            _fold('casse', g.say('ui.fold.breaks'), _list(breaks)),
            _fold('incert', g.say('ui.fold.uncertain'), _list(uncertain), part='uncertain'),
            _fold('plus', g.say('ui.fold.more'), g.dl(plus), g.say('ui.fold.more_chapter')),
            (f'<p class="garde"><span class="garde-k">{e(g.say("ui.keep"))}</span>{p.keep}</p>'
             if p.keep else ''),
            _transition(c, cid, index),
            '</section>']
    return {'id': cid, 'title': title, 'status': status, 'classes': classes,
            'html': ''.join(body), 'keep': p.keep}


def chapters(c: Context) -> list[dict]:
    return [chapter(c, cid, index) for index, cid in enumerate(CHAPTERS, start=1)]
