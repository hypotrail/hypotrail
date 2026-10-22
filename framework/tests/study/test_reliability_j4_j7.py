"""Bounded regression corpus for reliability-roadmap J4--J7.

These deterministic cases are independent contracts, not a claim that every possible
leakage pattern or misleading statement is detected.
"""
from __future__ import annotations

import copy

import pytest

from mlkit.study import (cite, code_compat, evidence_ref, read, render_notebook,
                         statements, view)
from mlkit.study.errors import StudyError

from flowkit import Flow, make_case, prepare


def test_exact_compatibility_is_directed_scoped_and_not_transitive():
    a, b, c = ('a' * 64, 'b' * 64, 'c' * 64)
    records = (
        {'module': 'm', 'from_sha256': a, 'to_sha256': b, 'activities': ['fit.x'],
         'reason': 'display-only change', 'evidence': ['test::one']},
        {'module': 'm', 'from_sha256': b, 'to_sha256': c, 'activities': ['fit.x'],
         'reason': 'another display-only change', 'evidence': ['test::two']},
    )
    assert code_compat.integrity(records)
    assert code_compat.equivalent('m', a, b, 'fit.x', records)
    assert not code_compat.equivalent('m', a, c, 'fit.x', records)
    assert not code_compat.equivalent('m', a, b, 'fit.y', records)
    assert not code_compat.equivalent('m', a, b, None, records)


def test_policy_inspection_records_every_consultation_without_refit(tmp_path):
    case = make_case(tmp_path / 'case', n_rows=120)['case'].parent
    study = prepare(case, tmp_path / 'study')
    flow = Flow(study, case, prefix='inspect')
    before = read.open(study).state
    fits = {slot: before['current'][slot] for slot in ('fit.baseline', 'fit.logistic')}
    one = flow.run('policy.inspect', '--rule', 'share:0.1', '--rule', 'threshold:0.5')
    two = flow.run('policy.inspect', '--rule', 'share:0.1', '--rule', 'threshold:0.5')
    state = read.open(study).state
    events = list(state['exploration']['events'].values())
    assert one['status'] == two['status'] == 'promoted'
    assert len(events) == 2 and sum(e['query_count'] for e in events) == 4
    assert {e['status'] for e in events} == {'completed'}
    assert {slot: state['current'][slot] for slot in fits} == fits
    assert state['current']['policy.inspection'] == two['result_id']
    assert read.open(study).current('policy.inspection')['output']['values']['mode'] == 'inspection'


def test_labelled_preview_and_unrecorded_surface_contract(tmp_path):
    case = make_case(tmp_path / 'case', n_rows=100)['case'].parent
    flow = Flow(tmp_path / 'study', case)
    flow.init()
    study = read.open(flow.study)
    labelled = [e for e in study.exposure_records()
                if e['purpose'] == 'labelled_preview_available']
    assert len(labelled) == 1 and labelled[0]['n_rows'] == 5
    assurance = view.build(study)['assurance']
    assert assurance['exploration_coverage'] == 'instrumented_operations_only'
    assert assurance['unrecorded_surfaces'] == ['preview', 'workbench', 'external_files']


def test_context_bound_reference_and_formatting(tmp_path):
    case = make_case(tmp_path / 'case', n_rows=120)['case'].parent
    study_path = prepare(case, tmp_path / 'study')
    flow = Flow(study_path, case, prefix='evidence')
    out = flow.run('policy.inspect', '--rule', 'share:0.1')
    study = read.open(study_path)
    path = 'rules.[share:0.1].models.[fit.logistic].precision'
    ref = evidence_ref.make(study, out['result_id'], path)
    assert evidence_ref.resolve(study, ref) == study.current('policy.inspection')[
        'output']['values']['rules']['share:0.1']['models']['fit.logistic']['precision']
    wrong = copy.deepcopy(ref)
    wrong['rule'] = 'share:0.2'
    with pytest.raises(StudyError, match='rule') as error:
        evidence_ref.resolve(study, wrong)
    assert error.value.code == 'evidence_context_mismatch'
    assert cite.format_value(.353, 'fraction', 'en') == '35.3%'
    assert cite.format_value(.353, 'fraction', 'fr') == '35,3\u00a0%'
    assert cite.format_value(.05, 'fraction_difference', 'en') == '5 percentage points'
    assert cite.format_value(.05, 'fraction_difference', 'fr') == '5 points de pourcentage'
    assert cite.format_value(37062, 'integer', 'en') == '37,062'
    assert cite.format_value(37062, 'integer', 'fr') == '37\u202f062'
    assert cite.format_value(None, 'fraction', 'en') == \
        'undefined: no selected observations'
    with pytest.raises(StudyError, match='Causal wording'):
        statements.render(study, {'kind': 'next_action',
                                  'text': 'This policy prevents cancellations.'})


def test_pause_and_presentation_snapshot_and_notebook_guard(tmp_path):
    case = make_case(tmp_path / 'case', n_rows=100)['case'].parent
    flow = Flow(tmp_path / 'study', case)
    flow.init()
    built = view.build(flow.study)
    pause = built['next_action']['pause']
    assert pause['schema'] == 'hypotrail.pause/1'
    assert pause['kind'] == 'action' and pause['proposal_id'] is None
    assert built['presentation']['revision'] == built['revision']
    assert built['presentation']['pending_action'] == pause
    source = render_notebook.generate_study_source(built)
    # No substantive registered recomputation can execute on notebook open.
    if 'Run registered recomputations' in source:
        assert 'mo.stop(not run_recompute.value' in source
