# Contract tests of the advanced companion, WP-E3 part (C4, C8, C10 anchors). Written by
# WP-0. WP-E3 removes the ``E3`` markers of this file only, and deletes
# ``test_wp0_stub_refuses_until_e3``, whose stub it replaces. Nothing else changes here
# without the integrator (docs/plans/COMPANION-ADVANCED-PLAN.md §2.1).
"""CLI-CONTRACT-COMPANION C4 (``preview proposal``), C8 (``eda.distribution:<column>``),
and the report anchors of C10.

WP-E3 has landed: its strict ``xfail`` markers are removed and its stub test deleted.
"""
from __future__ import annotations

import re

import pytest

import companion_contract as cc
import flowkit as fk
from mlkit.study import read

@pytest.fixture(scope='module')
def binary(tmp_path_factory, synthetic_case_dir):
    return cc.binary_study(synthetic_case_dir, tmp_path_factory.mktemp('cc-e3') / 'study')


@pytest.fixture
def clone(binary, tmp_path):
    return fk.Flow(fk.clone(binary.study, tmp_path / 'study'), binary.case_dir, prefix='k')


def test_distribution_slot_prefix_is_reserved():
    from mlkit.study import state as st
    assert 'eda.distribution:' in st.PER_COLUMN_SLOT_PREFIXES


# --- C4 ------------------------------------------------------------------------------------

def test_c4_draft_of_an_evaluated_rule_is_proposable(clone):
    pid = cc.open_proposal(clone, 'policy')
    before = cc.study_tree_digest(clone.study)
    code, p = cc.run('preview', 'proposal', 'policy', '--value', cc.POLICY_RULE,
                     '--study', clone.study)
    assert code == 0, p
    assert cc.study_tree_digest(clone.study) == before
    assert tuple(p) == cc.DRAFT_KEYS and p['schema'] == cc.DRAFT_SCHEMA
    assert p['decision_id'] == 'policy' and p['value'] == cc.POLICY_RULE
    assert p['proposable'] is True and p['missing'] == []
    assert isinstance(p['restatement'], str) and isinstance(p['rationale'], str)
    assert 'recommended default' not in p['restatement']
    assert tuple(p['evidence']) == cc.DRAFT_EVIDENCE_KEYS
    assert p['evidence']['result_id'] == read.open(clone.study).state['current'][
        'policy.evaluation']
    assert all(tuple(f) == cc.DRAFT_FIGURE_KEYS for f in p['evidence']['figures'])
    assert p['supersedes_proposal'] == pid
    assert p['recorded'] is False and p['note'] == cc.DRAFT_NOTE
    code, proposed = cc.run('decide', 'propose', 'policy', f'--value={cc.POLICY_RULE}',
                            f'--restatement={p["restatement"]}', f'--rationale={p["rationale"]}',
                            '--request-id', 'cc-draft', '--expected-revision', p['revision'],
                            '--study', clone.study)
    assert code == 0, proposed


def test_c4_unevaluated_rule_and_refusals(binary, tmp_path):
    code, p = cc.run('preview', 'proposal', 'policy', '--value', cc.UNEVALUATED_RULE,
                     '--study', binary.study)
    assert code == 0, p
    assert p['proposable'] is False and p['restatement'] is None and p['rationale'] is None
    assert p['missing'] == [{'requirement': 'evaluated_rule', 'value': cc.UNEVALUATED_RULE}]
    code, p = cc.run('preview', 'proposal', 'split', '--value', 'x', '--study', binary.study)
    assert code == 2 and cc.refusal(p)[0] == 'unsupported_capability', p
    assert {'capability', 'decisions'} <= set(cc.refusal(p)[1])
    code, p = cc.run('preview', 'proposal', 'model_choice', '--value', 'fit.linear',
                     '--study', binary.study)
    assert code == 2 and cc.refusal(p)[0] == 'unknown_decision', p
    code, p = cc.run('preview', 'proposal', 'policy', '--value', 'capacity:none',
                     '--study', binary.study)
    assert code == 2 and cc.refusal(p)[0] == 'invalid_value', p
    regression = cc.regression_study(tmp_path / 'rcase', tmp_path / 'rstudy')
    code, p = cc.run('preview', 'proposal', 'policy', '--value', cc.POLICY_RULE,
                     '--study', regression)
    assert code == 2 and cc.refusal(p)[0] == 'unknown_decision', p


def test_c4_reads_are_read_only(binary, tmp_path):
    study = fk.clone(binary.study, tmp_path / 'ro study')
    code, payload = cc.r1_read_only(study, 'preview', 'proposal', 'policy', '--value',
                                    cc.POLICY_RULE)
    assert code == 0 and payload['ok'] is True, payload
    assert not {'pandas', 'sklearn', 'scipy'} & set(
        cc.r3_imported(study, 'preview', 'proposal', 'policy', '--value', cc.POLICY_RULE))


# --- C8 ------------------------------------------------------------------------------------

def test_c8_numeric_distribution_reads_training_rows_only(clone):
    p = clone.run('eda.distribution', '--column', cc.NUMERIC_COLUMN)
    assert p['status'] == 'promoted', p
    assert p['result']['slot'] == f'eda.distribution:{cc.NUMERIC_COLUMN}'
    study = read.open(clone.study)
    entry = study.result(p['result']['result_id'])
    assert entry['activity'] == 'eda.distribution'
    assert entry['params']['column'] == cc.NUMERIC_COLUMN and entry['partition'] == 'train'
    values = entry['output']['values']
    assert tuple(values) == cc.DISTRIBUTION_VALUE_KEYS
    assert values['partition'] == 'train' and values['kind'] == 'numeric'
    assert values['note'] == cc.DISTRIBUTION_NOTE
    numeric = values['numeric']
    assert tuple(numeric) == cc.DISTRIBUTION_NUMERIC_KEYS and numeric['n_bins'] == 10
    assert all(tuple(b) == cc.DISTRIBUTION_BIN_KEYS for b in numeric['bins'])
    assert [b['closed'] for b in numeric['bins']] == ['left'] * 9 + ['both']
    special = sum(s['n_rows'] for s in values['special_values'])
    assert sum(b['n_rows'] for b in numeric['bins']) == values['n_rows'] - values['n_missing'] \
        - special
    record = [r for r in study.exposure_records() if r['result_id'] == entry['result_id']]
    assert [(r['purpose'], r['partition'], r['columns']) for r in record] == [
        ('train_eda', 'train', [cc.NUMERIC_COLUMN])]


def test_c8_special_values_categorical_groups_and_refusals(clone):
    p = clone.run('eda.distribution', '--column', cc.SPECIAL_COLUMN)
    values = read.open(clone.study).result(p['result']['result_id'])['output']['values']
    assert [s['value'] for s in values['special_values']] == [-1]
    assert all(tuple(s) == cc.DISTRIBUTION_SPECIAL_KEYS for s in values['special_values'])
    p = clone.run('eda.distribution', '--column', cc.CATEGORICAL_COLUMN)
    values = read.open(clone.study).result(p['result']['result_id'])['output']['values']
    assert values['kind'] == 'categorical' and values['numeric'] is None
    assert all(tuple(g) == cc.DISTRIBUTION_GROUP_KEYS for g in values['groups'])
    p = clone.run('eda.distribution', '--column', 'no_such_column', expect=2)
    assert cc.refusal(p)[0] == 'invalid_arguments' and 'columns' in cc.refusal(p)[1]


# --- C10 anchors ---------------------------------------------------------------------------

def test_c10_report_anchors_one_per_cited_result_and_no_editor_links(clone):
    code, p = cc.run('render', '--study', clone.study)
    assert code == 0, p
    html = (clone.study / 'reports' / 'study.html').read_text(encoding='utf-8')
    cited = set(re.findall(r'data-result-id="([0-9a-f]{64})"', html))
    assert cited
    for rid in cited:
        assert html.count(f'id="r-{rid}"') == 1, rid
    assert 'vscode:' not in html and 'command:' not in html
