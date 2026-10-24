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
                        # v0.2a (ADR 0006): the sealed final test, or status absent.
                        'final_test',
                        # v0.2a (WP-A4): the success criterion and the target-look count.
                        'criterion', 'eda_looks',
                        # Post-v0.1 (T8, F5): five resume lines generated from state.
                        'recap',
                        # v0.2a (WP-A1): who the recap is for, and its junior variant.
                        'recap_audience', 'recap_junior',
                        # v0.2a (WP-A7, companion requests): the confirmation mode and the
                        # view's ``deliverables``.
                        'mode', 'deliverables',
                        # v0.2b (WP-B1): the trial count.
                        'trials',
                        # v0.2b (WP-B6a): the scenario defaults, values only.
                        'scenario_defaults',
                        # v0.3 (WP-E2, R21): the study language.
                        'language')
SUMMARY_NOTE_KEYS = ('note_id', 'decision_id', 'status', 'user_words', 'resolution_words')
SUMMARY_HOLD_KEYS = ('decision_id', 'status', 'notes')
# Post-v0.1 fixes (D5): a hold may be withdrawn in the junior's words.
NOTE_STATUSES = ('open', 'resolved', 'withdrawn',
                 # ADR 0005 (R3): a correction is recorded at once.
                 'recorded')
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
                         'open_proposals',
                         # v0.2a (WP-A1): grouped per-feature basis of the availability.
                         'feature_basis')
# v0.2a (WP-A1): who each message is written for, and its junior variant.
AUDIENCES = ('junior', 'agent')
FEATURE_BASES = ('discussed', 'default_from_case')
SUMMARY_ARTIFACT_ITEM_KEYS = ('status', 'revision', 'last_ok_revision', 'message', 'audience',
                              'junior_message')
SUMMARY_LIMIT_KEYS = ('id', 'text', 'audience', 'junior_text')
DELIVERABLES_KEYS = ('interpreter', 'launch')
LAUNCH_KEYS = ('mode', 'path', 'argv', 'shell')
NOTICE_KEYS = ('code', 'audience', 'message', 'junior_message', 'line')
SUMMARY_GOAL_KEYS = ('intended_use', 'decision', 'observation_unit', 'prediction_time')
EXIT_CODES = {'EXIT_OK': 0, 'EXIT_INTERNAL': 1, 'EXIT_REFUSED': 2, 'EXIT_ARTIFACT_STALE': 3,
              'EXIT_UNKNOWN_OUTCOME': 4}
PAYLOAD_KEYS = {
    'init': ('schema', 'ok', 'study', 'revision', 'case', 'dataset', 'structural_exposure',
             # v0.2a (ADR 0006): the sealed final test.
             'final_test', 'plan',
             'next_action', 'agent_instructions', 'ignored_sources', 'note',
             # v0.2a (WP-A1, R7): editor-settings notices and the notebook launch commands.
             'notices', 'deliverables'),
    'status': ('schema', 'ok', 'study', 'revision', 'since', 'changed', 'changes_since', 'view'),
    'plan': ('schema', 'ok', 'study', 'revision', 'steps', 'current_step', 'next_action'),
    'decide': ('schema', 'ok', 'study', 'action', 'request_id', 'replayed', 'revision', 'result',
               'artifacts',
               # v0.3 (WP-J): the next action after the write, as status gives it.
               'next_action'),
    'error': ('schema', 'ok', 'command', 'error'),
}
RESULT_KEYS_BY_ACTION = {
    'decide.propose': ('proposal_id', 'decision_id', 'status', 'decision_status', 'superseded',
                       'restatement',
                       # v0.3 (WP-A, R32): said before the proposal is presented.
                       'data_contingent', 'data_contingent_reason'),
    'decide.confirm': ('decision_id', 'proposal_id', 'status', 'value', 'user_words', 'channel',
                       'actor', 'invalidation', 'basis', 'delegation_scope',
                       # ADR 0005 (R3): the agent's concern, and the contradiction warnings.
                       'agent_concern', 'warnings',
                       # v0.2b (WP-B2): the confirmation mode in force.
                       'mode',
                       # WP-B1: the opening of the final test that a final_test confirmation
                       # runs (null for any other decision).
                       'opening',
                       # v0.3 (WP-B, R27, R14/R16): whether a trade-off's words give a
                       # reason (null otherwise), and whether they answer the closed
                       # adoption question.
                       'reason_given', 'adoption_question'),
    'decide.withdraw': ('proposal_id', 'decision_id', 'status', 'decision_status'),
    # Post-v0.1 (P2).
    # Post-v0.1 fixes (D1): the decisions a hold on a confirmed decision asks for again.
    'decide.note': ('note_id', 'decision_id', 'status', 'user_words', 'open_holds',
                    'reconfirm_required',
                    # ADR 0005 (R3): hold or correction.
                    'kind'),
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
                 'decide.withdraw_note': {'note_id', 'user_words'},
                 # ADR 0005: the confirmation mode, in the user's words.
                 'study.set_mode': {'mode', 'user_words'}}
# ADR 0005: optional parameters, carried only when given (a replay stays a replay).
OPTIONAL_ACTION_PARAMS = {'decide.propose': {'channel', 'labels'},
                          'decide.confirm': {'agent_concern', 'adoption_question'},
                          'decide.note': {'kind'}}
VIEW_KEYS = ('schema', 'study', 'revision', 'updated', 'case', 'dataset', 'plan', 'current_step',
             'next_action', 'open_proposals', 'decisions', 'facts', 'structure', 'results',
             'stale', 'invalidations', 'executions', 'artifacts', 'exposure',
             'not_yet_defensible', 'settings',
             # M3 (regression): the task of the study, ``binary`` or ``regression``.
             'task',
             # Post-v0.1 (P2): the junior's conditions and holds.
             'notes',
             # v0.2a (ADR 0006): the sealed final test, or status absent.
             'final_test',
             # v0.2a (WP-A1, R7): the engine's Python and the notebook launch commands.
             'deliverables',
             # ADR 0005: the confirmation mode and the study language.
             'mode', 'language',
             # v0.2a (WP-A4): the success criterion assessment and the target-look ledger.
             'criterion', 'eda_looks',
             # v0.2b (WP-B3, R6): the teaching scenario's defaults from the case, or null.
             'scenario_defaults',
             # v0.2b (WP-B1): the configurations evaluated so far.
             'trials',
             # v0.3 (WP-F1): the selection among the variants and the model families.
             'model_selection', 'model_families', 'assurance',
             # Reliability roadmap J2: derived, null for legacy studies.
             'requirements', 'completion', 'claim_eligibility', 'presentation')
DECISION_VIEW_KEYS = ('decision_id', 'status', 'value', 'proposal_id', 'depends_on', 'revision',
                      'reason', 'confirmation', 'open_proposals',
                      # v0.2a (WP-A1): per-feature basis of a feature availability value.
                      'feature_basis')
CONFIRMATION_VIEW_KEYS = ('user_words', 'channel', 'actor', 'restatement', 'proposal_id',
                          'revision', 'time', 'authenticated', 'basis', 'delegation_scope',
                          # ADR 0005 (R3).
                          'agent_concern',
                          # v0.2b (WP-B2): the mode in force when the words were accepted.
                          'mode',
                          # WP-A9 (H3): the words_contradict_value warnings kept.
                          'warnings',
                          # v0.3 (WP-B, R27, R14/R16): a trade-off's reason, the closed
                          # adoption question.
                          'reason_given', 'adoption_question')
# Post-acceptance contract (D1): how the user decided. ADR 0005 adds the two recorded kinds
# of own words of the guided mode; ``explicit`` stays readable and is the request default.
CONFIRMATION_BASES = ('explicit', 'endorsed', 'restated', 'delegated_default')
REQUEST_BASES = ('explicit', 'delegated_default')
# ADR 0005: confirmation modes, languages, the guided reply reasons and warnings.
MODES = ('guided', 'training', 'express')
# v0.2b (WP-B2): the three modes are implemented.
SUPPORTED_MODES = ('guided', 'training', 'express')
MODE_STRICTNESS = {'express': 0, 'guided': 1, 'training': 2}
LANGUAGES = ('en', 'fr')
MODE_CHANGE_KEYS = ('mode', 'previous', 'user_words', 'revision', 'time', 'request_id')
WARNING_KEYS = ('code', 'variable', 'said', 'value', 'message')
# Acceptance rerun (R1): the scope of a delegation. A standing delegation never covers the
# policy or the conclusion.
DELEGATION_SCOPES = ('this_decision', 'standing')
STANDING_DELEGATION_DECISIONS = ('prediction_time', 'feature_availability', 'split')
# v0.2b (WP-B2): in the express mode, the framing decisions that follow the split too.
EXPRESS_STANDING_DELEGATION_DECISIONS = ('prediction_time', 'feature_availability', 'split',
                                         'success_criterion', 'preprocessing')
PROPOSAL_VIEW_KEYS = ('proposal_id', 'decision_id', 'value', 'restatement', 'rationale',
                      'revision', 'created',
                      # ADR 0005: restatements per language, and the study-language one,
                      # inserted before origin, which stays last (CI.6).
                      'labels', 'label',
                      # Advanced companion (C9, decision CI.6): additive, last.
                      'origin')
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
# v0.2a (WP-A4): a study created by init has seven decisions and ten steps; the v0.1 sets
# above stay the sets of a study created before (never migrated).
FULL_DECISION_IDS = ('prediction_time', 'feature_availability', 'split', 'success_criterion',
                     'preprocessing', 'policy', 'conclusion')
FULL_REGRESSION_DECISION_IDS = ('prediction_time', 'feature_availability', 'split',
                                'success_criterion', 'preprocessing', 'model_choice',
                                'conclusion')
# v0.2b (WP-B1): a study created by init has nine decisions and twelve steps; the v0.2a sets
# above stay the sets of a study created before (never migrated).
B1_DECISION_IDS = ('prediction_time', 'feature_availability', 'split', 'success_criterion',
                   'preprocessing', 'model_variant', 'policy', 'final_test', 'conclusion')
B1_REGRESSION_DECISION_IDS = ('prediction_time', 'feature_availability', 'split',
                              'success_criterion', 'preprocessing', 'model_variant',
                              'model_choice', 'final_test', 'conclusion')
B2_DECISION_IDS = ('prediction_time', 'feature_availability', 'split', 'success_criterion',
                   'preprocessing', 'model_variant', 'model_choice', 'policy', 'final_test',
                   'conclusion')
B1_STEP_IDS = ('discover_data', 'prediction_time', 'feature_availability', 'split',
               'success_criterion', 'train_eda', 'preprocessing', 'models', 'model_variant',
               'policy', 'final_test', 'conclusion')
B2_BINARY_STEP_IDS = ('discover_data', 'prediction_time', 'feature_availability', 'split',
                      'success_criterion', 'train_eda', 'preprocessing', 'models',
                      'model_variant', 'model_choice', 'policy', 'final_test', 'conclusion')
CV_METHODS = ('kfold_stratified', 'kfold_quantile', 'temporal_folds',
              'forward_chaining', 'ordered_retrospective', 'group_disjoint')
TRIALS_KEYS = ('count', 'results', 'note')
OPENING_RESULT_KEYS = ('status', 'execution_id', 'result_id', 'revision', 'error')
FULL_STEP_IDS = ('discover_data', 'prediction_time', 'feature_availability', 'split',
                 'success_criterion', 'train_eda', 'preprocessing', 'models', 'policy',
                 'conclusion')
FULL_REGRESSION_STEP_IDS = ('discover_data', 'prediction_time', 'feature_availability', 'split',
                            'success_criterion', 'train_eda', 'preprocessing', 'models',
                            'model_choice', 'conclusion')
DATA_PAYLOAD_KEYS = ('schema', 'ok', 'study', 'revision', 'observation_unit', 'development',
                     'target', 'final_test', 'groups', 'rows', 'note')
DATA_VARIABLE_KEYS = ('name', 'role', 'type', 'unit', 'description', 'description_fr',
                      'availability', 'decided', 'special_values', 'n_missing', 'n_distinct',
                      'examples')
PREPROCESSING_KEYS = ('missing', 'rare_category_min_rows', 'caps', 'log_transform')
CRITERION_VIEW_KEYS = ('decision_status', 'value', 'metric', 'status', 'result_id', 'rule',
                       'model', 'gain', 'low', 'high', 'minimum', 'unit',
                       'interval_includes_zero', 'verdict', 'contradicts_verdict',
                       # v0.2b (WP-B1): the criterion judged on the final test.
                       'final_test',
                       # B6c (H4): where the criterion is judged, and its status there.
                       'judged_on', 'judged_status')
EDA_LOOKS_KEYS = ('target_looks', 'results', 'by_activity', 'note')
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
                           # v0.2a (WP-A4).
                           14: 'preprocessing', 15: 'preprocessing.motivation',
                           16: 'success_criterion',
                           # v0.2b (WP-B1).
                           17: 'model_variant',
                           # Reliability roadmap J3: action objective/rule mutation.
                           18: 'success_criterion.selection', '*': 'unknown'}
NEXT_ACTION_KINDS = {'acknowledge_interruption', 'reconfirm', 'await_user_words', 'blocked',
                     'propose', 'run', 'done',
                     # Closure fix F1: a dead execution seen by the read-only lease probe.
                     'outcome_unknown',
                     # v0.2a (WP-A4, R2): step 0, informational.
                     'show_data_card'}
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
                          'conclusion_outdated', 'inconclusive_without_choice',
                          # v0.2a (WP-A4): an adopting verdict against the success criterion,
                          # a preprocessing motivated by a look at the target.
                          'verdict_contradicts_criterion', 'data_contingent_preprocessing',
                          # v0.2b (WP-B1): the final test sealed, its opening interrupted, a
                          # change after it.
                          'final_test_sealed', 'final_test_opening_interrupted',
                          'changed_after_final_test',
                          # B6c (H4): keeping the baseline against a criterion met on the
                          # final test.
                          'verdict_keeps_baseline_against_criterion'}
INVALIDATION_KEYS = ('revision', 'decision_id', 'mutation', 'row', 'reason', 'stale_results',
                     'stale_slots', 'reconfirm_required', 'effects', 'previous')
CONFIRM_INVALIDATION_KEYS = ('mutation', 'row', 'reason', 'stale_results', 'stale_slots',
                             'reconfirm_required')
EFFECT_KEYS = ('refit', 're_eda', 're_policy', 're_chart', 're_explain', 'reconfirm')
MUTATION_IDS = {1: 'prediction_time', 2: 'feature_availability.feature_set',
                3: 'feature_availability.wording', 4: 'split', 5: 'policy.parameter',
                6: 'policy.rule_type', 7: 'settings.bootstrap', 8: 'usage_label', 9: 'eda_added',
                10: 'conclusion', 11: 'code_fingerprint', 12: 'dataset',
                # WP-B2: explicit selected model in a binary study.
                13: 'model_choice',
                # v0.2a (WP-A4).
                14: 'preprocessing', 15: 'preprocessing.motivation', 16: 'success_criterion',
                # v0.2b (WP-B1).
                17: 'model_variant',
                # Reliability roadmap J3: action objective/rule mutation.
                18: 'success_criterion.selection', '*': 'unknown'}
ERROR_CODES = {
    'invalid_arguments', 'internal_error', 'invalid_request', 'idempotency_conflict',
    'stale_revision', 'invalid_command', 'study_missing', 'state_exists', 'integrity_error',
    'study_busy', 'platform_unsupported', 'invalid_case', 'confirmed_status_forbidden',
    'dataset_missing', 'dataset_changed', 'unsupported_capability', 'unknown_decision',
    'invalid_value', 'literal_number_in_text', 'ambiguous_confirmation', 'precondition_missing',
    'unknown_proposal', 'proposal_not_open', 'unknown_result', 'invalid_result', 'unknown_module',
    # Reliability roadmap J5: context-bound evidence references.
    'invalid_evidence_ref', 'unknown_evidence_result', 'invalid_evidence_path',
    'evidence_context_mismatch', 'evidence_integrity_error', 'evidence_not_current',
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
    'decision_on_hold', 'unknown_note', 'note_not_open', 'misattributed_delegation',
    # Advanced companion (CLI-CONTRACT-COMPANION §12, WP-E2): export handoff.
    'export_target_exists',
    # ADR 0005: a trade-off needs a reason (only in the training mode since v0.3, WP-B).
    'reason_required',
    # v0.2b (WP-B2): the training mode, a paraphrase on the proposal's concepts, and a
    # stop on words that contradict the value.
    'paraphrase_required', 'words_contradict_value',
    # WP-B1: the final test is opened once.
    'final_test_already_opened'}
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
                     'delegation_not_given_at_this_pause',
                     # ADR 0005 (guided mode): a question, a conditional agreement.
                     'question_reply', 'conditional_reply',
                     # v0.3 (WP-B): the final-test opening is never delegated (it was
                     # reason_required while a reason was mandatory).
                     'delegation_not_allowed'}
REGISTRY_ENTRY_KEYS = ('schema', 'result_id', 'input_key', 'activity', 'params', 'inputs', 'code',
                       'output', 'blobs', 'partition', 'n_rows', 'exposure_id', 'execution_id',
                       'started_revision', 'environment', 'created')
EXPOSURE_RECORD_KEYS = ('schema', 'exposure_id', 'revision', 'activity', 'result_id',
                        'execution_id', 'purpose', 'partition', 'n_rows', 'row_keys',
                        'dataset_sha256', 'columns', 'time')
EXPOSURE_PURPOSES = ('structural_inspection', 'train_eda', 'train_fit',
                     'validation_model_evaluation', 'validation_policy_selection',
                     # v0.2a (ADR 0006): the final-test rows set aside at init.
                     'sealed',
                     # v0.2b (WP-B1): cross-validation, the selection on out-of-fold
                     # predictions, the one evaluation of the final test.
                     'cross_validated_fit', 'out_of_fold_evaluation',
                     'out_of_fold_policy_selection', 'final_evaluation',
                     # v0.2b (WP-B4): the diagnostics of the development predictions.
                     'development_diagnostics', 'policy_exploration',
                     'labelled_preview_available')
EXPOSURE_PARTITIONS = ('all', 'train', 'validation', 'development', 'final_test')
FINAL_TEST_STATUS_KEYS = ('status', 'rows', 'method', 'fraction', 'development_rows',
                          'schema_check',
                          # v0.2b (WP-B1): the opening, and what changed after it.
                          'opening', 'post_final_test', 'changed_after',
                          # v0.2b (WP-B6a): rows kept out as already exposed.
                          'excluded_prior_exposed')
PARTITION_RECORD_KEYS = ('schema', 'status', 'method', 'fraction', 'seed', 'stratified_on',
                         'bins', 'order', 'dataset_sha256', 'n_rows', 'development',
                         'final_test', 'schema_check', 'created', 'implementation')
EXTENSIONS = {'run': 'mlkit.study.cmd_run', 'render': 'mlkit.study.cmd_render',
              'check': 'mlkit.study.cmd_check', 'preview': 'mlkit.study.cmd_preview',
              # Post-v0.1: read-only session timeline for observed sessions.
              'session-report': 'mlkit.study.cmd_session_report',
              # Advanced companion (CLI-CONTRACT-COMPANION §13): WP-0 stubs, then WP-E1/E2.
              'decisions': 'mlkit.study.cmd_decisions', 'evidence': 'mlkit.study.cmd_evidence',
              'explain': 'mlkit.study.cmd_explain', 'export': 'mlkit.study.cmd_export',
              # v0.2a (WP-A4, R2): the read-only data card.
              'data': 'mlkit.study.cmd_data',
              # ADR 0008: the opt-in understanding and handover review.
              'understanding': 'mlkit.study.cmd_understanding'}
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
                  'editable': 'notebooks/study_editable.py',
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
                  'misattributed_delegation': 'error',
                  # v0.2a (WP-A4).
                  'verdict_contradicts_criterion': 'warning',
                  # B6c (H4).
                  'verdict_keeps_baseline_against_criterion': 'warning',
                  'final_test_figure_outdated': 'error',
                  # Reliability roadmap J2: a completed non-inconclusive claim needs all
                  # derived validity requirements.
                  'validity_requirement_missing': 'error'}
LITERAL_KINDS = ('revision', 'ordinal', 'user_words', 'proposal', 'decision_value', 'case',
                 'identifier', 'parameter', 'environment', 'setting', 'message', 'category',
                 # v0.2a (WP-A6): state counts, the five example rows, chart axis ticks.
                 'structure', 'data_row', 'axis')
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
    assert [tuple(step) for step in payload['plan']] == [('id', 'title', 'status')] * len(
        B2_BINARY_STEP_IDS)
    # New binary studies choose the model and its policy separately; legacy B1 stays stable.
    assert tuple(payload['decisions']) == st.B2_DECISION_IDS == B2_DECISION_IDS
    assert all(tuple(d) == SUMMARY_DECISION_KEYS for d in payload['decisions'].values())
    assert tuple(payload['executions']) == EXECUTION_VIEW_KEYS
    assert tuple(payload['not_yet_defensible']) == ('top', 'more')
    assert view.RECAP_LABELS == RECAP_LABELS and len(payload['recap']) == len(RECAP_LABELS)
    assert [line.split(':', 1)[0] for line in payload['recap']] == list(RECAP_LABELS)
    assert tuple(payload['artifacts']) == ('status', 'items')
    for name, item in payload['artifacts']['items'].items():
        assert tuple(item) == SUMMARY_ARTIFACT_ITEM_KEYS, name
        assert item['audience'] in AUDIENCES and item['junior_message'], name
    assert all(tuple(x) == SUMMARY_LIMIT_KEYS and x['audience'] in AUDIENCES
               and (x['junior_text'] if x['audience'] == 'agent' else x['junior_text'] is None)
               for x in payload['not_yet_defensible']['top'])
    assert payload['recap_audience'] == 'agent' and len(payload['recap_junior']) == len(RECAP_LABELS)
    assert [line.split(':', 1)[0] for line in payload['recap_junior']] == list(RECAP_LABELS)
    assert {'audience', 'junior_message'} <= set(payload['next_action'])
    # WP-A7: the mode, and each launch's argument list (no interpreter, no shell form).
    assert payload['mode'] == 'guided'
    assert tuple(payload['deliverables']) == view.SUMMARY_DELIVERABLES_KEYS == ('launch',)
    assert tuple(payload['deliverables']['launch']) == ('notebook', 'editable', 'workbench')
    assert all(tuple(x) == view.SUMMARY_LAUNCH_KEYS == ('mode', 'path', 'argv')
               for x in payload['deliverables']['launch'].values())
    assert view.SUMMARY_NOTE_KEYS == SUMMARY_NOTE_KEYS
    assert view.SUMMARY_HOLD_KEYS == SUMMARY_HOLD_KEYS and payload['holds'] == []
    keys = ({SUMMARY_SCHEMA} | set(SUMMARY_PAYLOAD_KEYS) | set(SUMMARY_DECISION_KEYS)
            | set(SUMMARY_GOAL_KEYS) | {'top', 'more', 'message'} | set(RECAP_LABELS)
            | set(SUMMARY_NOTE_KEYS) | set(SUMMARY_HOLD_KEYS) | set(AUDIENCES)
            | set(FEATURE_BASES) | set(SUMMARY_ARTIFACT_ITEM_KEYS) | set(SUMMARY_LIMIT_KEYS)
            | set(DELIVERABLES_KEYS) | set(LAUNCH_KEYS) | set(NOTICE_KEYS))
    assert not sorted(k for k in keys if k not in DOC_TOKENS)


def test_view_model_keys(flow):
    v = flow['status'].payload['view']
    assert tuple(v) == VIEW_KEYS == view.VIEW_KEYS
    assert view.DECISION_VIEW_KEYS == DECISION_VIEW_KEYS
    assert view.CONFIRMATION_VIEW_KEYS == CONFIRMATION_VIEW_KEYS
    assert view.PROPOSAL_VIEW_KEYS == PROPOSAL_VIEW_KEYS
    assert view.RESULT_VIEW_KEYS == RESULT_VIEW_KEYS
    assert tuple(v['decisions']) == st.B2_DECISION_IDS
    assert all(tuple(d) == DECISION_VIEW_KEYS for d in v['decisions'].values())
    assert tuple(v['criterion']) == CRITERION_VIEW_KEYS
    assert tuple(v['eda_looks']) == EDA_LOOKS_KEYS
    conf = v['decisions']['prediction_time']['confirmation']
    assert tuple(conf) == CONFIRMATION_VIEW_KEYS and conf['authenticated'] is False
    # ADR 0005: "Yes, before the reminder." repeats the value, so it is recorded as restated.
    assert conf['basis'] == 'restated' and conf['delegation_scope'] is None
    assert conf['agent_concern'] is None
    assert v['mode'] == 'guided' and v['language'] == 'en'
    assert [tuple(p) for p in v['open_proposals']] in ([], [PROPOSAL_VIEW_KEYS])
    assert tuple(v['exposure']) == EXPOSURE_SUMMARY_KEYS
    assert tuple(v['artifacts']) == ARTIFACT_VIEW_KEYS
    assert tuple(v['facts']) == ('by_status', 'count')
    assert tuple(v['executions']) == EXECUTION_VIEW_KEYS
    assert (view.LIVENESS_RUNNING, view.LIVENESS_UNKNOWN, view.LIVENESS_NOT_CHECKED) \
        == LIVENESS_VALUES
    assert not [k for k in (*EXECUTION_VIEW_KEYS, *LIVENESS_VALUES, 'liveness')
                if k not in DOC_TOKENS]
    assert [s['id'] for s in v['plan']] == list(B2_BINARY_STEP_IDS)
    assert all(tuple(s) == STEP_KEYS for s in v['plan'])
    assert {'kind', 'message'} <= set(v['next_action'])
    assert {x['id'] for x in v['not_yet_defensible']} <= NOT_YET_DEFENSIBLE_IDS
    # v0.2a (WP-A1): every message carries its audience and a junior variant.
    assert v['next_action']['audience'] in AUDIENCES and v['next_action']['junior_message']
    assert all(x['audience'] in AUDIENCES and x['junior_text'] for x in v['not_yet_defensible'])
    assert all(i['audience'] in AUDIENCES and i['junior_message']
               for i in v['artifacts']['items'].values())
    assert tuple(v['deliverables']) == DELIVERABLES_KEYS
    assert all(tuple(x) == LAUNCH_KEYS for x in v['deliverables']['launch'].values())
    basis = v['decisions']['feature_availability']['feature_basis']
    assert basis is None or set(basis.values()) <= set(FEATURE_BASES)
    assert 'revision' in flow['status'].payload['changes_since'][0]


def test_next_action_kinds_and_not_yet_defensible_ids_in_source():
    source = (STUDY_PKG / 'state.py').read_text(encoding='utf-8')
    assert set(re.findall(r"'kind': '([a-z_]+)'", source)) == NEXT_ACTION_KINDS
    defensible = (inspect.getsource(st.not_yet_defensible) + inspect.getsource(view.build)
                  + inspect.getsource(view._small_data)
                  + inspect.getsource(view.small_partition_warning)
                  + inspect.getsource(view.capacity_warning)
                  + inspect.getsource(view._governance_limits))
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
    assert st.TOP_OPTIONAL_KEYS == ('task', 'notes', 'partition', 'mode', 'language',
                                    'mode_history', 'exploration', 'understanding')
    assert st.NOTE_KEYS == NOTE_STATE_KEYS and st.NOTE_RESOLUTION_KEYS == NOTE_RESOLUTION_KEYS
    assert st.NOTE_KINDS == ('hold', 'correction') and st.NOTE_STATUSES == NOTE_STATUSES
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
    # v0.3 (WP-B, R16): ``choice`` is a confirmation channel only.
    assert st.CONFIRMATION_CHANNELS == ('chat', 'cli', 'webview', 'choice')
    assert st.CONFIRMATION_BASES == CONFIRMATION_BASES and cmd.DEFAULT_BASIS == 'explicit'
    assert st.REQUEST_BASES == REQUEST_BASES
    assert st.CONFIRMATION_OPTIONAL_KEYS == ('basis', 'delegation_scope', 'agent_concern',
                                            'mode', 'warnings', 'reason_given',
                                            'adoption_question')
    assert {a: set(p) for a, p in cmd.OPTIONAL_PARAMS.items()} == OPTIONAL_ACTION_PARAMS
    assert not set(CONFIRMATION_BASES) - DOC_TOKENS
    assert st.DELEGATION_SCOPES == DELEGATION_SCOPES
    assert st.STANDING_DELEGATION_DECISIONS == STANDING_DELEGATION_DECISIONS
    assert st.EXPRESS_STANDING_DELEGATION_DECISIONS == EXPRESS_STANDING_DELEGATION_DECISIONS
    assert not (set(DELEGATION_SCOPES) | {'delegation_scope'}) - DOC_TOKENS
    assert '--delegation-scope this_decision|standing' in DOC
    assert st.DECISION_IDS == ('prediction_time', 'feature_availability', 'split', 'policy',
                               'conclusion')
    assert st.AVAILABILITY_DECISIONS == ('available_at_prediction', 'not_available',
                                         'uncertain_excluded', 'uncertain_included')
    assert pre.CONCLUSION_VERDICTS == ('adopt_policy', 'keep_baseline', 'inconclusive')


def test_wp_a4_contract_constants():
    """v0.2a (WP-A4): the decision sets and steps of a new study, the data card keys, the
    preprocessing and criterion shapes; every name is documented in CLI-CONTRACT.md."""
    from mlkit.study import activities as act, cmd_data, governance
    assert st.FULL_DECISION_IDS == FULL_DECISION_IDS
    assert st.FULL_REGRESSION_DECISION_IDS == FULL_REGRESSION_DECISION_IDS
    assert st.FULL_STEP_IDS == FULL_STEP_IDS and st.FULL_REGRESSION_STEP_IDS == FULL_REGRESSION_STEP_IDS
    assert st.STEP_IDS == STEP_IDS and st.DECISION_IDS[:3] == FULL_DECISION_IDS[:3]
    assert cmd_data.PAYLOAD_KEYS == DATA_PAYLOAD_KEYS
    assert cmd_data.VARIABLE_KEYS == DATA_VARIABLE_KEYS
    assert governance.PREPROCESSING_KEYS == PREPROCESSING_KEYS
    assert governance.DEFAULT_PREPROCESSING == {'missing': 'none', 'rare_category_min_rows': 0,
                                                'caps': {}, 'log_transform': []}
    assert governance.CRITERION_KEYS == {'binary': ('metric', 'min_points'),
                                         'regression': ('metric', 'min_share')}
    assert act.SHARED_ACTIVITIES == ('eda.distribution', 'eda.quality',
                                     'eda.single_feature_signal', 'eda.correlation')
    keys = (set(FULL_DECISION_IDS) | set(FULL_STEP_IDS) | set(DATA_PAYLOAD_KEYS)
            | set(DATA_VARIABLE_KEYS) | set(PREPROCESSING_KEYS) | set(CRITERION_VIEW_KEYS)
            | set(EDA_LOOKS_KEYS) | set(act.SHARED_ACTIVITIES)
            | {'show_data_card', 'default_value', 'motivated_by', 'data_contingent',
               'min_points', 'min_share', 'precision_gain', 'mae_reduction',
               'verdict_contradicts_criterion', 'data_contingent_preprocessing',
               'hypotrail.data/1', 'null_band', 'interval', 'question'})
    assert not sorted(k for k in keys if k not in DOC_TOKENS)


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
    # ``eda.distribution:`` reserved by WP-0 (CLI-CONTRACT-COMPANION §8, C8).
    assert st.PER_COLUMN_SLOT_PREFIXES == ('eda.rate_by:', 'eda.mean_by:', 'eda.distribution:')
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
    assert exposure.PARTITIONS == EXPOSURE_PARTITIONS
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
    # WP-A8: the data card's figures and the sealed counts are literals of a text check.
    assert {'cmd_check.data_card_figures', 'data_card', 'final_test'} <= DOC_TOKENS
    assert callable(cmd_check.data_card_figures)
    assert render_html.LITERAL_KINDS == LITERAL_KINDS
    assert cmd_render.FAULTS == ('render_html', 'render_notebook')
    assert (cmd_render.FAULT_ENV, cmd_render.HOOKS_ENV) == ('HYPOTRAIL_FAULT', 'HYPOTRAIL_TEST_HOOKS')
    assert [n for n, _ in _params(cmd_render.after_commit)] == ['study_dir', 'payload']
    keys = (set(PHASE3_SCHEMAS.values()) | set(CHECK_FINDINGS) | set(LITERAL_KINDS)
            | set(MANIFEST_ITEM_KEYS) | set(ARTIFACT_NAMES)
            | {k for keys in PHASE3_PAYLOAD_KEYS.values() for k in keys})
    assert not sorted(k for k in keys if k not in DOC_TOKENS)


def test_deliverable_file_currency_contract():
    """Review fix M4: the file reasons of a stale deliverable and the functions behind them."""
    from mlkit.study import currency
    assert currency.STALE_REASONS == ('file_missing', 'file_changed', 'revision_changed',
                                      'result_not_current')
    assert [n for n, _ in _params(currency.effective_status)] == ['item', 'state', 'is_current',
                                                                  'file']
    assert [n for n, _ in _params(currency.file_check)] == ['study_dir', 'item']
    tokens = {*currency.STALE_REASONS, 'stale_reason', 'currency.STALE_REASONS',
              'currency.file_check', 'edit_check_sha256', '__generated_with'}
    assert not sorted(t for t in tokens if t not in DOC_TOKENS)


def test_session_report_and_session_log_contract():
    from mlkit.study import cmd_session_report, sessionlog
    assert cmd_session_report.SCHEMA == SESSION_REPORT_SCHEMA
    assert cmd_session_report.PAYLOAD_KEYS == SESSION_REPORT_KEYS
    assert (sessionlog.SCHEMA, sessionlog.LOG_FILE, sessionlog.ENV) == tuple(SESSION_LOG.values())
    # v0.2a (WP-A4): the data card is read-only and never logged.
    assert sessionlog.UNLOGGED == ('session-report', 'export', 'data')
    # Reads (CLI-CONTRACT §8.6, CLI-CONTRACT-COMPANION R5): only status and check are logged,
    # when the log is on (owner decision at the companion integration).
    assert sessionlog.READ_COMMANDS == ('status', 'plan', 'preview', 'decisions', 'evidence',
                                        'explain', 'check')
    assert sessionlog.LOGGED_READS == ('status', 'check')
    assert {'sessionlog.READ_COMMANDS', 'sessionlog.LOGGED_READS',
            'sessionlog.UNLOGGED'} <= DOC_TOKENS
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


# Advanced companion (CLI-CONTRACT §8.7, CLI-CONTRACT-COMPANION; WP-I): the schema names of
# the new reads and the export, pinned here as CLI-CONTRACT-COMPANION §0 lists them.
COMPANION_SCHEMAS = {'decisions': 'hypotrail.decisions/1', 'preview_effects': 'hypotrail.preview_effects/1',
                     'proposal_draft': 'hypotrail.proposal_draft/1', 'evidence': 'hypotrail.evidence/1',
                     'explain': 'hypotrail.explain/1', 'export': 'hypotrail.export/1',
                     'handoff': 'hypotrail.handoff/1'}


def test_companion_schema_names():
    from mlkit.study import (cmd_decisions, cmd_evidence, cmd_explain, cmd_export, preview_effects,
                             preview_proposal)
    assert {'decisions': cmd_decisions.SCHEMA, 'preview_effects': preview_effects.SCHEMA,
            'proposal_draft': preview_proposal.SCHEMA, 'evidence': cmd_evidence.SCHEMA,
            'explain': cmd_explain.SCHEMA, 'export': cmd_export.SCHEMA,
            'handoff': cmd_export.HANDOFF_SCHEMA} == COMPANION_SCHEMAS
    section = DOC[DOC.index('### 8.7 Advanced companion'):DOC.index('## 9. Storage objects')]
    assert all(f'`{name}`' in section for name in COMPANION_SCHEMAS.values())
    for module in (cmd_decisions, cmd_evidence, cmd_explain, cmd_export, preview_effects, preview_proposal):
        assert not getattr(module, 'WP0_STUB', False), module.__name__


def test_final_test_partition_contract(tmp_path, synthetic_case_dir):
    """v0.2a (ADR 0006): the sealed final test's record, surfaces, and exposure keys."""
    from mlkit.study import exposure, partition
    assert exposure.PARTITIONS == EXPOSURE_PARTITIONS
    assert partition.RECORD_KEYS == PARTITION_RECORD_KEYS
    # WP-B1: the final test is opened once (optional record key ``opening``); WP-B3: the
    # optional ``groups`` of a case whose identical records are grouped.
    assert partition.STATUSES == ('sealed', 'opened') and partition.STATUS_ABSENT == 'absent'
    assert partition.OPTIONAL_RECORD_KEYS == ('groups', 'opening', 'prior_exposed',
                                              'training_exclusions', 'analysis_protocol')
    # WP-B6a: rows the case declares as already exposed, kept out of the final test; the
    # opening's time in the status view.
    assert partition.PRIOR_EXPOSED_KEYS == ('path', 'sha256', 'declared_rows', 'excluded_rows')
    assert partition.OPENING_VIEW_KEYS == ('revision', 'model', 'rule', 'result_id',
                                           'user_words', 'time')
    assert partition.OPENING_KEYS == ('revision', 'execution_id', 'proposal_id', 'user_words',
                                      'model', 'rule', 'time', 'result_id')
    assert partition.METHODS == ('stratified', 'quantile_stratified', 'temporal')
    assert (partition.DEFAULT_FRACTION, partition.DEFAULT_SEED) == (0.2, 0)
    study = tmp_path / 'study'
    init = _run('init', '--case', synthetic_case_dir, '--study', study).payload
    assert tuple(init['final_test']) == FINAL_TEST_STATUS_KEYS
    assert init['final_test']['status'] == 'sealed'
    v = _run('status', '--study', study).payload['view']
    assert tuple(v['final_test']) == FINAL_TEST_STATUS_KEYS
    assert tuple(_run('status', '--summary', '--study', study).payload['final_test']) == \
        FINAL_TEST_STATUS_KEYS
    assert init['final_test']['excluded_prior_exposed'] == 0   # the case declares none
def test_confirmation_modes_and_guided_rules_are_documented(tmp_path, synthetic_case_dir):
    """ADR 0005: modes, languages, ``mode set``, the guided reasons, ``reason_required`` and
    the ``words_contradict_value`` warning."""
    from mlkit.study import confirm as cf
    assert st.MODES == MODES and st.SUPPORTED_MODES == SUPPORTED_MODES
    assert st.DEFAULT_MODE == 'guided' and st.LANGUAGES == LANGUAGES
    assert st.DEFAULT_LANGUAGE == 'en' and st.MODE_CHANGE_KEYS == MODE_CHANGE_KEYS
    assert st.MODES_AVAILABLE_IN == {} and st.MODE_STRICTNESS == MODE_STRICTNESS
    # The model choice, policy, conclusion and final-test opening carry trade-offs.
    assert cf.REASON_DECISIONS == {'binary': ('model_choice', 'policy', 'conclusion',
                                              'final_test'),
                                   'regression': ('model_choice', 'conclusion', 'final_test')}
    assert cf.WORDS_CONTRADICT_VALUE == 'words_contradict_value'
    warning = cf.availability_warnings('exclude contact', {'contact': 'available_at_prediction'})
    assert [tuple(w) for w in warning] == [WARNING_KEYS]
    keys = (set(MODES) | set(LANGUAGES) | set(MODE_CHANGE_KEYS) | set(WARNING_KEYS)
            | set(CONFIRMATION_BASES) | {'mode_history', 'language', 'labels', 'label',
                                         'agent_concern', 'warnings', 'words_contradict_value',
                                         'reason_required', 'question_reply',
                                         'conditional_reply', 'correction', 'recorded',
                                         'study.set_mode', 'available_in', 'confirm.ENDORSEMENT',
                                         'confirm.availability_warnings', 'confirm.has_reason',
                                         # v0.2b (WP-B2).
                                         'paraphrase_required', 'missing', 'junior_message',
                                         'concepts.concept_map', 'concepts.check',
                                         'concepts.has_reason_connector',
                                         'concepts.mode_named', 'content/concepts.yaml',
                                         # v0.3 (WP-B).
                                         'reason_given', 'adoption_question', 'choice',
                                         'delegation_not_allowed', 'confirm.closed_affirmative',
                                         'state.CONFIRMATION_CHANNELS',
                                         'state.EXPRESS_STANDING_DELEGATION_DECISIONS',
                                         'state.MODE_STRICTNESS'})
    assert not sorted(k for k in keys if k not in DOC_TOKENS)
    for line in ('hypotrail mode set guided|training|express [--user-words TEXT]',
                 '[--channel chat|cli|webview|choice] [--adoption-question]',
                 '[--agent-concern TEXT]', '--proposal PROPOSAL', '[--kind hold|correction]',
                 '[--restatement-fr TEXT]', 'hypotrail init --case CASE --study DIR [--lang en|fr]'):
        assert line in DOC, line
    study = tmp_path / 'study'
    assert _run('init', '--case', synthetic_case_dir, '--study', study).exit_code == 0
    out = _run('mode', 'set', 'guided', '--user-words', 'I keep the guided mode.',
               '--request-id', 'm1', '--expected-revision', 1, '--study', study)
    assert out.exit_code == 0 and tuple(out.payload) == PAYLOAD_KEYS['decide']
    assert tuple(out.payload['result']) == ('mode', 'previous', 'user_words', 'changed')


def test_wp_b1_contract_constants():
    """v0.2b (WP-B1): the decision sets and steps of a new study, the evaluation schemes, the
    variant, the trial count, the opening; every name is documented in CLI-CONTRACT.md."""
    from mlkit.study import activities as act, governance, partition
    assert st.B1_DECISION_IDS == B1_DECISION_IDS
    assert st.B1_REGRESSION_DECISION_IDS == B1_REGRESSION_DECISION_IDS
    assert st.B2_DECISION_IDS == B2_DECISION_IDS
    assert st.B1_STEP_IDS == B1_STEP_IDS and st.WP_B1_DECISIONS == ('model_variant', 'final_test')
    assert st.B2_BINARY_STEP_IDS == B2_BINARY_STEP_IDS
    assert st.CV_METHODS == CV_METHODS and st.CV_KEYS == ('method', 'folds', 'seed')
    assert st.TEMPORAL_CV_KEYS == ('method', 'folds', 'gap')
    assert (st.DEFAULT_FOLDS, st.MIN_FOLDS, st.MAX_FOLDS) == (5, 3, 10)
    # v0.3 (WP-F1, ADR 0007): two more kinds, in a list of at most three variants.
    assert st.VARIANT_KINDS == ('regularisation', 'drop_group', 'tuned', 'family')
    assert st.VARIANT_STRENGTHS == ('weak', 'strong')
    assert act.B1_ACTIVITIES == ('fit.variant', 'final_test.evaluation')
    assert act.VARIANT_C == {'weak': 10.0, 'strong': 0.1}
    assert act.VARIANT_ALPHA == {'weak': 1.0, 'strong': 10.0}
    assert view.TRIALS_KEYS == TRIALS_KEYS and view.SUMMARY_TRIALS_KEYS == ('count',)
    assert cmd.OPENING_KEYS == OPENING_RESULT_KEYS
    assert cmd.FINAL_TEST_KEYS == ('model', 'rule')
    assert partition.STATUS_VIEW_KEYS == FINAL_TEST_STATUS_KEYS
    assert governance.FINAL_CRITERION_KEYS == (
        'status', 'gain', 'low', 'high', 'minimum', 'unit', 'interval_includes_zero',
        'result_id', 'point_meets_minimum', 'interval_excludes_zero',
        'lower_bound_meets_minimum', 'uncertainty_status', 'decision_rule',
        'decision_status', 'basis')
    assert rec.POLICY_MODELS == ('fit.logistic', 'fit.variant', 'fit.variant:2',
                                 'fit.variant:3')
    keys = (set(B1_DECISION_IDS) | set(B2_DECISION_IDS) | set(B1_STEP_IDS)
            | set(B2_BINARY_STEP_IDS) | set(CV_METHODS) | set(TRIALS_KEYS)
            | set(OPENING_RESULT_KEYS) | set(st.VARIANT_KINDS) | set(st.VARIANT_STRENGTHS)
            | set(act.B1_ACTIVITIES) | set(partition.OPENING_KEYS)
            | {'fit.variant', 'final_test.evaluation', 'comparisons', 'cross_validation',
               'out_of_fold', 'fold_rows', 'capacity_share', 'rule_final', 'post_final_test',
               'changed_after', 'opened', 'final_test_already_opened', 'drop_group',
               'state.has_wp_b1_decisions', 'records.canonical_policy',
               'data.load_final_test', 'activities.CAPABILITY_FOLDS'})
    assert not sorted(k for k in keys if k not in DOC_TOKENS)
    assert f'`{act.CAPABILITY_FOLDS}`' in DOC


def test_wp_f1_contract_constants():
    """v0.3 (WP-F1, ADR 0007): the variant budget, the slots of the variants, the grids of
    nested tuning, the model families, the selection and shortlist shapes, the linear checks;
    every name is documented in CLI-CONTRACT.md §14."""
    from mlkit.study import activities as act, case as c, diagnostics as dg, families, trials
    assert trials.MAX_VARIANTS == 3 and trials.VARIANT_SLOTS == (
        'fit.variant', 'fit.variant:2', 'fit.variant:3')
    assert act.VARIANT_SLOT_NAMES == ('fit.variant:2', 'fit.variant:3')
    assert set(act.VARIANT_SLOT_NAMES) <= set(act.CLI_NAMES)
    assert trials.KINDS == ('regularisation', 'drop_group', 'tuned', 'family')
    assert trials.FAMILIES == ('linear', 'ebm', 'hgb')
    assert trials.VARIANT_FAMILIES == ('ebm', 'hgb')
    assert trials.INTERPRETABILITY == ('required', 'preferred', 'none')
    assert trials.INNER_FOLDS == 3 and trials.INNER_SEED == 20261020
    assert {k: v['values'] for k, v in trials.GRIDS.items()} == {
        ('linear', 'binary'): (0.01, 0.1, 1.0, 10.0, 100.0),
        ('linear', 'regression'): (100.0, 10.0, 1.0, 0.1, 0.01),
        ('ebm', 'binary'): (0, 3), ('ebm', 'regression'): (0, 3),
        ('hgb', 'binary'): (2, 4), ('hgb', 'regression'): (2, 4)}
    assert trials.EBM_SETTINGS == {'outer_bags': 1, 'inner_bags': 0, 'max_rounds': 500,
                                   'learning_rate': 0.05, 'n_jobs': 1}
    assert trials.SELECTION_KEYS == ('available', 'metric', 'direction', 'folds',
                                     'configurations', 'best', 'one_se', 'optimism', 'advice',
                                     'budget', 'trials', 'note')
    assert trials.SHORTLIST_KEYS == ('constraints', 'evidence', 'families', 'shortlist',
                                     'recommendation', 'text', 'texts', 'data_contingent',
                                     'catalogue')
    assert dg.LINEAR_CHECK_KEYS == ('model', 'nonlinearity', 'interaction', 'calibration_slope',
                                    'flags', 'alpha', 'method', 'note')
    assert (dg.CHECK_BINS, dg.CHECK_ALPHA, dg.SLOPE_BAND) == (5, 0.01, (0.8, 1.2))
    assert c.CONSTRAINT_KEYS == ('interpretability',)
    keys = (set(trials.KINDS) | set(trials.FAMILIES) | set(trials.SELECTION_KEYS)
            | set(trials.CONFIGURATION_KEYS) | set(trials.SHORTLIST_KEYS)
            | set(dg.LINEAR_CHECK_KEYS) | set(trials.INTERPRETABILITY)
            | {'variant_index', 'variant_declared', 'inputs.trial_budget',
               'tuning', 'family_diagnostics', 'ebm_terms', 'permutation_importance',
               'gain_points_variants', 'run_diagnostics', 'stay_linear',
               'compare_nonlinear', 'fold_noise', 'budget_exhausted', 'may_continue',
               'no_variant', 'not_available', 'trials.select', 'trials.shortlist',
               'trials.selection', 'trials.draft', 'trials.used_specs', 'trials.changed_slots',
               'families.choose', 'families.ebm_terms', 'families.permutation_importance',
               'diagnostics.linear_checks', 'render_trials.section',
               'code_cells.selection_cell', 'recompute_selection', 'interpret._version',
               'state.default_variant', 'activities.resolve'})
    assert not sorted(k for k in keys if k not in DOC_TOKENS)
    assert all(f'`{slot}`' in DOC for slot in trials.VARIANT_SLOTS)
    assert families.MAX_SHAPE_POINTS == 40


def test_wp_b4_contract_constants():
    """v0.2b (WP-B4, R9): the diagnostics activities, their value shapes, their exposure, and
    the rule they follow; every name is documented in CLI-CONTRACT.md §13."""
    from mlkit.study import activities as act, diagnostics as dg, governance
    from mlkit.study import preconditions as pre
    assert act.DIAG_ACTIVITIES == {'binary': ('diag.binary', 'diag.final_test'),
                                   'regression': ('diag.regression', 'diag.final_test')}
    assert act.DEVELOPMENT_DIAGNOSTICS == ('diag.binary', 'diag.regression')
    for task in ('binary', 'regression'):
        assert act.task_activities(task)[-2:] == act.DIAG_ACTIVITIES[task]
    assert dg.DEVELOPMENT_PURPOSE == 'development_diagnostics' and \
        dg.FINAL_PURPOSE == 'final_evaluation'
    assert dg.EVIDENCE == ('development', 'final')
    assert dg.RULE_SOURCES == ('adopted', 'proposed', 'scenario_default', 'engine_default')
    assert dg.DEFAULT_RULE == 'share:0.1' and len(dg.CURVE_SHARES) == 20
    assert (dg.CALIBRATION_BINS, dg.MAX_SEGMENT_COLUMNS, dg.MAX_EXAMPLES,
            dg.SCATTER_POINTS) == (10, 2, 5, 150)
    # v0.3 (WP-J): Wald intervals from a sandwich covariance replace the 100-refit bootstrap.
    assert (dg.COEFFICIENT_INTERVALS, dg.COEFFICIENT_LEVEL) == ('wald_sandwich', 0.95)
    assert dg.COEFFICIENT_KEYS == ('terms', 'n_rows', 'level', 'penalty', 'point_check',
                                   'method', 'note')
    assert dg.COEFFICIENT_TERM_KEYS == ('term', 'value', 'low', 'high', 'std_error',
                                        'excludes_zero', 'inside_interval')
    assert dg.BINARY_KEYS == ('question', 'evidence', 'purpose', 'partition', 'evaluation', 'n',
                              'n_positive', 'base_rate', 'rule', 'rule_source',
                              'segment_columns', 'segment_rule', 'models', 'coefficient_rows',
                              'note', 'linear_checks')
    assert dg.REGRESSION_KEYS == ('question', 'evidence', 'purpose', 'partition', 'evaluation',
                                  'n', 'target', 'unit', 'residual_columns',
                                  'residual_definition', 'target_transform', 'smearing',
                                  'normality_note', 'models', 'coefficient_rows', 'note',
                                  'linear_checks')
    assert dg.BINARY_MODEL_KEYS == ('confusion', 'curve', 'roc_auc', 'average_precision',
                                    'calibration', 'segments', 'examples', 'coefficients',
                                    'predictions')
    assert dg.REGRESSION_MODEL_KEYS == ('errors', 'residuals', 'qq', 'by_prediction',
                                        'heteroscedasticity', 'by_feature', 'scatter',
                                        'examples', 'coefficients', 'predictions')
    assert pre.FINAL_DIAGNOSTICS == 'diag.final_test'
    assert set(act.DIAG_ACTIVITIES['binary'] + act.DIAG_ACTIVITIES['regression']) \
        <= set(governance.TARGET_ACTIVITIES)
    keys = (set(dg.BINARY_KEYS) | set(dg.REGRESSION_KEYS) | set(dg.FINAL_BINARY_KEYS)
            | set(dg.FINAL_REGRESSION_KEYS) | set(dg.BINARY_MODEL_KEYS)
            | set(dg.REGRESSION_MODEL_KEYS) | set(dg.RULE_SOURCES) | set(dg.EVIDENCE)
            | {'diag.binary', 'diag.regression', 'diag.final_test', 'development_diagnostics',
               'final_test_opened', 'activities.diagnostic_rule', 'diagnostics.DEFAULT_RULE',
               'diagnostics.calibration_bins', 'diagnostics.segment_columns',
               'diagnostics.residual_columns', 'code_cells.diagnostics_cell',
               'render_diagnostics.section', 'render_html.ANNEX_SKIPPED',
               'recompute_dev_diagnostics', 'recompute_final_diagnostics'})
    assert not sorted(k for k in keys if k not in DOC_TOKENS)


def test_review_v1_j1_j3_contract_constants():
    """The additive public schemas and enumerations introduced by reliability J1--J3."""
    from mlkit.study import evaluation_plan, objective, validity
    assert evaluation_plan.SCHEMA == 'hypotrail.evaluation_plan/1'
    assert evaluation_plan.INDEPENDENT_METHODS == (
        'kfold_stratified', 'kfold_quantile', 'group_disjoint')
    assert evaluation_plan.TEMPORAL_METHODS == (
        'forward_chaining', 'ordered_retrospective')
    assert evaluation_plan.METHODS == evaluation_plan.INDEPENDENT_METHODS \
        + evaluation_plan.TEMPORAL_METHODS
    assert validity.REQUIREMENT_CODES == (
        'scenario_bound', 'analysis_contract_present', 'feature_timing_supported',
        'evaluation_protocol_current', 'choice_evaluation_current',
        'selected_configuration_current', 'development_diagnostics_current',
        'interpretability_constraint_satisfied', 'uncertainty_available_for_claim',
        'final_evidence_current_for_configuration')
    assert objective.DECISION_RULES == ('point_estimate', 'lower_bound')
    assert objective.BINARY_METRICS == ('precision', 'recall')


def test_library_integration_v1_contract():
    """Library integration v1 (workstream A): the added activities, their place in the
    activity list, and the mapping of contract errors to frozen engine codes."""
    from mlkit.contracts import errors as cerr
    from mlkit.study import activities as act
    assert act.EXPORT_ACTIVITIES == ('predictor.capture', 'diagnostics.population')
    for task in ('binary', 'regression'):
        assert act.task_activities(task)[-4:-2] == act.EXPORT_ACTIVITIES
    assert set(cerr.ENGINE_CODES.values()) <= ERROR_CODES
    tokens = set(act.EXPORT_ACTIVITIES) | set(cerr.ENGINE_CODES) | {
        'contract_code', 'evidence_binding', 'engine_parity', 'semantic_dependencies',
        'evidently_snapshot', 'read_export_source', 'hypotrail.export_source/1'}
    assert not sorted(t for t in tokens if t not in DOC_TOKENS)


# --- ADR 0008: the understanding and handover review (CLI-CONTRACT §15) -----------------------

def test_understanding_contract_is_frozen():
    from mlkit.study import cmd_understanding as cu
    from mlkit.study.understanding import (CODES, DIMENSIONS, STATE_SCHEMA, canonical,
                                           evaluate, export, model, policy, snapshot,
                                           taskset, verify)
    assert cu.SCHEMA == 'hypotrail.understanding/1'
    assert STATE_SCHEMA == 'hypotrail.understanding-state/1'
    assert policy.SCHEMA == 'hypotrail.understanding-policy/1'
    assert taskset.SCHEMA == 'hypotrail.understanding-tasks/1'
    assert taskset.TASK_SCHEMA == 'hypotrail.understanding-task/1'
    assert export.SCHEMA == 'hypotrail.understanding-review/1'
    assert export.MANIFEST_SCHEMA == 'hypotrail.understanding-export-manifest/1'
    assert snapshot.PUBLIC_SCHEMA == 'hypotrail.public-source-scope/1'
    assert evaluate.GATE_SCHEMA == 'hypotrail.understanding-gate/1'
    assert verify.SCHEMA == 'hypotrail.understanding-verification/1'
    assert canonical.VERSION == 'hypotrail.canonical-json/1'
    assert DIMENSIONS == ('D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7', 'D8')
    assert policy.MODES == ('off', 'coaching', 'required')
    assert policy.MILESTONES == ('handoff',)
    assert policy.KEYS == ('schema', 'policy_id', 'version', 'mode', 'milestones',
                           'required_dimensions', 'responsibility_profiles',
                           'critical_dimensions', 'peer_required_dimensions',
                           'minimum_assurance', 'assistance_rule', 'expiration_rule',
                           'evidence_retention', 'evidence_requirement', 'context_requirement',
                           'export_policy', 'exemptions_policy', 'team_coverage', 'role_policy')
    assert model.DIMENSION_STATUSES == ('not_evaluated', 'demonstrated', 'to_consolidate',
                                        'needs_review')
    assert evaluate.DECISIONS == ('not_applicable', 'allowed', 'blocked', 'allowed_by_waiver')
    assert CODES == ('understanding_disabled', 'policy_invalid', 'unsupported_assurance',
                     'stale_revision', 'idempotency_conflict', 'invalid_transition',
                     'context_changed', 'unsupported_case', 'prerequisite_missing',
                     'evidence_invalid', 'review_required', 'privacy_approval_required',
                     'evidence_unavailable', 'path_outside_scope', 'git_index_conflict',
                     'export_stale', 'milestone_blocked', 'unsupported_capability')
    assert export.FILES == ('understanding-review.json', 'understanding-review.md',
                            'export-manifest.json')
    assert export.EXPORT_DIR == 'docs/understanding'
    assert cu.STUDY_OPTIONAL == ('verify-export',)
    assert sorted(cu.HANDLERS) == sorted([
        'policy show', 'policy set', 'plan', 'start', 'status', 'task', 'submit', 'coach',
        'rectify', 'propose-review', 'review', 'arbitrate', 'select', 'waive', 'handover set',
        'transfer start', 'transfer submit', 'transfer review', 'close', 'check',
        'export preview', 'export approve', 'export write', 'git-plan', 'git-stage',
        'git-receipt', 'relocate'])
    # Round 2 (C2-1): `relocate` records a declared move, so --author and --reason are
    # required (checked before any study is opened).
    out = cli.run(['understanding', 'relocate', '--session', 's', '--repo', '/x', '--study',
                   '/nonexistent-study', '--request-id', 'r', '--expected-revision', '0'])
    assert out.exit_code == 2 and out.payload['error']['code'] == 'invalid_arguments'
    assert '--author' in out.payload['error']['message']
    assert '--reason' in out.payload['error']['message']

