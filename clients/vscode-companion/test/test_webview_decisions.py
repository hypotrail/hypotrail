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

from conftest import inline_styles_ok

FORBIDDEN = re.compile(r'\b(threshold|capacity|precision|recall|positive class|policy|calling rule|decision rule|selected)\b', re.I)
THEMES = ['light', 'dark']
RESTATEMENT = 'Call the 100 clients with the highest scores.'


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


def effects_message(model, revision=None):
    return {'type': 'effects', 'proposalId': model['proposalId'], 'revision': revision or model['revision'], 'model': model}


def wait_until(page, expression, timeout_ms=3000):
    """Poll ``expression`` (the CSP forbids the string eval of ``wait_for_function``)."""
    for _ in range(timeout_ms // 50):
        if page.evaluate(expression):
            return
        page.wait_for_timeout(50)
    raise AssertionError(f'timed out waiting for {expression}')


def assert_clean(panel):
    assert panel.clean(), (panel.requests, panel.errors, panel.csp, panel.violations())
    assert inline_styles_ok(panel.page), 'no inline style attribute (CSP)'


# --- DC-12 (WP-E1): the card is read only; the answer is given in the chat --------------------------

@pytest.mark.parametrize('theme', THEMES)
def test_dc12_the_card_is_read_only_answer_in_the_chat_and_ask_the_agent(open_panel, binary, effects, theme):
    """DC-12 (WP-E1, R23): no words field, no Confirm, no Withdraw. DC-1, DC-2, DC-3 and DC-5
    are withdrawn with W1 and W2: the card holds no textarea and no write control at all."""
    panel = opened(open_panel, binary, theme=theme)
    page = panel.page
    c = card(panel)
    block = c.locator('[data-restatement-block="p_5"]')
    assert block.locator('.dc-lead').inner_text() == 'The assistant proposes:'
    assert block.locator('[data-restatement="p_5"]').inner_text() == RESTATEMENT
    assert block.locator('[data-proposed-value="p_5"]').inner_text() == 'In short: Select the top 100 by score'
    panel.send(effects_message(effects('preview_effects.binary.reconfirm')))
    assert page.locator('textarea').count() == 0
    assert page.locator('#panel-decisions [data-write]').count() == 0
    assert c.locator('button[data-action]').count() == 0
    buttons = c.locator('button').evaluate_all('bs => bs.map(b => b.innerText)')
    assert not [b for b in buttons if re.search(r'confirm|withdraw|propose', b, re.I)], buttons
    note = c.locator('[data-answer-in-chat="p_5"]')
    assert note.get_attribute('role') == 'note'
    assert note.locator('.title').inner_text() == 'Answer in the chat'
    assert 'This panel records no decision.' in note.inner_text()
    ask = c.locator('[data-ask-proposal="p_5"]')
    assert ask.inner_text() == 'Ask the agent about this'
    assert ask.get_attribute('data-ask-direct') == 'true'
    ask.click()
    # One press copies a ready question: no modal, no field (§6.8, WP-E1).
    assert page.locator('[role="dialog"]').count() == 0
    assert panel.posted()[-1] == {'v': 2, 'type': 'ask_agent', 'about': {'kind': 'proposal', 'id': 'p_5'},
                                  'question': 'Can you explain this proposal and what confirming it would change in my study?',
                                  'mode': 'copy'}
    assert not any(m['type'] in ('confirm', 'withdraw', 'propose') for m in panel.posted())
    assert_clean(panel)


def test_a_confirmation_made_in_the_chat_removes_the_card(open_panel, binary, model, payload):
    panel = opened(open_panel, binary)
    assert card(panel).count() == 1
    raw = copy.deepcopy(payload('summary.binary'))
    raw.update({'revision': 27, 'open_proposals': []})
    panel.snapshot(model('summary', raw))
    assert card(panel).count() == 0
    assert panel.page.locator('[data-nothing-waiting]').inner_text() == \
        'Nothing is waiting for your answer. The assistant proposes decisions in the chat.'
    assert (panel.state() or {}).get('drafts') is None, 'no confirmation drafts are kept any more'
    assert_clean(panel)


def test_a_blocked_preview_says_the_chat_confirmation_would_be_refused(open_panel, binary, effects):
    panel = opened(open_panel, binary)
    c = card(panel)
    panel.send(effects_message(effects('preview_effects.binary.blocked')))
    blocked = c.locator('[data-blocked="p_5"]')
    assert blocked.get_attribute('role') == 'status'
    assert blocked.inner_text().startswith('If you confirm it in the chat now, the engine will refuse it:')
    item = blocked.locator('[data-blocked-code="decision_on_hold"]')
    assert item.get_attribute('title').startswith('decision_on_hold'), 'the code is in the hover'
    assert blocked.locator('[data-engine-message]').inner_text() == \
        "This decision is on hold in the junior's own words; resolve the note first."
    assert 'decision_on_hold' not in blocked.inner_text()
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
def test_dc4_the_conclusion_to_confirm_again_in_words_kept_and_regenerated_under_details(open_panel, binary, effects, theme):
    panel = opened(open_panel, binary, theme=theme)
    panel.send(effects_message(effects('preview_effects.binary.reconfirm')))
    section = card(panel).locator('[data-effects="p_5"]')
    assert section.locator('h4').inner_text() == 'If you confirm'
    # R22: what a confirmation invalidates, in words; the rest under Details.
    invalidated = section.locator('[data-effects-invalidated] [data-effects-box]')
    assert invalidated.evaluate_all('bs => bs.map(b => b.dataset.effectsBox)') == ['reconfirm']
    assert section.locator('[data-effects-box="reconfirm"]').inner_text() == 'To confirm again: the conclusion'
    assert section.locator('[data-effects-nothing]').count() == 0
    details = section.locator('details[data-effects-details="p_5"]')
    assert details.get_attribute('open') is None
    assert details.locator('[data-effects-box="kept"]').text_content() == \
        'Kept: both models and their predictions, nothing refitted'
    assert details.locator('[data-effects-box="regenerated"]').text_content() == 'Regenerated: report and notebook'
    # WP-A5: the engine's note on the preview is kept, verbatim, under Details.
    assert details.locator('[data-effects-note]').text_content() == \
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
    # R22: nothing invalidated is one line; the rest is under Details.
    assert first.locator('[data-effects-nothing]').inner_text() == 'Confirming changes nothing already done.'
    assert first.locator('[data-effects-invalidated]').count() == 0
    assert first.locator('[data-effects-first]').text_content() == \
        'This is the first decision of the study, so nothing recorded so far is invalidated.'
    assert first.locator('[data-effects-box="kept"]').text_content() == 'Kept: nothing'
    split = card(panel, 'p_8').locator('[data-effects]')
    stale = split.locator('[data-effects-box="stale"]').inner_text()
    assert stale.startswith('Becomes stale: ')
    assert 'the logistic model' in stale and 'fit.logistic' not in stale, 'slots in words (WP-A5)'
    assert split.locator('[data-effects-box="reconfirm"]').inner_text() == 'To confirm again: the decision rule'
    assert 'fit.baseline' not in split.locator('[data-effects-box="kept"]').text_content()
    assert split.locator('[data-effects-nothing]').count() == 0
    assert split.locator('.dc-notes').inner_text() == 'Changing the split does not make explored rows unseen.'
    assert_clean(panel)


def test_an_unavailable_preview_says_so(open_panel, binary):
    panel = opened(open_panel, binary)
    message = ('The engine could not preview this confirmation. preview effects is reserved for the advanced '
               'companion and is not implemented in this version. Nothing was read or written.')
    panel.send({'type': 'effects', 'proposalId': 'p_5', 'revision': 26, 'model': {
        'available': False, 'proposalId': 'p_5', 'message': message, 'code': 'unsupported_capability', 'reason': 'not_implemented'}})
    missing = card(panel).locator('[data-effects-missing]')
    assert missing.inner_text() == f'The impact preview is not available. {message}'
    assert card(panel).locator('[data-answer-in-chat="p_5"]').count() == 1
    assert_clean(panel)


# --- the card head, holds, origin (DC-6), value groups --------------------------------------------

def test_card_head_pause_origin_holds_and_resolved_conditions(open_panel, binary, model, payload):
    panel = opened(open_panel, binary)
    c = card(panel)
    assert c.locator('[data-pause]').inner_text() == 'Pause 3 · business trade-off'
    assert c.locator('h3').first.inner_text() == 'Choose a decision policy'
    # WP-E1 (R22): the origin, the proposal id and the revision are under Details only.
    details = c.locator('details[data-value-details="p_5"]')
    assert details.get_attribute('open') is None
    assert details.locator('[data-origin]').text_content() == 'Proposed by the agent; not a decision yet.'
    assert details.locator('[data-made-at="p_5"]').text_content() == 'Proposal p_5, made at revision 26'
    assert details.locator('code').text_content() == 'capacity:100'
    value = c.locator('[data-proposed-value="p_5"]')
    assert value.inner_text() == 'In short: Select the top 100 by score'
    assert value.locator('[data-value-raw]').get_attribute('data-value-raw') == 'capacity:100'
    shown = ' '.join(c.locator(':scope > :not(details)').all_inner_texts())
    assert 'p_5' not in shown and 'revision 26' not in shown, 'no internal id or revision in the card text'
    # R25: words carry no dotted underline (citation style on numbers only).
    deco = value.locator('[data-value-raw]').evaluate('n => getComputedStyle(n).textDecorationLine')
    assert deco == 'none', deco
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
    origin = c.locator('[data-origin]')
    assert origin.text_content() == 'Proposed from this panel by an earlier version; not a decision yet.'
    assert origin.get_attribute('data-origin') == 'webview'
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




# --- INV-4: no delegation control; v2 extras ------------------------------------------------------

def test_inv4_no_delegation_control_and_no_write_control_at_v2(open_panel, binary):
    panel = opened(open_panel, binary, stage='v2')
    page = panel.page
    buttons = page.locator('#panel-decisions button').evaluate_all('bs => bs.map(b => b.innerText)')
    assert not [b for b in buttons if re.search(r'delegat|default|recommend', b, re.I)], buttons
    assert page.locator('#panel-decisions [data-write]').count() == 0, 'WP-E1: the tab writes nothing'
    ask = card(panel).locator('[data-ask-proposal="p_5"]')
    assert ask.inner_text() == 'Ask the agent about this' and ask.get_attribute('data-stage') is None, 'offered at every stage'
    ask.click()
    assert panel.posted()[-1]['type'] == 'ask_agent'
    assert panel.posted()[-1]['about'] == {'kind': 'proposal', 'id': 'p_5'}
    assert_clean(panel)


def test_v1_has_no_v2_control(open_panel, binary):
    panel = opened(open_panel, binary, stage='v1')
    assert panel.page.locator('[data-evidence], [data-stage="v2"]').count() == 0
    assert card(panel).locator('[data-ask-proposal="p_5"]').count() == 1, 'the card asks the agent at every stage'
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
        [['See the decision-rule evaluation →', 'policy.evaluation · result ae80b53f…']]
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
    assert panel.page.locator('#h-dc-queue').inner_text() == 'Needs your answer again'  # WP-E3: mode-neutral (R23)
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
    # R25: newest first; the revision and the time are in the hover of the decision.
    assert rows.evaluate_all('rs => rs.map(r => r.dataset.historyRow)') == [
        'policy:27', 'policy:23', 'split:7', 'feature_availability:5', 'prediction_time:3']
    assert page.locator('table[data-history] th').evaluate_all('ts => ts.map(t => t.innerText)') == \
        ['Decision', 'Your words', 'How']
    assert page.locator('table[data-history] .ht-mono').count() == 0, 'no monospace revision'
    when = page.locator('[data-history-row="split:7"] td[data-when]')
    assert when.get_attribute('title').startswith('revision 7 · '), when.get_attribute('title')
    assert 'revision 7' not in page.locator('[data-history-row="split:7"]').inner_text()
    split = page.locator('[data-history-row="split:7"]')
    basis = split.locator('[data-basis]')
    # WP-A7: the basis is a chip of one vocabulary, the channel in words beside it.
    assert basis.inner_text() == 'delegated (this decision)'
    assert split.locator('[data-basis-cell]').inner_text() == 'delegated (this decision) in the chat'
    assert 'dc-delegated' in basis.get_attribute('class')
    tone = basis.evaluate('b => [getComputedStyle(b).color, getComputedStyle(b).backgroundColor]')
    warn = page.evaluate("""() => { const p = document.createElement('span'); p.className = 'hold'; document.body.appendChild(p);
        const c = getComputedStyle(p).color; p.remove(); return c; }""")
    assert tone[0] == warn, 'the delegated basis uses the warning tone'
    # WP-A7: the fixture's prediction moment is restated (ADR 0005); a confirmation recorded
    # before the guided rule (explicit) reads "your words".
    assert page.locator('[data-history-row="prediction_time:3"] [data-basis-cell]').inner_text() == 'restated in the chat'
    assert page.locator('[data-history-row="policy:27"] [data-basis-cell]').inner_text() == 'your words in this panel'
    old = page.locator('[data-history-row="policy:23"]')
    assert old.get_attribute('data-current') == 'false'
    assert 'muted' in old.get_attribute('class')
    superseded = old.locator('[data-superseded]')
    assert superseded.inner_text().strip() == '· superseded'
    assert superseded.get_attribute('title') == 'superseded at revision 27'
    assert old.locator('[data-words-cell]').inner_text() == '“Yes, call everyone scored at 0.2 or more”'
    assert old.locator('td[data-when]').get_attribute('title').startswith('revision 23')
    assert page.locator('[data-not-authenticated]').inner_text() == 'Recorded words, not an authenticated signature.'
    details = page.locator('details[data-unconfirmed]')
    assert details.locator('summary').inner_text() == 'Proposals that were not confirmed'
    assert details.get_attribute('open') is None
    details.locator('summary').click()
    proposal = details.locator('[data-unconfirmed-proposal="p_6"]')
    assert 'withdrawn' in proposal.inner_text() and 'p_6' not in proposal.inner_text()
    assert proposal.locator('[title="p_6"]').count() == 1, 'the proposal id is in the hover'
    assert proposal.locator('blockquote').inner_text() == 'Call every client scored at 0.5 or more.'
    # WP-A5: the value in words; the status groups in the hover.
    fa = page.locator('[data-history-row="feature_availability:5"] .dc-history-value')
    assert fa.get_attribute('title').startswith('available at prediction time: age, balance')
    assert 'not available: campaign, day, duration, month' in fa.get_attribute('title')
    assert fa.inner_text().endswith('4 excluded (duration, day, month, campaign)') or \
        fa.inner_text().endswith('4 excluded (campaign, day, duration, month)'), fa.inner_text()
    assert page.locator('[data-history-row="policy:27"] .dc-history-value').inner_text() == 'Select the top 100 by score'
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
    assert card(panel).locator('[data-answer-in-chat="p_5"]').count() == 1
    assert card(panel).locator('[data-ask-proposal="p_5"]').count() == 1, 'the agent bridge stays'
    assert page.locator('[data-history-row]').count() > 0
    assert_clean(panel)


def test_v0_keeps_the_v0_cards_and_reads_nothing_more(open_panel, binary):
    panel = opened(open_panel, binary, stage='v0')
    page = panel.page
    page.wait_for_timeout(200)
    assert [m['type'] for m in panel.posted()] == ['ready']
    assert page.locator('textarea').count() == 0, 'WP-E1: no words field at v0 either'
    assert page.locator('[data-write]').count() == 0
    assert page.locator('[data-effects], [data-history], [data-pause]').count() == 0
    assert card(panel).locator('h3').inner_text() == 'Choose a decision policy', 'no raw decision id (WP-A5)'
    assert card(panel).locator('[data-answer-in-chat="p_5"] .title').inner_text() == 'Answer in the chat'
    ask = card(panel).locator('[data-ask-proposal="p_5"]')
    assert ask.inner_text() == 'Ask the agent about this'
    ask.click()
    assert panel.posted()[-1]['type'] == 'ask_agent', 'the bridge is v0 since WP-E1'
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
    assert card(panel, 'p_4').locator('[data-effects-box="kept"]').text_content() == \
        'Kept: both models and their predictions, nothing refitted'
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
    page.locator('[data-ask-proposal="p_5"]').focus()
    page.keyboard.press('Tab')
    page.keyboard.press('Shift+Tab')
    outline = page.evaluate('getComputedStyle(document.activeElement).outlineStyle')
    assert page.evaluate('document.activeElement.dataset.askProposal') == 'p_5'
    assert outline != 'none', 'focus is visible'
    assert_clean(panel)


def test_navigate_to_a_decision_focuses_its_open_card(open_panel, binary):
    panel = opened(open_panel, binary)
    panel.send({'type': 'navigate', 'tab': 'decisions', 'kind': 'decision', 'id': 'policy'})
    assert panel.page.evaluate('document.activeElement.id') == 'title-p_5'
    assert_clean(panel)


# --- DC-13 (owner session 2026-10-26, R16, D20): the choice the chat waits for ----------------

CHOICES = [{'id': 'adopt_policy', 'value': 'adopt_policy', 'label': 'Adopt the rule'},
           {'id': 'keep_baseline', 'value': 'keep_baseline', 'label': 'Keep the baseline'},
           {'id': 'inconclusive', 'value': 'inconclusive', 'label': 'Do not conclude (inconclusive)'}]


def choice_summary(model, payload, options=CHOICES):
    raw = copy.deepcopy(payload('captured/summary.binary.cv.opening'))
    raw['open_proposals'] = []
    raw['next_action'] = {'kind': 'propose', 'step': 'conclusion', 'decision': 'conclusion',
                          'message': 'Propose the conclusion.', 'audience': 'agent',
                          'junior_message': 'Choose the conclusion in the chat.',
                          'choice_options': options}
    return model('summary', raw)


@pytest.mark.parametrize('stage', ['v1', 'v2', 'v3'])
def test_dc13_a_choice_the_chat_waits_for_is_a_read_only_card(open_panel, model, payload, stage):
    """DC-13 (R16): at the conclusion the chat asks to choose before any proposal exists; the
    waiting section shows that choice with the engine's options, "Answer in the chat" and the
    copy-only ask button. No control, no field, no write; "nothing waits" is not shown."""
    panel = opened(open_panel, choice_summary(model, payload), stage=stage)
    page = panel.page
    c = page.locator('[data-choice-card="conclusion"]')
    assert c.count() == 1
    assert c.locator('h3').inner_text() == 'The conclusion: the assistant asks you to choose in the chat'
    assert c.locator('[data-choice-option]').all_inner_texts() == [o['label'] for o in CHOICES]
    assert c.locator('[data-choice-option="keep_baseline"]').get_attribute('title') == 'keep_baseline'
    assert page.locator('[data-nothing-waiting]').count() == 0
    # Under "Waiting for your answer", first.
    waiting = page.locator('section[aria-labelledby="h-proposals"]')
    assert waiting.locator('h2').inner_text() == 'Waiting for your answer'
    assert waiting.locator('[data-choice-card]').count() == 1
    note = c.locator('[data-answer-in-chat="conclusion"]')
    assert note.get_attribute('role') == 'note' and note.locator('.title').inner_text() == 'Answer in the chat'
    assert 'This panel records no choice.' in note.inner_text()
    assert c.locator('textarea, input, select, [data-write]').count() == 0
    assert c.locator('button').count() == 1
    ask = c.locator('[data-ask-choice="conclusion"]')
    assert ask.get_attribute('data-ask-direct') == 'true'
    ask.click()
    assert page.locator('[role="dialog"]').count() == 0
    assert panel.posted()[-1] == {'v': 2, 'type': 'ask_agent', 'about': {'kind': 'decision', 'id': 'conclusion'},
                                  'question': 'Can you explain these options and what each one would mean for my study?',
                                  'mode': 'copy'}
    assert not any(m['type'] in ('confirm', 'withdraw', 'propose', 'run') for m in panel.posted())
    assert_clean(panel)


def test_dc13_at_v0_the_next_move_says_answer_in_the_chat_and_no_card(open_panel, model, payload):
    """D20: v0 is one page without Decisions tab: no choice card; "Your next move" says to
    choose in the chat, with no button. From v1 the next move leads to the card."""
    summary = choice_summary(model, payload)
    panel = opened(open_panel, summary, stage='v0')
    page = panel.page
    assert page.locator('[data-choice-card]').count() == 0
    hero = page.locator('[data-ov="hero"]')
    assert hero.get_attribute('data-hero') == 'choice'
    assert hero.locator('[data-hero-title]').inner_text() == 'Choose the conclusion, in the chat'
    assert 'this panel records no choice' in hero.locator('[data-hero-lead]').inner_text()
    assert hero.locator('[data-hero-action]').count() == 0
    assert_clean(panel)
    panel = opened(open_panel, summary, stage='v1')
    page = panel.page
    page.locator('[role="tab"][data-tab="overview"]').click()
    action = page.locator('[data-hero-action="decision:conclusion"]')
    assert action.inner_text() == 'See the options'
    action.click()
    assert page.locator('[role="tab"][data-tab="decisions"]').get_attribute('aria-selected') == 'true'
    assert page.locator('[data-choice-card="conclusion"]').is_visible()


def test_dc13_the_choice_card_in_french_and_for_the_model_choice(open_panel, model, payload):
    """The card's words follow the panel language; the options keep the engine's labels."""
    options = [{'id': 'fit.logistic', 'value': 'fit.logistic', 'label': 'Le modèle logistique'},
               {'id': 'fit.variant:2', 'value': 'fit.variant:2', 'label': 'La deuxième variante · boosting explicable'}]
    raw = copy.deepcopy(payload('captured/summary.binary.cv.opening'))
    raw['open_proposals'] = []
    raw['next_action'] = {'kind': 'propose', 'step': 'model_choice', 'decision': 'model_choice',
                          'message': 'Propose the model choice.', 'audience': 'agent',
                          'junior_message': 'Choisissez le modèle dans le chat.', 'choice_options': options}
    panel = opened(open_panel, model('summary', raw), stage='v3')
    page = panel.page
    page.locator('[data-language="fr"]').click()
    c = page.locator('[data-choice-card="model_choice"]')
    assert c.locator('h3').inner_text() == "Le choix du modèle : l'assistant vous demande de choisir dans le chat"
    assert c.locator('[data-choice-option]').all_inner_texts() == [o['label'] for o in options]
    assert c.locator('[data-answer-in-chat] .title').inner_text() == 'Répondre dans le chat'
    assert_clean(panel)
