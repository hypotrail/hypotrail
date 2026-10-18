"""The junior study package stays isolated from the legacy pilot (plan WP0.3).

Two complementary checks cover every module under ``framework/mlkit/study``,
including modules added later, without listing them here:

* a fresh interpreter imports every study module and reports ``sys.modules``,
  which catches transitive imports;
* an AST scan of every ``*.py`` file rejects, even in code paths that do not run
  at import time, any import of a legacy module and any use of ``config.ROOT``,
  which is frozen when ``mlkit.config`` is imported.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

FRAMEWORK = Path(__file__).resolve().parents[2]
STUDY = FRAMEWORK / 'mlkit' / 'study'
LEGACY = ('pilot', 'drift', 'ensemble', 'automl', 'monitor', 'holdout', 'gate', 'run',
          'evaluate', 'baselines', 'quality', 'config')
FORBIDDEN = frozenset(f'mlkit.{name}' for name in LEGACY)


def study_files(root: Path = FRAMEWORK) -> list[Path]:
    return sorted((root / 'mlkit' / 'study').rglob('*.py'))


def module_name(path: Path, root: Path = FRAMEWORK) -> str:
    parts = list(path.relative_to(root).with_suffix('').parts)
    if parts[-1] == '__init__':
        parts.pop()
    return '.'.join(parts)


def _resolve(path: Path, root: Path, node: ast.ImportFrom) -> str:
    """Absolute module named by an ``ImportFrom`` node, relative imports included."""
    if not node.level:
        return node.module or ''
    name = module_name(path, root)
    package = name.split('.') if path.name == '__init__.py' else name.split('.')[:-1]
    base = package[:len(package) - (node.level - 1)]
    return '.'.join(base + ([node.module] if node.module else []))


def is_forbidden(module: str) -> bool:
    return any(module == f or module.startswith(f + '.') for f in FORBIDDEN)


def _constant_str(node: ast.Call) -> str | None:
    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
        return node.args[0].value
    return None


def violations(path: Path, root: Path = FRAMEWORK) -> list[str]:
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    rel = path.relative_to(root)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [f'{rel}:{node.lineno}: import {a.name}' for a in node.names
                      if is_forbidden(a.name)]
        elif isinstance(node, ast.ImportFrom):
            module = _resolve(path, root, node)
            if is_forbidden(module):
                found.append(f'{rel}:{node.lineno}: from {module} import ...')
            else:
                found += [f'{rel}:{node.lineno}: from {module} import {a.name}'
                          for a in node.names if is_forbidden(f'{module}.{a.name}')]
        elif isinstance(node, ast.Attribute) and node.attr == 'ROOT':
            owner = node.value
            if (isinstance(owner, ast.Name) and owner.id == 'config') or (
                    isinstance(owner, ast.Attribute) and owner.attr == 'config'):
                found.append(f'{rel}:{node.lineno}: config.ROOT')
        elif isinstance(node, ast.Call):
            func = node.func
            dynamic = (isinstance(func, ast.Name) and func.id in {'__import__', 'import_module'}) or (
                isinstance(func, ast.Attribute) and func.attr == 'import_module')
            target = _constant_str(node)
            if dynamic and target and is_forbidden(target):
                found.append(f'{rel}:{node.lineno}: dynamic import of {target}')
    return found


def _subprocess(code: str) -> subprocess.CompletedProcess:
    path = [str(FRAMEWORK)] + [p for p in os.environ.get('PYTHONPATH', '').split(os.pathsep) if p]
    env = {**os.environ, 'PYTHONPATH': os.pathsep.join(path)}
    return subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                          env=env, cwd=FRAMEWORK, timeout=120)


def test_study_package_exists_and_is_scanned():
    assert STUDY / '__init__.py' in study_files()


def test_plain_import_of_the_package_loads_no_legacy_module():
    proc = _subprocess('import mlkit.study, sys; print(sorted(sys.modules))')
    assert proc.returncode == 0, proc.stderr
    loaded = set(ast.literal_eval(proc.stdout.strip().splitlines()[-1]))
    assert 'mlkit.study' in loaded
    assert not sorted(m for m in loaded if is_forbidden(m))


def test_importing_every_study_module_loads_no_legacy_module():
    modules = [module_name(p) for p in study_files()]
    proc = _subprocess('import importlib, json, sys\n'
                       f'for name in {modules!r}:\n'
                       '    importlib.import_module(name)\n'
                       'print(json.dumps(sorted(sys.modules)))\n')
    assert proc.returncode == 0, proc.stderr
    loaded = set(json.loads(proc.stdout.strip().splitlines()[-1]))
    assert set(modules) <= loaded
    leaked = sorted(m for m in loaded if is_forbidden(m))
    assert not leaked, leaked


@pytest.mark.parametrize('path', study_files(), ids=lambda p: str(p.relative_to(STUDY)))
def test_study_source_has_no_legacy_import_or_config_root(path):
    found = violations(path)
    assert not found, '\n'.join(found)


@pytest.mark.parametrize('source, forbidden', [
    ('import mlkit.config', True),
    ('from mlkit import config', True),
    ('from mlkit.config import ROOT', True),
    ('from .. import config', True),
    ('from ..config import ROOT', True),
    ('from .. import classical, pilot', True),
    ('import mlkit.quality.sub', True),
    ('def later():\n    from mlkit import holdout', True),
    ('x = config.ROOT', True),
    ('import mlkit\nx = mlkit.config.ROOT', True),
    ('importlib.import_module("mlkit.gate")', True),
    ('__import__("mlkit.run")', True),
    ('from . import case', False),
    ('from .. import classical, decision', False),
    ('import mlkit.reliability', False),
    ('import mlkit.running_total', False),
    ('ROOT = "x"', False),
])
def test_scanner_detects_forbidden_forms(tmp_path, source, forbidden):
    probe = tmp_path / 'mlkit' / 'study' / 'sub' / 'probe.py'
    probe.parent.mkdir(parents=True)
    probe.write_text(source.replace('from ..', 'from ...') + '\n', encoding='utf-8')
    assert bool(violations(probe, tmp_path)) is forbidden
