---
description: Resume the study from its recorded state (goal, position, next decision, in five lines).
---

Resume this Hypotrail study from its recorded state, not from memory.

1. Run `{{HYPOTRAIL}} status --summary --study {{STUDY}}`. Use `status --json` only if a
   detail you need is missing from the summary.
2. Answer in plain words, in at most five lines, from that output only:
   1. **The goal first**, in one sentence: what the study is for (`goal.intended_use`)
<!-- hypotrail:task binary -->
      and the moment the prediction is made (`goal.prediction_time`), for example "We
      are ranking clients to call first when calls are limited, predicting before the
      call."
<!-- hypotrail:task regression -->
      and the moment the prediction is made (`goal.prediction_time`), for example "We
      are estimating a number for new rows, in its unit, once their characteristics are
      known."
<!-- hypotrail:end -->
   2. **Where we are**: the step in plain words (its title, not its id) and what was
      last decided, quoting the junior's recorded words for the most recent decision.
      Say if a decision was delegated to your default, needs reconfirmation, or waits
      for their answer.
   3. **What matters next**: the excluded features by name, the results the next step
      uses (cite figures with their `result_id`), and any stale result or interrupted
      execution. An execution under `executions.suspected_interrupted` (or
      `next_action.kind` `outcome_unknown`) stopped with an unknown outcome: say so,
      never "in progress", and ask before acknowledging it.
   4. **The deliverables**: each one's status in a few words (repeat its `message` if it
      is not up to date).
   5. **The next decision or action** (`next_action`) with your recommended default, and
      one question if a pause needs the junior.

   Do not show proposal ids, request ids, execution ids, or revision numbers unless the
   junior asks for them; a `result_id` goes only next to a figure it backs.
3. Do not run anything else before the junior answers, and do not say the study is up to
   date unless the summary shows every deliverable `ok`.
