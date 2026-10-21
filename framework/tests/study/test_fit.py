"""Baseline and logistic fits with persisted predictions (plan WP2.3, §3.4, §7 ``test_fit``).

Bank and the synthetic case go through the same flows. Studies live in ``tmp_path``.
"""
from __future__ import annotations

import gzip
import json
import subprocess
import sys

import numpy as np
import pytest

from mlkit.study import activities as act, case as c, executions as ex, fit, metrics, read
from mlkit.study import store as sto
from mlkit.study.errors import StudyError
from mlkit.reliability import CommandRefused

import flowkit as fk
from flowkit import Flow


@pytest.fixture(scope='module')
def cases(tmp_path_factory):
    return {'bank': fk.BANK,
            'synthetic': fk.make_case(tmp_path_factory.mktemp('synthetic'),
                                      n_rows=4000)['case'].parent}


@pytest.fixture(scope='module')
def prepared(tmp_path_factory, cases):
    return {name: fk.prepare(path, tmp_path_factory.mktemp(name) / 'study', upto='fits')
            for name, path in cases.items()}


@pytest.fixture(params=['bank', 'synthetic'])
def flow(request, tmp_path, prepared, cases):
    f = Flow(fk.clone(prepared[request.param], tmp_path / 'study'), cases[request.param])
    f.name = request.param
    return f


def _split(study):
    s = read.open(study)
    entry = s.current('split')
    return {p: s.blob(entry['blobs'][p]).decode().split() for p in ('train', 'validation')}


def test_predictions_are_persisted_and_readable_through_read(flow):
    s = read.open(flow.study)
    split = _split(flow.study)
    for slot in ('fit.baseline', 'fit.logistic'):
        entry = s.current(slot)
        assert s.is_current(slot) and entry['partition'] == 'validation'
        frame = s.predictions(entry['result_id'])
        assert list(frame.columns) == ['row_key', 'y', 'score']
        assert set(frame['row_key']) == set(split['validation'])
        assert len(frame) == entry['n_rows'] == len(split['validation'])
        meta = entry['output']['values']['predictions']
        assert meta['n'] == len(frame) and meta['n_positive'] == int(frame['y'].sum())
        assert meta['partition'] == 'validation' and 'not assessed' in meta['score_semantics']
        assert meta['positive_label'] == c.load_case(flow.case_dir).positive_label
        assert entry['output']['values']['validation']['roc_auc'] == pytest.approx(
            metrics.roc_auc(frame['y'], frame['score']))
    if flow.name == 'bank':
        assert (meta['n'], meta['n_positive']) == (1086, 125)   # v0.1: 1357, 156 (ADR 0006)


def test_constant_baseline_is_the_training_prior(flow):
    s = read.open(flow.study)
    entry = s.current('fit.baseline')
    values = entry['output']['values']
    frame = s.predictions(entry['result_id'])
    assert frame['score'].nunique() == 1
    assert frame['score'].iloc[0] == values['train_rate'] == \
        values['n_train_positive'] / values['n_train']
    assert values['features'] == [] and values['validation']['roc_auc'] == 0.5
    assert values['validation']['average_precision'] == pytest.approx(frame['y'].mean())
    if flow.name == 'bank':
        assert (values['n_train_positive'], values['n_train']) == (292, 2531)   # v0.1: 365, 3164


def test_baseline_needs_no_scikit_learn(flow):
    """A fresh process fits the baseline on a new split without importing sklearn."""
    flow.decide('split', {**fk.SPLIT, 'seed': 5})          # the baseline becomes stale
    flow.run('split')                                       # (sklearn runs in this process)
    code = ('import json, sys\n'
            'from mlkit.study import executions, read\n'
            f'study = {str(flow.study)!r}\n'
            'rev = read.open(study).revision\n'
            'out = executions.run(study, "fit.baseline", {}, request_id="fresh-baseline",\n'
            '                     expected_revision=rev).payload\n'
            'print(json.dumps([out["status"], "sklearn" in sys.modules]))\n')
    proc = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                          env=fk.env(), timeout=300)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.strip().splitlines()[-1]) == ['promoted', False]


def test_logistic_uses_only_available_features_and_flags_special_values(flow):
    case = c.load_case(flow.case_dir)
    entry = read.open(flow.study).current('fit.logistic')
    availability = flow.state()['decisions']['feature_availability']['value']
    used = [v['name'] for v in case.document['variables'] if v['role'] == 'feature'
            and availability[v['name']] in ('available_at_prediction', 'uncertain_included')]
    assert entry['inputs']['features'] == entry['output']['values']['features'] == used
    excluded = [f for f, v in availability.items() if v == 'not_available']
    assert excluded and not set(excluded) & set(used)
    numeric_specials = [f'{s["column"]}={s["value"]}' for s in case.document['special_values']
                        if s['column'] in used
                        and case.variables[s['column']]['type'] in ('integer', 'numeric')]
    assert entry['output']['values']['special_value_indicators'] == numeric_specials
    assert {f'num__{n}' for n in numeric_specials} <= set(entry['output']['values']['coefficients'])
    if flow.name == 'bank':
        assert 'duration' in excluded and 'duration' not in used
        assert numeric_specials == ['pdays=-1']
        assert entry['output']['values']['validation']['roc_auc'] > 0.6


def test_fits_record_train_fit_and_validation_model_evaluation_exposure(flow):
    s = read.open(flow.study)
    split = _split(flow.study)
    for slot in ('fit.baseline', 'fit.logistic'):
        entry = s.current(slot)
        records = [r for r in s.exposure_records() if r['result_id'] == entry['result_id']]
        assert [(r['purpose'], r['partition'], r['n_rows']) for r in records] == [
            ('train_fit', 'train', len(split['train'])),
            ('validation_model_evaluation', 'validation', len(split['validation']))]
        assert entry['exposure_id'] == records[-1]['exposure_id']
    assert s.exposure_summary()['validation_rows_used_for_selection'] == len(split['validation'])


def test_changing_exclusions_makes_logistic_stale_but_not_baseline(flow):
    state = flow.state()
    baseline, logistic = state['current']['fit.baseline'], state['current']['fit.logistic']
    used = read.open(flow.study).current('fit.logistic')['inputs']['features']
    drop = used[-1]
    flow.decide('feature_availability', fk.availability(flow.case_dir, **{drop: 'not_available'}),
                words=f'Yes, I exclude {drop} because it is not known in time')
    state = flow.state()
    assert logistic in state['stale'] and baseline not in state['stale']
    assert state['invalidations'][-1]['mutation'] == 'feature_availability.feature_set'
    assert flow.run('fit.baseline')['status'] == 'already_current'
    fresh = flow.run('fit.logistic')
    assert fresh['status'] == 'promoted' and drop not in fresh['values']['features']
    # Wording only (same feature set): nothing becomes stale.
    other = [f for f, v in fk.availability(flow.case_dir).items() if v == 'not_available'][0]
    flow.decide('feature_availability',
                fk.availability(flow.case_dir, **{drop: 'not_available', other: 'uncertain_excluded'}),
                words=f'Yes, {other} is uncertain and stays excluded, {drop} too')
    state = flow.state()
    assert state['invalidations'][-1]['mutation'] == 'feature_availability.wording'
    assert fresh['result_id'] not in state['stale']


def test_a_candidate_feature_without_availability_decision_is_refused(flow):
    state = flow.state()
    availability = state['decisions']['feature_availability']['value']
    missing = sorted(availability)[0]
    del availability[missing]
    with pytest.raises(CommandRefused) as info:
        act.plan(sto.StudyStore(flow.study), state, 'fit.logistic', {})
    assert info.value.code == 'precondition_missing'
    assert info.value.details['missing'] == [{
        'requirement': 'availability_decision', 'feature': missing,
        'detail': 'Every candidate feature needs an availability decision before a model may '
                  'use or ignore it.'}]
    act.plan(sto.StudyStore(flow.study), state, 'fit.baseline', {})   # uses no feature


def test_a_late_fit_after_an_availability_change_is_stored_not_promoted(flow):
    flow.decide('split', {**fk.SPLIT, 'seed': 99})
    flow.run('split')
    used = act.used_features(act.case_of(flow.state()),
                             flow.state()['decisions']['feature_availability']['value'])[0]

    def meanwhile(plan):
        flow.decide('feature_availability',
                    fk.availability(flow.case_dir, **{used[0]: 'not_available'}),
                    words=f'Yes, I now exclude {used[0]} from the model')

    payload = ex.run(flow.study, 'fit.logistic', {}, request_id='late-fit',
                     expected_revision=flow.rev(), hooks={'before_promote': meanwhile}).payload
    assert payload['status'] == 'late_not_promoted'
    entry = read.open(flow.study).result(payload['result_id'])
    assert used[0] in entry['inputs']['features']
    assert flow.state()['current']['fit.logistic'] != payload['result_id']
    assert read.open(flow.study).predictions(payload['result_id']).shape[0] == entry['n_rows']


def test_replaying_a_fit_request_does_not_fit_again(flow):
    flow.decide('split', {**fk.SPLIT, 'seed': 3})
    flow.run('split')
    rev = flow.rev()
    first = flow.call('run', 'fit.logistic', '--request-id', 'fit-once', '--expected-revision',
                      rev, '--study', flow.study)
    entries = fk.registry_entries(flow.study)
    replay = flow.call('run', 'fit.logistic', '--request-id', 'fit-once', '--expected-revision',
                       rev, '--study', flow.study)
    assert replay['replayed'] is True and replay['result_id'] == first['result_id']
    assert fk.registry_entries(flow.study) == entries
    fits = [e for e in entries if e['activity'] == 'fit.logistic']
    assert len({e['execution_id'] for e in fits}) == len(fits)


def test_fits_are_deterministic(flow):
    s = read.open(flow.study)
    store = sto.StudyStore(flow.study)
    plan = act.plan(store, s.state, 'fit.logistic', {})
    again = act.compute(store, plan)
    entry = s.current('fit.logistic')
    assert again['values'] == entry['output']['values']
    assert sto.hashlib.sha256(again['blobs']['predictions']).hexdigest() == \
        entry['blobs']['predictions']
    assert plan['input_key'] == entry['input_key']


def test_read_only_environment_makes_fits_raise(flow, monkeypatch):
    s = read.open(flow.study)
    case, dataset = act.load(act.plan(sto.StudyStore(flow.study), s.state, 'fit.baseline', {}),
                             sto.StudyStore(flow.study))
    split = _split(flow.study)
    train, validation = act.rows(dataset, split['train']), act.rows(dataset, split['validation'])
    monkeypatch.setenv('HYPOTRAIL_READ_ONLY', '1')
    for call in (lambda: fit.baseline(case, train, validation),
                 lambda: fit.logistic(case, train, validation,
                                      s.current('fit.logistic')['inputs'],
                                      s.current('fit.logistic')['params'])):
        with pytest.raises(StudyError) as info:
            call()
        assert info.value.code == 'read_only'


def test_predictions_blob_format():
    blob = fit.predictions_blob(['L2', 'L10'], [1, 0], [0.25, 1 / 3])
    assert blob == fit.predictions_blob(['L2', 'L10'], [1, 0], [0.25, 1 / 3])
    assert gzip.decompress(blob).decode() == 'row_key,y,score\nL2,1,0.25\nL10,0,0.3333333333333333\n'


@pytest.mark.parametrize('seed', [0, 1, 2])
def test_metrics_match_scikit_learn_with_and_without_ties(seed):
    from sklearn.metrics import average_precision_score, roc_auc_score
    rng = np.random.default_rng(seed)
    y = (rng.random(500) < 0.2).astype(int)
    for score in (rng.random(500), np.round(rng.random(500), 1), np.full(500, 0.3)):
        assert metrics.roc_auc(y, score) == pytest.approx(roc_auc_score(y, score), abs=1e-12)
        assert metrics.average_precision(y, score) == pytest.approx(
            average_precision_score(y, score), abs=1e-12)
    assert metrics.roc_auc([1, 1], [0.1, 0.2]) is None
    assert metrics.average_precision([0, 0], [0.1, 0.2]) is None
