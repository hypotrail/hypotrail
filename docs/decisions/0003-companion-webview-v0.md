# ADR 0003: Companion v0, a study panel behind a feature flag

- Status: accepted (owner's explicit request, 18 October 2026)
- Date: 18 October 2026
- Builds on: [ADR 0002](0002-companion-as-cli-client.md) (the companion is a client of the `hypotrail` CLI)
- Code: [`clients/vscode-companion/`](../../clients/vscode-companion/README.md)

## Context

ADR 0002 made any future webview companion a thin client of the `hypotrail` CLI, with no state, protocol, or server of its own. It said the first function would be chosen from v0.1 observations, such as the WP4.3 runs and real use. The owner has now explicitly asked for a first version behind a flag that is off by default.

No observation of a junior exists yet. The observation kit (`docs/research/OBSERVATION-PROTOCOL.md`) has not been run. The only evidence about where the chat workflow strains comes from the agentic acceptance runs. In those runs, most defects were about confirmations: bare acknowledgements, refusals read as agreement (P1), conditions the junior set (P2), and decisions lost between chats (T8). The paused companion in `experimental/companion/` must stay paused (`feature.json`, checked by `scripts/check_layout.py`).

## Decision

1. **Location: `clients/vscode-companion/`**, not `experimental/companion-webview/`.
   - `experimental/companion/` is the paused design, with its own SQLite protocol and bridge. A sibling under `experimental/` would suggest it shares that lineage, or that it falls under the same pause.
   - `clients/` names what ADR 0002 says this is: a client of the CLI contract, like the chat agent. More clients can sit beside it.
   - Its experimental status is carried by the flag, the version `0.0.1`, and this ADR, not by its folder.
2. **Feature flag, off by default.**
   - The setting `hypotrail.companion.enabled` defaults to `false`. The environment variable `HYPOTRAIL_COMPANION=1` turns it on, for tests and a development host.
   - The only activation event is `onCommand:hypotrail.companion.open`, and activation only registers that command.
   - With the flag off, the command shows "Companion disabled (feature flag)" and does nothing else: no setting other than the flag is read, no file is read, and no process is started.
   - A trusted workspace is required (declared in `package.json` and checked at run time), because the panel executes the CLI recorded in the study.
3. **Plain JavaScript, with no build step, no bundler, and no runtime dependency.** `check_layout.py` enforces the absence of dependencies.
4. **Reads go through `status --summary --json` only.**
   - There is no `view` command. `status --json` carries the full view, but it runs to tens of kilobytes and the handoff already steers clients to `--summary`.
   - `hypotrail.summary/1` holds everything the panel shows: `recap`, `current_step`, `plan`, `next_action`, `artifacts` with messages, `open_proposals` with restatements, `notes`, and `not_yet_defensible.top`.
   - The deliverable paths come from the contract's fixed artefact names (CLI-CONTRACT §8.3). This is why no engine or contract change was needed.
5. **The first function is the "pending decision" card**, the first candidate in ADR 0002.
   - The panel shows the open proposals with their restatement and value, and the holds that block them.
   - Its only write is to **confirm an open proposal in the junior's own typed words**, or **withdraw it**.
   - The textarea starts empty and is never filled by the panel, and "Confirm" is disabled until something is typed. A typed confirmation calls `decide confirm <pid> --user-words=<typed> --channel webview --actor user --request-id <fresh uuid> --expected-revision <revision shown>`.
   - Every refusal the engine gives the chat applies unchanged: `ambiguous_confirmation` (with all its reasons), `decision_on_hold`, `stale_revision` with its diff, and `precondition_missing`. The panel shows the code, the engine's message verbatim, and a short explanation, then refreshes.
   - Withdrawing asks for a modal confirmation first.
   - Rationale, given that no junior has been observed:
     - the agentic runs located the workflow's weak point at the confirmation;
     - this function is where a separate surface may help, because the restatement sits next to an answer box, and the hold and the refusal are visible in the same place;
     - it changes no engine rule, because the engine already records `channel: webview` (schema 1, ADR 0002).
   - It is a hypothesis, not a finding.
6. **The panel offers no delegation.** It has no `--basis delegated_default` and no "use your recommended default" button.
   - Delegation stays an act in the chat, where the assistant must state its recommended default in the restatement and the junior must say they hand the choice over (CLI-CONTRACT §5, D1 and R1).
   - In a panel, one button would make delegation the cheapest path, which is the opposite of what the acceptance fixes aimed at.
   - A typed delegation is refused by the engine (`delegation_needs_basis`), and the panel says to delegate in the chat.
7. **No other mutating command in v0.** There is no `propose`, `run`, `render`, `note`, `note --resolve`, or `run --acknowledge-interruption`. Holds are resolved in the chat.
8. **Change detection uses a debounced `fs.watch` on `.hypotrail/`**, filtered to `state.json`, `state.sha256`, `revisions.jsonl`, and `artifacts.json`.
   - The folder is watched rather than the files, because the engine replaces `state.json` by an atomic rename.
   - The panel also refreshes when it becomes visible, and after each of its own commands.
   - There is no polling and no daemon.
9. **Process execution.**
   - `child_process.execFile` runs the `cli.argv` list from `.hypotrail/agent.json`, never its shell string and never with `shell: true`.
   - Free text is passed as `--user-words=<text>`, so a reply that begins with `-` is not read as an option.
   - stdout must hold one JSON document. stderr is ignored, because `uv` may print warnings there.
   - When a write produces no JSON, the panel says the outcome is unknown, never that it succeeded.
   - A study whose `agent.json` records another path (a moved study) is refused.
10. **Webview security.**
    - The CSP is `default-src 'none'`, with script and style allowed only by a per-load nonce and inlined into the document.
    - It also sets `connect-src`, `img-src`, `font-src`, `frame-src`, and `form-action` to `'none'`.
    - There are no command URIs and no local resource roots.
    - Every study text is set with `textContent`.
    - Messages are whitelisted and validated in both directions.
11. **Accessibility basics and theme.**
    - Structure: headings, a label on every textarea, and `aria-current="step"` on the current step.
    - Announcements: a polite live region announces outcomes, and refusals carry `role="alert"`.
    - Focus is visible, and it is kept across a refresh.
    - Colours come from the VS Code theme variables, with fallbacks for a page shown outside VS Code.

## What is measured next

The observation sessions (`docs/research/OBSERVATION-PROTOCOL.md`) should run once with the flag off and once with it on. They should compare:

- confirmations refused and their reasons (`session-report`'s `refusals` and `decisions.refused_confirmations`), by channel;
- the time a proposal stays open (`decisions.seconds_open`);
- whether the junior's words restate the decision, as judged with the grid's comprehension items;
- whether the junior notices holds and stale proposals;
- whether the chat, report, and notebook stay usable on their own, with no step that needs the panel.

The panel must not raise the rate of confirmations that are accepted but do not restate the decision. If the comparison shows no gain, the flag stays off and the function is reconsidered from the observations, as ADR 0002 says. Navigation to evidence by `result_id` and the policy comparison remain candidates.

## Consequences

- The chat and the panel see the same revision, proposals, holds, and confirmations. A stale panel gets the same `stale_revision` refusal as a stale chat.
- A confirmation typed in the panel is recorded with `channel: webview`. It appears as such in the state, the report, and `session-report`. As with every confirmation, `authenticated` is `false`.
- No engine code or CLI contract changed.
- **Not verified in a real VS Code.** The tests use a fake `vscode` module, the real CLI, and the real webview document in headless Chromium. They do not exercise the VS Code webview host, its theme variables and default styles under a nonce-only CSP, workspace trust, or the Extension Development Host.
