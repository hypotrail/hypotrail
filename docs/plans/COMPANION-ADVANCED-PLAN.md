# Advanced companion: implementation plan for parallel agents

Status: **plan, not started.**

- Scope: [ADR 0004](../decisions/0004-companion-advanced.md)
- Behaviour: [COMPANION-ADVANCED.md](../specs/COMPANION-ADVANCED.md), the **spec**
- Engine interfaces: [CLI-CONTRACT-COMPANION.md](../specs/CLI-CONTRACT-COMPANION.md), **CC**

The plan follows the v0.1 orchestration rules (V0.1-DECISIONS O1–O2):

- every worktree agent first resets onto the integration branch tip;
- only the integrator merges, with `--no-ff`, into the integration branch.

## 1. Order of work

```text
Phase A (serial)        WP-0  frozen interfaces, skeletons, stubs, contract tests (integrator)
Phase B (parallel)      WP-E1  WP-E2  WP-E3        engine
                        WP-U1  WP-U2  WP-U3  WP-U4  WP-U5   client views (against fixtures)
Phase C (serial merges) WP-I   merge E1 → U1, U2 → stage v1 checklist
                               merge E2, E3 → U3, U4 → stage v2 checklist
                               merge U5 → stage v3 checklist
```

**Fixtures first.** The client work packages never wait for the engine. They build against the frozen fixtures of WP-0 and the stub CLI. The integrator enables their real-CLI integration tests when the engine work package they depend on is merged.

| Client WP | Needs engine WP |
|---|---|
| U1, U2 | E1 |
| U3, U4 | E2, E3 |
| U5 | E2 |

## 2. Frozen interfaces (WP-0 writes them first)

WP-0 is done by the integrator, or by one agent under the integrator, before the fan-out. Its subparts 0a (engine) and 0b (client) may run in parallel. It **writes no feature**. It freezes the following.

### 2.1 Engine side (0a)

1. **Commands registered.**
   - `cli.EXTENSIONS` gains `decisions`, `evidence`, `explain`, and `export`. Stub modules (`cmd_decisions.py`, `cmd_evidence.py`, `cmd_explain.py`, `cmd_export.py`) parse the CC arguments and refuse with `unsupported_capability` (`details.command`).
   - `cmd_preview.py` becomes the dispatcher of CC §3: `kind` ∈ `policy`, `effects`, `proposal`, with stub modules `preview_effects.py` and `preview_proposal.py`.
   - `status` accepts `--digest`: it refuses without `--summary`, and refuses with `unsupported_capability` until WP-E1 lands.
   - `decide propose` accepts `--channel` and refuses a non-`chat` value with `unsupported_capability` until WP-E1 lands.
2. **Constants.**
   - `state.PER_COLUMN_SLOT_PREFIXES` gains `'eda.distribution:'`.
   - `state.PROPOSAL_OPTIONAL_KEYS` gains `'origin'`.
   - `texts.CONTENT_FILES` gains `digest`, `drafts`, `evidence`, `learn`, with stub files that carry their `schema` header only.
   - `sessionlog` gains the option whitelist entries of CC R5.
3. **Contract tests.** There are three files, one per engine WP. Every test is marked `xfail(strict=True, reason='WP-Ex')`. Each engine WP removes **its own** markers, never another's, so an implemented feature that keeps its marker fails the gate.

   | File | Tests | WP |
   |---|---|---|
   | `framework/tests/study/test_contract_companion_e1.py` | C1, C2, C3, C9: key lists in order, refusal codes, R1 (tree digest before and after on a read-only tree), R3 (`sys.modules` after the import), the preview equals the confirmation invalidation | E1 |
   | `framework/tests/study/test_contract_companion_e2.py` | C5, C6, C7, C10 `location` | E2 |
   | `framework/tests/study/test_contract_companion_e3.py` | C4, C8, C10 anchors | E3 |

   The non-`xfail` part, which passes at once, asserts that the stubs refuse with `unsupported_capability`. It also asserts that `status --summary` without `--digest` is unchanged: byte-identical to a golden output on the synthetic study.

### 2.2 Client side (0b)

1. **`lib/protocol.js`.** The message table of spec §8, with `validateIncoming`, `validateOutgoing`, and the envelope `v: 2`. It also has an `--emit-webview` mode that writes `media/protocol.js`.
2. **`lib/cli.js`.**
   - Every read argv of spec §5.
   - The **seven write builders** W1–W7 of spec §7. They are frozen: the signatures and the exact argv order.
   - `run()` with per-op timeouts and `MAX_BUFFER` 16 MB.
3. **`lib/controller.js`.** The router: `handlers` is a map from message type to handler, filled by `lib/handlers/*.js` modules that each export `{types: {...}}`. The controller owns:
   - the per-key, per-revision cache;
   - coalescing;
   - the read concurrency limits;
   - the exclusive write lock;
   - the reviewer refusal;
   - stage gating: a message whose stage exceeds the active stage is ignored;
   - the generic write outcome mapping of spec §7.

   Handlers call `ctx.read(key, argv, modelFn)` and `ctx.write(op, argvFn, recordFn)`. They never call `cli.run` directly.
4. **`lib/flag.js`.** `isEnabled` (v0), plus `stage()`, `learningLayer()`, `chatInsert()`, and `reviewer()` with their environment overrides.
5. **`lib/html.js`.** It concatenates, in this fixed order:
   - CSS: `media/css/tokens.css`, `core.css`, then `media/css/*.css` in alphabetical order;
   - JS: `media/protocol.js`, `media/format.js`, `media/core.js`, `media/components/*.js`, `media/copy/*.js`, then `media/views/*.js` in alphabetical order.

   Everything is inlined under one nonce, with the v0 CSP unchanged. `html.js` refuses a file that contains `</script` or `</style`, as v0 does.
6. **`media/core.js`.** The webview runtime:
   - `el()` and `svg()`;
   - `register(viewName, {tab, stage, render(model, ctx), onMessage?})`;
   - the tabs, frame, recap strip, alert strip, live region, modal, and tooltip host;
   - the `send()` message whitelist;
   - the `vscode.setState` helpers.

   Views never call `acquireVsCodeApi`.
7. **`media/components/*.js`.** These are implemented in WP-0, because every view uses them. Their API is frozen:

   ```js
   bars(container, {items:[{label, value, valueText, small, cited:{resultId, path, value}|null}], max, rule:{value, label}|null, title, unit})
   intervalRows(container, {rows:[{label, point, low, high, pointText, intervalText}], zero:boolean, title})
   histogram(container, {bins:[{low, high, count, countText}], title, axisLabel})
   boxplot(container, {min, q25, median, q75, max, texts, title})
   valuesTable(container, {columns, rows, caption})     // the "Show values" alternative
   segments(container, segments)                        // text + <data> citations
   ```

8. **`media/format.js`.** The port of `cite.fmt_number`, with a cross-test against Python.
9. **`media/css/tokens.css`.** The tokens of spec §13. `core.css` holds the frame and the shared components.
10. **Test infrastructure.**
    - `test/fake-vscode.js` gains `globalState`, `env.clipboard`, `window.registerUriHandler`, `commands.executeCommand`, `env.openExternal` with a URI fragment, and `window.showOpenDialog`.
    - `test/conftest.py` provides the Playwright harness: it loads the document with a stub `acquireVsCodeApi`, records CSP violations, posts a model, and reads posted messages.
    - `test/fixtures/` holds hand-written payloads for every schema of CC, binary (Bank-like values from the mockups) and regression (Auto MPG values). `test/fixtures.test.js` checks them against the frozen key lists of CC.
11. **Migrated v0 tests.** `unit.test.js`, `integration.test.js`, and `test_webview_browser.py` move to protocol v2 with the same assertions. No assertion is weakened, and none is removed.
12. **`test/invariants.test.js`.** INV-1 to INV-5 and INV-13 as static and behavioural checks:
    - only `cli.js` requires `child_process`;
    - exactly seven write builders exist;
    - no builder emits `--basis`, `--delegation-scope`, `note`, `fit.`, `split`, `policy.evaluate`, or `evaluate.regression`;
    - the webview never sets `.value` of a words textarea.
13. **`package.json` and `check_layout.py`.**
    - New settings: `stage`, default `"v0"`; `learningLayer`; `chatInsert`, default `false`; `reviewer`, default `false`.
    - New commands: `openReviewer` and `goToResult`.
    - The activation events of spec §3.1.
    - `check_layout.py` asserts the new defaults and activation events. It keeps the forbidden-API regex, and adds `workspaceState`, which is not used (spec §10).

**WP-0 file ownership.**

- Engine:
  - `framework/mlkit/study/cli.py`
  - `cmd_preview.py`
  - the stubs `cmd_decisions.py`, `cmd_evidence.py`, `cmd_explain.py`, `cmd_export.py`, `preview_effects.py`, `preview_proposal.py`
  - `state.py` (constants only)
  - `texts.py`
  - `sessionlog.py`
  - `content/{digest,drafts,evidence,learn}.yaml` (stubs)
  - `framework/tests/study/test_contract_companion_e{1,2,3}.py`
- Client:
  - `clients/vscode-companion/lib/{protocol,cli,controller,flag,html,cache}.js`
  - `lib/models/summary.js` (moved from `lib/model.js`)
  - `media/{core,protocol,format}.js`
  - `media/components/*.js`
  - `media/copy/core.js`
  - `media/css/{tokens,core}.css`
  - `test/{fake-vscode.js,conftest.py,fixtures/,fixtures.test.js,protocol.test.js,invariants.test.js,cli-argv.test.js}`
  - the migrated v0 tests
  - `package.json`, `extension.js` (skeleton)
  - `scripts/check_layout.py`

  `media/panel.js` and `media/panel.css` are removed. Their v0 behaviour moves to `media/views/overview.js` and `media/views/decisions.js` as **minimal v0 skeletons**, which WP-U1 and WP-U2 then own.

**Exit of WP-0.** The full gate is green, with the `xfail` tests reported as `xfailed`. The v0 behaviour works unchanged at `stage: v0`. Every client WP can open a panel at its stage with fixtures and see an empty view registered under its tab.

## 3. Work packages and file ownership

**Rules.**

- A WP may create or modify **only** the files listed for it.
- It may read every file.
- It must not edit a file owned by another WP, or a WP-0 file, except WP-0 files listed as "extend" for it.
- A needed change to a frozen interface is a request to the integrator, made in the WP's report. It is never made in place.
- New test files follow the WP's prefix.

### WP-E1: engine reads for orientation and decisions (CC C1, C2, C3, C9)

| Files | Notes |
|---|---|
| `framework/mlkit/study/commands.py` | `confirmation_plan()` factored out of `_confirm`; the propose `channel` parameter (optional, omitted when `chat`); `origin` stored |
| `framework/mlkit/study/cli.py` | `--digest` implemented; `decide propose --channel` passed through |
| `framework/mlkit/study/view.py` | `moments`, `pauses`, `last_session`, `digest`, `SESSION_GAP_MINUTES`, `DIGEST_MAX_ITEMS`; `open_proposals[].origin`; optionally `task` in the summary (an open question, spec §14) |
| `framework/mlkit/study/state.py` | validation of the optional `origin` (the constants already exist from WP-0) |
| `framework/mlkit/study/cmd_decisions.py` | replaces the stub |
| `framework/mlkit/study/preview_effects.py` | replaces the stub |
| `framework/mlkit/study/content/steps.yaml` | `moments`, `regression_moments` |
| `framework/mlkit/study/content/digest.yaml` | the sentences of CC §1.4 |
| `framework/tests/study/test_companion_digest.py`, `test_companion_decisions.py`, `test_preview_effects.py`, `test_propose_channel.py` | new |
| `framework/tests/study/test_contract_companion_e1.py` | extend: remove its own `xfail` markers only |

**Tests.**

- Unit: digest kinds and texts for each action; the gap rule; `--since` bounds.
- Simulated: the real CLI on the Bank walkthrough (`test_walkthrough.py` helpers) and the Auto MPG walkthrough (`test_regression_walkthrough.py` helpers):
  - every confirmation is preceded by `preview effects`, and the test asserts equality with `result.invalidation`;
  - read-only tree digest;
  - import check;
  - the regression vocabulary scan of every digest text;
  - replay of a pre-C9 request id.

### WP-E2: evidence, explain, export, check locations (CC C5, C6, C7, C10 locations)

| Files | Notes |
|---|---|
| `framework/mlkit/study/cmd_evidence.py`, `cmd_explain.py`, `cmd_export.py` | replace the stubs |
| `framework/mlkit/study/dependencies.py` | `effects_for_mutation()` (pure, on a deep copy) |
| `framework/mlkit/study/read.py` | read-only helpers if needed (`Study.result_ids()`, `Study.exposure_records()` already exists); keep the AST rule (no writer import) |
| `framework/mlkit/study/cmd_check.py` | `location` in findings |
| `framework/mlkit/study/content/evidence.yaml`, `content/learn.yaml`, `content/glossary.yaml` (`example` fields) | no digits outside templates |
| `framework/tests/study/test_companion_evidence.py`, `test_companion_explain.py`, `test_export_handoff.py`, `test_check_location.py` | new |
| `framework/tests/study/test_contract_companion_e2.py` | extend: its own markers only |

**Tests.**

- Bank and Auto MPG walkthroughs:
  - the ledger equals `exposure_summary`;
  - the `impacts` rows of CC §5 acceptance;
  - `values: null` for stale results;
  - explain examples are `needs_results` before the results exist and `shown` after;
  - `check --text` on the joined explain texts is clean;
  - export determinism (two folders, identical bytes); `check --text handoff.md` is clean; a stale report is omitted, with exit 3; `export_target_exists`; `read_only`; the study tree is unchanged outside `--out`.
- Content lint: no digits.

### WP-E3: EDA distribution, proposal drafts, report changes (CC C4, C8, C10 anchors)

| Files | Notes |
|---|---|
| `framework/mlkit/study/eda.py` | `distribution()`, `DISTRIBUTION_BINS` |
| `framework/mlkit/study/activities.py` | `DISTRIBUTION`, `PER_COLUMN`, `TASK_ACTIVITIES`, `MODULES`, plan and column roles |
| `framework/mlkit/study/preconditions.py` | the activity preconditions of `eda.distribution` |
| `framework/mlkit/study/preview_proposal.py` | replaces the stub |
| `framework/mlkit/study/content/drafts.yaml` | the templates of CC §4 |
| `framework/mlkit/study/content/activities.yaml` | display specification of `eda.distribution` (both tasks) |
| `framework/mlkit/study/render_html.py`, `notebook_view.py`, `render_notebook.py` (if needed) | distribution display; annex anchors `r-<id>`; "Proposed from the companion" for `origin.channel == "webview"` |
| `framework/tests/study/test_eda_distribution.py`, `test_preview_proposal.py` | new |
| `framework/tests/study/deliverables/test_render_distribution.py` | new |
| `framework/tests/study/deliverables/test_html_offline.py` | extend: one anchor per cited result; no `vscode:` or `command:` URI |
| `framework/tests/study/test_contract_companion_e3.py` | extend: its own markers only |

**Tests.**

- Bank: `age` (numeric), `pdays` (a special value), and `job` (categorical); exposure columns are `[column]`, partition `train`.
- Auto MPG: `mpg` (the target) and `model_year` (discrete).
- A split change makes the distribution stale.
- High cardinality triggers `high_cardinality_grouping`.
- Every draft of the walkthroughs is proposed successfully on a temporary study; an unevaluated rule is not `proposable`; the drafts are clean under `check --text`.
- The report renders the distribution with cited numbers, and `check` is clean.

### WP-U1: Overview, health, studies, reviewer (spec §6.1, §3.3 reviewer; stage v1)

| Files | Notes |
|---|---|
| `clients/vscode-companion/media/views/overview.js`, `media/css/overview.css`, `media/copy/overview.js` | |
| `clients/vscode-companion/lib/models/summary.js` (extend: WP-0 moves v0 `lib/model.js` there and updates its importers), `lib/models/check.js` | `toSummaryModel`, `toCheckModel` |
| `clients/vscode-companion/lib/handlers/overview.js` | `ready`, `refresh`, `load: summary/check`, `render` (W5), `acknowledge` (W6), `open_artifact`, `switch_study` |
| `clients/vscode-companion/lib/study.js` | discovery at depth ≤ 2 (spec §6.1.6) |
| `clients/vscode-companion/test/overview.test.js`, `test/studies.test.js`, `test/test_webview_overview.py` | |

**Tests.**

- Node unit, with the fake `vscode` and a fake CLI: OV-1 to OV-8, HE-1 to HE-3, ST-1, ST-2, RV-2 (reviewer refuses every write type).
- Playwright: the map, the digest, the deliverables, the execution card (empty textarea; button disabled until text), and the reviewer DOM, which has no `data-write`.
- No CSP violation.

### WP-U2: Decisions (spec §6.2; stage v1)

| Files | Notes |
|---|---|
| `clients/vscode-companion/media/views/decisions.js`, `media/css/decisions.css`, `media/copy/decisions.js` | |
| `clients/vscode-companion/lib/models/decisions.js`, `lib/models/effects.js` | |
| `clients/vscode-companion/lib/handlers/decisions.js` | `confirm` (W1), `withdraw` (W2), `preview_effects`, `load: decisions` |
| `clients/vscode-companion/lib/refusals.js` | extend the v0 table with `export_target_exists` and the W3, W4, W6 refusal contexts; never suggest words |
| `clients/vscode-companion/test/decisions.test.js`, `test/test_webview_decisions.py` | |

**Tests.**

- DC-1 to DC-6, RQ-1, DH-1, DH-2.
- The Playwright DOM never contains the restatement inside the textarea.
- An injection fixture for words and restatements.

### WP-U3: Evidence and What if? (spec §6.4, §6.5, E; deep links; stage v2)

| Files | Notes |
|---|---|
| `clients/vscode-companion/media/views/evidence.js`, `media/views/whatif.js`, `media/css/evidence.css`, `media/css/whatif.css`, `media/copy/evidence.js`, `media/copy/whatif.js` | |
| `clients/vscode-companion/lib/models/evidence.js`, `lib/models/whatif.js`, `lib/models/preview.js`, `lib/models/draft.js` | |
| `clients/vscode-companion/lib/handlers/evidence.js` | `load: evidence/whatif`, the `open_artifact` report anchor, the notebook hint |
| `clients/vscode-companion/lib/handlers/whatif.js` | `preview_policy` (debounce, `seq`, cache), `draft`, `propose` (W3, with the re-read draft) |
| `clients/vscode-companion/lib/uri.js` | deep-link parsing and validation (CC §11); `goToResult` id resolution |
| `clients/vscode-companion/test/evidence.test.js`, `test/whatif.test.js`, `test/uri.test.js`, `test/test_webview_evidence.py`, `test/test_webview_whatif.py` | |

**Tests.**

- EV-1 to EV-6 and WI-1 to WI-5.
- WI-2: argv recording during simulated slider events, with fake timers.
- WI-3: the propose argv texts are byte-identical to the draft fixture.
- The Auto MPG vocabulary scan of both tabs.

### WP-U4: EDA (spec §6.3; stage v2)

| Files | Notes |
|---|---|
| `clients/vscode-companion/media/views/eda.js`, `media/css/eda.css`, `media/copy/eda.js` | |
| `clients/vscode-companion/lib/models/eda.js` | |
| `clients/vscode-companion/lib/handlers/eda.js` | `load: eda`, `run_eda` (W4 with the catalog check) |
| `clients/vscode-companion/test/eda.test.js`, `test/test_webview_eda.py` | |

**Tests.** ED-1 to ED-6. The hatch and the "small" text. The non-causal caption is present on every by-column card. The Auto MPG cards.

### WP-U5: Learn & hand off, agent bridge (spec §6.6, §6.8, §10; stages v2 and v3)

| Files | Notes |
|---|---|
| `clients/vscode-companion/media/views/learn.js`, `media/css/learn.css`, `media/copy/learn.js`, `media/terms.js` | tooltips: a `core.js` tooltip host API (frozen in WP-0); `terms.js` marks terms |
| `clients/vscode-companion/lib/models/explain.js`, `lib/models/session_report.js` | |
| `clients/vscode-companion/lib/handlers/learn.js` | `load: explain/session_report`, `learn_set`, `export_handoff` (W7), `navigate_external` |
| `clients/vscode-companion/lib/handlers/bridge.js`, `lib/bridge.js` | `ask_agent`: the template, clipboard, guarded `executeCommand` |
| `clients/vscode-companion/lib/localstore.js` | the `globalState` schema and limits of spec §10 |
| `clients/vscode-companion/test/learn.test.js`, `test/bridge.test.js`, `test/localstore.test.js`, `test/test_webview_learn.py` | |

**Tests.**

- LE-1 to LE-4, HO-1, HO-2, SR-1, AB-1, AB-2.
- The `globalState` key whitelist and size limits.
- Predictions never reach `cli.run` (spy).

### WP-I: integrator (after the fan-out)

| Files | Notes |
|---|---|
| `clients/vscode-companion/extension.js` | URI handler, the reviewer and go-to-result commands, settings change events |
| `clients/vscode-companion/package.json`, `README.md` | |
| `clients/vscode-companion/test/integration-v1.test.js`, `integration-v2.test.js`, `integration-v3.test.js`, `test/capture_fixtures.py`, `test/fixtures/captured/` | real CLI, end to end per stage |
| `docs/specs/CLI-CONTRACT.md` (§8.7 pointer), `framework/tests/study/test_contract_freeze.py` (new schema names) | in the commit that merges WP-E1 |
| `docs/handoff/IMPLEMENTATION.md`, `docs/plans/V0.1-DECISIONS.md` (a new "CA" section of decisions), `CONTRIBUTING.md` (gate lines), `docs/architecture/REPOSITORY.md`, `scripts/check_layout.py` | |
| `docs/specs/*COMPANION*.md`, `docs/decisions/0004-*.md` | clarifications requested by WPs; status lines |

**Integration tests (real CLI, temporary studies outside the repository, paths with spaces and quotes).**

- **v1.** On the synthetic binary case:
  - init; propose through the CLI;
  - the panel shows the digest; preview effects; confirm a typed answer; a bare "ok" is refused;
  - a hold blocks, with `effects.blocked`;
  - a stale revision; render; a fault-injected interrupted run (`HYPOTRAIL_TEST_HOOKS=1`, `HYPOTRAIL_FAULT=run_after_reserve`), then an acknowledgement with typed words;
  - reviewer mode refuses every write.
- **v2.** On the synthetic binary case:
  - EDA request for a feature distribution: the exposure ledger gains train rows only;
  - a slider preview; an unevaluated rule cannot be proposed;
  - after the agent (the test) runs `policy.evaluate --rule capacity:K`, the panel proposes it (W3) and confirms it with typed words;
  - `origin.channel == "webview"` in the state.

  On the synthetic regression variant: the residual explorer, a model-choice draft and proposal, and the vocabulary scan of the captured models.
- **v3.** The export pack with `check --text handoff.md` clean, `explain` examples, and a session report with the log on.

`capture_fixtures.py` regenerates `test/fixtures/captured/` from these runs. `test/fixtures.test.js` asserts that the hand-written fixtures and the captured ones have the same key sets.

## 4. Test plan summary

| Layer | Tool | Who | Runs in the gate |
|---|---|---|---|
| Engine unit and simulated | pytest, real CLI processes | E1, E2, E3 | yes: `framework/tests/study` |
| Engine contract | pytest, strict `xfail` until implemented | WP-0 writes; each E-WP clears its own | yes |
| Client unit | `node --test`, fake `vscode`, fake CLI | WP-0, U1–U5 | yes: `node --test clients/vscode-companion/test/*.test.js` |
| Client integration | `node --test`, real CLI on temporary studies | WP-0 (v0 migrated), WP-I | yes, skipped when `framework/.venv` is missing (v0 rule) |
| Webview browser | Playwright, offline, real document and CSP, stub `acquireVsCodeApi` | WP-0 harness, U1–U5 one file each | yes: `uv run --project framework python -m pytest -q -p no:cacheprovider clients/vscode-companion/test` |
| Layout | `python3 scripts/check_layout.py` | WP-0, WP-I | yes |
| Real VS Code | manual checklist (§6) | WP-I with the owner | no; it is a stage exit criterion |
| Observation | `docs/research/OBSERVATION-PROTOCOL.md` | owner | no; it is a stage exit criterion |

**Gate commands, unchanged from CONTRIBUTING.** Every WP runs all of them, fully green, before its report:

```sh
python3 scripts/check_layout.py
uv run --project framework python -m pytest -q framework/tests/test_pilot_revision.py framework/tests/test_quality.py framework/tests/test_discovery.py framework/tests/test_reliability.py framework/tests/test_classical.py framework/tests/test_env_smoke.py framework/tests/test_synthetic_case.py framework/tests/study framework/tests/acceptance
node --test clients/vscode-companion/test/*.test.js
uv run --project framework python -m pytest -q -p no:cacheprovider clients/vscode-companion/test
```

**Labels.** None of these tests is a VS Code session or a Copilot session. Reports say "simulated" and "not run inside a real VS Code" until §6 is done.

## 5. Definition of done (every WP)

1. **Files.** Only the owned files were changed. A diff check against the ownership map is part of the WP report.
2. **Gate.** The gate of §4 is fully green. No test was weakened, skipped, or deleted, and no strict `xfail` was left in place for an implemented feature.
3. **Requirements covered.** Every requirement id of the WP's spec sections has at least one test, named in a table in the WP report (id → test).
4. **Rules kept.**
   - No new runtime dependency.
   - No network module, shell, `exec`, `vscode.lm`, `localStorage`, or `indexedDB`.
   - No digits in content files outside templates.
   - English only.
5. **Engine WPs.**
   - R1–R5 tested for each read addition.
   - `status --summary` without `--digest` stays byte-identical.
   - No existing contract key was renamed or removed.
6. **Client WPs.**
   - The Playwright file reports no CSP violation.
   - The Auto MPG vocabulary scan passes for the WP's tabs.
   - Every write control carries `data-write` and is absent in reviewer mode.
7. **Report.** The WP report lists its deviations from the spec, requested interface changes, and open questions. The integrator records accepted ones as "CA.n" decisions.

## 6. Real VS Code checklist (WP-I, per stage)

These checks run in a VS Code 1.90 or later Extension Development Host, on a study created outside the repository, in light and dark themes. Record the results in `docs/acceptance/runs/companion-<stage>-<date>.md`.

1. Flag off: the command and a `vscode://` link both show "Companion disabled (feature flag)". No process starts (Process Explorer).
2. Untrusted workspace: refused.
3. CSP: the developer tools console shows no violation. VS Code's injected default styles apply, or their absence is recorded (CW.10's open review point).
4. Theme tokens: contrast is legible in Light+, Dark+, and High Contrast.
5. The watcher after a chat write (atomic rename of `state.json`): the panel refreshes once.
6. v1: confirm, withdraw, acknowledge, Regenerate, the study switch, and reviewer mode.
7. v2: slider latency (record the median of 10 moves), an EDA run, Propose, a deep link printed in the chat, "Show in report" with a fragment, and the `chatInsert` behaviour (inserted, **not sent**) in the Copilot chat.
8. v3: the export folder, learning-layer persistence across a reload, and a `globalState` dump.

## 7. Risks to the plan

| Risk | Mitigation |
|---|---|
| Fixtures drift from real payloads | The captured fixtures and the key-set test (WP-I); engine contract tests on key order |
| `core.js` or the components need a change during the fan-out | A request to the integrator; a small WP-0 follow-up merged first, which the client WPs rebase on |
| E1 and E3 both need view or render changes | Ownership is split by file: view.py goes to E1, render_html.py to E3. The `origin` label in the report reads a fixture until E1 merges |
| The real-CLI latency makes the integration tests slow | One temporary study per test module, reused; walkthrough helpers; record times |
