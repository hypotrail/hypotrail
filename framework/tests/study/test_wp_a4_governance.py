"""WP-A4 (v0.2a): data card, step 0, EDA governance, preprocessing, success criterion.

* ``hypotrail data`` (R2, R5): read-only, never logged, development rows only, grouped
  dictionary with French labels, five rows by row key with the target first, no rate;
* step 0 ``discover_data``: ``next_action`` ``show_data_card`` until the first proposal;
* the two decisions before the models: fits refused without them, the default
  preprocessing reproduces the models, a changed preprocessing refits the candidate only,
  ``data_contingent`` from the motivating results;
* EDA governance: ``eda.quality`` without the target and without a split, Wilson intervals
  and the permutation null band, the single-feature signal as a legitimacy question, the
  ledger of target looks;
* the success criterion assessment and ``check``'s ``verdict_contradicts_criterion``;
* a study created before WP-A4 keeps its five decisions.

Studies live in temporary directories; the committed cases are only read.
"""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from mlkit.study import case as c, governance, partition, read, state as st, store as sto

import flowkit as fk
from flowkit import Flow

AUTO = fk.REPO / 'use-cases' / 'auto-mpg'


@pytest.fixture(scope='module')
def bank_fits(tmp_path_factory) -> Path:
    """A Bank study up to the fits, with the success criterion and default preprocessing."""
    study = tmp_path_factory.mktemp('bank') / 'study'
    flow = Flow(study, fk.BANK, prefix='m')
    flow.init()
    flow.pauses(duration='not_available')
    flow.run('split')
    flow.run('fit.baseline')
    flow.run('fit.logistic')
    flow.variant()          # WP-B1: the variant the policy compares
    return study


def _copy(src: Path, tmp_path: Path) -> Flow:
    target = tmp_path / 'study'
    shutil.copytree(src, target)
    return Flow(target, fk.BANK, prefix='c')


# --- the data card ---------------------------------------------------------------------

def test_the_data_card_shows_development_rows_grouped_without_any_rate(tmp_path):
    flow = Flow(tmp_path / 'study', fk.BANK)
    flow.init()
    before = fk.tree_digest(flow.study)
    card = flow.call('data', '--study', flow.study)
    assert card['schema'] == 'hypotrail.data/1' and card['ok'] is True
    final = flow.view()['final_test']
    duplicates = card['development'].pop('duplicates')      # v0.2b (WP-B3), additive
    assert card['development'] == {'rows': final['development_rows'], 'columns': 17,
                                   'partition': 'development'}
    assert duplicates['policy'] is None and duplicates['n_groups'] == 0
    assert duplicates['line'] == 'No two development rows are identical.'
    assert card['final_test']['status'] == 'sealed' and card['final_test']['audience'] == 'junior'
    assert card['target']['positive_label'] == 'yes' and card['target']['negative_label'] == 'no'
    assert card['observation_unit']['value']
    groups = [g['group'] for g in card['groups']]
    assert groups[:2] == ['Client', 'Last contact of this campaign'] and 'Outcome' in groups
    variables = {v['name']: v for g in card['groups'] for v in g['variables']}
    assert set(variables) == set(c.load_case(fk.BANK).column_names)
    assert variables['age']['description_fr'] == 'Âge du client, en années.'
    assert variables['duration']['availability']['value'] == 'not_available'
    pdays = variables['pdays']['special_values'][0]
    assert pdays['value'] == -1 and pdays['n_rows'] > 0
    assert all(len(v['examples']) <= 3 for v in variables.values())
    rows = card['rows']
    # Contract P1.9: the seeded step-1 sample, eight development rows, target first.
    assert rows['columns'][0] == 'y' and rows['n_rows'] == 8
    keys = [r['row_key'] for r in rows['items']]
    development = fk.partition_keys(flow.study, 'development')
    assert keys == partition.draw(rows['seed'], development)
    assert not set(keys) & set(fk.partition_keys(flow.study, 'final_test'))
    text = json.dumps(card)
    assert '"rate"' not in text and 'share' not in text          # no target rate, no distribution
    assert fk.tree_digest(flow.study) == before                   # read-only, records nothing


def test_the_data_card_is_never_session_logged(tmp_path, monkeypatch):
    flow = Flow(tmp_path / 'study', fk.BANK)
    flow.init()
    monkeypatch.setenv('HYPOTRAIL_SESSION_LOG', '1')
    code, card = fk.hyp('data', '--study', flow.study, cwd=tmp_path)
    assert code == 0 and card['schema'] == 'hypotrail.data/1'
    assert not (flow.study / '.hypotrail' / 'session-log.jsonl').exists()
    proc = subprocess.run([sys.executable, '-m', 'mlkit.study.cli', 'data', '--format', 'text',
                           '--study', str(flow.study)], capture_output=True, text=True,
                          env=fk.env(), cwd=tmp_path)
    assert proc.returncode == 0 and proc.stdout.startswith('One row:')
    assert '## Client' in proc.stdout and 'fr: Âge du client' in proc.stdout



def test_check_lets_a_text_repeat_the_data_card(tmp_path):
    """WP-A8: at step 0 the agent shows the data card before any result exists; ``check``
    traces its figures (counts and quoted cells) and the sealed rows, and still refuses a
    number the card does not show, or a percentage made of a quoted cell."""
    from mlkit.study import cmd_check
    flow = Flow(tmp_path / 'study', fk.BANK)
    flow.init()
    card = flow.call('data', '--study', flow.study)
    variables = {v['name']: v for g in card['groups'] for v in g['variables']}
    sealed = flow.view()['final_test']['rows']
    balance = next(x for x in variables['balance']['examples'] if abs(x) > 100)
    text = (f"{card['development']['rows']:,} development rows and "
            f"{card['development']['columns']} columns; {sealed} rows are sealed. "
            f"{variables['pdays']['special_values'][0]['n_rows']} rows have pdays at -1, and "
            f"one client has a balance of {balance}.")
    out = cmd_check.run_check(flow.study, text)
    assert out['clean'], out['findings']
    sources = {t['text']: (t.get('source'), t.get('id')) for t in out['traced']}
    assert sources[str(sealed)] == ('final_test', 'final_test.rows')
    assert sources[str(balance)] == ('data_card', 'data.balance.examples')
    refused = cmd_check.run_check(flow.study, 'About 98765 clients, and 1787% of them.')
    assert [f['details']['number'] for f in refused['findings']
            if f['code'] == 'untraceable_number'] == ['98765', '1787%']


# --- step 0 ----------------------------------------------------------------------------

def test_step_zero_shows_the_data_card_until_the_first_proposal(tmp_path):
    flow = Flow(tmp_path / 'study', fk.BANK)
    init = flow.init()
    assert init['next_action']['kind'] == 'show_data_card'
    view = flow.view()
    assert view['current_step'] == 'discover_data'
    # WP-B2: a new binary study has separate model-choice and policy steps. Owner session
    # 2026-10-26 (L5, D5): it checks the structure before the preparation and the target.
    assert [s['id'] for s in view['plan']] == list(fk.STRUCTURAL_FIRST_BINARY_STEP_IDS)
    nxt = view['next_action']
    assert nxt['audience'] == 'agent' and 'hypotrail data' in nxt['message']
    assert 'hypotrail' not in nxt['junior_message'] and 'Nothing is decided' in nxt['junior_message']
    step0 = view['plan'][0]
    assert step0['decision'] is None and step0['activities'] == [] and step0['status'] == 'ready'
    flow.call('decide', 'propose', 'prediction_time', '--value', 'before the first contact',
              '--restatement', 'You predict before the first contact.', '--rationale', 'It fits.',
              '--request-id', 'p1', '--expected-revision', flow.rev(), '--study', flow.study)
    view = flow.view()
    assert view['plan'][0]['status'] == 'done'
    assert view['next_action']['kind'] == 'await_user_words'


# --- the two decisions before the models -------------------------------------------------

@pytest.mark.parametrize('generation', ['previous', 'structural_first'])
def test_fits_wait_for_the_success_criterion_and_the_preprocessing(tmp_path, generation):
    flow = Flow(tmp_path / 'study', fk.BANK)
    flow.init()
    if generation == 'previous':
        fk.previous_generation(flow.study)
    flow.pauses(model_decisions=False)
    flow.run('split')
    refused = flow.run('fit.baseline', expect=2)
    assert refused['error']['code'] == 'precondition_missing'
    named = [m.get('decision') for m in refused['error']['details']['missing']]
    assert named == ['success_criterion', 'preprocessing']
    eda = flow.run('eda.target_rate')                      # the exploration needs neither
    assert eda['status'] == 'promoted'
    view = flow.view()
    assert view['current_step'] == 'success_criterion'
    assert view['next_action'] == {**view['next_action'], 'kind': 'propose',
                                   'decision': 'success_criterion'}
    flow.decide('success_criterion', {'metric': 'precision_gain', 'min_points': 5})
    flow.run('eda.special_values')
    nxt = flow.view()['next_action']
    if generation == 'structural_first':
        # Owner session 2026-10-26 (L5, D5, D6): the quality check is a step before the
        # preparation (and the screened distributions, one column each); the draft cites it.
        assert (nxt['kind'], nxt['activity']) == ('run', 'eda.quality')
        while nxt['kind'] == 'run':
            options = [x for k, v in (nxt.get('options') or {}).items() for x in (f'--{k}', v)]
            flow.run(nxt['activity'], *options)
            nxt = flow.view()['next_action']
        assert nxt['decision'] == 'preprocessing'
        assert nxt['default_value']['motivated_by'][0] == flow.state()['current']['eda.quality']
        return
    assert nxt['decision'] == 'preprocessing'
    assert nxt['default_value'] == governance.DEFAULT_PREPROCESSING


@pytest.mark.parametrize('value, field', [
    ({'missing': 'all', 'rare_category_min_rows': 0, 'caps': {}, 'log_transform': []}, 'missing'),
    ({'missing': 'none', 'rare_category_min_rows': -1, 'caps': {}, 'log_transform': []},
     'rare_category_min_rows'),
    ({'missing': 'none', 'rare_category_min_rows': 0, 'caps': {'job': [0.01, 0.99]},
      'log_transform': []}, 'caps'),
    ({'missing': 'none', 'rare_category_min_rows': 0, 'caps': {'balance': [0.9, 0.1]},
      'log_transform': []}, 'caps.balance'),
    ({'missing': 'none', 'rare_category_min_rows': 0, 'caps': {}, 'log_transform': ['month']},
     'log_transform'),
    ({'missing': 'none', 'rare_category_min_rows': 0, 'caps': {}, 'log_transform': [],
      'motivated_by': ['nope']}, 'motivated_by'),
])
def test_a_preprocessing_value_that_does_not_fit_the_case_is_refused(tmp_path, value, field):
    flow = Flow(tmp_path / 'study', fk.BANK)
    flow.init()
    flow.pauses(model_decisions=False)
    out = flow.call('decide', 'propose', 'preprocessing', '--value-json', json.dumps(value),
                    '--restatement', 'You prepare the variables as stated.', '--rationale', 'x',
                    '--request-id', 'pp', '--expected-revision', flow.rev(),
                    '--study', flow.study, expect=2)
    assert out['error']['code'] == 'invalid_value'
    assert out['error']['details']['field'] == field


def test_criterion_values_are_checked_by_task(tmp_path):
    flow = Flow(tmp_path / 'study', fk.BANK)
    flow.init()
    flow.pauses(model_decisions=False)
    for bad in ({'metric': 'mae_reduction', 'min_share': 0.1},
                {'metric': 'precision_gain', 'min_points': 120},
                {'metric': 'precision_gain'}):
        out = flow.call('decide', 'propose', 'success_criterion', '--value-json', json.dumps(bad),
                        '--restatement', 'You fix the criterion.', '--rationale', 'x',
                        '--request-id', f'c{len(bad)}{bad.get("min_points")}',
                        '--expected-revision', flow.rev(), '--study', flow.study, expect=2)
        assert out['error']['code'] == 'invalid_value', bad


def test_the_default_preprocessing_reproduces_the_models(tmp_path, bank_fits):
    """The default changes nothing: the same coefficients and validation scores as a fit
    without the decision (the code path a study created before WP-A4 takes)."""
    from mlkit.study import activities as act, fit
    s = read.open(bank_fits)
    entry = s.current('fit.logistic')
    assert entry['inputs']['preprocessing'] == governance.DEFAULT_PREPROCESSING
    fitted = entry['output']['values']['preprocessing']['fitted']
    assert fitted == {'missing_indicators': [], 'rare_categories': {}, 'caps': {},
                      'log_transform': [], 'ignored': []}
    case = c.case_of(s.state)
    from mlkit.study import data as dt, partition
    from mlkit.study.store import StudyStore
    store = StudyStore(bank_fits)
    frame = dt.load_development(case, partition.development_keys(
        s.blob, partition.inputs(s.state))).frame
    keys = act.split_keys(store, s.state['current']['split'])
    inputs = {k: v for k, v in entry['inputs'].items() if k != 'preprocessing'}
    plain = fit.logistic(case, frame.loc[keys['train']], frame.loc[keys['validation']], inputs,
                         entry['params'])
    assert plain['values']['coefficients'] == entry['output']['values']['coefficients']
    assert plain['blobs']['predictions'] == s.blob(entry['blobs']['predictions'])
    assert 'preprocessing' not in plain['values']


def test_a_changed_preprocessing_refits_the_candidate_and_keeps_the_exploration(tmp_path,
                                                                                bank_fits):
    flow = _copy(bank_fits, tmp_path)
    rate = flow.run('eda.rate_by', '--column', 'poutcome')
    quality = flow.run('eda.quality')
    flow.run('policy.evaluation', '--rule', 'capacity:100')
    flow.decide('policy', 'capacity:100', 'Yes, capacity:100 because the team calls a hundred')
    before = flow.state()['current']
    value = {'missing': 'indicator', 'rare_category_min_rows': 30,
             'caps': {'balance': [0.01, 0.99]}, 'log_transform': ['balance', 'campaign'],
             'motivated_by': [quality['result_id']]}
    p = flow.call('decide', 'propose', 'preprocessing', '--value-json', json.dumps(value),
                  '--restatement', 'You cap and log the balance and group rare categories.',
                  '--rationale', 'The quality overview shows skewed amounts.',
                  '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                  '--study', flow.study)
    proposed = flow.state()['proposals'][p['result']['proposal_id']]['value']
    # WP-A9 (M1): the study looked at the outcome before (the rates by poutcome, the
    # training EDA), so the value is data-contingent even though its motivation is the
    # structural quality overview.
    assert proposed['motivated_by'] == [quality['result_id']]
    assert proposed['target_looks_before'] >= 1 and proposed['data_contingent'] is True
    out = flow.call('decide', 'confirm', p['result']['proposal_id'], '--user-words',
                    'Yes, cap and log the balance and group the rare categories',
                    '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                    '--study', flow.study)
    inv = out['result']['invalidation']
    assert inv['mutation'] == 'preprocessing' and inv['row'] == 14
    # WP-B1: the variant is the candidate with one change, so it is fitted again too.
    assert set(inv['stale_slots']) == {'fit.logistic', 'fit.variant', 'policy.evaluation'}
    assert set(inv['reconfirm_required']) == {'policy'}
    view = flow.view()
    assert view['results']['fit.baseline']['current'] is True
    assert view['results']['eda.rate_by:poutcome']['current'] is True
    assert view['results']['eda.quality']['current'] is True
    refit = flow.run('fit.logistic')
    pre = refit['values']['preprocessing']
    assert pre['fitted']['caps']['balance'][0] < pre['fitted']['caps']['balance'][1]
    assert pre['fitted']['log_transform'] == ['balance', 'campaign']
    assert 'job' in pre['fitted']['rare_categories'] or 'month' in pre['fitted']['rare_categories']
    assert refit['result_id'] != before['fit.logistic']
    # Motivated by a look at the target: stamped data-contingent, named as a limit.
    value2 = {**value, 'motivated_by': [rate['result_id']]}
    p = flow.call('decide', 'propose', 'preprocessing', '--value-json', json.dumps(value2),
                  '--restatement', 'You cap and log the balance and group rare categories.',
                  '--rationale', 'The rates by previous outcome.', '--request-id', flow.rid(),
                  '--expected-revision', flow.rev(), '--study', flow.study)
    out = flow.call('decide', 'confirm', p['result']['proposal_id'], '--user-words',
                    'Yes, cap and log the balance and group the rare categories',
                    '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                    '--study', flow.study)
    assert out['result']['invalidation']['mutation'] == 'preprocessing.motivation'
    assert out['result']['invalidation']['stale_slots'] == []
    assert flow.state()['decisions']['preprocessing']['value']['data_contingent'] is True
    limit = next(x for x in flow.view()['not_yet_defensible']
                 if x['id'] == 'data_contingent_preprocessing')
    assert limit['results'] == [rate['result_id']] and limit['audience'] == 'junior'


# --- EDA governance ---------------------------------------------------------------------

def test_quality_reads_the_development_rows_without_the_target_and_needs_no_split(tmp_path):
    flow = Flow(tmp_path / 'study', fk.BANK)
    flow.init()
    out = flow.run('eda.quality')
    v = out['values']
    assert v['partition'] == 'development' and v['target_read'] is False
    assert v['n_rows'] == flow.view()['final_test']['development_rows']
    assert 'y' not in {m['column'] for m in v['missing']}
    assert v['duplicates']['n_rows'] == 0 and v['n_rows_with_missing'] == 0
    assert any(x['column'] == 'month' and x['rare'] for x in v['cardinality'])
    assert v['question'].startswith('Are there missing cells')
    record = fk.exposure_records(flow.study)[-1]
    assert record['purpose'] == 'structural_inspection' and record['partition'] == 'development'
    assert 'y' not in record['columns']
    assert flow.view()['eda_looks']['target_looks'] == 0


def test_rate_by_carries_wilson_intervals_and_a_seeded_null_band(tmp_path, bank_fits):
    flow = _copy(bank_fits, tmp_path)
    out = flow.run('eda.rate_by', '--column', 'poutcome')
    v = out['values']
    band = v['null_band']
    assert band['shuffles'] == 19 and band['seed'] == 20261019
    assert band['chart']['outside'] is True                     # previous success: far above
    for g in v['groups']:
        assert g['interval']['low'] <= g['rate'] <= g['interval']['high']
        assert g['null_band']['low'] <= g['null_band']['high']
    assert v['question'].startswith('Does the positive rate differ across the groups of poutcome')
    again = flow.run('eda.rate_by', '--column', 'poutcome')     # seeded: the same result
    assert again['status'] == 'already_current' or again['result_id'] == out['result_id']
    rate = flow.run('eda.target_rate')['values']
    assert rate['interval']['low'] < rate['rate'] < rate['interval']['high']
    assert governance.ledger(fk.exposure_records(flow.study), 'y')['target_looks'] >= 2


def test_the_single_feature_signal_only_raises_a_legitimacy_question(tmp_path, bank_fits):
    flow = _copy(bank_fits, tmp_path)
    out = flow.run('eda.single_feature_signal')
    v = out['values']
    assert v['metric'] == 'roc_auc' and v['folds'] == 5
    top = v['signals'][0]
    assert top['feature'] == 'duration' and top['flag'] is True
    assert top['availability'] == 'not_available'
    question = v['questions'][0]
    assert question['feature'] == 'duration' and 'known at the prediction moment' in question['text']
    assert 'never keeps or drops a feature' in v['note']
    entry = read.open(flow.study).current('eda.single_feature_signal')
    assert 'features' not in v and 'features' not in entry['inputs']
    looks = flow.view()['eda_looks']
    assert out['result_id'] in looks['results']
    assert looks['by_activity']['eda.single_feature_signal'] == 1
    summary = flow.call('status', '--summary', '--study', flow.study)
    assert summary['eda_looks']['target_looks'] == looks['target_looks']


# --- the success criterion ------------------------------------------------------------

def _conclude(flow: Flow, verdict: str) -> None:
    p = flow.call('decide', 'propose', 'conclusion', '--value-json',
                  json.dumps({'verdict': verdict,
                              'text': 'The logistic model ranks the validation rows above the '
                                      'baseline at the adopted rule.'}),
                  '--restatement', 'You conclude as stated.', '--rationale', 'It fits.',
                  '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                  '--study', flow.study)
    flow.call('decide', 'confirm', p['result']['proposal_id'], '--user-words',
              'Yes, I conclude so because the ranking is better', '--request-id', flow.rid(),
              '--expected-revision', flow.rev(), '--study', flow.study)


def test_an_adopting_verdict_below_the_criterion_is_a_check_warning(tmp_path, bank_fits):
    flow = _copy(bank_fits, tmp_path)
    flow.run('policy.evaluation', '--rule', 'capacity:100')
    flow.decide('policy', 'capacity:100', 'Yes, capacity:100 because the team calls a hundred')
    criterion = flow.view()['criterion']
    assert criterion['status'] == 'met' and criterion['rule'] == 'capacity:100'
    assert criterion['low'] > 0 and criterion['gain'] >= 5
    # A stricter criterion, fixed again: the conclusion is asked again (row 16).
    p = flow.call('decide', 'propose', 'success_criterion', '--value-json',
                  json.dumps({'metric': 'precision_gain', 'min_points': 60}),
                  '--restatement', 'The model must beat the baseline by 60 points.',
                  '--rationale', 'x', '--request-id', flow.rid(),
                  '--expected-revision', flow.rev(), '--study', flow.study)
    out = flow.call('decide', 'confirm', p['result']['proposal_id'], '--user-words',
                    'Yes, I want 60 points over the baseline', '--request-id', flow.rid(),
                    '--expected-revision', flow.rev(), '--study', flow.study)
    assert out['result']['invalidation']['mutation'] == 'success_criterion'
    # Review round 9 (R9E-4): adopting rests on the final test, so it is opened first.
    flow.decide('final_test', st.choice_config(flow.state()),
                'Yes, I open the final test now, because the model and the rule are fixed')
    _conclude(flow, 'adopt_policy')
    view = flow.view()
    assert view['criterion']['status'] == 'not_met' and view['criterion']['contradicts_verdict']
    assert 'verdict_contradicts_criterion' in {x['id'] for x in view['not_yet_defensible']}
    check = flow.call('check', '--study', flow.study)
    codes = {f['code']: f for f in check['findings']}
    warning = codes['verdict_contradicts_criterion']
    assert warning['severity'] == 'warning' and warning['details']['status'] == 'not_met'
    summary = flow.call('status', '--summary', '--study', flow.study)
    assert summary['criterion']['contradicts_verdict'] is True
    assert summary['not_yet_defensible']['top'][0]['id'] == 'verdict_contradicts_criterion'


def test_the_conclusion_needs_the_success_criterion(tmp_path):
    flow = Flow(tmp_path / 'study', fk.BANK)
    flow.init()
    flow.pauses(model_decisions=False)
    p = flow.call('decide', 'propose', 'conclusion', '--value-json',
                  json.dumps({'verdict': 'inconclusive', 'text': 'Nothing is evaluated yet.'}),
                  '--restatement', 'You conclude as stated.', '--rationale', 'It fits.',
                  '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                  '--study', flow.study)
    out = flow.call('decide', 'confirm', p['result']['proposal_id'], '--user-words',
                    'Yes, inconclusive because nothing is evaluated', '--request-id', flow.rid(),
                    '--expected-revision', flow.rev(), '--study', flow.study, expect=2)
    assert out['error']['code'] == 'precondition_missing'
    assert {m['decision'] for m in out['error']['details']['missing']} == {'success_criterion',
                                                                          'preprocessing'}


def test_a_regression_criterion_is_a_relative_error_reduction(tmp_path):
    flow = Flow(tmp_path / 'study', AUTO)
    flow.init()
    flow.decide('prediction_time', 'when the characteristics of a new model are fixed')
    flow.decide('feature_availability', fk.availability(AUTO))
    flow.decide('split', {'method': 'ordinal_cutoff', 'column': 'model_year', 'cutoff': 79})
    flow.model_decisions()
    for a in ('split', 'fit.baseline', 'fit.linear'):
        flow.run(a)
    flow.variant()          # WP-B1: the variant the model choice compares
    flow.run('evaluate.regression')
    crit = flow.view()['criterion']
    ev = flow.view()['results']['evaluate.regression']['values']
    base = ev['models']['fit.baseline']['mae']
    assert crit['metric'] == 'mae_reduction' and crit['minimum'] == 0.1
    assert crit['gain'] == pytest.approx(-ev['deltas']['fit.linear']['mae']['point'] / base)
    assert crit['status'] in ('met', 'uncertain', 'not_met') and crit['rule'] is None
    signal = flow.run('eda.single_feature_signal')['values']
    assert signal['metric'] == 'r2' and signal['signals'][0]['score'] is not None
    # WP-A8: a regression study's questions name the target, never an "outcome".
    specials = flow.run('eda.special_values')['values']
    for text in [signal['question'], specials['question'],
                 *(q['text'] for q in signal['questions'])]:
        assert 'outcome' not in text and 'target' in text, text
    band = flow.run('eda.mean_by', '--column', 'cylinders')['values']
    assert band['null_band']['shuffles'] == 19
    assert all(g['interval'] is None or g['interval']['low'] <= g['mean'] <= g['interval']['high']
               for g in band['groups'])


# --- a study created before WP-A4 ----------------------------------------------------

def _pre_wp_a4_state(case_dir: Path) -> dict:
    """The state ``init`` wrote before WP-A4: the five v0.1 decisions and their depends_on."""
    state = st.initial_state(c.load_case(case_dir))
    for d in st.WP_A4_DECISIONS + st.WP_B1_DECISIONS:
        del state['decisions'][d]
    state['decisions'].pop('model_choice', None)
    for d, dec in state['decisions'].items():
        dec['depends_on'] = list(st.DEPENDS_ON[d])
    return state


def test_a_study_created_before_wp_a4_keeps_five_decisions(tmp_path):
    case_dir = fk.make_case(tmp_path / 'case', n_rows=300)['case'].parent
    store = sto.StudyStore(tmp_path / 'study')
    store.create(_pre_wp_a4_state(case_dir))
    flow = Flow(tmp_path / 'study', case_dir)
    view = flow.view()
    assert tuple(view['decisions']) == st.DECISION_IDS
    assert [s['id'] for s in view['plan']] == ['discover_data', *st.STEP_IDS]
    assert view['criterion'] is None
    flow.pauses()                                       # no criterion or preprocessing to give
    flow.run('split')
    fitted = flow.run('fit.logistic')
    entry = read.open(flow.study).current('fit.logistic')
    assert 'preprocessing' not in entry['inputs'] and 'preprocessing' not in fitted['values']
    out = flow.call('decide', 'propose', 'preprocessing', '--value-json',
                    json.dumps(governance.DEFAULT_PREPROCESSING), '--restatement', 'x',
                    '--rationale', 'x', '--request-id', 'pp', '--expected-revision', flow.rev(),
                    '--study', flow.study, expect=2)
    assert out['error']['code'] == 'unknown_decision'
    digest = flow.call('status', '--summary', '--digest', '--study', flow.study)
    steps = [s for m in digest['moments'] for s in m['steps']]
    assert 'success_criterion' not in steps and 'discover_data' in steps


# --- the case contract ----------------------------------------------------------------

@pytest.mark.parametrize('patch, path', [
    ({'group': ''}, 'variables[0].group'),
    ({'labels': {'de': 'Alter'}}, 'variables[0].labels.de'),
    ({'labels': {'fr': ' '}}, 'variables[0].labels.fr'),
    ({'range': {'min': 5, 'max': 1, 'status': 'observed', 'source': 'x'}}, 'variables[0].range'),
    ({'range': {'min': None, 'max': None, 'status': 'observed', 'source': 'x'}},
     'variables[0].range'),
])
def test_group_labels_and_range_are_validated(patch, path):
    import yaml
    doc = yaml.safe_load((fk.BANK / 'case.yaml').read_text(encoding='utf-8'))
    doc['variables'][0].update(copy.deepcopy(patch))
    problems = c.validate(doc)
    assert path in {p['path'] for p in problems}, problems


def test_a_declared_range_is_checked_by_the_quality_overview(tmp_path):
    import yaml
    case_dir = tmp_path / 'case'
    shutil.copytree(fk.BANK, case_dir)
    doc = yaml.safe_load((case_dir / 'case.yaml').read_text(encoding='utf-8'))
    age = next(v for v in doc['variables'] if v['name'] == 'age')
    age['range'] = {'min': 18, 'max': 70, 'status': 'scenario_assumption', 'source': 'test'}
    (case_dir / 'case.yaml').write_text(yaml.safe_dump(doc, sort_keys=False), encoding='utf-8')
    flow = Flow(tmp_path / 'study', case_dir)
    flow.init()
    ranges = {r['column']: r for r in flow.run('eda.quality')['values']['ranges']}
    assert ranges['age']['declared'] == {'min': 18, 'max': 70}
    assert ranges['age']['n_below'] == 0 and ranges['age']['n_above'] > 0
    assert ranges['balance']['declared'] is None and ranges['balance']['n_above'] is None


# --- pure governance functions ---------------------------------------------------------

def _view(task, criterion, results, verdict=None, policy='capacity:10'):
    decisions = {'success_criterion': {'status': 'confirmed', 'value': criterion}}
    if task == 'binary':
        decisions['policy'] = {'status': 'confirmed', 'value': policy}
    if verdict:
        decisions['conclusion'] = {'status': 'confirmed', 'value': {'verdict': verdict,
                                                                    'text': 'x'}}
    return {'task': task, 'decisions': decisions, 'results': results, 'open_proposals': []}


def _policy(point, low, high):
    return {'policy.evaluation': {'current': True, 'integrity': 'ok', 'result_id': 'r_pol',
                                  'values': {'rules': {'capacity:10': {'deltas': {
                                      'fit.logistic': {'precision': {'point': point, 'low': low,
                                                                     'high': high}}}}}}}}


@pytest.mark.parametrize('point, low, high, verdict, status, contradicts', [
    (0.10, 0.04, 0.16, 'adopt_policy', 'met', False),
    (0.10, -0.02, 0.22, 'adopt_policy', 'uncertain', True),
    (0.03, 0.01, 0.05, 'adopt_policy', 'not_met', True),
    (0.03, 0.01, 0.05, 'keep_baseline', 'not_met', False),
])
def test_the_binary_criterion_reads_the_paired_precision_gain(point, low, high, verdict, status,
                                                               contradicts):
    out = governance.assess(_view('binary', {'metric': 'precision_gain', 'min_points': 5},
                                  _policy(point, low, high), verdict))
    assert out['status'] == status and out['contradicts_verdict'] is contradicts
    assert out['gain'] == pytest.approx(100 * point) and out['rule'] == 'capacity:10'
    assert out['low'] == pytest.approx(100 * low) and out['result_id'] == 'r_pol'


def test_the_regression_criterion_is_a_share_of_the_baseline_error():
    results = {'evaluate.regression': {'current': True, 'integrity': 'ok', 'result_id': 'r_ev',
                                       'values': {'models': {'fit.baseline': {'mae': 5.0}},
                                                  'deltas': {'fit.linear': {'mae': {
                                                      'point': -1.0, 'low': -1.5,
                                                      'high': -0.5}}}}}}
    criterion = {'metric': 'mae_reduction', 'min_share': 0.1}
    out = governance.assess(_view('regression', criterion, results, 'adopt_model'))
    assert out['gain'] == pytest.approx(0.2)
    assert (out['low'], out['high']) == pytest.approx((0.1, 0.3))
    assert out['status'] == 'met' and out['contradicts_verdict'] is False
    stale = {k: {**v, 'current': False} for k, v in results.items()}
    assert governance.assess(_view('regression', criterion, stale,
                                   'adopt_model'))['status'] == 'not_assessed'
    assert governance.assess({'decisions': {}, 'task': 'binary'}) is None


def test_the_ledger_counts_every_exploration_that_read_the_target():
    records = [
        {'purpose': 'structural_inspection', 'activity': 'eda.quality', 'columns': ['a'],
         'result_id': 'q'},
        {'purpose': 'train_eda', 'activity': 'eda.distribution', 'columns': ['a'],
         'result_id': 'd1'},
        {'purpose': 'train_eda', 'activity': 'eda.distribution', 'columns': ['y'],
         'result_id': 'd2'},
        {'purpose': 'train_eda', 'activity': 'eda.rate_by', 'columns': ['y', 'a'],
         'result_id': 'r1'},
        {'purpose': 'train_eda', 'activity': 'eda.rate_by', 'columns': ['y', 'a'],
         'result_id': 'r1'},
        {'purpose': 'train_fit', 'activity': 'fit.logistic', 'columns': ['y', 'a'],
         'result_id': 'f'},
    ]
    out = governance.ledger(records, 'y')
    assert out['target_looks'] == 3 and out['results'] == ['d2', 'r1']
    assert out['by_activity'] == {'eda.distribution': 1, 'eda.rate_by': 2}


def test_uses_target_names_the_target_reading_results():
    assert governance.uses_target({'activity': 'eda.rate_by'})
    assert not governance.uses_target({'activity': 'eda.quality'})
    distribution = {'activity': 'eda.distribution', 'params': {'column': 'y'}, 'inputs': {}}
    assert governance.uses_target(distribution, 'y')
    assert not governance.uses_target(distribution, 'age')
    assert governance.uses_target({'activity': 'split',
                                   'inputs': {'decision': {'method': 'stratified_random'}}})
    assert not governance.uses_target({'activity': 'split',
                                       'inputs': {'decision': {'method': 'random'}}})
