"""Lot 2026-10-28 (one structure for every step; docs/plans/LOT-2026-10-28-SPEC.md §5, §7.4,
binding §8 and §9): the step card in headless Chromium, over digests of a French Auto MPG study
captured from the real engine (``fixtures/stepcards/``, written by
``fixtures/stepcards/capture.py``: a guided study walked by the engine tests' journey walker, and a
``full_demo`` automatic one) and the views of that study at the end (``evidence``, ``status``,
``decisions``, ``data``). This is not a VS Code session.

The tests the spec keeps (§8): T-P1 (Now in four blocks at the exploration), T-P2 without the
replay (the review form of every done step, full names, equal axes, the folds' legend, the
timeline's slider, the metric bars), and the fallback (a digest without step cards keeps
today's Now). ``HT_STEP_SHOTS=<folder>`` also writes the screenshots of the demo steps.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

import themes
from conftest import read_payload
from panel_cases import STYLE_GUARD, set_language, without_step_cards

STATES = ['data', 'moment', 'variables', 'split', 'metric', 'criterion', 'quality', 'preparation', 'exploration', 'models',
          'variants', 'choice', 'final', 'conclusion', 'done', 'done.automatic']
NO_DECISION = ('discover_data', 'structural_eda', 'train_eda', 'models')
CONCL = "() => [...document.querySelectorAll('[data-block=\"now\"] [data-lesson-concl], [data-block=\"now\"] .ht-concl, [data-block=\"now\"] [data-guided-reading]')].length"


@pytest.fixture(scope='module')
def sc_views(model):
    out = {f'summary.{s}': model('summary', f'stepcards/summary.{s}') for s in STATES}
    ev = 'stepcards/evidence.done'
    out['evidence'] = model('evidence', ev)
    out['eda'] = model('eda', ev)
    out['whatif'] = model('whatif', ev)
    out['trials'] = model('trials', 'stepcards/status.done')
    out['decisions'] = model('decisions', 'stepcards/decisions.done')
    out['data'] = model('data', 'stepcards/data.done')
    out['plain'] = model('summary', without_step_cards(read_payload('captured/summary.regression.cv.preparation')))
    return out


def open_state(open_panel, views, state, lang='fr', width=420, stage='v3', theme='dark-modern', height=900):
    panel = open_panel(color_scheme=themes.scheme(theme))
    panel.page.evaluate(STYLE_GUARD)
    panel.page.set_viewport_size({'width': width, 'height': height})
    themes.apply(panel.page, theme)
    summary = views[state] if state == 'plain' else views[f'summary.{state}']
    panel.init(stage=stage, task='regression', panelContract=2)
    panel.snapshot(summary)
    set_language(panel.page, lang)
    for view in ('evidence', 'eda', 'whatif', 'trials', 'decisions', 'data'):
        panel.view_data(view, views[view])
    panel.page.wait_for_selector('[data-block="now"]')
    return panel


def no_hscroll(page):
    return page.evaluate('() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1')


def test_tp1_exploration_four_blocks(open_panel, sc_views):
    """T-P1: PA-1, PA-2, PA-12, ST-1, ST-3, ST-12 at the exploration (FR, stage v2, 420 and 600)."""
    for width in (420, 600):
        p = open_state(open_panel, sc_views, 'exploration', width=width, stage='v2')
        page = p.page
        now = page.locator('[data-block="now"]')
        assert now.get_attribute('data-step-card') == 'train_eda'
        blocks = [b.get_attribute('data-block') for b in now.locator(':scope > section[data-block]').all()]
        assert blocks == ['picture', 'establish', 'answer', 'limit'], blocks
        assert 'Étape 9/14' in now.locator('h2').first.text_content() and 'Exploration' in now.locator('h2 .sc-full').inner_text()
        # Q1-Q3 numbered in block 2 and block 3.
        assert [b.inner_text() for b in now.locator('[data-block="establish"] [data-q-badge]').all()] == ['Q1', 'Q2', 'Q3']
        sections = now.locator('[data-block="answer"] [data-question-id]')
        assert [s.get_attribute('data-question-id') for s in sections.all()] == ['explore.target', 'explore.features', 'explore.redundant']
        for s in sections.all():
            assert [x.get_attribute('data-part') for x in s.locator('[data-part]').all()] == ['see', 'conclude', 'cannot']
            assert s.locator('.sc-rl').all_inner_texts()[:3] == ["CE QU'ON VOIT", "CE QU'ON EN CONCLUT", "CE QU'ON NE PEUT PAS CONCLURE"] or \
                [t.lower() for t in s.locator('.sc-rl').all_inner_texts()] == ["ce qu'on voit", "ce qu'on en conclut", "ce qu'on ne peut pas conclure"]
            assert s.locator('[data-chart] svg, [data-chart] table').count() >= 1, 'each question draws its chart'
        # The engine's readings, not the panel's guided conclusions (PA-2).
        assert page.evaluate(CONCL) == 0
        assert 'regard' in now.locator('[data-block="answer"] .sc-frame').first.inner_text()
        # The pause after the exploration (EN-12, R61) and the chat's question with its copy button.
        assert now.locator('[data-pause="read_exploration"]').count() == 1
        assert 'On passe aux modèles' in now.locator('[data-chat-block]').inner_text()
        # The numbers of a reading are cited (ST-3): hoverable to their result.
        assert now.locator('[data-part="see"] data[data-result-id]').count() >= 3
        assert no_hscroll(page), f'no horizontal scroll at {width}'
        assert p.clean(), (p.errors, p.requests)


def test_tp2_review_names_charts_and_slider(open_panel, sc_views):
    """T-P2 without the replay: PA-4, PA-5, PA-6, PA-8, PA-9, PA-10, PA-11 on the done digest."""
    p = open_state(open_panel, sc_views, 'done', width=420)
    page = p.page
    path = page.locator('[data-block="path"]')
    names = [t.inner_text() for t in path.locator('[data-step] .sc-t').all()]
    fr = ['Données', 'Moment de la prédiction', 'Variables disponibles', 'Découpage', "Mesure de l'erreur", 'Critère de succès',
          'Contrôle de qualité', 'Préparation', 'Exploration', 'Modèles', 'Variantes', 'Choix du modèle', 'Test final', 'Conclusion']
    assert names == [f'{i + 1} · {n}' for i, n in enumerate(fr)], names
    # Every done step opens its review form: the decision first, then the answers.
    steps = [s.get_attribute('data-step') for s in path.locator('li[data-step]').all()]
    assert len(steps) == 14
    for step in steps:
        page.locator(f'li[data-step="{step}"] > details > summary').click()
        form = page.locator(f'li[data-step="{step}"] [data-review="{step}"]')
        form.wait_for(timeout=5000)
        assert form.count() == 1, step
        assert form.locator('[data-answer], .sc-ra').count() >= 1, step
        # The decision taken, exactly where the engine's card has one (the data card, the quality
        # check, the exploration and the models record none).
        assert form.locator('.sc-decided').count() == (0 if step in NO_DECISION else 1), step
        page.locator(f'li[data-step="{step}"] > details > summary').click()
        form.wait_for(state='detached', timeout=5000)
    sent = len(p.posted())

    def show(step, qid):
        if page.locator(f'li[data-step="{step}"] > details').get_attribute('open') is None:
            page.locator(f'li[data-step="{step}"] > details > summary').click()
            page.locator(f'li[data-step="{step}"] [data-review]').wait_for(timeout=5000)
        page.locator(f'li[data-step="{step}"] [data-show-chart="{qid}"] > summary').click()
        box = page.locator(f'li[data-step="{step}"] [data-show-chart="{qid}"]')
        box.locator('[data-question-id]').wait_for(timeout=5000)
        return box

    # PA-10: observed against predicted, the same domain on both axes.
    op = show('models', 'models.where').locator('[data-observed-predicted]')
    assert op.get_attribute('data-x-domain') == op.get_attribute('data-y-domain')
    assert 'prédiction parfaite' in op.inner_html()
    # PA-8, PA-11: the folds' two-swatch legend, the display name, no column name in code.
    folds = show('split', 'split.folds').locator('[data-folds]')
    assert folds.get_attribute('data-legend') == '2' and folds.get_attribute('data-folds') == 'computed'
    html = folds.inner_html()
    assert 'année du modèle' in html and 'model_year' not in html
    assert 'validation · prédites dans ce tour' in html and 'entraînement · le modèle en apprend' in html
    assert show('split', 'split.sealed').locator('[data-strata="5"]').count() == 1
    # PA-9: the made-up errors, MAE 2 and RMSE 2,83.
    mb = show('error_metric', 'metric.weigh').locator('[data-metric-bars]')
    assert mb.get_attribute('data-mae') == '2' and mb.get_attribute('data-rmse') == '2,83'
    assert 'exemple fictif' in mb.inner_html()
    # PA-6: the timeline's slider moved by keyboard changes the kept list; nothing is sent.
    tl = show('prediction_time', 'moment.when')
    kept = tl.locator('[data-kept]')
    before = kept.get_attribute('data-kept')
    slider = tl.locator('[data-timeline-slider]')
    slider.focus()
    page.keyboard.press('ArrowLeft')
    after = tl.locator('[data-kept]').get_attribute('data-kept')
    assert before != after and 'weight' in before and 'weight' not in after
    assert 'Moteur conçu' in slider.get_attribute('aria-valuetext')
    assert len(p.posted()) == sent, 'the slider sends nothing'
    assert no_hscroll(page)
    # PA-12 (T-P1's drawer check, here where the study is evaluated and the drawer exists): the
    # What if? drawer holds the calm line and the button only.
    page.locator('[data-drawer="whatif"] > summary').click()
    body = page.locator('[data-drawer="whatif"] [data-whatif-drawer]')
    body.wait_for(timeout=5000)
    assert [c.evaluate('n => n.tagName') for c in body.locator(':scope > *').all()] == ['P', 'BUTTON']
    assert body.locator('[data-whatif-warning]').count() == 1 and body.locator('[data-open-whatif]').count() == 1
    assert page.locator('[data-drawer="whatif"] input, [data-drawer="whatif"] .ht-whatif').count() == 0
    assert p.clean(), (p.errors, p.requests)


def test_tp2_split_proposed_folds_before_any_fit(open_panel, sc_views):
    """T-P2 (EN-20, R59, R63): the split proposed shows the strata and equal folds before any fit."""
    p = open_state(open_panel, sc_views, 'split', width=420)
    now = p.page.locator('[data-block="now"]')
    assert now.locator('[data-strata="5"]').count() == 1
    folds = now.locator('[data-folds]')
    assert folds.get_attribute('data-folds') == 'illustrative' and folds.get_attribute('data-legend') == '2'
    assert 'model_year' not in folds.inner_html()
    assert no_hscroll(p.page)


def test_fallback_without_step_cards(open_panel, sc_views):
    """PA-2 fallback (§8): a digest without step cards keeps today's Now and path."""
    p = open_state(open_panel, sc_views, 'plain', width=420)
    now = p.page.locator('[data-block="now"]')
    assert now.get_attribute('data-step-card') is None
    assert now.locator('[data-block="picture"], [data-block="establish"]').count() == 0
    assert now.locator('h3[data-question]').count() >= 1, "today's question"
    assert p.page.locator('[data-step-card-path]').count() == 0
    assert p.page.locator('[data-block="path"] [data-phase-kind]').count() >= 1, "today's path"
    assert p.clean(), (p.errors, p.requests)


def test_r65_r66_engine_brief_and_checklist(open_panel, sc_views):
    """R66 and R65 on the engine's keys (CLI-CONTRACT §18.5, §18.7): the brief's texts with the
    top-level numbers and fictitious flag; the pill's note lists `defensibility.checklist` with the
    engine's texts and ticks, then the limits of `defensibility.items`."""
    p = open_state(open_panel, sc_views, 'done', width=420)
    page = p.page
    page.locator('[data-pill="defensible"]').click()
    pop = page.locator('[data-popover="def"]')
    pop.wait_for(timeout=5000)
    checks = pop.locator('[data-check]')
    assert [c.get_attribute('data-check') for c in checks.all()] == [
        'framing_in_your_words', 'model_chosen_by_you', 'final_test_opened_once', 'conclusion_written', 'no_stale_figure']
    assert pop.locator('[data-check="final_test_opened_once"]').get_attribute('data-done') == 'true'
    assert 'Le test final, ouvert une fois' in pop.inner_text()
    assert pop.locator('[data-def-limits-lead]').count() == 1 and pop.locator('[data-item]').count() >= 1
    p = open_state(open_panel, sc_views, 'data', width=420)
    brief = p.page.locator('[data-block="brief"]')
    assert brief.locator('[data-fictitious]').count() == 1
    numbers = brief.locator('[data-brief-numbers]').inner_text()
    assert '4,5 ' in numbers and '3,5 ' in numbers, numbers
    brief.locator('[data-fold-id="sc-brief-data_provenance"] > summary').click()
    brief.locator('[data-fold-id="sc-brief-data_provenance"] > :not(summary)').first.wait_for(timeout=5000)
    assert 'UCI Machine Learning Repository' in brief.locator('[data-fold-id="sc-brief-data_provenance"]').inner_text()
    assert brief.inner_text().count("Fiche du cas d'usage") == 1, 'the source label is not repeated'
    assert p.clean(), (p.errors, p.requests)


SHOTS = {'data': 1, 'moment': 2, 'metric': 5, 'criterion': 6, 'exploration': 9, 'choice': 12, 'conclusion': 14}


@pytest.mark.skipif(not os.environ.get('HT_STEP_SHOTS'), reason='HT_STEP_SHOTS names the folder of the demo screenshots')
def test_step_card_screenshots(open_panel, sc_views):
    """The demo screenshots (steps 1, 2, 5, 6, 9, 12, 14; FR; 420 px; dark and light)."""
    out = Path(os.environ['HT_STEP_SHOTS'])
    out.mkdir(parents=True, exist_ok=True)
    for state, n in SHOTS.items():
        for theme in ('dark-modern', 'light-modern'):
            p = open_state(open_panel, sc_views, state, width=420, theme=theme, height=900)
            p.page.wait_for_timeout(100)
            p.page.screenshot(path=str(out / f'step{n:02d}-{state}-{theme.split("-")[0]}.png'), full_page=True)
            assert p.clean(), (state, p.errors)
