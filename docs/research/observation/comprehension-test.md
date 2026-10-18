# Comprehension test (without assistance)

Part of the [observation protocol](../OBSERVATION-PROTOCOL.md), §7. Give the participant **only the questions** (Part A), on paper or in a separate document, after the terminal, the report, and the notebooks are closed. 15 minutes. Part B is for the scorers.

---

## Part A: questions for the participant

Participant: P__ · Date: ________ · Start: __:__ · End: __:__

Answer in your own words. Short answers are fine. If you do not know, write "I don't know": that tells us what to improve, and it says nothing about you.

1. **Unit of observation.** In this study, what is one row of the data? What does the model give a score to?

2. **Prediction moment.** At what moment is the prediction made, in the bank's process? Why does it matter which moment you chose?

3. **An excluded column.** The column `duration` was not used by the model. Why not?

4. **Choosing with a metric.** Which figure did you use to compare the model with the simple baseline, or to choose the calling rule? Why not simply the share of correct predictions (accuracy)?

5. **The interval.** The report shows a precision with an interval, for example "between *a* and *b*". In your own words, what does that interval tell you, and what does it not tell you?

6. **The change to 100 calls.** When the team could make only 100 calls, what changed in the study, and what stayed the same? Why was the model not trained again?

7. **A limit.** Name one thing the study's conclusion cannot claim, and say why. (If you let the assistant choose a decision for you, also say what that means for that decision.)

---

## Part B: answer key and rubric (scorers only)

Score each answer **0** (missing or wrong), **1** (partly right, or right without the reason), or **2** (right, with the reason). Maximum 14. Score from the written answer only, blind to the session notes. Do not reward vocabulary: a correct idea in plain words scores 2; a correct term with a wrong idea scores 0.

The expected answers refer to **the participant's own study**, not to fixed numbers: their decisions and results differ. Before scoring, read their study with `hypotrail status --summary --study <their study>` (and `status --json` for values). Below, `slot` and `path` name where a figure lives in that study (for example `eda.target_rate` `rate` is the base rate on training rows); `fact:<id>` names a case statement.

### Q1. Unit of observation

- Expected: one row is one client contacted in a telephone campaign (`fact:observation_unit`, "A customer contacted during a telephone campaign"); the model scores each client (each row) so they can be ranked.
- 2: client contacted in a campaign, and the score is per client/row.
- 1: "a client" or "a call" without the scoring; or "a row of the CSV" with the score per row.
- 0: "the campaign", "the bank", "a column", or no answer.
- Note: "a call" alone is a known confusion (`campaign` counts contacts, not rows); score 1 and log it.

### Q2. Prediction moment

- Expected: the moment the participant's study recorded (`decisions.prediction_time.value`; the case's default is `fact:prediction_time`, "Before the call"), and why: only what is known at that moment may be used; information that arrives later (the call itself) would make the study look better than it can be in use.
- 2: their recorded moment (or an equivalent) **and** the link to which information is available.
- 1: the moment without the reason, or the reason without a moment.
- 0: a moment contradicting their recorded decision, or "it does not matter".
- If the decision was delegated (`decisions.prediction_time.basis` is `delegated_default`), still score the same way; note the delegation.

### Q3. Why `duration` is excluded

- Expected: `duration` is the length of the last call, known only once that call has ended, so it is not available at the prediction moment (`feature_availability` value `not_available`; case source `data/bank-names.txt:56,60`). Using it would leak the outcome of the call into the prediction (**leakage**).
- 2: known only after the call / not available at prediction time, with the consequence (too good to be true, cannot be used in practice).
- 1: "it is leakage" or "it is not available" without saying why or when.
- 0: "it is not important", "it had missing values", "the model did not need it", or no answer.

### Q4. Metric choice

- Expected: precision (and recall) of the selected clients under the calling rule, or the ranking quality (ROC AUC) to compare models, read from `fit.logistic` `validation.roc_auc` against `fit.baseline`, and from `policy.evaluation` `rules.<rule>.models.<slot>.precision`. Not accuracy, because subscribers are rare (the base rate, `eda.target_rate` `rate`, is low): predicting "nobody subscribes" is right for most rows and useless for choosing whom to call (**accuracy paradox**).
- 2: a metric about the selected or ranked clients **and** the rarity argument.
- 1: names precision, recall, or AUC without the reason; or the rarity argument without a metric.
- 0: "accuracy", or no answer.

### Q5. The interval

- Expected: the interval is the spread of the figure over resamples of **these** validation rows (paired bootstrap percentile interval, `policy.evaluation` `rules.<rule>.intervals.<slot>.precision.low/high`). A wide interval means the figure is uncertain; if the interval of the difference with the baseline (`deltas`) contains 0, the study does not show the model is better. It is not a forecast for the next campaign, and not "the true value is in it with 95 % probability".
- 2: variability on these rows / uncertainty, **and** one thing it does not say (not a forecast, or not a guarantee).
- 1: "uncertainty" or "margin of error" without what it does not say.
- 0: "the model will get between *a* and *b* next time", "the range of the scores", or no answer.

### Q6. Capacity 100: what changed, and why no refit

- Expected: only the selection rule changed (`capacity:100`: the 100 highest scores); the model, its scores, and the stored predictions stayed the same (the `fit.logistic` and `fit.baseline` result ids are unchanged); a new policy evaluation was run on those stored predictions, and the new rule needs its own confirmation. No refit, because the capacity changes which scores are selected, not how the scores are computed. The 100 apply to the validation rows, which stand for a share of the contacts, not a whole campaign.
- 2: rule changed, model unchanged, **and** the reason (selection vs scoring).
- 1: "the model is the same" or "we just changed the number" without the reason; or the reason without stating what stayed the same.
- 0: "the model was retrained for 100", "the scores changed", or no answer.
- Bonus note (not scored): mentions that the 100 apply to the validation rows (F2).

### Q7. A limit

- Expected: any item of the participant's "What is not yet defensible" list (the view's `not_yet_defensible`), with its reason. Typical: validation rows were used to choose the rule, so its figures are optimistic and not independent evidence of future performance; the study shows association, not the effect of calling (`fact:causal_effect`); the public data were explored before; doubtful features kept; repeated clients cannot be checked (`fact:repeated_observations`). If a decision was delegated (`basis` `delegated_default`): it was taken by the assistant's default, not by their own judgment, and is listed as such.
- 2: a valid limit **and** its reason (and, if they delegated, a correct account of the delegation).
- 1: a valid limit without the reason, or "the model could be wrong" made specific in some way.
- 0: no limit, "the model is not accurate enough" alone, or a limit that contradicts the study.

### Scoring sheet

| Participant | Q1 | Q2 | Q3 | Q4 | Q5 | Q6 | Q7 | Total /14 | Scorer | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| P1 | | | | | | | | | | |
| P2 | | | | | | | | | | |
| P3 | | | | | | | | | | |

With two scorers, record both scores, discuss each difference, and keep the agreed score; note the questions that needed discussion. Report per-question scores per participant; do not average across 2 or 3 people.
