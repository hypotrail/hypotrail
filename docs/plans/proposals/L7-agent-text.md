# L7 agent-text proposal: what comes after the study

Lot L7 of [OWNER-SESSION-2026-10-26-PLAN.md](../OWNER-SESSION-2026-10-26-PLAN.md)
(§3 L7, decision D15). Under the shared-files rule (§1.3), L7 does not edit the agent
templates; this file gives the exact text for the integrator to apply against the word
ledger (§2.4, estimate for L7: +30 words).

## What the engine now serves

At `next_action.kind == "done"`, `next_action.after_study` (CLI-CONTRACT §3.1):

- `junior_text`: one paragraph in the study language, ready to relay: the handoff pack;
  the Azure ML export plan only when the chosen model is in the support matrix, otherwise
  why not; and that no Azure job or endpoint has ever been run from these exports. No
  command, id or revision number.
- `handoff.command`: `hypotrail export handoff --study <study> --expected-revision <rev>`.
- `azureml.supported`, `azureml.reason`, `azureml.plan_command` (null unless supported):
  `hypotrail export azureml --study <study> --expected-revision <rev> --plan`.
- `cloud_status: "not_qualified"`.

The engine carries the wording, so the template only has to say "relay it, offer only what
is supported, never claim a cloud run".

## Change 1 (required): the skill's conclusion section

File: `framework/mlkit/study/agent/dot-claude/skills/hypotrail-study/SKILL.md`, section
`## The conclusion`, shared by both tasks (outside the task blocks). Insert a new paragraph
**after** the indented command line `    {{HYPOTRAIL}} check --text - --study {{STUDY}}`
that ends the section:

```markdown
At `done`, relay `next_action.after_study.junior_text`, then offer the handoff pack and, only when `after_study.azureml.supported`, the export plan (its `plan_command`, prefix as in Commands). Never say an Azure job or endpoint ran.
```

Word delta (the budget test's count, `str.split()` on the raw template): **+30** for each
task (binary and regression), in line with the ledger's +30.

Pinned phrases to add in `framework/tests/study/test_agent_files.py` with the change (so the
rule cannot be removed silently): `next_action.after_study.junior_text`,
`after_study.azureml.supported`, `Never say an Azure job or endpoint ran`.

## Change 2 (optional, +15 words): the commands block

File: `framework/mlkit/study/agent/CLAUDE.md.in`, `## Commands`, after the `render` line.
Only if the ledger has room; `plan_command` and `handoff.command` already give the full
commands, so the agent can run them without these lines.

```sh
{{HYPOTRAIL}} export handoff --study {{STUDY}} --expected-revision REV
{{HYPOTRAIL}} export azureml --plan --study {{STUDY}} --expected-revision REV
```

Word delta: **+15** (7 + 8) for each task. Recommendation: leave it out for this batch
(headroom 1 word on binary before the ledger's savings).

## Why the template still says "prefix as in Commands"

The engine's commands start with the bare `hypotrail`; a workspace may call it through
`{{HYPOTRAIL}}` (for example `uv run --project ... hypotrail`). The four words
"prefix as in Commands" tell the agent to run the command with its own prefix. If the
integrator prefers fewer words, the engine could instead serve the arguments without the
program name; that is a contract change (CLI-CONTRACT §3.1) and is not made here.

## Not in the templates

- The panel's Learn & hand off tab shows nothing of `after_study` yet (the panel's models
  belong to L2; the summary already carries `next_action.after_study`).
- The R17 limit text and the R18 refusal need no template change: the engine's
  `junior_text` of `no_time_or_entity_identifier` and the export refusal's message carry
  them.
