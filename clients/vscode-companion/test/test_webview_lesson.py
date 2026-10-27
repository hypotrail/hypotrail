"""Browser tests of the lesson-style panel (scope S, simulated browser; owner-approved mockup
docs/plans/mockups/panel-lesson-style-fr.html, notes R27-R30 of
docs/acceptance/runs/copilot-companion-2026-10-26.md, owner decision 2026-10-27).

On the captured payloads of the real engine (``panel_cases.py``), in English and in French:

* R30: the journey rail above the tabs (one mark per plan step, one current step, the moments
  of the engine), what remains, and the sticky position line under the tabs;
* R29: "At this step" at the top of every tab, and the "Next" line at its end, which leads to
  the next tab;
* R30: every chart says why it is there and how to read it (the question, the frame of the
  evidence, the steps, the conclusion with the chart's own figures, the trap), and the
  notions put the term first, then the study's own values;
* "Learn more" for the marks of the header and the abbreviations of the evidence;
* the next move has one action, "Copy the question", which writes nothing;
* the VS Code theme class picks the board (dark), the white board (light) or the editor's own
  high-contrast colours, without a theme button of the panel's own.

COMPANION-ADVANCED §6.0, LS-1 to LS-6.

This is not a VS Code session.
"""
from __future__ import annotations

import pytest

from conftest import inline_styles_ok
from panel_cases import TABS, load_views, open_case


@pytest.fixture(scope='module')
def views(model, payload):
    return load_views(model, payload)


def clean(panel):
    assert not (panel.requests or panel.errors or panel.csp or panel.violations()), \
        (panel.requests, panel.errors, panel.csp, panel.violations())
    assert inline_styles_ok(panel.page)


@pytest.mark.parametrize('case', ['binary', 'regression'])
def test_ls1_r30_the_rail_what_remains_and_the_sticky_position_line(open_panel, views, case):
    summary = views[f'summary.{case}']
    panel = open_case(open_panel, views, case=case)
    page = panel.page
    rail = page.locator('[data-band] nav[data-rail="full"]')
    assert rail.count() == 1
    steps = rail.locator('[data-rail-step]').evaluate_all('ss => ss.map(s => s.dataset.railStep)')
    assert steps == [s['id'] for s in summary['plan']], 'one mark per plan step, in plan order'
    current = rail.locator('[data-rail-state="cur"]')
    assert current.count() == 1
    # Never colour alone: every mark has its words (hover and screen readers).
    for mark in rail.locator('[data-rail-step]').all()[:3]:
        assert ':' in mark.locator('.sr-only').inner_text() and mark.get_attribute('title')
    moments = [m['id'] for m in summary.get('moments') or []]
    if moments:
        assert rail.locator('[data-moment]').evaluate_all('ms => ms.map(m => m.dataset.moment)') == moments
    remain = page.locator('[data-remain]')
    assert remain.inner_text().startswith('Still to do')
    where = page.locator('[data-where]')
    assert where.get_attribute('data-where') == 'overview'
    assert where.evaluate('w => getComputedStyle(w).position') == 'sticky'
    title = current.get_attribute('title').split(' · ')[0]
    assert title in where.inner_text() and 'tab Overview' in where.inner_text()
    page.locator('[role="tab"][data-tab="evidence"]').click()
    assert page.locator('[data-where]').get_attribute('data-where') == 'evidence'
    assert 'tab Evidence' in page.locator('[data-where]').inner_text()
    clean(panel)


@pytest.mark.parametrize('lang', ['en', 'fr'])
def test_ls3_r29_every_tab_opens_on_at_this_step_and_ends_on_next(open_panel, views, lang):
    panel = open_case(open_panel, views, lang=lang)
    page = panel.page
    label = {'en': 'At this step', 'fr': 'À cette étape'}[lang]
    for i, tab in enumerate(TABS):
        page.locator(f'[role="tab"][data-tab="{tab}"]').click()
        intro = page.locator(f'#panel-{tab} [data-intro="{tab}"]')
        assert intro.count() == 1, tab
        assert intro.locator('.ht-ie').inner_text().lower() == label.lower(), tab
        assert len(intro.inner_text()) > 120, (tab, 'two or three sentences')
        trans = page.locator(f'#panel-{tab} .ht-trans')
        assert trans.count() == 1, tab
        target = TABS[i + 1] if i + 1 < len(TABS) else TABS[0]
        assert trans.get_attribute('data-next-tab') == target, tab
    # The "Next" line leads to the next tab.
    page.locator('[role="tab"][data-tab="overview"]').click()
    page.locator('#panel-overview .ht-trans button').click()
    assert page.locator('[role="tab"][aria-selected="true"]').get_attribute('data-tab') == 'eda'
    clean(panel)


GUIDES = """() => [...document.querySelectorAll('figure.ht-figure')].filter(f => f.getBoundingClientRect().width > 0).map(f => ({
  // An EDA card's own title is the chart's question; elsewhere "Why this chart" says it.
  top: !!f.querySelector(':scope > [data-guide]') && (!!f.querySelector(':scope > [data-guide] .ht-qq') || !!f.closest('[data-eda-card]')),
  frame: (f.querySelector(':scope > [data-guide] [data-guide-fact="frame"]') || {}).textContent || null,
  steps: f.querySelectorAll(':scope > [data-reading] details[data-lire] li').length,
  concl: (f.querySelector(':scope > [data-reading] [data-concl]') || {}).textContent || null,
  attn: !!f.querySelector(':scope > [data-reading] [data-attn]'),
  cited: f.querySelectorAll(':scope > [data-reading] data[data-result-id]').length,
  kind: (f.querySelector(':scope > [data-reading]') || {dataset: {}}).dataset.reading,
}))"""


@pytest.mark.parametrize('case', ['binary', 'regression', 'families'])
def test_ls4_r30_every_chart_says_why_and_how_to_read_it(open_panel, views, case):
    panel = open_case(open_panel, views, case=case)
    page = panel.page
    seen = 0
    for tab in ['eda', 'evidence', 'whatif']:
        page.locator(f'[role="tab"][data-tab="{tab}"]').click()
        closed = page.locator('details.eda-analysis:not([open]) > summary')
        while closed.count():
            closed.first.click()
        for g in page.evaluate(GUIDES):
            seen += 1
            assert g['top'] and g['steps'] >= 1 and g['attn'], (tab, g)
            # The frame of the evidence is said for every chart of these tabs.
            assert g['frame'], (tab, g)
            # A quoted figure is a copy, never a second cited element.
            assert g['cited'] == 0, (tab, g)
            if g['kind'] in ('bars', 'points', 'intervals', 'difference', 'histogram', 'boxplot'):
                assert g['concl'] and any(ch.isdigit() for ch in g['concl']), (tab, g)
    assert seen >= 5
    clean(panel)


def test_ls4_r30_eda_charts_name_their_frame_and_rows(open_panel, views):
    panel = open_case(open_panel, views)
    page = panel.page
    page.locator('[role="tab"][data-tab="eda"]').click()
    card = page.locator('[data-eda-card="eda.rate_by:job"]')
    card.locator('summary').first.click() if card.locator('details.eda-analysis:not([open])').count() else None
    pq = card.locator('[data-guide]').first
    assert pq.locator('.ht-qq').count() == 0, 'the card title is the question; it is not repeated'
    assert 'look, counted' in pq.locator('[data-guide-fact="frame"]').inner_text()
    assert 'training rows' in pq.locator('[data-guide-fact="rows"]').inner_text()
    clean(panel)


def test_ls5_notions_put_the_term_first_then_the_study_values(open_panel, views):
    summary = views['summary.binary']
    panel = open_case(open_panel, views)
    page = panel.page
    sealed = page.locator('#panel-overview [data-notion="sealed"]')
    assert sealed.locator('dfn').inner_text() == 'Sealed final test'
    here = sealed.locator('[data-here]').inner_text()
    assert f"{summary['finalTest']['rows']:,}" in here
    assert sealed.locator('[data-notion-fold]').evaluate_all('fs => fs.map(f => f.dataset.notionFold)') == ['why', 'casse']
    assert sealed.locator('[data-notion-keep]').count() == 1
    page.locator('[role="tab"][data-tab="eda"]').click()
    if (summary.get('edaLooks') or {}).get('targetLooks') is not None:
        looks = page.locator('[data-notion="looks"] [data-here]')
        assert str(summary['edaLooks']['targetLooks']) in looks.inner_text()
    page.locator('[role="tab"][data-tab="decisions"]').click()
    assert page.locator('[data-notion="proposal"]').count() == 1
    clean(panel)


def test_ls5_one_standard_error_rule_is_a_notion_with_the_selection_figures(open_panel, views):
    panel = open_case(open_panel, views, case='families')
    page = panel.page
    page.locator('[role="tab"][data-tab="evidence"]').click()
    notion = page.locator('[data-notion="one_se"]')
    if views['evidence.families'].get('selection') and views['evidence.families']['selection'].get('oneSe'):
        assert notion.count() == 1
        text = notion.locator('[data-here]').inner_text()
        assert 'the bar sits at' in text and 'The rule keeps' in text
    clean(panel)


def test_ls5_learn_more_for_the_marks_and_the_abbreviations(open_panel, views):
    panel = open_case(open_panel, views, case='regression')
    page = panel.page
    marks = page.locator('header details[data-more="marks"]')
    marks.locator('summary').click()
    assert 'Final test sealed' in marks.inner_text() and 'Revision' in marks.inner_text()
    assert marks.locator('.ht-hd').count() == 1, 'the half disc of development evidence is drawn, not a glyph'
    page.locator('[role="tab"][data-tab="evidence"]').click()
    abbr = page.locator('#panel-evidence details[data-more="abbr"]')
    abbr.locator('summary').click()
    text = abbr.inner_text()
    assert 'MAE' in text and 'RMSE' in text and 'AUC' not in text, 'the regression study lists its own measures'
    clean(panel)


@pytest.mark.parametrize('lang', ['en', 'fr'])
def test_ls2_the_next_move_copies_a_question_in_the_panel_language(open_panel, views, lang):
    panel = open_case(open_panel, views, lang=lang)
    page = panel.page
    hero = page.locator('[data-band] [data-ov="hero"]')
    button = hero.locator('[data-copy-question]')
    assert button.inner_text() == {'en': 'Copy the question', 'fr': 'Copier la question'}[lang]
    assert hero.locator('[data-write]').count() == 0
    before = len(panel.posted())
    button.click()
    sent = panel.posted()[before:]
    assert [m['type'] for m in sent] == ['ask_agent'] and sent[0]['mode'] == 'copy'
    assert sent[0]['question'].startswith({'en': 'I am reading the proposal on', 'fr': 'Je lis la proposition sur'}[lang])
    clean(panel)


BOARD = "() => getComputedStyle(document.body).getPropertyValue('--board').trim().toLowerCase()"


@pytest.mark.parametrize('theme,board', [('dark-modern', '#20312c'), ('light-modern', '#f1f3f1'), ('hc', None)])
def test_ls6_the_vscode_theme_class_picks_the_board(open_panel, views, theme, board):
    panel = open_case(open_panel, views, theme=theme)
    page = panel.page
    got = page.evaluate(BOARD)
    if board:
        assert got == board, (theme, got)
    else:
        editor = page.evaluate("() => getComputedStyle(document.documentElement)"
                               ".getPropertyValue('--vscode-editor-background').trim().toLowerCase()")
        assert got == editor, 'High Contrast keeps the editor background'
        ruling = page.evaluate("() => getComputedStyle(document.body).getPropertyValue('--ruleline').trim()")
        assert ruling == 'transparent', 'no ruling in High Contrast'
    # The editor decides the theme: the panel has no theme button of its own.
    assert page.locator('[data-theme-toggle], button[aria-label*="theme" i]').count() == 0
    clean(panel)
