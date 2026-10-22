# J2 — Availability, diagnostics and claim requirements

Depends on J0 and J1. Review coverage: B1, B4, I1, I7.

## Outcome

The engine enforces the conditions it announces. A fluent agent cannot accidentally
bypass them by issuing a direct CLI call. Uncertain assumptions remain visible;
documented impossibilities are not converted into facts by a confirmation.

## Implementation anchors

`commands.py`, `confirm.py`, `governance.py`, `preconditions.py`, `dependencies.py`,
`trials.shortlist`, `trials.data_contingency`, `activities.plan`, `executions.py`,
`diagnostics.py`, `state.choice_config`, `view.py` and `cmd_check.py`.
`preconditions.final_test_missing` currently explicitly ignores stale diagnostic
slots. That legacy rule must not remain the new profile's behavior.

## J2.1 — Enforce scenario-scoped availability

Use COMMON C3's `availability.restriction`; validate it in the case loader. The
effective availability is computed from the bound scenario, documented restriction
and adopted feature decision. Do not infer hard prohibitions from a column name,
high correlation, a keyword or AUC=1.

| Case information | Proposed inclusion | Behavior |
|---|---|---|
| Documented unavailable restriction in current scenario | available or uncertain_included | Refuse `invalid_value`, reason `documented_unavailability`; cite source and column |
| Scenario assumption of unavailability | available | Allow an explicit contradictory assumption with persistent limitation; never relabel as documented |
| Unknown/uncertain availability | uncertain_included | Allow exploratory comparison; list included uncertainty and narrow claim eligibility |
| Unknown/uncertain availability | uncertain_excluded | Exclude and explain; preserve uncertainty in history |
| Available with documented timing | available | Allow; does not itself prove the full study valid |
| Different prediction scenario | any | Require revised scoped contract; no free-text override of hard restriction |

Check at proposal and confirmation, and again when planning a fit. Confirmation may
be stale relative to the case or proposal. A manually edited state does not bypass
the computation boundary: the fit planner detects an included forbidden variable.

For the Hotel snapshot, the entire claim is limited even after known leaks are
excluded. Use a synthetic `outcome_copy` column to reproduce the direct leak test.
Do not train on historical Hotel holdout rows to prove the restriction works.

## J2.2 — One derived requirement evaluator

Introduce one pure evaluator (suggested `validity.py`) reused by decision checking,
activity reservation/promotion, `next_action`, `check`, and read models. It takes a
verified snapshot of state, relevant registry metadata and the case contract.

Return deterministic requirements keyed by code and relevant model/rule/result IDs.
At minimum support:

- `scenario_bound`, `analysis_contract_present`, `feature_timing_supported`;
- `evaluation_protocol_current`, `choice_evaluation_current`;
- `selected_configuration_current`, `development_diagnostics_current`;
- `interpretability_constraint_satisfied`, `uncertainty_available_for_claim`;
- `final_evidence_current_for_configuration`.

`status` or the panel must not implement a second approximate version. Before a
write, use the writer's verified snapshot and recheck revision. Do not use a read
view captured before the mutation as authoritative after it.

## J2.3 — Diagnostics required by the chosen conclusion

Define this minimal new-profile matrix; “current” includes matching prediction
result, model slot, population, protocol and adopted rule, not merely a slot name.

| Transition/assertion | Required diagnostic evidence |
|---|---|
| Initial candidate → variant discussion | Current candidate development error diagnostics; no need to prove a non-linear model will win |
| Open final test for binary ranking/action policy | Development confusion/action counts at the chosen rule and model; sample size and selection scope |
| Open final test for regression model | Development residual/error summary of chosen model; units and sample size |
| Describe probability quality | Current Brier score and calibration summary; always descriptive, with uncertainty/coverage limitations |
| Conclude using final evidence | Final evaluation plus final diagnostic summary for the recorded chosen configuration, computed from its persisted predictions |
| Conclude inconclusive without enough evidence | Allowed; explicitly list missing requirements; no implied empirical success |

`calibrated_probability` is not automatically eligible because a diagram exists or
a slope is between 0.8 and 1.2. In this first slice, the evaluator returns ineligible
for the general assertion “probabilities are calibrated”; it permits a descriptive
calibration statement tied to the actual diagnostic. A future specification may add
predeclared calibration tolerances and a validation protocol.

`keep_baseline` is allowed when the work stops without enough evidence, but the text
must distinguish “no justified change yet” from “baseline empirically superior.”
The latter assertion needs a valid comparison. Do not force an expensive fit merely
to allow an honest incomplete conclusion.

At the final-opening transition, refuse before reservation/final-row access if a
required development diagnostic is absent or stale. After successful final evaluation,
the next action is to calculate final diagnostics using stored final predictions;
this does not reopen or retune on the final test. The final has already been consumed
even if that diagnostic generation fails. Keep retries idempotent.

Use the existing explicit `run` execution model. `next_action` makes an authorized
diagnostic the next routine action, without asking a new approval question. Do not
hide an untracked long computation inside `status` or `decide propose`. Enforce the
prerequisite even if an agent skips the recommendation.

## J2.4 — Family admission and changed recommendations

Amend ADR 0007 explicitly for `review-v1`:

- `interpretability.required` is a hard constraint enforced at proposal, confirmation
  and fit reservation. `preferred` changes recommendation, not eligibility.
- A non-linear challenger may be predeclared for a substantive question; diagnostic
  flags are recommendations, not a theorem that only flagged models can improve.
- Extend new-profile list variants with `origin: planned|diagnostic_informed` and
  `diagnostic_result_id` (required for diagnostic-informed, null for planned). The
  question remains required; do not count its wording in model numerical identity.
- `planned` is permitted only if recorded before any model score is exposed through
  the instrumented workflow. It may be proposed early and adopted at the normal
  variant pause; retain its original event/revision. If declared after a score,
  classify as `diagnostic_informed`/data-contingent rather than backdating it.
- A diagnostic-informed proposal cites a current diagnostic and the question it
  motivates; its admission does not require a statistically significant flag.
- Preserve the maximum of three distinct confirmed variants, including replaced
  variants. No new budget is granted for changing family or question text.

Early planned declarations are proposals only; they do not fit or count as human
confirmation. Preserve the decision graph for adopting variants after prerequisites
exist. Concretely, allow `decide propose model_variant` to record a syntactically
valid `origin: planned` list before model execution in review-v1; its returned
proposal is `adoptable: false` with missing prerequisites until the normal adoption
point. `decide confirm` still checks every prerequisite. Proposal display does not
automatically advance the active step away from framing. This exception applies only
to predeclaration, not to arbitrary early decision confirmations. In the new profile,
repeated informal plans with no stored proposal are not
proof of predeclaration. Also disclose that instrumentation cannot prove no external
score has ever been inspected.

## J2.5 — Currency and refusal behavior

Changing the policy rule stales only rule-dependent diagnostics, not the split or
unchanged predictions. Changing model or preprocessing invalidates the appropriate
downstream diagnostics. Historical stale entries not referenced by a current required
slot are not blockers. Required current-slot results that are stale remain blockers.

`check` reports missing prerequisites as structured findings with the affected claim
or transition. It must not report a fully clean new-profile completed study that
skipped mandatory diagnostics. An early incomplete study may be internally consistent
while still incomplete; show `completion` and `claim_eligibility` separately from
integrity checks. Do not force all early status views to be “errors.”

## Acceptance

| ID | Scenario | Required outcome |
|---|---|---|
| J2-A01 | Include documented outcome_copy under bound scenario | Proposal and direct fit refused with source/column |
| J2-A02 | Include uncertain predictor | Exploratory fit allowed; future timing claim remains unsupported |
| J2-A03 | Confirm a stale availability proposal | Revision conflict; no decision or exposure mutation |
| J2-A04 | Open final without current development diagnostic | Refused before final-reader invocation; final still reserved |
| J2-A05 | Diagnostic exists for a different rule/model | Refused; correct routine next action supplied |
| J2-A06 | Old stale diagnostic plus a valid replacement | Opening not blocked by the old entry |
| J2-A07 | HGB under required interpretability | Refused through propose, confirm and run paths |
| J2-A08 | Predeclared EBM with no diagnostic flag | Admissible after required candidate diagnostics; no spurious flag required |
| J2-A09 | Claimed planned variant first declared after scores | No retroactive predeclaration; data-contingent provenance |
| J2-A10 | Final diagnostic fails after final evaluation | Final consumed, evaluation preserved, diagnostic retry allowed |
| J2-A11 | Inconclusive conclusion with absent models | Allowed with explicit missing-evidence explanation |
| J2-A12 | Calibration plot exists | No automatic “probabilities calibrated” eligibility |

Tests: `test_review_j2_validity.py` plus existing precondition, final opening,
diagnostics, trials, holds and conclusion-currency suites. Use a spy on the synthetic
final loader for A04, not a read of a real reserved test. J2 is complete only when
the direct CLI paths enforce the same rules as the guided path.
