---
description: Resume the study from its recorded state (goal, decisions, position, next decision, one limit, in five lines).
---

Resume this Hypotrail study from its recorded state, not from memory.

1. Run `{{HYPOTRAIL}} status --summary --study {{STUDY}}`. Use `status --json` only if a
   detail you need is missing from the summary.
2. Answer in plain words, in at most five lines, from that output only. The summary's
   `recap` holds these five lines, generated from the state: quote it, adding a
   `result_id` only next to a figure you add.
   1. **The goal first**, in one sentence: what the study is for (`goal.intended_use`)
      and the moment the prediction is made (`goal.prediction_time`), for example "We
      are ranking clients to call first when calls are limited, predicting before the
      call."
   2. **Decisions made**: each confirmed decision in a few words, with the
      excluded features by name; say if one was delegated to your default or needs
      reconfirmation.
   3. **Where we are**: the step in plain words (its title, not its id), and any
      deliverable that is not up to date. An execution under
      `executions.suspected_interrupted` (or `next_action.kind` `outcome_unknown`)
      stopped with an unknown outcome: say so, never "in progress", and ask before
      acknowledging it.
   4. **The next decision** (`next_action`) with your recommended default and one
      question if a pause needs the junior. Quote an open restatement as recorded: if it
      uses a stand-in figure, keep the word "illustrative".
   5. **One limitation**: the first limit the recap names.

   Do not show proposal ids, request ids, execution ids, or revision numbers unless the
   junior asks for them; a `result_id` goes only next to a figure it backs.
3. Do not run anything else before the junior answers, and do not say the study is up to
   date unless the summary shows every deliverable `ok`.
