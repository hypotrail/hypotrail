"""WP-B6a: a coefficient and its bootstrap interval come from the same fit on the same design.

The captured cross-validated Bank ``diag.binary`` showed ``cat__poutcome_unknown`` at -0.484
with a bootstrap interval of [-0.176, -0.101]. Cause: the fit used scikit-learn's default
L-BFGS, which stopped (tolerance 1e-4) along the nearly flat direction that a full one-hot
encoding and the intercept share, while the replicates (Newton-Cholesky, warm-started) reached
the optimum of the same penalised likelihood (-0.136). Fix: new logistic fits record and use
Newton-Cholesky with a tight tolerance; the diagnostics refit the stored model on the same
prepared rows and flag a point that is not that fit (``point_check``).

Studies and cases live in ``tmp_path``; the Bank case is only read.
"""
from __future__ import annotations

import pytest

from mlkit.study import activities, case as c, data as dt, diagnostics as dg, read

import flowkit as fk
from flowkit import Flow
from mlkit.study import state as st
from mlkit.study.store import StudyStore


def _bank_cv(tmp_path) -> Flow:
    flow = Flow(tmp_path / 'study', fk.BANK, prefix='c')
    flow.init()
    flow.decide('prediction_time', 'before the first contact of the campaign, from the client file')
    flow.decide('feature_availability', fk.availability(
        fk.BANK, duration='not_available', day='not_available', month='not_available',
        campaign='not_available', contact='uncertain_included'))
    flow.decide('split', st.b1_default_value(flow.state(), 'split'))
    flow.model_decisions()
    for activity in ('split', 'fit.baseline', 'fit.logistic'):
        flow.run(activity)
    flow.variant()
    return flow


def test_bank_cv_coefficients_lie_inside_their_own_intervals(tmp_path):
    flow = _bank_cv(tmp_path)
    values = flow.run('diag.binary')['values']
    study = read.open(flow.study)
    for model, d in values['models'].items():
        entry = study.current(model)
        assert entry['params']['solver'] == activities.LOGISTIC_SOLVER
        coef = d['coefficients']
        assert coef['point_check']['consistent'] is True
        assert coef['point_check']['misaligned_terms'] == []
        assert coef['point_check']['max_difference'] <= dg.POINT_TOLERANCE
        terms = {t['term']: t for t in coef['terms']}
        # The stored fit's values, every one inside its own interval (the reported bug).
        assert {k: t['value'] for k, t in terms.items()} == pytest.approx(
            entry['output']['values']['coefficients'])
        assert all(t['inside_interval'] is True for t in coef['terms']), \
            [t for t in coef['terms'] if not t['inside_interval']]
        assert terms['cat__poutcome_unknown']['low'] <= terms['cat__poutcome_unknown']['value'] \
            <= terms['cat__poutcome_unknown']['high']
        # At the optimum of an L2-penalised fit with a free intercept, the two one-hot terms
        # of a two-valued variable are opposite (shifting them to the intercept costs penalty).
        assert terms['cat__loan_yes']['value'] == pytest.approx(-terms['cat__loan_no']['value'],
                                                                abs=1e-6)


def _synthetic(tmp_path):
    case_dir = fk.make_case(tmp_path / 'case', task='binary', n_rows=600)['case'].parent
    flow = Flow(tmp_path / 'study', case_dir)
    flow.init()
    flow.decide('prediction_time', 'when the record is created, before the outcome')
    flow.decide('feature_availability', fk.availability(case_dir))
    flow.decide('split', flow.view()['next_action']['default_value'])
    flow.model_decisions()
    flow.run('split')
    flow.run('fit.logistic')
    return flow, case_dir


def _inputs(flow, case_dir):
    store = StudyStore(flow.study)
    study = read.open(flow.study)
    entry = study.current('fit.logistic')
    case = c.load_case(case_dir)
    keys = activities.split_keys(store, study.current('split')['result_id'])['train']
    development = fk.partition_keys(flow.study, 'development')
    frame = dt.load_development(case, development).frame.loc[keys]
    return case, frame, entry


def test_a_point_that_is_not_the_fit_on_the_same_design_is_flagged(tmp_path):
    flow, case_dir = _synthetic(tmp_path)
    case, frame, entry = _inputs(flow, case_dir)
    point = dict(entry['output']['values']['coefficients'])
    same = dg.coefficient_intervals(case, frame, activities._model_inputs(entry), entry['params'],
                                    True, point, replicates=20)
    assert same['point_check']['consistent'] is True
    term = sorted(point)[0]
    point[term] += 0.5
    off = dg.coefficient_intervals(case, frame, activities._model_inputs(entry), entry['params'],
                                   True, point, replicates=20)
    check = off['point_check']
    assert check['consistent'] is False and check['note'] == dg.POINT_INCONSISTENT_NOTE
    assert check['max_difference'] == pytest.approx(0.5, abs=1e-6)
    # The intervals are those of the same design: unchanged by the stored point.
    a = {t['term']: (t['low'], t['high']) for t in same['terms']}
    b = {t['term']: (t['low'], t['high']) for t in off['terms']}
    assert a == b


def test_a_fit_recorded_with_the_old_solver_is_flagged_not_hidden(tmp_path):
    """A result recorded before WP-B6a (no ``solver`` in its params) keeps L-BFGS: its point
    is compared with the optimum the replicates reach, and a gap is reported."""
    flow, case_dir = _synthetic(tmp_path)
    case, frame, entry = _inputs(flow, case_dir)
    params = {k: v for k, v in entry['params'].items() if k not in ('solver', 'tol')}
    from mlkit.study import fit
    model = fit._fit_predict(case, frame, frame.iloc[:1], activities._model_inputs(entry),
                             params, True)[1]
    names = [str(n) for n in model['preprocess'].get_feature_names_out()]
    point = dict(zip(names, (float(v) for v in model['model'].coef_[0])))
    out = dg.coefficient_intervals(case, frame, activities._model_inputs(entry), params, True,
                                   point, replicates=20)
    check = out['point_check']
    assert check['misaligned_terms'] == []
    assert check['consistent'] == (check['max_difference'] <= dg.POINT_TOLERANCE)
    assert all(t['inside_interval'] == (t['low'] <= t['value'] <= t['high'])
               for t in out['terms'])


def test_new_logistic_fits_record_the_solver(tmp_path):
    flow, _ = _synthetic(tmp_path)
    params = read.open(flow.study).current('fit.logistic')['params']
    assert (params['solver'], params['tol']) == (activities.LOGISTIC_SOLVER, activities.LOGISTIC_TOL)
