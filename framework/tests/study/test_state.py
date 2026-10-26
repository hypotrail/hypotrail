"""Study state ``hypotrail.study/1``: schema, confirmation, integrity, and derived views.

The state is built from the synthetic case in ``tmp_path`` and from the committed
Bank and Auto MPG cases, which are only read.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from mlkit.study import case as c, state as st
from mlkit.study.errors import StudyError

TESTS = Path(__file__).resolve().parents[1]
FRAMEWORK = TESTS.parent
REPO = FRAMEWORK.parent
_spec = importlib.util.spec_from_file_location('synthetic_make_case_for_state',
                                               TESTS / 'fixtures/synthetic/make_case.py')
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
make_case = _module.make_case


@pytest.fixture(scope='module')
def synthetic_case(tmp_path_factory):
    return c.load_case(make_case(tmp_path_factory.mktemp('case'), n_rows=300)['case'])


@pytest.fixture
def state(synthetic_case):
    return st.initial_state(synthetic_case, created='2026-10-18T00:00:00+00:00')


def _proposal(state, decision_id, value, pid=None):
    pid = pid or f'p_{len(state["proposals"]) + 1}'
    proposal = {'proposal_id': pid, 'decision_id': decision_id, 'value': value,
                'restatement': f'You decide {decision_id}.', 'rationale': 'Test only.',
                'revision': state['revision'], 'status': 'open', 'created': st.now()}
    state['proposals'][pid] = proposal
    state['decisions'][decision_id].update(status='proposed', value=value, proposal_id=pid)
    return proposal


def _confirm(state, decision_id, value):
    proposal = _proposal(state, decision_id, value)
    proposal['status'] = 'confirmed'
    state['decisions'][decision_id].update(
        status='confirmed', confirmation=st.confirmation(
            user_words='Yes, that is what I mean.', proposal=proposal, channel='chat',
            actor='junior', revision=state['revision']))


def test_initial_state_is_valid_and_takes_no_decision(state, synthetic_case):
    assert st.validate_state(state) == []
    assert state['schema'] == 'hypotrail.study/1' and state['revision'] == 0
    assert all(d['status'] == 'open' and d['confirmation'] is None
               for d in state['decisions'].values())
    assert state['proposals'] == {} and state['receipts'] == {}
    assert state['dataset']['sha256'] == synthetic_case.dataset['sha256']
    assert state['dataset']['row_key'] == {'rule': 'source_line', 'format': 'L<line>'}
    assert state['case']['sha256'] == c.sha256_file(synthetic_case.path)
    assert {f['status'] for f in state['facts'].values()} <= set(c.EPISTEMIC_STATUSES)
    # WP-A4: the policy rests on the preprocessing too (its models are fitted with it);
    # WP-B1: and on the variant it compares.
    assert state['decisions']['policy']['depends_on'] == ['prediction_time',
                                                           'feature_availability', 'split',
                                                           'preprocessing', 'model_variant',
                                                           'model_choice']
    assert state['decisions']['model_choice']['status'] == 'open'
    assert st.depends_on(_a4(state), 'policy') == (
        'prediction_time', 'feature_availability', 'split', 'preprocessing')


def _a4(state):
    import flowkit
    return flowkit.wp_a4_shape(copy.deepcopy(state))


def test_bank_initial_state_carries_prior_exposure():
    bank = st.initial_state(c.load_case(REPO / 'use-cases/bank-marketing'))
    assert st.validate_state(bank) == []
    assert bank['dataset']['rows'] == 4521
    assert len(bank['prior_exposure']) == 2
    assert 'public_data_already_explored' in {x['id'] for x in st.not_yet_defensible(bank)}


def test_auto_mpg_initial_state_is_a_regression_study():
    """M3: the regression study has the same pauses, with model_choice as its third
    decision; no policy decision exists, and the missing grouped split is listed."""
    auto = st.initial_state(c.load_case(REPO / 'use-cases/auto-mpg'))
    assert st.validate_state(auto) == []
    assert auto['task'] == 'regression' and st.task_of(auto) == 'regression'
    # WP-A4: a new study also fixes the success criterion and the preprocessing before
    # the models (st.REGRESSION_DECISION_IDS stays the set of a study created before);
    # WP-B1: it names a variant before the choice and may open the final test after it
    # (st.FULL_REGRESSION_DECISION_IDS stays the set of a study created before WP-B1).
    assert tuple(auto['decisions']) == st.B1_REGRESSION_DECISION_IDS == (
        'prediction_time', 'feature_availability', 'split', 'success_criterion',
        'preprocessing', 'model_variant', 'model_choice', 'final_test', 'conclusion')
    assert st.FULL_REGRESSION_DECISION_IDS == (
        'prediction_time', 'feature_availability', 'split', 'success_criterion',
        'preprocessing', 'model_choice', 'conclusion')
    assert st.REGRESSION_DECISION_IDS == (
        'prediction_time', 'feature_availability', 'split', 'model_choice', 'conclusion')
    assert auto['decisions']['conclusion']['depends_on'] == [
        'prediction_time', 'feature_availability', 'split', 'success_criterion',
        'preprocessing', 'model_variant', 'model_choice', 'final_test']
    assert _a4(auto)['decisions']['conclusion']['depends_on'] == [
        'prediction_time', 'feature_availability', 'split', 'success_criterion',
        'preprocessing', 'model_choice']
    assert [s['id'] for s in st.derive_plan(auto)] == list(st.B1_REGRESSION_STEP_IDS) == [
        'discover_data', 'prediction_time', 'feature_availability', 'split', 'success_criterion',
        'train_eda', 'preprocessing', 'models', 'model_variant', 'model_choice', 'final_test',
        'conclusion']
    assert [s['id'] for s in st.derive_plan(_a4(auto))] == list(
        st.FULL_REGRESSION_STEP_IDS) == [
        'discover_data', 'prediction_time', 'feature_availability', 'split', 'success_criterion',
        'train_eda', 'preprocessing', 'models', 'model_choice', 'conclusion']
    items = {x['id']: x for x in st.not_yet_defensible(auto)}
    assert items['grouped_split_unsupported']['column'] == 'car_name'
    assert items['grouped_split_unsupported']['capability'] == c.CAPABILITY_GROUPED_SPLIT
    assert 'no_time_or_entity_identifier' not in items
    broken = copy.deepcopy(auto)
    broken['decisions']['policy'] = broken['decisions'].pop('model_choice')
    assert {'path': 'decisions.model_choice', 'problem': 'is required'} in st.validate_state(broken)
    legacy = copy.deepcopy(auto)
    legacy.pop('task')          # a state without task is a binary study
    assert st.task_of(legacy) == 'binary' and st.validate_state(legacy)



@pytest.mark.parametrize('mutate, path', [
    (lambda s: s.update(schema='hypotrail.study/0'), 'schema'),
    (lambda s: s.pop('receipts'), 'receipts'),
    (lambda s: s.update(extra=1), 'extra'),
    (lambda s: s.update(revision=-1), 'revision'),
    (lambda s: s['facts'].update(x={'value': 1, 'status': 'confirmed', 'source': 's'}),
     'facts.x.status'),
    (lambda s: s['decisions']['split'].update(status='accepted'), 'decisions.split.status'),
    (lambda s: s['decisions']['split'].update(depends_on=['policy']),
     'decisions.split.depends_on'),
    (lambda s: s['decisions']['split'].update(value='70/30'), 'decisions.split'),
    (lambda s: s['decisions']['split'].update(status='confirmed', proposal_id=None),
     'decisions.split.confirmation'),
    (lambda s: s['decisions']['split'].update(proposal_id='p_9'), 'decisions.split.proposal_id'),
    (lambda s: s['decisions']['policy'].update(status='reconfirm_required'),
     'decisions.policy.reason'),
    (lambda s: s['decisions']['feature_availability'].update(
        status='proposed', value={'desk_followups': 'excluded'}),
     'decisions.feature_availability.value'),
    (lambda s: s['current'].update(split=''), 'current.split'),
    (lambda s: s['executions'].pop('late'), 'executions.late'),
])
def test_schema_problems_are_reported(state, mutate, path):
    mutate(state)
    problems = st.validate_state(state)
    assert path in {p['path'] for p in problems}, problems
    with pytest.raises(StudyError) as info:
        st.check_state(state)
    assert info.value.code == 'invalid_state'


def test_confirmation_records_channel_actor_and_is_not_authenticated(state):
    _confirm(state, 'prediction_time', 'before the first reminder')
    assert st.validate_state(state) == []
    record = state['decisions']['prediction_time']['confirmation']
    # ADR 0005 adds ``agent_concern`` (null when the agent raised nothing).
    assert set(record) == set(st.CONFIRMATION_KEYS) | {'basis', 'delegation_scope',
                                                       'agent_concern'}
    assert record['basis'] == 'explicit' and record['delegation_scope'] is None
    assert record['agent_concern'] is None
    assert record['authenticated'] is False and record['channel'] == 'chat'
    assert record['user_words'] == 'Yes, that is what I mean.'
    assert record['restatement'] == state['proposals']['p_1']['restatement']


@pytest.mark.parametrize('field, value', [('user_words', ''), ('user_words', '   '),
                                          ('channel', 'email'), ('actor', '')])
def test_incomplete_confirmation_is_refused(state, field, value):
    proposal = _proposal(state, 'split', '70/30 stratified')
    kwargs = dict(user_words='Yes, split 70/30.', proposal=proposal, channel='cli',
                  actor='junior', revision=1)
    kwargs[field] = value
    with pytest.raises(StudyError) as info:
        st.confirmation(**kwargs)
    assert info.value.code == 'invalid_confirmation'


def test_a_confirmation_claiming_authentication_is_invalid(state):
    _confirm(state, 'prediction_time', 'v')
    state['decisions']['prediction_time']['confirmation']['authenticated'] = True
    assert 'decisions.prediction_time.confirmation.authenticated' in {
        p['path'] for p in st.validate_state(state)}


def test_serialisation_is_canonical_and_integrity_is_checked(state):
    data = st.dumps(state)
    assert data == st.dumps(json.loads(data)) and data.endswith(b'\n')
    sha = st.digest(data)
    st.verify_integrity(data, st.sha_line(sha))
    assert st.parse_sha_line(st.sha_line(sha)) == sha
    with pytest.raises(StudyError) as info:
        st.verify_integrity(data + b' ', st.sha_line(sha))
    assert info.value.code == 'integrity_error'
    with pytest.raises(StudyError):
        st.verify_integrity(data, None)
    st.verify_integrity(data, st.sha_line('0' * 64), pending_sha256=sha)
    assert st.loads(data) == state


def _kinds(state):
    return [s['status'] for s in st.derive_plan(state)]


def test_plan_and_next_action_follow_the_three_pauses(state):
    """The plan of a study created by WP-A4 (v0.2a; a new study since WP-B1 has two more
    decisions, tested below): step 0, then the three pauses, the success criterion and the
    preprocessing at the split pause, before the models."""
    state = _a4(state)
    plan = st.derive_plan(state)
    assert [s['id'] for s in plan] == list(st.FULL_STEP_IDS)
    assert [s['pause'] for s in plan] == [None, 1, 1, 2, 2, None, 2, None, 3, 3]
    assert _kinds(state) == ['ready', 'ready'] + ['blocked'] * 8
    assert [s['current'] for s in plan] == [True] + [False] * 9
    assert st.next_action(state)['kind'] == 'show_data_card'

    _proposal(state, 'prediction_time', 'before the first reminder')
    assert _kinds(state)[:2] == ['done', 'awaiting_confirmation']
    action = st.next_action(state)
    assert action == {**action, 'kind': 'await_user_words', 'proposal_id': 'p_1'}

    state['proposals']['p_1']['status'] = 'withdrawn'
    state['decisions']['prediction_time'] = st.empty_decision('prediction_time')
    assert st.next_action(state)['decision'] == 'prediction_time'   # step 0 stays done
    _confirm(state, 'prediction_time', 'before the first reminder')
    _confirm(state, 'feature_availability', {'holds_open': 'available_at_prediction',
                                             'desk_followups': 'not_available',
                                             'reminders_sent': 'uncertain_included'})
    _confirm(state, 'split', 'stratified 70/30, seed 20261017')
    assert st.next_action(state) == {**st.next_action(state), 'kind': 'run', 'activity': 'split'}
    state['current']['split'] = 'r_split'
    assert _kinds(state)[:5] == ['done', 'done', 'done', 'done', 'ready']
    assert st.next_action(state) == {**st.next_action(state), 'kind': 'propose',
                                     'decision': 'success_criterion'}
    _confirm(state, 'success_criterion', {'metric': 'precision_gain', 'min_points': 5})
    assert st.next_action(state)['activity'] == 'eda.target_rate'
    for slot in ('eda.target_rate', 'eda.special_values'):
        state['current'][slot] = f'r_{slot}'
    action = st.next_action(state)
    assert action == {**action, 'kind': 'propose', 'decision': 'preprocessing'}
    assert action['default_value'] == {'missing': 'none', 'rare_category_min_rows': 0,
                                       'caps': {}, 'log_transform': []}
    assert _kinds(state)[7] == 'blocked'                  # the models wait for it
    _confirm(state, 'preprocessing', action['default_value'])
    for slot in ('fit.baseline', 'fit.logistic'):
        state['current'][slot] = f'r_{slot}'
    # A policy is evaluated before it is proposed.
    assert st.next_action(state) == {**st.next_action(state), 'kind': 'run',
                                     'activity': 'policy.evaluation'}
    state['current']['policy.evaluation'] = 'r_policy'
    assert st.next_action(state) == {**st.next_action(state), 'kind': 'propose',
                                     'decision': 'policy'}
    _confirm(state, 'policy', 'capacity:100')
    _confirm(state, 'conclusion', 'keep_baseline')
    assert _kinds(state) == ['done'] * 10
    assert st.next_action(state)['kind'] == 'done'
    assert st.validate_state(state) == []

    state['stale']['r_policy'] = {'reason': 'split changed', 'since': 9}
    assert _kinds(state)[8] == 'ready' and st.next_action(state)['activity'] == 'policy.evaluation'
    state['decisions']['policy'].update(status='reconfirm_required', reason='split changed')
    # Review round 4 (E4-3): its confirmation needs a current evaluation, so that runs first
    # (confirming it now would be refused), then the policy is asked again.
    assert st.next_action(state) == {**st.next_action(state), 'kind': 'run',
                                     'activity': 'policy.evaluation', 'reconfirm': 'policy'}
    del state['stale']['r_policy']
    assert st.next_action(state) == {**st.next_action(state), 'kind': 'reconfirm',
                                     'decision': 'policy', 'default_value': 'capacity:100'}
    state['stale']['r_policy'] = {'reason': 'split changed', 'since': 9}
    state['executions']['interrupted']['e1'] = {'status': 'interrupted_unknown'}
    assert st.next_action(state) == {**st.next_action(state), 'kind': 'acknowledge_interruption',
                                     'execution_id': 'e1'}


def test_the_plan_of_a_new_study_names_a_variant_and_may_open_the_final_test(state):
    """WP-B1: after the models, the variant (its fit is the step's activity), then the choice,
    then the opening of the final test, optional: a blocked opening never hides the
    conclusion, and once the choice is confirmed the engine drafts the opening."""
    plan = st.derive_plan(state)
    assert [s['id'] for s in plan] == list(st.B2_BINARY_STEP_IDS)
    by_id = {s['id']: s for s in plan}
    assert by_id['model_variant']['activities'] == ['fit.variant']
    assert by_id['model_variant']['requires'] == ['models']
    assert by_id['model_choice']['requires'] == ['model_variant', 'models']
    assert by_id['policy']['requires'] == ['models', 'model_variant', 'model_choice']
    assert by_id['final_test']['requires'] == ['model_choice', 'policy']
    assert by_id['final_test']['activities'] == ['final_test.evaluation']
    assert [s['pause'] for s in plan] == [None, 1, 1, 2, 2, None, 2, None, 3, 3, 3, 3, 3]
    _confirm(state, 'prediction_time', 'before the first reminder')
    _confirm(state, 'feature_availability', {'holds_open': 'available_at_prediction'})
    action = st.next_action(state)
    assert action['decision'] == 'split' and action['default_value'] == {
        'method': 'kfold_stratified', 'folds': 5, 'seed': st.DEFAULT_CV_SEED}
    _confirm(state, 'split', action['default_value'])
    _confirm(state, 'success_criterion', {'metric': 'precision_gain', 'min_points': 5})
    _confirm(state, 'preprocessing', {'missing': 'none', 'rare_category_min_rows': 0,
                                      'caps': {}, 'log_transform': []})
    for slot in ('split', 'eda.target_rate', 'eda.special_values', 'fit.baseline',
                 'fit.logistic'):
        state['current'][slot] = f'r_{slot}'
    # v0.3 (WP-F1, R28): the diagnostics of the first linear fit come before the variants.
    assert st.next_action(state) == {**st.next_action(state), 'kind': 'run',
                                     'activity': 'diag.binary'}
    state['current']['diag.binary'] = 'r_diag'
    action = st.next_action(state)
    # v0.3 (WP-F1): the drafted variant is the penalty tuned by nested cross-validation,
    # declared with its question.
    assert action == {**action, 'kind': 'propose', 'decision': 'model_variant',
                      'default_value': {'variants': [{
                          'kind': 'tuned', 'question': 'Does a penalty chosen by nested '
                                                       'cross-validation rank the rows better '
                                                       'than the default penalty?'}]}}
    _confirm(state, 'model_variant', action['default_value'])
    assert st.next_action(state)['activity'] == 'fit.variant'
    state['current']['fit.variant'] = 'r_variant'
    state['current']['policy.evaluation'] = 'r_policy'
    assert st.next_action(state)['decision'] == 'model_choice'
    _confirm(state, 'model_choice', 'fit.variant')
    assert st.next_action(state)['decision'] == 'policy'
    # Before the choice, the opening is blocked and skipped: the conclusion comes next.
    _confirm(state, 'conclusion', {'verdict': 'keep_baseline', 'text': 'Keep it.'})
    assert st.next_action(state)['decision'] == 'policy'
    state['decisions']['conclusion'] = st.empty_decision('conclusion')
    _confirm(state, 'policy', 'capacity:100@fit.variant')
    action = st.next_action(state)
    assert action == {**action, 'kind': 'propose', 'decision': 'final_test',
                      'default_value': {'model': 'fit.variant', 'rule': 'capacity:100'}}
    assert st.validate_state(state) == []
    without = copy.deepcopy(state)
    without['decisions']['policy'] = st.empty_decision('policy')
    without['decisions']['policy']['depends_on'] = list(st.depends_on(without, 'policy'))
    assert st.next_action(without)['decision'] == 'policy'
    _confirm(without, 'conclusion', {'verdict': 'keep_baseline', 'text': 'Keep it.'})
    plan = {s['id']: s['status'] for s in st.derive_plan(without)}
    assert plan['final_test'] == 'blocked'


def test_a_state_written_before_wp_a4_keeps_its_plan(state):
    """A study created before WP-A4 holds the five v0.1 decisions: it stays valid, its plan
    is step 0 then the v0.1 steps, and its models need the split only."""
    for d in st.WP_A4_DECISIONS + st.WP_B1_DECISIONS:
        del state['decisions'][d]
    state['decisions'].pop('model_choice', None)
    for d, dec in state['decisions'].items():
        dec['depends_on'] = list(st.DEPENDS_ON[d])
    assert st.validate_state(state) == []
    assert st.decision_ids(state) == st.DECISION_IDS
    plan = st.derive_plan(state)
    assert [s['id'] for s in plan] == ['discover_data', *st.STEP_IDS]
    assert [s['pause'] for s in plan] == [None, 1, 1, 2, None, None, 3, 3]
    assert next(s for s in plan if s['id'] == 'models')['requires'] == ['split']
    half = copy.deepcopy(state)
    half['decisions']['preprocessing'] = st.empty_decision('preprocessing')
    assert {p['path'] for p in st.validate_state(half)} == {'decisions.preprocessing'}


def test_not_yet_defensible_reflects_state(state):
    ids = [x['id'] for x in st.not_yet_defensible(state)]
    assert ids[0] == 'unconfirmed_decisions'
    assert {'validation_is_not_independent', 'no_time_or_entity_identifier', 'no_causality',
            'workbench_not_tracked'} <= set(ids)
    assert 'uncertain_features_included' not in ids
    _confirm(state, 'feature_availability', {'reminders_sent': 'uncertain_included',
                                             'holds_open': 'available_at_prediction'})
    state['stale']['r1'] = {'reason': 'x', 'since': 2}
    items = {x['id']: x for x in st.not_yet_defensible(state)}
    assert items['uncertain_features_included']['features'] == ['reminders_sent']
    assert items['stale_results']['results'] == ['r1']
    assert 'feature_availability' not in items['unconfirmed_decisions']['decisions']


def _structure(state, time=None, group=None, order=None):
    """The state with a time column, a group column and a sealed final test that follows
    ``order`` (a temporal partition) or not (a stratified one)."""
    out = copy.deepcopy(state)
    out['structure']['time_column']['value'] = time
    out['structure']['group_column']['value'] = group
    out['partition'] = ({'method': 'temporal', 'order': {'by': order, 'direction': 'ascending'}}
                        if order else {'method': 'stratified', 'order': None})
    return out


def _structure_item(state):
    return next((x for x in st.not_yet_defensible(state)
                 if x['id'] == 'no_time_or_entity_identifier'), None)


@pytest.mark.parametrize('time, group, order, missing', [
    (None, None, None, ['time_column', 'group_column']),     # nothing declared
    (None, None, 'line', ['group_column']),                  # Hotel: an order, no entity
    (None, None, 'arrival', ['group_column']),               # an order column
    ('model_year', None, None, ['group_column']),            # a time column, no entity
    (None, 'car_name', None, ['time_column']),               # an entity, no time
    (None, 'car_name', 'line', None),                        # an order and an entity
    ('model_year', 'car_name', None, None),                  # both declared
])
def test_the_structure_limit_names_only_what_is_missing(state, time, group, order, missing):
    """L7 (R17, J-LIMIT): a declared order (a temporal final test) is a time order; the
    limit names only what is missing, in English and in French, and says what a temporal
    final test can show."""
    from mlkit.study import junior
    item = _structure_item(_structure(state, time, group, order))
    if missing is None:
        assert item is None
        return
    assert item['missing'] == missing
    english, french = item['text'], junior.limit_fr(item)
    # The report quotes them: no causal or forecast wording for `check` to flag.
    from mlkit.study import cmd_check
    assert cmd_check.wording(english, 'limit') == [] and cmd_check.wording(french, 'limit') == []
    if 'time_column' in missing:
        assert 'time column' in english and 'drift over time' in english
        assert 'colonne de temps' in french and 'dérive' in french
    else:
        assert 'time column' not in english and 'drift' not in english
        assert 'colonne de temps' not in french and 'dérive' not in french
    if 'group_column' in missing:
        assert 'entity identifier' in english and "identifiant d'entité" in french
    else:
        assert 'entity' not in english and 'entité' not in french
    if order:
        assert item['ordered_by'] == order
        words = ("the order of the file's lines" if order == 'line' else f'the column {order}')
        assert (f'The rows follow a declared order ({words})' in english
                and 'a shift between the development period and the final period, not its '
                    'cause.' in english)
        assert 'Les lignes suivent un ordre déclaré' in french and "sans en expliquer l'origine" in french
    else:
        assert 'ordered_by' not in item and 'declared order (' not in english
        assert 'ordre déclaré (' not in french


def test_the_hotel_like_structure_limit_has_no_time_part(state):
    """R17 as the owner saw it: no time column, ``order: {by: line}``, a temporal final
    test; the closing limits never say "ni colonne de temps"."""
    from mlkit.study import junior
    item = _structure_item(_structure(state, order='line'))
    assert item['missing'] == ['group_column']
    assert item['text'].startswith('The data have no entity identifier, so the study cannot '
                                   'check whether the same entity appears in several '
                                   'partitions.')
    assert junior.limit_fr(item).startswith(
        "Les données n'ont pas d'identifiant d'entité : l'étude ne peut pas vérifier qu'une "
        'même entité apparaît dans plusieurs échantillons.')
    assert 'ni colonne de temps' not in junior.limit_fr(item)
    # The cross-validation follows the same rule (folds follow time).
    assert st.cv_method(_structure(state, order='line')) == 'temporal_folds'


def test_a_legacy_study_without_partition_keeps_both_missing(state):
    legacy = copy.deepcopy(state)
    legacy.pop('partition', None)
    legacy['structure']['time_column']['value'] = None
    legacy['structure']['group_column']['value'] = None
    item = _structure_item(legacy)
    assert item['missing'] == ['time_column', 'group_column'] and 'ordered_by' not in item
    assert item['text'] == ('The data have no time column or entity identifier, so the study '
                            'cannot check drift over time or repeated entities across '
                            'partitions.')


def test_derived_views_do_not_mutate_state(state):
    before = copy.deepcopy(state)
    st.derive_plan(state), st.next_action(state), st.not_yet_defensible(state)
    assert state == before


def test_state_and_store_import_no_heavy_library():
    """Plan §9 bis latency: status-side modules load no pandas, numpy, or scikit-learn.

    The import time is recorded in the test output (``-s`` or the captured stdout of a
    failure); there is no threshold.
    """
    code = ('import json, sys, time\n'
            't = time.perf_counter()\n'
            'import mlkit.study.state, mlkit.study.store, mlkit.study.lock\n'
            'elapsed = time.perf_counter() - t\n'
            'heavy = sorted(m for m in sys.modules if m.split(".")[0] in '
            '{"pandas", "numpy", "sklearn", "scipy"})\n'
            'print(json.dumps({"seconds": elapsed, "heavy": heavy}))\n')
    env = {**os.environ, 'PYTHONPATH': str(FRAMEWORK)}
    proc = subprocess.run([sys.executable, '-c', code], capture_output=True,
                          text=True, env=env, cwd=FRAMEWORK, timeout=60)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout.strip().splitlines()[-1])
    print(f'\nimport mlkit.study.state, store, lock: {result["seconds"] * 1000:.1f} ms')
    assert result['heavy'] == []
