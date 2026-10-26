"""The narrative body of the HTML report (lot L6, remark R8, owner decision D14).

The report reads as an explanation of the study, end to end, in the order it was carried
out: the verdict first, then nine chapters, then the annex, with a table of contents.

1. the question and the data; 2. the framing (prediction moment, availability); 3. how it
   is evaluated (the sealed final test, the split, the success criterion); 4. what the
   exploration showed (the structure first, then the looks at the outcome, counted);
5. the preparation of the variables and the readings that motivated it; 6. the models and
   their comparison (baseline, candidate, diagnostics, variants; the binary model choice);
7. the decision rule (binary) or the model choice (regression); 8. the final test; 9. the
   conclusion and its limits; then the annex (results, plan, case statements, history,
   surfaces).

Each chapter holds four parts, marked ``data-part``: the choice (the decision in the
junior's words with its basis, or the case's statement, or the explorations run), why
(the step texts of ``content/steps.yaml``, the term first), the evidence (each result with
its evidence class: no data read, structural reading, development evidence, or final
evidence, and its chart where the report draws one), and what remains uncertain (the
``not_yet_defensible`` items of the chapter, and in chapter nine all of them). A chapter
whose steps have not run says "not executed yet"; a chapter outside the study's plan says
so.

Navigation: a sticky table of contents on the left (anchors ``ch1`` to ``ch9``,
``verdict``, ``appendix``), folded into a top menu (``<details>``) below 600 px; the page
reads fully without script. An optional script marks the chapter being read
(``aria-current``, with a marker and weight, not colour alone).

Every number is a cited registry value (:mod:`mlkit.study.cite`); every text comes from
``content/report.yaml`` (``narrative``) or ``content/report_fr.yaml``. Pure: no pandas,
numpy, or scikit-learn.
"""
from __future__ import annotations

import html
import re
from typing import Mapping

from . import cite, render_charts, render_diagnostics, render_trials, texts
from . import render_html as rh

e = html.escape
lit = rh.lit

CHAPTERS = ('ch1', 'ch2', 'ch3', 'ch4', 'ch5', 'ch6', 'ch7', 'ch8', 'ch9')
# The chapter of each step of the plan (L5's ``structural_eda`` goes with the exploration).
STEP_CHAPTER = {'discover_data': 'ch1', 'prediction_time': 'ch2',
                'feature_availability': 'ch2', 'split': 'ch3', 'success_criterion': 'ch3',
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


def _labels() -> dict:
    return texts.report()


def _words() -> dict:
    return _labels()['narrative']


_HEADING = re.compile(r'<(/?)h([2-5])\b')


def demote(fragment: str) -> str:
    """A section of the former report placed inside a chapter: its headings one level down
    (the chapter title is the ``h2``)."""
    return _HEADING.sub(lambda m: f'<{m.group(1)}h{int(m.group(2)) + 1}', fragment)


def anchor_id(slot: str) -> str:
    return 'ev-' + re.sub(r'[^A-Za-z0-9_-]+', '-', slot)


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
    if slot == 'policy.evaluation':
        return 'ch7'
    if slot == 'evaluate.regression':
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
        # The study's own plan (L5: a structural-first study's ``structural_eda`` owns
        # ``eda.quality``, which the target exploration then leaves out).
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


# --- the four parts ----------------------------------------------------------------------------

def _part(name: str, body: str, tag: str = 'div') -> str:
    words = _words()['parts']
    icon = '<span aria-hidden="true">?</span> ' if name == 'uncertain' else ''
    cls = 'part uncertain' if name == 'uncertain' else 'part'
    return (f'<{tag} class="{cls}" data-part="{name}"><p class="label">{icon}'
            f'{e(words[name])}</p>{body}</{tag}>')


def _muted(text: str) -> str:
    return f'<p class="muted">{e(text)}</p>'


def _evidence_block(view: Mapping, citer: cite.Citer, slot: str,
                    charts: Mapping[str, list[str]], note: str = '') -> str:
    """One result as evidence: its class in words, a link to its annex entry, its chart
    where the report draws one, and its figures (:func:`render_html._result_block`, which
    says "not executed yet" or "stale" when it cannot be cited)."""
    item = view['results'].get(slot)
    rid = item['result_id'] if item else None
    citable = citer.citable(rid)
    kind = evidence_class(view, slot, item) if citable else 'none'
    head = ''
    if citable:
        link = (f' <a class="rid" href="#r-{e(rid)}">{e(_words()["result_link"])}</a>')
        head = f'<p class="ev-head">{ev_label(kind)}{link}</p>'
    figures = ''.join(charts.get(slot, [])) if citable else ''
    note_html = f'<p class="small">{e(note)}</p>' if note and citable else ''
    state = 'current' if citable else ('stale' if item else 'pending')
    return (f'<div class="evidence-block ev-{kind if citable else state}" id="{anchor_id(slot)}" '
            f'data-evidence-class="{kind if citable else state}" data-for-slot="{e(slot)}">'
            f'{head}{note_html}{figures}{rh._result_block(view, citer, slot)}</div>')


def _section_block(kind: str, body: str, slot: str, rid: str | None) -> str:
    """A whole section of the former report (policy, diagnostics, ...) as one piece of
    evidence, labelled with its class."""
    link = (f' <a class="rid" href="#r-{e(rid)}">{e(_words()["result_link"])}</a>'
            if rid else '')
    return (f'<div class="evidence-block ev-{kind}" id="{anchor_id(slot)}" '
            f'data-evidence-class="{kind}" data-for-slot="{e(slot)}">'
            f'<p class="ev-head">{ev_label(kind)}{link}</p>{demote(body)}</div>')


def _limits(view: Mapping, cid: str) -> list[str]:
    out = []
    for item in view['not_yet_defensible']:
        if item.get('junior') is False or LIMIT_CHAPTER.get(item['id']) != cid:
            continue
        text = item.get('junior_text') or item['text']
        out.append(f'<li data-limit="{e(item["id"])}">{lit("message", text)}</li>')
    return out


def _uncertain(items: list[str]) -> str:
    if not items:
        return _part('uncertain', _muted(_words()['uncertain_none']), 'aside')
    return _part('uncertain', f'<ul>{"".join(items)}</ul>', 'aside')


def _decision_cards(view: Mapping, steps: list[Mapping], variables: list[dict],
                    titles: Mapping, skip: tuple = ()) -> list[str]:
    cards = []
    for step in steps:
        did = step.get('decision')
        if did and did in view['decisions'] and did not in skip:
            cards.append(rh.decision_card(view, did, variables, titles))
    return cards


def _why(view: Mapping, citer: cite.Citer, steps: list[Mapping], status: str) -> str:
    if status == 'absent':
        return _part('why', _muted(_words()['absent_chapter']))
    return _part('why', ''.join(rh.why_step(view, citer, s) for s in steps))


# --- chapters -----------------------------------------------------------------------------------

class Context:
    def __init__(self, view, citer, variables, sample):
        self.view, self.citer = view, citer
        self.variables, self.sample = variables or [], sample
        self.task = view.get('task') or 'binary'
        self.titles = rh._step_titles(view.get('task'))
        self.charts = rh.chart_map(view, citer)
        self.steps = _step_chapter(view)


def _ch1(c: Context, steps, status) -> tuple[str, str, str]:
    view = c.view
    choice = rh._objective(view) or _muted(_words()['case_basis'])
    evidence = (f'<div class="evidence-block ev-none" id="ev-data" data-evidence-class="none">'
                f'<p class="ev-head">{ev_label("none")} {ev_label("structural", True)}</p>'
                f'{demote(rh._data(view, c.citer, c.variables, c.sample))}</div>')
    return choice, evidence, _uncertain(_limits(view, 'ch1'))


def _ch2(c: Context, steps, status):
    view, words = c.view, _words()
    cards = _decision_cards(view, steps, c.variables, c.titles)
    evidence = ''.join(_evidence_block(view, c.citer, s, c.charts, words['signal_note'])
                       for s in _chapter_slots(view, 'ch2', steps))
    items = _limits(view, 'ch2')
    value = (view['decisions'].get('feature_availability') or {}).get('value')
    if isinstance(value, Mapping):
        doubtful = [n for n in sorted(value)
                    if value[n] in ('uncertain_included', 'uncertain_excluded')]
        if doubtful:
            items.append(f'<li data-limit="uncertain_availability">'
                         f'{e(words["uncertain_features"])} '
                         + ', '.join(f'{lit("identifier", n, "code")} '
                                     f'({e(_labels()["availability"][value[n]].lower())})'
                                     for n in doubtful) + '</li>')
    return ''.join(cards), evidence or _muted(words['pending_chapter']), _uncertain(items)


def _sealing(view: Mapping) -> str:
    """The final test sealed at ``init``: an automatic choice, from the case."""
    final = view.get('final_test') or {}
    if final.get('status') in (None, 'absent'):
        return ''
    labels = _labels()
    ds, words = labels['data_section'], _words()
    rows = (cite.format_value(final['rows'], 'int', view.get('language') or 'en')
            if isinstance(final.get('rows'), int) else '')
    key = 'final_test_sealed' if final.get('status') == 'sealed' else 'final_test_opened'
    return (f'<div class="choice auto" data-choice="final_test_sealing">'
            f'<p class="choice-value">{lit("structure", rows)} {e(ds[key])}</p>'
            f'<p class="basis"><span class="chip auto">{e(words["sealing_basis"])}</span> '
            f'{e(words["sealing_note"])}</p></div>')


def _ch3(c: Context, steps, status):
    view = c.view
    choice = _sealing(view) + ''.join(_decision_cards(view, steps, c.variables, c.titles))
    evidence = ''.join(_evidence_block(view, c.citer, s, c.charts)
                       for s in _chapter_slots(view, 'ch3', steps))
    return (choice or _muted(_words()['choice_none']),
            evidence or _muted(_words()['pending_chapter']), _uncertain(_limits(view, 'ch3')))


# The order of the explorations in chapter four (mockup D14): quality, distributions and
# associations first; then the target, its special values, and the rates or means by group.
EXPLORATION_ORDER = ('eda.quality', 'eda.distribution', 'eda.correlation', 'eda.target_rate',
                     'eda.target_summary', 'eda.special_values', 'eda.rate_by', 'eda.mean_by')


def _exploration_order(slot: str) -> tuple:
    base = slot.partition(':')[0]
    rank = EXPLORATION_ORDER.index(base) if base in EXPLORATION_ORDER else len(EXPLORATION_ORDER)
    return rank, slot


def _slot_label(slot: str) -> str:
    return (texts.activity(slot).get('label')
            or _labels().get('slot_labels', {}).get(slot, slot))


def _ch4(c: Context, steps, status):
    view, words = c.view, _words()
    slots = sorted(_chapter_slots(view, 'ch4', steps), key=_exploration_order)
    structural = [s for s in slots if view['results'].get(s) and
                  evidence_class(view, s, view['results'][s]) == 'structural']
    looks = [s for s in slots if s not in structural]
    run = [s for s in slots if s in view['results']]
    if run:
        items = ''.join(
            f'<li><a href="#{anchor_id(s)}">'
            f'{e(_slot_label(s))}'
            f'</a> {ev_label(evidence_class(view, s, view["results"][s]), True)}</li>'
            for s in structural + [x for x in looks if x in view['results']])
        choice = f'<p>{e(words["exploration_choice"])}</p><ul class="explored">{items}</ul>'
    else:
        choice = _muted(words['exploration_none'])
    parts = []
    if structural:
        parts.append(f'<h3>{e(words["structural_heading"])}</h3>'
                     f'<p class="small">{e(words["structural_note"])}</p>')
        parts += [_evidence_block(view, c.citer, s, c.charts) for s in structural]
    if looks:
        parts.append(f'<h3>{e(words["target_heading"])}</h3>')
        parts.append(rh._concept('target_look') if texts.glossary('target_look') else '')
        parts += [_evidence_block(view, c.citer, s, c.charts) for s in looks]
    parts.append(rh._looks(view))
    items = _limits(view, 'ch4')
    count = (view.get('eda_looks') or {}).get('target_looks')
    if isinstance(count, int) and count:
        items.insert(0, f'<li data-limit="target_looks">{e(words["looks_limit"])} '
                        f'({lit("structure", count)} {e(words["looks_count"])})</li>')
    return choice, ''.join(parts), _uncertain(items)


def _ch5(c: Context, steps, status):
    view, words = c.view, _words()
    cards = _decision_cards(view, steps, c.variables, c.titles)
    value = (view['decisions'].get('preprocessing') or {}).get('value')
    links = []
    by_rid = {item.get('result_id'): slot for slot, item in view['results'].items()}
    for rid in (value.get('motivated_by') or []) if isinstance(value, Mapping) else []:
        slot = by_rid.get(rid)
        if slot and c.citer.citable(rid):
            label = _slot_label(slot)
            links.append(f'<li data-motivated-by="{e(rid)}"><a href="#{anchor_id(slot)}">'
                         f'{e(label)}</a> '
                         f'{ev_label(evidence_class(view, slot, view["results"][slot]), True)}'
                         f'</li>')
    if links:
        evidence = (f'<p>{e(words["motivation_heading"])}</p>'
                    f'<ul class="motivation">{"".join(links)}</ul>')
    elif status == 'absent':
        evidence = _muted(words['absent_chapter'])
    else:
        evidence = _muted(words['motivation_none'])
    return (''.join(cards) or _muted(words['choice_none']), evidence,
            _uncertain(_limits(view, 'ch5')))


def _nonlinear_charts(c: Context) -> str:
    """L6: the gap between the observed outcome and the mean prediction by range of each
    flagged feature (``linear_checks`` of the development diagnostics, recorded values)."""
    slot = render_diagnostics.DEVELOPMENT_SLOTS[c.task]
    rid = c.citer.slot_rid(slot)
    if rid is None:
        return ''
    checks = (c.citer.results[rid].values.get('linear_checks') or {})
    out = []
    for i, check in enumerate(checks.get('nonlinearity') or []):
        if isinstance(check, Mapping) and check.get('flagged') \
                and len(out) < MAX_NONLINEAR_CHARTS:
            out.append(render_charts.nonlinearity(c.citer, rid, i, check,
                                                  _words()['charts'],
                                                  binary=c.task != 'regression'))
    return ''.join(f for f in out if f)


def _fold_chart(c: Context) -> str:
    slot = 'evaluate.regression' if c.task == 'regression' else 'policy.evaluation'
    rid = c.citer.slot_rid(slot)
    values = c.citer.results[rid].values if rid else None
    sel = values.get('model_selection') if isinstance(values, Mapping) else None
    if not isinstance(sel, Mapping) or not sel.get('available'):
        return ''
    lang = c.view.get('language') if c.view.get('language') in render_trials.LABELS else 'en'
    lab = render_trials.LABELS[lang]
    names = [render_trials._name(conf.get('slot'), conf.get('words'), lab)
             for conf in sel.get('configurations') or [] if isinstance(conf, Mapping)]
    chart = render_charts.fold_scores(c.citer, rid, sel, names, _words()['charts'])
    if not chart:
        return ''
    return (f'<div class="evidence-block ev-development" id="ev-fold-scores" '
            f'data-evidence-class="development" data-for-chart="fold_scores">'
            f'<p class="ev-head">{ev_label("development")} <a class="rid" href="#r-{e(rid)}">'
            f'{e(_words()["result_link"])}</a></p>{chart}</div>')


def _ch6(c: Context, steps, status):
    view = c.view
    skip = () if c.task != 'regression' else ('model_choice',)
    cards = _decision_cards(view, steps, c.variables, c.titles, skip)
    slots = [s for s in _chapter_slots(view, 'ch6', steps) if s not in SECTION_SLOTS]
    parts = [_evidence_block(view, c.citer, s, c.charts) for s in slots]
    diag_slot = render_diagnostics.DEVELOPMENT_SLOTS[c.task]
    diag_rid = c.citer.slot_rid(diag_slot)
    diagnostics = render_diagnostics.section(view, c.citer, final=False)
    nonlinear = _nonlinear_charts(c) if diag_rid else ''
    if diag_rid:
        parts.append(_section_block('development', nonlinear + diagnostics, diag_slot,
                                    diag_rid))
    elif status != 'pending':
        parts.append(demote(diagnostics))
    trials = render_trials.section(view, c.citer)
    if trials:
        parts.append(_fold_chart(c))
        parts.append(demote(trials))
    return (''.join(cards) or _muted(_words()['choice_none']), ''.join(parts),
            _uncertain(_limits(view, 'ch6')))


def _ch7(c: Context, steps, status):
    view = c.view
    cards = _decision_cards(view, steps, c.variables, c.titles)
    slot = 'evaluate.regression' if c.task == 'regression' else 'policy.evaluation'
    rid = c.citer.slot_rid(slot)
    if rid:
        body = (rh._model_comparison(view, c.citer) if c.task == 'regression'
                else rh._policy(view, c.citer))
        figures = ''.join(c.charts.get(slot, []))
        evidence = _section_block('development', figures + body, slot, rid)
    elif status == 'absent':
        evidence = _muted(_words()['absent_chapter'])
    else:
        evidence = _evidence_block(view, c.citer, slot, c.charts)
    return (''.join(cards) or _muted(_words()['choice_none']), evidence,
            _uncertain(_limits(view, 'ch7')))


def _versus(c: Context) -> str:
    """Development evidence and final evidence side by side, at the rule of the final test
    (binary) or for the chosen model (regression); a row only when both sides are cited."""
    citer, words = c.citer, _words()['versus']
    final_rid = citer.slot_rid('final_test.evaluation')
    dev_slot = 'evaluate.regression' if c.task == 'regression' else 'policy.evaluation'
    dev_rid = citer.slot_rid(dev_slot)
    if not final_rid or not dev_rid:
        return ''
    final = citer.results[final_rid].values
    model = str(final.get('model'))
    rows: list[tuple[str, str, str, str]] = []

    def row(label, dev_path, final_path, fmt):
        if citer.has(dev_rid, dev_path) and citer.has(final_rid, final_path):
            rows.append((label, citer.num(dev_rid, dev_path, fmt),
                         citer.num(final_rid, final_path, fmt), dev_path))

    if c.task == 'regression':
        row(words['rows'], 'n', 'n', 'int')
        row(words['mae'], cite.format_path(['models', model, 'mae']),
            cite.format_path(['models', model, 'mae']), 'f2')
        row(words['mae_baseline'], cite.format_path(['models', 'fit.baseline', 'mae']),
            cite.format_path(['models', 'fit.baseline', 'mae']), 'f2')
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
                   for label, dev, fin, _ in rows)
    return (f'<h3>{e(words["heading"])}</h3><div class="scroll"><table class="versus">'
            f'<thead><tr><th scope="col">{e(words["measure"])}</th>'
            f'<th scope="col">{ev_label("development", True)}</th>'
            f'<th scope="col">{ev_label("final", True)}</th></tr></thead>'
            f'<tbody>{body}</tbody></table></div>')


def _ch8(c: Context, steps, status):
    view, words = c.view, _words()
    cards = _decision_cards(view, steps, c.variables, c.titles)
    final = view.get('final_test') or {}
    card = _labels()['verdict_card']
    if 'final_test' not in view['decisions'] or final.get('status') in (None, 'absent'):
        return (_muted(card['final_absent']), _muted(card['final_absent']),
                _uncertain(_limits(view, 'ch8')))
    rows = rh._final_rows(view, c.citer, c.task)
    facts = ('<dl class="facts">' + ''.join(f'<dt>{e(k)}</dt><dd>{v}</dd>' for k, v in rows)
             + '</dl>')
    rid = c.citer.slot_rid('final_test.evaluation')
    if rid:
        body = facts + _versus(c) + render_diagnostics.final_part(view, c.citer)
        evidence = _section_block('final', body, 'final_test.evaluation', rid)
    else:
        evidence = facts + demote(render_diagnostics.final_part(view, c.citer))
    return (''.join(cards) or _muted(words['choice_none']), evidence,
            _uncertain(_limits(view, 'ch8')))


def _ch9(c: Context, steps, status):
    view, words = c.view, _words()
    cards = _decision_cards(view, steps, c.variables, c.titles)
    criterion = rh.criterion_rows(view)
    facts = ('<dl class="facts">' + ''.join(f'<dt>{e(k)}</dt><dd>{v}</dd>'
                                            for k, v in criterion) + '</dl>') if criterion else ''
    evidence = (f'{facts}<p>{e(words["conclusion_evidence"])} '
                f'<a href="#verdict">{e(words["chapters"]["verdict"])}</a> · '
                f'<a href="#ch8">{e(words["chapters"]["ch8"]["title"])}</a></p>')
    conclusion = view['decisions'].get('conclusion') or {}
    if conclusion.get('status') == 'confirmed':
        evidence += f'<p class="next">{e(words["next_step"])}</p>'
    uncertain = _part('uncertain', demote(rh._not_yet_defensible(view)), 'aside')
    return ''.join(cards) or _muted(words['choice_none']), evidence, uncertain


BUILDERS = {'ch1': _ch1, 'ch2': _ch2, 'ch3': _ch3, 'ch4': _ch4, 'ch5': _ch5, 'ch6': _ch6,
            'ch7': _ch7, 'ch8': _ch8, 'ch9': _ch9}


def _chapter(c: Context, cid: str, index: int) -> tuple[str, str, str]:
    """``(html, title, status)`` of one chapter."""
    words = _words()
    steps = c.steps[cid]
    slots = _chapter_slots(c.view, cid, steps)
    status = _status(c.view, cid, steps, slots)
    title = words['chapters'][cid]['title']
    choice, evidence, uncertain = BUILDERS[cid](c, steps, status)
    classes = []
    for slot in slots:
        item = c.view['results'].get(slot)
        if item and c.citer.citable(item['result_id']):
            kind = evidence_class(c.view, slot, item)
            if kind not in classes:
                classes.append(kind)
    if not classes:
        classes = ['none']
    tags = (f'<span class="badge chapter-status {status}" data-chapter-status="{status}">'
            f'<span aria-hidden="true">{STATUS_GLYPHS[status]}</span> '
            f'{e(words["chapter_status"][status])}</span> '
            + ' '.join(ev_label(k, True) for k in EVIDENCE_CLASSES if k in classes))
    pending = (f'<p class="notice" data-pending="true">{e(words["pending_chapter"])}</p>'
               if status == 'pending' else '')
    body = (f'<section class="card chapter" id="{cid}" aria-labelledby="{cid}-t" '
            f'data-status="{status}">'
            f'<div class="ch-head"><span class="ch-num">{lit("ordinal", index)}</span><div>'
            f'<h2 id="{cid}-t">{e(title)}</h2><p class="ch-tags">{tags}</p></div></div>'
            f'<p class="lede">{e(words["chapters"][cid]["lede"])}</p>{pending}'
            f'{_part("choice", choice)}{_why(c.view, c.citer, steps, status)}'
            f'{_part("evidence", evidence)}{uncertain}</section>')
    return body, title, status


# --- table of contents, appendix, page ---------------------------------------------------------

def _toc_list(entries: list[tuple[str, str, str, str | None]]) -> str:
    words = _words()
    items = []
    for target, number, title, status in entries:
        mark = ''
        if status:
            mark = (f'<span class="toc-st" aria-hidden="true" title="'
                    f'{e(words["chapter_status"][status])}">{STATUS_GLYPHS[status]}</span>'
                    f'<span class="sr">{e(words["chapter_status"][status])}</span>')
        items.append(f'<li><a href="#{target}"><span class="toc-n">{number}</span>'
                     f'<span class="toc-t">{e(title)}</span>{mark}</a></li>')
    return f'<ol class="toc-list">{"".join(items)}</ol>'


def toc(entries) -> tuple[str, str]:
    """``(top menu, side table of contents)``: the same anchors; the menu shows below
    600 px, the side table above."""
    words = _words()
    listing = _toc_list(entries)
    mobile = (f'<details class="toc-mobile"><summary>{e(words["contents"])}</summary>'
              f'<nav aria-label="{e(words["contents"])}">{listing}</nav></details>')
    side = (f'<nav class="toc" aria-label="{e(words["contents"])}">'
            f'<p class="label">{e(words["contents"])}</p>{listing}'
            f'<p class="toc-legend">'
            + ' · '.join(f'<span class="ev-{k}"><span aria-hidden="true">{GLYPHS[k]}</span> '
                         f'{e(words["evidence_short"][k])}</span>' for k in EVIDENCE_CLASSES)
            + '</p></nav>')
    return mobile, side


def _howto(view: Mapping) -> str:
    words = _words()
    na = view['next_action']
    legend = ' '.join(ev_label(k) for k in EVIDENCE_CLASSES)
    return (f'<section class="howto" id="howto" aria-label="{e(words["howto_label"])}">'
            f'<p>{e(words["howto"])}</p>'
            f'<p class="small">{e(words["legend"])}</p><p class="ev-legend">{legend}</p>'
            f'<p><strong>{e(words["where"])}</strong> '
            f'{lit("message", na.get("junior_message") or na.get("message", ""))}</p></section>')


def _appendix(view: Mapping, citer: cite.Citer, surfaces: Mapping) -> str:
    words = _words()
    annex = words['annex']
    extras = [('plan', annex['plan'], rh._plan(view)), ('facts', annex['facts'], rh._facts(view)),
              ('history', annex['history'], rh._history(view)),
              ('revision', annex['revision'], rh._surfaces(view, surfaces))]
    more = ''.join(f'<details class="annex-part" data-annex="{key}"><summary>{e(title)}'
                   f'</summary>{demote(body)}</details>' for key, title, body in extras if body)
    return (f'<section class="card chapter appendix" id="appendix" aria-labelledby="appendix-t">'
            f'<div class="ch-head"><span class="ch-num">A</span><div>'
            f'<h2 id="appendix-t">{e(words["chapters"]["annex"])}</h2>'
            f'<p class="ch-tags">{e(annex["intro"])}</p></div></div>'
            f'{rh._annex(view, citer)}{more}</section>')


def body(view: Mapping, citer: cite.Citer, *, surfaces: Mapping, variables: list[dict],
         sample: Mapping | None, understanding: str) -> tuple[str, str, str]:
    """``(top menu, side table of contents, main content)`` of the report."""
    words = _words()
    c = Context(view, citer, variables, sample)
    sections = [rh._verdict(view, citer), _howto(view)]
    entries: list[tuple[str, str, str, str | None]] = [
        ('verdict', '', words['chapters']['verdict'], None)]
    for index, cid in enumerate(CHAPTERS, start=1):
        html_, title, status = _chapter(c, cid, index)
        sections.append(html_)
        entries.append((cid, lit('ordinal', index), title, status))
    if understanding:
        sections.append(understanding)
        entries.append(('understanding', '·', words['chapters']['understanding'], None))
    sections.append(_appendix(view, citer, surfaces))      # last: the annex reads citations
    entries.append(('appendix', 'A', words['chapters']['annex'], None))
    mobile, side = toc(entries)
    return mobile, side, ''.join(sections)


CSS = '''
body.report{--struct:#2f6f6a;--struct-soft:#e3f2f0;--none:#68758b;--none-soft:#eef0f4;--ok:#1f6f43;--ok-soft:#e2f4e9;--toc-w:244px}
body.report.dark{--struct:#8fd6cc;--struct-soft:#1f3a3a;--none:#a4b1c9;--none-soft:#26304a;--ok:#8fdcae;--ok-soft:#1d3a2b}
@media (prefers-color-scheme:dark){body.report:not(.light){color-scheme:dark;--bg:#111827;--paper:#1b2538;--ink:#e6ecf9;--muted:#a4b1c9;--line:#334059;--accent:#a3b1ff;--green:#a3b1ff;--soft:#28334f;--shade:#373024;--amber:#f1d394;--shadow:0 8px 28px #0001;--struct:#8fd6cc;--struct-soft:#1f3a3a;--none:#a4b1c9;--none-soft:#26304a;--ok:#8fdcae;--ok-soft:#1d3a2b}}
html{scroll-behavior:smooth;scroll-padding-top:16px}
.report header{flex-wrap:wrap}
.report .skip{position:absolute;left:-9999px}.report .skip:focus{left:16px;top:8px;z-index:20;background:var(--paper);padding:6px 10px;border-radius:6px}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.layout{display:grid;grid-template-columns:var(--toc-w) minmax(0,1fr);gap:36px;max-width:1300px;margin:0 auto;padding:0 28px}
.report .layout>main{max-width:none!important;margin:0!important;padding:28px 0 64px!important;min-width:0}
.toc{position:sticky;top:0;align-self:start;max-height:100vh;overflow-y:auto;padding:28px 14px 28px 0;border-right:1px solid var(--line)}
.toc .label{margin:0 0 8px}
.toc-list{list-style:none;margin:0;padding:0}
.toc-list a{display:grid;grid-template-columns:22px minmax(0,1fr) 16px;gap:6px;align-items:baseline;padding:7px 8px;border-radius:8px;color:var(--muted);text-decoration:none;font-size:13.5px;line-height:1.35;border-left:3px solid transparent}
.toc-list a:hover{background:var(--soft);color:var(--ink)}
.toc-list a[aria-current="true"]{background:var(--soft);color:var(--ink);font-weight:700;border-left-color:var(--ink)}
.toc-list a[aria-current="true"] .toc-t:before{content:"▸ "}
.toc-n{font-variant-numeric:tabular-nums;font-weight:700;color:var(--muted);white-space:nowrap}
.toc-st{font-size:12px;text-align:center}
.toc-legend{font-size:11.5px;color:var(--muted);margin-top:16px;line-height:1.7}
.toc-mobile{display:none}
.ev{display:inline-flex;gap:5px;align-items:baseline;font-size:11.5px;font-weight:650;border-radius:6px;padding:2px 8px;line-height:1.4;margin:0 4px 2px 0}
.ev-none{color:var(--none)}.ev.ev-none{background:var(--none-soft)}
.ev-structural{color:var(--struct)}.ev.ev-structural{background:var(--struct-soft)}
.ev-development{color:var(--accent)}.ev.ev-development{background:var(--soft)}
.ev-final{color:var(--amber)}.ev.ev-final{background:var(--shade)}
.ev-legend{display:flex;flex-wrap:wrap;gap:6px}
.report .verdict .next a{font-weight:650}
.howto{margin:22px 0 8px;padding:14px 18px;border:1px dashed var(--line);border-radius:12px;font-size:14px}
.howto p{margin:6px 0;color:var(--ink)}
section.card.chapter{padding:26px 28px;margin:26px 0}
.ch-head{display:flex;gap:16px;align-items:flex-start;margin-bottom:4px}
.ch-head h2{margin:0!important;font-size:23px!important;line-height:1.25}
.ch-num{flex:none;width:40px;height:40px;border-radius:10px;background:var(--soft);color:var(--accent);display:grid;place-items:center;font-weight:800;font-size:18px}
.ch-tags{margin:6px 0 0;display:flex;flex-wrap:wrap;gap:4px;align-items:center;font-size:13px;color:var(--muted)}
.badge.chapter-status.done{border-color:var(--ok);color:var(--ok);background:var(--ok-soft)}
.badge.chapter-status.pending,.badge.chapter-status.absent{border-style:dashed;color:var(--none);background:var(--none-soft)}
.badge.chapter-status.in_progress{border-style:dashed;border-color:var(--amber);color:var(--amber)}
.lede{font-size:16.5px;line-height:1.6;color:var(--ink);border-left:3px solid var(--line);padding-left:14px;margin:14px 0 16px}
.part{margin:18px 0 0}
.part>.label{margin:0 0 6px;color:var(--ink)}
.chapter article.decision{background:var(--soft);border:1px solid var(--line);border-left:3px solid var(--accent);box-shadow:none;border-radius:12px;padding:14px 18px;margin:10px 0}
.chapter article.decision h3,.chapter article.decision h4{margin:0 0 6px}
.chapter article.decision p{color:var(--ink)}
.choice-value{font-weight:650;color:var(--ink)}
.choice.auto,.choice.case{background:var(--none-soft);border:1px solid var(--line);border-radius:12px;padding:12px 16px;margin:10px 0}
.chip.auto,.chip.case{border-style:dashed}
.basis{font-size:13px;color:var(--muted);margin:6px 0 0}
.why-step{margin:8px 0 14px}
.why-step h3,.why-step h4{font-size:15px;margin:10px 0 4px}
.chapter section.card,.chapter .evidence-block section.card{border:0;box-shadow:none;padding:0;margin:12px 0;background:none}
.chapter section.card>h3:first-child{margin-top:4px!important}
.evidence-block{margin:14px 0 18px;padding:12px 16px;border:1px solid var(--line);border-left:4px solid var(--line);border-radius:12px;min-width:0}
.evidence-block.ev-structural{border-left-color:var(--struct)}.evidence-block.ev-development{border-left-color:var(--accent)}.evidence-block.ev-final{border-left-color:var(--amber)}
.evidence-block.ev-pending,.evidence-block.ev-stale{border-left-style:dashed}
.ev-head{margin:0 0 6px;display:flex;flex-wrap:wrap;gap:4px 10px;align-items:baseline}
a.rid{font-size:12px;color:var(--muted)}
.chapter figure{margin:12px 0 18px;padding:0;max-width:740px}
.chapter .chart-frame{max-width:740px;padding-right:60px}
.chapter figcaption{font-size:13px;color:var(--muted);margin:0 0 8px}
.chapter figcaption strong{color:var(--ink)}
.legend{flex-wrap:wrap}
.legend span.ci:before{height:0;border-radius:0;background:none;border-top:2px solid var(--ink);vertical-align:3px}
svg.chart circle.pt.m{fill:var(--accent);opacity:.85}
.part.uncertain{padding:12px 16px;border-radius:12px;background:var(--shade);border:1px solid var(--line)}
.part.uncertain>.label{color:var(--amber)}
.part.uncertain ul{margin:4px 0 0;padding-left:20px}
.part.uncertain li{margin:4px 0;color:var(--ink)}
.part.uncertain section.card{margin:0}
table.versus th[scope=row]{text-align:left;font-weight:600;color:var(--ink);background:none;font-size:13px;letter-spacing:0}
.appendix details{margin:12px 0}
.appendix details.annex>summary{font-size:16px}
@media (max-width:900px){.layout{grid-template-columns:196px minmax(0,1fr);gap:22px;padding:0 18px}}
@media (max-width:600px){
  html{scroll-padding-top:56px}
  .layout{display:block;padding:0 16px}
  .toc{display:none}
  .toc-mobile{display:block;position:sticky;top:0;z-index:10;background:var(--paper);border:0;border-bottom:1px solid var(--line);border-radius:0;margin:0;padding:0 16px}
  .toc-mobile summary{padding:12px 0;list-style:none;font-size:14px}
  .toc-mobile summary::-webkit-details-marker{display:none}
  .toc-mobile summary:before{content:"☰ "}
  .toc-mobile[open] summary:before{content:"✕ "}
  .toc-mobile nav{max-height:70vh;overflow-y:auto;padding-bottom:10px}
  .report header{padding:12px 16px!important}
  section.card.chapter,.report .verdict{padding:18px 16px}
  .ch-num{width:32px;height:32px;font-size:15px}
  .ch-head h2{font-size:19px!important}
  .evidence-block{padding:10px 12px}
}
@media print{.toc,.toc-mobile,[data-theme-toggle]{display:none}.layout{display:block}.chapter{break-inside:auto;box-shadow:none}}
'''

# Optional: marks the chapter being read in the table of contents and closes the top menu
# after a choice. The page reads fully without it.
SCRIPT = '''(function(){if(!("IntersectionObserver" in window)){return;}
var links=[].slice.call(document.querySelectorAll(".toc-list a"));var seen={};
var ids=[];links.forEach(function(a){var id=a.getAttribute("href").slice(1);if(ids.indexOf(id)<0){ids.push(id);}});
function mark(id){links.forEach(function(a){if(a.getAttribute("href")==="#"+id){a.setAttribute("aria-current","true");}else{a.removeAttribute("aria-current");}});}
var io=new IntersectionObserver(function(es){es.forEach(function(x){seen[x.target.id]=x.isIntersecting;});
for(var i=0;i<ids.length;i++){if(seen[ids[i]]){mark(ids[i]);return;}}},{rootMargin:"0px 0px -70% 0px"});
ids.forEach(function(id){var n=document.getElementById(id);if(n){io.observe(n);}});
var menu=document.querySelector(".toc-mobile");if(menu){menu.addEventListener("click",function(ev){if(ev.target.closest&&ev.target.closest("a")){menu.removeAttribute("open");}});}})();'''

