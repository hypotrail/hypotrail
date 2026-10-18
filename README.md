# Hypotrail

Hypotrail is an experimental method for agent-assisted machine learning studies: *do your ML study with an agent; Hypotrail guarantees that numbers, partitions, and decisions are traceable, and says what is not yet defensible.*

**v0.1** guides a junior through a Bank Marketing study in **Claude Code chat**, with one evolving offline HTML report and a generated Marimo notebook. GitHub Copilot is the longer-term target but is not tested yet. The visual companion is an experimental feature whose development is paused.

Start with [the implementation entry point](docs/START-HERE.md); [the handoff](docs/handoff/IMPLEMENTATION.md) lists what works and what does not.

## Quickstart (Linux, macOS, or WSL)

```sh
uv sync --project framework --group dev
uv run --project framework hypotrail init --case use-cases/bank-marketing/case.yaml --study ~/studies/bank
cd ~/studies/bank && claude
```

Create the study in a folder **outside this repository** (here `~/studies/bank`): Claude Code also loads instruction files from parent folders. `init` installs the study agent's instructions (`CLAUDE.md`, a skill, and a `/hypotrail-resume` command) in that folder. Open it with Claude Code and say what you want to do; the agent reads the study state, proposes each decision, and records it only with your own words or an explicit delegation. The report `reports/study.html` and the notebooks in `notebooks/` are generated after each recorded change.

| Directory | Purpose |
|---|---|
| [framework/](framework/README.md) | Reusable Python engine, notebook sources, templates, and tests |
| [use-cases/](use-cases/README.md) | Bank Marketing and Auto MPG data, context, adapters, and reference results |
| [clients/vscode-companion/](clients/vscode-companion/README.md) | Study panel for VS Code, a client of the `hypotrail` CLI behind a feature flag that is off by default (v0) |
| [experimental/companion/](experimental/companion/README.md) | Paused browser and VS Code companion experiment |
| [docs/](docs/START-HERE.md) | Product specification, architecture, design review, and implementation handoff |
| `scripts/` | Repository maintenance checks |

## Development

Use Python 3.13 and uv on Linux, macOS, or WSL. The engine relies on POSIX file locking; native Windows is not supported. Create a dedicated environment; do not copy an environment from another checkout.

`framework/pyproject.toml` and `framework/uv.lock` define the reproducible environment. See [CONTRIBUTING.md](CONTRIBUTING.md) for the full gate (with the `browser` group), the opt-in Marimo spike and agent acceptance, and current limitations.

## Data and project status

The examples use public UCI datasets. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for provenance and attribution. Included model outputs are exploratory teaching references, not a production assessment.

Historical local sessions, archives, virtual environments, and generated extension bundles are excluded. The repository works without the original development folder. `mlkit` and `OSML_*` remain compatibility identifiers inside the engine.

This repository is being prepared for a future open-source release. A project license has not yet been selected.
