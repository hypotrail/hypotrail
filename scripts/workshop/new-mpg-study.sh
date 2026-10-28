#!/usr/bin/env bash
# Creates a fresh Auto MPG study for one workshop pair and prints what to do next.
#
#   scripts/workshop/new-mpg-study.sh [NAME] [--lang fr|en] [--automation MODE] [--from-pdf [FILE]] [--open]
#   scripts/workshop/new-mpg-study.sh --azureml-plan NAME
#
#   NAME            letters, digits, dot, dash, underscore (default: mpg-<date>-<time>)
#   --lang          the study language (default fr)
#   --automation    until_final_test or full_demo: the automatic mode, for the organiser's
#                   demo (needs an engine with `init --automation`)
#   --from-pdf      start from the product owner's PDF (R68): `init --brief-pdf` copies it into
#                   the study and imports it, so the brief stays pending until the junior adopts
#                   the agent's draft (default use-cases/auto-mpg/po/fiche-cas-usage-mpg.pdf)
#   --open          reopen this VS Code window on the study folder when done (code -r)
#   --azureml-plan  show the Azure ML export plan of an existing study: files, statuses and
#                   missing fields; it writes nothing and runs no Azure job
#
# The study goes to $HYPOTRAIL_WORKSHOP_DIR/NAME (default <repo>/studies/NAME, git-ignored).
# It is made by `hypotrail init` on use-cases/auto-mpg, run from this repository's engine
# (uv run --project <repo>/framework), so the study's agent files (.github/agents,
# .github/copilot-instructions.md, CLAUDE.md) record that command. The script then adds the
# study panel's flag and stage v3 to the study's .vscode/settings.json, installs the workshop's
# Copilot hook (.github/hooks/hypotrail.json, scripts/workshop/hooks/pretool.py: the agent's
# plain `uv run ... hypotrail` commands run without a prompt, any raw read of the data file is
# refused, everything else is asked as usual), and checks that the panel is installed in VS
# Code. Nothing that exists is overwritten.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CASE="$REPO/use-cases/auto-mpg"
ROOT="${HYPOTRAIL_WORKSHOP_DIR:-$REPO/studies}"
PY="$REPO/framework/.venv/bin/python"
HYP=(uv run --quiet --project "$REPO/framework" hypotrail)

name="" lang="fr" automation="" open=0 plan="" pdf=""
while [ $# -gt 0 ]; do
  case "$1" in
    --lang) lang="${2:-}"; shift 2 ;;
    --lang=*) lang="${1#*=}"; shift ;;
    --automation) automation="${2:-}"; shift 2 ;;
    --automation=*) automation="${1#*=}"; shift ;;
    --open) open=1; shift ;;
    --azureml-plan) plan="${2:-}"; shift 2 ;;
    --azureml-plan=*) plan="${1#*=}"; shift ;;
    --from-pdf)
      if [ $# -gt 1 ] && [[ "$2" == *.pdf ]]; then pdf="$2"; shift 2
      else pdf="$CASE/po/fiche-cas-usage-mpg.pdf"; shift; fi ;;
    --from-pdf=*) pdf="${1#*=}"; shift ;;
    -h|--help) sed -n '2,26p' "$0"; exit 0 ;;
    -*) echo "unknown option: $1 (see --help)" >&2; exit 2 ;;
    *) [ -z "$name" ] || { echo "one study name only" >&2; exit 2; }; name="$1"; shift ;;
  esac
done

fail() { echo "error: $*" >&2; exit 1; }
valid_name() { [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ ]]; }

command -v uv >/dev/null 2>&1 || fail "uv is not on PATH (run .devcontainer/post-create.sh)"
if [ ! -x "$PY" ]; then
  echo "Engine environment missing: uv sync --project framework --group dev --group azureml"
  uv sync --quiet --project "$REPO/framework" --group dev --group azureml
fi

# The study's current revision, read from `status --json`.
revision_of() {
  "${HYP[@]}" status --json --study "$1" 2>/dev/null \
    | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["revision"])'
}

# --- Azure ML export plan (end of the workshop) -------------------------------------------
if [ -n "$plan" ]; then
  valid_name "$plan" || fail "invalid study name: $plan"
  study="$ROOT/$plan"
  [ -f "$study/.hypotrail/agent.json" ] || fail "no study at $study"
  rev="$(revision_of "$study")" || fail "cannot read the study revision (hypotrail status)"
  echo "\$ ${HYP[*]} export azureml --plan --expected-revision $rev --study $study --format text"
  exec "${HYP[@]}" export azureml --plan --expected-revision "$rev" --study "$study" --format text
fi

# --- New study ----------------------------------------------------------------------------
case "$lang" in fr|en) ;; *) fail "--lang must be fr or en" ;; esac
[ -n "$name" ] || name="mpg-$(date +%Y%m%d-%H%M%S)"
valid_name "$name" || fail "invalid study name: $name (letters, digits, . _ -)"
study="$ROOT/$name"
[ ! -e "$study" ] || fail "$study already exists; choose another name"

init_args=(init --study "$study" --case "$CASE" --lang "$lang" --format text)
if [ -n "$automation" ]; then
  case "$automation" in until_final_test|full_demo) ;; *) fail "--automation must be until_final_test or full_demo" ;; esac
  "${HYP[@]}" init --help 2>/dev/null | grep -q -- '--automation' \
    || fail "this engine has no 'init --automation' (it arrives with the v0.3 feature branch); create the study without it"
  init_args+=(--automation "$automation")
fi

if [ -n "$pdf" ]; then
  [ -f "$pdf" ] || fail "no PDF at $pdf"
  init_args+=(--brief-pdf "$(cd "$(dirname "$pdf")" && pwd)/$(basename "$pdf")")
fi

mkdir -p "$ROOT"
"${HYP[@]}" "${init_args[@]}"

# Panel flag and stage in the study's settings (init writes the interpreter line only).
"$PY" - "$study/.vscode/settings.json" <<'PYEOF'
import json, os, sys
path = sys.argv[1]
wanted = {'hypotrail.companion.enabled': True, 'hypotrail.companion.stage': 'v3'}
try:
    with open(path, encoding='utf-8') as handle:
        data = json.load(handle)
except FileNotFoundError:
    data = {}
except ValueError:
    print(f'note: {path} is not plain JSON; add by hand: {json.dumps(wanted)[1:-1]}')
    sys.exit(0)
missing = {k: v for k, v in wanted.items() if k not in data}
if missing:
    data.update(missing)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(data, handle, indent=2)
        handle.write('\n')
PYEOF

# Workshop hook (VS Code agent hooks, preview): see scripts/workshop/hooks/pretool.py.
"$PY" - "$study" "$REPO" "$PY" <<'PYEOF'
import json, os, shlex, sys
study, repo, py = sys.argv[1], sys.argv[2], sys.argv[3]
path = os.path.join(study, '.github', 'hooks', 'hypotrail.json')
if not os.path.exists(path):
    command = shlex.join([py, os.path.join(repo, 'scripts', 'workshop', 'hooks', 'pretool.py'),
                          '--repo', repo, '--data-file', 'auto-mpg.data',
                          '--log', os.path.join(study, '.github', 'hooks', 'hypotrail-hook.log')])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump({'hooks': {'PreToolUse': [{'type': 'command', 'command': command, 'timeout': 10}]}},
                  handle, indent=2)
        handle.write('\n')
PYEOF

rev="$(revision_of "$study")" || fail "the study was created but 'hypotrail status' failed"

# Panel installed? Only checkable from a VS Code integrated terminal.
panel_note=""
if [ -n "${VSCODE_IPC_HOOK_CLI:-}" ] && command -v code >/dev/null 2>&1; then
  bash "$REPO/scripts/workshop/install-panel.sh" --quiet \
    || panel_note="panel: not installed, see docs/workshop/README.md (Dépannage)"
fi

first_fr="On commence" first_en="On commence"
if [ -n "$pdf" ]; then
  first_fr="Prépare l'étude à partir de la fiche du PO
     (la fiche du PO, $(basename "$pdf"), est déjà importée dans l'étude, dossier brief/ ;
     l'étape 1 du panneau l'attend jusqu'à ce que vous adoptiez la fiche dans le chat)"
  first_en="Prépare l'étude à partir de la fiche du PO
     (the PO's brief, $(basename "$pdf"), is already imported into the study, folder brief/;
     step 1 of the panel waits for it until you adopt the brief in the chat)"
fi
shell_hyp="uv run --project $REPO/framework hypotrail"
if [ "$lang" = fr ]; then
  cat <<EOF

Étude Auto MPG prête : $study (révision $rev)
${automation:+Mode automatique : $automation (choisi au lancement, revu à la fin)
}${panel_note:+$panel_note
}
Ensuite, dans l'ordre :
  1. Ouvrir l'étude comme dossier de travail (Copilot lit .github/agents à la racine du
     dossier ouvert) :   code -r "$study"
     ou File > Open Folder... > $study  (faire confiance au dossier si VS Code le demande)
  2. Palette (Ctrl+Shift+P) : « Hypotrail: open the study panel »
  3. Chat Copilot (Ctrl+Alt+I) : choisir l'agent « Hypotrail » dans la liste des agents ;
     dans « Configure Tools », vérifier que vscode/askQuestions est coché.
  4. Écrire : $first_fr
     Les commandes « uv run ... hypotrail » de l'agent passent sans demande (règle de
     l'atelier : .github/hooks/hypotrail.json, journal hypotrail-hook.log). Si VS Code
     demande quand même : lire la commande, puis « Allow in this Session ».

Rapport HTML : $study/reports/study.html (dès le premier rendu) ; notebooks Marimo :
  tiroir « Livrables » du panneau, boutons « Ouvrir dans Marimo »
Fin d'atelier, plan d'export Azure ML (n'écrit rien, aucun job Azure) :
  scripts/workshop/new-mpg-study.sh --azureml-plan $name
CLI directe : $shell_hyp status --summary --study "$study" --format text
EOF
else
  cat <<EOF

Auto MPG study ready: $study (revision $rev)
${automation:+Automatic mode: $automation (chosen at launch, reviewed at the end)
}${panel_note:+$panel_note
}
Next, in order:
  1. Open the study as the workspace folder (Copilot reads .github/agents at the root of
     the open folder):   code -r "$study"
     or File > Open Folder... > $study  (trust the folder if VS Code asks)
  2. Command palette (Ctrl+Shift+P): "Hypotrail: open the study panel"
  3. Copilot chat (Ctrl+Alt+I): pick the "Hypotrail" agent in the agent list; in
     "Configure Tools", check that vscode/askQuestions is enabled.
  4. Type: $first_en
     The agent's "uv run ... hypotrail" commands run without a prompt (workshop rule:
     .github/hooks/hypotrail.json, log hypotrail-hook.log). If VS Code still asks: read
     the command, then "Allow in this Session".

HTML report: $study/reports/study.html (from the first render); Marimo notebooks:
  the panel's "Your deliverables" section, "Open in Marimo" buttons
End of the workshop, Azure ML export plan (writes nothing, no Azure job):
  scripts/workshop/new-mpg-study.sh --azureml-plan $name
Direct CLI: $shell_hyp status --summary --study "$study" --format text
EOF
fi

if [ "$open" = 1 ]; then
  command -v code >/dev/null 2>&1 || fail "no 'code' command here: open the folder by hand"
  code -r "$study"
fi
