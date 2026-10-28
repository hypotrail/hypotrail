"""The lesson-style report on real studies (owner decision 2026-10-27, R25 to R30, R26 defects).

Auto MPG in French and Bank Marketing in English, walked by the automatic mode to the review
(``init --automation until_final_test``, through the CLI's own code path ``cli.run``), then
rendered. Unit checks of the
page and simulated browser checks (Playwright, headless Chromium, network blocked); none of
them is a Copilot or Claude Code acceptance session.

* ``check`` is clean on both editions, and the page is deterministic and within its budget.
* R26: no classification wording in a regression report; no English in a French edition and
  no French in an English one (recorded words aside, marked with their language); an
  automatic decision never reads "Confirmed decision"; a variant is named by its family; the
  model choice states the tension between the one-standard-error rule and a paired difference
  that excludes zero; a regression final test drawn without order says it cannot show drift.
* R30: every figure and table has its guided reading with a conclusion.
* R27, R28: both languages switch in the browser; the board is the default; no sideways
  scrolling at 390 and 1280 px.
"""
from __future__ import annotations

import re
import sys
import warnings
from html.parser import HTMLParser
from pathlib import Path

import pytest

import flowkit as fk
from lesson_page import chapter_html, editions
from mlkit.study import cmd_check, manifest as mf, render_html, texts, view

REPO = Path(__file__).resolve().parents[4]
AUTO_MPG = REPO / 'use-cases' / 'auto-mpg'
sys.path.insert(0, str(REPO / 'framework' / 'tests' / 'acceptance' / 'agent'))
import graders_v03 as g  # noqa: E402

BUDGET_BYTES = 1_100_000         # two editions of a real study (about 0.8 MB on Auto MPG)


def _automatic(base: Path, case: Path, lang: str, mode: str = 'until_final_test') -> Path:
    f = fk.Flow(base, case, prefix=f'{base.name}-')
    f.call('init', '--case', case, '--study', base, '--lang', lang,
           '--automation', mode)
    f.call('automation', 'run', '--request-id', 'auto', '--expected-revision', f.rev(),
           '--study', f.study)
    f.call('render', '--study', f.study)
    return f.study


@pytest.fixture(scope='module')
def studies(tmp_path_factory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp('lesson')
    return {'auto-fr': _automatic(root / 'auto-fr', AUTO_MPG, 'fr'),
            'bank-en': _automatic(root / 'bank-en', fk.BANK, 'en'),
            # R48, R52, R53: the final test opened and the study concluded (a demonstration).
            'auto-demo': _automatic(root / 'auto-demo', AUTO_MPG, 'fr', 'full_demo')}


def _page(study: Path) -> str:
    return (study / mf.ARTIFACTS['report']).read_text(encoding='utf-8')


class _Text(HTMLParser):
    """The visible engine text of an edition: recorded words, quotations, identifiers,
    code and the elements written in the other language left out."""

    QUOTED = ('case', 'identifier', 'user_words', 'category', 'decision_value', 'data_row',
              'parameter', 'environment', 'code', 'message', 'proposal')

    def __init__(self, lang: str):
        super().__init__(convert_charrefs=True)
        self.lang, self.stack, self.out, self.skip = lang, [], [], 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('script', 'style', 'title'):
            self.skip += 1
        if tag in ('br', 'meta', 'circle', 'rect', 'line', 'polyline', 'img', 'input', 'wbr'):
            return
        exempt = tag in ('q', 'code', 'data', 'pre') or a.get('data-literal') in self.QUOTED \
            or a.get('lang') not in (None, self.lang) or 'recl' in (a.get('class') or '')
        self.stack.append((tag, exempt))

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'title'):
            self.skip -= 1
        if tag not in {t for t, _ in self.stack}:
            return
        while self.stack:
            t, _ = self.stack.pop()
            if t == tag:
                break

    def handle_data(self, data):
        if self.skip or any(x for _, x in self.stack):
            return
        text = ' '.join(data.split())
        if text:
            self.out.append(text)


def _texts(fragment: str, lang: str) -> list[str]:
    p = _Text(lang)
    p.feed(fragment)
    return p.out


# --- traceability, determinism, size ------------------------------------------------------------

@pytest.mark.parametrize('name', ['auto-fr', 'bank-en', 'auto-demo'])
def test_check_is_clean_on_both_editions_and_the_page_is_deterministic(studies, name):
    study = studies[name]
    report = cmd_check.run_check(study)
    assert report['clean'], report['findings']
    assert not [f for f in report['findings'] if f['code'] in ('causal_wording',
                                                               'forecast_wording')]
    page = _page(study)
    assert len(page.encode('utf-8')) <= BUDGET_BYTES
    assert set(editions(page)) == {'en', 'fr'}
    fk.Flow(study, AUTO_MPG).call('render', '--study', study)
    assert _page(study) == page
    assert f'content="{render_html.TEMPLATE_VERSION}"' in page and render_html.TEMPLATE_VERSION == 4


@pytest.mark.parametrize('name', ['auto-fr', 'bank-en', 'auto-demo'])
def test_every_figure_and_table_is_read_and_concluded(studies, name):
    page = _page(studies[name])
    for lang, fragment in editions(page).items():
        frames = re.split(r'(?=<div class="frame" id=)', fragment)[1:]
        assert len(frames) >= 20, (lang, len(frames))
        for frame in frames:
            kind = re.search(r'data-figure="([a-z_]+)"', frame).group(1)
            head = frame[:frame.index('<div class="fbody">')]
            assert '<div class="pq">' in head and '<p class="fm">' in head, (lang, kind)
            assert '<details class="f lire" open>' in frame, (lang, kind)
            assert '<div class="concl">' in frame, (lang, kind)
        # figure V (the development errors; once the final test is opened, the development
        # and final errors on one scale, R52), the paired differences, and every chapter
        # keeps a sentence
        figure_v = 'evidence_dots' if name == 'auto-demo' else 'errors_bar'
        assert f'data-figure="{figure_v}"' in fragment and 'data-figure="paired"' in fragment
        assert fragment.count('<p class="garde">') == 9
        assert fragment.count('<section class="notion chapter" id="ch') == 9


# --- R26 -----------------------------------------------------------------------------------------

def test_a_regression_report_holds_no_classification_wording(studies):
    page = _page(studies['auto-fr'])
    words = re.compile(r'\b(taux|lignes? positives?|positive rows?|classe moins bien|'
                       r'classe mieux|ranks? the rows|rank the rows|score moyen|mean score|'
                       r'observed rate|taux observé|base rate|taux de base|précision|precision|'
                       r'rappel|recall)\b', re.I)
    for lang, fragment in editions(page).items():
        found = [t for t in _texts(fragment, lang) if words.search(t)]
        assert found == [], (lang, found[:5])


@pytest.mark.parametrize('name', ['auto-fr', 'bank-en'])
def test_each_edition_is_written_in_its_own_language(studies, name):
    page = _page(studies[name])
    english = re.compile(r'\b(Rows read|Unit:|Intervals:|Scale:|the second variant|'
                         r'the third variant|Linear model|Mean baseline|Development rows|'
                         r'percentile intervals|Which variables)\b')
    for lang, fragment in editions(page).items():
        texts_ = _texts(fragment, lang)
        foreign = [s for t in texts_ for s in g.foreign_sentences(t, lang, min_words=3)]
        assert foreign == [], (lang, foreign[:5])
        if lang == 'fr':
            assert [t for t in texts_ if english.search(t)] == []


@pytest.mark.parametrize('name', ['auto-fr', 'bank-en'])
def test_an_automatic_decision_is_never_shown_as_confirmed(studies, name):
    page = _page(studies[name])
    for lang, fragment in editions(page).items():
        with texts.report_language_context(lang):
            labels = texts.report()
        cards = re.findall(r'<article class="decision" data-decision="([a-z_]+)" '
                           r'data-status="confirmed">(.*?)</article>', fragment, re.S)
        assert cards
        for did, card in cards:
            assert 'data-basis="automatic"' in card, did
            assert labels['decision_status']['confirmed'] not in card, (lang, did)
            assert labels['automatic'] in card, (lang, did)
        # the decisions to review, with the stamp and the chapter of each
        assert len(cards) >= 7
        review = fragment.split('<table class="dec-list">')[1].split('</table>')[0]
        assert review.count('<tr data-decision=') == len(cards)
        assert review.count('class="stamp auto"') == len(cards)


def _paired_attention(chapter: str) -> str:
    frame = chapter.split('data-figure="paired"')[1].split('<div class="frame"')[0]
    return frame.split('<div class="attn">')[1]


def test_a_variant_is_named_by_its_family_and_the_tension_is_stated(studies):
    study = studies['auto-fr']
    page = _page(study)
    fr, en = editions(page)['fr'], editions(page)['en']
    assert 'Variante du modèle linéaire, la deuxième' not in fr
    assert 'the second variant' not in en
    assert 'Variante EBM (modèle non linéaire lisible)' in fr
    assert 'EBM variant (readable non-linear model)' in en
    # Auto MPG: the one-standard-error rule keeps the linear model while the paired
    # difference of the tuned variant excludes zero; the choice says so, with the numbers.
    sel = view.build(study)['results']['evaluate.regression']['values']['model_selection']
    assert sel['one_se']['pick'] != sel['one_se']['best']
    for fragment, cid in ((fr, 'ch7'), (en, 'ch7--en')):
        attention = _paired_attention(chapter_html(fragment, cid))
        assert 'data-tension="one_se"' in attention
        assert attention.count('<data value=') >= 3          # the gap and its interval
    assert page.count('data-tension=') == 2


def test_a_regression_final_test_without_order_says_it_cannot_show_drift(studies):
    page = _page(studies['auto-fr'])
    state = view.build(studies['auto-fr'])['final_test']
    assert state['method'] == 'quantile_stratified'
    for lang, fragment in editions(page).items():
        ch8 = chapter_html(fragment, 'ch8' if lang == 'fr' else 'ch8--en')
        assert 'data-drift="unordered"' in ch8


def test_the_restated_words_of_the_other_language_are_marked(studies):
    page = _page(studies['auto-fr'])
    en = editions(page)['en']
    # the automatic mode's restatements were recorded in French
    assert re.search(r'data-literal="proposal" lang="fr">[^<]+</span> <span class="recl" '
                     r'lang="fr">\(fr\)</span>', en)
    assert 'class="recl" lang=' not in editions(page)['fr']


# --- browser (simulated, offline) ----------------------------------------------------------------

try:
    import playwright.sync_api as _sync_api
except ImportError:                                   # pragma: no cover - the full gate has it
    _sync_api = None


@pytest.fixture(scope='module')
def browser():
    if _sync_api is None:
        warnings.warn('Playwright is not installed: the lesson report browser checks did not '
                      'run (uv sync --group browser).', pytest.PytestWarning, stacklevel=1)
        pytest.skip('Playwright is not installed')
    from test_html_offline import _chromium
    with _sync_api.sync_playwright() as p:
        b = _chromium(p)
        yield b
        b.close()


@pytest.mark.parametrize('width', [390, 1280])
def test_the_real_report_fits_on_the_board_in_both_languages(browser, studies, width):
    report = studies['auto-fr'] / mf.ARTIFACTS['report']
    context = browser.new_context(offline=True, viewport={'width': width, 'height': 900},
                                  color_scheme='light', reduced_motion='reduce')
    requests, errors = [], []
    context.route('**/*', lambda route: route.continue_() if route.request.url.startswith('file:')
                  else (requests.append(route.request.url), route.abort()))
    try:
        page = context.new_page()
        page.on('pageerror', lambda exc: errors.append(str(exc)))
        page.goto(report.resolve().as_uri())
        page.wait_for_load_state('load')
        colour = page.evaluate('getComputedStyle(document.body).backgroundColor')
        assert sum(int(x) for x in re.findall(r'\d+', colour)[:3]) < 200   # the board
        assert page.evaluate('document.documentElement.lang') == 'fr'
        for step in ('fr', 'en'):
            assert page.evaluate('document.documentElement.scrollWidth') <= width, step
            page.click('#langBtn')
        assert page.evaluate('document.documentElement.lang') == 'fr'
        page.click('#themeBtn')
        assert page.evaluate('document.documentElement.scrollWidth') <= width
        assert requests == [] and errors == []
    finally:
        context.close()


# --- R52, R48, R53 (owner remarks 2026-10-28) ---------------------------------------------------

def _verdict(fragment: str) -> str:
    return re.search(r'<section class="blk" id="verdict[^"]*">(.*?)</section>', fragment,
                     re.S).group(1)


def test_development_and_final_evidence_are_one_table(studies):
    """R52: one table, a row per configuration (the reference last as "reference (predict the
    mean)"), then the paired difference and the criterion; the chosen row highlighted; a
    configuration the final test did not measure says so; dots on one scale under it."""
    demo, sealed = _page(studies['auto-demo']), _page(studies['auto-fr'])
    final = view.build(studies['auto-demo'])['results']['final_test.evaluation']['values']
    assert final['model'] == 'fit.linear'
    for lang, fragment in editions(demo).items():
        verdict = _verdict(fragment)
        assert 'class="vbox' not in verdict
        table = verdict.split('<table class="evtab"')[1].split('</table>')[0]
        configs = re.findall(r'<tr(?: class="chosen")? data-config="([^"]+)"', table)
        assert configs == ['fit.linear', 'fit.variant', 'fit.variant:2', 'fit.baseline']
        assert '<tr class="chosen" data-config="fit.linear">' in table
        reference = ('Référence (prédire la moyenne)' if lang == 'fr'
                     else 'Reference (predict the mean)')
        assert reference in table
        for slot in ('fit.variant', 'fit.variant:2'):
            row = table.split(f'data-config="{slot}"')[1].split('</tr>')[0]
            assert 'data-unmeasured="unmeasured"' in row
            assert ('le test final ne mesure que le modèle choisi' if lang == 'fr'
                    else 'the final test measures only the chosen model') in row
        for slot in ('fit.linear', 'fit.baseline'):
            row = table.split(f'data-config="{slot}"')[1].split('</tr>')[0]
            assert row.count('data-path="models.[') == 2           # development and final
            assert row.count('data-path="intervals.[') == 4
        assert 'data-row="paired"' in table and 'data-row="criterion"' in table
        criterion = table.split('data-row="criterion"')[1]
        assert 'data-path="criterion.gain"' in criterion
        assert ('erreur sur le test final' if lang == 'fr' else 'error on the final test') \
            in criterion
        assert 'data-figure="evidence_dots"' in verdict
        dots = verdict.split('data-figure="evidence_dots"')[1]
        assert '<line class="thr"' in dots                      # the final-test bound
        # the same layout once more in chapter eight, with its reading
        ch8 = chapter_html(fragment, 'ch8' if lang == 'fr' else 'ch8--en')
        assert 'data-figure="evidence_table"' in ch8 and 'data-figure="versus"' not in ch8
    for lang, fragment in editions(sealed).items():
        table = _verdict(fragment).split('<table class="evtab"')[1].split('</table>')[0]
        assert table.count('data-unmeasured="sealed_cell"') >= 4
        assert 'data-path="criterion.gain"' not in table


def test_the_conclusion_is_split_and_carried_by_charts(studies):
    """R48: "what the study establishes", "what it does not", "and then"; the criterion
    judged on the final test and the development and final errors drawn; the charts the
    engine cannot draw are named, not left out."""
    page = _page(studies['auto-demo'])
    for lang, fragment in editions(page).items():
        ch9 = chapter_html(fragment, 'ch9' if lang == 'fr' else 'ch9--en')
        parts = re.findall(r'data-part="(established|not_established|next)"', ch9)
        assert parts == ['established', 'not_established', 'next']
        established = ch9.split('data-part="established"')[1].split(
            'data-part="not_established"')[0]
        assert 'data-figure="criterion_final"' in established
        assert 'data-figure="evidence_dots"' in established
        assert 'data-path="criterion.minimum"' in established
        assert 'data-no-chart="observed_predicted"' in ch9
        assert 'data-no-chart="error_by_period"' in ch9
        assert "moyenne d'entraînement" not in ch9 and 'training mean' not in ch9


def test_the_method_is_drawn(studies):
    """R53 and R41: the partition and how it was drawn, the cross-validation rotation, the
    quality check column by column, the preparation pipeline with each column's verdict, the
    one-standard-error rule and the exposure ledger as a timeline, each with its reading."""
    page = _page(studies['auto-demo'])
    for lang, fragment in editions(page).items():
        assert 'data-partition-method="quantile_stratified"' in fragment
        for kind in ('cv_rotation', 'column_view', 'pipeline', 'one_se', 'exposure_timeline'):
            assert fragment.count(f'data-figure="{kind}"') == 1, (lang, kind)
        rotation = fragment.split('data-figure="cv_rotation"')[1].split('<div class="frame"')[0]
        assert rotation.count('class="cv-val"') == 5
        pipe = fragment.split('data-figure="pipeline"')[1].split('<div class="frame"')[0]
        assert re.search(r'data-stage="pipe_log"><b>[^<]+</b><span><code '
                         r'data-literal="identifier">horsepower</code>', pipe)
        assert pipe.count('data-path="ranges.') >= 4              # every numeric verdict
        rule = fragment.split('data-figure="one_se"')[1].split('<div class="frame"')[0]
        assert 'data-path="model_selection.one_se.bound"' in rule
        assert 'class="pick-ring"' in rule
        ledger = fragment.split('data-figure="exposure_timeline"')[1].split(
            '<div class="frame"')[0]
        assert 'class="ev-final"' in ledger and 'class="ev-look"' in ledger
