"""Project, journey, and result contracts; cross-project isolation and changed data."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import contracts  # noqa: E402

spec = importlib.util.spec_from_file_location('osml_protocol_contracts', ROOT / 'protocol.py')
protocol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(protocol)


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """Isolated copy of the registry, projects, and shared data."""
    shutil.copytree(ROOT / 'projects', tmp_path / 'projects')
    (tmp_path / 'data').mkdir()
    shutil.copy2(ROOT / 'data/bank.csv', tmp_path / 'data/bank.csv')
    monkeypatch.setattr(contracts, 'SHARED_DATA', tmp_path / 'data')
    return tmp_path / 'projects'


def edit(path, change):
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data, ensure_ascii=False))


def code(projects, project='uci-auto-mpg-v1'):
    with pytest.raises(contracts.ContractError) as error:
        contracts.load_bundle(project, projects)
    return error.value.code


def test_both_projects_valid_and_metrics_explicit():
    bank, mpg = contracts.load_bundle('uci-bank-marketing-v1'), contracts.load_bundle('uci-auto-mpg-v1')
    assert bank['journey']['id'] == 'binary-selection' and mpg['journey']['id'] == 'regression-comparison'
    names = {m for r in mpg['results']['results'] for m in r['metrics']}
    assert names == {'mae_mpg', 'rmse_mpg', 'mean_error_mpg', 'within_3_mpg_share'}
    assert not names & {'alerts', 'false_alarms', 'threshold'}
    assert all(d['unit'] for d in mpg['results']['metric_definitions'].values())
    assert {r['id']: r['display']['mae_mpg'] for r in mpg['results']['results']}['linear-all'].endswith(' mpg')
    # Documented mapping from historical Bank Marketing pages.
    assert bank['project']['compatibility']['legacy_steps'] == [a['id'] for a in bank['journey']['activities']]


@pytest.mark.parametrize('change,expected', [
    (lambda p: p.update(schema='hypotrail.project/9'), 'schema_version'),
    (lambda p: p.pop('title'), 'config'),
    (lambda p: [f.update(value='') for f in p['facts'] if f['id'] == 'target'], 'target_missing'),
    (lambda p: p['activities']['start']['blocks'].append({'component': 'gauge3d'}), 'component_unknown'),
    (lambda p: p['activities']['compare']['blocks'][0]['choice']['domain'].append({'value': 'forest', 'result': 'random-forest'}), 'result_missing'),
    (lambda p: p['activities']['baseline']['blocks'][0]['metrics'].append('r2'), 'metric_missing'),
    (lambda p: p['dataset'].update(path='../../../etc/passwd'), 'path_forbidden'),
    (lambda p: p['dataset'].update(path='/etc/passwd'), 'path_forbidden'),
    (lambda p: p['activities']['start'].update(command='rm -rf /'), 'config'),
    (lambda p: p.update(problem_type='forecasting'), 'journey_incompatible'),
    (lambda p: p['activities']['errors']['blocks'].pop(0), 'component_missing'),
    (lambda p: p['activities']['start']['blocks'][0]['highlights'][0].update(value='{{r:unknown.mae_mpg}}'), 'placeholder'),
])
def test_invalid_project_rejected_explicitly(tree, change, expected):
    edit(tree / 'auto-mpg/project.json', change)
    assert code(tree) == expected


@pytest.mark.parametrize('change,expected', [
    (lambda r: r['dataset'].update(id='uci-wine-quality'), 'results_other_dataset'),
    (lambda r: r.update(project_id='uci-bank-marketing-v1'), 'results_other_project'),
    (lambda r: r['metric_definitions']['mae_mpg'].update(unit=''), 'unit_missing'),
    (lambda r: r['metric_definitions'].pop('rmse_mpg'), 'metric_missing'),
    (lambda r: r.update(schema='hypotrail.results/0'), 'schema_version'),
])
def test_invalid_results_rejected(tree, change, expected):
    edit(tree / 'auto-mpg/results.json', change)
    assert code(tree) == expected


def test_registry_paths_and_journey_paths_constrained(tree):
    edit(tree / 'registry.json', lambda r: r['projects'].append({'id': 'evil', 'dir': '../outside'}))
    assert code(tree, 'evil') == 'path_forbidden'
    edit(tree / 'registry.json', lambda r: r['projects'].pop())
    edit(tree / 'auto-mpg/project.json', lambda p: p['journey'].update(id='../binary-selection'))
    assert code(tree) == 'path_forbidden'


def apply(db, answers, key, activity='compare'):
    s = protocol.status(db)
    event = {'protocol_version': 1, 'event_id': key, 'session_id': s['session_id'], 'expected_revision': s['revision'], 'context_hash': s['context_hash'],
             'type': 'submit_state', 'payload': {'state': {'activity': activity, 'answers': answers}}}
    registered = protocol.submit(db, event)
    return protocol.apply(db, key, registered['revision'], registered['context_hash'])


def test_regression_flow_blocked_until_confirmed_then_in_target_unit(tmp_path):
    protocol.use_project('uci-auto-mpg-v1')
    db = tmp_path / 'mpg.sqlite'
    s = protocol.status(db)
    assert s['blocked'] == {'compare': ['Prediction time']}
    unknown = [f['id'] for f in s['facts'] if f['status'] != 'confirmed']
    assert {'prediction_time', 'origin_meaning', 'observation_unit'} <= set(unknown)
    with pytest.raises(protocol.ProtocolError) as error:
        apply(db, {'model': 'linear-all'}, 'm1')
    assert error.value.code == 'blocked' and 'Prediction time' in str(error.value)
    with pytest.raises(protocol.ProtocolError):
        apply(db, {'model': 'random-forest'}, 'm0')
    protocol.confirm_fact(db, 'prediction_time', 'confirm')
    s = protocol.status(db)
    assert s['blocked'] == {} and s['pending_event_id'] == 'm1'
    applied = protocol.apply(db, 'm1', s['revision'], s['context_hash'])
    result = applied['application']['result']
    assert result['result_id'] == 'linear-all' and result['new_fits'] == 0 and result['display']['mae_mpg'].endswith('mpg')
    assert not {'alerts', 'false_alarms', 'threshold'} & set(result['metrics'])
    begun = protocol.assistant_begin(db, {'exchange_id': 'initial-m1-model', 'kind': 'initial', 'activity': 'compare', 'subject': 'applied',
                                          'context_hash': applied['context_hash'], 'expected_application_event_id': 'm1'})
    ctx = json.dumps(begun['context'], ensure_ascii=False)
    assert '"unit": "mpg"' in ctx and 'Bank' not in ctx and 'subscription' not in ctx and 'threshold' not in ctx and 'contacts' not in ctx
    assert begun['context']['project']['problem_type'] == 'regression'


def test_model_inference_never_confirms_and_no_transfer_between_projects(tmp_path):
    protocol.use_project('uci-auto-mpg-v1')
    mpg = tmp_path / 'mpg.sqlite'
    protocol.confirm_fact(mpg, 'prediction_time', 'confirm')
    protocol.explain(mpg, 'Prediction time is confirmed.', source='chat_tool')
    protocol.confirm_fact(mpg, 'origin_meaning', 'reject')
    facts = {f['id']: f for f in protocol.status(mpg)['facts']}
    assert facts['prediction_time']['status'] == 'confirmed' and facts['origin_meaning']['status'] == 'unknown'
    assert facts['observation_unit']['status'] == 'proposed'
    protocol.use_project('uci-bank-marketing-v1')
    bank = tmp_path / 'bank.sqlite'
    s = protocol.status(bank)
    assert s['project_id'] == 'uci-bank-marketing-v1' and all(f['confirmation'] is None for f in s['facts'])
    with pytest.raises(protocol.ProtocolError):
        protocol.confirm_fact(bank, 'origin_meaning', 'confirm')


def test_dataset_change_marks_results_stale_and_keeps_unaffected_confirmations(tree, tmp_path):
    protocol.use_project('uci-auto-mpg-v1', tree)
    db = tmp_path / 'mpg.sqlite'
    protocol.confirm_fact(db, 'prediction_time', 'confirm')
    protocol.confirm_fact(db, 'observation_unit', 'confirm')
    applied = apply(db, {'model': 'linear-all'}, 'm1')
    before = applied['context_hash']
    # Editing a title invalidates no calculation.
    edit(tree / 'auto-mpg/project.json', lambda p: p.update(title='Auto MPG · renamed'))
    protocol.use_project('uci-auto-mpg-v1', tree)
    assert protocol.status(db)['context_hash'] == before and protocol.status(db)['application']['current']
    with (tree / 'auto-mpg/data/auto-mpg.data').open('a') as data:
        data.write('30.0   4   100.0      80.00      2000.      15.0   82  3        "voiture ajoutee"\n')
    bundle = protocol.use_project('uci-auto-mpg-v1', tree)
    assert bundle['dataset_changed'] and all(r['status'] == 'stale' for r in bundle['results']['results'])
    s = protocol.status(db)
    assert s['context_hash'] != before and s['application']['current'] is False and 'review' in s
    facts = {f['id']: f for f in s['facts']}
    assert facts['prediction_time']['status'] == 'confirmed'
    assert facts['observation_unit']['needs_review'] and facts['observation_unit']['status'] == 'proposed'
    # L'historique reste consultable.
    assert protocol.dispatch(db, {'action': 'export'})['export']['applications'][0]['event_id'] == 'm1'
