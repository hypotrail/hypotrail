"""Executions: reserve, compute under a lease, promote or store late (plan WP2.1).

Process deaths are real: a ``hypotrail run`` subprocess ends itself with ``os._exit``
through the test hooks (``HYPOTRAIL_TEST_HOOKS=1``), so its lease is released by the
operating system exactly as after a crash. Interleavings that need a decision while a
computation runs use in-process hooks of :func:`mlkit.study.executions.run`.
Studies live in ``tmp_path``.
"""
from __future__ import annotations

import pytest

from mlkit.study import activities as act, executions as ex, lock, read
from mlkit.study.errors import StudyError
from mlkit.reliability import CommandRefused

import flowkit as fk
from flowkit import Flow


@pytest.fixture(scope='module')
def prepared(tmp_path_factory, synthetic_case_dir):
    """Decisions of pauses 1 and 2 confirmed; nothing computed yet."""
    return fk.prepare(synthetic_case_dir, tmp_path_factory.mktemp('prep') / 'study', upto='pauses')


@pytest.fixture
def flow(tmp_path, prepared, synthetic_case_dir):
    return Flow(fk.clone(prepared, tmp_path / 'study'), synthetic_case_dir)


@pytest.fixture
def work(tmp_path):
    folder = tmp_path / 'cwd'
    folder.mkdir()
    return folder


def _die(study, work, activity, fault, request_id='dying'):
    rev = read.open(study).revision
    proc = fk.spawn('run', activity, '--request-id', request_id, '--expected-revision', rev,
                    '--study', study, cwd=work,
                    extra_env={'HYPOTRAIL_TEST_HOOKS': '1', 'HYPOTRAIL_FAULT': fault})
    out, err = proc.communicate(timeout=300)
    assert proc.returncode == 70, (out, err)       # os._exit: no output, no cleanup
    assert out == '' and err == ''
    return ex.execution_id(request_id)


@pytest.mark.parametrize('fault', ['run_after_reserve', 'run_before_promote'])
def test_death_between_reserve_and_promote_is_an_unknown_outcome(flow, work, fault):
    before = len(fk.registry_entries(flow.study))
    eid = _die(flow.study, work, 'split', fault)
    state = flow.state()
    # status is read-only: the dead execution is still listed as active until a run
    # detects that nobody holds its lease.
    assert list(state['executions']['active']) == [eid]
    assert 'split' not in state['current']
    assert len(fk.registry_entries(flow.study)) == before      # put happens only at promotion
    rev = flow.rev()
    code, refused = fk.hyp('run', 'split', '--request-id', 'next',
                           '--expected-revision', rev, '--study', flow.study, cwd=work)
    assert code == 4 and refused['error']['code'] == 'interrupted_execution_pending'
    assert refused['error']['details']['interrupted'] == [eid]
    view = flow.view()
    assert view['executions']['active'] == {}
    record = view['executions']['interrupted'][eid]
    assert record['status'] == 'interrupted_unknown' and record['activity'] == 'split'
    assert view['next_action'] == {**view['next_action'], 'kind': 'acknowledge_interruption',
                                   'execution_id': eid}
    assert 'interrupted_executions' in {x['id'] for x in view['not_yet_defensible']}
    # The rows it may have read stay exposed, with no result.
    mine = [r for r in fk.exposure_records(flow.study) if r['execution_id'] == eid]
    assert [(r['purpose'], r['partition'], r['result_id']) for r in mine] == [
        ('structural_inspection', 'all', None)]
    assert not lock.orphaned_leases(flow.study)                # the orphan lease is cleared
    assert view['results'] == {}                               # nothing ran, nothing restarted
    assert len(fk.registry_entries(flow.study)) == before



def test_runs_refused_until_acknowledged_and_never_restarted(flow, work):
    eid = _die(flow.study, work, 'split', 'run_after_reserve')
    for _ in range(2):                                         # detection, then refusals
        payload = flow.run('split', expect=4)
        assert payload['error']['code'] == 'interrupted_execution_pending'
    wrong = flow.call('run', '--acknowledge-interruption', 'e_nothing', '--request-id', 'ack0',
                      '--expected-revision', flow.rev(), '--study', flow.study, expect=2)
    assert wrong['error']['code'] == 'unknown_execution'
    entries = len(fk.registry_entries(flow.study))
    rev = flow.rev()
    ack = flow.call('run', '--acknowledge-interruption', eid, '--request-id', 'ack1',
                    '--expected-revision', rev, '--study', flow.study)
    assert ack['schema'] == 'hypotrail.run/1' and ack['action'] == 'run.acknowledge'
    assert tuple(ack) == ex.PAYLOAD_KEYS
    assert ack['status'] == 'acknowledged' and ack['result']['restarted'] is False
    assert ack['revision'] == rev + 1
    again = flow.call('run', '--acknowledge-interruption', eid, '--request-id', 'ack1',
                      '--expected-revision', rev, '--study', flow.study)
    assert again['replayed'] is True and again['revision'] == rev + 1
    state = flow.state()
    assert state['executions']['interrupted'] == {} and state['executions']['active'] == {}
    assert 'split' not in state['current']                     # not restarted
    assert len(fk.registry_entries(flow.study)) == entries
    assert flow.run('split')['status'] == 'promoted'           # only an explicit new request


def test_stray_lease_without_reservation_is_removed(flow):
    stray = lock.lease_path(flow.study, 'e_stray')
    stray.parent.mkdir(exist_ok=True)
    stray.write_text('{}')                                     # a writer died before reserving
    assert flow.run('split')['status'] == 'promoted'
    assert not stray.exists()
    assert flow.state()['executions']['interrupted'] == {}


def test_late_result_is_stored_and_not_promoted(flow):
    def meanwhile(plan):                                       # another client decides
        flow.decide('split', {**fk.SPLIT, 'seed': fk.SPLIT['seed'] + 1})

    outcome = ex.run(flow.study, 'split', {}, request_id='late', expected_revision=flow.rev(),
                     hooks={'before_promote': meanwhile})
    payload = outcome.payload
    assert outcome.exit_code == 0 and payload['status'] == 'late_not_promoted'
    rid = payload['result_id']
    state = flow.state()
    assert 'split' not in state['current']
    late = state['executions']['late'][payload['execution_id']]
    assert late['status'] == 'late_not_promoted' and late['result_id'] == rid
    assert late['current_input_key'] != late['input_key'] == payload['result']['input_key']
    entry = read.open(flow.study).result(rid)                  # stored and verifiable
    assert entry['inputs']['decision'] == fk.SPLIT
    assert [r['result_id'] for r in fk.exposure_records(flow.study)
            if r['execution_id'] == payload['execution_id']] == [rid]
    fresh = flow.run('split')                                  # the new decision, promoted
    assert fresh['status'] == 'promoted' and fresh['result_id'] != rid
    assert fresh['values']['seed'] == fk.SPLIT['seed'] + 1


def test_replay_returns_the_execution_state_and_computes_nothing(flow):
    rev = flow.rev()
    first = flow.call('run', 'split', '--request-id', 'once', '--expected-revision', rev,
                      '--study', flow.study)
    assert first['status'] == 'promoted' and first['replayed'] is False
    entries, exposures = fk.registry_entries(flow.study), fk.exposure_records(flow.study)
    revision = flow.rev()
    replay = flow.call('run', 'split', '--request-id', 'once', '--expected-revision', rev,
                       '--study', flow.study)
    assert replay['replayed'] is True and replay['status'] == 'promoted'
    assert (replay['result_id'], replay['revision'], replay['execution_id']) == (
        first['result_id'], first['revision'], first['execution_id'])
    assert fk.registry_entries(flow.study) == entries and flow.rev() == revision
    assert fk.exposure_records(flow.study) == exposures
    conflict = flow.call('run', 'eda.target_rate', '--request-id', 'once',
                         '--expected-revision', rev, '--study', flow.study, expect=2)
    assert conflict['error']['code'] == 'idempotency_conflict'


def test_an_already_current_result_is_not_recomputed(flow):
    first = flow.run('split')
    rev = flow.rev()
    again = flow.run('split')
    assert again['status'] == 'already_current' and again['result_id'] == first['result_id']
    assert flow.rev() == rev


def test_stale_expected_revision_is_refused_without_lease(flow):
    payload = flow.call('run', 'split', '--request-id', 'old', '--expected-revision',
                        flow.rev() - 1, '--study', flow.study, expect=2)
    assert payload['error']['code'] == 'stale_revision'
    assert flow.state()['executions']['active'] == {}
    assert not list((flow.study / '.hypotrail' / 'executions').glob('*.lease'))


def test_a_failed_computation_is_recorded_and_its_rows_stay_exposed(flow, monkeypatch):
    def broken(store, plan):
        raise ValueError('boom')

    monkeypatch.setattr(act, 'compute', broken)
    rev = flow.rev()
    with pytest.raises(ValueError):
        ex.run(flow.study, 'split', {}, request_id='broken', expected_revision=rev)
    state = flow.state()
    eid = ex.execution_id('broken')
    assert state['executions']['active'] == {} and state['executions']['interrupted'] == {}
    fail = state['receipts'][ex.derived_request_id('fail', 'broken')]['result']
    assert fail['status'] == 'failed' and fail['error']['message'] == 'ValueError: boom'
    assert [r['result_id'] for r in fk.exposure_records(flow.study)
            if r['execution_id'] == eid] == [None]
    monkeypatch.undo()
    replay = ex.run(flow.study, 'split', {}, request_id='broken', expected_revision=rev).payload
    assert replay['replayed'] is True and replay['status'] == 'failed'


def test_read_only_process_refuses_to_run(flow, monkeypatch):
    monkeypatch.setenv('HYPOTRAIL_READ_ONLY', '1')
    before = fk.tree_digest(flow.study)
    payload = flow.run('split', expect=2)
    assert payload['error']['code'] == 'read_only'
    assert fk.tree_digest(flow.study) == before


def test_split_refused_before_pauses_one_and_two(tmp_path, synthetic_case_dir):
    flow = Flow(tmp_path / 'study', synthetic_case_dir)
    flow.init()
    payload = flow.run('split', expect=2)
    assert payload['error']['code'] == 'precondition_missing'
    missing = {m['decision'] for m in payload['error']['details']['missing']}
    assert missing == {'prediction_time', 'feature_availability', 'split'}
    flow.pauses(split=False)
    payload = flow.run('split', expect=2)
    assert [m['decision'] for m in payload['error']['details']['missing']] == ['split']
    flow.decide('split', fk.SPLIT)
    assert flow.run('split')['status'] == 'promoted'


def test_split_follows_the_decision_and_reports_overlap_after_a_change(flow):
    first = flow.run('split')['values']
    assert first['seed'] == fk.SPLIT['seed'] and first['overlap'] is None
    parts = first['partitions']
    assert parts['train']['n_rows'] + parts['validation']['n_rows'] == first['n_rows']
    flow.decide('split', {**fk.SPLIT, 'seed': 7})
    second = flow.run('split')['values']
    overlap = second['overlap']
    assert overlap['rows_in_new'] == overlap['rows_in_old'] == first['n_rows']
    assert overlap['moved'] > 0
    assert overlap['previously_exposed']['train']['structural_inspection'] == \
        second['partitions']['train']['n_rows']               # explored rows are never unseen
    again = flow.run('split')
    assert again['status'] == 'already_current'                # overlap is part of identity


def test_unknown_activity_and_bad_options_are_refused(flow):
    assert flow.call('run', 'fit.forest', '--request-id', 'x', '--expected-revision', flow.rev(),
                     '--study', flow.study, expect=2)['error']['code'] == 'invalid_arguments'
    assert flow.call('run', '--request-id', 'x', '--expected-revision', flow.rev(),
                     '--study', flow.study, expect=2)['error']['code'] == 'invalid_arguments'
    assert flow.run('split', '--column', 'x', expect=2)['error']['code'] == 'invalid_arguments'
    with pytest.raises(CommandRefused) as info:
        act.normalize_options('eda.rate_by', {})
    assert info.value.code == 'invalid_arguments'
    with pytest.raises(StudyError):
        ex._store(flow.study.parent / 'nowhere')
    assert flow.state()['executions'] == {'active': {}, 'interrupted': {}, 'late': {}}
