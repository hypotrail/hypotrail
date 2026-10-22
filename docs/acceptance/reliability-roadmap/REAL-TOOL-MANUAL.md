# Reliability roadmap — real-tool acceptance script

Status: **not run**. Preparing this script does not authorize installing extensions,
changing a VS Code profile, opening a paid model session, or spending an agent budget.

Use a new synthetic study outside this repository. Record the tested commit, date, OS,
VS Code version, Copilot/extension versions, Marimo version, task, language, and evidence
paths. Keep raw sessions outside the repository and redact secrets.

1. Open the temporary study in VS Code and select the generated Hypotrail custom agent.
2. Verify that it quotes the exact pending proposal and offers localized choices.
3. Choose Explain; verify that state and revision do not change and the same proposal returns.
4. Adopt it; inspect proposal ID, `choice` channel, and verbatim label with the CLI.
5. Complete the study with one changed choice and resume it in a fresh chat.
6. Open HTML and the generated notebook. Verify that opening triggers no fit or evaluation.
7. Press the notebook recomputation button once; compare the supported synthetic result.
8. Add a workbench note, render again, and verify that the note and any preserved generated
   edit remain available while the report/notebook show one revision and the same figures.
9. Open the synthetic final test once and verify scope, limits, and post-opening drift wording.
10. If the panel was separately authorized, run its manual checklist and restore temporary
    settings.

For every step record expected/observed behavior, pass/fail/not-run, unexpected behavior,
screenshots or logs, and evidence location. A working text fallback does not turn a failed
choice picker into a pass. CLI and mocked-extension tests are technical evidence only.
