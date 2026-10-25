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

**Round 3.** Regression tests: `framework/tests/study/libraries/test_review_round3_a.py`
(ported from the reviewer's probes). **R3-A1:** a planted
`packages/mlflow_pyfunc/__pycache__/hypotrail_pyfunc.cpython-*.pyc` used to replace the MLflow
wrapper (MLflow imports it instead of the source the digests bind) while `verify_bundle`,
`ArtifactPackager.verify` (which even ran it) and the export passed. Now a `__pycache__`
folder or a `*.pyc`/`*.pyo` file anywhere in a bundle (`verify_bundle`, listed or not, also
under `evidence/` and in an embedded bundle) or in a package (`ArtifactPackager.verify` and
`_inventory`, which refuse it instead of skipping it) is `artifact_integrity_failed`; every
listed file under `packages/<format>/` must be named by that package's descriptor; and
`ArtifactPackager.verify` runs no package code before the bytecode, file-list, descriptor,
environment, `MLmodel` and embedded-bundle checks pass, then loads the package for parity
from a fresh temporary copy (checked against the descriptor) with `sys.pycache_prefix` on an
empty temporary folder and `sys.dont_write_bytecode` set, restored afterwards; `package`
does the same. **R3-A4:** loading `<bundle>/packages/mlflow_pyfunc` in place with
`mlflow.pyfunc.load_model` writes a bytecode cache into the bundle, which is still refused;
the runtime's message says that a Python bytecode cache was written into the bundle by
loading its package in place, names the folder, and its remediation says to delete it and to
load packages from a copy. The engine's own loads (packager verify, export verification) no
longer write anything into the bundle. The study's junior text for this refusal is the
generic `artifact_integrity_failed` one of `capture.loading_refusal` (a stray file); its
`detail` carries the runtime message. **R3-A2:** a package's `artifact_id` is the content id
of its descriptor (`canonical.artifact_id` of the contract document without `artifact_id`:
files with digests, signature, environment, parity, extensions), recomputed by
`verify_bundle` and by `ArtifactPackager.verify`; the descriptor inside the package
(`hypotrail-package.json`, named by the extension `hypotrail.descriptor_copy`) is now the
contract document itself, byte-identical to `packages/<format>.descriptor.json`, and the
runtime requires the two to be canonically equal; the MLflow packager writes
`requirements.txt`, `conda.yaml` and `python_env.yaml` itself from the bundle's pinned
environment (semantic dependencies, runtime, and the MLflow version recorded in the
descriptor; every pin a name and a version) instead of keeping MLflow's (which add the local
pip and setuptools versions), and `verify` regenerates and compares them byte for byte, the
descriptor's `environment` and `signature` too. This changes the package bytes of new
captures: `PACKAGER_VERSION` is `2`, and a package written by version 1 (inner descriptor in
the old format, MLflow's environment files, the old artifact id) is refused by the runtime
(artifact id) and by `verify` (`schema_version_unsupported`); capture it again. The round-2
test helper `_redescribe_mlflow_package` now models an attacker who also recomputes the
artifact id and writes the same descriptor inside and beside the package, so the round-2
refusals are still the embedded-bundle checks. **R3-A3:** `_check_embedded` also requires
`MLmodel` to have only the `python_function` flavor, the environment files `conda.yaml` and
`python_env.yaml`, and the signature of the bundle; `ArtifactPackager.verify` converts every
exception into a `PackagingError` (a runtime `ContractError` keeps its code, with
`details.contract_code`; anything else, an `MlflowException` included, is
`artifact_integrity_failed`) or a `failed` result. **R3-A5:** an empty or relative trusted
root (`trusted_roots=['']`, `['.']`, `[Path('rel')]`) is `contract_invalid`; empty and relative
entries of `HYPOTRAIL_RUNTIME_TRUSTED_ROOTS` are dropped. The MLflow wrapper and the packager
pass resolved paths. **R3-A6:** the calibration ledger is read strictly. A torn last line
(no final newline, not a JSON document) is ignored for reading; the next claim removes it
under the lock by an atomic rewrite that keeps every complete line byte for byte, reports it
(`LedgerRepaired` warning, `CalibrationLedger.repairs`) and appends after it; a complete last
use without its newline is kept. Any other corruption (an unreadable middle line, a complete
last line that is not a use, a malformed field) is `contract_invalid` with a remediation, from
`uses()` and `claim()`, and nothing is claimed past it. **R3-A7:**
`test_workshop_capture_tampered_package_refuses_the_final_test` asserted an opening recorded
as failed; since `2b6c806` the opening is refused before it is recorded, and the test now
asserts that stronger behaviour (`precondition_missing`, requirement `capture_loadable`,
contract code `artifact_integrity_failed`, no result, nothing opened, no final-test exposure,
no evidence binding). The round-2 concurrency test patches `CalibrationLedger._read`, the
strict reader a claim now uses. **Observation:** `capture._membership` uses one digest scheme
for the training scope: under training exclusions it is the blob id the study store would
give the fitted keys (SHA-256 of `records.row_keys_bytes`, newline-terminated lines), the
scheme of the development blob id, no longer `'\n'.join(sorted(keys))`;
`test_the_capture_names_the_rows_it_was_fitted_on` checks it against `put_blob`. **Non-finite features (from area B):** `inference.check_frame` (every fit,
parity check and prediction) refuses `inf`/`-inf` in a `float64` feature with
`contract_invalid`, issue `{path: input/<col>, kind: non_finite_values, n_rows, rows}` (the
shape the exported project uses), instead of a raw scikit-learn `ValueError`; `NaN` keeps its
handling. Captures
made before this round read as `code_changed` (the runtime and packager sources changed).
Evidence: `framework/tests/study/libraries`,
`framework/tests/exporters` and `framework/tests/study/test_review_round2_training_exclusions.py`
together 500 passed, 7 skipped (507 collected: 243, 250 and 14; the round-3 file holds 36).

**Round 4.** Regression tests: `framework/tests/study/libraries/test_review_round4_a.py`
(the reviewer's probes ported, with variants; every bundle and study in `tmp_path`).
**R4-A1 (blocking):** `ArtifactPackager._check_embedded` compared a few keys of `MLmodel`'s
`python_function` block and nothing limited the files of a package, so `data: evil` in
`MLmodel` made `mlflow.pyfunc.load_model` load `evil/MLmodel` and `evil/hypotrail_pyfunc.py`,
which no check read; `verify_bundle` accepted, `ArtifactPackager.verify` returned `passed`
(and ran the evil wrapper), and the export said `packaged`. Now (1) `MLmodel` is the
packager's own document (`mlflow_packaging.mlmodel_document` / `mlmodel_bytes`: the
`python_function` flavor with the code-model loader, the wrapper, the embedded bundle as the
only artifact, the packager's environment files, the bundle's signature, the bundle's Python
version and the package's MLflow version; indented JSON with sorted keys, ASCII, which MLflow
reads as YAML; no clock, random model id, local path, `data`, `code`, `model_config` or other
key), written in place of MLflow's after `save_model` (whose loading keys are checked first,
so an MLflow version that would load the package otherwise is refused with
`capability_not_supported`); `verify` regenerates it from the descriptor's signature and
environment (both already checked against the bundle) and compares the bytes, and a refusal
names the differing keys (`details.unexpected`, `missing`, `changed`, dotted, for example
`flavors.python_function.data`); (2) the files of an `mlflow_pyfunc` package are an allowlist
(`PACKAGE_FILES`: `MLmodel`, `hypotrail_pyfunc.py`, `requirements.txt`, `conda.yaml`,
`python_env.yaml`, `hypotrail-package.json`, plus `artifacts/native_bundle/**`, the embedded
bundle checked against the native one): `package` and `verify` refuse any other file or
folder, an empty one included, and any missing file (`refuse_layout`,
`artifact_integrity_failed`, `details.unexpected` / `missing` / `allowed`), and the runtime's
`verify_bundle` refuses, for the `mlflow_pyfunc` format, a listed package file outside the
same list (`hypotrail_runtime.predictor.MLFLOW_PYFUNC_FILES`, kept equal to the packager's by
a test; the runtime still imports no packager) or a missing one, and a descriptor whose copy
or embedded-bundle extensions are not `hypotrail-package.json` and `artifacts/native_bundle`;
(3) `verify` still runs no package code before the layout, descriptor, environment, wrapper,
`MLmodel` and embedded-bundle checks pass, and then loads a fresh temporary copy. Because
`MLmodel` no longer carries MLflow's clock and random id, two captures of the same predictor
now give the same package and the same `artifact_id`. This changes the package bytes:
`PACKAGER_VERSION` is `3`; a version-2 package is refused by `verify`
(`schema_version_unsupported`, capture again) and, inside a bundle, by the export. **R4-A2
(minor):** `predictor.capture` records `values.packages[].artifact_id`, but nothing compared it
with the package the bundle holds. Now `read_export_source` states the recorded packages in
the extension `hypotrail.packages` (`[{format, artifact_id}]`, empty without a capture), and
the export refuses a bundle whose packages are not those (a recorded package missing, one the
capture did not record, or another artifact id) with `artifact_integrity_failed`,
`details.reason: package_not_recorded`, path `predictor.packages`, before any package is
verified or loaded (see the Azure ML handoff §11, round 4). The final-test opening's
loadability check (`capture.load_for_final`, so `require_loadable` and `loading_problem`)
compares the verified bundle's packages with the capture's recorded ones the same way
(`capture.package_mismatch`) and refuses with the same reason; its junior message (English and
French) says that the model package in the saved bundle is not the one recorded at capture
(naming the format), and to restore the bundle from a trusted copy or run `predictor.capture`
again, then open the final test; no final-test row is read. Captures made before this round
read as `code_changed` (the runtime, packager and capture sources changed) and are captured
again.
Evidence: `framework/tests/study/libraries` and `framework/tests/exporters` together 747
passed, 6 skipped (753 collected: 271 and 482; the round-4 file holds 28).

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

Any further edit of `activities.py` or `fit.py` (including the merge with `main`; review
round 2 made one, see the next section) makes these edges stop matching: the `506180a` studies lose their current results again unless the
comparison is re-run against the new bytes and, if it matches, new edges are added from the
base digests (no transitivity). `test_the_library_v1_edges_target_the_current_bytes` fails
then, with that instruction.

## Delayed labels (review round 2)

Pre-existing scientific defect, fixed on top of `818995c`. Under the `review-v1` temporal
profile with an outcome clock (`analysis_contract.timing.outcome_available_order`),
`partition.assign` listed the development rows whose outcome is available only at or after the
final start (their labels were not known at the simulated decision time) and `init` stored
them as `partition.training_exclusions.row_keys`, and the partition said they were "excluded
before training", but nothing read them: the split, the exploration of the target, every fit,
fold, inner tuning, validation score, the final refit and `predictor.capture` used them.

Now (`partition.training_exclusions`, `activities.load`, `CLI-CONTRACT.md` § Review-v1
evaluation plan):

- every activity except the structural inspections `eda.quality` and `eda.correlation` (no
  target, no split; the rows' predictors are known at decision time, only their labels are
  not) records `inputs.training_exclusions` and reads the development rows less those. The
  split holds none of them (blobs, folds, evaluation plan), so the training-partition
  exploration, the fits, the folds, the policy and regression evaluations and the diagnostics
  follow; `final_test.evaluation` refits and `predictor.capture` fits on the development rows
  less them. The exposure these activities record leaves them out; what was recorded before
  stays recorded. The AzureML export takes its development rows from the split, so it follows
  too.
- visibility: `values.training_exclusions` (`{n_rows, reasons, note}`) on the split and the
  final evaluation, `values.refit.n_rows` and the capture's `n_train`, and the limit
  `delayed_labels_excluded` in the status, the summary, the pause and the report: the term
  first ("A delayed label is an outcome that becomes known only some time after the
  prediction is made."), the count, then an example in the study's own prediction clock
  (English and French).
- a result computed with those rows (before the fix) is not current
  (`stale_reason.delayed_labels_included`, `partition.ignores_exclusions`), and a plan that
  would build on it is refused (`precondition_missing`, `computed_without_delayed_labels`)
  until it is computed again. `final_test.evaluation` runs once: a study with exclusions whose
  final test was opened before the fix keeps its recorded figures, shown as not current.

Compatibility. The shipped cases declare no outcome clock (`n_rows` 0), so no study of them
has an exclusion; for every such study nothing the engine plans or computes changes (no key,
no filter, no refusal: the code paths are taken only when the list is not empty). The edit of
`activities.py` (`d6806ce3…` → `b7c994d2…`) would still make every result of every existing
study report `code_changed`, so `mlkit/study/code_compat.py` holds two new exact edges to
`b7c994d2…`: from the `818995c` digest and from the `506180a` digest, each for the 21
activities of the base engine (`split`, the nine `eda.*`, the four fits, `policy.evaluation`,
`policy.inspect`, `evaluate.regression`, `diag.binary`, `diag.regression`,
`final_test.evaluation`, `diag.final_test`). Not attested: `predictor.capture` (its predictor
and computation ids hash the code fingerprint, never byte-identical across engines) and
`diagnostics.population` (its Evidently statistics differ in the last bits between runs and
its snapshot blob is not reproducible, so there is no byte equality to attest); such results
computed at `818995c` report `code_changed` and are recomputed by running them again, with the
consequence for a final evaluation that scored a capture described above. A study whose
outcome clock leaves rows out is not current whatever the edges say
(`partition.ignores_exclusions`), which is the intended consequence. The reviewed pre-WP-J
edge (`b04e5fad…`, `diag.final_test` only) is carried to `b7c994d2…` by a third exact edge, on
the evidence of that review and of the comparison below (`diag.final_test` byte-identical
between the `818995c` and current engines); no engine of the `b04e5fad…` digest was run.

Evidence (`framework/tests/study/code_compat_evidence.py`, extended: two review-v1 studies
without exclusions, an independent synthetic case and a future case whose outcome is known
at prediction time, and `diagnostics.population` in every study when the old engine has it,
reported but left out of the verdict). Each engine was a `git archive` of its commit run with
this checkout's environment (the lock of `818995c` is the current one; every package of the
`506180a` lock has the same version in it). With the `818995c` engine: 153 commands on six
studies (bin, bin-cv, reg, reg-cv as in E1, plus rev-ind and rev-fut0, each to an opened final
test and `diag.final_test`), the same outcomes, all succeeded; of the 109 attested registry
results, 77 are byte-identical (values, output digest, blobs, params, partition, row count)
and the 32 others (`policy.*`, `evaluate.regression`, the diagnostics) differ only by the ids
of their upstream results; in copies of the `818995c` studies the current engine finds every
promoted result of an attested activity current (99 of the 105 promoted results; the 6
others are the population profiles) and recomputes the 64 attested
leaf results byte-identically. `diagnostics.population` (6 fresh results, 6 leaves) differs in
the last bits of an Evidently p-value and in its snapshot blob in some studies and not in
others, and is not current there (no edge). With the `506180a` engine: 147 commands on the
same six studies (no population), the same outcomes; 109 results, 77 byte-identical and 32
identical up to upstream ids; every promoted result current at HEAD (99 of 99); 64 of 64
leaves byte-identical. Both comparisons print `MATCH`.
`test_review_round2_training_exclusions.py` checks, without the old engines, that the edges
target the current bytes and start at the recorded ones, their scope, and the behaviour
(fitted row keys, exposure, visibility, currency, unchanged identities without exclusions);
its opt-in `test_byte_comparison_with_the_previous_engine` repeats the comparison when
`HYPOTRAIL_COMPAT_OLD_PYTHON` and `HYPOTRAIL_COMPAT_OLD_ROOT` name an old engine.

Pre-existing defects seen while testing, fixed in review round 3 (below): a `tuned` or
`family` variant under a review-v1 explicit plan failed with `NameError: np`
(`families.choose` used `np` without importing it), and the generated notebook of a review-v1
explicit-plan study failed in its cross-validation cell (the fold series holds the scored rows
only, the development frame every development row). The capture's
`training_scope.membership_sha256` names the rows the capture was fitted on (since `ce82ca9`:
with exclusions, a digest of the eligible keys rather than the development blob; the digest
scheme belongs to `contracts/capture.py` and may change again), and `n_train` and the result's
`inputs.training_exclusions` give the same rows.

## Review round 3

Engine fixes of the review of 2026-10-25 (round 3), on top of `ce82ca9`
(`framework/tests/study/test_review_round3_engine.py`, temporary studies only; the reviewer's
scripts are ported there):

- E3-1, the notebooks with delayed labels: `notebook_view.development_frame` marks the rows the
  split was computed without `delayed_label` (it gave them partition `None` and the
  cross-validation cell used every development row, so its `assert` failed, 240 against 238,
  and the target and special-value cells after it); the split cell's `train` holds the
  split's rows only and counts the delayed-label rows apart; every cell that reads the target
  or fits reads `train`; the rows cell explains the term first, then prints this study's
  example (the engine's limit, in the study language), and the split step shows it.
- E3-2: the limit `delayed_labels_excluded` cites the final boundary ("prediction_tick 241")
  and the number of rows left out, which the number check rejected (`export handoff` refused
  every study with exclusions, `untraceable_number`; `check --text` flagged the engine's own
  text). Those two state values are now traced only in the context the limit writes them
  (source `partition`): the same numbers anywhere else stay untraceable, so the guarantee is
  not weakened for other text.
- E3-3 (completing E2-1): confirming `final_test`, and the reservation of
  `final_test.evaluation`, require every result the confirmation rests on (split, fits,
  variants, evaluation, review-v1 diagnostics, capture) to be current by the rule of `status`
  (`code_changed` under the attestations, `delayed_labels_included`, upstream), not the stale
  map alone (`mlkit.study.opening`); otherwise `precondition_missing` names them, with a junior
  message (run them again first; no final-test row was read). `next_action` then recommends
  running the first of them (`not_current` lists all), never the opening.
- E3-4: after an opening made before the delayed-label fix, `run diag.final_test` says the
  final test cannot be recomputed (junior message, study language), not "run it again".
- B3-0: `fit.compute_explicit_cv` read the regression target (an array) by row key, so every
  regression fit under a review-v1 explicit plan raised `AttributeError`; it is now indexed
  like the frame. Regression under review-v1 explicit plans is covered (fits, cross-validation,
  tuned variant, comparison, capture, final test, diagnostics, notebook).
- Known bugs: (a) `families.choose` imports numpy; (b) the explicit plan's notebook cells follow
  the registered memberships (each fold fitted on its `train_keys`, scoring its
  `validation_keys`; the regression baseline the median of each fold's training rows); (c) a
  glossary example whose value the result does not hold (the explicit baseline's single
  `train_rate`) is not shown, as `explain` does; (d) the study panel shows
  `delayed_labels_excluded` as a caveat (English and French; ADR 0004 constraints unchanged).

Compatibility. `fit.py` (`d39f3f5b…` → `9ca62f79…`) and `families.py` (`2d874879…` →
`4e207920…`) changed; both are in code fingerprints. The changed paths raised an exception with
every earlier engine (no earlier result was computed on them), and every other path is
unchanged, so `mlkit/study/code_compat.py` holds three new exact edges: `fit.py` from the
`ce82ca9` digest (unchanged since `621d607`, so also the `818995c` one) and from the `506180a`
digest (`28c00840…`), each for the eight activities whose fingerprint holds `fit.py` but the
capture (`fit.baseline`, `fit.logistic`, `fit.linear`, `fit.variant`,
`eda.single_feature_signal`, `diag.binary`, `diag.regression`, `final_test.evaluation`), and
`families.py` from its digest (unchanged since `506180a`) for `fit.variant` and
`final_test.evaluation`. Not attested, as before: `predictor.capture`, whose predictor and
computation ids hash the code fingerprint; a capture computed before reports `code_changed`
and is captured again (E2-1 and E3-3 refuse the opening on it until then). `activities.py` is
unchanged (`b7c994d2…`), so its round-2 edges still apply. The existing edge tests are kept;
`test_code_compat_library_v1.py::test_the_library_v1_edges_target_the_current_bytes` now
expects, for `fit.py`, the fit activities its edges covered (it compared every module with the
21 activities, which holds for `activities.py` only).

Evidence (`code_compat_evidence.py`, unchanged; each old engine a `git archive` of its commit
run with this checkout's environment, its own `hypotrail_runtime` first on the path when it
has one). With the `ce82ca9` engine: 153 commands on the six studies of round 2, the same
outcomes, all succeeded; 109 attested results, 77 byte-identical and 32 identical up to
upstream ids; every promoted result current at HEAD in copies of the `ce82ca9` studies (105 of
105, the population profiles included: their modules are unchanged); 64 of 64 leaves
byte-identical; `MATCH`. With the `818995c` engine (both its `activities.py` edge of round 2
and the new `fit.py` edge apply): the same 153 commands and figures, 99 of 105 promoted
results current (the 6 others are the population profiles, not attested since round 2), 64 of
64 leaves byte-identical; `MATCH`. With the `506180a` engine (its
`activities.py` edge of round 2, the new `fit.py` edge from `28c00840…` and the `families.py`
edge apply together): 147 commands on the same six studies (no population), the same
outcomes; 109 results, 77 byte-identical and 32 identical up to upstream ids; every promoted
result current at HEAD (99 of 99); 64 of 64 leaves byte-identical; `MATCH`. The paths fixed
here (regression and tuned or family variants under a review-v1 explicit plan) cannot be
compared: they raised an exception with every old engine.
`test_review_round3_engine.py` checks, without the old engines, that the edges target the
current bytes and start at the recorded ones (`ce82ca9`, `818995c`, `506180a`), their scope,
direction and exactness; its opt-in `test_byte_comparison_with_the_previous_engine` repeats
the comparison when `HYPOTRAIL_COMPAT_OLD_PYTHON` and `HYPOTRAIL_COMPAT_OLD_ROOT` name an old
engine.

## Review round 4

Engine fixes of the review of 2026-10-25 (round 4), on top of `9991de7`
(`framework/tests/study/test_review_round4_engine.py`, temporary studies only; the reviewer's
scripts are ported there):

- E4-1 (blocking): a final test confirmed but not opened (an interrupted execution refuses the
  opening that follows the confirmation, or the process stops between the confirmation's
  commit and the reservation) could be opened by `run final_test.evaluation` on stale evidence
  or on a model the study no longer chose: the reservation checked only the confirmation and
  the currency of the results, and the dependency table never asked the final test again. The
  reservation now applies the confirmation's whole rule (`preconditions.opening_missing`: the
  stale map, full currency, the configuration chosen now, nothing awaiting reconfirmation, the
  confirmation itself) before anything is opened, with a junior message in the study language
  (`opening.reservation_message`). The safe option is implemented: a change of what the
  unopened final test rests on (a decision it rests on, a hold, a result of the opening's basis
  replaced or made stale) makes its confirmation `reconfirm_required`
  (`dependencies._final_test_basis_changed`), so the junior confirms it again, in their own
  words, on the configuration the study then chooses; confirming it again changes no result
  (`final_test.reconfirmed`, a quiet mutation; it was the `unknown` row, which would have made
  everything stale). Once opened, the final test is never asked again (WP-B1).
- E4-2: after an opening made before the delayed-label fix (or an opening interrupted before
  its evaluation was recorded), `next_action` no longer loops on `run diag.final_test` (or `run
  final_test.evaluation`), both refused: it proposes the conclusion with the verdicts its rule
  still accepts (`verdicts`, `not_recomputable`), then `done`, with a junior message saying the
  final test cannot be recomputed and what remains (English and French).
- E4-3: every `next_action` runs as given: a run of the policy evaluation carries its `rules`;
  a reconfirmation its `default_value` (the policy's rule on the model chosen now, the final
  test's configuration); a reconfirmation whose own preconditions need a result runs that
  result first. A test follows every `next_action` of the round-3 and round-4 scenarios.
- E4-4: clock values are written exactly in the limit text (`20170301`, never `2.01703e+07`)
  and traced.
- E4-5: the report's data section shows the development rows, the delayed-label rows left out
  and the rows used apart; review-v1 explicit plans are read as cross-validations (they were
  shown as a stratified holdout split), and forward-chaining plans say that each later window
  is scored once by models fitted on earlier rows only and that the warm-up rows are never
  scored (English and French labels of the split card).
- E4-6: a French report failed its own `check` (`value_mismatch`): "1,286" was read as 1,286.
  The French renderer writes a narrow no-break space between thousands and a decimal comma
  whatever the format, and French text is read with a decimal comma (a comma never groups
  thousands); the review-v1 binary reports pass `check` with no error in English and French,
  with and without delayed labels.
- Number tracing: "241k", "1.5M", "241e3" are traced as the number they scale to (or reported),
  and an integer right after an ISO date is checked (the date's time of day must look like one).

Compatibility. No module of any activity's code fingerprint changed (`activities.py`,
`fit.py`, `families.py` and the other fingerprinted modules are byte-identical to `9991de7`):
the changes are in `state`, `dependencies`, `preconditions`, `opening`, `executions`, `view`,
`audience`, `numtrace`, `cite`, `cmd_check`, `commands`, `texts`, `render_html` and the content
files, none of which a result's identity or currency reads. No attestation edge is added, and
every result recorded by `9991de7` (or by an earlier engine the existing edges cover) stays
current. A study whose final test was confirmed but not opened when a decision it rests on
changed under an earlier engine keeps its `confirmed` status; its reservation is refused by the
new rule and `next_action` proposes the final test again (no loop).

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
