# L9 agent-text proposal: the automatic mode, reviewed at the end (R20)

Lot L9 of [OWNER-SESSION-2026-10-26-PLAN](../OWNER-SESSION-2026-10-26-PLAN.md) (§3 L9, §2.4
ledger, D17, D18). The integrator applies this text to
`framework/mlkit/study/agent/CLAUDE.md.in` against the word ledger; L9 does not edit the agent
templates (§1.3). The change is one shared bullet of rule 4 (Claude Code and Copilot copies
alike); no `FLAVOUR_TEXTS` slot changes, nothing in the skill or the resume command.

## What the agent must know, and what the engine already says

The engine carries the automatic mode by itself (CLI-CONTRACT §5.5): the mode is chosen at
`init --automation until_final_test|full_demo` (the owner or the junior creates the study
with it; the agent never sets it later, no command can); `hypotrail automation run` records
every decision it covers with the engine's value (`next_action.auto_value`) and stops by
itself where it must (the final test in `until_final_test`, `done` in `full_demo`, a hold, a
refusal); `next_action` then walks the review (`review: true`, its `junior_message` asking
the junior to adopt or change the decision in their own words); `not_yet_defensible` and the
report carry the banner. So the agent needs only four things: run it with `--progress` and
relay, never record `--basis automatic` itself, recognise a review pause, and record the
junior's "stop". Everything else (the order, the values, the refusals, the texts) is served.

How the agent offers the mode: it does not choose it. When the junior asks for it before the
study exists, the agent creates the study with `init --automation until_final_test` (the
default variant; `full_demo` only when the junior asks for a demonstration that also opens
the final test). Once the study exists the mode can no longer be chosen; the agent says so in
one sentence. This needs no template words: `init` is outside the per-study instructions,
which are installed by `init`.

## Exact insertion in `CLAUDE.md.in`

In rule 4, after the **Delegation** bullet (it ends "... Offer delegation at a pause only,
not ..."), insert this bullet, shared by both tasks:

```text
   - **Automatic mode** (`automation.status` `running`, chosen at `init`). Run
     `automation run --progress`, relay its lines, then its `reason` in one sentence; never
     pass `--basis automatic` yourself. A `next_action` with `review: true` is the review:
     propose its value again and ask the closed question; the junior adopts or changes it.
     Until none is left, the study is not defensible. Their "stop" is `automation stop`.
```

Optional, only if the integrator frees the words (see the ledger), in the **Commands** block
after the `run ACTIVITY` line:

```text
{{HYPOTRAIL}} automation run --progress | stop --user-words "<the junior's words>" --request-id ID --expected-revision REV --study {{STUDY}}
```

## Word delta (measured on `w3-l9`, `af.select_task(...).split()`)

| Task | Before (raw total) | Bullet | Total with bullet | With the commands line too |
|---|---|---|---|---|
| binary | 3,929 | +63 | 3,992 (cap 4,000) | 4,008: over the cap by 8 |
| regression | 3,888 | +63 | 3,951 | 3,967 |

The bullet alone fits (binary headroom 8 after it). The commands line needs 8 more words
freed in the binary copy; the candidate the plan names (§2.4) is the skill's "Resuming"
paragraph, which repeats `/hypotrail-resume`; its pinned phrases (`test_agent_files.py`
lines 251-257: 'A plain "where are we?" gets the same answer as the resume command',
'Objectif', 'Résultats clés', 'at most twelve bullets') must then move with it, with a test of
the resume command that keeps them. The parallel template fixes of this wave (R21, R22) change
the totals; the integrator measures after applying them.

Rendered Copilot copy: the bullet has no slot, so it adds the same 63 words (D18 cap 4,400).

## Pins to add with the text (`test_agent_files.py`)

- In rule 4 of both tasks: '`automation run --progress`', 'never\npass `--basis automatic`
  yourself' (as a flattened phrase: 'never pass `--basis automatic` yourself'),
  '`review: true`', '`automation stop`'.
- The engine side is already pinned by `test_automation.py` (the runner, the review, the
  refusals) and `test_contract_freeze.py::test_l9_automation_contract` (names, keys, payload).
