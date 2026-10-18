"""Closure fix F1: ``status`` never shows a dead execution as running.

``status`` stays read-only and takes no writer lock, but it probes each execution lease
with a read-only check. A real ``hypotrail run`` process is paused before promotion
(``HYPOTRAIL_TEST_HOOKS=1``), then killed with SIGKILL; each ``status`` is a fresh
process. Studies live in ``tmp_path``.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

import pytest

from mlkit.study import executions as ex, lock, read, view

import flowkit as fk
from flowkit import Flow


@pytest.fixture(scope='module')
def prepared(tmp_path_factory, synthetic_case_dir):
    return fk.prepare(synthetic_case_dir, tmp_path_factory.mktemp('prep') / 'study', upto='pauses')


@pytest.fixture
def flow(tmp_path, prepared, synthetic_case_dir):
    return Flow(fk.clone(prepared, tmp_path / 'study'), synthetic_case_dir)


def _wait(path, proc, timeout=120.0):
    deadline = time.monotonic() + timeout
    while not path.exists():
        assert proc.poll() is None, proc.communicate()
        assert time.monotonic() < deadline, 'the run never reached its pause'
        time.sleep(0.05)


def _text_status(study, cwd) -> str:
    proc = subprocess.run([sys.executable, '-m', 'mlkit.study.cli', 'status', '--format', 'text',
                           '--study', str(study)], capture_output=True, text=True, cwd=cwd,
                          env=fk.env(), timeout=300)
    assert proc.returncode == 0 and proc.stderr == '', proc.stderr
    return proc.stdout


def _spawn_python(code, *args, cwd) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, '-c', code, *map(str, args)], cwd=cwd,
                            env=fk.env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True)


def _status(flow, *extra):
    return fk.hyp('status', *extra, '--study', flow.study, cwd=flow.study.parent, expect=0)[1]


def _paused_run(flow, tmp_path, request_id='paused'):
    gate = tmp_path / 'gate'
    proc = fk.spawn('run', 'split', '--request-id', request_id, '--expected-revision', flow.rev(),
                    '--study', flow.study, cwd=tmp_path,
                    extra_env={'HYPOTRAIL_TEST_HOOKS': '1',
                               'HYPOTRAIL_FAULT': f'run_pause_before_promote:{gate}'})
    _wait(gate / 'ready', proc)
    return proc, gate, ex.execution_id(request_id)


def test_killed_run_is_reported_outcome_unknown_by_a_fresh_status_process(flow, tmp_path):
    proc, gate, eid = _paused_run(flow, tmp_path)
    try:
        # While the process lives and holds its lease, status reports it as running.
        live = _status(flow)['view']
        assert list(live['executions']['active']) == [eid]
        assert live['executions']['active'][eid]['liveness'] == 'running'
        assert live['executions']['suspected_interrupted'] == {}
        assert live['next_action']['kind'] != 'outcome_unknown'
        assert _status(flow, '--summary')['executions']['active'] == [eid]
    finally:
        os.kill(proc.pid, signal.SIGKILL)
        proc.communicate(timeout=60)
    assert proc.returncode == -signal.SIGKILL
    home = flow.study / '.hypotrail'
    before = {p.name: p.read_bytes() for p in home.iterdir() if p.is_file()}
    rev = flow.rev()

    payload = _status(flow)
    v = payload['view']
    assert v['executions']['active'] == {}                     # never shown as running
    record = v['executions']['suspected_interrupted'][eid]
    assert record['liveness'] == 'outcome_unknown' and record['activity'] == 'split'
    assert 'outcome is unknown' in record['reason']
    assert v['next_action']['kind'] == 'outcome_unknown'
    assert v['next_action']['execution_id'] == eid and v['next_action']['activity'] == 'split'
    assert 'never call it in progress' in v['next_action']['message']
    item = next(x for x in v['not_yet_defensible'] if x['id'] == 'interrupted_executions')
    assert item['executions'] == [eid]

    summary = _status(flow, '--summary')
    assert summary['executions']['active'] == []
    assert summary['executions']['suspected_interrupted'] == [
        {'execution_id': eid, 'activity': 'split', 'liveness': 'outcome_unknown',
         'reason': record['reason']}]
    assert summary['next_action']['kind'] == 'outcome_unknown'
    assert summary['not_yet_defensible']['top'][0]['id'] == 'interrupted_executions'

    text = _text_status(flow.study, tmp_path)
    assert f'execution {eid} (split): outcome unknown' in text
    assert 'next action: outcome_unknown' in text

    # status is read-only: no state change, no recovery, the orphan lease is left alone.
    after = {p.name: p.read_bytes() for p in home.iterdir() if p.is_file()}
    assert after == before and flow.rev() == rev
    assert list(flow.state()['executions']['active']) == [eid]
    assert lock.lease_path(flow.study, eid).exists()

    # The next run records it as interrupted (exit 4), as before; nothing is restarted.
    refused = flow.run('split', expect=4)
    assert refused['error']['code'] == 'interrupted_execution_pending'
    after_run = _status(flow)['view']
    assert after_run['executions']['suspected_interrupted'] == {}
    assert eid in after_run['executions']['interrupted']
    assert after_run['next_action']['kind'] == 'acknowledge_interruption'


def test_suspected_execution_can_be_acknowledged_with_the_juniors_words(flow, tmp_path):
    proc, gate, eid = _paused_run(flow, tmp_path)
    os.kill(proc.pid, signal.SIGKILL)
    proc.communicate(timeout=60)
    assert _status(flow)['view']['next_action']['kind'] == 'outcome_unknown'
    words = 'The split run stopped and its outcome is unknown; record that, I will decide later.'
    ack = flow.call('run', '--acknowledge-interruption', eid, '--user-words', words,
                    '--request-id', 'ack', '--expected-revision', flow.rev(),
                    '--study', flow.study)
    assert ack['status'] == 'acknowledged' and ack['result']['restarted'] is False
    v = _status(flow)['view']
    assert v['executions'] == {**v['executions'], 'active': {}, 'interrupted': {},
                               'suspected_interrupted': {}}
    assert 'split' not in v['results']


def test_status_probe_does_not_block_a_starting_run(flow, tmp_path):
    """Probing leases in a loop while runs start never makes a run fail."""
    stop = tmp_path / 'stop'
    prober = _spawn_python(
        'import sys, pathlib\n'
        'from mlkit.study import lock\n'
        'study, stop = sys.argv[1], pathlib.Path(sys.argv[2])\n'
        'while not stop.exists():\n'
        '    lock.probe_leases(study)\n', flow.study, stop, cwd=tmp_path)
    try:
        assert flow.run('split')['status'] == 'promoted'
    finally:
        stop.write_text('')
        prober.communicate(timeout=60)
    assert prober.returncode == 0


def test_view_without_probe_marks_liveness_not_checked(flow, tmp_path):
    proc, gate, eid = _paused_run(flow, tmp_path)
    try:
        built = view.build(read.open(flow.study))
        assert built['executions']['active'][eid]['liveness'] == 'not_checked'
        assert built['executions']['suspected_interrupted'] == {}
        held = lock.probe_leases(flow.study)
        assert held == {eid: True}
    finally:
        os.kill(proc.pid, signal.SIGKILL)
        proc.communicate(timeout=60)
    assert lock.probe_leases(flow.study) == {eid: False}
    assert view.build(read.open(flow.study), leases={})['executions']['active'][eid][
        'liveness'] == 'running'                                # reserved after the probe
