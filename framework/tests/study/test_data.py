"""Dataset loading, row keys, and content hashes (plan WP1.2).

Committed datasets (Bank Marketing, Auto MPG) are only read. Modified datasets are
synthetic copies in ``tmp_path``.
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest
import yaml

from mlkit.study import case as c, data

TESTS = Path(__file__).resolve().parents[1]
REPO = TESTS.parents[1]
_spec = importlib.util.spec_from_file_location('synthetic_make_case_for_data',
                                               TESTS / 'fixtures/synthetic/make_case.py')
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
make_case = _module.make_case


@pytest.fixture(scope='module')
def bank():
    return data.load_dataset(c.load_case(REPO / 'use-cases/bank-marketing'))


def test_bank_loads_4521_rows_keyed_by_source_line(bank):
    frame = bank.frame
    assert frame.shape == (4521, 17)
    assert frame.index.name == 'row_key'
    assert frame.index[0] == 'L2' and frame.index[-1] == 'L4522'
    assert frame.index.is_unique and len(bank.index) == 4521
    assert bank.sha256 == bank.case.dataset['sha256']
    assert int((frame['y'] == 'yes').sum()) == 521
    # Only declared na_values are missing: "unknown" stays a category.
    assert int(frame.isna().sum().sum()) == 0
    assert int((frame['poutcome'] == 'unknown').sum()) == 3705
    line = (REPO / 'use-cases/bank-marketing/data/bank.csv').read_text().splitlines()[1]
    assert frame.loc['L2', 'age'] == int(line.split(';')[0])


def test_bank_has_no_content_duplicates(bank):
    assert data.content_duplicates(bank.index) == []
    assert len(set(bank.index.content_hashes)) == 4521


def test_row_keys_are_stable_after_adding_a_derived_column(bank):
    frame = bank.frame.copy()
    keys_before = list(frame.index)
    frame['contacted_before'] = (frame['pdays'] != -1).astype(int)
    assert list(frame.index) == keys_before
    again = data.load_dataset(bank.case)
    assert again.index == bank.index
    assert list(again.frame.columns) == bank.case.column_names


def test_content_hash_ignores_quoting_and_spacing():
    assert data.content_hash(['a', 'b c']) != data.content_hash(['a b', 'c'])
    split = data._whitespace_tokenizer('"')
    assert split('18.0   8\t"chevrolet chevelle malibu"') == ['18.0', '8', 'chevrolet chevelle malibu']
    assert split('1  "say ""hi"""') == ['1', 'say "hi"']


def test_synthetic_case_loads(tmp_path):
    paths = make_case(tmp_path / 'case', n_rows=500)
    ds = data.load_dataset(c.load_case(paths['case']))
    assert ds.frame.shape == (500, 12)
    assert ds.frame.index[0] == 'L2' and ds.frame.index[-1] == 'L501'
    assert int((ds.frame['days_since_last_lapse'] == -1).sum()) > 0
    assert ds.frame['last_lapse_reason'].isna().sum() == 0


def test_changed_dataset_is_refused(tmp_path):
    paths = make_case(tmp_path / 'case', n_rows=200)
    raw = paths['data'].read_bytes()
    paths['data'].write_bytes(raw.replace(b';renewed\n', b';lapsed\n', 1))
    with pytest.raises(c.CaseError) as info:
        data.load_dataset(c.load_case(paths['case'], verify_data=False))
    assert info.value.code == 'dataset_changed'
    assert info.value.details['actual_sha256'] == hashlib.sha256(
        paths['data'].read_bytes()).hexdigest()


def test_content_duplicates_are_refused(tmp_path):
    paths = make_case(tmp_path / 'case', n_rows=200, duplicates=3)
    case = c.load_case(paths['case'])
    assert c.unsupported_capabilities(case) == []     # the case itself does not say
    with pytest.raises(c.CaseError) as info:
        data.load_dataset(case)
    assert info.value.code == 'unsupported_capability'
    [reason] = info.value.details['reasons']
    assert reason['capability'] == data.CAPABILITY_DUPLICATES
    assert reason['duplicate_rows'] == 3 and len(reason['examples']) == 3
    assert all(len(group) == 2 for group in reason['examples'])


def test_a_line_that_is_not_one_record_is_refused(tmp_path):
    paths = make_case(tmp_path / 'case', n_rows=200)
    lines = paths['data'].read_text().split('\n')
    lines[5] = lines[5] + ';extra'
    paths['data'].write_text('\n'.join(lines))
    doc = yaml.safe_load(paths['case'].read_text())
    doc['dataset']['sha256'] = hashlib.sha256(paths['data'].read_bytes()).hexdigest()
    paths['case'].write_text(yaml.safe_dump(doc, sort_keys=False))
    with pytest.raises(c.CaseError) as info:
        data.row_index(c.load_case(paths['case']))
    assert info.value.code == 'invalid_case'
    assert info.value.problems == [{'path': 'L6', 'problem': '13 fields, expected 12'}]


def test_auto_mpg_is_refused_before_reading_data():
    auto = c.load_case(REPO / 'use-cases/auto-mpg')
    with pytest.raises(c.CaseError) as info:
        data.load_dataset(auto)
    assert info.value.code == 'unsupported_capability'
    assert {r['capability'] for r in info.value.details['reasons']} == {
        c.CAPABILITY_REGRESSION, c.CAPABILITY_STRUCTURED_SPLIT}


def test_auto_mpg_structural_reading_without_header():
    """Structural inspection only: whitespace separator, quoted names, '?' missing."""
    auto = data.load_dataset(c.load_case(REPO / 'use-cases/auto-mpg'), supported_only=False)
    assert auto.frame.shape == (398, 9)
    assert auto.frame.index[0] == 'L1' and auto.frame.index[-1] == 'L398'
    assert auto.frame.loc['L1', 'car_name'] == 'chevrolet chevelle malibu'
    assert int(auto.frame['horsepower'].isna().sum()) == 6
