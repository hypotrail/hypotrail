# Hypotrail study companion (v0, behind a feature flag)

A VS Code webview panel for one Hypotrail study. It is **one more client of the `hypotrail` CLI** ([ADR 0002](../../docs/decisions/0002-companion-as-cli-client.md)); its scope and the reasons for it are in [ADR 0003](../../docs/decisions/0003-companion-webview-v0.md). It is **off by default**. The chat, the HTML report, and the notebook remain the workflow; this panel adds nothing they need.

This is not the paused companion in `experimental/companion/`: it shares no code, protocol, bridge, database, or language-model integration with it.

## What the panel shows and does

Reads, through `hypotrail status --summary` (CLI-CONTRACT §3):

- the five-line recap;
- the current step and its position in the plan, the plan with each step's status, and the next action;
- each deliverable's status with its message, and buttons to open the report in the browser and the generated notebook or the workbench in the editor;
- the open proposals with the assistant's restatement and the proposed value;
- the open holds (notes) in the junior's words, also shown on the proposal they block;
- the top items of "not yet defensible".

One write function: for an open proposal, the junior can

- **confirm it in their own words**: the textarea starts empty and is never filled by the panel; "Confirm" stays disabled until something is typed. The panel runs `decide confirm <proposal> --user-words=<typed words> --channel webview --actor user --request-id <new uuid> --expected-revision <revision shown>`. The engine applies the same rules as in the chat: "ok", a refusal, an unrelated reply, a stale revision, or a decision on hold are refused, and the panel shows the refusal code, the engine's message verbatim, and a short explanation, then refreshes;
- **withdraw it**, after a modal confirmation (`decide withdraw`).

The panel never delegates (no `--basis delegated_default`), never proposes, runs, renders, or records a note. Those stay in the chat.

The panel refreshes when the study's `.hypotrail/state.json`, `revisions.jsonl`, or `artifacts.json` change (a debounced `fs.watch` on `.hypotrail/`), when it becomes visible, and on "Refresh".

## Enable it and run it from source

There is no package and no build step. Requirements: VS Code 1.90 or later, a study created by `hypotrail init` (its folder holds `.hypotrail/agent.json`), and the engine's environment (`uv sync --project framework --group dev`).

1. Turn the flag on: setting `hypotrail.companion.enabled` to `true`, or start VS Code with `HYPOTRAIL_COMPANION=1` in its environment. With the flag off, the command shows "Companion disabled (feature flag)" and does nothing else.
2. Load the extension from this folder, either:
   - "Developer: Install Extension from Location..." and pick `clients/vscode-companion`; or
   - an Extension Development Host: `code --extensionDevelopmentPath=/abs/path/to/clients/vscode-companion /abs/path/to/the/study` (or F5 with a launch configuration whose `args` hold `--extensionDevelopmentPath=${workspaceFolder}/clients/vscode-companion`).
3. Open the study folder, trust the workspace, and run "Hypotrail: open the study panel". With several study folders in the workspace a quick pick asks which one; with none, a folder dialog.

The CLI is run with the argument vector recorded in `.hypotrail/agent.json` (`cli.argv`), through `child_process.execFile`, never a shell. A study moved since `init` is refused (its recorded paths are wrong); create a new study.

## Security

- The workspace must be trusted (`capabilities.untrustedWorkspaces.supported: false`, and checked at run time): the panel executes the CLI recorded in the study.
- The webview has a strict Content-Security-Policy: `default-src 'none'`, script and style only with a per-load nonce, `connect-src 'none'`, no remote resource, no command URIs, no local resource roots.
- Study text is set with `textContent`; nothing from the study is parsed as HTML.
- Messages are whitelisted both ways and validated (`lib/controller.js`, `media/panel.js`); an unknown or malformed message is ignored.
- The client keeps no state of its own: no database, server, socket, loopback HTTP, or browser storage. `scripts/check_layout.py` checks that the flag stays default-off, that there is no runtime dependency, and that the sources use no network module, shell, or language-model API.

## Tests

```sh
node --test clients/vscode-companion/test/*.test.js
uv run --project framework python -m pytest -q -p no:cacheprovider clients/vscode-companion/test
```

- `test/unit.test.js` (unit): the extension with a fake `vscode` module (`test/fake-vscode.js`, a require hook) and a fake `execFile`: flag off and on, workspace trust, study discovery, argv with spaces and quotes, the webview document's CSP, refresh on file change, the exact confirm and withdraw argv, refusal and stale-revision display, malformed messages.
- `test/integration.test.js` (simulated): the controller drives the **real** CLI on a temporary synthetic study outside the repository, with the argv recorded by `init`: a bare "ok" is refused and shown verbatim; a hold refuses the confirmation; a stale revision is refused with the diff; typed words confirm and the state records `channel: webview`, `actor: user`; a change made through the CLI reaches the panel through the file watch. It is skipped when `framework/.venv` is missing.
- `test/test_webview_browser.py` (simulated browser): the real webview document in headless Chromium, offline, with a stub `acquireVsCodeApi`: no remote request, CSP present and enforced, textarea empty, "Confirm" disabled until text is typed, study text never parsed as HTML, refusal rendered verbatim, light and dark colours.

## Limitations

- **Not run inside a real VS Code.** No VS Code is available where it was built: the `vscode` API calls, the webview host (its theme variables, default styles under the nonce-only CSP, message transport), workspace trust, and the Extension Development Host are untested. The first real session must check them.
- **Copilot is not involved.** The panel has no language-model or chat integration; the chat agent and the panel see the same study through the same CLI.
- No observation of a junior using it yet: the choice of this first function is a hypothesis (ADR 0003).
- POSIX only, like the engine.
