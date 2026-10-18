"""Real Chromium: journey, resumption, network failure, and cross-tab conflict on a local server."""
from contextlib import closing
import importlib.util
from pathlib import Path
import re
import subprocess
import sys
import threading

import pytest
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bridge', ROOT / 'bridge.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


@pytest.fixture
def app(tmp_path):
    db = tmp_path / 'session.sqlite'
    token = 'synthetic-test-token'
    server = bridge.make_server(db, token, 0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1280, 'height': 900})
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        url = f'http://127.0.0.1:{server.server_port}/#token={token}'
        page.goto(url)
        expect(page.get_by_text('Connected · shared exercise choices', exact=False)).to_be_visible()
        yield page, context, url, db
        assert not errors, errors
        context.close()
        browser.close()
    server.shutdown()
    worker.join(timeout=5)
    server.server_close()


def saved(page, step):
    # Wait for explicit acknowledgment, not a JS promise used as a truthy predicate.
    expect(page.locator('[data-sync]')).to_have_attribute('data-sync', 'saved', timeout=10000)
    token = page.evaluate("sessionStorage.getItem('tutorial-bridge-token:'+location.origin)")
    origin = page.evaluate('location.origin')
    response = page.request.get(origin + '/state', headers={'X-Pilot-Token': token})
    assert response.ok and response.json()['state']['step'] == step


def test_browser_full_tutorial_reload_and_cli_feedback(app):
    page, _, _, db = app
    for step in range(8):
        page.locator(f'[data-step="{step}"]').click()
        choices = page.locator('[data-quiz]')
        if choices.count():
            choices.first.click()
            expect(choices.first).to_have_attribute('aria-pressed', 'true')
        saved(page, step)
    expect(page.locator('#handoff')).to_be_visible()
    assert 'No real decision' in page.locator('#handoff').input_value()
    page.reload()
    expect(page.locator('[data-step="7"]')).to_have_attribute('aria-current', 'step')
    subprocess.run([sys.executable, str(ROOT / 'bridge.py'), 'explain', '--db', str(db),
                    '--message', 'Your hypothesis still needs confirmation.'], check=True, capture_output=True, timeout=10)
    expect(page.get_by_text('Your hypothesis still needs confirmation.', exact=True)).to_be_visible(timeout=6000)
    with closing(bridge.connect(db)) as connection:
        snapshot = bridge.snapshot(connection)
    assert snapshot['project_approval'] is False and snapshot['state']['answers']
    page.locator('#theme').click()
    expect(page.locator('body')).to_have_class(re.compile(r'(^| )dark( |$)'))
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')


def test_browser_network_failure_keeps_newest_choice(app):
    page, _, _, _ = app
    page.evaluate('''() => {
      const original=window.fetch; let first=true;
      window.fetch=(url,opts)=>{
        if(opts?.method==='POST' && first){first=false; return new Promise((_,reject)=>setTimeout(()=>reject(Error('test outage')),600));}
        return original(url,opts);
      };
    }''')
    page.locator('[data-step="1"]').click()
    page.locator('[data-step="2"]').click()
    saved(page, 2)
    expect(page.get_by_text('Recorded choices', exact=False)).to_be_visible()
    page.reload()
    expect(page.locator('[data-step="2"]')).to_have_attribute('aria-current', 'step')


def test_browser_conflict_requires_reload(app):
    page, context, url, _ = app
    other = context.new_page()
    other.goto(url)
    expect(other.get_by_text('Connected · shared exercise choices', exact=False)).to_be_visible()
    page.locator('[data-step="3"]').click()
    saved(page, 3)
    other.locator('[data-step="4"]').click()
    expect(other.get_by_text(re.compile('Another tab changed the answers|Shared state changed'))).to_be_visible()
    other.get_by_text('Conversation and export', exact=True).click()
    other.get_by_role('button', name='Reload shared state').click()
    expect(other.locator('[data-step="3"]')).to_have_attribute('aria-current', 'step')
    other.close()


def test_browser_return_to_previous_choice_during_write(app):
    page, _, _, _ = app
    page.evaluate('''() => {
      const original=window.fetch; let first=true;
      window.fetch=(url,opts)=>{
        if(opts?.method==='POST' && first){first=false; return new Promise(resolve=>setTimeout(()=>resolve(original(url,opts)),600));}
        return original(url,opts);
      };
    }''')
    page.locator('[data-step="1"]').click()
    page.locator('[data-step="0"]').click()
    saved(page, 0)
    page.reload()
    expect(page.locator('[data-step="0"]')).to_have_attribute('aria-current', 'step')
