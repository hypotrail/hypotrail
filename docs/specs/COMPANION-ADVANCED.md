# Advanced companion: detailed specification

Status: **the one-page panel is implemented behind the flag** (ADR 0004 decision 13, 2026-10-27; packages P-0 to P-6 and P-8 of [PANEL-ONE-PAGE-PLAN.md](../plans/PANEL-ONE-PAGE-PLAN.md) on the panel side, E-1 to E-8 on the engine side, integrated by I-1), on contract-P1 payloads captured from the engine (`clients/vscode-companion/test/fixtures/captured/`, the five states of the mockup as `summary.regression.<state>`, plus `summary.regression.interrupted`, NOW-13). Tested in Node, an offline browser, and on the real CLI, and **not run inside a real VS Code** ([manual checklist](../../clients/vscode-companion/MANUAL-TEST.md)). The pixel baselines of the tabbed panel were deleted; the one-page set waits for the owner's review (P-7). The tabbed panel (WP-0, WP-E1 to E3, WP-U1 to U5, WP-I with decisions CI.1 to CI.17 in [V0.1-DECISIONS](../plans/V0.1-DECISIONS.md)) is replaced; its requirements withdrawn by the one page are listed in §18. The default stage stays `v0` and the flag stays off by default. The scope and the staging are in [ADR 0004](../decisions/0004-companion-advanced.md). The engine interfaces are in [CLI-CONTRACT-COMPANION.md](CLI-CONTRACT-COMPANION.md), cited below as **CC §n**, and, for the one page, in [CLI-CONTRACT.md §17](CLI-CONTRACT.md) (contract P1), cited as **P1 §n**. The code base is `clients/vscode-companion/`.

**2026-10-27, ADR 0004 decision 13: one page instead of tabs.** The six tabs are replaced by one page in a fixed order (§4, §6): a sticky header and a one-line progress; then "To handle", "Since your last visit", **Now**, **the path** with its ledger line, and the **tools** as drawers. §3.2 (stages), §4 (information architecture), §6 (the page), §10 (local storage) and §16 (test hooks) are rewritten; LS-1, LS-3 and the theme clause of LS-6 are superseded (§6.0); the content of the former views (EDA cards, evidence, What if?, notions, handoff, session report) is kept in Appendix A, and §A.0 says where each part now lives. The engine names places with anchors (`now`, `todo:<kind>`, `path:<step_id>[/<slot>]`, `tools:<drawer>`, P1 §17.1) instead of tabs. A panel-only theme control (§13.3) replaces "no theme button" (R33), the EN | FR toggle moves into the "more" menu (§13.2), the step-1 data card shows a seeded sample of eight development rows whose target values count as a look (§6.9, P1 §17.3), and What if? is kept with a visible warning (§6.10). The writes stay **W4, W5 and W7** (§7) and the three Marimo launches; the panel decides nothing and records no words. §18 maps every former requirement id to its new place.

The amendment paragraphs that follow are the history of the tabbed panel. Where they name a tab, Appendix A and §18 say where that content now lives.

**Amended by WP-A5 (v0.2a, 2026-10-19; editable-copy extension 2026-10-23).** The panel speaks to the junior, not to the agent: the "verbatim" rule of engine texts becomes the **two-layer copy contract** of §15.1 (INV-16); every stage opens on "Your next move"; the journey marks the step that waits for the junior; decision values are shown in words with the recorded value in a hover and under "Details"; limits carry a severity and are listed once; "Since your last session" is grouped; a load error replaces the content (§3.3); Health appears only when something is wrong; the deliverables offer "Open file" and the three Marimo launches of ADR 0004 "local launch"; the theming, high-contrast, and narrow-width rules of §13 are extended.

**Amended by WP-A7 (v0.2a, 2026-10-19).** The data card (`hypotrail data`) and the quality check; each chart titled by the question it answers, with its confidence intervals with n and the shuffled-outcome null band; the leakage detector's question; the confirmation mode and what counts as an answer, the basis of each confirmation, the agent's concern kept on a confirmation, later corrections; the final-test chip; the success criterion's status.

**Amended by WP-B5 (v0.2b, 2026-10-19).** The final test first in the evidence, with the exposure ledger; development evidence (cross-validation, the variant) apart from final evidence; the diagnostics; a third What if? rule kind (a share) and the gain curve; opening the final test is a chat act, with no control.

**Amended by WP-E1 (v0.3, 2026-10-20): the narrowing.** W1 (confirm), W2 (withdraw), and W3 (propose) are withdrawn at every stage (owner decision R23, integrator decision I2; ADR 0004 decision 8, AGENTS.md). Every decision is read only in the panel, answered in the chat, and "Ask the agent about this" copies a ready question.

**Amended on 2026-10-27 (owner decision R31).** W6, the acknowledgement of an interrupted execution in typed words, is **withdrawn at every stage**: the panel takes no words of the junior. The panel's writes are **W4, W5 and W7**; `lib/cli.js` has no acknowledgement builder and `scripts/check_layout.py` (`companion_acknowledge_errors`) refuses one.

**Amended on 2026-10-27 (owner decision on `docs/plans/mockups/panel-lesson-style-fr.html`, notes R27 to R30): the lesson style** (§6.0).

Requirement identifiers are written like `NOW-3`. Each one is testable, and the plan maps each one to a test. "MUST" and "MUST NOT" are binding. The visual target of the one page is the owner-approved mockup `docs/plans/mockups/panel-synthesis-fr.html` (five study states, widths 320, 420 and 600 px, stages v0 to v3; its numbers are illustrative except the step-1 sample), and, for the figures, the mockups named in Appendix A. Where a mockup and this document differ, this document wins; the mockup's sections "Ce que le moteur doit ajouter" and "États encore à dessiner" are covered by P1 and by §6.11.

## 1. Purpose

The companion is a study panel in VS Code. It helps a junior see where the study stands, decide in their own words, find the evidence behind a number, explore without adopting anything, and hand the study over. It does this **without** becoming a second source of truth. The chat, the HTML report, and the notebooks remain complete without it (ADR 0002, JUNIOR-WORKFLOW).

Every feature is a hypothesis, to be measured against the flag-off workflow (ADR 0004, "What is measured").

## 2. Invariants

These hold in every stage, view, and state. The plan's `test/invariants.test.js` and `check_layout.py` check them.

| Id | Invariant | Source |
|---|---|---|
| INV-1 | The companion reads and writes the study **only** through the `hypotrail` CLI argv recorded in `.hypotrail/agent.json` (`cli.argv`), run with `child_process.execFile` without a shell. It never reads `.hypotrail/*.json` itself; it only watches the folder. It may read deliverable files (`reports/study.html`, `notebooks/*.py`) to open them in the editor | ADR 0002 items 1 and 2, CW.3, CW.4 |
| INV-2 | No state, database, server, socket, loopback HTTP, daemon, polling loop, or language-model call of its own. `vscode.lm` is never used. Local storage is limited to §10 | ADR 0002, CW.2 |
| INV-3 | Every write is one argv from the whitelist of §7. It carries a fresh `--request-id` (UUID v4, one per submission) and the `--expected-revision` the junior saw, except `render`, which has neither, and `export`, which has the revision only (CR.6). One write runs at a time | CLI-CONTRACT §1, CW.7 |
| INV-4 | No delegation from the webview: no `--basis delegated_default`, no `--delegation-scope`, no "use your recommended default" control. A typed delegation is refused by the engine (`delegation_needs_basis`), and the panel says to delegate in the chat | CW.6 |
| INV-5 | Every textarea that becomes `--user-words` starts empty and is never filled, suggested, autocompleted, or restored from another proposal. "Confirm" and "Acknowledge" stay disabled until the field holds a non-blank character. No control confirms in one click. Since WP-E1 no control of the panel confirms at all; since R31 (2026-10-27) no control acknowledges either, and the panel has no textarea that becomes `--user-words` (its one textarea is the question of "Ask the agent about this") | CW.5, PV.2 |
| INV-6 | A proposal, a preview, a draft, a What if? result, a prediction answer, or a learning card is **never** shown as a decision. Every such surface carries its label ("proposal, not a decision yet", "Experiment, not adopted", "Draft only") | AGENTS.md |
| INV-7 | A number is shown only when it comes from (a) a result with `current: true` and `integrity: "ok"`, as a cited segment, or a value of such a result in `evidence`/`status`; (b) a `preview` payload, shown only inside an Experiment surface; or (c) a recorded literal (revision, counts of the engine's own lists). Stale results are listed with "Not cited", without figures | CLI-CONTRACT §4 |
| INV-8 | The engine's refusal is shown with its `code`, its `reason`, the engine message **verbatim**, and a short explanation from `lib/refusals.js` that never suggests words to type. After a refusal the panel refreshes. A write without a JSON answer is reported as "outcome unknown", never as success | CW.8 |
| INV-9 | Study text is set with `textContent`, or as SVG text nodes; it is never parsed as HTML. The webview runs under the v0 CSP (§12) | CW.10 |
| INV-10 | Behind the master flag `hypotrail.companion.enabled` (default `false`). With the flag off, the command and the URI handler show "Companion disabled (feature flag)", and nothing else runs: no file is read and no process is started | CW.2 |
| INV-11 | A trusted workspace is required (`untrustedWorkspaces.supported: false`, checked at run time) | CW.2 |
| INV-12 | In a regression study the companion's own copy never uses the vocabulary of a decision rule: `threshold`, `capacity`, `precision`, `recall`, `positive class`, `policy`, `calling rule`, `decision rule`, `selected`. Texts from the engine are task-aware already. A Playwright test scans the whole DOM text of the page, every block, fold and drawer opened, on the Auto MPG fixtures for these words (case-insensitive, whole word) | CLI-CONTRACT §10, handoff M3 |
| INV-13 | The companion never fits a model, runs `split`, `policy.evaluate`, or `evaluate.regression`, records or resolves a note, edits a notebook, or runs "validate all". From the webview, EDA requests reach only the `eda.*` activities that `evidence.eda_catalog` lists | owner's feature list |
| INV-14 | No figure is computed by the companion. Bar lengths and axis positions are geometry derived from engine values. They are never displayed as numbers that the engine did not emit, except axis tick labels, which are rounded positions of an axis, are marked `aria-hidden`, and carry `data-literal="axis"` | INV-7 |
| INV-15 | Precomputed tutorial outputs (`use-cases/*/results.json`, `project.json`) are never read | AGENTS.md |
| INV-16 | Two-layer copy (§15.1, WP-A5). An engine text whose `audience` is `agent` (CLI-CONTRACT §3.3) is **never** primary content: the panel shows the engine's junior variant (`next_action.junior_message`, `not_yet_defensible.top[].junior_text`, `recap_junior`, `artifacts.items.*.junior_message`) or its own copy keyed by the engine's `kind`, `code`, or id; the engine text stays available under a "Details" disclosure (or a hover). Raw tokens (`capacity:100`, `p_5`, result ids, decision ids, slot names) are not primary content either: they go to a hover (`title`) or "Details". Refusals keep INV-8 (the engine message verbatim, it answers the junior's own action) | v0.2 synthesis §1 item 5 |

| OP-1 | One page (ADR 0004 decision 13). The panel has no tabs: no `role="tablist"`, no `data-tab`, no view that hides another. Every block of §4.2 is in one scrolling page in a fixed order; what a stage does not offer is **absent** from the DOM | ADR 0004 d13 |
| OP-2 | The panel decides nothing about the study's standing. Whether the study is defensible, which items are blocking, a decision's basis, a result's currency, the step a result belongs to, a headline, a criterion's status and its bound are read from the engine (P1 §17.2); when a key is absent the block shows its fallback (HON-9) and computes nothing in its place | AGENTS.md, ADR 0004 d13 |
| OP-3 | Nothing on the page can be mistaken for an answer. The engine's options are plain text, never buttons; the only control next to a question copies a ready question for the chat, and its label shows the exact question it copies | ADR 0004 d8, d12, d13 |

## 3. Activation, flags, stages, modes

### 3.1 Flags

| Setting | Type, default | Effect |
|---|---|---|
| `hypotrail.companion.enabled` | boolean, `false` | Master flag (INV-10). `HYPOTRAIL_COMPANION=1` also turns it on, as in v0. Turned off while a panel is open, it closes the panel and disposes its controller and watcher (decision CR.10) |
| `hypotrail.companion.stage` | enum `"v0"`, `"v1"`, `"v2"`, `"v3"`, default `"v0"` | Which blocks and features of the page are active (§3.2). `HYPOTRAIL_COMPANION_STAGE` overrides it (tests, observation sessions). Each stage includes the earlier ones. A stage higher than the extension knows reads as the highest one it knows. The default moves only through an ADR amendment after a stage's exit criteria are met (ADR 0004) |
| `hypotrail.companion.learningLayer` | boolean, `true` | Stage v3: the inline notions and the My notions drawer (§6.7.3). Off: none of them is rendered and `explain` is not called. It is a preference of the junior, not a feature gate |
| `hypotrail.companion.chatInsert` | boolean, `false` | Stage v2: "Ask the agent" inserts into the chat input through `workbench.action.chat.open` instead of the clipboard (§A.8). Until the API is verified in a real VS Code, the setting is **ignored** and reads as `false` (`lib/flag.js` `CHAT_INSERT_VERIFIED`, decision CR.8) |
| `hypotrail.companion.reviewer` | boolean, `false` | Read-only reviewer mode (§3.3). The command "Hypotrail: open the study panel (reviewer, read-only)" opens a reviewer panel whatever the setting |

**No per-feature sub-flags.** One stage enum keeps the test matrix small, at four stages: per-feature booleans would give 2^12 combinations. It also makes an observation session reproducible from one value. The only booleans are preferences or safety switches whose default must be off until something is verified (`chatInsert`) or until the user chooses it (`reviewer`).

`check_layout.py` is updated to assert the following:

- `enabled` defaults to `false`.
- `stage` defaults to `"v0"`.
- `chatInsert` defaults to `false`.
- `activationEvents` is exactly `["onCommand:hypotrail.companion.open", "onCommand:hypotrail.companion.openReviewer", "onCommand:hypotrail.companion.goToResult", "onUri"]`.
- The source still matches none of the forbidden APIs.

The plan's WP-I owns that change.

### 3.2 Stages (ADR 0004 decision 13)

Each stage includes the earlier ones. An element of a later stage is **absent** from the DOM, not disabled; it carries `data-stage` when it is gated (§16). A test renders every captured payload at each stage and checks that no `data-stage="vN"` element exists below `vN` (PG-12).

| Stage | Adds | Writes and launches | Engine additions it needs |
|---|---|---|---|
| v0 | the sticky header (study, final-test seal, the engine's "not yet defensible" pill, theme, more) and the progress; **To handle** read only; **Now** without figures: the question, the engine's options as plain text, "Copy the question", the limit line, the next line; **the path** with each step's decision value, basis and headline, and the ledger line; the **Deliverables** drawer with Open and the Marimo launches | L1, L2, L3 (no W) | P1 §17.1 (anchors), §17.2.1–§17.2.3 (`panel_contract`, `automation`, `review_queue`, `defensibility`, `ledger`, `headlines`, texts) |
| v1 | Regenerate (W5) in To handle and the Deliverables drawer; **Since your last visit**; "What your answer will change" in Now; the checks of the deliverables; each step's history in the path; the study switch; reviewer mode | W5 | C1, C2, C3, C10 (check `location`) |
| v2 | the data card with its sample (in Now at step 1, then in the Data drawer); the **figures** in Now and in the path's step details (EDA cards, evidence, variants, diagnostics, final test, the criterion per configuration); the **Data** drawer with "Run another chart" (W4); the **What if?** drawer; the ledger's table; deep links to a result | W4 | C4, C5, C8, C9, C10 (anchors), P1 §17.2.4–§17.2.6, §17.3, §17.4 |
| v3 | the inline **notions** (a term expands in place) and the **My notions** drawer; the handoff export (W7) and the session report in the Deliverables drawer | W7 | C6, C7 |

The default stage stays `v0`; it moves only through an ADR amendment after a stage's exit criteria are met (ADR 0004).

### 3.3 Modes and states that apply to the whole page

| State | Trigger | Behaviour |
|---|---|---|
| Flag off | INV-10 | Nothing is rendered; one information message |
| Untrusted | `vscode.workspace.isTrusted === false` | Error message "The Hypotrail companion runs the study CLI, so it needs a trusted workspace."; nothing is rendered or run |
| No study | No folder found (§A.1.6) | A folder dialog (v0). If it is cancelled, nothing happens |
| Moved study | `agent.json.study` differs from the folder | The `study_moved` message of v0 |
| Loading | The first `status` call has not answered | The header shows "Reading the study..."; the blocks are skeletons with `aria-busy="true"`; no control is enabled |
| Load error | The CLI cannot start, prints no JSON, or refuses | The error **replaces the content below the sticky region**: no To handle, Now, path or drawer is rendered. A `role="alert"` card says what happened, gives the next step ("Press Retry. If it fails again, ask the assistant in the chat to run the study status ..."), says "Last read at revision N; the study could not be read now" when a snapshot existed, and keeps the CLI's message and stderr under "Details from the CLI". "Retry" reads again; the content comes back with the next snapshot (PG-11) |
| Stale block | A watch event or a write moved the version while a block or drawer shows older data | Each block's data carries the version it was read at: the revision and the summary's `currency` (decision CR.1, §5). A block whose data is not at the snapshot's version reloads (§11); its older content is marked busy and dimmed; "Updating..." is never shown next to content that is current. Fold state and focus survive the reload (FOLD-2, FOCUS-1) |
| Reviewer | `reviewer` setting or command | The header shows a pill "Reviewer, read-only". **No** element with `data-write` is rendered except the handoff export (v3): no Run another chart, no Regenerate, no Marimo edit launch. The controller refuses W4 and W5 with `kind: "invalid"` and "Read-only reviewer mode." (RV-2). Reads, folds, navigation, Open, Open in Marimo (read), Show in report, and the agent bridge stay |
| Read-only process | `HYPOTRAIL_READ_ONLY=1` in the extension host | Writes are refused by the engine (`read_only`) and shown as refusals. Nothing special is done in the client |
| Busy | One write is running | Every `data-write` control is disabled, and the busy control shows `aria-busy="true"` and "Working..." |
| Contract skew | The digest's `panel_contract` is absent or differs from the panel's `PANEL_CONTRACT` (P1 §17.1.5) | Everything is rendered from what the engine gives; one read-only line (`data-skew`) in the "more" menu and the footer says the chat's "In the panel" lines may not match. Nothing else changes |

## 4. Information architecture

### 4.1 Page order

The page is one column, in this fixed order (OP-1). Only the first region is sticky.

```text
┌ sticky region (header + progress; PG-2)
│   header:   <study folder name> · [theme ◐] · [more ⋯]
│             pills: final-test seal · "not yet defensible" (the engine's list) · [automatic mode] · [Reviewer, read-only]
│   progress: one bar of segments grouped by moment · "Step i/N · <moment>" | "Review k of n" | "Study finished"
├ in the flow
│   To handle (n)            only items outside the current step; absent when empty         (§6.3)
│   Since your last visit    v1; a fold                                                       (§6.4)
│   Now · <step>             what the chat waits for; from v2 the figure that helps answer    (§6.5)
│   [Waiting · <step>]       other steps waiting, below Now, when the engine reopened one     (§6.5.3)
│   The path                 the ledger line, then one line per step, grouped by moment       (§6.6)
│   Tools                    drawers: The data (v2) · What if? (v2) · My notions (v3) · Deliverables (§6.7)
└ footer: "The panel reads the study through the hypotrail command line. Decisions are made in the chat; the chat, the report and the notebook stay complete without it."
```

The popovers (the "not yet defensible" list and the "more" menu) open over the page, next to their button, and never push the content down.

### 4.2 Blocks and anchors

Each block and each place the engine can name carries `data-anchor` with the anchor of P1 §17.1.1 (`now`, `todo:<kind>`, `path`, `path:<step_id>`, `path:<step_id>/<slot>`, `tools:<drawer>`). Every anchor the engine emits for a payload at a stage exists on the page rendered from that payload at that stage (PG-13).

| Block | `data-block` | Anchor(s) | Heading |
|---|---|---|---|
| Header and progress | `header`, `progress` | — | the visually hidden `h1` "Hypotrail study" / "Étude Hypotrail" |
| To handle | `todo` | `todo:<kind>` on each item | `h2` "To handle (n)" |
| Since your last visit | `since` | — | `summary` of a fold |
| Now | `now` | `now` | `h2` "Now · <step title>", or "What the study can claim" at `done` |
| Waiting | `waiting` | — (each card links to its `path:<step_id>` line) | `h2` "Waiting · <step title>" |
| The path | `path` | `path` on the ledger line, `path:<step_id>` on each step line, `path:<step_id>/<slot>` on each figure of a step's detail | `h2` "The path" |
| Tools | `tools` | `tools:<drawer>` on each drawer | `h2` "Tools" |

### 4.3 Navigation targets

A navigation request is `{anchor, kind?, id?}` (§8.2 `navigate`), where `kind` ∈ `result`, `decision`, `proposal`, `step`, `limit`, `execution`, `term`. It comes from a deep link (CC §11), a chip or "See the figure" in the page, and the command "Hypotrail: go to a result...". The controller resolves a result id to `path:<step_id>/<slot>` with the summary's `results` and the plan (the step of a result is the engine's, P1 §17.1.1, read from `results.<slot>.step` (§17.2.5) and `headlines`; a result whose slot the summary does not list opens the path's head). The page opens every fold that contains the target (FOLD-3), scrolls it into view below the sticky region, moves focus to its own heading (decision CI.14), and highlights it for 2 s, without motion when `prefers-reduced-motion` is set (NAV-1).

- NAV-1. A deep link `vscode://hypotrail-local.hypotrail-companion/result/<rid>` of a current `policy.evaluation` (Bank) or `evaluate.regression` (Auto MPG) result opens the step's fold and the figure's fold, focuses the figure's heading, and leaves every other fold as it was. An invalid id shows "This Hypotrail link is not valid." and opens nothing (EV-3).
- NAV-2. "Hypotrail: go to a result..." with a stale result opens its step line, which lists it as stale without figures (INV-7).

## 5. Data sources and caching

| Data key | CLI argv (after `agent.argv`) | Schema | Read when | Used by |
|---|---|---|---|---|
| `summary` | `status --summary --digest --json --study S` (every stage; the one page needs the digest's P1 keys at v0) | `hypotrail.summary/1` (+ CC §1, P1 §17.2) | on open, on visible, on watch, after each write, on Refresh | the header, the progress, To handle, Since your last visit, Now, the path's lines and ledger line, the Deliverables drawer |
| `decisions` | `decisions --json --study S` | `hypotrail.decisions/1` | v1: a step's fold of the path is opened, and the version moved | the step's history, corrections, concerns (§6.6, §A.2) |
| `effects:<pid>` | `preview effects <pid> --json --study S` | `hypotrail.preview_effects/1` | v1: Now holds an open proposal and "What your answer will change" is visible (IntersectionObserver) | "What your answer will change" (§6.5) |
| `evidence` | `evidence --json --study S` | `hypotrail.evidence/1` | v2: Now shows a figure, a step's detail with figures is opened, the ledger's fold is opened, or the Data or What if? drawer is opened, and the version moved | Now's figure, the path's figures, the ledger's table, the Data and What if? drawers |
| `evidence:<rid>` | `evidence --result <rid> --json --study S` | same | v2: a figure's detail ("Where it comes from") is opened | lineage, the result's facts |
| `preview:<rules>` | `preview policy --rule R [--rule R2 ...] [--intervals] --json --study S` | `hypotrail.preview/1` | v2: the What if? slider moves (debounced) | What if? (binary) |
| `draft:<d>:<v>` | `preview proposal <d> --value=<v> --json --study S` | `hypotrail.proposal_draft/1` | v2: an evaluated value in What if? | the read-only draft next to "Ask the agent to propose this" |
| `check` | `check --json --study S` | `hypotrail.check/1` | v1: To handle's checks item or the Deliverables drawer's checks fold is opened, and the version moved | findings |
| `explain` | `explain --json --study S` | `hypotrail.explain/1` | v3: the first notion is expanded, or My notions is opened, and the version moved | notions (§6.7.3, §A.6) |
| `session_report` | `session-report --json --study S` | `hypotrail.session_report/1` | v3: the session report fold of the Deliverables drawer is opened | session report |
| `data` | `data --json --study S` | `hypotrail.data/1` (CLI-CONTRACT §11.1, P1 §17.3, §17.4) | v2: Now shows the data card (step 1), or the Data drawer is opened, and the version moved | the data card, the sample, the special-value rows |
| `scenario` | `status --json --study S` | `hypotrail.status/1` (its `view.scenario_defaults`) | v2: the What if? drawer is opened, and the version moved | the scenario share on the gain curve |
| `trials` | `status --json --study S` (the same process and cache entry as `scenario`, key `view`) | `hypotrail.status/1` (`view.model_selection`, `view.model_families`) | v2: Now or the path shows the variants or families, and the version moved | the variant budget, each variant's question, the family shortlist |

A block that is folded or a drawer that is closed reads nothing (§11). The page never reads `summary` without `--digest`.

**Currency (decision CR.1).** A cached read is valid for one *version* of the study: the summary's revision **and** its `currency`. `currency` is the engine's root field of `status --summary --digest` (a short hexadecimal digest that changes when the dataset is edited, after a render, or when a deliverable is edited or deleted) when the engine sends it. With an engine that does not, the controller computes it (`lib/models/summary.js` `currencyOf`): the first 16 hexadecimal characters of the SHA-256 of the artefacts' statuses, messages and revisions, the not-yet-defensible items, `sources_changed`, and each result slot's id, current flag, integrity, and stale reason. Every read (`view_data`, `effects`, `draft_result`, `preview_policy_result`) carries the currency it was read at, and the webview reloads a block whose data is not at the snapshot's version. `effects:<pid>` and the `evidence:<rid>` detail (its `report_anchor`) follow the same rule.

**Refresh rule (decision CR.1).** The explicit Refresh (in the "more" menu, and Retry of the load-error card) and every write (W4, W5, W7) empty the controller's non-preview cache; after the explicit Refresh the webview also reads again every block and drawer that is open, even at the same version. A watch event keeps the cache: it reads the summary, and a block only when its version moved.

**Session log (integration, owner decision on CLI-CONTRACT §8.6).** Every read above runs with `HYPOTRAIL_SESSION_LOG=0` merged over the host's environment (`lib/cli.js` `READ_ENV`): the panel's own re-reads are not the junior's checks. A write (W4, W5, W7) inherits the environment, so it is logged like the chat's; W7 (`export`) is never logged by the engine.

**Free text in an argv.** It always uses the `--opt=value` form: `--value=`, `--column=`. A value that starts with `-` is therefore never read as an option (CW.7).

## 6. The page

Every block below lists its sources, its content per study state, its stage, its interactions, and its acceptance criteria. Stable test hooks are `data-*` attributes, listed in §16. New copy is in `media/copy/page.js` and its French twin `media/copy-fr/page.js` (parity tested, §13.2); the figures keep the copy of Appendix A.

### 6.0 Lesson style (every stage; owner decision 2026-10-27, notes R27–R30; amended by ADR 0004 decision 13)

The panel reads as a lesson on a board: a slate page, paper cards, graph-paper frames for the charts, headings in chalk (`media/css/lesson.css`, `media/components/lesson.js`). It adds no write and no state of its own.

- LS-1. **Superseded** (ADR 0004 d13): the journey rail, the tabs and the sticky position line are replaced by the progress (PG-8) and the path (§6.6).
- LS-2. **Moved** to Now: "Copy the question" (NOW-3) and the review of an automatic decision as an adoption question (NOW-6).
- LS-3. **Superseded**: "At this step" and the "Next" line of every tab are replaced by Now's next line (NOW-10).
- LS-4. Every chart says why it is there and how to read it: above it, "Why this chart" (`data-guide`: the question, except on an EDA card whose title is the question; the frame of the evidence, HON-1; the rows and the model when known); below it, a guided reading (`data-reading`): the steps in a fold (`details[data-lire]`), the conclusion with the chart's own drawn figures (`data-concl`, a copy of a cited value, never a second cited element) and the trap to avoid (`data-attn`). Kept.
- LS-5. Notions (`data-notion`): the term first (`dfn`), its general definition, then "In this study" with the study's own values (`data-here`). On the one page a notion **expands in place** (NOT-1); "Learn more" folds (`details[data-more]`) keep explaining the header marks, the abbreviations, the exposure ledger and the bases of a decision. Kept, placement amended.
- LS-6. Theme: **superseded in part** by §13.3 (THEME-1 to THEME-5): the panel has a theme control of its own. The mapping stays: `vscode-dark` to the dark board, `vscode-light` to the white board with darkened inks (AA on board and on paper), `vscode-high-contrast` and `vscode-high-contrast-light` keep the editor's own colours and contrast border, with no ruling, glow, shadow or chalk texture; with no class, `prefers-color-scheme` decides.

### 6.1 Header (sticky; v0)

Sources: `summary` (`study`, `final_test`, `defensibility`, `automation`, `not_yet_defensible`, `texts`), the panel's state (`reviewer`, `theme`, `language`).

- PG-1. The page holds, in this order and nothing else between them: the sticky region (header, progress), To handle (when not empty), Since your last visit (v1), Now, Waiting cards (when any), the path, Tools, the footer (§4.1). There is no `role="tablist"` and no `data-tab` element (OP-1).
- PG-2. Only the header and the progress are sticky (`position: sticky`). Their height is at most 110 px at 420 and 600 px wide and at most 150 px at 320 px, in English and in French, on every captured payload (the mockup: 96 and 143 px); the pills wrap rather than overflow. To handle is the first block of the flow, never in the sticky region.
- PG-3. The header's first line holds the study's folder name (its full path in the hover), the theme button (THEME-1) and the "more" button (`aria-haspopup="dialog"`, `aria-expanded`, `aria-controls`, accessible name "More options" / « Plus d'options »).
- PG-4. The header's second line holds the pills, in this order: the final-test seal (PG-5), the defensibility pill (PG-6), the automatic-mode pill when `automation` is not null (PG-7), "Reviewer, read-only" in reviewer mode.
- PG-5. **Seal pill** (`data-pill="seal"`), from `summary.final_test`: "Final test sealed" with a lock and the hover "N rows set aside at creation; no chart or computation reads them." (`status: sealed`); "Final test opened · once" in a solid seal colour with the hover "Opened once, <local date and time of `final_test.opening.time`>; every figure computed after it is marked "after the final test"." (`opened`); "Final test opened · changed after" when `post_final_test` is true, the hover listing `changed_after` in words; "No final test" (`absent`). An automatic opening (the limit `final_test_opened_automatically` is listed) adds "· demonstration" for good. Replaces FR-1 and OV-11's final-test row.
- PG-6. **Defensibility pill** (`data-pill="defensible"`), a button that opens a popover (`role="dialog"`, labelled) listing the items. Its text and tone come only from `summary.defensibility` (P1 §17.2.2; OP-2): `pending` neutral "Defensible at the end · N points"; `warn` coral "Not yet defensible · N points"; `limits` neutral "Defensible · N limits". The popover's heading follows the kind ("What the study will need", "What keeps the study from being defended", "Defensible, with these limits"); its list is `defensibility.items` in order, each the item's `texts.<lang>.limits.<id>` (the engine's junior text), with its severity in words as a tag (blocking, caveat, not final, context; never colour only). Without `defensibility` (an older engine) the pill reads "What you cannot claim yet · N", neutral, N the number of `not_yet_defensible` ids, and lists them (HON-5). The panel never adds, drops, reorders or re-grades an item.
- PG-7. **Automatic-mode pill** (`data-pill="automation"`), from `summary.automation`: "automatic until the final test" (`until_final_test`, active), "full demonstration" (`full_demo`; marked for good, also after it ended), "automatic mode ended" (ended, review not finished); its hover says the mode was chosen at launch and where it stops. Absent when `automation` is null or when it ended and `review_queue.items` is empty and the variant is `until_final_test`.
- PG-11. The load error replaces the content below the sticky region (§3.3); the header keeps the study name and the "more" button (Refresh, Change study).
- PG-12. No element of a later stage is in the DOM (§3.2).
- PG-13. For each captured payload and each stage, every anchor the engine's `companion_env` gives for that payload's `next_action` (`where` and, for the commands of the capture, `shown`) exists as a `data-anchor` on the page rendered at that stage.

**The "more" menu** (`data-more-menu`; a popover of real buttons and radio groups, not `role="menu"`). In this order: "Language" (a radio group English / Français, LANG-1); "Panel theme" (a radio group Auto / Dark / Light, THEME-2); "Refresh · read <age> ago, revision N" (the age is the view's clock, §A.1); "Change study: <name> ▾" (v1, §A.1.6); "How this panel works" (opens a fold at the end of Tools: what the panel is, that decisions are made in the chat only, the writes it can make in words, that every figure is an engine value with its source on hover; R1 of the former §6.1.2a); a faint line with the task and the stage ("Regression · experimental panel, stage v2"); the skew line when it applies (§3.3).

- PG-14. Escape closes a popover and returns focus to its button; a click outside closes it; opening one closes the other; when a popover opens, focus moves into it (FOCUS-3).

### 6.2 Progress (sticky; v0)

Sources: `summary.plan`, `summary.moments`, `summary.current_step`, `summary.next_action`, `summary.review_queue`, `texts.<lang>.moments`.

- PG-8. One bar of segments, one segment per plan step, grouped by moment (`summary.moments`, in plan order; a step no moment lists joins the moment of the step before it); a gap separates the moments. A segment is done, current (the step of `next_action`, the blocker-aware rule of §A.1.2), or to do; the bar is `aria-hidden`. Beside it one label: "Step i/N · <moment title>" (`texts.<lang>.moments`), or "Study finished" at `done`. A visually hidden text says the same in a sentence ("Step 7 of 13, phase Prepare"). No step label is ever shown next to another step label (R32).
- PG-9. During a review of the automatic mode (`next_action.review` is true, or `review_queue.items` is not empty and the plan's steps are done up to the review), the bar has one segment per decision of `review_queue.total`, `done` of them done and the next current, and the label reads "Review k of n · automatic decisions" (`k = review_queue.done + 1`, `n = review_queue.total`). No segment of a decision recorded automatically is ever shown as done before it is adopted.
- PG-10. The footer is the last element of the page, after Tools, with the sentence of §4.1.

### 6.3 To handle (v0, read only; Regenerate from v1)

Sources: `summary.executions`, `summary.artifacts`, `summary.not_yet_defensible` (`sources_changed`, `result_integrity`), `next_action.kind`, `check` (v1).

"To handle" lists **only what lies outside the current step**: what the junior must know before answering, but that the chat does not ask now. A reopened decision, a hold, a review, or a stale figure of the current step is Now's, never To handle's.

- TODO-1. The block (`data-block="todo"`, `h2` "To handle (n)") is absent when it has no item. Its items, in this order, each with `data-anchor="todo:<kind>"`: an interrupted, suspected or late execution (`execution`); changed sources (`sources`); a result whose integrity failed (`integrity`); deliverables that are stale, failed, missing, or not rendered (`deliverables`); the checks of the deliverables with errors (`checks`, v1, after the check read).
- TODO-2. An execution item reads "Interrupted run · <step short name>" and "<activity in words> stopped before it finished; its outcome is unknown. Say so in the chat, in your own words: this panel records nothing.", then "Copy "<question>"" (an agent-bridge copy, `ask_agent` kind `execution`). No words field, no `data-write`, no rerun (HE-1, HE-2). A late item says the result was computed for a state that no longer holds and is stored, not used.
- TODO-3. A deliverables item reads "Report and notebook out of date" (or the one concerned, in words), "They date from revision R; the study is at revision S." (revisions from `artifacts.items.*.revision` and the summary) with each item's `junior_message` in the hover; from v1, outside reviewer mode, a "Regenerate" button (`data-write="render"`, W5); at v0, "Ask for it in the chat." The outcome of W5 follows OV-8 (§A.1.4).
- TODO-4. The checks item (v1) is shown when the check read (made when To handle or the Deliverables drawer's checks fold is opened, cached per version) has errors; each finding as HE-3 (§A.1.5), with "Open" for a deliverable location.
- TODO-5. `sources_changed` and `result_integrity` items show the engine's junior text (`texts.<lang>.limits.<id>`), the engine text under "Details".

### 6.4 Since your last visit (v1)

Source: `summary.digest`, `summary.last_session`. A fold (`data-block="since"`, `data-fold-id="since"`), closed by default, between To handle and Now; its summary reads "Since your last visit" with the count of items ("2 results"). Its content is the former "Since your last session" (§A.1.3) unchanged: items in the panel's words by kind, grouped (needs you, re-evaluated, resolved, other), the first four shown, the engine texts under "Details", the boundary time, "Nothing has changed since then.", and the "Show changes since" select. Absent at v0, and absent when the digest has no item since the boundary.

- SINCE-1. With the Bank fixture after a capacity change, the fold's groups read needs you, re-evaluated (with "Models unchanged, nothing refitted."), resolved (the hold, in the junior's words), other; the engine texts are under Details, verbatim; beyond four items the rest is collapsed (OV-5).
- SINCE-2. The texts hold no revision number outside the select's option labels (OV-6).
- SINCE-3. A "Since your last visit" item whose result was requested from the panel (`results.<slot>.channel` `webview`, P1 §17.2.5) says "requested from this panel".

### 6.5 Now (v0; figures from v2)

Sources: `summary.next_action` and its `pause`, `summary.texts.<lang>` (`question`, `options`, `options_note`, `junior_digest`, `next_action`, `recap`, `plan`, `headlines`, `data_contingent`), `summary.open_proposals`, `summary.decisions`, `summary.criterion_configurations`, `summary.review_queue`; v1 `effects:<pid>`; v2 `evidence`, `data`, `trials`.

Now (`data-block="now"`, `data-anchor="now"`) answers one question: what does the chat wait for, and what helps to answer it. It follows the engine's `next_action` exactly (the blocker-aware current step of §A.1.2): when the engine reopens an earlier step, Now is that step, and the step the junior was on waits below it (§6.5.3).

#### 6.5.1 The common structure

In this order, each part present only when its source is:

1. `h2` "Now · <the step's title>" (`texts.<lang>.plan.<step>`); "Now · First: <the step's title>" when the step is a reopened one (`reconfirm` or a done step with an open proposal); "What the study can claim" at `done`.
2. "The chat waits for" (an eyebrow), only when `texts.<lang>.question` is not null.
3. The question (`h3`), `texts.<lang>.question` verbatim (the engine's junior text).
4. The options (`ul[data-options]`, each `li[data-option]`): the labels of `texts.<lang>.options`, in their order, **plain text** (OP-3), then `texts.<lang>.options_note` when not null.
5. "Copy "<question for the chat>"" (`button[data-copy-question]`): copies the agent-bridge template of §6.12 with a ready question chosen by the panel for the step (`media/copy*/page.js` `askQuestions`, keyed by step id and next-action kind; "What does <the step's term> mean for my study?" when none), never an answer, never the junior's words. Its label shows the exact question; after the copy a polite status "Copied" follows it.
6. The context card (§6.5.2), by state.
7. From v1, "What your answer will change" (`details[data-fold-id="effects"]`, closed by default): for an open proposal, the list of `preview effects` (what a confirmation would invalidate, in words, "Confirming changes nothing already done." when nothing; DC-4, DC-12); for a review or a reopened decision without proposal yet, the panel's fixed sentence for that decision ("If you change it, ... come back to review and the figures are computed again"); for a choice, the effects of the option the chat proposes once it is proposed.
8. The limit line (`p[data-limit]`): the `Limit` line of `texts.<lang>.recap` (the fifth line of `recap_junior`) without its label; at step 1, the panel's "Nothing is measured yet: there is no model and no performance figure."; for a review, the fixed sentence of HON-3.
9. The next line (`p[data-next]`): "Next: <title of the next plan step not done>." followed by the panel's one-sentence "why it matters" for that step (`media/copy*/junior.js`, the term first). Absent at `done`.

- NOW-1. Every captured state renders Now with parts 1 to 9 in that order, each present exactly when its source is; the question and the options are the engine's texts byte for byte in the panel language; the options are not buttons and carry no `data-write` and no click handler.
- NOW-2. The question and the options follow the panel language: switching EN | FR in the "more" menu switches them from `texts.en` to `texts.fr` without a CLI call. A text the engine gave in one language only carries the "(en)"/"(fr)" marker of §13.2.
- NOW-3. "Copy the question" copies exactly the template of §6.12 with the question its label shows; it runs no CLI process (a spy on `lib/cli.js` records none) and writes nothing to the study.
- NOW-12. At 320, 420 and 600 px, in both languages, Now's `h2` and question are inside the first viewport (800 px high) below the sticky region whenever To handle holds at most two items, and no raw result id, proposal id, rule token, or `snake_case` identifier appears in Now's prose (OV-0).

#### 6.5.2 The context card, by state

| State (`next_action`) | Card (`div.card`, eyebrow, `h3`) | Stage |
|---|---|---|
| step 1: `show_data_card` | "To answer, look at" · "The data card": its frame line (HON-1: "Structural reading, plus a preview of eight rows, target included (counted as a look) · no model"); the four facts (rows and period, columns and the target, the final-test rows with the notion "final test", the development rows); the **sample** (§6.9); the structural anomaly sentence from the quality facts the card holds (special values and missing cells by column, "You will decide at the quality check; nothing to do now."); folds "The N columns and their meaning" (the dictionary, §A.3.0), "The N rows with <special value>" (`special_rows`, §6.9), "Why a random draw, and why it is a look" (SAMPLE-4) | v2 (v0, v1: "The data card and the preview appear from stage v2; the chat presents them.") |
| `await_user_words` on a proposal | "Proposed in the chat · not a decision yet" · the step's title: the restatement (quoted, the panel-language text of `texts.<lang>.proposals`, with the chat-wording marker when it is in the other language), "In short: <value in words>" (the recorded value in the hover), "Answer in the chat" (DC-12); when `open_proposals[].data_contingent` is true, the engine's `texts.<lang>.data_contingent.<pid>` in a warning note (HON-8); the final test's opening has no control (OV-10) | v0 |
| a choice (`choice_options`; `pause.kind` `choice`) | "To answer, look at" · the figure that compares the options (the variants' paired differences, §A.4.2; the evaluated rules for a binary decision rule, §A.5.1), its frame line, its guided reading (LS-4), the rule line (HON-2), the criterion line (NOW-8), and folds "the configurations' errors, the rule, your criterion and the reference" (`chartMeans`, cited) and "How to read the paired difference" | v2 (v0, v1: "The comparison figure appears from stage v2. The chat gives you the figures.") |
| a review (`next_action.review` true) | "Automatic decision · to review" · the decision's title: "Chosen by the automatic mode, not by you." (HON-3); "Value: <recorded value in words>"; "To judge:" with `texts.<lang>.junior_digest` | v0 |
| a reopened decision (`reconfirm` not a review; or a done step with an open proposal) | "Why we come back to it" · "Your answer was set aside": the reason in words (`decisions.reconfirm_queue[].reason` at v1; the engine's `texts.<lang>.next_action` at v0) | v0 |
| a hold (`resolve_hold`) | "On hold in your words" · the decision: the junior's words quoted (`summary.holds`), "Nothing on hold is confirmed until you resolve it, in the chat." | v0 |
| a run (`run`) | "Being computed" · the step: "<activity in words> runs in the chat; nothing to answer now." No question, no options | v0 |
| `blocked` | "The step waits for" · the requirement's title in words | v0 |
| `done` | "Conclusion · <basis in words>" · the conclusion in words (`decisions.conclusion.value.text`, else the verdict in words); from v2 a table "Development (used to choose)" / "Final test (read once)" of the chosen model and the reference, cited (HON-1); the criterion judged on the final test (NOW-8); "What the study does not say" (the `caveat` items of `defensibility`, their junior texts); then `h2` "And after" with `next_action.after_study` (HO-3) and "Copy "<question>""; then "Your path: N steps, D decisions in your words, L looks at the target, the final test opened once." (counts of the engine's lists: plan length, decisions whose basis is `endorsed`, `restated` or `explicit`, `ledger.target_looks.total`, `ledger.final_test.openings`) | v0 (table, criterion: v2) |

- NOW-4. A choice (DC-13): the card above, the engine's options as plain text with their note ("From the simplest to the most flexible; the order is not a recommendation." when the engine says so), and no control but "Copy the question". At v0 and v1 the card is replaced by the stage line.
- NOW-5. A reopened decision is Now even when the junior was at a later step; the later step is shown under §6.5.3.
- NOW-6. A review: the heading reads "Now · Review the automatic decisions", the question is the engine's adoption question, the options are `adopt`, `change`, `explain` with the engine's labels and the note "No recommendation."; the card says "not by you"; the limit line is HON-3's; the progress is PG-9's (LS-2, R24).
- NOW-7. Opening the final test is a chat act: when the next action proposes or awaits `final_test`, Now names it, explains that it opens once, and offers no control but "Copy the question" (OV-10, DC-10). The answer rules of the mode (§A.2.5, "What counts as your answer") are a fold of Now (`data-fold-id="answer-rules"`, v1).
- NOW-8. **The criterion line** (`p[data-criterion]`, v2), from `criterion_configurations` (P1 §17.2.4): "Your criterion, <the criterion in words> (<the bound, cited> or better): <met by K of N configurations on their average | met | not met | uncertain>, in development. It is judged for good on the final test." Each figure is cited to its `result_id` and `path`; the status of a configuration whose `status` is `not_assessed` is said only from `point_meets_bound` ("meets the bound on its average; no interval"). At `done` the line says the criterion judged on the final test (`judged_on: final_test`) with the final test's figures only (`criterion_configurations.final_test`, P1 §17.2.4): "Your criterion, <words>, judged on the final test (<the bound from the final test's baseline, cited> or better, from the final test's baseline): <status>; <the model> reaches <its final-test value, cited>." It never shows the development bound next to the final-test status; an engine without `final_test` gets the development line. Without `criterion_configurations` the line falls back to `summary.criterion` for the one model it names (OV-9) and says nothing of the others.
- NOW-9. "What your answer will change" (v1) reads `preview effects` of the open proposal only, re-read when the version moves; it is absent at v0 and in a state without proposal, review or reopened decision.
- NOW-10. The next line names the next plan step not done after the current one by its title and the panel's sentence of why it matters; it is the only "next" on the page.
- NOW-11. At `done` the card holds no control but "Copy the question"; the handoff export stays in the Deliverables drawer (v3).

#### 6.5.3 Waiting cards

When Now is a reopened step and another step waits (a step with an open proposal, a `choice_options` the engine still lists for a later decision, or the step the progress was on before the reopening, i.e. the first later step whose decision is `awaiting_confirmation` or whose results are not current), a card follows Now: `h2` "Waiting · <step title>", and the card titled by that step's figure question. When its figures are not current, the card is hatched, carries the badge "Stale" (`data-stale`), says why in words (the results' `stale_reason`: "computed with the earlier preparation", "the outcome of the last run of <activity> is unknown"), and shows **no figure** (INV-7). Its title links to the step's line in the path.

- NOW-13. With the reopened-preparation capture (`x11` of the mockup, `captured/summary.regression.reopened`: the preparation changed after the models, then to confirm again; the models and variants stale), Now is the preparation; a Waiting card for the first later step not done (the models, whose fits are stale; its figures are the results filed under it and those its comparison shows) is hatched, says "Stale" and why (the engine's `stale_reason.reason` without its reference to the contract's table), and holds no number; To handle holds only what lies outside the step (the stale deliverables when there are any). The mockup also shows the EBM run interrupted in the same state, which the engine never gives: an interrupted execution comes first in its `next_action` (CLI-CONTRACT §3, priority 0 and 1). With the same study once a run was interrupted (`captured/summary.regression.interrupted`, E-8 integration correction, 2026-10-27), Now follows the engine: "A run stopped before it finished", with no question and no options; To handle holds the interrupted run (TODO-2); the path keeps the preparation's "to confirm again" flag.

### 6.6 The path (v0; details from v1, figures from v2)

Sources: `summary.plan`, `summary.moments`, `summary.decisions`, `summary.results` (with `channel`), `summary.headlines` and `texts.<lang>.headlines`, `summary.ledger`, `summary.review_queue`, `summary.holds`; v1 `decisions`; v2 `evidence`, `trials`.

The path (`data-block="path"`, `h2` "The path") is the study so far, one line per step, in plan order.

- PATH-1. **The ledger line** (`p[data-ledger]`, `data-anchor="path"`), first: "Ledger: final test {openings}/{max} opening · {total} looks at the target{, one of them the preview} · {tried} configurations tried{ + the reference}", all from `summary.ledger` (P1 §17.2.2; the clause in braces only when its value says so; "No final test" when `ledger.final_test` is null). From v2 the line is the summary of a fold (`data-fold-id="ledger"`) holding the exposure ledger table (§A.4, EV-2, EV-8), the sample's note (`texts.<lang>.sample_note`), and "Changing the split does not make explored rows unseen."
- PATH-2. **Phases.** One item per moment (`li[data-phase]`, the moment's title from `texts.<lang>.moments`):
  - a moment whose steps are all done and none is flagged is a fold (`details[data-fold-id="ph-<moment>"]`), **closed** by default, its summary "✓ <moment> · N steps done";
  - a moment holding the current step or a **flagged** step (basis `automatic`, a computation run automatically, `needs_reconfirmation` or reopened, delegated, held, stale results) is a fold **open** by default, its summary naming the flags in words ("5 to review", "2 stale");
  - a moment not started is one line, not a fold: "○ <moment> · <step short names joined by " · ">".
  Every mark has a visually hidden word ("done:", "in progress:", "to review:", "to come:"); the mark is never the only signal (OV-4).
- PATH-3. **A step line** (`[data-step="<step_id>"]`, `data-anchor="path:<step_id>"`, `data-step-state` ∈ `done`, `current`, `auto`, `computed`, `again`, `stale`, `held`, `delegated`, `later`): the mark, the step's short name (`media/copy*/overview.js` `journeyLabels`; the title in the hover), and:
  - the current step: "in progress, see Now" and the badge "waiting for you";
  - a done step: its headline (`texts.<lang>.headlines.<step_id>`, P1 §17.2.2), else the decision's value in words (`media/copy*/junior.js` `value`), else nothing;
  - a badge for a flag: "automatic decision" (basis `automatic`, dotted coral), "computed automatically" (no decision, results with `channel: cli`, grey), "to confirm again", "stale", "on hold", "delegated" (with its scope); never a ✓ for an automatic decision or computation (HON-3);
  - a step to come: its short name only.
- PATH-4. Every plan step appears once, in plan order; exactly one step line has `data-step-state="current"` and `aria-current="step"` except at `done` and during a review (where the current line is the decision under review) (OV-3).
- PATH-5. **A step's detail.** Every done or flagged step line is the summary of a fold (`data-fold-id="st-<step_id>"`, closed by default). Its content, each part only when its source is:
  - v0: the decision in words with its basis in words ("in your words", "adopted after review", "delegated to the assistant (standing)", "recorded by the automatic mode, not in your words"), the junior's words quoted when recorded (`decisions.<id>.user_words`), the reason given or "(no reason given)";
  - v0: the headline's provenance as a faint source line naming the results (`headlines.<step>.results`, ids in the hover);
  - v1: the step's history from `decisions` (newest first; restated, endorsed, delegated, automatic chips with their hover; the agent's concern kept; later corrections; proposals not confirmed in a nested fold; "Recorded words, not an authenticated signature."): §A.2.3 and §A.2.5, DH-1, DH-2, DC-8, DC-9;
  - v1: a stale result's reason in words, without figures (HON-4);
  - v2: "See the figure" for each current result of the step: a nested fold (`data-fold-id="fig-<slot>"`, `data-anchor="path:<step_id>/<slot>"`) with the figure of Appendix A for that activity (EDA cards §A.3, the split, model and variant comparisons and diagnostics §A.4, the final test §A.4.1), its frame line (HON-1), its guided reading (LS-4), its source line, and "Where it comes from" (the result's facts and lineage, §A.4, read with `evidence:<rid>`); a chart requested from the panel says "requested from this panel" (`channel: webview`).
- PATH-6. **Automatic mode.** A step whose decision's current basis is `automatic` is flagged "automatic decision"; a step without decision whose results carry `channel: cli` is flagged "computed automatically"; the two are visibly and textually different, and neither has a ✓ (mockup `auto`: 7 decisions, 3 computations).
- PATH-7. **Charts filed under their step.** A W4 chart is filed under the step the engine gives for its result (P1 §17.1.1: the exploration step), never in a separate gallery; the Data drawer links to it.
- PATH-8. The history of a step (v1) shows the restated, endorsed, delegated and automatic chips with their hovers, the kept concern and the correction (Bank fixture), every `user_words` set with `textContent` (a fixture's `<img src=x onerror=alert(1)>` renders literally), and the superseded threshold rule muted with "superseded".
- PATH-9. With the end fixture, every phase is a closed fold "✓ … N steps done", the ledger line reads 1/1 opening, and opening the final test's fold shows the final evidence (v2), cited.

### 6.7 Tools: the drawers

`h2` "Tools", then the drawers, each a fold (`details[data-drawer="<id>"]`, `data-anchor="tools:<id>"`, `data-fold-id="t-<id>"`, closed by default), in this order. A drawer reads its data only when opened (§5).

#### 6.7.1 The data (v2)

The data card (once step 1 is done; at step 1 it is in Now), the quality check, the sample and the special-value rows (§6.9), the dictionary with its meanings toggle (§A.3.0a), and "Run another chart".

- TOOL-1. The drawer opens on the data card, then the quality card, then "Run another chart"; the EDA charts themselves are filed under their steps in the path (PATH-7); the drawer lists them as links ("See it in the path: <question>").
- TOOL-2. "Run another chart" (`data-write="run_eda"`, W4) keeps ED-12: it states the question first, says "one more look" for a chart that reads the outcome, and sends exactly W4; it adds "It is filed under Exploration, in the path, and counts as a look." Before the split it is absent and a line says "Another chart: after the split, on training rows only." The whole-study correlation matrix stays offered (ADR 0004 d9). Absent in reviewer mode.
- TOOL-3. The data card holds no cited figure and no percentage outside the sample's values (DA-6).

#### 6.7.2 What if? (without deciding) (v2)

Present once a current `policy.evaluation` or `evaluate.regression` exists. Its content is §A.5 (the binary policy sandbox, its share rules and gain curve; the regression residual explorer) with its banner (WI-1) and:

- TOOL-4. **The warning** (`p[data-whatif-warning]`), first in the drawer, every state: "Replays another rule or choice on the figures already computed; no model is trained. Careful: a rule or a model changed after seeing the validation figures becomes a result-dependent choice. The study marks it, whether you came through What if? or not; this preview records nothing." (HON-7).
- TOOL-5. Preview values never leave the drawer (WI-5); moving the slider runs only `preview policy` (WI-2); "Ask the agent to propose this" is a copy (WI-3).

#### 6.7.3 My notions (v3)

- NOT-1. A term marked in the panel's copy (`data-term`) is a button (`aria-expanded`, `aria-controls`); pressing it (or Enter or Space) expands, **in place**, the term's definition then "In your study: …" with the study's values (`explain`, `example_status == "shown"`); pressing it again folds it. Its open state is kept (FOLD-1).
- NOT-2. Notions work with the keyboard and by touch; the expanded text has `role="note"`; Escape folds the notion whose button has focus (LE-4).
- NOT-3. The drawer "My notions" lists the notions met so far on the page (the terms of the steps done and of Now), each with its definition and the study's example, in the order met; at `done` it reads as a sheet to keep. Turning `learningLayer` off removes every notion button, expansion, concept card, prediction and the drawer, and no `explain` call is made (LE-3).
- **Concept cards (kept, LE-2).** My notions opens on the concept card of the step that waits (§A.6.1, `data-concept-card="<task>:<step>"`), labelled "a concept, not a decision" (INV-6); after its second sighting it collapses to a one-line link (`data-concept-card-link`). The count and the "Hide concept cards" preference are the extension's `globalState` (§10).
- **Predict before you look (kept, LE-1).** When a prediction of `explain.predictions` belongs to the step Now shows and the junior has not answered it for this study, Now holds it (`data-predict-now="<step>"`) under the figure's heading and before the figure is read: the question, the choices, and "Kept on this computer only. Never written to the study." An answer is a `learn_set` to the extension, never a study write; the reveal follows. At v3 Now reads `explain` for it when the learning layer is on.

#### 6.7.4 Deliverables (v0)

The rows of §A.1.4 (report, generated notebook, editable copy, workbench) with their status chip and junior message, "Open" (the report in the browser), "Open in Marimo (read)" and "Open in Marimo (edit)" (L1–L3; edit absent in reviewer mode), the box "What "Open in Marimo" does"; from v1 "Regenerate the report and notebook" (`data-write="render"`, W5) under the conditions of §A.1.4 and the fold "Checks of the deliverables" (HE-3); at v3 "Export a handoff pack" (`data-write="export"`, W7, §A.6.2) and the fold "Session report (for an observed session)" (§A.6.3).

- TOOL-6. The drawer is present at every stage; Open and the three launches keep OV-7 and the local-launch rules (§A.1.4); Regenerate keeps OV-8; the export keeps HO-1, HO-2; the session report keeps SR-1.

### 6.8 Honesty rules

- HON-1. **Development and final framing.** Every figure has a frame line (`[data-frame]`) naming its evidence class: "Structural reading" (no target), "Training rows" (EDA), "Development evidence · used to choose" (validation or out-of-fold), "Final test · measured once" (the opened final test), or "Sandbox · nothing adopted" (What if?). A table that shows development and final figures side by side labels its columns "Development (used to choose)" and "Final test (read once)". A figure computed after the opening carries "after the final test".
- HON-2. **A rule is not a decision.** The one-standard-error rule (and any engine selection rule) is "a rule of the tool, not your decision: you choose in the chat"; the panel never phrases the rule's pick as the junior's choice or as a recommendation. When the paired interval of two configurations stays within one standard error of zero (`model_selection`), the figure says "These folds do not separate them" and, visibly (not folded), "Not separating them does not prove they are equal."
- HON-3. **Automatic is not the junior's words.** A decision recorded with basis `automatic` reads "chosen by the automatic mode, not by you" wherever its value appears (Now, the path, the history), never "your words", never a ✓; a computation run by the automatic runner reads "computed automatically", distinct from a decision; during a review the limit line reads "The path's figures rest on decisions you have not adopted yet. Adopting them now fixes them after seeing these figures: the study will note it."
- HON-4. **Stale is marked, never cited.** A result that is not current, or whose integrity is not `ok`, is listed with "Stale" (or "Not cited") and its reason in words, without any figure (INV-7); a step whose figures are stale carries the badge "stale" in the path; Now never shows a stale figure as the figure that helps answer.
- HON-5. **The defensibility pill is the engine's.** Its kind, its count and its items come from `summary.defensibility` only (PG-6); the panel computes no severity and no kind; a missing key gives the neutral fallback of PG-6, never a reassuring "defensible".
- HON-6. **The sample is a counted look.** Wherever the sample shows target values, the line of SAMPLE-2 is visible next to it (not folded); the ledger line counts it (PATH-1).
- HON-7. **What if? is not a decision and a change is marked.** The banner and the warning of TOOL-4 are present in every state of the drawer.
- HON-8. **A data-contingent proposal is said.** When the engine marks an open proposal `data_contingent` (P1 §17.2.6; a preparation, a variant, or a rule or model changed after its validation evaluation), Now shows the engine's junior text in a warning note next to the proposal; the panel never adds such a mark by itself.
- HON-9. **Fallbacks compute nothing.** When a P1 key is absent (an older engine), its block degrades to what the engine gives: no headline (the value in words), no per-configuration criterion (OV-9's single model), no automation pill, the neutral defensibility pill, the first-rows card of an older `data` (labelled as such, its target values shown as before). It never derives the missing value from other keys.
- HON-10. **Copy says what it copies.** Every copy button's label shows the question it copies; nothing is copied that the label does not show, and no copy carries the junior's words or a decision value beyond the identifiers of §6.12 (AB-1).

### 6.9 The step-1 sample (v2)

Source: `data` (`rows`, `special_rows`, P1 §17.3, §17.4), `summary.sample`, `summary.ledger`.

- SAMPLE-1. The data card's preview (`table[data-sample]`, in a `data-scroll-ok` region with `tabindex="0"`, `role="region"` and an accessible name) shows `data.rows.items`: eight development rows (fewer for a smaller study), one `tr[data-sample-row="<row_key>"]` each, the row key first, then the target column marked "<target> ◂ to predict", then the other columns in the case's order; its caption reads "Preview · 8 <row unit> drawn at random among the N development rows". The rows are exactly those of the report's data section and the notebook's sample cell for the same study (a test compares the three).
- SAMPLE-2. Under the table, not folded: "A look at the target, counted: these 8 values of <target> are seen now, and the study's ledger records it. The draw is fixed: the panel, the report and the notebook show the same rows; drawing others would be one more look." (`p[data-sample-look]`). When `rows.target_shown` is false (the record does not exist yet, P1 §17.3), the target column is absent and the line reads "The target values of these rows are shown once the study records the look; the chat's next step records it."; when the engine also says `rows.exposure.withheld: split_confirmed` (a study whose split was confirmed before the look was recorded: no look is recorded, the target stays hidden for good, P1 §17.3), it reads "The target values of these rows are not shown: this study's split was confirmed before it recorded a look at them, and showing them now would be a look after the split." (`data-sample-look="withheld"`). A refused write records nothing.
- SAMPLE-3. The special-value rows (`special_rows`) are a fold "The N rows with <special value>" (`data-fold-id="special-rows"`), a table without the target (`tr[data-special-row]`), with "Shown without the target: they describe the anomaly, not what is predicted."; "Showing 50 of N" when `truncated`.
- SAMPLE-4. The fold "Why a random draw, and why it is a look" says that the file's first rows are often not typical (when the case declares an order), that seeing a few target values helps to understand what is predicted but is a look at the target, that these rows later fall in validation folds or the validation rows (the engine's `sample_note`), and that an idea it gives for the preparation should be said in the chat, so the study knows where it came from.
- SAMPLE-5. No sealed final-test row, count or value appears in the sample or the special rows (the engine never gives one; a test checks the row keys against the development keys).

### 6.10 What if? warning

Covered by TOOL-4 and HON-7: the warning is the first element of the What if? drawer in every state (loading, error, empty, populated), next to the experiment banner (WI-1), in both languages; it names no study value and offers no control.

### 6.11 States still to design (from the mockup), as specified here

| State | Where it is specified |
|---|---|
| the decision rule (binary) and its sandbox | Now's choice card with the evaluated rules (§6.5.2), the What if? drawer (§A.5.1, §A.5.4) |
| a holdout validation (no folds, so no one-standard-error rule) | the choice card shows the two models' validation figures and their paired difference (§A.4); HON-2's rule line is absent; the criterion line uses the validation values |
| a confirmation the engine would refuse | "What your answer will change" shows the `blocked` box of DC-12: "If you confirm it in the chat now, the engine will refuse it:" with each engine message |
| reviewer mode | §3.3 Reviewer; only the export is a write |
| a panel that cannot read the study, a dated read, several studies | §3.3 Load error, Stale block; the "more" menu's Change study (§A.1.6) |
| the full demonstration | PG-5 "· demonstration" and PG-7, for good |
| a delegated decision; a hold | PATH-3 badges; Now's hold card |
| a write in progress, failed or done; a deliverable edited by hand; check findings | §3.3 Busy, §7 outcome handling in the drawer or To handle that holds the control; TODO-3, TODO-4 |
| a conclusion that contradicts the criterion; a blocked plan with the reference kept | the `done` card shows the engine's `contradicts_verdict` warning line (OV-9); Now's `blocked` card |
| a step being computed, with no question; a late result | Now's `run` card; TODO-2's late item |
| the English version; high contrast (`forced-colors`) | §13.2, §13.3 |

### 6.12 Agent bridge

The "Copy …" buttons of Now, To handle, the path's details (v1: "Ask the agent about this" on a step), What if? ("Ask the agent to propose this", v2) and notions (v3) use the bridge of §A.8 unchanged: the fixed English template, `vscode.env.clipboard.writeText`, the notice "Copied. Paste it into the chat with your assistant.", `chatInsert` ignored until verified (AB-1, AB-2). On the one page a copy button copies at once, without the modal, and its label shows the question; "Ask the agent about this" in a step's detail keeps the modal with its empty "Your question" field.

## 7. Allowed writes (whitelist)

The one page (ADR 0004 d13) changes where the controls sit, not the whitelist: the writes are exactly **W4, W5 and W7**, plus the three Marimo launches L1–L3 of ADR 0004 decision 7, which are not writes.

`A` is `agent.argv`, `S` is the study directory, `ID` is a fresh UUID v4, and `R` is the revision that the junior's view showed. The controller builds every argv. The webview sends only the identifiers and the typed words; it never sends argv fragments, restatements, or option names.

| W | Stage | Trigger | Exact argv | Pre-checks in the controller (any failure is `kind: "invalid"`, nothing runs) |
|---|---|---|---|---|
| ~~W1~~ | withdrawn (WP-E1) | Confirm in my words | `A decide confirm <pid> --user-words=<words> --channel webview --actor user --request-id ID --expected-revision R --json --study S` | `pid` matches `^p_[0-9]+$` and is in the last snapshot's open proposals; `words` is non-blank and at most 4000 characters; not reviewer; not busy |
| ~~W2~~ | withdrawn (WP-E1) | Withdraw (after a modal) | `A decide withdraw <pid> --request-id ID --expected-revision R --json --study S` | as W1, without words; the modal answered "Withdraw" |
| ~~W3~~ | withdrawn (WP-E1) | Propose this rule or model choice (after a modal) | `A decide propose <d> --value=<v> --restatement=<draft.restatement> --rationale=<draft.rationale> --channel webview --request-id ID --expected-revision <draft.revision> --json --study S` | `d` ∈ {`policy` binary, `model_choice` regression}; `v` is a canonical rule or a fit slot. The controller itself re-runs `preview proposal <d> --value=<v>` **immediately before**, requires `proposable: true` and `draft.revision == R`, and takes the texts from that draft only. The modal: "Create a proposal for "<title>": <v>? It is not a decision. You will confirm it in your own words in Decisions." where `<title>` is the plan step's title of the last summary ("Choose a decision policy", "Choose the model"; the decision id in words when the plan has none; decision CR.9), plus "It replaces the open proposal p_N." when `supersedes_proposal` is set. [Propose]. The draft read just before neither reads nor fills the cache |
| W4 | v2 | "Run another chart" in the Data drawer (TOOL-2) | `A run <activity> --column=<c> --channel=webview --request-id ID --expected-revision R --json --study S`; v0.3 (WP-E2): `A run eda.correlation --channel=webview --request-id ID --expected-revision R --json --study S` (no column) | `activity` ∈ the `eda_catalog.activities[].activity` values with `per_column: true` and `runnable: true` of the evidence read at revision R; `c` is one of that activity's `columns[].name`. Without a column: `activity` is a whole-study chart the panel knows (`eda.correlation` only, `lib/models/eda.js` `WHOLE_STUDY`) and its catalog entry has `per_column: false` and `runnable: true` |
| W5 | v1 | Regenerate, in To handle or the Deliverables drawer | `A render --channel=webview --json --study S` | not reviewer; not busy |
| W6 | — | **withdrawn** (owner decision R31, 2026-10-27; ADR 0004 amendment) | none: the acknowledgement of an interrupted execution is made in the chat, in the junior's words (`run --acknowledge-interruption`, a chat act); the panel copies a ready question for it | — |
| W7 | v3 | Export a handoff pack, in the Deliverables drawer | `A export handoff --out=<chosen folder>/revision-<R> --channel=webview --expected-revision R --json --study S` (CR.6; never without `--expected-revision`: an older engine's refusal of the option is shown as such) | `R` is the last snapshot's revision; the folder comes from the VS Code dialog; it is not inside `S/.hypotrail` |

**Channel (v0.3, WP-J, R35).** Every write of W4, W5 and W7 carries `--channel=webview`: the engine records it on the run (the reservation's parameters) and as a `channel_action` event for a render or an export, and `status --summary --digest` lists them in `digest.channel_actions`, so the agent can say what was done from the panel. It changes no identity, no result and no revision of its own.

**WP-E1 narrowing (ADR 0004 decision 8).** W1, W2, and W3 are withdrawn at every stage: `lib/cli.js` has no builder for them, the protocol has no `confirm`, `withdraw`, or `propose` message, and `scripts/check_layout.py` refuses a client source that invokes `decide confirm`, `decide withdraw`, or `decide propose`. The rows above are kept for the record.

**WP-B5 narrowing of W1 (superseded by WP-E1).** A `confirm` for a proposal whose decision is `final_test` is refused by the controller (`kind: "invalid"`, nothing runs): opening the final test is answered in the chat only (ADR 0006 amendment, AGENTS.md). The webview offers no field for it.

**Not in the whitelist, whatever the stage.**

- `decide confirm`, `decide withdraw`, and `decide propose` of any decision (WP-E1);
- `decide confirm --basis ...` or `--delegation-scope`;
- `decide note`, and `decide note --resolve`;
- `run` of `split`, `fit.*`, `policy.evaluate`, or `evaluate.regression`;
- `run eda.*` without `--column`, except `eda.correlation` (v0.3, WP-E2: structural, no target, never a look); the non-per-column `eda.target_rate`, `eda.target_summary`, `eda.special_values`, `eda.quality` and `eda.single_feature_signal` are run by the agent as part of the plan;
- `run --max-groups`;
- `check --text`;
- `init`.

A unit test enumerates the argv builder module and asserts that exactly the three builders W4, W5 and W7 exist (seven before WP-E1, four before R31).

**Outcome handling (all writes).**

| Result | Panel |
|---|---|
| `ok: true`, exit 0 | Success region: what was recorded (`user_words` verbatim for W1 and W6 before they were withdrawn, the proposal id for W3, the slot and status for W4, the artefact messages for W5, the files for W7), then a refresh |
| `ok: true`, exit 3 | Success with problems: the artefact messages, verbatim |
| `ok: true`, `run.status` `late_not_promoted` | "The result was computed but not used: the study changed while it ran. Nothing in the study changed." |
| `ok: false`, any exit | The refusal (INV-8). Exit 4 adds "An execution has an unknown outcome." |
| no JSON, timeout, start failure | "The outcome is unknown: the refreshed panel shows whether anything was recorded." (v0) |
| replayed | It cannot happen (new id per submission). If it does, it is shown as success with "(replayed, no effect)" |

**Timeouts.** Reads: 30 s. W5 and W7: 120 s. W4: 300 s, because EDA loads the dataset with pandas.

## 8. Webview ↔ extension message protocol (`hypotrail.panel/2`)

- **Envelope.** Every message is a JSON object `{v: 2, type, ...fields}`. The one page keeps version 2: it keeps `learn_set` and `learn_state` (the concept cards and "predict before you look", kept at v3 by the integrator's correction of 2026-10-27, LE-2), changes the fields of `navigate`, and adds `panelContract` to `init`; a message of the tabbed form is dropped like any invalid message.
- **Unknown or invalid messages.** A message with an unknown `type`, an extra field, a wrong type, or `v !== 2` is dropped and counted in `diagnostics.ignored`. It is never answered.
- **Validation.** Both sides validate with one schema table in `lib/protocol.js`. The webview copy is `media/protocol.js`, generated by WP-0's script `lib/protocol.js --emit-webview`. A test asserts that the two are identical.
- **v0.** The v0 messages (implicitly `/1`) are retired. The v0 tests are migrated to `/2`, not deleted.

### 8.1 Webview → extension

| `type` | Fields (all required unless marked `?`) | Stage |
|---|---|---|
| `ready` | — | v0 |
| `refresh` | — | v0 |
| `load` | `view` ∈ `summary`, `decisions`, `eda`, `evidence`, `whatif`, `explain`, `check`, `session_report`, `data` (WP-A7), `scenario` (WP-B5), `trials` (v0.3, WP-K); `resultId?` (64 hex, `evidence` only); `since?` (int ≥ 0, `summary` only). The names are data views, not tabs: a block or drawer asks for the views it shows when it opens (§5). `eda`, `evidence`, and `whatif` share the cached `evidence` read and differ by their model function | v1 |
| `confirm`, `withdraw` | withdrawn by WP-E1: dropped as unknown | — |
| `preview_effects` | `proposalId`, `revision` | v1 |
| `preview_policy` | `rules` (1–4 strings matching `^(threshold:(0(\.\d+)?\|1(\.0+)?)\|capacity:[1-9]\d{0,6})$`), `intervals` (bool), `seq` (int ≥ 0) | v2 |
| `draft` | `decisionId` ∈ `policy`, `model_choice`; `value` (string ≤ 64); `revision` | v2 |
| `propose` | withdrawn by WP-E1: dropped as unknown | — |
| `run_eda` | `activity` (`^eda\.[a-z_]+$`), `column` (string, 1–200 characters), `revision` | v2 |
| `render` | — | v1 |
| `acknowledge` | withdrawn (R31, 2026-10-27): dropped as unknown | — |
| `open_marimo` | `artifact` ∈ `notebook`, `editable`, `workbench` (WP-A5, ADR 0004 "local launch": `marimo run` of the generated notebook, `marimo edit` of the editable copy or workbench, in a VS Code terminal; not a write; in reviewer mode both edit launches are refused with a notice) | v0 |
| `open_artifact` | `artifact` ∈ `report`, `notebook`, `editable`, `workbench`; `resultId?` (the report at `#r-<rid>`, or the generated notebook at the line that names the result; not the editable copy or workbench); `line?` (int ≥ 1, an editor deliverable at a check finding's line; not the report; not with `resultId`) | v0 (+ `resultId` and `line` v1, decision CI.3) |
| `navigate_external` | `kind` ∈ `reveal_export`; `path` (string, must equal the last export's `out`) | v3 |
| `ask_agent` | `about: {kind ∈ result, decision, proposal, step, limit, execution, term; id (string ≤ 100)}`, `question` (string ≤ 2000), `mode` ∈ `copy`, `insert` | v0 (v2 before WP-E1) |
| `export_handoff` | `revision` | v3 |
| `switch_study` | — | v1 |
| `learn_set` | `key` ∈ `seen`, `prediction`, `prefs`, `reset_predictions`; `id` (`^[a-z0-9_.:-]+$`, ≤ 100); `value?` (a choice id for `prediction`, `{hideCards?: bool}` for `prefs`, none otherwise) | v3, learning layer on; stored by the extension in `globalState` (§10), never sent to the CLI (LE-1) |

### 8.2 Extension → webview

| `type` | Fields | Notes |
|---|---|---|
| `init` | `stage`, `reviewer` (bool), `learningLayer` (bool), `chatInsert` (bool), `task` (`binary`\|`regression`\|`null`), `study?` (the study key of §10, 16 hex; never the path; CR.2), `marimo?` (`{kernel, notebook, editable?, workbench}`: the engine environment and the three launch commands with study-relative files, display only; WP-A5), `language?` (`auto`\|`en`\|`fr`, the setting `hypotrail.companion.language`; v0.3, WP-E2), `panelContract` (the panel's `PANEL_CONTRACT`, P1 §17.1.5) | sent once after `ready`, and again when a setting changes. The theme is not sent: it is the webview's own state (THEME-2) |
| `snapshot` | `revision`, `currency?` (CR.1), `model: SummaryModel` | after every summary read |
| `view_data` | `view`, `revision`, `currency?` (the version the model was read at, CR.1), `model` (the model of §9 for that view), `resultId?` | |
| `load_error` | `view` (or `null` for the summary), `message`, `detail` | |
| `busy` | `busy` (bool), `op` (W id or `read`) | |
| `outcome` | `op` (`W4`–`W7`; `W1`–`W3` before WP-E1), `kind` ∈ `ok`, `ok_with_problems`, `not_promoted`, `refused`, `failed`, `invalid`, `cancelled`; `target?` (pid, eid, slot); `revision?`; `refusal?` (`{code, reason, engineMessage, human, details: [string], humanFr?, detailsFr?: [string]}`; the French pair since v0.3, WP-K); `recorded?` (`{userWords?, channel?, decisionId?, proposalId?, slot?, status?, files?: [{path, bytes}], out?, warnings?: [string]}`); `artifacts?` (`[{name, status, message}]`); `message?` | |
| `preview_policy_result` | `seq`, `revision`, `currency?`, `model: PolicyPreviewModel` | dropped by the webview when `seq` is not the latest it sent |
| `effects` | `proposalId`, `revision`, `currency?`, `model: EffectsModel` | |
| `draft_result` | `decisionId`, `value`, `revision`, `currency?`, `model: DraftModel` | |
| `learn_state` | `prefs`, `seen`, `predictions` (this study's answers only) | after `init` at v3 with the learning layer on, and after every `learn_set` |
| `navigate` | `anchor` (a string of the grammar of P1 §17.1.1, at most 200 characters), `kind?` ∈ `result`, `decision`, `proposal`, `step`, `limit`, `execution`, `term`, `id?` (string ≤ 100) | deep link and "go to a result" (§4.3); `{tab, kind, id}` of the tabbed panel is dropped as invalid |
| `notice` | `text`, `politeness` ∈ `polite`, `assertive` | copy confirmation, invalid link, etc. |

**Protocol tests (frozen by WP-0).** For every type: one valid example, one example with an extra field, and one with a wrong type, in both directions. Plus a round-trip test: every model fixture sent as `view_data` passes webview validation.


## 9. Models (extension-side projections)

The models are pure functions in `lib/models/*.js`, from CLI payloads to plain objects. They hold only strings, numbers, booleans, arrays, `null`, and objects. Unknown payload keys are ignored, and a missing key becomes `null` or `[]`. Each model function throws a `ModelError` for a wrong `schema`. The webview renders models and nothing else.

| Model | Function | Input | Keys (top level) |
|---|---|---|---|
| `SummaryModel` | `toSummaryModel(summary)` (`lib/models/summary.js`, extends v0 `toModel`) | `hypotrail.summary/1` | `study`, `revision`, `task` (`null` in v0; from `plan` step ids: `model_choice` ⇒ regression), `recap[5]`, `goal`, `currentStep`, `plan[{id, title, status, pause, basis}]`, `moments[{id, title, steps}]`, `pauses`, `nextAction`, `artifacts[{name, label, path, status, message}]`, `artifactsStatus`, `proposals[{proposalId, decisionId, decisionTitle, value, restatement, revision, origin, holds, resolvedNotes}]`, `holds`, `executions{interrupted, suspected, late, active}`, `notYetDefensible{top, more}`, `alerts[{id, text}]`, `digest{since, sinceTime, gapMinutes, items[{revision, time, kind, text, keptFits, refit}], truncated}`, `waitingCount`, `currency` (CR.1); one page (P1 §17.2): `panelContract`, `automation`, `reviewQueue{items, done, total}`, `defensibility{kind, count, items}`, `ledger`, `sample`, `headlines`, `criterionConfigurations`, `texts{en, fr}`, each `null` when the engine did not send it |
| `DecisionsModel` | `toDecisionsModel(p)` | `hypotrail.decisions/1` | `revision`, `decisions[...]`, `queue[...]`, `history[{decisionId, title, value, userWords, basis, scope, channel, actor, revision, time, current, supersededAt}]`, `unconfirmedProposals[...]` |
| `EffectsModel` | `toEffectsModel(p)` | `hypotrail.preview_effects/1` | `proposalId`, `firstConfirmation` (bool), `kept{fitsAllKept, slots}`, `reconfirm[{id, title}]`, `stale[slots]`, `blocked[{code, reason, message}]`, `regenerated[names]`, `note` |
| `EvidenceModel` | `toEvidenceModel(p)` (`lib/models/evidence.js`) | `hypotrail.evidence/1` | `revision`, `task`, `results[...]`, `ledger[...]`, `lineage`, `impacts`, `sources`, `detail`, `uncertainty` (interval rows of the current evaluation) |
| `EdaModel` | `toEdaModel(p)` (`lib/models/eda.js`) | `hypotrail.evidence/1` | `revision`, `task`, `cards[{slot, activity, column, resultId, current, kind, data}]`, `catalog[{activity, label, perColumn, columns, runnable, missing}]`, `rowsSeen{trainEda, validationEda, validationModels}` |
| `WhatIfModel` | `toWhatIfModel(p)` (`lib/models/whatif.js`) | `hypotrail.evidence/1` | `task`, binary: `n`, `evaluatedRules[{rule, selected, truePositives, precision, recall, status}]`, `initialRule`; regression: `models`, `errors`, `deltas`, `residuals`, `residualsBy`, `splitLimits` |
| `PolicyPreviewModel` | `toPolicyPreviewModel(p)` | `hypotrail.preview/1` | `rules`, `byRule{rule: {models: {fit: {selected, truePositives, precision, recall, volume, tiedAtCut}}, intervals, deltas}}`, `adopted`, `note`, `modelsCurrent` (bool) |
| `DraftModel` | `toDraftModel(p)` | `hypotrail.proposal_draft/1` | `proposable`, `missing`, `restatement`, `rationale`, `evidence`, `supersedesProposal`, `note` |
| `ExplainModel` | `toExplainModel(p)` | `hypotrail.explain/1` | `terms{id: {term, definition, example(segments\|null)}}`, `steps`, `predictions` |
| `CheckModel` | `toCheckModel(p)` | `hypotrail.check/1` | `clean`, `counts`, `findings[{code, severity, where, message, location}]` |
| `SessionReportModel` | `toSessionReportModel(p)` | `hypotrail.session_report/1` | `log{enabled, note}`, `span`, `pauses`, `refusals`, `decisions`, `gaps` |
| `PageModel` (one page) | `toPageModel(summaryModel, stage, reviewer)` (`lib/models/page.js`) | the `SummaryModel` | `header{study, seal, defensibility, automation, reviewer}`, `progress{segments[{step, moment, state}], label, review}`, `todo[{kind, anchor, ...}]`, `since`, `now{kind, step, question, options[{id, label}], optionsNote, card, effects, limit, next, criterion}`, `waiting[{step, stale, reason}]`, `path{ledger, phases[{moment, title, fold, open, steps[{id, state, short, headline, basis, flags, results}]}]}`, `tools{drawers[{id, stage}]}`, `anchors[...]` (every `data-anchor` the page will render). A pure function: the webview renders it and nothing else; every placement rule of §6 is tested on it in Node |

**Segments.** A segment is rendered as a text node or a `<data value data-result-id data-path>` element with a title of "result <rid8>... · <path>". This is the same convention as the report, so a number in the panel can be traced the same way.

**Number formatting.** It follows the `format` given by the engine (`int`, `pct0`–`pct2`, `f1`–`f4`) through one function `media/format.js`. That function is a port of `cite.fmt_number`, with a test that compares its output with Python's for 200 values.


## 10. Local storage

| Store | Keys | May hold | Must not hold |
|---|---|---|---|
| `vscode.setState` (webview, per panel) | `askDraft` (the question of "Ask the agent about this"), `folds` (`{fold id: true \| false}`, the folds and notions the junior opened or closed, at most 300 ids, oldest dropped first; FOLD-1), `study` (the study key of `init`, CR.2), `language` (`en` \| `fr`, the "more" menu's choice; LANG-1), `theme` (`auto` \| `dark` \| `light`; THEME-2) | a question draft, view navigation, per-viewer preferences | anything read back as a decision, a number, a study value, the junior's words |
| `context.globalState` (extension) | `hypotrail.learn.prefs` (`{hideCards}`), `hypotrail.learn.seen` (`{card id: count ≤ 99}`, at most 500 ids), `hypotrail.learn.predictions` (`{study key: {question id: choice id}}`, at most 50 studies) | the learning layer's preferences, the concept cards seen, the answers to "predict before you look" (LE-2) | a decision, a study value, the junior's words |
| `context.workspaceState` | not used | — | — |

- `studyKey` is the first 16 hexadecimal characters of the SHA-256 of the absolute study path, so the path itself is not stored. It is not the engine's sample seed (P1 §17.3), which does not depend on the path.
- `check_layout.py` keeps forbidding `localStorage` and `indexedDB`.
- A unit test asserts that `setState` is called only with these keys, each value passing its schema, and that `globalState.update` is called only with the three `hypotrail.learn.*` keys.
- The question draft is deleted once the question is copied.
- Drafts and folds belong to one study (decision CR.2). `init.study` names it; when it differs from the stored `study` (the study switch reloads the same webview with its state, and a state without a key is treated as another study), `askDraft` and `folds` are dropped before anything is rendered; `language` and `theme` are kept (they are the viewer's, not the study's).
- A state saved by the tabbed panel (`tab`, `recapCollapsed`, `evidenceFilter`, `selectedResult`, `drafts`, `ackDrafts`) loses those keys on load.

## 11. Performance

| Item | Budget and rule |
|---|---|
| CLI calls on open | 1 (`status --summary --digest`) |
| CLI calls on a watch event | 1 summary read, plus the reads of the **open** blocks and drawers whose data is not at the new version (revision and currency, CR.1): `evidence` once if Now shows a figure or any figure fold, the ledger fold, the Data or the What if? drawer is open; `data` once if the data card is shown; `decisions` once if a step's fold is open (v1); `preview effects` for Now's open proposal when "What your answer will change" is visible. Each read runs once per version; a watch event that moves nothing reads only the summary. A closed fold or drawer reads lazily when opened (decision CR.5) |
| Coalescing | v0 coalescing applies to every data key: concurrent requests for one key at one version share one process. A request made while one is running for the same key runs once more after it (v0 `again`) |
| Cache | Per data key and version (`<revision>:<currency>`, CR.1). The entries of another version are dropped when a new summary arrives, except `preview:*` (64 most recent). The explicit Refresh and every write empty every non-preview entry (§5) |
| Debounce | Watch events: 250 ms (v0). Slider: 300 ms. Variable select: no CLI call |
| Concurrency | At most 2 read processes at once (summary plus one block read); `preview policy`: at most 1; writes: 1 and exclusive (reads wait) |
| Payload size | `evidence` with 200 results is expected under 1 MB. `MAX_BUFFER` is 16 MB. A payload over the limit is a `load_error` "The study's evidence is too large to show (more than 16 MB)." |
| Measured, not asserted | The integration test records the wall time of each read command on the synthetic study and writes it to the test output, as ADR 0002 asks. There is no invented threshold. A regression of more than 2x between two recorded runs is a review item for the integrator, not a failure |
| Rendering | A re-render replaces only the blocks whose model changed (`data-block`), keeps every fold's state (FOLD-2), the focus (FOCUS-1) and the scroll position, and renders at most 200 rows in any list; more rows need "Show more" |

## 12. Security

The v0 rules still apply: CSP, nonce, no command URIs, no local resource roots, `retainContextWhenHidden: false`, `textContent` only, and whitelisted messages. These additions apply on top:

- **Charts are inline SVG.** They are built with `document.createElementNS`. Geometry goes through `setAttribute` on SVG geometry attributes (`x`, `y`, `width`, `height`, `d`, `points`), and colour goes through `fill` and `stroke` attributes that take values from a fixed palette in `media/core.js`. A `style` attribute is never used: an inline style attribute is blocked by the nonce-only `style-src`. Dynamic widths of HTML elements are set with `element.style.setProperty`, which goes through CSSOM and is allowed under that CSP; a Playwright test runs with the real CSP and checks that no CSP violation is reported (`securitypolicyviolation` listener). v0.3 (WP-E2): the fluid HTML charts set only custom properties (`--v`, `--x`, `--a`, `--b`, `--n`) through CSSOM (`HT.el(tag, {css: {...}})`); the stylesheet turns them into widths and positions. Such a write leaves a `style` attribute on the element, so the rule tested is: no `style` attribute in the document the extension serves, none created with `setAttribute('style', ...)` (recorded in the browser tests), and every `style` attribute present holds custom properties only (`test_webview_wp_e2.py`, `test_webview_gate.py`). Width classes (`.w-0` ... `.w-100`) were not used.
- **No URI is created from study text.** Links are buttons that post messages. The extension opens only these targets:
  - `file:` URIs of the three deliverables;
  - the study's own files named by `check` locations, resolved and required to stay inside the study folder;
  - the export folder.
- **Location paths.** `location.path` is resolved with `path.resolve(S, path)` and must start with `S + path.sep`. Otherwise "Open" is not offered.
- **Argv.** Built only in `lib/cli.js`. Values from the webview reach an argv only through the W pre-checks of §7, in `--opt=value` form, and are checked against `\0`. There is never a shell.
- **URI handler.** The path is matched with the patterns of CC §11. VS Code hands the handler a decoded query (`vscode.Uri.query`), so the only query a link may carry is `study=<absolute path>`, and the path is the whole rest of the query taken as is: `+`, `&`, `=` and `%` are characters of the path, not separators (`URLSearchParams` would read `+` as a space and cut at `&`). `study` must equal a discovered study's path, or one the junior confirms in the quick pick. Otherwise the handler opens the quick pick. A link never triggers a write.
- **Clipboard.** It is written only by the agent bridge, with the template of §A.8. No other control, and nothing in the webview (`navigator.clipboard`), writes it; the result detail's "Select the id" only selects the text (decision CI.5, `test/invariants.test.js`).


## 13. Accessibility and theme

**Structure.** One `h1`, the panel title, visually hidden. Each block of §4.2 has an `h2` (To handle, Now, Waiting, The path, Tools); cards and figures inside them have `h3`; a fold's `summary` is not a heading. Landmarks are `header` (the sticky region), `main` (the flow), and `footer`. There is no `nav` tablist.

**Keyboard.** Every control is reachable with Tab, in page order. A fold opens and closes with Enter or Space on its `summary`. Escape closes a popover, a modal or the notion whose button has focus, and focus returns to the opener. Modals trap focus. Sliders follow the native `range` keyboard; Page Up and Page Down move by 10 % of the range. Every scrollable region (`data-scroll-ok`) is focusable (`tabindex="0"`), has `role="region"` and an accessible name, and scrolls with the arrow keys.

**Announcements.** One polite live region carries outcomes, "Copied" and "Updated to revision N". Refusals, load errors, and alerts carry `role="alert"`, as in v0. Opening a fold announces nothing beyond the native `details` state.

**Charts.** Every chart has:

- an accessible name ("Outcome rate by job, training rows");
- a "Show values" toggle that renders the same data as a `<table>`;
- small counts that are indicated by text, not by colour or pattern alone;
- both ends of every interval labelled, the negative sign typographic (−), the region "more error" (or "fewer reached") shaded and labelled;
- contrast of at least 3:1 for marks and 4.5:1 for text against the background, in every theme.

**Motion.** Highlight transitions are disabled under `prefers-reduced-motion: reduce`.

### 13.1 Re-render: folds, focus, scroll

- FOLD-1. Every `details` element of the page and every notion button carries a stable `data-fold-id` (`ph-<moment>`, `st-<step_id>`, `fig-<slot>`, `t-<drawer>`, `ledger`, `since`, `effects`, `answer-rules`, `special-rows`, `cols`, `why-sample`, `term-<id>`, and the ids of Appendix A's folds). When the junior opens or closes one, its id and state are kept in memory and in `vscode.setState` `folds` (§10); an id never set keeps its default state of §6.
- FOLD-2. A re-render (a snapshot, a block's data, a language or theme change, a write's outcome) restores every fold to its kept state; a test opens and closes folds in every block, triggers each kind of re-render, and checks that no fold changed state.
- FOLD-3. A navigation (§4.3) opens the folds that contain its target and records them as opened; it closes nothing.
- FOCUS-1. After a re-render, focus returns to the element that had it, matched by `data-focus-id` (every button, `summary`, radio and notion button has one, stable across renders); when that element no longer exists, focus goes to the heading of its block. The scroll position is kept.
- FOCUS-2. Pressing a control that triggers a re-render (copy, a notion, a radio of the "more" menu, Retry, a write) leaves focus on that control.
- FOCUS-3. Opening a popover moves focus to it (`tabindex="-1"` on its container); Escape or a click outside closes it and returns focus to its button (PG-14).
- FOCUS-4. Focus is visible on every control and card in every theme: a 2 px outline, yellow on the dark board, ink blue on paper and in the light board, the system `Highlight` under forced colours; a test reads the computed outline of each focusable element.

### 13.2 Panel language (v0.3, WP-E2, R21; moved into the "more" menu by ADR 0004 d13)

English is the source language; the panel ships a French translation of its own copy (AGENTS.md, owner decision 2026-10-20).

- **Setting.** `hypotrail.companion.language`: `auto` (default; follows the study language, the summary's `language`), `en`, or `fr`. It reaches the webview in `init.language` (§8.2).
- LANG-1. **The control** is a radio group "Language" (English, Français; `data-language-toggle`, `data-language`, `role="radiogroup"`, `aria-checked`) in the "more" menu; there is no language toggle in the header. Choosing switches the page at once (the panel's copy and the engine's `texts` tables), keeps the choice in `vscode.setState` (`language`), sends no message and writes nothing to the study. The choice overrides the setting until the panel's state is cleared.
- LANG-2. Every string of `media/copy/page.js` has a French counterpart of the same kind in `media/copy-fr/page.js`; `test/copy-fr.test.js` covers the new file.
- **Copy, engine texts, markers.** Unchanged from the tabbed panel: `media/copy/*.js` and `media/copy-fr/*.js`; engine junior texts from `texts.en` / `texts.fr` (L3, and P1 §17.2.3 for the question, options, headlines and notes); the "(en)"/"(fr)" marker (`data-en-marker`) on a text left in the other language; refusals carry `human`/`humanFr`; the engine's own refusal message stays verbatim; the text copied for the chat stays English (§A.8).

### 13.3 Theme control (R33; ADR 0004 d13)

- THEME-1. The header holds a theme button (`button[data-theme-control]`) that cycles Auto → Dark → Light → Auto; its icon shows the state (half disc, full disc, ring, `aria-hidden`), its accessible name says it ("Panel theme: follows VS Code (change)" / « Thème du panneau : suit VS Code (changer) »), its hover "Theme of this panel only".
- THEME-2. The "more" menu holds the same choice as a radio group "Panel theme" (Auto, Dark, Light). Both controls set one value, kept in `vscode.setState` `theme` (§10): a per-viewer convenience, not study state, not a write, no message to the extension.
- THEME-3. The body carries `data-theme` = `auto` | `dark` | `light`. `auto` follows the VS Code theme class as LS-6 says; `dark` applies the dark board and `light` the white board, whatever the editor's class.
- THEME-4. **High Contrast overrides.** Under `vscode-high-contrast` or `vscode-high-contrast-light`, or `@media (forced-colors: active)`, the editor's colours and contrast borders apply whatever `theme` holds; the control stays visible, its accessible name adds "High Contrast theme in use: the editor's colours are kept", and the stored value is kept for when High Contrast ends.
- THEME-5. The contrast rules of A11Y-4 hold under each of Auto (Light Modern, Dark Modern), Dark, Light, and High Contrast, on the board and on the paper surfaces.

### 13.4 Narrow widths (320, 420, 600 px)

- NAR-1. At 320, 420 and 600 px, in English and in French, on every captured state and stage: no horizontal scroll of the page; no element's right edge passes the viewport or its card outside a `data-scroll-ok` region; the sticky region obeys PG-2.
- NAR-2. The only regions that may scroll sideways are the sample, the special-value rows, the dictionary and the development-versus-final table, each in a focusable region (§13 Keyboard).
- NAR-3. A chart keeps one SVG unit per CSS pixel and never grows past its container (`max-width: 100%`), so its text, drawn at 11 to 12 px, is never scaled up (the mockup's 300-unit frame was not adopted: the existing chart components keep their frames and their tests); the path's step line wraps its value under its name below 420 px; the pills wrap onto a second line.
- NAR-4. Touch targets are at least 32 × 32 px at every width (fold summaries, notion buttons, copy buttons, the theme and "more" buttons).

### 13.5 Design system, tokens, and the gates

**v0.3 (WP-E2): the design system.** `media/css/tokens.css` and `media/css/core.css` implement the validated system of `docs/design/companion-v0.3-mockups/ds.css`, which supersedes the token tables below (kept for the record; their names stay as aliases):

- **Two token layers.** Layer 1: the host's `--vscode-*` values with the Light Modern / Dark Modern defaults as fallbacks. Layer 2: `--ht-fg` from `editor-foreground`; surfaces derived with `color-mix` (`--ht-surface` 2.5 % of the foreground into the editor background, `--ht-sunken`, `--ht-line`, `--ht-line-strong`, `--ht-faint`); six semantic hues (accent, warn, bad, seal, info, ok) and the chart roles (mark, reference grey, band, grid, axis, the diverging pair) fixed per theme kind on `body.vscode-light`, `body.vscode-dark`, `body.vscode-high-contrast` and `body.vscode-high-contrast-light` (outside VS Code, `prefers-color-scheme`). In High Contrast the hues are bright, the surfaces are the background, and every card, chip and button takes the theme's contrast border; `forced-colors` keeps the system colours.
- **Scale.** Spacing 4–32, type caption 11 (uppercase label), meta 12, body 13, title 15, page 18, stat 24, tabular numbers; radii chips 4, cards 8, pills 999; no shadow except the next move's 3 px accent ring.
- **One card pattern** (eyebrow, title as a question, figure, one sentence, footer with "Why?" and a faint source line), **filled status chips** with a dot, **notes** as tinted blocks.
- **Charts are fluid.** Bars, histograms, interval rows, the confusion 2×2 and the correlation matrix are HTML grids sized by CSSOM custom properties (§12): they follow the width of the panel. SVG is kept for curves (gain, calibration, quantile plot), drawn at the width of their container and redrawn when it changes (ResizeObserver), so one SVG unit is still one CSS pixel and chart text is never scaled up; any SVG is at most as wide as its container. **No chart and no page scrolls sideways at any width**; the only sideways scroll is inside the dictionary and the five example rows of the data card. This replaces the v0.2 rule "a narrow panel scrolls a chart sideways".
- **A11Y-4 (v0.3).** `test_webview_gate.py` (WP-E3; rewritten for the one page) runs the page on the captured payloads, every fold and drawer opened, under Light Modern, Dark Modern, High Contrast, and the panel themes Dark and Light (THEME-5), at 320, 420, 600 and 900 px, in English and in French: no element's right edge passes the viewport or its card (`section`, `article`, `.card`) outside `data-scroll-ok`; every visible text at one of the six type sizes (caption, meta, body, title, page, stat, read from the tokens on `<body>`), chart text at 10–13 px, monospace only for identifiers (three words at most); no raw result id, proposal id, rule token, `key:value` token or `snake_case` identifier in the prose (allowed: the faint source lines, code, the junior's quoted words, file names, and the study's column names, which engine texts quote); nothing underlined, numbers and prose words alike; the style-attribute rule of §12; no CSP violation. Per theme, the text tokens (`--ht-fg`, `--ht-muted`, `--ht-faint`, `--ht-link`, `--ht-accent-ink`, the warn, bad and seal inks) keep 4.5:1 against the page and the card surface (7:1 for the main and muted text in High Contrast), each chip ink 4.5:1 on its tint, and both button texts 4.5:1 on their buttons. Identifiers the panel itself shows (the result slots and the activities of the exposure ledger) are set as code.
- **Pixel baselines (v0.3, WP-E3; one page).** `test/baselines/*.png`: the five states of the synthesis mockup (step 1, the model choice, a reopened step, the automatic review, the end) on the captured studies, at 320, 420 and 600 px, Light Modern, Dark Modern and High Contrast, English and French, first viewport (800 px) plus Now's figure at v2. The 108 images of the tabbed panel are obsolete. **The new baselines are regenerated by the implementation and are not committed until the owner has reviewed them** from the diff images (PANEL-ONE-PAGE-PLAN, P-7). Until then no one-page baseline is committed: the pixel tests compare against a local uncommitted set when one exists and otherwise skip with "one-page baselines awaiting owner review", and the structural gate is the one that must pass. Rendering is pinned (DejaVu Sans and DejaVu Sans Mono, installed fonts only; reduced motion, no animation; a fixed date, locale and time zone; device scale 1). Chromium compares the images itself (two canvases, no image library): a pixel differs when a channel moves by more than 24, and more than 0.1 % of differing pixels fails; the capture, the baseline and a diff image go to `clients/vscode-companion/.local/baseline-diff/`. `--update-baselines` rewrites only the baselines that differ, and every baseline change is reviewed by the owner from those diff images before it is committed (CONTRIBUTING). Without the pinned fonts (Linux, `fc-match`) the pixel tests skip with a warning; the structural gate always runs.

**Theme tokens (v0.2, superseded by the paragraph above).** The tokens are defined in `media/css/tokens.css`. Each one maps a VS Code variable first and falls back to the mockup colour (light) or its dark counterpart:

| Token | VS Code variable | Light fallback | Dark fallback |
|---|---|---|---|
| `--ht-bg` | `--vscode-editor-background` | `#FBFAF7` | `#1E1F21` |
| `--ht-surface` | `--vscode-sideBar-background` | `#FFFFFF` | `#252628` |
| `--ht-border` | `--vscode-panel-border` | `#E3E1DA` | `#3A3C3F` |
| `--ht-fg` | `--vscode-foreground` | `#1C1E21` | `#E6E6E3` |
| `--ht-muted` | `--vscode-descriptionForeground` | `#5B6066` | `#A3A7AD` |
| `--ht-accent` | (fixed brand) | `#0F6E66` | `#4FB3A9` |
| `--ht-done-bg` | (fixed) | `#E3F1EF` | `#1F3A37` |
| `--ht-warn-bg` / `-border` / `-fg` | `--vscode-inputValidation-warningBackground` / `-warningBorder` / `--vscode-foreground` | `#FCEFD9` / `#EBCB97` / `#4A2604` | `#3A2C14` / `#8A6A2E` / `#F2DDB8` |
| `--ht-error-bg` / `-border` / `-fg` | `--vscode-inputValidation-errorBackground` / `-errorBorder` / `--vscode-errorForeground` | `#FBE7E4` / `#E6B3AB` / `#6B1E14` | `#3B1F1B` / `#8A3B30` / `#F4C7BF` |
| `--ht-experiment-bg` / `-fg` | (fixed) | `#EEE8F7` / `#3A2363` | `#2C2340` / `#D9CCF2` |
| `--ht-link` | `--vscode-textLink-foreground` | `#1D5FAF` | `#6FA8E8` |
| `--ht-font` / `--ht-mono` | `--vscode-font-family` / `--vscode-editor-font-family` | `system-ui, sans-serif` / `ui-monospace, monospace` | — |

No remote font is loaded: the mockup's IBM Plex is replaced by the VS Code fonts.

**WP-A5 additions.**

| Token | VS Code variable | Use |
|---|---|---|
| `--ht-st-ok`, `--ht-st-needs`, `--ht-st-sealed`, `--ht-st-error`, `--ht-st-stale` | `--vscode-charts-green`, `-blue`, `-purple`, `-red`, `-yellow` | the one status vocabulary (ok, needs you, sealed, error, stale): a border and a tint, never the text colour |
| `--ht-chart-model`, `--ht-chart-baseline`, `--ht-chart-text` | `--vscode-charts-blue`, `--vscode-charts-lines`, `--vscode-charts-foreground` | the model in the accent, the baseline (or any reference) in grey, chart text |
| `--ht-button-border`, `--ht-button2-border`, `--ht-card-border` | `--vscode-button-border`, then `--vscode-contrastBorder` | every button and card has a visible border in High Contrast |

- A disabled control is not marked by opacity alone: no fill, a dashed border, muted text.
- `@media (forced-colors: active)`: buttons, tags, cards, steps keep a border in system colours; chart marks use `CanvasText` and `GrayText`; the current step and the focused control use `Highlight`.
- Charts follow the width of the panel (v0.3, WP-E2; above): chart text is 11 px and never scaled up, and nothing scrolls sideways. Intervals sit on a drawn axis, with 0 marked and labelled when the chart compares to 0.
- Below 600 px every table becomes a list of cards (each cell labelled by its column), except the regions of NAR-2; the page never scrolls sideways (NAR-1).
- A11Y-3. `test_webview_themes.py` runs the page on the captured payloads under the Light+, Dark+ and High Contrast variable sets (`test/themes.py`) and the panel themes Dark and Light, at 320, 420, 600 and 900 px: chart text ≤ body text + 2 px; primary buttons have a visible border in High Contrast and under forced colours; no sideways scroll; no `agent` text visible anywhere on the page.

- A11Y-1. axe-core is **not** added, because it would be a dependency. Instead, a Playwright test asserts that every interactive element has an accessible name, every `img`-like SVG has `role="img"` and a name, there is no positive `tabindex`, and focus is visible (outline present) for each control.
- A11Y-2. Computed contrast of text tokens against `--ht-bg` is at least 4.5:1 in both fallback themes. This is tested by computing WCAG contrast in the test.

## 14. Task variants and vocabulary

| Element | Binary | Regression |
|---|---|---|
| Third decision | `policy` | `model_choice` |
| What if? drawer | policy sandbox (§A.5.1) | residual explorer (§A.5.2) |
| EDA target card | `eda.target_rate` | `eda.target_summary` |
| EDA by-column | `eda.rate_by` "Outcome rate by value" | `eda.mean_by` "Target mean by value" |
| Interval bars | precision, recall, volume, deltas | MAE, RMSE, deltas |
| Pause 3 label | "business trade-off" | "model choice" |
| Ledger "Rule selection" row | present when recorded | never (purpose not used) |

**Task detection.** The task comes from `evidence.task` and `decisions.task`. `SummaryModel.task` is derived from the plan's step ids until the summary carries `task`. That is an open question: adding `task` to the summary is additive and cheap, and WP-E1 may add it.

**Forbidden vocabulary.** INV-12 applies to the panel's own strings, which live in `media/copy.js`, keyed by task. The Playwright test of INV-12 runs the regex on the rendered DOM of the whole page, every fold and drawer opened, with the Auto MPG fixtures.

## 15. Copy catalogue

All panel-owned strings live in `media/copy/*.js` and `media/copy-fr/*.js` (webview; the one page adds `page.js`) and `lib/refusals.js` (refusal explanations, v0). They are English. They never contain digits, except through placeholders filled from models. They never suggest confirmation words. The strings quoted in this document are normative. New strings follow these rules:

- they are plain sentences, with no exclamation marks;
- they name the engine's terms (proposal, decision, result, revision);
- they say "nothing was recorded" after any refusal or cancelled action.

### 15.1 Two-layer copy (WP-A5)

This replaces the "verbatim" rule for engine texts shown as content (the refusals of INV-8 keep theirs).

1. **Layer 1, primary content**: the panel's own sentences, in `media/copy/*.js` (the junior-facing table is `media/copy/junior.js`), keyed by the engine's stable identifiers: `next_action.kind`, decision ids, `not_yet_defensible` ids, digest kinds, artefact names and statuses, activity and slot names. They are written for the junior: second person, plain business words, the statistical term first and then its use in the case, no command, flag, id, or field name. They follow the rules of §15 (no digit outside placeholders filled from engine values, no decision-rule vocabulary in a regression study).
2. **Engine junior texts** (`audience: junior`, or the `junior_*` variants of CLI-CONTRACT §3.3) may be shown as primary content as they are.
3. **Layer 2, engine text**: an `audience: agent` text is shown only inside a "Details" disclosure or a hover, labelled when it is an instruction to the assistant. Raw identifiers and recorded tokens are layer 2 as well.
4. A text without an audience (an engine before v0.2a) is shown as before.
5. (v0.3, WP-E2) Numbers are cited by `<data>` elements with their provenance in the hover; they are **never underlined**, and no dotted underline marks words in the prose (a glossary term of the learning layer is a hover target with a thin solid border). Result ids, revisions and other provenance appear only in a card's faint source line, in hovers, and under "Details"; never in a sentence. Every caveat of a card goes under its one "Why?" disclosure; a card shows one sentence of finding.


## 16. Stable test hooks

| Attribute | On | Values |
|---|---|---|
| `data-block` | each block of §4.2 | `header`, `progress`, `todo`, `since`, `now`, `waiting`, `path`, `tools` |
| `data-anchor` | each place the engine can name (P1 §17.1.1) | `now`, `todo:<kind>`, `path`, `path:<step_id>`, `path:<step_id>/<slot>`, `tools:<drawer>` |
| `data-stage` | any stage-gated element | `v1`, `v2`, `v3` |
| `data-write` | every control that triggers W4, W5 or W7 | `run_eda`, `render`, `export` |
| `data-fold-id` | every `details` and notion button (FOLD-1) | fold id |
| `data-focus-id` | every focusable control (FOCUS-1) | stable id |
| `data-pill` | the header's pills (PG-4) | `seal`, `defensible`, `automation`, `reviewer` |
| `data-more-menu` | the "more" popover (§6.1) | — |
| `data-theme-control`; `data-theme` on `body` | the theme button (THEME-1); the applied choice (THEME-3) | —; `auto`, `dark`, `light` |
| `data-language-toggle`, `data-language` | the language radio group in the "more" menu (LANG-1) | `en`, `fr` |
| `data-skew` | the contract-skew line (§3.3) | — |
| `data-options`, `data-option` | Now's options, plain text (NOW-1) | option id |
| `data-copy-question` | a copy button of Now, To handle or a step (NOW-3) | step id or kind |
| `data-limit`, `data-next`, `data-criterion` | Now's limit line, next line, criterion line | — |
| `data-stale` | a stale card or step (HON-4) | — |
| `data-phase` | a moment of the path (PATH-2) | moment id |
| `data-step`, `data-step-state` | a step line of the path (PATH-3) | step id; `done`, `current`, `auto`, `computed`, `again`, `stale`, `held`, `delegated`, `later` |
| `data-ledger` | the path's ledger line (PATH-1) | — |
| `data-drawer` | a tool drawer (§6.7) | `data`, `whatif`, `notions`, `deliverables` |
| `data-whatif-warning` | the What if? warning (TOOL-4) | — |
| `data-frame` | a figure's frame line (HON-1) | `structural`, `training`, `development`, `final`, `sandbox` |
| `data-sample`, `data-sample-row`, `data-sample-look` | the step-1 sample (SAMPLE-1, SAMPLE-2) | —; row key; — |
| `data-special-row` | a special-value row (SAMPLE-3) | row key |
| `data-proposal-card`, `data-restatement`, `data-hold` | Now's proposal card and holds | proposal or note id |
| `data-outcome`, `data-code`, `data-reason`, `data-engine-message`, `data-human` | outcome regions | v0 |
| `data-result-id`, `data-path`, `data-value` | cited numbers | engine values |
| `data-experiment` | the What if? banner and preview values | — |
| `data-literal` | client-derived displays | `axis`, `parameter`, `age` |
| `data-term` | notion buttons | glossary id |
| `data-eda-card` | EDA figures (in a step's detail or Now) | slot |
| `data-ledger-row` | rows of the exposure ledger table | `<purpose>:<partition>` |
| `data-en-marker` | the "(en)"/"(fr)" marker of an engine text in the other language | — |
| `data-zero-tile`, `data-log-scale`, `data-numeric-line`, `data-pair`, `data-flag`, `data-collinear`, `data-whole` | the figures of §A.3.0a | as before |
| `data-scroll-ok` | the only regions that may scroll sideways (NAR-2) | — |
| `data-guide`, `data-guide-fact`, `data-reading`, `data-lire`, `data-concl`, `data-attn` | "Why this chart" and the guided reading (LS-4) | as before |
| `data-notion`, `data-here`, `data-notion-fold`, `data-notion-keep`, `data-more` | notions and "Learn more" folds (LS-5) | as before |
| `data-ask-execution` | To handle's copy for an interrupted run (TODO-2) | — |

Removed with the tabs: `data-tab`, `data-tab-lead`, `data-band`, `data-rail`, `data-rail-step`, `data-rail-state`, `data-moment`, `data-remain`, `data-where`, `data-intro`, `data-next-tab`, `data-hero-review` (now `data-step-state="auto"` and NOW-6), `data-ov`.

## 17. Non-goals

The companion does not get:

- an embedded chat, an LLM call, or `vscode.lm`;
- its own computation of a statistic, its own state, or a server;
- model fitting, split, or policy evaluation from the webview;
- notebook editing;
- "validate all";
- delegation;
- notes or holds from the webview: the junior states a condition in the chat, where the agent records it verbatim (P2);
- a test partition, or any access to historical holdouts.

## 18. Former requirement ids: where they now live

"Kept" means the requirement holds unchanged, at the place named; "→ X" means X replaces it; "withdrawn" means the one page drops it (ADR 0004 d13).

| Former id | Now |
|---|---|
| INV-1 to INV-16 | kept (§2); INV-12's scan covers the whole page, OP-1 to OP-3 added (one-page invariants) |
| FR-1 (final-test chip) | → PG-5 |
| LS-1 (journey rail, tabs, position line) | withdrawn → PG-8, PATH-2 |
| LS-2 (next move, Copy the question, review) | → NOW-3, NOW-6 |
| LS-3 ("At this step", "Next" per tab) | withdrawn → NOW-10 |
| LS-4, LS-5 | kept (§6.0); notions expand in place (NOT-1) |
| LS-6 (theme from the VS Code class, no theme button) | mapping kept; "no theme button" → THEME-1 to THEME-5 |
| OV-0 (the first 400 px hold the next move) | → NOW-12 |
| OV-1, OV-2 (Where we are, the recap) | withdrawn: the path's lines and headlines say what is decided; the recap stays in the report and the chat |
| OV-3, OV-4 (study map, marks) | → PATH-4, PATH-2 |
| OV-5, OV-6 (since your last session) | → SINCE-1, SINCE-2 |
| OV-7, OV-8 (deliverables, Regenerate) | kept in the Deliverables drawer (TOOL-6) and To handle (TODO-3) |
| OV-9 (success criterion row) | → NOW-8 (per configuration) and the path's `success_criterion` line |
| OV-10 (opening the final test, no control) | → NOW-7 |
| OV-11 (final test and answers rows) | → PG-5 (final test), NOW-7 (answer rules) |
| HE-1, HE-2 (interrupted execution, read only, no rerun) | → TODO-2 |
| HE-3 (check findings) | → TODO-4, TOOL-6 |
| ST-1, ST-2 (studies) | kept (§A.1.6), the switch in the "more" menu |
| RV-2 (reviewer refusals) | kept (§3.3) |
| DC-1 to DC-3, DC-5 | withdrawn earlier (WP-E1) |
| DC-4, DC-12 (If you confirm; read-only card) | → NOW-9, Now's proposal card (§6.5.2) |
| DC-6 (proposal from this panel) | kept in a step's history (PATH-5) |
| DC-7, DC-10, DC-11 (mode, final_test card, refusals) | → NOW-7; refusals kept (INV-8) |
| DC-8, DC-9 (bases, concerns, values in words) | → PATH-8 |
| DC-13 (a choice the chat asks) | → NOW-4 |
| RQ-1 (reconfirmation queue) | → NOW-5 (the first reopened decision is Now), PATH-3 ("to confirm again") |
| DH-1, DH-2 (history) | → PATH-8 |
| DA-1 (data card first) | → §6.5.2 (step 1), TOOL-1 |
| DA-2 (five rows, target first) | → SAMPLE-1 (eight seeded rows) |
| DA-3 to DA-5 (dictionary, French labels) | kept in the data card (Now at step 1, the Data drawer after) |
| DA-6 | → TOOL-3 |
| ED-1 to ED-11, ED-13 | kept for the EDA figures in the path's details (PATH-5, PATH-7) and the Data drawer |
| ED-12 (Run another chart) | → TOOL-2 |
| EV-1 (Current/Stale filter) | withdrawn: each step lists its results, stale ones without figures (HON-4) |
| EV-2, EV-8 (exposure ledger) | → the ledger fold (PATH-1) |
| EV-3 (deep link) | → NAV-1 |
| EV-4 to EV-6, EV-9 to EV-15 | kept for the figures and "Where it comes from" in the path's details (PATH-5) and Now's choice card |
| EV-7 (final test first) | → PG-5 and the `final_test` step's detail |
| WI-1 to WI-7 | kept in the What if? drawer (§6.7.2), with TOOL-4 |
| LE-1 (no prediction message to the CLI) | kept: "predict before you look" is in Now at its step (§6.7.3); no answer reaches `cli.js` |
| LE-2 (concept cards collapse after two sightings) | kept (integrator's correction, 2026-10-27): the concept cards are in My notions (§6.7.3), the count in `globalState` (§10) |
| LE-3, LE-4 | → NOT-3, NOT-2 |
| HO-1, HO-2 (export) | kept in the Deliverables drawer (TOOL-6) |
| HO-3 (after the study) | → Now's `done` card (§6.5.2), NOW-11 |
| SR-1 (session report) | kept in the Deliverables drawer (TOOL-6) |
| AB-1, AB-2 (agent bridge) | kept (§6.12, §A.8) |
| A11Y-1, A11Y-2 | kept |
| A11Y-3, A11Y-4 | kept, at 320, 420, 600 and 900 px on the page (§13.5) |

## Appendix A. Block and figure specifications carried over from the tabbed panel

The sections below are the former §6.1 to §6.8, renumbered A.1 to A.8. They keep specifying the content of each figure, card and control. **Where they now live** is this table; wherever a carried-over sentence still says "tab", "the Overview", "Decisions", "Evidence", "the EDA tab" or "the Learn tab", read the place given here. A carried-over requirement holds at its new place unless §18 withdraws or replaces it.

### A.0 Placement

| Former place | Content | Now lives in | Stage |
|---|---|---|---|
| §A.1.0 Your next move | the next move, its title, why it matters, its single action | Now (§6.5); the question and options from the engine (P1 §17.2.3) | v0 |
| §A.1.1 Where we are | goal, decided values, success criterion, final test, answers | the path's lines and headlines (§6.6), Now's criterion line (NOW-8), the seal pill (PG-5), Now's answer rules (NOW-7) | v0 (criterion figures v2) |
| §A.1.2 Study map | the plan, its marks, the blocker-aware current step | the progress (PG-8) and the path (PATH-2 to PATH-4); the current-step rule is kept | v0 |
| §A.1.2a How this panel works | — | the "more" menu (§6.1) | v0 |
| §A.1.3 Since your last session | the digest | Since your last visit (§6.4) | v1 |
| §A.1.4 Deliverables | rows, Open, Marimo launches, Regenerate | the Deliverables drawer (§6.7.4); Regenerate also in To handle (TODO-3) | v0 (Regenerate v1) |
| §A.1.5 Health | executions, alerts, checks, what you cannot claim yet | To handle (§6.3); the defensibility pill (PG-6) | v0 (checks v1) |
| §A.1.6 Studies | discovery, switch | the "more" menu | v1 |
| §A.2.1 Pending decision card | restatement, value in words, if you confirm, answer in the chat | Now's proposal card (§6.5.2), NOW-9 | v0 (effects v1) |
| §A.2.2 Reconfirmation queue | decisions to confirm again | Now (NOW-5) and the path's flags (PATH-3) | v0 |
| §A.2.3 Decision history | confirmations, bases, superseded rows | each step's detail in the path (PATH-5, PATH-8) | v1 |
| §A.2.5 Mode, bases, concerns, corrections | — | Now's answer-rules fold (NOW-7), the path's details | v1 |
| §A.3.0 Data card and quality | the card, the dictionary, the quality check | Now at step 1, then the Data drawer (§6.7.1); the five rows become the sample (§6.9) | v2 |
| §A.3.0a, §A.3.1 EDA cards and charts | distributions, rates and means by group, correlation, special values, single-feature signal | the path's details under their step (PATH-5, PATH-7); Now when the step is current | v2 |
| §A.3 Request a chart | W4 | the Data drawer (TOOL-2) | v2 |
| §A.4 Evidence: results, detail, uncertainty, lineage, exposure ledger | — | the path's details ("See the figure", "Where it comes from"); the ledger table in the ledger fold (PATH-1) | v2 |
| §A.4.1 Final test, development and final evidence | — | the seal pill (PG-5), the `final_test` step's detail, Now's `done` card | v0 (figures v2) |
| §A.4.2 Variants and model families | — | Now's choice card at the model choice (§6.5.2); the `model_variant` and `models` steps' details | v2 |
| §A.5 What if? | sandbox, residual explorer, share rules, gain curve | the What if? drawer (§6.7.2) | v2 |
| §A.6.1 Learning layer | glossary hovers, concept cards, predictions | inline notions (the hovers become notions that expand in place, NOT-1); concept cards in My notions; "predict before you look" in Now at its step (§6.7.3) | v3 |
| §A.6.2 Hand off | export, reviewer line, after the study | the Deliverables drawer (TOOL-6); Now's `done` card (HO-3) | v3 (after the study: v0) |
| §A.6.3 Session report | — | the Deliverables drawer | v3 |
| §A.7 Term marking | — | notion buttons (NOT-1) | v3 |
| §A.8 Agent bridge | — | §6.12 | v0 |

### A.1 Overview (former; now Now, To handle, the path, the drawers: §A.0)

Mockup: `Main.dc.html`; WP-A5: `docs/design/companion-v0.2-mockups/overview.html`, `deliverables.html`.

Order (WP-A5). Stage v0: Your next move, the plan (§A.1.2 as one list), Where we are, What you cannot claim yet, Deliverables. Stage v1 and later: Your next move, Needs attention (only when something is wrong), Study map, Since your last session next to What you cannot claim yet, Where we are, Deliverables (with the checks).

#### A.1.0 Your next move (WP-A5, every stage)

The first block of the Overview at every stage, v0 included (`data-ov="hero"`). Keyed by `next_action.kind` (copy in `media/copy/junior.js`):

- an eyebrow "Your next move" and, for a decision, its pause ("Pause 3 · business trade-off");
- a title in the panel's words: "Answer the proposal on <decision>" (`await_user_words`), "Confirm <decision> again" (`reconfirm`), "A run stopped before it finished" (`outcome_unknown`, `acknowledge_interruption`), "Next step: <step title>" (`propose`, `run`, `blocked`), "Every step is done" (`done`);
- one lead sentence of the panel, and for an open proposal its restatement (quoted) and "In short: <value in words>" (the recorded value in the hover);
- "Why it matters": the term first, then its use in the case (per decision id);
- what supports it, in business words, when the evidence read is at hand (stage v2, a cited figure of the current evaluation of that proposal: the share of successes among the cases the rule picks, with its interval, against the baseline; or the average error of the chosen model against the other);
- one action: "See the proposal" (the proposal's card in Decisions; since v0.3, WP-E3, the lead says to answer in the chat, "adopt the decision or say what you change", and asks for the junior's own words only in the training mode, R23), "Open in Decisions" (the decision), "Go to the run" (the execution card, v1); at v0 an execution sends the junior to the chat;
- "Details": the engine's `junior_message` when it differs from the lead, the engine's `message` labelled as the instruction to the assistant when its audience is `agent`, and the recorded value with the proposal id.

- OV-0. On every captured payload, at 900 and 420 px and in Light+, Dark+ and High Contrast, the first 400 px of the Overview hold the next move and no raw result id, proposal id, or rule token (`test_webview_themes.py`).

**WP-B5 (v0.2b).** The pauses of v0.2 are named in words with why they matter (the term first, then its use): the success criterion, the data preparation, the variant to compare, the opening of the final test. An open proposal of these offers "See the proposal", except the opening of the final test: its next move says "Open the final test, in the chat", explains that it opens once (in the junior's own words and with a reason in the training mode only since v0.3, WP-B and WP-E3), and offers **no action** (`data-hero-chat`); before a proposal exists the next step says to say so in the chat when the model and the rule are settled. Under cross-validation the supporting figure says "On the out-of-fold predictions of the development rows".

- OV-10. On the captured Bank study waiting for the opening, the hero names the opening of the final test, holds no button and no `data-write`, and points to the chat; the Decisions card of that proposal holds no words field and no confirmation.

#### A.1.1 Where we are (A)

(Amended by WP-A5.) A `<dl>` with **Goal** (the `Goal` line of `summary.recap_junior`, or of `recap` from an engine without audience keys) and **Decided** (one line per confirmed or to-reconfirm decision in plan order: its name and its value in words, `media/copy/junior.js` `value`, the recorded value in the hover; "to confirm again" or "left to the assistant" as a status tag). The five lines of `recap_junior` follow, byte for byte, under "Details: the engine's recap". The agent recap (`recap`, `recap_audience: agent`) is never rendered. "Next" and "Limit" are not repeated here: the next move (§A.1.0) and the limits (§A.1.5) say them.

- OV-1. The Details hold `summary.recap_junior`, byte for byte; no line of the agent recap that differs from it appears in the Overview.
- OV-2. Without a recap, there is no Details disclosure and no Goal line; Decided still lists the decisions.

(WP-A7.) "Decided" also lists the success criterion and the data preparation. A **Success criterion** row follows, from `summary.criterion` (CLI-CONTRACT §11.4): the criterion in words ("Adopt only if precision beats the baseline by at least 5 points"), a status chip (met, uncertain, not met, not assessed yet) with one sentence of what it means, and, when the engine gives one, its gain with the paired interval, signed, in points (binary, `f1`) or as a share (regression, `pct1`), each figure cited to the evaluation `result_id`; a verdict that contradicts the criterion adds a warning line. The panel computes none of these figures.

- OV-11. (WP-B5) Two more rows: **Final test** (sealed with its rows; opened at a revision, in the junior's words quoted, with the success criterion judged on the final test, cited; changed after the opening, with what changed in words; or absent) and **Answers** (the mode as a chip, what counts as an answer in that mode, guided, training or express, the reason the trade-offs and the opening need, and that the mode changes in the chat only; no control).
- OV-9. With the Bank fixture the row reads "met" and the cited figures +30.5, +21.4, +40.2; each status changes the chip; a regression criterion reads as a share and holds none of the INV-12 words.

#### A.1.2 Study map (A)

**v0.3 (WP-E2): the journey bar replaces the four columns.** One ordered list (`ol.ht-journey`, `data-map`) of every plan step in plan order, at every stage: a segment per step whose tint is its status (done, now, reopened or to confirm again, the sealed final test, to do), the step's short label, and the sub-label below. **WP-K:** the label is the panel's short name of the step (the validated mockup's words: Data, Moment, Variables, Split, Criterion, Explore, Preparation, Models, Variants, Rule, Choice, Final test, Conclusion; in French Données, Moment, Variables, Découpage, Critère, Exploration, Préparation, Modèles, Variantes, Règle, Choix, Test final, Conclusion; `data-step-label`), so no word is broken at 420 px; the plan's full title is in the hover with the moment and in a screen-reader text. A step the panel has no label for shows its title. Each step carries its moment's title (`data-moment`, and in the hover). A line above says "N of M steps done" (`data-steps-done`); when a step is reopened or must be confirmed again, one note says why a step came back (`data-reopened-why`). The marks and their accessible texts are unchanged (OV-4). OV-3 now reads: every step appears once, in plan order; at most one step has `aria-current="step"` (`test_webview_wp_e2.py`). The four-column text below is kept for the record.

Four columns, from `summary.moments` (CC §1.1). Each column holds the plan steps listed in its moment, with their `title` from `summary.plan`.

| Step status | Mark | Style | Sub-label |
|---|---|---|---|
| `done` | ✓ | done tint | for a step whose decision is confirmed: "pause P · your words" when the basis is `explicit`, "pause P · delegated" when it is `delegated_default` |
| `awaiting_confirmation` | ● | accent border, bold | "pause P · waiting for you" |
| `needs_reconfirmation` | ↺ | warning tint | "pause P · confirm again" |
| `ready` | ○ | neutral | "ready" |
| `blocked` | ○ | muted | "after <title of the first unmet requirement>" |

The pause number comes from `summary.pauses`. The sub-labels are the only text the panel adds. The current step carries `aria-current="step"`.

**Blocker-aware (WP-A5).** The current step is the one that waits for the junior: the decision of `next_action` when its kind is `await_user_words` or `reconfirm`, else the first step `awaiting_confirmation` or `needs_reconfirmation`, else the engine's `current_step`. A `done` step whose decision has an open proposal is shown **reopened** (mark ↺, accessible text "reopened, waiting for you", sub-label "pause P · new proposal, waiting for you"), so a reconfirmation is visible on the map. At stage v0 the same steps are one list ("The plan").

- OV-3. The map has 4 columns with the CC §1.1 titles. Every step appears once. The current step has `aria-current="step"`.
- OV-4. The mark is never the only signal: each mark has an accessible text ("done", "waiting for you", "confirm again", "ready", "blocked").

#### A.1.2a How this panel works (v0.3, owner addition, I1)

The last card of the Overview at every stage (`data-ov="guide"`): what the panel is (a reader of the CLI with no state of its own; the chat, report and notebook stay complete without it), that decisions are made in the chat only, the writes it can make (W4, W5 and W7, in words; W6 withdrawn, R31), that every figure is an engine value with its source on hover and its caveats under "Why?", and that the language toggle changes the panel only. From v1 a "What each tab is for" disclosure lists every visible tab with its lead sentence. No extra tab.

#### A.1.3 Since your last session (A)

The items come from `summary.digest.items` (CC §1.4). (Amended by WP-A5.) The engine's digest texts speak of the junior in the third person, so:

- each item is written in the panel's words, keyed by its `kind` (and its decision, activity, slot, or note: a hold quotes the junior's words from `summary.notes`); an item the panel has no words for (`other`) keeps the engine text;
- items are grouped, each with a tag of one vocabulary: **needs you** (a proposal still open, a hold, a failed or interrupted run), **re-evaluated** (a result added or replaced), **resolved** (a confirmation, a withdrawal, a resolved hold, an acknowledgement, a proposal no longer open), **other**; plus one **deliverables** line from the summary's artefacts; needs you first, newest first inside a group;
- the first four items are shown; the rest are under a collapsed "Show all N changes";
- an item with `invalidation.refit == []` and a non-empty `kept_fits` adds the bold sentence "Models unchanged, nothing refitted.";
- the engine texts, verbatim and in order, are under "Details: the engine's record of these changes";
- a header line reads "Since <boundary_time, as a local date and time>"; when `gap_minutes` is null it reads "This session";
- when `truncated` is true, a final line reads "Older changes are not listed. The Decisions tab has the full history.";
- with no items, the section reads "Nothing has changed since then.";
- a `<select>` labelled "Show changes since" offers the boundary revision and "the start of the study" (revision 1); choosing one re-reads `summary` with `--since`.

- OV-5. With the Bank fixture after a capacity change, the groups read needs you, re-evaluated (with "Models unchanged, nothing refitted."), resolved (the hold, in the junior's words), other; the engine texts are under Details, verbatim; beyond four items the rest is collapsed.
- OV-6. The texts hold no revision number. The test asserts no `/revision \d/` in the section's text, outside the select's option labels.

#### A.1.4 Deliverables (F)

(Amended by WP-A5 and the 2026-10-23 editable-copy extension; stage v0 and later.) Titled "Your deliverables". One row per item of `summary.artifacts.items`, in the order `report`, `notebook`, `editable`, `workbench`:

- the label and the file ("Report · study.html"), the study-relative path, and one sentence of what it is;
- a status tag of one vocabulary (current, out of date, failed, missing, edited; "yours" for the editable copy and workbench) and the item's `junior_message` (the engine `message`, which names paths for the agent, in the hover);
- the report: "Open in browser"; the generated notebook: **"Open in Marimo (read)"** (`marimo run`) and "Open file"; the editable copy and workbench: **"Open in Marimo (edit)"** (`marimo edit`) and "Open file". In reviewer mode neither editable notebook has Marimo edit;
- a box "What "Open in Marimo" does": the three commands with study-relative files (`init.marimo`, display only) and the kernel line "Kernel: the engine environment <path>. Stop it with Ctrl+C in that terminal; the panel owns no process."

**Local launch (ADR 0004 amendment).** "Open in Marimo" sends `open_marimo {artifact}` (§8.1). The extension reads `status --json` once (never cached) and takes `view.deliverables.launch.<name>.argv` (CLI-CONTRACT §3, R7) when it has exactly the form `uv run --project <abs dir> marimo <mode> <file>` or `<abs python> -m marimo <mode> <file>`, with the notebook's mode and absolute path; otherwise it builds the same from the study's recorded CLI argv (`.hypotrail/agent.json`: `uv run --project <engine>/framework …`, or `<python> -m …`); otherwise nothing starts and a notice says so. The argv is started with `vscode.window.createTerminal({name, shellPath, shellArgs, cwd: S})`, an argument list, never a shell string and never typed into a terminal; the terminal is named "Hypotrail · marimo <mode> <file>" and is reused (shown again) while it is open for the same file. Nothing is written to the study. `lib/launch.js` holds the three launches; `scripts/check_layout.py` refuses any other terminal.

A "Regenerate the report and notebook" button (`data-write="render"`, v1) is shown when any generated artefact has status `stale` or `failed`, or the manifest is `not_rendered` (§7, W5). The button is absent in reviewer mode. "Checks of the deliverables" (§A.1.5) is a collapsed `<details>` at the end of this section (v1).

- OV-7. Each row shows its junior message (the engine message in the hover); "Open in Marimo (read)" and "(edit)" send `open_marimo` for the notebook and the workbench; the extension starts exactly `marimo run` / `marimo edit` in a named terminal with an argument list and reuses it (`extension.test.js`, `launch.test.js`). "Regenerate" is shown only under the conditions above.
- OV-8. After "Regenerate", the outcome lists each artefact's message from `render.artifacts`. Exit 3 is shown as "Regenerated with problems", not as a failure of the command.

#### A.1.5 Health (F)

(Amended by WP-A5.) **Needs attention** (the former Health section) is rendered only when something is wrong: an interrupted, suspected, or late execution, or an alert (`sources_changed`, `result_integrity`). It shows nothing otherwise. The checks of the deliverables move to the Deliverables section. "Not yet defensible" becomes its own section, **What you cannot claim yet**: every `top` item and every `more` id **once**, each with a severity tag of one vocabulary (blocking, caveat, not final, context; `media/copy/junior.js` `SEVERITY`), blocking first; the text is the item's junior variant, or the panel's words for its id (the `more` ids have no text in the summary); the engine texts that differ are under "Details: the engine's wording". The execution card keeps the engine's `reason` under "Details". The rest of this section describes the parts as before.

- **Executions.**
  - Each `summary.executions.interrupted` and `suspected_interrupted` item is one card: "<activity>: the outcome is unknown. Nothing will be restarted."
  - (Amended 2026-10-27, R31.) The card is read only: no words field, no write. It reads: "Acknowledging this interruption is done in the chat, in your own words: say there that you know this run was interrupted and that its outcome is unknown. 'ok' alone is not enough. This panel records nothing.", with "Learn more: Why words, and not an "ok" button?".
  - The card offers no rerun. A line reads: "Ask in the chat, to acknowledge it or to run it again.", and one button, "Copy the question", copies a ready question for the chat (`ask_agent`, kind `execution`; the agent bridge of §A.8, not a write).
  - `late` items are listed as "<activity>: a result was computed for a state that no longer holds; it is stored, not used."
- **Check findings.** A collapsed `<details>` titled "Checks of the deliverables".
  - Expanding it runs `check` (cached per revision). Each finding is shown with its `severity`, `code`, `message` verbatim, and `where`.
  - When `location.path` is a deliverable, an "Open" button opens it: an editor at `location.line` when it is set, or the browser at `#location.anchor` for the report.
  - The header shows `counts`, and "clean" or "N errors".
- **Not yet defensible.** `summary.not_yet_defensible.top` texts verbatim, and "More: <ids>" for `more`, in the warning colours of the mockup.

- HE-1. (Amended 2026-10-27, R31.) The panel takes no acknowledgement: an `acknowledge` message is dropped as unknown and runs nothing, the card has no words field and no `data-write`, and its one control copies a ready question for the chat. The acknowledgement is made in the chat, where the engine refuses a bare "ok" (`ambiguous_confirmation`, `bare_acknowledgement`).
- HE-2. An execution card never has a "Restart" or "Run" button.
- HE-3. Check findings of the Bank fixture with an injected stale citation show it with a working "Open": a cited number edited in the HTML is a `value_mismatch` error on `reports/study.html` after the junior's Refresh (the checks are read again at the same revision, CR.1); `stale_number` is the code of a draft text or the conclusion. With the engine's currency, the edit and a deleted report also move `currency` without the Refresh, and a deleted report is not current (`test_he3_real_cli.py`, real CLI).

#### A.1.6 Studies (K)

The extension discovers studies with `.hypotrail/agent.json` in:

- each workspace folder;
- each of its direct subfolders;
- the subfolders of those (depth ≤ 2).

It skips `node_modules`, `.git`, `.venv`, and dot-folders, and stops after visiting 500 folders, listing the studies it found in sorted order. No study is ever read beyond its `agent.json`, which is validated as in v0.

The header switcher is a button "Study: <folder name> ▾" that opens a VS Code quick pick: one entry per study, labelled with its folder name and described by its path, plus "Pick another folder...". Choosing another study disposes the current controller and watcher and opens the new one in the same panel. Only one study is open at a time.

- ST-1. Two studies in one workspace give a quick pick of both. Switching runs `status` on the new `--study` and disposes the old watcher.
- ST-2. A study more than two levels deep is not listed; "Pick another folder..." still reaches it.

### A.2 Decisions (former; now Now and the path: §A.0)

Mockup: `Decision.dc.html`.

#### A.2.1 Pending decision card (B)

There is one card per `summary.open_proposals` item, oldest first. Since WP-E1 the card is **read only** (ADR 0004 decision 8): the "Answer", "study changed while typing", and "Buttons" items below are replaced by "Answer in the chat" and "Ask the agent about this", and the proposal id, the revision, and the origin go under Details. Each card holds:

- **Head.** A pill "Pause P · <pause label>", where the pause labels are 1 "framing", 2 "evaluation design", and 3 "business trade-off" (binary) or "model choice" (regression). Then the plan step title as `h2`, and on the right "proposal by the agent · not a decision yet", or "proposal from this panel · not a decision yet" when `origin.channel == "webview"` (CC §9). Below, "Proposal p_N, made at revision R".
- **Restatement.** In a blockquote, verbatim. Then (WP-A5) "In short: <the value in words>" (`media/copy/junior.js` `value`: "Select the top 100 by score", "Stratified random split, 30% of the rows for validation", "Adopt the linear model"), the recorded value in the hover and, with the proposal id, under "Details"; availability is shown as status groups. The head reads "Proposed at revision R" with the proposal id in the hover; evidence chips name the result in words ("See the decision-rule evaluation →") with the activity and the result id in the hover; slot names in "If you confirm" are in words; the preview's `note` is under "Details". The history shows each value in words (the recorded value or the availability groups in the hover) under the columns Decision, Your words, How, When.
- **Evidence** (v2). Chips for each evidence link:
  - for a policy or model choice, the current `policy.evaluation` or `evaluate.regression` result (`<activity> · <rid8>…`), opening Evidence;
  - for a policy, the paired difference of the proposed rule with its interval, as a cited value from `evidence`;
  - "try other rules →", or "explore the errors →" in regression, opening What if?.
  - For the other decisions: the `split` result for split, and the `eda.*` results for availability when they exist. Chips are absent when no current result applies.
- **Holds.** Each open note of the decision: "On hold in your words: "<words>"", with the v0 sentence. Each resolved note: "Your condition, resolved: "<words>" → "<resolution words>"".
- **If you confirm** (v1, from `effects:<pid>`). Three boxes:
  - "Kept": the `kept_slots`, grouped (fits: "both models and their predictions, nothing refitted" when every fit is kept; else the slot names);
  - "To confirm again": `reconfirm_required` titles, or "nothing";
  - "Regenerated": "report and notebook".

  The first confirmation reads "Nothing recorded so far is invalidated." `stale_slots` is listed under "Becomes stale" when it is not empty. The section has a caption, `note` verbatim, in muted text. When `blocked` is not empty, a `role="status"` box reads "The engine will refuse a confirmation now:" followed by each blocked `code` (`reason`) and `message` verbatim. "Confirm in my words" is then disabled, with that box as its `aria-describedby`. The effects are re-read whenever the version moves (revision or currency, CR.1), only for visible cards.
- **Answer (withdrawn by WP-E1).** Was: a label "Your answer to this proposal, in your own words", an empty textarea, and the hint "Say what you accept and why it fits your situation. "ok" or "yes" alone is not enough. Nothing is filled in for you. What you type is recorded verbatim, with channel "webview"."
- **The study changed while typing (decision CR.3; withdrawn with W1 by WP-E1).** The draft kept the revision at which the junior started typing (§10). When the snapshot's revision is above it, a `role="status"` box under the textarea reads "The study changed while you were typing (revision A to B). Read the proposal again before you answer. A confirmation now names revision A, so the engine refuses it." with a button "I read the proposal again at revision B". "Confirm" sends the revision the draft names, so a confirmation typed before a change is refused by the engine (`stale_revision`, the v0 display and a refresh, DC-3). Typing more does not hide the box; it survives a reload of the webview; only the button (which moves the draft to revision B) or clearing the words removes it.
- **Answer in the chat (WP-E1).** A note "Answer in the chat" with "Confirm, change, or withdraw this proposal in the chat with your assistant. This panel records no decision." (`data-answer-in-chat`). The `final_test` card keeps its own note (DC-10).
- **Buttons.** "Ask the agent about this" only (H, from v0 since WP-E1): one press copies the fixed template of §A.8 with the question "Can you explain this proposal and what confirming it would change in my study?" (`data-ask-direct`), no modal; it never writes the study.
- **Details (WP-E1, R22).** "Proposal p_N, made at revision R", the origin ("Proposed by the agent; not a decision yet.", or from this panel for a proposal recorded before v0.3), and the recorded value.
- **If you confirm, in words (WP-E1, R22).** The three boxes become one list of what a confirmation invalidates ("To confirm again", "Becomes stale", "To compute again"), or the line "Confirming changes nothing already done." when nothing is invalidated; "Kept", "Regenerated", the first-confirmation sentence, and the engine's `note` are under Details. A `blocked` box reads "If you confirm it in the chat now, the engine will refuse it:" with each engine message (the code and reason in the hover).
- **Outcome region.** The refusal or success of the last write on this card (v0 rendering, INV-8).

The decisions: binary `prediction_time`, `feature_availability`, `split`, `policy`, `conclusion`; regression with `model_choice` in place of `policy`.

- DC-1. (Withdrawn by WP-E1: the card has no textarea.) The textarea is empty on first render, after a refresh, and after a successful confirmation. The words of one card never appear in another, nor in another study (decision CR.2).
- DC-2. (Withdrawn by WP-E1.) "Confirm" is disabled with blank words, while busy, or when `effects.blocked` is not empty.
- DC-3. (Withdrawn by WP-E1: there is no W1; a `confirm` message is dropped and no `decide` process runs.) The confirm argv is exactly W1. A stale revision gives the v0 stale display and a refresh.
- DC-4. "If you confirm" for the Bank fixture shows "both models and their predictions, nothing refitted" for a capacity change, and "the conclusion" under "To confirm again".
- DC-5. (Withdrawn by WP-E1.) Text from the preview is never placed in the textarea.
- DC-12. (WP-E1) The card holds no `textarea`, no `data-write` control, and no Confirm or Withdraw; it shows the restatement block, "Answer in the chat", and "Ask the agent about this" at every stage; the proposal id and revision are under Details only. When the preview invalidates nothing, the card reads "Confirming changes nothing already done." and the kept list is under Details.
- DC-6. A webview-originated proposal shows "proposal from this panel".

#### A.2.2 Reconfirmation queue (B)

The queue comes from `decisions.reconfirm_queue`. It is rendered above the history when it is not empty, and titled "Needs your words again". Each item holds:

- the step title;
- `reason`, verbatim;
- "Previously: "<previous.user_words>" (<basis> · <channel>)";
- "Open the new proposal" when `open_proposal` is set;
- otherwise "No new proposal yet. Ask the agent to propose it again.", with "Ask the agent" (v2). For `policy` or `model_choice`, there is also "Choose in What if?" (v2).

- RQ-1. Every `reconfirm_required` decision is listed once, with its previous words verbatim.

#### A.2.3 Decision history (B)

The history is a table with one row per `decisions.history` item, **newest first** (WP-E1, R25: the most recent confirmation sits next to the cards). Its columns are Decision, Your words, How; the revision and the local time are in the hover of the decision cell (WP-E1), not in a column. Before WP-E1 it was grouped by decision in plan order, with these columns:

- **Decision**: the title, and the value in `<code>`;
- **Words**: `user_words` verbatim in quotes;
- **Basis and channel**: "explicit · chat", "delegated (standing) · chat", or "explicit · webview";
- **When**: the revision, and the time in local format.

Rows with `current: false` are muted and add "superseded at revision N".

Below the confirmations, the withdrawn and superseded proposals of `decisions.proposals` are listed under a collapsed `<details>` titled "Proposals that were not confirmed", with their restatement, status, and `closed_reason`.

A note under the table reads "Recorded words, not an authenticated signature." (`report.yaml`'s `not_authenticated`).

- DH-1. Bank fixture: the split row shows the delegated basis in the warning tone. The superseded threshold policy row is muted with "superseded".
- DH-2. Every `user_words` is rendered with `textContent`. A fixture whose words contain `<img src=x onerror=alert(1)>` renders that text literally.

#### A.2.4 Copy (Decisions)

| Situation | Text |
|---|---|
| No open proposal | "Nothing is waiting for your answer. The assistant proposes decisions in the chat." |
| Answer note (WP-E1) | "Answer in the chat" + "Confirm, change, or withdraw this proposal in the chat with your assistant. This panel records no decision." |
| Nothing invalidated (WP-E1) | "Confirming changes nothing already done." |
| Withdraw modal, Confirm success | withdrawn with W1 and W2 (WP-E1) |
| Delegation attempted | the refusal, plus the explanation "Your reply hands the choice to the assistant. A delegation is recorded in the chat, not in this panel." (v0) |

#### A.2.5 Mode, bases, concerns, corrections (WP-A7)

- **Mode.** At stage v1 and later the tab opens on "What counts as your answer": the study's mode (`summary.mode`, ADR 0005) as a chip and, for `guided`, what counts as an answer (since v0.3, WP-B: a reply that adopts the open proposal, or a short yes to the closed question "Do you adopt this decision?"; not a question or a condition), that a reason is optional, also for the calling rule (the model choice in a regression study) and the conclusion, and recorded as "no reason given" when absent, and that a point the agent raises may be kept. The mode changes in the chat only (`mode set`, not a write of the panel): there is no control.
- **Reason hint** (withdrawn with the textarea by WP-E1; the mode section keeps the rule). A card of `policy`, `model_choice`, or `conclusion` said before the textarea that the decision is a trade-off and needs a reason; it suggests no words. The `reason_required` (training mode only since v0.3), `delegation_not_allowed`, `conditional_reply`, and `question_reply` refusals keep INV-8 with the explanations of `lib/refusals.js`.
- **No reason given (v0.3, WP-B, R27).** The history shows "(no reason given)" next to the current confirmation of a trade-off whose `reason_given` is false, and the channel `choice` as "chosen as an option in the chat" (R16: the adoption option of an interactive choice in the chat; the panel offers no such choice and records no decision).
- **Bases.** The history's "How" column is a chip of the basis (`restated`, `endorsed`, `delegated` with its scope; `your words` for an `explicit` record made before ADR 0005), its meaning in the hover, then the channel in words ("in the chat", "in this panel").
- **Concerns and corrections.** The current confirmation's `agent_concern` is shown under the words: "Point raised by the agent before you confirmed, kept by you: “…”"; each correction note (`kind: correction`) of that decision follows: "Your later correction, in your words: “…”".
- **Values in words.** The success criterion and the data preparation read in the words of `media/copy/junior.js`.

- DC-7. The mode section names the guided mode and the reason rule, task-aware, and holds no control (the card's reason hint went with the textarea, WP-E1).
- DC-8. The Bank fixture's history shows restated, endorsed and delegated chips with hovers, the kept concern, and the correction.
- DC-9. On the captured Bank decisions the success criterion and the data preparation are in words, with no raw JSON value.
- DC-10. (WP-B5) A proposal of `final_test` is shown with its restatement and value in words, and the note "Answer this one in the chat": no words field, no "Confirm in my words". Since WP-E1 no card has these, and a `confirm` message is dropped for every proposal. The mode section lists what counts as an answer in each mode (guided, training, express).
- DC-11. (WP-B5) The refusals of v0.2b are explained in words (`lib/refusals.js`): `paraphrase_required` (with the concepts not said yet, never words to type), `words_contradict_value`, and `final_test_already_opened` (with the revision of the opening).
- DC-13. (Owner session 2026-10-26, R16, D20) When the summary's `next_action` is a `propose` with `choice_options` (a choice the chat asks before any proposal: the conclusion, the model choice), from v1 the waiting section shows first a read-only card (`data-choice-card`): "<the decision>: the assistant asks you to choose in the chat", the options' labels as the engine gives them (the value in the hover), "Answer in the chat" with "Choose in the chat with your assistant: it then proposes your choice, and you adopt it there. This panel records no choice.", and "Ask the agent about this" (copy only, `about: {kind: decision}`). No field, no write control, no other button; "Nothing is waiting for your answer" is not shown. At v0 there is no card; "Your next move" reads "Choose <the decision>, in the chat" with the same "records no choice" lead, and from v1 a button "See the options" leads to the card. The Decisions badge still counts open proposals only.

### A.3 EDA (former; now the Data drawer and the path: §A.0)

Mockup: `EDA.dc.html`; WP-A7: `docs/design/companion-v0.2-mockups/eda.html`.

#### A.3.0 Data card and quality (WP-A7)

The tab ("Data & EDA") opens on the data card, from the `data` read (§5; CLI-CONTRACT §11.1: development rows only, no exposure, no target rate):

- three facts: what one row describes (the case's observation unit and its status), the development rows and columns, and the target with its description and labels ("how often it occurs is shown below, on the training rows, after the split");
- the final test's junior line (`final_test.line`) with a sealed chip;
- the five fixed development rows, the target column first; a column the availability decision leaves out (`not_available`, `uncertain_excluded`) is marked ✗ with a legend (not colour only);
- the dictionary, grouped in the case's order: column, type (with unit, and the number of values of a non-numeric column), meaning (the description and each special value with its meaning and rows), "Known at the prediction moment?" (the junior's decision in words, else the case's statement and its status), missing cells, examples;
- "Show French labels" when the case has `labels.fr` (`description_fr`): the descriptions switch to French, marked `lang="fr"`; the button says "Show English labels" to switch back; it is view memory only. (v0.3, WP-E2: replaced by the "Meanings EN | FR" toggle of §A.3.0a, which follows the panel language.)

The `eda.quality` result (development rows, the target not read) follows the data card, titled by its question: missing cells and co-missing patterns, repeated rows, rare categories, and the ranges of numeric columns against a declared range, each figure cited.

- DA-1. The tab asks for `data` and shows the data card first, then the quality card, then the exploration banner and charts.
- DA-2. The five rows have the target first and mark each excluded column with ✗ and a legend.
- DA-3. The dictionary's groups and variables follow the engine's order, with each variable's missing count and special values.
- DA-4. "Show French labels" swaps every description that has a French label, marked `lang="fr"`, and back.
- DA-5. Without French labels there is no toggle.
- DA-6. The data card holds no cited figure and no percentage.

#### A.3.0a The card pattern and the charts (v0.3, WP-E2)

Every EDA card follows the design system's pattern: an eyebrow (KIND · ROWS), the engine's question as the one visible title (the chart's name stays its accessible name only, R17), the column name and its meaning from the data card under the title (`data-column-meaning`), the chart, one sentence of finding, and a footer with one "Why?" disclosure (the term first, then every caveat: the non-causal sentence, the hollow-point and band legends, the engine's note and warnings) and a faint source line `Source · <activity> · <rid6>` that opens the result in Evidence (`data-chip`). Result ids never appear in the prose.

- **Distribution (R17).** A numeric column draws an HTML histogram with a y axis (the largest count, half of it, 0) and the bins' lower edges on the x axis (at most six labelled). When the engine marks the column skewed (`numeric.skewed`, CLI-CONTRACT §11.2), the exact zeros are a tile apart ("Exactly zero", their share and count, cited to `numeric.zeros`) and the positive values are drawn on the engine's log bins (`numeric.log_bins`), with "log scale" under the axis and the reason under "Why?". A stat row names the median, the IQR, the mean and the maximum (and the missing cells). Missing cells and special values are their own grey bars. A grouped column keeps its bars of counts and shares.
- **Rate or mean by group.** One row per group: a point at the group's value, its confidence interval with caps, the shuffled-outcome band behind it, the overall value as a dashed rule, and `n` next to the label; a small group is a hollow point and says "small". The finding is the null-band sentence.
- **Correlation matrix (R28).** From `eda.correlation` (development rows, predictors only, never a target look): the lower triangle in the engine's clustered order, positive (or unsigned) associations in the accent, negative ones in orange, the tint the strength, flagged pairs (|value| ≥ the engine's level) outlined (`data-flag`) and listed with their measure; above eight columns the numbers move to the hover and the values table. The finding names the count of flagged pairs; "Why?" defines collinearity and the three measures.
- **Run another chart.** Besides the per-column charts, the card offers the whole-study charts of the catalog (`eda.correlation`, W4 without a column, §7), saying that it reads no outcome.
- **No sideways scroll.** Every chart is an HTML grid (fluid); the dictionary and the five example rows are the only containers that may scroll sideways, inside their card (`data-scroll-ok`). The five rows are behind a "Five example rows" disclosure.
- **Dictionary meanings (R12 merged into R21).** The Meaning column follows the panel language when the case has `labels.fr`; a "Meanings EN | FR" segmented toggle (`data-french-toggle`, `data-meanings`) switches that column only, view memory only, with a one-line hint.

#### A.3.1 Exploration amendments (WP-A7)

- Each card's title is the engine's question (`values.question`); the chart's name and the result chip follow.
- The banner adds the sealed final-test rows ("never read here") and the ledger of looks at the outcome (`summary.eda_looks.target_looks`): each chart that reads the outcome counts once.
- Confidence intervals: the target rate and target mean say theirs; a by-column chart and the special values draw each group's interval as a line across its bar, and its values say "rate [low–high] of n".
- Null band: each group's shuffled-outcome band is drawn behind its bar (grey); one sentence says whether the observed spread is above every one of the 19 shuffles, with the engine's figures.
- Single-feature signal: one bar per feature (the flagged ones in the accent, the others grey, an excluded feature marked "(left out)", the level as a rule); for each flagged feature a "Leakage detector" box states its score, asks whether its value is really known at the prediction moment, and says the junior's availability decision for it in words. It never keeps or drops a feature.
- "Run another chart" (W4) offers the per-column training-row charts only and states the question of the chosen chart before it runs; a chart that reads the outcome says it is one more look.

- ED-7. Every card is titled by its question.
- ED-8. A by-column chart draws intervals and the band, and states the band in words with cited figures; the target card states its interval.
- ED-9. The leakage detector asks the question with the cited score and the availability decision (Bank: `duration`, already excluded).
- ED-10. The quality card says it reads development rows without the target, with cited counts.
- ED-11. The banner's look count and sealed rows equal the summary's.
- ED-12. "Run another chart" states the question first, says "one more look" for an outcome chart, and sends exactly W4.
- ED-13. The Auto MPG Data & EDA tab holds none of the INV-12 words, French labels shown.

**Sources.** `evidence` (results whose `activity` is an `eda.*` activity and whose `promoted` is true; `eda_catalog`; `exposure.ledger`).

**Banner.** It reads: "**Training rows only.** Every chart is a registered result, computed by the engine." On the right: "rows seen in EDA · train <a> · validation <b>".

- `a` is the `rows` of the ledger row (`train_eda`, `train`).
- `b` is the sum of the `rows` of every ledger row with partition `validation` and purpose `train_eda`. It is always 0 by engine construction; it is shown so the junior sees it.
- A second muted line: "Validation rows seen for model evaluation and selection: <rows of (validation_model_evaluation, validation) ∪ selection>", from `exposure.summary.validation_rows_used_for_selection` and the ledger.

**Gallery.** One card per promoted EDA result, in this order:

1. the target (`eda.target_rate` or `eda.target_summary`);
2. `eda.special_values`;
3. the `eda.rate_by:*` or `eda.mean_by:*` results, by column name;
4. the `eda.distribution:*` results, by column name.

Each card's header shows its title, `<activity> · <rid8>…` (a chip that opens Evidence), and "Stale · not cited" with no figures when `current` is false. The card bodies are:

| Activity | Chart | Text |
|---|---|---|
| `eda.target_rate` | Two-segment stacked bar (positive/negative) with counts and rates | Term first: "**Class imbalance**: one value of the target is much rarer." when the rate is below 0.2 or above 0.8. Otherwise "**Base rate**: how often the outcome occurs in the training rows." Then the `explain` example of `base_rate` when the learning layer is on |
| `eda.target_summary` | Box-and-whisker (min, q25, median, q75, max) on a value axis | "**Target distribution**", then the glossary definition |
| `eda.special_values` | One row per special value: column, value, meaning, rows, share. For each `co_occurrence` item with `same_rows: true`: "<a.column> = <a.value> and <b.column> = <b.value> are the same <n_both> rows". Binary: bars of `rate` by special value vs. the other rows | `note` verbatim |
| `eda.rate_by:<c>` | Horizontal bars of `rate` per group, in engine order (by group size), scale from 0 to the max rate rounded up to the next 5 %, with a vertical rule at `overall_rate`. A group with `small_count` gets a hatched bar (SVG pattern) and the text badge "small" | "Hatched bar: fewer than <min_group_rows> rows; the rate can move a lot with a few rows." Then the fixed non-causal caption (below), then `warnings` verbatim |
| `eda.mean_by:<c>` | The same with `mean` (target unit) and a rule at `overall_mean` | The same captions with "mean" |
| `eda.distribution:<c>` | `numeric`: histogram from `numeric.bins`; `discrete` and `categorical`: bars of `groups` (hatched `small_count`, "(other values)" last) | "Median <median> · middle half <q25>–<q75> · range <min>–<max> · <n> rows." (numeric); special values and missing as one muted line; `note` verbatim |

**Non-causal caption.** It is fixed English, chosen by task:

- Binary: "This describes who had the outcome in the training sample. It does not say that <column> causes it, nor how future cases will go."
- Regression: "This describes the target in the training sample. It does not say that <column> causes it, nor how future cases will go."

**Request a chart.**

- **Fields.** Two selects:
  - "Variable" lists `eda_catalog` columns of the runnable per-column activities, deduplicated by name and labelled with their role. A feature that the recorded availability decision marks `not_available` adds "not available at prediction time" to its label ("duration (feature, not available at prediction time)"), and, when chosen, a muted line: "<column> is not available at prediction time (your availability decision), so the models do not use it. The chart describes the training rows only." It stays runnable: EDA describes training rows (decision CR.7);
  - "Chart" lists, for the chosen column, the activities that accept it: "Distribution" (`eda.distribution`), and "Outcome rate by value" (binary `eda.rate_by`) or "Target mean by value" (regression `eda.mean_by`).
- **Button.** "Run on training rows" (`data-write="run_eda"`, W4).
- **Already computed.** When the chosen column already has a current result for that activity, the button reads "Show it" and scrolls to the card. It does not rerun.
- **Hint.** "Runs an engine EDA activity and records which rows were seen. Validation rows are never used here. For free exploration, use your workbench notebook, marked as an experiment." [Open the workbench]
- **Not runnable.** When `runnable` is false: "Not available yet: <missing texts>".

**States.**

- Empty: "No exploration yet. EDA runs after the split is confirmed." and the catalog when it is runnable.
- Loading: skeleton cards.
- Stale card: listed without figures.
- Failed run: the refusal (INV-8).

| Id | Requirement |
|---|---|
| ED-1 | The Request argv is exactly W4. A column not in `eda_catalog` is never sent: the controller rejects it as `invalid` before any CLI call |
| ED-2 | After a successful run, the gallery shows the new card, and the banner's train count equals the ledger. The validation count stays 0 |
| ED-3 | Bars with `small_count` have both the hatch pattern and the text "small" (not colour only) |
| ED-4 | Every rate and count text in a card equals the engine value, formatted with the precision of `content/activities.yaml`. A test compares the DOM `data-value` with the fixture |
| ED-5 | There is no control that names "validation" as a partition choice |
| ED-6 | On Auto MPG the gallery shows `eda.target_summary` and `eda.mean_by` cards, and the forbidden vocabulary (INV-12) is absent |

### A.4 Evidence (former; now the path's details and the ledger fold: §A.0)

Mockup: `Evidence.dc.html`.

**Results (left column).**

- **Filter.** A radio group with the options Current (default), Stale, and All.
- **List.** Each item shows the slot (or the activity), the headline segments, and a "stale" badge where it applies. Stale items have no figures (INV-7).
- **Selection.** Selecting an item loads `evidence:<rid>`.

**Result detail (right column).**

- **Header.** The slot as `h2`, then "<rid8>… · current|stale" with a "Select the id" button: it opens the full id and selects it, for the junior to copy with the keyboard. The panel writes no clipboard outside the agent bridge (§12, decision CI.5).
- **Facts list.**
  - "Evaluated on": the partition, `n_rows`, and `n_positive` when present;
  - the headline;
  - "Features": the count, and the excluded features by name, from `params` and `inputs.features`, and from the `feature_availability` decision;
  - "Preprocessing": `params.preprocessing` verbatim;
  - "Code": the module names, then "fingerprint matches" or "code changed since: <modules>";
  - "Exposure": the purpose, partition, and rows.
- **Buttons.**
  - "Show in report": opens the report at `#r-<rid>` when `report_anchor` is set; otherwise it is disabled with "This result is not cited in the current report".
  - "Show in the notebook": opens `notebook_hint.path` in the editor and selects the first line that contains `notebook_hint.search`.
  - "Ask the agent about this" (H).
- **Stale detail.** It shows `stale_reason` in words:
  - `reason` verbatim;
  - "code changed: <modules>";
  - "computed from a result that is not current: <rid8 list>";
  - "the case or dataset file changed".

**Uncertainty (E).** It lives in the detail of a `policy.evaluation` or `evaluate.regression` result.

- **Policy evaluation (binary).** For each rule in `params.rules`, one row with paired interval bars:
  - each model's `precision` and `recall` as a point inside its `intervals.<fit>` interval;
  - the `deltas.<fit.logistic>.precision` difference as a point and interval on an axis that includes 0, with a 0 rule.
- **Regression evaluation.** Each model's MAE and RMSE with their intervals, and the delta with its interval and a 0 rule.
- **Under each delta.** One fixed sentence, chosen by the position of the interval:
  - entirely above or below 0: "On these rows the interval stays on one side of zero.";
  - otherwise: "The interval includes zero: on these rows the difference could be chance."

  It is followed by the bootstrap description: "Paired bootstrap, <replicates> replicates, <level> level." The values are those of the result.
- **Small data.** The `small_validation_partition`, `capacity_exceeds_validation`, and `high_cardinality_grouping` items of `not_yet_defensible` that concern this result's slots are shown inside the detail, as warning boxes, verbatim.

**Lineage (C).** A horizontal flow of `lineage` nodes for the selected result: its ancestors (sources, decisions, results), the result, and its consumers (results and artefacts). It is rendered as an ordered list of chips separated by aria-hidden arrows. Each chip shows its kind and status ("bank.csv · sha ok", "split · your decision"). Below it:

- **Impact sentence.** It is built from `impacts`. For each impact whose `stale_slots` contains the selected slot: "Changing <decision title> (<change>) would make <stale_slots> stale; <kept fits> would stay current." For example: "Changing the feature list would make fit.logistic, its predictions and the policy evaluation stale. fit.baseline would stay current."
- **Lineage table.** A "Show as a table" toggle renders the nodes and edges as a table, for keyboard and screen-reader users.

**Exposure ledger (C).** It is a table of `exposure.ledger`. The purpose labels are:

| Purpose | Label |
|---|---|
| `structural_inspection` | "Structural inspection" |
| `train_eda` | "EDA" |
| `train_fit` | "Model fitting" |
| `validation_model_evaluation` | "Model evaluation" |
| `validation_policy_selection` | "Rule selection" (binary only; regression selection is recorded under model evaluation) |

The columns are Purpose, Partition, Rows, and "Recorded by" (activities). The row of a purpose used for selection on validation rows is highlighted. Below the table:

- the `validation_is_not_independent` and `public_data_already_explored` texts of `not_yet_defensible`, verbatim, when present;
- "Changing the split does not make explored rows unseen." whenever `split.values.overlap` is not null.

| Id | Requirement |
|---|---|
| EV-1 | The Current filter lists exactly the promoted current results. The Stale filter lists none of their figures |
| EV-2 | The ledger rows and counts equal `evidence.exposure.ledger`. Bank fixture: five rows, as in the mockup |
| EV-3 | A deep link `vscode://hypotrail-local.hypotrail-companion/result/<rid>` opens Evidence with that result selected and focused. An invalid id shows "This Hypotrail link is not valid." and opens nothing |
| EV-4 | "Show in report" opens a `file:` URI whose fragment is `r-<rid>`. It is disabled when `report_anchor` is null |
| EV-5 | Interval bars expose their values in an accessible table ("Show values"). An interval that includes 0 shows the "could be chance" sentence |
| EV-6 | The lineage of `fit.logistic` in the Bank fixture lists the dataset, split, feature availability, fit.logistic, policy.evaluation, and the report and notebook, in that order |

#### A.4.1 Final test first, development and final evidence apart (WP-B5)

Order of the tab: the final test, the exposure ledger, the development evidence, the variants and model families (v0.3, WP-K, §A.4.2), the final evidence, the diagnostics (when present), then the results and their detail, then the lineage.

- **Final test** (`data-ev="final-test"`, from the summary's `final_test` and `trials`, and the evidence's `final_test.evaluation`). Sealed: its rows "nobody has read", how they were set aside (the same share of each outcome, the latest rows in time order, ...), the development rows, that every figure below comes from rows that helped to choose, what must be confirmed before it can be opened (the choice, the variant, the success criterion, each with ✓ or ✗), and that opening it is a chat act: no button. Opened: the revision and the time of the evaluation, the junior's words quoted, and what was measured (the configuration in words, the final-test rows, the development rows of the refit). Changed after the opening: the decisions and results of `changed_after` in words. Absent: the study has no final test, so no figure is independent evidence. Then "Configurations evaluated: N" and one sentence on why the count matters.
- **Exposure ledger.** Each purpose in words, with what was done with the rows (`sealed`, `cross_validated_fit`, `out_of_fold_evaluation`, `out_of_fold_policy_selection`, `final_evaluation` added to §A.4); partitions as "development rows", "final test", "validation rows"; the final-test rows marked; the selection rows highlighted under cross-validation too.
- **Development evidence · used to choose.** The scheme in words (stratified, quantile, temporal folds; grouped duplicates), the spread across folds of the candidate and the variant (mean ± sd, lowest – highest fold, cited), and the variant: what it changes, each model on the same rows with its interval (the baseline grey), then the paired difference (variant minus candidate) with its interval on an axis with 0 and the fixed sentence of its side. A binary study shows the adopted (or proposed, or first evaluated) rule.
- **Final evidence · measured once.** The chosen model and the baseline on the final-test rows with their intervals, the paired difference, and the success criterion judged on the final test, all cited to `final_test.evaluation`; "Nothing is measured on the final test yet" while it is sealed.
- **Diagnostics** (WP-B4; CLI-CONTRACT §13, CLI-CONTRACT-COMPANION §14). Rendered when the evidence holds a current `diag.binary`, `diag.regression` or `diag.final_test`, in two labelled groups: development evidence (the rows read, out of fold or validation; the rule in words with its source: adopted, proposed, the case's teaching share as an exercise assumption, or the engine's default; "computed after the final test was opened" when its `started_revision` is above the opening's) and final evidence (the chosen model on the final-test rows; while sealed "the final test has no diagnostics yet", opening stays a chat act). The chosen model comes first (the adopted `@fit.variant` or model choice, else the candidate), the other under "Also". Binary: the confusion at the rule in words (reached, acted on by mistake, missed, correctly left out) with precision, recall and specificity; AUC and average precision; the gain curve (twenty points) and the calibration plot (ten bins with their Wilson intervals, the diagonal, the Brier score against the base rate); the segments with intervals and small cells marked; the largest coefficients with their bootstrap intervals. Regression: MAE and RMSE, the residual moments, the mean residual by range of the prediction on an axis with 0, the heteroscedasticity indicator, the quantile-quantile plot, residuals by variable, the coefficients, and "no target transform" (INV-12 holds). Every number is cited (`models.[fit].…`); points are marks. The panel never runs a diagnostic.

| Id | Requirement |
|---|---|
| EV-7 | The Evidence tab opens on the final test: sealed (rows, method, the chat act, no button), opened (revision, the junior's words, what was measured), changed after (the list in words), absent; with the trial count and its sentence |
| EV-8 | The ledger rows follow `exposure.ledger` with each purpose explained in words; the final-test rows are marked; no row is invented |
| EV-9 | Development evidence and final evidence are two labelled sections; the registry lists the final-test results apart |
| EV-10 | Under cross-validation the scheme is in words and the spread across folds shows mean ± sd and lowest – highest, each cited to its fit |
| EV-11 | The variant section shows each model with its interval and the paired difference with the sentence of its side, cited to the evaluation |
| EV-12 | Diagnostics appear only when `diag.*` results are current, development and final apart; each number is cited with its `models.[fit].…` path; a regression study shows none of the INV-12 words; no control runs them |

#### A.4.2 Variants and model families (v0.3, WP-K; WP-F1, ADR 0007, CLI-CONTRACT §14)

Read only, in the card pattern of §A.3.0a (an eyebrow, a question as title, the body, one finding, "Why?", a faint source line), after the development evidence. The engine's sentences (the one-standard-error rule, the optimism, the advice, the shortlist) are shown from their `texts` in the panel language; an engine text that exists in English only (the selection's `note`, a family's `note`) carries the "(en)" marker of §13.2 in a French panel.

- **Which configuration to keep** (`data-ev="selection"`). The budget as a chip and a sentence ("N of 3 variants used, M left"; `data-trial-budget="used/max"`), read from the full view (`trials`, live: every distinct variant ever confirmed counts, a replaced one too), else from the evaluation. When the current evaluation (`policy.evaluation` or `evaluate.regression`) stored an available `model_selection`: a table with one row per configuration (the candidate first, each variant named by what it changes: stronger or weaker penalty, without a group, tuned penalty, explainable boosting, gradient boosting), its mean ± standard error over the folds, and the paired difference with the candidate ± one standard error (cited to `model_selection.configurations.N.mean` and `.difference.mean`); the paired differences on an axis with 0; "Fold by fold" (a disclosure) with every per-fold value cited; the question each variant answers (quoted, from the full view; the stored selection drops it); the optimism (cited, `model_selection.optimism.estimate`); the advice with a chip "Stop here" or "Room for one more trial" and the engine's sentence. The finding names the configuration the one-standard-error rule keeps and whether it also has the best mean. Without cross-validation, the engine's `not_available` sentence. Without a current evaluation, "the comparison appears once the evaluation compares the variants fitted". "Why?" holds the budget's reason, the engine's rule and optimism sentences, its note, and the two sources.
- **Is there evidence for a non-linear model family?** (`data-ev="families"`, from `trials`: `view.model_families`). The recommendation as a chip (stay linear, a non-linear family may be compared, waiting for the diagnostics, diagnostics to run again); the flags of the linear checks in words, each with its p-value (a curved shape in a feature, a calibration slope that differs across a segment column, an overall calibration slope outside its band), or "No evidence for a non-linear family yet" (checked, nothing flagged, or not checked yet); the catalogue with each family's kind (glass box, black box) and status (default, on the shortlist, motivated by a flag, not on the shortlist, excluded by the case's interpretability constraint); the data-contingent sentence when a family proposed now would be one; the engine's shortlist sentence as the finding. The source line names the development diagnostics the checks were read from.
- **One card per compared variant** (owner session 2026-10-26, R11; `data-variant-card="<slot>"`, one per current variant fit in slot order, after the selection and shortlist cards; `data-ev="variant-fit"`, or `"family-fit"` for a family). What the variant changes (a stronger or weaker penalty, a group of variables left out, a penalty tuned inside each fold, another family) and its question; its mean ± standard error over the folds beside the candidate's and the paired difference, with whether it stays within the noise between folds (cited to `model_selection.configurations.N`); for a tuned variant (and a family's tuned setting), the value chosen in each outer fold and on all development rows (`tuning.per_fold.N.value`, cited to the fit); for a linear variant, its coefficients with their intervals from the current development diagnostics (`models.[<slot>].coefficients…`), or "Diagnostics not yet run for this variant" when none covers it. **A family's own diagnostics** (in the family variant's card, from its `family_diagnostics`). EBM: the importance of its largest terms (at most eight, bars, cited), the shape of the top main term (a nominal term as points on an axis with 0; a continuous term as the step function of its bins), the next two under a disclosure. Gradient boosting: the drop in AUC (or rise in MAE) when a column is shuffled, largest first, with the number of shuffles. Every value cited to the fit (`family_diagnostics.…`).
- **Decisions.** A waiting `model_variant` proposal shows, under its restatement, the budget it spends and the shortlist sentence (`data-trials-note`), read from `trials`; a `{"variants": [...]}` value reads in words ("Compare with a more regularised variant, an Explainable Boosting Machine and gradient boosting").
- **What if?** Unchanged: its gain and rules are per model, and the choice among configurations is the Evidence tab's.

| Id | Requirement |
|---|---|
| EV-13 | The selection card's figures are the stored `model_selection` of the current evaluation, each cited with its path; the budget follows the full view; nothing is computed but the geometry of the marks |
| EV-14 | The shortlist card shows the engine's recommendation, the flags in words with their p-values, or "no evidence for a non-linear family yet"; the family cards cite every importance and shape value to the fit |
| EV-15 | (Owner session 2026-10-26, R11) Every current variant fit has its own card in slot order, whatever it changes; its figures over the folds are cited to the stored selection, a tuned variant's per-fold values to its fit, a linear variant's coefficients to the development diagnostics, and a variant the diagnostics do not cover says so |

### A.5 What if? (the What if? drawer, v2)

Mockups: `WhatIf.dc.html` (binary) and `Regression.dc.html` (regression part).

**Banner on every state of the drawer.** It uses the experiment colour and an icon: "**Experiment, not adopted.** Nothing here changes the study. Computed from saved predictions; no model is refitted." It carries `role="note"` and `data-experiment`.

#### A.5.1 Binary: policy sandbox

- **Rule type.** A segmented control with Threshold and Capacity (`aria-pressed`).
- **Slider.**
  - Threshold: `<input type="range">` from 0 to 1, step 0.01. The label reads "Act on rows whose score is at least <t>".
  - Capacity: from 1 to `n` (the validation rows, from the current `policy.evaluation.values.n` or the `split` validation `n_rows`), step 1. The label reads "Act on the <k> highest-scored rows".
  - The initial position is the adopted or proposed rule when there is one, else the first evaluated rule.
  - The value is also editable in a number input bound to the slider.
  - `aria-valuetext` is "<k> rows" or "score at least <t>".
- **Under the slider (capacity).** "<k> of the <n> validation rows = <share> of rows. Extrapolate this as a rate, not as a count." The share is `k/n`, the only ratio the client computes. It is marked `data-literal="parameter"` and is a direct restatement of the junior's own parameter.
- **Comparison.** For each model (the logistic model and the baseline), bars of precision and recall from `preview.evaluations[rule][fit]`, with `selected`, `true_positives`, and the tie note when `tied_at_cut` is true ("Ties at the cut counted pro rata."). A `null` ratio is shown as "not defined (no row selected)".
- **Intervals.** After the slider is released, the panel requests `--intervals` for the current rule and shows the paired difference bar (E) with the sentence of §A.4.
- **Rules already evaluated.** A table from the current `policy.evaluation`, with these columns:
  - Rule;
  - Selected;
  - True positives, with the column title from the case, `target`, or "Positives";
  - Precision;
  - Recall;
  - Status: "adopted" (confirmed policy value), "proposed" (open proposal value), or "evaluated".

  The superseded rules of earlier evaluations are not shown, because their results are stale (INV-7).
- **Ask the agent to propose this (WP-E1; W3 withdrawn).** When the slider's canonical rule is one of `policy.evaluation.params.rules` (`preview proposal` says `proposable: true`), the engine's draft is shown read only ("What the agent would propose") with "Ask the agent to propose this rule" (`data-ask-propose`, no `data-write`): one press copies a question naming the rule in words and its token. The rule is named in words in headings and tables ("top 20%", "top 100 rows", "score at least 0.35"), its token in the hover.
  - Its hint reads "Copies a question for the chat. The agent proposes it there, and you answer in the chat."
  - For a rule that has not been evaluated: "This rule has not been evaluated by the engine yet, so the agent cannot propose it yet." and "Ask the agent to evaluate the rule "<rule in words>"" (H).

The capacity text above is case-neutral: "rows", not "clients". The case's own vocabulary appears only through engine texts.

#### A.5.2 Regression: residual explorer

There is no slider. The panel shows:

- **Model selector.** The linear model or the training mean (radio).
- **Error comparison.** MAE with its interval for each model, and the paired difference with its interval (E), from `evaluate.regression`. The heading is "Error on <validation description> · <n> validation rows". For an ordinal split the validation description is "<column> ≥ <cutoff>" (for example, "model_year ≥ 79"), from the split values.
- **Residual summary.** The selected model's `residuals` quantiles, as a box plot: "Residual = observed − predicted; a positive residual means the model predicted too low."
- **Bias by group.** From `residuals_by` (the time column), bars of `mean_residual` per group on an axis centred at 0, with `small_count` hatched.
  - When every group's mean residual has the same sign, a fixed sentence follows: "Every group is <positive|negative>: the model predicts these rows <too low|too high> on average." It is followed by the `extrapolation` glossary term when the split is `ordinal_cutoff`: "**Extrapolation**: predicting outside the range seen in training."
- **Split limits.** The `split.values.groups` (when `shared_groups > 0`): "<shared_groups> <column> values appear on both sides of the split (<validation_rows_in_shared_groups> validation rows). These rows are not fully independent. Grouped splits are not supported in this version."
- **Ask the agent to propose this model (WP-E1; W3 withdrawn).** When `preview proposal model_choice --value=<slot>` is `proposable`, the draft is shown read only with "Ask the agent to propose this model", a copied question.

#### A.5.3 Interactions and performance (What if?)

- Slider `input` events are debounced by 300 ms, and only the latest request is kept. A response whose `seq` is not the latest is dropped. At most one `preview policy` runs at a time.
- Results are cached per `(revision, canonical rule, intervals)`, keeping the last 64.
- Each CLI start costs about 0.5 to 2 s: `uv run` plus numpy and reading the predictions. While a preview is pending, the last values stay on screen, dimmed, with "Updating...". The slider never blocks.

| Id | Requirement |
|---|---|
| WI-1 | The banner is present in every state of the drawer (loading, error, empty, populated), with the warning of TOOL-4 |
| WI-2 | Moving the slider never runs a mutating argv. A test records every argv during 20 slider moves: only `preview policy` appears, at most one per 300 ms window |
| WI-3 | (WP-E1) No control of the tab writes: a `propose` message is dropped and no `decide` process runs. "Ask the agent to propose this rule" is shown only for a canonical rule in `params.rules`, next to the draft's texts byte-identical to `preview proposal` |
| WI-4 | A regression study renders §A.5.2 and none of §A.5.1, and INV-12 holds |
| WI-5 | Values from `preview` are never shown outside the What if? drawer |

#### A.5.4 Share rules and the gain curve (WP-B5)

- **Rule kinds.** Threshold, Capacity, and Share (`share:p`, 0.01 to 1 in hundredths; WP-B3): "Act on the top p of the scored rows". A share keeps its meaning on any number of rows; the engine turns it into a count.
- **Gain curve** (`data-gain`, an experiment surface). The engine's gain points (the top 5, 10 and 20 % of the scored rows) and every evaluated rule with the share it acts on (`capacity_share`), as points of the share of positives reached (recall) against the share of rows acted on, joined in order, with the random-selection diagonal; nothing is drawn between points as if measured. Marks: the junior's adopted or proposed rule, and the case's scenario share (`scenario_defaults.capacity_share`, read with `status --json`) labelled "exercise assumption" with the sentence that it is the exercise's assumption, not a team's figure. A table lists each point (cited) with "Try this share", which moves the slider (a preview, never a write).
- **Propose.** Since WP-E1 the panel proposes nothing: "Ask the agent to propose this" for a rule the engine evaluated (`proposable`), including a `share:p` rule; the panel never suggests the scenario share by itself.

| Id | Requirement |
|---|---|
| WI-6 | The gain curve shows only registered points (cited in its table), the diagonal, the junior's rule, and the scenario share labelled as an exercise assumption; no figure is computed by the panel |
| WI-7 | A `share:p` rule passes the protocol, the preview, and the draft, with the engine draft's texts byte for byte; a rule the engine did not evaluate is not proposable |

### A.6 Learn & hand off (former; now notions and the Deliverables drawer: §A.0)

Mockup: `Regression.dc.html` (learning parts).

#### A.6.1 Learning layer (G)

The learning layer is shown only when `learningLayer` is true.

**Glossary hovers.** Hovers apply to terms that the panel's own copy marks (`data-term="<id>"`), for example "Class imbalance", "MAE", or "Extrapolation".

- On hover, or on focus (keyboard), a tooltip (`role="tooltip"`, linked with `aria-describedby`) shows the `term` in bold, the `definition`, and the `example` segments when `example_status == "shown"`. The term comes first (AGENTS.md: the term first, then the contextual example).
- Escape closes the tooltip.
- A term absent from `explain.terms` (task filter) is not marked.

**Concept cards.** In My notions (§6.7.3; formerly at the top of the tab and at the first appearance of a step in Overview), there is one card per plan step that is `current` or `awaiting_confirmation`. The card is built from `explain.steps[step]`:

- the concept term, then its definition;
- `context`, `interpretation`, and `consequence` segments.

A card is "seen" each time it is fully visible for 2 s; it is not counted twice in one panel session. After it has been seen **twice**, it is collapsed to a one-line link "Show the concept: <term>". A "Hide concept cards" preference hides every card. Both are stored locally (§10).

**Predict before you look.** In Now, at the step it belongs to (§6.7.3), for each `explain.predictions` item whose step is current or done and that the junior has not answered for this study:

- a box shows "Optional · before you look", the `question`, and the `choices` as buttons;
- choosing one stores the choice locally (§10), then shows `reveal` when `available` (else "The answer appears once the engine has computed it.");
- the reveal box carries "Kept on this computer only. Never written to the study."

The answer is never sent to the CLI, the chat, or the study. "Reset my answers for this study" clears them.

| Id | Requirement |
|---|---|
| LE-1 | No message carrying a prediction choice ever reaches `cli.js`. A unit test spies on `run` |
| LE-2 | A concept card collapses after its second sighting, and the count survives a panel reload (globalState) |
| LE-3 | Turning `learningLayer` off removes every tooltip, card, and prediction, and no `explain` call is made |
| LE-4 | Tooltips appear on focus as well as hover, and close on Escape |

#### A.6.2 Hand off (I)

**Export.** A section "Hand the study over", with the button "Export a handoff pack" (`data-write="export"`, W7).

- The extension asks for a parent folder with a folder dialog (`showOpenDialog` with `canSelectFolders`, default `<study>/handoff/`) and passes `--out=<parent>/revision-<n> --expected-revision <n>`, so the engine refuses the export when the study moved since the panel showed revision n (decision CR.6). An engine that does not know the option refuses it (`invalid_arguments` naming `--expected-revision`); the panel never exports without it: the outcome is that refusal, the engine message verbatim, with the sentence that the study engine is older than the panel and must be updated (`lib/refusals.js`, `OLDER_ENGINE_EXPORT`). The default output is CC §7's.
- The outcome and "Open folder" name the folder the engine answered (`out`), never one the panel computed.
- The outcome lists the files written with their sizes, `warnings` in words (`recorded.warnings`, decision CI.3), and "Open folder" (`revealFileInOS`).
- With exit code 3, the outcome reads "The report was not current, so it is not in the pack. Regenerate it in the Deliverables drawer and export again if you need it."

**Reviewer mode.** A line explains it: "A reviewer can open this study read-only with "Hypotrail: open the study panel (reviewer, read-only)"."

- HO-1. Export runs the exact argv of W7. A non-empty target gives the `export_target_exists` refusal, verbatim.
- HO-2. Export stays in reviewer mode, and is the only write control there (decision CA.9, which answered the open question; WP-I aligned this text).
- HO-3. (Owner session 2026-10-26, L7, D15; wave W1 integration) At `done`, when the summary's `next_action.after_study` carries a junior text, the section shows "After the study" (`data-after-study`): that text verbatim (the handoff pack; the Azure ML export plan only when the chosen model is supported, else why not; no Azure job or endpoint ever run), and, only when `after_study.azureml.supported` is true, "The Azure ML export plan is available for this model: ask the assistant for it in the chat. This panel exports only the handoff pack." Read only: no control, no command, no new write (the panel's writes stay W4–W7). "Your next move" in Overview shows the same block under "Every step is done", at every stage.

#### A.6.3 Session report (J)

The session report is in a collapsed `<details>` titled "Session report (for an observed session)". Expanding it runs `session-report`. It shows:

- `sources.session_log.enabled`, as "Session log: on" or "off", with `sources.session_log.note` verbatim;
- `span` (first, last, and duration);
- `pauses` (seconds per pause);
- `refusals` counts by code and reason;
- `decisions` (seconds open, refused confirmations);
- `gaps`.

It shows no conversation content, because the report holds none.

The panel **does not** turn the session log on or off, because that would be a write. When the log is off, the panel shows the existing instruction verbatim: "Start the CLI once with HYPOTRAIL_SESSION_LOG=1 to turn it on; delete .hypotrail/session-log.jsonl to turn it off."

- SR-1. The view shows the log status and no `user_words`. A test asserts that no fixture `user_words` string appears in the section.

### A.7 Term marking

Terms marked in the panel's own copy are listed in `media/terms.js`, a map from `data-term` id to the place where it occurs. A test checks that each id exists in the glossary of at least one task.

### A.8 Agent bridge (H; every copy button from v0)

The "Ask the agent about this" buttons appear on:

- decision cards (from v0, one press copies the ready question without the modal: WP-E1);
- What if? for a rule or model the engine evaluated ("Ask the agent to propose this", one press, WP-E1);
- reconfirmation items;
- Evidence details;
- not-yet-defensible items;
- What if? for a rule that has not been evaluated;
- Learn concept cards.

Pressing one opens a small modal inside the webview. Its fields are:

- "About": read-only, the cited object;
- "Your question": an empty textarea, which may stay empty;
- the buttons "Copy for the chat" and "Insert into the chat" (the latter only when `chatInsert` is true, which it never is until the insertion is verified: CR.8).

The text prepared is a fixed template in English:

```text
Question about my Hypotrail study (<study folder name>), revision <N>.
About: <kind> <id> — <label>.            e.g. "result 1a2b3c4d (fit.logistic, validation AUC)"
                                              or "decision policy (proposal p_7, open)"
My question: <typed question, or "Can you explain this and what it means for my study?">
This is a question, not a confirmation of anything.
```

- It never includes the junior's draft confirmation words, a restatement, or study values beyond the identifiers above.
- **Copy** uses `vscode.env.clipboard.writeText(text)`, then shows "Copied. Paste it into the chat with your assistant."
- **Insert** runs `vscode.commands.executeCommand('workbench.action.chat.open', { query: text, isPartialQuery: true })`.
  - **Unverified:** the command id and the `query` and `isPartialQuery` arguments come from offline knowledge of VS Code 1.9x. They have not been checked against the documentation or a real VS Code. The extension never passes an option that submits.
  - If the command throws or is missing, the bridge falls back to Copy and says so.
  - Because an older VS Code could submit a query that ignores `isPartialQuery`, `chatInsert` stays off by default until the first real VS Code session verifies that the text is inserted and **not sent** (ADR 0004, v2 exit criteria).
  - The Claude Code extension and other agent chats have no insertion API; Copy is their path.

| Id | Requirement |
|---|---|
| AB-1 | The bridge never calls `vscode.lm`, never sends, and never includes the textarea content of a decision card. A unit test checks the template against a card whose draft words are set |
| AB-2 | With `chatInsert` false, only the clipboard is used. With it true and a throwing command, the clipboard is used and the notice says so |
