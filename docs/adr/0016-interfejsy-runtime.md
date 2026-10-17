# ADR 0016: Interfejsy i runtime

- **Status:** Accepted
- **Data:** 2026-10-17

## Decyzja
- **Główny interfejs: Claude Code** w repo:
  - skille projektu (`.claude/skills/`): `/daily-scan`, `/daily-report`, `/match-deep-dive`, `/log-bet`, `/post-mortem`, `/backtest`, `/fit-model`, `/ingest-news`, `/add-data-source`;
  - MCP:
    - `duckdb` (mcp-server-motherduck, tylko odczyt),
    - `sportsbet-mcp` (z biblioteki sports-betting),
    - od F4 własny `betting-mcp` (FastMCP): `get_value_bets`, `analyze_match`, `log_bet`, `clv_report`, `bankroll_status`.
- **Powiadomienia:** bot Telegram przez Bot API z Pythona. Token zakłada właściciel w BotFather i trzyma w `.env`. Wysyłamy alerty kandydatów oraz raport dzienny.
- **Raport dzienny:** `reports/YYYY-MM-DD.md` (poza gitem) i skrót na Telegram.
- **Runtime:** lokalnie na Macu.
  - `launchd` uruchamia pobieranie danych (Python) i `claude -p "/daily-scan"`;
  - alternatywnie zadania zaplanowane w aplikacji desktop.
  - Cloud routines odpadają: brak dostępu do lokalnego DuckDB.
- **Później:** VPS z polskim IP (oferta polskich bukmacherów zależy od IP).

## Konsekwencje
- Mac musi być włączony w czasie zadań. Ograniczenie akceptowalne na etapie MVP.
- Zapisy do bazy wykonuje wyłącznie kod Pythona. Claude czyta przez MCP tylko do odczytu, a zapisuje przez jawne komendy lub narzędzia (`log_bet`).
