# ADR 0006: A final test sealed at `init`

- Status: accepted and implemented in v0.2a (WP-A3). The opening of the final test, cross-validation, and diagnostics are v0.2b (WP-B1, WP-B4).
- Date: 19 October 2026
- Sources: [V0.2-REVIEW-SYNTHESIS.md](../plans/V0.2-REVIEW-SYNTHESIS.md) §3 and §4 (owner decision 6, "holdout assigned and sealed at `init`"), [V0.2-IMPLEMENTATION-PLAN.md](../plans/V0.2-IMPLEMENTATION-PLAN.md) WP-A3
- Contracts: [CLI-CONTRACT.md](../specs/CLI-CONTRACT.md) §4.1, [CASE-CONTRACT.md](../specs/CASE-CONTRACT.md) §Order

## Context

In v0.1 a study had two partitions, made by the `split` decision: training rows (EDA and fitting) and validation rows (model and policy selection). The validation rows are used to choose, so their figures are optimistic; nothing in the study was independent evidence. A junior who explored, refit, and changed the split could see every row before anything was set aside, and the report could only say "not independent".

The literature the synthesis reviewed (Ambroise & McLachlan 2002; Cawley & Talbot 2010; ESL §7.10.2) is consistent: only rows set aside before any selection, and read once at the end, are final evidence. To be credible the set-aside must happen before the first look, including the structural inspection of `init` and any future data card, and it must hold mechanically, not by agent discipline.

## Decision

1. **Assignment at `init`, before any look.** `init` assigns a final test of 20 % of the rows (`partition.DEFAULT_FRACTION`) and seals it:
   - with a declared `order` in the case (`order: {by: line | <numeric column>, direction, status, source}`): `temporal`, the last rows in that order, ties broken by file line (the count of ties at the cut is recorded);
   - otherwise, binary target: `stratified`, the same share of each label;
   - otherwise, regression target: `quantile_stratified`, the same share of each of 5 target quantile bins.

   A stratified draw takes, per stratum in file order, a permutation from `numpy.random.default_rng(seed)` and keeps `floor(n × 0.2 + 0.5)` rows. The seed (0) is recorded, so the assignment is reproducible from the dataset bytes. Bank Marketing's `bank.csv` documents no order: its final test is stratified (904 of 4,521 rows, 104 of 521 `yes`).

2. **Storage.** `state.partition` (`hypotrail.final-test/1`) holds the method and its parameters, the counts, and the two row-key sets as content-addressed blobs (`row_keys` is the sha256 of the sorted keys, one per line; the blob file holds the list). Reading the development rows is one blob read; the identity of the partition is that digest plus its count.

3. **One choke point.** Every activity reads the dataset through `data.load_development(case, development_keys)`: the final-test rows are dropped right after parsing, and the returned frame and row index hold development rows only. Each activity's identity records `inputs.development` (the blob digest and count). The `split` decision now divides the development rows into training and validation rows; its UX is unchanged, its counts are smaller. A guard test (`test_final_test_partition.py`) instruments the loader and the row accessor and checks every exposure record, split blob, and predictions blob of a full binary and regression study.

4. **Schema check only.** The final test's cells are read once, at `init`, for a pass/fail schema check (numeric cells parse, no missing target, a binary target holds only allowed labels), recorded as counts of failing rows with no value, label, or row key. A failure refuses `init` with those counts; the development rows keep the detailed refusals (value, first rows). The case declares no ranges or category lists yet, so there is nothing more to check.

5. **Exposure.** `init` records its structural inspection on the development rows (`structural_inspection`, partition `development`) and the final-test rows under the purpose `sealed` (partition `final_test`). Sealed rows are listed in the ledger and not counted in `rows_exposed`.

6. **Surfaces.** `init`, `status` (`view.final_test`), and `status --summary` report `{status: sealed, rows, method, fraction, development_rows, schema_check}`.

7. **Legacy studies.** A study created before v0.2a has no `partition` and is never migrated: it loads and runs as before (every row is a development row, identities and exposure partitions unchanged), and surfaces report `final_test.status: absent` ("no final test").

## Consequences

- Every figure of a new study is computed on fewer rows (Bank: 3,617 development rows; a 30 % validation share gives 2,531 training and 1,086 validation rows instead of 3,164 and 1,357). Intervals are wider; that is the price of having final evidence at all.
- Result identities of new studies include the development blob: two studies on the same case share results only if their partitions match, which the recorded seed guarantees.
- The final test is assigned without the junior's words. This is a protocol default, like the bootstrap settings, not a human decision: it fixes nothing about the question, only what stays unseen. Changing the fraction or the seed is not exposed in v0.2a.
- A case whose rows are ordered in time must declare `order`, otherwise its final test is a random sample of all periods. Auto MPG declares a time column but no order; its final test is stratified on target quantiles and the `ordinal_cutoff` split then applies to the development rows.
- A dataset with very few rows of a class may leave no row of that class in the final test (a stratum of one row rounds to zero). This is recorded in the counts, not refused.

## Follow-up (v0.2b)

- **Opening ritual** (WP-B1): a `final_test` decision in the junior's words, after a confirmed model choice and policy; `status` becomes `opened` with an `opening` record (revision, result ids, words); every result after opening is labelled, and any later change is marked "after the final test". The record keys above do not change; `STATUSES` gains `opened`.
- **Cross-validation** (WP-B1): 5-fold CV on development rows, stratified or temporal as the final test, replacing the single validation split.
- **Diagnostics** (WP-B4): on out-of-fold predictions before opening, on the final test after.
- Optional case keys for the fraction or a grouped final test (once grouped splits exist) may follow; each needs this ADR amended.
