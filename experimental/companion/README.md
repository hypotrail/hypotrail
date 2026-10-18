# Paused experimental companion

Status: **paused**. This code is retained for later UX research. The next milestone is Copilot chat + HTML + Marimo and does not depend on this feature.

- `runtime/`: tutorial UI, fallback server, contracts, event protocol, and tests.
- `vscode-extension/`: webview, VS Code model integration, transport, and tests.
- `artifacts/`: ignored local verification outputs.
- `feature.json`: a documentary priority marker, not a switch for an installed extension.

Datasets and preparation scripts live in `../../use-cases/`; internal runtime links preserve the existing tutorial contracts. `runtime/journeys/` and `prepare_discovery.py` remain tutorial-specific.

Build explicitly with `python3 experimental/companion/vscode-extension/scripts/package.py` from the repository root. It regenerates `assets/`, `engine/`, and the VSIX. Edit sources, not generated copies. Browser tests use a simulated model provider and do not verify a live Copilot connection.
