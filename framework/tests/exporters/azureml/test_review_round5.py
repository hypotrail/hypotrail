"""Regressions of the fifth review round (R5-A1) in the exported project.

The exported project scores with ``hypotrail_runtime.load_predictor``, which now compares the
installed runtime with the bundle's own wheel, file by file: another runtime of the same
version on the project's path is refused with ``environment_unqualified`` (reason
``runtime_not_bound``) and a remediation naming the wheel, and nothing is predicted. The
project runs in a subprocess from the moved folder; the data are the export fixtures'.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import hypotrail_runtime

from export_env import needs_hydra, needs_mlflow, project_env
from test_exported_project import _json, _run, project  # noqa: F401 - the module fixture

pytestmark = [needs_mlflow, needs_hydra]

SCORE = 'values = np.asarray(self.pipeline.predict(view), dtype=float)'


def _altered_runtime(tmp_path: Path) -> Path:
    """A copy of the installed runtime, same version, its regression output shifted."""
    root = tmp_path / 'altered-runtime'
    shutil.copytree(Path(hypotrail_runtime.__file__).resolve().parent,
                    root / 'hypotrail_runtime',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    predictor = root / 'hypotrail_runtime' / 'predictor.py'
    text = predictor.read_text()
    assert text.count(SCORE) == 1
    predictor.write_text(text.replace(SCORE, SCORE.replace('dtype=float)',
                                                           'dtype=float) + 1.0')))
    return root


def test_predict_refuses_another_runtime_of_the_same_version(project, tmp_path):  # noqa: F811
    out = tmp_path / 'predictions.json'
    env = project_env()
    env['PYTHONPATH'] = str(_altered_runtime(tmp_path))
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    result = subprocess.run([sys.executable, '-m', 'src.pipeline.utils.project', 'predict',
                             '--parity', '--output', str(out)], cwd=project['root'],
                            capture_output=True, text=True, env=env, timeout=600)
    assert result.returncode == 2, (result.stdout[-2000:], result.stderr[-2000:])
    document = _json(result)
    error = document.get('error') or document
    assert error['code'] == 'environment_unqualified', document
    assert 'is not the runtime this bundle binds' in error['message']
    assert 'predictor.py' in error['message']
    assert 'pip install <bundle>/runtime/hypotrail_runtime-' in error['remediation']
    assert not out.exists()
    # The installed (bound) runtime predicts the same parity rows.
    _run(project['root'], '-m', 'src.pipeline.utils.project', 'predict', '--parity',
         '--output', str(out))
    assert out.is_file()
