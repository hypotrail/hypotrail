# Hypotrail

Hypotrail is an experimental method for agent-assisted machine learning studies: *do your ML study with an agent; Hypotrail guarantees that numbers, partitions, and decisions are traceable, and says what is not yet defensible.*

**v0.2** guides a junior through a study in **Claude Code chat** (from v0.3, first on Hotel booking demand): a data card before any decision, a final test sealed at creation and opened once, cross-validation and model variants, ten decisions in a binary study (nine in a regression study) confirmed in the junior's own words (guided mode by default, training and express modes available), model diagnostics, one evolving offline HTML report, and a generated Marimo notebook whose cells recompute every figure. GitHub Copilot is the longer-term target but is not tested yet, and no human junior has used it. A study panel for VS Code exists behind a feature flag that is off by default; the old visual companion is paused.

Repository: https://github.com/hypotrail/hypotrail. Workshop participants: [installation guide](docs/workshop/README.md) ([page version](docs/workshop/README.html)).

Start with [the implementation entry point](docs/START-HERE.md); [the handoff](docs/handoff/IMPLEMENTATION.md) lists what works and what does not.

## Quickstart (Linux, macOS, or WSL)

```sh
uv sync --project framework --group dev
uv run --project framework hypotrail init --case use-cases/hotel-booking/case.yaml --study ~/studies/hotel
cd ~/studies/hotel && claude
```

The discovery case is [Hotel booking demand](use-cases/hotel-booking/README.md) (Resort Hotel): which new bookings the reservations team should contact, or ask for a deposit, when it can handle only some, with a clear timeline from the booking to the cancellation and leakage traps to find. Then try [Bank Marketing](use-cases/bank-marketing/README.md) (`use-cases/bank-marketing/case.yaml`, the v0.1/v0.2a reference) or its [full file in time order](use-cases/bank-marketing-full/README.md) (`use-cases/bank-marketing-full/case.yaml`, a temporal final test), and [Auto MPG](use-cases/auto-mpg/README.md) for regression. [Online Shoppers](use-cases/online-shoppers/README.md) is an advanced case: its scenario has a documented limitation (the target is known at the prediction moment).

Create the study in a folder **outside this repository** (here `~/studies/hotel`): Claude Code also loads instruction files from parent folders. `init` seals the final test, installs the study agent's instructions (`CLAUDE.md`, a skill, and a `/hypotrail-resume` command), and writes `.vscode/settings.json` pointing VS Code (and its Marimo extension) at the engine's interpreter, unless that file exists. Open the folder with Claude Code and say what you want to do; the agent shows the data card, proposes each decision, and records it only with your own words or an explicit delegation. The report `reports/study.html` and the notebooks in `notebooks/` are generated after each recorded change (or with `hypotrail render`). Open the notebooks with the engine's Marimo:

```sh
uv run --project framework marimo run  ~/studies/hotel/notebooks/study_generated.py   # read
uv run --project framework marimo edit ~/studies/hotel/notebooks/workbench.py         # your experiments
```

With GitHub Copilot instead (VS Code 1.109 or later, for the interactive choice picker): open the study folder in VS Code (`code ~/studies/hotel`), open the Chat view, pick the agent **Hypotrail** in the agent picker (installed by `init` as `.github/agents/hypotrail.agent.md`; it reads `.github/copilot-instructions.md` and the skill), and say what you want to do. At each decision it opens a picker in the study language that holds the key facts, the decision as a quoted block, and the closed question ("Do you adopt this decision?", or "Adoptez-vous cette décision ?" in a French study), with three options: adopt, change something, explain first. Check that `vscode/askQuestions` is enabled in the chat tools picker. The Copilot files are generated from the Claude Code instructions and are not covered by the automated acceptance runs.

Optional study panel (VS Code 1.90 or later, flag off by default): `HYPOTRAIL_COMPANION=1 HYPOTRAIL_COMPANION_STAGE=v3 code --extensionDevelopmentPath="$PWD/clients/vscode-companion" ~/studies/hotel`, then "Hypotrail: open the study panel". Its "Open in Marimo" buttons open the study's three notebooks in a VS Code terminal: the generated notebook with `marimo run` (read), and the editable study copy (`notebooks/study_editable.py`) and the workbench with `marimo edit`. See [its README](clients/vscode-companion/README.md); a step-by-step demo is in [the owner review guide](docs/plans/V0.2-OWNER-REVIEW.md#owner-demo-2-script).

| Directory | Purpose |
|---|---|
| [framework/](framework/README.md) | Reusable Python engine, notebook sources, templates, and tests |
| [use-cases/](use-cases/README.md) | Hotel booking demand, Bank Marketing (sample and full file), Auto MPG, Online Shoppers, and two scikit-learn cases: data, context, adapters, and reference results |
| [clients/vscode-companion/](clients/vscode-companion/README.md) | Study panel for VS Code, a client of the `hypotrail` CLI behind a feature flag that is off by default (stages v0 to v3, default v0) |
| [experimental/companion/](experimental/companion/README.md) | Paused browser and VS Code companion experiment |
| [docs/](docs/START-HERE.md) | Product specification, architecture, design review, and implementation handoff |
| `scripts/` | Repository maintenance checks; `scripts/workshop/` prepares workshop studies ([participant guide](docs/workshop/README.md), in French: Codespaces after a fork, or local) |

## Development

Use Python 3.13 and uv on Linux, macOS, or WSL. The engine relies on POSIX file locking; native Windows is not supported. Create a dedicated environment; do not copy an environment from another checkout.

`framework/pyproject.toml` and `framework/uv.lock` define the reproducible environment. See [CONTRIBUTING.md](CONTRIBUTING.md) for the full gate (with the `browser` group), the opt-in Marimo spike and agent acceptance, and current limitations.

## Data and project status

The examples use public UCI datasets. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for provenance and attribution. Included model outputs are exploratory teaching references, not a production assessment.

Historical local sessions, archives, virtual environments, and generated extension bundles are excluded. The repository works without the original development folder. `mlkit` and `OSML_*` remain compatibility identifiers inside the engine.

This repository is being prepared for a future open-source release. A project license has not yet been selected.
