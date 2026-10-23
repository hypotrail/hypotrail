"""The captured-payload cases of the panel's visual tests (WP-E2, shared with the WP-E3 gate).

``load_views(model, payload)`` builds the models of the captured payloads of the real engine
(``test/fixtures/captured``): the split Bank study (``binary``), the cross-validated Bank study
whose final test was opened (``cv``), the cross-validated Bank study with three variants
(``families``, v0.3 WP-K), and Auto MPG (``regression``). ``open_case`` opens the
panel on one of them under a theme of ``themes.py``, at a width, in a language, with every
view's read delivered. The page scripts below are the structural probes of the gate
(``test_webview_gate.py``). This is not a VS Code session.
"""
from __future__ import annotations

import themes

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

# Visible: laid out, not inside a closed disclosure, a hidden element or a screen-reader text.
VISIBLE = """
  const visible = n => {
    if (n.closest('[hidden], .sr-only')) return false;
    const d = n.closest('details');
    if (d && !d.open && !n.closest('summary')) return false;
    const r = n.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
"""

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


def load_views(model, payload) -> dict:
    out = {}
    for key, s in [('binary', 'summary.binary'), ('regression', 'summary.regression'), ('cv', 'summary.binary.cv'),
                   ('families', 'summary.binary.families')]:
        out[f'summary.{key}'] = model('summary', f'captured/{s}')
    # v0.3 (WP-K): `families` is the cross-validated Bank study with three variants (a stronger
    # penalty, an EBM, gradient boosting); `trials` is each study's full view at that point.
    for key, task, ev, dec, view in [
            ('binary', 'binary', 'evidence.binary', 'decisions.binary', 'status.binary'),
            ('regression', 'regression', 'evidence.regression', 'decisions.regression', 'status.regression'),
            ('cv', 'binary', 'evidence.binary.cv', 'decisions.binary.cv', 'status.binary.cv'),
            ('families', 'binary', 'evidence.binary.families', 'decisions.binary.families', 'status.binary.families')]:
        out[f'evidence.{key}'] = model('evidence', f'captured/{ev}')
        out[f'eda.{key}'] = model('eda', f'captured/{ev}')
        out[f'whatif.{key}'] = model('whatif', f'captured/{ev}')
        out[f'decisions.{key}'] = model('decisions', f'captured/{dec}')
        out[f'data.{key}'] = model('data', f'captured/data.{task}')
        out[f'explain.{key}'] = model('explain', f'captured/explain.{task}')
        out[f'trials.{key}'] = model('trials', f'captured/{view}')
    out['raw.evidence.binary'] = payload('captured/evidence.binary')
    out['raw.summary.binary'] = payload('captured/summary.binary')
    return out


def open_case(open_panel, views, case='binary', theme='light-modern', width=900, lang='en', stage='v3',
              height=900, before=None):
    """The panel on a captured case. ``before(page)`` runs after the page loaded and before
    any message (the pixel baselines fix the font and the clock there)."""
    panel = open_panel(color_scheme=themes.scheme(theme))
    panel.page.evaluate(STYLE_GUARD)
    panel.page.set_viewport_size({'width': width, 'height': height})
    themes.apply(panel.page, theme)
    if before:
        before(panel.page)
    summary = views[f'summary.{case}']
    panel.init(stage=stage, task=summary['task'])
    panel.snapshot(summary)
    if lang:
        # The toggle is UI state: press it as the junior would.
        panel.page.locator(f'[data-language="{lang}"]').click()
    for view in ['decisions', 'evidence', 'eda', 'whatif', 'explain', 'data', 'trials']:
        panel.view_data(view, views[f'{view}.{case}'])
    return panel


def expand_eda(page):
    """Open every collapsed EDA card, as the junior does (only the last one starts open)."""
    closed = page.locator('details.eda-analysis:not([open]) > summary')
    while closed.count():
        closed.first.click()
