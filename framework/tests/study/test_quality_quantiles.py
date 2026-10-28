"""Owner session 2026-10-26, lot L8 (R5): the quality check gives each numeric column its
1 %, 50 % and 99 % quantiles and its skewness.

``eda.quality`` ``ranges`` gain two additive keys per numeric column: ``quantiles``
(``{"0.01", "0.5", "0.99"}``, pandas' linear quantiles of the ordinary values: special values
and missing cells left out, as ``min`` and ``max``) and ``skewness`` (the sample skewness,
adjusted Fisher-Pearson, None with fewer than three values or no spread). Every other key
keeps its value; the target is still never read.
"""
from __future__ import annotations

import math

import pandas as pd
import pytest

from mlkit.study import case as c, data as dt, eda

import flowkit as fk
from flowkit import Flow

RANGE_KEYS = ('column', 'type', 'min', 'max', 'n_special', 'declared', 'n_below', 'n_above',
              'quantiles', 'skewness')


@pytest.mark.parametrize('values, quantiles, skewness', [
    # G1 = g1 * sqrt(n (n - 1)) / (n - 2), g1 = m3 / m2^1.5 = 88920 / 1522^1.5.
    ([1.0, 2.0, 3.0, 4.0, 100.0], {'0.01': 1.04, '0.5': 3.0, '0.99': 96.16}, 2.2324),
    ([5.0, 5.0, 5.0], {'0.01': 5.0, '0.5': 5.0, '0.99': 5.0}, None),     # no spread
    ([1.0, 2.0], {'0.01': 1.01, '0.5': 1.5, '0.99': 1.99}, None),        # fewer than three
    ([], {'0.01': None, '0.5': None, '0.99': None}, None),
])
def test_the_shape_of_a_column(values, quantiles, skewness):
    out = eda._shape(pd.Series(values, dtype=float))
    assert list(out) == ['quantiles', 'skewness']
    assert list(out['quantiles']) == ['0.01', '0.5', '0.99']
    for q, expected in quantiles.items():
        got = out['quantiles'][q]
        assert got is None if expected is None else got == pytest.approx(expected)
    if skewness is None:
        assert out['skewness'] is None
    else:
        assert out['skewness'] == pytest.approx(skewness, abs=1e-4)
        assert isinstance(out['skewness'], float) and math.isfinite(out['skewness'])


def test_the_quality_check_gives_quantiles_and_skewness_per_numeric_column(tmp_path,
                                                                         synthetic_case_dir):
    flow = Flow(tmp_path / 'study', synthetic_case_dir)
    flow.init()
    values = flow.run('eda.quality')['values']
    assert values['target_read'] is False
    case = c.load_case(synthetic_case_dir)
    frame = dt.load_development(case, fk.partition_keys(flow.study, 'development')).frame
    numeric = {v['name'] for v in case.document['variables']
               if v['role'] == 'feature' and v['type'] in eda.NUMERIC_TYPES
               and pd.api.types.is_numeric_dtype(frame[v['name']])}
    assert {r['column'] for r in values['ranges']} >= numeric
    specials = {}
    for s in case.document['special_values']:
        specials.setdefault(s['column'], []).append(s['value'])
    skewed = 0
    for item in values['ranges']:
        assert tuple(item) == RANGE_KEYS
        column = frame[item['column']]
        mask = column.isna()
        for value in specials.get(item['column'], []):
            mask |= eda._matches(column, value, case)
        ordinary = column[~mask].astype(float)
        assert item['min'] == ordinary.min() and item['max'] == ordinary.max()
        for q in eda.QUALITY_QUANTILES:
            assert item['quantiles'][str(q)] == float(ordinary.quantile(q)), item['column']
        assert item['quantiles']['0.01'] <= item['quantiles']['0.5'] <= item['quantiles']['0.99']
        assert item['skewness'] == pytest.approx(float(ordinary.skew()))
        skewed += abs(item['skewness']) > 1
    # The synthetic case has long-tailed counts and amounts (fines, lapses).
    assert skewed
    # Nothing else moved: the cardinality and the missing cells keep their shape.
    assert all(set(i) == {'column', 'type', 'n_distinct', 'rare', 'rare_rows'}
               for i in values['cardinality'])
