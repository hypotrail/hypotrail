# L5 agent-text proposal: relay the drafts that read the evidence (R5, R7, R13, R14, R15)

Lot L5 of [OWNER-SESSION-2026-10-26-PLAN](../OWNER-SESSION-2026-10-26-PLAN.md) (§3 L5, §2.4
ledger, D5, D6, D9, D10, D11). The integrator applies this text to
`framework/mlkit/study/agent/CLAUDE.md.in` against the word ledger; L5 does not edit the agent
templates (§1.3). Nothing here is Copilot-only: the three changes are shared lines of the
Claude Code and Copilot copies (no `FLAVOUR_TEXTS` slot changes).

## What changes and why

The engine now does what three passages ask the agent to compose:

- **Preparation** (R5, R7). In a new study the quality check runs before any look at the
  target and `next_action.default_value` of the preprocessing is drafted from it
  (`recommended.reasons`, one per parameter, each citing a registered path;
  `next_action.alternatives` holds the default as the comparison option). The stamp comes with
  its own junior text: `data_contingent_reason.junior_text` (study language: the term "look at
  the target" first, this study's looks, why it is recorded, "not a mistake"). The bare clause
  "chosen after looking at the target" in the restatement is what the owner read as a
  reproach (R5, last paragraph); it is dropped.
- **Variants and families** (R13, R14, R15). The drafted `default_value` adds the EBM when the
  diagnostics flag a pattern and two trials are left; `model_families.families[].junior_words`
  names `hgb` "tree boosting (the same family as XGBoost and LightGBM)"; `model_families.
  not_offered` says why there is no random forest; a family outside the catalogue is refused
  with `details.junior_message` (closest family, why the catalogue is closed, the workbench).
  The demo question sentence ("Pourquoi le moteur envisage-t-il ...") is replaced by the relay.
- **Decision list.** The value shapes the drafts and the refusals now give are dropped (the
  pinned `model_choice` phrase of the binary block is untouched).

## Exact replacements in `CLAUDE.md.in`

### A. Rule 3, the preprocessing paragraph

Replace:

```text
   **Preprocessing.** Propose `next_action.default_value` unless a result motivates a
   change, named in `motivated_by`. `decide propose` returns `data_contingent` and
   `data_contingent_reason`: when it is true, say that reason's `text` before you present
   the proposal, and say in the restatement that it was chosen after looking at the target
   (the development figures may be slightly optimistic).
```

with:

```text
   **Preprocessing.** Propose `next_action.default_value`, drafted from the quality check
   (`recommended.reasons`; `alternatives` is the comparison), unless a result motivates a
   change, named in `motivated_by`. `decide propose` returns `data_contingent`: when it is
   true, say `data_contingent_reason.junior_text` before you present the proposal.
```

### B. Rule 3, the variants paragraph (its first sentences, up to "model stays.")

Replace:

```text
   **Variants and model families** (ADR 0007). Propose the drafted `default_value` (the
   penalty tuned by nested cross-validation) unless the junior wants another variant:
   **regularisation**, dropping one feature group, or another family. Offer a family
   (`ebm`, `hgb`) only when `model_families.recommendation` is `compare_nonlinear` and you
   have shown the junior the diagnostic flags behind it. In the demo, ask “Pourquoi le
   moteur envisage-t-il une famille non linéaire ?” Answer with the flags, uncertainty,
   limits, why they justify exploration rather than adoption, and the same-protocol
   comparison. Otherwise relay that the linear
   model stays.
```

with:

```text
   **Variants and model families** (ADR 0007). Propose the drafted `default_value` (the
   tuned penalty, with the EBM when the diagnostics flag a pattern) unless the junior wants
   another variant: **regularisation**, dropping one feature group, or another family.
   Offer a family (`ebm`, `hgb`) only when `model_families.recommendation` is
   `compare_nonlinear` and you have shown the junior the diagnostic flags behind it. Name
   families by `junior_words`; relay `not_offered`, and a refused family's
   `details.junior_message`. Otherwise relay that the linear model stays.
```

(The rest of the paragraph, from "At most three variants ever", is unchanged.)

### C. The decision list after the commands block (its first lines, up to `"question"}]}`),`)

Replace:

```text
Decisions, proposed with the drafted `default_value` where there is one:
`prediction_time` (text), `feature_availability` (`{feature: status}`:
`available_at_prediction`, `not_available`, `uncertain_excluded`, `uncertain_included`),
`split`, `success_criterion` (from `criterion_options`), `preprocessing` (`{"missing",
"rare_category_min_rows", "caps", "log_transform", "motivated_by"}`), `model_variant`
(`{"variants": [{"kind": "tuned" | "regularisation" | "drop_group" | "family", ...,
"question"}]}`),
```

with:

```text
Decisions, proposed with the drafted `default_value` where there is one (a refusal's
`details` give the accepted shape): `prediction_time` (text), `feature_availability`
(`{feature: status}`), `split`, `success_criterion` (from `criterion_options`),
`preprocessing`, `model_variant` (each variant with its `question`),
```

## Word delta (raw templates, placeholders unexpanded, as `test_the_instructions_fit_the_word_budget` counts)

| Change | Before | After | Delta |
|---|---|---|---|
| A. preprocessing paragraph | 52 | 37 | −15 |
| B. variants paragraph (first sentences) | 88 | 75 | −13 |
| C. decision list (first lines) | 41 | 33 | −8 |
| **Total, both tasks** | | | **−36** |

The plan's ledger (§2.4) estimated L5 at +30 relayed and −132 freed; this proposal frees less
(−36 net) because the decision list keeps the statuses' context the junior's restatement uses.
No `{{SLOT}}` changes, so the rendered Copilot copy moves by the same −36.

## Pinned phrases

`test_agent_files.py::test_diagnostics_variants_and_r32` pins, in the preprocessing paragraph,
"say that reason's `text` before you present the proposal". Change A replaces it; the
integrator replaces the pinned phrase in the same commit by
"say `data_contingent_reason.junior_text` before you present the proposal", and the behaviour
that moved to the engine is pinned by engine tests of this lot
(`test_l5_recommendations.py::test_the_preparation_digest_explains_the_pipeline_and_the_stamp`:
`junior_text` in the study language, the term first, "not a mistake";
`::test_the_drafted_variants_are_proposed_as_given`: the variant stamp's `junior_text`;
`::test_family_refusal_teaches`; `::test_model_families_junior_words`). Every other pinned
phrase of rule 3 (`**preprocessing**`, `` `next_action.default_value` ``, `` `motivated_by` ``,
`` `data_contingent` ``, `**Variants and model families** (ADR 0007)`,
`` `model_families.recommendation` is `compare_nonlinear` ``, "shown the junior the diagnostic
flags behind it", "At most three variants") is kept, and the binary decision list's
`` `model_choice` (`"fit.logistic"` or a declared variant slot `` is untouched.

## Not proposed

- R12 (D8 a) needs no template words: the calendar-year advisory is in the availability's
  `recommended.why` and in the variant digest, which the agent already relays.
- The skill's "Reading the evidence" bullet on looks at the target stays; the engine's digest
  now introduces the term `target_look` at the preparation.
