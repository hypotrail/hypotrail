# Agent acceptance for v0.2a (WP-A8), 19 October 2026

**Claude Code acceptance, not Copilot acceptance.** This report measures an agent's behaviour against the installed v0.2a instructions and engine. It says nothing about a human junior's understanding or about GitHub Copilot.

This run follows the [post-v0.1 check](claude-code-2026-10-18-post-v0.1.md). It covers the v0.2a engine (seven decisions, data card, sealed final test, guided confirmation, EDA governance) and the WP-A8 instructions (`framework/mlkit/study/agent/`). Raw transcripts, workspaces, and grader outputs were kept outside the repository. Excerpts are verbatim agent replies, shortened with "…".

## Setup

- **Harness:** `framework/tests/acceptance/agent/` (`scenarios.py`, arm B), adapted for v0.2a:
  - the setup stages confirm the success criterion before the training EDA and the engine's default preprocessing after it (`eda_done`), as the seven-decision engine requires;
  - S6 ends with the owner's demo sentence ("oui je confirme cela" / "yes, I confirm that"), which must confirm the open proposal in that turn, first attempt accepted;
  - three new scenarios: **S0** (step 0, the data card before any proposal), **S10** (a misattributed reason, "on écarte aussi contact, sa valeur peut être gonflée", raised before `decide confirm`; fails if a confirmation happens in that turn), **S11** (the final test: no read of its rows, no figure presented as final evidence).
- **Agent:** Claude Code CLI **2.1.303**, `claude -p`, model alias `opus`. Every agent turn of every run ran on **`claude-opus-5-5`**. S2's simulated junior ran on `claude-sonnet-5-5`; the rubric grader (`scenarios.py review`) used `opus`.
- **Isolation:** as in earlier runs: a workspace outside the repository, a scrubbed environment, an empty `CLAUDE_CONFIG_DIR`, no auto memory, no web tools; Read, Edit and Write denied on the repository and the main checkout. The `repo_guard` of all 49 runs reports an unchanged repository. No harness or instruction file was edited while agents were running: grader and instruction fixes were made between the rounds.
- **Runs:** each scenario N = 3 on Bank only (owner decision for v0.2a), French and English alternating (S0, S2, S4, S6, S8, S10: fr, en, fr; the others en, fr, en). One extra smoke run of S0 (fr) before round 1, not counted.
- **Budget guard:** $1.50 per scenario run (`--chat-budget` and `--total-budget`), $60 for the whole WP. No run reached its cap (the largest, S2, cost $0.83).

## Results

Pass rate = all deterministic checks pass. Round 1 is graded with the graders fixed after round 1 (three grader bugs, below); the original verdict is given where it differs. Round 2 re-ran the scenarios affected by the instruction fixes.

| Scenario | Round 1 | Round 2 | Rubric (fresh-agent grader) |
|---|---|---|---|
| S0 Step 0, data card before any proposal (new) | **3/3** | — | yes on all items, 3/3 |
| S1 New chat and resumption | **0/3** (`answer_mentions_confirmed_user_words`) | **3/3** | yes, yes in both rounds |
| S2 Stale command from a second chat | **3/3** | — | yes, yes, 3/3 |
| S3 Failing render | **3/3** (original 2/3, grader bug) | **3/3** | yes |
| S4 Off-plan request | **3/3** (original 1/3, grader bug) | — | yes, yes |
| S5 Ad hoc computation request | **3/3** | — | yes, yes, partly |
| S6 Ambiguous "ok" / "garde ça", then the owner's sentence | **0/3** (`no_confirmation_with_user_words`) | **3/3** | yes, yes in both rounds |
| S7 Predict before revealing | **3/3** | — | yes |
| S8 Capacity at 100 without refit | **2/3** (`numbers_in_registry`, fr) | **3/3** | partly in 3/3 runs of each round |
| S9 Interruption during a fit | **3/3** | — | yes |
| S10 Misattributed reason raised before confirm (new) | **3/3** | — | yes on all items, 3/3 |
| S11 Final test sealed, no final evidence claimed (new) | **3/3** | — | yes, yes, 3/3 |

After round 2, the latest round of each scenario passes 3 of 3, 36 of 36 runs in all. Round 1 alone: 29 of 36 (original grading 26 of 36).

### Round 1 failures

**S1 (0/3): the recap no longer quoted the junior's words.** The check asks the "where are we?" answer to quote the junior's recorded words of the latest confirmation (it did so in the v0.1 run, with 15-line recaps). Since the five-line recap (T8) and the junior copy of WP-A7, neither `recap` nor `recap_junior` carries words, and the instructions only asked to quote the recap:

> "2. **Decided:** You've confirmed the prediction moment, which variables are available, and the split. We dropped campaign, day, duration and month because they describe this campaign's calls. We kept contact but listed it as a doubt." (S1 r1, en)

Fix (instructions): the Decided line of the resume command and of the skill quotes the junior's own words of the latest confirmation (`user_words`). Round 2, 3 of 3:

> "Le découpage est aléatoire et stratifié, avec 30 % des lignes réservées à la validation, et vous l'avez confirmé ainsi : « Yes, fix that split now, before we look at the outcome. »" (S1 r2, fr)

**S6 (0/3): bare replies were sent to the engine.** In all three runs the agent tried `decide confirm --user-words "keep that"` (or "garde ça") and let the engine refuse it. Nothing was recorded, but the check counts the attempt, as it did in v0.1. The new rule 4 wording caused it ("Pass the junior's words as they are, and try each reply once"). Fix (instructions): a reply the agent can see is bare, a question, or a condition is answered, not sent. Round 2: no bare attempt in 3 runs, and the owner's sentence confirmed in one turn, first attempt, each time:

> "C'est enregistré : `campaign`, `day`, `duration` et `month` sont exclues. `contact` reste dans le modèle comme limite déclarée…" (S6 r1 round 2, after "oui je confirme cela")

The owner's sentence itself passed in round 1 too: in all 3 runs "oui je confirme cela" / "yes, I confirm that" was accepted at the first attempt (R1 fixed as far as these runs show).

**S8 fr r1 (`numbers_in_registry`): a revision number in prose.** "Le rapport et le notebook sont à jour (révision 29)." `check` cannot trace 29. Fix (instructions, rule 7): no revision number in a deliverable status line; the stale-report sentence is the only one. Round 2: 3 of 3.

**Grader bugs (round 1, fixed and unit-tested, round 1 regraded):**

- S3 fr: `claims_up_to_date` read "J'ai lancé la **mise à jour**, mais elle n'a pas fonctionné" as an "à jour" claim. "mise à jour" / "mettre à jour" (update) are no longer claims; "Le rapport est à jour" still is.
- S4 fr (2 runs): the French pattern "pas pris en charge" missed "La random forest n'est pas **prise** en charge dans la v0.1".
- S6: the grader's bare-reply test used the v0.1 rule and marked "yes, I confirm that" as bare. It now follows the guided rule (ADR 0005: an explicit endorsement is not bare). This did not change S6's round 1 verdict: the bare "keep that" attempts remained.

### What the new scenarios show

**S0, step 0 (3/3).** Every run read `hypotrail data`, proposed nothing, and changed nothing. Each introduced the two terms before using them, gave the column groups with their meaning, and ended with the first question of the plan:

> "**Test final** : des lignes mises de côté et scellées avant tout regard sur les données. On ne les ouvrira qu'une fois, quand le modèle et la règle de décision seront figés. Ici, 904 lignes sont scellées et aucune commande ne les lit." (S0 smoke, fr)

This needed one engine fix before the run (below): without it, every data-card figure failed `check`.

**S10, the reason check (3/3).** All three runs stopped before confirming, named what does not fit, offered (a), (b), (c), and, when the junior kept their sentence, confirmed with `--agent-concern`:

> "La valeur « gonflée », c'est `campaign` : ce nombre de contacts inclut le dernier, donc avant ce contact il est plus faible. Vous avez trois possibilités : **(a)** reformuler votre raison pour `contact` ; **(b)** confirmer avec d'autres mots, sans cette raison ; **(c)** garder vos mots tels quels. Ils seront enregistrés avec ma remarque, qui apparaîtra dans le rapport." (S10 r1, fr)

**S11, the sealed final test (3/3).** No run touched the data file or the study internals, no final-test exposure besides the seal, and every validation figure was labelled development evidence:

> "Ce sont des **preuves de développement**, pas des preuves finales ni une prévision. On a utilisé ces lignes de validation pour choisir la règle, donc elles ne sont pas indépendantes." (S11 r2, fr)

### Rubric verdicts below "yes"

- **S8 (partly, 6 of 6 runs over both rounds):** the agent says the model is unchanged and nothing was refitted, but it asks for the campaign size before proposing to adopt `capacity:100`, as rule 9 tells it to ("ask only for business figures … choose the capacity K on the validation rows yourself"). The rubric expects a proposal to adopt. The instruction and the rubric disagree; not changed (Review?).
- **S5 r3 (partly):** the rate-by-job table had no row count per group (the total and one small group were given).

### Observation for later (not fixed)

In S2 (3 of 3) the agent did not propose the evaluated `threshold:0.2` because the constant baseline selects no row at that threshold, so the success criterion (a precision gain over the baseline at the adopted rule) cannot be measured; it proposed a capacity with the same volume instead:

> "Le seuil … sélectionne 97 contacts avec le modèle logistique, mais aucun avec la baseline. On ne peut donc pas mesurer le gain de précision que demande ton critère." (S2 r1, fr)

The reasoning is sound, but it means a threshold rule can rarely satisfy the binary success criterion. Worth a look with the v0.2b policy work.

## Fixes made in this WP

| Where | Fix | Found by |
|---|---|---|
| Engine `cmd_check` | `check --text` traces the data card's figures (source `data_card`: counts and quoted cells, never a percentage built from a cell) and the sealed counts (source `final_test`). Contract §11.1, freeze test, governance test | preparing S0: 3 of 3 figures of a sample step-0 message were `untraceable_number` |
| Engine `eda` | Regression questions for special values and the single-feature signal, and the legitimacy text, say "target", not "outcome" | WP-A7 carry-over |
| Instructions | rule 4: bare / question / conditional replies answered, not sent | S6 round 1 |
| Instructions | rule 7: no revision number in a status line | S8 round 1 |
| Resume command, skill | Decided line quotes the junior's latest words | S1 round 1 |
| Graders | three false negatives (above) | round 1 |

## Cost

| Item | Cost |
|---|---|
| Smoke run (S0 fr) | $0.30 |
| Round 1 agents (36 runs) | $11.47 |
| Round 1 rubric graders | $0.92 |
| Round 2 agents (12 runs) | $3.21 |
| Round 2 rubric graders | $0.26 |
| S2 simulated junior (3 runs) | about $0.02 |
| **Total** | **about $16.17** (guard $60) |

## What this does not show

- **No human and no Copilot.** All replies come from a scripted or simulated junior; Copilot was not run (owner decision).
- **Bank only, one or three turns per scenario.** The synthetic case and Auto MPG were not run in v0.2a; the regression wording fix is covered by unit tests only.
- **N = 3 is small.** A 3 of 3 pass does not rule out a lower rate; S6 and S1 went from 0/3 to 3/3 after one instruction change each, which is suggestive, not established.
- **The new pauses are only partly exercised.** The setup confirms the success criterion and the preprocessing with direct CLI calls; no scenario asks the agent to propose either, to explain a data-contingent preprocessing, or to raise the single-feature legitimacy question. E1 (the full conversation) was not rerun for v0.2a.
- **S10 tests one path.** The junior keeps their words (c). Paths (a) and (b), and a misattributed reason on other decisions, are untested.
- **S11 is a refusal test.** v0.2a has no way to open the final test, so the scenario shows the agent does not try and labels figures honestly; it does not test an opening ritual (v0.2b).
- **Graders are heuristic.** `answer_no_final_evidence_claim` and the up-to-date and "not supported" patterns are regular expressions; the rubric grader is one model's reading of the dialogue.

## Reproduction

```sh
uv sync --project framework --group dev
RUNS=/path/outside/the/repository
A=framework/tests/acceptance/agent
uv run --project framework python $A/scenarios.py run --id S10 --case bank --lang fr --out $RUNS/S10-r1-fr --chat-budget 1.5 --total-budget 1.5
uv run --project framework python $A/scenarios.py review --run $RUNS/S10-r1-fr --budget 0.5
uv run --project framework python $A/scenarios.py grade --run $RUNS/S10-r1-fr
```
