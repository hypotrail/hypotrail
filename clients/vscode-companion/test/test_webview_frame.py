"""Browser tests of the WP-0 frame (scope S, simulated browser; COMPANION-ADVANCED §3.2, §4.1,
§12, §13): stage gating of the tabs, the placeholders, reviewer mode, the WAI-ARIA tabs,
the shared chart components, the real CSP, the regression vocabulary, and the contrast of
the fallback theme tokens. Not a VS Code session.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from conftest import inline_styles_ok

TABS = ['overview', 'eda', 'decisions', 'evidence', 'whatif', 'learn']
STAGE_TABS = {'v0': [], 'v1': ['overview', 'decisions'],
              'v2': ['overview', 'eda', 'decisions', 'evidence', 'whatif'], 'v3': TABS}
FORBIDDEN = re.compile(r'\b(threshold|capacity|precision|recall|positive class|policy|calling rule|decision rule|selected)\b', re.I)


@pytest.fixture(scope='module')
def binary(model):
    return model('summary', 'summary.binary')


@pytest.fixture(scope='module')
def regression(model):
    return model('summary', 'summary.regression')


def _tabs(page):
    return page.locator('[role="tab"]').evaluate_all('ts => ts.map(t => t.dataset.tab)')


@pytest.mark.parametrize('stage', ['v0', 'v1', 'v2', 'v3'])
def test_tabs_of_a_later_stage_are_absent(open_panel, binary, stage):
    panel = open_panel()
    panel.init(stage=stage)
    panel.snapshot(binary)
    page = panel.page
    assert _tabs(page) == STAGE_TABS[stage]
    later = {'v0': ['v1', 'v2', 'v3'], 'v1': ['v2', 'v3'], 'v2': ['v3'], 'v3': []}[stage]
    for s in later:
        assert page.locator(f'[data-stage="{s}"]').count() == 0, s
    if stage == 'v0':
        # v0: one page, no tablist, the v0 sections only.
        assert page.locator('[role="tablist"]').count() == 0
        # WP-A5: the next move first, then the plan; the junior recap under Details.
        assert page.locator('main [data-ov]').first.get_attribute('data-ov') == 'hero'
        assert page.locator('[data-recap-details] li').count() == 5
        assert page.locator('[data-proposal-card]').count() == 1
    assert panel.clean(), (panel.requests, panel.errors, panel.csp, panel.violations())


def test_each_view_of_its_stage_is_registered_and_waits_busy_for_its_data(open_panel, binary):
    # WP-I: every tab has its real view (U1-U5), so no WP-0 placeholder is left. Without
    # its data a view waits, busy (§3.3 "Loading").
    panel = open_panel()
    panel.init(stage='v3')
    panel.snapshot(binary)
    page = panel.page
    views = page.evaluate('() => globalThis.Hypotrail.registered()')
    assert sorted(v['tab'] for v in views) == sorted(TABS), views
    assert {v['tab']: v['stage'] for v in views} == {'overview': 'v0', 'decisions': 'v0', 'eda': 'v2', 'evidence': 'v2',
                                                       'whatif': 'v2', 'learn': 'v3'}
    for tab in ['eda', 'evidence', 'whatif', 'learn']:
        page.locator(f'[role="tab"][data-tab="{tab}"]').click()
        shown = page.locator(f'#panel-{tab}')
        assert shown.is_visible()
        assert shown.locator('[data-placeholder]').count() == 0, tab
        assert shown.locator('[aria-busy="true"]').count() >= 1, tab
        assert page.locator('[data-recap-strip]').count() == 1, 'the recap strip is on every tab but Overview'
    page.locator('[role="tab"][data-tab="overview"]').click()
    assert page.locator('[data-recap-strip]').count() == 0
    assert panel.clean()


def test_tabs_follow_the_aria_pattern_and_remember_the_choice(open_panel, binary):
    panel = open_panel()
    panel.init(stage='v2')
    panel.snapshot(binary)
    page = panel.page
    first = page.locator('[role="tab"][data-tab="overview"]')
    assert first.get_attribute('aria-selected') == 'true'
    assert first.get_attribute('aria-controls') == 'panel-overview'
    first.focus()
    page.keyboard.press('ArrowRight')
    assert page.locator('[role="tab"][aria-selected="true"]').get_attribute('data-tab') == 'eda'
    page.keyboard.press('End')
    assert page.locator('[role="tab"][aria-selected="true"]').get_attribute('data-tab') == 'whatif'
    page.keyboard.press('Home')
    assert page.locator('[role="tab"][aria-selected="true"]').get_attribute('data-tab') == 'overview'
    page.keyboard.press('ArrowLeft')
    assert page.locator('[role="tab"][aria-selected="true"]').get_attribute('data-tab') == 'whatif'
    assert panel.state()['tab'] == 'whatif'
    assert page.locator('[role="tabpanel"]:not([hidden])').count() == 1
    badge = page.locator('[role="tab"][data-tab="decisions"] .ht-count')
    assert badge.get_attribute('aria-label') == f"{binary['waitingCount']} waiting for you"


def test_reviewer_mode_renders_no_write_control(open_panel, binary):
    panel = open_panel()
    panel.init(stage='v3', reviewer=True)
    panel.snapshot(binary)
    page = panel.page
    assert page.locator('[data-reviewer]').inner_text() == 'Reviewer, read-only'
    for tab in STAGE_TABS['v3']:
        page.locator(f'[role="tab"][data-tab="{tab}"]').click()
        assert page.locator('[data-write]:not([data-write="export"])').count() == 0, tab
        assert page.locator('textarea').count() == 0, tab


def test_alert_strip_and_navigation_to_health(open_panel, model):
    health = model('summary', 'summary.binary.health')
    panel = open_panel()
    panel.init(stage='v1')
    panel.snapshot(health)
    page = panel.page
    alerts = page.locator('[data-alert]')
    # WP-A5: not on the Overview (its first block is the next move); one alert per event
    # elsewhere (the unknown outcome is the interrupted execution), in the junior's words.
    assert alerts.count() == 0
    page.locator('[role="tab"][data-tab="decisions"]').click()
    assert alerts.evaluate_all('as => as.map(a => a.dataset.alert)') == ['outcome_unknown']
    assert alerts.first.get_attribute('role') == 'alert'
    assert alerts.first.locator('p').inner_text() == health['nextAction']['juniorMessage']
    alerts.first.get_by_role('button').click()
    assert page.locator('[role="tab"][aria-selected="true"]').get_attribute('data-tab') == 'overview'
    panel.send({'type': 'navigate', 'tab': 'decisions', 'kind': 'proposal', 'id': 'p_5'})
    assert page.locator('[role="tab"][aria-selected="true"]').get_attribute('data-tab') == 'decisions'
    assert page.evaluate('document.activeElement.closest("[data-nav]").dataset.nav') == 'proposal:p_5'


def test_load_error_replaces_the_content_and_gives_a_next_step(open_panel, binary):
    # WP-A5: the error state replaces the content (nothing read before is shown as current),
    # says what to do next, and keeps the CLI's message and stderr under Details.
    panel = open_panel()
    panel.init(stage='v1')
    panel.snapshot(binary)
    panel.send({'type': 'load_error', 'view': None, 'message': 'The hypotrail CLI could not be started.',
                'detail': 'stderr text'})
    banner = panel.page.locator('[data-load-error]')
    assert banner.get_attribute('role') == 'alert'
    assert f"Last read at revision {binary['revision']}" in banner.inner_text()
    assert 'Press Retry' in banner.locator('[data-next-step]').inner_text()
    assert banner.locator('details [data-error-message]').text_content() == 'The hypotrail CLI could not be started.'
    assert banner.locator('details pre').text_content() == 'stderr text'
    page = panel.page
    assert page.locator('main [data-load-error]').count() == 1
    assert page.locator('main section[data-tab]').count() == 0, 'no tab content under the error'
    assert page.locator('[data-ov="hero"], [data-proposal-card], .ht-alerts, [data-recap-strip]').count() == 0
    banner.get_by_role('button', name='Retry').click()
    assert panel.posted()[-1] == {'v': 2, 'type': 'refresh'}
    panel.snapshot(binary)
    assert page.locator('[data-load-error]').count() == 0
    assert page.locator('[data-ov="hero"]').count() == 1, 'the content is back once the study is read'


def test_components_render_geometry_hatch_values_and_citations(open_panel):
    panel = open_panel()
    page = panel.page
    page.evaluate("""() => {
      const HT = globalThis.Hypotrail, box = document.createElement('div');
      box.id = 'probe'; document.body.appendChild(box);
      HT.components.bars(box, {title: 'Outcome rate by job, training rows', max: 0.25, unit: 'rate',
        rule: {value: 0.115, label: 'overall'},
        items: [{label: 'retired', value: 0.233, valueText: '23.3%', small: false,
                 cited: {resultId: 'a'.repeat(64), path: 'groups.[retired].rate', value: 0.233}},
                {label: 'unknown', value: 0.192, valueText: '19.2%', small: true, cited: null}]});
      HT.components.intervalRows(box, {title: 'Precision difference', zero: true, rows: [
        {label: 'logistic - baseline', point: 0.245, low: 0.157, high: 0.345, pointText: '+0.245', intervalText: '[0.157, 0.345]'}]});
      HT.components.histogram(box, {title: 'Age', axisLabel: 'age', bins: [{low: 18, high: 25, count: 148, countText: '148'},
        {low: 25, high: 32, count: 642, countText: '642'}]});
      HT.components.boxplot(box, {title: 'mpg', min: 9, q25: 15.5, median: 19.95, q75: 25, max: 43.1,
        texts: {min: '9.0', q25: '15.5', median: '19.95', q75: '25.0', max: '43.1'}});
      HT.components.segments(box, [{text: 'Rate '}, {text: '11.5%', resultId: 'b'.repeat(64), path: 'rate', value: 0.1154}]);
    }""")
    probe = page.locator('#probe')
    # v0.3 (WP-E2): bars, interval rows and the histogram are HTML grids, the box plot an SVG;
    # each is an image with its accessible name.
    assert probe.locator('[role="img"]').count() == 4
    assert probe.locator('[role="img"]').first.get_attribute('aria-label') == 'Outcome rate by job, training rows'
    small = probe.locator('[data-small="true"]')
    assert small.locator('.ht-bar').get_attribute('data-hatched') == 'true'
    assert '(small)' in small.locator('.ht-lab').text_content()
    # Geometry: the bar's length is value / max, a custom property written through CSSOM.
    bar = probe.locator('[data-bar="retired"] .ht-bar')
    assert bar.get_attribute('style') == '--v: 93.20;'
    cited = probe.locator('.ht-val data[data-result-id]')
    assert cited.get_attribute('data-value') == '0.233'
    toggle = probe.locator('.ht-figure').first.locator('button[aria-controls]')
    assert toggle.inner_text() == 'Show values'
    assert toggle.get_attribute('aria-expanded') == 'false'
    toggle.click()
    assert toggle.get_attribute('aria-expanded') == 'true'
    assert probe.locator('table.ht-values').first.is_visible()
    data = probe.locator('data[data-result-id="' + 'b' * 64 + '"]')
    assert data.inner_text() == '11.5%' and data.get_attribute('title') == 'Source · bbbbbb · rate'
    assert probe.locator('[data-zero]').count() == 1
    assert inline_styles_ok(page), 'no inline style attribute (CSP)'
    assert panel.clean(), (panel.errors, panel.violations())


def test_svg_colours_come_from_the_palette_only(open_panel):
    panel = open_panel()
    with pytest.raises(Exception, match='palette'):
        panel.page.evaluate("() => globalThis.Hypotrail.svg('rect', {fill: '#ff0000'})")
    with pytest.raises(Exception, match='not allowed'):
        panel.page.evaluate("() => globalThis.Hypotrail.el('div', {style: 'color: red'})")


def test_regression_frame_and_loading_views_hold_no_decision_rule_vocabulary(open_panel, regression):
    panel = open_panel()
    panel.init(stage='v3', task='regression')
    panel.snapshot(regression)
    page = panel.page
    for tab in STAGE_TABS['v3']:
        page.locator(f'[role="tab"][data-tab="{tab}"]').click()
        text = page.locator('body').inner_text()
        assert not FORBIDDEN.search(text), (tab, FORBIDDEN.search(text).group(0))
    assert panel.clean()


def _luminance(hex_colour: str) -> float:
    rgb = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


CONTRAST = """pairs => {
  const probe = document.createElement('span');
  document.body.appendChild(probe);
  const rgb = value => {
    probe.style.setProperty('color', value);
    const c = getComputedStyle(probe).color;
    const m = c.match(/color\\(srgb ([0-9.]+) ([0-9.]+) ([0-9.]+)/) || c.match(/rgba?\\((\\d+), (\\d+), (\\d+)/);
    const scale = c.startsWith('color(') ? 1 : 255;
    return [1, 2, 3].map(i => Number(m[i]) / scale);
  };
  const lum = c => { const l = c.map(x => (x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4));
    return 0.2126 * l[0] + 0.7152 * l[1] + 0.0722 * l[2]; };
  const out = pairs.map(([fg, bg]) => { const a = lum(rgb(`var(${fg})`)), b = lum(rgb(`var(${bg})`));
    return [fg, bg, (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)]; });
  probe.remove();
  return out;
}"""
# The text tokens and the tinted chips (text on its tint) of the v0.3 design system.
TEXT_PAIRS = [['--ht-fg', '--ht-bg'], ['--ht-muted', '--ht-bg'], ['--ht-link', '--ht-bg'], ['--ht-faint', '--ht-bg'],
              ['--ht-fg', '--ht-surface'], ['--ht-muted', '--ht-surface'],
              ['--ht-accent-ink', '--ht-accent-tint'], ['--ht-warn', '--ht-warn-tint'], ['--ht-bad', '--ht-bad-tint'],
              ['--ht-seal', '--ht-seal-tint'], ['--ht-ok', '--ht-ok-tint'], ['--ht-info', '--ht-info-tint'],
              ['--ht-error-fg', '--ht-error-bg'], ['--ht-experiment-fg', '--ht-experiment-bg']]


@pytest.mark.parametrize('scheme, theme', [('light', None), ('dark', None), ('light', 'light-modern'),
                                           ('dark', 'dark-modern'), ('dark', 'hc')])
def test_text_tokens_contrast_at_least_4_5_to_1_in_both_fallback_themes(open_panel, scheme, theme):
    """A11Y-2 (v0.3, WP-E2): WCAG contrast of the text tokens against their background, computed
    in the browser from the resolved tokens (colour-mix surfaces included), in both fallback
    themes and under the Modern and High Contrast variable sets."""
    import themes
    panel = open_panel(color_scheme=scheme)
    if theme:
        themes.apply(panel.page, theme)
    for fg, bg, ratio in panel.page.evaluate(CONTRAST, TEXT_PAIRS):
        assert ratio >= 4.5, (scheme, theme, fg, bg, round(ratio, 2))


def test_recap_strip_shows_the_junior_recap_with_decisions_in_words(open_panel, model):
    # WP-A5 (two-layer copy): the strip on the other tabs is the engine's junior recap,
    # except its Decided line, which the panel writes from the decisions (no rule token).
    binary = model('summary', 'captured/summary.binary')
    panel = open_panel()
    panel.init(stage='v1', task='binary')
    panel.snapshot(binary)
    page = panel.page
    page.locator('[role="tab"][data-tab="decisions"]').click()
    # v0.3 (WP-E2): the strip is collapsed by default; the junior opens it.
    toggle = page.locator('[data-recap-strip] button')
    assert toggle.get_attribute('aria-expanded') == 'false' and page.locator('[data-recap-strip] li').count() == 0
    toggle.click()
    lines = page.locator('[data-recap-strip] li').all_inner_texts()
    junior = binary['recapJunior']
    assert [l.split(':')[0] for l in lines] == ['Goal', 'Decided', 'Now', 'Next', 'Limit']
    assert lines[0] == junior[0] and lines[2:] == junior[2:]
    assert lines[1] == ('Decided: the prediction moment: Before the first contact of the campaign, from the client file; '
                        'the variables you may use: 11 available · 1 uncertain, kept (contact) · 4 excluded '
                        '(campaign, day, duration, month); the split: Stratified random split, 30% of the rows for '
                        'validation; the success criterion: Adopt only if precision beats the baseline by at least 5 '
                        'points; the data preparation: Missing values not flagged, no capping, no log scale; '
                        # WP-B1: the variant the policy compares, in words
                        'the variant to compare: Compare with a more regularised variant; '
                        # The explicit binary model choice (main, 506180a), in words
                        'the model choice: Adopt the logistic model; '
                        'the decision rule: Select every case scored 0.2 or more.')
    strip = page.locator('[data-recap-strip]').inner_text()
    assert 'threshold:0.2' not in strip and 'result ' not in strip
    assert panel.clean()
