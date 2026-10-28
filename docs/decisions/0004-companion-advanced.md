# ADR 0004: The advanced companion, staged behind the flag

- Status: accepted for specification (the owner approved the feature set, 18 October 2026). The open questions are answered (below). WP-0, the engine work packages E1 to E3, and the client work packages U1 to U5 are done and integrated (WP-I, decisions CI.1 to CI.17): stages v1 to v3 are **implemented behind the flag**, whose default stays off with stage `v0`. They are tested in Node, an offline browser, and on the real CLI with Bank and Auto MPG studies, and **not run inside a real VS Code** yet (the stage exit criteria below stay open). Amended by WP-A5 (v0.2a, 2026-10-19; editable-copy extension 2026-10-23): decision 7, "local launch" (the three Marimo launches), and the two-layer copy of the specification (§15.1). Amended by WP-E1 (v0.3, 2026-10-20): decision 8, the **narrowing** that withdraws W1, W2, and W3 (owner decision R23, integrator decision I2); the panel's writes are W4–W7. Amended by WP-E2 (v0.3): decision 9, W4 runs `eda.correlation` without a column, and the panel language (R21). Amended on 2026-10-27: decision 12, **W6 withdrawn** (owner decision R31); the panel's writes are W4, W5, and W7, and the panel takes the lesson style of the approved mockup (display only). Amended on 2026-10-27 (later the same day): decision 13, **one page instead of tabs** ("Now, then the path"), a panel-only theme toggle, and a step-1 sample of development rows that counts as a look at the target (owner decisions on the synthesis mockup); implemented behind the flag, not run in a real VS Code.
- Date: 18 October 2026
- Builds on: [ADR 0002](0002-companion-as-cli-client.md), the companion as a client of the CLI, and [ADR 0003](0003-companion-webview-v0.md), companion v0 and decisions CW.1–CW.12
- Specification: [COMPANION-ADVANCED.md](../specs/COMPANION-ADVANCED.md)
- Engine contract: [CLI-CONTRACT-COMPANION.md](../specs/CLI-CONTRACT-COMPANION.md)
- Plan: [COMPANION-ADVANCED-PLAN.md](../plans/COMPANION-ADVANCED-PLAN.md)

## Context

v0 has one write function, the pending decision card, behind a flag that is off by default. Its status:

- it was not run in a real VS Code;
- no junior has used it;
- the measurements ADR 0003 asked for have not been taken.

The owner has approved a larger feature set. Its 11 groups are listed in the scope table below, together with an EDA tab. It comes with six static mockups and asks for a specification precise enough for parallel agents to implement end to end. AGENTS.md keeps companion development off the critical path of the junior workflow. This ADR therefore extends ADR 0003 under the same constraints: one more client of the CLI, no state of its own, and a flag that is off by default.

## Decision

1. **Scope.**

   | Group | What | Stage |
   |---|---|---|
   | A | orientation (study map, recap, "since your last session") | v1 |
   | B | decision center (cards, impact preview, typed confirmation, withdraw, reconfirmation queue, history) | v1 |
   | C | evidence explorer (registry, lineage, exposure ledger, deep links) | v2 |
   | D | read-only What if? (policy slider or residual explorer, "Propose this rule") | v2 |
   | E | uncertainty bars and small-data warnings | v2 |
   | F | health (deliverables and Regenerate, interrupted executions and acknowledgement, check findings) | v1 |
   | G | learning layer (glossary hovers, concept cards, predict before you look) | v3 |
   | H | agent bridge ("Ask the agent about this", copy, or insert where verified) | v2 |
   | I | handoff export and reviewer mode | reviewer v1, export v3 |
   | J | session report viewer | v3 |
   | K | multi-study switch | v1 |
   | — | EDA tab (gallery of registered results, "Request a chart" on training rows) | v2 |

   Out of scope:

   - embedded chat or LLM calls;
   - computation, state, or a server of its own;
   - model fitting, split, or policy evaluation from the webview;
   - notebook editing;
   - "validate all";
   - delegation, notes, or holds from the webview.

2. **Two writes are added, and the whitelist is closed.** The webview's writes are W1–W7 (spec §7):

   | Write | Stage | Status |
   |---|---|---|
   | confirm, withdraw | v0 | kept |
   | `render` | v1 | added |
   | `run --acknowledge-interruption` with typed words | v1 | added |
   | `decide propose` of `policy` or `model_choice`, with the engine's draft texts and `--channel webview` | v2 | **new kind of write** |
   | `run eda.*` per column, on training rows | v2 | **new kind of write** |
   | `export handoff`, outside the study state | v3 | added |

   - **Why a proposal is allowed and a confirmation stays typed.** A proposal is not a decision (AGENTS.md). The engine's draft (`preview proposal`) writes the restatement, never the client and never an LLM. A draft exists only for a rule or model that already has a current, verified evaluation, so the proposal is confirmable and no new validation exposure is created from the panel.
   - **Why EDA is allowed.** It reads training rows only, its exposure is recorded (`train_eda`), and it adds a result without replacing anything (dependency row 9). Free exploration stays in the workbench.
   - `policy.evaluate` stays in the chat, because it records `validation_policy_selection`.

3. **Engine additions.** CLI-CONTRACT-COMPANION C1–C11. All of them are additive.
   - The new read commands (`status --summary --digest`, `decisions`, `preview effects`, `preview proposal`, `evidence`, `explain`) never write, never record exposure, and work in a read-only process.
   - `preview effects` and `decide confirm` share one function, so the preview cannot drift from the confirmation.
   - `eda.distribution:<column>` reads one column of the training rows.
   - `export handoff` writes files under `--out` only.
   - The additions live in a separate contract document, so that the frozen CLI-CONTRACT.md is touched once, by the integrator.

4. **Deep links: a URI handler in the extension, none in the static report** (not even opt-in, CA.1).
   - The extension handles `vscode://hypotrail-local.hypotrail-companion/result/<id>` (and `decision/`, `proposal/`).
   - The report gets anchors `r-<result_id>`, and no `vscode:` links. A link is not a decision control, but a link in a portable, offline, shareable report that only works inside one editor is dead weight for reviewers, and it blurs the report's "no decision controls" statement.
   - "Go to a result..." accepts the id that every number already carries.

5. **Flags.**
   - The master flag `hypotrail.companion.enabled` stays, with default `false`.
   - One stage enum is added, `hypotrail.companion.stage`, with values `v0` to `v3` and default `v0`. There are no per-feature flags: they would multiply the test matrix, and they would make observation sessions hard to reproduce.
   - Two safety or preference booleans are added:
     - `chatInsert`, default `false`, because the chat insertion API is unverified; it is not contributed in `package.json` (hidden) and has no environment override until it is verified (CA.8);
     - `reviewer`, default `false`. Reviewer mode refuses every write except the handoff export (CA.9).
   - One preference is added: `learningLayer`, default `true`, effective only from v3.
   - The default stage moves up only by amending this ADR, after the exit criteria of that stage are met.

6. **Code structure for parallel work.** The webview script is split into a core and one file per view. These files are concatenated in a fixed order and inlined under the nonce, so there is still no build step and no dependency. The controller dispatches to one handler module per view group. A versioned message protocol (`hypotrail.panel/2`) and the model schemas are frozen first, with tests (plan, WP-0).

7. **Local launch (amendment, WP-A5, 2026-10-19; extended 2026-10-23 by the owner's request for an editable generated-study variant; owner decision 9 of the [v0.2 synthesis](../plans/V0.2-REVIEW-SYNTHESIS.md), AGENTS.md amended).** A third category besides reads and writes: the panel may **open the study's three notebooks with Marimo's own local server**, and nothing else:

   | Launch | Command | Stage |
   |---|---|---|
   | L1 "Open in Marimo (read)" | `marimo run notebooks/study_generated.py` (the generated notebook is regenerated, so it opens read-only) | v0 |
   | L2 "Open in Marimo (edit)" | `marimo edit notebooks/study_editable.py` (follows the generated notebook until its first user edit, then is never overwritten; not offered in reviewer mode) | v0 |
   | L3 "Open in Marimo (edit)" | `marimo edit notebooks/workbench.py` (the junior's own file; not offered in reviewer mode) | v0 |

   - **The argv.** The engine's `deliverables.launch.<name>.argv` from `status --json` (CLI-CONTRACT §3, remark R7) when it has exactly the form `uv run --project <dir> marimo <mode> <file>` or `<python> -m marimo <mode> <file>` with the notebook's absolute path; else the same built from the study's recorded CLI argv in `.hypotrail/agent.json` (`uv run --project <engine>/framework marimo …`). Anything else starts nothing (`lib/launch.js`).
   - **How it starts.** `vscode.window.createTerminal({name, shellPath, shellArgs, cwd})`: an argument list, never a shell string, and nothing is typed into the terminal. The terminal is named after the notebook and is reused while it is open for the same file. The panel does not own the process: the junior stops it with Ctrl+C in that terminal, as the panel says.
   - **What it is not.** It is not a write: nothing in the study changes, so it has no W number, no revision, and no request id. It is not a server of the panel's own (AGENTS.md: Marimo's own local editor server may be used), not `child_process` (still only `lib/cli.js`), and it reads no study state.
   - **Checked.** `scripts/check_layout.py` (`companion_terminal_errors`, tested in `test_check_layout_launch.py`) allows one `createTerminal` call, in `extension.js`, with `shellPath` and `shellArgs`, after `launch.isMarimoLaunch` accepted the argv, and `lib/launch.js` naming exactly `marimo run` of the generated notebook and `marimo edit` of the editable copy or workbench; `sendText`, a literal shell path, and a pseudo-terminal are refused; `child_process`, `exec`, and `spawn` stay forbidden.
   - **Why at v0.** Opening the deliverables is a read of the junior's own files, already allowed at v0 (Open); the default stage does not move.

8. **Narrowing: decisions in the chat only (amendment, WP-E1, 2026-10-20; owner decision R23 of [OWNER-DEMO-2-REMARKS](../acceptance/OWNER-DEMO-2-REMARKS.md), integrator decision I2 of [V0.3-DECISIONS](../plans/V0.3-DECISIONS.md)).** W1 (confirm), W2 (withdraw), and W3 (propose) are **withdrawn at every stage**. The whitelist of decision 2 is now:

   | Write | Stage | Status |
   |---|---|---|
   | confirm, withdraw (W1, W2) | — | **withdrawn** (R23) |
   | `decide propose` (W3) | — | **withdrawn** (I2) |
   | `run eda.*` per column, on training rows (W4) | v2 | kept |
   | `render` (W5) | v1 | kept |
   | `run --acknowledge-interruption` with typed words (W6) | v1 | kept |
   | `export handoff`, outside the study state (W7) | v3 | kept |

   - **Why.** The owner decided that, for now, every decision goes through the chat: a second place to answer made the panel harder to follow and let a junior get lost (R23, which supersedes the panel part of R16 and R22). W3 is the same kind of write: it creates a proposal outside the chat, so it goes with W1 and W2 (I2). W4–W7 decide nothing and stay.
   - **What replaces them.** The pending decision card is read only: the restatement, the value in words, "If you confirm" in words ("Confirming changes nothing already done." when nothing is invalidated; what stays current under Details), "Answer in the chat", and "Ask the agent about this", which copies a ready question for the chat (the agent bridge of group H, a clipboard copy and not a write; it is now offered from v0 for this card). The proposal id, its revision, and its origin are under Details. In What if?, the engine's draft of an evaluated rule or model is shown read only next to "Ask the agent to propose this", which copies a question; the agent proposes it in the chat.
   - **Checked.** `lib/cli.js` has exactly the builders W4–W7; `lib/protocol.js` has no `confirm`, `withdraw`, or `propose` message (they are dropped as unknown); `scripts/check_layout.py` (`companion_decide_errors`) refuses any client source that invokes `decide confirm`, `decide withdraw`, or `decide propose`, as an argv array or a command string.
   - **Consequences for this ADR.** The v1 exit criterion "confirm and withdraw" in a real VS Code session, the "Confirmations" and "What if? proposals" measurements for the webview channel, and the first two risks of the table below no longer apply to the panel: confirmations happen in the chat, where the engine's word rules apply unchanged. Proposals recorded with `origin.channel == "webview"` before this amendment stay valid and are shown as such. The default stage does not move. Bringing a decision write back to the panel needs a new explicit owner request and a new amendment.
9. **W4 scope and panel language (amendment, WP-E2, v0.3, 2026-10-20).** The owner's v0.3 plan asks for a predictor-versus-predictor correlation matrix that the panel's W4 can run (R28). W4 now also runs `eda.correlation` **without a column**: the engine's structural reading of the development rows' features, which reads no target and is never counted as a look; the controller accepts it only when the catalog lists it with `per_column: false` and `runnable: true`, and only that activity (`lib/models/eda.js` `WHOLE_STUDY`). No other whole-study `eda.*` run is added. The panel also gets a language (R21, owner decision): the setting `hypotrail.companion.language` (`auto`, `en`, `fr`) and a header EN | FR toggle kept in `vscode.setState`; neither writes study state. The default stage and the flag do not move.
10. **The engine names the panel's tabs (amendment note, 2026-10-26, owner session remark R1).** The agent's chat now ends each message that shows or changes something with one line naming the panel tab that shows it, only when the panel is on. To know that, the engine reads the same flag and stage the extension reads (`HYPOTRAIL_COMPANION`, `HYPOTRAIL_COMPANION_STAGE`, and the study's `.vscode/settings.json`) and copies the panel's tab labels per stage (`mlkit.study.companion_env`, `next_action.panel`, CLI-CONTRACT §3.2); a test checks the copy against `media/copy*/core.js` and `media/views/*.js`. This is a read of configuration by the engine, not a change to the panel: no new write, no new message, no stage change, the default stage and the flag unchanged, and the chat, report and notebook workflow complete without the panel (the key is absent when it is off).
11. **The engine names the panel's sections; the panel shows a choice the chat waits for and one card per variant (amendment note, 2026-10-26, owner session remarks R1b, R16, R11).** The panel line now points at what the message shows rather than at the next step: `next_action.panel.shown` names the tab and the section (a heading of the panel's copy, verbatim, checked by `test_panel_labels.py`) that show what the command produced, or is null when it produced nothing the panel shows (CLI-CONTRACT §3.2). This is the same one-way read of configuration as note 10: no write, no message, no stage change, and the panel's behaviour does not depend on it. Two read-only display changes follow in the panel: from stage `v1`, a choice the chat asks before any proposal (the conclusion, the model choice; `next_action.choice_options`) is shown under "Waiting for your answer" as a card with the engine's options, "Answer in the chat" and the copy-only "Ask the agent about this" (decision 8: no control, no field, the choice is made and adopted in the chat); and Evidence shows one card per compared variant, not only the family variants. The data card and the quality check gain section headings. The writes stay exactly W4–W7, the default stage stays `v0`, and the chat, report and notebook workflow stays complete without the panel.

12. **W6 withdrawn; the lesson style (amendment, 2026-10-27; owner decision R31 and notes R27–R30 of [copilot-companion-2026-10-26](../acceptance/runs/copilot-companion-2026-10-26.md)).** The acknowledgement of an interrupted execution in typed words (W6, `run --acknowledge-interruption`) is **withdrawn at every stage**, for the same reason as decision 8: words that the engine records as the junior's are given in the chat only. The whitelist of decision 2 is now:

   | Write | Stage | Status |
   |---|---|---|
   | confirm, withdraw, propose (W1, W2, W3) | — | **withdrawn** (R23, I2) |
   | `run eda.*` on training rows, or `eda.correlation` without a column (W4) | v2 | kept |
   | `render` (W5) | v1 | kept |
   | `run --acknowledge-interruption` with typed words (W6) | — | **withdrawn** (R31) |
   | `export handoff`, outside the study state (W7) | v3 | kept |

   - **What replaces it.** The Overview still shows an interrupted execution (its reason, what it may have touched), read only: a line says that acknowledging it is done in the chat, in the junior's own words ("ok" alone is not enough), and "Ask the agent about this" copies a ready question for the chat (a clipboard copy, not a write). The engine's acknowledgement command, its word rules and its refusals are unchanged; only the panel's way to call it is removed.
   - **Removed from the client.** The words field and its button, the `acknowledge` webview message (an earlier webview's message is dropped as unknown), the `acknowledgeArgv` builder and its timeout, the acknowledgement refusal texts specific to the panel, and the `ackDrafts` of `vscode.setState` (a state saved by an earlier panel loses them on load).
   - **Checked.** `lib/cli.js` has exactly the builders W4, W5, and W7; `lib/protocol.js` lists `WRITE_OPS` W4, W5, W7; `scripts/check_layout.py` (`companion_acknowledge_errors`) refuses any client source that builds `--acknowledge-interruption` or defines an acknowledgement argv builder, next to `companion_decide_errors`.
   - **The lesson style (display only).** The panel takes the look and the guidance of the owner-approved mockup `docs/plans/mockups/panel-lesson-style-fr.html` (specification §6.0, LS-1 to LS-6): a journey rail and a position line, "At this step" and "Next" on every tab, a guided reading for every chart, notions that put the term first and then the study's values, "Learn more" folds, and the board theme mapped from the VS Code theme class (High Contrast keeps the editor's colours). The next move's only new action, "Copy the question", is a clipboard copy. It adds no write, no message type that changes the study, no state, and no tab.
   - **Consequences.** The v1 exit criterion and measurements that named the acknowledgement in the panel no longer apply to it; an interruption is acknowledged in the chat, where the engine's word rules apply. The default stage stays `v0`, the flag stays off by default, and the chat, report and notebook workflow stays complete without the panel. Bringing W6 back needs a new explicit owner request and a new amendment.

13. **One page instead of tabs (amendment, 2026-10-27; owner decisions on `docs/plans/mockups/panel-synthesis-fr.html`, notes R32 and R33 of [copilot-companion-2026-10-26](../acceptance/runs/copilot-companion-2026-10-26.md)).** Accepted; **implemented behind the flag; not run in a real VS Code** (integration I-1, 2026-10-27: the panel side P-0 to P-8 and the engine side E-1 to E-8 of [PANEL-ONE-PAGE-PLAN](../plans/PANEL-ONE-PAGE-PLAN.md); the specification §3.2, §4, §6, §10, §16 and CLI-CONTRACT §17, contract P1, describe it; the one-page pixel baselines wait for the owner's review). The tabbed panel of decisions 10 to 12 is replaced.
   - **Layout.** The six tabs are replaced by one page in a fixed order: a sticky header (study, final-test seal, the engine's "not yet defensible" list as a pill, theme, more) and a one-line progress grouped by phase (R32: no step labels side by side); then, in the flow, "To handle" (only items outside the current step: an interrupted execution, stale deliverables, check findings), **Now** (what the chat waits for, the engine's options as plain text, "copy a question", the figure that helps answer, its plain-language reading, and the limit line), **the path** (one line per step with its decision and basis, folded by phase except the current phase and any step that is automatic, reopened, delegated or held; a ledger line of exposure and trials), and the **tools** as in-flow drawers (data and another chart, What if?, notions, deliverables).
   - **Stages.** v0: header, progress, To handle (read only), Now without figures (question, options, copy, the limit line), the path with decision values and the ledger line, deliverables with Open and the Marimo launches. v1 adds Regenerate (W5), "since your last visit", "what your answer will change", the study switch and reviewer mode. v2 adds the data card with its sample, the figures in Now and in the path, another chart (W4) and What if?. v3 adds the inline notions and "my notions", the handoff export (W7) and the session report. The default stage stays `v0`.
   - **Theme (R33).** A panel-only theme control (follow VS Code, dark, light) is allowed, kept in `vscode.setState` (`theme`, added to the keys of specification §10) as a per-viewer convenience: not study state, not a write. High Contrast themes always override the manual choice. This supersedes the "no theme button" clause of specification LS-6. The EN | FR toggle of decision 9 moves into the "more" menu.
   - **What if? is kept**, with a visible warning that a rule or model changed after seeing the validation figures is a result-dependent change. The engine marks any such change made after its validation evaluation exists, whether or not What if? was opened; the preview itself still records nothing.
   - **Step-1 sample (engine).** The data card shows a fixed random sample of development rows (a seed derived from the study and the data, row ids shown), target included, instead of the first rows of the file; the same rows appear in the panel, the report and the notebook. Showing their target values is a look at the target: the engine records it once per seed in the exposure ledger as pre-split development target values (not training-partition EDA), and the panel says so. With time-ordered folds these rows later fall in validation blocks; the ledger entry says so. Never a sealed final-test row; a study without a final test samples its development rows the same way. The special-value rows are listed without their target. A study created before the sample records its look only with a write that commits, never with a refused one, and a study whose split was confirmed before that write never records it and keeps the sample's target hidden, with the reason (integrator decision, 2026-10-28).
   - **Superseded once implemented.** The tab labels of decision 10, the "tab and section" of decision 11 (`next_action.panel.shown`, `test_panel_labels.py`) and the rail and tab clauses of LS-1: the engine names anchors instead (`now`, `todo:<kind>`, `path:<step>`, `tools:<drawer>`), replacing `panel.tabs` and `where.tab` in a versioned contract change, and the agent texts that place the panel line follow.
   - **Unchanged.** The writes stay W4, W5, and W7 (decision 12) and the three Marimo launches; the panel decides nothing and records no words; the flag stays off by default; the chat, report and notebook workflow stays complete without the panel.
   - **Needed before code.** Engine additions: automation and review queue in the digest, the awaited question as junior text, the opening time, a per-configuration criterion status, a per-step headline, a result's channel, the seeded sample and its ledger entry, and the special-value rows.

## Staging and exit criteria

Each stage ships behind `stage`, and the default stays `v0` until the stage's criteria are met.

| Stage | Contents | Exit criteria (all required) |
|---|---|---|
| **v1** | Overview (A, F), Decisions (B), studies (K), reviewer | 1. The gate is green: `check_layout`, the framework pytest scope with the browser group, `node --test`, and the companion Playwright tests. 2. The companion contract tests for C1, C2, C3, and C10 (check locations) pass, with no `xfail` left for them. 3. **One real VS Code session**, as a manual checklist in the plan, records: the CSP and theme in light and dark; workspace trust; the watcher after an atomic rename; confirm and withdraw; acknowledgement; Regenerate; the study switch; and the `onUri` activation with the flag off. 4. The two observation sessions of ADR 0003 (flag off, then stage v1) are run. The rate of confirmations that are accepted but do not restate the decision is no higher with the panel |
| **v2** | EDA, Evidence, What if?, uncertainty, agent bridge | 1. The v1 criteria still hold. 2. Contract tests C4, C5, C8, C9, and C10 (anchors) pass. 3. Real VS Code: the What if? slider latency is recorded; `chatInsert` is verified to insert without sending, and, if it holds, its default is reconsidered; the deep link from the chat works. 4. One observation session at v2 on Bank, and one on Auto MPG. On Auto MPG, the forbidden-vocabulary scan of the DOM is clean |
| **v3** | Learn & hand off (G, I export, J) | 1. Contract tests C6 and C7 pass; `check --text handoff.md` is clean on the Bank and Auto MPG walkthroughs. 2. The learning layer's local storage holds only the keys of spec §10, as an inspected `globalState` dump shows. 3. One reviewer reads a handoff pack without the companion and answers the comprehension items of the observation grid about the decisions and limits |

## What is measured

Measured per stage, with the flag off as the baseline. The sources are `session-report` and the observation grid.

- **Confirmations.** For each channel: refused confirmations and their reasons, the time each proposal stays open, and how many confirmations were accepted although they did not restate the decision. A rise in that last rate is a stop signal.
- **Holds and staleness.** Whether the junior notices a hold, a stale proposal, or an exit-3 deliverable without being told: grid items.
- **Navigation.** Navigation to evidence: how often a junior opens a result's detail or lineage before confirming the policy or the model choice, observed by the facilitator. The panel keeps no counter.
- **EDA.** The number of `eda.*` runs started from the panel against the chat (`session-report.runs`), and any EDA result the junior cites wrongly.
- **What if? proposals.** The share of `policy` and `model_choice` proposals made from the panel (`origin.channel`), and whether those proposals are then confirmed with words that restate them.
- **Self-sufficiency.** The chat, the report, and the notebook stay usable without the panel: every grid task can be done with the flag off.

## Risks

| Risk | Mitigation |
|---|---|
| The panel becomes the cheapest path to a confirmation, and "type anything" replaces thinking | The textarea is never filled and there is no one-click action (INV-5); the engine's word rules apply unchanged; the impact preview sits next to the words; this is measured, and a rise in non-restating confirmations stops the stage |
| A webview proposal is read as the junior's own restatement | The restatement comes from the engine's draft; it is labelled "proposal from this panel"; the origin is recorded (C9) |
| What if? figures are read as adopted or as forecasts | The banner is present in every state (WI-1); preview values never leave the tab (WI-5); preview records nothing (CLI-CONTRACT §8.1) |
| EDA from the panel turns into fishing | Training rows only; a catalog of the engine's activities and columns only; rows seen are shown; free exploration is sent to the workbench |
| The preview of effects drifts from the real confirmation | One shared function; a test checks equality on every walkthrough confirmation |
| Chat insertion submits a message | `chatInsert` defaults to off; the clipboard is the default; verification is part of the v2 exit criteria |
| Contract sprawl | A separate document, additive only, with contract tests written first (strict `xfail` until implemented) and one integrator |
| Startup latency of `uv run` makes the panel feel slow | A call budget, caching per revision, debounce, and coalescing (spec §11); the latency is recorded in a real session |
| Parallel agents conflict on shared files | File ownership map; WP-0 creates every shared skeleton and stub first (plan) |
| Nothing has been checked in a real VS Code | Each stage's exit criteria include a real session; until then, the documents say "not run inside a real VS Code" |

## Open questions for the owner

**Answered by the integrator, 18 October 2026** (recorded as decisions CA.1 to CA.10 in [V0.1-DECISIONS](../plans/V0.1-DECISIONS.md), section "Companion advanced"):

| # | Answer |
|---|---|
| 1 | **No.** No `vscode://` link in the report, not even opt-in. The report keeps the anchors `r-<result_id>` only (CA.1). |
| 2 | **Yes.** The engine's 20-minute gap rule is accepted for "since your last session" (CA.6). |
| 3 | **Chat.** `policy.evaluate` stays a chat act; the panel proposes evaluated rules only (CA.7). |
| 4 | **Yes.** One `hypotrail.companion.stage` setting, no per-feature flags (CA.8). |
| 5 | **Yes.** Reviewer mode may export a handoff pack (W7); every other write stays refused in reviewer mode (CA.9). |
| 6 | **v1.** Regenerate (W5) and acknowledgement (W6) stay in v1 (CA.10). W6 was later withdrawn (decision 12, R31). |
| 7 | **Yes.** WP-E1 adds `task` to `status --summary --digest`, after `digest`; without `--digest` the summary is unchanged (CA.3). |
| 8 | **Clipboard only.** The agent bridge copies to the clipboard. `chatInsert` stays off and hidden (not contributed in `package.json`, no environment override) until a real VS Code session verifies that insertion does not send (CA.8). |

The questions as they were asked:

1. **Deep links in the report.** Should an opt-in render setting add `vscode://` links to the cited numbers of the local report, with the shared handoff copy kept link-free? The default is no links (decision 4).
2. **"Since your last session".** It is derived by the engine from gaps of 20 minutes or more between revisions. It is not "since this panel last looked", which would need a stored revision in `workspaceState`. Is that acceptable?
3. **Proposals from the webview, for unevaluated rules.** Only evaluated rules can be proposed. Should the panel also be allowed to run `policy.evaluate` for one rule, which records `validation_policy_selection`, or should that stay in the chat, as now?
4. **Stage default.** Is a single stage enum acceptable, instead of per-feature flags?
5. **Reviewer export.** Should reviewer mode be allowed to export a handoff pack? It writes no study state, but it writes files.
6. **Acknowledgement and Regenerate from the panel.** Both were approved under F. Should they move to v2, so that v1 stays closer to the v0 write set during the first observations?
7. **`task` in `status --summary`.** It is a small additive key that removes the client's inference from step ids. Should WP-E1 add it?
8. **Copilot chat insertion.** `workbench.action.chat.open` with `{query, isPartialQuery}` is unverified. If it cannot be verified as non-sending, should H stay copy-only?

## Consequences

- The engine gains six read commands or options, one activity, and one optional proposal key. CLI-CONTRACT.md gets a §8.7 pointer and freeze-test entries when the first engine work package lands.
- `check_layout.py` changes: new activation events (`onUri` and two commands), and the default of the stage setting.
- The v0 panel keeps working at `stage: v0`, rendered by the new framework, and its tests are migrated, not dropped.
- Companion development remains outside the junior workflow's critical path (AGENTS.md). This ADR authorises the specification and staged implementation behind the flag, nothing more.
