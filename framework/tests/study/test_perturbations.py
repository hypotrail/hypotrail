"""Synthetic perturbations of a case (M3 generality): complete, or refuse with a named reason.

Each variant rewrites the synthetic case (``fixtures/synthetic/make_case.py``) in a
temporary folder: other column names, another separator, quoted fields, extra columns,
a constant column, a high-cardinality category, missing values, a group column, a date
time column, duplicate rows, extreme class imbalance, a tiny dataset. The same study is
then driven through ``cli.run`` (the CLI code path): init, the three pauses, the split,
training EDA, both fits, the evaluation, the adoption, a proportionate conclusion, and a
``check`` of the deliverables.

Every variant must either **complete** that walkthrough with a clean check and strictly
finite JSON payloads, or be **refused** with a stable error code and, for a missing
capability, the capability's name. A crash (an exception escaping the CLI) or a silent
change of meaning fails the test.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import math
from pathlib import Path

import pytest
import yaml

from mlkit.study import case as c, cli, read

import flowkit as fk

CONCLUSION = ('Keep the baseline for now: the comparison was made on the validation rows used '
              'to choose, so it is optimistic and is not a forecast.')


# --- building a perturbed case ------------------------------------------------------------

class Variant:
    """A case read from the synthetic generator, to be rewritten under ``out``."""

    def __init__(self, tmp: Path, *, task='binary', n_rows=600, positive_rate=0.12,
                 groups=False, time=False, duplicates=0, seed=20261018):
        base = fk.make_case(tmp / 'base', task=task, n_rows=n_rows, groups=groups, time=time,
                            duplicates=duplicates, seed=seed,
                            **({'positive_rate': positive_rate} if task == 'binary' else {}))
        self.out = tmp / 'case'
        self.doc = yaml.safe_load(base['case'].read_text(encoding='utf-8'))
        d = self.doc['dataset']
        with open(base['case'].parent / d['path'], encoding='utf-8', newline='') as handle:
            table = list(csv.reader(handle, delimiter=d['sep']))
        self.columns, self.rows = table[0], table[1:]
        self.sep, self.quoting = d['sep'], csv.QUOTE_MINIMAL

    # column-level edits
    def variable(self, name) -> dict:
        return next(v for v in self.doc['variables'] if v['name'] == name)

    def rename(self, mapping: dict) -> 'Variant':
        for v in self.doc['variables']:
            v['name'] = mapping.get(v['name'], v['name'])
        self.columns = [mapping.get(n, n) for n in self.columns]
        t = self.doc['target']
        t['column'] = mapping.get(t['column'], t['column'])
        for key in ('group_column', 'time_column'):
            s = self.doc['structure'][key]
            s['value'] = mapping.get(s['value'], s['value'])
        return self

    def add(self, name, kind, values, description='An extra column of the extract.',
            special_values=()) -> 'Variant':
        self.doc['variables'].insert(len(self.doc['variables']) - 1, {
            'name': name, 'type': kind, 'role': 'feature', 'description': description,
            'status': 'scenario_assumption', 'source': 'Perturbation test',
            'availability': {'value': 'available_at_prediction', 'status': 'scenario_assumption',
                             'source': 'Perturbation test'},
            'special_values': [dict(s) for s in special_values]})
        at = len(self.columns) - 1
        self.columns.insert(at, name)
        for row, value in zip(self.rows, values):
            row.insert(at, value)
        return self

    def cells(self, column, fn) -> 'Variant':
        i = self.columns.index(column)
        for n, row in enumerate(self.rows):
            row[i] = fn(n, row[i])
        return self

    def keep(self, n) -> 'Variant':
        self.rows = self.rows[:n]
        return self

    def write(self) -> Path:
        self.out.mkdir(parents=True, exist_ok=True)
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=self.sep, quoting=self.quoting, lineterminator='\n')
        writer.writerow(self.columns)
        writer.writerows(self.rows)
        data = buffer.getvalue().encode('utf-8')
        (self.out / 'data.csv').write_bytes(data)
        doc = copy.deepcopy(self.doc)
        doc['dataset'].update(path='data.csv', sep=self.sep, rows=len(self.rows),
                              columns=len(self.columns),
                              sha256=hashlib.sha256(data).hexdigest())
        doc['special_values'] = [{'column': v['name'], **s} for v in doc['variables']
                                 for s in v['special_values']]
        c.check_document(doc)
        (self.out / 'case.yaml').write_text(yaml.safe_dump(doc, sort_keys=False, width=100),
                                            encoding='utf-8')
        return self.out


# --- driving a study ----------------------------------------------------------------------

class Refused(Exception):
    def __init__(self, step, payload):
        super().__init__(step)
        self.step, self.error = step, payload['error']


def _strict(payload):
    """Every payload is strict JSON: no NaN or infinity standing in for a number."""
    json.dumps(payload, allow_nan=False)


class Walk:
    def __init__(self, case_dir: Path, study: Path):
        self.case_dir, self.study, self.n = case_dir, study, 0
        self.results: dict[str, dict] = {}

    def call(self, step, *args):
        outcome = cli.run([str(a) for a in args])        # an escaping exception fails the test
        _strict(outcome.payload)
        if outcome.exit_code != 0:
            raise Refused(step, outcome.payload)
        return outcome.payload

    def rev(self):
        return self.call('status', 'status', '--study', self.study)['revision']

    def rid(self):
        self.n += 1
        return f'p{self.n}'

    def decide(self, decision, value, words=None):
        p = self.call(decision, 'decide', 'propose', decision, '--value-json', json.dumps(value),
                      '--restatement', f'You decide the {decision} as stated.', '--rationale',
                      'It fits the scenario.', '--request-id', self.rid(),
                      '--expected-revision', self.rev(), '--study', self.study)
        return self.call(decision, 'decide', 'confirm', p['result']['proposal_id'],
                         '--user-words', words or f'Yes, I want the {decision} as you stated it',
                         '--request-id', self.rid(), '--expected-revision', self.rev(),
                         '--study', self.study)

    def run(self, activity, *options):
        out = self.call(activity, 'run', activity, *options, '--request-id', self.rid(),
                        '--expected-revision', self.rev(), '--study', self.study)
        self.results[activity] = out
        return out

    def walk(self, *, split=None, by=None, capacity=None) -> dict:
        """The whole study; returns the measured outcome."""
        self.call('init', 'init', '--case', self.case_dir, '--study', self.study)
        case = c.load_case(self.case_dir)
        regression = case.task == 'regression'
        self.decide('prediction_time', 'when the record is created, before the outcome')
        self.decide('feature_availability', fk.availability(self.case_dir))
        if split is None:
            split = ({'method': 'ordinal_cutoff', 'column': case.time_column, 'cutoff': 5}
                     if case.time_column else
                     {'method': 'random' if regression else 'stratified_random',
                      'validation_fraction': 0.3, 'seed': 7})
        self.decide('split', split)
        parts = self.run('split')['values']
        if regression:
            self.run('eda.target_summary')
        else:
            self.run('eda.target_rate')
        self.run('eda.special_values')
        by = by or next(v['name'] for v in case.document['variables'] if v['role'] == 'feature')
        self.run('eda.mean_by' if regression else 'eda.rate_by', '--column', by)
        self.run('fit.baseline')
        candidate = self.run('fit.linear' if regression else 'fit.logistic')
        if regression:
            ev = self.run('evaluate.regression')['values']
            self.decide('model_choice', 'fit.baseline', 'Yes, keep the mean baseline.')
        else:
            n_val = parts['partitions']['validation']['n_rows']
            capacity = capacity or max(1, n_val // 3)
            ev = self.run('policy.evaluate', '--rule', 'threshold:0.2', '--rule',
                          f'capacity:{capacity}')['values']
            self.decide('policy', f'capacity:{capacity}',
                        f'Yes, review the {capacity} highest scores.')
        self.decide('conclusion', {'verdict': 'keep_baseline', 'text': CONCLUSION},
                    'Yes, I keep the baseline and record why.')
        check = self.call('check', 'check', '--study', self.study)
        view = read.open(self.study)
        return {'split': parts, 'candidate': candidate['values'], 'evaluation': ev,
                'check': check, 'state': view.state,
                'nyd': {x['id'] for x in self.call('status', 'status', '--study',
                                                  self.study)['view']['not_yet_defensible']}}


def read_view(tmp: Path) -> dict:
    from mlkit.study import view
    return view.build(tmp / 'study')


def outcome(variant: Variant, tmp: Path, **walk) -> dict | Refused:
    case_dir = variant.write()
    try:
        return Walk(case_dir, tmp / 'study').walk(**walk)
    except Refused as refused:
        return refused


def completed(result) -> dict:
    assert not isinstance(result, Refused), (result.step, result.error)
    check = result['check']
    assert check['clean'] is True and check['counts']['error'] == 0, check['findings']
    for d in result['state']['decisions'].values():
        assert d['status'] == 'confirmed', d
    return result


def refused(result, step, code, capability=None) -> dict:
    assert isinstance(result, Refused), 'expected a refusal, the walkthrough completed'
    assert (result.step, result.error['code']) == (step, code), (result.step, result.error)
    if capability is not None:
        names = {r.get('capability') for r in result.error.get('details', {}).get('reasons', [])}
        assert capability in names, result.error
    return result.error


def _finite(values) -> bool:
    return all(math.isfinite(v) for v in values if isinstance(v, float))


# --- variants -----------------------------------------------------------------------------

RENAMES = {'member_age': 'Member age (years)', 'home_branch': 'branche d\'origine',
           'membership_days': 'days.member', 'fines_outstanding': 'Fines €',
           'outcome': 'Renewal Outcome'}


@pytest.mark.parametrize('task', ['binary', 'regression'])
def test_renamed_columns_with_spaces_punctuation_and_accents(task, tmp_path):
    v = Variant(tmp_path, task=task)
    mapping = RENAMES if task == 'binary' else {
        'floor_area': 'Floor area (m²)', 'staff_count': 'staff count', 'monthly_loans': 'Loans/month'}
    v.rename(mapping)
    by = 'branche d\'origine' if task == 'binary' else 'staff count'
    result = completed(outcome(v, tmp_path, by=by))
    used = result['candidate']['features']
    assert {m for k, m in mapping.items() if v.variable(m)['role'] == 'feature'
            and v.variable(m)['availability']['value'] != 'not_available'} - set(used) == set()


@pytest.mark.parametrize('sep', [',', '\t'])
def test_other_separators(sep, tmp_path):
    v = Variant(tmp_path)
    v.sep = sep
    completed(outcome(v, tmp_path))


def test_quoted_fields_holding_the_separator(tmp_path):
    v = Variant(tmp_path)
    v.sep, v.quoting = ',', csv.QUOTE_ALL
    v.cells('home_branch', lambda n, x: f'{x}, north wing' if n % 2 else x)
    completed(outcome(v, tmp_path, by='home_branch'))
    rate_by = read.open(tmp_path / 'study').current('eda.rate_by:home_branch')
    groups = {g['value'] for g in rate_by['output']['values']['groups']}
    assert any(', north wing' in str(g) for g in groups), groups


def test_extra_irrelevant_columns(tmp_path):
    v = Variant(tmp_path)
    n = len(v.rows)
    v.add('noise_number', 'numeric', [f'{(i * 7919) % 1000 / 10:.1f}' for i in range(n)])
    v.add('noise_code', 'category', [f'k{(i * 31) % 4}' for i in range(n)])
    result = completed(outcome(v, tmp_path, by='noise_code'))
    assert {'noise_number', 'noise_code'} <= set(result['candidate']['features'])


@pytest.mark.parametrize('task', ['binary', 'regression'])
def test_constant_column(task, tmp_path):
    v = Variant(tmp_path, task=task)
    v.add('constant_flag', 'integer', ['1'] * len(v.rows))
    result = completed(outcome(v, tmp_path, by='constant_flag'))
    assert 'constant_flag' in result['candidate']['features']
    assert _finite(result['candidate']['coefficients'].values())


def test_high_cardinality_category(tmp_path):
    v = Variant(tmp_path)
    v.add('ticket_code', 'category', [f'T{(i * 7) % 509:04d}' for i in range(len(v.rows))])
    result = completed(outcome(v, tmp_path, by='ticket_code'))
    groups = read.open(tmp_path / 'study').current('eda.rate_by:ticket_code')['output']['values']
    # G.12: the 20 largest groups and one "other" group, with counts; a warning, no refusal.
    assert groups['max_groups'] == 20 and groups['n_groups'] > 300
    assert len(groups['groups']) == 21 and groups['groups'][-1]['value'] == '(other values)'
    other = groups['other']
    assert other['n_values'] == groups['n_groups'] - 20
    assert other['n_rows'] == groups['groups'][-1]['n_rows']
    assert sum(g['n_rows'] for g in groups['groups']) == groups['n_rows']
    assert groups['warnings'][0].startswith(f'ticket_code has {groups["n_groups"]} values')
    assert 'high_cardinality_grouping' in result['nyd']
    assert _finite(result['candidate']['coefficients'].values())


def test_high_cardinality_grouping_is_configurable(tmp_path):
    v = Variant(tmp_path)
    v.add('ticket_code', 'category', [f'T{(i * 7) % 509:04d}' for i in range(len(v.rows))])
    walk = Walk(v.write(), tmp_path / 'study')
    walk.walk(by='ticket_code')
    out = walk.run('eda.rate_by', '--column', 'ticket_code', '--max-groups', '5')['values']
    assert out['max_groups'] == 5 and len(out['groups']) == 6
    assert out['other']['n_values'] == out['n_groups'] - 5
    assert out['other']['n_positive'] == out['groups'][-1]['n_positive']
    with pytest.raises(Refused) as exc:
        walk.run('eda.rate_by', '--column', 'ticket_code', '--max-groups', '0')
    assert exc.value.error['code'] == 'invalid_arguments'


@pytest.mark.parametrize('task', ['binary', 'regression'])
def test_declared_missing_values_in_features(task, tmp_path):
    v = Variant(tmp_path, task=task)
    numeric = 'member_age' if task == 'binary' else 'floor_area'
    category = 'home_branch' if task == 'binary' else 'branch_type'
    for column in (numeric, category):
        v.cells(column, lambda n, x: '' if n % 9 == 0 else x)
        v.variable(column)['special_values'].append(
            {'value': '', 'meaning': 'Not recorded', 'status': 'scenario_assumption',
             'source': 'Perturbation test'})
    v.doc['dataset']['na_values'] = v.doc['dataset'].get('na_values', []) + ['']
    result = completed(outcome(v, tmp_path, by=numeric))
    assert {numeric, category} <= set(result['candidate']['features'])
    specials = read.open(tmp_path / 'study').current('eda.special_values')['output']['values']
    counted = {s['column']: s['n_rows'] for s in specials['special_values'] if s['value'] == ''}
    assert counted[numeric] > 0 and counted[category] > 0


def test_group_column_overlap_is_reported_not_prevented(tmp_path):
    v = Variant(tmp_path, groups=True)
    result = completed(outcome(v, tmp_path))
    groups = result['split']['groups']
    assert groups['capability'] == 'grouped split (v0.2)' and groups['shared_groups'] > 0
    assert 'grouped_split_unsupported' in result['nyd']


def test_date_time_column_is_refused_with_its_capability(tmp_path):
    error = refused(outcome(Variant(tmp_path, time=True), tmp_path), 'init',
                    'unsupported_capability',
                    'temporal split on a date or non-integer time column (v0.2)')
    assert not (tmp_path / 'study' / '.hypotrail').exists()
    assert error['details']['reasons'][0]['column'] == 'cycle_start_date'


def test_duplicate_rows_are_refused_with_their_capability(tmp_path):
    error = refused(outcome(Variant(tmp_path, duplicates=4), tmp_path), 'init',
                    'unsupported_capability', 'duplicate records (v0.2)')
    assert error['details']['reasons'][0]['duplicate_rows'] == 4


def test_two_percent_positives(tmp_path):
    v = Variant(tmp_path, n_rows=1500, positive_rate=0.02, seed=11)
    result = completed(outcome(v, tmp_path))
    train = result['split']['partitions']['train']
    assert 0 < train['rate'] < 0.05
    rules = result['evaluation']['rules']
    for rule in rules.values():
        for model in rule['models'].values():
            assert all(x is None or math.isfinite(x) for x in model.values()
                       if isinstance(x, (int, float)) and not isinstance(x, bool))


@pytest.mark.parametrize('task', ['binary', 'regression'])
def test_tiny_dataset_of_sixty_rows(task, tmp_path):
    v = Variant(tmp_path, task=task, n_rows=100).keep(60)
    result = completed(outcome(v, tmp_path))
    assert result['split']['n_rows'] == 60
    assert result['split']['partitions']['validation']['n_rows'] == 18


def test_windows_line_endings(tmp_path):
    v = Variant(tmp_path)
    case_dir = v.write()
    data = (case_dir / 'data.csv').read_bytes().replace(b'\n', b'\r\n')
    (case_dir / 'data.csv').write_bytes(data)
    doc = yaml.safe_load((case_dir / 'case.yaml').read_text())
    doc['dataset']['sha256'] = hashlib.sha256(data).hexdigest()
    (case_dir / 'case.yaml').write_text(yaml.safe_dump(doc, sort_keys=False))
    completed(Walk(case_dir, tmp_path / 'study').walk())


def test_extreme_imbalance_one_positive_is_refused_at_the_split(tmp_path):
    v = Variant(tmp_path, n_rows=400)
    target = v.columns.index('outcome')
    first = next(i for i, r in enumerate(v.rows) if r[target] == 'renewed')
    v.cells('outcome', lambda n, x: 'renewed' if n == first else 'lapsed')
    error = refused(outcome(v, tmp_path), 'split', 'unsupported_capability',
                    'stratified split with fewer than two rows of each class')
    reason = error['details']['reasons'][0]
    assert reason['counts'] == {'renewed': 1, 'lapsed': 399}


def test_capacity_larger_than_the_validation_partition(tmp_path):
    v = Variant(tmp_path, n_rows=100).keep(60)
    result = completed(outcome(v, tmp_path, capacity=100))
    rule = result['evaluation']['rules']['capacity:100']['models']['fit.logistic']
    assert rule['selected'] == 18
    # G.12: warnings, not refusals: the capacity selects every row of a small partition.
    assert {'capacity_exceeds_validation', 'small_validation_partition'} <= result['nyd']
    items = {x['id']: x for x in read_view(tmp_path)['not_yet_defensible']}
    assert items['capacity_exceeds_validation']['rules'] == ['capacity:100']
    assert items['capacity_exceeds_validation']['n_rows'] == 18
    assert 'selects every row' in items['capacity_exceeds_validation']['text']
    assert items['small_validation_partition']['n_rows'] == 18
    assert '18 rows' in items['small_validation_partition']['text']


def test_undeclared_blank_cells_in_a_numeric_feature_are_refused(tmp_path):
    """A blank cell the case does not declare as missing would turn a numeric column into
    text, one-hot encoded without a word: the case must say how a blank is read."""
    v = Variant(tmp_path)
    v.cells('member_age', lambda n, x: '' if n % 11 == 0 else x)
    error = refused(outcome(v, tmp_path), 'init', 'invalid_case')
    [problem] = error['problems']
    assert problem['path'] == 'variables[0].type' and 'member_age' in problem['problem']
    assert "''" in problem['problem'] and 'na_values' in problem['problem']


def test_undeclared_text_token_in_a_numeric_feature_is_refused(tmp_path):
    v = Variant(tmp_path, task='regression')
    v.cells('floor_area', lambda n, x: 'n/a' if n == 3 else x)
    error = refused(outcome(v, tmp_path), 'init', 'invalid_case')
    assert "'n/a'" in error['problems'][0]['problem']


def test_missing_binary_target_is_refused_with_its_capability(tmp_path):
    v = Variant(tmp_path)
    v.cells('outcome', lambda n, x: '' if n % 50 == 0 else x)
    v.doc['dataset']['na_values'] = v.doc['dataset'].get('na_values', []) + ['']
    v.variable('outcome')['special_values'].append(
        {'value': '', 'meaning': 'Outcome not recorded', 'status': 'scenario_assumption',
         'source': 'Perturbation test'})
    error = refused(outcome(v, tmp_path), 'init', 'unsupported_capability',
                    'missing target values (v0.2)')
    assert error['details']['reasons'][0]['rows'] == 12
    assert not (tmp_path / 'study' / '.hypotrail').exists()


def test_missing_regression_target_is_refused_at_init(tmp_path):
    v = Variant(tmp_path, task='regression')
    v.cells('monthly_loans', lambda n, x: '' if n in (4, 9) else x)
    v.doc['dataset']['na_values'] = v.doc['dataset'].get('na_values', []) + ['']
    v.variable('monthly_loans')['special_values'].append(
        {'value': '', 'meaning': 'Not recorded', 'status': 'scenario_assumption',
         'source': 'Perturbation test'})
    error = refused(outcome(v, tmp_path), 'init', 'unsupported_capability',
                    'missing target values (v0.2)')
    assert error['details']['reasons'][0]['examples'] == ['L6', 'L11']


def test_three_positives_complete_or_name_their_limit(tmp_path):
    """Three positive rows can be stratified; the validation partition then holds one."""
    v = Variant(tmp_path, n_rows=400)
    target = v.columns.index('outcome')
    keep = [i for i, r in enumerate(v.rows) if r[target] == 'renewed'][:3]
    v.cells('outcome', lambda n, x: 'renewed' if n in keep else 'lapsed')
    result = completed(outcome(v, tmp_path, capacity=5))
    assert result['split']['partitions']['validation']['n_positive'] == 1
    # G.12: the single validation positive is named, with the counts.
    item = {x['id']: x for x in read_view(tmp_path)['not_yet_defensible']}[
        'small_validation_partition']
    assert item['n_positive'] == 1 and item['min_positive'] == 5
    assert '1 of them positive' in item['text']


def test_binary_target_label_outside_the_declared_labels_is_refused(tmp_path):
    v = Variant(tmp_path)
    v.cells('outcome', lambda n, x: 'Renewed' if n == 5 else x)
    error = refused(outcome(v, tmp_path), 'init', 'invalid_case')
    problem = error['problems'][0]
    assert problem['path'] == 'target' and "'Renewed'" in problem['problem']
