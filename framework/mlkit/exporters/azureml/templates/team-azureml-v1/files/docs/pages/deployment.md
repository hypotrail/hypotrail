# Deployment

This page explains what this folder is, what has been checked, and what remains a separate
step. A generated folder is not a cloud run, and a cloud run is not a deployed endpoint.

## Statuses

| Dimension | Values | Now |
|---|---|---|
| Configuration | draft / configured | `@@text:configuration_status@@` |
| Evaluated model | missing / captured / packaged | `@@text:artifact_status@@` |
| Local validation | not_run / passed / failed | `not_run` until `validate` |
| Azure preflight | not_run / passed / failed | `not_run` |
| Azure job | not_submitted / submitted / completed / failed / canceled | `not_submitted` |
| Registered model | not_registered / registered | `not_registered` |
| Scientific verdict | the study's own | @@text:verdict_sentence@@ |
| Production authorisation | outside_scope / approval_recorded | `outside_scope` |

@@text:missing_fields_sentence@@

## Workshop path (10 to 15 minutes, without the Azure build time)

1. Open `src/conf/config.yaml` and `src/conf/components/training/default.yaml`: the selected
   recipe, frozen by `hypotrail.expected_scientific_sha256`.
2. Open `aml/pipelines/training/pipeline-job.yml`: the destination (compute, data asset and
   environment by explicit version, never `latest`).
3. Run `python -m src.pipeline.utils.project validate --offline`: checksums, contract copies,
   Hydra freeze, Azure YAML graph, code upload content, credentials, model parity.
4. Run `python -m src.pipeline.utils.project predict --parity --output outputs/predictions.json`:
   the evaluated model predicts the parity rows without the target. @@text:predict_sentence@@
   Output: @@text:output_sentence@@ A decision rule the study adopted is not applied here.
5. Azure, optional and explained separately: `preflight` (read-only) then `submit --execute`
   (creates the assets, submits one pipeline job). The trainer may show a recipe run that is
   labelled as such. The job's model is a `rebuilt_candidate`: a new object.

## What each command proves

- `validate` passing: this folder is internally consistent on this machine. It is not an
  Azure qualification: a valid YAML schema is not a successful job, and a successful job is
  not an available endpoint.
- `preflight --execute` passing: the named resources could be read now with your identity.
- `submit --execute`: a job id exists; its result is observed only with `--wait` or later.

## Replay modes

- `rebuild_final_candidate` (available): fits the recipe on all @@text:n_development_rows@@
  development rows; technical checks only; no generalisation metric from training rows.
- `development_evaluation` (not in this version): would replay the recorded folds.

The final test of the study is not in this folder and no command reads it.

## Endpoints

No endpoint is defined here. A batch or online endpoint is a separate option, with its own
contract (request format, identity, compute, traffic, cleaning).
