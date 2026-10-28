"""v0.3 WP-J: engine changes of the finishing lot.

* The coefficient intervals of the development diagnostics are Wald intervals from a sandwich
  covariance of the (penalised) fit, one refit instead of a hundred bootstrap refits; their
  standard errors agree with a nonparametric bootstrap of the same estimator.
* Results computed before WP-J keep their currency except the development diagnostics.
* ``check`` accepts the honest figures the v0.3 runs saw refused (an interval's level in a
  header, a threshold the engine states, a group's counts with the group named in French or
  in the sentence before), and still refuses numbers that are not registered.

Studies and cases live in ``tmp_path``.
"""
from __future__ import annotations

import numpy as np
import pytest
from sklearn.base import clone

from mlkit.study import activities, case as c, data as dt, diagnostics as dg, fit, numtrace, read
from mlkit.study import view as view_mod
from mlkit.study.activities import positive
from mlkit.study.store import StudyStore

import flowkit as fk
from flowkit import Flow


def _ready(tmp_path, task='binary', n_rows=800) -> Flow:
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
    flow.run('fit.variant')
    flow.case_dir = case_dir
    return flow


def _bootstrap_sd(case, frame, entry, binary: bool, B: int = 300) -> dict:
    """The standard deviation of each coefficient over ``B`` refits of the model on prepared
    rows drawn with replacement (the method used until WP-J, with more refits)."""
    inputs = activities._model_inputs(entry)
    features, special = list(inputs['features']), list(inputs['special_values'])
    X, _ = fit.design(frame, features, special, case)
    X, _, _ = fit.prepare(case, frame, frame, X, X.copy(), features, inputs.get('preprocessing'),
                          special)
    model = fit._fit_predict(case, frame, frame.iloc[:1], inputs, entry['params'], binary)[1]
    Z = np.asarray(model['preprocess'].transform(X), dtype=float)
    names = [str(n) for n in model['preprocess'].get_feature_names_out()]
    y = positive(frame, case).to_numpy() if binary else fit._target(case, frame, 'development')
    rng = np.random.default_rng(7)
    draws = []
    for _ in range(B):
        idx = rng.integers(0, len(frame), len(frame))
        est = clone(model['model'])
        est.fit(Z[idx], y[idx])
        draws.append(np.ravel(est.coef_[0] if binary else est.coef_))
    return dict(zip(names, np.asarray(draws).std(axis=0, ddof=1)))


@pytest.mark.parametrize('task', ['binary', 'regression'])
def test_sandwich_standard_errors_match_a_bootstrap_of_the_same_estimator(tmp_path, task):
    flow = _ready(tmp_path, task)
    binary = task == 'binary'
    study = read.open(flow.study)
    store = StudyStore(flow.study)
    case = c.load_case(flow.case_dir)
    keys = activities.split_keys(store, study.current('split')['result_id'])['train']
    frame = dt.load_development(case, fk.partition_keys(flow.study, 'development')).frame.loc[keys]
    candidate = 'fit.logistic' if binary else 'fit.linear'
    for slot in (candidate, 'fit.variant'):
        entry = study.current(slot)
        out = dg.coefficient_intervals(case, frame, activities._model_inputs(entry),
                                       entry['params'], binary,
                                       entry['output']['values']['coefficients'])
        assert tuple(out) == dg.COEFFICIENT_KEYS
        sd = _bootstrap_sd(case, frame, entry, binary)
        ratios = np.array([t['std_error'] / sd[t['term']] for t in out['terms']
                           if sd[t['term']] > 1e-9])
        # The sandwich is the first-order (infinitesimal jackknife) approximation of the
        # bootstrap variance; with 300 refits the bootstrap's own error on a standard
        # deviation is about 4 %.
        assert 0.85 <= float(np.median(ratios)) <= 1.15, (slot, sorted(ratios))
        assert float(np.mean((ratios > 0.7) & (ratios < 1.4))) >= 0.9, (slot, sorted(ratios))
        z = 1.959963984540054
        for t in out['terms']:
            assert t['high'] - t['low'] == pytest.approx(2 * z * t['std_error'])
            assert t['excludes_zero'] == (t['low'] > 0 or t['high'] < 0)
        if out['penalty']:
            assert dg.PENALTY_NOTE in out['note']


def test_the_intervals_cost_one_refit_not_a_hundred(tmp_path, monkeypatch):
    """The speed of WP-J is structural: the intervals need one refit, started from the
    stored point (the reference of the point check), whatever the number of rows."""
    flow = _ready(tmp_path, 'binary', n_rows=400)
    study = read.open(flow.study)
    store = StudyStore(flow.study)
    case = c.load_case(flow.case_dir)
    keys = activities.split_keys(store, study.current('split')['result_id'])['train']
    frame = dt.load_development(case, fk.partition_keys(flow.study, 'development')).frame.loc[keys]
    entry = study.current('fit.logistic')
    from sklearn.linear_model import LogisticRegression
    calls = []
    original = LogisticRegression.fit

    def counted(self, *a, **k):
        calls.append(1)
        return original(self, *a, **k)
    monkeypatch.setattr(LogisticRegression, 'fit', counted)
    dg.coefficient_intervals(case, frame, activities._model_inputs(entry), entry['params'], True,
                             entry['output']['values']['coefficients'])
    assert len(calls) == 1


def test_results_before_wp_j_stay_current_except_the_development_diagnostics(tmp_path):
    """The reviewed WP-J edge covers final diagnostics only, never by exclusion/wildcard."""
    from mlkit.study import code_compat, registry
    case_dir = fk.make_case(tmp_path / 'case', n_rows=200)['case'].parent
    Flow(tmp_path / 'study', case_dir).init()
    study = read.open(tmp_path / 'study')
    now = registry.code_fingerprint(['mlkit.study.metrics'])['modules']
    # The pre-WP-J digests: the first edge of each module that covers diag.final_test only
    # (the library-v1 edges start from the 506180a digest, a later one).
    pre_j = {}
    for r in code_compat.ATTESTATIONS:
        if r['activities'] == ['diag.final_test']:
            pre_j.setdefault(r['module'], r['from_sha256'])
    assert set(pre_j) == {'mlkit.study.activities', 'mlkit.study.diagnostics'}
    entry = {'activity': 'diag.final_test', 'code': {'modules': {**pre_j, **now}}}
    assert study.code_changed(entry) == []
    for activity in ('fit.logistic', 'policy.evaluation', 'final_test.evaluation',
                     'diag.binary', 'diag.regression'):
        entry = {'activity': activity, 'code': {'modules': {**pre_j, **now}}}
        assert study.code_changed(entry) == ['mlkit.study.activities',
                                             'mlkit.study.diagnostics']


# --- check: honest figures the v0.3 runs saw refused (WP-H report) ------------------------

def _item(rid, values, n_rows=4000):
    return {'result_id': rid, 'values': values, 'n_rows': n_rows, 'current': True,
            'integrity': 'ok', 'activity': None, 'params': {}}


def _check_view():
    return {
        'results': {
            'evaluate.regression': _item('a1' * 32, {
                'unit': 'mpg', 'models': {'fit.linear': {'mae': {'point': 2.4138, 'low': 2.18,
                                                                 'high': 2.66}}},
                'bootstrap': {'level': 0.95}}),
            'eda.rate_by:job': _item('b2' * 32, {
                'column': 'job', 'overall_rate': 0.117, 'min_group_rows': 30, 'max_groups': 20,
                'groups': [{'value': 'student', 'n_rows': 459, 'positives': 131, 'rate': 0.2854},
                           {'value': 'retired', 'n_rows': 1264, 'positives': 289,
                            'rate': 0.2286}]}),
            'diag.binary': _item('c3' * 32, {'models': {'fit.logistic': {
                'segments': [{'column': 'job', 'small_cell_rule': 'fewer than 30 rows or fewer '
                                                                  'than 10 selected rows',
                              'groups': [{'value': 'student', 'n': 459, 'n_positive': 131,
                                          'selected': 333.0, 'true_positives': 104.0,
                                          'precision': 0.3123},
                                         {'value': 'retired', 'n': 1264, 'n_positive': 289,
                                          'selected': 212.0, 'true_positives': 77.0,
                                          'precision': 0.3632}]}]}}}),
        },
        'decisions': {}, 'open_proposals': [], 'settings': {'bootstrap': {'level': 0.95}},
        'dataset': {}, 'facts': {'by_status': {}}, 'plan': [], 'final_test': {}}


def _refused(text):
    findings, _ = numtrace.trace_text(numtrace.Pool(_check_view()), text, 'text')
    return [f['details']['number'] for f in findings if f['code'] in numtrace.NUMBER_CODES]


def test_an_interval_level_in_a_header_is_the_level_not_a_metric_value():
    # S14 Auto MPG round 2: a table header "MAE (95% interval)".
    assert _refused('| Model | MAE (95% interval) |\n| linear | 2.41 (2.18 to 2.66) |') == []
    assert _refused("L'erreur absolue moyenne (MAE), intervalle de confiance à 95 % : 2,41.") \
        == []
    assert _refused('The MAE is 2.41 mpg, 95% CI from 2.18 to 2.66.') == []
    # Without an interval word, a percentage said of the MAE is a claim about it.
    assert _refused('The MAE improves by 95%.') == ['95%']
    assert _refused('MAE (90% interval)') == ['90%']


def test_a_threshold_the_engine_states_is_citable_after_a_threshold_word():
    assert _refused('Les groupes de moins de 30 lignes sont signalés : leur taux est trop '
                    'bruité.') == []
    assert _refused('A cell with fewer than 10 selected rows is flagged as small.') == []
    # Another number after the same words is not a stated threshold.
    assert _refused('Les groupes de moins de 25 lignes sont signalés.') == ['25']
    # The threshold's value without a threshold word is no claim the engine made.
    assert _refused('Le groupe compte 30 lignes.') == ['30']


def test_a_groups_counts_are_citable_when_the_group_is_named_in_french_or_before():
    # S13 Bank full: « 333 étudiants sur 459 » for the group ``student``.
    assert _refused('À la règle, 333 étudiants sur 459 sont appelés.') == []
    assert _refused('Among them, 333 of 459 are called.') == []
    # The group named in the sentence before.
    assert _refused('Regardons le groupe student. Il compte 459 clients, dont 333 '
                    'sélectionnés.') == []
    # Counts that are not one group's pair stay refused.
    assert _refused('À la règle, 333 étudiants sur 460 sont appelés.') == ['333', '460']
    assert _refused('À la règle, 212 étudiants sur 459 sont appelés.') == ['212']
    # A segment figure without its group named anywhere stays refused (WP-A).
    assert _refused('Le modèle sélectionne 333 clients.') == ['333']


# --- fewer round trips: writes return the next action, status --fields --------------------

def _early(tmp_path, lang=None):
    case_dir = fk.make_case(tmp_path / 'case', task='binary', n_rows=300)['case'].parent
    flow = Flow(tmp_path / 'study', case_dir)
    args = ('init', '--case', case_dir, '--study', flow.study) + (('--lang', lang) if lang
                                                                   else ())
    flow.call(*args)
    flow.case_dir = case_dir
    return flow


def test_writes_return_the_next_action_status_would_give(tmp_path):
    flow = _early(tmp_path)
    p = flow.call('decide', 'propose', 'prediction_time', '--value',
                  'when the record is created, before the outcome', '--restatement',
                  'The score is computed when the record is created.', '--rationale', 'The case.',
                  '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                  '--study', flow.study)
    status = flow.call('status', '--summary', '--study', flow.study)
    assert p['next_action'] == status['next_action']
    assert p['next_action']['kind'] == 'await_user_words'
    assert p['next_action']['question'] == 'Do you adopt this decision?'
    c = flow.call('decide', 'confirm', p['result']['proposal_id'], '--user-words', 'yes',
                  '--adoption-question', '--request-id', flow.rid(),
                  '--expected-revision', p['revision'], '--study', flow.study)
    assert c['next_action'] == flow.call('status', '--summary', '--study', flow.study)[
        'next_action']
    assert c['next_action']['decision'] == 'feature_availability'
    assert c['next_action']['recommended'] is not None


def test_status_fields_prints_only_the_keys_asked_for(tmp_path):
    flow = _early(tmp_path)
    out = flow.call('status', '--summary', '--fields', 'next_action,criterion',
                    '--study', flow.study)
    assert tuple(out) == ('schema', 'ok', 'study', 'revision', 'next_action', 'criterion')
    full = flow.call('status', '--summary', '--study', flow.study)
    assert out['next_action'] == full['next_action']
    bad = flow.call('status', '--summary', '--fields', 'next_step', '--study', flow.study,
                    expect=2)
    assert bad['error']['code'] == 'invalid_arguments'
    assert bad['error']['details']['unknown'] == ['next_step']
    flow.call('status', '--fields', 'next_action', '--study', flow.study, expect=2)


@pytest.mark.parametrize('lang', ['en', 'fr'])
def test_the_success_criterion_has_a_recommended_default_with_its_why(tmp_path, lang):
    case_dir = fk.make_case(tmp_path / 'case', task='binary', n_rows=300)['case'].parent
    flow = Flow(tmp_path / 'study', case_dir)
    flow.call('init', '--case', case_dir, '--lang', lang, '--study', flow.study)
    flow.decide('prediction_time', 'when the record is created, before the outcome')
    flow.decide('feature_availability', fk.availability(case_dir))
    flow.decide('split', flow.view()['next_action']['default_value'])
    flow.run('split')
    action = flow.view()['next_action']
    assert action['decision'] == 'success_criterion'
    rec = action['recommended']
    assert rec['value'] == {'metric': 'precision_gain', 'min_points': 5}
    convention = 'convention' in rec['why']
    assert convention, rec['why']
    if lang == 'fr':
        assert 'Gardez-le' in rec['why'] and 'points de précision' in rec['why']
    else:
        assert 'Keep it' in rec['why']
    # The figures of the why are the engine's own options: check accepts them.
    extra = action['criterion_options']['candidates'][1]['per_1000']['extra']
    assert f'{extra}' in rec['why']
    pool = numtrace.study_pool(flow.study)
    findings, _ = numtrace.trace_text(pool, rec['why'], 'text')
    assert [f for f in findings if f['code'] in numtrace.NUMBER_CODES] == []
    assert rec['why'] in action['junior_digest'] or 'Recommand' in action['junior_digest']


def test_the_regression_criterion_recommends_ten_percent_less_error(tmp_path):
    case_dir = fk.make_case(tmp_path / 'case', task='regression', n_rows=300)['case'].parent
    flow = Flow(tmp_path / 'study', case_dir)
    flow.init()
    flow.decide('prediction_time', 'when the record is created, before the outcome')
    flow.decide('feature_availability', fk.availability(case_dir))
    flow.decide('split', flow.view()['next_action']['default_value'])
    flow.run('split')
    # R60 (lot 2026-10-28): a new regression study chooses its error measure first.
    assert flow.view()['next_action']['recommended']['value'] == {'metric': 'mae'}
    flow.decide('error_metric', {'metric': 'mae'})
    rec = flow.view()['next_action']['recommended']
    assert rec['value'] == {'metric': 'mae_reduction', 'min_share': 0.1}
    assert '10% less error' in rec['why'] and 'convention' in rec['why']


# --- mode-aware waiting message (R27) -------------------------------------------------------

def test_the_waiting_message_asks_own_words_only_in_the_training_mode(tmp_path):
    flow = _early(tmp_path)
    flow.call('decide', 'propose', 'prediction_time', '--value', 'when the record is created',
              '--restatement', 'The score is computed when the record is created.',
              '--rationale', 'The case.', '--request-id', flow.rid(),
              '--expected-revision', flow.rev(), '--study', flow.study)
    guided = flow.view()['next_action']
    assert 'own words' not in guided['message']
    assert '"Do you adopt this decision?"' in guided['message']
    assert 'own words' not in guided['junior_digest']
    flow.call('mode', 'set', 'training', '--request-id', flow.rid(),
              '--expected-revision', flow.rev(), '--study', flow.study)
    training = flow.view()['next_action']
    assert 'own words' in training['message']
    assert 'own words' in training['junior_digest']
    assert training['question'] == 'In your own words, what do you keep, and why?'


# --- the channel of panel-launched runs, renders and exports (R35) -------------------------

def test_runs_renders_and_exports_record_their_channel_in_the_digest(tmp_path):
    flow = _early(tmp_path)
    flow.decide('prediction_time', 'when the record is created, before the outcome')
    flow.decide('feature_availability', fk.availability(flow.case_dir))
    flow.decide('split', flow.view()['next_action']['default_value'])
    since = flow.rev()
    flow.call('run', 'split', '--request-id', flow.rid(), '--expected-revision', flow.rev(),
              '--study', flow.study)
    column = next(v['name'] for v in c.load_case(flow.case_dir).document['variables']
                  if v['role'] == 'feature')
    eda = flow.call('run', 'eda.distribution', '--column', column, '--channel', 'webview',
                    '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                    '--study', flow.study)
    assert eda['status'] == 'promoted'
    flow.call('render', '--channel', 'webview', '--study', flow.study)
    flow.call('export', 'handoff', '--out', str(tmp_path / 'handoff'), '--channel', 'webview',
              '--study', flow.study)
    digest = flow.call('status', '--summary', '--digest', '--since', since,
                       '--study', flow.study)['digest']
    actions = digest['channel_actions']
    assert [(a['action'], a['channel']) for a in actions] == [
        ('run', 'webview'), ('render', 'webview'), ('export', 'webview')]
    assert actions[0]['activity'] == 'eda.distribution'
    assert all(tuple(a) == view_mod.CHANNEL_ACTION_KEYS for a in actions)
    runs = {i['activity']: i for i in digest['items'] if i['activity']}
    assert runs['split']['channel'] is None
    assert runs['eda.distribution']['channel'] == 'webview'
    assert 'from the study panel' in runs['eda.distribution']['text']
    # The chat records nothing; an unknown channel is refused before anything is written.
    bad = flow.call('render', '--channel', 'phone', '--study', flow.study, expect=2)
    assert bad['error']['code'] == 'invalid_value'
    bad = flow.call('run', 'eda.distribution', '--column', column, '--channel', 'phone',
                    '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                    '--study', flow.study, expect=2)
    assert bad['error']['code'] == 'invalid_value'


# --- the Hotel case's interpretability constraint keeps existing studies working ------------

def test_a_hotel_study_started_before_the_constraint_keeps_its_case(tmp_path):
    """J9: the committed Hotel ``case.yaml`` gained ``constraints`` (read by the view's
    shortlist only). A study initialised on the earlier bytes is not "dataset changed": it
    reads its status and runs; any other edit of the case still is a change."""
    import shutil
    import hashlib
    hotel = fk.REPO / 'use-cases' / 'hotel-booking'
    case_dir = tmp_path / 'hotel'
    shutil.copytree(hotel, case_dir)
    current = (hotel / 'case.yaml').read_text(encoding='utf-8')
    # Keep this exact historical WP-J equivalence test. J0's substantive scope
    # addition is deliberately not an equivalent case change (tested separately).
    current = current[:current.index('analysis_contract:\n')] + current[current.index('constraints:\n'):]
    earlier = current[:current.index('constraints:\n')]
    (case_dir / 'case.yaml').write_text(earlier, encoding='utf-8')
    assert (c.sha256_file(case_dir / 'case.yaml'), hashlib.sha256(current.encode('utf-8')).hexdigest()) \
        in c.EQUIVALENT_CASE_FILES
    flow = Flow(tmp_path / 'study', case_dir, prefix='h')
    flow.init()
    (case_dir / 'case.yaml').write_text(current, encoding='utf-8')
    view = flow.view()
    assert 'sources_changed' not in [x['id'] for x in view['not_yet_defensible']]
    assert view['model_families']['constraints']['interpretability'] == 'preferred'
    flow.decide('prediction_time', 'when the booking is entered')
    flow.run('eda.quality')
    (case_dir / 'case.yaml').write_text(current + '\n', encoding='utf-8')
    refused = flow.call('status', '--study', flow.study)['view']
    assert 'sources_changed' in [x['id'] for x in refused['not_yet_defensible']]
