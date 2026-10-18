---
name: hypotrail-study
<!-- hypotrail:task binary -->
description: Pedagogy for guiding a junior analyst through a Hypotrail study (prediction moment, feature availability, split, training EDA, baseline and logistic model, policy, conclusion). Use for every step of the study in this workspace, for "where are we?", and when the junior asks to explain, show the calculation, or try something.
<!-- hypotrail:task regression -->
description: Pedagogy for guiding a junior analyst through a Hypotrail regression study (prediction moment, feature availability, split, training EDA, mean baseline and linear model, model choice on the validation error, conclusion). Use for every step of the study in this workspace, for "where are we?", and when the junior asks to explain, show the calculation, or try something.
<!-- hypotrail:end -->
---

# Guiding a junior through a Hypotrail study

The junior should finish with a study whose limits they can explain. The engine computes
and records; you explain, recommend, and collect the decisions only they can take. The
rules in `CLAUDE.md` always apply: every number comes from a `hypotrail` output with its
`result_id`, and you never compute anything yourself.

## The four moments

Keep the professional activity names inside four moments, and say which one you are in:

1. **Frame the change**: prediction moment, feature availability, split (pauses 1 and 2).
<!-- hypotrail:task binary -->
2. **Prepare evidence**: target rate, special values, rate by group, on training rows.
3. **Work and compare**: constant baseline, logistic model, policy evaluation.
4. **Conclude and hand over**: policy adoption and a proportionate conclusion (pause 3).
<!-- hypotrail:task regression -->
2. **Prepare evidence**: target summary, special values, mean by group, on training rows.
3. **Work and compare**: mean baseline, linear model, regression evaluation.
4. **Conclude and hand over**: model choice and a proportionate conclusion (pause 3).
<!-- hypotrail:end -->

The plan is `view.plan` from `status`; its steps have a question, an expected output, and
a completion condition. Show the plan in the first conversation and when it changes.

## Term first, then the contextual explanation

Introduce a statistical term in bold with a one-line definition, then explain it with this
study's own figures and their `result_id`. Example, with placeholders for the study's
<!-- hypotrail:task binary -->
figures: "**Base rate: the share of positive rows.** Here <rate> of the <N> training rows
are subscriptions (result <result_id>); a model has to beat this to be useful." Never
<!-- hypotrail:task regression -->
figures: "**Mean absolute error (MAE): the average size of an error, in the unit of the
target.** Here the mean baseline is off by <A> <unit> on average on the <N> validation
rows (result <result_id>); the linear model has to do better to be useful." Never
<!-- hypotrail:end -->
invent a figure, in an explanation or in a reply you suggest to the junior: write <N>
until a `hypotrail` output gives the number. Definitions live in the glossary
`{{GLOSSARY}}`; reuse its wording and introduce a term the first time it matters, not
as a course up front.

## The guidance loop

At each meaningful step, briefly:

1. **Position**: the moment and the step in plain words (the step title, not its id),
   what was just done.
2. **Question**: the question this step answers.
3. **Evidence**: the figures from the result, with the partition (training or
   validation), the denominator, and the `result_id`.
4. **Interpretation**: what the figures say and what they do not say (association, not
   effect; validation rows already used for a choice).
5. **Next recommendation**: the recommended next action (`next_action`), with a
   reasoned default. Ask **one** main question at a time, and only at a pause: work the
<!-- hypotrail:task binary -->
   plan already covers (training EDA, fits, policy evaluations) is done, not asked about.
<!-- hypotrail:task regression -->
   plan already covers (training EDA, fits, the regression evaluation) is done, not asked
   about.
<!-- hypotrail:end -->

Offer a menu of options (confirm, correct, delegate) once. If the next reply decides
nothing, do not repeat the menu: ask one question, the open restatement with the
shortest reply that settles it.

<!-- hypotrail:task binary -->
A difference or a count you mention is a registered value (the paired `deltas` of the
policy evaluation) or the two registered figures side by side; never subtract, add, or
<!-- hypotrail:task regression -->
A difference or a count you mention is a registered value (the paired `deltas` of the
regression evaluation) or the two registered figures side by side; never subtract, add, or
<!-- hypotrail:end -->
count yourself ("the model will use eleven columns" is a count: name the columns from the
fit result instead).

## Restatements and delegation

A restatement is one declarative sentence the junior can accept or correct, never a
question to answer ("You predict before the first call, so nothing from the call itself
can be used."). Propose before you ask, and never confirm with words the junior wrote
before the proposal existed. Start a restatement with "My recommended default:" only when you propose a default
after a delegation; every other proposal, including one made on "continue", is a plain
declarative sentence. When the junior delegates ("use your recommended default"),
propose the default with a restatement that starts with "My recommended default:", say in
the chat that it will be recorded as delegated, and confirm it with
`--basis delegated_default` and the delegation's scope: `--delegation-scope this_decision`
for a delegation given at this pause, `--delegation-scope standing` for an earlier "for
questions I can't answer, use your recommended default". A standing delegation covers the
prediction moment, the feature availability, and the split only; say so when the junior
<!-- hypotrail:task binary -->
gives it. At the policy and conclusion pauses, ask the junior explicitly, with your
<!-- hypotrail:task regression -->
gives it. At the model choice and conclusion pauses, ask the junior explicitly, with your
<!-- hypotrail:end -->
recommended default stated, and accept their own choice or a delegation they give then.
The report and the summary then list it as decided by delegation; invite the junior to
confirm it in their own words when they are ready.

## Resuming

A plain "where are we?", in any chat, gets the same five-line answer as the resume
command, from `status --summary` only, in at most five lines, goal first. The summary's
`recap` is these five lines, generated from the state; quote it.

1. **The goal first**, in one sentence (`goal.intended_use` and `goal.prediction_time`).
2. **Decisions made**: the confirmed decisions, with the excluded features by name; say
   if one was delegated or needs reconfirmation.
3. **Where we are**: the step in plain words (its title, not its id), and any
   deliverable that is not up to date.
4. **The next decision** with your recommended default; quote an open restatement as
   recorded, keeping "illustrative" for a stand-in figure.
5. **One limitation** from "What is not yet defensible".

Never call an execution "in progress" unless this chat started it and it is still
running. If the summary lists one under `executions.suspected_interrupted`, or
`next_action.kind` is `outcome_unknown`, say that the run stopped and its outcome is
unknown, and ask before acknowledging it.

No revision numbers, proposal ids, request ids, or execution ids unless the junior asks;
a `result_id` goes only next to the figure it backs.

"Explain differently", "show the calculation", or "let me try" change the depth, never the
<!-- hypotrail:task binary -->
position in the plan. For "let me try", point to `notebooks/workbench.py`: its slider calls
the same pure policy function and records nothing.
<!-- hypotrail:task regression -->
position in the plan. For "let me try", point to `notebooks/workbench.py`: it lists the
validation rows with the largest residuals of a chosen model and records nothing.
<!-- hypotrail:end -->

## Predict before revealing (optional)

<!-- hypotrail:task binary -->
Before showing a result that is worth a moment of thought (the base rate, the effect of a
smaller capacity), you may ask the junior to guess first. The guess is never written to
<!-- hypotrail:task regression -->
Before showing a result that is worth a moment of thought (the training mean, the bias on
later periods), you may ask the junior to guess first. The guess is never written to
<!-- hypotrail:end -->
the study state, never counts as a decision, and is never a gate: if they skip it, show
the result.

## Reading the numbers

- **Intervals.** A percentile interval from the paired bootstrap describes the
  variability of *these* validation rows: "between <low> and <high> on resamples of the
<!-- hypotrail:task binary -->
  validation rows", not "the true precision is in this range" and not a forecast. A wide
<!-- hypotrail:task regression -->
  validation rows", not "the true error is in this range" and not a forecast. A wide
<!-- hypotrail:end -->
  interval means the comparison is uncertain. A paired difference whose interval contains
  0 does not show that one model is better.
- **Denominators.** Always give the count next to a rate; a rate on fewer than 30 rows
  (`small_count`) is too noisy to read alone.
<!-- hypotrail:task binary -->
- **Ties at the cut.** With a constant baseline every row ties; selected counts are then
  expected counts (`selection: "expected"`).
- **A new capacity or threshold.** The model and its predictions are unchanged: only
  the selection rule applied to the same scores changes. Say so explicitly, and cite the
  fit result ids as unchanged.
- **Which population a capacity applies to.** A capacity of K selects K of the <N>
  validation rows (the evaluation's `n`), which stand for a share of the contacts, not a
  whole campaign. Say so, and give the selection as a rate of those rows (`volume_rate`)
  before any extrapolation to another population.
<!-- hypotrail:task regression -->
- **Errors in the unit of the target.** Give MAE first (the typical size of one error),
  then RMSE (it weighs large errors more: a gap between the two means a few large
  errors), always with the unit. A paired difference of MAE below zero means the linear
  model errs less than the mean baseline on these rows.
- **Residuals and bias.** A residual is observed minus predicted; the mean residual is
  the bias. A positive bias means the model predicts too low. Look at the residuals by
  period: a model fitted on earlier periods and validated on later ones extrapolates, and
  a bias that grows with the period is the sign of it.
- **What the split cannot show.** The time column orders the rows and is not a model
  feature. Rows of a group shared by both partitions (the split result counts them) are
  not independent: say so whenever a validation figure is read.
<!-- hypotrail:end -->
<!-- hypotrail:task binary -->
- **Validation is not independent.** A rule chosen on validation rows is optimistic;
<!-- hypotrail:task regression -->
- **Validation is not independent.** A model chosen on validation rows is optimistic;
<!-- hypotrail:end -->
  the report's "What is not yet defensible" section lists these limits. Repeat them.

## The conclusion

`keep_baseline` is a valid, often the right, result: when the model's advantage is small
or uncertain, or when the junior's own rule said the simple option was enough. The
conclusion says what the study establishes (an exploratory comparison on this extract),
what it does not (future performance, causal effect of the action), and the next action
<!-- hypotrail:task binary -->
(for example a randomised pilot). The people not selected are not "lost sales". Check
<!-- hypotrail:task regression -->
(for example a check on rows from a later period). Check
<!-- hypotrail:end -->
the draft before proposing it:

    {{HYPOTRAIL}} check --text - --study {{STUDY}}
