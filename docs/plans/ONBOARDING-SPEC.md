# Onboarding: from "I have a dataset" to a running study

Status: owner-approved plan, 1 November 2026 ("ok implémente"), from proposal v2 and two fresh reviews (product and UX; method and technique). This file is the specification for the implementation lots below. Explicit owner remarks take precedence.

## 1. Goal

A data scientist or a junior arrives with one data file and, optionally, a brief (PDF, Word or Markdown), a short free-text context, or nothing. In one install and one command they get a study whose final test was set aside properly, then run it with the existing engine, chat agent, panel and report. It must work on **Windows natively**, macOS, Linux and Codespaces, without Node.

## 2. Principles

1. **Two phases split by sealing.** Before sealing: structural inspection only (types, counts, missing values, cardinality, a few example values of predictors; for the target, its label set or range and its missing count). Never the target crossed with predictors, never a model. After sealing: the existing study.
2. **Six questions before sealing, the rest after.** Variable descriptions and availability stay study decisions (they already are). The six questions:
   1. Have you already explored this file? (asked first; becomes `prior_exposure`)
   2. What is the target (and the positive label for a binary target)?
   3. What does one row represent?
   4. When is the prediction made, and is the use about the future? (clocks)
   5. Do entities recur (customer, vehicle, patient)? (groups)
   6. Do you accept this final test? Shown in words and counts only ("the latest 20 %, 1,840 rows, March to June 2025").
3. **The agent proposes, the human confirms in their own words.** Inputs at three levels, same mechanics: a brief file (answers proposed with page citations), a free-text context (answers inferred from it), or nothing (answers inferred from column names and the structural profile, with suspicious columns flagged: a date after the outcome, an id that encodes time, a near-copy of the target). Every inferred or extracted answer is marked "proposed, to confirm" until confirmed; a brief or a context is a `scenario_assumption` source, never a fact.
4. **The final test is deduced, not chosen.** The case declares facts (`analysis_contract`: intended use, clocks, dependencies); the engine deduces the method with the existing `review-v1` planner. No new `holdout` key, no user seed. Rules, in order: future use with documented clocks → temporal (with delayed-label purge); recurring entities → grouped (grouped_temporal with a clock); assumed time dependence → temporal; otherwise stratified (binary) or quantile-stratified (regression); "unknown" → stratified with capped claims (`permitted_claims` without future performance). Fraction 0.2 by default; the effective fraction is reported and refused outside [0.10, 0.35]; at least 100 test rows and, for a binary target, 30 minority events in the test (constants, documented), else a reasoned refusal, never a silent fallback.
5. **Feasibility, not preview.** `case check --feasibility` reports counts without the target (rows, period covered, ties, groups) and a pass/fail on the minimums. No per-stratum proportions, so a split cannot be shopped for.
6. **Data stay outside the chat workspace.** New studies keep the case and its data in a sibling folder, not inside the opened study folder; the `data/` link (R69) is no longer created for new studies (existing studies untouched). The pre-seal structural inspection is recorded as `prior_exposure` (`observed`) and shown in the report. The hook stays a cooperative aid, not a security boundary.
7. **No shell scripts on the path.** Everything is a `hypotrail` subcommand in Python, with argument lists, `pathlib`, UTF-8 everywhere. User free text is passed by file (`--user-words-file`) as well as by argument.

## 3. Lots

### Lot 0. Portable package and CI (owner: agent P)
- `hypotrail-runtime`: make the wheel installable without a path dependency (vendor the runtime into the `hypotrail` wheel, or build and resolve both from the same Git subdirectory; choose and document). `uv tool install "git+https://github.com/hypotrail/hypotrail#subdirectory=framework"` must work.
- `agent.json` CLI command: an argument list to the installed `hypotrail` executable (or `python -m mlkit.study.cli` with an absolute interpreter), never `env PYTHONPATH=…`; displayed commands use the platform's quoting (PowerShell on Windows).
- Embed what a wheel misses (`uv.lock` for the snapshot, or record its absence explicitly).
- CI: `.github/workflows/ci.yml`, matrix `ubuntu-latest`, `windows-latest`, `macos-latest`, uv, Python 3.13, the study test suite (`framework/tests/study`), `scripts/check_layout.py`, and the panel's `node --test` on Ubuntu only.

### Lot 1. Start and install (owner: agent P)
- `hypotrail setup vscode`: installs the study panel from a VSIX **embedded in the Python package** with `code --install-extension` (find `code`, `code.cmd` on Windows, and the code-server fallback already used for Codespaces). The VSIX is built in pure Python (zip: `extension.vsixmanifest`, `[Content_Types].xml`, `extension/…`) from the panel sources shipped as package data; a test checks parity of the file list with the panel sources. No Node for users.
- `hypotrail doctor`: Python, uv, `code`, Copilot or Claude Code presence (best effort), panel installed, platform (Windows native supported once Lot 4 lands), PowerShell execution policy, long paths, OneDrive folder, proxy and certificates (`HTTPS_PROXY`, `UV_SYSTEM_CERTS`); prints the fix command.
- `hypotrail hook pretool`: the workshop hook moved into the package (argv-based matching derived from `agent.json`, data file names from the case); `scripts/workshop/hooks/pretool.py` delegates to it.
- `hypotrail new NAME …` (see Lot 2 for `--data`): for an existing case, `--case PATH` replaces `scripts/workshop/new-mpg-study.sh` (panel settings, hook, `--brief`, `--automation`, `--open`). The bash scripts become thin wrappers or are documented as legacy.
- Codespaces template folder `templates/study-template/` (devcontainer that installs the tool and the panel; a place for the user's data). Publishing it as its own repository is the owner's step.

### Lot 2. Preparation (owner: agent S)
- `hypotrail new NAME --data FILE [--brief FILE] [--context TEXT|--context-file FILE] [--lang fr|en]`: creates `NAME.case/` next to the study folder (data copied there, sha256, structural profile, `case.draft.yaml` with `todo:` entries), and the study folder `NAME/` in a **preparing** state with the agent files. No partition yet. Supported inputs: CSV first (separator, encoding detection limited to UTF-8 strict with a clear refusal otherwise); multi-line records refused with a message.
- Structural profile (`hypotrail case profile`): all rows, structural only (§2.1); recorded as the `prior_exposure` statement.
- Brief: reuse `brief import` for PDF; add `.docx` and `.md`/`.txt`; the free-text context is stored as a brief of kind `context`.
- The six questions: a CLI to record each answer with the user's words (`hypotrail prepare answer QUESTION --value-json … --user-words(-file) …`), and `hypotrail prepare status` (what is answered, proposed, missing). Answers are translated into `case.yaml` (target, task, `structure`, `order`/`analysis_contract` facts, `prior_exposure`) with sources quoting the user's words.
- `hypotrail case check --feasibility` (§2.5).
- `hypotrail seal`: requires the six answers and a passing feasibility check, writes `case.yaml`, runs `init` with `review-v1` when the contract supports it, records the deduction ("temporal on X because the use is about the future") as a protocol record, and the report gains a chapter-0 paragraph explaining how the final test was set aside.
- Agent instructions: a preparation section or on-demand skill (the always-loaded agent text is near its word cap): the three input levels, propose with sources, flag suspicious columns, one question at a time, never read the data file directly, then `seal`, then the usual study.

### Lot 3. Final-test deduction (owner: agent S)
- §2.4 rules on `analysis_contract`, guards and refusals, ADR 0006 amendment, CASE-CONTRACT and CLI-CONTRACT updates. Date clocks: a `date` clock with an explicit format, or a documented sorted copy (Hotel model); no implicit conversion. Missing target: refusal with the derived-copy option documented (not implemented here unless trivial).

### Lot 4. Windows native (owner: agent W)
- Replace `fcntl.flock` (`study/lock.py`, and other users found by grep) with a cross-platform lock (`msvcrt.locking` on a byte outside the content, or `portalocker` if a dependency is acceptable); re-check orphan lease detection; then lift `require_posix`.
- `os.replace` with bounded retries on `PermissionError` (Windows sharing violations).
- `sys.stdout`/`stderr` reconfigured to UTF-8 in the CLI; explicit `encoding='utf-8'` on every text open.
- Interpreter and executable resolution per OS (`Scripts\python.exe`, `hypotrail.exe`); `launch.py` argv; no `shlex.join` for display on Windows.
- `--user-words-file` on every command that takes `--user-words`.
- Two concurrency tests (two processes contending for the lock; replace while a reader holds the file).

### Lot 5. Validation
- Owner or an outside person: an unseen dataset prepared end to end, timed, on Windows native and in Codespaces.

## 4. Non-goals
No web UI or server; no panel write outside its whitelist; no automatic decision about variable availability; PyPI publication is the owner's step (reserve the names `hypotrail` and `hypotrail-runtime`).

## 5. Ownership for parallel work
- Agent P: `framework/pyproject.toml`, packaging, `framework/mlkit/study/agent_files.py` (CLI command only), `launch.py` (command display only), new modules `cmd_setup.py`, `cmd_doctor.py`, `cmd_hook.py`, `cmd_new.py` (existing-case path), `.github/workflows/`, `templates/study-template/`, `scripts/workshop/`, docs/workshop.
- Agent S: new modules `case_draft.py`, `cmd_case.py`, `cmd_prepare.py`, `cmd_seal.py`, partition deduction in `partition.py`, `case.py` validation for new fields, `commands.init` changes needed for sealing, agent instruction templates (preparation part), brief formats, report chapter 0, ADR 0006 amendment, CASE-CONTRACT and CLI-CONTRACT. `cmd_new.py` `--data` path is S's: P exposes a function S calls, or S extends the module after P (coordinate through the integrator).
- Agent W: `lock.py`, `store.py` (atomic writes), CLI encoding in `cli.py` (top of `main` only), `--user-words-file` flags, other `fcntl` users, concurrency tests.
- `cli.py` `EXTENSIONS`/`EXTENSION_HELP`: each agent adds its own entries; the integrator merges.
