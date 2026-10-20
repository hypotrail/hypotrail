"""v0.3 WP-E2 (scope S, simulated browser): the design system, the fluid charts, the panel
language, the journey bar and the panel's explanation.

The real document under the real CSP, offline, on the **captured** payloads of the real
engine (``test/fixtures/captured``): the split Bank study, the cross-validated Bank study whose
final test was opened, and Auto MPG; under the Light Modern, Dark Modern and High Contrast
variable sets (``themes.py``), at 900 and 420 px, in English and in French.

Structural assertions (the pixel baselines are WP-E3):

* nothing scrolls sideways and no element's right edge passes the viewport, except inside the
  dictionary and the five example rows (``data-scroll-ok``);
* no raw result id, proposal id or rule token in the prose (the faint source lines,
  ``.ht-src``, are the only place an id prefix shows);
* no number is underlined;
* a style attribute exists only where CSSOM set custom properties (``--v``, ``--x`` ...):
  none is in the document the extension serves, none is created with ``setAttribute``
  (``STYLE_GUARD`` records any such call), and every one holds custom properties only.

With ``HYPOTRAIL_SHOTS=<dir>`` the tests also write one screenshot per tab, theme, width and
language there, for a person to look at; nothing is asserted on them. Requirement ids: R12,
R17, R21, R26, R28, I1, A11Y-3. This is not a VS Code session.
"""
from __future__ import annotations

import copy
import os
import re
from pathlib import Path

import pytest

import themes

SHOTS = os.environ.get('HYPOTRAIL_SHOTS')
THEMES = ['light-modern', 'dark-modern', 'hc']
WIDTHS = [900, 420]
LANGS = ['en', 'fr']
TABS = ['overview', 'eda', 'decisions', 'evidence', 'whatif', 'learn']

# Records every setAttribute('style', ...) of the page (the CSP forbids inline style
# attributes; CSSOM writes of custom properties are the one allowed way to size a mark).
STYLE_GUARD = """() => {
  window.__styleAttrs = [];
  const original = Element.prototype.setAttribute;
  Element.prototype.setAttribute = function (name, value) {
    if (String(name).toLowerCase() === 'style') window.__styleAttrs.push(String(value));
    return original.call(this, name, value);
  };
}"""

OVERFLOW = """() => {
  const vw = document.documentElement.clientWidth;
  const out = [];
  for (const n of document.querySelectorAll('#app *')) {
    if (n.closest('[data-scroll-ok], [hidden], details:not([open]) > :not(summary), .sr-only')) continue;
    // A table head clipped to one pixel on a narrow panel (its cells are labelled instead).
    const head = n.closest('thead');
    if (head && head.getBoundingClientRect().width <= 1) continue;
    const r = n.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    if (r.right > vw + 1) out.push(`${n.tagName.toLowerCase()}.${n.className && n.className.baseVal === undefined ? n.className : ''} ${Math.round(r.right)} > ${vw}: ${(n.textContent || '').slice(0, 40)}`);
  }
  return {scroll: document.scrollingElement.scrollWidth, vw, out: out.slice(0, 10)};
}"""

PROSE = """() => {
  const out = [];
  const walker = document.createTreeWalker(document.getElementById('app'), NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const n = walker.currentNode;
    const p = n.parentElement;
    if (!n.textContent.trim() || !p) continue;
    if (p.closest('.ht-src, code, pre, [hidden], .sr-only, option, [data-scroll-ok]')) continue;
    const d = p.closest('details');
    if (d && !d.open && !p.closest('summary')) continue;
    const r = p.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    out.push(n.textContent);
  }
  return out.join(' \\n ');
}"""

UNDERLINED = """() => [...document.querySelectorAll('data[data-result-id]')]
  .filter(n => getComputedStyle(n).textDecorationLine !== 'none').length"""

STYLE_ATTRS = """() => [...document.querySelectorAll('#app [style]')].map(n => n.getAttribute('style'))"""


def shot(page, name):
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(SHOTS) / f'{name}.png'), full_page=True)
        # Readable parts of a tall page, 1600 px each (screenshots do not touch the DOM).
        width, height = page.evaluate('[document.documentElement.scrollWidth, document.documentElement.scrollHeight]')
        if height > 1600:
            (Path(SHOTS) / 'parts').mkdir(exist_ok=True)
            for i, top in enumerate(range(0, height, 1600)):
                page.screenshot(path=str(Path(SHOTS) / 'parts' / f'{name}.p{i + 1}.png'), full_page=True,
                                clip={'x': 0, 'y': top, 'width': width, 'height': min(1600, height - top)})


@pytest.fixture(scope='module')
def views(model, payload):
    out = {}
    for key, s in [('binary', 'summary.binary'), ('regression', 'summary.regression'), ('cv', 'summary.binary.cv')]:
        out[f'summary.{key}'] = model('summary', f'captured/{s}')
    for key, task, ev, dec in [('binary', 'binary', 'evidence.binary', 'decisions.binary'),
                               ('regression', 'regression', 'evidence.regression', 'decisions.regression'),
                               ('cv', 'binary', 'evidence.binary.cv', 'decisions.binary.cv')]:
        out[f'evidence.{key}'] = model('evidence', f'captured/{ev}')
        out[f'eda.{key}'] = model('eda', f'captured/{ev}')
        out[f'whatif.{key}'] = model('whatif', f'captured/{ev}')
        out[f'decisions.{key}'] = model('decisions', f'captured/{dec}')
        out[f'data.{key}'] = model('data', f'captured/data.{task}')
        out[f'explain.{key}'] = model('explain', f'captured/explain.{task}')
    out['raw.evidence.binary'] = payload('captured/evidence.binary')
    out['raw.summary.binary'] = payload('captured/summary.binary')
    return out


def open_case(open_panel, views, case='binary', theme='light-modern', width=900, lang='en', stage='v3'):
    panel = open_panel(color_scheme=themes.scheme(theme))
    panel.page.evaluate(STYLE_GUARD)
    panel.page.set_viewport_size({'width': width, 'height': 900})
    themes.apply(panel.page, theme)
    summary = views[f'summary.{case}']
    panel.init(stage=stage, task=summary['task'])
    panel.snapshot(summary)
    if lang:
        # The toggle is UI state: press it as the junior would.
        panel.page.locator(f'[data-language="{lang}"]').click()
    for view in ['decisions', 'evidence', 'eda', 'whatif', 'explain', 'data']:
        panel.view_data(view, views[f'{view}.{case}'])
    return panel


def structural(panel, where):
    page = panel.page
    o = page.evaluate(OVERFLOW)
    assert o['scroll'] <= o['vw'] + 1 and not o['out'], (where, o)
    prose = page.evaluate(PROSE)
    assert not re.search(r'\b[0-9a-f]{12,64}\b', prose), (where, re.search(r'\b[0-9a-f]{12,64}\b', prose).group(0))
    assert not re.search(r'\bp_\d+\b|\b(capacity|threshold|share):[0-9.]+', prose), where
    assert page.evaluate(UNDERLINED) == 0, where
    styles = page.evaluate(STYLE_ATTRS)
    assert all(re.fullmatch(r'(\s*--[a-z-]+:\s*[^;]+;?)+\s*', s) for s in styles), (where, [s for s in styles if '--' not in s][:3])
    assert page.evaluate('window.__styleAttrs') == [], where
    assert not (panel.requests or panel.errors or panel.csp or panel.violations()), \
        (where, panel.requests, panel.errors, panel.csp, panel.violations())


def test_the_served_document_holds_no_style_attribute(page_file):
    html = page_file.read_text(encoding='utf-8')
    body = html[html.index('<body>'):]
    assert ' style=' not in body.split('<script')[0]
    assert "setAttribute('style'" not in html and 'setAttribute("style"' not in html


@pytest.mark.parametrize('lang', LANGS)
@pytest.mark.parametrize('width', WIDTHS)
@pytest.mark.parametrize('theme', THEMES)
def test_every_tab_fits_and_keeps_ids_out_of_the_prose(open_panel, views, theme, width, lang):
    """A11Y-3, A11Y-4, R26: every tab at 900 and 420 px, three themes, both languages."""
    for case in ['binary', 'cv']:
        panel = open_case(open_panel, views, case=case, theme=theme, width=width, lang=lang)
        page = panel.page
        for tab in TABS:
            page.locator(f'[role="tab"][data-tab="{tab}"]').click()
            page.wait_for_timeout(30)
            structural(panel, f'{case}/{tab}/{theme}/{width}/{lang}')
            assert page.locator(f'#panel-{tab} [data-tab-lead="{tab}"]').count() == 1, (tab, 'one lead sentence per tab (I1)')
            if case == 'binary' or tab in ('overview', 'evidence'):
                shot(page, f'{tab}-{case}-{theme}-{width}-{lang}')


@pytest.mark.parametrize('width', WIDTHS)
def test_regression_tabs_fit_in_french(open_panel, views, width):
    panel = open_case(open_panel, views, case='regression', theme='light-modern', width=width, lang='fr')
    for tab in TABS:
        panel.page.locator(f'[role="tab"][data-tab="{tab}"]').click()
        structural(panel, f'regression/{tab}/{width}')
        shot(panel.page, f'{tab}-regression-light-modern-{width}-fr')


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
