# Hypotrail experimental VS Code companion

Version 0.5.0. Development is paused; read [the feature status](../README.md) before making changes.

A shared webview renders Bank Marketing or Auto MPG, applies tutorial choices through a local Python engine, and explains an applied choice through the VS Code `vscode.lm` API. Business-specific text, features, metrics, and units come from case contracts and journeys, not the generic UI or prompt.

## Build and try explicitly

From this directory, `python3 scripts/package.py` produces `hypotrail-companion-0.5.0.vsix` without publication. Installing that package is a separate action. Open the repository root as a trusted workspace and use **Hypotrail: open companion**. Select an explanation model when asked; access and model selection depend on the installed Copilot setup.

The packaged `assets/` and `engine/` directories are generated. The source runtime is `../runtime/`, and use-case resources are materialized into the package. The simulated provider and test directory are never packaged.

## Interaction contract

- Changing an option updates only a precomputed preview. It does not apply the choice, train, or call a model.
- **Apply and explain** first applies through the engine. Only success triggers an explanation from attested state. Official numbers appear before the streamed explanation completes.
- Panel questions apply no choice. Their context distinguishes the applied choice, an unapplied preview, and the activity.
- Every exchange references project, session, context hash, application, and activity. Navigation does not invalidate it; applying another choice cancels an older generation. Delayed fragments cannot replace current text.
- Switching projects cancels the current generation and isolates its events and conversation.
- Model errors retain the applied choice and result, with retry or model-selection actions. No fixed teaching text is presented as a generated answer.
- Closing a panel retains ongoing responses. After restart, unfinished responses are marked interrupted; no new model request is sent automatically.
- Duplicate clicks produce one idempotent application and initial explanation. Unknown execution outcomes require rereading state.

## Persistence and limits

One SQLite database per project: runtime `.local/<session_name>.sqlite`, or workspace `.hypotrail-tutorial/<session_name>.sqlite` when using a packaged engine outside this repository. Schema 3 migrates legacy sessions in place. An old application with a different context remains inspectable, never current.

Questions are limited to 4,000 characters and generated answers to 20,000. At most 10 recent activity exchanges are sent to the model. Local history remains complete; current state includes the latest 50 exchanges and export includes all exchanges.

Only relevant context is transmitted: project, provenance and hashes, fact statuses, variable metadata, activity, choice, associated results, limitations, and selected history. The repository, CSV, and unrelated project state are not included.

Facts are unknown, proposed, or confirmed with provenance. Only the person can confirm or reject a proposal. Activities may require confirmations. Data-dependent confirmations become reviewable after relevant hashes change. Clearing conversation preserves choices, applications, confirmations, and results. Resetting the exercise clears exercise choices only.

## Chat tools and transport

`hypotrailTutorialStatus` reads current state. `hypotrailTutorialApply` applies a recorded choice using event ID, expected revision, and context hash. `hypotrailTutorialExplain` publishes a message, attaching it only when application references match; it does not overwrite an ongoing panel response.

The webview uses message passing, not HTTP. CSP limits scripts and resources, messages are action- and size-checked, and model Markdown uses textContent without raw HTML or active links. Project switching accepts registry IDs rather than paths. No chat-opening command is executed.

## Validation

`node --test test/*.test.js` exercises orchestration with the real Python engine and a simulated provider. `../runtime/tests/` covers contracts, migration, state, browser UI, and simulated webview hosting. A real VS Code/Copilot acceptance run is separate from those tests.
