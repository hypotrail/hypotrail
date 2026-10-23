"""Import of the Hypotrail runtime (``hypotrail_runtime``) and of MLflow, with clear errors.

The runtime is the distribution that carries the fitted predictor's code (preprocessing,
estimator, typed predictions). It is installed from the wheel shipped in
``aml/pipelines/training/runtime/`` when the study captured a model. A missing runtime is
reported as a refusal (``optional_dependency_missing``), never replaced by another code.
"""

from __future__ import annotations

import importlib
import importlib.util
from typing import TYPE_CHECKING

from .errors import ProjectError

if TYPE_CHECKING:
    from types import ModuleType


def available(name: str) -> bool:
    """Tell whether a module can be imported, without importing it."""
    return importlib.util.find_spec(name) is not None


def runtime() -> ModuleType:
    """Return the ``hypotrail_runtime`` module or refuse."""
    try:
        return importlib.import_module("hypotrail_runtime")
    except ImportError as error:
        raise ProjectError(
            "optional_dependency_missing",
            "hypotrail_runtime is not installed, so no model can be loaded or fitted.",
            path="hypotrail_runtime",
            remediation="pip install aml/pipelines/training/runtime/*.whl "
            "(present only when the study captured its model).",
        ) from error


def mlflow() -> ModuleType:
    """Return the ``mlflow`` module or refuse."""
    try:
        return importlib.import_module("mlflow")
    except ImportError as error:
        raise ProjectError(
            "optional_dependency_missing",
            "MLflow is not installed in this environment.",
            path="mlflow",
            remediation="Create the environment from environment.yml.",
        ) from error
