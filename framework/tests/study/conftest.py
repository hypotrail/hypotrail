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


# --- a named selection of tests ----------------------------------------------------------------
# ``HYPOTRAIL_TEST_SELECTION=FILE`` (or a committed ``tests/study/ci-selection.txt``, for a
# temporary CI run on one platform; never merged) keeps only the tests the file lists, one
# node id per line relative to ``framework/`` (``tests/study/test_x.py::test_y``; a bare id
# also keeps its parametrizations, a file keeps all its tests). ``#`` starts a comment.

_SELECTION = Path(__file__).with_name('ci-selection.txt')


def _selection() -> set[str] | None:
    import os
    named = os.environ.get('HYPOTRAIL_TEST_SELECTION')
    path = Path(named) if named is not None else _SELECTION
    if not named and named is not None or not path.is_file():
        return None                 # HYPOTRAIL_TEST_SELECTION= (empty) runs everything
    lines = (line.split('#', 1)[0].strip() for line in path.read_text(encoding='utf-8')
             .splitlines())
    return {line.replace('\\', '/') for line in lines if line}


def pytest_collection_modifyitems(config, items):
    wanted = _selection()
    if wanted is None:
        return

    def kept(nodeid: str) -> bool:
        base = nodeid.split('[', 1)[0]
        return nodeid in wanted or base in wanted or base.split('::', 1)[0] in wanted
    selected = [i for i in items if kept(i.nodeid)]
    deselected = [i for i in items if not kept(i.nodeid)]
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected
