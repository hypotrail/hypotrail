"""Hypotrail predictor runtime v1 (workstream A): shared contracts and complete predictor.

Public API (CONTRAT-COMMUN-v1 §6)::

    validate_recipe(document) -> ModelRecipe
    validate_data_contract(document) -> DataContract
    verify_bundle(bundle_dir) -> BundleDescriptor
    load_predictor(bundle_dir, *, trusted_roots) -> Predictor
    Predictor.predict(raw_features) -> PredictionBatch
    fit_predictor(recipe, data_contract, training_frame, training_scope) -> FittedPredictor
    capture_predictor(fitted, context, parity_features, destination, packager=None)
        -> BundleDescriptor

This package imports no study engine, Marimo, Azure, Hydra or MLflow module.
"""
from __future__ import annotations

__version__ = '1.0.0'
DISTRIBUTION = 'hypotrail-runtime'
RUNTIME_API_VERSION = '1.0'
METHOD_CONTRACT_VERSION = 'hypotrail.method/1'
REQUIRES_PYTHON = '>=3.13,<3.14'
# Kept equal to framework/runtime/pyproject.toml (tested).
DEPENDENCIES = ('numpy>=1.26', 'pandas>=2.1', 'scikit-learn>=1.5', 'pydantic>=2.7,<3')

from .contracts import (ComputationContext, DataContract, DiagnosticResult,  # noqa: E402
                        EvidenceBinding, ModelRecipe, PackageDescriptor, ParityResult,
                        PredictorArtifact, PredictorBundle, UncertaintyResult, parse,
                        validate_data_contract, validate_recipe)
from .errors import ContractError  # noqa: E402
from .predictor import (BundleDescriptor, FittedPredictor, PredictionBatch,  # noqa: E402
                        Predictor, capture_predictor, check_parity, fit_predictor,
                        load_predictor, verify_bundle, write_evidence_binding)

__all__ = [
    'ComputationContext', 'DataContract', 'DiagnosticResult', 'EvidenceBinding',
    'ModelRecipe', 'PackageDescriptor', 'ParityResult', 'PredictorArtifact',
    'PredictorBundle', 'UncertaintyResult', 'parse', 'validate_data_contract',
    'validate_recipe', 'ContractError', 'BundleDescriptor', 'FittedPredictor',
    'PredictionBatch', 'Predictor', 'capture_predictor', 'check_parity', 'fit_predictor',
    'load_predictor', 'verify_bundle', 'write_evidence_binding',
]
