"""Review round 2 of the study engine (2026-10-24): E2-1, E2-2, E2-3 and area A's F1.

E2-1 / A F1: the final test is opened once. Before anything is marked opened, the captured
predictor must be current by the rule ``status`` and ``evidence`` use (stale map, code changed
under the code attestations, upstream) and loadable as the final evaluation loads it (bundle
verification, environment, parity rows). Otherwise the confirmation (or the run) is refused, the
final test stays sealed, no final-test row is read or recorded as exposed, and the junior is told
what to do. A refusal that only happens once the evaluation runs (the bundle changed after the
reservation) withdraws the opening instead of consuming the final test.

E2-2: ``run final_test.evaluation`` / ``run diag.final_test`` never answer ``already_current``
for a result that is not current; after the opening they say that it cannot be recomputed.

E2-3: an identical request on a result that is current under a code attestation is answered by
that result (nothing recomputed, nothing replaced); a change no attestation covers is still a
new request.

Every study is a temporary synthetic one; an engine change is simulated by monkeypatching the
digest the engine reads for one module (the bundle on disk stays valid).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / 'libraries'))

import flowkit as fk  # noqa: E402
import libkit  # noqa: E402
from mlkit.study import activities as act, code_compat, commands as cmd  # noqa: E402
from mlkit.study import executions, read, records as rec, registry  # noqa: E402
from mlkit.study import state as st  # noqa: E402
from mlkit.study.errors import StudyError  # noqa: E402

OPEN_WORDS = 'Yes, I open the final test now, because the model and the rule are fixed'
FAKE = '0' * 64


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
                  '--study', flow.study)
    return flow.call('decide', 'confirm', p['result']['proposal_id'], '--user-words',
                     OPEN_WORDS, '--request-id', flow.rid(), '--expected-revision',
                     flow.rev(), '--study', flow.study, expect=expect)


def _confirm_without_opening(flow, monkeypatch):
    """Confirm ``final_test`` while the opening that follows the confirmation is held back,
    so the next ``run final_test.evaluation`` is the one that opens."""
    with monkeypatch.context() as m:
        m.setattr(cmd, '_opening', lambda store, payload, request_id: None)
        _open(flow)
    assert st.final_test_opened(flow.state()) is False


def _changed(monkeypatch, module: str) -> None:
    """The engine now reads another digest for ``module`` (an engine upgrade)."""
    original = read.Study._module_sha

    def sha(self, name):
        return FAKE if name == module else original(self, name)
    monkeypatch.setattr(read.Study, '_module_sha', sha)


def _final_exposures(flow) -> list[dict]:
    """Final-test exposures of an evaluation (``init`` checks the partition's schema)."""
    return [e for e in fk.exposure_records(flow.study)
            if e['partition'] == 'final_test' and e['activity'] == act.FINAL]


def _sealed(flow) -> None:
    state = flow.state()
    assert not st.final_test_opened(state)
    assert (state.get('partition') or {}).get('opening') is None
    assert act.FINAL not in state['current']
    assert _final_exposures(flow) == []


# --- E2-1: a capture whose code changed --------------------------------------------------------

@pytest.mark.parametrize('module', ['hypotrail_runtime.predictor', 'mlkit.contracts.recipe'])
def test_confirmation_is_refused_on_a_capture_whose_code_changed(tmp_path, monkeypatch, module):
    flow = _chosen(tmp_path)
    flow.run('predictor.capture')
    with monkeypatch.context() as m:
        _changed(m, module)
        assert not read.open(flow.study).is_current(act.CAPTURE)   # what status/evidence say
        before = len(fk.exposure_records(flow.study))
        out = _open(flow, expect=2)
        error = out['error']
        assert error['code'] == 'precondition_missing'
        item = next(x for x in error['details']['missing'] if x.get('slot') == act.CAPTURE)
        assert item['requirement'] == 'result_current' and item['code_changed'] == [module]
        junior = error['details']['junior_message']
        assert 'predictor.capture' in junior and 'No final-test row was read' in junior
        _sealed(flow)
        assert len(fk.exposure_records(flow.study)) == before
        assert flow.state()['decisions']['final_test']['status'] != 'confirmed'
    # The code is back: the same opening works (the final test was never consumed).
    out = _open(flow)
    assert out['result']['opening']['status'] == 'promoted'


def test_run_is_refused_before_the_opening_on_a_capture_whose_code_changed(tmp_path,
                                                                             monkeypatch):
    """The run path (a confirmed final test whose opening has not run): the reservation
    refuses before it marks anything opened."""
    flow = _chosen(tmp_path)
    flow.run('predictor.capture')
    _confirm_without_opening(flow, monkeypatch)
    with monkeypatch.context() as m:
        _changed(m, 'hypotrail_runtime.predictor')
        out = flow.run('final_test.evaluation', expect=2)
        assert out['error']['code'] == 'precondition_missing'
        assert out['error']['details']['contract_code'] == 'model_not_captured'
        junior = out['error']['details']['junior_message']
        assert 'predictor.capture' in junior and 'No final-test row was read' in junior
        _sealed(flow)
    out = flow.run('final_test.evaluation')
    assert out['status'] == 'promoted'
    assert flow.state()['partition']['opening']['result_id'] == out['result_id']


def test_capture_with_a_stale_upstream_is_not_usable(tmp_path, monkeypatch):
    """Upstream currency counts too: a capture computed from a fit whose code changed."""
    flow = _chosen(tmp_path)
    flow.run('predictor.capture')
    with monkeypatch.context() as m:
        _changed(m, 'mlkit.study.policy')        # in the policy evaluation, not in the capture
        study = read.open(flow.study)
        reason = study.currency(study.state['current'][act.CAPTURE])['reason']
        assert reason['upstream_not_current'] and not reason.get('code_changed')
        out = _open(flow, expect=2)
        item = next(x for x in out['error']['details']['missing'] if x.get('slot') == act.CAPTURE)
        assert item['upstream_not_current']
        _sealed(flow)


# --- A F1: a capture the final evaluation cannot load ------------------------------------------

def test_stray_file_in_the_bundle_is_refused_before_the_opening(tmp_path):
    flow = _chosen(tmp_path, 'regression')
    v = flow.run('predictor.capture')['values']
    bundle = Path(flow.study) / '.hypotrail' / v['bundle']
    (bundle / '.DS_Store').write_bytes(b'\x00\x00\x00\x01Bud1')
    out = _open(flow, expect=2)
    error = out['error']
    assert error['code'] == 'precondition_missing'
    item = next(x for x in error['details']['missing'] if x['requirement'] == 'capture_loadable')
    assert item['contract_code'] == 'artifact_integrity_failed'
    assert 'stray file' in error['details']['junior_message']
    assert 'No final-test row was read' in error['details']['junior_message']
    _sealed(flow)
    (bundle / '.DS_Store').unlink()                      # repaired: the final test opens
    out = _open(flow)
    assert out['result']['opening']['status'] == 'promoted'


def test_environment_change_is_refused_before_the_opening(tmp_path, monkeypatch):
    import hypotrail_runtime.predictor as rp
    flow = _chosen(tmp_path)
    flow.run('predictor.capture')
    with monkeypatch.context() as m:
        m.setattr(rp, 'environment_issues', lambda manifest: [
            {'distribution': 'numpy', 'captured': '1.0', 'installed': '9.9'}])
        out = _open(flow, expect=2)
        item = next(x for x in out['error']['details']['missing']
                    if x['requirement'] == 'capture_loadable')
        assert item['contract_code'] == 'environment_unqualified'
        assert 'captured versions' in out['error']['details']['junior_message']
        _sealed(flow)
    assert _open(flow)['result']['opening']['status'] == 'promoted'


def test_a_bundle_refused_after_the_reservation_withdraws_the_opening(tmp_path, monkeypatch):
    """The bundle changes between the reservation (which checked it) and the evaluation: the
    evaluation refuses it before reading any final-test row, so the opening is withdrawn, only
    the development rows it read are recorded, and the final test can still be opened."""
    flow = _chosen(tmp_path)
    v = flow.run('predictor.capture')['values']
    bundle = Path(flow.study) / '.hypotrail' / v['bundle']
    _confirm_without_opening(flow, monkeypatch)
    stray = bundle / 'notes.txt'

    def tamper(plan):
        assert st.final_test_opened(read.open(flow.study).state)   # reserved: opened
        stray.write_text('edited after the reservation', encoding='utf-8')
    with pytest.raises(StudyError) as e:
        executions.run(flow.study, act.FINAL, {}, request_id=flow.rid(),
                       expected_revision=flow.rev(), hooks={'after_reserve': tamper},
                       render=False)
    assert e.value.details['final_test_rows_read'] is False
    assert 'No final-test row was read' in e.value.details['junior_message']
    _sealed(flow)
    state = flow.state()
    failed = [r for r in state['receipts'].values()
              if (r.get('result') or {}).get('final_test') == 'sealed']
    assert len(failed) == 1 and failed[0]['result']['status'] == 'failed'
    stray.unlink()
    out = flow.run('final_test.evaluation')
    assert out['status'] == 'promoted'
    assert len(_final_exposures(flow)) == 1


# --- E2-2: no already_current for a final result that is not current ---------------------------

def test_final_results_that_are_not_current_are_never_already_current(tmp_path, monkeypatch):
    flow = _chosen(tmp_path)
    flow.run('predictor.capture')
    assert _open(flow)['result']['opening']['status'] == 'promoted'
    flow.run('diag.final_test')
    # Current: an identical request is answered by the result.
    assert flow.run('final_test.evaluation')['status'] == 'already_current'
    assert flow.run('diag.final_test')['status'] == 'already_current'
    with monkeypatch.context() as m:
        _changed(m, 'hypotrail_runtime.predictor')     # the capture the final test scored
        study = read.open(flow.study)
        assert not study.is_current(act.FINAL) and not study.is_current(act.DIAG_FINAL)
        out = flow.run('final_test.evaluation', expect=2)
        assert out['error']['code'] == 'final_test_already_opened'
        assert out['error']['details']['current'] is False
        assert 'cannot be recomputed' in out['error']['message']
        out = flow.run('diag.final_test', expect=2)
        assert out['error']['code'] == 'precondition_missing'
        assert out['error']['details']['current'] is False
        assert 'cannot make it current' in out['error']['message']
        assert out['error']['details']['junior_message']


# --- E2-3: identical requests on attested-current results ---------------------------------------

def _engine_upgrade(monkeypatch, module: str, attested_for: list[str] | None) -> None:
    """``module`` now has another digest for the plan and for currency; an exact attestation
    from the recorded digest to it covers ``attested_for`` (none when None)."""
    real = registry.module_source_path(module).read_bytes()
    import hashlib
    old = hashlib.sha256(real).hexdigest()
    _changed(monkeypatch, module)
    original = registry.code_fingerprint

    def fingerprint(modules):
        out = original(modules)
        if module in out['modules']:
            shas = {**out['modules'], module: FAKE}
            out = {'fingerprint': rec.code_digest(shas), 'modules': shas}
        return out
    monkeypatch.setattr(registry, 'code_fingerprint', fingerprint)
    if attested_for:
        edge = {'module': module, 'from_sha256': old, 'to_sha256': FAKE,
                'activities': list(attested_for), 'reason': 'test edge',
                'evidence': ['framework/tests/study/test_review_round2_engine.py']}
        exact = code_compat.equivalent

        def equivalent(name, from_sha, to_sha=None, activity=None,
                       records=code_compat.ATTESTATIONS):
            return exact(name, from_sha, to_sha, activity, records=(*records, edge))
        monkeypatch.setattr(code_compat, 'equivalent', equivalent)


def _flow_with_baseline(tmp_path):
    flow = libkit.study_at_fits(tmp_path)
    first = flow.run('fit.baseline')
    return flow, first['result_id']


def test_identical_request_on_an_attested_result_is_answered_by_it(tmp_path, monkeypatch):
    flow, rid = _flow_with_baseline(tmp_path)
    n = len(fk.registry_entries(flow.study))
    with monkeypatch.context() as m:
        _engine_upgrade(m, 'mlkit.study.metrics', ['fit.baseline'])
        assert read.open(flow.study).is_current(act.BASELINE)      # attested: current
        again = flow.run('fit.baseline')
        assert again['status'] == 'already_current' and again['result_id'] == rid
        assert len(fk.registry_entries(flow.study)) == n           # nothing new
        assert flow.state()['current'][act.BASELINE] == rid
        assert read.open(flow.study).is_current(act.BASELINE)


@pytest.mark.parametrize('attested_for', [None, ['fit.logistic']])
def test_a_change_no_attestation_covers_is_a_new_request(tmp_path, monkeypatch, attested_for):
    """No edge, or an edge for another activity only: the result is not current and the
    identical request recomputes it (the shortcut hides no genuine change)."""
    flow, rid = _flow_with_baseline(tmp_path)
    with monkeypatch.context() as m:
        _engine_upgrade(m, 'mlkit.study.metrics', attested_for)
        study = read.open(flow.study)
        assert not study.is_current(act.BASELINE)
        assert study.currency(rid)['reason']['code_changed'] == ['mlkit.study.metrics']
        again = flow.run('fit.baseline')
        assert again['status'] == 'promoted' and again['result_id'] != rid
        assert read.open(flow.study).is_current(act.BASELINE)

