"""Environment flags of the Azure ML export tests (private to the tests)."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

FAKE_RUNTIME = Path(__file__).resolve().parent / 'fake_runtime'
# Deferred integration (after the merge with chantier A): HYPOTRAIL_EXPORT_REAL_RUNTIME=1
# runs the same suites against the installed hypotrail_runtime instead of the test double.
REAL_RUNTIME = os.environ.get('HYPOTRAIL_EXPORT_REAL_RUNTIME') == '1'
HAS_MLFLOW = importlib.util.find_spec('mlflow') is not None
HAS_HYDRA = importlib.util.find_spec('hydra') is not None
needs_mlflow = pytest.mark.skipif(not HAS_MLFLOW, reason='MLflow is not installed (azureml group)')
needs_hydra = pytest.mark.skipif(not HAS_HYDRA, reason='Hydra is not installed (azureml group)')


def project_env() -> dict:
    """The environment of a subprocess that runs an exported project: the test double of
    the runtime on PYTHONPATH (or the real runtime after the merge), no MLflow hint."""
    env = {k: v for k, v in os.environ.items() if k != 'PYTHONPATH'}
    if not REAL_RUNTIME:
        env['PYTHONPATH'] = str(FAKE_RUNTIME)
    env['MLFLOW_DISABLE_AGENT_HINT'] = '1'
    env['PYTHONWARNINGS'] = 'ignore'
    return env
