"""The opt-in ``diagnostics.population`` activity (Evidently) in a real study (AC12, AC27)."""
from __future__ import annotations

import pytest

import flowkit as fk
from mlkit.study import case as c, read

import libkit

pytest.importorskip('evidently')


@pytest.mark.parametrize('task', ['binary', 'regression'])
def test_population_diagnostics_read_features_only_and_reach_the_report(tmp_path, task):
    flow = libkit.study_at_fits(tmp_path, task=task)
    run = flow.run('diagnostics.population')
    v = run['values']
    assert v['diagnostic']['schema_version'] == 'hypotrail.diagnostic_result/1'
    assert v['populations']['scheme'] in ('folds', 'evaluation_windows', 'train_validation')
    assert v['alert'] in (True, False, None)
    case_target = c.load_case(flow.case_dir).target_column
    records = [r for r in fk.exposure_records(flow.study)
               if r['activity'] == 'diagnostics.population']
    assert records and all(r['purpose'] == 'structural_inspection' for r in records)
    assert all(case_target not in r['columns'] for r in records)       # never the target
    entry = read.open(flow.study).result(run['result_id'])
    assert 'evidently_snapshot' in entry['blobs']
    versions = {d['distribution'] for d in entry['params']['semantic_dependencies']}
    assert 'evidently' in versions                      # the backend version is identity
    html = (flow.study / 'reports' / 'study.html').read_text()
    assert 'diagnostics.population' in html             # shown in the report's annex


def test_without_the_extra_it_is_refused_before_any_read(tmp_path, monkeypatch):
    import importlib.util
    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, 'find_spec',
                        lambda name, *a: None if name == 'evidently' else real(name, *a))
    flow = libkit.study_at_fits(tmp_path, task='binary', n_rows=300)
    before = len(fk.exposure_records(flow.study))
    out = flow.run('diagnostics.population', expect=2)
    assert out['error']['details']['contract_code'] == 'optional_dependency_missing'
    assert len(fk.exposure_records(flow.study)) == before
