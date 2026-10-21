## Hypotrail study panel: visual and UX review (read-only, tip fdc9623)

Nothing in the repository was modified. Everything is in the scratch folder `/tmp/claude-0/-home-user-hypotrail/d627b9a6-d196-5d88-8cd2-a6e477a31532/scratchpad/ui-review-2/`.

### Verdict
The owner is right. The panel works, but it reads like an audit log: grey cards on a grey background, outlined chips, saturated default-blue bars, prose in the theme's low-contrast workbench grey, and a disclaimer under every element.

The v0.2 mockups looked better for three reasons:
1. **They cheated on colours.** They redefined the `--vscode-*` variables with a private warm palette and a teal accent (`docs/design/companion-v0.2-mockups/eda.html:8-30`). The implementation then mapped the tokens to the real theme variables, so the look changed completely:
   - `tokens.css:7`: the card surface is `sideBar-background`, so grey cards sit on a white editor.
   - `tokens.css:9`: prose uses `--vscode-foreground` (#616161, the workbench chrome grey) instead of `editor-foreground`.
   - `tokens.css:43`: chart marks use `--vscode-charts-blue` (#1a85ff), not the teal.
   - `core.css:109-111`: chips are outlined, not filled.
2. **The spec itself requires some of the defects.** §13 says "charts are drawn at their viewBox size… a narrow panel scrolls a chart sideways", and that rule produces the stray scrollbars. §15.1 says to cite every engine number, which produces the dotted underlines.
3. **The work was spread across many work packages** (WP-A5, A7, B5…), each adding a caveat paragraph. Nobody owned the whole page, and the screenshot tool (`HYPOTRAIL_SHOTS`) only writes images; nothing compares them.

The mockups in this review use the **real Light Modern / Dark Modern values** precisely so this drift cannot happen again.

### 1. Defects (current panel, captured payloads)
I captured 72 screenshots: the split study and the cross-validated opened study (`*.cv*`), every tab, light/dark/HC, at 900 and 420 px. They are in `…/ui-review-2/current/` (full pages), with 1300 px slices in `…/current/parts/`. The capture script is `…/tools/shoot_current.py`.

Key shots: `current/parts/split-eda-light-900.p1…p5.png`, `cv-eda-dark-900.p2.png`, `cv-eda-dark-420.p3.png`, `cv-evidence-light-900.p1…p4.png`, `split-decisions-light-900.p1.png`, `cv-whatif-light-900.p1.png`, `cv-overview-dark-420.p1.png`.

**Data bugs and wrong wording**
- **"rows seen in EDA · train 0 · validation 0" under CV, while 3,617 development rows were read.** In `lib/models/eda.js:286` the lookup matches `partition === 'train'`, but CV records `development`. The same banner says "Validation rows seen for model evaluation: 3,617" (`views/eda.js:635`), and there is no validation partition under CV.
- **"Training rows only: the validation rows stay unexplored" sits next to "development rows" counts** (R17). The copy is not aware of the split mode.
- **Meaningless "0 / 0" cells and "no declared range" in every row of the quality table** (`views/eda.js:502`, `copy/eda.js:66`).
- **The map is confusing in the opened CV study:** "Open the final test once" is ticked while "Explore the development rows" is the current step (`cv-overview-light-900.p1`). There is no explanation of why a step came back.
- **"Reading what a confirmation would change…" never resolves.** This happened in my harness without `preview_effects`; the real panel should check that this state times out.

**Overflow and scrollbars**
- The tab bar scrolls sideways at 420 px and hides "What if?" and "Learn & hand off" (`core.css:60-61`).
- Charts sit in `ht-chart-scroll` (`core.css:84-85`) with a fixed SVG width, so the scrollbars appear at 420 px on every interval chart (429 > 374, 508 > 374).
- The five-example-rows table scrolls at 900 px (1016 > 842; `eda.css:35`).
- In the gain and lift curves, the y-axis label is clipped ("ves reached", "share of positi"): `components/curve.js:42` draws the label at x=12, inside the tick labels.

**Noise**
- The recap strip is expanded by default and repeated on every non-Overview tab (`core.js:633`, `core.js:485`). That is a wall of about 10 lines above every tab.
- A dotted underline appears on every number and value (`core.css:103`, `core.css:123`).
- Raw result ids are shown as monospace links in each card head (`views/eda.js:81`).
- Monospace is mixed into prose and labels: the `rows seen` line (`views/eda.js:629`), `revision 42` in the header and in the history (`views/decisions.js:491`), and dictionary names in code font.
- Raw tokens show through:
  - `share:0.2` in the What-if heading and the rules table (`copy/whatif.js:36`).
  - `development_diagnostics` in the ledger (`views/evidence.js:394` falls back to the raw purpose).
  - `cat__poutcome_success` in the coefficients.
- Every chart has its own caveat paragraph, often twice (e.g. "Counts of training rows only… says nothing about causes" under each distribution). Rate-by has four.

**Charts**
- The histogram has no axes, no bin edges and no counts (`components/histogram.js:16-25`). A skewed column collapses into one bar, and the title appears three times (question, chip, figcaption).
- Rate-by and special-value bars are full-saturation blue with whiskers and the label crammed into the plot area.
- Tables shrink to their content and have centred captions (`core.css:88-89`).
- At 420 px every table becomes cards of "Label: value" (`core.css:127-133`). The five example rows become a 1,600 px column.

**Decisions**
- The W1/W2 textarea and buttons are still present, contrary to R23.
- The hint text is the old strict rule ("Say what you accept and why…").
- History is oldest-first, contrary to R25. It shows "restated" for "je confirme ce choix" and timestamps to the second in monospace.

**Theme**
- `tokens.css` switches on `prefers-color-scheme`. In VS Code the reliable signal is `body.vscode-light`, `body.vscode-dark` or `body.vscode-high-contrast`.
- `test/themes.py` only models the old Light+/Dark+ themes, not the current defaults (Light/Dark Modern).

### 2. Design system (plain CSS, no dependency, works under the current CSP)
The source is `…/ui-review-2/src/ds.css`, about 280 lines and directly portable.
- **Two token layers:**
  - Host values: `--vscode-*` with real Modern fallbacks.
  - Hypotrail tokens:
    - Neutral colours are derived from the theme with `color-mix`: `--ht-surface` (2.5 % of the foreground into the editor background), `--ht-sunken`, `--ht-line` and `--ht-line-strong`.
    - `--ht-fg` comes from `editor-foreground`.
    - Six semantic hues (accent teal, warn, bad, seal, info, ok) are fixed per theme kind, with tints via `color-mix`.
- **Scale:**
  - Spacing: 4, 8, 12, 16, 24, 32.
  - Type: caption 11 (uppercase label), meta 12, body 13 (the VS Code size), title 15, page 18, stat 24, with `tabular-nums` throughout.
  - Radii: chips 4, cards 8, pills 999.
  - No shadows. The only elevation is the hero's 3 px accent ring.
- **One card pattern:**
  - An eyebrow (KIND · ROWS) and a title phrased as a question.
  - The figure, then one sentence of finding.
  - A footer holding "Why?", a faint 11 px "Source · activity · 6-char id", and "Show values".
- **Disclosure:** one sentence plus `details.why`. Every caveat, definition and provenance goes in it. Statistical terms are bolded and defined there, which matches AGENTS ("term first, then example").
- **Numbers:** tabular, never underlined. Provenance lives on hover (`title`) and in the footer source line. Monospace is only for column identifiers and code.
- **Status:** filled tint chips with a dot (ok, warn, bad, seal, info, plain). In HC they get a border via `forced-colors`.
- **Charts:**
  - Bars, histograms, intervals, the 2×2 and the heatmap are **HTML/CSS grids, so they are fluid**. Values go in `--v`, `--a`/`--b` custom properties set through CSSOM, which the CSP allows.
  - SVG is kept only for curves (calibration, gain), sized ≤ the container so the text scale stays ≤ 1.
  - One mark colour (accent); the reference or baseline in grey; intervals in the foreground colour with caps; the overall rate as a dashed line; the null band as a neutral band; n < 100 hatched.
  - Every chart has a legend with ≥ 2 encodings; axes have at most 5 ticks.
  - Skewed numeric columns: an "Exactly 0" tile apart from the plot, then log bins with edge labels (0+, 1, 3, 10 … 3k s). Median, IQR, mean, max and missing are named in a stat row.
  - Correlation is diverging (orange–neutral–teal), lower triangle only, with |ρ| ≥ 0.85 outlined.
- **States:** a skeleton for loading, a dashed empty box with one action, and an error card that quotes the CLI code with "Try again".
- **FR/EN:** a header segmented `EN | FR` next to Refresh (R21). The dictionary has its own explicit "Meanings EN | FR" toggle (R12).

### 3. Mockups
They are self-contained HTML with no network access and the system font (Google Fonts deliberately not used, to stay faithful to the CSP), plus a light/dark toggle. Distributions and the Spearman matrix are computed on a 9,864-row Online Shoppers development sample **without the target**; outcome rates, AUCs and model figures are illustrative and labelled as such.
- HTML: `…/ui-review-2/mockups/overview.html`, `eda.html`, `decisions.html`, `evidence.html`, `deliverables.html`.
- PNG: `…/ui-review-2/mockups/png/{page}-{light|dark}-{900|420}.png` (20 files), with slices in `…/png/parts/`. The build script is `…/src/build.py` and the renderer `…/tools/render.py`. The renderer reports any page wider than the viewport; it found none.

What each page shows:
- **Overview:** the next-move hero, a 9-step journey bar, 4 stat tiles, "decided so far", 3 tagged limits with "Why?", the timeline since the last session, and the three states.
- **Data & EDA:** a data card with tiles, a grouped dictionary with availability chips, quality as 4 chips, a single CV note, the outcome rate, months, two skewed-duration cards, rate-by VisitorType (interval, null band, hatched small group), single-feature AUC with the PageValues leak callout, the correlation matrix (R28), and the request bar.
- **Decisions:** a read-only proposal card (restatement, why proposed, effect in words, "Answer in the chat", "Ask the agent"; R23) and history newest first (R25) with endorsed/with-reason labels.
- **Evidence:** the final-evidence hero (stats plus gain interval against the +5 criterion), the CV fold strip for the variant, a real 2×2 confusion matrix with counts and rates, a calibration plot with intervals, and an exposure summary.
- **Files:** three rows with Marimo run/edit and a "What happens when I click?" disclosure.

### 4. Gate against drift
- **Component inventory (one file each in `media/components/`):** `Card`, `StatTile`, `Chip`, `Why`, `Source`, `Note`, `HBars`, `Interval`, `Histogram` (with the zero tile), `Corr`, `Confusion`, `Curve`, `Timeline`, `Journey`, `Deliverable`, `Empty`/`Skeleton`/`ErrorCard`. Views may compose only these; `check_layout.py` would reject `className` strings outside an allow-list.
- **Deterministic structural assertions** run in the existing harness on the captured payloads, for every tab × {Light Modern, Dark Modern, HC} × {900, 600, 420}:
  - no element's right edge past the viewport, and no scrolling container except the dictionary table;
  - no monospace in elements containing more than 3 words;
  - no `text-decoration` on numbers;
  - no 6–64 hex string outside `.src`;
  - no `key:value` token or `snake_case` outside code;
  - one `h3` per card;
  - at most 1 note per card;
  - chart text 10–13 px.
- **Pixel baselines:** commit PNGs under `docs/design/baselines/`. Compare them inside Chromium itself, by loading both images into a canvas and counting pixels with a delta above 24. That needs no Pillow or pixelmatch (Pillow is not in the framework environment). A >0.5 % difference fails, and a `--update-baselines` flag refreshes them, with owner review required.
- Add Light/Dark Modern variable sets to `test/themes.py` and switch the tokens to `body.vscode-*` classes.

### 5. Migration plan
1. **S – stop the bleeding:**
   - Collapse the recap by default and show it only on Overview.
   - Remove the dotted underlines and the result-id chips (move them to the footer `Source`).
   - Fix the CV `rowsSeen` and validation wording.
   - Drop the "0 / 0" and "no declared range" cells.
   - Fix the clipped y labels; map the raw tokens (`share:0.2`, `development_diagnostics`, `cat__…`) to words.
   - Order history newest first; remove the W1/W2 UI (R23, plus the ADR 0004 narrowing).
2. **M – tokens and theme:**
   - Switch to the two-layer tokens with `editor-foreground` and the `color-mix` surfaces.
   - Use fixed semantic hues per `body.vscode-*`; switch to filled chips.
   - Amend spec §13 (drop "scroll sideways").
   - Add the Modern variable sets.
3. **M – the card and disclosure pattern across all tabs.** Rewrite the caveats into "one sentence + Why?". This is copy work in `media/copy/*`; plan it together with the R21 FR strings.
4. **L – chart rewrite as fluid HTML bars, with SVG curves sized to the container:**
   - zero-split log histogram;
   - interval rows;
   - confusion 2×2 at the adopted rule;
   - calibration;
   - correlation matrix. This needs a new engine activity; it reads no target.
5. **M – the gate:** structural assertions plus the in-browser pixel diff, wired into CONTRIBUTING.
6. **S – the Overview journey bar** in place of the 4-column map, with an explanation when a step reopens.

### 6. Risks and constraints
- **CSP:** no `style` attributes. The mockups use `style="--v:…"` only for brevity; production must set these with `el.style.setProperty`, which `core.css` already allows. Check that the sandbox does not flag CSSOM writes as attribute styles: `test_webview_themes` asserts `body [style]` count = 0, and CSSOM writes do create a style attribute. **That assertion must change** to "no style attribute present in the server HTML or created via `setAttribute`", or bars must use a fixed set of width classes (`.w-0…w-100`, 101 rules).
- **`color-mix`** needs Chromium 111 or later. VS Code 1.90+ ships it; the README requires 1.90.
- **Fixed hues versus custom themes:** the teal can clash with unusual themes. In HC, fall back to `CanvasText`/`Highlight`.
- **Fluid SVG** needs a `ResizeObserver` and a re-render. That is fine (no dependency), but it must keep the "one SVG unit = one CSS px" test meaningful.
- **"Marimo is running" state:** the panel does not own the terminal and has no state, so this can only be a transient outcome message, never live status.
- **Correlation matrix** is an engine change; it must stay unexpanded and target-free so it is not a counted look.
- **FR (R21):** French strings are about 20 % longer; the 420 px gate must also run with FR copy.

### Top 5 recommendations
1. **Design against real theme values, not a private palette.** Adopt the two-layer tokens with `editor-foreground`, `color-mix` surfaces and fixed semantic hues per `body.vscode-*`. This is the root cause of the drift.
2. **One card pattern and "one sentence + Why?" everywhere.** Delete the per-chart caveat paragraphs and the always-on recap; ids and revisions move to a faint footer line.
3. **Rewrite the charts as fluid HTML grids** (no sideways scroll, ever). Skewed columns get the zero tile plus log bins and a named median/IQR; rate-by gets a point, an interval, the null band and n.
4. **Fix the correctness bugs before any polish:** CV `rowsSeen` ("train 0"), the split-aware wording, the raw tokens, R23 (read-only proposal) and R25 (newest first).
5. **Gate it:** structural overflow, typography and id assertions plus in-browser pixel baselines, at 3 widths × 3 themes on the captured payloads, with screenshot review by the owner for any baseline change.