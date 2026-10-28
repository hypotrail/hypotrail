"""Regressions of the fifth review round of 25 October 2026, area A (library runtime).

R5-A1 the MLflow package pinned ``hypotrail-runtime==1.0.0`` from an index while the bundle
ships its own wheel, and nothing compared the installed runtime with that wheel: a runtime
of the same version with other code served other predictions under the evaluated predictor
id. Now the package's environment installs the embedded wheel by its path inside the
package, the wrapper refuses to serve unless the installed runtime is, file for file, the
bound wheel (checked before anything of it is imported) and reproduces the parity rows, and
``load_predictor`` (final test, export, exported project) makes the same runtime check.
R5-A2 the evidence folder admitted any file, inside a package's embedded bundle too: the
embedded bundle now carries no ``evidence/`` folder at all, and a bundle's ``evidence/``
holds evidence bindings only. R5-A3 a reused bundle's packages are compared with the ones
the capture has just built. Ported from the reviewer's probes; every bundle, study and
environment lives in ``tmp_path`` and the data are synthetic.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import numpy as np
import pytest
import yaml

import hypotrail_runtime
from hypotrail_runtime import (canonical, capture_predictor, check_parity, load_predictor,
                               verify_bundle, write_evidence_binding)
from hypotrail_runtime import predictor as runtime_predictor
from hypotrail_runtime import wheel as runtime_wheel
from hypotrail_runtime.errors import ContractError

import test_review_round2_a as r2
import test_review_round3_a as r3
import test_review_round4_a as r4

PKG = r2.PKG
needs_mlflow = r2.needs_mlflow
RUNTIME_SOURCE = Path(hypotrail_runtime.__file__).resolve().parent
UV = shutil.which('uv')
WHEEL = f'runtime/hypotrail_runtime-{hypotrail_runtime.__version__}-py3-none-any.whl'
WHEEL_LINE = f'./artifacts/native_bundle/{WHEEL}'
# The reviewer's altered runtime: same version, the positive-class score inverted.
SCORE_LINE = 'values = np.asarray(self.pipeline.predict_proba(view)[:, classes.index(1)],'
INVERTED = 'values = 1.0 - np.asarray(self.pipeline.predict_proba(view)[:, classes.index(1)],'


def _manifest(dest: Path) -> dict:
    return json.loads((dest / 'predictor.json').read_bytes())


def _altered_runtime(tmp_path: Path, *, invert=True, without_checks=False, extra=None,
                     marker=False) -> Path:
    """A copy of the installed runtime of the same version, changed as the reviewer did (the
    score inverted), optionally without the round-5 load check (an older 1.0.0), with an
    extra module, or writing a marker file when it is imported. Returns the folder to put on
    ``sys.path``."""
    root = tmp_path / 'altered-runtime'
    alt = root / 'hypotrail_runtime'
    shutil.copytree(RUNTIME_SOURCE, alt, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    predictor = alt / 'predictor.py'
    text = predictor.read_text()
    if invert:
        assert text.count(SCORE_LINE) == 1
        text = text.replace(SCORE_LINE, INVERTED)
    if without_checks:
        old = 'def runtime_issues(desc: BundleDescriptor) -> dict | None:\n'
        assert text.count(old) == 1
        text = text.replace(old, old + '    return None\n')
    predictor.write_text(text)
    if extra:
        (alt / extra).write_text('VALUE = 1\n')
    if marker:
        with open(alt / '__init__.py', 'a') as handle:
            handle.write('\nimport os as _os\nif _os.environ.get("R5_MARKER"):\n'
                         '    open(_os.environ["R5_MARKER"], "w").write("runtime imported")\n')
    return root


SERVE = textwrap.dedent('''
    import json, sys
    from pathlib import Path
    import mlflow.pyfunc
    package = Path(sys.argv[1])
    try:
        model = mlflow.pyfunc.load_model(str(package))
    except Exception as error:
        print(json.dumps({"refused": type(error).__name__, "message": str(error)}))
        sys.exit(0)
    import hypotrail_runtime as rt
    from hypotrail_runtime.predictor import frame_from_document
    bundle = package / "artifacts" / "native_bundle"
    features = frame_from_document(json.loads((bundle / "parity/features.json").read_bytes()))
    expected = json.loads((bundle / "parity/expected_outputs.json").read_bytes())
    served = model.predict(features.copy())
    print(json.dumps({"served": [float(v) for v in served[served.columns[0]]],
                      "expected": expected["values"], "runtime_file": rt.__file__}))
''')


def _serve(tmp_path: Path, dest: Path, runtime_path: Path | None = None, **env) -> dict:
    """``mlflow.pyfunc.load_model`` on a copy of the package (never in place) in a fresh
    process, with ``runtime_path`` first on ``sys.path`` when given; bytecode disabled."""
    copy = tmp_path / 'serve' / 'package'
    if copy.exists():
        shutil.rmtree(copy)
    shutil.copytree(dest / PKG, copy)
    script = tmp_path / 'serve.py'
    script.write_text(SERVE)
    environment = {k: v for k, v in os.environ.items() if k != 'PYTHONPATH'}
    environment.update(PYTHONDONTWRITEBYTECODE='1', MLFLOW_DISABLE_AGENT_HINT='1',
                       PYTHONWARNINGS='ignore', **env)
    if runtime_path is not None:
        environment['PYTHONPATH'] = str(runtime_path)
    out = subprocess.run([sys.executable, str(script), str(copy)], capture_output=True,
                         text=True, cwd=tmp_path, env=environment, timeout=600)
    assert out.returncode == 0, out.stderr[-3000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def _tolerance(dest: Path) -> dict:
    return json.loads((dest / 'predictor_bundle.json').read_bytes())['parity']['tolerance']


# --- R5-A1: the package installs, and serves only with, the bundle's own runtime ------------------

@needs_mlflow
def test_the_package_environment_installs_the_embedded_runtime_wheel(tmp_path):
    """Reviewer probe: requirements.txt and conda.yaml pinned hypotrail-runtime==1.0.0 from an
    index. Now they name the bundle's own wheel by its path inside the package, which resolves
    from the package folder to the wheel the predictor id binds; MLflow's own parsing reads
    it from python_env.yaml and does not report it as a mismatch."""
    from mlflow.utils.requirements_utils import (_check_requirement_satisfied,
                                                 _parse_requirements)
    mp, dest, d = r3._workshop(tmp_path)
    pkg = dest / PKG
    manifest = _manifest(dest)
    assert manifest['runtime']['wheel_relative_path'] == WHEEL
    requirements = (pkg / 'requirements.txt').read_text().splitlines()
    assert WHEEL_LINE in requirements
    assert not [line for line in requirements if 'hypotrail' in line and line != WHEEL_LINE]
    assert canonical.file_sha256(pkg / WHEEL_LINE) == manifest['runtime']['wheel_sha256']
    conda = yaml.safe_load((pkg / 'conda.yaml').read_text())
    pip = next(item['pip'] for item in conda['dependencies'] if isinstance(item, dict))
    assert pip == requirements
    assert yaml.safe_load((pkg / 'python_env.yaml').read_text())['dependencies'] == \
        ['-r requirements.txt']
    descriptor = json.loads((pkg / mp.DESCRIPTOR_FILE).read_bytes())
    assert descriptor['environment']['pip_requirements'] == requirements
    assert descriptor['extensions']['hypotrail.packager_version'] == mp.PACKAGER_VERSION == '4'
    parsed = [r.req_str for r in _parse_requirements(['-r requirements.txt'],
                                                     is_constraint=False, base_dir=str(pkg))]
    assert parsed == requirements
    assert _check_requirement_satisfied(WHEEL_LINE) is None
    # verify regenerates the environment files and compares the bytes.
    assert mp.ArtifactPackager().verify(dest, pkg).status == 'passed'
    assert d.packages[0].parity_result.status == 'ok'


@needs_mlflow
def test_a_package_naming_the_runtime_from_an_index_is_refused(tmp_path):
    """The round-4 environment (the runtime pinned by name and version), re-made consistently
    everywhere an attacker can write: the runtime cannot read the environment and accepts the
    bundle; the packager regenerates the environment from the bundle and refuses."""
    mp, dest, _ = r3._workshop(tmp_path)
    pkg = dest / PKG
    doc = json.loads((pkg / mp.DESCRIPTOR_FILE).read_bytes())
    pins = [p for p in doc['environment']['pip_requirements'] if p != WHEEL_LINE]
    doc['environment']['pip_requirements'] = sorted(
        pins + [f'hypotrail-runtime=={hypotrail_runtime.__version__}'])
    (pkg / mp.DESCRIPTOR_FILE).write_bytes(canonical.dumps(doc) + b'\n')
    mp.write_environment_files(pkg, doc['environment'])
    r2._redescribe_mlflow_package(dest)
    verify_bundle(dest)
    err = r3._packaging_refused(mp.ArtifactPackager().verify, dest, pkg)
    assert 'not the pinned environment of the native bundle' in err.message
    r3._export_refused(dest)


@pytest.mark.parametrize('runtime,path', [
    ({'distribution': 'hypotrail-runtime', 'version': '1.0.0', 'wheel_relative_path': None,
      'wheel_sha256': None}, 'no wheel'),
    ({'distribution': 'hypotrail-runtime', 'version': '1.0.0',
      'wheel_relative_path': 'runtime/hypotrail_runtime-1.0.1-py3-none-any.whl',
      'wheel_sha256': 'a' * 64}, 'another version'),
    ({'distribution': 'hypotrail-runtime', 'version': '1.0.0',
      'wheel_relative_path': 'runtime/../../evil-1.0.0-py3-none-any.whl',
      'wheel_sha256': 'a' * 64}, 'outside runtime/'),
    ({'distribution': 'other', 'version': '1.0.0', 'wheel_relative_path': WHEEL,
      'wheel_sha256': 'a' * 64}, 'another distribution'),
    ({'distribution': 'hypotrail-runtime', 'version': '1.0.0',
      'wheel_relative_path': 'runtime/hypotrail_runtime-1.0.0-py3-none-any.whl --index-url x',
      'wheel_sha256': 'a' * 64}, 'an option'),
])
def test_the_runtime_requirement_is_the_bundle_s_own_wheel_or_a_refusal(runtime, path):
    pytest.importorskip('mlflow')
    from mlkit.integrations import mlflow_packaging as mp
    assert mp.runtime_requirement({'runtime': {
        'distribution': 'hypotrail-runtime', 'version': hypotrail_runtime.__version__,
        'wheel_relative_path': WHEEL, 'wheel_sha256': 'a' * 64}}) == WHEEL_LINE
    with pytest.raises(mp.PackagingError) as err:
        mp.runtime_requirement({'runtime': runtime})
    assert err.value.code == 'contract_invalid', path
    assert err.value.path == 'runtime.wheel_relative_path'


@needs_mlflow
@pytest.mark.parametrize('variant', ['inverted_score', 'inverted_without_load_check',
                                     'extra_module'])
def test_serving_under_another_runtime_of_the_same_version_is_refused(tmp_path, variant):
    """Reviewer probe (scripts/serve_probe.py): with an altered hypotrail_runtime 1.0.0 first
    on sys.path, mlflow.pyfunc.load_model served inverted scores under the evaluated predictor
    id. Now the wrapper refuses before importing anything of that runtime, whether or not the
    altered runtime still holds the round-5 load check, and names the differing file."""
    _, dest, _ = r3._workshop(tmp_path)
    altered = _altered_runtime(tmp_path, invert=variant != 'extra_module',
                               without_checks=variant == 'inverted_without_load_check',
                               extra='extra.py' if variant == 'extra_module' else None,
                               marker=True)
    marker = tmp_path / 'imported'
    out = _serve(tmp_path, dest, altered, R5_MARKER=str(marker))
    assert out.get('refused') == 'RuntimeNotBound', out
    assert 'is not the runtime this package binds' in out['message']
    assert str(altered / 'hypotrail_runtime') in out['message']
    assert ('extra.py' if variant == 'extra_module' else 'predictor.py') in out['message']
    assert f'artifacts/native_bundle/{WHEEL}' in out['message']
    assert not marker.exists(), 'the unbound runtime was imported before the check'


@needs_mlflow
def test_serving_with_the_bound_runtime_reproduces_the_parity_outputs(tmp_path):
    _, dest, _ = r3._workshop(tmp_path)
    out = _serve(tmp_path, dest)
    assert 'refused' not in out, out
    assert Path(out['runtime_file']).resolve().parent == RUNTIME_SOURCE
    tol = _tolerance(dest)
    np.testing.assert_allclose(out['served'], out['expected'], rtol=tol['rtol'],
                               atol=tol['atol'])


@needs_mlflow
@pytest.mark.skipif(UV is None, reason='uv is needed for MLflow to restore the environment')
def test_mlflow_restores_the_package_environment_from_the_embedded_wheel(tmp_path):
    """MLflow's own environment restoration (``mlflow models predict --env-manager uv``)
    builds a fresh environment from the package's python_env.yaml and requirements.txt: the
    runtime it installs is the embedded wheel (the wrapper would refuse any other), and the
    package serves the bundle's parity outputs there."""
    from hypotrail_runtime.predictor import frame_from_document
    mlflow_cli = Path(sys.executable).parent / 'mlflow'
    if not mlflow_cli.is_file():
        pytest.skip('the mlflow command is not installed beside this interpreter')
    _, dest, _ = r3._workshop(tmp_path)
    copy = tmp_path / 'served' / 'package'
    shutil.copytree(dest / PKG, copy)
    bundle = copy / 'artifacts' / 'native_bundle'
    features = frame_from_document(json.loads((bundle / 'parity/features.json').read_bytes()))
    expected = json.loads((bundle / 'parity/expected_outputs.json').read_bytes())['values']
    rows = tmp_path / 'input.json'
    rows.write_text(json.dumps({'dataframe_split': json.loads(
        features.to_json(orient='split', index=False))}))
    out = tmp_path / 'out.json'
    scratch = tmp_path / 'scratch'
    scratch.mkdir()
    environment = {k: v for k, v in os.environ.items() if k != 'PYTHONPATH'}
    environment.update(PYTHONDONTWRITEBYTECODE='1', MLFLOW_DISABLE_AGENT_HINT='1',
                       TMPDIR=str(scratch), MLFLOW_ENV_ROOT=str(tmp_path / 'envs'))
    result = subprocess.run([str(mlflow_cli), 'models', 'predict', '-m', str(copy), '-i',
                             str(rows), '-t', 'json', '-o', str(out), '--env-manager', 'uv'],
                            capture_output=True, text=True, cwd=tmp_path, env=environment,
                            timeout=900)
    assert result.returncode == 0, (result.stdout[-3000:], result.stderr[-3000:])
    served = [row['score'] for row in json.loads(out.read_text())['predictions']]
    tol = _tolerance(dest)
    np.testing.assert_allclose(served, expected, rtol=tol['rtol'], atol=tol['atol'])


@needs_mlflow
def test_the_wrapper_refuses_to_serve_when_the_parity_rows_are_not_reproduced(tmp_path,
                                                                             monkeypatch):
    import mlflow.pyfunc
    _, dest, _ = r3._workshop(tmp_path)
    copy = tmp_path / 'copy' / 'package'
    shutil.copytree(dest / PKG, copy)
    calls = []

    def failed(predictor):
        calls.append(predictor.predictor_id)
        result = check_parity(predictor)
        return result.model_copy(update={'status': 'failed', 'reason': 'probe'})
    monkeypatch.setattr(hypotrail_runtime, 'check_parity', failed)
    monkeypatch.setattr(sys, 'dont_write_bytecode', True)
    with pytest.raises(Exception) as err:
        mlflow.pyfunc.load_model(str(copy))
    assert type(err.value).__name__ == 'ParityNotReproduced'
    assert 'does not reproduce the parity rows' in str(err.value) and '(probe)' in str(err.value)
    assert calls == [_manifest(dest)['predictor_id']]


@needs_mlflow
def test_a_package_of_the_round_4_packager_is_refused(tmp_path):
    mp, dest, _ = r3._workshop(tmp_path)
    pkg = dest / PKG
    doc = json.loads((pkg / mp.DESCRIPTOR_FILE).read_bytes())
    doc['extensions']['hypotrail.packager_version'] = '3'
    (pkg / mp.DESCRIPTOR_FILE).write_bytes(canonical.dumps(doc) + b'\n')
    r2._redescribe_mlflow_package(dest)
    r3._packaging_refused(mp.ArtifactPackager().verify, dest, pkg,
                          code='schema_version_unsupported')


def _point_at(monkeypatch, folder: Path) -> None:
    monkeypatch.setattr(runtime_wheel, 'installed_location', lambda: Path(folder).resolve())


def test_load_predictor_refuses_a_runtime_other_than_the_bundle_s(tmp_path, monkeypatch):
    """The runtime itself compares its installed files with the bundle's wheel before it
    unpickles anything: another 1.0.0 is environment_unqualified (runtime_not_bound) with the
    differing files and a remediation naming the wheel."""
    import pickle
    dest = tmp_path / 'b'
    capture_predictor(r2._fitted(), None, r2._parity(), dest, None, code_fingerprint=r2.FP)
    altered = _altered_runtime(tmp_path) / 'hypotrail_runtime'
    _point_at(monkeypatch, altered)
    loads = []
    monkeypatch.setattr(pickle, 'load', lambda *a, **k: loads.append(a))
    e = r2._refused(load_predictor, dest, trusted_roots=[dest], code='environment_unqualified')
    assert e.details['reason'] == runtime_predictor.RUNTIME_NOT_BOUND == 'runtime_not_bound'
    assert e.details['changed'] == ['predictor.py']
    assert e.details['missing'] == e.details['unexpected'] == []
    assert e.details['wheel_relative_path'] == WHEEL == e.path
    assert e.details['installed_digest'] != e.details['bound_digest']
    assert e.details['location'] == str(altered.resolve())
    assert f'pip install <bundle>/{WHEEL}' in e.remediation
    assert 'is not the runtime this bundle binds' in e.message and 'predictor.py' in e.message
    assert loads == []
    # A missing module and an added one are reported too.
    (altered / 'families.py').unlink()
    (altered / 'native.so').write_bytes(b'\x7fELF')
    e = r2._refused(load_predictor, dest, trusted_roots=[dest], code='environment_unqualified')
    assert (e.details['missing'], e.details['unexpected']) == (['families.py'], ['native.so'])
    # An identical copy of the bound runtime loads (its bytecode is not compared).
    identical = tmp_path / 'identical' / 'hypotrail_runtime'
    shutil.copytree(RUNTIME_SOURCE, identical,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    (identical / '__pycache__').mkdir()
    (identical / '__pycache__' / 'predictor.cpython-313.pyc').write_bytes(b'cache')
    _point_at(monkeypatch, identical)
    monkeypatch.undo()                      # pickle.load restored
    _point_at(monkeypatch, identical)
    assert check_parity(load_predictor(dest, trusted_roots=[dest])).status == 'ok'


def test_the_installed_runtime_is_the_wheel_it_builds(tmp_path):
    """The comparison is reproducible: the wheel built from the installed runtime holds
    exactly its files, so every capture binds the runtime that made it, and the code digest
    of both sides is the same."""
    assert runtime_wheel.installed_location() == RUNTIME_SOURCE
    files = runtime_wheel.installed_files()
    assert 'hypotrail_runtime/predictor.py' in files
    assert all(name.startswith('hypotrail_runtime/') for name in files)
    data = runtime_wheel.build(tmp_path / 'wheel').read_bytes()
    assert runtime_wheel.wheel_files(data) == files
    assert runtime_wheel.code_digest(runtime_wheel.wheel_files(data)) == \
        runtime_wheel.code_digest(files)
    assert runtime_wheel.installed_runtime_issues(data) is None


def test_a_capture_binds_the_installed_runtime_byte_for_byte(tmp_path):
    dest = tmp_path / 'b'
    capture_predictor(r2._fitted(), None, r2._parity(), dest, None, code_fingerprint=r2.FP)
    data = (dest / WHEEL).read_bytes()
    assert runtime_wheel.wheel_files(data) == runtime_wheel.installed_files()
    assert runtime_wheel.installed_runtime_issues(data) is None
    assert runtime_predictor.runtime_issues(verify_bundle(dest)) is None


def test_the_final_test_refuses_a_runtime_other_than_the_capture_s(tmp_path, monkeypatch):
    """Engine path: the study captured its predictor with one runtime; another runtime of the
    same version is installed before the final test. The opening refuses (capture_loadable,
    environment_unqualified, a junior message naming the runtime), nothing is opened and no
    final-test row is read."""
    import test_capture_final as tcf
    from mlkit.contracts import capture as cap
    from mlkit.study import read, state as st
    flow = tcf._chosen(tmp_path)
    flow.run('predictor.capture')
    _point_at(monkeypatch, _altered_runtime(tmp_path) / 'hypotrail_runtime')
    out = tcf._open(flow, expect=2)
    assert 'result' not in out
    item = next(x for x in out['error']['details']['missing']
                if x['requirement'] == 'capture_loadable')
    assert item['slot'] == cap.CAPTURE
    assert item['contract_code'] == 'environment_unqualified'
    assert 'hypotrail_runtime' in item['junior_message']
    assert 'even if its version did not' in item['junior_message']
    assert 'No final-test row was read' in item['junior_message']
    assert not st.final_test_opened(read.open(flow.study).state)
    monkeypatch.undo()
    assert tcf._open(flow)['result']['opening']['status'] == 'promoted'


# --- R5-A2: evidence never travels in a package; the evidence folder holds bindings only --------

@needs_mlflow
def test_evidence_files_inside_the_embedded_bundle_are_refused(tmp_path):
    """Reviewer probe (probes/test_probe_a.py): a module and a library planted under
    artifacts/native_bundle/evidence/ of the package, re-described consistently, were accepted
    by verify_bundle and by the packager. Now the runtime, the packager (in place and alone,
    beside an honest bundle) and the export refuse them."""
    mp, dest, _ = r3._workshop(tmp_path)
    clean = r4._clean_copy(dest, tmp_path)
    evidence = dest / PKG / 'artifacts/native_bundle/evidence'
    evidence.mkdir()
    (evidence / 'hypotrail_runtime.py').write_text('raise SystemExit("planted")\n')
    (evidence / 'notes.so').write_bytes(b'\x7fELF')
    r2._redescribe_mlflow_package(dest)
    planted = [f'{PKG}/artifacts/native_bundle/evidence/hypotrail_runtime.py',
               f'{PKG}/artifacts/native_bundle/evidence/notes.so']
    e = r2._refused(verify_bundle, dest)
    assert e.details['unexpected'] == planted
    r2._refused(load_predictor, dest, trusted_roots=[dest.parent])
    err = r3._packaging_refused(mp.ArtifactPackager().verify, dest, dest / PKG)
    assert err.details['contract_code'] == 'artifact_integrity_failed'
    r3._export_refused(dest)
    alone = r4._package_alone(dest, tmp_path)
    err = r3._packaging_refused(mp.ArtifactPackager().verify, clean, alone)
    assert err.details['unexpected'] == ['artifacts/native_bundle/evidence/',
                                         'artifacts/native_bundle/evidence/hypotrail_runtime.py',
                                         'artifacts/native_bundle/evidence/notes.so']
    assert mp.ArtifactPackager().verify(clean, clean / PKG).status == 'passed'


@needs_mlflow
@pytest.mark.parametrize('rel', ['evidence/binding-1.json', 'packages/notes.txt'])
def test_an_embedded_bundle_carries_no_evidence_or_package_folder(tmp_path, rel):
    """Even a well-formed binding, or an empty folder, is refused in the embedded bundle: the
    package carries the predictor, never its evidence."""
    mp, dest, _ = r3._workshop(tmp_path)
    clean = r4._clean_copy(dest, tmp_path)
    path = dest / PKG / 'artifacts/native_bundle' / rel
    path.parent.mkdir(parents=True)
    alone = r4._package_alone(dest, tmp_path)
    err = r3._packaging_refused(mp.ArtifactPackager().verify, clean, alone)
    assert err.details['unexpected'] == [f'artifacts/native_bundle/{rel.split("/")[0]}/']
    if rel.startswith('evidence/'):
        # The runtime refuses even an empty evidence folder in the embedded bundle.
        e = r2._refused(verify_bundle, dest)
        assert 'carries an evidence folder' in e.message
    path.write_bytes(canonical.dumps({'schema_version': 'hypotrail.evidence_binding/1'}))
    r2._redescribe_mlflow_package(dest)
    e = r2._refused(verify_bundle, dest)
    assert e.details['unexpected'] == [f'{PKG}/artifacts/native_bundle/{rel}']


def test_the_runtime_refuses_an_embedded_bundle_with_evidence(tmp_path):
    """Through the synthetic layout of a package the runtime does not know (no allowlist):
    an embedded bundle holding an evidence binding, a binding path or an unlisted file is
    refused by the embedded-bundle check itself."""
    from mlkit.contracts.testing_packager import SyntheticPackager

    class Embedding(SyntheticPackager):
        def package(self, native_bundle_dir, output_dir, parity_spec):
            doc = super().package(native_bundle_dir, output_dir, parity_spec)
            inner = Path(output_dir) / 'native'
            shutil.copytree(native_bundle_dir, inner,
                            ignore=shutil.ignore_patterns('packages'))
            doc['files'] = r2._inventory(Path(output_dir))
            doc['artifact_id'] = canonical.artifact_id(doc, exclude=('artifact_id',))
            return doc
    dest = tmp_path / 'b'
    d = capture_predictor(r2._fitted(), None, r2._parity(), dest, Embedding(),
                          code_fingerprint=r2.FP)
    inner = dest / 'packages' / 'synthetic_test' / 'native'
    verify_bundle(dest)
    write_evidence_binding(inner, {
        'schema_version': 'hypotrail.evidence_binding/1', 'predictor_id': d.predictor_id,
        'final_result_id': 'r1', 'study_revision': 1, 'decision_refs': ['final_test'],
        'protocol_id': None, 'evaluation_context_id': 'x', 'status': 'evaluated'})
    _relist_synthetic(dest)
    e = r2._refused(verify_bundle, dest)
    assert 'carries an evidence folder' in e.message


def _relist_synthetic(dest: Path) -> None:
    """Re-describe the synthetic package after an edit, as an attacker who knows every rule."""
    package = dest / 'packages' / 'synthetic_test'
    desc_path = dest / 'packages' / 'synthetic_test.descriptor.json'
    doc = json.loads(desc_path.read_bytes())
    doc['files'] = r2._inventory(package)
    doc['artifact_id'] = canonical.artifact_id(doc, exclude=('artifact_id',))
    desc_path.write_bytes(canonical.dumps(doc) + b'\n')
    bundle = json.loads((dest / 'predictor_bundle.json').read_bytes())
    kept = [e for e in bundle['files'] if not e['relative_path'].startswith('packages/')]
    new = r2._inventory(package, 'packages/synthetic_test/')
    new.append({'relative_path': 'packages/synthetic_test.descriptor.json',
                'size_bytes': desc_path.stat().st_size,
                'sha256': canonical.file_sha256(desc_path)})
    bundle['files'] = sorted(kept + new, key=lambda e: e['relative_path'])
    bundle['optional_packages'][0]['manifest_sha256'] = canonical.file_sha256(desc_path)
    bundle['optional_packages'][0]['artifact_id'] = doc['artifact_id']
    (dest / 'predictor_bundle.json').write_bytes(canonical.dumps(bundle) + b'\n')


def _binding(predictor_id: str, result: str = 'r1') -> dict:
    return {'schema_version': 'hypotrail.evidence_binding/1', 'predictor_id': predictor_id,
            'final_result_id': result, 'study_revision': 3, 'decision_refs': ['final_test'],
            'protocol_id': None, 'evaluation_context_id': 'ctx', 'status': 'evaluated'}


@pytest.fixture
def base_bundle(tmp_path):
    dest = tmp_path / 'predictors' / 'b'
    d = capture_predictor(r2._fitted(), None, r2._parity(), dest, None, code_fingerprint=r2.FP)
    return dest, d.predictor_id


STRAY_EVIDENCE = {
    'module': ('evidence/hypotrail_runtime.py', b'raise SystemExit("planted")\n'),
    'library': ('evidence/notes.so', b'\x7fELF'),
    'hidden_file': ('evidence/.DS_Store', b'\x00'),
    'leading_zero': ('evidence/binding-01.json', None),
    'sub_folder': ('evidence/old/binding-1.json', None),
    'another_name': ('evidence/binding-1.json.bak', None),
}


@pytest.mark.parametrize('name', sorted(STRAY_EVIDENCE))
def test_the_evidence_folder_holds_evidence_bindings_only(base_bundle, name):
    dest, pid = base_bundle
    write_evidence_binding(dest, _binding(pid))
    rel, data = STRAY_EVIDENCE[name]
    path = dest / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical.dumps(_binding(pid)) + b'\n' if data is None else data)
    e = r2._refused(verify_bundle, dest)
    assert 'only evidence/binding-<n>.json files are allowed there' in e.message
    assert rel in e.details['files'] or f'{Path(rel).parent.as_posix()}/' in e.details['folders']


def test_a_binding_file_must_be_a_binding_of_this_predictor(base_bundle):
    dest, pid = base_bundle
    write_evidence_binding(dest, _binding(pid))
    verify_bundle(dest)
    (dest / 'evidence/binding-2.json').write_bytes(canonical.dumps(_binding('e' * 64)) + b'\n')
    e = r2._refused(verify_bundle, dest)
    assert 'binds another predictor' in e.message
    (dest / 'evidence/binding-2.json').write_bytes(b'import os\n')
    e = r2._refused(verify_bundle, dest)
    assert 'is not an evidence binding' in e.message
    (dest / 'evidence/binding-2.json').unlink()
    verify_bundle(dest)


def test_evidence_bindings_are_written_atomically_from_beside_the_bundle(base_bundle):
    """Successive bindings stay, the bundle verifies after each, and no temporary file is left
    inside the bundle or beside it."""
    dest, pid = base_bundle
    first = write_evidence_binding(dest, _binding(pid, 'r1'))
    second = write_evidence_binding(dest, _binding(pid, 'r2'))
    assert (first.name, second.name) == ('binding-1.json', 'binding-2.json')
    assert sorted(p.name for p in (dest / 'evidence').iterdir()) == ['binding-1.json',
                                                                     'binding-2.json']
    assert sorted(p.name for p in dest.parent.iterdir()) == [dest.name]
    doc = verify_bundle(dest).bundle
    assert doc.evidence_binding_path == 'evidence/binding-2.json'


@needs_mlflow
def test_packaging_a_bundle_with_evidence_copies_no_evidence(base_bundle, tmp_path):
    """The packager leaves the bundle's evidence and packages folders out of the copy it
    embeds, so a package made after an evaluation holds the predictor only."""
    from mlkit.integrations import mlflow_packaging as mp
    dest, pid = base_bundle
    write_evidence_binding(dest, _binding(pid))
    (dest / 'packages').mkdir()
    out = tmp_path / 'elsewhere' / 'package'
    descriptor = mp.ArtifactPackager().package(dest, out)
    inner = out / 'artifacts' / 'native_bundle'
    assert not (inner / 'evidence').exists() and not (inner / 'packages').exists()
    assert mp.layout_issues(out) == {'unexpected': [], 'missing': []}
    assert descriptor.parity_result['status'] == 'passed'
    assert mp.ArtifactPackager().verify(dest, out).status == 'passed'


# --- R5-A3: a reused bundle holds the packages the capture has just built -------------------------

def _staged(root: Path, name: str, packager):
    return capture_predictor(r2._fitted(), None, r2._parity(), root / name, packager,
                             code_fingerprint=r2.FP)


@needs_mlflow
def test_a_reused_bundle_with_a_re_made_package_is_refused(tmp_path):
    """Reviewer finding: _place reused predictors/<pid>+mlflow_pyfunc after verify_bundle
    only, and the capture recorded the artifact id of the held package. A package re-made
    consistently there verifies; the reuse now compares it with the package just built in
    staging and refuses (artifact_integrity_failed, packages_differ)."""
    from mlkit.contracts import capture as cap
    from mlkit.integrations import mlflow_packaging as mp
    root = tmp_path / 'predictors'
    root.mkdir()
    first = _staged(root, '.staging-1', mp.packager_for('atelier'))
    folder, reused, held = cap._place(root, root / '.staging-1', first)
    assert folder.name == f'{first.predictor_id}+mlflow_pyfunc' and not reused
    # The honest retry reuses the bundle: its package is the one just built.
    again = _staged(root, '.staging-2', mp.packager_for('atelier'))
    folder, reused, held = cap._place(root, root / '.staging-2', again)
    assert reused and [p.artifact_id for p in held] == [p.artifact_id for p in again.packages]
    shutil.rmtree(root / '.staging-2')
    r4._remake_package(folder)
    verify_bundle(folder)
    third = _staged(root, '.staging-3', mp.packager_for('atelier'))
    with pytest.raises(ContractError) as err:
        cap._place(root, root / '.staging-3', third)
    e = err.value
    assert e.code == 'artifact_integrity_failed' and e.path == folder.name
    assert e.details == {'reason': cap.PACKAGES_DIFFER, 'changed': ['mlflow_pyfunc']}
    assert 'predictor.capture again' in e.remediation
    assert (root / '.staging-3').exists()           # nothing moved; the caller removes it


def test_packages_differ_compares_ids_and_bytes(tmp_path):
    from mlkit.contracts import capture as cap
    from mlkit.contracts.testing_packager import SyntheticPackager
    a = _staged(tmp_path, 'a', SyntheticPackager())
    b = _staged(tmp_path, 'b', SyntheticPackager())
    held, built = list(a.bundle.optional_packages), list(b.bundle.optional_packages)
    assert cap.packages_differ(tmp_path / 'a', tmp_path / 'b', held, built) == []
    assert cap.packages_differ(tmp_path / 'a', tmp_path / 'b', held, []) == ['synthetic_test']
    (tmp_path / 'b' / 'packages' / 'synthetic_test' / 'model.pkl').write_bytes(b'other')
    assert cap.packages_differ(tmp_path / 'a', tmp_path / 'b', held, built) == \
        ['synthetic_test']
    relabelled = [p.model_copy(update={'artifact_id': 'f' * 64}) for p in built]
    assert cap.packages_differ(tmp_path / 'a', tmp_path / 'a', held, relabelled) == \
        ['synthetic_test']
