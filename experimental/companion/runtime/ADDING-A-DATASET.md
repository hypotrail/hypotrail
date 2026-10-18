# Adding a dataset to the experimental companion

This feature is paused. This guide describes its current configuration-assisted onboarding, not the future junior framework workflow.

## Choose the supported task

A new dataset of an existing task type needs a case directory and adapter. A new task type needs a journey contract and possibly a new component. Unknown business meaning must be `unknown` or `proposed`; dependent activities stay blocked until human confirmation.

## Inspect and clarify

Inspect format, columns, apparent types, missing and special values, target candidates, time, identifiers, and groups without a model search. A name does not establish prediction-time availability. Ask only about facts that change the next step: target, use, prediction time, observation unit, repetition, and chronology.

## Define the project

Create `use-cases/<name>/project.json`, exposed through the runtime `projects/` link. Schema `hypotrail.project/1` requires an ID, title, language, problem type, journey reference, dataset provenance and hash, facts, variables, constraints, limitations, guidance, and content for every journey activity.

Required facts include `target`, `observation_unit`, `intended_use`, `decision`, and `prediction_time`. Record unknown values explicitly, with a source and relevant `dataset.content` or `dataset.schema` dependencies.

Activity blocks use validated components such as `objective`, `text`, `examples_table`, `distribution`, `variable_dictionary`, `clarifications`, `data_explorer`, `choice_question`, `numeric_selection`, `model_comparison`, `error_view`, `limits`, and `choice_summary`.

Reference calculated values with placeholders such as `{{r:result.metric}}`, `{{p:protocol.train}}`, `{{d:rows}}`, `{{x:display_path}}`, or `{{g:seed}}`. Unknown references are errors. Calculation-linked choices use `compute: precomputed` with an available result per option, or `not_available`. The companion never invents or starts the missing calculation.

## Prepare evidence

An explicit adapter checks source hashes, uses a justified protocol, fits preprocessing on training data, and records a simple reference plus model results. Write `results.json` under schema `hypotrail.results/1`: project and dataset references, protocols and scope justification, metric definitions with units, results with configuration and provenance, display data, and limitations.

Use case-specific metric names. Regression must not inherit classification alert language. Detailed EDA uses the authorized training partition. Record prior exposure rather than presenting explored observations as independent evidence.

## Register and validate

Add the project to `use-cases/registry.json`. Run `python bridge.py validate --project ID` and `python bridge.py status --project ID --db /tmp/hypotrail-example.sqlite`. Validation rejects unknown schemas, missing targets or units, unsupported components, wrong-dataset results, unsafe paths, and command keys.

Rebuild explicitly with `python ../vscode-extension/scripts/package.py` if a package is required. Each project has a separate session. Changing data invalidates dependent results and confirmations without erasing history; changing a title does not invalidate a calculation.

Current coverage is binary selection and regression comparison. There is no universal automatic business interpretation, semantic data-change analysis, or model execution from the UI.
