"""Spec L-05, L-09, L-10 / AC07, AC09, AC23, AC24: capture before the final test opens.

A temporary synthetic study is taken to its chosen configuration; ``predictor.capture``
fits the complete predictor on the development rows, checks it against the engine's fit,
writes and reloads its bundle; the final test then scores the reloaded capture. Packaging is
exercised with the test-only synthetic packager (``HYPOTRAIL_TEST_HOOKS=1``).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

import flowkit as fk
from hypotrail_runtime import load_predictor, verify_bundle
from hypotrail_runtime.errors import ContractError
from mlkit.study import activities as act, case as c, data as dt, fit, read, registry
from mlkit.study import state as st, store as sto

import libkit

OPEN_WORDS = 'Yes, I open the final test now, because the model and the rule are fixed'


def _chosen(tmp_path, task='binary'):
    flow = libkit.study_at_fits(tmp_path, task=task)
    flow.run('fit.baseline')
    flow.run('fit.linear' if task == 'regression' else 'fit.logistic')
    flow.variant()
    if task == 'binary':
        flow.run('policy.evaluate', '--rule', 'capacity:40')
        flow.decide('policy', 'capacity:40',
                    words='Yes, I adopt that rule because the desk can make that many calls')
    else:
        flow.run('evaluate.regression')
        flow.decide('model_choice', 'fit.linear',
                    words='Yes, I choose that model because its error is smaller')
    return flow


def _open(flow, expect=0):
    value = st.b1_default_value(flow.state(), 'final_test')
    p = flow.call('decide', 'propose', 'final_test', '--value-json', json.dumps(value),
                  '--restatement', 'You open the sealed final test once, for the chosen '
                                   'configuration.', '--rationale', 'Everything is chosen.',
                  '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                  '--study', flow.study, expect=None)
    return flow.call('decide', 'confirm', p['result']['proposal_id'], '--user-words',
                     OPEN_WORDS, '--request-id', flow.rid(), '--expected-revision',
                     flow.rev(), '--study', flow.study, expect=expect)


def _home(flow) -> Path:
    return Path(flow.study) / '.hypotrail'


@pytest.mark.parametrize('task', ['binary', 'regression'])
def test_final_test_scores_the_reloaded_capture(tmp_path, task):
    flow = _chosen(tmp_path, task)
    run = flow.run('predictor.capture')
    v = run['values']
    bundle = _home(flow) / v['bundle']
    desc = verify_bundle(bundle)
    assert desc.predictor_id == v['predictor_id']
    assert v['engine_parity']['status'] == v['parity']['status'] == 'ok'
    assert v['training_scope']['role'] == 'final_development_refit'
    assert not st.final_test_opened(flow.state())          # captured before the opening
    # AC24: no final-test row, no target, no study database in the bundle.
    case = c.load_case(flow.case_dir)
    final_keys = set(fk.partition_keys(flow.study, 'final_test'))
    parity = json.loads((bundle / 'parity/features.json').read_bytes())
    names = [col['name'] for col in parity['columns']]
    assert case.target_column not in names
    assert parity['n_rows'] <= 50
    files = {p.relative_to(bundle).as_posix() for p in bundle.rglob('*') if p.is_file()}
    assert not any(f.endswith(('state.json', '.sqlite', '.db')) for f in files)
    assert {'bundle.json', 'predictor.json', 'recipe.json', 'data_contract.json',
            'payload/model.pkl', 'environment/requirements.lock'} <= files
    assert any(f.startswith('runtime/hypotrail_runtime-') and f.endswith('.whl') for f in files)
    # The opening scores the capture, not a new fit.
    out = _open(flow)
    assert out['result']['opening']['status'] == 'promoted', out['result']['opening']
    s = read.open(flow.study)
    final = s.result(s.state['current'][act.FINAL])
    assert final['output']['values']['predictor']['predictor_id'] == v['predictor_id']
    assert final['inputs']['predictor']['result_id'] == run['result_id']
    preds = act.read_predictions(sto.StudyStore(flow.study), final['result_id'])
    assert set(preds['row_keys']) == final_keys
    development = dt.load_development(case, fk.partition_keys(flow.study, 'development')).frame
    frame = dt.load_final_test(case, sorted(final_keys)).frame
    expected = fit._fit_predict(case, fit._ordered(development), fit._ordered(frame),
                                final['inputs']['model_inputs'],
                                final['params']['model_params'], task == 'binary')[0]
    got = preds['score'] if task == 'binary' else preds['prediction']
    np.testing.assert_allclose(got, expected, rtol=1e-10, atol=1e-12)
    # The evidence binding is written beside the bundle; the bundle still verifies.
    binding = json.loads((bundle / 'evidence_binding.json').read_bytes())
    assert binding['status'] == 'evaluated' and binding['final_result_id'] == final['result_id']
    verify_bundle(bundle)
    # A capture after the opening would be a rebuilt candidate: refused.
    out = flow.run('predictor.capture', expect=2)
    assert out['error']['code'] == 'precondition_missing'


def test_capture_is_reused_when_identical_and_never_overwritten(tmp_path):
    flow = _chosen(tmp_path)
    first = flow.run('predictor.capture')['values']
    again = flow.run('predictor.capture')                 # same inputs: already current
    assert again['status'] == 'already_current'
    bundle = _home(flow) / first['bundle']
    (bundle / 'payload/model.pkl').write_bytes(b'tampered')
    with pytest.raises(ContractError) as e:
        verify_bundle(bundle)
    assert e.value.code == 'artifact_integrity_failed'
    with pytest.raises(ContractError):
        load_predictor(bundle, trusted_roots=[bundle.parent])


def test_untrusted_bundle_is_not_loaded(tmp_path):
    flow = _chosen(tmp_path)
    v = flow.run('predictor.capture')['values']
    bundle = _home(flow) / v['bundle']
    with pytest.raises(ContractError) as e:
        load_predictor(bundle)                            # no trusted root
    assert e.value.code == 'artifact_integrity_failed'
    assert load_predictor(bundle, trusted_roots=[bundle]).predictor_id == v['predictor_id']


def test_stale_capture_blocks_the_opening_before_anything_is_read(tmp_path):
    flow = _chosen(tmp_path)
    flow.run('predictor.capture')
    flow.run('policy.evaluate', '--rule', 'capacity:40', '--rule', 'capacity:60')
    flow.decide('policy', 'capacity:60',
                words='Yes, I adopt that rule because the desk can make that many calls')
    before = len(fk.exposure_records(flow.study))
    out = _open(flow, expect=2)
    assert out['error']['code'] == 'precondition_missing'
    assert any(m.get('slot') == 'predictor.capture'
               for m in out['error']['details']['missing'])
    assert not st.final_test_opened(flow.state())
    assert len(fk.exposure_records(flow.study)) == before


def test_workshop_profile_without_its_packager_is_refused_before_any_read(tmp_path):
    flow = _chosen(tmp_path)
    rev = flow.rev()
    before = len(fk.exposure_records(flow.study))
    out = flow.run('predictor.capture', '--profile', 'workshop', expect=2)
    err = out['error']
    assert err['code'] == 'unsupported_capability'
    assert err['details']['contract_code'] == 'optional_dependency_missing'
    assert flow.rev() == rev and len(fk.exposure_records(flow.study)) == before
    assert act.CAPTURE not in flow.state()['current']


def test_workshop_profile_packages_before_the_opening(tmp_path, monkeypatch):
    monkeypatch.setenv('HYPOTRAIL_TEST_HOOKS', '1')
    flow = _chosen(tmp_path)
    v = flow.run('predictor.capture', '--profile', 'workshop', '--packager',
                 'synthetic_test')['values']
    assert [p['format'] for p in v['packages']] == ['synthetic_test']
    bundle = _home(flow) / v['bundle']
    desc = verify_bundle(bundle)
    assert desc.bundle.optional_packages[0].format == 'synthetic_test'
    assert (bundle / 'packages/synthetic_test/package_descriptor.json').is_file()
    assert not st.final_test_opened(flow.state())


def test_failing_packager_fails_the_capture_and_keeps_the_test_sealed(tmp_path, monkeypatch):
    from mlkit.contracts import testing_packager
    monkeypatch.setenv('HYPOTRAIL_TEST_HOOKS', '1')
    monkeypatch.setattr(testing_packager, 'packager',
                        lambda: testing_packager.SyntheticPackager(fail=True))
    flow = _chosen(tmp_path)
    out = flow.run('predictor.capture', '--profile', 'workshop', '--packager',
                   'synthetic_test', expect=None)
    assert out['ok'] is False
    assert out['error']['details']['contract_code'] == 'artifact_integrity_failed'
    assert act.CAPTURE not in flow.state()['current']
    assert not st.final_test_opened(flow.state())
    root = _home(flow) / 'predictors'
    assert not [p for p in root.iterdir() if not p.name.startswith('.')] if root.exists() \
        else True


def test_capture_options_are_checked(tmp_path):
    flow = _chosen(tmp_path)
    out = flow.run('predictor.capture', '--packager', 'nope', expect=2)
    assert out['error']['code'] == 'unsupported_capability'
    out = flow.run('policy.evaluate', '--rule', 'capacity:40', '--profile', 'base', expect=2)
    assert out['error']['code'] == 'invalid_arguments'


def test_a_study_without_capture_keeps_the_historical_refit(tmp_path):
    flow = _chosen(tmp_path)
    _open(flow)
    s = read.open(flow.study)
    final = s.result(s.state['current'][act.FINAL])
    assert 'predictor' not in final['inputs'] and 'predictor' not in final['output']['values']
