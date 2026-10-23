"""The real end-to-end scenario of the integration (spec §16; AC07, AC19, AC21–AC24, AC26).

No backend is simulated: a temporary Auto MPG study (the committed case, only read) goes
through the engine's real commands; ``predictor.capture --profile workshop`` fits the
complete predictor and packages it with the real MLflow packager before the final test is
opened; the final test scores the reloaded capture and binds its evidence;
``hypotrail export azureml`` reads the study through ``read_export_source``; the exported
folder is moved away from the study and the repository; there, the native predictor and the
MLflow pyfunc load and reproduce the parity outputs, the development rows are materialised
from the original source file, the four steps are replayed, and the rebuilt candidate has a
new identity and no inherited verdict.
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

AUTO_SOURCE = Path(__file__).resolve().parents[4] / 'use-cases' / 'auto-mpg' / 'data' / \
    'auto-mpg.data'
WORDS = 'Yes, I choose that model because its error is smaller'
OPEN = 'Yes, I open the final test now, because the model and the rule are fixed'


def _run(root: Path, *args, check=True):
    result = subprocess.run([sys.executable, *args], cwd=root, capture_output=True, text=True,
                            env=project_env(), check=False, timeout=900)
    if check:
        assert result.returncode == 0, (result.stdout[-3000:], result.stderr[-3000:])
    return result


def _json(result) -> dict:
    return json.loads(result.stdout[result.stdout.index('{'):])


@pytest.fixture(scope='module')
def scenario(tmp_path_factory):
    import azureml_study as fx
    import libkit
    from mlkit.study import state as st
    base = tmp_path_factory.mktemp('e2e')
    flow = libkit.study_at_fits(base, case_dir=libkit.AUTO)
    flow.run('fit.baseline')
    flow.run('fit.linear')
    flow.variant()
    flow.run('evaluate.regression')
    flow.decide('model_choice', 'fit.linear', words=WORDS)
    capture = flow.run('predictor.capture', '--profile', 'workshop')['values']
    assert [p['format'] for p in capture['packages']] == ['mlflow_pyfunc']
    assert not st.final_test_opened(flow.state())          # packaged before the opening
    value = st.b1_default_value(flow.state(), 'final_test')
    proposal = flow.call('decide', 'propose', 'final_test', '--value-json', json.dumps(value),
                         '--restatement', 'You open the sealed final test once.',
                         '--rationale', 'The model is chosen.', '--request-id', flow.rid(),
                         '--expected-revision', flow.rev(), '--study', flow.study)
    opened = flow.call('decide', 'confirm', proposal['result']['proposal_id'], '--user-words',
                       OPEN, '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                       '--study', flow.study)
    assert opened['result']['opening']['status'] == 'promoted'
    import flowkit as fk
    before = fk.tree_digest(flow.study)
    out = base / 'export'
    export = flow.call('export', 'azureml', '--out', out, '--expected-revision', flow.rev(),
                       '--profile', fx.profile(base), '--study', flow.study)
    return {'flow': flow, 'capture': capture, 'export': export, 'out': out, 'base': base,
            'before': before}


def test_the_export_carries_the_evaluated_package(scenario):
    import flowkit as fk
    payload = scenario['export']
    assert payload['ok'] and payload['artifact_status'] == 'packaged'
    readiness = json.loads((scenario['out'] / 'data/hypotrail/contracts/readiness.json')
                           .read_text())
    assert readiness['evidence_status'] == 'evaluated'
    assert readiness['azure_job'] == 'not_submitted'
    assert readiness['azure_qualification'] == 'not_qualified'
    # The study is unchanged by the export (read-only source).
    flow = scenario['flow']
    assert fk.tree_digest(flow.study) == scenario['before']
    # No final-test row key and no study path in the exported bytes.
    final_keys = set(fk.partition_keys(flow.study, 'final_test'))
    plan = json.loads((scenario['out'] / 'data/hypotrail/contracts/development-plan.json')
                      .read_text())
    listed = {k for p in plan['partitions'] for k in p['row_keys']}
    assert listed and not listed & final_keys
    for path in scenario['out'].rglob('*'):
        if path.is_file() and path.suffix in ('.json', '.yaml', '.yml', '.md', '.py', '.lock'):
            assert str(flow.study) not in path.read_text(errors='ignore'), path


def test_the_moved_project_loads_replays_and_rebuilds(scenario):
    moved = scenario['base'] / 'elsewhere' / 'auto-mpg-azureml'
    moved.parent.mkdir()
    shutil.copytree(scenario['out'], moved)
    source = scenario['base'] / 'original.data'
    shutil.copyfile(AUTO_SOURCE, source)
    _run(moved, '-m', 'src.pipeline.utils.project', 'materialize', '--source', str(source))
    report = _json(_run(moved, '-m', 'src.pipeline.utils.project', 'validate', '--offline'))
    statuses = {c['id']: c['status'] for c in report['checks']}
    assert report['status'] == 'passed', report
    assert statuses['evaluated_model_parity'] == 'passed'
    assert statuses['evaluated_model_mlflow_package'] == 'passed'
    assert statuses['development_rows'] == 'passed'
    predictions = scenario['base'] / 'predictions.json'
    _run(moved, '-m', 'src.pipeline.utils.project', 'predict', '--parity', '--output',
         str(predictions))
    document = json.loads(predictions.read_text())
    assert document['predictor_id'] == scenario['capture']['predictor_id']
    assert document['output_contract']['unit'] == 'mpg'
    run = _json(_run(moved, '-m', 'src.pipeline.utils.project', 'run-local', '--mode',
                     'rebuild_final_candidate', '--run-dir', str(scenario['base'] / 'run')))
    assert run['ok'] and run['role'] == 'rebuilt_candidate'
    assert run['scientific_verdict'] == 'not_inherited'


def test_the_pyfunc_package_loads_alone_and_matches_the_native_model(scenario):
    import hypotrail_runtime as rt
    from mlkit.integrations import mlflow_packaging as mp
    bundle = scenario['out'] / 'data/hypotrail/models/evaluated'
    desc = rt.verify_bundle(bundle)
    package = bundle / desc.bundle.optional_packages[0].relative_path
    copy = scenario['base'] / 'pyfunc-alone'
    shutil.copytree(package, copy)
    script = ('import json, sys, mlflow.pyfunc\n'
              'import hypotrail_runtime.predictor as rp\n'
              'model = mlflow.pyfunc.load_model(sys.argv[1])\n'
              'features = rp.frame_from_document(json.load(open(sys.argv[2])))\n'
              'print(json.dumps(model.predict(features)["prediction"].tolist()))\n')
    result = subprocess.run([sys.executable, '-I', '-c', script, str(copy),
                             str(bundle / desc.bundle.parity.features_path)],
                            cwd=scenario['base'], capture_output=True, text=True,
                            env=project_env(), check=False, timeout=600)
    assert result.returncode == 0, result.stderr[-2000:]
    predicted = json.loads(result.stdout.strip().splitlines()[-1])
    expected = mp.read_table(bundle / desc.bundle.parity.expected_outputs_path)
    import pandas as pd
    assert mp.compare(pd.DataFrame({'prediction': predicted}), expected, 1e-10,
                      1e-12)['equal']


def test_a_repeated_export_is_byte_identical_and_a_used_target_is_refused(scenario):
    import azureml_study as fx
    flow = scenario['flow']
    again = scenario['base'] / 'again'
    second = flow.call('export', 'azureml', '--out', again, '--expected-revision', flow.rev(),
                       '--profile', fx.profile(scenario['base']), '--study', flow.study)
    assert second['export_id'] == scenario['export']['export_id']
    refused = flow.call('export', 'azureml', '--out', scenario['out'], '--expected-revision',
                        flow.rev(), '--study', flow.study, expect=None)
    assert refused['ok'] is False
    stale = flow.call('export', 'azureml', '--out', scenario['base'] / 'stale',
                      '--expected-revision', flow.rev() - 1, '--study', flow.study,
                      expect=None)
    assert stale['ok'] is False


def test_a_study_evaluated_without_capture_exports_its_recipe_only(tmp_path):
    """An older-style study (final test opened without any capture): the export describes
    the recipe from the chosen configuration, carries no model, and invents no evidence."""
    import azureml_study as fx
    import flowkit as fk
    import libkit
    from mlkit.study import state as st
    flow = libkit.study_at_fits(tmp_path, case_dir=libkit.AUTO)
    flow.run('fit.baseline')
    flow.run('fit.linear')
    flow.variant()
    flow.run('evaluate.regression')
    flow.decide('model_choice', 'fit.linear', words=WORDS)
    value = st.b1_default_value(flow.state(), 'final_test')
    proposal = flow.call('decide', 'propose', 'final_test', '--value-json', json.dumps(value),
                         '--restatement', 'You open the sealed final test once.',
                         '--rationale', 'The model is chosen.', '--request-id', flow.rid(),
                         '--expected-revision', flow.rev(), '--study', flow.study)
    flow.call('decide', 'confirm', proposal['result']['proposal_id'], '--user-words', OPEN,
              '--request-id', flow.rid(), '--expected-revision', flow.rev(),
              '--study', flow.study)
    before = fk.tree_digest(flow.study)
    out = tmp_path / 'export'
    payload = flow.call('export', 'azureml', '--out', out, '--expected-revision', flow.rev(),
                        '--profile', fx.profile(tmp_path), '--study', flow.study)
    assert fk.tree_digest(flow.study) == before
    assert payload['artifact_status'] == 'missing'
    assert not (out / 'data/hypotrail/models/evaluated').exists()
    readiness = json.loads((out / 'data/hypotrail/contracts/readiness.json').read_text())
    assert readiness['evidence_status'] != 'evaluated'
    recipe = json.loads((out / 'data/hypotrail/contracts/model-recipe.json').read_text())
    assert recipe['family'] == 'linear' and recipe['task'] == 'regression'
