# Experimental companion runtime

Development is paused. Read [the feature status](../README.md) and root instructions before changing or installing the companion.

The shared UI renders projects validated by `contracts.py`:

- `projects/registry.json`: project identifiers and directories.
- `projects/<name>/project.json`: provenance, business facts and status, variables, activity content.
- `projects/<name>/results.json`: protocols, metrics with units, scope, results, and limitations.
- `journeys/<id>.json`: activities, moments, components, prerequisites, choices, and teaching guidance.

The `projects/` link points to root `use-cases/`. See [ADDING-A-DATASET.md](ADDING-A-DATASET.md). This is configuration-assisted onboarding, not automatic interpretation of arbitrary datasets.

## Included cases

Bank Marketing uses 4,521 public UCI telephone campaign records. It studies pre-call contact selection, compares a constant reference, demonstrates leakage from `duration`, and explores selection thresholds. Its random stratified 70/30 split is exploratory; complete dates and customer identifiers are absent, and observed subscriptions do not establish the causal effect of a call.

Auto MPG uses 398 historical cars and numeric target `mpg`. Training uses 1970–1978 and validation 1979–1982. Compare the training median, a weight-only regression, and a technical-feature regression. A random split is an explicitly labeled counterexample. Errors use mpg rather than classification percentages. Some units and origin codes remain undocumented; some car names repeat across years.

Attribution and source files are documented in each case and root `THIRD_PARTY_NOTICES.md`. Results were calculated explicitly by the preparation scripts. Interface interactions select existing results; they do not retrain models.

## State and transport

Each project owns `.local/<session_name>.sqlite`; no conversation or confirmation transfers between cases. Result hashes depend on data, protocols, and values rather than titles or prose. Historical schema versions are migrated in place when an existing session is opened.

VS Code uses message passing without an HTTP server. Optional browser fallback: `python bridge.py serve [--project ID]`, bound to `127.0.0.1`, without panel AI. `bank-tutorial.html` is a historical offline export, not synchronized state.

CLI examples: `python bridge.py status --project uci-auto-mpg-v1`, `python bridge.py validate --project ID`, and `python bridge.py explain --message "..."`. Standard Python is sufficient for these engine operations. Use a temporary `--db` path for verification rather than touching a personal session.

## Reproducing calculations

From this directory, create a dedicated uv environment and install `requirements-bank.lock`. Explicitly running `prepare_bank.py` or `prepare_auto_mpg.py` trains models and updates outputs. `prepare_discovery.py` then adds training-only descriptive charts without fitting. Rebuild the extension only when needed, using `python ../vscode-extension/scripts/package.py`.

Bank EDA uses exactly the 3,164 training indices in `data/split.json`; Auto MPG uses 280 training cars. `results.display.eda` retains row indices and a source hash. Charts are local SVG/bar views with keyboard interaction and tables. Selecting a mark changes no data or applied choice. Preparing a chart question fills the composer without sending it and preserves an existing draft.

Use the root contribution guide for complete validation commands. Browser tests use a simulated model provider, not a live Copilot connection.
