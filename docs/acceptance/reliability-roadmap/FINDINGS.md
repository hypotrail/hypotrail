# Review-remediation evidence ledger

Baseline inspected: `86729175ed4b1b42163d327b9e100c9ce2cdf14a`, 21 October 2026.
Source: the consolidated attached review of a41c851 and the committed closing
journey/UI reviews. J0 introduced scope and assurance; J1--J3 implement the opt-in
evaluation, validity and objective corrections recorded below.
No historical holdout probe was rerun. “Code inspection” is not a reproduced result.

| ID | Finding and current code | Current behavior/evidence | Status | Owner | Verification and residual limit |
|---|---|---|---|---|---|
| B1 | Hotel booking snapshot/arrival split; case builder, partition.py | Review plans now enforce prediction/outcome clocks; Hotel remains a leakage exercise because its snapshot does not establish booking-time availability | fixed_with_case_limit | J0/J1/J2 | J1 explicit-clock tests; no booking-performance claim |
| B2 | Local CSV, commands/confirmation, no shared study ledger | Protocol reservation, agent-reported consent, no enforced cross-study inheritance | accepted_limit | J0/J4/J7 | J0-A06/A07: accessible synthetic source and unauthenticated choice channel; no claim of hostile-agent protection |
| B3 | explicit evaluation plans consumed by activities/fit/families | Review outer and inner memberships prohibit future/group leakage and shuffled fallback; legacy path remains historical | fixed_review_v1 | J1 | J1-A01--A12; no legacy reinterpretation |
| B4 | preconditions.final_test_missing | Review opening requires the matching current development diagnostic; final diagnostic follows evaluation | fixed_review_v1 | J2 | J2-A04--A06/A10; legacy unchanged |
| I1 | commands and validity availability validation | Documented scenario restriction is hard on proposal, confirmation and run paths | fixed_review_v1 | J2 | J2-A01--A03 |
| I2 | objective, families and trials | Review tuning/selection uses declared precision/recall or MAE objective | fixed_review_v1 | J3 | J3-A01/A02 exact oracle |
| I3 | objective.assess, criterion/governance | Point and qualified lower-bound decisions have explicit truth-table fields | fixed_review_v1 | J3 | J3-A05/A09 |
| I4 | objective bootstrap and uncertainty descriptor | Independent fixed holdout supported conservatively; temporal/group/batch-preserving inference explicit unavailable | accepted_limit | J3 | J3-A08/A09; no broad coverage claim |
| I5 | cmd_preview.preview_policy | Read-only previews remain unrecorded | confirmed_open | J4 | Code inspection; recorded inspection activity is still planned |
| I6 | trials.select | Pooled-count review selection suppresses incoherent one-SE/optimism; legacy heuristic remains labelled | fixed_review_v1 | J3/J5 | J3 selection and notebook tests; no equivalence claim |
| I7 | trials shortlist and proposal paths | Hard interpretability and planned/data-informed provenance enforced; diagnostics still inform soft recommendations | fixed_review_v1 | J2 | J2-A07--A09 |
| I8 | code_compat.equivalent, read.Study.code_changed | Old-digest predicate still lacks destination digest | confirmed_open | J4 | Code inspection; no numerical equivalence exceptions added by J0 |
| I9 | cmd_check.wording, numeric tracing | Unrestricted semantic claim checking is not established | not_retested | J5 | Review's French causal counterexample retained; no new semantic-certification claim |
| I10 | regression baseline | Review MAE uses the training-fold median; legacy mean results retain their label | fixed_review_v1 | J3 | J3-A03/A12 |
| M1 | eda permutation envelope | Review suppresses unrestricted shuffle interpretation under declared dependence; general alternatives remain limited | partially_fixed | J3/J5 | Explicit unavailable reason; no new exchangeability experiment |
| M2 | entity and duplicate grouping | Declared entity and exact-duplicate links close transitively in review plans; undeclared real-world identity remains unknowable | fixed_with_case_limit | J1/J4 | J1-A05; preview history remains J4 |
| M3 | code_cells, generated notebook | Shared computation does not independently prove validity | accepted_limit | J6/J7 | J0 tests include independent metadata oracles only; notebook execution redesign pending |
| M4 | policy capacity conversion and glossary AP wording | Review capacity is literal per declared batch and pooled; unrelated glossary wording remains J5 | partially_fixed | J3/J5 | J3-A06/A07 |

R39 (quoted decision before adoption) and R40 (Copilot choice picker/text fallback)
are retained. Their generated-file checks are technical evidence, not a real Copilot
session. Per-milestone test results and environment limitations belong in `J0.md` and
later acceptance records, not in invented retrospective pass rates.
