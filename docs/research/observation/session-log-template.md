# Session log: P__

Part of the [observation protocol](../OBSERVATION-PROTOCOL.md), §3 and §9. One log per participant, kept **outside the repository** with the other session data. Only a pseudonymised summary may be committed, with the participant's agreement.

## Setup

| Item | Value |
|---|---|
| Participant | P__ (screening answers below; no name) |
| Day 1 date and time | |
| Day 2 date and time (delay in hours) | |
| Facilitator, second scorer | |
| Machine (fresh account or machine?) | |
| Repository commit | `git rev-parse HEAD` |
| Claude Code version, model | `claude --version`; model shown in the session |
| uv version | `uv --version` |
| Study path (outside the repository) | |
| Session log on before T1? | `test -f <study>/.hypotrail/session-log.jsonl` |
| No user-level `CLAUDE.md`, skills, or memory? | checked ☐ |
| Consent choices (from the form) | study folder ☐ conversation ☐ screen ☐ audio ☐ quotations ☐ |

Screening answers (§2): 1. ___ 2. ___ 3. ___ 4. ___ 5. ___

## Timeline of the session

Facilitator notes in time order. Times are on the session clock (or the recording). Use the codes of the [observation grid](observation-grid.md).

| Time | Task | What happened | Code |
|---|---|---|---|
| | | | |

Interventions (§6):

| Time | Situation | Words used (standard unblock?) | Time lost |
|---|---|---|---|
| | | | |

## Engine record

After day 2, run and store next to this log (not in the repository):

```sh
uv run --project $REPO/framework hypotrail session-report --study $STUDY --format text > report-P__.md
uv run --project $REPO/framework hypotrail session-report --study $STUDY > report-P__.json
```

Copy the key figures here:

| Figure | Value |
|---|---|
| Span (first to last event) and revisions | |
| Idle gaps (should show the day break) | |
| Pause 1 / 2 / 3 elapsed time | |
| Refused confirmations, by reason | |
| Other refusals, by code | |
| Decisions delegated (and scope) | |
| `check` runs, and `untraceable_number` findings (in words: how many) | |
| Final step reached; deliverable statuses | |

## Issue log

One row per problem. **Evidence** is what was seen or said, quoted or described; **Where** is the transcript or recording timestamp, or the `session-report` timeline line. Severity uses the protocol's 0–4 scale (§9). **Cause** is the suspected part: `instructions` (the agent's `CLAUDE.md`, skill, or resume command), `engine` (a refusal, a missing feature), `deliverable` (report, notebook), `content` (glossary, step texts), `case` (Bank documentation), `agent` (model behaviour against its instructions), or `protocol`.

| Id | Task | Problem (one sentence) | Evidence | Where (timestamp) | Severity | Cause | Seen in (P1, P2, P3) | Recommendation |
|---|---|---|---|---|---|---|---|---|
| P__-01 | | | | | | | | |
| P__-02 | | | | | | | | |

## Comprehension and debrief

- Test: Q1 _ Q2 _ Q3 _ Q4 _ Q5 _ Q6 _ Q7 _ = __ / 14 (scorers: ___, ___; differences discussed: ___).
- Debrief answers (§8), one line each:
  1.
  2.
  3.
  4.
  5.
  6.
  7.
  8.
- Confidence: __ / 7. What would raise it by one point:

## Data handling

| Item | Kept where | Delete by | Deleted on |
|---|---|---|---|
| Notes, grid, test, this log | | | |
| `report-P__.md`, `report-P__.json` | | | |
| Study folder (only with consent) | | | |
| Conversation copy (only with consent) | | | |
| Recordings (only with consent) | | | |
