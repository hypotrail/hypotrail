"""Companion webview tests: simulated host, real router and engine, simulated model, two projects."""
import json
from pathlib import Path
import re
import subprocess

import pytest
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT.parent / 'vscode-extension/test/harness.js'
BUSINESS_BANK = ['subscription', 'Bank Marketing', 'selected contacts', 'threshold']


@pytest.fixture
def ui(tmp_path):
    host = subprocess.Popen(['node', str(HARNESS), '--dir', str(tmp_path)], stdout=subprocess.PIPE, text=True)
    url = json.loads(host.stdout.readline())['url']
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1280, 'height': 900})
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(url)
        expect(page.get_by_text('Connected · shared exercise choices', exact=False)).to_be_visible(timeout=30000)

        def control(**script):
            response = page.request.post(url + 'control', data=json.dumps(script)) if script else page.request.get(url + 'control')
            return response.json()
        yield page, context, url, control
        assert not errors, errors
        context.close(); browser.close()
    host.terminate(); host.wait(timeout=10)


def threshold_step(page, value):
    page.locator('[data-activity="selection"]').click()
    page.locator('#threshold').select_option(str(value))
    expect(page.locator('[data-sync]')).to_have_attribute('data-sync', 'saved', timeout=15000)


def test_preview_then_apply_shows_result_before_progressive_explanation(ui):
    page, _, _, control = ui
    threshold_step(page, 0.2)
    expect(page.locator('#choice-preview')).to_have_text('Preview — choice not applied: threshold 0.20')
    expect(page.locator('.metrics-card')).to_contain_text('75')
    assert control()['calls'] == 0 and control()['selections'] == 0
    control(delay=350, chunks=['**What you selected** — threshold 0.20. ', 'Second fragment. ', 'Third fragment. ', 'End.'])
    page.locator('#apply-exercise').click()
    expect(page.locator('#choice-applied')).to_have_text('Applied choice: threshold 0.20', timeout=15000)
    expect(page.locator('#choice-result')).to_contain_text('Selected contacts 75')
    exchange = page.locator('.exchange[data-kind="initial"]')
    expect(exchange).to_have_attribute('data-status', re.compile('pending|streaming'))
    expect(exchange.locator('.exchange-body')).to_contain_text('What you selected', timeout=15000)
    expect(exchange).to_have_attribute('data-status', 'streaming')
    expect(exchange).to_have_attribute('data-status', 'completed', timeout=15000)
    expect(exchange.locator('.exchange-body strong').first).to_have_text('What you selected')
    assert control()['calls'] == 1
    expect(page.locator('#assistant-live')).to_have_text('Response complete.')


def test_question_keyboard_send_stop_and_draft(ui):
    page, _, _, control = ui
    threshold_step(page, 0.2)
    page.locator('#apply-exercise').click()
    expect(page.locator('.exchange[data-kind="initial"]')).to_have_attribute('data-status', 'completed', timeout=15000)
    box = page.locator('#question')
    box.fill('First line')
    box.press('Shift+Enter'); box.type('second line')
    assert box.input_value() == 'First line\nsecond line'
    # Preserve the draft across journey refreshes and page reloads.
    page.locator('#threshold').select_option('0.35')
    expect(box).to_have_value('First line\nsecond line')
    page.reload()
    expect(page.get_by_text('Connected · shared exercise choices', exact=False)).to_be_visible(timeout=30000)
    expect(page.locator('#question')).to_have_value('First line\nsecond line')
    expect(page.locator('#question-context')).to_have_text('Question about preview: threshold 0.35 — not applied')
    control(delay=400, chunks=['un ', 'deux ', 'trois ', 'quatre ', 'cinq '])
    page.locator('#question').press('Enter')
    question = page.locator('.exchange[data-kind="question"]')
    expect(question.locator('.exchange-question')).to_contain_text('First line')
    expect(page.locator('#question')).to_have_value('')
    expect(page.locator('#stop')).to_be_visible()
    expect(question.locator('.exchange-body')).to_contain_text('un', timeout=15000)
    page.locator('#stop').click()
    expect(question).to_have_attribute('data-status', 'interrupted', timeout=15000)
    expect(question.locator('.exchange-state')).to_contain_text('Incomplete response')
    expect(page.locator('#choice-applied')).to_have_text('Applied choice: threshold 0.20')


def test_scroll_is_not_forced_and_focus_never_moves(ui):
    page, _, _, control = ui
    page.set_viewport_size({'width': 1100, 'height': 700})
    control(delay=5, chunks=['A sufficiently long response line. ' * 8 + '\n\n'] * 6)
    for i in range(3):
        page.locator('#question').fill(f'Question {i}')
        page.locator('#question').press('Enter')
        expect(page.locator('.exchange[data-status="completed"]')).to_have_count(i + 1, timeout=20000)
    thread = page.locator('#thread')
    thread.evaluate('t => t.scrollTop = 0')
    control(delay=300, chunks=['New ', 'response ', 'arrived.'])
    page.locator('.shortcuts [data-shortcut="simple"]').click()
    expect(page.locator('#new-reply')).to_be_visible(timeout=15000)
    assert thread.evaluate('t => t.scrollTop') == 0
    page.locator('#question').focus()
    expect(page.locator('.exchange[data-status="completed"]')).to_have_count(4, timeout=20000)
    assert page.evaluate('document.activeElement.id') == 'question'
    page.locator('#new-reply').click()
    expect(page.locator('#new-reply')).to_be_hidden()
    assert set(control()['seen']['messageTypes']) <= {'rpc', 'assistant'}


def test_error_retry_and_conflict_reload(ui):
    page, context, url, control = ui
    control(error={'code': 'quota', 'message': 'Usage limit reached.'})
    threshold_step(page, 0.2)
    page.locator('#apply-exercise').click()
    exchange = page.locator('.exchange[data-kind="initial"]')
    expect(exchange).to_have_attribute('data-status', 'error', timeout=15000)
    expect(exchange.locator('.exchange-state')).to_contain_text('Your choice and its results are preserved')
    expect(page.locator('#choice-applied')).to_have_text('Applied choice: threshold 0.20')
    control(error=None, chunks=['Response after retry.'])
    exchange.get_by_role('button', name='Retry').click()
    expect(exchange).to_have_attribute('data-status', 'completed', timeout=15000)
    expect(exchange.locator('.exchange-body')).to_have_text('Response after retry.')
    # Conflict: another tab changes state; no model request and an explicit reload action.
    other = context.new_page(); other.goto(url)
    expect(other.get_by_text('Connected · shared exercise choices', exact=False)).to_be_visible(timeout=30000)
    calls = control()['calls']
    other.locator('[data-activity="selection"]').click()
    other.locator('#threshold').select_option('0.5')
    expect(other.locator('[data-sync]')).to_have_attribute('data-sync', 'saved', timeout=15000)
    page.locator('#threshold').select_option('0.1')
    expect(page.locator('[data-sync]')).to_have_attribute('data-sync', 'conflict', timeout=15000)
    assert control()['calls'] == calls
    page.get_by_text('Conversation and export', exact=True).click()
    page.get_by_role('button', name='Reload shared state').click()
    expect(page.locator('#choice-preview')).to_have_text('Preview — choice not applied: threshold 0.50')
    other.close()


def test_resume_after_close_sends_no_request(ui):
    page, _, url, control = ui
    control(delay=300, chunks=['a ', 'b ', 'c ', 'd ', 'e '])
    threshold_step(page, 0.35)
    page.locator('#apply-exercise').click()
    expect(page.locator('.exchange[data-kind="initial"] .exchange-body')).to_contain_text('a', timeout=15000)
    page.goto('about:blank')
    page.goto(url)
    expect(page.get_by_text('Connected · shared exercise choices', exact=False)).to_be_visible(timeout=30000)
    page.locator('[data-activity="selection"]').click()
    exchange = page.locator('.exchange[data-kind="initial"]')
    expect(exchange).to_have_attribute('data-status', 'completed', timeout=20000)
    expect(exchange.locator('.exchange-body')).to_have_text('a b c d e')
    page.reload()
    expect(page.get_by_text('Connected · shared exercise choices', exact=False)).to_be_visible(timeout=30000)
    page.locator('[data-activity="selection"]').click()
    expect(page.locator('.exchange[data-kind="initial"] .exchange-body')).to_have_text('a b c d e')
    assert control()['calls'] == 1


def test_keyboard_theme_narrow_and_labels(ui):
    page, _, _, _ = ui
    page.locator('[data-activity="selection"]').click()
    expect(page.get_by_label('A question about this step?')).to_be_visible()
    expect(page.get_by_role('log', name='Explanations and answers for this activity')).to_be_visible()
    page.locator('#question').focus()
    page.keyboard.press('Tab')
    assert page.evaluate('document.activeElement.id') == 'junior'
    for theme in ('dark', 'light'):
        page.locator('#theme').click()
        assert ('dark' in page.locator('body').get_attribute('class')) == (theme == 'dark')
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')
    expect(page.locator('#apply-exercise')).to_be_visible()


def test_regression_project_same_webview_isolated(ui):
    page, _, url, control = ui
    bank_html = page.request.get(url).text()
    # A slow Bank response is in progress when the project changes.
    control(delay=500, ignoreAbort=True, chunks=['previous project 1 ', 'previous project 2 ', 'previous project 3 ', 'previous project 4 '])
    threshold_step(page, 0.2)
    page.locator('#apply-exercise').click()
    expect(page.locator('.exchange[data-kind="initial"] .exchange-body')).to_contain_text('previous project', timeout=15000)
    page.get_by_label('Companion project').select_option('uci-auto-mpg-v1')
    expect(page.locator('#project-pill')).to_contain_text('Auto MPG', timeout=30000)
    expect(page.get_by_text('Connected · shared exercise choices', exact=False)).to_be_visible(timeout=30000)
    assert re.sub(r'nonce(-|=")[0-9a-f]+', '', page.request.get(url).text()) == re.sub(r'nonce(-|=")[0-9a-f]+', '', bank_html)
    page.wait_for_timeout(2500)
    # Only the header project selector names other projects; the journey does not expose them.
    text = page.locator('main').inner_text()
    for word in BUSINESS_BANK + ['previous project']:
        assert word not in text, word
    # Discovery: show units and unknown facts.
    expect(page.get_by_role('table', name='Example data')).to_contain_text('Fuel efficiency (mpg)')
    expect(page.locator('.clarifications')).to_contain_text('Meaning of origin codes')
    # Block activity until human confirmation.
    page.locator('[data-activity="compare"]').click()
    expect(page.locator('#choice-blocked')).to_contain_text('Prediction time')
    expect(page.locator('[data-pick]').first).to_be_disabled()
    expect(page.locator('thead')).to_contain_text('mpg')
    blocking = page.locator('.fact[data-fact="prediction_time"]')
    expect(blocking).to_have_count(1)
    blocking.get_by_role('button', name='Confirm this proposal').click()
    expect(page.locator('[data-pick]').first).to_be_enabled(timeout=15000)
    control(delay=5, ignoreAbort=False, chunks=['**What you selected** — regression · characteristics. ', 'Mean error 4.38 mpg.'])
    page.locator('[data-pick][data-value="linear-all"]').click()
    expect(page.locator('#choice-preview')).to_have_text('Preview — choice not applied: Regression · characteristics')
    page.locator('#apply-exercise').click()
    expect(page.locator('#choice-result')).to_contain_text('4.38 mpg', timeout=15000)
    expect(page.locator('.exchange[data-kind="initial"]')).to_have_attribute('data-status', 'completed', timeout=15000)
    context = control()['contexts'][-1]
    assert '"problem_type": "regression"' in context and 'subscription' not in context
    page.locator('[data-activity="errors"]').click()
    expect(page.locator('#content')).to_contain_text('1980')
    expect(page.locator('#content')).to_contain_text('mpg')
    expect(page.locator('#content')).to_contain_text('(applied)')
