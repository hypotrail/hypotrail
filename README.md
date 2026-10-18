# Hypotrail

Hypotrail is an experimental method for agent-assisted machine learning development. Its next milestone is a guided junior workflow with **GitHub Copilot chat, an evolving HTML report, and an explanatory Marimo notebook**.

The reusable engine and two public-data examples are included. The new junior workflow is specified and remains to be implemented. The visual companion is an experimental feature whose development is paused.

Start with [the implementation entry point](docs/START-HERE.md).

| Directory | Purpose |
|---|---|
| [framework/](framework/README.md) | Reusable Python engine, notebook sources, templates, and tests |
| [use-cases/](use-cases/README.md) | Bank Marketing and Auto MPG data, context, adapters, and reference results |
| [experimental/companion/](experimental/companion/README.md) | Paused browser and VS Code companion experiment |
| [docs/](docs/START-HERE.md) | Product specification, architecture, design review, and implementation handoff |
| `scripts/` | Repository maintenance checks |

## Development

Use Python 3.13 and uv. Create a dedicated environment; do not copy an environment from another checkout.

```sh
uv venv framework/.venv --python 3.13
uv pip install --python framework/.venv/bin/python -r framework/requirements.txt -r framework/requirements-pilot.txt -r framework/requirements-browser.txt
python3 scripts/check_layout.py
PYTHONPATH="$PWD/framework" framework/.venv/bin/python -m pytest -q framework/tests/test_pilot_revision.py framework/tests/test_quality.py framework/tests/test_discovery.py framework/tests/test_reliability.py framework/tests/test_classical.py
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the test scopes and current limitations. Existing dependency files are inherited constraints, not a reproducibility guarantee for the future workflow.

## Data and project status

The examples use public UCI datasets. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for provenance and attribution. Included model outputs are exploratory teaching references, not a production assessment.

Historical local sessions, archives, virtual environments, and generated extension bundles are excluded. The repository works without the original development folder. `mlkit` and `OSML_*` remain compatibility identifiers inside the engine.

This repository is being prepared for a future open-source release. A project license has not yet been selected.
