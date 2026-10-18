"""Case contract ``hypotrail.case/1``: validation, refusals, and capability checks (WP0.4).

Cases come from the synthetic generator (framework/tests/fixtures/synthetic) and are
written to ``tmp_path``; committed use cases are only read or copied.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import shutil
from pathlib import Path

import pytest
import yaml

from mlkit.study import case as c

TESTS = Path(__file__).resolve().parents[1]
REPO = TESTS.parents[1]
_spec = importlib.util.spec_from_file_location('synthetic_make_case_for_study',
                                               TESTS / 'fixtures/synthetic/make_case.py')
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
make_case = _module.make_case


def _doc(paths) -> dict:
    return yaml.safe_load(paths['case'].read_text(encoding='utf-8'))


def _write(paths, doc) -> Path:
    paths['case'].write_text(yaml.safe_dump(doc, sort_keys=False), encoding='utf-8')
    return paths['case']


def _refusal(path, code) -> c.CaseError:
    with pytest.raises(c.CaseError) as info:
        c.load_case(path)
    assert info.value.code == code, info.value.to_dict()
    return info.value


@pytest.fixture
def synthetic(tmp_path):
    return make_case(tmp_path / 'case', n_rows=300)


def test_default_synthetic_case_loads_and_is_supported(synthetic):
    case = c.load_case(synthetic['case'].parent)
    assert case.task == 'binary' and case.positive_label == 'renewed'
    assert case.target_column == 'outcome' and case.read_sep == ';'
    assert case.column_names[-1] == 'outcome'
    assert case.dataset_path == synthetic['data'].resolve()
    assert c.unsupported_capabilities(case) == []
    assert c.require_supported(case) is case
    assert case.row_key(2) == 'L2'
    with pytest.raises(ValueError):
        case.row_key(1)          # line 1 is the header


@pytest.mark.parametrize('options, expected', [
    ({'groups': True}, [('structure.group_column', 'member_ref')]),
    ({'time': True}, [('structure.time_column', 'cycle_start_date')]),
    ({'groups': True, 'time': True}, [('structure.time_column', 'cycle_start_date'),
                                      ('structure.group_column', 'member_ref')]),
])
def test_declared_time_or_group_column_is_refused_with_its_capability(tmp_path, options, expected):
    paths = make_case(tmp_path / 'case', n_rows=200, **options)
    case = c.load_case(paths['case'])        # a valid case; only the capability is missing
    reasons = c.unsupported_capabilities(case)
    assert [(r['path'], r['column']) for r in reasons] == expected
    assert {r['code'] for r in reasons} == {'unsupported_capability'}
    assert {r['capability'] for r in reasons} == {c.CAPABILITY_STRUCTURED_SPLIT}
    assert c.CAPABILITY_STRUCTURED_SPLIT == 'temporal/grouped split (v0.2)'
    with pytest.raises(c.CaseError) as info:
        c.require_supported(case)
    refusal = info.value.to_dict()
    assert refusal['code'] == 'unsupported_capability'
    assert 'temporal/grouped split (v0.2)' in refusal['message']
    assert refusal['details']['reasons'] == reasons
    assert all('does not fall back' in r['reason'] for r in reasons)


def test_regression_task_is_refused_with_its_capability(synthetic):
    doc = _doc(synthetic)
    doc['task'] = 'regression'
    doc['target']['positive_label'] = None
    case = c.load_case(_write(synthetic, doc))
    reasons = c.unsupported_capabilities(case)
    assert [(r['capability'], r['path']) for r in reasons] == [('regression study (v0.2)', 'task')]
    with pytest.raises(c.CaseError) as info:
        c.require_supported(case)
    assert info.value.code == 'unsupported_capability'
    assert 'regression study (v0.2)' in info.value.message


def test_dataset_sha_mismatch_is_refused(synthetic):
    data = synthetic['data']
    data.write_bytes(data.read_bytes().replace(b'renewed', b'lapsed!', 1))
    refusal = _refusal(synthetic['case'], 'dataset_changed')
    assert refusal.details['declared_sha256'] == _doc(synthetic)['dataset']['sha256']
    assert refusal.details['actual_sha256'] == hashlib.sha256(data.read_bytes()).hexdigest()
    # Without data verification the document itself is still a valid case.
    assert c.load_case(synthetic['case'], verify_data=False).id == _doc(synthetic)['id']


def test_committed_case_with_changed_dataset_is_refused(tmp_path):
    folder = tmp_path / 'copy'
    shutil.copytree(REPO / 'use-cases/bank-marketing', folder, symlinks=False,
                    ignore=shutil.ignore_patterns('*.html', 'predictions.csv'))
    assert c.load_case(folder).dataset['rows'] == 4521
    with open(folder / 'data/bank.csv', 'ab') as handle:
        handle.write(b'\n')
    assert _refusal(folder, 'dataset_changed').details['path'] == 'data/bank.csv'


def test_missing_dataset_and_escaping_path_are_refused(synthetic):
    synthetic['data'].unlink()
    _refusal(synthetic['case'], 'dataset_missing')
    doc = _doc(synthetic)
    doc['dataset']['path'] = '../data.csv'
    error = _refusal(_write(synthetic, doc), 'invalid_case')
    assert {'path': 'dataset.path',
            'problem': 'must be a relative path inside the case directory'} in error.problems


@pytest.mark.parametrize('mutate', [
    lambda d: d['variables'][0].__setitem__('status', 'confirmed'),
    lambda d: d['variables'][0]['availability'].__setitem__('status', 'Confirmed'),
    lambda d: d['facts'][0].__setitem__('status', 'confirmed'),
    lambda d: d['structure']['time_column'].__setitem__('status', 'confirmed'),
    lambda d: d.__setitem__('migration', {'confirmation': {'by': 'tutorial'}}),
    lambda d: d['variables'][-1]['special_values'].append(
        {'value': 'x', 'meaning': 'y', 'status': 'confirmed', 'source': 'z'}),
])
def test_any_confirmed_status_anywhere_is_refused(synthetic, mutate):
    doc = _doc(synthetic)
    mutate(doc)
    error = _refusal(_write(synthetic, doc), 'confirmed_status_forbidden')
    assert error.problems and all('not allowed in a case' in p['problem'] for p in error.problems)


def _set(path, value):
    def mutate(doc):
        node = doc
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value
    return mutate


@pytest.mark.parametrize('mutate, path', [
    (_set(('schema',), 'hypotrail.case/2'), 'schema'),
    (_set(('unexpected',), 1), 'unexpected'),
    (_set(('task',), 'multiclass'), 'task'),
    (_set(('variables', 0, 'status'), 'proposed'), 'variables[0].status'),
    (_set(('variables', 0, 'availability', 'value'), 'yes'), 'variables[0].availability.value'),
    (_set(('variables', 0, 'availability', 'status'), 'unknown'), 'variables[0].availability'),
    (_set(('variables', 0, 'role'), 'excluded'), 'variables[0].role'),
    (_set(('target', 'positive_label'), None), 'target.positive_label'),
    (_set(('target', 'column'), 'missing'), 'target.column'),
    (_set(('row_key', 'rule'), 'row_number'), 'row_key.rule'),
    (_set(('dataset', 'sha256'), 'ABC'), 'dataset.sha256'),
    (_set(('dataset', 'columns'), 3), 'dataset.columns'),
    (_set(('special_values',), []), 'special_values'),
    (_set(('structure', 'time_column', 'value'), 'member_age'), 'structure.time_column'),
    (_set(('structure', 'duplicates', 'value'), -1), 'structure.duplicates.value'),
])
def test_schema_violations_are_reported_with_their_path(synthetic, mutate, path):
    doc = _doc(synthetic)
    mutate(doc)
    error = _refusal(_write(synthetic, doc), 'invalid_case')
    assert path in [p['path'] for p in error.problems], error.problems


def test_rows_and_header_must_match_the_file(synthetic):
    doc = _doc(synthetic)
    _write(synthetic, {**doc, 'dataset': {**doc['dataset'], 'rows': doc['dataset']['rows'] + 1}})
    assert _refusal(synthetic['case'], 'invalid_case').problems[0]['path'] == 'dataset.rows'
    swapped = copy.deepcopy(doc)
    swapped['variables'][0], swapped['variables'][1] = swapped['variables'][1], swapped['variables'][0]
    swapped['special_values'] = [{'column': v['name'], **sv} for v in swapped['variables']
                                 for sv in v['special_values']]
    assert _refusal(_write(synthetic, swapped), 'invalid_case').problems[0]['path'] == 'variables'


def test_refusal_is_structured(synthetic):
    doc = _doc(synthetic)
    doc['variables'][0]['status'] = 'confirmed'
    _write(synthetic, doc)
    with pytest.raises(c.CaseError) as info:
        c.load_case(synthetic['case'])
    out = info.value.to_dict()
    assert set(out) == {'code', 'message', 'problems'}
    assert out['problems'] == [{'path': 'variables[0].status',
                                'problem': 'value "confirmed" is not allowed in a case'}]
