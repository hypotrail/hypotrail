#!/usr/bin/env bash
# Installs the Hypotrail study panel (clients/vscode-companion) into the VS Code attached to
# this machine or codespace. Thin wrapper over `hypotrail setup vscode` (Onboarding Lot 1):
# the VSIX is built in pure Python from the panel's sources, so no Node is needed.
#
#   scripts/workshop/install-panel.sh [--build-only] [--force] [--quiet]
#
#   --build-only  only write the VSIX to .workshop-cache/ (git-ignored), install nothing
#   --force       reinstall even when the same version is installed
#   --quiet       print only errors
#
# Install: `hypotrail setup vscode` uses the `code` command of a VS Code integrated terminal
# when present, else the VS Code server's own CLI (code-server, found under /vscode,
# ~/.vscode-remote or ~/.vscode-server), else `code` on PATH. After an install, an open
# window needs "Developer: Reload Window" to show the panel's commands.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CACHE="${HYPOTRAIL_WORKSHOP_CACHE:-$REPO/.workshop-cache}"
HYP=(uv run --quiet --project "$REPO/framework" hypotrail)

build_only=0 force=() quiet=0
for arg in "$@"; do
  case "$arg" in
    --build-only) build_only=1 ;;
    --force) force=(--force) ;;
    --quiet) quiet=1 ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

if [ "$build_only" = 1 ]; then
  version="$(sed -n 's/^  "version": "\([^"]*\)".*/\1/p' "$REPO/clients/vscode-companion/package.json" | head -n 1)"
  mkdir -p "$CACHE"
  args=(setup vscode --vsix-out "$CACHE/hypotrail-companion-${version:-0}.vsix")
else
  args=(setup vscode ${force[@]+"${force[@]}"})
fi
if ! out="$("${HYP[@]}" "${args[@]}" --format text)"; then
  echo "[panel] $out" >&2
  exit 1
fi
[ "$quiet" = 1 ] || printf '[panel] %s\n' "$out"
