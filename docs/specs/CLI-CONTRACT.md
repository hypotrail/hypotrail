# CLI and study contract (`hypotrail`, v0.1)

Status: **frozen** at the end of Phase 1 (plan `docs/plans/V0.1-IMPLEMENTATION-PLAN.md` §4, §8, §9 bis). Implemented in `framework/mlkit/study/`. Frozen by `framework/tests/study/test_contract_freeze.py`.

Phase 2 (activities) and Phase 3 (deliverables) are built in parallel on this contract. They may **add** what the extension points below allow. They must not rename, remove, or change the meaning of anything listed here. A change goes through the integrator: bump the schema version (`/1` to `/2`), update this document and the contract test in the same commit.

Consumers: the chat agent (Claude Code under directive A1), the HTML report, the generated notebook and workbench, and later a webview client (ADR 0002). All of them read the same JSON and write only through the same commands.

## 1. Invocation

```sh
uv run --project framework hypotrail <command> ... --study DIR
python -m mlkit.study.cli <command> ... --study DIR     # same program
```

| Rule | Detail |
|---|---|
| Study location | `--study DIR` is required by every command. The study is never taken from the current directory or from `OSML_ROOT`. A study is a directory with a `.hypotrail/` marker. |
| Output | Exactly one JSON document on stdout, then a newline. `--json` selects it explicitly; `--format text` prints a short human summary instead (not a contract). Nothing is written to stderr on a handled outcome. |
| Mutations | Every mutation is one request `{request_id, expected_revision, action, params}` applied by `mlkit.reliability.apply_command` under the writer lock. `--request-id` and `--expected-revision` are required on every mutating command. |
| Idempotency | Replaying a `request_id` with the same request returns the stored receipt with `replayed: true` and writes nothing. The same `request_id` with a different request is refused (`idempotency_conflict`). A replay is recognised before the revision check. |
| Revision | `expected_revision` must equal the current revision, otherwise `stale_revision` with `details.current_revision` and `details.changes_since` (the revision records the client has not seen). |

### Commands (v0.1)

```text
hypotrail init --case CASE --study DIR [--lang en|fr]
hypotrail status --study DIR [--since REV] [--json] [--summary]
hypotrail plan --study DIR
hypotrail decide propose DECISION (--value TEXT | --value-json JSON)
                 --restatement TEXT --rationale TEXT [--lang en|fr]
                 [--restatement-en TEXT] [--restatement-fr TEXT]
                 --request-id ID --expected-revision REV --study DIR
hypotrail decide confirm (PROPOSAL | --proposal PROPOSAL) --user-words TEXT
                 [--channel chat|cli|webview] [--actor NAME]
                 [--basis explicit|delegated_default]
                 [--delegation-scope this_decision|standing] [--agent-concern TEXT]
                 --request-id ID --expected-revision REV --study DIR
hypotrail decide withdraw PROPOSAL [--reason TEXT]
                 --request-id ID --expected-revision REV --study DIR
hypotrail decide note (--about DECISION | --resolve NOTE_ID | --withdraw NOTE_ID) --text TEXT
                 [--kind hold|correction]
                 --request-id ID --expected-revision REV --study DIR
hypotrail mode set guided|training|express --user-words TEXT
                 --request-id ID --expected-revision REV --study DIR
```

`--channel` defaults to `chat`, `--actor` to `user`, and `--basis` to `explicit` (§5). `--delegation-scope` has no default and goes with `--basis delegated_default` only (§5, R1). Reserved extension commands, absent in Phase 1 and refused with `unsupported_capability` until their module exists: `run`, `render`, `check`, `preview` (§8). Phase 3 adds `render` and `check` (§8.3). Post-v0.1 adds the read-only `session-report` (§8.6) and `decide note` (P2, §5.1); the post-v0.1 fixes add `decide note --withdraw` (D5, §5.1). v0.2a (ADR 0005, §5.2) adds `init --lang`, `decide propose --lang/--restatement-en/--restatement-fr`, `decide confirm --proposal` (the same as the positional `PROPOSAL`; giving both or neither is `invalid_arguments`) and `--agent-concern`, `decide note --kind correction` (`--user-words` is an alias of `--text`), and `mode set`.

## 2. Exit codes

| Code | Meaning |
|---|---|
| `0` | Success, or replay of a committed request |
| `1` | Internal error (unexpected exception); the payload is still `hypotrail.error/1` with code `internal_error` |
| `2` | Refusal without effect (any `hypotrail.error/1` with a stable code, including invalid arguments) |
| `3` | The command committed, but an artefact is `stale` or `failed` after rendering (WP3.4) |
| `4` | An execution has an unknown outcome (WP2.1, `run`) |

`status` and `plan` return `0` even when the study has interrupted executions or stale artefacts: they report them in the view.

## 3. Payload schemas

Every payload is a JSON object whose first keys are `schema` and `ok`. Keys are listed in their emitted order. Clients must ignore keys they do not know; producers must not remove listed keys within a schema version.

| Schema | Emitted by | Keys |
|---|---|---|
| `hypotrail.init/1` | `init` | `schema`, `ok`, `study`, `revision`, `case`, `dataset`, `structural_exposure`, `plan`, `next_action`, `agent_instructions`, `ignored_sources`, `note` |
| `hypotrail.status/1` | `status` | `schema`, `ok`, `study`, `revision`, `since`, `changed`, `changes_since`, `view` |
| `hypotrail.plan/1` | `plan` | `schema`, `ok`, `study`, `revision`, `steps`, `current_step`, `next_action` |
| `hypotrail.decide/1` | `decide …` | `schema`, `ok`, `study`, `action`, `request_id`, `replayed`, `revision`, `result`, `artifacts` |
| `hypotrail.error/1` | any refusal | `schema`, `ok` (`false`), `command`, `error` |
| `hypotrail.summary/1` | `status --summary` | `schema`, `ok`, `study`, `revision`, `since`, `changed`, `goal`, `current_step`, `plan`, `next_action`, `open_proposals`, `decisions`, `results`, `artifacts`, `executions`, `not_yet_defensible`, `notes`, `holds`, `recap` |

* `status --summary` (D3, post-acceptance) prints a compact digest of the view (`view.summary`) for chat agents, a few kilobytes instead of the full view; `status --json` is unchanged and stays the client contract. `goal` is `{intended_use, decision, observation_unit, prediction_time}`: the first three are the case facts of those ids (`{value, status}` or `null`), `prediction_time` is `{value, source: decision|case, status}` (the decision value when there is one, else the case fact). `plan` lists the steps as `{id, title, status}`. `decisions` maps each decision to `{status, value, basis, delegation_scope, user_words, reason, open_proposals}` (a `feature_availability` value is grouped as `{status: [features]}`); `open_proposals` items are `{proposal_id, decision_id, value, restatement, revision}` (the restatement in the study language, `label`, is in `status --json` only, §5.2); `results` maps a slot to `{result_id, current, stale_reason, integrity}`; `artifacts` is `{status, items: {name: {status, revision, last_ok_revision, message}}}`; `executions` is `{active: [ids], interrupted: [{execution_id, activity, reason}], late: [{execution_id, activity, reason, result_id}], suspected_interrupted: [{execution_id, activity, liveness, reason}]}` (`active` lists only executions whose lease is held; see execution liveness, §3); `not_yet_defensible` is `{top: [{id, text}] (at most five, most urgent first), more: [ids]}`. `notes` (post-v0.1, P2; additive, before `recap`) lists every note of the study, oldest first, as `{note_id, decision_id, status, user_words, resolution_words}` (`view.SUMMARY_NOTE_KEYS`; `resolution_words` is `null` while the note is open, and holds the junior's resolving or withdrawing words otherwise). `holds` (post-v0.1 fixes, D5; additive, between `notes` and `recap`) groups the **open** holds by decision, in plan order: `[{decision_id, status, notes: [{note_id, user_words}]}]` (`view.SUMMARY_HOLD_KEYS`; `status` is the decision's status), so a restated hold is seen next to the one already recorded; `[]` when none is open.
* `summary.recap` (post-v0.1, acceptance T8 and F5; additive, the schema stays `/1`) is a list of exactly five strings, generated deterministically from the state by `view.recap`, that a new chat may quote to resume. Each starts with its label (`view.RECAP_LABELS`): `Goal` (the intended use and the prediction moment, the decision value or the case statement marked "from the case, not decided yet"), `Decided` (each confirmed decision in plan order, the feature availability with its excluded features by name and the doubtful ones kept, the split method and validation share (an ordinal cutoff names its column and cutoff), the policy rule of a binary study or the model choice of a regression study ("model choice: the linear model" or "the mean baseline"; M3), the conclusion verdict; "[delegated to the assistant]" or "[to confirm again]" when it applies; "nothing yet"), `Now` (the current step's title and the generated deliverables that are not up to date), `Next` (the next decision or action in words; an open proposal's restatement is quoted as recorded, so a stand-in figure keeps its caveat; an execution with an unknown outcome comes first), and `Limit` (the most urgent `not_yet_defensible` text other than `unconfirmed_decisions`). It holds no revision number, proposal, execution, or result id, with two exceptions. A binary study (post-v0.1 fixes, D10) whose `policy.evaluation` is current and verified cites the headline result of one evaluated rule: the adopted rule when it was evaluated, else the rule of the open policy proposal, else the first evaluated rule; the logistic model's precision and recall at that rule, in percent with one decimal as the report shows them, on the evaluation's `n` validation rows, with the first 8 characters of that result id: in `Decided` after an adopted policy ("policy capacity:100 (the logistic model at capacity:100 on the 90 validation rows: precision 31.0%, recall 54.5%, result 1a2b3c4d)"), otherwise in `Now` ("(latest policy evaluation: the logistic model at ...)"). And (P3) a regression study whose `evaluate.regression` is current and verified cites its validation MAE, as displayed with two decimals, in the target unit, with the first 8 characters of that result id: in `Decided` for a confirmed model choice ("model choice: the linear model (validation MAE 6.31 mpg, result 1a2b3c4d)"), otherwise in `Now` for both models. An open hold (P2, §5.1) is quoted in `Next` in the junior's words ("On hold in the junior's words: \"...\" (the policy); nothing on hold is confirmed until they resolve it."), the holds of one decision together ("\"a\"; \"b\" (the policy)", D5), so `open_holds` is not repeated as the `Limit`; nor is `conclusion_outdated` (D2), which `Decided` ("[to confirm again]") and `Next` already say. Each line is one flat line (whitespace collapsed, no line break). The deliverable messages hold no revision number either (P3, §8.3). A regression study's recap never uses the vocabulary of a decision rule (threshold, positive class, precision, recall, capacity): its texts come from the task-aware plan, next action, and limits.
* `status.since` is the `--since` value or `null`; `changed` is `revision > since` (or `null`); `changes_since` lists the revision records after `since` (or `null`). A webview polls with `--since`.
* `decide.revision` is the revision created by the request (also on replay). `artifacts` is `null` until Phase 3 renders after commits (§8.3).
* `init.agent_instructions` is `{source, copied, skipped_existing, status, cli, agent_file, glossary}`; `glossary` is the study path of the glossary copy (§8.4); `status` is `copied`, `kept_existing`, or `no_templates_yet`; `cli` is the exact shell command that runs this CLI (§8.4) and `agent_file` is `.hypotrail/agent.json`. `copied` and `skipped_existing` list workspace paths. `ignored_sources` names the companion files found next to the case (`project.json`, `results.json`, `tutorial-results.json`, `answers.yaml`, `project.yaml`, `frame.yaml`); they are never read. `structural_exposure` is `{exposure_id, n_rows}`.
* `error` is `{code, message, details?, problems?}`. `problems` (case validation) is a list of `{path, problem}`.

### 3.1 Plan steps and next action

Each item of `plan.steps` and `view.plan` has the keys `id`, `title`, `question`, `expected_output`, `completion`, `pause`, `decision`, `activities`, `decide_first`, `missing_results`, `requires`, `status`, `current`. Step ids, in order: `prediction_time`, `feature_availability`, `split`, `train_eda`, `models`, `policy`, `conclusion`; for a regression study (§10) `prediction_time`, `feature_availability`, `split`, `train_eda`, `models`, `model_choice`, `conclusion`. Step status is one of `done`, `needs_reconfirmation`, `awaiting_confirmation`, `ready`, `blocked`.

`next_action` always has `kind` and `message`. Kinds and their extra keys:

| `kind` | Extra keys |
|---|---|
| `outcome_unknown` | `execution_id`, `activity` (closure fix F1: emitted by `status` only, first in priority, when an active execution's lease is not held) |
| `acknowledge_interruption` | `execution_id` |
| `reconfirm` | `decision` |
| `await_user_words` | `proposal_id`, `decision` |
| `blocked` | `step`, `requires` |
| `propose` | `step`, `decision` |
| `run` | `step`, `activity` |
| `done` | — |

### 3.2 Decide results

| Action | `result` keys |
|---|---|
| `decide.propose` | `proposal_id`, `decision_id`, `status` (`open`), `decision_status`, `superseded`, `restatement` |
| `decide.confirm` | `decision_id`, `proposal_id`, `status` (`confirmed`), `value`, `user_words`, `channel`, `actor`, `invalidation`, `basis` (the recorded basis: `endorsed`, `restated` or `delegated_default`, §5.2), `delegation_scope`, `agent_concern` (ADR 0005, R3: the `--agent-concern` text or `null`), `warnings` (ADR 0005: `[]`, or for `feature_availability` the `words_contradict_value` warnings `{code, variable, said, value, message}`, §5.2; never a refusal) |
| `decide.withdraw` | `proposal_id`, `decision_id`, `status` (`withdrawn`), `decision_status` |
| `decide.note` | `note_id`, `decision_id`, `status` (`open`, or `recorded` for a correction), `user_words`, `open_holds` (the open note ids of that decision), `reconfirm_required` (D1: the decisions the hold asks for again, `[]` unless the decision was confirmed; always `[]` for a correction), `kind` (ADR 0005: `hold` or `correction`) |
| `study.set_mode` | `mode`, `previous`, `user_words`, `changed` (ADR 0005, §5.2; the command is `mode set`, its payload the `hypotrail.decide/1` receipt) |
| `decide.resolve_note` | `note_id`, `decision_id`, `status` (`resolved`), `user_words` (the resolving words), `open_holds` |
| `decide.withdraw_note` | `note_id`, `decision_id`, `status` (`withdrawn`), `user_words` (the withdrawing words), `open_holds` (D5) |

`invalidation` is `{mutation, row, reason, stale_results, stale_slots, reconfirm_required}` (§6). Proposal ids are `p_<n>`, assigned in order; note ids are `n_<n>`. The actions of `decide note` are `decide.note` (parameters `{decision_id, user_words}`, from `--about` and `--text`) `decide.resolve_note` (`{note_id, user_words}`, from `--resolve` and `--text`), and `decide.withdraw_note` (`{note_id, user_words}`, from `--withdraw` and `--text`; D5).

## 4. View model `hypotrail.view/1`

`mlkit.study.view.build(study_dir, *, leases=None) -> dict` is the **single** view of a study. `status` prints it under `view`, built with a read-only lease probe (`leases`, closure fix F1; see execution liveness below). The HTML report, the generated notebook, and a future webview consume it; renderers do not read raw state. It holds no clock reading, so two builds of one study content are equal.

| Key | Content |
|---|---|
| `schema` | `hypotrail.view/1` |
| `study` | Absolute study directory |
| `revision`, `updated` | Current revision and its commit time |
| `case` | `{id, path, sha256}` |
| `dataset` | `{path, sha256, rows, row_key}` |
| `plan` | Steps (§3.1) |
| `current_step` | Id of the first step not done, or `null` |
| `next_action` | §3.1 |
| `open_proposals` | List of `{proposal_id, decision_id, value, restatement, rationale, revision, created, labels, label, origin}`, oldest first. `origin` (advanced companion, C9; additive, last: decision CI.6) is the stored `{channel}` of the proposal, or `null` for one recorded before C9. `labels` (ADR 0005; additive, before `origin`) is the stored `{language: restatement}` or `null`; `label` is the restatement in the study language (`state.label_of`: `labels[language]`, else `restatement`) |
| `decisions` | `{decision_id: {decision_id, status, value, proposal_id, depends_on, revision, reason, confirmation, open_proposals}}` for the five decisions |
| `facts` | `{by_status: {documented_fact: [...], scenario_assumption: [...], observed: [...], unknown: [...]}, count}`; items are `{id, value, source}` |
| `structure` | The case structure statements (`row_unit`, `group_column`, `time_column`, `duplicates`) |
| `results` | `{slot: result item}` for every promoted slot (below) |
| `stale` | `{result_id: {reason, since}}` |
| `invalidations` | The invalidation records (§6), oldest first |
| `executions` | `{active, interrupted, late, suspected_interrupted}` (filled by Phase 2; `suspected_interrupted` added by closure fix F1, see below) |
| `artifacts` | `{manifest, status, items}`; before any render `{manifest: null, status: "not_rendered", items: {}}` |
| `exposure` | `{records, rows_exposed, by_purpose, by_partition, validation_rows_used_for_selection, prior_exposure}` |
| `not_yet_defensible` | List of `{id, text, ...}` (plan §6) |

**Execution liveness (closure fix F1).** `status` stays read-only and takes no writer lock, but before reading the state it probes every execution lease with a read-only check (`lock.probe_leases`, built on `lock.lease_is_held`: the lease file is opened read-only and a non-blocking shared lock is tried). Each record of `view.executions.active` carries `liveness`: `running` (the lease is held, or the execution was reserved after the probe) or `not_checked` (a view built without a probe: the renderers, which stay deterministic per revision). An execution recorded as active whose lease file exists but is held by no process is **not** listed under `active`: it moves to `suspected_interrupted` with `liveness: "outcome_unknown"` and a `reason`; `next_action` is then `{kind: "outcome_unknown", execution_id, activity, message}` (first in priority), and the `interrupted_executions` item of `not_yet_defensible` lists it. The state is unchanged: the next `run` or `run --acknowledge-interruption` records it as `interrupted_unknown` (§8 item 5). An agent tells the junior the outcome is unknown, never calls such an execution "in progress", and asks before acknowledging.
| `settings` | `{bootstrap: {replicates, seed, level}}` |
| `task` | `binary` or `regression` (M3, additive): the task of the study, from `state.task` (a state written before M3 has none and is `binary`). The decisions, the plan steps, the activities, and the dependency table follow the task (§10) |
| `notes` | Post-v0.1 (P2, additive): the junior's conditions and holds, oldest first, each `{note_id, decision_id, kind, user_words, status, revision, resolution}` (`view.NOTE_VIEW_KEYS`); `kind` is `hold` or `correction` (ADR 0005), `status` is `open`, `resolved`, `withdrawn`, or `recorded` (a correction), `resolution` is `null` or `{user_words, revision, time, request_id}` (§5.1). Empty for a study without notes |
| `mode` | ADR 0005 (additive): the confirmation mode, `guided` (a state without `mode` is guided) |
| `language` | ADR 0005 (additive): the study language, `en` or `fr` (a state without it is `en`) |

`decisions.*.confirmation` is `null` or `{user_words, channel, actor, restatement, proposal_id, revision, time, authenticated, basis, delegation_scope, agent_concern}`. `authenticated` is always `false`: the engine records words, it cannot verify who typed them. `basis` is `endorsed`, `restated`, or `delegated_default` for a confirmation recorded since v0.2a (ADR 0005, §5.2), and `explicit` for one recorded before; a stored confirmation without it (written before the post-acceptance fixes) reads as `explicit`. `agent_concern` (ADR 0005, R3) is the point the agent raised before the junior confirmed, or `null` (also for a confirmation recorded before v0.2a). `delegation_scope` is `null`, `this_decision`, or `standing` (§5, R1); `null` for an explicit confirmation and for one recorded before R1. Decision status is one of `open`, `proposed`, `confirmed`, `reconfirm_required`, `superseded`.

A result item has the keys `slot`, `result_id`, `activity`, `current`, `stale_reason`, `partition`, `n_rows`, `values`, `blobs`, `params`, `inputs`, `code_fingerprint`, `environment`, `execution_id`, `exposure_id`, `started_revision`, `integrity`. Since review fix H2, `current` is derived (`read.Study.currency`): a result is current only if it is promoted and not stale in state, its activity's code is unchanged since it was computed (plan §3.7 row 11: every module of its code fingerprint still has the recorded sha256), and every result in its `inputs.results` (except the history role `previous_split`) is current too. A result that fails the derived rule has `stale_reason` `{reason, since: null, code_changed?: [modules], upstream_not_current?: [result ids]}`; `read.Study.is_current(slot)` and the artefact currency rule (§8.3) use the same rule. `integrity` is `ok` or the refusal code (`integrity_error`, `unknown_result`); a result that fails it has `current: false`, `values: null`, and adds a `result_integrity` item to `not_yet_defensible`. **Only a result item with `current: true` and `integrity: "ok"` may be cited.**

`not_yet_defensible` ids emitted in v0.1: `unconfirmed_decisions`, `validation_is_not_independent`, `public_data_already_explored`, `no_time_or_entity_identifier`, `uncertain_features_included`, `stale_results`, `interrupted_executions`, `no_causality`, `workbench_not_tracked`, `result_integrity`. Added by M3: `grouped_split_unsupported` (`column`, `capability`: the case declares a group column and this version has no grouped split; every split reports the group values its partitions share, `split.values.groups`, §10). Added by review fix L1: `sources_changed` (`changes`: `[{label, path, expected_sha256, actual_sha256}]`, the case or dataset file whose bytes differ from `state.case.sha256` / `state.dataset.sha256`; every result item is then `current: false` with `stale_reason.sources_changed`). Added by review fix H2: `code_changed` (`slots`: the current results whose activity code changed since they were computed). Added post-v0.1 (P2): `open_holds` (`notes`, `decisions`: the open holds, quoted verbatim in `text`). Added post-v0.1 (G.12), warnings computed by the view from current, verified results, never refusals: `small_validation_partition` (`slots: ["split"]`, `n_rows`, `min_rows`, and in a binary study `n_positive`, `min_positive`) when the current split's validation partition has at most `view.SMALL_VALIDATION_ROWS` (30) rows or, in a binary study, at most `view.SMALL_VALIDATION_POSITIVES` (5) positive rows (inclusive since the post-v0.1 fixes, D4: the boundary the plan calls small is small; before, "fewer than"), its `text` stating the counts (`view.small_partition_warning`); `capacity_exceeds_validation` (`rules`, `n_rows`) when the current policy evaluation holds a capacity at least as large as its validation rows, which "selects every row" (`view.capacity_warning`; `preview policy` returns both warnings for its rules, §8.1); `high_cardinality_grouping` (`slots`) when a current `eda.rate_by` or `eda.mean_by` folded values into `(other values)` (§8.5). Added by the post-v0.1 fixes: `conclusion_outdated` (D2; `decisions: ["conclusion"]`, `reason`: the conclusion's reconfirmation reason) while the conclusion is `reconfirm_required`, so its text may no longer describe the study; `inconclusive_without_choice` (D6; `decisions`: the policy or the model choice) when a confirmed (or to-reconfirm) conclusion is `inconclusive` and that decision is not confirmed. Added after the Claude Code acceptance run: `delegated_decisions` (`decisions`: every decision whose current confirmation has basis `delegated_default`, "decided by delegation to the assistant's default, not by the junior's own judgment") and `adopted_rule_not_evaluated` (`rules`: the adopted policy rule, confirmed or awaiting reconfirmation, when no current, verified `policy.evaluation` lists it in `params.rules`).

## 5. Decisions and values

| Decision | `--value` / `--value-json` | Confirmation needs |
|---|---|---|
| `prediction_time` | Non-empty text | — |
| `feature_availability` | `{feature: status}` for **every** variable with role `feature`; status ∈ `available_at_prediction`, `not_available`, `uncertain_excluded`, `uncertain_included` | `prediction_time` confirmed |
| `split` | `{"method": "stratified_random", "validation_fraction": f, "seed": n}` with `0 < f < 1` | `prediction_time`, `feature_availability` confirmed |
| `policy` | `"threshold:t"` (`0 <= t <= 1`, inclusive `>=`) or `"capacity:k"` (`k >= 1`); since review fix L2 one canonical spelling, `records.canonical_rule`: plain ASCII decimal digits, trailing zeros of `t` and leading zeros of `k` dropped (`threshold:0.30` is stored, evaluated and compared as `threshold:0.3`); signs, exponents, underscores (`capacity:1_000`), `nan`, `inf`, and a decimal `k` are refused. The proposal stores the canonical value, `run policy.evaluate --rule` evaluates canonical rules, and every comparison of rules is canonical | the three above, and a current `policy.evaluation` whose `params.rule` (or `params.rules`) contains the value |
| `conclusion` | `{"verdict": v, "text": "..."}`, `v` ∈ `adopt_policy`, `keep_baseline`, `inconclusive` | the three above, and `policy` confirmed when `v` is `adopt_policy` (post-v0.1 fixes, D6: `inconclusive` needs no adopted policy and is then named in `not_yet_defensible`, `inconclusive_without_choice`) |

Proposal rules:

* A proposal is first-class: `{proposal_id, decision_id, value, restatement, rationale, revision, status, created, request_id, basis}`; status ∈ `open`, `confirmed`, `withdrawn`, `superseded`. `basis` holds the confirmed values of the decisions it depends on.
* Proposing never changes a confirmed decision. A new proposal supersedes an older open one for the same decision.
* The restatement and rationale may only contain numbers that appear in the proposed value (a fraction may also appear as a percentage), or figures of a current, verified registry result, traced with the matcher of `hypotrail check` (`cmd_check.Pool`, current results only, at their displayed precision: "115 selected", "11.5%"); anything else is `literal_number_in_text`. Since the post-acceptance fixes (D5) this check runs on the state the proposal is made against. Since review fixes L3 and L4: a percentage (`%`, `percent`, `pour cent` after the number) may come from a fraction of the value (`30%` for `validation_fraction` 0.3) or a current result, never from another number of the value (`capacity:100` does not allow `100% precision`; the refused number is reported as `100%`); digits glued to letters are numbers (`top250`), and identifiers are masked first (`commands.IDENTIFIER`: `p_5`, `r_1a2b`, `r-…`, a hexadecimal digest prefix of 8 or more characters with a letter and a digit). **Conclusion (review fix M1).** The conclusion's `value.text` is traced when proposed, with the matcher of `check` on the current results and the recorded literals (confirmed decisions other than the conclusion, the junior's recorded words, the rules of the current evaluation), never on the proposed value itself: an untraceable or stale number is `literal_number_in_text` with `details.field` `value.text`; then causal or forecast wording (`check`'s `causal_wording` and `forecast_wording` rules) in the text, restatement, or rationale is `causal_or_forecast_wording` with `details.findings`.

Confirmation rules (`ambiguous_confirmation`, with `details.reason`):

| `reason` | When |
|---|---|
| `missing_user_words` | `--user-words` is empty or blank |
| `negative_reply` | The words refuse, hesitate, or disagree (review fix H1, narrowed by P1 after the post-v0.1 acceptance: a negation is a refusal only when it targets the agreement or the proposal; `commands.is_negative`). In order: (1) a refusal of the agreement anywhere (`commands.REFUSES_AGREEMENT`: "disagree", "pas d'accord", "désaccord", "hold on", "not so fast", "I don't agree", "I can't confirm", an imperative "don't adopt ...", "je ne valide pas", "I'm not sure"); (2) a reply that opens with a refusal: its first word in `commands.NEGATIVE_LEADS` ("no", "non", "nope", "wait", "stop", "attends", "cancel", "never", "hold", ...) or an opening of `commands.REFUSAL_OPENINGS` ("not yet", "pas encore", "not now", "not that"), also right after an agreement word ("ok, not yet"); (3) a first clause that negates the proposal: a word of `commands.FIRST_CLAUSE_REFUSALS` ("wrong", "faux", "reject"), or, when the reply does not open with an agreement (`commands.AGREEMENT_LEAD`: "yes", "ok", "agreed", "right", "I confirm", "I adopt", "I choose", "I'll go with", "that matches", "oui", "d'accord", "je confirme", "j'adopte", ...) or a delegation, a negator ("not", "n't", "pas", "never") whose next word does not describe availability, a restart, or an inability to answer ("this feature is not available", "we don't know it before the call", "don't restart it", "for questions I can't answer" are statements); (4) a later clause that is a refusal on its own ("ok... no", "yes. No, wait.") or a reservation opening with "but" / "mais" followed by a negation ("Yes, but not before the first call", "d'accord, mais je ne veux pas de seuil"). After an agreement lead, a negated clause states a limit and is not a refusal ("Yes, and it's not a forecast", "agreed, never an input", "I confirm: its validation errors aren't evidence of future error"); the words are recorded verbatim, limits included |
| `bare_acknowledgement` | The words hold nothing beyond acknowledgements, filler words, and identifiers ("ok", "oui", "yes, that is right", "keep that", "garde ça", "d'accord", "sure, sounds good to me", "yes go with that", "ok p_5"); `commands.is_bare_acknowledgement`. Since ADR 0005 an explicit first-person endorsement is not bare (`confirm.ENDORSEMENT`: "I confirm", "I agree", "je confirme", "je valide", "je suis d'accord", "j'approuve"). Checked after `conditional_reply` |
| `question_reply` | ADR 0005 (guided): the words hold a question mark; a question is not an answer (`confirm.is_question`). Checked after `negative_reply` |
| `conditional_reply` | ADR 0005 (guided): the words set a condition or hesitate (`confirm.is_conditional`): anywhere "unless", "sauf si", "except if", "only if", "seulement si", "à condition", "provided that", "pourvu que", a hesitation ("réfléchir", "let me think", "think about it", "on verra"); or, right after an agreement or an endorsement (other agreement and filler words aside), "but", "mais", "however", "cependant", "toutefois", "sauf", "except", "though" ("oui mais je veux réfléchir", "d'accord sauf contact", "yes but"). Checked after `question_reply` |
| `unrelated_reply` | Not emitted by `decide confirm` since v0.2a (ADR 0005: the guided mode has no token-overlap requirement; reserved for the training mode of v0.2b). Still emitted by `decide note --resolve` (§5.1) and `run --acknowledge-interruption` (§8.1): the words share no word (same word, or the same first five letters of two long words, accents folded) and no number (digits or a number word, "twenty") with the note or proposal (review fix H1) |
| `proposal_not_found` | No such proposal |
| `proposal_withdrawn`, `proposal_superseded`, `proposal_confirmed` | The proposal is not open |
| `same_request` | The proposal was not created by an earlier request |
| `proposal_stale` | A decision the proposal rests on changed since it was made (`details.basis`, `details.current_basis`) |
| `not_a_delegation` | `--basis delegated_default`, but the words do not explicitly delegate to the assistant's recommended default |
| `delegation_needs_basis` | `--basis explicit`, but the words delegate the choice to the assistant: the confirmation must say so |
| `restatement_not_default` | `--basis delegated_default`, but the proposal's restatement does not say it is the assistant's recommended default |
| `delegation_not_given_at_this_pause` | `--basis delegated_default` for the `policy` or the `conclusion` without `--delegation-scope this_decision` (acceptance rerun, R1): a standing delegation covers `state.STANDING_DELEGATION_DECISIONS` only (`details.decision_id`, `details.delegation_scope`, `details.standing_covers`). Checked after `restatement_not_default` |

**Confirmation basis (D1, post-acceptance).** `explicit` (default): the user's own reply to the restatement decides. `delegated_default`: the user explicitly hands the choice to the assistant ("use your recommended default", "go with your recommendation", "je te laisse choisir", "prends ta recommandation"; `commands.is_delegation`), and the proposal's restatement states that it is the assistant's recommended default ("My recommended default: ..."; `commands.states_default`). A bare acknowledgement never delegates; silence is never a delegation. The basis is recorded in the confirmation, shown distinctly in the view, the HTML report and the notebook, and every delegated decision is listed in `not_yet_defensible` (`delegated_decisions`).

**Delegation scope (acceptance rerun, R1).** `--delegation-scope` (action parameter `delegation_scope`, `null` when absent) says which delegation a `delegated_default` confirmation rests on: `this_decision`, a delegation the junior gave at this very pause; or `standing`, an earlier delegation for every question they cannot answer ("for questions I can't answer, use your recommended default"). A standing delegation covers only `prediction_time`, `feature_availability`, and `split` (`state.STANDING_DELEGATION_DECISIONS`). The `policy` and the `conclusion` need the junior's own words (`explicit`) or a delegation given at that pause: `--basis delegated_default` for them without `--delegation-scope this_decision` is `ambiguous_confirmation` with reason `delegation_not_given_at_this_pause`. For the other three decisions the scope is optional and recorded as given. A scope with `--basis explicit`, or a value outside `state.DELEGATION_SCOPES`, is `invalid_value` (`details.field` `delegation_scope`). The scope is recorded in the confirmation and shown in the view and in `status --summary`. Confirmations recorded before R1 (without a scope, including a delegated policy) stay valid.

Then, in order: the case and dataset bytes must still match (`dataset_changed`), the value must be valid (`invalid_value`), and the pause preconditions must hold (`precondition_missing`, `details.missing`). A confirmation records `{user_words (verbatim), proposal_id, restatement, authenticated: false, channel, actor, revision, time, basis, delegation_scope, agent_concern}` and applies §6. `basis`, `delegation_scope` and `agent_concern` are optional in a stored record (`state.CONFIRMATION_OPTIONAL_KEYS`) so that earlier studies stay valid; `delegation_scope` is `null` unless the basis is `delegated_default`.

**Guided confirmation (ADR 0005, v0.2a).** The rules above are those of the `guided` mode (§5.2), the default and the only mode of v0.2a. A reply bound to a proposal (`PROPOSAL` or `--proposal`) that is the single open proposal of its decision at the current revision (`--expected-revision`), and that is neither negative, a question, conditional, nor bare, confirms it: no word needs to be shared with the proposal. Then, after `proposal_stale` and for a confirmation in the junior's own words only (not a delegation): the decisions of `confirm.REASON_DECISIONS` (`policy` and `conclusion` in a binary study, `model_choice` and `conclusion` in a regression study) need one reason, a clause beyond the endorsement (`confirm.has_reason`: a connector, "because", "since", "given", "parce que", "car", "puisque", "vu que", "étant donné", or any content word that is not an endorsement word or an intensifier); otherwise the refusal is `reason_required` (`details.decision_id`, `proposal_id`, `user_words`, `mode`), not `ambiguous_confirmation`. The recorded `basis` is `restated` when the words repeat a word or a number of the proposal's value, restatement or labels (endorsement words left out, `confirm.restates`), else `endorsed`; the request's `--basis` stays `explicit` or `delegated_default` (`state.REQUEST_BASES`), and a delegation is recorded as `delegated_default` as before. `explicit`, `endorsed` and `restated` are all the junior's own words: a change between them never outdates a conclusion (§6, `state.basis_class`).

**Agent concern and contradiction warnings (ADR 0005, R3).** `--agent-concern TEXT` (action parameter `agent_concern`, carried only when given) records, on the confirmation, a point the agent raised about the junior's words before they confirmed and that the junior kept; it is non-blank (`invalid_value`, `details.field` `agent_concern`), shown in the view, `decisions`, the HTML report ("Point raised by the agent ... kept by the user") and the handoff pack. For `feature_availability`, the confirm result carries `warnings` (`confirm.availability_warnings`): the words are cut into clauses; a clause naming a candidate feature with exclusion words ("exclure", "écarter", "retirer", "sans", "exclude", "drop", "remove") while the value marks it `available_at_prediction` or `uncertain_included`, or with keep words ("garder", "conserver", "inclure", "keep", "include", "use") while the value marks it `not_available` or `uncertain_excluded`, gives `{code: "words_contradict_value", variable, said: "exclude"|"keep", value, message}`. A clause without such words continues the direction of the clause before it ("exclure duration, contact et pdays"); a clause with both kinds, or with a negation before them, says nothing. It is a warning, never a refusal: the confirmation is recorded. A later correction of the reasoning is a note of kind `correction` (§5.1).

In a regression study (§10) the decisions are `prediction_time`, `feature_availability`, `split`, `model_choice`, `conclusion`; `policy` is not one of them (`unknown_decision`). `model_choice` is `"fit.linear"` or `"fit.baseline"` (`preconditions.MODEL_CHOICES`), confirmed only with a current `evaluate.regression` whose `params.models` lists it; the conclusion's verdict is one of `adopt_model`, `keep_baseline`, `inconclusive` (`preconditions.REGRESSION_CONCLUSION_VERDICTS`): `adopt_model` needs `model_choice` confirmed as `fit.linear`; `keep_baseline` and `inconclusive` need no model choice (D6; before the post-v0.1 fixes `inconclusive` needed a confirmed one). A standing delegation does not cover `model_choice` (it is not in `state.STANDING_DELEGATION_DECISIONS`).

**Split methods (M3).** `split` is one of `{"method": "stratified_random", "validation_fraction": f, "seed": n}` (binary study), `{"method": "random", "validation_fraction": f, "seed": n}` (regression study, not stratified), or `{"method": "ordinal_cutoff", "column": C, "cutoff": k}` (`commands.ORDINAL_SPLIT_KEYS`; `C` is the case's declared time column, of type `integer`; `k` an integer: rows with `C >= k` are validation rows). When the case declares a time column, `ordinal_cutoff` is the only method (`commands.split_methods`): a random split would mix earlier and later rows, so it is `invalid_value`, never a silent fallback. A method outside `commands.ALL_SPLIT_METHODS` is `unsupported_capability`. `run split` refuses a split the rows cannot support with `unsupported_capability` and a structured reason (`details.reasons[]: {code, capability, path, reason}`): `stratified split with fewer than two rows of each class` (with `counts` by label) before sampling, or `random split of these rows with these parameters` when the sampler refuses (for example a validation fraction that leaves a partition empty).

### 5.1 Notes: the junior's conditions and holds (post-v0.1, P2)

`hypotrail decide note --about DECISION --text TEXT` records a condition the junior stated at a pause, verbatim ("don't adopt anything until I bring my manager's figure"): a note `{note_id, decision_id, kind: "hold", user_words, status: "open", created, revision, request_id, resolution: null}` in `state.notes` (`state.NOTE_KEYS`). `--about` names a decision of the study (`unknown_decision` otherwise); the text must be non-blank and say more than an acknowledgement (`invalid_value`, `details.field` `user_words`). A refusal or a negation is allowed: a hold usually is one.

**A hold on a confirmed decision (post-v0.1 fixes, D1).** When the decision is already `confirmed`, the hold withdraws that agreement: the decision becomes `reconfirm_required` (its value and confirmation stay visible, `reason` names the note), and so does every confirmed decision that rests on it (`dependencies.dependents`: the decisions whose `depends_on` closure holds it; the conclusion rests on all of them). No result is invalidated, since no value changed. The invalidation is recorded with `mutation: hold_added`, `row: null`, `decision_id` the held decision (§6), and the `decide.note` result lists the decisions in `reconfirm_required`. A study therefore never shows a decision as confirmed while a hold on it is open; once the hold is resolved or withdrawn, the decision is proposed and confirmed again. A hold on an open or proposed decision changes no status. A state written before this rule may still hold a confirmed decision with an open hold; it is kept as recorded.

While a note on a decision is open, `decide confirm` of that decision is refused with `decision_on_hold` (`details.decision_id`, `proposal_id`, `notes: [{note_id, user_words}]`), whatever the basis, checked after the proposal is found open and created by an earlier request. Proposing is still allowed. `not_yet_defensible` lists `open_holds`; `status --summary` lists every note (`notes`) and the recap's `Next` line quotes the open ones; the HTML report shows each note, open or resolved, in its decision's card, in the junior's words.

`hypotrail decide note --resolve NOTE_ID --text TEXT` resolves an open note with the junior's own words, `resolution: {user_words, revision, time, request_id}` and `status: "resolved"`. The words follow the confirmation rules (`ambiguous_confirmation` with `details.reason` `missing_user_words`, `negative_reply` ("not yet"), `bare_acknowledgement`, or `unrelated_reply` when they share no word or number with the note's words, its decision's id, or that decision's open proposals); `same_request` when the request that recorded the note resolves it. A note id that does not exist is `unknown_note`; a resolved or withdrawn note is `note_not_open`. The words of a note and of its resolution are literals for `check` (`user_words`), like confirmation words.

`hypotrail decide note --withdraw NOTE_ID --text TEXT` (post-v0.1 fixes, D5) withdraws an open hold that no longer applies (a restatement of a hold already recorded, a condition the junior dropped), with the junior's own words: `status: "withdrawn"` and the same `resolution` record. The words may hold a negation ("no need to wait for that any more"); they must be non-blank (`ambiguous_confirmation`, `missing_user_words`) and say more than an acknowledgement (`bare_acknowledgement`); `same_request`, `unknown_note`, and `note_not_open` as for `--resolve`. A withdrawn note no longer blocks its decision; a decision a hold made `reconfirm_required` still needs the junior's words again. `state.NOTE_STATUSES` is `open`, `resolved`, `withdrawn`, `recorded`; the report shows a withdrawn note with the words that withdrew it.

**Corrections (ADR 0005, R3).** `hypotrail decide note --about DECISION --kind correction --user-words TEXT` (action parameter `kind`, carried only when it is not `hold`) records a later correction of a decision's reasoning in the junior's words, without asking for the decision again: a note `{kind: "correction", status: "recorded", resolution: null}`; no invalidation, no hold, nothing becomes `reconfirm_required`. The decision must have a confirmation (`confirmed` or `reconfirm_required`), otherwise `invalid_value` (`details.field` `kind`): before a confirmation the junior answers the proposal in the words they mean. A correction cannot be resolved or withdrawn (`note_not_open`). The report shows it in its decision's card ("Correction in your words"); the companion digest lists it with kind `other`.

### 5.2 Confirmation modes and language (ADR 0005)

`state.mode` is one of `state.MODES`: `guided` (the default, written by `init`), `training` and `express` (reserved: accepted in the schema, implemented in v0.2b). `hypotrail mode set MODE --user-words TEXT --request-id ID --expected-revision REV --study DIR` (action `study.set_mode`, parameters `{mode, user_words}`) records the mode with the user's words: a mode outside `state.MODES` is `invalid_value`; `training` and `express` are `unsupported_capability` with `mode`, `available_in` (`v0.2b`, `state.MODES_AVAILABLE_IN`) and `supported` in `details`; the words follow the guided reply rules (`ambiguous_confirmation`: `missing_user_words`, `negative_reply`, `question_reply`, `conditional_reply`, `bare_acknowledgement`), so a mode never changes without the user's words. Each accepted request appends `{mode, previous, user_words, revision, time, request_id}` (`state.MODE_CHANGE_KEYS`) to `state.mode_history`; the replay of a request is idempotent.

`state.language` is one of `state.LANGUAGES` (`en`, `fr`), set by `init --lang` (default `en`). A proposal keeps its structured `value` and its `restatement` (compatibility); `decide propose --restatement-en TEXT` and `--restatement-fr TEXT`, and `--lang L` (the language of `--restatement`), store `labels: {language: restatement}` on the proposal (action parameter `labels`, carried only when a language is given, so earlier requests keep their identity). Each label is non-blank, in a language of `state.LANGUAGES` (`invalid_value`, `details.field` `labels`), and checked for numbers like the restatement (`literal_number_in_text`, `details.field` `labels.<language>`). `status --json` shows `label`, the restatement in the study language, on each open proposal of the view (`status --summary` keeps its v0.1 shape); a French paraphrase can restate through the French label.

## 6. Invalidation (plan §3.7)

`mlkit.study.dependencies.MUTATIONS` is the table. `effects(old_state, decision_id, old, new)` returns at least `refit`, `re_eda`, `re_policy`, `re_chart`, `re_explain`, `reconfirm` (lists), plus `mutation`, `row`, `reason`, `recompute`, `blocked_until`, `scope`, `notes`.

| Row | `mutation` id | Classified from |
|---|---|---|
| 1 | `prediction_time` | any change of `prediction_time` |
| 2 | `feature_availability.feature_set` | availability change that changes the usable feature set (`available_at_prediction` ∪ `uncertain_included`) |
| 3 | `feature_availability.wording` | availability change with the same feature set |
| 4 | `split` | any change of `split` |
| 5 | `policy.parameter` | same rule type, new `t` or `k` |
| 6 | `policy.rule_type` | threshold ↔ capacity |
| 7 | `settings.bootstrap` | bootstrap settings |
| 8 | `usage_label` | usage label |
| 9 | `eda_added` | an EDA result added |
| 10 | `conclusion` | conclusion text or verdict |
| 11 | `code_fingerprint` | `old`/`new` = `{activity, fingerprint}` |
| 12 | `dataset` | `dataset` or `case`: refused with `dataset_changed` |
| `*` | `unknown` | anything else, or an unparseable value: every current result stale, every other confirmed decision `reconfirm_required`, reason recorded |

A regression study uses `dependencies.REGRESSION_MUTATIONS` (`dependencies.mutations(state)`), with the same row numbers: rows 1–4 and 7 name `fit.linear`, `evaluate.regression` (under `re_policy`, the key of evaluations recomputed from stored predictions), and `model_choice` where the binary table names `fit.logistic`, `policy.evaluation`, and `policy`; rows 5 and 6 do not exist; row 13, `model_choice`, is new (no refit, no new evaluation; `conclusion` is reconfirmed). Result replacement uses `dependencies.REGRESSION_RESTS_ON` (`model_choice` and `conclusion` rest on `split`, `fit.baseline`, `fit.linear`).

A first confirmation (`mutation: first_confirmation`) and a confirmation with an unchanged value (`unchanged_value`) have `row: null` and no effect, with one exception. **The conclusion summarizes its decisions (post-v0.1 fixes, D2).** When the conclusion is `confirmed` and a decision it rests on (`state.depends_on(state, "conclusion")`) is then confirmed with a different status (it was not `confirmed`: a policy or model choice adopted after a `keep_baseline` conclusion, a decision confirmed again after a reconfirmation request), a different value, or a different basis class (a delegated default confirmed again in the junior's own words, or the reverse; since ADR 0005 `explicit`, `endorsed` and `restated` are one class, `state.basis_class`), the conclusion becomes `reconfirm_required` (`dependencies.outdates_conclusion`), and `not_yet_defensible` names `conclusion_outdated` until it is confirmed again. The record keeps the mutation id (`first_confirmation`, `unchanged_value`, or the table row) and states the reason. **A hold** on a confirmed decision is recorded with `mutation: hold_added` and `row: null` (§5.1, D1). **Result replacement (review fix H2).** When `run.promote` puts a new result in a slot that held another one, `dependencies.apply_replacement` records an invalidation with `mutation: result_replaced`, `decision_id` the slot, `row` 11 when the activity's code fingerprint changed (else `null`): every current result computed from the replaced one (registry lineage) becomes stale, and the decisions resting on the slot (`dependencies.RESTS_ON`: `policy` and `conclusion` for `split`, `fit.baseline`, `fit.logistic`) become `reconfirm_required`. Nothing is recorded when nothing is invalidated (an EDA or policy evaluation rerun). The `run` result then carries `invalidation` (`{mutation, row, reason, stale_results, stale_slots, reconfirm_required}`, or `null`). Rows 7 (`settings.bootstrap`) and 8 (`usage_label`) are classified by `effects` but no v0.1 command changes the bootstrap settings or a usage label, so they are not reachable; row 9 (`eda_added`) needs no action because an EDA result goes into its own slot (a new `eda.rate_by:<column>` slot adds, never replaces). Facts are never reconfirmed. A policy confirmation never marks its own evaluation stale (a current evaluation of the new rule is its precondition). Staleness propagates downstream through registry lineage.

An invalidation record in `state.invalidations` and `view.invalidations` has the keys `revision`, `decision_id`, `mutation`, `row`, `reason`, `stale_results`, `stale_slots`, `reconfirm_required`, `effects`, `previous` (`{value, confirmation, proposal_id}` of the replaced confirmation, or `null`). A reconfirmation request keeps the decision's previous `value` and `confirmation` visible and sets `reason`.

## 7. Error codes

Stable codes. Clients branch on `error.code`; messages may change.

| Code | Source | Meaning |
|---|---|---|
| `invalid_arguments` | CLI | Missing or malformed command-line arguments (including a missing `--study`) |
| `internal_error` | CLI | Unexpected exception (exit 1) |
| `invalid_request` | `apply_command` | The request does not have exactly `request_id`, `expected_revision`, `action`, `params`, or a field is malformed |
| `idempotency_conflict` | `apply_command` | `request_id` already used for a different request |
| `stale_revision` | `apply_command` | `expected_revision` differs; `details.expected_revision`, `current_revision`, `changes_since` |
| `invalid_command` | `apply_command` | Unknown action or wrong parameter set |
| `study_missing` | store, read | No `.hypotrail/state.json` at `--study` |
| `state_exists` | `init` | A study already exists; it is never overwritten |
| `integrity_error` | store, read, registry | State, registry entry, or blob diverges from its digest |
| `study_busy` | lock | Another writer holds the lock past the timeout |
| `platform_unsupported` | lock | Native Windows |
| `invalid_case` | case | The case does not follow `hypotrail.case/1` (`problems`) |
| `confirmed_status_forbidden` | case | A case claims a confirmation |
| `dataset_missing` | case | The dataset file is absent or outside the case directory |
| `dataset_changed` | case, `decide propose`, `decide confirm`, `run`, `render` | Dataset or case bytes differ from the recorded sha256 (`case.source_changes`; `details.path`, `expected_sha256`, `actual_sha256`, `changes`). Since review fix L1 also `decide propose`, `render`, and the computation itself, which re-reads the case file and checks it against `inputs.case_sha256` of its plan |
| `unsupported_capability` | case, data, CLI | A capability this version does not have (`details.reasons` or `details.command`) |
| `unknown_decision` | `decide propose` | Decision id not in the five |
| `invalid_value` | `decide` | The value does not fit the decision (§5) |
| `literal_number_in_text` | `decide propose` | A number in the restatement or rationale is neither part of the value nor a figure of a current result (`details.numbers`) |
| `causal_or_forecast_wording` | `decide propose` | A proposed conclusion's text, restatement, or rationale uses causal or forecast wording (review fix M1; `details.findings`) |
| `ambiguous_confirmation` | `decide confirm`, `run --acknowledge-interruption`, `decide note --resolve`, `mode set` | §5, `details.reason` (§8.1 item 5 for an acknowledgement, §5.1 for a note, §5.2 for a mode) |
| `reason_required` | `decide confirm` | ADR 0005: the policy, the model choice or the conclusion confirmed in the junior's own words without a reason (§5; `details.decision_id`, `proposal_id`, `user_words`, `mode`) |
| `decision_on_hold` | `decide confirm` | Post-v0.1 (P2): the decision has an open note (§5.1; `details.notes`) |
| `unknown_note` | `decide note --resolve` | No such note (`details.open_holds`) |
| `note_not_open` | `decide note --resolve` | The note is already resolved |
| `misattributed_delegation` | `decide propose conclusion` | Post-v0.1 (P7): the conclusion's text, restatement, or rationale credits a recommended default to the analyst (`check`'s `misattributed_delegation` rule; `details.findings`, `details.delegated`). Checked after the numbers and before causal or forecast wording |
| `precondition_missing` | `decide confirm`, activities | A pause precondition is unmet (`details.missing`) |
| `unknown_proposal` | `decide withdraw` | No such proposal |
| `proposal_not_open` | `decide withdraw` | The proposal is not open |
| `unknown_result` | registry, read | No such result id |
| `invalid_result` | registry | A malformed `put` |
| `unknown_module` | registry | A module named in a code fingerprint has no source file |
| `invalid_exposure` | exposure | Unknown purpose or partition, or a reused exposure id |
| `no_predictions` | read | The result has no `predictions` blob |
| `invalid_state` | state | A state that does not follow `hypotrail.study/1` (refused before any write) |
| `invalid_confirmation` | state | An incomplete confirmation record |
| `lease_exists`, `lease_held` | lock | Execution lease conflicts |
| `interrupted_execution_pending` | `run` | An execution has an unknown outcome; every `run` is refused (exit 4) until `run --acknowledge-interruption E --user-words TEXT` (`details.interrupted`) |
| `execution_in_progress` | `run` | The same slot is being computed on the same inputs by an active execution (review fix L7; `details.execution_id`) |
| `unknown_execution` | `run` | `--acknowledge-interruption E` names no interrupted execution (`details.interrupted`), or an internal step names no active execution |
| `read_only` | activities, guard, store, every mutating command | `HYPOTRAIL_READ_ONLY=1` (a notebook kernel): the process may read results but never compute, record, render, or write one (`init`, every `decide`, `run`, `run --acknowledge-interruption`, every fit, `render`, and the notebook generator refuse; since review fix H3 `commands.apply`, `commands.init`, `executions.acknowledge`, and `StudyStore.create`/`writing`/`execute` call `guard.assert_writable` first). Phase 3's `read_only_process` was merged into this code by the Phase 4 integration |
| `untraceable_number` | cite, renderers | A number cannot be traced to a current registry result (unknown or non-current result id, missing path, non-numeric value, unknown format). The render of that artefact fails; it is never written with the number (§8.3) |

Added in Phase 2 (contract commit, reviewed by the integrator): `interrupted_execution_pending` and `unknown_execution` (reserved in Phase 1, now emitted) and `read_only`. Phase 2 also emits the existing codes `invalid_arguments` (unknown activity, missing `--column` or `--rule`, a `--column` that is not a feature), `precondition_missing` (pauses, a candidate feature without availability decision, missing fits), and `no_predictions`.

## 8. Extension points

### 8.1 Activities (Phase 2)

An activity is identified by its **slot** name, which is also its registry `activity`: `split`, `eda.target_rate`, `eda.special_values`, `fit.baseline`, `fit.logistic`, `policy.evaluation`. The plan's slots are `mlkit.study.state.ACTIVITY_SLOTS`. **Exception (Phase 4 integration):** `eda.rate_by` has one slot per column, `eda.rate_by:<column>` (`activities.slot_of`, `state.PER_COLUMN_SLOT_PREFIXES`); its registry entries keep `activity: "eda.rate_by"` and `params.column`, so exploring a second column never replaces the first. These slots are optional: they never block a step, are shown with the `train_eda` step, and a `code_fingerprint` change of `eda.rate_by` reaches every one of them. `run.result.slot` names the slot of a promoted result. A `{{slot:…}}` template may name a per-column slot (the longest known slot prefix wins).

1. **CLI command.** Create `framework/mlkit/study/cmd_run.py` (and `cmd_preview.py`) with
   ```python
   def configure(parser: argparse.ArgumentParser) -> None   # add arguments; --study and --format exist
   def main(args: argparse.Namespace) -> mlkit.study.commands.Outcome
   ```
   `cli.py` imports it only when `hypotrail run` (or `preview`) is invoked. Do not import pandas or scikit-learn at module level of `cmd_*` modules; import them inside the computation.
2. **State mutations.** Register `apply_command` actions:
   ```python
   commands.register_action(name: str, factory: Callable[[commands.Context], reliability.Handler]) -> None
   # Context(store: StudyStore, request_id: str); Handler(params: frozenset, run(state, params) -> result, check(params) -> None)
   commands.apply(study_dir, *, action: str, params: dict, request_id: str,
                  expected_revision: int, command: str = 'decide') -> Outcome
   ```
   Use dotted names, for example `run.reserve`, `run.promote`, `run.acknowledge`. `run` mutates state in memory only and raises `CommandRefused` to refuse.
3. **Preconditions.** Before reserving and again before promoting:
   ```python
   preconditions.require_activity(state, activity: str) -> None            # precondition_missing
   preconditions.missing_for_activity(state, activity: str) -> list[dict]
   preconditions.require_decision(state, decision_id, value=None, *, store=None) -> None
   ```
4. **Results.** Under the writer lock, after computing outside it:
   ```python
   code = registry.code_fingerprint(modules: Iterable[str]) -> {'fingerprint', 'modules'}
   eid = exposure.new_exposure_id() -> 'x_…'
   put = registry.put(store, *, activity, params, inputs, code, values, blobs=None,
                      partition=None, n_rows=None, exposure_id=None, execution_id=None,
                      started_revision=None, env=None)
         -> {'result_id', 'input_key', 'created', 'nondeterministic', 'same_input_results'}
   exposure.record(store, *, exposure_id, revision, activity, result_id, purpose, partition,
                   row_keys, dataset_sha256, columns, execution_id=None) -> dict
   ```
   * `inputs.results` maps a role to the upstream `result_id` (lineage); put decision values and `dataset_sha256` in `inputs` too, so `input_key` changes when they change.
   * `blobs` maps a name to bytes. Predictions use the name `predictions`: gzip CSV with header `row_key,y,score` (plan §3.4), read back by `read.Study.predictions`.
   * A policy evaluation records the evaluated rule(s) as `params.rule` or `params.rules`.
   * `put` never touches state. Promotion is a registered action that sets `state['current'][slot] = result_id` only if the `input_key` recomputed on current state is identical (plan WP2.1); otherwise record the execution under `state['executions']['late']`.
   * Record exposure for every read of rows, even for a result that is not promoted; use `result_id=None` when no result was stored (for example an interrupted execution).
   * Changing a split: compute `exposure.overlap(old_split, new_split, store=store)` and store it in the split result values.
   * A code change: `dependencies.effects(state, 'code_fingerprint', {'activity', 'fingerprint'}, {...})` then `dependencies.apply_effects(state, eff, revision=…, decision_id='code_fingerprint', store=store)` inside an action.
   * A replaced result (review fix H2): `run.promote` calls `dependencies.apply_replacement(state, slot, previous, new, *, revision, store, code_changed=False)`, which calls `apply_effects(..., seeds=[previous], keep=[new])`: `seeds` are results that no longer hold (their current descendants become stale), `keep` is never made stale. Staleness propagates through `inputs.results` without the history role `previous_split` (`records.HISTORY_ROLES`, `records.upstream(entry, history=False)`).
5. **Exit code 4** for an execution with an unknown outcome, including the `interrupted_execution_pending` refusal; `unknown_execution` refuses an acknowledgement of nothing (exit 2).
   **Acknowledgement words (D2, post-acceptance).** `hypotrail run --acknowledge-interruption E --user-words TEXT`: `--user-words` (the junior's verbatim reply after being told the outcome is unknown) is required and non-blank, otherwise `invalid_arguments`; it is refused with an activity. Since review fix L5 the words follow the confirmation rule (`commands.reply_problem`): a refusal, a bare acknowledgement, or words that name neither the interrupted activity nor its interruption (interrupted, unknown, outcome, restart, ...; `commands.ACKNOWLEDGEMENT_TOPIC`) are refused with `ambiguous_confirmation` and `details.reason` `negative_reply`, `bare_acknowledgement`, or `unrelated_reply`. The action `run.acknowledge` has the parameters `{execution_id, user_words}`; its result, and the execution history `.hypotrail/executions/<E>.json`, record `user_words`. An agent never acknowledges or reruns on its own.
6. **Payload schemas added in Phase 2** (additions; the five schemas of §3 are unchanged):

   | Schema | Emitted by | Keys |
   |---|---|---|
   | `hypotrail.run/1` | `run`, `run --acknowledge-interruption` | `schema`, `ok`, `study`, `action` (`run` or `run.acknowledge`), `request_id`, `replayed`, `revision`, `activity`, `execution_id`, `status`, `result_id`, `values`, `result`, `artifacts` |
   | `hypotrail.preview/1` | `preview policy` | `schema`, `ok`, `study`, `revision`, `kind`, `rules`, `models`, `evaluations`, `intervals`, `adopted`, `recorded` (`false`), `note`, `warnings` |

   `run.status` is one of `promoted`, `late_not_promoted`, `already_current`, `running`, `failed`, `interrupted_unknown`, `acknowledged`. An `acknowledged` result holds `execution_id`, `activity`, `status`, `restarted` (`false`), `started_revision`, `user_words`, `note`. `values` are the registry values of `result_id` (cite them only while the slot is current, §4); since review fix L6 a `late_not_promoted` payload has `values: null` and `result.citable: false` (the result is stored in the registry, but it describes a state that no longer holds). Since review fix L7, a `run` whose slot and `input_key` equal those of an active execution is refused with `execution_in_progress` (`details.execution_id`, `slot`, `activity`, `started_revision`) instead of computing twice. `preview` writes nothing and records no exposure; `validation_policy_selection` is recorded by `run policy.evaluate`. `preview.warnings` (post-v0.1 fixes, D4; additive) lists the G.12 warnings that bear on the previewed rules, as `not_yet_defensible` items words them (§4): `capacity_exceeds_validation` for the previewed capacities at least as large as the validation rows the fits scored, first, then `small_validation_partition` when the current split's validation partition is small; `[]` otherwise.

### 8.2 Read API (Phase 2 and 3)

```python
study = read.open(study_dir) -> read.Study       # one verified snapshot; integrity_error otherwise
study.revision -> int
study.state -> dict                               # deep copy
study.revisions(since: int = 0) -> list[dict]
study.current(slot: str) -> dict | None           # verified registry entry
study.is_current(slot: str) -> bool
study.result(rid: str) -> dict                    # verified registry entry
study.predictions(rid: str) -> pandas.DataFrame   # row_key, y, score; pandas imported here only
study.source(activity: str) -> {'activity', 'result_id', 'modules', 'fingerprint', 'fingerprint_matches'}
study.exposure_records() -> list[dict]
study.exposure_summary() -> dict
study.artifacts() -> dict | None                  # .hypotrail/artifacts.json
```

`read.py` and `view.py` never write and never import a writer module (`store`, `lock`, `registry`, `exposure`, `dependencies`, `commands`, `cli`, `migrate`, `preconditions`); an AST test enforces it. The notebook may import them under `HYPOTRAIL_READ_ONLY=1`.

### 8.3 Renderers (Phase 3)

* Consume `view.build(study_dir)` (§4). Cite a number only from a result item with `current: true` and `integrity: "ok"`, as `<data data-result-id="…">`.
* `framework/mlkit/study/cmd_render.py` provides `configure`/`main` for `hypotrail render` and
  ```python
  def after_commit(study_dir: pathlib.Path, payload: dict) -> dict   # {artifact: {'status': 'ok'|'stale'|'failed', ...}}
  ```
  which `commands.apply` calls after every committed, non-replayed mutation. Its return value becomes `decide.artifacts`; any `stale` or `failed` artefact makes the command exit `3`. A render failure never undoes the commit.
* The manifest lives at `.hypotrail/artifacts.json` (plan §3.6) with `{"status": …, "artifacts": {name: {...}}}`; `view.artifacts` exposes it as `{manifest, status, items}`; every item also has `message` (D7, below). Since the Phase 4 integration, `items.<name>.status` and `view.artifacts.status` are the **effective** statuses (`mlkit.study.currency.effective_status`, the pure currency rule below, against the current state), not the status stored by the last render; the stored value stays visible as `items.<name>.recorded_status`. A study whose state moved on without a render therefore shows `stale`. Review fix M4 (additive): every item also has `stale_reason`, null unless a recorded `ok` generated deliverable is `stale`, then one of `currency.STALE_REASONS`: `file_missing` (its file was deleted or moved), `file_changed` (its bytes differ from the manifest's `sha256`, or for the generated notebook from its `edit_check_sha256`, which ignores Marimo's `__generated_with` stamp), `revision_changed`, or `result_not_current`; the two file reasons take precedence, and its `message` says the file was deleted or changed.
* `framework/mlkit/study/cmd_check.py` provides `hypotrail check` with the same `configure`/`main` interface.
* Teaching texts belong in `mlkit/study/content/*.yaml`, not in this contract.

Added by Phase 3 (WP3.1–WP3.4), within these extension points:

```text
hypotrail render --study DIR
hypotrail check --study DIR [--text PATH | --text -] [--allow-user-text PATH | --allow-user-text -] ...
```

| Schema | Emitted by | Keys |
|---|---|---|
| `hypotrail.render/1` | `render` | `schema`, `ok`, `study`, `revision`, `status`, `artifacts` |
| `hypotrail.check/1` | `check` | `schema`, `ok`, `study`, `revision`, `target`, `clean`, `counts`, `findings`, `traced` |
| `hypotrail.artifacts/1` | `.hypotrail/artifacts.json` | `schema`, `revision`, `status`, `artifacts` |

* Artefact names: `report` (`reports/study.html`), `notebook` (`notebooks/study_generated.py`), `workbench` (`notebooks/workbench.py`). A manifest item has `path`, `kind`, `revision`, `status`, `consumed`, `sha256`, `generated`, `template_version`, `error`, `last_ok_revision`, `user_edits_preserved`, `candidate`. An artefact is current iff `status` is `ok`, `revision` equals the state revision, every result in `consumed` is current, and (review fix M4) its file exists with the recorded hash (`currency.file_check`, read on every `status`, summary, `check`, `evidence`, and `export`); the workbench (`generated: false`) is never stale. `check`'s `artifact_not_current` finding then has `details.reason` `file_missing` or `file_changed`.
* `render.artifacts` and `decide.artifacts` map each artefact name to `{status, path, revision, last_ok_revision, error}`, plus `tracked: false` for the workbench and `candidate` or `user_edits_preserved` when present, and `message` (D7, post-acceptance): one sentence an agent repeats to the junior (`currency.message`). After a failed render it reads "The report render failed at revision N: previous report kept and marked stale at revision N. Its content is from revision M; ..." (the same for the generated notebook). Since P3 (post-v0.1) the other messages hold no revision number, so a resume recap that repeats one holds none: "The report (reports/study.html) is up to date.", "The report (...) is stale: the study changed after it was written. Render again before relying on it."; the item's `revision` and `last_ok_revision` keep the numbers. `status` is `ok`, `stale`, or `failed`; `render` exits `3` when any artefact is `stale` or `failed`, and refuses with `read_only` in a read-only process. `error` is `{code, message}`; `code` is `render_failed` for an unexpected failure or a refusal code such as `untraceable_number`.
* On a failed HTML render the previous `reports/study.html` is kept and a banner replaces the region `<!--hypotrail:banner-->…<!--/hypotrail:banner-->`. Fault injection for tests: `HYPOTRAIL_FAULT=render_html|render_notebook` (comma-separated), honoured only when `HYPOTRAIL_TEST_HOOKS=1`.
* HTML numbers are `<data value data-result-id data-path title>` elements. Text shown as recorded rather than computed is wrapped in an element with `data-literal` ∈ `revision`, `ordinal`, `user_words`, `proposal`, `decision_value`, `case`, `identifier`, `parameter`, `environment`, `setting`, `message`, `category`; `check` ignores numbers there.
* `check` always exits `0`; `clean` is false when a finding has severity `error`. A finding is `{code, severity, where, message, details?}`. Codes (severity): `number_outside_result`, `unknown_result_id`, `value_mismatch`, `stale_result_cited`, `feature_without_status`, `excluded_feature_used`, `untraceable_number`, `stale_number` (error); `causal_wording`, `forecast_wording`, `artifact_not_current`, `untracked_files` (warning); post-v0.1 (P7) `misattributed_delegation` (error): with `--text`, a recommended default credited to the analyst, junior, or user ("followed the analyst's recommended defaults", "defaults chosen by the junior"; `cmd_check.MISATTRIBUTED_DEFAULT`): a delegated decision is the assistant's recommended default, delegated by the analyst. The HTML report's conclusion card lists who decided what: the delegated decisions as "the assistant's recommended default, delegated by the analyst (not the analyst's own choice)", the others as confirmed in the analyst's own words. `traced` lists each number of the checked text with the `result_id` and `path` (or the decision, setting, or case statement) it matched. Post-acceptance (D4): with `--text`, `--allow-user-text` (repeatable; a file, a pipe such as `<(printf ...)`, or `-` when `--text` is a file) gives text the junior wrote, whose numbers a draft may repeat (`traced` source `user_text`); the junior's recorded confirmation words and the rules of the current policy evaluation are literals too (`user_words`, `rule`); "percentage points" match a registered difference (`deltas`) times 100; U+2212 is a minus sign; rule identifiers (`capacity:100`) are never reported (`identifier`); numbers after "exit" and in a revision comparison ("revision 26 instead of 24") are exempt; since the acceptance rerun (R3), a result id prefix made only of digits is never reported either: a run of 6 or more digits (no sign, decimals, or percent) that follows "result", "result_id", "rid", "id", or "execution" ("(result 52659681)"), or that begins a `result_id` of the registry (`cmd_check.registry_ids`), is traced with source `identifier` and id `result_id` when it matches no figure; any other untraced number is still `untraceable_number`; the case and dataset files recorded in state are never `untracked_files`.
* Numbers written in words (post-v0.1, final acceptance F3; `mlkit/study/wordnum.py`). With `--text` and for the conclusion, `check` also reads common English and French word numbers **used quantitatively** and traces them like digits: cardinals 0–100 followed by a count noun ("the eleven kept columns", "quarante-trois clients", possibly one word between), "percent" / "pour cent" (a percentage), "percentage points" (a registered difference only), "dozen" / "douzaine" (12), ratios "k in N" / "k out of N" / "k sur N" ("one call in nine", "un client sur neuf"), and simple fractions followed by "of", "the", "de", "des", or a count noun ("half of the rows", "three quarters of", "la moitié des", "deux tiers des"). A ratio matches a registered rate `v` when `k / v` rounds to `N`; a fraction matches within `wordnum.FRACTION_TOLERANCE` (0.02); a cardinal matches as an integer. Such a number is `traced` (or reported) with `in_words: true` (and, in a finding, `kind` and `value`). Not read: "one" / "un" / "une" as a bare count ("one model"), "a single", ordinals ("first"), "the first half", cardinals above 100, vague quantities ("a few", "dozens", "most"), and a cardinal not followed by a listed count noun ("nine models"). In a regression study (M3) the target unit of the current results is a count noun too (`wordnum.unit_nouns`, a parenthesised note dropped): "about six mpg" is the count 6 and matches an error of 5.5 to 6.5 mpg. Like a digit, a word number traces to the first registered value it matches at its precision, so an unrelated value of the same size can trace it.
* Counts of the study's own structure (post-v0.1 fixes, D8). A count, in digits or in words, that matches no registered value but is followed (at most one word between) by a structural noun (`cmd_check.STRUCTURE_NOUNS`) is traced to the matching count of the view, with `source: "structure"` and an `id`: "columns", "features", "variables", "inputs", "predictors" (and "colonnes") to the length of a current, verified result's `values.features` list (`<slot>.features`) or a count of the feature availability decision or of an open proposal for it (`feature_availability.<decision|proposal id>.<all|usable|excluded|status>`); "groups" to the length of a current result's `values.groups` list; "steps", "pauses", "decisions" to the plan (`plan.steps`, `plan.pauses`) and the decisions (`decisions`). The same count before any other noun is not traced this way ("the seven columns we kept" is traced when the fit uses seven features; "seven calls" is not), and a structural count that matches none of these stays `untraceable_number`.
* Retired proposals (post-v0.1, F3): figures of `withdrawn` or `superseded` proposals are never literals (only open proposals and current decisions are). A draft number that matches nothing else stays `untraceable_number`, and its `details.retired_proposal` and `details.proposal_status` name the proposal it repeats (`cmd_check.retired_proposals`).

### 8.4 Agent instructions (Phase 4)

`init` installs the study agent instructions (`mlkit.study.agent_files`, WP4.1). The templates in `framework/mlkit/study/agent/` are stored under names that no agent loads (`CLAUDE.md.in`, `dot-claude/`), so developer sessions in this repository never load them; `agent_files.TARGETS` maps each one to its real name in the study workspace, for Claude Code and, from the same source, for GitHub Copilot (generated with a header comment, **not tested** under directive A1):

| Template | Claude Code | Copilot (untested) |
|---|---|---|
| `CLAUDE.md.in` | `CLAUDE.md` | `.github/copilot-instructions.md` |
| `dot-claude/skills/hypotrail-study/SKILL.md` | `.claude/skills/hypotrail-study/SKILL.md` | `.github/skills/hypotrail-study/SKILL.md` |
| `dot-claude/commands/hypotrail-resume.md` | `.claude/commands/hypotrail-resume.md` | `.github/prompts/hypotrail-resume.prompt.md` |

An existing file is never overwritten (`skipped_existing`). A template outside the table maps `dot-<name>/` to `.<name>/` and drops a trailing `.in`. The `README.md` is not installed.

**How the agent invokes the CLI.** Placeholders are replaced at install: `{{HYPOTRAIL}}` by the exact command, `{{STUDY}}` by the absolute study directory, `{{GLOSSARY}}` by the absolute path of the study's copy of the glossary, `.hypotrail/agent/glossary.yaml` (D10, post-acceptance: `init` copies `mlkit/study/content/glossary.yaml` there, never over an existing file, so the agent never reads the engine's source tree), `{{SKILL}}` by the agent's skill path. Every command in the instructions is therefore written in full, for example `uv run --project /abs/framework hypotrail status --json --study /abs/study`. The command is chosen in this order: the shell command in `HYPOTRAIL_CLI` if set; `uv run --project <framework> hypotrail` when the engine is the `framework/` uv project and `uv` is on `PATH` (the locked environment, from any directory); otherwise `env PYTHONPATH=<framework> <python> -m mlkit.study.cli`. It is recorded in `.hypotrail/agent.json`:

```json
{"schema": "hypotrail.agent/1", "study": "/abs/study",
 "cli": {"argv": ["uv", "run", "--project", "/abs/framework", "hypotrail"], "shell": "uv run --project /abs/framework hypotrail", "how": "uv_project | python_module | override"},
 "invocation": "<shell> <command> ... --study /abs/study", "glossary": "/abs/study/.hypotrail/agent/glossary.yaml",
 "glossary_source": "/abs/framework/mlkit/study/content/glossary.yaml", "files": {"CLAUDE.md": {"template", "flavour", "tested"}}, "note": "..."}
```

Moving the study or the engine makes the recorded paths wrong; a new `init` (a new study) records them again.

### 8.5 Result value shapes

Added by the Phase 4 integration. Phases 2 and 3 were built in parallel and met here; this section fixes **one** shape per activity. Producers (`mlkit.study.activities`, `eda`, `fit`, `policy`) emit it; consumers (`render_html`, `notebook_view`, `cmd_check`, the workbench template, `content/activities.yaml`) read it; the test fixtures (`framework/tests/study/deliverables/phase3_study.py`) build it. It is the producers' shape, completed where the report needed a field (`split.partitions.*.n_positive`, `rate`). Keys listed here are stable within `hypotrail.result/1`; producers may add keys. Paths use the `mlkit.study.cite` grammar (a segment holding a dot goes in brackets: `rules.[threshold:0.3].models.[fit.logistic].precision`).

| Activity (slot) | `values` |
|---|---|
| `split` | `method`, `validation_fraction`, `seed`, `stratified_on`, `n_rows`, `partitions: {train, validation: {n_rows, n_positive, rate}}`, `implementation`, `overlap` (`null`, or `{rows_in_new, rows_in_old, moved, transitions, previously_exposed: {partition: {purpose: n}}, previous_split, exposure_up_to_revision, note}` after a split change). The positive counts come from the stratification read of the target (`structural_inspection`). |
| `eda.target_rate` | `partition` (`train`), `target`, `positive_label`, `n_rows`, `n_positive`, `n_negative`, `rate` |
| `eda.special_values` | `partition`, `n_rows`, `special_values: [{column, value, meaning, status, source, n_rows, share, n_positive, rate}]`, `co_occurrence: [{a: {column, value}, b: {column, value}, n_a, n_b, n_both, n_either, same_rows}]`, `note` |
| `eda.rate_by:<column>` | `partition`, `column`, `n_rows`, `overall_rate`, `binned`, `binning`, `groups: [{value, n_rows, n_positive, rate, small_count}]`, `min_group_rows`, `warnings`, `note`; G.12 (post-v0.1): `n_groups` (the groups before folding), `max_groups`, `other` (below) |
| `fit.baseline` | `model` (`constant_prior`), `train_rate`, `n_train`, `n_train_positive`, `features` (`[]`), `validation: {n_rows, n_positive, roc_auc, average_precision}`, `predictions` (blob description), `note` |
| `fit.logistic` | `model` (`logistic`), `features` (used, case order), `special_value_indicators`, `n_train`, `n_train_positive`, `n_terms`, `intercept`, `coefficients: {term: value}`, `coefficient_scale`, `iterations`, `validation: {…as above}`, `predictions`. `inputs.features` repeats the features (identity). |
| `policy.evaluation` | `rules: {rule: {models: {fit slot: evaluation}, intervals: {fit slot: {precision, recall, volume: {low, high, undefined_replicates}}}, deltas: {fit slot ≠ reference: {precision, recall, volume: {point, low, high, undefined_replicates}}}}}`, `n`, `n_positive`, `predictions: {fit slot: result_id}`, `reference` (`fit.baseline`), `bootstrap: {replicates, seed, level, method}`, `counts`, `note`. `params` is `{rules, models, reference}`. `params.rules` is the requested rules, then the currently adopted policy rule if it was not requested (`activities.evaluated_rules`): a new evaluation replaces the slot, so an adopted policy never silently loses its current evaluation. |

An *evaluation* is the output of the pure `mlkit.study.policy.evaluate(y, score, rule)`, also used by `preview policy` and the workbench: `rule`, `kind`, `parameter`, `n`, `n_positive`, `selected`, `true_positives`, `false_positives`, `false_negatives`, `precision`, `recall`, `volume`, `volume_rate`, `tied_at_cut`, `cut: {score, n_tied, fraction_selected}`, `selection` (`exact`, or `expected` when a capacity cut splits a tie group pro rata). A ratio with an empty denominator is `null` and is never cited.

Regression activities (M3, §10) have these shapes:

| Activity (slot) | `values` |
|---|---|
| `split` (`random`) | `method`, `validation_fraction`, `seed`, `stratified_on` (`null`), `n_rows`, `partitions: {train, validation: {n_rows}}`, `implementation`, `groups`, `overlap`. No target is read. |
| `split` (`ordinal_cutoff`) | `method`, `column`, `cutoff`, `n_rows`, `partitions: {train, validation: {n_rows, column_min, column_max, distinct_values}}`, `validation_share`, `stratified_on` (`null`), `implementation`, `scenario`, `groups`, `overlap`. The time column is read as integers, never converted to a date; a missing or non-integer value, or a partition of fewer than 5 rows, is `invalid_value`. |
| `split.groups` (any method, when the case declares a group column) | `null`, or `{column, n_groups, train_groups, validation_groups, shared_groups, validation_rows, validation_rows_in_shared_groups, validation_share_in_shared_groups, examples, capability, note}`: the group values both partitions share. A binary `stratified_random` split adds `groups` only when a group column is declared. |
| `eda.target_summary` | `partition` (`train`), `target`, `unit`, `n_rows`, `n_missing`, `n`, `mean`, `sd`, `min`, `q25`, `median`, `q75`, `max`, `note` |
| `eda.special_values` (regression) | `partition`, `n_rows`, `target`, `unit`, `special_values: [{column, value, meaning, status, source, n_rows, share, mean_target}]`, `co_occurrence` (as binary), `note` |
| `eda.mean_by:<column>` | `partition`, `column`, `target`, `unit`, `n_rows`, `overall_mean`, `binned`, `binning`, `groups: [{value, n_rows, mean, sd, small_count}]`, `min_group_rows`, `warnings`, `note`, and (G.12) `n_groups`, `max_groups`, `other`. The column is a feature or the time column. |

**High-cardinality columns (G.12, post-v0.1).** When a column that is not binned has more than `max_groups` ordinary values (`eda.MAX_GROUPS`, 20; `run eda.rate_by|eda.mean_by --column C --max-groups N` with `N >= 1`, else `invalid_arguments`; written in `params` only when given), `eda.rate_by` and `eda.mean_by` keep the `max_groups` largest groups by training rows (ties in value order) and fold the other values into one group, `(other values)` (`eda.OTHER_GROUP`), shown after them; special values and missing cells keep their own groups. `other` is then `{n_values, n_rows, n_positive, rate}` (`{n_values, n_rows, mean}` for `eda.mean_by`), else `null`; the first warning says how many values were folded; `not_yet_defensible` lists `high_cardinality_grouping` (`slots`).
| `fit.baseline` (regression) | `model` (`train_mean`), `target`, `unit`, `train_mean`, `train_median`, `n_train`, `features` (`[]`), `train: {n_rows, mae, rmse, mean_residual}`, `validation: {…same}`, `predictions` (blob description), `note` |
| `fit.linear` | `model` (`linear`), `target`, `unit`, `features`, `special_value_indicators`, `n_train`, `n_terms`, `intercept`, `coefficients`, `coefficient_scale`, `train: {n_rows, mae, rmse, mean_residual}`, `validation: {…same}`, `predictions` |
| `evaluate.regression` | `n`, `target`, `unit`, `models: {fit slot: {n, mae, rmse, mean_residual, median_abs_residual, max_abs_residual}}`, `intervals: {fit slot: {mae, rmse: {low, high}}}`, `deltas: {fit.linear: {mae, rmse: {point, low, high}}}` (candidate minus baseline; negative is a smaller error), `residuals: {fit slot: {n, mean, sd, min, q05, q25, median, q75, q95, max}}`, `residuals_by: [{column, binned, binning, groups: [{value, n_rows, small_count, models: {fit slot: {mae, mean_residual}}}], min_group_rows}]` (the time column, when declared), `predictions: {fit slot: result_id}`, `reference` (`fit.baseline`), `candidate` (`fit.linear`), `bootstrap: {replicates, seed, level, method}`, `residual_definition`, `note`. `params` is `{models, reference, candidate, metrics}`. Exposure: `validation_model_evaluation`. |

A regression `predictions` blob is gzip CSV `row_key,y,prediction` (`y` and `prediction` in the target unit). A residual is `y - prediction` (observed minus predicted); the mean residual is the bias.

`cmd_check` reads the features a fit used from `values.features` and `inputs.features`. A number written with a minus sign glued to its digits (`-1`) is read as negative by `cite.parse_numbers`; `10-18` is still two numbers.


### 8.6 Session report and session log (post-v0.1, observation kit)

For observed sessions with a junior (`docs/research/OBSERVATION-PROTOCOL.md`). Added within the extension point of §8 (`cli.EXTENSIONS['session-report']` is `mlkit.study.cmd_session_report`).

```text
hypotrail session-report --study DIR [--since REV] [--gap-minutes M] [--format text]
```

* **Read-only**: it never writes (it runs in a read-only process too) and is never logged. Exit `0`; `--gap-minutes` below 1 is `invalid_arguments`. `--format text` prints the same report as Markdown (not a contract).
* Payload `hypotrail.session_report/1`, keys in order: `schema`, `ok`, `study`, `revision`, `since`, `sources`, `span`, `commands`, `refusals`, `decisions`, `pauses`, `runs`, `renders`, `checks`, `gaps`, `timeline`, `privacy`. `sources` is `{revisions, events, session_log: {enabled, entries, path, note}, artifacts_status}`; `span` is `{first, last, seconds, revisions}`; `commands` counts logged invocations by command and verb; `refusals` lists `{time, command, code, reason, revision, proposal_id, activity}`; `decisions` has one item per proposal `{proposal_id, decision_id, proposed_at, proposed_revision, outcome (open|confirmed|withdrawn|superseded), closed_at, seconds_open, basis, delegation_scope, refused_confirmations, refusal_reasons}`; `pauses` has one item per pause (1: `prediction_time`, `feature_availability`; 2: `split`; 3: `policy`, `conclusion` in a binary study, `model_choice`, `conclusion` in a regression study, M3) `{pause, decisions, opened_at, closed_at, seconds, proposals, confirmed, delegated, refused_confirmations}`, a pause closing when all its decisions are confirmed; `runs` lists executions `{execution_id, activity, rules, column, started_at, outcome, ended_at, seconds, slot, result_id}`; `renders` lists deliverable statuses after logged commands and `render_failed` events; `checks` lists logged `check` runs `{time, revision, target, clean, counts, codes, traced, in_words}`; `gaps` lists idle intervals longer than `--gap-minutes` (default 20) `{from, to, minutes}`, which usually separate chats or days; `timeline` merges revision records, operational events and session-log lines, each with `source` (`revision`, `event`, `session_log`) and `time`.
* `--since REV` keeps revisions after `REV`, and events and log lines from the time revision `REV` was committed.
* **Privacy**: the report copies no conversation content. From revision records it keeps identifiers only: action, revision, decision and proposal ids, `superseded`, basis, delegation scope, the invalidation's mutation and how many results it made stale, activity, execution id, rule identifiers, column, slot, status, and the first 8 characters of a result id. It never copies `user_words`, restatements, rationales, proposed values, reasons, or checked text.

**Session log** (`mlkit/study/sessionlog.py`): an opt-in, append-only file `.hypotrail/session-log.jsonl`, one `hypotrail.session_log/1` line per invocation of a mutating command, refusals included, and of a `status` or `check` read, written after the outcome is final (a write failure is ignored and never changes the outcome). Reads (owner decision at the companion integration, amending the review fix "reads write nothing"): of the read-only commands (`sessionlog.READ_COMMANDS`: `status`, `plan`, `preview`, `decisions`, `evidence`, `explain`, `check`), `status` and `check` (`sessionlog.LOGGED_READS`) append a line **when the log is on**, refused or not, because how often the junior checks is what an observation wants; with the log on they change the study tree by that line only. The other reads never append a line (a preview follows a slider); `HYPOTRAIL_SESSION_LOG=1` on one of them still creates the empty file, which is the opt-in. With the log off, every read leaves the study tree byte-identical. `export` and `session-report` never touch the file (`sessionlog.UNLOGGED`), so an export leaves the study tree byte-identical with the log on as well. The `preview` fields of a line below come only from lines written before the review fix. The companion panel runs its own reads with `HYPOTRAIL_SESSION_LOG=0`: its automatic re-reads are not the junior's checks (COMPANION-ADVANCED §5).

* Enabled by `HYPOTRAIL_SESSION_LOG=1` for that process, which creates the file; once the file exists, every later logged invocation (a mutating command, `status`, `check`) appends to it, in any chat, until the file is deleted. `HYPOTRAIL_SESSION_LOG=0` disables it for a process. A read-only process (`HYPOTRAIL_READ_ONLY=1`) never writes it, and `session-report` and `export` are never logged (`sessionlog.UNLOGGED`). Off by default: without the file and the variable, no command writes it, so `check` and `status` stay write-free.
* A line has `schema`, `time`, `command`, `verb`, `exit_code`, `ok`, `revision`, `options` (only `--basis`, `--delegation-scope`, `--proposal`, `--kind`, `--lang`, `--rule`, `--column`, `--channel`, `--acknowledge-interruption`, `--since`, `--about`, `--resolve`, `--max-groups`, the switches `--summary`, `--json`, `--intervals`, whether `--text` read a file or stdin, and how many `--allow-user-text` were given), and, as they apply: `decision_id`, `proposal_id`, `note_id`, `activity`, `refusal: {code, reason}` (the reason only when it is an identifier such as `bare_acknowledgement`), `replayed`, `status`, `basis`, `delegation_scope`, `invalidation: {mutation, stale_results}`, `artifacts` (name to status), `slot`, `result_id` (8 characters), `check: {target, clean, counts, codes, traced, in_words}`, `current_step`, `next_action` (its kind), `rules`. It never holds `--user-words`, a note's `--text`, `--restatement`, `--rationale`, `--value`/`--value-json`, `--reason`, request ids, checked or user text, or any message.

### 8.7 Advanced companion

The additions for the advanced companion (ADR 0004) are specified in [CLI-CONTRACT-COMPANION.md](CLI-CONTRACT-COMPANION.md), which this document does not repeat. All of them are implemented (WP-E1 to WP-E3):

| Addition | Command | Schema |
|---|---|---|
| C1 | `status --summary --digest [--since REV]` | `hypotrail.summary/1` (keys `moments`, `pauses`, `last_session`, `digest`, `task`, `currency` after `recap`; `origin` in `open_proposals`) |
| C2 | `decisions` | `hypotrail.decisions/1` |
| C3 | `preview effects PROPOSAL` | `hypotrail.preview_effects/1` |
| C4 | `preview proposal DECISION --value V` | `hypotrail.proposal_draft/1` |
| C5 | `evidence [--result RID] [--limit N]` | `hypotrail.evidence/1` |
| C6 | `explain [--term ID]` | `hypotrail.explain/1` |
| C7 | `export handoff [--out DIR]` | `hypotrail.export/1`, and the pack's `hypotrail.handoff/1` |
| C8 | activity `eda.distribution` (`--column`, training rows) | `hypotrail.run/1`, value shape in CC §8 |
| C9 | `decide propose ... --channel chat\|cli\|webview` | `hypotrail.decide/1`; the proposal's `origin`, also the last key of `open_proposals` in §4 |
| C10 | report anchors `r-<result_id>`; the optional `location` of `check` findings | `hypotrail.check/1` |

`status --summary` without `--digest` is byte-for-byte unchanged. A refusal of `export handoff` names the command `export handoff`, as `decide` names its verb. New error code: `export_target_exists` (`export handoff`: `--out` exists and is not an empty folder; `details.path`; nothing was written). `test_contract_freeze.py` pins the schema names (`test_companion_schema_names`).

## 9. Storage objects

### Registry entry `hypotrail.result/1`

`.hypotrail/registry/<result_id>.json`, written once. Keys: `schema`, `result_id`, `input_key`, `activity`, `params`, `inputs`, `code`, `output`, `blobs`, `partition`, `n_rows`, `exposure_id`, `execution_id`, `started_revision`, `environment`, `created`.

```text
output.sha256 = sha256(canonical({"values": output.values, "blobs": blobs}))
input_key     = sha256(canonical({"activity", "params", "inputs", "code_fingerprint"}))
result_id     = sha256(canonical({"activity", "params", "inputs", "code_fingerprint", "output_sha256"}))
canonical(x)  = UTF-8 JSON, sorted keys, separators (",", ":"), ensure_ascii false, NaN refused
```

`code` is `{fingerprint, modules: {module: sha256 of its source}}`; `fingerprint = sha256(canonical(modules))`. The environment, ids of the execution and the exposure, the revision, and `created` are outside identity. `registry.get` recomputes every digest and checks every blob. `.hypotrail/registry-index.jsonl` indexes `input_key → result_id`; two ids for one key flag nondeterminism (`nondeterministic_result` event).

### Exposure record `hypotrail.exposure/1`

`.hypotrail/exposure.jsonl`, append-only. Keys: `schema`, `exposure_id`, `revision`, `activity`, `result_id`, `execution_id`, `purpose`, `partition`, `n_rows`, `row_keys` (blob sha256 of the sorted keys, one per line), `dataset_sha256`, `columns`, `time`. Purposes: `structural_inspection`, `train_eda`, `train_fit`, `validation_model_evaluation`, `validation_policy_selection`. Partitions: `all`, `train`, `validation`.

### Study state `hypotrail.study/1`

`.hypotrail/state.json` with `state.sha256`; see `framework/mlkit/study/state.py` and plan §3.1. Clients read it through `status` or `read.open`, never directly. Since M3 a new state has the optional top-level key `task` (`state.TOP_OPTIONAL_KEYS`); a state without it is a binary study, and its `decisions` hold the decisions of its task. Post-v0.1 (P2) adds the optional key `notes` (`{note_id: note}`, §5.1), written with the first note; a state without it has no notes. v0.2a (ADR 0005, §5.2) adds the optional keys `mode` and `language` (written by every new study; a state without them is a guided study in English) and `mode_history` (written by the first `mode set`); a proposal may hold `labels`, and a confirmation `agent_concern` (`state.CONFIRMATION_OPTIONAL_KEYS`). No existing state is migrated.

## 10. Regression study (M3)

A case with `task: regression` (a numeric target with a declared `unit`, `positive_label: null`; `CASE-CONTRACT.md`) runs the same workflow with a task-aware decision set. Nothing in the engine names a dataset; Auto MPG and the synthetic generator's regression variant run the same code.

| | Binary study | Regression study |
|---|---|---|
| Decisions | `prediction_time`, `feature_availability`, `split`, `policy`, `conclusion` | `prediction_time`, `feature_availability`, `split`, `model_choice`, `conclusion` |
| Split | `stratified_random`, or `ordinal_cutoff` when a time column is declared | `random`, or `ordinal_cutoff` when a time column is declared |
| Training EDA | `eda.target_rate`, `eda.special_values`, `eda.rate_by:<column>` | `eda.target_summary`, `eda.special_values`, `eda.mean_by:<column>` |
| Models | `fit.baseline` (constant prior), `fit.logistic` | `fit.baseline` (training mean), `fit.linear` |
| Third pause | `policy.evaluation`, then `policy` | `evaluate.regression` (MAE, RMSE in the target unit, paired bootstrap intervals, residuals), then `model_choice` |
| Conclusion verdicts | `adopt_policy`, `keep_baseline`, `inconclusive` | `adopt_model`, `keep_baseline`, `inconclusive` |
| Dependency table | `dependencies.MUTATIONS` | `dependencies.REGRESSION_MUTATIONS` (row 13 `model_choice`) |

An activity of the other task is refused with `invalid_arguments` (`details.activities`, `details.task`); `preview policy` is refused in a regression study (`unsupported_capability`). A missing target value is refused at `init`, for both tasks (`unsupported_capability`, capability `missing target values (v0.2)`, `CASE-CONTRACT.md` §Dataset); a regression fit keeps the same refusal as a second guard. The time column is never a model feature (its role is `time`); a model fitted on earlier periods and validated on later ones extrapolates, which the residuals by period show. A declared group column is accepted (`case.limitations`), its overlap between partitions is reported in every split, and `not_yet_defensible` lists `grouped_split_unsupported`.
