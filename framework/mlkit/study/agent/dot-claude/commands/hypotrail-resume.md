---
description: Resume the study from its recorded state (status, five-line summary, next action).
---

Resume this Hypotrail study from its recorded state, not from memory.

1. Run `{{HYPOTRAIL}} status --json --study {{STUDY}}`.
2. Summarise in at most five lines, from that output only:
   - the moment and the current step (`view.current_step`);
   - the confirmed decisions, quoting the junior's recorded words for the most recent
     one, and any decision that needs reconfirmation or a proposal still waiting;
   - the excluded features, by name;
   - the current results that matter next, each with its `result_id`, and any stale result;
   - each deliverable with its own status (`view.artifacts.items`), and any interrupted
     execution.
3. Propose the next action (`view.next_action`) with a reasoned default, and ask one
   question if a pause needs the junior.

Do not run anything else before the junior answers, and do not say the study is up to date
unless the status shows every deliverable `ok`.
