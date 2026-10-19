"""Review fix M4: a deliverable is current only while its file is the one the engine wrote.

``currency.effective_status`` checks that each generated deliverable exists and that its
bytes match the manifest record (the generated notebook ignoring Marimo's
``__generated_with`` stamp). A deleted report, a report replaced by a blank file, and a
report or notebook with one byte changed are ``stale`` with ``stale_reason``
``file_missing`` or ``file_changed``: ``status``, the summary, the messages, and ``check``
say so, and a render makes them current again.
"""
from __future__ import annotations

import json
import time

import pytest

import companion_contract as cc
import flowkit as fk
from mlkit.study import currency, read, view

REPORT = 'reports/study.html'
NOTEBOOK = 'notebooks/study_generated.py'


@pytest.fixture(scope='module')
def rendered(tmp_path_factory, synthetic_case_dir):
    """A binary study whose three pauses are confirmed; every commit rendered it."""
    flow = fk.Flow(tmp_path_factory.mktemp('m4') / 'study', synthetic_case_dir, prefix='m')
    flow.init()
    flow.pauses()
    return flow


@pytest.fixture
def flow(rendered, tmp_path):
    return fk.Flow(fk.clone(rendered.study, tmp_path / 'study'), rendered.case_dir, prefix='n')


def _status(flow):
    code, p = cc.run('status', '--study', flow.study)
    assert code == 0, p
    return p['view']['artifacts']


def _summary(flow):
    code, p = cc.run('status', '--summary', '--study', flow.study)
    assert code == 0, p
    return p


def _check_findings(flow):
    _, p = cc.run('check', '--study', flow.study)
    return [f for f in p['findings'] if f['code'] == 'artifact_not_current']


def test_a_freshly_rendered_study_is_current(flow):
    artifacts = _status(flow)
    assert artifacts['status'] == 'ok'
    for name in ('report', 'notebook'):
        item = artifacts['items'][name]
        assert (item['status'], item['stale_reason']) == ('ok', None), item
    assert artifacts['items']['workbench']['stale_reason'] is None
    assert _check_findings(flow) == []


@pytest.mark.parametrize('change, reason', [
    ('delete', currency.FILE_MISSING),
    ('blank', currency.FILE_CHANGED),
    ('one_byte', currency.FILE_CHANGED),
])
def test_a_changed_report_is_not_current(flow, change, reason):
    path = flow.study / REPORT
    if change == 'delete':
        path.unlink()
    elif change == 'blank':
        path.write_bytes(b'')
    else:
        data = bytearray(path.read_bytes())
        i = data.index(b'<title>') + len(b'<title>')
        data[i] = ord('x') if data[i] != ord('x') else ord('y')
        path.write_bytes(bytes(data))

    items = _status(flow)['items']
    report = items['report']
    assert (report['status'], report['stale_reason'], report['recorded_status']) == \
        ('stale', reason, 'ok')
    assert ('deleted or moved' if change == 'delete' else 'was changed') in report['message']
    assert items['notebook']['status'] == 'ok'

    summary = _summary(flow)
    assert summary['artifacts']['status'] == 'stale'
    assert summary['artifacts']['items']['report']['status'] == 'stale'
    assert summary['artifacts']['items']['report']['message'] == report['message']
    assert any('report not up to date' in line for line in summary['recap']), summary['recap']

    [finding] = _check_findings(flow)
    assert finding['where'] == 'artifact:report'
    assert finding['details']['status'] == 'stale' and finding['details']['reason'] == reason

    code, p = cc.run('render', '--study', flow.study)        # Regenerate makes it current
    assert code == 0, p
    after = _status(flow)['items']['report']
    assert (after['status'], after['stale_reason']) == ('ok', None)
    assert _check_findings(flow) == []


def test_a_changed_or_deleted_notebook_is_not_current(flow):
    path = flow.study / NOTEBOOK
    original = path.read_bytes()
    path.write_bytes(original + b'\n# my note\n')
    item = _status(flow)['items']['notebook']
    assert (item['status'], item['stale_reason']) == ('stale', currency.FILE_CHANGED)
    [finding] = _check_findings(flow)
    assert finding['where'] == 'artifact:notebook'
    assert finding['details']['reason'] == currency.FILE_CHANGED

    path.unlink()
    item = _status(flow)['items']['notebook']
    assert (item['status'], item['stale_reason']) == ('stale', currency.FILE_MISSING)


def test_marimo_restamping_the_notebook_is_not_a_change(flow):
    path = flow.study / NOTEBOOK
    data = path.read_bytes()
    assert b'__generated_with = "' in data
    stamped = currency.GENERATED_WITH.sub(b'__generated_with = "9.9.9"', data)
    assert stamped != data
    path.write_bytes(stamped)
    item = _status(flow)['items']['notebook']
    assert (item['status'], item['stale_reason']) == ('ok', None)


def test_the_stale_reason_of_an_older_revision_is_kept(flow):
    """A deliverable written for an earlier revision keeps its reason (no regression)."""
    raw = json.loads((flow.study / '.hypotrail/artifacts.json').read_text())
    state = read.open(flow.study).state
    item = raw['artifacts']['report']
    older = {**state, 'revision': state['revision'] + 1}
    assert currency.stale_reason(item, older) == currency.REVISION_CHANGED
    assert currency.effective_status(item, older) == 'stale'
    assert currency.file_check(flow.study, item) is None
    assert currency.file_check(None, item) is None             # no study folder: not checked
    workbench = raw['artifacts']['workbench']
    (flow.study / workbench['path']).unlink()                   # the junior's free space
    assert currency.file_check(flow.study, workbench) is None
    assert currency.effective_status(workbench, state) == 'ok'


def test_status_latency_is_recorded(flow):
    """The cost of hashing the deliverables on every read; recorded, no threshold."""
    sizes = {name: (flow.study / rel).stat().st_size
             for name, rel in (('report', REPORT), ('notebook', NOTEBOOK))}
    timings = []
    for _ in range(5):
        start = time.perf_counter()
        view.build(flow.study)
        timings.append(time.perf_counter() - start)
    start = time.perf_counter()
    study = read.open(flow.study)
    raw = study.artifacts()['artifacts']
    for name in ('report', 'notebook'):
        assert currency.file_check(flow.study, raw[name]) is None
    checks = time.perf_counter() - start
    print('M4 latency', json.dumps({'view_build_s': sorted(timings)[len(timings) // 2],
                                    'file_checks_s': round(checks, 6), 'bytes': sizes}))
