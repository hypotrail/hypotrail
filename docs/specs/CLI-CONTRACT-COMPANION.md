# CLI contract: additions for the advanced companion

Status: **specified; WP-0 stubs registered (§13), features not implemented.** These are the interfaces that the advanced companion
([COMPANION-ADVANCED.md](COMPANION-ADVANCED.md), [ADR 0004](../decisions/0004-companion-advanced.md))
needs from the engine. The parallel work packages of the
[plan](../plans/COMPANION-ADVANCED-PLAN.md) treat this document as frozen. Any change goes
through the integrator, who updates this document and the contract tests
(`framework/tests/study/companion_contract.py` and `test_contract_companion_e{1,2,3}.py`)
in the same commit.

This document extends [CLI-CONTRACT.md](CLI-CONTRACT.md). It does not change anything that
document lists. Every rule of CLI-CONTRACT §1 to §3 applies here too:

- `--study` is required;
- stdout holds exactly one JSON document;
- `hypotrail.error/1` is used for refusals, with the exit codes of §2;
- payload keys are listed in their emitted order;
- clients ignore keys they do not know.

When the first work package lands, the integrator adds a section §8.7 to CLI-CONTRACT.md. That section points here and lists the new schemas, and `test_contract_freeze.py` gains the new schema names in the same commit.

**Why a separate document.** CLI-CONTRACT.md is frozen. Its freeze test reads it. Three engine work packages will edit their parts of this contract in parallel. Keeping the additions in one separate file avoids merge conflicts in the frozen document, and it keeps the v0.1 contract readable on its own.

## 0. Summary of additions

| # | Addition | Kind | Schema | Writes |
|---|---|---|---|---|
| C1 | `status --summary --digest [--since REV]` | read, additive keys | `hypotrail.summary/1` (keys added after `recap`) | nothing |
| C2 | `decisions` | read, new command | `hypotrail.decisions/1` | nothing |
| C3 | `preview effects PROPOSAL` | read, new `preview` kind | `hypotrail.preview_effects/1` | nothing |
| C4 | `preview proposal DECISION --value V` | read, new `preview` kind | `hypotrail.proposal_draft/1` | nothing |
| C5 | `evidence [--result RID] [--limit N]` | read, new command | `hypotrail.evidence/1` | nothing |
| C6 | `explain [--term ID]` | read, new command | `hypotrail.explain/1` | nothing |
| C7 | `export handoff [--out DIR]` | file export, new command | `hypotrail.export/1`, `hypotrail.handoff/1` | files under `--out` only, never study state |
| C8 | activity `eda.distribution:<column>` | new activity | `hypotrail.run/1` (unchanged), value shape §8 | the usual `run` writes |
| C9 | `decide propose ... [--channel chat\|cli\|webview]` | mutation, additive option | `hypotrail.decide/1` (unchanged); proposal key `origin` | the usual `propose` writes |
| C10 | report anchors `id="r-<result_id>"` and `check` finding `location` | deliverable and read, additive | `hypotrail.check/1` (key added in findings) | nothing new |
| C11 | content files `digest.yaml`, `drafts.yaml`, `evidence.yaml`, `learn.yaml`; `moments` in `steps.yaml`; `example` in `glossary.yaml` | engine data | `hypotrail.content.*/1` | nothing |

Common guarantees of every **read** addition (C1 to C6):

- R1. It takes no writer lock. It writes no state, revision, registry entry, blob, exposure record, artefact, manifest, or event. It works under `HYPOTRAIL_READ_ONLY=1`. A test runs each one on a study whose directory tree is made read-only (`chmod -R a-w`), and the test compares the tree's digest before and after.
- R2. It records **no exposure**. It reads registry values and blobs that were already exposed when they were computed. It never reads dataset rows. The one exception is `preview policy`, which already reads stored predictions (CLI-CONTRACT §8.1 item 6). C1, C2, C3, C5, and C6 do not read the dataset file at all.
- R3. It does not import pandas, scikit-learn, or scipy at module level. C1, C2, C3, C5, and C6 do not import numpy either. The import-time test of ADR 0002 is extended to `status --summary --digest`, `decisions`, `evidence`, and `explain`. The test records the time and asserts no threshold. It does assert that the modules are absent from `sys.modules`.
- R4. Its output is deterministic for one study content. It reads no clock. Two runs on one revision give the same bytes, apart from the absolute `study` path.
- R5. The session log (CLI-CONTRACT §8.6), when it is enabled, records it like any other command. `sessionlog` adds the switches `--digest` and `--limit` and the identifiers `--result`, `--term`, and the preview kind to its option whitelist. It never logs `--value` text of `preview proposal` beyond a rule identifier or a model slot, which are identifiers.

## 1. C1: `status --summary --digest`

```text
hypotrail status --study DIR --summary --digest [--since REV] [--json]
```

- `--digest` requires `--summary`. Without it the command fails with `invalid_arguments`.
- Without `--digest`, `status --summary` is byte-for-byte unchanged, and `status --json` is unchanged.
- With `--digest`, five keys are appended **after** `recap`, in this order: `moments`, `pauses`, `last_session`, `digest`, `task`. The schema stays `hypotrail.summary/1`, because the change is additive (CLI-CONTRACT §3, the precedent of `recap` and `notes`).
- `task` is `binary` or `regression` (`view.task`). It removes the client's inference from step ids (ADR 0004 open question 7, answered yes; decision CA.3).
- With `--digest` only, each `open_proposals` item gains `origin` as its last key (C9). Without `--digest` the items are unchanged, so the byte-identical rule above holds (decision CA.4).

### 1.1 `moments`

The four moments of JUNIOR-WORKFLOW.md, as a list of exactly four items, in order: `{id, title, steps}`.

| `id` | `title` | binary `steps` | regression `steps` |
|---|---|---|---|
| `frame` | `Frame the change` | `prediction_time`, `feature_availability`, `split` | the same |
| `evidence` | `Prepare evidence` | `train_eda` | `train_eda` |
| `compare` | `Work and compare` | `models`, `policy` | `models`, `model_choice` |
| `conclude` | `Conclude and hand over` | `conclusion` | `conclusion` |

The mapping is engine data: `content/steps.yaml`, key `moments`, with a `regression_moments` overlay. The mockup's step labels ("Problem framing", "Evaluation design") are not used. A client shows the plan's step `title`s.

### 1.2 `pauses`

A list of three items `{pause, decisions, status, confirmed}`:

- `pause` is `1`, `2`, or `3`.
- `decisions` follows the mapping of `session-report`: pause 1 is `prediction_time` and `feature_availability`; pause 2 is `split`; pause 3 is `policy` and `conclusion` (binary), or `model_choice` and `conclusion` (regression).
- `status` is `closed` when every decision of the pause is `confirmed`, and `open` otherwise.
- `confirmed` lists the decisions of the pause that are confirmed.

### 1.3 `last_session`

`{boundary_revision, boundary_time, gap_minutes}`.

- The engine reads the commit times of `revisions.jsonl` in order. `boundary_revision` is the last revision **before** the latest gap between two consecutive records that is longer than `view.SESSION_GAP_MINUTES`. That constant is 20, the default of `session-report --gap-minutes`.
- `boundary_time` is that revision's commit time, as recorded.
- `gap_minutes` is the length of that gap, rounded down to whole minutes.
- With no such gap, the result is `{boundary_revision: 1, boundary_time: <time of revision 1>, gap_minutes: null}`.
- The engine never compares a recorded time with the current clock (R4). "Since your last session" therefore means the changes of the latest working session, or of everything since the previous one. It does not mean "since this panel last looked", because that would require storage on the client.

### 1.4 `digest`

`{since, until, items, truncated, counts}`.

**`since` and `until`.** `since` is `--since REV` when given; otherwise it is `last_session.boundary_revision`. `until` is the current revision. `--since` below 0 or above the current revision is refused with `invalid_arguments`.

**`items`.** One item per revision record `r` with `since < r.revision <= until`, oldest first. At most `view.DIGEST_MAX_ITEMS` (50) items are listed: the newest ones, with `truncated: true` when older ones were dropped. Each item has the keys below, in this order; a key that does not apply is `null`:

| Key | Content |
|---|---|
| `revision`, `time` | From the record |
| `action` | The record's action (`decide.confirm`, `run.promote`, ...) |
| `kind` | One of `proposed`, `confirmed`, `withdrawn`, `hold_recorded`, `hold_resolved`, `result_added`, `result_replaced`, `run_failed`, `run_interrupted`, `interruption_acknowledged`, `other` |
| `decision_id`, `proposal_id`, `note_id` | Identifiers from the params and the result |
| `activity`, `slot`, `result_id`, `execution_id` | For `run.*` actions; `result_id` is the full id |
| `rules`, `column` | Rule identifiers and the column of the activity |
| `channel`, `basis`, `delegation_scope` | For `confirmed` |
| `superseded` | Proposal ids that a `proposed` item superseded |
| `invalidation` | `null`, or `{mutation, row, stale_slots, reconfirm_required, refit, kept_fits}`. `refit` and `kept_fits` are computed from the invalidation's `effects`: `kept_fits` lists the `fit.*` slots that were current before and are still current |
| `text` | One flat English sentence from `content/digest.yaml` (below) |

**`run.reserve`.** These records produce no item. Each one is counted in `counts.runs_started`.

**`text`.** The sentence holds no revision number and no result id (P3). It may hold rule identifiers (`capacity:100`), decision titles, column names, and, for `hold_recorded` and `hold_resolved` only, the junior's words, quoted verbatim. It never holds a restatement, a rationale, or confirmation words, because those are shown by the Decisions tab with their own label. Examples of the template output:

- "The policy was confirmed in the junior's words (channel webview)."
- "The policy evaluation was replaced: capacity:100 evaluated. Models unchanged, nothing refitted."
- "The policy needs confirmation again: the split changed."
- "Hold recorded on the policy: \"don't adopt anything until I bring my manager's figure\"."

A regression study's texts never use the vocabulary of a decision rule (CLI-CONTRACT §4 recap rule): its sentences come from the template's `regression` overlay.

**`counts`.** `{proposed, confirmed, withdrawn, holds_recorded, holds_resolved, results_added, results_replaced, runs_started, runs_failed, invalidations}`.

**Refusals.** `study_missing`, `integrity_error`, and `invalid_arguments`.

**Acceptance.**

- The `digest` of a study at revision N with `--since N` has no items.
- Each confirmation, proposal, note, and promoted run of the Bank walkthrough appears with its `kind`.
- The sentence for a policy reconfirmation names the reconfirmed decision.
- The regression digest of the Auto MPG walkthrough holds none of the words `threshold`, `capacity`, `precision`, `recall`, `policy`, or `positive class`.

## 2. C2: `decisions`

```text
hypotrail decisions --study DIR [--json]
```

Payload `hypotrail.decisions/1`, keys: `schema`, `ok`, `study`, `revision`, `task`, `decisions`, `proposals`, `history`, `reconfirm_queue`, `notes`.

- **`decisions`** is a list in the task's decision order. Each item is `{decision_id, title, pause, step, status, value, depends_on, reason, confirmation, open_proposals}`.
  - `title` is the title of the plan step of that decision.
  - `confirmation` is `view.decisions.*.confirmation` (`CONFIRMATION_VIEW_KEYS`), or `null`.
- **`proposals`** lists every proposal of the state, whatever its status, oldest first, as `{proposal_id, decision_id, value, restatement, rationale, status, revision, created, closed_revision, closed_reason, origin}`.
  - `origin` is `{channel}` (C9), or `null` for a proposal recorded before C9.
  - Values are full. Availability is not grouped.
- **`history`** lists one item per committed `decide.confirm` record of `revisions.jsonl`, oldest first: `{revision, time, decision_id, proposal_id, value, user_words, basis, delegation_scope, channel, actor, current, superseded_at}`.
  - `current` is true for the confirmation that the decision holds now.
  - `superseded_at` is the revision of the next confirmation of the same decision, or `null`.
  - `user_words` is copied verbatim from the record.
  - A record without `basis` reads `explicit`. One without `delegation_scope` reads `null`. One without `channel` reads `chat`.
- **`reconfirm_queue`** lists the decisions whose status is `reconfirm_required`: `{decision_id, reason, since_revision, previous, open_proposal}`.
  - `previous` is `{value, user_words, basis, channel}` of the confirmation that the decision still shows.
  - `since_revision` is the revision of the invalidation that set the status.
  - `open_proposal` is the open proposal id for that decision, or `null`.
- **`notes`** is `view.notes`, unchanged.

**Refusals.** `study_missing` and `integrity_error`.

**Acceptance.**

- After the Bank walkthrough, with a policy change from threshold to capacity followed by a reconfirmation, `history` holds two `policy` items, and only the last one is `current: true`.
- `proposals` lists the superseded threshold proposal with `status: "superseded"`.
- `reconfirm_queue` is empty at the end.
- A delegated split item shows `basis: delegated_default` and its scope.

## 3. C3: `preview effects`

```text
hypotrail preview effects PROPOSAL --study DIR [--json]
```

`cmd_preview.py` becomes a dispatcher on its positional `kind`, which takes the values `policy`, `effects`, or `proposal`:

- `policy` is unchanged;
- `effects` is implemented in `mlkit/study/preview_effects.py`;
- `proposal` is implemented in `mlkit/study/preview_proposal.py`.

`--rule` becomes required for `policy` only. A missing `--rule` for `policy` is still `invalid_arguments`.

It answers this question: if this open proposal were confirmed **now**, by words the engine accepts, what would change? It is the dry run of `decide confirm`.

**One implementation.** `commands.py` factors the part of `_confirm.run` that does not depend on the words into a pure function:

```python
commands.confirmation_plan(state: dict, store, proposal_id: str) -> dict
# {'blocked': [refusal dicts], 'decision_id', 'value', 'previous', 'effects', 'invalidation'}
```

Both `decide confirm` and `preview effects` call it. `preview effects` runs it on a deep copy of the state that was read without a lock. It runs `dependencies.apply_effects` on that copy with a store used for lineage reads only. It discards the copy.

**Guarantee.** At revision N, take a preview with empty `blocked`. Then take a `decide confirm` of the same proposal at the same revision whose words are accepted. Its `result.invalidation` equals the preview's `{mutation, row, reason, stale_results, stale_slots, reconfirm_required}`. A test checks this on every confirmation of the Bank and Auto MPG walkthroughs.

Payload `hypotrail.preview_effects/1`, keys: `schema`, `ok`, `study`, `revision`, `proposal_id`, `decision_id`, `value`, `previous`, `mutation`, `row`, `reason`, `stale_results`, `stale_slots`, `kept_slots`, `refit`, `re_eda`, `re_policy`, `recompute`, `reconfirm_required`, `supersedes_proposal`, `blocked`, `artifacts_after`, `notes`, `recorded`, `note`.

| Key | Content |
|---|---|
| `previous` | `null` for a first confirmation; otherwise `{value, user_words, basis, channel, revision, proposal_id}` of the confirmation that would be replaced |
| `mutation`, `row`, `reason` | As in an invalidation (CLI-CONTRACT §6). `first_confirmation` and `unchanged_value` have `row: null` |
| `stale_results`, `stale_slots` | What would become stale, including what lineage propagation reaches |
| `kept_slots` | The slots that are current now and would stay current |
| `refit`, `re_eda`, `re_policy`, `recompute` | The effect lists |
| `reconfirm_required` | The confirmed decisions that would need the junior's words again |
| `supersedes_proposal` | The proposal id that the confirmation would mark `superseded`, or `null` |
| `blocked` | The refusals that `decide confirm` would give **whatever the words**, in the engine's order, as `{code, reason, message, details}`: `dataset_changed`; `decision_on_hold` (`details.notes`); `proposal_stale` (as `{code: "ambiguous_confirmation", reason: "proposal_stale"}`); `invalid_value`; `precondition_missing` (`details.missing`). It is empty when nothing blocks |
| `artifacts_after` | `{report: "regenerated", notebook: "regenerated", workbench: "unchanged"}`. These are the renders that `after_commit` performs; the workbench is never written |
| `notes` | The notes of the dependency-table row |
| `recorded` | Always `false` |
| `note` | "Preview of a confirmation: nothing was recorded. The engine still checks the words when you confirm." |

**What it never predicts.** The refusals that depend on the words or on the basis are left out: `missing_user_words`, `negative_reply`, `bare_acknowledgement`, `unrelated_reply`, `delegation_needs_basis`, `not_a_delegation`, `restatement_not_default`, and `delegation_not_given_at_this_pause`. `same_request` cannot happen in a later request. `stale_revision` cannot be predicted: the confirm request carries the revision.

**Refusals.**

- `unknown_proposal`;
- `proposal_not_open` (details `status`);
- `study_missing`;
- `integrity_error`;
- `invalid_arguments` (a missing `PROPOSAL`).

**Acceptance.**

- A policy change from `threshold:0.2` to `capacity:100` in Bank gives `mutation: "policy.parameter"` or `policy.rule_type`, with empty `refit`. Both fits are in `kept_slots`, and `reconfirm_required` is `["conclusion"]` when the conclusion is confirmed.
- A split change lists both fits and every current EDA slot in `stale_slots`.
- An open hold gives `blocked[0].code == "decision_on_hold"`.
- Running it changes no byte of the study (R1).

## 4. C4: `preview proposal`

```text
hypotrail preview proposal DECISION --value VALUE --study DIR [--json]
```

This command produces the restatement and the rationale of a proposal that the **junior** starts from the companion. It is the only source of those texts: the companion never writes a restatement itself (COMPANION-ADVANCED §6.5).

- `DECISION` is `policy` (binary study) or `model_choice` (regression study). Any other decision is refused with `unsupported_capability`, with `details.capability` "a proposal draft for DECISION" and `details.decisions` the supported ones. Decisions of the other task are refused with `unknown_decision`.
- The `VALUE` of a policy is a rule (`threshold:t` or `capacity:k`), canonicalised with `records.canonical_rule`. The value of a model choice is `fit.linear` or `fit.baseline`. A value that `validate_value` refuses is `invalid_value`.
- **Proposable only from recorded evidence.**
  - A policy draft needs a current, verified `policy.evaluation` whose `params.rules` contains the canonical rule.
  - A model choice draft needs a current, verified `evaluate.regression` whose `params.models` lists the value.
  - Otherwise the draft is returned with `proposable: false` and `missing: [{requirement: "evaluated_rule" | "evaluated_model", value}]`, and with `restatement` and `rationale` set to `null`. The command still exits 0.
  - Rationale: a webview proposal must be confirmable; confirming needs that evaluation (CLI-CONTRACT §5); and the webview may not run `policy.evaluate`, because that records `validation_policy_selection` (COMPANION-ADVANCED §6.5).

Payload `hypotrail.proposal_draft/1`, keys: `schema`, `ok`, `study`, `revision`, `decision_id`, `value`, `proposable`, `missing`, `restatement`, `rationale`, `evidence`, `supersedes_proposal`, `recorded`, `note`.

| Key | Content |
|---|---|
| `restatement`, `rationale` | Generated from `content/drafts.yaml` with `cite` templates resolved to plain text at their displayed precision. The texts pass `decide propose`'s `literal_number_in_text` check by construction. A test proposes every draft of the walkthroughs on a temporary study and expects success. They never contain "recommended default", so a delegation can never confirm them (`restatement_not_default`). They contain no causal or forecast wording, and `check --text` reports them clean |
| `evidence` | `{result_id, activity, figures: [{path, value, shown}]}`: the result and the figures that the texts cite |
| `supersedes_proposal` | The open proposal of the same decision that a propose would supersede, or `null` |
| `recorded` | Always `false` |
| `note` | "Draft only: nothing was recorded. Proposing creates a proposal, not a decision." |

Draft templates (`content/drafts.yaml`; the wording is final, and numbers appear only as templates):

- **policy, `capacity:k`.**
  - Restatement: "Adopt the rule capacity:{k}: act on the {k} highest-scored rows. On the {{n}} validation rows the logistic model's selection had precision {{precision}} against {{baseline_precision}} for the baseline, and recall {{recall}}. These validation rows were used to choose the rule, so these figures are optimistic."
  - Rationale: "Chosen by the junior in the companion's What if? view, among rules already evaluated (result {{rid8}})."
- **policy, `threshold:t`.** The same, with "act on every row whose score is at least {t}" and the selected count.
- **model_choice, `fit.linear`.**
  - Restatement: "Adopt the linear model. On the {{n}} validation rows its mean absolute error is {{mae}} {{unit}} against {{baseline_mae}} for the training mean (paired difference {{delta}}, interval {{low}} to {{high}}). These rows were used to choose, so the figures are optimistic."
  - Rationale: "Chosen by the junior in the companion's What if? view (result {{rid8}})."
- **model_choice, `fit.baseline`.** "Keep the training mean as the model. ..." with the same figures.

**Refusals.**

- `unknown_decision`;
- `unsupported_capability`;
- `invalid_value`;
- `invalid_arguments` (a missing `--value`);
- `study_missing`;
- `integrity_error`.

**Acceptance.**

- A Bank draft for `capacity:100` with a current evaluation of it gives `proposable: true`, and the texts propose successfully.
- `capacity:150`, which has not been evaluated, gives `proposable: false`.
- An Auto MPG draft for `fit.linear` cites MAE 6.31 with its result id.
- A binary draft never appears in a regression study, and the reverse.

## 5. C5: `evidence`

```text
hypotrail evidence --study DIR [--result RID] [--limit N] [--json]
```

This command reads everything the EDA, Evidence, and What if? tabs show, in one call. Payload `hypotrail.evidence/1`, keys: `schema`, `ok`, `study`, `revision`, `task`, `results`, `truncated`, `lineage`, `exposure`, `impacts`, `eda_catalog`, `sources`, `detail`.

**`results`.** It lists the registry entries, newest last, at most `--limit` of them (default 200, at least 1, otherwise `invalid_arguments`). The entries promoted to a slot now always come first, whatever the limit. `truncated` is `true` when older entries were dropped. Each item is:

```text
{result_id, activity, slot, promoted, current, stale_reason, integrity, partition, n_rows,
 params, upstream, downstream, created, started_revision, execution_id, exposure_id,
 values, headline}
```

| Key | Content |
|---|---|
| `slot` | The slot this result occupies now, or the slot it was promoted to before it was replaced, or `null` (`late_not_promoted`) |
| `promoted` | True when `state.current[slot]` is this id |
| `current`, `stale_reason`, `integrity` | The derived currency of CLI-CONTRACT §4 (H2) |
| `upstream` | `{role: result_id}` from `inputs.results`, including the history role `previous_split`, marked `{role: "previous_split", history: true}` |
| `downstream` | The ids of registry entries that name this one upstream (history roles excluded) |
| `values` | The registry values **only when `current` is true and `integrity` is `ok`**; otherwise `null`. A client never shows a figure of a non-current result. The "Stale" filter lists such a result with its `headline` set to `null` and the label "Not cited" |
| `headline` | `null` or `{segments}`: one short line from `content/evidence.yaml` (for example "AUC {{roc_auc}} on {{n}} validation rows"), resolved for current, verified results only |

A **segment** (also used by C6) is `{text}`, or `{text, result_id, path, value, format}` for a cited number.

**`lineage`.** `{nodes, edges}`:

- `nodes` are `{id, kind, label, status}`:
  - `kind` ∈ `source` (`case`, `dataset`), `decision` (each confirmed decision), `result` (each listed result), `artifact` (`report`, `notebook`);
  - `status` ∈ `ok`, `changed`, `current`, `stale`, `confirmed`, `reconfirm_required`, `not_rendered`, `failed`.
- `edges` are `{from, to, role}`:
  - source → `split` and every activity that reads rows;
  - decision → result, when the decision value is in the result's `inputs`;
  - result → result, from `upstream`;
  - result → artifact, from the manifest's `consumed`.

**`exposure`.** `{summary, records, ledger, prior_exposure}`:

- `summary` is `read.Study.exposure_summary()`, unchanged.
- `records` lists every exposure record without its row-key blob: `{exposure_id, revision, time, activity, result_id, execution_id, purpose, partition, n_rows, columns}`.
- `ledger` holds one row per (purpose, partition) present: `{purpose, partition, rows, records, activities, first_revision, last_revision}`. `rows` counts distinct rows. The order is that of `records.EXPOSURE_PURPOSES`, then the partition order.
- `prior_exposure` is the state's `prior_exposure`, verbatim.

**`impacts`.** It answers this question: if a decision changed, what would go stale? There is one item per row of the study's dependency table whose mutation can change a confirmed decision. Rows 1 to 6 apply to binary studies, rows 1 to 4 and 13 to regression studies; rows 7, 8, 11, 12, and `*` are left out. Each item is:

```text
{decision_id, mutation, row, change, stale_slots, kept_slots, refit, reconfirm, notes}
```

- `change` is an English description from `content/evidence.yaml` ("a change that alters the set of usable features").
- The lists are computed by `dependencies.effects_for_mutation(state, mutation, store)`, a new pure helper. It builds the effects of a table row without old and new values, and applies them with lineage propagation to a deep copy.

**`eda_catalog`.** `{activities}`. One item per EDA activity of the task:

- binary: `eda.target_rate`, `eda.special_values`, `eda.rate_by`, `eda.distribution`;
- regression: `eda.target_summary`, `eda.special_values`, `eda.mean_by`, `eda.distribution`.

Each item is `{activity, per_column, columns, runnable, missing}`:

- `columns` lists `{name, role, type, slot, result_id}`, with the slot and result id of the current result for that column or `null`. It holds the columns the activity accepts, as `plan` would accept them: `eda.rate_by`, features; `eda.mean_by`, features and the time column; `eda.distribution`, features, the time column, and the target.
- `runnable` and `missing` come from `preconditions.missing_for_activity`.

This list is the **only** source of the columns the companion may request.

**`sources`.** `{case: {path, sha256, matches}, dataset: {path, sha256, matches}}`.

**`detail`.** It is `null` without `--result`. With `--result RID`, it is:

```text
{result_id, values, params, inputs, code: {fingerprint, modules: {module: {sha256, matches}}},
 environment, blobs, exposure, consumers, report_anchor, notebook_hint}
```

- `values` follows the same rule as above.
- `blobs` lists blob names only.
- `exposure` is the exposure record of `exposure_id`, or `null`.
- `consumers` lists the artefact names whose manifest lists this id in `consumed`.
- `report_anchor` is `"r-<result_id>"` when the current report cites the id (C10), else `null`.
- `notebook_hint` is `{path: "notebooks/study_generated.py", search: <first 8 characters of the id>}`, or `null`.

An unknown id is refused with `unknown_result`.

**Refusals.**

- `study_missing`;
- `integrity_error`, for the state; a single registry entry that fails its check is listed with `integrity: "integrity_error"` and `values: null`, and does not fail the command;
- `unknown_result`;
- `invalid_arguments`.

**Acceptance.**

- On the Bank walkthrough, `exposure.ledger` holds the five rows of the mockup (structural inspection on all rows; EDA, fitting, model evaluation, and rule selection), and every count equals `exposure.summary`.
- The `impacts` item for `feature_availability.feature_set` lists `fit.logistic` and `policy.evaluation` in `stale_slots`, and `fit.baseline` in `kept_slots`.
- After a threshold-to-capacity change, the replaced `policy.evaluation` is listed with `current: false` and `values: null`.

## 6. C6: `explain`

```text
hypotrail explain --study DIR [--term ID] [--json]
```

This command is the learning layer's only source of text. Payload `hypotrail.explain/1`, keys: `schema`, `ok`, `study`, `revision`, `task`, `terms`, `steps`, `predictions`.

**`terms`.** It lists the glossary entries of the task (the `regression_terms` overlay and the `binary_only` filter of `texts.py`), in file order. With `--term ID`, only that term is returned; an unknown id is `invalid_arguments`, with `details.terms`. Each item is `{id, term, definition, example, example_status, steps}`:

- `example` is `null` or `{segments}`: the contextual example of the new optional `cited_example` field of `glossary.yaml`, a template that cites study results (for example, for `base_rate`: "In this study's training rows the positive outcome occurs in {{slot:eda.target_rate:rate|pct1}} of rows."). The existing `example` field of `glossary.yaml` (post-v0.1 fix D11) is the agent's placeholder text and stays unchanged; `explain` never reads it (decision CA.2).
- `example_status` is `shown` when every cited result is current and verified, `needs_results` when a cited slot is missing or not current (`example: null`), and `none` when the term has no example.
- `steps` lists the step ids whose `concept` is this term.

**`steps`.** A map from step id to `{concept, context, method, interpretation, consequence, text_status}`, from `steps.yaml` (task-aware):

- each text is `{segments}`;
- when a template cites a result that is not current, that text is `null` and `text_status` is `needs_results`.

**`predictions`.** It lists the "predict before you look" questions of the new `content/learn.yaml`, for the task: `{id, step, question, choices, reveal, available}`.

- `choices` is a list of `{id, label}` with 2 to 4 items, one of which is always `not_sure`.
- `reveal` is `null` or `{segments}`: the observed answer, cited from current results.
- `available` is `true` when `reveal` is not `null`.

The engine never stores, receives, or grades an answer. Initial questions:

- binary, `train_eda`: "Is the positive outcome common or rare in the training rows?" The reveal cites `eda.target_rate:rate`.
- binary, `policy`: "Will the logistic model's selection beat the baseline's precision at the evaluated rule?" The reveal cites `deltas.precision`.
- regression, `models`: "Fitted on earlier years only, will the linear model predict later cars too low or too high?" The reveal cites the mean residual of `evaluate.regression` and its sign.
- regression, `model_choice`: "Will the linear model's validation error be below the training mean's?" The reveal cites the MAE of both models and the difference interval.

The question texts hold no digit. A test asserts that `learn.yaml`, `glossary.yaml`, and `drafts.yaml` contain no digit outside `{{...}}` templates and rule identifiers, as for every content file.

**Refusals.** `study_missing`, `integrity_error`, and `invalid_arguments`.

**Acceptance.**

- In a regression study no term of `binary_only` appears.
- Before `eda.target_rate` exists, the `base_rate` example is `needs_results`; after it, the example is `shown` and cites its result id.
- Every number in every segment is a cited segment, and `check --text` on the joined texts is clean.

## 7. C7: `export handoff`

```text
hypotrail export handoff --study DIR [--out DIR] [--json]
```

This command writes a reviewer's pack. It **never changes the study**:

- no state, revision, registry entry, exposure record, artefact, manifest, event, or lock;
- it does not render;
- it reads the view the way `status` does.

It writes files only under `--out`.

- **Default `--out`.** `<study>/handoff/revision-<n>/`, where `<n>` is the current revision, created with parents.
- **Rules on `--out`.** It must not be inside `<study>/.hypotrail/`, `reports/`, or `notebooks/`; otherwise the command fails with `invalid_arguments`, `details.field` `out`. It must not exist, or must be an empty directory; otherwise the command fails with `export_target_exists`, a new code (`details.path`). A file is never overwritten.
- **Read-only processes.** It is refused under `HYPOTRAIL_READ_ONLY=1` (`read_only`), because a read-only process writes no file.
- **Determinism.** It reads no clock. Its outputs are byte-identical for one study content and one `--out`.

Files written:

| File | Content |
|---|---|
| `handoff.md` | A human summary in English. Its sections are:<ul><li>the goal (the recap's `Goal`);</li><li>the decisions, each with its value, the junior's words, its basis and scope, its channel, and "words, not an authenticated signature";</li><li>the cited results, each number with `(result <first 8 characters>)`;</li><li>the exposure ledger;</li><li>the complete "not yet defensible" list;</li><li>the open items (proposals, holds, interrupted or unknown-outcome executions, stale deliverables);</li><li>how to reproduce: the exact CLI commands with `<study>` and the environment packages;</li><li>a closing statement that the pack does not authorise production use.</li></ul>Every number comes from a current, verified result or is a recorded literal. `hypotrail check --text handoff.md` must report it clean |
| `handoff.json` | `hypotrail.handoff/1`, keys: `schema`, `study`, `revision`, `task`, `case`, `dataset`, `goal`, `decisions`, `results_cited`, `exposure`, `not_yet_defensible`, `open_items`, `deliverables`, `reproduce`, `environment`. `results_cited` holds `{result_id, activity, path, value, shown}` |
| `study.html` | A byte copy of `reports/study.html`, **only** when the report is current (effective status `ok`); otherwise it is omitted, and `handoff.md` says so |
| `SHA256SUMS` | `<sha256>  <file>`, one line for each of the other files |

Payload `hypotrail.export/1`, keys: `schema`, `ok`, `study`, `revision`, `kind` (`handoff`), `out`, `files`, `included_report`, `warnings`.

- `files` is a list of `{path, sha256, bytes}`.
- `warnings` lists the reasons the pack is incomplete: `report_not_current`, `open_proposals`, `open_holds`, `interrupted_executions`, `sources_changed`, `unconfirmed_decisions`.

Exit code `0`, or `3` when the report is not current. The pack is still written.

**Refusals.**

- `read_only`;
- `invalid_arguments`;
- `export_target_exists`;
- `study_missing`;
- `integrity_error`;
- `untraceable_number`: a number cannot be traced, and nothing is written (the export builds every file in memory first).

**Acceptance.**

- The study tree outside `--out` is byte-identical before and after.
- `check --text handoff.md` is clean.
- Running the command twice into two new folders gives identical files.
- A stale report is not copied, and the exit code is 3.

## 8. C8: activity `eda.distribution:<column>`

```text
hypotrail run eda.distribution --column C --request-id ID --expected-revision REV --study DIR
```

- **Slot.** It is a per-column activity, like `eda.rate_by`. Its slot is `eda.distribution:<column>`. `activities.PER_COLUMN` and `state.PER_COLUMN_SLOT_PREFIXES` gain `eda.distribution:`. The registry entry keeps `activity: "eda.distribution"` and `params.column`.
- **Tasks and plan.** It is an activity of both tasks (`TASK_ACTIVITIES`). Its slots are optional: they never block a step, and they are shown with `train_eda`.
- **Preconditions.** Those of the other EDA activities: a current split.
- **Accepted columns.** A feature, the declared time column, or the target. Any other column is refused with `invalid_arguments`, with `details.columns`.
- **Rows read.** **Training rows only.** There is no partition option, and it is a test that the partition recorded in the exposure and in the result is `train`.
- **Exposure.** It is recorded with purpose `train_eda`, partition `train`, and `columns: [C]`. It reads only `C`, even when `C` is not the target: a distribution of a feature reads no outcome.
- **Code fingerprint.** `(mlkit.study.activities, mlkit.study.eda)`.
- **Dependency table.** Row 9 (`eda_added`) and the split row (`re_eda: '*'`) cover it. `dependencies._kind` already classifies `eda.*` as `re_eda`.

`values`:

```text
partition ("train"), column, role, type, kind ("numeric" | "discrete" | "categorical"),
n_rows, n_missing, special_values: [{value, meaning, n_rows, share}],
numeric: null | {n, min, q25, median, q75, max, mean, sd, n_bins, bin_width,
                 bins: [{low, high, n_rows, share, closed}]},
groups: null | [{value, n_rows, share, small_count}],
n_groups, max_groups, other, min_group_rows, warnings, note
```

**Numeric columns.** A column of type `number` or `integer` with more than `eda.MAX_DISTINCT_BEFORE_BINNING` (12) distinct ordinary values is `numeric`. The engine:

- excludes the declared special values and the missing cells from the bins, and counts them in `special_values` and `n_missing`;
- builds `eda.DISTRIBUTION_BINS` (10) fixed-width bins from the minimum to the maximum of the ordinary values;
- closes each bin on the left (`closed: "left"`), except the last, which is closed on both sides (`"both"`);
- fills `numeric`, with the quantiles computed by the same method as `eda.target_summary`.

**Discrete columns.** A numeric column with at most 12 distinct ordinary values is `discrete`. Its groups are in value order.

**Categorical columns.** These are `categorical`. Their groups are in descending row count, ties in value order.

**Groups (discrete and categorical).**

- Each group has `small_count: true` when `n_rows < eda.MIN_GROUP_ROWS` (30).
- High cardinality follows the G.12 rule of `eda.rate_by`: `max_groups` (20, or `--max-groups N`) largest groups, plus `(other values)` in `other: {n_values, n_rows, share}`. That triggers `high_cardinality_grouping` in `not_yet_defensible`, without other changes.

**`note`.** "Counts of training rows only. A distribution describes this sample; it is not a rate of the outcome and says nothing about causes."

**Deliverables.** `content/activities.yaml` and `regression_activities` gain a display specification. The HTML report shows it with the other EDA results of `train_eda`: a table of bins or groups, with every number cited. The generated notebook shows it too. `check` traces its numbers.

**Acceptance.**

- On Bank, `eda.distribution --column age` gives `kind: numeric`, 10 bins whose `n_rows` add up to `n_rows - n_missing - Σ special n_rows`, and an exposure record of the training rows with `columns: ["age"]`.
- `--column pdays` counts `-1` under `special_values`.
- `--column job` gives `categorical`.
- On Auto MPG, `--column mpg` is accepted (the target), and `--column model_year` (the time column) gives `discrete`.
- A split change makes every `eda.distribution:*` result stale.
- `run` with a validation option is impossible: no such argument exists.

## 9. C9: the origin of a proposal

```text
hypotrail decide propose DECISION ... [--channel chat|cli|webview] ...
```

- **Default.** `--channel` defaults to `chat`.
- **Action parameters.** `PROPOSE_PARAMS` accepts the parameter `channel` as optional: a request without it is still valid, and `cli.py` passes `channel` only when it is not `chat`. This keeps the identity of every earlier request, so replaying an old request id stays a replay and does not become an `idempotency_conflict`. A value outside `state.CHANNELS` is `invalid_value`, with `details.field` `channel`.
- **Stored origin.** The proposal stores `origin: {channel}` (`state.PROPOSAL_OPTIONAL_KEYS` gains `origin`).
- **Where it shows.** `decisions` (C2) lists `origin` for every proposal, and `status --summary --digest` adds it to each `open_proposals` item (§1); it is `null` for older proposals. `status --json` and `status --summary` without `--digest` are unchanged (decision CA.4). The HTML report shows "Proposed from the companion" for `channel: webview`, reading the proposal's stored `origin`.
- **Rules unchanged.** The channel changes no rule. A webview proposal is checked like any other: numbers, wording, values. It is confirmed only by a later request with acceptable words. Nothing records the junior as the author of the restatement: the restatement of a webview proposal is the engine's draft (C4).

**Acceptance.**

- A propose with `--channel webview` stores the origin, and `decisions` (C2) lists it.
- Replaying a request recorded before C9 is a replay.
- A session log line records `--channel` (it is already whitelisted).

## 10. C10: report anchors and check locations

- **Report anchors.** Each row of the report's annex (`section#annex`) that lists a cited result gets `id="r-<result_id>"`. These are anchors only: no link to VS Code and no control (§11). `test_html_offline.py` asserts that every cited result id has exactly one anchor, and that the document has no `vscode:` or `command:` URI.
- **Check locations.** Each `check` finding gains an optional `location`: `{path, anchor, line}`.
  - `path` is study-relative (`reports/study.html`, `notebooks/study_generated.py`, or a workspace file).
  - `anchor` is the nearest enclosing `id` in the HTML, or `null`.
  - `line` is the 1-based line in a text file, or `null`.

  `where` is unchanged. The schema stays `hypotrail.check/1`, because the change is additive.

## 11. Deep links (decision)

**Scheme.** The extension registers a VS Code URI handler:

```text
vscode://hypotrail-local.hypotrail-companion/result/<result_id>[?study=<absolute study path>]
vscode://hypotrail-local.hypotrail-companion/decision/<decision_id>[?study=...]
vscode://hypotrail-local.hypotrail-companion/proposal/<proposal_id>[?study=...]
```

- The authority is `<publisher>.<name>` from `package.json`.
- `result_id` is 64 lowercase hexadecimal characters.
- `decision_id` belongs to `state.ALL_DECISION_IDS`.
- `proposal_id` matches `p_<n>`.
- Anything else is ignored, with a notification ("This Hypotrail link is not valid.").
- The handler opens the panel on the matching tab: Evidence with the result selected, or Decisions with the card focused. It does this under the same flag, trust, and stage checks as the command (COMPANION-ADVANCED §3).

**Who emits these links.**

- The study agent may print them in the chat (a later instruction-template change, not part of this contract).
- The companion uses them internally for its own navigation.

**The static HTML report does not contain them.** The rule "no decision controls in static HTML" (ADR 0002, item 4) is not, strictly, broken by a plain link: a link decides nothing. Three reasons still keep them out:

1. The report is the standalone, offline, shareable deliverable. In a reviewer's browser without VS Code, or in the handoff pack, a `vscode://` link is dead, or prompts to open a program the reader does not have.
2. A link that drives the panel makes the report look like a control surface. That blurs the statement printed on the report: "There are no decision controls on this page."
3. `test_html_offline.py` and `check_layout.py` can assert a simple rule: no `vscode:` or `command:` URI in any rendered deliverable.

**Reaching the companion from a number in the report.** Each number carries its `result_id` (`<data data-result-id>`, and the hover title), and its annex row has the anchor `r-<result_id>` (C10). The companion's command "Hypotrail: go to a result..." accepts a pasted id, or its first 8 or more characters, and resolves it through `evidence`. From the companion to the report, "Show in report" opens the report at `#r-<result_id>`.

There is no opt-in render setting that adds the links, and no `vscode:` link in any deliverable, not even opt-in (ADR 0004 open question 1, answered no; decision CA.1).

## 12. New error code

| Code | Source | Meaning |
|---|---|---|
| `export_target_exists` | `export handoff` | `--out` exists and is not an empty directory (`details.path`). Nothing was written |

Every other refusal in this document reuses a code of CLI-CONTRACT §7.

## 13. Reserved stubs (WP-0)

Before the engine work packages start, WP-0 registers the new commands with modules that refuse. **The refusal of a reserved, not yet implemented command** is:

```json
{"code": "unsupported_capability",
 "message": "<command> is reserved for the advanced companion and is not implemented in this version. Nothing was read or written.",
 "details": {"command": "<command>", "reason": "not_implemented"}}
```

with exit code 2. It reuses the existing code `unsupported_capability` (CLI-CONTRACT §7), so every client already handles it; `details.reason: "not_implemented"` (`errors.NOT_IMPLEMENTED`, built by `errors.not_implemented(command)`) tells a reserved command from a capability the engine refuses by design. A stub reads and writes nothing, and the session log records it as a refusal. The `details.command` values are:

| Invocation | `details.command` | Replaced by |
|---|---|---|
| `status --summary --digest` | `status --summary --digest` | WP-E1 |
| `decisions` | `decisions` | WP-E1 |
| `preview effects PROPOSAL` | `preview effects` | WP-E1 |
| `decide propose ... --channel V` with `V` not `chat` | `decide propose --channel` | WP-E1 |
| `evidence` | `evidence` | WP-E2 |
| `explain` | `explain` | WP-E2 |
| `export handoff` | `export handoff` | WP-E2 |
| `preview proposal DECISION --value V` | `preview proposal` | WP-E3 |

What WP-0 registers:

- `cli.EXTENSIONS` gains `decisions` → `mlkit.study.cmd_decisions`, `evidence` → `mlkit.study.cmd_evidence`, `explain` → `mlkit.study.cmd_explain`, and `export` → `mlkit.study.cmd_export`. Each module parses the arguments of this document (`configure`) and exposes the frozen function its WP implements: `cmd_decisions.decisions(study_dir) -> dict`, `cmd_evidence.evidence(study_dir, *, result_id=None, limit=200) -> dict`, `cmd_explain.explain(study_dir, *, term=None) -> dict`, `cmd_export.export_handoff(study_dir, *, out=None) -> (dict, exit_code)`.
- `cmd_preview` takes `kind` ∈ `policy`, `effects`, `proposal`, an optional positional `TARGET`, `--rule` (repeatable), `--intervals`, and `--value`. It checks the per-kind rules (`--rule` is required for `policy` only; `TARGET` for `effects` and `proposal` only; `--value` for `proposal` only; anything else is `invalid_arguments`), then calls `preview_effects.preview_effects(study_dir, proposal_id) -> dict` or `preview_proposal.preview_proposal(study_dir, decision_id, value) -> dict`.
- `status` parses `--digest`: without `--summary` it is `invalid_arguments` (final behaviour); with it, the stub refusal above.
- `decide propose` parses `--channel` (no choices: WP-E1 validates against `state.CHANNELS` with `invalid_value`, `details.field: "channel"`). `chat`, or no option, proposes exactly as before and passes no `channel` parameter.
- Constants: `state.PER_COLUMN_SLOT_PREFIXES` gains `eda.distribution:`, `state.PROPOSAL_OPTIONAL_KEYS` gains `origin`, `texts.CONTENT_FILES` gains `digest`, `drafts`, `evidence`, `learn` (stub files with their `schema` header only), and `sessionlog` gains `--digest`, `--limit`, `--result`, `--term`, the positional identifier of `preview effects` and `preview proposal`, and a `--value` of `preview proposal` that is a rule or a model slot (R5).

Each stub module carries `WP0_STUB = True`; its engine work package removes it with the stub. The UI work can then call real argv against a real CLI from the first day.
