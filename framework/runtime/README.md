# hypotrail-runtime

The minimal distribution of the Hypotrail predictor (workstream A of the library
integration v1, `docs/specs/integration-libraries/`). It holds:

- the shared v1 contracts (`hypotrail.model_recipe/1`, `hypotrail.data_contract/1`,
  `hypotrail.computation_context/1`, `hypotrail.predictor_artifact/1`,
  `hypotrail.predictor_bundle/1`, `hypotrail.evidence_binding/1`,
  `hypotrail.diagnostic_result/1`, `hypotrail.uncertainty_result/1`,
  `hypotrail.package_descriptor/1`, `hypotrail.parity_result/1`) as strict Pydantic models,
  their canonical serialisation and generated JSON schemas (`hypotrail_runtime/schemas/`);
- the complete predictor: the engine's preparation (category text, special-value
  indicators, missing indicators, rare categories, caps, signed log) learnt on the
  training rows only, then imputation, scaling, one-hot encoding and the estimator, in one
  scikit-learn pipeline;
- `fit_predictor`, `capture_predictor`, `verify_bundle`, `load_predictor` and
  `Predictor.predict`.

It imports no study engine, Marimo, Azure or MLflow module. Install it alone from its
wheel; see `docs/handoff/LIBRARIES-V1.md`.
