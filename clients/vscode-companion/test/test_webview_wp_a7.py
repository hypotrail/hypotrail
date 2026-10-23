"""WP-A7 views (scope S, simulated browser): the Data & EDA tab, the Decisions mode and bases,
the header's final-test chip, and the success criterion on the Overview.

The real document under the real CSP, offline, on the **captured** payloads of the real
engine (``test/fixtures/captured``) and on the hand-written fixtures, in the Light+, Dark+ and
High Contrast variable sets (``themes.py``) at 900 and 420 px. With ``HYPOTRAIL_SHOTS=<dir>``
the tests also write screenshots there, for a person to look at; nothing is asserted on them.
Requirement ids: DA-1 to DA-6 (data card), ED-7 to ED-11 (questions, intervals, null band,
leakage detector, quality), DC-7 to DC-9 (mode, bases, concerns, corrections), FR-1 (the
final-test chip), OV-9 (the success criterion), A11Y-3 (themes, 420 px).

This is not a VS Code session.
"""
from __future__ import annotations

import copy
import os
import re
from pathlib import Path

import pytest

from conftest import inline_styles_ok
from panel_cases import expand_eda

import themes

SHOTS = os.environ.get('HYPOTRAIL_SHOTS')
THEMES = ['light', 'dark', 'hc']
FORBIDDEN = re.compile(r'\b(threshold|capacity|precision|recall|positive class|policy|calling rule|decision rule|selected)\b', re.I)


def shot(page, name):
    # Taken after the checks: a full-page screenshot may leave a style attribute behind.
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.evaluate("() => document.querySelectorAll('body [style]').forEach(n => n.setAttribute('data-had-style', ''))")
        page.screenshot(path=str(Path(SHOTS) / f'{name}.png'), full_page=True)
        # Readable parts of a tall page, 1200 px each.
        width, height = page.evaluate('[document.documentElement.scrollWidth, document.documentElement.scrollHeight]')
        for i, top in enumerate(range(0, height, 1200)):
            page.screenshot(path=str(Path(SHOTS) / f'{name}.part{i + 1}.png'), full_page=True,
                            clip={'x': 0, 'y': top, 'width': width, 'height': min(1200, height - top)})
        # Only what the screenshot tool itself added is undone; a style the panel set stays.
        page.evaluate("""() => document.querySelectorAll('body [style]:not([data-had-style])')
          .forEach(n => n.removeAttribute('style'))""")
        page.evaluate("() => document.querySelectorAll('[data-had-style]').forEach(n => n.removeAttribute('data-had-style'))")


@pytest.fixture(scope='module')
def views(model, payload):
    out = {}
    for task in ('binary', 'regression'):
        out[f'summary.{task}'] = model('summary', f'captured/summary.{task}')
        out[f'eda.{task}'] = model('eda', f'captured/evidence.{task}')
        out[f'data.{task}'] = model('data', f'captured/data.{task}')
        out[f'decisions.{task}'] = model('decisions', f'captured/decisions.{task}')
        out[f'raw.data.{task}'] = payload(f'captured/data.{task}')
        out[f'raw.evidence.{task}'] = payload(f'captured/evidence.{task}')
        out[f'raw.summary.{task}'] = payload(f'captured/summary.{task}')
    out['hand.summary'] = model('summary', 'summary.binary')
    out['hand.decisions'] = model('decisions', 'decisions.binary')
    out['hand.eda'] = model('eda', 'evidence.binary')
    return out


def open_tab(open_panel, views, task, tab, theme='light', width=900, summary=None, stage='v2', **init):
    panel = open_panel(color_scheme=themes.scheme(theme))
    panel.page.set_viewport_size({'width': width, 'height': 900})
    themes.apply(panel.page, theme)
    snap = summary or views[f'summary.{task}']
    panel.init(stage=stage, task=snap['task'], **init)
    panel.snapshot(snap)
    if tab != 'overview':
        panel.page.locator(f'[role="tab"][data-tab="{tab}"]').click()
    return panel


def feed_eda(panel, views, task, eda=None):
    panel.view_data('data', views[f'data.{task}'])
    panel.view_data('eda', eda or views[f'eda.{task}'])
    expand_eda(panel.page)


def clean(panel):
    assert not (panel.requests or panel.errors or panel.csp or panel.violations()), \
        (panel.requests, panel.errors, panel.csp, panel.violations())
    assert inline_styles_ok(panel.page)


# --- the data card -------------------------------------------------------------------------

@pytest.mark.parametrize('task', ['binary', 'regression'])
def test_da1_the_tab_reads_the_data_card_and_shows_it_first(open_panel, views, task):
    """DA-1: the Data & EDA tab asks for `data`, and the data card comes before the exploration."""
    panel = open_tab(open_panel, views, task, 'eda')
    page = panel.page
    assert page.locator('[role="tab"][data-tab="eda"]').inner_text() == 'Data & EDA'
    assert {'v': 2, 'type': 'load', 'view': 'data'} in panel.posted()
    assert page.locator('[data-data-loading]').count() == 1, 'a loading state until the read answers'
    feed_eda(panel, views, task)
    card = page.locator('[data-data-card]')
    assert card.count() == 1
    order = page.evaluate("""() => {
      const all = [...document.querySelectorAll('[data-data-card], [data-quality-card], .eda-banner, [data-eda-card]')];
      return all.map(n => n.matches('[data-data-card]') ? 'data' : n.matches('[data-quality-card]') ? 'quality'
        : n.matches('.eda-banner') ? 'banner' : 'chart');
    }""")
    assert order[:3] == ['data', 'quality', 'banner'] and set(order[3:]) == {'chart'}, order
    raw = views[f'raw.data.{task}']
    assert card.locator('[data-fact="unit"]').inner_text().startswith('One row')
    assert raw['observation_unit']['value'] in card.locator('[data-fact="unit"]').inner_text()
    rows = card.locator('[data-development-rows]')
    assert rows.get_attribute('data-development-rows') == str(raw['development']['rows'])
    # v0.3 (WP-E2): stat tiles, the rows and the columns apart.
    assert rows.inner_text() == f"{raw['development']['rows']:,}"
    assert f"{raw['development']['columns']}\nColumns" in card.locator('.eda-facts').inner_text()
    expected_final_test_line = raw['final_test'].get('junior_text') or raw['final_test']['line']
    assert card.locator('[data-seal-line]').inner_text().endswith(expected_final_test_line)
    assert card.locator('[data-data-note]').inner_text() == raw['note']['text']
    clean(panel)
    shot(page, f'data-card-{task}-light-900')


@pytest.mark.parametrize('task', ['binary', 'regression'])
def test_da2_five_rows_target_first_and_excluded_columns_marked(open_panel, views, task):
    """DA-2: the five fixed rows, the target column first, each excluded column marked (not by colour only)."""
    panel = open_tab(open_panel, views, task, 'eda')
    feed_eda(panel, views, task)
    page = panel.page
    raw = views[f'raw.data.{task}']
    heads = page.locator('[data-five-rows] thead th').evaluate_all('ts => ts.map(t => t.dataset.column)')
    assert heads == raw['rows']['columns'] and heads[0] == raw['target']['column']
    assert page.locator('[data-five-rows] tbody tr').count() == raw['rows']['n_rows'] == 5
    first = raw['rows']['items'][0]['values']
    # v0.3 (WP-E2): the five rows sit in a closed "Five example rows" disclosure: read their text.
    cells = page.locator('[data-five-rows] tbody tr').first.locator('td').all_text_contents()
    assert cells == ['(missing)' if first[c] is None else str(first[c]) for c in heads]
    decided = {v['name']: (v['decided'] or {}).get('value') for g in raw['groups'] for v in g['variables']}
    excluded = [c for c in heads if decided.get(c) in ('not_available', 'uncertain_excluded')]
    assert excluded, 'the capture excludes columns'
    for name in excluded:
        assert page.locator(f'[data-five-rows] th[data-column="{name}"]').text_content() == f'{name} ✗'
    assert page.locator('[data-excluded-legend]').count() == 1
    clean(panel)


@pytest.mark.parametrize('task', ['binary', 'regression'])
def test_da3_the_dictionary_is_grouped_in_the_case_order(open_panel, views, task):
    """DA-3: one group row per group, in the engine's order, each variable under its group with its counts."""
    panel = open_tab(open_panel, views, task, 'eda')
    feed_eda(panel, views, task)
    page = panel.page
    raw = views[f'raw.data.{task}']
    groups = page.locator('[data-dictionary] [data-group]').evaluate_all('ns => ns.map(n => n.dataset.group)')
    assert groups == [g['group'] for g in raw['groups']]
    names = page.locator('[data-dictionary] [data-variable]').evaluate_all('ns => ns.map(n => n.dataset.variable)')
    assert names == [v['name'] for g in raw['groups'] for v in g['variables']]
    for g in raw['groups']:
        for v in g['variables']:
            row = page.locator(f'[data-dictionary] [data-variable="{v["name"]}"]')
            assert row.locator(f'[data-missing-cell="{v["name"]}"]').inner_text() == f'{v["n_missing"]:,}'
            assert v['description'] in row.inner_text()
            known = row.locator('[data-known]').get_attribute('data-known')
            if v['role'] == 'target':
                assert known == 'target'
            elif v['decided']:
                assert known == v['decided']['value'], v['name']
            for s in v['special_values']:
                assert row.locator(f'[data-special="{v["name"]}:{s["value"]}"]').count() == 1
    clean(panel)


@pytest.mark.parametrize('task', ['binary', 'regression'])
def test_da4_french_labels_toggle_when_the_case_has_them(open_panel, views, task):
    """DA-4: the Meaning column swaps each description for the case's labels.fr, marked lang="fr"
    (v0.3, R12 merged into R21: a "Meanings EN | FR" toggle that names the language shown)."""
    panel = open_tab(open_panel, views, task, 'eda')
    feed_eda(panel, views, task)
    page = panel.page
    raw = views[f'raw.data.{task}']
    toggle = page.locator('[data-french-toggle]')
    assert toggle.locator('button').all_inner_texts() == ['Meanings EN', 'Meanings FR']
    assert toggle.get_attribute('aria-pressed') == 'false'
    assert page.locator('[data-meanings="en"]').get_attribute('aria-pressed') == 'true'
    page.locator('[data-meanings="fr"]').click()
    assert page.locator('[data-french-toggle]').get_attribute('aria-pressed') == 'true'
    assert page.locator('[data-meanings="fr"]').get_attribute('aria-pressed') == 'true'
    for g in raw['groups']:
        for v in g['variables']:
            desc = page.locator(f'[data-dictionary] [data-variable="{v["name"]}"] [data-description]')
            if v['description_fr']:
                assert desc.get_attribute('lang') == 'fr' and desc.inner_text() == v['description_fr']
            else:
                assert desc.inner_text() == v['description']
    shot(page, f'data-card-{task}-french')
    page.locator('[data-meanings="en"]').click()
    assert page.locator('[data-dictionary] [lang="fr"]').count() == 0
    clean(panel)


def test_da5_no_french_toggle_without_french_labels(open_panel, views, model, payload):
    raw = copy.deepcopy(payload('captured/data.binary'))
    raw['target']['description_fr'] = None
    for g in raw['groups']:
        for v in g['variables']:
            v['description_fr'] = None
    panel = open_tab(open_panel, views, 'binary', 'eda')
    panel.view_data('data', model('data', raw))
    panel.view_data('eda', views['eda.binary'])
    assert panel.page.locator('[data-french-toggle]').count() == 0
    clean(panel)


def test_da6_the_data_card_holds_no_outcome_rate(open_panel, views):
    """DA-6: the data card shows no figure about the outcome (CLI-CONTRACT §11.1)."""
    panel = open_tab(open_panel, views, 'binary', 'eda')
    feed_eda(panel, views, 'binary')
    card = panel.page.locator('[data-data-card]')
    assert card.locator('[data-result-id]').count() == 0
    assert '%' not in card.inner_text()
    clean(panel)


# --- the exploration ---------------------------------------------------------------------------

@pytest.mark.parametrize('task', ['binary', 'regression'])
def test_ed7_every_card_is_titled_by_its_question(open_panel, views, task):
    """ED-7: each chart is titled by the question the engine says it answers."""
    panel = open_tab(open_panel, views, task, 'eda')
    feed_eda(panel, views, task)
    page = panel.page
    for card in views[f'eda.{task}']['cards']:
        sel = f'[data-quality-card="{card["slot"]}"]' if card['kind'] == 'quality' else f'[data-eda-card="{card["slot"]}"]'
        assert card['question'], card['slot']
        assert page.locator(f'{sel} h3').first.inner_text() == card['question']
    clean(panel)


@pytest.mark.parametrize('task', ['binary', 'regression'])
def test_ed8_intervals_and_the_null_band_are_drawn_and_cited(open_panel, views, task):
    """ED-8: a by-column chart draws each group's interval and its shuffled-outcome band, says
    whether the spread is outside the band, and every number is the engine's."""
    panel = open_tab(open_panel, views, task, 'eda')
    feed_eda(panel, views, task)
    page = panel.page
    slot = 'eda.rate_by:job' if task == 'binary' else 'eda.mean_by:model_year'
    card = page.locator(f'[data-eda-card="{slot}"]')
    entry = next(r for r in views[f'raw.evidence.{task}']['results'] if r['slot'] == slot)
    groups = [g for g in entry['values']['groups'] if g.get('interval')]
    # v0.3 (WP-E2): an HTML grid; each group a point inside its interval, the band behind.
    assert card.locator('[data-chart] [data-interval]').count() >= len(groups) > 0
    assert card.locator('[data-chart] [data-band]').count() >= len([g for g in groups if g.get('null_band')]) > 0
    band = entry['values']['null_band']['chart']
    line = card.locator('[data-null-band]')
    assert line.get_attribute('data-null-band') == ('outside' if band['outside'] else 'inside')
    cited = line.locator('[data-result-id]').evaluate_all('ns => ns.map(n => [n.dataset.path, Number(n.dataset.value)])')
    assert ['null_band.chart.observed', band['observed']] in [[p, v] for p, v in cited]
    assert ['null_band.shuffles', 19] in [[p, v] for p, v in cited]
    assert card.locator('[data-legend]').count() == 1
    target = 'eda.target_rate' if task == 'binary' else 'eda.target_summary'
    interval = page.locator(f'[data-eda-card="{target}"] [data-interval-line] [data-result-id]')
    assert interval.count() == 2
    clean(panel)


@pytest.mark.parametrize('task', ['binary', 'regression'])
def test_ed9_the_leakage_detector_asks_the_legitimacy_question(open_panel, views, task):
    """ED-9: the single-feature signal flags a feature with a question, never a verdict, and
    says the junior's availability decision for it in words."""
    panel = open_tab(open_panel, views, task, 'eda')
    feed_eda(panel, views, task)
    page = panel.page
    card = page.locator('[data-eda-card="eda.single_feature_signal"]')
    values = next(r for r in views[f'raw.evidence.{task}']['results'] if r['slot'] == 'eda.single_feature_signal')['values']
    assert card.locator('[data-chart="bars"] [data-bar]').count() == len(values['signals'])
    if values['questions']:
        for q in values['questions']:
            leak = card.locator(f'[data-leak="{q["feature"]}"]')
            assert leak.locator('strong').first.inner_text().startswith('Leakage detector')
            score = leak.locator('[data-result-id]')
            assert score.get_attribute('data-path').startswith('questions.')
            assert float(score.get_attribute('data-value')) == q['score']
            assert score.inner_text() == f'{q["score"]:.2f}'
            assert 'Is its value really known at the prediction moment' in leak.inner_text()
            assert leak.locator('[data-leak-decision]').get_attribute('data-leak-decision') == (q['availability'] or 'none')
        if task == 'binary':
            assert 'duration' in [q['feature'] for q in values['questions']]
            assert 'leaves it out of the models' in card.locator('[data-leak="duration"]').inner_text()
    else:
        assert card.locator('[data-no-leak]').count() == 1
    clean(panel)
    shot(page, f'eda-{task}-light-900')


@pytest.mark.parametrize('task', ['binary', 'regression'])
def test_ed10_the_quality_check_reads_development_rows_without_the_target(open_panel, views, task):
    """ED-10: the quality card says it reads the development rows without the target, with the engine's counts."""
    panel = open_tab(open_panel, views, task, 'eda')
    feed_eda(panel, views, task)
    page = panel.page
    card = page.locator('[data-quality-card="eda.quality"]')
    values = next(r for r in views[f'raw.evidence.{task}']['results'] if r['slot'] == 'eda.quality')['values']
    # v0.3 (WP-E2): the eyebrow says it, the "Why?" says it in a sentence.
    assert card.locator('[data-eyebrow]').text_content() == ('Quality · development rows, no outcome' if task == 'binary'
                                                           else 'Quality · development rows, no target')
    assert 'without the target' in card.text_content()
    read = [n for n in card.locator('[data-result-id]').evaluate_all('ns => ns.map(n => n.dataset.path)')]
    assert 'n_rows' in read and 'n_columns' in read
    for r in [c for c in values['cardinality'] if c['rare']]:
        assert r['column'] in card.locator('[data-quality-detail="rare"]').text_content()
    if task == 'binary':
        assert 'dec (14)' in card.locator('[data-quality-detail="rare"]').text_content()
    clean(panel)


@pytest.mark.parametrize('task', ['binary', 'regression'])
def test_ed11_the_banner_counts_the_looks_and_names_the_sealed_rows(open_panel, views, task):
    panel = open_tab(open_panel, views, task, 'eda')
    feed_eda(panel, views, task)
    page = panel.page
    raw = views[f'raw.summary.{task}']
    assert page.locator('[data-looks]').get_attribute('data-looks') == str(raw['eda_looks']['target_looks'])
    assert page.locator('[data-looks-count]').inner_text() == str(raw['eda_looks']['target_looks'])
    assert page.locator('[data-banner-seal]').inner_text().endswith(
        f"The {raw['final_test']['rows']:,} final-test rows are never read here.")
    clean(panel)


def test_ed12_run_another_chart_shows_its_question_before_it_runs(open_panel, views):
    """ED-12: the request offers training-row charts only and says the question first; a chart
    that reads the outcome says it is one more look."""
    panel = open_tab(open_panel, views, 'binary', 'eda')
    feed_eda(panel, views, 'binary')
    page = panel.page
    assert page.locator('#eda-request-title').inner_text() == 'Run another chart'
    page.locator('#eda-variable').select_option('balance')
    page.locator('#eda-chart').select_option('eda.distribution')
    # v0.3 (WP-E2): the per-column chart's question (the correlation matrix has its own).
    q = page.locator('[data-request-question]:not([data-request-question="eda.correlation"])')
    assert q.get_attribute('data-request-question') == 'eda.distribution'
    assert 'How are the values of balance spread on the training rows?' in q.inner_text()
    assert page.locator('[data-one-more-look]').count() == 0
    page.locator('#eda-chart').select_option('eda.rate_by')
    assert 'Does the outcome rate differ across the values of balance' in q.inner_text()
    assert page.locator('[data-one-more-look]').count() == 1
    options = page.locator('#eda-chart option').evaluate_all('os => os.map(o => o.value)')
    assert set(options) <= {'eda.distribution', 'eda.rate_by', 'eda.mean_by'}
    page.locator('#eda-run').click()
    assert panel.posted()[-1] == {'v': 2, 'type': 'run_eda', 'activity': 'eda.rate_by', 'column': 'balance',
                                  'revision': views['eda.binary']['revision']}
    clean(panel)


def test_ed13_regression_data_and_eda_hold_no_decision_rule_vocabulary(open_panel, views):
    """INV-12 on the Data & EDA tab of Auto MPG, data card and leakage detector included."""
    panel = open_tab(open_panel, views, 'regression', 'eda')
    feed_eda(panel, views, 'regression')
    page = panel.page
    page.locator('[data-french-toggle]').click()
    text = page.locator('#panel-eda').inner_text()
    assert not FORBIDDEN.search(text), FORBIDDEN.search(text)
    clean(panel)


# --- Decisions --------------------------------------------------------------------------------

def test_dc7_the_mode_line_says_what_counts_as_an_answer(open_panel, views):
    """DC-7: the guided mode, what counts as an answer, the reason at a trade-off, and no control to change it."""
    panel = open_tab(open_panel, views, 'binary', 'decisions', stage='v2')
    page = panel.page
    mode = page.locator('[data-mode="guided"]')
    assert mode.count() == 1
    text = mode.inner_text()
    assert 'This study uses the guided mode.' in text
    # v0.3 (WP-B, R27): a reason is optional in the guided mode.
    assert 'A reason is optional, also for the decision rule and the conclusion' in text
    assert 'changes only in the chat' in text
    assert mode.locator('button, select, input, textarea, [data-write]').count() == 0
    card = page.locator('[data-proposal-card][data-decision="policy"]')
    # WP-E1: the card has no words field, so no reason hint; it points to the chat.
    assert card.locator('[data-reason-hint]').count() == 0
    assert card.locator('[data-answer-in-chat]').count() == 1
    clean(panel)


def test_dc7_regression_mode_names_the_model_choice(open_panel, views):
    panel = open_tab(open_panel, views, 'regression', 'decisions', stage='v1')
    text = panel.page.locator('[data-mode="guided"]').inner_text()
    # v0.3 (WP-B, R27): the reason is optional, also for the model choice.
    assert 'also for the model choice and the conclusion' in text and not FORBIDDEN.search(text)
    clean(panel)


def test_dc8_bases_concerns_and_corrections_in_the_history(open_panel, views):
    """DC-8: restated, endorsed and delegated as chips (their meaning in the hover); the agent's
    concern kept on the confirmation; a later correction in the junior's words."""
    panel = open_tab(open_panel, views, 'binary', 'decisions', summary=views['hand.summary'], stage='v1')
    panel.view_data('decisions', views['hand.decisions'])
    page = panel.page
    chips = page.locator('[data-history-row] [data-basis]').evaluate_all(
        'ns => ns.map(n => [n.closest("[data-history-row]").dataset.historyRow, n.dataset.basis, n.textContent, n.title])')
    by_row = {row: (basis, text, title) for row, basis, text, title in chips}
    assert by_row['prediction_time:3'][:2] == ('restated', 'restated')
    assert by_row['feature_availability:5'][:2] == ('endorsed', 'endorsed')
    assert by_row['split:7'][:2] == ('delegated_default', 'delegated (this decision)')
    assert all(title for _, _, title in by_row.values())
    concern = page.locator('[data-agent-concern="feature_availability"]')
    assert concern.inner_text().startswith('Point raised by the agent before you confirmed, kept by you:')
    assert 'inflation applies to campaign' in concern.inner_text()
    correction = page.locator('[data-correction="n_2"]')
    assert correction.inner_text().startswith('Your later correction, in your words:')
    assert page.locator('[data-history-row="feature_availability:5"] [data-correction]').count() == 1
    clean(panel)
    shot(page, 'decisions-history-light-900')


def test_dc9_the_two_governance_decisions_read_in_words(open_panel, views):
    """DC-9: the success criterion and the data preparation in words in the history (captured Bank)."""
    panel = open_tab(open_panel, views, 'binary', 'decisions', stage='v1')
    panel.view_data('decisions', views['decisions.binary'])
    page = panel.page
    crit = page.locator('[data-history-row^="success_criterion:"] [data-value-raw]').first
    assert crit.inner_text() == 'Adopt only if precision beats the baseline by at least 5 points'
    prep = page.locator('[data-history-row^="preprocessing:"] [data-value-raw]').first
    assert prep.inner_text().startswith('Missing values not flagged')
    assert not re.search(r'\{"', page.locator('[data-history]').inner_text()), 'no raw JSON value'
    clean(panel)


# --- the header and the Overview ----------------------------------------------------------------

@pytest.mark.parametrize('tab', ['overview', 'eda', 'decisions', 'evidence', 'whatif', 'learn'])
def test_fr1_the_final_test_chip_is_on_every_tab(open_panel, views, tab):
    panel = open_tab(open_panel, views, 'binary', tab, stage='v3')
    chip = panel.page.locator('header [data-final-test]')
    assert chip.get_attribute('data-final-test') == 'sealed'
    assert chip.inner_text() == 'Final test sealed · 904 rows'
    assert chip.get_attribute('title')
    clean(panel)


def test_fr1_v0_shows_the_chip_and_a_legacy_study_says_no_final_test(open_panel, views):
    panel = open_tab(open_panel, views, 'binary', 'overview', stage='v0')
    assert panel.page.locator('header [data-final-test]').inner_text() == 'Final test sealed · 904 rows'
    legacy = copy.deepcopy(views['summary.binary'])
    legacy['finalTest'] = {'status': 'absent', 'rows': None, 'method': None, 'fraction': None, 'developmentRows': None}
    panel.snapshot({**legacy, 'revision': legacy['revision'] + 1})
    chip = panel.page.locator('header [data-final-test]')
    assert chip.get_attribute('data-final-test') == 'absent' and chip.inner_text() == 'No final test'
    clean(panel)
    shot(panel.page, "overview-legacy-no-final-test")


def test_ov9_where_we_are_shows_the_success_criterion_status(open_panel, views):
    """OV-9: the criterion in words, its status (met), and the engine's gain with its interval, cited."""
    panel = open_tab(open_panel, views, 'binary', 'overview', summary=views['hand.summary'], stage='v1')
    page = panel.page
    row = page.locator('[data-recap-line="Criterion"]')
    assert row.get_attribute('data-criterion') == 'met'
    assert row.locator('[data-criterion-status]').inner_text() == 'met'
    assert 'Adopt only if precision beats the baseline by at least 5 points' in row.inner_text()
    cited = row.locator('[data-criterion-gain] [data-result-id]').evaluate_all('ns => ns.map(n => n.textContent)')
    assert cited == ['+30.5', '+21.4', '+40.2']
    assert 'when you select the top 100 by score' in row.inner_text()
    shot(page, 'overview-criterion')
    for status in ('uncertain', 'not_met', 'not_assessed'):
        changed = copy.deepcopy(views['hand.summary'])
        changed['criterion']['status'] = status
        changed['revision'] += 1
        panel.snapshot(changed)
        assert row.get_attribute('data-criterion') == status
    clean(panel)


def test_ov9_the_regression_criterion_reads_as_a_share(open_panel, views, model, payload):
    raw = copy.deepcopy(payload('captured/summary.regression'))
    raw['criterion'].update({'status': 'uncertain', 'gain': 0.123, 'low': -0.02, 'high': 0.25, 'minimum': 0.1,
                             'result_id': 'a' * 64})
    summary = model('summary', raw)
    panel = open_tab(open_panel, views, 'regression', 'overview', summary=summary, stage='v1')
    row = panel.page.locator('[data-recap-line="Criterion"]')
    assert row.locator('[data-criterion-gain] [data-result-id]').all_inner_texts() == ['+12.3%', '-2.0%', '+25.0%']
    assert not FORBIDDEN.search(row.inner_text())
    clean(panel)


# --- themes, narrow width --------------------------------------------------------------------------

@pytest.mark.parametrize('theme', THEMES)
@pytest.mark.parametrize('width', [900, 420])
@pytest.mark.parametrize('task', ['binary', 'regression'])
def test_a11y3_the_new_views_under_every_theme_and_420px(open_panel, views, task, theme, width):
    """A11Y-3 for WP-A7: no sideways page scroll, no style attribute, chart text not upscaled, in
    every theme and at 420 px; the header chip and the leakage box keep a visible border in HC."""
    panel = open_tab(open_panel, views, task, 'eda', theme=theme, width=width, stage='v2')
    feed_eda(panel, views, task)
    page = panel.page
    assert page.evaluate('document.scrollingElement.scrollWidth <= window.innerWidth + 1'), 'Data & EDA scrolls sideways'
    sizes = page.evaluate("""() => [...document.querySelectorAll('#panel-eda svg.ht-chart')].filter(s => s.getBoundingClientRect().width > 0)
      .map(svg => { const vb = svg.getAttribute('viewBox').split(/\\s+/).map(Number);
        return svg.getBoundingClientRect().width / vb[2]; })""")
    # v0.3 (WP-E2): the bars and histograms are HTML grids; an SVG (the box plot) is never upscaled.
    assert page.locator('#panel-eda [role="img"][aria-label]').count() > 0
    assert max(sizes, default=0) <= 1.0001
    chip = page.locator('header [data-final-test]')
    assert float(chip.evaluate('n => parseFloat(getComputedStyle(n).borderTopWidth)')) >= 1
    shot(page, f'eda-{task}-{theme}-{width}')
    page.locator('[role="tab"][data-tab="decisions"]').click()
    panel.view_data('decisions', views[f'decisions.{task}'])
    assert page.evaluate('document.scrollingElement.scrollWidth <= window.innerWidth + 1'), 'Decisions scrolls sideways'
    shot(page, f'decisions-{task}-{theme}-{width}')
    page.locator('[role="tab"][data-tab="overview"]').click()
    assert page.evaluate('document.scrollingElement.scrollWidth <= window.innerWidth + 1'), 'Overview scrolls sideways'
    clean(panel)
    shot(page, f'overview-{task}-{theme}-{width}')
