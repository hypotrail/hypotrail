"""Revision, duplicate-command, late-result, and cautious-resumption scenarios."""
import copy
import json
from pathlib import Path
import pytest
from mlkit import config, pilot, reliability, discover, task_contract
from test_classical import prepare

@pytest.fixture
def project(tmp_path, monkeypatch):
    prepare(tmp_path, 'binary')
    monkeypatch.setattr(config, 'ROOT', tmp_path)
    return tmp_path


def request(state, key='request-1', value='Synthetic use'):
    return {'request_id': key, 'expected_revision': state.get('revision', 0),
            'action': 'answer', 'params': {'question': 'Q-USE', 'value': value,
            'rationale': 'Synthetic test answer, not a demo decision', 'confirmed': False}}


def test_two_clients_and_duplicate_do_not_overwrite(project):
    state = pilot.init('junior'); first = request(state); second = request(state, 'other')
    receipt = reliability.apply(pilot, state, first)
    revision = state['revision']; count = len((project/'.pilot/events.jsonl').read_text().splitlines())
    assert reliability.apply(pilot, state, first)['replayed']
    assert state['revision'] == revision
    assert len((project/'.pilot/events.jsonl').read_text().splitlines()) == count
    with pytest.raises(ValueError, match='stale'): reliability.apply(pilot, state, second)
    altered = copy.deepcopy(first); altered['params']['value'] = 'Other value'
    with pytest.raises(ValueError, match='Idempotency'): reliability.apply(pilot, state, altered)
    assert state['answers']['Q-USE']['status'] == 'assumed'
    assert receipt['revision'] == revision


def test_failed_command_rolls_back_files_and_state(project):
    state = pilot.init('junior'); before = copy.deepcopy(state)
    req = request(state); req['params']['question'] = 'unknown'
    with pytest.raises(ValueError): reliability.apply(pilot, state, req)
    assert state == before and pilot.load() == before
    assert not (project/'.pilot/transaction.json').exists()


def test_crash_between_contract_write_and_commit_restores_contract(project):
    state = pilot.init('junior'); path = project/'project.yaml'; original = path.read_text()
    pilot.write(project/'.pilot/transaction.json', {'request_id':'crashed', 'before_files': {'project.yaml': original}})
    path.write_text('broken: contract')
    reliability.recover(pilot, state)
    assert path.read_text() == original and state == pilot.load()


def test_interrupt_reserves_budget_and_blocks_automatic_relaunch(project):
    state = pilot.init('auto')
    run = reliability.start(pilot, state, 'classical-run', ['python','-m','mlkit.classical','run'])
    restored = pilot.load(); reliability.recover(pilot, restored)
    assert restored['executions'] == 1 and restored['interrupted_execution']['id'] == run['id']
    assert 'interrupted' in pilot.step(restored)
    record = json.loads((project/'.pilot/executions'/f"{run['id']}.json").read_text())
    assert record['status'] == 'interrupted_unknown'
    assert pilot.main(['acknowledge-interruption','--execution',run['id']]) == 0
    assert pilot.load()['seconds_used'] == state['max_seconds']


def test_late_result_never_promoted_after_contract_or_code_change(project):
    state = pilot.init('auto'); run = reliability.start(pilot, state, 'discovery', [])
    (project/'mlkit').mkdir(); (project/'mlkit/change.py').write_text('# changed code')
    outcome = reliability.finish(pilot, state, run, 0, 1)
    assert outcome['status'] == 'stale' and not state['steps']


def test_exposure_survives_split_change_and_is_not_confirmation(project):
    first = discover.report(project)
    path = project/'project.yaml'; contract = config.load_yaml(path)
    contract['spec']['split']['seed'] += 1
    import yaml
    path.write_text(yaml.safe_dump(contract))
    second = discover.report(project)
    assert second['exposure']['validation_rows_previously_described'] > 0
    assert second['exposure']['generalization'] == 'not_established'
    assert second == discover.report(project)
    assert len(json.loads((project/'.pilot/exposures.json').read_text())) == 2


def test_summary_leads_with_validity_not_scores(project):
    state = pilot.init('junior'); overview = reliability.summary(pilot, state)
    assert overview['blockers'] and overview['generalization'] == 'not_established'
    assert len(overview['moments']) == 4
    state['seconds_used'] = state['max_seconds']
    assert reliability.summary(pilot, state)['status'] == 'budget_exhausted'


def test_failure_at_commit_restores_confirmed_answer_file(project, monkeypatch):
    state = pilot.init('junior'); before = copy.deepcopy(state)
    req = request(state); req['params']['confirmed'] = True
    def fail_commit(value):
        raise OSError('Simulated interrupted write before commit')
    monkeypatch.setattr(pilot, 'save', fail_commit)
    with pytest.raises(OSError): reliability.apply(pilot, state, req)
    assert state == before and pilot.load() == before
    assert not (project/'answers.yaml').exists()


def test_external_context_change_archives_previous_state(project):
    state = pilot.init('auto'); state['steps']['discovery'] = {'returncode':0}
    path = project/'project.yaml'; path.write_text(path.read_text()+'\n# external edit\n')
    pilot.sync_context(state)
    snapshots = list((project/'.pilot/iterations').glob('*-context-*/state.json'))
    assert len(snapshots) == 1
    assert json.loads(snapshots[0].read_text())['steps']['discovery']['returncode'] == 0
    assert state['steps'] == {}


def test_completed_result_invalidated_on_code_change_without_reconfirming_business(project):
    state = pilot.init('auto')
    pilot.propose(state, 'Q-USE', 'Confirmed test use', 'Simulation', status='confirmed')
    state['steps']['discovery'] = {'returncode':0,'provenance':reliability.provenance(project)}
    (project/'scripts').mkdir(); (project/'scripts/new.py').write_text('# implementation change')
    pilot.sync_context(state)
    assert not state['steps']
    assert state['answers']['Q-USE']['status'] == 'confirmed'
    assert list((project/'.pilot/iterations').glob('*-provenance-*/state.json'))


def test_specialist_result_rejected_after_code_change(project):
    state = pilot.init('auto'); task = pilot.dispatch(state, 'explorer', 'Synthetic task')
    (project/'scripts').mkdir(); (project/'scripts/new.py').write_text('# changed')
    with pytest.raises(ValueError, match='stale'): pilot.receive(state, task['task'])
    assert state['tasks'][0]['status'] == 'stale'


def test_auto_stops_after_first_failed_calculation(project, monkeypatch):
    import subprocess
    pilot.init('auto'); calls=[]
    def fail(*args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args[0], 7, 'controlled failure')
    monkeypatch.setattr(subprocess, 'run', fail)
    assert pilot.main(['auto']) == 2
    assert len(calls) == 1
    assert pilot.load()['steps']['discovery']['returncode'] == 7
