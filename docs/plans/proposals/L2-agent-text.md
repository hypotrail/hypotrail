# L2 agent-text proposal: rule 6 reads `panel.shown` (R1b, D3)

Lot L2 of [OWNER-SESSION-2026-10-26-PLAN](../OWNER-SESSION-2026-10-26-PLAN.md) (§3 L2, §2.4
ledger, D3). The integrator applies this text to `framework/mlkit/study/agent/CLAUDE.md.in`
against the word ledger; L2 does not edit the agent templates.

## What changes and why

The engine now gives `next_action.panel.shown` = `{tab, section, label, line}` (or `null`) on
every command surface when the panel is on: where the panel shows what **this command
produced**, named by tab and section, with a ready line in the study language
(CLI-CONTRACT §3.2, `mlkit.study.companion_env.shown`). Rule 6's own tab-by-step mapping
(Data & EDA after the data card, Decisions at a proposal, Evidence after the fits, What if? at
the decision rule or the model choice) is what pointed the owner at an empty Decisions tab
(R1b); it is removed, and the agent relays the engine's line instead. The task blocks of rule 6
disappear (the mapping was the only task-dependent part), so `{{PANEL_LINE_PLACE}}` occurs once.

## Exact replacement

Replace, in `CLAUDE.md.in`, the whole of rule 6 (from `6. **The panel.**` up to, not
including, `7. **Deliverables.**`):

```text
6. **The panel.** It is open when `next_action.panel` is present or the junior has
   already said the Hypotrail panel is open; remember it. Do not append a panel-open
   question to a resume, decision summary, or conclusion. When it is open, end each
   message that shows or changes something with one short line per step naming the tab
   to look at (`next_action.panel.where.line`, or the `panel.tabs` label of the step the
   message covers): Data & EDA ("Données et EDA") after the data card and the charts,
   Decisions ("Décisions") at a proposal, Evidence ("Preuves") after the fits, the
   diagnostics, and the opening,
<!-- hypotrail:task binary -->
   What if? ("Et si ?") at the decision rule.{{PANEL_LINE_PLACE}}
<!-- hypotrail:task regression -->
   What if? ("Et si ?") at the model choice.{{PANEL_LINE_PLACE}}
<!-- hypotrail:end -->
   The line adds to the chat; it never replaces its content. The panel can run charts,
   regenerate the deliverables, acknowledge an interruption, and export a handoff pack:
   when the revision moved without a command of yours, `status --summary --digest --since
   <your last revision>` lists them in `digest.channel_actions` (`channel` `webview`); say
   so ("you ran these charts from the panel") and use them.
```

with:

```text
6. **The panel.** It is open when `next_action.panel` is present or the junior has
   already said the Hypotrail panel is open; remember it. Do not append a panel-open
   question to a resume, decision summary, or conclusion. When it is open, end a message
   that shows or changes something with `next_action.panel.shown.line` of the last
   command it reports, verbatim; no line when `shown` is null.{{PANEL_LINE_PLACE}}
   The line adds to the chat; it never replaces its content. The panel can run charts,
   regenerate the deliverables, acknowledge an interruption, and export a handoff pack:
   when the revision moved without a command of yours, `status --summary --digest --since
   <your last revision>` lists them in `digest.channel_actions` (`channel` `webview`); say
   so ("you ran these charts from the panel") and use them.
```

No other template changes: `SKILL.md` ("5. **The panel line**, when the panel is open (CLAUDE.md
rule 6).") and `hypotrail-resume.md` stay as they are; `FLAVOUR_TEXTS[*]['PANEL_LINE_PLACE']` is
unchanged (Copilot: the last line of the picker question at a pause, else of the final message;
Claude Code: empty).

## Word count (measured on `w1-l2`, before any other lot's text)

| Measure | Binary | Regression |
|---|---|---|
| `CLAUDE.md.in`, task selected (raw) | 2,831 → 2,786 (**−45**) | 2,694 → 2,649 (**−45**) |
| Budget total of `test_the_instructions_fit_the_word_budget` (cap 4,000) | 3,999 → 3,954 | 3,958 → 3,913 |
| Rendered Copilot `CLAUDE.md` | 3,047 → 3,002 (−45) | 2,910 → 2,865 (−45) |

The §2.4 ledger estimated +15 / −45 for L2; the measured net is −45 (the relay sentence is
shorter than the mapping it replaces).

## Tests the integrator updates with the text (§2.4: no pinned phrase removed without a replacement)

`framework/tests/study/test_agent_files.py::test_the_panel_rule`:

- **Remove** the pins of the mapping: `'end each message that shows or changes something with
  one short line per step naming the tab'`, `'(`next_action.panel.where.line`, or the
  `panel.tabs` label of the step the message covers)'`, `'Data & EDA ("Données et EDA")'`,
  `'after the data card and the charts'`, `'Decisions ("Décisions") at a proposal'`,
  `'Evidence ("Preuves") after the fits, the diagnostics, and the opening'`,
  `'What if? ("Et si ?")'`, and the task check `('at the decision rule' in rule6) == (task ==
  'binary')`.
- **Add** the pins of the new rule: `'end a message that shows or changes something with
  `next_action.panel.shown.line` of the last command it reports, verbatim'`, `'no line when
  `shown` is null'`; a negative pin `'Data & EDA' not in rule6 and 'where.line' not in rule6`
  (the mapping is gone); `'shown' in ce.PANEL_KEYS and ce.SHOWN_KEYS == ('tab', 'section',
  'label', 'line')`.
- **Keep** the other pins (`'It is open when `next_action.panel` is present or the junior has
  already said the Hypotrail panel is open; remember it'`, `'Do not append a panel-open'`,
  `'it never replaces its content'`, `'`status --summary --digest'`, `'`channel` `webview`'`,
  `'"you ran these charts from the panel"'`, the Copilot `PANEL_LINE_PLACE` check).

The behaviour that moved from the template to the engine is tested by
`framework/tests/study/test_companion_env.py` (`test_shown_names_the_section_of_each_command`,
every command, stage and language; `test_shown_is_null_for_reads_and_render`;
`test_shown_names_the_choice_card_when_the_chat_asks_a_choice`;
`test_every_write_names_what_it_produced`; `test_no_panel_key_when_off`),
`framework/tests/study/test_journey_walkthrough.py` (J-PANEL engine part: every write of a
walkthrough names a section, every read past step 0 none, synthetic and Auto MPG, EN and FR)
and `clients/vscode-companion/test/test_journey_panel.py` (J-PANEL panel part: the named section
holds at least one item in the panel models), plus
`clients/vscode-companion/test/test_panel_labels.py::test_the_section_labels_equal_the_panel_copy`.
