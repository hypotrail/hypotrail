# Implementation handoff (v0.2)

## Owner-session batch of 27 October 2026, integrated (R23 to R31)

Three lots, integrated on branch `m-int` (unit, real-CLI and simulated-browser tests, the full gate once; **no Copilot or VS Code session**). Notes R23–R31 of [copilot-companion-2026-10-26](../acceptance/runs/copilot-companion-2026-10-26.md) are marked implemented.

- **Automatic mode** (R23, R24): `automation run --progress` narrates in the study language (`mlkit.study.automation_words`: a header, one line per recorded decision with its value and why, each computation's key result from registered values, a closing summary); on a terminal, `automation run` prints a readable summary, and `--json` or any non-terminal stdout keeps the JSON (the agent instructions pass `--json`; the panel never calls it and always passes `--json`). A review of an automatic decision is a `decision` pause (adopt / change / explain, nothing recommended, the reviewed decision's step). CLI-CONTRACT §1, §5.5.
- **Panel** (R27–R31): the lesson style (COMPANION-ADVANCED §6.0, LS-1 to LS-6: journey rail and position line, "At this step" and "Next", a guided reading for every chart, notions, "Copy the question", the board mapped from the VS Code theme class); W6 withdrawn (ADR 0004 decision 12): writes W4, W5, W7 only, `check_layout.py` refuses an acknowledgement control.
- **Report** (R25–R30, R26 defects): the lesson report below.
- **Integration fixes**: the panel's next move read an automatic review as "Confirm again"; it now reads "Review …" with an adoption question (`data-hero-review`, LS-2), consistent with the R24 pause; the panel's EDA intro no longer names "understanding" (the panel must not know the understanding review, A23). Panel fixtures recaptured (no hand-written fixture drifted).
- **Gate** (once, per directory): `check_layout.py` ok; top-level, acceptance and exporters 736 passed, 99 skipped (98 opt-in agent scenarios); `study/understanding` 398 passed, 2 skipped, 1 xfailed (one failure, fixed above, its file rerun green); `study/libraries` 322 passed, 5 skipped; `study/deliverables` 239 passed; `study/test_*.py` in quarters 2,460 passed, 6 skipped; Node 255 passed; panel pytest 460 passed, 12 skipped (the opt-in `HYPOTRAIL_SHOTS` screenshots), 12 failed, all pixel baselines (below).
- **Pixel baselines**: all 108 of `test_webview_gate.py` differ (the 12 parametrizations, 9 shots each), by design after the lesson restyle; **not updated**: the owner reviews the diff images (`clients/vscode-companion/.local/baseline-diff/`) before `--update-baselines`.

## Lesson-style report (owner decision 2026-10-27, R25 to R30)

The report follows the approved mockup [report-lesson-style-mpg-fr.html](../plans/mockups/report-lesson-style-mpg-fr.html) (branch `m-rep`; unit, real-study and simulated-browser tests, **no Copilot session**). `TEMPLATE_VERSION` 4; CLI-CONTRACT §8.3 and §11.5.

- **Shell** (R28): the "blackboard and graph paper" charter, the board by default (no `prefers-color-scheme`, no storage), a whiteboard button, a sticky table of contents with each chapter's status (folded under 1,040 px), a position line (chapter n/9, what remains, decisions to review). No CDN, reduced motion respected, no sideways scrolling at 390 px.
- **Two editions in one file** (R27): the study language first (the only one shown without script), the other behind the language button, which keeps the reader's place. The second edition is rendered from the same registry in the other language; words recorded in one language are shown as recorded and marked "(fr)" or "(en)". `check` reads the numbers of each edition in its language.
- **Chapters as lessons** (R29): "At this step", the term then "In this study", the choice cards (an automatic decision reads "to review", never "Confirmed decision", R26), folds (example, why it holds, code from the notebook, where it breaks, what remains uncertain), "What we keep", "Done → Next". Then a summary, "Say it out loud", the decisions to review, a compact annex.
- **Every figure and table** (R30) is framed with "Why this chart" and its frame line, "How to read it", "What we conclude" with cited registry values, and "Watch out" when a trap exists. Texts live in `content/lesson.yaml` (English and French, regression and binary overlays), none in Python. New charts from recorded results only: errors with intervals and the criterion bar (figure V), configurations fold by fold, paired differences, residuals by model and by period, a coefficient forest.
- **R26 defects**: no classification wording in a regression report, no English in a French edition (the French report texts now take the regression cross-validation overlay, as the English do), chapter status consistent with the plan, an EBM variant named by its family, the tension between the one-standard-error pick and a paired difference that excludes zero stated in chapter 7, and a regression final test drawn without a declared order says it cannot show drift.
- Left out of the mockup: the illustrative "course" figures and the interactive widgets (no recorded values), and numbers the registry does not hold (the criterion threshold in error units, the "x % lower" figure). Existing studies render unchanged in content; only the page layout moves to version 4.

## Owner-session batch, wave W3: L8, the fix pass and L9, integrated (26 October 2026)

Lots L8 and L9 and the third-session fix pass (R21, R22, capture before the opening) of the [2026-10-26 plan](../plans/OWNER-SESSION-2026-10-26-PLAN.md), integrated on branch `w3-int` (unit, walker, simulated-browser and real-CLI tests, the full gate once; **no Copilot session**). The L9 details:

- **Launch** (ADR 0005 amendment of 2026-10-26): `init --automation until_final_test|full_demo`; nothing else sets it. Studies created without the flag, or before L9, are unchanged (`view.automation` null, `view.review_queue` empty).
- **Run**: `hypotrail automation run [--progress]` follows `next_action` exactly as given, records each covered decision with the basis `automatic` (no words, `actor: assistant`; never the junior's words nor a delegation) and the engine's `auto_value` (draft or recommendation; else the one-standard-error pick, the scenario share, the conclusion from the criterion judged on the final test), runs each activity, stops at the first refusal or at anything only the junior answers, and ends the mode one way where it stops covering the plan. `automation stop --user-words` ends it midway.
- **Review**: `next_action` (`review: true`) walks every automatic decision in the plan's order; the junior adopts (`adopted_from`, no invalidation) or changes it; in `until_final_test` the junior opens the final test only after the review (`automatic_decisions_reviewed`).
- **Demo** (ADR 0006 amendment): `full_demo` also opens the final test (`basis: automatic` on the opening record; a delegation still never opens it) and concludes; "The final test was opened automatically" stays for good; changes during its review are marked as made after the final test.
- **Surfaces**: `not_yet_defensible` ids `automatic_decisions_to_review` and `final_test_opened_automatically`, first in the summary; report and notebook banners in English and French; the panel shows them in its alert strip and an "automatic, to review" basis chip (read only, no new write). AGENTS.md carries the owner-approved exception.
- Agent text: the rule-4 bullet of [proposals/L9-agent-text.md](../plans/proposals/L9-agent-text.md) applied; raw budget 3,977 / 3,936 words (binary / regression, cap 4,000), rendered Copilot copy 4,392 / 4,351 (cap 4,400).
- Integration fixes: a French handoff words the `automatic` basis, and a French regression pack traces its baseline MAE; the capture before the opening runs without MLflow noise on stderr; the full-demo runner follows that capture with its options. Panel fixtures recaptured; pixel baselines unchanged (the 12 environment failures are identical before and after L9; the batch's visual changes await the owner's review).

## Owner-session batch, wave W2 (26 October 2026)

Lots L3, L5 and L6 of the [2026-10-26 plan](../plans/OWNER-SESSION-2026-10-26-PLAN.md), integrated over wave W1 (unit, walker, simulated-browser and real-CLI tests; **no Copilot session yet**):

- **One language per study** (L3): `init` and `plan` give the step texts in the study language; EDA questions, notes and warnings are translated at read time (`question_junior`); the case's statements come in French from a translation sidecar `case.l10n.yaml` (five workshop cases; recorded with its digest at `init`, never `sources_changed`; it also declares `glossary_examples` for the cases the glossary's examples describe, so other studies read the definitions without them); `status --summary --digest` adds `texts {en, fr}` so the panel's EN/FR switch changes the engine's texts too; the report and the notebook follow the study language.
- **Drafts that read the evidence** (L5), new studies only (`exploration_order: structural_first`; an existing study keeps its plan and drafts): step `structural_eda` (`eda.quality`, then at most three screened `eda.distribution` runs, no target read) before the preparation; the preparation drafted with `recommended.reasons` and the default as `alternatives`, not data-contingent when only target-free results motivate it; `data_contingent_reason.junior_text` and the term "look at the target"; the EBM drafted beside the tuned penalty when the diagnostics flag a pattern; `junior_words` and `not_offered` for families; a family outside the catalogue refused with a teaching `junior_message`. Hotel's `calendar: year` declaration waits for a case revision.
- **Narrative report** (L6): verdict, nine chapters (choice, why, evidence with its class, what remains uncertain), a table of contents, a compact annex; the structural check is chapter four's first part. `TEMPLATE_VERSION` 3.
- Agent instructions: raw budget 3,929 / 3,888 words (binary / regression, cap 4,000); rendered Copilot copy 4,345 / 4,304 (cap 4,400).
- Journey checks: J-LANG automated on French synthetic and Auto MPG studies (gate) and on Hotel (opt-in, `HYPOTRAIL_JOURNEY_HOTEL=1`); J-REC on Hotel's structural steps (gate); J-REPORT structural and browser tests (gate).

## Owner-session batch, wave W1 (26 October 2026)

Lots L1, L2, L4 (level 1) and L7 of the [2026-10-26 plan](../plans/OWNER-SESSION-2026-10-26-PLAN.md), integrated on one branch (unit, walker, simulated-browser and real-CLI tests; **no Copilot session yet**, §5.4 rehearsal to do):

- **Pickers** (L1): every pause with options carries `pause.option_labels` in the study language; at the model choice and the conclusion (no recommendation) `next_action.choice_options` lists exactly the values a confirmation accepts now, pause kind `choice`. The Copilot copy ends every closed question with the picker, asks a dismissed picker again without blame, and proposes a free pick before adopting it; the Claude Code copy changes only listed shared lines.
- **Progress** (L4): `run … --progress` writes start, heartbeat (≤ 10 s) and end lines on stderr in the study language; stdout unchanged; both copies keep stderr; Copilot may narrate before and between tool calls. Fold-level progress needs L8.
- **Panel line** (L2): with the panel on, `next_action.panel.shown` names the tab and section that show what the command produced (null after reads, failed runs, acknowledgements); a write names what it produced even when a choice follows (the opening names Final test, D3), and a read names the choice the chat asks (Decisions → Waiting for your answer). Rule 6 relays `shown.line` instead of its own mapping. The panel shows that choice as a read-only card (v1+) and one Evidence card per compared variant.
- **Hand-over** (L7): the `no_time_or_entity_identifier` limit follows the declared order (R17); at `done`, `next_action.after_study` gives the handoff command, the Azure ML export plan only when the chosen model is in the `team-azureml-v1` matrix (binary logistic included since R19), and `cloud_status: not_qualified`; the skill relays its junior text; the panel shows that text read only in "Your next move" and Learn & hand off (no new write). `export azureml` without `--expected-revision` names the revision to use (R18).
- Agent instructions: raw budget 3,965 / 3,924 words (binary / regression, cap 4,000); rendered Copilot copy 4,381 / 4,340 (cap 4,400, D18).

## Understanding and handover review v1 (23 October 2026)

An opt-in review, off by default, that keeps the team's understanding of a study: tasks per
responsibility, first answers before help, human reviews (declared, not authenticated), a
colleague's handover task, freshness by dependency, an approved export committed with the
work, and a gate on `export handoff` under a required policy. It certifies neither
competence, security nor scientific validity; no pilot with people was run. Details, the
A01–A31 matrix and limits: [UNDERSTANDING-V1.md](UNDERSTANDING-V1.md), [ADR 0008](../decisions/0008-understanding-review.md).

## Library integration v1, workstream A (23 October 2026)

Shared v1 contracts, the separately installable predictor runtime, `run predictor.capture`
(the chosen model captured, reloaded and parity-checked before the final test opens; the
final test then scores the reloaded capture), `read_export_source` for the Azure ML
workstream, Pandera validation from the data contract, a SciPy bootstrap backend, an opt-in
Evidently profile (`run diagnostics.population`) and MAPIE risk control and split-conformal
adapters. Details, interfaces, test evidence, limits and the AC01–AC28 matrix:
[LIBRARIES-V1.md](LIBRARIES-V1.md).

## Review remediation J0--J3 (22 October 2026)

J0 adds an opt-in `init --reliability-profile review-v1`, static `analysis_contract`
validation and a derived `assurance` object (`status --summary --fields assurance`).
The default remains legacy and old state is not migrated. The opt-in profile now executes
J1 explicit evaluation memberships, J2 validity requirements and J3 business-objective
selection. Future/group-disjoint execution is available only with the required clocks or
groups and a feasible plan; no legacy fallback is used.

Hotel remains the discovery case, now explicitly an exercise in leakage and evidence
limits: **performance at booking is not established** from the published snapshot.
Bank full and Auto MPG have bounded retrospective claim ceilings. Their substantive
case changes trigger the normal source-change check for older studies; no new
case/code equivalence exception is added. Data bytes are unchanged.

The test is reserved by a cooperative protocol, not isolated from an agent that can
read the local source file. Confirmations are agent-reported, not independently
authenticated; cross-study exposure/budget inheritance is not enforced. The old
`sealed` status is a compatibility identifier, not a filesystem guarantee.

J1--J3 fix the opt-in temporal/nested-fold protocol, diagnostic prerequisites,
business-metric selection and criterion interpretation. Bounded code equivalence and the
remaining history work are still J4. See the [findings ledger](../acceptance/reliability-roadmap/FINDINGS.md)
and [J0](../acceptance/reliability-roadmap/J0.md), [J1](../acceptance/reliability-roadmap/J1.md),
[J2](../acceptance/reliability-roadmap/J2.md), [J3](../acceptance/reliability-roadmap/J3.md).
The required engine, Node and complete Companion gates pass in this cloud run. A saved
no-hinting fontconfig profile plus TTF copies decompressed from the image's OpenAI Sans WOFF2
files make Chromium rendering reproducible. Ninety pixel baselines remain unchanged; 18 EDA
baselines reflect the intended J0 disclosure copy and chart source-label changes. The owner
asked to review their retained before/after/diff sheet at final handoff. That work has since
been committed (J0 in `58f048c`, J1–J3 in `0263ccc`; see the git history).
The remaining sections below describe the legacy slice and its historical evidence.

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
3. **Ten decisions** in a binary study created today (nine in a regression study, and in a binary study created under the earlier v0.2b contract), at four pauses: (1) `prediction_time`, `feature_availability`; (2) `split` (by default a 5-fold cross-validation of the development rows, stratified, temporal blocks when the case has a time column, grouped when duplicates are declared; a train/validation split stays possible), `success_criterion` (fixed before any model: a minimum precision gain over the baseline at the adopted rule, or a minimum error reduction), then, after the exploration, `preprocessing` (missing indicator, rare-category threshold, caps, signed log transforms; parameters learnt per fold, stamped data-contingent when a target look preceded it); (3) `model_variant` (a weaker or stronger regularisation, or the model without one variable group, compared under the same protocol; the trial count is disclosed); (4) `model_choice` (binary: `fit.logistic` or a declared variant slot, never the baseline; regression: a fit slot, the mean baseline included), then, in a binary study, `policy` (`threshold:T`, `capacity:K`, or `share:p`, applied within each fold under CV, suffixed `@fit.variant` when the chosen model is a variant; the case's teaching share is 10 %, with gain points at 5, 10 and 20 %, R6), then `final_test` (opened **once**, in the junior's own words, never delegated; a reason is optional since v0.3, WP-B; it measures the chosen configuration and is never reopened; later changes are listed as made after the final test), then `conclusion` (`adopt_policy` / `adopt_model`, `keep_baseline`, `inconclusive`; an adopting verdict needs the final test opened with a current final evaluation, the other two are allowed at any time, review round 9). Studies created under v0.1 (five decisions, no final test) and v0.2a (seven) load and run unchanged; nothing is migrated.
4. **Confirmation modes** (R1, [ADR 0005](../decisions/0005-confirmation-modes.md)): `guided` (default) accepts an explicit endorsement bound to the open proposal ("oui je confirme cela"), refuses bare, negative, conditional, partial, off-topic and question replies; since v0.3 (WP-B, R27) a reason is optional for every decision (the record says `reason_given`, and a decision confirmed without one shows "no reason given"), and a short yes confirms only as the answer to the closed question "Do you adopt this decision?" (`--adoption-question`, or the adopt option of a choice picker, `--channel choice`); `training` asks the junior to restate the decision's concepts (lexical EN/FR concept lists); `express` adds a standing delegation of the framing decisions, the criterion and the preprocessing. Lowering the mode needs the junior's words. In guided mode a standing delegation also covers the engine's default preprocessing. Restatements carry English and French labels; the study language is recorded.
5. **The reason check** (R3): the agent stops before confirming when the junior's reason does not fit (a reformulate, b confirm with other words, c keep the words); with (c) the engine records `--agent-concern` and the report shows it; `decide note --kind correction` attaches a later correction; a mechanical contradiction check on feature availability stops a guided confirmation without a concern.
6. **EDA governance** (R8): a quality overview of the development rows (missing patterns, duplicates, cardinality, rare categories, ranges); target analyses on training or out-of-fold rows with Wilson intervals, n, and a 19-shuffle permutation null band; a single-feature signal that only raises a legitimacy question (Online Shoppers `PageValues` AUC about 0.86, Bank `duration` 0.81); a ledger of target-involving looks shown as disclosure.
7. **Diagnostics** (R9): `diag.binary` (confusion at the rule, gain, ROC, PR, calibration with Brier, segments with intervals, bootstrap coefficient intervals, example errors), `diag.regression` (residuals against prediction, distribution and QQ, by feature and segment, predicted against observed, a heteroscedasticity flag), both development evidence on out-of-fold predictions; `diag.final_test` after the opening only.
8. **Deliverables**: one offline HTML report (`reports/study.html`) with a verdict card first (one judged criterion: the final test once opened, development evidence otherwise), "The data", 3–5 inline SVG charts, the decisions with their basis and the junior's words, evidence by scope, "What is not yet defensible", and a collapsed annex; every number is a `<data data-result-id>` citation. A generated Marimo notebook (`notebooks/study_generated.py`) with readable pandas/scikit-learn cells that recompute the registered figures from the development rows and `assert` equality (counts exact, rates 1e-9, refits 1e-6), the exploration written as the pandas idioms a junior types (`head`, `info`, `describe`, `isna().sum()`, `value_counts`, `groupby`, `pd.crosstab`, `corr(method="spearman")`, `plot.hist`/`plot.bar`; v0.3 WP-F2); a workbench (`notebooks/workbench.py`, never overwritten) whose starter cells load the development training rows and take a first look at them. Open them with `marimo run` (read) and `marimo edit` (workbench) through the engine's environment; the commands are in `status --json` (`deliverables.launch`).
9. **`check`** traces every number of a draft or a deliverable to a registered result, a decision value, the junior's words or the data card, by evidence scope (development or final); it refuses causal or forecast wording, a final-test figure cited after a post-opening change (`final_test_figure_outdated`), and a doubled scale. It is lexical (English and French); a numeric form it cannot read (a number glued to letters, an exponent beyond ±300, a word number with a scale word, a French decimal without its leading zero) is reported, never skipped.
10. **Engine messages carry `audience: junior|agent`**; surfaces never show agent instructions to the junior; `recap_junior` says values in words.

The engine guarantees, with tests, everything v0.1 did (revisions and idempotent requests, exposure by row key, invalidation by the dependency table, leased executions with unknown outcomes, failed renders kept and marked stale) and, since v0.2: no final-test row reaches any activity, view, preview, export or notebook before the opening (guard test); the opening is reserved before any final row is read, so an interrupted opening consumes the final test.

## Commands

```sh
uv sync --project framework --group dev
uv run --project framework hypotrail init --case use-cases/hotel-booking/case.yaml --study ~/studies/hotel
cd ~/studies/hotel && claude          # then talk to the agent
```

Commands (`hypotrail --help` lists them): `init`, `status [--summary|--json]`, `plan`, `decide propose|confirm|withdraw|note`, `mode set`, `run <activity>`, `render`, `check`, `preview policy|effects|proposal`, `data`, `decisions`, `evidence`, `explain`, `export handoff|azureml`, `session-report`, `understanding` (opt-in, off by default, [ADR 0008](../decisions/0008-understanding-review.md)). Exit codes: 0, 2 refusal, 3 stale or failed deliverable, 4 unknown outcome. Contracts: [CLI-CONTRACT.md](../specs/CLI-CONTRACT.md) (v0.2 additions in §3.3, §4.1, §5.2–5.3, §11–§13), [CASE-CONTRACT.md](../specs/CASE-CONTRACT.md), [CLI-CONTRACT-COMPANION.md](../specs/CLI-CONTRACT-COMPANION.md).

Keep the study **outside the repository**: Claude Code loads `CLAUDE.md` and `AGENTS.md` from parent folders.

## What is refused or not built

Refused explicitly (`unsupported_capability`, the capability named; the "(v0.2)" in these identifiers is historical): a date or decimal time column, a missing target value, identical records without a `duplicates` declaration, a stratified split with fewer than two rows of a class, models other than the constant baseline, logistic regression, the training mean, linear regression, and their variants (a regularisation strength, a feature group left out, or, since v0.3, an Explainable Boosting Machine or histogram gradient boosting family, [ADR 0007](../decisions/0007-trial-budget-and-model-families.md)). A declared group column is accepted with the limitation `grouped split (v0.2)`: the split reports the groups both partitions share. A changed dataset or case file (`dataset_changed`, `sources_changed`): start a new study (regenerated case files make earlier Bank and Auto MPG studies report `sources_changed`).

Not built, by design: the old webview companion (paused), an application server, MCP integration, multi-agent orchestration, decision controls in the HTML. The study panel below is a flagged CLI client.

## Study panel for VS Code (flag off by default, stages v0 to v3)

[`clients/vscode-companion/`](../../clients/vscode-companion/README.md), [ADR 0003](../decisions/0003-companion-webview-v0.md), [ADR 0004](../decisions/0004-companion-advanced.md) (amended by WP-A5: decision 7 "local launch"), [spec](../specs/COMPANION-ADVANCED.md). Enable with `hypotrail.companion.enabled` or `HYPOTRAIL_COMPANION=1`; stage `hypotrail.companion.stage` (default `v0`) or `HYPOTRAIL_COMPANION_STAGE`.

- A client of the CLI only (argv from `.hypotrail/agent.json`, `execFile`, no shell, no state, no server, no model). Writes W4, W5, and W7 only, gated by stage (W1–W3, confirm, withdraw, propose, were withdrawn in v0.3: decisions are made in the chat; ADR 0004 decision 8; W6, the acknowledgement of an interrupted execution, was withdrawn by owner decision R31 on 2026-10-27: it is made in the chat, ADR 0004 decision 12). Opening the final test and changing the mode are chat acts: the panel explains them and offers no control.
- **v0.2 changes**: two-layer copy (the panel's own words for the junior; engine text for the agent only under "Details"); "Your next move" first at every stage; readable decision values ("Select the top 10% by score"); limits with severity, listed once; the final-test chip on every tab; **"Open in Marimo (read)"** (`marimo run` on the generated notebook) and **"Open in Marimo (edit)"** (`marimo edit` on the workbench), in a named VS Code terminal with an argument list (the only launches `check_layout.py` allows); Data & EDA (data card, quality, questions per chart, null band, look ledger, leakage detector); Evidence led by the final test and the exposure ledger, development evidence (CV, variant) apart from final evidence, diagnostics; What if? with share rules and the gain curve; the mode explainer; high-contrast borders, fixed-pixel charts, cards below 600 px.
- **One page (ADR 0004 decision 13, integrated 2026-10-27)**: the six tabs are replaced by one page ([PANEL-ONE-PAGE-PLAN](../plans/PANEL-ONE-PAGE-PLAN.md)): a sticky header and progress, To handle, Since your last visit, Now, the path with its ledger line, and the tools as drawers. The engine speaks contract P1 ([CLI-CONTRACT §17](../specs/CLI-CONTRACT.md)): `next_action.panel` version 2 names a place by an anchor (`now`, `todo:<kind>`, `path:<step>[/<slot>]`, `tools:<drawer>`), and `status --summary --digest` adds `panel_contract`, `automation`, `review_queue`, `defensibility`, `ledger`, `sample`, `headlines`, `criterion_configurations`, a result's `channel`, a proposal's `data_contingent`, and the texts of Now in both languages (the French ones with French typography). The step-1 data card shows eight development rows drawn from a seed, recorded once as a look at the target. The panel's fixtures are captured from the engine (`capture.py`, `one_page`); the one-page pixel baselines are not committed (the owner reviews them first) and the pixel tests skip until then.
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
