"""Playwright harness of the companion's webview tests (scope S, simulated browser; WP-0).

The real document (``lib/html.js``: every media file under the real CSP and one nonce) is
loaded in headless Chromium, offline, with a stub ``acquireVsCodeApi`` that records the
posted messages and the ``setState`` value. CSP violations are recorded twice: from the
``securitypolicyviolation`` event and from console errors. Models are produced by the real
``lib/models/*.js`` functions from the fixtures of ``test/fixtures/``. This is not a VS Code
session: its webview host, theme variables, and message transport are not exercised.

Fixtures for every webview test file (one file per WP, ``test_webview_<view>.py``):

* ``browser`` (session): a Chromium, or a skip with a ``PytestWarning`` saying why;
* ``page_file`` (session): the document for the fixed nonce ``NONCE``;
* ``open_panel`` (function): ``open_panel(color_scheme='light') -> Panel``;
* ``model``: ``model('summary', 'summary.v0.binary')`` runs ``toSummaryModel`` on a fixture;
* ``payload``: ``payload('error.bare_acknowledgement')`` reads a fixture's payload;
* ``node``: ``node(code, stdin='')`` runs Node.js in the client folder.

``Panel`` has ``page``, ``send(message)`` (adds ``v: 2``), ``init(stage=..., ...)``,
``snapshot(model)``, ``view_data(view, model)``, ``posted()``, ``state()``, ``requests``,
``errors``, ``csp`` (console reports) and ``violations()`` (``securitypolicyviolation``).
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import warnings
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CLIENT = HERE.parent
FIXTURES = HERE / 'fixtures'
NONCE = 'testNonce0123456789abcdef'
# The study key of `init` in these tests (decision CR.2): one study unless a test names another.
STUDY_KEY = '0123456789abcdef'
NODE = shutil.which('node')

try:
    import playwright.sync_api as playwright
except ImportError:  # pragma: no cover - the gate installs the browser group
    playwright = None

STUB = """
(() => {
  // v0.3 (WP-E2): record every setAttribute('style', ...): the CSP forbids inline style
  // attributes; CSSOM writes of custom properties are the one allowed way to size a mark.
  window.__styleAttrs = [];
  const setAttribute = Element.prototype.setAttribute;
  Element.prototype.setAttribute = function (name, value) {
    if (String(name).toLowerCase() === 'style') window.__styleAttrs.push(String(value));
    return setAttribute.call(this, name, value);
  };
  window.__posted = [];
  window.__csp = [];
  window.__state = null;
  document.addEventListener('securitypolicyviolation', e => window.__csp.push(
    {directive: e.violatedDirective, blocked: e.blockedURI, sample: e.sample}));
  let used = false;
  window.acquireVsCodeApi = () => {
    if (used) throw new Error('acquireVsCodeApi called twice');
    used = true;
    return { postMessage: m => window.__posted.push(JSON.parse(JSON.stringify(m))),
             getState: () => window.__state, setState: s => { window.__state = JSON.parse(JSON.stringify(s)); } };
  };
})();
"""


def _require_tools():
    if playwright is None:  # pragma: no cover
        warnings.warn('the companion webview browser tests did not run: Playwright is not '
                      'installed (uv sync --project framework --group dev --group browser).',
                      pytest.PytestWarning, stacklevel=2)
        pytest.skip('Playwright is not installed')
    if NODE is None:  # pragma: no cover
        pytest.skip('Node.js is not installed')


def inline_styles_ok(page) -> bool:
    """v0.3 (WP-E2, COMPANION-ADVANCED §12): no style attribute was created with setAttribute,
    and every style attribute in the body holds CSSOM custom properties only (--v, --x ...)."""
    styles = page.evaluate("() => [...document.querySelectorAll('body [style]')].map(n => n.getAttribute('style'))")
    custom = re.compile(r'(\s*--[a-z-]+:\s*[^;]+;?)+\s*')
    return page.evaluate('window.__styleAttrs') == [] and all(custom.fullmatch(s) for s in styles)


def run_node(code: str, stdin: str = '') -> str:
    return subprocess.run([NODE, '-e', code], input=stdin, capture_output=True, text=True,
                          check=True, cwd=CLIENT, timeout=60).stdout


def read_payload(name: str) -> dict:
    return json.loads((FIXTURES / f'{name}.json').read_text(encoding='utf-8'))['payload']


def to_model(module: str, name_or_payload) -> dict:
    """The model of ``lib/models/<module>.js`` for a fixture name or a payload."""
    data = read_payload(name_or_payload) if isinstance(name_or_payload, str) else name_or_payload
    code = ("let s='';process.stdin.on('data',d=>s+=d).on('end',()=>{"
            f"const m=require('./lib/models/{module}');"
            "const fn=Object.entries(m).find(([k,v])=>/^to[A-Z]\\w*Model$/.test(k))[1];"
            "process.stdout.write(JSON.stringify(fn(JSON.parse(s))))})")
    return json.loads(run_node(code, json.dumps(data)))


@pytest.fixture(scope='session')
def node():
    _require_tools()
    return run_node


@pytest.fixture(scope='session')
def payload():
    return read_payload


@pytest.fixture(scope='session')
def model():
    _require_tools()
    return to_model


@pytest.fixture(scope='session')
def page_file(tmp_path_factory) -> Path:
    _require_tools()
    html = subprocess.run([NODE, str(CLIENT / 'lib' / 'html.js'), NONCE], capture_output=True,
                          text=True, check=True, timeout=60).stdout
    target = tmp_path_factory.mktemp('webview') / 'panel.html'
    target.write_text(html, encoding='utf-8')
    return target


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
        warnings.warn('no Chromium for Playwright: the companion webview tests did not run.',
                      pytest.PytestWarning, stacklevel=1)
        pytest.skip('no Chromium available for Playwright')


@pytest.fixture(scope='session')
def browser():
    _require_tools()
    with playwright.sync_playwright() as p:
        b = _chromium(p)
        yield b
        b.close()


class Panel:
    def __init__(self, context, page, requests, errors, csp):
        self.context, self.page, self.requests, self.errors, self.csp = context, page, requests, errors, csp
        self.currency = None

    def send(self, message: dict) -> None:
        # Delivered synchronously: the `message` listeners (core.js) have run when this
        # returns. `window.postMessage` only queues a task, so an assertion that reads the
        # DOM without auto-waiting (`page.evaluate`, `get_attribute` on an element that
        # already exists) could run before the message was handled (WP-I: the intermittent
        # failure of test_ev3_navigation_selects_and_focuses_the_result).
        self.page.evaluate('m => window.dispatchEvent(new MessageEvent("message", {data: m}))',
                           {'v': 2, **message})

    def init(self, stage='v0', reviewer=False, learningLayer=True, chatInsert=False, task=None, study=STUDY_KEY,  # noqa: N803
             marimo=None):
        # `study`: the study key the controller sends (decision CR.2); None leaves it out.
        # `marimo`: the display of the Marimo launches (WP-A5); None leaves it out.
        message = {'type': 'init', 'stage': stage, 'reviewer': reviewer, 'learningLayer': learningLayer,
                   'chatInsert': chatInsert, 'task': task}
        if study is not None:
            message['study'] = study
        if marimo is not None:
            message['marimo'] = marimo
        self.send(message)

    def snapshot(self, model: dict) -> None:
        # As the controller: the snapshot carries the model's currency (decision CR.1).
        self.currency = model.get('currency')
        message = {'type': 'snapshot', 'revision': model['revision'], 'model': model}
        if self.currency:
            message['currency'] = self.currency
        self.send(message)

    def view_data(self, view: str, model: dict, revision=None, currency=None) -> None:
        # As the controller: a read carries the currency of the snapshot it was read at,
        # unless the test names another one.
        message = {'type': 'view_data', 'view': view,
                   'revision': model.get('revision', 0) if revision is None else revision, 'model': model}
        currency = self.currency if currency is None else currency
        if currency:
            message['currency'] = currency
        self.send(message)

    def posted(self) -> list:
        return self.page.evaluate('window.__posted')

    def state(self):
        return self.page.evaluate('window.__state')

    def violations(self) -> list:
        return self.page.evaluate('window.__csp')

    def clean(self) -> bool:
        """No remote request, page error, or CSP violation."""
        return not (self.requests or self.errors or self.csp or self.violations())


@pytest.fixture
def open_panel(browser, page_file):
    contexts = []

    def opener(color_scheme='light') -> Panel:
        context = browser.new_context(offline=True, color_scheme=color_scheme)
        contexts.append(context)
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
        return Panel(context, page, requests, errors, csp)

    yield opener
    for context in contexts:
        context.close()
