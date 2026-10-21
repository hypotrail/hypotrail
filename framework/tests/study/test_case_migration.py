"""Explicit migration from companion project.json files to case.yaml (WP0.4).

The committed use-case files are only read. Unit cases of the mapping table are built
in ``tmp_path``.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path

import pandas as pd
import pytest
import yaml

from mlkit.study import case as c
from mlkit.study import migrate as m

REPO = Path(__file__).resolve().parents[3]
CASES = {'bank': REPO / 'use-cases/bank-marketing', 'auto': REPO / 'use-cases/auto-mpg'}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _committed(which):
    folder = CASES[which]
    return c.load_case(folder), yaml.safe_load((folder / 'case.yaml').read_text(encoding='utf-8'))


def _statuses(node, path=''):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == 'status':
                yield path, value
            yield from _statuses(value, f'{path}.{key}')
    elif isinstance(node, list):
        for i, item in enumerate(node):
            yield from _statuses(item, f'{path}[{i}]')


# --- committed cases -----------------------------------------------------------------------

@pytest.mark.parametrize('which', sorted(CASES))
def test_committed_case_has_zero_confirmed_and_only_epistemic_statuses(which):
    folder = CASES[which]
    project = json.loads((folder / 'project.json').read_text(encoding='utf-8'))
    assert sum(1 for _, s in _statuses(project) if s == 'confirmed') > 0   # the source has some
    text = (folder / 'case.yaml').read_text(encoding='utf-8')
    assert 'confirmed' not in text.lower()
    _, doc = _committed(which)
    statuses = list(_statuses(doc))
    assert statuses and all(s in c.EPISTEMIC_STATUSES for _, s in statuses), statuses
    assert c.confirmation_claims(doc) == []


@pytest.mark.parametrize('which', sorted(CASES))
def test_committed_case_is_a_fresh_migration_of_untouched_sources(which):
    folder = CASES[which]
    before = {name: _sha(folder / name) for name in ('project.json', 'results.json')}
    text = m.render(m.from_companion_project(folder))
    assert text == (folder / 'case.yaml').read_text(encoding='utf-8')
    assert {name: _sha(folder / name) for name in before} == before
    _, doc = _committed(which)
    assert doc['migration']['from'] == 'project.json'
    assert doc['migration']['from_sha256'] == before['project.json']
    assert doc['migration']['supplement_sha256'] == _sha(folder / 'case-supplement.yaml')
    assert doc['migration']['tool'] == 'mlkit.study.migrate'
    assert doc['migration']['tool_version'] == m.TOOL_VERSION


def _data_columns(case: c.Case) -> list[str]:
    if not case.dataset['header']:
        return list(pd.read_csv(case.dataset_path, sep=case.read_sep, header=None,
                                quotechar=case.dataset['quotechar'], nrows=1).columns.map(
                                    lambda i: case.column_names[i]))
    with open(case.dataset_path, encoding='utf-8', newline='') as handle:
        return next(csv.reader(handle, delimiter=case.dataset['sep'],
                               quotechar=case.dataset['quotechar']))


@pytest.mark.parametrize('which', sorted(CASES))
def test_every_column_has_an_entry_and_undescribed_columns_have_unknown_availability(which):
    case, doc = _committed(which)
    assert _data_columns(case) == case.column_names
    frame = pd.read_csv(case.dataset_path, sep=case.read_sep,
                        header=0 if case.dataset['header'] else None,
                        names=None if case.dataset['header'] else case.column_names,
                        quotechar=case.dataset['quotechar'],
                        na_values=case.dataset.get('na_values'), keep_default_na=False)
    assert len(frame.columns) == doc['dataset']['columns'] and len(frame) == doc['dataset']['rows']
    described = {v['name'] for v in json.loads(
        (CASES[which] / 'project.json').read_text(encoding='utf-8'))['variables']}
    for v in doc['variables']:
        assert v['availability']['value'] in c.AVAILABILITY_VALUES
        if v['name'] not in described:
            assert v['availability'] == {
                'value': 'unknown', 'status': 'unknown',
                'source': 'Availability at prediction time is not documented'}
            # v0.2a (WP-A1): the statement names no tutorial file; the rule log keeps it.
            assert f'variables.{v["name"]}: not described in project.json: status and ' \
                   'availability unknown' in doc['migration']['rules']


@pytest.mark.parametrize('which', sorted(CASES))
def test_availability_is_never_a_documented_fact_except_not_available_with_a_citation(which):
    _, doc = _committed(which)
    documented = [v['name'] for v in doc['variables']
                  if v['availability']['status'] == 'documented_fact']
    assert documented == (['duration'] if which == 'bank' else [])


def test_bank_duration_is_not_available_as_a_documented_fact_citing_bank_names():
    case, _ = _committed('bank')
    duration = case.variables['duration']
    assert duration['availability']['value'] == 'not_available'
    assert duration['availability']['status'] == 'documented_fact'
    cite = re.search(r'data/bank-names\.txt:(\d+),(\d+)', duration['availability']['source'])
    lines = (CASES['bank'] / 'data/bank-names.txt').read_text(encoding='utf-8').splitlines()
    assert 'last contact of the current campaign' in lines[int(cite.group(1)) - 1]
    assert 'duration' in lines[int(cite.group(2)) - 1]


def test_bank_last_contact_variables_say_so_and_tutorial_choices_are_assumptions():
    case, doc = _committed('bank')
    for name in ('day', 'month', 'contact'):
        assert 'last contact of the current campaign' in case.variables[name]['description']
        assert case.variables[name]['availability']['status'] == 'unknown'
    assert 'including the last contact' in case.variables['campaign']['description']
    facts = {f['id']: f for f in doc['facts']}
    for fact in ('prediction_time', 'intended_use', 'decision'):
        assert facts[fact]['status'] == 'scenario_assumption'
    assert facts['target']['status'] == 'documented_fact'
    assert case.positive_label == 'yes' and case.task == 'binary'
    assert case.read_sep == ';' and case.row_key(2) == 'L2'
    assert c.unsupported_capabilities(case) == []
    by_line = {v['name']: v['availability'] for v in doc['variables']}
    assert by_line['balance']['status'] == 'scenario_assumption'   # was "UCI documentation"


def test_bank_structural_observations_hold():
    case, doc = _committed('bank')
    frame = pd.read_csv(case.dataset_path, sep=';')
    assert doc['structure']['duplicates'] == {
        'value': int(frame.duplicated().sum()), 'status': 'observed',
        'source': 'Structural inspection of data/bank.csv: no exact duplicate rows'}
    assert case.time_column is None and case.group_column is None
    sentinels = {(s['column'], s['value']) for s in doc['special_values']}
    assert ('pdays', -1) in sentinels and ('poutcome', 'unknown') in sentinels


def test_auto_mpg_case_is_supported_as_regression_with_the_grouped_split_named():
    """M3: regression with an integer time column is supported; the declared group column
    is accepted with the missing grouped split named, never assumed."""
    case, doc = _committed('auto')
    assert case.task == 'regression' and case.positive_label is None
    assert case.target_unit == 'mpg'
    assert case.time_column == 'model_year' and case.variables['model_year']['type'] == 'integer'
    assert c.unsupported_capabilities(case) == []
    assert c.require_supported(case) is case
    assert [(x['capability'], x['column']) for x in c.limitations(case)] == [
        ('grouped split (v0.2)', 'car_name')]
    assert case.row_key(1) == 'L1'                      # no header: the first row is line 1



def test_auto_mpg_structural_observations_hold():
    case, doc = _committed('auto')
    raw = pd.read_csv(case.dataset_path, sep=case.read_sep, header=None,
                      names=case.column_names, quotechar='"', dtype=str, keep_default_na=False)
    assert raw['car_name'].nunique() == 305 and len(raw) == 398
    assert '305 distinct car names' in doc['structure']['group_column']['source']
    assert int((raw['horsepower'] == '?').sum()) == 6
    assert doc['structure']['duplicates']['value'] == int(raw.duplicated().sum()) == 0
    assert case.variables['origin']['role'] == 'feature'


# --- mapping table on temporary projects -------------------------------------------------

def _project(folder: Path, *, variables=None, facts=None, problem_type='binary_classification',
             supplement=None, rows=4) -> Path:
    data = folder / 'data'
    data.mkdir(parents=True)
    lines = ['a;b;c;target'] + [f'{i};x{i % 2};{i * 1.5};{"yes" if i % 2 else "no"}'
                                for i in range(rows)]
    (data / 'table.csv').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    (data / 'table.names').write_text('1. a: first\n2. b: second\n3. c: third\n', encoding='utf-8')

    def var(name, status, source, avail, role='feature', type_='integer'):
        return {'name': name, 'label': name, 'description': f'{name} described', 'type': type_,
                'unit': None, 'role': role, 'available_at_prediction': avail,
                'special_values': [], 'status': status, 'source': source}

    project = {
        'schema': 'hypotrail.project/1', 'id': 'tmp-case', 'title': 'Temporary',
        'description': 'Temporary project.', 'problem_type': problem_type,
        'dataset': {'path': 'data/table.csv', 'sha256': _sha(data / 'table.csv'), 'rows': rows,
                    'provenance': {}},
        'facts': facts if facts is not None else [
            {'id': 'tutorial', 'value': 'v', 'status': 'confirmed', 'source': 'Tutorial scenario'},
            {'id': 'documented', 'value': 'v', 'status': 'confirmed', 'source': 'table.names'},
            {'id': 'proposal', 'value': 'v', 'status': 'proposed', 'source': 'Inspection'},
            {'id': 'open', 'value': 'v', 'status': 'unknown', 'source': 'Nobody'},
        ],
        'variables': variables if variables is not None else [
            var('a', 'confirmed', 'UCI documentation', 'yes'),
            var('b', 'proposed', 'Inspection', 'unknown', type_='category'),
            var('target', 'confirmed', 'table.names', 'no', role='target', type_='binary'),
        ],
    }
    (folder / 'project.json').write_text(json.dumps(project), encoding='utf-8')
    sup = {'schema': m.SUPPLEMENT_SCHEMA, 'dataset': {'sep': ';'},
           'target': {'positive_label': 'yes'}} if supplement is None else supplement
    if sup:
        (folder / 'case-supplement.yaml').write_text(yaml.safe_dump(sup), encoding='utf-8')
    return folder


def test_mapping_table_for_statuses_and_availability(tmp_path):
    folder = _project(tmp_path / 'p')
    before = _sha(folder / 'project.json')
    doc = m.from_companion_project(folder / 'project.json')
    assert _sha(folder / 'project.json') == before
    facts = {f['id']: f['status'] for f in doc['facts']}
    assert facts == {'tutorial': 'scenario_assumption', 'documented': 'documented_fact',
                     'proposal': 'scenario_assumption', 'open': 'unknown'}
    v = {x['name']: x for x in doc['variables']}
    assert [x['name'] for x in doc['variables']] == ['a', 'b', 'c', 'target']
    assert v['a']['status'] == 'documented_fact'
    assert v['a']['availability']['value'] == 'available_at_prediction'
    assert v['a']['availability']['status'] == 'scenario_assumption'
    assert v['b']['status'] == 'scenario_assumption'
    assert v['b']['availability'] == {'value': 'unknown', 'status': 'unknown',
                                      'source': 'Availability at prediction time is not '
                                                'documented'}
    assert v['c']['status'] == 'unknown' and v['c']['type'] == 'numeric'
    assert v['c']['availability']['value'] == 'unknown'
    assert v['target']['availability'] == {
        'value': 'not_available', 'status': 'scenario_assumption',
        'source': 'Teaching scenario assumption; not established by the dataset documentation'}
    assert 'confirmed' not in m.render(doc).lower()
    c.check_document(doc)


@pytest.mark.parametrize('change, message', [
    (lambda p: p['facts'].append({'id': 'x', 'value': 'v', 'status': 'accepted', 'source': 's'}),
     'unknown companion status'),
    (lambda p: p['variables'][0].__setitem__('available_at_prediction', 'maybe'),
     'unknown companion availability'),
    (lambda p: p['variables'][0].__setitem__('name', 'zzz'), 'absent from the data'),
    (lambda p: p.__setitem__('problem_type', 'ranking'), 'Unsupported companion problem_type'),
    (lambda p: p['facts'][0].__setitem__('value', 'Has {{x:count}} rows'), 'placeholders'),
    (lambda p: p['dataset'].__setitem__('sha256', '0' * 64), 'differs from project.json'),
])
def test_migration_refuses_instead_of_guessing(tmp_path, change, message):
    folder = _project(tmp_path / 'p')
    project = json.loads((folder / 'project.json').read_text())
    change(project)
    (folder / 'project.json').write_text(json.dumps(project))
    with pytest.raises(m.MigrationError, match=message):
        m.from_companion_project(folder)


@pytest.mark.parametrize('supplement, message', [
    ({'schema': m.SUPPLEMENT_SCHEMA, 'dataset': {'sep': ';'}}, 'positive_label'),
    ({'schema': m.SUPPLEMENT_SCHEMA, 'dataset': {'sep': ';'}, 'target': {'positive_label': 'yes'},
      'variables': {'a': {'availability': {'value': 'available_at_prediction',
                                           'status': 'documented_fact',
                                           'source': 'data/table.names:1'}}}},
     'only for not_available'),
    ({'schema': m.SUPPLEMENT_SCHEMA, 'dataset': {'sep': ';'}, 'target': {'positive_label': 'yes'},
      'variables': {'a': {'availability': {'value': 'not_available',
                                           'status': 'documented_fact',
                                           'source': 'The documentation'}}}},
     'must cite an existing use-case file'),
    ({'schema': m.SUPPLEMENT_SCHEMA, 'dataset': {'sep': ';'}, 'target': {'positive_label': 'yes'},
      'variables': {'a': {'availability': {'value': 'not_available',
                                           'status': 'documented_fact',
                                           'source': 'data/table.names:99'}}}},
     'must cite an existing use-case file'),
    ({'schema': m.SUPPLEMENT_SCHEMA, 'dataset': {'sep': ';'}, 'target': {'positive_label': 'yes'},
      'facts': {'tutorial': {'status': 'confirmed'}}}, 'never records a confirmation'),
    ({'schema': m.SUPPLEMENT_SCHEMA, 'dataset': {'sep': ';'}, 'target': {'positive_label': 'yes'},
      'variables': {'nope': {'status': 'unknown'}}}, 'absent from the data'),
])
def test_supplement_rules(tmp_path, supplement, message):
    folder = _project(tmp_path / 'p', supplement=supplement)
    with pytest.raises(m.MigrationError, match=message):
        m.from_companion_project(folder)


def test_supplement_may_document_not_available_with_a_line_citation(tmp_path):
    folder = _project(tmp_path / 'p', supplement={
        'schema': m.SUPPLEMENT_SCHEMA, 'dataset': {'sep': ';'},
        'target': {'positive_label': 'yes'},
        'variables': {'c': {'availability': {'value': 'not_available', 'status': 'documented_fact',
                                             'source': 'data/table.names:3'}}}})
    doc = m.from_companion_project(folder)
    c_var = next(v for v in doc['variables'] if v['name'] == 'c')
    assert c_var['availability']['status'] == 'documented_fact'
    assert 'variables.c: supplement sets availability' in doc['migration']['rules']


def test_cli_check_reports_drift_without_writing(tmp_path, capsys):
    folder = _project(tmp_path / 'p')
    assert m.main([str(folder), '--check']) == 1
    assert not (folder / 'case.yaml').exists()
    assert m.main([str(folder), '--write']) == 0
    assert m.main([str(folder), '--check']) == 0
    assert c.load_case(folder).id == 'tmp-case'


def test_check_layout_flags_confirmation_and_dataset_mismatch(tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location('check_layout_under_test',
                                                  REPO / 'scripts/check_layout.py')
    layout = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(layout)
    good = _project(tmp_path / 'use-cases' / 'good')
    m.main([str(good), '--write'])
    bad = _project(tmp_path / 'use-cases' / 'bad')
    m.main([str(bad), '--write'])
    text = (bad / 'case.yaml').read_text(encoding='utf-8')
    (bad / 'case.yaml').write_text(text.replace('status: unknown', 'status: Confirmed', 1),
                                   encoding='utf-8')
    with open(bad / 'data/table.csv', 'a', encoding='utf-8') as handle:
        handle.write('9;x1;1.0;yes\n')
    monkeypatch.setattr(layout, 'ROOT', tmp_path)
    errors = []
    assert layout.check_cases(errors) == 2
    assert errors == ['Case file declares a confirmation: bad/case.yaml',
                      'Case dataset fingerprint mismatch: bad']
