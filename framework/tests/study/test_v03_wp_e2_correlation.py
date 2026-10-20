"""v0.3 WP-E2 (R28): ``eda.correlation``, the predictor-versus-predictor association matrix.

* it reads the development rows' candidate features, never the target, needs no split and
  no decision, and records a structural inspection, not a target look;
* Spearman for two numeric features, bias-corrected Cramér's V for two categorical ones,
  the correlation ratio for a mixed pair; |association| >= 0.8 is flagged; the order groups
  associated features;
* it is in the engine's EDA catalog (both tasks) as a development-row activity without a
  column, so the panel's W4 can run it.

Studies live in temporary directories; the committed cases are only read.
"""
from __future__ import annotations

import pandas as pd

from mlkit.study import correlation

import flowkit as fk
from flowkit import Flow


def test_correlation_reads_the_features_of_the_development_rows_only(tmp_path):
    flow = Flow(tmp_path / 'study', fk.BANK)
    flow.init()
    out = flow.run('eda.correlation')
    v = out['values']
    assert v['partition'] == 'development' and v['target_read'] is False
    assert v['n_rows'] == flow.view()['final_test']['development_rows']
    names = [c['name'] for c in v['columns']]
    assert 'y' not in names and sorted(v['order']) == sorted(names)
    assert len(v['pairs']) == len(names) * (len(names) - 1) // 2
    assert {p['measure'] for p in v['pairs']} == {'spearman', 'cramers_v', 'eta'}
    for p in v['pairs']:
        if p['value'] is None:
            continue
        low = -1 if p['measure'] == 'spearman' else 0
        assert low - 1e-9 <= p['value'] <= 1 + 1e-9
        assert p['flag'] == (abs(p['value']) >= correlation.COLLINEARITY_LEVEL)
    assert v['n_flagged'] == len(v['flagged']) == sum(p['flag'] for p in v['pairs'])
    assert v['question'].startswith('Do any two predictors')
    record = fk.exposure_records(flow.study)[-1]
    assert record['purpose'] == 'structural_inspection' and record['partition'] == 'development'
    assert 'y' not in record['columns']
    assert flow.view()['eda_looks']['target_looks'] == 0


def test_correlation_is_in_the_catalog_without_a_column(tmp_path):
    flow = Flow(tmp_path / 'study', fk.BANK)
    flow.init()
    catalog = flow.call('evidence', '--json', '--study', flow.study)['eda_catalog']['activities']
    entry = next(a for a in catalog if a['activity'] == 'eda.correlation')
    assert entry['per_column'] is False and entry['columns'] == []
    assert entry['runnable'] is True and entry['partition'] == 'development'


class _Case:
    """The few case attributes the computation reads."""

    def __init__(self, types):
        self.variables = {k: {'name': k, 'type': t, 'role': 'feature'} for k, t in types.items()}
        self.document = {'special_values': [{'column': 'b', 'value': -1, 'meaning': 'unknown'}]}
        self.dataset = {}


def test_measures_flag_and_order_on_a_synthetic_frame():
    n = 200
    a = pd.Series(range(n), dtype=float)
    frame = pd.DataFrame({
        'a': a,
        'noise': pd.Series([(i * 7919) % 101 for i in range(n)], dtype=float),
        'b': a * 2 + 1,
        'colour': ['red' if i < n / 2 else 'blue' for i in range(n)],
        'shade': ['dark' if i < n / 2 else 'light' for i in range(n)],
    })
    frame.loc[5, 'b'] = -1          # a special value: left out of the pair
    case = _Case({'a': 'numeric', 'noise': 'numeric', 'b': 'numeric', 'colour': 'categorical',
                  'shade': 'categorical'})
    v = correlation.correlation(case, frame, ['a', 'noise', 'b', 'colour', 'shade'])
    pairs = {(p['a'], p['b']): p for p in v['pairs']}
    assert pairs[('a', 'b')]['measure'] == 'spearman' and pairs[('a', 'b')]['value'] > 0.999
    assert pairs[('a', 'b')]['n_rows'] == n - 1 and pairs[('a', 'b')]['flag']
    assert pairs[('colour', 'shade')]['measure'] == 'cramers_v' and pairs[('colour', 'shade')]['flag']
    assert pairs[('a', 'colour')]['measure'] == 'eta' and pairs[('a', 'colour')]['value'] > 0.8
    assert abs(pairs[('a', 'noise')]['value']) < 0.3 and not pairs[('a', 'noise')]['flag']
    order = v['order']
    # Strongly associated features sit next to each other.
    assert abs(order.index('colour') - order.index('shade')) == 1
    assert v['flagged'][0]['value'] >= v['flagged'][-1]['value']
