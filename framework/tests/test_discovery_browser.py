"""Vrai navigateur : report current, navigation et reprise de lecture locale."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from mlkit import config, discover, pilot
from test_classical import prepare


def test_full_discovery_and_pilot_view(tmp_path, monkeypatch):
    prepare(tmp_path, 'binary'); monkeypatch.setattr(config, 'ROOT', tmp_path)
    discover.report(tmp_path); state = pilot.init('junior')
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1280, 'height': 900})
        errors = []; page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto((tmp_path/'reports/pilot.html').as_uri())
        assert page.locator('#current-action').is_visible()
        assert 'Revision' in page.locator('#current-action').inner_text()
        assert 'unconfirmed' in page.locator('#current-action').inner_text()
        page.goto((tmp_path/'reports/dataset-discovery.html').as_uri())
        for i in range(2, 6):
            page.locator('#visit-next').click()
            assert page.locator(f'#visit-{i}').is_visible()
        assert '5/5 steps opened' in page.locator('#visit-status').inner_text()
        page.reload(); assert page.locator('#visit-5').is_visible()
        page.locator('[data-step="2"]').click()
        page.get_by_role('button', name='Light / dark').click()
        assert 'dark' in page.locator('body').get_attribute('class').split()
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.goto((tmp_path/'reports/pilot.html').as_uri())
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not errors
        browser.close()
    # Reading clicks confirm no pilot answer.
    assert pilot.load()['answers'] == state['answers'] == {}
