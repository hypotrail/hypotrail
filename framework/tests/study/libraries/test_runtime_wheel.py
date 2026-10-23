"""AC08 / AC25: the runtime wheel installs and predicts alone.

A predictor is captured from a temporary synthetic study; the wheel shipped *inside its
bundle* is installed into a fresh virtual environment (uv, Python 3.13) with the captured
semantic dependency versions and nothing else. A script run in isolated mode (``-I``, from a
directory outside the repository) verifies and loads the bundle, reproduces its parity rows
and checks that no engine, Marimo, MLflow or Azure module is importable.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from test_capture_final import _chosen

UV = shutil.which('uv')
SCRIPT = textwrap.dedent('''
    import importlib.util, json, sys
    from pathlib import Path
    import hypotrail_runtime as rt
    bundle = Path(sys.argv[1])
    predictor = rt.load_predictor(bundle, trusted_roots=[bundle])
    parity = rt.check_parity(predictor)
    absent = [m for m in ('mlkit', 'marimo', 'mlflow', 'azure', 'hydra', 'evidently', 'mapie')
              if importlib.util.find_spec(m) is not None]
    print(json.dumps({'predictor_id': predictor.predictor_id, 'parity': parity.status,
                      'max_abs_diff': parity.max_abs_diff, 'importable': absent,
                      'runtime_file': rt.__file__}))
''')


@pytest.mark.skipif(UV is None, reason='uv is needed to build a fresh environment')
def test_bundle_wheel_installs_and_predicts_in_a_fresh_environment(tmp_path):
    flow = _chosen(tmp_path / 'study')
    v = flow.run('predictor.capture')['values']
    bundle = Path(flow.study) / '.hypotrail' / v['bundle']
    # The bundle moves away from the study: no path back to it is needed.
    moved = tmp_path / 'elsewhere' / 'bundle'
    shutil.copytree(bundle, moved)
    shutil.rmtree(Path(flow.study))
    manifest = json.loads((moved / 'predictor.json').read_bytes())
    wheel = moved / manifest['runtime']['wheel_relative_path']
    pins = [f"{d['distribution']}=={d['version']}"
            for d in manifest['environment']['semantic_dependencies']
            if d['distribution'] != 'hypotrail-runtime']
    env = tmp_path / 'venv'
    subprocess.run([UV, 'venv', '-q', '--python', '3.13', str(env)], check=True)
    python = env / 'bin' / 'python'
    subprocess.run([UV, 'pip', 'install', '-q', '--python', str(python), str(wheel), *pins],
                   check=True)
    script = tmp_path / 'check.py'
    script.write_text(SCRIPT)
    out = subprocess.run([str(python), '-I', str(script), str(moved)], capture_output=True,
                         text=True, cwd=tmp_path)
    assert out.returncode == 0, out.stderr
    result = json.loads(out.stdout)
    assert result['predictor_id'] == v['predictor_id']
    assert result['parity'] == 'ok' and result['importable'] == []
    assert str(env) in result['runtime_file']               # the installed wheel, not sources
