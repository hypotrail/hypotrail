"""Shared fixtures of the study tests: a synthetic case and a fresh study in ``tmp_path``.

Nothing here touches ``use-cases/`` or an existing study.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

from mlkit.study import case as c, state as st, store as sto

TESTS = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('synthetic_make_case_for_conftest',
                                               TESTS / 'fixtures/synthetic/make_case.py')
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
make_case = _module.make_case

# One step-1 sample per case and dataset in every run (partition.SAMPLE_STAMP_ENV): the data
# card's example rows no longer change with each study's creation stamp, so a test picking a
# figure "no value of the study holds" cannot fail on the run where a drawn row holds it. Set
# in the environment, so the CLI processes the tests start inherit it. A test of the seed
# itself removes it (``monkeypatch.delenv``).
os.environ.setdefault('HYPOTRAIL_TEST_SAMPLE_STAMP', '2026-01-01T00:00:00+00:00')


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
    # ``HYPOTRAIL_SHARD=k/n``: the k-th of n CI shards (ci_shards.py), after any selection.
    from ci_shards import selected as shard_selected
    wanted = _selection()
    shard = shard_selected(i.nodeid.replace('\\', '/') for i in items)
    if wanted is None and shard is None:
        return

    def kept(nodeid: str) -> bool:
        nodeid = nodeid.replace('\\', '/')
        if shard is not None and nodeid not in shard:
            return False
        if wanted is None:
            return True
        base = nodeid.split('[', 1)[0]
        return nodeid in wanted or base in wanted or base.split('::', 1)[0] in wanted
    selected = [i for i in items if kept(i.nodeid)]
    deselected = [i for i in items if not kept(i.nodeid)]
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected


@pytest.hookimpl(optionalhook=True)
def pytest_xdist_make_scheduler(config, log):
    # ``--dist loadfile`` keeps a file on one worker, except the long files of ci_shards.SPLIT.
    if config.getvalue('dist') != 'loadfile':
        return None
    from ci_shards import scheduler
    return scheduler(config, log)
