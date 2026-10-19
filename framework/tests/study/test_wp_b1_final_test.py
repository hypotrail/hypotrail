"""WP-B1 (ADR 0006 amendment): cross-validation on the development rows, one analytical
variant, and the opening of the sealed final test, once.

* the cross-validation scheme of the ``split`` decision: folds, out-of-fold predictions of
  every development row (preparation learnt per fold), the spread across folds, exposure;
* the variant: decided in the junior's words, fitted under the same protocol, compared
  with the candidate (paired), selectable by the choice, counted in ``trials``;
* the final test: the guard (scored exactly once, only after the opening decision, by one
  reader), the refusals (before the choice, stale, delegated, without a reason, twice),
  an interrupted opening consumes it, and a later change is "after the final test".

Studies and cases live in ``tmp_path``; Auto MPG is only read.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from mlkit.study import activities as act, case as c, data as dt, executions, fit, partition
from mlkit.study import read, records as rec, state as st, store as sto

import flowkit as fk
from flowkit import Flow

AUTO = fk.REPO / 'use-cases' / 'auto-mpg'
CV = {'method': 'kfold_stratified', 'folds': 5, 'seed': 11}
OPEN_WORDS = 'Yes, I open the final test now, because the model and the rule are fixed'


def _flow(tmp_path, task='binary', n_rows=600, split=None) -> Flow:
    case_dir = fk.make_case(tmp_path / 'case', task=task, n_rows=n_rows)['case'].parent
    flow = Flow(tmp_path / 'study', case_dir)
    flow.init()
    flow.decide('prediction_time', 'when the record is created, before the outcome')
    flow.decide('feature_availability', fk.availability(case_dir))
    if split is None:
        split = flow.view()['next_action']['default_value']
    flow.decide('split', split)
    flow.model_decisions()
    flow.run('split')
    return flow


def _choose(flow, value=None):
    task = flow.state()['task']
    if task == 'binary':
        flow.run('policy.evaluate', '--rule', 'capacity:40')
        flow.decide('policy', value or 'capacity:40',
                    words='Yes, I adopt that rule because the desk can make that many calls')
    else:
        flow.run('evaluate.regression')
        flow.decide('model_choice', value or 'fit.linear',
                    words='Yes, I choose that model because its error is smaller')


def _propose_final(flow, value=None):
    value = value if value is not None else st.b1_default_value(flow.state(), 'final_test')
    return flow.call('decide', 'propose', 'final_test', '--value-json', json.dumps(value),
                     '--restatement', 'You open the sealed final test once, for the chosen '
                                      'configuration.',
                     '--rationale', 'Everything is chosen.', '--request-id', flow.rid(),
                     '--expected-revision', flow.rev(), '--study', flow.study, expect=None)


def _confirm(flow, pid, words=OPEN_WORDS, expect=0, *extra):
    return flow.call('decide', 'confirm', pid, '--user-words', words, *extra,
                     '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                     '--study', flow.study, expect=expect)


def _ready(tmp_path, task='binary') -> Flow:
    flow = _flow(tmp_path, task)
    flow.run('fit.baseline')
    flow.run('fit.linear' if task == 'regression' else 'fit.logistic')
    flow.variant()
    _choose(flow)
    return flow


# --- the evaluation scheme ---------------------------------------------------------------

def test_a_new_study_has_nine_decisions_and_drafts_cross_validation(tmp_path):
    case_dir = fk.make_case(tmp_path / 'case', n_rows=300)['case'].parent
    flow = Flow(tmp_path / 'study', case_dir)
    flow.init()
    state = flow.state()
    assert set(state['decisions']) == set(st.B1_DECISION_IDS)
    assert st.decision_ids(state) == st.B1_DECISION_IDS == (
        'prediction_time', 'feature_availability', 'split', 'success_criterion',
        'preprocessing', 'model_variant', 'policy', 'final_test', 'conclusion')
    assert [s['id'] for s in flow.view()['plan']] == list(st.B1_STEP_IDS) == [
        'discover_data', 'prediction_time', 'feature_availability', 'split',
        'success_criterion', 'train_eda', 'preprocessing', 'models', 'model_variant', 'policy',
        'final_test', 'conclusion']
    flow.decide('prediction_time', 'when the record is created, before the outcome')
    flow.decide('feature_availability', fk.availability(case_dir))
    action = flow.view()['next_action']
    assert action['decision'] == 'split'
    assert action['default_value'] == {'method': 'kfold_stratified', 'folds': 5,
                                       'seed': st.DEFAULT_CV_SEED}
    assert 'final_test_sealed' in {x['id'] for x in flow.view()['not_yet_defensible']}


@pytest.mark.parametrize('value, field', [
    ({'method': 'kfold_stratified', 'folds': 2, 'seed': 1}, 'folds'),
    ({'method': 'kfold_stratified', 'folds': 5, 'seed': 'x'}, 'seed'),
])
def test_an_invalid_scheme_is_refused(tmp_path, value, field):
    case_dir = fk.make_case(tmp_path / 'case', n_rows=300)['case'].parent
    flow = Flow(tmp_path / 'study', case_dir)
    flow.init()
    flow.decide('prediction_time', 'when the record is created, before the outcome')
    flow.decide('feature_availability', fk.availability(case_dir))
    out = flow.call('decide', 'propose', 'split', '--value-json', json.dumps(value),
                    '--restatement', 'Folds.', '--rationale', 'x', '--request-id', flow.rid(),
                    '--expected-revision', flow.rev(), '--study', flow.study, expect=2)
    assert out['error']['code'] == 'invalid_value'
    assert out['error']['details']['field'] == field
    wrong = {'method': 'kfold_quantile', 'folds': 5, 'seed': 1}
    out = flow.call('decide', 'propose', 'split', '--value-json', json.dumps(wrong),
                    '--restatement', 'Folds.', '--rationale', 'x', '--request-id', flow.rid(),
                    '--expected-revision', flow.rev(), '--study', flow.study, expect=2)
    assert out['error']['code'] == 'invalid_value'      # a binary target is stratified


def test_folds_out_of_fold_predictions_and_spread(tmp_path):
    flow = _flow(tmp_path, split=CV)
    s = read.open(flow.study)
    split = s.current('split')
    values = split['output']['values']
    development = fk.partition_keys(flow.study, 'development')
    final = set(fk.partition_keys(flow.study, 'final_test'))
    assert values['scheme'] == 'cross_validation' and values['folds'] == 5
    assert sum(f['n_rows'] for f in values['fold_rows']) == len(development) == values['n_rows']
    rates = [f['rate'] for f in values['fold_rows']]
    assert max(rates) - min(rates) < 0.02                       # stratified on the outcome
    store = sto.StudyStore(flow.study)
    folds = act.fold_assignment(store, split['result_id'])
    assert sorted(folds) == sorted(development) and not final & set(folds)
    keys = act.split_keys(store, split['result_id'])
    assert set(keys['train']) == set(keys['validation']) == set(development)
    flow.run('eda.target_rate')
    run = flow.run('fit.logistic')
    v = run['values']
    assert v['evaluation'] == 'out_of_fold' and v['predictions']['partition'] == 'development'
    assert len(v['cross_validation']['per_fold']) == 5
    spread = v['cross_validation']['spread']['roc_auc']
    per_fold = [f['roc_auc'] for f in v['cross_validation']['per_fold']]
    assert spread['min'] == min(per_fold) and spread['max'] == max(per_fold)
    assert abs(spread['mean'] - float(np.mean(per_fold))) < 1e-12
    preds = act.read_predictions(store, run['result_id'])
    assert sorted(preds['row_keys']) == sorted(development)       # every row once
    # Fold 1 is predicted by a model fitted on the other folds only.
    entry = s.result(run['result_id'])
    case = c.load_case(flow.case_dir)
    frame = dt.load_development(case, development).frame
    held = [k for k in frame.index if folds[k] == 1]
    rest = [k for k in frame.index if folds[k] != 1]
    expected = fit._fit_predict(case, frame.loc[rest], frame.loc[held], entry['inputs'],
                                entry['params'], True)[0]
    got = dict(zip(preds['row_keys'], preds['score']))
    assert np.allclose([got[k] for k in held], expected, atol=1e-12)
    in_sample = fit._fit_predict(case, frame, frame.loc[held], entry['inputs'],
                                 entry['params'], True)[0]
    assert not np.allclose([got[k] for k in held], in_sample)
    looks = flow.view()['exposure']['by_partition']['development']
    assert {'cross_validated_fit', 'out_of_fold_evaluation', 'train_eda'} <= set(looks)
    assert looks['cross_validated_fit'] == len(development)


def test_a_regression_study_uses_quantile_folds_and_temporal_folds_with_a_time_column(tmp_path):
    flow = _flow(tmp_path / 'r', task='regression', n_rows=400)
    assert flow.state()['decisions']['split']['value']['method'] == 'kfold_quantile'
    flow.run('fit.baseline')
    run = flow.run('fit.linear')
    assert set(run['values']['cross_validation']['spread']) == {'mae', 'rmse'}
    auto = Flow(tmp_path / 'auto', AUTO)
    auto.init()
    auto.decide('prediction_time', 'when the car is listed')
    auto.decide('feature_availability', fk.availability(AUTO))
    default = auto.view()['next_action']['default_value']
    assert default['method'] == 'temporal_folds'
    auto.decide('split', default)
    auto.model_decisions()
    values = auto.run('split')['values']
    ranges = values['fold_ranges']
    assert values['order_column'] == 'model_year' and values['seed'] is None
    assert all(a['max'] <= b['min'] for a, b in zip(ranges, ranges[1:]))     # in time order


# --- the variant ------------------------------------------------------------------------------

def test_the_variant_is_compared_with_the_candidate_and_can_be_chosen(tmp_path):
    flow = _flow(tmp_path, split=CV)
    flow.run('fit.baseline')
    flow.run('fit.logistic')
    refused = flow.run('policy.evaluate', '--rule', 'capacity:40', expect=2)
    assert refused['error']['code'] == 'precondition_missing'
    assert {'decision': 'model_variant'}.items() <= refused['error']['details']['missing'][0].items()
    assert flow.view()['trials']['count'] == 1
    flow.variant({'kind': 'regularisation', 'strength': 'weak'})
    variant = read.open(flow.study).current('fit.variant')
    assert variant['params']['C'] == act.VARIANT_C['weak'] == 10.0
    assert variant['output']['values']['variant'] == {'kind': 'regularisation', 'strength': 'weak'}
    assert flow.view()['trials']['count'] == 2
    values = flow.run('policy.evaluate', '--rule', 'capacity:40')['values']
    item = values['rules']['capacity:40']
    assert set(item['models']) == {'fit.baseline', 'fit.logistic', 'fit.variant'}
    comparison = item['comparisons']['fit.variant']
    assert comparison['reference'] == 'fit.logistic'
    point = item['models']['fit.variant']['precision'] - item['models']['fit.logistic']['precision']
    assert abs(comparison['precision']['point'] - point) < 1e-12
    assert comparison['precision']['low'] <= comparison['precision']['high']
    assert item['capacity_share'] == 40 / values['n']
    assert values['evaluation'] == 'out_of_fold' and set(values['ranking']) == set(item['models'])
    flow.decide('policy', 'capacity:40 @ fit.variant',
                words='Yes, I adopt the variant at that rule because it finds as many')
    assert flow.state()['decisions']['policy']['value'] == 'capacity:40@fit.variant'
    criterion = flow.view()['criterion']
    assert criterion['model'] == 'fit.variant' and criterion['rule'] == 'capacity:40'
    gain = 100 * item['deltas']['fit.variant']['precision']['point']
    assert abs(criterion['gain'] - gain) < 1e-9
    assert st.b1_default_value(flow.state(), 'final_test') == {'model': 'fit.variant',
                                                               'rule': 'capacity:40'}
    # A new variant refits the variant only and asks for the choice again.
    p = flow.call('decide', 'propose', 'model_variant', '--value-json',
                  json.dumps({'kind': 'regularisation', 'strength': 'strong'}),
                  '--restatement', 'A stronger regularisation.', '--rationale', 'x',
                  '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                  '--study', flow.study)
    out = _confirm(flow, p['result']['proposal_id'], 'I confirm the stronger regularisation')
    assert out['result']['invalidation']['mutation'] == 'model_variant'
    assert out['result']['invalidation']['row'] == 17
    assert out['result']['invalidation']['stale_slots'] == ['fit.variant', 'policy.evaluation']
    assert out['result']['invalidation']['reconfirm_required'] == ['policy']


def test_a_drop_group_variant_and_a_variant_model_choice(tmp_path):
    auto = Flow(tmp_path / 'auto', AUTO)
    auto.init()
    auto.decide('prediction_time', 'when the car is listed')
    auto.decide('feature_availability', fk.availability(AUTO))
    auto.decide('split', auto.view()['next_action']['default_value'])
    auto.model_decisions()
    auto.run('split')
    auto.run('fit.baseline')
    auto.run('fit.linear')
    bad = auto.call('decide', 'propose', 'model_variant', '--value-json',
                    json.dumps({'kind': 'drop_group', 'group': 'Wheels'}), '--restatement',
                    'x', '--rationale', 'x', '--request-id', auto.rid(), '--expected-revision',
                    auto.rev(), '--study', auto.study, expect=2)
    assert bad['error']['code'] == 'invalid_value' and 'Engine' in bad['error']['details']['groups']
    auto.variant({'kind': 'drop_group', 'group': 'Engine'})
    values = read.open(auto.study).current('fit.variant')['output']['values']
    assert values['dropped_group'] == 'Engine'
    assert not {'cylinders', 'displacement', 'horsepower'} & set(values['features'])
    evaluation = auto.run('evaluate.regression')['values']
    assert evaluation['comparisons']['fit.variant']['reference'] == 'fit.linear'
    auto.decide('model_choice', 'fit.variant',
                words='Yes, I choose the variant because it needs fewer measurements')
    assert auto.view()['criterion']['model'] == 'fit.variant'


def test_a_study_created_before_wp_b1_has_no_variant(tmp_path):
    case_dir = fk.make_case(tmp_path / 'case', n_rows=300)['case'].parent
    store = sto.StudyStore(tmp_path / 'study')
    state = st.initial_state(c.load_case(case_dir))
    for d in st.WP_B1_DECISIONS:
        state['decisions'].pop(d)
    for d, dec in state['decisions'].items():
        dec['depends_on'] = list(st.FULL_DEPENDS_ON_BY_TASK['binary'][d])
    store.create(state)
    flow = Flow(tmp_path / 'study', case_dir)
    assert st.validate_state(flow.state()) == []
    assert st.decision_ids(flow.state()) == st.FULL_DECISION_IDS
    flow.pauses()
    flow.run('split')
    out = flow.run('fit.variant', expect=2)
    assert out['error']['code'] == 'invalid_arguments'
    out = flow.call('decide', 'propose', 'split', '--value-json', json.dumps(CV),
                    '--restatement', 'Folds.', '--rationale', 'x', '--request-id', flow.rid(),
                    '--expected-revision', flow.rev(), '--study', flow.study, expect=2)
    assert out['error']['code'] == 'unsupported_capability'
    assert 'final_test_sealed' not in {x['id'] for x in flow.view()['not_yet_defensible']}


# --- the final test: once, only after the opening decision --------------------------------

def test_the_final_test_is_scored_exactly_once_and_only_after_the_opening(tmp_path,
                                                                          monkeypatch):
    flow = _ready(tmp_path)
    final = set(fk.partition_keys(flow.study, 'final_test'))
    seen = {'final': 0, 'opened_before_read': []}
    real_final, real_load = dt.load_final_test, dt.load_dataset

    def load_final(case, keys):
        state = read.open(flow.study).state
        seen['opened_before_read'].append(
            (state['partition']['status'], state['decisions']['final_test']['status']))
        seen['final'] += 1
        return real_final(case, keys)

    def load(case, **kwargs):
        dataset = real_load(case, **kwargs)
        if final & set(dataset.index.keys):
            assert seen['final'] and kwargs.get('rows') is not None
            assert set(dataset.index.keys) == final      # the final rows, through their reader
        return dataset

    monkeypatch.setattr(dt, 'load_final_test', load_final)
    monkeypatch.setattr(dt, 'load_dataset', load)
    assert seen['final'] == 0
    # Not before the decision: the evaluation is refused without it.
    out = flow.run('final_test.evaluation', expect=2)
    assert out['error']['code'] == 'precondition_missing' and seen['final'] == 0
    p = _propose_final(flow)
    assert p['ok'], p
    confirmed = _confirm(flow, p['result']['proposal_id'])
    opening = confirmed['result']['opening']
    assert opening['status'] == 'promoted' and opening['result_id']
    assert seen['final'] == 1
    assert seen['opened_before_read'] == [('opened', 'confirmed')]
    state = flow.state()
    assert state['partition']['status'] == 'opened'
    assert state['partition']['opening']['result_id'] == opening['result_id']
    assert state['partition']['opening']['user_words'] == OPEN_WORDS
    assert st.validate_state(state) == []
    # A second opening is refused everywhere; nothing is read again.
    again = _propose_final(flow)
    assert again['error']['code'] == 'final_test_already_opened'
    out = flow.run('final_test.evaluation')
    assert out['status'] == 'already_current' and seen['final'] == 1
    records = [r for r in read.open(flow.study).exposure_records()
               if r['partition'] == 'final_test']
    assert [r['purpose'] for r in records] == ['sealed', 'final_evaluation']
    assert set(read.open(flow.study).blob(records[1]['row_keys']).decode().split()) == final
    entry = read.open(flow.study).result(opening['result_id'])
    values = entry['output']['values']
    assert entry['partition'] == 'final_test' and values['n'] == len(final)
    assert values['refit']['n_rows'] == len(fk.partition_keys(flow.study, 'development'))
    assert sorted(act.read_predictions(sto.StudyStore(flow.study),
                                       opening['result_id'])['row_keys']) == sorted(final)
    view = flow.view()
    assert view['final_test']['status'] == 'opened' and not view['final_test']['post_final_test']
    assert view['criterion']['final_test']['result_id'] == opening['result_id']
    assert view['criterion']['final_test']['status'] == values['criterion']['status']
    assert view['exposure']['by_purpose']['final_evaluation'] == len(final)


def test_an_interrupted_opening_consumes_the_final_test(tmp_path):
    flow = _ready(tmp_path)
    p = _propose_final(flow)
    _confirm_without_opening(flow, p['result']['proposal_id'])

    def boom(_plan):
        raise RuntimeError('the process failed while scoring')
    with pytest.raises(RuntimeError):
        executions.run(flow.study, 'final_test.evaluation', {}, request_id='open-x',
                       expected_revision=flow.rev(), hooks={'before_promote': boom})
    state = flow.state()
    assert state['partition']['status'] == 'opened'
    assert state['partition']['opening']['result_id'] is None
    ids = {x['id'] for x in flow.view()['not_yet_defensible']}
    assert 'final_test_opening_interrupted' in ids
    out = flow.run('final_test.evaluation', expect=2)
    assert out['error']['code'] == 'final_test_already_opened'
    final = [r for r in read.open(flow.study).exposure_records()
             if r['purpose'] == 'final_evaluation']
    assert len(final) == 1 and final[0]['result_id'] is None     # the rows may have been read


def _confirm_without_opening(flow, pid):
    """Confirm ``final_test`` through ``apply_command`` only (no automatic run), as a process
    that died right after the confirmation would leave it."""
    from mlkit.study import commands as cmd
    store = sto.StudyStore(flow.study)
    request = {'request_id': flow.rid(), 'expected_revision': flow.rev(),
               'action': cmd.ACTION_CONFIRM,
               'params': {'proposal_id': pid, 'user_words': OPEN_WORDS, 'channel': 'chat',
                          'actor': 'user', 'basis': 'explicit', 'delegation_scope': None}}
    store.execute(request, cmd.handlers(cmd.Context(store, request['request_id'])))
    assert flow.state()['decisions']['final_test']['status'] == 'confirmed'
    assert flow.state()['partition']['status'] == 'sealed'


def test_the_opening_refusals(tmp_path):
    flow = _flow(tmp_path)
    flow.run('fit.baseline')
    flow.run('fit.logistic')
    flow.variant()
    flow.run('policy.evaluate', '--rule', 'capacity:40')
    # Before the choice: nothing to open (and the conclusion is not hidden by it).
    p = _propose_final(flow, {'model': 'fit.logistic', 'rule': 'capacity:40'})
    out = _confirm(flow, p['result']['proposal_id'], expect=2)
    assert out['error']['code'] == 'precondition_missing'
    assert {'decision': 'policy'}.items() <= next(
        m for m in out['error']['details']['missing'] if m.get('decision') == 'policy').items()
    flow.decide('policy', 'capacity:40', words='Yes, I adopt it because the desk can do it')
    # A value other than the chosen configuration: refused when proposed (B6c), and by the
    # opening's precondition if it ever reached a confirmation.
    p = _propose_final(flow, {'model': 'fit.variant', 'rule': 'capacity:40'})
    assert p['error']['code'] == 'invalid_value'
    assert p['error']['details']['chosen'] == {'model': 'fit.logistic', 'rule': 'capacity:40'}
    from mlkit.study import preconditions as pre
    assert [m['requirement'] for m in pre.final_test_missing(
        flow.state(), {'model': 'fit.variant', 'rule': 'capacity:40'})][:1] == [
        'chosen_configuration']
    p = _propose_final(flow)
    # Without a reason, or delegated.
    out = _confirm(flow, p['result']['proposal_id'], 'Yes, I confirm.', expect=2)
    assert out['error']['code'] == 'reason_required'
    out = _confirm(flow, p['result']['proposal_id'], 'Use your recommended default.', 2,
                   '--basis', 'delegated_default', '--delegation-scope', 'this_decision')
    assert out['error']['code'] == 'reason_required'
    # A stale fit blocks it.
    s = flow.state()
    fake = {**s}
    fake['stale'] = {s['current']['fit.variant']: {'reason': 'test', 'since': 1}}
    from mlkit.study import preconditions as pre
    assert [m['requirement'] for m in pre.final_test_missing(fake)] == ['nothing_stale',
                                                                       'result_current']
    assert flow.state()['partition']['status'] == 'sealed'


def test_a_change_after_the_opening_is_after_the_final_test(tmp_path):
    flow = _ready(tmp_path)
    p = _propose_final(flow)
    _confirm(flow, p['result']['proposal_id'])
    summary = flow.call('status', '--summary', '--study', flow.study)
    assert summary['final_test']['post_final_test'] is False
    assert summary['criterion']['final_test']['status'] in ('met', 'uncertain', 'not_met')
    assert summary['trials'] == {'count': 2}
    flow.run('policy.evaluate', '--rule', 'capacity:30')
    flow.decide('policy', 'capacity:30', words='Yes, I adopt thirty calls because the desk is '
                                               'smaller now')
    view = flow.view()
    assert view['final_test']['post_final_test'] is True
    assert 'policy' in view['final_test']['changed_after']
    assert 'policy.evaluation' in view['final_test']['changed_after']
    items = {x['id']: x for x in view['not_yet_defensible']}
    assert 'changed_after_final_test' in items and 'policy' in items['changed_after_final_test']['changed']
    # The opening is never asked again, and its record stays current and citable.
    assert flow.state()['decisions']['final_test']['status'] == 'confirmed'
    assert view['results']['final_test.evaluation']['current'] is True
    assert flow.call('status', '--summary', '--study', flow.study)['final_test'][
        'post_final_test'] is True


def test_a_regression_opening_judges_the_criterion_on_the_final_test(tmp_path):
    flow = _ready(tmp_path, task='regression')
    p = _propose_final(flow)
    assert p['result']['proposal_id']
    out = _confirm(flow, p['result']['proposal_id'])
    rid = out['result']['opening']['result_id']
    values = read.open(flow.study).result(rid)['output']['values']
    assert values['model'] == 'fit.linear' and values['rule'] is None
    crit = values['criterion']
    base, model = values['models']['fit.baseline']['mae'], values['models']['fit.linear']['mae']
    assert abs(crit['gain'] - (base - model) / base) < 1e-12
    status, _ = fit.criterion_status(crit['gain'], crit['low'], crit['high'], crit['minimum'])
    assert crit['status'] == status


def test_policy_values_with_a_model_have_one_spelling():
    assert rec.canonical_policy('capacity:040') == 'capacity:40'
    assert rec.canonical_policy('capacity:40@fit.logistic') == 'capacity:40'
    assert rec.canonical_policy(' threshold:0.30 @ fit.variant') == 'threshold:0.3@fit.variant'
    assert rec.canonical_policy('capacity:40@fit.baseline') is None
    assert rec.canonical_policy('capacity:40@') is None
    assert rec.policy_rule('capacity:40@fit.variant') == 'capacity:40'
    assert rec.policy_model('capacity:40') == 'fit.logistic'
    assert rec.policy_model('capacity:40@fit.variant') == 'fit.variant'


def test_criterion_status_follows_the_assessment_rule():
    assert fit.criterion_status(6.0, 1.0, 9.0, 5) == ('met', False)
    assert fit.criterion_status(6.0, -1.0, 9.0, 5) == ('uncertain', True)
    assert fit.criterion_status(4.0, 1.0, 9.0, 5) == ('not_met', False)
    assert fit.criterion_status(None, None, None, 5) == ('not_assessed', None)
