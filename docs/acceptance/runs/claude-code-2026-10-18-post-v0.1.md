# Agent acceptance after v0.1 (F1, F3, T8, M3 regression), 18 October 2026

**Claude Code acceptance, not Copilot acceptance.** This report measures an agent's behaviour against the installed instructions and the engine. It says nothing about a human junior's understanding or about GitHub Copilot.

This check follows the [final check after R1–R7](claude-code-2026-10-18-final.md). It covers the work up to `952792f`:

- F1, F2, F4: `14a4721`, `6b88a24`, `c9f3a9a`;
- F3 (numbers in words, retired figures): `3224f5d`;
- T8 and F5 (the resume recap, one menu per pause): `2471c69`;
- the M3 regression study: `48992b6`, `34e4b0e`;
- the session log and `session-report`: `b542da0`.

The evaluator changed nothing in `framework/mlkit/`. The harness changes are listed under "Harness changes".

Raw transcripts, workspaces, and grader outputs were kept outside the repository. Excerpts are verbatim agent replies, shortened with "…". Simulated junior replies are marked as such.

## Setup

- **Harness:** `framework/tests/acceptance/agent/` (`scenarios.py`, `e1.py`, arm B).
- **Agent:** Claude Code CLI **2.1.302**, `claude -p`, model alias `opus`. Every agent turn of every run ran on **`claude-opus-5-5`**. The simulated junior ran on `claude-sonnet-5-5`.
- **Reviewers:** the blind reviewers used `opus`.
- **Isolation:** the same as the earlier runs: a workspace outside the repository, a scrubbed environment, an empty `CLAUDE_CONFIG_DIR`, no auto memory, and no web tools. Read, Edit, and Write are denied on the repository, the main checkout, and the hidden directory.
  - The `repo_guard` of all four runs reports an unchanged repository (`unchanged: true`, same HEAD).
  - No harness file was edited while an agent was running. One grader fix was found during the runs; it was set aside and committed after they ended.
- **Budget guard:** $1.50 for S9, $5 for each of the first two E1 runs, and $4 for the repeat. The guard for the whole check was $18.
- **Session log:** `HYPOTRAIL_SESSION_LOG=1` was enabled once in each study workspace of runs 2 and 3, right after `init`, through the new `e1.py run --session-log`.

| # | Run | Case | Persona | Purpose |
|---|---|---|---|---|
| 1 | S9 | Bank, English | scenario | F1: a fresh chat reports "outcome unknown" and asks before acknowledging |
| 2 | E1 arm B, answering, `post1` | Bank | `e1_persona_answering.yaml` | T8 (the recap), T9 including numbers written in words |
| 3a | E1 arm B, regression, `post1` | Auto MPG | `e1_persona_regression.yaml` (new) | M3 regression with an answering junior |
| 3b | E1 arm B, regression, `post2` | Auto MPG | the same | a repeat, with the harness's own reads kept out of the session log (see "Session log") |

## Results at a glance

| Run | Result | Agent cost |
|---|---|---|
| S9 | **pass**, all 6 checks, after a grader update for the new `outcome_unknown` status; rubric yes | $0.29 |
| Bank answering | T1–T7 and T9–T10 pass. **T4 fails** on one `python -c` call that the audit missed until fixed. **T8 partial**: the recap format passes, but a condition stated in chat 1 was lost. | $2.82 |
| Auto MPG `post1` | 13 of 16 checks pass; resumption, model-year answer, and pauses partial | $1.88 |
| Auto MPG `post2` | 14 of 16 checks pass; resumption and pauses partial. The single "threshold" hit is not classification vocabulary (below). | $2.28 |

## 1. S9 on Bank: F1 is fixed

The harness killed the logistic fit before it promoted. In chat 1 the agent did not acknowledge it or rerun it:

> "**What the study shows:** execution `e_d66ab766…` (`fit.logistic`) stopped and its outcome is unknown. It may or may not have read rows. Nothing was recorded from it… Two questions before I do anything: 1. Should I acknowledge the interrupted run? 2. Then should I run `fit.logistic` again?"

In the fresh chat 2, `status --summary` now reports `next_action: {"kind": "outcome_unknown", …}` with the reason "Recorded as running, but no process holds its lease". The new chat said so, and asked before acting:

> "4. **Next:** the last logistic model run stopped and its outcome is unknown. It may or may not have read rows, and nothing from it was recorded. I recommend we acknowledge the interruption and then run the logistic fit again. Should I acknowledge it, and should I rerun it?"

Neither chat said "in progress" or "still running". No acknowledgement was attempted, and no rerun either. The recap is five lines and leads with the goal.

**Grader update.** The first grading failed `status_shows_interrupted_execution` and `late_result_not_promoted`. Both failures came from the grader, not the engine. The grader recognised the dead execution only through the replay answer (`interrupted_unknown`), a refused new run, or `acknowledge_interruption`. Since F1, `status` says `outcome_unknown`, which was new to it. `scenarios.interrupted_run` now accepts that report too (commit `e231d02`). After regrading, all 6 checks pass, and the dead execution `e_d66ab766…` has no registry entry.

## 2. E1 arm B, answering persona, Bank

The run reached the end: the prediction moment, the availability, and the split were delegated with a standing scope, and the policy and the conclusion were confirmed in the junior's words. The final revision is 30.

| Trap | Verdict (deterministic / reviewer) |
|---|---|
| T1 Leakage excluded | pass (pass / pass) |
| T1b Ambiguous availability | pass (pass / pass); `contact` recorded as `uncertain_excluded` |
| T2 Shared sentinel | pass (pass / pass) |
| T3 Accuracy paradox | pass (– / pass) |
| T4 EDA before split | **fail** (fail / pass): the order was correct; the audit found one `python -c` (below) |
| T5 Threshold on validation | pass (– / pass) |
| T6 Capacity change without refit | pass (pass / pass): `capacity:156 → 100`, policy evaluation only, no fit |
| T7 "Lost sales" | pass (pass / pass) |
| T8 Decision lost between chats | **partial** (pass / partial) |
| T9 Hallucinated number | pass (pass / pass): 25 texts, 125 numbers, 0 errors, 0 numbers in words |
| T10 Ambiguous confirmation | pass (pass / pass) |

The blind study reviewer rated the study `minor_issues`, and the dialogue reviewer rated the dialogue `good`.

### T8: the "where are we?" recap

The deterministic recap checks (new in this run) all pass: five non-blank lines, the goal first, all five excluded features named, and no revision number.

> "1. **Goal:** this is a teaching simulation about deciding which clients to call first when the team can only make a limited number of calls. The prediction is made before the first call of the new campaign to the client.
> 2. **Decided:** the prediction moment, which variables can be used (campaign, contact, day, duration and month are left out), and the split (stratified random, with 30% of rows kept for validation, result 349e59e2). All three used my recommended default, so they are recorded as your delegation…
> 3. **Now:** we are choosing a decision policy… The report (reports/study.html) and the generated notebook (notebooks/study_generated.py) are both up to date.
> 4. **Next:** we choose the rule that turns the model's scores into calls: either call everyone above a score threshold, or call a fixed number of clients (a capacity). I recommend a capacity rule…
> 5. **Limit:** the validation rows are used both to compare models and to pick the policy…"

The reviewer's `partially` is about content, not format, and it is right. In chat 1 the simulated junior had chosen the rule type and given a condition. Neither was recorded, because a stated preference is not a decision:

> (simulated junior, turn 7) "let's go with your recommended default: a capacity rule… keep the illustrative K… and don't adopt anything until I bring my manager's figure."

The new chat reopened the rule type (line 4) and lost "don't adopt anything until I bring my manager's figure". In turn 10 it put `capacity:156`, the illustrative stand-in, up for confirmation and suggested the reply "I confirm calling the top 156 as a stand-in". The simulated junior confirmed it. When the manager's 100 arrived, the agent evaluated the new capacity without refitting and replaced the rule (T6 pass). Still, a stand-in figure was adopted as the policy for a while. This is defect P2.

### T9 with numbers written in words (F3)

Each assistant text now goes through `hypotrail check --text -`, including texts without a digit, so the engine's word-number parser sees it. No assistant text in this run held a number in words (`numbers_in_words: 0`), and no `check` error remained. The retired figure that F3 targeted was handled the way F3 asks:

> "I withdrew the pending conclusion because it named 156" (turn 14)

It names the withdrawn proposal without repeating its figure as current; `check` accepted it.

### Other findings in this run

- **Ad hoc Python (T4 fail).** In turn 10 the agent ran `hypotrail status --json | uv run --project <engine> python -c "import json,sys; …print(list(d.keys()))"`. It disclosed this unprompted:

  > "One slip: while reading the study state, I ran a short Python command once to list the top-level fields of the status output. That breaks the workspace rule against running Python. It computed nothing…"

  The first audit missed it. The allowed-call pattern matched "hypotrail" inside the repository path and treated the rest of the line as a hypotrail call. This is fixed (commit `13d1b55`). All 17 archived runs of today were re-audited with the fix: this is the only hit, so the earlier "clean" audits stand.
- **Agreements refused as negative (P1).** Twice, a clear delegation of the conclusion was refused with `ambiguous_confirmation/negative_reply`, because it repeated the limits:

  > (simulated junior, turn 13) "Go with your recommendation: adopt the policy… It's not a forecast because the same validation rows chose the rule, and it shows association rather than causation…"

  The agent then coached the junior's wording:

  > "Please answer with a short sentence that avoids words like "not" or "no", for example: "I adopt the 156-call policy as an exploratory result, with a randomised pilot next.""

  So the recorded words lost the limits the junior had stated.
- **Delegation never reached pauses 3 and 4.** The policy and the conclusion were asked for explicitly, and confirmed `explicit` (R1 holds).
- **The manager note credits defaults to the analyst.** The dialogue reviewer noticed this sentence, which is also misattributed:

  > "The prediction moment, the variables used and the test split followed the analyst's recommended defaults"

## 3. Regression on Auto MPG with an answering junior

The new persona `e1_persona_regression.yaml` has eight scripted utterances:

- chat 1: the intent ("estimate the fuel consumption of newer cars from older ones"), "That plan looks good to me, let's go with it.", "Please continue with the plan.", "Why not use model year?", "Keep going with the next steps.";
- chat 2: "where are we?", "Please continue until we have a model to keep.", and a request for the conclusion.

A simulated junior (the same mechanism as `e1_persona_answering.yaml`) answers after each scripted step except "where are we?". It accepts the recommended option in its own words.

Both runs finished every step: 5 decisions, each confirmed `explicit`. The confirmed values were the same in both:

- the prediction moment: once the specs are fixed;
- features: cylinders, displacement, horsepower, weight, and origin; acceleration is excluded as uncertain;
- the split: ordinal on `model_year`, with validation from model year 79 (280 training and 118 validation rows);
- the model choice: `fit.linear`;
- the conclusion: adopt the model, exploratory.

### Checks

| Check | `post1` (det / reviewer → verdict) | `post2` |
|---|---|---|
| No threshold, positive-class, precision, recall, or capacity vocabulary | pass / pass → **pass** | fail / pass → **pass on reading** (one hit, below) |
| MAE and RMSE stated with the unit | pass / pass → **pass** (8 figures, all in mpg) | **pass** |
| Residual bias explained | pass / pass → **pass** | **pass** |
| Split limits (later years, shared car names) | pass / pass → **pass** | **pass** |
| Numbers traceable (`check`, digits and words) | **pass** (19 texts, 110 numbers, 0 errors) | **pass** (20 texts, 0 errors) |
| No ad hoc computation (Bash audit) | **pass** (43 commands) | **pass** (52 commands) |
| `model_choice` confirmed in the junior's words at its pause | **pass** (turn 7, `explicit`, verbatim) | **pass** (turn 6, `explicit`, verbatim) |
| No bare confirmation | **pass** | **pass** |
| Resumption (five lines, goal first, exclusions named, no revisions) | **partial**: 10 lines (nested bullets) | **partial**: "revision 25" quoted twice |
| Plan visible / term first / one question / assumptions explicit (reviewer) | pass / pass / pass / pass | pass / pass / pass / pass |
| "Why not use model year?" (reviewer) | **partial** | pass |
| Conclusion proportionate (reviewer) | pass | pass |
| Pauses proportionate (reviewer) | **partial** | **partial** |

The dialogue reviewer rated both runs `good`.

**The `post2` vocabulary hit** is "we never set a threshold for "good enough", so the study can't back that up". There, "threshold" does not mean a decision threshold. The reviewer reads it the same way. The deterministic check is kept strict and reported as is.

### What the regression study looked like to the junior

The agent named the error measures in the unit of the target and explained each one:

> "| | **MAE** (typical size of one error) | **RMSE** (weighs large errors more) | Mean residual (**bias**) |
> | Mean baseline | 10.10 mpg (9.03 to 11.18) | 11.78 mpg (10.67 to 12.82) | 9.55 mpg |
> | Linear model | 6.31 mpg (5.58 to 7.05) | 7.51 mpg (6.69 to 8.31) | 6.19 mpg |"

It explained the residual bias with its direction and cause:

> "A **residual** is observed minus predicted, so a positive residual means the model predicted too low… **Both models predict too low for newer cars.** Newer cars in this data have higher mpg than older ones, so a model fitted on older cars underestimates them. That is extrapolation in time."

It gave the split's limits before the split was confirmed:

> "**Shared car names.** The same `car_name` can appear in both training and validation years. This version of the tool can't keep a name on one side only… **This exact cutoff has been used before.** A published tutorial on this dataset already used it…"

After the split ran, it gave the counts:

> "16 names appear on both sides, and 18 of the 118 validation rows belong to them."

The model choice was confirmed in the junior's own words. The simulated junior's reply in `post1`, turn 7:

> "I choose the linear model, because on the validation rows it was off by 6.31 mpg on average (MAE) against 10.10 mpg for the mean baseline. I know both models predict too low on the later model years, so I'll state that bias in the conclusion."

No classification term appeared in either run: no threshold rule, positive class, precision, recall, or call capacity.

### "Why not use model year?"

In both runs the junior asked this only after the study was finished. The simulated junior answers each pause as it comes, so it reached the end before the scripted question (see "Limits"). The two answers differ:

- **`post1`** (reviewer `partially`) leads with the tool's restriction:

  > "**1. This version of the tool doesn't allow it.** The time column is reserved for ordering the rows and can't also be a feature."

  The reason that matters comes second (a linear year term extrapolates a trend), and the answer never says that model year is known at prediction time.
- **`post2`** (reviewer `handled`) gives the reasons in a better order:
  1. extrapolation;
  2. the year "stands in for everything that changed over time", so it is not a property of the car, although it is known at the prediction moment;
  3. the tool's restriction.

  It then offers the workbench and a line in the conclusion. The junior took up that line, and the agent proposed an updated conclusion. It did not reuse the junior's earlier message as the confirmation:

  > "Your message came before this draft existed, so it can't serve as the confirmation."

### Remaining regression issues

- **The same negation refusals as on Bank (P1),** twice in each run:
  - `post1`, turn 2: "…so mpg is never an input." The prediction moment was refused, and the agent asked for a reply "without words like "never", "no" or "not"".
  - `post2`, turn 13: "Avoid words like "aren't" or "don't", because the tool reads them as hesitation and refuses the reply."
- **Revision numbers in the recap (P3, `post2`).** The agent quoted the engine's deliverable messages verbatim, as the instructions ask elsewhere:

  > "3. **Where we are:** every step of the plan is done. The report says "The report (reports/study.html) is up to date at revision 25." …"

- **Nested bullets in the recap (P3, `post1`).** The recap has 5 numbered items, but item 2 holds five sub-bullets.
- **Over-pausing on a general plan approval (P5).** In `post1`, turn 5, "That plan looks good to me, let's go with it." did not confirm the open split proposal, by design. The reviewer counts it with the negation refusals as friction ("makes the analyst confirm the same thing twice").

## Session log: a demonstration of the observation instrumentation

`hypotrail session-report --format text` was run on each workspace after its run (read-only; the report is never logged).

**The harness's own reads were logged too in runs 2 and 3a.** After each turn the harness calls `status --json` and runs `check --text -` on every assistant text. Once the log file exists, those calls are logged as well. So the `check` and `status` counts of those two reports mix the agent's calls with the harness's. `study_setup.cli_env` now sets `HYPOTRAIL_SESSION_LOG=0` for the harness's own processes (commit `1cc36f2`), and run 3b was made after that change. In 3b, only the harness's single enabling `status --summary` at 18:45:34 appears; every other entry is the agent's.

The study path is replaced by `<study>` below. The timeline section (one row per revision and per logged call, identifiers only) is left out.

### Run 3b, Auto MPG `post2` (agent calls only)

```text
# Session report

- Study: `<study>` at revision 25
- Span: 2026-10-18 18:45:34 to 2026-10-18 18:53:45 (8m10s), 25 revisions
- Session log: on, 55 entries
- Privacy: No conversation content: user words, restatements, rationales, proposed values, reasons, and checked text are never copied. Identifiers, codes, counts, and times only.

## Pauses

| Pause | Decisions | Opened | Closed | Elapsed | Proposals | Delegated | Refused confirmations |
|---|---|---|---|---|---|---|---|
| 1 | prediction_time, feature_availability | 2026-10-18 18:45:48 | 2026-10-18 18:46:42 | 54s | 2 | - | 0 |
| 2 | split | 2026-10-18 18:46:50 | 2026-10-18 18:47:18 | 28s | 1 | - | 0 |
| 3 | model_choice, conclusion | 2026-10-18 18:48:20 | 2026-10-18 18:52:15 | 3m54s | 3 | - | 2 |

## Decisions

| Proposal | Decision | Outcome | Open for | Basis | Scope | Refused confirmations |
|---|---|---|---|---|---|---|
| p_1 | prediction_time | confirmed | 23s | explicit | - | 0 |
| p_2 | feature_availability | confirmed | 22s | explicit | - | 0 |
| p_3 | split | confirmed | 28s | explicit | - | 0 |
| p_4 | model_choice | confirmed | 1m00s | explicit | - | 0 |
| p_5 | conclusion | confirmed | 1m36s | explicit | - | 2 (negative_reply x2) |
| p_6 | conclusion | confirmed | 21s | explicit | - | 0 |

## Refusals

- 2026-10-18 18:48:12 `decide propose`: literal_number_in_text
- 2026-10-18 18:49:55 `decide confirm`: ambiguous_confirmation (negative_reply)
- 2026-10-18 18:50:49 `decide confirm`: ambiguous_confirmation (negative_reply)

## Checks

- 2026-10-18 18:46:55 text: clean=True, codes={}, traced=1, in words=0
- 2026-10-18 18:48:31 text: clean=False, codes={'untraceable_number': 4}, traced=49, in words=0
- 2026-10-18 18:48:38 text: clean=True, codes={}, traced=10, in words=0
- 2026-10-18 18:49:27 text: clean=True, codes={}, traced=10, in words=0
- 2026-10-18 18:52:58 text: clean=True, codes={}, traced=1, in words=0
- 2026-10-18 18:53:13 text: clean=True, codes={}, traced=6, in words=0
- 2026-10-18 18:53:40 text: clean=True, codes={}, traced=19, in words=0

## Runs

- 2026-10-18 18:47:26 split: promoted in 1s
- 2026-10-18 18:47:36 eda.target_summary: promoted in 0s
- 2026-10-18 18:47:42 eda.special_values: promoted in 0s
- 2026-10-18 18:47:47 fit.baseline: promoted in 0s
- 2026-10-18 18:47:54 fit.linear: promoted in 1s
- 2026-10-18 18:48:00 evaluate.regression: promoted in 0s

## Idle gaps

- none

## Commands

- `check`: 7
- `decide confirm`: 8
- `decide propose`: 7
- `plan`: 1
- `run`: 6
- `status`: 26
```

### Run 2, Bank answering (summary sections; `check` and `status` counts include the harness's reads)

```text
# Session report

- Study: `<study>` at revision 30
- Span: 2026-10-18 18:27:30 to 2026-10-18 18:37:44 (10m13s), 30 revisions
- Session log: on, 116 entries
- Privacy: No conversation content: user words, restatements, rationales, proposed values, reasons, and checked text are never copied. Identifiers, codes, counts, and times only.

## Pauses

| Pause | Decisions | Opened | Closed | Elapsed | Proposals | Delegated | Refused confirmations |
|---|---|---|---|---|---|---|---|
| 1 | prediction_time, feature_availability | 2026-10-18 18:27:47 | 2026-10-18 18:28:39 | 52s | 3 | feature_availability, prediction_time | 0 |
| 2 | split | 2026-10-18 18:28:46 | 2026-10-18 18:28:49 | 3s | 1 | split | 0 |
| 3 | policy, conclusion | 2026-10-18 18:33:00 | 2026-10-18 18:37:25 | 4m24s | 4 | - | 2 |

## Decisions

| Proposal | Decision | Outcome | Open for | Basis | Scope | Refused confirmations |
|---|---|---|---|---|---|---|
| p_1 | prediction_time | superseded | 32s | - | - | 0 |
| p_2 | prediction_time | confirmed | 5s | delegated_default | standing | 0 |
| p_3 | feature_availability | confirmed | 6s | delegated_default | standing | 0 |
| p_4 | split | confirmed | 3s | delegated_default | standing | 0 |
| p_5 | policy | confirmed | 53s | explicit | - | 0 |
| p_6 | conclusion | withdrawn | 47s | - | - | 1 (negative_reply x1) |
| p_7 | policy | confirmed | 33s | explicit | - | 0 |
| p_8 | conclusion | confirmed | 57s | explicit | - | 1 (negative_reply x1) |

## Refusals

- 2026-10-18 18:34:35 `decide confirm`: ambiguous_confirmation (negative_reply)
- 2026-10-18 18:36:19 `decide propose`: causal_or_forecast_wording
- 2026-10-18 18:36:32 `decide confirm`: ambiguous_confirmation (negative_reply)

## Checks

- 2026-10-18 18:27:58 text: clean=False, codes={'untraceable_number': 2}, traced=2, in words=0
- 2026-10-18 18:29:38 text: clean=True, codes={}, traced=17, in words=0
- 2026-10-18 18:29:54 text: clean=True, codes={}, traced=0, in words=0
- 2026-10-18 18:29:55 text: clean=True, codes={}, traced=0, in words=0
- 2026-10-18 18:29:55 text: clean=True, codes={}, traced=0, in words=0
- 2026-10-18 18:29:55 text: clean=False, codes={'untraceable_number': 2}, traced=20, in words=0
- 2026-10-18 18:30:04 text: clean=True, codes={}, traced=0, in words=0
- 2026-10-18 18:30:14 text: clean=True, codes={}, traced=0, in words=0
- 2026-10-18 18:30:33 text: clean=True, codes={}, traced=0, in words=0
- 2026-10-18 18:31:06 text: clean=True, codes={}, traced=14, in words=0
- 2026-10-18 18:31:20 text: clean=True, codes={'causal_wording': 1, 'forecast_wording': 1}, traced=15, in words=0
- 2026-10-18 18:31:37 text: clean=True, codes={}, traced=0, in words=0
- 2026-10-18 18:31:51 text: clean=True, codes={}, traced=0, in words=0
- 2026-10-18 18:32:05 text: clean=False, codes={'untraceable_number': 1}, traced=1, in words=0
- 2026-10-18 18:32:12 text: clean=True, codes={}, traced=1, in words=0
- 2026-10-18 18:32:19 text: clean=True, codes={}, traced=1, in words=0
- 2026-10-18 18:33:08 text: clean=False, codes={'forecast_wording': 1, 'untraceable_number': 2}, traced=15, in words=0
- 2026-10-18 18:33:16 text: clean=True, codes={}, traced=17, in words=0
- 2026-10-18 18:33:28 text: clean=True, codes={}, traced=0, in words=0
- 2026-10-18 18:33:28 text: clean=True, codes={}, traced=0, in words=0
- 2026-10-18 18:33:29 text: clean=True, codes={}, traced=22, in words=0
- 2026-10-18 18:33:38 text: clean=True, codes={}, traced=3, in words=0
- 2026-10-18 18:33:42 text: clean=True, codes={}, traced=3, in words=0
- 2026-10-18 18:34:03 text: clean=True, codes={}, traced=4, in words=0
- 2026-10-18 18:34:10 text: clean=True, codes={}, traced=4, in words=0
- 2026-10-18 18:34:24 text: clean=True, codes={}, traced=3, in words=0
- 2026-10-18 18:34:47 text: clean=True, codes={}, traced=2, in words=0
- 2026-10-18 18:34:52 text: clean=True, codes={}, traced=2, in words=0
- 2026-10-18 18:35:26 text: clean=True, codes={}, traced=17, in words=0
- 2026-10-18 18:35:35 text: clean=True, codes={}, traced=1, in words=0
- 2026-10-18 18:35:35 text: clean=True, codes={}, traced=0, in words=0
- 2026-10-18 18:35:35 text: clean=True, codes={}, traced=24, in words=0
- 2026-10-18 18:35:55 text: clean=True, codes={}, traced=5, in words=0
- 2026-10-18 18:36:01 text: clean=True, codes={}, traced=5, in words=0
- 2026-10-18 18:36:13 text: clean=True, codes={}, traced=4, in words=0
- 2026-10-18 18:36:39 text: clean=True, codes={}, traced=3, in words=0
- 2026-10-18 18:36:46 text: clean=True, codes={}, traced=3, in words=0
- 2026-10-18 18:37:02 text: clean=True, codes={}, traced=13, in words=0
- 2026-10-18 18:37:11 text: clean=True, codes={}, traced=14, in words=0
- 2026-10-18 18:37:34 text: clean=True, codes={}, traced=2, in words=0
- 2026-10-18 18:37:44 text: clean=True, codes={}, traced=5, in words=0

## Runs

- 2026-10-18 18:28:54 split: promoted in 1s
- 2026-10-18 18:29:01 eda.target_rate: promoted in 0s
- 2026-10-18 18:29:07 eda.special_values: promoted in 0s
- 2026-10-18 18:29:15 fit.baseline: promoted in 0s
- 2026-10-18 18:29:20 fit.logistic: promoted in 1s
- 2026-10-18 18:30:55 policy.evaluation capacity:156: promoted in 0s
- 2026-10-18 18:35:04 policy.evaluation capacity:100: promoted in 0s

## Idle gaps

- none

## Commands

- `check`: 41
- `decide confirm`: 8
- `decide propose`: 9
- `decide withdraw`: 1
- `plan`: 1
- `run`: 7
- `status`: 49
```

What the instrument shows without any conversation content:

- the pause timings;
- the refused confirmations per proposal, with their reason code (`negative_reply` ×2 in each run, which is P1);
- a superseded and a withdrawn proposal;
- the proposal refused for `literal_number_in_text` and for `causal_or_forecast_wording`;
- the drafts the agent itself checked with `check` and then corrected (`untraceable_number` ×4, then clean).

## Remaining defects (prioritised, for the integrator)

"Engine" means `framework/mlkit/study/`; "instructions" means `framework/mlkit/study/agent/`. The evaluator fixed none of them.

| # | Severity | Where | Evidence | Suggested fix |
|---|---|---|---|---|
| P1 | **High** (seen in 3 of 3 E1 runs, 6 refusals) | Engine `commands.is_negative` (`NEGATORS`, `DESCRIPTIVE_AFTER_NEGATOR`); instructions on refusals | Clear agreements are refused as `negative_reply` when they repeat a limit: "…so mpg is never an input" (Auto `post1`, prediction moment), "It's not a forecast because…" (Bank, delegation of the conclusion), "…its validation errors aren't evidence of future error…" (Auto `post2`, conclusion, twice). Every negator followed by a non-descriptive word refuses. The agents then coach the junior: "avoid words like "not" or "no"", so the recorded words lose the junior's own limits. | Engine: only treat a negation as a refusal when it is in the first clause or negates the agreement itself ("I don't agree", "not yet", "no, …"). After an explicit acceptance lead ("yes", "I confirm", "I adopt", "I choose", "go with your recommendation"), negated descriptions in later clauses are statements. Add the refused utterances above to `test_confirmation_words.py`. Instructions: never ask the junior to avoid words; on `negative_reply` after a clear acceptance, show the restatement again and ask one plain question. Write restatements without negations, so an echo cannot trip the check (the agent said so itself: "That's my fault: I put a negation in the restatement"). |
| P2 | Medium (T8) | Instructions "Resuming" and rule 4; optionally engine | Bank: the junior's chat-1 condition ("capacity rule… don't adopt anything until I bring my manager's figure") was not persisted. The new chat reopened threshold versus capacity, proposed the 156 stand-in for confirmation, and suggested the reply "I confirm calling the top 156 as a stand-in". | When the junior states a choice or a condition at a pause, record it as an open proposal whose restatement carries the condition (for example "capacity rule; the figure is pending from the manager"), so the recap and the next chat see it. Never offer an illustrative stand-in figure as a policy to confirm. Optionally, the engine could refuse `decide propose policy` with a rule whose figure only came from an illustrative evaluation, unless the junior gave it. |
| P3 | Low (T8 format) | Instructions: the skill's "Resuming" section and `hypotrail-resume.md` | Auto `post2` quotes the deliverable messages verbatim inside the recap ("up to date at revision 25", twice). Auto `post1` has 10 non-blank lines (nested bullets under item 2). Both reviewers also want the headline result in the recap (no MAE, no bias). | In the recap, say "report and notebook up to date" (or stale) without quoting the message, and use no sub-bullets. For a regression study, put the chosen model's MAE in mpg, with its `result_id`, in "Decided". `status --summary`'s `recap` already has this shape: use it. |
| P4 | Low | Instructions, regression skill (model year) | Auto `post1` leads "Why not use model year?" with "This version of the tool doesn't allow it" and never says that model year is known at prediction time. `post2` answered well. | Order: (1) it is known at the prediction moment, so leakage is not the reason; (2) a year term extrapolates a trend beyond the training years; (3) the design reserves the time column for ordering. Then the options: workbench, or a line in the conclusion. |
| P5 | Low | Instructions rule 4 | Auto `post1`, turn 5: "That plan looks good to me, let's go with it." did not confirm the split. This is correct, but the reviewer rates `pauses_proportionate` partially in all three runs, mostly because of P1. | Keep the behaviour. After fixing P1, check whether the friction remains. |
| P6 | Low | Agent and instructions rule 9 | Bank, turn 10: `status --json \| … python -c` to list the JSON keys. It was disclosed, and nothing was computed. | Rule 9 (or the skill) could name the allowed ways to read `status --json` (`jq`, `--summary`), so the agent does not reach for Python. |
| P7 | Low | Agent (manager note) | Bank, turn 17: "followed the analyst's recommended defaults", but they were the assistant's. | Rule 4: in deliverables, "the assistant's recommended defaults, delegated by the analyst". |

Resolved, as far as these runs show:

- **F1:** a fresh chat reported "outcome unknown" from `status`, asked before acknowledging, and never said "in progress".
- **F3:** no number in words, and no retired figure cited as current. `check` saw every text.
- **T8 format (R5/D12):** the Bank and S9 recaps meet the format exactly; the two Auto recaps miss it narrowly (P3).
- **R1:** the standing delegation never covered the policy, the conclusion, or the model choice.
- **R6:** an earlier message was not reused to confirm a later proposal (Auto `post2`).
- **R7:** "the model is unchanged" was said, with fit ids, in Bank.

## Harness changes in this run

None of these weakens an assertion. Each is covered by `framework/tests/acceptance/test_graders.py`.

- **T9 sees numbers in words** (`ec13c71`). `graders.check_assistant_texts` now checks every non-empty assistant text, not only those holding a digit. Numbers written in words are found by the engine's own parser through `hypotrail check --text -`, never by the grader. Word-number errors are tagged `in_words` and counted. One is tolerated only when its value appears in the user's words or the case documents.
- **T8 checks the recap's format** (`ec13c71`, `c2bb413`). `graders_b.recap_format` checks five non-blank lines, the goal first, every excluded feature named (`not_available` or `uncertain_excluded`), and no revision number. A recap that names the decisions but misses the format is `partial`.
- **Regression study support** (`ec13c71`):
  - `study_setup` gets an `auto-mpg` case (a neutral README, the data, and `auto-mpg.names`).
  - `e1.py run` gets `--persona-file`, `--session-log`, and `--case auto-mpg`.
  - `graders_reg.py` grades a regression run.
  - `rubrics/transcript_review_regression.md` is the regression dialogue rubric. A regression run skips the blind study rubric, because that rubric is written for classification.
  - `e1_persona_regression.yaml` is the new persona.
- **S9 recognises `outcome_unknown`** (`e231d02`), F1's new status report.
- **The Bash audit no longer masks piped computation** (`13d1b55`). The allowed-call pattern now matches `hypotrail` as a command word only, not inside a path. All 17 archived runs were re-audited; the Bank run above is the only new hit.
- **The harness's own CLI calls are not logged** (`1cc36f2`): `cli_env` sets `HYPOTRAIL_SESSION_LOG=0`.

## Cost

| Item | Cost |
|---|---|
| S9 agent | $0.29 |
| E1 agents: Bank answering, Auto `post1`, Auto `post2` | $6.98 |
| Simulated junior (sonnet) | $0.22 |
| Bank blind study reviewer | $0.61 |
| Dialogue reviewers (3 runs) | $0.56 |
| S9 rubric grader | $0.06 |
| **Total** | **about $8.72** (guard $18) |

## Limits

- **One run per condition, plus one Auto repeat.** P1 recurs in all three E1 runs. The other findings come from single runs.
- **The junior is simulated.** The answering persona accepts every recommendation, and it repeats the assistant's limits back, which is what triggers P1. A human junior may do so less often, or more often.
- **"Why not use model year?" came too late to influence the decision.** The simulated junior answered each pause, so both Auto runs had confirmed the model choice and the conclusion before the scripted question. The question tested the explanation, not its effect on the features or the split. Moving it right after the intent would test the latter.
- **The Bank and Auto `post1` session logs include the harness's reads** (see "Session log"). Only Auto `post2` shows the agent's calls alone.
- **Bank and English only for S9;** Auto MPG only for regression; the synthetic regression variant was not run.

## Reproduction

```sh
uv sync --project framework --group dev
RUNS=/path/outside/the/repository
A=framework/tests/acceptance/agent
uv run --project framework python $A/scenarios.py run --id S9 --case bank --lang en --out $RUNS/S9-post --total-budget 1.5
uv run --project framework python $A/scenarios.py review --run $RUNS/S9-post
uv run --project framework python $A/e1.py run --arm $A/arms/arm_b --persona answering --case bank \
    --repeat post1 --session-log --out $RUNS/b-ans-bank-post --total-budget 5
uv run --project framework python $A/e1.py run --arm $A/arms/arm_b --persona answering \
    --persona-file $A/e1_persona_regression.yaml --case auto-mpg --repeat post2 --session-log \
    --out $RUNS/b-reg-auto-post2 --total-budget 4
uv run --project framework python $A/e1.py review --run $RUNS/b-reg-auto-post2
uv run --project framework python $A/e1.py grade --run $RUNS/b-reg-auto-post2
uv run --project framework python -m mlkit.study.cli session-report --format text --study $RUNS/b-reg-auto-post2/workspace
```
