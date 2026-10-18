"""Properties of the synthetic planted-trap case and of its truth file.

Statistical checks compare a realised quantity with the exact expectation recorded in
truth.json. The tolerance is four standard errors computed from the sample size and the
true rates (or, for an AUC, from the Birnbaum-Klose upper bound on its variance,
A(1 - A) / min(n0, n1)). Under the generating model a deviation beyond four standard
errors has a probability of about 6e-5, so a failure points to a generator bug rather
than to sampling noise; and since the generator is seeded, a passing check never flakes.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('synthetic_make_case',
                                               HERE / 'fixtures/synthetic/make_case.py')
make_case_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(make_case_module)
make_case = make_case_module.make_case

EPISTEMIC = {'documented_fact', 'scenario_assumption', 'observed', 'unknown'}
Z = 4.0   # standard errors; see the module docstring


def _load(paths):
    case = yaml.safe_load(paths['case'].read_text(encoding='utf-8'))
    truth = json.loads(paths['truth'].read_text(encoding='utf-8'))
    df = pd.read_csv(paths['data'], sep=case['dataset']['sep'], keep_default_na=False)
    return case, truth, df


def _y(df, case):
    return (df[case['target']['column']] == case['target']['positive_label']).astype(int)


def _auc(score, y):
    ranks = pd.Series(score).rank(method='average').to_numpy()
    n1 = int(y.sum())
    n0 = len(y) - n1
    return (ranks[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0), n0, n1


@pytest.fixture(scope='module')
def default_case(tmp_path_factory):
    return make_case(tmp_path_factory.mktemp('default'))


@pytest.fixture(scope='module')
def full_case(tmp_path_factory):
    return make_case(tmp_path_factory.mktemp('full'), duplicates=30, groups=True, time=True)


def _bytes(paths):
    return {k: p.read_bytes() for k, p in paths.items()}


def test_same_seed_same_bytes_and_different_seed_different_data(tmp_path):
    options = dict(seed=11, n_rows=600, duplicates=7, groups=True, time=True)
    a = _bytes(make_case(tmp_path / 'a', **options))
    b = _bytes(make_case(tmp_path / 'b', **options))
    assert a == b
    c = _bytes(make_case(tmp_path / 'c', **{**options, 'seed': 12}))
    assert c['data'] != a['data'] and c['truth'] != a['truth']


def test_writes_only_the_three_files_into_out_dir(tmp_path):
    out = tmp_path / 'case'
    paths = make_case(out, n_rows=200)
    assert sorted(p.name for p in tmp_path.iterdir()) == ['case']
    assert sorted(p.name for p in out.iterdir()) == ['case.yaml', 'data.csv', 'truth.json']
    assert {p.parent for p in paths.values()} == {out}


@pytest.mark.parametrize('which', ['default_case', 'full_case'])
def test_case_contract_has_no_confirmed_status_anywhere(which, request):
    paths = request.getfixturevalue(which)
    assert 'confirmed' not in paths['case'].read_text(encoding='utf-8').lower()
    case, _, _ = _load(paths)
    assert case['schema'] == 'hypotrail.case/1' and case['task'] == 'binary'

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == 'status':
                    assert value in EPISTEMIC, value
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)
    walk(case)
    for var in case['variables']:
        assert var['status'] in EPISTEMIC
        assert var['availability']['status'] in EPISTEMIC
        assert var['availability']['value'] != 'confirmed'


@pytest.mark.parametrize('which', ['default_case', 'full_case'])
def test_every_column_has_a_dictionary_entry_and_sha_matches(which, request):
    paths = request.getfixturevalue(which)
    case, truth, df = _load(paths)
    assert [v['name'] for v in case['variables']] == list(df.columns) == truth['data']['columns']
    digest = hashlib.sha256(paths['data'].read_bytes()).hexdigest()
    assert case['dataset']['sha256'] == digest == truth['data']['sha256']
    assert case['dataset']['sep'] == ';' and case['dataset']['rows'] == len(df)
    assert case['row_key']['rule'] == 'source_line'
    lines = paths['data'].read_text(encoding='utf-8').split('\n')
    assert lines[-1] == '' and len(lines) - 2 == len(df)       # header + rows + final newline
    assert all(line.count(';') == len(df.columns) - 1 for line in lines[:-1])
    assert '"' not in paths['data'].read_text(encoding='utf-8')
    assert truth['data']['row_keys'] == {'first': 'L2', 'last': f'L{len(df) + 1}'}
    assert case['target'] == {'column': 'outcome', 'positive_label': 'renewed',
                              'negative_label': 'lapsed'}


def test_leakage_column_is_documented_as_recorded_after_outcome(default_case):
    case, truth, _ = _load(default_case)
    leak = next(v for v in case['variables'] if v['name'] == truth['leakage']['column'])
    assert 'after the outcome' in leak['description']
    assert leak['availability'] == {'value': 'not_available', 'status': 'documented_fact',
                                    'source': leak['availability']['source']}
    for name in truth['ambiguous_availability']['last_contact_columns']:
        var = next(v for v in case['variables'] if v['name'] == name)
        assert var['availability']['value'] == 'unknown'
        assert var['availability']['status'] == 'unknown'
    assert next(f for f in case['facts'] if f['id'] == 'prediction_time')['status'] == 'unknown'


@pytest.mark.parametrize('which', ['default_case', 'full_case'])
def test_sentinel_co_occurs_on_exactly_the_same_rows(which, request):
    case, truth, df = _load(request.getfixturevalue(which))
    cols = truth['sentinel']['columns']
    keys = np.array([f'L{i + 2}' for i in range(len(df))])
    masks = [(df[c].astype(str) == str(v)).to_numpy() for c, v in cols.items()]
    assert (masks[0] == masks[1]).all()
    assert list(keys[masks[0]]) == truth['sentinel']['row_keys']
    assert 0 < truth['sentinel']['count'] == masks[0].sum() < len(df)
    documented = {(s['column'], str(s['value'])) for s in case['special_values']}
    assert {(c, str(v)) for c, v in cols.items()} <= documented


def test_signal_has_the_documented_effect_and_leakage_is_strong(default_case):
    case, truth, df = _load(default_case)
    y = _y(df, case).to_numpy()
    sig = truth['signal']
    s = df[sig['column']].to_numpy()
    n1, n0 = int((s == 1).sum()), int((s == 0).sum())
    observed = y[s == 1].mean() - y[s == 0].mean()
    p1, p0 = sig['rate_if_one'], sig['rate_if_zero']
    se = math.sqrt(p1 * (1 - p1) / n1 + p0 * (1 - p0) / n0)
    assert abs(observed - sig['risk_difference']) <= Z * se
    assert sig['risk_difference'] > Z * se       # the effect is detectable at this size

    leak_auc, m0, m1 = _auc(df[truth['leakage']['column']].to_numpy(), y)
    expected = truth['leakage']['exact_auc']
    assert abs(leak_auc - expected) <= Z * math.sqrt(expected * (1 - expected) / min(m0, m1))
    signal_auc, _, _ = _auc(s, y)
    assert expected > 0.95 and leak_auc > signal_auc + 0.2

    # Reminders stop once a member renews: the "last contact" count depends on the outcome.
    assert truth['ambiguous_availability']['reminders_sent']['depends_on_target'] is True
    assert df.loc[y == 1, 'reminders_sent'].mean() < df.loc[y == 0, 'reminders_sent'].mean()


@pytest.mark.parametrize('rate', [0.05, 0.30])
def test_imbalance_option_is_respected(tmp_path, rate):
    n = 4000
    paths = make_case(tmp_path, n_rows=n, positive_rate=rate)
    case, truth, df = _load(paths)
    observed = _y(df, case).mean()
    assert truth['target']['model_positive_rate'] == pytest.approx(rate, abs=1e-9)
    assert truth['target']['observed_positive_rate'] == pytest.approx(observed, abs=1e-9)
    assert abs(observed - rate) <= Z * math.sqrt(rate * (1 - rate) / n)


def test_discrete_inputs_produce_tied_true_scores(default_case):
    _, truth, df = _load(default_case)
    cols = truth['ties']['columns']
    combos = df[cols].assign(lapsed=df['days_since_last_lapse'] != -1)
    combos = combos.drop(columns='days_since_last_lapse').drop_duplicates()
    assert 1 < truth['ties']['distinct_true_scores'] <= len(combos) <= 16
    assert df[truth['ties']['discrete_feature']].nunique() == 4


def test_reference_split_matches_the_documented_recipe(full_case):
    case, truth, df = _load(full_case)
    ref = truth['reference_split']
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([ref['seed'], ref['stream']])))
    order = np.argsort(rng.random(len(df)), kind='stable')
    n_train = int(round(ref['train_fraction'] * len(df)))
    y = _y(df, case).to_numpy()
    train = order[:n_train]
    assert ref['train_rows'] == n_train and ref['validation_rows'] == len(df) - n_train
    assert ref['train_positive'] == y[train].sum()
    assert ref['train_target_rate'] == pytest.approx(y[train].mean(), abs=1e-9)
    in_train = np.zeros(len(df), bool)
    in_train[train] = True
    idx = {f'L{i + 2}': i for i in range(len(df))}
    straddle = sum(in_train[idx[a]] != in_train[idx[b]] for a, b in truth['duplicates']['pairs'])
    assert ref['duplicate_pairs_across_partitions'] == straddle


def test_default_case_has_no_duplicates_groups_or_time(default_case):
    case, truth, df = _load(default_case)
    assert not df.duplicated().any()
    assert truth['duplicates'] == {'enabled': False, 'count': 0, 'pairs': []}
    assert truth['groups'] == {'enabled': False} and truth['time'] == {'enabled': False}
    assert case['structure']['group_column']['value'] is None
    assert case['structure']['time_column']['value'] is None


def test_optional_flags_produce_what_truth_claims(full_case):
    case, truth, df = _load(full_case)
    lines = full_case['data'].read_text(encoding='utf-8').split('\n')

    pairs = truth['duplicates']['pairs']
    assert truth['duplicates']['count'] == len(pairs) == 30
    for a, b in pairs:
        assert lines[int(a[1:]) - 1] == lines[int(b[1:]) - 1]
    claimed = {k for pair in pairs for k in pair}
    dup_mask = df.duplicated(keep=False).to_numpy()
    assert {f'L{i + 2}' for i in np.flatnonzero(dup_mask)} == claimed
    assert truth['data']['distinct_rows'] == len(df.drop_duplicates()) == len(df) - 30

    groups = truth['groups']
    assert case['structure']['group_column']['value'] == groups['column'] == 'member_ref'
    assert df['member_ref'].nunique() == groups['groups']
    sizes = df['member_ref'].value_counts().value_counts()
    assert {str(k): int(v) for k, v in sizes.items()} == groups['size_histogram']
    assert (df.groupby('member_ref')[groups['shared_columns']].nunique() == 1).all().all()
    for ref, keys in groups['members_with_repeats'].items():
        assert set(df.index[df['member_ref'] == ref] + 2) == {int(k[1:]) for k in keys}

    time = truth['time']
    assert case['structure']['time_column']['value'] == time['column'] == 'cycle_start_date'
    dates = pd.to_datetime(df[time['column']], format='%Y-%m-%d')
    assert dates.min().date().isoformat() == time['min']
    assert dates.max().date().isoformat() == time['max']


def test_optional_columns_do_not_change_the_target_draws(tmp_path):
    base = _load(make_case(tmp_path / 'base', n_rows=500))[2]
    timed = _load(make_case(tmp_path / 'timed', n_rows=500, time=True, groups=True))[2]
    assert (base['outcome'] == timed['outcome']).all()
    assert (base['holds_open'] == timed['holds_open']).all()


# Dataset-specific identifiers that must never appear in the generic study engine.
DATASET_NAMES = re.compile(
    r'bank|mpg|pdays|poutcome|quillmere|renewal[-_ ]reminder|desk_followups|days_since_last_lapse'
    r'|last_lapse_reason', re.IGNORECASE)


def test_study_engine_contains_no_dataset_specific_names():
    study = HERE.parent / 'mlkit' / 'study'
    if not study.is_dir():
        pytest.skip('framework/mlkit/study does not exist yet')
    offenders = []
    for path in sorted(study.rglob('*')):
        if path.is_file() and path.suffix in {'.py', '.md', '.json', '.yaml', '.yml', '.txt',
                                              '.html', '.css', '.js', '.jinja', '.tmpl'}:
            for n, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                if DATASET_NAMES.search(line):
                    offenders.append(f'{path.relative_to(study)}:{n}: {line.strip()}')
    assert not offenders, '\n'.join(offenders)
