# Handoff: Azure ML export v1 (chantier B)

Status on 23 October 2026: **B1 and B2 implemented and tested locally on a private test
double of chantier A; B3 (the real bundle and runtime of A) deferred to the merge; Azure
not qualified** (no job, no endpoint, no Azure call was made).

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
| Family id of the qualified model | `linear` (task `regression`, output `regression_point`) | `template.json` `capabilities` |
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
`unassessed` / `stale` (from the bundle's binding, never inferred); local validation,
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

Results: see the final section of this file once the full gate has run (pending at this commit).

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

- Support matrix: regression `linear` only (with output `regression_point`); everything
  else is refused with `capability_not_supported`, never substituted. Binary
  classification, other families and calibrated (MAPIE) capabilities are refused.
- Replay mode `rebuild_final_candidate` only; `development_evaluation` is refused.
- Materialisation supports positional row keys only (`source_position`).
- `submit --execute` reuses an existing asset of the same name and version on an "already
  exists" answer without being able to compare its content through the CLI (recorded as
  `reused_existing`); a content mismatch is not detected there.
- The base image must provide Python 3.13; only an Azure recipe run qualifies it.
- The exported project's `validate` reads the model with the runtime's pickle-based
  native format: trusted local artefacts only (a hash does not make a third-party pickle
  safe).
