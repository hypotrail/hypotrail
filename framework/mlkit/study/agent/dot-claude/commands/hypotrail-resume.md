---
description: Resume the study from its recorded state (goal, decisions, position, next decision, one limit, in five lines).
---

Resume this Hypotrail study from its recorded state, not from memory.

1. Run `{{HYPOTRAIL}} status --summary --study {{STUDY}}` (`status --json` only for a
   missing detail).
2. Answer in at most five lines, from that output only, in the junior's language. The
   summary's `recap_junior` holds these five lines, generated from the state: quote it.
   1. **The goal first** (`goal.intended_use`, `goal.prediction_time`).
   2. **Decisions made**, with the excluded features by name and the junior's own words of
      the latest confirmation in quotation marks; say if one was delegated or needs
      reconfirmation.
   3. **Where we are**: the step title, and any deliverable that is not up to date. An
      execution under `executions.suspected_interrupted` (or `outcome_unknown`) stopped
      with an unknown outcome: never say "in progress"; ask before acknowledging it.
   4. **The next decision** and your recommended default; quote an open restatement as
      recorded, keeping "illustrative" for a stand-in figure, and a hold in the junior's
      words.
   5. **One limitation**: the first the recap names.

   Five flat lines. No ids and no revision numbers unless the junior asks for them.
3. Run nothing else before the junior answers, and do not say the study is up to date
   unless the summary shows every deliverable `ok`.
