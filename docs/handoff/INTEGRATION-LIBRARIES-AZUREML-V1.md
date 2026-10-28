# Integration I1 — library integration (A) + Azure ML export (B) + main

Status: **ready to merge into `main` after review — validated locally; cloud not qualified.** Nothing was merged
into `main`; no branch was deleted or force-pushed.

## Branches and SHAs

| Item | SHA | Note |
|---|---|---|
| Base (both workstreams) | `581c7b3723629260a18e1281ef9e18583ae060a7` | `merge-base` of A, B and `main` |
| A — libraries (`claude/zealous-franklin-gywbya`, brief name `feature/libraries-v1`) | `46850ac` | 6 commits since the base |
| B — Azure ML export (`claude/cool-lamport-q68gsv`, brief name `feature/azureml-export-v1`) | `3c306fd` | 3 commits since the base |
| Target `origin/main` | `506180a` | 1 commit since the base (explicit binary model choice, editable notebook) |
| Merge of B into A | `f0b3a0a` | history kept (`--no-ff`) |
| Merge of `main` | `6be4a79` | no textual conflict |
| Integration HEAD | last commit of `claude/zealous-franklin-gywbya` | the session can push only to this branch; it plays the role of `integration/libraries-azureml-v1` |

The integration branch contains `main`; it merges into `main` without conflict at the time
of writing.

## Conflicts and resolutions

| Where | Cause | Resolution | Protected by |
|---|---|---|---|
| `framework/pyproject.toml` | git merged **silently** into two `[project.optional-dependencies]` tables (invalid TOML) | one table: `diagnostics`, `uncertainty` (A), `azureml` (B); B's `azureml` dependency group kept | `tomllib` load; `uv lock --check` |
| `framework/uv.lock` | both sides added packages | **regenerated** with `uv lock` (never merged by hand); the resolved set equals exactly the union of both locks (no version moved) | diff of the two package sets |
| `framework/mlkit/integrations/__init__.py` | add/add | one docstring naming both workstreams' modules | — |
| `CONTRIBUTING.md` | both gate lines | sync with `--group browser --group azureml --extra diagnostics --extra uncertainty`; pytest adds `framework/tests/exporters` | the gate |

Semantic conflicts (no textual conflict, found by running the products together):

| Interface | A delivered | B assumed | Resolution (A produces, B adapts) | Test |
|---|---|---|---|---|
| `read_export_source` module | `mlkit.contracts.export_source` | `mlkit.study.export_source` | B's `SOURCE_MODULE` | `test_end_to_end_real.py` |
| `ExportSource` content | references and digests | recipe and data-contract documents, development partitions by row key, protocol id, validity, metrics, case, conclusion | A adds them (additive, schema regenerated): documents from the captured bundle, or from the chosen configuration without any fit when the model is untuned; development keys only | `test_export_source.py`, e2e |
| Bundle document name | `bundle.json` | `predictor_bundle.json` | A adopts `predictor_bundle.json` | runtime and export suites |
| Evidence binding | file beside the bundle | `evidence_binding_path` in the bundle document | A versions `evidence/binding-<n>.json` and sets `evidence_binding_path`; the hashed content is unchanged; `read_evidence_binding` | `test_capture_final.py`, e2e |
| Parser keys | `encoding`, `delimiter`, `na_values`, `decimal` | + `header`, `quotechar` | A adds them from the case contract | e2e on Auto MPG (whitespace, no header, `?`) |
| Row keys with a header | `L<physical line>` (first data line `L2`) | `L1` for the first data line | B's `materialize` corrected | engine/case code; e2e (no header) |
| Parity tables | typed JSON documents | `.csv`/records/parquet | B's `read_table` reads the runtime's documents (typed, no inference) | B suites |
| Parity spec passed to the packager | mapping | `ParitySpec` dataclass | B accepts the mapping | `test_capture_final.py` (MLflow) |
| `load_predictor` | needs an explicit `trusted_roots` | none | B passes the bundle it verified (package wrapper, project) | B suites, e2e |
| Packager answers | contract models | B dataclasses (`passed`) | B adds `to_contract()`; the runtime accepts it | e2e |
| Packager verification | inside the bundle before the final document | after | the runtime verifies packages against the final bundle document; B's descriptor is written beside the package | `test_capture_final.py` |
| Environment lock | whole engine environment | merged with the template lock; conflict refuses | lock = dependency closure of `hypotrail-runtime` (what loading needs); real conflicts still refused (`test_a_conflicting_lock_is_refused`) | B suite |
| Workshop packager | `packager()` | `packager_for('atelier')` | A calls `packager_for('atelier')`; refusal before any read when MLflow is missing | `test_capture_final.py` |
| `predict --input` | strict physical types | pandas inference | B types user rows with the data contract (`typed_features`) | `test_exported_project.py` |
| Rebuild context | strict `ComputationContext` | free roles and backend | B maps fold roles to `fold_validation`, backend `{distribution, version}` | `test_exported_project.py` |
| `main`'s explicit binary `model_choice` | capture reads `choice_config` | — | no change needed (`choice_config` covers both flows) | library suite |

B's private test double of the runtime (`fixtures/fake_runtime`) was **removed**; every B
test now runs on the real runtime, with fixtures in the runtime's vocabulary. Assertions
tied to the double's internals were rewritten to the real objects (payload path from the
manifest, `runtime_closure`, `platform`), none weakened.

## Effective versions

Python 3.13.16 (Linux x86-64), uv 0.11.32. numpy 2.5.4, pandas 3.0.6, scikit-learn 1.9.1,
scipy 1.18.1, pydantic 2.14.1, pandera 0.34.1, hypotrail-runtime 1.0.0; extras: evidently
0.7.23, mapie 1.6.0, mlflow-skinny 3.17.2, hydra-core 1.3.7, omegaconf 2.3.1; dev:
hypothesis 6.170.8, ruff 0.4.5 (team template), playwright 1.55.0, marimo 0.25.1,
interpret-core 0.7.3.

## Commands run and results (gate run)

Run in this container on the integration branch (Python 3.13.16, uv 0.11.32), environment
synced with `uv sync --project framework --group dev --group browser --group azureml --extra
diagnostics --extra uncertainty`.

| Command | Result |
|---|---|
| `uv run --project framework python -m pytest framework/tests/study framework/tests/acceptance framework/tests/exporters -q` | **2084 passed, 99 skipped, 0 failed** (1 h 16). Includes the runtime and contract suites, Hypothesis properties and state machine, wheel build and fresh-environment install, fault injections (kill during capture, failure after reservation, altered payload), statistical oracles (bootstrap, DKW, conformal quantile, risk control), Hydra overrides, the B suites on the real runtime, and `test_end_to_end_real.py` (real Auto MPG study → workshop capture with MLflow → final test → export → moved folder). `test_contract_companion_e2.py::test_c7_export_handoff`, red at the base, passes. |
| `node --test` in `clients/vscode-companion` | **243 passed, 0 failed** |
| `uv run --project framework python -m pytest clients/vscode-companion/test -k "not pixel and not baseline"` | **390 passed, 12 skipped, 0 failed** (pixel baselines deselected) |
| `uv run --project framework python scripts/check_layout.py` | OK, no error |
| `uv lock --check --project framework` | lock current |
| Extras matrix (core only; `diagnostics`; `uncertainty`; all) | 4/4 on workstream A before the merge; **not rerun after the integration** |
| Pixel baselines (`test_*baseline*`, `*pixel*`) | fail identically at the base and on `origin/main` in this container (fonts); not rewritten |

### Panel regressions inherited from `main` (fixed here)

`origin/main` (`506180a`) is red on the panel suite by itself: the same 8 tests fail on a clean
worktree of `origin/main` in this container. `main` changed the engine payloads (the
`editable` notebook, the explicit binary `model_choice`, the handoff key order) and the EDA
cards (collapsed by default, localized titles) without recapturing the fixtures or updating
the panel tests other than `test_webview_eda.py`. Fixes:

| Failure | Cause | Fix |
|---|---|---|
| `test_fixture_drift` (captured and hand-written) | captures and hand-written fixtures predate `editable` | recaptured with `test/fixtures/capture.py`; `editable` added to the 13 hand-written fixtures that carry artifacts, launch, `artifacts_after` or renders (values from the live engine), formatting kept |
| `test_contract_keys`, Node `fixtures.test.js` | `HANDOFF_KEYS` moved `history` last on the engine side only | `contract-keys.json` and `handoff.binary.json` follow the engine order |
| `test_ed7_every_card_is_titled_by_its_question[binary, regression]` | **product bug**: every EDA card was titled with `requestQuestion`, a per-column chart question; the target, special-value and leakage cards read "…across the values of null…", and English titles no longer were the engine's question (ED-7) | `media/views/eda.js`: cards are titled by the engine's question; only in a French panel does a per-column chart (`distribution`, `rate_by`, `mean_by`) take the panel's French question (main's intent: no English engine text leaking into French) |
| `test_ed9…`, `test_the_rate_by_chart…`, `test_cards_put_provenance…` | the cards are now collapsed (`details.eda-analysis`), so their content has no visible text | the tests open the cards as the junior does (`panel_cases.expand_eda`), as `main` did in `test_webview_eda.py`; no assertion changed |
| `test_the_shortlist_lists_the_flags…` (French) | `main` switched French numbers to a decimal comma | expected text `0,71 … 0,8 à 1,2` |
| `test_ov7_*` (overview) | the fixture now carries the `editable` deliverable that `main`'s test injected by hand; an owned deliverable shows no status message | expected rows `report, notebook, editable, workbench`; `editable` shows no message, like the workbench; the workbench's Marimo button is scoped to its row |
| `test_recap_strip…`, Node OV-7 | the captured study now confirms `model_choice`; the summary lists the `editable` notebook | expected Decided line names the model choice; deliverable order `report, notebook, editable, workbench` |

## Acceptance criteria AC01–AC28

| ID | Status | Evidence |
|---|---|---|
| AC01 | pass | common base `581c7b3` verified; separate branches; nothing overwritten; no force-push |
| AC02 | pass | `test_contracts_v1.py` |
| AC03 | pass | `test_pandera_validation.py`; capture validates development rows |
| AC04 | pass | identity tests; Evidently versions in `diagnostics.population` params |
| AC05 | pass | legacy and evaluated-without-capture studies: read-only, recipe only, no invented model (`test_export_source.py`, e2e) |
| AC06 | pass | fold-by-fold parity (`test_predictor_parity.py`) |
| AC07 | pass | engine = runtime = reloaded = MLflow pyfunc on the parity rows, rtol 1e-10 / atol 1e-12 (library and e2e) |
| AC08 | pass | wheel from the bundle in a fresh uv environment (`test_runtime_wheel.py`) |
| AC09 | pass | kill during capture, failure after the final reservation, altered payload refused (library, B suites) |
| AC10 | pass | `test_scipy_bootstrap.py` |
| AC11 | pass | exact enumeration oracle, DKW bounds |
| AC12 | pass | eight Evidently scenarios; engine activity |
| AC13 | pass (adapter) / not applicable (engine) | eligibility and ledger tested; the engine creates no calibration partition (owner decision pending) |
| AC14 | pass | no admissible threshold → negative result |
| AC15 | pass | top-k/share and adaptive reuse refused |
| AC16 | pass | finite-sample quantile oracle |
| AC17 | pass | B: missing values, typo and added key refused, frozen config stable (exported project tests) |
| AC18 | pass | scientific override refused (`components.training.model.type=ridge`), operational overrides keep the identity |
| AC19 | pass | MLflow packager never fits; signature and pyfunc parity in a clean isolated process, now on the real runtime and on a real study (e2e) |
| AC20 | pass | `test_template_layout.py` |
| AC21 | pass | repeated export byte-identical (B suite and e2e on a real study); used target refused |
| AC22 | pass | moved folder: materialize, validate, predict, four-step rebuild (e2e) |
| AC23 | pass | rebuilt candidate: new id, verdict not inherited; capture after opening refused |
| AC24 | pass | no final-test key, study path or secret in the export (e2e, B suite) |
| AC25 | pass | lazy imports; extras matrix (A: 4 environments); B's `azureml` extra |
| AC26 | pass | B's suites and the e2e scenario run against A's real producers, no mock |
| AC27 | partial | CLI and HTML complete without the extension; the Marimo notebook does not show capture, diagnostics or export |
| AC28 | pass as a distinction; cloud **not run** | readiness separates YAML validity, job, registration and qualification; no Azure call |

## Limits and qualification

- **Cloud: validated locally; cloud not qualified.** No Azure resource was read or written,
  no job submitted, no endpoint exists; `preflight`/`submit` only print their commands.
- Export support matrix: regression `linear` (Auto MPG). Binary families capture and
  package (library tests) but the Azure template refuses them (`capability_not_supported`).
- Calibration partitions are not created by the engine (MAPIE adapters library-level).
- Source compatibility (review 2026-10-24, E1, fixed): the integration changed
  `mlkit/study/activities.py` and `fit.py`, so studies made at `506180a` had no current
  result at HEAD, and one whose final test was opened could not recover. Exact
  `code_compat` edges now cover the activities whose path is unchanged without a capture,
  each added only after a byte comparison of the two engines on four temporary studies
  ([LIBRARIES-V1.md](LIBRARIES-V1.md#source-compatibility-of-existing-studies)). Any later
  edit of either file needs the comparison again and new edges.
- Pixel baselines of the panel fail identically at the base in this container (fonts).
- `test_contract_companion_e2.py::test_c7_export_handoff` failed at the base `581c7b3`; it
  passes on the integration branch.
- The extras matrix was not rerun after the integration (the full environment was).
- No real Copilot, VS Code or human session; agent acceptance runs were not executed.

## Pull request summary (integration → `main`)

**Title:** Integrate library contracts v1 (A), Azure ML export v1 (B) and main's fixes

- **A (libraries v1):** `hypotrail-runtime` distribution (strict Pydantic contracts,
  canonical JSON, schemas); `predictor.capture` fits the complete predictor before the final
  test, writes a verified bundle and a wheel; the final test scores the reloaded capture and
  binds its evidence; Pandera data contracts; SciPy bootstrap, Evidently diagnostics, MAPIE
  risk control and conformal intervals as optional extras; Hypothesis properties.
- **B (Azure ML export v1):** `hypotrail export azureml` writes a self-contained project
  (Hydra configuration, four replayable steps, MLflow pyfunc package, readiness contract)
  from the read-only `read_export_source`. Cloud is **not qualified**: no Azure call is made.
- **Integration:** B consumes A's real runtime (test double removed); interface points
  closed in A's contract (see the semantic-conflict table); the workshop capture calls B's
  MLflow packager; a real end-to-end test runs from a study to a moved exported project.
- **main's fixes:** merged without textual conflict; the panel regressions `main` carried
  (stale fixtures, EDA card titles, collapsed cards in tests, French decimals) are fixed.
- **Validation:** engine gate 2084 passed / 0 failed; Node 243/243; panel 390 passed / 0 failed;
  layout OK. Not run: Azure, real Copilot/VS Code session, extras matrix after the merge,
  pixel baselines (font-dependent here).
- **Merge:** merge commit (no rebase, no force-push); the branch contains `main` at `506180a`.
