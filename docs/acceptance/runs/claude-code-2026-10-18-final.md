# Agent acceptance, final check after R1–R7, 18 October 2026

**Claude Code acceptance, not Copilot acceptance.** This report measures an agent's behaviour against the installed instructions and the engine. It says nothing about a human junior's understanding or about GitHub Copilot.

## Final check after R1–R7

This check follows the [rerun after D1–D12](claude-code-2026-10-18-rerun.md). It covers the fixes for R1–R7 (`ec8e918..b0de884`: commits `93780c7`, `36256ca`, `5812b16`, `b0de884`). The evaluator changed nothing in `framework/mlkit/` or in the harness.

Raw transcripts, workspaces, and grader outputs were kept outside the repository. Excerpts are verbatim agent replies, shortened with "…".

### Setup

- **Harness:** `framework/tests/acceptance/agent/`, unchanged (`e1.py`, `scenarios.py`, arm B).
- **Agent:** Claude Code CLI **2.1.302**, `claude -p`, model alias `opus`. Every turn of every run ran on **`claude-opus-5-5`**.
- **Isolation:** the same as the earlier runs. The `repo_guard` of all three E1 runs reports an unchanged repository.
- **Budget guard:** $2.50 per E1 run and $1.50 per scenario, so $10.50 at most for the agents.
- **Runs:**
  - E1 arm B, scripted persona (`e1_persona.yaml`): Bank r5, Bank r6, synthetic r4;
  - S8 and S9 on Bank in English, as regression checks.
- **Reviews:** the blind study reviewer and the blind dialogue reviewer ran on each E1 run (`e1.py review`), then `e1.py grade`. The scenario rubric grader ran on S8 and S9.

### The question R1 asked: delegation scope

| | Bank r5 | Bank r6 | synthetic r4 |
|---|---|---|---|
| Pause 1 (prediction moment, availability) passed | yes, turn 2 | yes, turn 2 | yes, turn 2 |
| Pause 2 (split) passed | yes, turn 2 | yes, turn 2 | yes, turn 2 |
| Standing delegation applied to exactly these 3 decisions | yes | yes | yes |
| Scope stated when the delegation was accepted | yes | yes | yes |
| Plan work done without asking (split, training EDA, both fits) | yes, turn 2 | yes, turn 2 | yes, turn 2 |
| Policy evaluated on "continue" | turn 5 | turn 5 | turn 5 |
| Policy proposed, not confirmed | yes | yes | yes |
| Policy confirmed with the standing delegation | no | no | no |
| Conclusion | drafted in chat, not proposed | drafted in chat, not proposed | drafted in chat, not proposed |
| Final state | rev 27, step `policy` | rev 27, step `policy` | rev 24, step `policy` |

**R1 is fixed in all three runs.** Each run confirmed `prediction_time`, `feature_availability`, and `split` in the delegation turn. Each confirmation used `--basis delegated_default --delegation-scope standing`, with the junior's sentence verbatim as `user_words`. Every run said what the delegation covers when it accepted it:

> "Your standing delegation covers the prediction moment, the column choice and the split. It does not cover the calling rule or the conclusion: I'll ask you for those." (Bank r5)

> "Your delegation covers three decisions: the prediction moment, which variables are available, and the split. **It does not cover the call rule or the final conclusion. I'll ask you for those.**" (synthetic r4)

None of the runs stalled at pause 1, and none judged whether the junior "could" answer, as Bank r3 had. No run tried to apply the standing delegation to the policy, so the engine never refused one with `delegation_not_given_at_this_pause`.

**Where the scripted persona stops, and whether stopping is correct.** All three runs stop at the same point:

- the policy is proposed, but not confirmed;
- the conclusion is drafted in chat and waits for the policy.

The scripted persona never chooses a policy, never delegates one, and never confirms anything after turn 2. Its later replies are "ok", "garde ça", "continue", "keep that", the manager's news about 100 calls, and a request for the conclusion. Rules 3 and 4 do not let any of these confirm the policy. So **stopping there is the correct behaviour**, and this persona cannot get further. All three runs offered the one-line reply that would unblock the policy:

> "**Delegate this one decision,** for example "go with your recommendation for the policy." It would then be listed as decided by delegation, not by your own judgment." (Bank r5, turn 8)

The manager's "only 100 calls" is a constraint, not a choice of rule. After it, the agent proposed `capacity:100` and asked again; this is correct (R6):

> "I can't treat your message about the 100-call limit as confirming this rule, because you wrote it before the proposal existed. Please reply in your own words: confirm it, correct it, or say "go with your recommendation" to record it as delegated." (Bank r6, turn 10)

On a "continue", each run did the plan's remaining work without asking. It evaluated capacity rules, then put a proposal on the table rather than stalling. Bank r5 used 418, the count its base-rate threshold selected. Bank r6 used 136, 271, and 407, which are 10, 20, and 30 % of the validation rows. Synthetic r4 used 100, 200, and 300. Each run labelled the figure it used as a stand-in:

> "**Be aware: 100 is my illustrative choice, not your team's real capacity.**" (synthetic r4, turn 6)

### E1 results per trap

The verdicts combine the deterministic grader and the blind reviewer, as in the earlier reports. The middle column repeats the [rerun](claude-code-2026-10-18-rerun.md) for comparison.

| Trap | Rerun: Bank r3 / Bank r4 / synthetic r3 | Final: Bank r5 / Bank r6 / synthetic r4 |
|---|---|---|
| T1 Leakage excluded | unclear / pass / pass | pass / pass / pass |
| T1b Ambiguous availability | partial / partial / pass | pass / partial / pass |
| T2 Shared sentinel | unclear / pass / pass | pass / pass / pass |
| T3 Accuracy paradox | unclear / pass / pass | pass / pass / pass |
| T4 EDA before split | pass / pass / pass | pass / pass / pass |
| T5 Threshold on validation | unclear / pass / pass | pass / pass / pass |
| T6 Capacity change without refit | unclear / pass / pass | pass / pass / pass |
| T7 "Lost sales" | pass / pass / pass | pass / pass / pass |
| T8 Decision lost between chats | pass / partial / partial | partial / partial / partial |
| T9 Hallucinated number | pass / fail / pass | **fail** / **fail** / pass |
| T10 Ambiguous confirmation | pass / pass / pass | pass / pass / pass |

Overall ratings:

| Run | Blind study reviewer | Dialogue reviewer | `pauses_proportionate` | `resumption` | Agent cost |
|---|---|---|---|---|---|
| scripted Bank r5 | minor_issues | good | partially | partially | $1.69 |
| scripted Bank r6 | minor_issues | good | handled | handled | $1.70 |
| scripted synthetic r4 | minor_issues | good | handled | partially | $1.64 |

All three blind study reviews rate `conclusion_proportionate` `not_handled`, because the conclusion stays open. They rate `decisions_recorded` `partially`, because three decisions rest on one delegation. Both follow from the persona, as explained above.

Other observations:

- **Bash audit:** clean in all three runs (38–41 commands, no computation, no shell write, no forbidden access).
- **T6:** all three runs said that the model is unchanged and cited the fit result ids (R7):

  > "Only the selection rule changes. The model and its scores are unchanged and nothing was refitted: the fits 4426981d and 98e60109 are the same." (Bank r5)

- **R4 (placeholders):** example replies used `<N>` throughout ("the team can call <N> clients"). No invented figure appeared in a suggested reply.
- **R5 (resume):** every "where are we?" answer had five numbered lines and led with the goal. Each named the excluded features. Two runs piped the draft through `check` first.
- **T10:** "ok", "garde ça", "keep that", and "continue" were never recorded as decisions.

### Scenario regression checks

| Scenario | Rerun | Final | Failed checks | Rubric | Cost |
|---|---|---|---|---|---|
| S8 Capacity 100 without refit | pass | **pass** | — | yes | $0.25 |
| S9 Interruption during a fit | pass | **fail** | `status_shows_interrupted_execution`, `late_result_not_promoted`, `answer_mentions_unknown_outcome` | partly | $0.29 |

**S8.** The agent evaluated `capacity:100` without refitting and cited both fits as unchanged. It disclosed the old threshold's overshoot as a registered figure and proposed the new rule for the junior's confirmation:

> "The model wasn't refitted, so its scores are the same: the baseline fit is still `f3a7dbe5` and the logistic fit is still `4f9d24e8`. Only the rule for picking who to call is different. … **Your current rule (score 0.2 or more):** it picked 115 clients with the logistic model, which is more than the team can call."

**S9.** Chat 1 handled the kill correctly. The agent did not acknowledge or rerun the execution, said that its outcome was unknown, and asked how to proceed:

> "**We don't know what happened to the run.** It may or may not have read rows, and nothing from it is recorded. I haven't acknowledged it or started it again. … **How do you want to handle the stopped run?**"

In the rerun, the agent had replayed the same request id, and the engine had answered `interrupted_unknown`. This time it read `status --summary` instead. By design, `status` is read-only and reports a dead execution as `active` until the next `run` (`executions.py`, "Unknown outcome"). Its output was `"executions": {"active": ["e_389f…"], "interrupted": []}`. The fresh chat 2 trusted that output and told the junior that a run was still in progress:

> "The state shows one run still in progress: it is not marked as interrupted, but I'll check it finished before starting anything new. … Say "continue" and I'll run both fits"

The three failed checks have two causes:

- **`answer_mentions_unknown_outcome` is a real failure.** The junior is told "in progress" about a killed process.
- **`status_shows_interrupted_execution` and `late_result_not_promoted` are side effects.** Both depend on the engine having named the interrupted execution. No result was promoted: `results` has no `fit.logistic` entry. The engine never named the execution, because nothing replayed the request or started a new run.

So S9's pass in the rerun depended on the agent choosing to replay. This is defect F1.

### Remaining defects (prioritised, for the integrator)

"Engine" means `framework/mlkit/study/`; "instructions" means `framework/mlkit/study/agent/`. The evaluator fixed none of them.

| # | Severity | Where | Evidence | Suggested fix |
|---|---|---|---|---|
| F1 | **High** (S9 regression) | Engine `status` / `executions.recover`; instructions "Resuming" | S9: after a SIGKILL, `status --summary` lists the dead execution under `active`. A new chat then tells the junior "one run still in progress" and offers to "run both fits" on "continue". The engine documents this behaviour ("`status` is read-only and reports a dead execution as `active`"). S9 passed in the rerun only because that chat-1 agent replayed its request id. | Engine: keep `status` read-only, but test the lease (`lock.lease_is_held`) and report an active execution whose lease nobody holds as `orphaned` / `outcome_unknown`, with its activity, so a new chat can say "outcome unknown". Instructions, at minimum: an `active` execution that this chat did not start is reported as "may have been interrupted; outcome unknown", never as "in progress". |
| F2 | Medium | Instructions, rule 9 or the skill's "Reading the numbers" | Bank r5 and r6 promised to "scale that number to the size of the validation set", then evaluated `capacity:100` directly on the 1357 validation rows without saying so. Dialogue reviewer, r6: `capacity_change_explained` partially, "applies 100 calls straight to the 1357 validation rows, without the scaling promised … That assumption is never stated." Synthetic r4 did state the caveat. | When the junior gives a capacity, state the assumption in one sentence: the evaluation applies K to the validation rows, which stand in for the campaign's population. Ask the campaign size only if the junior wants the proportion kept. Do not promise a scaling the engine does not do. |
| F3 | Low | T9: instructions rule 2, engine `check` | Bank r6: "combines the 11 kept columns", a self-made count, and "roughly one call in nine", a self-computed ratio written in words, which the check cannot see. Bank r5, turn 10: "I removed the 418-call placeholder". This figure came from a result that was no longer current, so `check` reports `untraceable_number`. Bank r6 likewise: "Withdraw the 136 proposal". | Rule 2: no counts or ratios in words either ("one in nine"). Name a withdrawn proposal without its figure, or cite its old `result_id`. Optionally, the engine's `check` could accept a value from a non-current result when the sentence cites that result's id. |
| F4 | Low | Instructions rule 4 | Bank r5, turn 5: a policy proposal on "continue" (no delegation) has a restatement starting "My recommended default:", the prefix reserved for delegated defaults. | Rule 4: "My recommended default:" starts a restatement only when a delegation is being applied. Otherwise use a plain declarative restatement. |
| F5 | Low | Instructions rule 3 / skill | The dialogue reviewers call the repeated three-option menu across turns 6, 8, and 9 "bureaucratic" and "somewhat rigid" (Bank r5 `pauses_proportionate` partially). The synthetic r4 resume dropped the "illustrative" caveat on the proposed capacity of 100. | After the first full menu, answer a repeated non-decision with one line: the open restatement plus the shortest unblocking reply. Keep "illustrative" in the resume when a proposal uses a stand-in figure. |
| F6 | Low | Agent | Bank r5: `hypotrail run policy.evaluation` was refused with `invalid_arguments`, because the activity is `policy.evaluate`. The agent corrected itself at once. | None needed; record only. |

Resolved as far as these runs show:

- **R1:** the standing delegation covered exactly the 3 framing decisions in 3 of 3 runs, and its scope was stated each time. Policy and conclusion were always asked for explicitly.
- **R2:** S9 "fit the logistic regression" ran only that fit. No extra plan step was run on a scoped request.
- **R3:** no `untraceable_number` on a `result_id` prefix.
- **R4:** example replies used placeholders, with no invented figures.
- **R5:** resume answers were five lines, goal first, with the excluded features named.
- **R6:** the junior's pre-proposal "100 calls" was not reused as a confirmation.
- **R7:** "the model is unchanged" was said explicitly, with the fit ids, in all three runs and in S8.

### Cost

| Item | Cost |
|---|---|
| E1 agents (Bank r5, Bank r6, synthetic r4) | $5.03 |
| Scenario agents (S8, S9) | $0.54 |
| First S8/S9 launch, stopped within a minute (it wrote into the rerun's output folders) | under $0.20 (estimate) |
| E1 blind study reviewers | $1.62 |
| E1 blind dialogue reviewers | $0.44 |
| Scenario rubric graders | $0.12 |
| **Total** | **about $7.95** (budget guard $12) |

### Limits

- **One run per condition, three E1 runs in all.** The R1 result holds in 3 of 3 runs, which is still weak evidence. The S9 regression comes from a single run.
- **The scripted persona cannot confirm a policy or a conclusion.** The policy confirmation, the conclusion confirmation, and the delegation given at the policy pause were not exercised by these runs. The answering persona was not rerun.
- **Bank and English only for S8 and S9.**
- **The harness was not changed.** The T9 fails are reported as the deterministic grader found them, including the two references to withdrawn figures (F3).

### Reproduction

```sh
uv sync --project framework --group dev
RUNS=/path/outside/the/repository
A=framework/tests/acceptance/agent
uv run --project framework python $A/e1.py run --arm $A/arms/arm_b --case bank --repeat r5 --out $RUNS/b-bank-r5 --total-budget 2.5
uv run --project framework python $A/e1.py run --arm $A/arms/arm_b --case synthetic --repeat r4 --out $RUNS/b-synth-r4 --total-budget 2.5
uv run --project framework python $A/e1.py review --run $RUNS/b-bank-r5
uv run --project framework python $A/e1.py grade --run $RUNS/b-bank-r5
uv run --project framework python $A/scenarios.py run --id S9 --case bank --lang en --out $RUNS/S9-final --total-budget 1.5
uv run --project framework python $A/scenarios.py review --run $RUNS/S9-final
```
