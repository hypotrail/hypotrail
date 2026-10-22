"""Analysis-contract validation and cooperative assurance (review roadmap J0).

Pure metadata only: this module reads no data, imports no writer and establishes no
scientific eligibility. A claim ceiling is not evidence that the claim is supported.
"""
from __future__ import annotations

PROFILES = ('legacy', 'review-v1')
ANALYSIS_SCHEMA = 'hypotrail.analysis/1'
ANALYSIS_KEYS = ('schema', 'scenario_id', 'intended_use', 'row_unit', 'population',
                 'prediction_statement', 'timing', 'dependencies', 'permitted_claims')
USES = ('retrospective_comparison', 'future_prediction', 'leakage_exercise')
DEPENDENCIES = ('independent', 'grouped', 'temporal', 'grouped_temporal', 'unknown')
CLAIMS = ('retrospective_association', 'future_predictive_performance', 'calibrated_probability')
TIMING_KEYS = ('prediction_order', 'outcome_available_order', 'scale')
CLOCK_KEYS = ('by', 'status', 'source')
DEPENDENCY_KEYS = ('kind', 'group_column', 'group_goal', 'status', 'source')
ASSURANCE_KEYS = ('profile', 'evaluation_protection', 'consent_provenance',
                  'cross_study_history', 'analysis_contract_status', 'claim_scope')
NOTICE_KEYS = ('code', 'audience', 'message', 'junior_message')
CAPABILITY = 'review-v1 analytical execution'


def profile(state) -> str:
    """Missing means legacy, without modifying the supplied state."""
    return state.get('settings', {}).get('reliability_profile', 'legacy')


def validate(contract, variables, problems) -> None:
    """Validate a static analysis declaration using the case validator's collector."""
    p, root = problems, 'analysis_contract'
    if not p.keys(contract, root, ANALYSIS_KEYS):
        return
    if contract['schema'] != ANALYSIS_SCHEMA:
        p.add(f'{root}.schema', f'must be {ANALYSIS_SCHEMA}')
    for key in ('scenario_id', 'row_unit', 'population', 'prediction_statement'):
        p.text(contract[key], f'{root}.{key}')
    use = contract['intended_use']
    if use not in USES:
        p.add(f'{root}.intended_use', f'must be one of {", ".join(USES)}')
    columns = {v['name']: v for v in variables if isinstance(v.get('name'), str)}
    timing = contract['timing']
    if p.keys(timing, f'{root}.timing', TIMING_KEYS):
        if timing['scale'] != 'ordinal':
            p.add(f'{root}.timing.scale', 'must be ordinal on one shared ascending scale')
        for key in TIMING_KEYS[:2]:
            clock, path = timing[key], f'{root}.timing.{key}'
            if clock is None:
                if use == 'future_prediction':
                    p.add(path, 'future prediction requires a documented clock')
                continue
            if not p.keys(clock, path, CLOCK_KEYS):
                continue
            p.status(clock['status'], f'{path}.status')
            p.text(clock['source'], f'{path}.source')
            by = clock['by']
            if not isinstance(by, str) or not by.strip():
                p.add(f'{path}.by', 'must name a non-target numeric/integer column or line')
            elif by == 'line':
                if 'line' in columns:
                    p.add(f'{path}.by', 'line is ambiguous with a variable name')
                if use == 'future_prediction':
                    p.add(f'{path}.by', 'file order alone does not establish future timing')
            elif by not in columns or columns[by]['role'] == 'target' \
                    or columns[by]['type'] not in ('numeric', 'integer'):
                p.add(f'{path}.by', 'must name a non-target numeric/integer column')
            if use == 'future_prediction' and clock['status'] != 'documented_fact':
                p.add(f'{path}.status', 'future prediction requires documented clock semantics')
        clock_columns = [clock.get('by') for clock in (timing[k] for k in TIMING_KEYS[:2])
                         if isinstance(clock, dict) and isinstance(clock.get('by'), str)
                         and clock['by'] in columns]
        units = {columns[name].get('unit') for name in clock_columns
                 if isinstance(columns[name].get('unit'), str)}
        if len(units) > 1:
            p.add(f'{root}.timing', 'declared clock units must share one comparable scale')
    dep = contract['dependencies']
    if p.keys(dep, f'{root}.dependencies', DEPENDENCY_KEYS):
        path = f'{root}.dependencies'
        p.status(dep['status'], f'{path}.status')
        p.text(dep['source'], f'{path}.source')
        if dep['kind'] not in DEPENDENCIES:
            p.add(f'{path}.kind', f'must be one of {", ".join(DEPENDENCIES)}')
        if dep['kind'] in ('grouped', 'grouped_temporal'):
            col = dep['group_column']
            if not isinstance(col, str) or col not in columns or columns[col]['role'] == 'target':
                p.add(f'{path}.group_column', 'must name a non-target group column')
            if dep['group_goal'] != 'unseen_groups':
                p.add(f'{path}.group_goal', 'only unseen_groups is supported')
        elif dep['group_column'] is not None or dep['group_goal'] is not None:
            p.add(path, 'non-grouped dependencies require null group_column and group_goal')
    claims = contract['permitted_claims']
    if not isinstance(claims, list) or any(not isinstance(c, str) or c not in CLAIMS
                                           for c in claims):
        p.add(f'{root}.permitted_claims', f'must be a list drawn from {", ".join(CLAIMS)}')
    elif len(claims) != len(set(claims)):
        p.add(f'{root}.permitted_claims', 'must not contain duplicate claims')
    elif use != 'future_prediction' and 'future_predictive_performance' in claims:
        p.add(f'{root}.permitted_claims', 'a retrospective/exercise scenario cannot claim future performance')


def describe(state, case=None) -> dict:
    contract = case.document.get('analysis_contract') if case is not None else None
    return dict(zip(ASSURANCE_KEYS, (
        profile(state), 'protocol_reserved', 'agent_reported', 'not_enforced',
        'present' if contract is not None else 'absent',
        list(contract['permitted_claims']) if contract is not None else [],
    )))


def scope_notice(case, language='en') -> str:
    contract = case.document.get('analysis_contract') if case is not None else None
    if contract and contract['intended_use'] == 'leakage_exercise':
        return ("La performance au moment de prédiction annoncé n'est pas établie. "
                "Ce cas sert à examiner les fuites d'information et les limites des preuves."
                if language == 'fr' else
                'Performance at the declared prediction time is not established. '
                'This case is an exercise in leakage and evidence limits.')
    return ''


def protection_notice(language='en') -> str:
    return ("Le test est réservé par le protocole ; le fichier source local reste accessible. "
            "Les confirmations sont rapportées par l'agent, sans authentification indépendante. "
            "L'historique entre études n'est pas imposé."
            if language == 'fr' else
            'The test is reserved by the protocol; the local source file remains accessible. '
            'Confirmations are agent-reported, not independently authenticated. '
            'Cross-study history is not enforced.')


def initial_notices(case, language='en') -> list[dict]:
    """Junior-facing init notices in the existing message/junior-message convention."""
    notices = [{
        'code': 'cooperative_evaluation_protection', 'audience': 'junior',
        'message': protection_notice(), 'junior_message': protection_notice(language),
    }]
    scope = scope_notice(case, language)
    if scope:
        notices.append({
            'code': 'analysis_claim_scope', 'audience': 'junior',
            'message': scope_notice(case), 'junior_message': scope,
        })
    assert all(tuple(notice) == NOTICE_KEYS for notice in notices)
    return notices


def require_activity(state, activity):
    """A review-v1 study needs a validated analysis contract before analysis."""
    if profile(state) != 'review-v1' or activity == 'eda.quality':
        return
    from .case import case_of
    from mlkit.reliability import CommandRefused
    contract = case_of(state).document.get('analysis_contract')
    if contract is None:
        raise CommandRefused('unsupported_capability',
                             'Review-v1 analytical execution needs an analysis contract.',
                             details={'capability': CAPABILITY,
                                      'reason': 'analysis_contract_missing',
                                      'activity': activity, 'profile': 'review-v1'})


def require_initialization(case, requested_profile):
    """J1 supplies the review-v1 partition planner; missing contracts remain legacy."""
    contract = case.document.get('analysis_contract')
    if requested_profile != 'review-v1' or contract is None:
        return
    return


def require_prediction_statement(state, value):
    """Bind the opt-in scenario without interpreting free text as equivalent evidence."""
    if profile(state) != 'review-v1':
        return
    from .case import case_of
    from mlkit.reliability import CommandRefused
    case = case_of(state)
    contract = case.document.get('analysis_contract')
    if contract is not None and ' '.join(value.split()) != ' '.join(
            contract['prediction_statement'].split()):
        raise CommandRefused('invalid_value',
                             'The prediction moment must match the declared scenario. '
                             'A different scenario needs a revised case and a new study.',
                             details={'reason': 'scenario_mismatch',
                                      'scenario_id': contract['scenario_id'],
                                      'expected': contract['prediction_statement']})
