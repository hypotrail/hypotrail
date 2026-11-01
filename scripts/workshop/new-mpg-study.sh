#!/usr/bin/env bash
# Creates a fresh Auto MPG study for one workshop pair and prints what to do next.
#
#   scripts/workshop/new-mpg-study.sh [NAME] [--lang fr|en] [--automation MODE] [--from-pdf [FILE]] [--open]
#   scripts/workshop/new-mpg-study.sh --azureml-plan NAME
#
#   NAME            letters, digits, dot, dash, underscore (default: mpg-<date>-<time>)
#   --lang          the study language (default fr)
#   --automation    until_final_test or full_demo: the automatic mode, for the organiser's
#                   demo
#   --from-pdf      start from the product owner's PDF (R68): it is copied into the study and
#                   imported, so the brief stays pending until the junior adopts the agent's
#                   draft (default use-cases/auto-mpg/po/fiche-cas-usage-mpg.pdf)
#   --open          reopen this VS Code window on the study folder when done (code -r)
#   --azureml-plan  show the Azure ML export plan of an existing study: files, statuses and
#                   missing fields; it writes nothing and runs no Azure job
#
# The study goes to $HYPOTRAIL_WORKSHOP_DIR/NAME (default <repo>/studies/NAME, git-ignored).
# Thin wrapper over `hypotrail new NAME --case use-cases/auto-mpg` (Onboarding Lot 1), run
# from this repository's engine (uv run --project <repo>/framework), so the study's agent
# files record that command. `hypotrail new` adds the study panel's flag and stage v3 to the
# study's .vscode/settings.json, installs the study's Copilot hook (.github/hooks/
# hypotrail.json, `hypotrail hook pretool`: the agent's plain engine commands run without a
# prompt, any raw read of the data file is refused, everything else is asked as usual),
# makes no data/ link, and in a VS Code terminal installs the panel when missing. Nothing
# that exists is overwritten. Without a checkout: run `hypotrail new` directly.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CASE="$REPO/use-cases/auto-mpg"
ROOT="${HYPOTRAIL_WORKSHOP_DIR:-$REPO/studies}"
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
if [ ! -x "$REPO/framework/.venv/bin/python" ]; then
  echo "Engine environment missing: uv sync --project framework --group dev --group azureml"
  uv sync --quiet --project "$REPO/framework" --group dev --group azureml
fi

# --- Azure ML export plan (end of the workshop) -------------------------------------------
if [ -n "$plan" ]; then
  valid_name "$plan" || fail "invalid study name: $plan"
  study="$ROOT/$plan"
  [ -f "$study/.hypotrail/agent.json" ] || fail "no study at $study"
  rev="$("${HYP[@]}" status --json --study "$study" 2>/dev/null \
    | "$REPO/framework/.venv/bin/python" -c 'import json,sys; print(json.load(sys.stdin)["revision"])')" \
    || fail "cannot read the study revision (hypotrail status)"
  echo "\$ ${HYP[*]} export azureml --plan --expected-revision $rev --study $study --format text"
  exec "${HYP[@]}" export azureml --plan --expected-revision "$rev" --study "$study" --format text
fi

# --- New study: `hypotrail new` -------------------------------------------------------------
case "$lang" in fr|en) ;; *) fail "--lang must be fr or en" ;; esac
[ -n "$name" ] || name="mpg-$(date +%Y%m%d-%H%M%S)"
valid_name "$name" || fail "invalid study name: $name (letters, digits, . _ -)"
study="$ROOT/$name"
[ ! -e "$study" ] || fail "$study already exists; choose another name"

new_args=(new "$name" --case "$CASE" --dir "$ROOT" --lang "$lang" --format text)
if [ -n "$automation" ]; then
  case "$automation" in until_final_test|full_demo) ;; *) fail "--automation must be until_final_test or full_demo" ;; esac
  new_args+=(--automation "$automation")
fi
if [ -n "$pdf" ]; then
  [ -f "$pdf" ] || fail "no PDF at $pdf"
  new_args+=(--brief "$(cd "$(dirname "$pdf")" && pwd)/$(basename "$pdf")")
fi
if [ "$open" = 1 ]; then new_args+=(--open); fi

mkdir -p "$ROOT"
"${HYP[@]}" "${new_args[@]}"

if [ "$lang" = fr ]; then
  cat <<EOF

Atelier : les commandes « uv run ... hypotrail » de l'agent passent sans demande (hook de
l'étude : .github/hooks/hypotrail.json, journal hypotrail-hook.log). Si VS Code demande
quand même : lire la commande, puis « Allow in this Session ».
Rapport HTML : $study/reports/study.html (dès le premier rendu) ; notebooks Marimo : tiroir
« Livrables » du panneau, boutons « Ouvrir dans Marimo ».
Fin d'atelier, plan d'export Azure ML (n'écrit rien, aucun job Azure) :
  scripts/workshop/new-mpg-study.sh --azureml-plan $name
EOF
else
  cat <<EOF

Workshop: the agent's "uv run ... hypotrail" commands run without a prompt (the study's
hook: .github/hooks/hypotrail.json, log hypotrail-hook.log). If VS Code still asks: read the
command, then "Allow in this Session".
HTML report: $study/reports/study.html (from the first render); Marimo notebooks: the
panel's "Your deliverables" section, "Open in Marimo" buttons.
End of the workshop, Azure ML export plan (writes nothing, no Azure job):
  scripts/workshop/new-mpg-study.sh --azureml-plan $name
EOF
fi
