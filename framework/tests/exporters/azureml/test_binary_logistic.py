"""R19: the binary logistic model is in the team-azureml-v1 support matrix.

A temporary synthetic binary study goes through the engine's real commands: the logistic
fit and a stronger-regularised variant (still the ``logistic`` family), the policy adopted
for the variant (``capacity:40@fit.variant``), ``predictor.capture --profile workshop``
before the final test is opened, the opening, then ``hypotrail export azureml --plan`` and
``--out``. The exported folder is moved away; there, ``validate --offline``, ``predict``
(the positive-class score, equal to the captured parity outputs), the MLflow pyfunc alone
(it returns the score), ``materialize``, ``run-local --mode rebuild_final_candidate``, the
project's own pytest and ruff all run. The decision rule is metadata only: no output
applies it. A study whose chosen model is of a family the runtime does not qualify
(histogram boosting) is still refused with ``capability_not_supported``, never substituted.
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

RULE_WORDS = 'Yes, I adopt that rule because the desk can make that many calls'
OPEN = 'Yes, I open the final test now, because the model and the rule are fixed'
VARIANT_WORDS = 'Yes, retain the variant because it ranks best'


def _run(root: Path, *args, check=True):
    result = subprocess.run([sys.executable, *args], cwd=root, capture_output=True, text=True,
                            env=project_env(), check=False, timeout=900)
    if check:
        assert result.returncode == 0, (result.stdout[-3000:], result.stderr[-3000:])
    return result


def _json(result) -> dict:
    return json.loads(result.stdout[result.stdout.index('{'):])


def _open_final_test(flow):
    from mlkit.study import state as st
    value = st.b1_default_value(flow.state(), 'final_test')
    proposal = flow.call('decide', 'propose', 'final_test', '--value-json', json.dumps(value),
                         '--restatement', 'You open the sealed final test once.',
                         '--rationale', 'The model and the rule are chosen.',
                         '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                         '--study', flow.study)
    return flow.call('decide', 'confirm', proposal['result']['proposal_id'], '--user-words',
                     OPEN, '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                     '--study', flow.study, expect=None)


def _adopt_policy(flow, value: str):
    proposal = flow.call('decide', 'propose', 'policy', '--value-json', json.dumps(value),
                         '--restatement', 'You call the rows with the highest scores, up to the desk capacity.',
                         '--rationale', 'The desk capacity.', '--request-id', flow.rid(),
                         '--expected-revision', flow.rev(), '--study', flow.study)
    return flow.call('decide', 'confirm', proposal['result']['proposal_id'], '--user-words',
                     RULE_WORDS, '--request-id', flow.rid(), '--expected-revision',
                     flow.rev(), '--study', flow.study)


@pytest.fixture(scope='module')
def scenario(tmp_path_factory):
    import azureml_study as fx
    import flowkit as fk
    import libkit
    from mlkit.study import state as st
    base = tmp_path_factory.mktemp('binary')
    flow = libkit.study_at_fits(base, task='binary')
    flow.run('fit.baseline')
    flow.run('fit.logistic')
    flow.variant()                          # a stronger penalty: still the logistic family
    flow.run('policy.evaluate', '--rule', 'capacity:40')
    if st.has_explicit_binary_model_choice(flow.state()):
        flow.decide('model_choice', 'fit.variant', words=VARIANT_WORDS)
    _adopt_policy(flow, 'capacity:40@fit.variant')     # the rule, for the variant
    assert st.choice_config(flow.state()) == {'model': 'fit.variant', 'rule': 'capacity:40'}
    capture = flow.run('predictor.capture', '--profile', 'workshop')['values']
    assert [p['format'] for p in capture['packages']] == ['mlflow_pyfunc']
    opened = _open_final_test(flow)
    assert opened['result']['opening']['status'] == 'promoted', opened
    before = fk.tree_digest(flow.study)
    profile = fx.profile(base)
    plan = flow.call('export', 'azureml', '--plan', '--expected-revision', flow.rev(),
                     '--profile', profile, '--study', flow.study)
    out = base / 'export'
    export = flow.call('export', 'azureml', '--out', out, '--expected-revision', flow.rev(),
                       '--profile', profile, '--study', flow.study)
    moved = base / 'elsewhere' / 'binary-azureml'
    moved.parent.mkdir()
    shutil.copytree(out, moved)
    return {'flow': flow, 'capture': capture, 'plan': plan, 'export': export, 'out': out,
            'moved': moved, 'base': base, 'before': before}


def test_the_plan_and_the_export_carry_the_binary_logistic_model(scenario):
    import flowkit as fk
    assert scenario['plan']['ok'] and scenario['plan']['plan'] is True
    payload = scenario['export']
    assert payload['ok'] and payload['artifact_status'] == 'packaged'
    assert payload['snapshot_id'] == scenario['plan']['snapshot_id']
    assert fk.tree_digest(scenario['flow'].study) == scenario['before']     # read-only
    contracts = scenario['out'] / 'data/hypotrail/contracts'
    recipe = json.loads((contracts / 'model-recipe.json').read_text())
    assert (recipe['task'], recipe['family']) == ('binary', 'logistic')
    assert 'C' in recipe['parameters']                       # the regularised variant
    assert recipe['output_contract']['kind'] == 'binary_score'
    assert recipe['output_contract']['columns'] == ['score']
    positive = recipe['target']['positive_label']
    assert positive is not None and recipe['output_contract']['positive_label'] == positive
    snapshot = json.loads((contracts / 'deployment-snapshot.json').read_text())
    rule = snapshot['decision_rule']
    assert rule['rule'] == 'capacity:40' and rule['kind'] == 'capacity'
    assert rule['model'] == 'fit.variant' and rule['score_column'] == 'score'
    assert rule['applied_in_model_output'] is False and rule['needs_batch_ranking'] is True
    assert rule['positive_label'] == positive
    readiness = json.loads((contracts / 'readiness.json').read_text())
    assert readiness['evidence_status'] == 'evaluated'
    assert readiness['azure_qualification'] == 'not_qualified'
    assert readiness['decision_rule'] == {'rule': 'capacity:40', 'kind': 'capacity',
                                          'applied_in_model_output': False,
                                          'needs_batch_ranking': True}
    readme = (scenario['out'] / 'README.md').read_text()
    assert '`binary_score`' in readme and f'`{positive}`' in readme
    assert '`capacity:40`' in readme and 'never applied inside the model' in readme
    # No final-test row key in the exported plan.
    final_keys = set(fk.partition_keys(scenario['flow'].study, 'final_test'))
    plan = json.loads((contracts / 'development-plan.json').read_text())
    listed = {k for p in plan['partitions'] for k in p['row_keys']}
    assert listed and not listed & final_keys


def test_the_moved_project_validates_predicts_scores_and_rebuilds(scenario):
    import hypotrail_runtime as rt
    import pandas as pd
    from mlkit.integrations import mlflow_packaging as mp
    moved, base = scenario['moved'], scenario['base']
    report = _json(_run(moved, '-m', 'src.pipeline.utils.project', 'validate', '--offline'))
    statuses = {c['id']: c['status'] for c in report['checks']}
    assert statuses['contract_identities'] == 'passed'
    assert statuses['evaluated_model_parity'] == 'passed'
    assert statuses['evaluated_model_mlflow_package'] == 'passed'
    # predict: the positive-class scores of the parity rows, equal to the captured ones.
    predictions = base / 'predictions.json'
    _run(moved, '-m', 'src.pipeline.utils.project', 'predict', '--parity', '--output',
         str(predictions))
    document = json.loads(predictions.read_text())
    assert document['predictor_id'] == scenario['capture']['predictor_id']
    assert document['columns'] == ['score']
    assert document['output_contract']['kind'] == 'binary_score'
    assert document['decision_rule']['applied_in_model_output'] is False
    scores = pd.DataFrame(document['rows'])
    assert ((scores['score'] >= 0) & (scores['score'] <= 1)).all()
    bundle = moved / 'data/hypotrail/models/evaluated'
    desc = rt.verify_bundle(bundle)
    expected = mp.read_table(bundle / desc.bundle.parity.expected_outputs_path)
    # The document rounds to 10 digits (JSON records); the bundle's parity holds exactly.
    assert mp.compare(scores, expected, 1e-8, 1e-9)['equal']
    # The MLflow pyfunc alone, in a fresh isolated process, returns the score.
    package = bundle / desc.bundle.optional_packages[0].relative_path
    copy = base / 'pyfunc-alone'
    shutil.copytree(package, copy)
    script = ('import json, sys, mlflow.pyfunc\n'
              'import hypotrail_runtime.predictor as rp\n'
              'model = mlflow.pyfunc.load_model(sys.argv[1])\n'
              'features = rp.frame_from_document(json.load(open(sys.argv[2])))\n'
              'out = model.predict(features)\n'
              'print(json.dumps({"columns": list(out.columns), '
              '"score": out["score"].tolist()}))\n')
    result = subprocess.run([sys.executable, '-I', '-c', script, str(copy),
                             str(bundle / desc.bundle.parity.features_path)],
                            cwd=base, capture_output=True, text=True, env=project_env(),
                            check=False, timeout=600)
    assert result.returncode == 0, result.stderr[-2000:]
    pyfunc = json.loads(result.stdout.strip().splitlines()[-1])
    assert pyfunc['columns'] == ['score']
    assert mp.compare(pd.DataFrame({'score': pyfunc['score']}), expected, 1e-10,
                      1e-12)['equal']
    # The four steps on the materialised development rows: a new candidate, technical
    # checks only, the rule reported and not applied.
    source = base / 'original.csv'
    shutil.copyfile(scenario['flow'].case_dir / 'data.csv', source)
    _run(moved, '-m', 'src.pipeline.utils.project', 'materialize', '--source', str(source))
    report = _json(_run(moved, '-m', 'src.pipeline.utils.project', 'validate', '--offline'))
    assert report['status'] == 'passed', report
    run_dir = base / 'run'
    run = _json(_run(moved, '-m', 'src.pipeline.utils.project', 'run-local', '--mode',
                     'rebuild_final_candidate', '--run-dir', str(run_dir)))
    assert run['ok'] and run['role'] == 'rebuilt_candidate'
    assert run['scientific_verdict'] == 'not_inherited'
    technical = json.loads(next(run_dir.rglob('technical-report.json')).read_text())
    checks = {c['id']: c['status'] for c in technical['checks']}
    assert checks['candidate_scores_are_probabilities'] == 'passed'
    assert checks['candidate_within_evaluated_tolerance'] == 'passed'
    assert checks['mlflow_package_parity'] == 'passed'
    assert technical['generalisation_metrics'] is None
    assert technical['output_kind'] == 'binary_score'
    assert technical['decision_rule']['rule'] == 'capacity:40'
    assert technical['decision_rule']['applied_in_model_output'] is False
    assert technical['candidate_predictor_id'] != scenario['capture']['predictor_id']
    prepared = json.loads(next(run_dir.rglob('validation-report.json')).read_text())
    encoding = prepared['target_encoding']
    assert encoding['positive_label'] == json.loads(
        (moved / 'data/hypotrail/contracts/model-recipe.json').read_text()
    )['target']['positive_label']
    assert encoding['n_positive'] > 0 and encoding['n_negative'] > 0


def test_the_project_tests_and_the_team_lint_pass(scenario):
    moved = scenario['moved']
    result = _run(moved, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', check=False)
    assert result.returncode == 0, result.stdout[-3000:]
    ruff = shutil.which('ruff', path=str(Path(sys.executable).parent))
    if ruff is None:
        pytest.skip('ruff is not installed next to this interpreter')
    lint = subprocess.run([ruff, 'check', '--no-cache', 'src'], cwd=moved, capture_output=True,
                          text=True, check=False, timeout=300)
    assert lint.returncode == 0, lint.stdout[-3000:]


def test_a_study_that_chose_histogram_boosting_is_refused_not_substituted(tmp_path):
    """The HGB variant chosen, the final test opened without a capture (the runtime cannot
    capture it): the export refuses on the family, writes nothing, and never offers the
    logistic model in its place."""
    import azureml_study as fx
    import flowkit as fk
    import libkit
    from mlkit.study import state as st
    flow = libkit.study_at_fits(tmp_path, task='binary', n_rows=300)
    flow.run('fit.baseline')
    flow.run('fit.logistic')
    flow.run('diag.binary')
    flow.decide('model_variant', {'variants': [{'kind': 'family', 'family': 'hgb',
                                                'question': 'Does boosting rank better?'}]})
    flow.run('fit.variant')
    flow.run('policy.evaluate', '--rule', 'capacity:30')
    if st.has_explicit_binary_model_choice(flow.state()):
        flow.decide('model_choice', 'fit.variant', words=VARIANT_WORDS)
    _adopt_policy(flow, 'capacity:30@fit.variant')     # the rule, for the variant
    refused = flow.run('predictor.capture', '--profile', 'workshop', expect=None)
    assert refused['ok'] is False
    assert refused['error']['details']['contract_code'] == 'capability_not_supported'
    assert _open_final_test(flow)['result']['opening']['status'] == 'promoted'
    before = fk.tree_digest(flow.study)
    for extra in (['--plan'], ['--out', tmp_path / 'export']):
        payload = flow.call('export', 'azureml', *extra, '--expected-revision', flow.rev(),
                            '--profile', fx.profile(tmp_path), '--study', flow.study,
                            expect=None)
        assert payload['ok'] is False
        error = payload['error']
        assert error['code'] == 'capability_not_supported'
        assert error['details']['reason'] == 'family_not_supported'
        assert error['details']['family'] == 'hgb'
        assert error['details']['path'] == 'model_recipe.family'
        assert {'task': 'binary', 'family': 'logistic', 'output_kind': 'binary_score'} in [
            {k: c[k] for k in ('task', 'family', 'output_kind')}
            for c in error['details']['supported']]
        assert 'captur' not in error['details']['remediation'].lower()
    assert not (tmp_path / 'export').exists()
    assert fk.tree_digest(flow.study) == before
