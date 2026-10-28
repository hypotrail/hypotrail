#!/usr/bin/env bash
# Prepares the workshop codespace (run by devcontainer.json's updateContentCommand, also
# during a prebuild). Idempotent: running it again only redoes what is missing or stale.
#
#   1. uv, pinned, in /usr/local/bin (on every user's PATH, including Copilot's terminal);
#   2. the engine environment: uv sync --project framework --group dev --group azureml;
#   3. the study panel (clients/vscode-companion) packaged as a VSIX, and installed into
#      VS Code when a VS Code server is already there (otherwise postAttachCommand does it).
set -euo pipefail

UV_VERSION="0.11.32"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

log() { printf '[post-create] %s\n' "$*"; }

if ! command -v uv >/dev/null 2>&1; then
  log "installing uv ${UV_VERSION}"
  installer="$(mktemp)"
  curl -LsSf "https://astral.sh/uv/${UV_VERSION}/install.sh" -o "$installer"
  if command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
    sudo env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh "$installer"
  else
    env UV_INSTALL_DIR="$HOME/.local/bin" sh "$installer"
    export PATH="$HOME/.local/bin:$PATH"
  fi
  rm -f "$installer"
fi
log "$(uv --version)"

log "syncing the engine environment (framework/.venv: dev + azureml)"
uv sync --project "$REPO/framework" --group dev --group azureml
uv run --project "$REPO/framework" hypotrail --help >/dev/null
log "engine ready: uv run --project $REPO/framework hypotrail"

log "packaging the study panel"
bash "$REPO/scripts/workshop/install-panel.sh" --build-only
# A VS Code server may already be attached (rebuild of a running codespace): install now.
bash "$REPO/scripts/workshop/install-panel.sh" --quiet || \
  log "panel not installed yet: postAttachCommand or new-mpg-study.sh will do it"
log "done"
