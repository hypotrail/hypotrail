"""AC25: the base works without the extras; optional imports are lazy; the extras install
alone and together.

The installation matrix builds four fresh environments from the lock (base, diagnostics,
uncertainty, both) and is opt-in (``HYPOTRAIL_EXTRAS_MATRIX=1``, a few minutes and the uv
cache); the import and absence checks run in the gate.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from hypotrail_runtime.errors import ContractError

FRAMEWORK = Path(__file__).resolve().parents[3]
UV = shutil.which('uv')

PROBE = textwrap.dedent('''
    import json, sys
    import mlkit.study.cli, mlkit.contracts.capture, mlkit.contracts.export_source
    import mlkit.contracts.population
    import mlkit.integrations.pandera_validation, mlkit.integrations.scipy_bootstrap
    import mlkit.integrations.evidently_diagnostics, mlkit.integrations.mapie_uncertainty
    print(json.dumps(sorted(m for m in ('evidently', 'mapie', 'mlflow', 'hydra', 'azure')
                            if m in sys.modules)))
''')


def test_importing_the_engine_and_adapters_loads_no_optional_backend():
    out = subprocess.run([sys.executable, '-c', PROBE], capture_output=True, text=True,
                         cwd=FRAMEWORK)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == []


def test_the_runtime_imports_no_engine_and_no_validation_backend():
    code = ('import json, sys, hypotrail_runtime; print(json.dumps(sorted(m for m in '
            '("mlkit", "pandera", "marimo", "evidently", "mapie", "mlflow") if m in sys.modules)))')
    out = subprocess.run([sys.executable, '-I', '-c', code], capture_output=True, text=True,
                         cwd='/')
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == []


@pytest.mark.parametrize('module, call', [
    ('evidently', lambda: __import__('mlkit.integrations.evidently_diagnostics',
                                     fromlist=['run']).run(
        {'schema_version': 'hypotrail.diagnostic_profile/1', 'name': 'x', 'version': 1,
         'columns': {}, 'missing_share_threshold': 0.05,
         'unknown_category_share_threshold': 0.05, 'multiple_testing': 'holm',
         'demonstration_thresholds': True},
        None, None, reference_partition='development', current_partition='development',
        authorized=('development',))),
    ('mapie', lambda: __import__('mlkit.integrations.mapie_uncertainty',
                                 fromlist=['split_conformal']).split_conformal(
        lambda X: X, [[0.0]], [0.0], [[0.0]], confidence_level=.9, predictor_id=None,
        calibration={'eligible': True, 'reasons': [], 'calibration_ref': 'c@x'})),
])
def test_a_missing_extra_is_a_named_refusal(monkeypatch, module, call):
    monkeypatch.setitem(sys.modules, module, None)          # import fails as if absent
    with pytest.raises(ContractError) as e:
        call()
    assert e.value.code == 'optional_dependency_missing'


SMOKE = textwrap.dedent('''
    import json, sys
    extras = set(sys.argv[1].split(',')) - {''}
    from hypotrail_runtime.errors import ContractError
    out = {}
    import numpy as np, pandas as pd
    from mlkit.integrations import evidently_diagnostics as ed, mapie_uncertainty as mu
    try:
        profile = ed.demonstration_profile({'x': 'numerical'})
        r = ed.run(profile, pd.DataFrame({'x': np.arange(100.0)}),
                   pd.DataFrame({'x': np.arange(100.0) + 50}), reference_partition='d',
                   current_partition='d', authorized=('d',))['result']
        out['diagnostics'] = r.status
    except ContractError as exc:
        out['diagnostics'] = exc.code
    try:
        r = mu.split_conformal(lambda X: np.asarray(X)[:, 0], np.arange(40.0)[:, None],
                               np.arange(40.0), np.zeros((2, 1)), confidence_level=.8,
                               predictor_id=None,
                               calibration={'eligible': True, 'reasons': [],
                                            'calibration_ref': 'c@x'})
        out['uncertainty'] = r.status
    except ContractError as exc:
        out['uncertainty'] = exc.code
    print(json.dumps(out))
''')


@pytest.mark.skipif(os.environ.get('HYPOTRAIL_EXTRAS_MATRIX') != '1' or UV is None,
                    reason='opt-in installation matrix (HYPOTRAIL_EXTRAS_MATRIX=1)')
@pytest.mark.parametrize('extras', [(), ('diagnostics',), ('uncertainty',),
                                    ('diagnostics', 'uncertainty')])
def test_extras_install_alone_and_together(tmp_path, extras):
    env = tmp_path / 'venv'
    flags = [arg for e in extras for arg in ('--extra', e)]
    environ = {**os.environ, 'UV_PROJECT_ENVIRONMENT': str(env)}
    subprocess.run([UV, 'sync', '-q', '--frozen', '--project', str(FRAMEWORK), *flags],
                   check=True, env=environ)
    script = tmp_path / 'smoke.py'
    script.write_text(SMOKE)
    out = subprocess.run([str(env / 'bin' / 'python'), str(script), ','.join(extras)],
                         capture_output=True, text=True, cwd=tmp_path)
    assert out.returncode == 0, out.stderr
    result = json.loads(out.stdout)
    assert result['diagnostics'] == ('ok' if 'diagnostics' in extras
                                     else 'optional_dependency_missing')
    assert result['uncertainty'] == ('ok' if 'uncertainty' in extras
                                     else 'optional_dependency_missing')
