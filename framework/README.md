# Hypotrail framework

This directory is the canonical reusable engine source, inherited from the reviewed 4.2-dev kit. Existing notebooks and templates are foundations; the complete evolving narrative notebook remains to be built.

Read [the handoff](../docs/handoff/IMPLEMENTATION.md) before changing the engine. Case data and adapters belong in `../use-cases/`. Historical synthetic configurations are test fixtures under `tests/fixtures/legacy-project/`.

The engine still uses `OSML_ROOT` or the current directory to select its study. Do not run a mutating command at the repository root without an explicit project. The future junior entry point should make this choice explicit.

Source separation is complete. `pyproject.toml` and `uv.lock` provide an editable, locked environment; packaging notebook and template resources for a non-editable wheel remains implementation work. Keep `mlkit` as the compatibility namespace.
