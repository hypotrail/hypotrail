"""Offline browser check of the HTML report (plan §7: ``test_html_offline``; WP3.1).

Simulated browser test (Playwright, headless Chromium, network blocked). It is not a
Copilot or Claude Code acceptance session. Requires the ``browser`` dependency group:
``uv sync --project framework --group dev --group browser``.
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

import pytest

from mlkit.study import manifest as mf

playwright = pytest.importorskip('playwright.sync_api')


def _chromium(p):
    try:
        return p.chromium.launch(headless=True)
    except Exception:
        # A preinstalled browser build that differs from the one this Playwright pins.
        root = os.environ.get('PLAYWRIGHT_BROWSERS_PATH', '/opt/pw-browsers')
        for pattern in ('chromium_headless_shell-*/chrome-linux/headless_shell',
                        'chromium-*/chrome-linux/chrome'):
            found = sorted(glob.glob(os.path.join(root, pattern)))
            if found:
                return p.chromium.launch(headless=True, executable_path=found[-1])
        pytest.skip('no Chromium available for Playwright')


@pytest.fixture(scope='module')
def browser():
    with playwright.sync_playwright() as p:
        b = _chromium(p)
        yield b
        b.close()


def _open(browser, page_path: Path, scheme='light'):
    context = browser.new_context(offline=True, color_scheme=scheme)
    requests, errors = [], []
    context.route('**/*', lambda route: route.continue_() if route.request.url.startswith('file:')
                  else (requests.append(route.request.url), route.abort()))
    page = context.new_page()
    page.on('pageerror', lambda exc: errors.append(str(exc)))
    page.on('console', lambda msg: errors.append(msg.text) if msg.type == 'error' else None)
    page.goto(page_path.resolve().as_uri())
    page.wait_for_load_state('load')
    return context, page, requests, errors


def test_report_works_offline_without_decision_controls(browser, full_study):
    report = full_study / mf.ARTIFACTS['report']
    context, page, requests, errors = _open(browser, report)
    try:
        assert requests == [] and errors == []
        assert page.locator('button').count() == 1
        assert page.locator('button[data-theme-toggle]').count() == 1
        for selector in ('input', 'form', 'select', 'textarea', '[role=slider]',
                         '[contenteditable]', 'iframe', 'a[href^="http"]'):
            assert page.locator(selector).count() == 0, selector
        data = page.locator('data')
        assert data.count() > 50
        assert page.locator('data:not([data-result-id])').count() == 0
        assert page.locator('[data-nyd]').count() >= 5
        assert page.locator('#policy table.metrics tbody tr').count() == 3
        # status is written in words, not shown by colour alone
        assert 'Confirmed decision' in page.inner_text('#decisions')
        body = page.locator('body')
        assert 'dark' not in (body.get_attribute('class') or '')
        page.click('button[data-theme-toggle]')
        assert 'dark' in body.get_attribute('class')
        assert page.get_attribute('button[data-theme-toggle]', 'aria-pressed') == 'true'
        page.click('button[data-theme-toggle]')
        assert 'dark' not in body.get_attribute('class')
    finally:
        context.close()


def test_report_follows_a_dark_preference(browser, full_study):
    context, page, requests, errors = _open(browser, full_study / mf.ARTIFACTS['report'], 'dark')
    try:
        assert requests == [] and errors == []
        assert 'dark' in page.locator('body').get_attribute('class')
    finally:
        context.close()


def test_stale_banner_is_visible_offline(browser, full_study, monkeypatch):
    from mlkit.study import cmd_render

    monkeypatch.setenv('HYPOTRAIL_TEST_HOOKS', '1')
    monkeypatch.setenv('HYPOTRAIL_FAULT', 'render_html')
    result = cmd_render.render_all(full_study)
    assert result['artifacts']['report']['status'] == 'failed'
    context, page, requests, errors = _open(browser, full_study / mf.ARTIFACTS['report'])
    try:
        assert requests == [] and errors == []
        alert = page.locator('[role=alert][data-hypotrail-banner=stale]')
        assert alert.count() == 1 and alert.is_visible()
        assert 'Stale report.' in alert.inner_text()
        assert page.locator('button').count() == 1
    finally:
        context.close()
