"""Environment flags of the Azure ML export tests (private to the tests)."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

# Since the integration (I1) the suites run against the installed hypotrail_runtime of
# workstream A; the private test double was removed.
REAL_RUNTIME = True
HAS_MLFLOW = importlib.util.find_spec('mlflow') is not None
HAS_HYDRA = importlib.util.find_spec('hydra') is not None
needs_mlflow = pytest.mark.skipif(not HAS_MLFLOW, reason='MLflow is not installed (azureml group)')
needs_hydra = pytest.mark.skipif(not HAS_HYDRA, reason='Hydra is not installed (azureml group)')


def project_env() -> dict:
    """The environment of a subprocess that runs an exported project: the installed runtime,
    no PYTHONPATH from the repository, no MLflow hint."""
    env = {k: v for k, v in os.environ.items() if k != 'PYTHONPATH'}
    env['MLFLOW_DISABLE_AGENT_HINT'] = '1'
    env['PYTHONWARNINGS'] = 'ignore'
    return env
