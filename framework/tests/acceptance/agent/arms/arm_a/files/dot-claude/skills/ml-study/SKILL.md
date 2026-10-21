---
name: ml-study
description: Method, vocabulary, and validity checklists for guiding a junior analyst through a supervised tabular ML study (framing, evaluation design, EDA, baseline, modelling, selection rule, conclusion). Use for every step of the study in this workspace, including resuming a study and answering "where are we?".
---

# Guiding an ML study for a junior analyst

The analyst should finish with a reproducible study whose limits they can explain. You do the computation; they make the decisions that only they can make; both of you can always see where the study stands.

## The four moments and the plan

Organise the work in four moments, and keep the professional activity names inside them:

1. **Frame the change**: problem framing (observation unit, target, predictors, prediction time, intended use) and evaluation design (split).
2. **Prepare evidence**: data understanding and EDA (Exploratory Data Analysis) on the training partition, preprocessing.
3. **Work and compare**: baseline, model, evaluation and error analysis, selection rule.
4. **Conclude and hand over**: what is established, what is not, next action.

After a first structural inspection (files, documentation, rows, columns, types, target, special values, time and group structure), write a plan of four to seven steps in `STUDY.md`. Each step has a question, an expected output, and a completion condition. Mark each step `todo`, `in progress`, or `done`. Explain any material change to the plan and its consequences.

## Guidance loop (each meaningful step)

Say briefly: where we are in the plan; what was done; the evidence (with sample size and partition); the useful observation; the interpretation; the limitation; the recommended next action. Ask **one** main question at a time, with a reasoned default. Do not turn every chart into a quiz. "Explain differently", "show the calculation", or "let me try" change depth, not position in the plan.

## Vocabulary: term first, then the contextual explanation

Introduce a statistical term in bold, give a one-line definition, then an example from this data. Example: "**Recall: the share of observed positives retrieved by the selection.** Here: of the clients who did subscribe in the validation rows, how many would be in the call list." Add each term to the glossary section of `STUDY.md` the first time it is used. Useful terms: observation unit, target, predictor, prediction time, data leakage, train/validation/test, stratification, distribution, median, quantile, missingness, special value (sentinel), association, baseline, overfitting, regularisation, precision, recall, base rate, threshold, calibration, uncertainty, external validity.

## Validity checklist

### Availability and leakage (before any modelling)

- Ask, or propose as an explicit exercise assumption, **when** the prediction is made (the prediction time) and what action follows.
- For every column, decide whether its value is known **at prediction time**. Read the documentation, not just the column name. Typical traps:
  - a column recorded after or because of the outcome (it can predict the target almost perfectly and is unusable);
  - a column describing the *current* or *last* contact, attempt, or reminder: its value may depend on the process that the prediction is meant to drive, or on the outcome itself (e.g. contacts stop once the outcome happens);
  - a snapshot whose date is not documented.
- Classify each column as available, not available, or uncertain. Exclude not-available columns. For uncertain ones, either exclude them or keep them and list them as a limitation. Record the list in `STUDY.md` and let the analyst confirm it.
- A suspiciously strong single predictor is a leakage alarm, not a success.

### Split before EDA

- Choose the evaluation split **before** looking at relationships between predictors and the target. Structural inspection (types, counts, special values, duplicates, time and group columns) may come first; target-conditioned statistics may not.
- Prefer a time-based or grouped split when time or repeated units exist; otherwise a stratified random split with a fixed seed. Say what the split can and cannot measure.
- Do EDA on the **training partition only**, and label every table and chart with partition and sample size.
- Rows already looked at do not become unseen evidence because the split changes.

### Special values

- Check for sentinel codes (`-1`, `999`, `unknown`, empty strings) before computing statistics. Do not treat them as ordinary numbers or as empty cells without justification. Check whether two columns carry a sentinel on the same rows, which means one fact is encoded twice.

### Baseline and metrics

- With an imbalanced target, **accuracy alone is misleading**: predicting the majority class already reaches the base rate. Always report the base rate and a simple baseline (constant, or a one-variable rule) next to any model.
- For prioritisation under limited capacity, evaluate the selection: for a call list of size k, how many observed positives it contains (precision at k, recall at k, lift over random selection).
- Fit every preprocessing step on the training partition only (use a pipeline).

### Selection rule (threshold or capacity)

- A threshold or list size chosen on the validation partition is part of model selection. Its validation performance is **optimistic** and must be presented as exploratory, not as an estimate of future performance.
- When only the capacity (k) changes, **do not retrain**: reuse the existing scores and recompute the selection. Retraining is needed only if data, features, or the target change.
- Give uncertainty for headline figures when possible (e.g. bootstrap interval on validation), with sample sizes.

### Proportionate conclusion

- State what the study establishes (an exploratory comparison on this extract), what it does not (future performance, causal effect of the action, independence of customers or time periods), and the next action.
- Observed outcomes among people not selected are **not** "lost sales": the data do not measure what the action would have caused.
- Keeping the baseline, or finding no supported improvement, is a valid result.
- Never claim causality from associations.

## STUDY.md: the persistent record

Keep `STUDY.md` current after every step. Template:

```markdown
# Study: <title>

## Intention
## Status
Current step: <n> — <name>. Next action: <...>.
## Plan
| # | Moment | Step | Question | Expected output | Done when | Status |
## Facts and assumptions
- <fact> — documented / observed / assumption / unknown — source
## Decisions
| Date | Decision | Value | Status (proposed / confirmed / assumption / superseded) | Analyst's exact words | Depends on |
## Variables
| Column | Meaning | Available at prediction time? | Used? | Why |
## Results
| Result | Value | Partition | n | Where computed |
## Limitations
## Glossary
```

When resuming ("where are we?"), read `STUDY.md` and the notebook, then summarise in at most five lines: intention, confirmed decisions, results so far, open questions, recommended next action. Do not replay completed work.
