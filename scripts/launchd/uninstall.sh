#!/bin/bash
# Usuwa zadania launchd pipeline'u Morning Scout (wszystkie albo wskazane).
#
#   scripts/launchd/uninstall.sh                 # wszystkie local.betting-analyst.*
#   scripts/launchd/uninstall.sh closing         # tylko wybrane
set -uo pipefail

DEST="$HOME/Library/LaunchAgents"
DOMAIN="gui/$(id -u)"

JOBS=("$@")
[[ ${#JOBS[@]} -eq 0 ]] && JOBS=(morning claude-morning closing report)

for job in "${JOBS[@]}"; do
  label="local.betting-analyst.$job"
  target="$DEST/$label.plist"
  launchctl bootout "$DOMAIN/$label" 2>/dev/null && echo "Zatrzymano $label"
  if [[ -f "$target" ]]; then
    rm "$target"
    echo "Usunięto $target"
  fi
done
