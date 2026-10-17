# ADR 0008: Przechowywanie danych

- **Status:** Accepted
- **Data:** 2026-10-17

## Kontekst
Dane to głównie szeregi czasowe kursów (snapshoty), wyniki, cechy, flagi z newsów i rejestr zakładów. Pracujemy lokalnie na Macu, na jednym użytkowniku, z analitycznymi zapytaniami.

## Decyzja
- **DuckDB** jako jedna baza analityczna w pliku `data/betting.duckdb` (poza gitem).
- **Warstwy:**
  - `data/raw/`: surowe odpowiedzi API i scraperów (JSON/CSV/Parquet ze znacznikiem czasu), niemodyfikowalne; pozwalają odtworzyć każdą analizę;
  - `clean`: znormalizowane tabele w DuckDB (`fixtures`, `odds_snapshots`, `results`, `team_aliases`, `news_flags`);
  - `features` i `ledger`: cechy modeli, `paper_bets`/`bets`, `bankroll`.
- **Każdy snapshot kursów ma `captured_at`**, co jest kluczowe dla CLV i dla unikania patrzenia w przyszłość w backteście.
- Dostęp dla Claude: MCP `mcp-server-motherduck` **tylko do odczytu**. Zapisy idą wyłącznie przez kod (ADR 0016).
- **Backup:** okresowy eksport do Parquet.

## Rozważane opcje
- **PostgreSQL:** zbędny narzut przy jednym użytkowniku lokalnie. Wrócimy do niego przy przeniesieniu na VPS lub dostępie wieloosobowym.
- **SQLite:** słabszy do zapytań analitycznych.
