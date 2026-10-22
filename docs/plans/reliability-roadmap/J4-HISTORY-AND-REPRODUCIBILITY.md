# J4 — Recorded exploration and bounded reproducibility

Depends on J0–J3. J4.1 may be implemented immediately after J0.
Review coverage: I5, I8, M2; explicit limitations from B2.

## Outcome

The engine can explain which instrumented consultations informed a decision and
whether an old result is reproducible with a specific code revision. It does not
claim to observe arbitrary file reads or all studies on the same machine.

## Current implementation anchors

`code_compat.py`, `read.Study.code_changed`, `currency.py`, `registry.py`,
`records.py`, `exposure.py`, `store.py`, `executions.py`, `cmd_run.py`,
`cmd_preview.py`, `sessionlog.py`, `trials.used_specs`, `cmd_export.py`.
The existing `preview policy` is explicitly read-only; the optional session log is
not the authoritative scientific ledger. Preserve that architectural distinction.

## J4.1 — Exact code-compatibility attestations

Replace the “old digest is in an allowlist” predicate with an explicit record:

```json
{
  "module": "mlkit.study.fit",
  "from_sha256": "<old bytes digest>",
  "to_sha256": "<verified destination bytes digest>",
  "activities": ["fit.logistic"],
  "reason": "Display-only change outside numerical path",
  "evidence": ["framework/tests/study/test_example_equivalence.py::test_named_case"]
}
```

Placeholder digests in this spec must never become real attestations. Generate them
from exact checked source bytes during implementation. The predicate receives
module, old digest, **actual current digest** and activity. All must match a record.
Equal old/current digest needs no attestation. Missing activity does not mean “all.”
Do not infer transitivity A→B→C, grant wildcard destinations or exempt an entire
module merely because one activity was unchanged. If transitive equivalence is ever
needed, require a separately tested explicit A→C attestation.

Do not automatically copy the existing allowlist into records with today's digest:
inspect the specific change and verify the activities first. Numerical changes in
J1/J3 require invalidation, not a new equivalence declaration. Keep compatibility
metadata outside the attested numerical module to avoid self-referential digests.

Expose three derived statuses separately: record integrity, validity for the current
study configuration, reproducibility under current code. The original registered
record is immutable. A historical final result may be displayed with its original
code/parameters and explicit limits even when it is not current-code reproducible;
that permission must not promote it into a current decision or reopen the final test.

## J4.2 — Add an explicitly recorded exploration activity

Add `run policy.inspect` to the engine catalog, using the existing `run` revision,
request-ID, lease and exposure protocol. Canonical stored activity/slot name:
`policy.inspection`. Accept repeated `--rule` arguments and optional `--intervals`
matching current preview calculations. All inputs are persisted development
predictions; this activity never trains or reads unopened final rows.

The guided agent MUST use this activity when a policy comparison will inform a
choice. It reuses the pure evaluation functions of `preview policy`, but records:

- canonical rules requested, model result IDs and prediction blob hashes;
- dataset identity, scored-row digest, protocol/window identity and partition;
- metric/objective, requested uncertainty mode and resulting values;
- request/execution/result IDs, starting revision and timestamp;
- purpose `policy_exploration`, and whether this occurred after final opening.

One request with five rules records one inspection event containing five distinct
rule/configuration queries. Expose both event count and distinct-query count; neither
is the number of independently validated hypotheses. Keep the three-variant budget
separate and unchanged. A query is identified by dataset, population, predictions,
objective and canonical rule, not by its displayed text.

Reuse the existing activity planning/reservation path. Record potential exposure
before computing so interruption cannot make a possibly observed result look unseen.
Store event status `reserved|completed|failed|outcome_unknown`; a reservation is
potential exposure, not proof that the user saw a result. Identical request-ID retries
must not duplicate the event; conflicting payloads refuse. A fresh request that
reuses cached calculations still records a consultation event while reusing the
registered calculation. Do not refit just to increment a counter.

The current `policy.inspection` slot may point at the latest inspection; older
immutable entries stay in history. Its replacement must not stale candidate fits
or the adopted policy. Its results are exploratory and not a replacement for the
adoption evaluation required by J2. If inputs change while computing, retain history
without promoting a stale result. Aggregate history from authoritative entries, not
from optional terminal/session logs.

## J4.3 — Keep read-only operations read-only

`preview policy`, `preview effects`, `preview proposal`, `status`, `data`, `evidence`
and report reading MUST NOT silently acquire mutation behavior. Keep byte-level
read-only tests. `preview policy` stays `recorded: false`; add a localized warning
that the inspection is not in the scientific exploration ledger and cannot be
represented as an unsearched selection.

The panel's What if view continues using the read-only preview. It may copy a
ready question asking the chat to record a comparison; it must not call
`policy.inspect`, propose/adopt anything, or add a write handler. No ADR 0004
whitelist expansion is part of this milestone.

For the workbench, unrestricted edits remain personal exploration. Do not instrument
every Python read or secretly mutate state when a slider moves. Provide a clearly
labelled snippet/question for the user to request a recorded comparison in chat.
The supported notebook helper's documentation must disclose that free exploration
is not exhaustively captured. This scoped solution intentionally does not claim to
solve every unrecorded-preview issue in the review.

`assurance` gains derived `exploration_coverage: instrumented_operations_only` and
`unrecorded_surfaces: [preview, workbench, external_files]`. Absence of entries on
these surfaces never means absence of exposure.

## J4.4 — Label previews and external/prior history correctly

The data card's five target-labelled examples are target exposure, not purely
structural inspection. Reserve/record their fixed row keys at study initialization
when the display sample is selected, conservatively as `labelled_preview_available`;
the subsequent read-only `data` command need not mutate. Distinguish made available
from demonstrably viewed. Never include final rows in this sample.

Preserve case-declared prior exposure in every study and handoff. Export a compact
history summary with dataset hashes and explicit instrumented coverage. Do not add
a global database, scan sibling studies or promise detection of reinitialization.
Cross-study inheritance requires an explicit future import specification; until
then show `cross_study_history: not_enforced` and explain that a fresh directory
does not establish fresh evidence. Do not invent a link to another study.

## J4.5 — Historical presentation and current blockers

Readers derive blockers from current required result IDs and their dependencies.
They may show old stale records in history without elevating them to active blockers.
An old record's existence must not block its valid replacement. Conversely, do not
remove old records from `state.stale` to make a display pass: J6 will align surfaces
on this derived reading. History and current actionability are different views.

## Acceptance

| ID | Scenario | Expected |
|---|---|---|
| J4-A01 | Attested A→B, actual current B, matching activity | Compatibility allowed |
| J4-A02 | Same attestation, actual C / wrong activity / missing activity | Compatibility refused |
| J4-A03 | A→B and B→C records only | A→C not automatically allowed |
| J4-A04 | Final result loses current-code reproducibility | Historical record still inspectable; final remains consumed |
| J4-A05 | policy.inspect with five distinct rules | One event, five queries, result IDs and row scope present |
| J4-A06 | Repeat same request; then reuse ID with different rule | First is idempotent; second conflicts with no new event |
| J4-A07 | Fresh request uses identical cached calculation | Consultation recorded; no refit; calculation reused |
| J4-A08 | Kill after reservation; change input before promotion | Potential exposure retained; outcome unknown/stale not hidden |
| J4-A09 | Call every existing read-only preview/data command | Study state, ledgers and revision unchanged |
| J4-A10 | Inspect generated data-card sample | Five labelled development keys accounted for; no final key |
| J4-A11 | New study on same synthetic file | Prior case exposure retained; no claim that cross-study history was checked |
| J4-A12 | Panel What if/slider | No new write command; unrecorded coverage disclosed |

Tests: `test_review_j4_history.py`, existing code-change/currency, exposure-kill,
read-only CLI, session-log and panel-whitelist suites. Update CLI and exposure
contracts, the export contract and agent instructions. Do not present this milestone
as protection against a malicious unrestricted agent.
