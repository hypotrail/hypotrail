# Starting work on Hypotrail

Open the **root of the `hypotrail` repository** and start the development agent there, so it reads the repository instructions and all three source areas.

## Where things stand

**v0.2 is implemented and closed**: a guided junior study driven by Claude Code in chat, first on Online Shoppers (the discovery case), with Bank Marketing, Bank Marketing full (a temporal final test), and Auto MPG (regression). The study engine (`framework/mlkit/study/`, CLI `hypotrail`) shows a data card before any decision, seals a final test at creation and lets the junior open it once, evaluates by cross-validation with one model variant, records nine decisions in the junior's own words (guided mode by default; training and express modes), runs model diagnostics, and keeps numbers, partitions, and decisions traceable in one offline HTML report and a generated Marimo notebook whose cells recompute the figures. Studies made under v0.1 (five decisions) and v0.2a (seven) still load. GitHub Copilot is not tested, no human junior has used it, and the old companion remains paused; a study panel for VS Code exists behind a feature flag that is off by default ([ADR 0003](decisions/0003-companion-webview-v0.md), stages v1 to v3 in [ADR 0004](decisions/0004-companion-advanced.md)), never run in a real VS Code. The handoff lists what works, what is refused, and what is not proven.

## Reading order

1. [Repository instructions](../AGENTS.md).
2. [Implementation handoff](handoff/IMPLEMENTATION.md): v0.2 capabilities, commands, exclusions, known limits, v0.3 candidates.
3. [v0.2 acceptance checklist](acceptance/V0.2-CHECKLIST.md): each owner remark and synthesis decision with its tests, agentic runs, and status, and what is not proven.
4. [v0.2 owner review guide](plans/V0.2-OWNER-REVIEW.md): the decisions most worth reviewing and the owner demo 2 script; the full [v0.2 decisions log](plans/V0.2-DECISIONS.md).
5. [Consolidated junior specification](specs/JUNIOR-WORKFLOW.md): the target; v0.2 implements a slice of it.
6. [CLI contract](specs/CLI-CONTRACT.md) (v0.2 additions in §3.3, §4.1, §5.2–5.3, §11–§13) and [case contract](specs/CASE-CONTRACT.md); ADRs [0005 confirmation modes](decisions/0005-confirmation-modes.md) and [0006 final test](decisions/0006-final-test-partition.md).
7. [Repository architecture](architecture/REPOSITORY.md).
8. Cases: [Online Shoppers](../use-cases/online-shoppers/README.md) first, then [Bank Marketing](../use-cases/bank-marketing/README.md) (the v0.1/v0.2a reference) and its [full file in time order](../use-cases/bank-marketing-full/README.md), and [Auto MPG](../use-cases/auto-mpg/README.md) for regression. The quickstart in the [README](../README.md) opens Online Shoppers.
9. For history: [owner demo 1 remarks](acceptance/OWNER-DEMO-1-REMARKS.md), the [review synthesis](plans/V0.2-REVIEW-SYNTHESIS.md), the [v0.2 plan](plans/V0.2-IMPLEMENTATION-PLAN.md), v0.1 ([plan](plans/V0.1-IMPLEMENTATION-PLAN.md), [checklist](acceptance/V0.1-CHECKLIST.md), [decisions](plans/V0.1-DECISIONS.md)), the [ADRs](decisions/), the [agent acceptance runs](acceptance/runs/), the [E1 steelman](research/E1-STEELMAN.md), and the [observation protocol](research/OBSERVATION-PROTOCOL.md) for sessions with human juniors.

The [independent design review summary](reference/INDEPENDENT-REVIEW.md) explains the validity and coherence requirements behind this direction. It is design evidence, not verification of the current code.

## Starting prompt for a fresh agent

```text
You are developing Hypotrail in the root of this repository.
Read AGENTS.md, docs/START-HERE.md, docs/handoff/IMPLEMENTATION.md,
docs/acceptance/V0.2-CHECKLIST.md, docs/plans/V0.2-OWNER-REVIEW.md and
docs/specs/CLI-CONTRACT.md, then read any additional specifications I provide.

v0.2 (Online Shoppers first, then Bank Marketing, Bank full and Auto MPG;
Claude Code; sealed final test, cross-validation, nine decisions; HTML report
and generated Marimo notebook) is implemented. Put reusable code in framework
and case material in use-cases. The experimental companion is paused; the
flagged study panel (clients/vscode-companion, ADRs 0003 and 0004) is off by
default. Preserve existing study state and data; create test studies outside
the repository.

Compare the task with the handoff's known limits, present a concrete plan,
and keep the CLI contract, its freeze test, and the documentation in step.
Run the gate in CONTRIBUTING.md before each commit. Identify acceptance
checks that need an agent session, a real VS Code session, or a real Copilot
session separately.
```
