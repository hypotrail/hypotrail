"""Browser tests of the decisions on the one page (scope S, simulated browser; WP-U2 re-pointed by
ADR 0004 d13; COMPANION-ADVANCED §6.5, §A.2, NOW-4, NOW-7, NOW-9, PATH-5, PATH-8, INV-4,
INV-5, INV-8, INV-9, §12, §13).

The open proposal is Now's card, read only and answered in the chat (DC-12 → NOW-9); "What your
answer will change" is a fold of Now that reads `preview effects` (DC-4 → NOW-9); each step's
history is in its detail in the path (DH-1, DH-2, DC-6 → PATH-5, PATH-8). Withdrawn with the
Decisions tab, and their tests with them: the card head with its pause and origin, the
availability groups and the evidence chips on the card (DC-8, DC-9 → PATH-8's words and
hovers), the reconfirmation queue section (RQ-1 → NOW-5, PATH-3; `test_webview_page.py`), the
three-card read budget (Now holds one proposal), and the tab's own heading and accessibility
scans (A11Y-1 on the whole page: `test_webview_header.py`).

The real document is loaded offline in headless Chromium (``conftest.py``); models come from
the real ``lib/models/*.js`` functions on the WP-0 fixtures. This is not a VS Code session.
"""
from __future__ import annotations

import copy
import re

import pytest

from conftest import inline_styles_ok
from panel_cases import click_fold

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
    panel.init(stage=stage, reviewer=reviewer, task=task, panelContract=2)
    panel.snapshot(summary)
    return panel


def card(panel, pid='p_5'):
    return panel.page.locator(f'[data-block="now"] [data-proposal-card="{pid}"]')


def open_effects(panel):
    """Open Now's "What your answer will change" (NOW-9), which reads `preview effects`."""
    click_fold(panel.page, 'effects')
    return panel.page.locator('[data-block="now"] [data-effects]')


def open_history(panel, step):
    """Go to a step of the path (NAV-1) and return its history (PATH-5, v1)."""
    panel.send({'type': 'navigate', 'anchor': f'path:{step}'})
    return panel.page.locator(f'[data-step-history="{step}"]')


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


def summary_with(payload, model, **changes):
    raw = copy.deepcopy(payload('summary.binary'))
    raw.update(changes)
    return model('summary', raw)


def test_hon8_a_data_contingent_proposal_is_said_next_to_it(open_panel, payload, model):
    """HON-8: when the engine marks the open proposal `data_contingent` (P1 §17.2.6), Now shows
    the engine's junior text in a warning note next to the proposal, in the panel language; the
    same text without the engine's mark shows nothing (the panel adds no such mark itself)."""
    words = {'en': 'You changed the rule after reading its validation result.',
             'fr': 'Vous avez changé la règle après avoir lu son résultat de validation.'}

    def summary(flag):
        raw = copy.deepcopy(payload('summary.binary'))
        for p in raw['open_proposals']:
            if p['proposal_id'] == 'p_5':
                p['data_contingent'] = flag
        texts = raw.get('texts') or {}
        for lang in ('en', 'fr'):
            texts[lang] = texts.get(lang) or {}
            texts[lang]['data_contingent'] = {'p_5': words[lang]}
        raw['texts'] = texts
        return model('summary', raw)

    panel = opened(open_panel, summary(True))
    note = panel.page.locator('[data-block="now"] [data-contingent="p_5"]')
    assert note.count() == 1 and note.get_attribute('role') == 'note'
    assert note.inner_text() == f'Result-dependent change: {words["en"]}'
    assert_clean(panel)
    for flag in (False, None):
        quiet = opened(open_panel, summary(flag))
        assert quiet.page.locator('[data-contingent]').count() == 0, flag
        assert words['en'] not in quiet.page.locator('[data-block="now"]').inner_text()


# --- DC-12 → NOW-9: the card is read only; the answer is given in the chat --------------------------

@pytest.mark.parametrize('theme', THEMES)
def test_dc12_now9_the_proposal_is_read_only_and_answered_in_the_chat(open_panel, binary, effects, theme):
    """DC-12 (WP-E1, R23), INV-4, INV-5: Now's proposal card has no words field, no Confirm, no
    Withdraw, no delegation; one press copies a ready question (§6.12). DC-1, DC-3 and DC-5 were
    withdrawn with W1 by WP-E1: there is no textarea to empty or fill and no confirm message."""
    panel = opened(open_panel, binary, theme=theme)
    page = panel.page
    c = card(panel)
    assert c.locator('[data-restatement="p_5"]').inner_text() == RESTATEMENT
    assert c.locator('.ht-plainsay').inner_text() == 'In short: Select the top 100 by score'
    assert c.locator('[data-value-raw]').get_attribute('data-value-raw') == 'capacity:100'
    open_effects(panel)
    panel.send(effects_message(effects('preview_effects.binary.reconfirm')))
    now = page.locator('[data-block="now"]')
    assert page.locator('textarea').count() == 0
    assert now.locator('[data-write], input, select').count() == 0
    buttons = now.locator('button').evaluate_all('bs => bs.map(b => b.innerText)')
    assert not [b for b in buttons if re.search(r'confirm|withdraw|propose|delegat|default|recommend', b, re.I)], buttons
    assert 'This panel records no decision.' in c.locator('[data-answer-in-chat]').inner_text()
    ask = now.locator('[data-copy-question="policy"]')
    question = page.evaluate('() => globalThis.Hypotrail.copy.page.askQuestions.policy')
    assert question in ask.inner_text()
    ask.click()
    # One press copies a ready question: no modal, no field (§6.12, WP-E1).
    assert page.locator('[role="dialog"]').count() == 0
    assert panel.posted()[-1] == {'v': 2, 'type': 'ask_agent', 'about': {'kind': 'step', 'id': 'policy'},
                                  'question': question, 'mode': 'copy'}
    assert not any(m['type'] in ('confirm', 'withdraw', 'propose') for m in panel.posted())
    # No internal id or revision in Now's prose (NOW-12).
    assert 'p_5' not in now.inner_text() and 'revision 26' not in now.inner_text()
    assert_clean(panel)


def test_a_confirmation_made_in_the_chat_moves_now_on(open_panel, binary, model, payload):
    panel = opened(open_panel, binary)
    assert card(panel).count() == 1
    panel.snapshot(summary_with(payload, model, revision=27, open_proposals=[]))
    assert card(panel).count() == 0
    assert (panel.state() or {}).get('drafts') is None, 'no confirmation drafts are kept any more'
    assert_clean(panel)


def test_a_blocked_preview_says_the_chat_confirmation_would_be_refused(open_panel, binary, effects):
    panel = opened(open_panel, binary)
    section = open_effects(panel)
    panel.send(effects_message(effects('preview_effects.binary.blocked')))
    blocked = section.locator('[data-blocked="p_5"]')
    assert blocked.get_attribute('role') == 'status'
    assert blocked.inner_text().startswith('If you confirm it in the chat now, the engine will refuse it:')
    item = blocked.locator('[data-blocked-code="decision_on_hold"]')
    assert item.get_attribute('title').startswith('decision_on_hold'), 'the code is in the hover'
    assert blocked.locator('[data-engine-message]').inner_text() == \
        "This decision is on hold in the junior's own words; resolve the note first."
    assert 'decision_on_hold' not in blocked.inner_text()
    assert_clean(panel)


# --- DC-4 → NOW-9: what your answer will change ------------------------------------------------------

def test_now9_the_preview_is_read_when_its_fold_opens_and_again_when_the_version_moves(open_panel, binary, effects):
    panel = opened(open_panel, binary)
    page = panel.page
    page.wait_for_timeout(100)
    assert not [m for m in panel.posted() if m['type'] == 'preview_effects'], 'a closed fold reads nothing (§11)'
    section = open_effects(panel)
    wait_until(page, "window.__posted.some(m => m.type === 'preview_effects')")
    assert [m for m in panel.posted() if m['type'] == 'preview_effects'] == \
        [{'v': 2, 'type': 'preview_effects', 'proposalId': 'p_5', 'revision': 26}]
    assert section.locator('[data-effects-loading]').get_attribute('aria-busy') == 'true'
    panel.send(effects_message(effects('preview_effects.binary')))
    panel.snapshot({**binary, 'revision': 27})
    wait_until(page, "window.__posted.filter(m => m.type === 'preview_effects').length === 2")
    assert [m['revision'] for m in panel.posted() if m['type'] == 'preview_effects'] == [26, 27]
    assert_clean(panel)


def test_now9_absent_at_v0(open_panel, binary):
    panel = opened(open_panel, binary, stage='v0')
    page = panel.page
    page.wait_for_timeout(200)
    assert [m['type'] for m in panel.posted()] == ['ready'], 'v0 reads nothing more'
    assert page.locator('[data-fold-id="effects"], [data-effects], [data-history]').count() == 0
    assert page.locator('textarea, [data-write]').count() == 0
    assert card(panel).locator('h3').inner_text() == 'Choose a decision policy', 'no raw decision id (WP-A5)'
    page.locator('[data-block="now"] [data-copy-question="policy"]').click()
    assert panel.posted()[-1]['type'] == 'ask_agent', 'the bridge is v0 since WP-E1'
    assert_clean(panel)


@pytest.mark.parametrize('theme', THEMES)
def test_dc4_the_conclusion_to_confirm_again_in_words_kept_and_regenerated_under_details(open_panel, binary, effects, theme):
    panel = opened(open_panel, binary, theme=theme)
    section = open_effects(panel)
    panel.send(effects_message(effects('preview_effects.binary.reconfirm')))
    assert section.locator('h4').first.inner_text() == 'If you confirm'
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


def test_dc4_first_confirmation_and_a_split_change(open_panel, effects, model, payload):
    first = {'proposal_id': 'p_1', 'decision_id': 'prediction_time', 'revision': 2, 'origin': None,
             'value': 'before the first contact of the campaign, from the client file', 'restatement': 'You score before the call.'}
    split = {'proposal_id': 'p_8', 'decision_id': 'split', 'revision': 26, 'origin': None,
             'value': {'method': 'stratified_random', 'seed': 7, 'validation_fraction': 0.3}, 'restatement': 'A new seed.'}
    raw = copy.deepcopy(payload('summary.binary'))
    raw['open_proposals'] = [first]
    raw['next_action'] = {**raw['next_action'], 'proposal_id': 'p_1', 'decision': 'prediction_time'}
    panel = opened(open_panel, model('summary', raw))
    section = open_effects(panel)
    panel.send(effects_message(effects('preview_effects.binary.first'), revision=26))
    # R22: nothing invalidated is one line; the rest is under Details.
    assert section.locator('[data-effects-nothing]').inner_text() == 'Confirming changes nothing already done.'
    assert section.locator('[data-effects-invalidated]').count() == 0
    assert section.locator('[data-effects-first]').text_content() == \
        'This is the first decision of the study, so nothing recorded so far is invalidated.'
    assert section.locator('[data-effects-box="kept"]').text_content() == 'Kept: nothing'
    raw['open_proposals'] = [split]
    raw['next_action'] = {**raw['next_action'], 'proposal_id': 'p_8', 'decision': 'split'}
    panel = opened(open_panel, model('summary', raw))
    section = open_effects(panel)
    panel.send(effects_message(effects('preview_effects.binary.split')))
    stale = section.locator('[data-effects-box="stale"]').inner_text()
    assert stale.startswith('Becomes stale: ')
    assert 'the logistic model' in stale and 'fit.logistic' not in stale, 'slots in words (WP-A5)'
    assert section.locator('[data-effects-box="reconfirm"]').inner_text() == 'To confirm again: the decision rule'
    assert 'fit.baseline' not in section.locator('[data-effects-box="kept"]').text_content()
    assert section.locator('[data-effects-nothing]').count() == 0
    assert section.locator('.dc-notes').inner_text() == 'Changing the split does not make explored rows unseen.'
    assert_clean(panel)


def test_an_unavailable_preview_says_so(open_panel, binary):
    panel = opened(open_panel, binary)
    section = open_effects(panel)
    message = ('The engine could not preview this confirmation. preview effects is reserved for the advanced '
               'companion and is not implemented in this version. Nothing was read or written.')
    panel.send({'type': 'effects', 'proposalId': 'p_5', 'revision': 26, 'model': {
        'available': False, 'proposalId': 'p_5', 'message': message, 'code': 'unsupported_capability', 'reason': 'not_implemented'}})
    assert section.locator('[data-effects-missing]').inner_text() == f'The impact preview is not available. {message}'
    assert card(panel).locator('[data-answer-in-chat]').count() == 1
    assert_clean(panel)


# --- DH-1, DH-2, DC-6 → PATH-5, PATH-8: each step's history -------------------------------------------

@pytest.mark.parametrize('theme', THEMES)
def test_dh1_dc6_path8_history_basis_channel_superseded_and_unconfirmed(open_panel, binary, decisions, theme):
    panel = opened(open_panel, binary, theme=theme)
    page = panel.page
    policy = open_history(panel, 'policy')
    assert {'v': 2, 'type': 'load', 'view': 'decisions'} in panel.posted(), 'an opened step reads its history'
    panel.view_data('decisions', decisions('decisions.binary'), revision=26)
    # R25: newest first; the revision and the time are in the hover of the decision.
    assert policy.locator('[data-history-row]').evaluate_all('rs => rs.map(r => r.dataset.historyRow)') == ['policy:27', 'policy:23']
    assert policy.locator('table[data-history] th').evaluate_all('ts => ts.map(t => t.innerText)') == \
        ['Decision', 'Your words', 'How']
    # DC-6: a confirmation from this panel (before WP-E1) says so.
    assert policy.locator('[data-history-row="policy:27"] [data-basis-cell]').inner_text() == 'your words in this panel'
    assert policy.locator('[data-history-row="policy:27"] .dc-history-value').inner_text() == 'Select the top 100 by score'
    old = policy.locator('[data-history-row="policy:23"]')
    assert old.get_attribute('data-current') == 'false'
    assert 'muted' in old.get_attribute('class')
    superseded = old.locator('[data-superseded]')
    assert superseded.inner_text().strip() == '· superseded'
    assert superseded.get_attribute('title') == 'superseded at revision 27'
    assert old.locator('[data-words-cell]').inner_text() == '“Yes, call everyone scored at 0.2 or more”'
    assert old.locator('td[data-when]').get_attribute('title').startswith('revision 23')
    assert policy.locator('[data-not-authenticated]').inner_text() == 'Recorded words, not an authenticated signature.'
    details = policy.locator('details[data-unconfirmed]')
    assert details.locator('summary').inner_text() == 'Proposals that were not confirmed'
    assert details.get_attribute('open') is None
    details.locator('summary').click()
    proposal = details.locator('[data-unconfirmed-proposal="p_6"]')
    assert 'withdrawn' in proposal.inner_text() and 'p_6' not in proposal.inner_text()
    assert proposal.locator('[title="p_6"]').count() == 1, 'the proposal id is in the hover'
    assert proposal.locator('blockquote').inner_text() == 'Call every client scored at 0.5 or more.'
    split = open_history(panel, 'split')
    row = split.locator('[data-history-row="split:7"]')
    assert page.locator('table[data-history] .ht-mono').count() == 0, 'no monospace revision'
    assert row.locator('td[data-when]').get_attribute('title').startswith('revision 7 · ')
    assert 'revision 7' not in row.inner_text()
    basis = row.locator('[data-basis]')
    # WP-A7: the basis is a chip of one vocabulary, the channel in words beside it.
    assert basis.inner_text() == 'delegated (this decision)'
    assert row.locator('[data-basis-cell]').inner_text() == 'delegated (this decision) in the chat'
    assert 'dc-delegated' in basis.get_attribute('class')
    tone = basis.evaluate('b => getComputedStyle(b).color')
    warn = page.evaluate("""() => { const p = document.createElement('span'); p.className = 'hold'; document.body.appendChild(p);
        const c = getComputedStyle(p).color; p.remove(); return c; }""")
    assert tone == warn, 'the delegated basis uses the warning tone'
    # WP-A7: the fixture's prediction moment is restated (ADR 0005).
    moment = open_history(panel, 'prediction_time')
    assert moment.locator('[data-history-row="prediction_time:3"] [data-basis-cell]').inner_text() == 'restated in the chat'
    # WP-A5: the value in words; the status groups in the hover.
    fa = open_history(panel, 'feature_availability').locator('[data-history-row="feature_availability:5"] .dc-history-value')
    assert fa.get_attribute('title').startswith('available at prediction time: age, balance')
    assert 'not available: campaign, day, duration, month' in fa.get_attribute('title')
    assert fa.inner_text().endswith('4 excluded (duration, day, month, campaign)') or \
        fa.inner_text().endswith('4 excluded (campaign, day, duration, month)'), fa.inner_text()
    assert_clean(panel)


def test_dh2_words_and_restatements_with_markup_render_as_text(open_panel, binary, decisions):
    panel = opened(open_panel, binary)
    page = panel.page
    page.evaluate('() => { window.alerted = false; window.alert = () => { window.alerted = true; }; }')
    history = open_history(panel, 'prediction_time')
    panel.view_data('decisions', decisions('decisions.binary.injection'), revision=26)
    words = history.locator('[data-history-row="prediction_time:3"] [data-words-cell]').inner_text()
    assert words == '“Before the call <img src=x onerror=alert(1)> and <b>nothing</b> else.”'
    for step in ('feature_availability', 'split', 'policy'):
        open_history(panel, step)
    for d in page.locator('details[data-unconfirmed] summary').all():
        d.click()
    assert page.locator('#main img, #main b:not(.ht-plainsay b):not([data-ledger] b):not(.ht-next b), #main script').count() == 0
    assert page.evaluate('window.alerted') is False
    assert '<img src=x onerror=alert(1)>' in page.locator('#main').inner_text()
    assert_clean(panel)


def test_history_loading_updating_and_load_error_with_retry(open_panel, binary, decisions):
    panel = opened(open_panel, binary)
    page = panel.page
    history = open_history(panel, 'split')
    assert history.count() == 0
    busy = page.locator('[data-step="split"] section[aria-labelledby="h-dc-history"]')
    assert busy.get_attribute('aria-busy') == 'true'
    panel.send({'type': 'load_error', 'view': 'decisions', 'message': 'unsupported_capability: decisions is reserved.', 'detail': ''})
    alert = page.locator('[data-history-error]')
    assert alert.get_attribute('role') == 'alert'
    assert 'unsupported_capability: decisions is reserved.' in alert.inner_text()
    before = len([m for m in panel.posted() if m == {'v': 2, 'type': 'load', 'view': 'decisions'}])
    alert.get_by_role('button', name='Retry').click()
    after = len([m for m in panel.posted() if m == {'v': 2, 'type': 'load', 'view': 'decisions'}])
    assert after == before + 1
    assert card(panel).count() == 1, 'Now still works from the summary'
    panel.view_data('decisions', decisions('decisions.binary'), revision=25)
    assert history.locator('[data-updating]').inner_text() == 'Updating...'
    assert_clean(panel)


# --- modes, navigation ----------------------------------------------------------------------------

def test_reviewer_mode_renders_no_answer_control(open_panel, binary, decisions):
    panel = opened(open_panel, binary, reviewer=True, stage='v2')
    page = panel.page
    history = open_history(panel, 'policy')
    panel.view_data('decisions', decisions('decisions.binary.reconfirm'), revision=26)
    assert page.locator('textarea').count() == 0
    assert page.locator('#main [data-write]').count() == 0
    assert card(panel).locator('[data-answer-in-chat]').count() == 1
    assert page.locator('[data-block="now"] [data-copy-question="policy"]').count() == 1, 'the agent bridge stays'
    assert history.locator('[data-history-row]').count() > 0
    assert_clean(panel)


def test_navigate_to_now_and_to_a_step_focuses_its_heading(open_panel, binary):
    """NAV-1: the controller turns a decision link into `now` (an open proposal) or
    `path:<decision>`; the page focuses that place's heading."""
    panel = opened(open_panel, binary)
    page = panel.page
    panel.send({'type': 'navigate', 'anchor': 'now', 'kind': 'decision', 'id': 'policy'})
    assert page.evaluate('document.activeElement.id') == 'ht-now-h'
    panel.send({'type': 'navigate', 'anchor': 'path:split', 'kind': 'decision', 'id': 'split'})
    assert page.evaluate('document.activeElement.closest("[data-anchor]").dataset.anchor') == 'path:split'
    assert_clean(panel)


# --- DC-13 → NOW-4 (R16, D20): the choice the chat waits for, on an engine before P1 ----------------

CHOICES = [{'id': 'adopt_policy', 'value': 'adopt_policy', 'label': 'Adopt the rule'},
           {'id': 'keep_baseline', 'value': 'keep_baseline', 'label': 'Keep the baseline'},
           {'id': 'inconclusive', 'value': 'inconclusive', 'label': 'Do not conclude (inconclusive)'}]


def choice_summary(model, payload, options=CHOICES, step='conclusion'):
    raw = copy.deepcopy(payload('captured/summary.binary.cv.opening'))
    raw['open_proposals'] = []
    raw['next_action'] = {'kind': 'propose', 'step': step, 'decision': step,
                          'message': f'Propose the {step}.', 'audience': 'agent',
                          'junior_message': 'Choose in the chat.', 'choice_options': options}
    return model('summary', raw)


@pytest.mark.parametrize('stage', ['v0', 'v1', 'v2', 'v3'])
def test_dc13_now4_a_choice_the_chat_waits_for_lists_the_options_as_text(open_panel, model, payload, stage):
    """DC-13 (R16) → NOW-4: before any proposal, Now lists the engine's options under "Answers
    offered in the chat" as plain text (HON-9: from `next_action.choice_options` on an engine
    before P1); no control but "Copy the question", no field, no write."""
    panel = opened(open_panel, choice_summary(model, payload), stage=stage)
    page = panel.page
    now = page.locator('[data-block="now"]')
    assert now.get_attribute('data-now-step') == 'conclusion'
    options = now.locator('[data-options] [data-option]')
    assert options.all_inner_texts() == [o['label'] for o in CHOICES]
    assert options.locator('button, [data-write]').count() == 0
    assert now.locator('textarea, input, select, [data-write]').count() == 0
    assert [b.get_attribute('data-copy-question') for b in now.locator('button').all() if b.get_attribute('data-copy-question')] == ['conclusion']
    now.locator('[data-copy-question="conclusion"]').click()
    assert page.locator('[role="dialog"]').count() == 0
    assert panel.posted()[-1] == {'v': 2, 'type': 'ask_agent', 'about': {'kind': 'step', 'id': 'conclusion'},
                                  'question': page.evaluate('() => globalThis.Hypotrail.copy.page.askQuestions.conclusion'),
                                  'mode': 'copy'}
    assert not any(m['type'] in ('confirm', 'withdraw', 'propose', 'run') for m in panel.posted())
    assert_clean(panel)


def test_dc13_the_options_keep_the_engine_labels_in_french(open_panel, model, payload):
    """The page's words follow the panel language; the options keep the engine's labels."""
    options = [{'id': 'fit.logistic', 'value': 'fit.logistic', 'label': 'Le modèle logistique'},
               {'id': 'fit.variant:2', 'value': 'fit.variant:2', 'label': 'La deuxième variante · boosting explicable'}]
    from panel_cases import set_language
    panel = opened(open_panel, choice_summary(model, payload, options, step='model_choice'), stage='v3')
    set_language(panel.page, 'fr')
    now = panel.page.locator('[data-block="now"]')
    assert now.locator('[data-option]').all_inner_texts() == [o['label'] for o in options]
    assert now.locator('[data-options]').get_attribute('aria-label').startswith('Réponses proposées dans le chat')
    assert_clean(panel)
