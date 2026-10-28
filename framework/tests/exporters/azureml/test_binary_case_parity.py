"""NR-19 (owner session 2026-10-26, §6.2 item 3): the binary logistic export on a Bank-like
and a Hotel-like study, native vs expected vs MLflow pyfunc.

R19 qualified binary ``logistic`` on a synthetic binary study. This deep validation takes
two studies whose data have the shape of the workshop's binary cases through the engine's
real commands (fits, policy, ``predictor.capture --profile workshop``, the opening, then
``export azureml --out``), and checks the exported model where an engineer would use it:

* **Bank-like**: the committed Bank Marketing case (``use-cases/bank-marketing``, read only):
  a text target (``yes``/``no``, positive ``yes``), categorical ``unknown`` special values,
  ``pdays = -1``, about one positive in nine, a stratified final test;
* **Hotel-like**: a temporary case derived from the committed Hotel booking case (every
  tenth booking, arrival order kept, the case's statements unchanged but the dataset's
  bytes, rows and digest): a numeric ``0``/``1`` target, ``order: {by: line}`` (a temporal
  final test), duplicate groups, missing values, a many-valued ``country``.

For each, in the moved project: the native bundle's predictions, the bundle's expected
outputs and the MLflow pyfunc (a fresh isolated process) agree at ``rtol 1e-10``,
``atol 1e-12`` (never relaxed); the pyfunc returns the positive-class ``score`` only; the
adopted rule is metadata (``applied_in_model_output: false``) and no output applies it.
Studies and derived cases live in temporary folders; committed cases are only read.
"""
from __future__ import annotations

import hashlib
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

RTOL, ATOL = 1e-10, 1e-12
RULE = 'share:0.1'


def _hotel_like(out: Path, every: int = 10) -> Path:
    """A Hotel-like case: every ``every``-th booking of the committed Hotel case, in
    arrival order; only the dataset's bytes, rows and digest change."""
    import yaml
    import flowkit as fk
    source = fk.REPO / 'use-cases' / 'hotel-booking'
    document = yaml.safe_load((source / 'case.yaml').read_text(encoding='utf-8'))
    lines = (source / document['dataset']['path']).read_bytes().split(b'\n')
    header, rows = lines[0], [r for r in lines[1:] if r]
    kept = rows[::every]
    data = b'\n'.join([header, *kept]) + b'\n'
    (out / 'data').mkdir(parents=True)
    (out / document['dataset']['path']).write_bytes(data)
    document['id'] = 'hotel-like-test-v1'
    document['dataset']['rows'] = len(kept)
    document['dataset']['sha256'] = hashlib.sha256(data).hexdigest()
    (out / 'case.yaml').write_text(yaml.safe_dump(document, sort_keys=False,
                                                  allow_unicode=True), encoding='utf-8')
    return out


def _run(root: Path, *args):
    result = subprocess.run([sys.executable, *args], cwd=root, capture_output=True, text=True,
                            env=project_env(), check=False, timeout=900)
    assert result.returncode == 0, (result.stdout[-3000:], result.stderr[-3000:])
    return result


@pytest.fixture(scope='module', params=['bank', 'hotel'])
def exported(request, tmp_path_factory):
    import azureml_study as fx
    import flowkit as fk
    import libkit
    from mlkit.study import state as st
    from test_binary_logistic import _adopt_policy, _open_final_test
    base = tmp_path_factory.mktemp(request.param)
    case_dir = (fk.REPO / 'use-cases' / 'bank-marketing' if request.param == 'bank'
                else _hotel_like(base / 'case'))
    flow = libkit.study_at_fits(base, task='binary', case_dir=case_dir)
    flow.run('fit.baseline')
    flow.run('fit.logistic')
    flow.run('policy.evaluate', '--rule', RULE)
    if st.has_explicit_binary_model_choice(flow.state()):
        flow.decide('model_choice', 'fit.logistic')
    _adopt_policy(flow, RULE)
    assert st.choice_config(flow.state()) == {'model': 'fit.logistic', 'rule': RULE}
    capture = flow.run('predictor.capture', '--profile', 'workshop')['values']
    assert [p['format'] for p in capture['packages']] == ['mlflow_pyfunc']
    opened = _open_final_test(flow)
    assert opened['result']['opening']['status'] == 'promoted', opened
    out = base / 'export'
    payload = flow.call('export', 'azureml', '--out', out, '--expected-revision', flow.rev(),
                        '--profile', fx.profile(base), '--study', flow.study)
    moved = base / 'elsewhere' / f'{request.param}-azureml'
    moved.parent.mkdir()
    shutil.copytree(out, moved)
    return {'name': request.param, 'flow': flow, 'payload': payload, 'moved': moved,
            'base': base, 'capture': capture}


def test_native_expected_and_pyfunc_agree(exported):
    import pandas as pd
    import hypotrail_runtime as rt
    from mlkit.integrations import mlflow_packaging as mp
    moved, base = exported['moved'], exported['base']
    assert exported['payload']['artifact_status'] == 'packaged'
    bundle = moved / 'data/hypotrail/models/evaluated'
    desc = rt.verify_bundle(bundle)
    recipe = json.loads((moved / 'data/hypotrail/contracts/model-recipe.json').read_text())
    assert (recipe['task'], recipe['family']) == ('binary', 'logistic')
    assert recipe['output_contract']['kind'] == 'binary_score'
    positive = recipe['target']['positive_label']
    assert positive == ('yes' if exported['name'] == 'bank' else '1')
    expected = mp.read_table(bundle / desc.bundle.parity.expected_outputs_path)
    features = rt.predictor.frame_from_document(
        json.loads((bundle / desc.bundle.parity.features_path).read_text()))
    assert len(features) == len(expected) > 0
    # Native: the bundle loaded by the runtime (trusted: the test made it).
    native = rt.load_predictor(bundle, trusted_roots=[moved]).predict(features)
    assert native.kind == 'binary_score' and native.columns == ['score']
    assert mp.compare(pd.DataFrame({'score': native.values}), expected, RTOL, ATOL)['equal']
    # MLflow pyfunc alone, in a fresh isolated process, after the move.
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
    scores = pd.DataFrame({'score': pyfunc['score']})
    assert mp.compare(scores, expected, RTOL, ATOL)['equal']
    assert mp.compare(scores, pd.DataFrame({'score': native.values}), RTOL, ATOL)['equal']
    # A score, not a decision: probabilities, not the 0/1 of an applied rule.
    assert ((scores['score'] > 0) & (scores['score'] < 1)).all()
    assert scores['score'].nunique() > 2


def test_the_rule_is_metadata_and_the_project_validates(exported):
    moved = exported['moved']
    contracts = moved / 'data/hypotrail/contracts'
    snapshot = json.loads((contracts / 'deployment-snapshot.json').read_text())
    rule = snapshot['decision_rule']
    assert rule['rule'] == RULE and rule['kind'] == 'share'
    assert rule['applied_in_model_output'] is False and rule['needs_batch_ranking'] is True
    readiness = json.loads((contracts / 'readiness.json').read_text())
    assert readiness['decision_rule']['applied_in_model_output'] is False
    assert readiness['azure_qualification'] == 'not_qualified'
    out = _run(moved, '-m', 'src.pipeline.utils.project', 'validate', '--offline').stdout
    report = json.loads(out[out.index('{'):])
    statuses = {c['id']: c['status'] for c in report['checks']}
    assert statuses['evaluated_model_parity'] == 'passed'
    assert statuses['evaluated_model_mlflow_package'] == 'passed'
    assert statuses['contract_identities'] == 'passed'
    predictions = exported['base'] / 'predictions.json'
    _run(moved, '-m', 'src.pipeline.utils.project', 'predict', '--parity', '--output',
         str(predictions))
    document = json.loads(predictions.read_text())
    assert document['columns'] == ['score']
    assert document['decision_rule']['applied_in_model_output'] is False
    # No final-test row key in the exported plan.
    import flowkit as fk
    final_keys = set(fk.partition_keys(exported['flow'].study, 'final_test'))
    plan = json.loads((contracts / 'development-plan.json').read_text())
    listed = {k for p in plan['partitions'] for k in p['row_keys']}
    assert listed and not listed & final_keys
