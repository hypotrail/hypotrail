"""Fine-grained invalidation table (plan WP1.3, §3.7): one case per row, plus unknown."""
from __future__ import annotations

import copy

import pytest

from mlkit.study import dependencies as dep, registry, state as st
from mlkit.study.errors import StudyError

PT = 'before the first reminder'
FA = {'holds_open': 'available_at_prediction', 'desk_followups': 'not_available',
      'reminders_sent': 'uncertain_excluded'}
SPLIT = {'method': 'stratified_random', 'validation_fraction': 0.3, 'seed': 20261017}
SLOTS = ('split', 'eda.target_rate', 'eda.special_values', 'fit.baseline', 'fit.logistic',
         'policy.evaluation')


def _confirm(state, decision_id, value):
    pid = f'p_{decision_id}'
    proposal = {'proposal_id': pid, 'decision_id': decision_id, 'value': value,
                'restatement': f'You decide {decision_id}.', 'rationale': 'Test only.',
                'revision': 1, 'status': 'confirmed', 'created': st.now()}
    state['proposals'][pid] = proposal
    state['decisions'][decision_id].update(
        status='confirmed', value=value, proposal_id=pid, revision=1,
        confirmation=st.confirmation(user_words=f'Yes, {decision_id} as restated.',
                                     proposal=proposal, channel='chat', actor='junior',
                                     revision=1))


@pytest.fixture
def full(new_study):
    """A study where every decision is confirmed and every slot holds a result."""
    state = new_study.load_state()
    for d, v in (('prediction_time', PT), ('feature_availability', FA), ('split', SPLIT),
                 ('policy', 'capacity:100'),
                 ('conclusion', {'verdict': 'keep_baseline', 'text': 'Keep the baseline.'})):
        _confirm(state, d, v)
    code = registry.code_fingerprint(['mlkit.study.records'])

    def put(activity, **results):
        return registry.put(new_study, activity=activity, params={}, inputs={'results': results},
                            code=code, values={'activity': activity})['result_id']
    split = put('split')
    eda1, eda2 = put('eda.target_rate', split=split), put('eda.special_values', split=split)
    base, logit = put('fit.baseline', split=split), put('fit.logistic', split=split)
    policy = put('policy.evaluation', baseline=base, model=logit)
    state['current'] = dict(zip(SLOTS, (split, eda1, eda2, base, logit, policy)))
    assert st.validate_state(state) == []
    return new_study, state


ROWS = [
    # (row, decision_id, old, new, mutation, stale slots, reconfirm_required)
    (1, 'prediction_time', PT, 'after the first reminder', 'prediction_time',
     {'fit.logistic', 'policy.evaluation'}, {'feature_availability', 'policy', 'conclusion'}),
    (2, 'feature_availability', FA, {**FA, 'reminders_sent': 'uncertain_included'},
     'feature_availability.feature_set', {'fit.logistic', 'policy.evaluation'},
     {'policy', 'conclusion'}),
    (3, 'feature_availability', FA, {**FA, 'reminders_sent': 'not_available'},
     'feature_availability.wording', set(), set()),
    (4, 'split', SPLIT, {**SPLIT, 'seed': 7}, 'split', set(SLOTS), {'policy', 'conclusion'}),
    (5, 'policy', 'capacity:100', 'capacity:200', 'policy.parameter', set(), {'conclusion'}),
    (6, 'policy', 'capacity:100', 'threshold:0.3', 'policy.rule_type', set(), {'conclusion'}),
    (7, 'settings.bootstrap', {'replicates': 2000}, {'replicates': 500}, 'settings.bootstrap',
     {'policy.evaluation'}, {'conclusion'}),
    (8, 'usage_label', 'call list', 'mailing list', 'usage_label', set(), {'conclusion'}),
    (9, 'eda_added', None, 'eda.rate_by:home_branch', 'eda_added', set(), set()),
    (10, 'conclusion', {'verdict': 'keep_baseline', 'text': 'Keep the baseline.'},
     {'verdict': 'keep_baseline', 'text': 'Keep the constant baseline for now.'}, 'conclusion',
     set(), set()),
    (11, 'code_fingerprint', {'activity': 'fit.baseline', 'fingerprint': 'a'},
     {'activity': 'fit.baseline', 'fingerprint': 'b'}, 'code_fingerprint',
     {'fit.baseline', 'policy.evaluation'}, set()),
    ('*', 'mystery_setting', 1, 2, 'unknown', set(SLOTS),
     {'prediction_time', 'feature_availability', 'split', 'policy', 'conclusion'}),
]


def test_table_has_rows_one_to_eighteen_and_unknown():
    # WP-B2 adds row 13 for changing the explicitly selected binary model.
    # WP-A4 adds rows 14 to 16 (preprocessing, its motivation, the success criterion);
    # WP-B1 row 17 (the variant); reliability J3 row 18 (selection objective/rule).
    assert [m['row'] for m in dep.MUTATIONS] == \
        list(range(1, 19)) + ['*']


def test_row_18_reuses_fixed_predictions_and_recomputes_selection(full):
    _, state = full
    old = {'metric': 'precision_gain', 'min_points': 5,
           'selection': {'metric': 'precision', 'rule': 'share:0.1'}}
    new = {'metric': 'recall_gain', 'min_points': 5,
           'selection': {'metric': 'recall', 'rule': 'share:0.2'}}
    effect = dep.effects(state, 'success_criterion', old, new)
    assert effect['row'] == 18 and effect['mutation'] == 'success_criterion.selection'
    assert effect['refit'] == []
    assert effect['re_policy'] == ['policy.evaluation']
    assert effect['reconfirm'] == ['policy', 'conclusion']


@pytest.mark.parametrize('row, decision_id, old, new, mutation, stale_slots, reconfirm', ROWS,
                         ids=[str(r[0]) for r in ROWS])
def test_mutation_row(full, row, decision_id, old, new, mutation, stale_slots, reconfirm):
    store, state = full
    before = copy.deepcopy(state)
    eff = dep.effects(state, decision_id, old, new)
    assert state == before                                   # effects is pure
    assert set(dep.EFFECT_KEYS) <= set(eff)
    assert eff['mutation'] == mutation and eff['row'] == row
    assert eff['re_chart'] == sorted(set(eff['refit'] + eff['re_eda'] + eff['re_policy']
                                         + eff['recompute']))
    record = dep.apply_effects(state, eff, revision=9, decision_id=decision_id, store=store,
                               previous={'value': old})
    stale = {s for s, rid in state['current'].items() if rid in state['stale']}
    assert stale == stale_slots
    assert set(record['reconfirm_required']) == reconfirm
    for d in st.DECISION_IDS:
        expected = 'reconfirm_required' if d in reconfirm else 'confirmed'
        assert state['decisions'][d]['status'] == expected, d
        if d in reconfirm:   # the previous value and the user's words stay visible
            assert state['decisions'][d]['value'] == before['decisions'][d]['value']
            assert state['decisions'][d]['confirmation'] == before['decisions'][d]['confirmation']
            assert state['decisions'][d]['reason'] == eff['reason']
    for rid in state['stale']:
        assert state['stale'][rid] == {'reason': eff['reason'], 'since': 9}
    if stale or reconfirm:
        assert state['invalidations'][-1] == record
        assert record['reason'] == eff['reason'] and record['previous'] == {'value': old}
    assert state['facts'] == before['facts']                 # facts are never reconfirmed
    assert st.validate_state(state) == []


def test_row_1_blocks_the_logistic_refit_until_availability_is_reconfirmed(full):
    _, state = full
    eff = dep.effects(state, 'prediction_time', PT, 'after the first reminder')
    # WP-B1: in a new study the variant is the candidate with one change, so it refits too.
    assert eff['refit'] == ['fit.logistic', 'fit.variant']
    assert eff['blocked_until'] == ['feature_availability']


def test_row_3_only_rewrites_the_dictionary_text(full):
    _, state = full
    eff = dep.effects(state, 'feature_availability', FA, {**FA, 'reminders_sent': 'not_available'})
    assert eff['refit'] == eff['re_policy'] == eff['reconfirm'] == []
    assert eff['re_explain'] == ['feature_availability']


def test_row_4_keeps_exposure_and_reports_overlap(full):
    _, state = full
    eff = dep.effects(state, 'split', SPLIT, {**SPLIT, 'seed': 7})
    assert eff['refit'] == ['fit.baseline', 'fit.logistic'] and eff['recompute'] == ['split']
    assert eff['re_eda'] == ['eda.special_values', 'eda.target_rate']
    assert any('overlap' in n and 'retained' in n for n in eff['notes'])


@pytest.mark.parametrize('new, row', [('capacity:200', 5), ('threshold:0.3', 6)])
def test_rows_5_and_6_reuse_predictions_and_keep_the_policy_evaluation(full, new, row):
    _, state = full
    current = dict(state['current'])
    eff = dep.effects(state, 'policy', 'capacity:100', new)
    assert eff['row'] == row and eff['refit'] == [] and eff['re_policy'] == ['policy.evaluation']
    dep.apply_effects(state, eff, revision=9, decision_id='policy')
    # The policy confirmation itself requires a current evaluation of the new rule.
    assert state['current'] == current and not state['stale']


def test_row_7_only_recomputes_intervals(full):
    _, state = full
    eff = dep.effects(state, 'settings.bootstrap', {'replicates': 2000}, {'replicates': 500})
    assert eff['scope'] == 'intervals' and eff['refit'] == []


def test_row_11_propagates_downstream_through_lineage_only_with_the_store(full):
    store, state = full
    eff = dep.effects(state, 'code_fingerprint', {'activity': 'fit.baseline', 'fingerprint': 'a'},
                      {'activity': 'fit.baseline', 'fingerprint': 'b'})
    assert eff['refit'] == ['fit.baseline'] and eff['reconfirm'] == []
    alone = copy.deepcopy(state)
    dep.apply_effects(alone, eff, revision=9, decision_id='code_fingerprint')
    assert set(alone['stale']) == {state['current']['fit.baseline']}
    dep.apply_effects(state, eff, revision=9, decision_id='code_fingerprint', store=store)
    assert set(state['stale']) == {state['current']['fit.baseline'],
                                   state['current']['policy.evaluation']}


@pytest.mark.parametrize('mutation', ['dataset', 'case'])
def test_row_12_dataset_or_case_change_is_refused(full, mutation):
    _, state = full
    with pytest.raises(StudyError) as err:
        dep.effects(state, mutation, 'a' * 64, 'b' * 64)
    assert err.value.code == 'dataset_changed'


def test_unknown_mutation_invalidates_everything_with_its_reason(full):
    store, state = full
    documented = {k: v for k, v in state['facts'].items() if v['status'] == 'documented_fact'}
    eff = dep.effects(state, 'mystery_setting', 1, 2)
    record = dep.apply_effects(state, eff, revision=9, decision_id='mystery_setting', store=store)
    assert 'unknown mutation' in record['reason']
    assert set(state['stale']) == set(state['current'].values())
    assert {k: v for k, v in state['facts'].items() if v['status'] == 'documented_fact'} == documented


@pytest.mark.parametrize('decision_id, value', [('policy', 'capacity:100'),
                                                ('policy', 'bogus'), ('feature_availability', 3)])
def test_unparseable_values_fall_back_to_unknown(full, decision_id, value):
    _, state = full
    other = 'nonsense' if value == 'capacity:100' else 'capacity:100'
    assert dep.effects(state, decision_id, other, value)['mutation'] == 'unknown'


def test_first_confirmation_and_unchanged_value_have_no_effect(full):
    _, state = full
    before = copy.deepcopy(state)
    for old, new in ((None, PT), (PT, PT)):
        eff = dep.effects(state, 'prediction_time', old, new)
        assert eff['row'] is None and eff['reconfirm'] == [] and eff['refit'] == []
        dep.apply_effects(state, eff, revision=9, decision_id='prediction_time', store=full[0])
    assert state == before


def test_policy_parsing():
    assert dep.parse_policy('capacity:100') == ('capacity', 100)
    assert dep.parse_policy('threshold:0.25') == ('threshold', 0.25)
    for bad in ('capacity:0', 'threshold:2', 'capacity:x', 'top:3', 3, 'capacity'):
        assert dep.parse_policy(bad) is None
