"""Browser test of the companion's webview document (scope S, simulated browser).

The real document (``lib/html.js``) and script (``media/panel.js``) are loaded in
headless Chromium, offline, with a stub ``acquireVsCodeApi`` that records the posted
messages. The model is produced by the real ``lib/model.js`` from a summary. This is not
a VS Code session: VS Code's own webview host, theme variables, and message transport
are not exercised.

Run: ``uv run --project framework python -m pytest -q clients/vscode-companion/test``
(needs the ``browser`` group and Node.js).
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import warnings
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CLIENT = HERE.parent
NONCE = 'testNonce0123456789abcdef'
NODE = shutil.which('node')

try:
    import playwright.sync_api as playwright
except ImportError:  # pragma: no cover - the gate installs the browser group
    warnings.warn('the companion webview browser test did not run: Playwright is not '
                  'installed (uv sync --project framework --group dev --group browser).',
                  pytest.PytestWarning, stacklevel=1)
    pytest.skip('Playwright is not installed', allow_module_level=True)
if NODE is None:  # pragma: no cover
    pytest.skip('Node.js is not installed', allow_module_level=True)

STUB = """
(() => {
  window.__posted = [];
  let state = null, used = false;
  window.acquireVsCodeApi = () => {
    if (used) throw new Error('acquireVsCodeApi called twice');
    used = true;
    return { postMessage: m => window.__posted.push(JSON.parse(JSON.stringify(m))),
             getState: () => state, setState: s => { state = s; } };
  };
})();
"""

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


def _node(code: str, stdin: str = '') -> str:
    return subprocess.run([NODE, '-e', code], input=stdin, capture_output=True, text=True,
                          check=True, cwd=CLIENT, timeout=60).stdout


@pytest.fixture(scope='module')
def page_file(tmp_path_factory) -> Path:
    html = subprocess.run([NODE, str(CLIENT / 'lib' / 'html.js'), NONCE], capture_output=True,
                          text=True, check=True, timeout=60).stdout
    target = tmp_path_factory.mktemp('webview') / 'panel.html'
    target.write_text(html, encoding='utf-8')
    return target


@pytest.fixture(scope='module')
def model() -> dict:
    return json.loads(_node("let s='';process.stdin.on('data',d=>s+=d).on('end',()=>"
                            "process.stdout.write(JSON.stringify(require('./lib/model')"
                            ".toModel(JSON.parse(s)))))", json.dumps(SUMMARY)))


@pytest.fixture(scope='module')
def refusal() -> dict:
    payload = {'schema': 'hypotrail.error/1', 'ok': False, 'command': 'decide confirm',
               'error': {'code': 'ambiguous_confirmation', 'message': ENGINE_MESSAGE,
                         'details': {'reason': 'bare_acknowledgement', 'user_words': 'ok'}}}
    return json.loads(_node("let s='';process.stdin.on('data',d=>s+=d).on('end',()=>"
                            "process.stdout.write(JSON.stringify(require('./lib/refusals')"
                            ".describe(JSON.parse(s)))))", json.dumps(payload)))


def _chromium(p):
    try:
        return p.chromium.launch(headless=True)
    except Exception:
        root = os.environ.get('PLAYWRIGHT_BROWSERS_PATH', '/opt/pw-browsers')
        for pattern in ('chromium_headless_shell-*/chrome-linux/headless_shell',
                        'chromium-*/chrome-linux/chrome'):
            found = sorted(glob.glob(os.path.join(root, pattern)))
            if found:
                return p.chromium.launch(headless=True, executable_path=found[-1])
        warnings.warn('no Chromium for Playwright: the companion webview test did not run.',
                      pytest.PytestWarning, stacklevel=1)
        pytest.skip('no Chromium available for Playwright')


@pytest.fixture(scope='module')
def browser():
    with playwright.sync_playwright() as p:
        b = _chromium(p)
        yield b
        b.close()


@pytest.fixture
def opened(browser, page_file):
    context = browser.new_context(offline=True)
    requests, errors, csp = [], [], []
    context.route('**/*', lambda route: route.continue_() if route.request.url.startswith('file:')
                  else (requests.append(route.request.url), route.abort()))
    context.add_init_script(STUB)
    page = context.new_page()
    page.on('pageerror', lambda exc: errors.append(str(exc)))
    page.on('console', lambda msg: (csp if 'Content Security Policy' in msg.text else errors)
            .append(msg.text) if msg.type == 'error' else None)
    page.goto(page_file.as_uri())
    page.wait_for_load_state('load')
    yield page, requests, errors, csp
    context.close()


def _send(page, message):
    page.evaluate('m => window.postMessage(m, "*")', message)


def _posted(page):
    return page.evaluate('window.__posted')


def test_document_is_offline_with_a_strict_csp(opened):
    page, requests, errors, csp = opened
    policy = page.locator('meta[http-equiv="Content-Security-Policy"]').get_attribute('content')
    assert policy.startswith("default-src 'none';")
    assert f"script-src 'nonce-{NONCE}'" in policy and "connect-src 'none'" in policy
    assert 'unsafe' not in policy and 'http' not in policy
    assert page.locator('script').count() == 1
    assert page.locator(f'script[nonce="{NONCE}"]').count() == 1
    assert _posted(page) == [{'type': 'ready'}]
    assert requests == [] and errors == [] and csp == []


def test_csp_blocks_a_script_without_the_nonce(opened):
    page, _requests, _errors, csp = opened
    page.evaluate("""() => { const s = document.createElement('script');
        s.textContent = 'window.__injected = true'; document.body.appendChild(s); }""")
    assert page.evaluate('window.__injected === undefined')
    assert csp, 'the browser reported the blocked script'


def test_proposal_textarea_starts_empty_and_confirm_needs_typed_words(opened, model):
    page, requests, errors, _csp = opened
    _send(page, {'type': 'snapshot', 'model': model})
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
    assert _posted(page)[-1] == {'type': 'confirm', 'proposalId': 'p_1',
                                 'words': 'Yes, before the first reminder is sent',
                                 'revision': 3}
    # No delegation control, no other mutating control.
    assert page.locator('button').filter(has_text='delegat').count() == 0
    actions = page.locator('button[data-action]').evaluate_all('bs => bs.map(b => b.dataset.action)')
    assert sorted(set(actions)) == ['confirm', 'withdraw']
    assert requests == [] and errors == []


def test_panel_shows_recap_plan_artifacts_and_limits(opened, model):
    page, *_ = opened
    _send(page, {'type': 'snapshot', 'model': model})
    assert page.locator('[data-recap] li').count() == 5
    assert page.locator('[data-current-step="prediction_time"]').inner_text() == \
        'Step 1 of 2: Define the prediction moment.'
    assert page.locator('li[aria-current="step"]').count() == 1
    assert 'stale' in page.locator('[data-artifact="report"]').inner_text()
    assert page.locator('[data-nyd="no_causality"]').inner_text() == 'Associations are not causes.'
    page.get_by_role('button', name='Open the report in the browser').click()
    assert _posted(page)[-1] == {'type': 'open', 'artifact': 'report'}


def test_refusal_is_rendered_verbatim_with_the_human_message(opened, model, refusal):
    page, requests, errors, _csp = opened
    _send(page, {'type': 'snapshot', 'model': model})
    page.get_by_label('Your answer, in your own words').fill('ok')
    _send(page, {'type': 'outcome', 'kind': 'refused', 'proposalId': 'p_1', 'exitCode': 2,
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


def test_busy_disables_the_buttons_and_a_new_revision_warns_a_typing_junior(opened, model):
    page, *_ = opened
    _send(page, {'type': 'snapshot', 'model': model})
    page.get_by_label('Your answer, in your own words').fill('Yes, before the reminder')
    _send(page, {'type': 'busy', 'busy': True, 'proposalId': 'p_1'})
    assert page.locator('button[data-action="confirm"]').is_disabled()
    assert page.locator('button[data-action="withdraw"]').is_disabled()
    _send(page, {'type': 'busy', 'busy': False, 'proposalId': 'p_1'})
    _send(page, {'type': 'snapshot', 'model': {**model, 'revision': 4}})
    assert 'revision 3 to 4' in page.locator('[data-notice]').inner_text()
    assert page.get_by_label('Your answer, in your own words').input_value() == \
        'Yes, before the reminder'
    # Unknown or malformed messages are ignored.
    _send(page, {'type': 'eval', 'code': 'window.__x = 1'})
    _send(page, {'type': 'snapshot', 'model': None})
    assert page.locator('[data-proposal-card="p_1"]').count() == 1


def test_dark_scheme_changes_the_colours(browser, page_file, model):
    colours = {}
    for scheme in ('light', 'dark'):
        context = browser.new_context(offline=True, color_scheme=scheme)
        context.add_init_script(STUB)
        page = context.new_page()
        page.goto(page_file.as_uri())
        colours[scheme] = page.evaluate('getComputedStyle(document.body).backgroundColor')
        context.close()
    assert colours['light'] != colours['dark']
