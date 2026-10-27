"""The narrative report as a lesson (lot L6, R8, D14; v4: owner decision 2026-10-27, R25 to
R30; journey check J-REPORT).

Unit tests on the fixture study (``phase3_study``) and simulated browser tests (Playwright,
headless Chromium, network blocked); none of them is a Copilot or Claude Code acceptance
session. The cross-validated Bank and Auto MPG studies with an opened final test are checked
in ``test_report_and_notebook_real.py`` (development and final evidence, regression chapter
seven, ``check`` clean).

* "How to read this report" and the verdict come first, then the nine chapters in the order
  of the study, then the summary, the questions to say out loud and the appendix; the table
  of contents lists the same anchors, and each resolves.
* Every chapter is a lesson: "At this step", the term first then "In this study", the choice,
  the evidence, the folds (example, why it holds, code, where it breaks, what remains
  uncertain, learn more), what we keep, and the transition to the next chapter; each
  decision sits in the chapter of its step, and each result in the chapter that explains it.
* Every figure and table has its guided reading: why it is there with its frame, how to read
  it, and what we conclude.
* A chapter not reached says "not executed yet"; an open proposal, a stale result and a
  delegated decision show where they belong.
* The annex is compact (one cited value per result) and the report stays within a size
  budget; every number is still cited and ``check`` resolves it.
* Both languages are in the page (R27), the study language's edition first; a French study's
  edition writes its chapters and folds in French.
* Offline, at 390 and 1280 px, on the board and the whiteboard, in both languages: the table
  of contents is sticky on a wide screen and folded on a narrow one, the position line says
  where the reader is, the page never scrolls sideways, the board (dark) is the default
  whatever the system theme, and the page reads in the study language without script.
"""
from __future__ import annotations

import re
import warnings
from html.parser import HTMLParser

import pytest

from mlkit.study import cmd_render, manifest as mf, render_html, render_narrative as rn
from mlkit.study import texts, view

import phase3_study as fx
from lesson_page import editions, primary

CHAPTER_IDS = [f'ch{i}' for i in range(1, 10)]
PARTS = ('choice', 'evidence', 'why', 'uncertain')


class Outline(HTMLParser):
    """Sections, parts, decisions and evidence blocks with the chapter that holds them."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, str | None]] = []
        self.sections: list[str] = []
        self.parts: dict[str, list[str]] = {}
        self.decisions: dict[str, str] = {}
        self.evidence: dict[str, tuple[str, str]] = {}
        self.ids: set[str] = set()
        self.toc: list[list[str]] = []
        self._toc: list[str] | None = None
        self.labels: list[tuple[str, str]] = []
        self._label: str | None = None

    def chapter(self) -> str | None:
        for tag, cid in reversed(self.stack):
            if cid:
                return cid
        return None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get('id'):
            self.ids.add(a['id'])
        cid = None
        if tag == 'section' and 'chapter' in (a.get('class') or '').split():
            cid = a['id'].split('--')[0]
        if tag == 'section' and a.get('id') and not self.chapter():
            self.sections.append(a['id'])
        if a.get('data-part') and self.chapter():
            self.parts.setdefault(self.chapter(), []).append(a['data-part'])
        if tag == 'article' and a.get('data-decision'):
            self.decisions[a['data-decision']] = self.chapter()
        if a.get('data-for-slot') and self.chapter():
            self.evidence.setdefault(a['data-for-slot'],
                                     (self.chapter(), a.get('data-evidence-class')))
        if tag == 'ol' and (a.get('class') or '') in ('toc-a', 'toc-list', 'toc-b'):
            self._toc = []
        if tag == 'a' and self._toc is not None:
            self._toc.append(a.get('href', ''))
        if tag == 'summary' and self.stack and self.stack[-1][0] == 'details':
            self._label = (self.chapter() or '')
        if tag not in ('br', 'meta', 'circle', 'rect', 'line', 'img', 'input'):
            self.stack.append((tag, cid))

    def handle_endtag(self, tag):
        if tag == 'ol' and self._toc is not None:
            self.toc.append(self._toc)
            self._toc = None
        if tag == 'summary':
            self._label = None
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self._label is not None and data.strip():
            self.labels.append((self._label, data.strip()))
            self._label = None


def outline(page: str) -> Outline:
    o = Outline()
    o.feed(page)
    return o


def chapter_html(page: str, cid: str) -> str:
    """One chapter of the study-language edition."""
    first = primary(page)
    start = first.index(f'<section class="notion chapter" id="{cid}"')
    end = first.find('<section class="notion chapter"', start + 10)
    if end < 0:
        end = first.find('id="resume"', start)
    return first[start:end if end > 0 else len(first)]


@pytest.fixture
def full_view(full_study):
    return view.build(full_study)


def _chapter_of_step(task: str) -> dict:
    return rn.REGRESSION_STEP_CHAPTER if task == 'regression' else rn.STEP_CHAPTER


# --- order and table of contents -----------------------------------------------------------------

def test_the_verdict_comes_first_then_the_chapters_in_study_order_then_the_annex(full_view):
    page, _ = render_html.build(full_view)
    o = outline(primary(page))
    assert o.sections[:3] == ['prereq', 'verdict', 'lesson']
    assert [s for s in o.sections if re.fullmatch(r'ch\d|resume|voix|appendix', s)] == \
        CHAPTER_IDS + ['resume', 'voix', 'appendix']
    # the table of contents: the opening, the nine chapters, then what comes after
    assert len(o.toc) == 3
    assert o.toc[0] == ['#prereq', '#verdict']
    assert o.toc[1] == [f'#{c}' for c in CHAPTER_IDS]
    assert o.toc[2][-1] == '#appendix' and '#resume' in o.toc[2] and '#voix' in o.toc[2]
    for href in sum(o.toc, []):
        assert href[1:] in o.ids, href
    # every internal link of the page resolves, in both editions
    whole = outline(page)
    for href in set(re.findall(r'href="#([^"]+)"', page)):
        assert href in whole.ids, href
    # the chapter numbers are ordinals, never uncited numbers
    for i in range(1, 10):
        assert f'<span class="ch-n" aria-hidden="true"><span data-literal="ordinal">{i}</span>' \
            in page


def test_every_chapter_is_a_lesson(full_view):
    """R25, R29, R30: each chapter opens with "At this step", introduces its terms (the term
    first, then this study), holds the choice, the evidence and the folds, keeps one
    sentence, and ends with the transition to the next chapter."""
    page, _ = render_html.build(full_view)
    o = outline(primary(page))
    for cid in CHAPTER_IDS:
        parts = o.parts.get(cid, [])
        assert [p for p in parts if p in PARTS] == list(PARTS), (cid, parts)
        html = chapter_html(page, cid)
        assert html.count('<div class="intro">') == 1, cid
        assert '<p class="terme"' in html and '<dfn>' in html, cid
        for fold in ('ex', 'preuve', 'code', 'casse', 'incert'):
            assert f'<details class="f {fold}"' in html, (cid, fold)
        assert '<p class="next">' in html, cid
    # the term first, then "In this study" with the study's own figures
    ch1 = chapter_html(page, 'ch1')
    assert ch1.index('<p class="terme"') < ch1.index('<p class="ici">')
    assert '<data ' in ch1.split('<p class="ici">', 2)[2].split('</p>')[0] or \
        'data-literal="structure"' in ch1.split('<p class="ici">', 2)[2].split('</p>')[0]
    # what we keep, and each transition names the next chapter
    for i, cid in enumerate(CHAPTER_IDS[:-1]):
        html = chapter_html(page, cid)
        assert '<p class="garde">' in html, cid
        assert f'href="#{CHAPTER_IDS[i + 1]}"' in html.split('<p class="next">')[1], cid
    assert 'href="#resume"' in chapter_html(page, 'ch9').split('<p class="next">')[1]


def test_every_figure_has_its_guided_reading(full_view):
    """R30: every figure or table says why it is there, with its frame (evidence, rows,
    model), then how to read it step by step and what we conclude."""
    page, _ = render_html.build(full_view)
    for lang, fragment in editions(page).items():
        frames = re.split(r'(?=<div class="frame" id=)', fragment)[1:]
        assert len(frames) >= 12, (lang, len(frames))
        for frame in frames:
            head = frame[:frame.index('<div class="fbody">')]
            assert '<div class="pq">' in head and 'class="k"' in head, head[:200]
            assert '<details class="f lire" open>' in frame, head[:200]
        missing = [re.search(r'data-figure="([a-z_]+)"', f).group(1) for f in frames
                   if '<div class="concl">' not in f]
        assert missing == [], (lang, missing)


def test_every_chapter_holds_its_decision_and_evidence(full_view):
    """Each decision sits in the chapter of its step; each result in the chapter that
    explains it (the choice can be followed to its evidence without leaving the chapter)."""
    page, _ = render_html.build(full_view)
    o = outline(primary(page))
    task = full_view.get('task') or 'binary'
    mapping = _chapter_of_step(task)
    for step in full_view['plan']:
        if step['decision']:
            assert o.decisions.get(step['decision']) == mapping[step['id']], step['id']
    assert set(o.decisions) == set(full_view['decisions'])
    for slot in full_view['results']:
        want = rn._slot_chapter(slot, task)
        if want:
            assert o.evidence[slot][0] == want, slot
    # the confirmed words are shown with the decision, in its chapter
    pt = full_view['decisions']['prediction_time']['confirmation']['user_words']
    assert pt.replace("'", '&#x27;') in chapter_html(page, 'ch2')
    # the policy table is in the decision rule's chapter, with its paired differences
    ch7 = chapter_html(page, 'ch7')
    assert 'id="policy"' in ch7 and 'data-rule="capacity:20"' in ch7
    # the limits of the whole study are in the conclusion
    assert 'id="not-yet-defensible"' in chapter_html(page, 'ch9')


def test_evidence_says_which_rows_it_read(full_view):
    page, _ = render_html.build(full_view)
    o = outline(primary(page))
    for slot, (cid, kind) in o.evidence.items():
        item = full_view['results'].get(slot)
        if item and item['current']:
            assert kind in rn.EVIDENCE_CLASSES, (slot, kind)
            assert kind == rn.evidence_class(full_view, slot, item)
    looks = set(full_view['eda_looks']['results'])
    assert all(o.evidence[s][1] == 'development' for s, i in full_view['results'].items()
               if i['result_id'] in looks)
    lesson = texts.load('lesson')['ui']['evidence']
    for kind in rn.EVIDENCE_CLASSES:          # the legend names every class in words
        assert lesson[kind]['en'] in page and lesson[kind]['fr'] in page
    # nothing of the sealed final test is shown as evidence
    assert 'data-evidence-class="final"' not in page


# --- intermediate states ---------------------------------------------------------------------------

def test_a_chapter_not_reached_says_not_executed_yet(tmp_path, synthetic_case_dir):
    b = fx.build(tmp_path / 'study', synthetic_case_dir, upto='split')
    page, _ = render_html.build(view.build(b.study))
    words = texts.report()['narrative']
    status_words = texts.load('lesson')['ui']['status']
    statuses = dict(re.findall(r'<section class="notion chapter" id="(ch\d)" [^>]*'
                               r'data-status="([a-z_]+)"', primary(page)))
    assert statuses['ch1'] == statuses['ch2'] == 'done'
    for cid in ('ch4', 'ch6', 'ch7', 'ch9'):
        assert statuses[cid] == 'pending', cid
        assert words['pending_chapter'] in chapter_html(page, cid)
        assert status_words['pending']['en'] in chapter_html(page, cid)
    # the table of contents says so in words too (not by a glyph alone)
    toc = primary(page).split('<aside class="side"')[1].split('</aside>')[0]
    assert f'<span class="sr">{status_words["pending"]["en"]}</span>' in toc
    # R26: a chapter whose steps are done never says "not executed yet" in its evidence
    assert words['pending_chapter'] not in chapter_html(page, 'ch2')


def test_chapter_four_checks_the_structure_before_the_target(tmp_path, synthetic_case_dir):
    """Wave W2 integration (L5 in L6): in a structural-first study, chapter four explains the
    structural check (``structural_eda``: ``eda.quality``) before the looks at the target, its
    evidence labelled structural before the development evidence of the looks; before the
    check has run, its quality evidence is announced as pending."""
    import flowkit as fk
    early = fx.build(tmp_path / 'early', synthetic_case_dir, upto='split')
    ch4 = chapter_html(render_html.build(view.build(early.study))[0], 'ch4')
    assert 'data-step="structural_eda"' in ch4
    assert re.search(r'data-evidence-class="pending" data-for-slot="eda\.quality"', ch4)
    f = fk.Flow(tmp_path / 'study', synthetic_case_dir, prefix='n')
    f.init()
    for _ in range(40):
        nxt = f.view()['next_action']
        if nxt['kind'] == 'run' and nxt['activity'].startswith('fit.'):
            break
        if nxt['kind'] == 'show_data_card':
            nxt = {'kind': 'propose', 'decision': 'prediction_time',
                   'default_value': 'when the record is created, before the outcome'}
        if nxt['kind'] == 'run':
            options = [x for k, v in (nxt.get('options') or {}).items()
                       for x in (f'--{k}', str(v))]
            f.run(nxt['activity'], *options)
        else:
            assert nxt['kind'] == 'propose', nxt
            value = nxt.get('default_value')
            if value is None:
                value = (nxt.get('recommended') or {}).get('value')
            f.decide(nxt['decision'], value)
    v = view.build(f.study)
    ids = [s['id'] for s in v['plan']]
    assert ids.index('structural_eda') < ids.index('preprocessing') < ids.index('train_eda')
    ch4 = chapter_html(render_html.build(v)[0], 'ch4')
    steps = re.findall(r'data-step="([a-z_]+)"', ch4)
    assert steps.index('structural_eda') < steps.index('train_eda')
    blocks = re.findall(r'data-evidence-class="([a-z]+)" data-for-slot="([^"]+)"', ch4)
    assert blocks[0] == ('structural', 'eda.quality'), blocks
    assert ('development', 'eda.target_rate') in blocks
    classes = [cls for cls, _ in blocks]
    assert classes.index('development') > max(i for i, c in enumerate(classes)
                                              if c == 'structural')


def test_an_open_proposal_a_stale_result_and_a_delegation_show_where_they_belong(
        tmp_path, synthetic_case_dir):
    b = fx.build(tmp_path / 'study', synthetic_case_dir, upto='models',
                 standing_delegation='Choose for me, I trust your defaults.')
    b.decide('model_choice', 'fit.logistic', 'Retain fit.logistic for the rule.',
             'I retain fit.logistic because it fits the study.')
    b.apply('decide.propose', {'decision_id': 'policy', 'value': 'capacity:20',
                               'restatement': 'Call the 20 highest-scored members.',
                               'rationale': 'Desk capacity.'})
    v = view.build(b.study)
    stale = v['results']['fit.logistic']['result_id']
    v['results']['fit.logistic']['current'] = False
    v['results']['fit.logistic']['stale_reason'] = {'reason': 'split changed', 'since': 99}
    page, consumed = render_html.build(v)
    ch7 = chapter_html(page, 'ch7')
    assert 'data-proposal=' in ch7 and 'data-decision="policy" data-status="proposed"' in ch7
    assert 'data-status="in_progress"' in ch7[:200]
    ch6 = chapter_html(page, 'ch6')
    assert 'data-for-slot="fit.logistic"' in ch6
    assert 'data-evidence-class="stale" data-for-slot="fit.logistic"' in ch6
    assert stale not in consumed and f'data-result-id="{stale}"' not in page
    ch2 = chapter_html(page, 'ch2')
    assert 'data-decision="prediction_time"' in ch2
    assert 'data-basis-chip="delegated_default"' in ch2


# --- annex, size, citations ---------------------------------------------------------------------

# v4 (R27): two editions, each a lesson with guided readings (the fixture study: about 520 kB;
# a single English edition was about 170 kB at L6).
BUDGET_BYTES = 650_000


def test_the_annex_is_compact_and_every_current_result_is_still_cited(full_view):
    page, consumed = render_html.build(full_view)
    assert len(page.encode('utf-8')) <= BUDGET_BYTES
    current = {r['result_id'] for r in full_view['results'].values() if r['current']}
    assert set(consumed) == current
    for lang, fragment in editions(page).items():
        suffix = '' if lang == 'en' else '--fr'
        annex = fragment.split(f'<details class="annex" id="annex{suffix}">')[1].split(
            '<details class="f annex-part"')[0]
        # one cited value per result in the annex (rows read, or its first number), never
        # the whole registry entry
        assert annex.count('<data ') <= len(full_view['results'])
        for rid in current:
            assert fragment.count(f'id="r-{rid}{suffix}"') == 1
            assert f'hypotrail evidence --result {rid}' in fragment
    for rid in current:                 # the anchor of the first edition is the plain one
        assert page.count(f'id="r-{rid}"') == 1


def test_the_annex_follows_every_number_of_the_report(full_study):
    """``hypotrail check`` still resolves every cited number of the rendered report."""
    from mlkit.study import cmd_check
    cmd_render.render_all(full_study)
    result = cmd_check.run_check(full_study)
    assert result['clean'], result['findings']


# --- language -----------------------------------------------------------------------------------

def test_a_french_report_writes_its_chapters_and_parts_in_french(full_view):
    page, _ = render_html.build(dict(full_view, language='fr'))
    assert re.search(r'<html lang="fr" data-lang="fr" data-study-lang="fr">', page)
    fr_page = editions(page)
    assert list(fr_page) == ['fr', 'en']           # the study language first
    fr_text, en_text = fr_page['fr'], fr_page['en']
    fr = texts.load('report_fr')['narrative']
    en = texts.load('report')['narrative']
    lesson = texts.load('lesson')['ui']
    for cid in CHAPTER_IDS:
        assert f'{fr["chapters"][cid]["title"]} '.replace("'", '&#x27;') in fr_text
        assert f'{en["chapters"][cid]["title"]} '.replace("'", '&#x27;') in en_text
    for fold in ('example', 'why', 'code', 'breaks', 'uncertain'):
        assert f'<summary>{lesson["fold"][fold]["fr"]}'.replace("'", '&#x27;') in fr_text
        assert f'<summary>{lesson["fold"][fold]["en"]}' in en_text
        if lesson['fold'][fold]['en'] != lesson['fold'][fold]['fr']:      # "Code" is both
            assert f'<summary>{lesson["fold"][fold]["en"]}<' not in fr_text
    assert lesson['contents']['fr'] in fr_text and lesson['contents']['en'] not in fr_text
    assert lesson['at_step']['fr'] in fr_text and lesson['at_step']['en'] not in fr_text


def test_a_regression_study_calls_chapter_seven_the_model_choice():
    with texts.task_context('regression'):
        title = texts.report()['narrative']['chapters']['ch7']['title']
    with texts.task_context('binary'):
        assert texts.report()['narrative']['chapters']['ch7']['title'] != title
    assert rn.REGRESSION_STEP_CHAPTER['model_choice'] == 'ch7'
    assert rn.STEP_CHAPTER['model_choice'] == 'ch6'


# --- browser (simulated, offline) ---------------------------------------------------------------

try:
    import playwright.sync_api as _sync_api
except ImportError:                                   # pragma: no cover - the full gate has it
    _sync_api = None


@pytest.fixture(scope='module')
def browser():
    if _sync_api is None:
        warnings.warn('Playwright is not installed: the narrative report browser checks did '
                      'not run (uv sync --group browser).', pytest.PytestWarning, stacklevel=1)
        pytest.skip('Playwright is not installed')
    from test_html_offline import _chromium
    with _sync_api.sync_playwright() as p:
        b = _chromium(p)
        yield b
        b.close()


def _page(browser, path, width, height=900, scheme='light', script=True):
    context = browser.new_context(offline=True, viewport={'width': width, 'height': height},
                                  color_scheme=scheme, java_script_enabled=script,
                                  reduced_motion='reduce')
    requests, errors = [], []
    context.route('**/*', lambda route: route.continue_() if route.request.url.startswith('file:')
                  else (requests.append(route.request.url), route.abort()))
    page = context.new_page()
    page.on('pageerror', lambda exc: errors.append(str(exc)))
    page.goto(path.resolve().as_uri())
    page.wait_for_load_state('load')
    return context, page, requests, errors

@pytest.fixture
def report(full_study):
    cmd_render.render_all(full_study)
    return full_study / mf.ARTIFACTS['report']


def _background(page) -> int:
    colour = page.evaluate('getComputedStyle(document.body).backgroundColor')
    return sum(int(x) for x in re.findall(r'\d+', colour)[:3])


@pytest.mark.parametrize('lang', ['study', 'other'])
@pytest.mark.parametrize('theme', ['board', 'whiteboard'])
@pytest.mark.parametrize('width', [390, 1280])
def test_no_horizontal_overflow(browser, report, width, theme, lang):
    context, page, requests, errors = _page(browser, report, width)
    try:
        assert requests == [] and errors == []
        if theme == 'whiteboard':
            page.click('#themeBtn')
        if lang == 'other':
            page.click('#langBtn')
        assert page.evaluate('document.documentElement.scrollWidth') <= width
        # no chapter, frame, card or fold is wider than the page; wide tables and charts
        # scroll inside their own frames
        wide = page.evaluate('''w => [...document.querySelectorAll(
            '.notion, .frame, .card, details.f, .verdict, .side, .posbar, .pq, .concl, .attn')]
            .filter(n => n.offsetParent !== null && n.getBoundingClientRect().right > w + 1)
            .map(n => n.id || n.className)''', width)
        assert wide == []
    finally:
        context.close()


def test_the_table_of_contents_is_sticky_and_its_anchors_work_offline(browser, report):
    context, page, requests, errors = _page(browser, report, 1280)
    try:
        side = page.locator('.ed[data-ed="en"] aside.side')
        assert side.is_visible()
        assert page.locator('.ed[data-ed="en"] aside.side details').get_attribute('open') \
            is not None
        hrefs = side.locator('a').evaluate_all('ns => ns.map(n => n.getAttribute("href"))')
        assert hrefs[:2] == ['#prereq', '#verdict'] and hrefs[-1] == '#appendix'
        for href in hrefs:
            assert page.locator(href).count() == 1, href
        # "How to read this report" and the verdict are the first things the page shows
        top = page.evaluate('''() => [...document.querySelectorAll(
            '.ed[data-ed="en"] main > section')].map(n => n.id)''')
        assert top[:2] == ['prereq', 'verdict']
        side.locator('a[href="#ch7"]').click()
        page.wait_for_function('window.location.hash === "#ch7"')
        posh = page.evaluate('parseFloat(getComputedStyle(document.documentElement)'
                             '.getPropertyValue("--posh"))')
        box = page.locator('#ch7').bounding_box()
        assert posh - 2 <= box['y'] <= posh + 40, box
        # sticky: after the jump the table of contents is still in view, under the line
        side_box = side.bounding_box()
        assert side_box['y'] <= posh + 20 and side.is_visible()
        # the chapter being read is marked (a marker and the weight, not colour alone)
        page.wait_for_function(
            'document.querySelector(\'.ed[data-ed="en"] .side a[href="#ch7"]\')'
            '.getAttribute("aria-current") === "true"')
        # the position line names the chapter and what remains (R30)
        line = page.locator('.ed[data-ed="en"] .posbar .pos-item:not([hidden])')
        assert line.count() == 1
        assert line.get_attribute('data-for') == 'ch7'
        text = line.inner_text()
        assert 'Chapter 7/9' in text and 'remaining' in text
        page.evaluate('window.scrollTo(0, document.documentElement.scrollHeight)')
        assert page.locator('.ed[data-ed="en"] .posbar').bounding_box()['y'] == 0
        assert requests == [] and errors == []
    finally:
        context.close()


def test_a_narrow_screen_folds_the_table_of_contents(browser, report):
    context, page, requests, errors = _page(browser, report, 390)
    try:
        toc = page.locator('.ed[data-ed="en"] aside.side details')
        assert toc.get_attribute('open') is None              # folded by default
        toc.locator('summary').click()
        assert toc.get_attribute('open') is not None
        toc.locator('a[href="#ch4"]').click()
        page.wait_for_function('window.location.hash === "#ch4"')
        assert toc.get_attribute('open') is None              # it folds after a choice
        assert page.locator('#ch4').bounding_box()['y'] < 120
        assert requests == [] and errors == []
    finally:
        context.close()


def test_the_page_reads_without_script_on_the_board_in_the_study_language(browser, report):
    """R28: the board (dark) is the default whatever the system theme; without script the
    study language's edition alone is shown, and the buttons that need the script are
    hidden."""
    for scheme in ('light', 'dark'):
        context, page, requests, errors = _page(browser, report, 1280, scheme=scheme,
                                                script=False)
        try:
            assert requests == []
            assert _background(page) < 200, scheme             # the slate board
            assert not page.locator('#tools').is_visible()
            assert page.locator('.ed[data-ed="en"]').is_visible()
            assert not page.locator('.ed[data-ed="fr"]').is_visible()
            # the content does not need the script: every chapter and the appendix are there
            for cid in ['prereq', 'verdict'] + CHAPTER_IDS + ['appendix']:
                assert page.locator(f'#{cid}').is_visible(), cid
        finally:
            context.close()
    # with the script, still the board by default; the whiteboard is a session choice
    context, page, requests, errors = _page(browser, report, 1280, scheme='light')
    try:
        assert _background(page) < 200
        page.click('button[data-theme-toggle]')
        assert 'white' in page.locator('body').get_attribute('class')
        assert page.get_attribute('button[data-theme-toggle]', 'aria-pressed') == 'true'
        assert _background(page) > 600
        assert errors == []
    finally:
        context.close()


def test_the_language_button_switches_the_whole_page_and_keeps_the_place(browser, report):
    """R27: one file, both languages; the button switches every text for the visit, keeps
    the reader's place, and switches back."""
    context, page, requests, errors = _page(browser, report, 1280)
    try:
        assert page.evaluate('document.documentElement.lang') == 'en'
        title_en = page.title()
        page.evaluate('document.getElementById("ch6").scrollIntoView()')
        before = page.locator('#ch6').bounding_box()['y']
        page.click('#langBtn')
        assert page.evaluate('document.documentElement.lang') == 'fr'
        assert page.locator('.ed[data-ed="fr"]').is_visible()
        assert not page.locator('.ed[data-ed="en"]').is_visible()
        assert page.title() != title_en
        assert page.get_attribute('#langBtn', 'aria-pressed') == 'true'
        # the place is kept: the French chapter six is where the English one was
        box = page.locator('#ch6--fr').bounding_box()
        assert abs(box['y'] - before) < 2, (box, before)
        fr = texts.load('report_fr')['narrative']['chapters']['ch6']['title']
        assert fr in page.locator('#ch6--fr').inner_text()
        page.click('#langBtn')
        assert page.evaluate('document.documentElement.lang') == 'en'
        assert page.locator('#ch6').is_visible()
        assert requests == [] and errors == []
    finally:
        context.close()
