# ADR 0002: The future companion is a client of the `hypotrail` CLI

- Status: accepted (Phase 0, plan §9 bis, amendment A8)
- Date: 18 October 2026
- Scope: design constraint only. No companion code is written in v0.1, and `experimental/companion/` is not modified.

## Context

Companion development is paused (`experimental/companion/feature.json`: `"status": "paused"`, `"resume_requires": "Explicit user request"`). The owner intends to resume it later as a VS Code webview. The v0.1 junior workflow uses three surfaces:

- chat with an agent;
- one HTML report;
- Marimo notebooks.

The v0.1 workflow keeps its decisions in `.hypotrail/state.json` and its results in the registry, and every change goes through the `hypotrail` CLI (`docs/plans/V0.1-IMPLEMENTATION-PLAN.md` §3, §4).

The paused companion took a different path. `experimental/companion/runtime/protocol.py` has **its own SQLite state and its own protocol**:

- tables `session`, `companion_meta`, `companion_events`, `fact_confirmations`, `assistant_exchanges`, and `schema_history` (`protocol.py:89-150`);
- its own `submit`, `apply`, and `confirm_fact` with their own revision and idempotency rules (`protocol.py:233`, `:284`, `:312`).

All of this runs in parallel with the legacy pilot. The VS Code extension launches a Python bridge against one SQLite file per project (`experimental/companion/vscode-extension/extension.js:12-27`). Reviving that design next to `.hypotrail` would create two sources of truth for revisions, confirmations, and results.

## Decision

1. The future webview companion is **one more client** of the `hypotrail` CLI and of the `.hypotrail` study state, like the chat agent. It reads through the CLI's JSON output (`status`, `plan`, `view`, `preview`). It writes only by calling the same commands (`decide … propose|confirm|withdraw`, `run`, `render`), with `request_id` and `expected_revision`.
2. The companion has **no state, no protocol, and no server of its own**. That means:
   - no SQLite database;
   - no daemon, websocket, or loopback HTTP service;
   - no second revision counter.

   The extension's existing model is enough: it launches a Python process and reads its output. It can watch `.hypotrail/state.json` and `revisions.jsonl` for changes.
3. The paused companion's SQLite protocol (`experimental/companion/runtime/protocol.py`) is **not reused**, not migrated, and not called from `mlkit/study/`. Its tests and design can inform later work. Its tutorial confirmations are never imported as human decisions (AGENTS.md; plan WP0.4).
4. A control in the companion exists only if it calls `apply_command` through the CLI. Static HTML keeps no decision controls. A webview may offer them on that sole condition.
5. The companion's **first function is chosen from v0.1 observations** (WP4.3 runs and real use), for example:
   - the "pending decision" card;
   - navigation to a piece of evidence by `result_id`;
   - the policy comparison.

   It is not designed in full up front. It is then measured against the chat, HTML, and notebook workflow, which must remain usable on its own.

## Preparations made in v0.1 (cheap, and useful to v0.1 itself)

| Measure | Where | Cost |
|---|---|---|
| Versioned, documented JSON schema for `status`, `plan`, `run`, `decide`, and refusals (`hypotrail.status/1`, stable error codes), with contract tests | WP1.4, `docs/specs/CLI-CONTRACT.md` | low |
| Single view `view.build(study) -> dict` as the source for the HTML, the notebook, and later the webview. Renderers consume the view, not raw state (exercised by the WP0.6 prototype, ADR 0001) | WP1.3 (`read.py`), WP3.1 | near zero |
| Confirmation carries `channel: chat\|cli\|webview` and `actor` from schema 1, so no migration is needed later | §3.2, WP1.4 | none |
| Proposals are first-class objects (`proposal_id`, restatement, status). A future "Confirm" button calls `decide confirm` | already planned | none |
| Maintained rule: a control exists only if it calls `apply`. It is forbidden in static HTML and allowed in the webview on that condition | §6 | none |
| Change detection without a daemon: atomic writes, append-only `revisions.jsonl`, and `status --since REV`. A webview can watch `.hypotrail/state.json` | WP1.2 | already planned |
| Chat and webview concurrency is covered by `expected_revision` and `request_id`. A test runs two clients in parallel on one proposal: a single confirmation, and the other client gets a refusal with a diff | `test_apply.py` | low |
| Latency: `status`, `plan`, and `view` import neither pandas nor scikit-learn (deferred imports). A test records the import time of `status` (value recorded, no invented threshold) | WP1.4 | low |
| Teaching texts (glossary, step labels, explanations) stored as data in `mlkit/study/content/*.yaml`, not hard-coded in the HTML renderer | WP3.1 | low |
| `policy.evaluate` stays pure. A read-only `preview policy --rule …` computes without recording anything; it serves the workbench slider now and the webview later | WP2.4 | low |
| A study is found by its `.hypotrail/` marker and `hypotrail status --study`, without a global registry | WP1.2 | none |

## Not done now

- No webview code.
- No server, daemon, websocket, or SQLite.
- No UI framework choice.
- No integration of the VS Code language-model API.
- No modification of `experimental/companion/`.

## Consequences

- There is one source of truth. Every surface (chat, CLI, notebook, HTML, and later the webview) sees the same revision, the same proposals, and the same `user_words`. A stale webview gets the same `stale_revision` refusal, with a diff, as a stale chat.
- The CLI's JSON output becomes a public contract. Changing it requires a schema version bump and contract-test updates, which v0.1 needs anyway for agent reliability.
- Process start-up latency matters, because a webview will call `status` often. The import-time test makes regressions visible.
- Resuming the companion means writing a new thin client. Code from `experimental/companion/` can be reused only where it does not carry state or protocol, for example rendering helpers. Its bridge and SQLite session do not carry over.
