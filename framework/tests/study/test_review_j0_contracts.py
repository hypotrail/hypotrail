"""J0 acceptance: metadata contracts and cooperative limits, synthetic studies only."""
from __future__ import annotations

import copy
import json

import pytest
import yaml
from mlkit.reliability import CommandRefused

from mlkit.study import assurance, case as c, cli, commands, read, state as st, store as sto
from mlkit.study.errors import StudyError
import flowkit as fk


def make_review(tmp_path, *, future=False):
    return fk._module.make_review_case(tmp_path / 'case', future=future)


def write_case(paths, document):
    paths['case'].write_text(yaml.safe_dump(document, sort_keys=False), encoding='utf-8')


def init(paths, study, *extra):
    return cli.run(['init', '--case', str(paths['case']), '--study', str(study), *extra])


def state_bytes(study):
    return {p.name: p.read_bytes() for p in (study / '.hypotrail').iterdir()
            if p.is_file() and p.suffix in ('.json', '.sha256', '.jsonl')}


def test_j0_a01_missing_profile_reads_as_legacy_without_writes(tmp_path):
    paths = make_review(tmp_path)
    study = tmp_path / 'study'
    assert init(paths, study).exit_code == 0
    before = state_bytes(study)
    s = read.open(study).state
    assert 'reliability_profile' not in s['settings']
    assert assurance.profile(s) == 'legacy'
    for args in (['status'], ['status', '--summary'], ['plan'], ['data']):
        assert cli.run([*args, '--study', str(study)]).exit_code == 0
    assert state_bytes(study) == before


@pytest.mark.parametrize('language', ['en', 'fr'])
def test_j0_a02_profile_is_opt_in_and_decisions_stay_open(tmp_path, language):
    paths = make_review(tmp_path)
    study = tmp_path / 'study'
    result = init(paths, study, '--reliability-profile', 'review-v1', '--lang', language)
    assert result.exit_code == 0, result.payload
    protection = next(n for n in result.payload['notices']
                      if n['code'] == 'cooperative_evaluation_protection')
    assert tuple(protection) == assurance.NOTICE_KEYS
    assert protection['message'] == assurance.protection_notice()
    assert protection['junior_message'] == assurance.protection_notice(language)
    s = read.open(study).state
    assert s['settings']['reliability_profile'] == 'review-v1'
    assert all(d['status'] == 'open' for d in s['decisions'].values())
    out = commands.status(study).payload['view']
    assert out['assurance'] == {
        'profile': 'review-v1', 'evaluation_protection': 'protocol_reserved',
        'consent_provenance': 'agent_reported', 'cross_study_history': 'not_enforced',
        'analysis_contract_status': 'present', 'claim_scope': ['retrospective_association']}
    assert tuple(out['assurance']) == assurance.ASSURANCE_KEYS
    short = cli.run(['status', '--summary', '--fields', 'assurance', '--study', str(study)])
    assert short.exit_code == 0 and short.payload['assurance'] == out['assurance']
    assert assurance.profile(s) == 'review-v1'
    assert 'J1' not in out['assurance']['claim_scope']


@pytest.mark.parametrize(('path', 'value'), [
    (('schema',), 'wrong/1'),
    (('extra',), 'not accepted'),
    (('timing', 'extra'), 'not accepted'),
    (('timing', 'prediction_order'), {'by': 'absent', 'status': 'documented_fact', 'source': 'test'}),
    (('timing', 'prediction_order'), {'by': 'subscribed', 'status': 'documented_fact', 'source': 'test'}),
    (('timing', 'prediction_order'), {'by': [], 'status': 'documented_fact', 'source': 'test'}),
    (('dependencies', 'kind'), 'magic'),
    (('dependencies', 'source'), ''),
    (('dependencies', 'group_goal'), 'known_clients'),
    (('permitted_claims',), ['causal_effect']),
    (('permitted_claims',), ['retrospective_association', 'retrospective_association']),
    (('permitted_claims',), ['future_predictive_performance']),
    (('intended_use',), 'deployment'),
])
def test_j0_a03_invalid_analysis_is_structured_and_creates_no_study(tmp_path, path, value):
    paths = make_review(tmp_path)
    document = yaml.safe_load(paths['case'].read_text())
    node = document['analysis_contract']
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    write_case(paths, document)
    study = tmp_path / 'study'
    out = init(paths, study, '--reliability-profile', 'review-v1')
    assert out.exit_code == 2, out.payload
    assert out.payload['error']['code'] == 'invalid_case'
    assert not (study / '.hypotrail').exists()


def test_j0_a03_target_clock_and_target_group_rejected(tmp_path):
    paths = make_review(tmp_path)
    document = yaml.safe_load(paths['case'].read_text())
    target = document['target']['column']
    document['analysis_contract']['timing']['prediction_order'] = {
        'by': target, 'status': 'documented_fact', 'source': 'test'}
    document['analysis_contract']['dependencies'].update(
        kind='grouped', group_column=target, group_goal='unseen_groups')
    write_case(paths, document)
    with pytest.raises(c.CaseError) as err:
        c.load_case(paths['case'])
    bad_paths = {p['path'] for p in err.value.problems}
    assert 'analysis_contract.timing.prediction_order.by' in bad_paths
    assert 'analysis_contract.dependencies.group_column' in bad_paths


def test_j0_a03_unknown_profile_is_refused_before_creation(tmp_path):
    paths = make_review(tmp_path)
    study = tmp_path / 'study'
    out = init(paths, study, '--reliability-profile', 'magic')
    assert out.exit_code == 2
    assert not study.exists()
    with pytest.raises(StudyError) as err:
        commands.init(paths['case'], study, reliability_profile='magic')
    assert err.value.code == 'invalid_arguments'
    assert not study.exists()


def test_j0_future_contract_has_planted_clocks_and_j1_partition(tmp_path):
    paths = make_review(tmp_path, future=True)
    case = c.load_case(paths['case'])
    contract = case.document['analysis_contract']
    assert contract['timing']['prediction_order']['by'] == 'prediction_tick'
    assert contract['timing']['outcome_available_order']['by'] == 'outcome_tick'
    from mlkit.study import data
    frame = data.load_dataset(case).frame
    assert list(frame['prediction_tick']) == list(range(1, 301))
    assert list(frame['outcome_tick'] - frame['prediction_tick']) == [2] * 300

    out = init(paths, tmp_path / 'study', '--reliability-profile', 'review-v1')
    assert out.exit_code == 0, out.payload
    part = read.open(tmp_path / 'study').state['partition']
    assert part['method'] == 'temporal'
    assert part['analysis_protocol']['intended_use'] == 'future_prediction'
    assert part['order']['by'] == 'prediction_tick'
    assert part['training_exclusions']['n_rows'] == 2


def test_j0_final_opening_is_refused_before_confirming_the_decision(tmp_path):
    paths = make_review(tmp_path)
    study = tmp_path / 'study'
    assert init(paths, study, '--reliability-profile', 'review-v1').exit_code == 0
    store = sto.StudyStore(study)
    with store.writing() as state:
        revision = state['revision'] + 1
        value = {'model': 'fit.logistic', 'rule': 'capacity:1'}
        state['proposals']['p_direct_final'] = {
            'proposal_id': 'p_direct_final', 'decision_id': 'final_test', 'value': value,
            'restatement': 'Open the final test once.', 'rationale': 'Direct-path guard test.',
            'revision': revision, 'status': 'open', 'created': st.now(),
        }
        state['decisions']['final_test'].update(
            status='proposed', value=value, proposal_id='p_direct_final', revision=revision)
        store.commit(state, {'request_id': 'fixture-final-proposal',
                             'action': 'test.fixture', 'params': {}, 'result': {}})
    before = state_bytes(study)
    out = cli.run(['decide', 'confirm', 'p_direct_final', '--user-words',
                   'Yes, I open the final test now.', '--request-id', 'direct-final-confirm',
                   '--expected-revision', str(read.open(study).state['revision']),
                   '--study', str(study)])
    assert out.exit_code == 2, out.payload
    assert out.payload['error']['code'] == 'precondition_missing'
    after = state_bytes(study)
    assert {k: v for k, v in after.items() if k != 'events.jsonl'} == {
        k: v for k, v in before.items() if k != 'events.jsonl'}
    assert read.open(study).state['decisions']['final_test']['status'] == 'proposed'


@pytest.mark.parametrize('mutation', ['null_clock', 'file_clock', 'assumed_clock'])
def test_j0_future_clocks_require_documented_semantics(tmp_path, mutation):
    paths = make_review(tmp_path, future=True)
    document = yaml.safe_load(paths['case'].read_text())
    timing = document['analysis_contract']['timing']
    if mutation == 'null_clock':
        timing['outcome_available_order'] = None
    elif mutation == 'file_clock':
        timing['prediction_order']['by'] = 'line'
    else:
        timing['prediction_order']['status'] = 'scenario_assumption'
    write_case(paths, document)
    with pytest.raises(c.CaseError) as err:
        c.load_case(paths['case'])
    assert err.value.code == 'invalid_case'
    assert any(p['path'].startswith('analysis_contract.timing.') for p in err.value.problems)


@pytest.mark.parametrize('with_contract', [False, True])
def test_j0_a04_inspection_allowed_but_pending_calculations_refused(tmp_path, with_contract):
    paths = make_review(tmp_path)
    if not with_contract:
        document = yaml.safe_load(paths['case'].read_text())
        del document['analysis_contract']
        write_case(paths, document)
    study = tmp_path / 'study'
    assert init(paths, study, '--reliability-profile', 'review-v1').exit_code == 0
    for command in ('data', 'plan', 'status'):
        assert cli.run([command, '--study', str(study)]).exit_code == 0
    before = state_bytes(study)
    for activity in ('split', 'fit.baseline', 'fit.logistic', 'final_test.evaluation'):
        out = cli.run(['run', activity, '--study', str(study), '--request-id', f'x-{activity}',
                       '--expected-revision', '1'])
        assert out.payload['error']['code'] == (
            'precondition_missing' if with_contract else 'unsupported_capability'), out.payload
        if not with_contract:
            assert out.payload['error']['details']['reason'] == 'analysis_contract_missing'
    after = state_bytes(study)
    assert {k: v for k, v in after.items() if k != 'events.jsonl'} == {
        k: v for k, v in before.items() if k != 'events.jsonl'}
    # Existing reliability machinery audits refused writer transactions. It does
    # not reserve an execution, expose rows, update state or create a receipt.
    assert after['events.jsonl'].startswith(before['events.jsonl'])
    audit = after['events.jsonl'][len(before['events.jsonl']):].splitlines()
    assert audit and all(json.loads(line)['kind'] == 'transaction_rolled_back' for line in audit)


@pytest.mark.parametrize('language', ['en', 'fr'])
def test_j0_a05_hotel_scope_in_card_plan_and_summary_without_fitting(tmp_path, language):
    # A tiny synthetic dataset with the committed adapter's analysis declaration;
    # no Hotel row, historical final partition or model is read for this acceptance.
    paths = make_review(tmp_path)
    hotel = c.load_case(fk.REPO / 'use-cases/hotel-booking', verify_data=False)
    contract = hotel.document['analysis_contract']
    assert contract['intended_use'] == 'leakage_exercise'
    assert contract['permitted_claims'] == ['retrospective_association']
    document = yaml.safe_load(paths['case'].read_text())
    document['analysis_contract'] = copy.deepcopy(contract)
    write_case(paths, document)
    study = tmp_path / 'study'
    assert init(paths, study, '--lang', language).exit_code == 0
    phrase = "n'est pas établie" if language == 'fr' else 'is not established'
    card = cli.run(['data', '--study', str(study)]).payload
    assert phrase in card['note']['junior_text']
    for args in (['plan'], ['status', '--summary']):
        payload = cli.run([*args, '--study', str(study)]).payload
        assert phrase in payload['next_action']['junior_digest']
    assert read.open(study).state['current'] == {}


def test_j0_a06_accessible_synthetic_source_does_not_change_assurance(tmp_path):
    paths = make_review(tmp_path)
    study = tmp_path / 'study'
    assert init(paths, study).exit_code == 0
    before = state_bytes(study)
    assert paths['data'].read_bytes()
    result = commands.status(study).payload['view']
    assert result['final_test']['status'] == 'sealed'
    assert result['assurance']['evaluation_protection'] == 'protocol_reserved'
    assert result['assurance']['consent_provenance'] == 'agent_reported'
    assert state_bytes(study) == before


def test_j0_a07_picker_confirmation_is_not_authenticated(tmp_path):
    paths = make_review(tmp_path)
    flow = fk.Flow(tmp_path / 'study', paths['case'].parent)
    flow.init()
    proposed = flow.call('decide', 'propose', 'prediction_time', '--value', 'Before contact',
                         '--restatement', 'Predict before contact', '--rationale', 'Exercise scope',
                         '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                         '--study', flow.study)
    pid = proposed['result']['proposal_id']
    adopted = flow.call('decide', 'confirm', pid, '--channel', 'choice',
                       '--user-words', "J'adopte cette décision", '--adoption-question',
                       '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                       '--study', flow.study)
    conf = flow.state()['decisions']['prediction_time']['confirmation']
    assert conf['channel'] == 'choice'
    assert conf['user_words'] == "J'adopte cette décision"
    assert conf['authenticated'] is False


def test_j0_a08_changed_contract_is_not_whitelisted_or_migrated(tmp_path):
    paths = make_review(tmp_path)
    study = tmp_path / 'study'
    assert init(paths, study).exit_code == 0
    before = state_bytes(study)
    document = yaml.safe_load(paths['case'].read_text())
    document['analysis_contract']['scenario_id'] = 'revised-scenario'
    write_case(paths, document)
    changes = read.open(study).source_changes()
    assert [x['label'] for x in changes] == ['case']
    status = commands.status(study).payload['view']
    assert any(x['id'] == 'sources_changed' for x in status['not_yet_defensible'])
    assert status['assurance']['analysis_contract_status'] == 'absent'
    assert state_bytes(study) == before
    out = init(paths, study, '--reliability-profile', 'review-v1')
    assert out.payload['error']['code'] == 'state_exists'
    assert state_bytes(study) == before


def test_j0_a09_generated_instructions_keep_quote_and_picker(tmp_path):
    paths = make_review(tmp_path)
    study = tmp_path / 'study'
    assert init(paths, study).exit_code == 0
    instructions = (study / '.github/copilot-instructions.md').read_text()
    agent = (study / '.github/agents/hypotrail.agent.md').read_text()
    assert 'The restatement as a quoted block' in instructions
    assert 'directly above the question' in instructions
    assert 'vscode/askQuestions' in agent and 'Without the picker, ask' in agent


def test_j0_state_rejects_bad_profile_and_unknown_settings(tmp_path):
    paths = make_review(tmp_path)
    state = st.initial_state(c.load_case(paths['case']))
    for key, value in [('reliability_profile', 'magic'), ('unknown_option', True)]:
        changed = copy.deepcopy(state)
        changed['settings'][key] = value
        assert any(x['path'] == f'settings.{key}' for x in st.validate_state(changed))


def test_j0_structural_quality_can_run_in_review_profile(tmp_path):
    paths = make_review(tmp_path)
    study = tmp_path / 'study'
    assert init(paths, study, '--reliability-profile', 'review-v1').exit_code == 0
    out = cli.run(['run', 'eda.quality', '--study', str(study),
                   '--request-id', 'quality', '--expected-revision', '1'])
    assert out.exit_code == 0, out.payload
    state = read.open(study).state
    assert 'eda.quality' in state['current']
    assert not any(slot.startswith('fit.') for slot in state['current'])
    assert state['partition']['status'] == 'sealed'
    assert all(d['status'] == 'open' for d in state['decisions'].values())


def test_j0_review_scenario_is_bound_without_changing_legacy_decisions(tmp_path):
    paths = make_review(tmp_path)
    study = tmp_path / 'study'
    assert init(paths, study, '--reliability-profile', 'review-v1').exit_code == 0
    s = read.open(study).state
    statement = c.load_case(paths['case']).document['analysis_contract']['prediction_statement']
    with pytest.raises(CommandRefused) as err:
        commands.validate_value(s, 'prediction_time', 'After seeing the outcome')
    assert err.value.code == 'invalid_value'
    assert err.value.details['reason'] == 'scenario_mismatch'
    commands.validate_value(s, 'prediction_time', statement.replace(' ', '  '))
    legacy = copy.deepcopy(s)
    del legacy['settings']['reliability_profile']
    commands.validate_value(legacy, 'prediction_time', 'Before contact')
    proposed = cli.run(['decide', 'propose', 'prediction_time', '--value', statement,
                        '--restatement', statement, '--rationale', 'Declared exercise scenario',
                        '--study', str(study), '--request-id', 'bound-scenario',
                        '--expected-revision', '1'])
    assert proposed.exit_code == 0, proposed.payload
    action = commands.status(study).payload['view']['next_action']
    assert action['default_value'] == statement
    assert action['recommended']['value'] == statement


def test_j0_clock_units_must_be_comparable(tmp_path):
    paths = make_review(tmp_path, future=True)
    document = yaml.safe_load(paths['case'].read_text())
    document['variables'][-2]['unit'] = 'days'
    document['variables'][-1]['unit'] = 'seconds'
    write_case(paths, document)
    with pytest.raises(c.CaseError) as err:
        c.load_case(paths['case'])
    assert any(p['path'] == 'analysis_contract.timing' for p in err.value.problems)
