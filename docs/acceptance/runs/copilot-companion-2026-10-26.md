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
- **R4. English text in the French panel.** Decisions tab, card "Pause 1 · cadrage — Définir le
  moment de la prédiction": the quoted proposal is French, but "En bref :" is followed by
  the English case text ("When the booking is entered in the hotel's property management
  system (the start of lead_time). Known then: …"). Source: the case's default value for
  `prediction_time` in `use-cases/hotel-booking/case.yaml` (line ~100, built by
  `build_case.py`) has no French form, unlike the column dictionary (`fr:`); the panel
  (`media/copy-fr/decisions.js`, `proposedValue`) shows it as is. Likely the same for the
  other case defaults (feature availability, criterion…) and the other cases. To decide: add
  `fr` to the case's decision values and have the engine pick the study language (with the
  panel showing it), or have the panel show the junior-language restatement instead.
  Other direction too: with the panel switched to EN (study in French), the Decisions card
  "Pause 2 · evaluation design" shows the French step title "Découper les données avant de
  les explorer" and the French quoted restatement, under English panel text ("The assistant
  proposes:", "In short: Cross-validation in 5 folds…"). So the panel's language switch
  changes only the panel's own copy, not the engine's texts, which come in the study
  language (step titles, junior messages) or in English only (case values). To decide: the
  engine gives each junior text in both languages (or the panel asks the CLI for its
  language), and the restatement, written by the agent in the junior's language, is labelled
  as the junior's language rather than translated.
- **O3 (R2 works).** The picker appears at pause 1 (prediction moment) and pause 2 (split).
- **R4, update.** The mixed languages are not systematic: some cards are right, some are not.
  To check when fixing: which texts come from the case (English only), which from the engine
  in the study language, which from the agent (junior's language), so each card's mix can be
  explained and fixed rather than sampled.
- **R3, second case.** After the four framing decisions, the recap turn ("Les quatre décisions
  de cadrage sont enregistrées…") ends with "La prochaine étape est l'exploration de
  l'échantillon de développement… On continue ?" in text, with no picker (then the panel
  line). Same pattern as step 0: a transition between moments, not a decision pause. So R3
  covers every closed "go on?" question at a step change, not only step 0.
- **R4, EDA card.** Data & EDA tab, panel in French: the card "Valeurs spéciales · lignes de
  développement" has an English question as its title ("How many development rows carry each
  special value, and how does the outcome look among them?"; engine text,
  `framework/mlkit/study/eda.py` ~587-598, the per-activity questions, English only), while
  the chart title and the table headers are French (panel copy). The table's "Sens" column
  shows the case's English `meaning` of each special value (`case.yaml` ~404-411, e.g. "No meal
  package. The dictionary groups…"), with no French form, unlike the column dictionary.
  Probably every EDA card's question and every special-value meaning, in every case.
- **R5. The preprocessing recommendation ignores what the quality check found.** Step 5: the
  agent recommends "la préparation par défaut, sans transformation" (no missing indicator,
  no rare grouping, no cap, no log) although the quality overview it shows reports skew and
  extreme values (`lead_time` 0 to 737 days, very high `adults` and `stays_in_week_nights`)
  and many rare categories in `agent` and `company`; and the quality overview (`eda.quality`,
  target-free) ran only because the owner asked for it.
  Why, in the code: `state._propose_action` always drafts `governance.DEFAULT_PREPROCESSING`
  (`{'missing': 'none', 'rare_category_min_rows': 0, 'caps': {}, 'log_transform': []}`),
  "what the models did before the decision existed, so results stay comparable"; nothing
  reads the quality results to draft a value. The fixed pipeline under it (median imputation
  and scaling of numbers, most-frequent imputation and one-hot encoding of categories,
  `code_cells.py`) is never shown as "what already happens". The default EDA runs only
  `eda.target_summary` and `eda.special_values`, not `eda.quality`.
  Why it matters: one-hot on thousands of rare `agent`/`company` codes, an untransformed
  heavy-tailed `lead_time`, and implausible extremes are exactly what a junior should learn
  to treat; a recommendation that ignores the check it just showed teaches the opposite.
  Proposed: run `eda.quality` by default before the preprocessing pause (target-free, so the
  draft is not data-contingent on the target); draft a recommendation from it (rare grouping
  for high-cardinality columns, signed log for strongly skewed positive numbers, caps for
  implausible extremes), each with its reason and `motivated_by` the quality result; keep
  the default as the comparison option; and say what the fixed pipeline already does.
  Also: the restatement "choisie après avoir regardé la cible" reads as a reproach; it is the
  `data_contingent` stamp and needs an explanation, not a bare clause.
- **R2b. After a picker left unanswered, the agent falls back to text for good.** At step 5
  the picker was not answered (closed, or the owner typed in the chat instead); the next turn
  opens with "Rien n'est encore enregistré pour la préparation des variables, puisque la
  question a été ignorée.", repeats the whole pause (quality findings, recommendation,
  quoted block, "Adoptez-vous cette décision ?", panel line) and ends in text, without the
  picker. The agent read the dismissed picker as "the call fails", which the R2 fix allows
  as the text fallback. To fix: a dismissed or unanswered picker is not a failed call; when
  the junior writes instead, read the reply (it may answer the question), and when the pause
  must be asked again, call the picker again. Only a tool error or a missing tool falls back
  to text. Also: "la question a été ignorée" reads as a reproach; say nothing was recorded
  and ask again.
- **O4 (positive).** After "Changer quelque chose", the owner asked "regrouper les catégories de
  agent et company sous 30 lignes, log de lead_time, plafonner adults". The new proposal came
  with the picker, said plainly what the engine cannot do as asked, chose a cap value and said
  it can be changed, and disclosed that the choice comes after two looks at the target.
- **R6. Rare grouping is global, not per column.** `rare_category_min_rows` is one integer for
  every kept categorical column (`governance.PREPROCESSING_KEYS`), so "group the rare codes of
  `agent` and `company`" becomes "every categorical column"; caps are per column, the log is
  per column. To decide: a per-column form (e.g. `{column: min_rows}`), as for caps and
  logs, so a junior's targeted choice can be recorded as asked.
- **R7. The preparation is stamped "after looking at the target" because of the EDA order.**
  The proposal says "Ce choix vient après 2 regards sur la cible. Il peut rendre les chiffres
  de développement un peu optimistes". The owner's choice is motivated by the quality check
  (target-free), but WP-A9 M1 stamps `data_contingent` whenever any target-involving look
  preceded the proposal, and the default exploration starts with two target looks
  (`eda.target_summary`, `eda.special_values` with outcome rates). So every study's
  preparation is data-contingent by construction. Linked to R5: run the target-free
  structural checks (`eda.quality`, distributions without the target) first and decide the
  preparation from them before any target look, then explore the target; or keep the order
  and explain the stamp in one sentence the junior can act on.
- **R8. `reports/study.html` is not clear enough; it should read as an explanation.** The owner
  finds the report hard to follow. Asked:
  - navigation: categories, an index, or a table of contents on the left;
  - a narrative, explanatory document: read like the notebook of someone who explains the
    study end to end (the approach and the design choices, in order), built with its evidence
    inline at the point where each argument needs it, rather than a list of decisions with
    the evidence gathered further down.
  To decide when fixing: the narrative order (question and data, framing, how it is
  evaluated, what the exploration showed, how the variables are prepared and why, the
  models and their comparison, the rule, the final test, the conclusion and its limits),
  each section stating the choice, why, the evidence (chart or figure with its result id),
  and what remains uncertain; a sticky left table of contents that works offline and on a
  narrow screen; the verdict card kept first; `hypotrail check` number tracing kept; the
  annex for raw tables.
- **R3, third case.** After the preparation is recorded, the turn ends with "La suite consiste
  à ajuster le modèle de référence, puis le modèle logistique … On lance les modèles ?" in
  text, no picker.
- **R1b. The panel line points to an empty place.** Same turn: "Dans le panneau : onglet
  Décisions." while the Decisions tab shows "En attente de votre réponse — Rien n'attend votre
  réponse" (the recorded preparation is only in "Historique des décisions", further down).
  The line must point where there is something to see for this message: after a
  confirmation, the decision history (name the section) or nothing; before running the
  models, the tab where their results will appear (Evidence) once they exist. To fix: compute
  `where` from what the message shows (the result or decision just produced) rather than
  from the next step's kind alone, name the section, not only the tab ("onglet Décisions,
  Historique des décisions"), and give no line when nothing new is shown. Check whether the
  agent used `next_action.panel.where.line` or its own rule-6 mapping here.
- **R9. No progress narration during long runs.** While the models run, the chat shows only
  "Ran uv run --project …", "Read content.txt", "Evaluating": nothing says what is being done.
  The owner wants, for each major step, a short line before it ("Je vais maintenant ajuster
  le modèle de référence", "je passe au modèle logistique") and the intermediate result after
  it ("le modèle de référence obtient …").
  Cause: the round-9 Copilot rule (R9UX-1 `RUN_NOTICE`) moves every run announcement to the
  final message of the turn, "never before a tool call", to avoid the folded-reasoning bug;
  so during the turn nothing is written.
  To fix: separate progress from content. Progress lines before and between tool calls are
  allowed (they are visible live while the turn runs, folded afterwards), one short line per
  major step and one per intermediate result; everything the junior must keep (the results,
  the pause, the question) is repeated in the final message or the picker. Also consider the
  `todo` tool (already in the agent's tool list): a visible checklist of the turn's major
  steps (baseline, logistic model, diagnostics) updated as each one finishes.
