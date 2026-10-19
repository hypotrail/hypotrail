"""WP-B5 views (scope S, simulated browser): the final test first in Evidence, the ledger in
words, development and final evidence apart, cross-validation and the variant, the
diagnostics, the gain curve and share rules of What if?, the next move for the opening of
the final test (a chat act), and the mode explainer.

The real document under the real CSP, offline, on the **captured** payloads of a real
cross-validated Bank study whose final test was opened once and then changed after
(``test/fixtures/captured/*.cv*``), on the captured Online Shoppers view (the scenario
share), and on the hand-written diagnostics fixture (WP-B4's planned shape, to reconcile),
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

import themes

SHOTS = os.environ.get('HYPOTRAIL_SHOTS')
THEMES = ['light', 'dark', 'hc']
FORBIDDEN = re.compile(r'\b(threshold|capacity|precision|recall|positive class|policy|calling rule|selected)\b', re.I)
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
        'evidence.diagnostics': model('evidence', 'evidence.binary.diagnostics'),
        'whatif.opened': model('whatif', 'captured/evidence.binary.cv'),
        'whatif.sealed': model('whatif', 'captured/evidence.binary.cv.sealed'),
        'decisions.opened': model('decisions', 'captured/decisions.binary.cv'),
        'scenario': model('scenario', 'captured/status.shoppers'),
        'raw.summary.opened': payload('captured/summary.binary.cv'),
        'raw.summary.opening': payload('captured/summary.binary.cv.opening'),
        'raw.evidence.opened': payload('captured/evidence.binary.cv'),
        'raw.evidence.diagnostics': payload('evidence.binary.diagnostics'),
    }
    return out


def open_tab(open_panel, summary, tab, theme='light', width=900, stage='v2', **init):
    panel = open_panel(color_scheme=themes.scheme(theme))
    panel.page.set_viewport_size({'width': width, 'height': 900})
    themes.apply(panel.page, theme)
    panel.init(stage=stage, task=summary['task'], **init)
    panel.snapshot(summary)
    if tab != 'overview':
        panel.page.locator(f'[role="tab"][data-tab="{tab}"]').click()
    return panel


def clean(panel):
    assert not (panel.requests or panel.errors or panel.csp or panel.violations()), \
        (panel.requests, panel.errors, panel.csp, panel.violations())
    assert panel.page.locator('body [style]').count() == 0


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
    panel.view_data('evidence', views['evidence.opened'])
    page = panel.page
    order = page.locator('.ht-evidence [data-ev]').evaluate_all('ns => ns.map(n => n.dataset.ev)')
    assert order[:2] == ['final-test', 'development'] or order[0] == 'final-test', order
    first = page.locator('.ht-evidence > section, .ht-evidence > div').evaluate_all(
        'ns => ns.filter(n => n.getBoundingClientRect().height > 0).map(n => n.dataset.ev || n.className)')
    assert first[0] == 'final-test', first
    assert page.locator('.ht-evidence > section').nth(1).get_attribute('data-ledger') == ''
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
    assert 'the calling rule' in card.locator('[data-changed-after]').inner_text()
    trials = card.locator('[data-trials]')
    assert trials.get_attribute('data-trials') == str(views['raw.summary.opened']['trials']['count'])
    assert 'Configurations evaluated: 2' in trials.inner_text() and 'luck' in trials.inner_text()
    assert card.locator('button, [data-write], textarea, input').count() == 0, 'no control: the opening is a chat act'
    clean(panel)
    shot(page, 'evidence-opened-changed-light-900')


def test_ev7_sealed_final_test_points_to_the_chat_and_lists_what_must_be_confirmed(open_panel, views):
    panel = open_tab(open_panel, views['summary.opening'], 'evidence')
    panel.view_data('evidence', views['evidence.sealed'])
    page = panel.page
    card = page.locator('[data-final-test-card="sealed"]')
    raw = views['raw.summary.opening']['final_test']
    assert f"{raw['rows']:,} rows nobody has read" in card.inner_text()
    assert card.locator('[data-partition-line="development"]').inner_text().startswith(f"{raw['development_rows']:,}")
    assert 'the same share of each outcome' in card.inner_text()
    assert card.locator('[data-open-in-chat]').inner_text().startswith('Opening it is a chat act')
    done = card.locator('[data-before]').evaluate_all('ns => ns.map(n => [n.dataset.before, n.dataset.done])')
    assert done == [['policy', 'true'], ['model_variant', 'true'], ['success_criterion', 'true']]
    assert card.locator('button, [data-write]').count() == 0
    assert page.locator('[data-ev="final"] [data-final-evidence="none"]').count() == 1
    clean(panel)
    shot(page, 'evidence-sealed-light-900')


def test_ev7_absent_final_test_says_no_figure_is_independent(open_panel, views):
    summary = copy.deepcopy(views['summary.sealed.split'])
    summary['finalTest'] = {'status': 'absent', 'rows': None, 'method': None, 'fraction': None, 'developmentRows': None,
                            'schemaCheck': None, 'opening': None, 'postFinalTest': False, 'changedAfter': []}
    panel = open_tab(open_panel, summary, 'evidence')
    panel.view_data('evidence', views['evidence.split'])
    card = panel.page.locator('[data-final-test-card="absent"]')
    assert 'No final test' in card.inner_text() and 'independent evidence' in card.inner_text()
    clean(panel)


def test_ev8_the_ledger_explains_each_purpose_and_marks_the_final_test_rows(open_panel, views):
    panel = open_tab(open_panel, views['summary.opened'], 'evidence')
    panel.view_data('evidence', views['evidence.opened'])
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
    panel.view_data('evidence', views['evidence.opened'])
    page = panel.page
    dev = page.locator('[data-ev="development"]')
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
    assert variant.locator('svg.ht-intervals line[data-tone="baseline"]').count() >= 1
    assert variant.locator('[data-zero]').count() >= 1
    sentences = variant.locator('[data-variant-sentence]').evaluate_all('ns => ns.map(n => n.dataset.variantSentence)')
    assert sentences and set(sentences) <= {'one_side', 'includes_zero'}
    cited = variant.locator('[data-variant-sentence] data').first
    assert cited.get_attribute('data-result-id') == raw['policy.evaluation']['result_id']
    fe = raw['final_test.evaluation']
    crit = final.locator('[data-final-criterion]')
    assert crit.get_attribute('data-final-criterion') == fe['values']['criterion']['status']
    assert crit.locator('data[data-path="criterion.gain"]').get_attribute('data-result-id') == fe['result_id']
    assert final.locator('[data-final-metric="precision"] svg.ht-intervals').count() == 2
    # The registry lists the final-test results apart.
    assert page.locator('[data-final-results]').count() == 1
    items = page.locator('[data-results-partition="final_test"] [data-result-item]').evaluate_all('ns => ns.map(n => n.dataset.resultItem)')
    assert items == [fe['result_id']]
    clean(panel)
    shot(page, 'evidence-development-final-light-900')


# --- diagnostics (EV-12) ------------------------------------------------------------------------

def test_ev12_diagnostics_render_when_present_each_number_cited(open_panel, views):
    panel = open_tab(open_panel, views['summary.opened'], 'evidence')
    panel.view_data('evidence', views['evidence.diagnostics'])
    page = panel.page
    section = page.locator('[data-ev="diagnostics"]')
    assert section.count() == 1
    assert section.locator('[data-diag-evaluation]').evaluate_all('ns => ns.map(n => n.dataset.diagEvaluation)') == \
        ['out_of_fold', 'final_test']
    kinds = section.locator('[data-diag]').evaluate_all('ns => ns.map(n => n.dataset.diag)')
    assert kinds == ['confusion', 'gain', 'calibration', 'segments', 'confusion']
    raw = next(r for r in views['raw.evidence.diagnostics']['results']
               if r['activity'] == 'diag.confusion' and r['partition'] == 'development')
    tn = section.locator(f'[data-cell="tn"] data[data-result-id="{raw["result_id"]}"]').first
    assert tn.get_attribute('data-path') == 'confusion.tn'
    assert tn.get_attribute('data-value') == str(raw['values']['confusion']['tn'])
    assert 'missed' in section.locator('[data-confusion="out_of_fold"]').inner_text()
    assert section.locator('[data-diag="calibration"] [data-diagonal]').count() == 1
    assert section.locator('[data-diag="calibration"] line[data-interval]').count() == 5
    assert section.locator('[data-segments="3"]').count() == 1
    charts_unscaled(page)
    clean(panel)
    shot(page, 'evidence-diagnostics-light-900')
    # Without diag.* results the section is absent.
    panel.view_data('evidence', views['evidence.opened'])
    assert page.locator('[data-ev="diagnostics"]').count() == 0


def test_ev12_regression_evidence_holds_no_rule_words(open_panel, views):
    panel = open_tab(open_panel, views['summary.regression'], 'evidence')
    panel.view_data('evidence', views['evidence.regression'])
    page = panel.page
    text = page.locator('#panel-evidence').inner_text()
    assert not FORBIDDEN.search(text), FORBIDDEN.search(text)
    assert page.locator('[data-ev="final-test"]').count() == 1
    clean(panel)


# --- What if?: the gain curve and share rules (WI-6, WI-7) ----------------------------------------

def test_wi6_the_gain_curve_shows_registered_points_and_the_scenario_share(open_panel, views):
    panel = open_tab(open_panel, views['summary.opened'], 'whatif')
    page = panel.page
    loads = [m['view'] for m in panel.posted() if m['type'] == 'load']
    assert 'scenario' in loads and 'whatif' in loads
    panel.view_data('scenario', views['scenario'])
    panel.view_data('whatif', views['whatif.opened'])
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
    panel.view_data('whatif', views['whatif.opened'])
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
    panel = open_tab(open_panel, views['summary.opening'], 'overview', stage=stage)
    page = panel.page
    hero = page.locator('[data-ov="hero"]')
    assert hero.locator('[data-hero-title]').inner_text() == 'Open the final test, in the chat'
    assert hero.locator('[data-hero-chat="final_test"]').count() == 1
    assert hero.locator('button, [data-write]').count() == 0
    assert 'once' in hero.locator('[data-hero-why]').inner_text()
    clean(panel)
    shot(page, f'overview-opening-{stage}-light-900')
    # Stage v0 shows the decision cards without a tab bar.
    if page.locator('[role="tab"][data-tab="decisions"]').count():
        page.locator('[role="tab"][data-tab="decisions"]').click()
    card = page.locator('[data-proposal-card][data-decision="final_test"]')
    assert card.count() == 1
    assert card.locator('textarea, [data-action="confirm"]').count() == 0, 'DC-10: no field, no confirm'
    assert card.locator('[data-final-test-chat]').inner_text().startswith('Answer this one in the chat')
    assert 'Open the final test once for the logistic model' in card.locator('[data-proposed-value]').inner_text()
    clean(panel)
    shot(page, f'decisions-opening-{stage}-light-900')


def test_ov11_where_we_are_shows_the_final_test_and_the_mode(open_panel, views):
    panel = open_tab(open_panel, views['summary.opened'], 'overview', stage='v1')
    page = panel.page
    row = page.locator('[data-final-test-row]')
    assert row.get_attribute('data-final-test-row') == 'changed'
    raw = views['raw.summary.opened']
    assert row.locator('[data-opening-words]').inner_text() == f"“{raw['final_test']['opening']['user_words']}”"
    crit = row.locator('[data-final-criterion]')
    assert crit.get_attribute('data-final-criterion') == raw['criterion']['final_test']['status']
    assert crit.locator('data[data-path="criterion.gain"]').get_attribute('data-result-id') == raw['criterion']['final_test']['result_id']
    assert 'the calling rule' in row.locator('[data-changed-after]').inner_text()
    mode = page.locator('[data-mode-explainer="guided"]')
    assert 'This study uses the guided mode.' in mode.inner_text()
    assert 'opening of the final test' in mode.inner_text().lower() or 'Opening the final test' in mode.inner_text()
    assert mode.locator('button, select, input, textarea, [data-write]').count() == 0
    assert 'changes only in the chat' in mode.locator('[data-mode-change]').inner_text()
    clean(panel)
    shot(page, 'overview-final-mode-light-900')


@pytest.mark.parametrize('mode', ['training', 'express'])
def test_ov11_the_mode_explainer_says_what_counts_in_each_mode(open_panel, views, mode):
    summary = copy.deepcopy(views['summary.opened'])
    summary['mode'] = mode
    panel = open_tab(open_panel, summary, 'overview', stage='v1')
    text = panel.page.locator(f'[data-mode-explainer="{mode}"]').inner_text()
    assert f'This study uses the {mode} mode.' in text
    if mode == 'training':
        assert 'key points' in text and 'because' in text
    else:
        assert "recommended default" in text and 'always yours' in text
    panel.page.locator('[role="tab"][data-tab="decisions"]').click()
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
    page.locator('[role="tab"][data-tab="evidence"]').click()
    panel.view_data('evidence', views['evidence.diagnostics'])
    no_sideways(page)
    charts_unscaled(page)
    # The confusion counts keep their column as a label when the table turns into cards.
    tp = page.locator('[data-confusion="out_of_fold"] td[data-cell="tp"]')
    assert tp.get_attribute('data-label') == 'acted on'
    assert page.locator('[data-confusion="out_of_fold"] td[data-cell="fn"]').get_attribute('data-label') == 'not acted on'
    shot(page, f'evidence-{theme}-{width}')
    page.locator('[role="tab"][data-tab="whatif"]').click()
    panel.view_data('scenario', views['scenario'])
    panel.view_data('whatif', views['whatif.opened'])
    no_sideways(page)
    charts_unscaled(page)
    shot(page, f'whatif-{theme}-{width}')
    if theme == 'hc':
        buttons = page.locator('[data-try-rule]').evaluate_all(
            'bs => bs.map(b => parseFloat(getComputedStyle(b).borderTopWidth))')
        assert buttons and all(w >= 1 for w in buttons), buttons
    clean(panel)
