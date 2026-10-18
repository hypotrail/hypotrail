"""Spike WP0.6: can Marimo 0.25.1 carry the generated notebook and workbench?

Run explicitly:

    HYPOTRAIL_RUN_SPIKES=1 PYTHONPATH=framework python -m pytest -q framework/tests/spikes

Every study lives in ``tmp_path`` with fake state and registry JSON. Notebook
execution always happens in a subprocess so that the read-only audit hook
never reaches the pytest process.

Tests marked ``xfail(strict=True)`` state a property Hypotrail needs and
record that Marimo 0.25.1 does not provide it. They are findings, not
tolerated failures: if Marimo changes, the XPASS fails the run and the ADR
(docs/decisions/0001-notebook-and-html.md) must be revisited.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from html.parser import HTMLParser
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("HYPOTRAIL_RUN_SPIKES") != "1",
    reason="spike: set HYPOTRAIL_RUN_SPIKES=1 to run",
)

SPIKES_DIR = Path(__file__).resolve().parent
PROTOTYPE_DIR = SPIKES_DIR / "prototype"
FIT_CALLS = {"fit", "fit_transform", "partial_fit", "fit_predict"}
FORBIDDEN_IMPORT_ROOTS = {"sklearn", "mlkit"}


# --------------------------------------------------------------------------- helpers

@pytest.fixture(scope="module")
def proto():
    pytest.importorskip("marimo")
    if str(SPIKES_DIR) not in sys.path:
        sys.path.insert(0, str(SPIKES_DIR))
    from prototype import fixture, read, render_notebook

    class Proto:
        pass

    Proto.fixture, Proto.read, Proto.render = fixture, read, render_notebook
    return Proto


@pytest.fixture
def study(tmp_path, proto):
    path = proto.fixture.make_study(tmp_path)
    proto.render.render(path)
    return path


def _env(**extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "HYPOTRAIL_READ_ONLY"}
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(SPIKES_DIR), env.get("PYTHONPATH")]))
    env.update(extra)
    return env


def _run(args: list[str], cwd: Path, timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, env=_env(), capture_output=True, text=True,
                          timeout=timeout, stdin=subprocess.DEVNULL)


def _export(notebook: Path, output: Path, *extra: str) -> tuple[subprocess.CompletedProcess, float]:
    start = time.perf_counter()
    proc = _run([sys.executable, "-m", "marimo", "export", "html", "--no-sandbox", *extra,
                 str(notebook), "-o", str(output), "-f"], cwd=notebook.parent)
    return proc, time.perf_counter() - start


def _state_hashes(study: Path) -> dict[str, str]:
    root = study / ".hypotrail"
    return {str(p.relative_to(study)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def _generated(study: Path) -> Path:
    return study / "notebooks" / "study_generated.py"


def _workbench(study: Path) -> Path:
    return study / "notebooks" / "workbench.py"


class _TagCollector(HTMLParser):
    """Static DOM as a browser sees it before any script runs."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.external: list[str] = []
        self.data_result_ids: list[str] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        for key in ("src", "href"):
            value = attributes.get(key) or ""
            if re.match(r"^(https?:)?//", value):
                self.external.append(f"<{tag} {key}={value}>")
        if tag == "data" and "data-result-id" in attributes:
            self.data_result_ids.append(attributes["data-result-id"])


def _parse(html_text: str) -> _TagCollector:
    collector = _TagCollector()
    collector.feed(html_text)
    return collector


# --------------------------------------------------------------- 1. headless execution

def test_generated_notebook_runs_as_script(study):
    """``python study_generated.py`` runs ``app.run()`` (codegen footer)."""
    proc = _run([sys.executable, str(_generated(study))], cwd=study.parent)
    assert proc.returncode == 0, proc.stderr


def test_generated_notebook_app_run_returns_view(study):
    """``app.run()`` returns (outputs, defs); the view comes from fixture state."""
    script = (
        "import importlib.util, json, sys\n"
        f"spec = importlib.util.spec_from_file_location('nb', {str(_generated(study))!r})\n"
        "nb = importlib.util.module_from_spec(spec); spec.loader.exec_module(nb)\n"
        "outputs, defs = nb.app.run()\n"
        "print(json.dumps({'revision': defs['view'].revision,\n"
        "                  'outputs': len(outputs),\n"
        "                  'sklearn': 'sklearn' in sys.modules}))\n"
    )
    proc = _run([sys.executable, "-c", script], cwd=study.parent)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout.strip().splitlines()[-1])
    assert result == {"revision": 7, "outputs": 6, "sklearn": False}


@pytest.mark.parametrize("which", ["generated", "workbench"])
def test_notebooks_export_html(study, which, tmp_path):
    notebook = _generated(study) if which == "generated" else _workbench(study)
    proc, _ = _export(notebook, tmp_path / f"{which}.html")
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / f"{which}.html").stat().st_size > 0


# ------------------------------------------------------- 2. no fit and no state write

def _forbidden_nodes(source: str) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names if a.name.split(".")[0] in FORBIDDEN_IMPORT_ROOTS]
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in FORBIDDEN_IMPORT_ROOTS:
                found.append(node.module)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in FIT_CALLS:
                found.append(f".{node.func.attr}(")
    return found


def test_ast_scan_no_fit_no_sklearn(study):
    sources = {
        "study_generated.py": _generated(study).read_text(encoding="utf-8"),
        "workbench.py": _workbench(study).read_text(encoding="utf-8"),
    }
    for module in ("read.py", "guard.py", "policy.py"):
        sources[f"prototype/{module}"] = (PROTOTYPE_DIR / module).read_text(encoding="utf-8")
    assert {name: _forbidden_nodes(src) for name, src in sources.items()} == {
        name: [] for name in sources}
    # The fit source exists only as registry data, displayed at run time.
    assert "model.fit(" not in sources["study_generated.py"]


def test_ast_scan_detects_a_fit(proto):
    """The scanner itself must catch what it claims to forbid."""
    assert _forbidden_nodes("from sklearn.linear_model import LogisticRegression\nm.fit(X, y)\n") == [
        "sklearn.linear_model", ".fit("]


def test_generated_setup_sets_read_only(study):
    tree = ast.parse(_generated(study).read_text(encoding="utf-8"))
    assigns = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)
               and ast.unparse(n.targets[0]) == "os.environ['HYPOTRAIL_READ_ONLY']"]
    assert len(assigns) == 1 and ast.literal_eval(assigns[0].value) == "1"


def test_execution_leaves_state_registry_manifest_unchanged(study, tmp_path):
    before = _state_hashes(study)
    assert {"state.json", "artifacts.json"} <= {Path(k).name for k in before}
    for notebook in (_generated(study), _workbench(study)):
        assert _run([sys.executable, str(notebook)], cwd=study.parent).returncode == 0
        proc, _ = _export(notebook, tmp_path / f"{notebook.stem}.html")
        assert proc.returncode == 0, proc.stderr
    assert _state_hashes(study) == before


def test_read_only_guard_refuses_writes_from_an_edited_cell(study):
    """A user cell that writes state is refused by the audit hook; nothing changes."""
    before = _state_hashes(study)
    notebook = _generated(study)
    source = notebook.read_text(encoding="utf-8")
    hostile = source.replace(
        "    view = read.open(STUDY_DIR)\n",
        "    view = read.open(STUDY_DIR)\n"
        "    try:\n"
        "        (STUDY_DIR / '.hypotrail' / 'state.json').write_text('{}')\n"
        "        print('WRITE-SUCCEEDED')\n"
        "    except PermissionError as error:\n"
        "        print('WRITE-REFUSED', type(error).__name__)\n"
        "    try:\n"
        "        import os as _os\n"
        "        _os.replace(STUDY_DIR / '.hypotrail' / 'artifacts.json', STUDY_DIR / 'moved.json')\n"
        "        print('REPLACE-SUCCEEDED')\n"
        "    except PermissionError as error:\n"
        "        print('REPLACE-REFUSED', type(error).__name__)\n",
        1,
    )
    assert hostile != source
    scratch = study / "notebooks" / "hostile.py"
    scratch.write_text(hostile, encoding="utf-8")
    proc = _run([sys.executable, str(scratch)], cwd=study.parent)
    assert "WRITE-REFUSED ReadOnlyError" in proc.stdout, proc.stdout + proc.stderr
    assert "REPLACE-REFUSED ReadOnlyError" in proc.stdout
    assert "SUCCEEDED" not in proc.stdout
    assert _state_hashes(study) == before


def test_render_refuses_in_read_only_process(study):
    script = ("from pathlib import Path\nfrom prototype import render_notebook\n"
              f"render_notebook.render(Path({str(study)!r}))\n")
    proc = subprocess.run([sys.executable, "-c", script], env=_env(HYPOTRAIL_READ_ONLY="1"),
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode != 0 and "ReadOnlyError" in proc.stderr


# ------------------------------------------------------------ 3. user edits preserved

def test_user_edit_is_preserved_byte_for_byte_then_regenerated(study, proto):
    notebook = _generated(study)
    edited = notebook.read_bytes().replace(b"view = read.open(STUDY_DIR)",
                                           b"view = read.open(STUDY_DIR)  # my tweak\r\n    extra = 1", 1)
    edited += "\n# trailing note é\n".encode("utf-8")
    notebook.write_bytes(edited)
    proto.fixture.write_state(study, 8)

    report = proto.render.render(study)

    copy = study / "notebooks" / "study_generated.user-edits-7.py"
    assert report["preserved"] == "notebooks/study_generated.user-edits-7.py"
    assert copy.read_bytes() == edited
    view = proto.read.build(study)
    assert notebook.read_text(encoding="utf-8") == proto.render.generate_study_source(view)
    assert "at revision 8" in notebook.read_text(encoding="utf-8")
    manifest = json.loads((study / ".hypotrail" / "artifacts.json").read_text())
    assert manifest["artifacts"]["notebooks/study_generated.py"]["user_edits_preserved"] == [
        "notebooks/study_generated.user-edits-7.py"]


def test_unedited_render_preserves_nothing_and_repeat_edits_never_overwrite(study, proto):
    assert proto.render.render(study)["preserved"] is None
    notebook = _generated(study)
    for n, suffix in ((1, ""), (2, "-2")):
        notebook.write_bytes(notebook.read_bytes() + f"# edit {n}\n".encode())
        expected = notebook.read_bytes()
        assert proto.render.render(study)["preserved"] == f"notebooks/study_generated.user-edits-7{suffix}.py"
        assert (study / "notebooks" / f"study_generated.user-edits-7{suffix}.py").read_bytes() == expected


def test_generator_is_deterministic(study, proto):
    first = _generated(study).read_bytes()
    proto.render.render(study)
    assert _generated(study).read_bytes() == first


# -------------------------------------------------------------- 4. workbench intact

def test_workbench_is_byte_identical_across_regenerations(study, proto):
    workbench = _workbench(study)
    text = workbench.read_text(encoding="utf-8")
    assert 'label="Experiment, not adopted"' in text
    assert "## Your notes" in text
    mine = text.replace("Write your observations here.",
                        "Write your observations here. Precision falls past 0.6.").encode()
    workbench.write_bytes(mine)
    for revision in (8, 9):
        proto.fixture.write_state(study, revision)
        report = proto.render.render(study)
        assert report["workbench"] == "kept" and report["candidate"] is None
        assert workbench.read_bytes() == mine
    assert not (study / "notebooks" / "workbench.candidate.py").exists()


def test_workbench_template_bump_writes_candidate_only(study, proto):
    workbench = _workbench(study)
    before = workbench.read_bytes()
    report = proto.render.render(study, workbench_template_version=2)
    candidate = study / "notebooks" / "workbench.candidate.py"
    assert report["candidate"] == "notebooks/workbench.candidate.py"
    assert workbench.read_bytes() == before
    assert candidate.read_text(encoding="utf-8") == proto.render.generate_workbench_source(2)
    assert candidate.read_bytes() != before
    record = json.loads((study / ".hypotrail" / "artifacts.json").read_text())["artifacts"][
        "notebooks/workbench.py"]
    assert record["template_version"] == 1 and record["candidate"]["template_version"] == 2


def test_workbench_runs_and_does_not_import_generated_notebook(study):
    source = _workbench(study).read_text(encoding="utf-8")
    assert "study_generated" not in source
    proc = _run([sys.executable, str(_workbench(study))], cwd=study.parent)
    assert proc.returncode == 0, proc.stderr


# ------------------------------------------------------------- 5. Marimo round trip

def _editor_reserialize(path: Path) -> str:
    """Exactly what the editor's save path writes for an unmodified notebook.

    AppFileManager.save -> _save_file -> PythonNotebookSerializer.serialize(app.to_ir())
    (marimo/_session/notebook/file_manager.py:423-489, 202-269).
    """
    from marimo._server.models.models import SaveNotebookRequest
    from marimo._session.notebook.file_manager import AppFileManager

    manager = AppFileManager(path)
    cells = list(manager.app.cell_manager.cell_data())
    request = SaveNotebookRequest(
        cell_ids=[c.cell_id for c in cells], codes=[c.code for c in cells],
        names=[c.name for c in cells], configs=[c.config for c in cells],
        filename=str(path), persist=False)
    return manager.save(request)


@pytest.mark.parametrize("which", ["generated", "workbench"])
def test_round_trip_parser_and_codegen_reproduce_bytes(study, which):
    from marimo._convert.converters import MarimoConvert

    path = _generated(study) if which == "generated" else _workbench(study)
    source = path.read_text(encoding="utf-8")
    assert MarimoConvert.from_py(source).to_py() == source
    assert _editor_reserialize(path) == source


def test_round_trip_normalizes_hand_written_sources(tmp_path):
    """Finding: hand-written templates are not canonical; Marimo rewrites them."""
    from marimo._convert.converters import MarimoConvert

    hand = (
        "import marimo\n"
        "app = marimo.App()\n\n"
        "@app.cell\n"
        "def _():\n"
        "    import marimo as mo\n"
        "    return mo,\n\n"
        "@app.cell\n"
        "def notes(mo):\n"
        "    mo.md('## Your notes\\n\\nWrite here.')\n"
        "    return\n"
    )
    canonical = MarimoConvert.from_py(hand).to_py()
    assert canonical != hand
    assert '__generated_with = "0.25.1"' in canonical  # version stamp inserted
    assert 'if __name__ == "__main__":' in canonical  # run guard appended
    assert 'mo.md("""' in canonical  # markdown cell re-quoted and dedented
    assert "return (mo,)" in canonical  # returns re-derived from defs
    assert MarimoConvert.from_py(canonical).to_py() == canonical  # fixed point


def test_editor_save_rewrites_whole_file(study, tmp_path):
    """Finding: a save regenerates every byte from cells; text between cells is lost."""
    from marimo._server.models.models import SaveNotebookRequest
    from marimo._session.notebook.file_manager import AppFileManager

    path = tmp_path / "workbench_copy.py"
    original = _workbench(study).read_text(encoding="utf-8")
    marker = "\n\n@app.cell\ndef threshold_slider"
    assert marker in original
    path.write_text(original.replace(marker, "\n\n# stray user comment" + marker, 1), encoding="utf-8")
    manager = AppFileManager(path)
    cells = list(manager.app.cell_manager.cell_data())
    codes = [c.code.replace("Write your observations here.", "Write here. Saved by editor.")
             for c in cells]
    manager.save(SaveNotebookRequest(
        cell_ids=[c.cell_id for c in cells], codes=codes, names=[c.name for c in cells],
        configs=[c.config for c in cells], filename=str(path)))
    saved = path.read_text(encoding="utf-8")
    assert "Saved by editor." in saved
    assert "# stray user comment" not in saved
    assert saved.startswith("# Hypotrail workbench")  # header comments are kept


def test_generated_with_stamp_is_the_only_version_coupling(study, proto):
    """A newer Marimo would rewrite ``__generated_with`` on save; that is not a user edit."""
    from marimo._utils.generated_with import contents_differ_excluding_generated_with

    notebook = _generated(study)
    text = notebook.read_text(encoding="utf-8")
    bumped = text.replace('__generated_with = "0.25.1"', '__generated_with = "0.99.0"')
    assert bumped != text
    assert not contents_differ_excluding_generated_with(text, bumped)
    notebook.write_text(bumped, encoding="utf-8")
    assert proto.render.render(study)["preserved"] is None


# ---------------------------------------- 7. ``marimo export html`` as the HTML source

@pytest.fixture
def exported(study, tmp_path):
    first, first_seconds = _export(_generated(study), tmp_path / "a.html")
    second, second_seconds = _export(_generated(study), tmp_path / "b.html")
    assert first.returncode == 0 and second.returncode == 0, first.stderr + second.stderr
    return {"a": tmp_path / "a.html", "b": tmp_path / "b.html",
            "seconds": (first_seconds, second_seconds)}


@pytest.mark.xfail(strict=True, reason="finding: export html loads its frontend (JS, CSS, fonts) "
                   "from cdn.jsdelivr.net (marimo/_templates.py:409-411); unreadable offline")
def test_export_criterion_offline(exported):
    assert _parse(exported["a"].read_text(encoding="utf-8")).external == []


def test_export_criterion_offline_evidence(exported):
    external = _parse(exported["a"].read_text(encoding="utf-8")).external
    assert external and all("cdn.jsdelivr.net/npm/@marimo-team/frontend@0.25.1" in e for e in external)
    print(f"external references: {len(external)}")


def test_export_criterion_deterministic(exported):
    assert exported["a"].read_bytes() == exported["b"].read_bytes()


@pytest.mark.xfail(strict=True, reason="finding: cell outputs are JSON-escaped inside a <script> "
                   "payload and rendered by CDN JavaScript; no <data data-result-id> in the static DOM")
def test_export_criterion_data_result_id_in_dom(exported):
    ids = _parse(exported["a"].read_text(encoding="utf-8")).data_result_ids
    assert {"r_split_0001", "r_target_rate_0002"} <= set(ids)


def test_export_criterion_data_result_id_survives_as_escaped_payload(exported):
    raw = exported["a"].read_text(encoding="utf-8")
    assert '\\u003Cdata data-result-id=\\"r_target_rate_0002\\"' in raw
    assert "<data data-result-id" not in raw


def test_export_criterion_duration_and_size(exported, record_property):
    size = exported["a"].stat().st_size
    record_property("export_bytes", size)
    record_property("export_seconds", [round(s, 2) for s in exported["seconds"]])
    print(f"export html: {size} bytes, {exported['seconds'][0]:.2f}s and {exported['seconds'][1]:.2f}s")
    assert size > 0


def test_export_criterion_no_code_option(study, tmp_path):
    proc, _ = _export(_generated(study), tmp_path / "nocode.html", "--no-include-code")
    assert proc.returncode == 0, proc.stderr
    raw = (tmp_path / "nocode.html").read_text(encoding="utf-8")
    for token in ("read.numbers_html", "RESULT_IDS", "HYPOTRAIL_READ_ONLY"):
        assert token not in raw
    assert "r_target_rate_0002" in raw  # outputs remain


def _failing_copy(study: Path) -> Path:
    source = _generated(study).read_text(encoding="utf-8")
    failing = source.replace("    view = read.open(STUDY_DIR)\n",
                             "    view = read.open(STUDY_DIR)\n    raise RuntimeError('spike-render-fault')\n", 1)
    assert failing != source
    path = study / "notebooks" / "failing.py"
    path.write_text(failing, encoding="utf-8")
    return path


def test_export_criterion_failure_is_detectable(study, tmp_path):
    proc, _ = _export(_failing_copy(study), tmp_path / "failing.html")
    assert proc.returncode != 0
    assert "some cells failed to execute" in proc.stderr


@pytest.mark.xfail(strict=True, reason="finding: on a failing cell, export html still writes the "
                   "error page over the previous file, non-atomically and without prompting when "
                   "stdout is not a TTY (marimo/_cli/export/commands.py:163-185, marimo/_cli/utils.py:18-33)")
def test_export_criterion_failure_keeps_previous_output(study, tmp_path):
    output = tmp_path / "study.html"
    good, _ = _export(_generated(study), output)
    assert good.returncode == 0
    previous = output.read_bytes()
    _run([sys.executable, "-m", "marimo", "export", "html", "--no-sandbox",
          str(_failing_copy(study)), "-o", str(output)], cwd=study)
    assert output.read_bytes() == previous


@pytest.mark.xfail(strict=True, reason="finding: export html persists a session snapshot to "
                   "notebooks/__marimo__/session/<name>.json (marimo/_export/requests.py:119, "
                   "marimo/_export/_session_cache.py:65-90)")
def test_export_writes_nothing_into_the_study(study, tmp_path):
    before = sorted(p.relative_to(study) for p in study.rglob("*"))
    proc, _ = _export(_generated(study), tmp_path / "x.html")
    assert proc.returncode == 0
    assert sorted(p.relative_to(study) for p in study.rglob("*")) == before


# ------------------------------------------------- configuration facts used by the ADR

def test_runtime_config_auto_instantiate_docstring_disagrees_with_default():
    from marimo._config.config import DEFAULT_CONFIG, RuntimeConfig

    assert DEFAULT_CONFIG["runtime"]["auto_instantiate"] is False
    assert "The default is `True`." in RuntimeConfig.__doc__.split("auto_reload")[0]
    assert DEFAULT_CONFIG["runtime"]["on_cell_change"] == "autorun"
    assert DEFAULT_CONFIG["save"]["autosave"] == "after_delay"
