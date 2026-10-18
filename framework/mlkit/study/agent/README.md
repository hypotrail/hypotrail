# Study agent instruction templates

Placeholder (plan WP1.4). WP4.1 fills this directory with the instructions that
`hypotrail init` copies into a new study workspace (plan §5):

- `CLAUDE.md`: the short, non-negotiable rules (always read `hypotrail status --json`
  first, never compute ad hoc, the three pauses, verbatim confirmation, a fresh
  `request_id` per intent, stale-revision handling, no causality);
- `.claude/skills/hypotrail-study/SKILL.md`: pedagogy (term first, then the contextual
  explanation; guidance loop; glossary; `keep_baseline` is a valid result);
- `.claude/commands/hypotrail-resume.md`: reread `status`, summarise, propose the next
  action.

`init` copies every file of this directory, keeping its relative path, **except this
README**. It never overwrites a file that already exists in the study workspace and
reports copied and skipped files under `agent_instructions` in its JSON output.
