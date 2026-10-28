"""Browser tests of the evidence figures (scope S, simulated browser; WP-U3; COMPANION-ADVANCED
§A.4, EV-2 to EV-6, EV-15, INV-7, INV-12, §13), re-pointed at the one page (ADR 0004 d13): a
result's figure and "Where it comes from" are folds of its step in the path (PATH-5), the
exposure ledger is the ledger fold (PATH-1), a deep link is `navigate {anchor}` (NAV-1). The
Current/Stale filter of the tabbed panel (EV-1) is withdrawn with its test; a stale result is a
line of its step without figures (HON-4, `test_webview_eda.py`, `test_webview_page.py`). The
real document under the real CSP, offline, with models produced by lib/models/evidence.js from
the WP-0 fixtures, in both fallback themes. Not a VS Code session.
"""
from __future__ import annotations

import copy
import re

import pytest

from conftest import inline_styles_ok
from panel_cases import click_fold, open_result, show as open_folds, with_results

LOGISTIC = 'd0af48b239d736c2c2b888841085499145e3fa4cfb56b13540251fa0af3883f5'
EVALUATION = 'ae80b53fe0f22e164e785d0939fef003c1b90c0482f5dd6f702ac28791426d02'
REGRESSION_EVAL = '142ac050de162499aa31cd03b837cd162f25d7cfef4d83b9b3d6e8d3cbef5301'
FORBIDDEN = re.compile(r'\b(threshold|capacity|precision|recall|positive class|policy|calling rule|decision rule|selected)\b', re.I)
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


def opened(open_panel, summary, ev, scheme='light', task='binary', reviewer=False):
    """The page at v2 on a WP-0 summary completed with the evidence's result slots."""
    panel = open_panel(scheme)
    panel.init(stage='v2', task=task, reviewer=reviewer, panelContract=2)
    panel.snapshot(with_results(summary, ev['results']))
    return panel


def loads(panel):
    return [m for m in panel.posted() if m['type'] == 'load' and m['view'] == 'evidence']


def show(panel, evidence_model, rid=None):
    message = {'type': 'view_data', 'view': 'evidence', 'revision': evidence_model['revision'], 'model': evidence_model}
    if rid:
        message['resultId'] = rid
    panel.send(message)


@pytest.mark.parametrize('scheme', THEMES)
def test_detail_facts_lineage_ev6_and_ledger_ev2(open_panel, model, binary, scheme):
    ev = model('evidence', 'evidence.binary')
    panel = opened(open_panel, binary, ev, scheme)
    page = panel.page
    fig = open_result(panel, 'fit.logistic')
    assert fig.get_attribute('data-anchor') == 'path:models/fit.logistic'
    assert loads(panel)[-1] == {'v': 2, 'type': 'load', 'view': 'evidence', 'resultId': LOGISTIC}
    show(panel, ev)
    assert 'Reading this result' in fig.locator('.ht-ev-detail').inner_text()
    show(panel, model('evidence', 'evidence.binary.detail'), LOGISTIC)
    detail = page.locator(f'[data-detail="{LOGISTIC}"]')
    assert detail.locator('h4').first.inner_text() == 'fit.logistic'
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
    assert fig.locator('.ht-chain-arrow[aria-hidden="true"]').count() == 6
    impact = page.locator('[data-impact="feature_availability"]').inner_text()
    assert impact == ('Changing feature availability (a change that alters the set of usable features) would make '
                      'fit.logistic, policy.evaluation stale; fit.baseline would stay current.')
    fig.get_by_role('button', name='Show as a table').click()
    tables = page.locator(f'#ht-ev-lineage-table-{LOGISTIC[:8]} table')
    assert tables.count() == 2 and tables.first.locator('tbody tr').count() == 7
    # Exposure ledger (EV-2): the ledger fold of the path (PATH-1).
    click_fold(page, 'ledger')
    rows = page.locator('[data-ledger-row]')
    assert rows.evaluate_all('xs => xs.map(x => x.dataset.ledgerRow)') == [
        'structural_inspection:all', 'train_eda:train', 'train_fit:train', 'validation_model_evaluation:validation',
        'validation_policy_selection:validation']
    assert rows.evaluate_all('xs => xs.map(x => x.cells[0].firstChild.textContent)') == [
        'Structural inspection', 'EDA', 'Model fitting', 'Model evaluation', 'Rule selection']
    assert rows.evaluate_all('xs => xs.map(x => x.cells[2].textContent)') == ['4,521', '3,164', '3,164', '1,357', '1,357']
    assert page.locator('tr.ht-ledger-selection').get_attribute('data-ledger-row') == 'validation_policy_selection:validation'
    assert page.locator('[data-ledger] [data-limit]').evaluate_all('xs => xs.map(x => x.dataset.limit)') == [
        'validation_is_not_independent', 'public_data_already_explored']
    assert page.locator('[data-split-unseen]').count() == 0
    assert inline_styles_ok(page)
    assert panel.clean(), (panel.requests, panel.errors, panel.csp, panel.violations())


def test_ev4_show_in_report_is_disabled_without_an_anchor(open_panel, model, payload, binary):
    ev = model('evidence', 'evidence.binary')
    panel = opened(open_panel, binary, ev)
    p = copy.deepcopy(payload('evidence.binary.detail'))
    p['detail']['report_anchor'] = None
    open_result(panel, 'fit.logistic')
    show(panel, model('evidence', p), LOGISTIC)
    button = panel.page.locator(f'[data-show-in-report="{LOGISTIC}"]')
    assert button.is_disabled()
    note = f'ht-ev-not-in-report-{LOGISTIC[:8]}'
    assert panel.page.locator(f'#{note}').inner_text() == 'This result is not cited in the current report'
    assert button.get_attribute('aria-describedby') == note


@pytest.mark.parametrize('scheme', THEMES)
def test_ev5_intervals_have_a_values_table_and_the_chance_sentence(open_panel, model, payload, binary, scheme):
    p = detail_payload(payload, 'evidence.binary', EVALUATION)
    ev = next(r for r in p['results'] if r['result_id'] == EVALUATION)
    ev['values']['rules']['capacity:100']['deltas']['fit.logistic']['recall'] = {
        'point': 0.02, 'low': -0.03, 'high': 0.07, 'undefined_replicates': 0}
    p['detail']['values'] = ev['values']
    panel = opened(open_panel, binary, model('evidence', 'evidence.binary'), scheme)
    page = panel.page
    fig = open_result(panel, 'policy.evaluation')
    show(panel, model('evidence', p), EVALUATION)
    unc = fig.locator('[data-uncertainty="policy"]')
    # WP-E1 (R26): the rule in words, the token in the hover.
    assert unc.locator('h4').all_inner_texts() == ['Rule top 100 rows', 'Rule score at least 0.2']
    assert unc.locator('h4').evaluate_all('hs => hs.map(h => h.title)') == ['capacity:100', 'threshold:0.2']
    sentences = unc.locator('[data-delta-sentence]').evaluate_all('xs => xs.map(x => [x.dataset.deltaSentence, x.textContent])')
    assert sentences[0] == ['one_side', 'On these rows the interval stays on one side of zero.']
    assert sentences[1] == ['includes_zero', 'The interval includes zero: on these rows the difference could be chance.']
    assert sentences[2][0] == 'undefined'
    assert unc.locator('[data-bootstrap]').inner_text() == 'Paired bootstrap, 2,000 replicates, 95% level.'
    figure = unc.locator('.ht-figure').first
    assert figure.locator('[role="img"]').get_attribute('aria-label') == 'Precision with its interval (95%)'
    figure.get_by_role('button', name='Show values').click()
    cells = figure.locator('table tbody tr').first.locator('td').all_inner_texts()
    assert cells == ['logistic model', '36.0%', '[26.0%, 47.0%]']
    assert unc.locator('[data-zero]').count() >= 2, 'each difference has a 0 rule'
    assert panel.clean(), (panel.requests, panel.errors, panel.csp, panel.violations())


def test_ev3_navigation_opens_and_focuses_the_result_in_the_path(open_panel, model, binary):
    """EV-3 → NAV-1: a deep link to a result opens its step and its figure and focuses it; the
    detail is read for that result."""
    ev = model('evidence', 'evidence.binary')
    panel = opened(open_panel, binary, ev)
    page = panel.page
    page.evaluate("() => globalThis.Hypotrail.setFold('src-fit.logistic', true)")
    panel.send({'type': 'navigate', 'anchor': 'path:models/fit.logistic', 'kind': 'result', 'id': LOGISTIC})
    assert loads(panel)[-1] == {'v': 2, 'type': 'load', 'view': 'evidence', 'resultId': LOGISTIC}
    show(panel, model('evidence', 'evidence.binary.detail'), LOGISTIC)
    assert page.evaluate('document.activeElement.closest("[data-anchor]").dataset.anchor') == 'path:models/fit.logistic'
    # R50 (lot P): the figure is inline in its opened step (no fold of its own).
    assert page.locator('[data-anchor="path:models/fit.logistic"]').is_visible()
    assert page.locator(f'[data-detail="{LOGISTIC}"]').count() == 1


def test_select_the_id_selects_the_full_id_and_never_writes_the_clipboard(open_panel, model, binary):
    # WP-I, decision CI.5: the panel writes the clipboard only through the agent bridge (§12).
    panel = opened(open_panel, binary, model('evidence', 'evidence.binary'))
    page = panel.page
    fig = open_result(panel, 'fit.logistic')
    show(panel, model('evidence', 'evidence.binary.detail'), LOGISTIC)
    fig.get_by_role('button', name='Select the id').click()
    assert page.evaluate('() => String(window.getSelection())') == LOGISTIC
    assert fig.locator('details.ht-ev-fullid').evaluate('d => d.open')
    assert fig.locator('[data-select-note]').inner_text() == 'The id is highlighted: copy it with the keyboard.'
    assert panel.clean(), (panel.requests, panel.errors, panel.csp, panel.violations())


def test_an_unknown_result_shows_the_engine_refusal_in_place(open_panel, model, binary):
    """A deep link to a result the study does not hold (NAV-2): the path opens, the engine's
    refusal is shown where the detail would be, as an alert."""
    panel = opened(open_panel, binary, model('evidence', 'evidence.binary'))
    page = panel.page
    fig = open_result(panel, 'fit.logistic')
    panel.send({'type': 'load_error', 'view': 'evidence', 'message': 'unknown_result: No result has this id.', 'detail': ''})
    error = fig.locator('[data-evidence-error]').first
    assert error.get_attribute('role') == 'alert'
    assert 'unknown_result: No result has this id.' in error.inner_text()


@pytest.mark.parametrize('scheme', THEMES)
def test_regression_evidence_holds_no_decision_rule_vocabulary(open_panel, model, payload, regression, scheme):
    ev = model('evidence', 'evidence.regression')
    # The model choice made: its evaluation is a figure of its step in the path (PATH-5); while
    # the choice waits, Now shows its one figure (NOW-1).
    decided = copy.deepcopy(regression)
    for step in decided['plan']:
        if step['id'] == 'model_choice':
            step['status'] = 'done'
    panel = opened(open_panel, decided, ev, scheme, task='regression')
    page = panel.page
    fig = open_result(panel, 'evaluate.regression')
    show(panel, model('evidence', detail_payload(payload, 'evidence.regression', REGRESSION_EVAL)), REGRESSION_EVAL)
    unc = fig.locator('[data-uncertainty="regression"]')
    assert unc.locator('[data-metric]').evaluate_all('xs => xs.map(x => x.dataset.metric)') == ['mae', 'rmse']
    # WP-I: each metric is named by its glossary term; below v3 the term is marked as text
    # (`data-term-text`), a notion button from v3 (NOT-1).
    assert unc.locator('[data-metric] h4 [data-term-text]').evaluate_all('xs => xs.map(x => x.dataset.termText)') == ['mae', 'rmse']
    assert unc.locator('[data-delta-sentence="one_side"]').count() == 2
    fig.get_by_role('button', name='Show as a table').click()
    for button in fig.locator('.ht-figure button[aria-controls]').all():
        button.click()
    click_fold(page, 'ledger')
    text = page.locator('body').inner_text()
    assert not FORBIDDEN.search(text), FORBIDDEN.search(text).group(0)
    assert page.locator('tr.ht-ledger-selection').get_attribute('data-ledger-row') == 'validation_model_evaluation:validation'
    assert page.locator('[data-ledger-row="validation_policy_selection:validation"]').count() == 0
    assert panel.clean(), (panel.requests, panel.errors, panel.csp, panel.violations())


def test_evidence_controls_are_named_and_reviewer_mode_keeps_the_reads(open_panel, model, binary):
    ev = model('evidence', 'evidence.binary')
    panel = opened(open_panel, binary, ev, reviewer=True)
    page = panel.page
    open_folds(panel, evidence=ev)
    fig = open_result(panel, 'fit.logistic')
    show(panel, model('evidence', 'evidence.binary.detail'), LOGISTIC)
    assert page.locator('[data-write]').count() == 0
    assert fig.locator('[data-show-in-report]').is_enabled(), 'reads and navigation stay in reviewer mode'
    # A11Y-1: every control has an accessible name, and no positive tabindex.
    unnamed = page.evaluate("""() => [...document.querySelectorAll('#main button, #main input')]
      .filter(b => !(b.textContent.trim() || b.getAttribute('aria-label') || (b.labels && b.labels.length))).length""")
    assert unnamed == 0
    assert page.locator('#main [tabindex]:not([tabindex="0"]):not([tabindex="-1"])').count() == 0


# --- EV-15 (owner session 2026-10-26, R11): one card per compared variant ---------------------

def _families(open_panel, model, payload, lang='en', raw=None):
    from panel_cases import load_views, open_all, open_case
    views = load_views(model, payload)
    if raw is not None:
        views['evidence.families'] = model('evidence', raw)
    panel = open_case(open_panel, views, case='families', lang=lang)
    open_all(panel, views, 'families')
    return panel, views['evidence.families']


@pytest.mark.parametrize('lang', ['en', 'fr'])
def test_ev15_every_compared_variant_has_its_own_card(open_panel, model, payload, lang):
    """R11: the penalised variant, the EBM and the boosting each have a card, in slot order,
    after the selection card: what it changes, its figures over the folds beside the
    candidate's (cited to the evaluation), and its own analysis (coefficients cited to the
    development diagnostics, the value chosen in each fold, the family's own diagnostics)."""
    panel, ev = _families(open_panel, model, payload, lang=lang)
    page = panel.page
    cards = page.locator('[data-variant-card]')
    assert cards.evaluate_all('cs => cs.map(c => c.dataset.variantCard)') == \
        ['fit.variant', 'fit.variant:2', 'fit.variant:3']
    # Next to the selection card, in the order of the cards.
    order = page.locator('[data-ev="selection"], [data-variant-card]').evaluate_all(
        'cs => cs.map(c => c.dataset.ev)')
    assert order == ['selection', 'variant-fit', 'family-fit', 'family-fit']
    selection = ev['selection']['resultId']
    for i, v in enumerate(ev['variantCards']):
        card = cards.nth(i)
        assert 'fit.variant · ' in card.locator('.ht-src').inner_text()
        table = card.locator(f'[data-variant-comparison="{v["slot"]}"]')
        assert table.locator('tbody tr').count() == 2           # the candidate, then the variant
        cited = table.locator('data[data-result-id]').evaluate_all(
            'ds => ds.map(d => [d.dataset.resultId, d.dataset.path])')
        assert all(rid == selection for rid, _ in cited)
        cmp = v['comparison']
        assert [p for _, p in cited] == [cmp['candidate']['mean']['path'], cmp['variant']['mean']['path'],
                                         cmp['difference']['mean']['path']]
        assert card.locator('[data-variant-noise]').count() == 1
    reg = page.locator('[data-variant-card="fit.variant"]')
    assert reg.get_attribute('data-ev') == 'variant-fit'
    coef = reg.locator('[data-coefficients]')
    assert coef.count() == 1
    diag = next(d for d in ev['diagnostics'] if d['slot'] == 'diag.binary')['resultId']
    assert coef.locator('data[data-result-id]').first.get_attribute('data-result-id') == diag
    assert coef.locator('data[data-result-id]').first.get_attribute('data-path') == \
        'models.[fit.variant].coefficients.terms.0.value'
    ebm = page.locator('[data-variant-card="fit.variant:2"]')
    assert ebm.get_attribute('data-family-fit') == 'ebm'
    tuning = ebm.locator('[data-variant-tuning]')
    assert tuning.get_attribute('data-variant-tuning') == '5'
    assert tuning.locator('data[data-path="tuning.per_fold.0.value"]').get_attribute('data-result-id') == \
        ev['variantCards'][1]['resultId']
    assert ebm.locator('[data-family-importance]').count() == 1
    if lang == 'en':
        assert reg.locator('h3').inner_text() == 'What does this penalty change in the model?'
        assert reg.locator('[data-variant-changes]').inner_text() == \
            'The candidate with more regularisation: a stronger penalty on its coefficients.'
        assert ebm.locator('h3').inner_text() == \
            'Which terms carry the explainable boosting model, and with what shape?'
        assert ebm.locator('[data-variant-changes]').inner_text() == 'Another model family: Explainable boosting.'
    else:
        assert reg.locator('h3').inner_text() == 'Que change cette pénalité dans le modèle\u202f?'
        assert "Valeur du nombre de termes d'interaction choisie dans chaque pli externe" in tuning.inner_text()
    assert panel.clean(), (panel.requests, panel.errors, panel.csp, panel.violations())


def test_ev15_a_tuned_variant_and_a_variant_the_diagnostics_miss(open_panel, model, payload):
    """A tuned variant shows the penalty chosen in each outer fold (cited to its fit); a
    variant the current development diagnostics do not cover says they are not run yet."""
    import copy
    raw = copy.deepcopy(payload('captured/evidence.binary.families'))
    find = lambda slot: next(r for r in raw['results'] if r['slot'] == slot and r['promoted'] and r['current'])
    first = find('fit.variant')
    first['values']['variant'] = {'kind': 'tuned'}
    first['values']['tuning'] = {'parameter': 'C', 'values': [0.01, 0.1, 1], 'inner_folds': 3,
                                 'metric': 'roc_auc', 'meaning': 'inverse penalty strength',
                                 'per_fold': [{'fold': k, 'value': 0.1 if k % 2 else 1} for k in range(1, 6)],
                                 'development': {'value': 0.1}}
    second = find('fit.variant:2')
    second['values']['variant'] = {'kind': 'drop_group', 'group': 'campaign'}
    del second['values']['family_diagnostics']
    del find('diag.binary')['values']['models']['fit.variant:2']
    panel, ev = _families(open_panel, model, payload, raw=raw)
    page = panel.page
    tuned = page.locator('[data-variant-card="fit.variant"]')
    assert tuned.get_attribute('data-variant-kind') == 'tuned'
    assert tuned.locator('h3').inner_text() == 'Which penalty does each fold choose, and with what result?'
    assert tuned.locator('[data-variant-tuning] tbody tr').count() == 5
    assert 'Value of the inverse penalty strength chosen in each outer fold' in tuned.inner_text()
    dev = tuned.locator('[data-variant-tuning-development] data[data-result-id]')
    assert dev.get_attribute('data-path') == 'tuning.development.value'
    assert tuned.locator('[data-coefficients]').count() == 1
    drop = page.locator('[data-variant-card="fit.variant:2"]')
    assert drop.get_attribute('data-ev') == 'variant-fit'
    assert drop.locator('[data-variant-changes]').inner_text() == \
        'The candidate without the group of variables "campaign".'
    assert drop.locator('[data-variant-diagnostics="not_run"]').inner_text().startswith(
        'Diagnostics not yet run for this variant')
    assert drop.locator('[data-coefficients]').count() == 0
    assert page.locator('[data-variant-card]').count() == 3
    assert panel.clean(), (panel.requests, panel.errors, panel.csp, panel.violations())
