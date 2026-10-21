"""WP-B6a (review M2): rows already exposed outside the study are never sealed.

A case may declare ``prior_exposed_rows`` (``CASE-CONTRACT.md``): a file of row keys inside
the case directory, with its sha256 and count. At ``init`` those rows stay development
rows: a temporal final test is the declared tail less them, a stratified one is drawn from
the other rows; the record keeps ``prior_exposed`` and the status view
``excluded_prior_exposed``. The Bank full case (``test_v02b_cases.py``) holds the real
numbers: 893 of its latest 9,042 lines are ``bank.csv`` records.

Studies and cases live in ``tmp_path``.
"""
from __future__ import annotations

import hashlib

from mlkit.study import case as c, partition

import flowkit as fk
from flowkit import Flow
from test_perturbations import Variant

PRIOR = 'prior-rows.txt'


def _case(tmp_path, keys, *, ordered=True, n_rows=200, sha=None, rows=None):
    variant = Variant(tmp_path, n_rows=n_rows)
    if ordered:
        variant.doc['order'] = {'by': 'line', 'direction': 'ascending',
                                'status': 'scenario_assumption', 'source': 'test: time order'}
    text = ''.join(f'{k}\n' for k in keys)
    variant.doc['prior_exposed_rows'] = {
        'path': PRIOR, 'sha256': sha or hashlib.sha256(text.encode()).hexdigest(),
        'rows': len(keys) if rows is None else rows, 'match': 'row_key',
        'status': 'observed', 'source': 'test: a tutorial published these rows'}
    case_dir = variant.write()
    (case_dir / PRIOR).write_text(text, encoding='utf-8')
    return case_dir


def test_temporal_final_test_is_the_tail_less_the_exposed_rows(tmp_path):
    exposed = ['L5', 'L170', 'L171', 'L199', 'L201']           # one early, four in the tail
    case_dir = _case(tmp_path, exposed)
    flow = Flow(tmp_path / 'study', case_dir)
    final = flow.init()['final_test']
    tail = [f'L{i}' for i in range(2 + 200 - 40, 2 + 200)]
    sealed = fk.partition_keys(flow.study, 'final_test')
    assert sorted(sealed, key=lambda k: int(k[1:])) == [k for k in tail if k not in exposed]
    assert final['rows'] == 36 and final['development_rows'] == 164
    assert final['excluded_prior_exposed'] == 4
    assert set(exposed) <= set(fk.partition_keys(flow.study, 'development'))
    record = flow.state()['partition']
    assert record['prior_exposed'] == {'path': PRIOR, 'sha256': record['prior_exposed']['sha256'],
                                       'declared_rows': 5, 'excluded_rows': 4}
    assert record['fraction'] == partition.DEFAULT_FRACTION     # the cut is unchanged
    assert 'prior_exposed_rows' in record['implementation']
    assert flow.view()['final_test']['excluded_prior_exposed'] == 4
    assert flow.call('status', '--summary', '--study', flow.study)['final_test'][
        'excluded_prior_exposed'] == 4


def test_stratified_final_test_is_drawn_from_the_other_rows(tmp_path):
    exposed = [f'L{i}' for i in range(2, 32)]
    case_dir = _case(tmp_path, exposed, ordered=False)
    flow = Flow(tmp_path / 'study', case_dir)
    final = flow.init()['final_test']
    sealed = set(fk.partition_keys(flow.study, 'final_test'))
    assert not sealed & set(exposed)
    assert final['excluded_prior_exposed'] == 30
    assert abs(final['rows'] - round(0.2 * 170)) <= 2              # a fifth of the others


def test_a_wrong_declaration_refuses_init(tmp_path):
    for i, (kwargs, code) in enumerate([
            ({'keys': ['L5', 'L999']}, 'invalid_case'),             # not a row of the dataset
            ({'keys': ['L5'], 'rows': 2}, 'invalid_case'),          # count differs
            ({'keys': ['L5'], 'sha': '0' * 64}, 'dataset_changed')]):
        case_dir = _case(tmp_path / str(i), **kwargs)
        out = Flow(tmp_path / str(i) / 'study', case_dir).call(
            'init', '--case', case_dir, '--study', tmp_path / str(i) / 'study', expect=None)
        assert out['ok'] is False and out['error']['code'] == code, out


def test_the_declaration_is_validated(tmp_path):
    doc = Variant(tmp_path, n_rows=200).doc
    doc['prior_exposed_rows'] = {'path': '../x.txt', 'sha256': 'x', 'rows': 0,
                                 'match': 'record', 'status': 'unknown_status', 'source': ''}
    problems = {p['path'] for p in c.validate(doc)}
    assert {'prior_exposed_rows.path', 'prior_exposed_rows.sha256', 'prior_exposed_rows.rows',
            'prior_exposed_rows.match', 'prior_exposed_rows.status',
            'prior_exposed_rows.source'} <= problems


def test_a_case_without_the_declaration_is_unchanged(tmp_path):
    variant = Variant(tmp_path, n_rows=200)
    flow = Flow(tmp_path / 'study', variant.write())
    final = flow.init()['final_test']
    assert final['excluded_prior_exposed'] == 0
    assert 'prior_exposed' not in flow.state()['partition']

