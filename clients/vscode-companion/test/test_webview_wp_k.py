"""v0.3 WP-K (scope S, simulated browser): the panel shows what WP-F1 added, read only.

On the **captured** payloads of the real engine (``panel_cases.py``): the cross-validated Bank
study with three variants (a stronger penalty, an Explainable Boosting Machine, gradient
boosting; ``families``), the split Bank study (one v0.2b variant, no cross-validation;
``binary``), and Auto MPG (``regression``). Checked: the variant budget (used of three, a
replaced variant counted by the engine), the configurations compared fold by fold with mean ±
standard error and the paired difference, the one-standard-error pick, the selection optimism
and the stop advice, in the panel language; the family shortlist with the checks that motivate
it (here: none, "no evidence for a non-linear family yet"); the EBM's terms and shape and the
boosting's permutation importance; the budget on a waiting variant proposal (Decisions); the
journey bar's short labels (no word broken at 420 px); the refusal explanation in French. Every
figure is a cited value of a registered result. Requirement ids: EV-13, EV-14, R21, R24,
R24bis, R26, R28, INV-7. This is not a VS Code session.

``HYPOTRAIL_SHOTS=<dir>`` also writes element screenshots of the new cards (light, dark, high
contrast; 420 and 900 px; English and French).
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from panel_cases import load_views, open_case

SHOTS = os.environ.get('HYPOTRAIL_SHOTS')
RID = re.compile(r'\b[0-9a-f]{12,64}\b')


@pytest.fixture(scope='module')
def views(model, payload):
    out = load_views(model, payload)
    out['summary.families.proposal'] = model('summary', 'captured/summary.binary.families.proposal')
    out['trials.families.proposal'] = model('trials', 'captured/status.binary.families.proposal')
    return out


def evidence(open_panel, views, case='families', lang='en', width=900, theme='light-modern'):
    panel = open_case(open_panel, views, case=case, lang=lang, width=width, theme=theme)
    panel.page.locator('[role="tab"][data-tab="evidence"]').click()
    return panel, panel.page


# --- the selection among the variants ------------------------------------------------------

def test_the_selection_card_cites_the_stored_comparison_fold_by_fold(open_panel, views):
    """EV-13: every figure is the stored selection of the current evaluation, cited."""
    panel, page = evidence(open_panel, views)
    card = page.locator('[data-ev="selection"]')
    assert card.count() == 1
    sel = views['evidence.families']['selection']
    # The budget: three of three used (the live view), as a chip and a sentence.
    assert card.locator('[data-trial-budget]').get_attribute('data-trial-budget') == '3/3'
    assert card.locator('[data-budget-chip]').inner_text() == '3 of 3 variants used'
    # One row per configuration, the candidate first; mean ± SE and the paired difference cited.
    table = card.locator('[data-selection-table]')
    assert table.get_attribute('data-selection-table') == '4'
    rows = table.locator('tbody tr')
    assert rows.evaluate_all('rs => rs.map(r => r.dataset.configuration)') == \
        ['fit.logistic', 'fit.variant', 'fit.variant:2', 'fit.variant:3']
    first = rows.nth(0)
    assert 'Logistic model (candidate)' in first.inner_text()
    assert '—' in first.inner_text(), 'the candidate has no difference with itself'
    for i, cfg in enumerate(sel['configurations']):
        cited = rows.nth(i).locator(f'data[data-path="model_selection.configurations.{i}.mean"]')
        assert cited.get_attribute('data-result-id') == sel['resultId']
        assert float(cited.get_attribute('value')) == cfg['mean']['value']
    names = rows.evaluate_all('rs => rs.map(r => r.firstChild.textContent)')
    assert names[1] == 'Stronger penalty' and names[2] == 'Explainable boosting'
    assert names[3].startswith('Gradient boosting') and names[3].endswith('kept')
    # The paired differences, one row per variant, on a zero line.
    chart = card.locator('[data-selection-chart="difference"]')
    assert chart.locator('[data-interval-row]').count() == 3
    assert chart.locator('[data-zero]').count() == 3
    # Fold by fold: five folds, every value cited from the evaluation.
    folds = card.locator('[data-fold-by-fold]')
    folds.locator('summary').click()
    assert folds.locator('[data-selection-folds]').get_attribute('data-selection-folds') == '5'
    assert folds.locator('data[data-result-id]').count() == 5 * 4
    # The question each variant answers (the junior's or the agent's words, quoted).
    assert card.locator('[data-variant-question]').count() == 3
    # The one-standard-error pick, the optimism (cited), and the stop advice in English.
    finding = card.locator('.ht-finding').inner_text()
    assert finding.startswith('The one-standard-error rule keeps Gradient boosting.')
    opt = card.locator('[data-selection-optimism] data')
    assert opt.get_attribute('data-path') == 'model_selection.optimism.estimate'
    advice = card.locator('[data-selection-advice]')
    assert advice.get_attribute('data-selection-advice') == 'budget_exhausted'
    assert 'Stop here' in advice.inner_text()
    assert sel['advice']['texts']['en'] in advice.inner_text()
    assert card.locator('.ht-src').inner_text().startswith('Source · policy.evaluation · ')
    assert not RID.search(card.inner_text().replace(card.locator('.ht-src').inner_text(), ''))


def test_the_selection_card_reads_in_french(open_panel, views):
    panel, page = evidence(open_panel, views, lang='fr')
    card = page.locator('[data-ev="selection"]')
    sel = views['evidence.families']['selection']
    assert card.locator('[data-budget-chip]').inner_text() == '3 variantes sur 3 utilisées'
    assert card.locator('h3').inner_text() == 'Quelle configuration garder, et un autre essai vaut-il la peine ?'
    advice = card.locator('[data-selection-advice]')
    assert 'Arrêtez-vous ici' in advice.inner_text()
    assert sel['advice']['texts']['fr'] in advice.inner_text()
    assert advice.locator('[data-en-marker]').count() == 0, 'the engine sent French: no (en) marker'
    assert card.locator('.ht-finding').inner_text().startswith("La règle d'une erreur type retient : Gradient boosting.")


def test_a_split_study_shows_the_budget_and_why_folds_are_not_compared(open_panel, views):
    panel, page = evidence(open_panel, views, case='binary')
    card = page.locator('[data-ev="selection"]')
    assert card.count() == 1
    assert card.locator('[data-trial-budget]').get_attribute('data-trial-budget') == '1/3'
    assert card.locator('[data-selection-table]').count() == 0
    assert card.locator('[data-selection-advice]').get_attribute('data-selection-advice') == 'not_available'
    card.locator('details.ht-why summary').click()
    assert 'before the budget existed' in card.locator('details.ht-why').inner_text()


# --- the family shortlist -------------------------------------------------------------------

def test_the_shortlist_says_there_is_no_evidence_for_a_nonlinear_family_yet(open_panel, views):
    """EV-14: the engine's recommendation, and no flag: no evidence for a non-linear family yet."""
    panel, page = evidence(open_panel, views)
    card = page.locator('[data-ev="families"]')
    assert card.count() == 1
    assert card.locator('[data-family-recommendation]').get_attribute('data-family-recommendation') == 'stay_linear'
    assert card.locator('[data-no-family-evidence="checked"]').inner_text().startswith(
        'No evidence for a non-linear family yet')
    families = card.locator('[data-family]').evaluate_all('ls => ls.map(l => [l.dataset.family, l.dataset.shortlisted])')
    assert families == [['linear', 'true'], ['ebm', 'false'], ['hgb', 'false']]
    assert 'glass box' in card.locator('[data-family="ebm"]').inner_text()
    assert 'black box' in card.locator('[data-family="hgb"]').inner_text()
    texts = views['trials.families']['families']['texts']
    assert texts['en'] in card.locator('.ht-finding').inner_text()
    card.locator('details.ht-why summary').click()
    assert 'balance' in card.locator('details.ht-why').inner_text(), 'the features the checks tested'
    assert card.locator('.ht-src').inner_text().startswith('Source · diag.binary · ')


def test_the_shortlist_lists_the_flags_that_motivate_a_family(open_panel, views):
    """A flag of the linear checks (here a curved shape in balance) names the check and its p."""
    import copy
    trials = copy.deepcopy(views['trials.families'])
    f = trials['families']
    f['recommendation'] = 'compare_nonlinear'
    f['flags'] = [{'check': 'nonlinearity', 'feature': 'balance', 'pValue': 0.0004, 'slope': None},
                  {'check': 'calibration_slope', 'feature': None, 'pValue': None, 'slope': 0.71}]
    f['shortlist'] = ['linear', 'ebm', 'hgb']
    f['dataContingent'] = True
    for x in f['families']:
        x['motivated'] = x['family'] != 'linear'
    panel, page = evidence(open_panel, views, lang='fr')
    panel.view_data('trials', trials)
    card = page.locator('[data-ev="families"]')
    flags = card.locator('[data-family-flag]').all_inner_texts()
    assert flags[0] == 'Une forme courbe pour balance (p < 0.001)'
    assert flags[1].startswith('Une pente de calibration globale de 0,71, hors de 0,8 à 1,2')
    assert card.locator('[data-family="ebm"]').get_attribute('data-shortlisted') == 'true'
    assert 'motivée par un signal' in card.locator('[data-family="ebm"]').inner_text()
    assert card.locator('[data-family-contingent]').count() == 1


# --- each family's own diagnostics -----------------------------------------------------------

def test_the_ebm_terms_and_shape_and_the_boosting_importance_are_cited(open_panel, views):
    """EV-14: each family's own diagnostics, every value cited to its fit."""
    panel, page = evidence(open_panel, views)
    fits = {f['slot']: f for f in views['evidence.families']['familyFits']}
    ebm = page.locator('[data-ev="family-fit"][data-family-fit="ebm"]')
    assert ebm.count() == 1
    assert ebm.locator('h3').inner_text() == 'Which terms carry the explainable boosting model, and with what shape?'
    bars = ebm.locator('[data-family-importance] [data-bar]')
    assert bars.count() == len(fits['fit.variant:2']['terms'])
    assert ebm.locator('[data-family-importance] data[data-result-id]').first.get_attribute('data-result-id') == \
        fits['fit.variant:2']['resultId']
    # The top term's shape is drawn (a nominal one as points on a zero line), the next under a disclosure.
    shape = ebm.locator('[data-family-shape]').first
    assert shape.get_attribute('data-family-shape') == fits['fit.variant:2']['terms'][0]['term']
    assert ebm.locator('[data-more-shapes]').count() == 1
    hgb = page.locator('[data-ev="family-fit"][data-family-fit="hgb"]')
    assert hgb.locator('h3').inner_text() == 'Which columns does the boosting model rely on?'
    assert hgb.locator('[data-family-importance] [data-bar]').count() == len(fits['fit.variant:3']['columns'])
    assert 'Drop in AUC when a column is shuffled' in hgb.inner_text()
    assert hgb.locator('.ht-src').inner_text().startswith('Source · fit.variant · ')


# --- the Decisions card of a waiting variant proposal ----------------------------------------

def test_a_waiting_variant_proposal_shows_the_budget_and_the_shortlist(open_panel, views):
    panel = open_panel()
    panel.init(stage='v3', task='binary')
    panel.snapshot(views['summary.families.proposal'])
    panel.view_data('trials', views['trials.families.proposal'])
    page = panel.page
    page.locator('[role="tab"][data-tab="decisions"]').click()
    note = page.locator('[data-decision="model_variant"] [data-trials-note]')
    assert note.count() == 1
    assert note.locator('[data-trial-budget]').inner_text() == 'Trial budget: 0 of 3 variants used, 3 left.'
    assert note.locator('[data-shortlist-text]').get_attribute('data-shortlist-text') == 'stay_linear'
    # The value in words, not the recorded list.
    value = page.locator('[data-decision="model_variant"] [data-proposed-value]').inner_text()
    assert 'a more regularised variant, an Explainable Boosting Machine and gradient boosting' in value


# --- the journey bar ---------------------------------------------------------------------------

@pytest.mark.parametrize('lang', ['en', 'fr'])
def test_the_journey_labels_never_break_a_word_at_420_px(open_panel, views, lang):
    panel = open_case(open_panel, views, case='cv', lang=lang, width=420)
    page = panel.page
    broken = page.evaluate("""() => {
      const out = [];
      for (const s of document.querySelectorAll('.ht-journey [data-step-label]')) {
        const words = s.getAttribute('data-step-label').split(/\\s+/);
        const range = document.createRange();
        const text = [...s.childNodes].find(n => n.nodeType === 1 && !n.classList.contains('ov-mark')
          && !n.classList.contains('sr-only')) || s;
        range.selectNodeContents(text);
        const lines = new Set([...range.getClientRects()].map(r => Math.round(r.top)));
        if (lines.size > words.length) out.push(s.getAttribute('data-step-label'));
      }
      return out;
    }""")
    assert broken == []
    labels = page.locator('.ht-journey [data-step-label]').evaluate_all('ss => ss.map(s => s.dataset.stepLabel)')
    assert 'Conclusion' in labels
    assert ('Split' if lang == 'en' else 'Découpage') in labels
    # The plan's full title stays in the hover and for screen readers.
    conclusion = page.locator('.ht-journey [data-step="conclusion"]')
    assert 'Conclude proportionately' in conclusion.get_attribute('title')
    assert conclusion.locator('.sr-only').last.inner_text() != ''


# --- refusals in the panel language -----------------------------------------------------------

def test_a_refusal_explains_itself_in_french(open_panel, views):
    panel = open_case(open_panel, views, case='binary', lang='fr')
    page = panel.page
    page.locator('[role="tab"][data-tab="eda"]').click()
    refusal = {'code': 'stale_revision', 'reason': None, 'engineMessage': 'expected revision 3, current 4',
               'human': 'The study changed after the panel showed it. Nothing was recorded.',
               'details': ['Revision read by the panel: 3'],
               'humanFr': "L'étude a changé après l'affichage du panneau. Rien n'a été enregistré.",
               'detailsFr': ['Révision lue par le panneau : 3']}
    panel.send({'type': 'outcome', 'op': 'W4', 'kind': 'refused', 'target': 'eda.rate_by:job', 'refusal': refusal})
    box = page.locator('[data-outcome="refused"]').first
    assert box.locator('[data-human]').inner_text() == refusal['humanFr']
    assert 'Révision lue par le panneau : 3' in box.inner_text()
    assert box.locator('[data-engine-message]').inner_text() == refusal['engineMessage']


# --- screenshots of the new cards (for a person to look at) -----------------------------------

@pytest.mark.skipif(not SHOTS, reason='HYPOTRAIL_SHOTS is not set')
@pytest.mark.parametrize('lang', ['en', 'fr'])
@pytest.mark.parametrize('width', [420, 900])
@pytest.mark.parametrize('theme', ['light-modern', 'dark-modern', 'hc'])
def test_shots_of_the_new_cards(open_panel, views, theme, width, lang):
    panel, page = evidence(open_panel, views, lang=lang, width=width, theme=theme)
    Path(SHOTS).mkdir(parents=True, exist_ok=True)
    for sel, name in [('[data-ev="selection"]', 'selection'), ('[data-ev="families"]', 'families'),
                      ('[data-family-fit="ebm"]', 'ebm'), ('[data-family-fit="hgb"]', 'hgb')]:
        node = page.locator(sel).first
        node.scroll_into_view_if_needed()
        node.screenshot(path=str(Path(SHOTS) / f'{name}-{theme}-{width}-{lang}.png'))
