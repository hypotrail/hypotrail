"""Exposure is never lost when a process dies around a recovery or a failure (finding M2).

An execution's planned exposure (the rows it may have read) used to be recorded after
the ``run.recover`` or ``run.fail`` commit. A process killed between the two left the
execution closed with no exposure: rows read were treated as unseen. The exposure is now
recorded before the commit, idempotently (an execution's exposure is recorded once).
Processes die for real (``os._exit`` through ``HYPOTRAIL_TEST_HOOKS=1``), as in the
reviewer's ``t6.py``. Studies live in ``tmp_path``.
"""
from __future__ import annotations

import pytest

from mlkit.study import executions as ex

import flowkit as fk
from flowkit import Flow


@pytest.fixture(scope='module')
def prepared(tmp_path_factory, synthetic_case_dir):
    return fk.prepare(synthetic_case_dir, tmp_path_factory.mktemp('xk') / 'study', upto='pauses')


@pytest.fixture
def flow(tmp_path, prepared, synthetic_case_dir):
    return Flow(fk.clone(prepared, tmp_path / 'study'), synthetic_case_dir)


def _run(flow, cwd, request_id, fault=None):
    extra = {'HYPOTRAIL_TEST_HOOKS': '1', 'HYPOTRAIL_FAULT': fault} if fault else None
    proc = fk.spawn('run', 'split', '--request-id', request_id, '--expected-revision',
                    flow.rev(), '--study', flow.study, cwd=cwd, extra_env=extra)
    out, err = proc.communicate(timeout=300)
    return proc.returncode, out, err


def _mine(flow, eid):
    return [(r['purpose'], r['partition'], r['result_id'])
            for r in fk.exposure_records(flow.study) if r['execution_id'] == eid]


def test_a_kill_during_recovery_never_loses_the_exposure(flow, tmp_path):
    code, _, _ = _run(flow, tmp_path, 'dying', 'run_after_reserve')
    assert code == 70
    eid = ex.execution_id('dying')
    # A second process detects the orphan and dies at the recovery commit point.
    code, _, _ = _run(flow, tmp_path, 'detector', 'recover_kill')
    assert code == 70
    # A third process completes the recovery.
    code, _, _ = _run(flow, tmp_path, 'third')
    assert code == 4
    assert eid in flow.state()['executions']['interrupted']
    assert _mine(flow, eid) == [('structural_inspection', 'all', None)]


def test_a_kill_during_a_failure_never_loses_the_exposure(flow, tmp_path):
    code, _, _ = _run(flow, tmp_path, 'failing', 'run_fail_before_promote,fail_kill')
    assert code == 70
    eid = ex.execution_id('failing')
    code, _, _ = _run(flow, tmp_path, 'after')
    assert code == 4                                   # an unknown outcome, never restarted
    assert eid in flow.state()['executions']['interrupted']
    assert _mine(flow, eid) == [('structural_inspection', 'all', None)]


def test_a_failure_records_its_exposure_once(flow, tmp_path):
    code, _, _ = _run(flow, tmp_path, 'failing', 'run_fail_before_promote')
    assert code == 1                                   # internal error, committed as failed
    eid = ex.execution_id('failing')
    assert eid not in flow.state()['executions']['active']
    assert _mine(flow, eid) == [('structural_inspection', 'all', None)]
    assert flow.run('split')['status'] == 'promoted'
    assert _mine(flow, eid) == [('structural_inspection', 'all', None)]
