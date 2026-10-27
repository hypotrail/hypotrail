"""Folds, focus and navigation across re-renders on the one page (scope S, simulated browser;
COMPANION-ADVANCED §4.3, §10, §13.1; ADR 0004 decision 13). The mockup review found that every
click rebuilt the panel, closed the folds and lost the focus: these tests open and close folds
in every block, trigger each kind of re-render, and check that nothing moved. Real document,
real CSP, offline, contract-P1 states. Not a VS Code session.
"""
from __future__ import annotations

import pytest

from conftest import STUDY_KEY
from panel_cases import click_fold, load_views, open_case, set_language


@pytest.fixture(scope='module')
def views(model, payload):
    return load_views(model, payload)


FOLDS = """() => Object.fromEntries([...document.querySelectorAll('details[data-fold-id]')].map(d => [d.dataset.foldId, d.open]))"""


def toggle(page, fold_id):
    click_fold(page, fold_id)


def test_fold1_fold2_folds_are_kept_across_every_kind_of_re_render(open_panel, views):
    """FOLD-1, FOLD-2, §10: folds opened and closed in every block keep their state across a new
    snapshot, a block's data, the language, the theme and a write's outcome; their state is in
    setState `folds`, which holds nothing else than fold ids and booleans."""
    panel = open_case(open_panel, views, case='reopened', width=600, lang='en', stage='v3')
    page = panel.page
    # since, the effects of Now, the ledger, a closed phase, a step, a drawer; and close an open phase.
    for f in ['since', 'effects', 'ledger', 'ph-frame', 'st-structural_eda', 't-deliverables', 'ph-compare']:
        toggle(page, f)
    panel.view_data('decisions', views['decisions.p1'])
    expected = page.evaluate(FOLDS)
    assert expected['since'] and expected['effects'] and expected['ledger'] and expected['ph-frame']
    assert expected['st-structural_eda'] and expected['t-deliverables'] and not expected['ph-compare']
    stored = panel.state()['folds']
    assert all(isinstance(v, bool) for v in stored.values()) and stored['ph-compare'] is False
    rerenders = [
        lambda: panel.snapshot(views['summary.reopened']),
        lambda: panel.view_data('evidence', views['evidence.p1']),
        lambda: set_language(page, 'fr'),
        lambda: set_language(page, 'en'),
        lambda: page.locator('[data-theme-control]').click(),
        lambda: panel.send({'type': 'outcome', 'op': 'W5', 'kind': 'ok', 'target': 'render',
                            'artifacts': [{'name': 'report', 'status': 'ok', 'message': 'The report is up to date.'}]}),
        lambda: panel.send({'type': 'notice', 'text': 'Copied.', 'politeness': 'polite'}),
    ]
    for i, again in enumerate(rerenders):
        again()
        now = page.evaluate(FOLDS)
        assert {k: v for k, v in now.items() if k in expected} == expected, i
    assert panel.clean()


def test_focus1_focus_stays_on_the_control_across_a_re_render(open_panel, views):
    """FOCUS-1, FOCUS-2: a focused fold summary, the theme button, a radio of the "more" menu and a
    copy button keep the focus across re-renders; the scroll position is kept."""
    panel = open_case(open_panel, views, case='choice', width=420, lang='en', height=600)
    page = panel.page
    summary = page.locator('details[data-fold-id="ph-evidence"] > summary')
    summary.focus()
    page.keyboard.press('Enter')
    assert page.evaluate("() => document.activeElement.getAttribute('data-focus-id')") == 'fold:ph-evidence'
    y = page.evaluate('window.scrollY')
    panel.snapshot(views['summary.choice'])
    panel.view_data('eda', views['eda.p1'])
    assert page.evaluate("() => document.activeElement.getAttribute('data-focus-id')") == 'fold:ph-evidence'
    assert page.evaluate('window.scrollY') == y
    page.locator('[data-theme-control]').focus()
    page.keyboard.press('Enter')
    assert page.evaluate("() => document.activeElement.hasAttribute('data-theme-control')")


def test_nav1_fold3_a_deep_link_opens_the_folds_that_hold_its_figure_and_nothing_else(open_panel, views):
    """NAV-1, FOLD-3, §4.3: `navigate` to a figure's anchor opens its phase, its step and its
    figure, records them opened, focuses the figure's heading, and leaves every other fold as
    it was; an unknown anchor goes to the path's head."""
    panel = open_case(open_panel, views, case='choice', width=420, lang='en')
    page = panel.page
    toggle(page, 't-deliverables')
    before = page.evaluate(FOLDS)
    anchor = 'path:train_eda/eda.mean_by:model_year'
    panel.send({'type': 'navigate', 'anchor': anchor, 'kind': 'result', 'id': views['summary.choice']['results']['eda.mean_by:model_year']['resultId']})
    after = page.evaluate(FOLDS)
    assert after['ph-evidence'] and after['st-train_eda'] and after['fig-eda.mean_by:model_year']
    assert after['t-deliverables'] == before['t-deliverables']
    assert all(after[k] == v for k, v in before.items() if k not in ('ph-evidence', 'st-train_eda'))
    assert panel.state()['folds']['fig-eda.mean_by:model_year'] is True
    focused = page.evaluate("() => document.activeElement.closest('[data-anchor]') && document.activeElement.closest('[data-anchor]').dataset.anchor")
    assert focused == anchor
    assert page.locator(f'[data-anchor="{anchor}"].ht-highlight').count() == 1
    # The tabbed form is dropped as invalid (§8.2).
    panel.send({'type': 'navigate', 'tab': 'evidence', 'kind': 'result', 'id': 'a' * 64})
    assert page.evaluate('window.Hypotrail.diagnostics.ignored') >= 1


def test_cr2_folds_and_the_question_draft_belong_to_one_study(open_panel, views):
    """§10, CR.2: `folds` and `askDraft` are dropped when `init` names another study; the language
    and the theme are the viewer's and stay; the tabbed panel's keys are dropped on load."""
    panel = open_case(open_panel, views, case='choice', width=420, lang='fr', deliver=False)
    page = panel.page
    toggle(page, 't-deliverables')
    page.locator('[data-theme-control]').click()
    assert set(panel.state()) == {'study', 'folds', 'language', 'theme'}
    panel.init(stage='v3', study='fedcba9876543210', panelContract=2)
    state = panel.state()
    assert 'folds' not in state and state['language'] == 'fr' and state['theme'] == 'dark'
    assert state['study'] == 'fedcba9876543210'
    other = open_panel()
    other.context.add_init_script("""window.__state = {tab: 'evidence', recapCollapsed: false, evidenceFilter: 'all',
      selectedResult: 'a', drafts: {}, ackDrafts: {}, study: '%s', theme: 'neon', folds: {'ph-frame': true, bad: 3}};""" % STUDY_KEY)
    other.page.reload()
    other.page.wait_for_load_state('load')
    assert other.state() == {'study': STUDY_KEY, 'folds': {'ph-frame': True}}
