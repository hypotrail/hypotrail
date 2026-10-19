"""Browser tests of the Evidence view (scope S, simulated browser; WP-U3; COMPANION-ADVANCED
§6.4, EV-1 to EV-6, INV-7, INV-12, §13). The real document under the real CSP, offline, with
models produced by lib/models/evidence.js from the WP-0 fixtures, in both fallback themes.
Not a VS Code session.
"""
from __future__ import annotations

import copy
import re

import pytest

LOGISTIC = 'd0af48b239d736c2c2b888841085499145e3fa4cfb56b13540251fa0af3883f5'
EVALUATION = 'ae80b53fe0f22e164e785d0939fef003c1b90c0482f5dd6f702ac28791426d02'
STALE = 'b7e3c1d09a4f5e6b8c2d1f0e3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b'
REGRESSION_EVAL = '142ac050de162499aa31cd03b837cd162f25d7cfef4d83b9b3d6e8d3cbef5301'
FORBIDDEN = re.compile(r'\b(threshold|capacity|precision|recall|positive class|policy|calling rule|selected)\b', re.I)
THEMES = ['light', 'dark']


@pytest.fixture(scope='module')
def binary(model):
    return model('summary', 'summary.binary')


@pytest.fixture(scope='module')
def regression(model):
    return model('summary', 'summary.regression')


def detail_payload(payload, name, rid, consumers=('report', 'notebook')):
    """An `evidence --result <rid>` payload built from a list fixture (CC §5 `detail`)."""
    p = copy.deepcopy(payload(name))
    r = next(x for x in p['results'] if x['result_id'] == rid)
    p['detail'] = {
        'result_id': rid, 'values': r['values'], 'params': r['params'],
        'inputs': {'results': dict(r['upstream'])}, 'code': {'fingerprint': 'f' * 64, 'modules': {'mlkit.study.metrics': {'sha256': 'a' * 64, 'matches': True}}},
        'environment': {}, 'blobs': [], 'exposure': None, 'consumers': list(consumers),
        'report_anchor': f'r-{rid}', 'notebook_hint': {'path': 'notebooks/study_generated.py', 'search': rid[:8]},
    }
    return p


def opened(open_panel, summary, scheme='light', task='binary'):
    panel = open_panel(scheme)
    panel.init(stage='v2', task=task)
    panel.snapshot(summary)
    panel.page.locator('[role="tab"][data-tab="evidence"]').click()
    return panel


def loads(panel):
    return [m for m in panel.posted() if m['type'] == 'load' and m['view'] == 'evidence']


def show(panel, evidence_model, rid=None):
    message = {'type': 'view_data', 'view': 'evidence', 'revision': evidence_model['revision'], 'model': evidence_model}
    if rid:
        message['resultId'] = rid
    panel.send(message)


@pytest.mark.parametrize('scheme', THEMES)
def test_ev1_registry_filters_and_stale_results_carry_no_figure(open_panel, model, binary, scheme):
    panel = opened(open_panel, binary, scheme)
    page = panel.page
    assert page.locator('#panel-evidence [data-loading="evidence"]').count() == 1
    assert loads(panel) == [{'v': 2, 'type': 'load', 'view': 'evidence'}]
    ev = model('evidence', 'evidence.binary')
    show(panel, ev)
    items = page.locator('[data-result-item]')
    current = [r['resultId'] for r in ev['results'] if r['promoted'] and r['current']]
    assert items.evaluate_all('xs => xs.map(x => x.dataset.resultItem)') == current
    assert page.locator('[data-result-item] [data-stale]').count() == 0
    assert page.locator('[data-result-item] data[data-result-id]').count() > 0, 'current headlines are cited'
    page.locator('#ht-ev-filter-stale').check()
    assert items.evaluate_all('xs => xs.map(x => x.dataset.resultItem)') == [STALE]
    stale = page.locator(f'[data-result-item="{STALE}"]')
    assert 'Not cited' in stale.inner_text() and 'stale' in stale.inner_text()
    assert stale.locator('data').count() == 0
    assert not re.search(r'\d', stale.inner_text()), 'no figure for a stale result (INV-7)'
    page.locator('#ht-ev-filter-all').check()
    assert items.count() == len(ev['results'])
    page.locator('[role="tab"][data-tab="overview"]').click()
    page.locator('[role="tab"][data-tab="evidence"]').click()
    assert panel.state()['evidenceFilter'] == 'all'
    assert len(loads(panel)) == 1, 'a filter change reads nothing'
    assert page.locator('[style]').count() == 0
    assert panel.clean(), (panel.requests, panel.errors, panel.csp, panel.violations())


@pytest.mark.parametrize('scheme', THEMES)
def test_detail_facts_lineage_ev6_and_ledger_ev2(open_panel, model, binary, scheme):
    panel = opened(open_panel, binary, scheme)
    page = panel.page
    show(panel, model('evidence', 'evidence.binary'))
    page.locator(f'[data-result-item="{LOGISTIC}"]').click()
    assert loads(panel)[-1] == {'v': 2, 'type': 'load', 'view': 'evidence', 'resultId': LOGISTIC}
    assert panel.state()['selectedResult'] == LOGISTIC
    assert 'Reading this result' in page.locator('.ht-ev-detail').inner_text()
    show(panel, model('evidence', 'evidence.binary.detail'), LOGISTIC)
    detail = page.locator(f'[data-detail="{LOGISTIC}"]')
    assert detail.locator('h2').inner_text() == 'fit.logistic'
    assert detail.locator('[data-currency]').inner_text() == 'd0af48b2… · current'
    facts = dict(zip(detail.locator('dt').all_inner_texts(), detail.locator('dd').all_inner_texts()))
    assert facts['Evaluated on'] == 'validation · 1,357 rows · 156 positive rows'
    assert facts['Result'].startswith('AUC 0.709')
    assert facts['Features'] == '12 · campaign, day, duration, month excluded'
    assert facts['Preprocessing'].endswith('fitted on training rows only')
    assert facts['Code'].endswith('· fingerprint matches')
    assert facts['Exposure'] == 'Model fitting · train · 3,164 rows'
    # Show in report (EV-4) and the notebook.
    detail.locator(f'[data-show-in-report="{LOGISTIC}"]').click()
    assert panel.posted()[-1] == {'v': 2, 'type': 'open_artifact', 'artifact': 'report', 'resultId': LOGISTIC}
    detail.locator('[data-show-in-notebook]').click()
    # WP-I (U3 request): the notebook opens at the line that names the result.
    assert panel.posted()[-1] == {'v': 2, 'type': 'open_artifact', 'artifact': 'notebook', 'resultId': LOGISTIC}
    assert 'look for d0af48b2' in detail.inner_text()
    # Lineage (EV-6) and the impact sentence.
    chain = page.locator(f'[data-chain="{LOGISTIC}"] [data-chain-node]')
    assert chain.evaluate_all('xs => xs.map(x => x.dataset.chainNode)') == [
        'dataset', 'split', 'feature_availability', 'fit.logistic', 'policy.evaluation', 'report', 'notebook']
    assert 'bank.csv · sha ok' in chain.nth(0).inner_text()
    assert 'your decision' in chain.nth(1).inner_text()
    assert page.locator('.ht-chain-arrow[aria-hidden="true"]').count() == 6
    impact = page.locator('[data-impact="feature_availability"]').inner_text()
    assert impact == ('Changing feature availability (a change that alters the set of usable features) would make '
                      'fit.logistic, policy.evaluation stale; fit.baseline would stay current.')
    page.get_by_role('button', name='Show as a table').click()
    tables = page.locator('#ht-ev-lineage-table table')
    assert tables.count() == 2 and tables.first.locator('tbody tr').count() == 7
    # Exposure ledger (EV-2).
    rows = page.locator('[data-ledger-row]')
    assert rows.evaluate_all('xs => xs.map(x => x.dataset.ledgerRow)') == [
        'structural_inspection:all', 'train_eda:train', 'train_fit:train', 'validation_model_evaluation:validation',
        'validation_policy_selection:validation']
    assert rows.evaluate_all('xs => xs.map(x => x.cells[0].firstChild.textContent)') == [
        'Structural inspection', 'EDA', 'Model fitting', 'Model evaluation', 'Rule selection']
    assert rows.evaluate_all('xs => xs.map(x => x.cells[2].textContent)') == ['4,521', '3,164', '3,164', '1,357', '1,357']
    assert page.locator('tr.ht-ledger-selection').get_attribute('data-ledger-row') == 'validation_policy_selection:validation'
    assert page.locator('[data-limit]').evaluate_all('xs => xs.map(x => x.dataset.limit)') == [
        'validation_is_not_independent', 'public_data_already_explored']
    assert page.locator('[data-split-unseen]').count() == 0
    assert page.locator('[style]').count() == 0
    assert panel.clean(), (panel.requests, panel.errors, panel.csp, panel.violations())


def test_ev4_show_in_report_is_disabled_without_an_anchor(open_panel, model, payload, binary):
    panel = opened(open_panel, binary)
    p = copy.deepcopy(payload('evidence.binary.detail'))
    p['detail']['report_anchor'] = None
    show(panel, model('evidence', 'evidence.binary'))
    panel.page.locator(f'[data-result-item="{LOGISTIC}"]').click()
    show(panel, model('evidence', p), LOGISTIC)
    button = panel.page.locator(f'[data-show-in-report="{LOGISTIC}"]')
    assert button.is_disabled()
    assert panel.page.locator('#ht-ev-not-in-report').inner_text() == 'This result is not cited in the current report'
    assert button.get_attribute('aria-describedby') == 'ht-ev-not-in-report'


@pytest.mark.parametrize('scheme', THEMES)
def test_ev5_intervals_have_a_values_table_and_the_chance_sentence(open_panel, model, payload, binary, scheme):
    p = detail_payload(payload, 'evidence.binary', EVALUATION)
    ev = next(r for r in p['results'] if r['result_id'] == EVALUATION)
    ev['values']['rules']['capacity:100']['deltas']['fit.logistic']['recall'] = {
        'point': 0.02, 'low': -0.03, 'high': 0.07, 'undefined_replicates': 0}
    p['detail']['values'] = ev['values']
    panel = opened(open_panel, binary, scheme)
    page = panel.page
    show(panel, model('evidence', 'evidence.binary'))
    page.locator(f'[data-result-item="{EVALUATION}"]').click()
    show(panel, model('evidence', p), EVALUATION)
    unc = page.locator('[data-uncertainty="policy"]')
    assert unc.locator('h4').all_inner_texts() == ['Rule capacity:100', 'Rule threshold:0.2']
    sentences = unc.locator('[data-delta-sentence]').evaluate_all('xs => xs.map(x => [x.dataset.deltaSentence, x.textContent])')
    assert sentences[0] == ['one_side', 'On these rows the interval stays on one side of zero.']
    assert sentences[1] == ['includes_zero', 'The interval includes zero: on these rows the difference could be chance.']
    assert sentences[2][0] == 'undefined'
    assert unc.locator('[data-bootstrap]').inner_text() == 'Paired bootstrap, 2,000 replicates, 95% level.'
    figure = unc.locator('.ht-figure').first
    assert figure.locator('svg[role="img"]').get_attribute('aria-label') == 'Precision with its interval (95%)'
    figure.get_by_role('button', name='Show values').click()
    cells = figure.locator('table tbody tr').first.locator('td').all_inner_texts()
    assert cells == ['logistic model', '36.0%', '[26.0%, 47.0%]']
    assert unc.locator('[data-zero]').count() >= 2, 'each difference has a 0 rule'
    assert panel.clean(), (panel.requests, panel.errors, panel.csp, panel.violations())


def test_ev3_navigation_selects_and_focuses_the_result(open_panel, model, binary):
    panel = opened(open_panel, binary)
    page = panel.page
    page.locator('[role="tab"][data-tab="overview"]').click()
    panel.send({'type': 'navigate', 'tab': 'evidence', 'kind': 'result', 'id': LOGISTIC})
    assert page.locator('[role="tab"][aria-selected="true"]').get_attribute('data-tab') == 'evidence'
    assert loads(panel)[-1] == {'v': 2, 'type': 'load', 'view': 'evidence', 'resultId': LOGISTIC}
    show(panel, model('evidence', 'evidence.binary.detail'), LOGISTIC)
    assert page.evaluate('document.activeElement.closest("[data-nav]").dataset.nav') == f'result:{LOGISTIC}'
    assert page.locator(f'[data-result-item="{LOGISTIC}"]').get_attribute('aria-pressed') == 'true'


def test_select_the_id_selects_the_full_id_and_never_writes_the_clipboard(open_panel, model, binary):
    # WP-I, decision CI.5: the panel writes the clipboard only through the agent bridge (§12).
    panel = opened(open_panel, binary)
    page = panel.page
    show(panel, model('evidence', 'evidence.binary'))
    page.locator(f'[data-result-item="{LOGISTIC}"]').click()
    show(panel, model('evidence', 'evidence.binary.detail'), LOGISTIC)
    page.get_by_role('button', name='Select the id').click()
    assert page.evaluate('() => String(window.getSelection())') == LOGISTIC
    assert page.locator('details.ht-ev-fullid').evaluate('d => d.open')
    assert page.locator('[data-select-note]').inner_text() == 'The id is selected: copy it with the keyboard.'
    assert panel.clean(), (panel.requests, panel.errors, panel.csp, panel.violations())


def test_an_unknown_result_shows_the_engine_refusal_and_returns_to_the_list(open_panel, model, binary):
    panel = opened(open_panel, binary)
    page = panel.page
    panel.send({'type': 'navigate', 'tab': 'evidence', 'kind': 'result', 'id': 'a' * 64})
    panel.send({'type': 'load_error', 'view': 'evidence', 'message': 'unknown_result: No result has this id.', 'detail': ''})
    error = page.locator('[data-evidence-error]')
    assert error.get_attribute('role') == 'alert'
    assert 'unknown_result: No result has this id.' in error.inner_text()
    error.get_by_role('button', name='Show the list of results').click()
    assert loads(panel)[-1] == {'v': 2, 'type': 'load', 'view': 'evidence'}


@pytest.mark.parametrize('scheme', THEMES)
def test_regression_evidence_holds_no_decision_rule_vocabulary(open_panel, model, payload, regression, scheme):
    panel = opened(open_panel, regression, scheme, task='regression')
    page = panel.page
    show(panel, model('evidence', 'evidence.regression'))
    page.locator('#ht-ev-filter-all').check()
    page.locator(f'[data-result-item="{REGRESSION_EVAL}"]').click()
    show(panel, model('evidence', detail_payload(payload, 'evidence.regression', REGRESSION_EVAL)), REGRESSION_EVAL)
    unc = page.locator('[data-uncertainty="regression"]')
    assert unc.locator('[data-metric]').evaluate_all('xs => xs.map(x => x.dataset.metric)') == ['mae', 'rmse']
    # WP-I: each metric is named by its glossary term, for the learning layer's hovers (§6.7).
    assert unc.locator('[data-metric] h4 [data-term]').evaluate_all('xs => xs.map(x => x.dataset.term)') == ['mae', 'rmse']
    assert unc.locator('[data-delta-sentence="one_side"]').count() == 2
    page.get_by_role('button', name='Show as a table').click()
    for button in page.locator('#panel-evidence .ht-figure button[aria-controls]').all():
        button.click()
    text = page.locator('body').inner_text()
    assert not FORBIDDEN.search(text), FORBIDDEN.search(text).group(0)
    assert page.locator('tr.ht-ledger-selection').get_attribute('data-ledger-row') == 'validation_model_evaluation:validation'
    assert page.locator('[data-ledger-row="validation_policy_selection:validation"]').count() == 0
    assert panel.clean(), (panel.requests, panel.errors, panel.csp, panel.violations())


def test_evidence_controls_are_named_and_reviewer_mode_keeps_the_reads(open_panel, model, binary):
    panel = open_panel()
    panel.init(stage='v2', reviewer=True)
    panel.snapshot(binary)
    page = panel.page
    page.locator('[role="tab"][data-tab="evidence"]').click()
    show(panel, model('evidence', 'evidence.binary'))
    page.locator(f'[data-result-item="{LOGISTIC}"]').click()
    show(panel, model('evidence', 'evidence.binary.detail'), LOGISTIC)
    assert page.locator('[data-write]').count() == 0
    assert page.locator('[data-show-in-report]').is_enabled(), 'reads and navigation stay in reviewer mode'
    unnamed = page.evaluate("""() => [...document.querySelectorAll('#panel-evidence button, #panel-evidence input')]
      .filter(b => !(b.textContent.trim() || b.getAttribute('aria-label') || (b.labels && b.labels.length))).length""")
    assert unnamed == 0
    assert page.locator('#panel-evidence [tabindex]:not([tabindex="0"]):not([tabindex="-1"])').count() == 0
