# ADR 0004: The advanced companion, staged behind the flag

- Status: accepted for specification (the owner approved the feature set, 18 October 2026). The open questions are answered (below). WP-0, the engine work packages E1 to E3, and the client work packages U1 to U5 are done and integrated (WP-I, decisions CI.1 to CI.17): stages v1 to v3 are **implemented behind the flag**, whose default stays off with stage `v0`. They are tested in Node, an offline browser, and on the real CLI with Bank and Auto MPG studies, and **not run inside a real VS Code** yet (the stage exit criteria below stay open).
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
| 6 | **v1.** Regenerate (W5) and acknowledgement (W6) stay in v1 (CA.10). |
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
