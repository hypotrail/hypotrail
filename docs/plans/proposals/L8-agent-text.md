# L8 agent-text proposal: per-column rare grouping (R6, D7)

Lot L8 of [OWNER-SESSION-2026-10-26-PLAN](../OWNER-SESSION-2026-10-26-PLAN.md) (§3 L8, §2.4
ledger, D7). The integrator applies this text to `framework/mlkit/study/agent/CLAUDE.md.in`
against the word ledger; L8 does not edit the agent templates.

## What changes and why

`rare_category_min_rows` is now one integer for every categorical feature (as before) **or** a
mapping `{column: min_rows}` (CLI-CONTRACT §11.3; `governance.check_preprocessing`). A column
the mapping leaves out keeps every category. Until L8 the agent had to say that the rule
applies to every categorical column (plan L5, R5 rule 1 and the O4 note); after L8 the junior's
"group the rare agents and companies" is recordable as stated, so the stop-gap sentence that
L5 may have added ("the rule is global") is withdrawn by the integrator when it merges L8.

The progress lines of `run --progress` now also say where a long run is ("pli 2/5",
"pénalité 3/5", "réplication bootstrap 120/1000"); the templates already run with
`--progress` and keep stderr (L4), so nothing changes there: the Copilot narration slot may
cite the fold it sees, but no new rule is needed.

## Exact replacement (+5 words in the shared raw text)

In `CLAUDE.md.in`, the decision list (around line 297):

```text
`split`, `success_criterion` (from `criterion_options`), `preprocessing` (`{"missing",
"rare_category_min_rows", "caps", "log_transform", "motivated_by"}`), `model_variant`
```

becomes

```text
`split`, `success_criterion` (from `criterion_options`), `preprocessing` (`{"missing",
"rare_category_min_rows" (an integer, or per column), "caps", "log_transform",
"motivated_by"}`), `model_variant`
```

## If L5 added a "the grouping is global" sentence

Remove it in the same commit (it frees its words). The engine refuses a key that is not a
categorical feature with `invalid_value` (`details.not_categorical`,
`details.categorical_features`), so no further rule is needed: the agent relays the refusal as
for any other value.

## Tests the integrator keeps or adds

- `test_agent_files.py::test_the_instructions_fit_the_word_budget` (unchanged cap).
- No pinned phrase is removed by this proposal.
