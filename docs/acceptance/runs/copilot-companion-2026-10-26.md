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
- **R3, fourth case.** After the fits and diagnostics, the turn ends with "Prochaine étape :
  choisir les variantes à comparer … On passe à ce choix ?" in text, no picker. Every step
  change so far (step 0, after framing, after preparation, after the fits) ends this way:
  R3 is systematic at transitions. The same message also says "Il y a eu 3 regards sur la
  cible." with no explanation of what that means for the junior (see R7).
- **R10. Long runs show no progress at all.** In the terminal the agent runs
  `hypotrail run fit.variant:2 --request-id … --expected-revision 32 --study … 2>/dev/null`
  and nothing appears until it ends. The owner wants slow work to be visibly progressing
  (fold by fold, variant by variant), more informative during training, without
  uninteresting technical detail.
  Causes: the engine writes no progress while it computes (only the final JSON on stdout;
  `executions.py` has no progress reporting), and the agent hides stderr with `2>/dev/null`
  (not asked by the instructions, which never mention stderr).
  To fix: the engine reports progress on stderr in plain words, one line per unit of work
  (for example "Modèle logistique · pli 2/5 · 14 s", "Variante 2/3 · recherche de la pénalité
  3/8"), with a progress bar when the terminal is interactive (tqdm, or the same lines when
  not), never mixed into the stdout JSON; the agent instructions say not to discard stderr;
  the agent relays the major steps in chat (R9). Check the panel's CLI calls ignore stderr
  progress cleanly.
- **R11. Only the last variant's analysis appears in the panel.** Two variants were chosen and
  fitted: a penalised logistic model (penalty chosen by nested cross-validation) and an EBM.
  Evidence shows "Deuxième variante · Boosting explicable" (term importances, the shape of
  `lead_time`) but no analysis of the first variant. To check: whether the engine keeps
  variant 1's result current after variant 2 is fitted, or the panel's Evidence model shows
  only the last variant slot; every compared variant needs its own card (coefficients or
  terms, its CV figures beside the logistic model's).
- **R12 (modelling, to discuss).** The EBM ranks `arrival_date_year` among its terms (0.200)
  under a temporal split. With temporal folds the validation years are later than the training
  years, so a year term can only extrapolate (or learn a trend the future may not follow); on
  the final test (the latest period) its effect is a guess. The engine or the agent could
  flag calendar-year predictors under a temporal split at the feature-availability or
  preparation step (keep the season, month and week; question the year).
- **R13. The drafted variant ignores the diagnostics' signals.** By default only the penalised
  logistic model (penalty by nested CV) is drafted; the EBM was added because the owner chose
  it after the agent said the engine "juge aussi justifié" a non-linear family. Cause, by
  design: `trials.draft` always drafts one `tuned` variant (WP-F1, V0.3-DECISIONS F1.1–F1.7:
  the candidate stays linear, a family change is an optional variant in the budget of three).
  Issue: with 32 049 rows and a few dozen predictors, tuning the penalty usually changes
  little (the data dominate the penalty), so the default comparison carries little
  information, while the diagnostics had just flagged non-linear `lead_time` and behaviour
  varying by arrival month and meal plan. Proposed: when the diagnostics flag
  non-linearity or interactions, draft the tuned penalty plus one readable non-linear family
  (EBM), each with the signal that motivates it; draft the penalty alone only when nothing is
  flagged; say the cost (each variant spends one trial of three and adds selection optimism).
- **R14 (wording).** The owner asked whether Random Forest or XGBoost should be offered. The
  engine already has a histogram gradient-boosting family (`hgb`, scikit-learn's
  HistGradientBoosting, the same algorithm family as XGBoost and LightGBM), but the junior
  does not recognise it under that name. Name it as such when the variants are offered
  ("boosting d'arbres, du même type que XGBoost"), and say in one line why a random forest is
  not offered (usually below tuned boosting on tabular data, and a variant of the same kind
  spends a trial for little new information).
- **R15. A model outside the catalogue (SVM, k-NN, a neural network…) gets a bare refusal.**
  The owner asked what happens when the junior asks for a really different model. The engine
  refuses a `family` variant outside `trials.VARIANT_FAMILIES` (`ebm`, `hgb`) with
  `invalid_value` "family is one of ebm, hgb (the linear model is the candidate)"
  (`framework/mlkit/study/trials.py` ~268); nothing is recorded and no trial is spent. The
  catalogue is closed on purpose: each family needs a fixed nested-CV grid, a trial in the
  budget, a code fingerprint and attestation, notebook cells that recompute it, one final-test
  evaluation, and export packaging.
  Missing for the junior: the refusal should say why the catalogue is closed (in their words,
  not the code's), offer the closest family that is available and why, and point to the
  workbench (`notebooks/workbench.py`, development training rows only) for a personal
  exploration that is not study evidence (not compared, not chosen, not final-tested, not in
  the report as a result). Never walked end to end: add an acceptance scenario (the junior
  asks for an SVM) and check the agent's answer, the engine's message, and the workbench
  starter cell. Adding a family remains framework development (k-NN or a small neural
  network would be more useful for teaching than a kernel SVM, which is slow on 32 000 rows
  with nested CV and needs calibration for probabilities).
- **R16. The chat waits for an answer while the panel says nothing waits.** At the
  conclusion, after the final test (development AUC 0.807 → final 0.783, recall 30.2 % →
  21.6 %, cancellation share 25.9 % → 35.3 %), the chat asks "Que concluez-vous parmi ces trois
  options ?" (adopt the rule, keep the baseline, do not conclude), while the panel's
  Decisions tab says "En attente de votre réponse — Rien n'attend votre réponse. L'assistant
  propose les décisions dans le chat." Cause: when `recommended` is null (conclusion, model
  choice) the agent asks the junior to choose before any proposal exists, so the engine has
  no open proposal and the panel shows nothing pending. To fix: the panel shows the step
  that waits for the junior's choice even before a proposal ("La conclusion : l'assistant
  vous demande de choisir dans le chat", with the engine's allowed verdicts from
  `next_action`), and the panel line names that card.
- **R2c. No picker at a free choice.** The same conclusion question lists its three options
  as text bullets and ends without the picker. The R2 fix covers the adopt/change/explain
  pause; a choice among the engine's options (conclusion verdicts, model choice, variants)
  should use the picker too, one option per allowed value with the junior's own words, no
  option marked recommended when `recommended` is null.
- **R17. A wrong limit in the closing message.** After the conclusion the agent lists the
  report's limits, among them "Ni colonne de temps ni identifiant d'entité : l'étude ne peut
  pas vérifier une dérive dans le temps, ni des entités répétées entre les échantillons." The
  Hotel study has a time order: its final test is temporal (`init`: `"method": "temporal"`)
  and its split uses temporal folds; the final test even shows the period effect
  (cancellation share 25.9 % → 35.3 %). To check: which `not_yet_defensible` item says this
  (probably the limit keyed on `structure.time_column` being absent while the case declares
  an order instead), and make it follow the case's declared order; the entity part may be
  right (no guest identifier).
- **Next step asked by the owner: "comment lancer le déploiement".** The closing message
  does not say what comes after the study (export, capture with packaging, deployment
  status). See the answer in the session; to decide whether the agent should offer the
  Azure ML export (`hypotrail export azureml --plan`) at `done`, with the honest status
  (no Azure job or endpoint has ever been run).
- **R18. `export azureml` without `--expected-revision` gives an unclear refusal.**
  `hypotrail export azureml --study … --plan --format text` answers "refused
  (invalid_arguments): --expected-revision must be a revision number." with remediation "Read
  the revision with hypotrail status first." The flag is required by contract (§15: the export
  reads exactly one revision), but the message reads as if a value were malformed, and the
  user has to run another command to find the number. To fix: say the flag is required, and
  name the current revision in the message and in `details` (the command already reads the
  study), e.g. "--expected-revision is required: the study is at revision 41; add
  --expected-revision 41". Also: the owner's shell had another project's `VIRTUAL_ENV`
  active, and uv warned and ignored it; harmless, but worth one line in the export docs.
- **R19. The discovery case cannot be exported.** `export azureml --plan` on the finished Hotel
  study refuses: "This template does not qualify the binary family 'logistic' with output
  'binary_score'" (`capability_not_supported`); the support matrix of team-azureml-v1 is
  regression `linear` only (`AZUREML-EXPORT-V1.md` §10). So the v0.3 discovery case (Hotel,
  binary) and Bank Marketing cannot reach the export at all; only Auto MPG (regression,
  linear model chosen) can. Nothing says so before the junior gets there: not the agent at
  `done`, not the panel, not the README. (My demo instructions also suggested exporting the
  Hotel study.) To decide: qualify the binary logistic family (output `binary_score`, the
  rule kept as metadata), then EBM/HGB, or state the matrix up front (agent at `done`, the
  report, the panel's hand-off tab) and offer the export only when the chosen model is
  supported. Also seen: running the export on the wrong study (another `$STUDY`) gave
  "no recipe of a selected model … final test is sealed": correct, but the message could
  name the study path and its revision so a wrong folder is obvious.
  **Fixed (2026-10-26, branch `r19`)**: team-azureml-v1 now qualifies binary `logistic`
  with output `binary_score` (the positive-class score), locally: native and MLflow pyfunc
  parity on a synthetic binary study taken through the engine (a regularised variant
  chosen, rule `capacity:40@fit.variant`, `predictor.capture --profile workshop`, final
  test opened), then `export azureml --plan` and `--out`, and in the moved project
  `validate --offline`, `predict`, `materialize`, `run-local`, its pytest and ruff
  (`framework/tests/exporters/azureml/test_binary_logistic.py`). A tuned, regularised or
  drop-group logistic variant is still `logistic`; EBM and histogram boosting stay refused
  (`capability_not_supported`, `details.reason: family_not_supported`). The adopted rule is
  carried as metadata (snapshot, `readiness.json`, README) and never applied in the model
  output. **Azure itself is still not qualified** (no job, no endpoint), and the Hotel and
  Bank studies themselves were not exported in that change. Not addressed here: stating the
  matrix up front (agent at `done`, report, panel) and naming the study path in the
  wrong-study message ([AZUREML-EXPORT-V1](../../handoff/AZUREML-EXPORT-V1.md), R19).
- **R20. A fully automatic mode, reviewed at the end (owner request).** The owner wants a
  mode where the assistant makes every choice and the junior reviews them at the end.
  Owner decision (2026-10-26): both variants, chosen at launch: "auto until the final test"
  (default: every decision and computation up to the model and the rule, each recorded as
  automatic and to review; the junior then adopts or changes each one in their own words and
  opens the final test themselves) and an explicit "full auto (demo)" that also opens the
  final test and concludes, with a report banner "automatic study, not defensible until
  reviewed" and every later change marked as made after the final test. This amends ADR 0005
  (confirmation modes) and the rule that the final-test opening is never delegated, for the
  demo variant only.
  Fixed (lot L9, integrated on `w3-int`): `init --automation until_final_test|full_demo`,
  the basis `automatic` (never the junior's words nor a delegation), `hypotrail automation
  run [--progress]` that follows `next_action` through the engine's own commands (the
  capture before the opening included, with its options) and honours every refusal, the
  review walked by `next_action` (`review: true`), `automation stop --user-words`, the
  banners in the report, the notebook and the panel; ADR 0005 and 0006 amendments,
  CLI-CONTRACT §5.5. Rule 4 of the agent instructions has the automatic-mode bullet. Unit,
  walker and in-process CLI tests on Auto MPG; not run with Copilot (J-A to rehearse).

## Third session (after the batch, `7c0213f`)

- **O5 (positive).** Step 0 now ends with the picker "On regarde ensemble la fiche des
  données ?", its question holding the data card (groups, the columns of uncertain timing,
  an example row), and the panel line names the section: "Dans le panneau : Données et EDA →
  Fiche des données."
- **R21. The panel line goes first, not last.** The owner prefers the "Dans le panneau : …"
  line at the beginning of the message (and of the picker question), so the junior looks at
  the panel while reading, rather than at the end. To change: rule 6 of the agent
  instructions (`CLAUDE.md.in`, the `PANEL_LINE_PLACE` Copilot slot) says where the line goes;
  move it to the first line of the message or picker question, keep the text from
  `next_action.panel.shown.line`, and update the pins in `test_agent_files.py`.
  Fixed: rule 6 of `CLAUDE.md.in` now starts a message that shows or changes something with
  `next_action.panel.shown.line`, verbatim, as its first line; the Copilot slot
  `PANEL_LINE_PLACE` makes it the first line of the picker question ("before the facts"),
  otherwise the first line of the final message; the skill's pause order lists the panel line
  first. Pinned in `test_agent_files.py::test_the_panel_rule` (no "last line" left) and listed
  in `CLAUDE_CODE_INTENDED_CHANGES`; raw budget 3,943 words (binary), rendered Copilot copy
  4,358 (cap 4,400).
- **R22 (blocker). The handoff pack cannot be exported from a French study.** Asked to export to
  `~/studies/hotel-demo3-aml-export` and then the handoff pack, the agent answers "Aucun des
  deux exports n'a été écrit" and explains that the handoff summary writes integers with a comma
  thousands separator ("32,049" development rows, "8,011" final-test rows) that the number check
  refuses, so nothing is written.
  Cause (verified in the code): `cmd_export.build` writes `handoff.md` in English with
  `cite.fmt_number` (`f'{n:,}'` → "32,049", `cite.py:187/195`), then checks it with
  `cmd_check.check_text(view, md, …)`, which reads numbers in the study language: in French
  "32,049" is the decimal 32.049, untraceable → `untraceable_number`, nothing written. Every
  French study with a count ≥ 1000 in its summary is affected. To fix: check `handoff.md` in
  the language it is written in (English), or write it in the study language with French
  number forms (narrow no-break space thousands, comma decimals, as `junior._int` does); add a
  French handoff export test.
  Fixed: `handoff.md` is written in the study language. A French study's pack has French
  headings, labels and verdicts, the French evidence headlines (out of fold where the result
  is), and every cited number in French form (`cite.format_value(..., 'fr')`: "1 200",
  "11,7 %"); it is checked in the language it is written in, so a count of 1,000 or more no
  longer reads as a decimal. `numtrace` reads the French "révision" and "résultat" like
  "revision" and "result" (exempt revision numbers and digit-only result id prefixes).
  `handoff.json` keeps its keys (`results_cited[].shown` is the text `handoff.md` shows). The
  English pack is byte-identical to the one before (compared on a 1,500-row study, and
  `test_adv_c4_bytes`). Tests: `test_export_handoff.py::test_a_french_study_with_thousands_of_rows_exports_its_pack`
  (1,200 development rows, `check --text handoff.md` clean) and
  `::test_an_english_pack_keeps_its_words_and_number_forms`. Contracts: CLI-CONTRACT-COMPANION
  §7 (`handoff.md` in the study language), CLI-CONTRACT (exempting words).
  At the integration (`w3-int`): a French regression pack refused the export too ("7,16 mpg
  pour le modèle de référence (la moyenne)" put the baseline word beyond the number
  tracer's window); the French headline is now "pour la moyenne de référence", and an
  automatic decision's basis is worded in French (`test_automation.py`).
  The Azure ML export was not written either; its own refusal message was not captured in the
  session (to check: whether the agent chained it after the handoff failure, or the export
  itself refused, e.g. `artifact_status` not `packaged`).
  Fixed (Azure ML export, reproduced): a small French binary logistic study walked to `done`
  along `next_action` never captured its model, since no step named the capture, and a capture
  is possible only before the opening; `export azureml --plan` and `--out` then succeeded but
  exported the recipe only (`artifact_status: missing`, `predictor_captured: missing`). The
  journey now captures the chosen model right before the opening is proposed, when the
  template supports it (`view._capture_first`: `run predictor.capture` with `options`
  `{"profile": "workshop"}` when MLflow is installed, a `junior_message` in the study
  language; the final test is still opened once, in the junior's words). Rule 1 of the agent
  instructions passes a run's `rules` and `options` as given. The export at `done` is then
  `packaged`. A study opened without a capture (the owner's existing study) is told so at
  `done`: `after_study.junior_text` says the export carries the recipe, not the evaluated
  model. Tests: `exporters/azureml/test_after_study.py::test_the_journey_captures_the_chosen_model_so_the_export_carries_it`
  (walker, plan and `--out` packaged, one opening) and
  `::test_a_model_opened_without_a_capture_is_said_to_export_as_its_recipe`;
  `test_journey_walkthrough.py` (the capture write shows nothing in the panel). Known, not
  changed then: a workshop capture writes MLflow warnings and a progress bar on stderr (the
  packaging module is fingerprinted). Fixed at the integration: `executions.run` silences
  them around the capture and the final evaluation (NR-17, `test_walkthrough.py` in real
  processes).
- **Mixed-language label in the Decisions tab (fix pass).** A French panel showed "Voir the
  decision-rule evaluation →" on the evidence chip of the rule card: the view held the result
  slots' words in English. Fixed: the words are the copy's `slotWords` (EN "See the
  decision-rule evaluation →", FR "Voir l'évaluation de la règle de décision →"), pinned in
  `decisions.test.js`.

## Fourth session (automatic mode, Auto MPG FR, `5352eeb`) — for the next batch

- **O6 (positive).** `init --automation until_final_test` then `automation run --progress` walked
  Auto MPG to the review (`reason: reached_end`, revision 38, 25 steps): the structural check
  ran before the target looks, the drafted preparation logged `horsepower`
  (`data_contingent: false`), the variants were a tuned ridge plus an EBM motivated by the
  shapes of `horsepower` and `weight`, the model choice picked the linear model, and the run
  stopped before the final test with every decision in the review queue.
- **R23. The automatic run's progress says too little.** Its stderr lines only name the step and
  a state ("Mode automatique · 3 · la disponibilité des variables · proposée", "… · enregistrée
  comme automatique", "Le modèle linéaire · terminé en 0 s"). The owner wants, clearly and in a
  friendly tone, what is going on, the intermediate results and the decisions taken:
  - one line per decision with its value in words and why (e.g. "Préparation : log de
    horsepower (distribution asymétrique) ; rien d'autre") instead of two lines "proposée" /
    "enregistrée comme automatique" (the propose/confirm pair is noise; the step counter
    counts it twice);
  - after each computation, its key result (split: 5 temporal folds, n rows each; quality:
    missing, extremes, rare categories found; baseline and linear model: MAE out of fold;
    variants: each one's MAE and the comparison's advice; diagnostics: the flags raised);
  - a short header (mode, case, what will be done, where it stops) and a closing summary
    (decisions to review, best model and its figure, what the junior does next);
  - stdout then prints the full `hypotrail.automation/1` JSON (very long in a terminal): with
    `--format text`, or by default on a terminal, print a readable summary instead and keep the
    JSON for `--json`.
  The numbers must stay traceable (cite registered values only; same formats as the study
  language).
  **Fixed (owner session 2026-10-27, automatic-mode lot).** `automation run --progress` now
  tells, on stderr and in the study language (`mlkit.study.automation_words`): a header (mode,
  case, the steps on the programme, where it stops); one numbered line per decision once it is
  recorded, its value in words and why (`recommended.why`, or the fixed rule in words; no JSON,
  no id, no "proposée"/"enregistrée" pair); one numbered line per computation, the activity's
  own progress lines indented under it, then its key result with registered figures (split:
  folds and rows; quality: missing values, repeated rows, rare categories, values outside a
  declared range; target summary; each model's out-of-fold MAE or AUC against its reference;
  the comparison's errors, `advice` and one-standard-error pick; the diagnostics' flags; the
  policy's precisions; the final test's figures in `full_demo`); a closing summary (decisions
  to review, the model kept and its figure, the final test, what the junior does next). The
  figures cited by the result and summary lines pass `check --text` on Auto MPG (EN, FR) and on
  a synthetic binary case. `--format text`, or the default when stdout is a terminal, prints a
  readable summary instead of the JSON (`--json` keeps it; a pipe always gets it; the agent
  instructions pass `--json`); CLI-CONTRACT §1 and §5.5. Tests:
  `test_automation.py::test_progress_tells_what_is_going_on[until|demo]`,
  `::test_the_text_summary_and_the_terminal_default` (a real pty),
  `test_contract_freeze.py::test_r23_r24_automation_words_contract`.
- **R24. The review pause offers the wrong options.** After the run, `next_action` is
  `reconfirm prediction_time` with `review: true` and the junior message "Relisez-la : adoptez-la
  avec vos propres mots, ou dites ce que vous changez", but its `pause` is `kind: action` with
  options `continue` / `explain` ("On continue", "Expliquer d'abord") and `recommended_option:
  continue`. A review pause is an adoption question: it should offer adopt / change / explain
  (the decision pause's options, with the restated value as the quoted block), never mark
  "continue" as recommended, and its position should name the reviewed decision, not
  `final_test`.
  **Fixed (owner session 2026-10-27, automatic-mode lot).** A review (`next_action.review`, the
  `reconfirm` and, once the value is proposed again, the `await_user_words`) gets a `decision`
  pause: options adopt / change / explain with the engine's `option_labels`, no
  `recommended_option`, the recorded value in words as the quoted block ("Le moment de la
  prédiction : … (valeur enregistrée par le mode automatique, pas encore avec vos mots).") then
  the closed adoption question, and `position.step_id` the reviewed decision's step
  (`guidance.pause`, `automation_words.review_restatement`; CLI-CONTRACT J4–J7 and §5.5). The
  agent instructions already relay `pause.options` and `option_labels` and recommend only what
  the pause names: unchanged. Tests:
  `test_automation.py::test_the_review_pause_offers_adopt_change_explain[until|demo]`,
  `test_pause_pickers.py::test_a_review_pause_is_an_adoption_pause[en|fr]`.
- **R25. Report in the lesson style (owner request).** The owner wants `reports/study.html` to
  take the design, structure, pedagogical depth and visual interest of the reference lesson
  page ("tableau noir v5" charter: board, index cards, graph-paper figures, sticky TOC, notions
  with term → contextual example → foldable Exemple / Pourquoi ça tient / Code / Où ça casse,
  résumé, "Dites-le à voix haute"). Mockup for approval:
  `docs/plans/mockups/report-lesson-style-mpg-fr.html` (Auto MPG FR, automatic mode, real
  numbers from the owner's report; invented figures stamped "illustratif (maquette)"). A panel
  mockup in the same charter, adapted to the construction journey, follows.
  **Implemented (report lot, integrated on `m-int` 2026-10-27).** `reports/study.html` is the
  lesson (`TEMPLATE_VERSION` 4, `render_lesson.py`, texts in `content/lesson.yaml`; CLI-CONTRACT
  §8.3, §11.5): the charter, the sticky table of contents, the chapters as lessons (term, "In
  this study", folds, "What we keep"), the summary and "Say it out loud". The mockup's
  illustrative figures and widgets are left out (no recorded values). Tests:
  `deliverables/test_lesson_report.py`.
- **R26. Defects the mockup work found in the current French regression report.**
  Classification wording in a regression study ("taux observé moins score moyen", "trop peu de
  lignes positives", "une configuration plus basse classe moins bien" while lower MAE is
  better); English left in the French report ("Development rows", "Linear model", "Mean
  baseline", "Rows read", "Unit", "Scale", "Intervals", "Case", yes/no, "the second variant"…);
  contradictory labels (automatic decisions shown as both "Décision confirmée" and
  "Automatique, à relire"; chapter 2 marked executed while its evidence says "pas encore
  exécuté"; the EBM titled "Variante du modèle linéaire, la deuxième"); and an unflagged tension:
  the one-standard-error rule keeps the linear model while the paired difference shows the EBM
  better by 0.30 mpg with an interval excluding zero. Also: the regression final test is drawn by
  target bins across all years (no declared order), so it cannot show the drift towards recent
  cars (residual +5.27 mpg for 1981–82).
  **Implemented (report lot, integrated on `m-int` 2026-10-27).** No classification wording in a
  regression report, no English in a French edition, an automatic decision never "confirmed",
  chapter status from the plan, the EBM named by its family, the one-standard-error tension
  stated in chapter 7, and a regression final test without a declared order says it cannot show
  drift. Tests: `test_lesson_report.py::test_a_regression_report_holds_no_classification_wording`,
  `::test_each_edition_is_written_in_its_own_language`,
  `::test_an_automatic_decision_is_never_shown_as_confirmed`,
  `::test_a_variant_is_named_by_its_family_and_the_tension_is_stated`,
  `::test_a_regression_final_test_without_order_says_it_cannot_show_drift`.
- **R27. The report switches between English and French.** The lesson-style report must offer an
  EN/FR switch, like the panel's: one generated file holding both languages (engine texts in
  both, as L3's `texts {en, fr}` already provides; the agent's restatements marked with their
  language), the study language shown first; no network, no storage needed (a session toggle).
  **Implemented (integrated on `m-int` 2026-10-27).** Report: two editions in one file, the
  study language first, the language button keeps the reader's place, words recorded in the
  other language marked "(fr)"/"(en)"; `check` reads each edition in its language
  (`test_lesson_report.py::test_check_is_clean_on_both_editions_and_the_page_is_deterministic`,
  `::test_the_restated_words_of_the_other_language_are_marked`). Panel: its EN/FR toggle in the
  lesson style (`test_webview_lesson.py`, both languages).
- **R28. Dark mode ("Tableau noir") by default.** The owner wants the board (dark) theme as the
  default for the report (and the mockups), with the "Tableau blanc" button to switch, instead
  of following `prefers-color-scheme` as the charter currently says. To decide for the panel:
  inside VS Code it should probably still follow the editor's theme.
  **Implemented (integrated on `m-int` 2026-10-27).** The report opens on the board, with a
  whiteboard button (no `prefers-color-scheme`, no storage); the panel follows the VS Code theme
  class, dark board, white board, or the editor's High Contrast colours, with no theme button of
  its own (COMPANION-ADVANCED LS-6, `test_webview_lesson.py::test_ls6_the_vscode_theme_class_picks_the_board`).
- **Mockup feedback.** The background ruling of cards and the graph-paper grid were too visible:
  made much fainter (separate `--ruleline` token; `--gridmm` lowered).
- **R29. A short introduction at the start of each step.** Each chapter of the lesson-style report
  (and each step in the panel) opens with two or three sentences saying what this step does and
  what it corresponds to in the study (why it comes now, what question it answers, what the
  junior will see and decide), before the term card. Example for chapter 7 "Le choix du
  modèle": what is being chosen (among the baseline, the linear model and the variants), on
  what evidence (out-of-fold errors, paired bootstrap, one-standard-error rule), and that the
  final test is still sealed. The engine needs one intro text per step (EN/FR) in the report
  content files.
  **Implemented (integrated on `m-int` 2026-10-27).** Each report chapter opens on "At this
  step" (EN/FR in `content/lesson.yaml`); each panel tab opens on "At this step" and ends on a
  "Next" line (LS-3, `test_webview_lesson.py::test_ls3_r29_every_tab_opens_on_at_this_step_and_ends_on_next`).
- **R30. Everything explained, fluid reading, always know where you are; every chart read and
  concluded.** Every term, number, chart, stamp and abbreviation is explained, at least in a
  foldable block; the main text stays fluid. The reader always sees where they are and what
  remains (sticky "Chapitre n/9 · … — reste : …", a transition line at the end of each chapter).
  Every chart says why it is there (question, frame: development vs final evidence, rows, model)
  and comes with a guided reading: "Comment le lire" step by step, "Ce qu'on en conclut" with the
  actual numbers, and "Attention" when a reading trap exists (example: Figure 7.4, residual boxes
  per model). Applies to the report and the panel.
  **Implemented (integrated on `m-int` 2026-10-27).** Report: the position line and table of
  contents, "Done → Next" transitions, every figure and table framed ("Why this chart", "How to
  read it", "What we conclude" with cited registry values, "Watch out")
  (`test_lesson_report.py::test_every_figure_and_table_is_read_and_concluded`,
  `::test_the_real_report_fits_on_the_board_in_both_languages`). Panel: the journey rail, what
  remains and the sticky position line, guided readings of every chart, notions and "Learn
  more" (LS-1, LS-4, LS-5; `test_webview_lesson.py`).
- **R31. No typed-words acknowledgement in the panel (owner decision 2026-10-27).** The panel's W6
  ("acknowledge an interrupted execution in typed words": a textarea and an "En prendre acte avec
  mes mots" button) is removed: the panel must not take the junior's words. It becomes a read-only
  line "Demandez-le dans le chat" with the copy-question button; the acknowledgement happens in
  the chat. W4 (run another chart), W5 (regenerate) and W7 (export the handoff pack) stay. For the
  real panel: an ADR 0004 amendment and an AGENTS.md update (writes W4, W5, W7 only).
  **Implemented (panel lot, integrated on `m-int` 2026-10-27).** W6 is gone from the protocol,
  the CLI argv builders and the handlers; an interrupted execution shows a read-only line and
  "Copy the question"; `scripts/check_layout.py` refuses an acknowledgement control in the
  panel sources (`test_check_layout_acknowledge.py`); ADR 0004 decision 12, AGENTS.md and
  COMPANION-ADVANCED updated (writes W4, W5, W7 only).

## Owner decision 2026-10-27: implement the mockups

The owner approved both mockups (`docs/plans/mockups/report-lesson-style-mpg-fr.html`,
`docs/plans/mockups/panel-lesson-style-fr.html`) and asked to implement them, with R23, R24,
R26–R31. Lots: report (R25–R30, R26 defects), panel (lesson style, R27–R31, W6 removed with an
ADR 0004 amendment and AGENTS.md update), automatic mode (R23 progress and text summary, R24
review pause).

**Integrated 2026-10-27 (branch `m-int`).** The three lots (automatic mode, panel, report) are
cherry-picked onto one branch with R23 to R31 implemented as marked above. One cross-lot fix:
the panel's next move read the review of an automatic decision (`next_action.review`) as
"Confirm again" with a "Something changed" question; it now reads "Review …" and copies an
adoption question, consistent with the R24 review pause (COMPANION-ADVANCED LS-2). Unit,
real-CLI and simulated-browser tests only: no Copilot or VS Code session has been run on this
batch.

## Fifth session (demo test, `686451b`) — for the next batch

- **R32. Journey rail labels overlap in the panel.** On the lesson-style panel's journey rail
  (Auto MPG FR, step 1 of 13, narrow panel width), neighbouring step labels collide: "Données"
  over "Moment", "Préparation" over "Exploration", "Test final" over "Conclusion"; the fourth
  phase title is truncated ("CONCLURE ET T…"). Labels are centred under evenly spaced dots with
  no width limit, so French labels wider than the dot spacing overlap. To fix: labels must never
  overlap at any panel width (wrap, shorten, or show only the current step's label and a tooltip
  on the others) and phase titles must stay readable; add a simulated-browser check at a narrow
  width in both languages. Noted only, not fixed.
- **R33. A theme toggle for the panel only.** Following the VS Code theme by default is right,
  but the owner wants a button in the panel header (next to EN/FR) that switches the panel
  between the dark board and the light paper, without changing the VS Code theme. Three states
  to decide: follow VS Code (default), dark, light; the choice is a per-viewer convenience kept
  in the webview state (`vscode.setState`), not study state, and is not a write (no CLI call,
  outside W4/W5/W7). Add a simulated-browser check that the toggle switches the tokens and
  survives a refresh. Noted only, not fixed.

**Owner decisions on the synthesis mockup (2026-10-27).** After four independent reviews of
`docs/plans/mockups/panel-synthesis-fr.html`: (1) the step-1 sample shows `mpg` (the owner chose
to show it; the look is counted and said); (2) amend ADR 0004 for one page instead of tabs
(decision 13, accepted, not implemented; R32 and R33 are covered by it); (3) keep What if?, with
its warning.
