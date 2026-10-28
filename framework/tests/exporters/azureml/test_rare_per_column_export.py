"""Owner session 2026-10-26, lot L8 (R6) with R19 (NR-19): a per-column rare grouping goes
through the capture and the Azure ML export, binary and regression.

A study whose preparation groups rare categories with a minimum per column records the
recipe operation ``rare_category`` in version 2 (``min_rows: {column: n}``). The capture fits
it with the runtime (which reads versions 1 and 2), the export carries it through the
project configuration unchanged, and the moved project validates offline (identities, parity
of the evaluated model and of its MLflow package), predicts the captured parity outputs and
rebuilds a candidate within the evaluated tolerance. The tolerances are the project's own,
never relaxed here.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from export_env import needs_hydra, needs_mlflow, project_env

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'study'))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'study' / 'libraries'))

pytestmark = [needs_mlflow, needs_hydra]

OPEN = 'Yes, I open the final test now, because the model and the rule are fixed'
RULE_WORDS = 'Yes, I adopt that rule because the desk can make that many calls'
MODEL_WORDS = 'Yes, I choose that model because its error is smaller'
AUTO_SOURCE = Path(__file__).resolve().parents[4] / 'use-cases' / 'auto-mpg' / 'data' / \
    'auto-mpg.data'
# The per-column minimums: the synthetic binary case folds the rarest lapse reasons; Auto MPG
# folds the rarest origin.
GROUPING = {'binary': {'last_lapse_reason': 50, 'last_reminder_weekday': 70},
            'regression': {'origin': 60}}


def _run(root: Path, *args, check=True):
    result = subprocess.run([sys.executable, *args], cwd=root, capture_output=True, text=True,
                            env=project_env(), check=False, timeout=900)
    if check:
        assert result.returncode == 0, (result.stdout[-3000:], result.stderr[-3000:])
    return result


def _json(result) -> dict:
    return json.loads(result.stdout[result.stdout.index('{'):])


def _confirm(flow, decision, value, words):
    proposal = flow.call('decide', 'propose', decision, '--value-json', json.dumps(value),
                         '--restatement', f'You decide the {decision} as stated.',
                         '--rationale', 'It fits the scenario.', '--request-id', flow.rid(),
                         '--expected-revision', flow.rev(), '--study', flow.study)
    return flow.call('decide', 'confirm', proposal['result']['proposal_id'], '--user-words',
                     words, '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                     '--study', flow.study)


@pytest.fixture(scope='module', params=['binary', 'regression'])
def exported(request, tmp_path_factory):
    import azureml_study as fx
    import libkit
    from mlkit.study import governance, state as st
    task = request.param
    base = tmp_path_factory.mktemp(f'rare-{task}')
    preprocessing = {**governance.DEFAULT_PREPROCESSING,
                     'rare_category_min_rows': GROUPING[task]}
    if task == 'binary':
        flow = libkit.study_at_fits(base, task='binary', n_rows=600,
                                    preprocessing=preprocessing)
        flow.run('fit.baseline')
        flow.run('fit.logistic')
        flow.variant()
        flow.run('policy.evaluate', '--rule', 'capacity:40')
        if st.has_explicit_binary_model_choice(flow.state()):
            flow.decide('model_choice', 'fit.logistic', words=MODEL_WORDS)
        _confirm(flow, 'policy', 'capacity:40', RULE_WORDS)
        source = flow.case_dir / 'data.csv'
    else:
        flow = libkit.study_at_fits(base, case_dir=libkit.AUTO, preprocessing=preprocessing)
        flow.run('fit.baseline')
        flow.run('fit.linear')
        flow.variant()
        flow.run('evaluate.regression')
        flow.decide('model_choice', 'fit.linear', words=MODEL_WORDS)
        source = AUTO_SOURCE
    capture = flow.run('predictor.capture', '--profile', 'workshop')['values']
    value = st.b1_default_value(flow.state(), 'final_test')
    opened = _confirm(flow, 'final_test', value, OPEN)
    assert opened['result']['opening']['status'] == 'promoted', opened
    out = base / 'export'
    export = flow.call('export', 'azureml', '--out', out, '--expected-revision', flow.rev(),
                       '--profile', fx.profile(base), '--study', flow.study)
    moved = base / 'elsewhere' / f'{task}-azureml'
    moved.parent.mkdir()
    shutil.copytree(out, moved)
    return {'task': task, 'flow': flow, 'capture': capture, 'export': export, 'out': out,
            'moved': moved, 'base': base, 'source': source}


def test_the_recipe_carries_the_grouping_per_column(exported):
    from mlkit.study import read
    task = exported['task']
    assert exported['export']['ok'] and exported['export']['artifact_status'] == 'packaged'
    slot = 'fit.logistic' if task == 'binary' else 'fit.linear'
    fitted = read.open(exported['flow'].study).current(slot)['output']['values'][
        'preprocessing']['fitted']
    assert set(fitted['rare_categories']) == set(GROUPING[task])
    assert all(v['folded'] for v in fitted['rare_categories'].values())    # it groups some
    contracts = exported['out'] / 'data/hypotrail/contracts'
    recipe = json.loads((contracts / 'model-recipe.json').read_text())
    [step] = [s for s in recipe['preprocessing'] if s['operation'] == 'rare_category']
    assert step == {'operation': 'rare_category', 'version': 2,
                    'parameters': {'min_rows': GROUPING[task]}}


def test_the_moved_project_validates_predicts_and_rebuilds(exported):
    import hypotrail_runtime as rt
    import pandas as pd
    from mlkit.integrations import mlflow_packaging as mp
    moved, base, task = exported['moved'], exported['base'], exported['task']
    report = _json(_run(moved, '-m', 'src.pipeline.utils.project', 'validate', '--offline'))
    statuses = {c['id']: c['status'] for c in report['checks']}
    assert statuses['contract_identities'] == 'passed'
    assert statuses['evaluated_model_parity'] == 'passed'
    assert statuses['evaluated_model_mlflow_package'] == 'passed'
    predictions = base / 'predictions.json'
    _run(moved, '-m', 'src.pipeline.utils.project', 'predict', '--parity', '--output',
         str(predictions))
    document = json.loads(predictions.read_text())
    assert document['predictor_id'] == exported['capture']['predictor_id']
    column = 'score' if task == 'binary' else 'prediction'
    bundle = moved / 'data/hypotrail/models/evaluated'
    desc = rt.verify_bundle(bundle)
    expected = mp.read_table(bundle / desc.bundle.parity.expected_outputs_path)
    # The document rounds to 10 digits (JSON records); the bundle's parity holds exactly.
    assert mp.compare(pd.DataFrame(document['rows'])[[column]], expected, 1e-8, 1e-9)['equal']
    source = base / 'original'
    shutil.copyfile(exported['source'], source)
    _run(moved, '-m', 'src.pipeline.utils.project', 'materialize', '--source', str(source))
    report = _json(_run(moved, '-m', 'src.pipeline.utils.project', 'validate', '--offline'))
    assert report['status'] == 'passed', report
    run_dir = base / 'run'
    run = _json(_run(moved, '-m', 'src.pipeline.utils.project', 'run-local', '--mode',
                     'rebuild_final_candidate', '--run-dir', str(run_dir)))
    assert run['ok'] and run['role'] == 'rebuilt_candidate'
    technical = json.loads(next(run_dir.rglob('technical-report.json')).read_text())
    checks = {c['id']: c['status'] for c in technical['checks']}
    assert checks['candidate_within_evaluated_tolerance'] == 'passed'
    assert checks['mlflow_package_parity'] == 'passed'
