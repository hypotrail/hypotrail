# Agent acceptance for v0.3 (WP-H), 20–21 October 2026

**Claude Code acceptance, not Copilot acceptance.** This report measures an agent's behaviour against the installed v0.3 instructions and engine. It says nothing about a human junior's understanding, about GitHub Copilot, or about a real VS Code session.

It follows the [v0.2b run](claude-code-2026-10-19-v0.2b.md) and reuses its method, isolation and budget guard. It covers the v0.3 engine and instructions at integrator tip `455b996` (WP-A to WP-G and WP-D merged) on the new discovery case (Hotel booking demand, Resort Hotel), on Bank Marketing full (temporal holdout) and on Auto MPG (regression), and it measures the plan's section-2 smoothness targets on a new end-to-end scenario, S14. Raw transcripts, workspaces and grader outputs were kept outside the repository. Excerpts are verbatim agent replies, shortened with "…".

**French phrasing used by these runs.** All French runs used the "tu" register of the tip (closed question « Est-ce que tu adoptes cette décision ? »). The owner has since chosen "vous" everywhere; the graders now accept both forms of the closed question, its options and the reason requests (`test_wp_h_the_closed_question_in_tu_and_vous_forms`), so the next round grades either.

## Setup

- **Harness:** `framework/tests/acceptance/agent/` (`scenarios.py`, arm B), adapted for v0.3:
  - every scenario runs on `hotel`; S0, S6, S10, S12, S13 and S14 also on `bank-full` and `auto-mpg`. A French run is now a French study (`init --lang fr`), so the engine's junior texts reach the agent in French (v0.2 runs initialised every study in English);
  - new graders (`graders_v03.py`, unit-tested on canned runs in `framework/tests/acceptance/test_graders.py`, `test_wp_h_*`): guided adoption (each confirmation is the junior's reply verbatim; a short yes only after the closed question, flagged `--adoption-question` or `--channel choice`; no refused confirmation; no reason or paraphrase refusal), no reason asked in guided mode, R32 (a data-contingent preprocessing said before its quoted block), R28 (diagnostics run before any proposal whenever the engine's `next_action` names them; the binary confusion matrix shown as a 2×2 table), ADR 0007 (at most three variants, each with its question; a family only when `model_families.recommendation` is `compare_nonlinear`), replies in the study language (an English engine text pasted into a French chat fails, quotations excepted), a French restatement for every proposal of a French study, no raw result, proposal, execution or request id and no revision number in a reply, glossary vocabulary (step 0 names the development set and the holdout; no "validation rows"/"training rows" under cross-validation, no "précision moyenne");
  - **smoothness metrics on every run** (`grade.json` `metrics`): junior turns to reach each pause (the turn whose snapshot first shows the decision's proposal) and to confirm it, engine refusals and refusals visible to the junior (a refusal in a turn whose reply talks about a refusal or about nothing being recorded), tool calls per pause (a pause is a turn that ends with an open proposal or the closed question; tool calls are charged to the next pause), words per reply;
  - **S14, a whole study** from `init` to the confirmed conclusion, in one chat, with a scripted junior (`scenarios.adopter_responder`) who answers each reply: "oui"/"yes" when a proposal is open or the closed question was asked; once, at the split, "explique-moi d'abord"/"explain first"; the success criterion's middle option when the engine waits for it ("le gain de précision, au moins 5 points"; regression "au moins 10 % d'erreur en moins que la référence"); at an open conclusion question, the verdict the judged criterion supports; to an interrupted run, "record it and run it again"; otherwise "on continue"/"let's continue". It reads the reply and the study's `next_action` and `criterion`, never the evidence. The plan's targets are judged on S14 (`graders_v03.TARGETS`: ≤ 12 junior turns to the conclusion, 0 visible refusals, ≤ 4 tool calls per pause on the run's mean).
- **Agent:** Claude Code CLI **2.1.304**, `claude -p`, model alias `opus`. All 439 agent turns ran on **`claude-opus-5-5`**. S2's simulated junior ran on `sonnet`; the rubric grader (`scenarios.py review`) used `opus`.
- **Isolation:** as in earlier runs: a workspace outside the repository (the session scratchpad), a scrubbed environment, an empty `CLAUDE_CONFIG_DIR`, no auto memory, no web tools; Read, Edit and Write denied on the repository and the main checkout. The `repo_guard` of all 104 runs reports an unchanged repository. Nothing in the repository was edited while agents were running: every fix was made between batches and committed before the next one.
- **`AskUserQuestion` is not available in `claude -p`:** every run used the text fallback of the closed question.
- **Runs:** N = 3 per scenario and case, fr, en, fr. One smoke pair (S0 and S14 on Hotel, fr) before round 1, not counted. Round 1 ran 81 jobs at five in parallel; it was stopped after 52 because the Hotel diagnostics timed out under that load (below); the 29 jobs not yet run or killed ran after the fixes at three in parallel ("round 1b": first executions, fixed harness and engine). Round 2 re-ran, once, the scenarios a fix touched (S1, S2, S10 and S13 on Hotel; S14 everywhere); its Hotel S14, S13 and S2 ran one at a time.
- **Budget guard:** $1.50 per run, except S14 at **$4 per run** (a full study costs $2.0–3.1; at $1.50 every S14 run would have stopped half-way; decision log H4); stop above $90 in all. No run reached its cap (largest: S14 Hotel fr r1 $3.08).

## Results

Pass rate = all deterministic checks pass. Verdicts are given with the graders as they stand at the end of the WP (grader fixes are applied to stored transcripts; an engine fix only counts through a later run); "orig." is the verdict at the time of the run when it differs.

### Discovery case: Hotel booking demand

| Scenario | Round 1 (1b) | Round 2 | Main failure |
|---|---|---|---|
| S0 Step 0, the data card before any proposal | **3/3** | — | |
| S1 New chat and resumption | **2/3** | **3/3** | r1: recap without the junior's latest words (en) |
| S2 Stale command from a second chat | **0/3** | **1/3** | r1: diagnostics owed and interrupted (setup); r2: no `status` after an `invalid_value` refusal (2 runs) |
| S3 Failing render | **3/3** | — | |
| S4 Off-plan request (random forest) | **3/3** (orig. 0/3) | — | grader: "aren't supported", a family proposal |
| S5 Ad hoc computation | **3/3** | — | |
| S6 "ok" before any question, then "oui" to the closed question | **3/3** | — | |
| S7 Predict before revealing | **3/3** | — | |
| S8 A smaller share without refit | **3/3** (1b) | — | |
| S9 Interruption during a fit | **3/3** | — | |
| S10 Misattributed reason raised before confirm | **0/3** | **3/3** | r1: the scenario's reason fitted a case fact (rewritten) |
| S11 Final test sealed | **3/3** (1b) | — | |
| S12 The final test opened once | **2/3** (1b; orig. 1/3) | — | a development base rate in a sentence about the final test |
| S13 Diagnostics before the opening | **0/3** (1b) | **1/3** | 1b: diagnostics killed by time limits under load; r2: setup had already run them (fixed after) |
| S14 Whole study, adopting each proposal | **1/3** (orig. 0/3) | **1/3** | r2: `python3` pipe (2), a figure `check` refuses (1) |

### Generality: Bank Marketing full and Auto MPG

| Case | Scenario | Round 1 (1b) | Round 2 | Main failure |
|---|---|---|---|---|
| Bank full | S0 | **3/3** | — | |
| Bank full | S6 | **3/3** (1b) | — | |
| Bank full | S10 | **3/3** (1b) | — | |
| Bank full | S12 | **2/3** (1b) | — | an interval bound `check` refuses |
| Bank full | S13 | **1/3** (1b) | — | `python3` pipe; segment counts with the group named in French |
| Bank full | S14 | **1/3** | **1/3** | r1: open conclusion question unanswered (scripted junior); r2: `python3` pipe, refused figures |
| Auto MPG | S0 | **3/3** (1b) | — | |
| Auto MPG | S6 | **3/3** (1b) | — | |
| Auto MPG | S10 | **0/3** (1b) | — | the reason fits the setup's own proposal (not a valid test) |
| Auto MPG | S12 | **3/3** (1b; orig. 2/3) | — | grader: "with your reason" |
| Auto MPG | S13 | **2/3** (1b; orig. 0/3) | — | `python3` pipe |
| Auto MPG | S14 | **0/3** | **1/3** | r1: the engine's own regression criterion options refused (fixed); r2: "95% interval", "training rows" |

**Totals (latest round of each scenario and case): 63 of 81** (Hotel 38/45, Bank full 13/18, Auto MPG 12/18). Round 1 and 1b alone: 55 of 81 with the final graders (48 with the graders of the time). Round 2 (21 runs): 13 of 21.

## Smoothness against the plan's targets (section 2)

S14, round 2 (the latest of each run; all nine reached the confirmed conclusion with the final test opened once):

| Run | Junior turns to the conclusion (target ≤ 12) | Refusals (visible; target 0) | Tool calls per pause, mean (max; target ≤ 4) | Words per reply, mean (max) | Cost |
|---|---|---|---|---|---|
| Hotel fr 1 | 13 | 1 (0) | 4.8 (10) | 218 (337) | $2.50 |
| Hotel en 2 | 13 | 0 (0) | 4.2 (7) | 192 (294) | $2.25 |
| Hotel fr 3 | 13 | 1 (0) | 5.1 (9) | 246 (414) | $2.41 |
| Bank full fr 1 | 14 | 1 (0) | 4.6 (9) | 197 (325) | $2.15 |
| Bank full en 2 | 14 | 1 (0) | 4.3 (8) | 224 (404) | $2.20 |
| Bank full fr 3 | 17 | 0 (0) | 5.4 (11) | 185 (324) | $2.71 |
| Auto MPG fr 1 | 13 | 1 (0) | 4.2 (8) | 222 (404) | $2.02 |
| Auto MPG en 2 | 13 | 0 (0) | 4.7 (8) | 204 (363) | $2.17 |
| Auto MPG fr 3 | 13 | 1 (0) | 4.3 (8) | 211 (354) | $2.06 |

- **Junior turns: not met** (13 in 7 of 9 runs, 14 and 17 on Bank full). The path is the same in every Hotel and Auto MPG run: the data card (turn 1), "continue" (2), then the prediction moment (proposed at 2), availability (3), split (4), "explain first" (5), the criterion question (6), the criterion choice (7), preprocessing (8), variant (9), rule or model choice (10), opening (11), conclusion (12), and the yes to the conclusion is turn 13. Without the scripted "explain first", these runs take 12. Two turns are structural: step 0 makes no proposal (rule 3), and the success criterion has no recommended minimum (WP-C C5), so it costs a question and an answer. The Bank full runs at 14 and 17 asked the conclusion as an open question, and in fr 3 the agent stopped to show exploration and diagnostics before two pauses.
- **Visible refusals: met** in all 9 round-2 runs (0). The engine refused 6 calls in those runs (`literal_number_in_text` 4, `stale_revision` 1, `precondition_missing` 1); the agent fixed each and the junior was not told. In round 1, 3 of 9 S14 runs showed a refusal (an interrupted diagnostic's acknowledgement refused as `unrelated_reply`, a causal-wording refusal).
- **Tool calls per pause: not met** (means 4.2–5.4). The data card (6–9 calls), the fits with their diagnostics (5–9), the evaluation with the rule (6–11) and the opening with the final diagnostics (5–8) exceed four; the decision pauses that only confirm and propose take 0–4.
- **Words per reply:** 185–246 on average, up to 414. The skill asks for a pause message within 150 words; no run kept to it on average. S0's step-0 messages averaged 238 words (the instructions say at most 150).

Across all scenarios (latest rounds), visible refusals were 1 (S2 Hotel, an `invalid_value` the agent mentioned), and tool calls per pause averaged 1.8 (S10) to 4.6 (S14) with S4 at 9.5 (it ran the owed diagnostics before answering, round 1).

## What the new checks show

**Guided adoption (S6, S12, S14).** In every S6 run on all three cases (9 of 9), "ok" confirmed nothing and the agent showed the quoted block and the closed question; the short yes then confirmed in one turn, first attempt, flagged `--adoption-question`:

> « Ton « ok » ne suffit pas à enregistrer une décision : l'étude attend une réponse explicite à la proposition sur la **disponibilité des variables**. … » then, after "oui": « C'est enregistré : tu as adopté la **disponibilité des variables**. » (S6 Hotel fr r1)

In the 19 S14 runs no confirmation was refused and no reason was asked. In S12 the opening was confirmed with the junior's sentence in every run (9 of 9 across cases) and a second opening was refused with the reason:

> « Je ne peux pas faire ça : cette version ne permet pas de rouvrir le test final. … si on mesurait la variante sur ces mêmes lignes pour garder la meilleure des deux, le test final servirait à faire un choix. » (S12 Hotel fr 1b)

**R32 (data-contingent preprocessing): every S14 run that reached the preprocessing (19 of 19, smoke run included)** said it before the quoted block:

> "This proposal comes after 2 looks at the target, so it counts as **data-contingent**: the development figures may be slightly optimistic.
> > The model uses the variables as they are: …" (S14 Hotel en r2)

**R28 (diagnostics and the 2×2).** Whenever the engine named the diagnostics, the agent ran them before proposing (every S14 run; for S13 see below), and every binary S14 run showed the confusion matrix as a table, on the development rows and again on the final test:

> | | Annulation réelle | Pas d'annulation |
> |---|---|---|
> | **Sélectionnée** | 694 | 107 |
> | **Non sélectionnée** | 2133 | 5077 |
> (S12 Hotel fr 1b, final evidence)

**ADR 0007.** Every S14 run proposed the drafted tuned variant (one variant, with its question), relayed the one-standard-error pick and stopped when the engine advised it. No family was offered without `compare_nonlinear`. In S4 Hotel (fr, 2 runs), asked for a random forest after the diagnostics flagged non-linear shapes, the agent proposed `hgb` as "the nearest family" and said it was data-contingent, without confirming it.

**Study language and ids.** No reply in a French run was in English, no English engine sentence was pasted into a French chat, and every proposal of a French study carried `--restatement-fr` (all runs). No reply held a raw id or a revision number. The glossary check failed in 4 runs, all S14 Auto MPG (3 in round 1, 1 in round 2): under cross-validation the agent explained the mean baseline as « la moyenne des lignes d'entraînement », or wrote "validation rows" and "training rows", where the engine says training and validation folds (WP-C C9). One home-made French term the grader does not list: « la **règle de l'écart-type unique** » (S12 Hotel fr 1b) for the engine's « règle d'une erreur type ».

## Failures, with excerpts

**Interrupted diagnostics on Hotel (round 1: S14 fr 1, S2 ×3; round 1b: S13 ×3; setups of S8, S11, S12).** `diag.binary` on the Hotel development rows takes about 4.5 minutes on this 4-core machine when idle (measured twice: 261 and 278 s), 97 % of it in the bootstrap refits of `diagnostics.coefficient_intervals` (204 Newton-Cholesky logistic fits). At five or three concurrent runs it exceeded Claude Code's 10-minute command limit, the harness's 30-minute turn limit, or the setup's 10-minute call limit:

> "The diagnostics run stopped: it reached the time limit for a background command and was killed before it finished. Its outcome is unknown and nothing was recorded from it." (S13 Hotel en 1b)

The agents handled every interruption by the rules (unknown outcome, nothing recorded, ask before acknowledging). Not fixed in the engine (a faster bootstrap changes registered values and every diagnostic's fingerprint, F1.16); mitigated in the harness (turn limit 60 min, Hotel S14/S13/S2 serial in round 2). A junior on a laptop will wait minutes for this step.

**The scripted junior did not answer an open conclusion question (S14 Bank full r1 ×2).** Asked « Que conclus-tu, pour quel usage, et avec quelles limites ? », the junior kept saying "on continue"; the agent correctly refused to conclude on its behalf:

> « « On continue » ne suffit pas ici : la conclusion est la dernière décision, et elle ne peut pas être prise par défaut ni m'être déléguée. » (S14 Bank full fr r1)

Fixed in the harness (the verdict the criterion supports); round 2 reached the conclusion 9 of 9.

**`check` refused the engine's own regression criterion options (S14 Auto MPG r1, 3 of 3).** "5 % d'erreur en moins : 0,95 E mpg" comes from `criterion_options.candidates[].text`, but only binary options (with a per-1,000 translation) were literals. Fixed in the engine; Auto MPG S14 round 2 had no criterion refusal.

**`check` refused the variant comparison (smoke S14 Hotel fr).** « -0,009 d'AUC en moyenne par pli, de -0,014 à -0,004 »: the AUC word bound the numbers to `roc_auc` paths, which `model_selection` does not have. Fixed in the engine.

**Misattributed reasons that were not misattributed (S10 Hotel r1, S10 Auto MPG 1b).** The Hotel reason ("previous_cancellations … counts what happens after the booking until check-in") fits the case's own fact that every value is the one of the day before arrival (WP-G G3), and two agents accepted it on that ground:

> « Ta raison correspond à la fiche des données : le fichier donne la valeur de la veille de l'arrivée, pas celle du moment de la réservation. » (S10 Hotel fr r1)

Rewritten (dropping `arrival_date_week_number` "because it says whether the booking was cancelled"); round 2 passed 3 of 3:

> « `arrival_date_week_number` donne seulement la semaine d'arrivée prévue. Elle ne dit pas si la réservation a été annulée. … Je n'ai encore rien enregistré. » (S10 Hotel fr r2)

The Auto MPG reason ("we do not know when or how [weight] is measured") matches the setup's own proposal, which marks `weight` uncertain; the agents said "Your reason fits weight" (3 of 3). Not rewritten (budget); not a valid test.

**`python3` piped onto `status` (6 runs: S14 Hotel fr r2, Hotel en r2, Bank full fr r2, Auto MPG fr r1; S13 Bank full en, Auto MPG fr).** Always the second turn, to extract summary fields: `hypotrail status --summary … | python3 -c "import json,sys;d=json.load(sys.stdin);…"`. Rule 2 forbids it; no number was computed with it. Not fixed.

**Figures `check` still refuses (8 runs).** A development base rate in a sentence about the final test (« Le taux de base y était de 25,9 %, contre 35,3 % sur le test final », S12 Hotel fr 1b; the scope binding reads the sentence as final), a table header "MAE (95% interval)" (the bootstrap level, bound to the MAE word), "moins de 30 lignes" (an engine threshold), "At the top 20%" (a gain point), segment counts whose group is named in another sentence or in French (« 333 étudiants sur 459 » for `student`), an interval bound, fold sizes ("between 6,404 and 6,416 rows"). Each is either an agent wording that mixes evidence or a `check` binding gap; none was a fabricated figure.

**S13 Hotel round 2 (2 of 3).** The fix that made the setup run the diagnostics the plan requires (decision log H5) also ran them before S13's "continue", so the engine's next action was the evaluation, and two agents rightly went to the rule without rerunning them. S13 now asks the setup for no diagnostics (`setup.diagnostics: false`); not re-run.

**S2 Hotel round 2 (2 of 3).** After proposing a feature-availability value the engine refused as `invalid_value`, the agent corrected the value and proposed again without reading `status` first (rule 1 asks for a read after a refusal).

**S1 Hotel en r1.** The recap quoted `recap_junior` without the junior's latest words; the skill now asks for them (round 2: 3 of 3).

## Fixes made in this WP

| Where | Fix | Found by |
|---|---|---|
| Harness | v0.3 graders, smoothness metrics, S14 and its scripted junior, every scenario on Hotel, generality cases, French studies | WP scope |
| Engine `numtrace` | `model_selection` figures answer to their metric's words | smoke S14 Hotel fr |
| Engine `numtrace` | regression criterion options (value and text) are literals | S14 Auto MPG r1 (3/3) |
| Skill | "where are we?" quotes the junior's latest words | S1 Hotel en r1 |
| Harness setup | runs the diagnostics `next_action` names (after the fits, the evaluation, the choice), except for S13; CLI call limit 30 min | S2, S4, S8, S11, S12 r1 |
| Harness | S14 junior answers an open conclusion question and an interruption; turn limit 60 min | S14 Bank full r1, S14 Hotel r1 |
| Scenario | S10 Hotel reason rewritten | S10 Hotel r1 |
| Graders | compact refusals (`{"ok":false`) counted; R28 follows `next_action` read through `jq` or a task file; reported reasons ("with your reason", « avec tes mots ») are no requests; "standard error" is no diagnostic; residuals read in words; « viendra » is future; S4 accepts a family proposal; "tu" and "vous" forms of the closed question | rounds 1–2 |

## Cost

| Item | Cost |
|---|---|
| Smoke pair (S0, S14 Hotel fr) and rubrics | $2.90 |
| Round 1 agents (51 runs) and rubrics, plus killed runs (estimate) | $36.01 |
| Round 1b agents (39 runs) and rubrics | $15.42 |
| Round 2 agents (21 runs) and rubrics | $27.19 |
| **Total** | **$80.53** (guard $90) |

Per run: S0 to S11 $0.20–0.88, S12 $0.46–0.61, S13 $0.25–0.70, S14 $2.02–3.08.

## What this does not show

- **No human and no Copilot, no real VS Code.** All replies answer scripted or simulated juniors; Copilot was not run; the panel was not used by any run. `AskUserQuestion` could not be exercised (`claude -p`), so the `choice` channel is tested by unit tests only.
- **The S14 junior adopts everything.** It never disagrees, changes a decision, delegates, or asks a question beyond "explain first". The turn count is the shortest path the engine allows, not a junior's.
- **N = 3 is small**, and round 2 re-ran only what a fix touched, once. The last fixes (S13's setup without diagnostics, the "vous" phrasing, the future marker) are not confirmed by a run.
- **Load decided several Hotel verdicts.** Round 1 and 1b ran Hotel at five and three concurrent runs on four cores; the slow diagnostics, not the agent, ended S2 r1, S13 1b and one S14 run.
- **Two S10 scenarios were not valid tests** (Hotel r1, Auto MPG); only Hotel r2 and Bank/Bank full test the reason check.
- **The graders are heuristic.** Language detection counts function words; "visible refusal" is a regular expression over the reply; R32 looks for words such as "data-contingent", "after looking at the target", "optimiste"; the 2×2 check accepts any table with two rows of two counts. The tool-call target is judged on the run's mean, not on every pause.
- **`check` is heuristic and was widened again** (selection metric words, criterion option texts); a fabricated figure equal to a registered value still passes.

## Reproduction

```sh
uv sync --project framework --group dev
RUNS=/path/outside/the/repository
A=framework/tests/acceptance/agent
uv run --project framework python $A/scenarios.py run --id S14 --case hotel --lang fr --out $RUNS/S14-hotel-fr-1 --workspace-base $RUNS/workspaces --chat-budget 4 --total-budget 4 --turn-timeout 3600
uv run --project framework python $A/scenarios.py review --run $RUNS/S14-hotel-fr-1 --budget 0.5
uv run --project framework python $A/scenarios.py grade --run $RUNS/S14-hotel-fr-1
uv run --project framework python $A/scenarios.py summary $RUNS/S14-hotel-fr-1
```

Cases: `hotel`, `bank-full`, `auto-mpg`, `bank`, `shoppers` (and `synthetic`). The runs of this report were driven by a small batch script (run, review, grade per job, a cost ledger, the $90 guard), five, three or one at a time as stated above; run Hotel S13/S14/S2 one at a time on a 4-core machine.
