"""Engine side of the shared contracts v1 (library integration, workstream A).

The models, canonical serialisation, generated JSON schemas and the complete predictor are
in the separately installable runtime (:mod:`hypotrail_runtime`). This package holds what
needs the study engine:

* :mod:`mlkit.contracts.recipe`: a fit's recipe and the case's data contract;
* :mod:`mlkit.contracts.context`: computation contexts and their identity;
* :mod:`mlkit.contracts.capture`: the ``predictor.capture`` activity's computation;
* :mod:`mlkit.contracts.export_source`: :func:`read_export_source`, the read-only view of a
  study that workstream B composes its deployment snapshot from;
* :mod:`mlkit.contracts.errors`: the mapping of contract errors to engine refusals.
"""
from hypotrail_runtime.contracts import (ComputationContext, DataContract,  # noqa: F401
                                         DiagnosticResult, EvidenceBinding, ModelRecipe,
                                         PredictorArtifact, PredictorBundle, UncertaintyResult)
from hypotrail_runtime.errors import CODES, ContractError  # noqa: F401
