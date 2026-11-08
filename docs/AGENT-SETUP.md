# Hypotrail setup: instructions for a coding agent

The user asked you to set up Hypotrail on their machine. Do these steps with your terminal tool, then stop at the handover (step 6). The study itself is the user's work and happens later, in the study folder's own chat. The human-readable guide is [INSTALL.md](INSTALL.md).

## Rules

1. **Never read the user's data file.** Pass its path to `hypotrail new` and nothing else:
   - do not open, print, list, search, copy or summarise it;
   - do not run Python, pandas or any other tool on it.
   
   Hypotrail sets a final test aside before any analysis. Looking at the rows first would break that.
2. **Do not start the study.** Do not run `prepare answer`, `seal`, `init`, `decide`, `run` or `automation`, and do not pass `--automation`. Do not answer the study's questions, not even as a proposal. Those answers must be the user's own words.
3. **Ask before changing a system setting** (PowerShell execution policy, registry, long paths, global git or proxy configuration). Installing uv, the `hypotrail` tool and its VS Code panel is what the user asked for: do it.
4. **Never put a study inside a git repository or inside another study.** Claude Code also loads instruction files from parent folders. Never overwrite an existing folder; `hypotrail new` refuses one anyway.
5. **Report refusals as they are.** When a `hypotrail` command refuses, give the user its message and its `fix` or `next_action`. Do not work around it.

## Inputs

Take them from the user's prompt. Ask only for what is missing and needed, in one message:

| Input | Default |
|---|---|
| Example study, or own data | the example (Hotel booking demand) |
| Own data: the CSV path | (required) |
| Own data: a context sentence, a context file, or a brief (PDF, `.docx`, `.md`, `.txt`) | nothing: the study agent will propose answers from the column names |
| Study language | `en` (or `fr`) |
| Study name | `hotel-demo` for the example; for own data, the file's stem, lowercase, letters, digits, `.`, `_` and `-` only |
| Working folder | the current folder, when it is not inside a git repository; otherwise ask |

## Steps

The commands are the same in PowerShell, bash and zsh unless noted. Run each one and read its output before the next.

### 1. uv

Run `uv --version`. If it is missing, install it:
- Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`;
- macOS and Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`.

The current shell may not see it yet. Call it by its full path, `~/.local/bin/uv` or, on Windows, `$HOME\.local\bin\uv.exe`.

**Behind a proxy**, a download fails on a certificate or a connection. Ask the user for the proxy address, then set two variables **in this shell only**:
- `HTTPS_PROXY`, the proxy address;
- `UV_SYSTEM_CERTS=1`.

### 2. The tool

```sh
uv tool install --force "git+https://github.com/hypotrail/hypotrail#subdirectory=framework"
```

About 650 MB of dependencies; allow several minutes. If `hypotrail` is not on the `PATH` afterwards:
- run `uv tool update-shell` for the user's next terminals;
- in this shell, call it by its full path: the folder printed by `uv tool dir --bin`, plus `hypotrail` (`hypotrail.exe` on Windows).

### 3. The study panel (VS Code only)

Run `hypotrail setup vscode`.
- **On `vscode_missing`:** VS Code or its `code` command is absent. Note it for the handover and go on: the panel is optional.
- **When the company blocks the extension:** note it for the handover and go on.

### 4. The machine check

Run `hypotrail doctor --format text`.
- Every `fail` and `warn` line has a `fix`. Apply a fix that needs no system setting change (rule 3), and ask for the others.
- Run `doctor` again once at the end.
- If `platform` still fails on Windows, tell the user to use WSL2 or Codespaces (see [INSTALL.md](INSTALL.md)), and stop.

### 5. The study

**Example:**

```sh
git clone --depth 1 https://github.com/hypotrail/hypotrail.git
hypotrail new NAME --case hypotrail/use-cases/hotel-booking --lang LANG --dir studies --open
```

**Own data:** pass the path the user gave, as given. The data stay in `studies/NAME.case/`, outside the study folder. Add one of the options below, or none:
- `--context "TEXT"`, or `--context-file FILE` when the context has quotes or several lines;
- `--brief FILE`.

```sh
hypotrail new NAME --data PATH --lang LANG --dir studies --open
```

**What to check:**
- `new` answers with JSON. Check `"ok": true`, and read `next_steps` (or `next`) for the handover.
- Leave out `--open` when VS Code is absent.

### 6. Handover, then stop

Tell the user, briefly:
- what was installed;
- the final `doctor` summary, and anything left for them to do;
- the study folder's full path.

Then say how to start, and stop. Do not continue the study in this chat.

**Example study:**
- **VS Code:** open the study folder and trust it. In Copilot chat, pick Agent mode and the agent **Hypotrail**, check `vscode/askQuestions` in *Configure Tools*, then type **Let's start** (French study: **On commence**).
- **Claude Code:** `cd` into the study folder, run `claude`, then type the same words.

**Own data:** the same, except that until the study is sealed there is no Hypotrail agent in Copilot, so the user stays in plain Agent mode. They type **Prepare the study** (French: **Prépare l'étude**), and the study agent asks six questions, one at a time.
