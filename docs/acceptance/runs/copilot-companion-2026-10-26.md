# Owner session notes: Copilot chat + study panel, 2026-10-26

Owner test of the chat-plus-panel walkthrough on Hotel booking demand (Resort Hotel), GitHub
Copilot agent **Hypotrail** in VS Code, panel flag on at stage v3, branch
`claude/zealous-franklin-gywbya` at `d59f0c4`. Notes only: nothing below is implemented yet.

## Observations

- **O1 (positive).** Step 0 ("Je veux faire cette étude, par où on commence ?"): the data card
  is visible after "Completed 10 steps", not folded into the collapsed reasoning (the
  round-9 Copilot fix holds on this message). Terms introduced before their explanation
  (development rows, final test), plan in four moments, no proposal in the same message.

## Remarks to address

- **R1. The chat must say, every time, where to look in the panel.** After each message that
  shows or changes something (data card, a proposal, a confirmation, a chart, a fit, the
  diagnostics, the final test, the deliverables), the chat ends with one line naming the
  panel tab and section that shows it, for example "Dans le panneau : Données et EDA → fiche
  des données".
  Design notes (to decide when implementing):
  - The chat, report, and notebook workflow must stay complete without the panel (AGENTS.md),
    so the line appears only when the panel is on: the CLI can read `HYPOTRAIL_COMPANION`
    and `HYPOTRAIL_COMPANION_STAGE` (the agent's terminal inherits VS Code's environment), or
    `hypotrail.companion.enabled` / `.stage` in the study's `.vscode/settings.json`.
  - The hint must name only tabs that exist at the stage (v0 one page; v1 Decisions; v2 Data
    & EDA, Evidence, What if?; v3 Learn & hand off), with the panel's own labels in the study
    language (`clients/vscode-companion/media/copy*/core.js`), checked by a test.
  - Likely shape: an optional `panel_hint` (tab, section, ready sentence) in command results
    and `next_action`, and one instruction line "end your message with its sentence". The
    agent word budget is full (4000), so some words must be freed.
  - It couples the engine to the panel's layout: record it in CLI-CONTRACT-COMPANION and check
    whether ADR 0004 needs an amendment (it does not widen the panel's writes).
- **R2. No picker at the first decision.** At the start (the first proposal, after the data
  card) Copilot did not offer the choice picker (`vscode/askQuestions`); the owner had to type
  the answer by hand. To investigate: whether the turn that proposes the first decision
  calls the picker at all (agent file and `copilot-instructions.md`), whether the step-0 turn
  ends the pause in text by design, whether the tool was enabled in the chat tools picker, and
  whether the Hypotrail agent (not the default Agent mode) was selected.
