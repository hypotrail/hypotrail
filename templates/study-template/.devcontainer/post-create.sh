#!/usr/bin/env bash
# Installs uv and the hypotrail tool (run by devcontainer.json's postCreateCommand).
# Idempotent. HYPOTRAIL_SOURCE overrides where the tool comes from (a Git URL or a path).
set -euo pipefail

UV_VERSION="0.11.32"
SOURCE="${HYPOTRAIL_SOURCE:-git+https://github.com/hypotrail/hypotrail#subdirectory=framework}"

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

log "installing hypotrail from $SOURCE"
uv tool install --python 3.13 "$SOURCE"
uv tool update-shell >/dev/null 2>&1 || true
export PATH="$(uv tool dir --bin):$PATH"
hypotrail doctor --format text || true
log "done: open a terminal and run  hypotrail new NAME --case cases/<your-case>"
