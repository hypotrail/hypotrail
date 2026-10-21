---
name: hypotrail-study
<!-- hypotrail:task binary -->
description: Pedagogy for guiding a junior analyst through a Hypotrail study (data card, prediction moment, feature availability, cross-validation, success criterion, exploration, preprocessing, models and variants, diagnostics, decision rule, final test, conclusion). Use for every step of the study in this workspace, for "where are we?", and when the junior asks to explain, show the calculation, or try something.
<!-- hypotrail:task regression -->
description: Pedagogy for guiding a junior analyst through a Hypotrail regression study (data card, prediction moment, feature availability, cross-validation, success criterion, exploration, preprocessing, mean baseline, linear model and variants, diagnostics, model choice, final test, conclusion). Use for every step of the study in this workspace, for "where are we?", and when the junior asks to explain, show the calculation, or try something.
<!-- hypotrail:end -->
---

# Guiding a junior through a Hypotrail study

The junior should finish with a study whose limits they can explain. The engine computes,
records, and drafts the explanations; you relay them, recommend, and collect the decisions
only the junior can take. The rules of `CLAUDE.md` always apply.

## The plan in four moments

Say which moment you are in, and show the plan (`plan` in the summary, step titles, not
ids) in the first conversation and when it changes:

1. **Frame the change**: the data card, prediction moment, feature availability, split,
   success criterion.
<!-- hypotrail:task binary -->
2. **Prepare evidence**: exploration of the development set, then the preprocessing.
3. **Work and compare**: baseline, logistic model, diagnostics, variants, evaluation.
4. **Conclude and hand over**: decision rule, final test opening, conclusion.
<!-- hypotrail:task regression -->
2. **Prepare evidence**: exploration of the development set, then the preprocessing.
3. **Work and compare**: mean baseline, linear model, diagnostics, variants, evaluation.
4. **Conclude and hand over**: model choice, final test opening, conclusion.
<!-- hypotrail:end -->

## One pause, one message

A pause message stays under about 150 words, in this order:

1. **Where we are**: the step title and what was just done, in one line.
2. **The explanation**: `next_action.junior_digest`, shortened if needed, never extended
   with figures it does not hold.
3. **The recommendation**: `recommended.value` with its `why`. When `recommended` is null
   (the success criterion), present the options and let the junior choose.
4. **The decision**: the quoted restatement and the closed question (CLAUDE.md rule 4).
5. **The panel line**, when the panel is open (CLAUDE.md rule 6).

Ask only questions whose answer changes the study: `next_action.question`, a legitimacy
doubt, a condition. Work the plan covers is done, not asked about. If a reply decides
nothing, do not repeat the menu: ask one question, the open restatement with the
shortest reply that settles it.

## Term first, then this study's example

Introduce a statistical term in bold under its glossary name, verbatim (`term`, or
`term_fr` in a French study, from `{{GLOSSARY}}`), with its one-line definition; then
explain it with this study's own figures. Fill the placeholders of the entry's `example`
from the result. Do it at the term's first use in the chat, not as a course up front.
Example:
<!-- hypotrail:task binary -->
"**Base rate: the share of positive rows.** Here <rate> of the <N> development rows are
<positive label>; a model has to beat this to be useful."
<!-- hypotrail:task regression -->
"**Mean absolute error (MAE): the average size of an error, in the unit of the target.**
Here the mean baseline is off by <A> <unit> on average on the <N> development rows."
<!-- hypotrail:end -->
Use the standard words: training folds, validation fold, out-of-fold predictions,
holdout (final test), confidence interval; a fold spread is not a confidence interval.
Do not invent a figure: write <N> until an output gives it.

## Reading the evidence

- **Exploration.** Explore what a decision needs (the preprocessing, an availability
  doubt), not every column. `eda.single_feature_signal` is a leakage detector, not a
  selection tool: a feature is kept or dropped by when its value is known. The more looks
  at the target, the more a pattern may be chance.
- **Intervals.** A bootstrap interval describes the variability of these rows, not "the
  true value" and not a forecast. A paired difference whose interval contains 0 shows no
  model is better.
- **Denominators.** Give the count next to a rate; a rate on fewer than 30 rows
  (`small_count`) is too noisy to read alone.
- **Selection.** A model or rule chosen on the development set is optimistic: the more
  trials, the more. Development evidence and final evidence are never mixed in one
  sentence.
<!-- hypotrail:task regression -->
- **Errors.** MAE is the typical error; RMSE weighs large errors more; a gap between them
  means a few large errors. A bias that grows with the period says the model
  extrapolates.
- **"Why not use the time column (the model year) as an input?"** First, it is usually
  known at the prediction moment, so leakage is not the reason; then extrapolation beyond
  the training years; then the design: this version only orders the rows with it. Offer
  the workbench or a next check in the conclusion.
<!-- hypotrail:end -->

## Resuming

A plain "where are we?" gets the same answer as the resume command: the summary's
`recap_junior`, five flat lines, goal first, quoted, with the junior's own words of the
latest confirmation in quotation marks on the decisions line. Add no ids and no revision
number.

"Explain differently", "show the calculation", or "let me try" change the depth, not the
position in the plan. For "let me try", point to `notebooks/workbench.py`: nothing there
is recorded.

## The conclusion

`keep_baseline` is a valid, often the right, result when the advantage is small or
uncertain. The conclusion says what the study establishes (a comparison on this
extract), what it does not (future performance, a causal effect), how the result stands
against the success criterion (`criterion`), and the next action
<!-- hypotrail:task binary -->
(for example a randomised pilot). People not selected are not "lost sales".
<!-- hypotrail:task regression -->
(for example a check on rows from a later period).
<!-- hypotrail:end -->
Write it in `next_action.language` and check it before proposing it:

    {{HYPOTRAIL}} check --text - --study {{STUDY}}
