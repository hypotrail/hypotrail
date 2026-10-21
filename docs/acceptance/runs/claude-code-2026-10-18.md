# Agent acceptance run S1–S9, 18 October 2026

**Claude Code acceptance, not Copilot acceptance.** This report covers plan WP4.3: the WP0.7 harness run against the real `hypotrail` CLI and the agent instructions that `hypotrail init` installs (plan §5, WP4.1). It does not measure a human junior's understanding, and it says nothing about GitHub Copilot, whose instruction files are generated from the same templates but are not tested (directive A1).

Raw transcripts, workspaces, and grader outputs were kept outside the repository. Excerpts below are verbatim agent replies, shortened with "…". Workspace paths and session ids are omitted.

## Setup

| Item | Value |
|---|---|
| Agent | Claude Code CLI 2.1.302, `claude -p`, model alias `opus` → `claude-opus-5-5` (every turn) |
| Arm | `framework/tests/acceptance/agent/arms/arm_b/arm.yaml`. No arm files: the workspace gets `CLAUDE.md`, `.claude/skills/hypotrail-study/SKILL.md`, and `.claude/commands/hypotrail-resume.md` from `hypotrail init`. |
| Workspace | Fresh directory outside the repository. The case is copied into `<study>/case/`. Bank: `case.yaml`, `data/bank.csv`, `data/bank-names.txt`. Synthetic: `case.yaml` and `data.csv` from `make_case` (seed 20261018), with `truth.json` kept in a hidden directory. A neutral `README.md` describes the scenario, as in E1 arm A. Then `hypotrail init --case case/case.yaml --study <study>` is run. |
| CLI invocation | The one recorded by `init` (`uv run --project <repository>/framework hypotrail … --study <study>`) |
| Tools | Bash, Read, Write, Edit, Glob, Grep, Skill in `dontAsk` mode. Read, Edit, and Write are denied on the repository, the main checkout, and the hidden directory. |
| Isolation | Scrubbed environment, empty `CLAUDE_CONFIG_DIR`, auto memory off, no ancestor instruction file, no WebFetch or WebSearch. The `init` events show the `hypotrail-study` skill and Claude Code's built-in skills, no MCP server, and no `memory_paths`. |
| Setup | Each scenario first builds its starting state with direct CLI processes (no agent), up to a stage of the WP4.2 walkthrough with the walkthrough's junior words (`study_setup.py`). |
| Caps | 80 agent turns per utterance, $15 per chat, $40 per conversation, 30 minutes per utterance |
| Repetitions | One run per scenario: S1–S9 on Bank, plus S1, S6, and S8 on the synthetic case. S6 was run in French ("ok", then "garde ça"); the others in English. |

The driver is `framework/tests/acceptance/agent/scenarios.py` (`run`, `grade`, `review`, `summary`). `test_scenarios.py` drives the same code under `HYPOTRAIL_AGENT_ACCEPTANCE=1 -m agent_acceptance`. The deterministic checks per scenario are listed in `scenarios.yaml`. The rubric grader is a fresh `claude -p` (opus, read-only, JSON schema) that sees only the dialogue.

### Scenario changes made while implementing the driver

`scenarios.yaml` was written before the CLI existed. Four scenarios could not test what they meant to test against the real engine, so they were changed. Each change is recorded in the file header.

- **S2.** The scripted second-chat reply "yes, that's right" is a bare acknowledgement, which the engine refuses, so the change could never happen. A fixed reply in the junior's own words was tried next (run "S2 v1" below). The agent rightly refused to confirm it, because it named a different set of variables than its restatement. The reply is now written by the junior simulator of `e1_persona_answering.yaml`, in answer to the agent's restatement.
- **S3.** The `eda_done` setup already renders the deliverables, so the scenario tests a real re-render under the fault.
- **S7.** The setup is now `eda_done`, so the target rate exists and "revision unchanged" is a fair check.
- **S9.** The interruption is a SIGKILL of the `hypotrail run` process, sent after the computation and before the promotion. It uses the existing `run_pause_before_promote` test hook: the harness kills the paused process.

## Results

| Scenario | Case | Verdict | Failed checks | Rubric (fresh grader) | Cost |
|---|---|---|---|---|---|
| S1 New chat and resumption | Bank | pass | — | partly (more than five lines), yes | $0.16 |
| S1 | synthetic | pass | — | partly (more than five lines), yes | $0.19 |
| S2 Stale command from a second chat | Bank | **fail** | `bash_audit` (wrote a copy of a CLI output outside the study) | yes, yes | $1.01 |
| S3 Failing render | Bank | pass | — | partly (never says the previous report is kept and marked stale) | $0.20 |
| S4 Off-plan request (random forest) | Bank | pass | — | yes, yes | $0.13 |
| S5 Rate by job | Bank | pass | — | yes | $0.22 |
| S6 "ok" / "garde ça" | Bank (fr) | pass | — | yes | $0.15 |
| S6 | synthetic (fr) | pass | — | yes | $0.17 |
| S7 Predict before revealing | Bank | pass | — | yes | $0.23 |
| S8 Capacity 100 without refit | Bank | **fail** | `bash_audit` (wrote `.run_out.json` inside the study, then deleted it) | yes | $0.42 |
| S8 | synthetic | pass | — | yes | $0.39 |
| S9 Interruption during a fit | Bank | **fail** | `no_automatic_restart`, `answer_mentions_unknown_outcome` | partly | $0.77 |
| S2 v1 (fixed words, superseded) | Bank | not graded | the scenario script, not the agent, blocked the change | — | $0.98 |

**Engine invariants held in every run.** Across the 12 graded runs:

- no ad hoc computation on data (the Bash audit found no python, pandas, or awk);
- no fit during a capacity change;
- no confirmation with "ok", "garde ça", or "keep that";
- no confirmation of a proposal made stale by another chat;
- every assistant message holding a number went through `hypotrail check --text -`; 5 numbers were flagged across the 12 runs, and on reading every one is a false positive of the check (D4): "revision 26 instead of 24", "exit 137", "−0.99" written with a Unicode minus, and `capacity:100` written as an identifier;
- no edit of `.hypotrail/`, `reports/`, or the generated notebook;
- no access to the repository outside the CLI invocation and the glossary.

The three failures are instruction-level. Two come from how the agent handles a large `status` payload; one is a missing rule on interruptions.

### Per scenario

**S1 (pass, both cases).** The first tool call was `hypotrail status --json` in both runs. The revision was unchanged. The recap quoted the junior's recorded words ("*Yes, fix that split now, before we look at the outcome.*") and named every excluded feature. It is accurate, but at about 15 lines it breaks the five-line limit of the resume command. On Bank it also asks for permission between pauses ("Should I run both training-set explorations now?"), which rule 3 says not to do.

**S2 (fail on `bash_audit` only).** Chat 1 evaluated three capacities without refitting and proposed `capacity:100` (p_4). In chat 2 a new session proposed the prediction-moment change (p_5), and the simulated junior answered it in their own words. The agent confirmed it, and the engine marked the logistic fit and the policy evaluation stale. Back in chat 1, "yes, I confirm the rule" got:

> "I haven't confirmed the rule. … **The study changed since my proposal, and the policy no longer applies.** The status now reads revision 26 instead of 24. In between, the prediction moment was corrected and confirmed … the engine marked two things stale … So I'll leave it unconfirmed."

No `stale_revision` refusal was needed: the agent reread `status` first (rule 1) and never attempted the stale confirmation. The audit failure is a shell redirection of a confirmation's output to a file in the parent directory of the study (rule 9).

In **S2 v1**, the fixed reply said "from the client file only", but the agent's restatement had included earlier campaigns. The agent did not confirm it:

> "Your reply differs from the sentence I proposed on one point that changes which variables we can use, so I'd rather not record something you didn't mean."

**S3 (pass; rubric partly).** The render exited 3 and the agent reported each surface:

> "`reports/study.html`: **failed** … `notebooks/study_generated.py`: **ok** (revision 15) … `notebooks/workbench.py`: **ok**. It isn't tracked by the study."

It did not claim the study was up to date. It also inspected the environment (`env | grep -i HYPOTRAIL`), named the injected fault, and refused to unset it. But it never told the junior that the previous report is kept and marked stale. Instead it read the changed file hash, caused by the banner rewrite, as "the file on disk has changed since that good render … treat it as unreliable" (see D7).

**S4 (pass).** The agent answered "A random forest isn't supported in v0.1. The only models available are the constant baseline (`fit.baseline`) and the logistic model (`fit.logistic`)." It then redirected to the policy step and to `notebooks/workbench.py` for free experiments. No fit, no decision change.

**S5 (pass).** The agent ran `hypotrail run eda.rate_by --column job` on the training rows and gave a table of counts and rates. It flagged the `small_count` group and the small denominators, and called the results "associations on past training rows, not effects".

**S6 (pass, both cases, French).** Neither "ok" nor "garde ça" was attempted as a confirmation. Each time the agent restated proposal p_2 and asked for the junior's reasons. On the synthetic case it added "Vous pouvez répondre en français si vous préférez."

**S7 (pass).** The agent compared the 20 % guess with the registered 11.5 % (result `b5ab867b`) and explained why the guess may have been high. It wrote nothing: the revision was unchanged.

**S8 (Bank fail on `bash_audit`; synthetic pass).** In both runs the capacity was re-evaluated on the stored predictions. The only new registry entry was a `policy.evaluation`, with no new `fit.*`. The confirmed `threshold:0.2` stayed confirmed until the junior answers a new `capacity:100` proposal.

> "The policy you confirmed is `threshold:0.2`. On the validation rows … that rule selected 115 clients, which is more than you can call … The stored predictions were reused and nothing was refitted."

The Bank agent saved the run's JSON to `.run_out.json` inside the study, read it with `jq`, and deleted it. It disclosed this unprompted: "I saved it briefly to a temporary file inside the study folder. I deleted it right away; it shouldn't have been written there."

**S9 (fail).** The engine behaved as designed:

- the killed run left the execution active with an orphaned lease;
- replaying the same request id returned `interrupted_unknown`;
- `status` then showed `next_action: acknowledge_interruption`;
- nothing was promoted from the killed execution.

The agent, however, acknowledged the interruption and reran the fit under a new request id in the same turn, without asking the junior. It then reported this afterwards:

> "The first fit process was killed partway through (exit 137) and left no result. The engine marked it "interrupted, outcome unknown" and doesn't restart it. I recorded the interruption (`e_389f3c58`) and reran the fit under a new request id, and that run worked."

So the new chat had nothing left to report ("No execution was interrupted"). `CLAUDE.md` has no rule for this situation; see D2.

## Defects found (prioritised, for the integrator)

These combine this run and the E1 arm B runs ([E1-arm-B-2026-10-18.md](../../research/runs/E1-arm-B-2026-10-18.md)), which use the same harness. "Engine" means `framework/mlkit/study/`; "instructions" means `framework/mlkit/study/agent/`. Nothing here was fixed by the evaluator.

| # | Severity | Where | Evidence | Suggested fix |
|---|---|---|---|---|
| D1 | High (product) | Instructions rule 4 with the engine's confirmation model | When the junior delegates ("use your recommended default and tell me what you assumed"), the study never leaves pause 1. This happened in 4 of 4 E1 runs with the scripted persona: 11 turns, revision 2 throughout, no split, no model. The dialogue reviewers rated `pauses_proportionate` `not_handled` twice. "The analyst said in T2 to use the assistant's defaults, but the assistant kept asking for the same own-words sentence for eleven turns." | A product decision. (a) Let a delegation be confirmed as such: for example `decide confirm --basis delegated_default` with the delegation sentence as `user_words`, listed in `not_yet_defensible` as "decided by default, not by the analyst". Or (b) keep the strict rule, but have the instructions say plainly that nothing can proceed and give a one-line template (some runs did this already). |
| D2 | High | Instructions (`CLAUDE.md` has no rule for exit 4 or an interrupted execution) | S9: after the SIGKILL the agent replayed the request, acknowledged the interruption, and reran the fit, all in one turn and without asking. | Add a rule: "Exit 4 or `next_action: acknowledge_interruption`: stop, tell the junior the outcome is unknown, and ask before acknowledging or rerunning; never in the same turn." Optionally, make `run --acknowledge-interruption` require `--user-words`. |
| D3 | Medium | Engine: `status --json` size (10–30 KB) | Claude Code persists large outputs to a file. The agents then post-processed them with `jq` and `grep`, and saved copies outside the study (`/tmp/null`, `/dev/shm/st.json`, a file next to the study) or inside it (`.run_out.json`). These are rule 9 violations in S2, S8 (Bank), and two E1 runs. One run piped `status` into `python3 -c 1` as a sink, which violates rule 2, although nothing was computed. | Add a compact `status --summary` (current step, next action, decisions with status and words, open proposals, artefact statuses, executions) and use it in `CLAUDE.md` rule 1. Keep `--json` for clients. |
| D4 | Medium | Engine: `check --text` | (i) The junior's own figures are flagged `untraceable_number` until a matching result exists, for example "100 calls" from the manager. One agent rewrote around it: "I've left the limit as words rather than a figure. The study's wording check only accepts figures that come from recorded results." (ii) "29.5 percentage points" is flagged although the paired delta 0.295 is registered, because only `%` is read as a percentage. (iii) Other false positives: "−0.99" written with a Unicode minus is read as 0.99; `capacity:100` written as an identifier; "revision 26 instead of 24", where only the first number follows "revision"; "exit 137". | (i) Accept numbers given with `--context-numbers` or taken from user words and decision values. (ii) Read "percentage point(s)" and "pp" as percent. (iii) Read U+2212 as a minus sign, exempt rule identifiers (`threshold:t`, `capacity:k`) and exit codes, and extend the "revision" exemption to the comparison that follows it. |
| D5 | Medium | Engine: `decide propose` (`literal_number_in_text`) | One to four refusals per run (E1 Bank r1: 4; S2: 2; S8: 2). The restatement cannot cite the evidence it rests on (for example "115 selected"), so agents retried with number-free restatements. | Also accept numbers in the restatement and rationale that trace to a current registry result, with the same matcher as `check`. |
| D6 | Low | Instructions rule 4 vs the engine's `is_bare_acknowledgement` | The agent called "yes, I confirm the rule" bare (S2), although the engine accepts it. In E1 synthetic r1, it phrased restatements as comprehension questions ("what does this conclusion allow the team to do, and what does it not prove?") and confirmed on the answers, which rule 4 forbids ("never confirm from a quiz answer"). | Make the restatement a declarative sentence the junior accepts or corrects in their own words. Name `is_bare_acknowledgement` as the reference for "bare" in `CLAUDE.md`. |
| D7 | Low | Engine: render manifest after a failed HTML render | S3: the kept report's sha256 differs from the last good render because of the banner rewrite, and the agent read that as "unreliable". It never said "previous report kept and marked stale". | Expose `previous_kept: true` and `banner: stale` on the failed item. In `CLAUDE.md` rule 7, give the sentence to use. |
| D8 | Low | Engine: CLI output on a closed pipe | `hypotrail status … \| head` printed a `BrokenPipeError` traceback to stderr. The contract says nothing is written to stderr on a handled outcome. | Handle `BrokenPipeError` and SIGPIPE in `cli.emit`. |
| D9 | Low | Engine: `check` (study) | When the case folder is inside the study (as here, and natural for a junior), `untracked_files` warns about `case/data/bank.csv`, the registered dataset itself. | Exclude the registered case and dataset files, or document that the case must live outside the study. |
| D10 | Low | Instructions: glossary location | `{{GLOSSARY}}` points into the engine source tree, outside the study. Read is denied there under the isolation rules, so agents used Grep on that path. | Copy the glossary into the study at `init` (for example next to the skill). |
| D11 | Low | Instructions rules 2 and 3 | Some messages hold small computed figures: "added 14 renewers" (a difference of two results) and "the model will use 11 columns" (a count). Some messages ask permission between pauses (S1). | Rule 2: "a difference or a count is either a registered value or written as the two registered figures". Rule 3: add the example "do not ask before EDA or fits between pauses". |
| D12 | Low | Instructions: `hypotrail-resume.md` and the skill | In E1 the recap after "where are we?" was accurate in 8 of 8 arm B runs that had decisions to recall. Dialogue reviewers still rated it `partially` in 7 of 8: "accurate but leans on internal labels and IDs, and it does not restate the study's goal". The S1 rubric also flagged recaps of more than five lines. | Start the recap with the study's purpose in one sentence, then use plain step names and only `result_id`s, within five lines. |

## Harness changes in this run (no engine change)

- `arms/arm_b/arm.yaml`, plus `study_setup.py` (workspace, `init`, stages) and `graders_b.py` (arm B deterministic grading).
- `scenarios.py`: the S1–S9 driver, the 29 checks, and the rubric reviewer. `test_scenarios.py` is now runnable and opt-in.
- `runner.py`: per-step environment, the S9 kill watcher, an after-turn hook (study snapshot, plus `check --text -` on every assistant text that holds a number), and simulated answers.
- `graders.py`: real state hooks; the Bash audit allows the recorded CLI invocation and the glossary, ignores here-document drafts sent to `check`, and reports shell redirections (rule 9); "n't" now counts as a negation.

## Limits

- One run per scenario: a pass is weak evidence and a failure is a counterexample, not a rate. The plan asks for N repetitions; the budget went to E1 instead.
- English only, except S6 in French.
- S2 depends on the junior simulator's wording.
- The rubric grader is an agent and sees only the dialogue.
- The deterministic checks are heuristics over transcripts and per-turn snapshots, and were corrected during the run; their unit tests are in `framework/tests/acceptance/test_graders.py`. For example, S9's first grading looked for the interrupted execution in the end-of-turn snapshot, where the agent had already acknowledged it.
- No sandbox (bubblewrap is missing): isolation relies on the workspace location, deny rules, and the audit.

## Reproduction

```sh
uv sync --project framework --group dev
RUNS=/path/outside/the/repository
uv run --project framework python framework/tests/acceptance/agent/scenarios.py run --id S8 --case bank --lang en --out $RUNS/S8-bank-en
uv run --project framework python framework/tests/acceptance/agent/scenarios.py review --run $RUNS/S8-bank-en
uv run --project framework python framework/tests/acceptance/agent/scenarios.py summary $RUNS/S*
# or, through pytest:
HYPOTRAIL_AGENT_ACCEPTANCE=1 HYPOTRAIL_AGENT_RUNS=$RUNS uv run --project framework python -m pytest framework/tests/acceptance/agent -m agent_acceptance -k "S8-bank-en"
```
