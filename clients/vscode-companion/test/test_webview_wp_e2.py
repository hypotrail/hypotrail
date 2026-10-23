"""v0.3 WP-E2 (scope S, simulated browser): the design system, the fluid charts, the panel
language, the journey bar and the panel's explanation.

The real document under the real CSP, offline, on the **captured** payloads of the real
engine (``test/fixtures/captured``): the split Bank study, the cross-validated Bank study whose
final test was opened, and Auto MPG; under the Light Modern, Dark Modern and High Contrast
variable sets (``themes.py``), at 900 and 420 px, in English and in French.

The structural matrix (every tab, three widths, three themes, both languages) and the pixel
baselines moved to the WP-E3 gate, ``test_webview_gate.py``; the cases and the page probes are
shared in ``panel_cases.py``. Requirement ids: R12,
R17, R21, R26, R28, I1, A11Y-3. This is not a VS Code session.
"""
from __future__ import annotations

import copy
import re

import pytest

from panel_cases import TABS, expand_eda, load_views, open_case

@pytest.fixture(scope='module')
def views(model, payload):
    return load_views(model, payload)


def test_the_served_document_holds_no_style_attribute(page_file):
    html = page_file.read_text(encoding='utf-8')
    body = html[html.index('<body>'):]
    assert ' style=' not in body.split('<script')[0]
    assert "setAttribute('style'" not in html and 'setAttribute("style"' not in html


# --- R21: the panel language ---------------------------------------------------------------

def test_the_language_toggle_is_ui_state_only(open_panel, views):
    panel = open_case(open_panel, views, lang=None)
    page = panel.page
    assert page.evaluate('document.documentElement.lang') == 'en'
    assert page.locator('[data-tab="overview"][role="tab"]').inner_text() == 'Overview'
    before = len(panel.posted())
    page.locator('[data-language="fr"]').click()
    assert page.evaluate('document.documentElement.lang') == 'fr'
    assert page.locator('[data-tab="overview"][role="tab"]').inner_text() == "Vue d'ensemble"
    assert page.locator('[data-language="fr"]').get_attribute('aria-pressed') == 'true'
    assert panel.state()['language'] == 'fr'
    # Nothing is sent: no write, no read, no message at all for a language switch.
    assert panel.posted()[before:] == []
    page.locator('[data-language="en"]').click()
    assert page.locator('[data-tab="overview"][role="tab"]').inner_text() == 'Overview'


def test_auto_follows_the_study_language_and_the_setting_overrides_it(open_panel, views):
    summary = copy.deepcopy(views['summary.binary'])
    summary['language'] = 'fr'
    panel = open_panel()
    panel.init(stage='v1', task='binary')
    panel.snapshot(summary)
    assert panel.page.evaluate('document.documentElement.lang') == 'fr'
    panel.send({'type': 'init', 'stage': 'v1', 'reviewer': False, 'learningLayer': True, 'chatInsert': False,
                'task': 'binary', 'study': '0123456789abcdef', 'language': 'en'})
    assert panel.page.evaluate('document.documentElement.lang') == 'en'


def test_an_english_engine_text_is_marked_in_a_french_panel(open_panel, views):
    panel = open_case(open_panel, views, lang='fr')
    page = panel.page
    page.locator('[role="tab"][data-tab="eda"]').click()
    markers = page.locator('#panel-eda [data-en-marker]')
    assert markers.count() >= 1
    assert markers.first.inner_text() == '(en)'
    assert markers.first.evaluate('n => n.parentElement.getAttribute("lang")') == 'en'
    page.locator('[data-language="en"]').click()
    assert page.locator('[data-en-marker]').count() == 0


def test_the_dictionary_meanings_follow_the_panel_language_with_their_own_toggle(open_panel, views):
    """R12 merged into R21: the Meaning column names its language and switches alone."""
    panel = open_case(open_panel, views, lang='en')
    page = panel.page
    page.locator('[role="tab"][data-tab="eda"]').click()
    toggle = page.locator('[data-french-toggle]')
    if toggle.count() == 0:
        pytest.skip('the captured case has no French labels')
    assert page.locator('[data-description="en"]').count() > 0
    page.locator('[data-meanings="fr"]').click()
    assert page.locator('[data-description="fr"]').count() > 0
    assert page.locator('[data-tab="overview"][role="tab"]').inner_text() == 'Overview', 'the panel stays English'


# --- R17, R28: the charts ------------------------------------------------------------------

def test_a_skewed_distribution_shows_its_zeros_apart_on_log_bins(open_panel, views):
    panel = open_case(open_panel, views)
    page = panel.page
    page.locator('[role="tab"][data-tab="eda"]').click()
    card = page.locator('[data-eda-card="eda.distribution:previous"]')
    assert card.count() == 1
    assert card.locator('[data-zero-tile]').count() == 1
    assert card.locator('[data-zero-tile] data[data-result-id]').first.get_attribute('data-path') == 'numeric.zeros.share'
    assert card.locator('[data-log-scale]').count() == 1 or card.locator('details.ht-why').count() == 1
    stats = card.locator('[data-numeric-line]').inner_text()
    for word in ['Median', 'IQR', 'Mean', 'Max']:
        assert word in stats
    # One visible title: the question; the chart's name is its accessible name only.
    assert card.locator('h3').count() == 1
    assert card.locator('figcaption.sr-only').count() >= 1
    # The axis names bin edges; bar heights are CSSOM custom properties.
    assert card.locator('.ht-xax [data-literal="axis"]').count() >= 3
    assert card.locator('.ht-cols > i').first.get_attribute('style').startswith('--v:')


def test_the_rate_by_chart_is_a_point_an_interval_a_band_and_n(open_panel, views):
    panel = open_case(open_panel, views)
    page = panel.page
    page.locator('[role="tab"][data-tab="eda"]').click()
    expand_eda(page)
    card = page.locator('[data-eda-card="eda.rate_by:job"]')
    rows = card.locator('[data-bar]')
    assert rows.count() > 3
    assert card.locator('[data-point]').count() == rows.count()
    assert card.locator('[data-interval]').count() >= rows.count() - 1
    assert card.locator('[data-band]').count() >= 1
    assert card.locator('[data-rule]').count() == rows.count()
    assert ' n ' in f" {rows.first.inner_text()} " or 'n ' in rows.first.inner_text() or 'n ' in rows.first.inner_text()
    # The caveats are behind "Why?", one disclosure per card.
    assert card.locator('details.ht-why').count() == 1
    assert card.locator('[data-noncausal]').evaluate('n => n.closest("details").open') is False


def test_the_correlation_matrix_reads_no_target_and_outlines_collinear_pairs(open_panel, views):
    panel = open_case(open_panel, views)
    page = panel.page
    page.locator('[role="tab"][data-tab="eda"]').click()
    raw = next(r for r in views['raw.evidence.binary']['results'] if r['activity'] == 'eda.correlation')
    values = raw['values']
    card = page.locator('[data-eda-card="eda.correlation"]')
    assert card.count() == 1
    n = len(values['columns'])
    assert card.locator('[data-pair]').count() == n * (n - 1) // 2
    flagged = [p for p in values['pairs'] if p['flag']]
    assert card.locator('[data-pair][data-flag="true"]').count() == len(flagged)
    first = values['pairs'][0]
    cell = card.locator(f'[data-pair="{first["b"]}|{first["a"]}"], [data-pair="{first["a"]}|{first["b"]}"]').first
    if first['value'] is not None:
        assert float(cell.locator('data').get_attribute('data-value')) == first['value']
    assert card.locator('[data-collinear]').count() == 1
    assert 'y' not in [c['name'] for c in values['columns']]


def test_the_correlation_matrix_is_requested_as_w4_without_a_column(open_panel, views):
    evidence = copy.deepcopy(views['eda.binary'])
    evidence['cards'] = [c for c in evidence['cards'] if c['activity'] != 'eda.correlation']
    panel = open_case(open_panel, views)
    panel.view_data('eda', evidence)
    page = panel.page
    page.locator('[role="tab"][data-tab="eda"]').click()
    page.locator('[data-whole="eda.correlation"] [data-write="run_eda"]').click()
    sent = [m for m in panel.posted() if m['type'] == 'run_eda'][-1]
    assert sent['activity'] == 'eda.correlation' and 'column' not in sent


def test_the_confusion_matrix_is_a_two_by_two_with_counts_and_rates(open_panel, views):
    panel = open_case(open_panel, views, case='cv')
    page = panel.page
    page.locator('[role="tab"][data-tab="evidence"]').click()
    cm = page.locator('[data-confusion="development"]').first
    assert cm.locator('[data-cell]').count() == 4
    assert cm.locator('[data-cell] data[data-result-id]').count() == 4
    rates = page.locator('[data-confusion-rates]').first.locator('data[data-result-id]')
    assert rates.count() == 3


def test_a_curve_follows_its_container(open_panel, views):
    panel = open_case(open_panel, views, case='cv', width=900)
    page = panel.page
    page.locator('[role="tab"][data-tab="evidence"]').click()
    svg = page.locator('[data-diag-chart="calibration"] svg.ht-chart').first
    wide = float(svg.get_attribute('width'))
    page.set_viewport_size({'width': 420, 'height': 900})
    page.wait_for_function("""w => { const s = document.querySelector('[data-diag-chart="calibration"] svg.ht-chart');
      return s && Number(s.getAttribute('width')) < w; }""", arg=wide)
    svg = page.locator('[data-diag-chart="calibration"] svg.ht-chart').first
    box = svg.bounding_box()
    assert abs(box['width'] - float(svg.get_attribute('width'))) < 1.5, 'one SVG unit per CSS pixel'
    assert svg.get_attribute('role') == 'img' and svg.get_attribute('aria-label')


# --- the card pattern, the recap, the journey, the explanation (R26, I1) --------------------------

def test_cards_put_provenance_in_a_faint_source_line(open_panel, views):
    panel = open_case(open_panel, views)
    page = panel.page
    page.locator('[role="tab"][data-tab="eda"]').click()
    expand_eda(page)
    for card in page.locator('[data-eda-card]').all():
        src = card.locator('.ht-card-f .ht-src')
        assert src.count() == 1
        assert re.search(r'· [0-9a-f]{6}$', src.inner_text())
        assert card.locator('h3').count() == 1


def test_the_recap_is_collapsed_and_shown_off_the_overview_only(open_panel, views):
    panel = open_case(open_panel, views)
    page = panel.page
    assert page.locator('[data-recap-strip]').count() == 0
    page.locator('[role="tab"][data-tab="eda"]').click()
    strip = page.locator('[data-recap-strip]')
    assert strip.count() == 1
    assert strip.locator('button').get_attribute('aria-expanded') == 'false'
    assert strip.locator('li').count() == 0


def test_the_journey_bar_lists_every_step_once_and_says_how_many_are_done(open_panel, views):
    panel = open_case(open_panel, views)
    page = panel.page
    plan = views['summary.binary']['plan']
    bar = page.locator('[data-ov="map"] .ht-journey')
    assert bar.locator('li[data-step]').count() == len(plan)
    assert [x for x in bar.locator('li[data-step]').evaluate_all('ls => ls.map(l => l.dataset.step)')] == [s['id'] for s in plan]
    assert bar.locator('li[aria-current="step"]').count() <= 1
    done = sum(1 for s in plan if s['status'] == 'done')
    assert page.locator('[data-steps-done]').get_attribute('data-steps-done') == f'{done}/{len(plan)}'


def test_the_overview_explains_the_panel_and_each_tab(open_panel, views):
    panel = open_case(open_panel, views)
    page = panel.page
    guide = page.locator('[data-ov="guide"]')
    assert guide.count() == 1
    assert 'chat' in guide.inner_text()
    guide.locator('details.ht-why summary').click()
    assert guide.locator('dt').count() == len(TABS)
    # The next move stays first.
    assert page.locator('[data-ov="hero"]').evaluate('h => h.getBoundingClientRect().top') < \
        guide.evaluate('g => g.getBoundingClientRect().top')
