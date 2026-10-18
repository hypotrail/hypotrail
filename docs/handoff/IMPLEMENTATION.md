# Implementation handoff

The repository contains the reusable engine and public-data tutorials. **The new junior workflow remains to be implemented.** The initial import prepares source boundaries and context; it does not deliver that future experience.

## Where to start

Work at the root of `hypotrail`. Read `AGENTS.md`, the user's specification, and `docs/specs/JUNIOR-WORKFLOW.md`. Put reusable work in `framework/` and the first study in `use-cases/bank-marketing/`. Use Auto MPG as the second adaptation check.

Companion development is paused. Its protocols and tests can inform design, but the new workflow must not require its UI or Copilot tutorial tools.

## Existing capabilities and gaps

| Source | Reusable capability | Current limitation |
|---|---|---|
| `framework/mlkit/pilot.py` | Historical guidance, answers, progress, revisions | Compare its contract and phases with the new specification |
| `framework/mlkit/reliability.py` | Idempotence, revisions, recovery, stale results | Integrate these controls into every new mutation |
| `framework/mlkit/discover.py` | Discovery, reports, exposure records | Connect to the new plan and evolving outputs |
| `framework/mlkit/task_contract.py`, `classical.py` | Task contracts and calculations | Different from the companion's `project.json` contract |
| `framework/mlkit/notebooks.py`, `framework/notebooks/` | Rendering and notebook foundations | Not yet a complete narrative notebook that preserves user cells |
| `framework/tests/` | Engine, quality, revision, and calculation checks | Some historical tests concern suspended holdout operations; do not reactivate them to obtain passing tests |
| `use-cases/*/project.json`, `results.json` | Documented context, EDA, tutorial results | No junior session or human decisions should be imported automatically |

The engine is canonical under `framework/`. Its synthetic configurations are fixtures under `framework/tests/fixtures/legacy-project/`. Historical archives and sessions are not repository dependencies.

## Implementation priorities

1. Define junior study state and its relationship to existing engine contracts. Separate context, proposals, decisions, executions, and results. Make migration explicit.
2. Provide an explicit per-project entry point. The engine still uses the Python path and `OSML_ROOT`; packaging has not been completed.
3. Build an adaptive visible plan and state-based resumption. Define when Copilot recommends, acts, and asks a useful question.
4. Generate HTML and notebook reference sections from the same evidence, with revisions and invalidation. Handle annotations and concurrent notebook edits before regeneration.
5. Complete Bank through conclusion, then Auto MPG with shared primitives. Loading historical results is not a new experiment.

First slice: structural inspection → proposed plan → useful confirmation → authorized EDA → consistent HTML and notebook → resumption in a new chat. Then add preparation, baseline, modeling, error analysis, and conclusion. Test failures and preservation alongside the successful path.

## Environments and verification

Follow `CONTRIBUTING.md`. Use uv and dedicated environments. The framework does not yet have a `pyproject.toml` or `uv.lock`. Introducing packaging must account for notebook and template resources. Existing requirement constraints are not a reproducibility guarantee.

The default validation scope is the targeted engine suite, repository integrity checks, and optional companion compatibility suites. Do not run a state-mutating pilot command at the repository root without selecting an explicit study. Browser tests require Playwright Chromium and a loopback port; their model provider is simulated.

See `docs/handoff/IMPORT-CHECKS.md` for validation performed during import. A real Copilot acceptance session remains separate from automated tests.

## Preservation

Do not reset existing study state to install changes. No previous personal session was imported. The public datasets and exploratory reference outputs were retained with provenance; tutorial scenario facts are not new human confirmations.

## Completion criterion

A junior user can follow Bank in Copilot, consult one current HTML report, manipulate the notebook at each phase, resume after interruption, and understand results without losing choices or notes. Outputs share evidence and limitations. Auto MPG demonstrates adaptation to another task. Identify real-user checks separately from automated tests.
