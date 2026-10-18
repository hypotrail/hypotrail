# ADR 0001: Generated Marimo notebooks and a separate HTML renderer

- Status: accepted (Phase 0 spike WP0.6, gate for Phases 2 and 3)
- Date: 18 October 2026
- Marimo version examined: 0.25.1 (pinned in `framework/requirements-pilot.txt`)
- Evidence: `framework/tests/spikes/test_marimo_preservation.py` with the throwaway prototype in `framework/tests/spikes/prototype/`

## Context

The v0.1 plan (`docs/plans/V0.1-IMPLEMENTATION-PLAN.md`, WP0.6 and §6) needs two deliverables built from the same read view of `.hypotrail` state:

- `notebooks/study_generated.py`, regenerated on every render. It is read-only, numbers are frozen by `RESULT_IDS`, and user edits are preserved before regeneration.
- `notebooks/workbench.py`, created once and never overwritten. It has a slider labelled "Experiment, not adopted" and a "Your notes" cell. A template change produces `workbench.candidate.py`.

`docs/specs/JUNIOR-WORKFLOW.md` adds two constraints. Opening the notebook must not download anything, train anything, or write decisions. Regeneration must never silently destroy user edits.

The open questions were:

- whether Marimo can run these files headless;
- whether its editor rewrites the files we generate, which would produce false "user edits";
- whether `marimo export html` could be the HTML report instead of a separate renderer.

docs.marimo.io was not used. Every claim below cites the installed package (`site-packages/marimo/…`, file:line) or a test in the spike.

## How to run the spike

```sh
HYPOTRAIL_RUN_SPIKES=1 PYTHONPATH=framework <venv>/bin/python -m pytest -q framework/tests/spikes -p no:cacheprovider
```

Without `HYPOTRAIL_RUN_SPIKES=1`, every test is skipped. Studies live in `tmp_path`, with fake state, registry, and manifest JSON from `prototype/fixture.py`. Notebook execution always happens in a subprocess. Recorded result: **28 passed, 4 xfailed** (about 44 s). The 5 targeted suites from `CONTRIBUTING.md` still pass (69 tests).

Each of the four `xfail(strict=True)` tests asserts a property Hypotrail needs and that Marimo 0.25.1 lacks. They are negative findings, not tolerated failures. Because they are strict, a Marimo change that makes one pass turns it into an XPASS, which fails the run and forces this ADR to be revisited. `--runxfail` confirms that each one fails on the asserted property, not on an incidental error.

## Measured findings

### 1. Headless execution: passes

- The file `generate_filecontents` writes ends with `if __name__ == "__main__": app.run()` (`marimo/_ast/codegen.py:604-606`). `python study_generated.py` exits with code 0 in about 0.9 s (`test_generated_notebook_runs_as_script`).
- `App.run()` returns `(outputs, defs)` (`marimo/_ast/app.py:662-666`). The spike imports the module, calls `app.run()`, and gets `defs["view"].revision == 7` from the fixture state, 6 outputs, and no `sklearn` in `sys.modules` (`test_generated_notebook_app_run_returns_view`).
- `python -m marimo export html --no-sandbox` runs both notebooks with exit code 0 (`test_notebooks_export_html`). `--no-sandbox` is passed explicitly because the CLI otherwise may ask about sandboxing (`marimo/_cli/export/commands.py:301-303`).
- The setup cell finds the study with `Path(__file__).resolve().parents[1]`. This works under `python nb.py`, `app.run()`, and `export html`; the runner patches `__file__` (`marimo/_runtime/runtime.py:374-375`).

### 2. No fit and no state write: passes

- The AST scan of both notebooks and of the prototype `read`, `guard`, and `policy` modules finds:
  - no `sklearn` or `mlkit` import;
  - no `.fit(`, `.fit_transform(`, `.partial_fit(`, or `.fit_predict(` call.

  A positive control checks that the scanner itself catches these (`test_ast_scan_no_fit_no_sklearn`, `test_ast_scan_detects_a_fit`). The fit source shown in the notebook comes from registry data at run time and never appears as code.
- The setup cell sets `os.environ["HYPOTRAIL_READ_ONLY"] = "1"` exactly once (`test_generated_setup_sets_read_only`).
- The guard is a Python audit hook (`prototype/guard.py`), installed by `read.open` when the variable is set. It refuses the following inside `<study>/.hypotrail`:
  - any write-mode `open`;
  - `os.rename` and `os.replace`;
  - `os.remove`, `os.rmdir`, `os.truncate`, `shutil.rmtree`, and `os.mkdir`.

  A user cell that tries `state.json.write_text(...)` and `os.replace(artifacts.json, …)` gets `ReadOnlyError` both times. The renderer also refuses to run in a read-only process (`test_read_only_guard_refuses_writes_from_an_edited_cell`, `test_render_refuses_in_read_only_process`).
- The sha256 of every file under `.hypotrail/` (state, three registry entries, manifest) is identical before and after these runs, for both notebooks (`test_execution_leaves_state_registry_manifest_unchanged`):
  - `python nb.py`;
  - `marimo export html`.
- Limit: an audit hook is a safeguard, not a sandbox. Code that uses `ctypes` or spawns a subprocess can bypass it. The guarantee that matters remains structural: the notebook imports no writer and no activity.

### 3. User edits are preserved: passes

- A user edit is any byte difference from the hash recorded in the manifest. The edit in the test has CRLF, a non-ASCII character, and a trailing comment. It is copied byte for byte to `study_generated.user-edits-<rev>.py`, where `<rev>` is the revision the edited file was generated at. The file is then regenerated at the new revision, and the manifest lists the copy in `user_edits_preserved` (`test_user_edit_is_preserved_byte_for_byte_then_regenerated`).
- Copies are created with `O_EXCL`. A second edit at the same revision becomes `-2.py` and never overwrites the first. An unedited render preserves nothing. Generation is deterministic (`test_unedited_render_preserves_nothing_and_repeat_edits_never_overwrite`, `test_generator_is_deterministic`).
- The edit check ignores exactly one line, `__generated_with = "…"`. A newer Marimo rewrites that version stamp on save, and Marimo ignores it for the same reason in its own reload check (`marimo/_utils/generated_with.py:6,17-21`). Every other byte counts (`test_generated_with_stamp_is_the_only_version_coupling`).

### 4. The workbench stays intact: passes

- The workbench is created once with `O_EXCL`. The test edits the user's notes and renders at revisions 8 and 9: the file stays byte-identical, and no candidate appears (`test_workbench_is_byte_identical_across_regenerations`).
- With template version 2:
  - `workbench.py` is untouched;
  - `workbench.candidate.py` is written;
  - the manifest records `template_version: 1` together with a `candidate` at version 2 (`test_workbench_template_bump_writes_candidate_only`).
- The workbench does not import the generated notebook and runs headless (`test_workbench_runs_and_does_not_import_generated_notebook`).

### 5. Round trip through Marimo's own parser and codegen: passes, with a condition

- Parser: `marimo._ast.parse.parse_notebook` (`marimo/_ast/parse.py:1077`), reached through `MarimoConvert.from_py` (`marimo/_convert/converters.py:56-67`).
- Codegen: `generate_filecontents` / `generate_filecontents_from_ir` (`marimo/_ast/codegen.py:509-610`).
- The editor's save path is:
  1. `AppFileManager.save` (`marimo/_session/notebook/file_manager.py:423-489`);
  2. `_save_file` (`:202-269`);
  3. `PythonNotebookSerializer.serialize(app.to_ir())` (`marimo/_session/notebook/serializer.py:55-66`, `marimo/_ast/app.py:1116-1133`).
- The prototype generates both files **with** `generate_filecontents`. Parsing and re-serialising them reproduces identical bytes, both through `MarimoConvert` and through the real `AppFileManager.save(..., persist=False)` path (`test_round_trip_parser_and_codegen_reproduce_bytes`). An unmodified editor save is therefore a no-op.
- The condition: a hand-written template is **not** canonical. Marimo rewrites it in four ways, and the result is then a fixed point (`test_round_trip_normalizes_hand_written_sources`):
  - it inserts `__generated_with`;
  - it appends the `__main__` guard;
  - it re-quotes and dedents `mo.md('…')` cells as `mo.md("""…""")`;
  - it re-derives `return (mo,)`.

  The prototype shows the same normalisation of its own `mo.md('…')` input for the pending step. A hand-written template would therefore turn every editor save into a false "user edit".
- `marimo edit` rewrites the whole file on save, not just the edited cell: it regenerates every byte from the cell list (`file_manager.py:483-488`). A comment placed between two cells disappears on save. The header comment block survives, because `_save_file` re-reads it with `extract_header` (`file_manager.py:228-235`; `test_editor_save_rewrites_whole_file`).
- Fallback if Marimo's internal codegen becomes unusable: write a template, normalise it once through `MarimoConvert.from_py(text).to_py()`, check that the result is a fixed point, and record the hash of the normalised bytes. The `__generated_with` exclusion stays as it is. Both APIs are underscore-internal, so the dependency stays pinned and the round-trip tests remain permanent (WP3.2).

### 6. Manual editor check: not headless, procedure recorded

This point is not automated. Procedure for the person who performs it:

1. Create a temporary study. Run `prototype.fixture.make_study` and then `prototype.render_notebook.render`, with `PYTHONPATH` set to `framework/tests/spikes`, in a directory outside the repository. Record `sha256sum` for `.hypotrail/*`, `.hypotrail/registry/*`, and both notebooks.
2. `marimo edit notebooks/workbench.py` with the same `PYTHONPATH`. Expect no cell to run on open: `auto_instantiate` defaults to `False` in edit mode (see below).
3. Run all cells. Move the slider: only the experiment row changes, and the adopted row matches the state. Edit the "Your notes" cell, save, and close.
4. `diff` against the recorded workbench: only the notes cell changes. Re-run the hashes: `.hypotrail/*` is unchanged. A `notebooks/__marimo__/` directory may appear; it is ignored by git.
5. Open `study_generated.py` in the editor, run it, save without editing, close. Its sha256 must be unchanged; any difference other than `__generated_with` is a finding. Then make a real edit, save, run `render`, and check that `study_generated.user-edits-<rev>.py` holds the edit.
6. Record the date, the Marimo version, the browser, and the diffs in the WP3.2 pull request.

Configuration facts that bear on this check (`marimo/_config/config.py`; `test_runtime_config_auto_instantiate_docstring_disagrees_with_default`):

- `auto_instantiate`: the docstring says "The default is `True`" (`:137-140`), but `DEFAULT_CONFIG` sets `False` (`:805`). The default is what is applied, through `ws_connection_validator.py:88` and `ws_session_connector.py:228-235`. So opening a notebook in `marimo edit` runs nothing until the user asks. `marimo run` and `export html` always instantiate (`ws_session_connector.py:233-235`, `marimo/_export/file.py:704`).
- `on_cell_change` defaults to `"autorun"` (`:146-148`, `:808`): editing a cell re-runs its descendants. That is acceptable, because the cells are read-only and the slider calls only the pure `policy.evaluate`.
- `save.autosave` defaults to `"after_delay"` with 1000 ms (`:821-822`). `marimo edit --watch` defaults to off (`marimo/_cli/cli.py:374-379`). Consequence: if `study_generated.py` is open in an editor during a `render`, the editor keeps its old copy and can write it back on the next autosave. Nothing is lost, because the next render preserves that copy as `user-edits` and regenerates. It is noisy, though, and the instructions should present `study_generated.py` as a document to read or `marimo run`, and the workbench as the place to edit.

### 7. `marimo export html` as the HTML source: fails 3 criteria

| Criterion | Result | Evidence |
|---|---|---|
| Offline readability | **Fails** | The page loads 107 resources (`index-*.js`, CSS, fonts, icons) from `https://cdn.jsdelivr.net/npm/@marimo-team/frontend@0.25.1/dist` (`marimo/_templates.py:409-411`, `:430-431`). `export html` exposes no `asset_url` option (`marimo/_cli/export/commands.py:291-330`). The local `_static/assets` directory holds 471 files (27 MB) and is not inlined. Without network the page shows nothing, which also contradicts "opening must not trigger downloads" (`test_export_criterion_offline`, xfail; `test_export_criterion_offline_evidence`). |
| Determinism | Passes | Two exports of the same notebook are byte-identical (`test_export_criterion_deterministic`). |
| `data-result-id` on numbers | **Fails** | The `<data data-result-id>` elements survive only as JSON-escaped text (`<data data-result-id=\"…\"`) inside a `<script>` payload, which the CDN JavaScript renders. There are none in the static DOM, so `check` and an offline Playwright test cannot rely on them (`test_export_criterion_data_result_id_in_dom`, xfail; `test_export_criterion_data_result_id_survives_as_escaped_payload`). |
| Duration and size | Recorded | 36,726 bytes (excluding the CDN assets); 1.7 to 1.8 s per export of a 7-cell notebook, because each export starts a kernel and runs every cell (`test_export_criterion_duration_and_size`). For comparison, running the notebook headless takes about 0.9 s. No threshold is set. |
| No-code option | Passes | `--no-include-code` removes cell code (`read.numbers_html`, `RESULT_IDS`, and `HYPOTRAIL_READ_ONLY` are absent) and keeps outputs (`test_export_criterion_no_code_option`). |
| Failure detectable | Passes | A raising cell gives exit code 1 and "Export was successful, but some cells failed to execute." (`marimo/_cli/export/commands.py:181-185`; `test_export_criterion_failure_is_detectable`). |
| Failure isolation (previous file kept) | **Fails** | The error page is still written over the previous file. `output.write_bytes` (`commands.py:163-167`) runs before the error check, the write is not atomic, and when stdout is not a TTY the overwrite prompt is skipped even without `-f` (`marimo/_cli/utils.py:18-33`; `test_export_criterion_failure_keeps_previous_output`, xfail). A wrapper could export to a temporary file, but criteria 1 and 3 would still fail. |
| Side effects | Finding | `export html` writes `notebooks/__marimo__/session/<name>.json` into the study (`persist_session=True` by default, `marimo/_export/requests.py:119`; `marimo/_export/file.py:717-733`; `marimo/_export/_session_cache.py:65-90`). `.hypotrail` is untouched (`test_export_writes_nothing_into_the_study`, xfail). `**/__marimo__/` is already git-ignored. |

## Decision

1. **Notebooks.** Adopt the prototype's approach for WP3.2:
   - generate `study_generated.py` and `workbench.py` with Marimo's own codegen, pinned to `marimo==0.25.1`;
   - detect edits by sha256 with only the `__generated_with` line neutralised;
   - preserve edits byte for byte as `study_generated.user-edits-<rev>.py`, created with `O_EXCL`;
   - create the workbench once and never write it again;
   - write `workbench.candidate.py` on a template bump;
   - set `HYPOTRAIL_READ_ONLY=1` and install the read guard in the setup cell.

   Points 1 to 5 hold. Make the spike tests permanent, keeping the strict xfails as upgrade alarms.
2. **HTML.** Use a **separate, deterministic, stdlib-only HTML renderer** fed by the same read view (`view.build`). `marimo export html` fails offline readability, `data-result-id` in the DOM, and failure isolation, so it is **not** the report source. It is not part of `render`. A user may run it by hand as a convenience, but it is not a deliverable and `check` does not read it.
3. **Single view.** The notebook generator and the HTML renderer both consume `read.build(study)`. The notebook never recomputes a number: it shows `output.values` by `result_id`, frozen at generation.

## Consequences

- Phase 3 owns a small HTML renderer, which needs:
  - atomic write;
  - the previous file kept with a stale banner on failure;
  - `<data data-result-id>` produced by `num(rid, path, fmt)`;
  - no external URLs, checked by an offline Playwright test.

  Phase 3 also owns the notebook generator. Neither one imports pandas or scikit-learn.
- Hypotrail depends on underscore-internal Marimo APIs: `marimo._ast.codegen.generate_filecontents`, `marimo._ast.app_config._AppConfig`, and `marimo._ast.cell.CellConfig`. The round-trip tests are the contract: any Marimo upgrade must pass them before the pin moves. If an upgrade breaks them, use the normalisation fallback in finding 5.
- The editor rewrites whole files, and autosave is on by default. `render` must therefore re-check the edit hash immediately before `os.replace`. The prototype checks once, then writes; that leaves a small window the real implementation must close. Concurrent editor writes remain possible, and they are absorbed by preservation rather than prevented. `writer.lock` cannot coordinate with the Marimo editor.
- The read-only guard is defence in depth. The structural guarantee is that the notebooks import only `read` (and the pure `policy`) and never a writer or an activity. The AST scan enforces this.
- `marimo edit` and `export html` may create `notebooks/__marimo__/`. The manifest and `check` must ignore it, and it is already git-ignored.
- The prototype under `framework/tests/spikes/prototype/` is throwaway. The real `read.py` (WP1.3) and notebook renderer (WP3.2) are written in `framework/mlkit/study/` against the frozen contract and do not import it.
- Not verified here: Marimo's behaviour in a real browser session (point 6), Windows paths, and the performance of a notebook over real Bank predictions (1,357 rows) rather than the 8-row fixture.
