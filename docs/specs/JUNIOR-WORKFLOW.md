# Junior Copilot HTML and Marimo workflow

Status: **consolidated target specification, partly implemented**: v0.2 implements a slice of it with Claude Code (not Copilot) on Online Shoppers, Bank Marketing, Bank Marketing full, Auto MPG and a synthetic case; see [the handoff](../handoff/IMPLEMENTATION.md) for what exists and [the v0.2 checklist](../acceptance/V0.2-CHECKLIST.md) for its evidence. This preserves the product decisions for an agent without conversation history. Explicit subsequent user specifications take precedence. Storage conventions below are implementation proposals to validate.

## Intended outcome

A developer new to ML starts from an intention, understands the data, reviews a plan, makes the useful decisions, and obtains a reproducible study whose limits they can explain. GitHub Copilot guides in its normal chat. One HTML report summarizes the study; an evolving Marimo notebook documents and executes the complete reasoning.

Fluidity means understanding the next action, retaining valid decisions, and resuming without reconstructing history. It is not measured by confirmation counts, arbitrary percentages, or chart volume.

Initial scope: local supervised tabular learning, first Bank Marketing, then Auto MPG (since v0.3, Hotel booking demand (Resort Hotel) is the discovery case, Bank Marketing full validates generality on scoring, Auto MPG covers regression, and Online Shoppers, the v0.2b discovery case, is an advanced case with a documented scenario limitation; owner decision 2026-10-20, AGENTS.md). The visual companion, webview, overnight autonomy, cloud execution, and senior mode are outside this milestone. Unsupported tasks must be identified; a universal-looking sequence must not hide different evidence requirements.

## Three surfaces with distinct responsibilities

| Surface | Purpose | Contract |
|---|---|---|
| Copilot chat | Guide, explain, recommend, and collect decisions | Reread persistent state; do not rely on conversational memory |
| Evolving HTML | Show position, findings, and useful evidence | Stable path, generation date, revision, offline readability; no fake mutation controls |
| Marimo notebook | Explain the full study and allow experimentation | Readable from the beginning, progressively completed, executable code and provenance |

Proposed case outputs are `reports/study.html` and `notebooks/study.py`. Dated exports may supplement these entry points. HTML represents the latest successful generation; an open page may need refreshing. Do not promise live synchronization until implemented and tested.

The notebook can open at any phase. Opening it must not trigger downloads, expensive training, or decision writes. Marimo's ordinary local editor server is allowed; the workflow does not require a companion application server.

## First contact and visible plan

Copilot briefly restates the intention and inspects structure: files, provenance, schema, candidate target, time, groups, and feature availability. It distinguishes documented, observed, proposed, and unknown information. A column name alone does not establish business meaning.

Before detailed EDA, propose an authorized development partition suited to the problem. Record structural inspection needed to identify units, time, and groups. Previously exposed observations do not become independent final evidence after a new split.

Ask initially only about information that changes the next action: use, target, prediction time, or an ambiguous population. In a teaching case, propose a default scenario explicitly as an exercise assumption. Avoid an exhaustive business questionnaire.

A short orientation may precede inspection. The detailed plan follows the structural findings and precedes the full study: usually four to seven concrete steps, each with a question, expected output, and completion condition. Explain material plan changes and their consequences.

Use four common moments: **frame the change, prepare evidence, work and compare, conclude and hand over**. Retain professional activity names within those moments.

## Statistical vocabulary

| Activity | Terms to introduce when relevant | Contextual explanation |
|---|---|---|
| Problem framing | Observation unit, target, predictors, prediction time | What a row represents, what is estimated, and what is known when acting |
| Data understanding and EDA — Exploratory Data Analysis | Distribution, median, quantiles, missingness, association | Understand data quality and shape to choose useful analyses |
| Evaluation design | Train, validation, test, stratification, temporal or grouped split | Define the situation being measured and what must remain independent |
| Preprocessing and feature engineering | Imputation, encoding, standardization, pipeline, data leakage | Learn transformation parameters on training data only |
| Baseline and modeling | Reference, model, overfitting, regularization | Compare a simple approach with an appropriate reference |
| Evaluation and error analysis | Precision, recall, MAE, RMSE, calibration, residuals | Relate observed errors to the use case, units, and sample sizes |
| Conclusion and next steps | Uncertainty, external validity, limitations, reproducibility | State what the study establishes and which next action is justified |

Lead with the professional term, then a brief explanation and data-specific example. For example: “**Recall: the share of observed subscriptions retrieved by the selection.** Read it here alongside the number of contacts to call.” Build the glossary from encountered concepts rather than requiring a course before starting.

Activity order adapts. Evaluation design must precede detailed EDA when required for validity. Summarize completed work when resuming rather than replaying it.

## Guidance loop

At each meaningful step, identify the current plan position and question, completed action, available evidence, useful observation, interpretation, limitation, and recommended next action. Ask one main question at a time and offer a reasoned default when possible.

An optional teaching question can illuminate a consequential choice. It must not become a gate at every chart. Requests such as “explain differently,” “show the calculation,” or “let me try” change depth without losing the study's place.

Within an accepted plan, perform routine authorized work, update outputs, and continue. Pause for an invalidating ambiguity, scope change, or uncovered cost rather than every intermediate task. Silence is never a human confirmation of a business fact.

## Useful EDA

Start with a few findings that affect the next decision and make detail available:

- Example rows and a variable dictionary: meaning, type, unit, availability, and confidence/status.
- Analyzed sample size, missing values, and special values. Do not treat `unknown` or `-1` as an empty cell without justification.
- Target and relevant feature distributions: histograms, quantiles, and justified boxplots.
- Targeted relationships: scatter plots, category rates with denominators, and associations without causal claims.
- Time structure, repeated observations, apparent duplicates, and extreme values to examine before changing data.

Every chart identifies population, partition, units, sample sizes, and the question it answers. Keep accessible tables. Avoid a giant correlation matrix by default, decorative effects, and meaning conveyed by color alone. An IQR outlier flag does not establish an erroneous observation.

Separate observation, explanatory hypothesis, and proposed consequence. Training-data associations can motivate an experiment; they are not independent evidence.

## Narrative and editable notebook

Create intention, plan, provenance, known limits, and future section headings immediately. Unexecuted sections say “upcoming” or “not executed” rather than displaying invented conclusions.

Each section follows **question → concept → method → code → result → interpretation → consequence**. Code should be readable and rerunnable. Share calculation primitives with the framework instead of implementing different metrics in each surface.

Keep three areas distinct: the reference study (applied decisions and retained outputs), pedagogical exploration (isolated experiments), and user notes (preserved annotations and personal cells).

An exploratory change becomes an explicit proposal. It must not silently overwrite the contract or current result. Adopting it explains changed dependencies, invalidated evidence, and required recomputation.

Choose and test an update mechanism that preserves user cells: identifiable generated regions, composition from external resources, or another verifiable method. Concurrent edits produce a candidate copy or explicit conflict, never silent destructive rewriting. Check supported mechanisms against the actual Marimo version.

A slider may update a view or recompute a metric from existing predictions. Training requires an explicit action, execution state, applicable budget, and identified output. An interpretation becomes stale when its result dependencies change.

## Authoritative state and synchronization

State is independent of chat, HTML, and unrestricted notebook outputs.

| Object | Minimum information |
|---|---|
| Study | ID, dataset/version, intention, task type, revision |
| Plan | Ordered steps, question, status, expected evidence, any pending decision |
| Fact or decision | Value, status, source, author/confirmation, date, dependencies |
| Protocol | Partition, relevant seed, units/groups/time, metrics, scope |
| Execution | ID, code/config/environment, status, timestamps, measured cost, starting revision |
| Result | Execution source, hashes, metrics, partition, scope, limitations |
| Exposure | Observations inspected, explored, or used for selection |
| Artifact | Path, revision, referenced results, generation date, validity |

Mutations carry an expected revision and idempotency key. Compatible retries are not applied twice; conflicts are explicit. Persistence must support interrupted-write recovery. A delayed result is retained without automatically replacing the current result.

HTML and notebook reference sections identify the same revision and evidence. If one generation fails, success of the other does not mean both are current. Keep the last valid artifact and expose the mismatch.

A fresh chat reads objective, plan, still-valid decisions, interrupted executions, invalidations, and next action. It does not restart the questionnaire or relaunch an execution with unknown outcome.

## Adaptation to a use case

The framework owns primitives, invariants, rendering, and tracking. A case owns business question, data, dictionary, adapter, proposed protocol, and constraints. Adding Auto MPG must not require copying the engine or adding `if bank` branches to generic logic.

Classification requires class distribution, an appropriate reference, suitable metrics, and possibly a threshold decision. Regression requires a numeric distribution, mean/median reference appropriate to the objective, metrics in the target unit, and residuals. Time and groups may constrain either protocol. Unsupported tasks receive an explicitly incomplete proposed plan rather than automatic validation.

## Concrete Bank Marketing walkthrough

**First contact.** The user asks to understand whether contacts can be prioritized. Copilot proposes a pre-call simulation and inspects the data. It identifies `y`, UCI provenance, and `duration`, which is known after the call. Confirm prediction time only if not already confirmed. Record the lack of a full timestamp and customer identifier.

**Proposed plan.**

1. Framing and evaluation design: pre-call use and a defensible exploratory comparison.
2. EDA: target, special values, and useful training-data relationships.
3. Preprocessing and baseline: available features and a reference.
4. Modeling: a simple logistic regression under the same protocol.
5. Evaluation and error analysis: selection trade-offs and errors.
6. Conclusion: evidence, decision, limits, and next question.

Explain why this exercise will not conclude with production validation. Allow deeper questions and revisions without restarting.

**EDA.** Generate training target distribution, a balance histogram, and subscription rates by previous campaign outcome with sample sizes. Numbers come from identified calculations, not a narrative written in advance. Explain class imbalance and why accuracy alone is insufficient; recommend precision/recall alongside selected volume.

The notebook contains code, results, explanation, and chart exploration. HTML shows findings, plan, and recommendation. Uncompleted modeling chapters remain visibly upcoming.

**Preparation and modeling.** Recommend excluding `duration` and introduce data leakage. Fit transformations on training data. Distinguish a constant reference from a fitted model. A leakage counterexample can support learning but remains separate and ineligible.

**Evaluation.** Using identified predictions, show selected contacts, retrieved subscriptions, false positives, and missed observed subscriptions across thresholds. The notebook allows exploratory threshold variation. An unknown call capacity can be simulated as an explicit teaching assumption, not a confirmed business constraint. Adopting a threshold is separate from moving a control.

A threshold chosen on validation remains exploratory. Missed observed subscriptions are not causally established lost sales. Historical observations do not establish future-campaign performance.

**Variants and model families (v0.3, [ADR 0007](../decisions/0007-trial-budget-and-model-families.md)).** After the first logistic fit, the engine runs its diagnostics as the next step of the plan; the junior does not have to ask. The diagnostics check whether the linear model misses a shape in a numeric variable, an interaction with a segment, or a calibration slope away from one. The junior then names up to three variants, each with the question it answers. The engine drafts the first: the penalty chosen by nested cross-validation, one trial. It proposes a non-linear family (an Explainable Boosting Machine first, gradient boosting when the case allows a black box) only when the diagnostics flagged something, shows that evidence, and says that this choice is data-contingent. Each variant is compared with the candidate on the same folds, with a paired difference and its noise. The engine names the configuration the one-standard-error rule keeps, states the approximate optimism of picking the best, and advises stopping when the differences stay within the noise between folds or the budget is used. The junior then chooses one configuration and one rule, and the diagnostics run again at the adopted rule, confusion matrix included, before the final test is opened.

**Conclusion and resumption.** Explain use, protocol, trials, results, limits, and next action. Keeping the reference or finding no sufficiently supported improvement are valid outcomes. A fresh chat reconstructs, for example: “Pre-call prediction is confirmed, duration is excluded, EDA and the first comparison are available; the next choice concerns simulated contact volume.” This comes from persistent state.

## Scientific validity

Fit preprocessing on training data. Tie predictions and metrics to the declared protocol. Record trials, model selection, and threshold exploration. Budget exhaustion is not evidence of convergence. Hyperparameters are chosen inside each outer fold (nested cross-validation), never on the rows that score them, and every variant confirmed counts against a budget of three, replaced ones included.

Current, stale, and exploratory describe different dimensions. Recalculation can restore freshness without independence. A new split does not erase prior exposure. Public data already explored does not become an unseen final test during a fresh demonstration.

Documented facts are not all human confirmations. Generalization and delivery claims require a separate defensible evidence strategy. Conclude only at the scope actually established.

## Acceptance checks

- Initial Bank interaction proposes a contextual plan and clear next action.
- Charts use a verifiable partition; future phases contain no fictional outputs.
- A fresh chat preserves valid confirmations and explains targeted invalidations.
- HTML and notebook share revision, metrics, partition, and limitations.
- The notebook opens at every phase, runs in the declared environment, and retains a user annotation after regeneration.
- Slider manipulation confirms no decision, triggers no training, and leaves reference results unchanged.
- Target/protocol/data changes invalidate dependent evidence without erasing history or exposure.
- Retries, interruption, and delayed completion duplicate no decisions and promote no stale evidence.
- A complete Bank study reaches a readable reproducible conclusion, including when there is no improvement.
- Auto MPG receives regression-specific language, plan, EDA, reference, and error analysis using shared code.
- Actual Copilot use validates instruction uptake and interaction flow separately from simulated tests.
