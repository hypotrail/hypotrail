"""The narrative report (lot L6, remark R8, owner decision D14; journey check J-REPORT).

Unit tests on the fixture study (``phase3_study``) and simulated browser tests (Playwright,
headless Chromium, network blocked); none of them is a Copilot or Claude Code acceptance
session. The cross-validated Bank and Auto MPG studies with an opened final test are checked
in ``test_report_and_notebook_real.py`` (development and final evidence, regression chapter
seven, ``check`` clean).

* The verdict comes first, then the nine chapters in the order of the study, then the
  annex; the table of contents lists the same anchors, and each resolves.
* Every chapter holds the choice, why, the evidence, and what remains uncertain; each
  decision sits in the chapter of its step, and each result in the chapter that explains it.
* A chapter not reached says "not executed yet"; an open proposal, a stale result and a
  delegated decision show where they belong.
* The annex is compact (one cited value per result) and the report stays within a size
  budget; every number is still cited and ``check`` resolves it.
* A French report writes its chapter titles and part labels in French.
* Offline, at 420 and 1280 px, light and dark: the table of contents is sticky on a wide
  screen and a top menu on a narrow one, the page never scrolls sideways, and the page
  follows the system theme even without script.
"""
from __future__ import annotations

import re
import warnings
from html.parser import HTMLParser

import pytest

from mlkit.study import cmd_render, manifest as mf, render_html, render_narrative as rn
from mlkit.study import texts, view

import phase3_study as fx

CHAPTER_IDS = [f'ch{i}' for i in range(1, 10)]
PARTS = ('choice', 'why', 'evidence', 'uncertain')


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
            cid = a['id']
        if tag == 'section' and a.get('id') and not self.chapter():
            self.sections.append(a['id'])
        if a.get('data-part') and self.chapter():
            self.parts.setdefault(self.chapter(), []).append(a['data-part'])
            self._label = a['data-part']
        if tag == 'article' and a.get('data-decision'):
            self.decisions[a['data-decision']] = self.chapter()
        if a.get('data-for-slot'):
            self.evidence.setdefault(a['data-for-slot'],
                                     (self.chapter(), a.get('data-evidence-class')))
        if tag == 'ol' and 'toc-list' in (a.get('class') or ''):
            self._toc = []
        if tag == 'a' and self._toc is not None:
            self._toc.append(a.get('href', ''))
        if tag not in ('br', 'meta', 'circle', 'rect', 'line', 'img', 'input'):
            self.stack.append((tag, cid))

    def handle_endtag(self, tag):
        if tag == 'ol' and self._toc is not None:
            self.toc.append(self._toc)
            self._toc = None
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self._label and data.strip() and data.strip() != '?':
            self.labels.append((self._label, data.strip()))
            self._label = None


def outline(page: str) -> Outline:
    o = Outline()
    o.feed(page)
    return o


def chapter_html(page: str, cid: str) -> str:
    start = page.index(f'<section class="card chapter" id="{cid}"')
    end = page.find('<section class="card chapter', start + 10)
    return page[start:end if end > 0 else len(page)]


@pytest.fixture
def full_view(full_study):
    return view.build(full_study)


def _chapter_of_step(task: str) -> dict:
    return rn.REGRESSION_STEP_CHAPTER if task == 'regression' else rn.STEP_CHAPTER


# --- order and table of contents -----------------------------------------------------------------

def test_the_verdict_comes_first_then_the_chapters_in_study_order_then_the_annex(full_view):
    page, _ = render_html.build(full_view)
    o = outline(page)
    assert o.sections[:2] == ['verdict', 'howto']
    assert [s for s in o.sections if s.startswith('ch') or s == 'appendix'] == \
        CHAPTER_IDS + ['appendix']
    assert o.sections[-1] == 'appendix'
    # two copies of the same table of contents: the top menu and the side table
    assert len(o.toc) == 2 and o.toc[0] == o.toc[1]
    assert o.toc[0] == ['#verdict'] + [f'#{c}' for c in CHAPTER_IDS] + ['#appendix']
    for href in o.toc[0]:
        assert href[1:] in o.ids, href
    # every internal link of the page resolves
    for href in set(re.findall(r'href="#([^"]+)"', page)):
        assert href in o.ids, href
    # the chapter numbers are ordinals, never uncited numbers
    for i in range(1, 10):
        assert f'<span class="ch-num"><span data-literal="ordinal">{i}</span></span>' in page


def test_every_chapter_holds_the_choice_why_the_evidence_and_what_remains_uncertain(full_view):
    page, _ = render_html.build(full_view)
    o = outline(page)
    for cid in CHAPTER_IDS:
        parts = o.parts.get(cid, [])
        assert [p for p in parts if p in PARTS] == list(PARTS), (cid, parts)
    labels = texts.report()['narrative']['parts']
    assert {label for _, label in o.labels} >= {labels[p] for p in PARTS}


def test_every_chapter_holds_its_decision_and_evidence(full_view):
    """Each decision sits in the chapter of its step; each result in the chapter that
    explains it (the choice can be followed to its evidence without leaving the chapter)."""
    page, _ = render_html.build(full_view)
    o = outline(page)
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
    o = outline(page)
    words = texts.report()['narrative']['evidence_class']
    for slot, (cid, kind) in o.evidence.items():
        item = full_view['results'].get(slot)
        if item and item['current']:
            assert kind in rn.EVIDENCE_CLASSES, (slot, kind)
            assert kind == rn.evidence_class(full_view, slot, item)
    looks = set(full_view['eda_looks']['results'])
    assert all(o.evidence[s][1] == 'development' for s, i in full_view['results'].items()
               if i['result_id'] in looks)
    for kind in rn.EVIDENCE_CLASSES:          # the legend names every class in words
        assert words[kind] in page
    # nothing of the sealed final test is shown as evidence
    assert 'data-evidence-class="final"' not in page


# --- intermediate states ---------------------------------------------------------------------------

def test_a_chapter_not_reached_says_not_executed_yet(tmp_path, synthetic_case_dir):
    b = fx.build(tmp_path / 'study', synthetic_case_dir, upto='split')
    page, _ = render_html.build(view.build(b.study))
    words = texts.report()['narrative']
    statuses = dict(re.findall(r'<section class="card chapter" id="(ch\d)" [^>]*'
                               r'data-status="([a-z_]+)"', page))
    assert statuses['ch1'] == statuses['ch2'] == 'done'
    for cid in ('ch4', 'ch6', 'ch7', 'ch9'):
        assert statuses[cid] == 'pending', cid
        assert words['pending_chapter'] in chapter_html(page, cid)
        assert words['chapter_status']['pending'] in chapter_html(page, cid)
    # the table of contents says so in words too (not by a glyph alone)
    toc = page.split('<nav class="toc"')[1].split('</nav>')[0]
    assert f'<span class="sr">{words["chapter_status"]["pending"]}</span>' in toc


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

BUDGET_BYTES = 300_000      # the fixture study (about 170 kB at L6; 207 kB before)


def test_the_annex_is_compact_and_every_current_result_is_still_cited(full_view):
    page, consumed = render_html.build(full_view)
    assert len(page.encode('utf-8')) <= BUDGET_BYTES
    annex = page.split('<details class="annex" id="annex">')[1].split(
        '<details class="annex-part"')[0]
    current = {r['result_id'] for r in full_view['results'].values() if r['current']}
    # one cited value per result in the annex (rows read, or its first number), never the
    # whole registry entry
    assert annex.count('<data ') <= len(full_view['results'])
    assert set(consumed) == current
    for rid in current:
        assert page.count(f'id="r-{rid}"') == 1
        assert f'hypotrail evidence --result {rid}' in page


def test_the_annex_follows_every_number_of_the_report(full_study):
    """``hypotrail check`` still resolves every cited number of the rendered report."""
    from mlkit.study import cmd_check
    cmd_render.render_all(full_study)
    result = cmd_check.run_check(full_study)
    assert result['clean'], result['findings']


# --- language -----------------------------------------------------------------------------------

def test_a_french_report_writes_its_chapters_and_parts_in_french(full_view):
    page, _ = render_html.build(dict(full_view, language='fr'))
    o = outline(page)
    fr = texts.load('report_fr')['narrative']
    en = texts.load('report')['narrative']
    for cid in CHAPTER_IDS:
        assert f'>{fr["chapters"][cid]["title"]}</h2>'.replace("'", '&#x27;') in page
    assert {label for _, label in o.labels} == {fr['parts'][p] for p in PARTS}
    assert fr['contents'] in page and en['contents'] not in page
    for p in PARTS:
        assert f'>{en["parts"][p]}</p>' not in page


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
                                  color_scheme=scheme, java_script_enabled=script)
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


@pytest.mark.parametrize('scheme', ['light', 'dark'])
@pytest.mark.parametrize('width', [420, 1280])
def test_no_horizontal_overflow(browser, report, width, scheme):
    context, page, requests, errors = _page(browser, report, width, scheme=scheme)
    try:
        assert requests == [] and errors == []
        assert page.evaluate('document.documentElement.scrollWidth') <= width
        # no chapter, part or evidence block is wider than the page
        wide = page.evaluate('''w => [...document.querySelectorAll(
            '.chapter, .part, .evidence-block, .verdict, .toc, .toc-mobile')]
            .filter(n => n.getBoundingClientRect().right > w + 1).map(n => n.id || n.className)''',
                             width)
        assert wide == []
    finally:
        context.close()


def test_the_table_of_contents_is_sticky_and_its_anchors_work_offline(browser, report):
    context, page, requests, errors = _page(browser, report, 1280)
    try:
        nav = page.locator('nav.toc')
        assert nav.is_visible() and not page.locator('details.toc-mobile').is_visible()
        hrefs = nav.locator('a').evaluate_all('ns => ns.map(n => n.getAttribute("href"))')
        assert hrefs[0] == '#verdict' and hrefs[-1] == '#appendix'
        for href in hrefs:
            assert page.locator(href).count() == 1, href
        # the verdict is the first thing the page shows
        top = page.evaluate('''() => [...document.querySelectorAll("main > section")]
            .map(n => n.id)''')
        assert top[0] == 'verdict'
        page.evaluate('document.documentElement.style.scrollBehavior = "auto"')
        nav.locator('a[href="#ch7"]').click()
        page.wait_for_function('window.location.hash === "#ch7"')
        box = page.locator('#ch7').bounding_box()
        assert -2 <= box['y'] <= 40, box
        # sticky: after the jump the table of contents is still at the top of the viewport
        nav_box = nav.bounding_box()
        assert nav_box['y'] <= 1 and nav.is_visible()
        # the chapter being read is marked (marker and weight, not colour alone)
        page.wait_for_function(
            'document.querySelector(\'nav.toc a[href="#ch7"]\').getAttribute("aria-current")'
            ' === "true"')
        page.evaluate('window.scrollTo(0, document.documentElement.scrollHeight)')
        assert nav.bounding_box()['y'] <= 1
        assert requests == [] and errors == []
    finally:
        context.close()


def test_a_narrow_screen_folds_the_table_of_contents_into_a_top_menu(browser, report):
    context, page, requests, errors = _page(browser, report, 420)
    try:
        menu = page.locator('details.toc-mobile')
        assert menu.is_visible() and not page.locator('nav.toc').is_visible()
        menu.locator('summary').click()
        assert menu.get_attribute('open') is not None
        page.evaluate('document.documentElement.style.scrollBehavior = "auto"')
        menu.locator('a[href="#ch4"]').click()
        page.wait_for_function('window.location.hash === "#ch4"')
        assert menu.get_attribute('open') is None             # the menu closes after a choice
        assert menu.bounding_box()['y'] <= 1                  # and stays at the top
        assert requests == [] and errors == []
    finally:
        context.close()


def test_the_page_reads_without_script_and_follows_the_system_theme(browser, report):
    for scheme, dark in (('light', False), ('dark', True)):
        context, page, requests, errors = _page(browser, report, 1280, scheme=scheme,
                                                script=False)
        try:
            assert requests == []
            colour = page.evaluate('getComputedStyle(document.body).backgroundColor')
            rgb = [int(x) for x in re.findall(r'\d+', colour)[:3]]
            assert (sum(rgb) < 200) is dark, (scheme, colour)
            # the content does not need the script: every chapter and the annex are there
            for cid in CHAPTER_IDS + ['appendix']:
                assert page.locator(f'#{cid}').is_visible()
        finally:
            context.close()
    # with the script, an explicit choice wins over the system theme
    context, page, requests, errors = _page(browser, report, 1280, scheme='dark')
    try:
        page.click('button[data-theme-toggle]')
        assert 'light' in page.locator('body').get_attribute('class')
        colour = page.evaluate('getComputedStyle(document.body).backgroundColor')
        assert sum(int(x) for x in re.findall(r'\d+', colour)[:3]) > 600
        assert errors == []
    finally:
        context.close()
