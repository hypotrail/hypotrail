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
                       'actor', 'invalidation'),
    'decide.withdraw': ('proposal_id', 'decision_id', 'status', 'decision_status'),
}
ACTION_PARAMS = {'decide.propose': {'decision_id', 'value', 'restatement', 'rationale'},
                 'decide.confirm': {'proposal_id', 'user_words', 'channel', 'actor'},
                 'decide.withdraw': {'proposal_id', 'reason'}}
VIEW_KEYS = ('schema', 'study', 'revision', 'updated', 'case', 'dataset', 'plan', 'current_step',
             'next_action', 'open_proposals', 'decisions', 'facts', 'structure', 'results',
             'stale', 'invalidations', 'executions', 'artifacts', 'exposure',
             'not_yet_defensible', 'settings')
DECISION_VIEW_KEYS = ('decision_id', 'status', 'value', 'proposal_id', 'depends_on', 'revision',
                      'reason', 'confirmation', 'open_proposals')
CONFIRMATION_VIEW_KEYS = ('user_words', 'channel', 'actor', 'restatement', 'proposal_id',
                          'revision', 'time', 'authenticated')
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
NEXT_ACTION_KINDS = {'acknowledge_interruption', 'reconfirm', 'await_user_words', 'blocked',
                     'propose', 'run', 'done'}
NOT_YET_DEFENSIBLE_IDS = {'unconfirmed_decisions', 'validation_is_not_independent',
                          'public_data_already_explored', 'no_time_or_entity_identifier',
                          'uncertain_features_included', 'stale_results',
                          'interrupted_executions', 'no_causality', 'workbench_not_tracked',
                          'result_integrity'}
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
    'interrupted_execution_pending', 'unknown_execution', 'read_only'}
RESERVED_CODES: set[str] = set()
AMBIGUOUS_REASONS = {'missing_user_words', 'bare_acknowledgement', 'proposal_not_found',
                     'proposal_withdrawn', 'proposal_superseded', 'proposal_confirmed',
                     'same_request', 'proposal_stale'}
REGISTRY_ENTRY_KEYS = ('schema', 'result_id', 'input_key', 'activity', 'params', 'inputs', 'code',
                       'output', 'blobs', 'partition', 'n_rows', 'exposure_id', 'execution_id',
                       'started_revision', 'environment', 'created')
EXPOSURE_RECORD_KEYS = ('schema', 'exposure_id', 'revision', 'activity', 'result_id',
                        'execution_id', 'purpose', 'partition', 'n_rows', 'row_keys',
                        'dataset_sha256', 'columns', 'time')
EXPOSURE_PURPOSES = ('structural_inspection', 'train_eda', 'train_fit',
                     'validation_model_evaluation', 'validation_policy_selection')
EXTENSIONS = {'run': 'mlkit.study.cmd_run', 'render': 'mlkit.study.cmd_render',
              'check': 'mlkit.study.cmd_check', 'preview': 'mlkit.study.cmd_preview'}
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
    assert tuple(v['exposure']) == EXPOSURE_SUMMARY_KEYS
    assert tuple(v['artifacts']) == ARTIFACT_VIEW_KEYS
    assert tuple(v['facts']) == ('by_status', 'count')
    assert tuple(v['executions']) == ('active', 'interrupted', 'late')
    assert [s['id'] for s in v['plan']] == list(STEP_IDS)
    assert all(tuple(s) == STEP_KEYS for s in v['plan'])
    assert {'kind', 'message'} <= set(v['next_action'])
    assert {x['id'] for x in v['not_yet_defensible']} <= NOT_YET_DEFENSIBLE_IDS
    assert 'revision' in flow['status'].payload['changes_since'][0]


def test_next_action_kinds_and_not_yet_defensible_ids_in_source():
    source = (STUDY_PKG / 'state.py').read_text(encoding='utf-8')
    assert set(re.findall(r"'kind': '([a-z_]+)'", source)) == NEXT_ACTION_KINDS
    defensible = inspect.getsource(st.not_yet_defensible) + inspect.getsource(view.build)
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


def test_actions_and_their_parameters():
    ctx = cmd.Context(store=None, request_id='x')
    built = cmd.handlers(ctx)
    for action, params in ACTION_PARAMS.items():
        assert set(built[action].params) == params
        assert isinstance(built[action], reliability.Handler)
    assert set(reliability.REQUEST_KEYS) == {'request_id', 'expected_revision', 'action', 'params'}
    assert cmd.DEFAULT_CHANNEL == 'chat' and st.CHANNELS == ('chat', 'cli', 'webview')
    assert st.DECISION_IDS == ('prediction_time', 'feature_availability', 'split', 'policy',
                               'conclusion')
    assert st.AVAILABILITY_DECISIONS == ('available_at_prediction', 'not_available',
                                         'uncertain_excluded', 'uncertain_included')
    assert pre.CONCLUSION_VERDICTS == ('adopt_policy', 'keep_baseline', 'inconclusive')


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
    assert [n for n, _ in _params(dep.apply_effects)] == ['state', 'eff', 'revision',
                                                          'decision_id', 'store', 'previous']
    assert [n for n, _ in _params(pre.require_activity)] == ['state', 'activity']
    assert [n for n, _ in _params(pre.missing_for_activity)] == ['state', 'activity']
    assert [n for n, _ in _params(pre.require_decision)] == ['state', 'decision_id', 'value',
                                                             'store']
    assert [n for n, _ in _params(view.build)] == ['study_dir']
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
