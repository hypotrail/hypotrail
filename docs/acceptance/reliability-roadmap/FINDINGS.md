# Review-remediation evidence ledger

Baseline inspected: `86729175ed4b1b42163d327b9e100c9ce2cdf14a`, 21 October 2026.
Source: the consolidated attached review of a41c851 and the committed closing
journey/UI reviews. J0 changes only scope, contracts, assurance and the opt-in guard.
No historical holdout probe was rerun. “Code inspection” is not a reproduced result.

| ID | Finding and current code | Current behavior/evidence | Status | Owner | Verification and residual limit |
|---|---|---|---|---|---|
| B1 | Hotel booking snapshot/arrival split; case builder, partition.py | Timing mismatch remains; J0 contract limits the case to a leakage exercise | partially_fixed | J0/J1/J2 | J0-A05: scope visible on synthetic data with the Hotel declaration; no booking-performance validation |
| B2 | Local CSV, commands/confirmation, no shared study ledger | Protocol reservation, agent-reported consent, no enforced cross-study inheritance | accepted_limit | J0/J4/J7 | J0-A06/A07: accessible synthetic source and unauthenticated choice channel; no claim of hostile-agent protection |
| B3 | activities.assign_folds, fit.compute_cv, families.inner_folds | Legacy complement-of-block and shuffled inner folds remain (code inspection) | confirmed_open | J1 | J0 refuses new-profile analytical execution; numerical remediation not yet implemented |
| B4 | preconditions.final_test_missing | Legacy diagnostics can still be bypassed (code inspection) | confirmed_open | J2 | J0 does not alter legacy opening; new-profile opening execution unavailable |
| I1 | commands availability validation | Known-unavailable override restriction not yet implemented | confirmed_open | J2 | Review reproduction retained as prior evidence; no real-case fit rerun |
| I2 | families._score, trials.select | Binary tuning/selection still uses ROC AUC | confirmed_open | J3 | Code inspection; business-objective oracle specified, not claimed passing |
| I3 | fit.criterion_status, criterion._status | Legacy point/minimum/zero-interval convention unchanged | confirmed_open | J3 | Code inspection; no useful-minimum confidence guarantee |
| I4 | diagnostics coefficient covariance and policy bootstrap | Conditional intervals remain; temporal/group coverage not established | not_retested | J3 | No new coverage experiment; do not treat numerical method change as broad proof |
| I5 | cmd_preview.preview_policy | Read-only previews remain unrecorded | confirmed_open | J4 | Code inspection; recorded inspection activity is still planned |
| I6 | trials.select | One-SE/optimism remain heuristic; dependencies/search history not fully handled | not_retested | J3/J5 | No new independent estimator validation |
| I7 | trials shortlist and proposal paths | Diagnostics mostly drive recommendations; hard/soft admission distinction pending | confirmed_open | J2 | Code inspection; no challenger-training run in J0 |
| I8 | code_compat.equivalent, read.Study.code_changed | Old-digest predicate still lacks destination digest | confirmed_open | J4 | Code inspection; no numerical equivalence exceptions added by J0 |
| I9 | cmd_check.wording, numeric tracing | Unrestricted semantic claim checking is not established | not_retested | J5 | Review's French causal counterexample retained; no new semantic-certification claim |
| I10 | fit.mean_baseline | MAE comparison still uses training mean in legacy studies | confirmed_open | J3 | Code inspection; Auto MPG README states this remains unchanged |
| M1 | eda permutation envelope | Exchangeability and general interval interpretation remain limited | not_retested | J3/J5 | No new permutation experiment |
| M2 | data.entity_groups, data-card sample | Exact duplicates are not all repeated entities; labelled preview accounting unchanged | confirmed_open | J1/J4 | J0 does not claim exhaustive exposure accounting |
| M3 | code_cells, generated notebook | Shared computation does not independently prove validity | accepted_limit | J6/J7 | J0 tests include independent metadata oracles only; notebook execution redesign pending |
| M4 | policy capacity conversion and glossary AP wording | Batch-period contract and canonical AP correction pending | confirmed_open | J3/J5 | Code inspection; no new capacity semantics in J0 |

R39 (quoted decision before adoption) and R40 (Copilot choice picker/text fallback)
are retained. Their generated-file checks are technical evidence, not a real Copilot
session. Per-milestone test results and environment limitations belong in `J0.md` and
later acceptance records, not in invented retrospective pass rates.
