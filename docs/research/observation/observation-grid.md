# Observation grid

Part of the [observation protocol](../OBSERVATION-PROTOCOL.md), §5 and §9. One grid per participant. Fill the "During" columns live with the time on the session clock (or the recording timestamp); complete the rest within two days. Write what you saw and heard, not what you inferred; put interpretations in "Notes".

Participant: P__ · Day 1: ____/____ __:__–__:__ · Day 2: ____/____ __:__–__:__ (delay: ___ h) · Facilitator: ______

Codes for the "Signals" column (combine as needed):

| Code | Meaning |
|---|---|
| `Q` | asks the assistant a question (quote the gist) |
| `F` | asks the facilitator something |
| `C` | visible confusion, hesitation over 20 s, or "I don't understand" |
| `R` | retypes a reply after a refusal ("ok" not accepted, own words asked for) |
| `D` | delegates ("use your recommended default", "you choose") |
| `T` | trusts a figure without checking ("ok, 11 %", moves on) |
| `V` | verifies: asks where a figure comes from, or opens the report or notebook to check |
| `O` | opens a deliverable (say which: report, generated notebook, workbench) |
| `M` | the assistant repeats the same option menu as in its previous turn |
| `X` | the assistant goes off-script (computes in prose, writes a script, asks for something outside the study) |
| `+` | positive remark ("that's useful", "now I get it") |
| `-` | negative remark ("this is annoying", "why again?") |
| `I` | facilitator intervention (which one, from §6) |

## During the session

| Task | Start | End | Signals (with times) | Think-aloud quotes (short, with times) | Notes |
|---|---|---|---|---|---|
| T1 Intent | | | | | |
| T2 Pauses 1 and 2 | | | | | |
| T3 Exploration | | | | | |
| T4 Models | | | | | |
| T5 Policy | | | | | |
| T6 Capacity 100 | | | | | |
| Deliverables prompt | | | | | |
| T7 Day 2, new chat | | | | | |
| T8 Conclusion | | | | | |

## Per pause

Fill from the notes, then check against `hypotrail session-report` (`pauses`, `decisions`, `refusals`).

| Pause | Decisions | Time from proposal to confirmation | Refused confirmations (reasons) | Delegated? (scope) | Read the restatement aloud? | Felt useful / in the way (quote) |
|---|---|---|---|---|---|---|
| 1 | prediction moment, feature availability | | | | | |
| 2 | split | | | | | |
| 3 | policy, conclusion | | | | | |

## Deliverables

| Deliverable | Opened? | When (task, time) | Prompted or unprompted | What they looked for | What they said |
|---|---|---|---|---|---|
| `reports/study.html` | | | | | |
| `notebooks/study_generated.py` | | | | | |
| `notebooks/workbench.py` | | | | | |

## Specific checks

| Check | Observed? | Time | Evidence |
|---|---|---|---|
| Asked why `duration` (or a last-contact column) is excluded | | | |
| Expected a refit when the capacity changed | | | |
| The assistant said the model is unchanged on the capacity change | | | |
| The assistant stated which rows the 100 calls apply to | | | |
| Used `/hypotrail-resume` or asked "where are we?" on day 2 | | | |
| Day-2 recap gave the goal, the decisions (excluded features named), the position, the next decision, one limit | | | |
| Recalled the excluded features unaided on day 2 | | | |
| Called people not selected "lost sales" or used causal wording | | | |
| Read the "What is not yet defensible" section | | | |
| Repeated a number in words that the assistant computed ("one in nine") | | | |

## After the session

- Comprehension test score: __ / 14 (see the [scoring sheet](comprehension-test.md#scoring-sheet)).
- Confidence rating (debrief): __ / 7. What would raise it: ______________________
- Three strongest observations (with times):
  1.
  2.
  3.
