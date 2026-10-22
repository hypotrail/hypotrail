"""Split and training-partition EDA (plan WP2.2, §7 ``test_eda``).

Every flow runs on the committed Bank case **and** on the synthetic case, whose
generating truth (``truth.json``, never shown to an agent) is an independent oracle.
Expected counts are recomputed here from the raw file with the ``csv`` module and the
split's own row keys, not with the engine's code. Studies live in ``tmp_path``.
"""
from __future__ import annotations

import csv
import json
import math
import re
from pathlib import Path

import pytest

from mlkit.study import activities as act, case as c, data as dt, eda, executions as ex, read

import flowkit as fk
from flowkit import Flow

FRAMEWORK = Path(__file__).resolve().parents[2]
STUDY_PKG = FRAMEWORK / 'mlkit' / 'study'


@pytest.fixture(scope='module')
def synthetic_full(tmp_path_factory):
    return fk.make_case(tmp_path_factory.mktemp('synthetic'), n_rows=4000)


@pytest.fixture(scope='module')
def cases(synthetic_full):
    return {'bank': fk.BANK, 'synthetic': synthetic_full['case'].parent}


@pytest.fixture(scope='module')
def prepared(tmp_path_factory, cases):
    return {name: fk.prepare(path, tmp_path_factory.mktemp(name) / 'study', upto='split')
            for name, path in cases.items()}


@pytest.fixture(params=['bank', 'synthetic'])
def flow(request, tmp_path, prepared, cases):
    f = Flow(fk.clone(prepared[request.param], tmp_path / 'study'), cases[request.param])
    f.name = request.param
    return f


def _raw(case_dir):
    """``{row_key: {column: text}}`` from the raw file, independently of the engine."""
    case = c.load_case(case_dir)
    with open(case.dataset_path, newline='', encoding=case.dataset['encoding']) as handle:
        reader = csv.reader(handle, delimiter=case.dataset['sep'])
        header = next(reader)
        return case, {f'L{i}': dict(zip(header, row)) for i, row in enumerate(reader, start=2)}


def _train_keys(study):
    s = read.open(study)
    entry = s.current('split')
    return [k for k in s.blob(entry['blobs']['train']).decode().splitlines() if k]


def test_split_matches_the_decision_and_the_known_partition_sizes(flow):
    values = read.open(flow.study).current('split')['output']['values']
    train, validation = values['partitions']['train'], values['partitions']['validation']
    case, raw = _raw(flow.case_dir)
    # ADR 0006: the split divides the development rows; the sealed final test is not split.
    final = set(fk.partition_keys(flow.study, 'final_test'))
    development = [k for k in raw if k not in final]
    assert final and set(fk.partition_keys(flow.study, 'development')) == set(development)
    assert values['n_rows'] == len(development) == train['n_rows'] + validation['n_rows']
    assert validation['n_rows'] == math.ceil(0.3 * len(development))   # rounds up
    if flow.name == 'bank':     # 4,521 rows less the 904 sealed (v0.1: 3164 and 1357)
        assert (train['n_rows'], validation['n_rows']) == (2531, 1086)


def test_target_rate_on_training_rows(flow):
    values = flow.run('eda.target_rate')['values']
    case, raw = _raw(flow.case_dir)
    train = _train_keys(flow.study)
    positives = sum(raw[k][case.target_column] == str(case.positive_label) for k in train)
    assert (values['n_rows'], values['n_positive']) == (len(train), positives)
    assert values['rate'] == pytest.approx(positives / len(train))
    if flow.name == 'bank':
        assert (values['n_positive'], values['n_rows']) == (292, 2531)   # v0.1: 365, 3164


def test_special_values_and_their_co_occurrence(flow, synthetic_full):
    values = flow.run('eda.special_values')['values']
    case, raw = _raw(flow.case_dir)
    train = set(_train_keys(flow.study))
    declared = [s for s in case.document['special_values']
                if case.variables[s['column']]['role'] == 'feature']
    assert [(s['column'], s['value']) for s in values['special_values']] == \
        [(s['column'], s['value']) for s in declared]
    for item in values['special_values']:
        expected = sum(raw[k][item['column']] == str(item['value']) for k in train)
        assert item['n_rows'] == expected, item
    pairs = {(p['a']['column'], p['b']['column']): p for p in values['co_occurrence']}
    if flow.name == 'bank':
        p = pairs[('pdays', 'poutcome')]
        assert (p['n_a'], p['n_b'], p['n_both'], p['same_rows']) == (2068, 2068, 2068, True)   # v0.1: 2608
        assert not pairs[('contact', 'poutcome')]['same_rows']
    else:
        truth = json.loads(synthetic_full['truth'].read_text())['sentinel']
        a, b = list(truth['columns'])
        p = pairs[(a, b)]
        expected = len(set(truth['row_keys']) & train)
        assert (p['n_a'], p['n_b'], p['n_both'], p['same_rows']) == (expected,) * 3 + (True,)


def test_rate_by_gives_rates_with_denominators_and_flags_small_groups(flow):
    case = c.load_case(flow.case_dir)
    categorical = next(v['name'] for v in case.document['variables']
                       if v['role'] == 'feature' and v['type'] == 'category')
    values = flow.run('eda.rate_by', '--column', categorical)['values']
    overall = flow.run('eda.target_rate')['values']
    groups = values['groups']
    assert sum(g['n_rows'] for g in groups) == overall['n_rows']
    assert sum(g['n_positive'] for g in groups) == overall['n_positive']
    for g in groups:
        assert g['rate'] == pytest.approx(g['n_positive'] / g['n_rows'])
        assert g['small_count'] is (g['n_rows'] < eda.MIN_GROUP_ROWS)
    assert len(values['warnings']) == sum(g['small_count'] for g in groups)
    if flow.name == 'bank':
        unknown = next(g for g in groups if g['value'] == 'unknown (special value)')
        assert unknown['n_rows'] == 19 and unknown['small_count'] is True   # v0.1: 26


def test_rate_by_bins_a_numeric_column_and_keeps_its_special_value_apart(flow):
    case = c.load_case(flow.case_dir)
    special = next(s for s in case.document['special_values']
                   if case.variables[s['column']]['type'] in ('integer', 'numeric'))
    values = flow.run('eda.rate_by', '--column', special['column'])['values']
    assert values['binned'] is True
    group = next(g for g in values['groups'] if g['value'] == f'{special["value"]} (special value)')
    pairs = flow.run('eda.special_values')['values']['special_values']
    assert group['n_rows'] == next(p['n_rows'] for p in pairs if p['column'] == special['column'])
    assert sum(g['n_rows'] for g in values['groups']) == values['n_rows']


def test_rate_by_refuses_the_target_and_unknown_columns(flow):
    case = c.load_case(flow.case_dir)
    for column in (case.target_column, 'no_such_column'):
        payload = flow.run('eda.rate_by', '--column', column, expect=2)
        assert payload['error']['code'] == 'invalid_arguments'
    assert flow.run('eda.rate_by', expect=2)['error']['code'] == 'invalid_arguments'


def test_rate_by_has_one_slot_per_column(flow):
    """Exploring a second column never replaces the first (contract §8.1, §8.5)."""
    from mlkit.study import dependencies as dep, render_html, view as view_model
    case = c.load_case(flow.case_dir)
    first, second = [v['name'] for v in case.document['variables']
                     if v['role'] == 'feature'][:2]
    a = flow.run('eda.rate_by', '--column', first)
    b = flow.run('eda.rate_by', '--column', second)
    assert a['result']['slot'] == f'eda.rate_by:{first}'
    assert b['result']['slot'] == f'eda.rate_by:{second}'
    state = flow.state()
    assert state['current'][f'eda.rate_by:{first}'] == a['result_id']
    assert state['current'][f'eda.rate_by:{second}'] == b['result_id']
    assert 'eda.rate_by' not in state['current']
    entry = read.open(flow.study).result(a['result_id'])
    assert entry['activity'] == 'eda.rate_by' and entry['params'] == {'column': first}
    # the same request on the same column is already current; nothing is computed
    again = flow.run('eda.rate_by', '--column', first)
    assert again['status'] == 'already_current' and again['result_id'] == a['result_id']
    # both are shown with the training EDA step of the report, each with its column
    v = view_model.build(flow.study)
    slots = render_html.slots_of_step('train_eda', v['results'])
    assert {f'eda.rate_by:{first}', f'eda.rate_by:{second}'} <= set(slots)
    page, consumed = render_html.build(v)
    assert a['result_id'] in consumed and b['result_id'] in consumed
    assert f'data-slot="eda.rate_by:{second}" data-state="current"' in page
    # a code change of eda.rate_by reaches every per-column slot
    eff = dep.effects(state, 'code_fingerprint', {'activity': 'eda.rate_by', 'fingerprint': 'a'},
                      {'activity': 'eda.rate_by', 'fingerprint': 'b'})
    assert eff['re_eda'] == sorted([f'eda.rate_by:{first}', f'eda.rate_by:{second}'])


def test_eda_records_train_eda_exposure_on_training_rows_only(flow):
    before = len(fk.exposure_records(flow.study))
    runs = [flow.run('eda.target_rate'), flow.run('eda.special_values')]
    new = fk.exposure_records(flow.study)[before:]
    train = set(_train_keys(flow.study))
    s = read.open(flow.study)
    assert [(r['purpose'], r['partition'], r['result_id']) for r in new] == [
        ('train_eda', 'train', p['result_id']) for p in runs]
    for r in new:
        assert set(s.blob(r['row_keys']).decode().split()) == train
    summary = s.exposure_summary()
    assert summary['by_partition']['train']['train_eda'] == len(train)
    assert summary['validation_rows_used_for_selection'] == 0


def test_no_validation_row_is_read_during_eda(flow, monkeypatch):
    """Probe: validation rows are poisoned and every row access is recorded.

    The poison sets every validation row to the positive label and to every declared
    special value. EDA that read one validation row would change its counts.
    """
    case = c.load_case(flow.case_dir)
    probe = Flow(fk.clone(flow.study, flow.study.parent / 'probe'), flow.case_dir, prefix='probe')
    s = read.open(flow.study)
    validation = s.blob(s.current('split')['blobs']['validation']).decode().split()
    train = set(_train_keys(flow.study))
    column = case.document['special_values'][-1]['column']
    activities = (('eda.target_rate', {}), ('eda.special_values', {}),
                  ('eda.rate_by', {'column': column}))
    clean = {}
    for activity, options in activities:
        args = ('--column', options['column']) if options else ()
        clean[activity] = flow.run(activity, *args)['values']

    real_load, real_rows, accessed = dt.load_dataset, act.rows, []

    def poisoned(case_, **kwargs):
        dataset = real_load(case_, **kwargs)
        frame = dataset.frame
        frame.loc[validation, case_.target_column] = case_.positive_label
        for sv in case_.document['special_values']:
            frame.loc[validation, sv['column']] = sv['value']
        return dataset

    def recording(dataset, keys):
        keys = list(keys)
        accessed.append(keys)
        return real_rows(dataset, keys)

    monkeypatch.setattr(dt, 'load_dataset', poisoned)
    monkeypatch.setattr(act, 'rows', recording)
    for activity, options in activities:
        out = ex.run(probe.study, activity, options, request_id=f'probe-{activity}',
                     expected_revision=probe.rev()).payload
        assert out['status'] == 'promoted'
        assert out['values'] == clean[activity], activity
    assert len(accessed) == len(activities)
    assert all(set(keys) == train for keys in accessed)


def test_eda_is_refused_before_the_split_result(tmp_path, cases):
    flow = Flow(tmp_path / 'study', cases['synthetic'])
    flow.init()
    flow.pauses()                                       # split decided but not computed
    for activity in ('eda.target_rate', 'eda.special_values'):
        payload = flow.run(activity, expect=2)
        assert payload['error']['code'] == 'precondition_missing'
        assert {'requirement': 'result_current', 'slot': 'split',
                'detail': 'Split the data before exploring or fitting it.'} in \
            payload['error']['details']['missing']
    assert [r['purpose'] for r in fk.exposure_records(flow.study)] == \
        ['structural_inspection', 'labelled_preview_available', 'sealed']


def test_eda_on_a_stale_split_is_refused_and_a_late_eda_is_not_promoted(flow):
    def meanwhile(plan):
        flow.decide('split', {**fk.SPLIT, 'seed': fk.SPLIT['seed'] + 1})

    outcome = ex.run(flow.study, 'eda.target_rate', {}, request_id='late-eda',
                     expected_revision=flow.rev(), hooks={'after_reserve': meanwhile})
    assert outcome.payload['status'] == 'late_not_promoted'
    assert 'precondition_missing' in outcome.payload['result']['reason']
    assert 'eda.target_rate' not in flow.state()['current']
    payload = flow.run('eda.special_values', expect=2)
    assert payload['error']['code'] == 'precondition_missing'


def test_a_split_change_keeps_eda_exposure_and_makes_eda_stale(flow):
    first = flow.run('eda.target_rate')
    explored = read.open(flow.study).exposure_summary()['by_purpose']['train_eda']
    flow.decide('split', {**fk.SPLIT, 'seed': 11})
    state = flow.state()
    assert first['result_id'] in state['stale']
    flow.run('split')
    after = read.open(flow.study)
    assert after.exposure_summary()['by_purpose']['train_eda'] == explored
    overlap = after.current('split')['output']['values']['overlap']
    assert overlap['previously_exposed']['validation']['train_eda'] > 0   # explored, now validation
    second = flow.run('eda.target_rate')
    assert second['status'] == 'promoted' and second['result_id'] != first['result_id']


def test_the_engine_names_no_dataset():
    """No column, label, or dataset name of either case appears in the engine."""
    names = set()
    for case_dir in (fk.BANK,):
        case = c.load_case(case_dir)
        names |= {v['name'] for v in case.document['variables'] if '_' in v['name']
                  or v['name'] in ('pdays', 'poutcome', 'duration', 'campaign', 'balance')}
    names |= {'bank', 'quillmere', 'member_age', 'home_branch', 'membership_days',
              'fines_outstanding', 'desk_followups', 'holds_open', 'visit_band',
              'days_since_last_lapse', 'last_lapse_reason', 'reminders_sent',
              'last_reminder_weekday', 'renewed', 'lapsed', 'subscription', 'deposit',
              # Auto MPG and the regression variant of the synthetic case (M3).
              'mpg', 'car_name', 'model_year', 'horsepower', 'displacement', 'cylinders',
              'monthly_loans', 'floor_area', 'staff_count', 'opening_hours', 'branch_type',
              'survey_score', 'heating_cost', 'returns_logged', 'site_ref',
              # The scikit-learn cases (M3 generality): WDBC and diabetes.
              'wdbc', 'diagnosis', 'malignant', 'benign', 'diabetes', 'progression', 'bmi',
              'breast', 'cancer', 'tumour', 'nuclei', 'cholesterol', 'triglycerides'}
    for case_dir in (fk.WDBC, fk.DIABETES):      # the committed adapters; data not needed
        case = c.load_case(case_dir, verify_data=False)
        names |= {v['name'] for v in case.document['variables'] if '_' in v['name']}
    pattern = re.compile(r'\b(' + '|'.join(sorted(map(re.escape, names))) + r')\b', re.I)
    found = []
    for path in sorted(STUDY_PKG.rglob('*.py')):
        for i, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if pattern.search(line):
                found.append(f'{path.name}:{i}: {line.strip()}')
    assert not found, '\n'.join(found)
