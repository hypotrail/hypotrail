"""Read-only API and single view model (plan WP1.3, §6, §9 bis)."""
from __future__ import annotations

import ast
import gzip
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from mlkit.study import exposure, read, registry, view
from mlkit.study.errors import StudyError

FRAMEWORK = Path(__file__).resolve().parents[2]
STUDY_PKG = FRAMEWORK / 'mlkit' / 'study'
READ_ONLY_MODULES = ('read.py', 'view.py')
WRITER_MODULES = frozenset({'store', 'lock', 'registry', 'exposure', 'dependencies', 'commands',
                            'cli', 'migrate', 'preconditions'})
WRITE_ATTRIBUTES = frozenset({'write_text', 'write_bytes', 'mkdir', 'unlink', 'rmdir', 'rename',
                              'touch', 'replace', 'symlink_to', 'chmod', 'truncate', 'makedirs',
                              'remove', 'rmtree', 'dump'})


def _mode_writes(node: ast.Call) -> bool:
    mode = node.args[1] if len(node.args) > 1 else next(
        (k.value for k in node.keywords if k.arg == 'mode'), None)
    if mode is None:
        return False
    if not isinstance(mode, ast.Constant) or not isinstance(mode.value, str):
        return True       # a computed mode is treated as a write
    return any(c in mode.value for c in 'wax+')


def write_violations(source: str) -> list[str]:
    tree = ast.parse(source)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in WRITE_ATTRIBUTES:
                found.append(f'{node.lineno}: .{func.attr}(')
            if isinstance(func, ast.Name) and func.id == 'open' and _mode_writes(node):
                found.append(f'{node.lineno}: open(..., write mode)')
            if isinstance(func, ast.Attribute) and func.attr == 'open' and _mode_writes(node):
                found.append(f'{node.lineno}: .open(..., write mode)')
        elif isinstance(node, ast.ImportFrom):
            module = (node.module or '')
            names = [a.name for a in node.names]
            if node.level and not module:
                found += [f'{node.lineno}: import {n}' for n in names if n in WRITER_MODULES]
            elif module.split('.')[-1] in WRITER_MODULES:
                found.append(f'{node.lineno}: from {module}')
            elif module in ('mlkit.study', 'mlkit'):
                found += [f'{node.lineno}: import {n}' for n in names if n in WRITER_MODULES]
            if module in ('os', 'shutil') and set(names) & (WRITE_ATTRIBUTES | {'replace'}):
                found.append(f'{node.lineno}: from {module} import writer')
        elif isinstance(node, ast.Import):
            found += [f'{node.lineno}: import {a.name}' for a in node.names
                      if a.name.split('.')[-1] in WRITER_MODULES and a.name.startswith('mlkit')]
    return found


@pytest.mark.parametrize('name', READ_ONLY_MODULES)
def test_read_and_view_contain_no_write_call_and_no_writer_import(name):
    found = write_violations((STUDY_PKG / name).read_text(encoding='utf-8'))
    assert not found, found


@pytest.mark.parametrize('source', [
    'p.write_text("x")', 'open(p, "w")', 'open(p, mode="a")', 'open(p, "rb+")', 'os.replace(a, b)',
    'p.mkdir()', 'p.unlink()', 'from . import store', 'from .registry import put',
    'from mlkit.study import exposure', 'import mlkit.study.lock', 'json.dump(x, f)',
    'from os import replace',
])
def test_write_scanner_detects_forbidden_forms(source):
    assert write_violations(source)


@pytest.mark.parametrize('source', ['p.read_text()', 'open(p)', 'open(p, "rb")', 'from . import state',
                                    'from . import read', 'json.dumps(x)'])
def test_write_scanner_accepts_reads(source):
    assert not write_violations(source)


def test_read_and_view_import_no_heavy_library_or_writer_module():
    code = ('import json, sys, time\n'
            't = time.perf_counter()\n'
            'import mlkit.study.view, mlkit.study.read\n'
            'elapsed = time.perf_counter() - t\n'
            'mods = sorted(sys.modules)\n'
            'print(json.dumps({"seconds": elapsed, "modules": mods}))\n')
    env = {**os.environ, 'PYTHONPATH': str(FRAMEWORK)}
    proc = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, env=env,
                          cwd=FRAMEWORK, timeout=60)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    print(f'\nimport mlkit.study.view, read: {out["seconds"] * 1000:.1f} ms')
    heavy = [m for m in out['modules'] if m.split('.')[0] in {'pandas', 'numpy', 'sklearn', 'scipy'}]
    assert heavy == []
    writers = [m for m in out['modules'] if m.startswith('mlkit.study.')
               and m.split('.')[-1] in WRITER_MODULES]
    assert writers == []


def _tree_digest(root: Path) -> dict:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file()}


def _csv_gz(rows) -> bytes:
    text = 'row_key,y,score\n' + ''.join(f'{k},{y},{s}\n' for k, y, s in rows)
    return gzip.compress(text.encode(), mtime=0)


@pytest.fixture
def populated(new_study):
    """A study with one promoted result that has predictions, plus one exposure."""
    code = registry.code_fingerprint(['mlkit.study.records'])
    eid = exposure.new_exposure_id()
    put = registry.put(new_study, activity='fit.baseline', params={}, inputs={}, code=code,
                       values={'auc': 0.5}, blobs={'predictions': _csv_gz([('L2', 1, 0.1),
                                                                           ('L3', 0, 0.1)])},
                       partition='validation', n_rows=2, exposure_id=eid)
    exposure.record(new_study, exposure_id=eid, revision=1, activity='fit.baseline',
                    result_id=put['result_id'], purpose='validation_model_evaluation',
                    partition='validation', row_keys=['L2', 'L3'], dataset_sha256='d' * 64,
                    columns=['outcome'])
    with new_study.writing() as state:
        state['current']['fit.baseline'] = put['result_id']
        new_study.commit(state, {'request_id': None, 'action': 'test.promote', 'params': {},
                                 'result': {}})
    return new_study, put['result_id']


def test_read_api_answers_from_one_verified_snapshot_without_writing(populated):
    store, rid = populated
    before = _tree_digest(store.study_dir)
    study = read.open(store.study_dir)
    assert study.revision == 2
    assert study.current('fit.baseline')['result_id'] == rid
    assert study.current('fit.logistic') is None
    assert study.is_current('fit.baseline')
    assert study.result(rid)['output']['values'] == {'auc': 0.5}
    frame = study.predictions(rid)
    assert list(frame.columns) == ['row_key', 'y', 'score'] and list(frame['row_key']) == ['L2', 'L3']
    src = study.source('fit.baseline')
    assert src['fingerprint_matches'] is True
    assert 'def canonical' in src['modules']['mlkit.study.records']
    assert [r['revision'] for r in study.revisions(0)] == [1, 2]
    assert [r['revision'] for r in study.revisions(1)] == [2]
    copy_ = study.state
    copy_['current'].clear()
    assert study.current('fit.baseline') is not None          # the snapshot is protected
    assert _tree_digest(store.study_dir) == before


def test_read_refuses_divergent_state_and_unknown_results(populated):
    store, rid = populated
    with pytest.raises(StudyError) as err:
        read.open(store.study_dir).result('0' * 64)
    assert err.value.code == 'unknown_result'
    path = store.state_path
    path.write_bytes(path.read_bytes().replace(b'"revision": 2', b'"revision": 3'))
    with pytest.raises(StudyError) as err:
        read.open(store.study_dir)
    assert err.value.code == 'integrity_error'


def test_view_has_the_contract_keys_and_is_deterministic(populated):
    store, rid = populated
    before = _tree_digest(store.study_dir)
    first, second = view.build(store.study_dir), view.build(read.open(store.study_dir))
    assert first == second
    assert tuple(first) == view.VIEW_KEYS
    json.dumps(first)                                          # JSON-serialisable
    # WP-A4: no proposal yet, so step 0 (the data card) is the current step.
    assert first['revision'] == 2 and first['current_step'] == 'discover_data'
    assert first['next_action']['kind'] == 'show_data_card'
    result = first['results']['fit.baseline']
    assert tuple(result) == view.RESULT_VIEW_KEYS
    assert result['result_id'] == rid and result['current'] and result['integrity'] == 'ok'
    assert result['values'] == {'auc': 0.5}
    assert first['exposure']['validation_rows_used_for_selection'] == 2
    assert first['artifacts']['status'] == 'not_rendered'
    assert set(first['facts']['by_status']) == {'documented_fact', 'scenario_assumption',
                                                'observed', 'unknown'}
    assert set(first['decisions']) == {'prediction_time', 'feature_availability', 'split',
                                       'success_criterion', 'preprocessing', 'policy',
                                       'conclusion',
                                       # WP-B1
                                           'model_variant', 'model_choice', 'final_test'}
    assert all(tuple(d) == view.DECISION_VIEW_KEYS for d in first['decisions'].values())
    assert first['not_yet_defensible'][0]['id'] == 'unconfirmed_decisions'
    assert _tree_digest(store.study_dir) == before


def test_view_reports_a_broken_result_instead_of_citing_it(populated):
    store, rid = populated
    path = store.home / 'registry' / f'{rid}.json'
    entry = json.loads(path.read_text())
    entry['output']['values']['auc'] = 0.9
    path.write_text(json.dumps(entry))
    v = view.build(store.study_dir)
    assert v['results']['fit.baseline']['integrity'] == 'integrity_error'
    assert v['results']['fit.baseline']['values'] is None
    assert v['results']['fit.baseline']['current'] is False
    assert 'result_integrity' in [x['id'] for x in v['not_yet_defensible']]
