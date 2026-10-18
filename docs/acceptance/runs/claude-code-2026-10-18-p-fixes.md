# Agent acceptance of the post-v0.1 fixes (P1–P7, G.12), 18 October 2026

**Claude Code acceptance, not Copilot acceptance.** This report measures an agent's behaviour against the installed instructions and the engine. It says nothing about a human junior's understanding or about GitHub Copilot.

This check follows the [post-v0.1 check](claude-code-2026-10-18-post-v0.1.md). It covers the fixes recorded as PV.1–PV.12 in [V0.1-DECISIONS.md](../../plans/V0.1-DECISIONS.md), up to `3a6145f`.

The evaluator changed nothing in `framework/mlkit/`. The harness changes are listed under "Harness changes". Raw transcripts, workspaces, and grader outputs were kept outside the repository. Excerpts are verbatim agent replies, shortened with "…". Simulated junior replies are marked as such.

## Setup

- **Harness:** `framework/tests/acceptance/agent/` (`e1.py`, arm B).
- **Agent:** Claude Code CLI **2.1.302**, `claude -p`, model alias `opus`. Every agent turn of every run ran on **`claude-opus-5-5`**. The simulated junior ran on `claude-sonnet-5-5`. The blind reviewers used `opus`.
- **Isolation:** the same as the earlier runs: a workspace outside the repository, a scrubbed environment, an empty `CLAUDE_CONFIG_DIR`, no auto memory, and no web tools. Read, Edit, and Write are denied on the repository, the main checkout, and the hidden directory.
  - The `repo_guard` of all four runs reports an unchanged repository (`unchanged: true`, same HEAD).
  - The harness changes were committed before the runs (`c2211e6`). One persona file was added between runs, never while an agent was running.
- **Session log:** on in every run (`--session-log`).
- **Budget guard:** about $12 for the whole check.

| # | Run | Case | Persona | Purpose |
|---|---|---|---|---|
| 1 | `bank-cond` | Bank | `e1_persona_conditions.yaml` (new) | P1 caveated agreements, P2 a condition stated at a pause, P3, P6, P7, T6, T9 |
| 2 | `auto-early` | Auto MPG | `e1_persona_regression_early.yaml` (new) | P4 "why not use model year?" right after the intent, P5 "plan looks good", PV.5 recap MAE |
| 3a | `syn-small` | synthetic, 60 rows | `e1_persona_answering.yaml` | G.12 warnings in plain words |
| 3b | `syn-small-30` | synthetic, 60 rows | `e1_persona_small.yaml` (new) | G.12 again, with the junior asking for a 30% validation share |

**The 60-row case.** `make_case` refuses fewer than 100 rows. As in `test_perturbations.py`, the new `synthetic-small` case generates 100 rows and keeps the first 60. It updates the row count and checksum of the case contract.

**Why 3b.** In 3a the agent chose a 50% validation share by itself. That gave 30 validation rows with 7 positives. Both are exactly at the thresholds of PV.10 (fewer than 30 rows, fewer than 5 positives), so no warning was raised. Run 3b changes one sentence of the plan approval ("For the split, keep 30% of the rows for validation, as our team always does"). That leaves 18 validation rows with 4 positives.

## Results at a glance

| Item | Result | Evidence |
|---|---|---|
| **P1** caveated agreements | **pass** | 0 `negative_reply` refusals in 4 runs (6 in the previous check). 0 hits for wording coaching. |
| **P2** condition recorded as a hold | **pass**, one new defect (D1) | Recorded verbatim at once. It survived the new chat and was quoted in the recap. It was resolved with the junior's words when the figure came. No confirmation was made while it was open. |
| **P3** recap | **pass** | All 4 recaps: 5 flat lines, the goal first, every exclusion named, no revision number. |
| **P4** model-year answer order | **pass** (reviewer: partial) | The answer goes: known at prediction time, then extrapolation, then the design restriction, then the options. |
| **P5** "plan looks good" | **pass** (reviewer: partial on friction) | No extra pause between the defined pauses in any run. |
| **P6** status reads | **pass** | 13–19 `status --summary` reads per run. No `python` pipe. `jq` was used (allowed). |
| **P7** credit for delegated defaults | **pass** | Bank: conclusion, manager note, and the engine record all say "the assistant's recommended defaults, delegated by the analyst". The engine's regex found nothing. |
| **PV.5** regression recap MAE | **pass** | "validation MAE of 6.31 mpg (result 142ac050)". `142ac050` is the current `evaluate.regression` result. |
| **G.12** warnings in plain words | **pass in 3b**; not raised in 3a (D4) | Both warnings were explained in plain words. No identifier was shown. |
| T6 capacity change without refit | **pass** (Bank, 3a, 3b) | Bank: `capacity:100` is a new policy evaluation only, with no fit command. |
| T9 traceable numbers | **pass** (Bank, Auto, 3a); **fail** in 3b | 3b: one "seven columns" (a count in words) twice, see D8. |

| Run | E1 traps / regression checks | Blind study review | Dialogue review | Agent cost |
|---|---|---|---|---|
| `bank-cond` | 9 pass, T1b and T8 partial | `minor_issues` | `good` | $2.29 |
| `auto-early` | 13 pass, 4 partial (units, assumptions, model year, pauses) | (skipped for regression) | `good` | $1.94 |
| `syn-small` | 10 pass, T8 partial | `minor_issues` | `good` | $2.09 |
| `syn-small-30` | 8 pass, T3 and T5 unclear (no blind review), T9 fail | (not run, budget) | `good` | $2.40 |

## 1. Bank with a stated condition and caveated agreements

### P1: agreements that state limits are accepted

The simulated junior's sheet asks it to add one limit with a negation whenever it accepts. Both decisions at pause 3 were confirmed in those words, verbatim, on the first try:

> (simulated junior, turn 13, policy) "Yes, adopt it: the team calls the 100 clients with the highest logistic scores. It's not a forecast of what the next campaign will produce, and the figures are a bit optimistic because we used the same validation rows to compare the rules."

> (simulated junior, turn 14, conclusion) "I confirm: the team adopts the 100-call rule ranked by the logistic model, with a randomised pilot as the next step. This is an exploratory result on past rows, so it isn't a forecast for the next campaign and doesn't show that calling caused the subscriptions."

The session report lists "Refusals: none recorded". No assistant text asked the junior to avoid a word. Across the four runs, 5 caveated agreements confirmed 6 decisions verbatim, and none was refused.

### P2: the condition becomes a hold that survives the new chat

The junior raised the condition twice in chat 1. First the simulated junior said it on its own (turn 5), then the scripted step said it (turn 7). Each time the agent recorded it with `decide note --about policy`, verbatim:

> "I've recorded your condition word for word alongside the earlier one: *"Keep going, but about how many people we call: don't adopt anything until I bring my manager's figure."* The study will refuse to adopt a calling rule until your own words lift it…"

Both notes were open at the start of chat 2. The fresh chat's recap quoted them in its `Next` line:

> "4. **Next:** choosing the policy. I recommend a capacity rule set to the number of calls the team can make. You put this on hold in your own words: "I'm still waiting for my manager's figure…" and "Keep going, but about how many people we call: don't adopt anything until I bring my manager's figure." Nothing gets adopted until you bring that figure."

The illustrative capacities (136 and 271) were never proposed. On "keep that" the agent said:

> "The two limits I showed, 136 and 20.0% of the validation rows, were examples for comparison. Neither is the team's real limit."

When the figure came ("Here is my manager's figure: the team can make only 100 calls…"), the agent did three things. It resolved both notes with those words (`decide note --resolve`). It evaluated `capacity:100` without refitting (T6 pass). It then proposed the rule. The grader's checks `recorded_at_once`, `verbatim`, `open_in_new_chat`, `no_confirmation_while_open`, and `resolved_in_junior_words_after_figure` all pass.

**New finding (D1).** In turn 17 the simulated junior contradicted itself: "I'm still waiting for my manager's figure…, so the 100 isn't confirmed". This came from the persona sheet (see "Limits"), but a human junior can do the same. The agent recorded a third note on the already confirmed policy and said honestly:

> "The study summary and the report now show the policy as on hold. The engine still lists the 100-call rule as confirmed until you resolve that condition."

The blind reviewer: "the state file and HTML report still show policy and conclusion as confirmed and done; only the manager note says 'provisional'." The dialogue reviewer: "the record no longer agrees with itself."

### P3, P6, P7

- **P3:** the recap above is five flat lines with no revision number. All five exclusions are named. The dialogue reviewer rated it `partially` because it carries no result (no precision, no AUC). See D10.
- **P6:** 19 `status --summary` reads and two `status --json | jq` reads. No Python.
- **P7:** all three framing decisions were delegated. Every mention credits them correctly. In the manager note:

  > "**Who decided what:** the call rule and the conclusion are the analyst's decisions, using your call limit. The prediction moment, the choice of usable variables and the train/validation split are the assistant's recommended defaults, delegated by the analyst."

  The confirmed conclusion in the record says the same.

### Other observations

- **T1b partial** (reviewer): `case.yaml` lists availability `unknown` for several client-file columns, and the delegated default set them all to available without flagging this. This is the same finding as in earlier runs.
- **Vocabulary:** "recall" is used without a definition, and "stratified" and "paired difference" are not explained (reviewer, `term_first_vocabulary: partially`).
- **The manager note was saved as a file** (`notes/manager_conclusion.md`) at the junior's request, inside the study folder (rule 10 allows it).

## 2. Auto MPG with "why not use model year?" asked early

### P4: the answer order

The question came right after the plan, while the prediction moment was open:

> "**1. Leakage isn't the reason.** A new car's model year is known as soon as its specifications are fixed… **2. Extrapolation.** We'll train on older model years and check the model on newer ones. A year input would learn a trend from the training years… **3. The tool's design.** This version of the tool uses the time column only to put the rows in order…
> If you'd like to see the effect of adding the year, there are two options… `notebooks/workbench.py`… or list it in the conclusion as a next check.
> Back to the open step. Does this describe your prediction moment?"

This is the order PV.7 asks for, and the answer returns to the open pause. The reviewer rated it `partially` because the cost of leaving the year out (the downward bias) is named only later, in turn 6:

> "Leaving the year out of the model, which we agreed on, has a cost: the model doesn't capture this trend."

### P5: a general plan approval

> (turn 3) "Great, the plan is approved. That lets me run the work between the decision points… without asking you each time. Approving the plan doesn't settle the decisions themselves, though. The prediction moment is one of them…"

After that, every decision was confirmed `explicit` at its pause. All work between the pauses ran without a stop. Turn 6 ran the split, two EDA activities, both fits, and the evaluation in one turn. The reviewer's `partially` is about the turn 1 menu, which offered "tell me to go with my recommendation"; the reviewer then reads turn 3 as refusing that offer. Under PV.8 the agent's reading is the intended one (D9).

### PV.5: the recap carries the MAE

> "1. **Goal:** this is an exercise to estimate a future car model's fuel efficiency from its technical characteristics…
> 2. **Decided:** you made every decision in your own words… You chose the linear model, with a validation MAE of 6.31 mpg (result 142ac050), and concluded to adopt it.
> 3. **Now:** every step of the plan is done, and the report and notebook are up to date.
> 4. **Next:** no decision is left…
> 5. **Limit:** the validation rows were used both to compare the models and to choose one…"

The recap does not quote a deliverable message, has no revision number and no sub-bullet, and cites the current `evaluate.regression` id. The regression checks for vocabulary, bias, split limits, traceable numbers (21 texts, 121 numbers, 0 errors), audit, and model choice all pass.

`errors_in_target_unit` is partial on one false positive of the deterministic check. The match is a section title, "the MAE and RMSE table with the ranges", in a report walkthrough with "6." in front of it. The reviewer rates `handled`.

## 3. Small data (G.12)

### 3a: 50% validation, no warning raised

The agent's own default split was "a training half and a validation half, with the same share of renewals in each". That gave 30 rows with 7 positives on each side.

- `small_validation_partition` was not raised: 30 is not fewer than 30, and 7 is not fewer than 5.
- The manager's 100 calls were only previewed (`hypotrail preview policy --rule capacity:100`), so `capacity_exceeds_validation` was not raised either. `preview` does not carry that warning.

The agent explained the issue itself:

> "the validation partition has 30 rows, and 100 is larger than that. So both models select all 30 rows (volume rate 1.0 of those rows) and pick up the same 7 renewed members. A capacity rule only tests the ranking when it selects part of the rows."

It then asked the junior to do a conversion in technical units (D3):

> "Once you know how many members the next campaign covers, work out how many of the 30 validation rows would represent the same share as the 100 calls. Then tell me, for example "use a capacity of <K> validation rows for the team's limit"."

It also refused to treat the manager's figure as resolving the junior's hold, because "they asked for a number per renewal cycle, and this one is per campaign". The run ended with four open holds (D5). The conclusion was still an open proposal. The engine had refused "inconclusive" (`precondition_missing`: "Adopt a policy first, or conclude keep_baseline", D6).

### 3b: 30% validation, both warnings explained in plain words

With 18 validation rows and 4 positives, `small_validation_partition` was raised after the fits. It was told in turn 5, before the policy question:

> "**The evidence is very thin.** The validation partition is small (18 rows, 4 of them positive), so every validation figure rests on those few rows, and a difference between models can be chance."

It was the `Limit` line of the fresh chat's recap:

> "5. **Limit:** the held-back validation rows are few (18 rows, 4 of them renewals, result bc8c5772). Every figure measured on them is uncertain, so a difference between the two models there could be chance."

`capacity_exceeds_validation` was raised by the saved `capacity:100` evaluation. It was told at once, and again in the conclusion and the limits for the manager:

> "**Caveat:** that test can't tell the two models apart. There are only 18 validation rows (4 renewals), fewer than 100, so the rule selects every row for both models."

> "**The 100-call test describes calling everyone.** It selects all 18 validation rows, so it shows nothing about choosing who to call."

No assistant text showed a warning identifier. The study ended with "keep the baseline", with the 100 calls run as a randomised pilot. Every decision ended up confirmed by the junior.

Two engine-level findings (D2):

- The conclusion was confirmed first (turn 8, "keep the baseline… no call policy is adopted yet"), while the policy was on hold.
- The policy was adopted later (turn 18), and the junior re-confirmed the two delegated decisions in their own words.

Neither change made the confirmed conclusion stale, although its text was now wrong on both counts. The agent noticed both mismatches itself and proposed a replacement:

> "**One thing left to fix: the conclusion is now out of date.** It still says "No call policy is adopted yet…". It also says you delegated the prediction moment and the variable choice to me, while the study records both as decided by you."

## Remaining defects (prioritised, for the integrator)

"Engine" means `framework/mlkit/study/`; "instructions" means `framework/mlkit/study/agent/`. The evaluator fixed none of them.

| # | Severity | Where | Evidence | Suggested fix |
|---|---|---|---|---|
| D1 | **Medium** | Engine `decide note` (PV.3) | Bank turn 17: a hold added to an already confirmed policy leaves the policy and the conclusion confirmed. The summary and the report show "on hold" next to "confirmed". Both reviewers flagged the inconsistent record. | Refuse `decide note --about D` when D is confirmed (for example `decision_already_confirmed`, "propose D again to reopen it"). Or mark D and its dependants "to confirm again" (the report already has that label). Name the open hold in `not_yet_defensible` (`open_holds`) even when D is confirmed. |
| D2 | **Medium** | Engine (dependencies of `conclusion`) | 3b: a conclusion confirmed while the policy was open stayed confirmed after the policy was adopted. Its credit line ("delegated") stayed confirmed after the junior re-confirmed those decisions explicitly. The agent caught both by reading the text. | A later confirmation of `policy` (or `model_choice`), or a change in the basis of a credited decision, makes a confirmed conclusion stale or "to confirm again". At least, add a `not_yet_defensible` item `conclusion_outdated`. |
| D3 | **Medium** | Instructions (capacity larger than the validation rows); engine option | 3a: the agent asked the junior to "work out how many of the 30 validation rows would represent the same share as the 100 calls" and to reply in "validation rows". It refused to let the manager's figure resolve the junior's hold because of a unit mismatch. | Instructions: never ask the junior for a figure in validation-row units. When a capacity exceeds the validation rows, evaluate it, explain "selects every row" (G.12), and say what would be needed, in business terms (the campaign size). A junior's figure that answers the hold's words resolves it. Engine (v0.2): a rule in shares (`volume_rate:`) plus a documented scaling from campaign size. |
| D4 | Low | Engine G.12 (`view.SMALL_VALIDATION_ROWS`, `preview`) | 3a: 30 validation rows with 7 positives raise no warning (the thresholds are strict: fewer than 30, fewer than 5). `preview policy --rule capacity:100` on 30 rows carries no `capacity_exceeds_validation`. | Use "at most 30 rows" (or scale the positives threshold to 10). Add the capacity warning to the `preview` payload. The PV.10 review flag already names the thresholds. |
| D5 | Low | Instructions (holds) | 3a ended with 4 open holds on the policy, each a restatement of "I don't have the number yet". Bank recorded two notes for one condition. The reviewer: "keep piling up holds word for word". | When a reply restates an open hold, quote the existing note instead of adding one. Add a note only for a new condition. |
| D6 | Low | Engine (`conclusion` preconditions) | 3a: "inconclusive" was refused with `precondition_missing` ("Adopt a policy first, or conclude keep_baseline") while the policy was on hold. That is exactly when "inconclusive" is the honest verdict. | Allow `inconclusive` without an adopted policy, or explain the rule in the decision content. **Review?** |
| D7 | Low | Instructions (R6) | 3b turn 10, Auto turn 7: an agreement given before the proposal existed cost a round trip ("Your agreement came before there was a proposal…"). Reviewers count it as friction. | Keep R6. When the junior's earlier words state the value, propose with their wording as the restatement, so the confirmation is a short "yes, that". |
| D8 | Low | Agent and engine `check` (T9) | 3b turn 5: "it uses the seven columns we kept" was flagged twice as `untraceable_number` (a count in words). The agent had not checked that text. | Instructions: run `check` on every reply that holds a count. Engine (optional): trace the length of a current fit's feature list. |
| D9 | Low | Instructions (option menu at pause 1) | Auto: the turn 1 menu offered "tell me to go with my recommendation". The reviewer then read "plan looks good, let's go with it" as a delegation the agent refused. | Leave the delegation option out of the message that presents the plan, or name it ("say 'use your recommendation for this'"), so a plan approval is not mistaken for it. |
| D10 | Low | Engine `recap` (binary) | Bank and 3a recaps carry no result. Both reviewers rated `resumption` partially for this. PV.5 added the MAE for regression only. | In a binary study, cite the adopted (or most recent) policy evaluation's precision at its rule, or the logistic ROC AUC, with the first 8 characters of its result id. |
| D11 | Low | Instructions (vocabulary) | Bank: "recall" is not defined. Bank and 3a: "stratified" and "paired difference" are not explained. | Glossary entries and "term first" reminders for `recall`, `stratified`, and `paired difference`. |

Resolved, as far as these runs show:

- **P1:** no caveated agreement was refused and no wording was coached. 5 caveated agreements confirmed 6 decisions verbatim.
- **P2:** the condition was recorded at once, verbatim, and survived a new chat. The illustrative figures were never put up for confirmation. The hold was resolved only by the junior's figure.
- **P3:** four recaps in the format, the regression recap with its MAE and result id.
- **P4, P5, P6, P7:** as above.
- **G.12:** with 18 validation rows, both warnings were told in plain words, before the decision they bear on, and in the conclusion.

## Harness changes in this run

None of these weakens an assertion. Each is covered by `framework/tests/acceptance/test_graders.py` (`c2211e6` and the commit of this report).

- **`graders_b.p_fixes`** reports evidence for:
  - P1: `negative_reply` refusals, flagged when the words open with an agreement; wording coaching; caveated agreements and what they confirmed.
  - P2 (`holds`): the notes created per turn and whether each is verbatim; holds open at the start of chat 2; any confirmation while a hold is open; resolutions in the junior's words after the figure.
  - P3: flat recaps.
  - P6: `status` reads, and `status --json` piped into Python.
  - P7: the engine's `misattributed_delegation` regex on every text and on the recorded conclusion, plus the `check` findings.
  - G.12: the first turn each warning appears in the state, and whether it was told in plain words without its identifier.
- **`recap_format`** adds a `no_sub_bullets` check (PV.6).
- **`graders_reg`** adds `recap_mae_cited` (PV.5): an MAE in mpg with two decimals and the current `evaluate.regression` id prefix.
- **`e1.compact_snapshot`** keeps `notes` and the `not_yet_defensible` ids per turn. **`graders.check_assistant_texts`** keeps non-number `check` errors (for example `misattributed_delegation`) in `text_errors`. They do not count for T9.
- **`study_setup`** has a `synthetic-small` case (`e1.py run --case synthetic-small`).
- **New personas:**
  - `e1_persona_conditions.yaml`: the condition at a pause, the figure in chat 2, caveated agreements;
  - `e1_persona_regression_early.yaml`: the model-year question right after the intent;
  - `e1_persona_small.yaml`: a 30% validation share.

## Cost

| Item | Cost |
|---|---|
| Agents: `bank-cond` $2.29, `auto-early` $1.94, `syn-small` $2.09, `syn-small-30` $2.40 | $8.72 |
| Simulated junior (sonnet), 4 runs | $0.26 |
| Blind study reviewers (Bank, `syn-small`) | $1.19 |
| Dialogue reviewers (4 runs) | $0.71 |
| **Total** | **about $10.88** (guard about $12) |

## Limits

- **One run per condition.** P1's absence of refusals is the strongest result (0 against 6 in the previous check, with a persona built to provoke them). The other findings come from single runs.
- **The junior is simulated.** The persona sheet of run 1 tells the simulator not to accept a number of calls "unless the message already says the team can make 100 calls". It sees only the last message, so in turn 17 it said the 100 was not confirmed after it had given it. D1 comes from that contradiction. A human can contradict themselves too, but less mechanically.
- **Run 3b changed the junior's plan approval** to get the 30% split. Its blind study review was skipped to stay within budget.
- **Bank, Auto MPG and one synthetic case, in English only.** French caveated agreements were not exercised in a live run (they are in the engine's unit tests).

## Reproduction

```sh
uv sync --project framework --group dev
RUNS=/path/outside/the/repository
A=framework/tests/acceptance/agent
uv run --project framework python $A/e1.py run --arm $A/arms/arm_b --persona answering \
    --persona-file $A/e1_persona_conditions.yaml --case bank --repeat pfix --session-log \
    --out $RUNS/bank-cond --total-budget 4
uv run --project framework python $A/e1.py run --arm $A/arms/arm_b --persona answering \
    --persona-file $A/e1_persona_regression_early.yaml --case auto-mpg --repeat pfix --session-log \
    --out $RUNS/auto-early --total-budget 3
uv run --project framework python $A/e1.py run --arm $A/arms/arm_b --persona answering \
    --case synthetic-small --repeat pfix --session-log --out $RUNS/syn-small --total-budget 3
uv run --project framework python $A/e1.py run --arm $A/arms/arm_b --persona answering \
    --persona-file $A/e1_persona_small.yaml --case synthetic-small --repeat pfix2 --session-log \
    --out $RUNS/syn-small-30 --total-budget 2.5
uv run --project framework python $A/e1.py review --run $RUNS/bank-cond        # --dialogue-only for Auto and 3b
uv run --project framework python $A/e1.py grade --run $RUNS/bank-cond         # p_fixes in grade.json
uv run --project framework python -m mlkit.study.cli session-report --format text --study $RUNS/bank-cond/workspace
```
