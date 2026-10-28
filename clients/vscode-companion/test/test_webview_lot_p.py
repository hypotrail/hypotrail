"""Lot P (owner remarks R34 to R53, 2026-10-28; ADR 0004 decision 14), scope S: the one page in
headless Chromium over states captured from the engine (``fixtures/capture.py``,
``cross_validated_regression``: Auto MPG with 80 rows sealed and five time-ordered folds, the
drafted preparation, two variants, the choice, the end) and the five one-page states. This is
not a VS Code session.

Two tests check several items at once, as the owner asked (the minimum, targeted):

* the journey: the figures behind each step in Now (quality per column, the preparation's
  distributions and diagram, the variants' diagnostics and budget bar), the calm
  result-dependent line, the per-fold dots, the budget after two variants (R47), the end's one
  table with its dots, the conclusion in three parts, the final-test criterion line, the
  Azure ML plan and the W8 gating, R34 and R38;
* What if? in its own read-only tab (R51), opened from the panel's button.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from panel_cases import STATES, click_fold, deliver_views, load_views, open_all, open_case

CV = ['preparation', 'variants', 'choice', 'done']


@pytest.fixture(scope='module')
def cv_views(model):
    out = {}
    for state in CV:
        out[f'summary.{state}'] = model('summary', f'captured/summary.regression.cv.{state}')
    reads = {'variants': 'variants', 'preparation': None, 'choice': None, 'done': 'done'}
    for state, suffix in reads.items():
        tail = f'.{suffix}' if suffix else ''
        ev = f'captured/evidence.regression.cv{tail}'
        status = f'captured/status.regression.cv{tail}'
        out[f'evidence.{state}'] = model('evidence', ev)
        out[f'eda.{state}'] = model('eda', ev)
        out[f'whatif.{state}'] = model('whatif', ev)
        out[f'trials.{state}'] = model('trials', status)
    out['decisions'] = model('decisions', 'captured/decisions.regression.cv')
    out['data'] = model('data', 'captured/data.regression.cv')
    out['azureml'] = model('azureml', 'captured/export.azureml.plan')
    return out


def open_cv(open_panel, views, state, lang='fr', width=420, stage='v3', reviewer=False, trials=True):
    panel = open_panel()
    panel.page.set_viewport_size({'width': width, 'height': 900})
    summary = views[f'summary.{state}']
    panel.init(stage=stage, task='regression', reviewer=reviewer, panelContract=2, language=lang)
    panel.snapshot(summary)
    for view in ('evidence', 'eda', 'whatif'):
        panel.view_data(view, views[f'{view}.{state}'])
    if trials:
        panel.view_data('trials', views[f'trials.{state}'])
    panel.view_data('decisions', views['decisions'])
    panel.view_data('data', views['data'])
    if state == 'done':
        panel.view_data('azureml', views['azureml'], revision=summary['revision'])
    panel.page.wait_for_selector('[data-block="now"]')
    return panel


def text(page, selector):
    return page.locator(selector).first.inner_text()


def test_lot_p_journey_figures_end_and_w8(open_panel, cv_views):
    """R34, R38, R39-R45, R47, R48, R49, R52, R53 on the captured Auto MPG study."""
    # The preparation proposal: the quality check per column, horsepower (the drafted log)
    # first and marked changed, every other column "no change" on the same figures; the
    # pipeline diagram; the limit line of this step (R43); nothing "to handle" (R34).
    p = open_cv(open_panel, cv_views, 'preparation')
    page = p.page
    figs = page.locator('[data-block="now"] [data-now-figures]')
    assert figs.count() == 1
    cols = figs.locator('[data-quality-column]')
    assert cols.count() >= 6
    assert cols.first.get_attribute('data-quality-column') == 'horsepower'
    assert cols.first.locator('[data-verdict]').get_attribute('data-verdict') == 'changed'
    assert figs.locator('[data-verdict="kept"]').count() == cols.count() - 1
    assert figs.locator('[data-method-diagram="pipeline"] [data-pipe-transform="horsepower"]').count() == 1
    # R43: the engine's limit line for the step when it sends one, else the panel's for the step.
    engine_limit = (cv_views['summary.preparation'].get('texts') or {}).get('fr', {}).get('step_limit')
    assert text(page, '[data-block="now"] [data-limit]').startswith(engine_limit or 'La préparation repose sur la structure')
    assert page.locator('[data-todo="deliverables"]').count() == 0
    # R38: every done step line says something; Données has the panel's line from the engine's rows.
    click_fold(page, 'ph-frame')
    data_line = page.locator('[data-step="discover_data"] .ht-v').first.inner_text()
    assert '398' in data_line and '80' in data_line, data_line
    assert p.clean()

    # The variants proposal: the diagnostics behind it (observed vs predicted, residuals along
    # columns), the budget as a bar (0 of 3), the result-dependent mark as one calm line.
    p = open_cv(open_panel, cv_views, 'variants')
    page = p.page
    now = page.locator('[data-block="now"]')
    assert now.locator('[data-figure="observed-predicted"]').count() == 1
    assert now.locator('[data-figure="residual-by-feature"]').count() >= 1
    assert now.locator('[data-budget-bar]').first.get_attribute('data-budget-bar') == '0/3'
    contingent = now.locator('[data-contingent]')
    assert contingent.count() == 1 and contingent.locator('.ht-warnline').count() == 0
    assert contingent.locator('details.ht-why').count() == 1

    # The choice after two confirmed variants (R47): an older `trials` read (the proposal's
    # 0 of 3) is never shown; the card reads 2 of 3 and asks for a fresh read. R42: per-fold dots.
    p = open_cv(open_panel, cv_views, 'choice', trials=False)
    page = p.page
    p.view_data('trials', cv_views['trials.variants'], revision=cv_views['summary.choice']['revision'] - 2)
    page.wait_for_selector('[data-trial-budget]')
    assert page.locator('[data-block="now"] [data-trial-budget]').first.get_attribute('data-trial-budget') == '2/3'
    assert any(m.get('type') == 'load' and m.get('view') == 'trials' for m in p.posted())
    dots = page.locator('[data-block="now"] [data-selection-chart="per-fold"]')
    assert dots.count() == 1 and dots.locator('[data-dot]').count() == 15
    # R45: each variant says which it is (the selection card's names: tuned penalty, EBM).
    assert 'pénalité réglée' in dots.inner_text().lower() and 'boosting explicable' in dots.inner_text().lower()
    assert page.locator('[data-method-diagram="one_se"]').count() == 1
    assert p.clean()

    # The end: one development-vs-final table (rows = configurations, then the difference with
    # the reference, then the criterion), unmeasured cells said, the same as dots on one scale;
    # the conclusion in three parts; the criterion line on the final test's error (R48, R52).
    p = open_cv(open_panel, cv_views, 'done')
    page = p.page
    table = page.locator('[data-block="now"] table[data-dev-final]')
    assert table.count() == 1
    rows = table.locator('tbody tr')
    assert [rows.nth(i).get_attribute('data-config') for i in range(rows.count())] == [
        'fit.linear', 'fit.variant', 'fit.variant:2', 'fit.baseline', 'difference', 'criterion']
    assert 'référence (prédire la moyenne)' in rows.nth(3).inner_text().lower()
    assert table.locator('[data-not-measured]').count() == 2
    assert 'non mesuré\u202f: le test final ne mesure que le modèle choisi' in text(page, '[data-not-measured="fit.variant"]')
    assert page.locator('[data-figure="dev-final-dots"] [data-mark="final"]').count() == 2
    assert page.locator('[data-conclusion-part]').count() == 2
    assert 'sur le test final' in text(page, '[data-criterion="final"]')
    assert text(page, '[data-criterion="final"]').count('test final') <= 2
    assert page.locator('[data-method-diagram="ledger"] [data-ledger-mark="opening"]').count() == 1
    # R49: "And after" shows the handoff export (W7) and the Azure ML plan (a read) with W8.
    after = page.locator('[data-block="after"]')
    assert after.locator('[data-after-handoff] [data-write="export"]').count() == 1
    assert int(after.locator('[data-azureml-plan]').get_attribute('data-azureml-plan')) > 50
    assert after.locator('[data-azureml-cloud="never"]').count() == 1
    after.locator('[data-write="azureml"]').click()
    assert {'v': 2, 'type': 'export_azureml', 'revision': cv_views['summary.done']['revision']} in p.posted()
    assert p.clean()
    # W8 is a stage v3 write: absent at v2, and absent in reviewer mode.
    for stage, reviewer in (('v2', False), ('v3', True)):
        q = open_cv(open_panel, cv_views, 'done', stage=stage, reviewer=reviewer)
        assert q.page.locator('[data-write="azureml"]').count() == 0, (stage, reviewer)


def test_lot_p_whatif_tab_opens_read_only(open_panel, cv_views):
    """R51: the panel's What if? drawer opens the editor tab; the tab is the residual explorer."""
    p = open_cv(open_panel, cv_views, 'choice')
    page = p.page
    page.locator('[data-drawer="whatif"] > summary').click()
    page.locator('[data-open-whatif]').click()
    assert {'v': 2, 'type': 'open_whatif'} in p.posted()
    assert page.locator('[data-drawer="whatif"] .ht-warnline').count() == 0
    # The tab: the same document with `surface: whatif`, read only.
    t = open_panel()
    t.page.set_viewport_size({'width': 1100, 'height': 900})
    t.send({'type': 'init', 'stage': 'v3', 'reviewer': False, 'learningLayer': True, 'chatInsert': False,
            'task': 'regression', 'panelContract': 2, 'surface': 'whatif'})
    t.snapshot(cv_views['summary.choice'])
    t.view_data('evidence', cv_views['evidence.choice'])
    t.page.wait_for_selector('[data-whatif-tab="regression"]')
    tab = t.page.locator('[data-whatif-tab]')
    assert tab.locator('[data-tab-configuration] input').count() == 3
    assert tab.locator('[data-figure="observed-predicted"]').count() == 1
    assert tab.locator('[data-figure="residual-by-feature"]').count() >= 4
    assert tab.locator('table[data-largest]').count() == 1
    assert t.page.locator('[data-block="path"], [data-block="now"], [data-write]').count() == 0
    tab.locator('[data-tab-configuration] input').nth(2).check()
    assert tab.locator('[data-figure="observed-predicted"]').get_attribute('data-model') == 'fit.variant:2'
    assert t.clean()


SHOTS = os.environ.get('HYPOTRAIL_LOT_P_SHOTS')


@pytest.mark.skipif(not SHOTS, reason='screenshots for the owner review only (HYPOTRAIL_LOT_P_SHOTS=<folder>)')
def test_lot_p_screenshots(open_panel, model, payload, cv_views):
    """Not a gate: full-page screenshots at 420 px in French, every fold open, for review."""
    out = Path(SHOTS)
    out.mkdir(parents=True, exist_ok=True)
    views = load_views(model, payload)
    for state in STATES:
        panel = open_case(open_panel, views, case=state, width=420, lang='fr', stage='v3')
        open_all(panel, panel.case_views, panel.case_reads)
        panel.page.screenshot(path=str(out / f'{state}.png'), full_page=True)
    for state in CV:
        panel = open_cv(open_panel, cv_views, state)
        panel.page.screenshot(path=str(out / f'cv-{state}.png'), full_page=True)
    t = open_panel()
    t.page.set_viewport_size({'width': 1100, 'height': 900})
    t.send({'type': 'init', 'stage': 'v3', 'reviewer': False, 'learningLayer': True, 'chatInsert': False,
            'task': 'regression', 'panelContract': 2, 'surface': 'whatif', 'language': 'fr'})
    t.snapshot(cv_views['summary.choice'])
    t.view_data('evidence', cv_views['evidence.choice'])
    t.page.wait_for_selector('[data-whatif-tab]')
    t.page.screenshot(path=str(out / 'whatif-tab.png'), full_page=True)
    assert deliver_views
