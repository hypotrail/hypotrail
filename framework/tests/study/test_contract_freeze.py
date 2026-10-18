# Contract tests: Phase 2/3 agents must not modify; change only via integrator.
"""Frozen CLI and study contract (``docs/specs/CLI-CONTRACT.md``, plan §8, §9 bis).

These tests pin schema ids, payload keys, view-model keys, exit codes, error codes,
action names, the §3.7 table ids, storage keys, and the signatures of the extension
points. A deliberate change bumps the schema version and updates the document and
this file in the same commit, through the integrator.
"""
from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest

from mlkit import reliability
from mlkit.study import (cli, commands as cmd, dependencies as dep, exposure, preconditions as pre,
                         read, records as rec, registry, state as st, view)

FRAMEWORK = Path(__file__).resolve().parents[2]
REPO = FRAMEWORK.parent
STUDY_PKG = FRAMEWORK / 'mlkit' / 'study'
DOC = (REPO / 'docs' / 'specs' / 'CLI-CONTRACT.md').read_text(encoding='utf-8')
DOC_TOKENS = {t.rstrip('.') for t in re.findall(r'[A-Za-z_][\w./]*', DOC)}

SCHEMAS = {'init': 'hypotrail.init/1', 'status': 'hypotrail.status/1', 'plan': 'hypotrail.plan/1',
           'decide': 'hypotrail.decide/1', 'error': 'hypotrail.error/1'}
# Post-acceptance contract (D3): ``status --summary``.
SUMMARY_SCHEMA = 'hypotrail.summary/1'
SUMMARY_PAYLOAD_KEYS = ('schema', 'ok', 'study', 'revision', 'since', 'changed', 'goal',
                        'current_step', 'plan', 'next_action', 'open_proposals', 'decisions',
                        'results', 'artifacts', 'executions', 'not_yet_defensible',
                        # Post-v0.1 (P2): the junior's conditions and holds, verbatim.
                        'notes',
                        # Post-v0.1 fixes (D5): the open holds grouped by decision.
                        'holds',
                        # Post-v0.1 (T8, F5): five resume lines generated from state.
                        'recap')
SUMMARY_NOTE_KEYS = ('note_id', 'decision_id', 'status', 'user_words', 'resolution_words')
SUMMARY_HOLD_KEYS = ('decision_id', 'status', 'notes')
# Post-v0.1 fixes (D5): a hold may be withdrawn in the junior's words.
NOTE_STATUSES = ('open', 'resolved', 'withdrawn')
# Post-v0.1 (P2): a junior's condition or hold on a decision.
NOTE_VIEW_KEYS = ('note_id', 'decision_id', 'kind', 'user_words', 'status', 'revision',
                  'resolution')
NOTE_STATE_KEYS = ('note_id', 'decision_id', 'kind', 'user_words', 'status', 'created',
                   'revision', 'request_id', 'resolution')
NOTE_RESOLUTION_KEYS = ('user_words', 'revision', 'time', 'request_id')
RECAP_LABELS = ('Goal', 'Decided', 'Now', 'Next', 'Limit')
# ``preview policy`` (Phase 2), with ``warnings`` added by the post-v0.1 fixes (D4).
PREVIEW_PAYLOAD_KEYS = ('schema', 'ok', 'study', 'revision', 'kind', 'rules', 'models',
                        'evaluations', 'intervals', 'adopted', 'recorded', 'note', 'warnings')
SUMMARY_DECISION_KEYS = ('status', 'value', 'basis', 'delegation_scope', 'user_words', 'reason',
                         'open_proposals')
SUMMARY_GOAL_KEYS = ('intended_use', 'decision', 'observation_unit', 'prediction_time')
EXIT_CODES = {'EXIT_OK': 0, 'EXIT_INTERNAL': 1, 'EXIT_REFUSED': 2, 'EXIT_ARTIFACT_STALE': 3,
              'EXIT_UNKNOWN_OUTCOME': 4}
PAYLOAD_KEYS = {
    'init': ('schema', 'ok', 'study', 'revision', 'case', 'dataset', 'structural_exposure', 'plan',
             'next_action', 'agent_instructions', 'ignored_sources', 'note'),
    'status': ('schema', 'ok', 'study', 'revision', 'since', 'changed', 'changes_since', 'view'),
    'plan': ('schema', 'ok', 'study', 'revision', 'steps', 'current_step', 'next_action'),
    'decide': ('schema', 'ok', 'study', 'action', 'request_id', 'replayed', 'revision', 'result',
               'artifacts'),
    'error': ('schema', 'ok', 'command', 'error'),
}
RESULT_KEYS_BY_ACTION = {
    'decide.propose': ('proposal_id', 'decision_id', 'status', 'decision_status', 'superseded',
                       'restatement'),
    'decide.confirm': ('decision_id', 'proposal_id', 'status', 'value', 'user_words', 'channel',
                       'actor', 'invalidation', 'basis', 'delegation_scope'),
    'decide.withdraw': ('proposal_id', 'decision_id', 'status', 'decision_status'),
    # Post-v0.1 (P2).
    # Post-v0.1 fixes (D1): the decisions a hold on a confirmed decision asks for again.
    'decide.note': ('note_id', 'decision_id', 'status', 'user_words', 'open_holds',
                    'reconfirm_required'),
    'decide.resolve_note': ('note_id', 'decision_id', 'status', 'user_words', 'open_holds'),
    # Post-v0.1 fixes (D5).
    'decide.withdraw_note': ('note_id', 'decision_id', 'status', 'user_words', 'open_holds'),
}
ACTION_PARAMS = {'decide.propose': {'decision_id', 'value', 'restatement', 'rationale'},
                 'decide.confirm': {'proposal_id', 'user_words', 'channel', 'actor', 'basis',
                                    'delegation_scope'},
                 'decide.withdraw': {'proposal_id', 'reason'},
                 'decide.note': {'decision_id', 'user_words'},
                 'decide.resolve_note': {'note_id', 'user_words'},
                 'decide.withdraw_note': {'note_id', 'user_words'}}
VIEW_KEYS = ('schema', 'study', 'revision', 'updated', 'case', 'dataset', 'plan', 'current_step',
             'next_action', 'open_proposals', 'decisions', 'facts', 'structure', 'results',
             'stale', 'invalidations', 'executions', 'artifacts', 'exposure',
             'not_yet_defensible', 'settings',
             # M3 (regression): the task of the study, ``binary`` or ``regression``.
             'task',
             # Post-v0.1 (P2): the junior's conditions and holds.
             'notes')
DECISION_VIEW_KEYS = ('decision_id', 'status', 'value', 'proposal_id', 'depends_on', 'revision',
                      'reason', 'confirmation', 'open_proposals')
CONFIRMATION_VIEW_KEYS = ('user_words', 'channel', 'actor', 'restatement', 'proposal_id',
                          'revision', 'time', 'authenticated', 'basis', 'delegation_scope')
# Post-acceptance contract (D1): how the user decided.
CONFIRMATION_BASES = ('explicit', 'delegated_default')
# Acceptance rerun (R1): the scope of a delegation. A standing delegation never covers the
# policy or the conclusion.
DELEGATION_SCOPES = ('this_decision', 'standing')
STANDING_DELEGATION_DECISIONS = ('prediction_time', 'feature_availability', 'split')
PROPOSAL_VIEW_KEYS = ('proposal_id', 'decision_id', 'value', 'restatement', 'rationale',
                      'revision', 'created')
RESULT_VIEW_KEYS = ('slot', 'result_id', 'activity', 'current', 'stale_reason', 'partition',
                    'n_rows', 'values', 'blobs', 'params', 'inputs', 'code_fingerprint',
                    'environment', 'execution_id', 'exposure_id', 'started_revision', 'integrity')
EXPOSURE_SUMMARY_KEYS = ('records', 'rows_exposed', 'by_purpose', 'by_partition',
                         'validation_rows_used_for_selection', 'prior_exposure')
ARTIFACT_VIEW_KEYS = ('manifest', 'status', 'items')
STEP_KEYS = ('id', 'title', 'question', 'expected_output', 'completion', 'pause', 'decision',
             'activities', 'decide_first', 'missing_results', 'requires', 'status', 'current')
STEP_IDS = ('prediction_time', 'feature_availability', 'split', 'train_eda', 'models', 'policy',
            'conclusion')
# M3 (regression): the same pauses; the third decision is model_choice.
TASKS = ('binary', 'regression')
REGRESSION_DECISION_IDS = ('prediction_time', 'feature_availability', 'split', 'model_choice',
                           'conclusion')
REGRESSION_STEP_IDS = ('prediction_time', 'feature_availability', 'split', 'train_eda', 'models',
                       'model_choice', 'conclusion')
REGRESSION_ACTIVITY_SLOTS = ('split', 'eda.target_summary', 'eda.special_values', 'fit.baseline',
                             'fit.linear', 'evaluate.regression')
REGRESSION_CONCLUSION_VERDICTS = ('adopt_model', 'keep_baseline', 'inconclusive')
MODEL_CHOICES = ('fit.linear', 'fit.baseline')
SPLIT_METHODS = ('stratified_random', 'random', 'ordinal_cutoff')
REGRESSION_MUTATION_IDS = {1: 'prediction_time', 2: 'feature_availability.feature_set',
                           3: 'feature_availability.wording', 4: 'split', 7: 'settings.bootstrap',
                           8: 'usage_label', 9: 'eda_added', 10: 'conclusion',
                           11: 'code_fingerprint', 12: 'dataset', 13: 'model_choice',
                           '*': 'unknown'}
NEXT_ACTION_KINDS = {'acknowledge_interruption', 'reconfirm', 'await_user_words', 'blocked',
                     'propose', 'run', 'done',
                     # Closure fix F1: a dead execution seen by the read-only lease probe.
                     'outcome_unknown'}
EXECUTION_VIEW_KEYS = ('active', 'interrupted', 'late', 'suspected_interrupted')
LIVENESS_VALUES = ('running', 'outcome_unknown', 'not_checked')
NOT_YET_DEFENSIBLE_IDS = {'unconfirmed_decisions', 'validation_is_not_independent',
                          'public_data_already_explored', 'no_time_or_entity_identifier',
                          'uncertain_features_included', 'stale_results',
                          'interrupted_executions', 'no_causality', 'workbench_not_tracked',
                          'result_integrity',
                          # Post-acceptance contract (D1, adopted rule).
                          'delegated_decisions', 'adopted_rule_not_evaluated',
                          # Review fix H2 (plan §3.7 row 11, detected by the view).
                          'code_changed',
                          # Review fix L1 (plan §3.7 row 12, flagged by the view).
                          'sources_changed',
                          # M3: a declared group column without a grouped split.
                          'grouped_split_unsupported',
                          # Post-v0.1 (P2): a condition of the junior not resolved yet.
                          'open_holds',
                          # G.12: small-data warnings (never refusals).
                          'small_validation_partition', 'capacity_exceeds_validation',
                          'high_cardinality_grouping',
                          # Post-v0.1 fixes: the conclusion outdated by a later change (D2),
                          # an inconclusive conclusion without a choice (D6).
                          'conclusion_outdated', 'inconclusive_without_choice'}
INVALIDATION_KEYS = ('revision', 'decision_id', 'mutation', 'row', 'reason', 'stale_results',
                     'stale_slots', 'reconfirm_required', 'effects', 'previous')
CONFIRM_INVALIDATION_KEYS = ('mutation', 'row', 'reason', 'stale_results', 'stale_slots',
                             'reconfirm_required')
EFFECT_KEYS = ('refit', 're_eda', 're_policy', 're_chart', 're_explain', 'reconfirm')
MUTATION_IDS = {1: 'prediction_time', 2: 'feature_availability.feature_set',
                3: 'feature_availability.wording', 4: 'split', 5: 'policy.parameter',
                6: 'policy.rule_type', 7: 'settings.bootstrap', 8: 'usage_label', 9: 'eda_added',
                10: 'conclusion', 11: 'code_fingerprint', 12: 'dataset', '*': 'unknown'}
ERROR_CODES = {
    'invalid_arguments', 'internal_error', 'invalid_request', 'idempotency_conflict',
    'stale_revision', 'invalid_command', 'study_missing', 'state_exists', 'integrity_error',
    'study_busy', 'platform_unsupported', 'invalid_case', 'confirmed_status_forbidden',
    'dataset_missing', 'dataset_changed', 'unsupported_capability', 'unknown_decision',
    'invalid_value', 'literal_number_in_text', 'ambiguous_confirmation', 'precondition_missing',
    'unknown_proposal', 'proposal_not_open', 'unknown_result', 'invalid_result', 'unknown_module',
    'invalid_exposure', 'no_predictions', 'invalid_state', 'invalid_confirmation',
    'lease_exists', 'lease_held',
    # Phase 2 contract commit: reserved codes now emitted, plus read_only.
    'interrupted_execution_pending', 'unknown_execution', 'read_only',
    # Phase 3 (WP3.1-WP3.4); its read_only_process was merged into read_only in Phase 4.
    'untraceable_number',
    # Review fix M1: causal or forecast wording in a proposed conclusion.
    'causal_or_forecast_wording',
    # Review fix L7: a concurrent duplicate run.
    'execution_in_progress',
    # Post-v0.1 (P2): holds; (P7) a default credited to the analyst.
    'decision_on_hold', 'unknown_note', 'note_not_open', 'misattributed_delegation'}
RESERVED_CODES: set[str] = set()
AMBIGUOUS_REASONS = {'missing_user_words', 'bare_acknowledgement', 'proposal_not_found',
                     'proposal_withdrawn', 'proposal_superseded', 'proposal_confirmed',
                     'same_request', 'proposal_stale',
                     # Post-acceptance contract (D1): delegated confirmations.
                     'not_a_delegation', 'delegation_needs_basis', 'restatement_not_default',
                     # Review fix H1: refusals and replies unrelated to the proposal.
                     'negative_reply', 'unrelated_reply',
                     # Acceptance rerun (R1): policy and conclusion need a delegation given
                     # at that pause.
                     'delegation_not_given_at_this_pause'}
REGISTRY_ENTRY_KEYS = ('schema', 'result_id', 'input_key', 'activity', 'params', 'inputs', 'code',
                       'output', 'blobs', 'partition', 'n_rows', 'exposure_id', 'execution_id',
                       'started_revision', 'environment', 'created')
EXPOSURE_RECORD_KEYS = ('schema', 'exposure_id', 'revision', 'activity', 'result_id',
                        'execution_id', 'purpose', 'partition', 'n_rows', 'row_keys',
                        'dataset_sha256', 'columns', 'time')
EXPOSURE_PURPOSES = ('structural_inspection', 'train_eda', 'train_fit',
                     'validation_model_evaluation', 'validation_policy_selection')
EXTENSIONS = {'run': 'mlkit.study.cmd_run', 'render': 'mlkit.study.cmd_render',
              'check': 'mlkit.study.cmd_check', 'preview': 'mlkit.study.cmd_preview',
              # Post-v0.1: read-only session timeline for observed sessions.
              'session-report': 'mlkit.study.cmd_session_report'}
# Post-v0.1 observation kit: ``session-report`` and the opt-in session log.
SESSION_REPORT_SCHEMA = 'hypotrail.session_report/1'
SESSION_REPORT_KEYS = ('schema', 'ok', 'study', 'revision', 'since', 'sources', 'span',
                       'commands', 'refusals', 'decisions', 'pauses', 'runs', 'renders',
                       'checks', 'gaps', 'timeline', 'privacy')
SESSION_LOG = {'schema': 'hypotrail.session_log/1', 'file': 'session-log.jsonl',
               'env': 'HYPOTRAIL_SESSION_LOG'}
# Phase 3 (WP3.1-WP3.4): render and check payloads, the artefact manifest, check findings.
PHASE3_SCHEMAS = {'render': 'hypotrail.render/1', 'check': 'hypotrail.check/1',
                  'artifacts': 'hypotrail.artifacts/1'}
PHASE3_PAYLOAD_KEYS = {
    'render': ('schema', 'ok', 'study', 'revision', 'status', 'artifacts'),
    'check': ('schema', 'ok', 'study', 'revision', 'target', 'clean', 'counts', 'findings',
              'traced'),
}
ARTIFACT_NAMES = {'report': 'reports/study.html', 'notebook': 'notebooks/study_generated.py',
                  'workbench': 'notebooks/workbench.py'}
MANIFEST_ITEM_KEYS = ('path', 'kind', 'revision', 'status', 'consumed', 'sha256', 'generated',
                      'template_version', 'error', 'last_ok_revision', 'user_edits_preserved',
                      'candidate')
CHECK_FINDINGS = {'number_outside_result': 'error', 'unknown_result_id': 'error',
                  'value_mismatch': 'error', 'stale_result_cited': 'error',
                  'feature_without_status': 'error', 'excluded_feature_used': 'error',
                  'untraceable_number': 'error', 'stale_number': 'error',
                  'causal_wording': 'warning', 'forecast_wording': 'warning',
                  'artifact_not_current': 'warning', 'untracked_files': 'warning',
                  # Post-v0.1 (P7).
                  'misattributed_delegation': 'error'}
LITERAL_KINDS = ('revision', 'ordinal', 'user_words', 'proposal', 'decision_value', 'case',
                 'identifier', 'parameter', 'environment', 'setting', 'message', 'category')
WRITER_MODULES = {'store', 'lock', 'registry', 'exposure', 'dependencies', 'commands', 'cli',
                  'migrate', 'preconditions'}


def _run(*argv):
    outcome = cli.run([str(a) for a in argv])
    json.dumps(outcome.payload)
    return outcome


@pytest.fixture
def flow(tmp_path, synthetic_case_dir):
    """Payloads of a short decision flow, run in-process through ``cli.run``."""
    study = tmp_path / 'study'
    out = {'init': _run('init', '--case', synthetic_case_dir, '--study', study)}
    out['propose'] = _run('decide', 'propose', 'prediction_time', '--value', 'before the reminder',
                          '--restatement', 'You predict before the reminder.', '--rationale',
                          'Earliest moment.', '--request-id', 'a', '--expected-revision', 1,
                          '--study', study)
    out['confirm'] = _run('decide', 'confirm', 'p_1', '--user-words', 'Yes, before the reminder.',
                          '--request-id', 'b', '--expected-revision', 2, '--study', study)
    _run('decide', 'propose', 'prediction_time', '--value', 'at renewal', '--restatement',
         'You predict at renewal.', '--rationale', 'Later.', '--request-id', 'c',
         '--expected-revision', 3, '--study', study)
    out['withdraw'] = _run('decide', 'withdraw', 'p_2', '--request-id', 'd',
                           '--expected-revision', 4, '--study', study)
    out['status'] = _run('status', '--study', study, '--since', 1)
    out['summary'] = _run('status', '--summary', '--study', study)
    out['plan'] = _run('plan', '--study', study)
    out['error'] = _run('decide', 'confirm', 'p_2', '--user-words', 'ok', '--request-id', 'e',
                        '--expected-revision', 5, '--study', study)
    out['study'] = study
    return out


def test_schema_ids_and_exit_codes():
    assert cmd.SCHEMAS == SCHEMAS
    assert {k: getattr(cmd, k) for k in EXIT_CODES} == EXIT_CODES
    assert view.SCHEMA == 'hypotrail.view/1'
    assert rec.RESULT_SCHEMA == 'hypotrail.result/1'
    assert rec.EXPOSURE_SCHEMA == 'hypotrail.exposure/1'
    assert st.SCHEMA == 'hypotrail.study/1'


def test_payload_keys_of_every_command(flow):
    for name in ('init', 'status', 'plan'):
        assert flow[name].exit_code == 0, flow[name].payload
        assert tuple(flow[name].payload) == PAYLOAD_KEYS[name]
        assert flow[name].payload['schema'] == SCHEMAS[name] and flow[name].payload['ok'] is True
    for name, action in (('propose', 'decide.propose'), ('confirm', 'decide.confirm'),
                         ('withdraw', 'decide.withdraw')):
        payload = flow[name].payload
        assert flow[name].exit_code == 0, payload
        assert tuple(payload) == PAYLOAD_KEYS['decide'] and payload['action'] == action
        assert tuple(payload['result']) == RESULT_KEYS_BY_ACTION[action]
    assert tuple(flow['confirm'].payload['result']['invalidation']) == CONFIRM_INVALIDATION_KEYS
    error = flow['error']
    assert error.exit_code == 2 and tuple(error.payload) == PAYLOAD_KEYS['error']
    assert error.payload['ok'] is False and error.payload['command'] == 'decide confirm'
    assert {'code', 'message'} <= set(error.payload['error'])


def test_status_summary_keys(flow):
    summary = flow['summary']
    assert summary.exit_code == 0, summary.payload
    payload = summary.payload
    assert cmd.SUMMARY_SCHEMA == view.SUMMARY_SCHEMA == SUMMARY_SCHEMA
    assert tuple(payload) == SUMMARY_PAYLOAD_KEYS and payload['schema'] == SUMMARY_SCHEMA
    assert view.SUMMARY_KEYS == SUMMARY_PAYLOAD_KEYS[6:]
    assert tuple(payload['goal']) == SUMMARY_GOAL_KEYS
    assert [tuple(step) for step in payload['plan']] == [('id', 'title', 'status')] * len(STEP_IDS)
    assert tuple(payload['decisions']) == st.DECISION_IDS
    assert all(tuple(d) == SUMMARY_DECISION_KEYS for d in payload['decisions'].values())
    assert tuple(payload['executions']) == EXECUTION_VIEW_KEYS
    assert tuple(payload['not_yet_defensible']) == ('top', 'more')
    assert view.RECAP_LABELS == RECAP_LABELS and len(payload['recap']) == len(RECAP_LABELS)
    assert [line.split(':', 1)[0] for line in payload['recap']] == list(RECAP_LABELS)
    assert tuple(payload['artifacts']) == ('status', 'items')
    for name, item in payload['artifacts']['items'].items():
        assert tuple(item) == ('status', 'revision', 'last_ok_revision', 'message'), name
    assert view.SUMMARY_NOTE_KEYS == SUMMARY_NOTE_KEYS
    assert view.SUMMARY_HOLD_KEYS == SUMMARY_HOLD_KEYS and payload['holds'] == []
    keys = ({SUMMARY_SCHEMA} | set(SUMMARY_PAYLOAD_KEYS) | set(SUMMARY_DECISION_KEYS)
            | set(SUMMARY_GOAL_KEYS) | {'top', 'more', 'message'} | set(RECAP_LABELS)
            | set(SUMMARY_NOTE_KEYS) | set(SUMMARY_HOLD_KEYS))
    assert not sorted(k for k in keys if k not in DOC_TOKENS)


def test_view_model_keys(flow):
    v = flow['status'].payload['view']
    assert tuple(v) == VIEW_KEYS == view.VIEW_KEYS
    assert view.DECISION_VIEW_KEYS == DECISION_VIEW_KEYS
    assert view.CONFIRMATION_VIEW_KEYS == CONFIRMATION_VIEW_KEYS
    assert view.PROPOSAL_VIEW_KEYS == PROPOSAL_VIEW_KEYS
    assert view.RESULT_VIEW_KEYS == RESULT_VIEW_KEYS
    assert tuple(v['decisions']) == st.DECISION_IDS
    assert all(tuple(d) == DECISION_VIEW_KEYS for d in v['decisions'].values())
    conf = v['decisions']['prediction_time']['confirmation']
    assert tuple(conf) == CONFIRMATION_VIEW_KEYS and conf['authenticated'] is False
    assert conf['basis'] == 'explicit' and conf['delegation_scope'] is None
    assert tuple(v['exposure']) == EXPOSURE_SUMMARY_KEYS
    assert tuple(v['artifacts']) == ARTIFACT_VIEW_KEYS
    assert tuple(v['facts']) == ('by_status', 'count')
    assert tuple(v['executions']) == EXECUTION_VIEW_KEYS
    assert (view.LIVENESS_RUNNING, view.LIVENESS_UNKNOWN, view.LIVENESS_NOT_CHECKED) \
        == LIVENESS_VALUES
    assert not [k for k in (*EXECUTION_VIEW_KEYS, *LIVENESS_VALUES, 'liveness')
                if k not in DOC_TOKENS]
    assert [s['id'] for s in v['plan']] == list(STEP_IDS)
    assert all(tuple(s) == STEP_KEYS for s in v['plan'])
    assert {'kind', 'message'} <= set(v['next_action'])
    assert {x['id'] for x in v['not_yet_defensible']} <= NOT_YET_DEFENSIBLE_IDS
    assert 'revision' in flow['status'].payload['changes_since'][0]


def test_next_action_kinds_and_not_yet_defensible_ids_in_source():
    source = (STUDY_PKG / 'state.py').read_text(encoding='utf-8')
    assert set(re.findall(r"'kind': '([a-z_]+)'", source)) == NEXT_ACTION_KINDS
    defensible = (inspect.getsource(st.not_yet_defensible) + inspect.getsource(view.build)
                  + inspect.getsource(view._small_data)
                  + inspect.getsource(view.small_partition_warning)
                  + inspect.getsource(view.capacity_warning))
    ids = set(re.findall(r"\{'id': '([a-z_]+)'", defensible))
    assert ids == NOT_YET_DEFENSIBLE_IDS


def _source_codes() -> set[str]:
    texts = [p.read_text(encoding='utf-8') for p in sorted(STUDY_PKG.rglob('*.py'))]
    texts.append((FRAMEWORK / 'mlkit' / 'reliability.py').read_text(encoding='utf-8'))
    codes = set()
    for text in texts:
        codes |= set(re.findall(r"(?:StudyError|CommandRefused|CaseError)\(\s*'([a-z_]+)'", text))
        codes |= set(re.findall(r"'refusal': '([a-z_]+)'", text))
    return codes


def test_error_codes_are_documented_and_frozen():
    emitted = _source_codes() | {'invalid_arguments', 'internal_error'}
    assert emitted <= ERROR_CODES, sorted(emitted - ERROR_CODES)
    assert not (ERROR_CODES | RESERVED_CODES) - DOC_TOKENS
    assert cmd.error_payload('x', ValueError('boom'))['error']['code'] == 'internal_error'


def test_ambiguous_confirmation_reasons():
    source = (STUDY_PKG / 'commands.py').read_text(encoding='utf-8')
    found = set(re.findall(r"_ambiguous\('([a-z_]+)'", source))
    dynamic = {f'proposal_{s}' for s in st.PROPOSAL_STATUSES if s != 'open'}
    assert found | dynamic == AMBIGUOUS_REASONS
    assert not AMBIGUOUS_REASONS - DOC_TOKENS


def test_notes_hold_a_decision_until_the_junior_resolves_them(tmp_path, synthetic_case_dir):
    """P2 (post-v0.1): ``decide note --about`` / ``--resolve``, its state, view, summary and
    refusal keys."""
    assert st.TOP_OPTIONAL_KEYS == ('task', 'notes')
    assert st.NOTE_KEYS == NOTE_STATE_KEYS and st.NOTE_RESOLUTION_KEYS == NOTE_RESOLUTION_KEYS
    assert st.NOTE_KINDS == ('hold',) and st.NOTE_STATUSES == NOTE_STATUSES
    assert view.NOTE_VIEW_KEYS == NOTE_VIEW_KEYS
    study = tmp_path / 'study'
    _run('init', '--case', synthetic_case_dir, '--study', study)
    out = _run('decide', 'note', '--about', 'policy', '--text',
               "Don't adopt anything until I bring my manager's figure.", '--request-id', 'n1',
               '--expected-revision', 1, '--study', study)
    assert out.exit_code == 0, out.payload
    assert tuple(out.payload) == PAYLOAD_KEYS['decide']
    assert tuple(out.payload['result']) == RESULT_KEYS_BY_ACTION['decide.note']
    v = _run('status', '--study', study).payload['view']
    assert [tuple(n) for n in v['notes']] == [NOTE_VIEW_KEYS]
    assert 'open_holds' in {x['id'] for x in v['not_yet_defensible']}
    summary = _run('status', '--summary', '--study', study).payload
    assert [tuple(n) for n in summary['notes']] == [SUMMARY_NOTE_KEYS]
    out = _run('decide', 'note', '--resolve', 'n_1', '--text', "My manager's figure is in.",
               '--request-id', 'n2', '--expected-revision', 2, '--study', study)
    assert out.exit_code == 0, out.payload
    assert tuple(out.payload['result']) == RESULT_KEYS_BY_ACTION['decide.resolve_note']
    out = _run('decide', 'note', '--about', 'split', '--text', 'Wait for the data owner on the '
               'split.', '--request-id', 'n3', '--expected-revision', 3, '--study', study)
    summary = _run('status', '--summary', '--study', study).payload
    assert [tuple(h) for h in summary['holds']] == [SUMMARY_HOLD_KEYS]
    out = _run('decide', 'note', '--withdraw', 'n_2', '--text', 'No need to wait for the data '
               'owner after all.', '--request-id', 'n4', '--expected-revision', 4, '--study', study)
    assert out.exit_code == 0, out.payload
    assert tuple(out.payload['result']) == RESULT_KEYS_BY_ACTION['decide.withdraw_note']
    assert out.payload['result']['status'] == 'withdrawn'
    keys = (set(NOTE_VIEW_KEYS) | set(NOTE_STATE_KEYS) | set(NOTE_RESOLUTION_KEYS)
            | set(NOTE_STATUSES) | {'decide.note', 'decide.resolve_note', 'decide.withdraw_note',
                                    'open_holds', 'notes', 'reconfirm_required', 'hold_added'})
    assert not sorted(k for k in keys if k not in DOC_TOKENS)
    assert ('hypotrail decide note (--about DECISION | --resolve NOTE_ID | --withdraw NOTE_ID) '
            '--text TEXT' in DOC)


def test_small_data_warnings_are_documented():
    """G.12 (post-v0.1): the small-data thresholds, the grouping default, and the new
    result value keys."""
    from mlkit.study import activities as act, eda
    assert (view.SMALL_VALIDATION_ROWS, view.SMALL_VALIDATION_POSITIVES) == (30, 5)
    assert (eda.MAX_GROUPS, eda.OTHER_GROUP) == (20, '(other values)')
    assert act.normalize_options('eda.rate_by', {'column': 'x'}) == {'column': 'x'}
    assert act.normalize_options('eda.mean_by', {'column': 'x', 'max_groups': 5}) == \
        {'column': 'x', 'max_groups': 5}
    keys = {'view.SMALL_VALIDATION_ROWS', 'view.SMALL_VALIDATION_POSITIVES', 'eda.MAX_GROUPS',
            'n_groups', 'max_groups', 'other', 'n_values', 'min_rows', 'min_positive'}
    assert not sorted(k for k in keys if k not in DOC_TOKENS)
    assert '--max-groups N' in DOC and '`(other values)`' in DOC
    # Post-v0.1 fixes (D4): inclusive thresholds, and the warnings of ``preview policy``.
    split = {'partitions': {'validation': {'n_rows': 30, 'n_positive': 5}}}
    assert view.small_partition_warning(split, True)['id'] == 'small_validation_partition'
    assert view.capacity_warning(['capacity:30'], 30)['id'] == 'capacity_exceeds_validation'
    from mlkit.study import cmd_preview
    assert cmd_preview.PAYLOAD_KEYS == PREVIEW_PAYLOAD_KEYS
    keys = {'view.small_partition_warning', 'view.capacity_warning', 'warnings'}
    assert not sorted(k for k in keys if k not in DOC_TOKENS)
    assert 'at most `view.SMALL_VALIDATION_ROWS` (30) rows' in DOC


def test_check_traces_structure_counts_and_the_binary_recap_headline():
    """Post-v0.1 fixes D8 (structure counts in ``check``) and D10 (the binary recap's
    headline policy result)."""
    from mlkit.study import cmd_check
    assert tuple(cmd_check.STRUCTURE_NOUNS) == ('features', 'groups', 'steps', 'pauses',
                                                'decisions')
    assert {'columns', 'features', 'variables'} <= set(cmd_check.STRUCTURE_NOUNS['features'])
    assert view.HEADLINE_MODEL == 'fit.logistic' and view.RECAP_RID == 8
    keys = {'cmd_check.STRUCTURE_NOUNS', 'structure', 'plan.steps', 'plan.pauses',
            'latest', 'Decided', 'Now'}
    assert not sorted(k for k in keys if k not in DOC_TOKENS)


def test_negative_reply_targets_the_agreement():
    """P1 (post-v0.1 acceptance): a negation is a refusal only when it targets the agreement
    or the proposal; the rule's named parts are documented."""
    for name in ('REFUSES_AGREEMENT', 'NEGATIVE_LEADS', 'REFUSAL_OPENINGS',
                 'FIRST_CLAUSE_REFUSALS', 'AGREEMENT_LEAD', 'is_negative'):
        assert hasattr(cmd, name) and f'commands.{name}' in DOC_TOKENS, name
    assert {'no', 'non', 'wait', 'stop', 'attends'} <= cmd.NEGATIVE_LEADS
    assert {('not', 'yet'), ('pas', 'encore')} <= set(cmd.REFUSAL_OPENINGS)
    for words in ('no', 'No, I do not agree with that at all', 'wait', 'non', 'not yet',
                  "je ne suis pas d'accord", 'pas d’accord', 'attends',
                  'Yes, but not before the first call'):
        assert cmd.reply_problem(words) == 'negative_reply', words
    for words in ("Yes, and it's not a forecast", 'agreed, never an input',
                  "ok with that — these aren't evidence of future error"):
        assert not cmd.is_negative(words), words


def test_actions_and_their_parameters():
    ctx = cmd.Context(store=None, request_id='x')
    built = cmd.handlers(ctx)
    for action, params in ACTION_PARAMS.items():
        assert set(built[action].params) == params
        assert isinstance(built[action], reliability.Handler)
    assert set(reliability.REQUEST_KEYS) == {'request_id', 'expected_revision', 'action', 'params'}
    assert cmd.DEFAULT_CHANNEL == 'chat' and st.CHANNELS == ('chat', 'cli', 'webview')
    assert st.CONFIRMATION_BASES == CONFIRMATION_BASES and cmd.DEFAULT_BASIS == 'explicit'
    assert st.CONFIRMATION_OPTIONAL_KEYS == ('basis', 'delegation_scope')
    assert not set(CONFIRMATION_BASES) - DOC_TOKENS
    assert st.DELEGATION_SCOPES == DELEGATION_SCOPES
    assert st.STANDING_DELEGATION_DECISIONS == STANDING_DELEGATION_DECISIONS
    assert not (set(DELEGATION_SCOPES) | {'delegation_scope'}) - DOC_TOKENS
    assert '--delegation-scope this_decision|standing' in DOC
    assert st.DECISION_IDS == ('prediction_time', 'feature_availability', 'split', 'policy',
                               'conclusion')
    assert st.AVAILABILITY_DECISIONS == ('available_at_prediction', 'not_available',
                                         'uncertain_excluded', 'uncertain_included')
    assert pre.CONCLUSION_VERDICTS == ('adopt_policy', 'keep_baseline', 'inconclusive')


def test_regression_contract_constants():
    """M3: the regression study's decisions, steps, slots, verdicts, split methods, and
    dependency table ids."""
    from mlkit.study import activities as act, case as c
    assert st.TASKS == TASKS and c.SUPPORTED_TASKS == TASKS
    assert st.REGRESSION_DECISION_IDS == REGRESSION_DECISION_IDS
    assert st.REGRESSION_STEP_IDS == REGRESSION_STEP_IDS
    assert st.REGRESSION_ACTIVITY_SLOTS == REGRESSION_ACTIVITY_SLOTS
    assert st.CHOICE_DECISION == {'binary': 'policy', 'regression': 'model_choice'}
    assert pre.REGRESSION_CONCLUSION_VERDICTS == REGRESSION_CONCLUSION_VERDICTS
    assert pre.MODEL_CHOICES == MODEL_CHOICES
    assert cmd.ALL_SPLIT_METHODS == SPLIT_METHODS
    assert cmd.ORDINAL_SPLIT_KEYS == ('method', 'column', 'cutoff')
    assert st.PER_COLUMN_SLOT_PREFIXES == ('eda.rate_by:', 'eda.mean_by:')
    assert act.TASK_ACTIVITIES['regression'] == ('split', 'eda.target_summary',
                                                 'eda.special_values', 'eda.mean_by',
                                                 'fit.baseline', 'fit.linear',
                                                 'evaluate.regression')
    assert {m['row']: m['mutation'] for m in dep.REGRESSION_MUTATIONS} == REGRESSION_MUTATION_IDS
    assert c.CAPABILITY_TIME_SPLIT == 'temporal split on a date or non-integer time column (v0.2)'
    assert c.CAPABILITY_GROUPED_SPLIT == 'grouped split (v0.2)'
    keys = (set(TASKS) | set(REGRESSION_DECISION_IDS) | set(REGRESSION_STEP_IDS)
            | set(REGRESSION_ACTIVITY_SLOTS) | set(REGRESSION_CONCLUSION_VERDICTS)
            | set(MODEL_CHOICES) | set(SPLIT_METHODS) | set(REGRESSION_MUTATION_IDS.values())
            | {'eda.mean_by', 'residuals_by', 'mean_residual', 'cutoff', 'groups'})
    assert not sorted(k for k in keys if k not in DOC_TOKENS)


def test_dependency_table_ids_and_effect_keys(flow):

    assert dep.EFFECT_KEYS == EFFECT_KEYS
    assert {m['row']: m['mutation'] for m in dep.MUTATIONS} == MUTATION_IDS
    state = read.open(flow['study']).state
    eff = dep.effects(state, 'prediction_time', 'a', 'b')
    assert set(EFFECT_KEYS) | set(dep.META_KEYS) <= set(eff)
    record = dep.apply_effects(state, eff, revision=99, decision_id='prediction_time')
    assert tuple(record) == INVALIDATION_KEYS


def test_storage_keys():
    assert rec.RESULT_KEYS == REGISTRY_ENTRY_KEYS
    assert rec.EXPOSURE_KEYS == EXPOSURE_RECORD_KEYS
    assert rec.EXPOSURE_PURPOSES == EXPOSURE_PURPOSES
    assert exposure.PARTITIONS == ('all', 'train', 'validation')
    assert exposure.EXPOSURE_FILE == 'exposure.jsonl'
    assert registry.INDEX_FILE == 'registry-index.jsonl'
    assert read.ARTIFACTS_FILE == 'artifacts.json'


def _params(fn) -> list[tuple[str, str]]:
    return [(p.name, p.kind.name) for p in inspect.signature(fn).parameters.values()]


def test_extension_point_signatures():
    assert cli.EXTENSIONS == EXTENSIONS
    assert cmd.AFTER_COMMIT_MODULE == 'mlkit.study.cmd_render'
    assert _params(cmd.register_action) == [('name', 'POSITIONAL_OR_KEYWORD'),
                                            ('factory', 'POSITIONAL_OR_KEYWORD')]
    assert [n for n, _ in _params(cmd.apply)] == ['study_dir', 'action', 'params', 'request_id',
                                                  'expected_revision', 'command']
    assert [f for f in cmd.Context.__dataclass_fields__] == ['store', 'request_id']
    assert [f for f in cmd.Outcome.__dataclass_fields__] == ['payload', 'exit_code']
    assert [n for n, _ in _params(registry.put)] == [
        'store', 'activity', 'params', 'inputs', 'code', 'values', 'blobs', 'partition', 'n_rows',
        'exposure_id', 'execution_id', 'started_revision', 'env']
    assert [n for n, _ in _params(registry.get)] == ['store', 'rid']
    assert [n for n, _ in _params(registry.lineage)] == ['store', 'rid']
    assert [n for n, _ in _params(registry.is_current)] == ['state', 'rid']
    assert [n for n, _ in _params(registry.code_fingerprint)] == ['modules']
    assert [n for n, _ in _params(exposure.record)] == [
        'store', 'exposure_id', 'revision', 'activity', 'result_id', 'purpose', 'partition',
        'row_keys', 'dataset_sha256', 'columns', 'execution_id']
    assert [n for n, _ in _params(exposure.overlap)] == ['old_split', 'new_split', 'store']
    assert [n for n, _ in _params(exposure.summary)] == ['store', 'state']
    assert [n for n, _ in _params(dep.effects)] == ['old_state', 'decision_id', 'old', 'new']
    # Review fix H2 added the keyword-only seeds and keep (result replacement).
    assert [n for n, _ in _params(dep.apply_effects)] == ['state', 'eff', 'revision',
                                                          'decision_id', 'store', 'previous',
                                                          'seeds', 'keep']
    assert [n for n, _ in _params(dep.apply_replacement)] == ['state', 'slot', 'previous', 'new',
                                                              'revision', 'store', 'code_changed']
    assert [n for n, _ in _params(pre.require_activity)] == ['state', 'activity']
    assert [n for n, _ in _params(pre.missing_for_activity)] == ['state', 'activity']
    assert [n for n, _ in _params(pre.require_decision)] == ['state', 'decision_id', 'value',
                                                             'store']
    assert [n for n, _ in _params(view.build)] == ['study_dir', 'leases']   # leases: F1
    assert [n for n, _ in _params(read.open)] == ['study_dir']
    for method in ('current', 'is_current', 'result', 'predictions', 'source', 'revisions',
                   'exposure_records', 'exposure_summary', 'artifacts', 'stale_reason', 'blob'):
        assert callable(getattr(read.Study, method)), method
    assert isinstance(inspect.getattr_static(read.Study, 'revision'), property)
    assert isinstance(inspect.getattr_static(read.Study, 'state'), property)


def test_extension_modules_are_absent_in_phase_1_or_follow_the_interface():
    import importlib
    import importlib.util
    for name, module in EXTENSIONS.items():
        if importlib.util.find_spec(module) is None:
            continue
        loaded = importlib.import_module(module)
        assert callable(getattr(loaded, 'configure')) and callable(getattr(loaded, 'main')), name


def test_phase3_render_and_check_contract():
    import importlib
    import importlib.util
    if any(importlib.util.find_spec(f'mlkit.study.{m}') is None
           for m in ('cmd_render', 'cmd_check')):
        pytest.skip('Phase 3 render and check are not present')
    from mlkit.study import cmd_check, cmd_render, manifest, render_html
    assert cmd_render.SCHEMA == PHASE3_SCHEMAS['render']
    assert cmd_check.SCHEMA == PHASE3_SCHEMAS['check']
    assert manifest.SCHEMA == PHASE3_SCHEMAS['artifacts']
    assert manifest.ARTIFACTS == ARTIFACT_NAMES and manifest.ITEM_KEYS == MANIFEST_ITEM_KEYS
    assert cmd_check.SEVERITY == CHECK_FINDINGS
    # Acceptance rerun R3: a digit-only result id prefix is an identifier, not a figure.
    assert cmd_check.RESULT_ID_DIGITS.pattern == r'\d{6,}'
    assert [n for n, _ in _params(cmd_check.check_text)] == ['view', 'text', 'where',
                                                             'user_texts', 'result_ids']
    assert {'cmd_check.registry_ids', 'result_id'} <= DOC_TOKENS
    assert render_html.LITERAL_KINDS == LITERAL_KINDS
    assert cmd_render.FAULTS == ('render_html', 'render_notebook')
    assert (cmd_render.FAULT_ENV, cmd_render.HOOKS_ENV) == ('HYPOTRAIL_FAULT', 'HYPOTRAIL_TEST_HOOKS')
    assert [n for n, _ in _params(cmd_render.after_commit)] == ['study_dir', 'payload']
    keys = (set(PHASE3_SCHEMAS.values()) | set(CHECK_FINDINGS) | set(LITERAL_KINDS)
            | set(MANIFEST_ITEM_KEYS) | set(ARTIFACT_NAMES)
            | {k for keys in PHASE3_PAYLOAD_KEYS.values() for k in keys})
    assert not sorted(k for k in keys if k not in DOC_TOKENS)


def test_session_report_and_session_log_contract():
    from mlkit.study import cmd_session_report, sessionlog
    assert cmd_session_report.SCHEMA == SESSION_REPORT_SCHEMA
    assert cmd_session_report.PAYLOAD_KEYS == SESSION_REPORT_KEYS
    assert (sessionlog.SCHEMA, sessionlog.LOG_FILE, sessionlog.ENV) == tuple(SESSION_LOG.values())
    assert sessionlog.UNLOGGED == ('session-report',)
    assert 'hypotrail session-report --study DIR [--since REV]' in DOC
    keys = {SESSION_REPORT_SCHEMA, *SESSION_REPORT_KEYS, SESSION_LOG['schema'],
            SESSION_LOG['env']}
    assert not sorted(k for k in keys if k not in DOC_TOKENS)
    assert f".hypotrail/{SESSION_LOG['file']}" in DOC


def test_read_side_never_imports_writer_modules():
    for name in ('read.py', 'view.py'):
        tree = (STUDY_PKG / name).read_text(encoding='utf-8')
        imported = set(re.findall(r'from \. import ([a-z_]+)', tree)) | set(
            re.findall(r'from \.([a-z_]+) import', tree))
        assert not imported & WRITER_MODULES, (name, imported & WRITER_MODULES)


def test_documented_keys_appear_in_the_contract_document():
    keys = (set(VIEW_KEYS) | set(DECISION_VIEW_KEYS) | set(RESULT_VIEW_KEYS) | set(STEP_KEYS)
            | set(INVALIDATION_KEYS) | set(EFFECT_KEYS) | set(REGISTRY_ENTRY_KEYS)
            | set(EXPOSURE_RECORD_KEYS) | set(EXPOSURE_SUMMARY_KEYS) | set(SCHEMAS.values())
            | {k for keys in PAYLOAD_KEYS.values() for k in keys} | set(MUTATION_IDS.values())
            | NEXT_ACTION_KINDS | NOT_YET_DEFENSIBLE_IDS | set(STEP_IDS))
    missing = sorted(k for k in keys if k not in DOC_TOKENS)
    assert not missing, missing
    assert 'Contract tests: Phase 2/3 agents must not modify' in Path(__file__).read_text()


def test_named_refusals_of_values_and_splits_are_documented():
    """M3 generality: every capability a split or a value check refuses with is named in
    the contracts, in the same words as the code."""
    from mlkit.study import activities, data
    case_doc = (REPO / 'docs' / 'specs' / 'CASE-CONTRACT.md').read_text(encoding='utf-8')
    for name in (activities.CAPABILITY_STRATIFY, activities.CAPABILITY_SPLIT_PARAMETERS):
        assert f'`{name}`' in DOC, name
    for name in (data.CAPABILITY_MISSING_TARGET, data.CAPABILITY_DUPLICATES):
        assert f'`{name}`' in case_doc, name
    assert f'`{data.CAPABILITY_MISSING_TARGET}`' in DOC
