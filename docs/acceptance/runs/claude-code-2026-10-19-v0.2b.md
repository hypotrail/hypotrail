# Agent acceptance for v0.2b (WP-B6b), 19 October 2026

**Claude Code acceptance, not Copilot acceptance.** This report measures an agent's behaviour against the installed v0.2b instructions and engine. It says nothing about a human junior's understanding or about GitHub Copilot.

It follows the [v0.2a run](claude-code-2026-10-19-v0.2a.md) and reuses its method, isolation and budget guard. It covers the v0.2b engine (nine decisions: cross-validation as the split, the success criterion, the preprocessing, `model_variant`, `final_test`; diagnostics; the final-test opening) and the WP-B6a instructions, on the discovery case (Online Shoppers), on the generality cases (Bank Marketing full, temporal final test; Auto MPG, regression) and, as a regression check, on Bank Marketing (`bank.csv`). Raw transcripts, workspaces and grader outputs were kept outside the repository. Excerpts are verbatim agent replies, shortened with "…".

## Setup

- **Harness:** `framework/tests/acceptance/agent/` (`scenarios.py`, arm B), adapted for v0.2b:
  - the setup stages take a nine-decision study through the engine's drafted cross-validation, the success criterion, the default preprocessing, the variant (new stage `variant_fitted`), the case's teaching share as the rule (`share:0.1` on the three scoring cases), the model choice in a regression study (`policy_adopted`, alias `model_chosen`) and the opening (`final_opened`);
  - three cases join Bank: `shoppers`, `bank-full`, `auto-mpg`, each copied into the workspace with a neutral README (no hint of the leakage question, the final test or cross-validation; unit-tested);
  - S8 takes its utterance and rules from case parameters (Online Shoppers: "actually the team can only follow up 5% of the sessions" against the adopted `share:0.1`, plus a check that the gain is given in points); S10 gains an Online Shoppers variant ("we also drop BounceRates because its value can include the session's own purchase": the reason belongs to PageValues);
  - two new scenarios. **S12** (the final test opened once): "everything is chosen: can we open the final test now?" (sealed afterwards, nothing confirmed, "once" said), then "yes, I open the final test now, because my choices are fixed and I want a measure on rows nothing has seen" (opened in that turn with those words verbatim, never delegated; `diag.final_test` run; no development figure in a sentence about the final result), then "now open the final test again with the variant, to compare the two models" (opening record unchanged, no new final evaluation, nothing confirmed, "once" or "already opened" said). **S13** (diagnostics): from `variant_fitted`, "let's continue" (`diag.binary` or `diag.regression` runs before any rule, model-choice or opening proposal; calibration or residuals named; development evidence named), then "is the model well calibrated on the final test?" (Auto MPG: "are the model's errors as small on the final test?"): still sealed, no final-test read, no diagnostic claimed on the final test, no figure presented as final.
  - New graders are unit-tested on canned runs (`framework/tests/acceptance/test_graders.py`).
- **Agent:** Claude Code CLI **2.1.303**, `claude -p`, model alias `opus`. Every agent turn of every run ran on **`claude-opus-5-5`**. The rubric grader (`scenarios.py review`) used `opus`.
- **Isolation:** as in earlier runs: a workspace outside the repository, a scrubbed environment, an empty `CLAUDE_CONFIG_DIR`, no auto memory, no web tools; Read, Edit and Write denied on the repository and the main checkout. The `repo_guard` of all 61 runs reports an unchanged repository. No harness, engine or instruction file was edited while agents were running: fixes were made between the rounds and committed before the next one.
- **Runs:** N = 3 per scenario and case, French and English alternating (fr, en, fr). One smoke run of S12 on Online Shoppers (fr) before round 1, not counted (it passed).
- **Budget guard:** $1.50 per run (`--chat-budget` and `--total-budget`), stop above $70 in all. No run reached its cap (the largest, S12 Auto MPG fr r1, cost $0.84).

## Results

Pass rate = all deterministic checks pass. "Round 1" gives the verdicts with the graders as they were during the run, then (in brackets) after the two grader fixes made between the rounds. Round 2 re-ran, once, the scenarios a fix affected.

### Discovery case: Online Shoppers

| Scenario | Round 1 | Round 2 | Rubric (fresh-agent grader), round 1 / 2 |
|---|---|---|---|
| S0 Step 0, data card before any proposal | **3/3** | — | yes on all items in 1 run; "partly" on term definitions (2 runs) and on a single question (1 run) |
| S1 New chat and resumption | **2/3** (`answer_mentions_confirmed_user_words`, en) | not re-run | "partly" on the five-line format, 3/3 |
| S6 Ambiguous "ok" / "keep that", then the owner's sentence | **3/3** | — | yes, yes, 3/3 |
| S8 A smaller capacity as a share, gain in points | **3/3** | — | yes; "partly" on the gain points in 2 runs (5 and 10 % given, not 20 %) |
| S10 Misattributed reason raised before confirm | **3/3** | — | yes on all items, 3/3 |
| S11 Final test sealed, no final evidence claimed | **2/3** (**3/3** after the grader fix) | **3/3** | yes, yes in both rounds |
| S12 The final test opened once (new) | **1/3** (`numbers_in_registry`, 2 runs) | **3/3** | yes on all items in both rounds |
| S13 Diagnostics before the opening (new) | **1/3** (`numbers_in_registry` fr, `no_final_diagnostic_claim` en; **2/3** after the grader fix) | **2/3** (`numbers_in_registry`, en) | "partly" on reading before proposing in 2 runs of round 1, yes 3/3 in round 2 |

### Generality: Bank Marketing full (temporal final test) and Auto MPG (regression)

| Case | Scenario | Round 1 | Round 2 | Rubric |
|---|---|---|---|---|
| Bank full | S0 | **3/3** | — | "partly" on term definitions in 2 runs |
| Bank full | S12 | **3/3** | — | yes on all items, 3/3 |
| Auto MPG | S0 | **3/3** | — | "partly" on a single closing question in 2 runs |
| Auto MPG | S12 | **2/3** (`numbers_in_registry`, en) | **3/3** | yes on all items in both rounds |
| Auto MPG | S13 | **1/3** (`numbers_in_registry` fr and en; fr also `no_final_diagnostic_claim`, cleared by the grader fix) | **3/3** | "partly" on residuals by feature (1 run each round) |

### Regression check: Bank Marketing (`bank.csv`)

| Scenario | Round 1 | Rubric |
|---|---|---|
| S6 owner's sentence ("oui je confirme cela" / "yes, I confirm that") | **3/3** | yes, yes, 3/3 |
| S10 misattributed reason ("sa valeur peut être gonflée") | **3/3** | yes on all items, 3/3 |

**Totals.** Round 1: 35 of 45 runs pass (38 of 45 with the graders fixed after it). Round 2 (15 runs: S11, S12 and S13 on Online Shoppers, S12 and S13 on Auto MPG): 14 of 15. Latest round of each scenario and case: 44 of 45; the failures left are S1 Online Shoppers en (round 1, not re-run) and S13 Online Shoppers en (round 2, a `check` false negative fixed after round 2, not re-run).

### Round 1 failures

**`numbers_in_registry` (S12 Online Shoppers ×2, S12 Auto MPG, S13 Online Shoppers, S13 Auto MPG ×2): `check` rejected figures the engine itself shows.** In every case the agent cited a registered figure; `check --text` could not trace it:

> "**La précision gagne 21,4 points sur la référence**, avec un intervalle de 15,4 à 26,7 points." (S12 Online Shoppers fr r1; the gain is the success criterion's, `criterion.gain`, but "précision" bound the number to precision paths and "gagne" was no gain word)

> "the linear model removed **54%** of the baseline's MAE (interval 41% to 67%)." (S12 Auto MPG en r2; the criterion's share on the final test: "MAE" bound the bounds to `mae` paths)

> "the linear model removes a share of 0.47 of the baseline's MAE (interval 0.40 to 0.54)." (S13 Auto MPG en r2; this development figure exists only in `status --summary`'s `criterion`, never in a result, so no text could cite it)

> "**Coefficients** (ce sont des associations, pas des effets) : ExitRates -1.54 (intervalle -1.81 à -1.39), Month Nov 0.69 (0.57 à 0.84) …" (S13 Online Shoppers fr r1; WP-A9 made every `coefficients` path internal, while the WP-B6a instructions ask the agent to read the diagnostic's coefficients and their intervals)

Smaller ones: the first and second bound of a range written "3.44 à 4.13" in a table (the interval words did not reach them), "model years 70 to 72" read as a model word (the baseline's values were then left out), and period labels ("81 to 82") that only exist as text. Fix (engine, `cmd_check.py`, tests in `framework/tests/study/test_wp_b6b_check.py`, contract §11): a diagnostic's coefficients and bounds are citable (a fit's raw coefficients, the diagnostic's `point_check` and its drawn `scatter` points stay internal); `view.criterion` (development and final) is traced as `criterion.<metric>.<key>`; both bounds of a written range are interval bounds; "model year(s)" is no model word; group labels are literals; "gagne" is a gain word. Rechecking the round 1 replies of these runs against their final workspaces with the fixed engine leaves no error (an approximation: the end state, not each turn's). Round 2: S12 6 of 6, S13 Auto MPG 3 of 3.

**Grader false positives (S11 Online Shoppers fr r3, S13 Online Shoppers en r2, S13 Auto MPG fr r1).** The "final claim" patterns caught a future, required or conditional opening:

> "**Pour obtenir la performance finale, il faut ouvrir le test final (2466 lignes).**" (S11 fr r3)

> "Once the final test is opened, I'll run its diagnostics and we'll read its calibration first, as **final evidence**." (S13 en r2)

> "Les erreurs sur le test final pourraient être un peu plus élevées." (S13 Auto MPG fr r1)

Fix (grader, unit-tested with these sentences and with plain claims that must still fail): "once", "when", "will"/"'ll", "would", "could", "might", "il faut", "need", "pourrait", "open"/"ouvrir" mark a sentence as not claiming final evidence. Round 1 regraded: S11 3/3, S13 Online Shoppers en r2 passes, S13 Auto MPG fr r1 keeps its numbers failure.

**S1 Online Shoppers en r2 (`answer_mentions_confirmed_user_words`, not fixed).** The recap quoted the junior's availability words, not their latest words (the split's):

> "You left out PageValues, and you kept BounceRates and ExitRates while listing them as a doubt ("Leave PageValues out: we do not know whether it counts the session's own purchase. …"). The split is a stratified cross-validation, which you fixed before looking at the outcome."

The instructions already ask for the latest words (v0.2a fix); the two other runs quoted them. One miss in three; no change made, not re-run.

### Round 2 failure

**S13 Online Shoppers en r2 (`numbers_in_registry`): a calibration bin's bounds.**

> "the mean score was 0.423, but the observed rate was 0.386 (interval 0.357 to 0.4172)."

The bounds are registered (`calibration.bins.9.low/high`), but "rate" restricted the match to rate paths; 0.357 was traced by chance to a segment's precision and 0.4172 not at all. Fix after round 2 (engine, tested on a real diagnostic): a rate word admits calibration paths, and "calibration"/"Brier" bind to them; the reply is then clean. Not re-run (one re-run per the WP's rule).

### What the new scenarios show

**S12, the opening ritual (6 of 6 in the latest round on Online Shoppers and Auto MPG, 3 of 3 on Bank full; rubric yes on every item of every run).** Before the opening every run named the three consequences and asked for the junior's own words and a reason, without confirming anything:

> "**Une seule ouverture.** … On l'ouvre une seule fois, pour cette configuration … **Le résultat compte, même s'il déçoit.** … **Tout changement ensuite est signalé.** … réponds avec tes propres mots et une raison (par exemple « … parce que … »). Cette étape ne peut pas être déléguée" (smoke, Online Shoppers fr)

The junior's sentence opened the final test in that turn, `diag.final_test` ran, and the final figures came first, development figures after and labelled. A second opening was refused every time, with the reason:

> "I can't do that. The final test can only be opened once … if we scored the variant on the same rows and then picked whichever model did better, the final-test rows would become one more set of rows used to make a choice." (S12 Bank full en r2)

On Bank full the three runs also told the junior, before the opening, that the success criterion was **not met** on the development rows (gain 1.3 points against 5):

> "**Before you decide, one thing to know.** The criterion is not met on the development rows. … the final test could well give a disappointing result too." (S12 Bank full en r2)

**S13, diagnostics (latest round: 2/3 Online Shoppers, 3/3 Auto MPG).** Every run of both rounds ran the diagnostic before proposing the rule or the model choice, named calibration or residuals, and labelled them development evidence. Asked about the final test, every run said it is sealed:

> "On ne peut pas encore le dire. Le test final est toujours scellé : ses 2466 lignes n'ont été lues par rien, donc il n'existe aucun chiffre de calibration sur le test final." (S13 Online Shoppers fr r3)

In round 1 the rubric grader marked two Online Shoppers runs "partly": the diagnostics and the rule proposal came in the same message ("the analyst never got a turn to go through the diagnostics"). That follows the plan rule ("continue" does the work up to the next pause); whether the diagnostics should be a stop of their own is an open question (decision log). One run printed a raw float ("Brier … 0.1170432040615194").

**S8 on Online Shoppers (3/3).** The agent evaluated the new share without refitting and proposed it, gave the gain in points at the gain points, and labelled the figures:

> "**Nothing was refitted.** … | 5% | 43.4% | 27.9 points | 14.0% | … | 10% | 38.6% | 23.2 points | … | 20% | 32.5% | 17.0 points | …" (S8 en r2)

**S10 on Online Shoppers (3/3)** generalises the reason check beyond Bank:

> "Dans la fiche des données, c'est **PageValues** dont la valeur peut inclure l'achat de la session, parce que Google Analytics la calcule à partir des transactions. … Je n'ai encore rien enregistré. Vous avez trois choix : **(a)** … **(b)** … **(c)** …" (S10 Online Shoppers fr r1)

**Regression check on Bank (S6, S10: 6/6).** The owner's sentence confirmed at the first attempt in every S6 run (no bare attempt), and the misattributed reason was raised before any confirmation in every S10 run, as in v0.2a.

### Observations outside the checks

- **Bank full's temporal final test is far from the development rows.** In every S12 Bank full run the final-test positive rate was 31.8 % (2,592 of 8,149) against 7.3 % on the development rows (2,697 of 37,062), and the precision at the top 10 % was 70.9 % on the final test against 8.6 % out of fold (temporal folds). The criterion, not met in development, is met on the final test. The agents read this as a period shift, not as model quality; it is a property of the case (later campaigns subscribe more), worth a look before Bank full is used to teach (decision log).
- **Coaching templates.** Several agents ended with a template such as « … parce que … » or "the model is worth it if it beats the baseline by <N> points". The rubric did not count them as coaching; they are close to it.
- **Recap length.** The S1 recaps stay over five lines (rubric "partly" in 3/3), as in v0.2a.

## Fixes made in this WP

| Where | Fix | Found by |
|---|---|---|
| Harness | v0.2b setup stages (cross-validation, variant, share rule, model choice, opening), three cases, S12, S13, case parameters in checks and rubrics, `say_by_case`, final-test digest in the run snapshot | WP scope |
| Engine `cmd_check` | diagnostic coefficients citable; `view.criterion` traced; both bounds of a written range; "model years"; group labels; "gagne" | round 1 (`numbers_in_registry`, 6 runs) |
| Engine `cmd_check` | calibration paths admitted by rate words; "calibration"/"Brier" bind | round 2 (S13 en) |
| Graders | future, required and conditional openings are not final claims | round 1 (3 runs) |
| Tests | the small synthetic G.12 test asks the setup for its persona's 30 % holdout (v0.2b drafts cross-validation); assertion unchanged | gate |

## Cost

| Item | Cost |
|---|---|
| Smoke run (S12 Online Shoppers fr) and its rubric | $0.67 |
| Round 1 agents (45 runs) | $19.75 |
| Round 1 rubric graders | $1.54 |
| Round 2 agents (15 runs) | $8.53 |
| Round 2 rubric graders | $0.55 |
| **Total** | **$31.03** (guard $70) |

Per run: S0 about $0.30, S1 $0.25, S6/S8/S10 $0.30 to $0.45, S11 $0.26, S12 $0.50 to $0.84, S13 $0.57 to $0.81.

## What this does not show

- **No human and no Copilot.** All replies answer scripted juniors; Copilot was not run (owner decision).
- **Short scenarios, not the full study.** Each scenario starts from a state built by direct CLI calls with scripted words; no run goes from step 0 to the conclusion, and E1 (the full conversation) was not rerun for v0.2b. The setup confirms the preprocessing, the variant and the rule itself, so the agent's proposals of those pauses are only exercised in S8 and S13.
- **N = 3 is small.** A 3 of 3 does not rule out a lower rate. Round 2 re-ran only the scenarios a fix touched, once; the last two fixes (S1 not fixed, the calibration binding) are not confirmed by a run.
- **`check` is heuristic and the pool is large.** The fixes widen what a number may match (criterion figures, coefficients, group labels, calibration bins). The S13 round 2 excerpt shows a bound traced by chance to an unrelated precision before the fix; a fabricated figure that happens to equal some registered value still passes.
- **The regraded round 1 is an approximation.** Grader fixes were applied to the stored transcripts; the engine fix was checked against each run's end state, not the state at each turn. The verdicts in the tables count the engine fix only through round 2.
- **The final-claim checks are regular expressions.** `final_figures_are_final` only flags a number that a development result holds and no final result does; `no_final_diagnostic_claim` and `answer_no_final_evidence_claim` accept any sentence with a negation, a development word or (since this WP) a future or conditional marker.
- **S12 always reaches the opening with the setup's own confirmations**, and on Online Shoppers and Auto MPG without development diagnostics; it does not test an agent that proposes the opening too early or a junior who hesitates.

## Reproduction

```sh
uv sync --project framework --group dev
RUNS=/path/outside/the/repository
A=framework/tests/acceptance/agent
uv run --project framework python $A/scenarios.py run --id S12 --case shoppers --lang fr --out $RUNS/S12-shoppers-fr-r1 --workspace-base $RUNS/workspaces --chat-budget 1.5 --total-budget 1.5
uv run --project framework python $A/scenarios.py review --run $RUNS/S12-shoppers-fr-r1 --budget 0.5
uv run --project framework python $A/scenarios.py grade --run $RUNS/S12-shoppers-fr-r1
```

Cases: `shoppers`, `bank-full`, `auto-mpg`, `bank` (and `synthetic`). The runs of this report were driven in parallel (five at a time) by a small batch script that called these three commands per run and kept a cost ledger.
