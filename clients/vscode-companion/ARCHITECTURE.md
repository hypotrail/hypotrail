# Study panel: architecture

The panel is one more client of the `hypotrail` CLI (ADR 0002). It has no build step and no runtime dependency. Behaviour is specified in [COMPANION-ADVANCED.md](../../docs/specs/COMPANION-ADVANCED.md) (the spec), the engine interfaces in [CLI-CONTRACT-COMPANION.md](../../docs/specs/CLI-CONTRACT-COMPANION.md) (CC), and the work packages in [COMPANION-ADVANCED-PLAN.md](../../docs/plans/COMPANION-ADVANCED-PLAN.md). WP-0 froze the interfaces below; WP-I extended them at the packages' request (decisions CI.1 to CI.17 in [V0.1-DECISIONS](../../docs/plans/V0.1-DECISIONS.md#companion-integration-ci)). A change to one is a request to the integrator.

## Modules

```text
extension.js            vscode API only: flag and trust checks, commands, URI handler, panel, host functions
lib/flag.js             enabled, stage (v0-v3), learningLayer, reviewer, chatInsert (hidden, forced off: CR.8), env overrides
lib/study.js            study discovery and agent.json validation (the CLI argv)
lib/watch.js            fs.watch of .hypotrail/ (debounced), no polling
lib/cli.js              THE ONLY child_process user: read builders (READS), write builders W4, W5, W7 (WRITES), run()
                        (W1-W3 withdrawn in v0.3, ADR 0004 decision 8; W6 withdrawn by R31, decision 12;
                        check_layout refuses a `decide` write and an acknowledgement builder)
lib/launch.js           the three Marimo launches (WP-A5, ADR 0004 "local launch"): marimo run of the generated
                        notebook, marimo edit of the editable copy and workbench; argv from status --json or agent.json
lib/protocol.js         hypotrail.panel/2 schema table and validators; emits media/protocol.js
lib/controller.js       router: validation, stage gate, reviewer refusal, summary, load dispatch,
                        cache + coalescing + read limits, exclusive write lock, outcome mapping
lib/cache.js            CLI payloads per read key and version (<revision>:<currency>, CR.1); preview:* keys in a bounded list
lib/handlers/<view>.js  {types, loads, commands, onReady}: one module per view group
lib/models/<view>.js    pure payload -> model functions (to<Name>Model) + FIXTURES
                        (WP-A7: lib/models/data.js, the data card of the Data & EDA tab, read with `data`;
                        WP-B5: lib/models/scenario.js, the case's teaching share, read with `status --json`;
                        v0.3 WP-K: lib/models/trials.js, the variant budget and the family shortlist, the
                        same `status --json` read, cache key `view`)
lib/refusals.js         refusal explanations (never suggest words), English and French (v0.3, WP-K)
lib/l10n.js             the extension's own words (notifications, notices) in English and French (WP-K)
lib/uri.js              deep-link parsing (a decoded query: study=<path as is>, CR.11) and result-id input (WP-U3)
lib/bridge.js           the agent bridge's template, clipboard, guarded chat command (WP-U5)
lib/localstore.js       the globalState schema and limits of spec §10 (WP-U5)
lib/html.js             the document: media concatenated in a fixed order under one nonce
media/protocol.js       generated copy of lib/protocol.js (never edit)
media/format.js         port of cite.fmt_number (cross-tested with Python)
media/core.js           webview runtime: frame, tabs, live region, modal, tooltip, send(), setState
media/terms.js          glossary marks and hovers; Hypotrail.askAgent / askButton (the one "Ask the agent" helper)
media/components/*.js   bars, intervalRows, histogram, boxplot, valuesTable, figure, segments, cited, curve (WP-B5);
                        v0.3 (WP-E2): card, why, source, chip, lead, engineText, corr, fluid; the charts are
                        HTML grids sized by CSSOM custom properties, curves redrawn at their container's width
media/components/lesson.js the lesson style (spec §6.0, 2026-10-27): intro, notion(s), fold, more, reading,
                        trans, trap, quote, withGuide/currentGuide (a view's frame of evidence merged into
                        every figure's "Why this chart" and guided reading)
media/css/tokens.css    the board tokens per VS Code theme class (dark board, white board, High Contrast keeps
                        the editor's colours; no class: prefers-color-scheme), redefined on paper surfaces
media/copy/<view>.js    panel-owned English strings (copy/core.js for the frame; copy/lesson.js for the lesson texts)
media/copy-fr/<view>.js the French translation of the same keys (v0.3, WP-E2, R21; test/copy-fr.test.js)
media/copy/junior.js    the junior-facing copy keyed by kind/code/id, and decision values in words (WP-A5,
                        two-layer copy, COMPANION-ADVANCED §15.1)
media/views/<view>.js   one view per tab, registered with Hypotrail.register
media/css/*.css         tokens.css (theme), core.css (frame, components), <view>.css
```

Only `lib/cli.js` starts a process. The one exception is not a child process of the panel: `extension.js` opens a VS Code terminal for the three Marimo launches that `lib/launch.js` accepts (`createTerminal` with `shellPath`/`shellArgs`), and `scripts/check_layout.py` refuses any other terminal. Every read runs with `cli.READ_ENV` (`HYPOTRAIL_SESSION_LOG=0`) merged over the host's environment, so the opt-in session log never records the panel's polling; writes inherit the environment (COMPANION-ADVANCED §5). Only `extension.js` requires `vscode`, so the controller and handlers run under `node --test` with a fake CLI.

## Message flow

```text
webview (media/*)                         extension host (lib/*)                    CLI
HT.send({type, ...})  -- {v: 2, ...} -->  controller.handle(raw)
                                            protocol.validateIncoming   (invalid: dropped, diagnostics.ignored)
                                            stage gate (stageOf > stage: dropped, diagnostics.ignored)
                                            reviewer + write type -> outcome invalid
                                            ready/refresh -> summary read --------------> status --summary [--digest]
                                            load -> handlers' loads[view] -> ctx.read --> (payload cached per read key and version,
                                                                                       projected by each loader's model)
                                            other -> handlers' types[type](message, ctx)
                                                       ctx.write(op, {argv, record}) -> W4, W5, W7 argv (exclusive)
render(model, ctx) <-- {v: 2, ...} -----  ctx.post(...) validated by protocol.validateOutgoing
```

Extension to webview: `init` (stage, reviewer, learningLayer, chatInsert, task, study key), `snapshot` (SummaryModel), `view_data` (a view's model), `load_error`, `busy`, `outcome` (`op` W4, W5, W7, `kind`), `effects`, `preview_policy_result`, `draft_result`, `learn_state`, `navigate`, `notice`. The webview drops anything that fails validation.

## Frozen interfaces

- **Handlers** (`lib/handlers/<name>.js`, discovered in file order): `types: {messageType: async (message, ctx)}`, `loads: {view: {stage?, when?(settings), key(message), argv(cli, agent, message), model(payload)}}` (`key` names the CLI read: loaders of one command share it and its cached payload, as EDA, Evidence and What if? share `evidence`; `when` false refuses the load like a stage gate), `commands: {name: async (args, ctx)}` (extension commands such as `go_to_result`), `onReady: async ctx`. A type, view, or command claimed twice throws at start. `ready`, `refresh`, `load`, and `load: summary` belong to the controller.
- **ctx**: `agent`, `settings`, `snapshot()`, `stageAtLeast(s)`, `post(message)`, `read(key, argv, modelFn, {group?, timeoutMs?, cache?})` → `{ok, model, revision, currency, payload, cached?} | {ok: false, message, detail, refusal?}` (the payload is cached per key and version, `<revision>:<currency>` of the last snapshot, CR.1; `cache: false` neither reads nor fills it; `modelFn` runs on every answer), `write(op, {target, argv(requestId), record(payload)})` → the outcome (or null when refused before running; one CLI process per write, never a retry, CR.6; every write empties the non-preview cache), `refresh()`, `invalid(op, message, target)`, `host` (openArtifact, pickFolder, openFile, revealInOS, writeClipboard, executeCommand, notify, globalState, switchStudy), `exists`, `artifactPath(name)`, `cli`, `refusals`, `uuid`, `log`, `diagnostics`.
- **Models**: each `lib/models/<name>.js` exports `to<Name>Model(payload)` (throws `ModelError` from `lib/models/common.js` on a wrong schema) and `FIXTURES` (names under `test/fixtures/`). `test/protocol.test.js` round-trips every one.
- **Views**: `Hypotrail.register(name, {tab, stage, views?, outcomes?, render(model, ctx), onMessage?(message, ctx), band?(model, ctx)})`. `band` (lesson style, 2026-10-27) returns what the view shows above the tabs on every tab (the Overview's journey rail and next move); its ctx carries `tab`, the tab open. `model` is the SummaryModel. `views` lists the data views the controller loads when the tab is shown and the snapshot moved past them; `ctx.data(view)` returns `{revision, model, resultId}`. `outcomes` lists the write ops whose outcome the view renders itself (`ctx.outcome(target)`, `ctx.renderOutcome(o)`); the frame's live region shows the others. `onMessage` returning `false` for a forwarded message (effects, preview_policy_result, draft_result, learn_state) skips the re-render.
- **View ctx**: `init`, `stage`, `reviewer`, `task`, `learningLayer`, `chatInsert`, `snapshot`, `data`, `error`, `busy`, `busyOp`, `busyTarget`, `send`, `load(view, extra)`, `version()` and `fresh(entry)` (whether data `{revision, currency, epoch}` is at the snapshot's version, CR.1: use them, never compare revisions), `stamp(message, epoch?)`, `epoch()` (the count of explicit Refreshes), `retry(view)` (forget a failed load so it can be asked again), (no `drafts` since R31: the confirmation drafts went with W1 and the acknowledgement drafts with W6), `ui` (setState keys of spec §10 only), `wordsArea`, `outcome`, `renderOutcome`, `el`, `svg`, `format`, `components`, `copy`, `gate(stage, node)`, `atLeast`, `modal`, `tooltip`, `navigate`, `placeholder()`, `rerender()`.
- **Components** (`Hypotrail.components`): `bars`, `intervalRows`, `histogram`, `boxplot`, `valuesTable`, `figure`, `segments`, `cited`, `textWidth`, with the signatures in each file's header and in the plan §2.2. `bars` and `intervalRows` size their text columns to their texts (`labelWidth`, `valueWidth`, `textWidth` override); `histogram` and `boxplot` take cited cells `{text, cited}` for edges and axis texts.
- **Frame helpers**: `Hypotrail.askButton(ctx, {kind, id}, shown, {label?, attrs?, question?, stage?, direct?})` (stage v2 unless `stage`; a modal, then `ask_agent`; `direct` copies the ready question at once, WP-E1), `Hypotrail.terms.mark(text, id)` (a glossary-marked word; its id must be in `terms.MAP`), `Hypotrail.registered()` (the registered views, for tests).
- **Messages added by WP-I**: `open_artifact.resultId` (v1; report anchor or notebook line) and `open_artifact.line` (v1; an editor deliverable at a finding's line); `outcome.recorded.warnings` (W7).
- **Fields added by CR**: `currency?` on `snapshot`, `view_data`, `effects`, `draft_result`, `preview_policy_result` (CR.1); `init.study?` (CR.2).

## Rules every view keeps

- Two-layer copy (COMPANION-ADVANCED §15.1, INV-16): primary content is the panel's copy keyed by the engine's kind, code, or id, or an engine junior text; an `audience: agent` text, a raw id, or a recorded token goes to a hover or a "Details" disclosure.
- Status and severity tags use one vocabulary (`ht-status ht-st-*`, `ht-tag ht-sev-*`), coloured by the `--vscode-charts-*` tokens; buttons and cards take their borders from `--ht-button-border` and `--ht-card-border`.

- Study text goes in with `text` or text nodes; `el()` refuses `style`, `innerHTML`, and non-function handlers.
- Words the junior types go only in `ctx.wordsArea({kind, key, ...attrs})`; no other textarea exists (INV-5, `test/invariants.test.js`).
- SVG colours are palette names (`Hypotrail.PALETTE`); sizes are attributes or `style.setProperty`; no `style` attribute.
- Every write control carries `data-write`; the frame removes all of them in reviewer mode.
- A stage-gated element carries `data-stage` (or comes from `ctx.gate`); a later-stage tab is absent, not disabled.
- Navigation targets carry `data-nav="<kind>:<id>"` (§4.2); `navigate` scrolls to, focuses, and highlights them.
- Copy lives in `media/copy/<view>.js`; it has no digits outside placeholders and, in a regression study, none of the words of INV-12. Every key has its French counterpart in `media/copy-fr/<view>.js` (v0.3); the frame swaps the tables when the panel language changes, so views read `Hypotrail.copy.<view>` at render time, never once at load.
- "Ask the agent about this" is `Hypotrail.askButton`; no view writes the clipboard or calls `navigator.clipboard` (§12, CI.5).
- `ctx.placeholder()` is kept in the API but every tab now has its real view; loading states carry `aria-busy="true"`.

## Tests and fixtures

- `test/fixtures/*.json`: hand-written payloads with the mockups' values (`index.json` lists them); `test/fixtures/captured/*.json`: real payloads from `test/fixtures/capture.py` (temporary Bank and Auto MPG studies). `test_fixture_drift.py` keeps the first in the shape of the second, and the second in the shape of the live engine.
- `test/realstudy.js` builds temporary studies from the committed cases and a real controller for `integration-v1/v2/v3.test.js`.
- `scripts/companion_coverage.py` maps the spec's requirement ids to the test files that name them; `test_requirement_coverage.py` keeps the table in `docs/acceptance/V0.1-CHECKLIST.md` current.

## How a view is changed or added

1. Edit `media/views/<view>.js` (keep `HT.register('<view>', {tab, stage, ...})`), `media/copy/<view>.js` (and its French twin in `media/copy-fr/`) and `media/css/<view>.css`.
2. Write `lib/models/<view>.js` with its `to<Name>Model` and `FIXTURES`.
3. Fill `lib/handlers/<view>.js`: `loads` for its data views, `types` for its messages, `commands` if it serves an extension command.
4. Test: `test/<view>.test.js` (fake CLI from `test/fixture-cli.js`), `test/test_webview_<view>.py` (the `open_panel` fixture of `test/conftest.py`).
5. Run the four gate commands of CONTRIBUTING.md. Nothing else needs to change: `lib/html.js` concatenates the new files, the controller discovers the handler.
