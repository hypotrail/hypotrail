# Handoff: Azure ML export v1 (chantier B)

Status on 23 October 2026: **B1 and B2 implemented; B3 done at integration I1 (the real
bundle and runtime of A, see INTEGRATION-LIBRARIES-AZUREML-V1.md); Azure not qualified** (no job, no endpoint, no Azure call was made).

`hypotrail export azureml` turns a study into a project in the team's Azure ML template
(team-azureml-v1): same paths, four steps, Hydra groups, `aml/` YAML, `.ci`, `.vscode`,
tests, docs and notebook; contents rendered deterministically from the study's recorded
decisions. The MLflow packager of contract v1 §6 (`ArtifactPackager`) is delivered and is
the hook chantier A injects into `capture_predictor`.

Sources: [export spec](../specs/azureml-export/Hypotrail-Spec-Export-AzureML.html),
[integration spec](../specs/azureml-export/SPEC-INTEGRATION-LIBRAIRIES.txt) and
[shared contract v1](../specs/azureml-export/CONTRAT-COMMUN-v1.txt) (French originals,
kept as received), [layout](../specs/azureml-export/TEMPLATE-LAYOUT-v1.json),
[transport inventory](../specs/azureml-export/TEMPLATE-TRANSPORT.json),
[SHA-256 of these copies](../specs/azureml-export/SHA256SUMS) (identical to the pack's).
The contract and the integration spec amend the export spec on responsibilities, the
MLflow hook and paths; where they disagree, they were followed (listed below).

## 1. Base, branch and inputs

| Item | Value |
|---|---|
| BASE_SHA | `581c7b3723629260a18e1281ef9e18583ae060a7` (the shared default; verified present) |
| `origin/main` when the work started | `581c7b3…` (no gap at that time; another agent pushes fixes to `main` meanwhile) |
| Branch | `claude/cool-lamport-q68gsv` |
| HEAD | the commit that adds this file (`git log claude/cool-lamport-q68gsv`) |
| Template archive | `ml_project_template-sans-historique.zip`, SHA-256 `b4bbe14e…a11ba62` (matches the transport inventory); the 53 kept files match their SHA-256; original archive identity `b2c3e943…cd7e` |
| Pack files | the 10 files of the pack match `SHA256SUMS.txt` |

**Branch name.** The work package names `feature/azureml-export-v1`. This cloud session can
push only to its assigned branch, `claude/cool-lamport-q68gsv`, so the work is there; it
starts from BASE_SHA, holds only this chantier's commits and was never merged into `main`
nor force-pushed. To use the requested name at integration:
`git branch feature/azureml-export-v1 origin/claude/cool-lamport-q68gsv`.

The archive was inspected without running any of its scripts; nothing of it executes at
export time (the generator reads its own versioned store, never the ZIP).

## 2. What is delivered

| Path | Role |
|---|---|
| `framework/mlkit/exporters/azureml/command.py` | `export_azureml`: validation, snapshot, render, atomic publication, payload `hypotrail.azureml_export/1` |
| `…/snapshot.py` | consumer of A's `read_export_source`; builds `hypotrail.deployment_snapshot/1` and the development plan (development keys only) |
| `…/artifact.py` | verification of a captured bundle (via `hypotrail_runtime.verify_bundle`), evidence binding, MLflow package verification, environment checks |
| `…/profile.py` | destination profile `hypotrail.azure_target/1`: draft/configured, missing fields, credential refusal |
| `…/render.py` | the declarative generator (`template.json` + `@@filter:name@@` markers), export manifest, readiness, lock, SHA256SUMS, notebook; self-check of the rendered Hydra projection |
| `…/layout.py` | the versioned template (store integrity against the transport inventory) and AZ-STRUCT-02 `check_tree` |
| `…/writer.py` | target checks (non-empty, symlink, study folders) and atomic publication (temporary sibling + rename) |
| `…/canonical.py`, `projection.py`, `transfer.py`, `azure_yaml.py` | standalone modules, copied byte for byte into each project (same identities, same checks on both sides) |
| `…/templates/team-azureml-v1/` | the cleaned skeleton: `template.json`, `files/` (a leading `.` stored as `dot-`), `layout.json` and `transport.json` (byte copies of the shared ones, hash-checked), `env/requirements-azureml.lock` |
| `framework/mlkit/integrations/mlflow_packaging.py` | `ArtifactPackager.package/verify`, `PackageDescriptor`, `ParityResult`, `packager_for(profile)`; standalone, copied into each project |
| `framework/mlkit/study/cmd_export.py` | routing only: `KINDS` gains `azureml`, four options, one dispatch |
| `framework/tests/exporters/azureml/` | 100+ tests; `fixtures/fake_runtime/` is the **private test double** of `hypotrail_runtime` |

### Generated project (team-azureml-v1)

Map of every path (kind: `preserved` byte-identical to the team template, `adapted` same
path with new fixed content, `rendered` markers from the snapshot, `added` allowlisted new
path, `shared` copy of a generator module, `generated` document, `copied` model files):

| Path | Kind | Origin | Source |
|---|---|---|---|
| `.pre-commit-config.yaml` | preserved | team template |  |
| `.vscode/extensions.json` | preserved | team template |  |
| `data/.gitignore` | preserved | team template |  |
| `docs/media/.gitkeep` | preserved | team template |  |
| `src/conf/hydra/job_logging/custom.yaml` | preserved | team template |  |
| `src/conf/logging_config.yaml` | preserved | team template |  |
| `src/pipeline/utils/enums.py` | preserved | team template |  |
| `src/pipeline/utils/tracking.py` | preserved | team template |  |
| `tests/conftest.py` | preserved | team template |  |
| `tests/pipeline/__init__.py` | preserved | team template |  |
| `tests/pipeline/data_preparation/__init__.py` | preserved | team template |  |
| `.gitignore` | adapted | team template |  |
| `.vscode/launch.json` | adapted | team template |  |
| `.vscode/tasks.json` | adapted | team template |  |
| `.ci/pipeline.yml` | adapted | team template |  |
| `Makefile` | adapted | team template |  |
| `cli-aliases.sh` | adapted | team template |  |
| `src/pipeline/data_preparation/main.py` | adapted | team template |  |
| `src/pipeline/data_splitting/main.py` | adapted | team template |  |
| `src/pipeline/training/main.py` | adapted | team template |  |
| `src/pipeline/evaluation/main.py` | adapted | team template |  |
| `src/pipeline/utils/data_management.py` | adapted | team template |  |
| `tests/pipeline/data_preparation/test_main.py` | adapted | team template |  |
| `docs/pages/.order` | adapted | team template |  |
| `README.md` | rendered | team template |  |
| `pyproject.toml` | rendered | team template |  |
| `environment.yml` | rendered | team template |  |
| `.vscode/settings.json` | rendered | team template |  |
| `.ci/deploy-pipeline.yml` | rendered | team template |  |
| `aml/components/data_preparation.yml` | rendered | team template |  |
| `aml/components/data_splitting.yml` | rendered | team template |  |
| `aml/components/evaluation.yml` | rendered | team template |  |
| `aml/components/training.yml` | rendered | team template |  |
| `aml/pipelines/training/aml-environment.yml` | rendered | team template |  |
| `aml/pipelines/training/data.yml` | rendered | team template |  |
| `aml/pipelines/training/pipeline-job.yml` | rendered | team template |  |
| `aml/pipelines/training/pipeline.yml` | rendered | team template |  |
| `src/conf/base_config.yaml` | rendered | team template |  |
| `src/conf/config.yaml` | rendered | team template |  |
| `src/conf/components/data_preparation/default.yaml` | rendered | team template |  |
| `src/conf/components/data_splitting/default.yaml` | rendered | team template |  |
| `src/conf/components/evaluation/default.yaml` | rendered | team template |  |
| `src/conf/components/training/default.yaml` | rendered | team template |  |
| `src/conf/components/training/random_forest.yaml` | rendered | team template |  |
| `src/pipeline/utils/schemas.py` | rendered | team template |  |
| `docs/pages/architecture.md` | rendered | team template |  |
| `docs/pages/code.md` | rendered | team template |  |
| `docs/pages/data.md` | rendered | team template |  |
| `docs/pages/references.md` | rendered | team template |  |
| `docs/pages/deployment.md` | rendered | new (allowlist) |  |
| `src/conf/hypotrail/replay.yaml` | rendered | new (allowlist) |  |
| `aml/pipelines/training/runtime/Dockerfile` | rendered | new (allowlist) |  |
| `.amlignore` | added | new (allowlist) |  |
| `src/pipeline/utils/project.py` | added | new (allowlist) |  |
| `src/pipeline/utils/hypotrail/__init__.py` | added | new (allowlist) |  |
| `src/pipeline/utils/hypotrail/errors.py` | added | new (allowlist) |  |
| `src/pipeline/utils/hypotrail/runtime_bridge.py` | added | new (allowlist) |  |
| `src/pipeline/utils/hypotrail/contracts.py` | added | new (allowlist) |  |
| `src/pipeline/utils/hypotrail/config.py` | added | new (allowlist) |  |
| `src/pipeline/utils/hypotrail/steps.py` | added | new (allowlist) |  |
| `tests/test_export_contract.py` | added | new (allowlist) |  |
| `aml/pipelines/training/runtime/README.md` | added | new (allowlist) |  |
| `src/pipeline/utils/hypotrail/canonical.py` | shared | new (allowlist) | mlkit.exporters.azureml.canonical |
| `src/pipeline/utils/hypotrail/projection.py` | shared | new (allowlist) | mlkit.exporters.azureml.projection |
| `src/pipeline/utils/hypotrail/transfer.py` | shared | new (allowlist) | mlkit.exporters.azureml.transfer |
| `src/pipeline/utils/hypotrail/azure_yaml.py` | shared | new (allowlist) | mlkit.exporters.azureml.azure_yaml |
| `src/pipeline/utils/hypotrail/mlflow_packaging.py` | shared | new (allowlist) | mlkit.integrations.mlflow_packaging |
| `notebooks/01_first_draft.ipynb` | generated | team template | notebook |
| `src/conf/hypotrail/contracts/model-recipe.json` | generated | new (allowlist) | recipe |
| `src/conf/hypotrail/contracts/data-contract.json` | generated | new (allowlist) | data_contract |
| `src/conf/azure/target.yaml` | generated | new (allowlist) | azure_target |
| `data/hypotrail/contracts/model-recipe.json` | generated | new (allowlist) | recipe |
| `data/hypotrail/contracts/data-contract.json` | generated | new (allowlist) | data_contract |
| `data/hypotrail/contracts/development-plan.json` | generated | new (allowlist) | plan |
| `data/hypotrail/contracts/deployment-snapshot.json` | generated | new (allowlist) | snapshot |
| `data/hypotrail/contracts/scientific-projection.json` | generated | new (allowlist) | projection |
| `data/hypotrail/contracts/readiness.json` | generated | new (allowlist) | readiness |
| `aml/pipelines/training/requirements.lock` | generated | new (allowlist) | lock |
| `aml/pipelines/training/runtime/requirements.lock` | generated | new (allowlist) | lock |
| `data/hypotrail/contracts/export-manifest.json` | generated | new (allowlist) | export_manifest |
| `data/hypotrail/SHA256SUMS` | generated | new (allowlist) | sha256sums |
| `data/hypotrail/models/evaluated/**` | copied | new (allowlist) | the captured bundle, byte copy |
| `aml/pipelines/training/runtime/<wheel>` | copied | new (allowlist) | the bundle's runtime wheel |
| `data/01_raw/reviews.csv` | removed | team template | business example data; directory kept |
| `data/01_raw/companies.csv` | removed | team template | business example data; directory kept |
| `data/01_raw/shuttles.xlsx` | removed | team template | business example data; directory kept |

### Justified deviations from the template

- **`code:` is the project root (`./../../`), filtered by a root `.amlignore`**, instead of
  `./../../src/`. The layout allows `.amlignore` at the root only; Azure ML reads the
  `.amlignore` of the uploaded folder, so a root upload is the only way to make it apply.
  The commands become `python -m src.pipeline.<step>.main`, the same as the template's
  README, launch.json and tests. The effective upload is tested (`transfer.transferable`):
  `src/` and root metadata only.
- **Model output type `uri_folder`** instead of `mlflow_model`: a run writes the native
  bundle, whose MLflow package sits at the relative path chosen at capture
  (`optional_packages`). Registering an MLflow model is a later explicit command.
- **One data asset** `data/hypotrail` (development rows, contracts, evaluated model), since
  the template has one `data.yml`; `.amlignore` keeps it out of the code upload.
- **`test_data` removed from `base_config.yaml`**: the evaluation step makes technical
  checks on parity rows; nothing names a test set the project does not have.
- **No sweeper or multirun, no `KEYVAULT_NAME`** in `config.yaml` (example-specific; a new
  exploration is a study activity). `random_forest.yaml` stays, `status:
  inactive_not_evaluated`, refused in replay.
- **`cli-aliases.sh`, `Makefile`, destructive tasks neutralised**: the files and labels
  stay; nothing edits `~/.bashrc`, `cd`, `.env` or conda environments, `clean` removes
  caches only, `clean_git_ignored_files` is a dry run.
- **`.gitignore`**: `*.amlignore` dropped (the file must be versioned); `data/hypotrail`
  contracts and the evaluated model re-included; development rows and `outputs/` ignored.
- **`data_management.py`**: no recursive deletion, no Excel (openpyxl not shipped), no
  pickle reading. `schemas.py` names the data contract's columns; Pandera is not shipped
  (chantier A derives Pandera from the DataContract in the engine).
- **Python 3.13** (`environment.yml`, ruff `py313`), not the template's 3.11; image from the
  profile, environment built from `aml/pipelines/training/runtime/` (Dockerfile, lock, wheel).
- Contract over export spec: `capability_not_supported` replaces the spec's
  `unsupported_export_capability`; `destination_not_empty` is answered with the existing
  `export_target_exists` (contract code in `details.contract_code`); paths follow the new
  mapping (no `azure/`, `deployment/`, `model/`, `scripts/`).

## 3. Contracts consumed, and the interface points to confirm at merge

> **Closed at integration I1** ([INTEGRATION-LIBRARIES-AZUREML-V1](INTEGRATION-LIBRARIES-AZUREML-V1.md)):
> `read_export_source` lives in `mlkit.contracts.export_source`; the bundle document is
> `predictor_bundle.json` (kept); parity tables are the runtime's typed JSON documents
> (`hypotrail.parity_frame/1`, `hypotrail.parity_outputs/1`), read by `read_table`; the
> parser keys are `encoding`, `delimiter`, `header`, `quotechar`, `na_values`, `decimal`;
> row keys are `L<physical line>` (the first data line of a file with a header is `L2`;
> `materialize` was corrected); `load_predictor` takes an explicit `trusted_roots`; the
> test double of the runtime was removed and every suite runs on the real runtime. The
> table below is the pre-integration text.

B consumes, never reimplements: `read_export_source` (A, engine), and from
`hypotrail_runtime`: `verify_bundle`, `load_predictor` (`Predictor.predict` →
`PredictionBatch`), `validate_recipe`, `validate_data_contract`, `fit_predictor`,
`capture_predictor(..., packager=)`. Without them the export refuses with
`optional_dependency_missing` (no fallback reader, no stub in a production path).

Contract v1 leaves these details open; the consumer assumes the values below, each in a
single place, to be confirmed or adjusted once with chantier A (not changed unilaterally):

| Point | Assumed here | Where |
|---|---|---|
| Module of `read_export_source` | `mlkit.study.export_source` | `snapshot.SOURCE_MODULE` |
| `ExportSource` field names | `study_id`, `revision`, `scientific_contracts.{model_recipe,data_contract}`, `decisions[{decision_id,status,value}]`, `results[{result_id,activity,current}]`, `validity`, `development_plan{protocol_id,partitions[{id,role,row_keys,membership_sha256,exposure_status}],final_test{status,n_rows}}`, `predictor{bundle_dir}`, `limitations`; optional `case`, `metrics`, `conclusion`, `development_data` | `snapshot.build` |
| Bundle document file name | `predictor_bundle.json` at the bundle root | `mlflow_packaging.BUNDLE_DOCUMENT` |
| Family ids of the qualified models | `linear` (task `regression`, output `regression_point`); since R19 `logistic` (task `binary`, output `binary_score`) | `template.json` `capabilities` |
| DataContract `parser` keys | `encoding`, `delimiter` (`whitespace` or a character), `header`, `quotechar`, `na_values` | project `contracts.py`, `project.py materialize` |
| Positional row key | `L<physical line>`, prefix `row_identity.prefix` (default `L`) | `project.py materialize` |
| Parity tables | `.csv` (header), `.json` records or `.parquet`; expected outputs named by `output_contract.columns` | `mlflow_packaging.read_table` |
| Model lock format | `name==version` lines | `render.lock_bytes` |
| `PredictionBatch.values` | 1-D for one output column, 2-D otherwise; `row_order` indices of the input | `mlflow_packaging.batch_frame` |
| Packager call by A | `packager.package(native_bundle_dir, output_dir, parity_spec=None)`; `output_dir` may be inside the bundle (the copy excludes it) | `ArtifactPackager.package` |
| ComputationContext passed by a rebuild | a `hypotrail.computation_context/1` mapping | project `steps.train` |
| Membership hashes | A's `membership_sha256` is carried as provenance; B's own `keys_sha256` (canonical sorted keys) is what the project verifies | `snapshot._plan` |

## 4. Statuses (spec §14) and what each export carries

`readiness.json` and the README keep independent statuses: configuration `draft` /
`configured`; artifact `missing` / `captured` / `packaged`; evidence `evaluated` /
`unassessed` / `stale` (from the study's record in `read_export_source`, which the
bundle's editable binding can only lower; never inferred, see §11); local validation,
preflight, job, registration, production authorisation, Azure qualification (all
`not_run` / `not_submitted` / `not_registered` / `outside_scope` / `not_qualified` in a
fresh export). A rebuilt candidate is always `rebuilt_candidate`, verdict
`not_inherited`, no generalisation metric.

## 5. Commands and results

```sh
uv sync --project framework --group dev --group browser --group azureml
uv run --project framework python -m pytest -q framework/tests/exporters
python3 scripts/check_layout.py
```

Results in this cloud session (Linux, Python 3.13.16, uv 0.11.32):

- `framework/tests/exporters`: **103 passed** (30 s), with MLflow-skinny 3.17.2, Hydra
  1.3.7, OmegaConf 2.3.1 and the **test double** of the runtime.
- Engine gate pytest line (`framework/tests/{study,acceptance,exporters}` and the listed
  modules): **1982 passed, 94 skipped, 2 failed** before the last fix; one failure was this
  branch's test (fixed, now in the 103 above). The other,
  `test_contract_companion_e2.py::test_c7_export_handoff`, **fails identically on the base
  commit 581c7b3** (its `HANDOFF_KEYS` lacks `history`, added in J4–J7): not caused by
  this branch, left to the `main` line. The 94 skips are the opt-in agent scenarios.
- `python3 scripts/check_layout.py`: no error.
- The exported project: its own `pytest` passes (18 tests) and `ruff check src` passes with
  the team template's ruff 0.4.5 rules.
- Not run here: the Node and companion-panel lines of the gate (no client file changed).

In an exported folder (moved elsewhere, runtime installed):

```sh
python -m src.pipeline.utils.project validate --offline
python -m src.pipeline.utils.project predict --parity --output outputs/predictions.json
python -m src.pipeline.utils.project materialize --source <original dataset file>
python -m src.pipeline.utils.project run-local --mode rebuild_final_candidate
python -m src.pipeline.utils.project preflight            # prints; --execute reads Azure
python -m src.pipeline.utils.project submit               # prints; --execute writes to Azure
pytest
```

## 6. Acceptance criteria (integration spec §15)

Status words: **met (local, test double)**: passing tests on synthetic fixtures with the
test double of the runtime; **deferred (A)**: needs chantier A's real code; **A's**: owned
by chantier A, nothing for B to deliver; **not run**: needs an authorised Azure run.

| ID | Status | Evidence |
|---|---|---|
| AC01 | met | common BASE_SHA recorded; separate branch; nothing of the user overwritten |
| AC02–AC06 | A's | Pydantic, Pandera, identities, history, fit scope |
| AC07 | met (local, test double); deferred (A) for A's predictor | `test_mlflow_packaging.py` (native vs expected vs pyfunc, rtol 1e-10, atol 1e-12, never relaxed), `evaluated_model_parity` |
| AC08 | A's (wheel); the export copies and pins it | `artifact.verify_predictor`, Dockerfile |
| AC09–AC16 | A's | runtime, bootstrap, Evidently, MAPIE |
| AC17 | met | project tests: `???` refused, unknown key and `_target_` refused, frozen copy unchanged after an environment change |
| AC18 | met | scientific overrides refused (`scientific_config_changed`), operational ones keep the SHA (project tests, `test_a_scientific_override_of_a_step_is_refused`) |
| AC19 | met (local, test double) | packager never fits (fit patched to fail), pyfunc loads in a fresh isolated process after a move, signature checked |
| AC20 | met | `test_template_layout.py`, `layout.check_tree` at every publication |
| AC21 | met | two exports byte-identical; a revision change changes the IDs; collisions refused untouched; the captured package is copied, not regenerated |
| AC22 | met (local, test double) | `test_exported_project.py`: moved folder, four steps, inference, project tests |
| AC23 | met | candidate has a new ID, `not_inherited`, no generalisation metric; an evaluated binding on a rebuilt candidate is refused |
| AC24 | met (fixtures) | no final-test key, secret or local path in any exported byte; the upload excludes data and secrets |
| AC25 | met for B's extra | `azureml` extra and group; the engine imports no MLflow/Hydra (`test_the_engine_imports_no_optional_library`); A's extras are A's |
| AC26 | **deferred (A)** | see §7 |
| AC27 | met | CLI only; no VS Code change; messages carry `remediation` |
| AC28 | met as a distinction; Azure **not run** | statuses and README separate YAML validity, job and endpoint; `azure_qualification: not_qualified` |

Export spec A-criteria: A02, A03, A04, A05, A10, A11, A13 (verdict copied, no promotion),
A14, A15, A16 (local atomicity), A19 met on fixtures; A01, A06, A07, A08, A09, A12 met on
the test double for what B owns, **re-run with A's runtime at merge** (A07/A08 semantics of
missing values, new categories and learnt state belong to A's predictor); A17, A18 need an
authorised Azure run; A20 (handoff and old studies) unchanged code paths, to re-run in
the full gate.

## 7. Deferred tests with chantier A (B3, I1)

Not replaced by any mock. After the merge, in a clean environment:

1. `HYPOTRAIL_EXPORT_REAL_RUNTIME=1 uv run --project framework python -m pytest -q framework/tests/exporters`
   (the fixtures then call the real `fit_predictor`/`capture_predictor`; the recipe's family
   and preprocessing names may need A's registry names; adjust the fixture, never the
   assertions).
2. Real end to end: synthetic study → authorised training → capture with
   `packager_for('atelier')` before the final test → controlled synthetic final test →
   `hypotrail export azureml` through A's real `read_export_source` → folder moved →
   `validate`, `predict --parity`, MLflow reload → `run-local` → distinct candidate.
3. Auto MPG workshop study (whitespace source without header, `?`), checking A's
   DataContract parser keys and `L<line>` keys against `project.py materialize`.
4. The study tree is byte-identical before and after an export (needs A's reader).
5. Old studies: export with `artifact_status: missing`, no confirmation added, no holdout
   reopened (A's `read_export_source` on a v0.2 study).
6. Close the interface points of §3 (one change each, both sides tested).

## 8. Likely merge conflicts

- `framework/pyproject.toml`: B adds the `azureml` extra and dependency group
  (`hydra-core==1.3.7`, `omegaconf==2.3.1`, `mlflow-skinny==3.17.2`); A adds its own extras.
  Unite the groups, then **regenerate** `framework/uv.lock` with `uv lock` (never merge the
  lock by hand). `mlflow-skinny` pulls `pydantic==2.14.1` in the lock: check it against A's
  Pydantic pin.
- `framework/mlkit/study/cmd_export.py`: B adds `azureml` to `KINDS`, four options and a
  dispatch at the top of `main`; keep every command and A's revision/exposure checks.
- `docs/specs/CLI-CONTRACT.md` (§15 added at the end) and `CONTRIBUTING.md` (gate line).
- `docs/handoff/`: this file is separate from `IMPLEMENTATION.md`; write the final state
  once at integration.

## 9. Cloud status

**Not qualified.** No Azure resource was read, created or submitted; no endpoint exists.
The YAML is checked statically (`azure_yaml.check`: expressions, bindings, explicit
versions, build context) and its graph is tested; that is not a successful job, and a job
is not a deployment. I2 (an authorised recipe run in a workspace, with its logs, artifacts
and image digest) is a separate step that needs explicit authorisation, a profile and
credentials, none of which this work had.

## 10. Limits

- Support matrix (`template.json` `capabilities`):

  | Task | Family | Output | Qualification |
  |---|---|---|---|
  | regression | `linear` | `regression_point` | local: native and MLflow pyfunc parity on synthetic and Auto MPG-like fixtures; Azure: not qualified |
  | binary | `logistic` | `binary_score` | local (R19): native and MLflow pyfunc parity of the positive-class score on synthetic binary and Bank/Hotel-like fixtures; the decision rule is metadata, never applied in the model output; Azure: not qualified |

  Everything else is refused with `capability_not_supported`, never substituted: ridge
  regression (a tuned or penalised regression variant), EBM and histogram boosting (no
  recipe: `details.reason: family_not_supported`), and calibrated (MAPIE) capabilities. A
  binary study's decision rule is never applied inside the model output (see R19 below).
- Replay mode `rebuild_final_candidate` only; `development_evaluation` is refused.
- Materialisation supports positional row keys only (`source_position`).
- `submit --execute` reuses an existing asset of the same name and version on an "already
  exists" answer without being able to compare its content through the CLI (recorded as
  `reused_existing`); a content mismatch is not detected there.
- The base image must provide Python 3.13; only an Azure recipe run qualifies it.
- The exported project's `validate` reads the model with the runtime's pickle-based
  native format: trusted local artefacts only (a hash does not make a third-party pickle
  safe).

## 11. Fixes of the review of 24 October 2026

From [REVIEW-2026-10-24](../acceptance/REVIEW-2026-10-24.md) (B-M1 to B-M5, E2 and the
export minor items). Regression tests: `framework/tests/exporters/azureml/test_review_fixes.py`
(synthetic material, the exported commands in subprocesses) and
`test_review_fixes_real.py` (real Auto MPG studies through the engine and the CLI).

- **Selected model (B-M1).** `read_export_source` says `captured` only for a current
  capture whose `selection_reference` is the selection confirmed now: the same
  configuration and the same confirmation (decision id and revision). A capture of a
  superseded selection is `stale` (limitation "not the confirmed selection"), its evidence
  is never `evaluated`, and the scientific contracts are the confirmed configuration's,
  never the old bundle's. The exporter also refuses a recipe whose `selection_reference`
  revision is not the confirmed decision's (`contract_invalid`,
  `selection_not_current_decision`). A stale capture while the final test is sealed is
  refused (`model_not_captured`, remediation: run `predictor.capture` again), since the
  capture can still be redone. Re-confirming the same value at a later revision also makes
  the capture stale (value **and** revision), so it must be captured again before the
  opening.
- **After the opening (B-M3).** A study changed after its final test opened (stale capture,
  which can no longer be redone) is exported **recipe-only** for the confirmed selection:
  `artifact_status: missing`, evidence `missing`, and the limitation "The final test
  evaluated an earlier predictor: its verdict is not inherited by the recipe of the current
  selection." A tuned model has no recipe without a fit; that export is refused with a
  remediation saying why.
- **No recipe at all.** A study without a recipe (no confirmed model choice, the constant
  baseline, a tuned model without capture, a study created before the final test) is
  refused with `capability_not_supported`, `details.reason: no_recipe`, the study's
  limitations, and a remediation the junior can follow (never "update the engine").
- **Reader refusals (E2).** A `hypotrail_runtime` `ContractError` raised by
  `read_export_source` (for example a stale `--expected-revision`) is an export refusal:
  exit code 2, `hypotrail.error/1`, the same export code when it is one (else
  `contract_invalid`), `details.contract_code`, `details.path` and `details.remediation`.
  The test double `reader_of` raises the runtime's `ContractError`, as the real reader does.
- **Evidence status.** Read from `read_export_source` (`predictor.evidence_status`);
  `evaluated` only when the study's record and the bundle's binding both say so; otherwise
  `stale` if either says so, else `unassessed` (warning
  `evidence_binding_disagrees_with_study` when the binding said more).
- **Study identity.** `study_id` is the first 16 hex digits of the SHA-256 of the canonical
  JSON of `{created, case_id, dataset_sha256, partition_seed}` from the study state, not of
  the folder path: the same study read from two folders has the same snapshot and export
  ids.
- **Records of the source (B-M2, B-M5).** `project.py materialize` reads records with a copy
  of the engine's reader (`mlkit.study.data.row_index` and `_field_splitter`; the project
  never imports the engine): split on `\n` only (not on U+2028, U+2029, form feed, vertical
  tab, NEL or a lone `\r`), the final empty line dropped, a trailing `\r` removed, fields by
  `csv.reader` on one line or, for `whitespace`, the engine's tokenizer (doubled quotes in a
  quoted field; backslashes and apostrophes are ordinary characters). A line that is not one
  record of the contract's width, a source that is not in the contract's encoding, and a
  file that splits into another number of records than the study counted
  (`development_plan.n_source_records`, from the partition's `n_rows`) are refused with
  `data_identity_mismatch`.
- **Number syntax and decimal mark.** Typed values follow what pandas (the engine's reader)
  accepts: ASCII digits, the contract's `parser.decimal` (a decimal comma is honoured, and a
  point is then refused), optional exponent and surrounding spaces; `1_000`, hexadecimal,
  non-ASCII digits and non-finite values are refused.
- **The exported commands (B-M4).** `validate`, `predict`, `materialize` and `run-local`
  always print one JSON document: a refusal (a `ProjectError`, a runtime or packager
  `ContractError`, an unreadable file, a CSV or pandas parsing error, a Hydra, OmegaConf or
  YAML error) exits with code 2; a failed check of `validate` exits with code 1 and is
  written to `outputs/validation.json` whatever failed; an unexpected exception is
  `internal_error` with code 1. `validate --offline` also compares the composed
  configuration's scientific projection with the checksummed
  `data/hypotrail/contracts/scientific-projection.json`, so editing the configuration and
  its expected identity together fails (`scientific_config_changed`).
- **README.** `predict --input` accepts a runtime parity frame (`hypotrail.parity_frame/1`)
  as well as a CSV, so the README's quickstart line works as written.
- **Other minor items.** A recipe or plan value equal to OmegaConf's `???` is refused at
  export (`contract_invalid`); a profile that is not UTF-8 is a refusal
  (`contract_invalid`, exit 2); the published project root follows the umask (it was 0700
  from the staging folder); `compare` refuses infinities at different rows or of different
  signs (`infinities_differ`).
- **Not covered.** `HYPOTRAIL_EXPORT_REAL_RUNTIME` is no longer read: since I1 the suites
  always run on the real runtime (`export_env.REAL_RUNTIME = True`).

**Round 2 fixes** (round-2 review N1 to N7 and A1-R2b; regression tests:
`framework/tests/exporters/azureml/test_review_round2.py`). They supersede the round-1
sentences above that say otherwise. *Selection (N1, N5)*: a capture is the confirmed
selection when its configuration equals the configuration confirmed now and the engine
reports the capture current (the rule the engine applies before it opens the final test);
the decision's revision is not the criterion, so confirming the same choice again (after a
hold, or by a new proposal) keeps the captured, evaluated export. `read_export_source` adds
`scientific_contracts.selection` (`capture`: `selected`, `awaiting_reconfirmation`,
`superseded`, `not_current`), and the exporter accepts an earlier `selection_reference`
revision only under that rule. While the choice is on hold the export is refused
(`contract_invalid`, `details.reason: selection_awaits_reconfirmation`) with a remediation
saying that confirming the same choice again in the chat makes it possible again; no
limitation then claims that an earlier predictor was evaluated. Another configuration
confirmed after the capture is still refused or exported recipe-only as in round 1.
*Recorded predictor (A1-R2b)*: the bundle at the recorded path must have the predictor id
the capture recorded (and its recipe and data-contract digests), and an `evaluated` binding
must name that id and the study's final result; otherwise `artifact_integrity_failed`
(`details.reason: bundle_not_recorded_predictor`). The registry records no separate payload
digest; the predictor id is the content id of the manifest, which binds it. *Study identity
(N4)*: the capture's computation context names the study by the export's path-independent
`study_id`, so new captures get new context digests and predictor ids. *Values (N2, N3)*:
`materialize` reads the values with the engine's own `pandas.read_csv` call on the whole
file (the contract's separator, encoding, decimal mark, quote character, header, only its
`na_values`, `keep_default_na=False`) and the engine's numeric conversion, then checks the
contract's physical types; row keys still come from the engine's record splitter. The
project's row files (`development.csv`, the prepared rows, the partitions) are lossless CSV
written and read with the `csv` module: a missing value is `\N`, a text starting with a
backslash gets one more, so an empty category stays an empty text. `predict --input` reads
a CSV with the dataset's reading rules (comma-separated, semicolon when the decimal mark is
a comma); a number is what pandas reads (`inf`, `Infinity`, a number wrapped in form feed),
an empty cell of a number column is missing. Two round-1 expectations changed accordingly
(`inf` and `Infinity` are accepted; a point under a decimal comma reads as the engine reads
it). *Predict input (N6)*: a malformed `hypotrail.parity_frame/1` document is a refusal
(`contract_invalid`, exit code 2). *Configuration literals (N7)*: a text of the recipe's
preprocessing that OmegaConf would interpret (`???`, `${`) is carried in the Hydra
configuration as `{hypotrail_literal_utf8_hex: ...}` and decoded by the projection, so the
project reads the exact token; a name or unit of the case equal to `???` is still refused
with a remediation the junior can follow.

**Round 3 fixes** (round-3 review B3-1 to B3-6; regression tests:
`framework/tests/exporters/azureml/test_review_round3.py`, temporary studies only). They
supersede the earlier sentences that say otherwise. *Development plan (B3-1)*: the exported
plan names exactly the rows the engine's final refit and capture train on, every
development row less the delayed-label rows, for every split kind (holdout, k-fold,
forward chaining, explicit review-v1 plan). `read_export_source` reads the explicit
evaluation plan before the `folds` blob (a forward-chaining split writes both, and its
`folds` blob names the validation rows only, so the warm-up partition was dropped: 195
rows rebuilt against 235 captured, 200 against 240 without delayed labels); a development
row no partition names is listed in an `unscored` partition (role `development`), and a
partition that names a delayed-label row or a row outside the development rows is
`contract_invalid`. `n_development_rows` and `development_keys_sha256` describe those rows.
When a captured predictor is exported, the plan's rows must be the capture's
`training_scope.membership_sha256` (the SHA-256 of the sorted row keys, one per line, or
joined by newlines): otherwise `contract_invalid`, `details.reason:
plan_rows_not_training_rows` (check `plan_rows_are_training_rows`). The technical report of
`run-local` adds the check `candidate_within_evaluated_tolerance`: a rebuilt candidate
outside the evaluated model's declared tolerance fails the report (status `failed`, the
evaluation step refuses), it never reports `passed`. *Predict input (B3-2)*: a non-finite
feature value (`inf`, `Infinity`, read as pandas reads them) is refused before any
prediction with `contract_invalid` (exit code 2) and an issue in the shape of the runtime's
input check (`path: input/<column>`, `kind: non_finite_values`, `n_rows`, `rows`); round 2
let it reach scikit-learn (`internal_error`). *Auxiliary columns (B3-3)*: an auxiliary
column whose pandas type the contract v1 cannot declare (an integer above the int64 range
read as `uint64`, booleans with a missing token read as an `object` column) is declared
`string` and listed under the data contract extension `hypotrail.auxiliary_as_text` with
the type the engine read; `materialize` reads every auxiliary `string` column as its text
(`dtype=str`, no numeric conversion), so the export and the project describe the same
values. *Configuration texts (B3-4)*: every text written into a YAML file of the project
is a double-quoted scalar whose characters outside YAML's printable set and whose line
breaks (NEL, U+2028, U+2029, a BOM) are escapes, so no YAML or OmegaConf resolver re-types
it (`1e9`, `1E-3`, `+1e5`, `yes`, `null`, a date) or folds it; the texts OmegaConf
interprets even when quoted (`???`, `${`) stay encoded literals in the preprocessing and
refused elsewhere (round 2). The generator's self-check reads the rendered configuration
through OmegaConf when it is installed. *Delayed labels (B3-5)*: the rows left out for a
delayed label are counted and explained (the term first, then the study's example in its
own clock, the engine's `delayed_labels_excluded` text) in the snapshot limitations (so the
README), the snapshot `evaluation_plan.excluded_rows` and the development plan
`excluded_rows`, and the data contract's `exclusions` (rule
`outcome_not_available_before_final`, a shorter justification with the count; a new
capture records it, a study without delayed labels keeps its contract unchanged).
*Validation patterns (B3-6)*: the profile's patterns, the Azure YAML expression and asset
patterns, the upload allowlist, the template metadata pattern, the `.amlignore` rules and
the lock lines are matched whole (`fullmatch` or `\Z`), so a value followed by a newline is
refused. *Expectation changes*: the synthetic material's capture now records the engine's
digest of its training rows (it recorded a placeholder), which the new check requires; the
rendered YAML of a project quotes its texts (bytes differ from round 2, same values).
*Not covered*: the B3-0 engine defect (a regression under review-v1 with an explicit
evaluation plan) is fixed separately; the tests of the review-v1 regression studies use a
marked workaround fixture until then. The native runtime's own input check does not test
finiteness; the exported project refuses non-finite values before calling it.

**Round 4 fixes** (round-4 review R4-A1 and R4-A2 of the library runtime; regression tests:
`framework/tests/study/libraries/test_review_round4_a.py`). *MLflow package (R4-A1)*:
`mlflow_packaging.py`, which the generated project copies byte for byte
(`src/pipeline/utils/hypotrail/mlflow_packaging.py`, a `shared` file computed from the module
at render time), now writes `MLmodel` itself (`mlmodel_bytes`: deterministic, no clock, random
id or local path, no `data`, `code` or other loader key) and verifies it by regenerating and
comparing the bytes, and admits exactly the files of `PACKAGE_FILES` plus
`artifacts/native_bundle/**` in a package; the runtime's `verify_bundle` applies the same
allowlist to an `mlflow_pyfunc` package. The export's `mlflow_package_verified` check therefore
refuses a package carrying another loader path, an extra file or folder, or an `MLmodel` key
the packager does not write, before any package code runs. `PACKAGER_VERSION` is `3`: a
package of version 2 is refused (`schema_version_unsupported`); capture again. *Recorded
package (R4-A2)*: `artifact.verify_predictor(..., recorded_packages=...)` compares the bundle's
`optional_packages` with the packages the capture recorded, which `read_export_source` states
in its extension `hypotrail.packages` (`artifact.recorded_packages(source)`; a source that
states only `predictor.packages` gives the formats without ids, and a source that states
neither, such as the synthetic test double, checks nothing). A recorded package missing, a
package the capture did not record, or another `artifact_id` refuses the export with
`artifact_integrity_failed`, `details.reason: package_not_recorded` (with `missing`,
`unrecorded`, `changed`, `recorded` and `held`), path `predictor.packages`, remediation:
restore the captured bundle from a trusted copy or capture again before the final test is
opened; it is checked before the MLflow package is verified, so a re-made package is never
loaded. The predictor record also lists `packages` (`[{format, artifact_id}]`). The generated
project's bytes are unchanged apart from the copied `mlflow_packaging.py` and, through the
captured bundle, the package files.

**Round 4 fixes** (round-4 review R4-B1 to R4-B3; regression tests:
`framework/tests/exporters/azureml/test_review_round4.py`, synthetic material and temporary
folders only). They supersede the earlier sentences that say otherwise. *YAML values
(R4-B1)*: round 3 quoted the texts of `src/conf` only; the Azure YAML still received
`experiment_name`, `data_asset.name`, `environment.name`, the compute, the asset
references and the service connection raw, so a loader re-typed `2026`, `True`, `null` or
`1.10` (the job input still named the text) and an environment named `null` failed the
export with `template_layout_mismatch`. Every value the generator writes into a YAML file
of the project (Azure YAML, `.ci/`, `environment.yml`, `src/conf`, comments included) is
now one whole double-quoted scalar: a reference such as `azureml:<name>:<version>` or a
component name is composed by the generator and quoted as one value, and the command lines
carry the fixed `mlflow_tracking=false`. A YAML template may no longer use the raw
`@@text:` marker (the generator refuses it, `template_layout_mismatch`), and
`src/conf/azure/target.yaml` is written with every text quoted (`safe_dump` left `1e9`
plain, which OmegaConf reads as a float). A profile name that is not an Azure name (`~`,
an empty text) is still refused on its field with `contract_invalid`. *Example code
(R4-B2)*: the check for code of the template's example (shuttles, companies, reviews)
reads the template's own files, before their markers are replaced, and the shared
generator modules (`Template.example_code`, run when the template is loaded and by
`check_tree`); it never reads a rendered value, so a case id, title or name with those
words exports. Generated documents (contracts, notebook, lock) and the copied model are the
study's, not the template's, and are not matched. *Run-local paths (R4-B3)*: each run path
is passed to the steps as one single-quoted Hydra value (`hydra_quoted`: a quote is `\'`,
the backslashes before a quote or the closing quote are doubled, `${` is escaped for
OmegaConf), so a folder named with `(`, `)`, `,`, `=`, quotes, `$`, brackets, braces,
spaces or non-ASCII letters runs; a relative `--run-dir` is read from the caller's folder
once. A failed step's refusal is relayed in the document (`error`: code, path, message,
remediation, details, beside `failed_step`, exit code 2); a step that stops without a
refusal is `step_failed` with its exit code and the tail of its output. *Not covered*:
Hydra creates its run folder from `hydra.run.dir` resolved once and resolves the absolute
copy `hydra.runtime.output_dir` again, so no escape keeps a `${` literal in both: a run
folder whose path holds `${` (a `--run-dir`, or the project folder of the default one) is
refused before any step runs (`invalid_arguments`). `pyproject.toml` (TOML, not YAML)
still receives the project name (a slug of the case id) and the description (with the
study id, 16 hexadecimal digits) raw inside its quotes.

**Round 5 fixes** (round-5 review R5-A1 to R5-A3 of the library runtime, described in the
library handoff, `LIBRARIES-V1.md`, round 5; regression tests:
`framework/tests/study/libraries/test_review_round5_a.py` and, for the generated project,
`framework/tests/exporters/azureml/test_review_round5.py`). *MLflow package (R5-A1)*: the
copied `mlflow_packaging.py` now writes package environments that install the bundle's own
runtime wheel by its path inside the package
(`./artifacts/native_bundle/runtime/hypotrail_runtime-<version>-py3-none-any.whl`, never
`hypotrail-runtime==<version>` from an index), a wrapper that refuses to serve unless the
installed `hypotrail_runtime` holds exactly the files of that wheel and reproduces the
bundle's parity rows, and `PACKAGER_VERSION` `4`: the export's `mlflow_package_verified`
check refuses a version-3 package (`schema_version_unsupported`, capture again). *Installed
runtime*: `hypotrail_runtime.load_predictor` compares the installed runtime with the
bundle's wheel, so the generated project's `predict` and `validate` (`evaluated_model_parity`)
refuse another runtime of the same version on the project's path with
`environment_unqualified`, `details.reason: runtime_not_bound`, the differing files and the
remediation `pip install <bundle>/runtime/<wheel>`, and predict nothing; the project's own
environment (`aml-environment.yml`) already installs that wheel, so a project run as
generated is unaffected. The export does not deploy the MLflow package; a deployment target
that builds its image from the package's `conda.yaml` without the model folder (Azure ML's
no-code MLflow deployment, for example) cannot resolve the local wheel path and needs an
environment that installs the wheel (not verified against Azure here). *Evidence (R5-A2)*: a
bundle's `evidence/` holds `evidence/binding-<n>.json` bindings of its predictor only, and
the package's embedded bundle no `evidence/` folder at all, so the export refuses either
otherwise (`artifact_integrity_failed`). The generated project's bytes are unchanged apart
from the copied `mlflow_packaging.py` and, through the captured bundle, the package files.

**Round 9 fixes** (round-9 review R9AB-1, R9AB-3, R9AB-5 and R9AB-6 of the export; R9AB-2
and R9AB-4 concern the library runtime and are described in `LIBRARIES-V1.md`, round 9;
regression tests: `framework/tests/exporters/azureml/test_review_round9.py`, synthetic
material and temporary folders only, and `framework/tests/study/libraries/test_review_round9_a.py`
for the packager). *Contract identities (R9AB-1)*: `data/hypotrail/SHA256SUMS` is written
with the data folder, so it shows that nothing changed by accident, not that a file is the
study's: a development plan given the final-test rows (its digests recomputed and its
checksum line rewritten) passed `validate`, `materialize` and `run-local`, which then fitted
the candidate on final-test rows, and an evaluated model copied from another bundle passed
`validate`, `evaluated_model_parity` included. The project now binds every contract it reads
to the configuration that travels with the code (`contracts.load`, the first call of every
step): the plan's partition digests, its `keys_sha256` and its development digest and row
count are recomputed from its row keys, and `keys_sha256` and `protocol_id` must be the
configuration's `components.data_splitting` values (part of the scientific projection); its
roles, final-test summary and excluded rows must be the snapshot's evaluation plan; the
snapshot must hash canonically to `hypotrail.snapshot_id` and name the configuration's study,
recipe, data contract and plan; `models/evaluated` must hold a bundle exactly when the
snapshot names a predictor, and that bundle must be it (the id `verify_bundle` recomputes
from the content, in the training and evaluation steps, `validate` and the default
`predict`). Every mismatch is `artifact_integrity_failed`, its `path` naming the contract
(`contracts/development-plan.json`, `contracts/deployment-snapshot.json` or
`models/evaluated`) and `details` the expected and found values; an override of
`hypotrail.snapshot_id`, `hypotrail.study_id` or `hypotrail.study_revision` is
`scientific_config_changed`. `validate` gains the check `contract_identities` (the same
checks, `not_run` without Hydra), `evaluated_model_parity` and
`evaluated_model_mlflow_package` compare the evaluated model with the snapshot, and
`materialize` checks the plan against the checksummed scientific projection and the snapshot
before it extracts a row. No refusal code was added. *Limit*: the anchor is the
configuration in `src/conf` (code, under version control, uploaded with the job); a change
of both the data folder and `src/conf` (the projection's expected digest, the plan digest,
the snapshot id) is a different export, which only the study's export record (its
`export_id` and `snapshot_id`) can tell apart. *Packaging from a uv project (R9AB-3)*: MLflow
3.17 copies `pyproject.toml`, `uv.lock` and `.python-version` from the working directory into
a package it saves when it finds a uv project there, and the package allowlist refused them,
so the training step failed (`backend_failed`) once the project folder had a `uv.lock`. The
copied `mlflow_packaging.py` passes an empty folder as `uv_project_path`, so nothing is
copied and the package holds the same bytes from any working directory; the wrapper and
`PACKAGER_VERSION` (`4`) are unchanged. *Step refusals (R9AB-5)*: the four steps' `main.py`
caught `ProjectError` only, so a refusal of `hypotrail_runtime` (`ContractError`) or of the
packager (`PackagingError`) stopped the step without a refusal line and `run-local` reported
`step_failed`. Each step now prints `errors.from_exception(error)` as its JSON refusal (exit
code 2), so `run-local` relays the runtime's code, path and remediation; an exception that is
no refusal is still raised (exit code 1, `step_failed` with the output's tail). *Hydra keys
(R9AB-6)*: a column named `_target_` exported, then the project's own `validate` refused its
configuration (`hydra_config_frozen`, a `_target_` key of `feature_types`). The export refuses
a configuration key named `_target_` as it refuses `${`, `@@` and `???` (`contract_invalid`,
path `scientific_projection.feature_types._target_`). Hydra's other instantiation keys
(`_args_`, `_recursive_`, `_convert_`, `_partial_`) and `_self_`, `defaults`, `hydra`,
`override` were exported as column names and validated: they compose and freeze as plain
keys and are not refused. Of the generated project's files, only `contracts.py`, `steps.py`,
`project.py`, the four step `main.py` files and the copied `mlflow_packaging.py` changed.

## R19: binary logistic

Owner request R19 ([acceptance run of 26 October 2026](../acceptance/runs/copilot-companion-2026-10-26.md)):
the discovery case (Hotel booking, binary) and Bank Marketing could not reach the export,
whose support matrix was regression `linear` only. The template now qualifies `{"task":
"binary", "family": "logistic", "output_kind": "binary_score"}` locally, end to end, with the
regression guarantees. Regression tests:
`framework/tests/exporters/azureml/test_binary_logistic.py` (a temporary synthetic binary
study through the engine's real commands; synthetic test words; temporary folders only).

- **Which models are `logistic`.** The engine writes every binary candidate and every
  variant that is not another family as `logistic` (`mlkit.contracts.recipe._family`): the
  candidate, a stronger or weaker penalty and a tuned penalty (parameter `C`, the tuning
  recorded in `extensions["hypotrail.tuning"]`), and a dropped feature group (fewer
  features). They are all supported. A variant of another family (`ebm`, `hgb`) is not:
  the runtime cannot capture it, `read_export_source` names it
  (`scientific_contracts.unsupported_family`, limitation "No recipe: the <family> family is
  not qualified ...") before the tuned-value reason that used to suggest a capture, and the
  export refuses with `capability_not_supported`, `details.reason: family_not_supported`,
  `details.family`, `details.supported` and path `model_recipe.family`; nothing is written
  and the logistic candidate is never offered instead.
- **Runtime.** Nothing changed: `fit_predictor` encodes the target with the recorded
  positive label (1 for that label, numerically for a numeric label and column, as text
  otherwise), `Predictor.predict` returns `predict_proba` of that class as `score`
  (`binary_score`), and the MLflow pyfunc returns the same column. `PACKAGER_VERSION` stays
  `4`; no packaged byte changed.
- **The four steps.** `data_preparation` adds `target_encoding` to its validation report
  (target, positive label, the rule, positive and negative counts, by the runtime's own
  encoding function) and refuses development rows of one class
  (`data_identity_mismatch`); `data_splitting` is unchanged; `training` fits the rebuilt
  candidate with the recorded recipe (`C`, solver, tolerance, seed) and records
  `output_kind` and the decision rule in `hypotrail-run.json`; `evaluation` adds the check
  `candidate_scores_are_probabilities` (every score of the parity rows finite and in
  [0, 1]) to the reload, MLflow and evaluated-tolerance parity checks (all on scores), and
  reports `output_kind` and the decision rule. Like the regression evaluation it computes
  no metric: the parity rows carry no label, and a ROC AUC, Brier score or log loss on the
  candidate's own training rows would not be generalisation evidence;
  `generalisation_metrics` stays null and the verdict `not_inherited`.
- **The decision rule.** The rule the study adopted (the confirmed policy:
  `threshold:t`, `capacity:k` or `share:p`, possibly for a variant, `capacity:40@fit.variant`)
  is carried as metadata only: the snapshot's `decision_rule` (`rule`, `kind`, `amount`,
  `model`, `policy_value`, `score_column`, `positive_label`, `applied_in_model_output:
  false`, `needs_batch_ranking`, `meaning`), bound by `hypotrail.snapshot_id` like the rest
  of the snapshot (R9AB-1); `readiness.json` `decision_rule`; the README ("What the study
  selected" and Limits) and `docs/pages/deployment.md`; `predict`'s document and the
  technical report. It is never applied inside the model, `predict` or the MLflow package:
  a threshold is a comparison the consumer makes, and a capacity or a share selects the
  highest scores of a whole batch of rows, which a row-wise endpoint cannot do. A binary
  recipe without a parsable adopted rule is refused (`contract_invalid`,
  `details.reason: decision_rule_missing`). A regression snapshot has no `decision_rule`
  key, so its bytes and id are unchanged; its README gains an "Output" line and "Decision
  rule: none".
- **Unchanged guarantees.** The plan, snapshot and evaluated-model bindings of round 9, the
  recorded package ids, the YAML quoting and the Hydra key rules apply as for regression;
  the project's own pytest and the team's ruff rules pass on a binary export.
- **Not covered.** Azure is not qualified (no job, no endpoint, no Azure call). The Hotel
  and Bank cases themselves were not run through the export in this change (the test
  study is synthetic, with the same task, family, rule kinds and capture profile). Ruff
  writes `.ruff_cache/` in the project folder unless run with `--no-cache`, and `.amlignore`
  does not exclude it, so a lint before the project's tests makes
  `test_code_upload_holds_only_code` fail (pre-existing, not changed here).
