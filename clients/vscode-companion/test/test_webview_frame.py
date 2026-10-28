"""Browser tests of the shared frame (scope S, simulated browser; COMPANION-ADVANCED §4.1, §12,
§13): the registered parts and their stages, the shared chart components, the palette-only SVG
colours under the real CSP, and the contrast of the text tokens. Not a VS Code session.

The tabbed frame's tests went with the tabs (ADR 0004 d13): the tab bar and its WAI-ARIA
pattern, the recap strip and the alert strip are withdrawn (§18: LS-1, OV-1, OV-2); stage
gating is PG-12 and the load error PG-11 (`test_webview_page.py`, `test_webview_header.py`);
reviewer mode and the regression vocabulary are checked on the whole page (RV-2, INV-12).
"""
from __future__ import annotations

import pytest

from conftest import inline_styles_ok


@pytest.fixture(scope='module')
def binary(model):
    return model('summary', 'summary.binary')


def test_each_part_is_registered_at_its_stage(open_panel, binary):
    """§3.2: one page renders; the other views are parts, registered at their stage (OP-1)."""
    panel = open_panel()
    panel.init(stage='v3', panelContract=2)
    panel.snapshot(binary)
    views = panel.page.evaluate('() => globalThis.Hypotrail.registered()')
    assert {v['name']: v['stage'] for v in views} == {'page': 'v0', 'overview': 'v0', 'decisions': 'v0', 'eda': 'v2',
                                                       'evidence': 'v2', 'whatif': 'v2', 'learn': 'v3'}
    assert panel.page.locator('[role="tablist"], [role="tab"], [role="tabpanel"], [data-placeholder]').count() == 0
    assert panel.clean()




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

