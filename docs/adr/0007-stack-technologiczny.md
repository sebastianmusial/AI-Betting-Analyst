# ADR 0007: Stack technologiczny

- **Status:** Accepted
- **Data:** 2026-10-17

## Decyzja
- **Język:** Python 3.12.
- **Zarządzanie projektem:** `uv` (środowisko, lockfile, `uv run`).
- **Jakość:** `ruff` (lint i format), `pytest`, `pyright` (przez LSP w Claude Code).
- **Modele danych i konfiguracja:** `pydantic`, YAML w `config/`, sekrety w `.env` (nie w repo).
- **Biblioteki domenowe:** `penaltyblog`, `sports-betting` (bez extra `execution`), `soccerdata`, `shin`; później scikit-learn, LightGBM, PyMC.
- **HTTP i scraping:** `httpx`; Playwright tylko tam, gdzie konieczny (OddsHarvester).
- **CLI i wyjście:** `rich`.
- **Konwencje:** kod i identyfikatory po angielsku, dokumentacja i komentarze domenowe po polsku. Pakiet `src/betting_analyst/`.

## Rozważane opcje
- **TypeScript/Node:** odrzucone; słabszy ekosystem statystyczny.
- **Poetry / pip-tools:** `uv` jest szybszy i prostszy.
