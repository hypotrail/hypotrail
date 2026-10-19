# Contract tests of the advanced companion, WP-E1 part (C1, C2, C3, C9). Written by WP-0;
# WP-E1 removed its ``E1`` markers and the WP-0 stub test it replaced. Nothing else changes
# here without the integrator (docs/plans/COMPANION-ADVANCED-PLAN.md §2.1).
"""CLI-CONTRACT-COMPANION C1 (``status --summary --digest``), C2 (``decisions``), C3
(``preview effects``), C9 (``decide propose --channel``), with R1 and R3.

WP-E1 implemented C1, C2, C3, and C9, so these tests are no longer marked ``xfail``. The
first three were permanent from WP-0: ``status --summary`` without ``--digest`` is
byte-identical to its golden output, ``--digest`` requires ``--summary``, and a request
recorded before C9 replays.
"""
from __future__ import annotations

import json
import os

import pytest

import companion_contract as cc
import flowkit as fk
from mlkit.study import read


@pytest.fixture(scope='module')
def binary(tmp_path_factory, synthetic_case_dir):
    return cc.binary_study(synthetic_case_dir, tmp_path_factory.mktemp('cc-e1') / 'study')


@pytest.fixture
def clone(binary, tmp_path):
    return fk.Flow(fk.clone(binary.study, tmp_path / 'study'), binary.case_dir, prefix='k')


# --- permanent since WP-0 --------------------------------------------------------------------

def test_digest_requires_summary(binary):
    code, payload = cc.run('status', '--digest', '--study', binary.study)
    assert code == 2 and cc.refusal(payload)[0] == 'invalid_arguments', payload


def test_summary_without_digest_is_byte_identical_to_its_golden_output(tmp_path):
    """CC §1: without ``--digest``, ``status --summary`` does not change by one byte."""
    text = cc.summary_golden_text(cc.golden_study(tmp_path))
    if os.environ.get('HYPOTRAIL_REGENERATE_GOLDEN') == '1':
        cc.GOLDEN_SUMMARY.write_text(text, encoding='utf-8')
        pytest.fail(f'regenerated {cc.GOLDEN_SUMMARY}: review the diff and commit it')
    assert text == cc.GOLDEN_SUMMARY.read_text(encoding='utf-8')
    assert tuple(json.loads(text)) == cc.SUMMARY_KEYS


def test_a_request_recorded_before_c9_replays(clone):
    """C9: ``channel`` is passed only when it is not ``chat``, so an earlier request id
    replays (with or without ``--channel chat``) instead of becoming a conflict."""
    rev = clone.rev()
    argv = ('decide', 'propose', 'policy', '--value', cc.POLICY_RULE, '--restatement',
            'You decide the policy again as stated.', '--rationale', 'It fits.',
            '--request-id', 'pre-c9', '--expected-revision', rev, '--study', clone.study)
    code, first = cc.run(*argv)
    assert code == 0 and first['replayed'] is False, first
    for extra in ((), ('--channel', 'chat')):
        code, again = cc.run(*argv, *extra)
        assert code == 0 and again['replayed'] is True, again
        assert again['revision'] == first['revision']


# --- C1 ------------------------------------------------------------------------------------

def test_c1_digest_keys_moments_pauses_and_last_session(binary):
    code, p = cc.run('status', '--summary', '--digest', '--study', binary.study)
    assert code == 0, p
    assert tuple(p) == cc.DIGEST_SUMMARY_KEYS
    assert p['task'] == 'binary'
    assert [tuple(m) for m in p['moments']] == [cc.MOMENT_KEYS] * 4
    assert [(m['id'], m['title']) for m in p['moments']] == list(cc.MOMENTS)
    assert [tuple(m['steps']) for m in p['moments']] == list(cc.MOMENT_STEPS['binary'])
    assert [tuple(x) for x in p['pauses']] == [cc.PAUSE_KEYS] * 3
    assert [x['pause'] for x in p['pauses']] == [1, 2, 3]
    assert p['pauses'][0]['decisions'] == ['prediction_time', 'feature_availability']
    # WP-A4: the split pause also holds the success criterion and the preprocessing.
    assert p['pauses'][1]['decisions'] == ['split', 'success_criterion', 'preprocessing']
    assert p['pauses'][2]['decisions'] == ['policy', 'conclusion']
    assert [x['status'] for x in p['pauses']] == ['closed', 'closed', 'open']
    assert tuple(p['last_session']) == cc.LAST_SESSION_KEYS
    digest = p['digest']
    assert tuple(digest) == cc.DIGEST_KEYS
    assert tuple(digest['counts']) == cc.DIGEST_COUNT_KEYS
    assert digest['until'] == p['revision']
    assert digest['since'] == p['last_session']['boundary_revision']
    assert digest['items'], digest
    for item in digest['items']:
        assert tuple(item) == cc.DIGEST_ITEM_KEYS
        assert item['kind'] in cc.DIGEST_KINDS
        assert isinstance(item['text'], str) and item['text']
        assert item['action'] != 'run.reserve'
        if item['invalidation'] is not None:
            assert tuple(item['invalidation']) == cc.DIGEST_INVALIDATION_KEYS
    assert [i['revision'] for i in digest['items']] == sorted(i['revision']
                                                             for i in digest['items'])
    pids = [o['proposal_id'] for o in p['open_proposals']]
    assert pids and all(tuple(o)[-1] == 'origin' for o in p['open_proposals'])


def test_c1_since_bounds(binary):
    rev = binary.rev()
    code, p = cc.run('status', '--summary', '--digest', '--since', rev, '--study', binary.study)
    assert code == 0 and p['digest']['items'] == [] and p['digest']['since'] == rev, p
    code, p = cc.run('status', '--summary', '--digest', '--since', 0, '--study', binary.study)
    assert code == 0 and p['digest']['since'] == 0, p
    for bad in (-1, rev + 1):
        code, p = cc.run('status', '--summary', '--digest', '--since', bad, '--study',
                         binary.study)
        assert code == 2 and cc.refusal(p)[0] == 'invalid_arguments', p


# --- R1, R3 (C1, C2, C3) -----------------------------------------------------------------

def test_e1_reads_are_read_only_and_import_no_heavy_module(binary, tmp_path):
    study = fk.clone(binary.study, tmp_path / 'ro study')
    pid = cc.open_proposal(fk.Flow(study, binary.case_dir), 'policy')
    for argv in (('status', '--summary', '--digest'), ('decisions',), ('preview', 'effects', pid)):
        code, payload = cc.r1_read_only(study, *argv)
        assert code == 0 and payload['ok'] is True, (argv, payload)
    for argv in (('status', '--summary', '--digest'), ('decisions',)):
        assert cc.r3_imported(study, *argv) == [], argv
    # C3 may not import numpy either (CC R3: C1, C2, C3, C5 and C6).
    assert cc.r3_imported(study, 'preview', 'effects', pid) == []


# --- C2 ------------------------------------------------------------------------------------

def test_c2_decisions_keys(binary):
    code, p = cc.run('decisions', '--study', binary.study)
    assert code == 0, p
    assert tuple(p) == cc.DECISIONS_KEYS and p['schema'] == cc.DECISIONS_SCHEMA
    assert p['task'] == 'binary'
    assert [d['decision_id'] for d in p['decisions']] == ['prediction_time',
                                                          'feature_availability', 'split',
                                                          'success_criterion', 'preprocessing',
                                                          'policy', 'conclusion']
    for d in p['decisions']:
        assert tuple(d) == cc.DECISIONS_ITEM_KEYS
    for item in p['proposals']:
        assert tuple(item) == cc.DECISIONS_PROPOSAL_KEYS
        assert item['origin'] is None or tuple(item['origin']) == cc.ORIGIN_KEYS
    assert [h['decision_id'] for h in p['history']] == ['prediction_time',
                                                        'feature_availability', 'split',
                                                        'success_criterion', 'preprocessing']
    for h in p['history']:
        assert tuple(h) == cc.DECISIONS_HISTORY_KEYS
        assert h['current'] is True and h['superseded_at'] is None
        # ADR 0005: own words repeating the proposal are recorded as restated (was explicit).
        assert h['basis'] == 'restated' and h['channel'] == 'chat'
    assert p['reconfirm_queue'] == []
    assert p['notes'] == []


# --- C3 ------------------------------------------------------------------------------------

def test_c3_preview_effects_keys_and_equality_with_the_confirmation(clone):
    pid = cc.open_proposal(clone, 'policy')
    before = cc.study_tree_digest(clone.study)
    code, p = cc.run('preview', 'effects', pid, '--study', clone.study)
    assert code == 0, p
    assert cc.study_tree_digest(clone.study) == before
    assert tuple(p) == cc.PREVIEW_EFFECTS_KEYS and p['schema'] == cc.PREVIEW_EFFECTS_SCHEMA
    assert p['proposal_id'] == pid and p['decision_id'] == 'policy'
    assert p['previous'] is None and p['mutation'] == 'first_confirmation' and p['row'] is None
    assert p['blocked'] == [] and p['recorded'] is False
    assert p['note'] == cc.PREVIEW_EFFECTS_NOTE
    assert p['artifacts_after'] == cc.ARTIFACTS_AFTER
    assert {'fit.baseline', 'fit.logistic'} <= set(p['kept_slots'])
    rev = clone.rev()
    code, confirmed = cc.run('decide', 'confirm', pid, '--user-words',
                             'Yes, I want the policy exactly as you stated it',
                             '--request-id', 'cc-confirm', '--expected-revision', rev,
                             '--study', clone.study)
    assert code in (0, 3), confirmed
    invalidation = confirmed['result']['invalidation']
    assert {k: p[k] for k in cc.PREVIEW_EQUALS_INVALIDATION} == {
        k: invalidation[k] for k in cc.PREVIEW_EQUALS_INVALIDATION}


def test_c3_refusals(binary):
    code, p = cc.run('preview', 'effects', 'p_999', '--study', binary.study)
    assert code == 2 and cc.refusal(p)[0] == 'unknown_proposal', p
    closed = [x['proposal_id'] for x in read.open(binary.study).state['proposals'].values()
              if x['status'] != 'open']
    code, p = cc.run('preview', 'effects', closed[0], '--study', binary.study)
    assert code == 2 and cc.refusal(p)[0] == 'proposal_not_open', p
    assert 'status' in cc.refusal(p)[1]
    code, p = cc.run('preview', 'effects', '--study', binary.study)
    assert code == 2 and cc.refusal(p)[0] == 'invalid_arguments', p


# --- C9 ------------------------------------------------------------------------------------

def test_c9_channel_webview_stores_the_origin(clone):
    rev = clone.rev()
    code, p = cc.run('decide', 'propose', 'policy', '--value', cc.POLICY_RULE, '--restatement',
                     'You decide the policy as stated, from the panel.', '--rationale',
                     'Chosen in the panel.', '--channel', 'webview', '--request-id', 'cc-web',
                     '--expected-revision', rev, '--study', clone.study)
    assert code == 0, p
    pid = p['result']['proposal_id']
    assert read.open(clone.study).state['proposals'][pid]['origin'] == {'channel': 'webview'}
    code, d = cc.run('decisions', '--study', clone.study)
    assert code == 0 and {x['proposal_id']: x['origin'] for x in d['proposals']}[pid] == {
        'channel': 'webview'}
    code, s = cc.run('status', '--summary', '--digest', '--study', clone.study)
    assert code == 0 and {x['proposal_id']: x['origin'] for x in s['open_proposals']}[pid] == {
        'channel': 'webview'}
    # Without --digest the summary is unchanged: no ``origin`` key (integrator CA.4).
    code, plain = cc.run('status', '--summary', '--study', clone.study)
    assert all('origin' not in x for x in plain['open_proposals'])
    code, bad = cc.run('decide', 'propose', 'policy', '--value', cc.POLICY_RULE, '--restatement',
                       'You decide the policy as stated.', '--rationale', 'It fits.',
                       '--channel', 'pigeon', '--request-id', 'cc-bad',
                       '--expected-revision', clone.rev(), '--study', clone.study)
    assert code == 2 and cc.refusal(bad) == ('invalid_value', {**cc.refusal(bad)[1],
                                                               'field': 'channel'}), bad

