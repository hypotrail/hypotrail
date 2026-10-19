"""Replacing a slot's result invalidates what was computed from it (review finding H2).

Plan §3.7 row 11: a code change makes the affected activity and everything downstream
stale. The reviewer's ``t5.py`` ran ``fit.logistic`` with changed code: the new fit was
promoted, yet the policy evaluation computed from the old fit stayed current and the
adopted policy stayed confirmed. Here the engine runs from a modified copy of
``mlkit`` (a real code change, in a subprocess), and studies live in ``tmp_path``.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from mlkit.study import activities as act, dependencies as dep, read, view

import flowkit as fk
from flowkit import Flow

# WP-B1: the variant the evaluation compares is downstream of the split too.
DOWNSTREAM = ('eda.target_rate', 'fit.baseline', 'fit.logistic', 'fit.variant',
              'policy.evaluation')


@pytest.fixture(scope='module')
def adopted(tmp_path_factory, synthetic_case_dir):
    """Split, training EDA, both fits, an evaluation, and a confirmed policy."""
    study = fk.prepare(synthetic_case_dir, tmp_path_factory.mktemp('rep') / 'study')
    flow = Flow(study, synthetic_case_dir, prefix='a')
    flow.run('eda.target_rate')
    flow.run('policy.evaluate', '--rule', 'capacity:20')
    flow.decide('policy', 'capacity:20', words='Yes, call the twenty highest-scored clients')
    assert flow.state()['decisions']['policy']['status'] == 'confirmed'
    return study


def changed_engine(tmp_path: Path, module: str) -> Path:
    """A copy of ``mlkit`` where ``module`` (e.g. ``study/fit.py``) has changed source."""
    root = tmp_path / 'fw'
    shutil.copytree(fk.FRAMEWORK / 'mlkit', root / 'mlkit',
                    ignore=shutil.ignore_patterns('__pycache__'))
    path = root / 'mlkit' / module
    path.write_text(path.read_text(encoding='utf-8') + '\n# a code change (test)\n',
                    encoding='utf-8')
    return root


def hyp_with(engine: Path, *args, cwd) -> tuple[int, dict]:
    env = {k: v for k, v in os.environ.items()
           if k not in ('HYPOTRAIL_READ_ONLY', 'HYPOTRAIL_FAULT', 'HYPOTRAIL_TEST_HOOKS')}
    env['PYTHONPATH'] = str(engine)
    proc = subprocess.run([sys.executable, '-m', 'mlkit.study.cli', *map(str, args)],
                          capture_output=True, text=True, cwd=cwd, env=env, timeout=300)
    assert proc.stderr == '', proc.stderr
    return proc.returncode, json.loads(proc.stdout)


def _rev(study):
    return read.open(study).revision


def test_rerunning_the_split_makes_everything_downstream_stale(adopted, tmp_path,
                                                                synthetic_case_dir):
    study = fk.clone(adopted, tmp_path / 'study')
    before = read.open(study).state
    engine = changed_engine(tmp_path, 'study/activities.py')     # every activity's code
    _, out = hyp_with(engine, 'run', 'split', '--request-id', 'resplit',
                         '--expected-revision', _rev(study), '--study', study, cwd=tmp_path)
    assert out['status'] == 'promoted' and out['result']['slot'] == 'split', out
    assert out['result_id'] != before['current']['split']
    state = read.open(study).state
    for slot in DOWNSTREAM:
        assert state['current'][slot] in state['stale'], slot
    assert state['decisions']['policy']['status'] == 'reconfirm_required'
    assert state['decisions']['conclusion']['status'] == 'open'          # never confirmed
    record = state['invalidations'][-1]
    assert record['mutation'] == 'result_replaced' and record['decision_id'] == 'split'
    assert set(record['stale_slots']) == set(DOWNSTREAM)
    assert record['reconfirm_required'] == ['policy']
    _, status = hyp_with(engine, 'status', '--study', study, cwd=tmp_path)
    v = status['view']
    assert v['results']['split']['current'] is True
    assert not any(v['results'][s]['current'] for s in DOWNSTREAM)
    # The report rendered after the commit cites none of the stale results.
    consumed = v['artifacts']['items']['report']['consumed']
    assert not set(consumed) & {state['current'][s] for s in DOWNSTREAM}
    # Under the unchanged engine, the new split itself is flagged: its code differs.
    here = view.build(study)['results']['split']
    assert here['current'] is False and here['stale_reason']['code_changed'] == [
        'mlkit.study.activities']
    assert view.build(study)['artifacts']['status'] == 'stale'


def test_a_changed_fit_flags_then_invalidates_the_policy(adopted, tmp_path):
    study = fk.clone(adopted, tmp_path / 'study')
    engine = changed_engine(tmp_path, 'study/fit.py')
    # Row 11, detection: status under the changed code flags both fits and, downstream,
    # the policy evaluation; state is untouched (status is read-only).
    _, status = hyp_with(engine, 'status', '--study', study, cwd=tmp_path)
    results = status['view']['results']
    for slot in ('fit.baseline', 'fit.logistic', 'fit.variant', 'policy.evaluation'):
        assert results[slot]['current'] is False, slot
    assert results['fit.logistic']['stale_reason']['code_changed'] == ['mlkit.study.fit']
    assert results['policy.evaluation']['stale_reason']['upstream_not_current'] == [
        results['fit.baseline']['result_id'], results['fit.logistic']['result_id'],
        results['fit.variant']['result_id']]
    assert results['split']['current'] is True and results['eda.target_rate']['current'] is True
    flagged = next(x for x in status['view']['not_yet_defensible'] if x['id'] == 'code_changed')
    assert flagged['slots'] == ['fit.baseline', 'fit.logistic', 'fit.variant']
    # Rerunning the fit with the new code replaces it: the evaluation computed from the
    # old fit becomes stale and the adopted policy needs reconfirmation.
    old_eval = read.open(study).state['current']['policy.evaluation']
    _, out = hyp_with(engine, 'run', 'fit.logistic', '--request-id', 'refit',
                         '--expected-revision', _rev(study), '--study', study, cwd=tmp_path)
    assert out['status'] == 'promoted', out
    state = read.open(study).state
    assert old_eval in state['stale'] and state['current']['policy.evaluation'] == old_eval
    assert state['decisions']['policy']['status'] == 'reconfirm_required'
    assert state['current']['fit.logistic'] not in state['stale']
    assert out['result']['invalidation']['mutation'] == 'result_replaced'
    assert out['result']['invalidation']['row'] == 11
    assert out['result']['invalidation']['stale_slots'] == ['policy.evaluation']
    _, status = hyp_with(engine, 'status', '--study', study, cwd=tmp_path)
    report = status['view']['artifacts']['items']['report']
    assert old_eval not in report['consumed'] and report['status'] == 'ok'
    assert status['view']['results']['policy.evaluation']['current'] is False
    assert status['view']['decisions']['policy']['status'] == 'reconfirm_required'


def test_a_result_built_on_a_replaced_input_is_never_shown_current(adopted, tmp_path,
                                                                    synthetic_case_dir,
                                                                    monkeypatch):
    """A study written before this fix may hold a current evaluation whose fit was
    replaced; the view derives currency through ``inputs.results``."""
    study = fk.clone(adopted, tmp_path / 'study')
    monkeypatch.setattr(dep, 'apply_replacement', lambda *a, **k: None)
    monkeypatch.setitem(act.MODULES, act.LOGISTIC, act.MODULES[act.LOGISTIC] + ('mlkit.study.texts',))
    flow = Flow(study, synthetic_case_dir, prefix='b')
    assert flow.run('fit.logistic')['status'] == 'promoted'
    state = flow.state()
    assert state['current']['policy.evaluation'] not in state['stale']       # old behaviour
    v = view.build(study)
    assert v['results']['policy.evaluation']['current'] is False
    assert read.open(study).is_current('policy.evaluation') is False
