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
hypotrail init --case CASE --study DIR
hypotrail status --study DIR [--since REV] [--json]
hypotrail plan --study DIR
hypotrail decide propose DECISION (--value TEXT | --value-json JSON)
                 --restatement TEXT --rationale TEXT
                 --request-id ID --expected-revision REV --study DIR
hypotrail decide confirm PROPOSAL --user-words TEXT [--channel chat|cli|webview] [--actor NAME]
                 --request-id ID --expected-revision REV --study DIR
hypotrail decide withdraw PROPOSAL [--reason TEXT]
                 --request-id ID --expected-revision REV --study DIR
```

`--channel` defaults to `chat` and `--actor` to `user`. Reserved extension commands, absent in Phase 1 and refused with `unsupported_capability` until their module exists: `run`, `render`, `check`, `preview` (§8). Phase 3 adds `render` and `check` (§8.3).

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

* `status.since` is the `--since` value or `null`; `changed` is `revision > since` (or `null`); `changes_since` lists the revision records after `since` (or `null`). A webview polls with `--since`.
* `decide.revision` is the revision created by the request (also on replay). `artifacts` is `null` until Phase 3 renders after commits (§8.3).
* `init.agent_instructions` is `{source, copied, skipped_existing, status}`; `status` is `copied`, `kept_existing`, or `no_templates_yet`. `ignored_sources` names the companion files found next to the case (`project.json`, `results.json`, `tutorial-results.json`, `answers.yaml`, `project.yaml`, `frame.yaml`); they are never read. `structural_exposure` is `{exposure_id, n_rows}`.
* `error` is `{code, message, details?, problems?}`. `problems` (case validation) is a list of `{path, problem}`.

### 3.1 Plan steps and next action

Each item of `plan.steps` and `view.plan` has the keys `id`, `title`, `question`, `expected_output`, `completion`, `pause`, `decision`, `activities`, `decide_first`, `missing_results`, `requires`, `status`, `current`. Step ids, in order: `prediction_time`, `feature_availability`, `split`, `train_eda`, `models`, `policy`, `conclusion`. Step status is one of `done`, `needs_reconfirmation`, `awaiting_confirmation`, `ready`, `blocked`.

`next_action` always has `kind` and `message`. Kinds and their extra keys:

| `kind` | Extra keys |
|---|---|
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
| `decide.confirm` | `decision_id`, `proposal_id`, `status` (`confirmed`), `value`, `user_words`, `channel`, `actor`, `invalidation` |
| `decide.withdraw` | `proposal_id`, `decision_id`, `status` (`withdrawn`), `decision_status` |

`invalidation` is `{mutation, row, reason, stale_results, stale_slots, reconfirm_required}` (§6). Proposal ids are `p_<n>`, assigned in order.

## 4. View model `hypotrail.view/1`

`mlkit.study.view.build(study_dir) -> dict` is the **single** view of a study. `status` prints it under `view`. The HTML report, the generated notebook, and a future webview consume it; renderers do not read raw state. It holds no clock reading, so two builds of one study content are equal.

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
| `open_proposals` | List of `{proposal_id, decision_id, value, restatement, rationale, revision, created}`, oldest first |
| `decisions` | `{decision_id: {decision_id, status, value, proposal_id, depends_on, revision, reason, confirmation, open_proposals}}` for the five decisions |
| `facts` | `{by_status: {documented_fact: [...], scenario_assumption: [...], observed: [...], unknown: [...]}, count}`; items are `{id, value, source}` |
| `structure` | The case structure statements (`row_unit`, `group_column`, `time_column`, `duplicates`) |
| `results` | `{slot: result item}` for every promoted slot (below) |
| `stale` | `{result_id: {reason, since}}` |
| `invalidations` | The invalidation records (§6), oldest first |
| `executions` | `{active, interrupted, late}` (filled by Phase 2) |
| `artifacts` | `{manifest, status, items}`; before any render `{manifest: null, status: "not_rendered", items: {}}` |
| `exposure` | `{records, rows_exposed, by_purpose, by_partition, validation_rows_used_for_selection, prior_exposure}` |
| `not_yet_defensible` | List of `{id, text, ...}` (plan §6) |
| `settings` | `{bootstrap: {replicates, seed, level}}` |

`decisions.*.confirmation` is `null` or `{user_words, channel, actor, restatement, proposal_id, revision, time, authenticated}`. `authenticated` is always `false`: the engine records words, it cannot verify who typed them. Decision status is one of `open`, `proposed`, `confirmed`, `reconfirm_required`, `superseded`.

A result item has the keys `slot`, `result_id`, `activity`, `current`, `stale_reason`, `partition`, `n_rows`, `values`, `blobs`, `params`, `inputs`, `code_fingerprint`, `environment`, `execution_id`, `exposure_id`, `started_revision`, `integrity`. `integrity` is `ok` or the refusal code (`integrity_error`, `unknown_result`); a result that fails it has `current: false`, `values: null`, and adds a `result_integrity` item to `not_yet_defensible`. **Only a result item with `current: true` and `integrity: "ok"` may be cited.**

`not_yet_defensible` ids emitted in v0.1: `unconfirmed_decisions`, `validation_is_not_independent`, `public_data_already_explored`, `no_time_or_entity_identifier`, `uncertain_features_included`, `stale_results`, `interrupted_executions`, `no_causality`, `workbench_not_tracked`, `result_integrity`.

## 5. Decisions and values

| Decision | `--value` / `--value-json` | Confirmation needs |
|---|---|---|
| `prediction_time` | Non-empty text | — |
| `feature_availability` | `{feature: status}` for **every** variable with role `feature`; status ∈ `available_at_prediction`, `not_available`, `uncertain_excluded`, `uncertain_included` | `prediction_time` confirmed |
| `split` | `{"method": "stratified_random", "validation_fraction": f, "seed": n}` with `0 < f < 1` | `prediction_time`, `feature_availability` confirmed |
| `policy` | `"threshold:t"` (`0 <= t <= 1`, inclusive `>=`) or `"capacity:k"` (`k >= 1`) | the three above, and a current `policy.evaluation` whose `params.rule` (or `params.rules`) contains the value |
| `conclusion` | `{"verdict": v, "text": "..."}`, `v` ∈ `adopt_policy`, `keep_baseline`, `inconclusive` | the three above, and `policy` confirmed unless `v` is `keep_baseline` |

Proposal rules:

* A proposal is first-class: `{proposal_id, decision_id, value, restatement, rationale, revision, status, created, request_id, basis}`; status ∈ `open`, `confirmed`, `withdrawn`, `superseded`. `basis` holds the confirmed values of the decisions it depends on.
* Proposing never changes a confirmed decision. A new proposal supersedes an older open one for the same decision.
* The restatement and rationale may only contain numbers that appear in the proposed value (a fraction may also appear as a percentage); anything else is `literal_number_in_text`.

Confirmation rules (`ambiguous_confirmation`, with `details.reason`):

| `reason` | When |
|---|---|
| `missing_user_words` | `--user-words` is empty or blank |
| `bare_acknowledgement` | The words are only acknowledgements ("ok", "yes, that is right", "keep that", "garde ça", "d'accord") |
| `proposal_not_found` | No such proposal |
| `proposal_withdrawn`, `proposal_superseded`, `proposal_confirmed` | The proposal is not open |
| `same_request` | The proposal was not created by an earlier request |
| `proposal_stale` | A decision the proposal rests on changed since it was made (`details.basis`, `details.current_basis`) |

Then, in order: the case and dataset bytes must still match (`dataset_changed`), the value must be valid (`invalid_value`), and the pause preconditions must hold (`precondition_missing`, `details.missing`). A confirmation records `{user_words (verbatim), proposal_id, restatement, authenticated: false, channel, actor, revision, time}` and applies §6.

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

A first confirmation (`mutation: first_confirmation`) and a confirmation with an unchanged value (`unchanged_value`) have `row: null` and no effect. Facts are never reconfirmed. A policy confirmation never marks its own evaluation stale (a current evaluation of the new rule is its precondition). Staleness propagates downstream through registry lineage.

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
| `dataset_changed` | case, `decide confirm` | Dataset or case bytes differ from the recorded sha256 |
| `unsupported_capability` | case, data, CLI | A capability this version does not have (`details.reasons` or `details.command`) |
| `unknown_decision` | `decide propose` | Decision id not in the five |
| `invalid_value` | `decide` | The value does not fit the decision (§5) |
| `literal_number_in_text` | `decide propose` | A number in the restatement or rationale is not part of the value (`details.numbers`) |
| `ambiguous_confirmation` | `decide confirm` | §5, `details.reason` |
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
| `interrupted_execution_pending` | `run` | An execution has an unknown outcome; every `run` is refused (exit 4) until `run --acknowledge-interruption E` (`details.interrupted`) |
| `unknown_execution` | `run` | `--acknowledge-interruption E` names no interrupted execution (`details.interrupted`), or an internal step names no active execution |
| `read_only` | activities, guard, `render` | `HYPOTRAIL_READ_ONLY=1` (a notebook kernel): the process may read results but never compute, record, render, or write one (`run`, every fit, `render`, and the notebook generator refuse). Phase 3's `read_only_process` was merged into this code by the Phase 4 integration |
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
5. **Exit code 4** for an execution with an unknown outcome, including the `interrupted_execution_pending` refusal; `unknown_execution` refuses an acknowledgement of nothing (exit 2).
6. **Payload schemas added in Phase 2** (additions; the five schemas of §3 are unchanged):

   | Schema | Emitted by | Keys |
   |---|---|---|
   | `hypotrail.run/1` | `run`, `run --acknowledge-interruption` | `schema`, `ok`, `study`, `action` (`run` or `run.acknowledge`), `request_id`, `replayed`, `revision`, `activity`, `execution_id`, `status`, `result_id`, `values`, `result`, `artifacts` |
   | `hypotrail.preview/1` | `preview policy` | `schema`, `ok`, `study`, `revision`, `kind`, `rules`, `models`, `evaluations`, `intervals`, `adopted`, `recorded` (`false`), `note` |

   `run.status` is one of `promoted`, `late_not_promoted`, `already_current`, `running`, `failed`, `interrupted_unknown`, `acknowledged`. `values` are the registry values of `result_id` (cite them only while the slot is current, §4). `preview` writes nothing and records no exposure; `validation_policy_selection` is recorded by `run policy.evaluate`.

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
* The manifest lives at `.hypotrail/artifacts.json` (plan §3.6) with `{"status": …, "artifacts": {name: {...}}}`; `view.artifacts` exposes it as `{manifest, status, items}`. Since the Phase 4 integration, `items.<name>.status` and `view.artifacts.status` are the **effective** statuses (`mlkit.study.currency.effective_status`, the pure currency rule below, against the current state), not the status stored by the last render; the stored value stays visible as `items.<name>.recorded_status`. A study whose state moved on without a render therefore shows `stale`.
* `framework/mlkit/study/cmd_check.py` provides `hypotrail check` with the same `configure`/`main` interface.
* Teaching texts belong in `mlkit/study/content/*.yaml`, not in this contract.

Added by Phase 3 (WP3.1–WP3.4), within these extension points:

```text
hypotrail render --study DIR
hypotrail check --study DIR [--text PATH | --text -]
```

| Schema | Emitted by | Keys |
|---|---|---|
| `hypotrail.render/1` | `render` | `schema`, `ok`, `study`, `revision`, `status`, `artifacts` |
| `hypotrail.check/1` | `check` | `schema`, `ok`, `study`, `revision`, `target`, `clean`, `counts`, `findings`, `traced` |
| `hypotrail.artifacts/1` | `.hypotrail/artifacts.json` | `schema`, `revision`, `status`, `artifacts` |

* Artefact names: `report` (`reports/study.html`), `notebook` (`notebooks/study_generated.py`), `workbench` (`notebooks/workbench.py`). A manifest item has `path`, `kind`, `revision`, `status`, `consumed`, `sha256`, `generated`, `template_version`, `error`, `last_ok_revision`, `user_edits_preserved`, `candidate`. An artefact is current iff `status` is `ok`, `revision` equals the state revision, and every result in `consumed` is current; the workbench (`generated: false`) is never stale.
* `render.artifacts` and `decide.artifacts` map each artefact name to `{status, path, revision, last_ok_revision, error}`, plus `tracked: false` for the workbench and `candidate` or `user_edits_preserved` when present. `status` is `ok`, `stale`, or `failed`; `render` exits `3` when any artefact is `stale` or `failed`, and refuses with `read_only` in a read-only process. `error` is `{code, message}`; `code` is `render_failed` for an unexpected failure or a refusal code such as `untraceable_number`.
* On a failed HTML render the previous `reports/study.html` is kept and a banner replaces the region `<!--hypotrail:banner-->…<!--/hypotrail:banner-->`. Fault injection for tests: `HYPOTRAIL_FAULT=render_html|render_notebook` (comma-separated), honoured only when `HYPOTRAIL_TEST_HOOKS=1`.
* HTML numbers are `<data value data-result-id data-path title>` elements. Text shown as recorded rather than computed is wrapped in an element with `data-literal` ∈ `revision`, `ordinal`, `user_words`, `proposal`, `decision_value`, `case`, `identifier`, `parameter`, `environment`, `setting`, `message`, `category`; `check` ignores numbers there.
* `check` always exits `0`; `clean` is false when a finding has severity `error`. A finding is `{code, severity, where, message, details?}`. Codes (severity): `number_outside_result`, `unknown_result_id`, `value_mismatch`, `stale_result_cited`, `feature_without_status`, `excluded_feature_used`, `untraceable_number`, `stale_number` (error); `causal_wording`, `forecast_wording`, `artifact_not_current`, `untracked_files` (warning). `traced` lists each number of the checked text with the `result_id` and `path` (or the decision, setting, or case statement) it matched.

### 8.5 Result value shapes

Added by the Phase 4 integration. Phases 2 and 3 were built in parallel and met here; this section fixes **one** shape per activity. Producers (`mlkit.study.activities`, `eda`, `fit`, `policy`) emit it; consumers (`render_html`, `notebook_view`, `cmd_check`, the workbench template, `content/activities.yaml`) read it; the test fixtures (`framework/tests/study/deliverables/phase3_study.py`) build it. It is the producers' shape, completed where the report needed a field (`split.partitions.*.n_positive`, `rate`). Keys listed here are stable within `hypotrail.result/1`; producers may add keys. Paths use the `mlkit.study.cite` grammar (a segment holding a dot goes in brackets: `rules.[threshold:0.3].models.[fit.logistic].precision`).

| Activity (slot) | `values` |
|---|---|
| `split` | `method`, `validation_fraction`, `seed`, `stratified_on`, `n_rows`, `partitions: {train, validation: {n_rows, n_positive, rate}}`, `implementation`, `overlap` (`null`, or `{rows_in_new, rows_in_old, moved, transitions, previously_exposed: {partition: {purpose: n}}, previous_split, exposure_up_to_revision, note}` after a split change). The positive counts come from the stratification read of the target (`structural_inspection`). |
| `eda.target_rate` | `partition` (`train`), `target`, `positive_label`, `n_rows`, `n_positive`, `n_negative`, `rate` |
| `eda.special_values` | `partition`, `n_rows`, `special_values: [{column, value, meaning, status, source, n_rows, share, n_positive, rate}]`, `co_occurrence: [{a: {column, value}, b: {column, value}, n_a, n_b, n_both, n_either, same_rows}]`, `note` |
| `eda.rate_by:<column>` | `partition`, `column`, `n_rows`, `overall_rate`, `binned`, `binning`, `groups: [{value, n_rows, n_positive, rate, small_count}]`, `min_group_rows`, `warnings`, `note` |
| `fit.baseline` | `model` (`constant_prior`), `train_rate`, `n_train`, `n_train_positive`, `features` (`[]`), `validation: {n_rows, n_positive, roc_auc, average_precision}`, `predictions` (blob description), `note` |
| `fit.logistic` | `model` (`logistic`), `features` (used, case order), `special_value_indicators`, `n_train`, `n_train_positive`, `n_terms`, `intercept`, `coefficients: {term: value}`, `coefficient_scale`, `iterations`, `validation: {…as above}`, `predictions`. `inputs.features` repeats the features (identity). |
| `policy.evaluation` | `rules: {rule: {models: {fit slot: evaluation}, intervals: {fit slot: {precision, recall, volume: {low, high, undefined_replicates}}}, deltas: {fit slot ≠ reference: {precision, recall, volume: {point, low, high, undefined_replicates}}}}}`, `n`, `n_positive`, `predictions: {fit slot: result_id}`, `reference` (`fit.baseline`), `bootstrap: {replicates, seed, level, method}`, `counts`, `note`. `params` is `{rules, models, reference}`. |

An *evaluation* is the output of the pure `mlkit.study.policy.evaluate(y, score, rule)`, also used by `preview policy` and the workbench: `rule`, `kind`, `parameter`, `n`, `n_positive`, `selected`, `true_positives`, `false_positives`, `false_negatives`, `precision`, `recall`, `volume`, `volume_rate`, `tied_at_cut`, `cut: {score, n_tied, fraction_selected}`, `selection` (`exact`, or `expected` when a capacity cut splits a tie group pro rata). A ratio with an empty denominator is `null` and is never cited.

`cmd_check` reads the features a fit used from `values.features` and `inputs.features`. A number written with a minus sign glued to its digits (`-1`) is read as negative by `cite.parse_numbers`; `10-18` is still two numbers.

### 8.4 Agent instructions (Phase 4)

`init` copies every file under `framework/mlkit/study/agent/` except its `README.md` into the study, keeping relative paths, never overwriting.

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

`.hypotrail/state.json` with `state.sha256`; see `framework/mlkit/study/state.py` and plan §3.1. Clients read it through `status` or `read.open`, never directly.
