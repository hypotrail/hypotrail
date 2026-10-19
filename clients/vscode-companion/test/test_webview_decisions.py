"""Browser tests of the Decisions view (scope S, simulated browser; WP-U2, COMPANION-ADVANCED
§6.2, INV-4, INV-5, INV-8, INV-9, INV-12, §12, §13).

The real document is loaded offline in headless Chromium (``conftest.py``); models come from
the real ``lib/models/*.js`` functions on the WP-0 fixtures, and messages the extension
would send are posted to the page. Each test also asserts that the page made no remote
request and reported no CSP violation. This is not a VS Code session.
"""
from __future__ import annotations

import copy
import json
import re

import pytest

FORBIDDEN = re.compile(r'\b(threshold|capacity|precision|recall|positive class|policy|calling rule|selected)\b', re.I)
THEMES = ['light', 'dark']
RESTATEMENT = 'Call the 100 clients with the highest scores.'
WORDS = 'Yes: we can make 100 calls per wave, so call the 100 best-scored clients.'


@pytest.fixture(scope='module')
def binary(model):
    return model('summary', 'summary.binary')


@pytest.fixture(scope='module')
def regression(model):
    return model('summary', 'summary.regression')


@pytest.fixture(scope='module')
def effects(model):
    return lambda name: model('effects', name)


@pytest.fixture(scope='module')
def decisions(model):
    return lambda name: model('decisions', name)


@pytest.fixture(scope='module')
def describe(node):
    def run(name_or_payload):
        from conftest import read_payload
        data = read_payload(name_or_payload) if isinstance(name_or_payload, str) else name_or_payload
        return json.loads(node("let s='';process.stdin.on('data',d=>s+=d).on('end',()=>process.stdout.write("
                               "JSON.stringify(require('./lib/refusals').describe(JSON.parse(s)))))", json.dumps(data)))
    return run


def opened(open_panel, summary, stage='v1', theme='light', reviewer=False, task=None):
    panel = open_panel(color_scheme=theme)
    panel.init(stage=stage, reviewer=reviewer, task=task)
    panel.snapshot(summary)
    tab = panel.page.locator('[role="tab"][data-tab="decisions"]')
    if tab.count():
        tab.click()
    return panel


def card(panel, pid='p_5'):
    return panel.page.locator(f'[data-proposal-card="{pid}"]')


def area(panel, pid='p_5'):
    return panel.page.locator(f'#words-{pid}')


def effects_message(model, revision=None):
    return {'type': 'effects', 'proposalId': model['proposalId'], 'revision': revision or model['revision'], 'model': model}


def textarea_values(page):
    return page.locator('textarea').evaluate_all('ts => ts.map(t => t.value)')


def wait_until(page, expression, timeout_ms=3000):
    """Poll ``expression`` (the CSP forbids the string eval of ``wait_for_function``)."""
    for _ in range(timeout_ms // 50):
        if page.evaluate(expression):
            return
        page.wait_for_timeout(50)
    raise AssertionError(f'timed out waiting for {expression}')


def assert_clean(panel):
    assert panel.clean(), (panel.requests, panel.errors, panel.csp, panel.violations())
    assert panel.page.locator('[style]').count() == 0, 'no inline style attribute (CSP)'


# --- DC-1, DC-2, DC-5: the answer is the junior's own -------------------------------------------

@pytest.mark.parametrize('theme', THEMES)
def test_dc1_dc5_textarea_starts_empty_confirm_needs_typed_words(open_panel, binary, effects, theme):
    panel = opened(open_panel, binary, theme=theme)
    page = panel.page
    c = card(panel)
    assert c.locator('[data-restatement="p_5"]').inner_text() == RESTATEMENT
    words = page.get_by_label('Your answer to this proposal, in your own words')
    assert words.input_value() == ''
    confirm = c.locator('button[data-action="confirm"]')
    assert confirm.inner_text() == 'Confirm in my words'
    assert confirm.is_disabled()
    # DC-5: no preview text ever goes into the textarea.
    panel.send(effects_message(effects('preview_effects.binary.reconfirm')))
    panel.snapshot(binary)
    assert textarea_values(page) == ['']
    assert page.locator('textarea[placeholder]').count() == 0
    assert RESTATEMENT not in page.locator('textarea').evaluate('t => t.value + t.defaultValue + t.textContent')
    assert confirm.is_disabled()
    words.fill('  \n ')
    assert confirm.is_disabled()
    words.fill(WORDS)
    assert confirm.is_enabled()
    confirm.click()
    assert panel.posted()[-1] == {'v': 2, 'type': 'confirm', 'proposalId': 'p_5', 'words': WORDS, 'revision': 26}
    hint = page.locator('#hint-p_5').inner_text()
    assert '"ok" or "yes" alone is not enough' in hint and 'Nothing is filled in for you' in hint
    assert words.get_attribute('aria-describedby') == 'hint-p_5'
    assert_clean(panel)


def test_dc1_words_stay_on_their_card_and_are_dropped_after_a_confirmation(open_panel, binary, model, payload):
    raw = copy.deepcopy(payload('summary.binary'))
    raw['open_proposals'].append({'proposal_id': 'p_7', 'decision_id': 'conclusion', 'value': 'adopt_policy',
                                  'restatement': 'You adopt the rule for the next wave.', 'revision': 26, 'origin': None})
    two = model('summary', raw)
    panel = opened(open_panel, two)
    page = panel.page
    area(panel, 'p_5').fill(WORDS)
    assert area(panel, 'p_7').input_value() == '', 'the words of one card never appear in another'
    panel.snapshot(two)
    assert area(panel, 'p_5').input_value() == WORDS, 'a refresh keeps the junior\'s own draft'
    assert area(panel, 'p_7').input_value() == ''
    # A successful confirmation: the card is gone, the outcome says what was recorded.
    panel.send({'type': 'outcome', 'op': 'W1', 'kind': 'ok', 'target': 'p_5', 'exitCode': 0, 'revision': 27,
                'recorded': {'userWords': WORDS, 'channel': 'webview', 'decisionId': 'policy', 'proposalId': 'p_5'},
                'artifacts': [{'name': 'report', 'status': 'ok', 'message': 'The report is up to date.'}]})
    after = copy.deepcopy(raw)
    after['revision'] = 27
    after['open_proposals'] = [after['open_proposals'][1]]
    panel.snapshot(model('summary', after))
    assert card(panel, 'p_5').count() == 0
    last = page.locator('[data-last-outcome="p_5"]')
    assert last.locator('[data-outcome="ok"]').count() == 1
    assert WORDS in last.inner_text()
    assert last.locator('.title').inner_text() == 'Confirmed the calling rule in your words (channel webview).'
    assert last.locator('[data-recorded-words]').inner_text() == f'Recorded: “{WORDS}”'
    assert 'The report is up to date.' in last.inner_text()
    assert textarea_values(page) == ['']
    assert 'p_5' not in json.dumps((panel.state() or {}).get('drafts', {}))
    assert_clean(panel)


def test_dc2_confirm_is_disabled_while_busy_and_when_the_engine_would_refuse(open_panel, binary, effects):
    panel = opened(open_panel, binary)
    page = panel.page
    c = card(panel)
    area(panel).fill(WORDS)
    confirm = c.locator('button[data-action="confirm"]')
    assert confirm.is_enabled()
    panel.send({'type': 'busy', 'busy': True, 'op': 'W1', 'target': 'p_5'})
    assert confirm.is_disabled() and c.locator('button[data-action="withdraw"]').is_disabled()
    assert confirm.get_attribute('aria-busy') == 'true' and confirm.inner_text() == 'Working...'
    panel.send({'type': 'busy', 'busy': False, 'op': 'W1', 'target': 'p_5'})
    assert confirm.is_enabled()
    panel.send(effects_message(effects('preview_effects.binary.blocked')))
    blocked = c.locator('[data-blocked="p_5"]')
    assert blocked.get_attribute('role') == 'status'
    assert blocked.inner_text().startswith('The engine will refuse a confirmation now:')
    assert blocked.locator('[data-blocked-code="decision_on_hold"] code').inner_text() == 'decision_on_hold'
    assert blocked.locator('[data-engine-message]').inner_text() == \
        "This decision is on hold in the junior's own words; resolve the note first."
    assert confirm.is_disabled()
    assert confirm.get_attribute('aria-describedby') == blocked.get_attribute('id')
    assert area(panel).input_value() == WORDS, 'the junior keeps their text'
    confirm.click(force=True)
    assert not any(m['type'] == 'confirm' for m in panel.posted())
    assert_clean(panel)


# --- DC-4: If you confirm ----------------------------------------------------------------------

def test_preview_is_requested_for_a_visible_card_and_again_when_the_revision_moves(open_panel, binary, effects):
    panel = opened(open_panel, binary)
    page = panel.page
    wait_until(page, "window.__posted.some(m => m.type === 'preview_effects')")
    asks = [m for m in panel.posted() if m['type'] == 'preview_effects']
    assert asks == [{'v': 2, 'type': 'preview_effects', 'proposalId': 'p_5', 'revision': 26}]
    assert card(panel).locator('[data-effects-loading]').get_attribute('aria-busy') == 'true'
    assert {'v': 2, 'type': 'load', 'view': 'decisions'} in panel.posted()
    panel.send(effects_message(effects('preview_effects.binary')))
    panel.snapshot({**binary, 'revision': 27})
    wait_until(page, "window.__posted.filter(m => m.type === 'preview_effects').length === 2")
    assert [m['revision'] for m in panel.posted() if m['type'] == 'preview_effects'] == [26, 27]
    assert_clean(panel)


def test_previews_are_read_for_visible_cards_at_most_three_at_once(open_panel, model, payload, effects):
    raw = copy.deepcopy(payload('summary.binary'))
    raw['open_proposals'] = [{'proposal_id': f'p_{n}', 'decision_id': 'conclusion', 'value': 'adopt_policy',
                              'restatement': f'Restatement {n}.', 'revision': 26, 'origin': None} for n in range(10, 16)]
    panel = opened(open_panel, model('summary', raw))
    page = panel.page
    page.set_viewport_size({'width': 1280, 'height': 4000})
    page.evaluate('() => window.scrollTo(0, 0)')
    asked = lambda: [m['proposalId'] for m in panel.posted() if m['type'] == 'preview_effects']  # noqa: E731
    wait_until(page, "window.__posted.filter(m => m.type === 'preview_effects').length === 3")
    page.wait_for_timeout(200)
    assert len(asked()) == 3, 'at most three previews are read at once'
    base = effects('preview_effects.binary.first')
    for pid in list(asked()):
        panel.send(effects_message({**base, 'proposalId': pid}, revision=26))
    wait_until(page, "window.__posted.filter(m => m.type === 'preview_effects').length === 6")
    assert sorted(asked()) == sorted(f'p_{n}' for n in range(10, 16))
    assert len(set(asked())) == 6, 'each card is read once per revision'
    assert_clean(panel)


@pytest.mark.parametrize('theme', THEMES)
def test_dc4_kept_fits_the_conclusion_to_confirm_again_and_regenerated(open_panel, binary, effects, theme):
    panel = opened(open_panel, binary, theme=theme)
    panel.send(effects_message(effects('preview_effects.binary.reconfirm')))
    section = card(panel).locator('[data-effects="p_5"]')
    assert section.locator('h4').inner_text() == 'If you confirm'
    boxes = section.locator('[data-effects-box]')
    assert boxes.evaluate_all('bs => bs.map(b => b.dataset.effectsBox)') == ['kept', 'reconfirm', 'regenerated']
    assert section.locator('[data-effects-box="kept"]').inner_text() == 'Kept\nboth models and their predictions, nothing refitted'
    assert section.locator('[data-effects-box="reconfirm"]').inner_text() == 'To confirm again\nthe conclusion'
    assert section.locator('[data-effects-box="regenerated"]').inner_text() == 'Regenerated\nreport and notebook'
    # WP-A5: the engine's note on the preview is kept, verbatim, under Details.
    assert section.locator('details [data-effects-note]').text_content() == \
        'Preview of a confirmation: nothing was recorded. The engine still checks the words when you confirm.'
    assert section.locator('[data-effects-first]').count() == 0
    panel.snapshot({**binary, 'revision': 27})
    assert section.locator('[data-effects-updating]').inner_text() == 'Updating...'
    assert_clean(panel)


def test_dc4_first_confirmation_and_a_split_change(open_panel, binary, effects, model, payload):
    raw = copy.deepcopy(payload('summary.binary'))
    raw['open_proposals'] = [
        {'proposal_id': 'p_1', 'decision_id': 'prediction_time', 'revision': 2, 'origin': None,
         'value': 'before the first contact of the campaign, from the client file', 'restatement': 'You score before the call.'},
        {'proposal_id': 'p_8', 'decision_id': 'split', 'revision': 26, 'origin': None,
         'value': {'method': 'stratified_random', 'seed': 7, 'validation_fraction': 0.3}, 'restatement': 'A new seed.'}]
    panel = opened(open_panel, model('summary', raw))
    panel.send(effects_message(effects('preview_effects.binary.first'), revision=26))
    panel.send(effects_message(effects('preview_effects.binary.split')))
    first = card(panel, 'p_1').locator('[data-effects]')
    assert first.locator('[data-effects-first]').inner_text() == 'Nothing recorded so far is invalidated.'
    assert first.locator('[data-effects-box="kept"]').inner_text() == 'Kept\nnothing'
    assert first.locator('[data-effects-box="reconfirm"]').inner_text() == 'To confirm again\nnothing'
    split = card(panel, 'p_8').locator('[data-effects]')
    stale = split.locator('[data-effects-box="stale"]').inner_text()
    assert 'the logistic model' in stale and 'fit.logistic' not in stale, 'slots in words (WP-A5)'
    assert split.locator('[data-effects-box="stale"] .dc-box-title').inner_text() == 'Becomes stale'
    assert split.locator('[data-effects-box="reconfirm"]').inner_text() == 'To confirm again\nthe calling rule'
    assert 'fit.baseline' not in split.locator('[data-effects-box="kept"]').inner_text()
    assert split.locator('.dc-notes').inner_text() == 'Changing the split does not make explored rows unseen.'
    assert_clean(panel)


def test_an_unavailable_preview_says_so_and_does_not_block(open_panel, binary):
    panel = opened(open_panel, binary)
    message = ('The engine could not preview this confirmation. preview effects is reserved for the advanced '
               'companion and is not implemented in this version. Nothing was read or written.')
    panel.send({'type': 'effects', 'proposalId': 'p_5', 'revision': 26, 'model': {
        'available': False, 'proposalId': 'p_5', 'message': message, 'code': 'unsupported_capability', 'reason': 'not_implemented'}})
    missing = card(panel).locator('[data-effects-missing]')
    assert missing.inner_text() == f'The impact preview is not available. {message}'
    area(panel).fill(WORDS)
    assert card(panel).locator('button[data-action="confirm"]').is_enabled()
    assert_clean(panel)


# --- the card head, holds, origin (DC-6), value groups --------------------------------------------

def test_card_head_pause_origin_holds_and_resolved_conditions(open_panel, binary, model, payload):
    panel = opened(open_panel, binary)
    c = card(panel)
    assert c.locator('[data-pause]').inner_text() == 'Pause 3 · business trade-off'
    assert c.locator('h3').first.inner_text() == 'Choose a decision policy'
    assert c.locator('[data-origin]').inner_text() == 'proposal by the agent · not a decision yet'
    # WP-A5: the proposal id and the recorded value are in the hover and under Details.
    made = c.locator('[data-made-at="p_5"]')
    assert made.inner_text() == 'Proposed at revision 26' and made.get_attribute('title') == 'p_5'
    value = c.locator('[data-proposed-value="p_5"]')
    assert value.inner_text() == 'In short: Call the top 100 by score'
    assert value.locator('[data-value-raw]').get_attribute('data-value-raw') == 'capacity:100'
    assert c.locator('[data-value-details="p_5"] code').text_content() == 'capacity:100'
    assert 'p_5' not in c.locator('h3, [data-proposed-value], [data-made-at]').all_inner_texts().__str__()
    assert c.locator('[data-resolved-note="n_1"]').inner_text() == \
        ('Your condition, resolved: “don\'t adopt anything until I bring my manager\'s figure” → '
         '“my manager says the team can make 100 calls per wave”')
    assert c.locator('[data-hold]').count() == 0
    raw = copy.deepcopy(payload('summary.binary'))
    raw['notes'][0].update({'status': 'open', 'resolution_words': None})
    held = model('summary', raw)
    panel.snapshot(held)
    hold = card(panel).locator('[data-hold="n_1"]')
    assert hold.inner_text() == ('On hold in your words: “don\'t adopt anything until I bring my manager\'s figure”. '
                                 'The engine refuses a confirmation of this decision until you resolve the hold in the chat.')
    assert_clean(panel)


def test_dc6_a_proposal_from_this_panel_and_the_regression_pause(open_panel, regression):
    panel = opened(open_panel, regression, task='regression')
    c = card(panel, 'p_4')
    assert c.locator('[data-origin]').inner_text() == 'proposal from this panel · not a decision yet'
    assert c.locator('[data-origin]').get_attribute('data-origin') == 'webview'
    assert c.locator('[data-pause]').inner_text() == 'Pause 3 · model choice'
    assert_clean(panel)


def test_availability_is_shown_as_status_groups(open_panel, binary, model, payload):
    raw = copy.deepcopy(payload('summary.binary'))
    raw['open_proposals'] = [{'proposal_id': 'p_2', 'decision_id': 'feature_availability', 'revision': 4, 'origin': None,
                              'restatement': 'You exclude duration.',
                              'value': {'age': 'available_at_prediction', 'contact': 'uncertain_included', 'duration': 'not_available'}}]
    panel = opened(open_panel, model('summary', raw))
    groups = card(panel, 'p_2').locator('[data-value-groups] li')
    assert groups.evaluate_all('ls => ls.map(l => l.innerText)') == [
        'available at prediction time: age', 'uncertain, included: contact', 'not available: duration']
    assert_clean(panel)


# --- stale revision while typing, refusals, outcome unknown, withdraw --------------------------------

def test_a_revision_that_moves_while_typing_warns_and_keeps_the_text(open_panel, binary):
    # Decision CR.3 (review finding M1): the draft keeps the revision at which the junior
    # started typing; Confirm sends it, so the engine's stale_revision guard sees the
    # change. The warning stays, typing more does not hide it, until the junior says they
    # read the proposal again.
    panel = opened(open_panel, binary)
    page = panel.page
    area(panel).fill('Yes, the 100 best-scored')
    panel.snapshot({**binary, 'revision': 27})
    warning = card(panel).locator('[data-typing-warning="p_5"]')
    assert warning.locator('[data-typing-text]').inner_text() == (
        'The study changed while you were typing (revision 26 to 27). Read the proposal again before you answer. '
        'A confirmation now names revision 26, so the engine refuses it.')
    assert warning.get_attribute('role') == 'status'
    assert area(panel).input_value() == 'Yes, the 100 best-scored'
    # One warning only, the card's (WP-I, decision CI.4: the frame's duplicate is gone).
    assert page.locator('[data-notice]').count() == 0
    area(panel).press('End')
    area(panel).type(' clients.')
    assert card(panel).locator('[data-typing-warning]').count() == 1, 'typing more does not hide it'
    card(panel).locator('button[data-action="confirm"]').click()
    assert panel.posted()[-1]['type'] == 'confirm'
    assert panel.posted()[-1]['revision'] == 26, 'the revision the junior started typing at'
    reread = warning.locator('button[data-reread="p_5"]')
    assert reread.inner_text() == 'I read the proposal again at revision 27'
    reread.click()
    assert card(panel).locator('[data-typing-warning]').count() == 0
    assert area(panel).input_value() == 'Yes, the 100 best-scored clients.'
    card(panel).locator('button[data-action="confirm"]').click()
    assert panel.posted()[-1]['revision'] == 27
    assert panel.state()['drafts']['p_5'] == {'text': 'Yes, the 100 best-scored clients.', 'revision': 27}
    assert_clean(panel)


@pytest.mark.parametrize('theme', THEMES)
def test_inv8_refusal_is_shown_verbatim_with_an_explanation_that_suggests_no_words(open_panel, binary, describe, theme):
    panel = opened(open_panel, binary, theme=theme)
    area(panel).fill('ok')
    for fixture in ('error.bare_acknowledgement', 'error.delegation_needs_basis', 'error.stale_revision'):
        refusal = describe(fixture)
        panel.send({'type': 'outcome', 'op': 'W1', 'kind': 'refused', 'target': 'p_5', 'exitCode': 2, 'refusal': refusal})
        region = card(panel).locator('[data-card-outcome="p_5"] [data-outcome="refused"]')
        assert region.get_attribute('role') == 'alert'
        assert region.get_attribute('data-code') == refusal['code']
        assert region.locator('[data-engine-message]').inner_text() == refusal['engineMessage']
        assert region.locator('[data-human]').inner_text() == refusal['human']
        assert not re.search(r'["“”]', refusal['human']), 'the explanation quotes no words to type'
        assert panel.page.locator('[data-outcome="refused"]').count() == 1, 'shown once, on its card'
        assert area(panel).input_value() == 'ok', 'the junior\'s own text stays, nothing is added'
    assert 'Changed at revision 26: decide.propose (policy)' in card(panel).locator('[data-card-outcome]').inner_text()
    assert_clean(panel)


def test_outcome_unknown_is_never_shown_as_a_success(open_panel, binary, model, payload):
    panel = opened(open_panel, binary)
    message = ('The hypotrail CLI timed out. The outcome is unknown: the refreshed panel shows whether anything was recorded.')
    area(panel).fill(WORDS)
    panel.send({'type': 'outcome', 'op': 'W1', 'kind': 'failed', 'target': 'p_5', 'exitCode': None, 'message': message})
    region = card(panel).locator('[data-card-outcome="p_5"] [data-outcome="failed"]')
    assert region.get_attribute('role') == 'alert'
    assert message in region.inner_text()
    assert panel.page.locator('[data-outcome="ok"]').count() == 0
    assert area(panel).input_value() == WORDS
    # The refresh shows the proposal confirmed: the unknown outcome stays visible with a hint.
    raw = copy.deepcopy(payload('summary.binary'))
    raw.update({'revision': 27, 'open_proposals': []})
    panel.snapshot(model('summary', raw))
    last = panel.page.locator('[data-last-outcome="p_5"]')
    assert message in last.inner_text()
    assert last.locator('[data-unknown-hint]').inner_text().startswith('Look at the history below')
    assert panel.page.locator('[data-nothing-waiting]').inner_text() == \
        'Nothing is waiting for your answer. The assistant proposes decisions in the chat.'
    assert_clean(panel)


def test_withdraw_asks_the_extension_which_shows_the_modal(open_panel, binary):
    panel = opened(open_panel, binary)
    withdraw = card(panel).locator('button[data-action="withdraw"]')
    assert withdraw.inner_text() == 'Withdraw proposal'
    withdraw.click()
    assert panel.posted()[-1] == {'v': 2, 'type': 'withdraw', 'proposalId': 'p_5', 'revision': 26}
    panel.send({'type': 'outcome', 'op': 'W2', 'kind': 'cancelled', 'target': 'p_5', 'message': 'Nothing was recorded.'})
    cancelled = card(panel).locator('[data-outcome="cancelled"]').inner_text()
    assert cancelled.startswith('Cancelled.') and cancelled.endswith('Nothing was recorded.')
    assert_clean(panel)


# --- INV-4: no delegation control; v2 extras ------------------------------------------------------

def test_inv4_no_delegation_control_and_ask_the_agent_never_sends_the_words(open_panel, binary):
    panel = opened(open_panel, binary, stage='v2')
    page = panel.page
    area(panel).fill(WORDS)
    buttons = page.locator('#panel-decisions button').evaluate_all('bs => bs.map(b => b.innerText)')
    assert not [b for b in buttons if re.search(r'delegat|default|recommend', b, re.I)], buttons
    writes = page.locator('#panel-decisions [data-write]').evaluate_all('ns => ns.map(n => n.dataset.write)')
    assert sorted(set(writes)) == ['confirm', 'withdraw']
    ask = card(panel).locator('[data-ask="p_5"]')
    assert ask.inner_text() == 'Ask the agent about this' and ask.get_attribute('data-stage') == 'v2'
    ask.click()
    # WP-I: the shared helper of §6.8 opens the modal (an empty question), then copies.
    dialog = page.locator('[role="dialog"]')
    assert dialog.locator('textarea').input_value() == ''
    assert dialog.locator('[data-ask-about="proposal:p_5"]').count() == 1
    dialog.get_by_role('button', name='Copy for the chat').click()
    sent = panel.posted()[-1]
    assert sent == {'v': 2, 'type': 'ask_agent', 'about': {'kind': 'proposal', 'id': 'p_5'}, 'question': '', 'mode': 'copy'}
    assert WORDS not in json.dumps(panel.posted())
    assert 'delegation' in card(panel).locator('#hint-p_5').inner_text(), 'the hint says to delegate in the chat'
    assert_clean(panel)


def test_v1_has_no_v2_control(open_panel, binary):
    panel = opened(open_panel, binary, stage='v1')
    assert panel.page.locator('[data-ask], [data-evidence], [data-stage="v2"]').count() == 0
    assert_clean(panel)


def test_evidence_chips_at_v2_come_from_current_results_only(open_panel, binary, model):
    # WP-I: the chips read the real EvidenceModel (lib/models/evidence.js on the evidence
    # fixture), not a shape of their own; the stale evaluation of the fixture gets no chip.
    panel = opened(open_panel, binary, stage='v2')
    rid = 'ae80b53fe0f22e164e785d0939fef003c1b90c0482f5dd6f702ac28791426d02'
    evidence = model('evidence', 'evidence.binary')
    assert any(r['slot'] == 'policy.evaluation' and not r['current'] for r in evidence['results'])
    panel.view_data('evidence', evidence)
    chips = card(panel).locator('[data-evidence="p_5"]')
    # WP-A5: chips in words; the activity and the result id in the hover.
    assert chips.locator('[data-evidence-chip]').evaluate_all('cs => cs.map(c => [c.innerText, c.title])') == \
        [['See the calling-rule evaluation →', 'policy.evaluation · result ae80b53f…']]
    delta = chips.locator('[data-evidence-delta] data[data-result-id]')
    assert delta.inner_text() == \
        'Share of successes among the cases picked, against the baseline: +24.5% (interval +15.7% to +34.5%)'
    assert delta.get_attribute('data-result-id') == rid
    assert delta.get_attribute('data-path') == 'rules.capacity:100.deltas.[fit.logistic].precision'
    assert chips.locator('[data-explore]').inner_text() == 'try other rules →'
    chips.locator('[data-evidence-chip]').click()
    assert panel.page.locator('[role="tab"][aria-selected="true"]').get_attribute('data-tab') == 'evidence'
    assert_clean(panel)


# --- RQ-1: the reconfirmation queue ----------------------------------------------------------------

def test_rq1_every_decision_to_confirm_again_is_listed_once_with_its_previous_words(open_panel, binary, decisions, payload):
    panel = opened(open_panel, binary, stage='v2')
    panel.view_data('decisions', decisions('decisions.binary.reconfirm'), revision=26)
    queue = panel.page.locator('[data-queue-item]')
    raw = payload('decisions.binary.reconfirm')
    assert queue.evaluate_all('qs => qs.map(q => q.dataset.queueItem)') == [q['decision_id'] for q in raw['reconfirm_queue']]
    item = panel.page.locator('[data-queue-item="conclusion"]')
    assert panel.page.locator('#h-dc-queue').inner_text() == 'Needs your words again'
    assert item.locator('h3').inner_text() == 'Conclude proportionately'
    assert item.locator('[data-queue-reason]').inner_text() == 'policy changed: capacity:100 replaces threshold:0.2'
    assert item.locator('[data-previous]').inner_text() == \
        ('Previously: “We adopt the threshold policy for the next wave, knowing the figures are optimistic.” '
         '(explicit · chat)')
    assert 'No new proposal yet. Ask the agent to propose it again.' in item.inner_text()
    assert item.locator('[data-ask-decision="conclusion"]').count() == 1
    assert item.locator('[data-choose]').count() == 0, 'What if? is for the third decision only'
    # The queue is above the history.
    order = panel.page.locator('#h-dc-queue, #h-dc-history').evaluate_all('hs => hs.map(h => h.id)')
    assert order == ['h-dc-queue', 'h-dc-history']
    assert_clean(panel)


def test_rq1_open_the_new_proposal_navigates_to_its_card(open_panel, binary, model, payload):
    raw = copy.deepcopy(payload('decisions.binary.reconfirm'))
    raw['reconfirm_queue'][0]['open_proposal'] = 'p_5'
    panel = opened(open_panel, binary)
    panel.view_data('decisions', model('decisions', raw), revision=26)
    panel.page.locator('[data-open-proposal="p_5"]').click()
    assert panel.page.evaluate('document.activeElement.closest("[data-nav]").dataset.nav') == 'proposal:p_5'
    assert_clean(panel)


# --- DH-1, DH-2: the history ------------------------------------------------------------------------

@pytest.mark.parametrize('theme', THEMES)
def test_dh1_history_basis_channel_superseded_and_unconfirmed(open_panel, binary, decisions, theme):
    panel = opened(open_panel, binary, theme=theme)
    page = panel.page
    panel.view_data('decisions', decisions('decisions.binary'), revision=26)
    rows = page.locator('[data-history-row]')
    assert rows.evaluate_all('rs => rs.map(r => r.dataset.historyRow)') == [
        'prediction_time:3', 'feature_availability:5', 'split:7', 'policy:27', 'policy:23']
    assert page.locator('table[data-history] th').evaluate_all('ts => ts.map(t => t.innerText)') == \
        ['Decision', 'Your words', 'How', 'When']
    split = page.locator('[data-history-row="split:7"]')
    basis = split.locator('[data-basis]')
    assert basis.inner_text() == 'delegated (this decision) · chat'
    assert 'dc-delegated' in basis.get_attribute('class')
    tone = basis.evaluate('b => [getComputedStyle(b).color, getComputedStyle(b).backgroundColor]')
    warn = page.evaluate("""() => { const p = document.createElement('span'); p.className = 'hold'; document.body.appendChild(p);
        const c = getComputedStyle(p).color; p.remove(); return c; }""")
    assert tone[0] == warn, 'the delegated basis uses the warning tone'
    assert page.locator('[data-history-row="prediction_time:3"] [data-basis]').inner_text() == 'explicit · chat'
    assert page.locator('[data-history-row="policy:27"] [data-basis]').inner_text() == 'explicit · webview'
    old = page.locator('[data-history-row="policy:23"]')
    assert old.get_attribute('data-current') == 'false'
    assert 'muted' in old.get_attribute('class')
    assert 'superseded at revision 27' in old.inner_text()
    assert old.locator('[data-words-cell]').inner_text() == '“Yes, call everyone scored at 0.2 or more”'
    assert 'revision 23' in old.inner_text()
    assert page.locator('[data-not-authenticated]').inner_text() == 'Recorded words, not an authenticated signature.'
    details = page.locator('details[data-unconfirmed]')
    assert details.locator('summary').inner_text() == 'Proposals that were not confirmed'
    assert details.get_attribute('open') is None
    details.locator('summary').click()
    proposal = details.locator('[data-unconfirmed-proposal="p_6"]')
    assert 'p_6 · withdrawn' in proposal.inner_text()
    assert proposal.locator('blockquote').inner_text() == 'Call every client scored at 0.5 or more.'
    # WP-A5: the value in words; the status groups in the hover.
    fa = page.locator('[data-history-row="feature_availability:5"] .dc-history-value')
    assert fa.get_attribute('title').startswith('available at prediction time: age, balance')
    assert 'not available: campaign, day, duration, month' in fa.get_attribute('title')
    assert fa.inner_text().endswith('4 excluded (duration, day, month, campaign)') or \
        fa.inner_text().endswith('4 excluded (campaign, day, duration, month)'), fa.inner_text()
    assert page.locator('[data-history-row="policy:27"] .dc-history-value').inner_text() == 'Call the top 100 by score'
    assert_clean(panel)


def test_dh2_words_and_restatements_with_markup_render_as_text(open_panel, binary, decisions):
    panel = opened(open_panel, binary)
    page = panel.page
    page.evaluate('() => { window.alerted = false; window.alert = () => { window.alerted = true; }; }')
    panel.view_data('decisions', decisions('decisions.binary.injection'), revision=26)
    words = page.locator('[data-history-row="prediction_time:3"] [data-words-cell]').inner_text()
    assert words == '“Before the call <img src=x onerror=alert(1)> and <b>nothing</b> else.”'
    page.locator('details[data-unconfirmed] summary').click() if page.locator('details[data-unconfirmed]').count() else None
    assert page.locator('#panel-decisions img, #panel-decisions b, #panel-decisions script').count() == 0
    assert page.evaluate('window.alerted') is False
    raw = page.locator('#panel-decisions').inner_text()
    assert '<img src=x onerror=alert(1)>' in raw
    assert_clean(panel)


def test_history_loading_updating_and_load_error_with_retry(open_panel, binary, decisions):
    panel = opened(open_panel, binary)
    page = panel.page
    section = page.locator('section[aria-labelledby="h-dc-history"]')
    assert section.get_attribute('aria-busy') == 'true'
    panel.send({'type': 'load_error', 'view': 'decisions', 'message': 'unsupported_capability: decisions is reserved.', 'detail': ''})
    alert = page.locator('[data-history-error]')
    assert alert.get_attribute('role') == 'alert'
    assert 'unsupported_capability: decisions is reserved.' in alert.inner_text()
    before = len([m for m in panel.posted() if m == {'v': 2, 'type': 'load', 'view': 'decisions'}])
    alert.get_by_role('button', name='Retry').click()
    after = len([m for m in panel.posted() if m == {'v': 2, 'type': 'load', 'view': 'decisions'}])
    assert after == before + 1
    assert card(panel).count() == 1, 'the cards still work from the summary'
    panel.view_data('decisions', decisions('decisions.binary'), revision=25)
    assert page.locator('[data-updating]').inner_text() == 'Updating...'
    assert_clean(panel)


# --- modes, stages, vocabulary, accessibility ---------------------------------------------------------

def test_reviewer_mode_renders_no_answer_control(open_panel, binary, decisions):
    panel = opened(open_panel, binary, reviewer=True, stage='v2')
    page = panel.page
    panel.view_data('decisions', decisions('decisions.binary.reconfirm'), revision=26)
    assert page.locator('textarea').count() == 0
    assert page.locator('#panel-decisions [data-write]').count() == 0
    assert card(panel).locator('[data-reviewer-note]').inner_text() == 'Read-only reviewer mode: this panel records no answer.'
    assert card(panel).locator('[data-ask="p_5"]').count() == 1, 'the agent bridge stays'
    assert page.locator('[data-history-row]').count() > 0
    assert_clean(panel)


def test_v0_keeps_the_v0_cards_and_reads_nothing_more(open_panel, binary):
    panel = opened(open_panel, binary, stage='v0')
    page = panel.page
    page.wait_for_timeout(200)
    assert [m['type'] for m in panel.posted()] == ['ready']
    assert page.get_by_label('Your answer, in your own words').input_value() == ''
    assert page.locator('[data-effects], [data-history], [data-pause], [data-origin]').count() == 0
    assert card(panel).locator('h3').inner_text() == 'Choose a decision policy', 'no raw decision id (WP-A5)'
    assert_clean(panel)


def test_inv12_regression_decisions_tab_holds_no_decision_rule_vocabulary(open_panel, regression, decisions, effects, model, payload):
    raw = copy.deepcopy(payload('decisions.regression'))
    raw['reconfirm_queue'] = [{'decision_id': 'model_choice', 'reason': 'the split changed', 'since_revision': 21,
                               'previous': {'value': 'fit.linear', 'user_words': 'Adopt the linear model.',
                                            'basis': 'explicit', 'channel': 'chat'}, 'open_proposal': None}]
    panel = opened(open_panel, regression, stage='v2', task='regression')
    page = panel.page
    panel.send(effects_message(effects('preview_effects.regression')))
    panel.view_data('decisions', model('decisions', raw), revision=22)
    panel.view_data('evidence', {'revision': 22, 'task': 'regression', 'results': [
        {'resultId': 'a' * 64, 'slot': 'evaluate.regression', 'activity': 'evaluate.regression', 'current': True, 'integrity': 'ok'}]})
    page.locator('details[data-unconfirmed] summary').click() if page.locator('details[data-unconfirmed]').count() else None
    text = page.locator('body').inner_text()
    assert not FORBIDDEN.search(text), FORBIDDEN.search(text).group(0)
    assert card(panel, 'p_4').locator('[data-explore]').inner_text() == 'explore the errors →'
    assert card(panel, 'p_4').locator('[data-effects-box="kept"]').inner_text() == \
        'Kept\nboth models and their predictions, nothing refitted'
    assert page.locator('[data-choose="model_choice"]').inner_text() == 'Choose in What if?'
    assert_clean(panel)


def test_a11y_names_labels_headings_focus_and_no_positive_tabindex(open_panel, binary, decisions, effects):
    panel = opened(open_panel, binary, stage='v2')
    page = panel.page
    panel.send(effects_message(effects('preview_effects.binary.reconfirm')))
    panel.view_data('decisions', decisions('decisions.binary.reconfirm'), revision=26)
    unnamed = page.evaluate("""() => [...document.querySelectorAll('#panel-decisions button, #panel-decisions textarea')]
        .filter(n => { const label = n.labels && n.labels.length ? n.labels[0].innerText : '';
                       return !(n.getAttribute('aria-label') || label || n.innerText).trim(); })
        .map(n => n.outerHTML.slice(0, 80))""")
    assert unnamed == []
    assert page.locator('#panel-decisions [tabindex]').evaluate_all(
        'ns => ns.filter(n => Number(n.getAttribute("tabindex")) > 0).length') == 0
    assert page.locator('#panel-decisions h2').count() >= 3
    assert card(panel).get_attribute('aria-labelledby') == 'title-p_5'
    assert card(panel).locator('[data-effects]').get_attribute('aria-labelledby') == 'effects-p_5'
    page.locator('#words-p_5').focus()
    page.keyboard.press('Tab')
    page.keyboard.press('Shift+Tab')
    outline = page.evaluate('getComputedStyle(document.activeElement).outlineStyle')
    assert page.evaluate('document.activeElement.id') == 'words-p_5'
    assert outline != 'none', 'focus is visible'
    assert_clean(panel)


def test_navigate_to_a_decision_focuses_its_open_card(open_panel, binary):
    panel = opened(open_panel, binary)
    panel.send({'type': 'navigate', 'tab': 'decisions', 'kind': 'decision', 'id': 'policy'})
    assert panel.page.evaluate('document.activeElement.id') == 'title-p_5'
    assert_clean(panel)
