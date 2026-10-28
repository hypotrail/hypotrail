# L3 agent-text proposal: one language per study (R4)

Lot L3 of [OWNER-SESSION-2026-10-26-PLAN](../OWNER-SESSION-2026-10-26-PLAN.md) (§3 L3, §2.4
ledger, D4 A, D4b). The integrator applies this text to `framework/mlkit/study/agent/CLAUDE.md.in`
against the word ledger; L3 does not edit the agent templates.

## What changes and why

The engine now gives the junior texts of a study in its language wherever they come from
(CLI-CONTRACT §3.3, "One language per study"):

- `init` and `plan` return the step titles and questions in the study language;
- `run` adds `question_junior`, the question an EDA result answers in the study language
  (the stored `values.question` stays the English source, `eda.py` being fingerprinted);
- the case's statements (facts, special values' meanings, group names, availability sources)
  come in French from the case's translation sidecar `case.l10n.yaml`, so the prediction
  moment's `recommended.value` is French in a French study, and `data --format text` prints
  the card in the study language;
- the report and the generated notebook show a proposal's French restatement when the agent
  gave one (`--restatement-fr`), and label an English restatement `lang="en"` otherwise.

Only one sentence of the template still points the agent at an English-only text: the
exploration paragraph of rule 3 tells it to say `values.question`, which is the English
source in every study. In a French study the agent then either quotes English or translates
it itself, which is what R4 reported. Everything else in the templates already reads a field
that is now in the study language (`junior_message`, `junior_text`, `recap_junior`,
`recommended`, `default_value`, `data --format text`), and rule 11 already asks for
`--restatement-fr` in French.

## Exact replacement

In `CLAUDE.md.in`, rule 3, paragraph **Exploration.**, replace:

```text
   **Exploration.** Say each result's `values.question` before its figure, with the count
```

with:

```text
   **Exploration.** Say each result's `question_junior` before its figure, with the count
```

## Word delta

0 words (one identifier replaces another). No change to `copilot-agent.md.in`, `SKILL.md`,
`hypotrail-resume.md` or `agent_files.FLAVOUR_TEXTS`.

## Checks for the integrator

- `test_agent_files.py`: the word budget is unchanged, but
  `test_instructions_carry_the_v0_2a_rules` (the rule-3 phrase list)
  pins `` `values.question` ``; replace that phrase with `` `question_junior` `` in the same
  commit.
- The J-LANG walkthrough (`framework/tests/study/test_l3_language.py`) does not read the
  templates; the manual Copilot acceptance (§5.4) checks that a French session's exploration
  questions are French.
