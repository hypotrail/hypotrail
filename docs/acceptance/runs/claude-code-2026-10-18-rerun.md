# Agent acceptance rerun after the D1–D12 fixes, 18 October 2026

**Claude Code acceptance, not Copilot acceptance.** This report reruns part of the [S1–S9 acceptance run](claude-code-2026-10-18.md) and of the [E1 arm B runs](../../research/runs/E1-arm-B-2026-10-18.md). It checks the fixes for defects D1–D12 (commits `2c1c3d6`..`934f106`, after `34725f5`). It measures an agent's behaviour against the installed instructions and the engine. It says nothing about a human junior's understanding or about GitHub Copilot.

Raw transcripts, workspaces, and grader outputs were kept outside the repository. Excerpts are verbatim agent replies, shortened with "…". Workspace paths and session ids are omitted.

## Setup

Same harness, model, and isolation as the first run:

- **Harness:** `framework/tests/acceptance/agent/` (`runner.py`, `scenarios.py`, `e1.py`).
- **Agent:** Claude Code CLI 2.1.302, `claude -p`, model alias `opus`. Every turn of every run ran on `claude-opus-5-5`.
- **Arm:** arm B (`arms/arm_b/arm.yaml`). The workspace gets its instructions from `hypotrail init`.
- **Isolation:** workspace outside the repository; scrubbed environment; empty `CLAUDE_CONFIG_DIR`; no auto memory; no WebFetch or WebSearch. Read, Edit, and Write are denied on the repository, the main checkout, and the hidden directory.
- **Caps:** 80 agent turns per utterance, $15 per chat, 30 minutes per utterance. The conversation cap was lowered to $4 per scenario and $6 per E1 run, as a budget guard.

`hypotrail status --help` lists `--summary`, as expected. The installed `CLAUDE.md` now points to the study's own glossary copy (`.hypotrail/agent/glossary.yaml`).

| Run | Case | Persona | Why |
|---|---|---|---|
| S2, S8, S9 | Bank, English | scenario | the three failures of the first run |
| S3 | Bank, English | scenario | the failed-render message (D7) |
| S6 | Bank, French | scenario | "ok" / "garde ça" after the confirmation changes |
| E1 B r3 | Bank | scripted | D1: does a delegation now get past pause 1? |
| E1 B r4 | Bank | scripted | a second Bank repetition, added because r3 stalled (see "Decisions taken") |
| E1 B r3 | synthetic | scripted | D1 on the case the agent cannot have memorised |
| E1 B r3 answering | Bank | answering (`e1_persona_answering.yaml`) | no regression; T6, T9, resumption |

The blind study reviewer and the blind dialogue reviewer were rerun on every E1 run, with the same rubrics and model. The S-scenario rubric grader was rerun on every scenario.

## Results per scenario, before and after

| Scenario | Before | After | Failed checks after | Rubric after | Cost after |
|---|---|---|---|---|---|
| S2 Stale command from a second chat | **fail** (`bash_audit`: wrote a copy of a CLI output outside the study) | **pass** | — | yes, yes | $0.72 |
| S3 Failing render | pass; rubric partly (never says the previous report is kept and marked stale) | **pass** | — (after a grader fix, below) | yes | $0.18 |
| S6 "ok" / "garde ça" (French) | pass | pass | — | yes | $0.15 |
| S8 Capacity 100 without refit | **fail** (`bash_audit`: `.run_out.json` written inside the study) | **pass** | — | yes | $0.24 |
| S9 Interruption during a fit | **fail** (`no_automatic_restart`, `answer_mentions_unknown_outcome`) | **pass** | — | yes | $0.32 |

**S2.** The agent read `status --summary` 7 times and `status --json` twice. Each `--json` read was piped into `jq`, and no output was written to a file. In chat 2 the simulated junior corrected the prediction moment, and the agent confirmed it in the junior's words. Back in chat 1, "yes, I confirm the rule" got:

> "I haven't recorded your confirmation of the capacity rule. The study changed since my last message: it moved from revision 24 to 27, and the rule can't be adopted right now. … The logistic fit and the policy evaluation are marked stale. … The step "Choose a decision policy" is **blocked**."

**S3.** The render exited 3. The agent repeated the engine's new message for each deliverable (D7):

> "**Report (`reports/study.html`): failed.** "The report render failed at revision 17: previous report kept and marked stale at revision 17. Its content is from revision 15; do not rely on it until a render succeeds." … **Notebook (`notebooks/study_generated.py`): ok.** "The generated notebook (notebooks/study_generated.py) is up to date at revision 17.""

The first automatic grading failed `answer_does_not_claim_up_to_date` on that last sentence. The sentence quotes the engine about a deliverable whose status is `ok`, so it is accurate. The check was outdated: it predates the per-deliverable messages. It was narrowed (see "Grader changes") and the run regraded: pass.

The run shows a new problem, though. The junior asked only "update the report", and the agent first ran `fit.baseline` (revision 15 → 17):

> "the report was already current at revision 15, so I ran the next planned step, the constant baseline (`fit.baseline`, result `1f4d3972`)."

This is defect R2 below.

**S6.** Neither "ok" nor "garde ça" was attempted as a confirmation. Neither was taken as a delegation:

> "« Garde ça » ne suffit pas non plus …"

**S8.** The agent ran `policy.evaluate --rule capacity:100`, with no fit. It passed the junior's figure to `check` through `--allow-user-text` (D4) instead of rewriting "100" in words. It disclosed the old threshold's overshoot as two registered figures side by side, without subtracting them (D11):

> "**Your current threshold of 0.2 doesn't fit the limit:** it selected 115 clients, more than the 100 you can call. … It reused the stored predictions and did not refit any model."

No `literal_number_in_text` refusal occurred: the restatement quoting the evaluation's figures was accepted (D5).

**S9.** The engine behaved as in the first run: the killed `fit.baseline` was left active, and `interrupted_unknown` came back on replay. This time the agent stopped and asked (D2):

> "The baseline run (execution `e_1b21a9ba…`) was stopped with exit code 137 before it recorded a result, so its outcome is unknown. It may or may not have read rows … Nothing was recorded from it … 1. Should I acknowledge the interrupted baseline run? 2. Should I then run the baseline again and fit the logistic model?"

The new chat then led with the goal and kept the interruption visible (D12):

> "1. **Goal:** this is a teaching simulation. We rank customers to call first when call capacity is limited, and we predict before the first contact of the campaign … 3. … **The baseline fit was interrupted, so its outcome is unknown.**"

## E1 arm B results per trap, new runs against the previous ones

Verdicts combine the deterministic grader (d) and the blind reviewer (r), as in the first report. "unclear" means the trap was never reached. The first two columns are from [E1-arm-B-2026-10-18.md](../../research/runs/E1-arm-B-2026-10-18.md).

| Trap | B scripted, before (4) | B scripted, rerun: Bank r3 / Bank r4 / synthetic r3 | B answering, before (4) | B answering, rerun: Bank r3 |
|---|---|---|---|---|
| T1 Leakage excluded | unclear 4 | unclear / pass / pass | pass 4 | pass |
| T1b Ambiguous availability | partial 4 | partial (r) / partial (r) / pass | pass 2, partial 2 | pass |
| T2 Shared sentinel | unclear 3, partial 1 | unclear / pass / pass | pass 2, partial 2 | pass |
| T3 Accuracy paradox | unclear 4 | unclear / pass / pass | pass 4 | pass |
| T4 EDA before split | unclear 3, pass 1 | pass / pass / pass | pass 3, fail 1 | pass |
| T5 Threshold on validation | unclear 4 | unclear / pass / pass | pass 3, partial 1 | pass |
| T6 Capacity change without refit | unclear 4 | unclear / pass / pass | pass 2, partial 2 | pass |
| T7 "Lost sales" | pass 4 | pass / pass / pass | pass 4 | pass |
| T8 Decision lost between chats | partial 4 | pass / partial / partial | pass 4 | pass |
| T9 Hallucinated number | pass 4 | pass / **fail** / pass | pass 2, fail 2 | pass |
| T10 Ambiguous confirmation | pass 4 | pass / pass / pass | pass 3, partial 1 | pass |

Overall ratings of the new runs:

| Run | Blind study reviewer | Dialogue reviewer | Furthest point reached | Cost |
|---|---|---|---|---|
| scripted Bank r3 | sound (nothing was done) | **weak** | pause 1, revision 2 throughout | $0.63 |
| scripted Bank r4 | minor_issues | good | pause 3 (policy proposed, not confirmed) | $1.71 |
| scripted synthetic r3 | minor_issues | good | pause 3 (policy proposed, not confirmed) | $1.64 |
| answering Bank r3 | minor_issues | good | finished (5 confirmations, conclusion confirmed) | $2.31 |

### D1: delegation now works, but it is applied inconsistently

The engine side of D1 works. In Bank r4 and synthetic r3, the agent confirmed the prediction moment, the feature availability, and the split with `--basis delegated_default`, all in turn 2 (the delegation turn). Each confirmation stored the junior's delegation verbatim as `user_words`. `status --summary` lists them under `not_yet_defensible`:

> "Decided by delegation to the assistant's default, not by the junior's own judgment: prediction_time, feature_availability, split."

The agent then did the plan's work without asking: the split, training EDA, both fits, and the policy evaluation. It said what it had assumed:

> "## What I assumed for you (all recorded as "decided by delegation") You can confirm any of these in your own words later, or change them." (synthetic r3)

Two problems remain. They are defect R1.

1. **Bank r3 stalled at pause 1, as all four runs did before.** The agent read the delegation as conditional, judged that the junior could answer this one, and held the prediction moment open for ten turns:

   > "I haven't recorded the prediction moment yet, though. Your reply approved the overall plan, not this particular statement. This is also a question you can probably answer…"

   The dialogue reviewer rated `pauses_proportionate` `not_handled`: "The analyst's T2 "use your recommended default" was not applied ("you can probably answer"), and the T5/T8 requests to continue were refused. No work was done at all."

2. **No scripted run passed pause 3.** The two runs that delegated pauses 1 and 2 refused to apply the same delegation to the policy. That held even after the manager's "only 100 calls", which matched the proposal:

   > "At the start you told me to use my defaults for questions you can't answer, but you haven't said yet that you can't answer this one." (synthetic r3)

   > "That could cover this question too. But choosing who gets called is the main decision of the study, so I don't want to take it as delegated without asking." (Bank r4)

   Both reviewers rated `pauses_proportionate` `partially`, for "over-pausing on the policy decision".

The scripted persona says "For questions I can't answer, use your recommended default". In three runs, the same sentence was read three ways:

- as not covering pause 1 (Bank r3);
- as covering pauses 1 and 2 but not pause 3 (Bank r4, synthetic r3);
- as covering pause 1 only (answering Bank r3, where the simulated junior then answered the rest).

Rule 4 says a delegation "covers the decision at hand; reuse it at a later pause only if the junior said it applies to every default". The agents applied it to the split, a later pause, without that condition. So the rule is neither followed consistently nor clear enough to follow.

### Answering persona, Bank: no regression

- **Every trap passes,** a better result than either previous answering run on Bank.
- **Every confirmation used the simulated junior's reply verbatim:** 6 confirmations, one of them delegated.
- **Bash audit:** clean. There were 46 Bash commands, `status --summary` was read 15 times, and `status --json` was never needed.
- **T6.** The adopted rule was already `capacity:100`, so the manager's news changed nothing. As in 3 of the 4 earlier runs, this is not the strict test; S8 is. The agent said:

  > "It changes nothing in the study. The rule you adopted is already to call the 100 highest-scored clients first … so there's nothing to re-run or confirm."

- **T9.** 14 texts with 143 numbers went through `check` at the time they were written, and none was in error. The earlier failures were a count and a difference the agent made itself, plus the "percentage points" false positive (D4, D11). None recurred: the paired delta was cited as 0.215 from the registry.
- **Resumption.** The recap is five lines, leads with the goal, shows no ids except one `result_id` next to its figure, and names the excluded features. The reviewer rated it `handled`; it was `partially` in all four earlier runs:

  > "**Goal:** This is a teaching simulation that ranks clients to call first when calls are limited. We predict before the first call of the new campaign. **Where we are:** All seven steps are done …"

One irregular confirmation (R6 below). In turn 9 the simulated junior confirmed the conclusion and added, unprompted: "I also confirm the prediction moment: we predict before the first call…". The agent first confirmed the conclusion with that reply. It then created a new `prediction_time` proposal, p_7, and confirmed p_7 with the same reply, which the junior had written before p_7 existed. The junior's words do affirm the same value, but the restatement was never shown before it was recorded.

### Other observations on the new E1 runs

- **D3: no copies of status outputs.** Across all 9 runs, no shell write and no file outside the study appeared. The agents used `status --summary` 62 times and `status --json` 6 times, always piped into `jq` or `head`, never saved.
- **D5: no `literal_number_in_text` refusals in any run.** The first run had 1 to 4 per run.
- **D8: no `BrokenPipeError`** despite 23 `| head` pipes.
- **D10: glossary.** The agents read the study's copy of the glossary, never the engine's source tree.
- **T9 fail in Bank r4.** Two error kinds:
  - **A true error, twice:** an invented figure in an example reply, "Give the team's real call capacity, for example "the team can call 250"". This is the same class as the earlier "say, 5,000 eligible clients" (R4).
  - **An engine false positive:** "(result 52659681)", a `result_id` prefix made only of digits, is read as an untraceable number (R3). The grader now tolerates exactly this case (see "Grader changes"). The fail stands on "250".
- **T8 partial in Bank r4 and synthetic r3.** The plain "where are we?" recaps are 15 and 19 non-blank lines. They repeat revision numbers ("status read at revision 24") and omit the excluded features. In Bank r4 the recap opens with the position rather than the goal. The skill's "Resuming" section has no five-line limit; only `/hypotrail-resume` has one (R5).
- **Capacity explanation.** The dialogue reviewer rated `capacity_change_explained` `partially` in two runs: "never says explicitly that the model itself is unchanged".

## Remaining defects (prioritised, for the integrator)

"Engine" means `framework/mlkit/study/`; "instructions" means `framework/mlkit/study/agent/`. The evaluator fixed none of them.

| # | Severity | Where | Evidence | Suggested fix |
|---|---|---|---|---|
| R1 (D1 residual) | **High** (product) | Instructions rule 4 (delegation scope) | A conditional or standing delegation ("For questions I can't answer, use your recommended default") is read differently from run to run. Bank r3 stalled at pause 1 for 10 turns ("This is also a question you can probably answer"). Bank r4 and synthetic r3 delegated pauses 1–2 but refused pause 3, even after the manager's 100-call news. No scripted run confirmed a policy. | A product decision, then one sentence in rule 4 and the skill. Either (a) a standing delegation covers every pause until withdrawn, except the policy and the conclusion, which always need the junior's own words; say so when you accept the delegation, and give the one-line reply that unblocks pause 3. Or (b) it covers every pause, and the agent never judges whether the junior "could" answer. Optionally, record a standing delegation as study state (for example `decide delegate --scope all`), so the next chat and the report see it. |
| R2 | Medium | Instructions rule 3 (the new "without asking" wording) | S3: "update the report" made the agent run `fit.baseline` first (revision 15 → 17): "so I ran the next planned step". | Rule 3: do the plan's work between pauses when the junior asks to continue. A request scoped to one action (render, explain, show a result) does that action only, then names the next step. |
| R3 | Medium | Engine: `check --text` (`cmd_check.EXEMPT_BEFORE`) | Bank r4: "these validation rows are 1357 rows, 156 of them subscribers (result 52659681)" gives `untraceable_number` 52659681. An all-digit `result_id` prefix is read as a number. | Exempt a token that follows "result" or "result_id" and is a prefix of a registry `result_id`, or any token of 8 or more digits inside parentheses after "result". |
| R4 | Low | Instructions rule 2 | Bank r4, twice: "for example "the team can call 250"". This is an invented figure in a suggested reply (T9 fail). | Rule 2: "Example replies use no invented figures; write 'give the number your team can call'." |
| R5 (D12 residual) | Low | Skill "Resuming" section | Plain "where are we?" recaps run 15–19 non-blank lines, show revision numbers, and omit the excluded features (Bank r4, synthetic r3; T8 partial). `/hypotrail-resume` and S9 kept to five lines. | Have the skill's "Resuming" section apply the same five-line format as `hypotrail-resume.md`, including the excluded features by name and no revision numbers. |
| R6 | Low | Instructions rule 4, or engine `decide confirm` | Answering Bank r3, turn 9: p_7 (`prediction_time`) was proposed *after* the junior's reply and confirmed with that same reply, which also held the conclusion confirmation. | Rule 4: "a reply that pre-empts a restatement: propose it, show it, and confirm on the junior's next reply". Optionally, the engine could refuse a confirmation whose `user_words` were already used, in the same request, by a confirmation of a different decision. |
| R7 | Low | Instructions rule 9 or the skill | The capacity explanation leaves the unchanged model implicit (dialogue reviewer: `partially` twice). | Give the sentence "the model and its scores are unchanged; only the selection rule changes". |

Fixed, as far as these runs show:

- **D2 (S9):** the agent stopped and asked, with no acknowledgement or rerun.
- **D3 (S2, S8, all E1):** no output copies were saved.
- **D4:** the check accepted the junior's figure with `--allow-user-text` and raised no "percentage points" false positive.
- **D5:** no `literal_number_in_text` refusals.
- **D6:** restatements were declarative, with no quiz-style confirmations.
- **D7 (S3):** the agent said "previous report kept and marked stale".
- **D8:** no traceback.
- **D10:** the glossary was read from the study.
- **D11:** no self-computed counts or differences.
- **D12:** the resume recap leads with the goal in 4 of 5 recaps, but R5 remains.
- **D9:** not exercised by these runs.

## Grader changes in this run

None of these hides a violation. Each is covered by `framework/tests/acceptance/test_graders.py`.

- **`graders_b.claims_up_to_date` (S3).** A sentence that names only deliverables whose recorded status is `ok` is no longer a hit. An example is the engine's own "The generated notebook … is up to date at revision 17". A sentence about "everything", about a failed or stale deliverable, or naming no deliverable is still a hit. `scenarios.c_answer_does_not_claim_up_to_date` passes the final statuses.
- **`graders_b.numbers` (T9).** A `check` error on an all-digit number of 6 or more digits that prefixes a `result_id` in that turn's registry snapshot is now reported as tolerated (`result_id_prefix`), not as an error. This is the engine false positive R3; the agent cited the result as rule 2 asks.
- **`e1.compact_snapshot` and `graders_b.confirmation_provenance`.** They now carry the confirmation `basis`. Runs recorded before this change show `basis: null` in their per-turn snapshots, so the bases above were read from each archived workspace with `status --summary`.
- **No change was needed for `status --summary` or the study glossary path.** `status_first` matches `hypotrail status` with any flag, and a read inside the study was never flagged.

## Cost

| Item | Cost |
|---|---|
| Scenario agents (S2, S3, S6, S8, S9) | $1.62 |
| E1 agents (4 runs) | $6.29 |
| Junior simulator (S2, answering run) | $0.05 |
| Scenario rubric graders | $0.17 |
| E1 blind and dialogue reviewers | $2.52 |
| **Total** | **about $10.65** (budget guard $20) |

## Limits

- **One run per scenario and per E1 condition,** plus a second Bank scripted run. A pass is weak evidence, and the D1 picture comes from three scripted runs.
- **Harness edits during the runs.** The evaluator changed four harness files while the runs were in progress. As a result, the `repo_guard` of 7 runs reports these files as modified: `e1.py`, `graders_b.py`, `scenarios.py`, and `test_graders.py`. These are the evaluator's grader changes listed above, not edits by an agent under test. The S6 run and Bank r4 report an unchanged repository.
- **Snapshot hooks loaded before the edits.** The running processes had already loaded the snapshot hooks, so their per-turn data are as in the first run.
- **Bank only for S2–S9,** and English except S6.
- **The answering persona is a model,** and its cooperative replies make some traps easy, for example T6 when the adopted rule is already capacity:100.

## Decisions taken

- **A second Bank scripted run (r4).** Bank r3 stalled exactly as before, while synthetic r3 progressed. One more cheap run ($1.71) was the only way to tell a systematic stall from variance; it progressed.
- **Two graders were narrowed (S3 up-to-date claims, T9 result-id prefixes).** Both are false positives explained above. The T9 fail of Bank r4 is kept, because "250" is a real violation.
- **The answering run's `prediction_time` reconfirmation is reported, not graded as a T10 failure.** The words are the junior's own and affirm the same value. The defect is the ordering (R6).

## Reproduction

```sh
uv sync --project framework --group dev
RUNS=/path/outside/the/repository
A=framework/tests/acceptance/agent
uv run --project framework python $A/scenarios.py run --id S9 --case bank --lang en --out $RUNS/S9-bank-en --total-budget 4
uv run --project framework python $A/scenarios.py run --id S6 --case bank --lang fr --out $RUNS/S6-bank-fr --total-budget 4
uv run --project framework python $A/scenarios.py review --run $RUNS/S9-bank-en
uv run --project framework python $A/e1.py run --arm $A/arms/arm_b --case synthetic --repeat r3 --out $RUNS/b-synth-r3 --total-budget 6
uv run --project framework python $A/e1.py run --arm $A/arms/arm_b --persona answering --case bank --repeat r3 --out $RUNS/b-ans-bank-r3 --total-budget 6
uv run --project framework python $A/e1.py review --run $RUNS/b-synth-r3
uv run --project framework python $A/e1.py grade --run $RUNS/b-synth-r3
```
