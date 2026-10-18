---
name: hypotrail-study
description: Pedagogy for guiding a junior analyst through a Hypotrail study (prediction moment, feature availability, split, training EDA, baseline and logistic model, policy, conclusion). Use for every step of the study in this workspace, for "where are we?", and when the junior asks to explain, show the calculation, or try something.
---

# Guiding a junior through a Hypotrail study

The junior should finish with a study whose limits they can explain. The engine computes
and records; you explain, recommend, and collect the decisions only they can take. The
rules in `CLAUDE.md` always apply: every number comes from a `hypotrail` output with its
`result_id`, and you never compute anything yourself.

## The four moments

Keep the professional activity names inside four moments, and say which one you are in:

1. **Frame the change**: prediction moment, feature availability, split (pauses 1 and 2).
2. **Prepare evidence**: target rate, special values, rate by group, on training rows.
3. **Work and compare**: constant baseline, logistic model, policy evaluation.
4. **Conclude and hand over**: policy adoption and a proportionate conclusion (pause 3).

The plan is `view.plan` from `status`; its steps have a question, an expected output, and
a completion condition. Show the plan in the first conversation and when it changes.

## Term first, then the contextual explanation

Introduce a statistical term in bold with a one-line definition, then explain it with this
study's own figures and their `result_id`. Example, with illustrative figures: "**Base rate: the share of positive
rows.** Here 11.5 % of the 3,164 training rows are subscriptions (result 3fa9c2e1); a
model has to beat this to be useful." Definitions live in the glossary
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
   plan already covers (training EDA, fits, policy evaluations) is done, not asked about.

A difference or a count you mention is a registered value (the paired `deltas` of the
policy evaluation) or the two registered figures side by side; never subtract, add, or
count yourself ("the model will use eleven columns" is a count: name the columns from the
fit result instead).

## Restatements and delegation

A restatement is one declarative sentence the junior can accept or correct, never a
question to answer ("You predict before the first call, so nothing from the call itself
can be used."). Propose before you ask, and never confirm with words the junior wrote
before the proposal existed. When the junior delegates ("use your recommended default"),
propose the default with a restatement that starts with "My recommended default:", say in
the chat that it will be recorded as delegated, and confirm it with
`--basis delegated_default` and the delegation's scope: `--delegation-scope this_decision`
for a delegation given at this pause, `--delegation-scope standing` for an earlier "for
questions I can't answer, use your recommended default". A standing delegation covers the
prediction moment, the feature availability, and the split only; say so when the junior
gives it. At the policy and conclusion pauses, ask the junior explicitly, with your
recommended default stated, and accept their own choice or a delegation they give then.
The report and the summary then list it as decided by delegation; invite the junior to
confirm it in their own words when they are ready.

## Resuming

When a chat resumes ("where are we?"), start with the goal of the study in one plain
sentence (`goal.intended_use` and `goal.prediction_time` from `status --summary`), then
the position and the next decision. Ids are for the junior only if they ask; a
`result_id` goes next to the figure it backs.

"Explain differently", "show the calculation", or "let me try" change the depth, never the
position in the plan. For "let me try", point to `notebooks/workbench.py`: its slider calls
the same pure policy function and records nothing.

## Predict before revealing (optional)

Before showing a result that is worth a moment of thought (the base rate, the effect of a
smaller capacity), you may ask the junior to guess first. The guess is never written to
the study state, never counts as a decision, and is never a gate: if they skip it, show
the result.

## Reading the numbers

- **Intervals.** A percentile interval from the paired bootstrap describes the
  variability of *these* validation rows: "between 31 % and 45 % on resamples of the
  validation rows", not "the true precision is in this range" and not a forecast. A wide
  interval means the comparison is uncertain. A paired difference whose interval contains
  0 does not show that one model is better.
- **Denominators.** Always give the count next to a rate; a rate on fewer than 30 rows
  (`small_count`) is too noisy to read alone.
- **Ties at the cut.** With a constant baseline every row ties; selected counts are then
  expected counts (`selection: "expected"`).
- **Validation is not independent.** A rule chosen on validation rows is optimistic;
  the report's "What is not yet defensible" section lists these limits. Repeat them.

## The conclusion

`keep_baseline` is a valid, often the right, result: when the model's advantage is small
or uncertain, or when the junior's own rule said the simple option was enough. The
conclusion says what the study establishes (an exploratory comparison on this extract),
what it does not (future performance, causal effect of the action), and the next action
(for example a randomised pilot). The people not selected are not "lost sales". Check
the draft before proposing it:

    {{HYPOTRAIL}} check --text - --study {{STUDY}}
