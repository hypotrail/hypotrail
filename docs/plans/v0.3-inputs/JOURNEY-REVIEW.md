## Hypotrail junior journey review (Online Shoppers, guided mode, tip fdc9623)

I made no changes to the repository. Everything I produced is in /tmp/claude-0/-home-user-hypotrail/d627b9a6-d196-5d88-8cd2-a6e477a31532/scratchpad/journey-review/:
- `os/` is the full study, carried through every step to the conclusion. `os2/` is the same study stopped with the decision-rule proposal open.
- `log.txt` records the size, time and exit code of every CLI call. `out/*.json` holds the payloads.
- `panel_mid.json` and `panel_end.json` are the panel's view messages, captured through the real `lib/controller.js`.
- `shots/{mid,end}-<tab>.png` and `.txt` are Playwright screenshots of the panel at stage v3, 900 px wide.

Below, **[V]** marks a fact I reproduced and **[O]** marks my opinion.

### 1. Friction map

**Overall load [V].**
- The agent loads CLAUDE.md (4,429 words) and the skill (3,747 words).
- Rule 1 says to read `status --summary` (950 to 1,420 words) before every decision and every run.
- Other large outputs: data card 1,810 words, `policy.evaluate` 1,980 words, `diag.binary` 5,410 words (68 KB).
- My walk took 55 CLI calls, read about 32,000 words of JSON and used 127 s of engine time (split 16 s, `policy.evaluate` 23 s, `diag` 12 s).
- A real agent following rule 1 plus `check` before each message with numbers needs about 65 calls and 60,000 to 70,000 words of tool output.
- The junior answers 9 pauses and gets 1 report of 13,000 words (1 MB).

**Config A, chat + report + notebook, per step:**

| Step | Calls (min) | Junior turns | Friction (evidence) |
|---|---|---|---|
| 0. Data card | 2 | 1 | [V] Step-0 limit already says "Validation rows are used…" although the study uses cross-validation. [V] VisitorType shows "distinct 2" next to the special value "Other" (76 rows). [O] 1,810 words pasted or summarised into the chat is too much. |
| 1. Prediction moment | 3 | 1 | [V] "oui je confirme" works first time. "ok" is refused (expected). |
| 1. Feature availability | 3 | 1 | [V] No `default_value`: the agent hand-writes a 17-key JSON from the case. |
| 2. Split | 4 | 1–2 | [V] "d'accord avec ta recommandation" is refused (`unrelated_reply`). [V] The split result reports `partitions.train` = `validation` = 9,864. |
| 2. Success criterion | 3 + check | 1–2 | [V] `next_action` has no default and no reference value (base rate 15.5 %) and is a 90-word English paragraph. [V] My 5-point criterion was met by 23.7 points (development) and 21.4 (final test), so it was asked blind (R18/R19). [V] The business translation "1000 sessions → about 155 buyers" is refused by `check`. |
| Training EDA | 6 runs + 6 status + check | 0–1 | [V] The engine's own single-feature question text ("out-of-fold AUC of 0.87… median 0.61") fails `check`. Even "0.8658" at full precision fails: those scores cannot be cited at all (R33, worse than reported). [V] `check` traced "14,8 %" to the wrong result (an unrelated VisitorType interval) because it matches by value. |
| Preprocessing | 3 | 1 | [V] The propose payload has no `data_contingent`; confirm reveals `data_contingent: true` for the do-nothing default with `motivated_by: []`. This contradicts CLAUDE.md ("when a motivating result read the target"). [V] The recap says "the default… [motivated by a look at the target]" (R32). |
| Fits, variant, evaluation, diagnostics | 5 runs + status | 1 | [V] The fit result names cross-validation figures `validation`. [V] Diagnostics are 5,410 words. [V] Exactly one variant (R24). |
| Decision rule | 3 + check | 2 | [V] "je confirme" and "j'adopte cette décision" are refused (`reason_required`): R27 is not implemented. [V] `diag.binary` goes stale on the first confirmation of the same rule (share:0.1) (R34). |
| Final-test opening | 3 + run | 2–3 | [V] Proposing the opening is accepted while `diag.binary` is stale, against instruction rule 10. [V] "ok allons-y" is refused (`unrelated_reply`); "je confirme" is refused (`reason_required`). [V] **Engine trap:** the confirm response gives top-level `revision` 39, but the opening moved the state to 41, so the next `run diag.final_test` is refused with `stale_revision`. |
| Conclusion | 3 + check | 2 | [V] **`check` says clean, then `decide propose` refuses the same text** ("interval 15.4 to 26.7", `literal_number_in_text`), while the HTML report prints exactly "interval 15.4 to 26.7". [V] The final recap's limit is "Some results are out of date" (noise, R34). |

**How the engine treats short replies (guided mode) [V]:**

| Outcome | Replies |
|---|---|
| Accepted | "je suis d'accord", "c'est bon pour moi", "oui je valide", "I agree", "j'adopte cette décision", "oui ça me va" |
| Refused as bare acknowledgement | "ok pour moi", "parfait", "vas-y" |
| Refused as unrelated | "allons-y", "d'accord avec ta recommandation" |
| Refused as `delegation_needs_basis` | "yes, go with your recommendation" (forces a withdraw and a new "My recommended default:" proposal) |

[O] To a junior this is a lottery. The agent has to predict lexical rules described across several hundred words of CLAUDE.md.

**Config B, chat + panel, stage v3 [V from screenshots]:**
- **What the panel adds over the chat:**
  - the Study map (four moments, pause chips; the best overview anywhere);
  - the Marimo read and edit buttons;
  - the deliverables status;
  - the What if? share slider;
  - EDA charts with null bands.
- **Duplication:**
  - The five-line recap is repeated at the top of 5 of the 6 tabs.
  - The restatement appears twice in the proposal card ("…" and "In short: …").
  - "What counts as your answer" appears on both Overview and Decisions and repeats the chat.
  - Limits appear in the chat, on Overview and in the report.
- **Contradicts owner decisions:**
  - The Decisions card still has a free-text answer box with the heading "Your answer to this proposal, in your own words" and the hint "say why it fits your situation" (R23, R27).
  - Overview's "Answer in Decisions" button sends the junior away from the chat.
- **Wrong or noisy content:**
  - EDA: "rows seen in EDA · train 0 · validation 0" next to 9,864 rows read.
  - The ranges table shows "0 / 0" and "no declared range".
  - A "Show French labels" button.
  - Decisions tab: "+23.7%" against Overview "+23.7 points"; "share of successes among the cases picked" instead of precision.
  - "Since your last session" lists "A result was computed." twice.
  - The proposal effects stay at "Reading what a confirmation would change…" until a separate read.
- **Volume:** 500 to 2,400 words per tab. The EDA tab is 6,452 px tall at 900 px.
- [O] The panel is a second, longer copy of the chat state, not a quieter companion to it.

### 2. Ideal journey, applying R15, R16, R20, R23, R24bis and R27

**A: chat only.** Each pause is one agent message: term first, a short example, the decision restated as a quoted block, then a choice offering adopt / change something / explain first, with a text fallback. One junior click or one short word confirms.

| # | Agent shows | Junior does |
|---|---|---|
| 0 | Data card, at most 150 words: row unit, groups, the 3 doubtful columns, 3 rows. Standard terms: "échantillon de développement", "holdout (test final)". | Reads it, says "on y va". |
| 1 | Prediction moment, then feature availability with an engine-drafted value (the case's statuses plus the doubtful columns as options). | 2 choices. |
| 2 | Evaluation scheme as k-fold cross-validation, out-of-fold predictions, folds. | 1 choice. |
| 3 | Success criterion: metric tied to the action (at a fixed share, precision, recall and lift rank models the same way), base rate stated, options +2 / +5 / +10 points each translated per 1,000 follow-ups, plus "Other". | 1 choice. |
| 4 | "Continue": EDA (including the predictor correlation matrix), fits, diagnostics with confusion matrix, run without asking. One message with a ≤5-bullet digest. The preprocessing proposal says whether it is data-contingent before showing it. | 1 choice. |
| 5 | Model family and variants within a budget of ≤3 trials (linear first; EBM or gradient boosting only with diagnostic evidence; nested-CV tuning counts as one trial). | 1–2 choices. |
| 6 | Decision rule, with the gain at 5 / 10 / 20 % shown. | 1 choice (a reason is optional and recorded if given). |
| 7 | Holdout opening ritual: 3 sentences on once only, results stand, later changes are flagged. | 1 choice. |
| 8 | Final figures first, then development figures; conclusion drafted in the study's language. | 1 choice. |

Target: about 12 junior turns, 0 visible refusals, at most 4 tool calls per pause.

**Today's journey vs ideal:**
- **Today:**
  - Paraphrase is asked for at every pause.
  - 3 forced reasons.
  - Refusals on natural French.
  - A blind criterion and long English engine paragraphs.
  - Figures the agent may not cite.
  - A stale-revision trap.
  - Diagnostics often not run (R28).
  - About 16 to 20 junior turns in the demo.
- **Ideal:** the target above.

**B: chat + panel.** Same chat flow. At step 0 the agent asks once "panneau ouvert ?". After that, at most one line per step points to a tab: "Data & EDA" after the data card or charts, "Decisions" to see the proposal and history, "Evidence" after fits and the opening, "What if?" at the rule.

The panel becomes read-only (R23):
- Overview: map, next move ("answer in the chat") and deliverables.
- Data & EDA, Evidence and What if?: no recap banner.
- Decisions: restatement block, effects in words, and a "Copy question for the agent" button.

The agent reads the channel `webview` in the digest and says "tu as lancé ces graphiques depuis le panneau" (R35). Panel actions are the chart runs and exports only.

### 3. Ranked improvements

| # | Change | Value | Effort | Layer |
|---|---|---|---|---|
| 1 | Guided = explicit endorsement everywhere (R27); replace the lexical endorsement lists with "any reply bound to the open proposal that is not negative, conditional or a question"; record choice-tool labels with channel `choice` (R16) | Very high | M | engine + instructions |
| 2 | One tracing function shared by `check`, `propose`, report and payload texts: rounding, %/points scaling, single-feature scores, interval points, scale examples "per 1,000" flagged illustrative. Test that every engine junior text passes `check` | Very high | M | engine |
| 3 | Return the final revision after a confirm that triggers the opening (and any chained run); test that no command's own output leads to `stale_revision` | High | S | engine |
| 4 | Success criterion: metric + minimum as a choice; payload carries the base rate, candidate options and the business translation (R18/R19) | High | M | engine payload + instructions |
| 5 | Cut agent reading: a `status --digest` of ≤200 words; drop "status before every run" (runs already check `--expected-revision`); diagnostics with a `junior_digest` and full JSON on demand | High | M | engine + instructions |
| 6 | Vocabulary pass (R15): partitions `development / fold / holdout`; remove `train`/`validation` keys under CV; precision named "precision"; points never as "%" | High | M | engine, report, panel copy |
| 7 | French variants of all junior texts (`junior_message`, questions, limits, recap) (R21/R36/R37) | High | M | engine |
| 8 | `data_contingent` in the propose payload; the do-nothing default is not data-contingent (or say exactly why) (R32) | Med | S | engine |
| 9 | Diagnostics not invalidated by a confirmation of the same rule; drop "some results are out of date" from junior limits (R34); auto-run diagnostics after fits as part of "continue" (R28) | Med | S | engine + instructions |
| 10 | Draft `feature_availability` from the case (`default_value`) | Med | S | engine |
| 11 | Rewrite CLAUDE.md and the skill to about half the length: remove the refusal taxonomy, move the mode, hold and delegation detail to the glossary or skill sections loaded on demand | Med | M | instructions |
| 12 | Panel design pass (R26) | Med | L | panel |

**To remove:**
- The panel answer box and W1/W2 (R23); W3 becomes "ask the agent".
- The repeated recap banner on 5 tabs and "What counts as your answer" in the panel.
- Revision numbers and timestamps in the history.
- "Show French labels", until R21.
- The guided reason requirement.
- The `delegation_needs_basis` dance: treat "go with your recommendation" at the open proposal as `delegated_default` directly.
- The "Since your last session" generic lines.
- The scenario's proxy contradiction: R31 reframe before any further demo [O, blocker].

### 4. Smoothness metrics for agentic acceptance

1. Junior turns per decision: ≤1.2 (today about 1.6–2).
2. Refusals that reach the junior per study: 0. Engine refusals per decision: ≤0.1.
3. Agent tool calls per pause: ≤4. `check` failures on engine-supplied or report-printed figures: 0 (today >0, verified).
4. `stale_revision` caused by the engine's own returned revision: 0.
5. Junior-facing words per pause message: ≤150. English sentences in a French study: 0.
6. Clarification questions from the junior ("que veux-tu dire par… ?") per study: ≤1. Count them from the transcript.
7. Wall-clock from "continue" to the next pause: ≤60 s. Total engine time: under 3 min.
8. Information dropped: figures removed from a draft after `check` (diff draft vs sent): 0.
9. Instruction violations scored by a judge: agent statement contradicted by a later payload (R32), diagnostics skipped, panel action unexplained (R35).
10. Panel only: share of agent pointers to the right tab (R20), and words duplicated between chat and panel.

### 5. Top 5 recommendations

1. **Unify number tracing and fix the self-inflicted refusals first** (`check` vs `propose` mismatch, untraceable single-feature scores, stale revision after the opening, diagnostics stale after confirmation). These are verified engine bugs that make even a perfect agent stumble, and they push it to drop information.
2. **Implement R27 + R16 as one change:** endorsement or a choice label confirms in guided mode; reasons optional; delegation phrases recognised; lexical lists removed. This cuts about 30 % of junior turns.
3. **Make payloads junior-ready:** French variants, standard vocabulary, a ≤200-word digest, drafted defaults for availability and criterion, the base rate plus business translation at the criterion.
4. **Shrink the agent's contract:** halve CLAUDE.md and the skill, drop the status-before-every-run rule, and make diagnostics part of "continue".
5. **Panel: narrow before polishing.** Make it read-only (R23), remove duplicated text, add the R20 one-line pointers in chat, fix the EDA counts, then run the R26 design pass with screenshot gates. Fix the Online Shoppers scenario (R31) before the next owner demo.

**Caveats:**
- My counts are from direct CLI calls, not a Copilot or Claude acceptance session. I estimated junior turns rather than observing them.
- I captured the panel views through the real controller but rendered them in Chromium, not in VS Code.
