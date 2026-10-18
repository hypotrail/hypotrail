# Starting the next Hypotrail implementation

Open the **root of the `hypotrail` repository** in VS Code. On the current machine this is `/Users/schadli/source/hypotrail`. Start the implementation agent there so it can read repository instructions and all three source areas.

## Next task

Implement the junior Copilot + HTML + Marimo workflow for Bank Marketing using the user's specification. Build a fluid, explicit experience with defensible evidence and reliable resumption. Companion development remains paused.

## Reading order

1. [Repository instructions](../AGENTS.md).
2. [Implementation handoff](handoff/IMPLEMENTATION.md).
3. [Consolidated junior specification](specs/JUNIOR-WORKFLOW.md).
4. [Repository architecture](architecture/REPOSITORY.md).
5. [Bank Marketing context](../use-cases/bank-marketing/README.md).

The [independent design review summary](reference/INDEPENDENT-REVIEW.md) explains the validity and coherence requirements behind this direction. It is design evidence, not verification of the current code.

## Starting prompt for a fresh agent

```text
You are developing Hypotrail in the root of this repository.
Read AGENTS.md, docs/START-HERE.md, docs/handoff/IMPLEMENTATION.md,
docs/architecture/REPOSITORY.md, and docs/specs/JUNIOR-WORKFLOW.md,
then read any additional specifications I provide.

Implement the junior Copilot chat + HTML + evolving Marimo notebook workflow.
Start with use-cases/bank-marketing and put reusable code in framework.
The experimental companion is paused. Preserve existing study state and data.

Compare the specification with the actual implementation and present a concrete
plan. First build a complete slice: structural inspection, a proposed plan,
a useful confirmation, EDA on the authorized partition, consistent HTML and
notebook outputs, and resumption in a new chat. Then complete the remaining
accepted phases. Do not present precomputed companion outputs as a new run.
Test the changes and identify acceptance checks that require actual Copilot use.
```
