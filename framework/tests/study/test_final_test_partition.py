"""The sealed final test (ADR 0006): assigned at ``init``, never read by an activity.

* the assignment: share, stratification, determinism, temporal order, recorded seed;
* the guard: no final-test row key reaches any activity input (instrumented loader),
  any registered result (row-key blobs, predictions), or any exposure record except the
  ``sealed`` one;
* the final test's schema check: counts only, a failure refuses ``init`` without a value;
* a legacy study (no partition) still loads, runs on every row, and shows "no final test".

Expected counts are recomputed from the raw file with the ``csv`` module. Studies and
cases live in ``tmp_path``.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import pytest

from mlkit.study import activities as act, case as c, cli, data as dt, partition, read
from mlkit.study import registry, state as st, store as sto

import flowkit as fk
from flowkit import Flow
from test_perturbations import Variant, Walk


def _raw(case_dir):
    case = c.load_case(case_dir)
    with open(case.dataset_path, newline='', encoding=case.dataset['encoding']) as handle:
        reader = csv.reader(handle, delimiter=case.dataset['sep'])
        header = next(reader)
        return case, {f'L{i}': dict(zip(header, row)) for i, row in enumerate(reader, start=2)}


def _half_up(n, fraction=partition.DEFAULT_FRACTION):
    return int(math.floor(n * fraction + 0.5))


@pytest.fixture(scope='module')
def bank_study(tmp_path_factory):
    flow = Flow(tmp_path_factory.mktemp('bank') / 'study', fk.BANK)
    payload = flow.init()
    return flow, payload


# --- assignment ---------------------------------------------------------------------------

def test_bank_final_test_is_a_stratified_fifth_sealed_at_init(bank_study):
    flow, payload = bank_study
    case, raw = _raw(fk.BANK)
    final = fk.partition_keys(flow.study, 'final_test')
    development = fk.partition_keys(flow.study, 'development')
    assert set(final).isdisjoint(development)
    assert set(final) | set(development) == set(raw)
    by_label = {}
    for key, row in raw.items():
        by_label.setdefault(row[case.target_column], []).append(key)
    for label, keys in by_label.items():            # the same share of each label
        assert sum(k in set(final) for k in keys) == _half_up(len(keys)), label
    assert (len(final), len(development)) == (904, 3617)      # 104 of 521 yes, 800 of 4000 no
    record = flow.state()['partition']
    assert record['status'] == 'sealed' and record['method'] == 'stratified'
    assert (record['fraction'], record['seed'], record['stratified_on']) == (0.2, 0, 'y')
    assert record['schema_check']['status'] == 'pass'
    assert payload['final_test'] == {'status': 'sealed', 'rows': 904, 'method': 'stratified',
                                     'fraction': 0.2, 'development_rows': 3617,
                                     'schema_check': 'pass'}
    assert payload['structural_exposure']['n_rows'] == 3617


def test_assignment_is_deterministic(bank_study, tmp_path):
    flow, _ = bank_study
    again = Flow(tmp_path / 'again', fk.BANK)
    again.init()
    for part in ('development', 'final_test'):
        assert again.state()['partition'][part] == flow.state()['partition'][part]


def test_status_and_summary_report_the_sealed_final_test(bank_study):
    flow, _ = bank_study
    expected = {'status': 'sealed', 'rows': 904, 'method': 'stratified', 'fraction': 0.2,
                'development_rows': 3617, 'schema_check': 'pass'}
    assert flow.view()['final_test'] == expected
    summary = flow.call('status', '--summary', '--study', flow.study)
    assert summary['final_test'] == expected


def test_exposure_records_development_inspection_and_sealed_final_test(bank_study):
    flow, _ = bank_study
    records = fk.exposure_records(flow.study)
    assert [(r['purpose'], r['partition'], r['n_rows']) for r in records] == [
        ('structural_inspection', 'development', 3617), ('sealed', 'final_test', 904)]
    s = read.open(flow.study)
    assert set(s.blob(records[0]['row_keys']).decode().split()) == \
        set(fk.partition_keys(flow.study, 'development'))
    summary = s.exposure_summary()
    assert summary['rows_exposed'] == 3617              # sealed rows are not looked at
    assert summary['by_purpose']['sealed'] == 904


def test_regression_final_test_is_stratified_on_target_quantile_bins(tmp_path):
    case_dir = fk.make_case(tmp_path / 'case', task='regression', n_rows=500)['case'].parent
    flow = Flow(tmp_path / 'study', case_dir)
    flow.init()
    record = flow.state()['partition']
    assert (record['method'], record['bins'], record['stratified_on']) == \
        ('quantile_stratified', partition.QUANTILE_BINS, c.load_case(case_dir).target_column)
    assert record['final_test']['n_rows'] + record['development']['n_rows'] == 500
    assert abs(record['final_test']['n_rows'] - 100) <= partition.QUANTILE_BINS


def _ordered(tmp_path, by='line', direction='ascending', n_rows=200):
    variant = Variant(tmp_path, n_rows=n_rows)
    variant.doc['order'] = {'by': by, 'direction': direction, 'status': 'scenario_assumption',
                            'source': 'Perturbation test: the extract is in time order.'}
    return variant


def test_declared_line_order_seals_the_last_rows(tmp_path):
    case_dir = _ordered(tmp_path).write()
    flow = Flow(tmp_path / 'study', case_dir)
    flow.init()
    record = flow.state()['partition']
    assert record['method'] == 'temporal' and record['seed'] is None
    assert record['order'] == {'by': 'line', 'direction': 'ascending', 'ties_at_cut': 0}
    final = sorted(fk.partition_keys(flow.study, 'final_test'), key=lambda k: int(k[1:]))
    assert final == [f'L{i}' for i in range(2 + 200 - 40, 2 + 200)]


def test_declared_column_order_descending_seals_the_smallest_values(tmp_path):
    variant = _ordered(tmp_path, by='rank_order', direction='descending')
    variant.add('rank_order', 'integer', [str(1000 - n) for n in range(len(variant.rows))])
    flow = Flow(tmp_path / 'study', variant.write())
    flow.init()
    case, raw = _raw(variant.out)
    final = set(fk.partition_keys(flow.study, 'final_test'))
    smallest = sorted(raw, key=lambda k: int(raw[k]['rank_order']))[:40]
    assert final == set(smallest)


@pytest.mark.parametrize('order, path', [
    ({'by': 'nowhere', 'direction': 'ascending'}, 'order.by'),
    ({'by': 'line', 'direction': 'sideways'}, 'order.direction'),
])
def test_an_invalid_order_is_refused(tmp_path, order, path):
    variant = Variant(tmp_path, n_rows=150)
    variant.doc['order'] = {**order, 'status': 'scenario_assumption', 'source': 'test'}
    with pytest.raises(c.CaseError) as err:
        variant.write()
    assert path in {p['path'] for p in err.value.problems}


# --- the final test's schema check ------------------------------------------------------

def _numeric_column(variant):
    return next(v['name'] for v in variant.doc['variables']
                if v['type'] in ('numeric', 'integer') and v['role'] == 'feature')


def test_a_bad_cell_in_the_final_test_refuses_init_with_counts_only(tmp_path):
    variant = _ordered(tmp_path)
    column = _numeric_column(variant)
    n = len(variant.rows)
    variant.cells(column, lambda i, v: 'SECRET-TOKEN' if i == n - 1 else v)
    out = cli.run(['init', '--case', str(variant.write()), '--study', str(tmp_path / 'study')])
    assert out.exit_code == 2
    error = out.payload['error']
    assert error['code'] == 'invalid_case'
    text = json.dumps(error)
    assert 'SECRET-TOKEN' not in text and f'L{n + 1}' not in text
    assert any(p['partition'] == 'final_test' and p['path'].startswith('variables[')
               and '1 sealed final-test rows' in p['problem']
               for p in error['problems'])
    assert not (tmp_path / 'study' / '.hypotrail' / 'state.json').exists()


def test_the_same_bad_cell_in_the_development_rows_is_named_with_its_row(tmp_path):
    variant = _ordered(tmp_path)
    column = _numeric_column(variant)
    variant.cells(column, lambda i, v: 'oops' if i == 0 else v)
    out = cli.run(['init', '--case', str(variant.write()), '--study', str(tmp_path / 'study')])
    assert out.payload['error']['code'] == 'invalid_case'
    assert "'oops'" in json.dumps(out.payload['error']) and 'L2' in json.dumps(out.payload['error'])


def test_a_missing_target_in_the_final_test_is_an_unsupported_capability(tmp_path):
    variant = _ordered(tmp_path)
    variant.doc['dataset']['na_values'] = ['NA']
    target = variant.doc['target']['column']
    n = len(variant.rows)
    variant.cells(target, lambda i, v: 'NA' if i == n - 1 else v)
    out = cli.run(['init', '--case', str(variant.write()), '--study', str(tmp_path / 'study')])
    reason = out.payload['error']['details']['reasons'][0]
    assert reason['capability'] == dt.CAPABILITY_MISSING_TARGET
    assert (reason['partition'], reason['rows']) == ('final_test', 1)


# --- the guard: no final-test row reaches an activity or a result -------------------------

def _instrument(monkeypatch, final: set):
    """Every dataset load after ``init`` must name its rows and return development rows."""
    seen = {'loads': 0, 'rows': 0}
    real_load, real_rows = dt.load_dataset, act.rows

    def load(case_, **kwargs):
        assert kwargs.get('rows') is not None, 'an activity read the dataset without its rows'
        dataset = real_load(case_, **kwargs)
        assert final.isdisjoint(dataset.frame.index)
        assert final.isdisjoint(dataset.index.keys)
        seen['loads'] += 1
        return dataset

    def rows(dataset, keys):
        keys = list(keys)
        assert final.isdisjoint(keys)
        seen['rows'] += 1
        return real_rows(dataset, keys)

    monkeypatch.setattr(dt, 'load_dataset', load)
    monkeypatch.setattr(act, 'rows', rows)
    return seen


def _assert_no_final_row_in_records(study: Path, final: set):
    s = read.open(study)
    store = sto.StudyStore(study)
    for record in s.exposure_records():
        keys = set(s.blob(record['row_keys']).decode().split())
        if record['purpose'] == 'sealed':
            assert keys == final
        else:
            assert final.isdisjoint(keys), record['purpose']
    entries = list(registry.entries(store))
    assert entries
    for entry in entries:
        for name, sha in entry['blobs'].items():
            if name in act.SPLIT_BLOBS:
                assert final.isdisjoint(s.blob(sha).decode().split()), entry['activity']
            elif name == act.PREDICTIONS:
                assert final.isdisjoint(act.read_predictions(store, entry['result_id'])['row_keys'])
        assert entry['inputs']['development'] == partition.inputs(s.state)


@pytest.mark.parametrize('task', ['binary', 'regression'])
def test_no_final_test_row_reaches_any_activity_or_result(tmp_path, monkeypatch, task):
    case_dir = fk.make_case(tmp_path / 'case', task=task, n_rows=600)['case'].parent
    walk = Walk(case_dir, tmp_path / 'study')
    walk.call('init', 'init', '--case', case_dir, '--study', walk.study)
    final = set(fk.partition_keys(walk.study, 'final_test'))
    assert len(final) == 120 or task == 'regression'
    seen = _instrument(monkeypatch, final)
    case = c.load_case(case_dir)
    regression = task == 'regression'
    walk.decide('prediction_time', 'when the record is created, before the outcome')
    walk.decide('feature_availability', fk.availability(case_dir))
    walk.decide('split', {'method': 'random' if regression else 'stratified_random',
                          'validation_fraction': 0.3, 'seed': 7})
    # WP-A4: the success criterion and the default preprocessing, before any model.
    walk.decide('success_criterion', fk.criterion(case.task))
    walk.decide('preprocessing', {'missing': 'none', 'rare_category_min_rows': 0, 'caps': {},
                                  'log_transform': []})
    parts = walk.run('split')['values']
    assert parts['n_rows'] == 600 - len(final)
    feature = next(v['name'] for v in case.document['variables'] if v['role'] == 'feature')
    for activity in (('eda.target_summary',) if regression else ('eda.target_rate',)):
        walk.run(activity)
    walk.run('eda.special_values')
    walk.run('eda.mean_by' if regression else 'eda.rate_by', '--column', feature)
    walk.run('eda.distribution', '--column', feature)
    walk.run('fit.baseline')
    walk.run('fit.linear' if regression else 'fit.logistic')
    if regression:
        walk.run('evaluate.regression')
    else:
        walk.run('policy.evaluate', '--rule', 'threshold:0.2', '--rule', 'capacity:20')
    for args in (('status', '--study', walk.study), ('evidence', '--study', walk.study),
                 ('export', '--study', walk.study), ('check', '--study', walk.study)):
        cli.run([str(a) for a in args])
    # split, 4 EDA, 2 fits (+ the regression evaluation, which reads its time column);
    # the policy evaluation reads predictions only.
    assert seen['loads'] == (8 if regression else 7) and seen['rows'] >= 6
    _assert_no_final_row_in_records(walk.study, final)


# --- legacy studies (no partition) ------------------------------------------------------

def test_a_legacy_study_without_partition_loads_runs_and_shows_no_final_test(tmp_path):
    case_dir = fk.make_case(tmp_path / 'case', n_rows=300)['case'].parent
    store = sto.StudyStore(tmp_path / 'study')
    store.create(st.initial_state(c.load_case(case_dir)))       # the v0.1 shape
    flow = Flow(tmp_path / 'study', case_dir)
    assert 'partition' not in flow.state()
    absent = {'status': 'absent', 'rows': None, 'method': None, 'fraction': None,
              'development_rows': None, 'schema_check': None}
    assert flow.view()['final_test'] == absent
    assert flow.call('status', '--summary', '--study', flow.study)['final_test'] == absent
    flow.pauses()
    split = flow.run('split')
    assert split['values']['n_rows'] == 300                     # every row is development
    entry = read.open(flow.study).current('split')
    assert 'development' not in entry['inputs'] and entry['partition'] == 'all'
    assert fk.exposure_records(flow.study)[-1]['partition'] == 'all'
