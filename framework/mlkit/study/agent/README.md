# Study agent instruction templates

`hypotrail init` installs these files into a new study workspace (plan §5, WP4.1;
`mlkit/study/agent_files.py`). They are stored under names that Claude Code and Copilot
do **not** load, so a developer session in this repository never picks up the study
agent's rules:

| Template | Study workspace |
|---|---|
| `CLAUDE.md.in` | `CLAUDE.md`, `.github/copilot-instructions.md` |
| `dot-claude/skills/hypotrail-study/SKILL.md` | `.claude/skills/hypotrail-study/SKILL.md`, `.github/skills/hypotrail-study/SKILL.md` |
| `dot-claude/commands/hypotrail-resume.md` | `.claude/commands/hypotrail-resume.md`, `.github/prompts/hypotrail-resume.prompt.md` |
| `copilot-agent.md.in` | `.github/agents/hypotrail.agent.md` (Copilot only: the custom agent "Hypotrail", whose tool list includes VS Code's `vscode/askQuestions` picker) |

The Copilot files are generated from the same source with a header comment; they are
**not tested** while directive A1 holds. Placeholders (`{{HYPOTRAIL}}`, `{{STUDY}}`,
`{{GLOSSARY}}`, `{{SKILL}}`, `{{CHOICE_TOOL}}`) are replaced at install; the CLI invocation is also recorded
in `.hypotrail/agent.json`. Existing files are never overwritten. This README is not
installed. Never add a file here under a loaded name (`CLAUDE.md`, `AGENTS.md`,
`.claude/`, `.github/`): `framework/tests/study/test_agent_files.py` refuses it.
