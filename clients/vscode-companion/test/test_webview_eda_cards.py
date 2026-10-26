"""EDA gallery cards and the "Run another chart" card (review 2026-10-24, panel minor items).

Simulated browser on the captured payloads (``panel_cases.py``); not a VS Code session.

* A per-column card and the request card ask the same question for the same chart: in
  English the engine's own question, in French the panel's translation of it; under
  cross-validation both name the development rows, never the training rows.
* A card the junior opened (or closed) stays so across a view re-render and the language
  toggle (view memory only, never study state).
"""
from __future__ import annotations

import copy

import pytest

from panel_cases import expand_eda, load_views, open_case
from test_webview_gate import show

PER_COLUMN = ('eda.distribution', 'eda.rate_by', 'eda.mean_by')


@pytest.fixture(scope='module')
def views(model, payload):
    return load_views(model, payload)


def gallery(views, case):
    return [c for c in views[f'eda.{case}']['cards'] if c['kind'] != 'quality']


def title(page, slot):
    return page.locator(f'[data-eda-card="{slot}"] summary h3').inner_text()


def eyebrow(page, slot):
    return page.locator(f'[data-eda-card="{slot}"] [data-eyebrow]').inner_text()


def request_question(page):
    return page.locator('.eda-request-question').inner_text()


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
    return out, card


@pytest.mark.parametrize('case', ['binary', 'regression'])
def test_english_gallery_titles_are_the_engine_questions(open_panel, views, case):
    panel = open_case(open_panel, views, case=case, lang='en')
    show(panel.page, 'eda')
    for card in gallery(views, case):
        assert title(panel.page, card['slot']) == card['question'], card['slot']


@pytest.mark.parametrize('lang', ['en', 'fr'])
@pytest.mark.parametrize('case, column, activity', [('binary', 'age', 'eda.distribution'),
                                                    ('binary', 'job', 'eda.rate_by'),
                                                    ('regression', 'model_year', 'eda.mean_by')])
def test_the_request_card_asks_the_question_of_the_card_it_adds(open_panel, views, lang, case, column, activity):
    panel = open_case(open_panel, views, case=case, lang=lang)
    page = panel.page
    show(page, 'eda')
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
    show(page, 'eda')
    assert 'développement' in eyebrow(page, card['slot']).lower()
    t = title(page, card['slot'])
    assert t == 'Comment les valeurs de age se répartissent-elles parmi les lignes de développement ?', t
    page.select_option('#eda-variable', 'age')
    page.select_option('#eda-chart', 'eda.distribution')
    q = request_question(page)
    assert "entraînement" not in q and q.endswith(t), q


def test_english_cross_validated_request_is_the_engine_question(open_panel, views):
    v, card = cv_views(views)
    panel = open_case(open_panel, v, case='cv', lang='en')
    page = panel.page
    show(page, 'eda')
    assert title(page, card['slot']) == card['question']
    page.select_option('#eda-variable', 'age')
    page.select_option('#eda-chart', 'eda.distribution')
    q = request_question(page)
    assert 'training rows' not in q and q.endswith(card['question']), q


def _details(page, slot):
    return page.locator(f'[data-eda-card="{slot}"] details.eda-analysis')


def test_an_opened_card_stays_open_across_a_rerender_and_the_language_toggle(open_panel, views):
    panel = open_case(open_panel, views, case='binary', lang='en')
    page = panel.page
    show(page, 'eda')
    first = _details(page, 'eda.target_rate')
    assert first.get_attribute('open') is None          # collapsed by default (not the last card)
    first.locator(':scope > summary').click()
    assert first.get_attribute('open') == ''
    # A view-local re-render (the junior picks another variable in "Run another chart").
    page.select_option('#eda-variable', 'age')
    assert first.get_attribute('open') == ''
    # A new read of the view re-renders it too.
    panel.view_data('eda', views['eda.binary'])
    assert first.get_attribute('open') == ''
    page.locator('[data-language="fr"]').click()
    assert first.get_attribute('open') == ''
    page.locator('[data-language="en"]').click()
    assert first.get_attribute('open') == ''
    # The others keep their default: only the last card starts open.
    slots = [c['slot'] for c in gallery(views, 'binary')]
    for slot in slots[1:-1]:
        assert _details(page, slot).get_attribute('open') is None, slot
    assert _details(page, slots[-1]).get_attribute('open') == ''


def test_a_closed_default_card_stays_closed_and_a_deep_link_opens_and_keeps_a_card(open_panel, views):
    panel = open_case(open_panel, views, case='binary', lang='en')
    page = panel.page
    show(page, 'eda')
    slots = [c['slot'] for c in gallery(views, 'binary')]
    last = _details(page, slots[-1])
    assert last.get_attribute('open') == ''
    last.locator(':scope > summary').click()
    assert last.get_attribute('open') is None
    page.select_option('#eda-variable', 'age')
    assert last.get_attribute('open') is None
    page.locator('[data-language="fr"]').click()
    assert last.get_attribute('open') is None
    # "Le montrer" / "Show it" opens a collapsed card (a deep link), which then stays open.
    page.locator('[data-language="en"]').click()
    page.select_option('#eda-variable', 'job')
    page.select_option('#eda-chart', 'eda.rate_by')
    card = _details(page, 'eda.rate_by:job')
    assert card.get_attribute('open') is None
    page.locator('#eda-show').click()
    assert card.get_attribute('open') == ''
    page.select_option('#eda-variable', 'age')
    assert card.get_attribute('open') == ''


def test_expand_eda_opens_every_card(open_panel, views):
    panel = open_case(open_panel, views, case='regression', lang='fr')
    show(panel.page, 'eda')
    assert panel.page.locator('details.eda-analysis:not([open])').count() > 0
    expand_eda(panel.page)
    assert panel.page.locator('details.eda-analysis:not([open])').count() == 0
    assert panel.page.locator('details.eda-analysis[open]').count() == len(gallery(views, 'regression'))
