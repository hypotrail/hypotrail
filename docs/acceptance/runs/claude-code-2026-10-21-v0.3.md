# Agent acceptance for v0.3 (WP-H), 20–21 October 2026

**Claude Code acceptance, not Copilot acceptance.** This report measures an agent's behaviour against the installed v0.3 instructions and engine. It says nothing about a human junior's understanding, about GitHub Copilot, or about a real VS Code session.

It follows the [v0.2b run](claude-code-2026-10-19-v0.2b.md) and reuses its method, isolation and budget guard. It covers the v0.3 engine and instructions at integrator tip `455b996` (WP-A to WP-G and WP-D merged) on the new discovery case (Hotel booking demand, Resort Hotel), on Bank Marketing full (temporal holdout) and on Auto MPG (regression), and it measures the plan's section-2 smoothness targets on a new end-to-end scenario, S14. Raw transcripts, workspaces and grader outputs were kept outside the repository. Excerpts are verbatim agent replies, shortened with "…". [Round 3](#round-3-wp-h3-21-october-2026) (WP-H3, tip `3773b3c` with WP-J and WP-K, French "vous") is at the end; the sections before it report rounds 1 and 2.

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

## Round 3 (WP-H3), 21 October 2026

Integrator tip `3773b3c`, which adds the following since round 2:
- the French "vous" register;
- WP-J: `diag.binary` in about 14 s instead of about 4 min; `decide` and `run` return the refreshed `next_action`; `status --summary --fields`; a recommended default for the success criterion; `check` fixes; a pause message of at most 150 words; no piping JSON into `python3`/`jq`;
- WP-K (panel only).

This round uses the same harness, isolation and budget guard as rounds 1–2, with Claude Code CLI 2.1.304, `claude -p`, `opus`. All agent turns ran on `claude-opus-5-5`, and the repo guard reports an unchanged repository in all 33 runs. Runs went three at a time; the load peaked at 8.3 on 4 cores and no run timed out. S14 took 8–25 min.

Scope:
- S14 on all three cases, N = 3 (fr, en, fr);
- S2, S12 and S13 on Hotel; S12 and S13 on Bank full; S13 on Auto MPG;
- S10 on Auto MPG, after the scenario was made a valid test (below).

After the 30 runs, the fixes below were committed and the two S14 runs whose failures came from fixed engine defects were re-run once. One of them, S14 Bank full fr 1, was re-run a second time, because the re-run exposed a bug in the first version of the number fix.

Verdicts are given with the graders as they stand at the end of the round; "orig." is the verdict at the time of the run when it differs. An engine fix counts only through a re-run.

### Results

| Case | Scenario | Round 2 (latest before) | Round 3 | Main failure in round 3 |
|---|---|---|---|---|
| Hotel | S2 | 1/3 | **0/3** | no `status` after an `invalid_value` refusal (3 runs, agent) |
| Hotel | S12 | 2/3 (1b) | **2/3** | fr 3: asked for the conclusion « avec vos mots » (`no_reason_requested`) |
| Hotel | S13 | 1/3 | **3/3** (orig. 2/3) | grader: « À l'ouverture, … mesureront » read as a final claim (fixed) |
| Hotel | S14 | 1/3 | **2/3** (orig. 1/3) | en 2: three honest figures `check` refuses (limitation); grader: "Do you adopt the opening of the final test?" not seen as the closed question (fixed) |
| Bank full | S12 | 2/3 (1b) | **3/3** | |
| Bank full | S13 | 1/3 (1b) | **3/3** | |
| Bank full | S14 | 1/3 | **2/3** with the re-run (round 3: 1/3) | en 2: fold sizes; fr 1: « 37 062 » and an interval's lower bound refused (engine, fixed; re-run passes) |
| Auto MPG | S10 | 0/3 (not a valid test) | **3/3** | |
| Auto MPG | S13 | 2/3 (1b) | **2/3** (orig. 1/3) | en 2: "3.34 mpg lower" (a negative paired difference written as a magnitude, limitation); grader: future reading (fixed) |
| Auto MPG | S14 | 1/3 | **0/3** | fr 1: « ses lignes d'entraînement » under cross-validation (re-run: a model choice asked as an open question, then a 20-turn loop); en 2 and fr 3: honest figures `check` refuses (limitations) |

**Totals:**
- Round 3: **19 of 30** with the final graders (17 with the graders of the time).
- **20 of 30** when the S14 Bank full fr 1 re-run replaces its round-3 run.
- Round 2's 21 re-runs: 13 of 21.
- By scenario, against round 2: S10 Auto MPG is a valid test for the first time (3/3); S13 is 8/9 across the cases (round 2 and 1b: 4/9); S12 is 5/6. S2 failed in all three runs, the same way as in round 2.

### S14 against the plan's targets

These are the nine round-3 S14 runs; the re-runs are listed below the table. "Words per pause" counts the reply of each turn that ends at a pause (an open proposal or the closed question). The skill asks for at most 150 words there.

| Run | Junior turns to the conclusion (target ≤ 12) | Refusals (visible; target 0) | Tool calls per pause, mean (max; target ≤ 4) | Words per pause, mean (max; pauses > 150) | Words per reply, mean | Cost |
|---|---|---|---|---|---|---|
| Hotel fr 1 | 15 | 2 (0) | 5.2 (13) | 171 (226; 7/10) | 174 | $3.06 |
| Hotel en 2 | 13 | 1 (0) | 4.6 (13) | 185 (237; 7/10) | 187 | $2.49 |
| Hotel fr 3 | 13 | 1 (0) | 5.0 (11) | 210 (292; 9/10) | 206 | $2.73 |
| Bank full fr 1 | 13 | 3 (0) | 4.7 (8) | 200 (348; 7/10) | 204 | $2.57 |
| Bank full en 2 | 13 | 2 (0) | 4.3 (8) | 192 (294; 9/10) | 189 | $2.13 |
| Bank full fr 3 | 13 | 2 (0) | 4.4 (7) | 208 (329; 7/10) | 205 | $2.42 |
| Auto MPG fr 1 | 13 | 1 (0) | 4.3 (9) | 169 (300; 6/10) | 175 | $2.20 |
| Auto MPG en 2 | 15 | 2 (0) | 4.6 (8) | 151 (244; 5/10) | 153 | $2.25 |
| Auto MPG fr 3 | 13 | 1 (0) | 4.3 (8) | 172 (278; 5/10) | 176 | $2.18 |

Re-runs:
- **Bank full fr 1, second re-run** (all fixes): pass, 16 turns, 2 refusals (0 visible), 5.0 tool calls per pause (max 9), 191 words per pause, $2.64.
- **Bank full fr 1, first re-run:** failed on « 37 062. », which the first number fix refused at the end of a sentence ($2.63).
- **Auto MPG fr 1 re-run:** asked the model choice as an open question; the scripted junior answered « on continue » until the turn limit, and the conclusion was not reached ($1.97).

Against round 2 (13–17 turns; 4.2–5.4 calls; words per reply 185–246, and 192–249 per pause message on the same measure):
- **Junior turns: not met, unchanged.** 13 in 7 of 9 runs (round 2: 7 of 9), and 15 in two:
  - Hotel fr 1 asked « Je les lance ? » before the diagnostics and the variant's fit;
  - Auto MPG en 2 asked the model choice as an open question twice.

  The recommended criterion saved its turn: it is proposed at turn 6 and confirmed at 7, together with the preprocessing's proposal. The conclusion now costs one more turn: after the opening, the agents ask for the verdict first (« Quel verdict retenez-vous ? »), then proposes it, and the junior's yes is turn 13. The Bank full runs fell from 14–17 to 13. The second Bank full fr 1 re-run took 16: three times it ended a turn with « Dites « on continue » et je lance … » instead of running the next step.
- **Visible refusals: met, 0 in 9 of 9.** Two counted at first; both were the metric's own false positive on « Le moteur signale… », fixed. The engine refused 15 calls (round 2: 6). 11 of them were `invalid_arguments` on `--fields`, in 8 of 9 runs:
  - mostly `status --summary --fields model_families,…`, a key that was only in the full view;
  - also `--fields` passed to `run` or `check`.

  Fixed (H3.5); the second Bank full fr 1 re-run had none.
- **Tool calls per pause: not met, unchanged** (4.3–5.2; maximum 13). The data card (6–8), the fits with their diagnostics (6–13) and the opening with the final diagnostics (6–9) still take more than four.
- **Words: down, not met.** The mean words per pause message fell from 192–249 to 151–210, and words per reply from 185–246 to 153–206. Still 5 to 9 of the 10 pause messages of each run exceed 150 words.

Other checks:
- **No JSON pipes.** No run piped JSON into `python3` or `jq`: 0 of 33 Bash histories, against 13 of 21 round-2 runs (into `jq` or `python3`; the grader then flagged only `python3`).
- **"vous" everywhere.** Every reply of every French run uses "vous" and no "tu" form outside quoted blocks (22–46 "vous" forms per S14 run), including the closed question « Adoptez-vous cette décision ? ».
- **Study language.** One reply was in English in a French study: the Auto MPG fr re-run, turn 4, « The variable availability is recorded. Next step: … ». No other French reply was.

### What the round shows, with excerpts

**S10 Auto MPG, now a valid test (3/3).** The setup's reason was rewritten (decision H3.1): weight is dropped "because it gives away the measured fuel efficiency", which belongs to the target. In every run, the agent named the target, waited, and recorded its remark when the junior kept the sentence:

> « Sur la fiche des données, `weight` est le **poids du véhicule** (en livres). La consommation mesurée, c'est `mpg`, la cible. Votre raison ne correspond donc pas à cette colonne … » (S10 Auto MPG fr r3 1)

**Fast diagnostics.** No run was interrupted. The S13 Hotel runs took 7–8 min, against 1b's time-outs. S14 Hotel took 21–25 min, mostly in the fits and the evaluation.

**S2 Hotel (0/3), the same agent behaviour as round 2.** The prediction moment changes in a second chat. The agent then proposes the feature availability again with only the changed columns, the engine refuses it (`invalid_value`: "Every candidate feature needs exactly one availability status"), and the agent corrects the value and proposes again without reading `status`. Rule 1 asks for that read. The study was never at risk (nothing changed between the two calls), but the rule was not followed. Not fixed.

**S12 Hotel fr 3.** At the conclusion pause the agent asked « Dites-moi la conclusion avec vos mots et je la mettrai en forme pour que vous l'adoptiez. ». Guided mode asks for no own words, and the rule asks the agent to state its recommended verdict. Not fixed.

**`check` still refuses honest figures (6 round-3 runs).** None was fabricated:
- "Precision is 73.6% of the 3,205 selected": a count in a precision sentence.
- "the variant's precision … is 69.2%, against 73.6% for the logistic model": two models in one sentence, and only the logistic model binds.
- "Top twentieth | 85.4%".
- "Fold 1 holds 226 positive rows out of 7,413": fold sizes.
- "missing on 6 rows, where the mean is 28 mpg": the word "missing" binds the mean to missing-value counts.
- "Its MAE is 3.34 mpg lower than the baseline's": a negative difference written as a magnitude.

These are reported as limitations (H3.8).

### Fixes made in round 3

| Where | Fix | Found by | Confirmed by |
|---|---|---|---|
| Scenario | S10 Auto MPG reason rewritten (target's reason), setup proposes `not_available` | round 1 report | S10 Auto MPG 3/3 |
| Engine `cite` | a space-grouped French number is one number (also before a full stop) | S14 Bank full fr 1 | its second re-run (pass) |
| Engine `numtrace` | the first bound of a range is not an interval level | S14 Bank full fr 1 | its second re-run |
| Engine `state`/`junior` | regression success step names the training folds (CV) or the training set, EN and FR | S14 Auto MPG fr 1 | not confirmed (the re-run stopped at the model choice) |
| Engine `commands`, rule 1 | `--fields` also gives `model_families` and `model_selection`; `--fields` only on `status --summary` | 8 of 9 S14 runs | Bank full fr 1 second re-run: no `invalid_arguments` |
| Harness | the scripted junior names the linear model at an open model choice | S14 Auto MPG fr 1 re-run | unit test only |
| Graders | the opening's closed question; « à l'ouverture » and a French future; "errors over time"; « le moteur » refusal talk | S13 Hotel fr 3, S13 Auto MPG fr 1/en 2, S14 Hotel en 2 and fr 1 | unit tests, re-grade |

### Cost

| Item | Cost |
|---|---|
| Round 3 agents (30 runs) and rubric reviews | $35.73 |
| Re-runs (3 S14 runs) and rubric reviews | $7.56 |
| **Total** | **$43.29** (guard $45) |

Per run: S14 $1.97–3.06; S10 $0.27–0.28; S2 $0.88–0.96; S12 $0.47–0.55; S13 $0.48–0.76.

### What round 3 does not show

- **Everything in "What this does not show" above still holds:** no human, no Copilot, no real VS Code; a scripted junior who adopts everything; heuristic graders and `check`; N = 3.
- **Three of the fixes have no confirming run.**
  - The regression wording (H3.4): the Auto MPG fr re-run stopped at the model choice before reaching the conclusion, and the glossary check that failed in fr 1 passed there for unrelated reasons.
  - The scripted junior's answer to an open model choice.
  - The `--fields` keys, which only the Bank full re-run exercised.
- **Re-runs are single runs.** The S14 Bank full fr 1 pass is one run. Its 16 turns show that the agent can trade tool calls per pause for extra turns, which the two targets cannot both reward.
- **The smoothness targets are still not met.** Junior turns stay at 13 even on a junior who adopts everything, and tool calls per pause stay above 4. The pause messages are shorter but mostly still over the 150 words the skill asks for.
