"""Browser test of the companion's webview document at stage v0 (scope S, simulated browser).

The real document (``lib/html.js``) is loaded in headless Chromium, offline, with a stub
``acquireVsCodeApi`` that records the posted messages (``conftest.py``). The model is
produced by the real ``lib/models/summary.js`` from a summary. This is not a VS Code
session: VS Code's own webview host, theme variables, and message transport are not
exercised.

Migrated by WP-0 to protocol hypotrail.panel/2 (every message carries ``v: 2``, ``open``
is ``open_artifact``, an outcome names its write ``op``). Re-pointed at the one page (ADR 0004
d13): the proposal is in Now, the stale report in To handle, the limits in the defensibility
pill's popover, the deliverables in their drawer. The recap under Details went with OV-1/OV-2
(withdrawn, COMPANION-ADVANCED §18); an open note shows when the engine waits for it
(``resolve_hold``), no longer on the proposal card.

Run: ``uv run --project framework python -m pytest -q clients/vscode-companion/test``
(needs the ``browser`` group and Node.js).
"""
from __future__ import annotations

import pytest

from conftest import NONCE
from panel_cases import click_fold

SUMMARY = {
    'schema': 'hypotrail.summary/1', 'ok': True, 'study': '/studies/my "study"', 'revision': 3,
    'since': None, 'changed': None, 'goal': {}, 'current_step': 'prediction_time',
    'plan': [{'id': 'prediction_time', 'title': 'Define the prediction moment',
              'status': 'awaiting_confirmation'},
             {'id': 'split', 'title': 'Split the data before exploring it', 'status': 'blocked'}],
    'next_action': {'kind': 'await_user_words', 'message': 'Show the restatement.'},
    'open_proposals': [{'proposal_id': 'p_1', 'decision_id': 'prediction_time',
                        'value': 'before the first reminder',
                        'restatement': 'You predict <b>before</b> the first reminder.',
                        'revision': 2}],
    'decisions': {}, 'results': {},
    'artifacts': {'status': 'stale', 'items': {
        'report': {'status': 'stale', 'message': 'The report (reports/study.html) is stale.'},
        'notebook': {'status': 'ok', 'message': 'The generated notebook is up to date.'}}},
    'executions': {}, 'not_yet_defensible': {'top': [{'id': 'no_causality',
                                                      'text': 'Associations are not causes.'}],
                                             'more': ['workbench_not_tracked']},
    'notes': [{'note_id': 'n_1', 'decision_id': 'prediction_time', 'status': 'open',
               'user_words': 'wait for <i>my</i> manager', 'resolution_words': None}],
    'recap': ['Goal: g', 'Decided: nothing yet.', 'Now: n', 'Next: x', 'Limit: l'],
}


@pytest.fixture(scope='module')
def summary_model(model) -> dict:
    return model('summary', SUMMARY)


@pytest.fixture
def opened(open_panel):
    panel = open_panel()
    yield panel.page, panel.requests, panel.errors, panel.csp, panel


def _send(page, message):
    # Synchronous delivery, as Panel.send in conftest.py (no race with the next assertion).
    page.evaluate('m => window.dispatchEvent(new MessageEvent("message", {data: m}))', {'v': 2, **message})


def _snapshot(page, model):
    _send(page, {'type': 'snapshot', 'revision': model['revision'], 'model': model})


def _posted(page):
    return page.evaluate('window.__posted')


def test_document_is_offline_with_a_strict_csp(opened):
    page, requests, errors, csp, panel = opened
    policy = page.locator('meta[http-equiv="Content-Security-Policy"]').get_attribute('content')
    assert policy.startswith("default-src 'none';")
    assert f"script-src 'nonce-{NONCE}'" in policy and "connect-src 'none'" in policy
    assert 'unsafe' not in policy and 'http' not in policy
    assert page.locator('script').count() == 1
    assert page.locator(f'script[nonce="{NONCE}"]').count() == 1
    assert _posted(page) == [{'v': 2, 'type': 'ready'}]
    assert requests == [] and errors == [] and csp == [] and panel.violations() == []


def test_csp_blocks_a_script_without_the_nonce(opened):
    page, _requests, _errors, csp, panel = opened
    page.evaluate("""() => { const s = document.createElement('script');
        s.textContent = 'window.__injected = true'; document.body.appendChild(s); }""")
    assert page.evaluate('window.__injected === undefined')
    assert csp, 'the browser reported the blocked script'
    assert panel.violations(), 'and fired securitypolicyviolation'


def test_the_proposal_card_is_read_only_and_asks_the_agent(opened, summary_model, model):
    """WP-E1 (R23, ADR 0004 amendment): the v0 card has no words field and no write control."""
    page, requests, errors, _csp, _panel = opened
    _snapshot(page, summary_model)
    now = page.locator('[data-block="now"]')
    assert now.get_attribute('data-now') == 'proposal'
    card = now.locator('[data-proposal-card="p_1"]')
    # Study text is shown as text, never parsed as HTML.
    assert card.locator('blockquote[data-restatement="p_1"]').inner_text() == \
        'You predict <b>before</b> the first reminder.'
    assert card.locator('blockquote b, blockquote i').count() == 0
    assert page.locator('textarea').count() == 0
    assert page.locator('[data-write], button[data-action]').count() == 0
    assert card.locator('[data-answer-in-chat]').inner_text().startswith('Answer in the chat')
    # No delegation control.
    assert page.locator('button').filter(has_text='delegat').count() == 0
    now.locator('[data-copy-question="prediction_time"]').click()
    assert _posted(page)[-1] == {'v': 2, 'type': 'ask_agent', 'about': {'kind': 'step', 'id': 'prediction_time'},
                                 'question': 'What does the prediction moment change in my study?',
                                 'mode': 'copy'}
    # The junior's open note, when the engine waits for it, is text too.
    held = model('summary', {**SUMMARY, 'next_action': {'kind': 'resolve_hold', 'decision': 'prediction_time',
                                                         'message': 'Resolve the hold in the junior words.'}})
    _snapshot(page, held)
    hold = page.locator('[data-block="now"] [data-hold="n_1"]')
    assert hold.inner_text() == 'wait for <i>my</i> manager'
    assert hold.locator('i').count() == 0
    assert requests == [] and errors == []


def test_panel_shows_recap_plan_artifacts_and_limits(opened, summary_model):
    page, *_ = opened
    _snapshot(page, summary_model)
    # Now holds the proposal; the path marks its step as the current one.
    assert page.locator('[data-block="now"]').get_attribute('data-now-step') == 'prediction_time'
    assert page.locator('li[aria-current="step"]').count() == 1
    assert page.locator('li[aria-current="step"]').get_attribute('data-step') == 'prediction_time'
    assert page.locator('[data-block="path"] [data-step]').evaluate_all('ns => ns.map(n => n.dataset.step)') == \
        ['prediction_time', 'split']
    # The stale report is in To handle.
    assert page.locator('[data-block="todo"] [data-todo="deliverables"]').get_attribute('title') == \
        'The report (reports/study.html) is stale.'
    # The limits: the pill counts them, its popover lists each in words (PG-6, HON-9 fallback).
    pill = page.locator('[data-pill="defensible"]')
    assert pill.inner_text().endswith('· 2')
    pill.click()
    items = page.locator('[data-popover="def"] [data-item]')
    assert items.evaluate_all('ns => ns.map(n => n.dataset.item)') == ['no_causality', 'workbench_not_tracked']
    assert 'workbench_not_tracked' not in page.locator('[data-popover="def"]').inner_text(), 'in words'
    # The deliverables' drawer opens the report.
    page.keyboard.press('Escape')
    assert page.locator('[data-popover="def"]').count() == 0
    click_fold(page, 't-deliverables')
    assert page.locator('[data-artifact="report"] [data-status-chip]').inner_text() == 'out of date'
    page.get_by_role('button', name='Open the report in the browser').click()
    assert _posted(page)[-1] == {'v': 2, 'type': 'open_artifact', 'artifact': 'report'}


def test_a_new_revision_redraws_and_malformed_messages_are_ignored(opened, summary_model):
    page, *_ = opened
    _snapshot(page, summary_model)
    _snapshot(page, {**summary_model, 'revision': 4})
    assert page.locator('[data-notice]').count() == 0
    # Unknown or malformed messages are ignored.
    _send(page, {'type': 'eval', 'code': 'window.__x = 1'})
    _send(page, {'type': 'snapshot', 'revision': 5, 'model': None})
    _send(page, {'type': 'busy', 'busy': True, 'op': 'W1', 'target': 'p_1'})
    page.evaluate('m => window.postMessage(m, "*")', {'type': 'snapshot', 'model': summary_model})
    assert page.locator('[data-proposal-card="p_1"]').count() == 1
    page.locator('[data-more]').click()
    assert 'revision 4' in page.locator('[data-more-menu] [data-refresh]').inner_text()
    assert page.evaluate('window.__x === undefined')


def test_dark_scheme_changes_the_colours(open_panel):
    colours = {}
    for scheme in ('light', 'dark'):
        panel = open_panel(color_scheme=scheme)
        colours[scheme] = panel.page.evaluate('getComputedStyle(document.body).backgroundColor')
    assert colours['light'] != colours['dark']
