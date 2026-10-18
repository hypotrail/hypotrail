# Repository architecture

## Canonical layout

```text
AGENTS.md
.github/copilot-instructions.md
framework/
  mlkit/                     reusable engine inherited from the reviewed kit
  notebooks/                 reusable notebook sources
  templates/                 rendering templates
  tests/
    fixtures/legacy-project/ synthetic context required by historical tests
  requirements*.txt          inherited dependencies
use-cases/
  registry.json              existing tutorial registry
  bank-marketing/
    project.json             existing tutorial context
    results.json             exploratory reference results
    prepare_bank.py          explicit data preparation and experiment
    data/                    public source data, split, and existing predictions
    tutorial-results.json    historical result format
    bank-tutorial.html    historical offline teaching export
  auto-mpg/
    project.json
    results.json
    prepare_auto_mpg.py
    data/
experimental/companion/
  runtime/                   tutorial UI, bridge, protocol, tests
  vscode-extension/          extension sources and Node tests
  feature.json               paused status, default_enabled false
scripts/check_layout.py       repository and dataset integrity checks
```

## Dependency direction

The framework must not depend on Bank Marketing, Auto MPG, or the companion. Business adaptations belong to use cases. The future engine should consume explicit project contracts rather than recognize datasets by name in generic code.

The experimental runtime accesses case resources through repository-relative symbolic links. These links stay inside the checkout. `journeys/` and `prepare_discovery.py` still belong to that tutorial, not to the future junior orchestration. The Bank and Auto MPG preparation scripts physically reside in their case directories.

`framework/mlkit/` is the canonical engine source. Its extraction did not make the old kit an installable Python library. Python packaging, explicit project selection, and resource distribution remain implementation work.

## Sources, outputs, and state

- Reusable sources: `framework/mlkit`, `framework/templates`, and `framework/notebooks`.
- Case sources: `use-cases/<id>/prepare_*.py`, context, and variable dictionary.
- Public reference data: `use-cases/<id>/data`, with provenance in `project.json`.
- Historical results: tutorial `results.json`, predictions, and HTML. They are reference artifacts, not new junior study evidence.
- Proposed future outputs: case `reports/study.html`, `notebooks/study.py`, and distinct persistent study state. These are conventions, not implemented deliverables.
- Local state: `.pilot`, `.osml`, `.local`, and equivalent directories remain untracked.

## Portability

No source file requires the previous development checkout. Historical archives and sessions were left there as a local backup and were not imported. Do not copy a virtual environment; recreate it with uv.

Internal symbolic links require a checkout that preserves links. Packaging the extension materializes its resources. A future Windows distribution should either enable links or replace this compatibility arrangement with configurable resource paths.

`mlkit`, `OSML_*`, some historical filenames, and contract identifiers remain stable for compatibility. Maintained prose and interface content use English. Third-party source data retains its original form.

## Generated artifacts

Extension `assets/`, `engine/`, VSIX bundles, browser artifacts, caches, environments, and local sessions are ignored. Run the explicit packaging script when an extension bundle is needed; do not edit generated copies.

The companion's paused marker records product priority. It does not disable an extension already installed in VS Code. No installed extension is required for framework development.
