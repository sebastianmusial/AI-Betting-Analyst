#!/bin/bash
# Instaluje zadania launchd pipeline'u Morning Scout dla bieżącego użytkownika.
# Uruchamia WYŁĄCZNIE właściciel, ręcznie, z głównego checkoutu repo (tam gdzie data/betting.duckdb):
#
#   scripts/launchd/install.sh                       # morning + closing + report
#   scripts/launchd/install.sh claude-morning closing report   # wariant z Claude zamiast morning
#
# Odinstalowanie: scripts/launchd/uninstall.sh. Instrukcja: docs/automation.md
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="$REPO/scripts/launchd"
DEST="$HOME/Library/LaunchAgents"
DOMAIN="gui/$(id -u)"

JOBS=("$@")
[[ ${#JOBS[@]} -eq 0 ]] && JOBS=(morning closing report)

if [[ " ${JOBS[*]} " == *" morning "* && " ${JOBS[*]} " == *" claude-morning "* ]]; then
  echo "Wybierz morning ALBO claude-morning — oba naraz zapisałyby typy dwa razy." >&2
  exit 1
fi
if [[ -f "$REPO/.git" ]]; then
  echo "Uwaga: $REPO to git worktree — zadania użyją jego data/ (osobna baza). Zalecany główny checkout." >&2
  read -r -p "Kontynuować? [t/N] " answer
  [[ "$answer" == "t" || "$answer" == "T" ]] || exit 1
fi
command -v uv >/dev/null || [[ -x /opt/homebrew/bin/uv || -x "$HOME/.local/bin/uv" ]] || {
  echo "Nie znaleziono uv (https://docs.astral.sh/uv/)." >&2
  exit 1
}

mkdir -p "$DEST" "$REPO/data/logs"
chmod +x "$REPO/scripts/run_job.sh"
# Ścieżka repo może mieć spacje; escapujemy znaki specjalne sed (\, &, |).
REPO_SED="$(printf '%s' "$REPO" | sed -e 's/[\\&|]/\\&/g')"

for job in "${JOBS[@]}"; do
  label="local.betting-analyst.$job"
  template="$SRC/$label.plist"
  [[ -f "$template" ]] || { echo "Brak szablonu $template" >&2; exit 1; }
  target="$DEST/$label.plist"
  sed "s|__REPO__|$REPO_SED|g" "$template" >"$target"
  plutil -lint "$target" >/dev/null
  launchctl bootout "$DOMAIN/$label" 2>/dev/null || true
  launchctl bootstrap "$DOMAIN" "$target"
  echo "Zainstalowano $label → $target"
done

echo
echo "Sprawdzenie: launchctl print $DOMAIN/local.betting-analyst.${JOBS[0]} | head -20"
echo "Test od ręki: launchctl kickstart $DOMAIN/local.betting-analyst.${JOBS[0]}"
echo "Logi: $REPO/data/logs/"
