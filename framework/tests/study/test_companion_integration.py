"""Engine follow-ups of the advanced companion's integration (WP-I; decisions CI.6 to CI.9).

* The proposal's stored ``origin`` is the last key of ``open_proposals`` in the view
  (``status --json``), so the report, which renders from the view, says "Proposed from the
  companion" for a webview proposal; ``status --summary`` without ``--digest`` is unchanged.
* The EDA catalog of ``evidence`` lists exactly the EDA activities of
  ``activities.task_activities(task)``, in plan order, so it cannot drift from ``run``.
* The ``distribution`` and ``class_imbalance`` glossary terms exist; ``eda.distribution``
  names its own term.
* A refusal of ``export handoff`` names the command with its verb.

Scope S (real CLI code path, in-process ``cli.run``), on temporary synthetic studies.
"""
from __future__ import annotations

import pytest

import companion_contract as cc
import flowkit as fk
from mlkit.study import activities as act, cmd_evidence, state as st, texts, view


@pytest.fixture(scope='module')
def binary(tmp_path_factory, synthetic_case_dir):
    return cc.binary_study(synthetic_case_dir, tmp_path_factory.mktemp('wpi') / 'study')


@pytest.fixture
def clone(binary, tmp_path):
    return fk.Flow(fk.clone(binary.study, tmp_path / 'study'), binary.case_dir, prefix='i')


def test_origin_is_the_last_key_of_open_proposals_and_the_report_says_so(clone):
    before = clone.view()['open_proposals']
    assert [tuple(p) for p in before] == [view.PROPOSAL_VIEW_KEYS] * len(before)
    assert before[-1]['origin'] == {'channel': 'chat'}
    out = clone.call('decide', 'propose', 'policy', '--value', cc.POLICY_RULE, '--restatement',
                     'You decide the policy as stated.', '--rationale', 'Chosen in the panel.',
                     '--channel', 'webview', '--request-id', clone.rid(), '--expected-revision',
                     clone.rev(), '--study', clone.study)
    pid = out['result']['proposal_id']
    proposals = {p['proposal_id']: p for p in clone.view()['open_proposals']}
    assert list(proposals[pid])[-1] == 'origin' and proposals[pid]['origin'] == {'channel': 'webview'}
    # The summary without --digest keeps its v0.1 shape: no origin there.
    summary = clone.call('status', '--summary', '--study', clone.study)
    assert all('origin' not in p for p in summary['open_proposals'])
    rendered = clone.call('render', '--study', clone.study, expect=None)
    assert rendered['ok'] is True
    html = (clone.study / 'reports' / 'study.html').read_text(encoding='utf-8')
    assert 'data-origin="webview"' in html and 'Proposed from the companion' in html


@pytest.mark.parametrize('task', st.TASKS)
def test_the_eda_catalog_is_the_eda_activities_of_the_task(task):
    expected = tuple(a for a in act.task_activities(task) if a in act.EDA)
    assert cmd_evidence.EDA_CATALOG[task] == expected
    assert act.DISTRIBUTION in expected, 'the shared activity is offered to both tasks'
    assert set(cmd_evidence.PER_COLUMN_ROLES) == set(act.PER_COLUMN)
    assert cmd_evidence.PER_COLUMN_ROLES[act.DISTRIBUTION] == act.DISTRIBUTION_ROLES


def test_the_live_catalog_matches_task_activities(binary):
    code, payload = cc.run('evidence', '--study', binary.study)
    assert code == 0, payload
    listed = tuple(a['activity'] for a in payload['eda_catalog']['activities'])
    assert listed == tuple(a for a in act.task_activities('binary') if a in act.EDA)


@pytest.mark.parametrize('task', st.TASKS)
def test_distribution_has_its_own_glossary_term(task):
    term = texts.glossary('distribution', task)
    assert term and term['term'] == 'Distribution'
    assert not any(ch.isdigit() for ch in term['definition'])
    assert texts.activity('eda.distribution', task)['glossary'] == 'distribution'
    assert (texts.glossary('class_imbalance', task) is not None) == (task == 'binary')


def test_an_export_refusal_names_the_command_with_its_verb(binary, tmp_path):
    taken = tmp_path / 'taken'
    taken.mkdir()
    (taken / 'note.txt').write_text('mine\n')
    code, payload = cc.run('export', 'handoff', '--out', taken, '--study', binary.study)
    assert code == 2 and payload['command'] == 'export handoff'
    assert cc.refusal(payload)[0] == 'export_target_exists'
    assert (taken / 'note.txt').read_text() == 'mine\n'
