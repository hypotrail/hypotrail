# J3 — Selection objective, references and success semantics

Depends on J0–J2. Review coverage: I2, I3, I4, I6, I10, M1, M4.

## Outcome

The criterion named before results determines tuning and model comparison. The
verdict distinguishes an attractive point estimate from uncertainty about a useful
minimum. Baselines, denominators and units match the actual objective.

## Current implementation anchors

`criterion.py`, `governance.py`, `fit.criterion_status`, `families._score`,
`families.choose`, `trials.select`, `policy.py`, `regression.py`, `metrics.py`,
`activities.plan`, `dependencies.py`, `render_trials.py`, `content/glossary.yaml`.
The inspected code duplicates criterion-status logic and selects binary variants by
ROC AUC even when the criterion is precision gain. Consolidate these semantics.

## J3.1 — Extend the existing success-criterion decision

New-profile proposals include the fields below. Legacy values continue to decode
without silently acquiring a new convention. All numerical fields must be finite;
booleans are not accepted as numbers.

```json
{
  "metric": "precision_gain",
  "min_points": 5,
  "decision_rule": "point_estimate",
  "selection": {
    "metric": "precision",
    "rule": "share:0.1",
    "scope": "evaluation_window",
    "batch_column": null,
    "aggregation": "pooled_counts"
  }
}
```

Binary metrics remain `precision_gain|recall_gain`; select using the corresponding
`precision|recall` at the fixed rule. Regression keeps `mae_reduction`, `min_share`,
selection metric `mae`, null rule and `aggregation: row_weighted`. Do not implement
arbitrary utility functions or new business metrics in this milestone.

`decision_rule` is `point_estimate|lower_bound`. Recommend `point_estimate` for the
exploratory teaching workflow with explicit wording; allow `lower_bound` only after
explaining that unsupported uncertainty can make the answer inconclusive. This is
part of the existing pause, not an extra questionnaire. Adopt before the first model
score. An edit after scores is allowed only as a recorded adaptive change and cannot
be described as preregistered. After final opening it cannot requalify that final
test as independent evidence for the newly chosen criterion.

The selection rule fixes **how candidates are compared**. The later `policy` decision
chooses the model and adopts that same rule. A different rule is a recorded proposal
change: invalidate selection-dependent tuning/evaluation, rerun needed computations
on development only, then ask adoption. Do not silently use AUC until a later policy
exists. Fixed candidate predictions need not be refitted just to evaluate a new rule.

## J3.2 — Action scope and metric aggregation

For `share:p`, apply the share separately in each declared evaluation window/batch,
using the existing rounding and pro-rata tie policy. Mark fractional tie counts as
expected counts. Sum TP, FP, FN and selected counts; compute overall precision from
total TP / total selected and recall from total TP / total positives. Do not average
per-window precision without its denominators. Tune and rank by this aggregate.

For `capacity:k`, require an explicit scope:

- `evaluation_window`: exactly up to k dossiers in each evaluation window; explicitly
  an exercise batch, not a daily/weekly production promise.
- `column_batch`: require a non-target `batch_column` identifying actual action
  batches. Each batch must be scored together by one fitted model and appear in one
  validation window. Refuse a split that cuts a batch. Sum batch-level results.

Use `min(k, batch_size)` with an underfilled-batch indicator; do not convert k into
`k / dataset_size` and transfer that fraction to another population. At final
evaluation, preserve the same declared batch semantics. If future action batches
cannot be identified, refuse a literal “100 per week” claim and offer an explicit
share exercise. Calendar construction is not implemented here.

For `threshold:t`, the threshold is fixed before tuning. Scores must be eligible
probabilities for a probability interpretation; a descriptive action rule can still
be evaluated with calibration limitations. If no rows are selected, precision is
null/undefined, never zero or one. If there are no positives, recall is undefined.
For candidate selection, an undefined objective in any required window makes that
candidate comparison unavailable with the reason; do not cherry-pick valid windows.
If all candidates are unavailable, propose revising the protocol/criterion explicitly.

MAE is sum of absolute errors / number of scored rows. Use identical keys and
weights for all models and paired differences. A model that fails a required window
must not be ranked against models scored on all windows.

## J3.3 — Baselines and one scoring implementation

- Regression MAE baseline predicts the **median of training targets** for each fold
  and the development median at final refit. Report its RMSE too if useful, but do
  not pretend this median minimizes squared error. For an already supported squared-
  error objective use the training mean; adding a new criterion is out of scope.
- Binary constant probability is the training positive rate, never the validation
  or all-development rate. Threshold behavior follows that actual constant.
- A no-information ranking reference for a share/capacity is expected random
  selection within the same action batch, with pro-rata ties and the actual batch
  outcomes used **only for evaluation**. Do not feed those outcomes into training.
- Keep `fit.baseline` as a slot; store `baseline_strategy` in parameters/values and
  fingerprint it. Never overwrite the old mean-baseline result in place.

Create one pure objective evaluator consumed by inner tuning, outer selection,
policy evaluation, final evaluation and the notebook. It returns metric, direction,
point, denominators, per-window values and unavailability reason. Diagnostics may
still show AUC/AP; they must not change which candidate the business rule selects.

Deterministic ties retain the predeclared simpler configuration using an explicit
complexity order and stable candidate ID. Keep the existing one-standard-error
recommendation as a separately labelled **heuristic** only when its equal-weight
fold summary is coherent with the objective. If pooled-count aggregation or unequal
window weights do not support the existing formula, return that heuristic unavailable
with a reason; do not attach its bound to a different statistic. This first slice
does not implement a new weighted selection-optimism estimator.

## J3.4 — One criterion assessment with a complete truth table

Centralize status logic in a pure function used by `fit`, `criterion` and
`governance`. Return separate fields:

`point_meets_minimum`, `interval_excludes_zero`, `lower_bound_meets_minimum`,
`uncertainty_status`, `decision_rule`, `decision_status`, `basis`.

`decision_status` is `met|not_met|uncertain|not_assessed`. `basis` explicitly identifies
`point_estimate`, `qualified_interval` or `unavailable`. An interval is qualified
only when its method, scope and assumptions support the stated assessment. Require
low <= high and finite values for a supplied interval; malformed input is an integrity
error, not missing uncertainty. Do not generally require the original point estimate
to lie inside a bootstrap percentile interval: a biased/skewed bootstrap distribution
can place it outside. Preserve that distinction rather than clamping a bound.

| Gain/minimum/interval | Point convention | Lower-bound convention |
|---|---|---|
| 6 / 5 / [1,11], qualified | met, by estimate | uncertain |
| 6 / 5 / none | met, by estimate; uncertainty unavailable | uncertain |
| 7 / 5 / [5.1,9], qualified | met | met |
| 5 / 5 / [5,5], qualified fixture | met | met (at least means >=) |
| 4 / 5 / [1,4.9], qualified | not_met | not_met |
| 4 / 5 / [1,9], qualified | not_met by estimate | uncertain |
| Missing gain | not_assessed | not_assessed |
| 6 / 5 / descriptive OOF spread [1,11] | met by estimate | uncertain; interval unqualified |

Use comparison tolerance solely for floating-point arithmetic (1e-12 in canonical
units); rounding for display never determines success. Binary differences are stored
as fractions in metrics, converted exactly once to percentage points for a
`min_points` comparison. Relative MAE reduction is
`(baseline_mae - model_mae) / baseline_mae`; if baseline_mae=0, it is undefined and
the relative criterion is not_assessed. Display the absolute errors and explain the
degenerate baseline; do not divide by zero or invent an infinite gain.

## J3.5 — Bounded uncertainty support

Store an uncertainty descriptor with method, level, unit of resampling, target
quantity, conditioning, dependence assumptions and eligibility. For this milestone:

- Independent held-out observations with a fixed already-selected configuration:
  retain paired row bootstrap with identical resamples for every compared model,
  clearly described as an approximate interval conditional on that fitted procedure
  and the declared sampling assumptions. Handle undefined replicates explicitly;
  never silently produce a bound from an arbitrary surviving fraction.
- Adaptive OOF selection: retain descriptive variability but do not call it a
  confidence interval for the whole selected/retrained procedure.
- Declared group/temporal dependence without an implemented justified method:
  `uncertainty_status: unavailable`, numeric bounds null for inferential assessment.
  A group/block bootstrap implementation is a later scoped task, not required here.
- Current coefficient Wald/sandwich intervals stay labelled conditional on preparation
  and penalty; do not claim robustness to clusters or the whole selection history.

Define an existing bootstrap call as unsuccessful if any required replicate's
objective is undefined; return unavailable and a count/reason. Do not silently
change the seed/number of replicates until an interval appears. This conservative
first-slice behavior may be relaxed only by a separately specified estimator.

Keep the 19-shuffle EDA envelope only as “exploratory envelope under label shuffling.”
For grouped/temporal/unknown dependence, suppress unrestricted shuffling unless a
valid exchangeability design is explicitly supported. Absence of a visible deviation
is not evidence of no association. One-SE and optimism outputs remain descriptive
aids, never model-equivalence tests or proofs that searching should stop.

## Acceptance and exact numeric oracles

| ID | Fixture/action | Expected |
|---|---|---|
| J3-A01 | y=[1,1,1,0,0,0,0,0], A=[.8,.7,.6,.9,.5,.4,.3,.2], B=[.9,.8,.1,.7,.6,.5,.4,.3], share=.25 | A AUC=.8, B AUC=2/3; top-share precision A=.5, B=1; business objective picks B |
| J3-A02 | Same oracle in inner tuning and outer comparison | Both follow declared objective; no AUC fallback |
| J3-A03 | Training and evaluation targets [0,0,0,0,100] | Mean prediction20 has MAE32; median prediction0 has MAE20 |
| J3-A04 | Validation targets changed, train unchanged | Fitted baseline and preparation unchanged |
| J3-A05 | All truth-table rows above, plus low>high/NaN | Exact statuses; malformed values rejected |
| J3-A06 | Batch sizes 40 and 200, capacity100 | Select40 and100, no conversion to a common fraction |
| J3-A07 | Unequal windows with precision1/1 and0/9 | Aggregate precision .1, not .5 |
| J3-A08 | Threshold selects nothing or target all negative | Correct undefined metric handling; no dropped fold |
| J3-A09 | Temporal/grouped uncertainty unsupported | Bounds not used for lower-bound success; explicit limitation |
| J3-A10 | Change selection rule after tuning | Tuned results stale; unchanged fixed predictions reusable only as appropriate |
| J3-A11 | Change minimum after final opening | Original final history retained; no independent success for adapted criterion |
| J3-A12 | Legacy mean-baseline result | Preserved and labelled; never reinterpreted as median |

Update ADR 0007, CLI contracts, rendering and text dictionaries. Targeted tests
include criterion, capacity/share, regression, trial selection and final-evaluation
suites plus `test_review_j3_objectives.py`. The notebook's agreement with the engine
is not a substitute for A01/A03's independently specified numbers.
