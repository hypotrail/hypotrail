# Install and start Hypotrail

Hypotrail runs on Windows (native PowerShell), macOS and Linux, without Node. You install one tool, `hypotrail`, then create a study with one command and run it in the chat of your coding agent (GitHub Copilot in VS Code, or Claude Code).

Three ways to begin:

- [A. Let your coding agent set everything up](#a-let-your-coding-agent-set-everything-up): paste one prompt.
- [B. Install by hand and start on an example](#b-install-by-hand-and-start-on-an-example).
- [C. Start on your own data](#c-start-on-your-own-data), with a short context, a product owner's brief, or nothing.

For a workshop in GitHub Codespaces, see the [participants' guide](workshop/README.md) (in French).

## Requirements

- **uv**, which installs Python 3.13 itself when it is missing.
  - Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
  - macOS and Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh` (or `brew install uv` on macOS)

  Open a new terminal afterwards.
- **git**, to fetch the example cases.
- **A coding agent with a chat:**
  - **GitHub Copilot** in VS Code 1.109 or later, with Agent mode. The `code` command must be on the `PATH`: on macOS, Command Palette, *Shell Command: Install 'code' command in PATH*; the Windows installer adds it.
  - or **Claude Code**.
- **Behind a company proxy:** set `HTTPS_PROXY` and `UV_SYSTEM_CERTS=1` before any `uv` command (PowerShell: `$env:UV_SYSTEM_CERTS = "1"`). If the company has a PyPI mirror, also set `UV_DEFAULT_INDEX`.

## A. Let your coding agent set everything up

Open a terminal-capable agent in an empty working folder:
- VS Code with Copilot in Agent mode;
- or Claude Code started in that folder.

Then paste this prompt, after changing the last sentence to what you want:

```text
Set up Hypotrail on this machine. Fetch and follow the instructions at
https://raw.githubusercontent.com/hypotrail/hypotrail/main/docs/AGENT-SETUP.md
Ask me before changing any system setting. Create the example study (Hotel booking demand), in English.
```

For your own data, end the prompt instead with, for example:

```text
Create a study on my data file C:\data\churn.csv, with this context: "A telecom operator
wants to know, each month, which customers are likely to leave." Study language: French.
```

Or point to a brief instead of a context: `with the brief C:\data\brief.pdf` (PDF, Word `.docx`, Markdown or text).

**What the agent does:** it checks uv, installs the tool and the VS Code study panel, runs `hypotrail doctor` and applies its fixes, and creates the study. Then it stops and tells you what to type in the study's chat. The study itself stays with you:
- the agent never opens your data file;
- it never answers the study's questions for you.

The agent's instructions are in [AGENT-SETUP.md](AGENT-SETUP.md).

## B. Install by hand and start on an example

### 1. Install the tool and the study panel

The same commands work in PowerShell, macOS and Linux:

```sh
uv tool install "git+https://github.com/hypotrail/hypotrail#subdirectory=framework"
hypotrail setup vscode
hypotrail doctor
```

- **`uv tool install`** installs the engine and its dependencies, about 650 MB: pandas, scikit-learn, SciPy, Marimo, InterpretML… If `hypotrail` is not found afterwards, run `uv tool update-shell` and open a new terminal.
- **`hypotrail setup vscode`** installs the study panel in VS Code, then run *Developer: Reload Window*.
  - The panel is optional: the chat, the HTML report and the notebooks are enough.
  - Without a `code` command, `hypotrail setup vscode --vsix-out panel.vsix` writes the file; install it from the Extensions view, menu **…**, *Install from VSIX…*.
- **`hypotrail doctor`** checks the machine (Python, uv, VS Code, the chat agent, the panel, proxy, OneDrive folder, long paths on Windows) and prints the command that fixes each problem.

To update later, reinstall by running `uv tool install --force "git+https://github.com/hypotrail/hypotrail#subdirectory=framework"`, then `hypotrail setup vscode`.

### 2. Create the example study

The example is **Hotel booking demand**: which new bookings of a resort hotel the reservations team should contact, when it can handle only some. It is a binary scoring study on 40,060 real bookings. Several of its columns are recorded after the booking, which makes them leakage traps to find. See the [case](../use-cases/hotel-booking/README.md).

The case files come with the repository. Work in a folder of your own, in a path **without spaces**:

```sh
git clone --depth 1 https://github.com/hypotrail/hypotrail.git
hypotrail new hotel-demo --case hypotrail/use-cases/hotel-booking --dir studies --open
```

- **What it creates:** the study `studies/hotel-demo`, with its final test already set aside and sealed. The case's data stay in the case folder, outside the study folder that the chat agent sees.
- **Language:** add `--lang fr` for a study in French.
- **Without VS Code:** leave out `--open`.

**Another example, with a product owner's brief.** **Auto MPG** is a regression case, and its brief is a PDF in French:

```sh
hypotrail new mpg-demo --case hypotrail/use-cases/auto-mpg --brief hypotrail/use-cases/auto-mpg/po/fiche-cas-usage-mpg.pdf --dir studies --open
```

### 3. Run the study in the chat

- **GitHub Copilot.** VS Code opens on the study folder; trust the folder if asked. Then:
  1. Command Palette (`Ctrl+Shift+P`), **Hypotrail: open the study panel** (optional).
  2. Copilot chat (`Ctrl+Alt+I`):
     - pick Agent mode and the agent **Hypotrail**;
     - in *Configure Tools*, check `vscode/askQuestions`;
     - type **Let's start**, or **Prepare the study from the PO's brief** for Auto MPG.
- **Claude Code:** `cd studies/hotel-demo`, then `claude`, then type **Let's start**. Later, `/hypotrail-resume` picks the study up where it stopped.

**What happens next:**
- The agent shows the data card first.
- It then proposes each decision, and records it only with your own words or an explicit delegation.
- After each recorded change it regenerates the report and the notebooks: `reports/study.html` is the report, and the notebooks are in `notebooks/`.

## C. Start on your own data

Install as in [B.1](#1-install-the-tool-and-the-study-panel), then give `hypotrail new` your data file instead of a case. Choose one of three inputs:

```sh
# with a short context, in your own words
hypotrail new churn --data churn.csv --context "A telecom operator wants to know, each month, which customers are likely to leave." --dir studies --open

# with the product owner's brief: PDF, Word .docx, Markdown .md or text .txt
hypotrail new churn --data churn.csv --brief brief.pdf --dir studies --open

# with nothing: the agent proposes answers from the column names and structure
hypotrail new churn --data churn.csv --dir studies --open
```

- **A longer context:** put it in a UTF-8 file and pass `--context-file context.txt`.
- **Language:** add `--lang fr` for a study in French.

**What `new` creates:**
- `studies/churn.case/`: a copy of your file and its structural profile, outside the chat's workspace;
- `studies/churn/`: the study, in a *preparing* state.

**The data file** must be a CSV in strict UTF-8, with a header row and one record per line. `new` refuses anything else with a reason, before writing anything.

**Prepare and seal, in the chat.** Open the study folder:
- in VS Code with Copilot, Agent mode;
- or with Claude Code, `cd studies/churn`, then `claude`.

Type **Prepare the study**. The agent asks six questions, one at a time:
1. Have you already explored this file?
2. What is the target, and its positive label for a yes/no target?
3. What does one row represent?
4. When is the prediction made, and is the use about the future?
5. Do entities recur (a customer, a vehicle, a patient)?
6. Do you accept this final test?

**How the questions work:**
- The agent proposes each answer with its source: the brief's page, your context, or a column name. It records the answer only in your own words.
- Before sealing it sees only the file's structure, never the target crossed with other columns.
- **The final test is deduced from your answers, never chosen.** For example: "temporal on `signup_day` because the use is about the future". It is shown to you in words and counts.
- `hypotrail seal` then sets the final test aside and turns the folder into a normal study. In Copilot, the **Hypotrail** agent appears after a *Reload Window*.

**When it refuses:**
- **A date used as the time of the prediction:** the engine needs a whole-number clock. The agent proposes `hypotrail prepare derive-clock --column signup_date --date-format %Y-%m-%d`, which appends the day number of each date to the case's copy of the file. Your own file is not changed. When a date such as `03/04/2025` could be read either way, you are asked whether the day or the month comes first.
- **Too few rows for a final test:** sealing is refused, with the reason. The minimums are 100 rows in the final test and, for a yes/no target, 30 cases of the rarer value. Nothing switches silently to another method.

**To try this path without your own file**, use the example's CSV (from the clone of B.2) as if it were yours:

```sh
hypotrail new hotel-raw --data hypotrail/use-cases/hotel-booking/data/hotel-resort.csv --context "A resort hotel wants to know, when a booking is entered, which bookings are likely to be cancelled." --dir studies --open
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `hypotrail` not found after the install | `uv tool update-shell`, then open a new terminal |
| `uv tool install` fails (network, certificate) | Proxy settings in [Requirements](#requirements) |
| The command "Hypotrail: open the study panel" is missing | `hypotrail setup vscode`, then *Developer: Reload Window* |
| The agent **Hypotrail** is missing in Copilot | Open the study folder itself and *Reload Window*. A study that is still preparing has no Hypotrail agent yet: use Agent mode |
| "extension not allowed" | Your company filters extensions; the panel is optional |
| Something else on the machine | `hypotrail doctor` prints the fix for each check |

Reference: [CLI contract §20–21](specs/CLI-CONTRACT.md), and [how Hypotrail works inside](explainer/hypotrail-internals.html) (in French).
