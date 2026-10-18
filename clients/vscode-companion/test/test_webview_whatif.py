"""Browser tests of the What if? view (scope S, simulated browser; WP-U3; COMPANION-ADVANCED
§6.5, WI-1 to WI-5, INV-6, INV-12, §13). The real document under the real CSP, offline, with
models produced by lib/models/{whatif,preview,draft}.js from the WP-0 fixtures, in both
fallback themes. The debounce and the single `preview policy` at a time are the
controller's (test/whatif.test.js); here the webview's messages are recorded. Not a VS
Code session.
"""
from __future__ import annotations

import copy
import re

import pytest

FORBIDDEN = re.compile(r'\b(threshold|capacity|precision|recall|positive class|policy|calling rule|selected)\b', re.I)
THEMES = ['light', 'dark']
WRITES = {'confirm', 'withdraw', 'propose', 'run_eda', 'render', 'acknowledge', 'export_handoff'}


@pytest.fixture(scope='module')
def binary(model):
    return model('summary', 'summary.binary')


@pytest.fixture(scope='module')
def regression(model):
    return model('summary', 'summary.regression')


def opened(open_panel, summary, scheme='light', task='binary', reviewer=False):
    panel = open_panel(scheme)
    panel.init(stage='v2', task=task, reviewer=reviewer)
    panel.snapshot(summary)
    panel.page.locator('[role="tab"][data-tab="whatif"]').click()
    return panel


def sent(panel, kind):
    return [m for m in panel.posted() if m['type'] == kind]


def banner_ok(page):
    banner = page.locator('#panel-whatif [data-experiment][role="note"]').first
    assert ('Experiment, not adopted. Nothing here changes the study. Computed from saved predictions; no model is '
            'refitted.') in banner.text_content()
    return True


@pytest.mark.parametrize('scheme', THEMES)
def test_wi1_the_banner_is_on_every_state(open_panel, model, payload, binary, scheme):
    panel = opened(open_panel, binary, scheme)
    page = panel.page
    assert banner_ok(page) and page.locator('[data-loading="whatif"]').count() == 1, 'loading'
    assert sent(panel, 'load')[-1] == {'v': 2, 'type': 'load', 'view': 'whatif'}
    panel.send({'type': 'load_error', 'view': 'whatif', 'message': 'unsupported_capability: evidence is reserved.', 'detail': ''})
    assert banner_ok(page) and page.locator('[data-whatif-error][role="alert"]').count() == 1, 'error'
    empty = copy.deepcopy(payload('evidence.binary'))
    empty['results'] = [r for r in empty['results'] if r['slot'] != 'policy.evaluation']
    panel.view_data('whatif', model('whatif', empty))
    assert banner_ok(page) and page.locator('[data-no-evaluation]').count() == 1, 'empty'
    panel.view_data('whatif', model('whatif', 'evidence.binary'))
    assert banner_ok(page) and page.locator('[data-slider]').count() == 1, 'populated'
    assert page.locator('[style]').count() == 0
    assert panel.clean(), (panel.requests, panel.errors, panel.csp, panel.violations())


@pytest.mark.parametrize('scheme', THEMES)
def test_sandbox_starts_at_the_proposed_rule_and_shows_the_experiment(open_panel, model, binary, scheme):
    panel = opened(open_panel, binary, scheme)
    page = panel.page
    panel.view_data('whatif', model('whatif', 'evidence.binary'))
    slider = page.locator('#ht-wi-slider')
    assert slider.get_attribute('data-slider') == 'capacity'
    assert (slider.get_attribute('min'), slider.get_attribute('max'), slider.input_value()) == ('1', '1357', '100')
    assert slider.get_attribute('aria-valuetext') == '100 rows'
    assert page.locator('[data-rule-label]').inner_text() == 'Act on the 100 highest-scored rows'
    assert page.locator('[data-rule-kind="capacity"]').get_attribute('aria-pressed') == 'true'
    share = page.locator('[data-share]')
    assert share.inner_text() == ('100 of the 1,357 validation rows = 7.4% of rows. '
                                  'Extrapolate this as a rate, not as a count.')
    assert share.locator('[data-literal="parameter"]').inner_text() == '7.4%'
    assert sent(panel, 'preview_policy') == [{'v': 2, 'type': 'preview_policy', 'rules': ['capacity:100'], 'intervals': True, 'seq': 1}]
    assert sent(panel, 'draft') == [{'v': 2, 'type': 'draft', 'decisionId': 'policy', 'value': 'capacity:100', 'revision': 26}]
    # Budget: showing the tab again asks nothing more at the same revision.
    page.locator('[role="tab"][data-tab="overview"]').click()
    page.locator('[role="tab"][data-tab="whatif"]').click()
    assert len(sent(panel, 'preview_policy')) == 1 and len(sent(panel, 'draft')) == 1
    assert len([m for m in sent(panel, 'load') if m['view'] == 'whatif']) == 1
    # The preview answer: bars, counts, the tie note, paired intervals.
    panel.send({'type': 'preview_policy_result', 'seq': 1, 'revision': 26, 'model': model('preview', 'preview.binary')})
    cmp = page.locator('.ht-wi-comparison')
    assert cmp.get_attribute('data-experiment') is not None
    values = cmp.locator('.ht-bars .ht-value').all_text_contents()
    assert values == ['36.0%', '11.5%', '23.1%', '7.4%']
    assert cmp.locator('.ht-wi-counts li').all_inner_texts() == [
        'logistic model: 100 selected, 36 true positives.', 'baseline: 100 selected, 11.5 true positives.']
    assert cmp.locator('[data-tie]').inner_text() == 'Ties at the cut counted pro rata.'
    assert cmp.locator('[data-delta-sentence="one_side"]').count() == 1
    assert cmp.locator('[data-bootstrap]').inner_text() == 'Paired bootstrap, 2,000 replicates, 95% level.'
    assert cmp.locator('data[data-result-id]').count() == 0, 'preview values are never cited as results'
    # Rules already evaluated: cited values of the current evaluation, with their status.
    rows = page.locator('[data-evaluated-rule]')
    assert rows.evaluate_all('xs => xs.map(x => [...x.cells].map(c => c.textContent))') == [
        ['capacity:100', '100', '36', '36.0%', '23.1%', 'proposed'],
        ['threshold:0.2', '115', '40', '34.8%', '25.6%', 'adopted']]
    assert rows.first.locator('data[data-result-id]').count() == 4
    assert page.locator('.ht-wi-evaluated th').all_inner_texts()[2] == 'Positives (y)'
    # The engine's draft: "Draft only", the texts verbatim, then Propose (identifiers only).
    draft = model('draft', 'proposal_draft.binary')
    panel.send({'type': 'draft_result', 'decisionId': 'policy', 'value': 'capacity:100', 'revision': 26, 'model': draft})
    card = page.locator('[data-draft="capacity:100"]')
    assert card.locator('.ht-wi-label').inner_text() == 'Draft only'
    assert card.locator('[data-draft-restatement]').text_content() == draft['restatement']
    button = page.locator('[data-write="propose"]')
    assert button.is_enabled() and button.inner_text() == 'Propose this rule'
    assert page.locator('#ht-wi-propose-hint').inner_text() == 'Creates a proposal only. You will confirm it in your own words in Decisions.'
    button.click()
    assert panel.posted()[-1] == {'v': 2, 'type': 'propose', 'decisionId': 'policy', 'value': 'capacity:100', 'revision': 26}
    assert page.locator('textarea').count() == 0, 'no words are typed to propose'
    assert panel.clean(), (panel.requests, panel.errors, panel.csp, panel.violations())


def test_wi2_wi3_slider_moves_send_previews_only_and_an_unevaluated_rule_cannot_be_proposed(open_panel, model, binary):
    panel = opened(open_panel, binary)
    page = panel.page
    panel.view_data('whatif', model('whatif', 'evidence.binary'))
    before = len(panel.posted())
    page.evaluate("""() => { const s = document.getElementById('ht-wi-slider');
      for (let i = 1; i <= 20; i += 1) { s.value = String(100 + i); s.dispatchEvent(new Event('input')); } }""")
    moves = panel.posted()[before:]
    assert [m['type'] for m in moves] == ['preview_policy'] * 20
    assert [m['rules'] for m in moves][-1] == ['capacity:120'] and not any(m['intervals'] for m in moves)
    assert [m['seq'] for m in moves] == list(range(2, 22))
    assert page.locator('#ht-wi-slider').count() == 1, 'the slider is never re-created while it moves'
    assert page.locator('[data-rule-label]').inner_text() == 'Act on the 120 highest-scored rows'
    # An answer for an older request is dropped.
    stale = model('preview', 'preview.binary')
    panel.send({'type': 'preview_policy_result', 'seq': 5, 'revision': 26, 'model': stale})
    assert page.locator('[data-preview-rule]').count() == 0
    # Release: intervals for the current rule; capacity:120 was never evaluated.
    page.evaluate("() => document.getElementById('ht-wi-slider').dispatchEvent(new Event('change'))")
    assert sent(panel, 'preview_policy')[-1] == {'v': 2, 'type': 'preview_policy', 'rules': ['capacity:120'], 'intervals': True, 'seq': 22}
    area = page.locator('[data-propose-area="capacity:120"]')
    assert area.locator('[data-not-evaluated]').inner_text() == ('This rule has not been evaluated by the engine yet, so it cannot be '
                                                                   'proposed here.')
    assert area.locator('[data-write="propose"]').count() == 0
    assert area.get_by_role('button', name='Ask the agent to evaluate capacity:120').count() == 1
    assert not [m for m in panel.posted()[before:] if m['type'] in WRITES or m['type'] == 'draft'], 'no write, no draft'
    # The number input is bound to the slider; Page Up moves by a tenth of the range.
    page.locator('#ht-wi-number').fill('300')
    page.locator('#ht-wi-number').dispatch_event('change')
    assert page.locator('#ht-wi-slider').input_value() == '300'
    page.locator('#ht-wi-slider').focus()
    page.keyboard.press('PageUp')
    assert page.locator('#ht-wi-slider').input_value() == '436'
    # Threshold: the evaluated threshold of the study, on a 0-1 scale.
    page.locator('[data-rule-kind="threshold"]').click()
    slider = page.locator('#ht-wi-slider')
    assert (slider.get_attribute('min'), slider.get_attribute('max'), slider.get_attribute('step'), slider.input_value()) == ('0', '1', '0.01', '0.2')
    assert page.locator('[data-rule-label]').inner_text() == 'Act on rows whose score is at least 0.2'
    assert sent(panel, 'preview_policy')[-1]['rules'] == ['threshold:0.2']
    assert page.locator('[data-share]').inner_text() == ''


def test_ask_the_agent_for_an_unevaluated_rule_uses_an_empty_question(open_panel, model, binary):
    panel = opened(open_panel, binary)
    page = panel.page
    panel.view_data('whatif', model('whatif', 'evidence.binary'))
    page.locator('#ht-wi-number').fill('150')
    page.locator('#ht-wi-number').dispatch_event('change')
    page.get_by_role('button', name='Ask the agent to evaluate capacity:150').click()
    dialog = page.locator('[role="dialog"]')
    assert not panel.errors, panel.errors
    assert dialog.locator('textarea').input_value() == ''
    assert dialog.get_by_role('button', name='Insert into the chat').count() == 0, 'chatInsert is off'
    dialog.get_by_role('button', name='Copy for the chat').click()
    assert panel.posted()[-1] == {'v': 2, 'type': 'ask_agent', 'about': {'kind': 'decision', 'id': 'policy'},
                                  'question': 'Could you evaluate the rule capacity:150, so that I can compare it with the rules already evaluated?',
                                  'mode': 'copy'}


def test_wi5_preview_values_are_never_shown_outside_the_tab(open_panel, model, payload, binary):
    panel = opened(open_panel, binary)
    page = panel.page
    panel.view_data('whatif', model('whatif', 'evidence.binary'))
    p = copy.deepcopy(payload('preview.binary'))
    p['evaluations']['capacity:100']['fit.logistic']['precision'] = 0.4321
    panel.send({'type': 'preview_policy_result', 'seq': 1, 'revision': 26, 'model': model('preview', p)})
    assert '43.2%' in page.locator('#panel-whatif').inner_text()
    panel.view_data('evidence', model('evidence', 'evidence.binary'))
    for tab in ['overview', 'eda', 'decisions', 'evidence']:
        page.locator(f'[role="tab"][data-tab="{tab}"]').click()
        assert '43.2%' not in page.locator('body').inner_text(), tab
        assert page.locator('[data-experiment]').count() == 0, tab


@pytest.mark.parametrize('scheme', THEMES)
def test_wi4_regression_renders_the_residual_explorer_without_rule_vocabulary(open_panel, model, regression, scheme):
    panel = opened(open_panel, regression, scheme, task='regression')
    page = panel.page
    panel.view_data('whatif', model('whatif', 'evidence.regression'))
    assert page.locator('#ht-wi-slider, [data-rule-kind], [data-evaluated-rules], .ht-wi-comparison').count() == 0, 'none of §6.5.1'
    assert sent(panel, 'preview_policy') == []
    assert page.locator('#ht-wi-fit-fit-linear').is_checked()
    assert page.locator('#ht-wi-err-h').inner_text() == 'Error on model_year ≥ 79 · 118 validation rows'
    errors = page.locator('[data-errors]')
    assert errors.locator('.ht-intervals .ht-value').all_text_contents() == [
        '6.31 mpg [5.58, 7.05]', '10.10 mpg [9.03, 11.18]', '-3.80 mpg [-4.34, -3.25]']
    assert errors.locator('[data-delta-sentence="one_side"]').count() == 1
    assert page.locator('[data-residuals="fit.linear"] p').last.inner_text().startswith('Residual = observed − predicted')
    bias = page.locator('[data-bias="model_year"]')
    assert bias.locator('[data-bar]').count() == 4
    assert bias.locator('[data-small="true"] rect[data-hatched="true"]').count() == 3
    assert bias.locator('.ht-value').all_text_contents() == ['+4.04 mpg', '+8.21 mpg', '+5.58 mpg', '+6.87 mpg']
    assert bias.locator('[data-bias-sign="positive"]').inner_text() == 'Every group is positive: the model predicts these rows too low on average.'
    assert bias.locator('[data-term="extrapolation"]').inner_text() == 'Extrapolation'
    assert bias.locator('[data-literal="axis"]').get_attribute('aria-hidden') == 'true'
    assert page.locator('[data-split-limits]').inner_text().endswith(
        '16 car_name values appear on both sides of the split (18 validation rows). These rows are not fully independent. '
        'Grouped splits are not supported in this version.')
    assert sent(panel, 'draft') == [{'v': 2, 'type': 'draft', 'decisionId': 'model_choice', 'value': 'fit.linear', 'revision': 22}]
    draft = model('draft', 'proposal_draft.regression')
    panel.send({'type': 'draft_result', 'decisionId': 'model_choice', 'value': 'fit.linear', 'revision': 22, 'model': draft})
    button = page.locator('[data-write="propose"]')
    assert button.inner_text() == 'Propose this model choice' and button.is_enabled()
    assert page.locator('[data-draft-restatement]').text_content() == draft['restatement']
    for toggle in page.locator('#panel-whatif .ht-figure button[aria-controls]').all():
        toggle.click()
    text = page.locator('body').inner_text()
    assert not FORBIDDEN.search(text), FORBIDDEN.search(text).group(0)
    # The other model: its residuals and its own draft.
    page.locator('#ht-wi-fit-fit-baseline').check()
    assert page.locator('[data-residuals="fit.baseline"]').count() == 1
    assert sent(panel, 'draft')[-1]['value'] == 'fit.baseline'
    assert button.is_disabled(), 'disabled until the engine says the new value is proposable'
    assert not [m for m in panel.posted() if m['type'] in WRITES], 'choosing a model writes nothing'
    assert page.locator('[style]').count() == 0
    assert panel.clean(), (panel.requests, panel.errors, panel.csp, panel.violations())


def test_reviewer_mode_has_no_propose_control_and_the_outcome_links_to_decisions(open_panel, model, binary):
    panel = opened(open_panel, binary, reviewer=True)
    page = panel.page
    panel.view_data('whatif', model('whatif', 'evidence.binary'))
    panel.send({'type': 'draft_result', 'decisionId': 'policy', 'value': 'capacity:100', 'revision': 26,
                'model': model('draft', 'proposal_draft.binary')})
    assert page.locator('[data-draft="capacity:100"]').count() == 1, 'the draft is readable'
    assert page.locator('[data-write]').count() == 0
    reviewer = panel
    panel = opened(open_panel, binary)
    page = panel.page
    panel.view_data('whatif', model('whatif', 'evidence.binary'))
    panel.send({'type': 'outcome', 'op': 'W3', 'kind': 'ok', 'target': 'policy', 'revision': 27,
                'recorded': {'proposalId': 'p_6', 'decisionId': 'policy', 'status': 'open', 'channel': 'webview'}})
    outcome = page.locator('[data-propose-outcome="ok"]')
    assert 'It is not a decision yet' in outcome.inner_text()
    assert page.locator('#outcome [data-outcome]').count() == 0, 'the view renders its own W3 outcome'
    outcome.get_by_role('button', name='Open Decisions').click()
    assert page.locator('[role="tab"][aria-selected="true"]').get_attribute('data-tab') == 'decisions'
    assert reviewer.clean() and panel.clean()
