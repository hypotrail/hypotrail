"""Derived review-v1 validity requirements.

There is intentionally no stored ``valid`` flag.  Requirements are recomputed from
the verified case/state/result snapshot so command, execution and view paths share
one answer and a hand-edited state cannot bypass a restriction.
"""
from __future__ import annotations

from typing import Any, Mapping

REQUIREMENT_CODES = (
    'scenario_bound', 'analysis_contract_present', 'feature_timing_supported',
    'evaluation_protocol_current', 'choice_evaluation_current',
    'selected_configuration_current', 'development_diagnostics_current',
    'interpretability_constraint_satisfied', 'uncertainty_available_for_claim',
    'final_evidence_current_for_configuration',
)


def _document(case):
    return getattr(case, 'document', case) if case is not None else {}


def restrictions(case) -> dict[str, dict]:
    """Documented availability restrictions keyed by feature name."""
    out = {}
    for variable in _document(case).get('variables', []):
        availability = variable.get('availability') or {}
        restriction = availability.get('restriction')
        if isinstance(restriction, Mapping) \
                and restriction.get('kind') == 'unavailable_at_prediction':
            out[variable.get('name')] = dict(restriction)
    return out


def availability_problems(case, adopted: Any, scenario_id: str | None = None) -> list[dict]:
    """Hard documented contradictions in an availability decision."""
    if not isinstance(adopted, Mapping):
        return []
    contract = _document(case).get('analysis_contract') or {}
    bound = scenario_id or contract.get('scenario_id')
    problems = []
    for column, restriction in restrictions(case).items():
        if restriction.get('scenario_id') == bound \
                and adopted.get(column) in ('available_at_prediction', 'uncertain_included'):
            problems.append({'reason': 'documented_unavailability', 'column': column,
                             'scenario_id': bound, 'source': restriction.get('source')})
    return problems


def require_availability(case, adopted: Any, scenario_id: str | None = None) -> None:
    problems = availability_problems(case, adopted, scenario_id)
    if problems:
        from mlkit.reliability import CommandRefused
        raise CommandRefused('invalid_value',
                             'A documented restriction forbids including this feature in '
                             'the bound prediction scenario.',
                             details={'reason': 'documented_unavailability',
                                      'problems': problems})


def _current(state, slot):
    current = state.get('current') or {}
    rid = current.get(slot)
    return rid if rid is not None and rid not in (state.get('stale') or {}) else None


def _requirement(code, satisfied, *, result_id=None, detail=None):
    return {'code': code, 'satisfied': bool(satisfied), 'result_id': result_id,
            'detail': detail}


def _confirmed_value(state, decision):
    item = (state.get('decisions') or {}).get(decision) or {}
    return item.get('value') if item.get('status') == 'confirmed' else None


def _result_metadata(results, result_id):
    if not result_id or not isinstance(results, Mapping):
        return None
    item = results.get(result_id)
    if item is not None:
        return item
    # Views commonly key results by slot rather than by id.
    return next((value for value in results.values()
                 if isinstance(value, Mapping) and value.get('result_id') == result_id), None)


def _matches_configuration(item, chosen, *, population=None) -> bool:
    if not isinstance(item, Mapping) or not isinstance(chosen, Mapping):
        return False
    params, values = item.get('params') or {}, item.get('values') or {}
    model = params.get('model', values.get('model'))
    rule = params.get('rule', values.get('rule'))
    models = params.get('models') or []
    model_ok = chosen.get('model') == model or chosen.get('model') in models
    rule_ok = chosen.get('rule') is None or chosen.get('rule') == rule \
        or chosen.get('rule') in (params.get('rules') or [])
    population_ok = population is None or values.get('population', population) == population
    return model_ok and rule_ok and population_ok


def evaluate(state: Mapping, case=None, results: Mapping | None = None,
             claim: str | None = None) -> dict:
    """Return the canonical requirement list and derived claim eligibility."""
    document, results = _document(case), results or {}
    contract = document.get('analysis_contract')
    prediction = _confirmed_value(state, 'prediction_time')
    availability = _confirmed_value(state, 'feature_availability')
    scenario_ok = bool(contract and prediction and
                       ' '.join(str(prediction).split()) ==
                       ' '.join(str(contract.get('prediction_statement', '')).split()))
    analysis_ok = isinstance(contract, Mapping)
    hard = availability_problems(document, availability)
    uncertain = sorted(k for k, v in (availability or {}).items()
                       if v == 'uncertain_included') if isinstance(availability, Mapping) else []
    timing_ok = bool(analysis_ok and not hard)
    if contract and contract.get('intended_use') == 'future_prediction':
        timing = contract.get('timing') or {}
        timing_ok = timing_ok and all(isinstance(timing.get(k), Mapping) and
                                      timing[k].get('status') == 'documented_fact'
                                      for k in ('prediction_order', 'outcome_available_order'))
    split_id = _current(state, 'split')
    task = ((state.get('facts') or {}).get('task') or {}).get('value') \
        if isinstance((state.get('facts') or {}).get('task'), Mapping) else state.get('task')
    if task not in ('binary', 'regression'):
        task = 'regression' if 'model_choice' in (state.get('decisions') or {}) else 'binary'
    choice_slot = 'policy.evaluation' if task == 'binary' else 'evaluate.regression'
    choice_id = _current(state, choice_slot)
    chosen = None
    if task == 'binary':
        policy = _confirmed_value(state, 'policy')
        if isinstance(policy, str):
            from . import records
            chosen = {'model': records.policy_model(policy),
                      'rule': records.policy_rule(policy)}
    else:
        model = _confirmed_value(state, 'model_choice')
        chosen = {'model': model, 'rule': None} if model else None
    selected_ok = bool(chosen and choice_id)
    diag_slot = 'diag.binary' if task == 'binary' else 'diag.regression'
    diag_id = _current(state, diag_slot)
    diag_item = _result_metadata(results, diag_id)
    diag_ok = bool(diag_id and (not results or _matches_configuration(
        diag_item, chosen, population='development')))
    constraint = ((document.get('constraints') or {}).get('interpretability') or {}).get('value')
    nonlinear_black_box = chosen and chosen.get('model', '').startswith('fit.variant') \
        and ((diag_item or {}).get('values') or {}).get('family') == 'hgb'
    interpretability_ok = not (constraint == 'required' and nonlinear_black_box)
    uncertainty_ok = claim not in ('lower_bound_success', 'calibrated_probability')
    final_id = _current(state, 'final_test.evaluation')
    final_diag_id = _current(state, 'diag.final_test')
    final_item = _result_metadata(results, final_id)
    final_ok = bool(final_id and final_diag_id and chosen and
                    (not results or _matches_configuration(final_item, chosen)))
    requirements = [
        _requirement('scenario_bound', scenario_ok,
                     detail=None if scenario_ok else 'The adopted prediction moment is not '
                     'bound to the case scenario.'),
        _requirement('analysis_contract_present', analysis_ok,
                     detail=None if analysis_ok else 'The case has no analysis contract.'),
        _requirement('feature_timing_supported', timing_ok,
                     detail={'documented_conflicts': hard, 'uncertain_included': uncertain}),
        _requirement('evaluation_protocol_current', bool(split_id), result_id=split_id,
                     detail=None if split_id else 'The evaluation plan is missing or stale.'),
        _requirement('choice_evaluation_current', bool(choice_id), result_id=choice_id,
                     detail=None if choice_id else 'The choice evaluation is missing or stale.'),
        _requirement('selected_configuration_current', selected_ok, result_id=choice_id,
                     detail={'configuration': chosen}),
        _requirement('development_diagnostics_current', diag_ok, result_id=diag_id,
                     detail={'configuration': chosen, 'population': 'development'}),
        _requirement('interpretability_constraint_satisfied', interpretability_ok,
                     detail={'constraint': constraint, 'configuration': chosen}),
        _requirement('uncertainty_available_for_claim', uncertainty_ok,
                     detail=None if uncertainty_ok else
                     'No qualified uncertainty supports this claim.'),
        _requirement('final_evidence_current_for_configuration', final_ok,
                     result_id=final_diag_id or final_id,
                     detail={'configuration': chosen, 'evaluation_result_id': final_id,
                             'diagnostic_result_id': final_diag_id}),
    ]
    permitted = set(contract.get('permitted_claims') or []) if contract else set()
    eligible = all(r['satisfied'] for r in requirements[:8])
    if claim:
        eligible = eligible and claim in permitted and uncertainty_ok
    return {'requirements': requirements, 'completion': {
                'complete': all(r['satisfied'] for r in requirements),
                'missing': [r['code'] for r in requirements if not r['satisfied']]},
            'claim_eligibility': {'claim': claim, 'eligible': eligible,
                                  'uncertain_included': uncertain,
                                  'limitations': [r for r in requirements
                                                  if not r['satisfied']]}}


requirements = evaluate
