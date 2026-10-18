"""``run`` payloads and concurrent duplicates (review findings L6, L7).

* L6: a ``late_not_promoted`` result is stored but describes a state that no longer
  holds; its payload carries no ``values`` an agent could cite.
* L7: a second ``run`` of the same slot on the same inputs, while the first one is
  computing, is refused (``execution_in_progress``) instead of computing twice.

Interleavings use in-process hooks of :func:`mlkit.study.executions.run`. Studies live
in ``tmp_path``.
"""
from __future__ import annotations

import json

import pytest

from mlkit.reliability import CommandRefused
from mlkit.study import executions as ex

import flowkit as fk
from flowkit import Flow


@pytest.fixture(scope='module')
def prepared(tmp_path_factory, synthetic_case_dir):
    return fk.prepare(synthetic_case_dir, tmp_path_factory.mktemp('rp') / 'study', upto='pauses')


@pytest.fixture
def flow(tmp_path, prepared, synthetic_case_dir):
    return Flow(fk.clone(prepared, tmp_path / 'study'), synthetic_case_dir)


def test_a_late_result_has_no_citable_values(flow):
    def change_the_split(_plan):
        flow.decide('split', {**fk.SPLIT, 'seed': 7},
                    words='Yes, the same stratified split with seed 7')

    rev = flow.rev()
    out = ex.run(flow.study, 'split', {}, request_id='late', expected_revision=rev,
                 hooks={'before_promote': change_the_split})
    payload = out.payload
    assert payload['status'] == 'late_not_promoted' and payload['result_id']
    assert payload['values'] is None
    assert payload['result']['citable'] is False
    replay = ex.run(flow.study, 'split', {}, request_id='late', expected_revision=rev).payload
    assert replay['replayed'] is True and replay['status'] == 'late_not_promoted'
    assert replay['values'] is None


def test_a_concurrent_duplicate_run_is_refused(flow):
    seen = {}

    def duplicate(_plan):
        with pytest.raises(CommandRefused) as err:
            ex.run(flow.study, 'split', {}, request_id='second', expected_revision=flow.rev())
        seen['error'] = err.value

    out = ex.run(flow.study, 'split', {}, request_id='first', expected_revision=flow.rev(),
                 hooks={'after_reserve': duplicate})
    assert out.payload['status'] == 'promoted'
    err = seen['error']
    assert err.code == 'execution_in_progress'
    assert err.details['execution_id'] == ex.execution_id('first')
    assert err.details['slot'] == 'split'
    # Not a lease conflict, not a second computation: one execution history only.
    histories = list((flow.study / '.hypotrail' / 'executions').glob('e_*.json'))
    assert [json.loads(h.read_text())['execution_id'] for h in histories] == [
        ex.execution_id('first')]


def test_another_slot_may_run_meanwhile(flow):
    flow.run('split')
    seen = {}

    def other(_plan):
        seen['out'] = ex.run(flow.study, 'eda.special_values', {}, request_id='other',
                             expected_revision=flow.rev())

    ex.run(flow.study, 'eda.target_rate', {}, request_id='one', expected_revision=flow.rev(),
           hooks={'after_reserve': other})
    assert seen['out'].payload['status'] == 'promoted'
