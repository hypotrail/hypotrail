"""The v0.3 discovery case (WP-G): Hotel booking demand, Resort Hotel.

* the committed ``case.yaml`` is what ``build_case.py`` generates and the derived data pass
  their integrity checks (``test_v02b_cases.py`` enumerates it with the other cases);
* the case states the timeline of the booking: the outcome columns and what the hotel
  does after the booking are ``not_available``, the columns whose timing is not documented
  are ``uncertain``, and each statement cites its source or says it is a scenario
  assumption;
* ``init`` seals the latest fifth of the arrivals (temporal, whole duplicate groups), the
  data card reads the case, and a study runs to the policy evaluation with the leakage
  traps excluded; the single-feature signal flags the outcome column.

Studies live in temporary directories; the committed case is only read.
"""
from __future__ import annotations

import pytest

from mlkit.study import case as c, data

import flowkit as fk
from flowkit import Flow

HOTEL = fk.REPO / 'use-cases' / 'hotel-booking'

NOT_AVAILABLE = {'reservation_status', 'reservation_status_date', 'assigned_room_type',
                 'booking_changes', 'days_in_waiting_list'}
UNCERTAIN = {'country', 'deposit_type', 'adr', 'required_car_parking_spaces',
             'total_of_special_requests'}


def test_the_case_states_the_booking_timeline():
    case = c.load_case(HOTEL)
    assert case.task == 'binary' and case.duplicates_policy == 'group'
    assert case.document['target'] == {'column': 'is_canceled', 'positive_label': '1',
                                       'negative_label': '0'}
    assert case.order == {'by': 'line', 'direction': 'ascending', 'status': 'observed',
                          'source': case.order['source']}
    features = {v['name']: v for v in case.document['variables'] if v['role'] == 'feature'}
    assert len(features) == 30 and 'hotel' not in features      # Resort only
    by_value = {}
    for name, v in features.items():
        by_value.setdefault(v['availability']['value'], set()).add(name)
        assert v['availability']['source'].strip()
        assert v['source'].strip() and v['status'] == 'documented_fact'
    assert by_value['not_available'] == NOT_AVAILABLE
    assert by_value['uncertain'] == UNCERTAIN
    assert set(by_value) == {'available_at_prediction', 'not_available', 'uncertain'}
    # a timing claim is either sourced in the documentation or a stated scenario assumption
    for name in by_value['available_at_prediction'] | UNCERTAIN:
        assert features[name]['availability']['status'] == 'scenario_assumption', name
    assert 'check-in or cancellation' in features['booking_changes']['availability']['source']
    assert 'accepts' in features['days_in_waiting_list']['availability']['source']
    assert "preparer's assumption" in features['assigned_room_type']['availability']['source']
    assert 'nationality' in features['country']['availability']['source']
    facts = {f['id']: f for f in case.document['facts']}
    assert 'day prior to each booking' in facts['data_snapshot']['source']
    assert facts['prediction_time']['status'] == 'scenario_assumption'
    labels = data.load_dataset(case).frame['is_canceled'].astype(str).value_counts().to_dict()
    assert labels == {'0': 28938, '1': 11122}
    # v0.3 (WP-J): the interpretability the use case asks of a model, a stated assumption.
    interp = case.document['constraints']['interpretability']
    assert (interp['value'], interp['status']) == ('preferred', 'scenario_assumption')
    from mlkit.study import trials
    assert trials.constraints_of(case.document) == {'interpretability': 'preferred',
                                                    'declared': True}


@pytest.fixture(scope='module')
def hotel(tmp_path_factory):
    """The Resort Hotel study to the policy evaluation, availability as the case states it
    (uncertain features included: a test choice, not a recommendation)."""
    flow = Flow(tmp_path_factory.mktemp('hotel') / 'study', HOTEL, prefix='h')
    init = flow.init()
    out = {'init': init, 'card': flow.call('data', '--study', flow.study),
           'quality': flow.run('eda.quality')['values']}
    flow.pauses()
    out['split'] = flow.run('split')['values']
    out['signal'] = flow.run('eda.single_feature_signal')['values']
    flow.run('fit.baseline')
    out['fit'] = flow.run('fit.logistic')['values']
    out['policy'] = flow.run('policy.evaluate', '--rule', 'share:0.1')['values']
    return flow, out


def test_init_seals_the_latest_arrivals(hotel):
    flow, out = hotel
    final = out['init']['final_test']
    assert final['method'] == 'temporal' and final['schema_check'] == 'pass'
    # 20 % is 8,012 rows; one copy of a duplicate group divided by the cut moves to the
    # development side with its group
    assert (final['rows'], final['development_rows']) == (8011, 32049)
    assert flow.state()['partition']['groups']['moved_rows'] == 1
    assert flow.state()['partition']['order']['ties_at_cut'] == 0
    sealed = set(fk.partition_keys(flow.study, 'final_test'))
    dev = set(fk.partition_keys(flow.study, 'development'))
    # arrival order: every sealed row comes after every development row but those moved
    # to keep a duplicate group whole (their copies sit before the cut)
    last_dev = max(int(k[1:]) for k in dev)
    first_sealed = min(int(k[1:]) for k in sealed)
    assert first_sealed >= 40061 - 8012
    groups = data.entity_groups(data.row_index(c.load_case(HOTEL)))
    assert not {groups[k] for k in dev} & {groups[k] for k in sealed}
    moved = flow.state()['partition']['groups']['moved_rows']
    assert sum(int(k[1:]) > first_sealed for k in dev) <= moved
    assert last_dev <= 40061
    card = out['card']
    assert card['development']['rows'] == final['development_rows']
    assert card['development']['duplicates']['policy'] == 'group'
    assert {g['group'] for g in card['groups']} == {
        'Outcome', 'Stay requested', 'Customer and history', 'Sale and terms',
        'Hotel handling of the booking', 'Customer requests'}
    assert flow.view()['scenario_defaults']['capacity_share']['value'] == 0.1


def test_the_study_runs_to_the_policy_without_the_traps(hotel):
    flow, out = hotel
    assert out['split']['duplicates']['divided_groups'] == 0
    features = set(out['fit']['features'])
    assert not features & NOT_AVAILABLE and UNCERTAIN <= features
    assert 0.6 < out['fit']['validation']['roc_auc'] < 0.99
    entry = out['policy']['rules']['share:0.1']['models']['fit.logistic']
    assert entry['capacity'] == round(0.1 * out['policy']['n'])


def test_the_outcome_raises_the_legitimacy_question(hotel):
    """The signal scores every feature, the excluded ones too: the outcome columns stand
    out and raise the question "is its value known at the prediction moment?"."""
    _, out = hotel
    signal = out['signal']
    assert signal['signals'][0]['feature'] in {'reservation_status', 'reservation_status_date'}
    flagged = {q['feature'] for q in signal['questions']}
    assert 'reservation_status' in flagged
    assert signal['signals'][0]['availability'] == 'not_available'
