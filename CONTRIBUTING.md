# Contributing

The immediate milestone is the junior workflow in [the specification](docs/specs/JUNIOR-WORKFLOW.md). Start with [the handoff](docs/handoff/IMPLEMENTATION.md). Companion development is paused.

Use English for maintained prose, interface text, code comments, and new examples. Preserve original third-party data and identifiers required for compatibility. Keep changes focused and explain both behavior and validation in commits and pull requests.

## Environment

Use Python 3.13, uv, and a dedicated environment. Node.js is needed only for companion tests and extension development.

```sh
uv venv framework/.venv --python 3.13
uv pip install --python framework/.venv/bin/python -r framework/requirements.txt -r framework/requirements-pilot.txt -r framework/requirements-browser.txt
```

Dependency locking and Python packaging remain implementation work. Do not reuse an environment copied from another checkout.

## Engine checks

```sh
python3 scripts/check_layout.py
PYTHONPATH="$PWD/framework" framework/.venv/bin/python -m pytest -q framework/tests/test_pilot_revision.py framework/tests/test_quality.py framework/tests/test_discovery.py framework/tests/test_reliability.py framework/tests/test_classical.py
```

This is the validated targeted scope, not a claim that the entire inherited suite passes. Some historical tests concern currently suspended holdout and production paths. Do not enable those operations or weaken assertions to obtain a passing suite.

## Companion compatibility

The companion is optional. If changing its contracts, transport, or layout, install its separate environment and run its suites:

```sh
uv venv experimental/companion/runtime/.venv --python 3.13
uv pip sync --python experimental/companion/runtime/.venv/bin/python experimental/companion/runtime/requirements-bank.lock
experimental/companion/runtime/.venv/bin/python -m playwright install chromium
experimental/companion/runtime/.venv/bin/python -m pytest -q experimental/companion/runtime/tests
node --test experimental/companion/vscode-extension/test/assistant.test.js
```

Browser tests use loopback services, temporary databases, and a simulated model. A real Copilot acceptance session is separate. Do not run preparation scripts merely to view existing results: they train models.

## Data and local state

Keep dataset attribution and hashes. Separate exploratory results from independent evidence. Do not commit local sessions, credentials, environments, generated bundles, or personal annotations. Run tests in temporary studies and preserve existing user decisions.

A project license has not yet been selected. Contribution terms should be established before accepting external contributions for a public release.
