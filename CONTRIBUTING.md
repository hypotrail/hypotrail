# Contributing

v0.1 of the junior workflow ([the specification](docs/specs/JUNIOR-WORKFLOW.md)) is implemented for Bank Marketing with Claude Code. Start with [the handoff](docs/handoff/IMPLEMENTATION.md) for its capabilities and limits, and [the checklist](docs/acceptance/V0.1-CHECKLIST.md) for its evidence. Companion development is paused.

Use English for maintained prose, interface text, code comments, and new examples. Preserve original third-party data and identifiers required for compatibility. Keep changes focused and explain both behavior and validation in commits and pull requests.

## Environment

Use Python 3.13, uv, and a dedicated environment. Node.js is needed only for companion tests and extension development.

Supported platforms are Linux, macOS, and WSL. The engine relies on POSIX file locking (`fcntl`); native Windows is not supported.

The framework is a uv project (`framework/pyproject.toml`, locked by `framework/uv.lock`). Create its environment in `framework/.venv` with the `dev` group:

```sh
uv sync --project framework --group dev
```

Add `--group browser` for local browser tests, then install Chromium with `uv run --project framework python -m playwright install chromium`. The optional EBM baseline (`interpret-core`) is not a core dependency. Do not run `uv init` in this project, and do not reuse an environment copied from another checkout.

## Engine checks

Test scopes:

| Scope | What it is | How it runs |
|---|---|---|
| U, unit | Pure functions and in-process checks | the gate |
| S, simulated | Real `hypotrail` CLI processes (killed with real signals where needed), headless Marimo, offline Playwright | the gate (the Playwright test needs the `browser` group) |
| Spike | Marimo preservation spike (ADR 0001), the upgrade gate for the pinned Marimo | opt-in, `HYPOTRAIL_RUN_SPIKES=1` |
| A, agent | Claude Code agentic acceptance (`claude -p`), "Claude Code acceptance", not Copilot | opt-in, `HYPOTRAIL_AGENT_ACCEPTANCE=1`, costs model spend |

### The gate

Run it, fully green, before each commit. It installs the `browser` group, so the offline report test (`framework/tests/study/deliverables/test_html_offline.py`, Playwright) runs instead of being skipped:

```sh
uv sync --project framework --group dev --group browser
uv run --project framework python -m playwright install chromium
python3 scripts/check_layout.py
uv run --project framework python -m pytest -q framework/tests/test_pilot_revision.py framework/tests/test_quality.py framework/tests/test_discovery.py framework/tests/test_reliability.py framework/tests/test_classical.py framework/tests/test_env_smoke.py framework/tests/test_synthetic_case.py framework/tests/study framework/tests/acceptance
```

At the v0.1 closure it reports about 800 passed; the only skips are the 34 opt-in agent scenarios of `framework/tests/acceptance/agent/test_scenarios.py`. Without the `browser` group the same command passes but skips the offline browser test with a `PytestWarning` that says so; that run is not the full gate.

`framework/tests/study/` covers the junior study engine, including real `hypotrail` CLI processes (`test_cli_decisions.py`, `test_walkthrough.py` on Bank, the synthetic case, and WDBC; `test_regression_walkthrough.py` on Auto MPG, the synthetic regression case, and diabetes; `test_perturbations.py` on 26 rewritten synthetic cases) and the frozen CLI contract (`test_contract_freeze.py`, see `docs/specs/CLI-CONTRACT.md`). A contract change updates the document and the freeze test in the same commit. The `hypotrail` command is installed in `framework/.venv` by `uv sync`; run it with `uv run --project framework hypotrail <command> --study DIR`. Create test studies in a temporary directory outside the repository.

### Marimo spike (opt-in)

Run it after any Marimo upgrade or change to notebook generation; its four strict `xfail` tests document Marimo limitations and turn into failures if Marimo changes:

```sh
HYPOTRAIL_RUN_SPIKES=1 uv run --project framework python -m pytest -q framework/tests/spikes
```

### Agent acceptance (opt-in, costs money)

The agent graders have unit tests on canned transcripts that need no model; they are part of the gate (`framework/tests/acceptance`).

The agent scenarios in `framework/tests/acceptance/agent/` (marker `agent_acceptance`) launch real `claude -p` sessions on Opus. They are skipped unless `HYPOTRAIL_AGENT_ACCEPTANCE=1` is set. Each scenario costs roughly $0.15 to $1 of model spend, an E1 run with its blind reviews about $2 to $4; the v0.1 evaluation cost about $63 in all. Set a budget with the drivers' `--total-budget`. Results are labelled "Claude Code acceptance" and do not count as Copilot acceptance. The S1–S9 scenarios are run with `scenarios.py`, the E1 steelman with `e1.py` ([protocol](docs/research/E1-STEELMAN.md); reproduction commands at the end of each report in `docs/acceptance/runs/`). Keep raw runs outside the repository.

### Alternative setup

Without uv project commands, using the inherited requirement files and `PYTHONPATH` (legacy scope only):

```sh
uv venv framework/.venv --python 3.13
uv pip install --python framework/.venv/bin/python -r framework/requirements.txt -r framework/requirements-pilot.txt -r framework/requirements-browser.txt
PYTHONPATH="$PWD/framework" framework/.venv/bin/python -m pytest -q framework/tests/test_pilot_revision.py framework/tests/test_quality.py framework/tests/test_discovery.py framework/tests/test_reliability.py framework/tests/test_classical.py framework/tests/test_env_smoke.py
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
