"""WP-B5 views (scope S, simulated browser): the final test first in Evidence, the ledger in
words, development and final evidence apart, cross-validation and the variant, the
diagnostics, the gain curve and share rules of What if?, the next move for the opening of
the final test (a chat act), and the mode explainer.

The real document under the real CSP, offline, on the **captured** payloads of a real
cross-validated Bank study whose final test was opened once and then changed after
(``test/fixtures/captured/*.cv*``), on the captured Online Shoppers view (the scenario
share), and on the captured diagnostics of WP-B4 (``diag.binary`` and ``diag.final_test`` in the
opened study, ``diag.regression`` in Auto MPG; CLI-CONTRACT §13),
in the Light+, Dark+ and High Contrast variable sets (``themes.py``) at 900 and 420 px.
With ``HYPOTRAIL_SHOTS=<dir>`` the tests also write screenshots there, for a person to look
at; nothing is asserted on them. Requirement ids: EV-7 to EV-12, WI-6, WI-7, OV-10, OV-11,
DC-10, A11Y-3. This is not a VS Code session.
"""
from __future__ import annotations

import copy
import os
import re
from pathlib import Path

import pytest

from conftest import inline_styles_ok
from panel_cases import OPEN_ONE, goto, with_results

import themes

SHOTS = os.environ.get('HYPOTRAIL_SHOTS')
THEMES = ['light', 'dark', 'hc']
FORBIDDEN = re.compile(r'\b(threshold|capacity|precision|recall|positive class|policy|calling rule|decision rule|selected)\b', re.I)
CHART_SIZES = """() => {
  const body = parseFloat(getComputedStyle(document.body).fontSize);
  return [...document.querySelectorAll('svg.ht-chart')].filter(s => s.getBoundingClientRect().width > 0).map(svg => {
    const vb = (svg.getAttribute('viewBox') || '').split(/\\s+/).map(Number);
    const scale = vb.length === 4 && vb[2] ? svg.getBoundingClientRect().width / vb[2] : 1;
    const texts = [...svg.querySelectorAll('text')].map(t => parseFloat(getComputedStyle(t).fontSize) * scale);
    return {body, scale, max: Math.max(0, ...texts)};
  });
}"""


def shot(page, name):
    # Taken after the checks: a full-page screenshot may leave a style attribute behind.
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.evaluate("() => document.querySelectorAll('body [style]').forEach(n => n.setAttribute('data-had-style', ''))")
        page.screenshot(path=str(Path(SHOTS) / f'{name}.png'), full_page=True)
        # Readable parts of a tall page, 1100 px each.
        width, height = page.evaluate('[document.documentElement.scrollWidth, document.documentElement.scrollHeight]')
        for i, top in enumerate(range(0, height, 1100)):
            page.screenshot(path=str(Path(SHOTS) / f'{name}.part{i + 1}.png'), full_page=True,
                            clip={'x': 0, 'y': top, 'width': width, 'height': min(1100, height - top)})
        page.evaluate("""() => document.querySelectorAll('body [style]:not([data-had-style])')
          .forEach(n => n.removeAttribute('style'))""")
        page.evaluate("() => document.querySelectorAll('[data-had-style]').forEach(n => n.removeAttribute('data-had-style'))")


@pytest.fixture(scope='module')
def views(model, payload):
    out = {
        'summary.opened': model('summary', 'captured/summary.binary.cv'),
        'summary.opening': model('summary', 'captured/summary.binary.cv.opening'),
        'summary.sealed.split': model('summary', 'captured/summary.binary'),
        'summary.regression': model('summary', 'captured/summary.regression'),
        'evidence.opened': model('evidence', 'captured/evidence.binary.cv'),
        'evidence.sealed': model('evidence', 'captured/evidence.binary.cv.sealed'),
        'evidence.split': model('evidence', 'captured/evidence.binary'),
        'evidence.regression': model('evidence', 'captured/evidence.regression'),
        'evidence.diagnostics': model('evidence', 'captured/evidence.binary.cv'),
        'evidence.regression.diag': model('evidence', 'captured/evidence.regression.diag'),
        'whatif.opened': model('whatif', 'captured/evidence.binary.cv'),
        'whatif.sealed': model('whatif', 'captured/evidence.binary.cv.sealed'),
        'decisions.opened': model('decisions', 'captured/decisions.binary.cv'),
        'scenario': model('scenario', 'captured/status.shoppers'),
        'raw.summary.opened': payload('captured/summary.binary.cv'),
        'raw.summary.opening': payload('captured/summary.binary.cv.opening'),
        'raw.evidence.opened': payload('captured/evidence.binary.cv'),
        'raw.evidence.diagnostics': payload('captured/evidence.binary.cv'),
        'raw.evidence.sealed': payload('captured/evidence.binary.cv.sealed'),
    }
    return out


def open_tab(open_panel, summary, tab, theme='light', width=900, stage='v2', **init):
    panel = open_panel(color_scheme=themes.scheme(theme))
    panel.page.set_viewport_size({'width': width, 'height': 900})
    themes.apply(panel.page, theme)
    panel.init(stage=stage, task=summary['task'], panelContract=2, **init)
    panel.snapshot(summary)
    if tab != 'overview':
        goto(panel)
    return panel


def feed(panel, **models):
    """Deliver the views, every fold then open (the path's figures and their sources, the
    ledger, the drawers): the former Evidence and What if? tabs, laid out on the one page."""
    for _ in range(10):
        for view, data in models.items():
            panel.view_data(view, data)
        if panel.page.evaluate(OPEN_ONE) == 0:
            break
        panel.page.wait_for_timeout(30)


def clean(panel):
    assert not (panel.requests or panel.errors or panel.csp or panel.violations()), \
        (panel.requests, panel.errors, panel.csp, panel.violations())
    assert inline_styles_ok(panel.page)


def no_sideways(page):
    assert page.evaluate('document.scrollingElement.scrollWidth <= window.innerWidth + 1')


def charts_unscaled(page):
    for chart in page.evaluate(CHART_SIZES):
        assert chart['scale'] <= 1.0001, chart
        assert chart['max'] <= chart['body'] + 2, chart


# --- Evidence: the final test first (EV-7), the ledger in words (EV-8) ----------------------

def test_ev7_evidence_opens_on_the_opened_final_test_then_the_ledger(open_panel, views):
    """EV-7: opened once (revision, the junior's words, what was measured), changed after (in words), the trial count."""
    panel = open_tab(open_panel, views['summary.opened'], 'evidence')
    feed(panel, evidence=views['evidence.opened'])
    page = panel.page
    # EV-7 → PG-5 and the `final_test` step's detail: the card comes first in that detail.
    first = page.locator('li[data-step="final_test"] .pg-detail > *').first
    assert first.get_attribute('data-ev') == 'final-test'
    assert page.locator('[data-block="header"] [data-pill="seal"]').get_attribute('data-seal') == 'changed'
    card = page.locator('[data-final-test-card]')
    assert card.get_attribute('data-final-test-card') == 'changed'
    raw = views['raw.summary.opened']['final_test']
    assert card.locator('[data-opened-at]').get_attribute('data-opened-at') == str(raw['opening']['revision'])
    assert card.locator('[data-opening-words]').inner_text() == raw['opening']['user_words']
    measured = card.locator('[data-opening-measured]').inner_text()
    assert 'the logistic model' in measured and 'top 10%' in measured
    fe = next(r for r in views['raw.evidence.opened']['results'] if r['slot'] == 'final_test.evaluation' and r['promoted'])
    assert f", on {fe['values']['n']:,} final-test rows, refitted on {fe['values']['refit']['n_rows']:,} development rows" in measured
    changed = card.locator('[data-changed]').evaluate_all('ns => ns.map(n => n.dataset.changed)')
    assert changed == raw['changed_after']
    assert 'the decision rule' in card.locator('[data-changed-after]').inner_text()
    trials = card.locator('[data-trials]')
    assert trials.get_attribute('data-trials') == str(views['raw.summary.opened']['trials']['count'])
    assert 'Configurations evaluated: 2' in trials.inner_text() and 'luck' in trials.inner_text()
    assert card.locator('button, [data-write], textarea, input').count() == 0, 'no control: the opening is a chat act'
    clean(panel)
    shot(page, 'evidence-opened-changed-light-900')


def test_ev7_sealed_final_test_points_to_the_chat_and_lists_what_must_be_confirmed(open_panel, views):
    panel = open_tab(open_panel, views['summary.opening'], 'evidence')
    feed(panel, evidence=views['evidence.sealed'])
    page = panel.page
    # NOW-7: at the opening, the card is in Now.
    card = page.locator('[data-block="now"] [data-final-test-card="sealed"]')
    raw = views['raw.summary.opening']['final_test']
    assert f"{raw['rows']:,} rows nobody has read" in card.inner_text()
    assert card.locator('[data-partition-line="development"]').inner_text().startswith(f"{raw['development_rows']:,}")
    assert 'the same share of each outcome' in card.inner_text()
    assert card.locator('[data-open-in-chat]').inner_text().startswith('Opening it is a chat act')
    done = card.locator('[data-before]').evaluate_all('ns => ns.map(n => [n.dataset.before, n.dataset.done])')
    assert done == [['policy', 'true'], ['model_variant', 'true'], ['success_criterion', 'true']]
    assert card.locator('button, [data-write]').count() == 0
    assert page.locator('[data-ev="final"]').count() == 0, 'no final evidence before the opening'
    clean(panel)
    shot(page, 'evidence-sealed-light-900')


def test_ev7_absent_final_test_says_no_figure_is_independent(open_panel, views):
    summary = copy.deepcopy(views['summary.sealed.split'])
    summary['finalTest'] = {'status': 'absent', 'rows': None, 'method': None, 'fraction': None, 'developmentRows': None,
                            'schemaCheck': None, 'opening': None, 'postFinalTest': False, 'changedAfter': []}
    panel = open_tab(open_panel, summary, 'evidence')
    feed(panel, evidence=views['evidence.split'])
    # EV-7 → PG-5: the seal pill says it, and its hover why no figure is independent.
    pill = panel.page.locator('[data-block="header"] [data-pill="seal"]')
    assert pill.get_attribute('data-seal') == 'absent' and pill.text_content() == 'No final test'
    assert 'every figure comes from rows the study has used' in pill.get_attribute('title')
    clean(panel)


def test_ev8_the_ledger_explains_each_purpose_and_marks_the_final_test_rows(open_panel, views):
    panel = open_tab(open_panel, views['summary.opened'], 'evidence')
    feed(panel, evidence=views['evidence.opened'])
    page = panel.page
    raw = views['raw.evidence.opened']['exposure']['ledger']
    rows = page.locator('[data-ledger-row]')
    assert rows.evaluate_all('rs => rs.map(r => r.dataset.ledgerRow)') == [f"{r['purpose']}:{r['partition']}" for r in raw]
    assert rows.evaluate_all('rs => rs.map(r => r.querySelector("[data-rows]").dataset.rows)') == [str(r['rows']) for r in raw]
    sealed = page.locator('[data-ledger-row="sealed:final_test"]')
    assert sealed.get_attribute('data-ledger-final') == 'true'
    assert 'Nobody has read them' in sealed.inner_text() and 'final test' in sealed.inner_text()
    assert 'development rows' in page.locator('[data-ledger-row="cross_validated_fit:development"]').inner_text()
    assert page.locator('[data-ledger-row="out_of_fold_policy_selection:development"]').get_attribute('class') == 'ht-ledger-selection'
    clean(panel)


# --- development and final evidence apart (EV-9, EV-10, EV-11) -------------------------------

def test_ev9_ev10_ev11_development_and_final_evidence_are_apart_and_cited(open_panel, views):
    """EV-9 two labelled sections; EV-10 the scheme in words, mean ± sd, lowest – highest; EV-11 the variant."""
    panel = open_tab(open_panel, views['summary.opened'], 'evidence')
    feed(panel, evidence=views['evidence.opened'])
    page = panel.page
    dev = page.locator('[data-anchor="path:model_variant/fit.variant"] [data-ev="development"]')
    final = page.locator('[data-ev="final"]')
    assert dev.locator('h3').inner_text() == 'Development evidence · used to choose'
    assert final.locator('h3').inner_text() == 'Final evidence · measured once'
    assert dev.locator('[data-cv-scheme="kfold_stratified"]').inner_text() == \
        'Cross-validation in 5 folds, each with the same share of each outcome.'
    raw = {r['slot']: r for r in views['raw.evidence.opened']['results'] if r['promoted'] and r['current']}
    spread = raw['fit.logistic']['values']['cross_validation']['spread']['roc_auc']
    cell = dev.locator(f'[data-cv-spread] data[data-result-id="{raw["fit.logistic"]["result_id"]}"]'
                       '[data-path="cross_validation.spread.roc_auc.mean"]')
    assert cell.get_attribute('data-value') == str(spread['mean'])
    assert ' ± ' in cell.inner_text()
    assert dev.locator('[data-path="cross_validation.spread.roc_auc.min"]').first.inner_text().count('–') == 1
    variant = dev.locator('[data-variant="regularisation"]')
    assert 'more regularisation' in variant.inner_text()
    assert variant.locator('.ht-intervals [data-interval][data-tone="baseline"]').count() >= 1
    assert variant.locator('[data-zero]').count() >= 1
    sentences = variant.locator('[data-variant-sentence]').evaluate_all('ns => ns.map(n => n.dataset.variantSentence)')
    assert sentences and set(sentences) <= {'one_side', 'includes_zero'}
    cited = variant.locator('[data-variant-sentence] data').first
    assert cited.get_attribute('data-result-id') == raw['policy.evaluation']['result_id']
    fe = raw['final_test.evaluation']
    crit = final.locator('[data-final-criterion]')
    assert crit.get_attribute('data-final-criterion') == fe['values']['criterion']['status']
    assert crit.locator('data[data-path="criterion.gain"]').get_attribute('data-result-id') == fe['result_id']
    assert final.locator('[data-final-metric="precision"] .ht-intervals').count() == 2
    # The final-test results are listed apart: the `final_test` step holds them (PATH-5).
    items = page.locator('li[data-step="final_test"] [data-result-slot]').evaluate_all('ns => ns.map(n => n.dataset.resultSlot)')
    on_final = [r['slot'] for r in views['raw.evidence.opened']['results']
                if r['promoted'] and r['current'] and r['partition'] == 'final_test']
    assert fe['slot'] in items and sorted(items) == sorted(on_final)
    clean(panel)
    shot(page, 'evidence-development-final-light-900')


# --- diagnostics (EV-12) ------------------------------------------------------------------------

def test_ev12_diagnostics_render_when_present_each_number_cited(open_panel, views):
    """EV-12 on the captured diagnostics: development (out of fold, computed after the opening) and final apart."""
    panel = open_tab(open_panel, views['summary.opened'], 'evidence')
    feed(panel, evidence=views['evidence.diagnostics'])
    page = panel.page
    # One figure per diagnostics result, under its step: development (models), final (final test).
    section = page.locator('#main')
    assert page.locator('[data-ev="diagnostics"]').evaluate_all('ns => ns.map(n => n.dataset.diagSlot)') == \
        ['diag.binary', 'diag.final_test']
    assert section.locator('[data-diag-evaluation]').evaluate_all('ns => ns.map(n => n.dataset.diagEvaluation)') == \
        ['development', 'final']
    raw = {r['slot']: r for r in views['raw.evidence.diagnostics']['results'] if r['promoted'] and r['current']}
    dev = section.locator('[data-diag="diag.binary"]')
    assert dev.get_attribute('data-result-ref') == raw['diag.binary']['result_id']
    assert dev.locator('[data-after-opening]').count() == 1, 'computed after the opening, on development rows'
    assert dev.locator('[data-diag-rule]').get_attribute('data-diag-rule') == raw['diag.binary']['values']['rule']
    assert '(your adopted rule)' in dev.locator('[data-diag-rule]').inner_text()
    chosen = dev.locator('[data-diag-model]').first.get_attribute('data-diag-model')
    policy = views['summary.opened']['decisions']['policy']['value']
    assert chosen == (policy.split('@')[1] if '@' in policy else 'fit.logistic')
    confusion = raw['diag.binary']['values']['models'][chosen]['confusion']
    tn = dev.locator(f'[data-diag-model="{chosen}"] [data-cell="tn"] data').first
    assert tn.get_attribute('data-path') == f'models.[{chosen}].confusion.true_negatives'
    assert float(tn.get_attribute('data-value')) == confusion['true_negatives']
    assert tn.get_attribute('data-result-id') == raw['diag.binary']['result_id']
    assert dev.locator('[data-diag-also]').count() == 1, 'the variant under "Also"'
    first = dev.locator(f'[data-diag-model="{chosen}"]').first
    assert first.locator('[data-diag-chart="gain"] [data-point]').count() == \
        len(raw['diag.binary']['values']['models'][chosen]['curve']['points'])
    assert first.locator('[data-diag-chart="calibration"] line[data-interval]').count() == \
        len(raw['diag.binary']['values']['models'][chosen]['calibration']['bins'])
    brier = first.locator('[data-brier] data').first
    assert brier.get_attribute('data-path') == f'models.[{chosen}].calibration.brier'
    assert first.locator('[data-segments]').count() == len(raw['diag.binary']['values']['models'][chosen]['segments'])
    assert first.locator('[data-coefficients]').count() == 1
    final = section.locator('[data-diag="diag.final_test"]')
    assert final.get_attribute('data-diag-evidence') == 'final'
    assert final.locator('[data-diag-rows="final_test"]').inner_text().startswith(
        f"On {raw['diag.final_test']['values']['n']:,} final-test rows")
    assert page.locator('[data-ev="diagnostics"] :is(button:not(.ht-link):not(.ht-term), [data-write])').count() == 0, \
        'the panel never runs a diagnostic'
    charts_unscaled(page)
    clean(panel)
    shot(page, 'evidence-diagnostics-light-900')
    # Sealed: development diagnostics, and the final test has none yet (a chat act).
    panel.snapshot(views['summary.opening'])
    feed(panel, evidence=views['evidence.sealed'])
    assert page.locator('[data-diag-final="sealed"]').count() == 1
    assert page.locator('[data-diag="diag.binary"] [data-after-opening]').count() == 0
    # Without diag.* results the section is absent. v0.3 (WP-F1, R28): the Bank capture now
    # runs its development diagnostics, so they are taken out of its model here.
    without = copy.deepcopy(views['evidence.split'])
    assert without['diagnostics']
    without['diagnostics'] = []
    panel.view_data('evidence', without)
    assert page.locator('[data-ev="diagnostics"]').count() == 0


@pytest.mark.parametrize('choice, policy, first', [
    (('confirmed', 'fit.variant'), 'share:0.2', 'fit.variant'),
    (('confirmed', 'fit.logistic'), 'share:0.2', 'fit.logistic'),
    (('proposed', 'fit.variant'), 'share:0.2', 'fit.logistic'),
    (('proposed', 'fit.variant'), 'share:0.2@fit.variant', 'fit.variant'),
])
def test_binary_diagnostics_show_the_chosen_model_first(open_panel, views, choice, policy, first):
    """R9UX-10: in a binary study the confirmed model choice says which model's diagnostics
    come first; without one, the policy's ``@model`` suffix does, else the candidate."""
    summary = copy.deepcopy(views['summary.opened'])
    summary['decisions']['model_choice'].update(status=choice[0], value=choice[1])
    summary['decisions']['policy']['value'] = policy
    panel = open_tab(open_panel, summary, 'evidence')
    feed(panel, evidence=views['evidence.diagnostics'])
    dev = panel.page.locator('[data-diag="diag.binary"]')
    order = dev.locator('[data-diag-model]').evaluate_all('ns => ns.map(n => n.dataset.diagModel)')
    assert order[0] == first and sorted(order) == ['fit.logistic', 'fit.variant'], order
    assert dev.locator('[data-diag-also] [data-diag-model]').get_attribute('data-diag-model') != first


@pytest.mark.parametrize('theme', THEMES)
def test_ev12_regression_diagnostics_residuals_without_rule_words(open_panel, views, theme):
    summary = with_results(views['summary.regression'], views['evidence.regression.diag']['results'])
    panel = open_tab(open_panel, summary, 'evidence', theme=theme)
    feed(panel, evidence=views['evidence.regression.diag'])
    page = panel.page
    dev = page.locator('[data-diag="diag.regression"]')
    assert dev.count() == 1
    assert dev.locator('[data-diag-rows="validation"]').count() == 1
    assert dev.locator('[data-errors] data').first.get_attribute('data-path').endswith('.errors.mae')
    assert dev.locator('[data-diag-chart="residuals"] [data-zero]').count() >= 1
    assert dev.locator('[data-diag-chart="qq"] [data-diagonal]').count() >= 1
    assert dev.locator('[data-by-feature]').count() >= 1
    assert dev.locator('[data-no-transform]').count() >= 1
    text = page.locator('#main').inner_text()
    assert not FORBIDDEN.search(text), FORBIDDEN.search(text)
    charts_unscaled(page)
    clean(panel)
    shot(page, f'evidence-regression-diagnostics-{theme}-900')


def test_ev12_regression_evidence_holds_no_rule_words(open_panel, views):
    panel = open_tab(open_panel, views['summary.regression'], 'evidence')
    feed(panel, evidence=views['evidence.regression'])
    page = panel.page
    text = page.locator('#main').inner_text()
    assert not FORBIDDEN.search(text), FORBIDDEN.search(text)
    assert page.locator('[data-block="header"] [data-pill="seal"]').count() == 1
    clean(panel)


# --- What if?: the gain curve and share rules (WI-6, WI-7) ----------------------------------------

def test_wi6_the_gain_curve_shows_registered_points_and_the_scenario_share(open_panel, views):
    panel = open_tab(open_panel, views['summary.opened'], 'whatif')
    page = panel.page
    loads = [m['view'] for m in panel.posted() if m['type'] == 'load']
    assert 'scenario' in loads and 'whatif' in loads
    feed(panel, scenario=views['scenario'], whatif=views['whatif.opened'])
    gain = page.locator('[data-gain]')
    raw = next(r for r in views['raw.evidence.opened']['results'] if r['slot'] == 'policy.evaluation' and r['promoted'])
    points = raw['values']['gain_points']['points']
    assert gain.get_attribute('data-experiment') == ''
    assert gain.locator('[data-gain-chart] [data-point]').count() == int(gain.get_attribute('data-gain'))
    assert gain.locator('[data-diagonal]').count() == 1
    first = gain.locator(f'[data-gain-table] data[data-path="gain_points.points.0.recall"]')
    assert first.get_attribute('data-value') == str(points[0]['recall'])
    assert first.get_attribute('data-result-id') == raw['result_id']
    scenario = gain.locator('[data-scenario-share]')
    assert scenario.get_attribute('data-scenario-share') == str(views['scenario']['capacityShare']['value'])
    assert 'exercise assumption' in scenario.inner_text() and 'not a figure from a team' in scenario.inner_text()
    assert gain.locator('[data-mark]').evaluate_all('ns => ns.map(n => n.dataset.mark)') == ['your rule', 'exercise assumption']
    assert gain.locator('[data-write]').count() == 0, 'the curve proposes nothing'
    charts_unscaled(page)
    clean(panel)
    shot(page, 'whatif-gain-light-900')


def test_wi7_try_a_share_previews_it_and_proposing_stays_w3_for_evaluated_rules(open_panel, views):
    panel = open_tab(open_panel, views['summary.opened'], 'whatif')
    page = panel.page
    feed(panel, whatif=views['whatif.opened'])
    page.locator('[data-rule-kind="share"]').click()
    assert page.locator('[data-slider="share"]').count() == 1
    assert page.locator('[data-rule-label]').inner_text().startswith('Act on the top')
    page.locator('[data-try-rule="share:0.05"]').click()
    previews = [m for m in panel.posted() if m['type'] == 'preview_policy']
    assert previews[-1]['rules'] == ['share:0.05']
    assert not [m for m in panel.posted() if m['type'] in ('propose', 'confirm')]
    assert page.locator('[data-not-evaluated="share:0.05"]').count() == 1, 'a gain point is not an evaluated rule'
    page.locator('[data-try-rule="share:0.2"]').click()
    posted = [m for m in panel.posted() if m['type'] == 'draft']
    assert posted and posted[-1]['value'] == 'share:0.2', 'an evaluated share rule asks the engine draft (W3 path)'
    clean(panel)


# --- the next move for the opening, the final test row, the mode (OV-10, OV-11, DC-10) -------------

@pytest.mark.parametrize('stage', ['v0', 'v2'])
def test_ov10_the_opening_of_the_final_test_is_a_chat_act(open_panel, views, stage):
    """OV-10, DC-10 → NOW-7: Now names the opening, says it opens once, in the chat, and offers
    no control but "Copy the question"."""
    panel = open_tab(open_panel, views['summary.opening'], 'overview', stage=stage)
    page = panel.page
    now = page.locator('[data-block="now"]')
    assert now.get_attribute('data-now-step') == 'final_test'
    # No control opens it; the one button copies a ready question for the chat, which writes nothing.
    assert now.locator('[data-write]').count() == 0
    assert now.locator('button:not([data-copy-question]):not(.ht-term)').count() == 0
    assert now.locator('[data-copy-question]').count() == 1
    card = now.locator('[data-proposal-card]')
    assert card.count() == 1
    assert card.locator('textarea, [data-action="confirm"]').count() == 0, 'DC-10: no field, no confirm'
    assert card.locator('[data-answer-in-chat]').inner_text() == \
        'The final test opens once, in the chat, when you decide it. Nothing in this panel opens it.'
    assert 'Open the final test once for the logistic model' in card.locator('.ht-plainsay').inner_text()
    clean(panel)
    shot(page, f'decisions-opening-{stage}-light-900')


def test_ov11_pg5_now7_the_final_test_and_the_mode(open_panel, views):
    """OV-11 → PG-5 (the seal pill: opened, then changed after) and NOW-7 (the answer rules of
    the mode, a fold of Now): the final test's opening words and criterion are in its step's
    card (EV-7, above); here the pill and the mode."""
    panel = open_tab(open_panel, views['summary.opened'], 'overview', stage='v1')
    pill = panel.page.locator('[data-block="header"] [data-pill="seal"]')
    assert pill.get_attribute('data-seal') == 'changed'
    assert 'the decision rule' in pill.get_attribute('title')
    clean(panel)
    panel = open_tab(open_panel, views['summary.opening'], 'overview', stage='v1')
    page = panel.page
    goto(panel)
    mode = page.locator('[data-block="now"] [data-mode="guided"]')
    assert 'This study uses the guided mode.' in mode.inner_text()
    assert mode.locator('button, select, input, textarea, [data-write]').count() == 0
    assert 'changes only in the chat' in mode.locator('[data-mode-change]').inner_text()
    clean(panel)
    shot(page, 'overview-final-mode-light-900')


@pytest.mark.parametrize('mode', ['training', 'express'])
def test_ov11_the_mode_explainer_says_what_counts_in_each_mode(open_panel, views, mode):
    summary = copy.deepcopy(views['summary.opening'])
    summary['mode'] = mode
    panel = open_tab(open_panel, summary, 'overview', stage='v1')
    goto(panel)
    text = panel.page.locator(f'[data-block="now"] [data-mode="{mode}"]').inner_text()
    assert f'This study uses the {mode} mode.' in text
    assert panel.page.locator(f'[data-mode="{mode}"] .dc-mode-rules li').count() >= 3
    clean(panel)


# --- themes and narrow width (A11Y-3) ------------------------------------------------------------

@pytest.mark.parametrize('theme', THEMES)
@pytest.mark.parametrize('width', [900, 420])
def test_a11y3_wp_b5_views_in_every_theme_and_at_420px(open_panel, views, theme, width):
    """A11Y-3: Overview, Evidence (opened, diagnostics) and What if? (gain curve) under the three themes, 900 and 420 px."""
    panel = open_tab(open_panel, views['summary.opened'], 'overview', theme=theme, width=width, stage='v2')
    page = panel.page
    no_sideways(page)
    shot(page, f'overview-{theme}-{width}')
    feed(panel, evidence=views['evidence.diagnostics'])
    no_sideways(page)
    charts_unscaled(page)
    # The confusion counts keep their column as a label (v0.3: a 2 x 2 grid, each cell named).
    tp = page.locator('[data-confusion="development"] [data-cell="tp"]').first
    assert tp.get_attribute('data-label') == 'acted on'
    assert page.locator('[data-confusion="final"] [data-cell="fn"]').first.get_attribute('data-label') == 'not acted on'
    shot(page, f'evidence-{theme}-{width}')
    feed(panel, scenario=views['scenario'], whatif=views['whatif.opened'])
    no_sideways(page)
    charts_unscaled(page)
    shot(page, f'whatif-{theme}-{width}')
    if theme == 'hc':
        buttons = page.locator('[data-try-rule]').evaluate_all(
            'bs => bs.map(b => parseFloat(getComputedStyle(b).borderTopWidth))')
        assert buttons and all(w >= 1 for w in buttons), buttons
    clean(panel)
