"""Browser tests of the lesson style on the one page (scope S, simulated browser; owner-approved
mockup docs/plans/mockups/panel-lesson-style-fr.html, notes R27-R30 of
docs/acceptance/runs/copilot-companion-2026-10-26.md; re-pointed by ADR 0004 d13).

On the captured payloads of the real engine (``panel_cases.py``), in English and in French:

* LS-4 (R30): every chart says why it is there and how to read it (the question, the frame of
  the evidence, the steps, the conclusion with the chart's own figures, the trap), wherever it
  now sits (the path's details, Now, the drawers);
* LS-2 → NOW-3, NOW-6: Now has one action, "Copy the question", which writes nothing; the
  review of an automatic decision asks to adopt or change it;
* LS-6: the VS Code theme class picks the board (dark), the white board (light) or the
  editor's own high-contrast colours (the panel's own theme control is THEME-1 to THEME-5,
  `test_webview_header.py`).

Withdrawn with the tabs, and their tests with them (§18): the journey rail and the sticky
position line (LS-1 → PG-8, PATH-2), "At this step" and "Next" per tab (LS-3 → NOW-10), the
lesson notions of the Overview, Data and Evidence tabs and the "Learn more" legends (LS-5 →
NOT-1 to NOT-3: a term expands in place, term first, then the study's values;
`test_webview_tools.py`).

This is not a VS Code session.
"""
from __future__ import annotations

import copy

import pytest

from conftest import inline_styles_ok
from panel_cases import load_views, open_all, open_case


@pytest.fixture(scope='module')
def views(model, payload):
    return load_views(model, payload)


def clean(panel):
    assert not (panel.requests or panel.errors or panel.csp or panel.violations()), \
        (panel.requests, panel.errors, panel.csp, panel.violations())
    assert inline_styles_ok(panel.page)


GUIDES = """() => [...document.querySelectorAll('figure.ht-figure')].filter(f => f.getBoundingClientRect().width > 0).map(f => ({
  // An EDA card's own title is the chart's question; elsewhere "Why this chart" says it.
  top: !!f.querySelector(':scope > [data-guide]') && (!!f.querySelector(':scope > [data-guide] .ht-qq') || !!f.closest('[data-eda-card]')),
  frame: (f.querySelector(':scope > [data-guide] [data-guide-fact="frame"]') || {}).textContent || null,
  steps: f.querySelectorAll(':scope > [data-reading] details[data-lire] li').length,
  concl: (f.querySelector(':scope > [data-reading] [data-concl]') || {}).textContent || null,
  attn: !!f.querySelector(':scope > [data-reading] [data-attn]'),
  cited: f.querySelectorAll(':scope > [data-reading] data[data-result-id]').length,
  kind: (f.querySelector(':scope > [data-reading]') || {dataset: {}}).dataset.reading,
  none: globalThis.Hypotrail.copy.lesson.concl.none,
}))"""


@pytest.mark.parametrize('case', ['binary', 'regression', 'families'])
def test_ls4_r30_every_chart_says_why_and_how_to_read_it(open_panel, views, case):
    panel = open_case(open_panel, views, case=case)
    open_all(panel, views, case)
    seen = 0
    for g in panel.page.evaluate(GUIDES):
        seen += 1
        assert g['top'] and g['steps'] >= 1 and g['attn'], g
        # The frame of the evidence is said for every chart.
        assert g['frame'], g
        # A quoted figure is a copy, never a second cited element.
        assert g['cited'] == 0, g
        if g['kind'] in ('bars', 'points', 'intervals', 'difference', 'histogram', 'boxplot'):
            # A figure with no value defined on its rows says so instead (an undefined difference).
            assert g['concl'] and (any(ch.isdigit() for ch in g['concl']) or g['concl'].endswith(g['none'])), (case, g)
    assert seen >= 5
    clean(panel)


def test_ls4_r30_eda_charts_name_their_frame_and_rows(open_panel, views):
    panel = open_case(open_panel, views)
    open_all(panel, views, 'binary')
    card = panel.page.locator('[data-block="path"] [data-eda-card="eda.rate_by:job"]')
    pq = card.locator('[data-guide]').first
    assert pq.locator('.ht-qq').count() == 0, 'the card title is the question; it is not repeated'
    assert 'look, counted' in pq.locator('[data-guide-fact="frame"]').inner_text()
    assert 'training rows' in pq.locator('[data-guide-fact="rows"]').inner_text()
    clean(panel)


@pytest.mark.parametrize('lang', ['en', 'fr'])
def test_ls2_now3_now_copies_a_question_in_the_panel_language(open_panel, views, lang):
    panel = open_case(open_panel, views, lang=lang)
    page = panel.page
    now = page.locator('[data-block="now"]')
    button = now.locator('[data-copy-question]')
    assert button.count() == 1, 'one action'
    question = page.evaluate('s => globalThis.Hypotrail.copy.page.askQuestions[s]', now.get_attribute('data-now-step'))
    # French typography: the panel sets narrow no-break spaces before ? and inside « » (§13.2).
    assert button.inner_text().replace('\u202f', ' ') == {'en': f'Copy "{question}"', 'fr': f'Copier « {question} »'}[lang]
    assert now.locator('[data-write]').count() == 0
    before = len(panel.posted())
    button.click()
    sent = panel.posted()[before:]
    assert [m['type'] for m in sent] == ['ask_agent'] and sent[0]['mode'] == 'copy'
    assert sent[0]['question'] == question
    clean(panel)


@pytest.mark.parametrize('lang', ['en', 'fr'])
def test_ls2_r24_now6_the_review_of_an_automatic_decision_copies_an_adoption_question(open_panel, views, lang):
    """R24 (owner session 2026-10-27) → NOW-6: ``next_action.review`` (a decision the automatic
    mode recorded) is an adoption question: Now says "Review", not "Confirm again", and its
    copied question asks what the decision changes, to adopt or change it. Without ``review``
    the same reconfirmation is a reopened decision."""
    summary = copy.deepcopy(views['summary.regression'])
    decision = 'prediction_time'
    assert decision in [s['id'] for s in summary['plan']]
    for review in (True, False):
        summary['nextAction'] = {**summary['nextAction'], 'kind': 'reconfirm', 'decision': decision,
                                 'proposalId': None, 'step': None, 'review': review}
        panel = open_case(open_panel, {**views, 'summary.regression': summary}, case='regression', lang=lang)
        page = panel.page
        now = page.locator('[data-block="now"]')
        assert now.get_attribute('data-now') == ('review' if review else 'reopened')
        heading = now.locator('h2').first.text_content()
        assert heading.startswith({'en': 'Now · Review', 'fr': 'Maintenant · Relire'}[lang]) is review, heading
        assert now.locator('[data-write]').count() == 0
        before = len(panel.posted())
        now.locator('[data-copy-question]').click()
        sent = panel.posted()[before:]
        assert [m['type'] for m in sent] == ['ask_agent'] and sent[0]['mode'] == 'copy'
        expected = page.evaluate("""([review, step]) => { const q = globalThis.Hypotrail.copy.page.askQuestions;
          return review ? q.review(globalThis.Hypotrail.copy.junior.decisionName(step, 'regression')) : q[step]; }""",
                                 [review, decision])
        assert sent[0]['question'] == expected
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
    clean(panel)
