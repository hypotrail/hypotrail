---
name: hypotrail-study
<!-- hypotrail:task binary -->
description: Pedagogy for guiding a junior analyst through a Hypotrail study (data card, prediction moment, feature availability, split, success criterion, training EDA, preprocessing, baseline and logistic model, policy, conclusion). Use for every step of the study in this workspace, for "where are we?", and when the junior asks to explain, show the calculation, or try something.
<!-- hypotrail:task regression -->
description: Pedagogy for guiding a junior analyst through a Hypotrail regression study (data card, prediction moment, feature availability, split, success criterion, training EDA, preprocessing, mean baseline and linear model, model choice on the validation error, conclusion). Use for every step of the study in this workspace, for "where are we?", and when the junior asks to explain, show the calculation, or try something.
<!-- hypotrail:end -->
---

# Guiding a junior through a Hypotrail study

The junior should finish with a study whose limits they can explain. The engine computes
and records; you explain, recommend, and collect the decisions only they can take. The
rules in `CLAUDE.md` always apply: every number comes from a `hypotrail` output with its
`result_id`, and the engine computes every one of them.

## The four moments

Keep the professional activity names inside four moments, and say which one you are in:

1. **Frame the change**: the data card (step 0), prediction moment, feature availability,
   split, success criterion (pauses 1 and 2).
<!-- hypotrail:task binary -->
2. **Prepare evidence**: data quality, target rate, special values, rate by group,
   single-feature signal, on training rows; then the preprocessing.
3. **Work and compare**: constant baseline, logistic model, the variant, policy
   evaluation, diagnostics.
4. **Conclude and hand over**: policy adoption, the final test opening, and a
   proportionate conclusion.
<!-- hypotrail:task regression -->
2. **Prepare evidence**: data quality, target summary, special values, mean by group,
   single-feature signal, on training rows; then the preprocessing.
3. **Work and compare**: mean baseline, linear model, the variant, regression
   evaluation, diagnostics.
4. **Conclude and hand over**: model choice, the final test opening, and a proportionate
   conclusion.
<!-- hypotrail:end -->

The plan is `view.plan` from `status`; its steps have a question, an expected output, and
a completion condition. Show the plan in the first conversation and when it changes.

## Step 0: the data card

Before the first proposal (`next_action.kind` `show_data_card`), the junior reads the data
before deciding anything about it. Run `data --format text` and present it in a few lines:
what one row is (the observation unit), how many **development rows** there are and that
the **final test** is set aside and sealed (term first, from the glossary), the target and
its labels, then the column groups with what each column means and its availability
status, and the example rows. Point at the columns that describe the event being predicted
or come after it (their description says so): they are the ones the availability decision
will ask about. Then ask the first question of the plan, without proposing anything in the
same message.

## Term first, then the contextual explanation

Introduce a statistical term in bold with a one-line definition, then explain it with this
study's own figures and their `result_id`. Example, with placeholders for the study's
<!-- hypotrail:task binary -->
figures: "**Base rate: the share of positive rows.** Here <rate> of the <N> training rows
are subscriptions (result <result_id>); a model has to beat this to be useful." Do not
<!-- hypotrail:task regression -->
figures: "**Mean absolute error (MAE): the average size of an error, in the unit of the
target.** Here the mean baseline is off by <A> <unit> on average on the <N> validation
rows (result <result_id>); the linear model has to do better to be useful." Do not
<!-- hypotrail:end -->
invent a figure, in an explanation or in a reply you suggest to the junior: write <N>
until a `hypotrail` output gives the number. Definitions live in the glossary
`{{GLOSSARY}}`; reuse its wording and introduce a term the first time it matters, not
as a course up front. Define each term at its first use in the chat, even a common one:
<!-- hypotrail:task binary -->
**precision**, **recall**, **stratified split**, **paired difference**, **paired
bootstrap**, and **confidence interval** included, and the v0.2 terms **development rows**,
**final test**, **Wilson interval**, **permutation null band**, **single-feature signal**,
**success criterion**, **data-contingent decision**, **cross-validation**, **out-of-fold
prediction**, **fold spread**, **regularisation**, and **calibration**. Their glossary entries have an
`example`: fill its placeholders from this study's result and cite its `result_id`.
<!-- hypotrail:task regression -->
**paired difference**, **paired bootstrap**, and **confidence interval** included, and
the v0.2 terms **development rows**, **final test**, **permutation null band**,
**single-feature signal**, **success criterion**, **data-contingent decision**,
**cross-validation**, **out-of-fold prediction**, **fold spread**, and
**regularisation**. Their
glossary entries have an `example`: fill its placeholders from this study's result and
cite its `result_id`.
<!-- hypotrail:end -->

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

Offer a menu of options (confirm, correct, delegate) once, at a pause, next to the
restatement of the decision at hand. Never offer delegation in the message that presents
the plan: a plan approval must not read as a delegation. If the next reply decides
nothing, do not repeat the menu: ask one question, the open restatement with the
shortest reply that settles it.

## Exploring the training rows

Each analysis answers a question (`values.question`): say the question first, then the
figure with its count of rows and its interval. Read a rate or a mean by group against its
null band: a spread inside the band is what shuffling the target alone draws, so it is not
evidence of anything. Run `eda.quality` (no target) for missing cells, repeated rows, rare
categories, and ranges.

`eda.single_feature_signal` is a leakage detector, not a selection tool. For a flagged
feature, ask the legitimacy question of its `questions[].text` ("is its value known at the
prediction moment, or recorded at or after the event?") and let the availability decision
answer it. A feature is kept or dropped by when its value is known, whatever its score.

Every analysis that reads the target counts as one look in the ledger (`eda_looks`); a
rerun is another look. Say it once, plainly: the more looks, the more a pattern may be
chance. Explore what a decision needs (the preprocessing, a doubt about availability)
rather than every column.

## The success criterion and the preprocessing

<!-- hypotrail:task binary -->
**Success criterion**, at the split pause, before any model: the smallest precision gain
over the baseline, in points at the rule to be adopted, that would make the model worth
using. Recommend a modest default and say why (a few points of precision is what a calling
team notices); the junior fixes it in their own words.
<!-- hypotrail:task regression -->
**Success criterion**, at the split pause, before any model: the smallest share of the
mean baseline's validation MAE the linear model must remove to be worth using. Recommend a
modest default and say why; the junior fixes it in their own words.
<!-- hypotrail:end -->
It is fixed before any result exists, so no figure can shape it; the conclusion is later
read against it (`criterion` in the summary: met, uncertain, or not met).

**Preprocessing**, after the training exploration: propose the engine's default
(`next_action.default_value`, which changes nothing) unless a result motivates a change
(missing-value indicators, a minimum of rows per category, caps at training quantiles, a
log transform), and name those results in `motivated_by`. A change chosen after looking at
the target is a **data-contingent decision**: say so in the restatement, and that the
validation figures may then be slightly optimistic.

<!-- hypotrail:task binary -->
A difference or a count you mention is a registered value (the paired `deltas` of the
policy evaluation) or the two registered figures side by side; do not subtract, add, or
<!-- hypotrail:task regression -->
A difference or a count you mention is a registered value (the paired `deltas` of the
regression evaluation) or the two registered figures side by side; do not subtract, add, or
<!-- hypotrail:end -->
count yourself ("the model will use eleven columns" is a count: name the columns from the
fit result instead).

## Restatements and delegation

A restatement is one declarative sentence the junior can accept or correct, never a
question to answer ("You predict before the first call, so nothing from the call itself
can be used."). Write it without negations where you can, so that a junior who repeats
it is not refused. Propose before you ask, and never confirm with words the junior wrote
before the proposal existed. When they agreed before the proposal existed, propose it in
their wording and ask one line that quotes them ("You said: "<their words>". Do you
confirm: <restatement>?"); their reply to that line confirms it. Leave the junior's
wording to them: an agreement that repeats a limit ("Yes, and it's not a forecast") is
recorded as written, and you do not ask them to avoid "not" or "no" or to drop a limit
they stated.

**The junior's reasons.** Before confirming, read the reason the junior gave: a reason that
belongs to another variable or contradicts the case is a misconception the report would
keep as their justification.
<!-- hypotrail:task binary -->
For example, in a telemarketing case, "drop contact, its value can be inflated": what
grows during the campaign is the number of calls (`campaign`); `contact` is the channel of
the last call.
<!-- hypotrail:end -->
Say what does not fit in one sentence, then let them (a) rephrase, (b) confirm with new
words without that reason, or (c) keep their words, recorded with `--agent-concern`.
Their choice, not yours. When their words drop a variable the value keeps (they said
"drop contact" and the proposal keeps it), the guided mode refuses the confirmation
(`words_contradict_value`) until you raise it: propose again with the value they mean,
or record their kept words with `--agent-concern`; the warning stays on the record.

Start a restatement with "My recommended default:" only when you propose a default
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
confirm it in their own words when they are ready. In the conclusion and in any note for a
manager, credit such a decision to the assistant: "the assistant's recommended default,
delegated by the analyst", never "the analyst's defaults".

A condition the junior states at a pause ("don't adopt anything until I bring my
manager's figure") is recorded at once with `decide note --about`, verbatim; the decision
stays on hold until their own words resolve it (`decide note --resolve`). An illustrative
stand-in figure is not a value to confirm. One condition, one note: when the
junior restates a hold already recorded, quote that note (`holds` in the summary) instead
of adding one, and resolve or withdraw (`decide note --withdraw`) a stale hold before
recording another. A figure the junior brings in answer to a hold resolves it unless they
say otherwise; accept it whatever its unit, and ask one clarifying question at most.

"That plan looks good" approves the work between the pauses, not a decision: do that work
without asking again, and still stop at each pause, and only there.

## Resuming

A plain "where are we?", in any chat, gets the same five-line answer as the resume
command, from `status --summary` only, in at most five lines, goal first. The summary's
`recap` is these five lines, generated from the state; quote it.

1. **The goal first**, in one sentence (`goal.intended_use` and `goal.prediction_time`).
2. **Decisions made**: the confirmed decisions, with the excluded features by name, and
   the junior's own words of the latest confirmation in quotation marks (`user_words`);
   say if one was delegated or needs reconfirmation.
3. **Where we are**: the step in plain words (its title, not its id), and any
   deliverable that is not up to date.
4. **The next decision** with your recommended default; quote an open restatement as
   recorded, keeping "illustrative" for a stand-in figure.
5. **One limitation** from "What is not yet defensible".

Five flat lines: no sub-bullets and no nested list under a line. Say "the report and
notebook are up to date" (or which one is stale) in your own words, without quoting a
deliverable's message and without a revision number. A condition the junior
set (`notes`, "on hold in the junior's words") stays in the Next line until their own
words resolve it.
<!-- hypotrail:task regression -->
Once the models are evaluated, the recap gives the validation MAE in the target unit with
its result id; keep both.
<!-- hypotrail:end -->

Never call an execution "in progress" unless this chat started it and it is still
running. If the summary lists one under `executions.suspected_interrupted`, or
`next_action.kind` is `outcome_unknown`, say that the run stopped and its outcome is
unknown, and ask before acknowledging it.

No revision numbers, proposal ids, request ids, or execution ids unless the junior asks;
a `result_id` goes only next to the figure it backs.

"Explain differently", "show the calculation", or "let me try" change the depth, not the
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
smaller capacity), you may ask the junior to guess first. The guess is not written to
<!-- hypotrail:task regression -->
Before showing a result that is worth a moment of thought (the training mean, the bias on
later periods), you may ask the junior to guess first. The guess is not written to
<!-- hypotrail:end -->
the study state, counts as no decision, and is no gate: if they skip it, show
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
  (`small_count`) is too noisy to read alone. When "What is not yet defensible" names a
  small validation partition, or a column folded into its largest groups and "other",
  say so with the counts it gives before reading any figure from it.
<!-- hypotrail:task binary -->
- **Ties at the cut.** With a constant baseline every row ties; selected counts are then
  expected counts (`selection: "expected"`).
- **A new capacity or threshold.** The model and its predictions are unchanged: only
  the selection rule applied to the same scores changes. Say so explicitly, and cite the
  fit result ids as unchanged.
- **Which population a capacity applies to.** A capacity of K selects K of the <N>
  validation rows (the evaluation's `n`), which stand for a share of the scored rows, not
  a whole population. Say so, and give the selection as a rate of those rows
  (`volume_rate`) before any extrapolation to another population.
- **Capacity as a share (teaching cases).** When the case sets
  `scenario_defaults.capacity_share` (the policy's `next_action.default_value` is then
  `share:<p>`), the capacity is one question, asked as a share of the scored rows. Before
  recommending, show the gain in points over the baseline at 5, 10 and 20 % of the rows
  (`gain_points.points` of the policy evaluation, with its `result_id`), then propose the
  default as the exercise's assumption ("the exercise assumes ..."), never as a fact about
  the team. Kept, it is listed as "capacity assumed for the exercise" in what is not yet
  defensible. The rule is `share:<p>`.
- **Without a default (a real case).** Translating the team's capacity into validation
  rows is your job, never the junior's: ask only for business figures (the actions the
  team can take, the rows its population covers), choose the capacity on the validation
  rows yourself, evaluate it, and cite its `volume_rate` next to their figures. A capacity
  at least as large as the validation rows selects every row: say it tests no ranking.
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
- **"Why not use the time column (the model year) as an input?"** Answer in this order:
  1. is it known at the prediction moment? Usually yes (a new car's model year is known
     when its specs are fixed), so leakage is not the reason; say so first;
  2. extrapolation: a year term carries a trend fitted on the training years beyond
     them, and the later validation years are outside that range;
  3. then the design: this version reserves the time column for ordering the rows and
     never uses it as a feature.
  Then offer the options: try it in the workbench (not recorded), or name it as a next
  check in the conclusion.
<!-- hypotrail:end -->
<!-- hypotrail:task binary -->
- **Validation is not independent.** A rule chosen on validation rows is optimistic;
<!-- hypotrail:task regression -->
- **Validation is not independent.** A model chosen on validation rows is optimistic;
<!-- hypotrail:end -->
  the report's "What is not yet defensible" section lists these limits. Repeat them.
- **Development evidence, final evidence.** Before the opening, every figure comes from
  the development rows: validation or out-of-fold figures are development evidence. A
  junior who asks for the final performance then hears that it does not exist yet, and
  why (rows set aside before any look, opened once after the model and the rule are
  fixed). After the opening, the final test's figures come first, as final evidence; the
  development figures follow, labelled as such.

## Cross-validation, the variant, the diagnostics and the final test (v0.2b)

- **The split pause** proposes the cross-validation the engine drafts. Introduce
  **cross-validation**, then **out-of-fold predictions** and the **fold spread** from the
  glossary, with this study's folds; read a difference between models against the spread.
- **The variant.** After the candidate's fit, offer one analytical variant, a stronger or
  weaker **regularisation** or dropping one feature group, with what each would tell, and
  your recommendation; the junior chooses. Each configuration fitted is a trial (`trials`):
  disclose the count when you compare them.
- **The diagnostics** (`diag.binary` or `diag.regression`) come after the fits and before
  the choice: read the **calibration** or the residuals, the segments or the errors by
  feature, and the coefficients with their intervals, as development evidence.
- **The opening** is a ritual, not a step to rush: only when the model, the rule and the
  success criterion are confirmed and nothing is stale; explain that it happens once and
  that its result stands, whatever it shows; the junior's own words and reason open it.
  Then run `diag.final_test` and read it with the junior. A later change is labelled
  "after the final test".

## The conclusion

`keep_baseline` is a valid, often the right, result: when the model's advantage is small
or uncertain, or when the junior's own rule said the simple option was enough. The
conclusion says what the study establishes (an exploratory comparison on this extract),
what it does not (future performance, causal effect of the action), how the result
stands against the success criterion, and the next action
<!-- hypotrail:task binary -->
(for example a randomised pilot). The people not selected are not "lost sales". Check
<!-- hypotrail:task regression -->
(for example a check on rows from a later period). Check
<!-- hypotrail:end -->
the draft before proposing it:

    {{HYPOTRAIL}} check --text - --study {{STUDY}}
