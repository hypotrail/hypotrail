# Code documentation

- `src/pipeline/<step>/main.py`: Hydra entry point of each step; it freezes the
  configuration, then calls `src/pipeline/utils/hypotrail/steps.py`.
- `src/pipeline/utils/hypotrail/config.py`: resolution, closed key set, scientific
  projection and its SHA-256 (`@@text:expected_scientific_sha256@@`).
- `src/pipeline/utils/hypotrail/contracts.py`: checksums, contract copies, typed rows.
- `src/pipeline/utils/hypotrail/mlflow_packaging.py`: the MLflow pyfunc packager (a copy of
  the generator's, verified by hash) injected when a candidate is captured.
- `src/pipeline/utils/project.py`: `validate`, `predict`, `materialize`, `run-local`,
  `preflight`, `submit`.
- `hypotrail_runtime` (installed from `aml/pipelines/training/runtime/`): the predictor's
  preprocessing, estimator and typed outputs; this project never re-implements them.
