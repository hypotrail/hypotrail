# Owner demo 2 remarks (Online Shoppers, 2026-10-20) — to process at the end

## R12 — "Show French labels" button is unclear
- Observed: Data & EDA tab, dictionary header, a "Show French labels" button with no explanation.
- What it does: swaps the dictionary's column descriptions to the case's `labels.fr` (French descriptions).
- Owner clarification: keep the button; only the label/UI must make clear what changes. Fix: a clearer label (e.g. "Column meanings: English | Français" as a two-state toggle showing the active language) plus a one-line hint near the Meaning column. No change to default behaviour.

## R13 — Tell the junior to look at the data in the panel at the start
- Wanted: at step 0, the agent (and/or the panel's "Your next move") points the junior to the Data & EDA tab to see the data card, rows and dictionary.
- Note: only when the panel is enabled; the chat must stay complete without it (AGENTS.md).

## Pending input
- Owner will send the full conversation transcript at the end to find what was unclear (from their questions).

## R14 — "Dis-moi avec tes mots…" is heavy when the junior simply agrees
- Observed (feature availability, Online Shoppers): the agent ends every proposal with "Dis-moi avec tes mots ce que tu gardes, ce que tu exclus, et pourquoi." In practice the owner paraphrases each time they agree.
- Mismatch: in guided mode the engine already accepts an explicit endorsement ("je confirme", "d'accord avec ta recommandation"); only the decision rule and the conclusion need a reason. The agent template still asks for a restatement — training-mode wording leaking into guided.
- Fix direction: in guided, the closing line offers the short path first ("Si ça te va, dis « je confirme » ; sinon dis ce que tu changes") and asks for a reason only where the engine requires one; keep the paraphrase request for training mode. Check the template and skill wording, plus the panel hint.
- Owner precision on R14: the right pattern is the one the agent used next — the decision restated visually as a quoted block ("Tu exclus PageValues parce que… ; tu gardes BounceRates et ExitRates… ; toutes les autres colonnes…") followed by one closed question "Est-ce que tu adoptes cette décision ?". Make that the default for every pause in guided mode: show the restatement block, ask for adoption, accept "oui je confirme" / "je confirme" (a reason only where the engine requires one); ask for the junior's own words only if they want to change something. Same layout in the panel's proposal card.

## R15 — Use the standard ML vocabulary, not home-made translations
- Observed (split pause): the agent introduced "blocs", "prédiction hors bloc", "écart entre blocs" instead of the terms a junior will meet everywhere.
- Wanted: usual terms first — training set / jeu d'entraînement, validation set / jeu de validation, fold / pli, k-fold cross-validation, out-of-fold predictions, holdout / test set (= our "final test"), confidence interval / intervalle de confiance — then the contextual explanation (AGENTS.md: term first, then example).
- Tension with WP-B6c M3 (no "training/validation" vocabulary under CV): the fix is not to hide the standard words but to use them correctly — under CV each fold is in turn the validation fold and the others the training folds. Revise that decision.
- Precision to keep: fold spread (min–max / sd across folds) is not a confidence interval; name both correctly where both appear.
- Fix scope: glossary (canonical English term + usual French term), agent template/skill (use glossary terms verbatim), engine junior texts, report and panel copy; "final test" labelled "holdout (test final)" at first mention.

## R16 — Interactive choices instead of typing (owner idea, to decide)
- Idea: at each pause, the agent uses Claude Code's interactive question tool (AskUserQuestion: 2–4 options + free "Other") instead of asking the junior to type.
- Proposed design: options "J'adopte cette décision" / "Je veux changer quelque chose" (→ free text) / "Explique-moi d'abord"; the selected label is recorded verbatim as user_words with channel `choice`, basis `endorsed`. For the decision rule and the conclusion, the reason stays typed (an agent-written reason as an option would defeat the purpose).
- Risks: rubber-stamping (agent-authored options); not available in `claude -p` (acceptance harness needs the text fallback) and not available in Copilot Chat as far as known (unverified) → must stay an optional layer over the text path. Panel buttons for the same would need an ADR 0004 amendment (W1 requires typed words).
- R16 VALIDATED by owner (options: adopt / change something → free text / explain first; label recorded verbatim with channel `choice`; reason still typed for decision rule and conclusion). Owner notes Copilot has an equivalent interactive-choice feature → implement for both, text path kept as fallback (and for `claude -p` acceptance).

## R17 — Distribution charts lack detail (panel Data & EDA; check the HTML report too)
- Observed (Administrative, Administrative_Duration): bars without x-axis values or bin edges, no y-axis/counts; heavily skewed columns (most rows at 0) collapse into one bar, so the chart says nothing; result id link shown in the card body; a horizontal scrollbar under the chart; the title repeated three times; dotted underline on every number.
- Contradictory text: "training rows only: the validation rows stay unexplored" next to "Counts of development rows … 9,864 rows" (under CV all development rows are read) — evidence-scope wording (see R15).
- Wanted: readable axes (bin edges, counts or %), share of zeros shown separately and a log/zoomed scale for skewed columns, mean + median + IQR named with standard terms, missing/special values as their own bar, column meaning under the title, ids under Details, no stray scrollbar, one title. Optional, counted as a look: conversion rate per bin on the same chart (with interval).

## R18 — Success criterion: metric imposed without justification
- Observed: the agent asks "how many precision points above the baseline" without saying why precision rather than recall, lift, expected value, AUC/AP.
- Fact: the engine hard-codes the binary criterion metric (`governance.CRITERION_METRICS = {'binary': 'precision_gain', ...}`); the junior cannot choose it, and the agent does not explain it.
- Justification that exists but is never said: with a fixed budget (capacity/share rule, k sessions selected) precision = TP/k and recall = TP/P both move with TP only, so they rank configurations identically; "precision gain over the base rate" is the lift in points. With a threshold rule they diverge, and then the choice matters.
- Also: "un critère modeste suffit en général… une équipe marketing remarque…" is an unsupported claim; the question is asked before the action type (share vs threshold) is known.
- Fix direction: the criterion becomes a two-part decision — metric (options explained, default tied to the action: capacity/share → precision at the share, with the precision/recall/lift equivalence stated; threshold → precision or recall chosen; expected value when cost/value assumptions exist; AUC/AP only as ranking diagnostics, not business criteria) + minimum; offered as R16 interactive options; no unsupported generalities.

## R19 — Criterion asked without the reference value and without a business translation
- Owner question: must I pick the points before knowing the reference? Answer: no, the reference is known before any model (base rate of the development rows, ~15.5 %, shown just above in the split result) — fixing the threshold before fitting is the point (pre-registration). But the agent did not state the reference value next to the question.
- Wanted: state the reference explicitly ("sans modèle, 15,5 % des sessions relancées achètent") and translate each candidate threshold into business terms on a worked example, e.g. "relancer 1 000 sessions : la référence trouve ~155 acheteurs ; +5 points = ~205, soit ~50 achats de plus par 1 000 relances" (per 1,000 actions, labelled illustrative, from development rows), with the case's cost/value assumptions when present (expected gain per wave).
- Combine with R18 (metric choice) and R16 (options: e.g. +2 / +5 / +10 points with their business translation, plus "Autre").

## R20 — The chat should point to the relevant panel tab at each step (generalises R13)
- Owner: at a proposal, the agent should say where to look in the panel (Decisions tab: the proposal card and its "what counts as an answer" hint; after confirming, the history). Same for other steps: Data & EDA after charts, Evidence after fits/diagnostics/opening, What if? at the decision rule.
- Constraint: only when the panel is enabled (chat must stay complete without it). Needs a way for the agent to know the panel is on (e.g. engine reads `.vscode/settings.json`/a study flag the panel writes? — panel has no write besides W1–W7; simplest: `status` reports nothing; agent asks once at step 0 "Tu as le panneau Hypotrail ouvert ?" and remembers it in the conversation). One short line per step, never a substitute for the content in chat.

## R21 — FR/EN language option for the panel
- Owner request: a FR/EN option for the panel UI language.
- Constraint: AGENTS.md says maintained UI text is English → this request is the explicit owner decision; amend AGENTS.md ("English is the source language; the panel may ship a French translation") + ADR 0004 note.
- Shape: VS Code setting `hypotrail.companion.language` (`auto` = follow the study language, `en`, `fr`) + a header toggle; no study state written. Client copy (media/copy/*) gets FR strings; engine junior texts (`junior_message`, limits, recap_junior, questions) are English today → engine must emit `fr` variants (study language already exists) or the panel shows them in English under a "(en)" marker. Case `labels.fr` reused for the dictionary (R12 toggle merges into this). Tests: FR snapshot on captured payloads, no missing key.

## R22 — Panel proposal card: "Kept" list is noise; the answer box is unexplained and its hint is wrong for guided
- "Kept": lists every registered result that confirming would NOT invalidate, as prettified slot names ("eda distribution Administrative and eda rate by …"). It is the effect preview (which results stay current, which need reconfirming, what is regenerated). Useful only when something is invalidated. Fix: when nothing is invalidated, one line "Confirming changes nothing already done"; otherwise list invalidated items in words, and keep the kept list under Details.
- Answer box: it is W1 — confirming (or withdrawing) the proposal from the panel instead of the chat, recorded with channel "webview". Nothing says so up front. Fix: title "Confirm here instead of in the chat (optional)", the R14/R16 short path (button "J'adopte" + optional text; reason field only for decision rule/conclusion — would need an ADR 0004 amendment since W1 requires typed words), and a hint that matches the study mode.
- Hint text "Say what you accept and why it fits your situation…" is the old strict rule: wrong in guided (no reason needed for the criterion) and too long. Mode-aware, one sentence.
- Also: "Proposed at revision 18", the dotted "proposal by the agent" underline: internal detail → Details.

## R23 — Decisions only in the chat: remove the panel's confirm/withdraw field (owner decision)
- Owner: for now everything is decided through the chat; remove the answer field (W1 confirm, W2 withdraw) from the panel to keep the UI simple and avoid users getting lost; may come back later.
- Supersedes the panel part of R16/R22 (no "J'adopte" button in the panel).
- Implementation: proposal card becomes read-only (restatement block, effects in words, "Answer in the chat" + "Ask the agent about this" copy-to-clipboard); W1/W2 disabled at every stage; ADR 0004 amendment (narrowing, allowed); AGENTS.md whitelist sentence updated; check_layout asserts no confirm/withdraw call remains.
- To decide alongside: W3 "Propose this rule" (What if?) is also a panel write that bypasses the chat — same logic suggests turning it into "Ask the agent to propose this" (clipboard). W4 (run a chart), W5 (regenerate), W6 (acknowledge interruption), W7 (export) — keep or not.
- R15 addition (owner, model results message): say "échantillon" (échantillon d'entraînement / de validation / de test; "sur l'échantillon de développement") rather than "les 9864 lignes"; "pli" instead of "bloc" ("AUC hors pli" → "AUC out-of-fold, moyenne sur les 5 plis"). Also seen in the same message: raw result ids in prose ("résultat 481d9d55", "b6e749d4") → ids only on demand; "précision moyenne" for average precision is misleading in French → "average precision (AP, aire sous la courbe précision-rappel)".

## R24 — Only one variant, one model family
- Observed: the variant pause offers one variant among three; no second variant, no other model family later.
- Fact: by design (WP-B1 decision "exactly one variant at a time", logistic/linear only). Rationale was limiting forking paths; the trials counter is shown.
- Owner question: is it OK? Assessment: too restrictive now that a sealed final test exists — the final test is what makes several development trials acceptable. The chosen variant here (drop GA group) is a sensitivity check, not a search for a better model; regularisation was never tuned.
- Proposal: (1) a small trial budget (e.g. up to 3 variants, each counted and shown, all compared out-of-fold with paired intervals); (2) regularisation strength chosen by nested/inner CV as ONE trial rather than weak/strong by hand; (3) one non-linear family (e.g. histogram gradient boosting) as a candidate in v0.3, with the same protocol and its own diagnostics. Keep "one decision = one recorded choice", junior picks, budget visible.
- R24 VALIDATED by owner (trial budget up to 3 variants, inner-CV regularisation as one trial, non-linear family in v0.3).
- R24bis VALIDATED (replaces R24 details): hyperparameters tuned by nested CV (one trial per family); junior budget ≤ 3 variants, each declared with its question; 1-SE rule for picking; trials + approximate selection optimism shown; engine advises stopping when fold noise exceeds expected differences.
- Owner amendment: model families are NOT a fixed pair. The family becomes a decision chosen from a small engine-supported catalog (linear/logistic; linear + splines / GAM-like for interpretable non-linearity; gradient boosting; maybe random forest), with an engine-drafted shortlist driven by (a) use-case constraints declared in the case (interpretability or regulation, monotonic constraints, data size, feature types, latency) and (b) diagnostics of the first linear fit (residuals/rates by feature showing non-linearity, interaction signals, calibration shape). Default path: start linear; propose a non-linear family only with the diagnostic evidence shown. Family choices count in the trial budget and are data-contingent when motivated by diagnostics.
- R24bis owner addition (VALIDATED): Explainable Boosting Machine (EBM, InterpretML) in the catalog as the interpretable non-linear family (shape function per feature + a few pairwise interactions). Caveats: new dependency (interpret-core, MIT) to pin and fingerprint, slower fits, notebook recomputation/assert tolerance to define, reproducibility (seeded bagging). Candidate to replace the splines/GAM slot.

## R25 — Decision history: newest first
- Owner: in the panel's Decisions tab the history should be in reverse order (most recent next to the decision block).
- Also seen on the same screen (integrator): "je confirme ce choix" is labelled "restated" while it is a pure endorsement → the basis classifier treats a generic word ("choix") as a token of the value; fix the restated/endorsed classification (only value/label content words count). Timestamps and "revision N" in monospace are internal → move under hover/Details. Every value is dotted-underlined (citation styling on words, not numbers).

## R26 — The panel (EDA above all) is visually unappealing
- Owner: the interface in general, and the EDA part in particular, is ugly and not appealing.
- Seen on the screenshot (integrator): walls of disclaimer text; content overflowing and cut at the right edge ("rows seen in EDA · train 0 · valida…"); monospace mixed into prose; raw result-id links; dotted underline on every number; stray horizontal scrollbars; flat grey/blue bars without labels; meaningless table cells ("0 / 0", "no declared range"); repeated titles; banners stacking. Also a data bug: "train 0" rows seen in EDA while 9,864 development rows were read (CV scope wording/counting, see R15/R17).
- Note: the v0.2 mockups (docs/design/companion-v0.2-mockups) were cleaner; the implementation drifted from them.
- Fix direction: a dedicated design pass before more features — design tokens on VS Code theme variables, a type scale, one card pattern, progressive disclosure (one sentence + "Why?" instead of paragraphs), charts with axes/labels/legend and a consistent palette, no overflow at any width (visual regression screenshots as a gate), ids and provenance only on hover/Details. Process: new mockups for EDA + Overview first → owner validates → implement → screenshot diff gate.

## R27 — Owner decision: drop "dis-le avec tes mots" except when the junior disagrees
- Owner: remove the "say it in your own words" demand everywhere; own words only when the junior wants something different. Strengthens R14/R16.
- Open point for the review: does this also remove the REASON requirement on the decision rule, the conclusion and the final-test opening (current guided hybrid rule, validated in R1)? Integrator default until then: keep a short reason for those three (offered as options per R16 + "Autre"), drop everything else.
- Seen: after the decision-rule confirmation the agent went straight to the final-test opening; "ok allons y" will be refused (bare + no reason) — the agent should offer the R16 options instead of asking for words.
- R27 RESOLVED by owner: paraphrase/reformulation demands exist ONLY in training mode. Integrator reading: guided = an explicit endorsement suffices for every decision, including the decision rule, the conclusion and the final-test opening (reason optional, offered as R16 options, recorded when given); training keeps paraphrase + reasons. This replaces the guided "hybrid rule" of R1 (reason required for policy/conclusion) and the WP-B1 "final_test needs a reason in every mode". Report shows "no reason given" where none was given.

## R28 — Usual artefacts missing: correlation matrix; predicted-vs-actual table
- Correlation matrix: NOT implemented. Planned in the synthesis (Spearman for numeric, Cramér's V for categorical, collinearity flag, training rows) but WP-A4 shipped quality, rate/mean by group with null band and single-feature signal only. The literature review advised against an all-pairs heatmap BY DEFAULT (forking paths) — but a predictor-vs-predictor correlation matrix does not read the target, so it is structural and cheap: add it (development rows, no target, collinearity flag, clustered order), and a target-correlation column only as a counted look.
- Confusion matrix (predicted vs actual, counts): exists in `diag.binary` (WP-B4) and in the panel's Evidence → Diagnostics, but diagnostics are opt-in and the agent did not run them in this demo → the agent must run diagnostics after the fits (instructions say so; it did not), and the report/panel should show the confusion matrix as a plain 2×2 table with counts and rates at the adopted rule.

## R29 — Generated notebook: plain pandas idioms first
- Owner: the generated notebook should favour pandas for exploration whenever possible, because that is how users work.
- Direction: every exploration cell written as the idiom a junior would type — `df.head()`, `df.info()`, `df.describe()`, `df.isna().sum()`, `df[col].value_counts(normalize=True)`, `df.groupby(col)[target].agg(['mean','count'])`, `pd.crosstab`, `df.corr(method='spearman')`, `df[col].plot.hist()` / `df.groupby(...).plot.bar()` — then an `assert` against the registry; `nv.*` helpers kept to loading rows (development/training frame) and the engine's narrative cells. Same rule for the workbench starter. Fold-level CV cells stay scikit-learn but with visible pandas frames (per-fold table via DataFrame).

# From the demo-2 chat transcript (integrator analysis, 2026-10-20)

## R30 — Ambiguous term "session de développement"
- Junior asked "Que veux-tu dire par session de dev ?" after "Quelques sessions de développement sont des copies exactes…". Mixing the row unit (session) with the partition name confuses. Use "les lignes de l'échantillon de développement" (R15) and introduce duplicates only when they matter (at the split), in one sentence.

## R31 — BLOCKER (case design): Online Shoppers scenario is incoherent
- Junior: "quand tu dis s'est terminée par un achat, c'est après notre relance ?" then "à la fin de la session on connaît déjà le résultat". Correct: the case scores finished sessions to decide follow-ups, but the target is the purchase in that same session, already known at prediction time. Precision "share of selected sessions that bought" is not the business value of a follow-up (you would follow up NON-buyers).
- The agent handled it honestly (limit recorded, A/B test as next step), but a discovery case must not start with a contradiction.
- Fix options (decide): (a) reframe as "lookalike scoring": among sessions that did NOT buy, rank by resemblance to buying sessions for retargeting — the model is trained on all sessions, the decision rule applies to non-buyers, and the case says plainly that the evaluation is a proxy; (b) reframe as in-session intent scoring with a documented limitation that the features are end-of-session totals (weak); (c) switch the discovery case. Recommendation: (a), with the scenario, prediction time, decision and limits rewritten in case-supplement, and the agent's step-0 text explaining the proxy.

## R32 — Agent told the junior something the engine contradicted
- At preprocessing the agent said the choices "ne regardent pas la cible, donc ne rendent pas les résultats plus optimistes"; the engine stamped them data-contingent (target looks before the proposal) and the agent corrected itself only at the end. Fix: the propose payload returns `data_contingent` + why before the agent presents the proposal; instructions: read it and say it.

## R33 — `check` rejects correctly rounded figures (friction + information loss)
- Seen: "0.87" (registry 0.8658), "0.61" (0.6130), "2.8 points" (0.028), "11.8 points" (0.118), "14.2 %" (0.1416), "-2.4" (-0.0244), "40.2 %" (0.40217), "184" (selected in a segment) all reported untraceable. The agent burned many tool calls and finally DROPPED information from its messages. Fix: accept any rounding of a registered value to the displayed decimals (and percentage/points scaling of shares), keep the anti-hallucination guarantee; trace segment counts. Regression tests with these exact values.

## R34 — Diagnostics marked stale by the first policy adoption
- diag.binary ran at the scenario-default rule share:0.1; adopting share:0.1 made it stale ("policy confirmed for the first time"). No change in rule → should stay current. Also the end-of-study "Limit: some results are out of date" line is noise for the junior.

## R35 — Agent unaware of panel actions
- Charts launched from the panel (W4) appeared mid-conversation; the agent guessed "quelqu'un… peut-être un notebook ?". The digest carries the channel (webview) → agent should say "tu as lancé ces graphiques depuis le panneau". Ties to R20.

## R36 — Language of recorded values
- The study is in French but the conclusion text and restatements stored are English (fr labels exist only for restatements). Conclusion value text should be in the study language.

## R37 — Long English engine questions reach the junior verbatim
- e.g. the success-criterion junior_message (English paragraph) in a French study. Engine junior texts need fr (ties to R21).
