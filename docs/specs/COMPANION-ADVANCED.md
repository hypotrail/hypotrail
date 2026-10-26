# Advanced companion: detailed specification

Status: **implemented behind the flag** (stages v0 to v3; WP-0, WP-E1 to E3, WP-U1 to U5, integrated by WP-I with decisions CI.1 to CI.17 in [V0.1-DECISIONS](../plans/V0.1-DECISIONS.md)). Tested in Node, an offline browser, and on the real CLI; **not run inside a real VS Code** ([manual checklist](../../clients/vscode-companion/MANUAL-TEST.md)). The default stage stays `v0`. The scope and the staging are in [ADR 0004](../decisions/0004-companion-advanced.md). The engine interfaces are in [CLI-CONTRACT-COMPANION.md](CLI-CONTRACT-COMPANION.md), cited below as **CC §n**. The work packages and file ownership are in [COMPANION-ADVANCED-PLAN.md](../plans/COMPANION-ADVANCED-PLAN.md). The code base is `clients/vscode-companion/`, which is v0 ([ADR 0003](../decisions/0003-companion-webview-v0.md), decisions CW.1 to CW.12).

**Amended by WP-A5 (v0.2a, 2026-10-19; editable-copy extension 2026-10-23).** The panel speaks to the junior, not to the agent: the "verbatim" rule of engine texts becomes the **two-layer copy contract** of §15.1 (INV-16); every stage opens on "Your next move" (§6.1.0); the journey marks the step that waits for the junior (§6.1.2); decision values are shown in words with the recorded value in a hover and under "Details"; limits carry a severity and are listed once (§6.1.5); "Since your last session" is grouped (§6.1.3); a load error replaces the content (§3.3); Health appears only when something is wrong; the deliverables offer "Open file" and the three Marimo launches of ADR 0004 "local launch" (§6.1.4); the theming, high-contrast, and narrow-width rules of §13 are extended. Where this amendment and an earlier paragraph differ, the amendment wins. Mockups: `docs/design/companion-v0.2-mockups/` (overview, decisions, deliverables).

**Amended by WP-A7 (v0.2a, 2026-10-19).** New views, read only; the writes stay W1–W7. The EDA tab becomes **Data & EDA** (its id stays `eda`): it opens on the data card (`hypotrail data`, a new read, §5, §6.3.0) and the quality check of the development rows, then the exploration of the training rows, where each chart is titled by the question it answers, shows its confidence intervals with n and the shuffled-outcome null band, and the single-feature signal raises the leakage detector's question (§6.3.1); "Run another chart" (W4) offers training-row charts only and says the question first. The Decisions tab shows the confirmation mode and what counts as an answer, the basis of each confirmation as a chip (restated, endorsed, delegated), the agent's concern kept on a confirmation, and later corrections (§6.2.5). The header carries the final-test chip on every tab (§4.1, FR-1); the Overview's "Where we are" shows the success criterion's status (§6.1.1, OV-9). Engine requests of WP-A5 delivered with it: `deliverables` and `mode` in `status --summary`, `recap_junior` in words, digest items with `audience`/`junior_text`, the unknown outcome named in words (CLI-CONTRACT §3, §3.3). Mockups: `eda.html`, `decisions.html`, `overview.html`, and the seal chip of `evidence.html`.

**Amended by WP-B5 (v0.2b, 2026-10-19).** Read-only views of v0.2b; the writes stay W1–W7. The Evidence tab leads with the final test and the exposure ledger, separates development evidence (cross-validation, the variant) from final evidence (the one evaluation of the final test), and shows the diagnostics when the engine has them (§6.4.1, EV-7 to EV-12). The What if? tab gains a third rule kind, a share of the scored rows, and the gain curve of the registered points, with the teaching scenario's share labelled as an assumption of the exercise (§6.5.4, WI-6, WI-7); W3 accepts a `share:p` rule the engine evaluated. "Your next move" covers the pauses of v0.2 (the success criterion, the data preparation, the variant, the opening of the final test); **opening the final test is a chat act**: the panel explains it and points to the chat, and neither the Overview nor the Decisions card offers a control for it; the controller refuses W1 for a `final_test` proposal (a narrowing of W1, §7), and the Decisions badge does not count it. "Where we are" shows the final test (sealed, opened once in the junior's words, changed after the opening) and the confirmation mode with what counts as an answer; changing the mode is a chat act (§6.1.0, §6.1.1, §6.2.5, OV-10, OV-11, DC-10, DC-11). One new read: `scenario` (`status --json`, its `view.scenario_defaults`; §5). Mockups: `evidence.html` (its "Open the final test… (in the chat)" button is not built: the opening has no control) and `overview.html`.

**Amended by WP-E1 (v0.3, 2026-10-20): the narrowing.** W1 (confirm), W2 (withdraw), and W3 (propose) are withdrawn at every stage (owner decision R23, integrator decision I2; [ADR 0004](../decisions/0004-companion-advanced.md) decision 8, AGENTS.md). The panel's writes are **W4–W7**; the messages `confirm`, `withdraw`, and `propose` no longer exist (§8.1) and are dropped as unknown. The pending decision card is read only (§6.2.1): the restatement block, the value in words, "If you confirm" in words ("Confirming changes nothing already done." when the confirmation invalidates nothing; what stays current and what is regenerated under Details), "Answer in the chat", and "Ask the agent about this", which copies a ready question for the chat at every stage (the agent bridge, §6.8, now from v0). The proposal id, its revision, and its origin are under Details (R22). The history is newest first, with the revision and the time in the hover (§6.2.3, R25); values in words carry no dotted underline (the citation style stays on numbers). In What if?, the engine's draft is shown read only next to "Ask the agent to propose this", a copied question (§6.5). Quick fixes of R26: the EDA rows-seen line is split-aware (under cross-validation, the development rows EDA read; no "validation rows stay unexplored"), rule tokens and prepared feature names read as words (`share:0.2` → "top 20%", `cat__poutcome_success` → "poutcome = success", `development_diagnostics` → "Diagnostics of the models"), the quality table drops "0 / 0" and "no declared range", and the y-axis label of a curve is written above the axis so it is never clipped. Where a section below still describes W1, W2, or W3, this paragraph prevails.

Requirement identifiers are written like `OV-3`. Each one is testable, and the plan maps each one to a test. "MUST" and "MUST NOT" are binding. The visual target is the six static mockups (`companion-mock/project/*.dc.html`): their layout, content, wording, and colours express intent; their numbers are real Bank and Auto MPG walkthrough values; their result ids are illustrative. Where the mockups and this document differ, this document wins.

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
| INV-5 | Every textarea that becomes `--user-words` starts empty and is never filled, suggested, autocompleted, or restored from another proposal. "Confirm" and "Acknowledge" stay disabled until the field holds a non-blank character. No control confirms in one click. Since WP-E1 no control of the panel confirms at all | CW.5, PV.2 |
| INV-6 | A proposal, a preview, a draft, a What if? result, a prediction answer, or a learning card is **never** shown as a decision. Every such surface carries its label ("proposal, not a decision yet", "Experiment, not adopted", "Draft only") | AGENTS.md |
| INV-7 | A number is shown only when it comes from (a) a result with `current: true` and `integrity: "ok"`, as a cited segment, or a value of such a result in `evidence`/`status`; (b) a `preview` payload, shown only inside an Experiment surface; or (c) a recorded literal (revision, counts of the engine's own lists). Stale results are listed with "Not cited", without figures | CLI-CONTRACT §4 |
| INV-8 | The engine's refusal is shown with its `code`, its `reason`, the engine message **verbatim**, and a short explanation from `lib/refusals.js` that never suggests words to type. After a refusal the panel refreshes. A write without a JSON answer is reported as "outcome unknown", never as success | CW.8 |
| INV-9 | Study text is set with `textContent`, or as SVG text nodes; it is never parsed as HTML. The webview runs under the v0 CSP (§12) | CW.10 |
| INV-10 | Behind the master flag `hypotrail.companion.enabled` (default `false`). With the flag off, the command and the URI handler show "Companion disabled (feature flag)", and nothing else runs: no file is read and no process is started | CW.2 |
| INV-11 | A trusted workspace is required (`untrustedWorkspaces.supported: false`, checked at run time) | CW.2 |
| INV-12 | In a regression study the companion's own copy never uses the vocabulary of a decision rule: `threshold`, `capacity`, `precision`, `recall`, `positive class`, `policy`, `calling rule`, `decision rule`, `selected`. Texts from the engine are task-aware already. A Playwright test scans the whole DOM text of every tab on the Auto MPG fixtures for these words (case-insensitive, whole word) | CLI-CONTRACT §10, handoff M3 |
| INV-13 | The companion never fits a model, runs `split`, `policy.evaluate`, or `evaluate.regression`, records or resolves a note, edits a notebook, or runs "validate all". From the webview, EDA requests reach only the `eda.*` activities that `evidence.eda_catalog` lists | owner's feature list |
| INV-14 | No figure is computed by the companion. Bar lengths and axis positions are geometry derived from engine values. They are never displayed as numbers that the engine did not emit, except axis tick labels, which are rounded positions of an axis, are marked `aria-hidden`, and carry `data-literal="axis"` | INV-7 |
| INV-15 | Precomputed tutorial outputs (`use-cases/*/results.json`, `project.json`) are never read | AGENTS.md |
| INV-16 | Two-layer copy (§15.1, WP-A5). An engine text whose `audience` is `agent` (CLI-CONTRACT §3.3) is **never** primary content: the panel shows the engine's junior variant (`next_action.junior_message`, `not_yet_defensible.top[].junior_text`, `recap_junior`, `artifacts.items.*.junior_message`) or its own copy keyed by the engine's `kind`, `code`, or id; the engine text stays available under a "Details" disclosure (or a hover). Raw tokens (`capacity:100`, `p_5`, result ids, decision ids, slot names) are not primary content either: they go to a hover (`title`) or "Details". Refusals keep INV-8 (the engine message verbatim, it answers the junior's own action) | v0.2 synthesis §1 item 5 |

## 3. Activation, flags, stages, modes

### 3.1 Flags

| Setting | Type, default | Effect |
|---|---|---|
| `hypotrail.companion.enabled` | boolean, `false` | Master flag (INV-10). `HYPOTRAIL_COMPANION=1` also turns it on, as in v0. Turned off while a panel is open, it closes the panel and disposes its controller and watcher (decision CR.10) |
| `hypotrail.companion.stage` | enum `"v0"`, `"v1"`, `"v2"`, `"v3"`, default `"v0"` | Which feature set is active (§3.2). `HYPOTRAIL_COMPANION_STAGE` overrides it (tests, observation sessions). Each stage includes the earlier ones. A stage higher than the extension knows reads as the highest one it knows. The default moves only through an ADR amendment after a stage's exit criteria are met (ADR 0004) |
| `hypotrail.companion.learningLayer` | boolean, `true` | Stage v3: glossary hovers, concept cards, and predictions. Off: none of them is rendered and `explain` is not called. It is a preference of the junior, not a feature gate |
| `hypotrail.companion.chatInsert` | boolean, `false` | Stage v2: "Ask the agent" inserts into the chat input through `workbench.action.chat.open` instead of the clipboard (§6.8). Until the API is verified in a real VS Code, the setting is **ignored** and reads as `false` (`lib/flag.js` `CHAT_INSERT_VERIFIED`, decision CR.8) |
| `hypotrail.companion.reviewer` | boolean, `false` | Read-only reviewer mode (§3.3). The command "Hypotrail: open the study panel (reviewer, read-only)" opens a reviewer panel whatever the setting |

**No per-feature sub-flags.** One stage enum keeps the test matrix small, at four stages: per-feature booleans would give 2^12 combinations. It also makes an observation session reproducible from one value. The only booleans are preferences or safety switches whose default must be off until something is verified (`chatInsert`) or until the user chooses it (`reviewer`).

`check_layout.py` is updated to assert the following:

- `enabled` defaults to `false`.
- `stage` defaults to `"v0"`.
- `chatInsert` defaults to `false`.
- `activationEvents` is exactly `["onCommand:hypotrail.companion.open", "onCommand:hypotrail.companion.openReviewer", "onCommand:hypotrail.companion.goToResult", "onUri"]`.
- The source still matches none of the forbidden APIs.

The plan's WP-I owns that change.

### 3.2 Stages

| Stage | Tabs and features (letters of the owner's list) | Engine additions it needs |
|---|---|---|
| v0 | v0 panel, rendered by the new view framework: recap, plan, deliverables, pending decision cards (read only since WP-E1: answered in the chat, "Ask the agent about this" copies a question) | none |
| v1 | **Overview** (A: map, recap, since last session; F: deliverables with Regenerate, executions with acknowledgement, check findings); **Decisions** (B: cards, impact preview, history, reconfirmation queue); multi-study switch (K); reviewer mode (I, without export) | C1, C2, C3, C10 (check `location`) |
| v2 | **EDA** tab (gallery, Request a chart); **Evidence** tab (C: registry, lineage, exposure ledger, deep links; E: interval bars, small-data warnings); **What if?** tab (D: policy sandbox or residual explorer; "Ask the agent to propose this" since WP-E1); agent bridge (H) | C4, C5, C8, C9, C10 (anchors) |
| v3 | **Learn & hand off** tab (G: glossary hovers, concept cards, predictions; I: export handoff; J: session report) | C6, C7 |

A tab or control of a later stage is **absent** from the DOM, not merely disabled. A test checks that every `data-stage` element is absent below its stage.

### 3.3 Modes and states that apply to every tab

| State | Trigger | Behaviour |
|---|---|---|
| Flag off | INV-10 | Nothing is rendered; one information message |
| Untrusted | `vscode.workspace.isTrusted === false` | Error message "The Hypotrail companion runs the study CLI, so it needs a trusted workspace."; nothing is rendered or run |
| No study | No folder found (§6.1.6) | A folder dialog (v0). If it is cancelled, nothing happens |
| Moved study | `agent.json.study` differs from the folder | The `study_moved` message of v0 |
| Loading | The first `status` call has not answered | The header shows "Reading the study..."; tabs are skeletons with `aria-busy="true"`; no control is enabled |
| Load error | The CLI cannot start, prints no JSON, or refuses | (WP-A5) The error **replaces the content**: no tab content, alert strip, or recap strip is rendered. A `role="alert"` card says what happened, gives the next step ("Press Retry. If it fails again, ask the assistant in the chat to run the study status ..."), says "Last read at revision N; the study could not be read now" when a snapshot existed, and keeps the CLI's message and stderr under "Details from the CLI". "Retry" reads again; the content comes back with the next snapshot |
| Stale view | A watch event or a write moved the version while a tab shows older data | Each tab's data carries the version it was read at: the revision and the summary's `currency` (decision CR.1, §5). A tab whose data is not at the snapshot's version (an older revision, or the same revision under another currency: a dataset edit, a deleted or edited deliverable) reloads (§11); its older content is marked busy (and dimmed where the view keeps it visible); "Updating..." is never shown next to content that is current (WP-A5). A textarea with text keeps the text and shows the warning of §6.2.1 "Answer" (CW.9, decision CR.3) |
| Reviewer | `reviewer` setting or command | The header shows a badge "Reviewer, read-only". **No** element with `data-write` is rendered except Export: no textarea for words, no Run, Regenerate, or Acknowledge (Confirm, Withdraw, and Propose no longer exist, WP-E1). The controller refuses every write message of the study (W4 to W6) with `kind: "invalid"` and "Read-only reviewer mode." (RV-2). The handoff export (W7) writes no study state, so a reviewer may run it (decision CA.9). Reads, navigation, Open, Show in report, and the agent bridge stay |
| Read-only process | `HYPOTRAIL_READ_ONLY=1` in the extension host | Writes are refused by the engine (`read_only`) and shown as refusals. Nothing special is done in the client |
| Busy | One write is running | Every `data-write` control is disabled, and the busy control shows `aria-busy="true"` and "Working..." |

## 4. Information architecture

### 4.1 Frame (every tab)

```text
┌ header: logo · "Hypotrail · <case id>" · [final-test chip, WP-A7] · [regression] · badge "Experimental · feature flag on"
│         [Reviewer, read-only] · study switcher (v1) · "revision N" · "read from CLI · <age>" · [Refresh]
├ tabs:   Overview · EDA (v2) · Decisions [count] · Evidence (v2) · What if? (v2) · Learn & hand off (v3)
├ alert strip (only when present, every tab except Overview; WP-A5): sources changed · execution with unknown outcome · integrity error · (L9, R20) automatic study to review · final test opened automatically
├ recap strip (every tab except Overview, collapsible, remembered per panel in vscode.setState; collapsed by default since v0.3, WP-E2):
│         Goal / Decided / Now / Next / Limit: summary.recap_junior (WP-A5), its Decided line in the panel's words
├ main: the tab
└ footer: "Reads the hypotrail CLI only · no state of its own · the chat, report and notebook stay complete without it."
```

**v0.3 (WP-E2) frame.** The header holds the EN | FR language toggle next to Refresh (§13.2); the revision is a faint word, not monospace. Under the tab bar each tab opens with one lead sentence saying what it is for (`data-tab-lead`, `copy.core.tabLeads`; owner addition, integrator decision I1). The tab bar wraps on a narrow panel instead of scrolling sideways.

**Final-test chip (WP-A7).** From `summary.final_test` (CLI-CONTRACT §4.1), on every tab and every stage: "Final test sealed · N rows" (`ht-st-sealed`, N the engine's count) when sealed, "Final test opened · N rows" when opened (v0.2b), and "No final test" for a study created before the seal (status `absent`); its hover says what it means. An engine without `final_test` gives no chip.

- FR-1. The chip reads "Final test sealed · 904 rows" on every tab of the captured Bank study, and "No final test" for a legacy summary (`test_webview_wp_a7.py`).

**Tab order.** The order follows the mockups. The final names are Overview, EDA, Decisions, Evidence, What if?, and **Learn & hand off**. The mockups' "Learn" becomes "Learn & hand off" because the tab also holds the export and the session report.

**Decisions badge.** The badge counts open proposals plus decisions in `reconfirm_required`. It is hidden when the count is 0, and its accessible name is "N waiting for you".

**"read from CLI · <age>".** The age is the time since the last successful read, computed by the client from its own clock. It is a clock of the view, not a study fact. It reads "just now", then "12 s ago" or "3 min ago", updated every 15 s without a CLI call.

**Tabs.** The tabs follow the WAI-ARIA tab pattern: `role="tablist"`, arrow keys, Home and End, `aria-selected`, and `aria-controls`. The selected tab is kept in `vscode.setState`.

**Alert strip.** Its sources are, in this order:

- the `sources_changed`, `interrupted_executions`, and `result_integrity` items of `summary.not_yet_defensible.top` (their `text` verbatim);
- `next_action.kind == "outcome_unknown"` (its `message` verbatim).

Each alert links to the Overview's "Needs attention" section. (WP-A5) The text is the item's junior variant, or the panel's words for its id (§15.1), never an `agent` text; an unknown outcome is one alert (the matching `interrupted_executions` item is not repeated); the strip is not shown on the Overview, whose first block already says what waits.

### 4.2 Navigation targets

A navigation request is `{tab, kind, id}`, where `kind` ∈ `result`, `decision`, `proposal`, `step`, `limit`, `execution`, `term`. Navigation requests come from deep links (CC §11), evidence chips, and the command "Hypotrail: go to a result...". The target tab opens, scrolls the item into view, moves focus to its own heading (`h2` to `h4`; decision CI.14), and highlights it for 2 s, without motion when `prefers-reduced-motion` is set.

## 5. Data sources and caching

| Data key | CLI argv (after `agent.argv`) | Schema | Read when | Used by |
|---|---|---|---|---|
| `summary` | `status --summary --json --study S` (v0); `status --summary --digest --json --study S` (v1 and later) | `hypotrail.summary/1` (+ CC §1) | on open, on visible, on watch, after each write, on Refresh | frame, Overview, Decisions cards |
| `decisions` | `decisions --json --study S` | `hypotrail.decisions/1` | Decisions tab shown, and the revision moved | Decisions history and queue |
| `effects:<pid>` | `preview effects <pid> --json --study S` | `hypotrail.preview_effects/1` | a card becomes visible (IntersectionObserver), at most 3 cards at once | "If you confirm" |
| `evidence` | `evidence --json --study S` | `hypotrail.evidence/1` | EDA, Evidence, or What if? shown, and the revision moved | EDA, Evidence, What if?, interval bars |
| `evidence:<rid>` | `evidence --result <rid> --json --study S` | same | a result is selected | result detail |
| `preview:<rules>` | `preview policy --rule R [--rule R2 ...] [--intervals] --json --study S` | `hypotrail.preview/1` | slider moves (debounced) | What if? (binary) |
| `draft:<d>:<v>` | `preview proposal <d> --value=<v> --json --study S` | `hypotrail.proposal_draft/1` | an evaluated value in What if? | the read-only draft card next to "Ask the agent to propose this" (WP-E1) |
| `check` | `check --json --study S` | `hypotrail.check/1` | Overview Health section expanded, and the revision moved | findings |
| `explain` | `explain --json --study S` | `hypotrail.explain/1` | first glossary hover or Learn tab, and the revision moved | Learn, hovers, cards |
| `session_report` | `session-report --json --study S` | `hypotrail.session_report/1` | Learn tab "Session report" expanded | session report |
| `data` | `data --json --study S` (WP-A7) | `hypotrail.data/1` (CLI-CONTRACT §11.1) | Data & EDA tab shown, and the version moved | the data card |
| `scenario` | `status --json --study S` (WP-B5) | `hypotrail.status/1` (its `view.scenario_defaults`, CLI-CONTRACT §4) | What if? tab shown, and the version moved | the scenario share on the gain curve |
| `trials` | `status --json --study S` (v0.3, WP-K; the same process and cache entry as `scenario`, key `view`) | `hypotrail.status/1` (its `view.model_selection` budget and questions, and `view.model_families`, CLI-CONTRACT §14) | Evidence tab shown, or a `model_variant` proposal waits on the Decisions tab, and the version moved | the variant budget, each variant's question, the family shortlist |

**Currency (decision CR.1).** A cached read is valid for one *version* of the study: the summary's revision **and** its `currency`. `currency` is the engine's root field of `status --summary --digest` (a short hexadecimal digest that changes when the dataset is edited, after a render, or when a deliverable is edited or deleted) when the engine sends it. With an engine that does not, the controller computes it (`lib/models/summary.js` `currencyOf`): the first 16 hexadecimal characters of the SHA-256 of the artefacts' statuses, messages and revisions, the not-yet-defensible items, `sources_changed`, and each result slot's id, current flag, integrity, and stale reason. Every read (`view_data`, `effects`, `draft_result`, `preview_policy_result`) carries the currency it was read at, and the webview reloads a view whose data is not at the snapshot's version. `effects:<pid>` and the `evidence:<rid>` detail (its `report_anchor`) follow the same rule.

**Refresh rule (decision CR.1).** The explicit Refresh (the header's button, and Retry of the load-error banner) and every write (W4 to W7) empty the controller's non-preview cache; after the explicit Refresh the webview also reads every shown view again, even at the same version. A watch event keeps the cache: it reads the summary, and a view only when its version moved.

**Session log (integration, owner decision on CLI-CONTRACT §8.6).** Every read above runs with `HYPOTRAIL_SESSION_LOG=0` merged over the host's environment (`lib/cli.js` `READ_ENV`): the engine logs `status` and `check` when the log is on, to observe how often the junior checks, and the panel's own re-reads (on open, on watch, after a write) are not the junior's checks. A write (W4 to W7) inherits the environment, so it is logged like the chat's; W7 (`export`) is never logged by the engine.

**Free text in an argv.** It always uses the `--opt=value` form: `--user-words=`, `--value=`, `--column=`, `--restatement=`, `--rationale=`, and `--reason=`. A value that starts with `-` is therefore never read as an option (CW.7).

## 6. Views

Every view below lists its sources, its components, its states, its interactions, its writes, its accessibility points, its copy, and its acceptance criteria. Stable test hooks are `data-*` attributes, listed in §16.

### 6.1 Overview (stage v1; v0 shows its v0 subset)

Mockup: `Main.dc.html`; WP-A5: `docs/design/companion-v0.2-mockups/overview.html`, `deliverables.html`.

Order (WP-A5). Stage v0: Your next move, the plan (§6.1.2 as one list), Where we are, What you cannot claim yet, Deliverables. Stage v1 and later: Your next move, Needs attention (only when something is wrong), Study map, Since your last session next to What you cannot claim yet, Where we are, Deliverables (with the checks).

#### 6.1.0 Your next move (WP-A5, every stage)

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

#### 6.1.1 Where we are (A)

(Amended by WP-A5.) A `<dl>` with **Goal** (the `Goal` line of `summary.recap_junior`, or of `recap` from an engine without audience keys) and **Decided** (one line per confirmed or to-reconfirm decision in plan order: its name and its value in words, `media/copy/junior.js` `value`, the recorded value in the hover; "to confirm again" or "left to the assistant" as a status tag). The five lines of `recap_junior` follow, byte for byte, under "Details: the engine's recap". The agent recap (`recap`, `recap_audience: agent`) is never rendered. "Next" and "Limit" are not repeated here: the next move (§6.1.0) and the limits (§6.1.5) say them.

- OV-1. The Details hold `summary.recap_junior`, byte for byte; no line of the agent recap that differs from it appears in the Overview.
- OV-2. Without a recap, there is no Details disclosure and no Goal line; Decided still lists the decisions.

(WP-A7.) "Decided" also lists the success criterion and the data preparation. A **Success criterion** row follows, from `summary.criterion` (CLI-CONTRACT §11.4): the criterion in words ("Adopt only if precision beats the baseline by at least 5 points"), a status chip (met, uncertain, not met, not assessed yet) with one sentence of what it means, and, when the engine gives one, its gain with the paired interval, signed, in points (binary, `f1`) or as a share (regression, `pct1`), each figure cited to the evaluation `result_id`; a verdict that contradicts the criterion adds a warning line. The panel computes none of these figures.

- OV-11. (WP-B5) Two more rows: **Final test** (sealed with its rows; opened at a revision, in the junior's words quoted, with the success criterion judged on the final test, cited; changed after the opening, with what changed in words; or absent) and **Answers** (the mode as a chip, what counts as an answer in that mode, guided, training or express, the reason the trade-offs and the opening need, and that the mode changes in the chat only; no control).
- OV-9. With the Bank fixture the row reads "met" and the cited figures +30.5, +21.4, +40.2; each status changes the chip; a regression criterion reads as a share and holds none of the INV-12 words.

#### 6.1.2 Study map (A)

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

#### 6.1.2a How this panel works (v0.3, owner addition, I1)

The last card of the Overview at every stage (`data-ov="guide"`): what the panel is (a reader of the CLI with no state of its own; the chat, report and notebook stay complete without it), that decisions are made in the chat only, the writes it can make (W4–W7, in words), that every figure is an engine value with its source on hover and its caveats under "Why?", and that the language toggle changes the panel only. From v1 a "What each tab is for" disclosure lists every visible tab with its lead sentence. No extra tab.

#### 6.1.3 Since your last session (A)

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

#### 6.1.4 Deliverables (F)

(Amended by WP-A5 and the 2026-10-23 editable-copy extension; stage v0 and later.) Titled "Your deliverables". One row per item of `summary.artifacts.items`, in the order `report`, `notebook`, `editable`, `workbench`:

- the label and the file ("Report · study.html"), the study-relative path, and one sentence of what it is;
- a status tag of one vocabulary (current, out of date, failed, missing, edited; "yours" for the editable copy and workbench) and the item's `junior_message` (the engine `message`, which names paths for the agent, in the hover);
- the report: "Open in browser"; the generated notebook: **"Open in Marimo (read)"** (`marimo run`) and "Open file"; the editable copy and workbench: **"Open in Marimo (edit)"** (`marimo edit`) and "Open file". In reviewer mode neither editable notebook has Marimo edit;
- a box "What "Open in Marimo" does": the three commands with study-relative files (`init.marimo`, display only) and the kernel line "Kernel: the engine environment <path>. Stop it with Ctrl+C in that terminal; the panel owns no process."

**Local launch (ADR 0004 amendment).** "Open in Marimo" sends `open_marimo {artifact}` (§8.1). The extension reads `status --json` once (never cached) and takes `view.deliverables.launch.<name>.argv` (CLI-CONTRACT §3, R7) when it has exactly the form `uv run --project <abs dir> marimo <mode> <file>` or `<abs python> -m marimo <mode> <file>`, with the notebook's mode and absolute path; otherwise it builds the same from the study's recorded CLI argv (`.hypotrail/agent.json`: `uv run --project <engine>/framework …`, or `<python> -m …`); otherwise nothing starts and a notice says so. The argv is started with `vscode.window.createTerminal({name, shellPath, shellArgs, cwd: S})`, an argument list, never a shell string and never typed into a terminal; the terminal is named "Hypotrail · marimo <mode> <file>" and is reused (shown again) while it is open for the same file. Nothing is written to the study. `lib/launch.js` holds the three launches; `scripts/check_layout.py` refuses any other terminal.

A "Regenerate the report and notebook" button (`data-write="render"`, v1) is shown when any generated artefact has status `stale` or `failed`, or the manifest is `not_rendered` (§7, W5). The button is absent in reviewer mode. "Checks of the deliverables" (§6.1.5) is a collapsed `<details>` at the end of this section (v1).

- OV-7. Each row shows its junior message (the engine message in the hover); "Open in Marimo (read)" and "(edit)" send `open_marimo` for the notebook and the workbench; the extension starts exactly `marimo run` / `marimo edit` in a named terminal with an argument list and reuses it (`extension.test.js`, `launch.test.js`). "Regenerate" is shown only under the conditions above.
- OV-8. After "Regenerate", the outcome lists each artefact's message from `render.artifacts`. Exit 3 is shown as "Regenerated with problems", not as a failure of the command.

#### 6.1.5 Health (F)

(Amended by WP-A5.) **Needs attention** (the former Health section) is rendered only when something is wrong: an interrupted, suspected, or late execution, an acknowledgement just made, or an alert (`sources_changed`, `result_integrity`). It shows nothing otherwise. The checks of the deliverables move to the Deliverables section. "Not yet defensible" becomes its own section, **What you cannot claim yet**: every `top` item and every `more` id **once**, each with a severity tag of one vocabulary (blocking, caveat, not final, context; `media/copy/junior.js` `SEVERITY`), blocking first; the text is the item's junior variant, or the panel's words for its id (the `more` ids have no text in the summary); the engine texts that differ are under "Details: the engine's wording". The execution card keeps the engine's `reason` under "Details". The rest of this section describes the parts as before.

- **Executions.**
  - Each `summary.executions.interrupted` and `suspected_interrupted` item is one card: "<activity>: the outcome is unknown. Nothing will be restarted."
  - The card has an empty textarea labelled "Your reply, in your own words".
  - Its hint reads: "Say that you know this run was interrupted and its outcome is unknown. 'ok' alone is not enough."
  - Its button is "Acknowledge in my words" (`data-write="acknowledge"`), disabled until text is typed (INV-5); see W6.
  - The card offers no rerun. A line reads: "To run it again, ask the agent in the chat."
  - `late` items are listed as "<activity>: a result was computed for a state that no longer holds; it is stored, not used."
- **Check findings.** A collapsed `<details>` titled "Checks of the deliverables".
  - Expanding it runs `check` (cached per revision). Each finding is shown with its `severity`, `code`, `message` verbatim, and `where`.
  - When `location.path` is a deliverable, an "Open" button opens it: an editor at `location.line` when it is set, or the browser at `#location.anchor` for the report.
  - The header shows `counts`, and "clean" or "N errors".
- **Not yet defensible.** `summary.not_yet_defensible.top` texts verbatim, and "More: <ids>" for `more`, in the warning colours of the mockup.

- HE-1. An acknowledgement typed in the panel runs the exact argv of W6. A bare "ok" is refused (`ambiguous_confirmation`, `bare_acknowledgement`), and the refusal is shown verbatim.
- HE-2. An execution card never has a "Restart" or "Run" button.
- HE-3. Check findings of the Bank fixture with an injected stale citation show it with a working "Open": a cited number edited in the HTML is a `value_mismatch` error on `reports/study.html` after the junior's Refresh (the checks are read again at the same revision, CR.1); `stale_number` is the code of a draft text or the conclusion. With the engine's currency, the edit and a deleted report also move `currency` without the Refresh, and a deleted report is not current (`test_he3_real_cli.py`, real CLI).

#### 6.1.6 Studies (K)

The extension discovers studies with `.hypotrail/agent.json` in:

- each workspace folder;
- each of its direct subfolders;
- the subfolders of those (depth ≤ 2).

It skips `node_modules`, `.git`, `.venv`, and dot-folders, and stops after visiting 500 folders, listing the studies it found in sorted order. No study is ever read beyond its `agent.json`, which is validated as in v0.

The header switcher is a button "Study: <folder name> ▾" that opens a VS Code quick pick: one entry per study, labelled with its folder name and described by its path, plus "Pick another folder...". Choosing another study disposes the current controller and watcher and opens the new one in the same panel. Only one study is open at a time.

- ST-1. Two studies in one workspace give a quick pick of both. Switching runs `status` on the new `--study` and disposes the old watcher.
- ST-2. A study more than two levels deep is not listed; "Pick another folder..." still reaches it.

### 6.2 Decisions (stage v1; v0 shows cards only)

Mockup: `Decision.dc.html`.

#### 6.2.1 Pending decision card (B)

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
- **Buttons.** "Ask the agent about this" only (H, from v0 since WP-E1): one press copies the fixed template of §6.8 with the question "Can you explain this proposal and what confirming it would change in my study?" (`data-ask-direct`), no modal; it never writes the study.
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

#### 6.2.2 Reconfirmation queue (B)

The queue comes from `decisions.reconfirm_queue`. It is rendered above the history when it is not empty, and titled "Needs your words again". Each item holds:

- the step title;
- `reason`, verbatim;
- "Previously: "<previous.user_words>" (<basis> · <channel>)";
- "Open the new proposal" when `open_proposal` is set;
- otherwise "No new proposal yet. Ask the agent to propose it again.", with "Ask the agent" (v2). For `policy` or `model_choice`, there is also "Choose in What if?" (v2).

- RQ-1. Every `reconfirm_required` decision is listed once, with its previous words verbatim.

#### 6.2.3 Decision history (B)

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

#### 6.2.4 Copy (Decisions)

| Situation | Text |
|---|---|
| No open proposal | "Nothing is waiting for your answer. The assistant proposes decisions in the chat." |
| Answer note (WP-E1) | "Answer in the chat" + "Confirm, change, or withdraw this proposal in the chat with your assistant. This panel records no decision." |
| Nothing invalidated (WP-E1) | "Confirming changes nothing already done." |
| Withdraw modal, Confirm success | withdrawn with W1 and W2 (WP-E1) |
| Delegation attempted | the refusal, plus the explanation "Your reply hands the choice to the assistant. A delegation is recorded in the chat, not in this panel." (v0) |

#### 6.2.5 Mode, bases, concerns, corrections (WP-A7)

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

### 6.3 EDA (stage v2)

Mockup: `EDA.dc.html`; WP-A7: `docs/design/companion-v0.2-mockups/eda.html`.

#### 6.3.0 Data card and quality (WP-A7)

The tab ("Data & EDA") opens on the data card, from the `data` read (§5; CLI-CONTRACT §11.1: development rows only, no exposure, no target rate):

- three facts: what one row describes (the case's observation unit and its status), the development rows and columns, and the target with its description and labels ("how often it occurs is shown below, on the training rows, after the split");
- the final test's junior line (`final_test.line`) with a sealed chip;
- the five fixed development rows, the target column first; a column the availability decision leaves out (`not_available`, `uncertain_excluded`) is marked ✗ with a legend (not colour only);
- the dictionary, grouped in the case's order: column, type (with unit, and the number of values of a non-numeric column), meaning (the description and each special value with its meaning and rows), "Known at the prediction moment?" (the junior's decision in words, else the case's statement and its status), missing cells, examples;
- "Show French labels" when the case has `labels.fr` (`description_fr`): the descriptions switch to French, marked `lang="fr"`; the button says "Show English labels" to switch back; it is view memory only. (v0.3, WP-E2: replaced by the "Meanings EN | FR" toggle of §6.3.0a, which follows the panel language.)

The `eda.quality` result (development rows, the target not read) follows the data card, titled by its question: missing cells and co-missing patterns, repeated rows, rare categories, and the ranges of numeric columns against a declared range, each figure cited.

- DA-1. The tab asks for `data` and shows the data card first, then the quality card, then the exploration banner and charts.
- DA-2. The five rows have the target first and mark each excluded column with ✗ and a legend.
- DA-3. The dictionary's groups and variables follow the engine's order, with each variable's missing count and special values.
- DA-4. "Show French labels" swaps every description that has a French label, marked `lang="fr"`, and back.
- DA-5. Without French labels there is no toggle.
- DA-6. The data card holds no cited figure and no percentage.

#### 6.3.0a The card pattern and the charts (v0.3, WP-E2)

Every EDA card follows the design system's pattern: an eyebrow (KIND · ROWS), the engine's question as the one visible title (the chart's name stays its accessible name only, R17), the column name and its meaning from the data card under the title (`data-column-meaning`), the chart, one sentence of finding, and a footer with one "Why?" disclosure (the term first, then every caveat: the non-causal sentence, the hollow-point and band legends, the engine's note and warnings) and a faint source line `Source · <activity> · <rid6>` that opens the result in Evidence (`data-chip`). Result ids never appear in the prose.

- **Distribution (R17).** A numeric column draws an HTML histogram with a y axis (the largest count, half of it, 0) and the bins' lower edges on the x axis (at most six labelled). When the engine marks the column skewed (`numeric.skewed`, CLI-CONTRACT §11.2), the exact zeros are a tile apart ("Exactly zero", their share and count, cited to `numeric.zeros`) and the positive values are drawn on the engine's log bins (`numeric.log_bins`), with "log scale" under the axis and the reason under "Why?". A stat row names the median, the IQR, the mean and the maximum (and the missing cells). Missing cells and special values are their own grey bars. A grouped column keeps its bars of counts and shares.
- **Rate or mean by group.** One row per group: a point at the group's value, its confidence interval with caps, the shuffled-outcome band behind it, the overall value as a dashed rule, and `n` next to the label; a small group is a hollow point and says "small". The finding is the null-band sentence.
- **Correlation matrix (R28).** From `eda.correlation` (development rows, predictors only, never a target look): the lower triangle in the engine's clustered order, positive (or unsigned) associations in the accent, negative ones in orange, the tint the strength, flagged pairs (|value| ≥ the engine's level) outlined (`data-flag`) and listed with their measure; above eight columns the numbers move to the hover and the values table. The finding names the count of flagged pairs; "Why?" defines collinearity and the three measures.
- **Run another chart.** Besides the per-column charts, the card offers the whole-study charts of the catalog (`eda.correlation`, W4 without a column, §7), saying that it reads no outcome.
- **No sideways scroll.** Every chart is an HTML grid (fluid); the dictionary and the five example rows are the only containers that may scroll sideways, inside their card (`data-scroll-ok`). The five rows are behind a "Five example rows" disclosure.
- **Dictionary meanings (R12 merged into R21).** The Meaning column follows the panel language when the case has `labels.fr`; a "Meanings EN | FR" segmented toggle (`data-french-toggle`, `data-meanings`) switches that column only, view memory only, with a one-line hint.

#### 6.3.1 Exploration amendments (WP-A7)

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

### 6.4 Evidence (stage v2)

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

#### 6.4.1 Final test first, development and final evidence apart (WP-B5)

Order of the tab: the final test, the exposure ledger, the development evidence, the variants and model families (v0.3, WP-K, §6.4.2), the final evidence, the diagnostics (when present), then the results and their detail, then the lineage.

- **Final test** (`data-ev="final-test"`, from the summary's `final_test` and `trials`, and the evidence's `final_test.evaluation`). Sealed: its rows "nobody has read", how they were set aside (the same share of each outcome, the latest rows in time order, ...), the development rows, that every figure below comes from rows that helped to choose, what must be confirmed before it can be opened (the choice, the variant, the success criterion, each with ✓ or ✗), and that opening it is a chat act: no button. Opened: the revision and the time of the evaluation, the junior's words quoted, and what was measured (the configuration in words, the final-test rows, the development rows of the refit). Changed after the opening: the decisions and results of `changed_after` in words. Absent: the study has no final test, so no figure is independent evidence. Then "Configurations evaluated: N" and one sentence on why the count matters.
- **Exposure ledger.** Each purpose in words, with what was done with the rows (`sealed`, `cross_validated_fit`, `out_of_fold_evaluation`, `out_of_fold_policy_selection`, `final_evaluation` added to §6.4); partitions as "development rows", "final test", "validation rows"; the final-test rows marked; the selection rows highlighted under cross-validation too.
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

#### 6.4.2 Variants and model families (v0.3, WP-K; WP-F1, ADR 0007, CLI-CONTRACT §14)

Read only, in the card pattern of §6.3.0a (an eyebrow, a question as title, the body, one finding, "Why?", a faint source line), after the development evidence. The engine's sentences (the one-standard-error rule, the optimism, the advice, the shortlist) are shown from their `texts` in the panel language; an engine text that exists in English only (the selection's `note`, a family's `note`) carries the "(en)" marker of §13.2 in a French panel.

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

### 6.5 What if? (stage v2)

Mockups: `WhatIf.dc.html` (binary) and `Regression.dc.html` (regression part).

**Banner on every state of this tab.** It uses the experiment colour and an icon: "**Experiment, not adopted.** Nothing here changes the study. Computed from saved predictions; no model is refitted." It carries `role="note"` and `data-experiment`.

#### 6.5.1 Binary: policy sandbox

- **Rule type.** A segmented control with Threshold and Capacity (`aria-pressed`).
- **Slider.**
  - Threshold: `<input type="range">` from 0 to 1, step 0.01. The label reads "Act on rows whose score is at least <t>".
  - Capacity: from 1 to `n` (the validation rows, from the current `policy.evaluation.values.n` or the `split` validation `n_rows`), step 1. The label reads "Act on the <k> highest-scored rows".
  - The initial position is the adopted or proposed rule when there is one, else the first evaluated rule.
  - The value is also editable in a number input bound to the slider.
  - `aria-valuetext` is "<k> rows" or "score at least <t>".
- **Under the slider (capacity).** "<k> of the <n> validation rows = <share> of rows. Extrapolate this as a rate, not as a count." The share is `k/n`, the only ratio the client computes. It is marked `data-literal="parameter"` and is a direct restatement of the junior's own parameter.
- **Comparison.** For each model (the logistic model and the baseline), bars of precision and recall from `preview.evaluations[rule][fit]`, with `selected`, `true_positives`, and the tie note when `tied_at_cut` is true ("Ties at the cut counted pro rata."). A `null` ratio is shown as "not defined (no row selected)".
- **Intervals.** After the slider is released, the panel requests `--intervals` for the current rule and shows the paired difference bar (E) with the sentence of §6.4.
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

#### 6.5.2 Regression: residual explorer

There is no slider. The panel shows:

- **Model selector.** The linear model or the training mean (radio).
- **Error comparison.** MAE with its interval for each model, and the paired difference with its interval (E), from `evaluate.regression`. The heading is "Error on <validation description> · <n> validation rows". For an ordinal split the validation description is "<column> ≥ <cutoff>" (for example, "model_year ≥ 79"), from the split values.
- **Residual summary.** The selected model's `residuals` quantiles, as a box plot: "Residual = observed − predicted; a positive residual means the model predicted too low."
- **Bias by group.** From `residuals_by` (the time column), bars of `mean_residual` per group on an axis centred at 0, with `small_count` hatched.
  - When every group's mean residual has the same sign, a fixed sentence follows: "Every group is <positive|negative>: the model predicts these rows <too low|too high> on average." It is followed by the `extrapolation` glossary term when the split is `ordinal_cutoff`: "**Extrapolation**: predicting outside the range seen in training."
- **Split limits.** The `split.values.groups` (when `shared_groups > 0`): "<shared_groups> <column> values appear on both sides of the split (<validation_rows_in_shared_groups> validation rows). These rows are not fully independent. Grouped splits are not supported in this version."
- **Ask the agent to propose this model (WP-E1; W3 withdrawn).** When `preview proposal model_choice --value=<slot>` is `proposable`, the draft is shown read only with "Ask the agent to propose this model", a copied question.

#### 6.5.3 Interactions and performance (What if?)

- Slider `input` events are debounced by 300 ms, and only the latest request is kept. A response whose `seq` is not the latest is dropped. At most one `preview policy` runs at a time.
- Results are cached per `(revision, canonical rule, intervals)`, keeping the last 64.
- Each CLI start costs about 0.5 to 2 s: `uv run` plus numpy and reading the predictions. While a preview is pending, the last values stay on screen, dimmed, with "Updating...". The slider never blocks.

| Id | Requirement |
|---|---|
| WI-1 | The banner is present in every state of the tab (loading, error, empty, populated) |
| WI-2 | Moving the slider never runs a mutating argv. A test records every argv during 20 slider moves: only `preview policy` appears, at most one per 300 ms window |
| WI-3 | (WP-E1) No control of the tab writes: a `propose` message is dropped and no `decide` process runs. "Ask the agent to propose this rule" is shown only for a canonical rule in `params.rules`, next to the draft's texts byte-identical to `preview proposal` |
| WI-4 | A regression study renders §6.5.2 and none of §6.5.1, and INV-12 holds |
| WI-5 | Values from `preview` are never shown outside this tab |

#### 6.5.4 Share rules and the gain curve (WP-B5)

- **Rule kinds.** Threshold, Capacity, and Share (`share:p`, 0.01 to 1 in hundredths; WP-B3): "Act on the top p of the scored rows". A share keeps its meaning on any number of rows; the engine turns it into a count.
- **Gain curve** (`data-gain`, an experiment surface). The engine's gain points (the top 5, 10 and 20 % of the scored rows) and every evaluated rule with the share it acts on (`capacity_share`), as points of the share of positives reached (recall) against the share of rows acted on, joined in order, with the random-selection diagonal; nothing is drawn between points as if measured. Marks: the junior's adopted or proposed rule, and the case's scenario share (`scenario_defaults.capacity_share`, read with `status --json`) labelled "exercise assumption" with the sentence that it is the exercise's assumption, not a team's figure. A table lists each point (cited) with "Try this share", which moves the slider (a preview, never a write).
- **Propose.** Since WP-E1 the panel proposes nothing: "Ask the agent to propose this" for a rule the engine evaluated (`proposable`), including a `share:p` rule; the panel never suggests the scenario share by itself.

| Id | Requirement |
|---|---|
| WI-6 | The gain curve shows only registered points (cited in its table), the diagonal, the junior's rule, and the scenario share labelled as an exercise assumption; no figure is computed by the panel |
| WI-7 | A `share:p` rule passes the protocol, the preview, and the draft, with the engine draft's texts byte for byte; a rule the engine did not evaluate is not proposable |

### 6.6 Learn & hand off (stage v3)

Mockup: `Regression.dc.html` (learning parts).

#### 6.6.1 Learning layer (G)

The learning layer is shown only when `learningLayer` is true.

**Glossary hovers.** Hovers apply to terms that the panel's own copy marks (`data-term="<id>"`), for example "Class imbalance", "MAE", or "Extrapolation".

- On hover, or on focus (keyboard), a tooltip (`role="tooltip"`, linked with `aria-describedby`) shows the `term` in bold, the `definition`, and the `example` segments when `example_status == "shown"`. The term comes first (AGENTS.md: the term first, then the contextual example).
- Escape closes the tooltip.
- A term absent from `explain.terms` (task filter) is not marked.

**Concept cards.** At the top of the tab and, when the layer is on, at the first appearance of a step in Overview, there is one card per plan step that is `current` or `awaiting_confirmation`. The card is built from `explain.steps[step]`:

- the concept term, then its definition;
- `context`, `interpretation`, and `consequence` segments.

A card is "seen" each time it is fully visible for 2 s; it is not counted twice in one panel session. After it has been seen **twice**, it is collapsed to a one-line link "Show the concept: <term>". A "Hide concept cards" preference hides every card. Both are stored locally (§10).

**Predict before you look.** For each `explain.predictions` item whose step is current or done and that the junior has not answered for this study:

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

#### 6.6.2 Hand off (I)

**Export.** A section "Hand the study over", with the button "Export a handoff pack" (`data-write="export"`, W7).

- The extension asks for a parent folder with a folder dialog (`showOpenDialog` with `canSelectFolders`, default `<study>/handoff/`) and passes `--out=<parent>/revision-<n> --expected-revision <n>`, so the engine refuses the export when the study moved since the panel showed revision n (decision CR.6). An engine that does not know the option refuses it (`invalid_arguments` naming `--expected-revision`); the panel never exports without it: the outcome is that refusal, the engine message verbatim, with the sentence that the study engine is older than the panel and must be updated (`lib/refusals.js`, `OLDER_ENGINE_EXPORT`). The default output is CC §7's.
- The outcome and "Open folder" name the folder the engine answered (`out`), never one the panel computed.
- The outcome lists the files written with their sizes, `warnings` in words (`recorded.warnings`, decision CI.3), and "Open folder" (`revealFileInOS`).
- With exit code 3, the outcome reads "The report was not current, so it is not in the pack. Regenerate it in Overview and export again if you need it."

**Reviewer mode.** A line explains it: "A reviewer can open this study read-only with "Hypotrail: open the study panel (reviewer, read-only)"."

- HO-1. Export runs the exact argv of W7. A non-empty target gives the `export_target_exists` refusal, verbatim.
- HO-2. Export stays in reviewer mode, and is the only write control there (decision CA.9, which answered the open question; WP-I aligned this text).
- HO-3. (Owner session 2026-10-26, L7, D15; wave W1 integration) At `done`, when the summary's `next_action.after_study` carries a junior text, the section shows "After the study" (`data-after-study`): that text verbatim (the handoff pack; the Azure ML export plan only when the chosen model is supported, else why not; no Azure job or endpoint ever run), and, only when `after_study.azureml.supported` is true, "The Azure ML export plan is available for this model: ask the assistant for it in the chat. This panel exports only the handoff pack." Read only: no control, no command, no new write (the panel's writes stay W4–W7). "Your next move" in Overview shows the same block under "Every step is done", at every stage.

#### 6.6.3 Session report (J)

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

### 6.7 Glossary, concept, and term marking in other tabs

Terms marked in the panel's own copy are listed in `media/terms.js`, a map from `data-term` id to the place where it occurs. A test checks that each id exists in the glossary of at least one task.

### 6.8 Agent bridge (H, stage v2; the decision card's button from v0, WP-E1)

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

## 7. Allowed writes (whitelist)

`A` is `agent.argv`, `S` is the study directory, `ID` is a fresh UUID v4, and `R` is the revision that the junior's view showed. The controller builds every argv. The webview sends only the identifiers and the typed words; it never sends argv fragments, restatements, or option names.

| W | Stage | Trigger | Exact argv | Pre-checks in the controller (any failure is `kind: "invalid"`, nothing runs) |
|---|---|---|---|---|
| ~~W1~~ | withdrawn (WP-E1) | Confirm in my words | `A decide confirm <pid> --user-words=<words> --channel webview --actor user --request-id ID --expected-revision R --json --study S` | `pid` matches `^p_[0-9]+$` and is in the last snapshot's open proposals; `words` is non-blank and at most 4000 characters; not reviewer; not busy |
| ~~W2~~ | withdrawn (WP-E1) | Withdraw (after a modal) | `A decide withdraw <pid> --request-id ID --expected-revision R --json --study S` | as W1, without words; the modal answered "Withdraw" |
| ~~W3~~ | withdrawn (WP-E1) | Propose this rule or model choice (after a modal) | `A decide propose <d> --value=<v> --restatement=<draft.restatement> --rationale=<draft.rationale> --channel webview --request-id ID --expected-revision <draft.revision> --json --study S` | `d` ∈ {`policy` binary, `model_choice` regression}; `v` is a canonical rule or a fit slot. The controller itself re-runs `preview proposal <d> --value=<v>` **immediately before**, requires `proposable: true` and `draft.revision == R`, and takes the texts from that draft only. The modal: "Create a proposal for "<title>": <v>? It is not a decision. You will confirm it in your own words in Decisions." where `<title>` is the plan step's title of the last summary ("Choose a decision policy", "Choose the model"; the decision id in words when the plan has none; decision CR.9), plus "It replaces the open proposal p_N." when `supersedes_proposal` is set. [Propose]. The draft read just before neither reads nor fills the cache |
| W4 | v2 | Run on training rows | `A run <activity> --column=<c> --channel=webview --request-id ID --expected-revision R --json --study S`; v0.3 (WP-E2): `A run eda.correlation --channel=webview --request-id ID --expected-revision R --json --study S` (no column) | `activity` ∈ the `eda_catalog.activities[].activity` values with `per_column: true` and `runnable: true` of the evidence read at revision R; `c` is one of that activity's `columns[].name`. Without a column: `activity` is a whole-study chart the panel knows (`eda.correlation` only, `lib/models/eda.js` `WHOLE_STUDY`) and its catalog entry has `per_column: false` and `runnable: true` |
| W5 | v1 | Regenerate | `A render --channel=webview --json --study S` | not reviewer; not busy |
| W6 | v1 | Acknowledge in my words | `A run --acknowledge-interruption <eid> --user-words=<words> --channel=webview --request-id ID --expected-revision R --json --study S` | `eid` is in the snapshot's `executions.interrupted` or `suspected_interrupted`; `words` is non-blank and at most 4000 characters |
| W7 | v3 | Export a handoff pack | `A export handoff --out=<chosen folder>/revision-<R> --channel=webview --expected-revision R --json --study S` (CR.6; never without `--expected-revision`: an older engine's refusal of the option is shown as such) | `R` is the last snapshot's revision; the folder comes from the VS Code dialog; it is not inside `S/.hypotrail` |

**Channel (v0.3, WP-J, R35).** Every write of W4-W7 carries `--channel=webview`: the engine records it on the run or the acknowledgement (the reservation's parameters) and as a `channel_action` event for a render or an export, and `status --summary --digest` lists them in `digest.channel_actions`, so the agent can say what was done from the panel. It changes no identity, no result and no revision of its own.

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

A unit test enumerates the argv builder module and asserts that exactly the four builders W4–W7 exist (seven before WP-E1).

**Outcome handling (all writes).**

| Result | Panel |
|---|---|
| `ok: true`, exit 0 | Success region: what was recorded (`user_words` verbatim for W1 and W6, the proposal id for W3, the slot and status for W4, the artefact messages for W5, the files for W7), then a refresh |
| `ok: true`, exit 3 | Success with problems: the artefact messages, verbatim |
| `ok: true`, `run.status` `late_not_promoted` | "The result was computed but not used: the study changed while it ran. Nothing in the study changed." |
| `ok: false`, any exit | The refusal (INV-8). Exit 4 adds "An execution has an unknown outcome." |
| no JSON, timeout, start failure | "The outcome is unknown: the refreshed panel shows whether anything was recorded." (v0) |
| replayed | It cannot happen (new id per submission). If it does, it is shown as success with "(replayed, no effect)" |

**Timeouts.** Reads: 30 s. W5, W6, and W7: 120 s. W4: 300 s, because EDA loads the dataset with pandas.

## 8. Webview ↔ extension message protocol (`hypotrail.panel/2`)

- **Envelope.** Every message is a JSON object `{v: 2, type, ...fields}`.
- **Unknown or invalid messages.** A message with an unknown `type`, an extra field, a wrong type, or `v !== 2` is dropped and counted in `diagnostics.ignored`. It is never answered.
- **Validation.** Both sides validate with one schema table in `lib/protocol.js`. The webview copy is `media/protocol.js`, generated by WP-0's script `lib/protocol.js --emit-webview`. A test asserts that the two are identical.
- **v0.** The v0 messages (implicitly `/1`) are retired. The v0 tests are migrated to `/2`, not deleted.

### 8.1 Webview → extension

| `type` | Fields (all required unless marked `?`) | Stage |
|---|---|---|
| `ready` | — | v0 |
| `refresh` | — | v0 |
| `load` | `view` ∈ `summary`, `decisions`, `eda`, `evidence`, `whatif`, `explain`, `check`, `session_report`, `data` (WP-A7), `scenario` (WP-B5), `trials` (v0.3, WP-K); `resultId?` (64 hex, `evidence` only); `since?` (int ≥ 0, `summary` only). `eda`, `evidence`, and `whatif` share the cached `evidence` read and differ by their model function | v1 |
| `confirm`, `withdraw` | withdrawn by WP-E1: dropped as unknown | — |
| `preview_effects` | `proposalId`, `revision` | v1 |
| `preview_policy` | `rules` (1–4 strings matching `^(threshold:(0(\.\d+)?\|1(\.0+)?)\|capacity:[1-9]\d{0,6})$`), `intervals` (bool), `seq` (int ≥ 0) | v2 |
| `draft` | `decisionId` ∈ `policy`, `model_choice`; `value` (string ≤ 64); `revision` | v2 |
| `propose` | withdrawn by WP-E1: dropped as unknown | — |
| `run_eda` | `activity` (`^eda\.[a-z_]+$`), `column` (string, 1–200 characters), `revision` | v2 |
| `render` | — | v1 |
| `acknowledge` | `executionId` (string, 1–100 characters, `^[A-Za-z0-9_.-]+$`), `words`, `revision` | v1 |
| `open_marimo` | `artifact` ∈ `notebook`, `editable`, `workbench` (WP-A5, ADR 0004 "local launch": `marimo run` of the generated notebook, `marimo edit` of the editable copy or workbench, in a VS Code terminal; not a write; in reviewer mode both edit launches are refused with a notice) | v0 |
| `open_artifact` | `artifact` ∈ `report`, `notebook`, `editable`, `workbench`; `resultId?` (the report at `#r-<rid>`, or the generated notebook at the line that names the result; not the editable copy or workbench); `line?` (int ≥ 1, an editor deliverable at a check finding's line; not the report; not with `resultId`) | v0 (+ `resultId` and `line` v1, decision CI.3) |
| `navigate_external` | `kind` ∈ `reveal_export`; `path` (string, must equal the last export's `out`) | v3 |
| `ask_agent` | `about: {kind ∈ result, decision, proposal, step, limit, execution, term; id (string ≤ 100)}`, `question` (string ≤ 2000), `mode` ∈ `copy`, `insert` | v0 (v2 before WP-E1) |
| `export_handoff` | `revision` | v3 |
| `switch_study` | — | v1 |
| `learn_set` | `key` ∈ `seen`, `prediction`, `prefs`, `reset_predictions`; `id` (string ≤ 100, `^[a-z0-9_.:-]+$`); `value` (for `seen`: no value; `prediction`: a choice id ≤ 40; `prefs`: `{hideCards?: bool}`) | v3 |

### 8.2 Extension → webview

| `type` | Fields | Notes |
|---|---|---|
| `init` | `stage`, `reviewer` (bool), `learningLayer` (bool), `chatInsert` (bool), `task` (`binary`\|`regression`\|`null`), `study?` (the study key of §10, 16 hex; never the path; CR.2), `marimo?` (`{kernel, notebook, editable?, workbench}`: the engine environment and the three launch commands with study-relative files, display only; WP-A5), `language?` (`auto`\|`en`\|`fr`, the setting `hypotrail.companion.language`; v0.3, WP-E2) | sent once after `ready`, and again when a setting changes |
| `snapshot` | `revision`, `currency?` (CR.1), `model: SummaryModel` | after every summary read |
| `view_data` | `view`, `revision`, `currency?` (the version the model was read at, CR.1), `model` (the model of §9 for that view), `resultId?` | |
| `load_error` | `view` (or `null` for the summary), `message`, `detail` | |
| `busy` | `busy` (bool), `op` (W id or `read`) | |
| `outcome` | `op` (`W4`–`W7`; `W1`–`W3` before WP-E1), `kind` ∈ `ok`, `ok_with_problems`, `not_promoted`, `refused`, `failed`, `invalid`, `cancelled`; `target?` (pid, eid, slot); `revision?`; `refusal?` (`{code, reason, engineMessage, human, details: [string], humanFr?, detailsFr?: [string]}`; the French pair since v0.3, WP-K); `recorded?` (`{userWords?, channel?, decisionId?, proposalId?, slot?, status?, files?: [{path, bytes}], out?, warnings?: [string]}`); `artifacts?` (`[{name, status, message}]`); `message?` | |
| `preview_policy_result` | `seq`, `revision`, `currency?`, `model: PolicyPreviewModel` | dropped by the webview when `seq` is not the latest it sent |
| `effects` | `proposalId`, `revision`, `currency?`, `model: EffectsModel` | |
| `draft_result` | `decisionId`, `value`, `revision`, `currency?`, `model: DraftModel` | |
| `learn_state` | `prefs`, `seen: {cardId: count}`, `predictions: {questionId: choiceId}` (this study only) | after `ready` and after each `learn_set` |
| `navigate` | `{tab, kind, id}` | deep link and "go to a result" |
| `notice` | `text`, `politeness` ∈ `polite`, `assertive` | copy confirmation, invalid link, etc. |

**Protocol tests (frozen by WP-0).** For every type: one valid example, one example with an extra field, and one with a wrong type, in both directions. Plus a round-trip test: every model fixture sent as `view_data` passes webview validation.

## 9. Models (extension-side projections)

The models are pure functions in `lib/models/*.js`, from CLI payloads to plain objects. They hold only strings, numbers, booleans, arrays, `null`, and objects. Unknown payload keys are ignored, and a missing key becomes `null` or `[]`. Each model function throws a `ModelError` for a wrong `schema`. The webview renders models and nothing else.

| Model | Function | Input | Keys (top level) |
|---|---|---|---|
| `SummaryModel` | `toSummaryModel(summary)` (`lib/models/summary.js`, extends v0 `toModel`) | `hypotrail.summary/1` | `study`, `revision`, `task` (`null` in v0; from `plan` step ids: `model_choice` ⇒ regression), `recap[5]`, `goal`, `currentStep`, `plan[{id, title, status, pause, basis}]`, `moments[{id, title, steps}]`, `pauses`, `nextAction`, `artifacts[{name, label, path, status, message}]`, `artifactsStatus`, `proposals[{proposalId, decisionId, decisionTitle, value, restatement, revision, origin, holds, resolvedNotes}]`, `holds`, `executions{interrupted, suspected, late, active}`, `notYetDefensible{top, more}`, `alerts[{id, text}]`, `digest{since, sinceTime, gapMinutes, items[{revision, time, kind, text, keptFits, refit}], truncated}`, `waitingCount`, `currency` (CR.1) |
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

**Segments.** A segment is rendered as a text node or a `<data value data-result-id data-path>` element with a title of "result <rid8>... · <path>". This is the same convention as the report, so a number in the panel can be traced the same way.

**Number formatting.** It follows the `format` given by the engine (`int`, `pct0`–`pct2`, `f1`–`f4`) through one function `media/format.js`. That function is a port of `cite.fmt_number`, with a test that compares its output with Python's for 200 values.

## 10. Local storage

| Store | Keys | May hold | Must not hold |
|---|---|---|---|
| `vscode.setState` (webview, per panel) | `drafts{pid: {text, revision}}`, `ackDrafts{eid: {text, revision}}` (the words and the revision at which the junior started typing them, CR.3), `askDraft`, `tab`, `recapCollapsed`, `evidenceFilter`, `selectedResult`, `study` (the study key of `init`, CR.2), `language` (`en`\|`fr`, the header's EN \| FR choice; v0.3, WP-E2) | draft words the junior is typing (never sent until submitted), view navigation | anything read back as a decision, or a number |
| `context.globalState` (extension) | `hypotrail.learn.prefs = {hideCards: bool}`; `hypotrail.learn.seen = {cardId: count ≤ 99}` (at most 500 ids); `hypotrail.learn.predictions = {studyKey: {questionId: choiceId}}` (at most 50 studies, oldest removed first) | learning-layer preferences, seen cards, prediction answers | study values, words, revisions, proposal or result ids, paths |
| `context.workspaceState` | not used | — | — |

- `studyKey` is the first 16 hexadecimal characters of the SHA-256 of the absolute study path, so the path itself is not stored.
- `cardId` is `<task>:<step id>` or `term:<id>`.
- `check_layout.py` keeps forbidding `localStorage` and `indexedDB`.
- A unit test asserts that `globalState.update` is called only with these three keys, and with values that pass their schema.
- Draft words in `setState` are deleted on a successful confirmation, a successful acknowledgement, a withdrawal, or when the proposal is no longer open (v0 behaviour, extended to acknowledgement drafts).
- Drafts belong to one study (decision CR.2). `init.study` names it; when it differs from the stored `study` (the study switch reloads the same webview with its state, and a state without a key is treated as another study), `drafts`, `ackDrafts`, `askDraft`, and `selectedResult` are dropped before anything is rendered. A draft of another form than `{text, revision}` is dropped when the webview starts.

## 11. Performance

| Item | Budget and rule |
|---|---|
| CLI calls on open | 1 (`status --summary --digest`) |
| CLI calls on a watch event | 1 summary read, plus the reads of the visible tab whose data is not at the new version (revision and currency, CR.1): one for most tabs; two for Decisions at v2 and later, `decisions` and `evidence` (its chips cite current results; the `evidence` read is shared with EDA, Evidence, and What if?), plus `preview effects` for each visible card. Each read runs once per version; a watch event that moves nothing reads only the summary. Hidden tabs reload lazily when shown (decision CR.5) |
| Coalescing | v0 coalescing applies to every data key: concurrent requests for one key at one revision share one process. A request made while one is running for the same key runs once more after it (v0 `again`) |
| Cache | Per data key and version (`<revision>:<currency>`, CR.1). The entries of another version are dropped when a new summary arrives, except `preview:*` (64 most recent). The explicit Refresh and every write empty every non-preview entry (§5, refresh rule). The draft is cached like any read (the uncached read before W3 went with W3, WP-E1) |
| Debounce | Watch events: 250 ms (v0). Slider: 300 ms. Variable select: no CLI call |
| Concurrency | At most 2 read processes at once (summary plus one tab read); `preview policy`: at most 1; writes: 1 and exclusive (reads wait) |
| Payload size | `evidence` with 200 results is expected under 1 MB. `MAX_BUFFER` is raised from 8 MB to 16 MB. A payload over the limit is a `load_error` "The study's evidence is too large to show (more than 16 MB)." |
| Measured, not asserted | The integration test records the wall time of each read command on the synthetic study and writes it to the test output, as ADR 0002 asks. There is no invented threshold. A regression of more than 2x between two recorded runs is a review item for the integrator, not a failure |
| Rendering | The webview re-renders only the tab whose model changed, keeps focus (v0) and scroll position, and renders at most 200 registry rows. More rows need "Show more" |

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
- **Clipboard.** It is written only by the agent bridge, with the template of §6.8. No other control, and nothing in the webview (`navigator.clipboard`), writes it; Evidence's "Select the id" only selects the text (decision CI.5, `test/invariants.test.js`).

## 13. Accessibility and theme

**Structure.** One `h1`, the panel title, visually hidden. Each tab panel has an `h2`, and sections have `h2` or `h3`. Landmarks are `header`, `nav` (the tablist), `main`, and `footer`.

**Keyboard.** Every control is reachable with Tab. The tabs use the arrow keys. Escape closes tooltips and modals, and focus returns to the opener. Modals trap focus. Sliders follow the native `range` keyboard; Page Up and Page Down move by 10 % of the range.

**Announcements.** One polite live region carries outcomes and "Updated to revision N". Refusals, load errors, and alerts carry `role="alert"`, as in v0.

**Charts.** Every chart has:

- an accessible name ("Outcome rate by job, training rows");
- a "Show values" toggle that renders the same data as a `<table>`;
- small counts that are indicated by text, not by colour or pattern alone;
- contrast of at least 3:1 for marks and 4.5:1 for text against the background, in both themes.

**Motion.** Highlight transitions are disabled under `prefers-reduced-motion: reduce`.

**v0.3 (WP-E2): the design system.** `media/css/tokens.css` and `media/css/core.css` implement the validated system of `docs/design/companion-v0.3-mockups/ds.css`, which supersedes the token tables below (kept for the record; their names stay as aliases):

- **Two token layers.** Layer 1: the host's `--vscode-*` values with the Light Modern / Dark Modern defaults as fallbacks. Layer 2: `--ht-fg` from `editor-foreground`; surfaces derived with `color-mix` (`--ht-surface` 2.5 % of the foreground into the editor background, `--ht-sunken`, `--ht-line`, `--ht-line-strong`, `--ht-faint`); six semantic hues (accent, warn, bad, seal, info, ok) and the chart roles (mark, reference grey, band, grid, axis, the diverging pair) fixed per theme kind on `body.vscode-light`, `body.vscode-dark`, `body.vscode-high-contrast` and `body.vscode-high-contrast-light` (outside VS Code, `prefers-color-scheme`). In High Contrast the hues are bright, the surfaces are the background, and every card, chip and button takes the theme's contrast border; `forced-colors` keeps the system colours.
- **Scale.** Spacing 4–32, type caption 11 (uppercase label), meta 12, body 13, title 15, page 18, stat 24, tabular numbers; radii chips 4, cards 8, pills 999; no shadow except the next move's 3 px accent ring.
- **One card pattern** (eyebrow, title as a question, figure, one sentence, footer with "Why?" and a faint source line), **filled status chips** with a dot, **notes** as tinted blocks.
- **Recap.** Collapsed by default on every tab except the Overview, which shows where the study stands itself.
- **Charts are fluid.** Bars, histograms, interval rows, the confusion 2×2 and the correlation matrix are HTML grids sized by CSSOM custom properties (§12): they follow the width of the panel. SVG is kept for curves (gain, calibration, quantile plot), drawn at the width of their container and redrawn when it changes (ResizeObserver), so one SVG unit is still one CSS pixel and chart text is never scaled up; any SVG is at most as wide as its container. **No chart and no page scrolls sideways at any width**; the only sideways scroll is inside the dictionary and the five example rows of the data card. This replaces the v0.2 rule "a narrow panel scrolls a chart sideways".
- **A11Y-4 (v0.3).** `test_webview_gate.py` (WP-E3; WP-E2 started it at two widths) runs every tab on the captured payloads under Light Modern, Dark Modern and High Contrast, at 1280, 900 and 420 px, in English and in French: no element's right edge passes the viewport or its card (`section`, `article`, `.card`) outside `data-scroll-ok`; every visible text at one of the six type sizes (caption, meta, body, title, page, stat, read from the tokens on `<body>`), chart text at 10–13 px, monospace only for identifiers (three words at most); no raw result id, proposal id, rule token, `key:value` token or `snake_case` identifier in the prose (allowed: the faint source lines, code, the junior's quoted words, file names, and the study's column names, which engine texts quote); nothing underlined, numbers and prose words alike; the style-attribute rule of §12; no CSP violation. Per theme, the text tokens (`--ht-fg`, `--ht-muted`, `--ht-faint`, `--ht-link`, `--ht-accent-ink`, the warn, bad and seal inks) keep 4.5:1 against the page and the card surface (7:1 for the main and muted text in High Contrast), each chip ink 4.5:1 on its tint, and both button texts 4.5:1 on their buttons. Identifiers the panel itself shows (the result slots and the activities of the exposure ledger) are set as code.
- **Pixel baselines (v0.3, WP-E3).** `test/baselines/*.png`: each tab of the split Bank capture at 420 and 900 px, Light Modern, Dark Modern and High Contrast, English and French, first viewport (800 px) plus the main chart of the EDA, Evidence and What if? tabs (108 images, about 8 MB). Rendering is pinned (DejaVu Sans and DejaVu Sans Mono, installed fonts only; reduced motion, no animation; a fixed date, locale and time zone; device scale 1). Chromium compares the images itself (two canvases, no image library): a pixel differs when a channel moves by more than 24, and more than 0.1 % of differing pixels fails; the capture, the baseline and a diff image go to `clients/vscode-companion/.local/baseline-diff/`. `--update-baselines` rewrites only the baselines that differ, and every baseline change is reviewed by the owner from those diff images before it is committed (CONTRIBUTING). Without the pinned fonts (Linux, `fc-match`) the pixel tests skip with a warning; the structural gate always runs.

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
- `@media (forced-colors: active)`: buttons, tags, cards, steps keep a border in system colours; chart marks use `CanvasText` and `GrayText`; the current step and the selected tab use `Highlight`.
- Charts follow the width of the panel (v0.3, WP-E2; above): chart text is 11 px and never scaled up, and nothing scrolls sideways. Intervals sit on a drawn axis, with 0 marked and labelled when the chart compares to 0.
- Below 600 px every table becomes a list of cards (each cell labelled by its column); the tab bar wraps (v0.3; it scrolled sideways before); the page never scrolls sideways at 420 px.
- A11Y-3. `test_webview_themes.py` runs the views on the captured payloads under the Light+, Dark+ and High Contrast variable sets (`test/themes.py`) at 900 and 420 px: chart text ≤ body text + 2 px; primary buttons have a visible border in High Contrast and under forced colours; no sideways scroll at 420 px; no `agent` text visible in any tab.

- A11Y-1. axe-core is **not** added, because it would be a dependency. Instead, a Playwright test asserts that every interactive element has an accessible name, every `img`-like SVG has `role="img"` and a name, there is no positive `tabindex`, and focus is visible (outline present) for each control.
- A11Y-2. Computed contrast of text tokens against `--ht-bg` is at least 4.5:1 in both fallback themes. This is tested by computing WCAG contrast in the test.

### 13.2 Panel language (v0.3, WP-E2, R21)

English is the source language; the panel ships a French translation of its own copy (AGENTS.md, owner decision 2026-10-20).

- **Setting.** `hypotrail.companion.language`: `auto` (default; follows the study language, the summary's `language`, CLI-CONTRACT §3), `en`, or `fr`. It reaches the webview in `init.language` (§8.2).
- **Header toggle.** An EN | FR segmented control next to Refresh (`data-language-toggle`, `data-language`, `aria-pressed`). Pressing it switches the panel at once and keeps the choice in `vscode.setState` (`language`, §10); it sends no message and writes nothing to the study. The choice overrides the setting until the panel's state is cleared.
- **Copy.** `media/copy/*.js` holds the English strings; `media/copy-fr/*.js` (loaded after them, `lib/html.js`) holds the same keys in French under `Hypotrail.copyFr`. The frame swaps every `Hypotrail.copy.<view>` for the French table merged over the English one before it renders; `document.documentElement.lang` follows. `test/copy-fr.test.js` fails when an English key has no French counterpart of the same kind, or when a French string holds a digit outside a placeholder or an exclamation mark.
- **Engine texts.** Engine junior texts (questions, notes, warnings, limits, digest texts, deliverable messages, the final-test line, the recap's goal) are shown as the engine sent them. In a French panel, a text whose language is not French (the study language) carries a faint "(en)" marker and `lang="en"` (`data-en-marker`, `HT.components.engineText`). The engine's French variants are WP-C's.
- **Engine texts in both languages (owner session 2026-10-26, L3; R4, decision D4b).** The engine now gives the junior texts the panel shows in both languages: `status --summary --digest` `texts` (step titles, moments, the next action, the choice options, the limits, the deliverables' messages, the recap, the digest, the goal, and each open proposal's restatement), `evidence` `texts` and `question_junior` of each `eda.*` result, and the data card's `texts` (row unit, groups, availability sources, special values' meanings, from the case's translation sidecar). The panel keeps the summary it read (`state.raw`) and shows the table of its own language (`core.localize`), so the EN | FR toggle switches the engine's texts as well as the panel's copy. The "(en)" / "(fr)" marker (`HT.components.engineText`) now marks a text in either direction: an engine text left in the other language (a stored fit or diagnostic note, an EDA text with no French form), and the agent's restatement when the agent gave none in the panel's language, with the line "(wording of the chat, in French)" / "(formulation du chat, en anglais)" (`copy.decisions.chatWording`). The Decisions tab's step titles follow the switch through the summary's `texts`; the Evidence tab shows the limits in the junior's words (`junior_text`, before L3 their English `text`). The texts the engine gives in the study language only (an `evidence` headline, the Learn tab's `explain` texts) are marked with their language in a panel of the other language. A study created before L3, or a study whose case has no current sidecar, shows the case's own words, marked.
- **Not translated.** The extension's own messages (`lib/refusals.js`, VS Code notifications and quick picks) stay English in v0.3. **Amended by WP-K (v0.3):** they are translated too. A refusal carries `human` and `details` in English and `humanFr` and `detailsFr` in French (`lib/refusals.js`); the panel shows the one of its language (the header toggle included). The extension's notifications, quick pick and dialogs, and the notices the handlers post, follow the setting: `en` or `fr`, else (`auto`) the open study's language, else VS Code's display language (`lib/l10n.js`); the header toggle is view state the extension never sees, so a notice follows the setting. The engine's own refusal message stays verbatim, in the engine's language. The text copied for the chat (§6.8) stays English.

## 14. Task variants and vocabulary

| Element | Binary | Regression |
|---|---|---|
| Third decision | `policy` | `model_choice` |
| What if? | policy sandbox (§6.5.1) | residual explorer (§6.5.2) |
| EDA target card | `eda.target_rate` | `eda.target_summary` |
| EDA by-column | `eda.rate_by` "Outcome rate by value" | `eda.mean_by` "Target mean by value" |
| Interval bars | precision, recall, volume, deltas | MAE, RMSE, deltas |
| Pause 3 label | "business trade-off" | "model choice" |
| Ledger "Rule selection" row | present when recorded | never (purpose not used) |

**Task detection.** The task comes from `evidence.task` and `decisions.task`. `SummaryModel.task` is derived from the plan's step ids until the summary carries `task`. That is an open question: adding `task` to the summary is additive and cheap, and WP-E1 may add it.

**Forbidden vocabulary.** INV-12 applies to the panel's own strings, which live in `media/copy.js`, keyed by task. The Playwright test of §6 runs the regex on the rendered DOM of all tabs with the Auto MPG fixtures.

## 15. Copy catalogue

All panel-owned strings live in `media/copy.js` (webview) and `lib/refusals.js` (refusal explanations, v0). They are English. They never contain digits, except through placeholders filled from models. They never suggest confirmation words. The strings quoted in this document are normative. New strings follow these rules:

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
| `data-tab` | tab buttons and panels | `overview`, `eda`, `decisions`, `evidence`, `whatif`, `learn` |
| `data-stage` | any stage-gated element | `v1`, `v2`, `v3` |
| `data-write` | every control that triggers W4–W7 | `run_eda`, `render`, `acknowledge`, `export` (`confirm`, `withdraw`, `propose` before WP-E1) |
| `data-proposal-card`, `data-restatement`, `data-hold` | decision cards | proposal or note id (v0) |
| `data-outcome`, `data-code`, `data-reason`, `data-engine-message`, `data-human` | outcome regions | v0 |
| `data-result-id`, `data-path`, `data-value` | cited numbers | engine values |
| `data-experiment` | What if? banner and preview values | — |
| `data-literal` | client-derived displays | `axis`, `parameter`, `age` |
| `data-term` | glossary-marked words | glossary id |
| `data-eda-card` | EDA cards | slot |
| `data-ledger-row` | ledger rows | `<purpose>:<partition>` |
| `data-tab-lead` | the lead sentence of a tab (v0.3) | tab id |
| `data-language-toggle`, `data-language` | the header's EN \| FR toggle (v0.3) | `en`, `fr` |
| `data-en-marker` | the "(en)" marker of an English engine text in a French panel (v0.3) | — |
| `data-ov="guide"` | "How this panel works" (v0.3) | — |
| `data-zero-tile`, `data-log-scale`, `data-numeric-line` | a skewed distribution's zero tile, log scale note, stat row (v0.3) | — |
| `data-pair`, `data-flag`, `data-collinear` | correlation matrix cells, flagged pairs, the finding (v0.3) | `<a>\|<b>` |
| `data-whole` | a whole-study chart of "Run another chart" (v0.3) | activity |
| `data-scroll-ok` | the only containers that may scroll sideways (v0.3) | — |

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
