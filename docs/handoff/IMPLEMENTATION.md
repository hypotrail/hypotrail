# Implementation handoff (v0.1)

Status: **v0.1 implemented** on branch `claude/hypotrail-product-review-yrstzb`, 18 October 2026. It is a vertical slice of the [junior workflow](../specs/JUNIOR-WORKFLOW.md) on Bank Marketing, guided by **Claude Code**, not GitHub Copilot. Evidence per behaviour: [V0.1-CHECKLIST.md](../acceptance/V0.1-CHECKLIST.md). Decisions taken during implementation, and open questions for the owner: [V0.1-DECISIONS.md](../plans/V0.1-DECISIONS.md). The plan: [V0.1-IMPLEMENTATION-PLAN.md](../plans/V0.1-IMPLEMENTATION-PLAN.md).

v0.1 delivers the repositioned promise on one workflow: *do your ML study with an agent; Hypotrail guarantees that numbers, partitions, and decisions are traceable, and says what is not yet defensible.*

## What a user can do now

On **Bank Marketing** (`use-cases/bank-marketing/case.yaml`) and on the **synthetic planted-trap case** (`framework/tests/fixtures/synthetic/make_case.py`, a fictitious library network), a user can:

1. create a study in a folder outside the repository (`hypotrail init`), which installs the study agent's instructions (`CLAUDE.md`, a skill, a resume command) and starts at revision 1 with every decision open; the case's facts keep their epistemic status (`documented_fact`, `scenario_assumption`, `observed`, `unknown`), and no tutorial choice is imported as a confirmation;
2. open that folder with Claude Code and follow the plan in chat, in seven steps and three pauses:
   - pause 1: the prediction moment, then each feature's availability (`duration` is documented as not available; `day`, `month`, `contact`, `campaign` describe the last contact and must be discussed);
   - pause 2: a stratified random split, before any look at the outcome;
   - then, without further questions: training-partition EDA (target rate, special values such as `pdays=-1` / `poutcome=unknown`, rate by a column), a constant baseline and a logistic model with persisted validation predictions, and policy evaluations (`threshold:T`, `capacity:K`) with paired bootstrap intervals and pro-rata ties;
   - pause 3: the policy adoption, then a proportionate conclusion (`adopt_policy`, `keep_baseline`, or `inconclusive`);
3. confirm each decision in their own words (copied verbatim), or delegate it explicitly ("use your recommended default"), which is recorded as a delegation and listed as not yet defensible; bare "ok", "keep that", refusals and unrelated replies never confirm;
4. change a capacity or threshold without refitting: the stored predictions are reused, and the adopted rule is always re-evaluated;
5. resume in a new chat from the recorded state (`status --summary`), with a five-line recap;
6. read one evolving offline HTML report (`reports/study.html`), where every number is a `<data data-result-id>` citation and a "What is not yet defensible" section lists the limits; read a generated read-only Marimo notebook (`notebooks/study_generated.py`), whose user edits are preserved as a copy before regeneration; experiment in `notebooks/workbench.py` (a policy slider labelled "Experiment, not adopted"; never overwritten, never recorded);
7. check a draft message for untraceable numbers and causal or forecast wording (`hypotrail check --text -`), including common numbers written in words (post-v0.1, F3).

The engine guarantees, with tests: revisions and idempotent requests (stale requests refused with the diff, replays without effect), exposure tracking by row key (kept after a split change), invalidation per the plan's dependency table (a replaced result makes its descendants stale; changed code or sources are flagged), executions with leases (an interrupted run has an unknown outcome, is never restarted automatically, and its late result is not promoted), and a failed render that keeps the previous report marked stale.

## Commands

```sh
uv sync --project framework --group dev
uv run --project framework hypotrail init --case use-cases/bank-marketing/case.yaml --study /path/outside/the/repository/bank-study
cd /path/outside/the/repository/bank-study && claude          # then talk to the agent
```

The agent uses the CLI, recorded in `.hypotrail/agent.json`: `status [--summary|--json]`, `plan`, `decide propose|confirm|withdraw|note`, `run <activity>`, `run --acknowledge-interruption`, `preview policy`, `check`, `render`; and, for the facilitator of an observed session, the read-only `session-report`. The full contract, with exit codes (0, 2 refusal, 3 stale or failed deliverable, 4 unknown outcome) and every schema, is [CLI-CONTRACT.md](../specs/CLI-CONTRACT.md); the case format is [CASE-CONTRACT.md](../specs/CASE-CONTRACT.md).

For the synthetic case:

```sh
uv run --project framework python framework/tests/fixtures/synthetic/make_case.py /path/outside/the/repository/synthetic-case
uv run --project framework hypotrail init --case /path/outside/the/repository/synthetic-case/case.yaml --study /path/outside/the/repository/synthetic-study
```

Keep the study **outside the repository**: Claude Code loads `CLAUDE.md` and `AGENTS.md` from parent folders, so a study inside the repository would also receive the repository's development instructions.

## What is excluded from v0.1

Refused explicitly (`unsupported_capability`, with the capability named), never handled silently:

- a time column of type date or decimal (`temporal split on a date or non-integer time column (v0.2)`), duplicate records, a held-out test partition, models other than the constant baseline, logistic regression, the training-mean baseline, and linear regression (a random forest is "not supported in v0.1");
- a grouped split: a declared group column is accepted, but the capability `grouped split (v0.2)` is named and every split reports the group values both partitions share (`grouped_split_unsupported`);
- a missing target value, refused at `init` for both tasks (`missing target values (v0.2)`); a stratified split with fewer than two rows of a class (`stratified split with fewer than two rows of each class`);
- values that would silently change meaning, refused at `init` with `invalid_case`: a cell of a numeric variable that is not a number and not declared in `na_values`, and a binary target label other than the declared labels;
- a changed dataset or case file (`dataset_changed`, `sources_changed`): start a new study.

Not built, by design: the old webview companion (paused; [ADR 0002](../decisions/0002-companion-as-cli-client.md) makes any new one a client of this CLI; the flagged study panel below is that client), an application server, MCP integration, multi-agent orchestration, decision controls in the HTML.

## Known limits and remaining defects

Platform and packaging:

- **POSIX only** (Linux, macOS, WSL): the engine uses `fcntl.flock`; native Windows is refused (`platform_unsupported`).
- **Editable install only**: notebook and template resources are not packaged for a non-editable wheel.
- **Absolute paths**: `init` records the absolute CLI command and study path; moving the study or the checkout needs a new study.
- **Marimo internal API**: notebooks are generated with Marimo's internal codegen, pinned to `marimo==0.25.1`; any upgrade must rerun the spike (`HYPOTRAIL_RUN_SPIKES=1`, [ADR 0001](../decisions/0001-notebook-and-html.md)), whose four strict `xfail` tests document Marimo limitations.
- **Float time columns** are still misread by `pd.to_datetime` in the legacy `classical.split`; only integer years are refused.

Evaluation:

- **GitHub Copilot is untested.** Its instruction files are generated from the same templates, with a header saying so. All agentic evidence is "Claude Code acceptance" on Opus (`claude-opus-5-5`) and does not count as Copilot acceptance.
- **No human junior has used v0.1.** The agentic runs measure an agent's behaviour against the instructions, with simulated juniors, not a junior's understanding.
- **One run per condition.** Each scenario ran once per round; a pass is weak evidence, a failure a counterexample.
- The scripted persona never confirms a policy or a conclusion, so those confirmations are exercised only by the answering persona (one Bank run, rerun round) and by the simulated tests.

Remaining defects from the acceptance reports (Claude Code, not fixed):

- **F1 is fixed in the engine and the instructions, but not re-run agentically**: the S9 regression of the final check (a new chat called a killed run "in progress") is covered by `test_status_liveness.py`, not by a new agent run.
- **F3 (T9, hallucinated number)**: T9 failed in 2 of 3 final E1 runs. Post-v0.1, `check` reads common English and French numbers written in words when used quantitatively ("one call in nine", "un sur neuf", "the eleven kept columns", "half of the rows"), and names the withdrawn or superseded proposal whose figure a draft repeats; rule 2 says numbers in words are numbers. Limits: cardinals above 100, vague quantities, and a cardinal without a listed count noun ("nine models") are not read; a ratio such as "one in nine" traces to a registered rate of about 1/9. **Not re-run agentically.**
- **F5**: a repeated three-option menu across turns read as bureaucratic. Post-v0.1, rule 4 and the skill say to offer the menu once, then ask a single question. **Not re-run agentically.**
- **T8 (decision lost between chats)** rated partial in 3 of 3 final runs. Post-v0.1, `status --summary` has a five-line `recap` generated from state (goal, decisions with excluded features, position, next decision quoting an open restatement, one limit), which the resume command and the skill quote. **Not re-run agentically.** **T1b (ambiguous availability)** partial in 1 of 3.
- **Post-v0.1 acceptance defects P1–P7** ([report](../acceptance/runs/claude-code-2026-10-18-post-v0.1.md); fixed in the engine and the instructions, **not re-run agentically**): P1 agreements that repeat a limit ("Yes, and it's not a forecast") are no longer refused as `negative_reply`, and agents are told never to coach the junior's wording; P2 a junior's condition is recorded with `decide note --about` and blocks its decision (`decision_on_hold`) until their words resolve it (`decide note --resolve`), shown in the summary, recap, and report; P3 the recap and deliverable messages hold no revision number, and a regression recap cites the validation MAE with its result id; P4 the "why not use the time column?" answer order; P5 a plan approval covers the work between pauses; P6 read status with `--summary`, never pipe it into python; P7 the report and `check` credit delegated defaults to the assistant (`misattributed_delegation`). The negation rule is still an English and French heuristic. Re-run agentically ([P-fix acceptance](../acceptance/runs/claude-code-2026-10-18-p-fixes.md), Claude Code, not Copilot): P1-P7 and G.12 pass. New defects D1 (a hold added to a confirmed decision leaves it confirmed) and D2 (a confirmed conclusion is not made stale by a later policy adoption) are Medium.
- `delegation_scope` is shown in `status`, the summary, and the text output, but not in the HTML or the notebook.
- `status --json` is large (tens of kilobytes); agents are told to use `status --summary`.
- The HTML report and notebook show execution liveness as `not_checked`; only `status` probes leases.

## Study panel for VS Code (companion v0, behind a flag)

Post-v0.1, on the owner's explicit request: [`clients/vscode-companion/`](../../clients/vscode-companion/README.md), [ADR 0003](../decisions/0003-companion-webview-v0.md), decisions [CW.1–CW.12](../plans/V0.1-DECISIONS.md#companion-v0-study-panel-behind-a-flag-cw). It is off by default: the setting `hypotrail.companion.enabled` or `HYPOTRAIL_COMPANION=1` enables it. With the flag off, the command shows "Companion disabled (feature flag)" and nothing else runs.

- It is a client of the CLI only. It reads `status --summary`, running the argv recorded in `.hypotrail/agent.json` through `execFile`, never a shell, and it refreshes on writes to `.hypotrail/`. It keeps no state and has no server or language-model integration.
- It shows the recap, the plan position, each deliverable's message with buttons to open the report in the browser and the notebook in the editor, the open proposals with their restatement, the open holds, and the top "not yet defensible" items.
- Its one write function is for an open proposal: the junior can confirm it in words they type themselves (`decide confirm ... --channel webview --actor user`, with a new request id and the revision shown), or withdraw it after a modal. Every engine refusal is shown verbatim with a short explanation. It offers no delegation and runs no other mutating command.
- Tests: Node unit tests with a fake `vscode` module; integration tests that drive the real CLI on a temporary synthetic study (a bare "ok" is refused; typed words are recorded with `channel: webview`); and an offline Playwright test of the webview document. See [CONTRIBUTING.md](../../CONTRIBUTING.md).
- **Not run inside a real VS Code**: the VS Code webview host, its theme, the CSP with VS Code's default styles, workspace trust, and the development host are untested. No junior has used it. The engine and the CLI contract are unchanged.

## Observation kit (post-v0.1)

For 2 or 3 sessions with human junior developers, run later by the owner: [the protocol](../research/OBSERVATION-PROTOCOL.md) and its [templates](../research/observation/) (observation grid, comprehension test with answer key, consent form, session log). Instrumentation: `hypotrail session-report --study S [--since REV]` (read-only, content-free timeline, `--format text` for Markdown) and the opt-in session log (`HYPOTRAIL_SESSION_LOG=1` once; [CLI-CONTRACT.md §8.6](../specs/CLI-CONTRACT.md#86-session-report-and-session-log-post-v01-observation-kit)). No session has been run.

## Validation

See [CONTRIBUTING.md](../../CONTRIBUTING.md) for the gate (`check_layout.py` and the targeted pytest scope with the `browser` group), the opt-in Marimo spike (`HYPOTRAIL_RUN_SPIKES=1`), and the opt-in agent acceptance (`HYPOTRAIL_AGENT_ACCEPTANCE=1`, real `claude -p` sessions with model cost). Agent acceptance reports: [first run](../acceptance/runs/claude-code-2026-10-18.md), [rerun](../acceptance/runs/claude-code-2026-10-18-rerun.md), [final check](../acceptance/runs/claude-code-2026-10-18-final.md); E1 steelman: [protocol](../research/E1-STEELMAN.md), [arm A](../research/runs/E1-arm-A-2026-10-18.md), [arm B](../research/runs/E1-arm-B-2026-10-18.md).

## Regression study (M3)

Since M3 the same workflow runs a **regression** study (`task: regression`, a numeric target with a unit), demonstrated on **Auto MPG** and on the regression variant of the synthetic generator, with no dataset-specific code ([CLI contract §10](../specs/CLI-CONTRACT.md)):

- decisions `prediction_time`, `feature_availability`, `split`, `model_choice` (adopt `fit.linear` or keep `fit.baseline`), `conclusion` (`adopt_model`, `keep_baseline`, `inconclusive`); no policy, threshold, or capacity anywhere in a regression study's deliverables, status, or instructions (tested);
- split `ordinal_cutoff` on an integer time column (read as integers, never as dates; the only method when a time column is declared) or `random`; the split reports the groups both partitions share;
- activities `eda.target_summary`, `eda.special_values`, `eda.mean_by:<column>`, `fit.baseline` (training mean), `fit.linear`, `evaluate.regression` (MAE and RMSE in the target unit, paired bootstrap intervals of each and of the difference, residuals, residuals by period);
- the dependency table `REGRESSION_MUTATIONS` (row 13: a new model choice reuses the evaluation and refits nothing).

Measured on Auto MPG (`test_regression_walkthrough.py`, split `model_year >= 79`: 280 training rows, 118 validation rows; 16 car names, 18 validation rows, shared across the split; features cylinders, displacement, horsepower, weight, origin; acceleration excluded as uncertain): MAE 10.10 mpg [9.03, 11.18] for the training mean, 6.31 [5.58, 7.05] for the linear model, difference −3.80 [−4.34, −3.25]; RMSE 11.78 [10.67, 12.82] and 7.51 [6.69, 8.31], difference −4.27 [−4.74, −3.76]; mean residual (bias) +6.19 mpg for the linear model, from +4.04 (1979) to +8.21 (1980): fitted on 1970–1978 without the year, it predicts later cars too low. These are validation figures after a choice made on them, and the rows were published before.

Limits: agentic acceptance of the regression workflow has not been run; the time column is never a model feature; no grouped split; regression has one candidate model.

## Generality (M3)

To test that the engine is not specialised to Bank Marketing and Auto MPG ([checklist section](../acceptance/V0.1-CHECKLIST.md#generality-m3)):

- **Two more real cases** from the installed scikit-learn, without download: [Breast Cancer Wisconsin](../../use-cases/breast-cancer-wdbc/README.md) (binary, 30 numeric features) and [diabetes progression](../../use-cases/diabetes/README.md) (regression on the raw features, no time or group column, so a random split). The package files state no licence for the data, so the data are **not committed**: each use case commits `prepare.py`, which copies the bundled bytes into an ignored `data/` folder and generates the committed `case.yaml` (`--check` detects a change of the bundled bytes, `--out DIR` makes a copy). Run `prepare.py` before `hypotrail init` on them; `check_layout.py` lists an absent copy as not materialized. Both walkthroughs run on them unchanged (WDBC logistic AUC 0.9962 on 171 validation rows; diabetes MAE 47.49 points [41.91, 53.09] against 68.88 for the training mean). Both datasets are likely known to language models, and their prediction-time semantics are a scenario, as their READMEs say.
- **26 synthetic perturbations** (`test_perturbations.py`): other names, separators, quoting, line endings, extra, constant and high-cardinality columns, declared missing values, a group column, extreme imbalance, and 60 rows complete with a clean `check`; a date time column, duplicates, a missing target, and a single positive row are refused with the capability named.
- **Four defects fixed** (contract changes): an undeclared blank or text token in a numeric column was silently read as a category; a binary target label outside the declared labels, and a missing binary target, silently counted as negative; a stratified split on a single positive row failed with an unstructured reason. `init` now reads the data through `data.load_dataset`, whose `check_values` refuses them.
- **Fixed post-v0.1 (G.12, warnings, not refusals)**: `not_yet_defensible` names a validation partition of fewer than 30 rows or (binary) fewer than 5 positive rows (`small_validation_partition`), a capacity that selects every validation row (`capacity_exceeds_validation`), and an exploration of a high-cardinality column, which now shows its 20 largest groups and `(other values)` with counts (`high_cardinality_grouping`, `--max-groups N`).

## Legacy and preservation

The legacy pilot (`framework/mlkit/pilot.py` and its modules) is unchanged apart from the Stale exit fix (WP0.2); `mlkit/study/` imports none of it (`test_isolation`). `use-cases/*/project.json` and `results.json` remain companion tutorial contracts: `case.yaml` is generated from them and `case-supplement.yaml` by an explicit migration, with tutorial confirmations downgraded to scenario assumptions. Historical tests that concern suspended holdout and production paths stay out of the gate. Do not reset existing study state; test in temporary studies.

## Next work

Owner decisions first ([open questions](../plans/V0.1-DECISIONS.md#open-questions-for-the-owner)), then, in the plan's spirit: an agentic re-run of S9 and the E1 runs with N repetitions (now also covering the post-v0.1 F3, F5, and T8 changes); the observed junior sessions of the observation kit; an agentic run of the regression workflow on Auto MPG (the engine side is done, M3) and of a study on the scikit-learn cases (engine side tested for generality); an agentic re-run after the P1–P7 fixes; a grouped split; a test partition; Copilot acceptance when directive A1 is lifted; a first session of the study panel inside a real VS Code, then observed sessions with the flag off and on (ADR 0003, "What is measured next"); and a first use by a real junior.
