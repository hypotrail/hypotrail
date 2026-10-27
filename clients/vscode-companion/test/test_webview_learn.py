"""Browser tests of the learning layer, the hand-off and the agent bridge on the one page (scope S,
simulated browser; WP-U5 re-pointed by ADR 0004 d13; COMPANION-ADVANCED §6.7.3, §6.7.4, §6.12,
§A.6, §10, §13). The Learn tab became: the concept cards in the My notions drawer (LE-2, kept
by the integrator's correction of 2026-10-27), "predict before you look" in Now at its step
(LE-1), the export and the session report in the Deliverables drawer (HO-1, HO-2, SR-1). The
glossary tooltips are withdrawn with their test: a marked term is a notion that expands in
place (LE-4 → NOT-2, `test_webview_tools.py`).

The real document under the real CSP, offline, with the stub ``acquireVsCodeApi`` of
conftest.py, in both colour schemes, on the binary (Bank) and regression (Auto MPG) WP-0
fixtures. Not a VS Code session: the clipboard, the chat, the folder dialog and globalState are
the extension's, tested in test/learn.test.js and test/bridge.test.js.
"""
from __future__ import annotations

import copy
import json
import re

import pytest

from conftest import inline_styles_ok
from panel_cases import click_fold

expect = pytest.importorskip('playwright.sync_api').expect

FORBIDDEN = re.compile(r'\b(threshold|capacity|precision|recall|positive class|policy|calling rule|decision rule|selected)\b', re.I)
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
                  'chatInsert': chatInsert, 'task': task, 'panelContract': 2})


def _snapshot(panel, model):
    _send(panel, {'type': 'snapshot', 'revision': model['revision'], 'model': model})


def _view_data(panel, view, model):
    _send(panel, {'type': 'view_data', 'view': view, 'revision': model.get('revision', 0), 'model': model})


def _open(open_panel, fixtures, task='binary', scheme='light', learn=EMPTY, explain=True, summary=None, **init):
    """The page at v3 with My notions open (it reads `explain`)."""
    panel = open_panel(color_scheme=scheme)
    _init(panel, stage='v3', task=task, **init)
    _snapshot(panel, summary or fixtures[task])
    _send(panel, {'type': 'learn_state', **learn})
    if init.get('learningLayer', True):
        click_fold(panel.page, 't-notions')
    if explain:
        _view_data(panel, 'explain', fixtures[f'explain.{task}'])
    return panel


def _posted(panel, type_):
    return [m for m in panel.posted() if m['type'] == type_]


def _concept_title(explain, step, plan):
    """The card's title: the first glossary term of the step, else the step's title."""
    order = explain.get('termOrder') or list(explain['terms'])
    term = next((explain['terms'][t]['term'] for t in order if step in (explain['terms'][t].get('steps') or [])), None)
    return term or next(s['title'] for s in plan if s['id'] == step)


def _at_train_eda(fixtures):
    """The Bank study while its exploration runs: Now's step is `train_eda`."""
    s = copy.deepcopy(fixtures['binary'])
    s['proposals'] = []
    s['nextAction'] = {**s['nextAction'], 'kind': 'run', 'step': 'train_eda', 'decision': None, 'proposalId': None,
                       'activity': 'eda.target_rate'}
    return s


@pytest.mark.parametrize('scheme', ['light', 'dark'])
@pytest.mark.parametrize('task', ['binary', 'regression'])
def test_the_learning_parts_render_cards_predictions_handoff_and_report_offline(open_panel, fixtures, scheme, task):
    panel = _open(open_panel, fixtures, task=task, scheme=scheme)
    page = panel.page
    assert {'v': 2, 'type': 'load', 'view': 'explain'} in _posted(panel, 'load')
    step = page.locator('[data-block="now"]').get_attribute('data-now-step')
    card = page.locator(f'[data-drawer="notions"] [data-concept-card="{task}:{step}"]')
    assert card.count() == 1
    assert card.get_attribute('data-nav') == f'step:{step}'
    assert 'Concept card, not a decision' in card.text_content()        # INV-6
    boxes = page.locator('[data-block="now"] [data-prediction]')
    assert boxes.count() == (1 if task == 'binary' else 0), 'the prediction of Now\'s step only'
    for box in boxes.all():
        assert box.locator('.ht-tag').first.text_content() == 'Optional · before you look'
        assert 'Kept on this computer only. Never written to the study.' in box.inner_text()
    click_fold(page, 't-deliverables')
    tools = page.locator('[data-drawer="deliverables"]')
    assert tools.locator('[data-write="export"]').inner_text() == 'Export a handoff pack'
    assert tools.locator('[data-reviewer-line]').count() == 1
    assert tools.locator('details[data-session-report] > summary').inner_text() == 'Session report (for an observed session)'
    assert inline_styles_ok(page), 'no inline style attribute (CSP)'
    if task == 'regression':
        text = page.locator('body').inner_text()
        assert not FORBIDDEN.search(text), FORBIDDEN.search(text).group(0)
    assert panel.clean(), (panel.requests, panel.errors, panel.csp, panel.violations())


def test_concept_card_puts_the_term_first_then_its_definition_and_the_study_texts(open_panel, fixtures):
    explain = copy.deepcopy(fixtures['explain.binary'])
    explain['terms']['base_rate']['steps'] = ['policy']           # a term whose concept is Now's step
    order = explain.get('termOrder') or list(explain['terms'])
    for t in order:
        if t != 'base_rate':
            explain['terms'][t]['steps'] = [s for s in (explain['terms'][t].get('steps') or []) if s != 'policy']
    panel = _open(open_panel, fixtures, explain=False)
    _view_data(panel, 'explain', explain)
    card = panel.page.locator('[data-concept-card="binary:policy"]')
    heading = card.locator('h3')
    assert heading.inner_text() == 'Base rate'
    assert heading.locator('[data-term="base_rate"]').count() == 1
    order = card.locator(':scope > *').evaluate_all('ns => ns.map(n => n.tagName + ":" + n.textContent)')
    assert order[0] == 'P:Concept card, not a decision'
    assert order[1] == 'H3:Base rate', 'the term first'
    assert order[2] == 'P:' + explain['terms']['base_rate']['definition'], 'then its definition'
    assert order[3] == 'P:Step: Choose a decision policy'
    for key in ('concept', 'context', 'interpretation', 'consequence'):
        segment_text = ''.join(s['text'] for s in explain['steps']['policy'][key])
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
    card_id = 'binary:policy'
    card = page.locator(f'[data-concept-card="{card_id}"]')
    if page.evaluate("() => document.querySelector('[data-concept-card]').getBoundingClientRect().bottom > innerHeight"):
        page.clock.run_for(2300)
        assert page.locator('[data-seen-timing]').count() == 0
        assert not [m for m in _posted(panel, 'learn_set') if m['key'] == 'seen'], 'a card partly out of view is not seen'
    card.scroll_into_view_if_needed()
    page.locator(f'[data-concept-card="{card_id}"][data-seen-timing]').wait_for()
    # Pause a little ahead of now: the clock still runs between the read and the pause, and
    # pausing at a time it has already passed is refused ("Cannot fast-forward to the past").
    page.clock.pause_at((page.evaluate('() => Date.now()') + 100) / 1000)   # seconds in the Python API
    page.clock.run_for(1500)
    assert not [m for m in _posted(panel, 'learn_set') if m['key'] == 'seen'], 'not before two seconds'
    page.clock.run_for(600)
    seen = [m for m in _posted(panel, 'learn_set') if m['key'] == 'seen']
    assert seen == [{'v': 2, 'type': 'learn_set', 'key': 'seen', 'id': card_id}]
    page.clock.resume()   # a paused clock also holds the page's message handling
    _send(panel, {'type': 'learn_state', **{**EMPTY, 'seen': {card_id: 1}}})
    page.clock.run_for(5000)
    assert page.locator('[data-seen-timing]').count() == 0, 'counted: no new timer'
    assert len([m for m in _posted(panel, 'learn_set') if m['key'] == 'seen']) == 1, 'not counted twice in one panel session'
    assert page.locator(f'[data-concept-card="{card_id}"]').count() == 1, 'one sighting: still open'
    # The stored count is 2 (a reload reads it from globalState): one line, then open on demand.
    _send(panel, {'type': 'learn_state', **{**EMPTY, 'seen': {card_id: 2}}})
    link = page.locator(f'[data-concept-card-link="{card_id}"] button')
    title = _concept_title(fixtures['explain.binary'], 'policy', fixtures['binary']['plan'])
    assert link.inner_text() == f'Show the concept: {title}'
    assert page.locator(f'[data-concept-card="{card_id}"]').count() == 0
    link.click()
    assert page.locator(f'[data-concept-card="{card_id}"]').count() == 1
    # "Hide concept cards" is a preference, sent as learn_set prefs.
    page.locator('[data-hide-cards="true"]').click()
    assert _posted(panel, 'learn_set')[-1] == {'v': 2, 'type': 'learn_set', 'key': 'prefs', 'id': 'prefs', 'value': {'hideCards': True}}
    _send(panel, {'type': 'learn_state', **{**EMPTY, 'prefs': {'hideCards': True}}})
    assert page.locator('[data-concept-card], [data-concept-card-link]').count() == 0
    assert page.locator('[data-cards-hidden]').count() == 1
    assert panel.clean()


def test_le1_predict_before_you_look_in_now_stores_locally_then_reveals(open_panel, fixtures):
    panel = _open(open_panel, fixtures, summary=_at_train_eda(fixtures))
    page = panel.page
    box = page.locator('[data-block="now"] [data-predict-now="train_eda"] [data-prediction="binary.train_eda.rare"]')
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
    page.locator('[data-reset-predictions]').click()
    assert _posted(panel, 'learn_set')[-1] == {'v': 2, 'type': 'learn_set', 'key': 'reset_predictions', 'id': 'study'}
    # At the rule's step, the answer given waits for the engine's figure.
    panel = _open(open_panel, fixtures, learn={**EMPTY, 'predictions': {'binary.policy.beats_baseline': 'yes'}})
    later = panel.page.locator('[data-block="now"] [data-prediction="binary.policy.beats_baseline"] [data-reveal="later"]')
    assert 'The answer appears once the engine has computed it.' in later.inner_text()
    assert panel.page.locator('[data-block="now"] [data-prediction="binary.train_eda.rare"]').count() == 0, 'Now\'s step only'
    assert panel.clean()


def test_le3_learning_layer_off_renders_no_notion_card_or_prediction_and_never_loads_explain(open_panel, fixtures):
    panel = _open(open_panel, fixtures, explain=False, learningLayer=False)
    page = panel.page
    page.wait_for_timeout(100)
    assert not any(m.get('view') == 'explain' for m in _posted(panel, 'load')), 'no explain call'
    _view_data(panel, 'explain', fixtures['explain.binary'])           # even if data arrived
    assert page.locator('.ht-term, [data-concept-card], [data-prediction], [data-learning-layer], [data-drawer="notions"]').count() == 0
    click_fold(page, 't-deliverables')
    assert page.locator('[data-write="export"]').count() == 1, 'the hand off stays'
    assert panel.clean()


def test_not1_pressing_two_notions_reads_explain_once(open_panel, fixtures):
    """NOT-1, §5: the first notion pressed reads `explain`; the next one reads nothing more."""
    panel = open_panel()
    _init(panel, stage='v3', task='binary')
    _snapshot(panel, fixtures['binary'])
    page = panel.page
    terms = page.locator('button.ht-term')
    assert terms.count() >= 1
    terms.first.click()
    page.locator('button.ht-term').last.click()
    assert [m for m in _posted(panel, 'load') if m['view'] == 'explain'] == [{'v': 2, 'type': 'load', 'view': 'explain'}]
    assert panel.clean()


def test_ho1_export_button_outcome_files_open_folder_and_the_stale_report(open_panel, fixtures, payload):
    panel = _open(open_panel, fixtures)
    page = panel.page
    click_fold(page, 't-deliverables')
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
        'The report was not current, so it is not in the pack. Regenerate it in Deliverables and export again if you need it.')
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
    click_fold(page, 't-deliverables')
    assert page.locator('[data-write]').evaluate_all('ns => ns.map(n => n.dataset.write)') == ['export']   # CA.9
    assert page.locator('[data-reviewer-line]').inner_text() == (
        'A reviewer can open this study read-only with "Hypotrail: open the study panel (reviewer, read-only)".')
    assert page.locator('[data-ask], [data-copy-question]').count() >= 1, 'the agent bridge stays in reviewer mode'
    assert page.locator('textarea').count() == 0
    assert panel.clean()


def test_sr1_session_report_shows_the_log_status_and_no_conversation_content(open_panel, fixtures, payload, model):
    panel = _open(open_panel, fixtures)
    page = panel.page
    click_fold(page, 't-deliverables')
    assert not any(m.get('view') == 'session_report' for m in _posted(panel, 'load')), 'read only when expanded'
    click_fold(page, 'session-report')
    page.wait_for_function("() => window.__posted.some(m => m.type === 'load' && m.view === 'session_report')")
    assert _posted(panel, 'load')[-1] == {'v': 2, 'type': 'load', 'view': 'session_report'}
    report = page.locator('details[data-session-report]')
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
    note = ('The session log is off: refused commands, status reads, and check runs were not recorded. '
            'Enable it before a session with HYPOTRAIL_SESSION_LOG=1.')
    raw['sources']['session_log'] = {'enabled': False, 'entries': 0, 'path': '.hypotrail/session-log.jsonl', 'note': note}
    _view_data(panel, 'session_report', model('session_report', raw))
    report = page.locator('details[data-session-report]')
    assert report.locator('[data-session-log]').inner_text() == 'Session log: off'
    assert report.locator('[data-session-log-note]').inner_text() == note
    assert report.locator('[data-session-log-instruction]').inner_text() == (
        'Start the CLI once with HYPOTRAIL_SESSION_LOG=1 to turn it on; delete .hypotrail/session-log.jsonl to turn it off.')
    assert not any(m['type'] not in ('ready', 'load', 'learn_set', 'preview_effects') for m in panel.posted()), \
        'the panel turns nothing on or off'
    assert panel.clean()


@pytest.mark.parametrize('chat_insert', [False, True])
def test_ab_ask_the_agent_modal_sends_only_the_cited_object_and_the_question(open_panel, fixtures, chat_insert):
    panel = _open(open_panel, fixtures, chatInsert=chat_insert)
    page = panel.page
    # AB-1: since WP-E1 a proposal has no words field at all; the bridge sends only the cited
    # object and the typed question.
    assert page.locator('[data-proposal-card="p_5"] textarea').count() == 0
    page.locator('[data-concept-card="binary:policy"] [data-ask="step:policy"]').click()
    dialog = page.locator('[role="dialog"]')
    assert dialog.locator('h2').inner_text() == 'Ask the agent'
    assert dialog.locator('[data-ask-about]').inner_text() == 'step policy (Choose a decision policy)'
    area = dialog.locator('textarea')
    assert area.input_value() == '', 'the question starts empty'
    labels = dialog.locator('[data-modal-action]').all_inner_texts()
    assert labels == (['Copy for the chat', 'Insert into the chat'] if chat_insert else ['Copy for the chat'])
    area.fill('Why is this step needed?')
    dialog.locator('[data-modal-action="copy"]').click()
    ask = _posted(panel, 'ask_agent')[-1]
    assert ask == {'v': 2, 'type': 'ask_agent', 'about': {'kind': 'step', 'id': 'policy'},
                   'question': 'Why is this step needed?', 'mode': 'copy'}
    assert not [m for m in panel.posted() if m['type'] in ('confirm', 'withdraw', 'propose')]
    assert 'askDraft' not in (panel.state() or {}), 'the question is not kept for another object'
    assert page.locator('[role="dialog"]').count() == 0
    if chat_insert:
        page.locator('[data-ask="step:policy"]').click()
        page.locator('[role="dialog"] [data-modal-action="insert"]').click()
        assert _posted(panel, 'ask_agent')[-1]['mode'] == 'insert'
    _send(panel, {'type': 'notice', 'text': 'Copied. Paste it into the chat with your assistant.', 'politeness': 'polite'})
    assert page.locator('[data-notice]').inner_text() == 'Copied. Paste it into the chat with your assistant.'
    assert panel.clean()


def test_my_notions_is_absent_below_v3_and_the_bridge_modal_below_v2(open_panel, fixtures):
    panel = open_panel()
    _init(panel, stage='v2', task='binary')
    _snapshot(panel, fixtures['binary'])
    page = panel.page
    assert page.locator('[data-drawer="notions"], [data-concept-card], [data-prediction], button.ht-term').count() == 0
    assert page.evaluate("() => globalThis.Hypotrail.askButton({atLeast: s => s !== 'v3'}, {kind: 'step', id: 'x'}, '') !== null")
    assert page.evaluate("() => globalThis.Hypotrail.askButton({atLeast: s => s === 'v0' || s === 'v1'}, {kind: 'step', id: 'x'}, '')") is None
    assert panel.clean()


def test_cr1_a_failed_explain_read_has_retry_and_is_asked_again_at_the_next_currency(open_panel, fixtures):
    panel = _open(open_panel, fixtures, explain=False)
    page = panel.page
    asked = lambda: [m for m in _posted(panel, 'load') if m['view'] == 'explain']  # noqa: E731
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
