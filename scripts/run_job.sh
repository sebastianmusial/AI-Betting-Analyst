#!/bin/bash
# Uruchamia zadanie pipeline'u Morning Scout (wywoływane przez launchd, można też ręcznie).
#
#   scripts/run_job.sh morning   # 08:00 — skan STS + Pinnacle, paper bets, skrót na Telegram
#   scripts/run_job.sh closing   # co 15 min 11:00–23:00 — snapshot zamknięcia (limit kredytów w configu)
#   scripts/run_job.sh report    # 23:30 — raport CLV do pliku + krótkie CLV na Telegram
#   scripts/run_job.sh claude-morning   # alternatywa dla „morning”: claude -p "/morning-scout --notify"
#
# Logi: data/logs/<zadanie>-RRRR-MM-DD.log. Zadania są serializowane blokadą (DuckDB = jeden zapisujący).
# Nie stawia zakładów — tylko analiza i paper trading (ADR 0001, 0019).
set -uo pipefail

JOB="${1:-}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 1

# launchd startuje z minimalnym PATH — dodajemy typowe miejsca instalacji uv i claude.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
export COLUMNS=200  # szersze tabele rich w plikach logów
export PYTHONUNBUFFERED=1

DAY="$(date +%Y-%m-%d)"
LOG_DIR="$REPO/data/logs"
mkdir -p "$LOG_DIR" "$REPO/reports"
LOG="$LOG_DIR/$JOB-$DAY.log"
LOCK="$LOG_DIR/.pipeline.lock"

case "$JOB" in
  morning)
    CMD=(uv run python -m betting_analyst.morning --log-paper --notify) ;;
  closing)
    CMD=(uv run python -m betting_analyst.closing --minutes-before 20) ;;
  report)
    CMD=(uv run python -m betting_analyst.report --notify) ;;
  claude-morning)
    # Subskrypcja Claude (bez --bare). Skill sam robi skan, newsy, weto i wysyła skrót (--notify).
    CMD=(claude -p "/morning-scout --notify"
         --allowedTools "Bash(uv run python -m betting_analyst.*)" Read Write WebSearch WebFetch) ;;
  *)
    echo "Użycie: $0 morning|closing|report|claude-morning" >&2
    exit 64 ;;
esac

notify_failure() {
  # Maks. jedno powiadomienie o błędzie na zadanie dziennie (closing biegnie co 15 min).
  local marker="$LOG_DIR/.failed-$JOB-$DAY"
  [[ -e "$marker" ]] && return 0
  touch "$marker"
  uv run python -m betting_analyst.notify text \
    "❌ Zadanie $JOB nie powiodło się (kod $1). Log: data/logs/$JOB-$DAY.log" >>"$LOG" 2>&1 || true
}

{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') start: ${CMD[*]}"
} >>"$LOG"

# lockf (macOS): czekamy maks. 15 min na zakończenie poprzedniego zadania (np. długi skan poranny).
if [[ "$JOB" == "report" ]]; then
  # Raport do pliku (stdout), błędy i ostrzeżenia do logu.
  /usr/bin/lockf -t 900 "$LOCK" "${CMD[@]}" >"$REPO/reports/$DAY-clv.txt" 2>>"$LOG"
else
  /usr/bin/lockf -t 900 "$LOCK" "${CMD[@]}" >>"$LOG" 2>&1
fi
STATUS=$?

echo "=== $(date '+%Y-%m-%d %H:%M:%S') koniec: kod $STATUS" >>"$LOG"
if [[ $STATUS -ne 0 ]]; then
  notify_failure "$STATUS"
fi
exit "$STATUS"
