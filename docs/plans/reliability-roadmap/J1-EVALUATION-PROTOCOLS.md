# J1 — Explicit evaluation protocols

Depends on J0. Review coverage: B3, timing portion of B1, M2.

## Outcome and non-negotiable invariant

For every fit, the engine knows exactly which row keys trained it and which row
keys evaluated it. For future prediction, all training information must have been
available strictly before the validation window starts. Nested tuning follows the
same rule. A fold number alone is not a sufficient representation of training rows.

## Current implementation anchors

`activities.assign_folds` and `compute_cv_split`; `fit.compute_cv` currently trains
on the complement of a validation fold. `families.inner_folds` uses shuffled splits
and lacks timing/group arguments. `partition.py` seals the final partition at init.
Consumers include `policy.py`, `cmd_preview._fold_groups`, `diagnostics.py`,
`code_cells.cv_fit_cell`, `notebook_view.py`, `eda.single_feature_signal` and
`trials.py`. Search every consumer of the `folds` blob before editing its schema.

## J1.1 — Introduce one explicit split-plan primitive

Add a pure planning component, suggested `evaluation_plan.py`; it consumes row keys,
validated clock/group arrays and a confirmed protocol. It does not read files or
write state. Persist its canonical output as a content-addressed blob referenced by
the split result. Suggested schema:

```json
{
  "schema": "hypotrail.evaluation_plan/1",
  "method": "forward_chaining",
  "folds": [
    {"id": 1, "train_keys": ["L2", "L3"], "validation_keys": ["L6", "L7"],
     "excluded_train_keys": [], "validation_start": 5, "validation_end": 6}
  ],
  "unscored_keys": ["L2", "L3", "L4", "L5"],
  "assumptions": [],
  "group_goal": null
}
```

Use fixture-appropriate keys; the schema example is illustrative, not a complete
partition oracle. Every fold must have nonempty disjoint training and validation
sets. Validation keys occur at most once in this first slice. `unscored_keys` contains
the development rows never predicted out of sample, including warm-up rows. Record
per-fold purge counts/reasons as well as keys; never expose final-test keys in a
junior response before opening. Every returned key must belong to the input universe.

For legacy results retain the old folds blob reader. New fits MUST consume explicit
memberships; no `train = all_rows - validation` reconstruction except for a declared
independent K-fold plan that explicitly encodes those memberships.

## J1.2 — Supported methods and deterministic rules

| Method | Training/validation rules | Supported purpose |
|---|---|---|
| Independent stratified K-fold | Existing seeded stratification; explicit memberships | Declared independent binary/quantile-stratified regression comparison |
| Group-disjoint K-fold | Entire groups held out; no shared group on either side | Unseen-group comparison |
| Forward chaining | Expanding eligible past, next contiguous validation block | Future prediction when both clocks are documented |
| Ordered retrospective chaining | Same chronological memberships using known order; missing outcome clock disclosed | Ordered retrospective exercise only |

Keep legacy `temporal_folds` distinguishable as “blocked-period stability; later
training may occur.” New-profile proposals MUST use explicit `forward_chaining` or
`ordered_retrospective` identifiers; do not silently reinterpret an old confirmed
value. J0/J1 contract amendments add the new split values.

For the new temporal methods, a decision contains
`{method, folds: k, gap: 0}`. `k >= 2`, gap is a nonnegative integer on the declared
ordinal scale. Sort **distinct prediction-order values**, then partition them into
`k + 1` consecutive nonempty chunks using numpy-array-split semantics (earlier chunks
get the remainder). Chunk 0 is warm-up; chunks 1…k are validation windows. All equal
timestamps stay together. Source-line ordering only makes output deterministic inside
a timestamp; it never permits training on a tied validation timestamp.

For window starting at `v`, a future-protocol row is train-eligible iff:

```text
prediction_order(row) < v - gap
AND outcome_available_order(row) < v - gap
AND row is not in validation
```

The conservative strict inequality is intentional. For ordered retrospective mode,
use only the first inequality and set `outcome_timing_verified: false`; forbid future
performance claims. Do not silently substitute this mode for a requested future mode.

For `grouped_temporal` with `unseen_groups`, additionally purge from training every
row whose declared group appears in this window's validation set. Keep validation
membership fixed. Never move a future row backward into training to keep a group
together. Exact-duplicate groups and declared entity groups are separate constraints:
combine their must-stay-together relations transitively where disjointness is
required; a pair `(entity, duplicate)` is not sufficient to represent their union.

Reject infeasible protocols explicitly: too few distinct times/groups, empty train
after purge, incompatible stratum sizes, or a classifier training fold without both
classes. An undefined validation metric is recorded as unavailable; never discard a
bad fold to improve the average. J3 defines comparison behavior with missing metrics.

## J1.3 — Nested tuning, diagnostic subfits and final refit

`families.choose` must receive the parent protocol and row metadata after subsetting
to the **outer training keys**. Reuse the same split-plan primitive at the inner
level. The inner planner cannot see outer validation labels, feature values or rows.
Imputation, rare-category handling, scaling, feature transformations and parameter
selection are fitted inside each inner train set. Enforce the same rule in diagnostic
or feature-signal subfits that claim out-of-sample performance; otherwise label their
output exploratory and do not use it to satisfy validation prerequisites.

Use the current fixed tuning grid; do not add search algorithms. If three inner
windows are infeasible, refuse the tuned variant with the precise reason and suggest
the fixed candidate or an explicitly revised protocol. Never fall back to shuffled
K-fold. Record the chosen parameter, scores, objective and inner-plan digest per
outer fold and for the final refit's development-only tuning.

For the final temporal boundary, use the prediction clock, not a convenience arrival
clock. Keep equal prediction times on one side. Use the latest approximately 20%
of rows, expanding the final side to include the complete tied boundary group;
report the actual fraction. Apply existing prior-exposure exclusions before settling
eligible final rows. Purge from the development/training side rows with labels not
available before the final start, plus overlapping groups when unseen-group generality
is required. Preserve excluded rows and exclusion reasons in partition metadata;
do not delete observations. Refuse if either usable side is empty. Never inspect
final target values to tune these boundaries.

Existing stratified independent final partitioning remains supported. A grouped
new-profile final partition must be group-disjoint; if both duplicate and entity
constraints apply, use their transitive grouping. Old final partitions are immutable.

## J1.4 — Predictions, consumers and displayed sample sizes

- Predictions contain only validation keys actually scored. No fake predictions or
  zeros for warm-up/purged rows. Attach the window/fold ID and plan digest.
- Every compared model uses the same scored keys and window assignments. A failed
  model/window fails the comparison; do not let each model choose its own subset.
- Binary constant probabilities and regression baselines are learned from each
  fold's train rows. Do not use all-development target rates to produce validation
  probabilities. Pooled AUC of changing constants is not “baseline discrimination”;
  prefer per-window ranking diagnostics and disclose undefined ones.
- Distinguish `n_development`, `n_scored`, `n_warmup`, and purge counts. The notebook,
  diagnostics and report must not continue to say every development row is OOF.
- EDA may still inspect authorized development rows; disclose target-informed
  adaptation. Forward membership correctness alone does not make an adaptively chosen
  development pipeline a pristine historical deployment simulation.

## Acceptance tests with independent oracles

| ID | Fixture/action | Required outcome |
|---|---|---|
| J1-A01 | Planner-only fixture: ticks 1…12, label tick=tick+2, k=2, gap=0 | Validation [5…8] trained only on [1,2]; validation [9…12] trained only on [1…6]; scored rows 5…12 |
| J1-A02 | Same fixture, label tick equals window start | Equal-time label is excluded, not treated as known |
| J1-A03 | Repeated prediction ticks at a cut | No time tie split between train and validation |
| J1-A04 | Group occurs in train candidate and next validation | All matching training rows purged; validation unchanged |
| J1-A05 | Entity linkage plus duplicate linkage through another row | No transitive leakage across a group-disjoint fold |
| J1-A06 | Inspect every inner plan | Subset of outer train; no future, overlapping group or outer validation key |
| J1-A07 | Inner plan impossible or training single-class | Specific refusal, no shuffled fallback, no promoted fit |
| J1-A08 | Extreme feature only in outer validation | Training preparation statistics unaffected |
| J1-A09 | New final temporal partition with delayed labels | Eligibility cut uses prediction and outcome clocks; exclusions counted |
| J1-A10 | Warm-up rows | Absent from predictions and metric denominators; present in development provenance |
| J1-A11 | Change split clock/plan during execution | Returned old fit archived or refused promotion, never current |
| J1-A12 | Old study with temporal_folds and opened final test | Unchanged history; legacy stability label; final not reopened |

Targeted suites: existing split, duplicate-group, fit, final-partition, trial and
notebook tests plus `test_review_j1_protocols.py`. Update CLI/case contracts, ADRs
0006/0007 and notebook generation together. This milestone is not complete with
only a replacement of `KFold` by `TimeSeriesSplit` in one function.

Use a larger synthetic fixture with alternating labels for the successful nested-fit
test; A01's first training window intentionally has only two rows and cannot support
three inner windows. Test that insufficiency as a refusal, not by weakening the
nested protocol to make the tiny oracle fit successfully.
