# Hypotrail study (Codespaces template)

This repository template opens a GitHub Codespace with the `hypotrail` tool and its study
panel installed. Nothing else is needed: no Node, no checkout of the engine.

## Layout

- `cases/`: your data, one folder per case (the case description `case.yaml` and its
  `data/` folder). The raw data stay here, outside the study folders, so the chat agent
  never sees them in its workspace.
- `studies/`: one folder per study, created by `hypotrail new`. Open a study as the
  workspace folder to work on it with the chat agent and the panel.

## Start a study

In the codespace terminal:

```
hypotrail doctor                       # what is installed, and how to fix the rest
hypotrail new my-study --case cases/my-case --dir studies --open
```

`hypotrail new` creates the study (its final test set aside before any look), enables the
study panel for that folder, installs the agent hook, and reopens the window on the study.
Then: Command Palette, "Hypotrail: open the study panel"; Copilot chat, pick the
"Hypotrail" agent; type "On commence" (or "Let's start").

Starting from a raw data file without a case (`hypotrail new NAME --data FILE`) arrives with
the preparation lot of the onboarding plan.

## Outside Codespaces

The same commands work on your machine:

```
uv tool install "git+https://github.com/hypotrail/hypotrail#subdirectory=framework"
hypotrail setup vscode
hypotrail doctor
```
