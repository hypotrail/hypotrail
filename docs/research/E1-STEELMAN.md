# E1 steelman protocol: does a good skill make the engine unnecessary?

Status: protocol for plan WP0.8 (amendment A5). Arm A was run on 18 October 2026; see [runs/E1-arm-A-2026-10-18.md](runs/E1-arm-A-2026-10-18.md). Arm B waits for the `hypotrail` CLI (plan Phase 4).

Results are **Claude Code acceptance** (plan A1). They are not Copilot acceptance, and they do not measure human comprehension.

## Question

The plan builds an engine: state, registry, exposure tracking, and a `check` command. A strong alternative needs no engine. It is a capable agent with a good pedagogy skill and an ordinary notebook. E1 asks whether that alternative already produces a valid, traceable junior study. If it does, the engine should shrink.

## Hypotheses

- **H1 (structural traps).** Even with a good skill, arm A fails traps that the engine prevents by construction. Examples are EDA before the split, a refit on a capacity change, decisions lost between chats, untraceable numbers, and "ok" recorded as a decision. Arm B should pass them because of how the engine is built, not because the instructions are well worded.
- **H2 (knowledge traps and recitation).** Arm A handles knowledge traps on Bank Marketing, such as the `duration` leakage, the `pdays = -1` sentinel, and the accuracy paradox. Models have probably memorised that dataset. It handles them less reliably on the contamination-free synthetic case, where only the documentation and the data can reveal them.
- **H0 (steelman holds).** Arm A passes the structural traps on both cases. The engine is then reduced to the registry and `check`, as WP0.8 requires.

## Arms

| Arm | Agent | Instructions | Computation | Persistence |
|---|---|---|---|---|
| A | Claude Code (`claude -p`, model alias `opus`) | `CLAUDE.md` with 8 rules and the `ml-study` skill (`framework/tests/acceptance/agent/arms/arm_a/`) | `.venv/bin/python` with pandas, scikit-learn, and marimo; no Hypotrail code | `STUDY.md` written by the agent; an empty Marimo notebook template |
| B | Same agent, model, and persona | Plan §5 instructions copied by `hypotrail init` | `hypotrail` CLI only (Bash audit forbids ad hoc computation) | `.hypotrail/` state, registry, generated notebook, HTML |

Arm A is a steelman. Its skill contains everything the plan expects a good guide to know:

- the four moments and a visible plan;
- term-first vocabulary;
- an availability and leakage checklist;
- split before EDA;
- sentinel checks;
- a baseline and the accuracy paradox;
- the threshold-on-validation caveat;
- no refit when only capacity changes;
- a proportionate conclusion that avoids "lost sales";
- decisions recorded with the analyst's exact words, where "ok", "keep that", and "garde ça" are not confirmations.

The skill names no dataset or column. The same files serve both cases.

The arm instruction files are stored under names Claude Code does not load (`CLAUDE.md.in`, `dot-claude/`). The runner copies them to `CLAUDE.md` and `.claude/skills/ml-study/SKILL.md` in the workspace. This keeps developer sessions in the repository from picking them up.

## Cases and contamination check

| Case | Copied into the workspace | Kept from the agent |
|---|---|---|
| Bank Marketing | `bank.csv`, the original `bank-names.txt`, and a neutral README of the scenario: prioritise calls **before calling**, with limited call capacity (`cases.py`) | The repository's tutorial material, which names the leakage and the split |
| Synthetic (WP0.9, seed 20261018, 4,000 rows, 12 % positives) | `data.csv` and a README generated from the `case.yaml` descriptions and special values | `truth.json` (written to a hidden directory outside the workspace); `case.yaml` availability statuses |

The Bank README says nothing about `duration`, leakage, sentinels, or splits. The synthetic README carries only what the membership office documents. For example, `desk_followups` is "logged … after the renewal cycle closed", and `reminders_sent` "includes the last one". The agent has to infer that the first is unusable and the second is ambiguous.

**Contamination reading.** A trap passed on Bank but failed on the synthetic case counts as recitation, not guidance. Only results that hold on both cases are attributed to the arm.

## Persona and conversation

The script is `framework/tests/acceptance/agent/e1_persona.yaml`. The persona is a cooperative, terse junior analyst who is new to ML. The script has two chats and 11 utterances, and every utterance is generic. None names a column, so the same script follows any agent's plan.

| # | Chat | Label | Utterance (verbatim) | What it probes |
|---|---|---|---|---|
| 1 | 1 | intent | "Hi! I'm a junior data analyst … whom to call first … Please explain things as we go." | Framing, first contact, plan |
| 2 | 1 | accept_plan | "That plan looks good to me … use your recommended default and tell me what you assumed." | Assumptions vs decisions |
| 3 | 1 | ok | "ok" | Ambiguous reply |
| 4 | 1 | garde_ca | "garde ça" | Ambiguous reply (French) |
| 5–6 | 1 | continue | "Please continue with the plan." / "Great, thanks. Keep going with the next steps." | Authorised work without over-asking |
| 7 | 2 (new session) | where_are_we | "where are we?" | Resumption from persistent state |
| 8 | 2 | continue_3 | "Please continue until we have a model and a recommendation for how many people to call." | Modelling, selection rule |
| 9 | 2 | keep_that | "keep that" | Ambiguous reply (English) |
| 10 | 2 | capacity_100 | "News from my manager: the team can make only 100 calls in the next campaign. What does that change?" | Capacity change without refit |
| 11 | 2 | conclusion | "Can you write the conclusion for my manager? What should we do?" | Proportionate conclusion |

## Planted traps

| Trap | Bank | Synthetic (from `truth.json`) | Deterministic check (`graders.py`) | Blind reviewer check |
|---|---|---|---|---|
| T1 Leakage | `duration` (known after the call) | `desk_followups` (recorded after the outcome; exact AUC in truth) | Column absent from the final features the reviewer lists | `leakage_post_outcome` |
| T1b Ambiguous availability | `campaign` (includes the last contact), `contact`, `day`, `month` | `reminders_sent` (stops when the member renews), `last_reminder_weekday` | A target-dependent column used without any flag in `STUDY.md` or the notebook | `availability_at_prediction_time` |
| T2 Sentinel | `pdays = -1` and `poutcome = unknown` on the same rows | `days_since_last_lapse = -1` and `last_lapse_reason = unknown` on the same rows | Both columns and `-1` named; co-occurrence noted | `special_values` |
| T3 Accuracy paradox | 11.5 % positives | 12 % positives | (reviewer only) | `class_imbalance_metrics` |
| T4 EDA before the split | — | — | Order of the first target-conditioned computation and the first split in the agent's code (heuristic) | `split_before_eda`, `eda_on_training_only` |
| T5 Threshold chosen on validation, then presented as performance | — | — | (reviewer only) | `threshold_selection_caveat` |
| T6 Refit on a capacity change | — | — | A fit executed during the capacity turn, inline or through a script or notebook that contains a fit | `capacity_change_handling` |
| T7 "Lost sales" | — | — | Unnegated "lost sales/subscriptions/renewals …" in replies or `STUDY.md` | `causal_language` |
| T8 Decision lost between two chats | — | — | In the "where are we?" turn: the record was read before answering, and the answer names the leakage exclusion | `decisions_recorded` |
| T9 Hallucinated number | — | — | Every number in replies traces to grader-recomputed data facts, the agent's tool outputs or code, or the user's words and documents | `numbers_traceable` |
| T10 Ambiguous confirmation | — | — | `STUDY.md` records a confirmed decision whose user words are only "ok", "garde ça", or "keep that" | Transcript reviewer `ambiguous_reply_handling` |

T1 to T9 are the WP0.8 traps. T1 splits the plan's "`duration`, and `campaign`" item into T1 and T1b. T10 adds the S6 "ok"/"garde ça" invariant.

**Number grader (b) for arm A.** Arm A has no registry, so the allowed set is built from four sources. The first is facts the grader recomputes from the whole file: counts, rates, category rates, numeric summaries, and sentinel counts. The second is numbers printed or written by the agent's own tool calls. The third is the user's words and the case documents. The fourth, flagged separately, is the exported notebook. A number matches when it agrees at its displayed precision, including conversions between percentages and fractions. Bare integers up to 10 and plausible years are ignored. For arm B, the allowed set will be the registry values (`hypotrail check --text -`).

**Combining verdicts.** A deterministic failure wins. Otherwise the reviewer's verdict is used. When the two disagree, the result is `partial`. A heuristic that does not fire gives `unclear`, never a pass.

## Blind review

After each run, `e1.py review` launches two fresh `claude -p` reviewers. Each runs in a temporary directory outside the repository with an empty configuration, read-only tools, and a JSON schema.

1. **Study reviewer** (`rubrics/blind_review.md`). It receives only the study folder: data, documentation, `STUDY.md`, the notebook, and any scripts and outputs. `CLAUDE.md`, `.claude/`, and the environment are removed, and absolute paths are replaced. Nothing identifies the arm. It returns:
   - 15 validity checks, each with a verdict and quoted evidence;
   - the final model's features as the study describes them;
   - an overall validity rating.
2. **Dialogue reviewer** (`rubrics/transcript_review.md`). It receives only the analyst's messages and the assistant's replies, with tool calls omitted. It returns nine guidance checks: plan visible, term-first vocabulary, one question at a time, ambiguous replies, explicit assumptions, resumption, capacity change, conclusion, and proportionate pauses.

`e1.py grade` then scores the traps. For the synthetic case it compares the reviewer's extracted feature list and the deterministic findings against `truth.json`. The reviewer itself never sees `truth.json`.

## Qualitative go/no-go

There is no numeric threshold (WP0.7). Every trap failure is read in the transcript.

- **Continue the engine as planned** if arm A fails, on either case, traps that arm B prevents structurally (T4, T6, T8, T9, T10), or fails knowledge traps on the synthetic case that it passes on Bank (recitation).
- **Reduce the engine to the registry and `check`** if arm A passes the structural traps on both cases across repetitions, and its failures are limited to wording that instructions can fix.
- **Rework the instructions first** if arm A's failures come from the skill's content rather than from missing state: for example, a rule the skill states but the agent ignores, or a rule the skill omits.

## Limits

- E1 measures the **validity of an agent's work**. It does not measure a human junior's understanding. A scripted persona cannot be confused, push back, or misunderstand. The persona's generic replies may also leave a pending question unanswered, which the arm then has to handle.
- Two runs per case is a small sample. Agent runs are non-deterministic, so a single success proves little, and a single failure is a counterexample, not a rate.
- The deterministic graders are heuristics over transcripts. EDA order and refit detection depend on code patterns, and the number tracing accepts any number the agent printed: a wrong computation that was printed counts as traceable. The blind reviewer is itself an agent, and it can be wrong.
- For arm A, the number grader (T9) has little power. In the 18 October runs, a random two-digit count or two-decimal fraction matched the pool of numbers the agent printed about 100 % of the time, and a one-decimal percentage 32–43 % of the time. Its "pass" is weak evidence until a registry exists (arm B).
- The blind reviewer sees the folder, not what was executed. In the 18 October runs it accepted every agent's "no retraining" claim, which the transcripts contradict (T6). Process claims must be checked against the transcript, not against the study.
- Bank is public. Even a perfect arm A on Bank says little, which is why every conclusion requires the synthetic case.
- No Bash sandbox is available in the test environment (bubblewrap is missing). Isolation relies on a separate workspace, deny rules for the repository and the hidden directory, an audit of tool calls, and a repository snapshot taken before and after each run.

## Running E1

```sh
uv sync --project framework --group dev
RUNS=/path/outside/the/repository
uv run --project framework python framework/tests/acceptance/agent/e1.py run --case bank --repeat r1 --out $RUNS/bank-r1
uv run --project framework python framework/tests/acceptance/agent/e1.py run --case synthetic --repeat r1 --out $RUNS/synth-r1
uv run --project framework python framework/tests/acceptance/agent/e1.py review --run $RUNS/bank-r1
uv run --project framework python framework/tests/acceptance/agent/e1.py grade --run $RUNS/bank-r1
uv run --project framework python framework/tests/acceptance/agent/e1.py summary $RUNS/bank-r1 $RUNS/synth-r1
```

Each run has these caps by default:

- 80 agent turns per utterance;
- $15 per chat session (Claude Code applies `--max-budget-usd` to the session's cumulative cost);
- $40 per conversation;
- 30 minutes per utterance.

Raw runs (transcripts, workspaces, `truth.json`) stay outside the repository. Only the summarised report goes into `docs/research/runs/`.

## Appendix: running Claude Code non-interactively (checked with CLI 2.1.302)

- `claude -p PROMPT --output-format stream-json --verbose` works non-interactively. The stream contains:
  - an `init` event with the session id, model, tools, skills, plugins, MCP servers, and CLI version;
  - every assistant message with its `tool_use` blocks;
  - every `tool_result`;
  - a final `result` event with the reply, `num_turns`, `total_cost_usd`, and `modelUsage`.

  `--output-format json` gives only the final `result`, so the harness uses `stream-json`.
- `--resume <session_id>` continues a conversation with its memory. A process started without `--resume` knows nothing of earlier chats. Both behaviours were verified.
- These flags are honoured in print mode:
  - `--max-turns`;
  - `--max-budget-usd`;
  - `--permission-mode dontAsk` combined with `--allowedTools` (tools that are not allowed are denied without prompting);
  - `--tools` (restricts the tool set);
  - `--json-schema` (structured output in `result.structured_output`, used by the reviewers).
- **Inherited environment leaks.** A child launched from inside a Claude Code session inherits several things:
  - the parent's `CLAUDE_CODE_SESSION_ID`, so it reports the parent's session id;
  - the user's synced skills, including pedagogy skills that would contaminate an arm;
  - plugins and MCP servers.

  The runner therefore starts each run with a scrubbed environment and an empty `CLAUDE_CONFIG_DIR`. Authentication still works through the environment's proxy. The child then gets a fresh session id, no user skills, no MCP servers, and no hooks. Claude Code's built-in skills, such as `dataviz` and `deep-research`, remain.
- **Auto memory** is on by default. In a probe, the agent saved a "remember this" note into the configuration's `memory/` directory, which would carry facts across "new chats". The runner disables it with `--settings '{"autoMemoryEnabled": false}'` and `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`. With it disabled, `memory_paths` disappears from `init`.
- **Instruction files (A2).** These were verified with marker files and match the [official memory documentation](https://code.claude.com/docs/en/memory):
  - `CLAUDE.md` and `.claude/CLAUDE.md` load from the working directory and every ancestor;
  - `AGENTS.md` loads from the working directory and every ancestor only when no `CLAUDE.md` exists there or above (the default `claude-md-or-agents-md` setting);
  - subdirectory files load on demand when the agent reads a file there;
  - `/etc/claude-code/CLAUDE.md` (managed) always loads, and is absent here.

  Consequences:
  - A study inside the repository with its own `CLAUDE.md` would *not* load the root `AGENTS.md` by default, but any ancestor `CLAUDE.md` would load.
  - A study without one would load the root development instructions.
  - Developer sessions would load an arm's `CLAUDE.md` if it were stored under that name in the repository.

  The runner refuses any workspace inside the repository or under an ancestor instruction file.
- **No sandbox.** The `sandbox` setting needs bubblewrap and socat, which are missing here. Claude Code warns and runs commands unsandboxed. The safeguards that replace it are listed under Limits.
- **Costs on resume are cumulative.** In a resumed turn, `result.total_cost_usd` is the session's cumulative cost, not the turn's. `--max-budget-usd` is checked against that cumulative value: a resume with a budget below the session's past cost answers once and ends with `error_max_budget_usd`. The runner records the per-turn increment (`cost_usd`) and the cumulative value (`session_cost_usd`) separately. `e1.py grade` recomputes per-turn costs for runs recorded before that fix.
- The default model here is `claude-sonnet-5-5`, and `--model opus` resolves to `claude-opus-5-5`. Each turn records the model ids from `modelUsage`.
