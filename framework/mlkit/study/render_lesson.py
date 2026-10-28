"""The lesson-style HTML report: its shell, both languages, and the charter (owner decision
2026-10-27, remarks R25 to R30; ``render_html.TEMPLATE_VERSION`` 4).

The page follows the "tableau noir" charter: a slate board carries the text in chalk; graph
paper frames hold the figures and their guided readings; index cards hold the term cards, the
choices and the folds. The dark board is the default theme (R28); the "Whiteboard" button
switches it for the visit, without storage and without reading the system preference.

**Both languages in one file (R27).** The page holds two editions, written by the same
renderers with the report language set to each language in turn: the study language first,
then the other one, written from the study read in that language (``twin``, built by
:mod:`mlkit.study.cmd_render`; derived from the view when not given). Without script, the
study language's edition alone is shown. The "EN"/"FR" button switches editions for the visit,
keeping the reader's place. The ``id`` of every element of the second edition carries the
suffix ``--<language>``, so every anchor of the first edition (``#ch1``, ``#r-<result id>``)
keeps its target. Words recorded in the study language (the junior's words, restatements,
decision values written as text) appear as recorded in the other edition, marked with their
language (``(fr)``, ``(en)``).

**The edition** (R29, R30): a position line pinned at the top ("Chapter n/9 · title —
remaining: ... · N decisions to review"), a header, a sticky table of contents with each
chapter's status (folded below 1040 px), "How to read this report" with "Learn more" (every
mark, stamp and abbreviation), the verdict with figure V, the nine chapters
(:mod:`mlkit.study.render_narrative`), the summary, "Say it out loud", the decisions to review
(automatic mode), and the appendix.

No URL is loaded, no storage is used, no number is written outside a cited ``<data>`` element
or a recorded literal (``hypotrail check``). Pure: no pandas, numpy, or scikit-learn.
"""
from __future__ import annotations

import copy
import html
import json
import re
from typing import Mapping

from . import audience, cite, render_charts, render_guide as g, texts
from . import render_evidence as ev
from . import render_html as rh
from . import render_narrative as rn

e = html.escape
LANGUAGES = ('en', 'fr')


# --- the twin view and the editions ---------------------------------------------------------

def _inverse_steps() -> dict[str, str]:
    from . import junior
    if junior._STEPS_FR is None:
        junior.step_text('', 'fr')
    return {fr: en for en, fr in (junior._STEPS_FR or {}).items()}


def _step_in(text: str, language: str) -> str:
    from . import junior
    if language == 'fr':
        return junior.step_text(text, 'fr')
    return _inverse_steps().get(text, text)


def derive_twin(view: Mapping, language: str) -> dict:
    """The view read in ``language`` when the study itself is not at hand (a view built in
    a test): the plan's titles and questions and the limits' texts in that language; the
    rest as recorded."""
    twin = copy.copy(dict(view))
    twin['language'] = language
    twin['plan'] = [{**s, 'title': _step_in(s.get('title') or '', language),
                     'question': _step_in(s.get('question') or '', language)}
                    for s in view['plan']]
    twin['not_yet_defensible'] = [
        audience.limit({k: v for k, v in item.items() if k != 'junior_text'}, language)
        if isinstance(item, Mapping) and item.get('text') else item
        for item in view['not_yet_defensible']]
    twin['_derived'] = True
    return twin


def _mark_labels(primary: Mapping, twin: Mapping, study: str) -> dict:
    """The twin with ``label_language`` on each confirmation and open proposal whose
    restatement is the study language's (the agent gave none in the twin's language)."""
    twin = dict(twin)
    decisions = {}
    for did, d in (twin.get('decisions') or {}).items():
        conf = (d or {}).get('confirmation')
        mine = ((primary.get('decisions') or {}).get(did) or {}).get('confirmation') or {}
        if isinstance(conf, Mapping) and (twin.get('_derived') or
                                          conf.get('label') == mine.get('label')):
            d = {**d, 'confirmation': {**conf, 'label_language': study}}
        decisions[did] = d
    twin['decisions'] = decisions
    mine = {p['proposal_id']: p for p in primary.get('open_proposals') or []}
    twin['open_proposals'] = [
        {**p, 'label_language': study}
        if twin.get('_derived') or p.get('label') == (mine.get(p['proposal_id']) or {}).get('label')
        else p for p in twin.get('open_proposals') or []]
    return twin


def model_names(view: Mapping, language: str) -> dict[str, str]:
    """The display names of the variants (R26: by their family)."""
    from . import trials
    out = {}
    if view.get('task') == 'regression':
        # R45, R48: the reference is "reference (predict the mean)", never "training mean".
        out['fit.baseline'] = texts.say(texts.lesson('models.baseline_regression'), language)
        out['phrase:fit.baseline'] = texts.say(
            texts.lesson('models.baseline_regression_phrase'), language)
    for slot, item in (view.get('results') or {}).items():
        if not slot.startswith('fit.variant') or not isinstance(item.get('values'), Mapping):
            continue
        variant = item['values'].get('variant')
        if not isinstance(variant, Mapping):
            continue
        family, kind = variant.get('family'), variant.get('kind')
        if family in ('ebm', 'hgb'):
            key = family
        elif kind == 'tuned':
            key = 'tuned' if view.get('task') == 'regression' else 'tuned_binary'
        else:
            key = None
        out['short:' + slot] = texts.say(texts.lesson(
            f'models_short.{key or "other"}'), language)
        if key:
            out[slot] = texts.say(texts.lesson(f'models.{key}'), language)
        else:
            words = trials.variant_words(variant, language)
            out[slot] = g.fill(texts.say(texts.lesson('models.other'), language),
                               {'words': e(words)})
    return out


_ID = re.compile(r'(?<![\w-])id="([^"]+)"')


def suffix_ids(fragment: str, language: str) -> str:
    """Every ``id`` of ``fragment`` and the internal references to it, with ``--<language>``
    (the second edition of the page)."""
    ids = set(_ID.findall(fragment))
    if not ids:
        return fragment

    def ref(m: re.Match) -> str:
        value = m.group(3)
        return f'{m.group(1)}="{m.group(2)}{value}--{language}"' if value in ids else m.group(0)
    fragment = re.sub(r'(?<![\w-])(id|aria-labelledby|aria-describedby|for)="()([^"]+)"',
                      ref, fragment)
    return re.sub(r'(?<![\w-])(href)="(#)([^"]+)"', ref, fragment)


def page(view: Mapping, *, surfaces: Mapping | None, variables: list[dict] | None,
         sample: Mapping | None, understanding: str = '',
         twin: Mapping | None = None) -> tuple[str, list[str]]:
    """``(html, consumed result ids)`` of the report (see :func:`render_html.build`)."""
    study = view.get('language') if view.get('language') in LANGUAGES else 'en'
    other = 'fr' if study == 'en' else 'en'
    twin = _mark_labels(view, twin if twin is not None else derive_twin(view, other), study)
    surfaces = dict(surfaces or {})
    surfaces.setdefault('report', {'status': 'ok', 'revision': view['revision']})
    editions, consumed = [], set()
    with texts.study_context(view), rh.study_language_context(study):
        for language, v in ((study, dict(view, language=study)), (other, twin)):
            with texts.report_language_context(language), \
                    rh.model_names_context(model_names(v, language)):
                citer = cite.Citer.from_view(v)
                # v4: in the second edition (shown only by the script), the hover title of a
                # cited number is set by the script from its attributes (it named the result
                # twice in each of a thousand numbers); the first edition keeps it.
                citer.titles = language == study
                body, title = edition(v, citer, surfaces=surfaces, variables=variables or [],
                                      sample=sample, understanding=understanding,
                                      primary=language == study)
                if language == 'fr':
                    # L3 (R4): the renderers' own English phrases (charts, diagnostics, table
                    # heads) in French (:mod:`mlkit.study.l10n_report`).
                    from . import l10n_report
                    body = l10n_report.french(body)
                if language != study:
                    body = suffix_ids(body, language)
                consumed |= {c['result_id'] for c in citer.cited}
                editions.append((language, body, title))
    snapshot_json = json.dumps(view.get('presentation'), sort_keys=True,
                               separators=(',', ':'), ensure_ascii=False).replace('<', '\\u003c')
    first_title = editions[0][2]
    with texts.report_language_context(study):
        tools = _tools(study)
    out = (f'<!doctype html>\n<html lang="{study}" data-lang="{study}" data-study-lang="{study}">'
           '<head><meta charset="utf-8">'
           '<meta name="viewport" content="width=device-width,initial-scale=1">'
           '<meta name="color-scheme" content="dark light">'
           '<meta name="theme-color" content="#20312C">'
           f'<meta name="hypotrail-revision" content="{view["revision"]}">'
           f'<meta name="hypotrail-template-version" content="{rh.TEMPLATE_VERSION}">'
           f'<title>{e(first_title)}</title><style>{css()}</style></head>\n'
           f'<body class="report" data-revision="{view["revision"]}">'
           f'{rh.BANNER_START}{rh.BANNER_END}\n'
           '<svg width="0" height="0" style="position:absolute" aria-hidden="true">'
           '<filter id="chalkf" x="-2%" y="-2%" width="104%" height="104%">'
           '<feTurbulence type="fractalNoise" baseFrequency="1.2" numOctaves="2" seed="7" '
           'result="n"/><feDisplacementMap in="SourceGraphic" in2="n" scale="1.2" '
           'xChannelSelector="R" yChannelSelector="G"/></filter></svg>'
           '<div class="ledge" aria-hidden="true"></div>\n'
           f'{tools}\n'
           + ''.join(f'<div class="ed" data-ed="{lang}" lang="{lang}" data-title="{e(title)}">'
                     f'{body}</div>\n' for lang, body, title in editions)
           + f'<script type="application/json" id="hypotrail-presentation">{snapshot_json}'
             f'</script><script>{SCRIPT}</script></body></html>\n')
    return out, sorted(consumed)


def _tools(study: str) -> str:
    """The language and theme buttons, fixed at the top right; hidden until the script runs
    (without script nothing would switch)."""
    other = 'fr' if study == 'en' else 'en'
    lang_label = ''.join(f'<span class="only-{lang}" lang="{"fr" if lang == "en" else "en"}">'
                         f'{e(texts.say(texts.lesson("ui.lang_to"), lang))}</span>'
                         for lang in LANGUAGES)
    white = ''.join(f'<span class="only-{lang} when-black">'
                    f'{e(texts.say(texts.lesson("ui.theme_white"), lang))}</span>'
                    f'<span class="only-{lang} when-white">'
                    f'{e(texts.say(texts.lesson("ui.theme_black"), lang))}</span>'
                    for lang in LANGUAGES)
    aria = {lang: texts.say(texts.lesson('ui.lang_aria'), lang) for lang in LANGUAGES}
    return (f'<div class="tools" id="tools" hidden>'
            f'<button class="tb" id="langBtn" type="button" data-lang-toggle '
            f'aria-pressed="false" aria-label="{e(aria[study])}" '
            f'data-aria-en="{e(aria["en"])}" data-aria-fr="{e(aria["fr"])}" '
            f'data-other="{other}">{lang_label}</button>'
            f'<button class="tb" id="themeBtn" type="button" data-theme-toggle '
            f'aria-pressed="false">{white}</button></div>')


# --- one edition -----------------------------------------------------------------------------

def edition(view: Mapping, citer: cite.Citer, *, surfaces: Mapping, variables: list[dict],
            sample: Mapping | None, understanding: str, primary: bool) -> tuple[str, str]:
    """``(html, title)`` of one edition, in the report language."""
    labels = texts.report()
    c = rn.Context(view, citer, variables, sample)
    verdict = _verdict(c)
    chapters = rn.chapters(c)
    prereq = _prereq(c)
    lesson = (f'<section class="blk" id="lesson"><h2 class="lecon-h">'
              f'{e(g.say("ui.lesson_heading"))}</h2><div class="lecon">'
              + ''.join(ch['html'] for ch in chapters) + '</div></section>')
    understanding_html = ''
    if understanding:
        lang = rh.foreign()
        understanding_html = (f'<section class="blk" id="understanding-wrap"'
                              f'{f" lang={chr(34)}{lang}{chr(34)}" if lang else ""}>'
                              f'<div class="card plain understanding">{understanding}</div>'
                              f'</section>')
    summary = _summary(c, chapters)
    voice = _voice(c, chapters)
    decisions = _decisions(c)
    appendix = _appendix(view, citer, surfaces)
    main = (prereq + verdict + lesson + understanding_html + summary + voice + decisions
            + appendix)
    title = f'{labels["title"]} · {view["case"].get("id", "")}'
    sections = _sections(c, chapters, bool(understanding), bool(decisions))
    out = (_posbar(c, chapters, sections)
           + '<div class="app">' + _header(c) + _automation(c)
           + '<div class="wrap">' + _toc(c, chapters, sections)
           + f'<main id="main">{main}</main></div>'
           + f'<footer class="page-footer">{g.t("ui.footer", revision=rh.lit("revision", view["revision"]))}'
             f'</footer></div>')
    return out, title


def _sections(c, chapters, understanding: bool, decisions: bool) -> list[tuple]:
    """``(id, group, title)`` of every section of the edition, in page order."""
    out = [('prereq', 'opening', g.say('ui.sections.prereq')),
           ('verdict', 'opening', g.say('ui.sections.verdict'))]
    out += [(ch['id'], 'chapter', ch['title']) for ch in chapters]
    if understanding:
        out.append(('understanding-wrap', 'after', g.say('ui.sections.understanding')))
    out.append(('resume', 'after', g.say('ui.sections.summary')))
    out.append(('voix', 'after', g.say('ui.sections.voice')))
    if decisions:
        out.append(('decisions', 'after', g.say('ui.sections.decisions')))
    out.append(('appendix', 'after', g.say('ui.sections.annex')))
    return out


def _automatic(view: Mapping) -> list[str]:
    """The decisions recorded by the automatic mode and not yet adopted, in plan order."""
    out = []
    for step in view['plan']:
        did = step.get('decision')
        d = view['decisions'].get(did) if did else None
        conf = (d or {}).get('confirmation') or {}
        if d and conf.get('basis') == 'automatic' \
                and d.get('status') in ('confirmed', 'reconfirm_required') and did not in out:
            out.append(did)
    return out


def _awaits(c) -> list[str]:
    view = c.view
    out = []
    final = view.get('final_test') or {}
    if final.get('status') == 'sealed':
        out.append(f'<a class="pend" href="#ch8">{e(g.say("ui.pos_final_test"))}</a>')
    if (view['decisions'].get('conclusion') or {}).get('status') != 'confirmed':
        out.append(f'<a class="pend" href="#ch9">{e(g.say("ui.pos_conclusion"))}</a>')
    auto = _automatic(view)
    if auto:
        out.append(f'<a class="pend" href="#decisions">'
                   f'{g.t("ui.pos_review", n=g.count("structure", len(auto)))}</a>')
    return out


def _posbar(c, chapters, sections) -> str:
    """The position line (R30): one item per section, the first shown without script."""
    awaits = _awaits(c)
    awaits_html = (g.t('ui.pos_awaits', list=', '.join(awaits)) if awaits
                   else e(g.say('ui.pos_complete')))
    by_id = {ch['id']: ch for ch in chapters}
    items = []
    total = g.ordinal(len(rn.CHAPTERS))
    final_status = (c.view.get('final_test') or {}).get('status')
    for i, (sid, group, title) in enumerate(sections):
        if group == 'chapter':
            ch = by_id[sid]
            n = rn.CHAPTERS.index(sid) + 1
            here = (f'<span class="k">{g.t("ui.pos_chapter", n=g.ordinal(n), total=total)}'
                    f'</span> · <b>{e(title)}</b>')
            if sid == 'ch8' and final_status == 'sealed':
                here += f' · {e(g.say("ui.pos_sealed"))}'
            elif ch['status'] == 'pending':
                here += f' · {e(g.say("ui.pos_pending"))}'
            rest = rn.CHAPTERS[n:]
            left = []
            if rest:
                left.append(g.t('ui.pos_rest', list=', '.join(
                    f'<a href="#{r}">{e(g.say("ui.short." + r))}</a>' for r in rest)))
            left.append(awaits_html)
            left_html = ' · '.join(left)
        else:
            word = g.say('ui.pos_opening' if group == 'opening' else 'ui.pos_after')
            here = f'<b>{e(word)}</b> · {e(title)}'
            if group == 'opening':
                left_html = (g.t('ui.pos_next', list=f'<a href="#verdict">'
                                                      f'{e(g.say("ui.pos_verdict"))}</a>, '
                                                      f'<a href="#ch1">'
                                                      f'{e(g.say("ui.pos_chapters"))}</a>')
                             + ' · ' + awaits_html)
            else:
                left_html = awaits_html
        hidden = '' if i == 0 else ' hidden'
        items.append(f'<div class="pos-item" data-for="{sid}"{hidden}>'
                     f'<div class="pos-here">{here}</div>'
                     f'<div class="pos-left">{left_html}</div></div>')
    return (f'<nav class="posbar" aria-label="{e(g.say("ui.where"))}">{"".join(items)}</nav>')


def _header(c) -> str:
    view = c.view
    case_id = view['case'].get('id', '')
    use = rh._fact_value(view, 'intended_use')
    words = texts.report()['narrative']['objective']
    lead = (f'<p class="use"><span>{e(words["intended_use"])}</span> '
            f'{rh.lit("case", use["value"], "q")}</p>' if use else '')
    legend = (''.join(f'<span>{g.evidence_badge(k)}</span>' for k in rn.EVIDENCE_CLASSES)
              + f'<span>{e(g.say("ui.legend_folds"))}</span>')
    return (f'<header class="top"><div class="crumb">Hypotrail › <b>{rh.lit("case", case_id)}</b>'
            f' › {g.t("ui.crumb", revision=rh.lit("revision", view["revision"]))}</div>'
            f'<h1><span class="ul">{e(rh.capital(g.say("ui.h1")))}</span></h1>{lead}</header>'
            f'<p class="sub">{g.t("ui.sub")}</p><div class="marks-legend">{legend}</div>')


def _automation(c) -> str:
    """The automatic mode's band (L9, R20): the decisions to review, and for good after a
    demonstration, the final test opened automatically."""
    view = c.view
    ids = {item.get('id') for item in view.get('not_yet_defensible') or []}
    parts = []
    if 'automatic_decisions_to_review' in ids:
        n = g.count('structure', len(_automatic(view)))
        parts.append(f'<p data-automation-banner="review">{e(g.say("ui.autoband"))}'
                     f'<small>{g.t("ui.autoband_detail", n=n)} '
                     f'<a href="#decisions">{e(g.say("ui.autoband_link"))}</a>.</small></p>')
    if 'final_test_opened_automatically' in ids:
        parts.append(f'<p data-automation-banner="opened">{e(g.say("ui.opened_band"))}</p>')
    if not parts:
        return ''
    return (f'<div class="autoband" role="note" data-automation="banner"><b class="l">'
            f'{e(g.say("ui.autoband_title"))}</b>{"".join(parts)}</div>')


def _toc(c, chapters, sections) -> str:
    view = c.view
    done_chapters = sum(1 for ch in chapters if ch['status'] == 'done')
    plan_done = sum(1 for s in view['plan'] if s.get('status') == 'done')
    auto = _automatic(view)

    def meter(label: str, shown: str, share: float, cls: str = '') -> str:
        width = f'{max(0.0, min(1.0, share)) * 100:.1f}%'
        return (f'<div class="meter"><div class="row"><span>{e(label)}</span><span>{shown}'
                f'</span></div><div class="bar{cls}"><i style="width:{width}"></i></div></div>')
    meters = [meter(g.say('ui.meter_steps'),
                    f'{g.count("structure", plan_done)} / {g.count("structure", len(view["plan"]))}',
                    plan_done / max(1, len(view['plan']))),
              meter(g.say('ui.meter_chapters'),
                    f'{g.count("structure", done_chapters)} / {g.count("structure", len(chapters))}',
                    done_chapters / max(1, len(chapters)))]
    if auto:
        meters.append(meter(g.say('ui.meter_review'),
                            g.t('ui.meter_review_count', n=g.count('structure', len(auto))),
                            1.0, ' pk'))
    meters.append(f'<div class="meter"><div class="row"><span>{e(g.say("ui.meter_reading"))}'
                  f'</span></div><div class="bar readbar"><i style="width:0%"></i></div></div>')

    def item(sid: str, number: str, title: str, mark: str = '') -> str:
        return (f'<li><a href="#{sid}"><span class="n">{number}</span><span>{e(title)}</span>'
                f'<span class="st">{mark}</span></a></li>')
    opening = [item(s, '·', t) for s, grp, t in sections if grp == 'opening']
    chapter_items = []
    final_status = (view.get('final_test') or {}).get('status')
    for ch in chapters:
        status = ch['status']
        glyph = rn.STATUS_GLYPHS[status]
        marks = ' '.join(rn.GLYPHS[k] for k in ch['classes'])
        if ch['id'] == 'ch8' and final_status == 'sealed':
            shown = e(g.say('ui.sealed_toc'))
        else:
            shown = f'{glyph} {marks}'
        cls = ' ok' if status == 'done' else ''
        chapter_items.append(
            f'<li data-status="{status}"><a href="#{ch["id"]}">'
            f'<span class="n">{g.ordinal(rn.CHAPTERS.index(ch["id"]) + 1)}</span>'
            f'<span>{e(ch["title"])}</span><span class="st{cls}" aria-hidden="true">{shown}'
            f'</span><span class="sr">{e(g.say("ui.status." + status))}</span></a></li>')
    after = [item(s, 'A' if s == 'appendix' else '·', t) for s, grp, t in sections
             if grp == 'after']
    summary = g.t('ui.contents_summary', chapters=g.count('structure', len(chapters)),
                  done=g.count('structure', done_chapters))
    return (f'<aside class="side" aria-label="{e(g.say("ui.contents"))}">'
            f'<details class="tocd" open><summary>{summary}</summary><div class="in">'
            f'<div class="root">{e(g.say("ui.root"))}</div>{"".join(meters)}'
            f'<h4>{e(g.say("ui.toc_opening"))}</h4><ol class="toc-a">{"".join(opening)}</ol>'
            f'<h4>{e(g.say("ui.toc_chapters"))}</h4><ol class="toc-list">'
            f'{"".join(chapter_items)}</ol>'
            f'<h4>{e(g.say("ui.toc_end"))}</h4><ol class="toc-b">{"".join(after)}</ol>'
            f'<p class="toc-legend">{e(g.say("ui.toc_legend"))}</p></div></details></aside>')


# --- opening sections ------------------------------------------------------------------------

def _prereq(c) -> str:
    items = ''.join(f'<li>{g.fill(text)}</li>' for text in g.items('prereq.items'))
    marks = g.dl([(g.evidence_badge(k), e(g.say(f'prereq.marks.{k}')))
                  for k in rn.EVIDENCE_CLASSES]
                 + [(e(' · '.join(f'{rn.STATUS_GLYPHS[s]} {g.say("ui.status." + s).split(" ", 1)[-1]}'
                                  for s in ('done', 'in_progress', 'pending'))),
                     e(g.say('prereq.marks.status')))])
    stamps = g.dl([(g.stamp(k), e(g.say(f'prereq.stamps.{k}')))
                   for k in ('real', 'state', 'text', 'auto', 'sealed', 'scenario', 'creation')]
                  + [(f'<span class="recl">({e(rh.study_language())})</span>',
                      e(g.say('prereq.stamps.marker')))])
    abbr = []
    for path in ('prereq.abbr', 'prereq.abbr_task'):
        if g.has(path):
            for node in texts.lesson(path):
                abbr.append((e(texts.say(node['term'])), e(texts.say(node['def']))))
    more = (f'<h5>{e(g.say("prereq.marks_heading"))}</h5>{marks}'
            f'<h5>{e(g.say("prereq.stamps_heading"))}</h5>{stamps}'
            f'<h5>{e(g.say("prereq.abbr_heading"))}</h5>{g.dl(abbr)}')
    return (f'<section class="blk" id="prereq"><div class="card" style="--ac:var(--blue)">'
            f'<div class="lbl">{e(g.say("prereq.label"))}</div><ul>{items}</ul></div>'
            f'<details class="f plus flush"><summary>{e(g.say("ui.fold.more"))} '
            f'<small>{e(g.say("ui.fold.more_report"))}</small></summary>'
            f'<div class="in">{more}</div></details></section>')


def _criterion_bar(c, rid: str, values: Mapping):
    """``(bar position, label)`` of the success criterion for figure V, computed from
    recorded values for the drawing only (no number of it is shown)."""
    sc = c.view['decisions'].get('success_criterion') or {}
    value = sc.get('value') if isinstance(sc.get('value'), Mapping) else {}
    if value.get('metric') == 'mae_reduction' and cite.is_number(value.get('min_share')):
        base = ((values.get('models') or {}).get('fit.baseline') or {}).get('mae')
        if cite.is_number(base):
            return base * (1 - value['min_share']), g.say('charts.errors_bar')
    return None, ''


def _verdict(c) -> str:
    view, citer = c.view, c.citer
    labels = texts.report()
    card = labels['verdict_card']
    task = c.task
    conclusion = view['decisions']['conclusion']
    value = conclusion.get('value') if isinstance(conclusion.get('value'), Mapping) else None
    final = view.get('final_test') or {}
    if conclusion['status'] == 'confirmed' and value:
        verdict = labels['verdict'].get(value.get('verdict'), value.get('verdict'))
        big = (f'<p class="big conclusion" data-verdict="{e(str(value.get("verdict")))}">'
               f'<strong>{e(verdict)}.</strong><small>{e(g.say("verdict.concluded_detail"))}'
               f'</small></p>{rh.recorded("decision_value", value.get("text", ""), "q")}'
               + rh._credit(view, c.titles))
    else:
        choice = view['decisions'].get('model_choice' if task == 'regression' else 'policy') or {}
        waiting = any(p['decision_id'] == 'conclusion' for p in view['open_proposals'])
        if choice.get('status') in ('confirmed', 'reconfirm_required'):
            chosen = choice.get('value')
            name = (rh.model_phrase(chosen) if task == 'regression'
                    else rh.rule_words(str(chosen).partition('@')[0]))
            by = (g.say('verdict.by_automatic')
                  if (choice.get('confirmation') or {}).get('basis') == 'automatic' else '')
            state = g.say('verdict.final_states.' + (
                'sealed' if final.get('status') == 'sealed' else
                'opened' if final.get('status') == 'opened' else 'absent'))
            detail = g.t('verdict.none_detail_chosen',
                         model=e(name) if task == 'regression'
                         else rh.lit('decision_value', name), by=e(by),
                         final_state=e(state))
        else:
            detail = g.t('verdict.none_detail')
        big = (f'<p class="big conclusion" data-verdict="none"><strong>'
               f'{e(card["not_concluded"])}</strong>'
               f'{" " + e(card["proposed"]) if waiting else ""}<small>{detail}</small></p>')
    # the development and final evidence side by side
    criterion = view.get('criterion') or {}
    if task == 'regression':
        chosen = criterion.get('model') or 'fit.linear'
        figures = rh._regression_figures(citer, chosen if chosen != 'fit.baseline'
                                         else 'fit.linear')
    else:
        rule = criterion.get('rule')
        model = criterion.get('model') or 'fit.logistic'
        adopted = view['decisions'].get('policy') or {}
        if rule is None and adopted.get('status') == 'confirmed':
            rule = str(adopted.get('value')).partition('@')[0]
            from .records import policy_model
            model = policy_model(adopted.get('value'))
        figures = rh._binary_figures(view, citer, rule, model)
        if figures and rule:
            figures.insert(0, (card['rule_of_figures'], rh.lit('decision_value',
                                                               rh.rule_words(rule))))
    final_rows = rh._final_rows(view, citer, task) if 'final_test' in view['decisions'] \
        else [(card['final'], e(card['final_absent']))]
    trials = (view.get('trials') or {}).get('count')
    if isinstance(trials, int) and trials and card['trials'] not in (k for k, _ in final_rows):
        figures.append((card['trials'], g.count('structure', trials)))
    dev_box = (f'<div class="vbox dev"><h3>{e(g.say("verdict.dev_title"))}</h3>'
               f'<p class="note">{e(g.say("verdict.dev_note"))}</p>'
               + (g.dl(((e(k), v) for k, v in figures), 'kv') if figures
                  else f'<p class="muted">{e(card["figures_none"])}</p>') + '</div>')
    sealed = g.stamp('sealed') if final.get('status') == 'sealed' else ''
    final_box = (f'<div class="vbox fin"><h3>{e(g.say("verdict.final_title"))} {sealed}</h3>'
                 f'<p class="note">{e(g.say("verdict.final_note"))}</p>'
                 + g.dl(((e(k), v) for k, v in final_rows), 'kv') + '</div>')
    # WP-B6a: once the final test is opened, its evidence comes first.
    boxes = (final_box + dev_box) if final.get('status') == 'opened' else (dev_box + final_box)
    crit_rows = rh.criterion_rows(view)
    crit = ''
    if crit_rows:
        label, text = crit_rows[0]
        status = criterion.get('judged_status') or criterion.get('status')
        stamp_html = ''
        sc = view['decisions'].get('success_criterion') or {}
        if (sc.get('confirmation') or {}).get('basis') == 'automatic':
            stamp_html = ' ' + g.stamp('auto')
        extra = ''
        if status == 'met' and criterion.get('judged_on') != 'final_test':
            extra = (f' <b class="ok">{e(g.say("verdict.criterion_status.met"))}</b>. '
                     f'{e(g.say("verdict.criterion_dev"))}')
        crit = f'<div class="crit"><b>{e(label)}</b>{stamp_html} : {text}{extra}</div>' \
            if c.lang == 'fr' else \
            f'<div class="crit"><b>{e(label)}</b>{stamp_html}: {text}{extra}</div>'
    # R52: a regression's development and final evidence in one table, configuration by
    # configuration; the criterion is its last row, judged on the final test once opened.
    table = ev.regression_table(view, citer) if task == 'regression' else ''
    evidence_html = table if table else f'<div class="vgrid">{boxes}</div>{crit}'
    # figure V
    figure = ''
    fin = citer.slot_rid('final_test.evaluation')
    if task == 'regression' and table and fin:
        # R52, R48: once the final test is opened, figure V draws the table's values as dots
        # with their intervals, development and final side by side, the final-test bound.
        fv = citer.results[fin].values
        dev = citer.slot_rid('evaluate.regression')
        m = cite.format_path(['models', str(fv.get('model')), 'mae'])
        b = cite.format_path(['models', 'fit.baseline', 'mae'])
        dots = ev.evidence_dots(view, citer)
        if dots and dev and citer.has(dev, m) and citer.has(fin, m) and citer.has(fin, b):
            figure = c.frame('verdict', 'evidence_dots', dots,
                             values={'dev': citer.num(dev, m, 'f2'),
                                     'final': citer.num(fin, m, 'f2'),
                                     'base': citer.num(fin, b, 'f2')},
                             slot='final_test.evaluation', evidence='final',
                             frame_html=g.frame_line('final', rn._frame_rows(c, fin)))
    elif task == 'regression':
        rid = citer.slot_rid('evaluate.regression')
        if rid:
            values = citer.results[rid].values
            bar, bar_label = _criterion_bar(c, rid, values)
            chart = render_charts.errors_bar(citer, rid, values, bar=bar, bar_label=bar_label)
            m = cite.format_path(['models', criterion.get('model') or 'fit.linear', 'mae'])
            b = cite.format_path(['models', 'fit.baseline', 'mae'])
            sc = view['decisions'].get('success_criterion') or {}
            fvalues, conclude = {}, 'none'
            status = criterion.get('judged_status') or criterion.get('status')
            if citer.has(rid, m) and citer.has(rid, b) and sc.get('value') is not None and status:
                fvalues = {'mae_model': citer.num(rid, m, 'f2'), 'mae_base': citer.num(rid, b, 'f2'),
                           'criterion': rh.lit('decision_value', rh.value_words(
                               'success_criterion', sc['value'], task)),
                           'status': e(g.say('verdict.criterion_status.' + (
                               'met_final' if status == 'met' and
                               criterion.get('judged_on') == 'final_test' else status)))}
                conclude = None
            note = f'<p class="cap">{e(g.say("figures.errors_bar.bar_note"))}</p>' if bar else ''
            figure = c.frame('verdict', 'errors_bar', chart + note, values=fvalues,
                             conclude=conclude, slot='evaluate.regression',
                             evidence='development',
                             frame_html=g.frame_line('development', rn._frame_rows(c, rid),
                                                     rn._scored()))
    else:
        figure = _verdict_binary_figure(c, criterion)
    plan_done = sum(1 for s in view['plan'] if s.get('status') == 'done')
    chips = []
    for s in view['plan']:
        cls = 'done' if s.get('status') == 'done' else ('here' if s.get('current') else '')
        here = f' · {e(g.say("verdict.here"))}' if s.get('current') else ''
        chips.append(f'<span class="{cls}" data-step="{e(s["id"])}" data-status="{e(s["status"])}">'
                     f'{e(s["title"])}{here}</span>')
    plan = (f'<div class="lbl">{g.t("verdict.plan_label", done=g.count("structure", plan_done), total=g.count("structure", len(view["plan"])))}</div>'
            f'<div class="plan" id="plan-chips">{"".join(chips)}</div>')
    limits = rh._limits(view)
    limits_html = ''
    if limits:
        limits_html = (f'<div class="lbl">{e(g.say("verdict.limits"))}</div><ul class="limits">'
                       + ''.join(f'<li>{rh.lit("message", t)}</li>' for t in limits) + '</ul>')
    na = view['next_action']
    where = (f'<p class="where"><b>{e(labels["narrative"]["where"])}</b> '
             f'{rh.recorded("message", na.get("junior_message") or na.get("message", ""), language=None if not view.get("_derived") else rh.study_language())}</p>')
    links = (f'<p class="links"><a href="#ch1">{e(g.say("ui.read_from_start"))}</a> · '
             f'<a href="#not-yet-defensible">{e(g.say("ui.all_limits"))}</a></p>')
    return (f'<section class="blk" id="verdict"><h2>{e(g.say("ui.sections.verdict_heading"))}</h2>'
            f'<div class="card verdict plain">'
            f'<div class="lbl">{g.t("verdict.label", revision=rh.lit("revision", view["revision"]))} '
            f'{g.stamp("real")}</div>{big}'
            f'{evidence_html}{figure}{plan}{limits_html}'
            f'{where}{links}</div></section>')


def _verdict_binary_figure(c, criterion: Mapping) -> str:
    """Figure V of a binary study: the precision of each model and of the baseline at the
    rule of the criterion, with their intervals, and the criterion's bar (the baseline's
    precision plus the criterion's points, a position for the drawing only)."""
    view, citer = c.view, c.citer
    rid = citer.slot_rid('policy.evaluation')
    rule = criterion.get('rule')
    if rid is None or not rule:
        return ''
    rules = citer.results[rid].values.get('rules') or {}
    item = rules.get(rule) if isinstance(rules, Mapping) else None
    if not isinstance(item, Mapping):
        return ''
    sub = {'models': item.get('models') or {}, 'intervals': item.get('intervals') or {}}
    sc = view['decisions'].get('success_criterion') or {}
    value = sc.get('value') if isinstance(sc.get('value'), Mapping) else {}
    bar, label = None, ''
    base = ((sub['models'].get('fit.baseline') or {}).get('precision'))
    if value.get('metric') == 'precision_gain' and cite.is_number(value.get('min_points')) \
            and cite.is_number(base):
        bar, label = base + value['min_points'] / 100, g.say('charts.errors_bar')
    chart = render_charts.errors_bar(rn._RulePrefixCiter(citer, rid, rule), rid, sub,
                                     metric='precision', bar=bar, bar_label=label,
                                     lower_better=False, fmt='pct1')
    model = criterion.get('model') or 'fit.logistic'
    m = cite.format_path(['rules', rule, 'models', model, 'precision'])
    b = cite.format_path(['rules', rule, 'models', 'fit.baseline', 'precision'])
    status = criterion.get('judged_status') or criterion.get('status')
    fvalues, conclude = {}, 'none'
    if citer.has(rid, m) and citer.has(rid, b) and sc.get('value') is not None and status:
        fvalues = {'precision': citer.num(rid, m, 'pct1'), 'base': citer.num(rid, b, 'pct1'),
                   'rule': rh.lit('decision_value', rh.rule_words(rule)),
                   'criterion': rh.lit('decision_value', rh._lower_first(rh.value_words(
                       'success_criterion', sc['value'], c.task))),
                   'status': e(g.say('verdict.criterion_status.' + (
                       'met_final' if status == 'met' and
                       criterion.get('judged_on') == 'final_test' else status)))}
        conclude = None
    note = f'<p class="cap">{e(g.say("figures.errors_bar.bar_note"))}</p>' if bar else ''
    return c.frame('verdict', 'errors_bar', chart + note, values=fvalues, conclude=conclude,
                   slot='policy.evaluation', evidence='development',
                   frame_html=g.frame_line('development', rn._frame_rows(c, rid), rn._scored()))


# --- after the chapters ----------------------------------------------------------------------

def _best(c) -> str | None:
    view, citer = c.view, c.citer
    if c.task == 'regression':
        rid = citer.slot_rid('evaluate.regression')
        model = (view.get('criterion') or {}).get('model') or 'fit.linear'
        if rid:
            m = cite.format_path(['models', model, 'mae'])
            b = cite.format_path(['models', 'fit.baseline', 'mae'])
            if citer.has(rid, m) and citer.has(rid, b):
                return g.t('summary.best_regression', model=e(rh.model_phrase(model)),
                           mae_model=citer.num(rid, m, 'f2'), mae_base=citer.num(rid, b, 'f2'))
    else:
        rid = citer.slot_rid('policy.evaluation')
        model = (view.get('criterion') or {}).get('model') or 'fit.logistic'
        auc = cite.format_path(['ranking', model, 'roc_auc'])
        if rid and citer.has(rid, auc):
            return g.t('summary.best_binary', model=e(rh.model_phrase(model)),
                       auc=citer.num(rid, auc, 'f3'))
    return None


def _summary(c, chapters) -> str:
    items = ''.join(f'<li data-chapter="{ch["id"]}">{ch["keep"]}</li>'
                    for ch in chapters if ch['keep'])
    target = rn._fact(c, 'target') or e(g.say('ui.sections.summary'))
    best = _best(c)
    concluded = (c.view['decisions'].get('conclusion') or {}).get('status') == 'confirmed'
    if best is None:
        phrase = g.t('summary.phrase_none', target=target)
    else:
        phrase = g.t('summary.phrase_closed' if concluded else 'summary.phrase_open',
                     target=target, best=best)
    return (f'<section class="blk" id="resume"><h2>{e(g.say("ui.sections.summary"))}</h2>'
            f'<div class="card resume"><p class="small">{e(g.say("summary.intro"))}</p>'
            f'<ol>{items}</ol></div><div class="phrase"><span class="k">'
            f'{e(g.say("summary.phrase_label"))}</span><p>{phrase}</p></div></section>')


def _voice(c, chapters) -> str:
    items = []
    for ch in chapters:
        if not ch['keep']:
            continue
        items.append(f'<li><span class="q">{g.t("chapters." + ch["id"] + ".question")}</span>'
                     f'<span class="a hid" tabindex="0" role="button" '
                     f'aria-label="{e(g.say("ui.reveal"))}">{ch["keep"]}</span></li>')
    return (f'<section class="blk" id="voix"><h2>{e(g.say("ui.sections.voice"))}</h2>'
            f'<div class="card say-card"><p class="small">{e(g.say("voice.intro"))}</p>'
            f'<ol class="verb">{"".join(items)}</ol></div></section>')


def _decisions(c) -> str:
    view = c.view
    auto = _automatic(view)
    if not auto:
        return ''
    mapping = rn.REGRESSION_STEP_CHAPTER if c.task == 'regression' else rn.STEP_CHAPTER
    step_of = {s.get('decision'): s['id'] for s in view['plan'] if s.get('decision')}
    rows = []
    for did in auto:
        d = view['decisions'][did]
        words = rh.value_words(did, d['value'], c.task)
        shown = (rh.recorded('decision_value', words) if isinstance(d['value'], str)
                 and words == d['value'] else rh.lit('decision_value', words))
        chapter = mapping.get(step_of.get(did), 'ch1')
        rows.append(f'<tr data-decision="{e(did)}"><td>{e(c.titles.get(did, did))}</td>'
                    f'<td>{shown}</td><td>{g.stamp("auto")}</td>'
                    f'<td><a href="#{chapter}">{g.t("ui.chapter_ref", n=g.ordinal(rn.CHAPTERS.index(chapter) + 1))}</a></td></tr>')
    cols = {k: e(g.say(f'decisions.cols.{k}')) for k in ('decision', 'value', 'basis', 'chapter')}
    na = view['next_action']
    message = na.get('junior_message') or na.get('message', '')
    return (f'<section class="blk" id="decisions"><h2>{e(g.say("ui.sections.decisions"))}</h2>'
            f'<div class="card plain dec-card" style="--ac:var(--red)">'
            f'<p>{e(g.say("decisions.intro"))}</p><div class="tbl"><table class="dec-list">'
            f'<thead><tr><th>{cols["decision"]}</th><th>{cols["value"]}</th>'
            f'<th>{cols["basis"]}</th><th>{cols["chapter"]}</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>'
            f'<p><b>{e(g.say("decisions.next"))}</b> '
            f'{rh.recorded("message", message, language=rh.study_language() if view.get("_derived") else None)}</p>'
            f'</div></section>')


def _appendix(view: Mapping, citer: cite.Citer, surfaces: Mapping) -> str:
    words = texts.report()['narrative']
    annex = words['annex']
    extras = [('plan', annex['plan'], rh._plan(view)), ('facts', annex['facts'], rh._facts(view)),
              ('history', annex['history'], rh._history(view)),
              ('revision', annex['revision'], rh._surfaces(view, surfaces))]
    more = ''.join(f'<details class="f annex-part" data-annex="{key}"><summary>{e(title)}'
                   f'</summary><div class="in">{rn.demote(body, 2)}</div></details>'
                   for key, title, body in extras if body)
    return (f'<section class="blk annex-blk" id="appendix" aria-labelledby="appendix-t">'
            f'<h2 id="appendix-t">{e(g.say("ui.sections.annex"))}</h2>'
            f'<p class="sub">{e(g.say("annex.intro"))}</p>'
            f'{rn.demote(rh._annex(view, citer), 1)}{more}</section>')


# --- style ------------------------------------------------------------------------------------

def css() -> str:
    from . import render_evidence
    return CSS + render_charts.CHART_CSS_LESSON + render_evidence.CSS


CSS = r'''
:root{--board:#20312C;--board2:#1A2925;--chalk:#EDE8DA;--chalk2:#C9C4B6;--dust:rgba(237,232,218,.55);
--ink:#EDE8DA;--muted:#C9C4B6;--faint:#8F9A93;--line:rgba(237,232,218,.14);--line2:rgba(237,232,218,.3);
--yellow:#F0D178;--pink:#EFA3B8;--mint:#B9E2C4;--teal:#9FE0D2;--violet:#C8B6F5;--blue:#A7CCEB;--green:#B9E2C4;--coral:#F3A28F;--amber:#F0D178;
--card:#F5F1E6;--cardink:#22302B;--cardmuted:#4E5A55;--cardline:rgba(34,48,43,.14);--cardsoft:#ECE7D8;
--gridmm:rgba(38,72,124,.045);--ruleline:rgba(34,48,43,.045);--red:#B8322A;--pen:#1E4E9E;--hl:rgba(255,222,64,.55);
--ochre:#B07418;--slate:#2E5446;
--serif:Georgia,"Iowan Old Style","Times New Roman",serif;--sans:"Avenir Next",Avenir,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;--mono:ui-monospace,Menlo,Consolas,monospace;
--s-lin:#1E4E9E;--s-base:#B07418;--s-ridge:#0F7A6E;--s-ebm:#6B46C1;--s-v3:#9B2C5C;--s-ok:#1F7A44;
--posh:58px;color-scheme:dark}
body.white{--board:#F1F3F1;--board2:#E4E8E4;--chalk:#1E2A36;--chalk2:#3E4A57;--dust:rgba(30,42,54,.6);
--ink:#1E2A36;--muted:#3E4A57;--faint:#7C8896;--line:rgba(30,42,54,.12);--line2:rgba(30,42,54,.3);
--yellow:#B7791F;--pink:#B93A5A;--mint:#1F7A44;--teal:#0F8A7C;--violet:#6B46C1;--blue:#1F5FA8;--green:#1F7A44;--coral:#C0392B;--amber:#B7791F;
--card:#FFFFFF;--cardsoft:#F1EFE9;--cardline:rgba(34,48,43,.12);--ruleline:rgba(34,48,43,.035);--gridmm:rgba(38,72,124,.035);color-scheme:light}
*{box-sizing:border-box}
html{scroll-behavior:smooth;scroll-padding-top:calc(var(--posh) + 12px)}
body{margin:0;background:var(--board);color:var(--ink);font-family:var(--sans);font-size:16px;line-height:1.5;-webkit-font-smoothing:antialiased;min-height:100vh;padding:var(--posh) 0 20px;
background-image:radial-gradient(ellipse at 20% 0%,rgba(255,255,255,.05),transparent 55%),radial-gradient(ellipse at 90% 100%,rgba(255,255,255,.04),transparent 50%)}
body.white{background-image:none}
a{color:inherit}
p,li,dd,dt,summary{overflow-wrap:anywhere}
td,th{overflow-wrap:normal;word-break:normal;hyphens:manual}
:focus-visible{outline:2px solid var(--yellow);outline-offset:2px}
.ledge{position:fixed;left:0;right:0;bottom:0;height:8px;background:linear-gradient(#5b4632,#3b2b1c);opacity:.9;z-index:5}
body.white .ledge{background:linear-gradient(#c8ccd0,#9aa1a8)}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.ed{display:none}
html[data-lang="en"] .ed[data-ed="en"],html[data-lang="fr"] .ed[data-ed="fr"]{display:block}
html[data-lang="en"] .only-fr,html[data-lang="fr"] .only-en{display:none}
.tb{font:500 13px var(--sans);color:var(--ink);background:transparent;border:1.5px solid var(--line2);border-radius:3px;padding:6px 12px;cursor:pointer;white-space:nowrap}
.tb:hover,.tb[aria-pressed="true"]{border-color:var(--yellow);color:var(--yellow)}
.tools{position:fixed;top:calc(env(safe-area-inset-top,0px) + 10px);right:calc(env(safe-area-inset-right,0px) + 14px);z-index:30;display:flex;gap:8px}
.tools[hidden]{display:none}
.tools .tb{background:var(--board2);box-shadow:0 6px 16px -8px rgba(0,0,0,.55)}
#langBtn{min-width:44px}
body:not(.white) .when-white,body.white .when-black{display:none}
.posbar{position:fixed;top:0;left:0;right:0;z-index:25;height:var(--posh);padding:6px calc(var(--toolsw,190px) + 28px) 6px 16px;background:var(--board2);border-bottom:1px solid var(--line2);box-shadow:0 8px 18px -14px rgba(0,0,0,.6);font:13px/1.35 var(--sans);color:var(--chalk2);overflow:hidden}
.pos-item{display:flex;flex-direction:column;justify-content:center;gap:1px;height:100%;min-width:0}
.pos-item[hidden]{display:none}
.pos-here,.pos-left{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
.pos-here b{color:var(--chalk);font-weight:600}
.pos-here .k{color:var(--yellow);font-weight:600}
.pos-left{font-size:12.5px;color:var(--faint)}
.posbar a{color:var(--chalk2);text-decoration:underline;text-decoration-color:var(--line2);text-underline-offset:2px}
.posbar a:hover{color:var(--yellow)}
.posbar a.pend{color:var(--pink);text-decoration-color:var(--pink)}
.app{max-width:1240px;margin:0 auto;padding:18px clamp(16px,3vw,32px) 60px}
.top{border-bottom:2px solid var(--line2);padding:6px 0 12px}
.top .crumb{font-size:13px;color:var(--faint)}
.top .crumb b{font-weight:500;color:var(--muted)}
.top h1{font-family:var(--serif);font-weight:400;font-size:clamp(24px,3.4vw,36px);line-height:1.2;color:var(--chalk);text-shadow:0 0 1px var(--dust);margin:6px 0 0}
.top .use{font-family:var(--serif);font-size:17px;line-height:1.45;color:var(--chalk2);margin:10px 0 0;max-width:80ch}
.top .use span{display:block;font:600 .74rem var(--sans);letter-spacing:.08em;text-transform:uppercase;color:var(--yellow)}
.top h1 .ul{text-decoration:underline;text-decoration-color:var(--yellow);text-decoration-thickness:3px;text-underline-offset:6px}
.sub{color:var(--muted);margin:14px 0 0;max-width:76ch;line-height:1.6;font-size:15.5px}
.marks-legend{display:flex;flex-wrap:wrap;gap:8px 18px;font-size:13.5px;color:var(--muted);margin:12px 0 0}
.marks-legend>span{display:inline-flex;align-items:center;gap:6px}
.autoband{margin:18px 0 0;border:1.5px solid var(--pink);background:rgba(239,163,184,.07);border-radius:3px;padding:12px 16px;transform:rotate(-.25deg);max-width:900px}
.autoband b.l{display:block;font:700 11px var(--sans);letter-spacing:.08em;text-transform:uppercase;color:var(--pink);margin-bottom:2px}
.autoband p{font-family:var(--serif);font-size:17px;color:var(--chalk);text-shadow:0 0 1px var(--dust);margin:4px 0}
.autoband p small{display:block;font:14px/1.5 var(--sans);color:var(--muted);text-shadow:none;margin-top:4px}
.autoband a{color:var(--yellow)}
.wrap{display:grid;grid-template-columns:250px minmax(0,1fr);gap:30px;margin-top:22px}
main{min-width:0}
.side{position:sticky;top:calc(var(--posh) + 12px);align-self:start;max-height:calc(100vh - var(--posh) - 28px);overflow:auto;font-size:13.5px;border-left:2px solid var(--yellow);padding:2px 0 8px 14px}
.side summary{display:none}
.side .root{font-family:var(--serif);font-size:17px;color:var(--chalk);text-shadow:0 0 1px var(--dust);margin-bottom:8px}
.side h4{font:600 11px var(--sans);letter-spacing:.08em;text-transform:uppercase;color:var(--faint);margin:14px 0 6px}
.side ol{list-style:none;margin:0;padding:0}
.side li{border-left:1px solid var(--line2);padding:3px 0 3px 10px}
.side li a{text-decoration:none;color:var(--chalk2);display:grid;grid-template-columns:18px 1fr auto;gap:4px;align-items:baseline}
.side li a:hover{color:var(--yellow)}
.side li .n{font:600 11.5px var(--sans);color:var(--faint)}
.side li .st{font-size:12px;color:var(--faint);white-space:nowrap}
.side li .st.ok{color:var(--mint)}
.side li.cur{border-left:2px solid var(--yellow);margin-left:-.5px}
.side li.cur a{color:var(--chalk);font-weight:600}
.side li.cur .n{color:var(--yellow)}
.side li a[aria-current="true"]{color:var(--chalk);font-weight:600}
.toc-legend{margin-top:10px;font-size:12px;color:var(--faint)}
.meter{margin:4px 0 10px}
.meter .row{display:flex;justify-content:space-between;color:var(--muted);font-size:12.5px;gap:8px}
.meter .bar{height:6px;border-radius:3px;background:var(--line);margin-top:3px;overflow:hidden}
.meter .bar i{display:block;height:100%;background:var(--yellow)}
.meter .bar.pk i{background:var(--pink)}
@media(max-width:1040px){
.wrap{grid-template-columns:minmax(0,1fr)}
.side{position:static;max-height:none;overflow:visible;border:1.5px solid var(--line2);border-radius:3px;padding:0}
.side summary{display:block;cursor:pointer;list-style:none;padding:10px 14px;font:600 13px var(--sans);color:var(--chalk)}
.side summary::-webkit-details-marker{display:none}
.side summary::before{content:"▸ ";color:var(--yellow)}
.side details[open] summary::before{content:"▾ "}
.side .in{padding:0 14px 12px}}
.card{background:repeating-linear-gradient(0deg,transparent 0 27px,var(--ruleline) 27px 28px),var(--card);color:var(--cardink);border-radius:3px;padding:16px 20px;box-shadow:0 14px 26px -14px rgba(0,0,0,.6),0 1px 0 rgba(0,0,0,.2);border-left:4px solid var(--ac,var(--ochre));margin:10px 0}
.card.plain{background:var(--card)}
.card .lbl,.frame .lbl,details .lbl,.choice>.lbl{font:600 11px var(--sans);letter-spacing:.08em;text-transform:uppercase;color:var(--cardmuted);margin-bottom:6px}
.choice>.lbl{color:var(--faint)}
.card p,.card li{font-size:15px;line-height:1.55}
.card ul,.card ol{padding-left:20px}.card li{margin:4px 0}
.card a,.frame a,details.f a{color:var(--slate);text-decoration-color:var(--ochre)}
code{font-family:var(--mono);font-size:.9em}
.card code,details code,.frame code{background:var(--cardsoft);border-radius:2px;padding:0 3px}
.frame{background:repeating-linear-gradient(0deg,var(--gridmm) 0 1px,transparent 1px 12px),repeating-linear-gradient(90deg,var(--gridmm) 0 1px,transparent 1px 12px),var(--card);color:var(--cardink);border:1px solid var(--cardline);border-radius:3px;box-shadow:0 14px 26px -14px rgba(0,0,0,.6),0 1px 0 rgba(0,0,0,.2);padding:14px 16px 12px;margin:14px 0 10px 44px;min-width:0}
.frame .frame{margin-left:0}
.frame .head{display:flex;flex-wrap:wrap;gap:6px 10px;align-items:baseline;justify-content:space-between;margin-bottom:6px}
.frame .head .lbl{margin:0}
.fbody{min-width:0}
.cap{font-family:var(--serif);font-size:14px;color:var(--cardmuted);margin-top:8px;line-height:1.5}
.stamp{display:inline-block;font:700 10.5px var(--sans);letter-spacing:.07em;text-transform:uppercase;border:1.5px solid currentColor;border-radius:2px;padding:1px 6px;transform:rotate(-1deg);white-space:nowrap;vertical-align:middle}
.stamp.real,.stamp.state,.stamp.text,.stamp.scenario,.stamp.creation,.stamp.words{color:var(--s-ok)}
.stamp.auto,.stamp.sealed{color:var(--red)}
.stamp.sealed{transform:rotate(1.5deg)}
.stamp.delegated{color:var(--ochre)}
.evb{display:inline-flex;align-items:center;gap:4px;font:600 11.5px var(--sans);border:1px solid currentColor;border-radius:10px;padding:0 8px;white-space:nowrap;vertical-align:middle;color:var(--chalk2)}
.card .evb,.frame .evb,details .evb{color:var(--cardmuted)}
.evb.ev-final{color:var(--mint)}
.recl{display:inline-block;font:600 10px var(--sans);letter-spacing:.06em;text-transform:uppercase;font-style:normal;color:inherit;opacity:.75;border:1px dotted currentColor;border-radius:2px;padding:0 4px;margin-left:6px;vertical-align:middle;white-space:nowrap}
.blk{margin:26px 0}
.blk>h2,.lecon-h{font-family:var(--serif);font-weight:400;font-size:24px;color:var(--chalk);text-shadow:0 0 1px var(--dust);margin:34px 0 12px}
.blk>h2::before,.lecon-h::before{content:"";display:inline-block;width:22px;height:2px;background:var(--ac,var(--yellow));vertical-align:middle;margin-right:12px;filter:url(#chalkf)}
.verdict .big{font-family:var(--serif);font-size:24px;line-height:1.25;color:var(--cardink);margin:4px 0}
.verdict .big small{display:block;font:15px/1.5 var(--sans);color:var(--cardmuted);margin-top:4px}
.vgrid{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(0,1fr);gap:14px;margin:14px 0 4px}
@media(max-width:760px){.vgrid{grid-template-columns:minmax(0,1fr)}}
.vbox{border:1.5px solid var(--cardline);border-radius:3px;padding:12px 14px;background:var(--card);min-width:0}
.vbox.dev{border-top:4px solid var(--s-lin)}.vbox.fin{border-top:4px solid var(--s-ok)}
.vbox h3{font:600 13px var(--sans);color:var(--slate);margin:0 0 2px}
.vbox .note{font-size:13px;color:var(--cardmuted);margin:0 0 8px}
dl.kv{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,1fr);gap:3px 12px;font-size:14px;align-items:baseline;margin:0}
dl.kv dt{color:var(--cardmuted)}dl.kv dd{margin:0;text-align:right;color:var(--cardink)}
@media(max-width:600px){dl.kv{grid-template-columns:minmax(0,1fr)}dl.kv dd{text-align:left;margin-bottom:4px}}
.crit{margin-top:12px;padding:10px 12px;border-left:3px solid var(--s-ok);background:var(--cardsoft);border-radius:2px;font-size:14.5px}
.crit b.ok{color:var(--s-ok)}
.plan{display:flex;flex-wrap:wrap;gap:4px;margin:8px 0 2px;counter-reset:pl}
.plan span{counter-increment:pl;font:600 11px var(--sans);border:1.5px solid var(--cardline);border-radius:3px;padding:3px 7px;color:var(--cardmuted);background:var(--card)}
.plan span::before{content:counter(pl) " ";opacity:.7}
.plan span.done{border-color:rgba(31,122,68,.45);color:var(--s-ok)}
.plan span.here{border-color:#B7791F;background:rgba(240,209,120,.45);color:var(--cardink)}
.verdict ul.limits{padding-left:20px}
.verdict .where,.verdict .links{font-size:14px;margin:8px 0 0}
.lecon{counter-reset:notion}
.notion{padding:24px 0 30px;border-top:1.5px dashed var(--line);max-width:960px}
.notion>h3{position:relative;padding-left:44px;font-family:var(--serif);font-weight:400;font-size:23px;line-height:1.3;color:var(--chalk);text-shadow:0 0 1px var(--dust);margin:0 0 4px}
.notion>h3 .ch-n{position:absolute;left:0;top:0;width:30px;height:30px;border-radius:50%;border:1.5px solid var(--ac,var(--yellow));color:var(--ac,var(--yellow));font:600 14px var(--sans);display:grid;place-items:center;text-shadow:none}
.tag{font:600 10.5px var(--sans);letter-spacing:.07em;text-transform:uppercase;border:1px solid currentColor;border-radius:3px;padding:1px 6px;margin-left:8px;vertical-align:middle;text-shadow:none;white-space:nowrap}
.tag.ok{color:var(--mint)}.tag.wait{color:var(--faint)}
.evrow{margin:2px 0 10px 44px;display:flex;flex-wrap:wrap;gap:6px}
.src{font-size:12.5px;color:var(--faint);margin:0 0 10px 44px}
.intro{margin:4px 0 14px 44px;max-width:74ch;font-family:var(--serif);font-size:16.5px;line-height:1.6;color:var(--chalk);text-shadow:0 0 1px var(--dust)}
.intro-k{display:block;font:600 .74rem var(--sans);letter-spacing:.08em;text-transform:uppercase;color:var(--yellow);text-shadow:none;margin-bottom:3px}
.intro p{margin:0}
.idee{margin-left:44px;color:var(--chalk);font-size:16px;line-height:1.65;max-width:74ch}
.idee p{margin:8px 0}
.idee b{color:var(--yellow);font-weight:600}
.terme{border-left:2px solid var(--ac,var(--yellow));padding:2px 0 2px 12px}
.terme dfn{font-family:var(--serif);font-style:normal;font-size:18px;color:var(--chalk);text-shadow:0 0 1px var(--dust);text-decoration:underline;text-decoration-color:var(--ac,var(--yellow));text-decoration-thickness:2px;text-underline-offset:4px}
.ici{color:var(--muted)}
.ici-k{font:600 10.5px var(--sans);letter-spacing:.08em;text-transform:uppercase;color:var(--faint)}
.ici q,.idee q{color:var(--chalk)}
.part{margin:0}
.choice{margin:14px 0 8px 44px;--ac:var(--ochre)}
.choice .card{margin:8px 0}
.choice .dec{font-family:var(--serif);font-size:17px;line-height:1.45;color:var(--cardink);margin:2px 0}
.choice .meta{display:flex;flex-wrap:wrap;gap:6px 10px;align-items:center;font-size:12.5px;color:var(--cardmuted);margin-top:4px}
article.decision{background:var(--card);color:var(--cardink);border-radius:3px;padding:14px 18px;box-shadow:0 10px 20px -14px rgba(0,0,0,.6);border-left:4px solid var(--ochre);margin:8px 0}
article.decision h3,article.decision h4{font:600 13px var(--sans);letter-spacing:.04em;color:var(--slate);margin:0 0 6px}
article.decision .choice-value{font-family:var(--serif);font-size:17px;line-height:1.45;color:var(--cardink);margin:2px 0 6px}
article.decision p{margin:4px 0}
.evidence{min-width:0}
.evidence>p.muted,.evidence>.card,.evidence>h4,.evidence>.src{margin-left:44px}
.evidence-block{min-width:0}
.diag-block>section.card{background:none;box-shadow:none;border:0;padding:0;margin:14px 0 0 44px;color:var(--chalk2)}
.diag-block>section.card>h3,.diag-block>section.card>h4{font-family:var(--serif);font-weight:400;font-size:19px;color:var(--chalk);margin:18px 0 6px}
.diag-block>section.card>div>p,.diag-block>section.card>p{max-width:76ch}
.diag-block>section.card .frame{margin-left:0}
.diag-block>section.card .notice{color:var(--chalk2);border-color:var(--yellow)}
.diag-block>section.card h4:not(.frame h4){color:var(--chalk)}
@media(max-width:600px){.diag-block>section.card{margin-left:0}}
details.f{margin:8px 0 0 44px;background:var(--card);color:var(--cardink);border-radius:3px;border-left:4px solid var(--ac,var(--yellow));box-shadow:0 10px 20px -16px rgba(0,0,0,.6)}
details.f>summary{cursor:pointer;list-style:none;padding:9px 14px;font:600 13.5px var(--sans);letter-spacing:.02em;color:var(--cardink)}
details.f>summary::-webkit-details-marker{display:none}
details.f>summary::before{content:"▸";display:inline-block;width:16px;color:var(--cardmuted)}
details.f[open]>summary::before{content:"▾"}
details.f>summary small{font-weight:400;color:var(--cardmuted);margin-left:6px;letter-spacing:0}
details.f .in{padding:2px 18px 14px;min-width:0}
details.f .in p,details.f .in li{font-size:15px;line-height:1.58;margin:5px 0}
details.f .in ol,details.f .in ul{padding-left:20px}
details.ex{--ac:var(--teal)}details.preuve{--ac:var(--violet)}details.code{--ac:var(--blue)}details.casse{--ac:var(--pink)}details.incert{--ac:var(--amber)}details.plus{--ac:var(--blue)}
.origin{font:600 10.5px var(--sans);letter-spacing:.06em;text-transform:uppercase;color:var(--cardmuted);margin:8px 0 2px}
pre.py{font:12.5px/1.6 var(--mono);background:var(--cardsoft);color:var(--cardink);border-radius:3px;padding:10px 12px;margin:6px 0;overflow-x:auto;white-space:pre;max-width:100%}
.garde{margin:16px 0 0 44px;font-family:var(--serif);font-size:16.5px;line-height:1.5;color:var(--chalk);text-shadow:0 0 1px var(--dust);border-left:3px solid var(--yellow);padding:4px 0 4px 14px;max-width:74ch}
.garde-k{display:block;font:600 10.5px var(--sans);letter-spacing:.08em;text-transform:uppercase;color:var(--faint);text-shadow:none;margin-bottom:2px}
.next{margin:14px 0 0 44px;max-width:74ch;font:14.5px/1.55 var(--sans);color:var(--chalk2);border-top:1px dashed var(--line);padding-top:10px}
.next b{color:var(--chalk);font-weight:600}
.next a{color:var(--yellow)}
.next .arr{color:var(--yellow);margin:0 4px}
.pq{background:var(--card);color:var(--cardink);border:1px solid var(--cardline);border-left:3px solid var(--ochre);border-radius:3px;padding:7px 11px 8px;margin:2px 0 10px;font:14px/1.5 var(--sans)}
.pq .k,.concl .k,.attn .k{display:block;font:600 10.5px var(--sans);letter-spacing:.08em;text-transform:uppercase;color:var(--ochre);margin-bottom:2px}
.pq p{margin:0}
.pq .fm{margin-top:5px;font-size:12.5px;color:var(--cardmuted)}
.pq .fm b{color:var(--cardink);font-weight:600}
.frame details.f.lire{margin:10px 0 0;box-shadow:none;border:1px solid var(--cardline);border-left:4px solid var(--slate)}
details.lire .in ol{padding-left:20px;margin:0}
details.lire .in li{font-size:14.5px;margin:3px 0}
.concl{margin-top:8px;background:var(--card);color:var(--cardink);border-left:3px solid var(--slate);border-radius:0 3px 3px 0;padding:6px 11px 7px;font-family:var(--serif);font-size:15.5px;line-height:1.5}
.concl .k{color:var(--slate)}
.concl p,.attn p{margin:0}
.attn{margin-top:8px;background:var(--card);color:var(--cardink);border:1.5px dashed var(--red);border-radius:3px;padding:6px 11px 7px;font-size:14px;line-height:1.5}
.attn .k{color:var(--red)}
.attn p+p{margin-top:6px}
details.plus dl{display:grid;grid-template-columns:minmax(0,15em) minmax(0,1fr);gap:5px 14px;margin:6px 0 4px;font-size:14.5px;line-height:1.5}
details.plus dt{font-weight:600}
details.plus dd{margin:0}
details.plus .stamp,details.plus .evb{white-space:normal}
details.plus h5{font:600 12px var(--sans);letter-spacing:.06em;text-transform:uppercase;color:var(--slate);margin:12px 0 2px}
.flush{margin-left:0!important}
.tbl,.scroll{overflow-x:auto;position:relative;-webkit-overflow-scrolling:touch;margin:8px 0;max-width:100%}
table{border-collapse:collapse;font:13.5px var(--sans);width:100%;background:var(--card);color:var(--cardink)}
th,td{border:1px solid var(--cardline);padding:5px 8px;text-align:left;vertical-align:top}
th{font:600 11px var(--sans);letter-spacing:.05em;text-transform:uppercase;color:var(--cardmuted);background:var(--cardsoft)}
td{font-variant-numeric:tabular-nums}
.frame h3,.frame h4,.frame h5,details.f h4,details.f h5,.card h3,.card h4{font:600 13px var(--sans);color:var(--slate);margin:12px 0 4px}
.frame h3 .badge{vertical-align:1px}
.frame p,.frame li{font-size:14px;line-height:1.5}
.frame details{border:1px solid var(--cardline);border-radius:3px;padding:6px 10px;margin:8px 0;background:var(--card)}
.frame details>summary{cursor:pointer;font:600 13px var(--sans)}
dl.facts{display:grid;grid-template-columns:minmax(0,220px) minmax(0,1fr);gap:4px 18px;margin:6px 0;font-size:14px}
dl.facts dt{color:var(--cardmuted)}dl.facts dd{margin:0}
dl.figures{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px 18px;max-width:640px;font-size:14px}
dl.figures dt{color:var(--cardmuted)}dl.figures dd{margin:0;text-align:right}
.scroll-hint{display:none}
@media(max-width:640px){dl.facts{grid-template-columns:minmax(0,1fr)}dl.facts dd{margin-bottom:8px}.scroll-hint{display:block}}
data{font-variant-numeric:tabular-nums;font-weight:650;border-bottom:1px dotted currentColor}
.small{font-size:12.5px;color:inherit;opacity:.85}
.muted{opacity:.8}
.notice{border:1.5px dashed var(--ochre);background:rgba(176,116,24,.07);border-radius:3px;padding:8px 12px;font-size:13.5px;margin:8px 0;color:inherit}
.notion>.notice{margin-left:44px;color:var(--chalk2);border-color:var(--yellow)}
.badge{display:inline-block;font:700 11px var(--sans);letter-spacing:.02em;border:1.5px solid currentColor;border-radius:2px;padding:1px 6px;margin-right:6px;vertical-align:middle;color:var(--s-ok)}
.badge.proposed,.badge.reconfirm_required,.badge.stale,.badge.failed,.badge.delegated,.badge.uncertain,.badge.not_met,.badge.not_assessed{color:var(--red);border-style:dashed}
.badge.met,.badge.done{color:var(--s-ok)}
.chip{display:inline-block;font:600 11px var(--sans);border-radius:10px;padding:0 8px;margin-right:6px;border:1px solid currentColor;color:var(--slate)}
.chip.automatic,.chip.delegated_default{color:var(--red);border-style:dashed}
.words{border-left:3px solid var(--ochre);padding:8px 12px;margin:8px 0;background:var(--cardsoft);border-radius:2px;font-size:14px}
.words.delegated{border-left-style:dashed;border-left-color:var(--red)}
.feedback{border:1px dashed var(--cardline);border-left:3px solid var(--ochre);border-radius:3px;padding:8px 12px;margin:8px 0;font-size:14px}
q[data-literal]{font-style:italic}
.term{font-weight:600}
.ev{display:inline-flex;gap:5px;align-items:baseline;font-size:11.5px;font-weight:650;border:1px solid currentColor;border-radius:10px;padding:0 7px;line-height:1.4;margin:0 4px 2px 0}
.ev.ev-final{color:var(--s-ok)}
.case-doubt{color:var(--red)}
.resume ol{padding-left:22px}.resume li{margin:6px 0}
.card.resume{--ac:var(--yellow)}.card.say-card{--ac:var(--teal)}
.phrase{font-family:var(--serif);font-size:17.5px;line-height:1.55;color:var(--chalk);text-shadow:0 0 1px var(--dust);background:var(--board2);border-left:2px solid var(--yellow);padding:10px 16px;margin:14px 0;max-width:80ch}
.phrase .k{display:block;font:600 10.5px var(--sans);letter-spacing:.08em;text-transform:uppercase;color:var(--faint);text-shadow:none}
.phrase p{margin:4px 0 0}
.verb{list-style:none;counter-reset:v;padding:0!important}
.verb li{counter-increment:v;display:grid;grid-template-columns:28px minmax(0,1fr);gap:4px 10px;padding:9px 0;border-top:1px solid var(--cardline)}
.verb li::before{content:counter(v);font:600 13px var(--sans);color:var(--cardmuted);grid-row:1 / span 2}
.verb .q{font-weight:600;grid-column:2}.verb .a{grid-column:2;color:var(--cardmuted)}
.verb .a.hid{filter:blur(6px);cursor:pointer;user-select:none}
.dec-list td:first-child{white-space:nowrap}
.annex-blk details.f{margin-left:0}
.annex-blk details.annex{margin:8px 0;background:var(--card);color:var(--cardink);border-radius:3px;padding:8px 14px;border-left:4px solid var(--blue)}
.annex-blk details.annex>summary{font:600 14px var(--sans);cursor:pointer}
.annex-blk details.annex details{border-top:1px dashed var(--cardline);padding:4px 0}
.annex-blk details.annex details>summary{font-size:13px;cursor:pointer}
.page-footer{margin-top:40px;color:var(--faint);font-size:13px;border-top:1.5px solid var(--line);padding-top:12px;line-height:1.6}
.understanding{--ac:var(--violet)}
.stale-banner{margin:0;border-radius:0;background:var(--card);color:var(--red);padding:10px 16px;border:2px solid var(--red)}
@media(max-width:600px){
.intro,.next,.idee,.frame,details.f,.garde,.src,.choice,.evrow,.evidence>p.muted,.evidence>.card,.evidence>h4,.evidence>.src,.notion>.notice{margin-left:0}
.notion>h3{font-size:20px}
.frame{padding:12px 10px 10px}
.card{padding:14px 14px}
.verdict .big{font-size:21px}
.posbar{font-size:12px}
.posbar .pos-left{overflow-x:auto;text-overflow:clip;scrollbar-width:none}
details.plus dl{grid-template-columns:minmax(0,1fr)}details.plus dd{margin-bottom:6px}}
@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important;scroll-behavior:auto!important}
.blk>h2::before,.lecon-h::before{filter:none}.verb .a.hid{filter:none;opacity:.35}}
@media print{.tools,.posbar,.side,.ledge{display:none}.wrap{display:block}body{padding-top:0}.ed{display:none}html[data-lang] .ed[data-ed]{display:none}html[data-lang="en"] .ed[data-ed="en"],html[data-lang="fr"] .ed[data-ed="fr"]{display:block}}
'''

# The script: the theme (dark by default, R28), the language (R27), the table of contents
# (open above 1040 px, the chapter being read), the position line (R30), the reading
# progress, the answers of "Say it out loud", and the annex anchors. No storage, no network,
# no prose: every word comes from the page.
SCRIPT = r'''(function(){"use strict";
var root=document.documentElement,body=document.body,tools=document.getElementById("tools");
var study=root.getAttribute("data-study-lang")||"en";
function lang(){return root.getAttribute("data-lang")||study;}
function ed(){return document.querySelector('.ed[data-ed="'+lang()+'"]');}
function base(id){return (id||"").replace(/--(en|fr)$/,"");}
function idIn(e,id){return e.getAttribute("data-ed")===study?id:id+"--"+e.getAttribute("data-ed");}
if(tools){tools.hidden=false;}
function syncTools(){if(tools){root.style.setProperty("--toolsw",Math.ceil(tools.getBoundingClientRect().width)+"px");}}
var theme=document.getElementById("themeBtn");
if(theme){theme.addEventListener("click",function(){var on=!body.classList.contains("white");body.classList.toggle("white",on);theme.setAttribute("aria-pressed",on?"true":"false");syncTools();});}
var langBtn=document.getElementById("langBtn");
function anchors(e){return [].slice.call(e.querySelectorAll("section[id],div.frame[id]"));}
function topAnchor(){var e=ed(),h=root.style.getPropertyValue("--posh")||58,best=null;anchors(e).forEach(function(n){var r=n.getBoundingClientRect();if(r.top<=parseFloat(h)+40){best=n;}});return best;}
function setLang(l){var a=topAnchor(),off=a?a.getBoundingClientRect().top:0;root.setAttribute("data-lang",l);root.lang=l;
var e=ed();if(e){document.title=e.getAttribute("data-title")||document.title;}
if(langBtn){langBtn.setAttribute("aria-pressed",l===study?"false":"true");langBtn.setAttribute("aria-label",langBtn.getAttribute("data-aria-"+l)||"");}
if(a&&e){var t=document.getElementById(idIn(e,base(a.id)));if(t){window.scrollTo(0,window.scrollY+t.getBoundingClientRect().top-off);}}
syncTools();track();}
if(langBtn){langBtn.addEventListener("click",function(){setLang(lang()===study?langBtn.getAttribute("data-other"):study);});}
window.addEventListener("resize",syncTools);syncTools();
var wide=window.matchMedia?window.matchMedia("(min-width: 1041px)"):null;
function syncToc(){[].slice.call(document.querySelectorAll(".side details.tocd")).forEach(function(d){d.open=!wide||wide.matches;});}
syncToc();if(wide&&wide.addEventListener){wide.addEventListener("change",syncToc);}
document.addEventListener("click",function(ev){var a=ev.target.closest&&ev.target.closest(".side a");if(a&&wide&&!wide.matches){var d=a.closest("details");if(d){d.open=false;var t=document.getElementById(a.getAttribute("href").slice(1));if(t){window.requestAnimationFrame(function(){t.scrollIntoView();});}}}});
function track(){var e=ed();if(!e){return;}var a=topAnchor();var sid=null;
var items=[].slice.call(e.querySelectorAll(".pos-item"));var keys=items.map(function(p){return p.getAttribute("data-for");});
var secs=[].slice.call(e.querySelectorAll("main section[id]")).filter(function(s){return keys.indexOf(base(s.id))>=0;});secs.forEach(function(s){if(s.getBoundingClientRect().top<=window.innerHeight*0.3){sid=s.id;}});
if(!sid&&secs.length){sid=secs[0].id;}
var key=base(sid);
items.forEach(function(p){p.hidden=p.getAttribute("data-for")!==key;});
if(!items.some(function(p){return !p.hidden;})&&items.length){items[0].hidden=false;}
[].slice.call(e.querySelectorAll(".side li")).forEach(function(li){var l=li.querySelector("a");var on=l&&base(l.getAttribute("href").slice(1))===key;li.classList.toggle("cur",!!on);if(l){if(on){l.setAttribute("aria-current","true");}else{l.removeAttribute("aria-current");}}});
var bar=e.querySelector(".readbar i");if(bar){var m=root.scrollHeight-root.clientHeight;bar.style.width=(m>0?Math.min(100,Math.round(100*root.scrollTop/m)):0)+"%";}}
var ticking=false;window.addEventListener("scroll",function(){if(!ticking){ticking=true;window.requestAnimationFrame(function(){ticking=false;track();});}},{passive:true});
window.addEventListener("hashchange",track);track();
[].slice.call(document.querySelectorAll(".verb .a")).forEach(function(a){function show(){a.classList.remove("hid");}a.addEventListener("click",show);a.addEventListener("keydown",function(ev){if(ev.key==="Enter"||ev.key===" "){show();}});});
function openHash(){var h=window.location.hash;if(!h){return;}var id=h.slice(1);var n=document.getElementById(id);
if(n&&n.closest&&n.closest(".ed")&&n.closest(".ed").getAttribute("data-ed")!==lang()){setLang(n.closest(".ed").getAttribute("data-ed"));}
if(base(id).indexOf("r-")===0&&n&&n.tagName==="DETAILS"){var p=n;while(p){if(p.tagName==="DETAILS"){p.open=true;}p=p.parentElement;}n.scrollIntoView();}}
openHash();window.addEventListener("hashchange",openHash);
function titled(ev){var d=ev.target&&ev.target.closest&&ev.target.closest("data[data-result-id],text[data-result-id]");if(d&&!d.getAttribute("title")){var t="result "+d.getAttribute("data-result-id")+" · "+d.getAttribute("data-path");d.setAttribute("title",t);if(d.tagName.toLowerCase()==="text"){var s=document.createElementNS(d.namespaceURI,"title");s.textContent=t;d.appendChild(s);}}}
document.addEventListener("mouseover",titled);document.addEventListener("focusin",titled);
})();'''
