"""Pure contract oracles for reliability-roadmap J2."""
import pytest

from mlkit.reliability import CommandRefused
from mlkit.study import validity


def case_document(restricted=True, interpretability='required'):
    availability = {'value': 'not_available' if restricted else 'unknown',
                    'status': 'documented_fact' if restricted else 'unknown', 'source': 'case'}
    if restricted:
        availability['restriction'] = {'scenario_id': 's1',
                                       'kind': 'unavailable_at_prediction',
                                       'source': 'measurement protocol'}
    return {'analysis_contract': {
                'scenario_id': 's1', 'prediction_statement': 'Predict at intake',
                'intended_use': 'future_prediction',
                'timing': {'prediction_order': {'status': 'documented_fact'},
                           'outcome_available_order': {'status': 'documented_fact'}},
                'permitted_claims': ['future_predictive_performance']},
            'variables': [{'name': 'outcome_copy', 'availability': availability}],
            'constraints': {'interpretability': {'value': interpretability,
                                                 'source': 'case'}}}


def test_j2_a01_documented_unavailability_is_a_hard_refusal():
    adopted = {'outcome_copy': 'available_at_prediction'}
    with pytest.raises(CommandRefused) as err:
        validity.require_availability(case_document(), adopted)
    assert err.value.details['reason'] == 'documented_unavailability'
    assert err.value.details['problems'][0]['source'] == 'measurement protocol'


def test_j2_a02_uncertain_inclusion_is_allowed_but_limits_claim():
    case = case_document(restricted=False)
    state = {'decisions': {
        'prediction_time': {'status': 'confirmed', 'value': 'Predict at intake'},
        'feature_availability': {'status': 'confirmed',
                                 'value': {'outcome_copy': 'uncertain_included'}}},
        'current': {}, 'stale': {}, 'task': 'binary'}
    out = validity.evaluate(state, case)
    timing = next(r for r in out['requirements'] if r['code'] == 'feature_timing_supported')
    assert timing['satisfied']
    assert timing['detail']['uncertain_included'] == ['outcome_copy']
    assert not out['claim_eligibility']['eligible']


def test_j2_requirement_objects_have_one_frozen_shape():
    out = validity.evaluate({'decisions': {}, 'current': {}, 'stale': {}}, {})
    assert [r['code'] for r in out['requirements']] == list(validity.REQUIREMENT_CODES)
    assert all(tuple(r) == ('code', 'satisfied', 'result_id', 'detail')
               for r in out['requirements'])


def test_j2_a12_calibration_is_not_automatically_claim_eligible():
    state = {'decisions': {}, 'current': {'diag.binary': 'r1'}, 'stale': {}, 'task': 'binary'}
    out = validity.evaluate(state, case_document(False), claim='calibrated_probability')
    requirement = next(r for r in out['requirements']
                       if r['code'] == 'uncertainty_available_for_claim')
    assert not requirement['satisfied']
    assert not out['claim_eligibility']['eligible']
