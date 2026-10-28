#!/usr/bin/env bash
# Packages the Hypotrail study panel (clients/vscode-companion, plain JavaScript, no build
# step) as a VSIX and installs it into the VS Code attached to this machine or codespace.
#
#   scripts/workshop/install-panel.sh [--build-only] [--force] [--quiet]
#
# Why a VSIX: --extensionDevelopmentPath does not exist in Codespaces, and the panel is not
# published. The package is made from a staged copy of extension.js, package.json,
# README.md, lib/ and media/ (the tests and their 11 MB of baselines are left out), with a
# pinned @vscode/vsce run through npx; the panel's sources are not modified. The VSIX is
# written to .workshop-cache/ (git-ignored) and rebuilt only when a source is newer.
#
# Install: the `code` command of a VS Code integrated terminal when present, else the VS
# Code server's own CLI (code-server --install-extension), found under /vscode,
# ~/.vscode-remote or ~/.vscode-server. After an install, an open window needs
# "Developer: Reload Window" to show the panel's commands.
set -euo pipefail

VSCE_VERSION="3.9.2"
EXTENSION_ID="hypotrail-local.hypotrail-companion"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="$REPO/clients/vscode-companion"
CACHE="${HYPOTRAIL_WORKSHOP_CACHE:-$REPO/.workshop-cache}"

build_only=0 force=0 quiet=0
for arg in "$@"; do
  case "$arg" in
    --build-only) build_only=1 ;;
    --force) force=1 ;;
    --quiet) quiet=1 ;;
    -h|--help) sed -n '2,18p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done
say() { [ "$quiet" = 1 ] || printf '[panel] %s\n' "$*"; }

version="$(sed -n 's/^  "version": "\([^"]*\)".*/\1/p' "$SRC/package.json" | head -n 1)"
VSIX="$CACHE/hypotrail-companion-${version:-0}.vsix"

build() {
  if [ -f "$VSIX" ] && [ "$force" = 0 ] && \
     [ -z "$(find "$SRC/extension.js" "$SRC/package.json" "$SRC/lib" "$SRC/media" -newer "$VSIX" -print -quit)" ]; then
    say "VSIX up to date: $VSIX"
    return 0
  fi
  command -v npx >/dev/null 2>&1 || { echo "npx (Node.js) is needed to package the panel" >&2; return 1; }
  mkdir -p "$CACHE"
  local stage status=0
  stage="$(mktemp -d)"
  cp -R "$SRC/extension.js" "$SRC/package.json" "$SRC/README.md" "$SRC/lib" "$SRC/media" "$stage/"
  say "packaging $EXTENSION_ID $version with @vscode/vsce@$VSCE_VERSION"
  (cd "$stage" && npx --yes "@vscode/vsce@$VSCE_VERSION" package \
      --no-dependencies --allow-missing-repository --skip-license --no-rewrite-relative-links \
      --out "$VSIX" >/dev/null) || status=$?
  rm -rf "$stage"
  [ "$status" = 0 ] || { echo "packaging failed (vsce exit $status)" >&2; return "$status"; }
  say "VSIX: $VSIX"
}

find_cli() {
  if [ -n "${VSCODE_IPC_HOOK_CLI:-}" ] && command -v code >/dev/null 2>&1; then
    echo code; return 0
  fi
  local found
  found="$(find /vscode "$HOME/.vscode-remote" "$HOME/.vscode-server" -maxdepth 6 \
             -type f -name code-server -path '*/bin/code-server' -printf '%T@ %p\n' 2>/dev/null \
           | sort -rn | head -n 1 | cut -d' ' -f2-)"
  [ -n "$found" ] && { echo "$found"; return 0; }
  command -v code >/dev/null 2>&1 && code --version >/dev/null 2>&1 && { echo code; return 0; }
  return 1
}

build
[ "$build_only" = 1 ] && exit 0

if ! cli="$(find_cli)"; then
  say "no VS Code CLI here; install by hand: Extensions view > ... > Install from VSIX... > $VSIX"
  exit 1
fi
if [ "$force" = 0 ] && "$cli" --list-extensions 2>/dev/null | grep -qix "$EXTENSION_ID"; then
  say "$EXTENSION_ID already installed"
  exit 0
fi
"$cli" --install-extension "$VSIX" --force >/dev/null
say "$EXTENSION_ID installed; run \"Developer: Reload Window\" if its commands do not appear"
