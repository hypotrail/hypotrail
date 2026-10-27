"""v0.3 WP-E3 (scope S, simulated browser): the panel's visual gate, on the one page (ADR 0004
d13; PANEL-ONE-PAGE-PLAN P-6, P-7).

The real document under the real CSP, offline, on the **captured** payloads of the real
engine and the five contract-P1 states of the mockup (``panel_cases.py``). Two layers:

1. **Structural assertions**, on the page of the split and the cross-validated Bank studies,
   the cross-validated Bank study with three variants (v0.3, WP-K), the five P1 states, and
   Auto MPG in French, at 320, 420, 600 and 900 px (§13.5), under Light Modern, Dark Modern
   and High Contrast (``themes.py``), in English and in French, as first rendered and with
   every fold and drawer open:

   * nothing scrolls sideways: no element's right edge passes the viewport, and none passes
     the right edge of its card (a ``section``, ``article`` or ``.card``), except inside the
     dictionary and the sample (``data-scroll-ok``);
   * the type scale: every visible text is set at one of the six sizes of the design system
     (caption, meta, body, title, page, stat; ``tokens.css``), chart text at 10 to 13 px, and
     monospace holds identifiers only (three words at most);
   * no raw result id, proposal id, rule token, ``key:value`` token or ``snake_case``
     identifier in the prose (the faint source lines, code, the junior's quoted words, file
     names and the study's own column names, which engine texts quote, are the places they
     may show);
   * nothing is underlined: neither the numbers nor any prose word (links included: the panel
     marks links by colour);
   * a style attribute holds CSSOM custom properties only, and none is created with
     ``setAttribute`` (CSP, WP-E2 decision E2.2);
   * no remote request, page error or CSP violation.

   And per theme, the contrast of the text tokens against the page and card backgrounds (WCAG
   AA, 4.5:1; 7:1 for the main text in High Contrast), of the chip inks on their tints, and of
   the button texts on their buttons.

2. **Pixel baselines** (``test/baselines/*.png``): the page of each of the five P1 states at
   420 and 900 px, Light Modern, Dark Modern and High Contrast, English and French; the first
   viewport (800 px high), and the choice state's comparison figure. Rendering is
   pinned: the DejaVu Sans and DejaVu Sans Mono fonts (installed, never fetched), reduced
   motion and no animation, a fixed clock, locale and time zone, a device scale of 1. The
   comparison runs inside Chromium (two canvases): a pixel differs when a channel moves by more
   than 24; more than 0.1 % of differing pixels fails. The failing captures, their baselines
   and a diff image (differing pixels in red over a faded baseline) are written to
   ``clients/vscode-companion/.local/baseline-diff/`` (``HYPOTRAIL_BASELINE_DIFF`` overrides).

   ``--update-baselines`` (or ``HYPOTRAIL_UPDATE_BASELINES=1``) rewrites the baselines that
   differ or are missing and writes their diff images too; the owner reviews every baseline
   change from those diff images before it is committed (CONTRIBUTING). The 108 baselines of
   the tabbed panel were deleted with the tabs (P-7); until the owner has reviewed and
   committed the one-page set, the pixel tests skip ("one-page baselines awaiting owner
   review") unless a local set exists. The baselines are drawn on Linux; without the DejaVu
   fonts (``fc-match``) the pixel tests skip with a warning, and the structural ones still run.

With ``HYPOTRAIL_SHOTS=<dir>`` the structural tests also write full-page screenshots for a
person to look at (WP-E2). Requirement ids: A11Y-3, A11Y-4, R21, R26. This is not a VS Code
session.
"""
from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

import themes
from panel_cases import OVERFLOW, PROSE, STATES, STYLE_ATTRS, UNDERLINED, VISIBLE, load_views, open_all, open_case

HERE = Path(__file__).resolve().parent
BASELINES = HERE / 'baselines'
DIFFS = Path(os.environ.get('HYPOTRAIL_BASELINE_DIFF') or HERE.parent / '.local' / 'baseline-diff')
SHOTS = os.environ.get('HYPOTRAIL_SHOTS')

THEMES = ['light-modern', 'dark-modern', 'hc']
WIDTHS = [320, 420, 600, 900]
LANGS = ['en', 'fr']

# The pixel subset (owner budget: the baselines stay well under 15 MB).
PIXEL_WIDTHS = [900, 420]
PIXEL_HEIGHT = 800
CHART_MAX_HEIGHT = 640
# The main figure of a state: the first of these selectors that matches a visible element.
MAIN_CHART = {
    'choice': ['[data-block="now"] .ht-figure'],
}
# A one-page baseline: `<state>-<theme>-<width>-<lang>.png` (or `<state>-chart-...`).
ONE_PAGE = re.compile(r'^(%s)-' % '|'.join(STATES))
CHANNEL_DELTA = 24
MAX_SHARE = 0.001
FONT = 'DejaVu Sans'
MONO = 'DejaVu Sans Mono'
CLOCK = '2026-10-20T09:30:00Z'

# --- structural probes ---------------------------------------------------------------------

# Every visible element must stay inside the right edge of its card.
CARD_OVERFLOW = """() => {
""" + VISIBLE + """
  const out = [];
  for (const card of document.querySelectorAll('#app section, #app article, #app .card')) {
    if (!visible(card) || card.closest('[data-scroll-ok]')) continue;
    const right = card.getBoundingClientRect().right;
    if (card.scrollWidth > card.clientWidth + 1 && getComputedStyle(card).overflowX !== 'visible') {
      out.push(`${card.className || card.tagName} scrolls: ${card.scrollWidth} > ${card.clientWidth}`);
    }
    for (const n of card.querySelectorAll('*')) {
      if (n.closest('[data-scroll-ok]') || !visible(n)) continue;
      const head = n.closest('thead');
      if (head && head.getBoundingClientRect().width <= 1) continue;
      const r = n.getBoundingClientRect();
      if (r.right > right + 1) out.push(`${n.tagName.toLowerCase()}.${n.className && n.className.baseVal === undefined ? n.className : ''} ${Math.round(r.right)} > card ${Math.round(right)}: ${(n.textContent || '').trim().slice(0, 40)}`);
    }
  }
  return [...new Set(out)].slice(0, 10);
}"""

# The type scale of tokens.css, read on <body> (the body size follows the host's font size).
TYPE_SCALE = """() => {
""" + VISIBLE + """
  const body = getComputedStyle(document.body);
  const px = name => {
    const probe = document.createElement('span');
    probe.style.setProperty('font-size', `var(${name})`);
    document.body.appendChild(probe);
    const v = parseFloat(getComputedStyle(probe).fontSize);
    probe.remove();
    return v;
  };
  const scale = ['--t-cap', '--t-meta', '--t-body', '--t-title', '--t-h', '--t-num'].map(px);
  const off = [], mono = [];
  for (const n of document.querySelectorAll('#app *')) {
    const own = [...n.childNodes].some(c => c.nodeType === 3 && c.textContent.trim());
    if (!own || !visible(n)) continue;
    const cs = getComputedStyle(n);
    const size = parseFloat(cs.fontSize);
    const where = `${n.tagName.toLowerCase()}.${n.className && n.className.baseVal === undefined ? n.className : ''} ${cs.fontSize}: ${n.textContent.trim().slice(0, 30)}`;
    if (n instanceof SVGElement) {
      if (size < 10 || size > 13) off.push('svg ' + where);
    } else if (!scale.some(s => Math.abs(s - size) < 0.05)) {
      off.push(where);
    }
    if (/mono/i.test(cs.fontFamily) && n.textContent.trim().split(/\\s+/).length > 3) mono.push(where);
  }
  return {scale, off: [...new Set(off)].slice(0, 10), mono: [...new Set(mono)].slice(0, 10)};
}"""

# Text with an underline anywhere in the panel (numbers, prose words, links).
UNDERLINED_TEXT = """() => {
""" + VISIBLE + """
  const out = [];
  for (const n of document.querySelectorAll('#app *')) {
    const own = [...n.childNodes].some(c => c.nodeType === 3 && c.textContent.trim());
    if (!own || !visible(n)) continue;
    if (getComputedStyle(n).textDecorationLine.includes('underline')) out.push(`${n.tagName.toLowerCase()}: ${n.textContent.trim().slice(0, 40)}`);
  }
  return [...new Set(out)].slice(0, 10);
}"""

# Prose without the junior's quoted words (they are quoted as recorded, tokens included),
# and without the engine's own record under "Details" (layer 2, verbatim by design, §15.1).
PROSE_UNQUOTED = PROSE.replace(".ht-src, code, pre,", ".ht-src, code, pre, [data-quoted], blockquote, q, [data-engine-text],")

# The resolved colours of the theme's tokens, as sRGB triples.
TOKENS = """(names) => {
  const out = {};
  const probe = document.createElement('span');
  document.body.appendChild(probe);
  for (const [key, value] of Object.entries(names)) {
    probe.style.setProperty('color', value);
    out[key] = getComputedStyle(probe).color;
  }
  probe.remove();
  return out;
}"""

TEXT_TOKENS = ['--ht-fg', '--ht-muted', '--ht-faint', '--ht-link', '--ht-accent-ink', '--ht-warn', '--ht-bad',
               '--ht-experiment-fg', '--ht-error-fg']
CHIP_INKS = {'ok': '--ht-ok', 'info': '--ht-info', 'seal': '--ht-seal', 'bad': '--ht-bad', 'warn': '--ht-warn',
             'accent': '--ht-accent-ink'}


def _rgb(css: str) -> tuple:
    """An opaque sRGB triple (0..1) of a computed colour: ``rgb(...)`` or ``color(srgb ...)``."""
    m = re.fullmatch(r'rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)', css)
    if m:
        assert m.group(4) in (None, '1'), f'translucent text colour: {css}'
        return tuple(float(m.group(i)) / 255 for i in (1, 2, 3))
    m = re.fullmatch(r'color\(srgb ([\d.e-]+) ([\d.e-]+) ([\d.e-]+)(?: / ([\d.]+))?\)', css)
    assert m, css
    assert m.group(4) in (None, '1'), f'translucent text colour: {css}'
    return tuple(float(m.group(i)) for i in (1, 2, 3))


def contrast(a: tuple, b: tuple) -> float:
    def lum(c):
        lin = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    hi, lo = sorted([lum(a), lum(b)], reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def column_names(payload, task: str) -> list:
    """The study's column names: identifiers of the data that engine texts quote as they are."""
    data = payload(f'captured/data.{task}')
    return [v['name'] for g in data['groups'] for v in g['variables']]


def structural(panel, where, columns=()):
    page = panel.page
    # A view that threw renders a one-line alert instead of itself (core.js): the gate fails then.
    errors = page.locator('[data-view-error]').all_inner_texts()
    assert errors == [], (where, errors)
    o = page.evaluate(OVERFLOW)
    assert o['scroll'] <= o['vw'] + 1 and not o['out'], (where, o)
    assert page.evaluate(CARD_OVERFLOW) == [], where
    t = page.evaluate(TYPE_SCALE)
    assert t['off'] == [], (where, 'off the type scale', t['scale'], t['off'])
    assert t['mono'] == [], (where, 'monospace prose', t['mono'])
    prose = page.evaluate(PROSE_UNQUOTED)
    for name in sorted(columns, key=len, reverse=True):
        prose = re.sub(rf'(?<![\w.]){re.escape(name)}(?![\w])', ' ', prose)
    for pattern in (r'\b[0-9a-f]{12,64}\b', r'\bp_\d+\b', r'\b(capacity|threshold|share|top_k|top|rule):[0-9.]+',
                    r'\b[a-z]+_[a-z0-9]+(?:_[a-z0-9]+)*\b(?!\.(?:py|json|html|csv|md|db))'):
        hit = re.search(pattern, prose)
        assert not hit, (where, 'raw token in the prose', hit and prose[max(0, hit.start() - 40):hit.end() + 40])
    assert page.evaluate(UNDERLINED) == 0, where
    assert page.evaluate(UNDERLINED_TEXT) == [], where
    styles = page.evaluate(STYLE_ATTRS)
    assert all(re.fullmatch(r'(\s*--[a-z-]+:\s*[^;]+;?)+\s*', s) for s in styles), (where, [s for s in styles if '--' not in s][:3])
    assert page.evaluate('window.__styleAttrs') == [], where
    assert not (panel.requests or panel.errors or panel.csp or panel.violations()), \
        (where, panel.requests, panel.errors, panel.csp, panel.violations())


def shot(page, name):
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(SHOTS) / f'{name}.png'), full_page=True)


def settle(page):
    # The curves redraw at their container's width (a ResizeObserver): two frames settle them.
    page.evaluate('() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))')


@pytest.fixture(scope='module')
def views(model, payload):
    return load_views(model, payload)


def gate(panel, where, case, columns):
    """The structural gate on the page as first rendered, then with every fold and drawer open."""
    settle(panel.page)
    structural(panel, f'{where}/closed', columns)
    open_all(panel, panel.case_views, panel.case_reads)
    settle(panel.page)
    assert panel.page.locator('#app details:not([open])').evaluate_all(
        'ds => ds.filter(d => !d.closest("[data-popover]")).length') == 0, where
    structural(panel, f'{where}/open', columns)


# --- 1. structural assertions --------------------------------------------------------------

@pytest.mark.parametrize('lang', LANGS)
@pytest.mark.parametrize('width', WIDTHS)
@pytest.mark.parametrize('theme', THEMES)
def test_the_page_passes_the_structural_gate(open_panel, views, payload, theme, width, lang):
    """A11Y-3, A11Y-4, R26, NAR-1, NAR-2 (§13.5): the page at 320, 420, 600 and 900 px, three themes,
    both languages, on the captured Bank studies and the five P1 states (Auto MPG)."""
    for case in ['binary', 'cv', 'families', *STATES]:
        panel = open_case(open_panel, views, case=case, theme=theme, width=width, lang=lang)
        columns = column_names(payload, 'regression' if case in STATES else 'binary')
        gate(panel, f'{case}/{theme}/{width}/{lang}', case, columns)
        if width in (320, 420) and case in STATES:
            shot(panel.page, f'{case}-{theme}-{width}-{lang}')
        panel.context.close()


@pytest.mark.parametrize('width', WIDTHS)
def test_the_regression_page_passes_the_structural_gate_in_french(open_panel, views, payload, width):
    panel = open_case(open_panel, views, case='regression', theme='light-modern', width=width, lang='fr')
    gate(panel, f'regression/{width}', 'regression', column_names(payload, 'regression'))
    if width != 900:
        shot(panel.page, f'regression-light-modern-{width}-fr')


@pytest.mark.parametrize('theme', THEMES)
def test_text_tokens_keep_their_contrast(open_panel, views, theme):
    """A11Y-4: text tokens on the page and on a card, chip inks on their tints, button texts."""
    panel = open_case(open_panel, views, theme=theme)
    names = {t: f'var({t})' for t in TEXT_TOKENS}
    names.update({'bg': 'var(--ht-bg)', 'surface': 'var(--ht-surface)', 'button-bg': 'var(--ht-button-bg)',
                  'button-fg': 'var(--ht-button-fg)', 'button2-bg': 'var(--ht-button2-bg)', 'button2-fg': 'var(--ht-button2-fg)'})
    for chip, ink in CHIP_INKS.items():
        names[f'chip-{chip}'] = f'var({ink})'
        hue = '--ht-accent' if chip == 'accent' else ink
        names[f'tint-{chip}'] = f'color-mix(in srgb, var({hue}) 12%, var(--ht-bg))'
    colours = {k: _rgb(v) for k, v in panel.page.evaluate(TOKENS, names).items()}
    low = []
    for token in TEXT_TOKENS:
        need = 7.0 if theme == 'hc' and token in ('--ht-fg', '--ht-muted') else 4.5
        for ground in ('bg', 'surface'):
            ratio = contrast(colours[token], colours[ground])
            if ratio < need:
                low.append(f'{token} on {ground}: {ratio:.2f} < {need}')
    for chip in CHIP_INKS:
        ratio = contrast(colours[f'chip-{chip}'], colours[f'tint-{chip}'])
        if ratio < 4.5:
            low.append(f'chip {chip}: {ratio:.2f} < 4.5')
    for fg, bg in (('button-fg', 'button-bg'), ('button2-fg', 'button2-bg')):
        ratio = contrast(colours[fg], colours[bg])
        if ratio < 4.5:
            low.append(f'{fg} on {bg}: {ratio:.2f} < 4.5')
    assert low == [], (theme, low)


# --- 2. pixel baselines --------------------------------------------------------------------

COMPARE = """async ([a, b]) => {
  const load = src => new Promise((ok, ko) => { const i = new Image(); i.onload = () => ok(i); i.onerror = ko; i.src = src; });
  const [x, y] = await Promise.all([load(a), load(b)]);
  if (x.width !== y.width || x.height !== y.height) return {size: [x.width, x.height, y.width, y.height]};
  const w = x.width, h = x.height;
  const pixels = img => { const c = document.createElement('canvas'); c.width = w; c.height = h;
    const g = c.getContext('2d'); g.drawImage(img, 0, 0); return g.getImageData(0, 0, w, h).data; };
  const p = pixels(x), q = pixels(y);
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  const g = c.getContext('2d'); const out = g.createImageData(w, h);
  let differ = 0;
  for (let i = 0; i < p.length; i += 4) {
    const d = Math.max(Math.abs(p[i] - q[i]), Math.abs(p[i + 1] - q[i + 1]), Math.abs(p[i + 2] - q[i + 2]), Math.abs(p[i + 3] - q[i + 3]));
    if (d > %d) { differ++; out.data.set([255, 0, 0, 255], i); }
    else { const v = 255 - (255 - (p[i] + p[i + 1] + p[i + 2]) / 3) * 0.25; out.data.set([v, v, v, 255], i); }
  }
  g.putImageData(out, 0, 0);
  return {differ, total: w * h, diff: c.toDataURL('image/png').split(',')[1]};
}""" % CHANNEL_DELTA


def _update() -> bool:
    return os.environ.get('HYPOTRAIL_UPDATE_BASELINES') == '1'


def _fonts_ok() -> str | None:
    """Why the pinned fonts cannot be used here, or None."""
    if not sys.platform.startswith('linux'):
        return f'the pixel baselines were drawn on Linux, not {sys.platform}'
    if not shutil.which('fc-match'):
        return 'fc-match is not installed (fontconfig)'
    for family in (FONT, MONO):
        got = subprocess.run(['fc-match', '-f', '%{family}', family], capture_output=True, text=True).stdout
        if family not in got:
            return f'the font {family} is not installed (fc-match gives {got!r})'
    return None


@pytest.fixture(scope='module')
def comparer(browser):
    context = browser.new_context(offline=True)
    page = context.new_page()
    page.set_content('<!doctype html><title>compare</title>')
    yield page
    context.close()


def pin(page):
    """Deterministic rendering: the fonts, the clock (the tests run offline, so nothing else)."""
    # A fixed Date only: timers and animation frames keep running (the curves redraw on them).
    page.clock.set_fixed_time(CLOCK)
    page.evaluate("""([font, mono]) => {
      const root = document.documentElement;
      root.style.setProperty('--vscode-font-family', `"${font}", sans-serif`);
      root.style.setProperty('--vscode-editor-font-family', `"${mono}", monospace`);
    }""", [FONT, MONO])


def check_pixels(comparer, name: str, png: bytes, update: bool, changed: list) -> str | None:
    """Compare one capture with its baseline; the failure message, or None."""
    target = BASELINES / f'{name}.png'
    if update:
        BASELINES.mkdir(exist_ok=True)
    if not target.exists():
        if update:
            target.write_bytes(png)
            changed.append(f'{name} (new)')
            return None
        DIFFS.mkdir(parents=True, exist_ok=True)
        (DIFFS / f'{name}.actual.png').write_bytes(png)
        return f'{name}: no baseline (run with --update-baselines, then have the owner review it)'
    url = 'data:image/png;base64,'
    r = comparer.evaluate(COMPARE, [url + base64.b64encode(png).decode(), url + base64.b64encode(target.read_bytes()).decode()])
    if 'size' in r or r['differ'] > MAX_SHARE * r['total']:
        DIFFS.mkdir(parents=True, exist_ok=True)
    if 'size' in r:
        problem = f'{name}: size {r["size"][0]}x{r["size"][1]} != baseline {r["size"][2]}x{r["size"][3]}'
    elif r['differ'] > MAX_SHARE * r['total']:
        problem = f'{name}: {r["differ"]} of {r["total"]} pixels differ ({100 * r["differ"] / r["total"]:.2f} % > {100 * MAX_SHARE} %)'
        (DIFFS / f'{name}.diff.png').write_bytes(base64.b64decode(r['diff']))
    else:
        return None
    (DIFFS / f'{name}.actual.png').write_bytes(png)
    (DIFFS / f'{name}.baseline.png').write_bytes(target.read_bytes())
    if update:
        target.write_bytes(png)
        changed.append(problem)
        return None
    return problem


def _one_page_set() -> bool:
    """Whether a set of one-page baselines exists here (committed after the owner's review, or local)."""
    return BASELINES.is_dir() and any(ONE_PAGE.match(f.name) for f in BASELINES.glob('*.png'))


@pytest.mark.parametrize('lang', LANGS)
@pytest.mark.parametrize('width', PIXEL_WIDTHS)
@pytest.mark.parametrize('theme', THEMES)
def test_every_state_matches_its_pixel_baseline(open_panel, views, comparer, request, theme, width, lang):
    why = _fonts_ok()
    if why:
        warnings.warn(f'the panel pixel baselines did not run: {why}.', pytest.PytestWarning, stacklevel=1)
        pytest.skip(why)
    update = request.config.getoption('--update-baselines', default=False) or _update()
    if not update and not _one_page_set():
        # P-7: the tabbed baselines were deleted; the one-page set waits for the owner.
        pytest.skip('one-page baselines awaiting owner review')
    options = {'locale': 'en-US', 'timezone_id': 'UTC', 'reduced_motion': 'reduce', 'device_scale_factor': 1}
    problems, changed = [], []
    for state in STATES:
        # open_case opens the panel through `open_panel`; the context options go with it.
        panel = open_case(lambda color_scheme: open_panel(color_scheme=color_scheme, **options), views, case=state,
                          theme=theme, width=width, lang=lang, height=PIXEL_HEIGHT, before=pin)
        page = panel.page
        page.evaluate('document.fonts.ready')
        settle(page)
        page.evaluate('window.scrollTo(0, 0)')
        png = page.screenshot(animations='disabled', caret='hide', scale='css')
        problem = check_pixels(comparer, f'{state}-{theme}-{width}-{lang}', png, update, changed)
        if problem:
            problems.append(problem)
        chart = next((page.locator(sel).first for sel in MAIN_CHART.get(state, []) if page.locator(sel).count()), None)
        if chart is not None:
            chart.scroll_into_view_if_needed()
            box = chart.bounding_box()
            png = page.screenshot(animations='disabled', caret='hide', scale='css', full_page=True,
                                  clip={'x': box['x'] + page.evaluate('scrollX'), 'y': box['y'] + page.evaluate('scrollY'),
                                        'width': box['width'], 'height': min(box['height'], CHART_MAX_HEIGHT)})
            problem = check_pixels(comparer, f'{state}-chart-{theme}-{width}-{lang}', png, update, changed)
            if problem:
                problems.append(problem)
        panel.context.close()
    if changed:
        warnings.warn('panel pixel baselines rewritten (owner review of the diff images in '
                      f'{DIFFS} before commit): ' + '; '.join(changed), pytest.PytestWarning, stacklevel=1)
    assert problems == [], f'diff images in {DIFFS}: ' + '; '.join(problems)
