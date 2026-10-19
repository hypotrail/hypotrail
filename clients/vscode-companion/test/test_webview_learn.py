"""Browser tests of the Learn & hand off view and the agent bridge (scope S, simulated browser;
WP-U5; COMPANION-ADVANCED §6.6, §6.7, §6.8, §10, §13). The real document under the real CSP,
offline, with the stub ``acquireVsCodeApi`` of conftest.py, in both colour schemes, on the
binary (Bank) and regression (Auto MPG) fixtures. Not a VS Code session: the clipboard, the
chat, the folder dialog and globalState are the extension's, tested in test/learn.test.js
and test/bridge.test.js.
"""
from __future__ import annotations

import copy
import json
import re

import pytest

expect = pytest.importorskip('playwright.sync_api').expect

FORBIDDEN = re.compile(r'\b(threshold|capacity|precision|recall|positive class|policy|calling rule|selected)\b', re.I)
EMPTY = {'prefs': {'hideCards': False}, 'seen': {}, 'predictions': {}}


@pytest.fixture(scope='module')
def fixtures(model):
    return {
        'binary': model('summary', 'summary.binary'),
        'regression': model('summary', 'summary.regression'),
        'explain.binary': model('explain', 'explain.binary'),
        'explain.regression': model('explain', 'explain.regression'),
        'report': model('session_report', 'session_report.binary'),
    }


def _send(panel, message: dict) -> None:
    """Post a message and wait until the frame has handled (and rendered) it."""
    panel.page.evaluate("""m => new Promise(resolve => {
      window.addEventListener('message', () => setTimeout(resolve, 0), {once: true});
      window.postMessage(m, '*');
    })""", {'v': 2, **message})


def _init(panel, stage='v3', reviewer=False, learningLayer=True, chatInsert=False, task=None):  # noqa: N803
    _send(panel, {'type': 'init', 'stage': stage, 'reviewer': reviewer, 'learningLayer': learningLayer,
                  'chatInsert': chatInsert, 'task': task})


def _snapshot(panel, model):
    _send(panel, {'type': 'snapshot', 'revision': model['revision'], 'model': model})


def _view_data(panel, view, model):
    _send(panel, {'type': 'view_data', 'view': view, 'revision': model.get('revision', 0), 'model': model})


def _open(open_panel, fixtures, task='binary', scheme='light', learn=EMPTY, explain=True, **init):
    panel = open_panel(color_scheme=scheme)
    _init(panel, stage='v3', task=task, **init)
    _snapshot(panel, fixtures[task])
    _send(panel, {'type': 'learn_state', **learn})
    panel.page.locator('[role="tab"][data-tab="learn"]').click()
    if explain:
        _view_data(panel, 'explain', fixtures[f'explain.{task}'])
    return panel


def _posted(panel, type_):
    return [m for m in panel.posted() if m['type'] == type_]


def _probe_term(page, term_id):
    """A word of another view's copy, marked like media/terms.js marks it."""
    page.evaluate("""id => { const s = globalThis.Hypotrail.terms.mark('the word', id); s.id = 'probe-term';
      document.querySelector('[data-view="learn"]').appendChild(s); }""", term_id)
    page.wait_for_timeout(50)
    return page.locator('#probe-term')


@pytest.mark.parametrize('scheme', ['light', 'dark'])
@pytest.mark.parametrize('task', ['binary', 'regression'])
def test_learn_tab_renders_cards_predictions_handoff_and_report_offline(open_panel, fixtures, scheme, task):
    panel = _open(open_panel, fixtures, task=task, scheme=scheme)
    page = panel.page
    learn = page.locator('#panel-learn')
    assert learn.locator('h2').first.inner_text() == 'Learn & hand off'
    assert _posted(panel, 'load')[-1] == {'v': 2, 'type': 'load', 'view': 'explain'}
    step = fixtures[task]['currentStep']['id']
    card = learn.locator(f'[data-concept-card="{task}:{step}"]')
    assert card.count() == 1
    assert card.get_attribute('data-nav') == f'step:{step}'
    assert 'Concept card, not a decision' in card.text_content()        # INV-6
    assert learn.locator('[data-prediction]').count() >= 1
    for box in learn.locator('[data-prediction]').all():
        assert box.locator('.ht-tag').first.text_content() == 'Optional · before you look'
        assert 'Kept on this computer only. Never written to the study.' in box.inner_text()
    assert learn.locator('[data-write="export"]').inner_text() == 'Export a handoff pack'
    assert learn.locator('[data-reviewer-line]').count() == 1
    assert learn.locator('details[data-session-report] > summary').inner_text() == 'Session report (for an observed session)'
    assert page.locator('[style]').count() == 0, 'no inline style attribute (CSP)'
    if task == 'regression':
        text = page.locator('body').inner_text()
        assert not FORBIDDEN.search(text), FORBIDDEN.search(text).group(0)
    assert panel.clean(), (panel.requests, panel.errors, panel.csp, panel.violations())


def test_concept_card_puts_the_term_first_then_its_definition_and_the_study_texts(open_panel, fixtures):
    explain = copy.deepcopy(fixtures['explain.binary'])
    explain['terms']['base_rate']['steps'] = ['conclusion']           # a term whose concept is the current step
    panel = _open(open_panel, fixtures, explain=False)
    _view_data(panel, 'explain', explain)
    card = panel.page.locator('[data-concept-card="binary:conclusion"]')
    heading = card.locator('h3')
    assert heading.inner_text() == 'Base rate'
    assert heading.locator('[data-term="base_rate"]').count() == 1
    order = card.locator(':scope > *').evaluate_all('ns => ns.map(n => n.tagName + ":" + n.textContent)')
    assert order[0] == 'P:Concept card, not a decision'
    assert order[1] == 'H3:Base rate', 'the term first'
    assert order[2] == 'P:' + explain['terms']['base_rate']['definition'], 'then its definition'
    assert order[3] == 'P:Step: Conclude proportionately'
    for key in ('concept', 'context', 'interpretation', 'consequence'):
        segment_text = ''.join(s['text'] for s in explain['steps']['conclusion'][key])
        assert segment_text in card.inner_text(), key
    assert panel.clean()


def test_le2_a_card_seen_for_two_seconds_is_counted_once_and_collapses_after_two_sightings(open_panel, fixtures):
    # No fixed sleep: Playwright's fake clock, installed before the panel renders, drives the
    # two seconds; `data-seen-timing` says when the card's timer is armed (a test hook, §16),
    # and the clock is paused from then on, so only run_for moves it.
    def clocked(color_scheme='light'):
        p = open_panel(color_scheme)
        p.page.clock.install()
        return p
    panel = _open(clocked, fixtures)
    page = panel.page
    card = page.locator('[data-concept-card="binary:conclusion"]')
    if page.evaluate("() => document.querySelector('[data-concept-card]').getBoundingClientRect().bottom > innerHeight"):
        page.clock.run_for(2300)
        assert page.locator('[data-seen-timing]').count() == 0
        assert not [m for m in _posted(panel, 'learn_set') if m['key'] == 'seen'], 'a card partly out of view is not seen'
    card.scroll_into_view_if_needed()
    page.locator('[data-concept-card="binary:conclusion"][data-seen-timing]').wait_for()
    page.clock.pause_at((page.evaluate('() => Date.now()') + 1) / 1000)   # seconds in the Python API
    page.clock.run_for(1500)
    assert not [m for m in _posted(panel, 'learn_set') if m['key'] == 'seen'], 'not before two seconds'
    page.clock.run_for(600)
    seen = [m for m in _posted(panel, 'learn_set') if m['key'] == 'seen']
    assert seen == [{'v': 2, 'type': 'learn_set', 'key': 'seen', 'id': 'binary:conclusion'}]
    page.clock.resume()   # a paused clock also holds the page's message handling
    _send(panel, {'type': 'learn_state', **{**EMPTY, 'seen': {'binary:conclusion': 1}}})
    page.clock.run_for(5000)
    assert page.locator('[data-seen-timing]').count() == 0, 'counted: no new timer'
    assert len([m for m in _posted(panel, 'learn_set') if m['key'] == 'seen']) == 1, 'not counted twice in one panel session'
    assert page.locator('[data-concept-card="binary:conclusion"]').count() == 1, 'one sighting: still open'
    # The stored count is 2 (a reload reads it from globalState): one line, then open on demand.
    _send(panel, {'type': 'learn_state', **{**EMPTY, 'seen': {'binary:conclusion': 2}}})
    link = page.locator('[data-concept-card-link="binary:conclusion"] button')
    assert link.inner_text() == 'Show the concept: Conclude proportionately'
    assert page.locator('[data-concept-card="binary:conclusion"]').count() == 0
    link.click()
    assert page.locator('[data-concept-card="binary:conclusion"]').count() == 1
    # "Hide concept cards" is a preference, sent as learn_set prefs.
    page.locator('[data-hide-cards="true"]').click()
    assert _posted(panel, 'learn_set')[-1] == {'v': 2, 'type': 'learn_set', 'key': 'prefs', 'id': 'prefs', 'value': {'hideCards': True}}
    _send(panel, {'type': 'learn_state', **{**EMPTY, 'prefs': {'hideCards': True}}})
    assert page.locator('[data-concept-card], [data-concept-card-link]').count() == 0
    assert page.locator('[data-cards-hidden]').count() == 1
    assert panel.clean()


def test_predict_before_you_look_stores_locally_then_reveals(open_panel, fixtures):
    panel = _open(open_panel, fixtures)
    page = panel.page
    box = page.locator('[data-prediction="binary.train_eda.rare"]')
    assert box.locator('.ht-question').inner_text() == 'Is the positive outcome common or rare in the training rows?'
    assert box.locator('[data-reveal]').count() == 0, 'no reveal before an answer'
    box.locator('[data-choice="rare"]').click()
    sent = _posted(panel, 'learn_set')[-1]
    assert sent == {'v': 2, 'type': 'learn_set', 'key': 'prediction', 'id': 'binary.train_eda.rare', 'value': 'rare'}
    # The answer travels only as learn_set (LE-1): no other message carries it.
    assert all('rare' not in json.dumps(m) for m in panel.posted() if m['type'] != 'learn_set')
    _send(panel, {'type': 'learn_state', **{**EMPTY, 'predictions': {'binary.train_eda.rare': 'rare',
                                                                    'binary.policy.beats_baseline': 'yes'}}})
    box = page.locator('[data-prediction="binary.train_eda.rare"]')
    assert box.locator('[data-answer]').inner_text() == 'Your answer: Rare'
    reveal = box.locator('[data-reveal="shown"]')
    cited = reveal.locator('data[data-result-id]')
    assert cited.inner_text() == '11.5%'
    assert cited.get_attribute('data-result-id') == '744b2d1cffbbdb905b9492fca6de249283b2144d61faaeeab794134ae0878db8'
    later = page.locator('[data-prediction="binary.policy.beats_baseline"] [data-reveal="later"]')
    assert 'The answer appears once the engine has computed it.' in later.inner_text()
    page.locator('[data-reset-predictions]').click()
    assert _posted(panel, 'learn_set')[-1] == {'v': 2, 'type': 'learn_set', 'key': 'reset_predictions', 'id': 'study'}
    assert panel.clean()


def test_le4_glossary_tooltip_on_focus_and_hover_term_first_with_the_cited_example_escape_closes(open_panel, fixtures):
    panel = _open(open_panel, fixtures)
    page = panel.page
    term = _probe_term(page, 'base_rate')
    assert 'ht-term' in term.get_attribute('class')
    term.focus()
    tip = page.locator('[role="tooltip"]')
    assert tip.count() == 1
    assert term.get_attribute('aria-describedby') == tip.get_attribute('id')
    assert tip.locator('strong').inner_text() == 'Base rate'
    children = tip.locator('[data-tooltip-term] > *').evaluate_all('ns => ns.map(n => n.tagName)')
    assert children[0] == 'STRONG', 'the term comes first'
    assert tip.locator('data[data-result-id]').inner_text() == '11.5%'
    page.keyboard.press('Escape')
    assert page.locator('[role="tooltip"]').count() == 0
    term.blur()
    term.hover()
    assert page.locator('[role="tooltip"]').count() == 1
    # A term outside this task's glossary is not marked.
    other = page.evaluate("""() => { const s = globalThis.Hypotrail.terms.mark('mae', 'mae'); s.id = 'probe-mae';
      document.querySelector('[data-view="learn"]').appendChild(s); return s.id; }""")
    page.wait_for_timeout(50)
    assert page.locator(f'#{other}').get_attribute('class') is None
    assert page.locator(f'#{other}').get_attribute('aria-describedby') is None
    # The intro's own marked term (confirmed_decision) has a tooltip too.
    assert page.locator('#panel-learn [data-term="confirmed_decision"].ht-term').count() == 1
    assert panel.clean()


def test_le3_learning_layer_off_renders_no_tooltip_card_or_prediction_and_never_loads_explain(open_panel, fixtures):
    panel = _open(open_panel, fixtures, explain=False, learningLayer=False)
    page = panel.page
    term = _probe_term(page, 'base_rate')
    term.hover()
    page.wait_for_timeout(100)
    assert not any(m.get('view') == 'explain' for m in _posted(panel, 'load')), 'no explain call'
    _view_data(panel, 'explain', fixtures['explain.binary'])           # even if data arrived
    assert page.locator('[role="tooltip"], .ht-term, [data-concept-card], [data-prediction], [data-learning-layer]').count() == 0
    assert page.locator('[data-write="export"]').count() == 1, 'the hand off stays'
    assert panel.clean()


def test_the_first_hover_of_a_term_in_another_tab_reads_explain_once(open_panel, fixtures):
    panel = open_panel()
    _init(panel, stage='v3', task='binary')
    _snapshot(panel, fixtures['binary'])
    page = panel.page
    page.evaluate("""() => { const s = globalThis.Hypotrail.terms.mark('base rate', 'base_rate'); s.id = 'probe-term';
      document.querySelector('#panel-overview').appendChild(s); }""")
    page.locator('#probe-term').hover()
    page.locator('#probe-term').hover()
    assert [m for m in _posted(panel, 'load') if m['view'] == 'explain'] == [{'v': 2, 'type': 'load', 'view': 'explain'}]
    assert panel.clean()


def test_ho1_export_button_outcome_files_open_folder_and_the_stale_report(open_panel, fixtures, payload):
    panel = _open(open_panel, fixtures)
    page = panel.page
    page.locator('[data-write="export"]').click()
    assert _posted(panel, 'export_handoff')[-1] == {'v': 2, 'type': 'export_handoff', 'revision': 26}
    out = payload('export.binary')['out']
    files = [{'path': f['path'], 'bytes': f['bytes']} for f in payload('export.binary')['files']]
    _send(panel, {'type': 'busy', 'busy': True, 'op': 'W7', 'target': 'handoff'})
    button = page.locator('[data-write="export"]')
    expect(button).to_have_attribute('aria-busy', 'true')
    assert button.is_disabled() and button.inner_text() == 'Working...'
    _send(panel, {'type': 'busy', 'busy': False, 'op': 'W7', 'target': 'handoff'})
    _send(panel, {'type': 'outcome', 'op': 'W7', 'kind': 'ok', 'target': 'handoff', 'exitCode': 0, 'revision': 26,
                'artifacts': [], 'recorded': {'files': files, 'out': out,
                                              'warnings': ['some proposals are still open', 'some decisions are not confirmed']}})
    region = page.locator('[data-export-outcome="ok"]')
    assert 'Exported the handoff pack.' in region.inner_text()
    # WP-I (U5 request R3): the warnings of the outcome, in words, with the files.
    assert region.locator('[data-export-warnings]').inner_text() == (
        'The pack is incomplete: some proposals are still open; some decisions are not confirmed.')
    assert region.locator('[data-export-files] li').all_inner_texts()[0] == 'handoff.md · 8213 bytes'
    assert region.locator('[data-export-out]').inner_text() == f'Folder: {out}'
    region.locator('[data-open-export]').click()
    assert _posted(panel, 'navigate_external')[-1] == {'v': 2, 'type': 'navigate_external', 'kind': 'reveal_export', 'path': out}
    assert page.locator('#outcome [data-outcome]').count() == 0, 'the view renders its own W7 outcome'
    _send(panel, {'type': 'outcome', 'op': 'W7', 'kind': 'ok_with_problems', 'target': 'handoff', 'exitCode': 3, 'revision': 26,
                'artifacts': [], 'recorded': {'files': files[:2] + files[3:], 'out': out}})
    assert page.locator('[data-export-stale-report]').inner_text() == (
        'The report was not current, so it is not in the pack. Regenerate it in Overview and export again if you need it.')
    error = payload('error.export_target_exists')['error']
    _send(panel, {'type': 'outcome', 'op': 'W7', 'kind': 'refused', 'target': 'handoff', 'exitCode': 2,
                'refusal': {'code': error['code'], 'reason': None, 'engineMessage': error['message'],
                            'human': 'The export folder already holds files.', 'details': []}})
    refused = page.locator('[data-export-outcome="refused"] [data-outcome="refused"]')
    assert refused.get_attribute('data-code') == 'export_target_exists'
    assert refused.locator('[data-engine-message]').inner_text() == error['message']
    assert page.locator('[data-open-export]').count() == 0
    assert panel.clean()


def test_ho2_reviewer_keeps_only_the_export_write_and_the_bridge(open_panel, fixtures):
    panel = _open(open_panel, fixtures, reviewer=True)
    page = panel.page
    assert page.locator('[data-write]').evaluate_all('ns => ns.map(n => n.dataset.write)') == ['export']   # CA.9
    assert page.locator('[data-reviewer-line]').inner_text() == (
        'A reviewer can open this study read-only with "Hypotrail: open the study panel (reviewer, read-only)".')
    assert page.locator('[data-ask]').count() >= 1, 'the agent bridge stays in reviewer mode'
    assert page.locator('textarea').count() == 0
    assert panel.clean()


def test_sr1_session_report_shows_the_log_status_and_no_conversation_content(open_panel, fixtures, payload, model):
    panel = _open(open_panel, fixtures)
    page = panel.page
    report = page.locator('details[data-session-report]')
    assert not any(m.get('view') == 'session_report' for m in _posted(panel, 'load')), 'read only when expanded'
    report.locator('summary').click()
    page.wait_for_function("() => window.__posted.some(m => m.type === 'load' && m.view === 'session_report')")
    assert _posted(panel, 'load')[-1] == {'v': 2, 'type': 'load', 'view': 'session_report'}
    assert 'Reading the session report...' in report.inner_text()
    _view_data(panel, 'session_report', fixtures['report'])
    report = page.locator('details[data-session-report]')
    assert report.get_attribute('open') is not None
    assert report.locator('[data-session-log]').inner_text() == 'Session log: on'
    text = report.inner_text()
    words = set()
    for name in ('summary.binary', 'decisions.binary', 'decisions.binary.injection', 'handoff.binary'):
        def walk(v):
            if isinstance(v, dict):
                for k, x in v.items():
                    if k in ('user_words', 'restatement', 'rationale') and isinstance(x, str) and x:
                        words.add(x)
                    walk(x)
            elif isinstance(v, list):
                for x in v:
                    walk(x)
        walk(payload(name))
    assert len(words) >= 5
    for w in words:
        assert w not in text, w
    assert 'Pause 3: still open' in text and 'policy (p_5): open' in text
    # Log off: the status, the engine note verbatim, and the instruction verbatim.
    raw = copy.deepcopy(payload('session_report.binary'))
    note = ('The session log is off: refusals, status reads, check runs, and previews were not recorded. '
            'Enable it before a session with HYPOTRAIL_SESSION_LOG=1.')
    raw['sources']['session_log'] = {'enabled': False, 'entries': 0, 'path': '.hypotrail/session-log.jsonl', 'note': note}
    _view_data(panel, 'session_report', model('session_report', raw))
    report = page.locator('details[data-session-report]')
    assert report.locator('[data-session-log]').inner_text() == 'Session log: off'
    assert report.locator('[data-session-log-note]').inner_text() == note
    assert report.locator('[data-session-log-instruction]').inner_text() == (
        'Start the CLI once with HYPOTRAIL_SESSION_LOG=1 to turn it on; delete .hypotrail/session-log.jsonl to turn it off.')
    assert not any(m['type'] not in ('ready', 'load', 'learn_set') for m in panel.posted()), 'the panel turns nothing on or off'
    assert panel.clean()


@pytest.mark.parametrize('chat_insert', [False, True])
def test_ab_ask_the_agent_modal_sends_only_the_cited_object_and_the_question(open_panel, fixtures, chat_insert):
    panel = _open(open_panel, fixtures, chatInsert=chat_insert)
    page = panel.page
    # Draft confirmation words typed in a decision card stay in that card (AB-1).
    page.locator('[role="tab"][data-tab="decisions"]').click()
    draft = 'Yes: call the 100 best-scored clients, DRAFT-WORDS-XYZ.'
    page.locator('[data-proposal-card="p_5"] textarea').fill(draft)
    page.locator('[role="tab"][data-tab="learn"]').click()
    page.locator('[data-concept-card="binary:conclusion"] [data-ask="step:conclusion"]').click()
    dialog = page.locator('[role="dialog"]')
    assert dialog.locator('h2').inner_text() == 'Ask the agent'
    assert dialog.locator('[data-ask-about]').inner_text() == 'step conclusion (Conclude proportionately)'
    area = dialog.locator('textarea')
    assert area.input_value() == '', 'the question starts empty'
    labels = dialog.locator('[data-modal-action]').all_inner_texts()
    assert labels == (['Copy for the chat', 'Insert into the chat'] if chat_insert else ['Copy for the chat'])
    area.fill('Why is this step needed?')
    dialog.locator('[data-modal-action="copy"]').click()
    ask = _posted(panel, 'ask_agent')[-1]
    assert ask == {'v': 2, 'type': 'ask_agent', 'about': {'kind': 'step', 'id': 'conclusion'},
                   'question': 'Why is this step needed?', 'mode': 'copy'}
    assert all(draft not in json.dumps(m) for m in panel.posted() if m['type'] != 'confirm'), 'draft words never sent'
    assert 'askDraft' not in (panel.state() or {}), 'the question is not kept for another object'
    assert page.locator('[role="dialog"]').count() == 0
    if chat_insert:
        page.locator('[data-ask="step:conclusion"]').click()
        page.locator('[role="dialog"] [data-modal-action="insert"]').click()
        assert _posted(panel, 'ask_agent')[-1]['mode'] == 'insert'
    _send(panel, {'type': 'notice', 'text': 'Copied. Paste it into the chat with your assistant.', 'politeness': 'polite'})
    assert page.locator('[data-notice]').inner_text() == 'Copied. Paste it into the chat with your assistant.'
    assert panel.clean()


def test_the_learn_tab_is_absent_below_v3_and_the_bridge_below_v2(open_panel, fixtures):
    panel = open_panel()
    _init(panel, stage='v2', task='binary')
    _snapshot(panel, fixtures['binary'])
    page = panel.page
    assert page.locator('[data-tab="learn"]').count() == 0
    assert page.evaluate("() => globalThis.Hypotrail.askButton({atLeast: s => s !== 'v3'}, {kind: 'step', id: 'x'}, '') !== null")
    assert page.evaluate("() => globalThis.Hypotrail.askButton({atLeast: s => s === 'v0' || s === 'v1'}, {kind: 'step', id: 'x'}, '')") is None
    assert panel.clean()


def test_cr1_a_failed_explain_read_has_retry_and_is_asked_again_at_the_next_currency(open_panel, fixtures):
    panel = _open(open_panel, fixtures, explain=False)
    page = panel.page
    asked = lambda: [m for m in _posted(panel, 'load') if m['view'] == 'explain']
    n = len(asked())
    assert n >= 1
    _send(panel, {'type': 'load_error', 'view': 'explain', 'message': 'The hypotrail CLI failed.', 'detail': ''})
    _snapshot(panel, fixtures['binary'])
    assert len(asked()) == n, 'no loop at the same version'
    page.locator('[data-retry="explain"]').click()
    assert len(asked()) == n + 1, 'Retry asks again'
    _send(panel, {'type': 'load_error', 'view': 'explain', 'message': 'The hypotrail CLI failed.', 'detail': ''})
    _send(panel, {'type': 'snapshot', 'revision': fixtures['binary']['revision'], 'currency': '00000000000000ee',
                  'model': {**fixtures['binary'], 'currency': '00000000000000ee'}})
    assert len(asked()) == n + 2, 'a new currency asks again'
    assert panel.clean()
