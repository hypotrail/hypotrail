# Hypotrail study companion (behind a feature flag)

A VS Code webview panel for one Hypotrail study. It is **one more client of the `hypotrail` CLI** ([ADR 0002](../../docs/decisions/0002-companion-as-cli-client.md)). Its first scope is [ADR 0003](../../docs/decisions/0003-companion-webview-v0.md) (stage v0); the staged advanced panel is [ADR 0004](../../docs/decisions/0004-companion-advanced.md), specified in [COMPANION-ADVANCED.md](../../docs/specs/COMPANION-ADVANCED.md) with the engine interfaces of [CLI-CONTRACT-COMPANION.md](../../docs/specs/CLI-CONTRACT-COMPANION.md). It is **off by default**. The chat, the HTML report, and the notebook remain the workflow; the panel adds nothing they need.

This is not the paused companion in `experimental/companion/`: it shares no code, protocol, bridge, database, or language-model integration with it. Module boundaries and the frozen interfaces are in [ARCHITECTURE.md](ARCHITECTURE.md).

## Stages

One setting, `hypotrail.companion.stage` (default `"v0"`; `HYPOTRAIL_COMPANION_STAGE` overrides it), selects the feature set. Each stage includes the earlier ones; a tab or control of a later stage is absent, not disabled. The default moves only through an ADR amendment after a stage's exit criteria are met, including the [manual checklist](MANUAL-TEST.md) in a real VS Code, which has **not** been run.

| Stage | Tabs and features | Writes it allows (spec §7) |
|---|---|---|
| `v0` (default) | one page: recap, plan, deliverables, pending decision cards (read only: "Answer in the chat", and "Ask the agent about this" copies a ready question) | none (W1 confirm and W2 withdraw were withdrawn in v0.3, ADR 0004 decision 8) |
| `v1` | **Overview** (map, recap, since your last session, deliverables, health: executions, check findings), **Decisions** (cards with the engine's "if you confirm" preview, a read-only card for a choice the chat asks before any proposal with the engine's options, reconfirmation queue, history), the study switch, reviewer mode | + W5 Regenerate, W6 acknowledge an interrupted execution in typed words |
| `v2` | **Data & EDA** (the data card and the quality check under their own headings, the gallery titled by questions with intervals, the null band and the leakage detector; run another per-column chart on training rows), **Evidence** (the final test first: sealed, opened once, or changed after; the exposure ledger in words; development evidence, with cross-validation and one card per compared variant (its figures beside the candidate's, its tuning per fold, its coefficients or its family's diagnostics), apart from final evidence; diagnostics; results, lineage, uncertainty, deep links), **What if?** (policy sandbox with threshold, capacity or share rules and the gain curve, or residual explorer; for an evaluated rule or model, the engine's draft and "Ask the agent to propose this"), "Ask the agent about this" (copies a question for the chat) | + W4 run an `eda.*` chart of the engine's catalog (W3 propose was withdrawn in v0.3) |
| `v3` | **Learn & hand off** (glossary hovers, concept cards, predictions kept on this computer, the handoff export, the session report) | + W7 export a handoff pack (files only; also in reviewer mode, decision CA.9) |

At every stage the Overview opens on "Your next move" (what waits for you, why, and where to answer), and "Your deliverables" offers "Open file" and, since WP-A5, **"Open in Marimo (read)"** for the generated notebook (`marimo run`) and **"Open in Marimo (edit)"** for the editable study copy and workbench (`marimo edit`), started in a named VS Code terminal with an argument list (ADR 0004, decision 7 "local launch"); that changes nothing in the study. The editable copy follows the generated notebook until its first user edit, then is never overwritten. The panel shows the engine's texts written for you, or its own words, and keeps the engine's instructions to the assistant, ids, and recorded tokens under "Details" (COMPANION-ADVANCED §15.1).

Every decision is proposed, confirmed, or withdrawn in the chat (v0.3 narrowing, owner decision R23, ADR 0004 decision 8): the panel shows the open proposals read only and copies a question for the chat. When the panel is on, the engine tells the agent which tab and section show what each command produced (`next_action.panel.shown`, owner session 2026-10-26, R1b), so the chat's panel line names a section that has something in it; the panel itself ignores that key. Opening the final test and changing the confirmation mode are chat acts too: the panel explains them and offers no control (WP-B5). The panel never confirms, withdraws, or proposes, never delegates, never records or resolves a note, never fits, splits, or evaluates, and never runs a command outside the four writes W4–W7 and the three Marimo launches. Every write carries a new request id and the revision the junior saw (except Regenerate and the export), and every refusal is shown with the engine's message verbatim.

Other settings: `hypotrail.companion.learningLayer` (default `true`; stage v3: off removes hovers, cards, and predictions, and `explain` is never read), `hypotrail.companion.reviewer` (default `false`; the command "Hypotrail: open the study panel (reviewer, read-only)" always opens a reviewer panel). `chatInsert` is read with default `false` but not contributed until a real VS Code session verifies that inserting into the chat does not send (decision CA.8).

## Enable it and run it from source

There is no package and no build step. Requirements: VS Code 1.90 or later, a study created by `hypotrail init` (its folder holds `.hypotrail/agent.json`), and the engine's environment (`uv sync --project framework --group dev`).

1. Turn the flag on: setting `hypotrail.companion.enabled` to `true`, or start VS Code with `HYPOTRAIL_COMPANION=1` in its environment. With the flag off, every command and a `vscode://` link show "Companion disabled (feature flag)" and nothing else runs.
2. Choose a stage: setting `hypotrail.companion.stage` (`v0` to `v3`), or `HYPOTRAIL_COMPANION_STAGE=v2` in VS Code's environment. A settings change applies to the open panel at once.
3. Load the extension from this folder, either:
   - "Developer: Install Extension from Location..." and pick `clients/vscode-companion`; or
   - an Extension Development Host: `HYPOTRAIL_COMPANION=1 HYPOTRAIL_COMPANION_STAGE=v3 code --extensionDevelopmentPath=/abs/path/to/clients/vscode-companion /abs/path/to/the/study` (or F5 with a launch configuration whose `args` hold `--extensionDevelopmentPath=${workspaceFolder}/clients/vscode-companion`).
4. Open the study folder, trust the workspace, and run "Hypotrail: open the study panel". Studies are found in the workspace folders and two levels below them; with several, a quick pick lists each by folder name and path ("Pick another folder..." reaches any other); with none, a folder dialog. From v1 the header's "Study: <name>" switches study in the same panel.
5. From v2, "Hypotrail: go to a result..." takes a result id (or its first 8 or more characters, as the report shows them) and opens it in Evidence; a link `vscode://hypotrail-local.hypotrail-companion/result/<id>[?study=<path>]` does the same.

The CLI is run with the argument vector recorded in `.hypotrail/agent.json` (`cli.argv`), through `child_process.execFile`, never a shell. A study moved since `init` is refused (its recorded paths are wrong); create a new study.

## Security

- The workspace must be trusted (`capabilities.untrustedWorkspaces.supported: false`, and checked at run time): the panel executes the CLI recorded in the study.
- The webview has a strict Content-Security-Policy: `default-src 'none'`, script and style only with a per-load nonce, `connect-src 'none'`, no remote resource, no command URIs, no local resource roots. Charts are inline SVG coloured by palette classes; no `style` attribute.
- Study text is set with `textContent`; nothing from the study is parsed as HTML.
- Messages are whitelisted both ways and validated with one schema table (`lib/protocol.js`, protocol `hypotrail.panel/2`, copied to `media/protocol.js`); an unknown or malformed message, or one of a later stage, is ignored.
- The client keeps no state of its own: no database, server, socket, loopback HTTP, or browser storage. `vscode.setState` holds draft words and navigation; `globalState` holds learning-layer preferences, seen cards, and prediction answers only (spec §10). Only the agent bridge writes the clipboard (§12). `scripts/check_layout.py` checks that the flag stays default-off, that there is no runtime dependency, and that the sources use no network module, shell, or language-model API.

## Tests

```sh
node --test clients/vscode-companion/test/*.test.js
uv run --project framework python -m pytest -q -p no:cacheprovider clients/vscode-companion/test
```

Both are in the CONTRIBUTING gate. None of them is a VS Code session or a Copilot session.

- **Unit (Node, fake `vscode` and fake CLI):** `protocol`, `cli-argv`, `invariants` (spec §2), `controller` (stage gate, reviewer refusal, the payload cache shared by loaders, the write lock, outcome mapping), `fixtures`, one file per view group (`overview`, `decisions`, `eda`, `evidence`, `whatif`, `learn`, `bridge`, `localstore`, `studies`), `extension` and `unit` (commands, URI handler, study switch, trust, flag).
- **Real CLI (Node):** `integration.test.js` (v0 on a synthetic study) and `integration-v1/v2/v3.test.js`, which drive the real controller and real `hypotrail` processes on temporary Bank Marketing and Auto MPG studies created from the committed cases (outside the repository, in paths with spaces and quotes): every write W4-W7 end to end with the resulting state, the decisions made in the chat (direct CLI calls) and read back by the panel, refusals verbatim, the read budget, the exposure of W4 (training rows only), the export files, and the absence of decision-rule words in the regression study. Read wall times are printed as test diagnostics. They are skipped when `framework/.venv` is missing.
- **Browser (Playwright, offline):** `test_webview_<view>.py` and `test_webview_frame.py` run the real document under the real CSP in headless Chromium with a stub `acquireVsCodeApi`, on models produced by `lib/models/*.js` from the fixtures, in light and dark fallback themes.
- **Fixtures and coverage:** `test/fixtures/` are hand-written payloads with the mockups' values; `test/fixtures/captured/` are real payloads captured by `test/fixtures/capture.py`. `test_fixture_drift.py` fails when a hand-written fixture's keys drift from the real payloads, or when the engine drifts from the committed captures (re-run `capture.py`, then fix the fixtures it names). `test_contract_keys.py` compares the client's key lists with the engine's contract tests; `test_requirement_coverage.py` requires a test for every requirement id of the spec.

## Limitations

- **Not run inside a real VS Code.** The `vscode` API calls, the webview host (theme variables, default styles under the nonce-only CSP, message transport), workspace trust, `revealFileInOS`, and the Extension Development Host are untested. [MANUAL-TEST.md](MANUAL-TEST.md) is the checklist for the owner's first session.
- **Copilot is not involved.** The panel has no language-model or chat integration; "Ask the agent" copies a question for the junior to paste.
- No junior has used it; every feature is a hypothesis to measure against the flag-off workflow (ADR 0004).
- POSIX only, like the engine.
