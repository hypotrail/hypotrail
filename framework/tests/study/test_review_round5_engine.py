"""Regressions of the fifth review round of 25 October 2026, area E (engine and runtime).

R5E-1 the installed-runtime check compared every file of the package folder: a ``.DS_Store``
in an editable runtime refused every capture (with a remediation to capture again). Both
sides now follow the wheel's own selection rule (a stray ``*.py`` and an extension module
still count) and a refusal of the capture says what to remove, in English and French.
R5E-2 the capture's fingerprint omitted runtime files the wheel holds, and a capture the
final evaluation could not load stayed ``already_current`` while ``next_action`` looped on the
opening: the fingerprint covers every wheel file, the run path and ``next_action`` treat an
unloadable capture as one to compute again, and the junior is never told to install a
bundle's wheel over the engine's runtime. R5E-3 a re-capture keeps the options of the capture
it replaces. R5E-4 ``next_action`` names the rules of the policy evaluation (the criterion's
under review-v1, the engine's recommended shares otherwise), the policy proposal carries its
rule, and the run digest asks nothing. R5E-5 scaled and odd numeric forms are traced or
reported. R5E-6 the review-v1 recommended criterion is complete. R5E-7 an unevaluated policy
proposal is evaluated first. R5E-8 after the opening, a proposal says that the final test
cannot be recomputed, and the export never says to capture again. R5E-9 French reports write
rule, decision-value and figure lines in French. Every study lives in ``tmp_path`` and the
data are synthetic.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / 'libraries'))

import hypotrail_runtime  # noqa: E402
from hypotrail_runtime import wheel as rw  # noqa: E402

import flowkit as fk  # noqa: E402
from mlkit.study import (activities as act, code_compat, governance, numtrace,  # noqa: E402
                         read, registry, state as st, view as view_mod)
from test_review_round2_training_exclusions import (CRITERION, OPEN, VARIANT,  # noqa: E402
                                                    ReviewFlow)
from test_review_round3_engine import (ADOPT, CHOOSE, REG_CRITERION, REG_WORDS,  # noqa: E402
                                       _changed, _to_choice)

REPO = Path(__file__).resolve().parents[3]
RUNTIME_SOURCE = Path(hypotrail_runtime.__file__).resolve().parent
ACTS = 'mlkit.study.activities'
ACTIVITIES_FILE = 'framework/mlkit/study/activities.py'
CURRENT = '9f5e8c3fa79d7ebbfdb146bc2c556733998377fc023d4309e99964feac48175b'
SOURCES = {'b5f6dba': 'b7c994d2e88edba8156c47756c0c43a496f0e04d4f7005bc1d9014ab639a48c1',
           '818995c': 'd6806ce3ff8f40c90eec7342c4ea2693a87c39a387a660dc1633364edd5c1f10',
           '506180a': '3065f4d623f1ea2346c43ef27c0dd0f9a948c8eb007355c9cb625967b17cc9e1'}
ATTESTED = ['split', 'eda.target_rate', 'eda.special_values', 'eda.rate_by',
            'eda.target_summary', 'eda.mean_by', 'eda.distribution', 'eda.quality',
            'eda.single_feature_signal', 'eda.correlation', 'fit.baseline', 'fit.logistic',
            'fit.linear', 'fit.variant', 'policy.evaluation', 'policy.inspect',
            'evaluate.regression', 'diag.binary', 'diag.regression', 'final_test.evaluation',
            'diag.final_test']


def _copy_runtime(base: Path, extra: dict | None = None, edit: dict | None = None) -> Path:
    """A copy of the installed runtime (an editable install elsewhere), with ``extra`` files
    added and ``edit`` files rewritten; returns its package folder."""
    alt = base / 'rt' / 'hypotrail_runtime'
    shutil.copytree(RUNTIME_SOURCE, alt, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for name, data in {**(extra or {}), **(edit or {})}.items():
        path = alt / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return alt


def _installed(monkeypatch, alt: Path, *, builds: bool = False) -> None:
    """The import system now resolves ``hypotrail_runtime`` to ``alt``; with ``builds`` the
    wheel of a capture is built from ``alt`` too (the runtime itself was changed)."""
    monkeypatch.setattr(rw, 'installed_location', lambda: alt.resolve())
    if builds:
        monkeypatch.setattr(rw, '__file__', str(alt / 'wheel.py'))


def _chosen(tmp_path, task='binary', language=None):
    import test_capture_final as tcf
    if language is None:
        return tcf._chosen(tmp_path, task)
    # test_capture_final._chosen (binary), in a study created in ``language``.
    case_dir = fk.make_case(tmp_path / 'case', task=task, n_rows=500)['case'].parent
    flow = fk.Flow(tmp_path / 'study', case_dir)
    flow.call('init', '--case', case_dir, '--study', flow.study, '--lang', language)
    flow.decide('prediction_time', 'when the record is created, before the outcome')
    flow.decide('feature_availability', fk.availability(case_dir))
    flow.decide('split', flow.view()['next_action']['default_value'])
    flow.model_decisions()
    flow.run('split')
    flow.run('fit.baseline')
    flow.run('fit.logistic')
    flow.variant()
    flow.run('policy.evaluate', '--rule', 'capacity:40')
    flow.decide('policy', 'capacity:40',
                words='Yes, I adopt that rule because the desk can make that many calls')
    return flow


def _open(flow, expect=0):
    import test_capture_final as tcf
    return tcf._open(flow, expect=expect)


def _to_opening(flow, limit=8):
    """The first ``next_action`` that opens the final test or captures the predictor, after
    the runs the plan names before it (executed as given)."""
    for _ in range(limit):
        nxt = flow.view()['next_action']
        if nxt.get('decision') == 'final_test' or nxt.get('activity') == act.CAPTURE:
            return nxt
        assert nxt['kind'] == 'run', nxt
        _run(flow, nxt['activity'], *[a for r in nxt.get('rules') or []
                                      for a in ('--rule', r)], expect=0)
    raise AssertionError('the opening was not reached')


def _run(flow, *args, expect=None):
    return flow.call('run', *args, '--request-id', flow.rid(), '--expected-revision',
                     flow.rev(), '--study', flow.study, expect=expect)


# --- R5E-1: the installed runtime is compared on the files its wheel holds ---------------------

@pytest.mark.parametrize('name', ['.DS_Store', '.predictor.py.swp', 'predictor.py.orig',
                                  'schemas/README.md', '__pycache__/x.cpython-313.pyc'])
def test_a_stray_file_the_wheel_ignores_is_ignored(tmp_path, monkeypatch, name):
    """The reviewer's probe: each of these refused every load (runtime_not_bound)."""
    data = rw.build(tmp_path / 'w').read_bytes()
    alt = _copy_runtime(tmp_path, {name: b'\0\0\0\1Bud1'})
    _installed(monkeypatch, alt)
    assert rw.installed_runtime_issues(data) is None
    assert rw.installed_files(alt) == rw.wheel_files(data)


@pytest.mark.parametrize('name', ['stray.py', 'schemas/extra.json', 'native.so',
                                  'native.cpython-313-x86_64-linux-gnu.so', 'native.pyd'])
def test_stray_code_still_counts(tmp_path, monkeypatch, name):
    data = rw.build(tmp_path / 'w').read_bytes()
    alt = _copy_runtime(tmp_path, {name: b'VALUE = 1\n'})
    _installed(monkeypatch, alt)
    issues = rw.installed_runtime_issues(data)
    assert issues is not None and issues['unexpected'] == [name]


def test_the_wheel_and_the_comparison_share_one_selection_rule(tmp_path):
    alt = _copy_runtime(tmp_path, {'.DS_Store': b'x', 'stray.py': b'VALUE = 1\n'})
    for path in alt.rglob('*'):
        if path.is_file():
            rel = path.relative_to(alt)
            assert rw.wheel_member(rel) == (path.suffix in ('.py', '.json', '.typed')
                                            and '__pycache__' not in rel.parts)
    assert 'hypotrail_runtime/stray.py' in rw.installed_files(alt)
    assert 'hypotrail_runtime/.DS_Store' not in rw.installed_files(alt)


def test_a_ds_store_in_an_editable_runtime_captures_and_opens(tmp_path, monkeypatch):
    """The reviewer's engine probe: the capture refused (unsupported_capability without a
    junior message) and ``next_action`` looped on the opening."""
    flow = _chosen(tmp_path)
    _installed(monkeypatch, _copy_runtime(tmp_path, {'.DS_Store': b'\0\0\0\1Bud1'}))
    assert _run(flow, 'predictor.capture')['status'] == 'promoted'
    nxt = _to_opening(flow)
    assert (nxt['kind'], nxt.get('decision')) == ('propose', 'final_test')
    assert _open(flow)['result']['opening']['status'] == 'promoted'


@pytest.mark.parametrize('language', ['en', 'fr'])
def test_a_capture_refused_by_the_runtime_folder_says_what_to_remove(tmp_path, monkeypatch,
                                                                    language):
    """An extension module beside the sources: no wheel carries it, so the capture's own
    reload refuses. The refusal names the file and how to fix it, never only "capture
    again", with a junior message in the study language."""
    flow = _chosen(tmp_path, language=language)
    _installed(monkeypatch, _copy_runtime(tmp_path, {'native.so': b'\x7fELF'}))
    out = _run(flow, 'predictor.capture', expect=2)
    err = out['error']
    assert err['code'] == 'unsupported_capability'
    details = err['details']
    assert (details['contract_code'], details['reason']) == ('environment_unqualified',
                                                             'runtime_not_bound')
    assert details['unexpected'] == ['native.so']
    assert details['remediation'].startswith('Remove native.so from ')
    junior = details['junior_message']
    assert 'native.so' in junior
    if language == 'fr':
        assert 'Retirez ces fichiers' in junior and "Rien n'a été capturé" in junior
    else:
        assert 'Remove those files' in junior and 'Nothing was captured' in junior
    assert act.CAPTURE not in flow.state()['current']


# --- R5E-2: every runtime file the wheel holds, and an unloadable capture --------------------

def test_the_capture_fingerprint_covers_every_file_of_the_wheel(tmp_path):
    data = rw.build(tmp_path / 'w').read_bytes()
    members = {name.removeprefix('hypotrail_runtime/') for name in rw.wheel_files(data)}
    covered = set()
    for name in act.MODULES[act.CAPTURE]:
        if name.startswith('hypotrail_runtime/'):
            covered.add(name.removeprefix('hypotrail_runtime/'))
        elif name == 'hypotrail_runtime' or name.startswith('hypotrail_runtime.'):
            path = read._module_path(name)
            covered.add(path.relative_to(RUNTIME_SOURCE).as_posix())
    assert covered == members
    code = registry.code_fingerprint(act.MODULES[act.CAPTURE])
    for name in act.MODULES[act.CAPTURE]:
        if name.startswith('hypotrail_runtime/'):
            assert code['modules'][name] == hashlib.sha256(
                (RUNTIME_SOURCE / name.removeprefix('hypotrail_runtime/')).read_bytes()
            ).hexdigest()
    assert read._module_path('hypotrail_runtime/../x.json') is None
    with pytest.raises(Exception) as caught:
        registry.module_source_path('hypotrail_runtime/schemas/none.json')
    assert getattr(caught.value, 'code', None) == 'unknown_module'


def _changed_runtime(tmp_path, monkeypatch, name='errors.py'):
    """The runtime installed now differs from the capture's in ``name`` only (an engine
    update), and builds the wheel of a new capture."""
    text = (RUNTIME_SOURCE / name).read_bytes() + b'\n# an engine update\n'
    alt = _copy_runtime(tmp_path, edit={name: text})
    _installed(monkeypatch, alt, builds=True)
    return alt


@pytest.mark.parametrize('name', ['errors.py', 'wheel.py', 'packaging.py',
                                  'schemas/model_recipe-v1.schema.json'])
def test_an_unloadable_capture_is_captured_again(tmp_path, monkeypatch, name):
    """The reviewer's loop: ``run predictor.capture`` answered ``already_current`` and
    ``next_action`` proposed the opening (refused, capture_loadable) forever."""
    flow = _chosen(tmp_path)
    first = _run(flow, 'predictor.capture')['result_id']
    _changed_runtime(tmp_path, monkeypatch, name)
    nxt = _to_opening(flow)
    assert (nxt['kind'], nxt['activity'], nxt['not_current']) == (
        'run', act.CAPTURE, [act.CAPTURE])
    assert 'Run predictor.capture again' in nxt['junior_message']
    assert 'Install' not in nxt['junior_message'] and 'wheel' not in nxt['junior_message']
    assert 'options' not in nxt                 # a base capture has none
    # A read-only process (a notebook kernel) never loads the bundle for next_action.
    from mlkit.study import capture_check
    snapshot = read.open(flow.study)
    assert capture_check.unloadable(snapshot, snapshot.state)['requirement'] == \
        'capture_loadable'
    monkeypatch.setenv('HYPOTRAIL_READ_ONLY', '1')
    assert capture_check.unloadable(snapshot, snapshot.state) is None
    monkeypatch.delenv('HYPOTRAIL_READ_ONLY')
    refused = _open(flow, expect=2)
    item = next(m for m in refused['error']['details']['missing']
                if m['requirement'] == 'capture_loadable')
    assert 'pip install' not in item['remediation']
    assert 'never' in item['remediation'].lower()
    # The proposal the confirmation refused stays open: its words are not asked for while
    # the capture cannot load.
    nxt = flow.view()['next_action']
    assert (nxt['kind'], nxt['activity']) == ('run', act.CAPTURE)
    out = _run(flow, 'predictor.capture')
    assert out['status'] == 'promoted' and out['result_id'] != first
    nxt = _to_opening(flow)
    assert (nxt['kind'], nxt.get('decision')) == ('await_user_words', 'final_test')
    assert _open(flow)['result']['opening']['status'] == 'promoted'


def test_a_loadable_capture_stays_already_current(tmp_path):
    flow = _chosen(tmp_path)
    first = _run(flow, 'predictor.capture')
    again = _run(flow, 'predictor.capture')
    assert again['status'] == 'already_current' and again['result_id'] == first['result_id']


# --- R5E-3: a re-capture keeps the options of the capture it replaces ------------------------

def test_a_re_capture_keeps_the_packager(tmp_path, monkeypatch):
    monkeypatch.setenv('HYPOTRAIL_TEST_HOOKS', '1')
    flow = _chosen(tmp_path)
    _run(flow, 'predictor.capture', '--packager', 'synthetic_test')
    _changed_runtime(tmp_path, monkeypatch)
    nxt = _to_opening(flow)
    assert nxt['activity'] == act.CAPTURE and nxt['options'] == {'packager': 'synthetic_test'}
    args = [nxt['activity']]
    for option, value in nxt['options'].items():
        args += [f'--{option}', value]
    out = _run(flow, *args)
    assert [p['format'] for p in out['values']['packages']] == ['synthetic_test']
    # Without the option, the run path defaults to the replaced capture's options.
    monkeypatch.undo()
    monkeypatch.setenv('HYPOTRAIL_TEST_HOOKS', '1')
    _changed_runtime(tmp_path / 'again', monkeypatch, 'packaging.py')
    out = _run(flow, act.CAPTURE)
    assert out['status'] == 'promoted'
    assert [p['format'] for p in out['values']['packages']] == ['synthetic_test']
    from mlkit.study import store as sto
    assert registry.get(sto.StudyStore(flow.study),
                        out['result_id'])['params']['packager'] == 'synthetic_test'
    # An explicit --profile base captures without a package.
    _changed_runtime(tmp_path / 'third', monkeypatch, 'wheel.py')
    out = _run(flow, act.CAPTURE, '--profile', 'base')
    assert out['values']['packages'] == []


def test_capture_options_of_params():
    assert view_mod.capture_options({'profile': 'base', 'packager': None}) == {}
    assert view_mod.capture_options({'profile': 'workshop', 'packager': 'mlflow_pyfunc'}) == {
        'profile': 'workshop'}
    assert view_mod.capture_options({'profile': 'base', 'packager': 'mlflow_pyfunc'}) == {
        'packager': 'mlflow_pyfunc'}


# --- R5E-4, R5E-6, R5E-7: the policy and the criterion as next_action gives them -------------

def test_the_recommended_rules_are_the_engine_s():
    from mlkit.study import diagnostics, policy
    assert view_mod.RECOMMENDED_RULES == tuple(f'share:{p}' for p in policy.GAIN_SHARES)
    assert view_mod.RECOMMENDED_RULE == diagnostics.DEFAULT_RULE
    assert view_mod.RECOMMENDED_RULE in view_mod.RECOMMENDED_RULES


def _until(f, wanted, limit=8):
    """Execute the ``run`` actions as given until ``wanted(next_action)``; return it."""
    for _ in range(limit):
        nxt = f.view()['next_action']
        if wanted(nxt):
            return nxt
        assert nxt['kind'] == 'run', nxt
        _run(f, nxt['activity'], *[a for r in nxt.get('rules') or [] for a in ('--rule', r)],
             expect=0)
    raise AssertionError('not reached')


def _review_at_criterion(tmp_path, language='en'):
    f = ReviewFlow(tmp_path, outcome_delay=0, language=language)
    f.init()
    f.decide('prediction_time', 'Predict using information available at the planted decision '
                                'time')
    f.decide('feature_availability', fk.availability(f.case_dir))
    f.decide('split', st.b1_default_value(f.state(), 'split'))
    return f


def test_the_review_v1_recommended_criterion_is_complete(tmp_path):
    """The reviewer's ``probe_sc``: proposing the recommended criterion was invalid_value."""
    f = _review_at_criterion(tmp_path)
    f.run('split')
    nxt = f.view()['next_action']
    assert nxt['decision'] == 'success_criterion'
    for item in nxt['criterion_options']['candidates']:
        assert item['value']['decision_rule'] == 'point_estimate'
        assert item['value']['selection'] == {'metric': 'precision', 'rule': 'share:0.1',
                                              'scope': 'evaluation_window',
                                              'batch_column': None,
                                              'aggregation': 'pooled_counts'}
    value = nxt['recommended']['value']
    assert 'select the top 10% by score' in nxt['recommended']['why']
    out = f.decide('success_criterion', value)
    assert out['ok']


def test_the_policy_evaluation_runs_on_the_criterion_s_rule(tmp_path):
    """The reviewer's ``probe_pol2``: ``run policy.evaluation`` without a rule, forever."""
    f = ReviewFlow(tmp_path, outcome_delay=0)
    f.init()
    f.pauses()
    f.run('split')
    f.models()
    f.decide('model_choice', 'fit.logistic', words=CHOOSE)
    nxt = _until(f, lambda n: n.get('activity') == 'policy.evaluation')
    assert (nxt['kind'], nxt['activity'], nxt['rules']) == ('run', 'policy.evaluation',
                                                           [CRITERION['selection']['rule']])
    assert 'Once it is done, you decide:' in nxt['junior_digest']
    assert 'on the rule: select the top 20% by score' in nxt['junior_digest']
    _run(f, nxt['activity'], *[a for r in nxt['rules'] for a in ('--rule', r)], expect=0)
    for _ in range(3):
        nxt = f.view()['next_action']
        if nxt['kind'] == 'propose':
            break
        _run(f, nxt['activity'], expect=0)
    assert (nxt['decision'], nxt['default_value']) == ('policy', 'share:0.2')
    assert nxt['recommended']['why'].startswith('The success criterion you confirmed fixes')
    assert 'Your success criterion fixes the rule' in nxt['junior_digest']


def _legacy_at_policy(tmp_path, language='en'):
    case_dir = fk.make_case(tmp_path / 'case', n_rows=300)['case'].parent
    f = fk.Flow(tmp_path / 'study', case_dir, prefix='leg')
    f.call('init', '--case', case_dir, '--study', f.study, '--lang', language)
    f.pauses()
    f.run('split')
    f.run('eda.quality')            # owner session 2026-10-26 (L5): a step of a new study
    f.run('fit.baseline')
    f.run('fit.logistic')
    f.variant()
    f.decide('model_choice', 'fit.logistic', words=CHOOSE)
    return f


def test_a_legacy_study_evaluates_the_engine_s_shares_then_proposes_one(tmp_path):
    f = _legacy_at_policy(tmp_path)
    nxt = _until(f, lambda n: n.get('activity') == 'policy.evaluation')
    assert (nxt['activity'], nxt['rules']) == ('policy.evaluation',
                                              list(view_mod.RECOMMENDED_RULES))
    _run(f, nxt['activity'], *[a for r in nxt['rules'] for a in ('--rule', r)], expect=0)
    for _ in range(3):
        nxt = f.view()['next_action']
        if nxt['kind'] == 'propose':
            break
        _run(f, nxt['activity'], expect=0)
    assert (nxt['decision'], nxt['default_value']) == ('policy', 'share:0.1')
    assert 'not a figure from a team' in nxt['recommended']['why']
    assert 'The engine proposes: select the top 10% by score.' in nxt['junior_digest']
    assert 'scenario' not in nxt['junior_digest']


def test_an_unevaluated_policy_proposal_is_evaluated_first(tmp_path):
    """The reviewer's ``probe_pol``: a proposal of a rule never evaluated was accepted, the
    confirmation refused it, ``next_action`` awaited words forever."""
    f = _legacy_at_policy(tmp_path)
    _run(f, 'policy.evaluate', '--rule', 'capacity:40', expect=0)
    p = f.call('decide', 'propose', 'policy', '--value-json', json.dumps('capacity:30'),
               '--restatement', 'You act on the top thirty.', '--rationale', 'Capacity.',
               '--request-id', f.rid(), '--expected-revision', f.rev(), '--study', f.study)
    pid = p['result']['proposal_id']
    nxt = f.view()['next_action']
    assert (nxt['kind'], nxt['activity'], nxt['proposal_id']) == ('run', 'policy.evaluation',
                                                                 pid)
    assert nxt['rules'][0] == 'capacity:30' and 'capacity:40' in nxt['rules']
    assert 'has not been evaluated' in nxt['junior_message']
    _run(f, nxt['activity'], *[a for r in nxt['rules'] for a in ('--rule', r)], expect=0)
    nxt = f.view()['next_action']
    assert (nxt['kind'], nxt['proposal_id']) == ('await_user_words', pid)
    out = f.call('decide', 'confirm', pid, '--user-words', ADOPT, '--request-id', f.rid(),
                 '--expected-revision', f.rev(), '--study', f.study)
    assert out['ok']


# --- R5E-8: after the opening ---------------------------------------------------------------

def test_a_proposal_after_an_opening_says_the_final_test_cannot_be_recomputed(tmp_path,
                                                                              monkeypatch):
    f = ReviewFlow(tmp_path, outcome_delay=0)
    _to_choice(f)
    f.decide('final_test', st.b1_default_value(f.state(), 'final_test'), words=OPEN)
    f.run('diag.final_test')
    assert f.view()['next_action']['decision'] == 'conclusion'
    assert 'not_recomputable' not in f.view()['next_action']
    with monkeypatch.context() as m:
        _changed(m, 'mlkit.study.policy')
        nxt = f.view()['next_action']
        assert (nxt['kind'], nxt['decision']) == ('propose', 'conclusion')
        assert nxt['not_recomputable'] == ['final_test.evaluation']
        assert nxt['junior_message'].startswith('The final test was opened once, and its '
                                                'evaluation cannot be computed again')
        assert nxt['verdicts']
        assert nxt['junior_digest'].startswith('The final test was opened once')


def test_the_export_never_says_to_capture_again_after_the_opening():
    from mlkit.exporters.azureml import snapshot
    from mlkit.exporters.azureml.errors import ExportError
    error = ExportError('artifact_integrity_failed', 'The runtime wheel is altered.',
                        path='predictor.runtime', remediation='Capture the predictor again.',
                        details={'reason': 'x'})
    after = snapshot.after_opening(error, 'opened')
    assert after.code == error.code and after.details['path'] == 'predictor.runtime'
    assert after.details['remediation'] == snapshot.AFTER_OPENING_REMEDIATION
    assert 'can no longer be captured again' in after.details['remediation']
    assert after.details['recapture_possible'] is False
    assert after.details['original_remediation'] == 'Capture the predictor again.'
    assert snapshot.after_opening(error, 'sealed') is error
    other = ExportError('contract_invalid', 'x', remediation='Fix the engine.')
    assert snapshot.after_opening(other, 'opened') is other


# --- R5E-5: scaled and odd numeric forms --------------------------------------------------------

def _pool(language='en', **values):
    results = {'eda.quality': {'result_id': 'a' * 64, 'current': True, 'integrity': 'ok',
                               'values': values or {'n_rows': 241, 'rate': 1.5, 'big': 12000},
                               'n_rows': None}}
    return numtrace.Pool({'results': results, 'decisions': {}, 'open_proposals': [],
                          'settings': {}, 'dataset': {}, 'facts': {'by_status': {}},
                          'plan': [], 'not_yet_defensible': [], 'language': language})


def _trace(pool, text):
    findings, traced = numtrace.trace_text(pool, text, 'draft')
    return ([(t.get('id') or t.get('path'), t.get('value')) for t in traced],
            [f['details']['number'] for f in findings])


SCALED = ['We lost 241 k clients.', 'We lost 241 K clients.', 'We lost 241 thousand clients.',
          'We lost 241 thousands.', 'Nous avons perdu 241 mille clients.',
          'We lost 1.5 billion.', 'Nous avons perdu 1,5 milliard.',
          'We lost 1.5 millions de clients.', 'We lost 1.5 bn.', 'We lost 1.5bn.',
          'We lost 241-thousand clients.', 'We lost 1.5‰.', 'We lost 241k€.',
          'We lost 1.5 million clients.', 'We lost 1.5x10^6 clients.',
          'We lost 1.5×10⁶ clients.', 'We lost 1.5Mio clients.']
ODD = ['We lost 241kEUR.', 'We lost 241kk clients.', 'We lost 241_000 clients.',
       'We lost 10² clients.', 'We lost ½ of clients.', 'We lost 0x1F clients.',
       'It took 12ms.']


@pytest.mark.parametrize('language', ['en', 'fr'])
@pytest.mark.parametrize('text', SCALED)
def test_a_scaled_number_is_never_read_as_the_bare_number(text, language):
    """The reviewer's ``probe_num``: these traced to 241 or 1.5 (n_rows, rate)."""
    traced, findings = _trace(_pool(language), text)
    assert traced == [] and len(findings) == 1, (text, traced, findings)


@pytest.mark.parametrize('language', ['en', 'fr'])
@pytest.mark.parametrize('text', ODD)
def test_an_odd_numeric_form_is_reported(text, language):
    findings, traced = numtrace.trace_text(_pool(language), text, 'draft')
    assert traced == [] and len(findings) == 1, (text, traced, findings)
    assert findings[0]['code'] == 'untraceable_number'
    assert findings[0]['details']['form']


@pytest.mark.parametrize('text,value', [
    ('We lost 241 k clients.', 241000), ('We lost 241-thousand clients.', 241000),
    ('Nous avons perdu 241 mille clients.', 241000), ('We lost 241 thousand rows.', 241000)])
def test_a_scaled_number_traces_to_the_value_it_scales_to(text, value):
    assert _trace(_pool(n_rows=241000), text) == ([('n_rows', 241000)], [])


def test_a_per_mille_and_a_scale_word_trace_when_registered():
    assert _trace(_pool(rate=0.0015), 'The rate is 1.5‰.') == ([('rate', 0.0015)], [])
    assert _trace(_pool('fr', big=1.5e9), 'Le total est 1,5 milliard.')[1] == []
    assert _trace(_pool(big=12e6), 'We lost 12,000 thousand.')[1] == []


@pytest.mark.parametrize('text', ['The 5 k-fold scheme', 'the 1st fold and the 2nd one',
                                  'le 1er pli, le 2e pli et le 3ème', 'the rule capacity:100',
                                  'result 4801e722aa', 'the f3 format', 'top250k',
                                  'gain of 2.8pp'])
def test_legitimate_text_is_not_an_odd_form(text):
    findings, _ = numtrace.trace_text(_pool(), text, 'draft')
    assert not [f for f in findings if (f.get('details') or {}).get('form')], findings


# --- R5E-1..R5E-9 together: follow next_action from init to done -----------------------------

CONCLUSION = ('The development evidence is all the study can cite: the final test was opened '
              'once.')
WORDS = {'model_choice': CHOOSE, 'policy': ADOPT, 'final_test': OPEN}
# The decisions whose value the junior states (the engine never drafts it): the prediction
# moment of a legacy study (the data card comes first) and the model choice.
JUNIOR_VALUES = ('prediction_time', 'model_choice')
# The reviewer's fragments (rule words, decision-value words, final-figure lines) and the
# decision titles.
ENGLISH_IN_FRENCH = ('Adopt only if', 'highest-scored rows', 'selected rows (precision',
                     'percentage points at the adopted rule', 'percentage points, interval',
                     'Positive rows found by the model', 'Baseline at the same rule',
                     'Mean absolute error,', 'Rule of these figures', 'Open the final test once',
                     'Use the linear model', 'Use the logistic model', 'Choose the model',
                     'Define the prediction moment')


def _junior_value(f, decision, task, review):
    if decision == 'prediction_time':
        return ('Predict using information available at the planted decision time' if review
                else 'when the record is created, before the outcome')
    return 'fit.linear' if task == 'regression' else 'fit.logistic'


def _words(decision, task):
    if decision == 'model_choice' and task == 'regression':
        return REG_WORDS
    return WORDS.get(decision) or fk.default_words(decision)


def _follow(f, task, review, limit=60):
    log = []
    for _ in range(limit):
        nxt = f.view()['next_action']
        kind = nxt['kind']
        log.append((kind, nxt.get('activity') or nxt.get('decision')))
        if kind in ('done', 'blocked'):
            return log, nxt
        if kind == 'show_data_card':
            nxt = {'kind': 'propose', 'decision': 'prediction_time'}
            kind = 'propose'
        if kind == 'run':
            digest = nxt['junior_digest']
            assert not digest.rstrip().endswith('?') or any(
                lead in digest for lead in ('Once it is done, you decide:',
                                            'It answers this question:',
                                            "c'est vous qui décidez :",
                                            'Il répond à cette question :')), digest
            args = [nxt['activity']]
            for rule in nxt.get('rules') or []:
                args += ['--rule', rule]
            for option, value in (nxt.get('options') or {}).items():
                args += [f'--{option}', str(value)]
            out = _run(f, *args)
            assert out.get('ok') and out['status'] in ('promoted', 'already_current'), (nxt, out)
        elif kind == 'await_user_words':
            out = f.call('decide', 'confirm', nxt['proposal_id'], '--user-words',
                         _words(nxt['decision'], task), '--request-id', f.rid(),
                         '--expected-revision', f.rev(), '--study', f.study, expect=None)
            assert out.get('ok'), (nxt, out)
        else:
            assert kind in ('propose', 'reconfirm'), nxt
            decision = nxt['decision']
            # Owner session 2026-10-26 (L1, R2c): a free choice lists the values the engine
            # accepts; at the conclusion they are the verdicts its rule allows.
            choices = [o['value'] for o in nxt.get('choice_options') or []]
            if kind == 'propose' and decision in ('conclusion', 'model_choice'):
                assert choices and nxt['pause']['kind'] == 'choice', nxt
            if decision == 'conclusion' and kind == 'propose':
                assert [c['verdict'] for c in choices] == (
                    nxt.get('verdicts') or [c['verdict'] for c in choices]), nxt
            if decision == 'conclusion':
                value = {'verdict': (nxt.get('verdicts') or ['inconclusive'])[0],
                         'text': CONCLUSION}
            else:
                value = nxt.get('default_value')
                if value is None:
                    value = (nxt.get('recommended') or {}).get('value')
                if value is None:
                    assert decision in JUNIOR_VALUES, nxt
                    value = _junior_value(f, decision, task, review)
                if decision == 'model_choice' and kind == 'propose':
                    assert value in choices, (value, choices)
            p = f.call('decide', 'propose', decision, '--value-json', json.dumps(value),
                       '--restatement', f'You decide the {decision} as stated.', '--rationale',
                       'It fits the scenario.', '--request-id', f.rid(), '--expected-revision',
                       f.rev(), '--study', f.study, expect=None)
            assert p.get('ok'), (nxt, p)
            out = f.call('decide', 'confirm', p['result']['proposal_id'], '--user-words',
                         _words(decision, task), '--request-id', f.rid(),
                         '--expected-revision', f.rev(), '--study', f.study, expect=None)
            assert out.get('ok'), (nxt, out)
    raise AssertionError(f'next_action did not settle: {log[-8:]}')


def _review_flow(base, task, delay, language, monkeypatch):
    if task == 'binary':
        f = ReviewFlow(base, outcome_delay=delay, language=language)
        f.init()
        return f
    mod = fk._module
    original = mod.make_case
    with monkeypatch.context() as m:
        m.setattr(mod, 'make_case', lambda out_dir, n_rows=300, **kw:
                  original(out_dir, task='regression', n_rows=n_rows))
        paths = mod.make_review_case(base / 'case-reg', future=True, outcome_delay=delay,
                                     n_rows=300)
    f = fk.Flow(base / 'reg', paths['case'].parent, prefix='reg')
    f.call('init', '--case', paths['case'], '--study', f.study, '--reliability-profile',
           'review-v1', '--lang', language)
    return f


def _legacy_flow(base, task, language):
    case_dir = fk.make_case(base / f'case-{task}', n_rows=300, task=task)['case'].parent
    f = fk.Flow(base / f'study-{task}', case_dir, prefix=task[:3])
    f.call('init', '--case', case_dir, '--study', f.study, '--lang', language)
    return f


CASES = [('legacy', 'binary', 0, 'en'), ('legacy', 'regression', 0, 'fr'),
         ('review', 'binary', 2, 'fr'), ('review', 'binary', 0, 'en'),
         ('review', 'regression', 5, 'en'), ('review', 'regression', 0, 'fr')]


@pytest.mark.parametrize('kind,task,delay,language', CASES)
def test_next_action_runs_as_given_from_init_to_done(tmp_path, monkeypatch, kind, task, delay,
                                                    language):
    """The reviewer's ``test_r5e_follow``, strict: every action is executed as the engine
    gives it (rules, options, default or recommended values, verdicts), each one accepted,
    with a stray ``.DS_Store`` in the installed runtime, and the report passes check."""
    _installed(monkeypatch, _copy_runtime(tmp_path, {'.DS_Store': b'\0\0\0\1Bud1'}))
    review = kind == 'review'
    f = (_review_flow(tmp_path, task, delay, language, monkeypatch) if review
         else _legacy_flow(tmp_path, task, language))
    log, last = _follow(f, task, review)
    assert last['kind'] == 'done', log[-5:]
    assert st.final_test_opened(f.state())
    f.call('render', '--study', f.study, expect=None)
    check = f.call('check', '--study', f.study, expect=None)
    assert check['counts'] == {'error': 0, 'warning': 0}, check['findings'][:5]
    import html
    report = html.unescape(next((Path(f.study) / 'reports').glob('*.html')).read_text('utf-8'))
    if language == 'fr':
        leaked = [w for w in ENGLISH_IN_FRENCH if w in report]
        assert not leaked, leaked
        if task == 'binary':
            assert 'lignes sélectionnées' in report and "N'adopter que si" in report
            assert 'points de pourcentage' in report
        else:
            assert 'Erreur absolue moyenne, ' in report


def test_a_french_report_writes_rules_and_values_in_french():
    from mlkit.study import render_html, texts
    with texts.report_language_context('fr'):
        assert render_html.rule_words('share:0.2') == ('Sélectionner les 20 % des lignes aux '
                                                       'scores les plus élevés')
        assert render_html.rule_words('threshold:0.3') == ('Sélectionner chaque ligne de '
                                                           'score 0,3 ou plus')
        assert render_html.value_words('success_criterion', {
            'metric': 'precision_gain', 'min_points': 5}, 'binary').startswith(
            "N'adopter que si la précision dépasse celle du modèle de référence d'au moins 5 "
            'points de pourcentage')
        assert render_html.value_words('model_choice', 'fit.linear', 'regression') == \
            'Utiliser le modèle linéaire'
    # The English report keeps its words.
    assert render_html.rule_words('share:0.2') == 'Select the 20% highest-scored rows'
    assert render_html.value_words('success_criterion', {
        'metric': 'precision_gain', 'min_points': 5}, 'binary') == (
        'Adopt only if the precision beats the baseline by at least 5 percentage points at '
        'the adopted rule')


# --- compatibility: the exact edges of the activities change --------------------------------

def test_the_round5_edges_target_the_current_bytes():
    now = hashlib.sha256((REPO / ACTIVITIES_FILE).read_bytes()).hexdigest()
    assert now == CURRENT, ('activities.py changed again: re-run code_compat_evidence.py '
                            'against the new bytes and, only if it matches, add new edges.')
    assert code_compat.integrity()
    for source in SOURCES.values():
        [record] = [r for r in code_compat.ATTESTATIONS if r['module'] == ACTS
                    and r['from_sha256'] == source and r['to_sha256'] == CURRENT]
        assert record['activities'] == ATTESTED
        assert 'framework/tests/study/test_review_round5_engine.py' in record['evidence']
        assert 'framework/tests/study/code_compat_evidence.py' in record['evidence']
    assert set(ATTESTED) == set(act.ACTIVITIES) - {act.CAPTURE, act.POPULATION}


def test_the_round5_edges_start_at_the_recorded_bytes():
    for commit, digest in SOURCES.items():
        probe = subprocess.run(['git', '-C', str(REPO), 'cat-file', '-e', f'{commit}^{{commit}}'],
                               capture_output=True)
        if probe.returncode != 0:
            pytest.skip(f'{commit} is not in this clone')
        blob = subprocess.run(['git', '-C', str(REPO), 'show', f'{commit}:{ACTIVITIES_FILE}'],
                              capture_output=True, check=True).stdout
        assert hashlib.sha256(blob).hexdigest() == digest, commit


def test_the_round5_edges_are_exact_and_leave_the_capture_out(tmp_path):
    case_dir = fk.make_case(tmp_path / 'case', n_rows=200)['case'].parent
    fk.Flow(tmp_path / 'study', case_dir).init()
    study = read.open(tmp_path / 'study')
    for source in SOURCES.values():
        for activity in ATTESTED:
            modules = dict(registry.code_fingerprint(list(act.MODULES[activity]))['modules'])
            modules[ACTS] = source
            assert study.code_changed({'activity': activity,
                                       'code': {'modules': modules}}) == [], activity
        assert not code_compat.equivalent(ACTS, source, CURRENT, act.CAPTURE)
        assert not code_compat.equivalent(ACTS, CURRENT, source, 'split')
