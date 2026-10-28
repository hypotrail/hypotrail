# Plan: owner session of 2026-10-26 (Copilot chat + study panel), remarks R1b–R20

Source: [copilot-companion-2026-10-26.md](../acceptance/runs/copilot-companion-2026-10-26.md)
(observations O1–O4, remarks R1–R20; R1 and R2 are fixed on `748bd8b` and tested by unit tests
only). Format precedent: [V0.2-DEMO-FEEDBACK-PLAN.md](V0.2-DEMO-FEEDBACK-PLAN.md).

Status: **draft for the owner's review**. It specifies and orders the work; it changes no code.
Every product choice that is still open is listed in [§4 Owner decisions](#4-owner-decisions-needed)
with a recommendation, and is not decided silently here. File and line references were checked
against branch `spec-lot` at `ba4819c`; anything not verified is marked **(unverified)**.

Implementation status: **wave W1 integrated** on branch `w1-int` (lots L1, L2, L4 level 1, L7;
L0 integration: the L2 and L7 agent text applied against the word ledger, the wave's contract
pins in `test_contract_freeze.py`, panel fixtures recaptured, the choice card and
`after_study` checked end to end on a real study). Unit, walker, simulated-browser and
real-CLI tests only; not run with Copilot (§5.4 still to do).

Implementation status: **wave W2 integrated** on branch `w2-int` (lots L6, L3, L5 cherry-picked
in that order over W1; L0 integration: the L3 and L5 agent text applied against the word
ledger, raw 3,929 / 3,888 words (binary / regression, cap 4,000), rendered Copilot copy 4,345 /
4,304 (cap 4,400); one contract commit for the wave (`next_action` key order with
`alternatives`, `test_w2_contract`); panel fixtures recaptured; L5's `structural_eda` shown in
chapter four of the narrative report before the looks at the target, and in the panel's
journey bar ("Quality" / "Qualité"); the case, not the engine, now declares that the
glossary's examples describe it (`glossary_examples` in its translation sidecar), so the
engine names no dataset). Journey checks on the integrated engine: **J-LANG** (no English
sentence in the payloads, the report or the notebook headings of French studies walked to
`done`: synthetic and Auto MPG in the gate, Hotel in the opt-in
`test_j_lang_hotel_french_to_done`, `HYPOTRAIL_JOURNEY_HOTEL=1`), **J-REC** (Hotel FR: the quality check and three screened distributions before any
look at the target, the preparation drafted from them and not data-contingent, the EBM drafted
beside the tuned penalty from the diagnostics' flags, boosting named as the junior knows it,
an SVM refused with a teaching message), **J-REPORT** (nine chapters, `check` clean, Hotel
report about 0.5 MB). Unit, walker, simulated-browser and real-CLI tests only; not run with
Copilot (§5.4 still to do); the owner has not yet read the report at a rehearsal (§5.4 step
16). Each lot's details: L6 `render_narrative` (`TEMPLATE_VERSION` 3); L3 `l10n`,
`l10n_report`, case sidecars `case.l10n.yaml` ([proposals/L3-agent-text.md](proposals/L3-agent-text.md));
L5 `drafts`, `exploration_order: structural_first` for new studies only, Hotel's
`calendar: year` waiting for the next case revision ([proposals/L5-agent-text.md](proposals/L5-agent-text.md)).

Implementation status (wave W3, D19 changed, §10): **L8** (R6 per-column rare grouping with
the recipe operation `rare_category` version 2 and a runtime that reads versions 1 and 2; R5
`quantiles` and `skewness` in `eda.quality`; R10 level 2 progress steps for folds, inner grids
and bootstrap replicates; one set of attestation edges with byte-comparison evidence against
the 10c1e70, 818995c and 506180a engines) is implemented on branch `w3-l8`, unit, process and
exporter tests only; existing captures stop being current (K3); not yet merged by the
integrator, not run with Copilot.

Implementation status (wave W3): **L9** (R20, the automatic mode reviewed at the end, both
variants chosen at launch; D17 a-g as approved, the AGENTS.md exception included) is
implemented on branch `w3-l9`: `init --automation until_final_test|full_demo`, the basis
`automatic` (`ambiguous_confirmation` reasons `automation_not_set`,
`automation_does_not_cover`), `next_action.auto_value` and its fixed rules,
`hypotrail automation run [--progress]` (follows `next_action`, honours every refusal, ends
the mode one way where it stops covering the plan) and `automation stop --user-words`,
`view.automation` and `view.review_queue`, the review in `next_action` (`review: true`;
adoption records `adopted_from`, never "after the final test"), the opening by the junior
only once the queue is empty (`automatic_decisions_reviewed`), the demo's automatic opening
(`basis: automatic` on the opening record), the limits and banners
`automatic_decisions_to_review` and `final_test_opened_automatically` in the report, the
notebook and the panel (read only). ADR 0005 and ADR 0006 amendments, CLI-CONTRACT §5.5. Agent
text in [proposals/L9-agent-text.md](proposals/L9-agent-text.md) for the integrator. Unit,
walker and in-process CLI tests on Auto MPG and synthetic cases; not merged by the integrator,
panel fixtures not recaptured, not run with Copilot (J-A still to rehearse).

Implementation status: **batch integrated** on branch `w3-int` (W1, W2, L8, the third-session
fix pass: R21 panel line first, R22 French handoff, capture before the opening, the panel
label; then L9 cherry-picked). L0 integration of W3: the L9 bullet applied in rule 4 (the
optional Commands line skipped; "only the runner passes `--basis automatic`", so no new
"never"), words freed from text the engine states itself; raw 3,977 / 3,936 words
(binary / regression, cap 4,000), rendered Copilot copy 4,392 / 4,351 (cap 4,400). Found at
integration and fixed: the French handoff words the `automatic` basis and a French
regression pack traces its baseline MAE ("pour la moyenne de référence"); the capture check
leaves the notebook's read side (`capture_check`); a capture or final evaluation writes
nothing on stderr (MLflow noise silenced around the computation, NR-17); walkers follow the
capture step. Panel fixtures recaptured. Full gate once, in chunks: all green apart from the
12 `test_webview_gate` pixel cases, which fail by environment with diffs identical to the
pre-L9 commit `277a738` (none from L9 or L0; the batch's own visual changes still need the
owner's review of `.local/baseline-diff/` before any baseline update). Not run with Copilot
(§5.4 rehearsal, J-A still to do).

**Priority of this batch (owner, 2026-10-26): the workshop journey.** The batch prepares a
workshop. What matters most is the junior's journey as they live it: visually clear,
pedagogical, working features, a fluid path. Lots and waves are therefore ordered by their
impact on that journey (a picker at every closed question, a panel line that points at
something real, one language per study, visible progress during long runs, recommendations
that read the evidence, a report that reads as an explanation, the export reachable at the
end). Internal and integrity work comes after, unless it blocks the journey. The
[journey acceptance](#5-journey-acceptance-the-workshop-path) (§5) is the primary acceptance;
the [non-regression section](#6-non-regression-the-safety-net) (§6) is the safety net behind it.

R19 (the binary logistic export) is implemented in parallel by another agent. This plan does
not design it: it says how R19 fits the batch (L7), what must be re-validated after it lands
(§6, item NR-19), and what it implies for existing studies (risk K3).

Contents: [1 Summary](#1-summary) · [2 Conventions](#2-conventions-for-every-lot) ·
[3 Lots](#3-lots) · [4 Owner decisions](#4-owner-decisions-needed) ·
[5 Journey acceptance](#5-journey-acceptance-the-workshop-path) ·
[6 Non-regression](#6-non-regression-the-safety-net) ·
[7 Contracts and documents](#7-contracts-and-documents-to-amend) ·
[8 Done, risks](#8-definition-of-done-and-risks) · [9 Verification notes](#9-verification-notes)

---

## 1. Summary

### 1.1 Lots

| Lot | Remarks | Theme (journey impact) | Main surfaces | Fingerprinted engine modules touched | ADR / contract |
|---|---|---|---|---|---|
| **L1** | R3, R2b, R2c (+ the agent side of R16) | **A picker at every closed question**; a dismissed picker is asked again, never turned into text | agent templates (`CLAUDE.md.in`, `copilot-agent.md.in`, skill, `FLAVOUR_TEXTS`), `guidance.py`, `junior.py` | none | CLI-CONTRACT §3.1 (pause), ADR 0005 note |
| **L2** | R1b, R16, R11 | **The panel line points at something real**; the panel shows a choice the chat waits for; one card per compared variant | `companion_env.py`, `commands.py` (write results), panel `lib/models/{summary,evidence}.js`, `media/views/{decisions,evidence}.js`, copy EN/FR | none | CLI-CONTRACT §3.2, CLI-CONTRACT-COMPANION, ADR 0004 note 11 |
| **L3** | R4 (every occurrence) | **One language per study**: case texts, engine texts, the panel's language switch | `junior.py`, `view.py`, `commands.init`, case sidecar (D4), panel copy | none (by design, §2.3) | CASE-CONTRACT (translations), CLI-CONTRACT §3.3 |
| **L4** | R9, R10 (level 1) | **Visible progress during long runs**: narration in the chat, progress lines in the terminal | `executions.py` / `cli.py` (`--progress`), Copilot `RUN_NOTICE`, commands block | none (level 1) | CLI-CONTRACT §1 (stderr clause), §8.1 |
| **L5** | R5, R7, R13, R12, R14, R15 | **Recommendations that read the evidence**: structural check first, a drafted preparation, a drafted non-linear variant when flagged, names the junior knows, a refusal that teaches | `state.py` (plan generation), `junior.py`, `view.py`, `commands.validate_variant`, glossary | none (L5 avoids them; L8 holds the rest) | CLI-CONTRACT §3.1, §11.2–11.3, §14; ADR 0007 note; JUNIOR-WORKFLOW |
| **L6** | R8 | **A report that reads as an explanation**, with a table of contents | `render_html.py`, `render_trials.py`, `render_diagnostics.py`, `content/report*.yaml` | none | CLI-CONTRACT §8.3, §11.5 |
| **L7** | R17, R18, R19 (integration), the "what comes after the study" request | **Conclusion and hand-over**: correct limits, a next step at `done`, an export that is reachable and honest | `state.py` (limits), `junior.py`, `cmd_export.py`, `mlkit/exporters/azureml/command.py`, skill conclusion | none in L7 itself (R19 is the other agent's) | CLI-CONTRACT §3.1, §15; AZUREML-EXPORT-V1 |
| **L8** | R6, R5 (quality quantiles), R10 (fold-level progress) | **Fingerprinted engine changes**, bundled once, with attestation edges | `governance.py`, `fit.py`, `eda.py`, `contracts/recipe.py`, `hypotrail_runtime/preprocess.py` | **yes**: `governance`, `fit`, `eda`, `activities`, recipe, runtime | CLI-CONTRACT §11.3; runtime contract op version; `code_compat` edges |
| **L9** | R20 | **Automatic mode reviewed at the end** (both variants chosen at launch) | `state.py`, `commands.py`, `view.py`, `junior.py`, render, agent templates, panel read-only banner | none if kept to state/commands/view | **ADR 0005 amendment**, **ADR 0006 amendment** (demo opening), CLI-CONTRACT §5 |
| **L0** | all | Integration: agent-template word budget, contract freeze, panel fixtures, pixel baselines review, journey harness | `test_agent_files.py`, `test_contract_freeze.py`, `clients/vscode-companion/test/fixtures/capture.py`, new journey tests | — | — |

R1 and R2 are fixed (`748bd8b`). R1b is the follow-up of R1; R2b and R2c of R2. O1–O4 are
observations to keep (they become journey checks in §5).

### 1.2 Waves (ordered by journey impact)

| Wave | Lots (parallel within a wave) | Gate before the next wave | Why this order |
|---|---|---|---|
| **W0** (before code) | Owner decisions §4; R19 merged by its agent; ADR 0005/0006 amendment drafts for L9 | decisions recorded in a short decisions log next to this plan | L3, L5, L6, L9 depend on product choices |
| **W1** | **L1**, **L2**, **L4** (level 1), **L7** (R17, R18, `done` next step; R19 deep validation, NR-19) | full gate green; journey checks J-PICK, J-PANEL, J-PROG, J-LIMIT automated parts green | The four things the owner saw break the flow in every step: no picker, a panel line to an empty tab, nothing moving for minutes, a wrong limit at the end |
| **W2** | **L3**, **L5**, **L6** | full gate; J-LANG, J-REC, J-REPORT green; panel fixtures recaptured; changed pixel baselines reviewed by the owner | Needs W0 decisions (case translations, EDA order, draft rules, report structure) |
| **W3** | **L9**, then (post-workshop recommended, D19) **L8** | full gate; NR-CC (attestations) for L8 | L9 is large and new; L8 touches fingerprinted modules and the runtime that R19 also touches |
| **W4** | Journey rehearsal | §5 owner Copilot rehearsal on Hotel (FR) and Auto MPG (EN, with export) | The only real Copilot evidence |

### 1.3 Shared files and the integrator

One integrator owns the files several lots edit, merges lot branches in wave order, and runs
the full gate after each merge.

| Shared file | Lots | Rule |
|---|---|---|
| `framework/mlkit/study/agent/CLAUDE.md.in`, `copilot-agent.md.in`, `dot-claude/skills/hypotrail-study/SKILL.md`, `dot-claude/commands/hypotrail-resume.md`, `agent_files.FLAVOUR_TEXTS` | L1, L2, L4, L5, L7, L9 | Lots write their **text proposals** in their branch; the integrator applies them against the word ledger (§2.4). No lot edits the templates directly after W1 starts except through the integrator. |
| `framework/mlkit/study/junior.py` | L1, L2, L3, L5, L7, L9 | Additive functions per lot; the integrator resolves `enrich` ordering (one function call per lot, fixed order). |
| `framework/mlkit/study/view.py`, `state.py`, `commands.py` | L2, L5, L7, L9 (L3 `view`, `commands.init`) | Additive keys only; `next_action` key order fixed by the integrator and pinned in `test_contract_freeze.py`. |
| `framework/mlkit/study/companion_env.py` | L2 (L3 labels) | L2 owns. |
| `framework/mlkit/study/guidance.py` | L1 (L9 option for automation banner) | L1 owns. |
| `docs/specs/CLI-CONTRACT.md` + `framework/tests/study/test_contract_freeze.py` | all engine lots | One contract commit per wave by the integrator (CONTRIBUTING: "A contract change updates the document and the freeze test in the same commit"). |
| `clients/vscode-companion/test/fixtures/` (captured), `capture.py` | L1, L2, L3, L5, L9 | Recapture once per wave after the engine merges (`uv run --project framework python clients/vscode-companion/test/fixtures/capture.py`), then fix the hand-written fixtures `test_fixture_drift.py` names. |
| `clients/vscode-companion/media/copy/*.js`, `media/copy-fr/*.js` | L2, L3, L9 | Every key in both languages in the same commit (`copy-fr.test.js`). |
| `clients/vscode-companion/test/baselines/` | L2, L3, L6? (report is not in baselines), L9 | Never rewritten without the owner reviewing every diff image (CONTRIBUTING). |
| `framework/mlkit/exporters/azureml/*`, `mlkit/contracts/recipe.py`, `hypotrail_runtime/*` | R19 (other agent), L7 (R18), L8 (R6) | L7's R18 edit lands **after** R19 is merged; L8 after R19 (risk K3). |

---

## 2. Conventions for every lot

### 2.1 One name per concept (new names introduced by this plan)

| Concept | Name | Where |
|---|---|---|
| Where the panel shows what the command just produced | `next_action.panel.shown` = `{tab, section, label, line}` or `null` | L2; added to `companion_env.PANEL_KEYS` after `where` |
| Where the panel will show the next step (exists, R1) | `next_action.panel.where` (unchanged meaning) | R1 |
| Labels of a pause's options, in the study language | `pause.option_labels` (`{option_id: label}`) | L1 |
| A free choice among the engine's allowed values | `pause.kind: "choice"` and `next_action.choice_options` (`[{id, value, label}]`) | L1, read by L2 |
| Progress on stderr | `run --progress` (flag); a progress line | L4, L8 |
| The plan generation that explores structure before the target | state key `exploration_order: "structural_first"`; step id `structural_eda` | L5 |
| A look at the target, as a term | glossary term `target_look` ("look at the target" / "regard sur la cible") | L5 |
| The junior-readable reason a preparation is data-contingent | `data_contingent_reason.junior_text` | L5 |
| The engine's drafted value and its comparison option | `next_action.default_value` (drafted), `next_action.alternatives` (`[{value, label, why}]`), `recommended.reasons` | L5 |
| A family name the junior recognises | `model_families.families[].junior_words` | L5 |
| A refused family outside the catalogue | `invalid_value`, `details.reason: "family_not_in_catalogue"`, `details.closest_family`, `details.junior_message`, `details.workbench` | L5 |
| What comes after the study | `next_action.after_study` (on `kind: done`) | L7 |
| An automatic study | state key `automation` (`null`, `until_final_test`, `full_demo`), `init --automation`, confirmation basis `automatic`, `view.review_queue`, limit id `automatic_decisions_to_review` | L9 |
| Engine junior texts in both languages for the panel | `texts: {en, fr}` next to the study-language text | L3 |

Existing names are kept: `junior_message`, `junior_digest`, `recommended`, `question`,
`default_value`, `pause`, `panel`, `data_contingent`, `motivated_by`, `model_families`,
`model_selection`, `not_yet_defensible` ids.

### 2.2 Compatibility rules (all lots)

1. **Existing studies load unchanged.** No reset, no migration of human decisions, no rewrite
   of `state.json`. A new behaviour that changes the plan applies to studies created after it
   (a state key written by `init`, as `has_wp_b1_decisions` and `has_explicit_binary_model_choice`
   did for earlier generations: `state.py:702-721`).
2. **Payload changes are additive.** New keys at the end of their object; no key renamed, no
   type changed. Where a value set grows (a new `pause.kind`, a new basis), the contract and
   the freeze test say so. With the panel off, every payload is byte-identical to today's
   except for the additive keys listed per lot (`test_next_action_has_no_panel_by_default`
   stays green and gains the L2 key `shown`).
3. **The case files.** Any byte change to a committed `case.yaml` makes every study created on
   the previous bytes report `sources_changed` (every result `current: false`, proposals
   refused; `test_sources_changed.py`, CLI-CONTRACT §4 `not_yet_defensible`). The owner's
   existing Hotel study is such a study. A case edit is therefore an owner decision (D4, D8).
4. **Stored result texts are not rewritten.** EDA questions and notes are stored in registered
   values in English (`eda.py:584-603`, `eda.development_words` 897-913). Translation happens
   at read time in non-fingerprinted modules, so old results translate too.

### 2.3 Fingerprint discipline

The registry's code fingerprint of each activity lists the modules of `activities.MODULES`
(`activities.py:190-251`): `activities`, `eda`, `fit`, `governance`, `trials`, `diagnostics`,
`policy`, `families`, `classical`, `metrics`, `objective`, `evaluation_plan`, `regression`,
`correlation`, the runtime and the contracts for `predictor.capture`, and the library versions.
A byte change to any of them makes the results of those activities "code changed" in every
existing study, **including the one evaluation of an opened final test**, unless an exact,
directed attestation edge is added to `mlkit/study/code_compat.py` with reproducible evidence
(`framework/tests/study/code_compat_evidence.py`, two engines, the same commands, byte
comparison). `predictor.capture` has never been attested (its ids hash the code fingerprint,
`code_compat.py` round-2 comment), so a change to any capture module makes existing captures
not current; for an opened final test the Azure ML export then falls back to recipe-only
(CLI-CONTRACT §15) **(inferred from the code and the contract; to confirm by a test in L8)**.

Rule for this batch: **W1 and W2 touch no module listed in `activities.MODULES`.** Wording,
drafts, plan order and panel hints go in `state.py`, `view.py`, `junior.py`, `commands.py`,
`guidance.py`, `companion_env.py`, `executions.py`, `cli.py`, `cmd_export.py` and the render
modules, none of which is fingerprinted. In particular:

- the R15 refusal text in `trials.py:268-270` is **not edited**: `commands.validate_variant`
  (`commands.py:608-626`) adds the junior message around it;
- the R14 names in `trials.FAMILY_WORDS` (`trials.py:114-119`) are **not edited**: the view
  adds `junior_words`;
- the R13 draft is computed in the view layer, not in `trials.draft` (`trials.py:414-418`);
- EDA questions are translated in `junior.py`, not in `eda.py`.

Everything that cannot avoid a fingerprinted module (R6, quality quantiles for R5, fold-level
progress for R10) is bundled in **L8**, with one set of attestation edges.

### 2.4 Agent-template word budget

`test_agent_files.py::test_the_instructions_fit_the_word_budget` (line 442) caps, per task,
the raw templates `CLAUDE.md.in` + `copilot-agent.md.in` + `hypotrail-resume.md` + `SKILL.md`
(task blocks selected, placeholders unexpanded) at 4,000 words. Measured on `ba4819c`:

| Task | CLAUDE.md.in | copilot-agent.md.in | resume | SKILL.md | Total | Headroom |
|---|---|---|---|---|---|---|
| binary | 2,831 | 159 | 197 | 812 | **3,999** | 1 |
| regression | 2,694 | 159 | 197 | 908 | 3,958 | 42 |

Rendered with placeholders expanded (binary): Claude Code copy 3,897 words, Copilot copy
**4,317** words. Known weakness: a `{{SLOT}}` counts as one word in the cap, so Copilot-only
text in `FLAVOUR_TEXTS` grows the Copilot copy without moving the measured total.

**Ledger for this batch (estimates; the integrator measures each change).**

| Change | Words (shared raw text) | Freed by |
|---|---|---|
| L1: closed questions use the picker (R3), a dismissed picker is not a failure (R2b), free choice (R2c) | +55 shared (rule 4, skill "One pause"), Copilot detail in slots | — |
| L2: the line is `panel.shown.line`, none when null (R1b) | +15 | **−45**: rule 6's tab-by-step mapping (`CLAUDE.md.in:203-212`) replaced by the engine's `shown` |
| L4: `--progress`, do not discard stderr (R10); narration (R9) in the Copilot `RUN_NOTICE` slot | +12 shared, slot text | — |
| L5: relay `data_contingent_reason.junior_text` (R7) | +20 | **−52**: the preprocessing paragraph (`CLAUDE.md.in:86-90`) |
| L5: relay `model_families` junior text (R13, R14) | +10 | **−30**: the demo question sentence (`CLAUDE.md.in:96-99`) |
| L5: decision list shortened to what `default_value` and refusals do not give | — | **−50** (`CLAUDE.md.in:294-313`; keep the pinned `model_choice` phrase) |
| L7: what comes after the study at `done` (skill "The conclusion") | +30 | — |
| L9: automatic mode (rule 4, a bullet) | +55 | — |
| **Net** | **+197** | **−177** |

Net about +20 on a headroom of 1 (binary): the integrator must find about 25 more words, for
example in the skill's "Resuming" heading list (now served by `/hypotrail-resume`). Two rules
for the integrator:

1. The existing cap stays (never raised to fit a change, never weakened).
2. **New test** `test_the_rendered_copilot_copy_stays_bounded`: the rendered Copilot copy
   (placeholders expanded) of each task stays at or below a cap the owner sets (D18;
   recommendation 4,400 words, today 4,317), so slot text is counted where the junior reads it.

Pinned phrases that a lot intentionally changes (for example rule 6's mapping, pinned in
`test_the_panel_rule`) are replaced in the same commit by pinned phrases of the new rule **and**
by engine tests of the behaviour that moved to the engine. Removing a pinned phrase without a
replacement test is a weakened assertion and is not accepted.

### 2.5 French examples

Product copy is quoted in French where the owner saw it; the documentation stays in English.
Every French text follows the "vous" register (owner decision 2026-10-21,
`test_v03_french_register.py`).

---

## 3. Lots

Each item gives: the problem with the evidence from the notes; the root cause in the code; the
specified behaviour; options where a product choice is open (with the decision number of §4);
contracts and documents; compatibility; tests; acceptance.

### L1 — A picker at every closed question (R3, R2b, R2c; agent side of R16)

Wave W1. Owner of `guidance.py`; proposes template text to the integrator.

#### R3 — No picker at step changes

- **Evidence.** Four cases in the notes: step 0 ends with "La prochaine étape consiste à définir
  le moment de la prédiction. On y passe ?"; after framing "On continue ?"; after the
  preparation "On lance les modèles ?"; after the fits "On passe à ce choix ?". All in text,
  no picker. "R3 is systematic at transitions."
- **Root cause.**
  - The R2 fix covers decision pauses only: `FLAVOUR_TEXTS[COPILOT]['CHOICE_STEPS']`
    (`agent_files.py:100-106`: "Every pause turn ends with this call") and
    `copilot-agent.md.in:7-17` ("every guided pause turn ends with a
    #tool:vscode/askQuestions call"). A transition is not a "pause" in the template's sense.
  - The engine already models these turns: `guidance.pause` gives `kind: "action"` with
    `options: ["continue", "explain"]` and `recommended_option: "continue"` and the question
    (`guidance.py:43-46`; observed on a scratch Hotel study: `"question": "On regarde ensemble
    la fiche des données ?"`). Nothing tells the agent to turn it into a picker, and the
    options have no labels in the study language.
  - `CLAUDE.md.in:74-78` says "Continue" approves the work between two pauses, so a "go on?"
    question is often avoidable; when the agent asks one anyway, it is closed.
- **Specified behaviour.**
  - Engine (`guidance.py`, not fingerprinted): `pause.option_labels` (new key after `options`)
    in the study language, for every kind that has options:

    | option id | EN | FR |
    |---|---|---|
    | `adopt` | I adopt this decision | J'adopte cette décision |
    | `change` | Change something | Changer quelque chose |
    | `explain` | Explain first | Expliquer d'abord |
    | `continue` | Let's continue | On continue |

    (`adopt`, `change`, `explain` repeat the labels the templates already fix,
    `copilot-agent.md.in:12-15`, so the agent stops translating them.)
  - Agent (Copilot only, through `FLAVOUR_TEXTS` slots; Claude Code copy unchanged): "With
    Copilot, a turn that ends with a closed question (go on, explain first, adopt, or one of the
    engine's options) ends with the picker; its options are `next_action.pause.options` with
    `pause.option_labels`, the recommended one marked only when `recommended_option` names it.
    An open question (what do you want to change?) stays in text."
  - The turn's last message still holds what the junior must keep (the summary of what was
    done, the next step), as the picker question (Copilot folds text written before a tool
    call, `agent_files.py:72-74`).
- **Options.** D1: picker for every closed question (recommended) vs. decision pauses only.
  D1b: apply the same to Claude Code (`AskUserQuestion`)? Recommendation: Copilot only in this
  batch (the notes concern Copilot; `test_the_r2_fix_leaves_the_claude_code_copy_unchanged`
  keeps protecting the Claude Code copy).
- **Contracts.** CLI-CONTRACT "Reliability roadmap J4–J7 additions" (`hypotrail.pause/1`):
  `option_labels`. `presentation.pending_action` equals the pause (`test_reliability_j4_j7.py:93-104`),
  so it gains the key too.

#### R2b — A dismissed picker becomes text for good

- **Evidence.** Step 5: the picker was not answered; the next turn opens "Rien n'est encore
  enregistré pour la préparation des variables, puisque la question a été ignorée.", repeats
  the whole pause and ends in text. "la question a été ignorée" reads as a reproach.
- **Root cause.** The fallback is worded as "only if the call fails or the tool is missing"
  (`copilot-agent.md.in:16-17`, `FLAVOUR_TEXTS[COPILOT]['TEXT_FALLBACK']`,
  `agent_files.py:109`). A closed or unanswered picker reads to the agent as a failed call.
  How VS Code reports a dismissed `askQuestions` call to the agent is **(unverified)**.
- **Specified behaviour (Copilot slot text).** "A picker closed without an answer, or a reply
  typed in the chat instead, is not a failed call. Read a typed reply as the answer (it may
  adopt, change, or ask). When the pause must be asked again, say nothing was recorded yet
  ("Rien n'est encore enregistré : voici de nouveau la décision.") and call the picker again.
  Only a tool error or a missing tool falls back to text." No word that blames the junior
  ("ignorée", "ignored").
- **Tests.** Template test pins the four ideas (not a failure, read a typed reply, ask again
  with the picker, only an error falls back); a negative pin: the rendered Copilot copy holds
  no "ignor" form; the Claude Code copy is unchanged.

#### R2c — No picker at a free choice

- **Evidence.** The conclusion question "Que concluez-vous parmi ces trois options ?" lists the
  options as bullets and ends without the picker.
- **Root cause.** At the model choice and the conclusion `recommended` is `null` (skill
  `SKILL.md:43-45`: "present the options and let the junior choose"); `guidance.pause` then
  has `kind: "action"` with options `continue`/`explain` (`guidance.py:43-46`), which are
  wrong for a choice. The engine's allowed values exist (`preconditions.conclusion_verdicts`,
  `preconditions.py:115`; `preconditions.missing_for_decision`, line 138, refuses an adopting
  verdict before the opening) but are not in `next_action`.
- **Specified behaviour.**
  - Engine (`junior.enrich` + `guidance.pause`): when `next_action.kind == "propose"`,
    `recommended` is `null` and the decision is `model_choice` or `conclusion`,
    `next_action.choice_options` lists the values the engine would accept now, each
    `{id, value, label}` in the study language:
    - conclusion: the verdicts of `conclusion_verdicts(state)` for which
      `missing_for_decision(state, "conclusion", {"verdict": v})` is empty (so `adopt_policy`
      appears only after the opening, as the round-9 rule requires); labels e.g. "Adopter la
      règle", "Garder la référence", "Ne pas conclure (non concluant)";
    - model choice: the candidate and the current declared variant slots (binary: never
      `fit.baseline`; regression: the baseline included), labels in words
      (`audience`/panel words, e.g. "Le modèle logistique", "La deuxième variante · boosting
      explicable").
    - `pause.kind = "choice"`, `pause.options` = the ids, `pause.option_labels`,
      `recommended_option: null`.
  - Agent: "When `pause.kind` is `choice`, offer one option per `choice_options` with its
    label, none marked recommended. The pick is the junior's choice, not a confirmation:
    propose that value (for the conclusion, with its text in `next_action.language`), then ask
    the adoption question as at any pause." A pick is never recorded with `--channel choice`
    (ADR 0005 amendment 4 limits `choice` to the adoption option of an open proposal).
- **Option.** D2: two steps (pick, then adopt the proposal) as specified, vs. one step for the
  model choice only. Recommendation: two steps everywhere (the conclusion carries a text the
  junior has not read yet; one rule is easier to teach).
- **Contracts.** CLI-CONTRACT §3.1: `choice_options` on `propose`; `hypotrail.pause/1` kind
  `choice`. `feasibility.checked` (round 6) must evaluate each option as the engine would
  confirm it, so no option is one the engine refuses.

#### L1 compatibility

Additive keys; a new pause kind value. Existing studies get the keys on read (no state change).
`presentation.pending_action` changes with the pause: the deliverables that embed it stay
deterministic (`test_generator_is_deterministic`).

#### L1 tests

- Unit (engine): `test_pause_option_labels_in_the_study_language` (EN/FR, every kind);
  `test_choice_options_are_exactly_the_accepted_values` (conclusion before and after the
  opening; model choice binary and regression; each option confirmed through the real CLI is
  accepted, and no accepted value is missing); `test_a_choice_pick_is_never_a_confirmation`
  (`--channel choice` on a decision with no open proposal is refused as today).
- Walkers: extend `test_review_round6_engine.py::test_next_action_is_never_refused_and_settles`
  and `test_review_round5_engine.py::test_next_action_runs_as_given_from_init_to_done` to
  confirm every `choice_options` entry in turn on clones.
- Agent templates: `test_copilot_ends_every_closed_question_with_the_picker` (R3),
  `test_a_dismissed_picker_is_asked_again` (R2b), `test_a_free_choice_uses_the_picker` (R2c),
  plus `test_the_r2_fix_leaves_the_claude_code_copy_unchanged` extended to these slots; the
  word cap and the new rendered cap (§2.4).
- Graders: a transcript grader `closed_question_without_picker(events)` for Copilot exports
  if the export format allows it (**(unverified)**: VS Code chat export JSON shape); for Claude
  Code `-p` runs the picker cannot appear, so the existing text path is graded as today.
- Manual Copilot: §5.4 steps 0, 3, 5, 12, 15.

#### L1 acceptance

Every turn that asks a closed question ends with the picker, in the study language; a
dismissed picker is asked again with the picker and without blame; the conclusion and the model
choice offer exactly the engine's allowed values; the Claude Code copy is byte-identical except
for shared lines the integrator lists.

### L2 — The panel line points at something real (R1b, R16, R11)

Wave W1. Owner of `companion_env.py` and of the panel changes.

#### R1b — The line points at an empty tab

- **Evidence.** After the preparation was recorded: "Dans le panneau : onglet Décisions." while
  Decisions shows "En attente de votre réponse — Rien n'attend votre réponse"; the recorded
  preparation is only in "Historique des décisions".
- **Root cause.** `companion_env.wanted_tab` (`companion_env.py:167-185`) maps the **next**
  action's kind to a tab (`propose` and `await_user_words` → Decisions, `run` → Evidence or
  Data & EDA, everything else → Overview); `where` (188-198) names a tab, never a section. The
  agent's rule 6 (`CLAUDE.md.in:200-217`) also carries its own step-to-tab mapping. On a scratch
  Auto MPG study with the panel on (stage v3, French), the confirmation of the preparation
  returned `next_action.panel.where.line` = "Dans le panneau : onglet Preuves." (next action
  `run fit.baseline`), before any fit exists; the line the owner saw ("onglet Décisions") is
  therefore the agent's own rule-6 mapping, or another path **(not reproduced)**. Either way
  the line follows the next step, not what the message shows.
- **Specified behaviour.**
  - `next_action.panel.shown` (new key after `where`): `{tab, section, label, line}` naming
    where the panel shows what **this command produced**, or `null` when it produced nothing
    the panel shows. Computed by the command surfaces (`commands.refreshed_next_action` /
    `_with_panel`, `commands.py:2195-2211`), from the command and its result, never from the
    view the deliverables are rendered from:

    | Command result | tab | section (panel heading, EN / FR) |
    |---|---|---|
    | `data` (step 0), via `next_action.kind == show_data_card` | `eda` | Data card / Fiche des données (**new heading** in the panel: the data card has none today; `media/copy*/eda.js` has `rowsTitle`, `dictionaryTitle` only) |
    | `decide propose` | `decisions` | Waiting for your answer / En attente de votre réponse (`waitingTitle`) |
    | `decide confirm` | `decisions` | Decision history / Historique des décisions (`historyTitle`) |
    | `decide note` (hold) | `decisions` | the holds section (`holdsTitle`, "En suspens") |
    | `run eda.quality` | `eda` | Data quality / Qualité des données (`qualityTitle`) |
    | `run eda.*` other | `eda` | the card of that activity (its heading) |
    | `run fit.*`, `policy.evaluate`, `evaluate.regression` | `evidence` | Development evidence · used to choose / Preuves de développement · ont servi à choisir (`developmentTitle`) |
    | `run diag.binary`, `diag.regression` | `evidence` | Diagnostics (`diagnosticsTitle`) |
    | `run final_test.evaluation`, `diag.final_test` | `evidence` | Final test / Test final (`finalTitle`) |
    | `render` | `null` (nothing new to look at in the panel) | — |

    At a stage that lacks the tab, the existing fallback (`FALLBACK`, line 63) applies; at v0
    the line names the panel's one page. `line`: "Dans le panneau : Décisions → Historique des
    décisions." / "In the panel: Decisions → Decision history."
  - `status` and `status --summary` give `shown: null` (a read shows nothing new).
  - Agent rule 6: "When the panel is open, end a message that shows or changes something with
    `next_action.panel.shown.line` of the command it reports; no line when it is null." The
    tab-by-step mapping of rule 6 is removed (§2.4).
  - Section labels are the panel's copy, verbatim; `test_panel_labels.py` extends to them.
- **Option.** D3: the line from what the message shows (recommended, as above) vs. keep the next
  step's tab with a section.
- **Contracts.** CLI-CONTRACT §3.2 ("Where the study panel shows the step"); ADR 0004 amendment
  note 11 (the engine names the panel's sections; a read of configuration, no write, no stage
  change, the panel's behaviour does not depend on it).

#### R16 — The chat waits; the panel says nothing waits

- **Evidence.** At the conclusion the chat asks "Que concluez-vous parmi ces trois options ?"
  while Decisions says "Rien n'attend votre réponse. L'assistant propose les décisions dans le
  chat."
- **Root cause.** The waiting section lists open proposals only (`media/views/decisions.js:498-499`,
  `nothingWaiting`, `media/copy-fr/decisions.js:10`); a `propose` next action is described as
  "Nothing waits for you here. The assistant proposes this step in the chat."
  (`media/copy/junior.js:296`). With `recommended: null` the agent asks before any proposal
  exists.
- **Specified behaviour.** The panel reads `next_action.choice_options` (L1) from the summary it
  already reads (`lib/models/summary.js:231`, `270-290`) and, when present, shows in "Waiting
  for your answer" a read-only card: "La conclusion : l'assistant vous demande de choisir dans
  le chat", the options' labels, "Answer in the chat", and the existing "Ask the agent about
  this" copy button (clipboard only, ADR 0004 decision 8). No control, no write. `shown` for
  that turn names "Décisions → En attente de votre réponse".
- **Constraints kept.** No new write; `lib/cli.js` still has exactly W4–W7
  (`invariants.test.js` INV-3); no `decide` in client sources (`check_layout.companion_decide_errors`).
- **Contracts.** CLI-CONTRACT-COMPANION (the summary's `next_action` gains `choice_options`; the
  client key list in `test_contract_keys.py`).

#### R11 — Only the last variant's analysis appears

- **Evidence.** Two variants fitted (tuned penalised logistic, EBM); Evidence shows "Deuxième
  variante · Boosting explicable" and no analysis of the first variant.
- **Root cause (verified in the client code; the session screen not reproduced).**
  `familyFitsOf` (`lib/models/evidence.js:706-716`) builds a card only for a fit with
  `family_diagnostics` (EBM terms, boosting importance); a `tuned`, `regularisation` or
  `drop_group` variant has none, so it gets no card. `variantOf` (360-399) reads the
  comparison of slot `fit.variant` only, not `fit.variant:2`/`:3`. The selection table
  (`selectionOf`) does list every configuration.
- **Specified behaviour.** One card per compared variant, in slot order, next to the selection
  card: what the variant changes (kind and words), its question, its cross-validation figures
  beside the candidate's (cited from the stored `model_selection`), and its own analysis:
  coefficients with intervals from the current development diagnostics when they cover the slot
  (`diag.* models[slot].coefficients`; the diagnostics cover the candidate and the compared
  variants, `activities.py:1153-1163`), the chosen penalty per outer fold for a `tuned` variant
  (the tuning record the fit stores, key names **(unverified)**), the family card for a family.
  A variant whose analysis is not computed says so ("Diagnostics not yet run for this
  variant").
- **Contracts.** None (client only); `test_requirement_coverage.py` gets the new requirement.

#### L2 compatibility

`shown` is absent when the panel is off (inside `panel`). Panel changes are reads. Captured
fixtures change (recapture); Evidence and Decisions baselines change → owner review.

#### L2 tests

- Unit: `test_companion_env.py`: `test_shown_names_the_section_of_each_command` (table above,
  EN/FR, every stage), `test_shown_is_null_for_reads_and_render`, `test_no_panel_key_when_off`
  (extends `test_next_action_has_no_panel_by_default`).
- Panel labels: `test_panel_labels.py::test_the_section_labels_equal_the_panel_copy`.
- Node: `decisions.test.js` (a `choice_options` card, no control); `evidence.test.js` (one card
  per variant slot, tuned/regularisation/drop_group/family); `invariants.test.js` unchanged
  and green.
- Integration (real CLI): `integration-v2.test.js` / `integration-v3.test.js` on the Bank
  families scenario: three variant cards; the conclusion choice card.
- **Journey check J-PANEL** (§5.3): for every write of the scripted walkthrough, the section
  `shown` names is rendered by the panel model with at least one item.
- Playwright structural: `test_webview_decisions.py`, `test_webview_evidence.py`; gate
  `test_webview_gate.py` structural assertions; pixel diffs to the owner.

#### L2 acceptance

Every panel line names a tab and a section that shows the thing the message talks about; no
line after a command that produced nothing the panel shows; at the conclusion the panel shows
the choice the chat waits for; every compared variant has its card.

### L3 — One language per study (R4, every occurrence)

Wave W2 (needs D4). Owner of the translations in `junior.py` and of the panel's language
labelling.

#### R4 — Inventory: where each text comes from

| # | Text | Source | Language today | Seen in |
|---|---|---|---|---|
| T1 | Panel labels, headings, buttons | `media/copy*/` | panel language | panel |
| T2 | Step titles and questions | `state.STEPS` via `junior.step_text` | study language in `status`; **English in the `init` payload** (`commands.py:2072`: `st.derive_plan(snapshot)` is not localized; observed: a French Hotel study's `init` returns "Discover the data") | agent, panel |
| T3 | `junior_message`, `junior_digest`, `recommended.why`, `question`, limits' `junior_text` | `junior.py`, `audience.py` | study language | agent, panel, report |
| T4 | Case facts (`prediction_time`, `intended_use`, `decision`, `observation_unit`…) | `case.yaml` `facts[].value` | **English only** | `recommended.value` of the prediction moment (`junior.py:528-536`), the summary's `goal`, the panel's "En bref" when the agent copies it into `--value` |
| T5 | Special-value `meaning` | `case.yaml` `special_values[].meaning` (`hotel-booking/case.yaml:850-896`) | **English only** | data card, EDA "Valeurs spéciales" table ("Sens" column) |
| T6 | Variable `group` names, availability `source` | `case.yaml` | **English only** (`labels.fr` exists for the description only, CASE-CONTRACT §Variables line 163) | data card, panel |
| T7 | EDA `question`, `note`, warnings | registered values, `eda.QUESTIONS` (`eda.py:584-603`, `question` 606-617) | **English only** | EDA cards' titles ("How many development rows carry each special value…") |
| T8 | `model_selection`, shortlist sentences | `trials.TEXTS` | both (`texts`) | panel Evidence |
| T9 | Restatement and its label | the agent (`--restatement`, `--restatement-fr`) | junior's language | panel Decisions, report |

The intermittence the owner saw ("some cards are right, some are not") follows from this table:
a card mixes T1 (panel language) with T2/T3 (study language), T4–T7 (English) and T9 (the
junior's language).

#### Specified behaviour

1. **Engine texts in the study language (T2, T7).** `init` returns the localized plan (the same
   `junior.step_text` path as `status`). EDA questions, notes and warnings get a junior form at
   read time in `junior.py` (keyed by activity, column, task and `rows_word`, so old results
   translate too); the panel's EDA payloads carry `question_junior` in the study language next
   to the stored `question`. `eda.py` is not edited (§2.3).
2. **Case texts (T4–T6).** By D4:
   - **Option A (recommended): a translation sidecar** `use-cases/<id>/case.l10n.yaml`
     (`schema: hypotrail.case_l10n/1`; `facts.<id>.fr`, `special_values[<column>,<value>].meaning.fr`,
     `variables.<name>.group.fr`, `variables.<name>.availability.source.fr`), generated by
     `build_case.py`, recorded with its sha256 at `init` for new studies and verified like the
     case file; it changes no case byte, so existing studies stay current. A study without a
     recorded sidecar shows English (unchanged).
   - Option B: French fields inside `case.yaml` (simpler contract; every existing study on that
     case reports `sources_changed`, the owner's Hotel study included).
   - Option C: no case change; the panel shows the junior-language restatement instead of the
     raw value. Partial: T5–T6 stay English.
   With A or B, `recommended.value` of the prediction moment is in the study language, so the
   value the agent records is French in a French study.
3. **The panel's language switch (the other direction).** By D4b:
   - **Recommended:** the engine gives `texts: {en, fr}` next to each junior text the panel
     shows (step titles, `junior_message`, limits' `junior_text`, EDA `question_junior`,
     special-value meaning, as T8 already does); the panel shows the one of its language. The
     agent's restatement (T9) is shown in the panel's language when the proposal has that label
     (`labels`), else as written with `lang` set and a small marker "(wording of the chat, in
     French)" / "(formulation du chat, en anglais)".
   - Alternative: the panel shows engine texts in the study language with a one-line notice.
4. **No English in a French study's junior-facing text** becomes a measured check (J-LANG, §5.3).

#### L3 contracts

CASE-CONTRACT: new section "Translations" (option A) or `fr` fields (option B);
CLI-CONTRACT §3.3 (audience): `texts` and `question_junior`; CLI-CONTRACT §3.1 (`init` plan
localized). CLI-CONTRACT-COMPANION: the EDA payload key.

#### L3 compatibility

Option A keeps every existing study current. The `init` plan text changes for new French
studies only (the English payload is unchanged). Panel fixtures recaptured in both languages.

#### L3 tests

- Unit: `test_every_eda_question_has_a_french_form` (every `QUESTIONS`, `REGRESSION_QUESTIONS`,
  per-column forms, the development-rows wording); `test_init_plan_is_in_the_study_language`;
  `test_case_l10n_is_verified_and_optional` (A); `test_every_case_text_shown_to_the_junior_has_a_french_form`
  for Hotel, Bank full, Auto MPG, Online Shoppers, Bank.
- Language scan: a walkthrough of a French study (synthetic, Auto MPG, Hotel structural steps)
  runs `graders_v03.foreign_sentences` over every junior-facing field of every payload
  (`junior_*`, `recommended.why`, `question`, `pause.*`, `choice_options[].label`,
  `question_junior`, special-value meanings); identifiers and quoted data values excepted.
- Panel: Playwright, panel FR on French captures and panel EN on English captures: no
  sentence of the other language in the DOM (extends `test_webview_wp_e3_copy.py`);
  `copy-fr.test.js` parity.
- Register: `test_v03_french_register.py` on the new French texts.

#### L3 acceptance

A French study's junior-facing texts are French everywhere (chat payloads, panel, report,
notebook headings), quoted data values and identifiers aside; the panel's language switch
changes every text it shows or labels the ones it cannot change.

### L4 — Visible progress during long runs (R9, R10 level 1)

Wave W1. Owner of `executions.py`/`cli.py` progress and of the Copilot `RUN_NOTICE` text.

#### R10 — The terminal shows nothing until the end

- **Evidence.** `hypotrail run fit.variant:2 … 2>/dev/null`: nothing until it ends. On Hotel,
  fits take minutes (ADR 0007 consequences) and `diag.binary` about 4.5 minutes
  (V0.3-DECISIONS H8).
- **Root cause.** The engine prints one JSON document at the end (`cli.emit`, `cli.py:421-427`);
  `executions.py` has no progress; CLI-CONTRACT §1 (line 257): "Nothing is written to stderr on
  a handled outcome", and tests pin it (`flowkit.hyp` asserts `stderr == ''`, `flowkit.py:71`;
  `test_cli_decisions.py:39`, `:722`; `test_result_replacement.py:59`;
  `companion_contract.py:341`). The agent added `2>/dev/null` on its own (the templates never
  mention stderr).
- **Specified behaviour.**
  - `run … --progress` (new flag on `run` only): progress lines on **stderr**, plain words in
    the study language, never on stdout; stdout stays exactly one JSON document, identical with
    or without the flag (except nothing). Without the flag nothing changes (the stderr clause
    and its tests hold).
  - Level 1 (W1, no fingerprinted module): one line when an activity starts, a heartbeat at
    least every **10 s** while it runs (D12), one line when it ends, with elapsed time:
    "Modèle logistique · démarré", "Modèle logistique · en cours · 40 s",
    "Modèle logistique · terminé en 1 min 12 s". Activity words from `audience.activity_words`
    (EN/FR). A heartbeat thread in the `run` path (`executions.py`, not fingerprinted); it never
    touches the study state.
  - Interactive terminal: when stderr is a TTY, the heartbeat rewrites one line (carriage
    return); otherwise one line per heartbeat. No new dependency (`tqdm` is only a transitive
    lock entry, `uv.lock:1879`; not used).
  - Level 2 (fold by fold, variant by variant: "Modèle logistique · pli 2/5 · 14 s",
    "Variante 2/3 · pénalité 3/8") needs calls inside `fit.py`/`diagnostics.py`: **L8**.
  - The panel never passes `--progress`, so its processes stay silent on stderr; its
    `execFile` `maxBuffer` (16 MB, `lib/cli.js:18`) also bounds stderr, so unbounded progress
    would be a risk there.
  - Agent (shared, slot-free): the commands block shows `run ACTIVITY … --progress`; one line:
    "Keep stderr: never add `2>/dev/null`."
- **Contracts.** CLI-CONTRACT §1 (Output row): "except the progress lines of `run --progress`
  on stderr"; §8.1 (the flag).

#### R9 — No narration while the models run

- **Evidence.** The chat shows only "Ran uv run …", "Read content.txt", "Evaluating".
- **Root cause.** The round-9 Copilot rule `FLAVOUR_TEXTS[COPILOT]['RUN_NOTICE']`
  (`agent_files.py:93-97`): "run announcements go in the final message of the turn, never before
  a tool call".
- **Specified behaviour (Copilot slot).** "Before each major step write one short line ('Je vais
  maintenant ajuster le modèle de référence.'), and after it one line with its result ('Le
  modèle de référence obtient …' cited from the output). These lines are visible while the turn
  runs and folded afterwards, so everything the junior must keep (results, the pause, the
  question) is repeated in the final message or the picker. Use the `todo` tool for the turn's
  major steps (baseline, logistic model, diagnostics), ticked as each one ends." (`todo` is
  already in the agent's tools, `copilot-agent.md.in:4`.) Claude Code copy unchanged (its
  `RUN_NOTICE` already asks to state what will be computed before runs).
- **Option.** D13: allow progress lines before tool calls in Copilot (recommended) vs. keep the
  round-9 rule.

#### L4 tests

- Unit/simulated: `test_progress_goes_to_stderr_only` (stdout JSON byte-identical with and
  without `--progress`, except timing-free content); `test_heartbeat_at_least_every_10_s` (a
  monkeypatched slow activity on the synthetic case; measured gaps); `test_no_progress_without_the_flag`
  (`stderr == ''`, the existing tests unchanged); `test_progress_words_in_the_study_language`.
- Panel: `cli-argv.test.js`: no builder passes `--progress`.
- Templates: `--progress` in the commands block; "never `2>/dev/null`"; the Copilot narration
  slot; Claude Code copy unchanged.
- **Journey check J-PROG** (§5.3).

#### L4 acceptance

During every run longer than 10 s, the terminal shows a progress line at least every 10 s in
the study language; in Copilot the chat says what starts and what each major step gave; stdout
and the panel are unchanged.

### L5 — Recommendations that read the evidence (R5, R7, R13, R12, R14, R15)

Wave W2 (needs D5–D11). No fingerprinted module (§2.3); the parts that need one are in L8.

#### R7 — The preparation is "after looking at the target" by construction

- **Evidence.** "Ce choix vient après 2 regards sur la cible. Il peut rendre les chiffres de
  développement un peu optimistes" while the owner's choice came from the target-free quality
  check; later "Il y a eu 3 regards sur la cible." without explanation.
- **Root cause.** WP-A9 M1: `governance.normalize_preprocessing` stamps `data_contingent` when
  any target look came before the proposal (`governance.py:206-237`, `looks_before` from
  `governance.ledger`, 100-135; `commands._normalized_preprocessing`, `commands.py:1209-1224`).
  The binary plan's exploration step runs `eda.target_rate` and `eda.special_values` (both in
  `TARGET_ACTIVITIES`, `governance.py:57-64`) before the preprocessing pause
  (`state.py:255-266`, `FULL_STEPS` 394-399; regression `eda.target_summary`, 298-308). So every
  study's preparation is data-contingent. (The notes name `eda.target_summary` for Hotel; in a
  binary study it is `eda.target_rate`.)
- **Specified behaviour.**
  1. **Plan generation `structural_first`** (D5, recommended), for studies created after the
     change (`init` writes `exploration_order: "structural_first"`; absent means today's plan):
     … `split`, `success_criterion`, **`structural_eda`** (activities: `eda.quality`; reads no
     target), `preprocessing`, `train_eda` (the target looks: `eda.target_rate` or
     `eda.target_summary`, `eda.special_values`), `models` …. The preprocessing step requires
     `structural_eda`; `models` keeps requiring `preprocessing`. The WP-A9 M1 rule is unchanged:
     a preparation proposed after a target look is still stamped, so a junior who explores the
     target first still sees the stamp.
  2. **Explain the stamp everywhere** (both generations): `data_contingent_reason.junior_text`
     in the study language: "Cette préparation est proposée après 2 regards sur la cible (le
     taux d'annulation, les valeurs spéciales). Ce n'est pas une erreur : c'est noté parce
     qu'un choix guidé par la cible peut rendre les chiffres de développement un peu
     optimistes." The agent relays it (rule 3's preprocessing paragraph shrinks, §2.4); the
     restatement no longer needs the bare clause "choisie après avoir regardé la cible".
  3. **Glossary term `target_look`**: "Look at the target: an analysis that read the variable to
     predict. The more looks, the more a pattern found among them can be chance." /
     "Regard sur la cible : une analyse qui a lu la variable à prédire…". The digest and
     `eda_looks` texts introduce it at first use (term first, then the study's example: "ici, le
     taux d'annulation et les valeurs spéciales"). The study's glossary copy is written at
     `init` and never overwritten (`agent_files.install`), so only new studies get the term in
     their copy; the engine's texts carry it in all.
- **Contracts.** CLI-CONTRACT §3.1 (step ids: `structural_eda`), §11.2 (EDA governance: the
  order), §3.2 (`data_contingent_reason.junior_text`); JUNIOR-WORKFLOW "Useful EDA" (structure
  before the target).

#### R5 — The preparation draft ignores the quality check

- **Evidence.** "la préparation par défaut, sans transformation" recommended while the quality
  overview showed `lead_time` 0–737, very high `adults`, many rare `agent`/`company` codes;
  `eda.quality` ran only because the owner asked.
- **Root cause.** `state._propose_action` always drafts `governance.DEFAULT_PREPROCESSING`
  (`state.py:1437-1450`); `junior._recommended` explains it as "changes nothing… nothing is
  tuned on the outcome" (`junior.py:557-563`); nothing reads `eda.quality`; the fixed pipeline
  (median imputation and scaling, most-frequent imputation and one-hot,
  `contracts/recipe.py:112-114`, `code_cells.py`) is never shown as "what already happens".
  `eda.quality` stores min/max, cardinality and rare categories (< 30 rows, `RARE_CATEGORY_ROWS`
  = `MIN_GROUP_ROWS`, `eda.py:61`, `569`) and declared-range breaches (`eda.py:701-776`), no
  quantile or skewness; `eda.distribution:<column>` stores a `skewed` flag for a numeric column
  (target-free when the column is not the target).
- **Specified behaviour.**
  - The engine drafts the preparation from current target-free results (view layer, not
    fingerprinted): `next_action.default_value` becomes the drafted value, with
    `motivated_by: [<eda.quality result id>, <eda.distribution ids used>]` and
    `recommended.reasons` (one per parameter: `{parameter, column, rule, evidence: {result_id, path}}`);
    `next_action.alternatives` holds the default preparation as the comparison option
    ("Sans transformation : rien n'est ajouté, pour comparer"). Under `structural_first` the
    draft is **not** data-contingent.
  - Draft rules (D6; recommended thresholds, open to the owner):
    1. rare categories: when a categorical candidate has at least 20 distinct values and its
       rare categories (fewer than 30 rows) hold at least 1 % of the rows → group rare
       categories (until L8: the global `rare_category_min_rows: 30`, which applies to every
       categorical column, and the reason says so; after L8: per column);
    2. missing values: a candidate with at least 5 % missing cells → `missing: {column: "indicator"}`;
    3. caps: a numeric candidate with values outside the range the case declares
       (`n_above`/`n_below` > 0) → cap at the training quantiles [0.005, 0.995];
    4. signed log: a numeric candidate whose current `eda.distribution` says `skewed: true` →
       `log_transform`; the structural step names `eda.distribution --column C` (target-free) for
       the numeric candidates the junior or the draft needs (at most three, D6); after L8 the
       quality result carries quantiles and skewness and the per-column runs are no longer needed.
  - The digest says what the fixed pipeline already does, in one sentence ("Dans tous les cas,
    le modèle remplace une valeur manquante par la médiane ou la catégorie la plus fréquente,
    met les nombres à la même échelle et code chaque catégorie en colonne 0/1.").
  - Rare grouping for `agent`/`company` as the junior asked (O4) is recordable per column only
    after L8 (R6); until then the agent says plainly that the rule applies to every categorical
    column (O4 shows it already does).
- **Option.** D6 (rules and thresholds; whether the draft or the default is the recommended
  value). Recommendation: the draft is the recommended value when at least one rule fires; the
  default stays one click away as the comparison option.

#### R13 — The drafted variant ignores the diagnostics' signals

- **Evidence.** Only the tuned penalty was drafted although the diagnostics flagged non-linear
  `lead_time` and behaviour varying by month and meal plan; 32,049 rows make the penalty matter
  little.
- **Root cause.** `trials.draft` always returns one `tuned` variant (`trials.py:414-418`), used
  by `state.default_variant` (`state.py:1488`) through `b1_default_value` (1589-1604); WP-F1
  F1.1 keeps the candidate linear and a family optional. `trials.shortlist` already computes
  `recommendation: "compare_nonlinear"` from the linear checks (`trials.py:650-694`).
- **Specified behaviour (D9).** In the view layer (where `model_families` is built), at the
  `model_variant` proposal: when `model_families.recommendation == "compare_nonlinear"`, the EBM
  is allowed and the budget has at least two trials left, `default_value` is
  `{variants: [tuned, {kind: family, family: ebm, question}]}` with the EBM's question in the
  study language naming the flag ("Les formes de `lead_time` et l'effet du mois que le modèle
  linéaire ne suit pas comptent-elles ?"); otherwise the tuned penalty alone (today's draft).
  `recommended.why` states the signal and the cost: each variant spends one trial of three and
  adds selection optimism. The proposal is stamped `data_contingent` as today
  (`trials.data_contingency`, `commands.data_contingency`). Under `review-v1` the EBM variant
  carries `origin: diagnostic_informed` and the current diagnostic's id (as
  `commands.validate_variant` requires).
- **Contracts.** CLI-CONTRACT §14 (the drafted value); ADR 0007 note under decision 5 (the
  engine drafts the glass box when flagged; the shortlist is unchanged); JUNIOR-WORKFLOW
  "Variants and model families" already says a family is proposed only when flagged.

#### R12 — A calendar year as a predictor under a temporal split (to discuss)

- **Evidence.** The EBM ranks `arrival_date_year` among its terms (0.200) while the folds and the
  final test are temporal.
- **Root cause.** `arrival_date_year` is a feature `available_at_prediction`
  (`hotel-booking/case.yaml:194-206`); nothing marks it as a calendar trend. (Auto MPG's
  `model_year` is the case's `time_column`, role `time`, not a feature.) AGENTS.md: a column
  name alone does not establish meaning, so the engine must not detect it by name.
- **Options (D8).** (a) **recommended**: a case declaration `variables[].calendar: year`
  (CASE-CONTRACT additive), and an engine advisory when a declared calendar-year feature is
  kept under a temporal split: a sentence in `recommended.why` of the feature availability and
  in the diagnostics' digest ("keep the month and the week; the year can only extrapolate");
  shipped with the next Hotel case revision (D4: under option A of D4 it still edits
  `case.yaml`, so it waits for a case revision the owner accepts); (b) a skill paragraph only,
  like the regression "Why not use the time column" (`SKILL.md:92-95`), about 40 words; (c)
  default availability `uncertain_excluded` for a declared calendar year under a temporal
  split (changes a decision draft; heavier).

#### R14 — The boosting family under a name the junior does not know

- **Root cause.** `trials.FAMILY_WORDS` says "le gradient boosting par histogrammes"
  (`trials.py:114-119`).
- **Specified behaviour.** `model_families.families[].junior_words` (view): "boosting d'arbres
  (même famille que XGBoost et LightGBM)" / "tree boosting (the same family as XGBoost and
  LightGBM)"; `model_families.not_offered`: `[{name: "random forest", why}]` with one line "une
  forêt aléatoire fait en général moins bien qu'un boosting réglé sur des données tabulaires, et
  une variante de même nature dépenserait un essai pour peu d'information nouvelle". The agent
  relays them (no template words beyond the relay). D10.

#### R15 — A model outside the catalogue gets a bare refusal

- **Root cause.** `trials.check_value` returns "family is one of ebm, hgb (the linear model is
  the candidate)." (`trials.py:268-270`); `commands.validate_variant` raises `invalid_value`
  with it (`commands.py:619-626`).
- **Specified behaviour.** Same code `invalid_value` (no new code); `commands.validate_variant`
  adds, when the problem is an unknown family: `details.reason: "family_not_in_catalogue"`,
  `details.asked`, `details.closest_family` (`hgb` for random forest, XGBoost, LightGBM,
  CatBoost; `ebm` for a neural network, an SVM, k-NN, a GAM, or anything else, as the readable
  non-linear family), `details.workbench: "notebooks/workbench.py"`, and
  `details.junior_message` (study language): why the catalogue is closed in the junior's words
  (each family needs a fixed tuning grid, a trial of the budget, a final-test evaluation, and
  notebook cells that recompute it), the closest family and why, and the workbench for a
  personal exploration on the development training rows that is not study evidence (not
  compared, not chosen, not final-tested, not reported as a result). The workbench starter cell
  is unchanged (it already loads the development training rows) **(to check in the acceptance
  scenario)**.
- **Acceptance scenario** S15 "The junior asks for an SVM" (Claude Code, opt-in): the agent's
  answer relays `junior_message`, offers the closest family within the budget, points to the
  workbench; nothing recorded, no trial spent. D11.

#### L5 compatibility

`structural_first` applies to new studies only; an existing study keeps its plan, its open
proposals, its drafted values. Additive keys (`alternatives`, `recommended.reasons`,
`junior_text`, `junior_words`, `not_offered`, refusal details). Glossary: new term; studies'
glossary copies unchanged.

#### L5 tests

- Unit: `test_structural_first_plan_order` (new study: `eda.quality` before the preprocessing
  proposal, no target look before it, `data_contingent` false for a draft motivated by
  `eda.quality` only); `test_an_existing_study_keeps_its_plan` (a state without
  `exploration_order`, plan identical to today's, by fixture);
  `test_preprocessing_draft_rules` (each rule fires and does not fire at its threshold; reasons
  cite registered paths; the draft is accepted by `check_preprocessing`);
  `test_draft_variant_adds_the_ebm_when_flagged` (flags → two variants; no flag → tuned only;
  budget with one trial left → tuned only; `interpretability: required` and the EBM still
  allowed; review-v1 origin); `test_family_refusal_teaches` (SVM, random forest, XGBoost →
  closest family; junior message EN/FR; nothing recorded, budget unchanged);
  `test_model_families_junior_words`.
- Walkers: rounds 4/5/6 and the Hypothesis state machine (`libraries/test_hypothesis_state_machine.py`)
  on a `structural_first` study, with the drafted preparation and the drafted variants proposed
  as given.
- Exposure: `test_structural_eda_records_no_target_look` (ledger `target_looks` 0 before the
  preprocessing proposal; exposure recorded as `train_eda` without the target column).
- Templates: the relays; word ledger.
- Acceptance: S8 (preprocessing) and S13 (variants) graders updated for the new drafts; new S15.

#### L5 acceptance

In a new Hotel study the quality check runs before the preparation is proposed; the proposal
cites what it read and is not data-contingent; the variant draft follows the diagnostics; the
boosting family is named as the junior knows it; an SVM request gets an answer that teaches.

### L6 — A report that reads as an explanation (R8)

Wave W2 (needs D14).

- **Evidence.** The owner finds `reports/study.html` hard to follow and asks for a table of
  contents and a narrative "notebook of someone who explains the study end to end", with the
  evidence inline.
- **Root cause.** The report concatenates sections by kind (`render_html.py:1608-1615`): verdict,
  objective, data, charts, plan, decisions, evidence, comparison, variants
  (`render_trials.section`), diagnostics (`render_diagnostics.section`), not yet defensible,
  understanding, facts, history, surfaces, annex. Decisions and their evidence are far apart.
- **Specified behaviour (D14, a mockup on Hotel first).**
  - Order: the verdict card (kept first), then chapters: 1 the question and the data; 2 the
    framing (prediction moment, availability); 3 how it is evaluated (split, criterion); 4 what
    the exploration showed (structural first, then the target looks with their count); 5 how the
    variables are prepared and why; 6 the models and their comparison (baseline, candidate,
    variants, selection); 7 the decision rule (binary) or the model choice; 8 the final test; 9
    the conclusion and its limits; annex (raw tables, history, facts).
  - Each chapter: the choice (the junior's words, the basis: endorsed, restated, delegated, or
    automatic under L9), why, the evidence inline (the chart or figure with its `data-result-id`
    citation), and what remains uncertain. A chapter not reached says "not executed yet".
  - Navigation: a sticky left table of contents (anchors per chapter, current chapter marked
    without colour alone), collapsed into a top menu below 600 px; offline, no script required
    to read (`details`/anchors), no fake controls.
  - Kept: the anchors `r-<result_id>` (ADR 0004 decision 4), every number a citation,
    `hypotrail check` tracing, determinism, the study language for static labels
    (`report_fr.yaml`).
- **Contracts.** CLI-CONTRACT §8.3 and §11.5 (report sections); ADR 0001 is unaffected (the
  notebook).
- **Tests.** `test_render_html.py`: determinism, every cited value equals the registry value,
  no fake controls, offline (`test_html_offline.py`, Playwright: TOC anchors work offline, no
  horizontal overflow at 420 px, sticky nav at 1280 px); `test_check_findings.py::test_rendered_study_is_clean`;
  a new `test_every_chapter_holds_its_decision_and_evidence`; French report: no English
  sentence (J-LANG). No panel baseline is involved.
- **Acceptance.** The owner reads the Hotel report of the rehearsal end to end and can follow
  each choice to its evidence without scrolling elsewhere (§5.4 step 16).

### L7 — Conclusion and hand-over (R17, R18, R19 integration, the next step after the study)

Wave W1 (R17, R18 after R19 merges, `after_study`), with NR-19 (§6) as its validation.

#### R17 — A wrong limit in the closing message

- **Evidence.** "Ni colonne de temps ni identifiant d'entité : l'étude ne peut pas vérifier une
  dérive dans le temps…" in a study whose final test is temporal.
- **Root cause.** `state.py:1737` lists `time_column` and `group_column` when their value is
  `null`, without reading the declared `order`; the text (1756-1760) and its French form
  (`junior.py:320-323`) name both whatever is missing. Hotel declares `structure.time_column:
  null` (`case.yaml:908`) and `order: {by: line}` (`case.yaml:930`); verified on a scratch Hotel
  study: the item is present with `missing: ["time_column", "group_column"]` and
  `final_test.method: "temporal"`.
- **Specified behaviour.** `time_column` is missing only when the case declares neither a time
  column nor an `order` (`partition.method != "temporal"` and no order); the text names only
  what is missing: "Les données n'ont pas d'identifiant d'entité : l'étude ne peut pas vérifier
  qu'une même entité apparaît dans plusieurs échantillons." When the order is declared, a
  separate sentence may say what the temporal final test can show (a shift between periods, not
  its cause). The id `no_time_or_entity_identifier` and its `missing` key are kept (contract
  list, panel `copy*/junior.js`).
- **Tests.** `test_state.py` (both, either, none missing; order declared or not); FR text;
  the panel's limit copy.

#### The next step after the study ("comment lancer le déploiement")

- **Specified behaviour.** On `next_action.kind == "done"`, `after_study`: `{handoff: {command},
  azureml: {supported, reason, plan_command}, cloud_status: "not_qualified"}`. `supported` is
  read from the template's support matrix for the chosen model's task, family and output
  (`team-azureml-v1`; after R19, binary logistic too); `reason` says why not otherwise
  ("this template does not export a boosting model yet"). The skill's conclusion section: "At
  `done`, say what comes next from `after_study`: the handoff pack; the Azure ML export plan
  only when `supported`; and that no Azure job or endpoint has ever been run." The panel's
  Learn & hand off tab shows the same, read only (the panel's export stays W7 handoff only).
  D15.

#### R18 — `export azureml` without `--expected-revision`

- **Root cause.** The `export` parser defines `--expected-revision` with `default=None`
  (`cmd_export.py:90`, shared with `handoff`, where it is optional); `export_azureml` refuses
  `None` with "--expected-revision must be a revision number." and "Read the revision with
  hypotrail status first." (`exporters/azureml/command.py:59-62`).
- **Specified behaviour.** Missing flag: `invalid_arguments`, message "--expected-revision is
  required: the study at <path> is at revision 41; add --expected-revision 41.",
  `details: {path: "expected_revision", reason: "missing", current_revision: 41, study: <path>,
  remediation}` (read-only read of the revision). A malformed value keeps today's message, plus
  `current_revision`. The refusals `model_not_captured` and `capability_not_supported` (no
  recipe) name the study path and its revision, so a wrong folder is obvious (R19 notes). One
  line in AZUREML-EXPORT-V1 §5 about a foreign `VIRTUAL_ENV` that uv ignores.
- **Tests.** `framework/tests/exporters/azureml/test_export_command.py`: missing, malformed,
  stale revision; the details keys; codes unchanged.

#### R19 — Integration of the binary export (delivered by the other agent)

Not designed here. The batch requires, after R19 merges and before W2: the deep validation
**NR-19** (§6), the `after_study.azureml.supported` read from the extended matrix, and the
documentation of the support matrix where the junior meets it (the `done` step, the report's
hand-off, the panel's Learn & hand off tab, the README quickstart). Note that the owner's
existing Hotel study was captured before R19: if R19 changed any module of the capture's
fingerprint, its capture is no longer current and, its final test being opened, its export is
recipe-only (risk K3).

#### L7 acceptance

The closing message lists only true limits; at `done` the agent says what comes next and offers
the export only when supported, with its honest status; a missing `--expected-revision` names
the revision to use; NR-19 green.

### L8 — Fingerprinted engine changes (R6, R5 quantiles, R10 level 2)

Wave W3; recommended **after the workshop** (D19) unless R6 is required for it.

- **R6 — per-column rare grouping.** `rare_category_min_rows` is one integer
  (`governance.PREPROCESSING_KEYS`, line 40; check 167-170; applied to every categorical column,
  `fit.py:159-171`; recipe `contracts/recipe.py:99-102`; runtime
  `hypotrail_runtime/preprocess.py:64-96`, `165`). Specified (D7): the value is an integer (all
  columns, as today) **or** a mapping `{column: min_rows}`, like `missing`
  (`governance.py:12`, 156-165); `fit.py` applies it per column; the recipe's `rare_category`
  step becomes version 2 with per-column `min_rows`; the runtime accepts versions 1 and 2;
  `confirm.py`/`concepts.py`/`view.py`/`render_html.py`/`code_cells.py` and the panel's
  `copy*/junior.js` say it per column. The training-mode concept map (`concepts.py:235`)
  covers the mapping.
- **R5 — quality quantiles.** `eda.quality` ranges gain `quantiles` (0.01, 0.5, 0.99) and
  `skewness` per numeric column (additive keys); the L5 draft then uses them and drops the
  per-column distribution runs.
- **R10 — level 2 progress.** A progress callback in `fit.py` (fold, variant, inner grid) and
  `diagnostics.py` (bootstrap replicates), no-op without `--progress`.
- **Attestation.** `governance`, `fit`, `eda`, `activities` (if dispatch changes) and the recipe
  change their digests. One set of edges in `code_compat.ATTESTATIONS`, each scoped to the
  activities whose computed values are unchanged for every value an existing study can hold
  (an integer `rare_category_min_rows`; quality values only gain keys, as the WP-F1 precedent
  accepted in ADR 0007 consequences), with evidence from `code_compat_evidence.py` (old engine
  `ba4819c`-era vs new, the same commands, byte comparison). `predictor.capture` is not
  attestable: existing captures become not current (risk K3); D19 asks the owner to accept it.
- **Tests.** `test_code_compat_library_v1.py` pattern for the new edges (opt-in byte comparison
  with `HYPOTRAIL_COMPAT_OLD_PYTHON`), `test_reliability_j4_j7.py::test_exact_compatibility_is_directed_scoped_and_not_transitive`,
  per-column grouping unit tests (fit, recipe v1/v2, runtime, notebook cells recompute it),
  exporter tests with a per-column recipe, NR-19 again.

### L9 — Automatic mode, reviewed at the end (R20)

Wave W3. ADR first (ADR 0005 and ADR 0006 amendments), then code.

- **Owner decision already taken (2026-10-26).** Both variants, chosen at launch: "auto until the
  final test" (default) and "full auto (demo)", which also opens the final test and concludes,
  with a report banner and every later change marked as made after the final test.
- **Specified behaviour (details for D17).**
  - `init --automation until_final_test|full_demo` writes `state.automation`; absent means no
    automation (every existing study). It cannot be set later to `full_demo`; it can be ended
    (one way, to the confirmation mode in force) with the junior's words (`mode set`-like
    command `automation stop --user-words`), recorded in `mode_history`.
  - The agent records each decision as automatic: `decide confirm --basis automatic` (new basis,
    distinct from `endorsed`, `restated`, `explicit` and `delegated_default`; `actor: assistant`;
    `user_words: null`). Accepted only when `state.automation` covers the decision:
    `until_final_test` covers every decision before `final_test`; `full_demo` also covers
    `final_test` and `conclusion`. Refused otherwise (`ambiguous_confirmation`, reason
    `automation_not_set` or `automation_does_not_cover`; no new error code).
  - When `recommended` is null, the engine gives the automatic value (`next_action.auto_value`,
    no free choice by the agent): model choice = the selection's one-standard-error pick (legacy
    profile) or the declared-metric winner (review-v1), else the candidate; policy = the case's
    scenario share when declared, else the recommended rule; conclusion (demo only) = from the
    criterion judged on the final test: `met` → adopt, `not_met` → `keep_baseline`, `uncertain`
    or `not_assessed` → `inconclusive`, with a text drafted by the engine in the study language.
  - Review at the end: `view.review_queue` lists every decision whose current confirmation is
    `automatic`; the junior adopts or changes each one in their own words (the normal propose and
    confirm, guided rules); a change invalidates as usual and, after a demo opening, is marked
    "after the final test" (`final_test.changed_after`). `not_yet_defensible` gains
    `automatic_decisions_to_review` while the queue is not empty.
  - Banners: report, notebook header and panel (read only): "Étude automatique : à relire, pas
    encore défendable" / "Automatic study: not defensible until reviewed" while the queue is not
    empty; in `full_demo`, permanently "Le test final a été ouvert automatiquement" /
    "The final test was opened automatically" (the opening cannot be redone).
  - The final-test opening by automation exists only in `full_demo` and only with
    `--basis automatic`; `--basis delegated_default` stays refused for `final_test` in every
    case (`delegation_not_allowed`).
  - Exposure, budget and sealing are unchanged: automation runs the same activities through the
    same commands.
- **Contracts and ADRs.** ADR 0005 amendment (automation: a launch choice, a basis, its review,
  its limits); ADR 0006 amendment (the demo opening; the opening record carries `basis:
  automatic`); CLI-CONTRACT §5 (basis), §3.1 (`auto_value`, `review_queue`), §4.1, §7 (reasons);
  CLI-CONTRACT-COMPANION (banner reads). AGENTS.md wording "decisions only from the junior's
  words" gains the owner's exception (an explicit automation chosen at launch, reviewed at the
  end) — an AGENTS.md change needs the owner's explicit approval.
- **Tests.** `test_automation_is_set_at_init_only`; `test_automatic_basis_is_never_a_human_basis`
  (credit lines, report, `delegated_decisions` separate); `test_until_final_test_never_opens`;
  `test_full_demo_opens_once_and_banners`; `test_delegation_still_never_opens`;
  `test_review_queue_adopt_and_change` (invalidation, after-final-test marks);
  `test_auto_value_is_accepted_as_given` (walkers); report/notebook banners; panel read.
  Acceptance: an automatic run on Auto MPG (fast) then a scripted review.
- **Acceptance.** An automatic study runs to the model and the rule (or to the conclusion in the
  demo variant) with every decision labelled automatic, the banner shown, and a review that
  turns each into the junior's own decision.

---

## 4. Owner decisions needed

Numbered; each with the recommendation. None is decided silently by this plan.

| # | Remark | Question | Recommendation |
|---|---|---|---|
| D1 | R3 | Picker for every closed question with Copilot (transitions included), or decision pauses only? | Every closed question; open questions stay in text. |
| D1b | R3 | Same rule for Claude Code (`AskUserQuestion`)? | Not in this batch: Copilot only; the Claude Code copy stays unchanged. |
| D2 | R2c | Free choice: pick then adopt the proposal (two steps), or confirm the pick directly for the model choice? | Two steps everywhere; `--channel choice` stays the adoption option only. |
| D3 | R1b | Panel line from what the message shows (`panel.shown`, tab and section, none when nothing new) or the next step's tab? | `panel.shown`; remove rule 6's own mapping. |
| D4 | R4 | French case texts: A sidecar `case.l10n.yaml` (no `sources_changed`), B fields in `case.yaml` (existing studies report `sources_changed`), C panel shows the restatement only? | A. |
| D4b | R4 | Panel language ≠ study language: engine gives `texts: {en, fr}` for junior texts, or a notice only? | `texts: {en, fr}`; agent restatements labelled with their language when no label exists. |
| D5 | R5/R7 | EDA order for new studies: structural check and preparation before any target look (`structural_first`), or keep the order and explain the stamp? | `structural_first` for new studies, and the explanation everywhere. |
| D6 | R5 | Draft rules and thresholds (rare ≥ 20 distinct and ≥ 1 % rare rows; missing ≥ 5 %; caps only against declared ranges; log only with a `skewed` distribution, at most three per-column runs); draft or default as the recommended value? | The thresholds above; the draft is recommended when a rule fires, the default is the comparison option. |
| D7 | R6 | Per-column rare grouping `{column: min_rows}` (contract change, recipe op v2, runtime) and its timing? | Yes, in L8 after R19 and after the workshop; until then the agent says the rule is global. |
| D8 | R12 | Calendar-year predictor: (a) case declaration `calendar: year` + engine advisory, (b) skill paragraph, (c) default `uncertain_excluded`? | (a), shipped with the next Hotel case revision the owner accepts; (b) as a stop-gap only if the workshop needs it before. |
| D9 | R13 | Draft tuned + EBM when the diagnostics flag something (and budget allows), tuned alone otherwise? | Yes. |
| D10 | R14 | Name `hgb` "tree boosting (same family as XGBoost and LightGBM)"; say why no random forest; no random-forest family? | Yes; no new family. |
| D11 | R15 | Refusal enriched (closest family, workbench, why closed); acceptance scenario S15; which family for k-NN or a neural network later (framework development)? | Enrich now; S15; family additions stay out of this batch. |
| D12 | R10 | Progress: explicit `run --progress` (recommended) vs. automatic when stderr is a TTY; heartbeat interval? | Explicit flag; heartbeat every 10 s; fold-level lines in L8. |
| D13 | R9 | Allow short progress lines before tool calls in Copilot (round-9 rule relaxed) with `todo`? | Yes, Copilot only; everything to keep is repeated in the final message or picker. |
| D14 | R8 | Report: the chapter order of L6, a sticky left TOC collapsing below 600 px, verdict first, annex for raw tables; validate a Hotel mockup before implementation? | Yes, mockup first. |
| D15 | next step | At `done`, offer the Azure ML export plan only when the template supports the chosen model, with "no Azure job or endpoint has ever been run"? | Yes. |
| D16 | R18 | Wording of the missing-revision refusal (L7)? | As specified. |
| D17 | R20 | (a) new basis `automatic`, never a human basis; (b) review queue, adopt or change in own words; (c) banner texts; (d) `auto_value` rules when `recommended` is null (one-SE pick or declared winner; scenario share; conclusion from the criterion judged status); (e) the demo opening as an amendment of "never delegated", `full_demo` set at `init` only, `delegated_default` still refused; (f) can automation be stopped midway (one way, junior's words)? (g) AGENTS.md exception wording. | As specified in L9 for (a)–(f); (g) owner to approve the AGENTS.md sentence. |
| D18 | budget | Cap for the rendered Copilot copy (slot weakness), and whether L9's words may raise the 4,000 cap? | Rendered Copilot ≤ 4,400; the 4,000 raw cap stays; L9 frees its own words. |
| D19 | L8 | Run L8 (fingerprinted) after the workshop, accepting that existing captures become not current (opened studies export recipe-only)? | After the workshop; accept for test studies; say it in the handoff. |
| D20 | R16 | The panel's choice card at stage v1 and above only (v0 is one page without Decisions)? | v1 and above; at v0 the page's "next move" says "answer in the chat". |

---

## 5. Journey acceptance (the workshop path)

The primary acceptance of this batch. Two workshop cases: **Hotel booking demand** (discovery,
binary, temporal final test) in French and in English, and **Auto MPG** (regression) in English
and in French, ending with the Azure ML export. Each step says what the junior must see in the
chat, the picker, the panel (tab and section, stage v3), the report, and the notebook.

### 5.1 Clarity and pedagogy criteria (checkable)

| Id | Criterion | How it is checked |
|---|---|---|
| C1 | A statistical term is introduced first (bold, glossary term verbatim, one-line definition), then explained with this study's example, at its first use | `graders_v03.glossary_vocabulary` on transcripts; manual rehearsal |
| C2 | One pause, one message, at most 150 words; the quoted block is never skipped | skill rule; grader on transcripts (word count of the final message or picker question) |
| C3 | Every message that shows or changes something ends with what to look at next (`panel.shown.line`), never pointing at an empty section | J-PANEL |
| C4 | No jargon without explanation: "regard sur la cible", "pli", "hors pli", "dépendante des données", "budget d'essais", "règle d'un écart-type" are defined at first use | term list grader over the junior-facing payload texts and transcripts |
| C5 | One language per study | J-LANG |
| C6 | Every number traced to a registered result, a decision value, the junior's words or the data card | `hypotrail check` (report, notebook-derived text, agent drafts) |
| C7 | No agent-facing text shown to the junior (no `audience: agent` text, no id, no revision number) | `test_integrity_audience.py` patterns; `graders_v03.raw_ids`; panel Playwright scan |
| C8 | The plan and the position are visible (moment and step title) | skill; resume command; manual |

### 5.2 Scenarios

#### J-H — Hotel booking demand, French (repeat in English with the same expectations)

| Step | Chat | Picker | Panel (tab → section) | Report / notebook |
|---|---|---|---|---|
| 0 Data card | ≤ 150 words; **échantillon de développement**, **échantillon de test final (holdout)** defined with this study's counts (32 049, 8 011); no proposal (O1) | "On continue" / "Expliquer d'abord" (R3) | Données et EDA → Fiche des données; group names and special-value meanings in French (R4) | "Les données" section; notebook opens (`marimo run`) |
| 1 Prediction moment | term, explanation, quoted block in French, "Adoptez-vous cette décision ?" | adopt / change / explain (R2) | Décisions → En attente de votre réponse; "En bref" in French (R4) | — |
| 2 Feature availability | block lists every excluded column with its reason | adopt / change / explain | Décisions → En attente; after adoption → Historique des décisions (R1b) | — |
| 3 Transition | one line on what was decided, next step | continue / explain (R3) | no line (nothing new) | — |
| 4 Split, criterion | **validation croisée à k plis**, temporal blocks; criterion options with the base rate and per-1 000 illustration | adopt / change / explain | Décisions → En attente | chapter 3 |
| 5 Structural check (new order, R7) | `eda.quality` question first, counts, rare categories of `agent`/`company`, ranges | — (work between pauses) | Données et EDA → Qualité des données | chapter 4 |
| 6 Preparation (R5) | draft cites the quality check, says what the fixed pipeline does, not data-contingent; comparison option | adopt / change / explain; dismissed → asked again without blame (R2b) | Décisions → En attente | chapter 5 |
| 7 Target exploration | **regard sur la cible** defined at first use (R7); rates with intervals and null band | — | Données et EDA → Valeurs spéciales (French question title, R4) | chapter 4 |
| 8 Fits | narration line before each major step and result after (R9); `todo` list | — | Preuves → Preuves de développement | chapter 6 |
| 9 Diagnostics | confusion matrix 2×2; flags (non-linear `lead_time`, month) | — | Preuves → Diagnostics | chapter 6 |
| 10 Variants (R13, R14) | draft tuned + EBM with the flags and the cost; boosting named "même famille que XGBoost"; random forest line; an SVM request answered (R15) | adopt / change / explain | Décisions → En attente; trials note | chapter 6 |
| 11 Variant fits | progress in the terminal ≥ every 10 s (R10) | — | Preuves → one card per variant (R11) | chapter 6 |
| 12 Model choice (R2c, R16) | options from `choice_options`, none recommended | one option per model | Décisions → En attente: the choice card | — |
| 13 Rule | share 10 % as the exercise's assumption; gain at 5/10/20 % | adopt / change / explain | Et si ? | chapter 7 |
| 14 Final test | opening ritual; final figures first, labelled | adopt / change / explain | Preuves → Test final | chapter 8 |
| 15 Conclusion (R2c, R16, R17) | allowed verdicts only; limits true (no "ni colonne de temps") | one option per verdict | Décisions → choice card, then Historique | chapter 9 |
| 16 Done (D15, L7) | what comes next: handoff pack, export plan if supported, honest status | — | Apprendre et transmettre | the whole report reads as an explanation (R8) |

#### J-M — Auto MPG, English (repeat in French), with the export

Same steps with regression wording (MAE then RMSE, residuals by period; the time column orders
the rows and is not a feature), the model choice with the mean baseline included, then at `done`:
`export azureml --plan` (missing `--expected-revision` names the revision, R18), `--out`, and in
the exported folder `validate --offline`, `predict --parity`, `materialize`, `run-local --mode
rebuild_final_candidate` (AZUREML-EXPORT-V1 §5). Auto MPG runs in seconds per activity (measured
on a scratch study: each fit and diagnostic about 1 s), so J-M is the fast end-to-end check.

#### J-A — Automatic mode (after L9)

Auto MPG, `init --automation until_final_test`: banner, every decision automatic, review queue
adopted or changed in the junior's words, then the opening by the junior.

### 5.3 Measurable checks and how each is automated

| Id | Check | Automated | Manual (Copilot) |
|---|---|---|---|
| J-PICK | A picker on every closed question; none on open ones; dismissed picker asked again | template tests (L1); engine: every `pause` with options has `option_labels`; `choice_options` complete | §5.4 at steps 0, 3, 6, 12, 15 |
| J-PANEL | `panel.shown` names a non-empty section after every write; null after reads/render | new `framework/tests/study/test_journey_walkthrough.py` drives Auto MPG and the synthetic case through the real CLI with `HYPOTRAIL_COMPANION=1`, stage v3, FR and EN, and saves each payload; new `clients/vscode-companion/test/journey.test.js` feeds them to the panel models and asserts the named section renders ≥ 1 item | each step of §5.4 |
| J-LANG | No sentence of the other language in junior-facing text | the walkthrough runs `graders_v03.foreign_sentences` on every junior field; Playwright on the panel (FR captures, EN captures) and on the French report | spot checks |
| J-PROG | A progress line at least every 10 s during runs | `--progress` on a slowed synthetic activity (unit) and a real EBM variant on Auto MPG (gap ≤ 10 s + tolerance) | Hotel fits, timed |
| J-TRACE | Every number traced | `hypotrail check` on the report and the walkthrough's drafted texts | — |
| J-AUD | No agent text shown | payload scan for `audience: agent` text in junior fields; panel vocabulary test | — |
| J-REC | Drafts read the evidence | L5 unit tests on Hotel-like synthetic cases; Hotel structural steps (`eda.quality` is target-free and fast enough) | steps 6, 10 |
| J-REPORT | Report narrative with TOC | Playwright structural (anchors, sticky nav, 420 px) | step 16 |
| J-LIMIT | Only true limits | unit (L7) | step 15 |
| J-EXPORT | Export reachable and honest | NR-19 + J-M | J-M at `done` |
| Agent behaviour | Claude Code acceptance (opt-in, costs model spend): S14 (whole study) rerun on Hotel and Auto MPG with the new templates; S15 (SVM); S16 (`done` then export plan) | `HYPOTRAIL_AGENT_ACCEPTANCE=1`, `scenarios.py`; results labelled "Claude Code acceptance", not Copilot | — |

A heavy Hotel walkthrough to `done` (fits, diagnostics, EBM, capture, opening) is opt-in
(`HYPOTRAIL_JOURNEY_HOTEL=1`): too slow for the gate.

### 5.4 Owner rehearsal script (real Copilot, VS Code, panel on at v3)

Timed, step by step. Set up a fresh study after W2 (and again after W3 for J-A):
`hypotrail init --case use-cases/hotel-booking/case.yaml --study ~/studies/hotel-ws --lang fr`;
open it in VS Code with `HYPOTRAIL_COMPANION=1`, `HYPOTRAIL_COMPANION_STAGE=v3`; select the
**Hypotrail** agent (not Agent mode); confirm `vscode/askQuestions` is enabled in the chat tools
picker. Record for each step: elapsed time, what the chat showed, whether a picker appeared, the
panel line and whether the named section showed the thing, any English text, anything unclear.

| # | Say | Expect (fail if not) | Target time |
|---|---|---|---|
| 0 | "Je veux faire cette étude, par où on commence ?" | data card visible (O1); terms defined; picker continue/explain (R3); "Dans le panneau : Données et EDA → Fiche des données" and the panel shows it in French | 2 min |
| 1 | pick "On continue" | pause 1 with quoted block and picker (O3); panel Décisions → En attente in French, "En bref" French (R4) | 2 min |
| 2 | pick adopt | recorded; next pause with picker; line → Historique des décisions | 2 min |
| 3 | adopt availability; at the split, close the picker without answering, then type "attends, pourquoi 5 plis ?" | the typed question answered; then the picker again; no "ignorée" (R2b) | 4 min |
| 4 | adopt split and criterion | transition with picker (R3) | 3 min |
| 5 | pick "On continue" | `eda.quality` runs first; quality figures with the question first; line → Qualité des données | 3 min |
| 6 | preparation pause | draft cites the quality check (rare `agent`/`company` categories), says what the pipeline already does, not "après avoir regardé la cible" (R5, R7) | 3 min |
| 7 | adopt; continue | target exploration; "regard sur la cible" defined once (R7) | 3 min |
| 8 | "on lance les modèles" | a line before each fit and its result after (R9); `todo` list; terminal progress at least every 10 s, stderr not discarded (R10) | 10–20 min (Hotel) |
| 9 | after diagnostics | confusion matrix; flags explained | 3 min |
| 10 | at the variants ask "et un SVM ? ou XGBoost ?" | the SVM answer teaches (closest family, workbench) (R15); boosting named like XGBoost; random forest line (R14); draft tuned + EBM (R13) | 4 min |
| 11 | adopt; fits run | progress; one Evidence card per variant (R11) | 10–20 min |
| 12 | model choice | picker with one option per model, none recommended (R2c); panel choice card (R16) | 3 min |
| 13 | rule | share 10 % with gain points; Et si ? | 3 min |
| 14 | opening | ritual; final figures first | 5 min |
| 15 | conclusion | picker with allowed verdicts (R2c); panel choice card (R16); limits true (R17) | 4 min |
| 16 | "et ensuite, comment on déploie ?" | handoff and export plan only if supported, honest cloud status (L7); open the report: TOC, chapters readable end to end (R8) | 5 min |

Repeat steps 0–2 and 12–16 in English (`--lang en`, panel EN), and the panel switched to the
other language once (D4b). Then J-M in English with the export commands. Record the session in
`docs/acceptance/runs/` as the previous one.

---

## 6. Non-regression (the safety net)

Behind the journey priority, these guarantees must not move. Each lot runs the chunk of tests
named in §6.3 before merging; the integrator runs the full gate after each merge.

### 6.1 Guarantees, existing protection, and tests to add

| Id | Guarantee | Existing tests | To add in this batch |
|---|---|---|---|
| NR-1 | Final test sealed at `init`, no final row read before the opening | `test_final_test_partition.py::test_bank_final_test_is_a_stratified_fifth_sealed_at_init`, `::test_no_final_test_row_reaches_any_activity_or_result`, `::test_declared_line_order_seals_the_last_rows`, `::test_a_legacy_study_without_partition_loads_runs_and_shows_no_final_test` | the guard test on a `structural_first` study and on an automatic study (L5, L9) |
| NR-2 | Opened once; never by a delegation (except the R20 demo variant if D17e is confirmed) | `test_wp_b1_final_test.py::test_the_final_test_is_scored_exactly_once_and_only_after_the_opening`, `::test_an_interrupted_opening_consumes_the_final_test`, `::test_the_opening_refusals` (`delegation_not_allowed`, line 456), `test_wp_b1_integration.py:194` | `test_delegation_still_never_opens` (also in `full_demo`), `test_until_final_test_never_opens`, `test_full_demo_opens_once_and_banners` |
| NR-3 | Exposure ledger kept, never erased by a new split; target looks counted | `test_exposure.py::test_exposure_is_retained_after_a_split_change_and_overlap_is_reported`, `::test_exposure_ids_are_unique_and_records_append_only`, `test_exposure_kill.py` (three tests) | `test_structural_eda_records_no_target_look` (L5) |
| NR-4 | Decisions only from the junior's words or an explicit delegation; a proposal is never confirmed implicitly | `test_guided_confirmation.py`, `test_confirmation_words.py`, `test_partial_and_offtopic_replies.py`, `test_confirmation_modes.py`, `test_delegation_scope.py`, `test_propose_channel.py` | `test_a_choice_pick_is_never_a_confirmation` (L1); `test_automatic_basis_is_never_a_human_basis` (L9) |
| NR-5 | Stale revision refused; idempotent replays | `test_apply.py::test_replay_is_a_no_op`, `::test_same_key_with_different_signature_is_refused`, `::test_stale_revision_refusal_carries_current_revision_and_diff`, `::test_two_concurrent_clients_confirming_the_same_thing` | — |
| NR-6 | `next_action` never names an action the engine refuses | `test_review_round6_engine.py::test_next_action_is_never_refused_and_settles`, `test_review_round5_engine.py::test_next_action_runs_as_given_from_init_to_done`, `test_review_round4_engine.py::test_every_next_action_after_a_code_change_runs_as_given`, `::test_every_next_action_of_a_delayed_label_study_runs_as_given`, `libraries/test_hypothesis_state_machine.py` | the walkers on `structural_first`, with drafted preparation and variants, `choice_options`, `auto_value` |
| NR-7 | Panel: flag off by default, stage `v0` default, CLI client only, writes W4–W7 only, three Marimo launches only | `scripts/check_layout.py` (`check_companion_client`, `companion_terminal_errors`, `companion_decide_errors`), `test_check_layout_decide.py`, `test_check_layout_launch.py`, `invariants.test.js` INV-1 to INV-15 | `cli-argv.test.js`: no builder passes `--progress`; the R16 card has no control (`decisions.test.js`) |
| NR-8 | Claude Code instructions unchanged where only Copilot is targeted | `test_agent_files.py::test_the_r2_fix_leaves_the_claude_code_copy_unchanged`, `::test_copilot_ends_every_pause_with_the_picker` | extend to L1/L4 slots; a per-lot list of intended shared-line changes checked by a test |
| NR-9 | `next_action.panel` absent when the panel is off (default payload unchanged) | `test_companion_env.py::test_next_action_has_no_panel_by_default`, golden `framework/tests/study/golden/summary_synthetic.json` (`companion_contract.GOLDEN_SUMMARY`) | `shown` absent when off |
| NR-10 | Number tracing | `test_check_findings.py`, `test_check_words.py`, `test_render_html.py::test_every_cited_value_equals_the_registry_value`, `::test_an_untraceable_number_is_refused`, `::test_unknown_number_in_a_content_template_fails_the_render` | the narrative report (L6) |
| NR-11 | Deliverables deterministic; notebook edits preserved | `test_render_html.py::test_report_is_deterministic_and_cites_only_current_results`, `test_render_notebook.py::test_generator_is_deterministic`, `::test_user_edit_is_preserved_byte_for_byte_then_regenerated`, `::test_workbench_is_byte_identical_across_regenerations`, `test_html_offline.py` | report TOC offline (L6) |
| NR-12 | Export integrity: R9AB-1 bindings, package artifact ids, YAML/Hydra | `exporters/azureml/test_review_round9.py` (R9AB-1 tests from line 112), `test_template_layout.py`, `test_mlflow_packaging.py`, `test_export_command.py`, `test_exported_project.py`, `test_end_to_end_real.py`, `test_review_round*.py`, `test_contract_units.py` | R18 details (L7); NR-19 |
| NR-13 | Source compatibility by exact attestations | `test_reliability_j4_j7.py::test_exact_compatibility_is_directed_scoped_and_not_transitive`, `test_code_compat_library_v1.py` (opt-in byte comparison), `code_compat_evidence.py` | a test that W1/W2 change no module of `activities.MODULES` (digests of those modules equal a pinned list at the wave's start); L8 edges with evidence |
| NR-14 | English/French parity of the panel copy; the "vous" register | `copy-fr.test.js` (every key, no digit outside placeholders), `test_panel_labels.py`, `test_webview_wp_e3_copy.py`, `test_v03_french_register.py` | section labels (L2); J-LANG |
| NR-15 | Agent word budget | `test_agent_files.py::test_the_instructions_fit_the_word_budget` | `test_the_rendered_copilot_copy_stays_bounded` (D18) |
| NR-16 | Frozen CLI contract and client key lists | `test_contract_freeze.py`, `clients/vscode-companion/test/test_contract_keys.py`, `test_fixture_drift.py`, `test_contract_companion_e1/e2/e3.py` | contract updates per wave in the same commit |
| NR-17 | One JSON document on stdout; nothing on stderr on a handled outcome (unless `--progress`) | `flowkit.hyp` (`stderr == ''`), `test_cli_decisions.py::test_a_closed_pipe_writes_nothing_to_stderr` | `test_progress_goes_to_stderr_only` (L4) |
| NR-18 | Studies of earlier generations load and run unchanged | `test_case_migration.py`, `test_wp_b1_final_test.py::test_a_study_created_before_wp_b1_has_no_variant`, `test_final_test_partition.py::test_a_legacy_study_without_partition_loads_runs_and_shows_no_final_test`, `test_sources_changed.py` | a study created before the batch keeps its plan and drafts (L5); a case sidecar never makes an older study `sources_changed` (L3) |
| NR-19 | **R19 deep validation** (owner addition): the binary export lands with only its own tests; the batch validates it fully | — | see §6.2 |
| NR-20 | Pixel baselines changed only with the owner's review | `test_webview_gate.py` (structural and pixel) | — (process: every changed PNG reviewed from `.local/baseline-diff/`) |

### 6.2 NR-19 — R19 deep validation (named item)

Run after R19 merges, before W2, and again after L8:

1. The full exporter and library suites: `uv run --project framework python -m pytest -q
   framework/tests/exporters framework/tests/study/libraries` (with the `azureml` group and the
   `diagnostics` and `uncertainty` extras, so nothing skips), and once with
   `HYPOTRAIL_EXPORT_REAL_RUNTIME=1`.
2. The template lint: the exported project's `ruff check src` with the team template's ruff
   0.4.5, and its own `pytest`.
3. MLflow pyfunc parity on a Bank-like and a Hotel-like binary fixture: native vs expected vs
   pyfunc, `rtol 1e-10`, `atol 1e-12`, never relaxed (`test_mlflow_packaging.py` pattern), plus the
   decision rule kept as metadata and not applied by the pyfunc unless R19 says otherwise.
4. The EBM and HGB refusal: `capability_not_supported`, the selected model kept and never
   substituted (`snapshot.py:539-550`).
5. The R9AB-1 integrity checks on a binary export: every test of `test_review_round9.py`
   (plan bound to projection and snapshot, final-test rows refused, an evaluated model from
   another bundle refused, identity overrides refused) parameterised for a binary export.
6. A real export of a Hotel study: plan, export, `validate --offline`, `predict --parity`,
   `materialize --source`, `run-local --mode rebuild_final_candidate`. On a **fresh** Hotel study
   created after R19 (heavy, opt-in) and on the owner's existing study (manual): if its capture
   is no longer current (risk K3), the export is recipe-only and `predict --parity` is not
   available there; the full chain is then proven on the fresh study.
7. Non-regression of the regression export path (Auto MPG): `test_end_to_end_real.py`,
   `test_exported_project.py`, and J-M.

### 6.3 Gate commands and chunks per lot

The full gate (CONTRIBUTING.md, about 1.5 h with the browser and pixel gates):

```sh
uv sync --project framework --group dev --group browser --group azureml --extra diagnostics --extra uncertainty
uv run --project framework python -m playwright install chromium
python3 scripts/check_layout.py
uv run --project framework python -m pytest -q framework/tests/test_pilot_revision.py framework/tests/test_quality.py framework/tests/test_discovery.py framework/tests/test_reliability.py framework/tests/test_classical.py framework/tests/test_env_smoke.py framework/tests/test_synthetic_case.py framework/tests/study framework/tests/acceptance framework/tests/exporters
node --test clients/vscode-companion/test/*.test.js
uv run --project framework python -m pytest -q -p no:cacheprovider clients/vscode-companion/test
```

The top-level legacy tests outside that list (`framework/tests/test_kit.py`,
`test_baselines.py`, `test_decision_v3.py`, `test_drift.py`, `test_ensemble.py`,
`test_residuals.py`, `test_training_sample.py`, `test_discovery_browser.py`) are **not part of
the gate** and fail by design (suspended holdout and production paths, CONTRIBUTING
"Alternative setup"); do not "fix" them by weakening assertions. (Their failure is stated by the
coordinator; not re-run for this plan.)

Chunks while a lot is in progress (the full gate still runs before each merge):

| Lot | Chunk |
|---|---|
| L1 | `framework/tests/study/test_agent_files.py test_agent_resume_and_menus.py test_reliability_j4_j7.py test_contract_freeze.py test_review_round5_engine.py test_review_round6_engine.py framework/tests/acceptance`; panel pytest line (fixtures drift) |
| L2 | `test_companion_env.py test_contract_freeze.py test_contract_companion_e1.py`; `node --test clients/vscode-companion/test/*.test.js`; panel pytest line (labels, Decisions, Evidence, gate) |
| L3 | `test_v03_french_register.py test_integrity_audience.py test_sources_changed.py test_case.py test_v03_hotel_case.py`; the walkthrough language scan; panel pytest line |
| L4 | `test_cli_decisions.py test_run_cli.py test_executions.py test_exposure_kill.py test_agent_files.py`; `node --test` (argv) |
| L5 | `test_wp_a4_governance.py test_wp_a9_fresh_review.py test_v03_wp_a_engine.py test_v03_wp_j_engine.py test_activities_eda.py test_walkthrough.py test_regression_walkthrough.py test_perturbations.py`; walkers; `libraries/test_hypothesis_state_machine.py` |
| L6 | `framework/tests/study/deliverables` (with the browser group) |
| L7 | `test_state.py`, `framework/tests/exporters`; NR-19 |
| L8 | the full gate; `HYPOTRAIL_COMPAT_OLD_PYTHON=… HYPOTRAIL_COMPAT_OLD_ROOT=… pytest framework/tests/study/test_code_compat_library_v1.py`; NR-19 |
| L9 | `test_confirmation_modes.py test_delegation_scope.py test_wp_b1_final_test.py test_wp_b1_integration.py test_holds_and_credit.py`; deliverables; walkers |

After an engine change that alters a payload: `uv run --project framework python
clients/vscode-companion/test/fixtures/capture.py`, then fix the fixtures `test_fixture_drift.py`
names. Pixel baselines: `--update-baselines` only after the owner reviewed every diff image.

---

## 7. Contracts and documents to amend

| Document | Lots | Change |
|---|---|---|
| `docs/specs/CLI-CONTRACT.md` §1 | L4 | stderr clause: progress lines of `run --progress` |
| §3.1 | L1, L3, L5, L7, L9 | `choice_options`; pause `option_labels`, kind `choice`; `init` plan localized; step `structural_eda`; `alternatives`, `recommended.reasons`; `after_study`; `auto_value`, `review_queue` |
| §3.2 | L2, L5 | `panel.shown`; `data_contingent_reason.junior_text` |
| §3.3 | L3 | `texts: {en, fr}`, `question_junior` |
| §5 / §5.4 | L9 | basis `automatic`; automation |
| §7 | L5, L7, L9 | refusal `details` additions; reasons `automation_not_set`, `automation_does_not_cover` (no new code) |
| §8.1 | L4 | `run --progress` |
| §8.3, §11.5 | L6 | report chapters and TOC |
| §11.2, §11.3 | L5, L8 | exploration order; drafted preparation; per-column rare grouping |
| §14 | L5 | drafted variants; `junior_words`, `not_offered` |
| §15 | L7, R19 | missing revision refusal; support matrix (R19's own text) |
| `docs/specs/CLI-CONTRACT-COMPANION.md` | L2, L3, L9 | summary `next_action.choice_options`; EDA `question_junior`; `texts`; automation banner read |
| `docs/specs/COMPANION-ADVANCED.md` | L2, L3, L9 | Decisions choice card; variant cards; language labelling; banner |
| `docs/specs/CASE-CONTRACT.md` | L3, L5 | translations sidecar (D4 A) or `fr` fields (B); `calendar: year` (D8 a) |
| `docs/specs/JUNIOR-WORKFLOW.md` | L5, L9 | structure before the target; drafted family variant; automatic mode |
| ADR 0004 | L2 | amendment note 11: the engine names the panel's sections (no write, no stage change) |
| ADR 0005 | L1, L9 | note: `choice` stays the adoption channel (R2c); amendment: automation and basis `automatic` |
| ADR 0006 | L9 | amendment: the demo opening |
| ADR 0007 | L5 | note under decision 5: the drafted glass-box variant when flagged |
| `docs/handoff/IMPLEMENTATION.md`, `AZUREML-EXPORT-V1.md` | L7, all | capabilities and limits at the end of the batch; the `VIRTUAL_ENV` line; support matrix |
| `framework/mlkit/study/agent/*` | L1, L2, L4, L5, L7, L9 | through the integrator (§2.4) |
| `AGENTS.md` | L9 | only with the owner's explicit approval (D17g) |

No new ADR is required unless the owner prefers a separate ADR for automation (alternative to
amending 0005 and 0006).

---

## 8. Definition of done and risks

### 8.1 Definition of done

- Every lot's acceptance above holds; the owner decisions it depends on are recorded.
- The full gate is green after the last merge, with the counts recorded; no assertion weakened;
  every pinned phrase removed is replaced by a test of the new rule.
- §5.3 automated journey checks green for J-H (structural parts), J-M (full) in FR and EN.
- Panel fixtures recaptured; every changed pixel baseline reviewed by the owner.
- NR-19 green; NR-13 shows W1–W2 left `activities.MODULES` untouched.
- The owner's Copilot rehearsal (§5.4) is run and recorded in `docs/acceptance/runs/`, with any
  remaining remark numbered for the next batch. Until then the documents say "not run with
  Copilot".
- The handoff states what changed, what existing studies see, and what is not proven.

### 8.2 Risks

| Id | Risk | Mitigation |
|---|---|---|
| K1 | Copilot behaviour cannot be tested in CI; template fixes may not change what Copilot does (as R2 → R3 showed) | the rehearsal script; transcript grader if the export format allows; small, explicit template rules |
| K2 | Word budget at 3,999/4,000: changes crowd each other | the ledger (§2.4); engine-served texts; the rendered Copilot cap |
| K3 | A change to any capture module (R19's recipe or runtime changes, or L8) makes existing captures not current; an opened study then exports recipe-only | L8 after the workshop (D19); NR-19 on a fresh study; say it in the handoff |
| K4 | A case edit makes existing studies `sources_changed` | sidecar translations (D4 A); case revisions only with the owner's approval |
| K5 | `structural_first` changes the plan for new studies; old-generation logic must stay exact | generation key written by `init`; walkers on both generations |
| K6 | Drafts (preparation, variants) look like decisions | they are proposals; the junior adopts; the comparison option is visible; `motivated_by` cites |
| K7 | Progress on stderr breaks a consumer that expected silence | explicit flag only; the panel never passes it; tests pin stdout identical |
| K8 | The automatic mode blurs "decisions from the junior's words" | a distinct basis, banners, the review queue, `not_yet_defensible`, AGENTS.md amended only with approval |
| K9 | Hotel runs are slow (minutes per fit; `diag.binary` about 4.5 min) for the workshop | progress (L4), rehearsal timing, Auto MPG as the fast path |
| K10 | Parallel lots conflict on shared files | the integrator table (§1.3); one contract commit per wave |
| K11 | Panel language switch with engine texts doubles payload size | `texts` only for texts the panel shows; measured in `status --summary` size |

---

## 9. Verification notes

Verified on `spec-lot` at `ba4819c` (file reads and, where stated, a throwaway study run with this
worktree's engine under the session's scratchpad):

- Word counts of the agent templates (3,999 binary, 3,958 regression; rendered Claude Code 3,897,
  Copilot 4,317).
- `next_action.panel.where` after the preparation confirmation on Auto MPG (FR, v3): "onglet
  Preuves" (next action `run fit.baseline`); `pause.kind: "action"` with `continue`/`explain`;
  the `init` plan of a French study in English; Hotel's `no_time_or_entity_identifier` with both
  columns missing and a temporal final test; Auto MPG fits and diagnostics about 1 s each.
- Every file:line cited in §3, except where marked.

Not verified:

- How VS Code reports a dismissed `askQuestions` call to the agent (R2b), and the shape of a VS
  Code chat export for a transcript grader.
- The exact screen of the R11 Evidence tab in the session (the client code path is verified).
- Whether the R1b line in the session came from `where.line` or the agent's own mapping (the
  engine would have said "Preuves").
- The tuning record keys of a `tuned` variant's fit (R11 card content).
- That a capture-module change makes existing captures not current (inferred from
  `code_compat.py`'s round-2 comment and CLI-CONTRACT §15; to be proven by a test in L8).
- The failure of the top-level legacy tests (stated by the coordinator; not re-run).
- What R19 changes exactly (implemented in parallel; only its integration is specified).

## 10. Owner decisions log

2026-10-26: the owner accepted every recommendation of §4 (D1–D20, D1b, D4b) as written,
and asked to start the implementation. Reserved: D17 (R20, L9) still needs the owner's
approval of the AGENTS.md wording before L9 lands; D14 (R8, L6) means a Hotel mockup of the
report is shown to the owner before L6 is implemented; D19 keeps L8 after the workshop.
2026-10-26 (later): the owner asked to run every lot to the end autonomously, and approved L9
(R20) including the AGENTS.md wording it needs (D17). L6 proceeds from the mockup
(`docs/plans/mockups/report-narrative-hotel-fr.html`). L8 awaits the owner's answer on its
timing (D19).
2026-10-26 (later): D19 changed by the owner: L8 lands before the workshop, in this batch.
Existing studies lose their capture (risk K3, accepted); the workshop uses new studies.

2026-10-26 (later): the owner changed D19: L8 lands before the workshop, in this batch (W3),
accepting that existing captures stop being current (K3: before the opening the junior
captures again; after it the final evaluation is not current and the export is recipe-only).
