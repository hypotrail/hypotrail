# Shared implementation contract

Normative for J0–J7. MUST means acceptance fails if the requirement is absent.
SHOULD is a default that may be changed only with a documented, tested reason.
New names in this package are **proposed interfaces**, not existing commands.

## C1. Preservation and execution boundaries

- Reusable implementation belongs in `framework/mlkit/study/`; adapters belong in
  `use-cases/<id>/`. Never branch generic engine logic on a case name.
- Never reset, migrate in place or delete a real study to make a test pass. No
  historical holdout reads. Test data and test studies live in temporary directories.
- Preserve the existing revision, idempotency, lease, interrupted-write and delayed
  completion machinery. All new mutations MUST pass through it. Recheck prerequisites
  at reservation and promotion; stale computation may be archived, never promoted.
- Keep source prose in English and localized junior prose in EN/FR. Identifiers remain
  stable and untranslated. Preserve R39's quoted proposal before adoption and R40's
  Copilot choice picker, with a text fallback and the same decision semantics.
- Do not install a new server, database, language-model dependency or orchestration
  layer. Do not widen the panel whitelist or its default stage.
- No scientific validity claim follows from `check clean`. The display must say
  which checks passed and which claims were not evaluated.

## C2. Reliability profile and backward compatibility

J0 introduces optional `settings.reliability_profile` with values `legacy` and
`review-v1`, and `hypotrail init --reliability-profile review-v1`. Missing means
`legacy` in memory; reading MUST NOT write a default into old state. During J0–J7,
omitting the option keeps current initialization behavior. A later release decision
may change the default only after acceptance and documented compatibility review.

For `review-v1`, optional contracts added by this pack become required at the point
where they are needed. A missing field produces an actionable refusal, never an
inferred scientific assumption. Update the strict schema validators and frozen key
lists when adding a field; do not loosen unknown-key rejection globally.

| Situation | Required behavior |
|---|---|
| Old state, unmodified code/data | Loads without rewriting; legacy semantics labelled |
| Old result after numerical implementation changes | Preserved as historical evidence; never silently relabelled as new-profile evidence |
| Old opened final test | Remains consumed; no automatic reopening or refitting on final rows |
| Code compatibility not established | Reproducibility under current code unavailable; show the recorded result only as historical |
| Existing case file edited | Preserve source-change detection; create a new case revision/study where needed |
| New display-only field | Derive in the reader when possible; do not mutate scientific identities just to localize |
| New profile explicitly requested on an old study | Refuse in-place conversion; explain the supported new-study path and inherited exposure limits |

Legacy loading is not a promise that old numerical code remains executable after a
refactor. If it cannot be safely reproduced, provide read/export of verified historical
records and a clear unsupported-recomputation refusal. Do not simulate old algorithms
using new semantics under the old identity. Where current renderers reject stale
results, J4 adds a separate historical-evidence presentation path; do not make all
stale results current to recover rendering.

## C3. Canonical case analysis contract (new, J0)

Add optional top-level `analysis_contract` to `hypotrail.case/1`. Existing cases remain
loadable. New-profile analytical claims require this contract; absence permits
inspection and an explicit incomplete plan, not fitting with invented semantics.

```yaml
analysis_contract:
  schema: hypotrail.analysis/1
  scenario_id: synthetic-future-ranking-v1
  intended_use: future_prediction
  row_unit: reservation
  population: New reservations in the declared scoring batches
  prediction_statement: Predict at reservation entry
  timing:
    prediction_order: {by: prediction_tick, status: documented_fact, source: fixture specification}
    outcome_available_order: {by: outcome_tick, status: documented_fact, source: fixture specification}
    scale: ordinal
  dependencies:
    kind: temporal
    group_column: null
    group_goal: null
    status: scenario_assumption
    source: Synthetic chronological evaluation scenario
  permitted_claims: [retrospective_association, future_predictive_performance]
```

Allowed `intended_use`: `retrospective_comparison`, `future_prediction`,
`leakage_exercise`. Allowed dependency `kind`: `independent`, `grouped`, `temporal`,
`grouped_temporal`, `unknown`. For grouped modes, require a non-target group column
and `group_goal: unseen_groups`. Repeated-known-entity forecasting is explicitly not
supported in this first slice. A declaration of independence is an assumption with
provenance, not a fact inferred from the absence of a group column: add
`dependencies.status` and `dependencies.source` using the existing epistemic enums.
These two keys are required, including for independent or unknown dependence.

Timing uses numeric/integer order columns or `by: line`, with documented ascending
meaning and one shared scale. `scale` is `ordinal` for this slice. Future prediction
requires both clocks with comparable units; arbitrary file order alone does not prove
outcome availability. Retrospective/exercise contracts may use null timing fields.
Do not reconstruct Hotel booking time from arrival minus lead time and call it a
documented historical timestamp. Date parsing and calendar deployment schedules are
outside this first implementation.

`permitted_claims` is a ceiling, not an approval: available evidence can narrow it.
Allowed values are `retrospective_association`, `future_predictive_performance`,
`calibrated_probability`. Causal/intervention-effect claims are unsupported. An empty
list permits an explicitly incomplete study. Static metadata cannot establish
calibration or out-of-sample validity on its own.

J2 adds optional per-variable `availability.restriction`:
`{scenario_id, kind: unavailable_at_prediction, source}`. It is allowed only with
`availability.value: not_available` and a documented source. It is scoped to the
declared scenario, not a universal ban on that column.

Contracts are static facts/assumptions. They MUST NOT contain `confirmed` or
`confirmation`, and MUST NOT install decisions. The existing `prediction_time`
proposal quotes `prediction_statement` and its source; user confirmation remains a
separate state event. In this bounded slice an incompatible prediction statement
requires a revised case/scenario and a new study, not a silent semantic match by an LLM.
Use exact text after whitespace normalization for this binding, and explain the
restriction before asking for adoption.

## C4. Evidence eligibility, currency and interpretation

Treat these as separate dimensions in every derived view:

1. **Integrity:** registered values and blobs match their hashes.
2. **Currency:** the result matches the active inputs and required code compatibility.
3. **Scope:** development, final evaluation, historical or personal exploration.
4. **Claim eligibility:** protocol, availability and diagnostics support the requested
   kind of assertion. A current result can still be ineligible for a future claim.
5. **Uncertainty:** quantified under named assumptions, approximate/descriptive, or
   unavailable. No interval is not a zero-width interval.

J2 introduces derived `claim_eligibility` (do not add a second persistent truth store):
`{claim, eligible, requirements, limitations, evidence_refs}` per supported claim.
Requirements contain `{code, satisfied, result_id, detail}`. Stable codes are asserted
in tests; localized messages are presentation. `eligible: true` means the named
software prerequisites are satisfied, never scientific certification.

Use existing top-level error codes where possible: `invalid_value`,
`unsupported_capability`, `precondition_missing`, `integrity_error`, revision errors.
New precise refusal reasons belong under structured `details.reason` and
`details.requirements`. Never convert scientific refusal into a generic traceback.

## C5. Result identity and invalidation

New protocol memberships, selection objective, baseline policy and numerical method
MUST be represented in activity inputs/parameters and the existing code fingerprint.
The current `records.result_id` already binds output hashes and upstream inputs;
reuse it. Do not invent a second mutable result version counter.

| Change | Required numerical consequences |
|---|---|
| Prediction/label timing, groups, split memberships | Split-dependent fits, tuning, diagnostics, evaluations and conclusion invalidated |
| Included feature or preparation | Affected fits and downstream evidence invalidated |
| Selection metric/rule/aggregation | Tuned fits and selection/evaluation invalidated; fixed untuned predictions may be reused only if their inputs are unchanged |
| Success minimum or convention only | Verdict/decision eligibility recomputed; do not refit unchanged models; mark after-results choice |
| Adopted model or action rule | Rule/model-specific diagnostics and conclusion invalidated |
| Language, rounding, layout | No refit or loss of valid human decisions |
| Numerical source change without exact equivalence | Affected results not current under current code; history retained |

After final opening, changes never restore an unopened final test. Show the original
configuration and mark newer choices as post-opening. A new split does not erase
exposure. Same request ID and same payload replay the same event; same ID with a
different payload is a conflict. A stale request MUST NOT mutate any history.

## C6. Verification and acceptance record

Read `CONTRIBUTING.md` for the authoritative gate. Do not execute the gate merely
because specifications were authored; run it during implementation. Use uv and the
configured framework environment. Targeted tests are necessary but do not replace
the required pre-commit gate.

Tests MUST contain independent expected memberships/metrics, not only an assertion
that two consumers of the same helper agree. Use small planted counterexamples and
existing `flowkit` fixtures. Maintain old contract tests; intentional semantic changes
get version/profile-specific expectations, not deleted assertions.

Every J-file defines acceptance IDs. Record for each: command/test, expected result,
actual result, `pass|fail|not_run`, and evidence path. No invented pass counts. A
manual UI test, a browser simulation and a real Copilot session are distinct evidence.
New tests should go in the existing test directories with `test_review_j<N>_...`
names; these names are proposed, not files that already exist.

Required acceptance-record sections:

```text
Scope and profile
Base commit and tested changes
Requirement/acceptance ID matrix
Commands and actual results
Compatibility and invalidation
Manual/paid checks not run
Remaining limitations and next handoff
```

## C7. Architecture choices deliberately excluded

No new task families, AutoML search, cloud execution, causal estimator, global
cross-study database, protected-data service or authenticated-user interface.
No broad regex engine presented as semantic proof. No mandatory quiz at each pause.
No target inspection of a reserved historical test to demonstrate the old defect.
No calendar capacity support disguised as a rescaled fraction. No automatic
refitting when a reader opens HTML or a notebook.
