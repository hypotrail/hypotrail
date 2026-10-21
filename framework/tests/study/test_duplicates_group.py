"""Duplicate records as entity groups (v0.2b, WP-B3).

Without a declaration, identical records are refused (``duplicate records (v0.2)``,
``test_data.py``). A case that declares ``duplicates: {policy: group}`` is accepted, and a
group of identical records is never divided: not by the sealed final test, not by the
split, not by the folds of the single-feature signal. Exposure still counts rows; the data
card and ``eda.quality`` report the groups.

Studies live in temporary directories on synthetic cases.
"""
from __future__ import annotations

import copy

import numpy as np
import pytest
import yaml

from mlkit.study import case as c, data, partition

import flowkit as fk
from flowkit import Flow

FIXTURES = fk.TESTS / 'fixtures' / 'synthetic'
import sys  # noqa: E402
sys.path.insert(0, str(FIXTURES))
from make_case import make_case  # noqa: E402

DECLARATION = {'policy': 'group', 'status': 'scenario_assumption',
               'source': 'Test: identical records are one entity recorded more than once'}


def _grouped_case(tmp_path, *, duplicates=60, order=False, n_rows=1500):
    paths = make_case(tmp_path / 'case', n_rows=n_rows, duplicates=duplicates, seed=7)
    doc = yaml.safe_load(paths['case'].read_text())
    doc['duplicates'] = dict(DECLARATION)
    if order:
        doc['order'] = {'by': 'line', 'direction': 'ascending', 'status': 'scenario_assumption',
                        'source': 'Test: rows written in time order'}
    paths['case'].write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))
    return paths


def _groups_of(case_dir):
    case = c.load_case(case_dir)
    return data.entity_groups(data.row_index(case))


def _divided(groups, side_a, side_b) -> int:
    a, b = {groups[k] for k in side_a}, {groups[k] for k in side_b}
    return len(a & b)


# --- the contract ------------------------------------------------------------------------

@pytest.mark.parametrize('value, path', [
    ({'policy': 'drop', 'status': 'observed', 'source': 'x'}, 'duplicates.policy'),
    ({'policy': 'group', 'status': 'confirmed_by_me', 'source': 'x'}, 'duplicates.status'),
    ({'policy': 'group', 'status': 'observed'}, 'duplicates.source'),
])
def test_a_duplicates_declaration_is_validated(tmp_path, value, path):
    doc = yaml.safe_load(_grouped_case(tmp_path)['case'].read_text())
    doc['duplicates'] = value
    assert path in {p['path'] for p in c.validate(doc)}


def test_without_a_declaration_identical_records_stay_refused(tmp_path):
    paths = make_case(tmp_path / 'case', n_rows=300, duplicates=4, seed=7)
    with pytest.raises(c.CaseError) as info:
        data.row_index(c.load_case(paths['case']))
    [reason] = info.value.details['reasons']
    assert reason['capability'] == data.CAPABILITY_DUPLICATES
    assert 'policy: group' in reason['reason']


def test_entity_groups_name_the_first_identical_record(tmp_path):
    paths = _grouped_case(tmp_path, duplicates=30)
    index = data.row_index(c.load_case(paths['case']))
    groups = data.entity_groups(index)
    assert set(groups) == set(index.keys)
    for members in data.content_duplicates(index):
        assert {groups[k] for k in members} == {members[0]}
    summary = data.duplicate_summary(c.load_case(paths['case']), index)
    assert summary['policy'] == 'group' and summary['n_extra_rows'] == 30
    assert summary['n_rows'] == sum(len(g) for g in data.content_duplicates(index))


def test_grouped_stratified_draws_the_same_rows_when_every_group_is_one_row():
    keys = [f'L{i}' for i in range(2, 502)]
    strata = [str(i % 3 == 0) for i in range(500)]
    plain = partition._stratified(keys, strata, 0.2, 0)
    grouped = partition.grouped_stratified(keys, strata, {k: k for k in keys}, 0.2, 0)
    assert grouped == plain


# --- the final test, the split, the folds ------------------------------------------------

def test_init_seals_whole_groups_and_counts_rows(tmp_path):
    paths = _grouped_case(tmp_path)
    flow = Flow(tmp_path / 'study', paths['case'].parent)
    init = flow.init()
    record = flow.state()['partition']
    assert record['groups']['policy'] == 'group' and record['groups']['moved_rows'] == 0
    assert record['groups']['n_rows'] > record['groups']['n_groups'] > 0
    assert 'entity group' in record['implementation']
    groups = _groups_of(paths['case'].parent)
    dev = fk.partition_keys(flow.study, 'development')
    final = fk.partition_keys(flow.study, 'final_test')
    assert _divided(groups, dev, final) == 0
    assert len(dev) + len(final) == len(groups)
    assert abs(len(final) - round(0.2 * len(groups))) <= 3
    assert init['structural_exposure']['n_rows'] == len(dev)      # exposure counts rows


def test_the_split_and_the_signal_folds_keep_groups_whole(tmp_path):
    paths = _grouped_case(tmp_path)
    flow = Flow(tmp_path / 'study', paths['case'].parent)
    flow.init()
    flow.pauses()
    result = flow.run('split')
    values = result['values']
    assert values['duplicates']['divided_groups'] == 0
    assert values['duplicates']['policy'] == 'group'
    assert 'grouped_stratified' in values['implementation']
    from mlkit.study import activities, read
    from mlkit.study.store import StudyStore
    parts = activities.split_keys(StudyStore(flow.study), result['result_id'])
    groups = _groups_of(paths['case'].parent)
    assert _divided(groups, parts['train'], parts['validation']) == 0
    share = len(parts['validation']) / (len(parts['train']) + len(parts['validation']))
    assert abs(share - 0.3) < 0.01
    signal = flow.run('eda.single_feature_signal')['values']
    assert signal['grouped_folds'].startswith('identical records kept in one fold')
    assert read.open(flow.study).state['current']['eda.single_feature_signal']


def test_the_data_card_and_quality_report_the_groups(tmp_path):
    paths = _grouped_case(tmp_path)
    flow = Flow(tmp_path / 'study', paths['case'].parent)
    flow.init()
    card = flow.call('data', '--study', flow.study)
    dup = card['development']['duplicates']
    assert dup['policy'] == 'group' and dup['n_groups'] > 0 and dup['audience'] == 'junior'
    assert 'one side of every split' in dup['line']
    quality = flow.run('eda.quality')['values']
    assert quality['duplicates']['records']['n_groups'] == dup['n_groups']
    assert quality['duplicates']['n_rows'] >= dup['n_extra_rows']


def test_a_temporal_final_test_moves_a_divided_group_to_its_earliest_side(tmp_path):
    paths = _grouped_case(tmp_path, order=True, duplicates=80)
    case = c.load_case(paths['case'])
    index = data.row_index(case)
    frame = data.read_frame(case, index)
    assigned = partition.assign(case, index, frame)
    groups = data.entity_groups(index)
    assert _divided(groups, assigned['development'], assigned['final_test']) == 0
    plain_doc = copy.deepcopy(case.document)
    del plain_doc['duplicates']
    plain = c.Case(case.path, plain_doc)
    cut = partition._temporal(plain, frame, list(index.keys), 0.2)[0]
    moved = len(set(cut) ^ set(assigned['final_test']))
    assert assigned['record']['groups']['moved_rows'] == moved
    # every moved row went to the side of its group's earliest record (development here)
    earliest = {}
    for k in index.keys:
        earliest.setdefault(groups[k], k)
    for k in set(cut) - set(assigned['final_test']):
        assert earliest[groups[k]] in assigned['development']
    assert np.all([k in assigned['development'] for k in set(cut) - set(assigned['final_test'])])
