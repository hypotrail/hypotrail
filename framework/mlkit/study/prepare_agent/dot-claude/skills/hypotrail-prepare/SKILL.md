---
name: hypotrail-prepare
description: Prepare a Hypotrail study from one data file before it is sealed (six questions, the deduced final test, then seal). Use while `prepare status` says the study is preparing, for "prépare l'étude", "prepare the study", and when the user asks what is left before the study can start.
---

# Preparing a study before it is sealed

The user arrived with one data file and maybe a brief or a few lines of context. Before any
analysis, the study needs six answers in the user's own words; then the engine **deduces**
the final test from them and seals it. Speak the study language (`language` in
`prepare status`). Introduce a term first, then explain it with this dataset.

## Start

Run `{{HYPOTRAIL}} prepare status --study {{STUDY}}`. It gives `revision` (pass it as
`--expected-revision` to every write), `questions` (each `missing`, `proposed` or
`answered`), `next_question`, `columns` (structure only), `suspicious`, `brief`, and once
five questions are answered `final_test` (the plan in words and counts, its `plan` digest,
and pass or fail checks). Every write prints the refreshed status.

## Three input levels, one mechanism

- **A brief** (`brief.kind` pdf, docx, markdown or text): read `brief.source` (its text
  page by page or section by section). Propose the answers it supports and cite the page:
  `--source "brief p.3"`.
- **A context** (`brief.kind` context): the user's few lines, in the same file. Propose what
  they imply: `--source "context"`.
- **Nothing**: propose from the column names and `columns` only: `--source "column names
  and structural profile"`.

A brief or a context is an assumption of the scenario, never a fact. Record a proposal with
`prepare answer QUESTION --propose --source "..." --value-json '...' --expected-revision N
--study {{STUDY}}`; it stays "proposed, to confirm".

## The six questions, one per message

Ask exactly one question per message, in this order, starting with your proposal and its
source, and record the reply with `prepare answer QUESTION --value-json '...' --user-words
"<their words, verbatim>"` (or `--user-words-file FILE` for long or quoted words) and
`--basis known` when they state it from their own knowledge, `assumed` when it is a
plausible guess, `unknown` when they do not know. Never pass `known` because a brief says so.

1. `exposure`, first: "Have you already explored this file?" `{"explored": "not_explored" |
   "looked_at_rows" | "analysed_with_target"}`. Offer the three as a closed question with
   {{CHOICE_TOOL}}. Already analysed means the final test is not unseen: say so plainly.
2. `target`: `{"column": C, "positive_label": L}` for two values (L one of the labels
   `columns` lists), or `{"column": C, "unit": U}` for a numeric target. Never guess it.
3. `row_unit`: `{"row_unit": "one booking"}`, plus `"duplicates": "same_entity" | "distinct"
   | "unknown"` when `columns` reports repeated rows.
4. `timing`: `{"use": "future" | "retrospective" | "unknown", "statement": "<when the
   prediction is made>", "prediction_clock": C or null, "outcome_clock": C or null}`. A
   **clock** is a column of numbers on one ascending scale: the moment of the prediction, and
   the moment the outcome becomes known. A date column is refused with the way forward:
   relay it.
5. `entities`: `{"recurring": "yes" | "no" | "unknown", "column": C or null}`: does a customer,
   a vehicle, a patient appear on several rows?
6. `final_test`: once `final_test.status` is `pass`, show `final_test.words` (and the rule's
   `reason`) verbatim, then ask whether the user accepts it. Record `{"accept": true, "plan":
   "<final_test.plan>"}` with their words. If a check fails, relay its reason: the answers
   are what changes the final test, never a choice of method.

Flag the columns of `suspicious` while you ask `timing` and `target`: an identifier that
may encode time, a date that may come after the outcome, a near-copy of the target. Ask;
never decide their availability here, the study does that after sealing.

## Seal

When every question is answered, run `{{HYPOTRAIL}} seal --expected-revision N --study
{{STUDY}}`. It writes the case, sets the final test aside, creates the study and replaces
these instructions with the study's own. Tell the user in two lines how the final test was
set aside (`deduction.reason`) and how many rows it holds, then read the new `CLAUDE.md` and
continue with the study's first step. A refusal names its reason: relay it, change nothing
yourself.
