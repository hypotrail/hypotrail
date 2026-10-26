# Owner session notes: Copilot chat + study panel, 2026-10-26

Owner test of the chat-plus-panel walkthrough on Hotel booking demand (Resort Hotel), GitHub
Copilot agent **Hypotrail** in VS Code, panel flag on at stage v3, branch
`claude/zealous-franklin-gywbya` at `d59f0c4`. R1 and R2 are fixed since (see Fixes); the
fixes are tested by unit tests only, not yet in a real Copilot session.

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
  Update: this is general, not only the first decision. At the prediction-moment pause
  (second message) the agent again ended in text: the term, its explanation, the quoted
  decision block, then "Adoptez-vous cette décision ? Vous pouvez l'adopter, changer quelque
  chose ou me demander d'abord une explication." No picker appears at any pause; typing is
  the only option. The content itself is right and visible (not collapsed).
  Lead: the earlier owner session that saw the picker, with its text folded above it, ran
  before `0065fcd` (that commit fixed the folding); it says nothing about the picker after
  that commit. The likely cause is the wording of the round-9 rewrite (R9UX-1/R9UX-2,
  `90e89e4`): it offered several text endings (the "Without the picker, ask in text"
  fallback, "explain first" answered in text, the skill's pause message described as a
  text message), and the agent took one at every pause. Check the generated
  `.github/agents/hypotrail.agent.md` and `.github/copilot-instructions.md` for wording that
  makes the text form look like the default, and confirm the tool is still offered to the
  agent in that session (chat tools picker).

## Fixes

Branch `r1r2`, commit "Fix R2 (Copilot picker at every pause) and R1 (panel tab line)".
Unit tests only: no real Copilot or VS Code session has been run with these fixes.

- **R2, fixed.** For Copilot only (the Claude Code instructions are unchanged), every pause
  turn ends with the `#tool:vscode/askQuestions` call, never in plain text: its question
  holds the whole pause message of the skill (at most 150 words), "explain first" calls the
  picker again, and the text form is only the fallback when the call fails or the tool is
  missing (`copilot-agent.md.in`; the Copilot slots of `CLAUDE.md.in` and of the skill's
  "One pause, one message" in `agent_files.FLAVOUR_TEXTS`). Tests:
  `test_agent_files.py::test_copilot_ends_every_pause_with_the_picker`,
  `::test_the_r2_fix_leaves_the_claude_code_copy_unchanged`.
- **R1, fixed.** When the panel is on (`HYPOTRAIL_COMPANION=1`, or
  `hypotrail.companion.enabled` in the study's `.vscode/settings.json`), every
  `next_action` carries `panel`: the stage, the panel's tab labels at that stage in the
  study language, and `where` the current step is shown, with a ready line ("Dans le
  panneau : onglet Données et EDA."). Rule 6 of the agent instructions now triggers on it
  and ends each message that shows or changes something with that line (with Copilot, the
  last line of the picker question). Absent when the panel is off. Section labels (for
  example "fiche des données") are not given: tabs only. Engine: `mlkit/study/companion_env.py`;
  contract: CLI-CONTRACT §3.2; ADR 0004 amendment note 10. Tests:
  `framework/tests/study/test_companion_env.py`,
  `clients/vscode-companion/test/test_panel_labels.py`.

## Second session (after the fixes, `748bd8b`)

- **O2 (R1 works).** The step-0 message (data card) ends with "Dans le panneau : onglet
  Données et EDA.", the agent being Hypotrail with the panel flag on.
- **R3. No picker at step 0 either.** The data-card message ends with an open question in
  text: "La prochaine étape consiste à définir le moment de la prédiction. On y passe ?".
  Step 0 is not a decision pause (no proposal in that message, by design), so the R2 fix
  does not cover it; the owner expects a picker for every question that asks the junior to
  choose or go on. To decide: with Copilot, end every turn that asks the junior something
  closed (go on / ask a question about the data, and the like) with the picker too, not only
  decision pauses. Whether the picker now appears at the first decision pause (R2) is not
  yet observed.
