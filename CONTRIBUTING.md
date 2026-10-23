# Contributing

v0.2 of the junior workflow ([the specification](docs/specs/JUNIOR-WORKFLOW.md)) is implemented with Claude Code, on Online Shoppers first, then Bank Marketing, Bank Marketing full, and Auto MPG. Start with [the handoff](docs/handoff/IMPLEMENTATION.md) for its capabilities and limits, and [the v0.2 checklist](docs/acceptance/V0.2-CHECKLIST.md) for its evidence ([v0.1 checklist](docs/acceptance/V0.1-CHECKLIST.md) for the earlier slice). The old companion is paused; a study panel for VS Code (`clients/vscode-companion/`, ADRs 0003 and 0004) exists behind a feature flag that is off by default, with its stages v1 to v3 behind the stage setting (default `v0`).

Use English for maintained prose, interface text, code comments, and new examples. Preserve original third-party data and identifiers required for compatibility. Keep changes focused and explain both behavior and validation in commits and pull requests.

## Environment

Use Python 3.13, uv, and a dedicated environment. Node.js (22 or later) is needed for the study panel's tests and for companion development.

Supported platforms are Linux, macOS, and WSL. The engine relies on POSIX file locking (`fcntl`); native Windows is not supported.

The framework is a uv project (`framework/pyproject.toml`, locked by `framework/uv.lock`). Create its environment in `framework/.venv` with the `dev` group:

```sh
uv sync --project framework --group dev
```

Add `--group browser` for local browser tests, then install Chromium with `uv run --project framework python -m playwright install chromium`. `interpret-core` (MIT, pinned) is a core dependency since v0.3: the study engine fits the Explainable Boosting Machine as a model family ([ADR 0007](docs/decisions/0007-trial-budget-and-model-families.md)); the legacy `mlkit.baselines` EBM baseline uses the same package. Do not run `uv init` in this project, and do not reuse an environment copied from another checkout.

## Engine checks

Test scopes:

| Scope | What it is | How it runs |
|---|---|---|
| U, unit | Pure functions and in-process checks | the gate |
| S, simulated | Real `hypotrail` CLI processes (killed with real signals where needed), headless Marimo, offline Playwright | the gate (the Playwright test needs the `browser` group) |
| Spike | Marimo preservation spike (ADR 0001), the upgrade gate for the pinned Marimo | opt-in, `HYPOTRAIL_RUN_SPIKES=1` |
| A, agent | Claude Code agentic acceptance (`claude -p`), "Claude Code acceptance", not Copilot | opt-in, `HYPOTRAIL_AGENT_ACCEPTANCE=1`, costs model spend |

### The gate

Run it, fully green, before each commit. It installs the `browser` group, so the offline report test (`framework/tests/study/deliverables/test_html_offline.py`, Playwright) runs instead of being skipped, and the `diagnostics` and `uncertainty` extras, so the Evidently and MAPIE tests of `framework/tests/study/libraries/` run instead of being skipped (library integration v1, [LIBRARIES-V1](docs/handoff/LIBRARIES-V1.md); the runtime wheel test needs `uv` on the path):

```sh
uv sync --project framework --group dev --group browser --extra diagnostics --extra uncertainty
uv run --project framework python -m playwright install chromium
python3 scripts/check_layout.py
uv run --project framework python -m pytest -q framework/tests/test_pilot_revision.py framework/tests/test_quality.py framework/tests/test_discovery.py framework/tests/test_reliability.py framework/tests/test_classical.py framework/tests/test_env_smoke.py framework/tests/test_synthetic_case.py framework/tests/study framework/tests/acceptance
node --test clients/vscode-companion/test/*.test.js
uv run --project framework python -m pytest -q -p no:cacheprovider clients/vscode-companion/test
```

The last two lines test the study panel (`clients/vscode-companion/`, ADRs 0003 and 0004), and both must be green. The Node line runs the unit tests (a fake `vscode` module and a fake CLI) and the integration tests that drive the real controller and the real `hypotrail` CLI: `integration.test.js` on a temporary synthetic study, and `integration-v1/v2/v3.test.js` on temporary Bank Marketing and Auto MPG studies made from the committed cases (only read); about a minute in all, mostly the Bank fits. The pytest line runs the offline Playwright tests of the webview document (one file per view), the client and engine key lists (`test_contract_keys.py`), the fixture drift check against real payloads (`test_fixture_drift.py`, which also captures again from the live engine), and the requirement coverage (`test_requirement_coverage.py`); about a minute and a half. Run that pytest command separately: pytest takes its configuration from `framework/pyproject.toml` only when every path is under `framework/`. After an engine change that alters a payload, run `uv run --project framework python clients/vscode-companion/test/fixtures/capture.py` and fix the hand-written fixtures the drift test names. None of these runs a real VS Code; the manual checklist is `clients/vscode-companion/MANUAL-TEST.md`.

The pytest line includes the panel's visual gate (`test_webview_gate.py`, v0.3 WP-E3; spec A11Y-4). Its structural assertions run every tab on the captured payloads at 1280, 900 and 420 px, in Light Modern, Dark Modern and High Contrast, in English and in French: no horizontal overflow of the page or of any card, the six sizes of the type scale, no raw id or token in the prose, nothing underlined, the text-token contrasts. Its pixel baselines (`clients/vscode-companion/test/baselines/`, about 8 MB) compare each tab at 420 and 900 px in the three themes and both languages, first viewport plus the main chart, inside Chromium with a small tolerance (a channel moved by more than 24 on more than 0.1 % of the pixels fails). Rendering is pinned to the installed DejaVu Sans fonts; without them (non-Linux, no `fc-match`) the pixel tests skip with a warning and the structural ones still run. A failure writes the capture, the baseline and a diff image to `clients/vscode-companion/.local/baseline-diff/`. After an intended visual change, rewrite the baselines that differ with

```sh
uv run --project framework python -m pytest -q -p no:cacheprovider clients/vscode-companion/test/test_webview_gate.py --update-baselines
```

and **have the owner review every changed baseline from the diff images** in that folder before committing the new PNGs; a baseline change without that review is not accepted. The gate adds about three minutes to the pytest line.

At the v0.1 closure it reported about 800 passed, 1159 after the advanced companion's integration (WP-I), and 1603 passed at the v0.2 closure (the Node line 236 tests, the panel pytest line 322 passed); the only skips are the opt-in agent scenarios of `framework/tests/acceptance/agent/test_scenarios.py` (34 at v0.1, 66 since WP-B6b). Without the `browser` group the same command passes but skips the offline browser test with a `PytestWarning` that says so; that run is not the full gate.

`framework/tests/study/` covers the junior study engine, including real `hypotrail` CLI processes (`test_cli_decisions.py`, `test_walkthrough.py` on Bank, the synthetic case, and WDBC; `test_regression_walkthrough.py` on Auto MPG, the synthetic regression case, and diabetes; `test_perturbations.py` on 26 rewritten synthetic cases) and the frozen CLI contract (`test_contract_freeze.py`, see `docs/specs/CLI-CONTRACT.md`). A contract change updates the document and the freeze test in the same commit. The `hypotrail` command is installed in `framework/.venv` by `uv sync`; run it with `uv run --project framework hypotrail <command> --study DIR`. Create test studies in a temporary directory outside the repository.

### Library integration v1 (opt-in parts)

The installation matrix of the extras (base, `diagnostics`, `uncertainty`, both; four fresh environments from the lock) runs with `HYPOTRAIL_EXTRAS_MATRIX=1`; the Hypothesis state machine's budget is raised with `HYPOTRAIL_HYPOTHESIS_EXAMPLES` and `HYPOTRAIL_HYPOTHESIS_STEPS`. Regenerate the JSON schemas of the contracts after a model change with `uv run --project framework python -m hypotrail_runtime.schemas` (the gate checks them).

### Marimo spike (opt-in)

Run it after any Marimo upgrade or change to notebook generation; its four strict `xfail` tests document Marimo limitations and turn into failures if Marimo changes:

```sh
HYPOTRAIL_RUN_SPIKES=1 uv run --project framework python -m pytest -q framework/tests/spikes
```

### Agent acceptance (opt-in, costs money)

The agent graders have unit tests on canned transcripts that need no model; they are part of the gate (`framework/tests/acceptance`).

The agent scenarios in `framework/tests/acceptance/agent/` (marker `agent_acceptance`) launch real `claude -p` sessions on Opus. They are skipped unless `HYPOTRAIL_AGENT_ACCEPTANCE=1` is set. Each scenario costs roughly $0.15 to $1 of model spend, an E1 run with its blind reviews about $2 to $4; the v0.1 evaluation cost about $63 in all. Set a budget with the drivers' `--total-budget`. Results are labelled "Claude Code acceptance" and do not count as Copilot acceptance. The S0–S13 scenarios are run with `scenarios.py` (cases `bank`, `bank-full`, `hotel`, `shoppers`, `auto-mpg`, `synthetic`; from v0.3 the scenario lists use `hotel`, the discovery case, where they used `shoppers`), the E1 steelman with `e1.py` ([protocol](docs/research/E1-STEELMAN.md); reproduction commands at the end of each report in `docs/acceptance/runs/`). Keep raw runs outside the repository.

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
