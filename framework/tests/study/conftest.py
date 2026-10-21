"""Shared fixtures of the study tests: a synthetic case and a fresh study in ``tmp_path``.

Nothing here touches ``use-cases/`` or an existing study.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from mlkit.study import case as c, state as st, store as sto

TESTS = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('synthetic_make_case_for_conftest',
                                               TESTS / 'fixtures/synthetic/make_case.py')
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
make_case = _module.make_case


@pytest.fixture(scope='module')
def synthetic_case_dir(tmp_path_factory) -> Path:
    return make_case(tmp_path_factory.mktemp('case'), n_rows=300)['case'].parent


@pytest.fixture
def new_study(tmp_path, synthetic_case_dir) -> sto.StudyStore:
    store = sto.StudyStore(tmp_path / 'study')
    store.create(st.initial_state(c.load_case(synthetic_case_dir)))
    return store
