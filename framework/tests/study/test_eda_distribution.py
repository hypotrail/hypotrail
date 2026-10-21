"""``eda.distribution:<column>`` (CLI-CONTRACT-COMPANION §8, C8; WP-E3).

Real cases: the committed Bank case (``age`` numeric, ``pdays`` with its special value,
``job`` categorical) and the committed Auto MPG case (``mpg`` the target, ``model_year``
the time column, discrete on training rows). Expected counts are recomputed from the raw
file with the ``csv`` module and the split's own row keys, not with the engine's code.
Studies live in ``tmp_path``.
"""
from __future__ import annotations

import csv
import math

import pytest

from mlkit.study import case as c, eda, read

import companion_contract as cc
import flowkit as fk

AUTO = fk.REPO / 'use-cases' / 'auto-mpg'
AUTO_CUTOFF = 79


@pytest.fixture(scope='module')
def bank_split(tmp_path_factory):
    return fk.prepare(fk.BANK, tmp_path_factory.mktemp('bank') / 'study', upto='split')


@pytest.fixture
def bank(bank_split, tmp_path):
    return fk.Flow(fk.clone(bank_split, tmp_path / 'study'), fk.BANK, prefix='d')


@pytest.fixture(scope='module')
def auto(tmp_path_factory):
    flow = fk.Flow(tmp_path_factory.mktemp('auto') / 'study', AUTO, prefix='a')
    flow.init()
    flow.pauses(split=False)
    flow.decide('split', {'method': 'ordinal_cutoff', 'column': 'model_year',
                          'cutoff': AUTO_CUTOFF})
    flow.model_decisions()          # WP-A4: success criterion and default preprocessing
    flow.run('split')
    return flow


def _raw(case_dir):
    case = c.load_case(case_dir)
    with open(case.dataset_path, newline='', encoding=case.dataset['encoding']) as handle:
        reader = csv.reader(handle, delimiter=case.dataset['sep'])
        header = next(reader)
        return case, {f'L{i}': dict(zip(header, row)) for i, row in enumerate(reader, start=2)}


def _train_keys(study):
    s = read.open(study)
    return [k for k in s.blob(s.current('split')['blobs']['train']).decode().splitlines() if k]


def _entry(flow, payload):
    return read.open(flow.study).result(payload['result']['result_id'])


def _exposure(flow, payload):
    return [(r['purpose'], r['partition'], r['columns'], r['n_rows'])
            for r in read.open(flow.study).exposure_records()
            if r['result_id'] == payload['result']['result_id']]


def test_bank_age_is_numeric_with_ten_bins_of_training_rows(bank):
    p = bank.run('eda.distribution', '--column', 'age')
    assert p['status'] == 'promoted' and p['result']['slot'] == 'eda.distribution:age'
    entry = _entry(bank, p)
    values = entry['output']['values']
    assert tuple(values) == cc.DISTRIBUTION_VALUE_KEYS
    assert (values['kind'], values['role'], values['type']) == ('numeric', 'feature', 'integer')
    assert entry['partition'] == values['partition'] == 'train'
    case, raw = _raw(fk.BANK)
    train = _train_keys(bank.study)
    ages = sorted(int(raw[k]['age']) for k in train)
    numeric = values['numeric']
    # v0.1: 3164 training rows, before the final test was sealed (ADR 0006)
    assert values['n_rows'] == len(train) == 2531 and values['n_missing'] == 0
    assert values['special_values'] == [] and values['groups'] is None
    assert (numeric['n'], numeric['min'], numeric['max']) == (len(ages), ages[0], ages[-1])
    assert numeric['mean'] == pytest.approx(sum(ages) / len(ages))
    assert numeric['median'] == pytest.approx((ages[len(ages) // 2 - 1] + ages[len(ages) // 2]) / 2)
    assert numeric['n_bins'] == eda.DISTRIBUTION_BINS == 10
    assert numeric['bin_width'] == pytest.approx((ages[-1] - ages[0]) / 10)
    bins = numeric['bins']
    for i, b in enumerate(bins):      # recount every bin from the raw file
        last = i == len(bins) - 1
        expected = sum(b['low'] <= a < b['high'] or (last and a == b['high']) for a in ages)
        assert b['n_rows'] == expected, b
        assert b['share'] == pytest.approx(expected / len(train))
        assert b['closed'] == ('both' if last else 'left')
    assert sum(b['n_rows'] for b in bins) == len(train)
    assert _exposure(bank, p) == [('train_eda', 'train', ['age'], len(train))]
    assert entry['inputs'].get('target') is None          # the outcome is no input
    assert sorted(entry['code']['modules']) == ['mlkit.study.activities', 'mlkit.study.eda']


def test_bank_pdays_counts_its_special_value_apart(bank):
    values = _entry(bank, bank.run('eda.distribution', '--column', 'pdays'))['output']['values']
    case, raw = _raw(fk.BANK)
    train = _train_keys(bank.study)
    special = sum(raw[k]['pdays'] == '-1' for k in train)
    assert [(s['value'], s['n_rows']) for s in values['special_values']] == [(-1, special)]
    assert special == 2068          # v0.1: 2608, before the final test was sealed
    numeric = values['numeric']
    assert numeric['min'] >= 0 and numeric['n'] == len(train) - special
    assert sum(b['n_rows'] for b in numeric['bins']) == values['n_rows'] - values['n_missing'] \
        - special


def test_bank_job_is_categorical_by_descending_count(bank):
    values = _entry(bank, bank.run('eda.distribution', '--column', 'job'))['output']['values']
    assert values['kind'] == 'categorical' and values['numeric'] is None
    case, raw = _raw(fk.BANK)
    train = _train_keys(bank.study)
    counts = {}
    for k in train:
        counts[raw[k]['job']] = counts.get(raw[k]['job'], 0) + 1
    unknown = counts.pop('unknown')            # a declared special value, counted apart
    assert [(s['value'], s['n_rows']) for s in values['special_values']] == [('unknown', unknown)]
    expected = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    assert [(g['value'], g['n_rows']) for g in values['groups']] == expected
    assert values['n_groups'] == len(expected) and values['other'] is None
    for g in values['groups']:
        assert g['small_count'] is (g['n_rows'] < eda.MIN_GROUP_ROWS)


def test_a_distribution_never_reads_the_outcome(bank, monkeypatch):
    seen = []
    original = eda.distribution

    def probe(case, train, column, max_groups=eda.MAX_GROUPS):
        seen.append(list(train.columns))
        return original(case, train, column, max_groups)
    monkeypatch.setattr(eda, 'distribution', probe)
    p = bank.run('eda.distribution', '--column', 'balance')
    assert seen == [['balance']]
    assert _exposure(bank, p)[0][2] == ['balance']


def test_high_cardinality_folds_the_smallest_groups(bank):
    p = bank.run('eda.distribution', '--column', 'job', '--max-groups', '3')
    values = p['values']
    assert values['max_groups'] == 3 and values['n_groups'] == 11
    assert [g['value'] for g in values['groups']][-1] == eda.OTHER_GROUP
    assert len(values['groups']) == 4
    assert values['other']['n_values'] == 8
    assert sum(g['n_rows'] for g in values['groups']) + sum(
        s['n_rows'] for s in values['special_values']) == values['n_rows']
    assert values['warnings'] and 'job has 11 values' in values['warnings'][0]
    nyd = {x['id']: x for x in bank.view()['not_yet_defensible']}
    assert 'eda.distribution:job' in nyd['high_cardinality_grouping']['slots']


def test_refusals_unknown_column_group_column_and_partition_option(bank, tmp_path):
    p = bank.run('eda.distribution', '--column', 'no_such_column', expect=2)
    assert p['error']['code'] == 'invalid_arguments'
    assert 'age' in p['error']['details']['columns'] and 'y' in p['error']['details']['columns']
    assert bank.run('eda.distribution', expect=2)['error']['code'] == 'invalid_arguments'
    # no partition option exists: a validation distribution cannot be asked for
    p = bank.call('run', 'eda.distribution', '--column', 'age', '--partition', 'validation',
                  '--request-id', 'd-part', '--expected-revision', bank.rev(),
                  '--study', bank.study, expect=None)
    assert p['ok'] is False


def test_the_target_is_accepted_and_reads_the_target_only(bank):
    p = bank.run('eda.distribution', '--column', 'y')
    values = p['values']
    assert values['role'] == 'target' and values['kind'] == 'categorical'
    assert sum(g['n_rows'] for g in values['groups']) == values['n_rows']
    assert _exposure(bank, p)[0][2] == ['y']


def test_a_split_change_makes_every_distribution_stale(bank):
    for column in ('age', 'job'):
        bank.run('eda.distribution', '--column', column)
    p = bank.call('decide', 'propose', 'split', '--value-json',
                  '{"method": "stratified_random", "validation_fraction": 0.25, "seed": 7}',
                  '--restatement', 'You decide the split as stated.', '--rationale', 'Another.',
                  '--request-id', bank.rid(), '--expected-revision', bank.rev(),
                  '--study', bank.study)
    bank.call('decide', 'confirm', p['result']['proposal_id'], '--user-words',
              'Yes, I want the split exactly as you stated it', '--request-id', bank.rid(),
              '--expected-revision', bank.rev(), '--study', bank.study)
    results = bank.view()['results']
    for slot in ('eda.distribution:age', 'eda.distribution:job'):
        assert results[slot]['current'] is False, slot


def test_auto_mpg_target_and_discrete_time_column(auto):
    p = auto.run('eda.distribution', '--column', 'mpg')
    values = p['values']
    assert values['role'] == 'target' and values['kind'] == 'numeric'
    assert _exposure(auto, p)[0][:3] == ('train_eda', 'train', ['mpg'])
    summary = auto.run('eda.target_summary')['values']
    for key in ('min', 'q25', 'median', 'q75', 'max', 'mean'):
        assert values['numeric'][key] == pytest.approx(summary[key]), key
    p = auto.run('eda.distribution', '--column', 'model_year')
    values = p['values']
    assert values['role'] == 'time' and values['kind'] == 'discrete'
    years = [g['value'] for g in values['groups']]
    assert years == sorted(years) and years[-1] < AUTO_CUTOFF
    assert all(isinstance(y, int) for y in years)
    assert sum(g['n_rows'] for g in values['groups']) == values['n_rows'] - values['n_missing']
    assert math.isclose(sum(g['share'] for g in values['groups']), 1.0)
