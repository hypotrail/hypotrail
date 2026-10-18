#!/usr/bin/env bash
# Start an agent session with the selected role environment.
#   scripts/session.sh explorer          # Claude Code
#   scripts/session.sh leak-reviewer copilot
# Never expose holdout: remove OSML_HOLDOUT_DIR from the environment.
set -euo pipefail
role="${1:?role: data-analyst | explorer | feature-builder | leak-reviewer | stop-writer | validator}"
tool="${2:-claude}"
unset OSML_HOLDOUT_DIR
export OSML_ROLE="$role" OSML_ROOT="$(pwd)"
prompt="You are acting as $role in Hypotrail-ML. Read AGENTS.md and wait for the assigned task."
case "$tool" in
  claude)  exec claude "$prompt" ;;
  copilot) echo "First message to paste: $prompt"; exec copilot ;;
  *) echo "unknown tool: $tool (claude | copilot)" >&2; exit 1 ;;
esac
