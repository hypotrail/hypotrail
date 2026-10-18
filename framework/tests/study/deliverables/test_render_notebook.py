"""Generated notebook and workbench (plan WP3.2, §6; ADR 0001 decision 1).

Permanent versions of the WP0.6 spike checks (``framework/tests/spikes``), run against
the real modules: headless execution, no fit and no state write, the read-only guard,
byte-for-byte preservation of user edits, an untouched workbench, a template bump that
writes a candidate only, and the Marimo round trip. Notebook execution always happens
in a subprocess so the audit hook never reaches the pytest process.

The ``marimo export html`` criteria (strict xfails) stay in the spike: export is not a
deliverable (ADR 0001 decision 2).
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from mlkit.study import manifest as mf, read, render_notebook as rn, view
from mlkit.study.errors import StudyError
from mlkit.study.store import StudyStore
from mlkit.study.templates import workbench as wb_template

import phase3_study as fx

FRAMEWORK = Path(__file__).resolve().parents[3]
STUDY_PKG = FRAMEWORK / 'mlkit' / 'study'
FIT_CALLS = {'fit', 'fit_transform', 'partial_fit', 'fit_predict'}
WRITER_MODULES = {'store', 'lock', 'registry', 'exposure', 'dependencies', 'commands', 'cli',
                  'migrate', 'preconditions', 'cmd_render', 'cmd_run', 'render_notebook',
                  'manifest'}
NOTEBOOK_SIDE = ('notebook_view.py', 'read.py', 'view.py', 'guard.py', 'cite.py', 'texts.py',
                 'render_html.py', 'state.py', 'records.py', 'case.py', 'errors.py')


def render(study: Path, **kw) -> dict:
    """What ``hypotrail render`` does for the notebooks (without the HTML)."""
    manifest = mf.load(study)
    out = rn.render(study, view.build(study), manifest, **kw)
    manifest['artifacts'].update(notebook=out['notebook'], workbench=out['workbench'])
    mf.save(study, manifest)
    return out


def advance(study: Path) -> int:
    """Commit one revision without any automatic render."""
    store = StudyStore(study)
    with store.writing() as state:
        store.commit(state, {'request_id': None, 'action': 'test.advance', 'params': {},
                             'result': {}})
    return read.open(study).revision


@pytest.fixture
def study(full_study) -> Path:
    render(full_study)
    return full_study


def _generated(study):
    return study / rn.GENERATED


def _workbench(study):
    return study / rn.WORKBENCH


def _env(**extra):
    env = {k: v for k, v in os.environ.items() if k not in ('HYPOTRAIL_READ_ONLY',
                                                              'HYPOTRAIL_FAULT')}
    env.update(extra)
    return env


def _run(args, cwd, **env):
    return subprocess.run(args, cwd=cwd, env=_env(**env), capture_output=True, text=True,
                          timeout=180, stdin=subprocess.DEVNULL)


def _hashes(study: Path) -> dict:
    root = study / '.hypotrail'
    return {str(p.relative_to(study)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file() and p.name != 'writer.lock'}


# --- 1. headless execution --------------------------------------------------------------

@pytest.mark.parametrize('which', ['generated', 'workbench'])
def test_notebooks_run_as_scripts(study, which):
    path = _generated(study) if which == 'generated' else _workbench(study)
    proc = _run([sys.executable, str(path)], cwd=study.parent)
    assert proc.returncode == 0, proc.stderr
    assert 'Traceback' not in proc.stderr, proc.stderr


def test_app_run_shows_the_numbers_of_the_report(study):
    script = (
        'import importlib.util, json, re, sys\n'
        f'spec = importlib.util.spec_from_file_location("nb", {str(_generated(study))!r})\n'
        'nb = importlib.util.module_from_spec(spec); spec.loader.exec_module(nb)\n'
        'outputs, defs = nb.app.run()\n'
        'from mlkit.study import notebook_view as nv\n'
        'html = nv.step_html(defs["cited"], nb.RESULT_IDS, ["split", "eda.target_rate"], "", "")\n'
        'print(json.dumps({"revision": defs["study"].revision, "outputs": len(outputs),\n'
        '    "sklearn": "sklearn" in sys.modules, "pandas": "pandas" in sys.modules,\n'
        '    "data": re.findall(r"<data[^>]*>[^<]*</data>", html)}))\n')
    proc = _run([sys.executable, '-c', script], cwd=study.parent)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    assert out['revision'] == read.open(study).revision
    assert out['sklearn'] is False and out['pandas'] is False
    report = (study / mf.ARTIFACTS['report'])
    page = report.read_text() if report.exists() else None
    assert out['data'] and all('data-result-id=' in d for d in out['data'])
    if page is not None:                 # the HTML report cites the same values
        for d in out['data']:
            assert d in page, d


# --- 2. no fit and no state write -------------------------------------------------------

def _imports(source: str) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = '.' * node.level + (node.module or '')
            found += [f'{base}.{a.name}' if base and not base.endswith('.') else base + a.name
                      for a in node.names]
    return found


def _forbidden(source: str) -> list[str]:
    bad = []
    for name in _imports(source):
        root = name.lstrip('.').split('.')
        if root[0] in ('sklearn', 'scipy') or set(root) & WRITER_MODULES \
                or (root[0] == 'mlkit' and len(root) > 1 and root[1] != 'study'):
            bad.append(name)
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in FIT_CALLS:
            bad.append(f'.{node.func.attr}(')
    return bad


def test_notebooks_and_their_read_side_import_no_writer_no_sklearn_no_fit(study):
    sources = {'study_generated.py': _generated(study).read_text(),
               'workbench.py': _workbench(study).read_text()}
    for name in NOTEBOOK_SIDE:
        sources[name] = (STUDY_PKG / name).read_text()
    assert {k: _forbidden(v) for k, v in sources.items()} == {k: [] for k in sources}
    nb_imports = set(_imports(sources['study_generated.py'])) | set(
        _imports(sources['workbench.py']))
    assert nb_imports == {'os', 'pathlib.Path', 'marimo', 'mlkit.study.notebook_view'}
    assert 'from mlkit.study import notebook_view as nv' in sources['study_generated.py']
    assert 'model.fit(' not in sources['study_generated.py']


def test_scanner_detects_forbidden_forms():
    assert _forbidden('from sklearn.linear_model import X\nm.fit(a, b)\n') == [
        'sklearn.linear_model.X', '.fit(']
    assert _forbidden('from . import store') and _forbidden('from mlkit.study import registry')
    assert _forbidden('import mlkit.pilot')


def test_generated_setup_sets_read_only_once(study):
    tree = ast.parse(_generated(study).read_text())
    assigns = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)
               and ast.unparse(n.targets[0]) == "os.environ['HYPOTRAIL_READ_ONLY']"]
    assert len(assigns) == 1 and ast.literal_eval(assigns[0].value) == '1'


def test_execution_leaves_state_registry_manifest_unchanged(study):
    before = _hashes(study)
    assert {'state.json', 'artifacts.json'} <= {Path(k).name for k in before}
    for path in (_generated(study), _workbench(study)):
        assert _run([sys.executable, str(path)], cwd=study.parent).returncode == 0
    assert _hashes(study) == before


def test_read_only_guard_refuses_writes_from_an_edited_cell(study):
    before = _hashes(study)
    source = _generated(study).read_text()
    hostile = source.replace(
        '    study = nv.open_study(STUDY_DIR)\n',
        '    study = nv.open_study(STUDY_DIR)\n'
        '    for _attempt in ("write", "replace", "remove"):\n'
        '        try:\n'
        '            if _attempt == "write":\n'
        '                (STUDY_DIR / ".hypotrail" / "state.json").write_text("{}")\n'
        '            elif _attempt == "replace":\n'
        '                import os as _os\n'
        '                _os.replace(STUDY_DIR / ".hypotrail" / "artifacts.json", STUDY_DIR / "x.json")\n'
        '            else:\n'
        '                (STUDY_DIR / ".hypotrail" / "state.sha256").unlink()\n'
        '            print("SUCCEEDED", _attempt)\n'
        '        except PermissionError as _error:\n'
        '            print("REFUSED", _attempt, type(_error).__name__)\n', 1)
    assert hostile != source
    scratch = study / 'notebooks' / 'hostile.py'
    scratch.write_text(hostile)
    proc = _run([sys.executable, str(scratch)], cwd=study.parent)
    for attempt in ('write', 'replace', 'remove'):
        assert f'REFUSED {attempt} ReadOnlyError' in proc.stdout, proc.stdout + proc.stderr
    assert 'SUCCEEDED' not in proc.stdout
    assert _hashes(study) == before


def test_render_refuses_in_a_read_only_process(study):
    script = ('from mlkit.study import render_notebook, view, manifest\n'
              f'p = {str(study)!r}\n'
              'render_notebook.render(p, view.build(p), manifest.load(p))\n')
    proc = _run([sys.executable, '-c', script], cwd=study.parent, HYPOTRAIL_READ_ONLY='1')
    assert proc.returncode != 0 and 'read_only_process' in proc.stderr
    os.environ.pop('HYPOTRAIL_READ_ONLY', None)
    with pytest.raises(StudyError) as err:
        os.environ['HYPOTRAIL_READ_ONLY'] = '1'
        try:
            rn.render(study, view.build(study), mf.load(study))
        finally:
            del os.environ['HYPOTRAIL_READ_ONLY']
    assert err.value.code == 'read_only_process'


# --- 3. user edits preserved ------------------------------------------------------------

def test_user_edit_is_preserved_byte_for_byte_then_regenerated(study):
    notebook = _generated(study)
    rev = read.open(study).revision
    edited = notebook.read_bytes().replace(b'study = nv.open_study(STUDY_DIR)',
                                           b'study = nv.open_study(STUDY_DIR)  # my tweak\r\n'
                                           b'    extra = 1', 1)
    edited += '\n# trailing note é\n'.encode()
    notebook.write_bytes(edited)
    new_rev = advance(study)
    out = render(study)
    name = f'notebooks/study_generated.user-edits-{rev}.py'
    assert out['preserved'] == [name]
    assert (study / name).read_bytes() == edited
    assert notebook.read_text() == rn.generate_study_source(view.build(study))
    assert f'at revision {new_rev}' in notebook.read_text()
    item = mf.load(study)['artifacts']['notebook']
    assert item['user_edits_preserved'] == [name] and item['revision'] == new_rev


def test_unedited_render_preserves_nothing_and_repeat_edits_never_overwrite(study):
    assert render(study)['preserved'] == []
    rev = read.open(study).revision
    notebook = _generated(study)
    for n, suffix in ((1, ''), (2, '-2')):
        notebook.write_bytes(notebook.read_bytes() + f'# edit {n}\n'.encode())
        expected = notebook.read_bytes()
        assert render(study)['preserved'] == [f'notebooks/study_generated.user-edits-{rev}{suffix}.py']
        assert (study / f'notebooks/study_generated.user-edits-{rev}{suffix}.py').read_bytes() == expected


def test_generator_is_deterministic(study):
    first = _generated(study).read_bytes()
    render(study)
    assert _generated(study).read_bytes() == first
    assert rn.generate_study_source(view.build(study)).encode() == first


def test_an_edit_saved_during_the_render_is_preserved_too(study, monkeypatch):
    """The hash is checked again right before os.replace (Marimo autosaves)."""
    notebook = _generated(study)
    racing = notebook.read_bytes() + b'# saved by the editor during the render\n'
    calls = []

    def editor_saves(path):
        if not calls:
            path.write_bytes(racing)
        calls.append(path)

    monkeypatch.setattr(rn, 'before_replace', editor_saves)
    out = render(study)
    rev = read.open(study).revision
    assert out['preserved'] == [f'notebooks/study_generated.user-edits-{rev}.py']
    assert (study / out['preserved'][0]).read_bytes() == racing
    assert notebook.read_text() == rn.generate_study_source(view.build(study))
    assert len(calls) == 2


def test_generated_with_stamp_is_the_only_version_coupling(study):
    from marimo._utils.generated_with import contents_differ_excluding_generated_with

    notebook = _generated(study)
    text = notebook.read_text()
    bumped = text.replace('__generated_with = "0.25.1"', '__generated_with = "0.99.0"')
    assert bumped != text and not contents_differ_excluding_generated_with(text, bumped)
    notebook.write_text(bumped)
    assert render(study)['preserved'] == []


def test_a_notebook_without_a_manifest_record_is_preserved(study):
    notebook = _generated(study)
    mine = b'# a file the user put here\n'
    notebook.write_bytes(mine)
    manifest = mf.load(study)
    manifest['artifacts'].pop('notebook')
    mf.save(study, manifest)
    out = render(study)
    assert len(out['preserved']) == 1 and (study / out['preserved'][0]).read_bytes() == mine


def test_pending_steps_say_not_executed_yet(tmp_path, synthetic_case_dir):
    b = fx.build(tmp_path / 'study', synthetic_case_dir, upto='split')
    render(b.study)
    source = _generated(b.study).read_text()
    assert source.count('_Not executed yet._') == 2           # train_eda and models
    assert '"split"' in source and 'fit.logistic' not in source.split('RESULT_IDS')[1].split('}')[0]
    proc = _run([sys.executable, str(_generated(b.study))], cwd=b.study.parent)
    assert proc.returncode == 0, proc.stderr


# --- 4. workbench intact ----------------------------------------------------------------

def test_workbench_is_byte_identical_across_regenerations(study):
    workbench = _workbench(study)
    text = workbench.read_text()
    assert f'label="{wb_template.EXPERIMENT_LABEL}"' in text and '## Your notes' in text
    mine = text.replace('Write your observations here.',
                        'Write your observations here. Precision falls past the cut.').encode()
    workbench.write_bytes(mine)
    for _ in range(2):
        advance(study)
        out = render(study)
        assert workbench.read_bytes() == mine
        assert out['workbench']['candidate'] is None
    assert not (study / rn.CANDIDATE).exists()


def test_workbench_template_bump_writes_candidate_only(study):
    before = _workbench(study).read_bytes()
    out = render(study, workbench_template_version=wb_template.TEMPLATE_VERSION + 1)
    candidate = study / rn.CANDIDATE
    assert _workbench(study).read_bytes() == before
    assert candidate.read_text() == rn.generate_workbench_source(wb_template.TEMPLATE_VERSION + 1)
    assert candidate.read_bytes() != before
    record = mf.load(study)['artifacts']['workbench']
    assert record['template_version'] == wb_template.TEMPLATE_VERSION
    assert record['candidate']['template_version'] == wb_template.TEMPLATE_VERSION + 1
    assert out['workbench']['generated'] is False


def test_workbench_uses_the_policy_function_or_says_it_is_missing(study):
    source = _workbench(study).read_text()
    assert 'study_generated' not in source
    script = (
        'import importlib.util, json\n'
        f'spec = importlib.util.spec_from_file_location("wb", {str(_workbench(study))!r})\n'
        'wb = importlib.util.module_from_spec(spec); spec.loader.exec_module(wb)\n'
        'outputs, defs = wb.app.run()\n'
        'from mlkit.study import notebook_view as nv\n'
        'html = nv.experiment_html(defs["policy"], defs["scores"], defs["study"], "capacity", 0.5, 20)\n'
        'print(json.dumps({"policy": defs["policy"] is not None, "n": defs["scores"]["n"],\n'
        '                  "html": html}))\n')
    proc = _run([sys.executable, '-c', script], cwd=study.parent)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    assert out['n'] == 90
    from importlib.util import find_spec
    has_policy = find_spec('mlkit.study.policy') is not None
    assert out['policy'] is has_policy
    if has_policy:
        assert 'Experiment, not adopted' in out['html'] and 'capacity:20' in out['html']
    else:
        assert 'not available in this version' in out['html']


# --- 5. Marimo round trip ---------------------------------------------------------------

def _editor_reserialize(path: Path) -> str:
    from marimo._server.models.models import SaveNotebookRequest
    from marimo._session.notebook.file_manager import AppFileManager

    manager = AppFileManager(path)
    cells = list(manager.app.cell_manager.cell_data())
    return manager.save(SaveNotebookRequest(
        cell_ids=[c.cell_id for c in cells], codes=[c.code for c in cells],
        names=[c.name for c in cells], configs=[c.config for c in cells],
        filename=str(path), persist=False))


@pytest.mark.parametrize('which', ['generated', 'workbench'])
def test_round_trip_parser_and_codegen_reproduce_bytes(study, which):
    from marimo._convert.converters import MarimoConvert

    path = _generated(study) if which == 'generated' else _workbench(study)
    source = path.read_text()
    assert MarimoConvert.from_py(source).to_py() == source
    assert _editor_reserialize(path) == source
