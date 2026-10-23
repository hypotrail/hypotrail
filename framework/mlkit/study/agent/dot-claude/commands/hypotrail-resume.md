---
description: Resume the study from its recorded state in a short, structured briefing.
---

Resume this Hypotrail study from its recorded state, not from memory.

1. Run `{{HYPOTRAIL}} status --summary --study {{STUDY}}` (`status --json` only for a
   missing detail).
2. Answer from that output only, in the junior's language, with no introduction:
   - **Objectif**: `goal.intended_use` and `goal.prediction_time`.
   - **Décisions**: group related choices; name exclusions; quote the junior's own words
     of the latest confirmation only to disambiguate.
   - **Résultats clés**: at most three figures, with denominator and evidence scope.
   - **État actuel**: current step and outdated deliverables. An
      execution under `executions.suspected_interrupted` (or `outcome_unknown`) stopped
      with an unknown outcome: never say "in progress"; ask before acknowledging it.
   - **Prochaine action**: one action or decision and its default; quote the open
     restatement, preserving "illustrative".
   - **Risques et limites**: at most three, including holds in the junior's words.

   Keep it scannable: at most twelve bullets total. No ids or revision numbers unless the
   junior asks. Never finish by asking whether the Hypotrail panel is open.
3. Run nothing else before the junior answers, and do not say the study is up to date
   unless the summary shows every deliverable `ok`.
