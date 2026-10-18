"""Check training scope, absence of fitting, and safe column rendering."""
import json
import numpy as np
import pytest
import yaml
from mlkit import classical, config, discover, pilot, task_contract, tutorial


def setup(root):
    tutorial.create(root)
    return task_contract.load(root)


def test_train_only_no_raw_rows_no_fit(tmp_path, monkeypatch):
    root = tmp_path / 'project'
    spec = setup(root)
    df, y = classical.dataset(root, spec)
    tr, va = classical.split(df, y, spec)
    df.loc[va, 'signal_a'] = 999999
    df.to_csv(root / spec['data']['path'], index=False)
    def forbidden(*args, **kwargs):
        raise AssertionError('No training during discovery')
    monkeypatch.setattr(classical, 'pipeline', forbidden)
    result = discover.report(root)
    col = next(c for c in result['columns'] if c['name'] == 'signal_a')
    assert col['stats']['summary']['max'] < 999999
    assert result['train_rows'] == len(tr) and result['validation_rows'] == len(va)
    assert not (root / '.osml/classical/fits.jsonl').exists()
    excluded = next(c for c in result['columns'] if c['name'] == 'incident_confirme_apres_decision')
    assert excluded['role'] == 'excluded from the model' and 'stats' not in excluded
    assert 'stats' not in next(c for c in result['columns'] if c['role'] == 'id')
    assert (root / 'notebooks/discovery.py').exists()


def test_html_escapes_column_injection_and_category_values(tmp_path):
    root = tmp_path / 'project'
    spec = setup(root)
    df, _ = classical.dataset(root, spec)
    name = '<script>alert(1)</script>'
    df[name] = 'PRIVATE_EMAIL@example.org'
    spec['data']['features'].append(name)
    df.to_csv(root / spec['data']['path'], index=False)
    (root / 'project.yaml').write_text(yaml.safe_dump({'schema_version': 1, 'spec': spec}))
    discover.report(root)
    doc = (root / 'reports/dataset-discovery.html').read_text()
    assert name not in doc and '&lt;script&gt;' in doc
    assert 'PRIVATE_EMAIL' not in doc
    assert 'PRIVATE_EMAIL' not in (root / 'reports/dataset-discovery.json').read_text()


def test_missing_constant_and_deterministic_fingerprints(tmp_path):
    root = tmp_path / 'project'
    spec = setup(root)
    df, _ = classical.dataset(root, spec)
    df['signal_a'] = np.nan
    df['signal_b'] = 7
    df.to_csv(root / spec['data']['path'], index=False)
    first = discover.report(root)
    assert first == discover.report(root)
    stats = {c['name']: c.get('stats') for c in first['columns']}
    assert stats['signal_a']['missing_share'] == 1
    assert stats['signal_b']['summary']['min'] == stats['signal_b']['summary']['max'] == 7
    spec['task']['purpose'] = 'New usage'
    (root / 'project.yaml').write_text(yaml.safe_dump({'schema_version': 1, 'spec': spec}))
    assert discover.report(root)['context'] != first['context']


def test_discovery_precedes_training_and_blocks_on_failure(tmp_path, monkeypatch):
    root = tmp_path / 'project'
    setup(root)
    monkeypatch.setattr(config, 'ROOT', root)
    state = pilot.init('auto')
    assert pilot.remaining(state)[0] == ('discovery', ['discover'])
    state['steps'] = {key: {'returncode': 0} for key in ['classical-plan', 'classical-profile']}
    state['steps']['discovery'] = {'returncode': 1}
    assert 'Data discovery failed' in pilot.step(state)


@pytest.mark.parametrize('kind', ['regression', 'multiclass', 'ranking', 'clustering'])
def test_discovery_all_classical_tasks(tmp_path, kind):
    from test_classical import prepare
    prepare(tmp_path, kind)
    result = discover.report(tmp_path)
    assert result['task'] == kind and result['train_rows'] > 0
    assert (result['target'] is None) == (kind == 'clustering')
