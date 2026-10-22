# Implementation specifications: review remediation, J0–J7

Status: **J0--J3 implemented and automatically verified on 22 October 2026; owner review of
18 intentional EDA baseline changes is deferred until final handoff; J4--J7 remain proposed**.
Prepared on 21 October 2026 for sequential handoff to an implementation model.
Inspected checkout: `86729175ed4b1b42163d327b9e100c9ce2cdf14a`.
Review baseline: `a41c851e2b854780445806e7263e8665a8d10666`.

Implementation evidence is in `docs/acceptance/reliability-roadmap/J0.md` through
`J3.md`. The specifications below remain the normative trace of the design; statements
describing the package as wholly unimplemented are historical for J0--J3. Do not infer
implementation of J4--J7 from the combined profile.

## Intended outcome

A cooperative user and coding agent complete a narrowly scoped binary-classification
or regression study. The engine enforces the supported evaluation protocol, exposes
the limits of the evidence, and produces a readable report and explanatory notebook.
An independent reader can reconstruct the important choices. This is not a claim of
production readiness, causal effectiveness, proven learning, or resistance to an
agent with unrestricted filesystem access.

The source is the supplied **Revue-Hypotrail-v0.3-a41c851.html**, consolidated on
21 October 2026, especially findings B1–B4, I1–I10, M1–M4 and sections 7–10.
The source is an attached review, not a file committed in this directory. The
requirements below restate the actionable findings so implementation does not depend
on access to that attachment. Existing repository evidence includes
[the journey review](../v0.3-inputs/CLOSING-JOURNEY-REVIEW.md) and
[the UI review](../v0.3-inputs/CLOSING-UI-REVIEW.md).

These specifications are in English, the repository's maintained source language.
Junior-facing output must support English and French.

## Read and implement in this order

| Order | Specification | Completion produces |
|---|---|---|
| Always | [Common contracts](COMMON.md) | Shared semantics, compatibility rules and verification discipline |
| J0 | [Scope and guarantees](J0-SCOPE-AND-GUARANTEES.md) | Explicit contract and evidence ledger |
| J1 | [Evaluation protocols](J1-EVALUATION-PROTOCOLS.md) | Explicit train/validation memberships, including nested temporal evaluation |
| J2 | [Validity requirements](J2-VALIDITY-REQUIREMENTS.md) | Availability restrictions and diagnostics enforced at the relevant transition |
| J3 | [Objective and verdict](J3-OBJECTIVE-AND-VERDICT.md) | Consistent tuning, selection, baseline and uncertainty interpretation |
| J4 | [History and reproducibility](J4-HISTORY-AND-REPRODUCIBILITY.md) | Recorded exploration and bounded code equivalence |
| J5 | [Evidence references and guidance](J5-EVIDENCE-AND-GUIDANCE.md) | Context-bound figures and concise engine-produced pauses |
| J6 | [Consistent deliverables](J6-CONSISTENT-DELIVERABLES.md) | Coherent chat, HTML, Marimo and optional panel |
| J7 | [Acceptance and release evidence](J7-ACCEPTANCE.md) | Technical, real-tool and human evidence reported separately |

Implement one milestone at a time. Inside each milestone, follow its ordered work
packages; do not combine all changes into one patch. J4's bounded-equivalence fix
can be pulled forward after J0 if code changes would otherwise mask invalidation.
J5 may be developed after the shared contracts stabilize, but its acceptance still
depends on J1–J4. No multi-agent orchestration is required or authorized by this pack.

## Decisions made by this proposed design

1. Keep the local CLI architecture, normal chat, offline HTML and two Marimo
   notebooks. Keep the study panel default-off and inside W4–W7; add no panel write.
2. Keep Hotel as a **discovery exercise in leakage and evidence limits**; do not
   claim prediction-at-booking validity from its current snapshot. This refines its
   teaching scope without silently changing the owner's discovery-case selection.
3. Use synthetic fixtures for exact validity tests, Bank full for a bounded scoring
   walkthrough, and Auto MPG for regression. Bank's row order does not supply
   missing historical feature snapshots or outcome-availability timestamps.
4. Introduce an explicit, opt-in `review-v1` reliability profile while implementing
   this pack. Existing studies remain legacy; there is no silent migration. Do not
   change the default profile as a side effect of an intermediate milestone.
5. Preserve read-only previews. Add a recorded **engine activity** for exploration
   that informs a decision. Instrumented activity coverage is not a record of every
   filesystem/notebook read. The panel keeps read-only previews and discloses this gap.
6. Prefer bounded supported behavior and explicit unavailability over an invented
   protocol, a fabricated confidence interval or automatic fallback to shuffled CV.
7. Do not add a new mandatory confirmation for every technical parameter. Put the
   selection rule and success convention into the existing success-criterion pause.

These are proposed product/contract changes, not claims that the current code already
does them. An implementation assignment for a milestone authorizes that milestone's
changes. Repository changes to accepted decisions must amend the relevant ADR in the
same implementation work; do not silently rewrite an accepted ADR's historical text.
In particular, J2 changes ADR 0007's diagnostic-based family policy and J1/J3 change
its evaluation and selection mechanics. No amendment in this pack widens the panel.

## Traceability to the review

| Finding | Requirement owner | Required evidence |
|---|---|---|
| B1: Hotel snapshot and prediction-time mismatch | J0, J1, J2 | Restricted claims; timing and availability fixtures |
| B2: readable test, reported consent, cross-study reset | J0, J4, J7 | Honest guarantee labels and explicit coverage limits |
| B3: future training, shuffled/group-leaking inner CV | J1 | Independent membership oracles at both levels |
| B4: final opening without diagnostics | J2 | Direct CLI refusal before final-row access |
| I1: known late predictor accepted | J2 | Restriction cannot be overridden by an endorsement |
| I2: AUC used instead of business selection metric | J3 | Ranking-versus-top-share oracle |
| I3: useful minimum versus point estimate | J3 | Explicit decision convention and complete truth table |
| I4: dependent rows and conditional intervals | J3 | Supported-method metadata or unavailable uncertainty |
| I5: unrecorded policy search | J4 | Recorded activity and honest uninstrumented-read limits |
| I6: simplicity/optimism overinterpretation | J3, J5 | Heuristic labels, no equivalence claim |
| I7: non-linear-family admission policy | J2 | Hard constraints enforced; planned challenger distinguished |
| I8: unbounded code equivalence | J4 | A→B allowed, A→C refused |
| I9: correct number, incorrect claim | J5 | Population/rule/scope mismatch rejection; FR/EN wording fixtures |
| I10: mean baseline for MAE | J3 | Independent five-number oracle |
| M1: permutation envelope interpretation | J3, J5 | Exploratory label; unsupported dependent mixing suppressed |
| M2: duplicates, entities, labelled previews | J1, J4 | Separate dependency metadata and exposure accounting |
| M3: shared errors in notebook and engine | J6, J7 | Cell provenance and independent expected results |
| M4: capacity period and AP definition | J3, J5 | Batch-scoped rule; correct canonical glossary |
| Long payloads, mixed language, false stale blocks | J5, J6 | Compact response, FR/EN scenarios, current-result assertions |
| No demonstrated real-tool/human usability | J7 | Clearly classified acceptance records |

## How to hand off a milestone

Give the model repository access and the following prompt, substituting the milestone
filename. All paths are relative to the repository root.

```text
Implement only milestone J<N> in docs/plans/reliability-roadmap/J<N>-<NAME>.md.
First read AGENTS.md, docs/START-HERE.md, docs/handoff/IMPLEMENTATION.md,
docs/specs/JUNIOR-WORKFLOW.md, docs/architecture/REPOSITORY.md, CONTRIBUTING.md,
docs/plans/reliability-roadmap/README.md and COMMON.md in the same directory.

The specification is a proposed implementation contract, not a description of code
already present. Inspect git status, HEAD and the actual implementation first.
Check the acceptance evidence for prerequisite milestones. Do not implement a
downstream milestone to compensate for a missing prerequisite.

List the work packages, files to change and acceptance IDs, then implement them in
order. Use the existing engine and reliability machinery; preserve all real studies,
human confirmations, exposure history and notebook annotations. Use temporary
synthetic studies for tests. Keep the companion default-off and inside its current
write whitelist. Preserve R39 and R40. Do not spawn agents.

Do not weaken tests or whitelist changed numerical code as equivalent. If a required
contract cannot be satisfied, record the concrete conflict and stop that work package;
do not silently substitute a weaker behavior. Routine internal naming choices do not
need clarification. New public keys and behavior must match the specs and be reflected
in the CLI/case contracts, freeze tests and applicable ADR amendment.

Run the targeted acceptance tests, then the applicable repository gate before any
commit. Do not launch paid agent acceptance, install an extension, train a business
model, open a historical holdout, publish or deploy without the corresponding task
authorization. Report unavailable manual checks as not run.

Finish with changed files, acceptance IDs passed/failed/not run, commands and results,
compatibility impact, remaining limits, and the next milestone's starting state.
Do not claim the milestone complete while its required automated checks fail.
```

## Definition of delivery

The deliverable of each milestone is code, updated contracts, tests and an English
acceptance record at `docs/acceptance/reliability-roadmap/J<N>.md`. Record the tested
commit or dirty-tree diff, environment, exact commands, outcomes and skipped checks.
That record must distinguish `implemented`, `automatically_verified`,
`manually_verified` and `not_run`; these are not interchangeable.

This specification-writing task did not execute the engine gate, train models,
change study state or implement the proposed features. No duration or monetary
estimate in an earlier review is adopted as an implementation commitment.
