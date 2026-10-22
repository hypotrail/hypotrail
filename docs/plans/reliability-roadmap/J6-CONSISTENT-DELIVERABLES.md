# J6 — Consistent chat, HTML, notebook and optional panel

Depends on J0–J5. Review coverage: interface findings, M3, stale-history false blocks.

## Outcome

A user sees the same position, chosen configuration, evidence scope and limitations
wherever they read the study. The generated notebook explains and can recompute;
the workbench remains editable and its annotations survive regeneration.

## Implementation anchors

`view.py`, `currency.py`, `read.py`, `render_html.py`, `render_notebook.py`,
`notebook_view.py`, `code_cells.py`, `render_diagnostics.py`, `render_trials.py`,
`cmd_render.py`, `manifest.py`, `launch.py`, `templates/workbench.py`.
Panel: `clients/vscode-companion/lib/models/`, `lib/handlers/`, `lib/l10n.js`,
`lib/html.js`, `media/` and the captured-fixture pipeline. Follow ADRs 0001–0004.

## J6.1 — One presentation snapshot

Build all outputs from one verified snapshot carrying study revision, source result
IDs, claim eligibility, uncertainty descriptors, assurance and pending action.
Represent result status in the dimensions of COMMON C4. Do not compute separate
scientific verdicts in JavaScript, notebook prose and HTML templates.

Required compact presentation fields (reuse existing equivalents where present):

- current step and next action;
- chosen model, preparation and action rule, in ordinary language;
- criterion convention and judged scope, with development and final values separate;
- sample sizes/populations and timing assumptions;
- final state: reserved, consumed with result, consumed with unknown/failed outcome;
- active requirements, historical invalidations and uninstrumented exposure limits;
- artifact revision, generation time and result references.

A visible “blocked” status is derived only from unsatisfied requirements for the
current next transition. Historical stale entries can remain in an audit trail.
An artifact stale after a new decision must be identified as such, without blocking
unrelated exploration or deleting its last valid content.

## J6.2 — HTML reading order

Keep one stable offline report path. Order the first screen around:

1. question and current position;
2. what is currently supported, with the criterion convention and scope;
3. most important limitation;
4. next decision/action and link to supporting evidence.

The report does not implement adoption or mutation controls. It may show a ready
question to ask in chat. Keep detailed identities and logs in an annex while every
empirical figure remains bound to J5 evidence metadata. Historical results get an
explicit historical section, never the current verdict position.

After opening, show the final evaluation separately with original configuration and
date. Display descriptive drift using development/final target rates, counts,
periods and populations. Derive all figures from registered evidence; do not hard-
code the review's 25.9%/35.3%. Do not access reserved labels to prepare this comparison
early. State that drift may reflect composition/context and does not establish cause.
No suggestion to tune again on the same final test.

Keep offline resources, accessible tables, keyboard focus, contrast and responsive
layout. Follow the repository's existing visual system; a new design language or
full panel redesign is not part of this milestone.

## J6.3 — Notebook roles and explicit execution

Every generated section follows question → concept → method → code → result →
interpretation → consequence, as far as evidence exists. Upcoming sections say
“not executed”; do not manufacture a final narrative before evaluation.

Label each substantive cell with one of:

| Cell role | Meaning and constraints |
|---|---|
| Recompute | Executes visible calculation from permitted inputs; names protocol, result and expected equality |
| Registry view | Reads a registered result; does not claim independent recomputation |
| Personal exploration | User-owned workbench code; isolated from authoritative decisions/results |

Generated opening MUST NOT silently refit models. Place refits behind a Marimo
explicit run control/guard supported by the pinned version. On initial open the
generated notebook may display registered summaries and lightweight explanatory
code. The refit cell waits for the user's action and explains expected work and
data scope. It does not write a new authoritative study result just because the
notebook ran. A user who wants to adopt an exploration returns to chat and engine
commands. Do not create a second engine inside the notebook.

Use J1's explicit train/validation memberships for recomputation, including warm-up
coverage and nested tuning. Keep readable pandas/sklearn code where educational;
shared primitives may ensure definitions match, but label the dependency honestly.
Keep independent small-oracle tests outside shared engine helpers (J7).

No generated cell reads reserved final labels. After opening, view final predictions
and diagnostics already recorded; do not refit on final labels or rerun final
evaluation. A recomputation of a summary from persisted final predictions must be
labelled as that, not an independent second final test.

The workbench is never overwritten. Preserve personal cells and annotations under
the existing generated/reference versus workbench separation. If a generated file
has unexpected user changes, write a candidate/conflict artifact following ADR 0001
rather than silently deleting edits. Do not automatically run arbitrary modified
workbench code during a render or acceptance check.

## J6.4 — Artifact publication and partial failure

Generate HTML and notebook against the same snapshot. Use the existing temporary-
file/manifest publication mechanisms; strengthen them if needed. Before publishing,
verify the state has not changed. If it has, keep outputs as candidates/stale artifacts
and do not label them current.

If one renderer fails, retain the last valid artifact(s), record the failed attempt
and display per-artifact revision/currentness. Do not report “deliverables updated”
when only one is current. A language-only regeneration does not invalidate models
or human decisions. Artifact metadata must make mixed revisions visible.

## J6.5 — Optional panel alignment without scope expansion

The panel reads the same derived CLI data, with localized text and compact details.
Fix false stale blockers, bilingual gaps and access to the final result. It remains
default-off with default stage v0. It never confirms, proposes, withdraws, records
exploration, trains, splits or evaluates. The only existing Marimo launch exception
remains unchanged. Do not introduce direct state-file reads, a socket or an API.

Keep What if unrecorded and visibly exploratory per J4. Copying a question to chat
is not a recorded comparison. A higher stage must not bypass final-test or
interpretability requirements. Regenerate captured fixtures via
`clients/vscode-companion/test/fixtures/capture.py`, not by hand.

## Acceptance

| ID | Scenario | Required outcome |
|---|---|---|
| J6-A01 | Compare chat payload, report, notebook and panel snapshot | Same revision, model/rule, scope, criterion and evidence IDs |
| J6-A02 | Current replacement plus old stale diagnostic | No false current blocker; history still visible |
| J6-A03 | Actually stale required diagnostic | Every surface identifies requirement and next action |
| J6-A04 | Open generated notebook at each phase | No unrequested model refit, state write or final-label access |
| J6-A05 | Explicit synthetic recomputation | Correct memberships and expected numbers; no authoritative adoption |
| J6-A06 | Add workbench annotation, render twice | Exact user content preserved |
| J6-A07 | Unexpected edit to generated file | Explicit conflict/candidate; no destructive replacement |
| J6-A08 | HTML succeeds, notebook renderer fails | Accurate per-artifact status; last valid notebook retained |
| J6-A09 | State changes during generation | Old snapshot never published as current |
| J6-A10 | Before/after synthetic final opening | Drift hidden before opening; counts/periods shown afterwards |
| J6-A11 | FR and EN, narrow/wide viewport, light/dark/high contrast | Readable, no page overflow, no agent-only instructions in junior text |
| J6-A12 | Panel disabled and absent | Complete chat/HTML/notebook workflow remains usable |

Run notebook-generation tests and the ADR 0001 spike when changing execution guards.
Run offline report tests and panel tests as required in CONTRIBUTING. Pixel-baseline
updates require the existing owner review of actual diff images; do not update every
baseline blindly. Browser simulations do not count as a real VS Code session.

Completion requires coherent renderers and preservation checks. A nominal walkthrough
with no changes is insufficient: A02, A03, A06, A08 and A09 test the recovery behavior
the user needs in actual work.
