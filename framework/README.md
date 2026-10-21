# Hypotrail framework

This directory is the canonical reusable engine source, inherited from the reviewed 4.2-dev kit. The junior study engine is `mlkit/study/` (CLI `hypotrail`, every command takes `--study DIR`): it writes the HTML report and generates the study's Marimo notebook and workbench. The legacy notebooks and templates in `notebooks/` and `templates/` are older foundations.

Read [the handoff](../docs/handoff/IMPLEMENTATION.md) before changing the engine. Case data and adapters belong in `../use-cases/`. Historical synthetic configurations are test fixtures under `tests/fixtures/legacy-project/`.

The legacy pilot (`mlkit/pilot.py` and its modules) still uses `OSML_ROOT` or the current directory to select its project; do not run a mutating legacy command at the repository root without an explicit project. The junior entry point, `hypotrail`, always names its study explicitly.

Source separation is complete. `pyproject.toml` and `uv.lock` provide an editable, locked environment; packaging notebook and template resources for a non-editable wheel remains implementation work. Keep `mlkit` as the compatibility namespace.
