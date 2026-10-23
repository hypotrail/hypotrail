# Contract helpers of the advanced companion: WP-0 writes them, only the integrator
# changes them (docs/plans/COMPANION-ADVANCED-PLAN.md §2.1).
"""Frozen key lists and study builders of ``docs/specs/CLI-CONTRACT-COMPANION.md`` (CC).

The three contract files ``test_contract_companion_e{1,2,3}.py`` import this module. The
key lists are those of CC, in emitted order. The client's fixtures
(``clients/vscode-companion/test/fixtures/contract-keys.json``) carry the same lists;
``clients/vscode-companion/test/test_contract_keys.py`` checks that they agree.

Studies are built in temporary directories from the synthetic case
(``framework/tests/fixtures/synthetic/make_case.py``), through ``cli.run`` (the same code
path as the CLI) and, where a test needs a real process, through ``flowkit.hyp``.
"""
from __future__ import annotations

import hashlib
import json
import stat
import subprocess
import sys
from pathlib import Path

from mlkit.study import cli

import flowkit as fk

# --- C1 (CC §1) --------------------------------------------------------------------------
SUMMARY_KEYS = ('schema', 'ok', 'study', 'revision', 'since', 'changed', 'goal', 'current_step',
                'plan', 'next_action', 'open_proposals', 'decisions', 'results', 'artifacts',
                'executions', 'not_yet_defensible', 'notes', 'holds',
                # v0.2a (ADR 0006): the sealed final test, before the recap.
                'final_test',
                # v0.2a (WP-A4): the success criterion and the target-look count.
                'criterion', 'eda_looks', 'recap',
                # v0.2a (WP-A1, CLI-CONTRACT §3): additive keys after ``recap``.
                'recap_audience', 'recap_junior',
                # v0.2a (WP-A7): the confirmation mode and the notebook launch commands.
                'mode', 'deliverables',
                # v0.2b (WP-B1): the trial count.
                'trials',
                # v0.2b (WP-B6a): the scenario defaults, values only.
                'scenario_defaults',
                # v0.3 (WP-E2, R21): the study language.
                'language')
# With ``--digest`` only: four keys after ``recap`` (CC §1), then ``task`` (integrator
# decision CA.3, ADR 0004 open question 7), then ``currency`` (review fix H1, CC §1.5).
# Without ``--digest`` the summary is unchanged.
DIGEST_SUMMARY_KEYS = SUMMARY_KEYS + ('moments', 'pauses', 'last_session', 'digest', 'task',
                                      'currency')
CURRENCY_HEX = 16
CURRENCY_INPUT_KEYS = ('revision', 'sources', 'artifacts', 'sources_changed', 'alerts',
                       'next_action', 'executions', 'results')
MOMENT_KEYS = ('id', 'title', 'steps')
MOMENTS = (('frame', 'Frame the change'), ('evidence', 'Prepare evidence'),
           ('compare', 'Work and compare'), ('conclude', 'Conclude and hand over'))
# v0.2a (WP-A4): step 0 and the success criterion frame the change; the preprocessing is
# prepared with the evidence. A moment lists only the steps of its study.
# WP-B1: the variant is compared with the models, the final test opened before concluding.
MOMENT_STEPS = {
    'binary': (('discover_data', 'prediction_time', 'feature_availability', 'split',
                'success_criterion'), ('train_eda', 'preprocessing'),
               ('models', 'model_variant', 'policy'), ('final_test', 'conclusion')),
    'regression': (('discover_data', 'prediction_time', 'feature_availability', 'split',
                    'success_criterion'), ('train_eda', 'preprocessing'),
                   ('models', 'model_variant', 'model_choice'), ('final_test', 'conclusion')),
}
PAUSE_KEYS = ('pause', 'decisions', 'status', 'confirmed')
LAST_SESSION_KEYS = ('boundary_revision', 'boundary_time', 'gap_minutes')
DIGEST_KEYS = ('since', 'until', 'items', 'truncated', 'counts',
               'channel_actions')          # v0.3 (WP-J, R35)
DIGEST_ITEM_KEYS = ('revision', 'time', 'action', 'kind', 'decision_id', 'proposal_id', 'note_id',
                    'activity', 'slot', 'result_id', 'execution_id', 'rules', 'column', 'channel',
                    'basis', 'delegation_scope', 'superseded', 'invalidation', 'text',
                    # v0.2a (WP-A7): the audience of ``text`` and its junior variant.
                    'audience', 'junior_text')
DIGEST_KINDS = ('proposed', 'confirmed', 'withdrawn', 'hold_recorded', 'hold_resolved',
                'result_added', 'result_replaced', 'run_failed', 'run_interrupted',
                'interruption_acknowledged', 'other')
DIGEST_INVALIDATION_KEYS = ('mutation', 'row', 'stale_slots', 'reconfirm_required', 'refit',
                            'kept_fits')
DIGEST_COUNT_KEYS = ('proposed', 'confirmed', 'withdrawn', 'holds_recorded', 'holds_resolved',
                     'results_added', 'results_replaced', 'runs_started', 'runs_failed',
                     'invalidations')
SESSION_GAP_MINUTES = 20
DIGEST_MAX_ITEMS = 50

# --- C2 (CC §2) --------------------------------------------------------------------------
DECISIONS_SCHEMA = 'hypotrail.decisions/1'
DECISIONS_KEYS = ('schema', 'ok', 'study', 'revision', 'task', 'decisions', 'proposals',
                  'history', 'reconfirm_queue', 'notes')
DECISIONS_ITEM_KEYS = ('decision_id', 'title', 'pause', 'step', 'status', 'value', 'depends_on',
                       'reason', 'confirmation', 'open_proposals')
DECISIONS_PROPOSAL_KEYS = ('proposal_id', 'decision_id', 'value', 'restatement', 'rationale',
                           'status', 'revision', 'created', 'closed_revision', 'closed_reason',
                           'origin')
DECISIONS_HISTORY_KEYS = ('revision', 'time', 'decision_id', 'proposal_id', 'value', 'user_words',
                          'basis', 'delegation_scope', 'channel', 'actor', 'current',
                          'superseded_at')
RECONFIRM_QUEUE_KEYS = ('decision_id', 'reason', 'since_revision', 'previous', 'open_proposal')
RECONFIRM_PREVIOUS_KEYS = ('value', 'user_words', 'basis', 'channel')

# --- C3 (CC §3) --------------------------------------------------------------------------
PREVIEW_EFFECTS_SCHEMA = 'hypotrail.preview_effects/1'
PREVIEW_EFFECTS_KEYS = ('schema', 'ok', 'study', 'revision', 'proposal_id', 'decision_id', 'value',
                        'previous', 'mutation', 'row', 'reason', 'stale_results', 'stale_slots',
                        'kept_slots', 'refit', 're_eda', 're_policy', 'recompute',
                        'reconfirm_required', 'supersedes_proposal', 'blocked', 'artifacts_after',
                        'notes', 'recorded', 'note')
PREVIEW_EFFECTS_PREVIOUS_KEYS = ('value', 'user_words', 'basis', 'channel', 'revision',
                                 'proposal_id')
PREVIEW_EFFECTS_BLOCKED_KEYS = ('code', 'reason', 'message', 'details')
PREVIEW_EFFECTS_NOTE = ('Preview of a confirmation: nothing was recorded. The engine still checks '
                        'the words when you confirm.')
# The part of a confirmation's ``result.invalidation`` the preview must equal (CC §3).
PREVIEW_EQUALS_INVALIDATION = ('mutation', 'row', 'reason', 'stale_results', 'stale_slots',
                               'reconfirm_required')
ARTIFACTS_AFTER = {'report': 'regenerated', 'notebook': 'regenerated',
                   'editable': 'synced_if_unedited', 'workbench': 'unchanged'}

# --- C4 (CC §4) --------------------------------------------------------------------------
DRAFT_SCHEMA = 'hypotrail.proposal_draft/1'
DRAFT_KEYS = ('schema', 'ok', 'study', 'revision', 'decision_id', 'value', 'proposable', 'missing',
              'restatement', 'rationale', 'evidence', 'supersedes_proposal', 'recorded', 'note')
DRAFT_EVIDENCE_KEYS = ('result_id', 'activity', 'figures')
DRAFT_FIGURE_KEYS = ('path', 'value', 'shown')
DRAFT_NOTE = 'Draft only: nothing was recorded. Proposing creates a proposal, not a decision.'

# --- C5 (CC §5) --------------------------------------------------------------------------
EVIDENCE_SCHEMA = 'hypotrail.evidence/1'
EVIDENCE_KEYS = ('schema', 'ok', 'study', 'revision', 'task', 'results', 'truncated', 'lineage',
                 'exposure', 'impacts', 'eda_catalog', 'sources', 'detail')
EVIDENCE_RESULT_KEYS = ('result_id', 'activity', 'slot', 'promoted', 'current', 'stale_reason',
                        'integrity', 'partition', 'n_rows', 'params', 'upstream', 'downstream',
                        'created', 'started_revision', 'execution_id', 'exposure_id', 'values',
                        'headline')
SEGMENT_KEYS = ('text',)
CITED_SEGMENT_KEYS = ('text', 'result_id', 'path', 'value', 'format')
LINEAGE_KEYS = ('nodes', 'edges')
LINEAGE_NODE_KEYS = ('id', 'kind', 'label', 'status')
LINEAGE_EDGE_KEYS = ('from', 'to', 'role')
LINEAGE_NODE_KINDS = ('source', 'decision', 'result', 'artifact')
LINEAGE_NODE_STATUSES = ('ok', 'changed', 'current', 'stale', 'confirmed', 'reconfirm_required',
                         'not_rendered', 'failed')
EXPOSURE_KEYS = ('summary', 'records', 'ledger', 'prior_exposure')
EXPOSURE_RECORD_VIEW_KEYS = ('exposure_id', 'revision', 'time', 'activity', 'result_id',
                             'execution_id', 'purpose', 'partition', 'n_rows', 'columns')
LEDGER_KEYS = ('purpose', 'partition', 'rows', 'records', 'activities', 'first_revision',
               'last_revision')
IMPACT_KEYS = ('decision_id', 'mutation', 'row', 'change', 'stale_slots', 'kept_slots', 'refit',
               'reconfirm', 'notes')
EDA_CATALOG_KEYS = ('activities',)
EDA_CATALOG_ITEM_KEYS = ('activity', 'per_column', 'columns', 'runnable', 'missing', 'partition')
EDA_CATALOG_COLUMN_KEYS = ('name', 'role', 'type', 'slot', 'result_id')
EDA_CATALOG_ACTIVITIES = {
    'binary': ('eda.target_rate', 'eda.special_values', 'eda.rate_by', 'eda.distribution',
               'eda.quality', 'eda.single_feature_signal', 'eda.correlation'),
    'regression': ('eda.target_summary', 'eda.special_values', 'eda.mean_by', 'eda.distribution',
                   'eda.quality', 'eda.single_feature_signal', 'eda.correlation'),
}
SOURCES_KEYS = ('case', 'dataset')
SOURCE_KEYS = ('path', 'sha256', 'matches')
DETAIL_KEYS = ('result_id', 'values', 'params', 'inputs', 'code', 'environment', 'blobs',
               'exposure', 'consumers', 'report_anchor', 'notebook_hint')
DETAIL_CODE_KEYS = ('fingerprint', 'modules')
NOTEBOOK_HINT_KEYS = ('path', 'search')

# --- C6 (CC §6) --------------------------------------------------------------------------
EXPLAIN_SCHEMA = 'hypotrail.explain/1'
EXPLAIN_KEYS = ('schema', 'ok', 'study', 'revision', 'task', 'terms', 'steps', 'predictions')
EXPLAIN_TERM_KEYS = ('id', 'term', 'definition', 'example', 'example_status', 'steps')
EXAMPLE_STATUSES = ('shown', 'needs_results', 'none')
EXPLAIN_STEP_KEYS = ('concept', 'context', 'method', 'interpretation', 'consequence',
                     'text_status')
EXPLAIN_PREDICTION_KEYS = ('id', 'step', 'question', 'choices', 'reveal', 'available')
EXPLAIN_CHOICE_KEYS = ('id', 'label')

# --- C7 (CC §7) --------------------------------------------------------------------------
EXPORT_SCHEMA = 'hypotrail.export/1'
HANDOFF_SCHEMA = 'hypotrail.handoff/1'
EXPORT_KEYS = ('schema', 'ok', 'study', 'revision', 'kind', 'out', 'files', 'included_report',
               'warnings')
EXPORT_FILE_KEYS = ('path', 'sha256', 'bytes')
HANDOFF_KEYS = ('schema', 'study', 'revision', 'task', 'case', 'dataset', 'goal', 'decisions',
                'results_cited', 'exposure', 'not_yet_defensible', 'open_items', 'deliverables',
                'reproduce', 'environment', 'history')
HANDOFF_CITED_KEYS = ('result_id', 'activity', 'path', 'value', 'shown')
EXPORT_WARNINGS = ('report_not_current', 'open_proposals', 'open_holds', 'interrupted_executions',
                   'sources_changed', 'unconfirmed_decisions')
EXPORT_FILES = ('handoff.md', 'handoff.json', 'study.html', 'SHA256SUMS')

# --- C8 (CC §8) --------------------------------------------------------------------------
DISTRIBUTION_VALUE_KEYS = ('partition', 'column', 'role', 'type', 'kind', 'n_rows', 'n_missing',
                           'special_values', 'numeric', 'groups', 'n_groups', 'max_groups',
                           'other', 'min_group_rows', 'warnings', 'note',
                           # v0.2a (WP-A4): the question every analysis answers.
                           'question')
DISTRIBUTION_KINDS = ('numeric', 'discrete', 'categorical')
DISTRIBUTION_NUMERIC_KEYS = ('n', 'min', 'q25', 'median', 'q75', 'max', 'mean', 'sd', 'n_bins',
                             'bin_width', 'bins',
                             # v0.3 (WP-E2, R17): the exact zeros and the log bins of a skewed column.
                             'zeros', 'skewed', 'log_bins')
DISTRIBUTION_BIN_KEYS = ('low', 'high', 'n_rows', 'share', 'closed')
DISTRIBUTION_GROUP_KEYS = ('value', 'n_rows', 'share', 'small_count')
DISTRIBUTION_SPECIAL_KEYS = ('value', 'meaning', 'n_rows', 'share')
DISTRIBUTION_NOTE = ('Counts of training rows only. A distribution describes this sample; it is '
                     'not a rate of the outcome and says nothing about causes.')

# --- C9, C10 (CC §9, §10) ----------------------------------------------------------------
ORIGIN_KEYS = ('channel',)
CHECK_LOCATION_KEYS = ('path', 'anchor', 'line')

# --- C12 and §13: the new error code and the WP-0 stubs -------------------------------------
NEW_ERROR_CODES = ('export_target_exists',)
NOT_IMPLEMENTED = 'not_implemented'

# Synthetic-case columns used by the tests (make_case.py): a numeric feature, a feature
# with a special value, a categorical feature.
NUMERIC_COLUMN, SPECIAL_COLUMN, CATEGORICAL_COLUMN = ('member_age', 'days_since_last_lapse',
                                                      'home_branch')
POLICY_RULE = 'capacity:20'
UNEVALUATED_RULE = 'capacity:21'


def run(*argv):
    """``(exit code, payload)`` of one in-process CLI invocation."""
    outcome = cli.run([str(a) for a in argv])
    json.dumps(outcome.payload)
    return outcome.exit_code, outcome.payload


def refusal(payload: dict) -> tuple:
    error = payload.get('error') or {}
    return error.get('code'), (error.get('details') or {})


def not_implemented(payload: dict, command: str) -> bool:
    """True when ``payload`` is the WP-0 stub refusal of ``command`` (CC §13)."""
    code, details = refusal(payload)
    return (payload.get('ok') is False and code == 'unsupported_capability'
            and details == {'command': command, 'reason': NOT_IMPLEMENTED})


def binary_study(case_dir: Path, study: Path) -> fk.Flow:
    """A binary study with the three pauses confirmed, the split, the target rate and the
    special values, both fits, ``policy.evaluate --rule capacity:20``, and one **open**
    policy proposal of ``capacity:20`` (proposed with ``chat``, no ``--channel``)."""
    flow = fk.Flow(study, case_dir, prefix='cc')
    flow.init()
    flow.pauses()
    for activity in ('split', 'eda.target_rate', 'eda.special_values', 'fit.baseline',
                     'fit.logistic'):
        flow.run(activity)
    flow.variant()
    flow.decide('model_choice', 'fit.logistic')
    flow.run('policy.evaluate', '--rule', POLICY_RULE)
    flow.call('decide', 'propose', 'policy', '--value', POLICY_RULE, '--restatement',
              'You decide the policy as stated.', '--rationale', 'It fits the scenario.',
              '--request-id', flow.rid(), '--expected-revision', flow.rev(),
              '--study', flow.study)
    return flow


def open_proposal(flow: fk.Flow, decision_id: str) -> str:
    view = flow.view()
    ids = [p['proposal_id'] for p in view['open_proposals'] if p['decision_id'] == decision_id]
    assert ids, view['open_proposals']
    return ids[-1]


def regression_study(work: Path, study: Path) -> Path:
    """A freshly initialised study on the synthetic regression case."""
    case = fk.make_case(work, task='regression')['case']
    code, payload = run('init', '--case', case, '--study', study)
    assert code == 0, payload
    return study


def study_tree_digest(study: Path) -> dict:
    """sha256 of every file under the study folder (R1: a read writes nothing)."""
    study = Path(study)
    return {str(p.relative_to(study)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(study.rglob('*')) if p.is_file()}


def read_only_tree(study: Path):
    """Make the whole study tree read-only (``chmod -R a-w``); returns an undo function."""
    modes = {}
    for p in [Path(study), *Path(study).rglob('*')]:
        modes[p] = p.stat().st_mode
    for p in sorted(modes, key=lambda x: len(x.parts), reverse=True):
        p.chmod(modes[p] & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))

    def undo():
        for p in sorted(modes, key=lambda x: len(x.parts)):
            p.chmod(modes[p])
    return undo


def r1_read_only(study: Path, *argv) -> tuple[int, dict]:
    """R1: run ``argv`` as a real process under ``HYPOTRAIL_READ_ONLY=1`` on a read-only
    tree, and assert that no byte of the study changed. Returns ``(exit code, payload)``."""
    before = study_tree_digest(study)
    undo = read_only_tree(study)
    try:
        code, payload = fk.hyp(*argv, '--study', study, cwd=Path(study).parent,
                               extra_env={'HYPOTRAIL_READ_ONLY': '1'})
    finally:
        undo()
    assert study_tree_digest(study) == before, argv
    return code, payload


HEAVY_MODULES = ('pandas', 'sklearn', 'scipy', 'numpy')


def r3_imported(study: Path, *argv) -> list[str]:
    """R3: the heavy modules present in ``sys.modules`` after running ``argv`` in a fresh
    interpreter (in process, through ``cli.run``). The test asserts which are absent."""
    code = ('import json, sys\n'
            'from mlkit.study import cli\n'
            f'outcome = cli.run({[str(a) for a in argv] + ["--study", str(study)]!r})\n'
            'assert outcome.payload.get("ok") is True, outcome.payload\n'
            f'print(json.dumps(sorted(m for m in {HEAVY_MODULES!r} if m in sys.modules)))\n')
    proc = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                          cwd=Path(study).parent, env=fk.env(), timeout=120)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


def is_hex64(value) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef'
                                                               for c in value)


def summary_golden_text(study: Path) -> str:
    """The exact stdout of ``status --summary --json`` (a real process), with the absolute
    study path replaced by ``<study>``: the golden output of the C1 freeze."""
    proc = subprocess.run([sys.executable, '-m', 'mlkit.study.cli', 'status', '--summary',
                           '--json', '--study', str(study)], capture_output=True, text=True,
                          cwd=Path(study).parent, env=fk.env(), timeout=120)
    assert proc.returncode == 0 and proc.stderr == '', proc.stderr
    # WP-A7: the summary's ``deliverables`` name the engine's checkout (its Python and its
    # uv project), which differs between checkouts: it reads ``<engine>``.
    from mlkit.study import launch
    engine = json.dumps(str(launch.framework_dir().parent))[1:-1]
    return proc.stdout.replace(json.dumps(str(study))[1:-1], '<study>').replace(engine, '<engine>')



GOLDEN_SUMMARY = Path(__file__).resolve().parent / 'golden' / 'summary_synthetic.json'


def golden_study(root: Path) -> Path:
    """The study of the C1 freeze: the synthetic binary case of 300 rows, prediction time
    confirmed, and an open feature-availability proposal (no clock value is shown)."""
    case = fk.make_case(Path(root) / 'case', n_rows=300)['case'].parent
    flow = fk.Flow(Path(root) / 'study', case, prefix='g')
    flow.init()
    flow.decide('prediction_time', 'before the first contact of the campaign')
    flow.call('decide', 'propose', 'feature_availability', '--value-json',
              json.dumps(fk.availability(case)), '--restatement',
              'You decide the feature_availability as stated.', '--rationale', 'It fits.',
              '--request-id', 'g-open', '--expected-revision', flow.rev(), '--study', flow.study)
    return flow.study
