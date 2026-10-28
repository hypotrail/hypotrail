"""EDA cards and the "Run another chart" card (review 2026-10-24, panel minor items; re-pointed
by ADR 0004 d13: the cards are figures of the path, the request is in the Data drawer).

Simulated browser on the captured payloads (``panel_cases.py``); not a VS Code session.

* A per-column card and the request card ask the same question for the same chart: in
  English the engine's own question, in French the panel's translation of it; under
  cross-validation both name the development rows, never the training rows.
* A card the junior closed (or opened) stays so across a re-render and the language switch
  (a fold of the page, FOLD-1: `setState` `folds`, never study state); "Show it" opens it.
  The gallery's "only the last card open" default is withdrawn with the gallery: every
  figure of the path opens with its analysis.
"""
from __future__ import annotations

import copy

import pytest

from panel_cases import load_views, open_all, open_case, set_language, with_results

PER_COLUMN = ('eda.distribution', 'eda.rate_by', 'eda.mean_by')


@pytest.fixture(scope='module')
def views(model, payload):
    return load_views(model, payload)


def gallery(views, case):
    return [c for c in views[f'eda.{case}']['cards'] if c['kind'] != 'quality']


def show(panel, views, case):
    """Every fold open: the figures of the path and the Data drawer (the former EDA tab)."""
    open_all(panel, views, case)


def title(page, slot):
    return page.locator(f'[data-block="path"] [data-eda-card="{slot}"] summary h3').inner_text().replace('\u202f', ' ')


def eyebrow(page, slot):
    return page.locator(f'[data-block="path"] [data-eda-card="{slot}"] [data-eyebrow]').inner_text()


def request_question(page):
    # French typography (§13.2) applies to the panel's copy, not to the engine's text: compared without it.
    return page.locator('.eda-request-question').inner_text().replace('\u202f', ' ')


def cv_views(views):
    """The cross-validated study with a per-column card, worded as the engine words it there
    (``mlkit/study/eda.py`` ``development_words``: training rows become development rows)."""
    out = dict(views)
    eda = copy.deepcopy(views['eda.cv'])
    card = copy.deepcopy(next(c for c in views['eda.binary']['cards'] if c['slot'] == 'eda.distribution:age'))
    card['question'] = card['question'].replace('training rows', 'development rows')
    # L3: the engine's texts of the card, in both languages, worded the same way.
    for lang, words in (('en', ('training rows', 'development rows')),
                        ('fr', ("lignes d'entraînement", 'lignes de développement'))):
        if card.get('texts') and card['texts'].get(lang) and card['texts'][lang].get('question'):
            card['texts'][lang]['question'] = card['texts'][lang]['question'].replace(*words)
    eda['cards'].append(card)
    out['eda.cv'] = eda
    # The one page files a chart under its step when the summary names its result (P1 §17.2).
    out['summary.cv'] = with_results(views['summary.cv'], [card])
    return out, card


@pytest.mark.parametrize('case', ['binary', 'regression'])
def test_english_gallery_titles_are_the_engine_questions(open_panel, views, case):
    panel = open_case(open_panel, views, case=case, lang='en')
    show(panel, views, case)
    for card in gallery(views, case):
        assert title(panel.page, card['slot']) == card['question'], card['slot']


@pytest.mark.parametrize('lang', ['en', 'fr'])
@pytest.mark.parametrize('case, column, activity', [('binary', 'age', 'eda.distribution'),
                                                    ('binary', 'job', 'eda.rate_by'),
                                                    ('regression', 'model_year', 'eda.mean_by')])
def test_the_request_card_asks_the_question_of_the_card_it_adds(open_panel, views, lang, case, column, activity):
    panel = open_case(open_panel, views, case=case, lang=lang)
    page = panel.page
    show(panel, views, case)
    slot = f'{activity}:{column}'
    assert page.locator(f'[data-eda-card="{slot}"]').count() == 1, slot
    page.select_option('#eda-variable', column)
    page.select_option('#eda-chart', activity)
    question = request_question(page)
    assert question.endswith(f' {title(page, slot)}'), (question, title(page, slot))
    if lang == 'en':
        card = next(c for c in gallery(views, case) if c['slot'] == slot)
        assert title(page, slot) == card['question']


def test_french_cross_validated_titles_and_request_name_the_development_rows(open_panel, views):
    v, card = cv_views(views)
    panel = open_case(open_panel, v, case='cv', lang='fr')
    page = panel.page
    show(panel, v, 'cv')
    assert 'développement' in eyebrow(page, card['slot']).lower()
    t = title(page, card['slot'])
    assert t.replace('\u202f', ' ') == 'Comment les valeurs de age se répartissent-elles parmi les lignes de développement ?', t
    page.select_option('#eda-variable', 'age')
    page.select_option('#eda-chart', 'eda.distribution')
    q = request_question(page)
    assert "entraînement" not in q and q.endswith(t), q


def test_english_cross_validated_request_is_the_engine_question(open_panel, views):
    v, card = cv_views(views)
    panel = open_case(open_panel, v, case='cv', lang='en')
    page = panel.page
    show(panel, v, 'cv')
    assert title(page, card['slot']) == card['question']
    page.select_option('#eda-variable', 'age')
    page.select_option('#eda-chart', 'eda.distribution')
    q = request_question(page)
    assert 'training rows' not in q and q.endswith(card['question']), q


def _details(page, slot):
    return page.locator(f'[data-block="path"] [data-eda-card="{slot}"] details.eda-analysis')


def test_fold1_a_closed_card_stays_closed_across_a_rerender_and_the_language_switch(open_panel, views):
    panel = open_case(open_panel, views, case='binary', lang='en')
    page = panel.page
    show(panel, views, 'binary')
    first = _details(page, 'eda.target_rate')
    assert first.get_attribute('open') == '', 'a figure of the path opens with its analysis'
    first.locator(':scope > summary').click()
    assert first.get_attribute('open') is None
    # A view-local re-render (the junior picks another variable in "Run another chart").
    page.select_option('#eda-variable', 'age')
    assert first.get_attribute('open') is None
    # A new read of the view re-renders it too.
    panel.view_data('eda', views['eda.binary'])
    assert first.get_attribute('open') is None
    set_language(page, 'fr')
    assert first.get_attribute('open') is None
    set_language(page, 'en')
    assert first.get_attribute('open') is None
    assert panel.state()['folds']['eda-eda.target_rate'] is False, 'a fold of the page (FOLD-1), not study state'
    # The others keep their default.
    for slot in [c['slot'] for c in gallery(views, 'binary')][1:]:
        if _details(page, slot).count():
            assert _details(page, slot).get_attribute('open') == '', slot
    first.locator(':scope > summary').click()
    page.select_option('#eda-variable', 'job')
    assert first.get_attribute('open') == '', 'opened again, it stays open'


def test_show_it_opens_a_closed_card_which_then_stays_open(open_panel, views):
    panel = open_case(open_panel, views, case='binary', lang='en')
    page = panel.page
    show(panel, views, 'binary')
    card = _details(page, 'eda.rate_by:job')
    card.locator(':scope > summary').click()
    assert card.get_attribute('open') is None
    page.select_option('#eda-variable', 'job')
    page.select_option('#eda-chart', 'eda.rate_by')
    assert card.get_attribute('open') is None
    page.locator('#eda-show').click()
    assert card.get_attribute('open') == ''
    page.select_option('#eda-variable', 'age')
    assert card.get_attribute('open') == ''
