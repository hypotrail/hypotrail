"""WP-B4 (owner remark R9): model diagnostics.

* ``diag.binary`` / ``diag.regression`` read the stored out-of-fold predictions of the
  candidate and the variant on the development rows (development evidence): confusion
  matrix at the rule, gain/ROC/PR points, calibration with Wilson intervals and the Brier
  score, segments, coefficients with bootstrap intervals, example errors; residual
  diagnostics for a regression;
* the guard: ``diag.final_test`` is refused before the final test is opened and reads no
  final-test row; after the opening it reads the final evaluation's predictions and the
  final-test rows only (final evidence, purpose ``final_evaluation``);
* exposure (a development diagnostic is a target look), invalidation (another adopted rule,
  a refit), the report section (cited, ``check`` clean) and the notebook cell.

Studies and cases live in ``tmp_path``.
"""
from __future__ import annotations

import json
import subprocess
import sys

import numpy as np
import pytest

from mlkit.study import data as dt, diagnostics as dg, notebook_view as nv, policy, read
from mlkit.study import state as st

import flowkit as fk
from flowkit import Flow

OPEN_WORDS = 'Yes, I open the final test now, because the model and the rule are fixed'


def _ready(tmp_path, task='binary', n_rows=600) -> Flow:
    case_dir = fk.make_case(tmp_path / 'case', task=task, n_rows=n_rows)['case'].parent
    flow = Flow(tmp_path / 'study', case_dir)
    flow.init()
    flow.decide('prediction_time', 'when the record is created, before the outcome')
    flow.decide('feature_availability', fk.availability(case_dir))
    flow.decide('split', flow.view()['next_action']['default_value'])
    flow.model_decisions()
    flow.run('split')
    flow.run('fit.baseline')
    flow.run('fit.linear' if task == 'regression' else 'fit.logistic')
    flow.variant()
    return flow


def _open(flow) -> dict:
    value = st.b1_default_value(flow.state(), 'final_test')
    p = flow.call('decide', 'propose', 'final_test', '--value-json', json.dumps(value),
                  '--restatement', 'You open the sealed final test once, for the chosen '
                                   'configuration.',
                  '--rationale', 'Everything is chosen.', '--request-id', flow.rid(),
                  '--expected-revision', flow.rev(), '--study', flow.study)
    return flow.call('decide', 'confirm', p['result']['proposal_id'], '--user-words',
                     OPEN_WORDS, '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                     '--study', flow.study)


def _records(flow, activity):
    return [r for r in read.open(flow.study).exposure_records() if r['activity'] == activity]


def test_binary_diagnostics_read_the_out_of_fold_predictions(tmp_path):
    flow = _ready(tmp_path)
    out = flow.run('diag.binary')
    values = out['values']
    study = read.open(flow.study)
    development = set(fk.partition_keys(flow.study, 'development'))
    assert values['evidence'] == 'development' and values['purpose'] == 'development_diagnostics'
    assert values['partition'] == 'development' and values['evaluation'] == 'out_of_fold'
    assert values['question'] and values['note'] == dg.DEVELOPMENT_NOTE
    # No rule adopted or proposed, no teaching share in the synthetic case: the default.
    assert (values['rule'], values['rule_source']) == (dg.DEFAULT_RULE, 'engine_default')
    assert tuple(values) == dg.BINARY_KEYS
    assert set(values['models']) == {'fit.logistic', 'fit.variant'}
    for model, d in values['models'].items():
        assert tuple(d) == dg.BINARY_MODEL_KEYS
        preds = study.predictions(study.current(model)['result_id'])
        assert d['predictions'] == study.current(model)['result_id']
        y, score = preds['y'].to_numpy(dtype=float), preds['score'].to_numpy(dtype=float)
        assert values['n'] == len(y) == len(development)
        # The confusion matrix is the policy evaluation's at the same rule: under
        # cross-validation (B6c, H3) the rule selects within each fold.
        assignment = nv.folds(study)
        groups = assignment.reindex(preds['row_key']).to_numpy()
        ev = policy.evaluate(y, score, values['rule'], groups)
        c = d['confusion']
        assert c['selection_scope'] == ev['selection_scope'] == 'within_fold'
        assert (c['true_positives'], c['false_positives'], c['false_negatives']) == \
            (ev['true_positives'], ev['false_positives'], ev['false_negatives'])
        assert c['true_positives'] + c['false_positives'] + c['false_negatives'] \
            + c['true_negatives'] == len(y)
        # Curve: twenty points to the whole list; recall reaches one; AUC exact.
        points = d['curve']['points']
        assert len(points) == 20 and points[-1]['recall'] == pytest.approx(1.0)
        assert all(a['recall'] <= b['recall'] + 1e-12 for a, b in zip(points, points[1:]))
        assert d['roc_auc'] == pytest.approx(study.current(model)['output']['values']
                                             ['validation']['roc_auc'])
        # Calibration: ten bins of (almost) equal size covering every row, Wilson intervals.
        bins = d['calibration']['bins']
        assert len(bins) == 10 and sum(b['n'] for b in bins) == len(y)
        assert max(b['n'] for b in bins) - min(b['n'] for b in bins) <= 1
        assert all(b['low'] <= b['observed_rate'] <= b['high'] for b in bins)
        assert d['calibration']['brier'] == pytest.approx(float(np.mean((score - y) ** 2)))
        # Segments: every row once, counts add up, small cells flagged.
        assert values['segment_columns'] and len(d['segments']) == len(values['segment_columns'])
        for seg in d['segments']:
            assert sum(g['n'] for g in seg['groups']) == len(y)
            assert sum(g['selected'] for g in seg['groups']) == pytest.approx(c['selected'])
            for g in seg['groups']:
                assert g['small_cell'] == (g['n'] < dg.SMALL_CELL_ROWS
                                           or g['selected'] < dg.SMALL_CELL_SELECTED)
        # Examples: development rows only, at most five, really errors.
        by_key = dict(zip(preds['row_key'], y))
        for kind, label in (('false_positives', 0), ('false_negatives', 1)):
            items = d['examples'][kind]
            assert len(items) <= dg.MAX_EXAMPLES
            assert {i['row_key'] for i in items} <= development
            assert all(by_key[i['row_key']] == label for i in items)
            assert all(set(i['values']) == set(d['examples']['features']) for i in items)
        # Coefficients: the fit's values, bootstrap intervals that hold them.
        coef = d['coefficients']
        fitted = study.current(model)['output']['values']['coefficients']
        assert {t['term']: t['value'] for t in coef['terms']} == pytest.approx(fitted)
        assert coef['replicates'] + coef['skipped_replicates'] == dg.COEFFICIENT_REPLICATES
        inside = [t['low'] <= t['value'] <= t['high'] for t in coef['terms']]
        assert sum(inside) >= 0.8 * len(inside)
        assert coef['scale'].startswith('per standard deviation')
    # Exposure: one record on the development rows, read with the target: a look.
    [record] = _records(flow, 'diag.binary')
    assert record['purpose'] == 'development_diagnostics' and record['partition'] == 'development'
    assert record['n_rows'] == len(development)
    looks = flow.view()['eda_looks']
    assert looks['by_activity'].get('diag.binary') == 1 and out['result_id'] in looks['results']
    # The final test was never read.
    assert not [r for r in study.exposure_records() if r['partition'] == 'final_test'
                and r['purpose'] != 'sealed']


def test_the_rule_follows_the_proposal_then_the_adoption(tmp_path):
    flow = _ready(tmp_path)
    flow.run('policy.evaluate', '--rule', 'capacity:40', '--rule', 'capacity:30')
    p = flow.call('decide', 'propose', 'policy', '--value-json', json.dumps('capacity:40'),
                  '--restatement', 'You call the forty best-scored rows.', '--rationale', 'x',
                  '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                  '--study', flow.study)
    out = flow.run('diag.binary')
    assert (out['values']['rule'], out['values']['rule_source']) == ('capacity:40', 'proposed')
    assert out['values']['models']['fit.logistic']['confusion']['selected'] == 40
    flow.call('decide', 'confirm', p['result']['proposal_id'], '--user-words',
              'Yes, I adopt that rule because the desk can make that many calls',
              '--request-id', flow.rid(), '--expected-revision', flow.rev(),
              '--study', flow.study)
    # A first adoption makes the diagnostics stale: they said "proposed".
    assert not st.is_current(flow.state(), 'diag.binary')
    again = flow.run('diag.binary')
    assert again['values']['rule_source'] == 'adopted'
    # Another rule adopted later: stale again; the stale diagnostics never block the opening.
    flow.decide('policy', 'capacity:30',
                words='Yes, I adopt thirty instead because the desk is smaller')
    state = flow.state()
    assert not st.is_current(state, 'diag.binary')
    assert any('diag.binary' in i['stale_slots'] for i in state['invalidations'])
    from mlkit.study import preconditions as pre
    assert not [m for m in pre.final_test_missing(state) if m['requirement'] == 'nothing_stale']
    # A refit of the candidate makes them stale through lineage (and the code fingerprint).
    flow.run('diag.binary')
    flow.decide('preprocessing', {'missing': 'indicator', 'rare_category_min_rows': 0,
                                  'caps': {}, 'log_transform': []},
                words='Yes, add missing indicators because some values are missing')
    assert not read.open(flow.study).is_current('diag.binary')


def test_final_diagnostics_only_after_the_opening(tmp_path, monkeypatch):
    flow = _ready(tmp_path)
    flow.run('policy.evaluate', '--rule', 'capacity:40')
    flow.decide('policy', 'capacity:40',
                words='Yes, I adopt that rule because the desk can make that many calls')
    flow.run('diag.binary')
    final = set(fk.partition_keys(flow.study, 'final_test'))
    reads = []
    real = dt.load_final_test

    def load_final(case, keys):
        reads.append(read.open(flow.study).state['partition']['status'])
        return real(case, keys)

    monkeypatch.setattr(dt, 'load_final_test', load_final)
    # Sealed: refused, nothing read, nothing recorded.
    out = flow.run('diag.final_test', expect=2)
    assert out['error']['code'] == 'precondition_missing'
    assert out['error']['details']['missing'][0]['requirement'] == 'final_test_opened'
    assert reads == [] and not _records(flow, 'diag.final_test')
    view = flow.view()
    assert 'diag.final_test' not in view['results']
    _open(flow)
    assert reads == ['opened']          # the one evaluation of the final test
    out = flow.run('diag.final_test')
    assert reads == ['opened', 'opened']
    values = out['values']
    assert tuple(values) == dg.FINAL_BINARY_KEYS
    assert values['evidence'] == 'final' and values['purpose'] == 'final_evaluation'
    assert values['partition'] == 'final_test' and values['n'] == len(final)
    assert values['note'] == dg.FINAL_NOTE
    model = values['model']
    d = values['models'][model]
    assert set(values['models']) == {model}
    assert tuple(d) == tuple(k for k in dg.BINARY_MODEL_KEYS if k != 'coefficients')
    assert values['rule'] == read.open(flow.study).current('final_test.evaluation')[
        'output']['values']['rule_final']
    for kind in ('false_positives', 'false_negatives'):
        assert {i['row_key'] for i in d['examples'][kind]} <= final
    [record] = _records(flow, 'diag.final_test')
    assert (record['purpose'], record['partition']) == ('final_evaluation', 'final_test')
    assert set(read.open(flow.study).blob(record['row_keys']).decode().split()) == final
    # The development diagnostics stay current, computed before the opening.
    view = flow.view()
    assert view['results']['diag.binary']['current'] is True
    assert view['results']['diag.binary']['started_revision'] < \
        view['final_test']['opening']['revision']
    # Diagnostics are not "a change after the final test".
    assert not view['final_test']['post_final_test']


def test_regression_diagnostics(tmp_path):
    flow = _ready(tmp_path, task='regression', n_rows=500)
    values = flow.run('diag.regression')['values']
    assert tuple(values) == dg.REGRESSION_KEYS
    assert set(values['models']) == {'fit.linear', 'fit.variant'}
    assert all(tuple(d) == dg.REGRESSION_MODEL_KEYS for d in values['models'].values())
    assert values['smearing'] == {'applies': False, 'implemented': False,
                                  'note': dg.SMEARING_NOTE}
    assert values['target_transform'] is None and 'Lumley' in values['normality_note']
    study = read.open(flow.study)
    for model, d in values['models'].items():
        preds = study.predictions(study.current(model)['result_id'])
        r = preds['y'].to_numpy(dtype=float) - preds['prediction'].to_numpy(dtype=float)
        assert d['residuals']['mean'] == pytest.approx(r.mean())
        assert d['errors']['mae'] == pytest.approx(np.abs(r).mean())
        assert len(d['qq']['points']) == len(dg.QQ_PROBABILITIES)
        assert sum(b['n'] for b in d['by_prediction']['bins']) == len(r)
        h = d['heteroscedasticity']
        assert -1 <= h['abs_residual_prediction_correlation'] <= 1 and 'flag' in h
        assert d['scatter']['n_shown'] == min(dg.SCATTER_POINTS, len(r))
        assert len(d['examples']['largest_errors']) == dg.MAX_EXAMPLES
        biggest = max(abs(x) for x in r)
        assert abs(d['examples']['largest_errors'][0]['residual']) == pytest.approx(biggest)
        for block in d['by_feature']:
            assert sum(g['n'] for g in block['groups']) == len(r)
        assert d['coefficients']['terms']
    assert flow.run('diag.binary', expect=2)['error']['code'] == 'invalid_arguments'


def test_report_section_is_cited_and_the_notebook_recomputes(tmp_path):
    flow = _ready(tmp_path)
    flow.run('policy.evaluate', '--rule', 'capacity:40')
    flow.decide('policy', 'capacity:40',
                words='Yes, I adopt that rule because the desk can make that many calls')
    flow.run('diag.binary')
    flow.call('render', '--study', flow.study)
    page = (flow.study / 'reports' / 'study.html').read_text()
    assert 'id="diagnostics"' in page and 'data-chart="diag_gain"' in page
    assert 'data-chart="diag_calibration"' in page and 'data-final="sealed"' in page
    assert 'Development evidence' in page and 'Final evidence' in page
    check = flow.call('check', '--study', flow.study)
    assert check['clean'] is True, check['findings']
    _open(flow)
    flow.run('diag.final_test')
    flow.call('render', '--study', flow.study)
    page = (flow.study / 'reports' / 'study.html').read_text()
    assert 'data-evidence="final"' in page and 'data-opening="before"' in page
    check = flow.call('check', '--study', flow.study)
    assert check['clean'] is True, check['findings']
    notebook = flow.study / 'notebooks' / 'study_generated.py'
    text = notebook.read_text()
    assert 'recompute_dev_diagnostics' in text and 'recompute_final_diagnostics' in text
    run = subprocess.run([sys.executable, str(notebook)], capture_output=True, text=True,
                         cwd=flow.study, env=dict(fk.env(), HYPOTRAIL_READ_ONLY='1'),
                         timeout=300)
    assert run.returncode == 0, run.stderr[-3000:]
    assert "'true_positives'" in run.stdout
