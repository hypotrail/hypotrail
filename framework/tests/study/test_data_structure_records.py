"""The panel digest's ``data_structure`` is counted without pandas (CC R3: a read imports no
heavy module), by :func:`cmd_data.structure_records` on :func:`data.development_records`.
It must equal :func:`cmd_data.structure` on the pandas frame of the same rows: on every
real case whose data are present, on the synthetic case, and on a small case that holds the
traps of a text reader (numbers written two ways, the decimal comma, missing values, a
group column)."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mlkit.study import case as c, cmd_data, data as dt

REPO = Path(__file__).resolve().parents[3]
REAL = sorted(p.parent for p in (REPO / 'use-cases').glob('*/case.yaml'))


def _both(case, rows=None):
    pandas_side = cmd_data.structure(case, dt.load_dataset(case, supported_only=False,
                                                           rows=rows).frame)
    return pandas_side, cmd_data.structure_records(case, dt.development_records(case, rows))


@pytest.mark.parametrize('case_dir', REAL, ids=[p.name for p in REAL])
def test_real_cases(case_dir):
    try:
        case = c.load_case(case_dir)
    except c.CaseError as exc:
        pytest.skip(f'{case_dir.name}: {exc}')
    pandas_side, records_side = _both(case)
    assert records_side == pandas_side


def test_synthetic_case_on_development_rows(synthetic_case_dir):
    case = c.load_case(synthetic_case_dir)
    keys = list(dt.row_index(case).keys)[::3]
    pandas_side, records_side = _both(case, keys)
    assert records_side == pandas_side


def test_text_reader_traps(synthetic_case_dir, tmp_path):
    """``1`` and ``1,0`` are one number (decimal comma), ``NA`` is missing and equal to
    another missing value, a text column stays text, a group column counts its values."""
    rows = ['x;y;g;t', '1;a;G1;lapsed', '1,0;a;G1;renewed', 'NA;b;G2;lapsed',
            'NA;b;NA;renewed', '2;c;G3;lapsed', '2,5;c;G3;lapsed']
    path = tmp_path / 'traps.csv'
    path.write_bytes(('\n'.join(rows) + '\n').encode('utf-8'))
    import hashlib
    document = yaml.safe_load((synthetic_case_dir / 'case.yaml').read_text(encoding='utf-8'))
    document['dataset'].update(path=path.name, sep=';', decimal=',', header=True,
                               na_values=['NA'], rows=len(rows) - 1, columns=4,
                               sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    document['dataset'].pop('quotechar', None)
    template = {**document['variables'][0], 'special_values': []}
    kinds = {'x': ('feature', 'numeric'), 'y': ('feature', 'category'),
             'g': ('group_id', 'category'), 't': ('target', 'binary')}
    document['variables'] = [{**template, 'name': n, 'role': r, 'type': t}
                             for n, (r, t) in kinds.items()]
    document['special_values'] = []
    document['structure'] = {**(document.get('structure') or {}),
                             'group_column': {**((document.get('structure') or {})
                                                 .get('group_column') or {}), 'value': 'g'}}
    document['target'] = {'column': 't', 'positive_label': 'renewed', 'negative_label': 'lapsed'}
    (tmp_path / 'case.yaml').write_text(yaml.safe_dump(document, allow_unicode=True),
                                        encoding='utf-8', newline='\n')
    try:
        case = c.load_case(tmp_path)
    except c.CaseError as exc:      # pragma: no cover - the case template changed
        pytest.fail(f'the trap case no longer loads: {exc}')
    pandas_side, records_side = _both(case)
    assert records_side == pandas_side
    assert records_side['duplicates']['identical_feature_rows'] == 4
    assert records_side['groups'] == [{'column': 'g', 'groups': 3, 'rows_in_repeated_groups': 4}]
