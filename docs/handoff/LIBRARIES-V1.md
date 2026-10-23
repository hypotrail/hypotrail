# Library integration v1 — workstream A handoff

Status: **implemented on branch `claude/zealous-franklin-gywbya`, not merged.** Scope: the
owner's specification pack in [`docs/specs/integration-libraries/`](../specs/integration-libraries/README.md)
(spec v1 and shared contract v1, 23 October 2026; French originals kept verbatim with their
SHA-256). Workstream B (Azure ML export, Hydra, MLflow packager, template) is out of scope and
was not touched.

## Base and branch

| Item | Value |
|---|---|
| Audited base (spec) | `581c7b3723629260a18e1281ef9e18583ae060a7` |
| Base used | `581c7b3723629260a18e1281ef9e18583ae060a7` (equal to `origin/main` when work started) |
| Gap to the target branch at start | none (`origin/main` was `581c7b3`) |
| Branch | `claude/zealous-franklin-gywbya` (the session's designated branch; the brief named `feature/libraries-v1`, which this session may not push). Rename on merge if wanted. |
| HEAD | see `git log` of the branch; this document is updated in the last commit |

The other agent pushes fixes directly to `main` in parallel; the integrator merges this branch
separately (spec §16). No history was rewritten and nothing was force-pushed.

## What exists now

| Spec | Capability | Where |
|---|---|---|
| §4, L-01, L-06 | Ten v1 contracts as strict Pydantic models (`schema_version` literal, unknown major refused first, unknown fields refused outside namespaced `extensions`, no NaN/Infinity, `"3"`/`true` never an integer), semantic checks separate from structure, generated JSON schemas, canonical serialisation `hypotrail.canonical/1` with frozen reference vectors | `framework/runtime/src/hypotrail_runtime/{contracts,canonical,errors}.py`, `schemas/` |
| L-02, L-03 | Computation identity: inputs, partitions, decisions, method, code, runtime and the versions of the engines the method calls; the full lock is audit-only | `framework/mlkit/contracts/context.py` |
| L-07 | Pandera schema derived from the DataContract (no coercion, no row change, partition authorisation, bounded issues); same verdicts as the runtime's own input check | `framework/mlkit/integrations/pandera_validation.py`, `hypotrail_runtime/inference.py` |
| L-08, L-09 | Complete predictor: the engine's preparation (category text, special-value indicators, missing indicators, rare categories, caps, signed log) as a fitted scikit-learn step before imputation, scaling, one-hot encoding and the estimator; fold-by-fold parity with `fit._fit_predict`; families `linear`, `ridge`, `logistic` qualified, `ebm`/`hgb` refused (never replaced) | `hypotrail_runtime/{preprocess,families,predictor}.py`, `mlkit/contracts/recipe.py` |
| L-05, L-10, §6 | `run predictor.capture [--profile base|workshop] [--packager F]`: fitted on the development rows, validated, compared with the engine's fit, captured in a staging directory, reloaded, parity-checked, optionally packaged, moved atomically to `.hypotrail/predictors/<predictor_id>/`; the final test then requires a current capture of the configuration it opens and scores the reloaded predictor (no refit); evidence binding written after the result | `mlkit/contracts/capture.py`, `mlkit/study/activities.py` (dispatch), `fit.final_evaluation(predictor=...)`, `executions.py` (binding) |
| §6 | Packaging hook injected into `capture_predictor` (`ArtifactPackager` protocol); workshop profile without its packager refused before any read; `synthetic_test` packager for tests only (`HYPOTRAIL_TEST_HOOKS=1`) | `hypotrail_runtime/packaging.py`, `mlkit/contracts/testing_packager.py` |
| §6 | `read_export_source(study, expected_revision)` → `hypotrail.export_source/1` | `mlkit/contracts/export_source.py` |
| L-09 | `hypotrail-runtime` distribution, installable alone; the bundle ships its own reproducible wheel | `framework/runtime/`, `hypotrail_runtime/wheel.py` |
| L-11, L-12 | SciPy paired percentile bootstrap adapter with explicit generator, seed and versions, the engine's undefined-replicate policy, capability matrix | `mlkit/integrations/scipy_bootstrap.py` |
| L-13, L-14 | Evidently profile → `hypotrail.diagnostic_result/1`; `run diagnostics.population` (opt-in) | `mlkit/integrations/evidently_diagnostics.py`, `mlkit/contracts/population.py` |
| L-15–L-17 | MAPIE: calibration eligibility and ledger, precision risk control on a fixed threshold grid, split-conformal intervals; calibrated export refused | `mlkit/integrations/mapie_uncertainty.py` |

## Interfaces (v1) for workstream B and the integrator

```python
# hypotrail_runtime (framework/runtime; no engine import)
validate_recipe(document) -> ModelRecipe
validate_data_contract(document) -> DataContract
verify_bundle(bundle_dir) -> BundleDescriptor              # no unpickling
load_predictor(bundle_dir, *, trusted_roots) -> Predictor  # trusted roots are explicit
Predictor.predict(raw_features: DataFrame) -> PredictionBatch
fit_predictor(recipe, data_contract, training_frame, training_scope) -> FittedPredictor
capture_predictor(fitted, context, parity_features, destination, packager=None, *,
                  parity_origin, tolerance, code_fingerprint, extensions) -> BundleDescriptor
check_parity(predictor) -> ParityResult
write_evidence_binding(bundle_dir, binding) -> Path
# packaging protocol (B implements): ArtifactPackager.format, .package(native, out, parity_spec)
#   -> PackageDescriptor, .verify(native, package_dir, parity_spec) -> ParityResult
# engine
mlkit.contracts.export_source.read_export_source(study_path, expected_revision) -> ExportSource
mlkit.contracts.capture.PACKAGERS  # {'mlflow_pyfunc': (mlflow_packaging, 'packager_for', 'atelier', 'mlflow')}
```

> **Updated at integration I1** ([INTEGRATION-LIBRARIES-AZUREML-V1](INTEGRATION-LIBRARIES-AZUREML-V1.md)):
> the bundle document is `predictor_bundle.json`; evidence bindings are versioned under
> `evidence/binding-<n>.json` and named by its `evidence_binding_path`; the parser carries
> `header` and `quotechar`; the environment lock is the runtime's dependency closure; the
> workshop packager is workstream B's `packager_for('atelier')`. The notes below are the
> pre-integration text where they differ.

**Bundle layout** (`hypotrail.predictor_bundle/1`, relative paths only, every file hashed in
`predictor_bundle.json` except itself and `evidence/`): `predictor.json`
(`hypotrail.predictor_artifact/1`, `predictor_id` = digest of the manifest without itself),
`recipe.json`, `data_contract.json`, `computation_context.json`, `payload/model.pkl`
(`sklearn_pickle/1`), `runtime/hypotrail_runtime-1.0.0-py3-none-any.whl`,
`environment/requirements.lock`, `parity/features.json` (`hypotrail.parity_frame/1`, feature
columns only, at most 50 development rows), `parity/expected_outputs.json`,
`packages/<format>/` and `packages/<format>.descriptor.json` (optional) and, after the final
evaluation, `evidence/binding-<n>.json`.

**Migration notes for B.**
1. B's packager module is `mlkit.integrations.mlflow_packaging` exposing `packager()` that
   returns an object with `format = 'mlflow_pyfunc'`, `package(...)` and `verify(...)`; the
   descriptor's `predictor_id` must equal the native bundle's. Until it exists,
   `--profile workshop` is refused with `optional_dependency_missing` before any read.
2. `PackageDescriptor` and `ParityResult` are validated strictly (schemas in
   `hypotrail_runtime/schemas/`); B creates no second schema.
3. `read_export_source` exposes `predictor.bundle_dir` (absolute), the digests, the evidence
   status (`evaluated` only for the predictor the final test scored) and `limitations`; it
   never carries rows or labels. B composes `DeploymentSnapshot` from it.
4. `load_predictor` needs an explicit trusted root (a digest does not make a pickle safe):
   the exported project passes its own bundle directory.
5. `contract_invalid` and the other v1 codes reach the CLI as frozen engine codes with
   `details.contract_code` (CLI-CONTRACT, "Library integration v1 additions").

## Commands and test evidence

Environment: Python 3.13, uv 0.11, the lock in `framework/uv.lock` (`uv sync --project
framework --group dev --group browser --extra diagnostics --extra uncertainty`).

| Suite | Result |
|---|---|
| `framework/tests/study/libraries/` (contracts, parity, capture/final, export source, Pandera, wheel, SciPy, Evidently, population activity, MAPIE, optional dependencies, Hypothesis) | 116 passed, 4 skipped (opt-in matrix) |
| Extras installation matrix (`HYPOTRAIL_EXTRAS_MATRIX=1`, four fresh environments: base, diagnostics, uncertainty, both) | 4 passed (run once, 36 s) |
| Runtime wheel in a fresh uv environment, bundle moved away from its deleted study, `python -I`, no `mlkit`/`marimo`/`mlflow`/`azure`/`hydra`/`evidently`/`mapie` importable | passed |
| Gate (CONTRIBUTING) | see "Gate run" |

### Gate run

Run on this branch in this cloud container (Python 3.13.x, Linux, 4 cores), framework
environment synced with `--group dev --group browser --extra diagnostics --extra uncertainty`:

| Line of the gate | Result |
|---|---|
| `python3 scripts/check_layout.py` | no error |
| engine pytest line (CONTRIBUTING) | 1968 passed, 98 skipped, 2 failed (1 h 24): `test_contract_companion_e2.py::test_c7_export_handoff` **fails identically at the base `581c7b3`** (export key order, unrelated); the Hypothesis machine failed in the version collected at the start of that run and was fixed during it (oracle too strict on a replayed `already_current` run) |
| `framework/tests/study/libraries` + `test_contract_freeze.py`, re-run after the fixes | 120 passed, 4 skipped (the opt-in extras matrix) |
| Hypothesis machine at 40 examples × 30 steps | passed (40 passing cases) |
| `node --test clients/vscode-companion/test/*.test.js` | 239 passed |
| panel pytest line (after recapturing the fixtures) | 389 passed, 12 skipped; **12 pixel baselines fail, and fail identically at the base** in this container (font rendering; the fontconfig profile of the J0 run is not available here). No baseline was rewritten. |

Reference run at the base `581c7b3` in a separate worktree (same container, without the
browser group): 1875 passed, 95 skipped, 1 failed (`test_c7_export_handoff`).

The panel's captured fixtures were regenerated with `capture.py` (documented procedure after
an engine change): result ids follow the code fingerprint. Recapturing at the base in this
container changes the same floating-point fields (`std_error`, interval bounds) as on this
branch, and the branch's capture differs from the base's only by random exposure ids and
hashes: the numeric differences come from the environment, not from this work.

### Observations made by the state machine (engine behaviour, unchanged)

- A refused command still appends to the session log (`events.jsonl`) and rewrites the
  writer lock's bookkeeping; study state, registry and exposure files are untouched.
- After a process dies mid-run, the next command records the interruption (with its
  planned reads, `result_id: null`) and then refuses: that first refusal writes state.
- A `run` answered `already_current` reserves nothing and records no receipt: replaying it
  is not marked `replayed`, and its request id is not consumed (it can be reused for another
  command without `idempotency_conflict`). Harmless (nothing was recorded) but worth knowing
  for clients that treat request ids as consumed.

## Dependency changes

Base (installed for everyone): `hypotrail-runtime` (path dependency), `pydantic>=2.7,<3`,
`pandera>=0.20` — new packages in the base export: pydantic 2.14.1, pydantic-core 2.50.1,
annotated-types, typing-inspection, pandera 0.34.1, typeguard, typing-inspect,
mypy-extensions. Dev group: `hypothesis>=6.100` (+ sortedcontainers). Extras:
`diagnostics = ["evidently==0.7.23"]` (109 packages in the export with it, 59 without),
`uncertainty = ["mapie==1.6.0"]` (60). Existing pins (pandas 3.0.6, numpy 2.5.4,
scikit-learn 1.9.1, scipy 1.18.1, marimo 0.25.1, interpret-core 0.7.3) are unchanged; the
lock only adds packages. Python range unchanged (`>=3.13,<3.14`).

Measured import cost on this machine (cold import in a fresh process, peak RSS after it):
pandera 0.6 s / 106 MB, `hypotrail_runtime` 1.4 s / 170 MB (scikit-learn, pandas), MAPIE
1.3 s / 176 MB, Evidently 3.7 s / 262 MB (33 MB on disk; it prints a `SyntaxWarning` from its
own sources on first compilation). Evidently is imported only by `diagnostics.population`.

## Shared files touched (minimal, for the integrator)

`framework/pyproject.toml` (dependencies, extras, `[tool.uv.sources]`, dev group),
`framework/uv.lock` (regenerated by `uv lock`, additions only), `mlkit/study/activities.py`
(constants, `EXPORT_ACTIVITIES`, dispatch, option checks, final plan branch),
`mlkit/study/fit.py` (`final_evaluation(predictor=None)`), `mlkit/study/preconditions.py`
(capture requirements), `mlkit/study/executions.py` (evidence binding after promotion),
`mlkit/study/cmd_run.py` (`--profile`, `--packager`), `docs/specs/CLI-CONTRACT.md` and
`framework/tests/study/test_contract_freeze.py` (same commit), `CONTRIBUTING.md`,
`docs/architecture/REPOSITORY.md`, `docs/handoff/IMPLEMENTATION.md`,
`mlkit/study/code_compat.py` (see "Source compatibility").

## Source compatibility of existing studies

Editing `activities.py` (in every activity's fingerprint) and `fit.py` makes the results of
studies computed at the base report `code_changed` (kept, not current), as every earlier
engine change did; consistent with the repository's practice (J0–J3: "no new code
equivalence exception"), **no broad attestation was added**. Only the existing, reviewed
`diag.final_test` edge of `mlkit/study/code_compat.py` was retargeted to the new bytes of
`activities.py`, plus the same edge from the base digest
(`3065f4d6…` → `4179e60b…`): the final-test diagnostic dispatch is unchanged. The
reviewer may add edges for other activities (their engine paths are unchanged when no
capture exists) or remove these; either way nothing becomes wrong, only current or not.
Any further edit of `activities.py` (including the merge with `main`) must recompute these
digests.

## Limits and what is not done

- **Calibration partitions are not created by the engine.** The MAPIE adapters, the
  eligibility check and the ledger are complete and tested, but `init` reserves no calibration
  rows, so every engine study is `not_applicable` for risk control and intervals (as
  `read_export_source` states). Adding a sealed calibration partition changes the frozen
  `init` and partition contracts and the panel fixtures: it needs an owner decision (share,
  ADR 0006 amendment). The adapters are therefore library-level only.
- **The engine's review-v1 bootstrap still uses `random.Random`.** The SciPy backend exists
  and is tested; switching a study's backend changes its numbers (different generator) and is
  a versioned decision, not done silently.
- **Exported families**: linear and ridge regression (Auto MPG), logistic regression
  (synthetic tests). EBM and histogram boosting are refused for capture; a study that chose
  one cannot capture (its final test keeps the historical refit if never captured).
- **Trusted local pickle** only; no third-party bundle should be loaded.
- **Marimo**: the generated notebook does not show the capture or the population
  diagnostics (the HTML report's annex and the CLI do).
- **No real MLflow, Azure or cloud run** (workstream B / I2). No real VS Code, Copilot or
  human junior session.
- Evidently's `SyntaxWarning` on first import is upstream noise, not silenced globally.

## Integration tasks left (I1)

1. Merge A then B without squash; regenerate `uv.lock` with both groups of extras.
2. Run B's packager suite against a bundle produced by `predictor.capture` (AC26) and the
   real end-to-end scenario of spec §16 (capture → final test → export → moved folder →
   native and MLflow loading → replay → rebuilt candidate).
3. Decide on calibration partitions (above) and on the bootstrap backend of new studies.
4. Review the code-compatibility attestation.

## Acceptance matrix AC01–AC28

| ID | Status | Justification |
|---|---|---|
| AC01 | pass, with a deviation | Base `581c7b3` recorded and equal to `origin/main` at start; separate checkout on the session branch; no user work overwritten. The branch name is the session's, not `feature/libraries-v1`. |
| AC02 | pass | `test_contracts_v1.py`: bool/int/float/string ambiguity, unknown field, non-namespaced extension, NaN in Python and in JSON, unknown major version, stable codes with path and remediation. |
| AC03 | pass | `test_pandera_validation.py`: schema from the DataContract; no mutation (frame and order compared); same verdicts as the runtime. |
| AC04 | pass | `test_contracts_v1.py` identity tests (SciPy/NumPy version changes the bootstrap identity, pandas/Evidently do not); `diagnostics.population` puts the Evidently versions in its params. |
| AC05 | pass | `test_export_source.py`: a v0.1-shaped study and a study evaluated without capture read without writes, no model invented, capture after opening refused. |
| AC06 | pass | `test_predictor_parity.py`: state learnt per fold on the fold's training rows, every historical out-of-pipeline rule included. |
| AC07 | pass | Engine fit = runtime fit = captured = reloaded (rtol 1e-10, atol 1e-12) in `test_predictor_parity.py` and `test_capture_final.py` (final-test predictions too). |
| AC08 | pass | `test_runtime_wheel.py`: wheel from the bundle, fresh uv environment, `-I`, moved bundle, deleted study. |
| AC09 | pass | Kill during the capture (interruption recorded with its reads, nothing promoted, final test sealed); failure after the final reservation (test consumed, no evaluated binding, never reopened). |
| AC10 | pass | `test_scipy_bootstrap.py`: paired, percentile, level, replicates, generator, seed, versions, gain direction, undefined policy. |
| AC11 | pass | Exact enumeration oracle with DKW bounds for both backends; no seed-equality test. |
| AC12 | pass | `test_evidently_diagnostics.py`: the eight scenarios, fixed methods, NA separate, failed → alert null; `test_population_activity.py` in a real study. |
| AC13 | pass (adapter); engine not applicable | Eligibility refuses overlap, late reservation and explored rows; the engine creates no calibration partition yet (see Limits). |
| AC14 | pass | No admissible threshold → `insufficient_data`, `no_admissible_threshold`, empty list, no threshold. |
| AC15 | pass | `capacity`, `share`, `top_k` refused; the ledger refuses a second procedure on the same calibration. |
| AC16 | pass | Half-width equals the finite-sample residual quantile; insufficient rows → `insufficient_data`; marginal-only assumptions shown; subgroup coverage descriptive. |
| AC17 | not applicable | Hydra is workstream B. |
| AC18 | not applicable | Workstream B. |
| AC19 | not applicable (A side tested) | MLflow packager is B's; the hook, its refusal and a failing packager are tested with the test-only packager. |
| AC20 | not applicable | Template is B's. |
| AC21 | partial (A side) | A capture identical to an existing one reuses the verified bundle and never overwrites (`destination_not_empty`, tamper detection); export hashes are B's. |
| AC22 | partial (A side) | The bundle predicts after being moved away from its deleted study; the four template steps are B's. |
| AC23 | pass | Capture after the opening refused; `evidence_status` is `evaluated` only for the scored predictor; training-scope roles distinct. |
| AC24 | pass (bundle) | No target, final-test row, study database or secret in the bundle (test); B's fixtures and template not covered. |
| AC25 | pass | Lazy imports (gate), named refusal without an extra (gate), four-environment matrix (opt-in, run once: 4 passed). |
| AC26 | not run | Needs B's packager and the merge. |
| AC27 | partial | CLI and HTML report (annex) complete without the extension; refusals carry `remediation`; the Marimo notebook does not show the new results. |
| AC28 | not applicable | Cloud qualification is B / I2. |
