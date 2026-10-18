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

The agent uses the CLI, recorded in `.hypotrail/agent.json`: `status [--summary|--json]`, `plan`, `decide propose|confirm|withdraw`, `run <activity>`, `run --acknowledge-interruption`, `preview policy`, `check`, `render`; and, for the facilitator of an observed session, the read-only `session-report`. The full contract, with exit codes (0, 2 refusal, 3 stale or failed deliverable, 4 unknown outcome) and every schema, is [CLI-CONTRACT.md](../specs/CLI-CONTRACT.md); the case format is [CASE-CONTRACT.md](../specs/CASE-CONTRACT.md).

For the synthetic case:

```sh
uv run --project framework python framework/tests/fixtures/synthetic/make_case.py /path/outside/the/repository/synthetic-case
uv run --project framework hypotrail init --case /path/outside/the/repository/synthetic-case/case.yaml --study /path/outside/the/repository/synthetic-study
```

Keep the study **outside the repository**: Claude Code loads `CLAUDE.md` and `AGENTS.md` from parent folders, so a study inside the repository would also receive the repository's development instructions.

## What is excluded from v0.1

Refused explicitly (`unsupported_capability`, with the capability named), never handled silently:

- regression tasks: **Auto MPG** has a `case.yaml` but `init` refuses it (regression, declared group column); generality on Auto MPG is not validated;
- declared time or group columns, duplicate records, a held-out test partition, models other than the constant baseline and logistic regression (a random forest is "not supported in v0.1");
- a changed dataset or case file (`dataset_changed`, `sources_changed`): start a new study.

Not built, by design: the webview companion (paused; [ADR 0002](../decisions/0002-companion-as-cli-client.md) makes any future one a client of this CLI), an application server, MCP integration, multi-agent orchestration, decision controls in the HTML.

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
- `delegation_scope` is shown in `status`, the summary, and the text output, but not in the HTML or the notebook.
- `status --json` is large (tens of kilobytes); agents are told to use `status --summary`.
- The HTML report and notebook show execution liveness as `not_checked`; only `status` probes leases.

## Observation kit (post-v0.1)

For 2 or 3 sessions with human junior developers, run later by the owner: [the protocol](../research/OBSERVATION-PROTOCOL.md) and its [templates](../research/observation/) (observation grid, comprehension test with answer key, consent form, session log). Instrumentation: `hypotrail session-report --study S [--since REV]` (read-only, content-free timeline, `--format text` for Markdown) and the opt-in session log (`HYPOTRAIL_SESSION_LOG=1` once; [CLI-CONTRACT.md §8.6](../specs/CLI-CONTRACT.md#86-session-report-and-session-log-post-v01-observation-kit)). No session has been run.

## Validation

See [CONTRIBUTING.md](../../CONTRIBUTING.md) for the gate (`check_layout.py` and the targeted pytest scope with the `browser` group), the opt-in Marimo spike (`HYPOTRAIL_RUN_SPIKES=1`), and the opt-in agent acceptance (`HYPOTRAIL_AGENT_ACCEPTANCE=1`, real `claude -p` sessions with model cost). Agent acceptance reports: [first run](../acceptance/runs/claude-code-2026-10-18.md), [rerun](../acceptance/runs/claude-code-2026-10-18-rerun.md), [final check](../acceptance/runs/claude-code-2026-10-18-final.md); E1 steelman: [protocol](../research/E1-STEELMAN.md), [arm A](../research/runs/E1-arm-A-2026-10-18.md), [arm B](../research/runs/E1-arm-B-2026-10-18.md).

## Legacy and preservation

The legacy pilot (`framework/mlkit/pilot.py` and its modules) is unchanged apart from the Stale exit fix (WP0.2); `mlkit/study/` imports none of it (`test_isolation`). `use-cases/*/project.json` and `results.json` remain companion tutorial contracts: `case.yaml` is generated from them and `case-supplement.yaml` by an explicit migration, with tutorial confirmations downgraded to scenario assumptions. Historical tests that concern suspended holdout and production paths stay out of the gate. Do not reset existing study state; test in temporary studies.

## Next work

Owner decisions first ([open questions](../plans/V0.1-DECISIONS.md#open-questions-for-the-owner)), then, in the plan's spirit: an agentic re-run of S9 and the E1 runs with N repetitions (now also covering the post-v0.1 F3, F5, and T8 changes); the observed junior sessions of the observation kit; Auto MPG (regression) to validate generality; a test partition; Copilot acceptance when directive A1 is lifted.
