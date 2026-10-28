"""The cases of the panel's browser tests (WP-E2, the WP-E3 gate; the one page of ADR 0004 d13).

``load_views(model, payload)`` builds the models of the captured payloads of the real engine
(``test/fixtures/captured``): the split Bank study (``binary``), the cross-validated Bank study
whose final test was opened (``cv``), the cross-validated Bank study with three variants
(``families``, v0.3 WP-K), and Auto MPG (``regression``); and the five states of the approved
mockup under contract P1 (``STATES``, captured from a one-page Auto MPG study by
``fixtures/capture.py``, ``one_page``). ``open_case`` opens the
panel on one of them under a theme of ``themes.py``, at a width, in a language, with every
view's read delivered. The page scripts below are the structural probes of the gate
(``test_webview_gate.py``). This is not a VS Code session.
"""
from __future__ import annotations

import themes

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


# The five states of the approved mockup (ADR 0004 d13), captured under contract P1 from the
# engine (PANEL-ONE-PAGE-PLAN E-8): ``captured/summary.regression.<state>``. The review is an
# Auto MPG study created with ``init --automation until_final_test``; the others are one study.
STATES = ['step1', 'choice', 'reopened', 'review', 'done']


def load_views(model, payload) -> dict:
    out = {}
    for key, s in [('binary', 'captured/summary.binary'), ('regression', 'captured/summary.regression'),
                   ('cv', 'captured/summary.binary.cv'), ('families', 'captured/summary.binary.families')]:
        out[f'summary.{key}'] = model('summary', s)
    for state in STATES:
        out[f'summary.{state}'] = model('summary', f'captured/summary.regression.{state}')
    # The same study once a run was interrupted after the reopening: the interruption is the
    # engine's next action (it comes first), the preparation stays to confirm again.
    out['summary.interrupted'] = model('summary', 'captured/summary.regression.interrupted')
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
    # The P1 states read the one-page study's other payloads at the model choice (the same
    # result ids), and its seeded sample (§17.3).
    for view, name in [('evidence', 'evidence'), ('eda', 'evidence'), ('whatif', 'evidence'), ('decisions', 'decisions'),
                       ('explain', 'explain'), ('trials', 'status'), ('data', 'data')]:
        out[f'{view}.p1'] = model(view, f'captured/{name}.regression.onepage')
    out['raw.evidence.binary'] = payload('captured/evidence.binary')
    out['raw.summary.binary'] = payload('captured/summary.binary')
    return out


def set_language(page, lang):
    """The language radio of the "more" menu (LANG-1), pressed as the junior does."""
    page.locator('[data-more]').click()
    page.locator(f'[data-more-menu] [data-language="{lang}"]').click()
    page.keyboard.press('Escape')


def open_case(open_panel, views, case='binary', theme='light-modern', width=900, lang='en', stage='v3', height=900,
              before=None, reviewer=False, learning=True, panel_theme=None, deliver=True):
    """The panel on a case (a captured study, or one of STATES) under a theme, at a width, in a
    language, with every view's read delivered. ``before(page)`` runs after the page loaded and
    before any message (the pixel baselines fix the font and the clock there)."""
    panel = open_panel(color_scheme=themes.scheme(theme))
    panel.page.evaluate(STYLE_GUARD)
    panel.page.set_viewport_size({'width': width, 'height': height})
    themes.apply(panel.page, theme)
    if before:
        before(panel.page)
    summary = views[f'summary.{case}']
    reads = 'p1' if case in STATES or case == 'interrupted' else case
    panel.init(stage=stage, task=summary['task'], reviewer=reviewer, learningLayer=learning, panelContract=2)
    panel.snapshot(summary)
    if lang:
        set_language(panel.page, lang)
    if panel_theme:
        panel.page.locator('[data-more]').click()
        panel.page.locator(f'[data-more-menu] [data-theme="{panel_theme}"]').click()
        panel.page.keyboard.press('Escape')
    if deliver:
        deliver_views(panel, views, reads)
    # `goto` re-delivers the reads that opened folds ask for.
    panel.case_views, panel.case_reads = views, reads
    return panel


def goto(panel, *_):
    """The tabbed tests' "open the tab" on the one page (ADR 0004 d13): every fold and drawer
    open, as a reader who opens everything would see the page, so that the figures, cards and
    controls of the former tab are laid out at their places (Now, the path, the drawers)."""
    open_all(panel, getattr(panel, 'case_views', None), getattr(panel, 'case_reads', None))


def expand_eda(page):
    """Open every fold of the page, the EDA cards' analyses included."""
    for _ in range(10):
        if page.evaluate(OPEN_ONE) == 0:
            break
        page.wait_for_timeout(30)


def click_fold(page, fold_id):
    """Press a fold's summary as the junior does, and wait for its lazy body: the `toggle`
    event, which re-renders the page with the body, is dispatched after the click."""
    page.locator(f'details[data-fold-id="{fold_id}"] > summary').first.click()
    # The `toggle` event is a queued task, also when a fold closes: let it run (it records the
    # fold in setState) before the test sends the next message.
    page.evaluate('() => new Promise(r => setTimeout(r, 0))')
    page.wait_for_function("""id => { const d = document.querySelector(`details[data-fold-id="${id}"]`);
      return d && (!d.open || d.getAttribute('data-lazy') !== 'true' || d.children.length > 1); }""", arg=fold_id)


def deliver_views(panel, views, reads):
    for view in ['decisions', 'evidence', 'eda', 'whatif', 'explain', 'data', 'trials']:
        panel.view_data(view, views[f'{view}.{reads}'])


# Opens every closed fold at once through the page's own fold state (FOLD-1), then renders once:
# a lazy fold builds its body on that render (pressing them one by one would wait for each
# toggle event). Details without a fold id are opened in place.
OPEN_ONE = """() => {
  const HT = globalThis.Hypotrail;
  const closed = [...document.querySelectorAll('#app details:not([open])')]
    .filter(d => !d.closest('[data-popover]'));
  for (const d of closed) {
    const id = d.getAttribute('data-fold-id');
    if (id) HT.setFold(id, true); else d.open = true;
  }
  if (closed.some(d => d.getAttribute('data-fold-id'))) HT.rerender();
  return closed.length;
}"""


ANCHOR_OF = """slot => {
  const p = globalThis.Hypotrail.currentPage();
  for (const ph of p.path.phases) for (const st of ph.steps)
    for (const r of st.results || []) if (r.slot === slot) return `path:${st.id}/${slot}`;
  return null;
}"""


def open_result(panel, slot):
    """Go to a result's place in the path as a deep link does (NAV-1, `navigate {anchor}`) and
    open its "Where it comes from" fold, which reads the result's detail. Returns the figure's
    fold (``data-anchor="path:<step>/<slot>"``)."""
    page = panel.page
    anchor = page.evaluate(ANCHOR_OF, slot)
    assert anchor, f'{slot} has no place in the path'
    page.evaluate('s => globalThis.Hypotrail.setFold(`src-${s}`, true)', slot)
    panel.send({'type': 'navigate', 'anchor': anchor})
    return page.locator(f'[data-anchor="{anchor}"]')


def with_results(summary, items):
    """A WP-0 summary fixture with the result slots of a view model's cards or results that it
    predates (the one page lists a figure under its step only when the summary's ``results``
    name it, P1 §17.2). Captured fixtures need none of this."""
    out = dict(summary)
    results = dict(out.get('results') or {})
    for item in items:
        slot = item.get('slot')
        if item.get('promoted') is False:
            continue
        if slot and slot not in results and item.get('resultId'):
            results[slot] = {'resultId': item['resultId'], 'current': item.get('current') is not False,
                             'staleReason': item.get('staleReason'), 'integrity': None, 'channel': None}
    out['results'] = results
    return out


def show(panel, **models):
    """The tabbed tests' "open the tab" on the one page (ADR 0004 d13): deliver the given view
    models (``eda=..., evidence=...``) as the opened folds ask for them, opening every fold and
    drawer, so that each figure, card and control of those views is laid out at its place (the
    path's details, Now, the drawers). The first opening happens before any delivery, so the
    reads the page asks for can be asserted."""
    page = panel.page
    for _ in range(10):
        n = page.evaluate(OPEN_ONE)
        page.wait_for_timeout(30)
        for view, data in models.items():
            panel.view_data(view, data)
        if n == 0:
            break
    page.evaluate('() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))')
    return panel


def open_all(panel, views=None, reads=None, rounds=10):
    """Open every fold and drawer of the page, as a junior who reads everything would: each
    opening of a lazy fold re-renders the page with its body, which may hold more folds; the
    reads its body asks for are delivered again when `views` is given."""
    page = panel.page
    for _ in range(rounds):
        n = page.evaluate(OPEN_ONE)
        page.wait_for_timeout(30)
        if views is not None:
            deliver_views(panel, views, reads)
        if n == 0:
            break
    page.evaluate('() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))')
