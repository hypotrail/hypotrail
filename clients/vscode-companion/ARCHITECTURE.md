# Study panel: architecture

The panel is one more client of the `hypotrail` CLI (ADR 0002). It has no build step and no runtime dependency. Behaviour is specified in [COMPANION-ADVANCED.md](../../docs/specs/COMPANION-ADVANCED.md) (the spec), the engine interfaces in [CLI-CONTRACT-COMPANION.md](../../docs/specs/CLI-CONTRACT-COMPANION.md) (CC), and the work packages in [COMPANION-ADVANCED-PLAN.md](../../docs/plans/COMPANION-ADVANCED-PLAN.md). WP-0 froze the interfaces below; a change to one is a request to the integrator.

## Modules

```text
extension.js            vscode API only: flag and trust checks, commands, URI handler, panel, host functions
lib/flag.js             enabled, stage (v0-v3), learningLayer, reviewer, chatInsert (hidden), env overrides
lib/study.js            study discovery and agent.json validation (the CLI argv)
lib/watch.js            fs.watch of .hypotrail/ (debounced), no polling
lib/cli.js              THE ONLY child_process user: read builders (READS), write builders W1-W7 (WRITES), run()
lib/protocol.js         hypotrail.panel/2 schema table and validators; emits media/protocol.js
lib/controller.js       router: validation, stage gate, reviewer refusal, summary, load dispatch,
                        cache + coalescing + read limits, exclusive write lock, outcome mapping
lib/cache.js            per key and revision; preview:* keys in a bounded list
lib/handlers/<view>.js  {types, loads, commands, onReady}: one module per view group
lib/models/<view>.js    pure payload -> model functions (to<Name>Model) + FIXTURES
lib/refusals.js         refusal explanations (never suggest words)
lib/uri.js              deep-link parsing and result-id input (WP-U3)
lib/html.js             the document: media concatenated in a fixed order under one nonce
media/protocol.js       generated copy of lib/protocol.js (never edit)
media/format.js         port of cite.fmt_number (cross-tested with Python)
media/core.js           webview runtime: frame, tabs, live region, modal, tooltip, send(), setState
media/components/*.js   bars, intervalRows, histogram, boxplot, valuesTable, figure, segments, cited
media/copy/<view>.js    panel-owned English strings (copy/core.js for the frame)
media/views/<view>.js   one view per tab, registered with Hypotrail.register
media/css/*.css         tokens.css (theme), core.css (frame, components), <view>.css
```

Only `lib/cli.js` starts a process. Only `extension.js` requires `vscode`, so the controller and handlers run under `node --test` with a fake CLI.

## Message flow

```text
webview (media/*)                         extension host (lib/*)                    CLI
HT.send({type, ...})  -- {v: 2, ...} -->  controller.handle(raw)
                                            protocol.validateIncoming   (invalid: dropped, diagnostics.ignored)
                                            stage gate (stageOf > stage: dropped, diagnostics.ignored)
                                            reviewer + write type -> outcome invalid
                                            ready/refresh -> summary read --------------> status --summary [--digest]
                                            load -> handlers' loads[view] -> ctx.read --> (cached per key and revision)
                                            other -> handlers' types[type](message, ctx)
                                                       ctx.write(op, {argv, record}) -> W1-W7 argv (exclusive)
render(model, ctx) <-- {v: 2, ...} -----  ctx.post(...) validated by protocol.validateOutgoing
```

Extension to webview: `init` (stage, reviewer, learningLayer, chatInsert, task), `snapshot` (SummaryModel), `view_data` (a view's model), `load_error`, `busy`, `outcome` (`op` W1-W7, `kind`), `effects`, `preview_policy_result`, `draft_result`, `learn_state`, `navigate`, `notice`. The webview drops anything that fails validation.

## Frozen interfaces

- **Handlers** (`lib/handlers/<name>.js`, discovered in file order): `types: {messageType: async (message, ctx)}`, `loads: {view: {stage?, key(message), argv(cli, agent, message), model(payload)}}`, `commands: {name: async (args, ctx)}` (extension commands such as `go_to_result`), `onReady: async ctx`. A type, view, or command claimed twice throws at start. `ready`, `refresh`, `load`, and `load: summary` belong to the controller.
- **ctx**: `agent`, `settings`, `snapshot()`, `stageAtLeast(s)`, `post(message)`, `read(key, argv, modelFn, {group?, timeoutMs?})` → `{ok, model, revision} | {ok: false, message, detail, refusal?}`, `write(op, {target, argv(requestId), record(payload)})` → the outcome (or null when refused before running), `refresh()`, `invalid(op, message, target)`, `host` (openArtifact, confirmWithdraw, confirmModal, pickFolder, openFile, revealInOS, writeClipboard, executeCommand, notify, globalState, switchStudy), `exists`, `artifactPath(name)`, `cli`, `refusals`, `uuid`, `log`, `diagnostics`.
- **Models**: each `lib/models/<name>.js` exports `to<Name>Model(payload)` (throws `ModelError` from `lib/models/common.js` on a wrong schema) and `FIXTURES` (names under `test/fixtures/`). `test/protocol.test.js` round-trips every one.
- **Views**: `Hypotrail.register(name, {tab, stage, views?, outcomes?, render(model, ctx), onMessage?(message, ctx)})`. `model` is the SummaryModel. `views` lists the data views the controller loads when the tab is shown and the snapshot moved past them; `ctx.data(view)` returns `{revision, model, resultId}`. `outcomes` lists the write ops whose outcome the view renders itself (`ctx.outcome(target)`, `ctx.renderOutcome(o)`); the frame's live region shows the others. `onMessage` returning `false` for a forwarded message (effects, preview_policy_result, draft_result, learn_state) skips the re-render.
- **View ctx**: `init`, `stage`, `reviewer`, `task`, `learningLayer`, `chatInsert`, `snapshot`, `data`, `error`, `busy`, `busyOp`, `busyTarget`, `send`, `load(view, extra)`, `drafts`, `ui` (setState keys of spec §10 only), `wordsArea`, `outcome`, `renderOutcome`, `el`, `svg`, `format`, `components`, `copy`, `gate(stage, node)`, `atLeast`, `modal`, `tooltip`, `navigate`, `placeholder()`, `rerender()`.
- **Components** (`Hypotrail.components`): `bars`, `intervalRows`, `histogram`, `boxplot`, `valuesTable`, `figure`, `segments`, `cited`, with the signatures in each file's header and in the plan §2.2.

## Rules every view keeps

- Study text goes in with `text` or text nodes; `el()` refuses `style`, `innerHTML`, and non-function handlers.
- Words the junior types go only in `ctx.wordsArea({kind, key, ...attrs})`; no other textarea exists (INV-5, `test/invariants.test.js`).
- SVG colours are palette names (`Hypotrail.PALETTE`); sizes are attributes or `style.setProperty`; no `style` attribute.
- Every write control carries `data-write`; the frame removes all of them in reviewer mode.
- A stage-gated element carries `data-stage` (or comes from `ctx.gate`); a later-stage tab is absent, not disabled.
- Navigation targets carry `data-nav="<kind>:<id>"` (§4.2); `navigate` scrolls to, focuses, and highlights them.
- Copy lives in `media/copy/<view>.js`; it has no digits outside placeholders and, in a regression study, none of the words of INV-12.

## How a work package adds its view

1. Replace the placeholder `media/views/<view>.js` (keep `HT.register('<view>', {tab, stage, ...})`), fill `media/copy/<view>.js` and `media/css/<view>.css`.
2. Write `lib/models/<view>.js` with its `to<Name>Model` and `FIXTURES`.
3. Fill `lib/handlers/<view>.js`: `loads` for its data views, `types` for its messages, `commands` if it serves an extension command.
4. Test: `test/<view>.test.js` (fake CLI from `test/fixture-cli.js`), `test/test_webview_<view>.py` (the `open_panel` fixture of `test/conftest.py`).
5. Run the four gate commands of CONTRIBUTING.md. Nothing else needs to change: `lib/html.js` concatenates the new files, the controller discovers the handler.
