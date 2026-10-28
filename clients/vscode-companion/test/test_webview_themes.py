"""Browser gates of WP-A5, INV-16 and A11Y-3 (scope S, simulated browser): the panel under the variable sets
of VS Code's Light+, Dark+ and High Contrast themes (``themes.py``), at 900 and 420 px,
on the **captured** payloads of the real engine (``test/fixtures/captured``), not only the
hand-written fixtures.

* the first viewport below the sticky region holds Now's heading and no raw result id (NOW-12);
* no text written for the agent is shown as primary content anywhere on the page, every fold
  and drawer open (the engine's record stays under "Details");
* chart text is drawn at most 2 px larger than the body text (no SVG upscaling), the
  baseline is grey and the model is the accent, intervals sit on an axis with 0 marked;
* every primary button has a visible border in High Contrast (and under forced colours);
  a disabled control is not marked by opacity alone;
* at 420 px nothing scrolls the page sideways and tables turn into cards.

Re-pointed at the one page (ADR 0004 d13); the tab bar's wrapping went with the tabs.

This is not a VS Code session: the variables are the built-in themes' values, set as the
host sets them.
"""
from __future__ import annotations

import re

import pytest

from conftest import inline_styles_ok
from panel_cases import OPEN_ONE

import themes

THEMES = ['light', 'dark', 'hc']
WIDTHS = [900, 420]
SUMMARIES = ['summary.binary', 'summary.regression', 'summary.binary.health', 'summary.v0.binary', 'summary.v0.regression']


def captured(name):
    return f'captured/{name}'


@pytest.fixture(scope='module')
def views(model, payload):
    """Every captured model, keyed by fixture name, and the raw summaries."""
    out = {name: model('summary', captured(name)) for name in SUMMARIES}
    for task in ['binary', 'regression']:
        out[f'decisions.{task}'] = model('decisions', captured(f'decisions.{task}'))
        out[f'evidence.{task}'] = model('evidence', captured(f'evidence.{task}'))
        out[f'eda.{task}'] = model('eda', captured(f'evidence.{task}'))
        out[f'whatif.{task}'] = model('whatif', captured(f'evidence.{task}'))
        out[f'explain.{task}'] = model('explain', captured(f'explain.{task}'))
    out['raw'] = {name: payload(captured(name)) for name in SUMMARIES}
    return out


def panel_for(open_panel, theme, width, summary, stage='v3', **init):
    panel = open_panel(color_scheme=themes.scheme(theme))
    panel.page.set_viewport_size({'width': width, 'height': 900})
    themes.apply(panel.page, theme)
    panel.init(stage=stage, task=summary['task'], panelContract=2, **init)
    panel.snapshot(summary)
    return panel


def feed(panel, views, task):
    """Every read delivered, every fold and drawer open (as a reader who opens everything)."""
    for _ in range(10):
        for view in ('decisions', 'evidence', 'eda', 'whatif', 'explain'):
            panel.view_data(view, views[f'{view}.{task}'])
        if panel.page.evaluate(OPEN_ONE) == 0:
            break
        panel.page.wait_for_timeout(30)


def clean(panel):
    assert not (panel.requests or panel.errors or panel.csp or panel.violations()), \
        (panel.requests, panel.errors, panel.csp, panel.violations())
    # The theme variables sit on <html> through CSSOM, as VS Code sets them; no element of
    # the panel has a style attribute (CSP).
    assert inline_styles_ok(panel.page)


def result_ids(raw):
    return sorted({str(r.get('result_id')) for r in (raw.get('results') or {}).values() if r and r.get('result_id')})


TEXT_ABOVE = """limit => {
  const out = [];
  // Lesson style (2026-10-27): the next move is the board callout above the tabs, so the
  // whole panel is read, from its top.
  const walker = document.createTreeWalker(document.getElementById('app'), NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const n = walker.currentNode;
    if (!n.textContent.trim()) continue;
    // A closed <details> shows only its summary.
    const d = n.parentElement.closest('details');
    if (d && !d.open && !n.parentElement.closest('summary')) continue;
    const range = document.createRange(); range.selectNodeContents(n);
    const r = range.getBoundingClientRect();
    if (r.height > 0 && r.top < limit) out.push(n.textContent);
  }
  return out.join(' ');
}"""


@pytest.mark.parametrize('theme', THEMES)
@pytest.mark.parametrize('width', WIDTHS)
@pytest.mark.parametrize('name', SUMMARIES)
def test_ov0_now12_the_first_viewport_holds_now_and_no_raw_result_id(open_panel, views, name, theme, width):
    """OV-0 → NOW-12: Now's heading is in the first viewport (800 px), and no raw result id,
    proposal id or rule token is there."""
    summary = views[name]
    stage = 'v0' if '.v0.' in name else 'v1'
    panel = panel_for(open_panel, theme, width, summary, stage=stage)
    page = panel.page
    now = page.locator('[data-block="now"] h2').first
    assert now.evaluate('h => h.getBoundingClientRect().top') < 800, 'Now starts in the first viewport'
    top = page.evaluate(TEXT_ABOVE, 800)
    assert now.text_content() in top
    for rid in result_ids(views['raw'][name]):
        assert rid[:8] not in top, f'raw result id {rid[:8]} in the first viewport'
    assert not re.search(r'\b[0-9a-f]{12,64}\b', top)
    assert not re.search(r'\bp_\d+\b|\b(capacity|threshold):[0-9.]+', top), 'no raw token in the first viewport'
    clean(panel)


@pytest.mark.parametrize('theme', THEMES)
@pytest.mark.parametrize('task, name', [('binary', 'summary.binary'), ('regression', 'summary.regression'),
                                        ('binary', 'summary.binary.health')])
def test_no_agent_text_is_primary_content_anywhere(open_panel, views, task, name, theme):
    summary = views[name]
    raw = views['raw'][name]
    panel = panel_for(open_panel, theme, 900, summary)
    feed(panel, views, task)
    agent = []
    if raw['next_action'].get('audience') == 'agent':
        agent.append(raw['next_action']['message'])
    agent += [i['text'] for i in raw['not_yet_defensible']['top'] if i.get('audience') == 'agent']
    agent += [a['message'] for a in raw['artifacts']['items'].values() if a.get('audience') == 'agent'
              and a['message'] != a.get('junior_message')]
    if raw.get('recap_audience') == 'agent':
        agent += [line for line in raw['recap'] if line not in (raw.get('recap_junior') or [])]
    assert agent, 'the captured payload has agent texts to keep out'
    page = panel.page
    # Every fold open; the engine's own record under "Details" (layer 2, §15.1) is left out.
    visible = page.evaluate("""() => { const m = document.getElementById('app').cloneNode(true);
      for (const d of m.querySelectorAll('details.ht-details')) d.remove();
      document.body.appendChild(m); const t = m.innerText; m.remove(); return t; }""")
    for text in agent:
        assert text not in visible, text
    assert 'could not be read' not in visible
    clean(panel)


CHART_SIZES = """() => {
  const body = parseFloat(getComputedStyle(document.body).fontSize);
  return [...document.querySelectorAll('svg.ht-chart')].filter(s => s.getBoundingClientRect().width > 0).map(svg => {
    const vb = (svg.getAttribute('viewBox') || '').split(/\\s+/).map(Number);
    const scale = vb.length === 4 && vb[2] ? svg.getBoundingClientRect().width / vb[2] : 1;
    const texts = [...svg.querySelectorAll('text')].map(t => parseFloat(getComputedStyle(t).fontSize) * scale);
    return {body, scale, max: Math.max(0, ...texts)};
  });
}"""


@pytest.mark.parametrize('theme', THEMES)
@pytest.mark.parametrize('width', WIDTHS)
@pytest.mark.parametrize('task', ['binary', 'regression'])
def test_chart_text_is_never_larger_than_body_text_plus_2px(open_panel, views, task, theme, width):
    panel = panel_for(open_panel, theme, width, views[f'summary.{task}'])
    feed(panel, views, task)
    page = panel.page
    seen = 0
    for chart in page.evaluate(CHART_SIZES):
        seen += 1
        assert chart['scale'] <= 1.0001, chart
        assert chart['max'] <= chart['body'] + 2, chart
    # v0.3 (WP-E2): nothing scrolls sideways, neither a chart nor the page.
    assert page.evaluate('document.scrollingElement.scrollWidth <= window.innerWidth + 1')
    assert seen > 0, 'charts were drawn'
    clean(panel)


def test_baseline_is_grey_model_is_the_accent_and_intervals_have_a_zero_axis(open_panel, views):
    panel = panel_for(open_panel, 'light', 900, views['summary.regression'])
    feed(panel, views, 'regression')
    page = panel.page
    # v0.3 (WP-E2): interval rows are an HTML grid; each interval is a line (its background colour).
    lines = page.locator('.ht-intervals [data-interval][data-tone]')
    assert lines.count() > 0, 'interval charts are drawn'
    tones = lines.evaluate_all('ls => ls.filter(l => l.getBoundingClientRect().width > 0).map(l => [l.dataset.tone, getComputedStyle(l).backgroundColor])')
    base = {s for t, s in tones if t == 'baseline'}
    accent = {s for t, s in tones if t == 'model'}
    assert base and accent and not (base & accent), tones
    for colour in base:
        r, g, b = [int(x) for x in re.findall(r'\d+', colour)[:3]]
        assert max(r, g, b) - min(r, g, b) <= 24, f'the baseline is grey, not a hue: {colour}'
    zero = page.locator('.ht-intervals [data-zero]')
    if zero.count():
        assert page.locator('.ht-intervals [data-axis] [data-literal="axis"]').first.text_content() == '0'
    assert page.locator('.ht-intervals [data-axis]').count() > 0, 'intervals sit on a drawn axis'
    clean(panel)


BORDERS = """sel => [...document.querySelectorAll(sel)].filter(b => b.getBoundingClientRect().width > 0).map(b => {
  const s = getComputedStyle(b);
  return {text: b.textContent.trim().slice(0, 40), width: parseFloat(s.borderTopWidth), style: s.borderTopStyle,
          color: s.borderTopColor, bg: s.backgroundColor, opacity: s.opacity, disabled: b.disabled};
})"""


def parse(colour):
    nums = [float(x) for x in re.findall(r'[\d.]+', colour)]
    return nums[:3], (nums[3] if len(nums) > 3 else 1.0)


@pytest.mark.parametrize('width', WIDTHS)
def test_high_contrast_primary_buttons_have_a_visible_border(open_panel, views, width):
    panel = panel_for(open_panel, 'hc', width, views['summary.binary'])
    feed(panel, views, 'binary')
    page = panel.page
    seen = 0
    for b in page.evaluate(BORDERS, '#app button:not(.ht-link):not(.ht-term)'):
        seen += 1
        rgb, alpha = parse(b['color'])
        assert b['width'] >= 1 and b['style'] != 'none', b
        assert alpha > 0.5 and rgb != [0.0, 0.0, 0.0], f'the border shows against the black page: {b}'
    assert seen >= 4
    # Now's one action is a primary button: the High Contrast border colour.
    assert page.locator('[data-block="now"] [data-copy-question]').evaluate('b => getComputedStyle(b).borderTopColor') == \
        'rgb(111, 195, 223)'
    clean(panel)


def test_forced_colors_keep_button_borders(open_panel, views):
    panel = panel_for(open_panel, 'light', 900, views['summary.binary'])
    panel.page.emulate_media(forced_colors='active')
    for b in panel.page.evaluate(BORDERS, '#app button:not(.ht-link):not(.ht-term)'):
        assert b['width'] >= 1 and b['style'] != 'none', b
    clean(panel)


@pytest.mark.parametrize('theme', THEMES)
def test_disabled_is_not_opacity_only(open_panel, model, theme):
    # WP-E1: the Decisions card has no write control any more; R31 (2026-10-27): nor has the
    # interrupted execution (W6 withdrawn). While a write runs, Refresh is disabled.
    panel = panel_for(open_panel, theme, 900, model('summary', 'summary.binary.health'))
    page = panel.page
    panel.send({'type': 'busy', 'busy': True, 'op': 'W5', 'target': 'render'})
    page.locator('[data-more]').click()
    selector = 'button[data-refresh]'
    button = page.locator(selector).first
    assert button.is_disabled()
    state = page.evaluate(BORDERS, selector)[0]
    assert float(state['opacity']) == 1.0
    assert state['style'] == 'dashed', 'a disabled control has a dashed border'
    clean(panel)


@pytest.mark.parametrize('theme', THEMES)
def test_420px_no_sideways_scroll_and_tables_are_cards(open_panel, views, theme):
    """A11Y-3 at 420 px, every fold and drawer open (NAR-1)."""
    panel = panel_for(open_panel, theme, 420, views['summary.binary'])
    feed(panel, views, 'binary')
    page = panel.page
    assert page.evaluate('document.scrollingElement.scrollWidth <= window.innerWidth + 1')
    table = page.locator('table[data-history]').first
    assert table.evaluate('t => getComputedStyle(t.querySelector("tbody tr")).display') == 'block'
    assert table.locator('td[data-label="Your words"]').count() > 0
    clean(panel)
