# ADR 0006: A final test sealed at `init`

- Status: accepted and implemented in v0.2a (WP-A3); amended and implemented in v0.2b (WP-B1): the opening ritual and cross-validation (see the amendment below). Diagnostics are WP-B4.
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

## Amendment (v0.2b, WP-B1): cross-validation, one variant, the opening ritual

- Date: 19 October 2026
- Sources: [V0.2-REVIEW-SYNTHESIS.md](../plans/V0.2-REVIEW-SYNTHESIS.md) §3 (out-of-fold numbers are development evidence, only the sealed holdout is final evidence) and §4 ("5-fold CV with one analytical variant chosen by the junior so selection has a purpose"), [V0.2-IMPLEMENTATION-PLAN.md](../plans/V0.2-IMPLEMENTATION-PLAN.md) WP-B1
- Contracts: [CLI-CONTRACT.md](../specs/CLI-CONTRACT.md) §12

### Context

With a single validation split, every model and rule figure rests on one draw of about 30 % of the development rows, and the final test sealed at `init` had no way to be opened. Cross-validation uses every development row for both fitting and evaluation, and gives a spread across folds; but it is only meaningful when something is selected with it, so the junior names one variant to compare. The final test must then be opened once, after the choice, and anything changed afterwards must say so.

### Decision

1. **Generations.** A study created by `init` since WP-B1 has nine decisions: the seven of WP-A4, plus `model_variant` (before the choice) and `final_test` (after it). `state.decision_ids(state)` reads the set a state holds; v0.1 and v0.2a studies keep theirs and are never migrated.
2. **The evaluation scheme.** In such a study the `split` decision may be a cross-validation of the development rows, `{method, folds, seed}`: `kfold_stratified` (binary target), `kfold_quantile` (5 target quantile bins), or `temporal_folds` (contiguous blocks in time order when the case declares a time column or an order; each block is predicted by a model fitted on the other blocks, later ones included, so it measures stability across periods, not a forecast). 5 folds by default (3 to 10 accepted), seed 20261017. It is the default the engine drafts (`next_action.default_value`); the train/validation split stays accepted.
3. **Out-of-fold predictions.** Under cross-validation every development row is explored (the exploration's "training rows" are all development rows; target looks are still counted) and every fit predicts each fold with a model fitted, preprocessing included, on the other folds. Metrics are reported on the out-of-fold predictions of all rows with their per-fold spread; the policy and regression evaluations read those predictions, with paired bootstrap intervals over them. The binary baseline scores every row with the development positive rate (a per-fold rate would rank rows by fold); the regression baseline predicts each fold with the other folds' mean. A capacity is also expressed as a share of the rows it was chosen on.
4. **One variant.** `model_variant` names one variant of the candidate, decided in the junior's words without a reason: `{kind: regularisation, strength: weak|strong}` (logistic C 10 or 0.1 against the candidate's 1; ridge alpha 1 or 10 against the unregularised linear model) or `{kind: drop_group, group}` (the candidate without the features of one case group). `fit.variant` fits it under the same protocol; the evaluations compare it with the candidate (`comparisons`, variant minus candidate, paired). The choice selects the winner: a binary policy may apply its rule to the variant (`capacity:100@fit.variant`), a regression `model_choice` may be `fit.variant`. `view.trials` counts the candidate and variant configurations evaluated so far (a disclosure).
5. **The opening ritual.** `final_test` is decided in the junior's own words, with a reason, never by delegation, once the choice and the success criterion are confirmed, no fit or evaluation is stale and no decision waits for reconfirmation. Its value is the chosen configuration `{model, rule}`. Confirming it runs `final_test.evaluation` once: reserving it sets `partition.status` to `opened` with an `opening` record before any final-test row is read (so an interrupted run consumes the final test rather than allowing a second look), it refits the chosen configuration and the baseline on every development row, scores the final-test rows (`data.load_final_test`, the only reader of those rows), and evaluates the adopted rule (a capacity keeps its share of the rows) or the errors, with paired intervals, and the success criterion on the final test. Exposure: `train_fit` on the development rows and `final_evaluation` on partition `final_test`. A second opening is refused (`final_test_already_opened`).
6. **After the opening.** The opening is never asked again. Any later confirmation of a decision the evaluation rests on, or any fit or evaluation computed later, is listed in `view.final_test.changed_after` with `post_final_test: true`; `not_yet_defensible` then says the final test no longer measures what the study holds (`changed_after_final_test`). Before the opening, `final_test_sealed` says every figure is development evidence.

### Consequences

- Development figures use every development row (Bank: 3,617 out-of-fold predictions instead of 1,086 validation rows), and the report separates development evidence from the final test.
- The final test is consumed by its one evaluation, even an interrupted one: the price of never scoring it twice.
- Temporal folds are not a forward backtest; the temporal final test (when declared) is the forward check.
- A study keeps its variant's comparison and every configuration it fitted in the trial count; choosing among more configurations is disclosed, not corrected.
