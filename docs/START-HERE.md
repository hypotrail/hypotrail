# Starting work on Hypotrail

Open the **root of the `hypotrail` repository** and start the development agent there, so it reads the repository instructions and all three source areas.

## Where things stand

**v0.1 is implemented**: a guided junior study of Bank Marketing, driven by Claude Code in chat, with one evolving offline HTML report and a generated Marimo notebook, on top of a study engine (`framework/mlkit/study/`, CLI `hypotrail`) that keeps numbers, partitions, and decisions traceable. GitHub Copilot is not tested yet, no human junior has used it, and the old companion remains paused; a study panel for VS Code exists behind a feature flag that is off by default ([ADR 0003](decisions/0003-companion-webview-v0.md); its stages v1 to v3, [ADR 0004](decisions/0004-companion-advanced.md), are implemented behind a stage setting and not yet run in a real VS Code). The handoff lists what works, what is refused, and the remaining defects.

## Reading order

1. [Repository instructions](../AGENTS.md).
2. [Implementation handoff](handoff/IMPLEMENTATION.md): v0.1 capabilities, commands, exclusions, known limits.
3. [v0.1 acceptance checklist](acceptance/V0.1-CHECKLIST.md): each behaviour with its test or agentic evidence.
4. [v0.1 decisions and open questions](plans/V0.1-DECISIONS.md): what the implementing agents decided, and what the owner should review.
5. [Consolidated junior specification](specs/JUNIOR-WORKFLOW.md): the target; v0.1 implements a slice of it.
6. [CLI contract](specs/CLI-CONTRACT.md) and [case contract](specs/CASE-CONTRACT.md).
7. [Repository architecture](architecture/REPOSITORY.md).
8. Cases: from v0.2b the discovery case is [Online Shoppers](../use-cases/online-shoppers/README.md) (try it first), then [Bank Marketing](../use-cases/bank-marketing/README.md) (the v0.1/v0.2a reference) and its [full file in time order](../use-cases/bank-marketing-full/README.md), and [Auto MPG](../use-cases/auto-mpg/README.md) for regression. The quickstart in the [README](../README.md) opens Online Shoppers.
9. For history: [the v0.1 plan](plans/V0.1-IMPLEMENTATION-PLAN.md), the [ADRs](decisions/), the [agent acceptance runs](acceptance/runs/), the [E1 steelman](research/E1-STEELMAN.md), and the [observation protocol](research/OBSERVATION-PROTOCOL.md) for sessions with human juniors.

The [independent design review summary](reference/INDEPENDENT-REVIEW.md) explains the validity and coherence requirements behind this direction. It is design evidence, not verification of the current code.

## Starting prompt for a fresh agent

```text
You are developing Hypotrail in the root of this repository.
Read AGENTS.md, docs/START-HERE.md, docs/handoff/IMPLEMENTATION.md,
docs/acceptance/V0.1-CHECKLIST.md, docs/plans/V0.1-DECISIONS.md and
docs/specs/CLI-CONTRACT.md, then read any additional specifications I provide.

v0.1 (Bank Marketing, Claude Code, HTML report, generated Marimo notebook) is
implemented. Put reusable code in framework and case material in use-cases.
The experimental companion is paused; a flagged study panel (clients/vscode-companion, ADR 0003) is off by default. Preserve existing study state and data;
create test studies outside the repository.

Compare the task with the handoff's known limits, present a concrete plan,
and keep the CLI contract, its freeze test, and the documentation in step.
Run the gate in CONTRIBUTING.md before each commit. Identify acceptance
checks that need an agent session or a real Copilot session separately.
```
