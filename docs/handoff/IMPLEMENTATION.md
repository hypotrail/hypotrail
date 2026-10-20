# Implementation handoff (v0.2)

Status: **v0.2 implemented and closed** (v0.2a then v0.2b) on branch `claude/hypotrail-product-review-yrstzb`, 19 October 2026. It is a vertical slice of the [junior workflow](../specs/JUNIOR-WORKFLOW.md), guided by **Claude Code**, not GitHub Copilot, and used by no human junior yet. Evidence per remark and per decision: [V0.2-CHECKLIST.md](../acceptance/V0.2-CHECKLIST.md). Decisions taken during implementation: [V0.2-DECISIONS.md](../plans/V0.2-DECISIONS.md); the short list worth the owner's review and the demo script: [V0.2-OWNER-REVIEW.md](../plans/V0.2-OWNER-REVIEW.md). Scope sources: [owner demo 1 remarks R1–R11](../acceptance/OWNER-DEMO-1-REMARKS.md), the [review synthesis](../plans/V0.2-REVIEW-SYNTHESIS.md), and the [plan](../plans/V0.2-IMPLEMENTATION-PLAN.md). The v0.1 handoff is in the git history (commit `c534680` and before) and its evidence in [V0.1-CHECKLIST.md](../acceptance/V0.1-CHECKLIST.md).

The promise is unchanged: *do your ML study with an agent; Hypotrail guarantees that numbers, partitions, and decisions are traceable, and says what is not yet defensible.*

## What a user can do now

### Cases

| Case | Role | Final test sealed at `init` |
|---|---|---|
| [Hotel booking demand](../../use-cases/hotel-booking/README.md) (`use-cases/hotel-booking/case.yaml`, Resort Hotel) | **Discovery case from v0.3**: which new bookings to contact or ask a deposit from when the team handles 10 % of them; prediction when the booking is entered; leakage traps `reservation_status` and its date, `assigned_room_type`, `booking_changes`, `days_in_waiting_list`, and five columns of uncertain timing | 8,011 rows, **temporal** by arrival date (32,049 development rows); 6,092 identical rows kept together (`duplicates: {policy: group}`) |
| [Online Shoppers](../../use-cases/online-shoppers/README.md) (`use-cases/online-shoppers/case.yaml`) | **Advanced case since v0.3** (the v0.2b discovery case; its target is known at its prediction moment, R31): which finished sessions to follow up when the budget covers 10 % of them; the leakage question is `PageValues` | 2,466 rows, stratified (9,864 development rows); 125 identical rows kept together (`duplicates: {policy: group}`) |
| [Bank Marketing](../../use-cases/bank-marketing/README.md) (`bank.csv`) | v0.1/v0.2a reference and regression check | 904 rows, stratified (3,617 development rows) |
| [Bank Marketing full](../../use-cases/bank-marketing-full/README.md) (`bank-full.csv`, in time order) | Generality: a **temporal** final test, the last fifth of the campaigns less the 893 `bank.csv` rows already public (`prior_exposed_rows`) | 8,149 rows (37,062 development rows) |
| [Auto MPG](../../use-cases/auto-mpg/README.md) | Regression (MAE and RMSE in mpg) | 80 rows, stratified on target quantiles (318 development rows) |
| Synthetic planted-trap case (`framework/tests/fixtures/synthetic/make_case.py`), [WDBC](../../use-cases/breast-cancer-wdbc/README.md), [diabetes](../../use-cases/diabetes/README.md) | Generality tests (scikit-learn cases: run `prepare.py` first) | 20 % |

### The study

1. `hypotrail init` creates a study **outside the repository**, seals the final test before any look (default 20 %, seed recorded; temporal when the case declares `order`), installs the agent instructions (`CLAUDE.md`, a skill, `/hypotrail-resume`; Copilot files generated from the same templates, untested), writes `.vscode/settings.json` with the engine's interpreter when absent (otherwise prints the line, R7), and ignores `__marimo__/` in `.gitignore` and in `check`. Every decision starts open; no tutorial choice is imported.
2. **Step 0** (R2, R5): the agent shows the data card (`hypotrail data`): the row unit, sizes, the target labels, the column dictionary grouped with meaning, unit, availability and its source, special values, missing and distinct counts, three examples, and five fixed development rows with the target first. No rate or distribution before the split.
3. **Nine decisions** in a study created since v0.2b, at four pauses: (1) `prediction_time`, `feature_availability`; (2) `split` (by default a 5-fold cross-validation of the development rows, stratified, temporal blocks when the case has a time column, grouped when duplicates are declared; a train/validation split stays possible), `success_criterion` (fixed before any model: a minimum precision gain over the baseline at the adopted rule, or a minimum error reduction), then, after the exploration, `preprocessing` (missing indicator, rare-category threshold, caps, signed log transforms; parameters learnt per fold, stamped data-contingent when a target look preceded it); (3) `model_variant` (a weaker or stronger regularisation, or the model without one variable group, compared under the same protocol; the trial count is disclosed); (4) `policy` (binary: `threshold:T`, `capacity:K`, or `share:p`, applied within each fold under CV; the case's teaching share is 10 %, with gain points at 5, 10 and 20 %, R6) or `model_choice` (regression), then `final_test` (opened **once**, in the junior's own words, never delegated; a reason is optional since v0.3, WP-B; it measures the chosen configuration and is never reopened; later changes are listed as made after the final test), then `conclusion` (`adopt_policy` / `adopt_model`, `keep_baseline`, `inconclusive`). Studies created under v0.1 (five decisions, no final test) and v0.2a (seven) load and run unchanged; nothing is migrated.
4. **Confirmation modes** (R1, [ADR 0005](../decisions/0005-confirmation-modes.md)): `guided` (default) accepts an explicit endorsement bound to the open proposal ("oui je confirme cela"), refuses bare, negative, conditional, partial, off-topic and question replies, and asks a reason for the rule (or the model choice), the conclusion, and the final-test opening; `training` asks the junior to restate the decision's concepts (lexical EN/FR concept lists); `express` adds a standing delegation of the framing decisions, the criterion and the preprocessing. Lowering the mode needs the junior's words. In guided mode a standing delegation also covers the engine's default preprocessing. Restatements carry English and French labels; the study language is recorded.
5. **The reason check** (R3): the agent stops before confirming when the junior's reason does not fit (a reformulate, b confirm with other words, c keep the words); with (c) the engine records `--agent-concern` and the report shows it; `decide note --kind correction` attaches a later correction; a mechanical contradiction check on feature availability stops a guided confirmation without a concern.
6. **EDA governance** (R8): a quality overview of the development rows (missing patterns, duplicates, cardinality, rare categories, ranges); target analyses on training or out-of-fold rows with Wilson intervals, n, and a 19-shuffle permutation null band; a single-feature signal that only raises a legitimacy question (Online Shoppers `PageValues` AUC about 0.86, Bank `duration` 0.81); a ledger of target-involving looks shown as disclosure.
7. **Diagnostics** (R9): `diag.binary` (confusion at the rule, gain, ROC, PR, calibration with Brier, segments with intervals, bootstrap coefficient intervals, example errors), `diag.regression` (residuals against prediction, distribution and QQ, by feature and segment, predicted against observed, a heteroscedasticity flag), both development evidence on out-of-fold predictions; `diag.final_test` after the opening only.
8. **Deliverables**: one offline HTML report (`reports/study.html`) with a verdict card first (one judged criterion: the final test once opened, development evidence otherwise), "The data", 3–5 inline SVG charts, the decisions with their basis and the junior's words, evidence by scope, "What is not yet defensible", and a collapsed annex; every number is a `<data data-result-id>` citation. A generated Marimo notebook (`notebooks/study_generated.py`) with readable pandas/scikit-learn cells that recompute the registered figures from the development rows and `assert` equality (counts exact, rates 1e-9, refits 1e-6); a workbench (`notebooks/workbench.py`, never overwritten) whose starter cell loads the development training rows. Open them with `marimo run` (read) and `marimo edit` (workbench) through the engine's environment; the commands are in `status --json` (`deliverables.launch`).
9. **`check`** traces every number of a draft or a deliverable to a registered result, a decision value, the junior's words or the data card, by evidence scope (development or final); it refuses causal or forecast wording, a final-test figure cited after a post-opening change (`final_test_figure_outdated`), and a doubled scale. It is lexical (English and French).
10. **Engine messages carry `audience: junior|agent`**; surfaces never show agent instructions to the junior; `recap_junior` says values in words.

The engine guarantees, with tests, everything v0.1 did (revisions and idempotent requests, exposure by row key, invalidation by the dependency table, leased executions with unknown outcomes, failed renders kept and marked stale) and, since v0.2: no final-test row reaches any activity, view, preview, export or notebook before the opening (guard test); the opening is reserved before any final row is read, so an interrupted opening consumes the final test.

## Commands

```sh
uv sync --project framework --group dev
uv run --project framework hypotrail init --case use-cases/hotel-booking/case.yaml --study ~/studies/hotel
cd ~/studies/hotel && claude          # then talk to the agent
```

Commands (`hypotrail --help` lists them): `init`, `status [--summary|--json]`, `plan`, `decide propose|confirm|withdraw|note`, `mode set`, `run <activity>`, `render`, `check`, `preview policy|effects|proposal`, `data`, `decisions`, `evidence`, `explain`, `export handoff`, `session-report`. Exit codes: 0, 2 refusal, 3 stale or failed deliverable, 4 unknown outcome. Contracts: [CLI-CONTRACT.md](../specs/CLI-CONTRACT.md) (v0.2 additions in §3.3, §4.1, §5.2–5.3, §11–§13), [CASE-CONTRACT.md](../specs/CASE-CONTRACT.md), [CLI-CONTRACT-COMPANION.md](../specs/CLI-CONTRACT-COMPANION.md).

Keep the study **outside the repository**: Claude Code loads `CLAUDE.md` and `AGENTS.md` from parent folders.

## What is refused or not built

Refused explicitly (`unsupported_capability`, the capability named; the "(v0.2)" in these identifiers is historical): a date or decimal time column, a missing target value, identical records without a `duplicates` declaration, a stratified split with fewer than two rows of a class, models other than the constant baseline, logistic regression (with its variant), the training mean and linear regression (with its variant). A declared group column is accepted with the limitation `grouped split (v0.2)`: the split reports the groups both partitions share. A changed dataset or case file (`dataset_changed`, `sources_changed`): start a new study (regenerated case files make earlier Bank and Auto MPG studies report `sources_changed`).

Not built, by design: the old webview companion (paused), an application server, MCP integration, multi-agent orchestration, decision controls in the HTML. The study panel below is a flagged CLI client.

## Study panel for VS Code (flag off by default, stages v0 to v3)

[`clients/vscode-companion/`](../../clients/vscode-companion/README.md), [ADR 0003](../decisions/0003-companion-webview-v0.md), [ADR 0004](../decisions/0004-companion-advanced.md) (amended by WP-A5: decision 7 "local launch"), [spec](../specs/COMPANION-ADVANCED.md). Enable with `hypotrail.companion.enabled` or `HYPOTRAIL_COMPANION=1`; stage `hypotrail.companion.stage` (default `v0`) or `HYPOTRAIL_COMPANION_STAGE`.

- A client of the CLI only (argv from `.hypotrail/agent.json`, `execFile`, no shell, no state, no server, no model). Writes W1–W7 only, gated by stage. Opening the final test and changing the mode are chat acts: the panel explains them and offers no control.
- **v0.2 changes**: two-layer copy (the panel's own words for the junior; engine text for the agent only under "Details"); "Your next move" first at every stage; readable decision values ("Select the top 10% by score"); limits with severity, listed once; the final-test chip on every tab; **"Open in Marimo (read)"** (`marimo run` on the generated notebook) and **"Open in Marimo (edit)"** (`marimo edit` on the workbench), in a named VS Code terminal with an argument list (the only launches `check_layout.py` allows); Data & EDA (data card, quality, questions per chart, null band, look ledger, leakage detector); Evidence led by the final test and the exposure ledger, development evidence (CV, variant) apart from final evidence, diagnostics; What if? with share rules and the gain curve; the mode explainer; high-contrast borders, fixed-pixel charts, cards below 600 px.
- **Unverified**: no real VS Code session ([MANUAL-TEST.md](../../clients/vscode-companion/MANUAL-TEST.md), status "not run"; the exit criterion before moving the default stage); the chat insertion stays off (CA.8); no human use.

## Evidence

Gates at the v0.2 closure: see [the checklist](../acceptance/V0.2-CHECKLIST.md#gate-run-for-this-checklist). Agent acceptance (Claude Code on `claude-opus-5-5`, not Copilot, simulated juniors, N = 3 per scenario and case): [v0.2a](../acceptance/runs/claude-code-2026-10-19-v0.2a.md) on Bank, S0–S11, latest round 36/36 (about $16); [v0.2b](../acceptance/runs/claude-code-2026-10-19-v0.2b.md) on Online Shoppers, Bank full, Auto MPG and Bank, S0, S1, S6, S8, S10–S13, latest round 44/45 ($31.03). Earlier reports: [`docs/acceptance/runs/`](../acceptance/runs/).

## Known limits and gaps

Not proven (details in the checklist's "Not proven" section):

- **No human junior, no GitHub Copilot, no real VS Code session.** All agentic evidence is Claude Code with scripted or simulated juniors; Copilot instruction files are generated but untested (owner decision for v0.2).
- **Short scenarios, N = 3.** No agent run went from step 0 to the conclusion in v0.2; E1 (the full conversation) was not rerun. The setup confirms the preprocessing, the variant and the rule by direct CLI calls, so the agent's proposals at those pauses are only exercised in S8 and S13. Two fixes (the S13 calibration binding; the S1 recap that quoted older words) are not confirmed by a run.
- **Lexical heuristics.** Guided, training and partial-refusal rules, the reason check, the contradiction warning, `check`'s number binding and evidence scopes, `feature_basis` name matching and the graders are word lists (English and French). "oui, la pizza du client est bonne pour la campagne" would still pass the relation check. Each `check` fix of v0.2b widened the pool a figure may match.
- **Hotel booking demand data** (v0.3) are derived from the tidytuesday mirror (the authors' files were unreachable), checked against the counts the article publishes but **not compared byte for byte** with the authors' files. The article's variable table could not be read: descriptions come from the tidytuesday dictionary, and the article states that every value is the one of the day before arrival, not at booking (fact `snapshot_limit` in the case).
- **Online Shoppers data** come from one public GitHub mirror (UCI was unreachable), checked against UCI's published counts but **not compared byte for byte** with the UCI archive (owner TODO, in the case README). Its variable descriptions are `scenario_assumption` (recalled, not read from the source). Bank full comes from two byte-identical mirrors, same caveat.

Known behaviour worth a decision (all in [the owner review](../plans/V0.2-OWNER-REVIEW.md)):

- **Bank full period shift**: the temporal final test has a positive rate of 31.8 % against 7.3 % in development; the criterion is not met in development and met on the final test. Kept as a drift lesson.
- The junior path is heavy (nine confirmations, three evidence scopes, an agent prompt of about 4,300 words); recaps run over five lines; agents sometimes offer coaching templates ("… parce que …").
- Diagnostics are not a pause of their own (read and rule proposal in one message).
- A threshold rule rarely satisfies the binary criterion (the constant baseline selects no row above most thresholds); share rules are the default.
- Coefficient intervals are conditional on the fitted preparation; earlier L-BFGS logistic results are flagged by `point_check`, not recomputed.
- Notebook and workbench reads are not in the look ledger.

Remaining defects and small gaps:

- The plan step "Choose a decision policy" still says "(a threshold or a capacity)" without the share rule.
- The panel reads the scenario share from `status --json` although the summary now carries `scenario_defaults`.
- The Overview concept card at a step's first appearance is not built (CI.16).
- `delegation_scope` is not shown in the HTML or the notebook; `status --json` is large (agents use `--summary`); deliverables show execution liveness as `not_checked`.

Platform: POSIX only (`fcntl`); editable install only; absolute paths recorded at `init` (moving a study or the checkout needs a new study); Marimo internal codegen pinned to `marimo==0.25.1` (rerun the spike after any upgrade, [ADR 0001](../decisions/0001-notebook-and-html.md); running the generated notebook refits one model); float time columns are still misread by the legacy `classical.split`.

## Legacy and preservation

The legacy pilot (`framework/mlkit/pilot.py`) is unchanged; `mlkit/study/` imports none of it (`test_isolation`). `use-cases/*/project.json` and `results.json` remain companion tutorial contracts; `case.yaml` is generated from them (Bank, Auto MPG) or by `build_case.py` (Hotel booking, Online Shoppers, Bank full), never importing tutorial choices as decisions. v0.1 and v0.2a studies keep their decision sets, result identities and partitions. Do not reset existing study state; test in temporary studies.

## Next work (v0.3 candidates, each needs an owner decision)

From the [review synthesis §4](../plans/V0.2-REVIEW-SYNTHESIS.md#v03-and-later-candidates-each-needs-an-owner-decision), with what v0.2 taught:

1. **Owner demo 2** on Online Shoppers with the panel on ([script](../plans/V0.2-OWNER-REVIEW.md#owner-demo-2-script)), the real VS Code checklist ([MANUAL-TEST.md](../../clients/vscode-companion/MANUAL-TEST.md)), and the byte comparison of the two mirrored datasets with UCI.
2. **Observed junior sessions** with the [observation kit](../research/OBSERVATION-PROTOCOL.md) when possible (owner: no gate, do not ask again).
3. **Senior review packet** and reviewer loop (the positioning toward team integrity; the handoff export is a start).
4. **Privacy / redaction mode** (a `privacy` case field that masks example rows), then **case drafting from the junior's own CSV**.
5. **Model info sheet** (Kapoor & Narayanan 2023) and a manager brief export.
6. **Engine-served pedagogy**: `next_action` carries the term, the misconception and the question, so the agent prompt shrinks (about 4,300 words, 16 "never"); key for **Copilot portability** and a Copilot acceptance run.
7. A full-conversation agent run (E1) on Hotel booking demand (the discovery case since v0.3), with N > 3, before trusting pass rates.
8. Later: counterfactual leakage branch ("what if `PageValues` were included?"), pilot designer, forward temporal backtest, more model families under a complexity budget, a grouped split by a group column, a multi-study portfolio, a local learning record, Online Retail II as an advanced cross-sell case, publication of the trap benchmark.
