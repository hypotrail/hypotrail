"""Fixtures of the Azure ML export tests.

``hypotrail_runtime`` here is the PRIVATE TEST DOUBLE of ``fixtures/fake_runtime`` (it is
put on ``sys.path`` by these fixtures only); the real runtime of chantier A replaces it in
the deferred integration suite. MLflow and Hydra come from the ``azureml`` dependency
group; without them the tests that need them are skipped with that reason.
"""
from __future__ import annotations

import importlib
import importlib.util
import os
import sys
import warnings
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'fixtures'))
os.environ.setdefault('MLFLOW_DISABLE_AGENT_HINT', '1')

from export_env import FAKE_RUNTIME, HAS_MLFLOW, REAL_RUNTIME  # noqa: E402


@pytest.fixture(scope='session')
def runtime():
    if REAL_RUNTIME:
        return importlib.import_module('hypotrail_runtime')
    if str(FAKE_RUNTIME) not in sys.path:
        sys.path.insert(0, str(FAKE_RUNTIME))
    warnings.filterwarnings('ignore', module='mlflow')
    return importlib.import_module('hypotrail_runtime')


@pytest.fixture(scope='session')
def material(tmp_path_factory, runtime):
    """A source file, its contract, and a captured bundle: packaged (when MLflow is
    installed) and bound to an evaluated final result."""
    import azureml_study as fx
    folder = tmp_path_factory.mktemp('material')
    source = fx.write_source(folder)
    contract = fx.data_contract(source)
    packager = None
    if HAS_MLFLOW:
        from mlkit.integrations.mlflow_packaging import ArtifactPackager
        packager = ArtifactPackager(runtime)
    bundle = fx.capture(runtime, folder / 'artifacts', source, contract, fx.recipe(),
                        packager=packager)
    fx.bind_evidence(bundle)
    native = fx.capture(runtime, folder / 'native-only', source, contract, fx.recipe())
    return {'folder': folder, 'source': source, 'contract': contract, 'bundle': bundle,
            'native_bundle': native}


@pytest.fixture
def export(tmp_path, material):
    """``export(**changes)`` runs one export of the synthetic study into ``tmp_path``."""
    import azureml_study as fx

    from mlkit.exporters.azureml import export_azureml

    def run(*, name='export', bundle='bundle', profile=True, profile_changes=None,
            source_changes=None, plan=False, require_configured=False, reader=None,
            expected_revision=fx.REVISION, out=None):
        bundle_dir = material[bundle] if bundle else None
        doc = fx.export_source(material['folder'], bundle_dir=bundle_dir,
                               contract=material['contract'], source=material['source'])
        for key, value in (source_changes or {}).items():
            doc[key] = value
        profile_path = fx.profile(tmp_path, **(profile_changes or {})) if profile else None
        target = out if out is not None else (tmp_path / name)
        payload, code = export_azureml(tmp_path / 'study', expected_revision=expected_revision,
                                       out=None if plan else target, profile_path=profile_path,
                                       plan=plan, require_configured=require_configured,
                                       reader=reader or fx.reader_of(doc))
        return payload, code, target
    return run

