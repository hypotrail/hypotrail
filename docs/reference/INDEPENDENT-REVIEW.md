# Independent workflow review findings

This is an English synthesis of the independent review supplied on October 17, 2026. It preserves the findings relevant to the next implementation. It is a design review, not a fresh code audit, production certification, or adoption study.

## Overall assessment

A single guiding pilot, initial data discovery, decisions tied to evidence, explicit resumption, and a comparison with a reference are useful foundations. The proposed product combined too many responsibilities before establishing state consistency, result validity, and recovery. A sophisticated interface cannot substitute for these mechanisms.

The user's later decision narrows the next milestone to a junior workflow in Copilot chat with HTML and Marimo. The visual companion is paused, and a public teaching dataset replaces the review's initial suggestion of a real ticket.

## Authoritative state

Chat memory is not project state. A user may change a split while the assistant retains an older explanation and a previous calculation finishes. All mutations need an expected revision and idempotency key. Conflicting stale writes must be rejected rather than silently merged.

Each execution and result must reference data, code, environment, configuration, and starting revision. A late result remains inspectable without automatically becoming current. Before a decision or expensive action, the assistant must reread state. Tests should cover duplicate commands, stale clients, process interruption, and delayed completion.

## Execution and recovery

Persistent files alone do not establish durable autonomous execution. A process can stop, a job can continue elsewhere, or an authorization can block progress. Distinguish stopped, running, failed, interrupted with unknown outcome, and completed but not collected.

Start with bounded, predefined work. Record measurable budgets and reserve capacity before concurrent work. Never relaunch an execution with an unknown outcome automatically. Overnight agentic exploration is outside the first junior milestone.

## Exposure and independent evidence

Structural inspection is needed to identify observation units, time, and groups. Detailed EDA should then use an authorized development partition. Keep an exposure record. If a split changes, observations already explored may move into a purported final test; invalidating old reports does not remove that knowledge.

Distinguish technical freshness, exploratory usefulness, and evidence supporting generalization. Recalculation can repair freshness without establishing independence. If final independence is not defensible, acquire new data or narrow the conclusion. Do not reactivate suspended holdout or production packaging paths to create a false end-to-end claim.

## Assumptions and interpretation

A promising score can anchor a user into confirming an unsupported business assumption. Present facts that limit validity before ranking attractive gains. Distinguish observed, assumed, tested, untested, and incomparable. Preserve negative results and the number of trials attempted.

Valid outcomes include keeping the reference, finding no sufficiently supported improvement, or identifying missing information. A morning confirmation cannot retroactively make an adaptive experiment preregistered.

## Adaptation to the actual task

A universal modeling sequence does not fit a parser refactor, data-source migration, ranking task, clustering exercise, and classification study equally. Use four common moments: frame the change, prepare evidence, work and compare, conclude and hand over. Insert task-specific activities inside them.

Classification and regression need distinct interpretations and evidence. Ranking requires query/group units and available information. Clustering requires an account of usefulness, representation, distance, and stability; an internal score alone does not establish business value. Initial coverage should be narrow and explicit.

## Teaching without constant gates

An explanation is not proof of understanding. A user should be able to change a relevant assumption, predict what must be recomputed, and diagnose a simple failure. Optional teaching questions can help, but requiring a prediction and reformulation at every step turns guidance into friction.

Introduce professional terminology, explain it in context, and adapt depth explicitly. Do not infer a person's competence from clicks, reading speed, or writing style. Work guidance and optional practice have different goals.

## Notebook and interface boundaries

Keep the current objective, action or decision, useful evidence, and next step immediately visible. Avoid permanent panels whose density forces users to reconcile multiple representations.

A notebook is a voluntary exploration tool. If it can propose recognized study changes, it must use the same state contract; otherwise its outputs are explicitly exploratory and cannot silently replace reference evidence. HTML exports are dated snapshots and must not imply that offline controls mutate project state.

## Deterministic controls and security

Multiple specialist agents do not establish expertise or independent review. Prefer bounded tasks and verifiable outputs, with deterministic invariants outside the model's judgment. Use additional agents only when their contribution can be assessed, and retain meaningful disagreements.

A local service is not a security boundary by itself. Restrict access and mutations, minimize model inputs, and treat datasets, comments, and generated reports as untrusted content rather than authorization. A worktree does not isolate secrets, network access, or the filesystem.

## Acceptance evidence

Verify state conflicts, double actions, interrupted calculations, delayed results, changed datasets, changed splits after exposure, notebook edits, and user resumption. Observe whether a user can identify the applied decision and relevant evidence without help.

Keep automated correctness, live Copilot integration, usability, and learning claims separate. A simulated model test does not establish a real provider connection; a successful walkthrough does not establish independent generalization or durable learning.
