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
evaluation, `evidence/binding-<n>.json`. Every one of these files except the bundle document,
the evidence bindings and the packages is bound to the predictor id by the manifest (review
2026-10-24, below).

> **Updated after the review of 24 October 2026** ([REVIEW-2026-10-24](../acceptance/REVIEW-2026-10-24.md),
> area A; see "Review 2026-10-24 fixes" below): the predictor id now binds every immutable
> byte of the bundle (the parity block and the computation context enter the manifest's
> extensions), and a bundle holding packages lives at `predictors/<predictor_id>+<format>`.

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

## Review 2026-10-24 fixes (area A)

Regression tests: `framework/tests/study/libraries/test_review_2026_10_24_a.py`.

- **A1, what the predictor id binds.** `verify_bundle` compares every digest the manifest
  records with the bytes: `payload_files[].sha256`, `runtime.wheel_sha256`,
  `environment.lock_sha256`. The parity block of `predictor_bundle.json` (paths, digests,
  origin, row count, tolerance) must equal the manifest extension `hypotrail.parity`, and
  the computation context is bound by `hypotrail.computation_context`
  (`{relative_path, sha256}`, or null when the capture had none). A listed file that neither
  the manifest nor a declared package binds is refused, and so is a manifest without these
  two extensions (a bundle captured before the fix: capture again). `check_parity` re-reads
  the parity digests before comparing. Consequences: swapping the payload (even with the
  parity outputs regenerated and the bundle document edited), changing the wheel or the
  lock, relaxing the tolerance, or removing, adding or editing the context is refused with
  `artifact_integrity_failed`; a capture's id now changes with its tolerance and its
  computation context, which records the study revision at the capture (two captures of one
  configuration at two revisions are two predictors). The evidence binding stays outside the
  id, mutable and versioned; its temporary document is written under `evidence/`, so a crash
  cannot leave an unlisted file beside the bundle document. Predictor ids of earlier bundles
  are not valid any more (pre-release v1); recipe and data-contract ids are unchanged (the
  frozen `RECIPE_ID` and `CONTRACT_ID` vectors did not move).
- **Optional packages** are made from the verified native bundle after its id exists, so
  they stay outside the id; `verify_bundle` checks each one against its descriptor
  (`packages/<format>`, one per format, descriptor listed with its recorded digest, same
  format, predictor id and artefact id, parity `ok`, every descriptor file present with its
  digest). `packager.format` is checked (`[A-Za-z0-9][A-Za-z0-9_-]{0,63}`) before it becomes
  a path.
- **A2.** `trusted_roots` is None or a collection of paths; a string, bytes, a single path or
  a non-path element is refused with `contract_invalid` before anything is read.
- **A3.** The bundle folder is `<predictor_id>` without packages and
  `<predictor_id>+<format>[+...]` with packages; a capture reuses only a bundle of the same id
  and the same formats, reports the packages of the bundle it names (so does
  `read_export_source`), verifies every existing bundle of the same predictor first (an
  altered one refuses the capture), and removes its staging folder on every outcome.
- **A4.** The MAPIE calibration ledger keys a use on the rows: the membership digest of
  `calibration_ref` (same rows under another partition id are refused for another
  procedure, reproduced for the same one) and, with `claim(..., keys=...)`, per-row digests
  (an overlapping set or a superset is refused). Round 2 makes `keys` mandatory (see
  below).
- **Minor items.** A recipe feature absent at inference is `missing_columns` even when the
  contract does not require it; string columns (`object`, `string[python]`,
  `string[pyarrow]`) reach the preparation with `NaN` for a missing value, and the
  preparation reads `pd.NA` as the engine reads `NaN`; a lone surrogate is
  `contract_invalid`; at the conformal boundary (rank ⌈(n+1)·level⌉ = n, refused by
  MAPIE 1.x) the adapter keeps its own finite-sample rule and computes the quantile itself
  (`hypotrail.quantile: adapter_rank_rule`, with a warning); Evidently compares categories
  after writing an integral float as an integer, validates the profile strictly, refuses an
  inverted alert (a p-value alerts with `lt`/`le`, a distance with `gt`/`ge`), reports an
  empty profile as `failed` with "the profile declares no check" and a profile column
  absent from a population as `contract_invalid`; the Pandera schema honours the declared
  conversions as the runtime does; `C=1` and `C=1.0` (any real-valued family parameter) give
  one recipe id; validated contracts are immutable all the way down (their dicts and lists
  refuse mutation); a bootstrap whose point estimate is undefined on the full sample is
  `insufficient_data`; a missing MAPIE submodule is `optional_dependency_missing`; the lock
  header names the platform as the manifest does (`sys.platform`-machine), not the kernel
  build. The test-only synthetic packager hands its raw pipeline NaN for a missing text
  value, as the runtime's input check does.
- **Evidence after the fixes:** `framework/tests/study/libraries` 167 passed, 4 skipped
  (opt-in extras matrix); the Azure ML exporter files that build bundles
  (`test_mlflow_packaging`, `test_export_command`, `test_contract_units`, `test_review_fixes`)
  139 passed, 1 skipped. Editing the runtime modules changes the code fingerprint of
  `predictor.capture` and `diagnostics.population`: earlier results of these two activities
  read as not current.

**Round 2.** Regression tests: `framework/tests/study/libraries/test_review_round2_a.py`
(ported from the reviewer's probes). **A1-R2a:** a package is outside the predictor id, so
its embedded native bundle is now checked against the predictor. `verify_bundle` verifies
every folder of a package holding a `predictor_bundle.json` (and the folder the descriptor
names with `hypotrail.native_bundle`, which must exist) as a bundle of its own, and requires
the same predictor id, manifest, recipe, data contract and payload, no package of its own,
and exactly the files the outer predictor id binds with the same digests; otherwise
`artifact_integrity_failed` (so the final-test opening and the Azure ML export refuse it).
`ArtifactPackager.verify` (and `package`, before publishing) also requires the packager's
own wrapper bytes, an `MLmodel` that loads that wrapper on `artifacts/native_bundle`, and the
same byte identity, raising `artifact_integrity_failed`; a parity mismatch is still a
`failed` result. A package re-captured with another model that agrees on the parity rows,
and re-described consistently, used to verify under the evaluated id and be exported as
`packaged`. **A4-R2:** `CalibrationLedger.claim(ref, procedure, *, keys)` requires the row
keys (`None`, a string or an empty set is `contract_invalid`; omitting the argument is a
`TypeError`); a recorded use without row digests cannot be shown disjoint and blocks every
other membership (`recorded_rows_unknown`); a claim reads, checks and appends under an
exclusive `flock` on `<ledger>.lock`, so two concurrent claims never both bind. Changed
expectations: the round-1 ledger tests (`test_mapie_uncertainty.py`,
`test_review_2026_10_24_a.py`) now pass keys; the refusal they assert is unchanged. The
round-1 xfail `test_ledger_overlapping_superset_also_escapes` was not in this repository; a
test of that name now passes in the round-2 file. **N1:** the Evidently adapter reads `None`,
`NaN`, `pd.NA` and `NaT` as missing in a categorical column of any dtype (never the category
`'<NA>'`). **N2:** an integer given for a real-valued family parameter that no float
represents exactly (`10**400`, `2**53 + 1`) is `contract_invalid`, from a mapping and from
JSON bytes, never a raw `OverflowError` or a silent rounding. **N4 (observation, behaviour
unchanged):** below 0.5, MAPIE can take one rank above the adapter's rule (its 1 − α is
`0.30000000000000004` at 0.3), a wider interval; documented in the `mapie_uncertainty`
docstring and bounded by a test. No contract docstring changed: the JSON schemas are
current (`python -m hypotrail_runtime.schemas --check`). Evidence:
`framework/tests/study/libraries` 202 passed, 5 skipped (the opt-in extras matrix and one integer beyond the JSON
reader's digit limit); the four Azure ML exporter files above 139 passed, 1 skipped.

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

Editing `activities.py` (in every activity's fingerprint) and `fit.py` changed their digests
(`activities.py` `3065f4d6…` → `d6806ce3…`, `fit.py` `28c00840…` → `d39f3f5b…` between the
base `506180a` and `621d607`). Without an attestation every result of a study computed at the
base reports `code_changed` and is not current at HEAD. That is a real loss, not a cosmetic
one: the results can be recomputed, except `final_test.evaluation`, which runs once, so a
study whose final test was opened could never be current again (review 2026-10-24, E1).

Decision of the integrator (2026-10-24): attest the paths that are unchanged when no capture
is used, and only with evidence. `mlkit/study/code_compat.py` now holds, besides the reviewed
`diag.final_test` edges, two exact edges from the base digests to the `621d607` digests:

- `mlkit.study.activities` `3065f4d6…` → `d6806ce3…` for the twenty other activities of the
  base engine (`split`, the nine `eda.*`, `fit.baseline`, `fit.logistic`, `fit.linear`,
  `fit.variant`, `policy.evaluation`, `policy.inspect`, `evaluate.regression`, `diag.binary`,
  `diag.regression`, `final_test.evaluation`). The change adds the `predictor.capture` and
  `diagnostics.population` constants, option checks and dispatch, and a final-test plan branch
  and load that are taken only when a `predictor.capture` result is current, which no study of
  the base has.
- `mlkit.study.fit` `28c00840…` → `d39f3f5b…` for the eight activities whose fingerprint holds
  it (`fit.baseline`, `fit.logistic`, `fit.linear`, `fit.variant`, `eda.single_feature_signal`,
  `diag.binary`, `diag.regression`, `final_test.evaluation`). The change adds the optional
  `predictor` argument of `final_evaluation`, `None` without a capture.

`predictor.capture` and `diagnostics.population` are not attested: they did not exist at the
base. No other fingerprinted module changed (`scikit-learn` 1.9.1 and `interpret-core` 0.7.3
are pinned at both commits).

Documented loss, not attested (review fix A, 2026-10-24): the review fixes changed the
runtime and the capture behaviour (`hypotrail_runtime` `predictor`, `contracts`, `canonical`,
`families`, `inference`, `preprocess`; `mlkit/contracts/capture.py`; the MAPIE, Evidently,
Pandera and SciPy integrations), and a bundle without the new manifest extensions is now
refused. A `predictor.capture` or `diagnostics.population` result computed before those fixes
(at `621d607` or on a branch of it) therefore reports `code_changed` and is not current, by
design; there is no byte equality to attest. Re-running the activity recaptures the predictor.
The consequence that cannot be repaired: a `final_test.evaluation` that scored a reloaded
capture names that capture among its inputs, so it is not current either (upstream not
current), with the `diag.final_test` computed from it, and the final test is not run twice.
Such a study keeps its recorded final figures, shown as not current; its evidence can only be
current again in a new study. Studies of the base (`506180a`) have no capture and are not
affected.

A study whose final test is still sealed is not lost (review round 2, E2-1, 2026-10-24). Until
then, the engine opened the final test on such a capture: the opening checked the capture
against the stale map only, while `status` and `evidence` also apply `code_changed` (with the
code attestations) and upstream currency, so the opening either failed (`integrity_error` on an
old bundle) or produced a final result that was not current from the start, and the final test
was used up either way. Now the engine refuses to open the final test on a capture that is not
current by the rule `status` and `evidence` use, for any fingerprinted module change, and
equally on a capture the final evaluation could not load (a stray file in the bundle such as a
`.DS_Store`, an environment whose library versions differ from the capture's; area A, F1). The
check runs before the `final_test` confirmation commits and again when the evaluation is
reserved, before the opening is recorded: the confirmation is refused with
`precondition_missing` (slot `predictor.capture`, requirement `result_current` with
`code_changed` / `upstream_not_current`, or `capture_loadable`), nothing is marked opened, no
final-test row is read or recorded as exposed, and `details.junior_message` tells the junior
what to do. What the junior does: run `predictor.capture` again (after bringing any result it
was made from up to date) when the capture is not current; remove the stray file or restore the
captured environment when it cannot be loaded; then confirm the opening again. If the bundle
changes between the reservation and the evaluation, the evaluation refuses it before reading
any final-test row and the opening is withdrawn (`run.fail` with `final_test_unread`), so the
final test is still not consumed. After an opening, `run final_test.evaluation` and `run
diag.final_test` no longer answer `already_current` for a result that is not current: they say
it cannot be recomputed (E2-2). An identical request on a result that is current under a code
attestation is answered by that result instead of recomputing and replacing it (E2-3); a module
change no exact attestation covers for that activity is still a new request.

Evidence (`framework/tests/study/code_compat_evidence.py`, reproducible; the opt-in test
`test_code_compat_library_v1.py::test_byte_comparison_with_the_base_engine` runs it when
`HYPOTRAIL_COMPAT_OLD_PYTHON` and `HYPOTRAIL_COMPAT_OLD_ROOT` name a `506180a` checkout with its
own `uv sync --frozen` environment). The same 95 commands ran with the `506180a` engine and with
the current one on four temporary studies made from the same case files: a synthetic binary
case with the default holdout and three variants (tuned, gradient boosting, stronger penalty),
the same case under 5-fold stratified cross-validation (stronger penalty, EBM), Auto MPG with
the default holdout (tuned, gradient boosting), and a synthetic regression case under 5-fold
quantile cross-validation (stronger penalty, EBM); each runs every activity of its task, then
confirms the model and (binary) the rule, opens the final test (`final_test.evaluation`) and
runs `diag.final_test`. All 95 commands had the same outcome. Of the 73 registry results, all
have byte-identical blobs (prediction and row-key digests), params, partition and row count;
53 have byte-identical values and output digest; the 20 others (`policy.*`, `evaluate.regression`
and the diagnostics) differ only by the ids of the upstream results they name, because a
result id hashes the code fingerprint. Then, in copies of the four `506180a` studies, the
current engine found every promoted result current (67 of 67) and recomputed the 42 leaf
results (every EDA, `policy.inspect`, `policy.evaluation`, `evaluate.regression`, the
diagnostics and `diag.final_test`), whose upstream ids stay the old ones: all 42 are
byte-identical to the `506180a` results (values, output digest, blobs, params, inputs).
The comparison was run again on the working tree after the review fixes of the runtime and
the capture had landed (none of them touches a module these activities fingerprint): the
same counts, all matching.
`test_code_compat_library_v1.py` also checks, without the old engine, that the attested
digests are the bytes of both commits and of the current files, that each activity list is
explicit and complete, and that the edges stay exact, directed and scoped.

With the reviewer's drivers, the `506180a` studies (an open binary study, the same with its
final test opened and `diag.final_test`, Auto MPG) are current again at HEAD (9 of 9, 11 of
11, 8 of 8), including the opened final test, and `check`, `render` and `export handoff` pass.

Any further edit of `activities.py` or `fit.py` (including the merge with `main`) makes these
edges stop matching: the `506180a` studies lose their current results again unless the
comparison is re-run against the new bytes and, if it matches, new edges are added from the
base digests (no transitivity). `test_the_library_v1_edges_target_the_current_bytes` fails
then, with that instruction.

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
