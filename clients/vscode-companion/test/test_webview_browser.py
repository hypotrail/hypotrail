"""Browser test of the companion's webview document at stage v0 (scope S, simulated browser).

The real document (``lib/html.js``) is loaded in headless Chromium, offline, with a stub
``acquireVsCodeApi`` that records the posted messages (``conftest.py``). The model is
produced by the real ``lib/models/summary.js`` from a summary. This is not a VS Code
session: VS Code's own webview host, theme variables, and message transport are not
exercised.

Migrated by WP-0 to protocol hypotrail.panel/2 (every message carries ``v: 2``, ``open``
is ``open_artifact``, an outcome names its write ``op``); every v0 assertion is kept.

Run: ``uv run --project framework python -m pytest -q clients/vscode-companion/test``
(needs the ``browser`` group and Node.js).
"""
from __future__ import annotations

import json

import pytest

from conftest import NONCE

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
ENGINE_MESSAGE = ('A bare acknowledgement is not a decision. Restate the proposal and ask the '
                  'user to answer it in their own words.')


@pytest.fixture(scope='module')
def summary_model(model) -> dict:
    return model('summary', SUMMARY)


@pytest.fixture(scope='module')
def refusal(node) -> dict:
    payload = {'schema': 'hypotrail.error/1', 'ok': False, 'command': 'decide confirm',
               'error': {'code': 'ambiguous_confirmation', 'message': ENGINE_MESSAGE,
                         'details': {'reason': 'bare_acknowledgement', 'user_words': 'ok'}}}
    return json.loads(node("let s='';process.stdin.on('data',d=>s+=d).on('end',()=>"
                           "process.stdout.write(JSON.stringify(require('./lib/refusals')"
                           ".describe(JSON.parse(s)))))", json.dumps(payload)))


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


def test_proposal_textarea_starts_empty_and_confirm_needs_typed_words(opened, summary_model):
    page, requests, errors, _csp, _panel = opened
    _snapshot(page, summary_model)
    card = page.locator('[data-proposal-card="p_1"]')
    # Study text is shown as text, never parsed as HTML.
    assert card.locator('blockquote[data-restatement="p_1"]').inner_text() == \
        'You predict <b>before</b> the first reminder.'
    assert page.locator('b, i').count() == 0
    assert 'wait for <i>my</i> manager' in card.locator('[data-hold="n_1"]').inner_text()
    area = page.get_by_label('Your answer, in your own words')
    assert area.input_value() == ''
    confirm = card.locator('button[data-action="confirm"]')
    assert confirm.is_disabled()
    area.fill('   ')
    assert confirm.is_disabled()
    area.fill('Yes, before the first reminder is sent')
    assert confirm.is_enabled()
    confirm.click()
    assert _posted(page)[-1] == {'v': 2, 'type': 'confirm', 'proposalId': 'p_1',
                                 'words': 'Yes, before the first reminder is sent',
                                 'revision': 3}
    # No delegation control, no other mutating control.
    assert page.locator('button').filter(has_text='delegat').count() == 0
    actions = page.locator('button[data-action]').evaluate_all('bs => bs.map(b => b.dataset.action)')
    assert sorted(set(actions)) == ['confirm', 'withdraw']
    writes = page.locator('button[data-write]').evaluate_all('bs => bs.map(b => b.dataset.write)')
    assert sorted(set(writes)) == ['confirm', 'withdraw']
    assert requests == [] and errors == []


def test_panel_shows_recap_plan_artifacts_and_limits(opened, summary_model):
    page, *_ = opened
    _snapshot(page, summary_model)
    assert page.locator('[data-recap] li').count() == 5
    assert page.locator('[data-current-step="prediction_time"]').inner_text() == \
        'Step 1 of 2: Define the prediction moment.'
    assert page.locator('li[aria-current="step"]').count() == 1
    assert 'stale' in page.locator('[data-artifact="report"]').inner_text()
    assert page.locator('[data-nyd="no_causality"]').inner_text() == 'Associations are not causes.'
    page.get_by_role('button', name='Open the report in the browser').click()
    assert _posted(page)[-1] == {'v': 2, 'type': 'open_artifact', 'artifact': 'report'}


def test_refusal_is_rendered_verbatim_with_the_human_message(opened, summary_model, refusal):
    page, requests, errors, _csp, _panel = opened
    _snapshot(page, summary_model)
    page.get_by_label('Your answer, in your own words').fill('ok')
    _send(page, {'type': 'outcome', 'op': 'W1', 'kind': 'refused', 'target': 'p_1', 'exitCode': 2,
                 'refusal': refusal})
    alert = page.locator('[data-outcome="refused"]')
    assert alert.get_attribute('role') == 'alert'
    assert alert.get_attribute('data-reason') == 'bare_acknowledgement'
    assert alert.locator('[data-engine-message]').inner_text() == ENGINE_MESSAGE
    assert alert.locator('[data-human]').inner_text() == refusal['human']
    assert refusal['human'].endswith('Nothing was recorded.')
    # The junior's own text stays for them to edit; the panel adds nothing to it.
    assert page.get_by_label('Your answer, in your own words').input_value() == 'ok'
    assert requests == [] and errors == []


def test_busy_disables_the_buttons_and_a_new_revision_warns_a_typing_junior(opened, summary_model):
    page, *_ = opened
    _snapshot(page, summary_model)
    page.get_by_label('Your answer, in your own words').fill('Yes, before the reminder')
    _send(page, {'type': 'busy', 'busy': True, 'op': 'W1', 'target': 'p_1'})
    assert page.locator('button[data-action="confirm"]').is_disabled()
    assert page.locator('button[data-action="withdraw"]').is_disabled()
    _send(page, {'type': 'busy', 'busy': False, 'op': 'W1', 'target': 'p_1'})
    _snapshot(page, {**summary_model, 'revision': 4})
    assert 'revision 3 to 4' in page.locator('[data-notice]').inner_text()
    assert page.get_by_label('Your answer, in your own words').input_value() == \
        'Yes, before the reminder'
    # Unknown or malformed messages are ignored.
    _send(page, {'type': 'eval', 'code': 'window.__x = 1'})
    _send(page, {'type': 'snapshot', 'revision': 5, 'model': None})
    page.evaluate('m => window.postMessage(m, "*")', {'type': 'snapshot', 'model': summary_model})
    assert page.locator('[data-proposal-card="p_1"]').count() == 1
    assert page.locator('[data-revision]').get_attribute('data-revision') == '4'


def test_dark_scheme_changes_the_colours(open_panel):
    colours = {}
    for scheme in ('light', 'dark'):
        panel = open_panel(color_scheme=scheme)
        colours[scheme] = panel.page.evaluate('getComputedStyle(document.body).backgroundColor')
    assert colours['light'] != colours['dark']
